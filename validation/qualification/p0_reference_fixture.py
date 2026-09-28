"""WP-2.0.3 — the LedgerLock reference workload fixture: freeze, materialise, check, run.

Owner authorization "AISEF V2 — CYCLE-2 WP-2.0.3 EXECUTION AUTHORIZATION / REFERENCE LEDGERLOCK WORKLOAD FIXTURE"
(2026-09-28). The fixture lives under tests/v2/fixtures/workloads/ledgerlock-reference/:

    REQUIREMENTS.md          the frozen requirements, byte-identical to the LedgerLock repository's docs/requirements.md
    reference/ledgerlock/    the stdlib-only reference implementation, authored from REQUIREMENTS.md alone
    acceptance.py            the independent acceptance suite: every observation through a fresh subprocess
    MUTANTS.json             the mutant catalog: one exact source change each, target requirement, expected failures
    mutants/<id>/<module>    every mutant, materialised as an ordinary source file (bound by blob)
    REQUIREMENTS-MAP.json    the closed mapping requirement -> reference behaviour -> assertions -> mutants

This module is a harness (validation/qualification, not a Q0 checker):

    --freeze       write P0-REFERENCE-FIXTURE-FREEZE.json before the fixture exists (owner section 3)
    --materialise  apply MUTANTS.json to the reference and write mutants/<id>/<module> (the committed files)
    --check        every committed mutant equals the reference plus exactly its catalogued change; mapping closed
    --run          reference acceptance (twice), every mutant, the vacuous-runner calibration, the static checks;
                   write P0-REFERENCE-FIXTURE.json (refused on any problem)
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FIX_REL = "tests/v2/fixtures/workloads/ledgerlock-reference"
FIX = ROOT / FIX_REL
REF = FIX / "reference"
MUT = FIX / "mutants"
FREEZE_REL = "closure-evidence/v2/cycle2/P0-REFERENCE-FIXTURE-FREEZE.json"
OUT_REL = "closure-evidence/v2/cycle2/P0-REFERENCE-FIXTURE.json"
REQUIREMENTS_SHA = "3a6a99959bbc6cf39c4d4afa9c2de222925fdcaad30aaf3fa2d04ee446597ecc"
REQUIREMENTS_ORIGIN = {"repository": "ledgerlock-aiseftest-run2", "path": "docs/requirements.md",
                       "plan_commit": "136a68dcdc3f416b2a76c561a7df12d1282ad4d5",
                       "v1_freeze": "closure-evidence/hardening/W1-PLAN-V2.1-FREEZE.json"}
REQUIREMENTS_SRC = pathlib.Path("/Users/nghinh/Downloads/projects/ledgerlock-aiseftest-run2/docs/requirements.md")
REFERENCE_MODULES = ("ledgerlock/__init__.py", "ledgerlock/__main__.py", "ledgerlock/ledger.py", "ledgerlock/cli.py")
#: R-10: the modules the frozen requirements allow the reference to import (plus __future__).
ALLOWED_IMPORTS = {"hashlib", "json", "os", "sys", "pathlib", "tempfile", "argparse", "unittest", "typing",
                   "unicodedata", "uuid", "__future__", "ledgerlock"}   # the package's own modules
FORBIDDEN_NAMES = ("aisef", "aisef2", "ledgerlock_aiseftest", "ai-sdlc", "ai_sdlc", "closure-evidence", "_bmad-output")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _norm(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _identity(path: pathlib.Path) -> dict:
    data = _norm(path.read_bytes())
    return {"sha256": _sha(data), "git_blob": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def _load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------- the requirement set

def sections(text: str) -> list[dict]:
    """One row per `##`/`###` heading of the frozen document: stable id R-<n>[.<m>], line range, digest of the
    section's text (heading to the next heading)."""
    import re
    lines = text.split("\n")
    heads = [(i, line) for i, line in enumerate(lines) if re.match(r"^#{2,3} ", line)]
    out = []
    for n, (i, line) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        m = re.match(r"^#{2,3} (\d+(?:\.\d+)?)\.? (.*)$", line)
        body = "\n".join(lines[i:end]).rstrip("\n") + "\n"
        out.append({"id": f"R-{m.group(1)}", "heading": m.group(2), "lines": [i + 1, end],
                    "sha256": _sha(body.encode("utf-8"))})
    return out


