"""WP-0.2 — the architecture catalog, generated from `aisef2/arch/enums.py`, with a `--check` twin.

`--check` fails closed in BOTH directions, and names which one:

* a vocabulary or member present in code but absent from the committed catalog;
* a vocabulary or member present in the committed catalog but absent from code;

plus a frozen-item or RFC-section disagreement, plus any remaining byte-level drift.

    python -P validation/v2/gen_arch_catalog.py            # write docs/implementation/v2/arch-catalog.md
    python -P validation/v2/gen_arch_catalog.py --check    # fail on drift
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG_REL = "docs/implementation/v2/arch-catalog.md"
_ROW = re.compile(r"^\| `(\w+)` \| (F\d+) \| (§[\d.]+) \| (.*) \|$")

HEADER = (
    "# AISEF V2 — architecture catalog\n\n"
    "**Generated from `aisef2/arch/enums.py` by `validation/v2/gen_arch_catalog.py`. Do not hand-edit:** `--check`\n"
    "fails in both directions — a member in code but not here, and a member here but not in code. WP-0.3 separately\n"
    "requires the code to agree with the frozen RFC.\n\n"
    "| vocabulary | frozen item | RFC | members |\n"
    "|---|---|---|---|\n"
)


def code_vocabularies(root: pathlib.Path = ROOT) -> dict[str, tuple[str, str, list[str]]]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from aisef2.arch import enums
    return {name: (item, section, [m.value for m in enum]) for name, (enum, item, section) in
            enums.VOCABULARIES.items()}


def render(vocab: dict[str, tuple[str, str, list[str]]]) -> str:
    rows = [f"| `{n}` | {item} | {sec} | " + ", ".join(f"`{v}`" for v in members) + " |"
            for n, (item, sec, members) in vocab.items()]
    total = sum(len(m) for _, _, m in vocab.values())
    return HEADER + "\n".join(rows) + f"\n\n{len(vocab)} vocabularies, {total} members.\n"


def parse(text: str) -> dict[str, tuple[str, str, list[str]]]:
    out = {}
    for line in text.splitlines():
        m = _ROW.match(line)
        if m:
            out[m.group(1)] = (m.group(2), m.group(3), re.findall(r"`([^`]+)`", m.group(4)))
    return out


def compare(code: dict, catalog_text: str) -> list[str]:
    cat = parse(catalog_text)
    problems = []
    for n in code.keys() - cat.keys():
        problems.append(f"in code, absent from catalog: vocabulary {n}")
    for n in cat.keys() - code.keys():
        problems.append(f"in catalog, absent from code: vocabulary {n}")
    for n in code.keys() & cat.keys():
        ci, cs, cm = code[n]
        ki, ks, km = cat[n]
        for v in [v for v in cm if v not in km]:
            problems.append(f"in code, absent from catalog: {n}.{v}")
        for v in [v for v in km if v not in cm]:
            problems.append(f"in catalog, absent from code: {n}.{v}")
        if (ci, cs) != (ki, ks):
            problems.append(f"frozen item / RFC section differ for {n}: code {ci} {cs}, catalog {ki} {ks}")
    if not problems and catalog_text != render(code):
        problems.append("catalog differs from its generated form (byte-level drift)")
    return sorted(problems)


def check(root: pathlib.Path = ROOT) -> list[str]:
    path = root / CATALOG_REL
    if not path.exists():
        return [f"{CATALOG_REL} is missing"]
    return compare(code_vocabularies(root), path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        problems = check()
        for p in problems:
            print(f"FAIL  {p}")
        print("architecture catalog: " + ("FAIL" if problems else "PASS"))
        return 1 if problems else 0
    text = render(code_vocabularies())
    (ROOT / CATALOG_REL).write_text(text, encoding="utf-8")
    print(f"wrote {CATALOG_REL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
