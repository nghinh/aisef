"""Release identity is the product's, not the repository HEAD's (V1-A..V1-H).

The defect this file was written against — measured on this repository
2026-09-15, D-022: after `v1.7.1` was published and G1 read PASSED, a commit
that only synced public documentation (`8b3eada`) moved HEAD past the release
commit, and G1.0 went FAILED — "HEAD is 0e68b96, closure targets 5c5ba52".
Nothing that ships in the wheel had changed. Recording post-release assurance
evidence (an external-validation report, a doc sync, a closure record) was
enough to invalidate the release it was evidence *for*, so the only way to make
G1 green again was another release — whose own evidence would land in a later
commit and invalidate it in turn. A fixed-point loop with no fixed point.

Root cause: release identity was conflated with repository HEAD, and the
exception (`_only_bookkeeping_changed`) was a filename allowlist — one
directory and one file — rather than a statement about *what the product is*.

The model these tests pin instead (`aisef/control/planes.py`): two planes
linked by explicit identities.

* **Product plane** — everything that determines the published artifact:
  runtime source, package data, build configuration. Identified by
  `release_source_sha` (the tag's commit), a content digest over the product
  inputs, and the artifact digests on PyPI.
* **Assurance plane** — tests, evidence, approvals, reports, closure records.
  Identified by the commit that carries them (`closure_record_sha`), which
  is allowed to differ from `release_source_sha` after publication.

A later commit may coexist with release R when the product digest at HEAD
equals the product digest at R. Equivalence is decided by classification and
digest, never by "the diff looks harmless"; a path no rule classifies is
`UNRESOLVED`, which blocks and names the path.

Red-first: the `TestV1AFixedPoint` class was run against the old probe before
the model existed — 2 of 5 red (the report commit and the doc-sync commit both
invalidated the release), the negative control green.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import closure as CL  # noqa: E402
from aisef.control import planes  # noqa: E402
from aisef.control.gate import Outcome  # noqa: E402
from tests.test_closure import (  # noqa: E402
    PYPROJECT, Repo, WHEEL_SHA, crit, git, spec_of, write_manifest,
)


def _release_repo(*, tag: str = "v9.9.9", extra_crit: dict | None = None) -> Repo:
    """A checkout that has just published `tag`: product files, a release
    record naming the tag, the closure target frozen at the tag commit, and
    the release manifest recorded from the tag's tree."""
    c = crit("G1.0", "aisef.control.closure:probe_closure_target",
             evidence="closure-evidence/release.json")
    crits = [c] + ([extra_crit] if extra_crit else [])
    repo = Repo(spec_of(*crits), commit=False)
    repo.write("aisef/__init__.py", "__version__ = '9.9.9'\n")
    repo.write("aisef/kit/prompts/story.md", "prompt v1\n")
    repo.write("pyproject.toml", PYPROJECT)
    repo.write("README.md", "# aisef\n\n## Install\n\npip install aisef\n")
    repo.write("docs/USAGE-GUIDE.md", "aisef doctor\n")
    repo.write("tests/test_x.py", "def test_x():\n    assert True\n")
    git(repo.root, "init")
    git(repo.root, "config", "user.name", "Test")
    git(repo.root, "config", "user.email", "t@t.t")
    git(repo.root, "add", ".")
    git(repo.root, "commit", "-m", "release candidate")
    git(repo.root, "tag", tag)
    repo.write_json("closure-evidence/release.json", {"version": "9.9.9", "tag": tag})
    repo.spec["closure_target_sha"] = repo.head
    repo.write_json(CL.CRITERIA_PATH, repo.spec)
    write_manifest(repo, tag=tag)
    git(repo.root, "add", ".")
    git(repo.root, "commit", "-m", "record the release")
    return repo


def _commit(repo: Repo, rel: str, text: str, msg: str = "post-release") -> None:
    repo.write(rel, text)
    git(repo.root, "add", ".")
    git(repo.root, "commit", "-m", msg)


def _g1(repo: Repo) -> CL.Probed:
    repo.spec = CL.load_spec(repo.root)
    return CL.probe_closure_target(repo.ctx({"evidence": "closure-evidence/release.json"}))


def _rules(repo: Repo):
    return planes.rules_from(CL.load_spec(repo.root))


