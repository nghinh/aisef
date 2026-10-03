"""WP-2.3.1 — the bytecode family (P7-FINDING-001) re-run against the `process_effect` probe: FM2-PYC-EFFECT-1..5.

The offending state is built deterministically, as tests/v2/test_p7_finding_001.py builds it: `app/mod.py` holds
SOURCE_B beside `app/__pycache__/mod.<tag>.pyc` compiled from SOURCE_A, the bytecode's header matching the source's
size and whole-second mtime, so CPython would take the stale code if it looked in the tree. Every verdict is read from
the real probe on a real checkout: the scenario's call (in the harness process) and its subprocess step (a child with
its own fresh prefix) observe the source, never the stale bytecode. FM2-PYC-2 (P7-FINDING-001 case 2, two checkouts
of the same content with different dates) is in tests/v2/test_probe_process_effect.py and uses this construction.
"""

import importlib.util
import os
import pathlib
import py_compile
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement, SubjectAbsence  # noqa: E402
from aisef2.probe import process_effect as pe  # noqa: E402
from aisef2.probe.process_effect import ProcessEffectProbe  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
#: the source the stale bytecode was compiled from, and the revision's source: same size, one character apart
SOURCE_A = "import sys\n\n\ndef value():\n    return 1\n\n\nif __name__ == \"__main__\":\n    sys.exit(value())\n"
SOURCE_B = SOURCE_A.replace("return 1", "return 2")
assert len(SOURCE_A) == len(SOURCE_B)
RETURNS_2, RETURNS_1 = {"returns": 2, "within_s": 20}, {"returns": 1, "within_s": 20}
CALL = [{"step": "call", "args": [], "kwargs": {}}]
#: the module run as __main__ by a subprocess step: its exit status is the value it computes
SUB_EXITS_2 = [{"step": "subprocess", "argv": ["-m", "app.mod"], "expect_exit": 2}, *CALL]


def value_spec(observable, scenario=CALL, *, expectation=S):
    return ProductProofSpec.create(
        contract_id="BC-PYC-EFFECT", probe_id=pe.PROBE_ID, probe_digest=pe.DIGEST,
        probe_input={"subject": {"kind": "process_effect", "locator": "app.mod:value"}, "stimulus": {"scenario": scenario},
                     "observable": observable, "subject_absence": SubjectAbsence.REQUIRES_SUBJECT.value},
        candidate_expectation=expectation, compiler_id="test", compiler_digest="c" * 64)


def stale_checkout(root: pathlib.Path, *, offset_s: int = 0, bytecode: bool = True) -> dict:
    """app/mod.py holding SOURCE_B beside app/__pycache__/mod.<tag>.pyc compiled from SOURCE_A, the header matching the
    source's size and (offset 0) its whole-second mtime."""
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    src = app / "mod.py"
    src.write_text(SOURCE_A, encoding="utf-8", newline="\n")
    cfile = importlib.util.cache_from_source(str(src))
    if bytecode:
        py_compile.compile(str(src), cfile=cfile, doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
    header = pathlib.Path(cfile).read_bytes()[:16] if bytecode else b"\0" * 16
    src.write_text(SOURCE_B, encoding="utf-8", newline="\n")
    second = int.from_bytes(header[8:12], "little")
    os.utime(src, (second + offset_s, second + offset_s))
    st = src.stat()
    return {"bytecode": cfile if bytecode else None,
            "collision": bytecode and second == int(st.st_mtime) & 0xFFFFFFFF
            and st.st_size == int.from_bytes(header[12:16], "little")}


def snapshot(root: pathlib.Path) -> dict:
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


def verdict(record):
    return record.result.behavior_verdict if isinstance(record.result, Executed) else record.result


def env():
    return ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)


