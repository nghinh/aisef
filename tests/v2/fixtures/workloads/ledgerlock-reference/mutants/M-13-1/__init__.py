"""LedgerLock reference implementation (AISEF V2 Cycle 2, WP-2.0.3).

An append-only, tamper-evident key/value ledger: a JSONL file whose lines form a SHA-256 hash chain, idempotent
mutations keyed by request id, all-or-nothing batches, a deterministic snapshot and a tail repair. Authored from
REQUIREMENTS.md (the frozen LedgerLock requirements) alone, with the standard library only. It is a reference for
calibration and falsifiability, not the implementation under evaluation.
"""

from ledgerlock.ledger import (
    ConflictError, CorruptionError, Ledger, Result, Verdict, append, batch_apply as apply_batch, snapshot, verify,
)

__all__ = ["ConflictError", "CorruptionError", "Ledger", "Result", "Verdict", "append", "apply_batch", "snapshot",
           "verify"]
