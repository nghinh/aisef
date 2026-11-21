"""Q0-1: the round-v2.3 counterpart of the v2.2 round's GATED Q0 calibration, and its fail-closed controls.

The v2.2 Q0 test (tests/v2/p0/test_checker_calibration.py::CheckerCalibration) and its record
(closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json) are history, both unchanged: replay_v22.Q0_REPLAYED replays the
class at v2.2.0 and requires the record it derives there to be byte-identical to the committed one
(RoundV23.test_replay_v22). Round v2.3 keeps the same control on the HEAD tree:

* `Q0RoundV23` — the v2.2 class's nine tests, bodies verbatim (replay_v22.coverage proves none is lost), on
  validation/v23/q0_round.run(): the same calibration inside `version_forward.in_round("v2.3")`. The one record
  assertion is rebound to the round's own record, q0_round.V23_REL. Under AISEF_SEALING=1 each test FAILS — never
  skips — unless ledger seq 13 is committed by the owner (test_v23_rounds.round_v23_missing), the v2.2 record is still
  its v2.2.0 bytes, no v2.2 checker is dropped, and V23_REL exists and is what this tree derives;
* `Q0Wiring` — the reviewed wiring skips the v2.2 Q0 test at HEAD only together with this file and q0_round.py
  pinned (SEQ13-WIRING-R4.patch: V22_REPLAYED_Q0, V23_PINNED).

Both are `round_gate` classes (closed list: test_v23_rounds.V23_GATED). The other classes always run, in seconds, on
throwaway trees: each way the round-v2.3 record or the v2.2 history can be missing, stale or corrupted is named, and
the replay names a missing, corrupted or not byte-identical historical Q0 record.
"""
from __future__ import annotations

import contextlib
import importlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest
from dataclasses import replace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v2 import sealing_gate  # noqa: E402
from tests.v23 import test_v23_rounds as R  # noqa: E402  (module import: its TestCases are not collected twice)
from validation.v23 import q0_round as Q  # noqa: E402
from validation.v23 import replay_v22 as RP  # noqa: E402

cc = Q.cc()
HERE = "tests/v23/test_v23_q0_round.py"


