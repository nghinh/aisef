"""WP-2.0.1 — Q0 static rules over the probe harness (`aisef2/probe/`). Each rule is a calibrated checker.

The rules read facts the catalog declares (`aisef2/probe/catalog.py`: where the subject runs, how the protocol is
carried, the stimulus shape) and the probe's source, so a Cycle-2 probe is checked before it exists: a rule scoped
to scenario probes is vacuous while there is none and rejects its known-bad fixture regardless.

* **PROBE_CATALOG_CLOSURE** — every probe module under `aisef2/probe/` (all but `protocol.py`, `calibration.py`,
  `catalog.py`) is registered in `CATALOG` exactly once, with the module's live `PROBE_ID`, `DIGEST`, `CLASSES` and
  `METADATA`; every entry's module exists; every observation class has a positive and a negative calibration fixture
  under `tests/v2/fixtures/calibration/<fixture_root>/<class>/`; one active entry per subject kind; a Cycle-1
  entry carries the digest the Cycle-2 freeze manifest inherits. Closed both ways: an unregistered module and an
  entry without a module both fail.
* **NO_CLOCK_IN_PROBE_FACTS** (RFC §9.2) — the clock may end an observation window; it never enters an observation.
  The child script a probe runs inside the subject's process imports neither `time` nor `datetime`; in the probe
  module no clock read (`time.time/monotonic/perf_counter…`, `datetime.now/utcnow`) appears inside the arguments of
  an `Observation`, `Executed`, `Unrunnable`, `InvalidSpec` or `ProbeRecord` construction, nor inside `verdict_of`,
  `observation_class` or `spec_class`. The Cycle-1 probe's deadline helpers read the clock outside every constructor,
  which is the shape the rule keeps.
* **NO_TEST_ARTEFACT_IN_PROBES** (invariant IX) — no string constant of a probe module or its child script, outside
  docstrings, matches the contract rule that refuses developer test artefacts (`aisef2.product.contract`): a probe
  never knows the name of a test.
* **CLOSED_DISPATCH_IN_SCENARIO_PROBES** — no wildcard `case _:` in any probe module; in a probe whose stimulus shape
  is `scenario`, an `if/elif` chain comparing one name (a step kind) never ends in an `else`: an unknown step is
  refused at admission, never given a default meaning.
* **SINGLE_PLACEHOLDER_TOKEN** — in a scenario probe the only substitution token in any string constant is `<ws>`,
  and its child script builds no string by f-string, `.format` or `%`: what the harness substitutes is one declared
  path, never text.
* **PROTOCOL_CHANNEL_DISCIPLINE** (DESIGN-CHECK-1) — a probe whose subject runs in a process of its own
  (`child_of_harness`) never references `sys.stdout` in its child script and never prints without a `file=`: the
  protocol goes to the declared channel, so a subject that writes to stdout cannot forge or break it.

    python -P validation/v2/probe_static_checks.py --check
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROBE_DIR = "aisef2/probe"
NOT_PROBES = ("__init__.py", "protocol.py", "calibration.py", "catalog.py")
FIXTURES_REL = "tests/v2/fixtures/calibration"
FREEZE_REL = "closure-evidence/v2/cycle2/CYCLE2-FREEZE-MANIFEST.json"
RULES = ("PROBE_CATALOG_CLOSURE", "NO_CLOCK_IN_PROBE_FACTS", "NO_TEST_ARTEFACT_IN_PROBES",
         "CLOSED_DISPATCH_IN_SCENARIO_PROBES", "SINGLE_PLACEHOLDER_TOKEN", "PROTOCOL_CHANNEL_DISCIPLINE")
SOURCE_RULES = RULES[1:]
CLOCK_MODULES = ("time", "datetime")
CLOCK_CALLS = {("time", "time"), ("time", "monotonic"), ("time", "monotonic_ns"), ("time", "perf_counter"),
               ("time", "perf_counter_ns"), ("time", "process_time"), ("time", "time_ns"),
               ("datetime", "now"), ("datetime", "utcnow"), ("date", "today")}
RESULT_CONSTRUCTORS = ("Observation", "Executed", "Unrunnable", "InvalidSpec", "ProbeRecord")
VERDICT_FUNCTIONS = ("verdict_of", "observation_class", "spec_class")
PLACEHOLDER = "<ws>"
_TOKEN = re.compile(r"<[a-z][a-z0-9_]*>")


def _test_artefact_rule() -> re.Pattern:
    from aisef2.product.contract import _TEST_ARTEFACT
    return _TEST_ARTEFACT


# --------------------------------------------------------------------------------------- source rules

def _docstrings(tree: ast.AST) -> set[int]:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) \
                and isinstance(n.body[0].value.value, str):
            out.add(id(n.body[0].value))
    return out


def _strings(tree: ast.AST) -> list[tuple[int, str]]:
    skip = _docstrings(tree)
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip]


def child_scripts(tree: ast.Module) -> list[tuple[str, int, ast.Module]]:
    """Module-level string constants bound to an UPPERCASE name that parse as a Python module and import something:
    the scripts a probe runs in the subject's process."""
    out = []
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and n.targets[0].id.isupper() and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            try:
                inner = ast.parse(n.value.value)
            except SyntaxError:
                continue
            if any(isinstance(x, (ast.Import, ast.ImportFrom)) for x in ast.walk(inner)):
                out.append((n.targets[0].id, n.lineno, inner))
    return out


