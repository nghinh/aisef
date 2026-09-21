"""WP-0.3 — F1–F11 conformance: every frozen item reports a definite state, and nothing passes by absence.

The **reference** for every check is extracted from the approved RFC itself, not transcribed. States:

* **PASS** — the implementation exists and equals the RFC reference.
* **FAIL** — it differs; or the RFC reference cannot be extracted; or a sub-check owned by a package in a phase
  already reached has no implementation (the ratchet); or a later-phase implementation has appeared before a real
  comparison exists for it (fail-closed: presence without evaluation is never a pass).
* **PENDING** — the shape belongs to a later phase and its implementation does not exist yet. A PENDING result
  always names the package that will implement it, and is never interpreted as PASS.

An item is PASS only if every sub-check is PASS; FAIL if any is FAIL; otherwise PENDING.

    python -P validation/v2/freeze_conformance.py            # write closure-evidence/v2/F-CONFORMANCE.json
    python -P validation/v2/freeze_conformance.py --check    # fail on FAIL, on a broken ratchet, or on staleness
"""

from __future__ import annotations

import ast
import importlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RFC_REL = "docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md"
MANIFEST_REL = "docs/implementation/v2/cycle1-manifest.json"
OUT_REL = "closure-evidence/v2/F-CONFORMANCE.json"
NORMATIVE_MARK = "## 1. Executive architecture decision"
FROZEN_IDS = [f"F{i}" for i in range(1, 12)]

#: The phase the Cycle-1 implementation has reached. Every sub-check owned by a package in this phase or an earlier
#: one must PASS. Advanced by one reviewed line at each phase boundary.
# ponytail: a constant, not a progress database; move it into a progress record if phases start overlapping.
CURRENT_PHASE = "P0"

PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING"


# --------------------------------------------------------------------------------------- RFC reference extraction

class RFC:
    def __init__(self, text: str):
        self.body = text[text.index(NORMATIVE_MARK):] if NORMATIVE_MARK in text else ""
        self.enums: dict[str, list[str]] = {}
        self.dataclasses: dict[str, list[str]] = {}
        self.protocols: dict[str, list[str]] = {}
        for block in re.findall(r"```python\n(.*?)```", self.body, re.S):
            try:
                tree = ast.parse(block)
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                if not isinstance(n, ast.ClassDef):
                    continue
                bases = {getattr(b, "id", "") for b in n.bases}
                decos = {getattr(d, "id", "") for d in n.decorator_list} | \
                        {getattr(getattr(d, "func", None), "id", "") for d in n.decorator_list}
                if "Enum" in bases:
                    self.enums[n.name] = [t.id for s in n.body if isinstance(s, ast.Assign)
                                          for t in s.targets if isinstance(t, ast.Name)]
                elif "Protocol" in bases:
                    self.protocols[n.name] = [s.target.id if isinstance(s, ast.AnnAssign) else s.name
                                              for s in n.body if isinstance(s, ast.AnnAssign | ast.FunctionDef)]
                elif "dataclass" in decos:
                    self.dataclasses[n.name] = [s.target.id for s in n.body if isinstance(s, ast.AnnAssign)]

    def section(self, begin: str, end: str) -> str:
        if begin not in self.body or end not in self.body:
            return ""
        i = self.body.index(begin)
        return self.body[i:self.body.index(end, i)]

    def event_types(self) -> list[str]:
        s = self.section("### 20.1 Vocabulary", "### 20.2")
        return list(dict.fromkeys(re.findall(r"`([a-z]+/[a-z-]+)`", s)))

    def invariants(self) -> dict[str, str]:
        s = self.section("## 4. Top-level invariants", "## 5. Planes")
        return dict(re.findall(r"^\| \*\*([IVX]+)\*\* \| \*\*([^*]+?)\.\*\*", s, re.M))

    def control_projections(self) -> list[str]:
        s = self.section("## 21. Control-critical projections", "## 22.")
        line = next((ln for ln in s.splitlines() if "story state" in ln), "")
        return [re.sub(r"^\d+\.\s*", "", p.strip()).replace(" ", "_") for p in line.split("·") if p.strip()]

    def subject_kinds(self) -> list[str]:
        m = re.search(r"kind: Literal\[(.*?)\]", self.body)
        return re.findall(r'"([a-z_]+)"', m.group(1)) if m else []

    def cited_identities(self) -> list[str]:
        s = self.section("### 5.1 The four cited identities", "## 6.")
        return [" / ".join(re.findall(r"`([a-z_]+)`", row.split("|")[1]))
                for row in s.splitlines() if row.startswith("| `")]

    def lifetime_order(self) -> dict[str, list[str]]:
        s = self.section("### 18.1 Lifetime order", "## 19.")
        out = {}
        for key, marker in (("begin", "**Begin order (normative):**"),
                            ("shutdown", "**Successful shutdown order (normative):**")):
            if marker in s:
                tail = s[s.index(marker) + len(marker):]
                steps = []
                for ln in tail.splitlines():
                    m = re.match(r"^(\d+)\. (.+)$", ln.strip())
                    if m:
                        steps.append(m.group(2).rstrip(";."))
                    elif steps and ln.strip():
                        break
                out[key] = steps
        return out