@R.round_gate
class Q0RoundV23(unittest.TestCase):
    """CheckerCalibration's tests on this tree in round v2.3 (bodies verbatim from v2.2.0; see replay_v22.coverage)."""

    @classmethod
    def setUpClass(cls):
        cls.result = Q.run()

    def open(self):
        missing = R.round_v23_missing()
        if missing:
            self.fail("round v2.3 is not open: " + "; ".join(missing))

    def test_every_checker_is_calibrated_and_the_committed_record_is_current(self):
        # round v2.3: authority, history, no checker dropped, its own record — every problem named in one message
        self.assertEqual(R.round_v23_missing() + Q.history_problems() + Q.dropped(self.result)
                         + Q.record_problems(self.result), [])
        self.assertEqual(cc.problems_of(self.result), [])
        self.assertEqual(self.result["calibrated_count"], len(cc.REGISTRY))
        self.assertEqual((ROOT / Q.V23_REL).read_text(encoding="utf-8"), Q.render(self.result))

    def test_the_2_0_record_is_history(self):
        self.open()
        self.assertNotEqual(cc.OUT_REL, cc.HISTORY_REL)
        self.assertEqual(cc.history_problems(), [])
        tampered = (ROOT / cc.HISTORY_REL).read_bytes() + b" "
        with mock.patch.object(pathlib.Path, "read_bytes", return_value=tampered):
            self.assertEqual(cc.history_problems(), [f"{cc.HISTORY_REL} is not its v2.0.0 blob (history)"])

    def test_every_checker_has_a_committed_fixture_that_fails_it_for_the_named_reason(self):
        self.open()
        for r in self.result["checkers"]:
            with self.subTest(checker=r["checker"]):
                self.assertTrue((ROOT / r["fixture"]).is_file())
                self.assertTrue(r["clean_passes"])
                self.assertTrue(r["rejects_for_the_expected_reason"], r["observed"])

    def test_an_always_pass_checker_fails_calibration(self):
        self.open()
        for make in cc.REGISTRY:
            c = make()
            with self.subTest(checker=c.name):
                self.assertFalse(cc.calibrate(cc.always_pass_mutant(c))["calibrated"])

    def test_a_checker_that_fails_everything_fails_calibration(self):
        self.open()
        c = cc.REGISTRY[0]()
        broken = replace(c, clean=lambda: ["always"], known_bad=lambda fx: ["always"])
        self.assertFalse(cc.calibrate(broken)["calibrated"])

    def test_a_checker_that_rejects_for_the_wrong_reason_fails_calibration(self):
        self.open()
        c = cc.REGISTRY[0]()
        wrong = replace(c, known_bad=lambda fx: ["some unrelated file is missing"])
        self.assertFalse(cc.calibrate(wrong)["calibrated"])

    def test_a_missing_fixture_means_not_calibrated(self):
        self.open()
        c = replace(cc.REGISTRY[0](), name="no_such_checker")
        r = cc.calibrate(c)
        self.assertFalse(r["calibrated"])
        self.assertIn("no committed known-bad fixture", r["reason"])

    def test_a_stale_fixture_that_no_longer_fails_is_a_calibration_failure(self):
        self.open()
        fx = cc.fixture_for("packaging_check")
        with mock.patch.object(cc, "fixture_for", return_value=dict(fx, replace=fx["find"])):
            r = cc.calibrate(cc._packaging_check())
        self.assertFalse(r["rejects_known_bad"])
        self.assertFalse(r["calibrated"])

    def test_an_uncalibrated_checker_module_is_a_failure(self):
        self.open()
        self.assertEqual(self.result["uncovered_checker_modules"], [])
        dropped = [make() for make in cc.REGISTRY if make is not cc._packaging_check]
        self.assertIn("validation/v2/packaging_check.py", cc.uncovered_checker_modules(dropped))
        bad = dict(self.result, uncovered_checker_modules=["validation/v2/packaging_check.py"])
        self.assertTrue(cc.problems_of(bad))


@R.round_gate
class Q0Wiring(unittest.TestCase):
    """Red until the reviewed wiring is applied: the v2.2 Q0 test is skipped at HEAD, naming the replay, only while
    this file and q0_round.py are pinned and every pin holds."""

    def test_the_Q0_test_is_skipped_at_head_only_together_with_its_pinned_counterpart(self):
        self.assertEqual(tuple(getattr(sealing_gate, "V22_REPLAYED_Q0", ())), (RP.Q0_REPLAYED,))
        self.assertIn(RP.Q0_REPLAYED, sealing_gate.GATED)
        self.assertLessEqual({HERE, "validation/v23/q0_round.py"}, set(getattr(sealing_gate, "V23_PINNED", {})))
        self.assertTrue(getattr(sealing_gate, "V23_PINS_HOLD", False), "a V23_PINNED file is not as pinned")
        cls = importlib.import_module("tests.v2.p0.test_checker_calibration").CheckerCalibration
        self.assertTrue(getattr(cls, "__unittest_skip__", False))
        self.assertIn("replayed at v2.2.0", getattr(cls, "__unittest_skip_why__", ""))


# ------------------------------------------------------------------------------------------- always-run controls

def _git(root, *a) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false", *a], capture_output=True, check=True, encoding="utf-8").stdout.strip()


