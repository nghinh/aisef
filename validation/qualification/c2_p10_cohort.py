"""C2-P10 / WP-2.10.1 — the evidence record of the evaluation-cohort machinery (RFC §28-§30, §33 trigger authorized as
machinery only by the owner ruling of 2026-09-30).

The record re-derives from the tree, so `--check` recomputes it and compares:

    sources       sha256 (LF) of every module of the machinery, its checker, its tests and this builder
    machinery     the states and the one way, the typed refusals, the preregistration schema and frozen inputs
    adversarial   every required adversarial case, run in process on synthetic preregistrations, with the refusal seen
    ledgerlock    the DEVELOPMENT_REGRESSION entry and its binding to the frozen files (RFC §30)
    census        the tree holds no preregistration and no cohort: cohort count = 0
    confinement   no module outside the allowed set imports aisef2.cohort; the machinery imports only its boundary
    tests         the kill-test module, run (tests run, OK)
    mutation      the C2-P10 summary of closure-evidence/v2/cycle2/P10-MUTATION.json, validated by mutation.py

    python -P validation/qualification/c2_p10_cohort.py --write   # refused unless every case holds
    python -P validation/qualification/c2_p10_cohort.py --check
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.cohort import lifecycle as L  # noqa: E402
from aisef2.cohort import preregistration as P  # noqa: E402
from aisef2.cohort.lifecycle import CohortState as S  # noqa: E402
from aisef2.cohort.preregistration import CohortRefused  # noqa: E402
from tests.v2 import test_c2_p10_cohort as T  # noqa: E402  — the synthetic preregistrations of the kill tests

OUT_REL = "closure-evidence/v2/cycle2/P10-COHORT-MACHINERY.json"
MUTATION_REL = "closure-evidence/v2/cycle2/P10-MUTATION.json"
BASE = {"commit": "9bd16fa9c578bb91a0a6c0047d2ceb6e6ab3b414", "aisef2_tree": "37bf6457f350dd720a2214f04f3896c554ad0904",
        "note": "the C2-P6 closure (QP-2.6 requalified GREEN on candidate 37dc0dc, R3)"}
SOURCES = ("aisef2/cohort/__init__.py", "aisef2/cohort/preregistration.py", "aisef2/cohort/lifecycle.py",
           "validation/v2/cohort_static_checks.py", "tests/v2/test_c2_p10_cohort.py",
           "tests/v2/test_c2_p10_cohort_static.py", "validation/qualification/c2_p10_cohort.py",
           *(f"tests/v2/fixtures/known_bad/{n}.json" for n in ("cohort_confined", "cohort_boundary",
                                                               "development_regression_bound", "no_cohort_record")))
KILL_TESTS = "tests.v2.test_c2_p10_cohort"
VERDICT = "machinery qualified; cohort count = 0"


def _load(name: str, path: pathlib.Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cs = _load("aisef_v2_cohort_static_checks", ROOT / "validation" / "v2" / "cohort_static_checks.py")
mu = _load("aisef_v2_mutation", ROOT / "validation" / "v2" / "mutation.py")


def _sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _seen(fn, *args, **kwargs) -> str:
    try:
        out = fn(*args, **kwargs)
    except CohortRefused as e:
        return f"REFUSED {e.code.value}: {e.why}"
    if isinstance(out, L.EvaluationCohort):
        return f"{out.state.value}" + (f": {out.exposed_reason}" if out.exposed_reason else "")
    return "ACCEPTED"


def adversarial() -> list[dict]:
    """The required adversarial cases (manifest WP-2.10.1, owner brief), each on synthetic preregistrations."""
    dev = L.advance(L.observe_inputs(T.evaluating(1, done=3, read=10.0), {}), S.DEVELOPMENT)
    fresh = {**T.prereg(1), "prompts": {"sha256": "9" * 64}}
    read = T.evaluating(2, done=3, read=20.0)
    unread = T.evaluating(3, done=2)
    stale = L.observe_inputs(unread, {**unread.frozen_inputs, "prompts": "0" * 64})
    keep_req = T.ledgerlock(plan_baseline=T.prereg(9)["workload"]["plan_baseline"],
                            plan_hash=T.prereg(9)["workload"]["plan_hash"])
    keep_base = T.ledgerlock(plan_hash=T.prereg(9)["workload"]["plan_hash"])
    keep_base["requirements"]["sha256"] = T.prereg(9)["requirements"]["sha256"]
    keep_hash = T.ledgerlock(plan_baseline=T.prereg(9)["workload"]["plan_baseline"])
    keep_hash["requirements"]["sha256"] = T.prereg(9)["requirements"]["sha256"]
    twin = T.prereg(5)
    twin["workload"]["plan_hash"] = T.prereg(4)["workload"]["plan_hash"]
    a = T.evaluating(4, done=3, read=1.0)
    b = L.read_results(L.record_run(L.record_run(L.record_run(L.advance(L.seal(twin), S.EVALUATING), "r1"), "r2"),
                                    "r3"), 2.0)
    cases = [
        ("COH-ADV-1", "a DEVELOPMENT workload cannot seal (a fresh preregistration of a workload whose cohort is "
         "DEVELOPMENT)", "REFUSED WORKLOAD_DEMOTED", _seen(L.seal, fresh, [dev])),
        ("COH-ADV-2", "DEVELOPMENT -> SEALED", "REFUSED NOT_FORWARD", _seen(L.advance, dev, S.SEALED)),
        ("COH-ADV-3", "DEVELOPMENT -> HOLDOUT (a holdout is a sealed cohort by another name)", "REFUSED NOT_FORWARD",
         _seen(L.advance, dev, "HOLDOUT")),
        ("COH-ADV-4", "a frozen-input change after results_read_at demotes", "EXPOSED",
         _seen(L.observe_inputs, read, {**read.frozen_inputs, "execution_profile": "0" * 64})),
        ("COH-ADV-5", "a frozen-input change during EVALUATING, results unread, invalidates the completed runs",
         "EVALUATING", f"{stale.state.value}: invalidated {list(stale.invalidated_runs)}, stale {list(stale.stale_inputs)}"),
        ("COH-ADV-6", "after it, the cohort requires a fresh preregistration", "REFUSED PREREGISTRATION_STALE",
         _seen(L.record_run, stale, "r3")),
        ("COH-ADV-7", "an OPAQUE aggregate (aggregate_min_grade OPAQUE) bars sealing", "REFUSED OPAQUE_PROFILE",
         _seen(L.seal, T.prereg(6, grade="OPAQUE"))),
        ("COH-ADV-8", "LedgerLock, by its full frozen identity, under a fresh name", "REFUSED DEVELOPMENT_REGRESSION",
         _seen(L.seal, T.ledgerlock())),
        ("COH-ADV-9", "LedgerLock by its requirements sha256 alone", "REFUSED DEVELOPMENT_REGRESSION",
         _seen(L.seal, keep_req)),
        ("COH-ADV-10", "LedgerLock by its plan baseline alone", "REFUSED DEVELOPMENT_REGRESSION",
         _seen(L.seal, keep_base)),
        ("COH-ADV-11", "LedgerLock by its plan hash alone", "REFUSED DEVELOPMENT_REGRESSION", _seen(L.seal, keep_hash)),
        ("COH-ADV-12", "LedgerLock constructed directly as a SEALED cohort (no path skips the bar)",
         "REFUSED DEVELOPMENT_REGRESSION", _seen(L.EvaluationCohort, T.ledgerlock(), S.SEALED)),
        ("COH-ADV-13", "a generalization from one sealed workload", "REFUSED GENERALIZATION_REFUSED",
         _seen(L.generalization, [a])),
        ("COH-ADV-14", "a generalization from two cohorts of one workload (same plan hash)",
         "REFUSED GENERALIZATION_REFUSED", _seen(L.generalization, [a, b])),
        ("COH-ADV-15", "a generalization resting on an EXPOSED cohort", "REFUSED GENERALIZATION_REFUSED",
         _seen(L.generalization, [a, L.advance(read, S.EXPOSED, "seen")])),
    ]
    return [{"id": i, "case": c, "expected": e, "observed": o, "holds": o.split(":")[0] == e}
            for i, c, e, o in cases]


def positive() -> dict:
    c = L.seal(T.prereg(1))
    path = [c.state.value]
    for to, reason in ((S.EVALUATING, None), (S.EXPOSED, "tuned against"), (S.DEVELOPMENT, None)):
        c = L.advance(c, to, reason)
        path.append(c.state.value)
    refused = 0
    states = [L.seal(T.prereg(1)), T.evaluating(1), L.advance(T.evaluating(1), S.EXPOSED, "x"), c]
    for x in states:
        for to in [*S, "HOLDOUT"]:
            if L.NEXT.get(x.state) is not to:
                refused += _seen(L.advance, x, to).startswith("REFUSED NOT_FORWARD")
    runs = T.evaluating(1, runs=3, done=3)
    two = L.generalization([T.evaluating(1, runs=3, done=3, read=1.0), T.evaluating(2, runs=2, done=2, read=2.0)])
    return {
        "lifecycle_one_way": {"path": path, "non_successor_moves_refused": refused, "non_successor_moves": 17},
        "repetitions_never_demote": {"runs_recorded": len(runs.runs_completed), "state": runs.state.value,
                                     "exposed_reason": runs.exposed_reason},
        "generalization_statement_shape": {
            "note": "two synthetic in-memory cohorts: the statement states the sample size per workload and in total; "
                    "this is a check of the machinery, not a claim",
            "fields": sorted(two), "per_workload": [w["sample_size"] for w in two["workloads"]],
            "sample_size_total": two["sample_size_total"]},
    }


def tests() -> dict:
    r = subprocess.run([sys.executable, "-m", "unittest", KILL_TESTS], cwd=ROOT, capture_output=True,
                       encoding="utf-8")
    ran = re.search(r"Ran (\d+) tests?", r.stderr)
    return {"module": KILL_TESTS, "tests_run": int(ran.group(1)) if ran else None,
            "result": "OK" if r.returncode == 0 and r.stderr.rstrip().endswith("OK") else "FAIL"}


def mutation() -> dict:
    record = json.loads((ROOT / MUTATION_REL).read_text(encoding="utf-8"))
    targets = record["targets"]
    return {"record": MUTATION_REL, "sha256": _sha(MUTATION_REL), "targets": len(targets),
            "mutants": sum(t.get("mutants", 0) for t in targets), "killed": sum(t.get("killed", 0) for t in targets),
            "survivors": sum(len(t.get("survivors", [])) for t in targets),
            "killed_by_timeout": sum(t.get("killed_by_timeout", 0) for t in targets),
            "problems": mu.problems_of(record, ROOT, "C2-P10")}


def build() -> dict:
    found = cs.census(ROOT, cs._listed(ROOT, "*.json", "*.jsonl"))
    (entry,) = P.DEVELOPMENT_REGRESSION
    return {
        "record": "AISEF V2 — CYCLE-2 C2-P10 / WP-2.10.1 EVALUATION-COHORT MACHINERY",
        "package": "WP-2.10.1", "phase": "C2-P10",
        "authority": "owner ruling 2026-09-30: explicit authorization of the C2-P10 scope declared in the accepted "
                     "manifest (WP-2.10.1, WP-2.10.2) — sealed-cohort machinery only (RFC §33 trigger); no cohort is "
                     "authorized and no workload is selected",
        "base": BASE,
        "sources": {rel: _sha(rel) for rel in SOURCES},
        "machinery": {
            "states": [s.value for s in S], "one_way": {a.value: b.value for a, b in L.NEXT.items()},
            "terminal": "DEVELOPMENT", "refusals": [r.value for r in P.Refusal],
            "preregistration_schema": P.SCHEMA, "frozen_inputs": list(P.FROZEN_INPUTS),
            "workload_identity": list(P.IDENTITY), "min_workloads_for_generalization": L.MIN_WORKLOADS,
            "results_read_at": "the caller's timestamp; the machine reads no clock",
            "event_vocabulary": "none: CohortState and Refusal live in aisef2/cohort and are carried in no event (F1 "
                                "unchanged); no existing aisef2 file was edited",
        },
        "adversarial": adversarial(),
        "positive": positive(),
        "ledgerlock": {"classification": "DEVELOPMENT_REGRESSION, permanently (RFC §30)", "entry": entry,
                       "binding_problems": cs.binding_problems(ROOT, P.DEVELOPMENT_REGRESSION),
                       "identified_by": "requirements sha256, plan baseline, plan hash — any one component; never "
                                        "by a name"},
        "census": {
            "scope": "every *.json and *.jsonl file of the tree, tracked or untracked and not ignored; any object at "
                     f"any depth whose schema is {P.SCHEMA} (every persisted preregistration or cohort carries one)",
            "cohort_records": found, "cohort_count": len(found),
            "statement": "No cohort record exists anywhere in the tree: no preregistration and no evaluation cohort. "
                         "closure-evidence/cohorts/ (C-1, C-1b, C-2) is frozen V1 model-pair bench evidence that "
                         "predates RFC §28, and closure-evidence/v2/P10/LEDGERLOCK-REGRESSION.json is the Cycle-1 "
                         "regression record (cohort_state DEVELOPMENT, generalization_claim NONE); neither is an "
                         "evaluation cohort, and neither was touched.",
        },
        "confinement": {"allowed_importers": list(cs.ALLOWED_IMPORTERS),
                        "allowed_dependencies": list(cs.ALLOWED_DEPENDENCIES),
                        "scope": "every *.py file of the tree, tracked or untracked and not ignored",
                        "violations": cs.check(ROOT, ("COHORT_CONFINED", "COHORT_BOUNDARY"))},
        "tests": tests(),
        "mutation": mutation(),
        "verdict": VERDICT,
        "not_done": ["no cohort sealed, preregistered or recorded", "no workload selected", "no generalization claim",
                     "LedgerLock stays DEVELOPMENT_REGRESSION", "no live provider call (WP-2.10.1 makes none)"],
    }


def problems_of(rec: dict) -> list[str]:
    out = [f"{c['id']} does not hold: expected {c['expected']}, saw {c['observed']}" for c in rec["adversarial"]
           if not c["holds"]]
    pos = rec["positive"]["lifecycle_one_way"]
    if pos["path"] != ["SEALED", "EVALUATING", "EXPOSED", "DEVELOPMENT"] or \
            pos["non_successor_moves_refused"] != pos["non_successor_moves"]:
        out.append(f"the one way does not hold: {pos}")
    out += rec["ledgerlock"]["binding_problems"] + rec["confinement"]["violations"] + rec["mutation"]["problems"]
    if rec["census"]["cohort_count"] != 0:
        out.append(f"cohort count is {rec['census']['cohort_count']}: {rec['census']['cohort_records']}")
    if rec["tests"]["result"] != "OK":
        out.append(f"{KILL_TESTS}: {rec['tests']}")
    if rec["mutation"]["survivors"]:
        out.append(f"{rec['mutation']['survivors']} mutation survivors")
    return out


def render(rec: dict) -> str:
    return json.dumps(rec, indent=1, ensure_ascii=False) + "\n"


def check() -> list[str]:
    rec = build()
    out = problems_of(rec)
    path = ROOT / OUT_REL
    if not path.exists() or path.read_text(encoding="utf-8").replace("\r\n", "\n") != render(rec):
        out.append(f"{OUT_REL} is missing or does not re-derive from the tree")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--write" in argv:
        rec = build()
        problems = problems_of(rec)
        if not problems:
            (ROOT / OUT_REL).write_text(render(rec), encoding="utf-8")
            print(f"wrote {OUT_REL}: {rec['verdict']}")
    else:
        problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print(f"c2_p10_cohort: {'FAIL' if problems else 'PASS'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