# --------------------------------------------------------------------------------------- code side

def code_vocabularies() -> dict | None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        enums = importlib.import_module("aisef2.arch.enums")
    except ModuleNotFoundError:
        return None
    return {name: ([m.name for m in e], [m.value for m in e]) for name, (e, _i, _s) in enums.VOCABULARIES.items()} | \
        {"__invariant_titles__": ([], [f"{k.value}:{v}" for k, v in enums.INVARIANT_TITLE.items()])}


def symbol_present(module: str, attr: str | None) -> bool:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError:
        return False
    return attr is None or hasattr(mod, attr)


# --------------------------------------------------------------------------------------- sub-checks

def _phase_of(package: str, manifest: dict) -> str:
    return next(p["phase"] for p in manifest["work_packages"] if p["id"] == package)


def _reached(phase: str, manifest: dict) -> bool:
    order = [ph["id"] for ph in manifest["phases"]]
    return order.index(phase) <= order.index(CURRENT_PHASE)


def _vocab(name: str, rfc_members: list[str], code, *, by_value: bool = False) -> dict:
    if not rfc_members:
        return {"state": FAIL, "detail": f"RFC reference for {name} could not be extracted"}
    if code is None or name not in code:
        return {"state": None, "detail": f"{name} absent from aisef2.arch.enums"}
    got = code[name][1] if by_value else code[name][0]
    if got != rfc_members:
        missing = [m for m in rfc_members if m not in got]
        extra = [m for m in got if m not in rfc_members]
        return {"state": FAIL, "detail": f"{name} differs from the RFC", "missing": missing, "extra": extra,
                "order_differs": not missing and not extra}
    return {"state": PASS, "detail": f"{name} equals the RFC ({len(got)} members)"}


def _shape(module: str, attr: str | None, reference) -> dict:
    if not reference:
        return {"state": FAIL, "detail": "RFC reference for this shape could not be extracted"}
    if not symbol_present(module, attr):
        return {"state": None, "detail": f"{module}{'.' + attr if attr else ''} not implemented", "rfc_reference": reference}
    return {"state": FAIL, "rfc_reference": reference,
            "detail": f"{module}{'.' + attr if attr else ''} exists but no conformance comparison has been written for "
                      "it — presence without evaluation is never a pass"}


