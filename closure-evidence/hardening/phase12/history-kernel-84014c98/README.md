# VALID HISTORICAL EVIDENCE — NOT FINAL QUALIFICATION EVIDENCE

The complete single-kernel Phase 12 dataset for product tree `84014c980e75…` (git faf3ecd…abad2a6, run 2026-09-17
06:36 → 13:20): 100 000 / 100 000 traces matched, 0 unexplained, 0 invariant violations, 0 exceptions, 0 silent skips,
one kernel digest, manifest hard requirements all met, 26/26 reachable transitions, 28/28 fault kinds, 378/378 fault
pairs. It closed Phase 12 for that kernel and qualified nothing after SS-65.

Owner decision 2026-09-17 ("FIX SS-65 AT CAPABILITY-MODEL LEVEL AND RE-QUALIFY", item 12): the SS-65 fix changes
`aisef/`, so this dataset is **valid historical evidence** and regression history, and it is **not** final
qualification evidence for the new kernel. The final dataset is re-run in full against the new product tree and lives
at `closure-evidence/hardening/differential-p12-*.json` with its own identity, integrity, manifest and coverage
records. Nothing here was edited; the files were moved with `git mv`.
