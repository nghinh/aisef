"""The QP-2.9 harness corrections of the owner ruling 'AISEF V2 — BOUNDED CORRECTIVE PATCH' — deterministic, no model,
no LedgerLock repository, nothing run:

  H-PROMPT-001 (§4)  the developer prompt carries no V1-era control metadata (write_scope / ac_proof / story_type /
                     covers / depends_on / screens); the legacy story text is prose context that yields to the current
                     clauses; the product subjects come from the approved contracts.
  §7                 a run's git objects are preserved outside its temporary directory before it is removed, and it
                     is not removed unless they are.
  §6                 the proposed `v1-aligned` profile gives 3 total developer attempts; the default profile is the
                     one attempts 1 and 2 ran.
  H-REGRESSION-001   a story's regression set names only test files main holds: a story that committed without a
                     developer call (K-PRESAT-001, K-NOWORK-001) wrote none, and naming it rolled the next story back.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole, Owner  # noqa: E402
from aisef2.orchestrate.workspace import commit_all, git  # noqa: E402
from tests.v2 import test_p6_orchestration as e2e  # noqa: E402
from validation.qualification import c2_p9  # noqa: E402
from validation.qualification import p10_contracts as aid  # noqa: E402

#: Story 1.1's metadata exactly as the V1-era epics carry it at the plan commit (the block attempt 2 handed over)
STORY_1_1_METADATA = """**Story metadata:**
- covers: FR-1, FR-12, FR-14
- ac_proof: 1=CHANGE_REQUIRED/FR-1, 2=CHANGE_REQUIRED/FR-1, 3=CHANGE_REQUIRED/FR-14, 4=NEGATIVE_INVARIANT/FR-14, 5=NEGATIVE_INVARIANT/FR-14, 6=CHANGE_REQUIRED/FR-14, 7=CHANGE_REQUIRED/FR-12
- write_scope: pyproject.toml, ledgerlock/__init__.py, ledgerlock/__main__.py, ledgerlock/format.py, tests/__init__.py, tests/test_skeleton.py, tests/test_nfc_normalization.py, README.md
- depends_on: none
- screens: none"""
STORIES = [(1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (2, 1), (2, 2), (3, 1), (3, 2), (4, 1), (4, 2), (4, 3), (5, 1), (5, 2), (5, 3)]
LEGACY_TOKENS = ("write_scope", "ac_proof", "story_type", "depends_on:", "covers:", "screens:", "Story metadata", "VERIFICATION_ONLY",
                 "ledgerlock/format.py", "tests/test_skeleton.py", "Scope note", "do not pre-empt", "PRESERVE_REQUIRED", "CHANGE_REQUIRED",
                 "NEGATIVE_INVARIANT")
#: Story 4.1's ownership note in the V1-era epics (prose, outside the metadata block): V1 ownership and a V1 proof mode
SCOPE_NOTE = ("Scope note: the **error** exit codes are STORY-04-02's contract. Implement the success paths here; do not pre-empt "
              "them. This story must not regress the usage-error exit, which is why its criterion here is PRESERVE_REQUIRED.")
REQUIREMENTS = (ROOT / "tests/v2/fixtures/workloads/ledgerlock-reference/REQUIREMENTS.md").read_text(encoding="utf-8")
#: sha256 of the nine generated prompts joined in story order, over the synthetic epics below (the prompt snapshot)
SNAPSHOT = "858af6d1ff552d47c0c956516bd62436d3d6492fc96357721ebca9b6a826ee1d"


def epics() -> str:
    """A V1-shaped epics document: every story a section with prose and a 'Story metadata' block."""
    out = ["# Epics", "", "## Epic 1: Foundation"]
    for e, n in STORIES:
        meta = STORY_1_1_METADATA if (e, n) == (1, 1) else (
            f"**Story metadata:**\n- covers: FR-{e}\n- ac_proof: 1=CHANGE_REQUIRED/FR-{e}\n"
            + ("- story_type: VERIFICATION_ONLY\n" if e == 5 else "")
            + f"- write_scope: ledgerlock/legacy_{e}_{n}.py, tests/test_legacy_{e}_{n}.py\n- depends_on: {e}.{n - 1 or 1}\n- screens: none")
        out += ["", f"### Story {e}.{n}: legacy title {e}.{n}", "", f"**As a** developer **I want** behaviour {e}.{n}.", "",
                *([SCOPE_NOTE, ""] if (e, n) == (4, 1) else []),
                "**Acceptance criteria:**", "", f"- Given the library, when story {e}.{n} is done, then `normalize_key` behaves.", "", meta]
    return "\n".join(out) + "\n"


class Prompt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = aid.build()["plan"]
        cls.epics = epics()
        cls.tasks, cls.clauses, cls.by_criterion = c2_p9.prompts(cls.plan, cls.epics, REQUIREMENTS)

    def test_the_fixture_is_contaminated_the_way_attempt_2_was(self):
        legacy = c2_p9.epics_section(self.epics, "STORY-01-01")
        self.assertIn("write_scope: pyproject.toml, ledgerlock/__init__.py, ledgerlock/__main__.py, ledgerlock/format.py", legacy)
        self.assertNotIn("ledger.py", legacy.split("write_scope:")[1].splitlines()[0])   # the obsolete scope has no ledger.py

    def test_no_prompt_carries_legacy_control_metadata(self):
        self.assertEqual(sorted(self.tasks), sorted({o.story_id for o in self.plan.obligations}))
        self.assertEqual(len(self.tasks), 9)
        for story, prompt in self.tasks.items():
            for token in LEGACY_TOKENS:
                with self.subTest(story=story, token=token):
                    self.assertNotIn(token, prompt)

    def test_the_prose_of_a_legacy_section_is_kept_without_its_metadata(self):
        prose = c2_p9.story_prose(self.epics, "STORY-01-01")
        self.assertTrue(prose.startswith("### Story 1.1: legacy title 1.1"))
        self.assertIn("**Acceptance criteria:**", prose)
        self.assertIn("normalize_key", prose)
        self.assertNotIn("Story metadata", prose)
        for story in sorted({f"STORY-{e:02d}-{n:02d}" for e, n in STORIES}):
            self.assertEqual([k for k in c2_p9.LEGACY_KEYS if f"{k}:" in c2_p9.story_prose(self.epics, story)], [], story)

    def test_a_scope_note_paragraph_is_removed_and_the_prose_around_it_kept(self):
        legacy = c2_p9.epics_section(self.epics, "STORY-04-01")
        self.assertIn("Scope note:", legacy)
        prose = c2_p9.story_prose(self.epics, "STORY-04-01")
        self.assertEqual(prose, "### Story 4.1: legacy title 4.1\n\n**As a** developer **I want** behaviour 4.1.\n\n"
                                "**Acceptance criteria:**\n\n- Given the library, when story 4.1 is done, then `normalize_key` behaves.")

    def test_a_stray_metadata_line_outside_the_block_is_removed_too(self):
        stray = "### Story 1.1: t\n\nprose line\n- write_scope: ledgerlock/format.py\n* ac_proof: 1=CHANGE_REQUIRED/FR-1\nmore prose\n"
        self.assertEqual(c2_p9.story_prose(stray, "STORY-01-01"), "### Story 1.1: t\n\nprose line\nmore prose")

    def test_the_legacy_text_is_stated_as_context_that_yields_to_the_clauses(self):
        for story, prompt in self.tasks.items():
            with self.subTest(story=story):
                self.assertIn("historical context only", prompt)
                self.assertIn("the clauses and the requirements govern", prompt)
                self.assertLess(prompt.index("historical context only"), prompt.index("The story (context only):"))
                self.assertLess(prompt.index("The story (context only):"), prompt.index("each of the following requirement clauses"))

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

    def test_the_proof_stays_independent_no_stimulus_observable_or_expectation_is_shown(self):
        for story, prompt in self.tasks.items():
            for word in ("stimulus", "observable", "expect_raises", "scenario", "within_s", "semantic_hash", "PPS-"):
                with self.subTest(story=story, word=word):
                    self.assertNotIn(word, prompt)

    def test_the_prompt_snapshot(self):
        joined = "\n=====\n".join(f"{s}\n{self.tasks[s]}" for s in sorted(self.tasks))
        self.assertEqual(hashlib.sha256(joined.encode("utf-8")).hexdigest(), SNAPSHOT)

    def test_generation_is_deterministic(self):
        again = c2_p9.prompts(self.plan, self.epics, REQUIREMENTS)
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
    """H-REGRESSION-001 (found reviewing K-NOWORK-001, measured through the real story path): the runner named the test
    file of every committed story as a regression test of the next — also of a story that committed without a developer
    call, which has none."""
    setUp = e2e.Orchestration.setUp
    story, inputs, adapters = e2e.Orchestration.story, e2e.Orchestration.inputs, e2e.Orchestration.adapters
    events, failures, details, assertAttempts = (e2e.Orchestration.events, e2e.Orchestration.failures, e2e.Orchestration.details,
                                                 e2e.Orchestration.assertAttempts)

    def delivery(self, regressions: tuple[str, ...]):
        """A story with developer work, correct and adequately tested, under the blocking tests policy."""
        dev = e2e.Dev({"app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD})
        plan = e2e.plan_of(self.base, e2e.obligation("C1", self.s1.id, "S1", ObligationRole.INTRODUCE))
        return self.story(plan, "S1", dev, inputs=self.inputs("S1", regressions=regressions), tests_block=True)

    def test_a_regression_file_nobody_wrote_rolls_a_correct_story_back(self):
        r = self.delivery(("tests/test_other.py", c2_p9.test_path("STORY-02-01")))       # the set the runner used to build
        self.assertAttempts(r, ["RETRY", "ROLLBACK"])
        self.assertEqual({(code, owner) for code, owner, _ in self.failures("S1")}, {("TESTS_INADEQUATE", "DEVELOPER")})
        self.assertEqual({e.data["regressions"]["selection"] for e in self.events("tests/adequacy", "S1")}, {"STORY_TESTS_NOT_COLLECTABLE"})

    def test_the_set_the_runner_builds_names_only_the_files_main_holds_and_the_story_commits(self):
        delivered = ["OTHER", "STORY-02-01"]                    # the second committed without a developer call: no file
        self.assertEqual(c2_p9.test_path("OTHER"), "tests/test_other.py")
        held = c2_p9.regression_tests(self.repo, "S1", delivered)
        self.assertEqual(held, ("tests/test_other.py",))
        self.assertAttempts(self.delivery(held), ["COMMIT"])

    def test_with_no_file_held_the_set_is_the_story_s_own_tests_as_for_the_first_story(self):
        self.assertEqual(c2_p9.regression_tests(self.repo, "S1", []), ("tests/test_s1.py",))
        self.assertEqual(c2_p9.regression_tests(self.repo, "S1", ["STORY-02-01", "STORY-02-02"]), ("tests/test_s1.py",))


if __name__ == "__main__":
    unittest.main()
