"""C2-ORCHESTRATION-CONFORMANCE-REPAIR (owner ruling 2026-09-30, "ORCHESTRATION CONFORMANCE REPAIR AUTHORIZED"): one
ProductProof evaluation per PlanObligation, by the probe identity its ProductProofSpec carries — never one probe per
story, never a representative probe, never one verdict for several specs, no result shared between obligations.

Every story here runs the one authoritative path (`story_runner.run_story`) on a small real git repository with the
real Cycle-2 probes of `aisef2.probe.catalog` (python_callable_v2, file_artifact, cli_invocation, process_effect), the
harness wiring the whole catalogue keyed by probe id; typed doubles only where the path meets a capability (the
developer, the reviewer, the scanner — test_p6_orchestration's). The party cases use test_p6_stages' fakes where no real
probe can produce the state. The LedgerLock stories (case 14) and the record (case 15) need validation/qualification,
which the mutation runner's tree copy does not hold: there they are skipped; the suite runs them.
"""

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.v2.test_p6_orchestration as e2e  # noqa: E402
import tests.v2.test_p6_stages as st  # noqa: E402
from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict as V, ContractSatisfaction as CS, ControlProjection as P, EventType as T, Enforcement,
    MeasurementPoint as M, ObligationRole as R, Owner, Polarity, SubjectAbsence, SubjectKind,
)
from aisef2.control.owner import FailureCode as F, classify  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.journal import format3 as f3  # noqa: E402
from aisef2.orchestrate import proof as pf, story_runner as sr  # noqa: E402
from aisef2.orchestrate.quality import TestsPolicy  # noqa: E402
from aisef2.orchestrate.workspace import GitMerger, GitWorkspace, git  # noqa: E402
from aisef2.plan.drift import budget_problems  # noqa: E402
from aisef2.plan.story_admission import ordering_problems  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, bound_result, run_probe  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject, plain  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from aisef2.quality import test_execution as te  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from tests.v2.p4.test_run_scope import spec as RUN_SPEC  # noqa: E402
from tests.v2.p4.world import closed_after  # noqa: E402

ENV = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)
#: the harness wiring: every registered probe by id (active or superseded), each factory the catalog's own constructor
PROBES = {e.probe_id: (lambda on_range, scratch, f=e.factory: f(on_range=on_range, scratch=scratch)) for e in catalog.CATALOG}
REFS = {kind: ProbeRef(e.probe_id, e.probe_digest) for kind, e in catalog.active().items()}
KIND = {e.probe_id: e.subject_kind.value for e in catalog.CATALOG}
FILE = catalog.active()[SubjectKind.FILE_ARTIFACT]

# ------------------------------------------------------------------------------------------- the product

MAIN = ("import sys\n\nfrom app import calc\n\n\ndef main(argv):\n    op = getattr(calc, argv[0], None) if argv else None\n"
        "    if op is None:\n        return 2\n    sys.stdout.write(str(op(*map(int, argv[1:]))))\n    return 0\n\n\n"
        "sys.exit(main(sys.argv[1:]))\n")
TALLY = "class Tally:\n    def __init__(self):\n        self.n = 0\n\n    def total(self):\n        return self.n\n"
TALLY_ADD = TALLY + "\n    def add(self, k):\n        self.n += k\n        return self.n\n"
MUL = "\n\ndef mul(a, b):\n    return a * b\n"
TEST_MUL = ("import unittest\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_mul(self):\n"
            "        self.assertEqual(calc.mul(2, 3), 6)\n")
BASE_FILES = {"app/__main__.py": MAIN, "app/tally.py": TALLY}   # beside test_p6_orchestration's app/calc.py (`sub`)
IMPLEMENTED = {"app/calc.py": e2e.CALC + e2e.ADD, "app/tally.py": TALLY_ADD, "tests/test_s1.py": e2e.TEST_ADD}
WRONG_ADD = {**IMPLEMENTED, "app/calc.py": e2e.CALC + "\n\ndef add(a, b):\n    return a + b + 1\n"}


def contract(cid: str, kind: str, locator: str, stimulus: dict, observable: dict,
             absence: str = "REQUIRES_SUBJECT") -> ProductProofSpec:
    """A human-approved contract compiled to its ProductProofSpec against the catalog's active probe of its kind."""
    req = Requirement.create(id=f"R-{cid}", text=f"requirement {cid}", source="tests")
    c = BehaviorContract.create(id=f"BC-{cid}", requirement_ids=(req.id,), subject=Subject(SubjectKind(kind), locator),
                                stimulus=stimulus, observable={**observable, "within_s": 20}, polarity=Polarity.MUST_HOLD,
                                subject_absence=SubjectAbsence[absence], rationale=f"rationale {cid}")
    approval = ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())
    return compile_spec(c, requirements={req.id: req}, approvals=[approval], probes=REFS)


def _construct():
    return {"step": "construct", "args": [], "kwargs": {}}


def _call(method, *args):
    return {"step": "call", "method": method, "args": list(args), "kwargs": {}}


SPECS = {
    # python_callable_v2
    "P_ADD": contract("P_ADD", "python_callable", "app.calc:add", {"args": [1, 2]}, {"returns": 3}),
    "P_SUB": contract("P_SUB", "python_callable", "app.calc:sub", {"args": [3, 1]}, {"returns": 2}),
    # file_artifact
    "F_ADD": contract("F_ADD", "file_artifact", "path:app/calc.py", {"grep": "^def add", "suffixes": [".py"]}, {"matches": 1}),
    "F_CALC": contract("F_CALC", "file_artifact", "path:app/calc.py", {}, {"condition": "exists"}, "ABSENCE_IS_DECIDABLE"),
    "F_TALLY": contract("F_TALLY", "file_artifact", "path:app/tally.py", {"grep": "def total", "suffixes": [".py"]},
                        {"matches": 1}),
    "F_MUL": contract("F_MUL", "file_artifact", "path:app/calc.py", {"grep": "^def mul", "suffixes": [".py"]}, {"matches": 1}),
    # cli_invocation
    "K_ADD": contract("K_ADD", "cli_invocation", "app:__main__", {"argv": ["add", "1", "2"]}, {"exit_code": 0}),
    "K_SUB": contract("K_SUB", "cli_invocation", "app:__main__", {"argv": ["sub", "3", "1"]}, {"exit_code": 0, "stdout": "2"}),
    # process_effect
    "E_ADD": contract("E_ADD", "process_effect", "app.tally:Tally", {"scenario": [_construct(), _call("add", 2)]},
                      {"returns": 2}),
    "E_TOTAL": contract("E_TOTAL", "process_effect", "app.tally:Tally", {"scenario": [_construct(), _call("total")]},
                        {"returns": 0}),
}
#: a spec the real file_artifact probe refuses: its observable declares no bounded window (INVALID_SPEC, §9.2)
NO_WINDOW = ProductProofSpec.create(
    contract_id="BC-NO-WINDOW", probe_id=FILE.probe_id, probe_digest=FILE.probe_digest,
    probe_input={"subject": {"kind": "file_artifact", "locator": "path:app/calc.py"}, "stimulus": {},
                 "observable": {"condition": "exists"}, "subject_absence": SubjectAbsence.ABSENCE_IS_DECIDABLE.value},
    candidate_expectation=V.SATISFIED, compiler_id="c2-orch", compiler_digest="c" * 64)