def subchecks(rfc: RFC, code) -> list[dict]:
    e = rfc.enums
    V = _vocab
    S = []

    def add(item, sid, owner, result):
        S.append({"item": item, "id": sid, "implemented_by": owner, **result})

    add("F1", "F1.event_vocabulary", "WP-0.2", V("EventType", rfc.event_types(), code, by_value=True))
    for n in ("Vacuity", "Relevance", "AdequacyOutcome", "TestExecutionStatus", "TestOutcome", "TestSelection"):
        add("F1", f"F1.payload_enum.{n}", "WP-0.2", V(n, e.get(n, []), code))
    add("F1", "F1.event_envelope", "WP-3.1", _shape("aisef2.journal.event", "Event", rfc.dataclasses.get("Event")))
    for n in ("ProbeExecutionStatus", "BehaviorVerdict", "ContractSatisfaction"):
        add("F2", f"F2.enum.{n}", "WP-0.2", V(n, e.get(n, []), code))
    add("F2", "F2.contract_satisfaction_derivation", "WP-1.3",
        _shape("aisef2.product.outcome", "contract_satisfaction", ["behavior_verdict == candidate_expectation"]))
    add("F2", "F2.owner_routing_table", "WP-1.4",
        _shape("aisef2.control.routing", "route", ["six legal (status, verdict) states -> owner"]))
    add("F3", "F3.owner_set", "WP-0.2", V("Owner", e.get("Owner", []), code))
    for n in ("Polarity", "SubjectAbsence"):
        add("F4", f"F4.enum.{n}", "WP-0.2", V(n, e.get(n, []), code))
    add("F4", "F4.subject_kinds", "WP-0.2", V("SubjectKind", rfc.subject_kinds(), code, by_value=True))
    add("F4", "F4.behavior_contract_shape", "WP-1.1",
        _shape("aisef2.product.contract", "BehaviorContract", rfc.dataclasses.get("BehaviorContract")))
    add("F4", "F4.product_proof_spec_shape", "WP-1.2",
        _shape("aisef2.product.spec", "ProductProofSpec", rfc.dataclasses.get("ProductProofSpec")))
    add("F5", "F5.enum.Enforcement", "WP-0.2", V("Enforcement", e.get("Enforcement", []), code))
    add("F5", "F5.probe_protocol", "WP-2.1", _shape("aisef2.probe.protocol", "Probe", rfc.protocols.get("Probe")))
    add("F5", "F5.calibration_contracts", "WP-2.2",
        _shape("aisef2.probe.calibration", "ProbeCapabilityCalibration",
               {"ProbeCapabilityCalibration": rfc.dataclasses.get("ProbeCapabilityCalibration"),
                "SpecFalsifiabilityEvidence": rfc.dataclasses.get("SpecFalsifiabilityEvidence")}
               if rfc.dataclasses.get("ProbeCapabilityCalibration") and rfc.dataclasses.get("SpecFalsifiabilityEvidence")
               else None))
    for n in ("ObligationRole", "ParentExpectation"):
        add("F6", f"F6.enum.{n}", "WP-0.2", V(n, e.get(n, []), code))
    add("F6", "F6.plan_obligation_shape", "WP-2.3",
        _shape("aisef2.plan.obligation", "PlanObligation", rfc.dataclasses.get("PlanObligation")))
    add("F7", "F7.dispositions", "WP-0.2",
        V("StoryAdmissionDisposition", e.get("StoryAdmissionDisposition", []), code))
    order = rfc.lifetime_order()
    add("F8", "F8.scopes_and_lifetime_order", "WP-4.3",
        _shape("aisef2.runtime.run_scope", "RunScope",
               order if len(order.get("begin", [])) == 5 and len(order.get("shutdown", [])) == 6 else None))
    add("F9", "F9.enum.IdentityGrade", "WP-0.2", V("IdentityGrade", e.get("IdentityGrade", []), code))
    ids = rfc.cited_identities()
    add("F9", "F9.cited_identities_and_runspec", "WP-4.4",
        _shape("aisef2.runtime.runspec", "RunSpec", {"identities": ids, "RunSpec": rfc.dataclasses.get("RunSpec")}
               if len(ids) == 4 and rfc.dataclasses.get("RunSpec") else None))
    inv = rfc.invariants()
    add("F10", "F10.invariant_ids", "WP-0.2", V("InvariantId", list(inv), code, by_value=True))
    titles = [f"{k}:{v}" for k, v in inv.items()]
    add("F10", "F10.invariant_titles", "WP-0.2", V("__invariant_titles__", titles, code, by_value=True))
    add("F10", "F10.invariants_armed_with_mechanisms", "WP-5.5",
        _shape("aisef2.invariants.registry", "arm", list(inv) if len(inv) == 9 else None))
    add("F11", "F11.closed_projection_list", "WP-0.2",
        V("ControlProjection", rfc.control_projections(), code, by_value=True))
    add("F11", "F11.projections_implemented", "WP-3.4",
        _shape("aisef2.journal.projections", None, rfc.control_projections() or None))
    return S


