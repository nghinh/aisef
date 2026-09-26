"""Systematic hardening program (owner directive 2026-09-16, `docs/INVARIANTS.md`).

Tests here are written RED-first against the frozen 1.7.6 baseline. A reproducer for a
defect that is registered but not yet fixed is marked ``@unittest.expectedFailure`` and
names the defect id; when the family-level fix lands the marker must be removed in the
same commit (an unexpected success fails the suite on purpose).
"""