class Q0Record(unittest.TestCase):
    """q0_round on throwaway roots: the round-v2.3 record and the v2.2 history, each failure mode named."""

    @classmethod
    def setUpClass(cls):
        cls.v22 = (ROOT / Q.V22_REL).read_bytes()
        cls.result = json.loads(cls.v22)          # the committed v2.2 record is a calibration result itself

    def root(self, *, v22: bytes | None = None, v23: bytes | None = None) -> pathlib.Path:
        t = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory(prefix="aisef-q0-round-")))
        for rel, data in ((Q.V22_REL, v22), (Q.V23_REL, v23)):
            if data is not None:
                (t / rel).parent.mkdir(parents=True, exist_ok=True)
                (t / rel).write_bytes(data)
        return t

    def test_constants_agree_with_the_replay_and_the_history(self):
        self.assertEqual((Q.V22_REL, RP.Q0_RECORD_REL), (cc.OUT_REL, cc.OUT_REL))
        self.assertEqual(Q.history_problems(), [])
        self.assertEqual(_git(ROOT, "rev-parse", f"{RP.V2_2_0}:{Q.V22_REL}"), _git(ROOT, "rev-parse", f"HEAD:{Q.V22_REL}"))
        self.assertFalse(Q.V23_REL.startswith("closure-evidence/"), "placement: never under closure-evidence/")

    def test_the_round_v23_record_missing_corrupted_stale_or_current(self):
        good = Q.render(self.result).encode("utf-8")
        stale = Q.render(dict(self.result, calibrated_count=56)).encode("utf-8")
        cases = {"missing": (None, "is missing"), "not JSON": (good[:-40], "is corrupted (not UTF-8 JSON)"),
                 "not UTF-8": (b"\xff" + good, "is corrupted"), "stale": (stale, "is stale or corrupted"),
                 "one byte changed": (good.replace(b'"v2.3"', b'"v2.4"', 1), "is stale or corrupted"),
                 "CRLF": (good.replace(b"\n", b"\r\n"), None), "current": (good, None)}
        for name, (data, why) in cases.items():
            with self.subTest(name):
                got = Q.record_problems(self.result, self.root(v23=data))
                if why is None:
                    self.assertEqual(got, [])
                else:
                    self.assertEqual(len(got), 1, got)
                    self.assertIn(Q.V23_REL, got[0])
                    self.assertIn(why, got[0])

    def test_the_v22_history_missing_or_corrupted_fails_closed_naming_it(self):
        cases = {"missing": (None, "is missing (history: fail closed)"),
                 "one byte changed": (self.v22.replace(b"57", b"58", 1), "is not its v2.2.0 bytes"),
                 "truncated": (self.v22[:100], "is not its v2.2.0 bytes")}
        for name, (data, why) in cases.items():
            with self.subTest(name):
                got = Q.history_problems(self.root(v22=data))
                self.assertEqual(len(got), 1, got)
                self.assertIn(Q.V22_REL, got[0])
                self.assertIn(why, got[0])
        self.assertEqual(Q.history_problems(self.root(v22=self.v22.replace(b"\n", b"\r\n"))), [])   # CRLF checkout

    def test_a_dropped_v22_checker_and_a_short_registry_are_named(self):
        t = self.root(v22=self.v22)
        self.assertEqual(Q.dropped(self.result, t), [])
        fewer = dict(self.result, checkers=self.result["checkers"][1:], calibrated_count=56)
        self.assertEqual(Q.dropped(fewer, t), [f"v2.2 Q0 checker {self.result['checkers'][0]['checker']} is not "
                                               "calibrated in round v2.3"])
        self.assertIn("calibrated 56 of 57 registered checkers", Q.problems(fewer, t, record_too=False))
        self.assertEqual(Q.problems(self.result, t, record_too=False), [])

    def test_the_writer_refuses_a_closed_round_writes_once_and_never_rewrites(self):
        t = self.root(v22=self.v22)
        with mock.patch.object(Q, "ROOT", t), mock.patch.object(Q, "run", return_value=self.result), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            with mock.patch.object(R, "round_v23_missing", return_value=["no seq 13"]):
                self.assertEqual(Q.main(["--write"]), 1)
            self.assertFalse((t / Q.V23_REL).exists())
            self.assertIn("refused: round v2.3 is not open: no seq 13", out.getvalue())
            with mock.patch.object(R, "round_v23_missing", return_value=[]):
                self.assertEqual(Q.main(["--write"]), 0)
                first = (t / Q.V23_REL).read_bytes()
                self.assertEqual(Q.main(["--write"]), 1)
            self.assertIn(f"refused: {Q.V23_REL} exists", out.getvalue())
            self.assertEqual((t / Q.V23_REL).read_bytes(), first)
            self.assertEqual(Q.main(["--check"]), 0)
            with mock.patch.object(Q, "run", return_value=dict(self.result, calibrated_count=56)):
                self.assertEqual(Q.main(["--check"]), 1)
        self.assertEqual(Q.record_problems(self.result, t), [])

    def test_the_writer_refuses_an_uncalibrated_tree(self):
        t = self.root(v22=self.v22)
        red = dict(self.result, uncovered_checker_modules=["validation/v2/gen_probe_grammar.py"])
        with mock.patch.object(Q, "ROOT", t), mock.patch.object(Q, "run", return_value=red), \
                mock.patch.object(R, "round_v23_missing", return_value=[]), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(Q.main(["--write"]), 1)
        self.assertFalse((t / Q.V23_REL).exists())
        self.assertIn("checker module with no calibration: validation/v2/gen_probe_grammar.py", out.getvalue())

    def test_run_enters_round_v23_when_the_selection_exists(self):
        from validation.v2 import version_forward as vf
        seen = []

        @contextlib.contextmanager
        def in_round(r):
            seen.append(("enter", r))
            yield
            seen.append(("exit", r))

        with mock.patch.object(vf, "in_round", in_round, create=True), \
                mock.patch.object(cc, "run", side_effect=lambda: seen.append("run") or {}):
            Q.run()
        self.assertEqual(seen, [("enter", "v2.3"), "run", ("exit", "v2.3")])