def evaluate(rfc_text: str, code, manifest: dict) -> dict:
    rfc = RFC(rfc_text)
    subs = subchecks(rfc, code)
    ratchet = []
    for s in subs:
        required = _reached(_phase_of(s["implemented_by"], manifest), manifest)
        s["required_now"] = required
        if s["state"] is None:  # implementation absent
            if required:
                s["state"] = FAIL
                s["detail"] += f" — but {s['implemented_by']} is in a phase already reached ({CURRENT_PHASE}): FAIL, not PENDING"
                ratchet.append(s["id"])
            else:
                s["state"] = PENDING
    items = []
    for fid in FROZEN_IDS:
        mine = [s for s in subs if s["item"] == fid]
        states = {s["state"] for s in mine}
        state = FAIL if (not mine or FAIL in states) else PENDING if PENDING in states else PASS
        items.append({"id": fid, "state": state, "subchecks": [s["id"] for s in mine],
                      "pending_on": sorted({s["implemented_by"] for s in mine if s["state"] == PENDING})})
    return {
        "record": "AISEF V2 — F1–F11 CONFORMANCE",
        "work_package": "WP-0.3",
        "current_phase": CURRENT_PHASE,
        "reference": "extracted from the RFC normative body; never transcribed",
        "items": items,
        "subchecks": subs,
        "summary": {s: sum(1 for i in items if i["state"] == s) for s in (PASS, PENDING, FAIL)},
        "ratchet_violations": ratchet,
    }


def load_inputs(root: pathlib.Path = ROOT):
    return ((root / RFC_REL).read_text(encoding="utf-8"), code_vocabularies(),
            json.loads((root / MANIFEST_REL).read_text(encoding="utf-8")))


def problems_of(result: dict) -> list[str]:
    out = [f"{i['id']} FAIL" for i in result["items"] if i["state"] == FAIL]
    out += [f"{s['id']}: {s['detail']}" for s in result["subchecks"] if s["state"] == FAIL]
    out += [f"{s['id']} is required now but is {s['state']}" for s in result["subchecks"]
            if s["required_now"] and s["state"] != PASS and s["state"] != FAIL]
    if [i["id"] for i in result["items"]] != FROZEN_IDS:
        out.append("items are not exactly F1–F11")
    for i in result["items"]:
        if i["state"] not in (PASS, FAIL, PENDING):
            out.append(f"{i['id']} has no definite state")
        if i["state"] == PASS and i["pending_on"]:
            out.append(f"{i['id']} reports PASS while pending on {i['pending_on']}")
    return out


def render(result: dict) -> str:
    return json.dumps(result, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    result = evaluate(*load_inputs())
    problems = problems_of(result)
    if "--check" in argv:
        committed = ROOT / OUT_REL
        if not committed.exists():
            problems.append(f"{OUT_REL} is missing")
        elif committed.read_text(encoding="utf-8") != render(result):
            problems.append(f"{OUT_REL} is stale: regenerate it")
    for i in result["items"]:
        print(f"{i['state']:8s} {i['id']:4s}" + (f"  pending on {', '.join(i['pending_on'])}" if i["pending_on"] else ""))
    for p in problems:
        print(f"FAIL  {p}")
    print(f"summary {result['summary']} | ratchet violations {len(result['ratchet_violations'])}")
    if "--check" not in argv and not problems:
        (ROOT / OUT_REL).write_text(render(result), encoding="utf-8")
        print(f"wrote {OUT_REL}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
