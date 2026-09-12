"""Bộ chạy bench (ADR-005 V8) — validate ×k, chạy một client, báo cáo, xuất Harbor.

Khuôn `tests/dogfood/_runner.py`. Phần cần agent bật bằng ``AISEF_BENCH=1``.

**Cách ly lịch sử.** Không dùng `WorktreeManager`: worktree thấy mọi ref
`story/*`, tức là thấy gold. Mỗi trạng thái là `git archive <base>` bung vào
một `git init` mới — đúng một commit, không ref nào khác (unit kiểm
`git rev-list --all`). Tạo tác của lượt gốc (`_bmad-output/evidence`,
`journal`, `reviews`, `sprint-status.json`, `ledger.json`) bị bỏ khỏi bản
chép: đó là lịch sử, không phải mã. `node_modules` của e9 được **nhân bản**
(`cp -c`, APFS clone) chứ không symlink — test ghi `node_modules/.cache`,
symlink là ghi ngược vào e9 đang có lượt agent chạy.

**validate.** base+test ẩn và base+test+gold, mỗi bên `runs` lần; test đổi
kết cục giữa các lần → `flaky_ids`, loại khỏi F2P/P2P và nêu tên; không còn
F2P → INVALID; gold còn đỏ → INVALID. Chạy qua `tools.run_tool` (sandbox
theo cấu hình dự án: e9 khai `use_docker: false` có lý do; task lỗi kho chạy
suy biến vì ảnh `python:3.12-alpine` không có git mà unit kho cần git).
`isolation` ghi vào kết quả, không giấu.

**run.** Một phiên client với guard như hợp quy (`compile_for` + `--settings`,
env `AISEF_*`), `note mode=bench` trong bằng chứng, không reviewer/security,
không merge, không `sprint-status`. Sau phiên: hoàn nguyên tệp test agent
chạm (`changed_files ∩ is_test_path`), áp `tests.patch`, commit tạm để có SHA
ứng viên, chạy test ở SHA ấy (bằng chứng mang `candidate`), chấm
PASS/FAIL/INVALID/UNRUNNABLE theo **tên** F2P/P2P — không theo mã thoát.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.base import ClientAdapter, RunSpec  # noqa: E402
from aisef.kit.fetch import remove_tree  # noqa: E402
from aisef.clients.compile import compile_for, write_compile_report  # noqa: E402
from aisef.config import Config  # noqa: E402
from aisef.control.impact import is_test_path  # noqa: E402
from aisef.harness.guardrails import (  # noqa: E402
    ENV_BASE_REF, ENV_PROJECT, ENV_STORY_ID, ENV_WORKDIR, ENV_WRITE_SCOPE, changed_files, head_sha,
)
from aisef.harness.observe import NOTE, Event, EvidenceStore  # noqa: E402
from aisef.harness.testlog import parse as parse_testlog  # noqa: E402
from aisef.harness.tools import describe_tools, image_for, run_tool  # noqa: E402

from ._mine import KEEP_DIR, Task, _git  # noqa: E402

ENABLED = os.environ.get("AISEF_BENCH") == "1"

#: Lệnh `--client <id>` nào trong `aisef.clients.simulated` không tốn tiền,
#: không cần AISEF_BENCH=1, không chạy compile_for.  Bộ lọc chứ không phải
#: bí danh để tránh nhầm "opencode" với "opencode-mini".
SIMULATED_CLIENTS: frozenset[str] = frozenset({"simulated-weak"})

PASS, FAIL, INVALID, UNRUNNABLE = "PASS", "FAIL", "INVALID", "UNRUNNABLE"


def make_client(client_id: str) -> ClientAdapter:
    """Build an adapter by id — bench-only dispatch.

    ``ADAPTERS`` lives in ``aisef.clients.compile`` and is the production
    registry: only ``claude`` and ``opencode``.  Simulated weak/strong
    clients live in ``aisef.clients.simulated`` and are reached via
    this lookup, so the production compile surface does not grow.

    Tests instantiate directly (``SimulatedWeakAdapter()``); this
    helper exists so the bench CLI does not branch by string.
    """
    if client_id == "simulated-weak":
        from aisef.clients.simulated import SimulatedWeakAdapter

        return SimulatedWeakAdapter()
    from aisef.clients.compile import ADAPTERS

    if client_id not in ADAPTERS:
        raise ValueError(f"client not supported: {client_id}. Available: "
                         f"{', '.join(sorted({*ADAPTERS, *SIMULATED_CLIENTS}))}")
    return ADAPTERS[client_id]()


def is_simulated(client: ClientAdapter) -> bool:
    """True for clients that bypass ``AISEF_BENCH=1`` and ``compile_for``."""
    return getattr(client, "id", "") in SIMULATED_CLIENTS

#: Lịch sử của lượt gốc — không vào bản chép.
_STRIP = ("_bmad-output/evidence", "_bmad-output/journal", "_bmad-output/reviews",
          "_bmad-output/sprint-status.json", "_bmad-output/sprint-status.json.lock",
          "_bmad-output/ledger.json", "_bmad-output/INDEX.md")


def repo_for(task: Task) -> Path:
    if task.source == "bug":
        return ROOT
    e9 = os.environ.get("AISEF_BENCH_E9", "")
    if not e9:
        raise RuntimeError("task story cần AISEF_BENCH_E9 = đường dẫn dự án e9 (chỉ đọc)")
    return Path(e9)


def apply_patch(ws: Path, patch: Path) -> None:
    if patch.is_file() and patch.stat().st_size:
        _git(ws, "apply", "--binary", str(patch))


def _clone_node_modules(repo: Path, dest: Path) -> None:
    src, dst = repo / "node_modules", dest / "node_modules"
    if not src.is_dir() or dst.exists():
        return
    if subprocess.run(["cp", "-Rc", str(src), str(dst)], capture_output=True).returncode:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, symlinks=True)


def materialize(task: Task, dest: Path | str, *, tests: bool = False, gold: bool = False) -> Path:
    """Bản chép `base` không lịch sử, `.ai/config.json` trỏ đúng lệnh test của task,
    một commit `nền`. `tests`/`gold` áp patch **trước** commit nền."""
    repo = repo_for(task)
    dest = Path(dest)
    remove_tree(dest)          # ignore_errors leaves read-only .git objects behind
    dest.mkdir(parents=True)
    tar = subprocess.run(["git", "archive", "--format=tar", task.base], cwd=repo,
                         capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        tf.extractall(dest, filter="data")
    for rel in _STRIP:
        p = dest / rel
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    for p in (dest / "_bmad-output").glob("LOOP-REPORT-*.md"):
        p.unlink()
    _clone_node_modules(repo, dest)
    cfg_path = dest / ".ai" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
    cfg.update({"tools.test": task.verify, "sandbox.use_docker": task.use_docker, "sandbox.allow_degraded": True})
    cfg_path.parent.mkdir(exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # `git init` **trước** khi áp patch: bản chép nằm trong `.bench/` của chính kho,
    # `git apply` chưa có repo riêng sẽ tìm thấy kho bao ngoài, coi đường dẫn trong
    # patch là "ngoài thư mục" và lặng lẽ bỏ qua với mã thoát 0 (đo 2026-09-06:
    # bug-13 F2P = 0 vì test hồi quy chưa từng được áp).
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "config", "user.email", "bench@aisef")
    _git(dest, "config", "user.name", "bench")
    (dest / ".git" / "info" / "exclude").write_text("node_modules/\n", encoding="utf-8")
    if tests:
        apply_patch(dest, task.dir / "tests.patch")
    if gold:
        apply_patch(dest, task.dir / "gold.patch")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-qm", f"nền: {task.id} @{task.base[:7]}")
    return dest


def _run_tests(ws: Path, **kw):
    return run_tool("test", ws, config=Config.load(ws), **kw)


# ------------------------------------------------------------ validate


def validate(task: Task, runs: int = 3) -> Task:
    """Điền `f2p_ids`/`p2p_ids`/`flaky_ids`/`validated`; task hỏng mang `invalid_reason`.
    Chạy lại thì chấm lại từ đầu — kết luận lần trước không phải lý do để bỏ qua
    (đo 2026-09-06: lần validate đầu hỏng vì patch chưa áp, ba lần sau trả lại
    đúng kết luận cũ mà không chạy gì)."""
    if not task.base or not task.read("tests.patch"):   # loại từ lúc đào — không có gì để chạy
        return task
    task.invalid_reason, task.f2p_ids, task.p2p_ids, task.flaky_ids = "", [], [], []
    logs: dict[str, list] = {}
    for state, gold in (("base", False), ("gold", True)):
        ws = materialize(task, KEEP_DIR / "validate" / task.id / state, tests=True, gold=gold)
        logs[state] = []
        for _ in range(runs):
            res = _run_tests(ws)
            log = parse_testlog(res.stdout + "\n" + res.stderr)
            if res.unrunnable or not log.test_ids:
                task.invalid_reason = (f"{state}: không chạy được / không đọc được tên test — "
                                       f"{res.unrunnable or res.tail(3)}")
                task.validated = {"base_fail": False, "gold_pass": False, "runs": runs}
                task.save()
                return task
            logs[state].append(log)

    def verdict(ls) -> dict[str, set[bool]]:   # id → tập {xanh?} qua các lần; vắng mặt = không xanh
        ids = {i for l in ls for i in l.test_ids}
        return {i: {i in l.passed for l in ls} for i in ids}

    base, gold = verdict(logs["base"]), verdict(logs["gold"])
    flaky = sorted(i for i in set(base) | set(gold)
                   if len(base.get(i, {False})) > 1 or len(gold.get(i, {False})) > 1)
    green_gold = {i for i, v in gold.items() if v == {True}} - set(flaky)
    task.f2p_ids = sorted(i for i in green_gold if base.get(i, {False}) == {False})
    task.p2p_ids = sorted(i for i in green_gold if base.get(i) == {True})
    task.flaky_ids = flaky
    red_gold = sorted(i for i, v in gold.items() if False in v and i not in flaky)
    task.validated = {"base_fail": bool(task.f2p_ids), "gold_pass": not red_gold, "runs": runs}
    if red_gold:
        task.invalid_reason = "base+test+gold còn đỏ: " + ", ".join(red_gold[:5])
    elif not task.f2p_ids:
        task.invalid_reason = "không test nào đỏ ở base rồi xanh ở gold (F2P = 0)"
    task.save()
    return task


# ------------------------------------------------------------ run


@dataclass
class Result:
    task_id: str
    client: str
    attempt: int
    outcome: str
    f2p_pass: int = 0
    f2p_total: int = 0
    p2p_red: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    turns: int = 0
    duration_ms: int = 0
    files: int = 0          # diff nguồn base..ứng viên, không tính test
    lines: int = 0
    guard_block: int = 0
    candidate: str = ""
    isolation: str = ""
    error: str = ""


def _prompt(task: Task, ws: Path, cfg: Config) -> str:
    scope = "\n".join(f"- `{p}`" for p in task.write_scope)
    return (
        task.read("prompt.md").rstrip()
        + "\n\n## Phạm vi được ghi\n\n" + scope
        + "\n\nGuard chặn mọi thao tác ghi ngoài phạm vi này, ngay lúc ghi.\n\n## Công cụ\n\n"
        + describe_tools(ws, cfg)
        + "\n\nChạy `test` qua công cụ sau mỗi lần sửa và trước khi kết thúc: cổng đọc bằng "
        "chứng, không đọc lời kể. Không sửa, không đổi tên, không xoá test có sẵn.\n"
    )


def run(task: Task, client: ClientAdapter, attempts: int = 3, *, bare: bool = False) -> list[Result]:
    condition = f"{client.id}-bare" if bare else client.id
    out: list[Result] = []
    sim = is_simulated(client)
    for n in range(1, attempts + 1):
        if task.invalid_reason or not task.validated.get("gold_pass"):
            out.append(Result(task.id, condition, n, INVALID, error=task.invalid_reason or "chưa validate"))
            continue
        ws = materialize(task, KEEP_DIR / "run" / condition / task.id / f"a{n}", tests=task.tests_visible)
        base = head_sha(ws)
        root = ws / "_bmad-output"
        if not bare and not sim:
            # Simulated clients do not run real hooks — skip compile_for
            # so the worktree stays free of a misleading settings.json.
            write_compile_report(ws, [compile_for(client.id, ws, aisef_bin=str(ROOT / "bin" / "aisef"))])
        store = EvidenceStore(root)
        store.record(task.id, Event(kind=NOTE, name="mode",
                                    detail={"mode": "bench", "client": condition, "attempt": n,
                                            "base": base, "bare": bare,
                                            "sim": sim}))
        cfg = Config.load(ws)
        prompt = _prompt(task, ws, cfg)
        sim_env = (
            {
                "AISEF_BENCH_TASK_DIR": str(task.dir),
                "AISEF_BENCH_AISEF_ROOT": str(ROOT),
                "AISEF_BENCH_ATTEMPT": str(n),
                "AISEF_BENCH_BASE_SHA": base,
            }
            if sim
            else {}
        )
        if bare:
            spec = RunSpec(
                prompt=prompt, workdir=ws, max_turns=cfg["run.max_turns"],
                timeout_seconds=cfg["run.timeout_seconds"],
                env=sim_env,
            )
        else:
            settings = ws / ".claude" / "settings.json"
            spec = RunSpec(
                prompt=prompt, workdir=ws, max_turns=cfg["run.max_turns"],
                timeout_seconds=cfg["run.timeout_seconds"],
                settings_file=settings if settings.is_file() and not sim else None,
                env={
                    **sim_env,
                    ENV_WRITE_SCOPE: ",".join(task.write_scope), ENV_STORY_ID: task.id,
                    ENV_BASE_REF: base, ENV_WORKDIR: str(ws), ENV_PROJECT: str(ws),
                },
            )
        result = client.run(spec)
        store.agent_run(task.id, result, name=f"{task.id}#{n}", prompt_chars=len(prompt))

        # guard.protect (BERBench): test agent chạm bị hoàn nguyên, rồi test ẩn mới được áp.
        for p in [p for p in changed_files(str(ws), base_ref=base) if is_test_path(p)]:
            if _git(ws, "ls-tree", "--name-only", base, "--", p):
                _git(ws, "checkout", base, "--", p)
            else:
                (ws / p).unlink(missing_ok=True)
        if not task.tests_visible:
            apply_patch(ws, task.dir / "tests.patch")
        _git(ws, "add", "-A", "--", ".", ":(exclude)_bmad-output", ":(exclude).claude", ":(exclude).aisef")
        _git(ws, "commit", "-qm", f"{task.id}: ứng viên lượt {n}", check=False)   # không có gì để chốt = HEAD
        cand = head_sha(ws)
        res = run_tool("test", ws, story_id=task.id, artifact_root=root, config=cfg, candidate=cand)
        out.append(_grade(task, condition, n, result, res, ws, base, cand, len(store.read(task.id).guard_blocks)))
    KEEP_DIR.mkdir(parents=True, exist_ok=True)
    with (KEEP_DIR / "results.jsonl").open("a", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    return out


def _grade(task: Task, client_id: str, n: int, result, res, ws: Path, base: str, cand: str,
           guard_block: int) -> Result:
    log = parse_testlog(res.stdout + "\n" + res.stderr)
    r = Result(task.id, client_id, n, FAIL, f2p_total=len(task.f2p_ids), cost_usd=result.cost_usd,
               turns=result.num_turns, duration_ms=result.duration_ms, guard_block=guard_block,
               candidate=cand, isolation=str(res.detail.get("isolation", "")), error=result.error)
    if res.unrunnable or not log.test_ids:
        r.outcome, r.error = UNRUNNABLE, res.unrunnable or "không đọc được tên test"
        return r
    r.f2p_pass = sum(1 for i in task.f2p_ids if i in log.passed)
    r.p2p_red = [i for i in task.p2p_ids if i not in log.passed]
    r.outcome = PASS if r.f2p_pass == r.f2p_total and not r.p2p_red else FAIL
    for line in _git(ws, "diff", "--numstat", base, cand).splitlines():
        a, d, p = line.split("\t", 2)
        if not is_test_path(p):
            r.files += 1
            r.lines += (int(a) + int(d)) if a != "-" else 0
    return r


def load_results() -> list[Result]:
    p = KEEP_DIR / "results.jsonl"
    if not p.is_file():
        return []
    return [Result(**json.loads(l)) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


# ------------------------------------------------------------ report


def report(results: list[Result], tasks: list[Task] | None = None) -> str:
    """task × client × lượt, rồi pass@1/pass@k, ổn định (mọi lượt cùng kết cục), cost so lịch sử."""
    hist = {t.id: t for t in tasks or []}
    lines = [f"# Bench — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC", "",
             "| task | client | lượt | kết cục | F2P | P2P đỏ | $ | turn | ms | tệp/dòng | guard chặn | cách ly | ghi chú |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.task_id} | {r.client} | {r.attempt} | {r.outcome} | {r.f2p_pass}/{r.f2p_total} | "
                     f"{len(r.p2p_red)} | {r.cost_usd:.2f} | {r.turns} | {r.duration_ms} | {r.files}/{r.lines} | "
                     f"{r.guard_block} | {r.isolation} | {r.error[:60]} |")
    groups: dict[tuple[str, str], list[Result]] = {}
    for r in results:
        groups.setdefault((r.task_id, r.client), []).append(r)
    lines += ["", "## Theo task × client", "",
              "| task | client | pass@1 | pass@k | ổn định | $/lượt | $ lịch sử | tỉ lệ |",
              "|---|---|---|---|---|---|---|---|"]
    n = p1 = pk = stable = cost_ok = cost_n = 0
    for (tid, cl), rs in sorted(groups.items()):
        if all(x.outcome == INVALID for x in rs):
            lines.append(f"| {tid} | {cl} | – | – | – | – | – | INVALID: {rs[0].error[:50]} |")
            continue
        n += 1
        a = sum(x.outcome == PASS for x in rs) / len(rs)
        k = int(any(x.outcome == PASS for x in rs))
        s = len({x.outcome for x in rs}) == 1
        p1, pk, stable = p1 + a, pk + k, stable + s
        cost = sum(x.cost_usd for x in rs) / len(rs)
        hc = float(hist[tid].history.get("cost_usd") or 0.0) if tid in hist else 0.0
        if hc:
            cost_n, cost_ok = cost_n + 1, cost_ok + (cost <= 2 * hc)
        lines.append(f"| {tid} | {cl} | {a:.2f} | {k} | {'✓' if s else '✗'} | {cost:.2f} | {hc:.2f} | "
                     f"{f'{cost / hc:.2f}×' if hc else '–'} |")
    if n:
        lines += ["", f"**pass@1** {p1 / n:.2f} · **pass@k** {pk / n:.2f} · **ổn định** {stable}/{n} · "
                      f"**cost ≤ 2× lịch sử** {cost_ok}/{cost_n}"]
    clients = sorted({cl for _, cl in groups})
    bare_pairs = [(cl.replace("-bare", ""), cl) for cl in clients if cl.endswith("-bare")]
    for base_cl, bare_cl in bare_pairs:
        if base_cl not in clients:
            continue
        lines += ["", f"## So sánh {base_cl} (AISEF) vs {bare_cl} (bare)", "",
                  "| task | AISEF pass@1 | bare pass@1 | delta | AISEF $/lượt | bare $/lượt | guard chặn |",
                  "|---|---|---|---|---|---|---|"]
        a_p1 = a_cost = b_p1 = b_cost = 0
        a_n = b_n = a_guard = 0
        for tid in sorted({t for t, _ in groups}):
            a_rs = groups.get((tid, base_cl), [])
            b_rs = groups.get((tid, bare_cl), [])
            if not a_rs or not b_rs or all(x.outcome == INVALID for x in a_rs + b_rs):
                continue
            ap = sum(x.outcome == PASS for x in a_rs) / len(a_rs)
            bp = sum(x.outcome == PASS for x in b_rs) / len(b_rs)
            ac = sum(x.cost_usd for x in a_rs) / len(a_rs)
            bc = sum(x.cost_usd for x in b_rs) / len(b_rs)
            gb = sum(x.guard_block for x in a_rs)
            a_p1 += ap; b_p1 += bp; a_cost += ac; b_cost += bc; a_guard += gb
            a_n += 1; b_n += 1
            d = ap - bp
            lines.append(f"| {tid} | {ap:.2f} | {bp:.2f} | {d:+.2f} | {ac:.2f} | {bc:.2f} | {gb} |")
        if a_n:
            lines += ["",
                f"**AISEF pass@1** {a_p1 / a_n:.2f} vs **bare pass@1** {b_p1 / b_n:.2f} "
                f"(delta {(a_p1 - b_p1) / a_n:+.2f})",
                f"**AISEF $/lượt trung bình** {a_cost / a_n:.2f} vs **bare** {b_cost / b_n:.2f} "
                f"(tỉ lệ {a_cost / b_cost:.2f}× nếu bare > 0)" if b_cost else "",
                f"**Guard chặn tổng** {a_guard} lần trên {a_n} task"]
    bad = [t for t in tasks or [] if t.invalid_reason or t.flaky_ids]
    if bad:
        lines += ["", "## Task loại / test chập chờn", ""]
        for t in bad:
            lines.append(f"- `{t.id}`: {t.invalid_reason or 'ok'}"
                         + (f" · flaky: {', '.join(t.flaky_ids)}" if t.flaky_ids else ""))
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------ export Harbor

_TEST_SH = """#!/bin/sh
# Verifier Harbor: áp test ẩn, chạy lệnh test của dự án, ghi reward 0/1.
# Chấm bằng mã thoát (Harbor không có tên test); bộ chạy nội bộ chấm theo tên F2P.
set -u
cd /app
[ -s /tests/tests.patch ] && { git apply --binary /tests/tests.patch 2>/dev/null || patch -p1 < /tests/tests.patch; }
if {verify}; then r=1; else r=0; fi
mkdir -p /logs/verifier
echo "$r" > /logs/verifier/reward.txt
"""

_SOLVE_SH = """#!/bin/sh
# Oracle: áp gold — chứng minh verifier tự chứng minh được (Harbor `--agent oracle` = 1.0).
set -eu
cd /app
[ -s /solution/gold.patch ] && git apply --binary /solution/gold.patch
"""

_TASK_TOML = """version = "1.0"

