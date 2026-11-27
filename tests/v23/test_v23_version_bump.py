"""L1-QUAL (W1-DESIGN §3, §9 N11/N12/N34; CODE-AUDIT #3 EVID-COUPLING-01, #40).

EVID-COUPLING-01: `release_calibration.RECORD_REL` followed pyproject's version (`newest_rel(_version())[0]`), so a
code-identical version bump named a record that does not exist; the consumers `p5_acceptance.reverify` (both rounds),
`v21_conformance_ruling.derive` and `q2` went red with it. The record is now resolved by input identity (`resolve()`),
not by the version string. Since the v2.3 round owns 2.3.0.dev0 (ROUND_VERSION) and ships its own
V2.3.0.dev0-PROBE-CALIBRATIONS.json, the bump that exercises this property is one ABOVE the round ceiling (2.4.0): no
record is named for it, so resolution falls by identity to the newest existing record — the round's V2.3.0.dev0 record,
VERIFIED_REUSE (16 of 19 rows carried from V2.2.0), never MEASURED. Every consumer gives what it gives without the bump,
the M5 tests pass and `calibrations.py` is not touched (N11); the bump plus one changed fixture byte is INVALIDATED and
every consumer fails naming that reason (N12); the current round version resolves the same record, never MEASURED (N34).
Every version-keyed reader of the calibration record is enumerated here, so a new one cannot appear unchecked.

#40: `reverify()` dereferenced the 2.0 records with no None guard; a missing record raised TypeError (red-before,
measured on the base code). It now returns PROBLEMS naming the missing record, as `history_problems()` does.
Evidence: docs/v2.3/evidence/l1-qual/README.md.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v23.test_v23_calibration_rows import NEG, V220, V230, data_clone  # noqa: E402
from validation.qualification import common as C  # noqa: E402
from validation.qualification import p5_acceptance as A  # noqa: E402
from validation.qualification import q2  # noqa: E402
from validation.qualification import release_calibration as rc  # noqa: E402
from validation.qualification import v21_conformance_ruling as CR  # noqa: E402

BUMP = "2.4.0"   # a bump ABOVE the round ceiling (2.3.0.dev0 owns a record): names no record, so resolution is by identity
#: the unit tests a version-only bump turned red (W1-DESIGN M5; measured red-before on the base code)
M5 = ("tests.v2.test_c2_p5_acceptance.V21Records.test_each_re_verification_check_refuses_for_its_own_reason",
      "tests.v2.test_c2_p5_acceptance.V21Records.test_the_committed_re_verification_is_current_only_exactly_with_every_guard_run",
      "tests.v2.test_qualification_release_mode.Subject.test_release_q2_reads_the_calibrations_the_rc_ships")
#: every reader of the record's location or state outside release_calibration.py itself (production code)
CONSUMERS = {"validation/qualification/p5_acceptance.py", "validation/qualification/q2.py",
             "validation/qualification/v21_conformance_ruling.py"}


def _sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def _v23_basis() -> str:
    """The VERIFIED_REUSE basis the tree's committed V2.3.0.dev0 record resolves with (measured_on read from it)."""
    m = json.loads((ROOT / V230).read_text(encoding="utf-8"))["identity"]["measured_on"]
    return f"v2.3-measured@{m}; 16 of 19 rows carried from {V220} by identical inputs"


@contextlib.contextmanager
def imported_as(resolved: tuple[str, str, str]):
    """What importing release_calibration and q2 binds when resolve() gives `resolved` (both are module constants)."""
    with mock.patch.multiple(rc, RECORD_REL=resolved[0], STATE=resolved[1], BASIS=resolved[2]), \
            mock.patch.object(q2, "RELEASE_CALIBRATION_RECORDS", (resolved[0],)):
        yield


def run(names) -> unittest.TestResult:
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    assert result.testsRun == len(names), result.testsRun
    return result


