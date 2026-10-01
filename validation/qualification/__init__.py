"""P7 / QP-7 — the Q0→Q3 qualification harness (RFC §27; owner authorization "AISEF V2 — P7 / QP-7 EXECUTION
AUTHORIZATION / Q0 → Q1 → Q2 → Q3 QUALIFICATION", 2026-09-27).

This package is the harness, not a Q0 checker: `validation/v2/` holds the checkers (each calibrated against a
committed known-bad fixture), `validation/qualification/` runs them and the named semantic, adequacy and fault cases
against the frozen qualification subject, and writes typed records under `closure-evidence/v2/Q0-Q3/`. Its own
digest is bound into every record (§25). It executes no provider and no project admission.

    python -P validation/qualification/run.py --rungs q0 q1 q2 q3 [--print]     # in order; stops at the first non-GREEN
    python -P validation/qualification/summary.py [--check]                     # assemble / verify SUMMARY.json
"""
