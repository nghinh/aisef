"""V2.0-S2 mutation: cases that kill survivors of the current-snapshot campaign. A file of its own, named only in the kill
sets of the targets it was written for (validation/v2/mutation.py), so adding to it re-measures those targets alone —
every other result's kill-test closure stays byte-identical (validation/qualification/s2_mutation_record.py)."""

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

from aisef2.probe import cli_invocation as ci  # noqa: E402


class AgentInvoke(unittest.TestCase):
    """cli_invocation's shipped AGENT, op invoke of a module as `python -m` runs it."""

    def test_a_module_run_as_main_sees_itself_as_main_and_its_own_file_as_argv0(self):
        """AGENT/op_invoke L129 (`alter_sys=True`): the subject's sys.argv[0] is its file and sys.modules['__main__'] is
        the subject itself, as under `python -m`."""
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(os.path.realpath(t))
            root, work = t / "rev", t / "work"
            (root / "mainsubj").mkdir(parents=True)
            work.mkdir()
            (root / "mainsubj" / "__init__.py").write_text("", encoding="utf-8")
            mod = root / "mainsubj" / "cli.py"
            mod.write_text("import sys\nMARK = object()\nprint(sys.argv[0])\nprint(sys.argv[1:])\n"
                           "print(sys.modules['__main__'].__dict__.get('MARK') is MARK)\n", encoding="utf-8")
            with open(work / "agent.log", "wb") as log:
                agent = subprocess.Popen([sys.executable, "-I", "-B", "-X", "utf8=1", "-c", ci.AGENT, str(root), str(work)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, cwd=work)
            try:
                self.assertEqual(json.loads(agent.stdout.readline()), {"ready": True, "n": 0})
                req = {"op": "invoke", "n": 1, "stdin": os.devnull, "out": str(work / "o.bin"), "err": str(work / "e.bin"),
                       "name": "mainsubj.cli", "attr": "__main__", "argv": ["x", "y"]}
                agent.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
                agent.stdin.flush()
                self.assertEqual(json.loads(agent.stdout.readline()), {"raw": None, "code": 0, "raised": None, "n": 1})
            finally:
                agent.stdin.close()
                agent.wait(30)
                agent.stdout.close()
            self.assertEqual((work / "o.bin").read_bytes().decode("utf-8").splitlines(), [str(mod), "['x', 'y']", "True"])
            self.assertEqual((work / "e.bin").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
