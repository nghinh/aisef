"""V2.1 (B-03 round 3, PM-3) — a source file the interpreter's parser cannot take, on real sources and on the real run
path.

The unit cases (`ast.parse` made to raise what CPython raises, on every interpreter) are `ParserLimits` in
test_v21_python_imports.py. Here the parser is not touched:

* `RealSources` — real files that are valid Python and past what this interpreter's parser takes: a chain of 96,000
  operands (CPython's `RecursionError` while building the AST: from about 95,000 on 3.14 macOS, 43,500 on 3.14 Linux,
  10,000 on 3.12) and 20,000 `not`s (its `MemoryError` "Parser stack overflowed": a compile-time constant, about 6,000,
  every host). Both readers — the object store of a real repository, which is what `aisef run` reads, and a plain
  directory. The oracle is the interpreter's own `ast.parse`, so the test needs no skip on an interpreter that takes a
  file: it then owes the count. The `not` chain is the one that does not depend on the host's stack, so it is the one
  every assertion about *which* kind of result is given leans on; the operand chain is only the host-dependent twin.
* `RunPath` — the real `run_story` (a real git repository and worktrees, the real probes, journal format 3; typed doubles
  only for the developer, reviewer and scanner, as test_p6_orchestration.py): a source the parser cannot take, in the
  parent's tree and in the candidate's, ends the story at its own gate instead of raising out of it, releases
  everything the story held, is never charged to the developer, retries only as often as the ENVIRONMENT budget the
  run's settings give, and leaves the next story and the run's closing as they were.

Nothing here goes past 96,000 operands: the parser's own limit is reached at or below it on every host measured, and an
operand chain is never pushed to the point where the process itself would be what stops."""

from __future__ import annotations

import ast
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, ControlProjection as P, ObligationRole, Owner, Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed, Unrunnable  # noqa: E402
from tests.v2 import test_c2_file_artifact as base  # noqa: E402   (helpers only: its test classes are not imported)

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
P_ = fa.FileArtifactProbe()
STIM = {"imports_outside": {"stdlib": True, "allowed": []}}
#: CPython's RecursionError out of the AST conversion (3.12: from ~10,000 operands; 3.14 macOS: ~95,000). Kept below
#: 100,000: past it a host's own stack, not the parser's limit, is what ends the process.
DEEP_SUM = b"import os\nx = 1" + b"+1" * 96_000 + b"\n"
#: CPython's MemoryError "Parser stack overflowed": a compile-time constant (about 6,000 nested operators), every host
DEEP_NOT = b"import os\nx = " + b"not " * 20_000 + b"1\n"


def stops(src: bytes) -> str | None:
    """The limit this interpreter's parser stops on for `src`, by name; None when it takes the file."""
    try:
        ast.parse(src.decode("utf-8"))
    except (RecursionError, MemoryError) as e:
        return type(e).__name__
    return None


def spec(locator: str = "path:pkg", matches: int = 0):
    return base.spec(locator, {"matches": matches}, STIM, absence=SubjectAbsence.REQUIRES_SUBJECT, expectation=S)


