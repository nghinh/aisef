"""WP-5.4 — RFC §15 / §15.3: EngineeringTestAdequacy assembled from typed facts.

ADEQ-1..17 as the owner listed them, typed first and then for real through WP-5.1 → WP-5.2 → WP-5.3 → assemble; the
whole well-formed input space, exhaustively, against the frozen precedence; the shape's refusals; and the mechanical
separations: no product proof, no journal, no prose read for control, no side state, chronology recorded and never
consulted."""

import ast
import difflib
import itertools
import pathlib
import shutil
import sys
import tempfile
import unittest
from types import MappingProxyType

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import AdequacyOutcome as A, Owner, Relevance as R, TestExecutionStatus as X, TestOutcome as TO, TestSelection as TS, Vacuity as V  # noqa: E402,E501
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.quality import adequacy as aq, test_execution as te  # noqa: E402
from aisef2.quality.adequacy import Assembly, EngineeringTestAdequacy, assemble, may_block  # noqa: E402
from aisef2.quality.relevance import measure, story_diff  # noqa: E402
from aisef2.quality.test_execution import Dependencies, DeveloperTests, TestExecution, unrunnable  # noqa: E402
from aisef2.quality.vacuity import evaluate  # noqa: E402

# ------------------------------------------------------------------------------------------------ typed fixtures
RAN_OK = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None, "the story's tests ran and passed")
RAN_BAD = TestExecution(X.EXECUTED, TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER, "1 story test failed")
NONE = TestExecution(X.EXECUTED, TO.PASSED, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER, "no story test matched")
NC_DEV = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER, "import app.missing: project source")
NC_INT = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION, "import zzz: cause undeterminable")
UNRUN = unrunnable("the interpreter is absent")
REG_NONE = TestExecution(X.EXECUTED, TO.PASSED, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER, "no regression test matched")
REG_NC_DEV = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER, "import app.missing: project source")
REG_NC_INT = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION, "import zzz: cause undeterminable")
RED_GREEN = {"process/tdd-chronology": "RED_THEN_GREEN", "red_at": "p1", "green_at": "c1"}
GREEN_ONLY = {"process/tdd-chronology": "GREEN_ONLY", "violated": True}


def executions() -> list[TestExecution]:
    """Every well-formed TestExecution (WP-5.1's shape): 1 UNRUNNABLE + 8 EXECUTED."""
    out = [UNRUN]
    for o in (TO.PASSED, TO.FAILED):
        out.append(TestExecution(X.EXECUTED, o, TS.STORY_TESTS_RAN, Owner.DEVELOPER if o is TO.FAILED else None, "ran"))
        out.append(TestExecution(X.EXECUTED, o, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER, "none matched"))
        for owner in (Owner.DEVELOPER, Owner.INTEGRATION):
            out.append(TestExecution(X.EXECUTED, o, TS.STORY_TESTS_NOT_COLLECTABLE, owner, "not collectable"))
    return out


def space():
    """Every well-formed (execution, vacuity, relevance, regressions): 333 combinations."""
    for x, g in itertools.product(executions(), executions()):
        if x.status is X.UNRUNNABLE:
            yield x, None, None, g
            continue
        vac = (V.NON_VACUOUS, V.VACUOUS, V.INDETERMINATE) if x.selection is TS.STORY_TESTS_RAN else (V.INDETERMINATE,)
        for v, r in itertools.product(vac, (R.RELEVANT, R.IRRELEVANT, R.UNMEASURABLE)):
            yield x, v, r, g


def verdict(a: Assembly) -> tuple:
    return (a.adequacy, a.outcome, a.owner, a.may_block, a.developer_chargeable, a.reason)


