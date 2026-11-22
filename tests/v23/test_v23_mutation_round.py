"""Round-v2.3 mutation supersession (W1-DESIGN §2.5; ledger seq 13) — the read-time mechanism, always run.

The phase records, RECORDS, PHASE_TARGETS, SUPERSEDED and V21_TARGETS are never touched: a round-v2.3 entry replaces
a target's entry at READ time only, and only when it is committed at HEAD. These tests prove the mechanism fails
closed: a rewritten committed prefix, an uncommitted newest entry (I7 — never a fallback), the FS-4 pristine
exclusion, and the two-file positional audits whose key carries the source digest.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import mutation as m  # noqa: E402


def _git(root: pathlib.Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                          capture_output=True, encoding="utf-8", check=True).stdout.strip()


def repo_with(entries_committed: list[dict], entries_working: list[dict] | None = None) -> pathlib.Path:
    t = pathlib.Path(tempfile.mkdtemp(prefix="aisef-v23-mut-"))
    _git(t, "init", "-q")
    p = t / m.V23_REL
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"record": "r", "entries": entries_committed}), encoding="utf-8")
    _git(t, "add", "-A")
    _git(t, "commit", "-qm", "one")
    if entries_working is not None:
        p.write_text(json.dumps({"record": "r", "entries": entries_working}), encoding="utf-8")
    return t


class Newest(unittest.TestCase):
    E1 = {"target": "aisef2/x.py::f", "runner": 2, "killed": 1}
    E2 = {"target": "aisef2/x.py::f", "runner": 2, "killed": 2}
    E3 = {"target": "aisef2/y.py::g", "runner": 2, "killed": 3}

    def test_the_last_committed_entry_per_target_wins(self):
        t = repo_with([self.E1, self.E3, self.E2])
        newest, problems = m.v23_newest(t)
        self.assertEqual((problems, newest["aisef2/x.py::f"]["killed"], newest["aisef2/y.py::g"]["killed"]),
                         ([], 2, 3))

    def test_an_uncommitted_newest_entry_is_unresolved_never_a_fallback(self):
        t = repo_with([self.E1], [self.E1, self.E2])
        newest, problems = m.v23_newest(t)
        self.assertEqual(problems, [])
        self.assertIn("UNRESOLVED (I7)", newest["aisef2/x.py::f"]["error"])
        self.assertNotIn("killed", newest["aisef2/x.py::f"])   # the committed E1 is not fallen back to

    def test_a_rewritten_committed_prefix_fails_closed(self):
        t = repo_with([self.E1, self.E3], [self.E2, self.E3])
        newest, problems = m.v23_newest(t)
        self.assertEqual(newest, {})
        self.assertEqual(len(problems), 1)
        self.assertIn("not a prefix of the working list", problems[0])

    def test_no_record_is_no_entries_and_no_problem(self):
        t = pathlib.Path(tempfile.mkdtemp(prefix="aisef-v23-mut-"))
        _git(t, "init", "-q")
        (t / "a.txt").write_text("x", encoding="utf-8")
        _git(t, "add", "-A")
        _git(t, "commit", "-qm", "one")
        self.assertEqual(m.v23_newest(t), ({}, []))

    def test_substitution_replaces_matching_targets_only(self):
        record = {"record": "r", "targets": [{"target": "a", "n": 1}, {"target": "b", "n": 2}]}
        out = m.v23_substituted(record, {"b": {"target": "b", "n": 9}})
        self.assertEqual([t["n"] for t in out["targets"]], [1, 9])
        self.assertEqual([t["n"] for t in record["targets"]], [1, 2])   # the record itself is untouched

    def test_entry_sha256_is_canonical(self):
        self.assertEqual(m.entry_sha256({"b": 1, "a": [2]}), m.entry_sha256({"a": [2], "b": 1}))
        self.assertNotEqual(m.entry_sha256({"a": 1}), m.entry_sha256({"a": 2}))


class Fs4(unittest.TestCase):
    def test_pristine_excludes_the_round_records(self):
        src = pathlib.Path(tempfile.mkdtemp(prefix="aisef-v23-fs4-"))
        for rel in (m.V23_REL, m.V23_AUDITS_REL, "closure-evidence/v2/v2.3/KEEP.json"):
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            (src / rel).write_text("{}", encoding="utf-8")
        dst = pathlib.Path(tempfile.mkdtemp(prefix="aisef-v23-fs4-")) / "tree"
        tree, _ = m._pristine(src, dst)
        self.assertFalse((tree / m.V23_REL).exists())
        self.assertFalse((tree / m.V23_AUDITS_REL).exists())
        self.assertTrue((tree / "closure-evidence/v2/v2.3/KEEP.json").exists())


class Audits(unittest.TestCase):
    ENTRY = {"target": "aisef2/x.py::f", "mutant": "L2 Gt->LtE", "class": "AUDITED", "group": "g",
             "grounds": "the branch is unreachable for every consumer", "index": 0, "source_sha256": "a" * 64,
             "consumers_checked": ["tests/v2/test_x.py"], "exceptions_checked": ["none"]}

    def write(self, root: pathlib.Path, rel: str, entries: list) -> None:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"entries": entries}), encoding="utf-8")

    def test_both_files_are_read_and_the_round_key_carries_the_source(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="aisef-v23-aud-"))
        other = dict(self.ENTRY, source_sha256="b" * 64, grounds="re-measured source")
        self.write(root, m.AUDITS_REL, [self.ENTRY])
        self.write(root, m.V23_AUDITS_REL, [other])
        self.assertEqual(m.audits_at(root)[1], [])
        self.assertEqual(m.v23_audits_at(root)[1], [])
        # same (target, index, mutant), different sources: each round's audit covers its own digest, no collision
        self.assertIsNotNone(m.audit_of(root, self.ENTRY["target"], 0, self.ENTRY["mutant"], "a" * 64))
        self.assertIsNotNone(m.audit_of(root, self.ENTRY["target"], 0, self.ENTRY["mutant"], "b" * 64))
        self.assertIsNone(m.audit_of(root, self.ENTRY["target"], 0, self.ENTRY["mutant"], "c" * 64))

    def test_a_true_duplicate_is_still_named(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="aisef-v23-aud-"))
        self.write(root, m.V23_AUDITS_REL, [self.ENTRY, dict(self.ENTRY)])
        _, problems = m.v23_audits_at(root)
        self.assertEqual(len(problems), 1)
        self.assertIn("is audited twice", problems[0])
        self.assertIn(m.V23_AUDITS_REL, problems[0])


if __name__ == "__main__":
    unittest.main()