class TestV1AFixedPoint(unittest.TestCase):
    """Phase V1-A — the deterministic regression for the release/closure loop.

    1. release R is published and G1 passes;
    2. only post-release assurance evidence is added;
    3. product/package inputs stay byte-identical;
    4. recording that evidence must NOT invalidate R;
    5. closure may reference a later evidence commit while validating R.
    """

    def test_release_passes_at_the_tag(self):
        repo = _release_repo()
        self.addCleanup(repo.close)
        p = _g1(repo)
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)

    def test_an_external_validation_report_does_not_invalidate_the_release(self):
        repo = _release_repo()
        self.addCleanup(repo.close)
        before = git(repo.root, "rev-parse", f"{repo.spec['closure_target_sha']}:aisef").stdout
        _commit(repo, "docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md",
                "# report\n\nProduct version validated: 9.9.9\n", "docs(g6): record")
        after = git(repo.root, "rev-parse", "HEAD:aisef").stdout
        self.assertEqual(before, after, "product tree must be byte-identical")
        p = _g1(repo)
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)

    def test_a_documentation_sync_does_not_invalidate_the_release(self):
        """The exact instance measured on this repository: commit 8b3eada."""
        repo = _release_repo()
        self.addCleanup(repo.close)
        _commit(repo, "docs/USAGE-GUIDE.md", "aisef doctor\naisef plan\n", "docs: sync to 9.9.9")
        p = _g1(repo)
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)

    def test_closure_may_reference_a_later_evidence_commit(self):
        repo = _release_repo()
        self.addCleanup(repo.close)
        _commit(repo, "closure-evidence/closure-state.json", '{"approval": {}}\n', "closure record")
        self.assertNotEqual(repo.head, repo.spec["closure_target_sha"])
        p = _g1(repo)
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)

    def test_a_runtime_change_still_invalidates_the_release(self):
        """Negative control — the loosening must not hide a product change."""
        repo = _release_repo()
        self.addCleanup(repo.close)
        _commit(repo, "aisef/__init__.py", "__version__ = '9.9.10'\n", "fix")
        self.assertTrue(_g1(repo).outcome.blocks)


