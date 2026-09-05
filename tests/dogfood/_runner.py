"""Kho hồi quy dogfood (R5): dựng lại dự án thử **từ đầu vào trong kho**, chạy
thật, so với mốc. Không dùng bản scratch — bản scratch không lặp lại được.

Bật bằng ``AISDLC_DOGFOOD=1`` (tốn tiền thật: `par` EPIC-01 ≈ $3–6).
Đầu vào của `par`: kế hoạch ở commit `9adfb59` của dự án thử, `package.json` +
`.ai/config.json` ở `963dae3` (lệnh test đã sửa — lần dogfood đầu lấy bản
`node --test src/` đỏ vì MODULE_NOT_FOUND, ba story đốt $17 trong vòng lặp
guard `completion`). `.claude/` **không** commit và **không** gitignore — đúng
kịch bản G4 và kịch bản cấu hình client bị chép vào worktree. Mốc so sánh (đo 2026-09-05,
3 story song song, Claude): 3/3 qua ở lượt đầu, $3,14.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

ENABLED = os.environ.get("AISDLC_DOGFOOD") == "1"
KEEP_DIR = Path(os.environ.get("AISDLC_DOGFOOD_DIR") or (ROOT / ".dogfood"))
INPUTS = Path(__file__).parent

#: Mốc `par` EPIC-01 — đo 2026-09-05 (commit `f0342e9`, 3 story, wave 1).
PAR_BASELINE_USD = 3.14


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()


def make_project(name: str, *, src: str = "") -> Path:
    """Chép đầu vào (`src`, mặc định cùng tên), `git init`, commit nền, biên dịch hook Claude (không commit)."""
    from aisdlc.clients.compile import compile_for, write_compile_report

    dst = KEEP_DIR / name
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(INPUTS / (src or name), dst)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=dst, check=True)
    subprocess.run(["git", "config", "user.email", "dogfood@aisdlc"], cwd=dst, check=True)
    subprocess.run(["git", "config", "user.name", "dogfood"], cwd=dst, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dst, check=True)
    subprocess.run(["git", "commit", "-qm", "nền: đầu vào dogfood"], cwd=dst, check=True)
    rep = compile_for("claude", dst, aisdlc_bin=str(ROOT / "bin" / "aisdlc"))
    write_compile_report(dst, [rep])
    return dst


def clean_env() -> dict[str, str]:
    """Không thừa hưởng `CLAUDE*` của phiên gọi (hợp quy C3)."""
    return {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}


def run_epic(project: Path, epic: str, *, client: str = "claude") -> str:
    proc = subprocess.run(
        [str(ROOT / "bin" / "aisdlc"), "run", "--epic", epic, "--client", client, "--force"],
        cwd=project, capture_output=True, text=True, env=clean_env(), timeout=3600,
    )
    (project / "_bmad-output" / "dogfood-run.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    return proc.stdout


def milestones(project: Path, story_ids: list[str]) -> dict:
    """Đọc từ đĩa: trạng thái, số lượt, chi phí, merge, mã tiêu chí, HANDOFF."""
    from aisdlc.harness.observe import AGENT_RUN, HANDOFF, TOOL_RUN, EvidenceStore
    from aisdlc.control.acceptance import missing as ac_missing

    root = project / "_bmad-output"
    st = json.loads((root / "sprint-status.json").read_text(encoding="utf-8"))["stories"]
    idx = {s["id"]: s for s in json.loads((root / "stories.index.json").read_text(encoding="utf-8"))["stories"]}
    ev = EvidenceStore(root)
    out = {"stories": {}, "cost_usd": 0.0}
    for sid in story_ids:
        e = ev.read(sid)
        xanh = [x for x in e.of(TOOL_RUN, "test") if x.ok]
        ids = list(xanh[-1].detail.get("test_ids") or []) if xanh else []
        n_ac = len(idx[sid].get("acceptance_criteria") or [])
        out["stories"][sid] = {
            "status": st.get(sid, {}).get("status"),
            # đếm lượt developer từ evidence (`<story>#<n>`) — `attempts` trong
            # sprint-status không tăng khi có lượt 2 (ghi nhận P2, 2026-09-05)
            "attempts": len([x for x in e.of(AGENT_RUN) if x.name.startswith(sid + "#")]),
            "cost_usd": e.total_cost_usd,
            "runs": len(e.of(AGENT_RUN)),
            "ac_missing": ac_missing(sid, n_ac, ids),
            "handoffs": len(e.of(HANDOFF)),
        }
        out["cost_usd"] += e.total_cost_usd
    # `main` chỉ đổi qua worktree: mọi commit không-merge sau commit nền phải
    # nằm trên một nhánh `story/*` (merge fast-forward là hợp lệ — lần dogfood 2
    # story 01-01 lên main bằng FF, đúng như git làm khi không có gì để trộn).
    logs = _git(project, "log", "--format=%H %P", "main").splitlines()
    lac = []
    for l in logs[:-1]:
        parts = l.split()
        if len(parts) < 3:   # không phải merge
            nhanh = _git(project, "branch", "--contains", parts[0])
            if "story/" not in nhanh:
                lac.append(parts[0][:8])
    out["stray_commits"] = lac
    return out
