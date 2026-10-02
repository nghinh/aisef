"""K-NOWORK-001 (owner ruling 'AISEF V2 — K-NOWORK-001 MEASURED ARCHITECTURE CORRECTION', 2026-10-02; RFC §13, §14) —
recorded separately from K-PRESAT-001, whose history is not rewritten.

The measured defect (the offline rehearsal of DELIVERY-EXPERIMENT-1; QP-2.9 attempt 2, STORY-05-01): a story admitted
with no product behaviour left to introduce — every INTRODUCE obligation PRE_SATISFIED, its remaining PRESERVE / VERIFY
obligations already SATISFIED at the parent — was still sent to the developer, because a satisfied PRESERVE and any
VERIFY are READY (§13). The developer had nothing legitimate to change; engineering adequacy then judged the no-op /
tests-only result VACUOUS / IRRELEVANT, and a correct product was rolled back.

The ruling: the developer has work only where an INTRODUCE obligation is READY. When none is, AND every obligation is
INTRODUCE + PRE_SATISFIED, or PRESERVE + SATISFIED, or VERIFY + SATISFIED: no developer call, no developer budget, no
engineering adequacy, candidate = parent — and every obligation still proved at the candidate by both parties, review
and security as before, the post-merge proof, PLAN_DRIFT for each PRE_SATISFIED INTRODUCE. No new disposition; the
admission's own facts decide.

The cases, through the one real path (the Cycle-1 fixture of test_p6_orchestration, nothing mocked):

  A  INTRODUCE PRE_SATISFIED + PRESERVE SATISFIED + blocking tests policy   -> no developer, commit at the parent
  B  INTRODUCE PRE_SATISFIED + VERIFY SATISFIED                             -> the same
  C  INTRODUCE READY + PRESERVE SATISFIED                                   -> the developer and adequacy run, as before
  D  INTRODUCE PRE_SATISFIED + PRESERVE not satisfied                       -> PRECONDITION_BROKEN, as before
  E  no INTRODUCE READY + VERIFY UNSATISFIED                                -> NOT this correction's case: nothing new is
     routed for it, the existing developer path is kept (VERIFY_NO_INTRODUCER_UNSATISFIED: the owner's to rule)

On the kernel before the correction (d427299, tree 4fe9ccaa) A and B are red — the developer is called and the story
rolled back — and C, D, E are green: closure-evidence/v2/cycle2/K-NOWORK-001-REHEARSAL.json records both runs.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole as R, Owner  # noqa: E402
from tests.v2 import test_c2_k_presat_001 as presat  # noqa: E402
from tests.v2 import test_p6_orchestration as e2e  # noqa: E402

P = e2e.P
#: `mul` exists and answers wrongly: a VERIFY of it is measured UNSATISFIED at the parent (an absent `mul` would be a
#: broken precondition instead — case D's row)
MUL_WRONG = "def mul(a, b):\n    return a + b\n"


class Fixture(presat.Fixture):
    def plan(self, *triples):
        """A plan at main's tip: each (criterion, spec, role) an obligation of S1."""
        return e2e.plan_of(self.merger.base(), *(e2e.obligation(c, s.id, "S1", role) for c, s, role in triples))

    def admitted(self) -> dict:
        rows = self.events("story/admitted", "S1")
        self.assertEqual(len(rows), 1)
        return rows[0].data

    def assertNoDeveloperWork(self, r, parent: str, dispositions: dict, pre_satisfied: tuple[str, ...]) -> None:
        """Everything the ruling names for the no-developer-work path."""
        self.assertCommitted(r)
        self.assertAttempts(r, ["COMMIT"])                                        # commit / success, no retry, no rollback
        self.assertEqual((r.revision, self.merger.base()), (parent, parent))      # candidate == parent: nothing landed
        a = self.admitted()
        # the admission's facts are the RFC's, untouched: a satisfied PRESERVE and a VERIFY are READY (§13)
        self.assertEqual((a["dispositions"], a["admitted"]), (dispositions, True))
        self.assertEqual(self.requests(Owner.DEVELOPER), [])                      # developer / provider execution skipped
        b = self.run.state(P.BUDGETS)
        self.assertEqual((b["developer"], b["retries"]), ({}, {}))               # developer budget consumed = 0
        self.assertEqual(self.failures("S1"), [])                                 # no DEVELOPER failure from the skipped stages
        self.assertEqual(self.events("story/retry", "S1"), [])
        self.assertEqual(self.events("story/rollback", "S1"), [])
        self.assertEqual(self.events("tests/adequacy", "S1"), [])                 # engineering adequacy skipped
        self.assertEqual([x for x in self.rows("S1") if x[0] == "S1:quality"], [])
        drift = self.events("story/plan-drift", "S1")                             # PLAN_DRIFT for each PRE_SATISFIED INTRODUCE
        self.assertEqual([e.data["criterion_id"] for e in drift], list(pre_satisfied))
        # every obligation's spec is executed at the candidate by both parties (independent verification), and again
        # after the merge step
        criteria = tuple(dispositions)
        proofs = self.events("proof/verified", "S1")
        self.assertEqual([(e.data["criterion_id"], e.data["agreement"], e.data["verdict"], e.data["candidate"]) for e in proofs],
                         [(c, True, "SATISFIED", parent) for c in criteria] * 2)
        self.assertEqual(len(self.events("probe/evaluated", "S1")), 5 * len(criteria))     # parent; candidate x2; post-merge x2
        for e in proofs:
            cited = [self.run.events[s] for s in e.source_seqs]
            self.assertEqual([c.type for c in cited], ["probe/evaluated"] * 2)
            self.assertEqual({c.data["record"]["revision"] for c in cited}, {parent})
        # REVIEW and SECURITY under the existing rules: one review request over every criterion, the scanner invoked
        self.assertEqual([(e.data["budget_owner"], tuple(e.data["criteria"])) for e in self.events("provider/request", "S1")],
                         [("REVIEW", criteria)])
        self.assertEqual(len(self.events("tool/invoked", "S1")), 1)
        self.assertEqual([c for c, ok, _ in self.rows("S1") if c == "S1:security"], ["S1:security"])


