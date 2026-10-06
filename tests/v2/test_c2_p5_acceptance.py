"""C2-P5 acceptance boundary: the real approvals are content-addressed, bound to the accepted proposal and given by the
established owner identity; a tampered or synthetic approval is refused; the acceptance re-derives on this tree — on 2.1
(owner B-03a) as the 2.0 record kept as history plus the v2.1 re-verification, compared exactly."""

import contextlib
import copy
import dataclasses
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from aisef2.plan.obligation import Plan
from validation.qualification import p5_acceptance as A


def _doc() -> dict:
    return json.loads((A.ROOT / A.APPROVALS_REL).read_text(encoding="utf-8"))


def _set(doc, path, value):
    """`doc` with the value at `path` (keys and indexes) replaced."""
    at = doc
    for k in path[:-1]:
        at = at[k]
    at[path[-1]] = value
    return doc


RUNNER, AID = "validation/qualification/p5_falsifiability.py", "validation/qualification/p10_contracts.py"


class Approvals(unittest.TestCase):
    def test_one_real_approval_per_retained_contract_by_the_owner(self):
        doc = _doc()
        self.assertEqual(A.approvals_problems(doc), [])
        self.assertEqual(doc["count"], 59)
        self.assertEqual({r["approver"] for r in doc["approvals"]}, {A.OWNER})
        self.assertEqual({r["contract_id"] for r in doc["approvals"]}, {c.id for c in A.contracts().values()})
        self.assertEqual(doc["binds"]["proposal_digest"], A.ACCEPTED["proposal_digest"])
        self.assertIn("closure-evidence/v2/AISEF-V2-RFC-APPROVAL.json", doc["approver_identity"]["established_by"])

    def test_a_tampered_approval_is_refused(self):
        doc = _doc()
        bad = copy.deepcopy(doc)
        bad["approvals"][0]["contract_hash"] = "0" * 64
        self.assertTrue(A.approvals_problems(bad))
        bad = copy.deepcopy(doc)
        bad["approvals"].pop()
        self.assertTrue(A.approvals_problems(bad))

    def test_a_synthetic_approver_is_refused(self):
        bad = copy.deepcopy(_doc())
        bad["approvals"][0]["approver"] = A._aid().SYNTHETIC_APPROVER
        problems = A.approvals_problems(bad)
        self.assertTrue(any("synthetic" in p for p in problems))
        self.assertTrue(any("is not human:owner" in p for p in problems))


