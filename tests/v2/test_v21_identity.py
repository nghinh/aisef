"""V2.1 (A, B — ARCHITECTURE-EXCEPTION-V2-007): the probe's three identities, the `.pth` channel closed, and the
migration of a 2.0.0 bundle.

* A spec binds the probe's CAPABILITY (id, CAPABILITY_VERSION, classes); a calibration row and the run's RunSpec bind
  the EXECUTION_DIGEST (the bytes that run). A byte change therefore needs its calibrations demonstrated again — the
  shipped rows must name every class of every active probe at its current bytes — but no approval and no plan change.
* The 2.0.0 channel (360° security W1, measured): developer tests and the probes shared `<out>/probe-python`; a `.pth`
  that test code wrote into its site-packages ran in every later probe controller (`-I` does not disable `site`).
  Now the probes run on this kernel's interpreter with `-I -S`, the tests on their own venv. Not a sandbox: test code
  runs as the operator's user and can still change that interpreter or the installed kernel (V2-05 is the sandbox).
* `aisef bundle migrate` re-binds the 2.0.0 LedgerLock bundle — 59 specs, 67 obligations — without re-approval, and it
  is then admitted under this release; the unmigrated bundle is refused naming the command.
Offline; the probes run on committed calibration fixtures."""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.calibrations import CALIBRATIONS  # noqa: E402
from aisef2.arch.enums import Enforcement  # noqa: E402
from aisef2.plan.obligation import Plan  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import process_effect as pe  # noqa: E402
from aisef2.probe import python_callable as pc1  # noqa: E402
from aisef2.probe import python_callable_v2 as pc2  # noqa: E402
from aisef2.probe.calibration import calibration_env, executing, fixture_spec  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402

LEDGERLOCK_2_0_0 = ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json"
FIXTURE = ROOT / "tests/v2/fixtures/calibration/python_callable_v2/returns/positive"