[metadata]
author_name = "AISEF bench (ADR-005 V8)"
difficulty = "medium"
category = "software-engineering"
tags = ["aisef", "{source}"]

[verifier]
timeout_sec = 1800.0

[agent]
timeout_sec = 1800.0

[environment]
build_timeout_sec = 600.0
"""


def export(task: Task, out_dir: Path | str) -> Path:
    """Thư mục định dạng Harbor — adapter ngoài, không nhập runtime. Bản chép `base`
    đóng trong `environment/snapshot.tar` (không `.git`, không URL kho)."""
    out = Path(out_dir) / task.id
    shutil.rmtree(out, ignore_errors=True)
    for d in ("environment", "tests", "solution"):
        (out / d).mkdir(parents=True)
    repo = repo_for(task)
    (out / "environment" / "snapshot.tar").write_bytes(subprocess.run(
        ["git", "archive", "--format=tar", task.base], cwd=repo, capture_output=True, check=True).stdout)
    (out / "environment" / "Dockerfile").write_text(
        f"FROM {image_for(repo)}\nWORKDIR /app\nADD snapshot.tar /app\n", encoding="utf-8")
    (out / "instruction.md").write_text(task.read("prompt.md"), encoding="utf-8")
    (out / "task.toml").write_text(_TASK_TOML.format(source=task.source), encoding="utf-8")
    (out / "tests" / "tests.patch").write_text(task.read("tests.patch"), encoding="utf-8")
    (out / "tests" / "test.sh").write_text(_TEST_SH.replace("{verify}", task.verify), encoding="utf-8")
    (out / "solution" / "gold.patch").write_text(task.read("gold.patch"), encoding="utf-8")
    (out / "solution" / "solve.sh").write_text(_SOLVE_SH, encoding="utf-8")
    for sh in (out / "tests" / "test.sh", out / "solution" / "solve.sh"):
        sh.chmod(0o755)
    return out
