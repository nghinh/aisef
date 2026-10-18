"""Reference implementation for the W1-a dry check only (never given to any arm). §2–§4 of docs/requirements.md."""
import os
import re

from treesum.digest import file_sha256

_LINE = re.compile(r"([0-9a-f]{64})  (.+)")


def build(root):
    if not os.path.isdir(root):
        raise NotADirectoryError(str(root))
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.isfile(full):
                out[os.path.relpath(full, root).replace(os.sep, "/")] = file_sha256(full)
    return dict(sorted(out.items()))


def dumps(snapshot):
    return "".join(f"{snapshot[p]}  {p}\n" for p in sorted(snapshot))


def loads(text):
    out = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _LINE.fullmatch(line)
        if m is None:
            raise ValueError(f"not a snapshot line: {line!r}")
        out[m[2]] = m[1]
    return out


def compare(old, new):
    return {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
            "changed": sorted(p for p in set(old) & set(new) if old[p] != new[p])}
