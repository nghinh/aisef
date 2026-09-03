#!/bin/sh
# Chỉ ghi log, luôn exit 0 — không được phép chặn gì.
LOG="$(dirname "$0")/probe.log"
printf '%s | project-level hook đã chạy\n' "$(date +%H:%M:%S)" >> "$LOG"
exit 0
