"""`aisef bundle`: the project bundle's own tools — outside a run, no provider, no repository written.

    aisef bundle migrate IN --out OUT     a bundle of an earlier release, its plan re-bound to this release's spec ids

V2.1 (ARCHITECTURE-EXCEPTION-V2-007): a ProductProofSpec binds its probe's capability (id, version, classes), no longer
the bytes of its source. A bundle written for 2.0.0 names spec ids compiled under 2.0.0's source digests, so its plan
names specs this release does not compile; `migrate` re-binds each obligation to the spec its own approved contract
compiles to now. The contracts, approvals, requirements and facts are untouched — nothing is re-approved, because the
contract semantics an approval binds did not change. An obligation whose spec no known release compiles from one of
the bundle's approved contracts is refused, never guessed. The input is never written."""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
from typing import Mapping

from aisef2.app import bundle as B
from aisef2.arch.enums import SubjectKind
from aisef2.plan.obligation import Plan
from aisef2.probe import catalog
from aisef2.product.approval import ContractApproval, Requirement
from aisef2.product.compiler import ProbeRef, compile_spec
from aisef2.product.contract import BehaviorContract, plain
from aisef2.product.spec import ProductProofSpec

#: what each earlier release compiled specs under: its active probes' digests and its compiler digest (2.0.0 =
#: tag v2.0.0 at ca26313: the source digests its shipped calibrations name; the compiler is unchanged since)
RELEASES: Mapping[str, dict] = {
    "2.0.0": {"compiler_digest": "f31a4602a61d412d834890f46dcc9ca4d0ce240a106a4772dc9a1e8e7fb8ea76",
              "probes": {SubjectKind.FILE_ARTIFACT: ("probe.file_artifact", "31465b73cbe2440e0e9f6b418665b6f4b1682ee7da2b8968357709daea5e5901"),
                         SubjectKind.PYTHON_CALLABLE: ("probe.python_callable_v2", "b1f25878d350b7848caddd8be01f09da63066876d5b3adb71af61ed9d874b3ae"),
                         SubjectKind.CLI_INVOCATION: ("probe.cli_invocation", "d42449fd8e3ac428758b78d2136e3f2280c2c97223385cdd4d87ec5885572f3f"),
                         SubjectKind.PROCESS_EFFECT: ("probe.process_effect", "815e4c865274d43a7c0467e3af3fbceb67f9086a84eb8f3d2074e43ac16f9273")}},
}


class MigrationError(B.BundleError):
    """The bundle cannot be re-bound: what it names is not what any known release compiled from its contracts."""


def _earlier(spec: ProductProofSpec, release: dict) -> str | None:
    """The id `spec`'s contract compiled to under `release`, or None (no probe of that release for its kind)."""
    kind = SubjectKind(spec.probe_input["subject"]["kind"])
    ref = release["probes"].get(kind)
    if ref is None:
        return None
    return ProductProofSpec.create(contract_id=spec.contract_id, probe_id=ref[0], probe_digest=ref[1],
                                   probe_input=spec.probe_input, candidate_expectation=spec.candidate_expectation,
                                   compiler_id=spec.compiler_id, compiler_digest=release["compiler_digest"]).id


def migrate(data: Mapping) -> tuple[dict, dict]:
    """(the re-bound bundle, the report). Refuses a bundle whose shape does not hold or whose plan names a spec that no
    known release compiles from one of its approved contracts."""
    if not isinstance(data, Mapping) or data.get("format") != B.FORMAT:
        raise MigrationError(f"not a project bundle of format {B.FORMAT}")
    B.shape_problems(data)
    try:
        requirements = {r["id"]: Requirement(**r) for r in data["requirements"]}
        contracts = [BehaviorContract.from_json(c) for c in data["contracts"]]
        approvals = tuple(ContractApproval(**a) for a in data["approvals"])
        plan = B._plan(data["plan"])
    except (KeyError, TypeError, ValueError) as e:
        raise MigrationError(f"the bundle's kernel objects do not load: {type(e).__name__}: {e}") from e
    refs = {kind: ProbeRef(e.probe_id, e.probe_digest) for kind, e in catalog.active().items()}
    current: dict[str, ProductProofSpec] = {}
    for c in contracts:
        try:
            current[c.id] = compile_spec(c, requirements=requirements, approvals=approvals, probes=refs)
        except ValueError as e:
            raise MigrationError(f"contract {c.id} does not compile: {e}") from e
    now = {s.id: s.id for s in current.values()}
    known = dict(now)
    origin = {s.id: "current" for s in current.values()}
    for name, release in RELEASES.items():
        for s in current.values():
            old = _earlier(s, release)
            if old is not None and old not in known:
                known[old], origin[old] = s.id, name
    obligations, mapped, unknown = [], {}, []
    for o in plan.obligations:
        new = known.get(o.product_proof_spec_id)
        if new is None:
            unknown.append(o.criterion_id)
            continue
        if new != o.product_proof_spec_id:
            mapped[o.product_proof_spec_id] = {"to": new, "from_release": origin[o.product_proof_spec_id]}
        obligations.append(dataclasses.replace(o, product_proof_spec_id=new))
    if unknown:
        raise MigrationError(f"{len(unknown)} obligation(s) name a spec no known release ({', '.join(RELEASES)} or this "
                             f"one) compiles from the bundle's approved contracts: {unknown[:5]}")
    new_plan = Plan.create(id=plan.id, baseline=plan.baseline, obligations=tuple(obligations),
                           plan_quality_policy=plan.plan_quality_policy)
    out = {**dict(data), "plan": plain(new_plan)}
    B.load(out)     # the result loads, every seal re-checked, under this release's probes
    report = {"specs_rebound": len(mapped), "obligations": len(obligations), "mapping": mapped,
              "plan_hash": {"from": plan.plan_hash, "to": new_plan.plan_hash},
              "unchanged": ["requirements", "contracts", "approvals", "facts", "stories", "requirements_document"]}
    return out, report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aisef bundle", description="The project bundle's own tools (no run, no provider).")
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("migrate", help="re-bind an earlier release's bundle to this release's spec ids")
    m.add_argument("bundle", type=pathlib.Path)
    m.add_argument("--out", type=pathlib.Path, required=True, help="the migrated bundle (a new file; never the input)")
    a = p.parse_args(argv)
    try:
        if a.out.exists():
            raise MigrationError(f"{a.out} exists: migrate writes a new file and never overwrites one")
        try:
            data = json.loads(a.bundle.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            raise MigrationError(f"{a.bundle}: cannot be read as JSON ({type(e).__name__})") from e
        out, report = migrate(data)
    except B.BundleError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    a.out.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(a.out), **report}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