class Predicate(unittest.TestCase):
    """The kernel reads one admission fact — every obligation measured SATISFIED at the parent. On an admitted story
    that IS the ruling's predicate, row by row of §13's table: this pins the equivalence, so a new row breaks it loudly."""

    def test_all_satisfied_at_the_parent_is_the_ruling_s_predicate_on_every_admissible_combination(self):
        import itertools
        from aisef2.arch.enums import ContractSatisfaction as S, StoryAdmissionDisposition as D
        from aisef2.plan import story_admission as sa
        rows = {k: v for k, v in sa.TABLE.items() if v not in sa.BLOCKING}        # what an admitted story can hold
        self.assertEqual({(role.value, sat.value): d.value for (role, _, sat), d in rows.items()},
                         {("INTRODUCE", "UNSATISFIED"): "READY", ("INTRODUCE", "SATISFIED"): "PRE_SATISFIED",
                          ("PRESERVE", "SATISFIED"): "READY", ("VERIFY", "SATISFIED"): "READY", ("VERIFY", "UNSATISFIED"): "READY"})
        cells = [(role, sat, d) for (role, _, sat), d in rows.items()]
        cells.append((R.INTRODUCE, S.INDETERMINATE, D.READY))                     # §10.3: PRECONDITION_ABSENT at the parent
        checked = 0
        for n in (1, 2, 3):
            for story in itertools.product(cells, repeat=n):
                developer_work_required = any(role is R.INTRODUCE and d is D.READY for role, _, d in story)
                ruled = not developer_work_required and all(
                    d is D.PRE_SATISFIED if role is R.INTRODUCE else sat is S.SATISFIED for role, sat, d in story)
                self.assertEqual(all(sat is S.SATISFIED for _, sat, _ in story), ruled, story)
                checked += 1
        self.assertEqual(checked, 6 + 36 + 216)