class TestV1GRegressionMatrix(unittest.TestCase):
    """Phase V1-G — the eleven behaviours the model must exhibit, one each."""

    def setUp(self):
        self.repo = _release_repo()
        self.addCleanup(self.repo.close)

    # 1. runtime source change → release stale
    def test_01_runtime_source_change_makes_the_release_stale(self):
        _commit(self.repo, "aisef/__init__.py", "__version__ = '9.9.10'\n")
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("runtime_source", p.detail)
        self.assertIn("new release", p.detail)

    # 2. package data change → release stale
    def test_02_package_data_change_makes_the_release_stale(self):
        _commit(self.repo, "aisef/kit/prompts/story.md", "prompt v2\n")
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("package_data", p.detail)

    # 3. external-validation report added → release still valid
    def test_03_external_validation_report_keeps_the_release_valid(self):
        _commit(self.repo, "docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md", "# report\n")
        self.assertIs(_g1(self.repo).outcome, Outcome.PASSED)

    # 4. closure evidence added → release still valid
    def test_04_closure_evidence_keeps_the_release_valid(self):
        _commit(self.repo, "closure-evidence/suite.json", '{"passed": 1}\n')
        _commit(self.repo, "closure-evidence/closure-report.json", '{"closable": false}\n')
        self.assertIs(_g1(self.repo).outcome, Outcome.PASSED)

    # 5. documentation change → per the doc/claim policy: G1 valid, G6's clock decides
    def test_05_documentation_change_is_not_a_product_change(self):
        _commit(self.repo, "README.md", "# aisef\n\n## Install\n\npip install aisef --upgrade\n")
        _commit(self.repo, "docs/USAGE-GUIDE.md", "aisef doctor\naisef qa\n")
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)
        ch = planes.changes(self.repo.root, self.repo.spec["closure_target_sha"], "HEAD", _rules(self.repo))
        self.assertEqual(ch.product, [])
        self.assertEqual(ch.staling, [])
        self.assertEqual(sorted(ch.by_class[planes.DOCUMENTATION]), ["README.md", "docs/USAGE-GUIDE.md"])

    # 6. a validation of release A cannot satisfy G6 for release B — see
    #    tests/test_closure.py::TestG6::test_a_record_for_another_release_cannot_satisfy_this_one;
    #    here the manifest side: a manifest for another source cannot pass G1.0
    def test_06_a_manifest_for_another_release_cannot_pass(self):
        write_manifest(self.repo, release_source_sha="0" * 40)
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("another release", p.detail)

    # 7. modifying historical evidence invalidates its digest
    def test_07_editing_the_manifest_after_recording_is_caught(self):
        write_manifest(self.repo)
        m = CL.Ctx(root=self.repo.root, spec=CL.load_spec(self.repo.root)).read_json(
            "closure-evidence/releases/9.9.9.json")
        m["product"]["digest"] = "f" * 64
        self.repo.write_json("closure-evidence/releases/9.9.9.json", m)
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("re-record", p.detail)

    def test_07b_an_approval_goes_stale_when_recorded_evidence_is_edited(self):
        """The signed digest set binds the approval to the manifest's bytes."""
        report = CL.evaluate(self.repo.root)
        state = {"approval": {"by": "owner", "at": "now", "contract_sha256": report.contract["sha256"],
                              "digests": {r.id: r.digest for r in report.results}}}
        self.assertEqual(CL.approval_state(state, report)["status"], "approved")
        m = CL.Ctx(root=self.repo.root, spec=CL.load_spec(self.repo.root)).read_json(
            "closure-evidence/releases/9.9.9.json")
        m["recorded_at"] = "rewritten"
        self.repo.write_json("closure-evidence/releases/9.9.9.json", m)
        again = CL.evaluate(self.repo.root)
        self.assertEqual(CL.approval_state(state, again)["status"], "stale")

    # 8. changing instructions after execution cannot relabel an old G6 — see
    #    tests/test_closure.py::TestG6::test_instructions_edited_after_the_run_cannot_relabel_the_record;
    #    here: the bundle digest is byte-exact, a one-byte edit moves it
    def test_08_bundle_digest_is_byte_exact(self):
        d = self.repo.root / "closure-evidence/external-validation/9.9.9"
        self.repo.write("closure-evidence/external-validation/9.9.9/INSTRUCTIONS.md", "pip install aisef==9.9.9\n")
        before, names = planes.bundle_digest(d, exclude=("REPORT.md",))
        self.assertEqual(names, ["INSTRUCTIONS.md"])
        self.repo.write("closure-evidence/external-validation/9.9.9/REPORT.md", "the participant's output\n")
        self.assertEqual(planes.bundle_digest(d, exclude=("REPORT.md",))[0], before,
                         "the report is the participant's output, not part of the instructions")
        self.repo.write("closure-evidence/external-validation/9.9.9/INSTRUCTIONS.md", "pip install aisef==9.9.9 \n")
        self.assertNotEqual(planes.bundle_digest(d, exclude=("REPORT.md",))[0], before)

    # 9. artifact digest mismatch → G1 fails regardless of HEAD
    def test_09_artifact_digest_mismatch_fails_even_with_head_at_the_tag(self):
        write_manifest(self.repo, observed={
            "wheel": {"sha256": "x" * 64, "mismatched": [], "unmapped": []},
            "sdist": {"sha256": "s" * 64, "mismatched": [], "unmapped": []}})
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("not the one recorded", p.detail)

    def test_09b_a_member_that_differs_from_the_source_fails(self):
        write_manifest(self.repo, observed={
            "wheel": {"sha256": WHEEL_SHA, "mismatched": ["aisef/__init__.py"], "unmapped": []},
            "sdist": {"sha256": "s" * 64, "mismatched": [], "unmapped": []}})
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("not built from the release source", p.detail)

    def test_09c_an_artifact_never_observed_is_unrunnable_not_assumed(self):
        write_manifest(self.repo, observed={})
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("asserted, not observed", p.detail)

    # 10. same artifacts + evidence-only commit → G1 valid (the fixed-point step)
    def test_10_same_artifacts_and_an_evidence_only_commit_pass(self):
        _commit(self.repo, "closure-evidence/onboarding-digest.json", '{"digest": "abc"}\n')
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)
        self.assertIn("carried unchanged by HEAD", p.detail)

    # 11. fixed-point convergence — the permanent meta-assurance invariant
    def test_11_release_validate_record_close_converges_without_another_release(self):
        """release R → validate R → record → close R must converge: after every
        assurance-plane commit the release still describes HEAD, and the
        closure record's commit is allowed to differ from `release_source_sha`."""
        r = self.repo.spec["closure_target_sha"]
        steps = [
            ("closure-evidence/external-validation/9.9.9/INSTRUCTIONS.md", "install 9.9.9\n", "bundle"),
            ("closure-evidence/external-validation/9.9.9/REPORT.md", "validated 9.9.9\n", "validate R"),
            ("closure-evidence/closure-report.json", '{"closable": true}\n', "record"),
            ("closure-evidence/closure-state.json", '{"approval": {"by": "owner"}}\n', "close R"),
            ("docs/BASELINE-v1-CLOSED.md", "closure_record_sha: later\n", "baseline"),
        ]
        for rel, text, msg in steps:
            _commit(self.repo, rel, text, msg)
            p = _g1(self.repo)
            self.assertIs(p.outcome, Outcome.PASSED, f"after '{msg}': {p.detail}")
        closure_record_sha = self.repo.head
        self.assertNotEqual(closure_record_sha, r)
        ident_r = planes.identity(self.repo.root, r, _rules(self.repo))
        ident_h = planes.identity(self.repo.root, closure_record_sha, _rules(self.repo))
        self.assertEqual(ident_r.digest, ident_h.digest)
        # …and the moment the product moves, convergence correctly stops.
        _commit(self.repo, "pyproject.toml", PYPROJECT.replace("9.9.9", "9.9.10"), "bump")
        self.assertIs(_g1(self.repo).outcome, Outcome.UNRUNNABLE,
                      "a bumped version names a manifest that does not exist yet")

    # UNRESOLVED is never harmless
    def test_12_an_unclassified_path_blocks_and_is_named(self):
        _commit(self.repo, "mystery/thing.bin", "?\n")
        p = _g1(self.repo)
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("mystery/thing.bin", p.detail)
        self.assertIn("planes", p.detail)


