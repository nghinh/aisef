"""WP-6.3 — no dual authority, on the real tree (owner authorization §3–§9, §17–§20).

The committed authority inventory matches reality in both directions; an unenumerated authority, a stale row, a
dual-authority function (even one whose two paths agree) and a legacy fallback each fail the audit, closed; every
V1 authority family is poisoned while real ORCH fixtures run unchanged (R1); developer tests changed five ways leave
the product proof identical (R2); parent-side developer artefacts that explode never run (R3); only an explicit
immutable reference selects evidence, whatever the timestamps say (R4); retry state is the journal and nothing beside
it (R5); every control decision rests on journal facts that precede it (R6)."""

import importlib.util
import importlib
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.v2.test_p6_orchestration as e2e  # noqa: E402
from aisef2.arch.enums import ContractSatisfaction as CS, ControlProjection as P, EventType as T, ObligationRole  # noqa: E402
from aisef2.control import budget  # noqa: E402
from aisef2.journal import format3 as f3  # noqa: E402
from aisef2.journal.event import Event, JournalError  # noqa: E402
from aisef2.orchestrate import story_runner as sr  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from tests.v2.p4.test_run_scope import spec as RUN_SPEC  # noqa: E402
from tests.v2.p4.world import closed_after  # noqa: E402
from tests.v2.test_v2_005 import record as sealed_record  # noqa: E402


def _load(name, rel):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


opa = _load("aisef_v2_old_path_audit", "validation/v2/old_path_audit.py")
COPIED = ("aisef2", "aisef", "validation/v2", "tests/v2", "pyproject.toml", opa.INVENTORY_REL)