class NoDeveloperWork(Fixture):
    def nothing_to_introduce(self, role: R, dev=None, files=None, tests_block: bool = True):
        """C1 (add) landed earlier, so its INTRODUCE is PRE_SATISFIED; C0 (sub) holds at the parent under `role`."""
        parent = e2e.land(self.repo, {"app/calc.py": e2e.CALC + e2e.ADD, **(files or {})}, "add landed earlier")
        dev = dev or e2e.Dev(outage=True)                                          # a developer call would raise
        r = self.story(self.plan(("C1", self.s1, R.INTRODUCE), ("C0", self.s0, role)), "S1", dev, tests_block=tests_block)
        self.assertNoDeveloperWork(r, parent, {"C1": "PRE_SATISFIED", "C0": "READY"}, ("C1",))
        self.assertTrue(self.admitted()["developer_call_permitted"])              # F7 says a call is permitted; none is made
        self.assertEqual(dev.calls, [])
        return self.summary()

    def test_A_introduce_pre_satisfied_and_preserve_satisfied_under_a_blocking_policy(self):
        s = self.nothing_to_introduce(R.PRESERVE)
        self.assertEqual(s["state"]["outcome"], "COMMIT")

    def test_A_a_developer_that_would_only_add_tests_is_never_asked(self):
        """The measured shape: this developer, called, lands a tests-only change that adequacy judges VACUOUS and
        IRRELEVANT (there is no story change for a test to touch) — RETRY, ROLLBACK on the kernel before the correction."""
        dev = e2e.Dev({"tests/test_s1.py": e2e.TEST_ADD})
        self.nothing_to_introduce(R.PRESERVE, dev=dev)

    def test_A_the_story_s_test_file_and_the_stance_do_not_matter(self):
        a = self.nothing_to_introduce(R.PRESERVE)
        for files, block in (({"tests/test_s1.py": e2e.TEST_ADD}, True), ({}, False)):
            other = NoDeveloperWork("nothing_to_introduce")
            other.setUp()
            try:
                self.assertEqual(other.nothing_to_introduce(R.PRESERVE, files=files, tests_block=block), a)
            finally:
                other.doCleanups()

    def test_B_introduce_pre_satisfied_and_verify_satisfied(self):
        s = self.nothing_to_introduce(R.VERIFY)
        self.assertEqual(s["state"]["outcome"], "COMMIT")

    def test_preserve_and_verify_only_all_satisfied_has_no_introduce_ready_either(self):
        """The predicate as ruled, with no INTRODUCE obligation at all (STORY-05-01 as QP-2.9 attempt 2 ran it): nothing
        is READY to introduce and every obligation is satisfied at the parent."""
        parent = e2e.land(self.repo, {"app/calc.py": e2e.CALC + e2e.ADD}, "add landed earlier")
        dev = e2e.Dev(outage=True)
        r = self.story(self.plan(("C0", self.s0, R.PRESERVE), ("C1", self.s1, R.VERIFY)), "S1", dev, tests_block=True)
        self.assertNoDeveloperWork(r, parent, {"C0": "READY", "C1": "READY"}, ())
        self.assertEqual(dev.calls, [])

    def test_the_path_is_the_fully_pre_satisfied_story_s_path(self):
        """The same stages, in the same order, as K-PRESAT-001's already-satisfied story over the same two specs."""
        a = self.nothing_to_introduce(R.PRESERVE)
        other = NoDeveloperWork("nothing_to_introduce")
        other.setUp()
        try:
            e2e.land(other.repo, {"app/calc.py": e2e.CALC + e2e.ADD}, "add landed earlier")
            other.story(other.plan(("C1", other.s1, R.INTRODUCE), ("C0", other.s0, R.INTRODUCE)), "S1", e2e.Dev(outage=True), tests_block=True)
            b = other.summary()
        finally:
            other.doCleanups()
        drift = "story/plan-drift"
        self.assertEqual([t for t in a["types"] if t != drift], [t for t in b["types"] if t != drift])
        self.assertEqual((a["types"].count(drift), b["types"].count(drift)), (1, 2))
        self.assertEqual((a["rows"], a["budgets"]), (b["rows"], b["budgets"]))


