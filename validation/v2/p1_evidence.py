"""P1 evidence records — computed from the code, never written by hand, with a --check twin.

Every record carries `properties`: named facts measured on the implementation. `--check` re-derives each record and
fails if it differs from the committed one **or** if any property is false, so a record cannot certify a property
the code no longer has.

    python -P validation/v2/p1_evidence.py            # write every record whose package is implemented
    python -P validation/v2/p1_evidence.py --check    # fail on drift or on a false property
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import pathlib
import sys
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _module(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _rfc():
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    return fc.RFC((ROOT / fc.RFC_REL).read_text(encoding="utf-8"))


def _raises(fn: Callable, *exc: type[BaseException]) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


# --------------------------------------------------------------------------------------- WP-1.1

def contract_shapes() -> dict:
    from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind
    from aisef2.product.approval import ContractApproval, Requirement, UnapprovedContract, require_approved
    from aisef2.product.contract import BehaviorContract, ContractError, Subject
    ks = _module("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
    rfc = _rfc()
    base = dict(id="BC-REF", requirement_ids=("REQ-REF",), subject=Subject(SubjectKind.CLI_INVOCATION, "app.cli:main"),
                stimulus={"argv": ["--quiet"]}, observable={"stdout": "empty"}, polarity=Polarity.MUST_NOT_HOLD,
                subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="reference contract")
    ref = BehaviorContract.create(**base)
    req = Requirement.create(id="REQ-REF", text="reference requirement", source="evidence")
    ok = ContractApproval(req.id, req.requirement_hash, ref.id, ref.contract_hash, "human:evidence", 0.0, ())
    variants = {"id": "BC-X", "requirement_ids": ("REQ-REF", "REQ-X"),
                "subject": Subject(SubjectKind.CLI_INVOCATION, "app.cli:other"), "stimulus": {"argv": []},
                "observable": {"stdout": "x"}, "polarity": Polarity.MUST_HOLD,
                "subject_absence": SubjectAbsence.ABSENCE_IS_DECIDABLE, "rationale": "reworded"}
    bound = {f: BehaviorContract.create(**{**base, f: v}).contract_hash != ref.contract_hash for f, v in variants.items()}
    named = ["tests/test_cli.py", "pkg.tests.test_cli", "cli_test.py", "conftest.py", "x.py::test_a", "pytest"]
    edited_req = Requirement.create(id="REQ-REF", text="edited", source="evidence")
    shapes = {c.__name__: {"rfc": rfc.dataclasses.get(c.__name__), "code": [f.name for f in dataclasses.fields(c)]}
              for c in (Requirement, ContractApproval, Subject, BehaviorContract)}
    return {
        "record": "AISEF V2 — P1 CONTRACT SHAPES", "work_package": "WP-1.1", "rfc_sections": ["6", "7"],
        "shapes": shapes,
        "reference_contract_hash": ref.contract_hash,
        "contract_hash_bound_fields": bound,
        "properties": {
            "shapes_equal_rfc": all(s["rfc"] == s["code"] for s in shapes.values()),
            "contract_hash_binds_every_field": set(bound) == {f.name for f in dataclasses.fields(BehaviorContract)}
                                               - {"contract_hash"} and all(bound.values()),
            "contract_hash_binds_subject_absence": bound["subject_absence"],
            "rationale_edit_detected": _raises(lambda: dataclasses.replace(ref, rationale="edited"), ContractError),
            "supplied_hash_verified": _raises(lambda: BehaviorContract(**base, contract_hash="0" * 64), ContractError),
            "json_round_trip_is_identity": BehaviorContract.from_json(json.loads(json.dumps(ref.to_json()))) == ref,
            "approval_binds_both_hashes": not _raises(lambda: require_approved(ref, {req.id: req}, [ok]),
                                                      UnapprovedContract),
            "requirement_edit_invalidates_approval": _raises(
                lambda: require_approved(ref, {req.id: edited_req}, [ok]), UnapprovedContract),
            "contract_edit_invalidates_approval": _raises(
                lambda: require_approved(BehaviorContract.create(**{**base, "rationale": "x"}), {req.id: req}, [ok]),
                UnapprovedContract),
            "unapproved_contract_refused": _raises(lambda: require_approved(ref, {req.id: req}, []), UnapprovedContract),
            "model_cannot_approve": _raises(lambda: ContractApproval(req.id, req.requirement_hash, ref.id,
                                                                     ref.contract_hash, "model:any", 0.0, ()),
                                            ContractError),
            "test_artefacts_rejected": all(_raises(lambda n=n: Subject(SubjectKind.PYTHON_CALLABLE, n), ContractError)
                                           for n in named),
            "subject_absence_never_inferred": _raises(lambda: BehaviorContract.create(**{**base, "subject_absence": None}),
                                                      ContractError),
            "no_prose_control": ks.check(ROOT, ("NO_PROSE_CONTROL",)) == [],
        },
    }


#: package -> (record path, builder, module that must exist before the record is built)
BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-1.1": ("closure-evidence/v2/P1-CONTRACT-SHAPES.json", contract_shapes, "aisef2/product/contract.py"),
}


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


def problems_of(record: dict) -> list[str]:
    props = record.get("properties") or {}
    out = [] if props else [f"{record.get('work_package')}: record carries no properties"]
    return out + [f"{record.get('work_package')}: property {k} is false" for k, v in props.items() if v is not True]


def check(root: pathlib.Path = ROOT) -> list[str]:
    out = []
    for rel, build, needs in BUILDERS.values():
        if not (root / needs).exists():
            continue
        fresh = build()
        out += problems_of(fresh)
        committed = root / rel
        if not committed.exists():
            out.append(f"{rel} is missing")
        elif committed.read_text(encoding="utf-8") != render(fresh):
            out.append(f"{rel} is stale: regenerate it")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        problems = check()
    else:
        problems = []
        for rel, build, needs in BUILDERS.values():
            if (ROOT / needs).exists():
                record = build()
                problems += problems_of(record)
                if not problems_of(record):
                    (ROOT / rel).write_text(render(record), encoding="utf-8")
                    print(f"wrote {rel}")
    for p in problems:
        print(f"FAIL  {p}")
    print("p1 evidence: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