def snapshot() -> pathlib.Path:
    """A copy of everything the audit reads, to inject into."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="nda-"))
    for rel in COPIED:
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, d / rel, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, d / rel)
    return d


class Inventory(unittest.TestCase):
    """§2, §3, §17–§19 on the real tree."""

    def test_the_committed_inventory_matches_reality_in_both_directions(self):
        self.assertEqual(opa.check(ROOT), [])
        inv = json.loads((ROOT / opa.INVENTORY_REL).read_text(encoding="utf-8"))
        self.assertEqual(inv["summary"]["UNCLASSIFIABLE"], 0)
        self.assertEqual(inv["summary"]["REMOVED"], 0)
        self.assertEqual(inv["legacy_references"], [])
        self.assertTrue(all(r["disposition"] in opa.DISPOSITIONS and set(r["authority_kind"]) <= set(opa.KINDS) for r in inv["rows"]))
        v1 = [r for r in inv["rows"] if r["path"].startswith("aisef/")]
        self.assertTrue(all(r["disposition"] == "UNREACHABLE" for r in v1))
        self.assertGreaterEqual(len(v1), 100)
        self.assertEqual({r["disposition"] for r in inv["rows"] if r["path"] == "aisef2/orchestrate/seam.py"}, {"COMPATIBILITY_NONAUTHORITATIVE"})
        self.assertEqual({r["disposition"] for r in inv["rows"] if r["path"].startswith("tests/")}, {"HISTORICAL_ONLY"})
        self.assertEqual(inv["entrypoints"]["v2_console_script"], False)
        self.assertEqual(opa.inventory_digest(inv), opa.inventory_digest(opa.inventory(ROOT)))

    def test_an_unenumerated_authority_and_a_stale_row_each_fail_the_audit(self):
        d = snapshot()
        (d / "aisef2/orchestrate/side_gate.py").write_text(
            "from aisef2.arch.enums import EventType as T\n\n\ndef decide(run):\n    return run.append(T.GATE_DECISION, {}).seq\n", encoding="utf-8")
        problems = opa.check(d)
        self.assertIn("UNENUMERATED authority: aisef2/orchestrate/side_gate.py::decide (ACTIVE_V2_AUTHORITY) is in the tree and not in the inventory", problems)
        (d / "aisef2/orchestrate/side_gate.py").write_text("", encoding="utf-8")
        inv = json.loads((d / opa.INVENTORY_REL).read_text(encoding="utf-8"))
        inv["rows"].append({"id": "aisef/control/gate.py::judge_everything", "path": "aisef/control/gate.py", "symbol": "judge_everything",
                            "authority_kind": ["GATE_DECISION"], "reachable_from": [], "disposition": "UNREACHABLE", "replacement": None, "evidence": "x"})
        (d / opa.INVENTORY_REL).write_text(opa.render(inv), encoding="utf-8")
        self.assertEqual(opa.check(d), ["STALE inventory row: aisef/control/gate.py::judge_everything no longer resolves to an authority in the tree"])

    def test_dual_authority_fails_even_when_both_paths_agree(self):
        d = snapshot()
        (d / "aisef2/orchestrate/twin.py").write_text(
            "from aisef.control.gate import judge_only\nfrom aisef2.control.owner import FailureCode, classify\n\n\n"
            "def decide(story):\n    legacy = judge_only(story)\n    mine = classify(FailureCode.UNKNOWN)\n    return legacy and mine\n", encoding="utf-8")
        problems = opa.check(d)
        self.assertIn("DUAL_AUTHORITY: aisef2/orchestrate/twin.py:5 decide names ['judge_only'] — an old authority is reachable again", problems)
        self.assertIn("LEGACY_IMPORT: aisef2/orchestrate/twin.py:1 aisef.control.gate — an old authority is reachable again", problems)
        self.assertTrue(any(p.startswith("PROOF NO_OLD_GATE_AUTHORITY does not hold") for p in problems))
        self.assertTrue(any(p.startswith("UNCLASSIFIABLE: aisef/control/gate.py::<module>") for p in problems))

    def test_a_legacy_fallback_fails(self):
        d = snapshot()
        (d / "aisef2/orchestrate/fallback.py").write_text(
            "import aisef.control.gate as legacy\n\n\ndef decide(story, v2):\n    try:\n        return v2(story)\n"
            "    except Exception:\n        return legacy.evaluate(story)\n\n\n"
            "def decide2(story, v2_unknown, legacy_result=None):\n    if v2_unknown:\n        return legacy.judge_only(story)\n    return 1\n", encoding="utf-8")
        problems = opa.check(d)
        self.assertIn("LEGACY_FALLBACK: aisef2/orchestrate/fallback.py:4 decide names ['legacy'] — an old authority is reachable again", problems)
        self.assertIn("LEGACY_FALLBACK: aisef2/orchestrate/fallback.py:11 decide2 names ['legacy'] — an old authority is reachable again", problems)

    def test_an_adapter_that_touches_v1_and_an_old_authority_reachable_again_fail(self):
        d = snapshot()
        seam = d / "aisef2/orchestrate/seam.py"
        seam.write_text("import aisef.control.obligation\n" + seam.read_text(encoding="utf-8"), encoding="utf-8")
        problems = opa.check(d)
        self.assertIn("ADAPTER touches V1: aisef2/orchestrate/seam.py imports [(1, 'aisef.control.obligation')]", problems)
        self.assertTrue(any(p.startswith("DISPOSITION moved: aisef2/orchestrate/seam.py::admit_legacy is UNCLASSIFIABLE") for p in problems))
        self.assertTrue(any(p.startswith("DISPOSITION moved: aisef/control/obligation.py::<module> is UNCLASSIFIABLE") for p in problems))


# --------------------------------------------------------------------------------------------- R1: poisoning

class PoisonedV1(RuntimeError):
    pass


class _PoisonFinder:
    """A meta-path finder that refuses every import of the frozen V1 kernel and counts the attempts."""

    def __init__(self):
        self.attempts = []

    def find_spec(self, name, path=None, target=None):
        if name == "aisef" or name.startswith("aisef."):
            self.attempts.append(name)
            raise PoisonedV1(f"import of {name}")
        return None


class Poisoned(unittest.TestCase):
    """§4, §20: every former V1 authority family raises if reached; real ORCH fixtures run unchanged."""

    def setUp(self):
        # every V1 family module is imported first (as an earlier test of the suite may already have done), so the
        # poison below covers every named symbol every run — functions, classes and the one Enum — whatever the order
        for rel in opa.V1_SYMBOLS:
            importlib.import_module(rel[:-3].replace("/", "."))
        self.finder = _PoisonFinder()
        sys.meta_path.insert(0, self.finder)
        self.addCleanup(self._unpoison)
        self.calls = []
        self.poisoned = []
        for rel, symbols in opa.V1_SYMBOLS.items():
            module = sys.modules[rel[:-3].replace("/", ".")]
            for sym in symbols:
                obj, attr = (module, sym) if "." not in sym else (getattr(module, sym.split(".")[0], None), sym.split(".")[1])
                if obj is None or not hasattr(obj, attr):
                    continue
                poison = self._poison(f"{rel}::{sym}")
                target = getattr(obj, attr)
                patcher = mock.patch.object(obj, attr, poison if not isinstance(target, type) else self._poisoned_class(target, f"{rel}::{sym}"))
                patcher.start()
                self.addCleanup(patcher.stop)
                self.poisoned.append(f"{rel}::{sym}")

    def _poison(self, name):
        def raiser(*a, **k):
            self.calls.append(name)
            raise PoisonedV1(name)
        return raiser

    def _poisoned_class(self, cls, name):
        calls = self.calls
        try:
            class Poisoned(cls):
                def __init__(self, *a, **k):
                    calls.append(name)
                    raise PoisonedV1(name)
            return Poisoned
        except TypeError:   # an Enum with members cannot be subclassed: a proxy that raises on any call or member access
            class PoisonedEnum:
                def __call__(self, *a, **k):
                    calls.append(name)
                    raise PoisonedV1(name)

                def __getattr__(self, attr):
                    calls.append(name)
                    raise PoisonedV1(name)
            return PoisonedEnum()

    def _trace(self, case_name, story_fn):
        case = e2e.Orchestration(case_name)
        case.setUp()
        try:
            r = story_fn(case)
            events = list(case.run.events)
            proofs = [(e.data["criterion_id"], e.data["agreement"], e.data.get("verdict")) for e in events if e.type == "proof/verified"]
            budgets = case.run.state(P.BUDGETS)
            return {"outcomes": [a.outcome for a in r.attempts], "failures": [e.data["code"] for e in events if e.type == "failure/observed"],
                    "types": [e.type for e in events], "proofs": proofs, "checks": [(e.data["check"], e.data["passed"]) for e in events if e.type == "gate/check"],
                    "budgets": {"developer": dict(budgets["developer"]), "review": dict(budgets["review"]), "security": dict(budgets["security"]),
                                "retries": dict(budgets["retries"])},
                    "state": dict(case.run.state(P.STORY_STATE).get("S1", {})),
                    "decisions": opa.decision_problems(opa.decision_table(events))}
        finally:
            case.doCleanups()

    FIXTURES = {
        "commit": ("test_ORCH_1_an_end_to_end_story_completes_through_the_real_path", lambda c: c.story(c.s1_plan(), "S1", c.s1_dev())),
        "conflict": ("test_ORCH_8_and_SCHEMA_3_a_merge_conflict_is_MERGE_CONFLICT_INTEGRATION_with_zero_developer_charge",
                     lambda c: c.story(c.s1_plan(), "S1", c.s1_dev(on_trunk={"app/calc.py": e2e.CALC + "\n\ndef add(a, b):\n    return b + a\n"}, repo=c.repo))),
        "outage-retry": ("test_ORCH_2_a_developer_outage_mid_story_is_a_typed_PROVIDER_failure_with_no_cross_charge",
                         lambda c: c.story(c.s1_plan(), "S1", e2e.Dev(outage=True))),
    }
    UNPOISONED = {}

    def _unpoison(self):
        sys.meta_path[:] = [f for f in sys.meta_path if f is not self.finder]   # an in-memory list, not a host resource

    def test_every_v1_family_is_poisoned_and_the_real_path_runs_unchanged(self):
        self.assertEqual(len(self.poisoned), sum(len(v) for v in opa.V1_SYMBOLS.values()))   # every named family, no exception
        v1_gate, v1_qual = sys.modules["aisef.control.gate"], sys.modules["aisef.control.qualification"]   # never an import here
        with self.assertRaises(PoisonedV1):
            v1_gate.evaluate(None)                                        # a function
        with self.assertRaises(PoisonedV1):
            v1_gate.StoryGate()                                           # a class
        with self.assertRaises(PoisonedV1):
            _ = v1_qual.Decision.PASS                                     # the Enum, by member access
        with self.assertRaises(PoisonedV1):
            v1_qual.Decision("PASS")                                      # the Enum, by value
        with self.assertRaises(PoisonedV1):
            importlib.import_module("aisef.control.nonexistent")          # a fresh import
        self.assertEqual(self.finder.attempts, ["aisef.control.nonexistent"])
        self.calls.clear()
        self.finder.attempts.clear()
        poisoned = {name: self._trace(*fx) for name, fx in self.FIXTURES.items()}
        self.assertEqual(self.finder.attempts, [])                       # no V2 code reached for V1 at import
        self.assertEqual(self.calls, [])                                  # no already-imported V1 family was called
        # the same fixtures without the poison, in the same process: byte-for-byte the same control chain
        self._unpoison()
        try:
            for name, fx in self.FIXTURES.items():
                self.assertEqual(poisoned[name], self._trace(*fx), name)
        finally:
            sys.meta_path.insert(0, self.finder)
        self.assertEqual(poisoned["commit"]["outcomes"], ["COMMIT"])
        self.assertEqual(poisoned["conflict"]["failures"], ["MERGE_CONFLICT"])
        self.assertEqual(poisoned["outage-retry"]["outcomes"], ["RETRY", "ROLLBACK"])
        self.assertTrue(all(t["decisions"] == [] for t in poisoned.values()))
        with self.assertRaises(PoisonedV1):                               # the poison is real: a family symbol, after the trace
            sys.modules["aisef.control.gate"].judge_only(None)
        with self.assertRaises(PoisonedV1):                               # and the finder still refuses a fresh V1 import
            importlib.import_module("aisef.harness.nonexistent")


# --------------------------------------------------------------------------------------------- R2

VACUOUS_TEST = ("import unittest\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n"
                "        add = getattr(calc, 'add', None)\n        if add:\n            add(1, 2)\n        self.assertTrue(True)\n")
IRRELEVANT_TEST = "import unittest\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_sub(self):\n        self.assertEqual(calc.sub(3, 1), 2)\n"


class DeveloperTestsNeverDecide(unittest.TestCase):
    """§5: developer tests PASS, FAIL, VACUOUS, IRRELEVANT, INCOMPLETE — the harness-owned probe result constant —
    leave the product proof identical; only the engineering-quality facts change."""

    VARIANTS = {
        "PASS": {"tests/test_s1.py": e2e.TEST_ADD},
        "FAIL": {"tests/test_s1.py": e2e.TEST_ADD_WRONG},
        "VACUOUS": {"tests/test_s1.py": VACUOUS_TEST},
        "IRRELEVANT": {"tests/test_s1.py": IRRELEVANT_TEST},
        "INCOMPLETE": {"tests/test_s1.py": e2e.TEST_ADD, "tests/test_other.py": "import zzz_no_such_dependency\n" + e2e.TEST_OTHER},
    }

    def test_five_developer_test_variants_one_product_proof(self):
        proofs, adequacy, measured = {}, {}, {}
        for name, files in self.VARIANTS.items():
            case = e2e.Orchestration("test_ORCH_14_a_change_of_engineering_adequacy_leaves_the_product_proof_unchanged")
            case.setUp()
            try:
                r = case.story(case.s1_plan(), "S1", e2e.Dev({"app/calc.py": e2e.CALC + e2e.ADD, **files}), tests_block=False)
                self.assertTrue(r.committed, name)
                events = list(case.run.events)
                proofs[name] = [{k: v for k, v in e.data.items() if k not in ("candidate", "story_id")} for e in events if e.type == "proof/verified"]
                a = next(e.data for e in events if e.type == "tests/adequacy")
                adequacy[name] = (a["outcome"], a["vacuity"], a["relevance"], a["execution"]["outcome"], a["regressions"]["selection"])
                measured[name] = (r.measured[case.s1.id].at_parent, r.measured[case.s1.id].at_merge)
                self.assertEqual([e.data["code"] for e in events if e.type == "failure/observed"], [], name)
            finally:
                case.doCleanups()
        self.assertEqual(adequacy["PASS"], ("ADEQUATE", "NON_VACUOUS", "RELEVANT", "PASSED", "STORY_TESTS_RAN"))
        self.assertEqual(adequacy["FAIL"][:1] + adequacy["FAIL"][3:4], ("INADEQUATE", "FAILED"))
        self.assertEqual(adequacy["VACUOUS"][:2], ("INADEQUATE", "VACUOUS"))
        self.assertEqual(adequacy["IRRELEVANT"][2], "IRRELEVANT")
        self.assertEqual(adequacy["INCOMPLETE"][0], "INCOMPLETE")
        self.assertEqual(adequacy["INCOMPLETE"][4], "STORY_TESTS_NOT_COLLECTABLE")
        first = proofs["PASS"]
        self.assertEqual([p["verdict"] for p in first], ["SATISFIED", "SATISFIED"])
        for name in self.VARIANTS:
            self.assertEqual(proofs[name], first, name)                          # spec, semantic_hash, agreement, verdict
            self.assertEqual(measured[name], (CS.INDETERMINATE, CS.SATISFIED), name)


# --------------------------------------------------------------------------------------------- R3

class NothingExecutesAtTheParent(unittest.TestCase):
    """§6: every developer test module at the parent explodes on import and leaves a mark; the V2 path never
    touches them, admission probes the subject with the harness's own probe, the story commits."""

    def test_exploding_parent_tests_are_never_imported_collected_or_executed(self):
        mark = pathlib.Path(tempfile.mkdtemp(prefix="parent-mark-")) / "exploded"
        bomb = f"import pathlib\npathlib.Path({str(mark)!r}).write_text('exploded', encoding='utf-8')\nraise RuntimeError('a developer test executed at the parent')\n"
        case = e2e.Orchestration("test_ORCH_1_an_end_to_end_story_completes_through_the_real_path")
        case.setUp()
        try:
            base = e2e.land(case.repo, {"tests/test_s1.py": bomb, "tests/test_other.py": bomb, "tests/conftest.py": bomb}, "exploding parent tests")
            dev = e2e.Dev({"app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD, "tests/test_other.py": e2e.TEST_OTHER,
                           "tests/conftest.py": ""})
            r = case.story(e2e.plan_of(base, e2e.obligation("C1", case.s1.id, "S1", ObligationRole.INTRODUCE)), "S1", dev)
            self.assertTrue(r.committed, case.failures("S1"))
            self.assertFalse(mark.exists(), "a parent-side developer test ran")
            parent_probes = [e for e in case.run.events if e.type == "probe/evaluated" and e.data["record"]["revision"] == base]
            self.assertEqual(len(parent_probes), 1)                                   # admission probed the subject at the parent
            self.assertEqual(parent_probes[0].data["record"]["result"]["behavior_verdict"], "INDETERMINATE")   # add absent at the parent
            adequacy = next(e.data for e in case.run.events if e.type == "tests/adequacy")
            self.assertEqual(adequacy["outcome"], "ADEQUATE")                          # the candidate's tests ran, at the candidate
        finally:
            case.doCleanups()
        self.assertFalse(mark.exists())