BY_ID = {s.id: s for s in (*SPECS.values(), NO_WINDOW)}


def plan_of(base: str, *rows, pid: str = "PLAN-C2-ORCH"):
    """rows: (criterion id, spec name, story, role)."""
    return e2e.plan_of(base, *(e2e.obligation(cid, (NO_WINDOW if name == "NO_WINDOW" else SPECS[name]).id, story, role)
                               for cid, name, story, role in rows), pid=pid)


class Cleanups:
    """`addCleanup` for a caller that is not a TestCase (the reproducer's subprocess): run in reverse by `close`."""

    def __init__(self) -> None:
        self._fns: list = []

    def addCleanup(self, fn, *args) -> None:
        self._fns.append((fn, args))

    def close(self) -> None:
        for fn, args in reversed(self._fns):
            fn(*args)


class World:
    """A fresh fixture under `root`: the product repository at its base, the workspace and merge roots, the scan
    script, and a run writing journal format 3."""

    def __init__(self, holder, root: pathlib.Path, files: dict | None = None) -> None:
        root.mkdir(parents=True)
        self.repo, self.base = e2e.make_repo(root, {**BASE_FILES, **(files or {})})
        for d in ("ws", "merge", "run"):
            (root / d).mkdir()
        self.script = root / "scan.py"
        self.script.write_text(e2e.SCAN_SCRIPT, encoding="utf-8")
        self.ws, self.merger = GitWorkspace(self.repo, root / "ws"), GitMerger(self.repo, "main", root / "merge")
        clock = iter(float(n) for n in range(10 ** 6))
        self.run = closed_after(holder, RunScope(root / "run", "run-c2-orch", spec=RUN_SPEC, clock=lambda: next(clock)))
        self.run.begin()

    def story(self, plan, story_id: str, dev, *, probes=PROBES, env=ENV, limits=e2e.LIMITS, specs=BY_ID,
              tests=("tests/test_s1.py",), deps=("app", "tests")):
        inputs = sr.StoryInputs(specs, probes, env, te.DeveloperTests(story_id, tests),
                                te.DeveloperTests(story_id, ("tests/test_other.py",)),
                                te.Dependencies(frozenset(), frozenset(deps)), te.UNITTEST)
        adapters = sr.Adapters(dev, e2e.Rev(), e2e.Scan(str(self.script)), self.merger, self.ws)
        return sr.run_story(self.run, plan, story_id, inputs, adapters,
                            sr.Policy(limits, TestsPolicy(False), tool_timeout_s=60))

    def events(self, kind=None, story=None) -> list:
        return [e for e in self.run.events if (kind is None or e.type == kind)
                and (story is None or e.data.get("story_id") == story)]

    def failures(self, story: str) -> list:
        return [(e.data["code"], e.data["owner"], e.data["retryable"]) for e in self.events("failure/observed", story)]

    def details(self, story: str) -> list:
        return [e.data["detail"] for e in self.events("failure/observed", story)]

    def rows(self, story: str) -> list:
        return [(e.data["check"], e.data["passed"], e.data["detail"]) for e in self.events("gate/check")
                if e.data["check"].startswith(story + ":")]

    def admitted(self, story: str) -> dict:
        return dict(self.events("story/admitted", story)[-1].data)

    def records(self, story: str, criterion: str | None = None, revision: str | None = None) -> list:
        return [e for e in self.events("probe/evaluated", story) if (criterion is None or e.data["criterion_id"] == criterion)
                and (revision is None or e.data["record"]["revision"] == revision)]

    def developer_requests(self, story: str) -> list:
        return [e for e in self.events("provider/request", story) if e.data["budget_owner"] == Owner.DEVELOPER.value]


def verdict_of(record: dict) -> str | None:
    return record["result"].get("behavior_verdict")


def result_of(record: dict) -> dict:
    """A journaled record's result in plain form (an Unrunnable or InvalidSpec result is its detail; the disposition
    and the failure code carry which one it is)."""
    return plain(record["result"])


def reproduce_multi_kind(root: pathlib.Path) -> dict:
    """The defect reproducer's story (validation/qualification/c2_orchestration_repair.py runs it under the kernel of
    6311254 and under this one): two probe kinds in one story, both READY at the parent, the harness wiring exactly
    the story's two probes. Everything it observed, typed; an aborted run is interrupted so nothing survives it."""
    holder = Cleanups()
    try:
        w = World(holder, root)
        plan = plan_of(w.base, ("C-F", "F_ADD", "S1", R.INTRODUCE), ("C-P", "P_ADD", "S1", R.INTRODUCE))
        probes = {SPECS[n].probe_id: PROBES[SPECS[n].probe_id] for n in ("F_ADD", "P_ADD")}
        try:
            r = w.story(plan, "S1", e2e.Dev(IMPLEMENTED), probes=probes)
            out = {"raised": None, "attempts": [a.outcome for a in r.attempts], "committed": r.committed}
        except InvariantError as e:
            out = {"raised": f"{type(e).__name__}: {e}", "attempts": None, "committed": False}
            w.run.interrupt()
        out.update(
            probe_factories=sorted(probes),
            event_types=[e.type for e in w.run.events],
            dispositions=plain(w.admitted("S1")["dispositions"]),
            developer_requests=[list(e.data["criteria"]) for e in w.developer_requests("S1")],
            records=[{"criterion_id": e.data["criterion_id"], "probe_id": e.data["record"]["probe_id"],
                      "at": "parent" if e.data["record"]["revision"] == w.base else "later",
                      "verdict": verdict_of(e.data["record"])} for e in w.records("S1")],
            proofs=[{"criterion_id": e.data["criterion_id"], "agreement": e.data["agreement"], "verdict": e.data.get("verdict")}
                    for e in w.events("proof/verified", "S1")],
            failures=[list(f) for f in w.failures("S1")])
        return out
    finally:
        holder.close()