class Q0Coverage(unittest.TestCase):
    """Every assertion of the v2.2 Q0 class at v2.2.0 is in its Q0RoundV23 method; the class pairs are closed."""

    def test_every_v22_q0_assertion_has_its_counterpart_and_the_methods_pair_exactly(self):
        doc = RP.coverage(ROOT)
        q0 = [t for t in doc["tests"] if t["id"].startswith(RP.Q0_REPLAYED + ".")]
        self.assertEqual(len(q0), 9)
        self.assertEqual([g for g in doc["gaps"] if g.startswith(RP.Q0_REPLAYED)], [])
        self.assertTrue(all(t["byte_identical_at_head"] and t["counterpart_found"] for t in q0))
        self.assertEqual([a["kind"] for t in q0 for a in t["assertions"]].count("rebound"), 1)
        mine = {n for n in vars(Q0RoundV23) if n.startswith("test_")}
        self.assertEqual(mine, {t["id"].rsplit(".", 1)[1] for t in q0})

    def test_a_dropped_q0_assertion_is_a_gap(self):
        src = (ROOT / RP.Q0_COUNTERPART_REL).read_text(encoding="utf-8")
        line = "                self.assertFalse(cc.calibrate(cc.always_pass_mutant(c))[\"calibrated\"])\n"
        self.assertIn(line, src)
        fn = RP._method(src.replace(line, "                pass\n", 1), "Q0RoundV23.test_an_always_pass_checker_fails_calibration")
        self.assertNotIn("self.assertFalse(cc.calibrate(cc.always_pass_mutant(c))['calibrated'])",
                         [a for _, a in RP.assertions(fn)])


#: a synthetic v2.2.0 tree's Q0 test module: its class derives @RESULT@ and asserts @CHECK@
FAKE_CC = textwrap.dedent('''\
    import json, pathlib, types, unittest
    ROOT = pathlib.Path(__file__).resolve().parents[3]
    cc = types.SimpleNamespace(OUT_REL="closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json",
                               render=lambda r: json.dumps(r, indent=1) + "\\n")
    class CheckerCalibration(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            cls.result = @RESULT@
        def test_current(self):
            @CHECK@
    ''')
OWNED_RUN = textwrap.dedent('''\
    import json, subprocess, sys
    out, cmd = sys.argv[2], sys.argv[4:]
    code = subprocess.run(cmd).returncode
    json.dump({"exit": code, "owned_after": 0, "escaped": [], "released_empty": True}, open(out, "w"))
    sys.exit(code)
    ''')
STRICT = 'self.assertEqual((ROOT / cc.OUT_REL).read_text(encoding="utf-8"), cc.render(self.result))'


