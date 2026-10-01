"""C2-P10 / WP-2.10.2 — model / profile freezing (RFC §23, §24, §28 rule 5), qualified against the local fixture
provider only (tests/v2/fixtures/provider/fixture_provider.py on 127.0.0.1). No real provider is called: a preflight to
any other host is refused before a connection is made."""

import copy
import importlib.util
import json
import pathlib
import sys
import unittest
from dataclasses import asdict
from unittest import mock

from aisef2.cohort import lifecycle as L
from aisef2.cohort import preregistration as P
from aisef2.cohort.lifecycle import CohortState as S
from aisef2.cohort.preregistration import CohortRefused, Refusal as R
from tests.v2 import test_c2_p10_cohort as T

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod      # a dataclass resolves its module through sys.modules
    spec.loader.exec_module(mod)
    return mod


pf = _load("aisef_v2_profile_freeze_test", ROOT / "validation" / "v2" / "profile_freeze.py")
fp = _load("aisef_v2_fixture_provider_test", ROOT / "tests" / "v2" / "fixtures" / "provider" / "fixture_provider.py")
CLIENT = "aisef-preflight (validation/v2/profile_freeze.py)"


def route(model: str) -> "pf.Route":
    return pf.Route(client=CLIENT, provider="fixture", endpoint="fixture-provider (127.0.0.1 stub)", model=model)


def measure(model: str, **provider) -> dict:
    with fp.FixtureProvider(**provider) as fx:
        return pf.preflight(fx.base_url, route(model))


def prereg_with(profile: dict, cap) -> dict:
    return {**T.prereg(1), "execution_profile": profile,
            "model_route": {"capability": cap.name, "route": cap.tuple_["route"]}}


class Classification(unittest.TestCase):
    def test_a_fixed_model_attests(self):
        m = measure("fixture-model-1")
        self.assertEqual(m, {"listing": {"id": "fixture-model-1", "owned_by": "fixture"},
                             "calls": [{"served_model": "fixture-model-1", "deployment": "fp_fixture_1",
                                        "finish_reason": "length"}] * 3})
        cap, why = pf.classify(route("fixture-model-1"), m)
        self.assertEqual((cap.grade.value, why), ("ATTESTED", []))
        binding = dict(cap.tuple_)
        self.assertEqual({k: v for k, v in binding.items() if k != "fingerprint"}, {
            "provider": "fixture", "endpoint": "fixture-provider (127.0.0.1 stub)", "declared_model": "fixture-model-1",
            "route": "fixture/fixture-model-1", "client": CLIENT, "deployment": "fp_fixture_1"})
        self.assertEqual(len(binding["fingerprint"]), 64)
        self.assertEqual(cap.enforcement, pf.ENFORCEMENT)

    def test_every_alias_class_is_opaque_and_binds_no_inferred_model(self):
        cases = {"fixture-combo": ["LISTED_AS_ALIAS", "SERVED_OTHER_MODEL", "UNSTABLE"],
                 "fixture-alias": ["SERVED_OTHER_MODEL"], "fixture-rotating": ["UNSTABLE"],
                 "fixture-unlisted": ["NOT_LISTED"]}
        for model, reasons in cases.items():
            with self.subTest(model=model):
                m = measure(model)
                cap, why = pf.classify(route(model), m)
                self.assertEqual((cap.grade.value, why), ("OPAQUE", reasons))
                served = {c["served_model"] for c in m["calls"]} - {model}
                self.assertFalse(served & set(cap.tuple_.values()), "an OPAQUE identity names a model an alias served")
                self.assertEqual(cap.tuple_["declared_model"], model)

    def test_a_route_is_measured_or_opaque(self):
        self.assertEqual(pf.classify(route("fixture-model-1"), None)[1], ["UNMEASURED"])
        with fp.FixtureProvider() as fx:
            short = pf.preflight(fx.base_url, route("fixture-model-1"), calls=2)
        self.assertEqual(pf.classify(route("fixture-model-1"), short)[1], ["UNDER_MEASURED"])

    def test_no_real_provider_is_ever_called(self):
        with mock.patch.object(pf.urllib.request, "build_opener", side_effect=AssertionError("a socket was opened")):
            for url in ("https://api.openai.com", "http://10.0.0.1:8080", "http://example.invalid"):
                with self.assertRaises(pf.PreflightRefused) as cm:
                    pf.preflight(url, route("fixture-model-1"))
                self.assertIn("LIVE_PROVIDER_REFUSED", str(cm.exception))
        with fp.FixtureProvider() as fx:
            with self.assertRaises(pf.PreflightRefused):
                pf.preflight(fx.base_url + "/nowhere", route("fixture-model-1"))
            self.assertEqual({p for p, _ in fx.requests}, {"/nowhere/v1/models"})