class Fixture(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-c2-orch-")
        self.addCleanup(self._d.cleanup)
        self.tmp = pathlib.Path(self._d.name)
        self._n = 0

    def world(self, files=None) -> World:
        self._n += 1
        return World(self, self.tmp / f"w{self._n}", files)

    def assertOwnInstrument(self, w: World, story: str, criterion: str, spec_name: str, revision: str, n: int):
        """`n` records of `criterion` at `revision`, each the ProductProofSpec's own: its spec id, semantic hash, probe
        id and digest — a record of another probe never answers it."""
        spec = SPECS[spec_name]
        got = w.records(story, criterion, revision)
        self.assertEqual(len(got), n, f"{criterion} at {revision[:7]}")
        for e in got:
            r = e.data["record"]
            self.assertEqual((r["spec_id"], r["semantic_hash"], r["probe_id"], r["probe_digest"]),
                             (spec.id, spec.semantic_hash, spec.probe_id, spec.probe_digest), criterion)
        return got


# ------------------------------------------------------------------------------------------- the path

class OneProofPerObligation(Fixture):
    def test_1_a_story_with_specs_of_two_probe_kinds_commits_each_proved_by_its_own_probe(self):
        w = self.world()
        dev = e2e.Dev(IMPLEMENTED)
        r = w.story(plan_of(w.base, ("C-F", "F_ADD", "S1", R.INTRODUCE), ("C-P", "P_ADD", "S1", R.INTRODUCE)), "S1", dev)
        self.assertEqual([a.outcome for a in r.attempts], ["COMMIT"], w.failures("S1"))
        self.assertEqual(w.admitted("S1")["dispositions"], {"C-F": "READY", "C-P": "READY"})
        self.assertEqual({KIND[SPECS[n].probe_id] for n in ("F_ADD", "P_ADD")}, {"file_artifact", "python_callable"})
        for cid, name in (("C-F", "F_ADD"), ("C-P", "P_ADD")):
            self.assertOwnInstrument(w, "S1", cid, name, w.base, 1)
            self.assertOwnInstrument(w, "S1", cid, name, dev.candidates[0], 2)
            self.assertOwnInstrument(w, "S1", cid, name, r.revision, 2)
        self.assertEqual([(e.data["criterion_id"], e.data["agreement"], e.data["verdict"]) for e in w.events("proof/verified", "S1")],
                         [("C-F", True, "SATISFIED"), ("C-P", True, "SATISFIED")] * 2)
        self.assertEqual([p.spec_id for p in r.attempts[0].proofs], [SPECS["F_ADD"].id, SPECS["P_ADD"].id] * 2)

    def test_4_all_PRE_SATISFIED_no_developer_request_the_candidate_is_the_parent_and_every_obligation_is_proved(self):
        w = self.world()
        rows = (("C-F0", "F_CALC", "S1", R.INTRODUCE), ("C-P0", "P_SUB", "S1", R.INTRODUCE),
                ("C-K0", "K_SUB", "S1", R.INTRODUCE), ("C-E0", "E_TOTAL", "S1", R.INTRODUCE))
        dev = e2e.Dev(outage=True)                       # a developer call would raise: none is made
        r = w.story(plan_of(w.base, *rows), "S1", dev)
        self.assertTrue(r.committed, w.failures("S1"))
        self.assertEqual((r.revision, dev.calls), (w.base, []))
        adm = w.admitted("S1")
        self.assertEqual((adm["dispositions"], adm["developer_call_permitted"]), ({c: "PRE_SATISFIED" for c, *_ in rows}, False))
        self.assertEqual(w.developer_requests("S1"), [])
        self.assertEqual([e.data["budget_owner"] for e in w.events("provider/request", "S1")], ["REVIEW"])
        self.assertEqual(w.run.state(P.BUDGETS)["developer"], {})
        self.assertEqual(sorted(e.data["criterion_id"] for e in w.events("story/plan-drift", "S1")), sorted(c for c, *_ in rows))
        self.assertEqual(len({KIND[SPECS[n].probe_id] for _, n, _, _ in rows}), 4)
        for cid, name, _, _ in rows:                     # parent, candidate x2 and post-merge x2 — all at the parent
            self.assertOwnInstrument(w, "S1", cid, name, w.base, 5)
            self.assertIn((f"S1:proof:{cid}", True, "verified"), w.rows("S1"))
        cand = [e for e in w.events("proof/verified", "S1")][:len(rows)]
        self.assertEqual([(e.data["criterion_id"], e.data["candidate"], e.data["verdict"]) for e in cand],
                         [(c, w.base, "SATISFIED") for c, *_ in rows])
        self.assertEqual({s: (m.at_parent, m.at_merge) for s, m in r.measured.items()},
                         {SPECS[n].id: (CS.SATISFIED, CS.SATISFIED) for _, n, _, _ in rows})

    def test_5_one_PRECONDITION_BROKEN_among_READY_blocks_the_story_before_any_developer_request(self):
        w = self.world()
        rows = (("C-F", "F_ADD", "S1", R.INTRODUCE), ("C-K", "K_ADD", "S1", R.PRESERVE), ("C-P", "P_ADD", "S1", R.INTRODUCE))
        r = w.story(plan_of(w.base, *rows), "S1", e2e.Dev(IMPLEMENTED))
        c = classify(F.PRECONDITION_BROKEN)
        self.assertEqual(w.admitted("S1")["dispositions"], {"C-F": "READY", "C-K": "PRECONDITION_BROKEN", "C-P": "READY"})
        self.assertEqual(w.failures("S1"), [("PRECONDITION_BROKEN", c.owner.value, c.budget is not None)])
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])
        self.assertEqual(w.rows("S1"), [("S1:admission", False, "C-K: PRECONDITION_BROKEN")])
        self.assertEqual(w.events("provider/request", "S1"), [])
        for cid, name, _, _ in rows:                     # every obligation measured at the parent, by its own probe
            self.assertOwnInstrument(w, "S1", cid, name, w.base, 1)
        self.assertEqual(verdict_of(w.records("S1", "C-K")[0].data["record"]), "REFUTED")
        self.assertEqual(w.merger.base(), w.base)

    def test_6_one_PROBE_UNRUNNABLE_among_READY_is_the_environment_s_and_charges_its_budget(self):
        w = self.world()
        rows = (("C-F", "F_ADD", "S1", R.INTRODUCE), ("C-P", "P_ADD", "S1", R.INTRODUCE), ("C-T", "F_TALLY", "S1", R.VERIFY))
        env = ExecutionEnv("/nonexistent/aisef2-python", 60, Enforcement.PARTIAL)   # no interpreter for a subject
        r = w.story(plan_of(w.base, *rows), "S1", e2e.Dev(IMPLEMENTED), env=env)
        self.assertEqual(w.admitted("S1")["dispositions"], {"C-F": "READY", "C-P": "PROBE_UNRUNNABLE", "C-T": "READY"})
        self.assertEqual(w.failures("S1"), [("PROBE_UNRUNNABLE", "ENVIRONMENT", True)] * 2)
        self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "ROLLBACK"])      # ENVIRONMENT limit 1
        self.assertEqual(w.run.state(P.BUDGETS)["retries"], {"S1": {"ENVIRONMENT": 1}})
        self.assertEqual(w.events("provider/request", "S1"), [])
        p = w.records("S1", "C-P")[0].data["record"]
        self.assertEqual((p["probe_id"], result_of(p)), (SPECS["P_ADD"].probe_id,
                                                          {"detail": "interpreter absent: /nonexistent/aisef2-python"}))
        for cid in ("C-F", "C-T"):                       # the file probe needs no interpreter: it measured
            self.assertEqual(verdict_of(w.records("S1", cid)[0].data["record"]), "REFUTED" if cid == "C-F" else "SATISFIED")

    def test_7_one_INVALID_SPEC_among_READY_is_PROBE_INVALID_from_the_real_probe_or_from_an_unwired_one(self):
        w = self.world()
        r = w.story(plan_of(w.base, ("C-F", "F_ADD", "S1", R.INTRODUCE), ("C-X", "NO_WINDOW", "S1", R.INTRODUCE),
                            ("C-P", "P_ADD", "S1", R.INTRODUCE)), "S1", e2e.Dev(IMPLEMENTED))
        c = classify(F.PROBE_INVALID_SPEC)
        self.assertEqual(w.admitted("S1")["dispositions"], {"C-F": "READY", "C-X": "PROBE_INVALID", "C-P": "READY"})
        self.assertEqual(w.failures("S1"), [("PROBE_INVALID_SPEC", c.owner.value, c.budget is not None)])
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])
        self.assertEqual(w.events("provider/request", "S1"), [])
        x = w.records("S1", "C-X")[0].data["record"]
        self.assertEqual((x["probe_id"], x["probe_digest"], x["enforcement"], sorted(result_of(x))),
                         (FILE.probe_id, FILE.probe_digest, "FULL", ["detail"]))           # the real probe refused it
        w2 = self.world()                                # the harness wires no factory for one spec's probe
        without = {k: v for k, v in PROBES.items() if k != SPECS["P_ADD"].probe_id}
        r2 = w2.story(plan_of(w2.base, ("C-F", "F_ADD", "S1", R.INTRODUCE), ("C-P", "P_ADD", "S1", R.INTRODUCE)), "S1",
                      e2e.Dev(IMPLEMENTED), probes=without)
        self.assertEqual(w2.admitted("S1")["dispositions"], {"C-F": "READY", "C-P": "PROBE_INVALID"})
        self.assertEqual(([a.outcome for a in r2.attempts], w2.events("provider/request", "S1")), (["ROLLBACK"], []))
        p = w2.records("S1", "C-P")[0].data["record"]
        self.assertEqual((p["probe_id"], p["enforcement"], result_of(p)),
                         (SPECS["P_ADD"].probe_id, "UNAVAILABLE",
                          {"detail": f"probe {SPECS['P_ADD'].probe_id} is not in the harness catalogue"}))

    def test_10_one_failing_candidate_spec_is_not_masked_by_the_others_passing(self):
        w = self.world()
        dev = e2e.Dev(WRONG_ADD)                         # `add` defined and runnable from the CLI, but wrong
        rows = (("C-F", "F_ADD", "S1", R.INTRODUCE), ("C-K", "K_ADD", "S1", R.INTRODUCE), ("C-P", "P_ADD", "S1", R.INTRODUCE))
        r = w.story(plan_of(w.base, *rows), "S1", dev, limits={**e2e.LIMITS, Owner.DEVELOPER: 0})
        self.assertFalse(r.committed)
        self.assertEqual(w.failures("S1"), [("CONTRACT_UNSATISFIED", "DEVELOPER", True)])
        self.assertEqual(w.details("S1"), ["proof of C-P: CONTRACT_UNSATISFIED"])
        self.assertEqual([x for x in w.rows("S1") if ":proof:" in x[0]],
                         [("S1:proof:C-F", True, "verified"), ("S1:proof:C-K", True, "verified"),
                          ("S1:proof:C-P", False, "CONTRACT_UNSATISFIED")])
        cand = dev.candidates[0]
        verdicts = {cid: [verdict_of(e.data["record"]) for e in self.assertOwnInstrument(w, "S1", cid, name, cand, 2)]
                    for cid, name, _, _ in rows}
        self.assertEqual(verdicts, {"C-F": ["SATISFIED"] * 2, "C-K": ["SATISFIED"] * 2, "C-P": ["REFUTED"] * 2})
        self.assertEqual((w.merger.base(), [x for x in w.rows("S1") if x[0] == "S1:merge"]), (w.base, []))

    def test_12_a_permuted_obligation_order_gives_the_same_semantic_outcome(self):
        rows = (("C-F", "F_ADD", "S1", R.INTRODUCE), ("C-E", "E_ADD", "S1", R.INTRODUCE), ("C-F0", "F_CALC", "S1", R.INTRODUCE))
        seen = []
        for order in (rows, rows[::-1]):
            w = self.world()
            dev = e2e.Dev(IMPLEMENTED)
            r = w.story(plan_of(w.base, *order), "S1", dev)
            point = {w.base: "PARENT", dev.candidates[0]: "CANDIDATE", r.revision: "POST_MERGE"}
            adm = w.admitted("S1")
            seen.append({
                "attempts": [a.outcome for a in r.attempts], "failures": w.failures("S1"),
                "dispositions": dict(adm["dispositions"]), "permitted": adm["developer_call_permitted"],
                "developer_criteria": sorted(c for e in w.developer_requests("S1") for c in e.data["criteria"]),
                "records": sorted((e.data["criterion_id"], point[e.data["record"]["revision"]], e.data["record"]["spec_id"],
                                   e.data["record"]["probe_id"], json.dumps(result_of(e.data["record"]), sort_keys=True))
                                  for e in w.records("S1")),
                "proofs": sorted((e.data["criterion_id"], point[e.data["candidate"]], e.data["spec_id"], e.data["semantic_hash"],
                                  e.data["agreement"], e.data.get("verdict")) for e in w.events("proof/verified", "S1")),
                "measured": {s: (m.at_parent, m.at_merge) for s, m in r.measured.items()},
                "tree": git(w.repo, "rev-parse", f"{r.revision}^{{tree}}").stdout.strip()})
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(seen[0]["attempts"], ["COMMIT"])
        self.assertEqual(seen[0]["dispositions"], {"C-F": "READY", "C-E": "READY", "C-F0": "PRE_SATISFIED"})


