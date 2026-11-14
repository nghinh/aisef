"""ROADMAP-2.2 A1 — runtime arming: the nine invariants are registered and armed in the RUNNING process, not only
in the test tiers. `register_runtime` resolves every CODE mechanism (importable from an installed kernel: the
static-rule/checker/tier/document checks are the development tier's and stay in `register`), `arm_runtime` marks the
process armed, and `require_armed` passes for either kind of arming. A clean process is unarmed and its journal
choke points fail closed. `verify` re-derives the recorded digests against its own kernel — same kernel only."""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

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
        with self.assertRaisesRegex(reg.RegistrationError, "^the registry holds exactly I..IX in order"):
            reg.register_runtime(registry=reg.REGISTRY[1:])     # not exactly I..IX
        with self.assertRaisesRegex(reg.RegistrationError, "^the registry holds exactly I..IX in order"):
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

    def test_a_malformed_digest_fails_closed_on_any_kernel(self):
        # Lane B-A: a digest that is not a 64-hex sha256 is malformed provenance — a problem even when the
        # verifying kernel is NOT the run's (the old code excused it as "not compared"), and never a mere note.
        for bad in (None, "", "a" * 63, "A" * 64, 123):
            for field in ("registry_digest", "code_mechanism_digest"):
                for kernel in (R.kernel_digest(), "f" * 64):
                    rec = {**self.rec, "kernel_digest": kernel,
                           "invariants": {**self.rec["invariants"], field: bad}}
                    problems, said = _invariant_problems(rec)
                    self.assertEqual(len(problems), 1, (field, bad, kernel, problems))
                    self.assertIn("is not a 64-hex sha256", problems[0])
                    self.assertEqual(said, [])

    def test_an_invariants_object_missing_a_digest_field_is_malformed(self):
        rec = {**self.rec, "invariants": {k: v for k, v in self.rec["invariants"].items()
                                          if k != "registry_digest"}}
        problems, said = _invariant_problems(rec)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("registry_digest is not a 64-hex sha256: None", problems[0])
        self.assertEqual(said, [])

    def test_an_absent_field_is_an_earlier_release_and_another_kernel_is_not_compared(self):
        problems, said = _invariant_problems({"kernel_digest": R.kernel_digest()})
        self.assertEqual(problems, [])
        self.assertIn("a run of a release before", said[0])
        problems, said = _invariant_problems({**self.rec, "kernel_digest": "f" * 64})
        self.assertEqual(problems, [])
        self.assertIn("not compared", said[0])


