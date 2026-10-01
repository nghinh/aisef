"""Tier PLAN of the V2 harness: RFC §4 invariants I–IX are armed here, before any test module of the tier is imported
(WP-5.5; `arm` registers, fails closed, and marks the nine armed for this tier in this process)."""

from aisef2.invariants.registry import Tier, arm

ARMED = arm(Tier.PLAN)
