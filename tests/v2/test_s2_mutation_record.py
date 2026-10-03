"""validation/qualification/s2_mutation_record.py: the kill tests' closure and the reuse proof of a mutation result."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
