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

from aisef2.arch.enums import BehaviorVerdict, Enforcement, SubjectAbsence  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import process_effect as pe  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, ObservationKind, RevisionRef  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402


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


class ProcessEffectAsk(unittest.TestCase):
    """process_effect HARNESS/ask: two of its mutants were killed only by the clock (L47 the request line's newline,
    L51 the answer ask returns) — each leaves the harness waiting. One bounded observation, its whole outcome asserted,
    fails them by assertion inside its own window. First in that target's kill set, before the files that would hang."""

    def test_one_asked_call_is_answered_and_observed(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-s2-kills-") as t:
            root = pathlib.Path(os.path.realpath(t))
            (root / "subj.py").write_text("def total(*values):\n    return sum(values)\n", encoding="utf-8")
            probe = pe.ProcessEffectProbe()
            spec = ProductProofSpec.create(
                contract_id="BC-EFFECT", probe_id=probe.id, probe_digest=probe.digest,
                probe_input={"subject": {"kind": "process_effect", "locator": "subj:total"},
                             "stimulus": {"scenario": [{"step": "call", "args": [1, 2], "kwargs": {}}]},
                             "observable": {"returns": 3, "within_s": 5},
                             "subject_absence": SubjectAbsence.REQUIRES_SUBJECT.value},
                candidate_expectation=BehaviorVerdict.SATISFIED, compiler_id="test", compiler_digest="c" * 64)
            o = probe.observe(spec, RevisionRef("89abcdef0123456789abcdef0123456789abcdef", str(root)),
                              ExecutionEnv(sys.executable, 10, Enforcement.PARTIAL))
            self.assertEqual((o.kind, o.verdict), (ObservationKind.OBSERVED, BehaviorVerdict.SATISFIED), o.detail)


if __name__ == "__main__":
    unittest.main()
