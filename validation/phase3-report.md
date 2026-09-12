# Phase 3 end-to-end validation

16/16 checks passed.

## Detailed observations

- [PASS] 1.config defaults surface: all four knobs at default 0/false
- [PASS] 2.qualify failed+over-max-retries → STOP: max_retries (2) reached on S1
- [PASS] 2.qualify failed+retryable → VERIFY: 1 story/ies ready for verification: S1
- [PASS] 2.qualify all-verified → MERGE: 2 story/ies ready to merge: S1, S2
- [PASS] 3.budget no-caps short-circuit: 999/999 accepted
- [PASS] 3.budget cap-block before settle: blocked=True spent=0.0000
- [PASS] 3.budget refund on exception: spent=0.0000 after refund
- [PASS] 3.budget settle on success: spent=0.4000
- [PASS] 4.identity probe matches bound run: r1=True r2=False
- [PASS] 4.identity lease re-acquire after release: second fd=4
- [PASS] 5.findings round-trip id-stable: lines=1 ids-match=True
- [PASS] 5.findings stable id across same/different file: same=True different_id=70bd8620
- [PASS] 6.after_event excludes older higher-seq event: paths=['new.py'] (expected ['new.py']; old.py seq=165 pre-dates test seq=144 in time)
- [PASS] 6.seq-based view would have included stale event: seq_view=['old.py', 'new.py'] (illustrative: shows why the fix matters)
- [PASS] 7.lock sidecar serialises concurrent reserves: second guard raised BudgetExceeded while first held the lock
- [PASS] 7.cap check counts outstanding reservations: 0.06 outstanding + 0.06 proposed > 0.10 cap blocks at reserve
