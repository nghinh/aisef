"""L1-F5 round mechanics (W1-DESIGN §2.6; ledger seq 13) — the NEW, always-run unit tests.

The gated counterparts (tests/v23/test_v23_rounds.py, pinned) prove the REAL nodes at HEAD; this file proves the
MECHANISM on synthetic and throwaway data, so a defect in round selection is red in the ordinary suite:

* round-v2.3 selection is the verified head of a chain — a base-only series, a tampered head and a replayed
  (round, commit) pair each refuse with their own message, and the v2.2 selection rule and messages are untouched;
* the k-series loader is fail-closed: a gap, a leading zero or a non-numeric suffix raises, and outside the round
  the v2.3 files are invisible;
* write_supersession in round v2.3 appends -<k>.json append-only ("x"), supersedes the head by digest, no-ops on an
  equal body, and a second derivation on one commit is a broken chain (replay guard);
* the DAG state machine maps check results to MEASURED / VERIFIED_REUSE / INVALIDATED / UNRESOLVED and propagates a
  bad upstream — an always-VERIFIED_REUSE mutant of _validate_v23 fails here (W1-DESIGN §2.6 NEW-tests list).
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import currency_dag as cd  # noqa: E402
from validation.v2 import version_forward as vf  # noqa: E402

V22_REL = "closure-evidence/v2/v2.2/SYNTH-RECORD.json"
LEGACY_REL = "closure-evidence/v2/v2.1/SYNTH-RECORD.json"
STEM = "SYNTH-RECORD"


def synth_chain() -> list[tuple[str, dict, bytes]]:
    """[base, v2.2 supersession] — the committed-history shape every real series has."""
    base = {"record": "BASE", "n": 1}
    base_b = vf._canon(base)
    v22 = vf.bind({"record": "V2.2", "sources": {"a": "x"}}, version_context="v2.2", source_commit="c1" * 20,
                  kernel_digest="k1" * 20, predecessor_path=LEGACY_REL, predecessor_bytes=base_b)
    return [(LEGACY_REL, base, base_b), (V22_REL, v22, vf._canon(v22))]


def grow(series: list, body: dict, *, commit: str) -> list:
    """Append a v2.3 record superseding the current head (synthetic twin of write_supersession's binding)."""
    head_rel, _, head_b = series[-1]
    k = sum(1 for rel, _, _ in series if rel.startswith(vf.V23_DIR + "/")) + 1
    rec = vf.bind(body, version_context=vf.BRANCH_ROUND, source_commit=commit, kernel_digest="t" * 40,
                  predecessor_path=head_rel, predecessor_bytes=head_b)
    return series + [(f"{vf.V23_DIR}/{STEM}-{k}.json", rec, vf._canon(rec))]


class RoundSelection(unittest.TestCase):
    """select_for_tree / validate_chain across the two rounds, on synthetic chains."""

    def test_round_v23_selects_the_verified_head_and_ignores_the_tree(self):
        series = grow(synth_chain(), {"record": "V2.3-1"}, commit="a1" * 20)
        with vf.in_round("v2.3"):
            path, rec = vf.select_for_tree(series, version_context="nonsense", kernel_digest="z" * 40)
        self.assertEqual((path, rec["record"]), (f"{vf.V23_DIR}/{STEM}-1.json", "V2.3-1"))
        # the default round still selects by (round, tree), messages untouched
        self.assertEqual(vf.select_for_tree(series, version_context="v2.2", kernel_digest="k1" * 20)[1]["record"],
                         "V2.2")
        with self.assertRaisesRegex(LookupError, "no record declared for round 'v9.9'"):
            vf.select_for_tree(series, version_context="v9.9", kernel_digest="k1" * 20)

    def test_a_base_only_series_has_no_round_record(self):
        base_rel, base, base_b = synth_chain()[0]
        with vf.in_round("v2.3"):
            with self.assertRaisesRegex(LookupError, f"no record in the series of {base_rel} for round 'v2.3'"):
                vf.select_for_tree([(base_rel, base, base_b)], version_context="v2.3", kernel_digest="k1" * 20)

    def test_a_tampered_head_refuses(self):
        series = grow(synth_chain(), {"record": "V2.3-1", "payload": "good"}, commit="a1" * 20)
        rel, rec, _ = series[-1]
        bad = json.loads(json.dumps(rec))
        bad["payload"] = "TAMPERED"
        series[-1] = (rel, bad, vf._canon(bad))
        with vf.in_round("v2.3"):
            with self.assertRaisesRegex(LookupError, "tampered"):
                vf.select_for_tree(series, version_context="v2.3", kernel_digest="k1" * 20)

    def test_two_v23_records_on_one_commit_are_a_replay(self):
        series = grow(grow(synth_chain(), {"record": "V2.3-1"}, commit="a1" * 20),
                      {"record": "V2.3-2"}, commit="a1" * 20)
        problems = vf.validate_chain(series)
        self.assertTrue(any("duplicate (version_context, source_commit)" in p for p in problems), problems)
        # distinct commits are a sound chain
        series = grow(grow(synth_chain(), {"record": "V2.3-1"}, commit="a1" * 20),
                      {"record": "V2.3-2"}, commit="b2" * 20)
        self.assertEqual(vf.validate_chain(series), [])

    def test_the_v22_duplicate_message_is_unchanged(self):
        one = synth_chain()[1][1]
        twin_body = {k: v for k, v in one.items() if k != vf.BLOCK} | {"record": "V2.2-TWIN"}
        twin = vf.bind(twin_body, version_context="v2.2", source_commit="c9" * 20, kernel_digest="k1" * 20,
                       predecessor_path=V22_REL, predecessor_bytes=vf._canon(one))
        series = synth_chain() + [("twin.json", twin, vf._canon(twin))]
        problems = vf.validate_chain(series)
        self.assertTrue(any("duplicate (version_context, kernel_digest)" in p
                            and "(ambiguous head / replay / rollback)" in p for p in problems), problems)


class SeriesFiles(unittest.TestCase):
    """load_series k-discipline on a throwaway root (no git needed)."""

    def write_series(self, root: pathlib.Path, names: list[str]) -> None:
        series = synth_chain()
        (root / LEGACY_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / LEGACY_REL).write_bytes(series[0][2])
        (root / V22_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / V22_REL).write_bytes(series[1][2])
        d = root / vf.V23_DIR
        d.mkdir(parents=True, exist_ok=True)
        for name in names:
            (d / name).write_bytes(vf._canon({"record": name}))

    def test_k_order_gaps_and_leading_zeros(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            self.write_series(root, [f"{STEM}-2.json", f"{STEM}-1.json"])
            with vf.in_round("v2.3"):
                rels = [rel for rel, _, _ in vf.load_series(root, LEGACY_REL, V22_REL)]
            self.assertEqual(rels, [LEGACY_REL, V22_REL,
                                    f"{vf.V23_DIR}/{STEM}-1.json", f"{vf.V23_DIR}/{STEM}-2.json"])
            # outside the round the v2.3 files are invisible
            self.assertEqual([rel for rel, _, _ in vf.load_series(root, LEGACY_REL, V22_REL)],
                             [LEGACY_REL, V22_REL])
        for bad in ([f"{STEM}-2.json"], [f"{STEM}-01.json"], [f"{STEM}-1.json", f"{STEM}-3.json"]):
            with tempfile.TemporaryDirectory() as t:
                root = pathlib.Path(t)
                self.write_series(root, bad)
                with vf.in_round("v2.3"), self.assertRaises(ValueError):
                    vf.load_series(root, LEGACY_REL, V22_REL)


class WriteSupersession(unittest.TestCase):
    """write_supersession in round v2.3 on a throwaway git repository."""

    def repo(self, stack: contextlib.ExitStack) -> pathlib.Path:
        root = pathlib.Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="aisef-f5-round-")))
        def git(*a):
            subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                           capture_output=True, check=True)
        (root / "aisef2").mkdir()
        (root / "aisef2/x.py").write_text("x = 1\n", encoding="utf-8")
        git("init", "-q")
        git("add", "-A")
        git("commit", "-qm", "one")
        series = synth_chain()
        (root / LEGACY_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / LEGACY_REL).write_bytes(series[0][2])
        self.git = git
        return root

    def test_append_only_noop_and_replay_guard(self):
        render = lambda rec: json.dumps(rec, indent=1, ensure_ascii=False) + "\n"  # noqa: E731
        with contextlib.ExitStack() as stack, vf.in_round("v2.3"):
            root = self.repo(stack)
            rc, msg = vf.write_supersession(root, LEGACY_REL, V22_REL, {"record": "R1"}, render=render)
            self.assertEqual((rc, msg.split(":")[0]), (0, f"wrote {vf.V23_DIR}/{STEM}-1.json"))
            rc, msg = vf.write_supersession(root, LEGACY_REL, V22_REL, {"record": "R1"}, render=render)
            self.assertEqual(rc, 0)
            self.assertIn("already records this derivation", msg)
            # a second derivation on the SAME commit is written but the chain refuses it (replay guard)
            rc, _ = vf.write_supersession(root, LEGACY_REL, V22_REL, {"record": "R2"}, render=render)
            self.assertEqual(rc, 0)
            with self.assertRaisesRegex(LookupError, r"duplicate \(version_context, source_commit\)"):
                vf.select_for_tree(vf.load_series(root, LEGACY_REL, V22_REL),
                                   version_context="v2.3", kernel_digest="x" * 40)

    def test_a_new_commit_grows_the_chain_to_a_verified_head(self):
        render = lambda rec: json.dumps(rec, indent=1, ensure_ascii=False) + "\n"  # noqa: E731
        with contextlib.ExitStack() as stack, vf.in_round("v2.3"):
            root = self.repo(stack)
            vf.write_supersession(root, LEGACY_REL, V22_REL, {"record": "R1"}, render=render)
            (root / "aisef2/x.py").write_text("x = 2\n", encoding="utf-8")
            self.git("add", "-A")
            self.git("commit", "-qm", "two")
            rc, msg = vf.write_supersession(root, LEGACY_REL, V22_REL, {"record": "R2"}, render=render)
            self.assertEqual((rc, msg.split(":")[0]), (0, f"wrote {vf.V23_DIR}/{STEM}-2.json"))
            series = vf.load_series(root, LEGACY_REL, V22_REL)
            self.assertEqual(vf.validate_chain(series), [])
            path, rec = vf.select_for_tree(series, version_context="v2.3", kernel_digest="x" * 40)
            self.assertEqual((path, rec["record"]), (f"{vf.V23_DIR}/{STEM}-2.json", "R2"))


