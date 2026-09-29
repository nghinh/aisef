"""WP-2.3.2 — the `process_effect` probe calibrated and its specs made falsifiable over the LedgerLock reference
fixture: closure-evidence/v2/cycle2/P3-EFFECT-CALIBRATION.json.

    --run            (1) the three classes calibrated by the frozen `calibrate()` over the committed small fixtures
                     (tests/v2/fixtures/calibration/process_effect) and (2) over the LedgerLock reference: per class a
                     positive fixture whose checkout is the reference tree and a negative one whose checkout is one
                     mutant of MUTANTS.json, both built in a temporary directory from the frozen blobs; (3) the
                     DECISION-1 quantifier declarations; (4) SpecFalsifiabilityEvidence: ProductProofSpec-shaped
                     contracts authored from REQUIREMENTS.md, compiled with the frozen compiler, each observed on the
                     reference (SATISFIED) and on every mutant (controlled_product_mutation), the evidence objects
                     validated by `falsifiability_problems`; a spec that refutes no mutant is reported NOT QUALIFIED;
                     the requirement sections covered and the mutants no spec refutes (a gap list); (5) the test
                     modules under the owned-process gate, the C2-P3 mutation summary, the static checks; write the
                     record (refused on any problem)
    --bind-ci RUN    bind the CI measurements of the record's commit (as validation/qualification/c2_effect_harness.py)

The reference fixture is FROZEN: nothing here writes under tests/v2/fixtures/workloads/ledgerlock-reference/. A mutant
tree is the reference copied into a temporary directory with each touched module replaced by the reference module plus
exactly the mutant's declared change (p0_reference_fixture.apply_change over changes_of / modules_of), checked
byte-identical to the committed mutants/<id>/<module> blob before it is used.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT_REL = "closure-evidence/v2/cycle2/P3-EFFECT-CALIBRATION.json"
HARNESS_REL = "closure-evidence/v2/cycle2/P3-EFFECT-HARNESS.json"
PACKAGE = "WP-2.3.2"
FIXTURES_REL = "tests/v2/fixtures/calibration/process_effect"
FIX_REL = "tests/v2/fixtures/workloads/ledgerlock-reference"
TEST_MODULES = ("tests.v2.test_c2_effect_calibration", "tests.v2.test_probe_process_effect_units")
CASES = {f"PECAL-{n}": f"test_PECAL_{n}_" for n in range(1, 5)}
APPROVER = "human:c2-p3-calibration-fixture"
L = "<ws>/l.jsonl"
LEDGER = "ledgerlock.ledger:Ledger"
NEW = {"step": "construct", "args": [L], "kwargs": {}}


def call(method, *args, bind=None):
    out = {"step": "call", "method": method, "args": list(args), "kwargs": {}}
    if bind:
        out["as"] = bind
    return out


def raises(method, exception, *args):
    out = {"step": "expect_raises", "args": list(args), "kwargs": {}, "exception": exception}
    if method:
        out["method"] = method
    return out


def put(key, value, rid, ts, bind=None):
    return call("put", key, value, rid, ts, bind=bind)


def fault(name):
    return {"step": "fault", "fault": name}


def cli(*argv, code):
    return {"step": "subprocess", "argv": ["-m", "ledgerlock", *argv], "expect_exit": code}


def _canonical(record: dict) -> bytes:
    """§3.2 as the reference's documented interpretation fixes it (REQUIREMENTS-MAP R-3.2): sorted keys, no whitespace,
    non-ASCII kept, `hash` and `prev_hash` blanked. Computed here, independently of the reference's code."""
    return json.dumps({**record, "hash": "", "prev_hash": ""}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def chain_hashes(*records: dict) -> list[str]:
    """hash = SHA-256(prev_hash || "|" || canonical_bytes), the first prev_hash the literal GENESIS (§3.2)."""
    out, prev = [], "GENESIS"
    for rec in records:
        prev = hashlib.sha256(prev.encode("utf-8") + b"|" + _canonical(rec)).hexdigest()
        out.append(prev)
    return out


H = chain_hashes({"op": "put", "key": "a", "value": 1, "ts": 1, "id": "r1"},
                 {"op": "put", "key": "b", "value": 2, "ts": 2, "id": "r2"})
TRUNCATED = '{"op":"put","key":"c"'
#: The specs: ProductProofSpec-shaped contracts over the reference, authored from REQUIREMENTS.md (the section ids are
#: REQUIREMENTS-MAP.json's). Each declares its family, its requirement sections, its quantifier semantics (DECISION-1)
#: and the subject-absence rule; `observable` omits the window, added at compile time.
SPECS = [
    {"id": "LL-HASH-1", "family": "hash chain", "requirements": ["R-3.2"],
     "claim": "two appends chain: the second line's hash is SHA-256(first hash | canonical bytes of the second)",
     "locator": LEDGER, "scenario": [NEW, put("a", 1, "r1", 1), put("b", 2, "r2", 2)],
     "observable": {"files": {L: {"jsonl": {"line": 1, "field": "hash", "equals": H[1]}}}},
     "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-NFC-1", "family": "hash chain", "requirements": ["R-3.1"],
     "claim": "a key given in NFD is stored in NFC",
     "locator": LEDGER, "scenario": [NEW, put("é", 1, "r1", 1)],
     "observable": {"files": {L: {"jsonl": {"line": 0, "field": "key", "equals": "é"}}}},
     "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-VERIFY-1", "family": "verify", "requirements": ["R-3.3", "R-3.4"],
     "claim": "a value changed on disk after three appends is found at its index by the same instance's verify",
     "locator": LEDGER, "scenario": [NEW, put("a", 1, "r1", 1), put("b", 2, "r2", 2), put("c", 3, "r3", 3),
                                     {"step": "edit_jsonl", "path": L, "line": 1, "field": "value", "value": 99},
                                     call("verify")],
     "observable": {"returns": [False, 1, 3]}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-VERIFY-2", "family": "verify", "requirements": ["R-3.3"],
     "claim": "a prev_hash changed on disk is found at its index",
     "locator": LEDGER, "scenario": [NEW, put("a", 1, "r1", 1), put("b", 2, "r2", 2),
                                     {"step": "edit_jsonl", "path": L, "line": 1, "field": "prev_hash", "value": H[1]},
                                     call("verify")],
     "observable": {"returns": [False, 1, 2]}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-RID-1", "family": "batches/idempotency/conflicts", "requirements": ["R-4.1"],
     "claim": "an empty request id is refused",
     "locator": LEDGER, "scenario": [NEW, raises("put", "ValueError", "a", 1, "", 1)],
     "observable": {"raises": True}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-IDEM-1", "family": "batches/idempotency/conflicts", "requirements": ["R-4.2"],
     "claim": "a replayed request id returns the first result and appends nothing",
     "locator": LEDGER, "scenario": [NEW, put("a", 1, "r1", 1, bind="first"), put("a", 1, "r1", 1, bind="again")],
     "observable": {"returns_name": "first", "equals_name": "again"}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-CONFLICT-1", "family": "batches/idempotency/conflicts", "requirements": ["R-4.3"],
     "claim": "another request id mutating a key raises ConflictError",
     "locator": LEDGER, "scenario": [NEW, put("a", 1, "r1", 1), raises("put", "ConflictError", "a", 2, "r2", 2)],
     "observable": {"raises": True}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-TOMB-1", "family": "batches/idempotency/conflicts", "requirements": ["R-4.4", "R-4.5"],
     "claim": "a put with another request id conflicts against a tombstone",
     "locator": LEDGER, "scenario": [NEW, call("delete", "a", "r1", 1), raises("put", "ConflictError", "a", 2, "r2", 2)],
     "observable": {"raises": True}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-BATCH-1", "family": "batches/idempotency/conflicts", "requirements": ["R-5", "R-13"],
     "claim": "ledger.apply_batch with a conflict in its third op commits nothing (the ledger file is never created)",
     "locator": "ledgerlock.ledger:apply_batch", "absence": "ABSENCE_IS_DECIDABLE",
     "scenario": [raises(None, "ConflictError", L, [["put", "a", 1, "r1", 1], ["put", "b", 2, "r2", 2],
                                                    ["put", "a", 3, "r3", 3]])],
     "observable": {"raises": True}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-BATCH-2", "family": "batches/idempotency/conflicts", "requirements": ["R-5"],
     "claim": "a request id replayed inside one batch commits one line",
     "locator": LEDGER, "scenario": [NEW, call("apply_batch", [["put", "a", 1, "r1", 1], ["put", "a", 1, "r1", 1]])],
     "observable": {"files": {L: {"line_count": 1}}}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-SNAP-1", "family": "snapshot", "requirements": ["R-6"],
     "claim": "the snapshot holds the live keys in byte order, a tombstoned key absent",
     "locator": LEDGER, "scenario": [NEW, put("b", 2, "r1", 1), put("a", 1, "r2", 2), call("delete", "d", "r3", 3),
                                     call("snapshot")],
     "observable": {"returns_bytes_hex": b'{"a":1,"b":2}\n'.hex()}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-REPAIR-1", "family": "repair-tail", "requirements": ["R-7"],
     "claim": "repair-tail is a no-op on a clean chain, removes exactly a truncated final line, and the chain verifies",
     "locator": LEDGER, "scenario": [NEW, put("a", 1, "r1", 1), put("b", 2, "r2", 2), call("repair_tail"),
                                     {"step": "write", "path": L, "text": TRUNCATED, "append": True},
                                     call("repair_tail"), call("verify")],
     "observable": {"returns": [True, None, 2]}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-REPAIR-2", "family": "repair-tail", "requirements": ["R-7"],
     "claim": "repair-tail refuses corruption that is not confined to the tail and leaves the file as it was",
     "locator": LEDGER, "scenario": [NEW, put("a", 1, "r1", 1), put("b", 2, "r2", 2),
                                     {"step": "edit_jsonl", "path": L, "line": 0, "field": "value", "value": 7},
                                     {"step": "write", "path": L, "text": TRUNCATED, "append": True},
                                     raises("repair_tail", "CorruptionError")],
     "observable": {"files": {L: {"line_count": 3}}}, "quantifier": "exhaustive_finite_domain"},
    {"id": "LL-FSYNC-1", "family": "fsync-before-rename and durability (DECISION-2 fault step)", "requirements": ["R-5"],
     "claim": "a batch whose temp-file fsync fails is not renamed over the ledger: the ledger keeps its one line",
     "locator": LEDGER, "scenario": [NEW, put("a", 1, "r1", 1), fault("os.fsync"),
                                     raises("apply_batch", "OSError", [["put", "b", 2, "r2", 2]]), call("verify")],
     "observable": {"returns": [True, None, 1]}, "quantifier": "bounded_witness_measurement"},
    {"id": "LL-FSYNC-2", "family": "fsync-before-rename and durability (DECISION-2 fault step)", "requirements": ["R-8"],
     "claim": "an append whose fsync fails does not return successfully",
     "locator": LEDGER, "scenario": [NEW, fault("os.fsync"), raises("put", "OSError", "a", 1, "r1", 1)],
     "observable": {"raises": True}, "quantifier": "bounded_witness_measurement"},
    {"id": "LL-REPLACE-1", "family": "fsync-before-rename and durability (DECISION-2 fault step)", "requirements": ["R-5"],
     "claim": "a batch whose rename fails leaves the ledger byte-identical to its pre-batch state",
     "locator": LEDGER, "scenario": [{"step": "workspace", "files": {"l.jsonl": {"text": ""}}}, NEW,
                                     fault("os.replace"), raises("apply_batch", "OSError", [["put", "a", 1, "r1", 1]])],
     "observable": {"files": {L: {"equals_before": True}}}, "quantifier": "bounded_witness_measurement"},
    {"id": "LL-CLI-1", "family": "CLI exit codes (subprocess step)", "requirements": ["R-9"],
     "claim": "the CLI exits 3 on a missing ledger, 4 on a conflict and 5 on a corrupt chain",
     "locator": LEDGER, "scenario": [NEW, cli("verify", "<ws>/missing.jsonl", code=3), put("a", 1, "r1", 1),
                                     cli("put", L, "a", "2", "--rid", "r2", "--ts", "2", code=4),
                                     {"step": "edit_jsonl", "path": L, "line": 0, "field": "value", "value": 5},
                                     cli("verify", L, code=5)],
     "observable": {"files": {L: {"line_count": 1}}}, "quantifier": "exhaustive_finite_domain"},
]


#: per class, the LedgerLock request and the one mutant (MUTANTS.json) whose declared target the class observes
LEDGERLOCK_CLASSES = {
    "scenario_returns": {"spec": "LL-VERIFY-1", "mutant": "M-3.3-1",
                         "why": "verify recomputes every hash from disk (R-3.3): the mutant never recomputes one, so "
                                "the tampered value is not found and verify returns another value"},
    "scenario_raises": {"spec": "LL-CONFLICT-1", "mutant": "M-4.3-1",
                        "attrs": {"args": ["key 'a' was last mutated by another rid"]},
                        "why": "another request id on a mutated key raises ConflictError (R-4.3): the mutant's "
                               "inverted condition never conflicts, so nothing is raised"},
    "scenario_files": {"spec": "LL-HASH-1", "mutant": "M-3.2-1",
                       "why": "the chained hash is SHA-256(prev_hash | canonical bytes) (R-3.2): the mutant drops the "
                              "separator, so the second line's stored hash is not the specified one"},
}
WINDOW = 30
MECHANISM = "controlled_product_mutation"
#: the verdict path, the file observables and equality: C2-P3 mutation targets since WP-2.3.1, measured at this digest
VERDICT_TARGETS = ("verdict_of", "_HOLDS", "_returns_hold", "_raises_hold", "_same", "_identity", "_jsonl_holds",
                   "_FILE_HOLDS", "_files_hold")
VERDICT_KILL_NOTE = ("killed by the class table on fixture facts (tests/v2/test_probe_process_effect_units.py); "
                     "tests/v2/test_c2_effect_calibration.py is not in their kill sets because it loads this builder "
                     "from validation/qualification, which the mutation runner's scratch tree (COPY, shared by every "
                     "phase) does not contain — COPY is not widened by this package")


def _load(name: str, rel: str):
    import importlib.util
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _p0():
    return _load("aisef_v2_p0_reference_fixture", "validation/qualification/p0_reference_fixture.py")


def _harness():
    return _load("aisef_v2_c2_effect_harness", "validation/qualification/c2_effect_harness.py")


def spec_def(spec_id: str) -> dict:
    return next(d for d in SPECS if d["id"] == spec_id)


# --------------------------------------------------------------------------------------- trees

def build_tree(mutant_id: str | None, work: pathlib.Path) -> pathlib.Path:
    """The reference tree (mutant None) or one mutant's, under `work`: the frozen reference copied, each module the
    mutant touches replaced by the reference module plus exactly the mutant's declared change — and checked
    byte-identical to the committed mutants/<id>/<module> blob before it is returned. Nothing is written under the
    frozen fixture."""
    p0 = _p0()
    tree = work / (mutant_id or "reference")
    shutil.copytree(p0.REF, tree)
    if mutant_id is None:
        return tree
    m = next(x for x in p0._catalog() if x["id"] == mutant_id)
    for module in p0.modules_of(m):
        text = p0._expected_module(m, module)
        committed = (p0.MUT / mutant_id / module).read_bytes().replace(b"\r\n", b"\n")
        if text.encode("utf-8") != committed:
            raise SystemExit(f"{mutant_id}/{module}: the materialised module differs from the committed mutant")
        (tree / "ledgerlock" / module).write_text(text, encoding="utf-8", newline="\n")
    return tree


def tree_identity(tree: pathlib.Path) -> dict:
    h = _harness()
    return {str(p.relative_to(tree)).replace("\\", "/"): h._identity(p)["sha256"]
            for p in sorted(tree.rglob("*.py")) if "__pycache__" not in p.parts}


# --------------------------------------------------------------------------------------- specs

def _section(rid: str) -> str:
    """The section's text as REQUIREMENTS-MAP.json binds it (heading to the next heading), checked by its digest."""
    rmap = json.loads((ROOT / FIX_REL / "REQUIREMENTS-MAP.json").read_text(encoding="utf-8"))
    row = next(r for r in rmap["requirements"] if r["id"] == rid)
    lines = (ROOT / FIX_REL / "REQUIREMENTS.md").read_text(encoding="utf-8").split("\n")
    body = "\n".join(lines[row["lines"][0] - 1:row["lines"][1]]).rstrip("\n") + "\n"
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != row["sha256"]:
        raise SystemExit(f"{rid}: the section text does not match REQUIREMENTS-MAP.json")
    return body


def compile_contract(defn: dict):
    """The spec's contract (approved by a fixture approval for compilation only — no plan uses it) compiled with the
    frozen compiler against the catalog's process_effect probe. Returns (contract, spec)."""
    from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind
    from aisef2.probe import process_effect as pe
    from aisef2.product.approval import ContractApproval, Requirement
    from aisef2.product.compiler import ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, Subject
    reqs = {rid: Requirement.create(id=rid, text=_section(rid), source=f"{FIX_REL}/REQUIREMENTS.md#{rid}")
            for rid in defn["requirements"]}
    contract = BehaviorContract.create(
        id=f"BC-{defn['id']}", requirement_ids=tuple(defn["requirements"]),
        subject=Subject(SubjectKind.PROCESS_EFFECT, defn["locator"]), stimulus={"scenario": defn["scenario"]},
        observable={**defn["observable"], "within_s": WINDOW}, polarity=Polarity.MUST_HOLD,
        subject_absence=SubjectAbsence(defn.get("absence", "REQUIRES_SUBJECT")), rationale=defn["claim"])
    approvals = [ContractApproval(rid, r.requirement_hash, contract.id, contract.contract_hash, APPROVER, 0.0, ())
                 for rid, r in reqs.items()]
    spec = compile_spec(contract, requirements=reqs, approvals=approvals,
                        probes={SubjectKind.PROCESS_EFFECT: ProbeRef(pe.PROBE_ID, pe.DIGEST)})
    return contract, spec


def observe(spec, tree: pathlib.Path):
    """The spec run by the catalog's probe at the fixture revision, read through its bound record (PROBE-BIND-1)."""
    from aisef2.probe import process_effect as pe
    from aisef2.probe.calibration import FIXTURE_REVISION, calibration_env
    from aisef2.probe.protocol import RevisionRef, bound_result, run_probe
    probe = pe.ProcessEffectProbe()
    at = RevisionRef(FIXTURE_REVISION, str(tree.resolve()))
    return bound_result(run_probe(probe, spec, at, calibration_env(sys.executable)), spec=spec, revision=at.sha,
                        enforcement=probe.enforcement())


def _verdict(result) -> str:
    if hasattr(result, "behavior_verdict"):
        return result.behavior_verdict.value
    return f"{result.status.value}: {getattr(result, 'detail', '')}"


def falsifiability(defn: dict, trees: dict[str, pathlib.Path]) -> dict:
    """One spec against the reference (it must be SATISFIED) and every mutant tree given; each mutant it refutes is
    a SpecFalsifiabilityEvidence (controlled_product_mutation), validated by `falsifiability_problems`. A spec that
    refutes no mutant is NOT QUALIFIED — reported, never hidden."""
    from aisef2.arch.enums import BehaviorVerdict
    from aisef2.probe.calibration import SpecFalsifiabilityEvidence, falsifiability_problems
    from aisef2.product.outcome import Executed
    p0 = _p0()
    contract, spec = compile_contract(defn)
    targets = {m["id"]: m["target"] for m in p0._catalog()}
    verdicts, evidence, problems = {}, [], []
    for name, tree in trees.items():
        result = observe(spec, tree)
        verdicts[name] = _verdict(result)
        if name == "reference" or not (isinstance(result, Executed)
                                       and result.behavior_verdict is BehaviorVerdict.REFUTED):
            continue
        ev = SpecFalsifiabilityEvidence(spec.id, spec.semantic_hash, MECHANISM, f"{FIX_REL}/mutants/{name}",
                                        result.behavior_verdict)
        found = falsifiability_problems(ev, spec)
        problems += [f"{defn['id']} x {name}: {p}" for p in found]
        evidence.append({"spec_id": ev.spec_id, "semantic_hash": ev.semantic_hash, "mechanism": ev.mechanism,
                         "counterexample_ref": ev.counterexample_ref, "observed": ev.observed.value,
                         "falsifiability_problems": found})
    if verdicts.get("reference") != "SATISFIED":
        problems.append(f"{defn['id']}: the reference is observed {verdicts.get('reference')}, not SATISFIED")
    mutants = [n for n in trees if n != "reference"]
    refuted = [n for n in mutants if verdicts[n] == "REFUTED"]
    designed = [n for n in mutants if targets[n] in defn["requirements"]]
    return {"id": defn["id"], "family": defn["family"], "requirements": defn["requirements"], "claim": defn["claim"],
            "quantifier_semantics": defn["quantifier"], "subject": defn["locator"],
            "subject_absence": defn.get("absence", "REQUIRES_SUBJECT"), "contract_id": contract.id,
            "contract_hash": contract.contract_hash, "spec_id": spec.id, "semantic_hash": spec.semantic_hash,
            "probe_input": json.loads(json.dumps(spec.to_json()["probe_input"])),
            "reference": verdicts.get("reference"), "verdicts": {n: verdicts[n] for n in mutants},
            "designed_for": designed, "refuted": refuted,
            "unrefuted_designed": [n for n in designed if n not in refuted],
            "refuted_beyond_design": [n for n in refuted if n not in designed],
            "qualified": bool(refuted) and verdicts.get("reference") == "SATISFIED",
            "status": "QUALIFIED" if refuted and verdicts.get("reference") == "SATISFIED" else "NOT QUALIFIED",
            "evidence": evidence, "problems": problems}


# --------------------------------------------------------------------------------------- calibrations

def small_calibrations() -> tuple[list[dict], list[str]]:
    """The three classes over the committed small fixtures (real calibrate(), the catalog registry); each rejected
    once its fixtures stop contrasting."""
    from dataclasses import asdict
    from aisef2.probe import catalog, process_effect as pe
    from aisef2.probe.calibration import NotQualified, calibrate, calibration_env
    probe, registry, env = pe.ProcessEffectProbe(), catalog.registry(), calibration_env(sys.executable)
    records, problems = [], []
    for cls in pe.CLASSES:
        pos, neg = (ROOT / FIXTURES_REL / cls / side for side in ("positive", "negative"))
        try:
            rec = calibrate(probe, cls, pos, neg, env, time.time, registry=registry,
                            names=(f"{FIXTURES_REL}/{cls}/positive", f"{FIXTURES_REL}/{cls}/negative"))
        except NotQualified as e:
            problems.append(f"small {cls}: {e}")
            continue
        records.append(asdict(rec))
        for a, b in ((neg, neg), (pos, pos)):
            try:
                calibrate(probe, cls, a, b, env, time.time, registry=registry)
                problems.append(f"small {cls}: a non-contrasting pair ({a.name}, {b.name}) was not rejected")
            except NotQualified:
                pass
    return records, problems


def _fixture(root: pathlib.Path, request: dict, tree: pathlib.Path) -> pathlib.Path:
    root.mkdir(parents=True)
    (root / "request.json").write_text(json.dumps(request, indent=1) + "\n", encoding="utf-8")
    shutil.copytree(tree, root / "checkout")
    return root


def ledgerlock_request(cls: str) -> dict:
    row = LEDGERLOCK_CLASSES[cls]
    defn = spec_def(row["spec"])
    scenario = json.loads(json.dumps(defn["scenario"]))
    if row.get("attrs"):
        scenario[-1]["attrs"] = row["attrs"]
    return {"subject": {"kind": "process_effect", "locator": defn["locator"]}, "stimulus": {"scenario": scenario},
            "observable": {**defn["observable"], "within_s": WINDOW}, "subject_absence": "REQUIRES_SUBJECT"}


def ledgerlock_calibrations(work: pathlib.Path) -> tuple[list[dict], list[str]]:
    """Per class: a positive fixture whose checkout is the reference, a negative one whose checkout is the class's
    mutant, both built under `work` from the frozen blobs; the frozen calibrate() on them (and on a non-contrasting
    pair, which must be rejected)."""
    from dataclasses import asdict
    from aisef2.probe import catalog, process_effect as pe
    from aisef2.probe.calibration import NotQualified, calibrate, calibration_env
    probe, registry, env = pe.ProcessEffectProbe(), catalog.registry(), calibration_env(sys.executable)
    records, problems = [], []
    for cls, row in LEDGERLOCK_CLASSES.items():
        request = ledgerlock_request(cls)
        base = work / f"calibration-{cls}"
        pos = _fixture(base / "positive", request, build_tree(None, base / "trees"))
        neg = _fixture(base / "negative", request, build_tree(row["mutant"], base / "trees"))
        try:
            rec = calibrate(probe, cls, pos, neg, env, time.time, registry=registry,
                            names=(f"{FIX_REL}/reference", f"{FIX_REL}/mutants/{row['mutant']}"))
        except NotQualified as e:
            problems.append(f"ledgerlock {cls}: {e}")
            continue
        rejected = True
        try:
            calibrate(probe, cls, neg, neg, env, time.time, registry=registry)
            rejected = False
            problems.append(f"ledgerlock {cls}: the non-contrasting pair (mutant, mutant) was not rejected")
        except NotQualified:
            pass
        records.append({**asdict(rec), "mutant": row["mutant"], "mutant_target": _mutant(row["mutant"])["target"],
                        "request": request, "why": row["why"], "non_contrasting_pair_rejected": rejected,
                        "positive_checkout": tree_identity(pos / "checkout"),
                        "negative_checkout": tree_identity(neg / "checkout")})
    return records, problems


def _mutant(mutant_id: str) -> dict:
    return next(x for x in _p0()._catalog() if x["id"] == mutant_id)


# --------------------------------------------------------------------------------------- the record

def class_table() -> dict:
    from aisef2.probe import process_effect as pe
    return {cls: {"quantifier": row["quantifier"], "domain": row["domain"], "enforcement": row["enforcement"],
                  "on_deadline": pe.ON_DEADLINE[cls].value,
                  "rows": [{"facts": facts, "verdict": verdict} for facts, verdict in row["rows"]]}
            for cls, row in pe.CLASS_TABLE.items()}


def falsifiability_table(work: pathlib.Path) -> dict:
    p0 = _p0()
    trees = {"reference": build_tree(None, work)}
    trees.update({m["id"]: build_tree(m["id"], work) for m in p0._catalog()})
    rows = [falsifiability(defn, trees) for defn in SPECS]
    rmap = json.loads((ROOT / FIX_REL / "REQUIREMENTS-MAP.json").read_text(encoding="utf-8"))
    observable = [r["id"] for r in rmap["requirements"] if r["kind"] in ("BEHAVIOUR", "STATIC")]
    covered = sorted({rid for r in rows if r["qualified"] for rid in r["requirements"]}, key=observable.index)
    refuted_by = {m["id"]: sorted(r["id"] for r in rows if m["id"] in r["refuted"]) for m in p0._catalog()}
    return {
        "mechanism": MECHANISM, "window_s": WINDOW, "approver": APPROVER,
        "approval_note": "the approvals are fixture approvals, for compilation only: these contracts are calibration "
                         "and falsifiability instruments over the reference, not a plan (DECISION-3: no LedgerLock "
                         "contract is approved by this package)",
        "trees": {name: tree_identity(tree) for name, tree in trees.items()},
        "specs": rows,
        "qualified": [r["id"] for r in rows if r["qualified"]],
        "not_qualified": [r["id"] for r in rows if not r["qualified"]],
        "families": sorted({r["family"] for r in rows}),
        "requirement_sections_covered": covered,
        "requirement_sections_not_covered": [rid for rid in observable if rid not in covered],
        "mutants_refuted_by": refuted_by,
        "gap_mutants_refuted_by_no_spec": [mid for mid, by in refuted_by.items() if not by],
        "gap_rule": "a mutant no spec refutes is a gap of the specs (or of the probe kind), listed, never a failure; a "
                    "spec that refutes no mutant is NOT QUALIFIED, listed, never removed",
    }


def run() -> dict:
    h = _harness()
    cli = h._cli()
    from aisef2.probe import process_effect as pe
    problems: list[str] = []
    small, found = small_calibrations()
    problems += found
    with tempfile.TemporaryDirectory(prefix="aisef2-p3-effect-cal-", ignore_cleanup_errors=True) as t:
        ledgerlock, found = ledgerlock_calibrations(pathlib.Path(t) / "calibrations")
        problems += found
        table = falsifiability_table(pathlib.Path(t) / "trees")
    for row in table["specs"]:
        problems += row["problems"]
    if len(table["families"]) < 6:
        problems.append(f"falsifiability: {len(table['families'])} requirement families, fewer than six")
    runs = {m: cli.owned_run(m) for m in TEST_MODULES}
    for m, r in runs.items():
        if r["status"] != "OK" or r["exit"] != 0 or r["residual"]:
            problems.append(f"{m}: status {r['status']} exit {r['exit']} residual {r['residual']}")
    outcomes = {k: v for k, v in cli.in_process("tests.v2.test_c2_effect_calibration").items()}
    cases = cli.rows_of(outcomes, CASES)
    for row, r in cases.items():
        if r["outcome"] != "PASS":
            problems.append(f"case {row}: {r['outcome']}")
    classes = class_table()
    static = h.static_checks()
    for name, found in static.items():
        if found:
            problems.append(f"{name}: {found}")
    mutation = h.mutation_summary()
    problems += [f"mutation: {p}" for p in mutation["problems"]]
    verdict_targets = {f: mutation.get("per_target", {}).get(f) for f in VERDICT_TARGETS}
    for f, t in verdict_targets.items():
        if not t or t["mutants"] != t["killed"]:
            problems.append(f"mutation: the verdict target {f} is not measured or not fully killed: {t}")
    mutation["verdict_targets"] = {"targets": verdict_targets, "note": VERDICT_KILL_NOTE}
    identities = h.identities()
    identities["package"] = PACKAGE
    harness_record = json.loads((ROOT / HARNESS_REL).read_text(encoding="utf-8")) \
        if (ROOT / HARNESS_REL).is_file() else {}
    same_digest = harness_record.get("identities", {}).get("probe", {}).get("digest") == pe.DIGEST
    if not same_digest:
        problems.append(f"{HARNESS_REL} binds another probe digest (or is missing)")
    return {
        "record": "AISEF V2 — WP-2.3.2 PROCESS EFFECT CALIBRATION (probe.process_effect: class calibrations over the "
                  "small fixtures and the LedgerLock reference, DECISION-1 declarations, SpecFalsifiabilityEvidence)",
        "work_package": PACKAGE,
        "rfc_sections": ["9.1", "9.1.1", "9.1.2", "9.2"],
        "rule": "a ProbeCapabilityCalibration exists only when the positive fixture is observed SATISFIED and the "
                "negative one REFUTED by the real probe (the frozen calibrate(), the observation class read from the "
                "catalog registry); a spec is falsifiable only when it is SATISFIED on the reference and REFUTED by "
                "at least one controlled mutant of it",
        "identities": identities,
        "harness_record": {"path": HARNESS_REL, "commit": harness_record.get("identities", {}).get("head"),
                           "same_probe_digest": same_digest},
        "platform": {"python": sys.version.split()[0], "platform": sys.platform},
        "calibrations": {"small_fixtures": small, "ledgerlock": ledgerlock},
        "fixtures": {cls: {side: {rel: h._identity(ROOT / FIXTURES_REL / cls / side / rel)
                                  for rel in ("request.json", "checkout/tally.py")}
                           for side in ("positive", "negative")} for cls in pe.CLASSES},
        "reference_fixture": {"path": FIX_REL, "requirements_sha256":
                              h._identity(ROOT / FIX_REL / "REQUIREMENTS.md")["sha256"],
                              "mutants_catalog_sha256": h._identity(ROOT / FIX_REL / "MUTANTS.json")["sha256"],
                              "requirements_map_sha256": h._identity(ROOT / FIX_REL / "REQUIREMENTS-MAP.json")["sha256"],
                              "frozen": "read only; every tree built in a temporary directory"},
        "class_table": classes,
        "decision_1": {"quantifiers": ["exhaustive_finite_domain", "bounded_witness_measurement",
                                       "unsupported_for_full_enforcement"],
                       "declared_per_class": {cls: row["quantifier"] for cls, row in classes.items()},
                       "declared_per_spec": {r["id"]: r["quantifier_semantics"] for r in table["specs"]},
                       "fault_step": pe.FAULT_WITNESS,
                       "enforcement": "PARTIAL for every class; no class claims FULL",
                       "rule": "a class measures the one declared scenario exhaustively; a spec whose fault step "
                               "witnesses a property quantified over every crash point declares "
                               "bounded_witness_measurement, and its verdict is never recorded as a proof of it"},
        "falsifiability": table,
        "tests": runs,
        "cases": cases,
        "mutation": mutation,
        "static": static,
        "problems": problems,
        "verdict": "CALIBRATED" if not problems else "NOT QUALIFIED",
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--bind-ci" in argv:
        cp = _harness().bind_ci(int(argv[argv.index("--bind-ci") + 1]), OUT_REL)
        for a in cp["ci"]["attempts"]:
            for r in a["jobs"]:
                print(f"attempt {a['attempt']}: {r['job']:32s} {r['conclusion']:8s} tests {r['tests_run']}")
        print(f"bound CI run {cp['ci']['run']} into {OUT_REL}")
        return 0
    if "--run" in argv:
        rec = run()
        for p in rec["problems"]:
            print("FAIL ", p)
        for c in rec["calibrations"]["small_fixtures"]:
            print(f"calibrated (small)      {c['observation_class']:17s} {c['probe_id']}@{c['probe_digest'][:12]}")
        for c in rec["calibrations"]["ledgerlock"]:
            print(f"calibrated (ledgerlock) {c['observation_class']:17s} negative {c['mutant']}")
        for r in rec["falsifiability"]["specs"]:
            print(f"{r['id']:13s} {r['status']:13s} reference {r['reference']:9s} refutes {r['refuted']}")
        print(f"not qualified: {rec['falsifiability']['not_qualified']}; gap mutants: "
              f"{rec['falsifiability']['gap_mutants_refuted_by_no_spec']}")
        for m, r in rec["tests"].items():
            print(f"{m}: Ran {r['ran']} {r['status']} exit {r['exit']} owned {r['owned_processes']}")
        if rec["problems"]:
            return 1
        (ROOT / OUT_REL).write_text(_harness().render(rec), encoding="utf-8")
        print(f"wrote {OUT_REL}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