class PerRun(unittest.TestCase):
    def test_the_fingerprint_attests_each_run_and_detects_drift(self):
        frozen, _ = pf.classify(route("fixture-model-1"), measure("fixture-model-1"))
        self.assertEqual(pf.attest_run(frozen, route("fixture-model-1"), measure("fixture-model-1")).identity,
                         frozen.identity)
        with self.assertRaises(pf.AttestationRefused) as cm:
            pf.attest_run(frozen, route("fixture-model-1"), measure("fixture-model-1", deployment="fp_fixture_1b"))
        self.assertEqual(cm.exception.code, "DRIFT")
        with self.assertRaises(pf.AttestationRefused) as cm:
            pf.attest_run(frozen, route("fixture-alias"), measure("fixture-alias"))
        self.assertEqual((cm.exception.code, str(cm.exception)), ("OPAQUE", "OPAQUE: fixture/fixture-alias: SERVED_OTHER_MODEL"))

    def test_drift_after_the_read_demotes_the_cohort(self):
        """WP-2.10.2 into WP-2.10.1: a drifted fingerprint changes the frozen execution profile."""
        frozen, _ = pf.classify(route("fixture-model-1"), measure("fixture-model-1"))
        drifted, _ = pf.classify(route("fixture-model-1"), measure("fixture-model-1", deployment="fp_fixture_1b"))
        before = prereg_with(pf.freeze_profile([frozen], {}, "1" * 40), frozen)
        after = prereg_with(pf.freeze_profile([drifted], {}, "1" * 40), drifted)
        c = L.read_results(L.record_run(L.advance(L.seal(before), S.EVALUATING), "r1"), 5.0)
        x = L.observe_inputs(c, P.frozen_inputs(after))
        self.assertEqual((x.state, x.exposed_reason),
                         (S.EXPOSED, "frozen inputs changed after results were read at 5.0: execution_profile"))


class Profiles(unittest.TestCase):
    def test_the_profile_is_content_addressed(self):
        cap, _ = pf.classify(route("fixture-model-1"), measure("fixture-model-1"))
        profile = pf.freeze_profile([cap], {"max_turns": {"value": 40, "layer": "profile"}}, "1" * 40)
        self.assertEqual(P.runspec_of(profile).runspec_hash, profile["runspec_hash"])
        self.assertEqual(profile["aggregate_min_grade"], "ATTESTED")
        self.assertFalse(pf.bars_sealing(profile))
        other = pf.freeze_profile([cap], {"max_turns": {"value": 41, "layer": "profile"}}, "1" * 40)
        self.assertNotEqual(other["runspec_hash"], profile["runspec_hash"])
        forged = copy.deepcopy(profile)
        forged["aggregate_min_grade"] = "VERIFIED"
        with self.assertRaises(CohortRefused):
            P.runspec_of(forged)

    def test_an_opaque_route_bars_sealing(self):
        fixed, _ = pf.classify(route("fixture-model-1"), measure("fixture-model-1"))
        combo, _ = pf.classify(route("fixture-combo"), measure("fixture-combo"), "model.reviewer")
        mixed = pf.freeze_profile([fixed, combo], {}, "1" * 40)
        self.assertEqual(mixed["aggregate_min_grade"], "OPAQUE")
        self.assertTrue(pf.bars_sealing(mixed))
        with self.assertRaises(CohortRefused) as cm:
            L.seal(prereg_with(mixed, fixed))
        self.assertIs(cm.exception.code, R.OPAQUE_PROFILE)
        self.assertIs(L.seal(prereg_with(pf.freeze_profile([fixed], {}, "1" * 40), fixed)).state, S.SEALED)