class Cases(unittest.TestCase):
    """ADEQ-1..15 on typed inputs, each pinned to its outcome, owner, blocking permission and chargeability."""

    def test_ADEQ_1_all_green_is_ADEQUATE(self):
        a = assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.ADEQUATE, None, False, False))
        self.assertEqual(a.adequacy, EngineeringTestAdequacy(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, None, A.ADEQUATE))
        self.assertEqual(a.reason, "ADEQUATE: the story's tests ran and passed, NON_VACUOUS, RELEVANT, the regressions ran and passed")

    def test_ADEQ_2_primary_UNRUNNABLE_has_no_outcome_and_the_environment_owner_the_typed_fact_carries(self):
        a = assemble(UNRUN, None, None, RAN_OK)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (None, Owner.ENVIRONMENT, False, False))
        self.assertIs(a.owner, UNRUN.owner_on_failure)
        self.assertEqual((a.adequacy.vacuity, a.adequacy.relevance, a.adequacy.regressions), (None, None, RAN_OK))
        self.assertEqual(a.reason, "the story's tests could not execute: an environment outcome, no AdequacyOutcome — the interpreter is absent")
        for v, r in ((V.NON_VACUOUS, None), (None, R.RELEVANT), (V.INDETERMINATE, R.UNMEASURABLE)):
            with self.assertRaises(InvariantError):   # nothing measured the story's tests: no vacuity, no relevance exists
                assemble(UNRUN, v, r, RAN_OK)
        for g in (RAN_BAD, NONE, NC_DEV, UNRUN):        # whatever the regressions say, the story's execution comes first
            self.assertEqual((assemble(UNRUN, None, None, g).outcome, assemble(UNRUN, None, None, g).owner), (None, Owner.ENVIRONMENT))

    def test_ADEQ_3_regression_UNRUNNABLE_has_no_outcome_and_keeps_the_environment_owner(self):
        a = assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, UNRUN)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (None, Owner.ENVIRONMENT, False, False))
        self.assertIs(a.owner, UNRUN.owner_on_failure)
        self.assertEqual((a.adequacy.vacuity, a.adequacy.relevance), (V.NON_VACUOUS, R.RELEVANT))   # measured, kept, not judged
        self.assertEqual(a.reason, "the regressions could not execute: an environment outcome, no AdequacyOutcome — the interpreter is absent")
        for x, v, r in ((RAN_BAD, V.INDETERMINATE, R.UNMEASURABLE), (RAN_OK, V.VACUOUS, R.IRRELEVANT), (NC_DEV, V.INDETERMINATE, R.RELEVANT)):
            b = assemble(x, v, r, UNRUN)                # a defect or a gap on the story side changes nothing: availability first
            self.assertEqual((b.outcome, b.owner, b.may_block, b.developer_chargeable), (None, Owner.ENVIRONMENT, False, False))

    def test_ADEQ_4_the_story_tests_FAILED_is_INADEQUATE_DEVELOPER(self):
        a = assemble(RAN_BAD, V.NON_VACUOUS, R.RELEVANT, RAN_OK)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(a.reason, "INADEQUATE: the story's tests executed and failed")

    def test_ADEQ_5_NO_STORY_TESTS_MATCHED_is_INADEQUATE_DEVELOPER(self):
        a = assemble(NONE, V.INDETERMINATE, R.IRRELEVANT, RAN_OK)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(a.reason, "INADEQUATE: no story test matched the story's declared tests")

    def test_ADEQ_6_a_developer_caused_collection_failure_is_INADEQUATE_DEVELOPER(self):
        for r in (R.RELEVANT, R.IRRELEVANT, R.UNMEASURABLE):
            a = assemble(NC_DEV, V.INDETERMINATE, r, RAN_OK)
            self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(assemble(NC_DEV, V.INDETERMINATE, R.RELEVANT, RAN_OK).reason,
                         "INADEQUATE: the story's tests could not be collected for a cause typed as the developer's")

    def test_ADEQ_7_an_integration_owned_collection_failure_is_never_charged_to_the_developer(self):
        for r in (R.RELEVANT, R.IRRELEVANT, R.UNMEASURABLE):   # IRRELEVANT of tests that did not run charges nobody
            a = assemble(NC_INT, V.INDETERMINATE, r, RAN_OK)
            self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INCOMPLETE, None, False, False))
            self.assertIsNot(a.owner, Owner.DEVELOPER)
        self.assertEqual(assemble(NC_INT, V.INDETERMINATE, R.IRRELEVANT, RAN_OK).reason,
                         "INCOMPLETE (reduced engineering-quality coverage, never blocking, charged to nobody): vacuity is "
                         "INDETERMINATE; the story's tests were not collected, owner INTEGRATION: import zzz: cause undeterminable")
        failed = TestExecution(X.EXECUTED, TO.FAILED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION, "one file ran and failed")
        a = assemble(failed, V.INDETERMINATE, R.RELEVANT, RAN_OK)   # a story test that ran and FAILED is §15.3's own trigger
        self.assertEqual((a.outcome, a.owner, a.reason), (A.INADEQUATE, Owner.DEVELOPER, "INADEQUATE: the story's tests executed and failed"))

    def test_ADEQ_8_VACUOUS_is_INADEQUATE_DEVELOPER(self):
        a = assemble(RAN_OK, V.VACUOUS, R.RELEVANT, RAN_OK)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(a.reason, "INADEQUATE: the story's tests are VACUOUS: they pass without the story's product change")

    def test_ADEQ_9_IRRELEVANT_is_INADEQUATE_DEVELOPER(self):
        a = assemble(RAN_OK, V.NON_VACUOUS, R.IRRELEVANT, RAN_OK)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(a.reason, "INADEQUATE: the story's tests are IRRELEVANT: none touches the story's change")

    def test_ADEQ_10_regressions_FAILED_is_INADEQUATE_DEVELOPER(self):
        a = assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_BAD)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(a.reason, "INADEQUATE: regressions executed and failed")
        reg = TestExecution(X.EXECUTED, TO.FAILED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION, "one file ran and failed")
        self.assertEqual(assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, reg).outcome, A.INADEQUATE)   # FAILED is FAILED under any selection

    def test_ADEQ_11_INDETERMINATE_vacuity_alone_is_INCOMPLETE_non_blocking_uncharged(self):
        a = assemble(RAN_OK, V.INDETERMINATE, R.RELEVANT, RAN_OK)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INCOMPLETE, None, False, False))
        self.assertEqual(a.reason, "INCOMPLETE (reduced engineering-quality coverage, never blocking, charged to nobody): vacuity is INDETERMINATE")

    def test_ADEQ_12_UNMEASURABLE_relevance_alone_is_INCOMPLETE_non_blocking_uncharged(self):
        a = assemble(RAN_OK, V.NON_VACUOUS, R.UNMEASURABLE, RAN_OK)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INCOMPLETE, None, False, False))
        self.assertEqual(a.reason, "INCOMPLETE (reduced engineering-quality coverage, never blocking, charged to nobody): relevance is UNMEASURABLE")
        both = assemble(RAN_OK, V.INDETERMINATE, R.UNMEASURABLE, RAN_OK)
        self.assertEqual((both.outcome, both.reason), (A.INCOMPLETE, "INCOMPLETE (reduced engineering-quality coverage, never "
                                                       "blocking, charged to nobody): vacuity is INDETERMINATE; relevance is UNMEASURABLE"))

    def test_ADEQ_13_FAILED_with_UNMEASURABLE_is_INADEQUATE_the_hard_defect_dominates(self):
        for v in (V.NON_VACUOUS, V.INDETERMINATE):
            a = assemble(RAN_BAD, v, R.UNMEASURABLE, RAN_OK)
            self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(assemble(RAN_BAD, V.INDETERMINATE, R.UNMEASURABLE, RAN_OK).reason, "INADEQUATE: the story's tests executed and failed")

    def test_ADEQ_14_regressions_FAILED_with_INDETERMINATE_is_INADEQUATE(self):
        for r in (R.RELEVANT, R.UNMEASURABLE):
            a = assemble(RAN_OK, V.INDETERMINATE, r, RAN_BAD)
            self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
            self.assertEqual(a.reason, "INADEQUATE: regressions executed and failed")

    def test_ADEQ_15_opposite_TDD_chronology_with_identical_typed_inputs_is_the_identical_result(self):
        n = 0
        for x, v, r, g in space():
            red, green, none = (assemble(x, v, r, g, chronology=c) for c in (RED_GREEN, GREEN_ONLY, None))
            self.assertEqual(verdict(red), verdict(green))
            self.assertEqual(verdict(red), verdict(none))
            self.assertEqual((dict(red.chronology), dict(green.chronology), none.chronology), (RED_GREEN, GREEN_ONLY, None))
            n += 1
        self.assertEqual(n, 333)
        source = dict(RED_GREEN)
        a = assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, chronology=source)
        source["process/tdd-chronology"] = "GREEN_ONLY"                 # the record is a copy, not a view
        self.assertEqual(a.chronology["process/tdd-chronology"], "RED_THEN_GREEN")
        self.assertIsInstance(a.chronology, MappingProxyType)
        with self.assertRaises(TypeError):
            a.chronology["process/tdd-chronology"] = "x"                # and it is read-only
        self.assertIs(assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK).chronology, None)


