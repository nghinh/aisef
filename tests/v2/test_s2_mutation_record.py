"""validation/qualification/s2_mutation_record.py: the kill tests' closure and the reuse proof of a mutation result."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from validation.qualification import s2_mutation_record as R  # noqa: E402
from validation.v2 import mutation as m  # noqa: E402


def _git(repo: pathlib.Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", check=True, env=env).stdout.strip()


class Closure(unittest.TestCase):
    def test_imports_package_inits_and_named_test_paths_are_in_it_and_a_separator_is_not(self):
        with tempfile.TemporaryDirectory() as t:
            repo = pathlib.Path(t)
            files = {
                "tests/__init__.py": "", "tests/v2/__init__.py": "",
                "tests/v2/test_k.py": "import os\nfrom tests.v2 import helper\nDATA = 'fixtures'\nSEP = '/'\n",
                "tests/v2/helper.py": "from tests.v2.deep import x\n", "tests/v2/deep.py": "x = 1\n",
                "tests/v2/fixtures/a.json": "{}", "tests/v2/fixtures/b/c.json": "{}",
                "tests/v2/test_other.py": "", "aisef2/__init__.py": "",
            }
            for rel, text in files.items():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(text, encoding="utf-8")
            _git(repo, "init", "-q")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "c")
            got = R.closure(repo, _git(repo, "rev-parse", "HEAD"), ("tests/v2/test_k.py",))
            self.assertEqual(sorted(got), ["tests/__init__.py", "tests/v2/__init__.py", "tests/v2/deep.py",
                                           "tests/v2/fixtures/a.json", "tests/v2/fixtures/b/c.json", "tests/v2/helper.py",
                                           "tests/v2/test_k.py"])


class Proof(unittest.TestCase):
    TARGET = "aisef2/probe/cli_invocation.py::_argv_ok"

    def result(self, **over) -> dict:
        src = (ROOT / self.TARGET.split("::")[0]).read_text(encoding="utf-8")
        descs = [d for d, _ in m.mutants(src, self.TARGET.split("::")[1], m._enum_members(src, ROOT))]
        return {"target": self.TARGET, "kill_tests": list(m.S2_TARGETS[self.TARGET]),
                "results": [{"mutant": d, "killed": True} for d in descs], **over}

    def test_a_result_measured_at_head_is_usable(self):
        self.assertEqual(R.proof(ROOT, self.result(), "HEAD")[0], [])

    def test_a_different_kill_set_a_different_mutant_list_or_an_error_is_not(self):
        self.assertEqual(R.proof(ROOT, self.result(kill_tests=["tests/v2/test_c2_cli_protocol.py"]), "HEAD")[0],
                         ["its kill set is not the current one"])
        self.assertEqual(R.proof(ROOT, self.result(results=[]), "HEAD")[0], ["its mutants are not the current generator's"])
        self.assertEqual(R.proof(ROOT, self.result(error="boom"), "HEAD")[0], ["the run errored: boom"])

    def test_c_is_excluded_by_the_ruling(self):
        self.assertEqual(set(R.EXCLUDED), {"C"})


def _row(target, why=(), current=True, at=False, worker="X", survivors=(), timed_out=0, mutants=2, error=None) -> dict:
    results = [{"mutant": f"m{i}", "killed": True, **({"timed_out": ["tests/x.py"]} if i < timed_out else {})} for i in range(mutants)]
    result = {"target": target, "mutants": mutants, "killed": mutants - len(survivors), "survivors": list(survivors), "results": results,
              **({"error": error} if error else {})}
    return {"worker": worker, "measured_on": "c" * 40, "target": target, "why": list(why), "current": current,
            "at_final_head": at, "other_code_changed": [], "result": result}


class Account(unittest.TestCase):
    TARGETS = ("t/a.py::f", "t/b.py::g", "t/c.py::h")

    def test_three_classes_each_target_exactly_once(self):
        a = R.account([_row("t/a.py::f", at=True), _row("t/b.py::g", current=True), _row("t/c.py::h", current=False),
                       _row("t/c.py::h", why=["kill tests changed: tests/x.py"], worker="Y")], self.TARGETS)
        self.assertEqual((a["measured_at_final_head"], a["reused_after_mechanical_proof"]), (["t/a.py::f"], ["t/b.py::g", "t/c.py::h"]))
        self.assertEqual(a["stale_excluded"], [{"worker": "Y", "measured_on": "c" * 40, "target": "t/c.py::h",
                                               "why": ["kill tests changed: tests/x.py"]}])
        self.assertEqual((a["missing"], a["unknown"], a["accounted_exactly_once"], a["not_passing"]), ([], [], True, {}))

    def test_a_duplicate_is_accounted_once_a_current_result_preferred(self):
        a = R.account([_row("t/a.py::f", current=False, worker="B"), _row("t/a.py::f", current=True, worker="E"),
                       _row("t/a.py::f", current=True, worker="F"), _row("t/b.py::g"), _row("t/c.py::h")], self.TARGETS)
        self.assertEqual(a["chosen"]["t/a.py::f"]["worker"], "E")
        self.assertEqual([(e["worker"], e["why"]) for e in a["stale_excluded"]],
                         [("B", ["superseded by a current-snapshot result"]), ("F", ["a result already chosen for this target"])])
        self.assertTrue(a["accounted_exactly_once"])

    def test_a_missing_an_error_only_and_a_stale_only_target_are_not_accounted(self):
        a = R.account([_row("t/a.py::f"), _row("t/b.py::g", why=["the run errored: kill tests fail on the unmutated tree"]),
                       _row("t/c.py::h", why=["the target file changed since it was measured"]), _row("t/c.py::h", why=["x"])],
                      self.TARGETS)
        self.assertEqual((a["missing"], a["accounted_exactly_once"]), (["t/b.py::g", "t/c.py::h"], False))
        a = R.account([_row("t/a.py::f")], self.TARGETS)
        self.assertEqual(a["missing"], ["t/b.py::g", "t/c.py::h"])
        a = R.account([_row(t) for t in self.TARGETS] + [_row("t/z.py::q")], self.TARGETS)
        self.assertEqual((a["unknown"], a["accounted_exactly_once"]), (["t/z.py::q"], False))

    def test_a_timeout_a_survivor_or_an_error_never_passes(self):
        a = R.account([_row("t/a.py::f", timed_out=2), _row("t/b.py::g", survivors=["m1"]), _row("t/c.py::h", error="boom")],
                      self.TARGETS)
        self.assertEqual(a["not_passing"], {"t/a.py::f": ["2 mutant(s) killed only by the clock"],
                                            "t/b.py::g": ["1 unaudited survivor(s): ['m1']"],
                                            "t/c.py::h": ["the run errored: boom"]})
        self.assertEqual(R.account([_row("t/b.py::g", survivors=["m1"])], self.TARGETS, frozenset({("t/b.py::g", "m1")}))["not_passing"], {})

    def test_every_one_of_the_261_targets_is_accounted_for_exactly_once(self):
        a = R.account([_row(t) for t in m.S2_TARGETS], m.S2_TARGETS)
        self.assertEqual((len(m.S2_TARGETS), len(a["chosen"]), a["accounted_exactly_once"]), (261, 261, True))


class Artifacts(unittest.TestCase):
    def test_a_head_whose_tree_differs_outside_the_evidence_is_a_mismatch(self):
        with tempfile.TemporaryDirectory() as t:
            repo = pathlib.Path(t)
            (repo / "closure-evidence").mkdir()
            (repo / "src.py").write_text("a\n", encoding="utf-8")
            (repo / "closure-evidence" / "r.json").write_text("{}", encoding="utf-8")
            _git(repo, "init", "-q")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "measured")
            measured = _git(repo, "rev-parse", "HEAD")
            (repo / "closure-evidence" / "r.json").write_text('{"x": 1}', encoding="utf-8")
            _git(repo, "commit", "-qam", "evidence only")
            self.assertTrue(R.at_final_head(repo, measured, "HEAD"))
            (repo / "src.py").write_text("b\n", encoding="utf-8")
            _git(repo, "commit", "-qam", "code")
            self.assertFalse(R.at_final_head(repo, measured, "HEAD"))
            (repo / R.SUMMARY_REL).parent.mkdir(parents=True)
            (repo / R.SUMMARY_REL).write_text(json.dumps({"FINAL_HEAD": measured}), encoding="utf-8")
            self.assertEqual(R.check(repo), [f"HEAD mismatch: HEAD's tree outside closure-evidence/ is not FINAL_HEAD {measured[:12]}'s"])

    def test_a_kept_log_or_record_whose_bytes_changed_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            d = root / R.WORKERS_REL
            d.mkdir(parents=True)
            (d / "W.log").write_bytes(b"log\n")
            (d / "W.record.json").write_text('{"targets": []}', encoding="utf-8")
            sha = lambda p: R._sha256(p)  # noqa: E731
            doc = {"worker": "W", "snapshot": "c" * 40, "status": "s", "log": {"path": f"{R.WORKERS_REL}/W.log", "sha256": sha(d / "W.log")},
                   "record": {"path": f"{R.WORKERS_REL}/W.record.json", "sha256": sha(d / "W.record.json")}}
            (d / "W.history.json").write_text(json.dumps(doc), encoding="utf-8")
            self.assertEqual([h["worker"] for h in R.histories(root)], ["W"])
            (d / "W.log").write_bytes(b"log edited\n")
            with self.assertRaisesRegex(R.ArtifactMismatch, "is not the log W.history.json kept"):
                R.histories(root)
            (d / "W.log").write_bytes(b"log\n")
            (d / "W.record.json").write_text('{"targets": [ ]}', encoding="utf-8")
            with self.assertRaisesRegex(R.ArtifactMismatch, "is not the record W.history.json kept"):
                R.histories(root)

    def test_the_reuse_criteria_are_the_ones_frozen_at_819fe4d(self):
        self.assertEqual(R.criteria_sha256(), R.FROZEN_CRITERIA_SHA256)
        self.assertEqual(R.FROZEN_CRITERIA_SHA256, "dee08768f72aaacf31d2dcd0f9fde9e354d088f6b8d1ee7c8031aef664afacc0")


if __name__ == "__main__":
    unittest.main()