class DagStates(unittest.TestCase):
    """_validate_v23's state machine, with the node checks controlled — an always-VERIFIED_REUSE mutant fails here."""

    def test_states_and_upstream_propagation(self):
        def fail():
            return ["boom: the PLAN check found a problem"]
        def boom():
            raise RuntimeError("the ruling reader fell over")
        ok = lambda: []  # noqa: E731
        table = {nid: ok for nid in cd.NODES}
        table["PLAN"] = fail
        table["CONFORMANCE-RULING"] = boom
        with mock.patch.object(cd, "_checks", return_value=table):
            rep = cd.validate(ROOT, round="v2.3")
        n = rep["nodes"]
        self.assertEqual(n["P5-PROPOSAL"]["state"], "VERIFIED_REUSE")
        self.assertEqual(n["P5-PROPOSAL"]["basis"], "v2.2.0-accepted@da3ea33f; re-checked in round v2.3")
        self.assertEqual((n["PLAN"]["state"], n["PLAN"]["detail"]),
                         ("INVALIDATED", "boom: the PLAN check found a problem"))
        self.assertEqual((n["K-NOWORK"]["state"], n["K-NOWORK"]["detail"]),
                         ("INVALIDATED", "upstream not current for round 'v2.3': ['PLAN']"))
        self.assertEqual(n["CONFORMANCE-RULING"]["state"], "UNRESOLVED")
        self.assertIn("RuntimeError: the ruling reader fell over", n["CONFORMANCE-RULING"]["detail"])
        self.assertEqual(n["ORCH"]["state"], "INVALIDATED")  # depends on the unresolved ruling
        self.assertEqual(sorted(p.split(":")[0] for p in rep["problems"]),
                         ["CONFORMANCE-RULING", "K-NOWORK", "ORCH", "PLAN"])
        self.assertEqual(rep["round"], "v2.3")

    def test_a_committed_round_record_is_measured(self):
        node = cd.NODES["P5-PROPOSAL"]
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            base = {"record": "BASE"}
            base_b = vf._canon(base)
            (root / node.legacy).parent.mkdir(parents=True, exist_ok=True)
            (root / node.legacy).write_bytes(base_b)
            head = vf.bind({"record": "ROUND"}, version_context="v2.3", source_commit="a1" * 20,
                           kernel_digest="t" * 40, predecessor_path=node.legacy, predecessor_bytes=base_b)
            stem = node.v22.rsplit("/", 1)[-1][: -len(".json")]
            (root / vf.V23_DIR).mkdir(parents=True, exist_ok=True)
            (root / vf.V23_DIR / f"{stem}-1.json").write_bytes(vf._canon(head))
            with mock.patch.object(cd, "_checks", return_value={nid: (lambda: []) for nid in cd.NODES}):
                rep = cd.validate(root, round="v2.3")
        e = rep["nodes"]["P5-PROPOSAL"]
        self.assertEqual((e["state"], e["head"]), ("MEASURED", f"{vf.V23_DIR}/{stem}-1.json"))

    def test_the_cli_prints_the_affected_set(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cd.main(["--kernel", "f" * 40, "--affected"])
        self.assertEqual(rc, 1)
        self.assertIn("AFFECTED", out.getvalue())
        self.assertIn("affected node(s)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
