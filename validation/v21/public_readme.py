"""The README a package index shows, from README.md (B-10: the docs host is the owner's choice; nothing here waits on it).

On PyPI a relative link resolves against pypi.org and 404s, and this repository is private, so a link into it is no
link for a reader there. Two outputs, both refusing any relative link left:

    python3 validation/v21/public_readme.py --out PYPI-README.md                       self-contained: every link into
                                                                                       the repository becomes its path
                                                                                       as text (`docs/v2/USAGE.md`)
    python3 validation/v21/public_readme.py --base https://docs.example/aisef --out F  each such link rewritten to
                                                                                       BASE/<path> (the chosen host)

Absolute links and in-page anchors are kept. A relative link to a path the tree does not hold is refused (a broken
link is not published). The output is a new file; it never overwrites one."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")
ABSOLUTE = re.compile(r"[a-z][a-z0-9+.-]*:|#")


def render(text: str, base: str | None, root: pathlib.Path = ROOT) -> tuple[str, list[str]]:
    """(the rendered text, the problems): relative links rewritten to `base` or made text."""
    problems: list[str] = []

    def one(m: re.Match) -> str:
        bang, label, target = m.groups()
        if ABSOLUTE.match(target):
            return m.group(0)
        path = target.split("#", 1)[0]
        if not (root / path).exists():
            problems.append(f"a link to {target} names nothing in the tree")
            return m.group(0)
        if base:
            return f"{bang}[{label}]({base.rstrip('/')}/{target})"
        return f"{label} (`{path}`)" if label != path else f"`{path}`"
    out = LINK.sub(one, text)
    left = [t for _, _, t in LINK.findall(out) if not ABSOLUTE.match(t)]
    problems += [f"relative link left: {t}" for t in left]
    return out, problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--source", type=pathlib.Path, default=ROOT / "README.md")
    p.add_argument("--base", help="the public docs host's URL the repository's paths live under")
    p.add_argument("--out", type=pathlib.Path, required=True)
    a = p.parse_args(argv)
    text, problems = render(a.source.read_text(encoding="utf-8"), a.base)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    with a.out.open("x", encoding="utf-8") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