def _is_clock_call(n: ast.AST) -> bool:
    return isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
        and (n.func.value.id, n.func.attr) in CLOCK_CALLS


def _callee(n: ast.Call) -> str | None:
    if isinstance(n.func, ast.Name):
        return n.func.id
    if isinstance(n.func, ast.Attribute):
        return n.func.attr
    return None


def _compared_name(test: ast.AST) -> str | None:
    """The name an `if` test compares (`x == "a"`, `x is K.A`, `x in (...)`), or None."""
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name):
        return test.left.id
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Attribute):
        return ast.unparse(test.left)
    return None


def _chains_with_default(tree: ast.AST) -> list[tuple[int, str]]:
    """`if/elif` chains over one compared name that end in an `else`: a dispatch with a default branch."""
    out = []
    heads = {id(n.orelse[0]) for n in ast.walk(tree)
             if isinstance(n, ast.If) and len(n.orelse) == 1 and isinstance(n.orelse[0], ast.If)}
    for n in ast.walk(tree):
        if not isinstance(n, ast.If) or id(n) in heads:
            continue
        name = _compared_name(n.test)
        if name is None:
            continue
        cur, elifs = n, 0
        while len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If) and _compared_name(cur.orelse[0].test) == name:
            cur, elifs = cur.orelse[0], elifs + 1
        if elifs and cur.orelse:
            out.append((n.lineno, name))
    return out


