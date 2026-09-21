"""Kernel error types shared across planes."""


class InvariantError(Exception):
    """An architecture invariant was about to be violated. Never caught by kernel code (RFC §4)."""
