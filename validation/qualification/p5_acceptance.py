"""C2-P5 acceptance boundary (owner ruling 'AISEF V2 — CYCLE-2 OWNER RULING / C2-P5 ACCEPTED WITH EXPLICIT CONTRACT
INTERPRETATIONS / AUTHORIZE QP-2.6 ...', 2026-09-30).

    python -P validation/qualification/p5_acceptance.py --approve   # write P5-CONTRACT-APPROVALS.json (once; refuses if present)
    python -P validation/qualification/p5_acceptance.py --write     # verify, then write C2-P5-ACCEPTANCE.json (once)
    python -P validation/qualification/p5_acceptance.py --check     # re-derive everything but the guard runs; exit 1 on drift

**Real approvals.** One ContractApproval per retained contract, approver `OWNER` — the repository's established owner
identity (`"approver": "owner"` in the owner-approval records, `owner_identity_records()`) written in the kernel's
`human:` namespace. Each approval is content-addressed; the file carries an aggregate digest and binds the accepted
proposal. It is written once and never rewritten (`--approve` refuses when it exists; `check` compares every committed
version). The synthetic identity of the proposal never appears in it and is never passed to the admission here.

**Nothing semantic moves.** Every contract is re-created from the authoring aid's spec table and compiled under the real
approvals; its contract hash, spec id and semantic hash, every requirement hash, the plan hash and the proposal digest
must equal the accepted ones, and the P5 corpus must reproduce its sealed digests. The three interface rulings bind
the contracts that already encode them (found mechanically below); none of them edits a contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CYC = "closure-evidence/v2/cycle2"
APPROVALS_REL = f"{CYC}/P5-CONTRACT-APPROVALS.json"
OUT_REL = f"{CYC}/C2-P5-ACCEPTANCE.json"
HISTORY_REL = f"{CYC}/C2-P5-RUN-HISTORY.json"
PROPOSAL_REL = f"{CYC}/P5-PLAN-V2.2-PROPOSAL.json"
FALSIFIABILITY_REL = f"{CYC}/P5-FALSIFIABILITY.json"
AUDIT_REL = f"{CYC}/P5-CORRECTION-AUDIT.json"
OWNER = "human:owner"
AUTHORITY = ("owner ruling 'AISEF V2 — CYCLE-2 OWNER RULING / C2-P5 ACCEPTED WITH EXPLICIT CONTRACT INTERPRETATIONS / "
             "AUTHORIZE QP-2.6 AND AUTOMATIC DOWNSTREAM EXECUTION / MAXIMIZE SAFE PARALLELISM' (2026-09-30)")
#: what the owner accepted, exactly as reported
ACCEPTED = {
    "candidate": "3ac9b8c9f67fcf307ec34009d540e9094cea46bb",
    "execution": "8fd083b",
    "base": "0f779956f98f38abf4d4c33c6db4cadd819d8640",
    "proposal_digest": "856ed25dcf10df2b7c1c3e45c125ca0642a6f8aef6b913ae84bba13cdfd1e3f9",
    "plan_hash": "27b679d9513f3dc2f9b5da68a694a3ef1baff50f87eae9903721415a4670a669",
    "baseline": "136a68dc",
    "retained": 59, "qualified": 59, "not_qualified": 0, "reference_unsatisfied": 0, "without_witness": 0,
}
FROZEN_CYCLE1_PROBE = ("probe.python_callable", "1961e84d913edc687bdb52f6c6cd0f034e86f2d1dadd9e89fa76757a51dc35bf")
RULINGS = {
    "OR-IFACE-1": {"binding": "IB-LEDGER",
                   "ruling": "APPROVED WITH SCOPE LIMITATION: Ledger(path) with apply_batch, snapshot, verify and operation stimuli as "
                             "JSON arrays, for the exact PLAN-V2.2 BehaviorContracts of the LedgerLock Cycle-2 DEVELOPMENT_REGRESSION "
                             "workload",
                   "semantics": "an OPERATIONAL CONTRACT BINDING for this qualification/regression workload; NOT a statement that the "
                                "frozen prose requirements mandate this Python API shape; not framework-wide; not evidence that "
                                "arbitrary conforming LedgerLock implementations must expose it; its authority is only the exact "
                                "human-approved contract hashes"},
    "OR-IFACE-2": {"binding": "IB-ELEMENTS",
                   "ruling": "APPROVED WITH SCOPE LIMITATION: a delete's value slot is null; ts is an integer the caller supplies — "
                             "the canonical test stimulus representation of the exact approved benchmark contracts",
                   "semantics": "a stimulus convention of the approved benchmark contracts; no broader requirement claim; no new "
                                "framework semantics"},
    "OR-IFACE-3": {"binding": "IB-EMPTY",
                   "ruling": "APPROVED WITH SCOPE LIMITATION: an existing zero-byte ledger file is a fresh ledger state — the "
                             "canonical initial-state interpretation of the exact approved benchmark contracts",
                   "semantics": "binds the exact approved contract set; not framework-wide; no generalization claim; the frozen "
                                "requirements document is not altered"},
}
D3_APPROVED = {"AC-STORY-05-01-1": "S-D3-05-01-1", "AC-STORY-05-01-2": "S-D3-05-01-2"}
D3_ENGINEERING = ("AC-STORY-05-01-3", "AC-STORY-05-02-1", "AC-STORY-05-02-2", "AC-STORY-05-02-3")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _file(rel: str) -> dict:
    return {"path": rel, "sha256": _sha((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))}


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, encoding="utf-8", check=True).stdout.strip()


def _aid():
    from validation.qualification import p10_contracts
    return p10_contracts


def owner_identity_records() -> list[str]:
    """The owner-approval records that establish the identity: every closure record whose approver is 'owner'."""
    out = []
    for p in sorted((ROOT / "closure-evidence/v2").glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if any(isinstance(x, dict) and x.get("approver") == "owner" for x in _walk(doc)):
            out.append(p.relative_to(ROOT).as_posix())
    return out


# ------------------------------------------------------------------------------------------- contracts

def contracts() -> dict:
    """Every retained contract, re-created from the authoring aid's table exactly as `author` creates it (no approval)."""
    from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind
    from aisef2.product.contract import BehaviorContract, Subject
    aid = _aid()
    out = {}
    for sid, t in aid.SPECS.items():
        c = BehaviorContract.create(id=f"BC-V22-{sid}", requirement_ids=(t["requirement"],),
                                    subject=Subject(SubjectKind(t["kind"]), t["locator"]), stimulus=t["stimulus"],
                                    observable=t["observable"], polarity=Polarity[t.get("polarity", "MUST_HOLD")],
                                    subject_absence=SubjectAbsence[t["absence"]], rationale=t["measured"])
        out[sid] = c
    return out


