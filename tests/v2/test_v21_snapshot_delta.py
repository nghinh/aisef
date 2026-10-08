"""validation/qualification/v21_snapshot_delta.py on a toy repository: each kind of change after the snapshot gets its
targets and the reuse proof's verdict, and --check refuses a table that is stale."""

from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from validation.qualification import v21_snapshot_delta as D  # noqa: E402


def _toy_mutation(targets: dict[str, list[str]]) -> str:
    """A toy validation/v2/mutation.py: the real generator, null mutant and enum lookup, with its own targets."""
    src = (ROOT / "validation/v2/mutation.py").read_text(encoding="utf-8")
    keep = {"_SWAP", "_inert", "_script", "_root", "mutants", "_enum_members", "null_mutant"}
    segs = [ast.get_source_segment(src, n) for n in ast.parse(src).body
            if getattr(n, "name", None) in keep or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) in keep)]
    return ("from __future__ import annotations\n\nimport ast\nimport copy\nimport pathlib\n\n" + "\n\n\n".join(segs)
            + f"\n\n\nCOPY = ('aisef2', 'tests/v2', 'validation/v2', 'docs')\nV21_TARGETS = {targets!r}\n")


TARGETS = {"aisef2/m.py::f": ["tests/v2/test_m.py"], "aisef2/m.py::g": ["tests/v2/test_m.py"],
           "aisef2/n.py::h": ["tests/v2/test_n.py"]}
FILES = {
    "aisef2/__init__.py": "", "aisef2/m.py": "def f(x):\n    return x == 1\n\n\ndef g(x):\n    return x > 2\n",
    "aisef2/n.py": "def h(x):\n    return not x\n",
    "tests/__init__.py": "", "tests/v2/__init__.py": "", "tests/v2/helper.py": "VALUE = 1\n",
    "tests/v2/test_m.py": "from tests.v2 import helper\nDATA = 'docs/data.json'\n", "tests/v2/test_n.py": "X = 1\n",
    "docs/data.json": "{}\n", "docs/notes.md": "notes\n",
    "validation/__init__.py": "", "validation/v2/__init__.py": "", "validation/v2/mutation.py": _toy_mutation(TARGETS),
    "validation/v2/cleanup_authority.py": "X = 1\n", "validation/v2/owned_run.py": "X = 1\n",
    "validation/v2/execution_order.py": "from validation.v2 import mutation\n",
}


def _git(repo: pathlib.Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", check=True,
                          env=env).stdout.strip()


