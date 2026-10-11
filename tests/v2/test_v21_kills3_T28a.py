"""Survivor batch T28a (V2.1 mutation campaign 2): the budget block's `inherited` share, the redaction of a stream that
is not there, and the order in which the ownership check names its violators.

Each class states the requirement it pins. The three targets and their mutants:

* aisef2/app/client.py::Budget.account [6, 12, 13, 14]
* aisef2/app/client.py::redact [4]
* aisef2/plan/static_admission.py::check_ownership [10, 17]
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import client  # noqa: E402
from tests.v2.p2 import test_static_admission as base  # noqa: E402  (its fixtures; none of its test classes)

LIMITS = {"provider_requests": 60, "turns": 100, "input_tokens": 10_000, "output_tokens": 1_000}
PREFLIGHT = {"provider_requests": 1, "turns": 0, "input_tokens": 10, "output_tokens": 1}
KEYS = ("provider_requests", "turns", "input_tokens", "output_tokens")


def step(i: int = 100, o: int = 10) -> str:
    return json.dumps({"type": "step_finish", "part": {"tokens": {"input": i, "output": o, "reasoning": 0}}})


class Temp(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()


# ------------------------------------------------------------------------------------------------ Budget.account

class BudgetBlockNamesTheLineagesShare(Temp):
    """A continuation's `spent` already holds what its lineage spent (the ceilings are the lineage's: ADR-8). The
    record's budget block says how much of it that was: `inherited`, the four ceiling counters of the lineage and
    nothing else — present exactly when the lineage spent something, absent in a run that inherited nothing. An
    operator reading RUN.json is the reader (no code reads the field; `--verify` re-derives `spent` alone), so the
    key name and the per-counter values are what is pinned, not any rendering.

    Pins aisef2/app/client.py::Budget.account [6, 12, 13, 14]."""

    LINEAGE = {"provider_requests": 3, "turns": 4, "input_tokens": 500, "output_tokens": 50}
    PLAIN_KEYS = {"limits", "preflight", "spent", "reached", "limitation"}

    def budget(self, inherited: dict | None = None) -> client.Budget:
        (self.tmp / "s.jsonl").write_text(step(100, 10) + "\n", encoding="utf-8")   # this run's own: 1 turn, 100/10
        return client.Budget(LIMITS, dict(PREFLIGHT), self.tmp, lambda: 1, inherited)

    def test_a_continuation_states_the_lineages_share_inside_what_it_spent(self):
        # what run.execute hands the Budget is lineage.lineage_account's whole answer: more than the four counters
        given = {**self.LINEAGE, "runs": [{"run": "first"}], "unaccounted": []}
        acc = self.budget(given).account()
        self.assertEqual(set(acc), self.PLAIN_KEYS | {"inherited"})
        self.assertEqual(acc["inherited"], self.LINEAGE)                       # the four counters, nothing else
        self.assertTrue(all(type(v) is int for v in acc["inherited"].values()))
        own = {"provider_requests": 1, "turns": 1, "input_tokens": 100, "output_tokens": 10}
        self.assertEqual({k: acc["spent"][k] for k in KEYS},
                         {k: PREFLIGHT[k] + self.LINEAGE[k] + own[k] for k in KEYS})
        self.assertIsNone(acc["reached"])
        self.assertEqual(acc["limits"], LIMITS)
        self.assertEqual(acc["preflight"], PREFLIGHT)

    def test_any_one_counter_the_lineage_spent_is_enough_and_the_others_are_named_zero(self):
        for spent in KEYS:      # a lineage that only made requests, or only ran turns, still spent something
            with self.subTest(only=spent):
                acc = self.budget({spent: 7}).account()
                self.assertIn("inherited", acc)
                self.assertEqual(acc["inherited"], {k: 7 if k == spent else 0 for k in KEYS})

    def test_a_run_that_inherited_nothing_states_no_share(self):
        plain = self.budget().account()
        self.assertEqual(set(plain), self.PLAIN_KEYS)
        for nothing in ({}, {k: 0 for k in KEYS}, {**{k: 0 for k in KEYS}, "unaccounted": [], "runs": []}):
            with self.subTest(inherited=nothing):
                acc = self.budget(nothing).account()
                self.assertNotIn("inherited", acc)
                self.assertEqual(acc, plain)                                   # the rest of the block is untouched

    def test_the_share_is_the_only_difference_between_a_continuation_and_a_plain_run(self):
        plain, continued = self.budget().account(), self.budget(self.LINEAGE).account()
        self.assertEqual({k: v for k, v in continued.items() if k not in ("inherited", "spent")},
                         {k: v for k, v in plain.items() if k != "spent"})
        self.assertEqual({k: continued["spent"][k] - plain["spent"][k] for k in KEYS}, self.LINEAGE)


# ------------------------------------------------------------------------------------------------ redact

class RedactingAStreamThatIsNotThere(Temp):
    """`redact` answers how many values it replaced, an int the callers record as the session's `redacted` count. A
    stream that does not exist has nothing replaced: 0 — a count, never None — and redaction must not create it
    (it would fabricate session evidence).

    Pins aisef2/app/client.py::redact [4]."""

    def test_nothing_is_replaced_and_nothing_is_created(self):
        missing = self.tmp / "absent.jsonl"
        n = client.redact(missing, ("abcdefgh12", "another-secret"))
        self.assertEqual(n, 0)
        self.assertIs(type(n), int)                                            # a count: not None, not False
        self.assertFalse(missing.exists())
        self.assertEqual(os.listdir(self.tmp), [])


# ------------------------------------------------------------------------------------------------ check_ownership

def named(problems: list[str], kind: str) -> list[tuple[str, int]]:
    """(identifier, count) of every problem of one kind, in the order the check reports them: the criterion and the
    number of stories that own it, or the spec and the number of INTRODUCE owners it has."""
    pattern = {"criterion": r"^criterion (\S+) belongs to (\d+) stories", "spec": r"^spec (\S+) has (\d+) INTRODUCE owners"}
    return [(m[1], int(m[2])) for m in (re.match(pattern[kind], p) for p in problems) if m]


class OwnershipNamesItsViolatorsInIdOrder(unittest.TestCase):
    """The static admission's ownership check lists the criteria that belong to other than one story, then the specs
    with more than one INTRODUCE owner, each once and each half in identifier order, whatever order the plan lists
    its obligations in (the module's canonical-order contract: the same findings are one result, and the result's
    digest binds the list). Reversing the obligations changes nothing.

    Pins aisef2/plan/static_admission.py::check_ownership [10, 17]."""

    CRITERIA = [("C2", 3), ("C5", 2), ("C9", 4)]            # (criterion, the number of stories that own it), by id
    SPECS = [("PPS-a", 3), ("PPS-b", 2), ("PPS-c", 4)]      # (spec, the number of its INTRODUCE owners), by id

    def over_owned_criteria(self):
        # First mentioned in the order C5, C9, C2. The id order C2, C5, C9 is then neither the order of mention, nor its
        # reverse, nor the order of the story counts, ascending or descending: only sorting by id gives it.
        v = base.Role.VERIFY
        return tuple(base.ob(c, "BC-ADD", f"S{n}", v)
                     for c, k in (("C5", 2), ("C9", 4), ("C2", 3)) for n in range(1, k + 1))

    def over_introduced_specs(self):
        # The same shape for the specs, first listed in the order PPS-b, PPS-c, PPS-a. Every INTRODUCE has a criterion of
        # its own, in one story, so only the specs are named. (The ownership check never resolves a spec: the ids need
        # not be the fixture's two.)
        i = base.Role.INTRODUCE
        criteria = (f"C{n}" for n in range(1, 100))
        return tuple(base.ob(next(criteria), spec, "S1", i) for spec, k in (("PPS-b", 2), ("PPS-c", 4), ("PPS-a", 3))
                     for _ in range(k))

    def test_criteria_are_named_in_id_order_once_each_with_their_story_count(self):
        obligations = self.over_owned_criteria()
        got = base.sa.check_ownership(base.plan(obligations), base.INPUTS)
        self.assertEqual(len(got), 3)
        self.assertEqual(named(got, "criterion"), self.CRITERIA)
        self.assertEqual(named(got, "spec"), [])
        self.assertEqual(got, base.sa.check_ownership(base.plan(tuple(reversed(obligations))), base.INPUTS))

    def test_specs_are_named_in_id_order_once_each_with_their_owner_count(self):
        obligations = self.over_introduced_specs()
        got = base.sa.check_ownership(base.plan(obligations), base.INPUTS)
        self.assertEqual(len(got), 3)
        self.assertEqual(named(got, "spec"), self.SPECS)
        self.assertEqual(named(got, "criterion"), [])
        self.assertEqual(got, base.sa.check_ownership(base.plan(tuple(reversed(obligations))), base.INPUTS))

    def test_the_order_is_the_admission_s_too_so_its_digest_does_not_depend_on_the_listing(self):
        obligations = self.over_owned_criteria()
        forward = base.ENGINE.admit(base.plan(obligations), base.INPUTS)
        backward = base.ENGINE.admit(base.plan(tuple(reversed(obligations))), base.INPUTS)
        ownership = next(c for c in forward.checks if c.name == "ownership")
        self.assertFalse(ownership.passed)
        self.assertEqual(named(list(ownership.problems), "criterion"), self.CRITERIA)
        self.assertEqual(forward.result_digest, backward.result_digest)


if __name__ == "__main__":
    unittest.main()
