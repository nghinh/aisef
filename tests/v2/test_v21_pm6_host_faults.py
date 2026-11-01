"""B-03 round 5 (PM-6, the DEFECT part) — a host fault in the evaluation directory is a typed answer, and an argv no
process can carry is refused at admission.

Requirement. `aisef2/probe/protocol.py` ("Observation harness vs subject"): a fault of the observation harness before it
obtains an observation is UNRUNNABLE, owner ENVIRONMENT, and `observe` reports it as a typed Observation (the
`harness_preconditions` of every probe name the evaluation directory, which holds the harness log); a spec the probe
cannot give a class is UNSUPPORTED -> INVALID_SPEC at admission, never a default meaning (process_effect docstring,
"Stimulus"). Neither raises out of `observe` / `run_probe`, and neither is ever a verdict.

The fault is a real one: the evaluation directory is made, then a *directory* takes the path of the file the probe
writes there (`harness.log`, `request.json`), so the real `open()` / `write_text()` raise a real IsADirectoryError.
Nothing about `open` is patched; the controller of the control runs is a real process.
"""

import contextlib
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement, ProbeExecutionStatus, SubjectAbsence  # noqa: E402
from aisef2.probe import catalog, cli_invocation as ci, process_effect as pe, python_callable_v2 as pc2  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, Observation, ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

SHA = "89abcdef0123456789abcdef0123456789abcdef"
ENV = ExecutionEnv(sys.executable, 30, Enforcement.PARTIAL)
SUBJECT = "def main(argv=None):\n    return 0\n"


def _host_open_error() -> str:
    """The class `open(.., "wb")` raises when a *directory* holds the written file's path is the host's to name —
    IsADirectoryError on POSIX, PermissionError on Windows, the same (correct) refusal — and the probe's detail carries
    `type(e).__name__` verbatim. The expected class is therefore computed by provoking that exact fault once, so the
    equality assertions below pin the full typed answer on every OS instead of one OS's spelling."""
    with tempfile.TemporaryDirectory(prefix="aisef2-pm6-class-") as t:
        taken = os.path.join(t, "taken")
        os.mkdir(taken)
        try:
            open(taken, "wb").close()
        except OSError as e:
            return type(e).__name__
    raise AssertionError("opening a directory for writing did not fail on this host")


PREPARED = f"the evaluation directory cannot be prepared: {_host_open_error()}"


def _spec(probe, kind, locator, stimulus, observable):
    return ProductProofSpec.create(
        contract_id="BC-PM6", probe_id=probe.id, probe_digest=probe.digest,
        probe_input={"subject": {"kind": kind, "locator": locator}, "stimulus": stimulus, "observable": observable,
                     "subject_absence": SubjectAbsence.REQUIRES_SUBJECT.value},
        candidate_expectation=BehaviorVerdict.SATISFIED, compiler_id="test", compiler_digest="c" * 64)


def pe_spec(scenario, observable=None):
    return _spec(pe.ProcessEffectProbe, "process_effect", "cli:main", {"scenario": scenario},
                 observable or {"files": {"<ws>/a.txt": {"absent": True}}, "within_s": 20})


def ci_spec():
    return _spec(ci.CliInvocationProbe, "cli_invocation", "cli:main", {"argv": []}, {"exit_code": 0, "within_s": 20})


def pc2_spec():
    return _spec(pc2.PythonCallableV2Probe, "python_callable", "cli:main", {"args": [[]], "kwargs": {}},
                 {"returns": 0, "within_s": 20})


CASES = {   # name -> (module, probe class, spec builder)
    "process_effect": (pe, pe.ProcessEffectProbe, lambda: pe_spec([{"step": "call", "args": [], "kwargs": {}}])),
    "cli_invocation": (ci, ci.CliInvocationProbe, ci_spec),
    "python_callable_v2": (pc2, pc2.PythonCallableV2Probe, pc2_spec),
}


