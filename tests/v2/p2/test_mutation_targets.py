"""The mutation tool locates every P2 target, including a method named by its class (`Class.method`) where one module
has several methods of that name (protocol.py's `__post_init__`s)."""

import ast
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("p2_mutation_tool", ROOT / "validation" / "v2" / "mutation.py")
mu = importlib.util.module_from_spec(_s)
_s.loader.exec_module(mu)


class Locator(unittest.TestCase):
    def test_a_class_qualified_name_picks_that_class_method(self):
        tree = ast.parse("class A:\n    def f(self):\n        return 1\n\n\nclass B:\n    def f(self):\n        return 2\n")
        self.assertEqual(mu._root(tree, "B.f")[0].lineno, 7)
        self.assertEqual(mu._root(tree, "f")[0].lineno, 2)
        self.assertIsNone(mu._root(tree, "C.f"))

    def test_a_return_of_None_is_not_mutated_into_itself(self):
        got = [d for d, _ in mu.mutants("def f(x):\n    if x:\n        return None\n    return x\n", "f", {})]
        self.assertEqual([d for d in got if "returns None" in d], ["L4 returns None"])

    def test_a_reference_models_refusal_message_is_not_a_mutation_site(self):
        src = "def f(x):\n    if x > 1:\n        raise Refused(f'seq {x}: refused ' + 'here')\n    return x\n"
        got = [d for d, _ in mu.mutants(src, "f", {})]
        self.assertEqual(sorted(got), sorted(["L2 Gt->LtE", "L2 condition negated", "L4 returns None"]))
        self.assertTrue(all(k[0].startswith("tests/v2/refmodel/") and v for k, v in mu.AUDITED.items()))

    def test_every_target_resolves(self):
        for target in mu.TARGETS:
            rel, func = target.split("::")
            with self.subTest(target=target):
                self.assertIsNotNone(mu._root(ast.parse((ROOT / rel).read_text(encoding="utf-8")), func))


class TableAuthorityMigration(unittest.TestCase):
    """Owner directive 2026-11-26 LANE A §1: story_state._OUTCOMES/_WITHIN and terminal_state._RUN were consolidated
    into aisef2/journal/transitions.py (STORY/WITHIN/RUN/symbol_of). These adversarial controls prove the mutation
    coverage moved WITH the authority and did not silently disappear."""

    TABLE = "aisef2/journal/transitions.py"
    MOVED = ("STORY", "WITHIN", "RUN", "symbol_of")
    RETIRED = ("aisef2/journal/projections/story_state.py::_OUTCOMES",
               "aisef2/journal/projections/story_state.py::_WITHIN",
               "aisef2/journal/projections/terminal_state.py::_RUN")

    def test_the_moved_authority_is_targeted_resolves_and_generates_mutants(self):
        src = (ROOT / self.TABLE).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for sym in self.MOVED:
            with self.subTest(surface=sym):
                self.assertIn(f"{self.TABLE}::{sym}", mu.TARGETS, "not registered as a mutation target")
                self.assertIsNotNone(mu._root(tree, sym), "does not resolve in the source")
                self.assertTrue(mu.mutants(src, sym, {}), "generates no mutants — coverage vanished")
                # killed by the table's own digest pin: a value mutation cannot survive it
                self.assertIn("tests/v2/test_v23_transitions.py", mu.TARGETS[f"{self.TABLE}::{sym}"])

    def test_the_retired_symbols_cannot_linger_as_dead_targets(self):
        for gone in self.RETIRED:
            rel, func = gone.split("::")
            with self.subTest(target=gone):
                self.assertNotIn(gone, mu.TARGETS, "consolidated symbol still registered as a target")
                self.assertIsNone(mu._root(ast.parse((ROOT / rel).read_text(encoding="utf-8")), func),
                                  "consolidated symbol still present in the source")

    def test_a_table_value_mutation_is_caught_by_the_digest_pin(self):
        # the kill mechanism, demonstrated: any edit to a table value moves TABLE_DIGEST, which
        # tests/v2/test_v23_transitions.py asserts as a literal (C-1 §3.1) — so the mutant is killed
        import aisef2.journal.transitions as tr
        from aisef2.product.contract import digest
        self.assertEqual(digest(tr._digest_form()), tr.TABLE_DIGEST)                    # the pin matches the live table
        form = tr._digest_form()
        form["STORY"] = [row for row in form["STORY"] if row != ["ACTIVE", "story/commit", "DECIDED_COMMIT"]]
        self.assertNotEqual(digest(form), tr.TABLE_DIGEST)                              # drop one move -> pin breaks -> killed


