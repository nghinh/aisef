"""Lệnh ``doctor`` — kiểm môi trường, cấu hình, hook và skill đã cài."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import Config, ConfigError
from ._common import EXIT_NOT_READY, EXIT_OK


def _hook_paths_elsewhere(project: Path) -> list[str] | None:
    """Đường dẫn dự án ghi trong hook/plugin biên dịch mà **khác** dự án này.
    None khi không có hook nào để so."""
    import re as _re

    goc = project.resolve()
    thay: list[str] = []
    hook = project / ".claude" / "settings.json"
    if hook.is_file():
        thay += _re.findall(r"--project\s+(\S+)\s+guard", hook.read_text(encoding="utf-8", errors="replace"))
    plugin = project / ".opencode" / "plugin" / "aisef-guard.ts"
    if plugin.is_file():
        thay += _re.findall(r'const PROJECT = "([^"]+)"', plugin.read_text(encoding="utf-8", errors="replace"))
    if not thay:
        return None
    return sorted({p for p in thay if Path(p).resolve() != goc})


def cmd_doctor(args) -> int:
    """Kiểm tra môi trường có đủ chạy framework không."""
    project = Path(args.project)
    problems: list[str] = []
    lines: list[str] = []

    def check(label: str, ok: bool, detail: str = "", *, required: bool = True) -> None:
        mark = "✅" if ok else ("✗" if required else "○")
        lines.append(f"  {mark} {label}{(' — ' + detail) if detail else ''}")
        if required and not ok:
            problems.append(label)

    lines.append("Môi trường:")
    check("python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    check("git", bool(shutil.which("git")))

    claude = shutil.which("claude")
    check("claude CLI", bool(claude), claude or "không tìm thấy", required=False)
    opencode = shutil.which("opencode")
    check("opencode CLI", bool(opencode), opencode or "không tìm thấy", required=False)

    docker_ok = False
    if shutil.which("docker"):
        try:
            docker_ok = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=10
            ).returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            docker_ok = False
    check(
        "docker daemon",
        docker_ok,
        "chạy" if docker_ok else "không chạy — sandbox sẽ suy biến, bảo đảm thấp hơn",
        required=False,
    )

    from ..harness.browser import availability as browser_availability
    from ..harness.tools import image_for

    browser_why = browser_availability(project)
    check(
        "playwright + chromium",
        not browser_why,
        "sẵn sàng" if not browser_why else f"{browser_why} — không trích được hợp đồng mockup",
        required=False,
    )

    lines.append("Dự án:")
    check("thư mục dự án", project.is_dir(), str(project))
    from ..harness import sandbox as _sandbox

    try:
        cfg_for_sandbox = Config.load(project)
        image = image_for(project, cfg_for_sandbox)
        spec = _sandbox.SandboxSpec(
            workspace=project, cmd=["true"],
            use_docker=cfg_for_sandbox["sandbox.use_docker"],
            provider=cfg_for_sandbox["sandbox.provider"],
        )
    except ConfigError:
        image, spec = "?", _sandbox.SandboxSpec(workspace=project, cmd=["true"])
    # Provider đang dùng và bảo đảm nó khai (ADR-005 V5): người đọc biết
    # bằng chứng sắp ghi `degraded` vì **thiếu gì**, trước khi chạy story nào.
    try:
        prov, missing = _sandbox.select_provider(spec)
    except (RuntimeError, ValueError, ImportError, AttributeError) as e:
        prov, missing = None, []
        check("sandbox provider", False, str(e), required=False)
    if prov is not None:
        co = sorted(g.value for g, s in prov.guarantees(spec.level).items() if s.blocks_at_source)
        check(
            "sandbox provider", not missing,
            f"{prov.id} — bảo đảm ở {spec.level.value}: {', '.join(co) or 'không có'}"
            + (f"; THIẾU {', '.join(missing)} — công cụ chạy ngoài cách ly, bằng chứng ghi degraded"
               if missing else ""),
            required=False,
        )
    if prov is not None and prov.id == "docker":
        # Chỉ Docker mới bàn về ảnh; provider khác chạy công cụ của máy.
        check(
            "ảnh sandbox",
            image != "alpine:latest",
            image + (" — không có công cụ của stack nào, test sẽ đỏ vì thiếu công cụ"
                     if image == "alpine:latest" else " (hợp stack)"),
            required=False,
        )
    req = project / "docs" / "requirements.md"
    check("docs/requirements.md", req.is_file(), str(req))

    # Hook sinh ra ≠ hook chạy. Story chạy trong worktree; worktree chỉ có
    # `.claude/` nếu dự án commit nó. Harness nay truyền `--settings` tường
    # minh (G4), nhưng thứ đó chỉ được chứng minh bằng hợp quy — ở đây nói
    # thẳng tình trạng để người đọc biết mình đang dựa vào lớp nào.
    plugin = project / ".opencode" / "plugin" / "aisef-guard.ts"
    if plugin.is_file():
        tracked = subprocess.run(
            ["git", "-C", str(project), "ls-files", "--error-unmatch", str(plugin)],
            capture_output=True, text=True, timeout=10,
        ).returncode == 0
        check(
            "plugin OpenCode trong worktree",
            tracked,
            "`.opencode/plugin` đã commit — worktree tự có plugin" if tracked else
            "`.opencode/plugin` chưa commit — worktree KHÔNG có plugin, OpenCode chạy "
            "story với zero guard (đo hợp quy 2026-09-05); commit `.opencode/` hoặc "
            "không dùng OpenCode cho `run`",
            required=False,
        )
    hook = project / ".claude" / "settings.json"
    if hook.is_file():
        tracked = subprocess.run(
            ["git", "-C", str(project), "ls-files", "--error-unmatch", str(hook)],
            capture_output=True, text=True, timeout=10,
        ).returncode == 0
        check(
            "hook trong worktree",
            tracked,
            "`.claude/settings.json` đã commit — worktree tự có hook" if tracked else
            "`.claude/settings.json` chưa commit — worktree không có hook; harness "
            "truyền `--settings` tường minh, cổng story mục \"guard có chạy\" sẽ "
            "trượt nếu hook không tới",
            required=False,
        )

    # Guard framework thêm sau lần `compile` cuối thì hook cũ không biết —
    # ví dụ `process-ref` (luật 6, 2026-09-05). Không kiểm thì guard mới chỉ
    # có trong mã, không có trong phiên agent nào.
    rep = project / "_bmad-output" / "compile-report.json"
    if rep.is_file():
        from ..harness.guardrails import GUARD_MATCHERS

        try:
            data = json.loads(rep.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        for c in data.get("clients", []):
            thieu = sorted(set(GUARD_MATCHERS) - set(c.get("guards_wired") or []) - set(c.get("guards_post_hoc") or []))
            check(
                f"hook {c.get('client')} đủ guard", not thieu,
                f"{len(GUARD_MATCHERS)} guard" if not thieu else
                f"thiếu {', '.join(thieu)} — framework có guard mới sau lần biên dịch; chạy `aisef compile --client {c.get('client')}`",
            )

    # Ngưỡng cỡ story chỉ đáng tin chừng nào nó còn khớp dữ liệu thật
    # (ADR-004 R5). Bảng hiệu chuẩn do `run` tự ghi sau mỗi story.
    from ..control import complexity

    rows = complexity.load_calibration(project / "_bmad-output")
    if rows:
        lech_nguong = complexity.divergence(rows)
        check(
            "ngưỡng cỡ story khớp dữ liệu", not lech_nguong,
            f"{len(rows)} story đã đo, không thấy lệch" if not lech_nguong else
            "; ".join(lech_nguong) + " — chỉnh `story.max_complexity` trong "
            "`.ai/config.json` hoặc xem lại trọng số ở `control/complexity.py`",
            required=False,
        )

    lech = _hook_paths_elsewhere(project)
    if lech is not None:
        check(
            "hook trỏ đúng dự án", not lech,
            "đường dẫn `--project`/`PROJECT` trong hook khớp thư mục này" if not lech else
            f"hook trỏ sang {', '.join(lech[:2])} — dự án bị chép/di chuyển? guard sẽ ghi bằng "
            "chứng vào dự án ấy; chạy `aisef compile` lại",
        )

    try:
        cfg = Config.load(project)
        check("cấu hình", True, cfg.source)
        lenh = str(cfg.get("tools.test", "") or "")
        if lenh:
            co_cov = any(k in lenh for k in ("--coverage", "--cov", "--experimental-test-coverage", "c8 ", "nyc "))
            check(
                "lệnh test in coverage", co_cov,
                "cổng `coverage.min` đọc được số" if co_cov else
                f"`tools.test` = `{lenh}` không in coverage → mục coverage của cổng sẽ là **chưa cấu hình** "
                "(thêm `--coverage` / `--cov` / `--experimental-test-coverage`)",
                required=False,
            )
            # Tên test đọc được không (ADR-005 V9)? Có bằng chứng thì tin bằng
            # chứng: lần `tool_run test` gần nhất ghi `test_format`; chưa có
            # thì đoán từ cờ lệnh. e9/par: 220/377 lần test không đọc được tên.
            from ..harness.observe import TOOL_RUN, EvidenceStore

            store = EvidenceStore(project / "_bmad-output")
            lan = [e for sid in store.stories() for e in store.read(sid).of(TOOL_RUN)
                   if e.name in ("test", "test:baseline") and not e.detail.get("skipped")]
            if lan:
                doc_ten = bool(lan[-1].detail.get("test_format"))
                vi = f"lần test gần nhất ghi test_format={lan[-1].detail.get('test_format') or ''!r}"
            else:
                doc_ten = any(k in lenh for k in ("-v", "--verbose", "--reporter=verbose",
                                                  "--test-reporter", "node --test", "ctrf"))
                vi = "chưa có bằng chứng — đoán từ cờ lệnh"
            check(
                "lệnh test in tên test", doc_ten,
                f"cổng đọc được tên test ({vi})" if doc_ten else
                f"{vi} → mục `tiêu chí có test`/`không làm đỏ test có sẵn` là **chưa cấu hình**. "
                "Dùng reporter in tên hoặc CTRF: pytest `-v` hay `pip install pytest-json-ctrf` + "
                "`pytest --ctrf /dev/stdout`; vitest `--reporter=verbose` hay `vitest-ctrf-json-reporter` "
                "(in `vitest-ctrf/report.json` ra stdout, giữ mã thoát); node `--test-reporter=spec|tap`",
                required=False,
            )
    except ConfigError as e:
        check("cấu hình", False, str(e))

    skills_dir = project / ".claude" / "skills"
    if skills_dir.is_dir():
        from ..kit.security_filter import Verdict, classify_all

        installed = [d for d in skills_dir.iterdir() if d.is_dir()]
        lines.append("Skill đã cài:")
        check("có skill", bool(installed), f"{len(installed)} thư mục")

        # Bất biến: skill tấn công không bao giờ được có mặt trong dự án.
        offensive = [
            c.skill.name
            for c in classify_all(skills_dir)
            if c.verdict is Verdict.OFFENSIVE
        ]
        # Skill của framework nằm trong kho framework; dự án giữ một bản
        # sao. Sửa skill mà không cài lại thì agent vẫn chạy bản cũ, và
        # cách duy nhất phát hiện là ngồi so từng file.
        from ..kit.install import OWN_SKILLS

        stale = []
        for own in sorted(OWN_SKILLS.glob("*/SKILL.md")) if OWN_SKILLS.is_dir() else []:
            copied = skills_dir / own.parent.name / "SKILL.md"
            if copied.is_file() and copied.read_bytes() != own.read_bytes():
                stale.append(own.parent.name)
        check(
            "skill framework cập nhật",
            not stale,
            "khớp bản gốc" if not stale
            else f"cũ hơn kho: {', '.join(stale)} — chạy `aisef setup`",
            required=False,
        )

        check(
            "không có skill tấn công",
            not offensive,
            "sạch" if not offensive else f"LỌT: {', '.join(offensive[:5])}",
        )
    else:
        lines.append("Skill đã cài:")
        check("đã chạy setup", False, "chưa — chạy: aisef setup", required=False)

    print("\n".join(lines))
    if problems:
        print(f"\n✗ thiếu: {', '.join(problems)}")
        return EXIT_NOT_READY
    print("\n✅ sẵn sàng")
    return EXIT_OK
