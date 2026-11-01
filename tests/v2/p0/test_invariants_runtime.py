"""ROADMAP-2.2 A1 — runtime arming: the nine invariants are registered and armed in the RUNNING process, not only
in the test tiers. `register_runtime` resolves every CODE mechanism (importable from an installed kernel: the
static-rule/checker/tier/document checks are the development tier's and stay in `register`), `arm_runtime` marks the
process armed, and `require_armed` passes for either kind of arming. A clean process is unarmed and its journal
choke points fail closed. `verify` re-derives the recorded digests against its own kernel — same kernel only."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from aisef2.app import run as R
from aisef2.app.verify import _invariant_problems
from aisef2.arch.enums import InvariantId
from aisef2.invariants import registry as reg

ROOT = Path(__file__).resolve().parents[3]


class RuntimeArming(unittest.TestCase):
    def test_arm_runtime_is_idempotent_and_its_digests_are_the_registry_s(self):
        a1, a2 = reg.arm_runtime(), reg.arm_runtime()
        self.assertEqual(a1, a2)
        self.assertEqual(a1.invariants, frozenset(InvariantId))
        self.assertEqual(a1.registry_digest, reg.registry_digest())
        self.assertEqual(a1.code_mechanism_digest, reg.runtime_mechanism_digest())
        for invariant in InvariantId:
            reg.require_armed(invariant)    # armed either way; raises on failure

    def test_runtime_registration_agrees_with_the_full_one_on_the_development_tree(self):
        """Same typed registry, same registry digest; the code digest covers exactly the CODE mechanisms."""
        full = reg.register()
        runtime = reg.register_runtime()
        self.assertEqual(full.digest, runtime.digest)
        self.assertEqual(runtime.code_mechanism_digest, reg.runtime_mechanism_digest())

    def test_a_clean_process_is_unarmed_and_the_journal_choke_points_fail_closed(self):
        """In a fresh interpreter (no test tier imported): require_armed raises, Authority refuses to append, and
        arm_runtime() opens both — the uncontainable InvariantError is the refusal, not a verdict."""
        code = (
            "from aisef2.invariants import registry as reg\n"
            "from aisef2.arch.enums import InvariantId\n"
            "from aisef2.errors import InvariantError\n"
            "try:\n"
            "    reg.require_armed(InvariantId.VI)\n"
            "    raise SystemExit('require_armed passed unarmed')\n"
            "except InvariantError:\n"
            "    pass\n"
            "from aisef2.journal.format2 import JournalWriter2\n"
            "from aisef2.journal.fold import Authority\n"
            "from aisef2.journal.projections import PROJECTIONS\n"
            "import tempfile, pathlib\n"
            "d = pathlib.Path(tempfile.mkdtemp())\n"
            "a = Authority(JournalWriter2(d / 'j.jsonl', clock=lambda: 0.0), PROJECTIONS.values())\n"
            "from aisef2.arch.enums import EventType as T\n"
            "try:\n"
            "    a.append(T.RUN_BEGIN, {'journal_format': 'aisef-v2-journal/2', 'run_id': 'x'})\n"
            "    raise SystemExit('append passed unarmed')\n"
            "except InvariantError:\n"
            "    pass\n"
            "reg.arm_runtime()\n"
            "reg.require_armed(InvariantId.VI)\n"
            "try:\n"
            "    a.append(T.RUN_BEGIN, {'journal_format': 'aisef-v2-journal/2', 'run_id': 'x'})\n"
            "except InvariantError:\n"
            "    raise SystemExit('append still refused after arming')\n"
            "except Exception:\n"
            "    pass    # past the guard: whatever the payload validation says is not the arming's subject\n"
            "print('ARMED-AND-OPEN')\n"
        )
        p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        self.assertEqual((p.returncode, p.stdout.strip()[-14:]), (0, "ARMED-AND-OPEN"), p.stderr[-2000:])

    def test_a_registry_that_does_not_register_arms_nothing(self):
        before = reg.arm_runtime()
        with self.assertRaises(reg.RegistrationError):
            reg.register_runtime(registry=reg.REGISTRY[1:])     # not exactly I..IX
        with self.assertRaises(reg.RegistrationError):
            reg.arm_runtime(registry=reg.REGISTRY[:-1])
        self.assertEqual(reg.arm_runtime(), before)             # the failed arm changed nothing


class VerifyRederives(unittest.TestCase):
    def setUp(self):
        reg.arm_runtime()
        self.armed = reg.arm_runtime()
        self.rec = {"kernel_digest": R.kernel_digest(),
                    "invariants": {"armed": sorted(i.value for i in InvariantId),
                                   "registry_digest": self.armed.registry_digest,
                                   "code_mechanism_digest": self.armed.code_mechanism_digest,
                                   "statement": reg.RUNTIME_STATEMENT}}

    def test_a_faithful_record_re_derives_clean(self):
        self.assertEqual(_invariant_problems(self.rec), ([], []))

    def test_a_forged_digest_is_a_problem_on_the_same_kernel(self):
        for field in ("registry_digest", "code_mechanism_digest"):
            rec = {**self.rec, "invariants": {**self.rec["invariants"], field: "0" * 64}}
            problems, said = _invariant_problems(rec)
            self.assertEqual(len(problems), 1, (field, problems))
            self.assertIn("is not this kernel's", problems[0])
            self.assertEqual(said, [])

    def test_an_absent_field_is_an_earlier_release_and_another_kernel_is_not_compared(self):
        problems, said = _invariant_problems({"kernel_digest": R.kernel_digest()})
        self.assertEqual(problems, [])
        self.assertIn("a run of a release before", said[0])
        problems, said = _invariant_problems({**self.rec, "kernel_digest": "f" * 64})
        self.assertEqual(problems, [])
        self.assertIn("not compared", said[0])


if __name__ == "__main__":
    unittest.main()