def approval_fields(a) -> dict:
    return {"requirement_id": a.requirement_id, "requirement_hash": a.requirement_hash, "contract_id": a.contract_id,
            "contract_hash": a.contract_hash, "approver": a.approver, "approved_at": a.approved_at,
            "model_reviews": list(a.model_reviews)}


def approve() -> dict:
    """The real approvals, once: one per retained contract, bound to the accepted proposal."""
    from aisef2.product.approval import ContractApproval
    if (ROOT / APPROVALS_REL).exists():
        raise SystemExit(f"refused: {APPROVALS_REL} exists and is immutable")
    reqs = _aid().requirements()
    at = float(int(time.time()))
    rows = []
    for sid, c in sorted(contracts().items(), key=lambda kv: kv[1].id):
        (rid,) = c.requirement_ids
        a = ContractApproval(rid, reqs[rid].requirement_hash, c.id, c.contract_hash, OWNER, at, ())
        f = approval_fields(a)
        rows.append({**f, "spec_id": sid, "approval_digest": _sha(_canon(f))})
    body = {
        "record": "AISEF V2 — C2-P5 CONTRACT APPROVALS (real, human owner) for the accepted LedgerLock PLAN-V2.2",
        "authority": AUTHORITY,
        "approver": OWNER,
        "approver_identity": {"established_by": owner_identity_records(), "field": "approver", "value": "owner",
                              "namespace": "human: (aisef2/product/approval.py HUMAN_PREFIX)",
                              "rule": "the repository's established owner identity, reused; no new identity invented"},
        "approved_at": at, "approved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at)),
        "approved_at_rule": "the time this ruling was recorded into the repository; the ruling itself is dated 2026-09-30",
        "binds": {"proposal_digest": ACCEPTED["proposal_digest"], "plan_hash": ACCEPTED["plan_hash"],
                  "baseline": ACCEPTED["baseline"], "proposal_record": _file(PROPOSAL_REL), "candidate": ACCEPTED["candidate"]},
        "model_reviews": [],
        "advisory_only": {"record": AUDIT_REL, "rule": "a model review is advisory evidence only and appears in no approval"},
        "approval_digest_rule": "sha256 of the canonical JSON (sorted keys, no whitespace) of the seven ContractApproval fields",
        "approvals": rows,
        "count": len(rows),
        "aggregate_digest": _sha(_canon([r["approval_digest"] for r in rows])),
        "immutability": "written once; never rewritten; every committed version must equal the first (p5_acceptance.check)",
    }
    (ROOT / APPROVALS_REL).write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return body


