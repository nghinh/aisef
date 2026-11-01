"""P9 / Q5 — the reproduction harness itself (validation/qualification/q5.py), on every platform CI runs: a real
execution recorded, then reproduced with the model stream alone replayed; the two mandatory adversarial cases of QP-9
(a changed request with the same call count does not bind; a changed tool behaviour is a diff, never a satisfied
recording); assertConsumed's refusals; normalization that cannot hide a regression; the recording as expectation only.

Every case here records its own scratch stream in a temporary directory: nothing writes a Q5 corpus; Q5_14 reads 2.0's
(release/Q5-RC2, release/Q5-RC1, cycle2/Q5-FINAL, cycle2/Q5) as history only; Q5_15 proves q5 refuses to write into any
of them, or anywhere in closure-evidence/ but 2.1's own places; Q5_16-Q5_19 are the V2.1 kernel comparison (validation/qualification/v21_q5_compare.py) and its record.
"""

import contextlib
import importlib
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

from validation.qualification import q5  # noqa: E402

NORMAL = next(i for i in q5.CORPUS if i.id == "normal-completion")


def _record(item=NORMAL):
    base = q5.execute(item, "record")
    assert base["outcomes"] == item.expected_outcomes, (base["outcomes"], base["notes"])
    return base


def _reproduce(base, item=NORMAL, **kw):
    return q5.compare(base, q5.execute(item, "replay", ledger=kw.pop("ledger", base["model_ledger"]), **kw))


