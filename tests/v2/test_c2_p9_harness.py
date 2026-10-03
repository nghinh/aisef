"""The QP-2.9 harness corrections of the owner ruling 'AISEF V2 — BOUNDED CORRECTIVE PATCH' — deterministic, no model,
no LedgerLock repository, nothing run:

  H-PROMPT-002       the developer prompt is built from the current authoritative sources only — the requirement
                     clauses of the story's obligations, the product subjects of the approved contracts, the plan
                     stories it depends on. No V1-era story text: its execution examples (attempt 3: STORY-01-05's
                     `("delete", key, rid, ts)`) contradicted the requirements and were implemented. It replaces
                     H-PROMPT-001, which kept that text as 'context only' without its metadata.
  §7                 a run's git objects are preserved outside its temporary directory before it is removed, and it
                     is not removed unless they are.
  §6                 the proposed `v1-aligned` profile gives 3 total developer attempts; the default profile is the
                     one attempts 1 and 2 ran.
  H-RETRY-001        a retry prompt states the evidence the journal holds for each failure — and, for a failed proof,
                     the criterion, contract, spec, probe, candidate, status, verdict, agreement, owner and cited seqs
                     — and nothing it does not hold: no probe input, stimulus or invented detail. It is prompt text
                     only; it cannot change the kernel's control (PROBE-DIAGNOSTIC-GAP-001 stays open).
  H-REGRESSION-001   a story's regression set leaves out only a test file that was never produced: a story that
                     committed without a developer call (K-PRESAT-001, K-NOWORK-001) wrote none, and naming it rolled
                     the next story back. Every real regression test stays; one that should exist and is gone is still
                     named, so its typed failure is kept (the owner's adversarial cases A-D).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole, Owner  # noqa: E402
from aisef2.orchestrate.workspace import commit_all, git  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402
from tests.v2 import test_p6_orchestration as e2e  # noqa: E402
from validation.qualification import c2_p9  # noqa: E402
from validation.qualification import c2_plan_correction as pc  # noqa: E402
from validation.qualification import p10_contracts as aid  # noqa: E402

#: V1-era control metadata and story prose: none of it may be in a prompt (H-PROMPT-001, H-PROMPT-002)
LEGACY_TOKENS = ("write_scope", "ac_proof", "story_type", "depends_on:", "covers:", "screens:", "Story metadata", "VERIFICATION_ONLY",
                 "ledgerlock/format.py", "tests/test_skeleton.py", "Scope note", "do not pre-empt", "PRESERVE_REQUIRED", "CHANGE_REQUIRED",
                 "NEGATIVE_INVARIANT", "### Story", "**As a**", "**I want**", "**So that**", "Acceptance criteria", "context only",
                 "historical context")
REQUIREMENTS = (ROOT / "tests/v2/fixtures/workloads/ledgerlock-reference/REQUIREMENTS.md").read_text(encoding="utf-8")
#: the legacy execution shapes of attempt 3's seven prompts, measured on the harness of the commit it executed on
ATTEMPT_3 = json.loads((ROOT / "tests/v2/fixtures/h_prompt_002/ATTEMPT-3-LEGACY-SHAPES.json").read_text(encoding="utf-8"))
#: what attempt 3's STORY-01-05 prompt prescribed, and every candidate after it implemented
FOUR_ELEMENT_DELETE = ('Ledger.append(("put", key, value, rid, ts))', '("delete", key, rid, ts)', 'delete("k", "r1", 100)')
#: a delete with three parts after the op, in a tuple or a call: the shape §5 does not have
DELETE_SHAPE = re.compile(r'\(\s*"delete"\s*,(?:[^,()]*,){2}[^,()]*\)|\bdelete\((?:[^,()]*,){2}[^,()]*\)')
CODE = re.compile(r"`([^`\n]+)`")
#: sha256 of the seven prompts of the corrected plan joined in story order (the prompt snapshot)
SNAPSHOT = "8d277f575dde49ad91e1de3365bf5fa55dc01f36e8a5a687810c5997f3e2876f"


def composites(value):
    """Every list and dict inside a probe input — each step, each argument list, each observable: what a prompt must
    never show (a leaf string may be a word the requirements also use)."""
    if isinstance(value, (list, dict)):
        yield value
        for v in (value.values() if isinstance(value, dict) else value):
            yield from composites(v)


class Prompt(unittest.TestCase):
    """H-PROMPT-002, on the real prompts: the corrected plan's seven stories over the frozen requirements."""

    @classmethod
    def setUpClass(cls):
        cls.plan = pc.corrected_plan()
        cls.tasks, cls.clauses, cls.by_criterion = c2_p9.prompts(cls.plan, REQUIREMENTS)

    def test_the_prompts_are_built_from_the_plan_and_the_requirements_only(self):
        self.assertEqual(list(inspect.signature(c2_p9.prompts).parameters), ["plan", "requirements"])
        self.assertEqual(sorted(self.tasks), ["STORY-01-01", "STORY-01-05", "STORY-02-01", "STORY-02-02", "STORY-03-01", "STORY-04-01",
                                              "STORY-04-02"])
        for name in ("story_prose", "epics_section", "LEGACY_BLOCK", "LEGACY_KEYS", "LEGACY_LINE", "LEGACY_NOTE"):
            self.assertFalse(hasattr(c2_p9, name), name)

    def test_no_legacy_metadata_or_story_text(self):
        for story, prompt in self.tasks.items():
            for token in LEGACY_TOKENS:
                with self.subTest(story=story, token=token):
                    self.assertNotIn(token, prompt)

    def test_the_four_element_delete_of_attempt_3_does_not_return(self):
        self.assertTrue(DELETE_SHAPE.search('`("delete", key, rid, ts)`') and DELETE_SHAPE.search('delete("k", "r1", 100)'))
        self.assertFalse(DELETE_SHAPE.search('("delete", key, value, rid, ts)'))          # §5's five-field tuple is not that shape
        for story, prompt in self.tasks.items():
            with self.subTest(story=story):
                self.assertEqual([x for x in FOUR_ELEMENT_DELETE if x in prompt], [])
                self.assertIsNone(DELETE_SHAPE.search(prompt))

    def test_none_of_attempt_3_s_legacy_execution_shapes_returns(self):
        self.assertEqual((ATTEMPT_3["shapes_total"], len(ATTEMPT_3["distinct_shapes_not_verbatim_in_the_requirements"])), (162, 43))
        self.assertTrue(set(FOUR_ELEMENT_DELETE[:2]) <= set(ATTEMPT_3["distinct_shapes_not_verbatim_in_the_requirements"]))
        for story, prompt in self.tasks.items():
            with self.subTest(story=story):
                self.assertEqual([x for x in ATTEMPT_3["distinct_shapes_not_verbatim_in_the_requirements"] if x in prompt], [])

    def test_every_code_span_is_requirement_text_or_the_harness_s_own_instruction(self):
        for story, prompt in self.tasks.items():
            own = {"ledgerlock/", f"python -m unittest {c2_p9.test_path(story)}"}
            with self.subTest(story=story):
                self.assertEqual([c for c in CODE.findall(prompt) if c not in own and c not in REQUIREMENTS], [])

    def test_no_hidden_probe_input(self):
        specs = {s.id: s for s in c2_p9._compiled().values()}
        for story, prompt in self.tasks.items():
            for o in (o for o in self.plan.obligations if o.story_id == story):
                pi = plain(specs[o.product_proof_spec_id].probe_input)
                hidden = [json.dumps(v, ensure_ascii=False) for v in composites({k: pi.get(k) for k in ("stimulus", "observable")})]
                with self.subTest(story=story, criterion=o.criterion_id):
                    self.assertEqual([h for h in hidden if len(h) > 6 and h in prompt], [])
            for word in ("stimulus", "observable", "expect_raises", "scenario", "within_s", "semantic_hash", "PPS-", "probe_input"):
                with self.subTest(story=story, word=word):
                    self.assertNotIn(word, prompt)

    def test_the_plan_stories_it_depends_on_are_named(self):
        self.assertNotIn("depends on", self.tasks["STORY-01-01"])
        self.assertIn("The stories of this plan it depends on: STORY-01-01, STORY-01-05, STORY-02-01, STORY-02-02.", self.tasks["STORY-03-01"])
        self.assertIn("The stories of this plan it depends on: STORY-01-01, STORY-01-05, STORY-02-01, STORY-02-02, STORY-03-01, STORY-04-01.",
                      self.tasks["STORY-04-02"])

    def test_scope_comes_from_the_current_plan_every_obligation_s_clause_and_the_contract_subjects(self):
        specs = {s.id: sid for sid, s in c2_p9._compiled().items()}
        for story, prompt in self.tasks.items():
            mine = [o for o in self.plan.obligations if o.story_id == story]
            with self.subTest(story=story):
                for o in mine:
                    self.assertIn(self.by_criterion[o.criterion_id], prompt)
                    self.assertIn(f"[{o.role.value}]", self.by_criterion[o.criterion_id])
                subjects = prompt.split("The product subjects those clauses are verified on: ")[1].split(".\n")[0]
                want = {c2_p9.subject_text(aid.SPECS[specs[o.product_proof_spec_id]]["kind"],
                                           aid.SPECS[specs[o.product_proof_spec_id]]["locator"]) for o in mine}
                self.assertEqual(set(subjects.split(", ")), want)
        s11 = self.tasks["STORY-01-01"]
        for subject in ("ledgerlock/ledger.py", "ledgerlock/cli.py", "ledgerlock/__init__.py", "python -m ledgerlock"):
            self.assertIn(subject, s11)                       # the files the obsolete write_scope did not have

    def test_the_prompt_snapshot(self):
        joined = "\n=====\n".join(f"{s}\n{self.tasks[s]}" for s in sorted(self.tasks))
        self.assertEqual(hashlib.sha256(joined.encode("utf-8")).hexdigest(), SNAPSHOT)

    def test_generation_is_deterministic(self):
        again = c2_p9.prompts(self.plan, REQUIREMENTS)
        self.assertEqual((self.tasks, self.clauses, self.by_criterion), again)


