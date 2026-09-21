"""WP-1.2 — compile the committed contract corpus into ProductProofSpecs, with a `--check` twin (RFC §8, Q0).

The corpus (`corpus.json`) holds requirements, behaviour contracts, their human approvals and the probe catalogue.
Every spec is derived by the pure compiler; none is hand-authored. `--check` re-derives every spec and fails on any
byte of drift, on a committed spec with no contract, and on a contract with no committed spec.

Cycle-1 corpus probes are declared identities (`fixture.*`): real probes arrive with WP-2.1, and each digest says so.

    python -P validation/v2/gen_specs.py [--corpus DIR]            # write DIR/specs/<contract id>.json
    python -P validation/v2/gen_specs.py [--corpus DIR] --check    # fail on drift
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS_REL = "tests/v2/fixtures/p1/corpus"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load(corpus: pathlib.Path):
    from aisef2.arch.enums import SubjectKind
    from aisef2.product.approval import ContractApproval, Requirement
    from aisef2.product.compiler import ProbeRef
    from aisef2.product.contract import BehaviorContract
    data = json.loads((corpus / "corpus.json").read_text(encoding="utf-8"))
    requirements = {r["id"]: Requirement(**r) for r in data["requirements"]}
    contracts = [BehaviorContract.from_json(c) for c in data["contracts"]]
    approvals = [ContractApproval(**{**a, "model_reviews": tuple(a["model_reviews"])}) for a in data["approvals"]]
    probes = {SubjectKind(k): ProbeRef(**v) for k, v in data["probes"].items()}
    return requirements, contracts, approvals, probes


def derive(corpus: pathlib.Path) -> dict[str, str]:
    """contract id -> the canonical text of its compiled spec."""
    from aisef2.product.compiler import compile_spec
    requirements, contracts, approvals, probes = load(corpus)
    return {c.id: json.dumps(compile_spec(c, requirements=requirements, approvals=approvals, probes=probes).to_json(),
                             indent=1, sort_keys=True, ensure_ascii=False) + "\n"
            for c in contracts}


def check(corpus: pathlib.Path = ROOT / CORPUS_REL) -> list[str]:
    fresh = derive(corpus)
    specs = corpus / "specs"
    committed = {p.stem: p.read_text(encoding="utf-8") for p in sorted(specs.glob("*.json"))} if specs.exists() else {}
    out = [f"spec for {cid} differs from its fresh derivation" for cid in sorted(fresh.keys() & committed.keys())
           if fresh[cid] != committed[cid]]
    out += [f"contract {cid} has no committed spec" for cid in sorted(fresh.keys() - committed.keys())]
    out += [f"committed spec {cid} has no contract" for cid in sorted(committed.keys() - fresh.keys())]
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    corpus = pathlib.Path(argv[argv.index("--corpus") + 1]) if "--corpus" in argv else ROOT / CORPUS_REL
    if "--check" in argv:
        problems = check(corpus)
        for p in problems:
            print(f"FAIL  {p}")
        print("specs: " + ("FAIL" if problems else "PASS"))
        return 1 if problems else 0
    specs = corpus / "specs"
    specs.mkdir(exist_ok=True)
    for cid, text in derive(corpus).items():
        (specs / f"{cid}.json").write_text(text, encoding="utf-8")
        print(f"wrote {specs.relative_to(ROOT) if specs.is_relative_to(ROOT) else specs}/{cid}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