class TestCommitBoundEvidenceStaleness(unittest.TestCase):
    """`bound_to: commit` evidence (suite, lint, selfcheck) is stale by
    dependency, not by HEAD movement."""

    def setUp(self):
        c = crit("G2.1", "aisef.control.closure:probe_suite_green",
                 evidence="closure-evidence/suite.json")
        self.repo = _release_repo(extra_crit=c)
        self.addCleanup(self.repo.close)
        self.at = self.repo.head
        self.repo.write_json("closure-evidence/suite.json",
                             {"commit": self.at, "exit": 0, "passed": 10, "failed": 0,
                              "errors": 0, "skipped": 0, "tree": "main"})
        git(self.repo.root, "add", "."); git(self.repo.root, "commit", "-m", "record suite")

    def probe(self):
        self.repo.spec = CL.load_spec(self.repo.root)
        return CL.probe_suite_green(self.repo.ctx({"evidence": "closure-evidence/suite.json"}))

    def test_evidence_and_docs_commits_keep_it_fresh(self):
        _commit(self.repo, "docs/USAGE-GUIDE.md", "aisef doctor\naisef plan\n")
        _commit(self.repo, "closure-evidence/lint.json", '{"exit": 0}\n')
        self.assertIs(self.probe().outcome, Outcome.PASSED)

    def test_a_test_change_stales_it(self):
        _commit(self.repo, "tests/test_y.py", "def test_y():\n    assert True\n")
        p = self.probe()
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("tests/test_y.py", p.detail)
        self.assertIn("re-record", p.detail)

    def test_a_product_change_stales_it(self):
        _commit(self.repo, "aisef/__init__.py", "x = 2\n")
        self.assertIs(self.probe().outcome, Outcome.UNRUNNABLE)

    def test_an_unclassified_change_is_unrunnable_and_named(self):
        _commit(self.repo, "mystery.txt", "?\n")
        p = self.probe()
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("mystery.txt", p.detail)

    def test_no_rules_means_cannot_tell(self):
        spec = CL.load_spec(self.repo.root)
        spec.pop("planes")
        self.repo.write_json(CL.CRITERIA_PATH, spec)
        _commit(self.repo, "docs/USAGE-GUIDE.md", "aisef doctor\naisef plan\n")
        p = self.probe()
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("planes", p.detail)


