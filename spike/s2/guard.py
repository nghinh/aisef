#!/usr/bin/env python3
"""Guard thử: chặn Write/Edit ra ngoài src/. Exit 2 = chặn (Claude Code)."""
import json, sys
try:
    ev = json.load(sys.stdin)
except Exception as e:
    print(f"guard: không đọc được input: {e}", file=sys.stderr); sys.exit(0)
path = (ev.get("tool_input") or {}).get("file_path", "")
if path and "/src/" not in path and not path.endswith("/src"):
    print(f"CHẶN: {path} nằm ngoài write_scope (src/)", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