class ThreeIdentities(unittest.TestCase):
    def test_a_spec_binds_the_capability_and_the_bytes_are_their_own_digest(self):
        for e in catalog.CATALOG:
            if not e.active:
                continue
            mod = sys.modules[e.factory.__module__]
            with self.subTest(e.probe_id):
                want = hashlib.sha256(json.dumps([e.probe_id, mod.CAPABILITY_VERSION, list(e.classes)]).encode()).hexdigest()
                self.assertEqual(e.probe_digest, want)
                self.assertEqual(executing(e.factory), mod._probe_digest())
                self.assertNotEqual(executing(e.factory), e.probe_digest)

    def test_the_cycle1_probe_keeps_its_one_frozen_digest(self):
        self.assertEqual(pc1.DIGEST, "1961e84d913edc687bdb52f6c6cd0f034e86f2d1dadd9e89fa76757a51dc35bf")
        self.assertEqual(executing(pc1.PythonCallableProbe), pc1.DIGEST)

    def test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now(self):
        have = {(r["probe_id"], r["probe_digest"], r["observation_class"]) for r in CALIBRATIONS}
        for e in catalog.CATALOG:
            if e.active:
                for cls in e.classes:
                    self.assertIn((e.probe_id, executing(e.factory), cls), have,
                                  "a probe's bytes changed: run validation/qualification/release_calibration.py --write")

    def test_calibrations_of_other_bytes_admit_nothing(self):
        stale = tuple(dict(r, probe_digest="0" * 64) for r in CALIBRATIONS)
        project = bundle.load(bundle_cli.migrate(json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8")))[0])
        self.assertTrue(R.admit(project, R.calibrations())["admitted"])
        a = R.admit(project, R.calibrations(stale))
        self.assertFalse(a["admitted"])
        self.assertEqual([f["check"] for f in a["failed"]], ["9. probe_calibration"])
        self.assertIn("executing", a["failed"][0]["problems"][0])

    def test_the_runspec_binds_each_probe_s_bytes(self):
        from aisef2.app import adapters as ad
        from aisef2.app import preflight, settings
        from aisef2.runtime.capability import digest_of
        from tests.v2 import test_app_run as e2e
        with tempfile.TemporaryDirectory() as t:
            p, st = bundle.load(e2e.project_bundle("a" * 40)), settings.load(e2e.SETTINGS)
            pre = preflight.run(e2e.ROUTE, 2, e2e.provider(), pathlib.Path(t) / "pre")
            spec = R.runspec_of(p, st, pre, "client-x", sys.executable, ad.NoScanner())
        caps = {c.name: c for c in spec.capabilities}
        for e in catalog.CATALOG:
            if e.active:
                self.assertEqual(caps[e.probe_id].tuple_["digest"], digest_of(executing(e.factory).encode()))
        self.assertEqual(caps["python"].tuple_["digest"], digest_of(pathlib.Path(sys.executable)))


@unittest.skipUnless(os.name == "posix", "the venv layout and the marker are POSIX here")
class PthChannel(unittest.TestCase):
    """The reproducer: a `.pth` in an interpreter's site-packages runs under `-I`, never under `-S`; every launch of
    an active probe carries `-S`; and a probe evaluation on an interpreter holding such a file never runs it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.python = R.probe_interpreter(self.tmp / "venv")
        site = subprocess.run([self.python, "-I", "-c", "import site; print(site.getsitepackages()[0])"],
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
        self.marker = self.tmp / "pth-ran"
        pathlib.Path(site, "zz_inject.pth").write_text(
            f"import pathlib; pathlib.Path({str(self.marker)!r}).write_text('ran')\n", encoding="utf-8")

    def test_the_mechanism_minus_I_runs_it_minus_S_does_not(self):
        subprocess.run([self.python, "-I", "-S", "-B", "-c", "pass"], check=True)     # first, so nothing is deleted
        self.assertFalse(self.marker.exists())
        subprocess.run([self.python, "-I", "-B", "-c", "pass"], check=True)
        self.assertTrue(self.marker.exists(), "2.0.0's controller flags (-I -B) run the .pth")

    def test_every_active_probe_launch_carries_minus_S(self):
        for mod in (ci, pc2, pe):
            with self.subTest(mod.PROBE_ID):
                src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
                self.assertNotIn('"-I", "-B"', src)                    # no launch without -S: controller, agent, subject
                self.assertGreaterEqual(src.count('"-I", "-S", "-B"'), 2)
                self.assertEqual(mod._harness_argv("/py", "/a", "/c")[1:4], ["-I", "-S", "-B"])

    def test_a_probe_on_an_interpreter_holding_a_pth_never_runs_it(self):
        probe = pc2.PythonCallableV2Probe()
        spec = fixture_spec(probe, FIXTURE)
        at = RevisionRef("0" * 40, str((FIXTURE / "checkout").resolve()))
        rec = run_probe(probe, spec, at, ExecutionEnv(self.python, 30.0, Enforcement.PARTIAL))
        self.assertFalse(self.marker.exists(), "the probe's controller, agent or subject ran the injected .pth")
        self.assertEqual(rec.result.behavior_verdict.value, "SATISFIED", rec)

    def test_the_run_gives_the_probes_this_interpreter_and_the_tests_their_own(self):
        self.assertEqual(calibration_env(sys.executable).interpreter, sys.executable)
        src = (ROOT / "aisef2/app/run.py").read_text(encoding="utf-8")
        self.assertIn('env = ExecutionEnv(sys.executable, settings.timeouts_s["probe"]', src)
        self.assertIn("test_interpreter=python)", src)
        self.assertIn('python = probe_interpreter(out / "test-python")', src)


class Migrate(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8"))

    def test_the_2_0_0_bundle_is_refused_naming_the_command(self):
        with self.assertRaises(bundle.BundleError) as c:
            bundle.load(self.doc)
        self.assertIn("aisef bundle migrate", str(c.exception))

    def test_migration_rebinds_the_plan_and_nothing_else(self):
        out, report = bundle_cli.migrate(self.doc)
        self.assertEqual((report["specs_rebound"], report["obligations"]), (59, 67))
        self.assertEqual({v["from_release"] for v in report["mapping"].values()}, {"2.0.0"})
        for k in ("requirements", "contracts", "approvals", "facts", "stories", "requirements_document", "name"):
            self.assertEqual(out[k], self.doc[k], k)
        project = bundle.load(out)
        self.assertEqual(len(project.specs), 59)
        again, report2 = bundle_cli.migrate(out)
        self.assertEqual((again, report2["specs_rebound"]), (out, 0))     # idempotent

    def test_a_spec_no_release_compiles_is_refused_not_guessed(self):
        plan = bundle._plan(self.doc["plan"])       # a sealed plan whose first obligation names an unknown spec
        obligations = (dataclasses.replace(plan.obligations[0], product_proof_spec_id="PPS-" + "f" * 64), *plan.obligations[1:])
        doc = {**self.doc, "plan": plain(Plan.create(id=plan.id, baseline=plan.baseline, obligations=obligations,
                                                     plan_quality_policy=plan.plan_quality_policy))}
        with self.assertRaises(bundle_cli.MigrationError) as c:
            bundle_cli.migrate(doc)
        self.assertIn(plan.obligations[0].criterion_id, str(c.exception))
        doc = json.loads(json.dumps(self.doc))
        doc["contracts"] = doc["contracts"][1:]     # a spec whose contract left the bundle
        with self.assertRaises(bundle.BundleError):
            bundle_cli.migrate(doc)

    def test_the_command_writes_a_new_file_and_never_the_input(self):
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t) / "migrated.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bundle_cli.main(["migrate", str(LEDGERLOCK_2_0_0), "--out", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["approvals"], self.doc["approvals"])
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(bundle_cli.main(["migrate", str(LEDGERLOCK_2_0_0), "--out", str(out)]), 2)
                self.assertEqual(bundle_cli.main(["migrate", str(pathlib.Path(t) / "none.json"), "--out",
                                                  str(pathlib.Path(t) / "x.json")]), 2)
            self.assertIn("never overwrites", err.getvalue())

    def test_the_write_is_exclusive_so_a_file_that_appears_after_the_check_is_never_replaced(self):
        # B-03c: the exists() check only refuses early; the create itself is exclusive (O_EXCL), so a file created
        # between the check and the write (here: the check made blind to it) is refused, never written over
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t) / "migrated.json"
            out.write_text("theirs", encoding="utf-8")
            real = pathlib.Path.exists
            err = io.StringIO()
            with mock.patch.object(pathlib.Path, "exists", autospec=True, side_effect=lambda p: p != out and real(p)), \
                    contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bundle_cli.main(["migrate", str(LEDGERLOCK_2_0_0), "--out", str(out)]), 2)
            self.assertEqual(out.read_text(encoding="utf-8"), "theirs")
            self.assertIn(f"{out} exists: the bundle tools write a new file and never overwrite one", err.getvalue())


if __name__ == "__main__":
    unittest.main()