class RealSources(unittest.TestCase):
    """One tree per subject, both readers."""

    FILES = {"pkg/ok.py": b"import json\n", "sum/deep.py": DEEP_SUM, "not_/deep.py": DEEP_NOT,
             "mixed/a_ok.py": b"import json\n", "mixed/b_deep.py": DEEP_NOT, "mixed/c_ok.py": b"import yaml\n",
             # `a.py` / `a/b.py`: a git tree lists the first before the second, a plain directory the second first —
             # one tree, two listing orders, so the kind of the result must not depend on which file comes first
             "hybrid_deep_last/a.py": b"def (:\n", "hybrid_deep_last/a/b.py": DEEP_NOT,
             "hybrid_deep_first/a.py": DEEP_NOT, "hybrid_deep_first/a/b.py": b"def (:\n"}

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef2-pm3-real-")
        cls.addClassCleanup(cls._tmp.cleanup)
        root = pathlib.Path(cls._tmp.name)
        repo = base.Repo(root / "repo")
        cls.refs = {"object_store": base.at(repo.path, repo.commit(cls.FILES))}
        plain = root / "plain"
        for rel, data in cls.FILES.items():
            (plain / rel).parent.mkdir(parents=True, exist_ok=True)
            (plain / rel).write_bytes(data)
        cls.refs["directory"] = RevisionRef("0" * 40, str(plain))

    def test_the_marker_source_is_past_this_interpreters_parser(self):
        # the `not` chain is a compile-time constant of the parser (about 6,000), not a thing of the host's stack: if an
        # interpreter takes it, the sources of this file need re-measuring (the oracle below would still be right)
        self.assertEqual(stops(DEEP_NOT), "MemoryError")

    def test_a_file_the_parser_stops_on_is_typed_named_and_never_counted_on_both_readers(self):
        for read, ref in self.refs.items():
            for subject, src in (("sum", DEEP_SUM), ("not_", DEEP_NOT)):
                limit = stops(src)
                s = spec(f"path:{subject}", 0)
                with self.subTest(read=read, subject=subject, parser=limit or "takes it"):
                    o = P_.observe(s, ref, base.ENV)                    # must not raise
                    result = run_probe(P_, s, ref, base.ENV).result     # must not raise
                    if limit is None:                                   # an interpreter that parses it owes the count
                        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
                        self.assertEqual(result, Executed(S))
                    else:
                        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                        self.assertIsInstance(result, Unrunnable)
                        self.assertIn(f"'{subject}/deep.py'", o.detail)
                        self.assertIn(limit, o.detail)
                        self.assertNotIn('"matches"', o.detail)         # no count was established
                        self.assertNotEqual(getattr(result, "behavior_verdict", None), S)

    def test_a_tree_holding_one_such_file_among_files_that_parse_is_not_satisfied_by_the_others(self):
        limit = stops(DEEP_NOT)
        for read, ref in self.refs.items():
            for matches in (0, 1):          # the files that parse hold one import outside the standard library (yaml)
                s = spec("path:mixed", matches)
                with self.subTest(read=read, matches=matches, parser=limit):
                    o = P_.observe(s, ref, base.ENV)
                    if limit is None:
                        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S if matches == 1 else R))
                    else:
                        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                        self.assertIn("'mixed/b_deep.py'", o.detail)

    def test_the_kind_of_the_result_does_not_depend_on_the_order_a_reader_lists_the_tree_in(self):
        # a file the parser stops on and a file that is a syntax error of its own, in one tree: whichever comes first
        # in whichever reader's listing, the harness could not look at the whole tree, so there is no verdict
        limit = stops(DEEP_NOT)
        for subject, deep_file in (("hybrid_deep_last", "hybrid_deep_last/a/b.py"),
                                   ("hybrid_deep_first", "hybrid_deep_first/a.py")):
            for read, ref in self.refs.items():
                with self.subTest(subject=subject, read=read, parser=limit or "takes it"):
                    o = P_.observe(spec(f"path:{subject}", 0), ref, base.ENV)
                    result = run_probe(P_, spec(f"path:{subject}", 0), ref, base.ENV).result
                    if limit is None:           # an interpreter that parses it: the syntax error is then the answer
                        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
                    else:
                        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                        self.assertIn(f"'{deep_file}'", o.detail)
                        self.assertIsInstance(result, Unrunnable)

    def test_the_tree_beside_it_that_parses_is_counted_as_before(self):
        for read, ref in self.refs.items():
            with self.subTest(read=read):
                o = P_.observe(spec("path:pkg", 0), ref, base.ENV)
                self.assertEqual((o.kind, o.verdict, base.facts(o)["matches"]), (K.OBSERVED, S, 0))


