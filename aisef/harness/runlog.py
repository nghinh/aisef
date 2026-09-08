"""Human-readable run log — one timestamped line per event, 512KB rotation."""

from __future__ import annotations

import time
from pathlib import Path

_LOG_MAX_BYTES = 512 * 1024
_LOG_NAME = "run.log"


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
