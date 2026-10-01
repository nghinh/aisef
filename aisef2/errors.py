"""Kernel error types shared across planes."""

from __future__ import annotations

import sys


class InvariantError(BaseException):
    """An architecture invariant was about to be violated (RFC §4). Uncontainable: it derives from `BaseException`,
    not `Exception`, so no `except Exception` boundary can hold it, and every broader kernel boundary re-raises it
    (validation/v2/except_boundaries.py audits that statically). It carries the module that raised it."""

    def __init__(self, message: str = "", *, invariant: str | None = None, module: str | None = None) -> None:
        super().__init__(message)
        self.invariant = invariant
        self.module = module or sys._getframe(1).f_globals.get("__name__")