class Preservation(unittest.TestCase):
    def repository(self, root: pathlib.Path) -> tuple[pathlib.Path, str, str]:
        """A run repository: main at a final commit, and a rolled-back candidate that is on no branch."""
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
        final = commit_all(repo, "final main")
        wt = root / "wt"
        self.assertEqual(git(repo, "worktree", "add", "--detach", str(wt), final).returncode, 0)
        (wt / "app.py").write_text("x = 2\n", encoding="utf-8")
        candidate = commit_all(wt, "a candidate the story rolled back")
        self.assertEqual(git(repo, "worktree", "remove", "--force", str(wt)).returncode, 0)
        self.assertEqual(git(repo, "branch", "--contains", candidate).stdout.strip(), "")      # reachable from nothing
        return repo, final, candidate

    def test_final_main_and_an_unreachable_candidate_survive_the_removal_of_the_run_directory(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-c2-p9-keep-") as keep:
            dest = pathlib.Path(keep) / "attempt-3.git"
            with tempfile.TemporaryDirectory(prefix="aisef2-c2-p9-run-") as tmp:
                repo, final, candidate = self.repository(pathlib.Path(tmp))
                tree = git(repo, "rev-parse", f"{final}^{{tree}}").stdout.strip()
                kept = c2_p9.preserve(repo, dest, final, [final, candidate])
                self.assertEqual((kept["final_main"], kept["final_tree"], kept["missing"], kept["revisions_pinned"]), (final, tree, [], 2))
                self.assertTrue(c2_p9.may_remove(kept))
            self.assertFalse(pathlib.Path(tmp).exists())                    # the run's temporary directory is gone
            for sha in (final, candidate):
                self.assertEqual(git(dest, "cat-file", "-t", sha).stdout.strip(), "commit", sha)
            self.assertEqual(git(dest, "rev-parse", "refs/qp-2.9/final-main").stdout.strip(), final)
            self.assertEqual(git(dest, "rev-parse", f"refs/qp-2.9/revisions/{candidate}").stdout.strip(), candidate)
            self.assertEqual(git(dest, "show", f"{final}:app.py").stdout, "x = 1\n")     # the workspace can be read back
            self.assertEqual(git(dest, "show", f"{candidate}:app.py").stdout, "x = 2\n")
            self.assertEqual(git(dest, "fsck", "--no-dangling").returncode, 0)

    def test_a_revision_the_copy_does_not_hold_is_named_and_the_directory_is_then_kept(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-c2-p9-keep-") as keep, tempfile.TemporaryDirectory(prefix="aisef2-c2-p9-run-") as tmp:
            repo, final, _ = self.repository(pathlib.Path(tmp))
            absent = "0123456789abcdef0123456789abcdef01234567"
            kept = c2_p9.preserve(repo, pathlib.Path(keep) / "attempt-3.git", final, [final, absent])
            self.assertEqual(kept["missing"], [absent])
            self.assertFalse(c2_p9.may_remove(kept))

    def test_nothing_preserved_means_nothing_removed(self):
        self.assertFalse(c2_p9.may_remove(None))
        self.assertFalse(c2_p9.may_remove({"path": "x", "error": "OSError: disk full", "missing": ["<not preserved>"]}))
        self.assertFalse(c2_p9.may_remove({"path": "x", "final_main": "a", "final_tree": None, "missing": []}))

    def test_a_preserved_run_is_never_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-c2-p9-keep-") as keep, tempfile.TemporaryDirectory(prefix="aisef2-c2-p9-run-") as tmp:
            repo, final, candidate = self.repository(pathlib.Path(tmp))
            dest = pathlib.Path(keep) / "attempt-3.git"
            c2_p9.preserve(repo, dest, final, [final])
            with self.assertRaises(FileExistsError):
                c2_p9.preserve(repo, dest, final, [final, candidate])

    def test_the_revisions_a_run_names_are_the_ones_pinned(self):
        events = [{"type": "story/begin", "data": {"story_id": "S", "parent": "p" * 40}},
                  {"type": "proof/verified", "data": {"story_id": "S", "candidate": "c" * 40}},
                  {"type": "story/commit", "data": {"story_id": "S", "revision": "m" * 40}},
                  {"type": "story/rollback", "data": {"story_id": "T"}}]
        sessions = [{"role": "developer", "candidate": "d" * 40}, {"role": "reviewer"}]
        self.assertEqual(c2_p9.run_shas(events, sessions, "f" * 40), sorted(x * 40 for x in "pcmdf"))

    def test_the_preservation_root_is_outside_this_repository_and_can_be_set(self):
        old = os.environ.pop(c2_p9.PRESERVE_ENV, None)
        try:
            default = c2_p9.preserve_root().resolve()
            self.assertNotIn(ROOT.resolve(), [default, *default.parents])
            os.environ[c2_p9.PRESERVE_ENV] = "/somewhere/else"
            self.assertEqual(c2_p9.preserve_root(), pathlib.Path("/somewhere/else"))
        finally:
            os.environ.pop(c2_p9.PRESERVE_ENV, None)
            if old is not None:
                os.environ[c2_p9.PRESERVE_ENV] = old


class RetryProfile(unittest.TestCase):
    setUp = e2e.Orchestration.setUp
    story, inputs, adapters = e2e.Orchestration.story, e2e.Orchestration.inputs, e2e.Orchestration.adapters
    events, failures, details, assertAttempts = (e2e.Orchestration.events, e2e.Orchestration.failures, e2e.Orchestration.details,
                                                 e2e.Orchestration.assertAttempts)

    def attempts(self, profile: str) -> tuple[list[str], int]:
        limits = {Owner[k]: v for k, v in c2_p9.PROFILES[profile].items()}
        dev = e2e.Dev({"app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD_WRONG})    # never acceptable
        plan = e2e.plan_of(self.base, e2e.obligation("C1", self.s1.id, "S1", ObligationRole.INTRODUCE))
        r = self.story(plan, "S1", dev, tests_block=True, limits=limits)
        return [a.outcome for a in r.attempts], len(dev.calls)

    def test_the_default_profile_is_the_one_attempts_1_and_2_ran(self):
        self.assertIs(c2_p9.PROFILES["qp-2.9"], c2_p9.LIMITS)
        self.assertEqual(c2_p9.LIMITS, {"DEVELOPER": 1, "PLAN": 0, "ENVIRONMENT": 1, "PROVIDER": 1, "INTEGRATION": 0, "REVIEW": 1, "SECURITY": 1})
        self.assertEqual(self.attempts("qp-2.9"), (["RETRY", "ROLLBACK"], 2))                 # 2 developer attempts

    def test_the_proposed_v1_aligned_profile_gives_three_developer_attempts_and_changes_nothing_else(self):
        aligned = c2_p9.PROFILES["v1-aligned"]
        self.assertEqual({k: v for k, v in aligned.items() if v != c2_p9.LIMITS[k]}, {"DEVELOPER": 2})
        self.assertEqual(self.attempts("v1-aligned"), (["RETRY", "RETRY", "ROLLBACK"], 3))    # 3 total, as the V1 baseline


class RegressionSet(unittest.TestCase):
    """H-REGRESSION-001 (found reviewing K-NOWORK-001, measured through the real story path; accepted by the owner's
    ruling 'FINAL REBIND + SINGLE PAID DELIVERY EXPERIMENT' §1 with the adversarial cases A-D of its §3): the runner
    named the test file of every committed story as a regression test of the next — also of a story that committed
    without a developer call, which has none. `delivered` below is what the runner keeps: committed story -> whether
    main held its test file when it committed."""
    setUp = e2e.Orchestration.setUp
    story, inputs, adapters = e2e.Orchestration.story, e2e.Orchestration.inputs, e2e.Orchestration.adapters
    events, failures, details, assertAttempts = (e2e.Orchestration.events, e2e.Orchestration.failures, e2e.Orchestration.details,
                                                 e2e.Orchestration.assertAttempts)
    NO_CALL = "STORY-02-01"       # committed without a developer call: tests/test_story_02_01.py was never written

    def delivery(self, regressions: tuple[str, ...]):
        """A story with developer work, correct and adequately tested, under the blocking tests policy."""
        dev = e2e.Dev({"app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD})
        plan = e2e.plan_of(self.merger.base(), e2e.obligation("C1", self.s1.id, "S1", ObligationRole.INTRODUCE))
        return self.story(plan, "S1", dev, inputs=self.inputs("S1", regressions=regressions), tests_block=True)

    def assertTypedFailure(self, r) -> None:
        self.assertAttempts(r, ["RETRY", "ROLLBACK"])
        self.assertEqual({(code, owner) for code, owner, _ in self.failures("S1")}, {("TESTS_INADEQUATE", "DEVELOPER")})
        self.assertEqual({e.data["regressions"]["selection"] for e in self.events("tests/adequacy", "S1")}, {"STORY_TESTS_NOT_COLLECTABLE"})

    def test_the_defect_a_regression_file_nobody_wrote_rolls_a_correct_story_back(self):
        self.assertTypedFailure(self.delivery(("tests/test_other.py", c2_p9.test_path(self.NO_CALL))))   # the set the runner used to build

    def test_A_a_prior_story_s_real_test_file_stays_in_the_set(self):
        self.assertEqual(c2_p9.test_path("OTHER"), "tests/test_other.py")
        self.assertTrue(c2_p9.holds(self.repo, "tests/test_other.py"))
        named = c2_p9.regression_tests(self.repo, "S1", {"OTHER": True})
        self.assertEqual(named, ("tests/test_other.py",))
        r = self.delivery(named)
        self.assertAttempts(r, ["COMMIT"])
        self.assertEqual([e.data["regressions"]["selection"] for e in self.events("tests/adequacy", "S1")], ["STORY_TESTS_RAN"])   # and it ran

    def test_B_a_story_that_committed_without_a_test_file_injects_no_path(self):
        self.assertFalse(c2_p9.holds(self.repo, c2_p9.test_path(self.NO_CALL)))
        self.assertEqual(c2_p9.regression_tests(self.repo, "S1", {self.NO_CALL: False}), ("tests/test_s1.py",))      # the story's own, as for the first
        self.assertEqual(c2_p9.regression_tests(self.repo, "S1", {}), ("tests/test_s1.py",))
        named = c2_p9.regression_tests(self.repo, "S1", {"OTHER": True, self.NO_CALL: False})
        self.assertEqual(named, ("tests/test_other.py",))
        self.assertAttempts(self.delivery(named), ["COMMIT"])

    def test_C_a_mixed_sequence_keeps_every_real_test_in_order_and_fabricates_none(self):
        e2e.land(self.repo, {"tests/test_story_03_01.py": e2e.TEST_OTHER, "tests/test_story_04_01.py": e2e.TEST_OTHER}, "two later stories' tests")
        delivered = {"OTHER": True, self.NO_CALL: False, "STORY-02-02": False, "STORY-03-01": True,
                     "STORY-04-01": False}       # the last: not produced by its own story, yet main holds it — a valid test stays
        named = c2_p9.regression_tests(self.repo, "S1", delivered)
        self.assertEqual(named, ("tests/test_other.py", "tests/test_story_03_01.py", "tests/test_story_04_01.py"))
        self.assertAttempts(self.delivery(named), ["COMMIT"])

    def test_D_a_produced_test_file_that_is_gone_is_still_named_and_its_typed_failure_is_kept(self):
        gone = c2_p9.test_path("STORY-03-01")
        self.assertFalse(c2_p9.holds(self.repo, gone))
        named = c2_p9.regression_tests(self.repo, "S1", {"OTHER": True, "STORY-03-01": True})    # it was there when its story committed
        self.assertEqual(named, ("tests/test_other.py", gone))                                      # not dropped as if harmless
        self.assertTypedFailure(self.delivery(named))


ATTEMPT_3_JOURNAL = ROOT / "closure-evidence/v2/cycle2/P10/attempt-3/JOURNAL.json"
#: the retry feedback attempt 3's own journal gives for the first retry of STORY-03-01 and of STORY-04-02 (H-RETRY-001)
FEEDBACK_03_01 = (
    "- CONTRACT_UNSATISFIED (owner DEVELOPER) — STORY-03-01, criterion S-4.4-a [INTRODUCE]: R-4.4 (docs/requirements.md §4.4 "
    "Tombstones), clause R-4.4/1: a put with another rid after a tombstone MUST conflict\n"
    "  contract BC-V22-S-4.4-a, ProductProofSpec PPS-130df03b6e64d882a2b283367f0c58736ed84b017f59da3c296464f37edf0dff, probe "
    "probe.process_effect, subject ledgerlock.ledger:Ledger; candidate 917627ccd57e925478de22af8290299a6fb151bf: probe status "
    "EXECUTED, verdict REFUTED (expected SATISFIED), the independent verifier agrees. Evidence: journal seq 7072, 7075 (the probe "
    "records), 7076 (the proof), 7079 (this failure).\n"
    "  The candidate remains REFUTED for this approved contract and the independent verifier agrees. Inspect the implementation "
    "against that requirement clause. The hidden proof stimulus is not disclosed.")
FEEDBACK_04_02 = (
    "- CONTRACT_UNSATISFIED (owner DEVELOPER) — STORY-04-02, criterion S-D3-05-01-1 [VERIFY]: R-3.3 (docs/requirements.md §3.3 "
    "Tamper evidence), clause R-3.3/2: ok iff every recomputed hash matches AND every prev_hash matches the previous stored hash\n"
    "  contract BC-V22-S-D3-05-01-1, ProductProofSpec PPS-b3407979dd38c3b08a8bbae4199e4aee2bd4a7b747bb87a6f0ac80f276279404, probe "
    "probe.process_effect, subject ledgerlock.ledger:Ledger; candidate 6edb8634b0ca1008f8983c537e909635c1161b27: probe status "
    "EXECUTED, verdict REFUTED (expected SATISFIED), the independent verifier agrees. Evidence: journal seq 7689, 7692 (the probe "
    "records), 7693 (the proof), 7696 (this failure).\n"
    "  The candidate remains REFUTED for this approved contract and the independent verifier agrees. Inspect the implementation "
    "against that requirement clause. The hidden proof stimulus is not disclosed.")
INVENTED = re.compile(r"\b\w+(?:Error|Exception)\b|\braised\b|\bstep \d|\btraceback\b", re.I)


class RetryFeedback(unittest.TestCase):
    """H-RETRY-001 on attempt 3's own evidence: what the journal holds, and nothing it does not."""

    @classmethod
    def setUpClass(cls):
        cls.events = [(e["seq"], e["type"], e["data"]) for e in json.loads(ATTEMPT_3_JOURNAL.read_text(encoding="utf-8"))]
        cls.plan = pc.corrected_plan()
        cls.facts = c2_p9.obligation_facts(cls.plan, REQUIREMENTS)
        cls.specs = {s.id: s for s in c2_p9._compiled().values()}

    def before_retry(self, story: str, n: int = 1) -> list:
        """The journal as the developer's attempt n + 1 finds it: everything before that attempt's admission."""
        nth = [q for q, t, d in self.events if t == "story/admitted" and d["story_id"] == story][n]
        return [e for e in self.events if e[0] < nth]

    def test_story_03_01_and_04_02_attempt_3_evidence_give_bounded_feedback(self):
        self.assertEqual(c2_p9.retry_feedback(self.before_retry("STORY-03-01"), "STORY-03-01", self.facts), FEEDBACK_03_01)
        self.assertEqual(c2_p9.retry_feedback(self.before_retry("STORY-04-02"), "STORY-04-02", self.facts), FEEDBACK_04_02)

    def test_the_feedback_is_bound_to_the_evidence_it_cites(self):
        by_seq = {q: (t, d) for q, t, d in self.events}
        for story, text in (("STORY-03-01", FEEDBACK_03_01), ("STORY-04-02", FEEDBACK_04_02)):
            cited = [int(x) for x in re.findall(r"\d+", text.split("Evidence: journal seq ")[1].split(".")[0])]
            kinds = [by_seq[q][0] for q in cited]
            with self.subTest(story=story):
                self.assertEqual(kinds, ["probe/evaluated", "probe/evaluated", "proof/verified", "failure/observed"])
                cid = by_seq[cited[2]][1]["criterion_id"]
                self.assertTrue(all(by_seq[q][1]["story_id"] == story for q in cited))
                self.assertEqual({by_seq[q][1]["criterion_id"] for q in cited[:3]}, {cid})
                proof = by_seq[cited[2]][1]
                self.assertIn(f"candidate {proof['candidate']}:", text)                    # the exact candidate, full SHA
                self.assertEqual({by_seq[q][1]["record"]["revision"] for q in cited[:2]}, {proof["candidate"]})
                self.assertIn(f"ProductProofSpec {proof['spec_id']},", text)               # the exact spec
                self.assertIn(f"verdict {proof['verdict']} (expected {self.specs[proof['spec_id']].candidate_expectation.value})", text)
                hexes = set(re.findall(r"[0-9a-f]{40,64}", text))
                self.assertEqual(hexes, {proof["candidate"], proof["spec_id"].removeprefix("PPS-")})

    def test_no_hidden_probe_input_and_no_invented_detail_for_any_story(self):
        stories = sorted({d["story_id"] for _, t, d in self.events if t == "failure/observed"})
        for story in stories:
            text = c2_p9.retry_feedback(self.events, story, self.facts)
            told = text
            for f in self.facts.values():           # the approved clause texts are public facts (R-13/2 names ConflictError)
                told = told.replace(f["clause_text"], "")
            with self.subTest(story=story):
                self.assertTrue(text)
                self.assertIsNone(INVENTED.search(told))
                for o in (o for o in self.plan.obligations if o.story_id == story):
                    pi = plain(self.specs[o.product_proof_spec_id].probe_input)
                    hidden = [json.dumps(v, ensure_ascii=False) for v in composites({k: pi.get(k) for k in ("stimulus", "observable")})]
                    self.assertEqual([h for h in hidden if len(h) > 6 and h in text], [])
                for word in ("stimulus:", "observable", "scenario", "expect_raises", "probe_input", "oracle", "mutant", "reference"):
                    self.assertNotIn(word, text)

    def test_the_journal_records_no_observation_detail_to_tell(self):
        """PROBE-DIAGNOSTIC-GAP-001: every probe record of attempt 3 holds a verdict and a reason only."""
        shapes = {tuple(sorted(d["record"]["result"])) for _, t, d in self.events if t == "probe/evaluated"}
        self.assertEqual(shapes, {("behavior_verdict", "reason")})
        gap = json.loads((ROOT / "closure-evidence/v2/cycle2/PROBE-DIAGNOSTIC-GAP-001.json").read_text(encoding="utf-8"))
        self.assertEqual((gap["status"], gap["measured"]["attempt_3_probe_records"]),
                         ("ESCALATED_MEASURED_BLOCKER", {"total": 414, "verdict_and_reason_only": 414}))   # owner ruling 2026-10-03 §E
        self.assertEqual(gap["status_history"][0]["status"], "OPEN")

    def test_a_probe_that_did_not_execute_gives_no_advice_and_no_record_detail(self):
        for result, code, owner in (({"detail": "harness launch failed: ENOENT secret-path"}, "PROBE_UNRUNNABLE", "ENVIRONMENT"),
                                    ({"detail": "unsupported locator <hidden>"}, "PROBE_INVALID_SPEC", "PLAN")):
            rec = {"record": {"result": result, "revision": "a" * 40}, "story_id": "STORY-03-01", "criterion_id": "S-4.4-a"}
            events = [(1, "probe/evaluated", rec), (2, "probe/evaluated", rec),
                      (3, "proof/verified", {"story_id": "STORY-03-01", "criterion_id": "S-4.4-a", "candidate": "a" * 40, "agreement": True,
                                             "spec_id": self.facts["S-4.4-a"]["spec"]}),
                      (4, "failure/observed", {"story_id": "STORY-03-01", "code": code, "owner": owner, "detail": f"proof of S-4.4-a: {code}"})]
            text = c2_p9.retry_feedback(events, "STORY-03-01", self.facts)
            with self.subTest(code=code):
                self.assertIn(f"- {code} (owner {owner})", text)
                self.assertIn("probe status not EXECUTED", text)
                self.assertNotIn("verdict", text.split("subject ")[1])
                self.assertNotIn("Inspect the implementation", text)
                self.assertNotIn(result["detail"], text)

    def test_identical_evidence_gives_byte_identical_feedback(self):
        events = self.before_retry("STORY-04-02", 2)
        once = c2_p9.retry_feedback(events, "STORY-04-02", self.facts)
        again = c2_p9.retry_feedback(json.loads(json.dumps(events)), "STORY-04-02", json.loads(json.dumps(self.facts)))
        self.assertEqual(once.encode("utf-8"), again.encode("utf-8"))
        self.assertEqual(once.count("- CONTRACT_UNSATISFIED (owner DEVELOPER)"), 2)                # both failed attempts, in order

    def test_a_failure_that_is_not_a_proof_is_its_code_owner_and_typed_detail(self):
        events = [(1, "failure/observed", {"story_id": "S", "code": "TESTS_INADEQUATE", "owner": "DEVELOPER", "detail": "engineering quality: TESTS_INADEQUATE"})]
        self.assertEqual(c2_p9.retry_feedback(events, "S", self.facts), "- TESTS_INADEQUATE (owner DEVELOPER): engineering quality: TESTS_INADEQUATE")


class RetryFeedbackControl(unittest.TestCase):
    """H-RETRY-001 through the real story path: the feedback is prompt text only — whatever it says, the kernel's
    owner, retryability, budget, verdicts and gate decisions are the same."""
    setUp = e2e.Orchestration.setUp
    story, inputs, adapters = e2e.Orchestration.story, e2e.Orchestration.inputs, e2e.Orchestration.adapters
    WRONG = {"app/calc.py": e2e.CALC + "\n\ndef add(a, b):\n    return a - b\n"}
    RIGHT = {"app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD}

    def deliver(self) -> tuple[list, list[str]]:
        prompts: list[str] = []

        def session(name, prompt, cwd, log, timeout_s, **kw):
            prompts.append(prompt)
            for rel, text in (self.WRONG if len(prompts) == 1 else self.RIGHT).items():
                pathlib.Path(cwd, rel).parent.mkdir(parents=True, exist_ok=True)
                pathlib.Path(cwd, rel).write_text(text, encoding="utf-8")
            return {"error": None, "exit": 0, "timed_out": False, "stopped": None, "turns": 1, "text": "", "started": True,
                    "tokens": {"input": 0, "output": 0}, "seconds": 0.0, "log": None, "log_sha256": None}
        facts = {"C1": {"story": "S1", "criterion": "C1", "role": "INTRODUCE", "requirement": "R-1", "section": "§1 Adding",
                        "clause": "R-1/1", "clause_text": "add returns the sum", "contract": self.c1.id, "spec": self.s1.id,
                        "probe": self.s1.probe_id, "candidate_expectation": self.s1.candidate_expectation.value, "subject": "app.calc:add"}}
        dev = c2_p9.OpenCodeDeveloper(self.run, {"S1": "Implement S1."}, self.tmp / "logs", facts)
        plan = e2e.plan_of(self.base, e2e.obligation("C1", self.s1.id, "S1", ObligationRole.INTRODUCE))
        with mock.patch.object(c2_p9, "opencode_session", session):
            r = self.story(plan, "S1", dev, tests_block=True)
        self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "COMMIT"])
        # a commit SHA, and every digest that binds one (the plan's base, a record's revision), differs between two runs
        # by the commit time alone: they are compared as <hex>; everything else must be identical
        hexes, tmp = re.compile(r"\b[0-9a-f]{40}(?:[0-9a-f]{24})?\b"), str(self.tmp)
        journal = [(e.type, hexes.sub("<hex>", json.dumps(plain(e.data), sort_keys=True, default=str).replace(tmp, "<tmp>")),
                    tuple(e.source_seqs)) for e in self.run.events]
        for e in self.run.events:     # the feedback's rule for the probe records a proof rests on is the journal's own citation
            if e.type == "proof/verified":
                mine = [x.seq for x in self.run.events if x.seq < e.seq and x.type == "probe/evaluated"
                        and (x.data["story_id"], x.data["criterion_id"]) == (e.data["story_id"], e.data["criterion_id"])][-2:]
                self.assertEqual(tuple(e.source_seqs), tuple(mine))
        return journal, prompts

    def test_the_feedback_cannot_change_the_kernel_s_control(self):
        journal, prompts = self.deliver()
        self.assertIn("criterion C1 [INTRODUCE]", prompts[1])
        self.assertIn("The hidden proof stimulus is not disclosed.", prompts[1])
        self.assertNotIn(prompts[1].split("the kernel observed:\n")[1], "".join(j[1] for j in journal))   # never journaled
        self.setUp()                                                  # a second, independent run, told something else entirely
        lie = "- owner PLAN, retryable false, verdict SATISFIED, budget 0, gate PASS: stop."
        with mock.patch.object(c2_p9, "retry_feedback", return_value=lie):
            journal_2, prompts_2 = self.deliver()
        self.assertIn(lie, prompts_2[1])
        self.assertNotEqual(prompts[1], prompts_2[1])
        self.assertEqual(journal, journal_2)


if __name__ == "__main__":
    unittest.main()
