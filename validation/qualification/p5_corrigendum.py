"""C2-P5 acceptance corrigendum 1 (owner ruling 2026-09-30, "P5 WORDING CORRIGENDUM"): append-only; the acceptance
record is never edited.

    python -P validation/qualification/p5_corrigendum.py --write    # closure-evidence/v2/cycle2/C2-P5-ACCEPTANCE-CORRIGENDUM-1.json (once)
    python -P validation/qualification/p5_corrigendum.py --check

The acceptance associated S-5-a with the zero-byte-file ruling (OR-IFACE-3) by copying the proposal's IB-EMPTY prose;
S-5-a begins with no ledger file. The corrected statement is derived from the contracts' content (the same mechanical
reading the acceptance used), and every identity the acceptance bound is re-derived to show that nothing semantic moves.
Refused (STOP) if any contract, spec, semantic hash, the plan hash or the falsifiability evidence differs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import p5_acceptance as pa  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/C2-P5-ACCEPTANCE-CORRIGENDUM-1.json"
SPEC = "S-5-a"


def _sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build() -> dict:
    from aisef2.product.contract import plain
    acceptance = json.loads((ROOT / pa.OUT_REL).read_text(encoding="utf-8"))
    v = pa.verify(run_guards=False)
    cs = pa.contracts()
    bindings = pa.ruling_bindings(cs)
    stim = plain(cs[SPEC].stimulus)
    walk = list(pa._walk(stim))
    s5a = {"contract_id": cs[SPEC].id, "contract_hash": cs[SPEC].contract_hash,
           "zero_byte_ledger_file_in_the_stimulus": any(isinstance(x, dict) and x.get("bytes_hex") == "" for x in walk),
           "any_workspace_file_in_the_stimulus": any(isinstance(x, dict) and "bytes_hex" in x for x in walk),
           "first_step": stim["scenario"][0], "bound_by_OR_IFACE_3": SPEC in bindings["OR-IFACE-3"]}
    fals = json.loads((ROOT / pa.FALSIFIABILITY_REL).read_text(encoding="utf-8"))
    row = next(r for r in fals["specs"] if r["spec_id"] == SPEC)
    problems = list(v["problems"])
    if v["semantic_change"] != "NONE":
        problems.append("a semantic identity differs from the accepted one")
    if s5a["zero_byte_ledger_file_in_the_stimulus"] or s5a["bound_by_OR_IFACE_3"]:
        problems.append("S-5-a does hold a zero-byte ledger file: the corrigendum's statement would be false")
    if json.loads(json.dumps(v["identities"])) != acceptance["verification"]["identities"]:
        problems.append("the accepted identities do not re-derive")
    return {
        "record": "AISEF V2 — C2-P5 ACCEPTANCE CORRIGENDUM 1 (S-5-a and the zero-byte-file ruling)",
        "id": "AISEF-V2-CYCLE2-C2-P5-ACCEPTANCE-CORRIGENDUM-1",
        "authority": "owner ruling 2026-09-30 'P5 WORDING CORRIGENDUM': append-only; the recorded acceptance is not edited",
        "corrects": {"record": {"path": pa.OUT_REL, "sha256": _sha(pa.OUT_REL), "edited": False},
                     "statement": "verification.rulings.OR-IFACE-3.as_named_by_the_proposal lists S-5-a, copied from the proposal's "
                                  "IB-EMPTY prose (P5-PLAN-V2.2-PROPOSAL.json interface_bindings.IB-EMPTY.gap)",
                     "as_recorded": acceptance["verification"]["rulings"]["OR-IFACE-3"].get("as_named_by_the_proposal")},
        "corrected_statement": [
            "S-5-a does NOT rely on the zero-byte-existing-file interpretation (OR-IFACE-3): its stimulus holds no ledger file at all; "
            "its scenario constructs Ledger(<ws>/l.jsonl) over a path with no file, as its exact approved contract hash encodes",
            "the OR-IFACE-3 ruling applies only where the stimulus actually contains an existing zero-byte ledger: "
            + ", ".join(bindings["OR-IFACE-3"]),
            "no BehaviorContract changes; no ProductProofSpec changes; no semantic_hash changes; no plan_hash change; no falsifiability "
            "evidence invalidated"],
        "measured": {"S-5-a": s5a, "or_iface_3_contracts": bindings["OR-IFACE-3"],
                     "semantic_change": v["semantic_change"], "plan_hash": v["identities"]["plan_hash"],
                     "proposal_digest": v["identities"]["proposal_digest"],
                     "specs_equal_to_accepted": sum(1 for r in v["identities"]["specs"] if r["equal_to_accepted"]),
                     "falsifiability": {"record": {"path": pa.FALSIFIABILITY_REL, "sha256": _sha(pa.FALSIFIABILITY_REL)},
                                        "S-5-a": {"status": row["status"], "pristine": row["pristine"], "mutant_verdict": row["mutant_verdict"],
                                                  "semantic_hash": row["semantic_hash"]}}},
        "problems": problems,
        "verdict": "CORRIGENDUM RECORDED — NO SEMANTIC CHANGE" if not problems else "STOP",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    rec = build()
    if rec["problems"]:
        print("STOP: " + "; ".join(rec["problems"]))
        return 1
    path = ROOT / OUT_REL
    if a.write:
        if path.exists():
            raise SystemExit(f"refused: {OUT_REL} exists (append-only)")
        path.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    else:
        old = json.loads(path.read_text(encoding="utf-8"))
        if {k: v for k, v in old.items() if k != "corrects"} != {k: v for k, v in rec.items() if k != "corrects"}:
            print(f"{OUT_REL} does not re-derive")
            return 1
    print(rec["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