class B1SurvivorKills(unittest.TestCase):
    """Release gate B1 mutation-survivor kills: pin the digest values and preimage format, drive the fail-closed
    error paths of `runtime_mechanism_digest`, and pin which mechanism kinds `register_runtime` resolves."""

    # --------------------------------------------------------------------------- runtime_mechanism_digest

    def test_the_runtime_digest_is_64_hex_and_recomputes_from_the_imported_module_bytes(self):
        """Independent recomputation: sha256 over '\\n'-joined `id ref sha256(module bytes, CRLF-normalized)`
        lines of every CODE mechanism (registry order, then UNCONTAINABLE) — pins the preimage format."""
        digest = reg.runtime_mechanism_digest()
        self.assertRegex(digest, r"\A[0-9a-f]{64}\Z")
        lines = []
        for m in [m for i in reg.REGISTRY for m in i.mechanisms] + list(reg.UNCONTAINABLE):
            if m.kind is not reg.MechanismKind.CODE:
                continue
            content = Path(importlib.import_module(m.ref.partition(":")[0]).__file__).read_bytes()
            content = content.replace(b"\r\n", b"\n")
            lines.append(f"{m.id} {m.ref} {hashlib.sha256(content).hexdigest()}")
        self.assertEqual(digest, hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest())

    def _digesting(self, mechanism: reg.Mechanism) -> tuple:
        """A one-invariant registry carrying `mechanism` (the digest iterates; it does not validate ids)."""
        return (dataclasses.replace(reg.REGISTRY[0], mechanisms=(mechanism,)),)

    def _fake_module(self, name: str, file: object) -> None:
        module = types.ModuleType(name)
        module.__file__ = file
        sys.modules[name] = module
        self.addCleanup(sys.modules.pop, name, None)

    def test_a_code_module_that_does_not_import_refuses_as_registration_error(self):
        m = reg.Mechanism("x", reg.MechanismKind.CODE, "aisef2.__no_such_module__:f", "r")
        with self.assertRaises(reg.RegistrationError):
            reg.runtime_mechanism_digest(self._digesting(m))

    def test_a_code_module_without_file_refuses_as_registration_error(self):
        m = reg.Mechanism("x", reg.MechanismKind.CODE, "sys:f", "r")    # builtin: no __file__
        with self.assertRaises(reg.RegistrationError):
            reg.runtime_mechanism_digest(self._digesting(m))

    def test_a_code_module_whose_file_is_none_refuses_as_registration_error(self):
        self._fake_module("aisef_b1_filenone_mod", None)                # namespace-package shape
        m = reg.Mechanism("x", reg.MechanismKind.CODE, "aisef_b1_filenone_mod:f", "r")
        with self.assertRaises(reg.RegistrationError):
            reg.runtime_mechanism_digest(self._digesting(m))

    def test_a_code_module_whose_file_is_unreadable_refuses_as_registration_error(self):
        self._fake_module("aisef_b1_gonefile_mod", str(ROOT / "no-such-dir" / "gone.py"))
        m = reg.Mechanism("x", reg.MechanismKind.CODE, "aisef_b1_gonefile_mod:f", "r")
        with self.assertRaises(reg.RegistrationError):
            reg.runtime_mechanism_digest(self._digesting(m))

    # --------------------------------------------------------------------------------------- registry_digest

    #: regenerate only on a deliberate registry change:
    #: PYTHONPATH=. python3 -P -c "from aisef2.invariants.registry import registry_digest; print(registry_digest())"
    REGISTRY_DIGEST_GOLDEN = "a5ef12d7009538d5e7d3b3ae98ea70934d2aede284a0b118b1be4bcc4162d7f3"

    def test_the_registry_digest_is_the_frozen_golden_value(self):
        """One pinned constant: any drift in field coverage, tuple shapes, the uncontainable row or its label —
        the value persisted in every RUN.json and compared by verify — lands here."""
        self.assertEqual(reg.registry_digest(), self.REGISTRY_DIGEST_GOLDEN)

    # --------------------------------------------------------------------------------------------- verify

    def test_a_non_object_invariants_field_is_the_one_typed_problem(self):
        self.assertEqual(_invariant_problems({"invariants": []}),
                         (["RUN.json's invariants field is not an object"], []))

    # ------------------------------------------------------------------------------------- register_runtime

    def test_register_runtime_resolves_the_registry_s_code_mechanisms(self):
        """A CODE ref whose module imports but whose attribute resolves nowhere is refused — the digest alone
        (module bytes) would not see it, so the per-invariant loop must resolve CODE mechanisms."""
        i0 = reg.REGISTRY[0]
        m0 = dataclasses.replace(i0.mechanisms[0], ref="aisef2.product.approval:no_such_name")
        bad = (dataclasses.replace(i0, mechanisms=(m0,) + i0.mechanisms[1:]),) + reg.REGISTRY[1:]
        with self.assertRaisesRegex(reg.RegistrationError, "resolves nowhere"):
            reg.register_runtime(bad)

    def test_register_runtime_resolves_the_uncontainable_code_mechanisms(self):
        u = (reg.Mechanism("u", reg.MechanismKind.CODE, "aisef2.errors:NoSuchAttr", ""),)
        with mock.patch.object(reg, "UNCONTAINABLE", u):
            with self.assertRaisesRegex(reg.RegistrationError, "resolves nowhere"):
                reg.register_runtime()

    def test_a_containable_invariant_error_is_refused_at_runtime_registration(self):
        class Containable(Exception):
            pass
        with mock.patch.object(reg, "InvariantError", Containable):
            with self.assertRaisesRegex(reg.RegistrationError, "must derive from BaseException"):
                reg.register_runtime()


if __name__ == "__main__":
    unittest.main()
