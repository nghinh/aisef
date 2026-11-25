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


class QaAcceptance(unittest.TestCase):
    """Q0-1 option Q-a (owner ruling 2026-11-22 §D): the B1 moved-source acceptance is LIVE, round-gated and
    fail-closed — a moved target is accepted only in round v2.3, only with a committed round entry that measured
    exactly the live bytes and is clean; everything else stays red. Red-before/green-after at the mechanism level
    (the real green lands with the targeted measurement)."""

    SRC = "aisef2/app/run.py"
    TGT = "aisef2/app/run.py::execute"

    def man(self):
        import hashlib
        from validation.v2 import b1_bindings_check as bc
        reg = "aisef2/invariants/registry.py"
        return {"frozen_bindings": {"aisef2_kernel_tree": "k" * 40, "registry_file": reg,
                                    "registry_sha256": hashlib.sha256((bc.ROOT / reg).read_bytes()).hexdigest()},
                "targets": {self.TGT: {"source": self.SRC, "source_sha256": "0" * 64}}}

    def probs(self, newest):
        from unittest import mock
        from validation.v2 import b1_bindings_check as bc
        from validation.v2 import mutation as mu
        from validation.v2 import version_forward as vf
        with mock.patch.object(mu, "v23_newest", return_value=newest), vf.in_round("v2.3"):
            return [x for x in bc.problems(self.man(), kernel="k" * 40) if not x.startswith("kernel ")]

    def entry(self, **over):
        """A FULLY admissible round entry (the shared rule, mutation.v23_admissible, really runs — no mocking it):
        every override below starts from evidence that passes, so each red case isolates exactly one violation."""
        import hashlib
        from validation.v2 import mutation as mu
        live = mu.source_digest((ROOT / self.SRC).read_text(encoding="utf-8"))

        def lf(rel):   # the admissibility rule checks each identity map against the LIVE tree (LF-normalised)
            return hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        identity = {"measured_on": "c" * 40, "dirty": False,
                    "slice": {"func": "execute", "null_sha256": "d" * 64}, "closure": {self.SRC: lf(self.SRC)},
                    "kill_files": {"tests/v2/test_app_run.py": lf("tests/v2/test_app_run.py")},
                    "generator": {"descriptions_sha": "a" * 64, "mutated_slices_sha": "b" * 64},
                    "enum_modules": {self.SRC: lf(self.SRC)},
                    "platform": {"family": "posix", "sys_platform": "darwin", "release": "r", "machine": "arm64"},
                    "env": {"python": "3", "implementation": "cpython", "tree_sha256": "1" * 64,
                            "runner_sha256": "2" * 64}}
        kill, hdr = "tests/v2/test_app_run.py", "FAIL: t (v2.test_app_run.T.t) | AssertionError"
        control = {"file": kill, "role": "control", "exit": 0, "outcome": "PASS", "why": None, "ran": 1}
        row = {"mutant": "L1 Gt->LtE", "class": "KILLED", "killed": True, "killed_by": {"file": kill, "first": hdr},
               "files": [{"file": kill, "exit": 1, "outcome": "FAIL", "why": None, "ran": 1, "failures": 1,
                          "first": hdr}, control, dict(control),
                         {"file": kill, "role": "rerun", "exit": 1, "outcome": "FAIL", "why": None, "ran": 1,
                          "failures": 1, "first": hdr}]}
        return {"target": self.TGT, "runner": 2, "source_sha256": live,
                "kill_tests": [kill], "mutants": 1, "killed": 1, "killed_by_timeout": 0, "survivors": [],
                "results": [row],
                "t0": [{"file": kill, "role": "t0", "exit": 0, "outcome": "PASS", "why": None, "ran": 1}],
                "identity": identity, **over}

    def test_red_before_no_round_entry_keeps_the_target_red(self):
        self.assertEqual(self.probs(({}, [])), [f"{self.TGT}: {self.SRC} moved since the manifest froze"])

    def test_red_outside_the_round_whatever_the_entries_say(self):
        from unittest import mock
        from validation.v2 import b1_bindings_check as bc
        from validation.v2 import mutation as mu
        with mock.patch.object(mu, "v23_newest", return_value=({self.TGT: self.entry()}, [])):
            out = [x for x in bc.problems(self.man(), kernel="k" * 40) if not x.startswith("kernel ")]
        self.assertEqual(out, [f"{self.TGT}: {self.SRC} moved since the manifest froze"])

    def test_green_after_a_committed_clean_entry_at_the_live_digest_is_accepted(self):
        self.assertEqual(self.probs(({self.TGT: self.entry()}, [])), [])

    def test_fail_closed_on_digest_mismatch_uncommitted_entry_open_problems_or_a_broken_record(self):
        dirty = self.entry()
        dirty["identity"] = dict(dirty["identity"], dirty=True)
        unstated = self.entry()
        unstated["identity"] = {k: v for k, v in unstated["identity"].items() if k != "dirty"}
        unaudited = self.entry(survivors=["L1 Gt->LtE"], killed=0,
                               results=[{"mutant": "L1 Gt->LtE", "class": "SURVIVED"}])
        no_identity = self.entry()
        del no_identity["identity"]
        cases = {
            "digest mismatch": ({self.TGT: self.entry(source_sha256="f" * 64)}, []),
            "uncommitted newest (I7)": ({self.TGT: {"target": self.TGT, "error": "UNRESOLVED (I7): uncommitted"}}, []),
            "dirty identity (owner ruling 2026-11-25 1)": ({self.TGT: dirty}, []),
            "dirty key absent (cleanliness unproven)": ({self.TGT: unstated}, []),
            "no identity at all": ({self.TGT: no_identity}, []),
            "no T0 observation": ({self.TGT: self.entry(t0=[])}, []),
            "unaudited survivor": ({self.TGT: unaudited}, []),
            "malformed entry (missing kill_tests)": ({self.TGT: {"target": self.TGT, "runner": 2,
                                                                 "source_sha256": self.entry()["source_sha256"]}}, []),
            "broken round record": ({}, ["not a prefix (fail closed)"]),
        }
        for name, newest in cases.items():
            with self.subTest(name):
                self.assertEqual(self.probs(newest),
                                 [f"{self.TGT}: {self.SRC} moved since the manifest froze"])


if __name__ == "__main__":
    unittest.main()