class TestPlanes(unittest.TestCase):
    """The classifier and the identity digest, on their own."""

    RULES = planes.rules_from(spec_of())

    def test_first_match_wins(self):
        self.assertEqual(planes.classify("aisef/kit/prompts/x.md", self.RULES).part, "package_data")
        self.assertEqual(planes.classify("aisef/x.py", self.RULES).part, "runtime_source")

    def test_unmatched_is_unresolved_and_no_rule_may_declare_it(self):
        self.assertEqual(planes.class_of("spike/x", self.RULES), planes.UNRESOLVED)
        with self.assertRaises(ValueError):
            planes.rules_from({"planes": {"rules": [{"class": "UNRESOLVED", "match": "*"}]}})
        with self.assertRaises(ValueError):
            planes.rules_from({"planes": {"rules": [{"class": "PRODUCT_AFFECTING"}]}})

    def test_no_planes_block_means_no_rules(self):
        self.assertEqual(planes.rules_from({}), ())

    def test_identity_ignores_untracked_and_assurance_files(self):
        repo = _release_repo()
        self.addCleanup(repo.close)
        rules = _rules(repo)
        base = planes.identity(repo.root, "HEAD", rules)
        self.assertTrue(base.ok)
        self.assertEqual(sorted(base.parts), ["build_config", "package_data", "runtime_source"])
        _commit(repo, "tests/test_z.py", "def test_z():\n    assert True\n")
        self.assertEqual(planes.identity(repo.root, "HEAD", rules).digest, base.digest)
        repo.write("aisef/untracked.py", "never committed\n")
        self.assertEqual(planes.identity(repo.root, "HEAD", rules).digest, base.digest)
        (repo.root / "aisef/untracked.py").unlink()
        _commit(repo, "aisef/kit/prompts/story.md", "prompt v2\n")
        moved = planes.identity(repo.root, "HEAD", rules)
        self.assertNotEqual(moved.digest, base.digest)
        self.assertNotEqual(moved.parts["package_data"], base.parts["package_data"])
        self.assertEqual(moved.parts["runtime_source"], base.parts["runtime_source"])

    def test_identity_of_an_unknown_revision_is_empty_not_a_digest(self):
        repo = _release_repo()
        self.addCleanup(repo.close)
        self.assertFalse(planes.identity(repo.root, "0" * 40, _rules(repo)).ok)

    def test_changes_are_classified_and_unreadable_diffs_are_not_empty(self):
        repo = _release_repo()
        self.addCleanup(repo.close)
        a = repo.head
        _commit(repo, "docs/x.md", "x\n")
        _commit(repo, "aisef/y.py", "y\n")
        ch = planes.changes(repo.root, a, "HEAD", _rules(repo))
        self.assertEqual(ch.product, ["aisef/y.py"])
        self.assertEqual(ch.staling, ["aisef/y.py"])
        self.assertEqual(ch.by_class[planes.DOCUMENTATION], ["docs/x.md"])
        bad = planes.changes(repo.root, "0" * 40, "HEAD", _rules(repo))
        self.assertFalse(bad.readable)
        self.assertEqual(bad.total, 0)

    def test_every_tracked_path_of_this_repository_is_classified(self):
        """The shipped rules must cover the shipped tree — an unclassified path
        would block closure, so it is caught here first."""
        rules = planes.rules_from(CL.load_spec(ROOT))
        ident = planes.identity(ROOT, "HEAD", rules)
        self.assertTrue(ident.digest)
        self.assertEqual(ident.unresolved, [])
        self.assertGreater(ident.files, 50)
        self.assertEqual(sorted(ident.parts), ["build_config", "package_data", "runtime_source"])

    def test_the_shipped_rules_put_the_runtime_and_the_wheel_data_in_the_product(self):
        rules = planes.rules_from(CL.load_spec(ROOT))
        self.assertEqual(planes.class_of("aisef/control/closure.py", rules), planes.PRODUCT)
        self.assertEqual(planes.class_of("aisef/kit/prompts/story-implement.md", rules), planes.PRODUCT)
        self.assertEqual(planes.class_of("pyproject.toml", rules), planes.PRODUCT)
        self.assertEqual(planes.class_of("tests/test_closure.py", rules), planes.ASSURANCE)
        self.assertEqual(planes.class_of("closure-evidence/suite.json", rules), planes.EVIDENCE)
        self.assertEqual(planes.class_of("docs/closure-gate.json", rules), planes.EVIDENCE)
        self.assertEqual(planes.class_of("docs/USAGE-GUIDE.md", rules), planes.DOCUMENTATION)
        self.assertEqual(planes.class_of("landingpage/index.html", rules), planes.DOCUMENTATION)


class TestTheDefectInstance(unittest.TestCase):
    """The measured instance, replayed on this repository's own history: the
    doc-sync commit `8b3eada` carried the same product as `v1.7.1`."""

    def test_the_doc_sync_commit_carried_the_released_product(self):
        rules = planes.rules_from(CL.load_spec(ROOT))
        tag = git(ROOT, "rev-list", "-n", "1", "v1.7.1").stdout.strip()
        if not tag:
            self.skipTest("v1.7.1 is not in this checkout")
        released = planes.identity(ROOT, tag, rules)
        synced = planes.identity(ROOT, "8b3eada", rules)
        if not synced.digest:
            self.skipTest("8b3eada is not in this checkout")
        self.assertEqual(released.digest, synced.digest)
        ch = planes.changes(ROOT, tag, "8b3eada", rules)
        self.assertEqual(ch.product, [])
        self.assertEqual(ch.unresolved, [])


if __name__ == "__main__":
    unittest.main()