class Reproduction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = _record()

    def test_Q5_1_a_recorded_story_reproduces_with_the_model_stream_alone_replayed(self):
        v = _reproduce(self.base)
        self.assertEqual(v["status"], "GREEN", (v["errors"], v["journal_diffs"][:1], v["workspace"]["final"]["diff"], v["notes"]))
        self.assertEqual(v["journal_diffs"], [])
        self.assertEqual((v["tool_executions"], v["tool_diffs"]), (1, 0))               # the scanner ran again, and matched
        self.assertEqual(v["workspace"]["final"]["diff"], [])
        self.assertEqual(v["workspace"]["final"]["tip_expected"], v["workspace"]["final"]["tip_observed"])   # the revision, literally
        mc = v["model_calls"]
        self.assertEqual((mc["expected"], mc["observed"], mc["request_hash_mismatches"], mc["drift_total"]), (2, 2, 0, 0))
        self.assertTrue(mc["consumption"]["ok"], mc["consumption"])
        self.assertEqual(v["network"], {"guarded": True, "socket_attempts": 0})

    def test_Q5_2_every_model_request_is_bound_by_request_hash_not_by_position(self):
        for r in self.base["model_ledger"]:
            self.assertEqual(len(r["request_hash"]), 64)
            self.assertEqual(r["request_hash"], q5.request_hash(r["request"]))
            for key in q5.HEADER_CLASSES[r["header_class"]]["stable"]:
                self.assertIn(key, r["request"], key)
        self.assertEqual([r["header_class"] for r in self.base["model_ledger"]], ["DEVELOPER_IMPLEMENT", "REVIEWER_REVIEW"])

    def test_Q5_3_ADVERSARIAL_a_changed_request_with_the_same_call_count_does_not_bind_the_old_stream(self):
        v = _reproduce(self.base, variant="changed_request")
        self.assertNotEqual(v["status"], "GREEN")
        self.assertEqual(v["replay_failure"]["kind"], "REQUEST_HASH_MISMATCH", v["replay_failure"])
        self.assertGreaterEqual(v["errors"]["replay_request_mismatch"], 1)
        self.assertIn("semantic_hashes", v["replay_failure"]["detail"])

    def test_Q5_4_ADVERSARIAL_a_changed_tool_behaviour_is_a_tool_diff_never_a_satisfied_recording(self):
        v = _reproduce(self.base, variant="changed_tool")
        self.assertNotEqual(v["status"], "GREEN")
        self.assertGreaterEqual(v["tool_diffs"], 1)
        t = v["tool_ledger"][0]
        self.assertEqual(t["verdict"], "DIFF")
        self.assertNotEqual(t["expected_result"]["report_sha256"], t["observed_result"]["report_sha256"])

    def test_Q5_5_a_changed_tool_exit_status_is_a_diff(self):
        v = _reproduce(self.base, variant="tool_exit")
        self.assertGreaterEqual(v["tool_diffs"], 1)
        t = v["tool_ledger"][0]
        self.assertEqual((t["expected_result"]["exit_code"], t["observed_result"]["exit_code"]), (0, 3))

    def test_Q5_6_a_changed_final_workspace_fails_even_with_an_identical_event_stream(self):
        v = _reproduce(self.base, variant="workspace_changed")
        self.assertNotEqual(v["status"], "GREEN")
        self.assertTrue(any(d.startswith("tip:") for d in v["workspace"]["final"]["diff"]), v["workspace"]["final"]["diff"])

    def test_Q5_7_the_recording_is_expectation_only_a_tampered_expected_tool_result_is_reported_as_a_diff(self):
        tampered = dict(self.base)
        tampered["tool_ledger"] = [{**self.base["tool_ledger"][0], "report_sha256": "0" * 64}]
        v = _reproduce(tampered)
        self.assertEqual(v["tool_ledger"][0]["verdict"], "DIFF")          # the current execution, not the record, is the evidence
        self.assertEqual(v["tool_ledger"][0]["observed_result"]["report_sha256"], self.base["tool_ledger"][0]["report_sha256"])

    def test_Q5_8_assertConsumed_rejects_a_missing_item_an_extra_call_and_an_unconsumed_item(self):
        ledger = self.base["model_ledger"]
        v = _reproduce(self.base, ledger=ledger[:1])                          # the reviewer's item is gone: its request is extra
        self.assertEqual(v["replay_failure"]["kind"], "EXTRA_MODEL_CALL")
        self.assertFalse(v["model_calls"]["consumption"]["ok"])
        synthetic = {**ledger[-1], "seq": 3, "request_hash": "f" * 64, "request": {**ledger[-1]["request"], "story_id": "S9"}}
        v = _reproduce(self.base, ledger=ledger + [synthetic])                # one item nobody asks for
        self.assertEqual(v["model_calls"]["consumption"]["missing_unconsumed"], [3])
        self.assertNotEqual(v["status"], "GREEN")

    def test_Q5_9_assertConsumed_rejects_reordering_and_duplicate_consumption(self):
        ledger = self.base["model_ledger"]
        s = q5.ModelStream("replay", ledger=[ledger[1], ledger[0]])
        with self.assertRaises(q5.ReplayMismatch) as cm:
            s.answer(ledger[0]["header_class"], ledger[0]["request"])
        self.assertEqual(cm.exception.kind, "REORDERED_REQUEST")
        s = q5.ModelStream("replay", ledger=ledger)
        s.consume(1)
        with self.assertRaises(q5.DuplicateConsumption):
            s.consume(1)
        s = q5.ModelStream("replay", ledger=ledger)
        with self.assertRaises(q5.ReplayMismatch) as cm:                       # same count, other content: never bound
            s.answer(ledger[0]["header_class"], {**ledger[0]["request"], "criteria": ["C9"]})
        self.assertEqual(cm.exception.kind, "REQUEST_HASH_MISMATCH")

    def test_Q5_10_normalization_drops_time_and_temp_paths_and_nothing_semantic(self):
        tokens = {"/tmp/a": "<TMP>"}
        a = {"seq": 1, "type": "gate/check", "time": 1.0, "data": {"detail": "x", "passed": True}, "source_seqs": []}
        self.assertEqual(q5.normalize_event(a, tokens), q5.normalize_event({**a, "time": 99.0}, tokens))
        p = {**a, "type": "story/resource-released", "data": {"detail": "left /tmp/a/wt", "status": "RESIDUAL"}}
        q = {**p, "data": {"detail": "left /tmp/b/wt", "status": "RESIDUAL"}}
        self.assertEqual(q5.normalize_event(p, {"/tmp/a": "<TMP>"}), q5.normalize_event(q, {"/tmp/b": "<TMP>"}))
        for x, y in ((("tool/result", {"outcome": "COMPLETED", "detail": ""}), ("tool/result", {"outcome": "FAILED", "detail": "exit status 3"})),
                     (("failure/observed", {"code": "X", "owner": "DEVELOPER", "retryable": True}), ("failure/observed", {"code": "X", "owner": "PLAN", "retryable": False})),
                     (("story/commit", {"revision": "a" * 40}), ("story/commit", {"revision": "b" * 40})),
                     (("gate/check", {"detail": "1 test failed"}), ("gate/check", {"detail": "0 tests failed"}))):
            self.assertNotEqual(q5.normalize_event({**a, "type": x[0], "data": x[1]}, tokens), q5.normalize_event({**a, "type": y[0], "data": y[1]}, tokens))
        self.assertTrue(all("time" not in e for e in self.base["journal"]))

    def test_Q5_11_the_probe_is_the_corrected_one_and_the_stream_never_carries_a_tool_result(self):
        from aisef2.probe.python_callable import PythonCallableProbe
        self.assertEqual(PythonCallableProbe.digest, q5.PROBE_DIGEST)
        for r in self.base["model_ledger"]:
            self.assertEqual(set(r["response"]) - {"kind", "files", "message", "detail", "findings"}, set())


def _failures(base, story):
    return [(e["data"]["code"], e["data"]["owner"], e["data"]["retryable"], e["data"]["detail"]) for e in base["journal"]
            if e["type"] == "failure/observed" and e["data"].get("story_id") == story]