class MixedStory(unittest.TestCase):
    """One story over three probe kinds: READY and PRE_SATISFIED obligations, two specs of one kind, and one spec
    under two obligations — run once through the path; every case reads its journal."""
    ROWS = (("C-F", "F_ADD", "S1", R.INTRODUCE), ("C-P", "P_ADD", "S1", R.INTRODUCE), ("C-K", "K_ADD", "S1", R.INTRODUCE),
            ("C-F0", "F_CALC", "S1", R.INTRODUCE), ("C-FV", "F_ADD", "S1", R.VERIFY))

    @classmethod
    def setUpClass(cls):
        d = tempfile.TemporaryDirectory(prefix="aisef2-c2-mixed-")
        cls.addClassCleanup(d.cleanup)
        holder = Cleanups()
        cls.addClassCleanup(holder.close)
        cls.w = World(holder, pathlib.Path(d.name) / "w")
        cls.dev = e2e.Dev(IMPLEMENTED)
        cls.r = cls.w.story(plan_of(cls.w.base, *cls.ROWS), "S1", cls.dev)
        cls.cand = cls.dev.candidates[0] if cls.dev.candidates else None

    def test_2_one_story_with_specs_of_three_probe_kinds_commits(self):
        self.assertEqual([a.outcome for a in self.r.attempts], ["COMMIT"], self.w.failures("S1"))
        self.assertEqual({KIND[SPECS[n].probe_id] for _, n, _, _ in self.ROWS}, {"file_artifact", "python_callable", "cli_invocation"})
        self.assertEqual(self.w.merger.base(), self.r.revision)
        self.assertEqual([(e.data["criterion_id"], e.data["agreement"], e.data.get("verdict")) for e in self.w.events("proof/verified", "S1")],
                         [(c, True, "SATISFIED") for c, *_ in self.ROWS] * 2)

    def test_3_mixed_PRE_SATISFIED_and_READY_the_developer_gets_the_READY_ones_and_all_are_proved(self):
        adm = self.w.admitted("S1")
        self.assertEqual(adm["dispositions"], {"C-F": "READY", "C-P": "READY", "C-K": "READY", "C-F0": "PRE_SATISFIED", "C-FV": "READY"})
        self.assertIs(adm["developer_call_permitted"], True)
        self.assertEqual([list(e.data["criteria"]) for e in self.w.developer_requests("S1")], [["C-F", "C-P", "C-K", "C-FV"]])
        self.assertEqual(self.dev.calls[0][1], ("C-F", "C-P", "C-K", "C-FV"))
        self.assertEqual([e.data["criterion_id"] for e in self.w.events("story/plan-drift", "S1")], ["C-F0"])
        self.assertEqual([x[0] for x in self.w.rows("S1") if ":proof:" in x[0]], [f"S1:proof:{c}" for c, *_ in self.ROWS])
        self.assertEqual(self.r.measured[SPECS["F_CALC"].id].at_parent, CS.SATISFIED)
        self.assertEqual(self.r.measured[SPECS["P_ADD"].id].at_parent, CS.INDETERMINATE)

    def test_8_each_obligation_has_its_own_candidate_records_binding_its_spec_probe_and_candidate(self):
        level = {e.probe_id: e.factory().enforcement().value for e in catalog.CATALOG}
        for cid, name, _, _ in self.ROWS:
            spec = SPECS[name]
            got = [e.data["record"] for e in self.w.records("S1", cid, self.cand)]
            self.assertEqual(len(got), 2, cid)
            for rec in got:
                self.assertEqual((rec["spec_id"], rec["semantic_hash"], rec["probe_id"], rec["probe_digest"], rec["revision"],
                                  rec["enforcement"], verdict_of(rec)),
                                 (spec.id, spec.semantic_hash, spec.probe_id, spec.probe_digest, self.cand,
                                  level[spec.probe_id], "SATISFIED"), cid)

    def test_9_each_obligation_has_its_own_verified_proof_citing_its_two_records(self):
        proofs = self.r.attempts[0].proofs
        self.assertEqual([(p.criterion_id, p.spec_id) for p in proofs], [(c, SPECS[n].id) for c, n, _, _ in self.ROWS] * 2)
        for p in proofs:
            v = self.w.run.events[p.verified_seq]
            a, b = self.w.run.events[p.implementer_seq], self.w.run.events[p.verifier_seq]
            self.assertEqual((v.type, tuple(v.source_seqs)), ("proof/verified", (a.seq, b.seq)))
            self.assertEqual({a.data["criterion_id"], b.data["criterion_id"], v.data["criterion_id"]}, {p.criterion_id})
            spec = BY_ID[p.spec_id]
            self.assertEqual((v.data["spec_id"], v.data["semantic_hash"], v.data["agreement"], v.data["verdict"]),
                             (spec.id, spec.semantic_hash, True, "SATISFIED"))
            self.assertEqual({a.data["record"]["revision"], b.data["record"]["revision"]}, {v.data["candidate"]})
            vp = f3.verified_proof(v, self.w.run.events[:v.seq])
            self.assertEqual((vp["spec_id"], vp["candidate_sha"], vp["verdict"]), (spec.id, v.data["candidate"], "SATISFIED"))
            self.assertEqual((p.agreement, p.satisfaction, p.failure), (True, CS.SATISFIED, None))
        self.assertEqual({self.w.run.events[p.verified_seq].data["candidate"] for p in proofs}, {self.cand, self.r.revision})

    def test_11_no_evaluation_is_shared_two_specs_of_one_kind_and_one_spec_under_two_obligations_each_run(self):
        for cid, *_ in self.ROWS:                        # parent 1, candidate 2, post-merge 2: nothing reused
            self.assertEqual(len(self.w.records("S1", cid)), 5, cid)
        same = [e.seq for c in ("C-F", "C-FV") for e in self.w.records("S1", c)]
        self.assertEqual(len(set(same)), 10)             # one spec, two obligations: ten records of its own
        self.assertEqual({e.data["record"]["spec_id"] for c in ("C-F", "C-FV") for e in self.w.records("S1", c)}, {SPECS["F_ADD"].id})
        kinds = {e.data["record"]["spec_id"] for c in ("C-F", "C-F0") for e in self.w.records("S1", c)}
        self.assertEqual(kinds, {SPECS["F_ADD"].id, SPECS["F_CALC"].id})   # one kind, two specs, two answers
        ranges = [e.data["resource"] for e in self.w.events("story/resource-acquired", "S1") if e.data["resource"].startswith("probe ")]
        for cid, name in (("C-P", "P_ADD"), ("C-K", "K_ADD")):   # every subprocess evaluation its own process range
            for point in ("CANDIDATE", "POST_MERGE"):
                for party in ("implementer", "verifier"):
                    self.assertIn(f"probe {SPECS[name].id} [{cid}/{point} {party}]", ranges)
        self.assertEqual(len(ranges), 2 + 8)             # admission 2 (P, K); 2 x 2 x 2 at the candidate and after merge

    def test_13_the_developer_request_follows_the_complete_admission_that_permits_it(self):
        mine = self.w.events(story="S1")
        types = [e.type for e in mine]
        admitted = types.index("story/admitted")
        self.assertEqual(types[:admitted].count("probe/evaluated"), len(self.ROWS))   # every obligation measured first
        self.assertLess(admitted, types.index("provider/request"))
        typed = [(T(e.type), dict(e.data)) for e in self.w.run.events   # the developer's budget: its requests only
                 if e.type != "provider/request" or e.data["budget_owner"] == Owner.DEVELOPER.value]
        self.assertEqual((ordering_problems(typed), budget_problems(typed)), ([], []))
        self.assertEqual([e.data["record"]["revision"] for e in mine[:admitted] if e.type == "probe/evaluated"],
                         [self.w.base] * len(self.ROWS))