#: How this package reads each section (owner section 3: "the exact set of requirements interpreted").
INTERPRETATION = {
    "R-1": "DESCRIPTIVE", "R-2": "DESCRIPTIVE", "R-3": "CONTAINER", "R-4": "CONTAINER",
    "R-3.1": "BEHAVIOUR", "R-3.2": "BEHAVIOUR", "R-3.3": "BEHAVIOUR", "R-3.4": "BEHAVIOUR",
    "R-4.1": "BEHAVIOUR", "R-4.2": "BEHAVIOUR", "R-4.3": "BEHAVIOUR", "R-4.4": "BEHAVIOUR", "R-4.5": "BEHAVIOUR",
    "R-5": "BEHAVIOUR", "R-6": "BEHAVIOUR", "R-7": "BEHAVIOUR", "R-9": "BEHAVIOUR",
    "R-8": "STATIC (durability is asserted on the reference's source: fsync in every write path; not observable "
           "from outside the process)",
    "R-10": "STATIC (allowed imports and the __future__ import, asserted on the source)",
    "R-12": "STATIC (no socket / subprocess / os.system, asserted on the source)",
    "R-13": "STATIC (package layout and the names ledger.py must define)",
    "R-11": "DEVELOPER_TEST_REQUIREMENT (unit tests, coverage, runner agreement: a requirement on the product's own "
            "tests; outside ProductProof by invariant IX and outside this fixture, which measures product behaviour "
            "only — the DECISION-3 domain)",
    "R-14": "MAPPED (items 1-4 and 6 are the assertions named in REQUIREMENTS-MAP.json; item 5 is R-11's coverage "
            "requirement)",
}

#: The plan bound before the fixture exists: assertion ids by requirement, and the mutant catalog as intended.
PLANNED_ASSERTIONS = {
    "R-3.1": ["A-3.1-a"], "R-3.2": ["A-3.2-a", "A-3.2-b"], "R-3.3": ["A-3.3-a", "A-3.3-b", "A-3.3-c", "A-3.3-d", "A-3.3-e"],
    "R-3.4": ["A-3.4-a"], "R-4.1": ["A-4.1-a"], "R-4.2": ["A-4.2-a"], "R-4.3": ["A-4.3-a"], "R-4.4": ["A-4.4-a"],
    "R-4.5": ["A-4.5-a"], "R-5": ["A-5-a", "A-5-b", "A-5-c", "A-5-d"], "R-6": ["A-6-a", "A-6-b"],
    "R-7": ["A-7-a", "A-7-b", "A-7-c"], "R-8": ["A-8-a"],
    "R-9": ["A-9-a", "A-9-b", "A-9-c", "A-9-d", "A-9-e", "A-9-f", "A-9-g", "A-9-h"],
    "R-10": ["A-10-a"], "R-12": ["A-12-a"], "R-13": ["A-13-a"],
}
PLANNED_MUTANTS = [
    ("M-3.1-1", "R-3.1", "ledger.py", "key normalisation returns the raw key (NFC dropped)", ["A-3.1-a"]),
    ("M-3.2-1", "R-3.2", "ledger.py", "the line hash omits the '|' separator", ["A-3.2-a"]),
    ("M-3.2-2", "R-3.2", "ledger.py", "every line's prev_hash is GENESIS (no chaining)", ["A-3.2-a"]),
    ("M-3.3-1", "R-3.3", "ledger.py", "verify never compares the recomputed hash with the stored one", ["A-3.3-a", "A-3.3-b", "A-3.3-c"]),
    ("M-3.3-2", "R-3.3", "ledger.py", "verify never checks prev_hash linkage", ["A-3.3-e"]),
    ("M-3.3-3", "R-3.3", "ledger.py", "first_bad_index is off by one", ["A-3.3-a", "A-3.3-c", "A-3.3-e"]),
    ("M-3.4-1", "R-3.4", "ledger.py", "verify trusts the instance's cached line count and skips the chain", ["A-3.4-a"]),
    ("M-4.1-1", "R-4.1", "ledger.py", "an empty rid is accepted", ["A-4.1-a"]),
    ("M-4.2-1", "R-4.2", "ledger.py", "a replayed rid appends a new line", ["A-4.2-a"]),
    ("M-4.3-1", "R-4.3", "ledger.py", "the conflict check is removed", ["A-4.3-a"]),
    ("M-4.3-2", "R-4.3", "ledger.py", "the line is written before the conflict is raised", ["A-4.3-a"]),
    ("M-4.4-1", "R-4.4", "ledger.py", "a tombstone does not block a different rid", ["A-4.4-a"]),
    ("M-4.5-1", "R-4.5", "ledger.py", "a different op with a different rid does not conflict", ["A-4.5-a"]),
    ("M-5-1", "R-5", "ledger.py", "a batch commits line by line: a later conflict leaves earlier lines", ["A-5-b"]),
    ("M-5-2", "R-5", "ledger.py", "a replay inside a batch appends a second line", ["A-5-c"]),
    ("M-6-1", "R-6", "ledger.py", "the snapshot is in insertion order, not byte order", ["A-6-a"]),
    ("M-6-2", "R-6", "ledger.py", "the snapshot includes tombstoned keys", ["A-6-a"]),
    ("M-7-1", "R-7", "ledger.py", "repair-tail drops the last line even when the chain is clean", ["A-7-b"]),
    ("M-7-2", "R-7", "ledger.py", "repair-tail repairs instead of refusing mid-chain corruption", ["A-7-c"]),
    ("M-7-3", "R-7", "ledger.py", "repair-tail drops two lines", ["A-7-a"]),
    ("M-8-1", "R-8", "ledger.py", "fsync removed from the append path", ["A-8-a"]),
    ("M-9-1", "R-9", "cli.py", "a conflict exits 5 instead of 4", ["A-9-e"]),
    ("M-9-2", "R-9", "cli.py", "an I/O error exits 1 instead of 3", ["A-9-d"]),
    ("M-9-3", "R-9", "cli.py", "verify exits 0 whatever the verdict", ["A-9-b"]),
]