def _checks(base, story):
    return [(e["data"]["check"], e["data"]["passed"]) for e in base["journal"]
            if e["type"] == "gate/check" and e["data"]["check"].startswith(f"{story}:")]


class MultiStory(unittest.TestCase):
    """V2.1 (V21-38; validation/qualification/v21_q5_changes.py): 2.0's item `post-merge-regression` — S2's candidate breaks
    S0's preserved `sub` — is the developer's at the candidate (Q5_13); the post-merge path it covered is
    `post-merge-integration-regression`, main moving under a clean candidate (Q5_12); 2.0's record stays (Q5_14)."""

    def assert_as_stated(self, base, item_id):
        """The 2.1 behaviour the B-03d ruling's data states (v21_q5_changes.CHANGES[item]['expectation_2_1']) is this
        execution's: its outcomes, every model call by header class and story, every failure of every story."""
        from validation.qualification import v21_q5_changes as X
        stated = X.CHANGES[item_id]["expectation_2_1"]
        self.assertEqual(base["outcomes"], stated["outcomes"])
        self.assertEqual([f"{r['header_class']} {r['request']['story_id']}" for r in base["model_ledger"]], stated["model_calls"])
        self.assertEqual([{k: e["data"][k] for k in ("story_id", "code", "owner", "retryable", "detail")} for e in base["journal"]
                          if e["type"] == "failure/observed"], stated["failures"])

    def test_Q5_12_a_two_story_run_with_a_post_merge_regression_reproduces(self):
        item = next(i for i in q5.CORPUS if i.id == "post-merge-integration-regression")
        base = _record(item)
        v = _reproduce(base, item)
        self.assertEqual(v["status"], "GREEN", (v["errors"], v["journal_diffs"][:1], v["notes"]))
        self.assertEqual(v["outcomes"]["observed"], {"S0": ["COMMIT"], "S2": ["ROLLBACK"]})
        self.assertEqual(v["model_calls"]["observed"], 4)
        self.assertEqual([r["header_class"] for r in base["model_ledger"]], ["DEVELOPER_IMPLEMENT", "REVIEWER_REVIEW"] * 2)
        self.assertTrue(base["consumption"]["ok"], base["consumption"])                  # every scripted answer was asked for
        self.assertEqual(_failures(base, "S2"), [("POST_MERGE_REGRESSION", "INTEGRATION", False, "post-merge C0: POST_MERGE_REGRESSION")])
        checks = _checks(base, "S2")
        self.assertIn(("S2:proof:C0", True), checks)                                    # the candidate kept S0's behaviour
        self.assertEqual(checks[-2:], [("S2:post-merge:C2", True), ("S2:post-merge:C0", False)])   # the merged revision did not
        self.assert_as_stated(base, item.id)

    def test_Q5_13_a_regression_the_developer_made_is_found_at_the_candidate_retried_and_never_merged(self):
        item = next(i for i in q5.CORPUS if i.id == "developer-regression-at-candidate")
        base = _record(item)
        v = _reproduce(base, item)
        self.assertEqual(v["status"], "GREEN", (v["errors"], v["journal_diffs"][:1], v["notes"]))
        self.assertEqual(v["outcomes"]["observed"], {"S0": ["COMMIT"], "S2": ["RETRY", "ROLLBACK"]})
        self.assertEqual(v["model_calls"]["observed"], 4)
        self.assertEqual([r["header_class"] for r in base["model_ledger"]],
                         ["DEVELOPER_IMPLEMENT", "REVIEWER_REVIEW", "DEVELOPER_IMPLEMENT", "DEVELOPER_IMPLEMENT"])   # S2 is never reviewed
        self.assertTrue(base["consumption"]["ok"], base["consumption"])                  # every scripted answer was asked for
        self.assertEqual(base["model_ledger"][3]["request"]["prior_failures"], ["CONTRACT_UNSATISFIED"])     # fed back to the retry
        self.assertEqual(_failures(base, "S2"), [("CONTRACT_UNSATISFIED", "DEVELOPER", True, "proof of C0: CONTRACT_UNSATISFIED")] * 2)
        checks = _checks(base, "S2")
        self.assertEqual(checks.count(("S2:proof:C0", False)), 2)
        self.assertEqual([c for c, _ in checks if c.endswith(":merge") or ":post-merge:" in c], [])            # nothing merged
        self.assert_as_stated(base, item.id)

    def test_Q5_14_HISTORY_2_0_s_item_stays_as_recorded_and_every_2_1_change_is_traced(self):
        from validation.qualification import v21_q5_changes as X
        rc2 = ROOT / "closure-evidence/v2/release/Q5-RC2"
        for d in ("release/Q5-RC2", "release/Q5-RC1", "cycle2/Q5-FINAL", "cycle2/Q5"):   # closure-evidence/v2/Q5: cycle2_baseline's
            for rel in ("CORPUS.json", "corpus/post-merge-regression.json", "REPRODUCTION.json", "reproduction/post-merge-regression.json"):
                path = f"closure-evidence/v2/{d}/{rel}"
                blob = subprocess.run(["git", "cat-file", "blob", f"{X.V2_0_0}:{path}"], cwd=ROOT, capture_output=True, check=True).stdout
                self.assertEqual((ROOT / path).read_bytes().replace(b"\r\n", b"\n"), blob, path)
            status = lambda rel, d=d: json.loads((ROOT / "closure-evidence/v2" / d / rel).read_text(encoding="utf-8"))["status"]   # noqa: E731
            self.assertEqual((status("REPRODUCTION.json"), status("reproduction/post-merge-regression.json")), ("GREEN", "GREEN"), d)
        load = lambda rel: json.loads((rc2 / rel).read_text(encoding="utf-8"))   # noqa: E731
        corpus, rec = load("CORPUS.json"), load("corpus/post-merge-regression.json")
        self.assertEqual((load("REPRODUCTION.json")["status"], load("reproduction/post-merge-regression.json")["status"]), ("GREEN", "GREEN"))
        quote, row = X.RC2_POST_MERGE_REGRESSION, corpus["items"]["post-merge-regression"]
        self.assertEqual({k: row[k] for k in ("outcomes", "model_calls", "tool_calls", "events", "ledger_digest")} | {"coverage": corpus["coverage"][quote["item"]]},
                         {k: quote[k] for k in ("outcomes", "model_calls", "tool_calls", "events", "ledger_digest", "coverage")})
        self.assertEqual([{"seq": e["seq"], **{k: e["data"][k] for k in ("story_id", "code", "owner", "retryable", "detail")}}
                          for e in rec["journal"] if e["type"] == "failure/observed"], [quote["failure"]])
        by_id = {i.id: i for i in q5.CORPUS}
        self.assertNotIn(quote["item"], by_id)                                  # its meaning changed: the id is not reused
        self.assertEqual(set(corpus["items"]) - {quote["item"]} | set(X.CHANGES), set(by_id))
        self.assertEqual(set(X.UNCHANGED["identical_up_to_kernel_identity"]) | set(X.UNCHANGED["identity_only"]["items"]),
                         set(corpus["items"]) - {quote["item"]})
        for item_id, change in X.CHANGES.items():
            self.assertEqual(change["expectation_2_1"]["outcomes"], by_id[item_id].expected_outcomes, item_id)
            self.assertEqual(len(change["expectation_2_1"]["model_calls"]), len(by_id[item_id].developer) + len(by_id[item_id].reviewer))
            self.assertTrue(change["requirement"] and change["decision"] and change["cause_commit"] == X.V21_38, item_id)
            for name in change["behaviour_tests"]:
                module, cls, method = name.rsplit(".", 2)
                self.assertTrue(callable(getattr(getattr(importlib.import_module(module), cls), method, None)), name)