class ReproofOfAnotherKind(unittest.TestCase):
    """After a merge, a prior committed story's PRESERVE obligation (a cli_invocation spec) is re-proved at the merged
    revision with its own probe, although every spec of the current story is a file_artifact spec."""

    @classmethod
    def setUpClass(cls):
        d = tempfile.TemporaryDirectory(prefix="aisef2-c2-reprove-")
        cls.addClassCleanup(d.cleanup)
        holder = Cleanups()
        cls.addClassCleanup(holder.close)
        w = cls.w = World(holder, pathlib.Path(d.name) / "w")
        cls.plan = plan_of(w.base, ("C-K0", "K_SUB", "S0", R.PRESERVE), ("C-F", "F_ADD", "S0", R.INTRODUCE),
                           *((f"C-M{n}", "F_MUL", f"S{n}", R.INTRODUCE) for n in (2, 3, 4)))
        cls.r0 = w.story(cls.plan, "S0", e2e.Dev(IMPLEMENTED))
        cls.tip = w.merger.base()
        mul = {"app/calc.py": e2e.CALC + e2e.ADD + MUL, "tests/test_s2.py": TEST_MUL}
        broken = {**mul, "app/calc.py": "def sub(a, b):\n    return a + b\n" + e2e.ADD + MUL}   # breaks S0's `sub`
        file_only = {k: v for k, v in PROBES.items() if KIND[k] == "file_artifact"}
        cls.r2 = w.story(cls.plan, "S2", e2e.Dev(mul), probes=file_only, tests=("tests/test_s2.py",))
        cls.after2 = w.merger.base()
        cls.r3 = w.story(cls.plan, "S3", e2e.Dev(broken), tests=("tests/test_s2.py",))
        cls.after3 = w.merger.base()
        cls.r4 = w.story(cls.plan, "S4", e2e.Dev(mul), tests=("tests/test_s2.py",))

    def post_merge(self, story):
        return [(c, p) for c, p, _ in self.w.rows(story) if ":post-merge:" in c]

    def test_the_prior_PRESERVE_spec_of_another_kind_is_re_proved_by_its_own_probe(self):
        self.assertTrue(self.r0.committed, self.w.failures("S0"))
        self.assertTrue(self.r4.committed, self.w.failures("S4"))
        self.assertEqual({KIND[BY_ID[o.product_proof_spec_id].probe_id] for o in self.plan.obligations if o.story_id == "S4"},
                         {"file_artifact"})
        self.assertEqual(self.post_merge("S4"), [("S4:post-merge:C-M4", True), ("S4:post-merge:C-K0", True)])
        k = [e.data["record"] for e in self.w.records("S4", "C-K0")]
        self.assertEqual(len(k), 2)
        self.assertEqual({(x["probe_id"], x["probe_digest"], x["revision"], verdict_of(x)) for x in k},
                         {(SPECS["K_SUB"].probe_id, SPECS["K_SUB"].probe_digest, self.r4.revision, "SATISFIED")})

    def test_a_regression_of_the_prior_spec_of_another_kind_is_POST_MERGE_REGRESSION_and_rolled_back(self):
        self.assertEqual(self.w.failures("S3"), [("POST_MERGE_REGRESSION", "INTEGRATION", False)])
        self.assertEqual(self.w.details("S3"), ["post-merge C-K0: POST_MERGE_REGRESSION"])
        self.assertEqual(self.post_merge("S3"), [("S3:post-merge:C-M3", True), ("S3:post-merge:C-K0", False)])
        self.assertEqual({(e.data["record"]["probe_id"], verdict_of(e.data["record"])) for e in self.w.records("S3", "C-K0")},
                         {(SPECS["K_SUB"].probe_id, "REFUTED")})
        self.assertEqual(self.after3, self.tip)

    def test_a_prior_spec_whose_probe_the_harness_did_not_wire_is_a_typed_INVALID_SPEC_never_a_crash(self):
        self.assertEqual([a.outcome for a in self.r2.attempts], ["ROLLBACK"])
        self.assertEqual(self.w.failures("S2"), [("PROBE_INVALID_SPEC", "INTEGRATION", False)])
        self.assertEqual(self.w.details("S2"), ["post-merge C-K0: PROBE_INVALID_SPEC"])
        k = [e.data["record"] for e in self.w.records("S2", "C-K0")]
        self.assertEqual([(x["probe_id"], x["probe_digest"], x["enforcement"], result_of(x)) for x in k],
                         [(SPECS["K_SUB"].probe_id, SPECS["K_SUB"].probe_digest, "UNAVAILABLE",
                           {"detail": f"probe {SPECS['K_SUB'].probe_id} is not in the harness catalogue"})] * 2)
        v = [e for e in self.w.events("proof/verified", "S2") if e.data["criterion_id"] == "C-K0"]
        self.assertEqual([(e.data["agreement"], "verdict" in e.data) for e in v], [(True, False)])
        self.assertEqual(self.after2, self.tip)          # the merge was reverted
        self.assertEqual(self.w.run.state(P.STORY_STATE)["S2"]["state"], "ENDED")


