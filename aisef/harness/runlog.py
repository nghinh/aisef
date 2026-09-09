"""Human-readable run log — one timestamped line per event, 512KB rotation."""

from __future__ import annotations

import time
from pathlib import Path

_LOG_MAX_BYTES = 512 * 1024
_LOG_NAME = "run.log"


def one_line(text: object, limit: int = 500) -> str:
    """Collapse ``text`` to a single log line, marking any cut.

    The run log is one line per event, so a multi-line reason has to be
    folded; folding it by slicing (`reason[:120]`) cut mid-word and left the
    reader unable to tell a complete reason from a truncated one — the log
    said `lint: > todo@1.0.0 lint > node --chec` and stopped. Newlines become
    ` · `, and a cut is stated with how much was dropped; the untruncated text
    is always in evidence (`note:gate:verdict`, `tool_run` detail).
    """
    s = " · ".join(x.strip() for x in str(text).splitlines() if x.strip())
    return s if len(s) <= limit else f"{s[:limit]} …(+{len(s) - limit} chars, see evidence)"


def run_log(artifact_root: Path | str, msg: str) -> None:
    root = Path(artifact_root)
    log = root / _LOG_NAME
    root.mkdir(parents=True, exist_ok=True)
    if log.is_file() and log.stat().st_size > _LOG_MAX_BYTES:
        lines = log.read_text(encoding="utf-8").splitlines(keepends=True)
        half = len(lines) // 2
        log.write_text("".join(lines[half:]), encoding="utf-8")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"[{ts}] {msg}\n")