def _reached(*a, **k):
    raise AssertionError("a q5 writer was reached")


class Writers(unittest.TestCase):
    def test_Q5_15_every_q5_mode_refuses_a_2_0_record_directory_before_it_creates_or_writes_anything(self):
        modes = (["--record"], ["--reproduce"], ["--calibrate"], ["--freeze"], ["--conformance", "start"], ["--conformance", "end"])
        fresh = [f"{rel}/v2.1-attempt" for rel in q5.V2_0_RECORD_DIRS]          # inside one, not yet existing: never created
        outs = [*q5.V2_0_RECORD_DIRS, *fresh, f"{q5.CYCLE1_OUT_REL}/corpus", str(ROOT / "closure-evidence/v2/release/Q5-RC2")]
        outs += [rel.upper() for rel in q5.V2_0_RECORD_DIRS if (ROOT / rel.upper()).exists()]   # a case-insensitive file system
        # the allow-list: any other 2.0-era record directory (Q4's, P10's), closure-evidence itself, a sibling of a 2.0 Q5
        # directory or of 2.1's, a 2.1 candidate's directory that is not the frozen one; the repository named in another case
        outs += ["closure-evidence/v2/Q4", "closure-evidence/v2/cycle2/Q4-FINAL", "closure-evidence/v2/P10", "closure-evidence",
                 "closure-evidence/v2/cycle2/Q5-FINAL-2", f"{q5.V21_DIR}-attempt", "closure-evidence/v2/release/Q5-2.1.0-RC1"]
        alt = pathlib.Path(str(ROOT).swapcase())
        outs += [str(alt / "closure-evidence/v2/Q4")] if alt.exists() else []
        # the live state decides whether a 2.1 candidate is frozen: its own directory is then the one allowed release
        # directory, not a must-refuse (the mocked frozen/unfrozen cases below pin both behaviours)
        allowed = q5.release_q5_dir()
        outs = [o for o in outs if allowed is None or (ROOT / o).resolve() != allowed.resolve()]
        from validation.qualification import q4_aggregate
        with mock.patch.multiple(q5, record=_reached, reproduce=_reached, calibrate=_reached, freeze=_reached), \
                mock.patch.object(q4_aggregate, "conformance", _reached), mock.patch.object(pathlib.Path, "mkdir", _reached):
            for out in outs:                                               # refused before a directory is made: nothing to remove
                for m in modes:
                    with contextlib.redirect_stdout(io.StringIO()) as said:
                        self.assertEqual(q5.main([*m, "--out", out]), 2, (m, out))
                    self.assertIn("REFUSED", said.getvalue(), (m, out))
            for rel in fresh:
                self.assertFalse((ROOT / rel).exists(), rel)
        with mock.patch.multiple(q5, record=_reached, reproduce=_reached, calibrate=_reached, freeze=_reached), \
                tempfile.TemporaryDirectory() as t:                        # a directory of its own reaches the writer
            self.assertIsNone(q5.refused_out(pathlib.Path(t)))
            with self.assertRaisesRegex(AssertionError, "a q5 writer was reached"):
                q5.main(["--freeze", "--out", t])
        self.assertIsNone(q5.refused_out(ROOT / q5.V21_DIR))
        self.assertIsNone(q5.refused_out(ROOT / q5.V21_DIR / "Q5-2.1.0-scratch"))
        rc21 = {"mode": "release", "q5_out_rel": "closure-evidence/v2/release/Q5-2.1.0-RC1", "freeze": {"rc": {"version": "2.1.0"}}}
        with mock.patch.object(q5.C, "candidate", return_value=rc21):     # a frozen 2.1 candidate: its own directory, exactly
            self.assertIsNone(q5.refused_out(ROOT / "closure-evidence/v2/release/Q5-2.1.0-RC1"))
            for rel in ("closure-evidence/v2/release/Q5-2.1.0-RC1/corpus", "closure-evidence/v2/release/Q5-2.1.0-RC10",
                        "closure-evidence/v2/release/Q5-RC2", "closure-evidence/v2/cycle2/Q5-FINAL-2"):
                self.assertIsNotNone(q5.refused_out(ROOT / rel), rel)
        rc20 = {"mode": "release", "q5_out_rel": "closure-evidence/v2/release/Q5-RC3", "freeze": {"rc": {"version": "2.0.0"}}}
        with mock.patch.object(q5.C, "candidate", return_value=rc20):     # a 2.0.0 candidate's: never
            self.assertIsNotNone(q5.refused_out(ROOT / "closure-evidence/v2/release/Q5-RC3"))
        none = {"mode": "cycle2", "q5_out_rel": "closure-evidence/v2/cycle2/Q5-NEXT", "freeze": None}
        with mock.patch.object(q5.C, "candidate", return_value=none):     # no candidate frozen: no release directory at all
            self.assertIsNotNone(q5.refused_out(ROOT / "closure-evidence/v2/cycle2/Q5-NEXT"))
        self.assertIsNotNone(q5.refused_out(ROOT / "closure-evidence/v2/cycle2/Q5-FINAL-2"))   # a sibling: not 2.1's either