# ------------------------------------------------------------------------------------------- the parties

class Parties(st.Journal):
    def setUp(self):
        super().setUp()
        self.scope = self.activate()

    def spec(self, probe_id: str, digest: str) -> ProductProofSpec:
        return ProductProofSpec.create(contract_id="BC-X", probe_id=probe_id, probe_digest=digest,
                                       probe_input=dict(self.s1.probe_input), candidate_expectation=V.SATISFIED,
                                       compiler_id="c2-orch", compiler_digest="c" * 64)

    def test_the_runner_resolves_the_factory_of_the_spec_s_own_probe_identity_or_none(self):
        made = []

        class A(st.FakeProbe):
            id, digest = "probe.a", "a" * 64

        class B(st.FakeProbe):
            id, digest = "probe.b", "b" * 64

        def factory(cls):
            return lambda on_range, scratch: made.append((cls.id, on_range, scratch)) or cls({}, on_range)
        inputs = sr.StoryInputs(self.specs, {"probe.a": factory(A), "probe.b": factory(B)}, st.ENV,
                                te.DeveloperTests("S1", ("tests/test_s1.py",)), te.DeveloperTests("S1", ("tests/test_other.py",)),
                                te.Dependencies(frozenset(), frozenset()), te.UNITTEST)
        got = sr._probe(inputs, "range", "scratch", self.spec("probe.b", "b" * 64))
        self.assertIsInstance(got, B)
        self.assertEqual(made, [("probe.b", "range", "scratch")])
        self.assertIsInstance(sr._probe(inputs, "r2", "s2", self.spec("probe.a", "a" * 64)), A)
        self.assertEqual(made[-1], ("probe.a", "r2", "s2"))
        self.assertIsNone(sr._probe(inputs, "range", "scratch", self.spec("probe.c", "c" * 64)))
        self.assertEqual(len(made), 2)                   # nothing constructed for an identity the harness lacks
        with self.assertRaisesRegex(InvariantError, "^cycle 1 proves a story with exactly one probe factory$"):
            sr._probe(inputs, None)                      # without a spec, two factories are ambiguous: refused

    def test_a_by_spec_party_gives_the_maker_the_spec_and_makes_a_probe_per_evaluation(self):
        seen = []

        def maker(on_range, spec):
            seen.append(spec.id)
            return st.FakeProbe({spec.id: Executed(V.SATISFIED)}, on_range)
        party = pf.Party(self.scope, maker, "implementer", by_spec=True)
        at = RevisionRef(st.SHA_B, str(self.tmp / "impl"))
        a = party.run(self.s1, at, st.ENV, under="C1/CANDIDATE")
        b = party.run(self.s0, at, st.ENV, under="C0/CANDIDATE")
        self.assertEqual(seen, [self.s1.id, self.s0.id])
        self.assertEqual([(r.spec_id, r.result) for r in (a, b)], [(self.s1.id, Executed(V.SATISFIED)), (self.s0.id, Executed(V.SATISFIED))])
        legacy = pf.Party(self.scope, lambda on_range: st.FakeProbe({self.s1.id: Executed(V.REFUTED)}, on_range), "verifier")
        self.assertEqual(legacy.run(self.s1, at, st.ENV, under="C1/CANDIDATE").result, Executed(V.REFUTED))   # one argument, as before

    def test_a_party_without_the_spec_s_probe_records_a_typed_INVALID_SPEC_and_runs_nothing(self):
        absent = pf.Party(self.scope, lambda on_range, spec: None, "implementer", by_spec=True)
        n = len(self.run.events)
        rec = absent.run(self.s1, RevisionRef(st.SHA_B, str(self.tmp / "impl")), st.ENV, under="C1/CANDIDATE")
        self.assertEqual((rec.spec_id, rec.semantic_hash, rec.probe_id, rec.probe_digest, rec.revision, rec.enforcement),
                         (self.s1.id, self.s1.semantic_hash, self.s1.probe_id, self.s1.probe_digest, st.SHA_B, Enforcement.UNAVAILABLE))
        self.assertEqual(type(rec.result).__name__, "InvalidSpec")
        self.assertEqual(plain(rec)["result"], {"detail": f"probe {self.s1.probe_id} is not in the harness catalogue"})
        self.assertEqual((len(self.run.events), self.scope.held), (n, ()))   # no range acquired, nothing journaled
        self.assertEqual(bound_result(rec, spec=self.s1, revision=st.SHA_B, enforcement=Enforcement.UNAVAILABLE), rec.result)
        p = pf.prove(self.run, "S1", "C1", self.s1, R.INTRODUCE, implementer=absent,
                     verifier=pf.Party(self.scope, lambda on_range, spec: None, "verifier", by_spec=True), candidate=st.SHA_B,
                     implementer_root=str(self.tmp / "impl"), verifier_root=str(self.tmp / "ver"), env=st.ENV,
                     point=M.CANDIDATE)
        self.assertEqual((p.agreement, p.satisfaction, p.failure.code), (True, None, F.PROBE_INVALID_SPEC))
        self.assertNotIn("verdict", self.run.events[p.verified_seq].data)


