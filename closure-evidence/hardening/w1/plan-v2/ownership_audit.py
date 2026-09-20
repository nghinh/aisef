"""Semantic-ownership audit of every acceptance criterion in W1-LEDGERLOCK-PLAN-V2 (owner decision 2026-09-21).

The question this answers is not "was the criterion green at some parent" — that is what a run measures, and the
owner forbids using it as ownership proof. It is: **which story's declared contract necessarily introduces this
behaviour?** A behaviour entailed by an upstream story's own responsibility is owned upstream, whatever a model
happened to write early; a behaviour an upstream story merely over-implemented stays where the plan put it.

Every criterion is judged, and the judgement carries its reason. Where two stories declare CHANGE_REQUIRED on one
requirement, the rationale says which distinct behaviour each introduces — a 14-requirement plan with 76 criteria
cannot have one criterion per requirement, and the rule the owner set is one introduction owner per *behaviour*.

    python3 ownership_audit.py <epics.md> <prd.md> --out W1-PLAN-V2.1-OWNERSHIP-AUDIT.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from aisef.control.normalize import parse_epics  # noqa: E402

KEEP, MOVE, PRESERVE, REMOVE = "KEEP_CHANGE", "MOVE_CHANGE_OWNER", "PRESERVE_DOWNSTREAM", "REMOVE_DUPLICATE"

#: The behaviour each criterion introduces, named so two criteria under one requirement can be told apart. Keyed by
#: AC id. Every criterion of the plan appears; the audit fails if one does not.
BEHAVIOUR = {
    # --- STORY-01-01 package skeleton, CLI surface, NFC
    "AC-STORY-01-01-1": "normalize_key returns unicodedata NFC byte-for-byte",
    "AC-STORY-01-01-2": "NFC and NFD spellings of one key normalize to the same bytes",
    "AC-STORY-01-01-3": "the ledgerlock package is importable from a stdlib-only pyproject",
    "AC-STORY-01-01-4": "no forbidden import appears in the runtime package",
    "AC-STORY-01-01-5": "no side-channel call appears in the runtime package",
    "AC-STORY-01-01-6": "Ledger and ConflictError are importable from the package root",
    "AC-STORY-01-01-7": "a wrong positional count is a usage error with silent stdout",
    # --- STORY-01-02 canonical bytes
    "AC-STORY-01-02-1": "canonical_bytes encodes a line with sorted keys and tight separators",
    "AC-STORY-01-02-2": "canonical_bytes is stable across two calls on equal dicts",
    "AC-STORY-01-02-3": "canonical_bytes emits non-ASCII as UTF-8 literals",
    "AC-STORY-01-02-4": "canonical_bytes ignores key insertion order",
    "AC-STORY-01-02-5": "GENESIS is the literal seven-character string",
    "AC-STORY-01-02-6": "canonical_bytes survives a json round trip",
    # --- STORY-01-03 line hash
    "AC-STORY-01-03-1": "line_hash returns 64 lowercase hex characters",
    "AC-STORY-01-03-2": "line_hash separates distinct prev_hash values",
    "AC-STORY-01-03-3": "line_hash empties the hash fields before hashing",
    "AC-STORY-01-03-4": "line_hash is deterministic for one input pair",
    "AC-STORY-01-03-5": "line_hash accepts the non-hex GENESIS prev_hash",
    # --- STORY-01-04 store primitives
    "AC-STORY-01-04-1": "read_lines splits JSONL into newline-stripped byte lines",
    "AC-STORY-01-04-2": "read_lines raises FileNotFoundError on a missing path",
    "AC-STORY-01-04-3": "read_lines returns an empty list for an empty file",
    "AC-STORY-01-04-4": "write_atomic replaces a file with the given lines",
    "AC-STORY-01-04-5": "write_atomic leaves the original intact when the replace fails",
    "AC-STORY-01-04-6": "write_atomic writes its temp file beside the target",
    # --- STORY-01-05 append
    "AC-STORY-01-05-1": "append writes the first chained line with GENESIS prev_hash",
    "AC-STORY-01-05-2": "append chains the second line to the first line's hash",
    "AC-STORY-01-05-3": "append rejects an empty key after normalization",
    "AC-STORY-01-05-4": "a fresh Ledger reads the chain tail from disk",
    "AC-STORY-01-05-5": "append durably commits the bytes before returning",
    # --- STORY-01-06 rid semantics
    "AC-STORY-01-06-1": "a replayed rid returns the committed line and appends nothing",
    "AC-STORY-01-06-2": "a different rid on a live key raises ConflictError and appends nothing",
    "AC-STORY-01-06-3": "a different rid against a tombstone conflicts",
    "AC-STORY-01-06-4": "the same rid against a tombstone replays",
    "AC-STORY-01-06-5": "replay matching is by NFC-normalized key",
    # --- STORY-02-01 verify
    "AC-STORY-02-01-1": "verify returns ok on a valid chain",
    "AC-STORY-02-01-2": "verify returns ok on an empty chain",
    "AC-STORY-02-01-3": "verify raises FileNotFoundError on a missing chain",
    "AC-STORY-02-01-4": "verify detects an overwritten hash field from disk alone",
    "AC-STORY-02-01-5": "verify detects a mutated value from disk alone",
    # --- STORY-02-02 snapshot
    "AC-STORY-02-02-1": "snapshot is deterministic and sorted by key",
    "AC-STORY-02-02-2": "a refused conflicting delete leaves the snapshot unchanged",
    "AC-STORY-02-02-3": "a tombstoned key is absent from the snapshot",
    "AC-STORY-02-02-4": "snapshot keys are the NFC form",
    "AC-STORY-02-02-5": "two Ledger instances snapshot one chain equally",
    # --- STORY-03-01 atomic batch
    "AC-STORY-03-01-1": "apply_batch commits N conflict-free lines as one chain",
    "AC-STORY-03-01-2": "apply_batch replays a matching rid inside the batch",
    "AC-STORY-03-01-3": "apply_batch refuses the whole batch on an inner conflict",
    "AC-STORY-03-01-4": "apply_batch reports the conflicting batch index",
    "AC-STORY-03-01-5": "a crash inside apply_batch leaves the pre-batch bytes",
    # --- STORY-03-02 repair tail
    "AC-STORY-03-02-1": "repair_tail strips only the truncated final line",
    "AC-STORY-03-02-2": "repair_tail is a no-op on a clean chain",
    "AC-STORY-03-02-3": "repair_tail refuses when the corruption is mid-chain",
    "AC-STORY-03-02-4": "repair_tail refuses a tampered, parseable final line",
    # --- STORY-04-01 CLI success paths
    "AC-STORY-04-01-1": "snapshot without --out is a usage error",
    "AC-STORY-04-01-2": "a wrong positional count is a usage error with silent stdout",
    "AC-STORY-04-01-3": "--help lists the four subcommands and exits 0",
    "AC-STORY-04-01-4": "verify succeeds with silent stdout and one stderr line",
    "AC-STORY-04-01-5": "snapshot --out writes the snapshot bytes",
    "AC-STORY-04-01-6": "apply --batch commits from the CLI",
    "AC-STORY-04-01-7": "repair-tail leaves a clean chain untouched from the CLI",
    # --- STORY-04-02 error exit codes
    "AC-STORY-04-02-1": "a missing batch file exits 3",
    "AC-STORY-04-02-2": "a conflicting batch exits 4 and commits nothing",
    "AC-STORY-04-02-3": "verify on a corrupted chain exits 5",
    "AC-STORY-04-02-4": "repair-tail on mid-chain corruption exits 5",
    # --- STORY-04-03 stderr shapes
    "AC-STORY-04-03-1": "verify succeeds with silent stdout and one stderr line",
    "AC-STORY-04-03-2": "apply prints one stderr line naming the appended count",
    "AC-STORY-04-03-3": "snapshot prints one stderr line naming the destination",
    "AC-STORY-04-03-4": "repair-tail prints one stderr line on success",
    "AC-STORY-04-03-5": "every success path leaves stdout empty",
    # --- STORY-05-01 property round trip
    "AC-STORY-05-01-1": "the chain verifies and the snapshot is stable across random sequences",
    "AC-STORY-05-01-2": "a refused conflict leaves the chain at its prefix",
    "AC-STORY-05-01-3": "unittest and pytest agree on the property module",
    # --- STORY-05-02 coverage and parity
    "AC-STORY-05-02-1": "line coverage of the package is at least 85%",
    "AC-STORY-05-02-2": "unittest and pytest agree on the whole suite",
    "AC-STORY-05-02-3": "the test sources are excluded from the coverage measure",
    # --- STORY-05-03 guard test
    "AC-STORY-05-03-1": "no forbidden import appears in the runtime package",
    "AC-STORY-05-03-2": "no side-channel call appears in the runtime package",
}

#: Criteria whose judgement is not the default. `action`, `owner` (the semantic introduction owner), `why`, and for
#: a change: `to_mode`, `to_requirement`, `to_story`.
JUDGED = {
    "AC-STORY-04-01-2": {
        "action": MOVE,
        "downstream_disposition": PRESERVE,
        "owner": "STORY-01-01",
        "to_mode": "PRESERVE_REQUIRED",
        "to_requirement": "FR-12",
        "also_add_change_to": "STORY-01-01",
        "why": "Two defects in one criterion. (1) Requirement: 'calling any subcommand with the wrong number of "
               "positional arguments exits 2' is a testable consequence of FR-12, the exit-code contract; FR-11 is "
               "the subcommand surface. (2) Ownership: STORY-01-01's declared responsibility is 'a CLI module that "
               "registers verify/snapshot/apply/repair-tail argparse subcommands', and argparse's documented "
               "contract for a usage error is SystemExit(2) with the message on stderr and stdout untouched. Any "
               "correct implementation of STORY-01-01 therefore already exits 2 on a wrong positional count — the "
               "behaviour is entailed by the story's own contract, not over-implemented by chance. So the "
               "introduction owner is STORY-01-01, and because STORY-04-01 rewrites ledgerlock/cli.py and "
               "ledgerlock/__main__.py wholesale it can regress the behaviour, which is what PRESERVE_REQUIRED is "
               "for. The run-1 observation (green at the parent) agrees with this reading but is not its basis.",
    },
    "AC-STORY-01-01-4": {
        "action": KEEP,
        "owner": "STORY-01-01",
        "duplicate_of": "AC-STORY-05-03-1",
        "why": "The same prohibition is declared twice on purpose, and both are NEGATIVE_INVARIANT, so neither "
               "claims introduction ownership: it must hold when the package is created and again when it ships. "
               "At STORY-01-01's parent the package does not exist, so the prohibition holds vacuously — measured "
               "in diagnostic run 1, where the nop control at the parent executed 6 tests with exactly these 2 "
               "green and the 4 CHANGE_REQUIRED ones red.",
    },
    "AC-STORY-01-01-5": {"action": KEEP, "owner": "STORY-01-01", "duplicate_of": "AC-STORY-05-03-2",
                         "why": "See AC-STORY-01-01-4: one prohibition, two checkpoints, neither an introduction."},
    "AC-STORY-01-01-7": {
        "action": KEEP,
        "owner": "STORY-01-01",
        "why": "PLAN-V2.1 introduction owner of the usage-error exit. The story's declared responsibility is the "
               "argparse CLI surface, and argparse exits 2 with stdout untouched on a usage error, so this story "
               "is where the behaviour first exists. At its own parent no package exists and `python -m "
               "ledgerlock` exits 1 with ModuleNotFoundError, so the criterion can legitimately be red there.",
    },
    "AC-STORY-04-03-1": {
        "action": KEEP, "owner": "STORY-04-01",
        "why": "PRESERVE_REQUIRED, and correctly so: STORY-04-01 AC-4 introduces the verify stderr line, and "
               "STORY-04-03 rewrites cli.py and can regress it.",
    },
    "AC-STORY-04-03-5": {
        "action": KEEP, "owner": "STORY-04-01",
        "why": "PRESERVE_REQUIRED over the silent-stdout property STORY-04-01 introduces across its success paths.",
    },
    "AC-STORY-05-01-1": {"action": KEEP, "owner": "STORY-01-05",
                         "why": "PRESERVE_REQUIRED over the chain integrity STORY-01-05 introduces."},
    "AC-STORY-05-01-2": {"action": KEEP, "owner": "STORY-03-01",
                         "why": "PRESERVE_REQUIRED over the batch atomicity STORY-03-01 introduces."},
    "AC-STORY-05-01-3": {
        "action": KEEP, "owner": "REPOSITORY_CONVENTION",
        "why": "PRESERVE_REQUIRED over runner parity. No single story introduces it: requirements §11 makes every "
               "test unittest.TestCase-based, so parity holds from the first test onward and is green at this "
               "story's parent. Recorded explicitly because the introducer is a convention, not a criterion.",
    },
    "AC-STORY-05-02-2": {"action": KEEP, "owner": "REPOSITORY_CONVENTION",
                         "why": "See AC-STORY-05-01-3 — the same parity property, guarded once more over the whole "
                                "suite rather than one module."},
}

#: Where two stories declare CHANGE_REQUIRED on one requirement, the distinct behaviours that justifies.
DUPLICATE_FR_RATIONALE = {
    "FR-1": "STORY-01-01 introduces NFC normalization itself; STORY-01-05 introduces the rejection of a key that is "
            "empty after normalization. Different behaviours of one requirement.",
    "FR-2": "The hash chain is built in three layers, each a separate contract: STORY-01-02 the canonical encoding, "
            "STORY-01-03 the digest over it, STORY-01-05 the chaining of one line to the previous. None entails the "
            "others: a correct canonical_bytes says nothing about how a digest is taken, and a correct digest says "
            "nothing about what prev_hash a line carries.",
    "FR-12": "Four stories, four distinct parts of the exit-code contract. STORY-01-01 introduces the usage-error "
             "exit (2) that its own argparse surface establishes (PLAN-V2.1); STORY-04-01 the success exits (0) "
             "for apply and repair-tail; STORY-04-02 the error exits (3, 4, 5); STORY-04-03 the stderr status "
             "shapes. The scope note in STORY-04-01 states the split, and each story's criteria stay inside it.",
    "FR-13": "STORY-01-04 introduces the atomic write primitive, STORY-01-05 the durability of a single append, "
             "STORY-03-01 the crash behaviour of a multi-line batch. Three distinct guarantees.",
    "FR-14": "STORY-01-01 introduces the stdlib-only import surface, STORY-05-02 the coverage gate and its "
             "exclusion of test sources. The prohibition itself is NEGATIVE_INVARIANT in STORY-01-01 and "
             "STORY-05-03 and claims no introduction.",
}


def audit(epics: Path, prd: Path) -> dict:
    plan = parse_epics(epics.read_text(encoding="utf-8"))
    listed = plan.stories() if callable(plan.stories) else plan.stories
    stories = {s.id: s for s in listed}
    frs = sorted(set(re.findall(r"^#### (FR-\d+):", prd.read_text(encoding="utf-8"), re.M)),
                 key=lambda x: int(x.split("-")[1]))
    rows, errors, warnings = [], [], []
    change_owner: dict[str, list[str]] = {}
    for sid, s in stories.items():
        n = len(s.acceptance_criteria)
        for i in range(1, n + 1):
            code = f"AC-{sid}-{i}"
            decl = (s.ac_proof or {}).get(code) or {}
            mode, req = decl.get("proof_mode"), decl.get("requirement")
            j = JUDGED.get(code, {})
            behaviour = BEHAVIOUR.get(code)
            if behaviour is None:
                errors.append(f"{code}: the audit has no behaviour for this criterion — coverage is not 100%")
            owner = j.get("owner") or sid
            action = j.get("action") or KEEP
            row = {"ac_id": code, "story": sid, "requirement": req, "proof_mode": mode, "behaviour": behaviour,
                   "semantic_owner_story": owner, "upstream_dependencies": list(s.depends_on or []),
                   "another_story_claims_introduction": None, "necessarily_implied_upstream": owner != sid,
                   "action": action, "rationale": j.get("why") or
                   ("this story's own contract introduces the behaviour; no earlier story's responsibility entails it"
                    if mode == "CHANGE_REQUIRED" else
                    "the behaviour is introduced elsewhere and this story can regress it"
                    if mode == "PRESERVE_REQUIRED" else
                    "a prohibition that holds before and after this story; it claims no introduction")}
            for k in ("to_mode", "to_requirement", "also_add_change_to", "duplicate_of",
                      "downstream_disposition"):
                if k in j:
                    row[k] = j[k]
            if "to_mode" in j:
                row["already_applied_in_this_plan"] = (j["to_mode"] == mode and j.get("to_requirement") == req)
            if mode == "CHANGE_REQUIRED":
                change_owner.setdefault(str(req), []).append(code)
            rows.append(row)
    # one introduction owner per behaviour
    by_behaviour: dict[str, list[str]] = {}
    for r in rows:
        if r["proof_mode"] == "CHANGE_REQUIRED" and r["action"] not in (PRESERVE, MOVE):
            by_behaviour.setdefault(str(r["behaviour"]), []).append(r["ac_id"])
    dup_behaviour = {b: ids for b, ids in by_behaviour.items() if len(ids) > 1}
    for b, ids in dup_behaviour.items():
        errors.append(f"two stories claim introduction of the same behaviour ({b}): {', '.join(ids)}")
    for r in rows:
        same = by_behaviour.get(str(r["behaviour"]), [])
        r["another_story_claims_introduction"] = sorted(x for x in same if x != r["ac_id"]) or None
    # every requirement that a criterion names must have an introduction owner somewhere
    named = sorted({str(r["requirement"]) for r in rows})
    no_owner = [f for f in named if f not in change_owner]
    # traceability: every requirement the PRD declares must be named by at least one criterion of the plan
    untraced = [f for f in frs if f not in named]
    for f in untraced:
        errors.append(f"{f} is declared by the PRD but no criterion of the plan names it")
    for f in no_owner:
        errors.append(f"{f} is named by criteria but no story introduces it as CHANGE_REQUIRED")
    # PRESERVE_REQUIRED must protect something introduced elsewhere
    for r in rows:
        if r["proof_mode"] == "PRESERVE_REQUIRED" and r["semantic_owner_story"] == r["story"]:
            errors.append(f"{r['ac_id']}: PRESERVE_REQUIRED but its introducer is the story itself")
    # every normal story keeps at least one CHANGE_REQUIRED after the actions
    for sid, s in stories.items():
        kind = str(getattr(s, "story_type", "NORMAL") or "NORMAL").upper()
        after = [r for r in rows if r["story"] == sid
                 and (r.get("to_mode") or r["proof_mode"]) == "CHANGE_REQUIRED" and r["action"] != REMOVE]
        moved_in = [r for r in rows if r.get("also_add_change_to") == sid]
        after = after + moved_in
        if kind == "NORMAL" and not after:
            errors.append(f"{sid}: no CHANGE_REQUIRED criterion would remain after the audit's actions")
    for fr, ids in sorted(change_owner.items()):
        if len({i.rsplit("-", 1)[0] for i in ids}) > 1 and fr not in DUPLICATE_FR_RATIONALE:
            errors.append(f"{fr}: CHANGE_REQUIRED in several stories with no written rationale")
        elif len({i.rsplit("-", 1)[0] for i in ids}) > 1:
            warnings.append(f"{fr}: introduced across {len({i.rsplit('-', 1)[0] for i in ids})} stories — "
                            + DUPLICATE_FR_RATIONALE[fr])
    actions = {a: len([r for r in rows if r["action"] == a]) for a in (KEEP, MOVE, PRESERVE, REMOVE)}
    return {
        "artifact": "W1-PLAN-V2.1-OWNERSHIP-AUDIT",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "owner_decision": "FINAL PLAN CORRECTION, KERNEL REMAINS FROZEN (2026-09-21), sections 1-4",
        "method": "Each criterion is judged against the declared contracts of the plan and the frozen requirements: "
                  "a behaviour entailed by an upstream story's stated responsibility is owned upstream. What a model "
                  "happened to implement early is never the basis for a judgement; where diagnostic run 1 agrees, "
                  "that is recorded as corroboration only.",
        "plan": "W1-LEDGERLOCK-PLAN-V2",
        "requirements_in_prd": frs,
        "stories": len(stories), "criteria": len(rows),
        "criteria_covered_by_this_audit": len([r for r in rows if r["behaviour"]]),
        "coverage": "100%" if all(r["behaviour"] for r in rows) else "INCOMPLETE",
        "modes": {m: len([r for r in rows if r["proof_mode"] == m])
                  for m in ("CHANGE_REQUIRED", "PRESERVE_REQUIRED", "NEGATIVE_INVARIANT")},
        "actions": actions,
        "duplicate_introduction_of_one_behaviour": dup_behaviour,
        "requirements_without_an_introduction_owner": no_owner,
        "prd_requirements_no_criterion_names": untraced,
        "requirements_traceability": "100%" if not untraced else f"{len(frs) - len(untraced)}/{len(frs)}",
        "duplicate_requirement_rationale": DUPLICATE_FR_RATIONALE,
        "warnings": warnings, "errors": errors, "rows": rows,
        "pass": not errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epics")
    ap.add_argument("prd")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rec = audit(Path(a.epics), Path(a.prd))
    Path(a.out).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: rec[k] for k in ("stories", "criteria", "coverage", "modes", "actions", "pass")},
                     ensure_ascii=False))
    for e in rec["errors"]:
        print("  ERROR", e)
    for w in rec["warnings"]:
        print("  ·", w[:150])
    return 0 if rec["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
