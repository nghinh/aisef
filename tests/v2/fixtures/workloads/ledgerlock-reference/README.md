# LedgerLock reference workload fixture (WP-2.0.3)

An independent reference for calibration and falsifiability in Cycle 2: a stdlib-only implementation of the
frozen LedgerLock requirements, an acceptance suite that observes it from outside, and named one-line mutants
that each violate one requirement.

| file | role |
|---|---|
| `REQUIREMENTS.md` | the frozen requirements, byte-identical to the LedgerLock repository's `docs/requirements.md` (sha256 `3a6a9995…`) |
| `reference/ledgerlock/` | the reference implementation, authored from `REQUIREMENTS.md` alone |
| `acceptance.py` | the acceptance suite: `python acceptance.py <tree>`; every observation in a fresh `python -I` subprocess |
| `MUTANTS.json` | the mutant catalog: one exact source change, one target requirement, expected and consequential failures |
| `mutants/<id>/<module>` | every mutant materialised from the catalog (`validation/qualification/p0_reference_fixture.py --materialise`) |
| `REQUIREMENTS-MAP.json` | the closed mapping requirement → reference behaviour → assertions → mutants |

The fixture is not the implementation under evaluation and imports nothing of AISEF or of any LedgerLock produced
by it. Nothing about ProductProof depends on these file names or their placement: the fixture supplies measured
behaviour only. Evidence: `closure-evidence/v2/cycle2/P0-REFERENCE-FIXTURE-FREEZE.json` (bound before the fixture
was written) and `P0-REFERENCE-FIXTURE.json` (the run).
