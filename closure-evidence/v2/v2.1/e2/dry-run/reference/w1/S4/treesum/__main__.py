"""Reference implementation for the W1-a dry check only (never given to any arm). §5 of docs/requirements.md."""
import argparse
import os
import sys

from treesum import snapshot


def _inside(path, root):
    """The relative path of `path` inside `root` (with /), or None when it lies outside."""
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(root))
    return None if rel.startswith("..") or os.path.isabs(rel) else rel.replace(os.sep, "/")


def main(argv):
    p = argparse.ArgumentParser(prog="treesum")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("dir")
    b.add_argument("-o", "--output")
    v = sub.add_parser("verify")
    v.add_argument("dir")
    v.add_argument("file")
    try:
        a = p.parse_args(argv)
    except SystemExit as e:        # argparse: 2 on a usage error, 0 on --help
        return e.code if isinstance(e.code, int) else 2
    if not os.path.isdir(a.dir):
        print(f"treesum: not a directory: {a.dir}", file=sys.stderr)
        return 2
    current = snapshot.build(a.dir)
    if a.command == "build":
        if a.output is None:
            sys.stdout.write(snapshot.dumps(current))
            return 0
        current.pop(_inside(a.output, a.dir), None)
        with open(a.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(snapshot.dumps(current))
        return 0
    try:
        with open(a.file, encoding="utf-8") as f:
            old = snapshot.loads(f.read())
    except (OSError, ValueError) as e:
        print(f"treesum: {e}", file=sys.stderr)
        return 2
    current.pop(_inside(a.file, a.dir), None)
    diff = snapshot.compare(old, current)
    kind = {p: k for k in ("added", "removed", "changed") for p in diff[k]}
    for path in sorted(kind):
        print(f"{kind[path]} {path}")
    return 1 if kind else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