class Toy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = pathlib.Path(self._tmp.name) / "repo"
        self.edit(FILES)
        _git(self.repo, "init", "-q")
        self.base = self.commit("snapshot")

    def edit(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text, encoding="utf-8")

    def commit(self, msg: str) -> str:
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", msg)
        return _git(self.repo, "rev-parse", "HEAD")

    def delta(self, files: dict[str, str]) -> dict:
        self.edit(files)
        head = self.commit("change")
        doc, _ = D.build(self.repo, self.base, head)
        self.assertEqual(len(doc["files"]), 1, doc["files"])
        return doc

    def verdicts(self, doc: dict) -> dict[str, str]:
        return {t: v["verdict"] for t, v in doc["targets"].items()}

    def test_a_product_change_re_measures_every_target_of_its_module_and_no_other(self):
        doc = self.delta({"aisef2/n.py": "def h(x):\n    return x\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], list(row["targets"]), row["remeasure"], row["names_changed"]),
                         (["product"], ["aisef2/n.py::h"], ["aisef2/n.py::h"], ["h"]))
        stand = f"a {self.base[:7]} result can stand at head"
        self.assertEqual(self.verdicts(doc), {"aisef2/m.py::f": stand, "aisef2/m.py::g": stand,
                                              "aisef2/n.py::h": "re-measure: the target file changed since it was measured"})

    def test_a_kill_file_change_re_measures_the_targets_whose_kill_set_holds_it(self):
        doc = self.delta({"tests/v2/test_n.py": "X = 2\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], row["targets"]), (["kill_file"], {"aisef2/n.py::h": ["in its kill set"]}))
        self.assertEqual(doc["targets"]["aisef2/n.py::h"]["verdict"], "re-measure: kill tests changed: tests/v2/test_n.py")
        self.assertEqual(doc["counts"]["remeasure"], 1)

    def test_a_closure_only_change_re_measures_the_targets_whose_kill_tests_import_it(self):
        doc = self.delta({"tests/v2/helper.py": "VALUE = 2\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], sorted(row["targets"]), row["tests_or_harness"]),
                         (["kill_closure"], ["aisef2/m.py::f", "aisef2/m.py::g"], ["tests/v2/test_m.py"]))
        self.assertEqual(self.verdicts(doc)["aisef2/m.py::f"], "re-measure: kill tests changed: tests/v2/helper.py")
        self.assertTrue(self.verdicts(doc)["aisef2/n.py::h"].endswith("can stand at head"))

    def test_a_harness_change_affects_every_target_and_the_proof_still_decides(self):
        doc = self.delta({"validation/v2/owned_run.py": "X = 2\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], sorted(row["targets"]), row["remeasure"]), (["harness"], sorted(TARGETS), []))
        self.assertEqual(doc["harness_changed"], [{"path": "validation/v2/owned_run.py", "names_changed": ["X"]}])
        self.assertEqual(doc["counts"]["remeasure"], 0)
        _, md = D.build(self.repo, self.base, "HEAD")
        self.assertIn("every V2.1 target (3): harness change", md)

    def test_an_evidence_only_change_affects_no_target(self):
        doc = self.delta({"docs/notes.md": "more notes\n"})
        self.assertEqual((doc["files"][0]["kinds"], doc["files"][0]["targets"]), ([D.EVIDENCE], {}))
        self.assertEqual((doc["counts"]["affected_targets"], doc["counts"]["remeasure"]), (0, 0))

    def test_data_a_kill_test_names_is_reported_beside_a_verdict_the_proof_does_not_change(self):
        doc = self.delta({"docs/data.json": "{\"x\": 1}\n"})
        self.assertEqual((doc["files"][0]["kinds"], doc["files"][0]["tests_or_harness"]), (["copy_data"], ["tests/v2/test_m.py"]))
        f = doc["targets"]["aisef2/m.py::f"]
        self.assertTrue(f["verdict"].endswith("can stand at head"))
        self.assertEqual(f["outside_the_proof"], ["data its kill tests read changed: docs/data.json"])

    def test_check_refuses_a_stale_or_edited_table_and_passes_a_current_one(self):
        self.edit({"docs/notes.md": "more notes\n"})
        head = self.commit("evidence")
        out = self.repo / "closure-evidence" / "delta"
        doc, md = D.build(self.repo, self.base, head)
        out.mkdir(parents=True)
        (out / "DELTA.json").write_text(D.S2._render(doc), encoding="utf-8")
        (out / "DELTA.md").write_text(md, encoding="utf-8")
        self.commit("the table")                         # inside OUT_DIR: never a change the table must cover
        self.assertEqual(D.check(self.repo, out), [])
        self.edit({"docs/more.md": "x\n"})
        self.commit("more evidence")                     # evidence after the table's head: still covered
        self.assertEqual(D.check(self.repo, out), [])
        self.edit({"aisef2/n.py": "def h(x):\n    return x\n"})
        now = self.commit("product")
        self.assertEqual(D.check(self.repo, out), [f"stale: HEAD {now[:12]} has changes after the table's head "
                                                   f"{head[:12]} that it does not cover: aisef2/n.py"])
        (out / "DELTA.md").write_text(md.replace("re-measure", "stands"), encoding="utf-8")
        self.assertIn(f"{out}/DELTA.md is not what {self.base[:12]}..{head[:12]} derives now", D.check(self.repo, out))
        doc["head"] = now
        (out / "DELTA.json").write_text(json.dumps(doc), encoding="utf-8")
        self.assertIn(f"{out}/DELTA.json is not what {self.base[:12]}..{now[:12]} derives now", D.check(self.repo, out))


if __name__ == "__main__":
    unittest.main()
