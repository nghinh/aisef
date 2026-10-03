"""Packaging guard (docs/v2/V2-STABLE-RELEASE-CHARTER.md G1, §9): the `aisef` distribution ships exactly V1 (`aisef`)
and the V2 runtime (`aisef2`, every subpackage) — never tests/, validation/ or closure-evidence/.

`check` reads pyproject's package-discovery table and applies the same `fnmatchcase` filter setuptools applies to
every package the repository holds (found the way `find_packages` walks: directories with `__init__.py`, reached only
through directories that have one), so it needs no setuptools. `artifact_problems` opens the built wheel and sdist.

    python -P validation/v2/packaging_check.py --check            # pyproject: exactly aisef + aisef2 would ship
    python -P validation/v2/packaging_check.py --artifacts dist   # the built wheel + sdist in dist/ hold exactly that
"""

from __future__ import annotations

import fnmatch
import pathlib
import sys
import tarfile
import tomllib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHIPPED = ("aisef", "aisef2")
#: sdist members outside the shipped trees that setuptools itself writes (metadata, the build config, the readme)
SDIST_METADATA = ("PKG-INFO", "pyproject.toml", "README.md", "setup.cfg", "MANIFEST.in", "aisef.egg-info")


def repo_packages(root: pathlib.Path = ROOT) -> list[str]:
    todo = [(p, p.name) for p in root.iterdir() if "." not in p.name and (p / "__init__.py").is_file()]
    out = []
    while todo:
        d, name = todo.pop()
        out.append(name)
        todo += [(c, f"{name}.{c.name}") for c in d.iterdir() if "." not in c.name and (c / "__init__.py").is_file()]
    return sorted(out)


def check(pyproject_text: str, packages: list[str] | None = None) -> list[str]:
    cfg = tomllib.loads(pyproject_text)["tool"]["setuptools"]["packages"]["find"]
    inc, exc = cfg.get("include", []), cfg.get("exclude", [])
    pkgs = repo_packages() if packages is None else packages

    def shipped(name: str) -> bool:
        return any(fnmatch.fnmatchcase(name, p) for p in inc) and not any(fnmatch.fnmatchcase(name, p) for p in exc)

    product = [n for n in pkgs if n.split(".")[0] in SHIPPED]
    return [f"{t} is not a package of the repository" for t in SHIPPED if t not in pkgs] + \
           [f"{n} would NOT ship in the aisef wheel" for n in product if not shipped(n)] + \
           [f"{n} would ship in the aisef wheel but is not aisef or aisef2" for n in pkgs if n not in product and shipped(n)]


def _sources(root: pathlib.Path) -> set[str]:
    return {p.relative_to(root).as_posix() for t in SHIPPED for p in (root / t).rglob("*.py") if "__pycache__" not in p.parts}


def artifact_problems(dist: pathlib.Path, root: pathlib.Path = ROOT) -> list[str]:
    """The one wheel and one sdist in `dist` hold every .py of aisef/ and aisef2/ and nothing outside them but metadata."""
    wheels, sdists = sorted(dist.glob("*.whl")), sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        return [f"{dist}: expected one wheel and one sdist, found {[p.name for p in (*wheels, *sdists)]}"]
    with zipfile.ZipFile(wheels[0]) as z:
        wheel = [n for n in z.namelist() if not n.endswith("/")]
    with tarfile.open(sdists[0]) as t:
        sdist = [m.name.split("/", 1)[1] for m in t.getmembers() if m.isfile() and "/" in m.name]
    want, out = _sources(root), []
    for name, members, allowed in ((wheels[0].name, wheel, ()), (sdists[0].name, sdist, SDIST_METADATA)):
        tops = {m.split("/", 1)[0] for m in members}
        out += [f"{name} ships {t} — not aisef, aisef2 or metadata" for t in sorted(tops)
                if t not in (*SHIPPED, *allowed) and not t.endswith(".dist-info")]
        out += [f"{name} lacks {rel}" for rel in sorted(want - set(members))]
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--artifacts"] and len(argv) == 2:
        problems = artifact_problems(pathlib.Path(argv[1]))
    elif argv == ["--check"]:
        problems = check((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    else:
        print(__doc__.rsplit("\n\n", 1)[1], file=sys.stderr)
        return 2
    for p in problems:
        print(f"FAIL  {p}")
    print("packaging: " + ("FAIL" if problems else "PASS (exactly aisef + aisef2)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
