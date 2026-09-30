"""WP-2.5.2 (C2-P5) — SpecFalsifiabilityEvidence for every spec of the LedgerLock PLAN-V2.2 proposal, over the WP-2.0.3
reference fixture (RFC §9.1.2, §27): closure-evidence/v2/cycle2/P5-FALSIFIABILITY.json.

    python -P validation/qualification/p5_falsifiability.py --run

Every spec the authoring aid compiles (validation/qualification/p10_contracts.py) is run by its catalog probe, at the
fixture revision, against the frozen reference tree. A spec the reference SATISFIES is then run against each of the 26
materialised mutants (c2_effect_calibration.build_tree: the reference plus exactly the mutant's declared change, checked
byte-identical to the committed blob); each mutant it REFUTES is a SpecFalsifiabilityEvidence
(`controlled_product_mutation`), validated by the frozen `falsifiability_problems`. What is reported, never hidden:

* a spec the reference does not satisfy (REFERENCE_NOT_SATISFIED) — no mutant can show contrast, so none is run; the
  reference's observation (kind, verdict, detail) is recorded, from a second, diagnostic observation of the same spec;
* a mutant designed for the spec's requirement (FR -> reference section, `FR_SECTIONS`) that the spec does not refute
  (`unrefuted_designed`);
* a spec whose reference is satisfied but which refutes no mutant at all (NOT_QUALIFIED).

The reference is the requirements' implementation, not PLAN-V2.1's: it does not define `ledgerlock.format` or
`ledgerlock.store`, and it fixes interface details the plan fixes differently (the mutation API, verify's return, the
CLI's stdout and stderr). Those differences decide REFERENCE_NOT_SATISFIED; they are the plan's commitments beyond the
requirements, reported per spec. The record is a measurement: nothing here approves, admits or applies the proposal.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import platform
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_REL = "closure-evidence/v2/cycle2/P5-FALSIFIABILITY.json"
PACKAGE = "WP-2.5.2"
MECHANISM = "controlled_product_mutation"
FIX_REL = "tests/v2/fixtures/workloads/ledgerlock-reference"
#: the package's tests, run under the owned-process gate (validation/v2/owned_run.py) as the lanes' builders do
#: (the Record case reads the record this run writes, so it runs in the suite, not here)
TEST_MODULES = ("tests.v2.test_p5_falsifiability.Falsifiability", "tests.v2.test_p5_plan_v22_proposal")
#: the PLAN-V2.1 requirement (FR) -> the reference fixture's requirement sections it names (REQUIREMENTS-MAP.json)
FR_SECTIONS = {"FR-1": ("R-3.1",), "FR-2": ("R-3.2",), "FR-3": ("R-4.1", "R-4.2"), "FR-4": ("R-4.3", "R-4.5"),
               "FR-5": ("R-4.4",), "FR-6": ("R-3.3",), "FR-7": ("R-3.4",), "FR-8": ("R-5",), "FR-9": ("R-6",),
               "FR-10": ("R-7",), "FR-11": ("R-9",), "FR-12": ("R-9",), "FR-13": ("R-8",),
               "FR-14": ("R-10", "R-12", "R-13")}


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _aid():
    return _load("aisef_v2_p10_contracts", "validation/qualification/p10_contracts.py")


def _trees():
    return _load("aisef_v2_c2_effect_calibration", "validation/qualification/c2_effect_calibration.py")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file(rel: str) -> dict:
    return {"path": rel, "sha256": _sha((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))}


def _probe(probe_id: str):
    from aisef2.probe import catalog
    return next(e for e in catalog.CATALOG if e.probe_id == probe_id).factory()


def observe(spec, tree: pathlib.Path):
    """The spec run by its catalog probe at the fixture revision, read through its bound record (PROBE-BIND-1)."""
    from aisef2.probe.calibration import FIXTURE_REVISION, calibration_env
    from aisef2.probe.protocol import RevisionRef, bound_result, run_probe
    probe = _probe(spec.probe_id)
    at = RevisionRef(FIXTURE_REVISION, str(tree.resolve()))
    return bound_result(run_probe(probe, spec, at, calibration_env(sys.executable)), spec=spec, revision=at.sha,
                        enforcement=probe.enforcement())


def diagnose(spec, tree: pathlib.Path) -> dict:
    """A second, diagnostic observation: what the probe saw (kind, verdict, detail). Never evidence of a verdict."""
    from aisef2.probe.calibration import FIXTURE_REVISION, calibration_env
    from aisef2.probe.protocol import RevisionRef
    obs = _probe(spec.probe_id).observe(spec, RevisionRef(FIXTURE_REVISION, str(tree.resolve())), calibration_env(sys.executable))
    return {"kind": obs.kind.value, "verdict": obs.verdict.value if obs.verdict else None, "detail": obs.detail[:1200]}


def verdict_of(result) -> str:
    if hasattr(result, "behavior_verdict"):
        return result.behavior_verdict.value + (f" ({result.reason.value})" if result.reason else "")
    return f"{result.status.value}: {getattr(result, 'detail', '')[:300]}"


def falsify(e: dict, spec, trees: dict[str, pathlib.Path], targets: dict[str, str]) -> dict:
    from aisef2.arch.enums import BehaviorVerdict
    from aisef2.probe.calibration import SpecFalsifiabilityEvidence, falsifiability_problems
    from aisef2.product.outcome import Executed
    sections = FR_SECTIONS[e["requirement"]]
    designed = [m for m, t in targets.items() if t in sections]
    out = {"ac_id": e["ac_id"], "requirement": e["requirement"], "sections": list(sections), "spec_id": spec.id,
           "semantic_hash": spec.semantic_hash, "probe_id": spec.probe_id, "observation_class": e["observation_class"],
           "quantifier": e["quantifier"], "expectation": spec.candidate_expectation.value, "designed_for": designed}
    ref = observe(spec, trees["reference"])
    out["reference"] = verdict_of(ref)
    if not (isinstance(ref, Executed) and ref.behavior_verdict is spec.candidate_expectation):
        out.update(status="REFERENCE_NOT_SATISFIED", reference_observation=diagnose(spec, trees["reference"]),
                   verdicts={}, refuted=[], unrefuted_designed=designed, refuted_beyond_design=[], evidence=[],
                   note="no mutant can show contrast against a reference that does not meet the expectation; none run")
        return out
    verdicts, evidence, problems = {}, [], []
    for name, tree in trees.items():
        if name == "reference":
            continue
        result = observe(spec, tree)
        verdicts[name] = verdict_of(result)
        if isinstance(result, Executed) and result.behavior_verdict is not spec.candidate_expectation \
                and result.behavior_verdict in (BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED):
            ev = SpecFalsifiabilityEvidence(spec.id, spec.semantic_hash, MECHANISM, f"{FIX_REL}/mutants/{name}",
                                            result.behavior_verdict)
            found = falsifiability_problems(ev, spec)
            problems += [f"{e['ac_id']} x {name}: {p}" for p in found]
            evidence.append({"counterexample_ref": ev.counterexample_ref, "mechanism": ev.mechanism,
                             "observed": ev.observed.value, "falsifiability_problems": found})
    refuted = [x["counterexample_ref"].rsplit("/", 1)[1] for x in evidence if not x["falsifiability_problems"]]
    out.update(status="QUALIFIED" if refuted else "NOT_QUALIFIED", verdicts=verdicts, refuted=refuted,
               unrefuted_designed=[m for m in designed if m not in refuted],
               refuted_beyond_design=[m for m in refuted if m not in designed], evidence=evidence, problems=problems)
    return out


def reproduce_finding_001(built: dict, reference: pathlib.Path) -> dict:
    """C2-P5-FINDING-001, measured: the form ec473d1 compiled for the four source-tree prohibitions (grep_count
    {matches: 0}) under the seam's MUST_NOT_HOLD, run on the reference. The reference has no forbidden line; a verdict
    SATISFIED under the expectation REFUTED is the inversion — a correct product violates the contract."""
    aid = _aid()
    reqs = aid.requirements()
    crit = {e["ac_id"]: e for e in built["criteria"]}
    rows = {}
    for ac, form in aid.INVERTED_FORMS.items():
        e = crit[ac]
        spec = aid.author(ac, form, e["requirement"], e["polarity"], e["criterion"], reqs, polarity_rule=False)["spec"]
        result = observe(spec, reference)
        rows[ac] = {"polarity": e["polarity"], "semantic_hash": spec.semantic_hash,
                    "expectation": spec.candidate_expectation.value, "reference": verdict_of(result),
                    "inverted": verdict_of(result) != spec.candidate_expectation.value}
    return {"finding": "C2-P5-FINDING-001", "specs": rows, "reproduced": all(r["inverted"] for r in rows.values()),
            "rule": "the ec473d1 form of each prohibition, compiled with the aid's polarity rule off, run on the reference"}


def run() -> dict:
    started = time.monotonic()
    aid, T = _aid(), _trees()
    p0 = T._p0()
    built = aid.build()
    specs = built["specs"]
    targets = {m["id"]: m["target"] for m in p0._catalog()}
    rows = []
    with tempfile.TemporaryDirectory(prefix="aisef-p5-") as tmp:
        work = pathlib.Path(tmp)
        trees = {"reference": T.build_tree(None, work)}
        trees.update({m: T.build_tree(m, work) for m in targets})
        identities = {name: T.tree_identity(tree) for name, tree in trees.items()}
        finding = reproduce_finding_001(built, trees["reference"])
        for e in built["criteria"]:
            if e["v22_status"] != "COMPILED":
                rows.append({"ac_id": e["ac_id"], "requirement": e["requirement"], "status": "NO_SPEC",
                             "v22_status": e["v22_status"], "reason": e["typed_refusal"]})
                continue
            rows.append(falsify(e, specs[e["spec_id"]], trees, targets))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    compiled = [r for r in rows if r["status"] != "NO_SPEC"]
    body = {
        "record": "AISEF V2 — C2-P5 WP-2.5.2 SPEC FALSIFIABILITY (PLAN-V2.2 proposal specs over the LedgerLock reference)",
        "work_package": PACKAGE,
        "authority": "owner ruling 'AISEF V2 — CYCLE-2 OWNER RULING / C2-P0 ACCEPTED / AUTHORIZE MAXIMUM SAFE PARALLEL "
                     "EXECUTION' (2026-09-29): C2-P5 WP-2.5.2 after WP-2.5.1",
        "status": "MEASUREMENT of a proposal that is NOT approved and NOT applied",
        "identities": {"head": _git("rev-parse", "HEAD"), "aisef2_tree": _git("rev-parse", "HEAD:aisef2"),
                       "proposal": _file(aid.OUT_REL), "proposal_digest": json.loads((ROOT / aid.OUT_REL).read_text(encoding="utf-8"))["proposal_digest"],
                       "plan_hash": built["plan"].plan_hash, "authoring_aid": _file("validation/qualification/p10_contracts.py"),
                       "runner": _file("validation/qualification/p5_falsifiability.py"),
                       "fixture": {"path": FIX_REL, "record": _file("closure-evidence/v2/cycle2/P0-REFERENCE-FIXTURE.json"),
                                   "mutants_catalog": _file(f"{FIX_REL}/MUTANTS.json"),
                                   "requirements_map": _file(f"{FIX_REL}/REQUIREMENTS-MAP.json")},
                       "trees": identities},
        "platform": {"python": platform.python_version(), "platform": sys.platform},
        "mechanism": MECHANISM, "fr_sections": {k: list(v) for k, v in FR_SECTIONS.items()},
        "counts_by_status": dict(sorted(counts.items())),
        "summary": {
            "specs": len(compiled),
            "reference_satisfied": sum(1 for r in compiled if r["status"] in ("QUALIFIED", "NOT_QUALIFIED")),
            "qualified": sum(1 for r in compiled if r["status"] == "QUALIFIED"),
            "reference_not_satisfied_by_cause": _causes(compiled),
            "unrefuted_designed_mutants": {r["ac_id"]: r["unrefuted_designed"] for r in compiled
                                           if r["status"] in ("QUALIFIED", "NOT_QUALIFIED") and r["unrefuted_designed"]},
            "mutants_refuted_by_no_spec": sorted(set(targets) - {m for r in compiled for m in r.get("refuted", [])}),
        },
        "specs": rows,
        "finding_001": finding,
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    runs = {m: _load("aisef_v2_c2_cli_harness", "validation/qualification/c2_cli_harness.py").owned_run(m)
            for m in TEST_MODULES}
    body["tests"] = runs
    body["problems"] = [p for r in compiled for p in r.get("problems", [])]
    body["problems"] += [f"{m}: status {r['status']} exit {r['exit']} residual {r['residual']}"
                         for m, r in runs.items() if r["status"] != "OK" or r["exit"] != 0 or r["residual"]]
    if not finding["reproduced"]:
        body["problems"].append("C2-P5-FINDING-001 is not reproduced on the reference")
    body["verdict"] = "COMPLETE" if not body["problems"] else "PROBLEMS"
    return body


def _causes(rows: list[dict]) -> dict:
    """REFERENCE_NOT_SATISFIED grouped by what the reference's observation says."""
    out: dict[str, list[str]] = {}
    for r in rows:
        if r["status"] != "REFERENCE_NOT_SATISFIED":
            continue
        o = r["reference_observation"]
        key = o["kind"] if o["kind"] != "OBSERVED" else f"OBSERVED {o['verdict']}"
        out.setdefault(key, []).append(r["ac_id"])
    return out


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", required=True)
    ap.parse_args(argv)
    rec = run()
    (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{OUT_REL}: {rec['verdict']}; {rec['counts_by_status']}; qualified {rec['summary']['qualified']}/"
          f"{rec['summary']['specs']}; {rec['elapsed_s']} s")
    return 0 if not rec["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
