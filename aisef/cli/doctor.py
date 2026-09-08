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

    lines.append("Environment:")
    check("python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    check("git", bool(shutil.which("git")))

    claude = shutil.which("claude")
    check("claude CLI", bool(claude), claude or "not found", required=False)
    opencode = shutil.which("opencode")
    check("opencode CLI", bool(opencode), opencode or "not found", required=False)

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
        "running" if docker_ok else "not running — sandbox will degrade, lower guarantees",
        required=False,
    )

    from ..harness.browser import availability as browser_availability
    from ..harness.tools import image_for

    browser_why = browser_availability(project)
    check(
        "playwright + chromium",
        not browser_why,
        "ready" if not browser_why else f"{browser_why} — cannot extract mockup contracts",
        required=False,
    )

    lines.append("Project:")
    check("project directory", project.is_dir(), str(project))
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
            f"{prov.id} — guarantees at {spec.level.value}: {', '.join(co) or 'none'}"
            + (f"; MISSING {', '.join(missing)} — tools run outside isolation, evidence marked degraded"
               if missing else ""),
            required=False,
        )
    if prov is not None and prov.id == "docker":
        # Chỉ Docker mới bàn về ảnh; provider khác chạy công cụ của máy.
        check(
            "sandbox image",
            image != "alpine:latest",
            image + (" — no stack tools, tests will fail due to missing tools"
                     if image == "alpine:latest" else " (matches stack)"),
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
            "OpenCode plugin in worktree",
            tracked,
            "`.opencode/plugin` committed — worktree has plugin" if tracked else
            "`.opencode/plugin` not committed — worktree has NO plugin, OpenCode runs "
            "stories with zero guards (conformance measured 2026-09-05); commit `.opencode/` or "
            "do not use OpenCode for `run`",
            required=False,
        )
    hook = project / ".claude" / "settings.json"
    if hook.is_file():
        tracked = subprocess.run(
            ["git", "-C", str(project), "ls-files", "--error-unmatch", str(hook)],
            capture_output=True, text=True, timeout=10,
        ).returncode == 0
        check(
            "hook in worktree",
            tracked,
            "`.claude/settings.json` committed — worktree has hook" if tracked else
            "`.claude/settings.json` not committed — worktree has no hook; harness "
            "passes `--settings` explicitly, story gate \"guard ran\" will "
            "fail if hook is missing",
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
                f"hook {c.get('client')} has all guards", not thieu,
                f"{len(GUARD_MATCHERS)} guards" if not thieu else
                f"missing {', '.join(thieu)} — framework has new guards since last compile; run `aisef compile --client {c.get('client')}`",
            )

    # Ngưỡng cỡ story chỉ đáng tin chừng nào nó còn khớp dữ liệu thật
    # (ADR-004 R5). Bảng hiệu chuẩn do `run` tự ghi sau mỗi story.
    from ..control import complexity

    rows = complexity.load_calibration(project / "_bmad-output")
    if rows:
        lech_nguong = complexity.divergence(rows)
        check(
            "story size thresholds match data", not lech_nguong,
            f"{len(rows)} stories measured, no divergence" if not lech_nguong else
            "; ".join(lech_nguong) + " — adjust `story.max_complexity` in "
            "`.ai/config.json` or review weights in `control/complexity.py`",
            required=False,
        )

    lech = _hook_paths_elsewhere(project)
    if lech is not None:
        check(
            "hook points to this project", not lech,
            "`--project`/`PROJECT` path in hook matches this directory" if not lech else
            f"hook points to {', '.join(lech[:2])} — project copied/moved? guards will write "
            "evidence to that project; run `aisef compile` again",
        )

    try:
        cfg = Config.load(project)
        check("config", True, cfg.source)
        lenh = str(cfg.get("tools.test", "") or "")
        if lenh:
            co_cov = any(k in lenh for k in ("--coverage", "--cov", "--experimental-test-coverage", "c8 ", "nyc "))
            check(
                "test command prints coverage", co_cov,
                "gate `coverage.min` can read the number" if co_cov else
                f"`tools.test` = `{lenh}` does not print coverage — gate coverage check will be **not configured** "
                "(add `--coverage` / `--cov` / `--experimental-test-coverage`)",
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
                vi = f"last test run recorded test_format={lan[-1].detail.get('test_format') or ''!r}"
            else:
                doc_ten = any(k in lenh for k in ("-v", "--verbose", "--reporter=verbose",
                                                  "--test-reporter", "node --test", "ctrf"))
                vi = "no evidence yet — guessing from command flags"
            check(
                "test command prints test names", doc_ten,
                f"gate can read test names ({vi})" if doc_ten else
                f"{vi} — gate `has tests`/`no existing tests broken` will be **not configured**. "
                "Use a reporter that prints names or CTRF: pytest `-v` or `pip install pytest-json-ctrf` + "
                "`pytest --ctrf /dev/stdout`; vitest `--reporter=verbose` or `vitest-ctrf-json-reporter` "
                "(prints `vitest-ctrf/report.json` to stdout, preserves exit code); node `--test-reporter=spec|tap`",
                required=False,
            )
    except ConfigError as e:
        check("config", False, str(e))

    skills_dir = project / ".claude" / "skills"
    if skills_dir.is_dir():
        from ..kit.security_filter import Verdict, classify_all

        installed = [d for d in skills_dir.iterdir() if d.is_dir()]
        lines.append("Installed skills:")
        check("has skills", bool(installed), f"{len(installed)} directories")

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
            "framework skills up to date",
            not stale,
            "matches source" if not stale
            else f"outdated: {', '.join(stale)} — run `aisef setup`",
            required=False,
        )

        check(
            "no offensive skills",
            not offensive,
            "clean" if not offensive else f"FOUND: {', '.join(offensive[:5])}",
        )
    else:
        lines.append("Installed skills:")
        check("setup completed", False, "not yet — run: aisef setup", required=False)

    print("\n".join(lines))
    if problems:
        print(f"\n✗ missing: {', '.join(problems)}")
        return EXIT_NOT_READY
    print("\n✅ ready")
    return EXIT_OK
