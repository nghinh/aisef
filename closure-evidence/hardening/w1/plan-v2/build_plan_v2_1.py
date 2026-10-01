"""W1-LEDGERLOCK-PLAN-V2.1 — the final workload-plan revision of this qualification cycle.

Exactly what the ownership audit found, and nothing else. The requirements and the hidden oracle are untouched.

    python3 build_plan_v2_1.py <epics.md> --out-edits PLAN-V2.1-EDITS.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from aisef.control.normalize import parse_epics  # noqa: E402

#: The criterion STORY-01-01 gains: the usage-error exit its own argparse CLI surface necessarily introduces.
NEW_AC_0101 = ("- Given the registered CLI, `python -m ledgerlock verify <ledger> <extra-positional>` in a "
               "subprocess exits `2` and writes nothing to stdout (argparse reports a usage error on stderr).")

EDITS = [
    {
        "id": "PLAN-V2.1-01",
        "kind": "MOVE_CHANGE_OWNER",
        "ac": "AC-STORY-04-01-2",
        "from": {"story": "STORY-04-01", "proof_mode": "CHANGE_REQUIRED", "requirement": "FR-11"},
        "to": {"story": "STORY-04-01", "proof_mode": "PRESERVE_REQUIRED", "requirement": "FR-12"},
        "introduction_owner_becomes": "STORY-01-01 (new criterion 7, CHANGE_REQUIRED / FR-12)",
        "rationale":
            "Two defects in one criterion, both found by the ownership audit and both traceable to the frozen "
            "documents. Requirement: 'calling any subcommand with the wrong number of positional arguments exits 2' "
            "is a testable consequence the PRD lists under FR-12, the exit-code contract; FR-11 is the subcommand "
            "surface. Ownership: STORY-01-01's declared responsibility is 'a CLI module that registers "
            "verify/snapshot/apply/repair-tail argparse subcommands', and argparse's contract for a usage error is "
            "SystemExit(2) with the message on stderr and stdout untouched — so every correct implementation of "
            "STORY-01-01 already exhibits the behaviour. STORY-04-01 rewrites ledgerlock/cli.py and "
            "ledgerlock/__main__.py wholesale and can therefore regress it, which is what PRESERVE_REQUIRED is for. "
            "Diagnostic run 1 observed the criterion green at STORY-04-01's parent; that agrees with this reading "
            "but is not its basis, and no mode was changed because a model happened to implement something early.",
    },
    {
        "id": "PLAN-V2.1-02",
        "kind": "ADD_INTRODUCTION_OWNER",
        "ac": "AC-STORY-01-01-7",
        "story": "STORY-01-01",
        "proof_mode": "CHANGE_REQUIRED",
        "requirement": "FR-12",
        "text": NEW_AC_0101,
        "rationale":
            "The other half of PLAN-V2.1-01: the behaviour needs an introduction owner, and it is this story. At "
            "STORY-01-01's parent no `ledgerlock` package exists, so `python -m ledgerlock` exits 1 with a "
            "ModuleNotFoundError rather than 2 — the criterion can legitimately be red there and green at the "
            "story's candidate. STORY-01-01's `covers` gains FR-12 so the criterion's requirement stays inside the "
            "story's declared coverage.",
    },
]


def apply_edits(text: str) -> str:
    out = text

    # --- PLAN-V2.1-02: STORY-01-01 gains criterion 7, its covers gains FR-12, its ac_proof gains 7=CHANGE/FR-12
    anchor = "- Given an `__init__.py`, `from ledgerlock import Ledger, ConflictError` returns both names without exception and `Ledger` is a callable class.\n"
    assert out.count(anchor) == 1, "the STORY-01-01 anchor criterion is not unique"
    out = out.replace(anchor, anchor + NEW_AC_0101 + "\n")

    old_meta = ("- covers: FR-1, FR-14\n"
                "- ac_proof: 1=CHANGE_REQUIRED/FR-1, 2=CHANGE_REQUIRED/FR-1, 3=CHANGE_REQUIRED/FR-14, "
                "4=NEGATIVE_INVARIANT/FR-14, 5=NEGATIVE_INVARIANT/FR-14, 6=CHANGE_REQUIRED/FR-14\n")
    assert out.count(old_meta) == 1, "the STORY-01-01 metadata block is not unique"
    out = out.replace(old_meta, ("- covers: FR-1, FR-12, FR-14\n"
                                 "- ac_proof: 1=CHANGE_REQUIRED/FR-1, 2=CHANGE_REQUIRED/FR-1, "
                                 "3=CHANGE_REQUIRED/FR-14, 4=NEGATIVE_INVARIANT/FR-14, "
                                 "5=NEGATIVE_INVARIANT/FR-14, 6=CHANGE_REQUIRED/FR-14, 7=CHANGE_REQUIRED/FR-12\n"))

    # --- PLAN-V2.1-01: STORY-04-01 criterion 2 becomes PRESERVE_REQUIRED / FR-12
    old_04 = ("- ac_proof: 1=CHANGE_REQUIRED/FR-11, 2=CHANGE_REQUIRED/FR-11, 3=CHANGE_REQUIRED/FR-11, "
              "4=CHANGE_REQUIRED/FR-11, 5=CHANGE_REQUIRED/FR-11, 6=CHANGE_REQUIRED/FR-12, 7=CHANGE_REQUIRED/FR-12\n")
    assert out.count(old_04) == 1, "the STORY-04-01 obligation line is not unique"
    out = out.replace(old_04, ("- ac_proof: 1=CHANGE_REQUIRED/FR-11, 2=PRESERVE_REQUIRED/FR-12, "
                               "3=CHANGE_REQUIRED/FR-11, 4=CHANGE_REQUIRED/FR-11, 5=CHANGE_REQUIRED/FR-11, "
                               "6=CHANGE_REQUIRED/FR-12, 7=CHANGE_REQUIRED/FR-12\n"))

    # the scope note says what STORY-04-01 now inherits rather than introduces
    old_note = ("Scope note: the **error** exit codes (`3` I/O, `4` conflict, `5` corruption) are STORY-04-02's "
                "contract, and the stderr status shapes beyond `verify` are STORY-04-03's. Implement the success "
                "paths here; do not pre-empt them.\n")
    assert out.count(old_note) == 1, "the STORY-04-01 scope note is not unique"
    out = out.replace(old_note, old_note.rstrip("\n") + (
        " The usage-error exit (`2` on a wrong positional count) is already established by STORY-01-01's argparse "
        "surface; this story must not regress it, which is why its criterion here is PRESERVE_REQUIRED.\n"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epics")
    ap.add_argument("--out-edits", required=True)
    a = ap.parse_args()
    p = Path(a.epics)
    before = p.read_text(encoding="utf-8")
    after = apply_edits(before)
    p.write_text(after, encoding="utf-8")

    plan = parse_epics(after)
    listed = plan.stories() if callable(plan.stories) else plan.stories
    stories = {s.id: s for s in listed}
    s1, s4 = stories["STORY-01-01"], stories["STORY-04-01"]
    checks = {
        "story_01_01_criteria": len(s1.acceptance_criteria),
        "story_01_01_ac7": (s1.ac_proof or {}).get("AC-STORY-01-01-7"),
        "story_01_01_covers": list(s1.covers),
        "story_04_01_ac2": (s4.ac_proof or {}).get("AC-STORY-04-01-2"),
        "total_criteria": sum(len(s.acceptance_criteria) for s in stories.values()),
        "modes": {m: sum(1 for s in stories.values() for d in (s.ac_proof or {}).values()
                         if (d or {}).get("proof_mode") == m)
                  for m in ("CHANGE_REQUIRED", "PRESERVE_REQUIRED", "NEGATIVE_INVARIANT")},
    }
    rec = {"artifact": "W1-LEDGERLOCK-PLAN-V2.1", "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "owner_decision": "FINAL PLAN CORRECTION, KERNEL REMAINS FROZEN (2026-09-21), section 5",
           "base": "W1-LEDGERLOCK-PLAN-V2 (1621a2bc)", "requirements_changed": False, "hidden_oracle_changed": False,
           "edits": EDITS, "verified_by_the_product_parser": checks}
    Path(a.out_edits).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