class Acceptance(unittest.TestCase):
    def test_the_acceptance_re_derives_on_this_tree(self):
        # V2.1 (owner B-03a): the owner's 2.0 acceptance is history (its v2.0.0 blob, its verdict, the closed C2-P5 history,
        # the approvals never rewritten); the boundary re-derives on this tree as the v2.1 re-verification, exactly
        self.assertEqual(A.history_problems(), [])
        self.assertEqual(A.reverification_problems(), [])

    def test_the_admission_holds_only_under_every_real_approval(self):
        doc = json.loads((A.ROOT / A.OUT_REL).read_text(encoding="utf-8"))
        adm = doc["verification"]["admission"]
        self.assertEqual((adm["admitted"], adm["checks_passed"], adm["synthetic_approval_used"]), (True, 9, False))
        self.assertEqual(len(adm["approvals_given"]), 59)
        self.assertFalse(adm["one_approval_removed"]["admitted"])
        self.assertFalse(adm["no_approvals"]["admitted"])
        self.assertEqual(doc["verification"]["semantic_change"], "NONE")

    def test_a_2_0_record_not_its_v2_0_0_blob_is_not_history_and_no_writer_writes_outside_v2_1(self):
        from validation.qualification import rebind
        with mock.patch.object(rebind, "lf_sha_at", return_value="0" * 64):
            self.assertEqual(A.history_problems(), [f"{A.OUT_REL} is not its v2.0.0 blob (history)",
                                                    f"{A.APPROVALS_REL} is not its v2.0.0 blob (history)"])
            self.assertIn(f"{A.PROPOSAL_REL} is not its v2.0.0 blob (history)", A.proposal_history_problems())
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(A, "ROOT", pathlib.Path(tmp)):   # never the real tree
            for rel in (A.OUT_REL, A.PROPOSAL_REL, "closure-evidence/v2/C2-P5-ACCEPTANCE-REVERIFICATION.json"):
                with self.assertRaises(SystemExit):
                    A._write_once(rel, {})
            self.assertEqual(list(pathlib.Path(tmp).rglob("*")), [])
            A._write_once(A.V21_OUT_REL, {"a": 1})                    # a v2.1 record is written once ...
            with self.assertRaises(SystemExit) as refused:            # ... and an existing one is never rewritten
                A._write_once(A.V21_OUT_REL, {"b": 2})
            self.assertIn("exists", str(refused.exception))
            self.assertEqual(json.loads((pathlib.Path(tmp) / A.V21_OUT_REL).read_text(encoding="utf-8")), {"a": 1})
            self.assertEqual([f.relative_to(tmp).as_posix() for f in pathlib.Path(tmp).rglob("*") if f.is_file()], [A.V21_OUT_REL])

    def test_a_missing_2_0_record_is_a_history_problem_never_an_exception(self):
        is_file = pathlib.Path.is_file
        for rel, history, expected in ((A.OUT_REL, A.history_problems, [f"{A.OUT_REL} is not its v2.0.0 blob (history)"]),
                                       (A.HISTORY_REL, A.history_problems, ["the closed C2-P5 history changed"]),
                                       (A.PROPOSAL_REL, A.proposal_history_problems, [f"{A.PROPOSAL_REL} is not its v2.0.0 blob (history)",
                                                                                      f"{A.PROPOSAL_REL} is not the accepted candidate's"])):
            missing = (A.ROOT / rel).as_posix()
            with self.subTest(rel), mock.patch.object(pathlib.Path, "is_file", autospec=True,
                                                     side_effect=lambda p, m=missing: p.as_posix() != m and is_file(p)):
                self.assertEqual(history(), expected)

    def test_a_refused_re_verification_run_is_kept_outside_the_evidence_tree(self):
        rec = {"problems": ["guard checker_calibration: exit 1"], "verdict": "PROBLEMS", "guards": {"checker_calibration": {"exit": 1}}}
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as kept, tempfile.TemporaryDirectory() as fallback, \
                mock.patch.object(A, "ROOT", pathlib.Path(tmp)):                         # never the real tree
            root, kept = pathlib.Path(tmp), pathlib.Path(kept).resolve()
            with mock.patch.dict(os.environ, {"AISEF_FAILED_RUN_DIR": str(kept)}), mock.patch.object(A, "reverify", return_value=rec), \
                    self.assertRaises(SystemExit) as refused:
                A.write_v21()
            files = sorted(kept.iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text(encoding="utf-8")), rec)          # the full record, kept
            self.assertIn(f"guard checker_calibration: exit 1 — the run is kept at {files[0]}", str(refused.exception))
            self.assertEqual(list(root.rglob("*")), [])                                      # nothing under closure-evidence
            for inside in (root / "closure-evidence", root / "closure-evidence" / "v2" / "v2.1"):  # never the evidence tree
                with self.subTest(inside=inside), mock.patch.dict(os.environ, {"AISEF_FAILED_RUN_DIR": str(inside)}), \
                        mock.patch.object(A.tempfile, "gettempdir", return_value=fallback):
                    self.assertEqual(pathlib.Path(A.keep_failed_run(A.V21_OUT_REL, rec)).parent, pathlib.Path(fallback).resolve())
            self.assertEqual(list(root.rglob("*")), [])
            (root / A.V21_OUT_REL).parent.mkdir(parents=True)
            (root / A.V21_OUT_REL).write_text("{}", encoding="utf-8")
            with mock.patch.object(A, "reverify", side_effect=AssertionError("run")), self.assertRaises(SystemExit) as refused:
                A.write_v21()                                                              # an existing record: before the run
            self.assertIn("exists", str(refused.exception))

    def test_a_guard_run_is_recorded_with_its_time_never_rounded_to_zero(self):
        done = mock.Mock(returncode=0, stdout="PASS\n", stderr="")
        for clock, seconds, problems in (([0.0, 0.0004], 0.001, []), ([0.0, 1.23456], 1.235, []),
                                         ([1.0, 1.0], 0, [f"guard {k}: not a recorded run of its command" for k in A.GUARDS])):
            with self.subTest(clock=clock), mock.patch.object(A.subprocess, "run", return_value=done), \
                    mock.patch.object(A.time, "monotonic", side_effect=clock * len(A.GUARDS)):
                ran = A.guards()
                self.assertEqual({g["seconds"] for g in ran.values()}, {seconds})
                self.assertEqual(A.guard_problems(ran), problems)


