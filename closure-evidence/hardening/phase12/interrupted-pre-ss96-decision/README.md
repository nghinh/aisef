# PRE-SS96-DECISION — NOT FINAL QUALIFICATION EVIDENCE

The Phase 12 run started on 2026-09-20 at 13:57 and stopped cleanly at 15:16, before it completed, so that SS-96
could be resolved first (owner decision "STOP PHASE 12 CLEANLY — SS-96 MUST BE RESOLVED FIRST").

Preserved here, unedited:

* `differential-p12-00000.json`, `differential-p12-10000.json` — the two chunks that finished (seeds 0-19 999),
  10 000 traces each, 10 000/10 000 matched, 0 unexplained, 0 invariant violations, 0 exceptions.
* `diff-p12-0.log`, `diff-p12-10000.log` — their runner logs.
* `diff-p12-20000.log` — the log of the chunk that was interrupted at 246 s (seeds 20 000-29 999). It is empty
  because the runner writes its summary only when the chunk ends; no chunk file was written, so nothing was
  truncated.
* `MANIFEST.json` — the exact seed ranges, per-chunk counters, the product tree digest, the model and comparator
  digests, and how the run was stopped.

**These traces qualify nothing.** They were measured on product tree `42a29853`. If SS-96 is confirmed P1 the fix
changes that tree, and a dataset measured on another kernel can never be final evidence for it (owner section 9).
The next Phase 12 starts from zero on the new exact kernel; this dataset is never resumed into it.
