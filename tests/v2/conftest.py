"""pytest entry for the V2 tiers (the suite itself runs under unittest): the tiers arm RFC §4's invariants in their
package `__init__` modules, which pytest imports like unittest does; this file only makes that explicit."""

from aisef2.invariants.registry import Tier, arm

ARMED = arm(Tier.ROOT)
