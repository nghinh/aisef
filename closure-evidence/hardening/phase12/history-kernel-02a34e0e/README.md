# VALID HISTORICAL EVIDENCE — NOT FINAL QUALIFICATION EVIDENCE

The complete single-kernel Phase 12 dataset for product tree `02a34e0e63ed…` (KERNEL_CANDIDATE af94372dd186, the
kernel of the W0 record that was VOIDED on 2026-09-18 for SS-81 — closure-evidence/hardening/W0-INVALIDATION-SS81.json):
100 000 / 100 000 traces matched, 0 unexplained, 0 invariant violations, 0 exceptions, 0 silent skips, one kernel
digest, manifest hard requirements met.

Owner decision 2026-09-18 ("FIX SS-81 FAMILY, VOID W0, THEN REQUALIFY", section 10): the SS-81 family fix changes
`aisef/`, so this dataset is **valid historical evidence** and regression history, and it is **not** qualification
evidence for the new kernel. The new dataset is run in full against the new product tree and lives at
`closure-evidence/hardening/differential-p12-*.json` with its own identity, integrity, manifest and coverage records.
Nothing here was edited; the files were moved with `git mv`.