#: Where the committed catalog departs from the freeze's plan, and why (owner section 3: never silently absorbed).
DEVIATION_NOTES = {
    "M-3.1-1": "planned as 'normalisation returns the raw key'; committed as 'normalises to NFD instead of NFC' — "
               "the raw-key form left the unicodedata import unused (a lint-visible, not a behavioural, difference); "
               "the NFD form is a defect of the same requirement with the same target assertion",
    "M-4.3-2": "planned as 'the line is written before the conflict is raised'; not committed — moving the write is "
               "not a one-line change, and the 'no line appended' half of R-4.3 is measured by A-4.3-a's line count "
               "under M-4.3-1",
    "A-3.3-f": "assertion added beyond the plan: a removed middle line (A-3.3-e) is caught by the hash recomputation "
               "alone, so the prev_hash-equals-previous-hash rule of R-3.3 needed its own observation (a changed "
               "prev_hash field); without it M-3.3-2 was equivalent under the suite and would have been rejected",
    "M-10-1": "added by the owner's C2-P0 correction (2026-09-29): R-10 had no negative witness; a used disallowed "
              "import cannot honestly be one changed line (the import statement and its use), so it is two",
    "M-12-1": "added by the owner's C2-P0 correction (2026-09-29): R-12 had no negative witness",
    "M-13-1": "added by the owner's C2-P0 correction (2026-09-29): R-13 had no negative witness; renaming the "
              "required definition alone would break the package import and hide the layout defect behind an "
              "import failure in every observation, so the package re-export is changed with it (two lines)",
}

#: The record this run supersedes: the pre-correction run at 002fdb7 (kept in history, never rewritten).
SUPERSEDES = {"path": "closure-evidence/v2/cycle2/P0-REFERENCE-FIXTURE.json", "commit": "002fdb773c57a5c247b9ae900cb5ad7aa72bac08",
              "reason": "owner ruling 'CYCLE-2 C2-P0 CORRECTION / WP-2.0.3 COMPLETION DEFECT ONLY': R-10, R-12 and R-13 had "
                        "no negative witness; this run adds M-10-1, M-12-1, M-13-1 and the in-tree harness calibration"}


def identities() -> dict:
    cb = _module("aisef_v2_cycle2_baseline", ROOT / "validation" / "v2" / "cycle2_baseline.py")
    rfc = _load("closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json")
    return {
        "head": _git("rev-parse", "HEAD"),
        "aisef2_tree": _git("rev-parse", "HEAD:aisef2"),
        "cycle2_manifest": {"path": cb.MANIFEST_REL, "sha256": _identity(ROOT / cb.MANIFEST_REL)["sha256"]},
        "cycle2_freeze_manifest": {"path": cb.OUT_REL, "sha256": _identity(ROOT / cb.OUT_REL)["sha256"]},
        "owner_decisions": {"path": cb.DECISIONS_REL, "sha256": _identity(ROOT / cb.DECISIONS_REL)["sha256"]},
        "wp_2_0_1_acceptance": {"path": "closure-evidence/v2/cycle2/WP-2.0.1-ACCEPTANCE.json",
                                "sha256": _identity(ROOT / "closure-evidence/v2/cycle2/WP-2.0.1-ACCEPTANCE.json")["sha256"]},
        "cycle1": {"semantic_candidate": cb.PARENT_COMMIT, "aisef2_tree": cb.PARENT_AISEF2_TREE,
                   "probe": dict(cb.CYCLE1_PROBE)},
        "rfc": {k: rfc.get(k) for k in ("rfc_normative_digest", "freeze_table_digest")},
        "hash_rule": "every sha256 here is over bytes with CRLF normalised to LF; git_blob = sha1 of the blob header and the same bytes",
    }