class Exhaustive(unittest.TestCase):
    """The whole well-formed input space against the frozen precedence, and the invariants that hold over all of it."""

    @staticmethod
    def defect(x, v, r, g) -> bool:
        return (x.outcome is TO.FAILED or x.selection is TS.NO_STORY_TESTS_MATCHED
                or (x.selection is TS.STORY_TESTS_NOT_COLLECTABLE and x.owner_on_failure is Owner.DEVELOPER)
                or v is V.VACUOUS or (r is R.IRRELEVANT and x.selection is TS.STORY_TESTS_RAN) or g.outcome is TO.FAILED
                or g.selection is TS.NO_STORY_TESTS_MATCHED
                or (g.selection is TS.STORY_TESTS_NOT_COLLECTABLE and g.owner_on_failure is Owner.DEVELOPER))

    def test_assembly_is_total_and_follows_the_precedence(self):
        seen = {None: 0, A.INADEQUATE: 0, A.INCOMPLETE: 0, A.ADEQUATE: 0}
        for x, v, r, g in space():
            a = assemble(x, v, r, g)
            seen[a.outcome] += 1
            if x.status is X.UNRUNNABLE or g.status is X.UNRUNNABLE:
                self.assertIs(a.outcome, None, (x, v, r, g))
                self.assertIs(a.owner, (x if x.status is X.UNRUNNABLE else g).owner_on_failure)
                self.assertIs(a.owner, Owner.ENVIRONMENT)
            elif self.defect(x, v, r, g):
                self.assertIs(a.outcome, A.INADEQUATE, (x, v, r, g))
            elif v is V.INDETERMINATE or r is R.UNMEASURABLE or g.selection is TS.STORY_TESTS_NOT_COLLECTABLE:
                self.assertIs(a.outcome, A.INCOMPLETE, (x, v, r, g))
                if g.selection is TS.STORY_TESTS_NOT_COLLECTABLE:
                    self.assertIs(g.owner_on_failure, Owner.INTEGRATION)          # the DEVELOPER-typed one is a defect above
            else:
                self.assertIs(a.outcome, A.ADEQUATE, (x, v, r, g))
                self.assertEqual((x.outcome, v, r, g.outcome, g.selection),
                                 (TO.PASSED, V.NON_VACUOUS, R.RELEVANT, TO.PASSED, TS.STORY_TESTS_RAN))   # positively
            self.assertEqual((a.adequacy.execution, a.adequacy.vacuity, a.adequacy.relevance, a.adequacy.regressions,
                              a.adequacy.sensitivity), (x, v, r, g, None))
        self.assertEqual(seen, {None: 9 + 36, A.INADEQUATE: 274, A.INCOMPLETE: 13, A.ADEQUATE: 1})
        self.assertEqual(sum(seen.values()), 333)

    def test_owner_blocking_and_charge_are_read_from_the_typed_facts_only(self):
        for x, v, r, g in space():
            a = assemble(x, v, r, g)
            self.assertEqual(a.may_block, a.outcome is A.INADEQUATE)
            self.assertEqual(a.developer_chargeable, a.outcome is A.INADEQUATE)
            self.assertEqual(a.owner is Owner.DEVELOPER, a.outcome is A.INADEQUATE)
            if a.outcome in (A.INCOMPLETE, A.ADEQUATE):
                self.assertIs(a.owner, None)
            if Owner.INTEGRATION in (x.owner_on_failure, g.owner_on_failure) and not self.defect(x, v, r, g):
                self.assertIsNot(a.owner, Owner.DEVELOPER)          # INTEGRATION is never converted into DEVELOPER
            fabricated = Assembly(a.adequacy, None, "INADEQUATE: fabricated prose")                       # prose decides nothing
            self.assertEqual(verdict(a)[:-1], verdict(fabricated)[:-1])
        self.assertEqual([may_block(o) for o in (A.INADEQUATE, A.INCOMPLETE, A.ADEQUATE, None)], [True, False, False, False])

    def test_ADEQ_R_the_regression_dimension_follows_the_same_typed_rules(self):
        """The owner's ruling on the regression dimension (RFC §15 `regressions`, §15.0 rule 5): UNRUNNABLE => None;
        FAILED, NO_STORY_TESTS_MATCHED, NOT_COLLECTABLE typed DEVELOPER => INADEQUATE / DEVELOPER; NOT_COLLECTABLE typed
        INTEGRATION => INCOMPLETE, no developer charge, non-blocking; PASSED + STORY_TESTS_RAN => satisfied."""
        a = assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, REG_NONE)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(a.reason, "INADEQUATE: no regression test matched the regression selection")
        a = assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, REG_NC_DEV)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(a.reason, "INADEQUATE: the regressions could not be collected for a cause typed as the developer's")
        a = assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, REG_NC_INT)
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INCOMPLETE, None, False, False))
        self.assertEqual(a.reason, "INCOMPLETE (reduced engineering-quality coverage, never blocking, charged to nobody): the "
                                   "regressions could not be collected, owner INTEGRATION: import zzz: cause undeterminable")
        a = assemble(RAN_OK, V.INDETERMINATE, R.UNMEASURABLE, REG_NC_INT)          # every gap is named, none charged
        self.assertEqual((a.outcome, a.owner), (A.INCOMPLETE, None))
        self.assertEqual(a.reason, "INCOMPLETE (reduced engineering-quality coverage, never blocking, charged to nobody): vacuity is "
                                   "INDETERMINATE; relevance is UNMEASURABLE; the regressions could not be collected, owner "
                                   "INTEGRATION: import zzz: cause undeterminable")
        failed = TestExecution(X.EXECUTED, TO.FAILED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION, "one file ran and failed")
        a = assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, failed)                    # a regression that ran and FAILED is a defect
        self.assertEqual((a.outcome, a.owner, a.reason), (A.INADEQUATE, Owner.DEVELOPER, "INADEQUATE: regressions executed and failed"))
        for g in (REG_NONE, REG_NC_DEV, REG_NC_INT):                                # availability first, on the story side too
            self.assertEqual((assemble(UNRUN, None, None, g).outcome, assemble(UNRUN, None, None, g).owner), (None, Owner.ENVIRONMENT))
        a = assemble(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK)
        self.assertEqual((a.outcome, a.adequacy.regressions.selection), (A.ADEQUATE, TS.STORY_TESTS_RAN))