# --------------------------------------------------------------------------------------------- R4

class OnlyExplicitReferencesSelectEvidence(unittest.TestCase):
    """§7: two probe records for one criterion, the newer one wrong; the proof cites the older correct one by seq and
    that is what control reads — with the timestamps reversed, the same."""

    def journal(self, clock_values):
        d = tempfile.TemporaryDirectory(prefix="r4-")
        self.addCleanup(d.cleanup)
        clock = iter(clock_values)
        run = closed_after(self, RunScope(pathlib.Path(d.name) / "run", "run-r4", spec=RUN_SPEC, clock=lambda: next(clock)))
        run.begin()
        run.append(T.PLAN_FROZEN, {"plan_id": "PLAN-1", "plan_hash": "b" * 64, "roles": {"C1": "INTRODUCE"}})
        run.append(T.STORY_BEGIN, {"story_id": "S1", "parent": "a" * 40})
        run.append(T.STORY_ADMITTED, {"story_id": "S1", "parent": "a" * 40, "admitted": True, "developer_call_permitted": True,
                                      "dispositions": {"C1": "READY"}})
        right = sealed_record(rev="c" * 40)                                # SATISFIED
        wrong = sealed_record(verdict=__import__("aisef2.arch.enums", fromlist=["BehaviorVerdict"]).BehaviorVerdict.REFUTED, rev="c" * 40)
        a = run.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": right}).seq
        b = run.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": right}).seq
        run.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": wrong})     # newer, wrong
        run.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": wrong})
        payload = f3.verified_payload(story_id="S1", criterion_id="C1", spec_id="PPS-C1", semantic_hash="c" * 64,
                                      candidate="c" * 40, implementer=right, verifier=right)
        proof = run.append(T.PROOF_VERIFIED, payload, source_seqs=(a, b))
        row = run.append(T.GATE_CHECK, {"gate": "story", "check": "S1:proof:C1", "passed": True, "detail": "verified"})
        decision = run.append(T.GATE_DECISION, {"gate": "story", "passed": True, "projections": ["story_state", "budgets", "failure_owner", "retry_target"]},
                              source_seqs=(row.seq,))
        return run, proof, decision, (a, b)

    def test_the_cited_record_decides_whatever_the_timestamps_say(self):
        forward, f_proof, f_decision, (a, b) = self.journal(range(1, 100))
        backward, b_proof, b_decision, _ = self.journal(range(100, 1, -1))          # every later event carries an EARLIER time
        for run, proof, decision in ((forward, f_proof, f_decision), (backward, b_proof, b_decision)):
            read = f3.verified_proof(proof, run.events[:proof.seq])
            self.assertEqual((read["verdict"], read["implementer_result"]["behavior_verdict"]), ("SATISFIED", "SATISFIED"))
            self.assertEqual(tuple(proof.source_seqs), (a, b))                          # the explicit reference
            self.assertEqual([e.seq for e in run.events if e.type == "probe/evaluated"][-2:], [a + 2, a + 3])   # the newer wrong pair, uncited
            self.assertEqual(tuple(decision.source_seqs), (proof.seq + 1,))
            table = opa.decision_table(list(run.events))
            self.assertEqual(next(t["facts"] for t in table if t["decision"] == "proof/verified"), [a, b])
        f_times = [e.time for e in forward.events]
        b_times = [e.time for e in backward.events]
        self.assertEqual(sorted(f_times), f_times)
        self.assertEqual(sorted(b_times, reverse=True), b_times)
        for p in P:
            self.assertEqual(forward.state(p), backward.state(p), p)                       # no projection reads time
        with self.assertRaisesRegex(JournalError, "the verdict is 'REFUTED' by the two records"):   # citing the wrong pair cannot claim SATISFIED
            forward.append(T.PROOF_VERIFIED, dict(f_proof.data, criterion_id="C1"), source_seqs=(a + 2, a + 3))


