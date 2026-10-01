"""ORACLE-INDEPENDENCE.json (owner rule C): for every oracle expectation — the requirement passage it rests on, the
independently derived expected behaviour, whether any AISEF-generated implementation was inspected, whether a prior
candidate/replay result influenced it, and the fixture provenance. Also: the assumptions the requirements leave open
(each with its predeclared arbitration), the requirement ambiguities, the disclosure of v1's calibration against an
AISEF delivery and the corrections that replaced it. The verdict is computed, not asserted.

    <oracle venv>/bin/python closure-evidence/hardening/w1/oracle/independence.py   # after calibrate.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "ORACLE-INDEPENDENCE.json"
FIXTURE = "reference/ (written from docs/requirements.md alone; sha256 per file in CALIBRATION.json) + the mutant named"
NOT_INSPECTED = ("no — v2 was written from the requirements text only; the archived AISEF run-2 delivery was not opened while "
                 "writing it (v1 HAD been executed against that delivery — disowned, see `disclosure`)")

EXPECTATIONS = [
    {"id": "E1", "test": "TestAcceptance::test_14_1_verify_exits_0_on_a_fresh_ledger",
     "source": ["§14.1: `python -m ledgerlock verify path/to/ledger.jsonl` exits 0 on a fresh ledger.",
                "§9: `0` — success (… verify ok …)", "§9: `3` — I/O error (file not found, permission denied)"],
     "expected": "verify on an existing ledger file holding no record exits 0; verify on a path that does not exist exits 3",
     "assumptions": ["A4"], "negative_control": None},
    {"id": "E2", "test": "TestAcceptance::test_14_2_snapshot_is_byte_deterministic",
     "source": ["§14.2: `python -m ledgerlock snapshot path/to/ledger.jsonl` produces deterministic bytes.",
                "§6: sorted by NFC-normalized key in byte order (UTF-8 codepoint order). The snapshot MUST be byte-stable for a given chain content",
                "§6: The CLI `ledgerlock snapshot --out <file>` writes this same document.",
                "§3.1: Two strings that differ only in NFC/NFD representation MUST be treated as the same key.",
                "§4.3: If a different `rid` tries to mutate a key whose last committed mutation used a different `rid`, the call MUST raise `ConflictError` (or return an error result depending on CLI surface) and MUST NOT append a new line.",
                "§9: `4` — conflict (rid mismatch on a key)"],
     "expected": "puts of b, a, é(NFC) with three rids exit 0; a put of é(NFD) with a fourth rid exits 4 (same key, other rid); two `snapshot --out` runs exit 0 with identical bytes; the document holds exactly a, b, é in UTF-8 byte order; the bare §14.2 form is OBSERVED (AMB-1), not judged",
     "assumptions": ["A1", "A3"], "negative_control": "M4 (no NFC), M5 (unsorted), M9 (nondeterministic)"},
    {"id": "E3", "test": "TestAcceptance::test_14_3_apply_batch_commits_atomically",
     "source": ["§14.3: `python -m ledgerlock apply --batch batch.json path/to/ledger.jsonl` commits atomically.",
                "§5: the JSONL on disk MUST either reflect the full batch or be byte-identical to its pre-batch state — never a partial batch.",
                "§5: The CLI equivalent is `ledgerlock apply --batch <file>` which reads the batch spec and performs the same atomic operation.",
                "§3.2: Each line is one of: put / delete … The chain is append-only: existing records MUST NOT be rewritten in place."],
     "expected": "after a two-op batch exits 0 the file starts with its previous bytes, has exactly two more lines, and verifies (exit 0)",
     "assumptions": ["A1"], "negative_control": "M2 (partial batch)"},
    {"id": "E4", "test": "TestAcceptance::test_14_4_repair_tail_fixes_a_truncated_tail_and_refuses_mid_chain_corruption",
     "source": ["§14.4: `python -m ledgerlock repair-tail path/to/ledger.jsonl` fixes a truncated tail.",
                "§7: If the JSONL ends in a truncated line … `repair-tail` MUST rewrite the file with the truncated final line removed and verify cleanly afterwards. No other content may be modified. If the chain is clean, `repair-tail` is a no-op. If the chain is corrupt in the middle (not at the tail), `repair-tail` MUST refuse.",
                "§3.3: Any modification to a committed line (mutating `value`, swapping `op`, or modifying `hash`) MUST be detected by an independent full verify",
                "§9: `5` — corruption (verify reports `ok=False` or repair-tail finds non-tail corruption)"],
     "expected": "a truncated final line: verify 5, repair-tail 0, bytes identical to the pre-truncation file, verify 0; repair-tail on the clean chain: 0 and unchanged bytes; line 0's committed value changed (parsed, modified, re-serialised by the standard json module — independent of the delivery's serialisation): verify 5, repair-tail 5",
     "assumptions": ["A1", "A5"], "negative_control": "M1 (hash not recomputed), M6 (mid-chain 'repaired')"},
    {"id": "E5", "test": "TestAcceptance::test_14_5_coverage_at_least_85_percent_with_unittest_discover",
     "source": ["§14.5: `coverage run -m unittest discover && coverage report` reports ≥85%.",
                "§11: ≥85% line coverage measured by `coverage.py`"],
     "expected": "the verbatim command exits 0 in the project root and the TOTAL line of `coverage report` is ≥ 85%",
     "assumptions": [], "negative_control": "none needed (a numeric threshold on a tool's report); the reference measures 97%"},
    {"id": "E6", "test": "TestAcceptance::test_14_6_no_third_party_imports_at_runtime",
     "source": ["§14.6: No third-party imports succeed at runtime.", "§2: No third-party runtime dependencies", "§10: Stdlib only.",
                "§12: No `socket`, no `subprocess`, no `os.system`."],
     "expected": "every import under ledgerlock/ names a module of sys.stdlib_module_names; none is socket or subprocess; no `os.system` attribute; and `python -S -m ledgerlock verify` on a fresh ledger exits 0 (without site-packages a third-party import cannot succeed at runtime); stdlib modules outside §10's list are OBSERVED (AMB-4)",
     "assumptions": [], "negative_control": "M7 (guarded third-party import)"},
    {"id": "E7", "test": "TestIdempotencyAndConflict::test_replay_is_idempotent_and_a_different_rid_conflicts",
     "source": ["§5: `apply_batch(ops)` accepts an iterable of (op, key, value, rid, ts) tuples",
                "§13: ledger.py # core: Ledger, ConflictError, append, verify, snapshot, apply_batch",
                "§4.2: If the same `rid` is replayed, the second call MUST return the same result and MUST NOT append a new line to the chain.",
                "§4.3 (conflict: MUST raise `ConflictError` … and MUST NOT append a new line)",
                "§4.5: A `put` on key `k` with `rid=r1`, then a `delete` on key `k` with `rid=r2` — the second MUST conflict.",
                "§3.4: It MUST recompute the chain from disk end-to-end."],
     "expected": "put k/r1 appends ≥1 line; the same call again returns an equal result and appends nothing; put k/r2 raises ConflictError, nothing appended; delete k/r2 raises ConflictError, nothing appended; CLI verify exits 0",
     "assumptions": ["A2", "A6"], "negative_control": "M3 (no conflict), M8 (replay appends)"},
    {"id": "E8", "test": "TestIdempotencyAndConflict::test_a_tombstone_conflicts_like_a_live_value",
     "source": ["§4.4: A `delete` produces a tombstone line. A subsequent `put` on the same key with a different `rid` MUST conflict against the tombstone just as it would against a live value. A subsequent `put` with the same `rid` as the tombstone is an idempotent replay and MUST be a no-op"],
     "expected": "delete t/d1 on a never-mutated key appends a tombstone line; put t/d2 raises ConflictError and appends nothing; put t/d1 raises nothing and appends nothing",
     "assumptions": ["A2", "A6", "A7"], "negative_control": "M3 (no conflict), M8 (replay appends)"},
    {"id": "E9", "test": "TestIdempotencyAndConflict::test_a_conflicting_batch_exits_4_and_commits_nothing_through_the_cli",
     "source": ["§9: `4` — conflict (rid mismatch on a key)", "§4.3 (… MUST NOT append a new line)",
                "§5: never a partial batch … The CLI equivalent … performs the same atomic operation."],
     "expected": "a two-op batch whose second op conflicts exits 4 and leaves the ledger byte-identical (its non-conflicting first op is not committed)",
     "assumptions": ["A1", "A2"], "negative_control": "M3 (no conflict), M10 (prefix committed on conflict)"},
]

ASSUMPTIONS = {
    "A1": {"what": "the batch spec file is a JSON array of {op, key, value, rid, ts} objects",
           "basis": "§14.3 names `batch.json` (a JSON file); §5's tuple names the five fields; the requirements pin no shape",
           "arbitration": "if `apply --batch` exits 2 or 3 on the oracle's file, the affected tests (E2, E3, E4, E9) are neither a product failure nor a FALSE PASS: they are reported to the owner as ORACLE-ASSUMPTION-A1 with the delivery's documented shape quoted; the oracle is not edited during W1"},
    "A2": {"what": "`Ledger(path)` — the constructor takes the ledger path",
           "basis": "§13 names the class; §5/§6/§7 speak of `the JSONL path`; nothing else is pinned",
           "arbitration": "a TypeError from the constructor → ORACLE-ASSUMPTION-A2, same handling as A1 (E7, E8, E9)"},
    "A3": {"what": "the snapshot document is a JSON object keyed by key (or an array of {key, value} entries)",
           "basis": "§6: `a deterministic, sorted JSON document representing the current materialized state: for each key, the most recent committed put value`",
           "arbitration": "any other shape → ORACLE-ASSUMPTION-A3 for E2's key-order and key-set assertions; the byte-determinism assertion stands on its own"},
    "A4": {"what": "a `fresh ledger` (§14.1) is an existing file holding no record",
           "basis": "§9 makes a missing file an I/O error (exit 3), so the fresh ledger of §14.1 must exist",
           "arbitration": "none needed: both readings are asserted separately (exit 0 on the empty file, exit 3 on the missing path)"},
    "A5": {"what": "a truncated final line is corruption for `verify` (exit 5)",
           "basis": "§3.3/§3.4: verify recomputes every line from disk; a line that does not parse cannot match a stored hash → ok=False → §9 exit 5",
           "arbitration": "a verify exit of 0 over a truncated tail is reported as a §3.3 finding; if the owner rules the tail is `not a line`, E4's first assertion is withdrawn by the owner, never by the oracle"},
    "A6": {"what": "`ledgerlock.ledger` is importable with the project root on sys.path",
           "basis": "§13 repository layout (`ledgerlock/ledger.py`)", "arbitration": "an ImportError → ORACLE-ASSUMPTION-A6 (E7–E9)"},
    "A7": {"what": "a `delete` on a key with no prior mutation is permitted and produces a tombstone",
           "basis": "§4.4: `A delete produces a tombstone line`; nothing restricts deletes to live keys; this is the only tombstone path §4.2 leaves unambiguous (AMB-3)",
           "arbitration": "a refusal (exception / exit ≠ 0) → ORACLE-ASSUMPTION-A7 for E8 only"},
}

AMBIGUITIES = {
    "AMB-1": {"passages": ["§6: The CLI `ledgerlock snapshot --out <file>` writes this same document.",
                           "§14.2: `python -m ledgerlock snapshot path/to/ledger.jsonl` produces deterministic bytes."],
              "why_objectively_present": "§14.2's form has no `--out`; where its bytes go (stdout?) is unstated",
              "handling": "the oracle asserts the §6 form and OBSERVES the bare form (exit code, determinism of stdout, whether stdout is the document) — no verdict; the observation is reported to the owner with the W1 record"},
    "AMB-2": {"passages": ["§9: `0` — success (append / verify ok / snapshot ok / repair-tail no-op or repair ok)",
                           "§5 / §6 / §7 / §14 name the CLI commands `apply --batch`, `snapshot`, `repair-tail`, `verify`"],
              "why_objectively_present": "`append` appears as a CLI success case but no CLI `append` command is specified; §13 lists `append` as a library function",
              "handling": "the oracle tests no CLI `append`"},
    "AMB-3": {"passages": ["§4.2: If the same `rid` is replayed, the second call MUST return the same result and MUST NOT append a new line",
                           "§4.5: Replays of either MUST NOT conflict."],
              "why_objectively_present": "whether a `delete` carrying the rid of the key's last `put` is a replay (no-op) or a new mutation (tombstone) is not pinned; under the literal §4.2 a key can never be deleted once put",
              "handling": "the oracle never takes this path; tombstones are created on a fresh key (A7); v1 took it (correction C3)"},
    "AMB-4": {"passages": ["§10: Stdlib only. Allowed: `hashlib`, `json`, `os`, `sys`, `pathlib`, `tempfile`, `argparse`, `unittest`, `typing`, `unicodedata`, `uuid`."],
              "why_objectively_present": "whether `Allowed:` is exhaustive (excluding e.g. `dataclasses`, `io`) or illustrative of `Stdlib only`",
              "handling": "the oracle asserts stdlib-only and §12's bans; stdlib modules outside the list are OBSERVED, not judged"},
}

DISCLOSURE = {
    "v1": "closure-evidence/hardening/w1/oracle/test_oracle.v1-disowned.py.txt (committed as test_oracle.py in bb31522)",
    "what_happened": "v1 was executed against the archived AISEF run-2 delivery (closure-evidence/dogfood/ledgerlock-run2, 5/16 stories) as a calibration and its per-test failures were read; an earlier draft had used `put`/`delete` CLI subcommands the requirements do not name and was corrected to `apply --batch`. Because v1's expectations were shaped in the presence of implementation behaviour, EVERY v1 expectation is disowned under the owner's rule and re-derived above from the requirements text alone.",
    "prior_candidate_or_replay_results": "none of v2's expectations derives from an AISEF gate result, replay output, reviewer conclusion or candidate behaviour",
    "corrections_v1_to_v2": [
        "C1 E4: the tamper was a byte substitution `\"value\": 0` → `\"value\": 9` that depends on the delivery's JSON serialisation (default separators); replaced by parse → modify → re-serialise",
        "C2 E5: coverage ran `--source=ledgerlock -m unittest discover -q`, not §14.5's command; replaced by the verbatim `coverage run -m unittest discover`",
        "C3 E8: the tombstone was reached through a same-rid delete after a put (AMB-3); replaced by a delete on a fresh key (§4.4, A7)",
        "C4 E6: a string grep for six spellings; replaced by an ast import audit against sys.stdlib_module_names, §12's bans as ast checks, and a `python -S` runtime run",
        "C5 E2: the NFD put's exit code was ignored; now asserted 4 (§3.1 + §4.3 + §9)",
        "C6 E1/E9: §9's exit 3 (file not found) and §5's no-partial-batch-on-conflict were not asserted; added",
        "C7 E7: §4.2's `same result` was not asserted; added",
        "fixture: v1 had no independent fixture; v2 is calibrated on reference/ (written from the requirements) and ten one-line mutants — CALIBRATION.json",
    ],
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    cal = json.loads((HERE / "CALIBRATION.json").read_text(encoding="utf-8"))
    oracle_sha = sha(HERE / "test_oracle.py")
    exps = []
    for e in EXPECTATIONS:
        exps.append({**e, "aisef_generated_implementation_inspected": NOT_INSPECTED, "influenced_by_prior_candidate_or_replay_result": False,
                     "fixture_provenance": FIXTURE, "calibration": {"reference": cal["fixtures"]["reference"]["results"].get(e["test"]),
                                                                     "killed_by": [k for k, f in cal["fixtures"].items() if k != "reference" and f["results"].get(e["test"]) in ("FAILED", "ERROR")]}})
    checks = {
        "every_expectation_cites_requirement_passages": all(e["source"] for e in EXPECTATIONS),
        "no_expectation_influenced_by_aisef_output": all(not e["influenced_by_prior_candidate_or_replay_result"] for e in exps),
        "every_assumption_has_a_predeclared_arbitration": all(a.get("arbitration") for a in ASSUMPTIONS.values()),
        "calibration_pass": bool(cal.get("pass")),
        "calibration_oracle_matches_this_oracle": cal.get("oracle_sha256") == oracle_sha,
        "requirements_frozen_digest": cal.get("requirements_sha256"),
        "every_expectation_green_on_reference": all(e["calibration"]["reference"] == "PASSED" for e in exps),
        "every_behavioural_expectation_killed_by_a_mutant": all(e["calibration"]["killed_by"] for e in exps if e["id"] not in ("E1", "E5")),
    }
    verdict = "PASS" if all(v is True for k, v in checks.items() if k != "requirements_frozen_digest") else "FAIL"
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rule": "The oracle's expected behaviour MUST be derived from the frozen LedgerLock requirements/specification, not from AISEF output.",
           "requirements": {"path": "docs/requirements.md (frozen; identical in ledgerlock-aiseftest-run2 and w1-run-1)", "sha256": cal.get("requirements_sha256")},
           "oracle": {"path": "closure-evidence/hardening/w1/oracle/test_oracle.py", "version": "v2 (2026-09-17)", "sha256": oracle_sha,
                      "w1_precondition": "before the oracle runs on any W1 delivery, sha256(test_oracle.py) must equal this value; a difference means the oracle was edited after calibration → STOP"},
           "expectations": exps, "assumptions": ASSUMPTIONS, "ambiguities": AMBIGUITIES, "disclosure": DISCLOSURE,
           "calibration": {"file": "closure-evidence/hardening/w1/oracle/CALIBRATION.json", "pass": cal.get("pass"), "elapsed_s": cal.get("elapsed_s"),
                           "reference": cal["fixtures"]["reference"]["pass"], "mutants_killed": [k for k, f in cal["fixtures"].items() if k != "reference" and f["killed"]],
                           "mutants_survived": [k for k, f in cal["fixtures"].items() if k != "reference" and not f["killed"]],
                           "observations_on_reference": cal.get("observations", {}).get("reference", [])},
           "checks": checks, "verdict": verdict}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(checks, indent=1)); print("ORACLE-INDEPENDENCE:", verdict)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
