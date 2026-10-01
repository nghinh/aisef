"""WP-2.5.2 (C2-P5, corrected) — SpecFalsifiabilityEvidence for every retained PLAN-V2.2 ProductProofSpec:
closure-evidence/v2/cycle2/P5-FALSIFIABILITY.json (RFC §9.1.2, §27).

    python -P validation/qualification/p5_falsifiability.py --seal    # binds each P5 mutant's materialised digests
    python -P validation/qualification/p5_falsifiability.py --run     # the evidence run

**Its own witness per spec.** The P0 mutants (P0-REFERENCE-FIXTURE.json) prove the reference ACCEPTANCE falsifiable; they
are not reused as this package's witnesses. Each retained spec has one controlled mutation of its own in the P5 corpus
(tests/v2/fixtures/workloads/ledgerlock-p5-mutants/MUTANTS.json), materialised here from the frozen reference into a
temporary directory (the reference is never written) and refused unless it reproduces the sealed digests. For every
spec: the pristine reference must SATISFY it and its witness must REFUTE it; the observed contrast is a
SpecFalsifiabilityEvidence (`controlled_product_mutation`) validated by the frozen `falsifiability_problems`.

**Consequential failures, separately.** Every spec also runs against every other P5 witness (which other specs a
mutation reaches) and against the 26 P0 mutants (which accepted-acceptance defects the ProductProof set reaches; every
P0 mutant no spec refutes carries an explanation). The harness never reads a mutant's id or metadata to decide a
verdict: a tree is a directory, a spec is a ProductProofSpec, the probe is the catalog's.
"""

from __future__ import annotations

import argparse
import concurrent.futures
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
MUTANTS_REL = "tests/v2/fixtures/workloads/ledgerlock-p5-mutants/MUTANTS.json"
WORKERS = 3
#: the package's tests, run under the owned-process gate (the Record case reads this record, so it runs in the suite)
TEST_MODULES = ("tests.v2.test_p5_falsifiability.Falsifiability", "tests.v2.test_p5_plan_v22_proposal")
#: why a P0 mutant is reached by no retained ProductProofSpec (reporting only; never read by a verdict)
P0_UNCOVERED_REASON = {
    "M-3.2-1": "the '|' separator changes every hash consistently: the product's own verify accepts its own chain, and no "
               "spec may recompute a hash value (R-3.2/2: the canonical bytes are open)",
    "M-3.2-2": "it breaks only Ledger.append's chaining; the retained specs mutate through apply_batch(ops), the one mutation "
               "signature the requirements fix (§5); append's signature is open (IB-LEDGER)",
    "M-3.3-3": "it changes only first_bad_index for a hash violation (i + 1), which no spec observes (R-3.3/3); the repair-tail "
               "refusal it causes needs an unterminated tail line that parses and fails its hash, which the specs' truncated "
               "tail (a line that does not parse) is not",
    "M-4.1-1": "it accepts an empty rid; the requirements prescribe no behaviour for an empty rid (R-4.1/1 is descriptive)",
    "M-5-2": "it breaks a replay between two elements of ONE batch; the requirements judge replays and conflicts against "
             "committed mutations (RISK-10), so no spec requires in-batch replay",
    "M-6-1": "it drops the snapshot's key order; the order is observable only through a layout the requirements leave open (R-6/3)",
    "M-8-1": "it removes an fsync; durability is not observable from outside the process (R-8/1)",
    "M-9-1": "exit 4 (conflict) is reachable only through `apply --batch <file>`, whose file shape is open (R-9/4, OD-BATCH)",
}


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


def _p0():
    return _load("aisef_v2_p0_reference_fixture", "validation/qualification/p0_reference_fixture.py")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file(rel: str) -> dict:
    return {"path": rel, "sha256": _sha((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))}


