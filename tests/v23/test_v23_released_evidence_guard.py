"""CODE-AUDIT #52 (b), COMPATIBILITY-MATRIX CT-6: the released-V2 evidence guard (validation/v23/released_evidence_guard.py).

Red-before: closure-evidence/v2/** is outside the V1 guard (tests/v2/test_v1_evidence_guard.py asserts that changes
under v2/ are ignored), so before this guard a committed edit, a deletion or a baseline edit of a released v2 record
passed every check. Throwaway-repo tests: each now FAILs, an addition passes. The live half: the committed baseline
agrees with tag v2.2.0, and HEAD keeps every released blob.

CIGOV-R1 OPEN: the ledger (closure-evidence/v2/cycle2/RELEASE-DECISIONS.json) is a released blob here and append-only
under CT-5, so a seq 13 append FAILs this guard while CT-5 passes. Pinned below as measured; the decision is the
owner's or integrator's (docs/v2.3/amendments/CIGOV-R1.md).
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
LEDGER = "closure-evidence/v2/cycle2/RELEASE-DECISIONS.json"     # the real ledger's path (v2_release_gate.py reads it)
ENTRIES = [{"seq": 1, "id": "A"}, {"seq": 2, "id": "B"}]


def ledger(entries: list[dict], record: str = "ledger") -> str:
    return json.dumps({"record": record, "entries": entries}, indent=1) + "\n"


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
        self.write(LEDGER, ledger(ENTRIES))
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

    def test_cigov_r1_open_a_ct5_append_to_the_ledger_fails_the_guard(self):
        """CIGOV-R1 OPEN (docs/v2.3/amendments/CIGOV-R1.md): a whole-entry append keeps CT-5 (entries[:n] equal, seq
        strictly increasing), yet it changes the ledger's blob, so CT-6 / #52 (b) FAIL it. This pins the measured
        conflict. Only the decided amendment may change this outcome, and never by an exception for the ledger path."""
        self.write(LEDGER, ledger([*ENTRIES, {"seq": 3, "id": "C"}]))
        self.commit("append seq 3")
        head = json.loads((self.d / LEDGER).read_text(encoding="utf-8"))["entries"]
        seqs = [e["seq"] for e in head]
        self.assertEqual((head[:2], seqs), (ENTRIES, sorted(set(seqs))))           # CT-5 holds
        self.assertEqual(self.check(), [f"committed mutation of released evidence ({self.released[:12]}): {LEDGER}"])

    def test_no_ledger_rewrite_passes(self):
        """Whatever CIGOV-R1 decides, these stay FAIL: an entry edited, entries reordered, one deleted, another key
        changed (option (a) of the amendment must keep each of them red)."""
        for name, text in {"entry 1 edited": ledger([{"seq": 1, "id": "X"}, ENTRIES[1]]),
                           "entries reordered": ledger(ENTRIES[::-1]),
                           "an entry deleted": ledger(ENTRIES[:1]),
                           "another key changed": ledger(ENTRIES, record="other")}.items():
            with self.subTest(name):
                self.write(LEDGER, text)
                self.commit(name)
                self.assertEqual(self.check(), [f"committed mutation of released evidence ({self.released[:12]}): "
                                                f"{LEDGER}"])
                self.write(LEDGER, ledger(ENTRIES))
                self.commit("restore")
                self.assertEqual(self.check(), [])


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
