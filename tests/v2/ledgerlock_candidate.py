"""The 2.0.0 LedgerLock bundle as this release can load it — for the tests that need its plan, its specs or its
criteria, not its approvals. This module is not a test.

`aisef bundle migrate` writes a candidate: the plan re-bound, and the approvals of the contracts a declared capability
change evaluates differently withheld (owner decision 2026-10-15, item 1), so the candidate does not load until they
are approved again. These tests do what the owner does, in memory and with a stand-in approver that no record keeps:
`approved` approves each contract the report says needs it through `bundle_cli.approve` — the same command — and
returns the bundle; nothing is written, and nothing here is the owner's approval."""

from __future__ import annotations

import functools
import json
import pathlib

from aisef2.app import bundle, bundle_cli

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGERLOCK_2_0_0 = ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json"
STAND_IN = "human:test-stand-in-for-the-owner"


def read() -> dict:
    return json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8"))


def approved(candidate: dict, report: dict) -> dict:
    """`candidate` with each contract of `report["needs_owner_reapproval"]` approved by the stand-in."""
    for row in (report["needs_owner_reapproval"] or {}).get("contracts", ()):
        candidate = bundle_cli.approve(candidate, row["contract"], STAND_IN, 1.0)
    return candidate


def loadable(doc: dict | None = None) -> dict:
    """The migrated bundle of `doc` (the 2.0.0 LedgerLock by default) with the withheld approvals approved by the stand-in."""
    return approved(*bundle_cli.migrate(read() if doc is None else doc))


@functools.lru_cache(maxsize=1)
def project() -> bundle.Project:
    return bundle.load(loadable())