# --------------------------------------------------------------------------------------------- R5

class RetryStateIsTheJournal(unittest.TestCase):
    """§8: a non-authoritative counter corrupted changes nothing; the journal's budget state corrupted changes the
    retry decision exactly as the projection says."""

    def test_a_reporting_counter_is_irrelevant_and_the_journal_decides(self):
        case = e2e.Orchestration("test_ORCH_2_a_developer_outage_mid_story_is_a_typed_PROVIDER_failure_with_no_cross_charge")
        case.setUp()
        try:
            original = sr._Held.__call__

            def bogus(self, process_range):                     # the range-naming counter, corrupted: reporting only
                name = f"{process_range.name} [{self.stage} 999]"
                self._held.append(self.scope.acquire(sr.Ranged(process_range, name)))
            with mock.patch.object(sr._Held, "__call__", bogus):
                r = case.story(case.s1_plan(), "S1", e2e.Dev(outage=True))
            self.assertIsNot(sr._Held.__call__, bogus)
            self.assertIs(sr._Held.__call__, original)
            self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "ROLLBACK"])
            events = list(case.run.events)
            failure = next(e for e in events if e.type == "failure/observed")
            retry = next(e for e in events if e.type == "story/retry")
            prefix = events[:retry.seq]
            self.assertEqual((budget.charge(prefix, "S1", e2e.LIMITS).retry, budget.charge(prefix, "S1", e2e.LIMITS).failure_seq), (True, failure.seq))
            # the journal's budget state corrupted: a retry already charged -> no retry; no approved count -> no retry;
            # the failure gone -> nothing to retry
            charged = prefix + [Event(seq=len(prefix), type="story/retry", data={"story_id": "S1"}, time=0.0, source_seqs=(failure.seq,))]
            second = charged + [Event(seq=len(charged), type="failure/observed", data=dict(failure.data), time=0.0, source_seqs=())]
            self.assertFalse(budget.charge(second, "S1", e2e.LIMITS).retry)
            self.assertEqual(budget.charge(second, "S1", e2e.LIMITS).spent, 1)
            self.assertFalse(budget.charge(prefix, "S1", {**e2e.LIMITS, budget.Owner.PROVIDER: None}).retry)
            self.assertFalse(budget.charge([e for e in prefix if e.seq < failure.seq], "S1", e2e.LIMITS).retry)
            self.assertEqual(budget.charge([e for e in prefix if e.seq < failure.seq], "S1", e2e.LIMITS).reason, "S1 has no failure to retry")
            # the run's own decision came from that projection and nothing else
            self.assertEqual(case.run.state(P.BUDGETS)["retries"], {"S1": {"PROVIDER": 1}})
            self.assertEqual(tuple(retry.source_seqs), (failure.seq,))
        finally:
            case.doCleanups()