class Q0Replay(unittest.TestCase):
    """replay_v22 on synthetic trees: the historical Q0 record missing, corrupted, or not what the class derives."""

    def tree(self, result: str = '{"calibrated": 57}', check: str = STRICT, record: str = '{\n "calibrated": 57\n}\n'):
        t = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory(prefix="aisef-q0-replay-")), "tree").resolve()
        files = {"tests/__init__.py": "", "tests/v2/__init__.py": "", "tests/v2/p0/__init__.py": "",
                 "tests/v2/p0/test_checker_calibration.py": FAKE_CC.replace("@RESULT@", result).replace("@CHECK@", check),
                 "tests/v2/sealing_gate.py": f"GATED = ({RP.Q0_REPLAYED!r},)\n", "validation/v2/owned_run.py": OWNED_RUN,
                 RP.Q0_RECORD_REL: record}
        for rel, text in files.items():
            (t / rel).parent.mkdir(parents=True, exist_ok=True)
            (t / rel).write_text(text, encoding="utf-8")
        _git(t, "init", "-q")
        _git(t, "add", "-A")
        _git(t, "commit", "-q", "-m", "fake v2.2.0")
        return t, _git(t, "rev-parse", "HEAD")

    def replay(self, t, commit):
        with tempfile.TemporaryDirectory(prefix="aisef-q0-replay-scratch-") as s:
            return RP.replay(t, [RP.Q0_REPLAYED], scratch=pathlib.Path(s), commit=commit)

    def test_an_intact_record_regenerates_byte_identically(self):
        doc = self.replay(*self.tree())
        self.assertEqual(doc["problems"], [])
        self.assertEqual(doc["verdict"], "PARTIAL")               # Q0 alone is a subset, never a full PASS
        (t,) = doc["tests"]
        self.assertTrue(t["q0_record"]["byte_identical"])
        self.assertEqual(t["q0_record"]["regenerated_sha256"], t["q0_record"]["committed_sha256"])

    def test_a_missing_record_fails_closed_naming_it(self):
        t, commit = self.tree()
        (t / RP.Q0_RECORD_REL).unlink()
        probs = self.replay(t, commit)["problems"]
        self.assertIn(f"{RP.Q0_REPLAYED}: Q0 record {RP.Q0_RECORD_REL} is missing from the tree (fail closed)", probs)
        self.assertIn(f"tree not clean: D {RP.Q0_RECORD_REL}", probs)
        self.assertTrue(any(p.startswith(f"{RP.Q0_REPLAYED}: FAIL") for p in probs), probs)

    def test_a_corrupted_record_fails_closed_naming_it(self):
        t, commit = self.tree()
        (t / RP.Q0_RECORD_REL).write_text('{\n "calibrated": 56\n}\n', encoding="utf-8")
        probs = self.replay(t, commit)["problems"]
        self.assertIn(f"{RP.Q0_REPLAYED}: Q0 record {RP.Q0_RECORD_REL} in the tree is not the v2.2.0 committed bytes "
                      "(corrupted)", probs)
        self.assertIn(f"{RP.Q0_REPLAYED}: record {RP.Q0_RECORD_REL} is not the v2.2.0 committed bytes", probs)

    def test_a_regeneration_that_differs_is_named_even_when_the_test_would_pass(self):
        doc = self.replay(*self.tree(result='{"calibrated": 56}', check="self.assertTrue(True)"))
        self.assertEqual(doc["tests"][0]["outcome"], "PASS")
        self.assertIn(f"{RP.Q0_REPLAYED}: Q0 record {RP.Q0_RECORD_REL}: the regenerated record is not byte-identical "
                      "to the v2.2.0 committed bytes", doc["problems"])

    def test_a_class_that_cannot_calibrate_is_named(self):
        doc = self.replay(*self.tree(result="1 / 0"))
        self.assertIn(f"{RP.Q0_REPLAYED}: Q0 record {RP.Q0_RECORD_REL} was not regenerated (the class did not "
                      "calibrate)", doc["problems"])

    def test_the_replayed_set_is_the_11_and_the_gated_q0_class(self):
        self.assertEqual(RP.REPLAYED, (*RP.V22_REPLAYED, RP.Q0_REPLAYED))
        self.assertIn(RP.Q0_REPLAYED, sealing_gate.GATED)


if __name__ == "__main__":
    unittest.main()
