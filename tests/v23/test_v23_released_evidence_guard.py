"""CODE-AUDIT #52 (b), COMPATIBILITY-MATRIX CT-6: the released-V2 evidence guard (validation/v23/released_evidence_guard.py).

Red-before: closure-evidence/v2/** is outside the V1 guard (tests/v2/test_v1_evidence_guard.py asserts that changes
under v2/ are ignored), so before this guard a committed edit, a deletion or a baseline edit of a released v2 record
passed every check. Throwaway-repo tests: each now FAILs, an addition passes. The live half: the committed baseline
agrees with tag v2.2.0, and HEAD keeps every released blob.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23 import released_evidence_guard as RE  # noqa: E402

BASE = "docs/released-baseline.json"
QUIET_GIT = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


class ThrowawayRepo(unittest.TestCase):
    """A repo whose first commit plays tag v2.2.0: two released records, one V1 file outside the scope."""

    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = pathlib.Path(t.name)
        env = mock.patch.dict(os.environ, QUIET_GIT)
        env.start()
        self.addCleanup(env.stop)
        self.git("init", "-q")
        self.write("closure-evidence/v2/release/R.json", "{}\n")
        self.write("closure-evidence/v2/v2.1/MUTATION.json", "[]\n")
        self.write("closure-evidence/hardening/v1.json", "{}\n")
        self.released = self.commit("released")
        (self.d / "docs").mkdir()
        (self.d / BASE).write_text(json.dumps(RE.build_baseline(self.d, self.released)), encoding="utf-8")
        self.commit("baseline")

    def git(self, *a: str) -> str:
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                              cwd=self.d, check=True, capture_output=True, encoding="utf-8").stdout

    def write(self, rel: str, text: str) -> None:
        (self.d / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.d / rel).write_text(text, encoding="utf-8")

    def commit(self, msg: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD").strip()

    def check(self, base: str | None = None) -> list[str]:
        return RE.check(self.d, BASE, self.released, base)

    def test_unchanged_passes_and_an_addition_is_allowed(self):
        self.assertEqual(self.check(), [])
        self.write("closure-evidence/v2/v2.3/NEW.json", "{}\n")
        self.commit("add")
        self.assertEqual(self.check(), [])

    def test_a_committed_edit_fails(self):
        self.write("closure-evidence/v2/release/R.json", '{"edited": true}\n')
        self.commit("edit")
        self.assertEqual(self.check(), [f"committed mutation of released evidence ({self.released[:12]}): "
                                        "closure-evidence/v2/release/R.json"])

    def test_a_committed_deletion_fails(self):
        self.git("rm", "-q", "closure-evidence/v2/v2.1/MUTATION.json")
        self.commit("delete")
        self.assertEqual(self.check(), [f"committed deletion of released evidence ({self.released[:12]}): "
                                        "closure-evidence/v2/v2.1/MUTATION.json"])

    def test_a_baseline_edit_fails(self):
        for key, value in (("files_digest_sha256", "0" * 64), ("file_count", 1), ("source_revision", "f" * 40)):
            with self.subTest(key):
                doc = json.loads((self.d / BASE).read_text(encoding="utf-8"))
                (self.d / BASE).write_text(json.dumps({**doc, key: value}), encoding="utf-8")
                self.commit(f"baseline {key}")
                self.assertEqual(len(self.check()), 1)
                self.assertIn("the baseline itself was altered", self.check()[0])
                (self.d / BASE).write_text(json.dumps(doc), encoding="utf-8")
                self.commit("restore")
        (self.d / BASE).unlink()
        self.assertIn("missing or unreadable", self.check()[0])

    def test_a_working_tree_change_fails_and_v1_files_are_out_of_scope(self):
        self.write("closure-evidence/hardening/v1.json", '{"v1": "the V1 guard\'s"}\n')
        self.assertEqual(self.check(), [])
        self.write("closure-evidence/v2/release/R.json", '{"rewritten": true}\n')
        self.assertEqual(self.check(), ["working-tree change to released evidence:  M closure-evidence/v2/release/R.json"])
        self.git("checkout", "--", "closure-evidence/v2/release/R.json")
        self.git("mv", "closure-evidence/v2/v2.1/MUTATION.json", "closure-evidence/v2/v2.1/MOVED.json")
        self.assertEqual(self.check(), ["working-tree change to released evidence: R  closure-evidence/v2/v2.1/MUTATION.json"])

    def test_the_released_revision_must_be_available(self):
        found = RE.check(self.d, BASE, "e" * 40, None)
        self.assertEqual(len(found), 1)
        self.assertIn("is not available", found[0])

    def test_the_branch_base_pin_protects_records_added_after_the_release(self):
        """CT-6: a record added after the tag is protected from the branch base on (an edit of it fails)."""
        self.write("closure-evidence/v2/cycle2/AUDIT.json", "{}\n")
        branch_base = self.commit("post-release record")
        self.assertEqual(self.check(branch_base), [])
        self.write("closure-evidence/v2/cycle2/AUDIT.json", '{"edited": true}\n')
        self.commit("edit it")
        self.assertEqual(self.check(), [])                     # the tag pin alone does not cover it
        self.assertEqual(self.check(branch_base), [f"committed mutation of released evidence ({branch_base[:12]}): "
                                                   "closure-evidence/v2/cycle2/AUDIT.json"])


class LiveRepository(unittest.TestCase):
    """The committed baseline is tag v2.2.0's listing, and HEAD keeps every released blob (committed state only: the
    working tree after the suite is the CI step's)."""

    def test_the_committed_baseline_is_the_tag_s_listing(self):
        b = json.loads((ROOT / RE.BASELINE_REL).read_text(encoding="utf-8"))
        at = RE.entries(RE.RELEASED)
        self.assertEqual(subprocess.run(["git", "-C", str(ROOT), "rev-parse", "v2.2.0^{commit}"], capture_output=True,
                                        encoding="utf-8", check=True).stdout.strip(), RE.RELEASED)
        self.assertEqual((b["source_revision"], b["file_count"], b["files_digest_sha256"]),
                         (RE.RELEASED, len(at), RE.digest(at)))
        self.assertEqual(b["file_count"], 6339)
        self.assertEqual(b, RE.build_baseline(ROOT))

    def test_head_keeps_every_released_blob(self):
        self.assertEqual(RE.committed_changes(RE.RELEASED), [])
        self.assertEqual(RE.committed_changes(RE.BRANCH_BASE), [])


if __name__ == "__main__":
    unittest.main()