class V21Records(unittest.TestCase):
    """The v2.1 proposal envelope, the recorded guard runs and the re-verification's binding of the v2.1 falsifiability
    record (owner B-03a), each failing for its own reason."""

    def test_the_v2_1_proposal_is_the_aid_s_record_verbatim_and_claims_no_approval(self):
        rec = {"verdict": "v", "plan": {"plan_hash": "p"}}
        doc = A.v21_proposal(rec)
        self.assertEqual(sorted(doc), ["record", "v2_1"])
        self.assertIs(doc["record"], rec)
        self.assertEqual(doc["v2_1"]["authority"], A.B03_REF)
        self.assertEqual(doc["v2_1"]["derived_from"], {"path": A.PROPOSAL_REL,
                                                        "blob_at_v2_0_0": A._git("rev-parse", f"{A.V2_0_0}:{A.PROPOSAL_REL}")})
        self.assertEqual(sorted(doc["v2_1"]), ["authority", "derived_from", "rule"])     # no approval, no acceptance field
        entry = next(e for e in json.loads((A.ROOT / A.DECISIONS_REL).read_text(encoding="utf-8"))["entries"] if e["id"] == A.B03_ID)
        self.assertEqual((entry["seq"], "B-03a" in entry["decision"]), (A.B03_REF["seq"], True))

    def test_the_v2_1_proposal_is_current_only_exactly(self):
        derived = A._aid().record()
        good = A.v21_proposal(copy.deepcopy(derived))
        cases = {"exact": (good, True, []), "verbatim, no envelope": (derived, False, None)}
        bad = copy.deepcopy(good)
        bad["v2_1"]["authority"] = "owner ruling 2026-09-30"
        cases["2.0 authority"] = (bad, False, ["v2_1.authority"])
        bad = copy.deepcopy(good)
        bad["record"]["identities"]["admission_engine_digest"] = "0" * 64
        cases["engine digest"] = (bad, False, ["record.identities.admission_engine_digest"])
        for name, (committed, current, paths) in cases.items():
            with self.subTest(name), mock.patch.object(A, "_json_or_none", return_value=committed):
                r = A.v21_proposal_currency()
                self.assertEqual(r["current"], current)
                if paths is not None:
                    self.assertEqual(r["differing_paths"], paths)

    def test_recorded_guard_runs_must_be_runs_of_their_commands(self):
        good = {k: {"command": "python -P " + " ".join(v), "exit": 0, "tail": ["PASS"], "seconds": 0.1} for k, v in A.GUARDS.items()}
        self.assertEqual(A.guard_problems(good), [])
        k = next(iter(A.GUARDS))
        for change, why in (({"command": "SCRATCH DEMO — not a guard run"}, "not a recorded run of its command"),
                            ({"seconds": 0}, "not a recorded run of its command"),
                            ({"seconds": True}, "not a recorded run of its command"),
                            ({"tail": "PASS"}, "not a recorded run of its command"),
                            ({"exit": 1}, "exit 1")):
            with self.subTest(change):
                bad = copy.deepcopy(good)
                bad[k].update(change)
                self.assertEqual(A.guard_problems(bad), [f"guard {k}: {why}"])
        bad = copy.deepcopy(good)
        del bad[k]
        self.assertEqual(A.guard_problems(bad), [f"the recorded guard runs are not exactly {sorted(A.GUARDS)}"])
        self.assertEqual(A.guard_problems({}), [f"the recorded guard runs are not exactly {sorted(A.GUARDS)}"])

    @contextlib.contextmanager
    def on_2_1(self):
        """This tree once its v2.1 records exist, served to the readers from memory or a temp file and never written into
        the repository: the v2.1 proposal (the aid's record in its envelope, or state['proposal']), the falsifiability
        record (2.0's run made this tree's — its plan, kernel, runner, aid and semantic hashes — then `as_v21`:
        state['fals']) and the re-verification (the file state['reverification'] names)."""
        from validation.qualification import p5_falsifiability as pf
        derived = A._aid().record()
        written = {rel: {"path": rel, "sha256": c * 64} for rel, c in ((A.V21_PROPOSAL_REL, "f"), (pf.V21_OUT_REL, "e"))}
        files, docs = A._file, A._json_or_none
        two_oh = json.loads((A.ROOT / A.FALSIFIABILITY_REL).read_text(encoding="utf-8"))
        state = {"derived": derived, "two_oh": two_oh}

        def json_or_none(rel):
            if rel == A.V21_PROPOSAL_REL:
                return state.get("proposal") or A.v21_proposal(derived)
            if rel == pf.V21_OUT_REL:
                return state.get("fals")
            if rel == A.V21_OUT_REL:
                return json.loads(state["reverification"].read_text(encoding="utf-8")) if state.get("reverification") else None
            return docs(rel)

        with mock.patch.object(A, "_file", side_effect=lambda rel: written.get(rel) or files(rel)), \
                mock.patch.object(A, "_json_or_none", side_effect=json_or_none):
            # run() on 2.1 as recorded (2.0's run with this tree's plan, kernel, runner, aid and semantic hashes), made the
            # v2.1 record
            run = copy.deepcopy(two_oh)
            run["identities"].update(plan_hash=derived["plan"]["plan_hash"], aisef2_tree=A._git("rev-parse", "HEAD:aisef2"),
                                     runner=A._file(RUNNER), authoring_aid=A._file(AID))
            semantic = {s["spec_id"]: s["semantic_hash"] for s in derived["specs"]}
            for r in run["specs"]:
                r["semantic_hash"] = semantic[r["spec_id"]]
            state["fals"] = pf.as_v21(run)
            yield state

    def test_the_re_verification_binds_the_v2_1_falsifiability_record_to_2_1(self):
        from validation.qualification import p5_falsifiability as pf
        with self.on_2_1() as state:
            good, two_oh = state["fals"], state["two_oh"]

            def problems(fals):
                state["fals"] = fals
                return [p for p in A.reverify(run_guards=False)["problems"] if p.startswith(pf.V21_OUT_REL)]

            self.assertEqual(problems(good), [])
            self.assertEqual(good["identities"]["probe_execution_digests"],
                             pf.probe_execution_digests(r["probe_id"] for r in state["derived"]["specs"]))
            # the 2.0 record verbatim (what run() alone gives): its header, its proposal, its kernel, runner and aid, no
            # execution digests, its plan and hashes
            self.assertEqual(problems(two_oh), [f"{pf.V21_OUT_REL}: {k} is false" for k in (
                "header_is_the_v21_one", "names_the_v21_proposal", "kernel_is_this_tree_s", "runner_is_this_tree_s",
                "authoring_aid_is_this_tree_s", "probe_execution_digests_are_this_tree_s", "plan_hash_is_this_tree_s",
                "semantic_hashes_are_this_tree_s")])
            probe, module, row = next(iter(good["identities"]["probe_execution_digests"])), next(iter(good["tests"])), good["specs"][0]
            for name, path, value in (("header_is_the_v21_one", ("authority",), two_oh["authority"]),
                                      ("header_is_the_v21_one", ("supersedes",), two_oh["supersedes"]),
                                      ("names_the_v21_proposal", ("identities", "proposal"), two_oh["identities"]["proposal"]),
                                      ("names_the_v21_proposal", ("identities", "proposal_digest"), A.ACCEPTED["proposal_digest"]),
                                      ("p5_corpus_is_this_tree_s", ("identities", "p5_mutants", "corpus_sha256"), "0" * 64),
                                      ("kernel_is_this_tree_s", ("identities", "aisef2_tree"), two_oh["identities"]["aisef2_tree"]),
                                      ("runner_is_this_tree_s", ("identities", "runner", "sha256"), "0" * 64),
                                      ("authoring_aid_is_this_tree_s", ("identities", "authoring_aid", "sha256"), "0" * 64),
                                      ("probe_execution_digests_are_this_tree_s", ("identities", "probe_execution_digests", probe), "0" * 64),
                                      ("probe_execution_digests_are_this_tree_s", ("identities", "probe_execution_digests"), {}),
                                      ("plan_hash_is_this_tree_s", ("identities", "plan_hash"), A.ACCEPTED["plan_hash"]),
                                      ("semantic_hashes_are_this_tree_s", ("specs", 0, "semantic_hash"), "0" * 64),
                                      ("every_spec_qualified", ("specs", 0, "status"), "NOT_QUALIFIED"),
                                      # QUALIFIED as written, but its verdicts are not a qualification
                                      ("every_spec_qualified", ("specs", 0, "mutant_verdict"), row["expectation"]),
                                      ("every_spec_qualified", ("specs", 0, "pristine"), row["mutant_verdict"]),
                                      ("tests_all_ok", ("tests", module, "exit"), 1),
                                      ("tests_all_ok", ("tests", module, "status"), "FAILED"),
                                      ("tests_all_ok", ("tests", module, "residual"), 1),
                                      ("tests_all_ok", ("tests", module, "residual"), None),
                                      ("tests_all_ok", ("tests",), {module: good["tests"][module]}),
                                      ("tests_all_ok", ("tests",), {}),
                                      ("verdict_is_complete", ("verdict",), "PROBLEMS")):
                with self.subTest(name=name, path=path, value=value):
                    self.assertEqual(problems(_set(copy.deepcopy(good), path, value)), [f"{pf.V21_OUT_REL}: {name} is false"])
            self.assertIn(f"{pf.V21_OUT_REL}: every_spec_qualified is false", problems(None))

    def test_the_committed_re_verification_is_current_only_exactly_with_every_guard_run(self):
        from validation.qualification import p5_falsifiability as pf
        ran = {k: {"command": "python -P " + " ".join(v), "exit": 0, "tail": ["PASS"], "seconds": 0.25} for k, v in A.GUARDS.items()}
        with self.on_2_1() as state, tempfile.TemporaryDirectory() as tmp:
            rec = A.reverify(run_guards=False)
            self.assertEqual((rec["problems"], rec["verdict"], rec["claims_owner_acceptance"], rec["new_approvals"]),
                             ([], A.V21_VERDICT, False, []))
            state["reverification"] = at = pathlib.Path(tmp) / "C2-P5-ACCEPTANCE-REVERIFICATION.json"

            def problems(change=lambda doc: None):
                doc = copy.deepcopy({**rec, "guards": ran})
                change(doc)
                at.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                return A.reverification_problems()

            self.assertEqual(problems(), [])
            k, stale = next(iter(A.GUARDS)), f"{A.V21_OUT_REL} is not what this tree re-verifies"
            not_exactly = f"{A.V21_OUT_REL}: the recorded guard runs are not exactly {sorted(A.GUARDS)}"
            for name, change, expected in (("a guard exit 1", lambda d: d["guards"][k].update(exit=1), [f"{A.V21_OUT_REL}: guard {k}: exit 1"]),
                                           ("a guard missing", lambda d: d["guards"].pop(k), [not_exactly]),
                                           ("no guard run", lambda d: d.pop("guards"), [not_exactly]),
                                           ("a guard not run", lambda d: d["guards"][k].update(seconds=0),
                                            [f"{A.V21_OUT_REL}: guard {k}: not a recorded run of its command"]),
                                           ("claims_owner_acceptance", lambda d: d.update(claims_owner_acceptance=True), [stale]),
                                           ("a new approval", lambda d: d["new_approvals"].append(A.OWNER), [stale]),
                                           ("the owner's verdict", lambda d: d.update(verdict=A.ACCEPTED_VERDICT), [stale])):
                with self.subTest(name):
                    self.assertEqual(problems(change), expected)
            # the falsifiability record changed after the re-verification was written: refused for its own reason too
            fals = state["fals"]
            for name, path, value, check in (("a NOT_QUALIFIED row", ("specs", 0, "status"), "NOT_QUALIFIED", "every_spec_qualified"),
                                             ("a stale aisef2_tree", ("identities", "aisef2_tree"), "0" * 40, "kernel_is_this_tree_s"),
                                             ("a changed runner", ("identities", "runner", "sha256"), "0" * 64, "runner_is_this_tree_s")):
                with self.subTest(name):
                    state["fals"] = _set(copy.deepcopy(fals), path, value)
                    self.assertEqual(problems(), [f"{pf.V21_OUT_REL}: {check} is false", stale])
            state["fals"] = fals
            self.assertEqual(problems(), [])

    def test_each_re_verification_check_refuses_for_its_own_reason(self):
        from validation.qualification import release_calibration as rc
        with self.on_2_1() as state, tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(A.reverify(run_guards=False)["problems"], [])
            derived, ledger = state["derived"], json.loads((A.ROOT / A.DECISIONS_REL).read_text(encoding="utf-8"))
            at = pathlib.Path(tmp) / "RELEASE-DECISIONS.json"

            def decisions(change):
                doc = copy.deepcopy(ledger)
                change(next(e for e in doc["entries"] if e.get("id") == A.B03_ID))
                at.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
                return mock.patch.object(A, "DECISIONS_REL", str(at))      # ROOT / an absolute path is that path

            def proposal(path, value):
                return mock.patch.dict(state, {"proposal": _set(A.v21_proposal(copy.deepcopy(derived)), path, value)})

            sid, req = derived["specs"][0]["spec_id"], next(iter(derived["requirements"]))
            current = f"{A.V21_PROPOSAL_REL} is not what the authoring aid derives from this tree"
            missing = "closure-evidence/v2/v2.1/NO-RELEASE-CALIBRATION.json"
            rewritten = {"commits": 2, "distinct_blobs": ["a", "b"], "identical": False}
            for name, patch, expected in (   # each patch made when its case runs (one ledger file at a time)
                    ("the 2.0 acceptance is not history", lambda: mock.patch.object(A, "history_problems", return_value=["h"]), [f"{A.OUT_REL}: ['h']"]),
                    ("the 2.0 proposal is not history", lambda: mock.patch.object(A, "proposal_history_problems", return_value=["p"]),
                     [f"{A.PROPOSAL_REL}: ['p']"]),
                    ("the B-03a text is not the ledger's", lambda: decisions(lambda e: e.update(owner_text="x")),
                     [f"the B-03a text is not in {at} entry {A.B03_ID}"]),
                    ("the ledger entry is not the reference", lambda: decisions(lambda e: e.update(seq=4)), [f"{at} entry {A.B03_ID} is not {A.B03_REF}"]),
                    ("the v2.1 proposal is not the aid's", lambda: proposal(("v2_1", "rule"), "x"), [current]),
                    ("its engine digest", lambda: proposal(("record", "identities", "admission_engine_digest"), "0" * 64),
                     [current, "admission: the engine digest is not the v2.1 proposal's"]),
                    ("its spec identities", lambda: proposal(("record", "specs", 0, "semantic_hash"), "0" * 64),
                     [f"{sid}: identities_are_the_v21_proposal_s is false", current]),
                    ("its requirements", lambda: proposal(("record", "requirements", req, "hash"), "0" * 64),
                     ["requirements: are_the_v21_proposal_s is false", current]),
                    ("its plan", lambda: proposal(("record", "plan", "plan_hash"), "0" * 64), ["plan: is_the_v21_proposal_s is false", current]),
                    ("the approvals rewritten", lambda: mock.patch.object(A, "committed_versions_identical", return_value=rewritten),
                     [f"{A.APPROVALS_REL} was rewritten", f"{A.OUT_REL}: ['{A.APPROVALS_REL} was rewritten']"]),
                    ("the admission", lambda: mock.patch.object(A, "_admission_problems", return_value=["not admitted"]), ["not admitted"]),
                    ("a literal comparison", lambda: mock.patch.object(A, "_cycle1_drift", return_value={**A._cycle1_drift(), "ok": False}),
                     ["cycle1_drift_is_the_accepted_record_s is false"]),
                    ("the release calibration", lambda: mock.patch.object(rc, "RECORD_REL", missing), [f"{missing} is missing"])):
                with self.subTest(name), patch():
                    self.assertEqual(A.reverify(run_guards=False)["problems"], expected)



