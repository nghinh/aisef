"""The E2 campaign driver (validation/experiments/campaign.py), offline: the tests' fake client plays the agent of
both arms, a loopback fake provider answers the aisef arm's preflight, and the hidden evaluator of
tests/v2/test_v21_experiment judges the candidates. Nothing reaches a network host or the real client.

    nice -n 19 python3 -P -B -m unittest validation.experiments.test_campaign_offline -v"""

from __future__ import annotations

import contextlib
import http.server
import io
import json
import os
import pathlib
import shutil
import sys
import threading
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402
from tests.v2.test_app_run import SETTINGS, ProductBase, client_config, project_bundle  # noqa: E402
from tests.v2.test_v21_experiment import EVALUATOR  # noqa: E402
from validation.experiments import campaign as C  # noqa: E402
from validation.experiments import harness as H  # noqa: E402


class Provider(http.server.BaseHTTPRequestHandler):
    """The fake provider of tests/v2/test_app_run.provider, over loopback HTTP for the aisef subprocess's preflight."""

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
        endpoint = f"http://127.0.0.1:{srv.server_address[1]}/v1"
        client_config(self.tmp, endpoint=endpoint, key="{env:AISEF_TEST_KEY}")
        # the subprocess's PATH: the fake client first, then only what python and git need — never the real client
        path = os.pathsep.join([str(self.client.parent), os.path.dirname(sys.executable),
                                os.path.dirname(shutil.which("git")), "/usr/bin", "/bin"])
        env = mock.patch.dict(os.environ, {"AISEF_TEST_KEY": "test-key-of-a-loopback-fake", "PATH": path,
                                           **{f"XDG_{k}_HOME": str(self.tmp / "xdg" / k.lower()) for k in ("DATA", "STATE", "CACHE")}})
        env.start()
        self.addCleanup(env.stop)
        self.files = self.tmp / "campaign"
        self.files.mkdir()
        settings = {**SETTINGS, "provider": {**SETTINGS["provider"], "endpoint": endpoint, "api_key_env": "AISEF_TEST_KEY"}}
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

    def run_(self, *extra: str) -> tuple[int, str]:
        return self.campaign("run", "--campaign", str(self.files / "CAMPAIGN.json"), "--out", str(self.out),
                             "--client-exe", str(self.client), "--client-version", "0.0.0-fake", "--identity", "unverified",
                             "--identity-reason", "a fake provider over loopback", *extra)

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
        self.assertEqual(control["model"], {"declared": "model-1", "route": "fakeprov/model-1", "identity_confidence": "unverified",
                                            "reason": "a fake provider over loopback"})
        self.assertEqual(control["client"]["version"], "0.0.0-fake")
        self.assertFalse(list(self.out.glob("*/RESULT.json")))
        (self.out / "STOP").unlink()
        # 2. --max-runs 1: the direct arm only; the manifests are reused, not rewritten
        code, text = self.run_("--max-runs", "1")
        self.assertEqual(code, 3, text)
        self.assertEqual(C.read_json(self.out / "calc-r1-direct" / "MANIFEST.json"), control)
        direct = C.read_json(self.out / "calc-r1-direct" / "RESULT.json")
        self.assertEqual((direct["arm"], direct["manifest_sha256"], direct["exit"]), ("direct", control["manifest_sha256"], 0))
        self.assertEqual((direct["evaluation"]["total"], direct["evaluation"]["satisfied"], direct["escaped_defects"], direct["valid"]),
                         (1, 1, [], True))
        self.assertEqual(direct["usage"]["cost"]["value"], None)       # no price table: unknown, never 0
        self.assertEqual(direct["usage"]["budget"]["spent"]["provider_requests"], 1)
        self.assertEqual(direct["usage"]["tokens"]["input"], 120)
        self.assertEqual(direct["candidate_frozen"]["commit"], direct["candidate"])
        self.assertFalse((self.out / "calc-r1-aisef" / "RESULT.json").exists())
        # 3. resumed: the aisef arm (aisef run as a subprocess on a fresh clone, the fake client, the loopback provider)
        code, text = self.run_()
        self.assertEqual(code, 0, text + (self.out / "calc-r1-aisef" / "arm" / "run.stderr").read_text(encoding="utf-8", errors="replace"))
        aisef = C.read_json(self.out / "calc-r1-aisef" / "RESULT.json")
        self.assertEqual(aisef["exit"], 0, (self.out / "calc-r1-aisef" / "arm" / "run.stderr").read_text(encoding="utf-8", errors="replace"))
        self.assertEqual(aisef["aisef_run"]["delivery_verdict"], "PASS", aisef["aisef_run"])
        self.assertEqual((aisef["evaluation"]["total"], aisef["evaluation"]["satisfied"], aisef["valid"], aisef["rollback"]), (1, 1, True, False))
        self.assertEqual(aisef["candidate"], aisef["aisef_run"]["final_main"])
        self.assertEqual(aisef["usage"]["cost"]["value"], None)
        self.assertEqual(aisef["usage"]["budget"]["spent"]["provider_requests"], 3 + 2)      # preflight 3, two sessions
        self.assertTrue((self.out / "calc-r1-aisef" / "arm" / "run.anchor").exists())
        self.assertTrue((self.out / "calc-r1-aisef" / "arm" / "run" / "sessions").is_dir())
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
        self.assertEqual((rows["calc", "direct"]["requests"], rows["calc", "aisef"]["requests"]), (1, 5))

    def test_a_leaked_stimulus_invalidates_the_result_and_a_failed_arm_is_kept(self):
        runs = C.load_campaign(self.files / "CAMPAIGN.json")
        self.out.mkdir()
        a = mock.Mock(client_exe=str(self.client), client_version="0.0.0-fake", identity="unverified", identity_reason="fake")
        manifests, problems = C.seal_all(runs, self.out, a)
        self.assertEqual(problems, [])
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


if __name__ == "__main__":
    unittest.main()