class ConfiguredProfile(unittest.TestCase):
    def test_the_configured_development_profile_is_opaque(self):
        routes = pf.configured_routes(ROOT)
        self.assertEqual(sorted(routes), ["designer", "developer", "reviewer", "security"])
        recorded = pf.recorded_measurement(ROOT)
        self.assertEqual(recorded["listing"], {"id": "mycombo", "owned_by": "combo"})
        self.assertEqual([c["served_model"] for c in recorded["calls"]], ["MiniMax-M3"] * 3)
        for role, r in routes.items():
            self.assertEqual((r.client, r.route), ("opencode", "9router/mycombo"))
            for measured, reasons in ((None, ["UNMEASURED"]), (recorded, ["LISTED_AS_ALIAS", "SERVED_OTHER_MODEL"])):
                cap, why = pf.classify(r, measured, f"model.{role}")
                self.assertEqual((cap.grade.value, why), ("OPAQUE", reasons))
                self.assertNotIn("MiniMax-M3", json.dumps(cap.resolved()))   # no model inferred from the alias

    def test_an_opencode_configuration_yields_its_route_and_nothing_else(self):
        cfg = ROOT / "tests/v2/fixtures/provider/opencode.json"
        r = pf.opencode_route(cfg)
        self.assertEqual(r, pf.Route(client="opencode", provider="fixture-router", endpoint="fixture-router",
                                     model="fixture-combo"))
        cap, why = pf.classify(r, None)
        out = json.dumps([asdict(r), cap.resolved(), why])
        for secret in ("FIXTURE-PLACEHOLDER-NOT-A-KEY", "127.0.0.1:9", "apiKey", "baseURL"):
            self.assertNotIn(secret, out)


class Checker(unittest.TestCase):
    def test_the_checker_passes_the_tree_and_refuses_a_forged_attestation(self):
        self.assertEqual(pf.check(ROOT), [])
        bad = json.loads((ROOT / "tests/v2/fixtures/known_bad/profile_freeze.json").read_text(encoding="utf-8"))
        self.assertEqual(pf.record_problems(bad["record"]), [
            "BAD-ALIAS-AS-ATTESTED: recorded ATTESTED [], the measurement classifies OPAQUE ['SERVED_OTHER_MODEL']"])

    def test_the_record_checks_fingerprints_profiles_and_inferred_models(self):
        rec = json.loads((ROOT / pf.RECORD_REL).read_text(encoding="utf-8"))
        self.assertEqual(pf.record_problems(rec), [])
        fixed = next(c for c in rec["classifications"] if c["id"] == "FIX-FIXED")
        forged = copy.deepcopy(fixed)
        forged["measurement"]["calls"] = [dict(c, deployment="fp_other") for c in forged["measurement"]["calls"]]
        self.assertEqual(pf.record_problems({"classifications": [forged]}),
                         ["FIX-FIXED: the recorded capability is not the one its measurement derives",
                          "FIX-FIXED: the fingerprint is not the sha256 of the recorded preflight"])
        alias = copy.deepcopy(next(c for c in rec["classifications"] if c["id"] == "FIX-ALIAS"))
        alias["capability"]["binding"]["declared_model"] = "fixture-model-2"
        self.assertIn("FIX-ALIAS: an OPAQUE identity binds a model inferred from an alias: ['fixture-model-2']",
                      pf.record_problems({"classifications": [alias]}))
        profile = copy.deepcopy(rec["profiles"][0])
        profile["bars_sealing"] = not profile["bars_sealing"]
        self.assertTrue(pf.record_problems({"profiles": [profile]}))

    def test_the_evidence_record_re_derives(self):
        from validation.qualification import c2_p10_profile as B
        self.assertEqual(B.check(), [])
        rec = json.loads((ROOT / B.OUT_REL).read_text(encoding="utf-8"))
        self.assertEqual((rec["verdict"], rec["live_provider_calls"]), ("attestation qualified", 0))
        self.assertEqual({c["id"]: c["grade"] for c in rec["classifications"] if c["id"].startswith("FIX-")}, {
            "FIX-FIXED": "ATTESTED", "FIX-COMBO": "OPAQUE", "FIX-ALIAS": "OPAQUE", "FIX-ROTATING": "OPAQUE",
            "FIX-UNLISTED": "OPAQUE", "FIX-UNMEASURED": "OPAQUE"})


if __name__ == "__main__":
    unittest.main()