def approvals_problems(doc: dict) -> list[str]:
    out = []
    digests = []
    for r in doc["approvals"]:
        f = {k: r[k] for k in ("requirement_id", "requirement_hash", "contract_id", "contract_hash", "approver", "approved_at",
                               "model_reviews")}
        if _sha(_canon(f)) != r["approval_digest"]:
            out.append(f"{r['contract_id']}: approval digest does not bind its fields")
        if r["approver"] != OWNER:
            out.append(f"{r['contract_id']}: approver {r['approver']!r} is not {OWNER}")
        digests.append(r["approval_digest"])
    if _sha(_canon(digests)) != doc["aggregate_digest"]:
        out.append("aggregate digest does not bind the approvals")
    if doc["count"] != len(doc["approvals"]):
        out.append("count differs from the approvals")
    text = json.dumps(doc)
    if _aid().SYNTHETIC_APPROVER in text or "c2-p5-proposal-check" in text:
        out.append("a synthetic identity appears in the approvals")
    return out


def load_approvals() -> tuple:
    """The persisted real approvals as kernel objects, refused unless every digest binds."""
    from aisef2.product.approval import ContractApproval
    doc = json.loads((ROOT / APPROVALS_REL).read_text(encoding="utf-8"))
    bad = approvals_problems(doc)
    if bad:
        raise SystemExit("refused: " + "; ".join(bad))
    return tuple(ContractApproval(r["requirement_id"], r["requirement_hash"], r["contract_id"], r["contract_hash"], r["approver"],
                                  r["approved_at"], tuple(r["model_reviews"])) for r in doc["approvals"])


def committed_versions_identical(rel: str) -> dict:
    revs = [r for r in _git("log", "--format=%H", "--", rel).splitlines() if r]
    blobs = sorted({_git("rev-parse", f"{r}:{rel}") for r in revs})
    return {"commits": len(revs), "distinct_blobs": blobs, "identical": len(blobs) <= 1}


# ------------------------------------------------------------------------------------------- the rulings

def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        yield o
        for v in o:
            yield from _walk(v)


def _ops(stimulus) -> list[list]:
    return [x for x in _walk(stimulus) if isinstance(x, list) and len(x) == 5 and x[0] in ("put", "delete")
            and isinstance(x[1], str) and isinstance(x[3], str)]


def ruling_bindings(cs: dict) -> dict:
    """The contracts each ruling binds, found from their content (never from the aid's prose)."""
    from aisef2.product.contract import plain
    ledger, elements, empty = [], [], []
    for sid, c in sorted(cs.items()):
        stim = plain(c.stimulus)
        steps = stim.get("scenario", []) if isinstance(stim, dict) else []
        if c.subject.kind.value == "process_effect" and c.subject.locator.endswith(":Ledger") \
                and any(s.get("step") == "construct" for s in steps):
            ledger.append(sid)
        ops = _ops(stim)
        if ops and all(isinstance(o[4], int) and not isinstance(o[4], bool) for o in ops):
            elements.append(sid)
        if any(isinstance(x, dict) and x.get("bytes_hex") == "" for x in _walk(stim)) \
                or any(isinstance(x, dict) and x.get("bytes_hex") == "" for x in _walk(plain(c.observable))):
            empty.append(sid)
    deletes = [sid for sid, c in sorted(cs.items()) if any(o[0] == "delete" and o[2] is None for o in _ops(plain(c.stimulus)))]
    return {"OR-IFACE-1": ledger, "OR-IFACE-2": elements, "OR-IFACE-2:delete_value_null": deletes, "OR-IFACE-3": empty}