class Bump(unittest.TestCase):
    def test_N11_a_scratch_pyproject_bump_resolves_by_identity_to_the_record_already_cited(self):
        with tempfile.TemporaryDirectory() as tmp:
            scratch = pathlib.Path(tmp) / "pyproject.toml"
            text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
            scratch.write_text(re.sub(r'(?m)^version = "[^"]+"$', f'version = "{BUMP}"', text, count=1), encoding="utf-8")
            version = rc._version(scratch)
        self.assertEqual(version, BUMP)
        self.assertFalse((ROOT / rc.newest_rel(version)[0]).exists())          # a bump above the round: no record named for it
        self.assertEqual(rc.resolve(version), (V230, "VERIFIED_REUSE", _v23_basis()))  # falls by identity to the round's record

    def test_N11_the_import_time_binding_under_the_bump(self):
        code = ("import json, sys, tomllib\nreal = tomllib.loads\n"
                "def loads(s, **k):\n    d = real(s, **k)\n    d['project']['version'] = %r\n    return d\n"
                "tomllib.loads = loads\nsys.path.insert(0, %r)\n"
                "from validation.qualification import release_calibration as rc, q2\n"
                "print(json.dumps([rc._version(), rc.RECORD_REL, rc.STATE, rc.BASIS, list(q2.RELEASE_CALIBRATION_RECORDS)]))\n"
                % (BUMP, str(ROOT)))
        out = subprocess.run([sys.executable, "-P", "-c", code], capture_output=True, encoding="utf-8", check=True, cwd=ROOT).stdout
        self.assertEqual(json.loads(out), [BUMP, V230, "VERIFIED_REUSE", _v23_basis(), [V230]])

    def test_N11_every_consumer_and_the_M5_tests_are_unmoved_by_the_bump_and_calibrations_py_is_untouched(self):
        shipped = _sha(rc.SHIPPED_REL)
        before = {r: A.reverify(run_guards=False, round=r) for r in ("v2.1", "v2.2")}
        ruling = CR.check_version_forward()
        with mock.patch.object(C, "MODE", "release"):
            keys = q2._committed_calibration_keys()
        with imported_as(rc.resolve(BUMP)):
            self.assertEqual({r: A.reverify(run_guards=False, round=r) for r in ("v2.1", "v2.2")}, before)
            self.assertEqual(CR.check_version_forward(), ruling)
            with mock.patch.object(C, "MODE", "release"):
                self.assertEqual(q2._committed_calibration_keys(), keys)
            result = run(M5)
            self.assertTrue(result.wasSuccessful(), [t for _, t in result.failures + result.errors])
        self.assertEqual(_sha(rc.SHIPPED_REL), shipped)

    def test_N12_the_bump_and_one_fixture_byte_invalidate_and_every_consumer_fails_for_that_reason(self):
        with data_clone() as t:
            with open(t / NEG, "ab") as f:
                f.write(b"#")
            resolved = rc.resolve(BUMP)
        self.assertEqual(resolved[:2], (V230, "INVALIDATED"))
        reason = f"{V230}: INVALIDATED — {resolved[2]}"
        self.assertIn("probe.file_artifact exists: the negative fixture tree is not the record's", reason)
        with imported_as(resolved):
            for r in ("v2.1", "v2.2"):
                self.assertIn(reason, A.reverify(run_guards=False, round=r)["problems"])
            # On a tree whose kernel moved past the v2.2 record (E5), the v2.2-ambient consumer refuses one step
            # earlier, at supersession resolution — still never a silent pass, which is what N12 proves.
            rev = A.reverification_v22_problems()
            self.assertTrue(rev, "reverification_v22_problems passed under an invalidated calibration")
            self.assertTrue(reason in rev or any("missing supersession" in p for p in rev), rev)
            crp = CR.check_version_forward()
            self.assertTrue(crp, "check_version_forward passed under an invalidated calibration")
            self.assertTrue(reason in crp or any("missing supersession" in p for p in crp), crp)
            with mock.patch.object(C, "MODE", "release"):
                q2p = q2._calibration_cycle2()["problems"]
                self.assertTrue(q2p, "_calibration_cycle2 passed under an invalidated calibration")
                self.assertTrue(reason in q2p or any("missing supersession" in p for p in q2p), q2p)
                self.assertTrue(q2._committed_calibration_keys().isdisjoint(r[:3] for r in rc.derived_rows()))  # no key from it
            result = run(M5)
        failed = {t.id(): trace for t, trace in result.failures + result.errors}
        self.assertEqual(set(failed), set(M5))
        for name in M5[:2]:                                            # their problem lists carry the fixture-tree reason
            self.assertIn("negative fixture tree", failed[name], name)  # short slice: unittest's diff repr wraps the full phrase

    def test_N34_the_v2_2_era_record_named_by_the_current_version_is_never_measured(self):
        self.assertEqual(rc._version(), "2.2.0")                                # pyproject still trails the round
        self.assertEqual(rc.resolve(), (V230, "VERIFIED_REUSE", _v23_basis()))  # the round version resolves its own record
        self.assertNotEqual(rc.STATE, "MEASURED")

    def test_every_version_keyed_reader_of_the_record_is_enumerated_and_checks_its_state(self):
        reads = re.compile(r"\b(?:rc|release_calibration)\.(RECORD_REL|newest_rel|record_rel|_version|resolve|STATE|BASIS)\b")
        found = set()
        for p in (q for top in ("aisef", "aisef2", "validation") for q in (ROOT / top).rglob("*.py")):
            rel = p.relative_to(ROOT).as_posix()
            text = p.read_text(encoding="utf-8", errors="replace")
            if rel != "validation/qualification/release_calibration.py" and "release_calibration" in text and reads.search(text):
                found.add(rel)
        self.assertEqual(found, CONSUMERS)
        for rel in sorted(CONSUMERS):
            self.assertIn("state_problems()", (ROOT / rel).read_text(encoding="utf-8"), rel)
        self.assertRegex((ROOT / "validation/qualification/release_calibration.py").read_text(encoding="utf-8"),
                         r"(?m)^RECORD_REL, STATE, BASIS = resolve\(\)$")