def _obs(**over):
    """A minimal observation in the shape v21_q5_compare.observation gives."""
    spec = "PPS-" + "a" * 64
    base = {"outcomes": {"S1": ["COMMIT"]}, "requests": [{"semantic_hashes": {"C3": "s" * 64}, "plan_hash": "p" * 64}],
            "journal": [{"type": "probe/evaluated", "data": {"record": {"spec_id": spec, "passed": True}}},
                        {"type": "story/resource-acquired", "data": {"resource": f"probe {spec} [admission 1]"}}]}
    return json.loads(json.dumps(base)) | over


from tests.v2.sealing_gate import sealing  # noqa: E402 — ROADMAP-2.2 F1: the sealing tier's gate


class KernelComparison(unittest.TestCase):
    """V2.1: validation/qualification/v21_q5_compare.py — the engineering measurement v21_q5_changes cites."""

    @classmethod
    def setUpClass(cls):
        from validation.qualification import v21_q5_compare as M
        cls.M = M

    def test_Q5_16_classification_identical_identity_only_differs(self):
        M, other = self.M, "PPS-" + "b" * 64
        self.assertEqual(M.classify(_obs(), _obs()), {"classification": "identical", "identity_fields": {}, "other_fields": {}})
        moved = _obs()
        moved["journal"][0]["data"]["record"]["spec_id"] = other
        moved["journal"][1]["data"]["resource"] = f"probe {other} [admission 1]"
        moved["requests"][0].update(semantic_hashes={"C3": "t" * 64}, plan_hash="q" * 64)
        self.assertEqual(M.classify(_obs(), moved), {"classification": "identity-only", "other_fields": {}, "identity_fields": {
            "journal probe/evaluated: data.record.spec_id": 1, "journal story/resource-acquired: data.resource": 1,
            "requests[].plan_hash": 1, "requests[].semantic_hashes.C3": 1}})
        renamed = _obs()
        renamed["journal"][1]["data"]["resource"] = f"probe {other} [admission 2]"      # more than the spec id
        failed = _obs()
        failed["journal"][0]["data"]["record"]["passed"] = False
        longer = _obs()
        longer["journal"].append(longer["journal"][0])
        criterion = _obs()                                             # a request gains a criterion: structure, not identity
        criterion["requests"][0]["semantic_hashes"]["C9"] = "u" * 64
        gained = _obs()                                                # a probe record gains a field an identity is named by
        gained["journal"][0]["data"]["record"]["probe_digest"] = "d" * 64
        lost = _obs()
        lost["journal"][0]["data"]["record"]["spec_id"] = None
        for new, field in ((renamed, "journal story/resource-acquired: data.resource"), (failed, "journal probe/evaluated: data.record.passed"),
                           (longer, "journal"), (_obs(outcomes={"S1": ["ROLLBACK"]}), "outcomes.S1[]"), (moved | {"outcomes": {}}, "outcomes.S1"),
                           (criterion, "requests[].semantic_hashes.C9"), (gained, "journal probe/evaluated: data.record.probe_digest"),
                           (lost, "journal probe/evaluated: data.record.spec_id")):
            got = M.classify(_obs(), new)
            self.assertEqual((got["classification"], list(got["other_fields"])), ("differs", [field]), field)
        obs = _obs() | {"errors": {}, "notes": [], "consumption": {"ok": True}, "replay_failure": None, "tool_ledger": [],
                        "final_workspace": None, "replay": {}}
        obs["requests"][0] |= {"header_class": "DEVELOPER_IMPLEMENT", "story_id": "S1"}
        obs["journal"][0]["data"]["record"] |= {"probe_id": "probe.cli_invocation", "probe_digest": "d" * 64}
        obs["journal"].append(json.loads(json.dumps(obs["journal"][0])))
        obs["journal"][-1]["data"]["record"]["probe_digest"] = "e" * 64
        self.assertEqual(M.summary(obs)["probe_digests"], {"probe.cli_invocation": ["d" * 64, "e" * 64]})   # each side's, by value

    def test_Q5_17_the_items_are_2_0_s_and_2_1_s_with_rc2_s_definitions_and_the_record_is_written_once_outside_2_0(self):
        M = self.M
        got = [(i.id, a, b) for i, a, b in M.items()]
        self.assertEqual(got, [(i.id, i.id != "developer-regression-at-candidate" and i.id != "post-merge-integration-regression", True)
                               for i in q5.CORPUS] + [("post-merge-regression", True, False)])
        self.assertEqual(M.definition_problems(), [])
        item, a, b = M.items()[0]
        changed = q5.Item(item.id, item.covers, item.stories, item.developer + item.developer, item.reviewer, kind=item.kind,
                          expected_outcomes=item.expected_outcomes)
        with mock.patch.object(M, "items", return_value=[(changed, a, b)]):
            self.assertEqual(M.definition_problems(), [f"{item.id}: the definition measured is not {M.RC2}'s"])
        old = next(i for i, _, in_2_1 in M.items() if not in_2_1)
        foreign = q5.Item(old.id, old.covers, (q5.Story("S0", (("C3", "INTRODUCE"),)),), old.developer, old.reviewer)
        with mock.patch.object(M, "items", return_value=[(foreign, True, False)]):
            self.assertIn(f"{old.id}: rebuilt with a criterion outside q5.CONTRACTS (its kind is not recorded)", M.definition_problems())
        with tempfile.TemporaryDirectory() as t:
            fresh, existing = pathlib.Path(t) / "Q5-KERNEL-COMPARISON.json", pathlib.Path(t) / "there.json"
            existing.write_text("{}", encoding="utf-8")
            self.assertIsNone(M.refused(fresh))
            self.assertIn("exists", M.refused(existing))
            with mock.patch.object(M, "derive", side_effect=AssertionError("measured")), contextlib.redirect_stdout(io.StringIO()):
                for out in (existing, ROOT / "closure-evidence/v2/release/Q5-RC2/Q5-KERNEL-COMPARISON.json", ROOT / "validation/x.json"):
                    self.assertEqual(M.write(out), 2, out)
                with mock.patch.object(M, "dirty", return_value=[" M aisef2/x.py"]):   # uncommitted: refused before measuring
                    self.assertEqual(M.write(fresh), 2)
            with mock.patch.object(M, "dirty", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
                with mock.patch.object(M, "derive", return_value={"tree_dirty": ["?? validation/x.py"], "summary": {}}):
                    self.assertEqual(M.write(fresh), 2)                       # the tree moved while measured: nothing written
                self.assertFalse(fresh.exists())
                head = M.C.git("rev-parse", "HEAD")
                with mock.patch.object(M, "derive", return_value={"tree_dirty": [], "summary": {}, "execution_commit": "0" * 40}):
                    self.assertEqual(M.write(fresh), 2)                       # HEAD moved while measured: nothing written
                self.assertFalse(fresh.exists())
                with mock.patch.object(M, "derive", return_value={"tree_dirty": [], "summary": {}, "execution_commit": head}):
                    self.assertEqual(M.write(fresh), 0)                       # clean: written once
                self.assertEqual(json.loads(fresh.read_text(encoding="utf-8")),
                                 {"tree_dirty": [], "summary": {}, "execution_commit": head})
                self.assertIn("exists", M.refused(fresh))
        with mock.patch.object(M.C, "git", return_value=" M aisef2/x.py\n?? validation/y.py") as g:
            self.assertEqual(M.dirty(), [" M aisef2/x.py", "?? validation/y.py"])
        g.assert_called_once_with("status", "--porcelain", "--", "aisef2", "tests/v2", "validation")
        self.assertIsNone(M.refused(ROOT / M.V21_DIR / "never-written.json"))
        self.assertIn("outside closure-evidence/v2/v2.1", M.refused(ROOT / "closure-evidence/v2/cycle2/Q5/x.json"))
        alt = pathlib.Path(str(ROOT).swapcase())
        if alt.exists():                                                   # the repository named in another case is the repository
            self.assertIn("outside closure-evidence/v2/v2.1", M.refused(alt / "closure-evidence/v2/cycle2/Q5/x.json"))
            self.assertIn("outside closure-evidence/v2/v2.1", M.refused(alt / "validation/x.json"))

    @sealing
    def test_Q5_18_check_binds_the_record_to_q5_both_kernels_the_corpus_and_the_ruling_s_data(self):
        from validation.qualification import v21_q5_changes as X
        M = self.M
        stated = {i: "identical" for i in X.UNCHANGED["identical_up_to_kernel_identity"]} | \
            {i: "identity-only" for i in X.UNCHANGED["identity_only"]["items"]} | {i: "differs" for i in [*X.CHANGES, "post-merge-regression"]}
        now = M.bindings()
        helpers = {"fixture_helpers": now["fixture_helpers"]}
        rec = {"bindings": now, "kernels": {"v2.0.0": helpers, "2.1": helpers}, "tree_dirty": [],
               "items": {i.id: {"in_2_0_corpus": a, "in_2_1_corpus": b, "classification": stated[i.id],
                                "2.1": {"outcomes": i.expected_outcomes, "consumption_ok": True, "replay": {"status": "GREEN"}}}
                         for i, a, b in M.items()}}
        q = X.RC2_POST_MERGE_REGRESSION
        rec["items"][q["item"]]["v2.0.0"] = {"outcomes": q["outcomes"], "model_calls": ["call"] * q["model_calls"], "tool_calls": q["tool_calls"],
                                            "events": q["events"], "failures": [q["failure"]]}
        ident = X.UNCHANGED["identity_only"]
        for n, (kind, pid) in enumerate(ident["probe_ids_by_kind"].items()):   # one probe per identity-only item, both sides
            item = rec["items"][ident["items"][n]]
            old, new = ident["probe_digests_by_kind"][kind]
            item["v2.0.0"] = {"probe_digests": {pid: [old + "0" * 52]}}
            item["2.1"]["probe_digests"] = {pid: [new + "0" * 52]}
        rec["summary"] = {c: sorted(k for k, v in rec["items"].items() if v["classification"] == c) for c in ("identical", "identity-only", "differs")}
        with tempfile.TemporaryDirectory() as t:
            path = pathlib.Path(t) / "r.json"

            def check(edit=lambda r: None):
                r = json.loads(json.dumps(rec))
                edit(r)
                path.write_text(json.dumps(r), encoding="utf-8")
                with mock.patch.object(M, "bindings", return_value=now):
                    return M.check(path)

            path.write_text(json.dumps(rec), encoding="utf-8")
            self.assertEqual(M.check(path), [])                                       # the bindings derived for real
            self.assertEqual(check(), [])
            self.assertEqual(check(lambda r: r["bindings"].update(kernel_2_1="0" * 64)), [f"stale: kernel_2_1 recorded {'0' * 64}, now {now['kernel_2_1']}"])
            self.assertEqual(check(lambda r: r["bindings"].update(kernel_v2_0_0="0" * 64)), [f"stale: kernel_v2_0_0 recorded {'0' * 64}, now {now['kernel_v2_0_0']}"])
            q5_rel = "validation/qualification/q5.py"
            self.assertEqual(check(lambda r: r["bindings"].update({q5_rel: "0" * 64})), [f"stale: {q5_rel} recorded {'0' * 64}, now {now[q5_rel]}"])
            got = check(lambda r: r["items"]["normal-completion"]["2.1"].update(outcomes={"S1": ["ROLLBACK"]}))
            self.assertEqual(len(got), 1)
            self.assertTrue(got[0].startswith("normal-completion: 2.1 measured {'S1': ['ROLLBACK']}"), got)
            self.assertEqual(len(check(lambda r: r["items"]["post-merge-integration-regression"]["2.1"]["replay"].update(status="FAILED"))), 1)
            self.assertEqual(len(check(lambda r: r["items"]["pre-satisfied"]["2.1"].update(consumption_ok=False))), 1)

            def reclassify(r):
                r["items"]["normal-completion"]["classification"] = "identity-only"
                r["summary"] = {c: sorted(k for k, v in r["items"].items() if v["classification"] == c) for c in ("identical", "identity-only", "differs")}
            self.assertEqual(len(check(reclassify)), 2)                               # identical and identity-only both disagree with the data
            self.assertIn("the summary is not the items' classification", check(lambda r: r["summary"]["differs"].pop()))
            got = check(lambda r: r["items"].pop("post-merge-regression"))                # not measured, so neither classified nor summarised
            self.assertEqual([g.split(":")[0] for g in got], ["the items measured are not 2.0's and 2.1's corpora", "post-merge-regression",
                                                              "the summary is not the items' classification", "differs"], got)
            self.assertEqual(check(lambda r: r.update(tree_dirty=["?? validation/x.py"])), ["measured on a tree with uncommitted changes: ['?? validation/x.py']"])
            self.assertEqual(check(lambda r: r.pop("tree_dirty")), ["measured on a tree with uncommitted changes: None"])
            self.assertEqual(check(lambda r: r["items"]["post-merge-regression"]["v2.0.0"].update(events=144)),
                             [f"post-merge-regression: the v2.0.0 kernel did not measure what {q['source']} recorded"])
            self.assertEqual(check(lambda r: r["items"]["post-merge-regression"]["v2.0.0"]["failures"][0].update(seq=135)),
                             [f"post-merge-regression: the v2.0.0 kernel did not measure what {q['source']} recorded"])
            cli = rec["items"][ident["items"][0]]
            self.assertEqual(check(lambda r: r["items"][ident["items"][0]]["2.1"]["probe_digests"].update({"probe.cli_invocation": ["f" * 64]})),
                             [f"probe.cli_invocation: measured {cli['v2.0.0']['probe_digests']['probe.cli_invocation']} -> {['f' * 64]}, "
                              "v21_q5_changes states d42449fd8e3a -> 330ae4a88cc8"])
            self.assertEqual(check(lambda r: r["items"][ident["items"][0]]["v2.0.0"]["probe_digests"].update({"probe.cli_invocation": ["0" * 64]})),
                             [f"probe.cli_invocation: measured {['0' * 64]} -> {cli['2.1']['probe_digests']['probe.cli_invocation']}, "
                              "v21_q5_changes states d42449fd8e3a -> 330ae4a88cc8"])   # the v2.0.0 side's own prefix is checked
            self.assertEqual(len(check(lambda r: r["items"][ident["items"][0]]["v2.0.0"]["probe_digests"]["probe.cli_invocation"].append("d42449fd8e3a" + "1" * 52))), 1)
            self.assertEqual(len(check(lambda r: r["items"][ident["items"][1]]["2.1"]["probe_digests"].update({"probe.file_artifact": []}))), 1)
            self.assertEqual(check(lambda r: [r["items"][ident["items"][3]][side].pop("probe_digests") for side in ("v2.0.0", "2.1")]),
                             [f"probes measured {sorted(set(ident['probe_ids_by_kind'].values()) - {'probe.python_callable_v2'})}, "
                              f"v21_q5_changes states {sorted(ident['probe_ids_by_kind'].values())}"])
            self.assertEqual(check(lambda r: r["kernels"]["2.1"].update(fixture_helpers={})),
                             ["q5's fixture helpers differ between the two kernels' trees: the comparison is not the kernels' alone"])
        self.assertEqual(M.check(pathlib.Path(t) / "absent.json"), [f"{pathlib.Path(t) / 'absent.json'}: no record (v21_q5_compare.py --write)"])

    @sealing
    def test_Q5_19_the_kernel_comparison_record_binds_this_tree(self):
        """Red until the lead writes closure-evidence/v2/v2.1/Q5-KERNEL-COMPARISON.json (v21_q5_compare.py --write) on the
        final 2.1 kernel; then it fails whenever q5.py, the tool, the fixture helpers or the kernel move."""
        self.assertEqual(self.M.check(), [])


if __name__ == "__main__":
    unittest.main()
