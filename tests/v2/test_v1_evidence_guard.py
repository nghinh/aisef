"""WP-0.4 — the V1 evidence guard.

**Importing this module arms the preventive layer for the whole test process.** `unittest` discovery imports
every test module before it runs any test, so the audit hook is live before the first test executes. It is armed
in `enforce` mode; `AISEF_V1_GUARD=record` is for measurement only.

Every adversarial probe here is zero-risk to real evidence *even if the guard were broken*: writes to existing
protected files open in append mode and write nothing; deletions and renames target protected paths that do not
exist (a working guard raises PermissionError, a broken one FileNotFoundError — distinguishable and harmless);
byte-level mutations are exercised in throwaway git repositories.
"""

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
_NAME = "aisef_v2_v1_evidence_guard"
if _NAME in sys.modules:
    guard = sys.modules[_NAME]
else:
    _s = importlib.util.spec_from_file_location(_NAME, ROOT / "validation" / "v2" / "v1_evidence_guard.py")
    guard = importlib.util.module_from_spec(_s)
    sys.modules[_NAME] = guard
    _s.loader.exec_module(guard)

guard.install(mode=os.environ.get("AISEF_V1_GUARD", "enforce"))

HARDENING = ROOT / "closure-evidence" / "hardening"
EXISTING = HARDENING / "state-model-results.json"
ABSENT = HARDENING / "__v1_guard_probe_never_exists__"


def _base():
    return guard._norm(str(ROOT / guard.PROTECTED_DIR)), guard._norm(str(ROOT / guard.EXCLUDED_DIR))


class Preventive(unittest.TestCase):
    """The in-process layer refuses mutation of protected paths and permits everything else."""

    def setUp(self):
        if guard._armed.get("mode") != "enforce":
            self.skipTest("guard armed in record mode (measurement run)")

    def test_armed_in_enforce_mode(self):
        self.assertEqual(guard._armed.get("mode"), "enforce")

    def test_append_to_existing_protected_file_is_refused(self):
        before = EXISTING.read_bytes()
        with self.assertRaises(PermissionError):
            with open(EXISTING, "ab"):
                pass  # writes nothing even if the guard were broken
        self.assertEqual(EXISTING.read_bytes(), before)

    def test_pathlib_write_to_protected_file_is_refused(self):
        with self.assertRaises(PermissionError):
            ABSENT.write_text("x", encoding="utf-8")
        self.assertFalse(ABSENT.exists())

    def test_create_new_file_in_protected_dir_is_refused(self):
        try:
            with self.assertRaises(PermissionError):
                open(ABSENT, "x").close()
        finally:
            if ABSENT.exists():  # only if the guard failed; the hook itself would refuse os.remove
                subprocess.run(["git", "clean", "-f", "--", str(ABSENT)], cwd=ROOT, check=False)
        self.assertFalse(ABSENT.exists())

    def test_remove_is_refused_before_it_reaches_the_filesystem(self):
        with self.assertRaises(PermissionError):
            os.remove(ABSENT)  # FileNotFoundError here would mean the guard did not intervene

    def test_rename_into_protected_dir_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            src = pathlib.Path(t) / "probe"
            src.write_text("x", encoding="utf-8")
            with self.assertRaises(PermissionError):
                os.replace(src, ABSENT)
            self.assertTrue(src.exists())
        self.assertFalse(ABSENT.exists())

    def test_rmtree_of_protected_dir_is_refused(self):
        with self.assertRaises(PermissionError):
            shutil.rmtree(HARDENING / "__v1_guard_probe_dir_never_exists__")

    def test_reading_protected_evidence_is_permitted(self):
        self.assertTrue(json.loads(EXISTING.read_text(encoding="utf-8")))

    def test_writing_under_v2_is_permitted(self):
        probe = ROOT / "closure-evidence" / "v2" / f"__guard_probe_{os.getpid()}__"
        try:
            probe.write_text("x", encoding="utf-8")
            self.assertTrue(probe.exists())
        finally:
            probe.unlink(missing_ok=True)

    def test_dir_fd_relative_removal_elsewhere_is_not_a_false_positive(self):
        # Regression: shutil.rmtree removes a throwaway repo's own `closure-evidence` with
        # os.rmdir("closure-evidence", dir_fd=...). That path is relative to dir_fd, not the cwd.
        t = tempfile.TemporaryDirectory()
        (pathlib.Path(t.name) / "closure-evidence" / "hardening").mkdir(parents=True)
        (pathlib.Path(t.name) / "closure-evidence" / "hardening" / "x.json").write_text("{}", encoding="utf-8")
        t.cleanup()  # must not raise
        self.assertFalse(pathlib.Path(t.name).exists())

    @unittest.skipUnless(sys.platform.startswith("linux") or sys.platform == "darwin", "dir_fd resolution")
    def test_dir_fd_resolution_distinguishes_repo_from_elsewhere(self):
        base, excluded = _base()
        with tempfile.TemporaryDirectory() as t:
            fd = os.open(t, os.O_RDONLY)
            try:
                self.assertFalse(guard._is_protected("closure-evidence", base, excluded, fd))
            finally:
                os.close(fd)
        fd = os.open(ROOT, os.O_RDONLY)
        try:
            self.assertTrue(guard._is_protected("closure-evidence", base, excluded, fd))
            self.assertFalse(guard._is_protected("closure-evidence/v2", base, excluded, fd))
        finally:
            os.close(fd)


