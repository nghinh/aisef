"""The proof model for test evidence (SS-81 family — INV-TDD-NOP-PROOF, INV-T.EXECUTED-EVIDENCE).

One question sits under the nop control, TDD, baseline regression, preservation and the behaviour ledger: *what did
this test run actually show about this test?* The kernel used to answer it five times, each time reading an absent id
as whatever the caller needed — red for the nop control, green for preservation — and a collection error, a missing
third-party package, a skipped test and a test that never ran were all indistinguishable from a result.

Here a test's state in one run is one of an explicit, closed set, read from the run's own record:

    RED_EXECUTED                    ran and failed (not because a package outside the story is missing)
    RED_COLLECTION_BOUND_TO_STORY   could not import or set up because a module / symbol THIS story introduces is
                                    absent — bound to that test's own file, never to unrelated tests
    GREEN_EXECUTED                  ran and passed
    SKIPPED                         collected, not executed
    NOT_COLLECTED                   its file failed to collect for a reason not bound to the story (syntax, …)
    COLLECTION_ABORTED              the runner stopped the session before reaching it
    ENVIRONMENT_UNRUNNABLE          the tool or its environment could not run
    DEPENDENCY_UNRUNNABLE           an import outside the story is missing (third-party, not installed)
    MALFORMED_EVIDENCE              the record cannot be read (no names, output truncated before its summary)
    ABSENT                          the run completed and this test is simply not in it

Only the first two prove red; only GREEN_EXECUTED is green. Every other state is "no evidence", which can never pass
a control and can never keep a behaviour verified.
"""
from __future__ import annotations

import posixpath
from enum import Enum

from .acceptance import ac_code, coverage

MANIFESTS = ("package.json", "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "cargo.toml", "go.mod",
             "pom.xml", "build.gradle", "gemfile", "composer.json")
#: Where a Python import resolves from in a project: its root, or a `src/` layout. Anchoring here is what keeps a
#: missing third-party `yaml` from matching a story file `config/yaml.py` (owner regression 8).
IMPORT_ROOTS = ("", "src/")
_JS_EXT = (".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx")


class Proof(str, Enum):
    RED_EXECUTED = "RED_EXECUTED"
    RED_COLLECTION_BOUND_TO_STORY = "RED_COLLECTION_BOUND_TO_STORY"
    GREEN_EXECUTED = "GREEN_EXECUTED"
    SKIPPED = "SKIPPED"
    NOT_COLLECTED = "NOT_COLLECTED"
    COLLECTION_ABORTED = "COLLECTION_ABORTED"
    ENVIRONMENT_UNRUNNABLE = "ENVIRONMENT_UNRUNNABLE"
    DEPENDENCY_UNRUNNABLE = "DEPENDENCY_UNRUNNABLE"
    MALFORMED_EVIDENCE = "MALFORMED_EVIDENCE"
    ABSENT = "ABSENT"


PROVES_RED = frozenset({Proof.RED_EXECUTED, Proof.RED_COLLECTION_BOUND_TO_STORY})


# ------------------------------------------------------------------ executed-evidence views of one run's record

def not_green(detail: dict) -> set[str]:
    """Ids that did not execute and pass: failed, errored, skipped. The single definition every consumer uses."""
    return {str(t) for k in ("failed_ids", "errored_ids", "skipped_ids") for t in (detail.get(k) or [])}


def executed_green(detail: dict) -> set[str]:
    """Ids the run executed and passed — the only green there is."""
    bad = not_green(detail)
    return {str(t) for t in (detail.get("test_ids") or []) if str(t) not in bad}


def aborted(detail: dict) -> bool:
    """Did the runner stop the whole session at collection? Records written before the proof model carry no flag, only
    the output's tail — read there, so older evidence cannot slip past as a complete run."""
    if "collection_aborted" in detail:
        return bool(detail["collection_aborted"])
    from ..harness.testlog import _PYTEST_ABORT
    return bool(_PYTEST_ABORT.search(str(detail.get("tail") or "")))


def complete_observation(detail: dict) -> tuple[bool, str]:
    """Did this run observe every test it was given? An aborted collection or an unrunnable run did not."""
    if aborted(detail):
        return False, "the runner stopped the session at collection — tests in files that did collect never ran"
    if detail.get("unrunnable"):
        return False, f"the run did not execute ({detail['unrunnable']})"
    if not detail.get("test_format"):
        return False, str(detail.get("test_note") or "the runner's output carries no test names")
    return True, ""