class Shape(unittest.TestCase):
    """EngineeringTestAdequacy refuses every contradiction of the typed facts."""

    def refuses(self, *args, msg: str | None = None):
        with self.assertRaises(InvariantError) as cm:
            EngineeringTestAdequacy(*args)
        if msg is not None:
            self.assertEqual(str(cm.exception), msg)

    def test_the_fields_are_the_rfcs(self):
        self.assertEqual(tuple(EngineeringTestAdequacy.__dataclass_fields__),
                         ("execution", "vacuity", "relevance", "regressions", "sensitivity", "outcome"))
        self.assertEqual(tuple(Assembly.__dataclass_fields__), ("adequacy", "chronology", "reason"))
        ok = EngineeringTestAdequacy(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, None, A.ADEQUATE)
        with self.assertRaises(AttributeError):
            ok.outcome = A.INADEQUATE                                    # frozen

    def test_typed_executions_and_no_sensitivity(self):
        self.refuses("ran", V.NON_VACUOUS, R.RELEVANT, RAN_OK, None, A.ADEQUATE,
                     msg="an adequacy is assembled from typed executions (§15.0)")
        self.refuses(RAN_OK, V.NON_VACUOUS, R.RELEVANT, {"status": "EXECUTED"}, None, A.ADEQUATE)
        self.refuses(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, {"mutants_killed": 1}, A.ADEQUATE,
                     msg="sensitivity evidence is deferred from cycle 1 (§33): nothing may claim it")
        self.refuses(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, False, A.ADEQUATE)

    def test_UNRUNNABLE_story_execution_carries_nothing_measured_and_no_outcome(self):
        EngineeringTestAdequacy(UNRUN, None, None, RAN_OK, None, None)
        EngineeringTestAdequacy(UNRUN, None, None, UNRUN, None, None)
        self.refuses(UNRUN, V.INDETERMINATE, None, RAN_OK, None, None,
                     msg="UNRUNNABLE story execution: no vacuity, no relevance, no AdequacyOutcome — an environment outcome, "
                         "never a quality result (§15.0 rule 1, §15.3)")
        self.refuses(UNRUN, None, R.UNMEASURABLE, RAN_OK, None, None)
        for o in (A.INADEQUATE, A.INCOMPLETE, A.ADEQUATE):
            self.refuses(UNRUN, None, None, RAN_OK, None, o)

    def test_EXECUTED_story_execution_carries_typed_measurements_of_tests_that_ran(self):
        typed = "an EXECUTED story execution carries a typed Vacuity and a typed Relevance (§15)"
        self.refuses(RAN_OK, None, R.UNMEASURABLE, RAN_OK, None, A.INCOMPLETE, msg=typed)   # one untyped is enough
        self.refuses(RAN_OK, V.INDETERMINATE, None, RAN_OK, None, A.INCOMPLETE, msg=typed)
        self.refuses(RAN_OK, "NON_VACUOUS", R.RELEVANT, RAN_OK, None, A.ADEQUATE)
        for x in (NONE, NC_DEV, NC_INT):                                # tests that did not run have no vacuity value
            for v in (V.NON_VACUOUS, V.VACUOUS):
                self.refuses(x, v, R.RELEVANT, RAN_OK, None, A.INADEQUATE,
                             msg="NON_VACUOUS and VACUOUS are said of story tests that actually ran (§15.1 conditions 2–3; "
                                 "WP-5.3's baseline): tests that did not run have INDETERMINATE vacuity")
        EngineeringTestAdequacy(NC_INT, V.INDETERMINATE, R.RELEVANT, RAN_OK, None, A.INCOMPLETE)

    def test_UNRUNNABLE_regressions_carry_no_outcome(self):
        EngineeringTestAdequacy(RAN_OK, V.NON_VACUOUS, R.RELEVANT, UNRUN, None, None)
        EngineeringTestAdequacy(RAN_BAD, V.INDETERMINATE, R.UNMEASURABLE, UNRUN, None, None)
        for o in (A.INADEQUATE, A.INCOMPLETE, A.ADEQUATE):
            self.refuses(RAN_OK, V.NON_VACUOUS, R.RELEVANT, UNRUN, None, o,
                         msg="UNRUNNABLE regression execution: no AdequacyOutcome — an environment outcome under the same "
                             "typed rules (§15.0 rule 5, §15.3)")
            self.refuses(RAN_BAD, V.INDETERMINATE, R.UNMEASURABLE, UNRUN, None, o)

    def test_both_EXECUTED_the_outcome_is_defined_and_is_what_the_facts_assemble_to(self):
        self.refuses(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, None, None,
                     msg="both mandatory executions EXECUTED: the AdequacyOutcome is defined (§15.3)")
        self.refuses(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, None, "ADEQUATE")
        # INADEQUATE needs a defect
        self.refuses(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, None, A.INADEQUATE,
                     msg="INADEQUATE names a developer-owned defect of §15.3; the typed facts carry none")
        self.refuses(RAN_OK, V.INDETERMINATE, R.UNMEASURABLE, RAN_OK, None, A.INADEQUATE)
        self.refuses(NC_INT, V.INDETERMINATE, R.IRRELEVANT, RAN_OK, None, A.INADEQUATE)
        for args in ((RAN_BAD, V.NON_VACUOUS, R.RELEVANT, RAN_OK), (NONE, V.INDETERMINATE, R.RELEVANT, RAN_OK),
                     (NC_DEV, V.INDETERMINATE, R.RELEVANT, RAN_OK), (RAN_OK, V.VACUOUS, R.RELEVANT, RAN_OK),
                     (RAN_OK, V.NON_VACUOUS, R.IRRELEVANT, RAN_OK), (RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_BAD),
                     (RAN_OK, V.NON_VACUOUS, R.RELEVANT, REG_NONE), (RAN_OK, V.NON_VACUOUS, R.RELEVANT, REG_NC_DEV)):
            EngineeringTestAdequacy(*args, None, A.INADEQUATE)
            self.refuses(*args, None, A.INCOMPLETE,                     # a defect is never hidden by INCOMPLETE
                         msg="a developer-owned defect is INADEQUATE; a secondary gap never hides it (§15.3)")
            self.refuses(*args, None, A.ADEQUATE)
        # INCOMPLETE needs a gap and no defect
        self.refuses(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, None, A.INCOMPLETE,
                     msg="INCOMPLETE is exactly an INDETERMINATE vacuity, an UNMEASURABLE relevance, or a regression selection "
                         "not collected for a cause that is not the developer's (§15.3)")
        for args in ((RAN_OK, V.INDETERMINATE, R.RELEVANT, RAN_OK), (RAN_OK, V.NON_VACUOUS, R.UNMEASURABLE, RAN_OK),
                     (NC_INT, V.INDETERMINATE, R.IRRELEVANT, RAN_OK), (RAN_OK, V.NON_VACUOUS, R.RELEVANT, REG_NC_INT)):
            EngineeringTestAdequacy(*args, None, A.INCOMPLETE)
            self.refuses(*args, None, A.ADEQUATE)
            self.refuses(*args, None, A.INADEQUATE)
        # ADEQUATE is constructed positively: each conjunct, violated alone, is refused
        EngineeringTestAdequacy(RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_OK, None, A.ADEQUATE)
        for args in ((RAN_BAD, V.NON_VACUOUS, R.RELEVANT, RAN_OK), (RAN_OK, V.VACUOUS, R.RELEVANT, RAN_OK),
                     (RAN_OK, V.INDETERMINATE, R.RELEVANT, RAN_OK), (RAN_OK, V.NON_VACUOUS, R.IRRELEVANT, RAN_OK),
                     (RAN_OK, V.NON_VACUOUS, R.UNMEASURABLE, RAN_OK), (RAN_OK, V.NON_VACUOUS, R.RELEVANT, RAN_BAD),
                     (RAN_OK, V.NON_VACUOUS, R.RELEVANT, REG_NONE), (RAN_OK, V.NON_VACUOUS, R.RELEVANT, REG_NC_INT)):
            self.refuses(*args, None, A.ADEQUATE, msg="ADEQUATE is constructed positively: the story's tests passed, "
                                                       "NON_VACUOUS, RELEVANT, the regressions ran and passed (§15.3)")


