"""The E2 campaign driver (validation/experiments/campaign.py), offline: the tests' fake client plays the agent of
both arms, a loopback fake provider answers both arms' preflight, and the hidden evaluator of
tests/v2/test_v21_experiment judges the candidates. Nothing reaches a network host or the real client.

    PATH=<no opencode> nice -n 19 python3 -P -B validation/experiments/test_campaign_offline.py -v"""

from __future__ import annotations

import contextlib
import http.server
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402
from tests.v2.test_app_run import ADD, SETTINGS, ProductBase, client_config, git, project_bundle  # noqa: E402
from tests.v2.test_v21_experiment import EVALUATOR  # noqa: E402
from validation.experiments import campaign as C  # noqa: E402
from validation.experiments import harness as H  # noqa: E402


class Provider(http.server.BaseHTTPRequestHandler):
    """The fake provider of tests/v2/test_app_run.provider, over loopback HTTP for both arms' preflight."""

    def _send(self, doc: dict) -> None:
        body = json.dumps(doc).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send({"data": [{"id": "model-1", "owned_by": "fake"}]})

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send({"model": "model-1", "system_fingerprint": "fp-1", "usage": {"prompt_tokens": 9, "completion_tokens": 1}})

    def log_message(self, *a) -> None:
        pass


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class Campaign(ProductBase):
    def setUp(self) -> None:
        super().setUp()
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.endpoint = f"http://127.0.0.1:{srv.server_address[1]}/v1"
        client_config(self.tmp, endpoint=self.endpoint, key="{env:AISEF_TEST_KEY}")
        # this process's PATH: the fake client first, then only what python and git need — never the real client
        path = os.pathsep.join([str(self.client.parent), os.path.dirname(sys.executable),
                                os.path.dirname(shutil.which("git")), "/usr/bin", "/bin"])
        env = mock.patch.dict(os.environ, {"AISEF_TEST_KEY": "test-key-of-a-loopback-fake", "PATH": path,
                                           **{f"XDG_{k}_HOME": str(self.tmp / "xdg" / k.lower()) for k in ("DATA", "STATE", "CACHE")}})
        env.start()
        self.addCleanup(env.stop)
        self.files = self.tmp / "campaign"
        self.files.mkdir()
        settings = {**SETTINGS, "provider": {**SETTINGS["provider"], "endpoint": self.endpoint, "api_key_env": "AISEF_TEST_KEY"}}
        (self.files / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        (self.files / "bundle.json").write_text(json.dumps(project_bundle(self.baseline)), encoding="utf-8")
        doc, _ = bundle_cli.seal(EVALUATOR, repo=self.tmp / "source")
        self.evaluator = bundle_cli.approve(doc, "BC-HIDDEN-ADD", "human:experiment-owner", 1.0)
        (self.files / "evaluator.json").write_text(json.dumps(self.evaluator), encoding="utf-8")
        workload = {"id": "calc", "repo": "../source", "commit": self.baseline, "requirements_path": "docs/requirements.md",
                    "task_text": "Implement docs/requirements.md."}
        (self.files / "CAMPAIGN.json").write_text(json.dumps({"runs": [
            {"run_id": f"calc-r1-{arm}", "workload": workload, "arm": arm, "settings_path": "settings.json",
             "bundle_path": "bundle.json", "evaluator_path": "evaluator.json", "rep": 1} for arm in ("direct", "aisef")]}),
            encoding="utf-8")
        self.out = self.tmp / "out"

    def campaign(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = C.main([*argv])
        return code, buf.getvalue()

    def run_(self, *extra: str, client: pathlib.Path | None = None) -> tuple[int, str]:
        return self.campaign("run", "--campaign", str(self.files / "CAMPAIGN.json"), "--out", str(self.out),
                             "--client-exe", str(client or self.client), "--client-version", "0.0.0-fake", *extra)

    def sealed(self) -> tuple[list[dict], dict[str, dict]]:
        """The campaign's runs and their manifests, sealed by the driver as `run` would (no arm started)."""
        runs = C.load_campaign(self.files / "CAMPAIGN.json")
        self.out.mkdir(exist_ok=True)
        a = mock.Mock(client_exe=str(self.client), client_version="0.0.0-fake")
        manifests, problems = C.seal_all(runs, self.out, a)
        self.assertEqual(problems, [])
        return runs, manifests

    def test_the_whole_flow_offline(self):
        # 1. manifests are sealed before anything runs; a STOP file stops the campaign before its first arm
        (self.out / "STOP").parent.mkdir()
        (self.out / "STOP").write_text("")
        code, text = self.run_()
        self.assertEqual(code, 3, text)
        self.assertIn("STOP file", text)
        control, treatment = (C.read_json(self.out / f"calc-r1-{a}" / "MANIFEST.json") for a in ("direct", "aisef"))
        self.assertEqual(H.check(control) + H.check(treatment), [])
        self.assertEqual(H.pair_problems(control, treatment), [])
        # the model's identity is the gate's, the same words in both arms; the client's bytes are bound (fix 3, 7)
        self.assertEqual(control["model"], {"declared": "model-1", "route": "fakeprov/model-1", **C.MODEL_IDENTITY})
        self.assertEqual(control["model"]["identity_confidence"], "provider_reported")
        self.assertIn("preflight", control["model"]["reason"])
        self.assertIn("alias", control["model"]["reason"])
        self.assertEqual(control["client"]["version"], "0.0.0-fake")
        self.assertEqual((control["client"]["exe"], control["client"]["sha256"]),
                         (os.path.realpath(self.client), H.sha(self.client.read_bytes())))
        self.assertEqual(control["client"], treatment["client"])
        other = H.seal({**treatment, "client": {**treatment["client"], "sha256": "0" * 64}})
        self.assertTrue(any("client.sha256" in p for p in H.pair_problems(control, other)))
        self.assertFalse(list(self.out.glob("*/RESULT.json")))
        (self.out / "STOP").unlink()
        # 2. --max-runs 1: the direct arm only — behind the gate; the manifests are reused, not rewritten
        code, text = self.run_("--max-runs", "1")
        self.assertEqual(code, 3, text)
        self.assertEqual(C.read_json(self.out / "calc-r1-direct" / "MANIFEST.json"), control)
        direct = C.read_json(self.out / "calc-r1-direct" / "RESULT.json")
        self.assertEqual((direct["arm"], direct["manifest_sha256"], direct["exit"], direct["error"]), ("direct", control["manifest_sha256"], 0, None))
        self.assertEqual((direct["evaluation"]["total"], direct["evaluation"]["satisfied"], direct["escaped_defects"], direct["valid"]),
                         (1, 1, [], True))
        self.assertEqual(direct["usage"]["cost"]["value"], None)       # no price table: unknown, never 0
        arm = self.out / "calc-r1-direct" / "arm"
        pre = C.read_json(arm / "preflight" / "PREFLIGHT.json")                 # fix 7: the direct arm's gate, recorded
        self.assertEqual((pre["verdict"], pre["accounting"]["provider_requests"]), ("ATTESTED", 3))   # listing + 2 probes
        self.assertEqual(direct["preflight"]["verdict"], "ATTESTED")
        self.assertEqual(direct["usage"]["preflight"]["provider_requests"], 3)
        self.assertEqual(direct["usage"]["budget"]["spent"]["provider_requests"], 3 + 1)        # the gate, then one session
        self.assertEqual(direct["usage"]["tokens"]["input"], 120)
        self.assertEqual(direct["candidate_frozen"]["commit"], direct["candidate"])
        self.assertEqual(direct["configured_endpoint"], self.endpoint)                            # fix 4: in the record
        self.assertEqual(C.read_json(arm / "ARM.json")["configured_endpoint"], self.endpoint)     # and in ARM.json
        self.assertEqual(H.git(arm / "ws", "remote"), "")                                         # fix 2: no remote
        self.assertFalse((self.out / "calc-r1-aisef" / "RESULT.json").exists())
        # 3. resumed: the aisef arm (aisef run as a subprocess on a fresh clone, the fake client, the loopback provider)
        code, text = self.run_()
        self.assertEqual(code, 0, text + (self.out / "calc-r1-aisef" / "arm" / "run.stderr").read_text(encoding="utf-8", errors="replace"))
        aisef = C.read_json(self.out / "calc-r1-aisef" / "RESULT.json")
        self.assertEqual(aisef["exit"], 0, (self.out / "calc-r1-aisef" / "arm" / "run.stderr").read_text(encoding="utf-8", errors="replace"))
        self.assertEqual(aisef["aisef_run"]["delivery_verdict"], "PASS", aisef["aisef_run"])
        self.assertEqual(aisef["aisef_run"]["preflight_verdict"], "ATTESTED")
        self.assertEqual((aisef["evaluation"]["total"], aisef["evaluation"]["satisfied"], aisef["valid"], aisef["rollback"],
                          aisef["false_rollbacks"], aisef["error"]), (1, 1, True, False, [], None))
        self.assertEqual(aisef["candidate"], aisef["aisef_run"]["final_main"])
        self.assertEqual(aisef["usage"]["cost"]["value"], None)
        self.assertEqual(aisef["usage"]["budget"]["spent"]["provider_requests"], 3 + 2)      # preflight 3, two sessions
        self.assertTrue((self.out / "calc-r1-aisef" / "arm" / "run.anchor").exists())
        self.assertTrue((self.out / "calc-r1-aisef" / "arm" / "run" / "sessions").is_dir())
        self.assertEqual(H.git(self.out / "calc-r1-aisef" / "arm" / "ws", "remote"), "")
        self.assertNotIn("add", H.git(self.tmp / "source", "show", "main:app/calc.py"))     # the source is never written
        log = (self.out / "campaign.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual([line.split()[1] for line in log], ["calc-r1-direct", "calc-r1-aisef"])
        # 4. a finished campaign runs nothing more; replay prints nothing; summary has one row per workload x arm
        code, text = self.run_()
        self.assertEqual((code, text.count("starting")), (0, 0))
        code, text = self.campaign("replay", "--out", str(self.out))
        self.assertEqual((code, text), (0, ""))
        code, text = self.campaign("summary", "--out", str(self.out))
        rows = {(r["workload"], r["arm"]): r for r in map(json.loads, text.splitlines())}
        self.assertEqual(set(rows), {("calc", "direct"), ("calc", "aisef")})
        for r in rows.values():
            self.assertEqual((r["n"], r["satisfied_mean"], r["escaped_defects"], r["false_rollbacks"], r["cost"], r["valid"], r["failed"]),
                             (1, 1.0, 0, 0, None, True, 0))
        self.assertEqual((rows["calc", "direct"]["requests"], rows["calc", "aisef"]["requests"]), (4, 5))

    def test_a_leaked_stimulus_invalidates_the_result_and_a_failed_arm_is_kept(self):
        runs, manifests = self.sealed()
        run = runs[0]
        arm = self.out / run["run_id"] / "arm"
        (arm / "sessions").mkdir(parents=True)
        (arm / "sessions" / "direct.developer.1.jsonl").write_text(json.dumps({"type": "text", "part": {"text": json.dumps(
            {"args": [10, -4]}, sort_keys=True)}}) + "\n", encoding="utf-8")
        res = C.record(run, manifests[run["run_id"]], {"arm": "direct", "candidate": None, "sessions": arm / "sessions",
                                                       "repo": arm / "ws", "exit": 1}, self.out, error="the client failed")
        self.assertEqual((res["valid"], res["evaluator_leaks"], res["candidate"], res["evaluation"]["total"], res["error"]),
                         (False, [{"session": "direct.developer.1.jsonl", "strings": 1}], None, None, "the client failed"))
        self.assertTrue((self.out / run["run_id"] / "RESULT.json").exists())
        code, text = self.campaign("summary", "--out", str(self.out))
        row = json.loads(text)
        self.assertEqual((row["n"], row["evaluated"], row["valid"], row["failed"], row["satisfied_mean"]), (1, 0, False, 1, None))

    def test_1_a_stopped_aisef_run_is_a_failed_arm_not_a_candidate(self):
        # the canary's shape (closure-evidence/v2/v2.1/canary/tier-1/run/RUN.json): NOT_REACHED, final_main = baseline
        runs, manifests = self.sealed()
        run = runs[1]
        arm = self.out / run["run_id"] / "arm"
        (arm / "run").mkdir(parents=True)
        subprocess.run(["git", "clone", "--quiet", str(self.tmp / "source"), str(arm / "run" / "repo")], check=True, capture_output=True)
        (arm / "run" / "RUN.json").write_text(json.dumps({
            "delivery_verdict": "NOT_REACHED", "delivery_blocked_by": ["1 of the plan's stories did not commit: ['S1']",
                                                                       "the budget ended the run: S1 not run: max_provider_requests: 4 of 4"],
            "final_main": self.baseline, "failure": None, "budget_stop": "S1 not run: max_provider_requests: 4 of 4",
            "stage": "finished", "story_outcomes": {"S1": ["NOT_RUN: max_provider_requests: 4 of 4"]},
            "budget": {"spent": {"provider_requests": 4}}, "usage": {"cost": {"value": None, "status": "unknown"}},
            "preflight": {"verdict": "ATTESTED"}}), encoding="utf-8")
        rec = C.aisef_record(run, manifests[run["run_id"]], arm, 0, 1.0)
        self.assertIsNone(rec["candidate"])
        self.assertIn("delivery_verdict='NOT_REACHED'", rec["error"])
        self.assertIn("stage='finished'", rec["error"])
        res = C.record(run, manifests[run["run_id"]], rec, self.out)
        self.assertEqual((res["candidate"], res["evaluation"], res["candidate_frozen"], res["aisef_run"]["final_main"]),
                         (None, C.NO_EVALUATION, None, self.baseline))
        self.assertIn("aisef run not delivered", res["error"])
        code, text = self.campaign("summary", "--out", str(self.out))
        row = json.loads(text)
        self.assertEqual((row["n"], row["evaluated"], row["failed"], row["satisfied_mean"], row["escaped_defects"]), (1, 0, 1, None, 0))
        # an identity stop: failure named, stage preflight — the same
        shutil.rmtree(arm)
        (arm / "run").mkdir(parents=True)
        (arm / "run" / "RUN.json").write_text(json.dumps({
            "delivery_verdict": "NOT_REACHED", "final_main": self.baseline, "stage": "preflight",
            "failure": {"type": "IdentityStop", "detail": "the route is not attested: probe 0: served by 'x'", "stage": "preflight"}}))
        rec = C.aisef_record(run, manifests[run["run_id"]], arm, 1, 1.0)
        self.assertEqual(rec["candidate"], None)
        self.assertIn("IdentityStop", rec["error"])
        # no RUN.json at all: failed too
        (arm / "run" / "RUN.json").unlink()
        rec = C.aisef_record(run, manifests[run["run_id"]], arm, 1, 1.0)
        self.assertEqual((rec["candidate"], rec["error"]), (None, "aisef run left no RUN.json (exit 1)"))

    def test_2_the_direct_arm_cannot_write_into_the_source(self):
        from aisef2.app import client, settings
        runs, manifests = self.sealed()
        source = self.tmp / "source"
        before = git(source, "for-each-ref")
        st = settings.load(SETTINGS)
        budget = client.Budget(st.budget, dict.fromkeys(client.Budget.KEYS, 0), self.tmp / "d" / "sessions",
                               requests=lambda: len(list((self.tmp / "d" / "sessions").glob("*.jsonl"))))
        kw = {"model": st.route, "env": client.environment(st.client_env, client.overlay(st.route, st.model_limit)),
              "budget": budget, "turn_cap": st.max_turns_per_session}
        arm = H.direct_arm(manifests["calc-r1-direct"], self.tmp / "d", task="Implement docs/requirements.md.",
                           client_exe=str(self.client), session_kw=kw, timeout_s=60)
        ws = self.tmp / "d" / "ws"
        self.assertTrue(arm["changed"])
        self.assertEqual(git(ws, "remote"), "")
        push = subprocess.run(["git", "-C", str(ws), "push", "origin", "HEAD:refs/heads/x"], capture_output=True)
        self.assertNotEqual(push.returncode, 0)
        self.assertEqual(git(source, "for-each-ref"), before)
        self.assertNotIn("add", git(source, "show", "main:app/calc.py"))

    def test_3_one_client_binary_across_the_arms(self):
        other = self.tmp / "other"
        other.mkdir()
        shutil.copy(self.client, other / "oc")
        (other / "oc").chmod(0o755)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, text = self.run_(client=other / "oc")
        self.assertEqual(code, 2)
        self.assertIn("basename is exactly 'opencode'", err.getvalue())
        shutil.copy(self.client, other / "opencode")
        (other / "opencode").chmod(0o644)            # a file PATH lookup cannot execute: `opencode` resolves to nothing
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, text = self.run_(client=other / "opencode")
        self.assertEqual(code, 2)
        self.assertIn("resolves to None", err.getvalue())
        self.assertFalse(self.out.exists() and list(self.out.glob("*/MANIFEST.json")))
        real, path, why = C.client_path(str(self.client))
        self.assertIsNone(why)
        self.assertEqual(path.split(os.pathsep)[0], str(self.client.parent))
        self.assertEqual(path.split(os.pathsep)[-2:], ["/usr/bin", "/bin"])
        self.assertEqual(shutil.which("opencode", path=path), str(self.client))

    def test_4_the_direct_arm_refuses_a_client_configured_for_another_endpoint(self):
        client_config(self.tmp, endpoint="http://127.0.0.1:9/v1", key="{env:AISEF_TEST_KEY}")
        code, text = self.run_("--max-runs", "1")
        self.assertEqual(code, 3, text)
        res = C.read_json(self.out / "calc-r1-direct" / "RESULT.json")
        self.assertEqual((res["candidate"], res["evaluation"]["total"], res["configured_endpoint"]), (None, None, "http://127.0.0.1:9/v1"))
        self.assertIn(f"to http://127.0.0.1:9/v1, not to the settings' endpoint {self.endpoint}", res["error"])
        arm = self.out / "calc-r1-direct" / "arm"
        self.assertEqual(C.read_json(arm / "ARM.json")["configured_endpoint"], "http://127.0.0.1:9/v1")
        self.assertFalse((arm / "sessions").exists())           # no session
        self.assertFalse((arm / "preflight").exists())          # and no request: the endpoint is checked first
        self.assertEqual(res["usage"]["budget"]["spent"]["provider_requests"], 0)
        code, text = self.campaign("summary", "--out", str(self.out))
        self.assertEqual(json.loads(text)["failed"], 1)

    def test_5_false_rollbacks_are_the_plans_measure(self):
        runs, manifests = self.sealed()
        run = runs[1]
        repo = self.out / run["run_id"] / "arm" / "run" / "repo"        # where an aisef arm's kernel clone lives
        repo.parent.mkdir(parents=True)
        subprocess.run(["git", "clone", "--quiet", str(self.tmp / "source"), str(repo)], check=True, capture_output=True)
        (repo / "app" / "calc.py").write_text(ADD)
        git(repo, "commit", "-qam", "S1: developer attempt 1")
        good = git(repo, "rev-parse", "HEAD")
        git(repo, "reset", "-q", "--hard", self.baseline)      # main back at the baseline; `good` is an unreferenced object
        gone = "f" * 40
        journal = self.tmp / "aisef-run.jsonl"
        rows = [("run/begin", {"journal_format": 3, "run_id": "aisef-run"}),
                ("story/begin", {"story_id": "S1", "parent": self.baseline}),
                ("proof/verified", {"story_id": "S1", "criterion_id": "C-ADD", "candidate": good}),
                ("story/rollback", {"story_id": "S1"}),
                ("story/begin", {"story_id": "S2", "parent": self.baseline}),
                ("proof/verified", {"story_id": "S2", "criterion_id": "C-X", "candidate": self.baseline}),
                ("story/retry", {"story_id": "S2"}),
                ("proof/verified", {"story_id": "S2", "criterion_id": "C-X", "candidate": gone}),
                ("story/rollback", {"story_id": "S2"}),
                ("story/begin", {"story_id": "S3", "parent": self.baseline}),
                ("story/rollback", {"story_id": "S3"}),
                ("proof/verified", {"story_id": "S4", "criterion_id": "C-Y", "candidate": good}),
                ("story/commit", {"story_id": "S4", "revision": good})]
        journal.write_text("".join(json.dumps({"chain": "0" * 64, "event": {"seq": i, "type": t, "data": d}}) + "\n"
                                   for i, (t, d) in enumerate(rows)), encoding="utf-8")
        outcomes = {"S1": ["ROLLBACK"], "S2": ["RETRY", "ROLLBACK"], "S3": ["ROLLBACK"], "S4": ["COMMIT"]}
        arm_rec = {"arm": "aisef", "manifest_sha256": manifests[run["run_id"]]["manifest_sha256"], "candidate": None,
                   "repo": repo, "journal": journal, "sessions": self.tmp / "none", "exit": 0,
                   "run": {"delivery_verdict": "FAIL", "story_outcomes": outcomes, "final_main": self.baseline},
                   "error": "aisef run not delivered: delivery_verdict='FAIL'"}
        rolled = C.false_rollbacks(arm_rec, self.evaluator)
        self.assertEqual([r["story"] for r in rolled], ["S1", "S2", "S3"])
        s1, s2, s3 = rolled
        self.assertEqual((s1["false_rollback"], s1["candidates"][0]["sha"], s1["candidates"][0]["evaluation"]["satisfied"]), (True, good, 1))
        self.assertEqual([(c["sha"], c["present"], c.get("note")) for c in s2["candidates"]],
                         [(self.baseline, True, None), (gone, False, "candidate object gone")])
        self.assertEqual((s2["false_rollback"], s2["candidates"][0]["evaluation"]["satisfied"], s2["candidates"][0]["passes"]), (False, 0, False))
        self.assertEqual((s3["false_rollback"], s3["candidates"], s3["note"]), (False, [], "candidate not in journal"))
        res = C.record(run, manifests[run["run_id"]], arm_rec, self.out)
        self.assertEqual((res["candidate"], res["rollback"], [r["false_rollback"] for r in res["false_rollbacks"]]), (None, True, [True, False, False]))
        code, text = self.campaign("summary", "--out", str(self.out))
        row = json.loads(text)
        self.assertEqual((row["false_rollbacks"], row["failed"], row["evaluated"]), (1, 1, 0))

    def test_6_the_bundles_baseline_is_the_workloads_commit(self):
        bundle = json.loads((self.files / "bundle.json").read_text(encoding="utf-8"))
        bundle["plan"]["baseline"] = "0" * 40
        (self.files / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        code, text = self.run_()
        self.assertEqual(code, 2, text)
        self.assertIn(f"bundle_path {self.files / 'bundle.json'}: plan.baseline {'0' * 40} is not the workload's commit {self.baseline}", text)
        self.assertIn("REFUSED (no arm started)", text)
        self.assertEqual(list(self.out.glob("*/MANIFEST.json")) + list(self.out.glob("*/RESULT.json")), [])
        (self.files / "bundle.json").write_text(json.dumps(project_bundle(self.baseline)), encoding="utf-8")
        ev = json.loads((self.files / "evaluator.json").read_text(encoding="utf-8"))
        ev["plan"]["baseline"] = "1" * 40
        (self.files / "evaluator.json").write_text(json.dumps(ev), encoding="utf-8")
        code, text = self.run_()
        self.assertEqual(code, 2, text)
        self.assertIn("evaluator_path", text)
        self.assertEqual(list(self.out.glob("*/MANIFEST.json")), [])

    def test_7_the_direct_arm_is_refused_when_the_preflight_does_not_attest(self):
        def opaque(route, chat_probes, transport, directory, served_model=None, listed_owner=None):
            directory.mkdir(parents=True, exist_ok=False)
            rec = {"observation": {"route": route}, "problems": ["probe 0: served by 'other', not 'model-1' (an alias or a re-route)"],
                   "verdict": "OPAQUE", "accounting": {"provider_requests": 2, "turns": 0, "input_tokens": 9, "output_tokens": 1,
                                                       "unaccounted": []}}
            (directory / "PREFLIGHT.json").write_text(json.dumps(rec), encoding="utf-8")
            return rec
        with mock.patch.object(C, "preflight_run", opaque):
            code, text = self.run_("--max-runs", "1")
        self.assertEqual(code, 3, text)
        res = C.read_json(self.out / "calc-r1-direct" / "RESULT.json")
        self.assertEqual((res["candidate"], res["evaluation"]["total"], res["identity"], res["preflight"]["verdict"]), (None, None, "OPAQUE", "OPAQUE"))
        self.assertIn("identity: OPAQUE", res["error"])
        self.assertIn("an alias or a re-route", res["error"])
        arm = self.out / "calc-r1-direct" / "arm"
        self.assertEqual(C.read_json(arm / "preflight" / "PREFLIGHT.json")["verdict"], "OPAQUE")
        self.assertEqual(C.read_json(arm / "ARM.json")["identity"], "OPAQUE")
        self.assertFalse((arm / "sessions").exists())
        self.assertFalse((arm / "ws").exists())
        self.assertEqual(res["usage"]["budget"]["spent"]["provider_requests"], 2)      # what the gate spent is counted
        code, text = self.campaign("summary", "--out", str(self.out))
        self.assertEqual(json.loads(text)["failed"], 1)


if __name__ == "__main__":
    unittest.main()
