"""WP-2.0.1 — the Cycle-2 baseline guard, the probe catalog and the probe source rules (Q0)."""

import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import SubjectKind  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.probe import catalog, python_callable as pc, python_callable_v2 as pc2  # noqa: E402


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cb = _load("aisef_v2_cycle2_baseline", "validation/v2/cycle2_baseline.py")
ps = _load("aisef_v2_probe_static_checks", "validation/v2/probe_static_checks.py")
FIXTURES = ROOT / "tests" / "v2" / "fixtures" / "known_bad"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class Catalog(unittest.TestCase):
    def test_the_cycle1_probe_stays_registered_at_its_frozen_digest_superseded_by_the_second_identity(self):
        # WP-2.4.1 (DECISION-6): the Cycle-1 entry is registered, inactive, at the frozen digest; the one active
        # entry for python_callable is the second identity
        entries = catalog.active()
        self.assertEqual(list(entries), [SubjectKind.PYTHON_CALLABLE])
        e = entries[SubjectKind.PYTHON_CALLABLE]
        self.assertEqual((e.probe_id, e.probe_digest, e.cycle), (pc2.PROBE_ID, pc2.DIGEST, 2))
        c1 = next(x for x in catalog.CATALOG if x.probe_id == pc.PROBE_ID)
        self.assertEqual((c1.probe_digest, c1.cycle, c1.active), (cb.CYCLE1_PROBE["digest"], 1, False))
        self.assertEqual(pc.DIGEST, cb.CYCLE1_PROBE["digest"])

    def test_registry_and_catalogue_are_built_from_the_catalog(self):
        self.assertIsNotNone(catalog.registry())
        probes = catalog.catalogue()
        self.assertIsInstance(probes[SubjectKind.PYTHON_CALLABLE], pc2.PythonCallableV2Probe)
        self.assertEqual(list(catalog.probes_by_id()), [pc.PROBE_ID, pc2.PROBE_ID])

    def test_two_active_probes_for_one_kind_are_refused_F4(self):
        second = catalog.CatalogEntry("probe.python_callable_v2", "b" * 64, SubjectKind.PYTHON_CALLABLE, ("returns_bytes",),
                                      catalog.ProbeMetadata("probe.python_callable_v2", "b" * 64, lambda s: None),
                                      pc.PythonCallableProbe, "aisef2/probe/python_callable_v2.py", "python_callable_v2",
                                      "in_harness_process", "captured_stdout", "call", 2)
        problems = catalog.problems_of((*catalog.CATALOG, second))
        self.assertTrue(any("F4" in p for p in problems), problems)
        with self.assertRaises(InvariantError):
            catalog.catalogue((*catalog.CATALOG, second))
        # superseding keeps the Cycle-1 identity registered and makes the second the one that compiles
        superseded = catalog.CatalogEntry(**{**{f: getattr(catalog.CATALOG[0], f) for f in catalog.CatalogEntry.__slots__},
                                             "active": False})
        self.assertEqual(catalog.problems_of((superseded, second)), [])
        self.assertEqual(list(catalog.probes_by_id((superseded, second))), [pc.PROBE_ID, "probe.python_callable_v2"])
        self.assertEqual(catalog.active((superseded, second))[SubjectKind.PYTHON_CALLABLE].probe_id, "probe.python_callable_v2")

    def test_DESIGN_CHECK_1_a_subject_that_owns_stdout_cannot_share_it_with_the_protocol(self):
        with self.assertRaises(InvariantError):
            catalog.CatalogEntry("probe.cli_invocation", "c" * 64, SubjectKind.CLI_INVOCATION, ("exits",),
                                 catalog.ProbeMetadata("probe.cli_invocation", "c" * 64, lambda s: None),
                                 pc.PythonCallableProbe, "aisef2/probe/cli_invocation.py", "cli_invocation",
                                 "child_of_harness", "captured_stdout", "invocation", 2)


class ProbeRules(unittest.TestCase):
    def test_the_real_probe_tree_passes_every_rule(self):
        self.assertEqual(ps.check(ROOT), [])

    def test_each_rule_rejects_its_known_bad_fixture(self):
        for name in ("no_clock_in_probe_facts", "no_test_artefact_in_probes", "closed_dispatch_in_scenario_probes",
                     "single_placeholder_token", "protocol_channel_discipline"):
            fx = _fixture(name)
            with self.subTest(rule=fx["rule"]):
                found = ps.violations(fx["path"], fx["source"], (fx["rule"],), fx.get("facts"))
                self.assertTrue(any(fx["expect"] in v for v in found), found)

    def test_the_scoped_rules_are_scoped_by_declaration_not_by_exemption(self):
        # the Cycle-1 probe's class dispatch ends in an else; declared "call", it is out of scope; declared "scenario"
        # the same source is rejected — nothing about the Cycle-1 probe is special-cased
        src = (ROOT / "aisef2/probe/python_callable.py").read_text(encoding="utf-8")
        rules = ("CLOSED_DISPATCH_IN_SCENARIO_PROBES",)
        self.assertEqual(ps.violations("aisef2/probe/python_callable.py", src, rules,
                                       {"subject_process": "in_harness_process", "stimulus_shape": "call"}), [])
        self.assertTrue(ps.violations("aisef2/probe/python_callable.py", src, rules,
                                      {"subject_process": "in_harness_process", "stimulus_shape": "scenario"}))

    def test_the_closure_rejects_a_stale_digest_and_an_unregistered_module(self):
        fx = _fixture("probe_catalog_closure")
        found = ps.closure_problems(fx["entries"], fx["modules"], set(fx["fixtures_present"]), fx["frozen"])
        self.assertTrue(any("catalog digest" in p for p in found), found)
        modules = dict(fx["modules"], **{"aisef2/probe/other.py": {"probe_id": "probe.other", "digest": "d" * 64,
                                                                   "classes": ["x"], "metadata_id": "probe.other",
                                                                   "metadata_digest": "d" * 64}})
        found = ps.closure_problems(fx["entries"], modules, set(fx["fixtures_present"]), fx["frozen"])
        self.assertTrue(any("not registered" in p for p in found), found)


class Baseline(unittest.TestCase):
    def test_the_committed_freeze_manifest_holds(self):
        self.assertEqual(cb.check(), [])

    def test_a_changed_cycle1_probe_digest_fails_R2(self):
        problems = cb.check(live_probe_digest="0" * 64)
        self.assertTrue(any("R2" in p for p in problems), problems)

    def test_the_manifest_baseline_must_equal_the_inherited_identities(self):
        manifest = json.loads((ROOT / cb.MANIFEST_REL).read_text(encoding="utf-8"))
        self.assertEqual(cb.manifest_problems(manifest), [])
        wrong = dict(manifest, architecture_baseline=dict(manifest["architecture_baseline"], cycle1_aisef2_tree="0" * 40))
        self.assertTrue(any("cycle1_aisef2_tree" in p for p in cb.manifest_problems(wrong)))

    def test_every_owner_decision_is_recorded_with_its_text_and_verdict(self):
        record = json.loads((ROOT / cb.DECISIONS_REL).read_text(encoding="utf-8"))
        self.assertEqual(cb.decisions_problems(record), [])
        missing = dict(record, decisions=[d for d in record["decisions"] if d["id"] != "DECISION-3"])
        self.assertTrue(any("DECISION-3" in p for p in cb.decisions_problems(missing)))


if __name__ == "__main__":
    unittest.main()