class Bytecode(unittest.TestCase):
    def setUp(self):
        # holds controller-owned scratches: on Windows a member the job just ended can hold a handle for a moment
        # (C2-P2-FINDING-003); process leaks are the owned range's measurement, not this directory's
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-pyc-effect-", ignore_cleanup_errors=True)
        self.addCleanup(self._d.cleanup)
        self.tmp = pathlib.Path(self._d.name)
        self.root = self.tmp / "checkout"
        self.built = stale_checkout(self.root)
        self.assertTrue(self.built["collision"], self.built)
        self.at = RevisionRef("a" * 40, str(self.root))

    def observe(self, observable, scenario=CALL, *, probe=None, expectation=S):
        return run_probe(probe or ProcessEffectProbe(), value_spec(observable, scenario, expectation=expectation),
                         self.at, env())

    def test_FM2_PYC_EFFECT_1_in_tree_stale_bytecode_with_a_matching_header_is_never_the_subject(self):
        self.assertEqual(verdict(self.observe(RETURNS_2)), S)   # 2 is SOURCE_B's behaviour; the stale bytecode says 1
        self.assertEqual(verdict(self.observe(RETURNS_1, expectation=R)), R)
        other = self.tmp / "verifier"
        self.assertFalse(stale_checkout(other, offset_s=100)["collision"])
        b = run_probe(ProcessEffectProbe(), value_spec(RETURNS_2), RevisionRef("a" * 40, str(other)), env())
        self.assertEqual(verdict(b), S)

    def test_FM2_PYC_EFFECT_2_a_subprocess_step_observes_the_source_too(self):
        self.assertEqual(verdict(self.observe(RETURNS_2, SUB_EXITS_2)), S)
        stale = [{"step": "subprocess", "argv": ["-m", "app.mod"], "expect_exit": 1}, *CALL]
        self.assertEqual(verdict(self.observe(RETURNS_2, stale)), R)   # the child ran the source: exit 2, not 1

    def test_FM2_PYC_EFFECT_3_the_probe_writes_no_bytecode_into_the_checkout(self):
        before = snapshot(self.root)
        self.assertEqual(verdict(self.observe(RETURNS_2, SUB_EXITS_2)), S)
        self.assertEqual(snapshot(self.root), before)
        plain = self.tmp / "plain"
        stale_checkout(plain, bytecode=False)
        self.assertEqual(verdict(run_probe(ProcessEffectProbe(), value_spec(RETURNS_2, SUB_EXITS_2),
                                           RevisionRef("a" * 40, str(plain)), env())), S)
        self.assertEqual(sorted(str(p.relative_to(plain)) for p in plain.rglob("*.pyc")), [])

    def test_FM2_PYC_EFFECT_4_the_cache_is_fresh_empty_outside_the_checkout_and_distinct_per_evaluation(self):
        seen = []
        real_start = pe.ProcessRange.start

        def start(run):
            argv = run._argv
            prefix = argv[argv.index("-X") + 1].removeprefix("pycache_prefix=")
            seen.append((prefix, os.listdir(prefix) == [], pe._inside(prefix, str(self.root)), argv[1:4]))
            return real_start(run)
        scratch = self.tmp / "scratch"
        scratch.mkdir()
        with mock.patch.object(pe.ProcessRange, "start", start):
            self.assertEqual(verdict(self.observe(RETURNS_2)), S)
            for _ in ("implementer", "verifier"):
                self.assertEqual(verdict(self.observe(RETURNS_2, SUB_EXITS_2,
                                                      probe=ProcessEffectProbe(scratch=str(scratch)))), S)
        self.assertEqual(len({p for p, *_ in seen}), 3)
        self.assertEqual([(empty, inside, flags) for _, empty, inside, flags in seen], [(True, False, ["-I", "-B", "-X"])] * 3)
        self.assertFalse(pathlib.Path(seen[0][0]).exists())   # the probe's own temporary directory: gone
        self.assertEqual({pathlib.Path(p).parent.parent for p, *_ in seen[1:]}, {scratch})
        # each subprocess step had a fresh prefix of its own in the evaluation directory; -B: nothing written
        self.assertEqual(sorted(p.name for p in scratch.glob("*/pycache-step*")), ["pycache-step0", "pycache-step0"])
        self.assertEqual(sorted(scratch.rglob("*.pyc")), [])

    def test_FM2_PYC_EFFECT_5_without_the_external_cache_the_stale_bytecode_decides_the_reproducer_detects_it(self):
        # B1: the subject is imported in its own process (the shared agent): the controls are on its command line
        flags = '"-I", "-B", "-X", "pycache_prefix=" + req["agent_pycache"], '
        self.assertEqual(pe.HARNESS.count(flags), 1)
        for keep_b in (True, False):
            harness = pe.HARNESS.replace(flags, '"-I", ' + ('"-B", ' if keep_b else ""))
            with self.subTest(keep_b=keep_b), mock.patch.object(pe, "HARNESS", harness):
                self.assertEqual(verdict(self.observe(RETURNS_2)), R)   # the stale code's 1, not the source's 2
                self.assertEqual(verdict(self.observe(RETURNS_1, expectation=R)), S)
        # without -B the subject's bytecode lands under the prefix, never in the checkout
        scratch = self.tmp / "scratch"
        scratch.mkdir()
        before = snapshot(self.root)
        with mock.patch.object(pe, "HARNESS", pe.HARNESS.replace(flags, '"-I", "-X", "pycache_prefix=" + req["agent_pycache"], ')):
            self.assertEqual(verdict(self.observe(RETURNS_2, probe=ProcessEffectProbe(scratch=str(scratch)))), S)
        self.assertEqual(snapshot(self.root), before)
        self.assertTrue(any(p.name.startswith("mod.") for p in scratch.rglob("*.pyc")))


if __name__ == "__main__":
    unittest.main()