# ------------------------------------------------------------------ binding an import failure to the story (SS-82)

def story_file_for(missing: str, story_files, *, importer: str = "", package_dir: bool = True) -> str:
    """The story file a missing import names, or "". SS-82: a package root maps to its `__init__.py`, and a Python
    module is matched only at an import root — so `ledgerlock` finds `ledgerlock/__init__.py`, while a third-party
    `yaml` never finds `config/yaml.py`. A JS target is resolved relative to the file that imported it.
    `package_dir`: also accept any file under the package's directory — right for a module the parent lacks entirely
    (the story brings the package in), wrong for a symbol missing from a module that exists."""
    files = {str(f).replace("\\", "/") for f in story_files}
    if not missing:
        return ""
    m = missing.replace("\\", "/")
    if "/" in m or m.startswith(".") or m.endswith(_JS_EXT):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), m)) if m.startswith(".") and importer else m
        base = base.lstrip("/")
        stem = base[: -len(posixpath.splitext(base)[1])] if base.endswith(_JS_EXT) else base
        for cand in (base, *(stem + e for e in _JS_EXT), *(stem + "/index" + e for e in _JS_EXT)):
            if cand in files:
                return cand
        return ""
    path = m.replace(".", "/")
    for root in IMPORT_ROOTS:
        for cand in (f"{root}{path}.py", f"{root}{path}/__init__.py"):
            if cand in files:
                return cand
        pkg = f"{root}{path}/"
        under = sorted(f for f in files if f.startswith(pkg) and f.endswith(".py")) if package_dir else []
        if under:                          # a package directory the story brings in wholesale (namespace package)
            return under[0]
    return ""


def bound(err: dict, story_files, added) -> tuple[bool, str]:
    """Is this import failure caused by something THIS story introduces? (story file, or "" with the reason)."""
    kind, mod = err.get("error", ""), str(err.get("missing_module") or "")
    if kind not in ("module_not_found", "import_name") or not mod:
        return False, ""
    # A module the parent lacks must be one the story ADDS; a symbol the parent lacks must come from that module's
    # own file, which the story CHANGES — or be a submodule of it the story ADDS (`from pkg import store`). Another
    # file somewhere under the package is package matching, never proof (owner decision 2026-09-18, section 6).
    new = added if added is not None else story_files
    if kind == "module_not_found":
        f = story_file_for(mod, new, importer=str(err.get("importer") or ""))
        return bool(f), f
    name = str(err.get("missing_name") or "")
    f = story_file_for(mod, story_files, package_dir=False) or (story_file_for(f"{mod}.{name}", new) if name else "")
    return bool(f), f


# ------------------------------------------------------------------ one test's state in one run

def files_of(tests, story_id: str, n: int, ac_code_files: dict | None) -> dict[str, list[str]]:
    """Which story test file declares each test. A pytest id names it (`file::test`); a node/vitest id is a title,
    so the file comes from the harness's scan of the story's test files for each criterion code."""
    ac_code_files = ac_code_files or {}
    out: dict[str, list[str]] = {}
    by_code = coverage(story_id, n, [str(t) for t in tests]) if n > 0 else {}
    for t in tests:
        t = str(t)
        if "::" in t:
            out[t] = [t.split("::", 1)[0]]
            continue
        codes = [ac_code(story_id, i) for i, ts in by_code.items() if t in ts]
        out[t] = sorted({f for c in codes for f in (ac_code_files.get(c) or [])})
    return out


def _collection_error_for(tid: str, detail: dict, files: list[str]) -> dict | None:
    for e in detail.get("collection_errors") or []:
        if e.get("file") in files:
            return e
        mod = str(e.get("module") or "")
        if mod and "::" not in tid and tid.startswith(mod + "."):     # unittest: dotted id under the failed module
            return e
    return None


