"""The product runtime's control functions one by one (aisef2.app): the settings and the bundle a run accepts, the
budget and the session evidence it is computed from, the provider preflight's attestation, the delivery verdict and the
ProductProof account re-derived from journal events, the run directory's verification, the adapters' outcomes and the
command's modes. Offline: no network, no model; the client is never looked up."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, cli, client, preflight, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.arch.enums import ControlProjection, Enforcement, Owner  # noqa: E402
from aisef2.journal.format2 import OperationOutcome as O  # noqa: E402
from aisef2.orchestrate.adapters import ProviderOutage  # noqa: E402
from aisef2.runtime.capability import verified  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from aisef2.runtime.runspec import resolve  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

BUDGET = {"provider_requests": 5, "turns": 10, "input_tokens": 1000, "output_tokens": 100}
BASE = {"provider_requests": 1, "turns": 0, "input_tokens": 10, "output_tokens": 1}


def SPEC():
    return resolve([verified("kernel", b"k", Enforcement.FULL)], {}, "a" * 40)


def step(i: int | None = 100, o: int | None = 10, reasoning: int = 0, cache: dict | None = None) -> str:
    tokens = {"input": i, "output": o, "reasoning": reasoning, **({"cache": cache} if cache is not None else {})}
    return json.dumps({"type": "step_finish", "part": {"tokens": tokens}})


class Temp(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()


# --------------------------------------------------------------------------------------------- settings

class Settings(unittest.TestCase):
    def load(self, **changes) -> settings.Settings:
        return settings.load({**copy.deepcopy(e2e.SETTINGS), **changes})

    def refused(self, pattern: str, **changes) -> None:
        with self.assertRaisesRegex(settings.SettingsError, pattern):
            self.load(**changes)

    def test_a_complete_document_loads_with_nothing_defaulted(self):
        s = self.load()
        self.assertEqual((s.route, s.provider, s.model, s.endpoint, s.api_key_env), (e2e.ROUTE, "fakeprov", "model-1",
                                                                                    "https://provider.invalid/v1", "AISEF_TEST_NO_KEY"))
        self.assertEqual(s.budget, e2e.SETTINGS["budget"])
        self.assertEqual(s.limits, {o: 1 for o in Owner})
        self.assertEqual((s.max_turns_per_session, s.chat_probes, s.client_env), (10, 2, ()))
        self.assertEqual(s.timeouts_s, {"developer": 60.0, "reviewer": 60.0, "tool": 120.0, "probe": 60.0})
        self.assertEqual(s.content, e2e.SETTINGS)
        self.assertEqual(self.load(provider={**e2e.SETTINGS["provider"], "endpoint": "https://x/v1/"}).endpoint, "https://x/v1")
        self.assertEqual(self.load(client_env=["A", "B"]).client_env, ("A", "B"))

    def test_every_field_is_checked(self):
        self.refused("not run settings", format="aisef-v2-run/0")
        with self.assertRaisesRegex(settings.SettingsError, "nothing is defaulted"):
            settings.load({k: v for k, v in e2e.SETTINGS.items() if k != "client_env"})
        with self.assertRaisesRegex(settings.SettingsError, "nothing is defaulted"):
            settings.load({**e2e.SETTINGS, "extra": 1})
        with self.assertRaisesRegex(settings.SettingsError, "not run settings"):
            settings.load(["format"])
        self.refused("client is one of", client="claude")
        for route in ("model-1", "/model-1", "fakeprov/", 7):
            with self.subTest(route=route):
                self.refused("one fixed route", route=route)
        self.refused("provider is", provider={**e2e.SETTINGS["provider"], "name": "other"})
        self.refused("provider is", provider={"name": "fakeprov", "endpoint": "https://x"})
        prov = e2e.SETTINGS["provider"]
        self.assertIsNone(self.load(provider={**prov, "api_key_env": None, "listed_owner": None}).api_key_env)
        for bad, why in ((("api_key_env", ""), "api_key_env names a variable"), (("served_model", ""), "served_model is"),
                         (("listed_owner", 3), "listed_owner is"), (("model_limit", {"context": 1}), "model_limit is"),
                         (("model_limit", {"context": 0, "output": 1}), r"model_limit\.context is an integer >= 1")):
            with self.subTest(field=bad[0], value=bad[1]):
                self.refused(why, provider={**prov, bad[0]: bad[1]})
        s = self.load()
        self.assertEqual((s.served_model, s.listed_owner, s.model_limit), ("model-1", "fake", {"context": 100000, "output": 8000}))
        self.refused("provider is", provider="fakeprov")
        for endpoint in ("http://provider/v1", "ftp://x", "http://127.0.0.2.evil/v1"):
            with self.subTest(endpoint=endpoint):
                self.refused("https", provider={**e2e.SETTINGS["provider"], "endpoint": endpoint})
        for ok in ("http://127.0.0.1:8080/v1", "http://localhost:1/v1"):
            self.assertTrue(self.load(provider={**e2e.SETTINGS["provider"], "endpoint": ok}).endpoint.startswith("http://"))
        for env in ("A", [""], [1], None):
            with self.subTest(client_env=env):
                self.refused("client_env", client_env=env)
        self.refused("budget names exactly", budget={**e2e.SETTINGS["budget"], "usd": 1})
        self.refused("budget names exactly", budget=[1, 2, 3, 4])
        for bad in (0, -1, True, 1.5, "3"):
            with self.subTest(budget=bad):
                self.refused(r"budget\.turns is an integer >= 1", budget={**e2e.SETTINGS["budget"], "turns": bad})
        self.refused("limits name every owner", limits={o.value: 1 for o in list(Owner)[1:]})
        self.refused("limits name every owner", limits=[1])
        self.assertEqual(self.load(limits={o.value: 0 for o in Owner}).limits, {o: 0 for o in Owner})
        self.refused(r"limits\.DEVELOPER is an integer >= 0", limits={**{o.value: 1 for o in Owner}, "DEVELOPER": -1})
        self.refused("timeouts_s names", timeouts_s={"developer": 1, "reviewer": 1, "tool": 1})
        self.refused("timeouts_s names", timeouts_s=[1])
        for bad in (0, -1, True, float("inf"), float("nan"), "60"):
            with self.subTest(timeout=bad):
                self.refused(r"timeouts_s\.tool is a positive number", timeouts_s={**e2e.SETTINGS["timeouts_s"], "tool": bad})
        self.assertEqual(self.load(timeouts_s={**e2e.SETTINGS["timeouts_s"], "tool": 0.5}).timeouts_s["tool"], 0.5)
        self.refused("preflight names chat_probes", preflight={"chat_probes": 2, "x": 1})
        self.refused("preflight names chat_probes", preflight=2)
        self.refused(r"preflight\.chat_probes is an integer >= 2", preflight={"chat_probes": 1})
        self.refused("max_turns_per_session is an integer >= 1", max_turns_per_session=0)
        self.refused(r"the preflight's 3 requests exceed budget.provider_requests 2",
                     budget={**e2e.SETTINGS["budget"], "provider_requests": 2})
        self.assertEqual(self.load(budget={**e2e.SETTINGS["budget"], "provider_requests": 3}).budget["provider_requests"], 3)
        self.assertEqual(self.load(max_turns_per_session=1).max_turns_per_session, 1)

    def test_read_is_load_of_the_file(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "s.json"
            p.write_text(json.dumps(e2e.SETTINGS), encoding="utf-8")
            self.assertEqual(settings.read(p), self.load())


# --------------------------------------------------------------------------------------------- the client's evidence

class Sessions(Temp):
    def log(self, name: str, *lines: str) -> pathlib.Path:
        p = self.tmp / name
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_a_session_stream_is_read_for_text_error_turns_and_tokens(self):
        p = self.log("a.jsonl", "starting", '{"type": "text", "part": {"text": "he"}}', "{not json",
                     json.dumps({"type": "text", "part": {"text": "llo"}}),
                     step(100, 10, reasoning=5, cache={"read": 7, "write": 3}), step(1, 1),
                     json.dumps({"type": "step_finish", "part": {"tokens": {"input": "x", "output": 1}}}),
                     json.dumps({"type": "step_finish", "part": {}}),
                     json.dumps({"type": "error", "error": {"name": "APIError", "data": {"message": "m" * 300, "statusCode": 429}}}))
        s = client.read_session(p)
        self.assertEqual(s["text"], "hello")
        self.assertEqual(s["turns"], 4)
        self.assertEqual(s["tokens"], {"input": 100 + 7 + 3 + 1, "output": 10 + 5 + 1})
        self.assertEqual(s["steps_without_tokens"], 2)
        self.assertEqual(s["error"], "APIError: " + "m" * 200 + " (HTTP 429)")
        self.assertEqual(client.read_session(self.log("b.jsonl", json.dumps({"type": "error", "error": {}})))["error"], "error: ")

    def budget(self, requests: int = 0, **limits) -> client.Budget:
        return client.Budget({**BUDGET, **limits}, dict(BASE), self.tmp, lambda: requests)

    def test_the_budget_has_four_ceilings_and_a_base_for_each(self):
        with self.assertRaises(ValueError):
            client.Budget({**BUDGET, "usd": 1}, BASE, self.tmp)
        with self.assertRaises(ValueError):
            client.Budget(BUDGET, {k: v for k, v in BASE.items() if k != "turns"}, self.tmp)
        b = client.Budget(BUDGET, {**BASE, "unaccounted": []}, self.tmp)
        self.assertEqual(b.base, BASE)

    def test_spend_is_the_base_plus_the_journal_plus_every_session_stream(self):
        self.log("s1.jsonl", step(100, 10), step(50, 5))
        self.log("s2.jsonl", step(10, 1))
        self.log("other.txt", step(1000, 1000))
        s = self.budget(requests=2).spend()
        self.assertEqual({k: s[k] for k in client.Budget.KEYS},
                         {"provider_requests": 3, "turns": 3, "input_tokens": 170, "output_tokens": 17})
        self.assertEqual((s["sessions_started"], s["requests_recorded"], s["unaccounted"]), (2, 2, []))
        self.assertEqual(client.Budget(BUDGET, BASE, self.tmp / "absent").spend()["sessions_started"], 0)

    def test_spend_that_cannot_be_accounted_for_ends_the_run(self):
        self.log("s1.jsonl", step(100, 10))
        self.assertIn("1 sessions were started but 0 provider requests are recorded", self.budget(requests=0).spend()["unaccounted"][0])
        self.log("s2.jsonl", json.dumps({"type": "step_finish", "part": {}}))
        self.assertIn("s2.jsonl: 1 finished steps report no tokens", self.budget(requests=2).spend()["unaccounted"])
        live = self.log("s3.jsonl", "")
        b = self.budget(requests=3)
        self.assertTrue(any("s3.jsonl: a session that started finished no step" in u for u in b.spend()["unaccounted"]))
        self.assertFalse(any("s3.jsonl" in u for u in b.spend(live)["unaccounted"]))
        self.assertTrue(b.reached().startswith("unaccounted: "))

    def test_each_ceiling_is_reached_at_its_value_and_requests_only_beyond_it_while_one_is_in_progress(self):
        self.log("s.jsonl", step(100, 10))
        b = self.budget(requests=1)                      # spent: 2 requests, 1 turn, 110 input, 11 output
        self.assertIsNone(b.reached())
        self.assertEqual(self.budget(requests=1, turns=1).reached(), "max_turns: 1 of 1")
        self.assertEqual(self.budget(requests=1, input_tokens=110).reached(), "max_input_tokens: 110 of 110")
        self.assertEqual(self.budget(requests=1, output_tokens=11).reached(), "max_output_tokens: 11 of 11")
        self.assertIsNone(self.budget(requests=1, output_tokens=12).reached())
        at = self.budget(requests=1, provider_requests=2)
        self.assertEqual(at.reached(), "max_provider_requests: 2 of 2")
        self.assertIsNone(at.reached(in_progress=True))
        self.assertEqual(self.budget(requests=1, provider_requests=1).reached(in_progress=True), "max_provider_requests: 2 of 1")
        self.assertEqual(self.budget(requests=1, turns=1).reached(in_progress=True), "max_turns: 1 of 1")
        self.assertIsNone(self.budget(requests=1, turns=1).exceeded())          # AT a ceiling is not past it
        self.assertEqual(self.budget(requests=1, turns=0 + 1, input_tokens=109).exceeded(), "max_input_tokens exceeded: 110 of 109")
        self.assertEqual(self.budget(requests=0).exceeded()[:13], "unaccounted: ")
        acc = b.account()
        self.assertEqual((acc["limits"], acc["preflight"], acc["reached"], acc["limitation"]), (BUDGET, BASE, None, client.LIMITATION))

    def test_secret_values_are_redacted_from_a_session_stream_longest_first(self):
        log = self.log("r.jsonl", json.dumps({"type": "text", "part": {"text": "KEY=sk-abcdef123 and sk-abcdef123456"}}), step())
        self.assertEqual(client.redact(log, ("sk-abcdef123", "sk-abcdef123456", "")), 2)
        text = log.read_text(encoding="utf-8")
        self.assertNotIn("sk-abcdef", text)
        self.assertEqual(client.read_session(log)["text"], "KEY=[REDACTED] and [REDACTED]")
        before = log.read_bytes()
        self.assertEqual(client.redact(log, ("absent-value",)), 0)
        self.assertEqual(log.read_bytes(), before)

    def test_the_client_s_own_configuration_names_the_endpoint_and_the_key(self):
        cfg = self.tmp / "opencode"
        cfg.mkdir()

        def write(options):
            (cfg / "opencode.json").write_text(json.dumps({"provider": {"p": {"options": options}}}), encoding="utf-8")
        env = {"XDG_CONFIG_HOME": str(self.tmp), "MYKEY": "from-env-123"}
        write({"baseURL": "https://e/v1/", "apiKey": "literal-key-123"})
        self.assertEqual(client.configured_provider("p", env), ("https://e/v1", "literal-key-123"))
        write({"baseUrl": "https://e/v1", "apiKey": "{env:MYKEY}"})
        self.assertEqual(client.configured_provider("p", env), ("https://e/v1", "from-env-123"))
        self.assertEqual(client.configured_provider("p", {"XDG_CONFIG_HOME": str(self.tmp)}), ("https://e/v1", ""))
        self.assertEqual(client.configured_provider("other", env), (None, ""))
        self.assertEqual(client.configured_provider("p", {"XDG_CONFIG_HOME": str(self.tmp / "none")}), (None, ""))
        (self.tmp / "home" / ".config" / "opencode").mkdir(parents=True)
        (self.tmp / "home" / ".config" / "opencode" / "opencode.json").write_text(
            json.dumps({"provider": {"p": {"options": {"baseURL": "https://h/v1", "apiKey": "k"}}}}), encoding="utf-8")
        self.assertEqual(client.configured_provider("p", {"HOME": str(self.tmp / "home")}), ("https://h/v1", "k"))

    def test_the_overlay_fixes_both_models_and_declares_the_route_s_model(self):
        self.assertEqual(client.overlay("9router/ds/deepseek-v4-pro", {"context": 200000, "output": 32768}),
                         {"model": "9router/ds/deepseek-v4-pro", "small_model": "9router/ds/deepseek-v4-pro",
                          "provider": {"9router": {"models": {"ds/deepseek-v4-pro": {"name": "ds/deepseek-v4-pro",
                                                                                     "limit": {"context": 200000, "output": 32768}}}}}})
        self.assertEqual(client.overlay("p/m")["provider"], {"p": {"models": {"m": {"name": "m"}}}})

    def test_the_client_environment_is_built_not_inherited(self):
        with mock.patch.dict(os.environ, {"PATH": "/p", "HOME": "/h", "SECRET_X": "s", "NAMED": "n", "LANG": "C"}, clear=True):
            env = client.environment(("NAMED", "ABSENT"), client.overlay("a/b"))
        self.assertEqual(env, {"PATH": "/p", "HOME": "/h", "NAMED": "n", "LANG": "C",
                               "OPENCODE_CONFIG_CONTENT": json.dumps(client.overlay("a/b"), sort_keys=True)})

    def test_an_unbound_or_unaccountable_session_never_starts(self):
        b = self.budget(requests=0)
        kw = {"model": "a/b", "env": {"PATH": ""}, "budget": b, "turn_cap": 3}
        for k in kw:
            with self.subTest(unbound=k), self.assertRaisesRegex(client.SessionRefused, f"unbound: {k}$"):
                client.session("n", "p", str(self.tmp), self.tmp / "x.jsonl", 1, **{**kw, k: None})
        with self.assertRaisesRegex(client.SessionRefused, "not on the PATH"):
            client.session("n", "p", str(self.tmp), self.tmp / "logs" / "x.jsonl", 1, **kw)
        existing = self.log("old.jsonl", step())
        s = client.session("n", "p", str(self.tmp), existing, 1, **{**kw, "exe": "/bin/false"})
        self.assertEqual((s["started"], s["exit"], s["log"]), (False, None, None))
        self.assertIn("never overwritten", s["stopped"])
        spent = self.budget(requests=0, turns=1)
        self.log("s.jsonl", step())
        s = client.session("n", "p", str(self.tmp), self.tmp / "logs" / "y.jsonl", 1, **{**kw, "budget": spent, "exe": "/bin/false"})
        self.assertEqual((s["started"], s["error"], s["turns"]), (False, s["stopped"], 0))
        self.assertTrue(s["stopped"])
        self.assertFalse((self.tmp / "logs" / "y.jsonl").exists())

    def test_a_running_session_is_stopped_at_the_budget_or_its_turn_cap(self):
        class Range:
            def __init__(self, codes):
                self.codes, self.waits = list(codes), []

            def wait(self, t):
                self.waits.append(t)
                return self.codes.pop(0) if self.codes else None
        log = self.log("live.jsonl", step(1, 1), step(1, 1))
        with mock.patch.object(client, "POLL_S", 0.01):
            self.assertEqual(client.wait_within(Range([0]), log, 5, self.budget(requests=1), 10), (0, None))
            self.assertEqual(client.wait_within(Range([None]), log, 5, self.budget(requests=1), 2), (None, "session turn cap: 2 turns"))
            self.assertEqual(client.wait_within(Range([None, None, 7]), log, 5, self.budget(requests=1), 3), (7, None))
            self.assertEqual(client.wait_within(Range([None]), log, 5, self.budget(requests=1, turns=2), 9), (None, "max_turns: 2 of 2"))
            r = Range([])
            self.assertEqual(client.wait_within(r, log, 0.05, self.budget(requests=1), 9), (None, None))
            self.assertTrue(all(0 <= w <= 0.01 for w in r.waits) and r.waits)


# --------------------------------------------------------------------------------------------- the preflight

class Preflight(Temp):
    def test_the_ledger_accounts_for_every_request_sent(self):
        led = self.tmp / "L.jsonl"
        self.assertEqual(preflight.accounting(led), {"provider_requests": 0, "turns": 0, "input_tokens": 0, "output_tokens": 0, "unaccounted": []})
        for row in ({"n": 1, "event": "sent"}, {"n": 1, "event": "done", "input_tokens": 3, "output_tokens": 1},
                    {"n": 2, "event": "sent"}, {"n": 3, "event": "sent"}, {"n": 3, "event": "done", "input_tokens": 4}):
            preflight._append(led, row)
        self.assertEqual(preflight.accounting(led), {"provider_requests": 3, "turns": 0, "input_tokens": 7, "output_tokens": 1, "unaccounted": [2]})

    def test_an_attested_route_and_its_record(self):
        t = e2e.provider()
        rec = preflight.run(e2e.ROUTE, 3, t, self.tmp / "pre")
        self.assertEqual((rec["verdict"], rec["problems"]), ("ATTESTED", []))
        self.assertEqual(t.calls, ["/models", "/chat/completions", "/chat/completions", "/chat/completions"])
        self.assertEqual(rec["accounting"], {"provider_requests": 4, "turns": 0, "input_tokens": 27, "output_tokens": 3, "unaccounted": []})
        self.assertEqual(rec["observation"]["listing"], {"http": 200, "listed": True, "id": "model-1", "owned_by": "fake"})
        self.assertEqual(json.loads((self.tmp / "pre" / "PREFLIGHT.json").read_text(encoding="utf-8")), rec)
        rows = [json.loads(x) for x in (self.tmp / "pre" / "LEDGER.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(r["n"], r["event"]) for r in rows][:2], [(1, "sent"), (1, "done")])
        self.assertEqual(preflight.fingerprint_fields(rec["observation"]),
                         {"declared_model": "model-1", "listed_id": "model-1", "owned_by": "fake", "served_models": ["model-1"],
                          "system_fingerprint": ["fp-1"]})
        self.assertEqual(preflight.deployment(rec["observation"]), "fp-1")
        with self.assertRaises(FileExistsError):
            preflight.run(e2e.ROUTE, 2, t, self.tmp / "pre")

    def test_every_identity_problem_is_named(self):
        def obs(listing=(200, True), probes=((200, "model-1", "fp"),)):
            return {"declared_model": "model-1", "listing": {"http": listing[0], "listed": listing[1]},
                    "probes": [{"http": h, "served_model": m, "system_fingerprint": f} for h, m, f in probes]}
        self.assertEqual(preflight.identity_problems(obs()), [])
        self.assertEqual(preflight.identity_problems(obs(listing=(500, True))), ["the provider does not list the declared model model-1"])
        self.assertEqual(preflight.identity_problems(obs(listing=(200, False))), ["the provider does not list the declared model model-1"])
        self.assertEqual(preflight.identity_problems(obs(probes=((502, None, "fp"),))), ["probe 0: HTTP 502"])
        self.assertEqual(preflight.identity_problems(obs(probes=((200, "model-1", "fp"), (200, "m2", "fp")))),
                         ["probe 1: served by 'm2', not 'model-1' (an alias or a re-route)"])
        self.assertEqual(preflight.identity_problems(obs(probes=((200, "model-1", "a"), (200, "model-1", "b")))),
                         ["the deployment changed between probes (2 fingerprints)"])
        self.assertIsNone(preflight.deployment(obs(probes=((200, "model-1", preflight.NOT_EXPOSED),))))
        self.assertIsNone(preflight.deployment(obs(probes=((200, "model-1", "a"), (200, "model-1", "b")))))
        rec = preflight.run(e2e.ROUTE, 2, e2e.provider(fingerprint=None), self.tmp / "p2")
        self.assertEqual(rec["verdict"], "ATTESTED")
        self.assertEqual({p["system_fingerprint"] for p in rec["observation"]["probes"]}, {preflight.NOT_EXPOSED})

        def unlisted(path, body=None):
            return (200, {"data": [{"id": "other"}, "junk"]}) if body is None else e2e.provider()(path, body)
        rec = preflight.run(e2e.ROUTE, 2, unlisted, self.tmp / "p3")
        self.assertEqual((rec["verdict"], rec["observation"]["listing"]["listed"]), ("OPAQUE", False))

    def test_a_transport_without_a_key_is_refused(self):
        with self.assertRaisesRegex(preflight.IdentityStop, "no provider key"):
            preflight.http_transport("https://x", "")

    def test_a_router_serving_the_route_under_its_upstream_name_is_attested_only_as_declared(self):
        """The attempt-4 route: 9router lists `ds/deepseek-v4-pro` owned by `ds`, and every completion reports serving
        `deepseek-v4-pro`. Attested only with that served model and that owner declared; the router's own alias
        owner (`combo`) is refused."""
        def router(owner="ds", served="deepseek-v4-pro"):
            def t(path, body=None):
                if body is None:
                    return 200, {"data": [{"id": "ds/deepseek-v4-pro", "owned_by": owner}]}
                return 200, {"model": served, "system_fingerprint": "fp", "usage": {"prompt_tokens": 1, "completion_tokens": 9}}
            return t
        route = "9router/ds/deepseek-v4-pro"
        ok = preflight.run(route, 2, router(), self.tmp / "a", "deepseek-v4-pro", "ds")
        self.assertEqual((ok["verdict"], ok["problems"]), ("ATTESTED", []))
        undeclared = preflight.run(route, 2, router(), self.tmp / "b")
        self.assertEqual(undeclared["verdict"], "OPAQUE")
        self.assertIn("probe 0: served by 'deepseek-v4-pro', not 'ds/deepseek-v4-pro' (an alias or a re-route)", undeclared["problems"])
        alias = preflight.run(route, 2, router(owner="combo"), self.tmp / "c", "deepseek-v4-pro", "ds")
        self.assertEqual(alias["problems"], ["the listing names 'combo' as the model's owner, not 'ds'"])
        self.assertEqual(preflight.run(route, 2, router(owner="combo"), self.tmp / "d", "deepseek-v4-pro", None)["verdict"], "ATTESTED")

    def test_probe_requests_carry_enough_tokens_for_a_reasoning_model(self):
        bodies = []
        def t(path, body=None):
            bodies.append(body)
            return e2e.provider()(path, body)
        preflight.run(e2e.ROUTE, 2, t, self.tmp / "p")
        self.assertEqual([b["max_tokens"] for b in bodies if b], [preflight.PROBE_MAX_TOKENS] * 2)
        self.assertEqual(preflight.PROBE_MAX_TOKENS, 16)


# --------------------------------------------------------------------------------------------- the bundle

class Bundle(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = e2e.project_bundle("a" * 40)

    def refused(self, pattern: str, doc: dict) -> None:
        with self.assertRaisesRegex(bundle.BundleError, pattern):
            bundle.load(doc)

    def test_a_bundle_loads_with_every_spec_compiled_and_its_digest(self):
        p = bundle.load(self.doc)
        self.assertEqual((p.name, p.requirements_path, p.product_roots), ("calc", "docs/requirements.md", ("app", "tests")))
        self.assertEqual(p.digest, hashlib.sha256(json.dumps(self.doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest())
        self.assertEqual(set(p.specs), {o.product_proof_spec_id for o in p.plan.obligations})
        self.assertEqual(bundle.load(json.loads(json.dumps(self.doc))).digest, p.digest)

    def test_what_a_bundle_must_hold(self):
        self.refused("not a project bundle", {**self.doc, "format": "x"})
        self.refused("not a project bundle", [])
        self.refused("holds exactly", {**self.doc, "extra": 1})
        self.refused("do not load", {**self.doc, "requirements": [{"id": "R"}]})
        self.refused("do not load", {**self.doc, "plan": {**self.doc["plan"], "plan_hash": "0" * 64}})
        self.refused("does not compile", {**self.doc, "approvals": []})
        other = copy.deepcopy(self.doc)
        other["plan"] = json.loads(json.dumps(bundle.plain(e2e.Plan.create(
            id="X", baseline="a" * 40, plan_quality_policy=e2e.NOT_PREREGISTERED, obligations=(e2e.PlanObligation(
                "C-ADD", "PPS-" + "0" * 64, "S1", e2e.ObligationRole.INTRODUCE, e2e.EXPECTED_AT_PARENT[e2e.ObligationRole.INTRODUCE],
                (), "r"),)))))
        self.refused("names 1 spec", other)
        self.refused("facts are the public fields", {**self.doc, "facts": {}})
        self.refused("facts are the public fields", {**self.doc, "facts": {"C-ADD": {**self.doc["facts"]["C-ADD"], "stimulus": "x"}}})
        self.refused("facts are the public fields", {**self.doc, "facts": {"C-ADD": {**self.doc["facts"]["C-ADD"], "clause": 1}}})
        self.refused("stories are exactly", {**self.doc, "stories": {}})
        for roots in ([], ["a/b"], [""], [1]):
            with self.subTest(roots=roots):
                self.refused("product_roots", {**self.doc, "product_roots": roots})

    def test_stories_run_in_dependency_order_ties_by_name_and_a_cycle_is_refused(self):
        p = bundle.load(self.doc)
        stories = {"S3": {"depends_on": ["S1"]}, "S2": {"depends_on": ["S3", "OUTSIDE"]}, "S1": {"depends_on": []}, "S0": {"depends_on": []}}
        plan = types.SimpleNamespace(obligations=[types.SimpleNamespace(story_id=s) for s in stories])
        q = bundle.Project(**{**{f: getattr(p, f) for f in p.__dataclass_fields__}, "plan": plan, "stories": stories})
        self.assertEqual(q.order(), ["S0", "S1", "S3", "S2"])
        stories["S1"]["depends_on"] = ["S2"]
        with self.assertRaisesRegex(bundle.BundleError, "cycle"):
            q.order()


# --------------------------------------------------------------------------------------------- verdicts from events

def ev(seq: int, type_: str, **data) -> dict:
    return {"seq": seq, "type": type_, "data": data}


class Verdicts(unittest.TestCase):
    def setUp(self) -> None:
        self.p = bundle.load(e2e.project_bundle("a" * 40))
        self.spec = next(iter(self.p.specs.values()))

    def test_the_delivery_verdict(self):
        decided = [ev(1, "gate/decision"), ev(2, "story/commit", story_id="S1")]
        self.assertEqual(R.delivery(self.p, decided, {"S1": ["COMMIT"]}, None, []), ("PASS", [], {"S1"}))
        self.assertEqual(R.delivery(self.p, [], {}, None, [])[0], "NOT_REACHED")
        self.assertEqual(R.delivery(self.p, [ev(2, "story/commit", story_id="S1")], {"S1": ["COMMIT"]}, None, [])[0], "NOT_REACHED")
        v, blocked, committed = R.delivery(self.p, decided, {"S1": ["COMMIT"]}, "max_turns: 2 of 2", [])
        self.assertEqual((v, blocked, committed), ("FAIL", ["the budget ended the run: max_turns: 2 of 2"], {"S1"}))
        v, blocked, _ = R.delivery(self.p, decided, {"S1": ["COMMIT"]}, None, [{"story": "S1"}])
        self.assertEqual((v, blocked), ("FAIL", ["1 stories were refused"]))
        rolled = [*decided, ev(3, "story/rollback", story_id="S1")]
        v, blocked, committed = R.delivery(self.p, rolled, {"S1": ["COMMIT"]}, None, [])
        self.assertEqual((v, blocked, committed), ("FAIL", ["1 of the plan's stories did not commit: ['S1']"], set()))
        self.assertEqual(R.delivery(self.p, decided, {"S1": ["COMMIT", "RETRY"]}, None, [])[0], "FAIL")
        self.assertEqual(R.delivery(self.p, [ev(1, "gate/decision"), ev(2, "story/retry", story_id="S1"),
                                             ev(3, "story/commit", story_id="S1")], {"S1": ["RETRY", "COMMIT"]}, None, [])[0], "PASS")

    def test_the_productproof_account(self):
        expected = self.spec.candidate_expectation.value
        proof = lambda seq, verdict, agreement=True: ev(seq, "proof/verified", story_id="S1", criterion_id="C-ADD",  # noqa: E731
                                                         candidate="c", agreement=agreement, verdict=verdict)
        acc = R.productproof(self.p, [proof(4, "REFUTED"), proof(9, expected)], {"S1"})
        row = acc["obligations"][0]
        self.assertEqual((row["satisfied_at_last_proof"], row["delivered"], row["last_proof"]["seq"]), (True, True, 9))
        self.assertEqual((acc["total"], acc["satisfied_at_last_proof"], acc["delivered"]), (1, 1, 1))
        self.assertEqual((row["story"], row["criterion"], row["role"], row["spec"], row["expected"]),
                         ("S1", "C-ADD", "INTRODUCE", self.spec.id, expected))
        self.assertEqual(R.productproof(self.p, [proof(9, expected)], set())["delivered"], 0)
        self.assertEqual(R.productproof(self.p, [proof(9, expected, agreement=False)], {"S1"})["satisfied_at_last_proof"], 0)
        self.assertEqual(R.productproof(self.p, [proof(9, expected), proof(10, "REFUTED")], {"S1"})["delivered"], 0)
        self.assertEqual(R.productproof(self.p, [ev(1, "proof/verified", story_id="S9", criterion_id="C-ADD", verdict=expected,
                                                    agreement=True)], {"S1"})["delivered"], 0)
        self.assertIsNone(R.productproof(self.p, [], {"S1"})["obligations"][0]["last_proof"])


# --------------------------------------------------------------------------------------------- the run's own functions

class RunParts(Temp):
    def test_the_kernel_digest_covers_every_kernel_source_by_path(self):
        root = pathlib.Path(R.__file__).resolve().parents[1]
        h = hashlib.sha256()
        for p in sorted(root.rglob("*.py")):
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes().replace(b"\r\n", b"\n") + b"\0")
        self.assertEqual(R.kernel_digest(), h.hexdigest())

    def test_shipped_calibrations_are_read_or_absent(self):
        row = {"probe_id": "p", "probe_digest": "d", "observation_class": "returns", "positive_fixture": "+",
               "negative_fixture": "-", "demonstrated_at": 3}
        cals = R.calibrations([row, {**row, "probe_id": "q"}])
        self.assertEqual([(c.probe_id, c.probe_digest, c.observation_class, c.positive_fixture, c.negative_fixture, c.demonstrated_at)
                          for c in cals], [("p", "d", "returns", "+", "-", 3.0), ("q", "d", "returns", "+", "-", 3.0)])
        self.assertEqual(R.calibrations([]), ())
        with mock.patch.dict(sys.modules, {"aisef2.app.calibrations": None}):
            self.assertEqual(R.calibrations(), ())
        shipped = types.ModuleType("aisef2.app.calibrations")
        shipped.CALIBRATIONS = (row,)
        with mock.patch.dict(sys.modules, {"aisef2.app.calibrations": shipped}):
            self.assertEqual([c.probe_id for c in R.calibrations()], ["p"])

    def test_admission_is_re_derived_and_names_every_failed_check(self):
        p = bundle.load(e2e.project_bundle("a" * 40))
        ok = R.admit(p, e2e.calibrations())
        self.assertEqual((ok["admitted"], ok["failed"]), (True, []))
        self.assertEqual(len(ok["engine_digest"]), 64)
        bad = R.admit(p, ())
        self.assertEqual((bad["admitted"], [f["check"] for f in bad["failed"]]), (False, ["9. probe_calibration"]))
        self.assertNotEqual(bad["result_digest"], ok["result_digest"])

    def test_the_repository_must_hold_the_baseline_and_its_requirements(self):
        base = e2e.make_repo(self.tmp / "repo")
        p = bundle.load(e2e.project_bundle(base))
        R.check_repository(p, self.tmp / "repo")
        with self.assertRaisesRegex(R.RunRefused, "does not hold the plan's baseline"):
            R.check_repository(bundle.load(e2e.project_bundle("b" * 40)), self.tmp / "repo")
        doc = e2e.project_bundle(base)
        doc["requirements_document"]["path"] = "docs/absent.md"
        with self.assertRaisesRegex(R.RunRefused, "is not the bundle's"):
            R.check_repository(bundle.load(doc), self.tmp / "repo")
        doc = e2e.project_bundle(base)
        doc["requirements_document"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(R.RunRefused, "is not the bundle's"):
            R.check_repository(bundle.load(doc), self.tmp / "repo")

    def test_a_git_older_than_b4_needs_is_refused_with_what_was_found(self):
        R.check_git()       # this host's git
        real = subprocess.run

        def git_says(text):
            return lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 0, text, "") if cmd == ["git", "--version"] else real(cmd, *a, **k)
        for text in ("git version 2.31.0\n", "git version 2.55.0.windows.5\n", "git version 3.0.1 (Apple Git-1)\n"):
            with mock.patch.object(R.subprocess, "run", git_says(text)):
                R.check_git()
        for text, found in (("git version 2.30.9\n", "git version 2.30.9"), ("git version 1.99.0\n", "git version 1.99.0"),
                            ("hub version 2.40.0\n", "hub version 2.40.0"), ("", "nothing")):
            with mock.patch.object(R.subprocess, "run", git_says(text)), self.assertRaises(R.RunRefused) as c:
                R.check_git()
            self.assertEqual(str(c.exception), f"git 2.31 or newer is required (B4): found {found}")
        with mock.patch.object(R.subprocess, "run", side_effect=FileNotFoundError("git")), self.assertRaises(R.RunRefused) as c:
            R.check_git()
        self.assertEqual(str(c.exception), "git 2.31 or newer is required (B4): found unavailable: FileNotFoundError")
        if os.name == "posix":      # a git whose output is not UTF-8 is read, not a crash
            (self.tmp / "bin").mkdir()
            (self.tmp / "bin" / "git").write_bytes(b"#!/bin/sh\nprintf 'git version 2.40.1 \\377\\n'\n")
            (self.tmp / "bin" / "git").chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": f"{self.tmp / 'bin'}{os.pathsep}{os.environ['PATH']}"}):
                R.check_git()

    def test_a_run_and_a_check_on_an_old_git_are_refused_before_any_git_command(self):
        base = e2e.make_repo(self.tmp / "source")
        (self.tmp / "p.json").write_text(json.dumps(e2e.project_bundle(base)), encoding="utf-8")
        (self.tmp / "s.json").write_text(json.dumps(e2e.SETTINGS), encoding="utf-8")
        real, seen = subprocess.run, []

        def old_git(cmd, *a, **k):
            if isinstance(cmd, list) and cmd[:1] == ["git"]:    # git only: platform.system() runs `ver` on Windows
                seen.append(cmd[:2])
            return subprocess.CompletedProcess(cmd, 0, "git version 2.30.2\n", "") if cmd == ["git", "--version"] else real(cmd, *a, **k)
        with mock.patch.object(R.subprocess, "run", old_git), self.assertRaisesRegex(R.RunRefused, r"^git 2\.31 or newer"):
            R.execute(bundle.read(self.tmp / "p.json"), settings.read(self.tmp / "s.json"), self.tmp / "source", self.tmp / "out")
        self.assertEqual(seen, [["git", "--version"]])
        self.assertFalse((self.tmp / "out" / "repo").exists())
        rec = json.loads((self.tmp / "out" / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual((rec["failure"]["stage"], rec["delivery_verdict"]), ("repository", "NOT_REACHED"))
        seen.clear()
        err = io.StringIO()
        with mock.patch.object(R.subprocess, "run", old_git), contextlib.redirect_stderr(err):
            code = cli.run(["--check", "--project", str(self.tmp / "p.json"), "--settings", str(self.tmp / "s.json"),
                            "--repo", str(self.tmp / "source")])
        self.assertEqual((code, seen), (2, [["git", "--version"]]))
        self.assertIn("aisef run: refused: git 2.31 or newer is required (B4): found git version 2.30.2", err.getvalue())

    def test_the_probe_interpreter_is_a_private_venv_without_pip_or_host_packages(self):
        exe = R.probe_interpreter(self.tmp / "py")
        self.assertTrue(pathlib.Path(exe).is_file())
        self.assertTrue(exe.startswith(str(self.tmp / "py")))
        out = subprocess.run([exe, "-c", "import sys, importlib.util; print(sys.prefix != sys.base_prefix, "
                                         "importlib.util.find_spec('pip') is None, any('site-packages' in p and "
                                         "not p.startswith(sys.prefix) for p in sys.path))"],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout.split()
        self.assertEqual(out, ["True", "True", "False"])
        with mock.patch.object(R.subprocess, "run"), self.assertRaisesRegex(R.RunRefused, "was not created"):
            R.probe_interpreter(self.tmp / "py2")

    def test_regression_tests_name_produced_or_held_tests_else_the_story_own(self):
        base = e2e.make_repo(self.tmp / "repo")
        p = bundle.load(e2e.project_bundle(base))
        stories = {"S1": {"depends_on": [], "tests": ["tests/a.py"]}, "S2": {"depends_on": [], "tests": ["app/calc.py"]},
                   "S3": {"depends_on": [], "tests": ["tests/c.py"]}}
        q = bundle.Project(**{**{f: getattr(p, f) for f in p.__dataclass_fields__}, "stories": stories})
        self.assertEqual(R.regression_tests(self.tmp / "repo", q, "S3", {}), ("tests/c.py",))
        self.assertEqual(R.regression_tests(self.tmp / "repo", q, "S3", {"S1": False}), ("tests/c.py",))
        self.assertEqual(R.regression_tests(self.tmp / "repo", q, "S3", {"S1": True}), ("tests/a.py",))
        self.assertEqual(R.regression_tests(self.tmp / "repo", q, "S3", {"S1": True, "S2": False}), ("tests/a.py", "app/calc.py"))

    def test_close_shuts_down_or_interrupts_and_names_the_journal(self):
        self.assertEqual(R._close(None), {"journal": None})
        run = RunScope(self.tmp / "out" / "run", "r", spec=SPEC)
        run.begin()
        j = R._close(run)["journal"]
        data = (self.tmp / "out" / "run" / "journals" / "r.jsonl").read_bytes()
        self.assertEqual(j, {"path": "run/journals/r.jsonl", "sha256": hashlib.sha256(data).hexdigest(),
                             "lines": data.count(b"\n"), "closed": "SHUTDOWN"})
        self.assertEqual(R._close(run)["journal"]["closed"], run._state)
        refused = RunScope(self.tmp / "o2" / "run", "r", spec=SPEC)
        refused.begin()
        with mock.patch.object(RunScope, "open_stories", return_value=["S1"]):
            closed = R._close(refused)["journal"]["closed"]
        self.assertTrue(closed.startswith("INTERRUPTED after a refused shutdown: stories ['S1']"), closed)
        self.assertIn("run/interrupted", [e.type for e in refused.events])

    def test_runspec_binds_the_kernel_the_bundle_the_settings_and_the_attested_route(self):
        p = bundle.load(e2e.project_bundle("a" * 40))
        s = settings.load(e2e.SETTINGS)
        pre = preflight.run(e2e.ROUTE, 2, e2e.provider(), self.tmp / "pre")
        spec = R.runspec_of(p, s, pre, "client-x", sys.executable, ad.NoScanner())
        names = {c.name: c for c in spec.capabilities}
        self.assertEqual(names["developer"].grade.value, "ATTESTED")
        self.assertEqual(names["scanner"].grade.value, "OPAQUE")
        self.assertEqual(names["kernel"].grade.value, "VERIFIED")
        other = R.runspec_of(p, settings.load({**e2e.SETTINGS, "max_turns_per_session": 11}), pre, "client-x", sys.executable, ad.NoScanner())
        self.assertNotEqual(spec.runspec_hash, other.runspec_hash)
        self.assertNotEqual(spec.runspec_hash, R.runspec_of(p, s, pre, "client-y", sys.executable, ad.NoScanner()).runspec_hash)
        ruff = R.runspec_of(p, s, pre, "client-x", sys.executable, ad.RuffScanner(sys.executable))
        self.assertEqual({c.name: c for c in ruff.capabilities}["scanner"].grade.value, "VERIFIED")


# --------------------------------------------------------------------------------------------- verification

@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class Verification(e2e.ProductBase):
    def test_every_way_a_run_directory_can_disagree_with_its_journal(self):
        self.execute()
        out = self.tmp / "out"
        rec = json.loads((out / "RUN.json").read_text(encoding="utf-8"))

        def with_record(**changes) -> dict:
            (out / "RUN.json").write_text(json.dumps({**rec, **changes}), encoding="utf-8")
            return verify(self.project, out)
        self.assertEqual(with_record(format="x"), {"verdict": "REFUTED", "problems": [f"RUN.json is not a run record of format {R.FORMAT}"]})
        self.assertIn("the run is not of this project bundle", with_record(bundle_digest="0")["problems"])
        self.assertIn("the run has no journal (it ended before the run began)", with_record(journal=None)["problems"])
        self.assertIn("the journal is not the one RUN.json names (digest or length)",
                      with_record(journal={**rec["journal"], "lines": rec["journal"]["lines"] + 1})["problems"])
        self.assertIn("the journal is not the one RUN.json names (digest or length)",
                      with_record(journal={**rec["journal"], "sha256": "0" * 64})["problems"])
        self.assertIn("the record's ProductProof account is not the one the journal re-derives",
                      with_record(productproof={})["problems"])
        self.assertIn("the run's repository main is not the record's final main",
                      with_record(final_main=self.baseline)["problems"])
        self.assertIn("the record says PASS; the journal re-derives FAIL",
                      with_record(failure={"type": "X"})["problems"])
        self.assertIn("the record says PASS; the journal re-derives FAIL",
                      with_record(budget_stop="max_turns exceeded: 9 of 8")["problems"])
        self.assertEqual(with_record()["verdict"], "VERIFIED")
        self.assertEqual(with_record()["journal_events"], len(self.journal().events))
        journal = out / rec["journal"]["path"]
        journal.write_bytes(journal.read_bytes() + b'{"torn')
        v = with_record(journal={**rec["journal"], "sha256": hashlib.sha256(journal.read_bytes()).hexdigest()})
        self.assertIn("the journal ends in a torn line", v["problems"])


# --------------------------------------------------------------------------------------------- the adapters

class Adapters(Temp):
    def setUp(self) -> None:
        super().setUp()
        e2e.make_repo(self.tmp / "repo")
        self.project = bundle.load(e2e.project_bundle("a" * 40))
        self.events = []
        self.run = types.SimpleNamespace(events=self.events, state=lambda proj: {"S1": {"attempt": 2}}
                                         if proj is ControlProjection.STORY_STATE else None)

    def session(self, *, error=None, text="", write=None):
        def fake(name, prompt, cwd, log, timeout_s, **kw):
            self.prompts.append(prompt)
            if write:
                (pathlib.Path(cwd) / write).write_text("x = 1\n")
            return {"exit": 0, "timed_out": False, "stopped": None, "started": True, "error": error, "text": text,
                    "turns": 1, "tokens": {"input": 1, "output": 1}, "seconds": 0.0, "log": log.name}
        self.prompts = []
        return mock.patch.object(client, "session", fake)

    def test_attempt_of_reads_the_kernel_projection_and_prior_failures(self):
        self.assertEqual(ad.attempt_of(self.run, "S1"), (2, False))
        self.events.append(types.SimpleNamespace(type="failure/observed", data={"story_id": "S2"}))
        self.assertEqual(ad.attempt_of(self.run, "S1"), (2, False))
        self.events.append(types.SimpleNamespace(type="failure/observed", data={"story_id": "S1"}))
        self.assertEqual(ad.attempt_of(self.run, "S1"), (2, True))
        self.assertEqual(ad.attempt_of(self.run, "S9"), (0, False))

    def test_the_developer_commits_what_it_changed_or_says_why_not(self):
        dev = ad.Developer(self.run, self.project, self.tmp / "logs", {}, 5)
        with self.session(write="app/new.py"):
            r = dev.implement("S1", ("C-ADD",), str(self.tmp / "repo"))
        self.assertEqual(r.outcome, O.COMPLETED)
        self.assertEqual(e2e.git(self.tmp / "repo", "rev-parse", "HEAD"), r.candidate)
        self.assertEqual((dev.sessions[0]["candidate"], dev.sessions[0]["attempt"], dev.sessions[0]["developer_committed_itself"]),
                         (r.candidate, 2, False))
        self.assertNotIn("A previous attempt", self.prompts[0])
        with self.session():
            r = dev.implement("S1", ("C-ADD",), str(self.tmp / "repo"))
        self.assertEqual((r.outcome, r.candidate), (O.FAILED, None))
        self.assertIn("the developer changed nothing", r.detail)
        with self.session(error="APIError: down"), self.assertRaisesRegex(ProviderOutage, "down"):
            dev.implement("S1", ("C-ADD",), str(self.tmp / "repo"))
        self.events.append(types.SimpleNamespace(seq=7, type="failure/observed", data={"story_id": "S1", "code": "X", "owner": "DEVELOPER"}))
        with self.session(error="APIError: partial", write="app/more.py"):
            r = dev.implement("S1", ("C-ADD",), str(self.tmp / "repo"))
        self.assertEqual(r.outcome, O.COMPLETED)
        self.assertIn("A previous attempt of this story was not accepted", self.prompts[0])
        self.assertIn("- X (owner DEVELOPER)", self.prompts[0])

    def test_the_review_never_blocks_on_unparsed_text_and_an_outage_is_typed(self):
        rev = ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5)
        scope = types.SimpleNamespace(story_id="S1", root=str(self.tmp / "repo"))
        with self.session(text='noise {"findings": [{"id": "F1", "blocking": true}, "junk", {"id": 2}]} tail'):
            r = rev.review(scope, ("C-ADD",))
        self.assertEqual([(f.id, f.blocking) for f in r.findings], [("F1", True), ("2", False)])
        self.assertEqual(r.detail, "2 findings, parsed=True")
        for text, detail in (("no json here", "0 findings, parsed=False"), ('{"findings": 3}', "0 findings, parsed=True"),
                             ("{bad json}", "0 findings, parsed=True"), ('{"other": []}', "0 findings, parsed=True")):
            with self.subTest(text=text), self.session(text=text):
                self.assertEqual(rev.review(scope, ("C-ADD",)).detail, detail)
        with self.session(error="APIError: down"), self.assertRaises(ProviderOutage):
            rev.review(scope, ("C-ADD",))
        with self.session(error="APIError: late", text='{"findings": []}'):
            self.assertEqual(rev.review(scope, ("C-ADD",)).outcome, O.COMPLETED)


# --------------------------------------------------------------------------------------------- the command

class Command(Temp):
    def cli(self, *argv: str):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.run(list(argv))
            except SystemExit as e:
                code = ("exit", e.code)
        return code, out.getvalue(), err.getvalue()

    def test_each_mode_names_what_it_needs(self):
        p = ("--project", str(self.tmp / "p.json"))
        self.assertEqual(self.cli(*p)[0], ("exit", 2))
        self.assertIn("--settings --repo --out", self.cli(*p)[2])
        self.assertIn("this mode needs --settings --repo", self.cli("--check", *p)[2])
        self.assertIn("this mode needs --out", self.cli("--verify", *p)[2])
        self.assertEqual(self.cli("--check", "--verify", *p)[0], ("exit", 2))

    def test_a_missing_bundle_file_is_an_error_not_a_verdict(self):
        with self.assertRaises(FileNotFoundError):
            cli.run(["--verify", "--project", str(self.tmp / "absent.json"), "--out", str(self.tmp)])
        (self.tmp / "p.json").write_text(json.dumps({"format": "x"}), encoding="utf-8")
        code, _, err = self.cli("--verify", "--project", str(self.tmp / "p.json"), "--out", str(self.tmp))
        self.assertEqual(code, 2)
        self.assertIn("aisef run: refused: not a project bundle", err)


if __name__ == "__main__":
    unittest.main()