def violations(rel: str, source: str, rules: tuple[str, ...] = SOURCE_RULES, facts: dict | None = None) -> list[str]:
    """Rule violations in one probe module. `facts` are the module's catalog declarations (`subject_process`,
    `stimulus_shape`); without them the scoped rules do not apply (PROBE_CATALOG_CLOSURE reports the omission)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"SYNTAX {rel}:{e.lineno}: {e.msg}"]
    facts = facts or {}
    scenario = facts.get("stimulus_shape") == "scenario"
    own_process = facts.get("subject_process") == "child_of_harness"
    scripts = child_scripts(tree)
    out: list[str] = []

    if "NO_CLOCK_IN_PROBE_FACTS" in rules:
        for name, line, inner in scripts:
            for x in ast.walk(inner):
                if isinstance(x, ast.Import) and any(a.name.split(".")[0] in CLOCK_MODULES for a in x.names) \
                        or isinstance(x, ast.ImportFrom) and (x.module or "").split(".")[0] in CLOCK_MODULES:
                    out.append(f"NO_CLOCK_IN_PROBE_FACTS {rel}:{line}: child script {name} imports a clock "
                               f"(its line {x.lineno})")
                elif _is_clock_call(x):
                    out.append(f"NO_CLOCK_IN_PROBE_FACTS {rel}:{line}: child script {name} reads the clock "
                               f"(its line {x.lineno})")
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and _callee(n) in RESULT_CONSTRUCTORS:
                args = [*n.args, *(k.value for k in n.keywords)]
                if any(_is_clock_call(x) for a in args for x in ast.walk(a)):
                    out.append(f"NO_CLOCK_IN_PROBE_FACTS {rel}:{n.lineno}: a clock read inside {_callee(n)}(...)")
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in VERDICT_FUNCTIONS:
                for x in ast.walk(n):
                    if _is_clock_call(x):
                        out.append(f"NO_CLOCK_IN_PROBE_FACTS {rel}:{x.lineno}: {n.name} reads the clock")

    if "NO_TEST_ARTEFACT_IN_PROBES" in rules:
        rule = _test_artefact_rule()
        strings = _strings(tree) + [(line, s) for _, line, inner in scripts for _, s in _strings(inner)]
        for line, s in strings:
            m = rule.search(s)
            if m:
                out.append(f"NO_TEST_ARTEFACT_IN_PROBES {rel}:{line}: names a test artefact {m.group(0)!r}")

    if "CLOSED_DISPATCH_IN_SCENARIO_PROBES" in rules:
        for n in ast.walk(tree):
            if isinstance(n, ast.match_case) and isinstance(n.pattern, ast.MatchAs) and n.pattern.pattern is None \
                    and n.pattern.name is None:
                out.append(f"CLOSED_DISPATCH_IN_SCENARIO_PROBES {rel}:{n.pattern.lineno}: wildcard case")
        if scenario:
            for line, name in _chains_with_default(tree) + [(line, f"{sname}: {n}") for sname, line, inner in scripts
                                                               for _, n in _chains_with_default(inner)]:
                out.append(f"CLOSED_DISPATCH_IN_SCENARIO_PROBES {rel}:{line}: dispatch on {name} ends in a default "
                           "branch")

    if "SINGLE_PLACEHOLDER_TOKEN" in rules and scenario:
        strings = _strings(tree) + [(line, s) for _, line, inner in scripts for _, s in _strings(inner)]
        for line, s in strings:
            for tok in _TOKEN.findall(s):
                if tok != PLACEHOLDER:
                    out.append(f"SINGLE_PLACEHOLDER_TOKEN {rel}:{line}: token {tok!r}; only {PLACEHOLDER} is substituted")
        for name, line, inner in scripts:
            for x in ast.walk(inner):
                if isinstance(x, ast.JoinedStr) or isinstance(x, ast.Call) and _callee(x) == "format" \
                        or isinstance(x, ast.BinOp) and isinstance(x.op, ast.Mod):
                    out.append(f"SINGLE_PLACEHOLDER_TOKEN {rel}:{line}: child script {name} formats text "
                               f"(its line {x.lineno})")

    if "PROTOCOL_CHANNEL_DISCIPLINE" in rules and own_process:
        for name, line, inner in scripts:
            for x in ast.walk(inner):
                if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "sys" \
                        and x.attr == "stdout":
                    out.append(f"PROTOCOL_CHANNEL_DISCIPLINE {rel}:{line}: child script {name} uses sys.stdout "
                               f"(its line {x.lineno}); the subject owns it")
                elif isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == "print" \
                        and not any(k.arg == "file" for k in x.keywords):
                    out.append(f"PROTOCOL_CHANNEL_DISCIPLINE {rel}:{line}: child script {name} prints to stdout "
                               f"(its line {x.lineno})")
    return out


# --------------------------------------------------------------------------------------- catalog closure

def _entry_facts(e) -> dict:
    return {"probe_id": e.probe_id, "probe_digest": e.probe_digest, "subject_kind": e.subject_kind.value,
            "classes": list(e.classes), "module": e.module, "fixture_root": e.fixture_root, "active": e.active,
            "cycle": e.cycle, "subject_process": e.subject_process, "stimulus_shape": e.stimulus_shape,
            "metadata_id": e.metadata.probe_id, "metadata_digest": e.metadata.probe_digest}


def _module_facts(root: pathlib.Path) -> dict[str, dict]:
    out = {}
    for p in sorted((root / PROBE_DIR).glob("*.py")):
        if p.name in NOT_PROBES:
            continue
        rel = f"{PROBE_DIR}/{p.name}"
        try:
            mod = importlib.import_module(f"aisef2.probe.{p.stem}")
            meta = mod.METADATA
            out[rel] = {"probe_id": mod.PROBE_ID, "digest": mod.DIGEST, "classes": list(mod.CLASSES),
                        "metadata_id": meta.probe_id, "metadata_digest": meta.probe_digest}
        except (ImportError, AttributeError) as e:
            out[rel] = {"error": f"{type(e).__name__}: {e}"}
    return out


def _fixtures_present(root: pathlib.Path, entries: list[dict]) -> set[str]:
    return {f"{e['fixture_root']}/{c}/{side}" for e in entries for c in e["classes"] for side in ("positive", "negative")
            if (root / FIXTURES_REL / e["fixture_root"] / c / side / "request.json").is_file()}


def closure_problems(entries: list[dict], modules: dict[str, dict], fixtures: set[str], frozen: dict) -> list[str]:
    """Pure: the closure of a catalog over the probe modules, their calibration fixtures and the frozen Cycle-1
    identity. `entries` and `modules` are plain facts (see `_entry_facts`, `_module_facts`)."""
    out = []
    by_module: dict[str, list[dict]] = {}
    for e in entries:
        by_module.setdefault(e["module"], []).append(e)
    for rel, facts in sorted(modules.items()):
        if "error" in facts:
            out.append(f"PROBE_CATALOG_CLOSURE {rel}: not a probe module ({facts['error']})")
            continue
        if rel not in by_module:
            out.append(f"PROBE_CATALOG_CLOSURE {rel}: probe module not registered in aisef2/probe/catalog.py")
    seen: set[tuple[str, str]] = set()
    for e in entries:
        key = (e["probe_id"], e["probe_digest"])
        if key in seen:
            out.append(f"PROBE_CATALOG_CLOSURE {e['probe_id']}: registered twice at {e['probe_digest'][:12]}")
        seen.add(key)
        facts = modules.get(e["module"])
        if facts is None:
            out.append(f"PROBE_CATALOG_CLOSURE {e['probe_id']}: module {e['module']} does not exist")
        elif "error" not in facts:
            for name, want, have in (("id", e["probe_id"], facts["probe_id"]),
                                     ("digest", e["probe_digest"], facts["digest"]),
                                     ("classes", e["classes"], facts["classes"]),
                                     ("metadata id", e["metadata_id"], facts["metadata_id"]),
                                     ("metadata digest", e["metadata_digest"], facts["metadata_digest"])):
                if want != have:
                    out.append(f"PROBE_CATALOG_CLOSURE {e['probe_id']}: catalog {name} {want!r} != module {have!r}")
        for c in e["classes"]:
            for side in ("positive", "negative"):
                if f"{e['fixture_root']}/{c}/{side}" not in fixtures:
                    out.append(f"PROBE_CATALOG_CLOSURE {e['probe_id']}: class {c} has no {side} calibration fixture "
                               f"({FIXTURES_REL}/{e['fixture_root']}/{c}/{side}/request.json)")
        if e["cycle"] == 1 and (e["probe_id"], e["probe_digest"]) != (frozen.get("id"), frozen.get("digest")):
            out.append(f"PROBE_CATALOG_CLOSURE {e['probe_id']}: a Cycle-1 entry carries {e['probe_digest'][:12]}, the "
                       f"freeze manifest inherits {str(frozen.get('digest'))[:12]}")
    for kind in sorted({e["subject_kind"] for e in entries}):
        active = [e["probe_id"] for e in entries if e["active"] and e["subject_kind"] == kind]
        if len(active) != 1:
            out.append(f"PROBE_CATALOG_CLOSURE {kind}: {len(active)} active probes; exactly one compiles (F4)")
    return out


def _frozen(root: pathlib.Path) -> dict:
    import json
    path = root / FREEZE_REL
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("cycle1", {}).get("probe", {})


def catalog_check(root: pathlib.Path = ROOT) -> list[str]:
    from aisef2.probe import catalog
    entries = [_entry_facts(e) for e in catalog.CATALOG]
    problems = [f"PROBE_CATALOG_CLOSURE {p}" for p in catalog.problems_of(catalog.CATALOG)]
    frozen = _frozen(root)
    if not frozen:
        problems.append(f"PROBE_CATALOG_CLOSURE {FREEZE_REL} is missing or names no Cycle-1 probe")
    return problems + closure_problems(entries, _module_facts(root), _fixtures_present(root, entries), frozen)


# --------------------------------------------------------------------------------------- the checker

def check(root: pathlib.Path = ROOT, rules: tuple[str, ...] = RULES) -> list[str]:
    out = catalog_check(root) if "PROBE_CATALOG_CLOSURE" in rules else []
    source_rules = tuple(r for r in rules if r in SOURCE_RULES)
    if source_rules:
        from aisef2.probe import catalog
        for p in sorted((root / PROBE_DIR).glob("*.py")):
            if p.name == "__init__.py":
                continue
            rel = f"{PROBE_DIR}/{p.name}"
            e = catalog.entry_for(rel)
            facts = {"subject_process": e.subject_process, "stimulus_shape": e.stimulus_shape} if e else None
            out += violations(rel, p.read_text(encoding="utf-8"), source_rules, facts)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rules = tuple(a for a in argv if a in RULES) or RULES
    problems = check(ROOT, rules)
    for p in problems:
        print(f"FAIL  {p}")
    print(f"probe static checks: {'FAIL' if problems else 'PASS'} ({len(rules)} rules)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