# ------------------------------------------------------------------------------------------- PLAN-V2.2 (case 14)

QUALIFICATION = ROOT / "validation" / "qualification"
LEDGERLOCK = ("STORY-01-01", "STORY-03-01", "STORY-04-01", "STORY-04-02")
SMOKE = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_import(self):\n        import ledgerlock  # noqa: F401\n"


@unittest.skipUnless((QUALIFICATION / "p5_acceptance.py").exists(),
                     "validation/qualification is not in this tree (the mutation runner's copy); the suite runs it")
class LedgerLockStories(unittest.TestCase):
    """Case 14: the four owner-approved PLAN-V2.2 stories QP-2.9's preflight found unprovable become representable with
    no contract or plan change — the approved specs (real approvals), the approved plan, the frozen reference tree."""

    @classmethod
    def setUpClass(cls):
        from validation.qualification import p5_acceptance as pa
        from validation.qualification import p5_falsifiability as pfz
        aid = pa._aid()
        reqs, real = aid.requirements(), pa.load_approvals()
        cls.specs = {s.id: s for s in (compile_spec(c, requirements=reqs, approvals=real, probes=REFS) for c in pa.contracts().values())}
        cls.plan = aid.build()["plan"]
        cls.accepted = pa.ACCEPTED["plan_hash"]
        d = tempfile.TemporaryDirectory(prefix="aisef2-c2-ledgerlock-")
        cls.addClassCleanup(d.cleanup)
        cls.tmp = pathlib.Path(d.name)
        cls.reference = pfz.build_tree(None, cls.tmp)

    def mine(self, story):
        return [o for o in self.plan.obligations if o.story_id == story]

    def test_14a_each_spec_s_own_probe_gives_its_pristine_expectation_on_the_reference_tree(self):
        from aisef2.probe.calibration import FIXTURE_REVISION, calibration_env
        self.assertEqual(self.plan.plan_hash, self.accepted)
        self.assertTrue({o.product_proof_spec_id for o in self.plan.obligations} <= set(self.specs))
        inputs = sr.StoryInputs(self.specs, PROBES, ENV, te.DeveloperTests("S", ("t",)), te.DeveloperTests("S", ("t",)),
                                te.Dependencies(frozenset(), frozenset()), te.UNITTEST)
        want = {"STORY-01-01": {"cli_invocation", "file_artifact", "python_callable"},
                "STORY-03-01": {"process_effect", "python_callable"},
                "STORY-04-01": {"cli_invocation", "process_effect"}, "STORY-04-02": {"cli_invocation", "process_effect"}}
        at = RevisionRef(FIXTURE_REVISION, str(self.reference.resolve()))
        for story in LEDGERLOCK:
            kinds = set()
            for o in self.mine(story):
                spec = self.specs[o.product_proof_spec_id]
                probe = sr._probe(inputs, None, str(self.tmp), spec)
                self.assertEqual((probe.id, probe.digest), (spec.probe_id, spec.probe_digest), o.criterion_id)
                result = bound_result(run_probe(probe, spec, at, calibration_env(sys.executable)), spec=spec,
                                      revision=at.sha, enforcement=probe.enforcement())
                self.assertEqual(getattr(result, "behavior_verdict", result), spec.candidate_expectation, o.criterion_id)
                kinds.add(KIND[spec.probe_id])
            self.assertEqual(kinds, want[story], story)

    def test_14b_admission_and_both_parties_accept_each_whole_story_through_the_path(self):
        files = {f"ledgerlock/{p.name}": p.read_text(encoding="utf-8") for p in sorted((self.reference / "ledgerlock").glob("*.py"))}
        holder = Cleanups()
        self.addCleanup(holder.close)
        w = World(holder, self.tmp / "world", {**files, "tests/test_smoke.py": SMOKE})
        for story in LEDGERLOCK:
            with self.subTest(story=story):
                r = w.story(self.plan, story, e2e.Dev(unchanged=True), specs=self.specs, tests=("tests/test_smoke.py",),
                            deps=("ledgerlock", "app", "tests"))
                self.assertEqual([a.outcome for a in r.attempts], ["COMMIT"], (w.failures(story), w.details(story)))
                mine = self.mine(story)
                self.assertEqual(w.admitted(story)["dispositions"],
                                 {o.criterion_id: "PRE_SATISFIED" if o.role is R.INTRODUCE else "READY" for o in mine})
                by_cid = {o.criterion_id: self.specs[o.product_proof_spec_id] for o in mine}
                records = w.records(story)
                self.assertEqual(len([e for e in records if e.data["criterion_id"] in by_cid]), 5 * len(mine))
                for e in records:
                    spec = self.specs[e.data["record"]["spec_id"]]
                    rec = e.data["record"]
                    self.assertEqual((rec["probe_id"], rec["probe_digest"], rec["semantic_hash"], verdict_of(rec)),
                                     (spec.probe_id, spec.probe_digest, spec.semantic_hash, spec.candidate_expectation.value),
                                     e.data["criterion_id"])
                proved = [e.data["criterion_id"] for e in w.events("proof/verified", story) if e.data["candidate"] == w.base]
                self.assertTrue(set(by_cid) <= set(proved))


# ------------------------------------------------------------------------------------------- the record (case 15)

@unittest.skipUnless((QUALIFICATION / "c2_orchestration_repair.py").exists(),
                     "validation/qualification is not in this tree (the mutation runner's copy); the suite runs it")
class Record(unittest.TestCase):
    def test_15_the_record_binds_this_tree_and_old_and_new_agree_on_every_single_probe_story(self):
        from validation.qualification import c2_orchestration_repair as rp
        self.assertEqual(rp.check(), [])
        rec = json.loads((ROOT / rp.OUT_REL).read_text(encoding="utf-8"))
        eq = rec["single_probe_equivalence"]
        self.assertEqual((eq["items"], eq["identical"]), (7, 7))
        self.assertTrue(all(v["outcomes_identical"] and v["journal_identical_but_kernel_identity"] for v in eq["by_item"].values()))
        old, new = rec["defect_reproducer"]["old"], rec["defect_reproducer"]["new"]
        self.assertEqual(old["raised"], "InvariantError: cycle 1 proves a story with exactly one probe factory")
        self.assertEqual((new["raised"], new["attempts"]), (None, ["COMMIT"]))


if __name__ == "__main__":
    unittest.main()
