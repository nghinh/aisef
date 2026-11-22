"""CODE-AUDIT #52 (b), COMPATIBILITY-MATRIX CT-6: the released-V2 evidence guard (validation/v23/released_evidence_guard.py).

Red-before: closure-evidence/v2/** is outside the V1 guard (tests/v2/test_v1_evidence_guard.py asserts that changes
under v2/ are ignored), so before this guard a committed edit, a deletion or a baseline edit of a released v2 record
passed every check. Throwaway-repo tests: each now FAILs, an addition passes. The live half: the committed baseline
agrees with tag v2.2.0, and HEAD keeps every released blob.

CIGOV-R1 DECIDED (docs/v2.3/amendments/CIGOV-R1.md, option (a), byte-prefix variant, 2026-11-22): the ledger
(closure-evidence/v2/cycle2/RELEASE-DECISIONS.json) alone is checked by the typed append-only rule — a whole-entry
append passes, while an edit, reorder, deletion, re-indentation, top-level change or non-monotonic seq stays red.
Red-before: the superseded pin `test_cigov_r1_open_a_ct5_append_to_the_ledger_fails_the_guard` (measured at 57f9d68e
and in every CI run up to it) showed the append failing the old blob-identity rule while CT-5 passed.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
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

    def test_cigov_r1_decided_an_append_only_growth_of_the_ledger_passes(self):
        """CIGOV-R1 DECIDED, option (a) byte-prefix (green-after; the red-before is the superseded pin named in the
        module docstring): a whole-entry append keeps CT-5 AND passes CT-6 / #52 (b) — uncommitted, committed, twice
        over, with a seq gap, and against a later branch base. Never by an exception: the rule still checks the path."""
        self.write(LEDGER, ledger([*ENTRIES, {"seq": 3, "id": "C"}]))
        self.assertEqual(self.check(), [])                                          # working-tree append
        appended = self.commit("append seq 3")
        self.assertEqual(self.check(), [])                                          # committed append
        self.write(LEDGER, ledger([*ENTRIES, {"seq": 3, "id": "C"}, {"seq": 5, "id": "D"}]))
        self.commit("append seq 5")
        self.assertEqual(self.check(), [])                                          # grown again; gap in seq is fine
        self.assertEqual(self.check(appended), [])                                  # a base that already holds seq 3

    def test_no_ledger_rewrite_passes(self):
        """The red set every CIGOV-R1 outcome must keep (the amendment's option (a) list): an entry edited, entries
        reordered, one deleted, another top-level key changed, the old entries re-indented (byte-prefix variant), a
        non-integer / boolean / non-increasing seq, a non-object entry — uncommitted and committed alike."""
        reindented = json.dumps({"record": "ledger", "entries": ENTRIES}, indent=2) + "\n"
        nonobject = json.dumps({"record": "ledger", "entries": [*ENTRIES, 7]}, indent=1) + "\n"
        for name, text in {"entry 1 edited": ledger([{"seq": 1, "id": "X"}, ENTRIES[1]]),
                           "entries reordered": ledger(ENTRIES[::-1]),
                           "an entry deleted": ledger(ENTRIES[:1]),
                           "another key changed": ledger(ENTRIES, record="other"),
                           "old entries re-indented": reindented,
                           "a non-integer seq appended": ledger([*ENTRIES, {"seq": "3", "id": "C"}]),
                           "a boolean seq appended": ledger([*ENTRIES, {"seq": True, "id": "C"}]),
                           "a non-increasing seq appended": ledger([*ENTRIES, {"seq": 2, "id": "C"}]),
                           "a repeated seq appended": ledger([*ENTRIES, {"seq": 2, "id": "B"}]),
                           "a non-object entry appended": nonobject,
                           "not JSON at all": "}{not json\n"}.items():
            with self.subTest(name + ", working tree"):
                self.write(LEDGER, text)
                self.assertTrue(any("ledger append-only rule (working tree" in p for p in self.check()), self.check())
            with self.subTest(name + ", committed"):
                self.commit(name)
                self.assertTrue(any("ledger append-only rule (HEAD" in p for p in self.check()), self.check())
                self.write(LEDGER, ledger(ENTRIES))
                self.commit("restore")
                self.assertEqual(self.check(), [])

    def test_a_duplicate_json_key_smuggle_stays_red(self):
        """Adversarial finding (2026-11-22): json.loads alone is last-key-wins, so a file whose BYTES hold a forged
        entry displaced by a second `entries` key parses as the unchanged ledger and passed every typed check. The
        duplicate-key-rejecting parse keeps it red — at the top level and at entry depth, uncommitted and committed."""
        old = ledger(ENTRIES)
        m = re.search(r"\s*\]\s*\}\s*$", old)
        smuggle = old[: m.start()] + ',\n  {"seq": 99, "id": "EVIL"}\n ],\n "entries": ' + json.dumps(ENTRIES) + "\n}\n"
        self.assertEqual(json.loads(smuggle)["entries"], ENTRIES)      # a last-wins parse sees no change at all
        self.assertIn("EVIL", smuggle)                                 # yet the bytes carry a forged entry
        depth = ledger([*ENTRIES, {"seq": 3, "id": "C"}]).replace('"id": "C"', '"id": "EVIL", "id": "C"')
        self.assertEqual(json.loads(depth)["entries"][2]["id"], "C")   # same trick inside one entry
        for name, text in {"a second top-level entries key": smuggle, "a duplicate key inside an entry": depth}.items():
            with self.subTest(name + ", working tree"):
                self.write(LEDGER, text)
                self.assertTrue(any("ledger append-only rule (working tree" in p for p in self.check()), self.check())
            with self.subTest(name + ", committed"):
                self.commit(name)
                self.assertTrue(any("ledger append-only rule (HEAD" in p for p in self.check()), self.check())
                self.write(LEDGER, ledger(ENTRIES))
                self.commit("restore")
                self.assertEqual(self.check(), [])

    def test_a_staged_rewrite_behind_a_clean_worktree_stays_red(self):
        """Adversarial finding (2026-11-22): the index is a commit-in-waiting. A rewrite staged with `git add` and
        hidden by restoring the working-tree bytes (porcelain MM) — or hidden under a valid working-tree append — must
        stay red; a staged valid append is green."""
        self.write(LEDGER, ledger([{"seq": 1, "id": "X"}, ENTRIES[1]]))
        self.git("add", LEDGER)
        self.write(LEDGER, ledger(ENTRIES))                            # working tree restored, index holds the rewrite
        self.assertTrue(any("ledger append-only rule (index" in p for p in self.check()), self.check())
        self.write(LEDGER, ledger([*ENTRIES, {"seq": 3, "id": "C"}]))  # a valid append on top changes nothing
        self.assertTrue(any("ledger append-only rule (index" in p for p in self.check()), self.check())
        self.git("add", LEDGER)                                        # the staged state becomes the valid append
        self.assertEqual(self.check(), [])

    def test_deleting_or_renaming_the_ledger_still_fails(self):
        """Option (a) item 4: the append-only rule never excuses the ledger going missing."""
        self.git("mv", LEDGER, "closure-evidence/v2/cycle2/MOVED.json")
        self.assertTrue(any("working-tree change to released evidence: R" in p for p in self.check()), self.check())
        self.commit("rename the ledger")
        found = self.check()
        self.assertTrue(any(f"committed deletion of released evidence ({self.released[:12]}): {LEDGER}" == p
                            for p in found), found)
        self.assertTrue(any("missing or unreadable" in p for p in found), found)


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
