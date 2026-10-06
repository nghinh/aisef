"""P9 / Q5 — the reproduction harness itself (validation/qualification/q5.py), on every platform CI runs: a real
execution recorded, then reproduced with the model stream alone replayed; the two mandatory adversarial cases of QP-9
(a changed request with the same call count does not bind; a changed tool behaviour is a diff, never a satisfied
recording); assertConsumed's refusals; normalization that cannot hide a regression; the recording as expectation only.

Every case here records its own scratch stream in a temporary directory: nothing writes a Q5 corpus; Q5_14 reads 2.0's
(release/Q5-RC2) as history only.
"""

import importlib
import json
import pathlib
import subprocess
import sys
import unittest

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

    def test_Q5_14_HISTORY_2_0_s_item_stays_as_recorded_and_every_2_1_change_is_traced(self):
        from validation.qualification import v21_q5_changes as X
        rc2 = ROOT / "closure-evidence/v2/release/Q5-RC2"
        for rel in ("CORPUS.json", "corpus/post-merge-regression.json", "REPRODUCTION.json", "reproduction/post-merge-regression.json"):
            blob = subprocess.run(["git", "cat-file", "blob", f"{X.V2_0_0}:closure-evidence/v2/release/Q5-RC2/{rel}"], cwd=ROOT,
                                  capture_output=True, check=True).stdout
            self.assertEqual((rc2 / rel).read_bytes().replace(b"\r\n", b"\n"), blob, rel)
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


if __name__ == "__main__":
    unittest.main()