def corpus() -> dict:
    return json.loads((ROOT / MUTANTS_REL).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------- trees

def reference_modules() -> dict[str, str]:
    ref = ROOT / FIX_REL / "reference" / "ledgerlock"
    return {p.name: p.read_bytes().replace(b"\r\n", b"\n").decode("utf-8") for p in sorted(ref.glob("*.py"))}


def apply_mutant(m: dict, modules: dict[str, str]) -> dict[str, str | None]:
    """The package's modules after `m`'s declared changes (a module removed maps to None). A `before` that is not exactly
    one line of its module refuses the mutant."""
    out: dict[str, str | None] = dict(modules)
    for c in m["changes"]:
        name = c["module"]
        if c.get("remove"):
            out[name] = None
            continue
        if "rename_to" in c:
            out[c["rename_to"]], out[name] = out[name], None
            continue
        lines = out[name].split("\n")
        hits = [i for i, line in enumerate(lines) if line == c["before"]]
        if len(hits) != 1:
            raise SystemExit(f"{m['id']}: {c['before']!r} occurs {len(hits)} times in {name}")
        after = [] if c["after"] is None else list(c["after"])
        out[name] = "\n".join(lines[:hits[0]] + after + lines[hits[0] + 1:])
    return out


def mutant_digests(m: dict) -> dict[str, str | None]:
    ref = reference_modules()
    new = apply_mutant(m, ref)
    return {f"ledgerlock/{k}": (None if v is None else _sha(v.encode("utf-8"))) for k, v in sorted(new.items()) if ref.get(k) != v}


def build_tree(m: dict | None, work: pathlib.Path) -> pathlib.Path:
    """The reference tree (m None) or m's, under `work`; a mutant whose digests differ from its seal is refused."""
    tree = work / (m["id"] if m else "reference")
    pkg = tree / "ledgerlock"
    pkg.mkdir(parents=True)
    modules = reference_modules()
    if m is not None:
        if mutant_digests(m) != m.get("modules"):
            raise SystemExit(f"{m['id']}: the materialised modules do not reproduce the sealed digests")
        modules = apply_mutant(m, modules)
    for name, text in modules.items():
        if text is not None:
            (pkg / name).write_bytes(text.encode("utf-8"))
    return tree


def build_p0_tree(mutant_id: str, work: pathlib.Path) -> pathlib.Path:
    return _load("aisef_v2_c2_effect_calibration", "validation/qualification/c2_effect_calibration.py").build_tree(mutant_id, work / "p0")


def tree_identity(tree: pathlib.Path) -> dict:
    return {str(p.relative_to(tree)).replace("\\", "/"): _sha(p.read_bytes()) for p in sorted(tree.rglob("*.py"))
            if "__pycache__" not in p.parts}


def seal() -> dict:
    doc = corpus()
    for m in doc["mutants"]:
        m["modules"] = mutant_digests(m)
    doc["corpus_sha256"] = _sha(json.dumps(doc["mutants"], sort_keys=True, ensure_ascii=False).encode("utf-8"))
    (ROOT / MUTANTS_REL).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return doc


def corpus_problems() -> list[str]:
    doc = corpus()
    out = []
    if doc.get("corpus_sha256") != _sha(json.dumps(doc["mutants"], sort_keys=True, ensure_ascii=False).encode("utf-8")):
        out.append("MUTANTS.json: corpus_sha256 does not bind the mutants")
    for m in doc["mutants"]:
        if mutant_digests(m) != m.get("modules"):
            out.append(f"{m['id']}: the materialised modules do not reproduce the sealed digests")
    specs = [m["spec"] for m in doc["mutants"]]
    out += [f"{s}: {specs.count(s)} witnesses" for s in sorted(set(specs)) if specs.count(s) != 1]
    return out


# --------------------------------------------------------------------------------------- observation

_SPECS: dict = {}


def _spec(spec_id: str):
    if not _SPECS:
        _SPECS.update(_aid().build()["compiled"])
    return _SPECS[spec_id]


def _probe(probe_id: str):
    from aisef2.probe import catalog
    return next(e for e in catalog.CATALOG if e.probe_id == probe_id).factory()


def observe(spec, tree: pathlib.Path):
    from aisef2.probe.calibration import FIXTURE_REVISION, calibration_env
    from aisef2.probe.protocol import RevisionRef, bound_result, run_probe
    probe = _probe(spec.probe_id)
    at = RevisionRef(FIXTURE_REVISION, str(tree.resolve()))
    return bound_result(run_probe(probe, spec, at, calibration_env(sys.executable)), spec=spec, revision=at.sha,
                        enforcement=probe.enforcement())


def verdict_of(result) -> str:
    if hasattr(result, "behavior_verdict"):
        return result.behavior_verdict.value + (f" ({result.reason.value})" if result.reason else "")
    return f"{result.status.value}: {getattr(result, 'detail', '')[:200]}"


def _job(args) -> tuple:
    spec_id, tree_name, tree = args
    return spec_id, tree_name, verdict_of(observe(_spec(spec_id), pathlib.Path(tree)))


def diagnose(spec, tree: pathlib.Path) -> dict:
    """A second, diagnostic observation (kind, verdict, detail); never a verdict's evidence."""
    from aisef2.probe.calibration import FIXTURE_REVISION, calibration_env
    from aisef2.probe.protocol import RevisionRef
    obs = _probe(spec.probe_id).observe(spec, RevisionRef(FIXTURE_REVISION, str(tree.resolve())), calibration_env(sys.executable))
    return {"kind": obs.kind.value, "verdict": obs.verdict.value if obs.verdict else None, "detail": obs.detail[:1200]}


def evidence(spec, mutant_id: str, verdict: str) -> dict:
    from aisef2.arch.enums import BehaviorVerdict
    from aisef2.probe.calibration import SpecFalsifiabilityEvidence, falsifiability_problems
    if verdict not in ("SATISFIED", "REFUTED"):
        return {"counterexample_ref": f"{MUTANTS_REL}#{mutant_id}", "observed": verdict, "falsifiability_problems": ["no decided verdict"]}
    ev = SpecFalsifiabilityEvidence(spec.id, spec.semantic_hash, MECHANISM, f"{MUTANTS_REL}#{mutant_id}", BehaviorVerdict(verdict))
    return {"spec_id": ev.spec_id, "semantic_hash": ev.semantic_hash, "mechanism": ev.mechanism,
            "counterexample_ref": ev.counterexample_ref, "observed": ev.observed.value,
            "falsifiability_problems": falsifiability_problems(ev, spec)}


def classify(expectation: str, pristine: str, witness: str) -> str:
    if pristine != expectation:
        return "REFERENCE_NOT_SATISFIED"
    contrast = {"SATISFIED": "REFUTED", "REFUTED": "SATISFIED"}[expectation]
    return "QUALIFIED" if witness == contrast else "NOT_QUALIFIED"


def reproduce_finding_001(reference: pathlib.Path) -> dict:
    """C2-P5-FINDING-001 kept measurable: ec473d1's inverted form (grep_count {matches: 0} under MUST_NOT_HOLD), compiled
    with the aid's polarity rule off, on the reference."""
    aid = _aid()
    entry = {**aid.INVERTED_FORM, "requirement": "R-12", "quantifier": aid.EX, "polarity": "MUST_NOT_HOLD", "measured": "(inverted)"}
    spec = aid.author("FINDING-001", entry, {"R-12": aid.requirements().get("R-12")}, polarity_rule=False)["spec"]
    got = verdict_of(observe(spec, reference))
    return {"finding": "C2-P5-FINDING-001", "semantic_hash": spec.semantic_hash, "expectation": spec.candidate_expectation.value,
            "reference": got, "reproduced": got != spec.candidate_expectation.value}


# --------------------------------------------------------------------------------------- the run

def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def run(matrix: bool = True) -> dict:
    started = time.monotonic()
    aid = _aid()
    built = aid.build()
    specs = built["compiled"]
    entries = {e["spec_id"]: e for e in built["specs"]}
    doc = corpus()
    mutants = {m["id"]: m for m in doc["mutants"]}
    witness_of = {m["spec"]: m["id"] for m in doc["mutants"]}
    p0 = [m["id"] for m in _p0()._catalog()]
    with tempfile.TemporaryDirectory(prefix="aisef-p5f-", ignore_cleanup_errors=True) as tmp:
        work = pathlib.Path(tmp)
        trees = {"reference": build_tree(None, work)}
        trees.update({mid: build_tree(m, work) for mid, m in mutants.items()})
        p0_trees = {mid: build_p0_tree(mid, work) for mid in p0}
        identities = {name: tree_identity(t) for name, t in {**trees, **{f"P0:{k}": v for k, v in p0_trees.items()}}.items()}
        jobs = [(sid, "reference", str(trees["reference"])) for sid in specs]
        jobs += [(sid, mid, str(trees[mid])) for sid in specs for mid in (mutants if matrix else [witness_of[sid]])]
        jobs += [(sid, f"P0:{mid}", str(p0_trees[mid])) for sid in specs for mid in (p0 if matrix else [])]
        verdicts: dict[tuple, str] = {}
        _SPECS.update(specs)   # built once, before any worker reads it
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:   # each job waits on its own child processes
            for sid, name, v in pool.map(_job, jobs):
                verdicts[(sid, name)] = v
        rows = []
        for sid, spec in specs.items():
            expectation = spec.candidate_expectation.value
            mid = witness_of[sid]
            status = classify(expectation, verdicts[(sid, "reference")], verdicts[(sid, mid)])
            row = {"spec_id": sid, "clause": entries[sid]["clause"], "requirement": entries[sid]["requirement"],
                   "probe_id": spec.probe_id, "observation_class": entries[sid]["observation_class"],
                   "semantic_hash": spec.semantic_hash, "expectation": expectation,
                   "pristine": verdicts[(sid, "reference")], "mutant_id": mid,
                   "mutation": [{k: v for k, v in c.items()} for c in mutants[mid]["changes"]],
                   "violation": mutants[mid]["violation"], "mutant_verdict": verdicts[(sid, mid)], "status": status,
                   "evidence": evidence(spec, mid, verdicts[(sid, mid)].split(" ")[0]) if status == "QUALIFIED" else None,
                   "consequential_p5": sorted(m for m in mutants if m != mid and (sid, m) in verdicts
                                              and verdicts[(sid, m)].split(" ")[0] == {"SATISFIED": "REFUTED", "REFUTED": "SATISFIED"}[expectation]),
                   "p0_refuted": sorted(m for m in p0 if (sid, f"P0:{m}") in verdicts
                                        and verdicts[(sid, f"P0:{m}")].split(" ")[0] == {"SATISFIED": "REFUTED", "REFUTED": "SATISFIED"}[expectation])}
            if status != "QUALIFIED":
                row["reference_observation"] = diagnose(spec, trees["reference"])
                row["mutant_observation"] = diagnose(spec, trees[mid])
            rows.append(row)
        finding = reproduce_finding_001(trees["reference"])
    by_mutant = {mid: {"spec": m["spec"], "refuted_by": sorted(r["spec_id"] for r in rows if r["mutant_id"] == mid and r["status"] == "QUALIFIED")
                       + sorted(r["spec_id"] for r in rows if mid in r["consequential_p5"])} for mid, m in mutants.items()}
    p0_cross = {mid: {"target": next(x["target"] for x in _p0()._catalog() if x["id"] == mid),
                      "refuted_by": sorted(r["spec_id"] for r in rows if mid in r["p0_refuted"])} for mid in p0}
    for mid, v in p0_cross.items():
        if not v["refuted_by"]:
            v["explanation"] = P0_UNCOVERED_REASON.get(mid)
    status_counts: dict[str, int] = {}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    runs = {m: _load("aisef_v2_c2_cli_harness", "validation/qualification/c2_cli_harness.py").owned_run(m) for m in TEST_MODULES}
    body = {
        "record": "AISEF V2 — C2-P5 WP-2.5.2 SPEC FALSIFIABILITY (corrected): every retained PLAN-V2.2 ProductProofSpec against "
                  "the pristine reference and its own controlled witness",
        "work_package": PACKAGE,
        "authority": "owner ruling 'AISEF V2 — CYCLE-2 OWNER REVIEW / C2-P5 NOT ACCEPTED / P5 CORRECTION AUTHORIZED' (2026-09-30)",
        "status": "MEASUREMENT of a proposal that is NOT approved and NOT applied",
        "supersedes": {"commit": "0f779956f98f38abf4d4c33c6db4cadd819d8640", "sha256": "cc73087449204b8a484ffa4bea0150be289bac15da68ee4c9ead84b57f173935",
                       "reason": "owner ruling 2026-09-30: C2-P5 NOT ACCEPTED (7/64 qualified, reused P0 mutants); rebuilt with the "
                                 "requirements-grounded spec set and a P5 witness per spec"},
        "identities": {"head": _git("rev-parse", "HEAD"), "aisef2_tree": _git("rev-parse", "HEAD:aisef2"),
                       "proposal": _file(aid.OUT_REL), "proposal_digest": json.loads((ROOT / aid.OUT_REL).read_text(encoding="utf-8"))["proposal_digest"],
                       "plan_hash": built["plan"].plan_hash, "authoring_aid": _file("validation/qualification/p10_contracts.py"),
                       "runner": _file("validation/qualification/p5_falsifiability.py"),
                       "p5_mutants": {**_file(MUTANTS_REL), "corpus_sha256": doc["corpus_sha256"]},
                       "reference": {"path": f"{FIX_REL}/reference", "record": _file("closure-evidence/v2/cycle2/P0-REFERENCE-FIXTURE.json")},
                       "trees": identities},
        "platform": {"python": platform.python_version(), "platform": sys.platform},
        "mechanism": MECHANISM,
        "summary": {"retained_specs": len(rows), "qualified": status_counts.get("QUALIFIED", 0),
                    "not_qualified": status_counts.get("NOT_QUALIFIED", 0),
                    "reference_not_satisfied": status_counts.get("REFERENCE_NOT_SATISFIED", 0),
                    "specs_without_witness": sum(1 for s in specs if s not in witness_of),
                    "p0_mutants_refuted": sum(1 for v in p0_cross.values() if v["refuted_by"]),
                    "p0_mutants_uncovered": sorted(k for k, v in p0_cross.items() if not v["refuted_by"])},
        "specs": rows,
        "p5_mutants": by_mutant,
        "p0_cross_check": p0_cross,
        "finding_001": finding,
        "tests": runs,
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    body["problems"] = ([f"{r['spec_id']}: {r['status']} (pristine {r['pristine']}, witness {r['mutant_id']} {r['mutant_verdict']})"
                         for r in rows if r["status"] != "QUALIFIED"]
                        + [f"{r['spec_id']}: {p}" for r in rows if r["evidence"] for p in r["evidence"]["falsifiability_problems"]]
                        + [f"P0 {k}: refuted by no spec and no explanation" for k, v in p0_cross.items() if not v["refuted_by"] and not v.get("explanation")]
                        + ([] if finding["reproduced"] else ["C2-P5-FINDING-001 is not reproduced"])
                        + [f"{m}: status {r['status']} exit {r['exit']} residual {r['residual']}" for m, r in runs.items()
                           if r["status"] != "OK" or r["exit"] != 0 or r["residual"]]
                        + corpus_problems())
    body["verdict"] = "COMPLETE — EVERY RETAINED SPEC QUALIFIED" if not body["problems"] else "PROBLEMS"
    return body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--seal", action="store_true")
    g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    if a.seal:
        doc = seal()
        print(f"{MUTANTS_REL}: {len(doc['mutants'])} mutants sealed, corpus {doc['corpus_sha256'][:12]}")
        return 0
    rec = run()
    (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{OUT_REL}: {rec['verdict']}; {rec['summary']}; {rec['elapsed_s']} s")
    return 0 if not rec["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
