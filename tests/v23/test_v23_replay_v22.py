"""validation/v23/replay_v22.py fails closed: each failure mode on a synthetic git tree (seconds, no real replay)."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23 import replay_v22 as RP  # noqa: E402

FAKE = "tests/v2/test_fake.py::Fake."
FILES = {
    "tests/__init__.py": "",
    "tests/v2/__init__.py": "",
    "closure-evidence/r.json": '{"ok": true}\n',
    "tests/v2/test_fake.py": textwrap.dedent('''\
        import json, os, pathlib, shutil, unittest
        ROOT = pathlib.Path(__file__).resolve().parents[2]
        class Fake(unittest.TestCase):
            def test_reads(self):
                self.assertTrue(json.loads((ROOT / "closure-evidence/r.json").read_text(encoding="utf-8"))["ok"])
                self.assertEqual(os.environ.get("AISEF_SEALING"), "1")
                self.assertIsNone(shutil.which("opencode"))
                self.assertNotIn("AISEF_OTHER", os.environ)
                self.assertNotIn("PYTHONPATH", os.environ)
                self.assertIn("xdg", os.environ["XDG_DATA_HOME"])
            def test_skips(self):
                self.skipTest("skipped at v2.2.0")
            def test_fails(self):
                self.fail("red at v2.2.0")
            def test_residual(self):
                pass
            def test_ungated(self):
                pass
        '''),
    # stand-in for the tree's own process-range harness: runs CMD, reports exit; "residual" when the id says so
    "validation/v2/owned_run.py": textwrap.dedent('''\
        import json, subprocess, sys
        out, cmd = sys.argv[2], sys.argv[4:]
        code = subprocess.run(cmd).returncode
        residual = any("test_residual" in c for c in cmd)
        json.dump({"exit": code, "owned_after": int(residual), "escaped": [], "released_empty": True}, open(out, "w"))
        sys.exit(3 if residual else code)
        '''),
}
GATED_NAMES = ("test_reads", "test_skips", "test_fails", "test_residual")


def _git(root, *a):
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false", *a], capture_output=True, check=True, encoding="utf-8").stdout.strip()


class Replay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef-replay-test-")
        cls.tree = pathlib.Path(cls._tmp.name, "tree").resolve()
        files = dict(FILES, **{"tests/v2/sealing_gate.py": "GATED = (\n" + "".join(
            f"    {FAKE + n!r},\n" for n in GATED_NAMES) + ")\n"})
        for rel, text in files.items():
            (cls.tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (cls.tree / rel).write_text(text, encoding="utf-8")
        _git(cls.tree, "init", "-q")
        _git(cls.tree, "add", "-A")
        _git(cls.tree, "commit", "-q", "-m", "fake v2.2.0")
        cls.commit = _git(cls.tree, "rev-parse", "HEAD")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_replay(self, *names, commit=None):
        with tempfile.TemporaryDirectory(prefix="aisef-replay-scratch-") as s:
            old = dict(os.environ)
            os.environ.update(AISEF_OTHER="1", PYTHONPATH="/nonexistent")
            try:
                return RP.replay(self.tree, [FAKE + n for n in names], scratch=pathlib.Path(s),
                                 commit=commit or self.commit)
            finally:
                os.environ.clear()
                os.environ.update(old)

    def test_a_passing_test_lists_its_records_under_the_env_guard(self):
        doc = self.run_replay("test_reads")
        self.assertEqual(doc["problems"], [])
        self.assertEqual(doc["verdict"], "PARTIAL")      # a subset is never a full PASS
        (t,) = doc["tests"]
        self.assertEqual((t["outcome"], t["ran"], t["skipped"], t["exit"]), ("PASS", 1, 0, 0))
        self.assertEqual(t["records"], [{"path": "closure-evidence/r.json", "committed": True,
                                         "sha256": RP._sha(FILES["closure-evidence/r.json"].encode())}])
        self.assertEqual(doc["tree"]["commit"], self.commit)

    def test_a_wrong_commit_is_refused(self):
        doc = self.run_replay("test_reads", commit="0" * 40)
        self.assertIn(f"tree is at {self.commit}, not v2.2.0 {'0' * 40}", doc["problems"])
        self.assertEqual(doc["verdict"], "FAIL")

    def test_a_corrupted_record_is_named_by_path_by_the_clean_tree_rule_and_by_the_test(self):
        p = self.tree / "closure-evidence/r.json"
        p.write_text('{"ok": false}\n', encoding="utf-8")
        try:
            doc = self.run_replay("test_reads")
        finally:
            p.write_text(FILES["closure-evidence/r.json"], encoding="utf-8")
        probs = doc["problems"]
        self.assertIn("tree not clean: M closure-evidence/r.json", probs)
        self.assertTrue(any(x.startswith(f"{FAKE}test_reads: FAIL") for x in probs), probs)
        self.assertIn(f"{FAKE}test_reads: record closure-evidence/r.json is not the v2.2.0 committed bytes", probs)

    def test_an_untracked_or_ignored_file_is_refused(self):
        p = self.tree / "closure-evidence/planted.json"
        p.write_text("{}", encoding="utf-8")
        try:
            doc = self.run_replay("test_reads")
        finally:
            p.unlink()
        self.assertIn("tree not clean: ?? closure-evidence/planted.json", doc["problems"])

    def test_a_skip_a_failure_and_a_residual_process_are_each_named(self):
        doc = self.run_replay("test_skips", "test_fails", "test_residual")
        out = {t["id"].split(".")[-1]: t for t in doc["tests"]}
        self.assertEqual(out["test_skips"]["outcome"], "SKIP")
        self.assertEqual(out["test_fails"]["outcome"], "FAIL")
        self.assertTrue(any("red at v2.2.0" in m for m in out["test_fails"]["messages"]))
        self.assertEqual((out["test_residual"]["outcome"], out["test_residual"]["exit"]), ("ERROR", 3))
        self.assertEqual(len([p for p in doc["problems"] if p.startswith(FAKE)]), 3)

    def test_a_test_outside_the_trees_GATED_list_is_refused(self):
        doc = self.run_replay("test_ungated")
        self.assertIn(f"{FAKE}test_ungated: not in the tree's sealing_gate.GATED", doc["problems"])

    def test_the_evidence_carries_no_local_path(self):
        doc = self.run_replay("test_reads", "test_fails")
        text = json.dumps(doc)
        for local in (str(self.tree), os.path.realpath(self.tree), str(pathlib.Path.home())):
            self.assertNotIn(local, text)

    def test_the_cli_refuses_an_unknown_id_and_fails_on_a_tree_that_is_not_v2_2_0(self):
        self.assertEqual(RP.main(["--only", "tests/v2/test_x.py::X.test_y"]), 2)
        with tempfile.TemporaryDirectory(prefix="aisef-replay-scratch-") as s:
            self.assertEqual(RP.main(["--tree", str(self.tree), "--only", RP.V22_REPLAYED[0], "--scratch", s]), 1)


class EnvGuard(unittest.TestCase):
    def test_opencode_dirs_aisef_vars_and_python_path_are_removed(self):
        with tempfile.TemporaryDirectory(prefix="aisef-replay-guard-") as s:
            s = pathlib.Path(s)
            (s / "bin").mkdir()
            (s / "bin" / "opencode").write_text("#!/bin/sh\n", encoding="utf-8")
            env = RP.guarded_env(s, {"PATH": os.pathsep.join([str(s / "bin"), "/usr/bin"]), "AISEF_X": "1",
                                     "PYTHONPATH": "x", "HOME": "h"})
            self.assertEqual(env["PATH"], "/usr/bin")
            self.assertNotIn("AISEF_X", env)
            self.assertNotIn("PYTHONPATH", env)
            self.assertEqual((env["AISEF_SEALING"], env["PYTHONDONTWRITEBYTECODE"]), ("1", "1"))
            for k in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
                self.assertTrue(env[k].startswith(str(s)), k)


if __name__ == "__main__":
    unittest.main()
