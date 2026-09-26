"""P0 packaging guard: `aisef2` must not ship inside the `aisef` wheel, and `aisef` must.

`include = ["aisef*"]` also matches `aisef2`; the exclude keeps V2 scaffolding out. Applies the same
`fnmatchcase` filter setuptools' package discovery applies, so it needs no setuptools. The one-time proof with the
real discovery function is closure-evidence/v2/P0-PACKAGING-EXCLUDE.json.
"""

from __future__ import annotations

import fnmatch
import tomllib

MUST_SHIP = ("aisef", "aisef.control", "aisef.harness")
MUST_NOT_SHIP = ("aisef2", "aisef2.arch")


def check(pyproject_text: str) -> list[str]:
    cfg = tomllib.loads(pyproject_text)["tool"]["setuptools"]["packages"]["find"]
    inc, exc = cfg.get("include", []), cfg.get("exclude", [])

    def shipped(name: str) -> bool:
        return any(fnmatch.fnmatchcase(name, p) for p in inc) and not any(fnmatch.fnmatchcase(name, p) for p in exc)

    return [f"{n} would NOT ship in the aisef wheel" for n in MUST_SHIP if not shipped(n)] + \
           [f"{n} would ship in the aisef wheel" for n in MUST_NOT_SHIP if shipped(n)]