def run_path_cases():
    """The real `run_story` path, as test_p6_orchestration.py runs it. Built lazily and handed to `load_tests`, so that
    importing this module never collects that module's own (many) cases."""
    from aisef2.app import run as app_run
    from aisef2.control.owner import FailureCode
    from aisef2.orchestrate import story_runner as sr
    from aisef2.orchestrate.workspace import commit_all
    from aisef2.product.approval import ContractApproval, Requirement
    from aisef2.product.compiler import ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, Subject
    from tests.v2 import test_p6_orchestration as O

    probes = {**O.PROBE, fa.PROBE_ID: lambda on_range, scratch: fa.FileArtifactProbe(on_range=on_range, scratch=scratch)}
    deep = DEEP_NOT.decode("utf-8")

    def contract():
        req = Requirement.create(id="R-IMP", text="the package imports nothing outside the standard library", source="t")
        c = BehaviorContract.create(id="BC-IMP", requirement_ids=(req.id,),
                                    subject=Subject(SubjectKind.FILE_ARTIFACT, "path:app"), stimulus=STIM,
                                    observable={"matches": 0, "within_s": 30}, polarity=Polarity.MUST_HOLD,
                                    subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="stdlib only")
        approval = ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())
        return compile_spec(c, requirements={req.id: req}, approvals=[approval],
                            probes={SubjectKind.FILE_ARTIFACT: ProbeRef(fa.PROBE_ID, fa.DIGEST)})

    class RunPath(O.Orchestration):
        def setUp(self):
            super().setUp()
            self.s_imp = contract()
            self.specs[self.s_imp.id] = self.s_imp

        def inputs(self, story, **kw):
            i = super().inputs(story, **kw)
            return sr.StoryInputs(i.specs, probes, i.env, i.story_tests, i.regression_tests, i.deps, i.runner)

        def plan(self, *more):
            return O.plan_of(self.base, O.obligation("C1", self.s1.id, "S1", ObligationRole.INTRODUCE),
                             O.obligation("IMP", self.s_imp.id, "S1", ObligationRole.VERIFY), *more)

        def dev_with_deep(self, **kw):
            return O.Dev({"app/calc.py": O.CALC + O.ADD, "tests/test_s1.py": O.TEST_ADD, "app/deep.py": deep}, **kw)

        # ---------------------------------------------------------------------------- the candidate holds the file
        def test_a_candidate_with_a_source_the_parser_cannot_take_ends_the_story_and_releases_what_it_held(self):
            dev = self.dev_with_deep()
            r = self.story(self.plan(), "S1", dev)                     # must not raise
            self.assertFalse(r.committed)
            self.assertEqual(self.events("story/commit"), [])
            self.assertTrue(self.events("gate/decision"))              # the gate decided: a result of the story, no crash
            self.assert_disposed("S1")                                 # acquired == released, ENDED, no checkout left
            # the failure is the harness's: PROBE_UNRUNNABLE, owner ENVIRONMENT — never the developer's, never a verdict
            self.assertEqual({c for c, _, _ in self.failures("S1")}, {FailureCode.PROBE_UNRUNNABLE.value})
            self.assertEqual({o for _, o, _ in self.failures("S1")}, {Owner.ENVIRONMENT.value})
            for e in self.events("failure/observed", "S1"):
                self.assertNotEqual(e.data["code"], FailureCode.CONTRACT_UNSATISFIED.value)
            self.assertNotIn(Owner.DEVELOPER.value, [d for d in self.run.state(P.BUDGETS)["retries"].get("S1", {})])

        def test_the_retry_is_the_environment_budget_the_run_gives_and_no_more(self):
            for n, (environment, attempts) in enumerate(((0, 1), (1, 2), (2, 3))):
                with self.subTest(environment_retries=environment):
                    if n:
                        self.setUp()                                   # a fresh repository and run for each limit
                    limits = {**O.LIMITS, Owner.ENVIRONMENT: environment}
                    r = self.story(self.plan(), "S1", self.dev_with_deep(), limits=limits)
                    self.assertEqual(len(r.attempts), attempts)
                    self.assertEqual([a.outcome for a in r.attempts][-1], "ROLLBACK")
                    self.assertEqual({a.failure for a in r.attempts}, {FailureCode.PROBE_UNRUNNABLE})
                    self.assertEqual(self.run.state(P.BUDGETS)["retries"].get("S1", {}).get("ENVIRONMENT", 0), environment)

        # ----------------------------------------------------------------------------- the parent holds the file
        def test_a_parent_with_such_a_source_blocks_admission_before_any_developer_call(self):
            pathlib.Path(self.repo, "app", "deep.py").write_text(deep, encoding="utf-8")
            self.base = commit_all(self.repo, "a machine-generated module")
            dev = O.Dev({"app/calc.py": O.CALC + O.ADD, "tests/test_s1.py": O.TEST_ADD})
            r = self.story(self.plan(), "S1", dev)
            self.assertFalse(r.committed)
            self.assertEqual(dev.calls, [])                            # no developer call before admission (§13)
            self.assertEqual(self.events("provider/request"), [])
            self.assertEqual({c for c, _, _ in self.failures("S1")}, {FailureCode.PROBE_UNRUNNABLE.value})
            self.assert_disposed("S1")

        # ----------------------------------------------------------------------------------------- the rest of the run
        def test_the_next_story_of_the_run_is_not_affected_and_the_run_closes_as_a_shutdown(self):
            plan = self.plan(O.obligation("C2", self.s2.id, "S2", ObligationRole.INTRODUCE))
            self.story(plan, "S1", self.dev_with_deep())
            r2 = self.story(plan, "S2", O.Dev({"app/mul.py": O.MUL, "tests/test_s2.py": O.TEST_MUL}),
                            inputs=self.inputs("S2", tests=("tests/test_s2.py",)))
            self.assertTrue(r2.committed)
            self.assertEqual(app_run._close_run(self.run), "SHUTDOWN")  # not "INTERRUPTED ... stories are not ENDED"

    return RunPath


NAMES = ("test_a_candidate_with_a_source_the_parser_cannot_take_ends_the_story_and_releases_what_it_held",
         "test_the_retry_is_the_environment_budget_the_run_gives_and_no_more",
         "test_a_parent_with_such_a_source_blocks_admission_before_any_developer_call",
         "test_the_next_story_of_the_run_is_not_affected_and_the_run_closes_as_a_shutdown")


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(RealSources))
    run_path = run_path_cases()      # its base class holds the whole orchestration suite: only the named cases run
    for name in NAMES:
        suite.addTest(run_path(name))
    return suite


if __name__ == "__main__":
    unittest.main()