# ------------------------------------------------------------------------------------------------ mechanical separations
SOURCE = ROOT / "aisef2/quality/adequacy.py"
FORBIDDEN = {"ProductProofSpec", "ProbeResult", "CandidateProof", "VerifiedProof", "BehaviorVerdict", "ContractSatisfaction",
             "FailureCode", "EventType", "Event", "Journal", "emit", "charge", "Budget"}
ALLOWED_IMPORTS = {"__future__", "dataclasses", "types", "typing", "aisef2.arch.enums", "aisef2.errors",
                   "aisef2.quality.test_execution"}


def _aisef2_imports(rel: str) -> set[str]:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("aisef2"):
            out.add(n.module)
        elif isinstance(n, ast.Import):
            out.update(a.name for a in n.names if a.name.startswith("aisef2"))
    return out


def _closure(module: str) -> set[str]:
    seen, todo = set(), {module}
    while todo:
        mod = todo.pop()
        seen.add(mod)
        rel = mod.replace(".", "/") + ".py"
        if (ROOT / rel).exists():
            todo |= _aisef2_imports(rel) - seen
    return seen


class Separation(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        self.parents = {c: p for p in ast.walk(self.tree) for c in ast.iter_child_nodes(p)}

    def test_no_path_reaches_a_product_proof_a_journal_or_a_budget(self):
        imports = {n.module for n in ast.walk(self.tree) if isinstance(n, ast.ImportFrom)}
        imports |= {a.name for n in ast.walk(self.tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertLessEqual(imports, ALLOWED_IMPORTS, imports - ALLOWED_IMPORTS)
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        names |= {a.name for n in ast.walk(self.tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        self.assertFalse(names & FORBIDDEN, names & FORBIDDEN)
        self.assertFalse(set(vars(aq)) & FORBIDDEN)
        # transitively: adequacy adds no import path beyond WP-5.1's own closure (which reaches the journal through P4's
        # process range) — the only module it brings in is itself
        self.assertEqual(_closure("aisef2.quality.adequacy") - _closure("aisef2.quality.test_execution"), {"aisef2.quality.adequacy"})
        # the only state written is the chronology copy made read-only on the assembly itself
        stores = [n for n in ast.walk(self.tree) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)]
        setattrs = [n for n in ast.walk(self.tree) if isinstance(n, ast.Call) and ast.unparse(n.func) in ("setattr", "object.__setattr__")]
        self.assertEqual((stores, [ast.unparse(n.args[1]) for n in setattrs]), ([], ["'chronology'"]))

    def test_no_prose_is_read_for_control_and_no_side_state_exists(self):
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Attribute) and n.attr == "reason":
                parent = self.parents[n]
                self.assertIsInstance(parent, ast.BinOp | ast.FormattedValue, ast.unparse(parent))   # concatenated, never compared or called
        self.assertFalse([n for n in ast.walk(self.tree) if isinstance(n, ast.Global | ast.Nonlocal)])
        self.assertNotIn("re", {a.name for n in ast.walk(self.tree) if isinstance(n, ast.Import) for a in n.names})
        mutable = {k for k, v in vars(aq).items() if isinstance(v, list | dict | set) and not k.startswith("__")}
        self.assertEqual(mutable, set())

    def test_no_policy_object_decides_adequacy_blocking_and_INCOMPLETE_cannot_block_under_any(self):
        users = set()
        for p in (ROOT / "aisef2").rglob("*.py"):
            src = p.read_text(encoding="utf-8")
            if "AdequacyOutcome" in src and any(isinstance(n, ast.Name) and n.id == "AdequacyOutcome" for n in ast.walk(ast.parse(src))):
                users.add(p.relative_to(ROOT).as_posix())
        # no policy object exists: the enum's only other user is the format-3 tests/adequacy schema (V2-005), a shape
        self.assertEqual(users, {"aisef2/arch/enums.py", "aisef2/quality/adequacy.py", "aisef2/journal/format3.py"})
        body = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == "may_block")
        read = {n.id for s in body.body for n in ast.walk(s) if isinstance(n, ast.Name)} - {"outcome", "AdequacyOutcome"}
        self.assertEqual(read, set())                                                   # blocking permission reads the outcome alone
        self.assertFalse(may_block(A.INCOMPLETE))


# ------------------------------------------------------------------------------------------------ for real
OLD = "def add(a, b):\n    return a - b\n"
NEW = "def add(a, b):\n    return a + b\n"
NEW_LEGACY = NEW + "\n\ndef legacy():\n    return 0\n"
HEAD = "import unittest\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n"
TEST_ADD = HEAD + "    def test_add(self):\n        self.assertEqual(calc.add(1, 2), 3)\n"
TEST_WRONG = HEAD + "    def test_add(self):\n        self.assertEqual(calc.add(1, 2), 4)\n"
TEST_GONE = HEAD + "    def test_gone(self):\n        self.assertFalse(hasattr(calc, 'legacy'))\n        self.assertEqual(calc.add(1, 2), 3)\n"
REG_OK = HEAD + "    def test_two(self):\n        self.assertEqual(calc.add(2, 2), 4)\n"
REG_BAD = HEAD + "    def test_two(self):\n        self.assertEqual(calc.add(2, 2), 5)\n"
STORY = DeveloperTests("S1", ("tests/test_calc.py",))
REGRESSIONS = DeveloperTests("S1", ("tests/test_other.py",))
ABSENT = te.Runner("absent", ("-m", "aisef2_no_such_runner", "{out}"), te._read_unittest)


def patch(old: str, new: str, path: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "a/" + path, "b/" + path))


def project(files: dict) -> str:
    d = tempfile.mkdtemp(prefix="aisef2-p5adq-")
    base = {"app/__init__.py": "", "app/calc.py": NEW, "tests/__init__.py": "", "tests/test_other.py": REG_OK}
    for rel, text in {**base, **files}.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


class ForReal(unittest.TestCase):
    """WP-5.1 → WP-5.2 → WP-5.3 → assemble, through the harness-owned runner."""

    def run_(self, files: dict, diff: str, story_runner=te.UNITTEST, regression_runner=te.UNITTEST) -> Assembly:
        d = project(files)
        self.addCleanup(shutil.rmtree, d, True)
        deps = Dependencies(frozenset(), te.project_top_level(d))
        rep, x = te.execute(story_runner, d, STORY, deps, targets=(*STORY.paths, te.MEASURE), timeout_s=120)
        vacuity = relevance = None
        if x.status is X.EXECUTED:
            relevance = measure(x, rep.result_set, STORY, story_diff(diff), d).relevance
            vacuity = evaluate(te.UNITTEST, d, diff, STORY, deps, (rep, x), timeout_s=120).vacuity
        _, g = te.execute(regression_runner, d, REGRESSIONS, deps, timeout_s=120)
        return assemble(x, vacuity, relevance, g, chronology=RED_GREEN)

    def test_ADEQ_1_for_real(self):
        a = self.run_({"tests/test_calc.py": TEST_ADD}, patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.outcome, a.owner, a.adequacy.vacuity, a.adequacy.relevance), (A.ADEQUATE, None, V.NON_VACUOUS, R.RELEVANT))
        self.assertEqual((a.adequacy.execution.selection, a.adequacy.regressions.outcome), (TS.STORY_TESTS_RAN, TO.PASSED))

    def test_ADEQ_2_for_real_the_story_runner_cannot_execute(self):
        a = self.run_({"tests/test_calc.py": TEST_ADD}, patch(OLD, NEW, "app/calc.py"), story_runner=ABSENT)
        self.assertEqual((a.outcome, a.owner, a.adequacy.execution.status, a.adequacy.regressions.status),
                         (None, Owner.ENVIRONMENT, X.UNRUNNABLE, X.EXECUTED))

    def test_ADEQ_3_for_real_the_regression_runner_cannot_execute(self):
        a = self.run_({"tests/test_calc.py": TEST_ADD}, patch(OLD, NEW, "app/calc.py"), regression_runner=ABSENT)
        self.assertEqual((a.outcome, a.owner, a.adequacy.execution.status, a.adequacy.regressions.status),
                         (None, Owner.ENVIRONMENT, X.EXECUTED, X.UNRUNNABLE))
        self.assertEqual((a.adequacy.vacuity, a.adequacy.relevance), (V.NON_VACUOUS, R.RELEVANT))

    def test_ADEQ_4_and_10_for_real(self):
        a = self.run_({"tests/test_calc.py": TEST_WRONG}, patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.outcome, a.owner, a.adequacy.execution.outcome), (A.INADEQUATE, Owner.DEVELOPER, TO.FAILED))
        a = self.run_({"tests/test_calc.py": TEST_ADD, "tests/test_other.py": REG_BAD}, patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.outcome, a.owner, a.adequacy.regressions.outcome, a.reason),
                         (A.INADEQUATE, Owner.DEVELOPER, TO.FAILED, "INADEQUATE: regressions executed and failed"))

    def test_ADEQ_6_and_7_for_real_collection_failures_by_their_typed_owner(self):
        a = self.run_({"tests/test_calc.py": "from app import missing\n" + TEST_ADD}, patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.adequacy.execution.selection, a.adequacy.execution.owner_on_failure), (TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER))
        self.assertEqual((a.outcome, a.owner), (A.INADEQUATE, Owner.DEVELOPER))
        a = self.run_({"tests/test_calc.py": "import zzz_neither_declared_nor_project\n" + TEST_ADD}, patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.adequacy.execution.selection, a.adequacy.execution.owner_on_failure), (TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION))
        self.assertEqual((a.outcome, a.owner, a.adequacy.vacuity, a.may_block, a.developer_chargeable),
                         (A.INCOMPLETE, None, V.INDETERMINATE, False, False))

    def test_ADEQ_R_for_real_regression_selection_and_collection_by_their_typed_owner(self):
        a = self.run_({"tests/test_calc.py": TEST_ADD, "tests/test_other.py": "from app import missing\n" + REG_OK}, patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.adequacy.regressions.selection, a.adequacy.regressions.owner_on_failure), (TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER))
        self.assertEqual((a.outcome, a.owner), (A.INADEQUATE, Owner.DEVELOPER))
        a = self.run_({"tests/test_calc.py": TEST_ADD, "tests/test_other.py": "import unittest\n"}, patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.adequacy.regressions.selection, a.outcome, a.owner), (TS.NO_STORY_TESTS_MATCHED, A.INADEQUATE, Owner.DEVELOPER))
        a = self.run_({"tests/test_calc.py": TEST_ADD, "tests/test_other.py": "import zzz_neither_declared_nor_project\n" + REG_OK}, patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.adequacy.regressions.selection, a.adequacy.regressions.owner_on_failure), (TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION))
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INCOMPLETE, None, False, False))
        self.assertEqual((a.adequacy.vacuity, a.adequacy.relevance), (V.NON_VACUOUS, R.RELEVANT))   # the story side is clean

    def test_ADEQ_16_for_real_a_pure_deletion_otherwise_green_is_INCOMPLETE(self):
        a = self.run_({"tests/test_calc.py": TEST_GONE}, patch(NEW_LEGACY, NEW, "app/calc.py"))
        self.assertEqual((a.adequacy.vacuity, a.adequacy.relevance), (V.NON_VACUOUS, R.UNMEASURABLE))
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INCOMPLETE, None, False, False))
        self.assertEqual(a.reason, "INCOMPLETE (reduced engineering-quality coverage, never blocking, charged to nobody): relevance is UNMEASURABLE")

    def test_ADEQ_17_for_real_a_tests_only_diff_is_INADEQUATE_by_the_frozen_rules(self):
        a = self.run_({"tests/test_calc.py": TEST_ADD}, patch("", TEST_ADD, "tests/test_calc.py"))
        self.assertEqual((a.adequacy.vacuity, a.adequacy.relevance), (V.VACUOUS, R.IRRELEVANT))
        self.assertEqual((a.outcome, a.owner, a.may_block, a.developer_chargeable), (A.INADEQUATE, Owner.DEVELOPER, True, True))
        self.assertEqual(a.reason, "INADEQUATE: the story's tests are VACUOUS: they pass without the story's product change; "
                                   "the story's tests are IRRELEVANT: none touches the story's change")


if __name__ == "__main__":
    unittest.main()