def _git(root, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.t", *args], cwd=root,
                          capture_output=True, text=True, check=True).stdout.strip()


class Detective(unittest.TestCase):
    """The git-object layer fails closed on every kind of mutation, including of the baseline itself."""

    def test_repository_matches_the_baseline(self):
        self.assertEqual(guard.check(), [])

    def test_baseline_records_provenance(self):
        b = json.loads((ROOT / guard.BASELINE_REL).read_text(encoding="utf-8"))
        self.assertEqual(b["source_revision"], guard.V1_CLOSE)
        self.assertEqual(b["excluded"], ["closure-evidence/v2/"])
        self.assertEqual(b["file_count"], len(b["files"]))
        self.assertTrue(all(len(f["sha256"]) == 64 and f["blob"] and f["path"] for f in b["files"]))
        self.assertEqual(b["enforcement"]["overall_grade"], "DETECTIVE")

    def _repo(self, t):
        root = pathlib.Path(t)
        _git(root, "init", "-q")
        (root / "closure-evidence" / "hardening").mkdir(parents=True)
        (root / "closure-evidence" / "v2").mkdir()
        (root / "closure-evidence" / "hardening" / "a.json").write_text('{"a": 1}\n', encoding="utf-8")
        (root / "closure-evidence" / "hardening" / "b.json").write_text('{"b": 2}\n', encoding="utf-8")
        _git(root, "add", ".")
        _git(root, "commit", "-q", "-m", "close")
        close = _git(root, "rev-parse", "HEAD")
        b = guard.build_baseline(root, close)
        (root / guard.BASELINE_REL).write_text(json.dumps(b), encoding="utf-8")
        _git(root, "add", ".")
        _git(root, "commit", "-q", "-m", "baseline")
        return root, close

    def test_clean_throwaway_repo_passes(self):
        with tempfile.TemporaryDirectory() as t:
            root, close = self._repo(t)
            self.assertEqual(guard.check(root, source=close), [])

    def test_working_tree_mutation_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root, close = self._repo(t)
            (root / "closure-evidence/hardening/a.json").write_text('{"a": 9}\n', encoding="utf-8")
            self.assertTrue(any("working-tree change" in p for p in guard.check(root, source=close)))

    def test_untracked_addition_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root, close = self._repo(t)
            (root / "closure-evidence/hardening/new.json").write_text("{}", encoding="utf-8")
            self.assertTrue(any("working-tree change" in p for p in guard.check(root, source=close)))

    def test_committed_mutation_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root, close = self._repo(t)
            (root / "closure-evidence/hardening/a.json").write_text('{"a": 9}\n', encoding="utf-8")
            _git(root, "commit", "-q", "-am", "mutate")
            self.assertTrue(any("committed mutation" in p for p in guard.check(root, source=close)))

    def test_committed_deletion_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root, close = self._repo(t)
            _git(root, "rm", "-q", "closure-evidence/hardening/b.json")
            _git(root, "commit", "-q", "-m", "delete")
            self.assertTrue(any("committed deletion" in p for p in guard.check(root, source=close)))

    def test_editing_the_baseline_to_bless_a_mutation_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root, close = self._repo(t)
            (root / "closure-evidence/hardening/a.json").write_text('{"a": 9}\n', encoding="utf-8")
            _git(root, "commit", "-q", "-am", "mutate")
            b = json.loads((root / guard.BASELINE_REL).read_text(encoding="utf-8"))
            forged = _git(root, "rev-parse", "HEAD:closure-evidence/hardening/a.json")
            for f in b["files"]:
                if f["path"].endswith("a.json"):
                    f["blob"] = forged
            (root / guard.BASELINE_REL).write_text(json.dumps(b), encoding="utf-8")
            problems = guard.check(root, source=close)
            self.assertTrue(any("does not agree with the V1 closure revision" in p for p in problems), problems)

    def test_changes_under_v2_are_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            root, close = self._repo(t)
            (root / "closure-evidence/v2/anything.json").write_text("{}", encoding="utf-8")
            self.assertEqual(guard.check(root, source=close), [])

    def test_baseline_refuses_a_dirty_tree(self):
        with tempfile.TemporaryDirectory() as t:
            root, close = self._repo(t)
            (root / "closure-evidence/hardening/a.json").write_text('{"a": 9}\n', encoding="utf-8")
            with self.assertRaises(RuntimeError):
                guard.build_baseline(root, close)


if __name__ == "__main__":
    unittest.main()
