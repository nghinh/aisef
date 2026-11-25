"""B1 moved-source admissibility vs the dirty-identity rule (adversarial negative test).

The round-v2.3 B1 acceptance (`b1_bindings_check._v23_accepts`, owner ruling 2026-11-22 section D) accepts a moved
target only on a committed round entry that measured exactly the live bytes and is clean under the mutation rules.
The engine's own documented rule says a dirty identity can never become MEASURED (`_v23_identity`: "`dirty: true`
can never become MEASURED"), so an entry whose `identity.dirty` is true must NOT qualify a moved B1 source.

These tests assert that correct behaviour. The dirty case is the reproduction: it FAILS on the current code, because
`target_problems` -> `_problems_v2` never reads `identity.dirty`, so a measurement taken on a dirty tree is accepted
as current B1 qualification. The control case (the byte-identical entry with `dirty: false`) is accepted, so the
pair isolates `dirty` as the deciding factor and cannot pass vacuously after an over-broad fix.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import b1_bindings_check as bc  # noqa: E402
from validation.v2 import mutation as mu  # noqa: E402
from validation.v2 import version_forward as vf  # noqa: E402


def _lf(root: pathlib.Path, rel: str) -> str:
    """The LF-normalised digest the admissibility rule compares each identity map against."""
    import hashlib
    return hashlib.sha256((root / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git(root: pathlib.Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                          capture_output=True, encoding="utf-8", check=True).stdout.strip()


class DirtyIdentityAdmissibility(unittest.TestCase):
    """A committed, all-KILLED round-v2.3 entry at the live digest, differing ONLY in `identity.dirty`."""

    SRC = "pkg/mod.py"
    TGT = "pkg/mod.py::f"
    KILL = "tests/v2/p0/test_kill.py"
    HDR = "FAIL: test_kill (v2.p0.test_kill.T.test_kill) | AssertionError"
    MOVED = "pkg/mod.py::f: pkg/mod.py moved since the manifest froze"

    def _entry(self, root: pathlib.Path, head: str, dirty: bool) -> dict:
        """A well-formed runner-2 entry, clean under `_problems_v2` (confirmed kill bracket, counts consistent,
        T0 green, source_sha256 = the live file's LF digest), shaped like the committed record's entries."""
        live = mu.source_digest((root / self.SRC).read_text(encoding="utf-8"))
        control = {"file": self.KILL, "role": "control", "exit": 0, "outcome": "PASS", "why": None, "ran": 1}
        result = {"mutant": "L2 return 1 -> return None", "class": "KILLED", "killed": True,
                  "killed_by": {"file": self.KILL, "first": self.HDR},
                  "files": [{"file": self.KILL, "exit": 1, "outcome": "FAIL", "why": None, "ran": 1,
                             "failures": 1, "first": self.HDR},
                            control, dict(control),
                            {"file": self.KILL, "role": "rerun", "exit": 1, "outcome": "FAIL", "why": None,
                             "ran": 1, "failures": 1, "first": self.HDR}]}
        return {"target": self.TGT, "runner": 2, "source_sha256": live, "mutants": 1, "killed": 1,
                "killed_by_timeout": 0, "survivors": [], "kill_tests": [self.KILL], "results": [result],
                "t0": [{"file": self.KILL, "role": "t0", "exit": 0, "outcome": "PASS", "why": None, "ran": 1}],
                "tree_sha256": "0" * 64, "strays_reaped": 0,
                "identity": {"measured_on": head, "dirty": dirty,
                             "slice": {"func": "f", "null_sha256": "0" * 64},
                             # full provenance on BOTH variants (the shared admissibility rule refuses an empty
                             # closure/generator/env as unproven): dirty stays the only difference between the cases
                             "closure": {self.SRC: _lf(root, self.SRC)}, "kill_files": {self.KILL: _lf(root, self.KILL)},
                             "generator": {"descriptions_sha": "0" * 64, "mutated_slices_sha": "0" * 64},
                             "enum_modules": {self.SRC: _lf(root, self.SRC)}, "platform": {"family": "posix"},
                             "env": {"tree_sha256": "0" * 64, "runner_sha256": "0" * 64}}}

    def _repo(self, dirty: bool) -> pathlib.Path:
        """A minimal git repo: the live target source, a registry file, and the round record COMMITTED at HEAD
        (the committed entries are the whole working list, so the append-only prefix rule passes)."""
        root = pathlib.Path(tempfile.mkdtemp(prefix="aisef-v23-b1-adm-"))
        _git(root, "init", "-q")
        (root / self.SRC).parent.mkdir(parents=True)
        (root / self.SRC).write_text("def f():\n    return 1\n", encoding="utf-8")
        (root / self.KILL).parent.mkdir(parents=True)   # the admissibility rule checks every identity map
        (root / self.KILL).write_text("def test_kill():\n    pass\n", encoding="utf-8")   # against the live tree
        (root / "reg.py").write_text("REGISTRY = 1\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "sources")
        head = _git(root, "rev-parse", "HEAD")
        p = root / mu.V23_REL
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"record": "r", "tool": "t", "entries": [self._entry(root, head, dirty)]}),
                     encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "round record")
        return root

    def _man(self, root: pathlib.Path) -> dict:
        """A manifest whose recorded digest differs from the live bytes, so the target reads as moved and the
        decision falls to the round-v2.3 acceptance."""
        return {"frozen_bindings": {"aisef2_kernel_tree": "k" * 40, "registry_file": "reg.py",
                                    "registry_sha256": hashlib.sha256((root / "reg.py").read_bytes()).hexdigest()},
                "targets": {self.TGT: {"source": self.SRC, "source_sha256": "f" * 64}}}

    def test_a_dirty_identity_entry_must_not_qualify_a_moved_b1_source(self):
        root = self._repo(dirty=True)
        with mock.patch.object(bc, "ROOT", root), vf.in_round("v2.3"):
            self.assertFalse(
                bc._v23_accepts(self.TGT, {"source": self.SRC}),
                "a round-v2.3 measurement taken on a DIRTY tree (identity.dirty == true) was accepted as current "
                "B1 qualification, although a dirty identity can never become MEASURED")
            self.assertEqual(bc.problems(self._man(root), kernel="k" * 40), [self.MOVED],
                             "problems() must still report the moved source when the only round entry is dirty")

    def test_control_the_same_entry_with_a_clean_identity_is_accepted(self):
        root = self._repo(dirty=False)
        with mock.patch.object(bc, "ROOT", root), vf.in_round("v2.3"):
            self.assertTrue(bc._v23_accepts(self.TGT, {"source": self.SRC}),
                            "the byte-identical entry with dirty: false must be accepted (dirty is the deciding "
                            "factor; an over-broad fix that refuses both is wrong)")
            self.assertEqual(bc.problems(self._man(root), kernel="k" * 40), [])


if __name__ == "__main__":
    unittest.main()
