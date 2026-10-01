"""WP-2.2.2 — ProbeCapabilityCalibration of `probe.cli_invocation` over the committed fixtures (RFC §9.1.1, CAL-1), the
class table with its DECISION-1 quantifier declarations tested exhaustively on fixture facts, and the two-invocation
`equality` class (DECISION-4). Kill set for the class table, the equality comparator and the equality path."""

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict  # noqa: E402
from aisef2.probe import catalog, cli_invocation as ci  # noqa: E402
from aisef2.probe.calibration import NotQualified, calibrate, calibration_env, fixture_spec  # noqa: E402
from aisef2.probe.cli_invocation import CliInvocationProbe  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef  # noqa: E402
from aisef2.product.contract import names_test_artefact  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from tests.v2.test_c2_cli_invocation import checkout, env, facts_of  # noqa: E402

P = CliInvocationProbe()
S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
BASE = ROOT / "tests" / "v2" / "fixtures" / "calibration" / "cli_invocation"
ENV = calibration_env(sys.executable)
REGISTRY = catalog.registry()
SHA = "89abcdef0123456789abcdef0123456789abcdef"
HANG_W = 0.4
#: A product whose output depends on argv only — or, by command, on something a second invocation must not share.
PRODUCT = {
    "eq/__init__.py": "",
    "eq/__main__.py": '''
import os
import sys
import time

cmd, rest = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("echo", [])
out = sys.stdout.buffer
if cmd == "echo":
    out.write((" ".join(rest) + "\\n").encode())
elif cmd == "raw":
    out.write(" ".join(rest).encode())
elif cmd == "crlf":
    out.write((" ".join(rest) + "\\r\\n").encode())
elif cmd == "err":
    sys.stderr.buffer.write((" ".join(rest) + "\\n").encode())
elif cmd == "json":
    out.write(b'{"a": 1, "b": [1, 2]}' if rest == ["a"] else b'{"b": [1, 2], "a": 1}')
elif cmd == "mark":
    out.write(b"seen" if os.path.exists("marker") else b"fresh")
    open("marker", "w").close()
elif cmd == "rand":
    out.write(os.urandom(8).hex().encode())
elif cmd == "exit":
    sys.exit(int(rest[0]))
elif cmd == "sleep":
    time.sleep(float(rest[0]))
''',
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def equality(a, b, *, streams=("stdout",), normalization=None, comparator=None, window=10, locator="eq:__main__",
             stimulus=None):
    eq = {"stimulus_a": {"argv": a} if isinstance(a, list) else a, "stimulus_b": {"argv": b} if isinstance(b, list) else b,
          "normalization": {} if normalization is None else normalization,   # DECISION-4: both are always declared
          "comparator": "bytes_equal" if comparator is None else comparator}
    return ProductProofSpec.create(
        contract_id="BC-EQ", probe_id=P.id, probe_digest=P.digest,
        probe_input={"subject": {"kind": "cli_invocation", "locator": locator}, "stimulus": stimulus or {},
                     "observable": {"equality": eq, "streams": list(streams), "within_s": window},
                     "subject_absence": "REQUIRES_SUBJECT"},
        candidate_expectation=S, compiler_id="test", compiler_digest="c" * 64)


class Fixtures(unittest.TestCase):
    def test_CLICAL_1_every_class_is_calibrated_with_contrast_and_rejected_without_it(self):
        self.assertEqual(sorted(p.name for p in BASE.iterdir() if p.is_dir()), sorted(ci.CLASSES))
        for cls in ci.CLASSES:
            pos, neg = BASE / cls / "positive", BASE / cls / "negative"
            with self.subTest(cls=cls):
                for d in (pos, neg):
                    self.assertTrue((d / "checkout" / "calib_cli.py").is_file())
                    self.assertEqual(ci.spec_class(fixture_spec(P, d)), cls)
                    self.assertEqual(REGISTRY.observation_class(P.id, P.digest, fixture_spec(P, d)), cls)
                    self.assertEqual(names_test_artefact(json.loads((d / "request.json").read_text(encoding="utf-8"))), [])
                    self.assertFalse([p for p in (d / "checkout").rglob("*") if p.name.startswith("test")])
                rec = calibrate(P, cls, pos, neg, ENV, time.time, registry=REGISTRY)
                self.assertEqual((rec.probe_id, rec.probe_digest, rec.observation_class), (P.id, P.digest, cls))
                self.assertEqual((rec.positive_fixture, rec.negative_fixture), (str(pos), str(neg)))
                for a, b in ((neg, neg), (pos, pos), (neg, pos)):
                    with self.assertRaises(NotQualified):
                        calibrate(P, cls, a, b, ENV, time.time, registry=REGISTRY)
        # the negative fixtures are one-line mutants of their positives
        for cls in ci.CLASSES:
            a = (BASE / cls / "positive" / "checkout" / "calib_cli.py").read_text(encoding="utf-8").splitlines()
            b = (BASE / cls / "negative" / "checkout" / "calib_cli.py").read_text(encoding="utf-8").splitlines()
            differing = sum(1 for x, y in zip(a, b, strict=False) if x != y) + abs(len(a) - len(b))
            self.assertEqual(differing, 1, cls)   # exactly one changed line

    def test_CLICAL_2_an_always_0_fixture_pair_is_rejected(self):
        tmp = tempfile.mkdtemp(prefix="aisef2-cal-")
        for side in ("positive", "negative"):
            d = pathlib.Path(tmp, side)
            (d / "checkout").mkdir(parents=True)
            (d / "checkout" / "calib_cli.py").write_text("import sys\n\nif __name__ == \"__main__\":\n    sys.exit(0)\n",
                                                          encoding="utf-8")
            (d / "request.json").write_text(json.dumps({"subject": {"kind": "cli_invocation", "locator": "calib_cli:__main__"},
                                                        "stimulus": {"argv": []}, "observable": {"exit_code": 0, "within_s": 5},
                                                        "subject_absence": "REQUIRES_SUBJECT"}), encoding="utf-8")
        with self.assertRaises(NotQualified) as rejected:
            calibrate(P, "exits", pathlib.Path(tmp, "positive"), pathlib.Path(tmp, "negative"), ENV, time.time, registry=REGISTRY)
        self.assertIn("negative fixture observed", str(rejected.exception))
        self.assertIn("no contrast with a SATISFIED expectation", str(rejected.exception))
        # and a pair the probe refutes on both sides (an always-REFUTED calibration) is rejected on the positive side
        (pathlib.Path(tmp, "positive", "request.json")).write_text(json.dumps({
            "subject": {"kind": "cli_invocation", "locator": "calib_cli:__main__"}, "stimulus": {"argv": []},
            "observable": {"exit_code": 4, "within_s": 5}, "subject_absence": "REQUIRES_SUBJECT"}), encoding="utf-8")
        (pathlib.Path(tmp, "negative", "request.json")).write_text(json.dumps({
            "subject": {"kind": "cli_invocation", "locator": "calib_cli:__main__"}, "stimulus": {"argv": []},
            "observable": {"exit_code": 4, "within_s": 5}, "subject_absence": "REQUIRES_SUBJECT"}), encoding="utf-8")
        with self.assertRaises(NotQualified) as rejected:
            calibrate(P, "exits", pathlib.Path(tmp, "positive"), pathlib.Path(tmp, "negative"), ENV, time.time, registry=REGISTRY)
        self.assertIn("positive fixture observed", str(rejected.exception))


class Equality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.at = RevisionRef(SHA, checkout(PRODUCT))

    def see(self, s, e=None):
        return P.observe(s, self.at, e or env())

    def test_CLICAL_3_two_invocations_the_comparator_the_normalisation_and_the_swap(self):
        same = equality(["echo", "x"], ["echo", "x"])
        self.assertEqual(ci.spec_class(same), "equality")
        o = self.see(same)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        f = facts_of(o)
        self.assertIs(f["distinct_evaluation_directories"], True)
        self.assertEqual((f["a"]["exit_code"], f["b"]["exit_code"], f["a"]["stdout"]["sha256"]), (0, 0, sha(b"x\n")))
        self.assertNotIn("path", o.detail)
        swapped = equality(["echo", "x"], ["echo", "y"])
        self.assertNotEqual(swapped.semantic_hash, same.semantic_hash)   # stimulus_b is bound into what is proved
        self.assertEqual(self.see(swapped).verdict, R)
        # the comparator: the same document in another key order
        self.assertEqual(self.see(equality(["json", "a"], ["json", "b"])).verdict, R)
        self.assertEqual(self.see(equality(["json", "a"], ["json", "b"], comparator="json_equal")).verdict, S)
        self.assertEqual(self.see(equality(["echo", "x"], ["echo", "x"], comparator="json_equal")).verdict, R)   # not JSON
        self.assertNotEqual(equality(["json", "a"], ["json", "b"], comparator="json_equal").semantic_hash,
                            equality(["json", "a"], ["json", "b"]).semantic_hash)
        # the normalisation policy: a declared newline and a trailing newline
        self.assertEqual(self.see(equality(["crlf", "x"], ["echo", "x"])).verdict, R)
        self.assertEqual(self.see(equality(["crlf", "x"], ["echo", "x"], normalization={"newline": "\r\n"})).verdict, S)
        self.assertEqual(self.see(equality(["raw", "x"], ["echo", "x"])).verdict, R)
        self.assertEqual(self.see(equality(["raw", "x"], ["echo", "x"],
                                           normalization={"strip_trailing_newline": True})).verdict, S)
        self.assertNotEqual(equality(["raw", "x"], ["echo", "x"], normalization={"strip_trailing_newline": True}).semantic_hash,
                            equality(["raw", "x"], ["echo", "x"]).semantic_hash)
        # every named stream and both exit codes count
        self.assertEqual(self.see(equality(["err", "z"], ["echo"], streams=("stdout", "stderr"))).verdict, R)
        self.assertEqual(self.see(equality(["err", "z"], ["err", "z"], streams=("stdout", "stderr"))).verdict, S)
        self.assertEqual(self.see(equality(["err", "z"], ["err", "q"], streams=("stdout",))).verdict, S)   # stderr not named
        self.assertEqual(self.see(equality(["exit", "1"], ["exit", "2"])).verdict, R)
        self.assertEqual(self.see(equality(["exit", "1"], ["exit", "1"])).verdict, S)
        # no residue of the first invocation reaches the second, and nothing outside the invocations decides
        o = self.see(equality(["mark"], ["mark"]))
        self.assertEqual((o.verdict, facts_of(o)["a"]["stdout"]["sha256"]), (S, sha(b"fresh")))
        self.assertEqual(self.see(equality(["rand"], ["rand"])).verdict, R)
        # a half that is not a returned invocation is the observation
        self.assertEqual(self.see(equality(["echo"], ["echo"], locator="gone:__main__")).kind, K.SUBJECT_ABSENT)
        o = self.see(equality(["sleep", "30"], ["echo"], window=HANG_W))
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R))
        o = self.see(equality(["echo"], ["sleep", "30"], window=HANG_W))
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R))
        o = self.see(equality({"argv": ["echo"], "pre": [{"argv": ["exit", "3"]}]}, ["echo"]))
        self.assertEqual((o.kind, o.verdict, facts_of(o)["pre_failed"]), (K.OBSERVED, R, 0))   # that half's own facts
        o = self.see(equality(["echo"], {"argv": ["echo"], "pre": [{"argv": ["exit", "3"]}]}))
        self.assertEqual((o.kind, o.verdict, facts_of(o)["pre_failed"], "a" in facts_of(o)), (K.OBSERVED, R, 0, False))
        o = self.see(equality({"argv": ["echo"], "pre": [{"argv": ["echo"]}]}, ["echo"]))
        self.assertEqual((o.verdict, facts_of(o)["subject"], len(facts_of(o)["a"]["pre"])), (S, "present", 1))
        gone = os.path.join(self.at.root, "no-python")
        self.assertEqual(self.see(same, e=env(interpreter=gone)).kind, K.HARNESS_FAILED)
        probe = CliInvocationProbe(scratch=os.path.join(self.at.root, "scratch-in-tree"))
        os.makedirs(os.path.join(self.at.root, "scratch-in-tree"), exist_ok=True)
        self.assertEqual(probe.observe(same, self.at, env()).kind, K.HARNESS_FAILED)
        self.assertEqual(CliInvocationProbe(scratch=os.path.join(self.at.root, "none")).observe(same, self.at, env()).detail,
                         "the evaluation directory cannot be created: FileNotFoundError")

if __name__ == "__main__":
    unittest.main()
