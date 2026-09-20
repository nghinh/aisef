# VALID HISTORICAL EVIDENCE — NOT FINAL QUALIFICATION EVIDENCE

The complete single-kernel Phase 12 dataset for product tree `a2f6e76b…`.

Owner decision 2026-09-20 ("STOP PROFILE HUNTING, FIX W1 PLAN + TDD PROOF POLICY", section 15): the TDD proof policy V2 changes `aisef/`, so the kernel this dataset measured (candidate 40393cda89db, TDD_POLICY_V1) is superseded.

The product tree changed, so this dataset is **valid historical evidence** and regression history, and it is **not**
qualification evidence for the new kernel. The new dataset is run in full against the new product tree and lives at
`closure-evidence/hardening/differential-p12-*.json` with its own identity, integrity, manifest and coverage
records. Nothing here was edited; the files were moved with `git mv`.
