"""Metadata of the operator's real OpenCode store and session folders — os.stat only, nothing opened or read."""
import json, os, pathlib, sys
home = pathlib.Path(sys.argv[1])
out = {}
for rel in (".local/share/opencode/opencode.db", ".local/share/opencode/opencode.db-wal", ".local/share/opencode/opencode.db-shm",
            ".local/share/opencode/auth.json", ".config/opencode/opencode.json"):
    p = home / rel
    out[rel] = (lambda s: {"size": s.st_size, "mtime_ns": s.st_mtime_ns, "inode": s.st_ino})(p.stat()) if p.exists() else None
for rel in (".local/share/opencode/storage", ".local/share/opencode/snapshot", ".local/share/opencode/log", ".local/share/opencode/tool-output"):
    p = home / rel
    if p.is_dir():
        names = sorted(os.listdir(p))
        out[rel] = {"entries": len(names), "dir_mtime_ns": p.stat().st_mtime_ns,
                    "newest_entry_mtime_ns": max((os.stat(p / n).st_mtime_ns for n in names), default=None)}
    else:
        out[rel] = None
print(json.dumps(out, indent=1, sort_keys=True))