class KernelProvenance(unittest.TestCase):
    """The proposal names the kernel it was authored on; only that field may differ after an authorized kernel change,
    and only when the committed value is the accepted candidate's kernel (owner, 2026-10-01)."""
    ACCEPTED_K, HEAD_K = "a" * 40, "b" * 40

    def _rec(self, tree, **identities):
        return {"proposal_digest": "d", "plan": {"plan_hash": "p"}, "identities": {"aisef2_tree": tree, "compiler": {"digest": "c"},
                                                                                     **identities}}

    def test_identical_records_are_current(self):
        r = A.proposal_currency(self._rec(self.ACCEPTED_K), self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.ACCEPTED_K)
        self.assertEqual((r["current"], r["differing_paths"]), (True, []))

    def test_only_the_provenance_differs_from_the_accepted_kernel_is_current(self):
        r = A.proposal_currency(self._rec(self.HEAD_K), self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.HEAD_K)
        self.assertEqual((r["current"], r["provenance_only"], r["differing_paths"]), (True, True, [A.PROVENANCE_PATH]))

    def test_a_committed_kernel_that_is_not_the_accepted_one_is_refused(self):
        r = A.proposal_currency(self._rec(self.HEAD_K), self._rec("c" * 40), self.ACCEPTED_K, self.HEAD_K)
        self.assertFalse(r["current"])

    def test_a_derived_kernel_that_is_not_this_tree_is_refused(self):
        r = A.proposal_currency(self._rec("c" * 40), self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.HEAD_K)
        self.assertFalse(r["current"])

    def test_any_semantic_difference_is_refused_with_or_without_the_provenance(self):
        for derived in (self._rec(self.HEAD_K, compiler={"digest": "x"}), self._rec(self.ACCEPTED_K, compiler={"digest": "x"})):
            r = A.proposal_currency(derived, self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.HEAD_K)
            self.assertFalse(r["current"])
            self.assertIn("identities.compiler.digest", r["differing_paths"])
        bad = self._rec(self.HEAD_K)
        bad["proposal_digest"] = "e"
        self.assertFalse(A.proposal_currency(bad, self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.HEAD_K)["current"])

    def test_the_authoring_aid_s_own_sha_is_tolerated_only_as_given(self):
        derived, committed = self._rec(self.HEAD_K), self._rec(self.ACCEPTED_K)
        derived["identities"]["authoring_aid"], committed["identities"]["authoring_aid"] = {"sha256": "n"}, {"sha256": "o"}
        self.assertFalse(A.proposal_currency(derived, committed, self.ACCEPTED_K, self.HEAD_K)["current"])
        self.assertFalse(A.proposal_currency(derived, committed, self.ACCEPTED_K, self.HEAD_K, aid=("x", "n"))["current"])
        r = A.proposal_currency(derived, committed, self.ACCEPTED_K, self.HEAD_K, aid=("o", "n"))
        self.assertEqual((r["current"], sorted(r["differing_paths"])), (True, sorted([A.AID_PATH, A.PROVENANCE_PATH])))
        self.assertIsNotNone(A.aid_provenance())        # on this tree: the aid changed in calibrations() alone

    def test_on_this_tree_the_committed_proposal_is_current(self):
        # V2.1 (owner B-03a): the admission engine moved (ProbeIdentityRebinding measures it), so the proposal current on
        # this tree is the v2.1 record — EXACTLY, with no kernel provenance, aid sha or probe-identity re-binding
        # tolerated; the accepted 2.0 proposal and its document are history (their v2.0.0 blobs, as recorded)
        r = A.v21_proposal_currency()
        self.assertTrue(r["current"], r)
        self.assertEqual(A.proposal_history_problems(), [])
        self.assertEqual(r["differing_paths"], [])