def classify(detail: dict, tests, story_files, *, added=None, files: dict | None = None) -> dict[str, tuple[Proof, str]]:
    """State of each of `tests` in the run recorded by `detail` — (Proof, why). Pure: no filesystem, no clock.

    `story_files`: the story's non-test changed files. `added`: those absent at the parent (the nop records them;
    None = unknown, and then `story_files` stands in). `files`: test id -> the story test file(s) declaring it
    (`files_of`); a pytest id carries its own."""
    files = files or {}
    story_files = [f for f in (story_files or [])]
    passed = executed_green(detail)
    failed = {str(t) for t in detail.get("failed_ids") or []}
    errored = {str(t) for t in detail.get("errored_ids") or []}
    skipped = {str(t) for t in detail.get("skipped_ids") or []}
    fimp = detail.get("failure_imports") or {}
    unrun = str(detail.get("unrunnable") or "")
    out: dict[str, tuple[Proof, str]] = {}
    for t in tests:
        t = str(t)
        imp = fimp.get(t)
        if t in passed:
            out[t] = (Proof.GREEN_EXECUTED, "ran and passed")
            continue
        if t in errored or t in failed:
            if imp:
                ok, f = bound({"error": "module_not_found" if not imp.get("missing_name") else "import_name", **imp}, story_files, added)
                if ok:
                    out[t] = (Proof.RED_COLLECTION_BOUND_TO_STORY if t in errored else Proof.RED_EXECUTED,
                              f"cannot run without {f}, which this story introduces")
                else:
                    out[t] = (Proof.DEPENDENCY_UNRUNNABLE, f"needs {imp.get('missing_module')}, which is not part of this story")
            elif t in errored:
                out[t] = (Proof.NOT_COLLECTED, "errored before its body ran, for a reason not bound to the story")
            else:
                out[t] = (Proof.RED_EXECUTED, "ran and failed")
            continue
        if t in skipped:
            out[t] = (Proof.SKIPPED, "collected, not executed")
            continue
        err = _collection_error_for(t, detail, files.get(t) or ([t.split("::", 1)[0]] if "::" in t else []))
        if err is not None:
            ok, f = bound(err, story_files, added)
            if ok:
                what = err.get("missing_name") and f"`{err['missing_name']}` from {err['missing_module']}" or err.get("missing_module")
                out[t] = (Proof.RED_COLLECTION_BOUND_TO_STORY, f"its file {err.get('file')} cannot import {what} — {f} is this story's")
            elif err.get("error") in ("module_not_found", "import_name"):
                out[t] = (Proof.DEPENDENCY_UNRUNNABLE, f"its file {err.get('file')} needs {err.get('missing_module')}, which is not part of this story")
            else:
                out[t] = (Proof.NOT_COLLECTED, f"its file {err.get('file')} failed to collect ({err.get('error') or 'unknown error'})")
            continue
        if aborted(detail):
            out[t] = (Proof.COLLECTION_ABORTED, "the session stopped at collection before reaching it")
            continue
        if unrun:
            if "no project manifest" in unrun and any(posixpath.basename(f).lower() in MANIFESTS for f in (added if added is not None else [])):
                out[t] = (Proof.RED_COLLECTION_BOUND_TO_STORY, "the parent has no project at all — this story creates its manifest")
            elif "dependencies are not installed" in unrun:
                out[t] = (Proof.DEPENDENCY_UNRUNNABLE, unrun)
            else:
                out[t] = (Proof.ENVIRONMENT_UNRUNNABLE, unrun)
            continue
        if not detail.get("test_format") or detail.get("output_complete") is False:
            out[t] = (Proof.MALFORMED_EVIDENCE, str(detail.get("test_note") or "the runner's output cannot be read completely"))
            continue
        out[t] = (Proof.ABSENT, "the run completed without it")
    return out


def run_proves_red(detail: dict, tests, story_files, **kw) -> bool:
    """TDD's red: this run shows at least one of the story's tests red for a reason the story's code decides."""
    return any(p in PROVES_RED for p, _ in classify(detail, tests, story_files, **kw).values())


def summarize(states: dict[str, tuple[Proof, str]], story_id: str, n: int) -> dict:
    """Per acceptance criterion: each of its tests' states, and whether every one of them proves red."""
    by_code = coverage(story_id, n, list(states)) if n > 0 else {}
    per: dict[str, dict] = {}
    for i, ts in by_code.items():
        a = per.setdefault(ac_code(story_id, i), {"tests": {}, "proven": bool(ts)})
        for t in ts:
            p, why = states[t]
            a["tests"][t] = {"state": p.value, "why": why}
            a["proven"] = a["proven"] and p in PROVES_RED
    return per