class V23Retirement(unittest.TestCase):
    """Owner ruling 2026-11-27 §1-2: fail-closed controls on the v2.3 mutation-retirement mapping. Retirement stops
    demanding a fresh measurement of a GONE symbol, never grants its successor a verdict, is narrow to the v2.3 era,
    and refuses a malformed, resurrected, provenance-less or mis-mapped entry."""

    OUTCOMES = "aisef2/journal/projections/story_state.py::_OUTCOMES"

    def test_the_live_mapping_is_exactly_the_three_and_valid(self):
        self.assertEqual(set(mu.V23_RETIRED), {
            self.OUTCOMES, "aisef2/journal/projections/story_state.py::_WITHIN",
            "aisef2/journal/projections/terminal_state.py::_RUN"})
        self.assertEqual(sorted(mu.V23_RETIRED.values()), [
            "aisef2/journal/transitions.py::RUN", "aisef2/journal/transitions.py::STORY",
            "aisef2/journal/transitions.py::WITHIN"])
        self.assertNotIn("aisef2/journal/transitions.py::symbol_of", mu.V23_RETIRED.values())  # symbol_of is NEW authority
        self.assertEqual(mu.v23_retirement_problems(ROOT), [])
        self.assertEqual(mu.v23_retired_absent(ROOT), set(mu.V23_RETIRED))  # all three provably gone from source

    def test_a_retired_symbol_is_dropped_from_re_check_but_its_successor_keeps_its_obligation(self):
        probs = mu.check(ROOT)
        for sym in mu.V23_RETIRED:
            self.assertFalse(any(sym in p for p in probs), f"{sym} is still demanded — retirement not applied")
        for succ in mu.V23_RETIRED.values():   # NOT granted PASS/MEASURED/QUALIFIED: still owes a measurement
            self.assertIn(f"{succ} has no mutation result", probs)

    def test_NEG_missing_successor(self):
        with mock.patch.object(mu, "V23_RETIRED", {**mu.V23_RETIRED, self.OUTCOMES: "aisef2/journal/transitions.py::NOPE"}):
            self.assertTrue(any("missing successor" in p for p in mu.v23_retirement_problems(ROOT)))

    def test_NEG_invalid_mapping(self):   # a real target, but not a transition-table surface
        bad = {**mu.V23_RETIRED, self.OUTCOMES: "aisef2/journal/projections/story_state.py::StoryState.step"}
        with mock.patch.object(mu, "V23_RETIRED", bad):
            self.assertTrue(any("invalid mapping" in p for p in mu.v23_retirement_problems(ROOT)))

    def test_NEG_resurrected_legacy_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            rel = "aisef2/journal/projections/story_state.py"
            (root / rel).parent.mkdir(parents=True)
            (root / rel).write_text("_OUTCOMES = {}\n", encoding="utf-8")                 # the gone symbol is back
            (root / mu.RECORDS["P3"]).parent.mkdir(parents=True, exist_ok=True)
            (root / mu.RECORDS["P3"]).write_text(json.dumps({"targets": [{"target": self.OUTCOMES}]}), encoding="utf-8")
            self.assertNotIn(self.OUTCOMES, mu.v23_retired_absent(root))                   # not absent -> stays checked
            self.assertTrue(any("resurrected" in p and "_OUTCOMES" in p for p in mu.v23_retirement_problems(root)))

    def test_NEG_missing_historical_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)                                                         # no source, empty P3 record
            (root / mu.RECORDS["P3"]).parent.mkdir(parents=True)
            (root / mu.RECORDS["P3"]).write_text(json.dumps({"targets": []}), encoding="utf-8")
            self.assertTrue(any("provenance missing" in p for p in mu.v23_retirement_problems(root)))

    def test_NEG_unmeasured_successor_stays_a_blocker_and_unrelated_stale_are_not_hidden(self):
        probs = mu.check(ROOT)
        for succ in mu.V23_RETIRED.values():                                              # §2: successor not granted a verdict
            self.assertIn(f"{succ} has no mutation result", probs)
        # an UNRELATED pre-existing stale target is NOT hidden by the retirement (the blocker count is not silently cut)
        self.assertTrue(any("old_path_audit.py::check" in p and "target changed" in p for p in probs))

    def test_NEG_a_reduced_records_without_the_v23_phase_is_a_noop_not_a_crash(self):
        # test_v21_mutation_runner patches m.RECORDS to a toy/empty dict with no "P3"; v23_retirement_problems (run by
        # check()) must return [] rather than raise KeyError on RECORDS[V23_RETIRED_PHASE] (regression, owner CI 2026-11-27).
        for reduced in ({}, {"TOY": "closure-evidence/v2/toy/MUTATION.json"}):
            with mock.patch.object(mu, "RECORDS", reduced):
                self.assertEqual(mu.v23_retirement_problems(ROOT), [])

    def test_the_integrity_control_is_enforced_by_the_mutation_qualification_path(self):
        """Owner follow-up 2026-11-27: the retirement integrity controls must be enforced BY the mutation
        qualification path — the calibrated `mutation` checker whose clean() == mutation.check() feeds
        validation/v23/q0_round.py::problems for Q0 — not merely callable here. A broken mapping must turn THAT
        checker red through its clean(), and the live mapping must carry no integrity problem on that path."""
        spec = importlib.util.spec_from_file_location(
            "aisef_v2_checker_calibration_pathtest", ROOT / "validation" / "v2" / "checker_calibration.py")
        cc = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cc                             # dataclass needs the module registered during exec
        spec.loader.exec_module(cc)
        chk = cc._mutation()                                   # the calibrated 'mutation' checker
        self.assertEqual(chk.name, "mutation")
        mod = sys.modules["aisef_v2_mutation"]                 # the exact module its clean() calls check() on
        live = chk.clean()
        self.assertTrue(live, "the mutation gate is ALREADY red for other reasons (stale targets + unmeasured successors)")
        self.assertFalse(any(s in p for p in live for s in     # live mapping is valid: no integrity problem on the path
                             ("missing successor", "invalid mapping", "resurrected", "provenance missing")))
        bad = {**mod.V23_RETIRED, self.OUTCOMES: "aisef2/journal/transitions.py::NOPE"}
        with mock.patch.object(mod, "V23_RETIRED", bad):       # an invalid mapping names itself through check()/the Q0 checker
            red = chk.clean()
            self.assertTrue(any("missing successor" in p for p in red),
                            "an invalid retirement mapping must name its own failure through the mutation qualification path")
            self.assertGreater(len(red), len(live))            # ADDED on top of the pre-existing reds: still red for other reasons

    def test_NEG_narrow_to_the_v23_era_v21_v22_replay_is_never_interpreted(self):
        rec = {"targets": [{"target": self.OUTCOMES}]}
        self.assertNotIn(self.OUTCOMES, mu.superseded(rec, "V2.1", ROOT))                  # frozen replay untouched
        self.assertIn(self.OUTCOMES, mu.superseded(rec, "P3", ROOT))                       # v2.3 era: retired
        self.assertEqual(mu.V21_RETIRED, ("aisef2/probe/process_effect.py::HARNESS/guarded",))  # legacy table unchanged


if __name__ == "__main__":
    unittest.main()