class ProbeIdentityRebinding(unittest.TestCase):
    """The release's B1 moved three probe digests, hence the spec id and semantic hash of every spec on those probes,
    the plan hash and the proposal digest. The committed proposal is current up to probe identity
    (validation/qualification/rebind.py) — and nothing else may move with it: each case below changes one more thing
    and is refused. On 2.1 the admission engine moved as well: the re-binding leaves exactly its digests (owner B-03a:
    no engine-digest tolerance; a v2.1 proposal record replaces this one, KernelProvenance)."""
    #: measured on 2.1: aisef2/plan/static_admission.py's check 9 changed (919a271), hence the engine digest and every
    #: admission result digest; the re-binding does not absorb them
    ENGINE_PATHS = ["identities.admission_engine_digest",
                    "static_admission.with_synthetic_approvals.engine_digest",
                    "static_admission.with_synthetic_approvals.result_digest",
                    "static_admission.without_approvals.engine_digest",
                    "static_admission.without_approvals.result_digest"]

    @classmethod
    def setUpClass(cls):
        aid = A._aid()
        cls.plan = aid.build()["plan"]
        cls.committed = json.loads((A.ROOT / A.PROPOSAL_REL).read_text(encoding="utf-8"))
        cls.derived = aid.record()
        for k in ("aisef2_tree", "authoring_aid"):          # provenance as committed: what differs is the re-binding alone
            cls.derived["identities"][k] = cls.committed["identities"][k]
        cls.moved = next(i for i, (d, c) in enumerate(zip(cls.derived["specs"], cls.committed["specs"], strict=True))
                         if d["probe_digest"] != c["probe_digest"])

    def currency(self, derived, committed=None, plan=None):
        committed = committed or self.committed
        return A.proposal_currency(derived, committed, "k", "k", A.proposal_subst(derived, committed, plan or self.plan))

    def changed(self, **fields):
        d = copy.deepcopy(self.derived)
        d["specs"][self.moved].update(fields)
        return d

    def beyond_the_engine(self, r):
        """What differs beyond the measured engine change: on 2.1 the injected change shows up here, refused."""
        return sorted(set(r["differing_paths"]) - set(self.ENGINE_PATHS))

    def unbound(self, field):
        """The residue of one spec field changed: that field, the spec's identities (not re-bound) and the two hashes."""
        m = self.moved
        return sorted(["plan.plan_hash", "proposal_digest", f"specs[{m}].{field}", f"specs[{m}].semantic_hash", f"specs[{m}].spec_hash_id"])

    def test_the_re_binding_alone_is_current(self):
        # V2.1: what is left after the re-binding is exactly the engine change, so it is NOT current; the record it
        # compares with is history
        self.assertNotEqual(self.derived["plan"]["plan_hash"], self.committed["plan"]["plan_hash"])
        r = self.currency(self.derived)
        self.assertEqual((r["current"], sorted(r["differing_paths"])), (False, self.ENGINE_PATHS))
        self.assertGreater(r["identities_rebound"], 0)
        self.assertEqual(A.proposal_history_problems(), [])

    def test_a_contract_hash_change_is_refused(self):
        r = self.currency(self.changed(contract_hash="0" * 64))
        self.assertFalse(r["current"])
        self.assertEqual(self.beyond_the_engine(r), self.unbound("contract_hash"))
        self.assertIn(f"specs[{self.moved}].contract_hash", r["differing_paths"])
        self.assertIn(f"specs[{self.moved}].spec_hash_id", r["differing_paths"])      # its identities are not re-bound

    def test_a_probe_id_change_is_refused(self):
        r = self.currency(self.changed(probe_id="probe.python_callable"))
        self.assertFalse(r["current"])
        self.assertEqual(self.beyond_the_engine(r), self.unbound("probe_id"))
        self.assertIn(f"specs[{self.moved}].probe_id", r["differing_paths"])

    def test_a_re_derived_digest_that_is_not_this_tree_s_catalog_digest_is_refused(self):
        r = self.currency(self.changed(probe_digest="f" * 64))
        self.assertFalse(r["current"])
        self.assertEqual(self.beyond_the_engine(r), self.unbound("probe_digest"))
        self.assertIn(f"specs[{self.moved}].semantic_hash", r["differing_paths"])

    def test_a_mapped_back_hash_that_is_not_the_committed_is_refused(self):
        for path in (("plan", "plan_hash"), ("proposal_digest",)):
            committed = copy.deepcopy(self.committed)
            at = committed
            for k in path[:-1]:
                at = at[k]
            at[path[-1]] = "0" * 64
            with self.subTest(path=path):
                r = self.currency(self.derived, committed)
                self.assertFalse(r["current"])
                self.assertEqual(self.beyond_the_engine(r), [".".join(path)])
                self.assertIn(".".join(path), r["differing_paths"])
        # a plan that differs beyond its spec ids: mapped back, its hash is not the accepted plan's
        o = self.plan.obligations[0]
        plan = Plan.create(id=self.plan.id, baseline=self.plan.baseline, plan_quality_policy=self.plan.plan_quality_policy,
                           obligations=(dataclasses.replace(o, ownership_rationale=o.ownership_rationale + " (edited)"),
                                        *self.plan.obligations[1:]))
        derived = copy.deepcopy(self.derived)
        derived["plan"]["plan_hash"] = plan.plan_hash
        r = self.currency(derived, plan=plan)
        self.assertFalse(r["current"])
        self.assertEqual(self.beyond_the_engine(r), ["plan.plan_hash", "proposal_digest"])
        self.assertIn("plan.plan_hash", r["differing_paths"])


if __name__ == "__main__":
    unittest.main()