class DeveloperWorkRemains(Fixture):
    def test_C_introduce_ready_and_preserve_satisfied_the_developer_and_adequacy_run(self):
        dev = e2e.Dev({"app/mul.py": e2e.MUL, "tests/test_s1.py": e2e.TEST_MUL})
        r = self.story(self.plan(("C2", self.s2, R.INTRODUCE), ("C0", self.s0, R.PRESERVE)), "S1", dev, tests_block=True)
        self.assertCommitted(r)
        self.assertEqual(self.admitted()["dispositions"], {"C2": "READY", "C0": "READY"})
        self.assertEqual([c[1] for c in dev.calls], [("C2", "C0")])               # the developer MUST still run
        self.assertEqual([list(e.data["criteria"]) for e in self.requests(Owner.DEVELOPER)], [["C2", "C0"]])
        adequacy = self.events("tests/adequacy", "S1")
        self.assertEqual(len(adequacy), 1)                                        # engineering adequacy MUST still run
        self.assertEqual((adequacy[0].data["execution"]["status"], adequacy[0].data["execution"]["selection"]),
                         ("EXECUTED", "STORY_TESTS_RAN"))
        self.assertIn(("S1:quality", True), [(c, ok) for c, ok, _ in self.rows("S1")])
        self.assertNotEqual(r.revision, self.base)                                # the candidate landed

    def test_C_a_blocking_policy_still_blocks_that_story_on_failing_tests(self):
        failing = e2e.TEST_MUL.replace(", 6)", ", 7)")
        dev = e2e.Dev({"app/mul.py": e2e.MUL, "tests/test_s1.py": failing})
        r = self.story(self.plan(("C2", self.s2, R.INTRODUCE), ("C0", self.s0, R.PRESERVE)), "S1", dev, tests_block=True,
                       limits={**e2e.LIMITS, Owner.DEVELOPER: 0})
        self.assertAttempts(r, ["ROLLBACK"])
        self.assertEqual(self.failures("S1"), [("TESTS_INADEQUATE", "DEVELOPER", True)])
        self.assertEqual(self.events("tests/adequacy", "S1")[0].data["outcome"], "INADEQUATE")

    def test_C_an_introduce_ready_beside_a_pre_satisfied_one_and_a_satisfied_verify_still_needs_the_developer(self):
        e2e.land(self.repo, {"app/calc.py": e2e.CALC + e2e.ADD}, "add landed earlier")
        dev = e2e.Dev({"app/mul.py": e2e.MUL, "tests/test_s1.py": e2e.TEST_MUL})
        r = self.story(self.plan(("C1", self.s1, R.INTRODUCE), ("C2", self.s2, R.INTRODUCE), ("C0", self.s0, R.VERIFY)), "S1", dev,
                       tests_block=True)
        self.assertCommitted(r)
        self.assertEqual(self.admitted()["dispositions"], {"C1": "PRE_SATISFIED", "C2": "READY", "C0": "READY"})
        self.assertEqual([c[1] for c in dev.calls], [("C2", "C0")])
        self.assertEqual(len(self.events("tests/adequacy", "S1")), 1)

    def test_D_introduce_pre_satisfied_and_preserve_not_satisfied_is_precondition_broken_as_before(self):
        e2e.land(self.repo, {"app/calc.py": e2e.CALC + e2e.ADD}, "add landed earlier")
        dev = e2e.Dev(outage=True)
        r = self.story(self.plan(("C1", self.s1, R.INTRODUCE), ("C2", self.s2, R.PRESERVE)), "S1", dev, tests_block=True,
                       limits={**e2e.LIMITS, Owner.PLAN: 0})
        self.assertAttempts(r, ["ROLLBACK"])
        a = self.admitted()
        self.assertEqual((a["dispositions"], a["admitted"], a["developer_call_permitted"]),
                         ({"C1": "PRE_SATISFIED", "C2": "PRECONDITION_BROKEN"}, False, False))
        self.assertEqual([(code, owner) for code, owner, _ in self.failures("S1")], [("PRECONDITION_BROKEN", "PLAN")])
        self.assertEqual((dev.calls, self.events("provider/request", "S1"), self.events("proof/verified", "S1")), ([], [], []))

    def test_E_no_introduce_ready_and_a_verify_unsatisfied_is_not_this_correction_s_case(self):
        """VERIFY_NO_INTRODUCER_UNSATISFIED_REQUIRES_OWNER_DECISION: the correction refuses the case — nothing new is
        routed for it; the kernel does what it did before, which is to give the developer the READY VERIFY."""
        e2e.land(self.repo, {"app/calc.py": e2e.CALC + e2e.ADD, "app/mul.py": MUL_WRONG}, "add landed earlier; mul is wrong")
        dev = e2e.Dev({"app/mul.py": e2e.MUL, "tests/test_s1.py": e2e.TEST_MUL})
        r = self.story(self.plan(("C1", self.s1, R.INTRODUCE), ("C2", self.s2, R.VERIFY)), "S1", dev, tests_block=True)
        self.assertEqual(self.admitted()["dispositions"], {"C1": "PRE_SATISFIED", "C2": "READY"})
        self.assertEqual([c[1] for c in dev.calls], [("C2",)])                    # the no-developer path was NOT taken
        self.assertEqual([list(e.data["criteria"]) for e in self.requests(Owner.DEVELOPER)], [["C2"]])
        self.assertEqual(len(self.events("tests/adequacy", "S1")), 1)             # nor adequacy skipped
        self.assertCommitted(r)

    def test_E_a_developer_who_changes_nothing_there_fails_exactly_as_before(self):
        e2e.land(self.repo, {"app/calc.py": e2e.CALC + e2e.ADD, "app/mul.py": MUL_WRONG}, "add landed earlier; mul is wrong")
        dev = e2e.Dev(fail=True)
        r = self.story(self.plan(("C1", self.s1, R.INTRODUCE), ("C2", self.s2, R.VERIFY)), "S1", dev, tests_block=True,
                       limits={**e2e.LIMITS, Owner.DEVELOPER: 0})
        self.assertAttempts(r, ["ROLLBACK"])
        self.assertEqual(len(dev.calls), 1)
        self.assertEqual({owner for _, owner, _ in self.failures("S1")}, {"DEVELOPER"})


@unittest.skipUnless((ROOT / "validation/qualification/c2_k_nowork_001.py").exists(),
                     "validation/qualification is not in this tree (the mutation runner's copy); the suite runs it")
class Record(unittest.TestCase):
    def test_the_record_binds_this_tree_and_shows_the_cases_red_before_and_green_after(self):
        from validation.qualification import c2_k_nowork_001 as kn
        self.assertEqual(kn.check(), [])


if __name__ == "__main__":
    unittest.main()