def _module(name: str, path: pathlib.Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------------------- freeze

def freeze() -> dict:
    src = REQUIREMENTS_SRC.read_bytes()
    if _sha(src) != REQUIREMENTS_SHA:
        raise SystemExit(f"the requirements at {REQUIREMENTS_SRC} are not the frozen document ({_sha(src)[:12]})")
    FIX.mkdir(parents=True, exist_ok=True)
    copy = FIX / "REQUIREMENTS.md"
    copy.write_bytes(src)
    secs = sections(src.decode("utf-8"))
    return {
        "record": "AISEF V2 — WP-2.0.3 REFERENCE FIXTURE FREEZE (bound before the fixture is written)",
        "work_package": "WP-2.0.3",
        "authority": "owner decision 'AISEF V2 — CYCLE-2 WP-2.0.3 EXECUTION AUTHORIZATION / REFERENCE LEDGERLOCK WORKLOAD FIXTURE' (2026-09-28)",
        "parent": identities(),
        "requirements": {"origin": REQUIREMENTS_ORIGIN, "sha256": REQUIREMENTS_SHA,
                         "fixture_copy": f"{FIX_REL}/REQUIREMENTS.md",
                         "sections": secs,
                         "interpretation": INTERPRETATION,
                         "authored_from": "REQUIREMENTS.md alone; nothing copied from AISEF output, the AISEF-generated "
                                          "LedgerLock, a Cycle-1 candidate, a developer agent, a probe implementation "
                                          "or a PLAN-V2.2 proposal"},
        "planned": {"reference_modules": list(REFERENCE_MODULES),
                    "acceptance_harness": f"{FIX_REL}/acceptance.py (digest bound at --run; every observation "
                                          "through a fresh `python -I` subprocess with only the tree root on sys.path)",
                    "assertions": PLANNED_ASSERTIONS,
                    "mutants": [{"id": i, "target": t, "module": m, "change": c, "expect_fail": e}
                                for i, t, m, c, e in PLANNED_MUTANTS],
                    "mutant_count": len(PLANNED_MUTANTS)},
        "rules": ["one mutant, one exact source change, one target requirement; a mutant whose defect necessarily "
                  "reaches other observables records them as consequential, never as a second target",
                  "a mutant is valid only if its target assertion fails and every failing assertion belongs to its "
                  "declared set; an equivalent mutant is removed, not kept",
                  "the acceptance suite observes behaviour through the CLI and the library in fresh subprocesses; "
                  "it never reads a mutant id, a path or a fixture name",
                  "deviations from this plan are recorded in P0-REFERENCE-FIXTURE.json, never silently absorbed"],
    }


# --------------------------------------------------------------------------------------- mutants

def _catalog() -> list[dict]:
    return json.loads((FIX / "MUTANTS.json").read_text(encoding="utf-8"))["mutants"]


MODULES = ("__init__.py", "__main__.py", "ledger.py", "cli.py")


def changes_of(m: dict) -> list[dict]:
    """A mutant's controlled changes: one (module, before, after) in the one-line form, or several under `changes`
    when the defect cannot honestly be one changed line — then `multi_line_rationale` says why."""
    if "changes" in m:
        return [dict(c, id=m["id"]) for c in m["changes"]]
    return [{"id": m["id"], "module": m["module"], "before": m["before"], "after": m["after"]}]


def modules_of(m: dict) -> list[str]:
    return sorted({c["module"] for c in changes_of(m)})


def apply_change(source: str, change: dict) -> str:
    """One exact change of a mutant: `before` (a line, without its newline) occurs exactly once in the module and
    becomes `after` (None deletes the line; a list inserts several lines)."""
    lines = source.split("\n")
    hits = [i for i, line in enumerate(lines) if line == change["before"]]
    if len(hits) != 1:
        raise ValueError(f"{change['id']}: the anchor occurs {len(hits)} times, not once: {change['before']!r}")
    after = change["after"]
    if after is None:
        lines[hits[0]:hits[0] + 1] = []
    elif isinstance(after, list):
        lines[hits[0]:hits[0] + 1] = after
    else:
        lines[hits[0]] = after
    return "\n".join(lines)


def _expected_module(m: dict, module: str) -> str:
    src = (REF / "ledgerlock" / module).read_text(encoding="utf-8")
    for c in changes_of(m):
        if c["module"] == module:
            src = apply_change(src, c)
    return src


def materialise() -> list[str]:
    written = []
    for m in _catalog():
        for module in modules_of(m):
            out = MUT / m["id"] / module
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(_expected_module(m, module), encoding="utf-8")
            written.append(str(out.relative_to(ROOT)))
    return written


def lines_changed(m: dict) -> dict:
    """Per touched module, the lines removed and added between the reference and the committed mutant (difflib)."""
    out = {}
    for module in modules_of(m):
        ref = (REF / "ledgerlock" / module).read_text(encoding="utf-8").split("\n")
        actual = (MUT / m["id"] / module).read_text(encoding="utf-8").split("\n")
        changed = [d for d in difflib.ndiff(ref, actual) if d[:1] in "+-"]
        out[module] = {"removed": sum(1 for d in changed if d.startswith("-")),
                       "added": sum(1 for d in changed if d.startswith("+"))}
    return out


def mutant_problems() -> list[str]:
    """Every committed mutant file equals the reference module plus exactly its catalogued changes (measured by
    difflib, not trusted): one anchor line removed per change, no more lines added than the change declares; a
    mutant with more than one change carries its rationale; ids unique; modules known."""
    out = []
    seen = set()
    for m in _catalog():
        if m["id"] in seen:
            out.append(f"{m['id']}: duplicated id")
        seen.add(m["id"])
        changes = changes_of(m)
        if len(changes) > 1 and not m.get("multi_line_rationale"):
            out.append(f"{m['id']}: {len(changes)} changes without multi_line_rationale")
        for module in modules_of(m):
            if module not in MODULES:
                out.append(f"{m['id']}: unknown module {module}")
                continue
            ref = REF / "ledgerlock" / module
            path = MUT / m["id"] / module
            if not ref.is_file() or not path.is_file():
                out.append(f"{m['id']}: reference module or mutant file missing ({module})")
                continue
            try:
                expected = _expected_module(m, module)
            except ValueError as e:
                out.append(str(e))
                continue
            if path.read_text(encoding="utf-8") != expected:
                out.append(f"{m['id']}: {module} is not the reference plus the catalogued change(s)")
                continue
            mine = [c for c in changes if c["module"] == module]
            allowed_added = sum(len(c["after"]) if isinstance(c["after"], list) else (0 if c["after"] is None else 1)
                                for c in mine)
            counts = lines_changed(m)[module]
            # an insertion keeps its anchor line, so difflib removes nothing for it; a replacement or deletion
            # removes exactly its anchor — never more lines than the declared changes, never more added than declared
            if counts["removed"] > len(mine) or counts["added"] > allowed_added or counts["removed"] + counts["added"] == 0:
                out.append(f"{m['id']}: {module} differs by more than the declared change(s) "
                           f"(removed {counts['removed']}, added {counts['added']})")
        extra = {f for f in (MUT / m["id"]).glob("*.py")} - {MUT / m["id"] / module for module in modules_of(m)} \
            if (MUT / m["id"]).is_dir() else set()
        if extra:
            out.append(f"{m['id']}: uncatalogued files {sorted(p.name for p in extra)}")
    return out


# --------------------------------------------------------------------------------------- static checks

def _imports(tree: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out.add((n.module or "").split(".")[0])
    return out


def stdlib_problems() -> list[str]:
    """R-10 on the reference (the allowed list, and the __future__ import); stdlib-only on the acceptance suite."""
    out = []
    for rel in REFERENCE_MODULES:
        tree = ast.parse((REF / rel).read_text(encoding="utf-8"))
        extra = _imports(tree) - ALLOWED_IMPORTS
        if extra:
            out.append(f"{rel}: imports outside the allowed set: {sorted(extra)}")
        if rel != "ledgerlock/__init__.py" and not any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                                                       for n in tree.body):
            out.append(f"{rel}: no `from __future__ import annotations`")
    extra = _imports(ast.parse((FIX / "acceptance.py").read_text(encoding="utf-8"))) - set(sys.stdlib_module_names)
    if extra:
        out.append(f"acceptance.py: non-stdlib imports {sorted(extra)}")
    return out


def independence_problems() -> list[str]:
    """The reference and the acceptance suite import nothing of AISEF or of the implementation under evaluation and
    name no path outside the fixture; the runtime half (the imported `ledgerlock` resolves inside the tree) is
    measured by acceptance.py itself (A-13-a reports the module file)."""
    out = []
    for path in [*(REF / rel for rel in REFERENCE_MODULES), FIX / "acceptance.py"]:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        bad = {i for i in _imports(tree) if i in ("aisef", "aisef2")}
        if bad:
            out.append(f"{path.name}: imports {sorted(bad)}")
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                for name in FORBIDDEN_NAMES:
                    if name in n.value:
                        out.append(f"{path.relative_to(ROOT)}:{n.lineno}: names {name!r}")
    return out


def mapping_problems() -> list[str]:
    """REQUIREMENTS-MAP.json is closed: every section of the frozen document has exactly one row; every BEHAVIOUR/STATIC
    row names reference locations, assertions and (where declared) mutants that exist; every assertion and mutant is
    reachable from a requirement; digests agree with the fixture copy."""
    out = []
    mp = json.loads((FIX / "REQUIREMENTS-MAP.json").read_text(encoding="utf-8"))
    secs = {s["id"]: s for s in sections((FIX / "REQUIREMENTS.md").read_text(encoding="utf-8"))}
    rows = {r["id"]: r for r in mp["requirements"]}
    if set(rows) != set(secs):
        out.append(f"mapping rows {sorted(set(rows) ^ set(secs))} do not match the document's sections")
    acc = _module("ledgerlock_reference_acceptance", FIX / "acceptance.py")
    assertions = set(acc.ASSERTIONS)
    mutants = {m["id"]: m for m in _catalog()}
    used_a, used_m = set(), set()
    for rid, r in rows.items():
        if rid in secs and r.get("sha256") != secs[rid]["sha256"]:
            out.append(f"{rid}: mapping digest differs from the document")
        if r["kind"] in ("BEHAVIOUR", "STATIC"):
            if not r.get("reference"):
                out.append(f"{rid}: no reference location")
            if not r.get("assertions"):
                out.append(f"{rid}: no acceptance assertion")
            for a in r.get("assertions", []):
                if a not in assertions:
                    out.append(f"{rid}: assertion {a} does not exist")
                used_a.add(a)
            for m in r.get("mutants", []):
                if m not in mutants:
                    out.append(f"{rid}: mutant {m} does not exist")
                elif mutants[m]["target"] != rid:
                    out.append(f"{rid}: mutant {m} targets {mutants[m]['target']}")
                used_m.add(m)
        elif r["kind"] == "MAPPED":
            for a in r.get("assertions", []):
                if a not in assertions:
                    out.append(f"{rid}: assertion {a} does not exist")
        elif r["kind"] not in ("DESCRIPTIVE", "CONTAINER", "DEVELOPER_TEST_REQUIREMENT"):
            out.append(f"{rid}: unknown kind {r['kind']}")
        elif not r.get("reason"):
            out.append(f"{rid}: {r['kind']} without a reason")
    for a in sorted(assertions - used_a):
        out.append(f"assertion {a} is reachable from no requirement")
    for m in sorted(set(mutants) - used_m):
        out.append(f"mutant {m} is reachable from no requirement")
    for m in mutants.values():
        for a in m["expect_fail"] + m.get("consequential", []):
            if a not in assertions:
                out.append(f"{m['id']}: expects {a}, which does not exist")
    return out


# --------------------------------------------------------------------------------------- run

def _tree_with(mutant: dict | None, work: pathlib.Path) -> pathlib.Path:
    tree = work / (mutant["id"] if mutant else "reference")
    shutil.copytree(REF, tree)
    if mutant:
        for module in modules_of(mutant):
            shutil.copy(MUT / mutant["id"] / module, tree / "ledgerlock" / module)
    return tree


def run_matrix(acc, *, workers: int | None = None) -> dict:
    """Reference twice (determinism), every mutant once; per assertion ok/detail. Workers default to half the cores
    (at most 4): every assertion spawns interpreters, and a hosted CI runner needs cycles of its own to stay in
    contact with its server (attempt 1 of b07dbbd lost the Windows runner while this matrix ran with four)."""
    import os
    from concurrent.futures import ThreadPoolExecutor
    if workers is None:
        workers = max(1, min(4, (os.cpu_count() or 2) // 2))
    catalog = _catalog()
    with tempfile.TemporaryDirectory(prefix="ledgerlock-ref-") as t:
        work = pathlib.Path(t)
        trees = {"reference": _tree_with(None, work)}
        for m in catalog:
            trees[m["id"]] = _tree_with(m, work)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs = {name: pool.submit(acc.run, tree) for name, tree in trees.items()}
            second = pool.submit(acc.run, trees["reference"])
            results = {name: job.result() for name, job in jobs.items()}
            results["reference#2"] = second.result()
    return results


def evaluate(results: dict) -> dict:
    """Per mutant: the failing set, whether the target assertions failed, whether every failure is declared."""
    ref = results["reference"]
    out = {"reference_green": all(r["ok"] for r in ref.values()),
           "reference_failures": sorted(a for a, r in ref.items() if not r["ok"]),
           "deterministic": results["reference"] == results["reference#2"],
           "mutants": {}}
    for m in _catalog():
        failing = sorted(a for a, r in results[m["id"]].items() if not r["ok"])
        declared = set(m["expect_fail"]) | set(m.get("consequential", []))
        out["mutants"][m["id"]] = {
            "target": m["target"], "expected_failing": sorted(m["expect_fail"]),
            "consequential_declared": sorted(m.get("consequential", [])),
            "changes": len(changes_of(m)), "lines_changed": lines_changed(m),
            "one_line": len(changes_of(m)) == 1, "multi_line_rationale": m.get("multi_line_rationale"),
            "observed_failing": failing,
            "red_on_target": all(a in failing for a in m["expect_fail"]),
            "undeclared_failures": sorted(set(failing) - declared),
            "valid": bool(failing) and all(a in failing for a in m["expect_fail"]) and not (set(failing) - declared),
            "observed_detail": {a: results[m["id"]][a]["detail"] for a in failing},
        }
    return out


def vacuous_runner_rejected(acc, tree: pathlib.Path) -> bool:
    """Harness calibration: a runner whose every assertion passes cannot qualify anything — it reports no RED for a
    mutant, and that is what the run refuses."""
    original = acc.check
    acc.check = lambda *a, **k: {"ok": True, "detail": "vacuous"}
    try:
        res = acc.run(tree)
    finally:
        acc.check = original
    return all(r["ok"] for r in res.values())   # True: the vacuous runner saw no failure on a mutant -> rejected


def in_tree_resolution_rejected(acc, tree: pathlib.Path, other: pathlib.Path) -> bool:
    """Harness calibration for the in-tree half of A-13-a. Under `python -I` with only the tree on sys.path a product
    tree cannot make `ledgerlock` resolve outside itself, so no product mutant can witness that half; its negative
    witness is the harness importing another tree: `lib` is pointed at `other` while A-13-a evaluates `tree`, and
    the assertion must go RED for that reason (the module file is not inside the tree)."""
    original = acc.lib
    acc.lib = lambda t, code: original(other, code)
    try:
        with tempfile.TemporaryDirectory(prefix="ledgerlock-cal-") as w:
            res = acc.check(tree, "A-13-a", pathlib.Path(w) / "cal")
    finally:
        acc.lib = original
    return res["ok"] is False and "module inside the tree False" in res["detail"]


def run() -> dict:
    acc = _module("ledgerlock_reference_acceptance", FIX / "acceptance.py")
    problems = mutant_problems() + stdlib_problems() + independence_problems() + mapping_problems()
    results = run_matrix(acc)
    ev = evaluate(results)
    if not ev["reference_green"]:
        problems.append(f"reference not GREEN: {ev['reference_failures']}")
    if not ev["deterministic"]:
        problems.append("reference acceptance is not deterministic across two runs")
    for mid, r in ev["mutants"].items():
        if not r["valid"]:
            problems.append(f"{mid}: not RED on its target or fails undeclared assertions: observed {r['observed_failing']}, "
                            f"undeclared {r['undeclared_failures']}")
    with tempfile.TemporaryDirectory(prefix="ledgerlock-cal-") as t:
        first = _catalog()[0]
        vacuous = vacuous_runner_rejected(acc, _tree_with(first, pathlib.Path(t)))
        pristine = _tree_with(None, pathlib.Path(t))
        other = pathlib.Path(t) / "other"
        shutil.copytree(REF, other)
        in_tree = in_tree_resolution_rejected(acc, pristine, other)
    if not vacuous:
        problems.append("the vacuous-runner calibration did not behave as expected")
    if not in_tree:
        problems.append("the in-tree resolution calibration did not behave as expected")
    freeze = _load(FREEZE_REL)
    planned = {m["id"]: m for m in freeze["planned"]["mutants"]}
    actual = {m["id"]: m for m in _catalog()}
    planned_a = {a for ids in freeze["planned"]["assertions"].values() for a in ids}
    deviations = [f"assertion {a} not in the plan" for a in acc.ASSERTIONS if a not in planned_a] + \
                 [f"planned assertion {a} not committed" for a in sorted(planned_a) if a not in acc.ASSERTIONS] + \
                 [f"planned mutant {i} not committed" for i in planned if i not in actual] + \
                 [f"mutant {i} not in the plan" for i in actual if i not in planned] + \
                 [f"{i}: target {actual[i]['target']} != planned {planned[i]['target']}" for i in actual
                  if i in planned and actual[i]["target"] != planned[i]["target"]] + \
                 [f"{i}: {note}" for i, note in DEVIATION_NOTES.items()]
    record = {
        "record": "AISEF V2 — WP-2.0.3 REFERENCE FIXTURE (LedgerLock reference workload, acceptance and mutants)",
        "work_package": "WP-2.0.3",
        "authority": freeze["authority"],
        "freeze": {"path": FREEZE_REL, "sha256": _identity(ROOT / FREEZE_REL)["sha256"], "deviations": deviations},
        "identities": identities(),
        "platform": {"python": sys.version.split()[0], "platform": sys.platform},
        "requirements": {"sha256": REQUIREMENTS_SHA, "fixture_copy_sha256": _sha((FIX / "REQUIREMENTS.md").read_bytes()),
                         "interpretation": INTERPRETATION},
        "fixture": {rel: _identity(FIX / rel) for rel in ("REQUIREMENTS.md", "acceptance.py", "MUTANTS.json", "REQUIREMENTS-MAP.json")}
                   | {f"reference/{rel}": _identity(REF / rel) for rel in REFERENCE_MODULES}
                   | {f"mutants/{m['id']}/{module}": _identity(MUT / m["id"] / module)
                      for m in _catalog() for module in modules_of(m)},
        "requirement_map": json.loads((FIX / "REQUIREMENTS-MAP.json").read_text(encoding="utf-8"))["requirements"],
        "mutant_catalog": _catalog(),
        "static": {"stdlib_only": stdlib_problems() == [], "independence": independence_problems() == [],
                   "one_line_mutants": mutant_problems() == [], "mapping_closed": mapping_problems() == []},
        "reference_acceptance": {"green": ev["reference_green"], "failures": ev["reference_failures"],
                                 "assertions": {a: r["ok"] for a, r in results["reference"].items()},
                                 "deterministic_two_runs": ev["deterministic"]},
        "mutants": ev["mutants"],
        "mutant_count": len(_catalog()),
        "all_mutants_red_on_target": all(r["valid"] for r in ev["mutants"].values()),
        "harness_calibration": {"vacuous_runner_rejected": vacuous,
                                "in_tree_resolution_rejected": in_tree,
                                "rule": "a runner whose every assertion passes reports no RED for a mutant; the run "
                                        "refuses to qualify under it. The in-tree half of A-13-a cannot be violated "
                                        "by a product tree under python -I isolation, so its negative witness is the "
                                        "harness importing another tree, which A-13-a must reject"},
        "supersedes": SUPERSEDES,
        "problems": problems,
        "verdict": "REFERENCE GREEN, EVERY MUTANT RED ON TARGET" if not problems else "NOT QUALIFIED",
    }
    return record


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout


def bind_ci(run_id: int) -> dict:
    """Bind the CI measurements of the implementation commit into the record: every attempt of the run, every job's
    conclusion, the unittest count read from its log when a log exists, and the check-run annotations when it does
    not (a lost runner leaves no log). The run must be of the commit the record names, so the fixture bytes the CI
    measured are the ones the record binds by digest."""
    rec = _load(OUT_REL)
    head = rec["identities"]["head"]
    attempts = int(json.loads(_gh("run", "view", str(run_id), "--json", "attempt"))["attempt"])
    out = {"run": run_id, "commit": head, "attempts": []}
    for n in range(1, attempts + 1):
        jobs = json.loads(_gh("api", f"repos/nghinh/aisef/actions/runs/{run_id}/attempts/{n}/jobs"))["jobs"]
        rows = []
        for j in sorted(jobs, key=lambda x: x["name"]):
            if j["head_sha"] != head:
                raise SystemExit(f"run {run_id} attempt {n} is of {j['head_sha'][:7]}, not {head[:7]}")
            # the job's own log by id through the API: `gh run view --job --log` resolves a re-run job's name to the
            # latest attempt's log, which would credit a lost runner with the retry's test count
            log = subprocess.run(["gh", "api", "--allow-escape-sequences", f"repos/nghinh/aisef/actions/jobs/{j['id']}/logs"],
                                 cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
            import re
            text = log.stdout or ""
            available = log.returncode == 0 and bool(text.strip()) and "<Error>" not in text[:300]
            m = re.search(r"Ran (\d+) tests", text) if available else None
            ann = subprocess.run(["gh", "api", f"repos/nghinh/aisef/check-runs/{j['id']}/annotations"], cwd=ROOT,
                                 capture_output=True, encoding="utf-8", errors="replace")
            annotations = [a.get("message", "") for a in json.loads(ann.stdout or "[]")] if ann.returncode == 0 else []
            failing = sorted(set(re.findall(r"(?:ERROR|FAIL): \S+ \((\S+)\)", text))) if available else []
            rows.append({"job": j["name"], "job_id": j["id"], "conclusion": j["conclusion"], "started_at": j["started_at"],
                         "completed_at": j["completed_at"], "tests_run": int(m.group(1)) if m else None,
                         "log_available": available, "failing_tests": failing, "annotations": annotations})
        out["attempts"].append({"attempt": n, "jobs": rows})
    rec["cross_platform"] = {
        "rule": "the implementation commit's CI runs tests/v2/test_p0_reference_fixture.py, which executes the whole "
                "reference-and-mutant matrix on every platform of the matrix; the fixture bytes it measured are the "
                "ones this record binds by digest (the evidence commit changes evidence files only)",
        "ci": out,
        "platforms": sorted({("windows" if "windows" in r["job"] else "linux") for a in out["attempts"] for r in a["jobs"]
                             if r["job"].startswith("unit")}),
    }
    (ROOT / OUT_REL).write_text(render(rec), encoding="utf-8")
    return rec["cross_platform"]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--bind-ci" in argv:
        cp = bind_ci(int(argv[argv.index("--bind-ci") + 1]))
        for a in cp["ci"]["attempts"]:
            for r in a["jobs"]:
                print(f"attempt {a['attempt']}: {r['job']:32s} {r['conclusion']:8s} tests {r['tests_run']} "
                      f"{'(no log; ' + '; '.join(r['annotations'])[:90] + ')' if not r['log_available'] else ''}")
        print(f"bound CI run {cp['ci']['run']} into {OUT_REL}")
        return 0
    if "--freeze" in argv:
        rec = freeze()
        (ROOT / FREEZE_REL).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / FREEZE_REL).write_text(render(rec), encoding="utf-8")
        print(f"wrote {FREEZE_REL}: {len(rec['requirements']['sections'])} sections, "
              f"{rec['planned']['mutant_count']} planned mutants")
        return 0
    if "--materialise" in argv:
        for w in materialise():
            print("wrote", w)
        return 0
    if "--check" in argv:
        problems = mutant_problems() + stdlib_problems() + independence_problems() + mapping_problems()
        for p in problems:
            print("FAIL ", p)
        print(f"reference fixture static checks: {'FAIL' if problems else 'PASS'}")
        return 1 if problems else 0
    if "--run" in argv:
        rec = run()
        for p in rec["problems"]:
            print("FAIL ", p)
        print(f"reference: {'GREEN' if rec['reference_acceptance']['green'] else 'RED'}; mutants RED on target: "
              f"{sum(r['valid'] for r in rec['mutants'].values())}/{rec['mutant_count']}; "
              f"deterministic: {rec['reference_acceptance']['deterministic_two_runs']}; "
              f"vacuous runner rejected: {rec['harness_calibration']['vacuous_runner_rejected']}")
        if rec["problems"]:
            return 1
        (ROOT / OUT_REL).write_text(render(rec), encoding="utf-8")
        print(f"wrote {OUT_REL}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
