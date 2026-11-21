"""F2 (v2.3; W1-DESIGN §7, DEPENDENCY-DAG R6): typed test markers. After 2.2 they are the only source of a release
exception; a hand-authored version-scoped allowlist is history (2.1.0) and is never honoured again.

A test declares, next to itself, why its failure on a platform is not a product signal:

    from validation.qualification.test_markers import marker

    class C(unittest.TestCase):
        @marker(category="platform-harness", id="V21-36", reason="...", platforms=["windows"],
                positive="v2.test_y.Y.test_the_product_path_is_covered_on_windows")
        def test_x(self): ...

`collect()` reads every marker from the SOURCE (AST over tests/, never by importing a test), so what is excepted is
exactly what is written. A marker is refused (a problem, and release_qualify FAILs on any problem) unless:
  * `category` is `sealing` or `platform-harness`: a product or safety test is never self-excepted (R6, the
    charter's "no allowlist masking");
  * `id` is a row of docs/v2.3/MASTER-CHECKLIST.md;
  * `reason` is a non-empty string;
  * `platforms` is a non-empty subset of linux/darwin/windows, and a proper subset for `platform-harness` (a limit
    on every platform is not a platform limit);
  * the category matches the test: `sealing` only on a test the `@sealing` gate carries (tests/v2/sealing_gate.py);
  * `positive` names another test that unittest discovers and that carries no marker. It is the positive assertion
    that the path stays covered (R6). release_qualify also requires it to have passed in the same run.
A marker anywhere else (a class, a helper, a module-level function), a positional, missing, extra or non-literal
field, or two markers on one test is a problem too. The decorator is inert: it changes nothing about how a test runs.
Declared limit: a marker spelled under another name (an import alias) is not read, so it excepts nothing.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECKLIST = "docs/v2.3/MASTER-CHECKLIST.md"
CATEGORIES = frozenset({"sealing", "platform-harness"})
PLATFORMS = frozenset({"linux", "darwin", "windows"})
FIELDS = frozenset({"category", "id", "reason", "platforms", "positive"})
_ROW = re.compile(r"^\| ([^|\s][^|]*?) \| (?:NEW_WORK|OWNER_DECISION|ALREADY_FIXED|DONE|DUPLICATE|NOT_APPLICABLE) \|",
                  re.M)


def marker(**fields):
    """The declaration. Inert when the test runs: `collect` reads it from the source."""
    return lambda test: test


@dataclasses.dataclass(frozen=True)
class Marker:
    test: str                     # the unittest id, as `unittest discover -s tests` names it
    category: str
    id: str                       # a MASTER-CHECKLIST row
    reason: str
    platforms: tuple[str, ...]
    positive: str                 # the unittest id of the positive assertion
    where: str                    # tests/<path>.py:<line>


def checklist_ids(root: pathlib.Path = ROOT) -> set[str]:
    p = root / CHECKLIST
    return set(_ROW.findall(p.read_text(encoding="utf-8"))) if p.is_file() else set()


def _named(node: ast.expr, name: str) -> bool:
    f = node.func if isinstance(node, ast.Call) else node
    return isinstance(f, ast.Name) and f.id == name or isinstance(f, ast.Attribute) and f.attr == name


def _read(d: ast.expr, test: str, where: str) -> Marker | str:
    """The marker as written, or why it cannot be read."""
    if not isinstance(d, ast.Call) or d.args or any(k.arg is None for k in d.keywords):
        return f"{where}: {test}: a marker takes keyword fields only"
    names = [k.arg for k in d.keywords]
    if set(names) != FIELDS or len(names) != len(FIELDS):
        return f"{where}: {test}: the fields must be exactly {sorted(FIELDS)}, got {names}"
    try:
        f = {k.arg: ast.literal_eval(k.value) for k in d.keywords}
    except (ValueError, TypeError):
        return f"{where}: {test}: every field must be a literal"
    if not all(isinstance(f[k], str) for k in ("category", "id", "reason", "positive")) \
            or not isinstance(f["platforms"], (list, tuple)) or not all(isinstance(p, str) for p in f["platforms"]):
        return f"{where}: {test}: category/id/reason/positive must be strings and platforms a list of strings"
    return Marker(test=test, category=f["category"], id=f["id"], reason=f["reason"],
                  platforms=tuple(sorted(set(f["platforms"]))), positive=f["positive"], where=where)


def _check(m: Marker, gated: bool, tests: set[str], marked: set[str], checklist: set[str]) -> list[str]:
    out = []
    if m.category not in CATEGORIES:
        out.append(f"category {m.category!r} is not one of {sorted(CATEGORIES)}: a product or safety test is "
                   "never self-excepted (R6)")
    if m.id not in checklist:
        out.append(f"id {m.id!r} is not a checklist ID (no row in {CHECKLIST})")
    if not m.reason.strip():
        out.append("the reason is empty")
    if not m.platforms or not set(m.platforms) <= PLATFORMS:
        out.append(f"platforms {list(m.platforms)} must be a non-empty subset of {sorted(PLATFORMS)}")
    elif m.category == "platform-harness" and set(m.platforms) == PLATFORMS:
        out.append("a platform-harness marker on every platform is not a platform limit")
    if m.category == "sealing" and not gated:
        out.append("category sealing on a test the @sealing gate does not carry")
    if m.positive == m.test or m.positive not in tests or m.positive in marked:
        out.append(f"positive {m.positive!r} must name another discovered test that carries no marker")
    return [f"{m.where}: {m.test}: {p}" for p in out]


def collect(root: pathlib.Path = ROOT) -> tuple[list[Marker], list[str]]:
    """Every marker under root/tests and every problem with them. Only an empty problem list is clean."""
    tests_dir = root / "tests"
    found: list[tuple[Marker, bool]] = []
    tests: set[str] = set()
    problems: list[str] = []
    for p in sorted(tests_dir.rglob("test*.py")):
        rel = p.relative_to(root).as_posix()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError, ValueError) as e:
            problems.append(f"{rel}: cannot be read for markers ({type(e).__name__})")
            continue
        # unittest discovers a file only through packages; a test it never runs is no positive assertion
        discovered = all((d / "__init__.py").is_file() for d in p.parents if tests_dir in d.parents)
        module = rel[len("tests/"):-len(".py")].replace("/", ".")
        placed: set[ast.expr] = set()
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            for fn in cls.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not fn.name.startswith("test"):
                    continue
                test = f"{module}.{cls.name}.{fn.name}"
                if discovered:
                    tests.add(test)
                gated = any(_named(d, "sealing") for d in cls.decorator_list + fn.decorator_list)
                for d in (d for d in fn.decorator_list if _named(d, "marker")):
                    placed.add(d)
                    m = _read(d, test, f"{rel}:{d.lineno}")
                    if isinstance(m, str):
                        problems.append(m)
                    else:
                        found.append((m, gated))
        for node in ast.walk(tree):
            for d in getattr(node, "decorator_list", ()):
                if _named(d, "marker") and d not in placed:
                    problems.append(f"{rel}:{d.lineno}: a marker must decorate a test method of a top-level class")
    marked = [m.test for m, _ in found]
    problems += [f"{t}: more than one marker" for t in sorted({t for t in marked if marked.count(t) > 1})]
    checklist = checklist_ids(root)
    for m, gated in found:
        problems += _check(m, gated, tests, set(marked), checklist)
    return [m for m, _ in found], problems