class _Checkout(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory(prefix="aisef2-pm6-")
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.root = self.tmp / "rev"
        self.root.mkdir()
        (self.root / "cli.py").write_text(SUBJECT, encoding="utf-8", newline="\n")
        self.at = RevisionRef(SHA, str(self.root))
        self.evaluations = self.tmp / "evaluations"     # where this test's evaluation directories are made
        self.evaluations.mkdir()
        self.addCleanup(setattr, tempfile, "tempdir", tempfile.tempdir)
        tempfile.tempdir = str(self.evaluations)

    def leftovers(self) -> list[str]:
        return sorted(os.listdir(self.evaluations))


@contextlib.contextmanager
def taken(module, *names):
    """Every evaluation directory `module` makes has a *directory* at each of `names` before the probe writes there."""
    real = module._evaluation_dir

    def make(scratch):
        holder = real(scratch)

        @contextlib.contextmanager
        def seeded():
            with holder as work:
                for name in names:
                    os.mkdir(os.path.join(work, name))
                yield work
        return seeded()
    with mock.patch.object(module, "_evaluation_dir", make):
        yield


class HostFaultInTheEvaluationDirectory(_Checkout):
    """PM-6: the harness log (and the request) belong to the evaluation directory: a fault there is HARNESS_FAILED."""

    def test_the_unfaulted_evaluation_runs_for_real(self):
        for name, (_module, cls, mk) in CASES.items():
            with self.subTest(probe=name):
                o = cls().observe(mk(), self.at, ENV)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, BehaviorVerdict.SATISFIED), o.detail)
                self.assertEqual(self.leftovers(), [])

    def test_a_harness_log_that_cannot_be_created_is_an_unrunnable_harness_and_nothing_runs(self):
        for name, (module, cls, mk) in CASES.items():
            for taken_name in ("harness.log", "request.json"):
                with self.subTest(probe=name, taken=taken_name), taken(module, taken_name), \
                        mock.patch.object(module, "ProcessRange", side_effect=AssertionError("a range was built")):
                    self.assertEqual(cls().observe(mk(), self.at, ENV), Observation(K.HARNESS_FAILED, detail=PREPARED))
                    result = run_probe(cls(), mk(), self.at, ENV).result
                    self.assertEqual((result.status, result.detail), (ProbeExecutionStatus.UNRUNNABLE, PREPARED))
                    self.assertEqual(self.leftovers(), [], "the evaluation directory is disposed")

    def test_both_files_taken_is_still_one_typed_answer(self):
        for name, (module, cls, mk) in CASES.items():
            with self.subTest(probe=name), taken(module, "request.json", "harness.log"), \
                    mock.patch.object(module, "ProcessRange", side_effect=AssertionError("a range was built")):
                self.assertEqual(cls().observe(mk(), self.at, ENV), Observation(K.HARNESS_FAILED, detail=PREPARED))


class ArgvNoProcessCanCarry(_Checkout):
    """PM-6: `subprocess.run` raises ValueError for a NUL in an argument, so the controller used to fail *after*
    admission and the plan-authoring error read as ENVIRONMENT (retryable). It is not a class: INVALID_SPEC."""

    @staticmethod
    def step(*tail):
        return {"step": "subprocess", "argv": ["-m", "cli", *tail]}

    def test_a_nul_in_any_argument_gives_the_spec_no_class(self):
        # the NUL in the first, a middle and the last argument after `-m <module>`, alone and among clean ones
        for tail in (("a\0b",), ("\0",), ("ok", "x\0"), ("<ws>/a\0",), ("a", "b", "c\0"), ("a\0b", "ok"),
                     ("x", "\0", "y"), ("\0", "ok", "fine"), ("ok", "\0", "ok", "also fine")):
            with self.subTest(tail=tail):
                step = self.step(*tail)
                self.assertIs(False, pe._step_ok(step))
                spec = pe_spec([step])
                self.assertIsNone(pe.spec_class(spec))
                self.assertIsNone(catalog.registry().observation_class(spec.probe_id, spec.probe_digest, spec))
                with mock.patch.object(pe, "ProcessRange", side_effect=AssertionError("a range was built")):
                    o = pe.ProcessEffectProbe().observe(spec, self.at, ENV)
                    self.assertEqual(o.kind, K.UNSUPPORTED)
                    self.assertIn("refused, not degraded", o.detail)
                    self.assertEqual(run_probe(pe.ProcessEffectProbe(), spec, self.at, ENV).result.status,
                                     ProbeExecutionStatus.INVALID_SPEC)

    def test_every_other_argument_a_process_can_carry_is_still_admitted(self):
        for tail in (("a b",), ("\t",), ("a\nb",), ("é",), ("",), ("a\\0b",), ("\\x00",), ("<ws>/a.txt",), ("-x", "--y=1")):
            with self.subTest(tail=tail):
                self.assertIs(True, pe._step_ok(self.step(*tail)))
                self.assertEqual(pe.spec_class(pe_spec([self.step(*tail)])), "scenario_files")

    def test_a_real_child_receives_an_argument_with_a_backslash_and_a_zero(self):
        """The refusal is of the NUL byte, not of the two characters: the child runs and exits 0 under its window."""
        (self.root / "echo.py").write_text("import sys\nsys.exit(0 if sys.argv[1:] == ['a\\\\0b'] else 3)\n", encoding="utf-8")
        spec = pe_spec([{"step": "subprocess", "argv": ["-m", "echo", "a\\0b"]}])
        o = pe.ProcessEffectProbe().observe(spec, self.at, ENV)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, BehaviorVerdict.SATISFIED), o.detail)


if __name__ == "__main__":
    unittest.main()