# --------------------------------------------------------------------------------------------- R6

class EveryDecisionIsJournalBacked(unittest.TestCase):
    """§9: the decision -> source-seq table of a real story, every decision resting on journal facts before it."""

    def test_the_table_of_a_committed_and_a_rolled_back_story(self):
        for name, fn, expect in (
                ("commit", lambda c: c.story(c.s1_plan(), "S1", c.s1_dev()), ["COMMIT"]),
                ("rollback", lambda c: c.story(c.s1_plan(), "S1", e2e.Dev(outage=True), limits={**e2e.LIMITS, budget.Owner.PROVIDER: 0}), ["ROLLBACK"])):
            case = e2e.Orchestration("test_ORCH_1_an_end_to_end_story_completes_through_the_real_path")
            case.setUp()
            try:
                r = fn(case)
                self.assertEqual([a.outcome for a in r.attempts], expect, name)
                events = list(case.run.events)
                table = opa.decision_table(events)
                self.assertEqual(opa.decision_problems(table), [], name)
                by = {}
                for t in table:
                    by.setdefault(t["decision"], []).append(t)
                for row in by["gate/check"]:
                    self.assertEqual(len(row["facts"]), 1, row)                              # one typed evidence event per row
                    fact = events[row["facts"][0]]
                    stage = row["check"].split(":")[1]
                    self.assertIn(fact.type, opa.ROW_EVIDENCE[stage], row)
                decision = by["gate/decision"][0]
                self.assertEqual(sorted(decision["facts"]), sorted(t["seq"] for t in by["gate/check"]))
                self.assertEqual(events[decision["seq"]].data["passed"], name == "commit")
                if name == "commit":
                    self.assertEqual(by["story/commit"][0]["facts"], [decision["seq"]])
                    self.assertEqual(by["story/end"][0]["facts"], [by["story/commit"][0]["seq"]])
                else:
                    self.assertEqual(by["failure/observed"][0]["facts"], [decision["seq"]])
                    self.assertEqual(by["story/rollback"][0]["facts"], [by["failure/observed"][0]["seq"]])
                self.assertEqual(by["story/admitted"][0]["facts"], [e.seq for e in events if e.type == "probe/evaluated" and e.seq < by["story/admitted"][0]["seq"]])
                for p in by.get("proof/verified", []):
                    self.assertEqual(len(p["facts"]), 2)
                for p in by.get("provider/result", []):
                    self.assertEqual(events[p["facts"][0]].type, "provider/request")
            finally:
                case.doCleanups()


if __name__ == "__main__":
    unittest.main()