@contextlib.contextmanager
def absent(rel: str):
    """`rel` removed, as every reader in p5_acceptance sees it (is_file / exists / read_text / read_bytes)."""
    gone = (A.ROOT / rel).as_posix()
    real = {k: getattr(pathlib.Path, k) for k in ("is_file", "exists", "read_text", "read_bytes")}

    def test(name):
        return lambda p, *a, **k: False if p.as_posix() == gone else real[name](p, *a, **k)

    def read(name):
        def f(p, *a, **k):
            if p.as_posix() == gone:
                raise FileNotFoundError(gone)
            return real[name](p, *a, **k)
        return f
    with contextlib.ExitStack() as stack:
        for name in ("is_file", "exists"):
            stack.enter_context(mock.patch.object(pathlib.Path, name, autospec=True, side_effect=test(name)))
        for name in ("read_text", "read_bytes"):
            stack.enter_context(mock.patch.object(pathlib.Path, name, autospec=True, side_effect=read(name)))
        yield


class MissingRecord(unittest.TestCase):
    def test_40_a_missing_2_0_record_is_a_problem_in_both_rounds_never_an_exception(self):
        for round_ in ("v2.1", "v2.2"):
            for rel in (A.OUT_REL, A.PROPOSAL_REL):
                with self.subTest(round=round_, rel=rel), absent(rel):
                    history = A.history_problems() + A.proposal_history_problems()
                    rec = A.reverify(run_guards=False, round=round_)
                    self.assertEqual(rec["verdict"], "PROBLEMS")
                    self.assertEqual(rec["problems"], [f"{rel} is missing", *history])
                    self.assertIn(f"{rel} is not its v2.0.0 blob (history)", history)       # consistent with history_problems
                    self.assertEqual((rec["claims_owner_acceptance"], rec["new_approvals"]), (False, []))

    def test_40_with_both_records_present_the_full_re_verification_runs(self):
        for round_ in ("v2.1", "v2.2"):
            rec = A.reverify(run_guards=False, round=round_)
            self.assertIn("specs", rec)
            self.assertFalse([p for p in rec["problems"] if p.endswith(" is missing")], round_)


if __name__ == "__main__":
    unittest.main()