# ------------------------------------------------------------------------------------------- verification

#: The one field of the proposal record that names where it was authored rather than what it says: the kernel tree.
#: The owner authorized a kernel change after the acceptance (ruling 2026-09-30 B, C2-ORCHESTRATION-CONFORMANCE-REPAIR)
#: and, asked about this field (2026-10-01), chose the narrow provenance rule below.
PROVENANCE_PATH = "identities.aisef2_tree"


def _paths(a, b, at: str = "") -> list[str]:
    """The dotted paths where two JSON values differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [p for k in sorted(set(a) | set(b)) for p in _paths(a.get(k), b.get(k), f"{at}.{k}" if at else k)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b, strict=True)) for p in _paths(x, y, f"{at}[{i}]")]
    return [] if a == b else [at]


def proposal_currency(recomputed: dict, committed: dict, accepted_kernel: str, head_kernel: str) -> dict:
    """Is the committed proposal what the authoring aid derives from this tree? Fail closed: current when the two are
    equal, or when they differ ONLY in the authoring-kernel provenance and the committed value is exactly the accepted
    candidate's kernel while the derived one is this tree's — every semantic field (specs, contracts, semantic hashes,
    plan, compiler, admission engine, catalog, requirements, digest) still re-derives identically."""
    diff = _paths(recomputed, committed)
    tree = lambda d: (d.get("identities") or {}).get("aisef2_tree")   # noqa: E731
    provenance_only = diff == [PROVENANCE_PATH] and tree(committed) == accepted_kernel and tree(recomputed) == head_kernel
    return {"differing_paths": diff, "committed_kernel": tree(committed), "derived_kernel": tree(recomputed),
            "accepted_kernel": accepted_kernel, "provenance_only": provenance_only, "current": not diff or provenance_only,
            "rule": "the proposal names the kernel it was authored on; a later authorized kernel changes that field only — "
                    "tolerated when it is the one differing path and the committed value is the accepted candidate's kernel"}


def current_proposal_currency() -> dict:
    """`proposal_currency` of the committed proposal against the authoring aid on this tree."""
    return proposal_currency(_aid().record(), json.loads((ROOT / PROPOSAL_REL).read_text(encoding="utf-8")),
                             _git("rev-parse", f"{ACCEPTED['candidate']}:aisef2"), _git("rev-parse", "HEAD:aisef2"))


def verify(run_guards: bool) -> dict:
    """Everything the acceptance binds, re-derived on this tree; `run_guards` also runs the five guard commands."""
    from aisef2.plan import static_admission as sa
    from aisef2.probe import catalog
    from aisef2.probe import python_callable as pc
    from aisef2.product.compiler import ProbeRef, compile_spec
    from aisef2.product.contract import plain
    from validation.qualification import p5_falsifiability as pf
    aid = _aid()
    problems: list[str] = []
    prop = json.loads((ROOT / PROPOSAL_REL).read_text(encoding="utf-8"))
    accepted_blob = _git("rev-parse", f"{ACCEPTED['candidate']}:{PROPOSAL_REL}")
    now_blob = _git("rev-parse", f"HEAD:{PROPOSAL_REL}") if _git("ls-files", PROPOSAL_REL) else None
    reqs = aid.requirements()
    real = load_approvals()
    cs = contracts()
    refs = {k: ProbeRef(e.probe_id, e.probe_digest) for k, e in catalog.active().items()}
    specs, rows = {}, []
    for s in prop["specs"]:
        sid = s["spec_id"]
        c = cs[sid]
        spec = compile_spec(c, requirements=reqs, approvals=real, probes=refs)
        specs[spec.id] = spec
        row = {"spec_id": sid, "contract_id": c.id, "contract_hash": c.contract_hash, "spec_hash_id": spec.id,
               "semantic_hash": spec.semantic_hash, "probe_id": spec.probe_id, "probe_digest": spec.probe_digest,
               "equal_to_accepted": (c.id, c.contract_hash, spec.id, spec.semantic_hash, spec.probe_id, spec.probe_digest)
               == (s["contract_id"], s["contract_hash"], s["spec_hash_id"], s["semantic_hash"], s["probe_id"], s["probe_digest"])}
        rows.append(row)
        if not row["equal_to_accepted"]:
            problems.append(f"{sid}: a hash differs from the accepted proposal")
    req_rows = {rid: {"hash": r.requirement_hash, "accepted": prop["requirements"][rid]["hash"],
                      "equal": r.requirement_hash == prop["requirements"][rid]["hash"]} for rid, r in reqs.items()}
    problems += [f"{rid}: requirement hash differs" for rid, v in req_rows.items() if not v["equal"]]
    if set(reqs) != set(prop["requirements"]):
        problems.append("the cited requirement set differs")
    # the plan: the authoring aid's obligations; every spec id it binds is the one compiled above under the real approvals
    b = aid.build()
    plan = b["plan"]
    plan_ok = plan.plan_hash == ACCEPTED["plan_hash"] == prop["plan"]["plan_hash"] and \
        {o.product_proof_spec_id for o in plan.obligations} <= set(specs)
    if not plan_ok:
        problems.append("the plan hash or its spec ids differ from the accepted plan")
    recomputed = aid.record()
    digest_ok = recomputed["proposal_digest"] == ACCEPTED["proposal_digest"] == prop["proposal_digest"]
    if not digest_ok:
        problems.append("the proposal digest differs")
    currency = proposal_currency(recomputed, prop, _git("rev-parse", f"{ACCEPTED['candidate']}:aisef2"), _git("rev-parse", "HEAD:aisef2"))
    record_current = currency["current"]
    if not record_current:
        problems.append(f"{PROPOSAL_REL} is not what the authoring aid derives from this tree")
    if now_blob is not None and now_blob != accepted_blob:
        problems.append(f"{PROPOSAL_REL} changed since the accepted candidate")
    corpus = {"problems": pf.corpus_problems(), "corpus_sha256": pf.corpus()["corpus_sha256"], "file": _file(pf.MUTANTS_REL)}
    problems += [f"P5 corpus: {p}" for p in corpus["problems"]]
    fals = json.loads((ROOT / FALSIFIABILITY_REL).read_text(encoding="utf-8"))
    qualified = sum(1 for r in fals["specs"] if r.get("status") == "QUALIFIED")
    fals_ok = (len(fals["specs"]), qualified) == (ACCEPTED["retained"], ACCEPTED["qualified"]) and \
        _git("rev-parse", f"{ACCEPTED['candidate']}:{FALSIFIABILITY_REL}") == _git("rev-parse", f"HEAD:{FALSIFIABILITY_REL}")
    if not fals_ok:
        problems.append("the P5 falsifiability record is not the accepted one")
    # the approvals: one per retained contract, binding each current hash; the admission under them alone
    by_contract = {a.contract_id: a for a in real}
    if set(by_contract) != {c.id for c in cs.values()} or len(real) != ACCEPTED["retained"]:
        problems.append("the approvals are not exactly one per retained contract")
    stale = [a.contract_id for a in real if (a.requirement_hash, a.contract_hash) !=
             (reqs[a.requirement_id].requirement_hash, cs[a.contract_id[len("BC-V22-"):]].contract_hash)]
    problems += [f"{c}: the approval does not bind the current hashes" for c in stale]
    cals = aid.calibrations()
    catalogue, registry = catalog.catalogue(), catalog.registry()
    contracts_by_id = {c.id: c for c in cs.values()}
    engine = sa.StaticPlanAdmissionEngine()
    admitted = engine.admit(plan, sa.AdmissionInputs(reqs, contracts_by_id, real, specs, catalogue, cals, registry))
    dropped = engine.admit(plan, sa.AdmissionInputs(reqs, contracts_by_id, real[1:], specs, catalogue, cals, registry))
    bare = engine.admit(plan, sa.AdmissionInputs(reqs, contracts_by_id, (), specs, catalogue, cals, registry))
    synthetic_passed = any(a.approver == aid.SYNTHETIC_APPROVER for a in real)
    passed = sum(1 for c in admitted.checks if c.passed)
    if not admitted.admitted or passed != 9 or synthetic_passed:
        problems.append(f"not admitted 9/9 under the real approvals alone ({passed}/9)")
    if dropped.admitted or bare.admitted:
        problems.append("admitted with an approval missing: the approval gate did not hold")
    # the rulings: bound to contracts that already encode them — no contract is edited
    bindings = ruling_bindings(cs)
    expected_empty = sorted(s for s in aid.INTERFACE_BINDINGS["IB-EMPTY"]["gap"].split("(")[-1].split(")")[0].replace(",", " ").split()
                            if s.startswith("S-"))
    rulings = {k: {**v, "interface_binding_as_proposed": aid.INTERFACE_BINDINGS[v["binding"]],
                   "contracts": [{"spec_id": s, "contract_id": cs[s].id, "contract_hash": cs[s].contract_hash} for s in bindings[k]],
                   "count": len(bindings[k]), "semantic_edit_required": False} for k, v in RULINGS.items()}
    rulings["OR-IFACE-2"]["delete_value_null_contracts"] = bindings["OR-IFACE-2:delete_value_null"]
    rulings["OR-IFACE-3"]["as_named_by_the_proposal"] = expected_empty
    if not all(bindings[k] for k in RULINGS):
        problems.append("a ruling binds no contract")
    # disclosed, not a semantic change: the proposal's IB-EMPTY prose named S-5-a among the zero-byte specs, but S-5-a (like
    # every process_effect contract) constructs Ledger(<ws>/l.jsonl) over a path holding no file — a fresh start under
    # the Ledger(path) binding of OR-IFACE-1, encoded in its exact approved hash; no contract is edited
    rulings["OR-IFACE-3"]["prose_vs_content"] = {
        "named_by_the_proposal_prose": expected_empty, "zero_byte_file_in_the_contract": sorted(bindings["OR-IFACE-3"]),
        "named_but_no_zero_byte_file": sorted(set(expected_empty) - set(bindings["OR-IFACE-3"])),
        "zero_byte_file_but_not_named": sorted(set(bindings["OR-IFACE-3"]) - set(expected_empty)),
        "no_file_start_contracts": [s for s in bindings["OR-IFACE-1"]
                                    if not any(isinstance(x, dict) and "bytes_hex" in x for x in _walk(plain(cs[s].stimulus)))],
        "reading": "the zero-byte ruling binds the contracts whose content holds a zero-byte ledger file; a process_effect contract "
                   "that constructs Ledger(path) over a path with no file starts fresh under OR-IFACE-1's Ledger(path) binding, "
                   "as its exact approved hash encodes; the prose inaccuracy is disclosed, no contract changes"}
    # Cycle-1 compatibility: the frozen probe resolvable at its digest, inactive for its kind
    entry = next(e for e in catalog.CATALOG if e.probe_id == FROZEN_CYCLE1_PROBE[0])
    drift = {"probe_id": entry.probe_id, "catalog_digest": entry.probe_digest, "module_digest": pc.DIGEST, "active": entry.active,
             "active_for_kind": catalog.active()[entry.subject_kind].probe_id, "frozen": FROZEN_CYCLE1_PROBE[1]}
    drift["ok"] = entry.probe_digest == pc.DIGEST == FROZEN_CYCLE1_PROBE[1] and not entry.active \
        and drift["active_for_kind"] == "probe.python_callable_v2"
    if not drift["ok"]:
        problems.append(f"Cycle-1 drift: {drift}")
    out = {
        "identities": {"specs": rows, "requirements": req_rows, "plan_hash": plan.plan_hash, "plan_ok": plan_ok,
                       "proposal_digest": recomputed["proposal_digest"], "proposal_digest_ok": digest_ok,
                       "proposal_record_current": record_current, "proposal_record_blob": {"accepted": accepted_blob, "head": now_blob},
                       "p5_corpus": corpus, "p5_falsifiability": {"record": _file(FALSIFIABILITY_REL), "retained": len(fals["specs"]),
                                                                   "qualified": qualified, "verdict": fals.get("verdict"), "ok": fals_ok},
                       "catalog": {e.probe_id: {"digest": e.probe_digest, "kind": e.subject_kind.value, "active": e.active}
                                   for e in catalog.CATALOG}},
        "semantic_change": "NONE" if not [p for p in problems if "differ" in p or "changed" in p] else "CHANGED",
        "rulings": rulings,
        "admission": {"engine_digest": admitted.engine_digest, "admitted": admitted.admitted, "checks_passed": passed,
                      "result_digest": admitted.result_digest,
                      "checks": [{"number": c.number, "name": c.name, "passed": c.passed, "problems": list(c.problems[:3])}
                                 for c in admitted.checks],
                      "synthetic_approval_used": synthetic_passed,
                      "approvals_given": [approval_fields(a) | {"approval_digest": _sha(_canon(approval_fields(a)))} for a in real],
                      "one_approval_removed": {"admitted": dropped.admitted,
                                               "failed_checks": [c.number for c in dropped.checks if not c.passed]},
                      "no_approvals": {"admitted": bare.admitted, "failed_checks": [c.number for c in bare.checks if not c.passed]},
                      "plan_structure": "the authoring aid's obligations (p10_contracts.build); its in-memory synthetic compilation "
                                        "never reaches this admission, which receives exactly the persisted approvals"},
        "cycle1_drift": drift,
        "proposal_kernel_provenance": currency,
        "approvals_file": {**_file(APPROVALS_REL), "committed_versions": committed_versions_identical(APPROVALS_REL)},
        "problems": problems,
    }
    if not out["approvals_file"]["committed_versions"]["identical"]:
        problems.append(f"{APPROVALS_REL} was rewritten")
    if run_guards:
        out["guards"] = guards()
        problems += [f"guard {k}: exit {v['exit']}" for k, v in out["guards"].items() if v["exit"] != 0]
    return out


GUARDS = {"cycle2_baseline": ["validation/v2/cycle2_baseline.py", "--check"],
          "checker_calibration": ["validation/v2/checker_calibration.py", "--check"],
          "f1_f11": ["validation/v2/freeze_conformance.py", "--check"],
          "v1_guard": ["validation/v2/v1_evidence_guard.py", "--check"],
          "run_history": ["validation/v2/run_history.py", "check"]}


def guards() -> dict:
    out = {}
    for name, argv in GUARDS.items():
        t = time.monotonic()
        r = subprocess.run([sys.executable, "-P", *argv], cwd=ROOT, capture_output=True, encoding="utf-8")
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        out[name] = {"command": "python -P " + " ".join(argv), "exit": r.returncode, "tail": tail,
                     "seconds": round(time.monotonic() - t, 1)}
    return out


def history() -> dict:
    doc = json.loads((ROOT / HISTORY_REL).read_text(encoding="utf-8"))
    e = doc["entries"]
    return {"path": HISTORY_REL, "total_attempts": len(e), "sha256": _file(HISTORY_REL)["sha256"],
            "by_commit": {c: sum(1 for x in e if x["commit"] == c) for c in dict.fromkeys(x["commit"] for x in e)},
            "failed": [{k: x.get(k) for k in ("seq", "commit", "where", "job", "classification", "gate_effect")} for x in e if x["result"] == "FAIL"],
            "includes_the_accepted_candidate": any(x["commit"] == ACCEPTED["candidate"] for x in e),
            "rule": "closed at this count by this acceptance; the acceptance commit's own attempts open C2-P6-RUN-HISTORY.json; "
                    "nothing rewritten"}


def record() -> dict:
    v = verify(run_guards=True)
    aid = _aid()
    prop = json.loads((ROOT / PROPOSAL_REL).read_text(encoding="utf-8"))
    approvals = json.loads((ROOT / APPROVALS_REL).read_text(encoding="utf-8"))
    clauses = prop["clauses"]
    body = {
        "record": "AISEF V2 — CYCLE-2 C2-P5 OWNER ACCEPTANCE (LedgerLock PLAN-V2.2, requirements-grounded)",
        "id": "AISEF-V2-CYCLE2-C2-P5-ACCEPTANCE",
        "authority": AUTHORITY,
        "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "accepted": ACCEPTED,
        "owner_identity": {"approver": OWNER, "established_by": approvals["approver_identity"]["established_by"]},
        "contract_approvals": {"record": _file(APPROVALS_REL), "count": approvals["count"],
                               "aggregate_digest": approvals["aggregate_digest"], "approved_at_utc": approvals["approved_at_utc"],
                               "synthetic_identity_persisted": False,
                               "synthetic_identity": aid.SYNTHETIC_APPROVER,
                               "synthetic_rule": "NON-AUTHORITATIVE TEST FIXTURE DATA of the proposal; never persisted as approval, never "
                                                 "an approver of a production ContractApproval, never passed to the acceptance admission"},
        "verification": v,
        "unsupported_clauses": [{"id": c["id"], "clause": c["clause"], "class": c["class"], "reason": c.get("reason")}
                                for c in clauses if c["class"] == aid.U],
        "unsupported_rule": "remain UNSUPPORTED_FOR_FULL_ENFORCEMENT; approval of PLAN-V2.2 turns none of them into a verified "
                            "clause; never reported VERIFIED, FULLY_PROVED or FULL_ENFORCEMENT",
        "engineering_test_clauses": [{"id": c["id"], "class": c["class"], "reason": c.get("reason")} for c in clauses if c["class"] == aid.E],
        "requirement_ambiguities": prop["requirement_risks"],
        "ambiguity_rule": "kept explicit; no missing requirement semantics invented during qualification; the frozen requirements "
                          "are not edited; no agent/model judgment becomes ProductProof truth",
        "decision_3": {"approved_exact_mappings": {ac: {"spec_id": s, **next({"contract_id": r["contract_id"], "contract_hash": r["contract_hash"],
                                                                              "semantic_hash": r["semantic_hash"]}
                                                                             for r in v["identities"]["specs"] if r["spec_id"] == s)}
                                                   for ac, s in D3_APPROVED.items()},
                       "engineering_test_requirement_outside_productproof": list(D3_ENGINEERING),
                       "R-11": "ENGINEERING_TEST_REQUIREMENT / NOT_PRODUCTPROOF — the classification does not mean the requirement is "
                               "product-proved"},
        "attempt_history": history(),
        "boundary": "C2-P5 is CLOSED. No later edit of the approved BehaviorContracts, the approved ProductProofSpecs, PLAN-V2.2, this "
                    "acceptance, the P5 falsifiability corpus or the closed C2-P5 history without a new explicit candidate that "
                    "invalidates downstream evidence",
        "authorized_successors": "QP-2.6 (Q0-Q3 on one exact Cycle-2 candidate); after it is GREEN, LANE-Q (QP-2.7 -> QP-2.8 -> QP-2.9) "
                                 "in parallel with LANE-X (WP-2.10.1 -> WP-2.10.2)",
    }
    body["verdict"] = "C2-P5 ACCEPTED BY THE OWNER — ACCEPTANCE BOUNDARY RECORDED" if not v["problems"] else "PROBLEMS"
    return json.loads(json.dumps(body))


def check() -> list[str]:
    """Re-derive the acceptance on this tree (the guard runs are recorded, not repeated here)."""
    doc = json.loads((ROOT / OUT_REL).read_text(encoding="utf-8"))
    v = verify(run_guards=False)
    out = list(v["problems"])
    for k in ("identities", "semantic_change", "rulings", "admission", "cycle1_drift"):
        if json.loads(json.dumps(v[k])) != doc["verification"][k]:
            out.append(f"{OUT_REL} is stale in verification.{k}")
    h = json.loads((ROOT / HISTORY_REL).read_text(encoding="utf-8"))["entries"]
    if len(h) != doc["attempt_history"]["total_attempts"]:
        out.append("the closed C2-P5 history changed")
    if doc["verdict"] != "C2-P5 ACCEPTED BY THE OWNER — ACCEPTANCE BOUNDARY RECORDED":
        out.append("the acceptance verdict is not recorded")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.approve:
        doc = approve()
        print(f"{APPROVALS_REL}: {doc['count']} approvals by {doc['approver']}; aggregate {doc['aggregate_digest']}")
        return 0
    if a.write:
        if (ROOT / OUT_REL).exists():
            raise SystemExit(f"refused: {OUT_REL} exists")
        rec = record()
        if rec["verification"]["problems"]:
            print("\n".join(rec["verification"]["problems"]))
            return 1
        (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"{OUT_REL}: {rec['verdict']}")
        return 0
    found = check()
    print("\n".join(found) if found else "PASS")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
