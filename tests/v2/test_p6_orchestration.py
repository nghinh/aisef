"""WP-6.2 — the single authoritative orchestration path, end to end and adversarially (ORCH-1..16), and the typed
states ARCHITECTURE-EXCEPTION-V2-005 gave it (ORCH-SCHEMA-1..10).

Every story here runs the real path: a real git repository and worktrees, the real python_callable probe for both
parties, WP-5's real test runners at the candidate, the real merger, a RunScope writing journal format 3 — with
typed test doubles only where the path meets a capability (the developer, the reviewer, the scanner). Nothing is
asserted from prose; every claim is read from the journal and its six projections.
"""

import inspect
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction as CS, ControlProjection as P, Enforcement, ObligationRole, Owner, Polarity, SubjectAbsence, SubjectKind,
)
from aisef2.control import budget  # noqa: E402
from aisef2.control.owner import FailureCode, classify  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.journal import format3 as f3  # noqa: E402
from aisef2.journal.format2 import OperationOutcome as O  # noqa: E402
from aisef2.orchestrate import adapters, seam, story_runner as sr  # noqa: E402
from aisef2.orchestrate.adapters import (  # noqa: E402
    CapabilityUnrunnable, Finding, Implemented, ProviderOutage, ResourceUnavailable, Reviewed, Scanned,
)
from aisef2.orchestrate.quality import TestsPolicy  # noqa: E402
from aisef2.orchestrate.workspace import GitMerger, GitWorkspace, commit_all, git  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv  # noqa: E402
from aisef2.probe.python_callable import PythonCallableProbe  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.quality import test_execution as te  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from tests.v2.p4.test_run_scope import spec as RUN_SPEC  # noqa: E402
from tests.v2.p4.world import closed_after  # noqa: E402

ENV = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)
PROBE = {PythonCallableProbe.id: lambda on_range: PythonCallableProbe(on_range=on_range)}
CALC = "def sub(a, b):\n    return a - b\n"
ADD = "\n\ndef add(a, b):\n    return a + b\n"
MUL = "def mul(a, b):\n    return a * b\n"
TEST_OTHER = "import unittest\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_sub(self):\n        self.assertEqual(calc.sub(3, 1), 2)\n"
# the developer's test fails by assertion, not by exception, once the product change is neutralised (§15.1: an
# exception establishes no cause; only an assertion attributes the test to the change)
TEST_ADD = ("import unittest\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n"
            "        add = getattr(calc, 'add', None)\n        self.assertEqual(add(1, 2) if add else None, 3)\n")
TEST_ADD_WRONG = TEST_ADD.replace(", 3)", ", 4)")
TEST_MUL = "import unittest\nfrom app import mul\n\n\nclass T(unittest.TestCase):\n    def test_mul(self):\n        self.assertEqual(mul.mul(2, 3), 6)\n"
SCAN_SCRIPT = "import json, sys\nopen(sys.argv[1], 'w').write(sys.argv[2])\n"
LIMITS = {o: 1 for o in Owner}


# --------------------------------------------------------------------------------------- fixtures

def make_repo(root: pathlib.Path, files: dict | None = None) -> tuple[str, str]:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    base = {"app/__init__.py": "", "app/calc.py": CALC, "tests/__init__.py": "", "tests/test_other.py": TEST_OTHER}
    for rel, text in {**base, **(files or {})}.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    return str(repo), commit_all(repo, "base")


def contract(cid: str, locator: str, args: list, returns) -> tuple:
    req = Requirement.create(id=f"R-{cid}", text=f"requirement {cid}", source="tests")
    c = BehaviorContract.create(id=f"BC-{cid}", requirement_ids=(req.id,),
                                subject=Subject(SubjectKind.PYTHON_CALLABLE, locator), stimulus={"args": args},
                                observable={"returns": returns, "within_s": 10}, polarity=Polarity.MUST_HOLD,
                                subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale=f"rationale {cid}")
    approval = ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())
    spec = compile_spec(c, requirements={req.id: req}, approvals=[approval],
                        probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(PythonCallableProbe.id, PythonCallableProbe.digest)})
    return c, spec


def obligation(cid: str, spec_id: str, story: str, role: ObligationRole) -> PlanObligation:
    return PlanObligation(cid, spec_id, story, role, EXPECTED_AT_PARENT[role], (), f"{story} owns {cid}")


def plan_of(base: str, *obligations: PlanObligation, pid: str = "PLAN-ORCH") -> Plan:
    return Plan.create(id=pid, baseline=base, obligations=tuple(obligations), plan_quality_policy=NOT_PREREGISTERED)


class Dev:
    """A developer capability: writes files into its checkout and commits; optionally also lands a commit on the
    branch first (a concurrent merge), fails, or is out."""

    def __init__(self, files: dict | None = None, *, on_trunk: dict | None = None, repo: str | None = None,
                 fail: bool = False, outage: bool = False, unchanged: bool = False) -> None:
        self.files, self.on_trunk, self.repo, self.fail, self.outage = files or {}, on_trunk, repo, fail, outage
        self.unchanged = unchanged   # answers with the checkout's own revision: a candidate without a change
        self.calls: list[tuple[str, tuple[str, ...], str]] = []
        self.candidates: list[str] = []

    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str) -> Implemented:
        self.calls.append((story_id, criteria, checkout))
        if self.outage:
            raise ProviderOutage("503 from the developer capability")
        if self.fail:
            return Implemented(O.FAILED, None, "the developer gave up")
        if self.unchanged:
            return Implemented(O.COMPLETED, git(checkout, "rev-parse", "HEAD").stdout.strip(), "nothing to change")
        for rel, text in self.files.items():
            p = pathlib.Path(checkout, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        sha = commit_all(checkout, f"{story_id}: {', '.join(criteria)}")
        self.candidates.append(sha)
        if self.on_trunk:
            land(self.repo, self.on_trunk, "concurrent change on main")
        return Implemented(O.COMPLETED, sha, f"implemented {len(self.files)} files")


def land(repo: str, files: dict, message: str) -> str:
    """A commit on main made by somebody else, through a detached worktree (git makes and removes it) and update-ref."""
    tip = git(repo, "rev-parse", "main").stdout.strip()
    wt = os.path.join(tempfile.mkdtemp(prefix="land-"), "wt")
    assert git(repo, "worktree", "add", "--detach", wt, tip).returncode == 0
    try:
        for rel, text in files.items():
            pathlib.Path(wt, rel).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(wt, rel).write_text(text, encoding="utf-8")
        sha = commit_all(wt, message)
        assert git(repo, "update-ref", "refs/heads/main", sha, tip).returncode == 0
        return sha
    finally:
        git(repo, "worktree", "remove", "--force", wt)
        git(repo, "worktree", "prune")


class Rev:
    def __init__(self, findings=(), *, outage=False, unrunnable=False, writes=False, fails=False) -> None:
        self.findings, self.outage, self.unrunnable, self.writes, self.fails = tuple(findings), outage, unrunnable, writes, fails
        self.seen: list[adapters.ReadOnlyScope] = []

    def review(self, scope: adapters.ReadOnlyScope, criteria: tuple[str, ...]) -> Reviewed:
        self.seen.append(scope)
        if self.outage:
            raise ProviderOutage("reviewer 502")
        if self.unrunnable:
            raise CapabilityUnrunnable("no reviewer binary on this host")
        if self.writes:
            pathlib.Path(scope.root, "app", "calc.py").write_text("tampered", encoding="utf-8")
        if self.fails:
            return Reviewed(O.FAILED, (), "the reviewer failed")
        return Reviewed(O.COMPLETED, self.findings, f"reviewed {len(scope.files())} files")


class Scan:
    name = "scan"

    def __init__(self, script: str, findings=(), *, interpreter: str = sys.executable, silent: bool = False) -> None:
        self.script, self.findings, self.interpreter, self.silent = script, tuple(findings), interpreter, silent

    def argv(self, scope: adapters.ReadOnlyScope, report: str) -> tuple[str, ...]:
        payload = "" if self.silent else json.dumps([[f.id, f.blocking, list(f.corroborated_by)] for f in self.findings])
        return (self.interpreter, self.script, report, payload)

    def read(self, report: str, exit_code) -> Scanned:
        p = pathlib.Path(report)
        if not p.exists() or not p.read_text(encoding="utf-8").strip():
            return Scanned(False, ())
        rows = json.loads(p.read_text(encoding="utf-8"))
        return Scanned(True, tuple(Finding(i, b, tuple(c)) for i, b, c in rows))


class Orchestration(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-orch-")
        self.addCleanup(self._d.cleanup)
        self.tmp = pathlib.Path(self._d.name)
        self.repo, self.base = make_repo(self.tmp)
        (self.tmp / "ws").mkdir()
        (self.tmp / "merge").mkdir()
        (self.tmp / "run").mkdir()
        self.script = str(self.tmp / "scan.py")
        pathlib.Path(self.script).write_text(SCAN_SCRIPT, encoding="utf-8")
        self.ws = GitWorkspace(self.repo, self.tmp / "ws")
        self.merger = GitMerger(self.repo, "main", self.tmp / "merge")
        self.clock = iter(float(n) for n in range(10 ** 6))
        self.run = closed_after(self, RunScope(self.tmp / "run", "run-orch", spec=RUN_SPEC, clock=lambda: next(self.clock)))
        self.run.begin()
        self.c1, self.s1 = contract("C1", "app.calc:add", [1, 2], 3)
        self.c2, self.s2 = contract("C2", "app.mul:mul", [2, 3], 6)
        self.c0, self.s0 = contract("C0", "app.calc:sub", [3, 1], 2)
        self.specs = {self.s1.id: self.s1, self.s2.id: self.s2, self.s0.id: self.s0}

    # ---- helpers
    def inputs(self, story: str, tests=("tests/test_s1.py",), regressions=("tests/test_other.py",), runner=te.UNITTEST, **kw):
        return sr.StoryInputs(self.specs, PROBE, ENV, te.DeveloperTests(story, tuple(tests)),
                              te.DeveloperTests(story, tuple(regressions)), te.Dependencies(frozenset(), frozenset({"app", "tests"})),
                              runner, **kw)

    def adapters(self, dev, reviewer=None, scanner=None, workspace=None, merger=None):
        return sr.Adapters(dev, reviewer or Rev(), scanner or Scan(self.script), merger or self.merger, workspace or self.ws)

    def story(self, plan, story, dev, *, inputs=None, tests_block=True, limits=LIMITS, **adapter_kw):
        return sr.run_story(self.run, plan, story, inputs or self.inputs(story), self.adapters(dev, **adapter_kw),
                            sr.Policy(limits, TestsPolicy(tests_block), tool_timeout_s=60))

    def events(self, kind=None, story=None):
        return [e for e in self.run.events if (kind is None or e.type == kind)
                and (story is None or e.data.get("story_id") == story)]

    def types(self, story=None):
        return [e.type for e in self.events(story=story)] if story else [e.type for e in self.run.events]

    def failures(self, story):
        return [(e.data["code"], e.data["owner"], e.data["retryable"]) for e in self.events("failure/observed", story)]

    def details(self, story):
        return [e.data["detail"] for e in self.events("failure/observed", story)]

    def rows(self, story):
        return [(e.data["check"], e.data["passed"], e.data["detail"]) for e in self.events("gate/check")
                if e.data["check"].startswith(story + ":")]

    def s1_dev(self, **kw):
        return Dev({"app/calc.py": CALC + ADD, "tests/test_s1.py": TEST_ADD}, **kw)

    def s1_plan(self):
        return plan_of(self.base, obligation("C1", self.s1.id, "S1", ObligationRole.INTRODUCE))

    def assert_disposed(self, story):
        acquired = self.events("story/resource-acquired", story)
        released = self.events("story/resource-released", story)
        self.assertEqual(len(acquired), len(released))
        self.assertTrue(all(e.data["status"] == "RELEASED" for e in released), [e.data for e in released])
        self.assertEqual(self.run.state(P.STORY_STATE)[story]["state"], "ENDED")
        self.assertFalse((self.tmp / "ws" / f"wt-{story}").exists())
        self.assertFalse((self.tmp / "ws" / f"verifier-wt-{story}").exists())

    # ------------------------------------------------------------------------------- ORCH-1..16
    def test_ORCH_1_an_end_to_end_story_completes_through_the_real_path(self):
        dev = self.s1_dev()
        r = self.story(self.s1_plan(), "S1", dev)
        self.assertTrue(r.committed)
        self.assertEqual(r.revision, self.merger.base())         # the merge landed on main
        self.assertNotEqual(r.revision, self.base)
        self.assertEqual([a.outcome for a in r.attempts], ["COMMIT"])
        self.assertIsInstance(r.attempts, tuple)                # immutable, like every result of the path
        self.assertIsInstance(r.attempts[0].proofs, tuple)
        self.assertIsInstance(r.attempts[0].checks, tuple)
        st = self.run.state(P.STORY_STATE)["S1"]
        self.assertEqual((st["state"], st["attempt"], st["outcome"]), ("ENDED", 1, "COMMIT"))
        b = self.run.state(P.BUDGETS)
        self.assertEqual(b["developer"], {"S1": {"requests": 1, "criteria": {"C1": 1}}})
        self.assertEqual(b["review"], {"S1": {"requests": 1, "criteria": {"C1": 1}}})
        self.assertEqual((b["retries"], b["format"]), ({}, 3))
        kinds = self.types("S1")
        for k in ("story/begin", "probe/evaluated", "story/admitted", "provider/request", "provider/result",
                  "proof/verified", "tests/adequacy", "tool/invoked", "tool/result", "story/commit", "story/dispose",
                  "story/end"):
            self.assertIn(k, kinds, k)
        self.assertLess(kinds.index("story/admitted"), kinds.index("provider/request"))   # ORCH-4: nothing before admission
        self.assertLess(kinds.index("proof/verified"), kinds.index("tests/adequacy"))
        self.assertLess(kinds.index("tests/adequacy"), kinds.index("tool/invoked"))
        self.assertLess(kinds.index("tool/result"), kinds.index("story/commit"))
        proofs = self.events("proof/verified", "S1")
        self.assertEqual([e.data["agreement"] for e in proofs], [True, True])          # candidate, then post-merge
        self.assertEqual([e.data["candidate"] for e in proofs], [dev.candidates[0], r.revision])
        adequacy = self.events("tests/adequacy", "S1")[0].data
        self.assertEqual((adequacy["outcome"], adequacy["owner"], adequacy["may_block"]), ("ADEQUATE", None, False))
        decision = self.events("gate/decision")[-1]
        checks = [e for e in self.run.events if e.type == "gate/check" and e.data["gate"] == "story"]
        self.assertEqual((decision.data["passed"], tuple(decision.source_seqs)), (True, tuple(e.seq for e in checks)))
        self.assertEqual(self.rows("S1"), [
            ("S1:admission", True, "admitted"), ("S1:developer", True, "implemented 2 files"),
            ("S1:proof:C1", True, "verified"), ("S1:quality", True, "ADEQUATE"),
            ("S1:review", True, "reviewed: no finding"), ("S1:security", True, "scan ran: no finding"),
            ("S1:merge", True, f"merged at {r.revision}"), ("S1:post-merge:C1", True, "re-proved at the merged revision")])
        probe = f"probe {self.s1.id}"
        self.assertEqual([e.data["resource"] for e in self.events("story/resource-acquired", "S1")], [
            "scratch-S1", "wt-S1", "verifier-wt-S1", f"{probe} [admission 1]",
            f"{probe} [C1/CANDIDATE implementer]", f"{probe} [C1/CANDIDATE verifier]",
            "tests S1 [tests 1]", "tests S1 [tests 2]", "tests S1 [tests 3]", "tool scan-S1#1",
            f"{probe} [C1/POST_MERGE implementer]", f"{probe} [C1/POST_MERGE verifier]"])
        self.assert_disposed("S1")
        self.assertEqual(self.failures("S1"), [])
        self.assertEqual(self.run.state(P.STORY_STATE)["S1"]["outcome"], "COMMIT")
        self.assertEqual(sorted(r.measured), [self.s1.id])
        self.assertEqual((r.measured[self.s1.id].at_parent, r.measured[self.s1.id].at_merge), (CS.INDETERMINATE, CS.SATISFIED))

    def test_SINGLE_PATH_one_entry_and_no_V1_authority(self):
        src = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "aisef2/orchestrate").glob("*.py")}
        for name, text in src.items():
            with self.subTest(module=name):
                self.assertNotRegex(text, r"^\s*(from|import) aisef(\.|\s|$)", "the frozen V1 kernel is never imported")
                self.assertNotIn("aisef.control", text)
        self.assertEqual([n for n, f in inspect.getmembers(sr, inspect.isfunction) if not n.startswith("_") and f.__module__ == sr.__name__],
                         ["run_story"])
        self.assertEqual(len(inspect.signature(sr.run_story).parameters), 6)

    def test_ORCH_13_the_seam_refuses_a_HUMAN_DECLARATION_REQUIRED_row_before_any_provider_execution(self):
        table = json.loads((ROOT / "closure-evidence/v2/P6-MIGRATION-TABLE.json").read_text(encoding="utf-8"))
        before = len(self.run.events)
        with self.assertRaisesRegex(seam.SeamRefusal, r"C1 \(CHANGE_REQUIRED\): HUMAN_DECLARATION_REQUIRED"):
            self.story(self.s1_plan(), "S1", self.s1_dev(),
                       inputs=self.inputs("S1", legacy={"C1": "CHANGE_REQUIRED"}, migration_table=table))
        self.assertEqual(len(self.run.events), before)                                    # no story/begin, no request
        with self.assertRaisesRegex(seam.SeamRefusal, "no migration table"):
            self.story(self.s1_plan(), "S1", self.s1_dev(), inputs=self.inputs("S1", legacy={"C1": "CHANGE_REQUIRED"}))
        with self.assertRaisesRegex(seam.SeamRefusal, "no row in the migration table"):
            self.story(self.s1_plan(), "S1", self.s1_dev(),
                       inputs=self.inputs("S1", legacy={"C1": "NOT_A_MODE"}, migration_table=table,
                                          declarations={"C1": SubjectAbsence.REQUIRES_SUBJECT}))
        self.assertEqual(len(self.run.events), before)
        r = self.story(self.s1_plan(), "S1", self.s1_dev(),
                       inputs=self.inputs("S1", legacy={"C1": "CHANGE_REQUIRED"}, migration_table=table,
                                          declarations={"C1": SubjectAbsence.REQUIRES_SUBJECT}))
        self.assertTrue(r.committed)
        legacy = seam.resolve("C1", "CHANGE_REQUIRED", table, SubjectAbsence.REQUIRES_SUBJECT)
        self.assertEqual((legacy.role, legacy.polarity, legacy.subject_absence),
                         (ObligationRole.INTRODUCE, Polarity.MUST_HOLD, SubjectAbsence.REQUIRES_SUBJECT))

    def test_ORCH_14_a_change_of_engineering_adequacy_leaves_the_product_proof_unchanged(self):
        # the product proof passes while the developer's own test is wrong: INADEQUATE, DEVELOPER — only the policy blocks
        dev = Dev({"app/calc.py": CALC + ADD, "tests/test_s1.py": TEST_ADD_WRONG})
        r = self.story(self.s1_plan(), "S1", dev, tests_block=False)
        self.assertTrue(r.committed)
        adequacy = self.events("tests/adequacy", "S1")[0].data
        self.assertEqual((adequacy["outcome"], adequacy["owner"], adequacy["may_block"], adequacy["developer_chargeable"]),
                         ("INADEQUATE", "DEVELOPER", True, True))
        self.assertEqual([e.data["agreement"] for e in self.events("proof/verified", "S1")], [True, True])
        self.assertEqual(self.failures("S1"), [])

    def test_ORCH_11_scenario_L_INTRODUCE_PRESERVE_and_VERIFY_give_the_identical_product_verdict(self):
        # one spec, three stories with the three roles; S1 introduces `add`, S2 and S3 change nothing, so the three
        # post-merge proofs are of the same spec at the same revision — and must say the same thing
        plan = plan_of(self.base, obligation("C1", self.s1.id, "S1", ObligationRole.INTRODUCE),
                       obligation("C1P", self.s1.id, "S2", ObligationRole.PRESERVE),
                       obligation("C1V", self.s1.id, "S3", ObligationRole.VERIFY))
        r1 = self.story(plan, "S1", self.s1_dev())
        r2 = self.story(plan, "S2", Dev(unchanged=True), tests_block=False)
        r3 = self.story(plan, "S3", Dev(unchanged=True), tests_block=False)
        self.assertEqual([r.committed for r in (r1, r2, r3)], [True, True, True])
        self.assertEqual({r.revision for r in (r1, r2, r3)}, {r1.revision})
        proofs = {}
        for story in ("S1", "S2", "S3"):
            e = [e for e in self.events("proof/verified", story) if e.data["candidate"] == r1.revision][-1]
            proofs[story] = {k: v for k, v in e.data.items() if k not in ("story_id", "criterion_id")}
            self.assertEqual(f3.verified_proof(e, self.run.events[:e.seq])["verdict"], "SATISFIED")
            records = [self.run.events[s].data["record"] for s in e.source_seqs]
            self.assertEqual({(x["probe_id"], x["probe_digest"], x["enforcement"], x["semantic_hash"], x["revision"])
                              for x in records},
                             {(PythonCallableProbe.id, PythonCallableProbe.digest, "PARTIAL", self.s1.semantic_hash,
                               r1.revision)})
        self.assertEqual(proofs["S1"], proofs["S2"])
        self.assertEqual(proofs["S2"], proofs["S3"])
        self.assertEqual(sorted(proofs["S1"]), ["agreement", "candidate", "semantic_hash", "spec_id", "verdict"])
        self.assertEqual((proofs["S1"]["verdict"], proofs["S1"]["agreement"]), ("SATISFIED", True))
        roles = self.events("plan/frozen")[0].data["roles"]
        self.assertEqual(dict(roles), {"C1": "INTRODUCE", "C1P": "PRESERVE", "C1V": "VERIFY"})
        self.assertEqual([(r.measured[self.s1.id].at_parent, r.measured[self.s1.id].at_merge) for r in (r1, r2, r3)],
                         [(CS.INDETERMINATE, CS.SATISFIED), (CS.SATISFIED, CS.SATISFIED), (CS.SATISFIED, CS.SATISFIED)])

    def test_ORCH_12_a_reviewer_confinement_parameter_is_impossible_by_API_shape(self):
        for mod in (sr, adapters):
            for name, f in inspect.getmembers(mod, inspect.isfunction):
                for bad in ("readonly", "read_only", "sandbox", "allow_write", "confinement", "writable"):
                    self.assertNotIn(bad, inspect.signature(f).parameters, f"{mod.__name__}.{name}")
        self.assertEqual(list(inspect.signature(adapters.confine).parameters), ["story_id", "checkout"])
        reviewer = Rev(writes=True)
        with self.assertRaises(PermissionError):
            self.story(self.s1_plan(), "S1", self.s1_dev(), reviewer=reviewer)
        self.assertEqual(len(reviewer.seen), 1)
        self.assertTrue(reviewer.seen[0].root.endswith("verifier-wt-S1"))

    def test_VERIFIER_INDEPENDENCE_its_own_checkout_and_the_identical_instrument(self):
        r = self.story(self.s1_plan(), "S1", self.s1_dev())
        proofs = [e for e in self.events("proof/verified", "S1")]
        for e in proofs:
            a, b = (self.run.events[s].data["record"] for s in e.source_seqs)
            self.assertEqual((a["probe_id"], a["probe_digest"], a["enforcement"], a["semantic_hash"]),
                             (b["probe_id"], b["probe_digest"], b["enforcement"], b["semantic_hash"]))
            self.assertEqual(a["revision"], b["revision"])
        names = [e.data["resource"] for e in self.events("story/resource-acquired", "S1")]
        self.assertEqual(names[:3], ["scratch-S1", "wt-S1", "verifier-wt-S1"])
        self.assertTrue(r.committed)

    def test_ORCH_8_and_SCHEMA_3_a_merge_conflict_is_MERGE_CONFLICT_INTEGRATION_with_zero_developer_charge(self):
        dev = self.s1_dev(on_trunk={"app/calc.py": CALC + "\n\ndef add(a, b):\n    return b + a\n"}, repo=self.repo)
        r = self.story(self.s1_plan(), "S1", dev)
        self.assertFalse(r.committed)
        self.assertEqual(self.failures("S1"), [("MERGE_CONFLICT", "INTEGRATION", False)])
        self.assertEqual(self.details("S1"), ["merge: MERGE_CONFLICT"])
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])
        self.assertEqual(self.run.state(P.BUDGETS)["retries"], {})
        merge_check = next(e for e in self.events("gate/check") if e.data["check"] == "S1:merge")
        self.assertEqual((merge_check.data["passed"], "app/calc.py" in merge_check.data["detail"]), (False, True))
        self.assert_disposed("S1")

    def test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back(self):
        plan = plan_of(self.base, obligation("C1", self.s1.id, "S0", ObligationRole.INTRODUCE),
                       obligation("C0", self.s0.id, "S0", ObligationRole.PRESERVE),
                       obligation("C2", self.s2.id, "S2", ObligationRole.INTRODUCE))
        r0 = self.story(plan, "S0", self.s1_dev(), inputs=self.inputs("S0"))
        self.assertTrue(r0.committed)
        self.assertEqual([e.data["check"] for e in self.events("gate/check") if e.data["check"].startswith("S0:post")],
                         ["S0:post-merge:C1", "S0:post-merge:C0"])
        tip = self.merger.base()
        breaking = Dev({"app/mul.py": MUL, "tests/test_s2.py": TEST_MUL,
                        "app/calc.py": "def sub(a, b):\n    return a + b\n"})       # breaks S0's preserved behaviour
        r2 = self.story(plan, "S2", breaking, inputs=self.inputs("S2", tests=("tests/test_s2.py",), regressions=("tests/test_other.py",)),
                        tests_block=False)
        self.assertFalse(r2.committed)
        codes = self.failures("S2")
        self.assertEqual(codes, [("POST_MERGE_REGRESSION", "INTEGRATION", False)])
        self.assertEqual(self.details("S2"), ["post-merge C0: POST_MERGE_REGRESSION"])
        self.assertEqual(self.merger.base(), tip)           # the merge was rolled back
        checks = [(e.data["check"], e.data["passed"]) for e in self.events("gate/check") if e.data["check"].startswith("S2:post")]
        self.assertEqual(checks, [("S2:post-merge:C2", True), ("S2:post-merge:C0", False)])   # the prior story's PRESERVE, re-proved
        self.assertEqual([a.outcome for a in r2.attempts], ["ROLLBACK"])
        adequacy = self.events("tests/adequacy", "S2")[0].data
        self.assertEqual((adequacy["outcome"], adequacy["regressions"]["outcome"]), ("INADEQUATE", "FAILED"))  # the policy let it through; the proof did not
        self.assert_disposed("S2")

    def test_JOURNAL_AUTHORITY_the_decision_cites_every_check_row_of_the_story_gate(self):
        r = self.story(self.s1_plan(), "S1", self.s1_dev())
        decisions = self.events("gate/decision")
        self.assertEqual(len(decisions), 1)
        cited = [self.run.events[s] for s in decisions[0].source_seqs]
        self.assertTrue(all(e.type == "gate/check" and e.data["gate"] == "story" for e in cited))
        self.assertEqual(len(cited), len([e for e in self.events("gate/check")]))
        self.assertEqual(list(decisions[0].data["projections"]), ["story_state", "budgets", "failure_owner", "retry_target"])
        self.assertTrue(r.committed)

    def test_ORCH_16_retry_state_derives_solely_from_the_journal_projection(self):
        scanner = Scan(self.script, interpreter="/nonexistent/aisef2-python")
        calls = []
        real = Scan(self.script)

        class Flaky:
            name = "scan"

            def argv(s, scope, report):
                calls.append(1)
                return (scanner if len(calls) == 1 else real).argv(scope, report)

            def read(s, report, exit_code):
                return real.read(report, exit_code)
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), scanner=Flaky(), limits={**LIMITS, Owner.ENVIRONMENT: 1})
        self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "COMMIT"])
        self.assertEqual(self.failures("S1"), [("CAPABILITY_UNRUNNABLE", "ENVIRONMENT", True)])
        b = self.run.state(P.BUDGETS)
        self.assertEqual(b["retries"], {"S1": {"ENVIRONMENT": 1}})
        self.assertEqual(b["developer"]["S1"]["requests"], 2)   # two attempts, each admitted and implemented anew
        st = self.run.state(P.STORY_STATE)["S1"]
        self.assertEqual((st["attempt"], st["outcome"]), (2, "COMMIT"))
        self.assertEqual(self.types("S1").count("story/retry"), 1)
        self.assert_disposed("S1")

    def test_ORCH_2_a_developer_outage_mid_story_is_a_typed_PROVIDER_failure_with_no_cross_charge(self):
        r = self.story(self.s1_plan(), "S1", Dev(outage=True))
        self.assertEqual(self.failures("S1"), [("PROVIDER_UNAVAILABLE", "PROVIDER", True)] * 2)
        self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "ROLLBACK"])   # PROVIDER limit 1: one retry, then no
        self.assertEqual(self.merger.base(), self.base)
        self.assert_disposed("S1")
        self.assertEqual(self.rows("S1"), [("S1:admission", True, "admitted"),
                                           ("S1:developer", False, "developer outage: 503 from the developer capability")] * 2)
        self.assertEqual(self.details("S1"), ["developer outage: 503 from the developer capability"] * 2)
        b = self.run.state(P.BUDGETS)
        self.assertEqual(b["retries"], {"S1": {"PROVIDER": 1}})            # the PROVIDER budget, nothing else
        self.assertEqual((b["review"], b["security"]), ({}, {}))
        self.assertEqual(b["developer"]["S1"]["requests"], 2)              # two requests made, no developer retry
        self.assertEqual(self.run.state(P.FAILURE_OWNER)["S1"]["owner"], "PROVIDER")
        results = self.events("provider/result", "S1")
        self.assertEqual([(e.data["outcome"], e.data["detail"], e.data["synthetic"]) for e in results],
                         [("FAILED", "developer outage: 503 from the developer capability", False)] * 2)
        self.run.shutdown()
        self.assertEqual(self.types()[-1], "run/end")

    def test_ORCH_3_an_admission_refusal_makes_no_provider_request(self):
        plan = plan_of(self.base, obligation("C1", self.s1.id, "S1", ObligationRole.PRESERVE))   # `add` is absent at base
        r = self.story(plan, "S1", self.s1_dev())
        c = classify(FailureCode.PRECONDITION_BROKEN)
        self.assertEqual(self.failures("S1"), [("PRECONDITION_BROKEN", c.owner.value, c.budget is not None)])
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])
        self.assertEqual(self.events("provider/request", "S1"), [])
        self.assertEqual(self.events("story/admitted", "S1")[0].data["admitted"], False)
        self.assertEqual(self.rows("S1"), [("S1:admission", False, "C1: PRECONDITION_BROKEN")])
        self.assertEqual(self.details("S1"), ["admission: PRECONDITION_BROKEN"])
        self.assertEqual((r.measured[self.s1.id].at_parent, r.measured[self.s1.id].at_merge), (CS.INDETERMINATE, None))
        self.assertEqual(self.run.state(P.BUDGETS)["developer"], {})
        self.assertEqual(self.merger.base(), self.base)
        self.assert_disposed("S1")

    def test_ORCH_4_pre_satisfied_obligations_skip_the_developer_and_the_candidate_is_still_verified(self):
        land(self.repo, {"app/calc.py": CALC + ADD, "tests/test_s1.py": TEST_ADD}, "add landed earlier")
        base = self.merger.base()
        r = self.story(plan_of(base, obligation("C1", self.s1.id, "S1", ObligationRole.INTRODUCE)), "S1",
                       Dev(outage=True), tests_block=False)                     # a developer call would raise: none is made
        self.assertTrue(r.committed)
        self.assertEqual(self.events("story/admitted", "S1")[0].data["dispositions"]["C1"], "PRE_SATISFIED")
        self.assertEqual([e.data["budget_owner"] for e in self.events("provider/request", "S1")], ["REVIEW"])
        self.assertEqual(self.run.state(P.BUDGETS)["developer"], {})
        drift = self.events("story/plan-drift", "S1")
        self.assertEqual([(e.data["criterion_id"], e.data["attributed_to"]) for e in drift], [("C1", "UNATTRIBUTED")])
        probes = self.events("probe/evaluated", "S1")
        self.assertEqual(len(probes), 5)                                        # parent; candidate x2; post-merge x2
        self.assertEqual([e.data["agreement"] for e in self.events("proof/verified", "S1")], [True, True])
        self.assertEqual(r.revision, base)                                      # nothing to merge: main stays
        self.assertEqual((r.measured[self.s1.id].at_parent, r.measured[self.s1.id].at_merge), (CS.SATISFIED, CS.SATISFIED))
        self.assertIn("S1:proof:C1", [e.data["check"] for e in self.events("gate/check")])

    def test_ORCH_15_only_an_explicit_immutable_reference_selects_evidence(self):
        calls = []
        real, absent = Scan(self.script), Scan(self.script, interpreter="/nonexistent/aisef2-python")

        class Flaky:
            name = "scan"

            def argv(s, scope, report):
                calls.append(1)
                return (absent if len(calls) == 1 else real).argv(scope, report)

            def read(s, report, exit_code):
                return real.read(report, exit_code)
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), scanner=Flaky())
        self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "COMMIT"])
        retry = self.events("story/retry", "S1")[0]
        failure = self.events("failure/observed", "S1")[0]
        self.assertEqual(tuple(retry.source_seqs), (failure.seq,))             # the retry cites its failure by seq
        first, second = self.events("gate/decision")
        self.assertEqual(tuple(first.source_seqs), r.attempts[0].checks)
        self.assertEqual(tuple(second.source_seqs), r.attempts[1].checks)
        self.assertTrue(all(s > retry.seq for s in second.source_seqs))       # the new attempt's own rows, not the latest of all
        self.assertTrue(all(s < failure.seq for s in first.source_seqs))
        proofs = self.events("proof/verified", "S1")
        self.assertEqual(len(proofs), 3)                                        # attempt 1 candidate; attempt 2 candidate, post-merge
        for e in proofs:
            cited = [self.run.events[s] for s in e.source_seqs]
            self.assertEqual([c.type for c in cited], ["probe/evaluated", "probe/evaluated"])
            self.assertEqual({c.data["record"]["revision"] for c in cited}, {e.data["candidate"]})
            self.assertEqual(f3.verified_proof(e, self.run.events[:e.seq])["candidate_sha"], e.data["candidate"])
        commit = self.events("story/commit", "S1")[0]
        self.assertEqual(commit.data["revision"], r.revision)
        before = budget.charge(self.run.events[:retry.seq], "S1", LIMITS)                  # the projection, not a counter
        self.assertEqual((before.retry, before.failure_seq, before.budget), (True, failure.seq, "ENVIRONMENT"))
        self.assertIsNone(self.run.state(P.RETRY_TARGET)["S1"]["failure_seq"])            # cleared by the commit
        self.assertEqual(self.run.state(P.STORY_STATE)["S1"]["attempt"], r.attempts[-1].number)

    # ------------------------------------------------------------------------------- ORCH-SCHEMA-1..10
    def _double(self, verdict_for_verifier):
        """A probe pair: the implementer's real probe, and a verifier probe answering `verdict_for_verifier`."""
        real = PythonCallableProbe

        class Verifier:
            id, digest = real.id, real.digest

            def __init__(self, on_range=None):
                self._real = real(on_range=on_range)

            def enforcement(self):
                return Enforcement.PARTIAL

            def harness_preconditions(self):
                return ()

            def evaluate(self, spec, at, env):
                return Executed(verdict_for_verifier)
        made = []

        def factory(on_range):
            made.append(1)
            return real(on_range=on_range) if len(made) % 2 == 1 else Verifier(on_range)
        return {real.id: factory}

    def test_ORCH_5_and_SCHEMA_1_a_verifier_disagreement_is_VERIFIER_DISAGREEMENT_INTEGRATION_and_stops(self):
        inputs = sr.StoryInputs(self.specs, self._double(BehaviorVerdict.REFUTED), ENV, te.DeveloperTests("S1", ("tests/test_s1.py",)),
                                te.DeveloperTests("S1", ("tests/test_other.py",)), te.Dependencies(frozenset(), frozenset({"app"})), te.UNITTEST)
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), inputs=inputs)
        self.assertEqual(self.failures("S1"), [("VERIFIER_DISAGREEMENT", "INTEGRATION", False)])
        self.assertEqual(self.details("S1"), ["proof of C1: VERIFIER_DISAGREEMENT"])
        self.assertEqual(self.rows("S1")[-1], ("S1:proof:C1", False, "VERIFIER_DISAGREEMENT"))
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])
        proof = self.events("proof/verified", "S1")[0].data
        self.assertEqual((proof["agreement"], "verdict" in proof), (False, False))
        self.assertEqual(len(self.events("probe/evaluated", "S1")), 3)  # one at the parent, two at the candidate: never a third
        self.assertEqual(self.merger.base(), self.base)

    def test_ORCH_SCHEMA_2_a_probe_mismatch_is_PROBE_MISMATCH_and_never_a_proof(self):
        real = PythonCallableProbe

        class Other(real):
            digest = "1" * 64
        made = []

        def factory(on_range):
            made.append(1)
            return real(on_range=on_range) if len(made) % 2 == 1 else Other(on_range=on_range)
        inputs = sr.StoryInputs(self.specs, {real.id: factory}, ENV, te.DeveloperTests("S1", ("tests/test_s1.py",)),
                                te.DeveloperTests("S1", ("tests/test_other.py",)), te.Dependencies(frozenset(), frozenset({"app"})), te.UNITTEST)
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), inputs=inputs)
        self.assertEqual(self.failures("S1"), [("PROBE_MISMATCH", "INTEGRATION", False)])
        self.assertEqual(self.details("S1"), ["proof of C1: PROBE_MISMATCH"])
        self.assertEqual(self.rows("S1")[-1], ("S1:proof:C1", False, "PROBE_MISMATCH"))
        self.assertEqual(self.events("proof/verified", "S1"), [])
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])

    def test_ORCH_SCHEMA_4_tests_that_cannot_run_are_TESTS_UNRUNNABLE_with_no_developer_charge(self):
        absent = te.Runner("absent", ("-m", "aisef2_no_such_runner", "{out}"), te._read_unittest)
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), inputs=self.inputs("S1", runner=absent))
        self.assertEqual(self.failures("S1"), [("TESTS_UNRUNNABLE", "ENVIRONMENT", True)] * 2)
        self.assertEqual(self.details("S1"), ["engineering quality: TESTS_UNRUNNABLE"] * 2)
        self.assertEqual([x for x in self.rows("S1") if x[0] == "S1:quality"], [("S1:quality", False, "no AdequacyOutcome")] * 2)
        self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "ROLLBACK"])
        b = self.run.state(P.BUDGETS)
        self.assertEqual(b["retries"], {"S1": {"ENVIRONMENT": 1}})
        adequacy = self.events("tests/adequacy", "S1")[0].data
        self.assertEqual((adequacy["outcome"], adequacy["owner"], adequacy["developer_chargeable"]), (None, "ENVIRONMENT", False))
        self.assertNotIn("DEVELOPER", b["retries"]["S1"])

    def test_ORCH_SCHEMA_5_INADEQUATE_under_a_blocking_policy_is_TESTS_INADEQUATE_owned_by_DEVELOPER(self):
        dev = Dev({"app/calc.py": CALC + ADD, "tests/test_s1.py": TEST_ADD_WRONG})
        r = self.story(self.s1_plan(), "S1", dev, tests_block=True, limits={**LIMITS, Owner.DEVELOPER: 0})
        self.assertEqual(self.failures("S1"), [("TESTS_INADEQUATE", "DEVELOPER", True)])
        self.assertEqual(self.details("S1"), ["engineering quality: TESTS_INADEQUATE"])
        self.assertEqual(self.rows("S1")[-1], ("S1:quality", False, "INADEQUATE"))
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])
        self.assertEqual(self.events("tests/adequacy", "S1")[0].data["outcome"], "INADEQUATE")

    def test_ORCH_SCHEMA_6_an_integration_owned_INCOMPLETE_collection_is_recorded_only(self):
        dev = Dev({"app/calc.py": CALC + ADD, "tests/test_s1.py": TEST_ADD,
                   "tests/test_other.py": "import zzz_no_such_dependency\n" + TEST_OTHER})
        r = self.story(self.s1_plan(), "S1", dev, tests_block=True)
        adequacy = self.events("tests/adequacy", "S1")[0].data
        self.assertEqual((adequacy["outcome"], adequacy["owner"], adequacy["may_block"], adequacy["developer_chargeable"]),
                         ("INCOMPLETE", None, False, False))
        self.assertEqual(adequacy["regressions"]["selection"], "STORY_TESTS_NOT_COLLECTABLE")
        self.assertEqual(adequacy["regressions"]["owner_on_failure"], "INTEGRATION")
        self.assertEqual(self.failures("S1"), [])
        self.assertTrue(r.committed)
        self.assertEqual(self.run.state(P.BUDGETS)["retries"], {})

    def test_ORCH_SCHEMA_7_a_review_request_charges_the_REVIEW_budget_and_blocks_only_with_corroboration(self):
        advisory = Rev([Finding("style", True, ())])                       # a model review alone: never the sole authority
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), reviewer=advisory)
        self.assertTrue(r.committed)
        b = self.run.state(P.BUDGETS)
        self.assertEqual(b["review"], {"S1": {"requests": 1, "criteria": {"C1": 1}}})
        self.assertEqual(b["developer"]["S1"]["requests"], 1)
        row = next(e for e in self.events("gate/check") if e.data["check"] == "S1:review:style")
        self.assertEqual((row.data["passed"], "sole blocking authority" in row.data["detail"]), (True, True))
        request = next(e for e in self.events("provider/request", "S1") if e.data["budget_owner"] == "REVIEW")
        self.assertEqual(list(request.data["criteria"]), ["C1"])

    def test_ORCH_SCHEMA_7b_a_corroborated_review_finding_is_REVIEW_FINDING_owned_by_REVIEW(self):
        corroborated = Rev([Finding("sql-injection", True, ("scanner:bandit", "human:owner"))])
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), reviewer=corroborated, limits={**LIMITS, Owner.REVIEW: 0})
        self.assertEqual(self.failures("S1"), [("REVIEW_FINDING", "REVIEW", True)])
        self.assertEqual(self.details("S1"), ["review: REVIEW_FINDING"])
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])
        self.assertEqual(self.run.state(P.BUDGETS)["review"]["S1"]["requests"], 1)
        self.assertEqual(self.events("tool/invoked", "S1"), [])                # security never ran: review stopped the story

    def test_ORCH_7_and_SCHEMA_8_a_scanner_that_ran_and_found_is_EXECUTED_and_SECURITY_FINDING(self):
        finding = Scan(self.script, [Finding("hardcoded-secret", True, ("scanner:scan",))])
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), scanner=finding, limits={**LIMITS, Owner.SECURITY: 1})
        self.assertEqual(self.failures("S1"), [("SECURITY_FINDING", "SECURITY", True)] * 2)
        self.assertEqual(self.details("S1"), ["security: SECURITY_FINDING"] * 2)
        self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "ROLLBACK"])
        self.assertEqual(self.run.state(P.BUDGETS)["retries"], {"S1": {"SECURITY": 1}})
        results = self.events("tool/result", "S1")
        self.assertEqual([e.data["outcome"] for e in results], ["COMPLETED", "COMPLETED"])   # ran and found: EXECUTED
        row = next(e for e in self.events("gate/check") if e.data["check"] == "S1:security:hardcoded-secret")
        self.assertFalse(row.data["passed"])

    def test_ORCH_6_and_SCHEMA_9_a_reviewer_environment_failure_is_CAPABILITY_UNRUNNABLE_ENVIRONMENT_never_DEVELOPER(self):
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), reviewer=Rev(unrunnable=True), limits={**LIMITS, Owner.ENVIRONMENT: 0})
        self.assertEqual(self.failures("S1"), [("CAPABILITY_UNRUNNABLE", "ENVIRONMENT", True)])
        self.assertEqual(self.events("provider/result", "S1")[-1].data["outcome"], "FAILED")
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])

    def test_ORCH_2b_a_reviewer_outage_stays_PROVIDER(self):
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), reviewer=Rev(outage=True), limits={**LIMITS, Owner.PROVIDER: 0})
        self.assertEqual(self.failures("S1"), [("PROVIDER_UNAVAILABLE", "PROVIDER", True)])
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])

    def test_ORCH_SCHEMA_10_a_resource_that_cannot_be_acquired_is_RESOURCE_ACQUISITION_FAILED(self):
        class NoRoom(GitWorkspace):
            def checkout(self, name, revision):
                raise ResourceUnavailable(f"checkout {name}: no disk")
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), workspace=NoRoom(self.repo, self.tmp / "ws"),
                       limits={**LIMITS, Owner.ENVIRONMENT: 0})
        self.assertEqual(self.failures("S1"), [("RESOURCE_ACQUISITION_FAILED", "ENVIRONMENT", True)])
        self.assertEqual(self.details("S1"), ["resources: checkout wt-S1: no disk"])
        self.assertEqual(self.rows("S1"), [("S1:resources", False, "resources: checkout wt-S1: no disk")])
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])
        self.assertEqual(self.events("provider/request", "S1"), [])
        self.assert_disposed("S1")

    def test_ORCH_SCHEMA_10b_a_checkout_that_cannot_reach_the_candidate_is_RESOURCE_ACQUISITION_FAILED(self):
        class NoMove(GitWorkspace):
            def move(self, checkout, revision):
                raise ResourceUnavailable(f"checkout {checkout.name} to {revision[:12]}: no room")
        dev = self.s1_dev()
        r = self.story(self.s1_plan(), "S1", dev, workspace=NoMove(self.repo, self.tmp / "ws"),
                       limits={**LIMITS, Owner.ENVIRONMENT: 0})
        self.assertEqual(self.failures("S1"), [("RESOURCE_ACQUISITION_FAILED", "ENVIRONMENT", True)])
        self.assertEqual(self.details("S1"), [f"candidate checkout: checkout wt-S1 to {dev.candidates[0][:12]}: no room"])
        self.assertEqual(self.rows("S1")[-1], ("S1:candidate", False, f"candidate checkout: checkout wt-S1 to {dev.candidates[0][:12]}: no room"))
        self.assertEqual((len(self.events("proof/verified", "S1")), [a.outcome for a in r.attempts]), (0, ["ROLLBACK"]))
        self.assertEqual(self.merger.base(), self.base)
        self.assert_disposed("S1")

    def test_ORCH_SCHEMA_10c_a_checkout_that_cannot_reach_the_merged_revision_reverts_the_merge(self):
        moves = []

        class NoMoveAfterMerge(GitWorkspace):
            def move(self, checkout, revision):
                moves.append(revision)
                if len(moves) > 2:                                       # the two moves to the candidate succeed
                    raise ResourceUnavailable(f"checkout {checkout.name} to {revision[:12]}: no room")
                super().move(checkout, revision)
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), workspace=NoMoveAfterMerge(self.repo, self.tmp / "ws"),
                       limits={**LIMITS, Owner.ENVIRONMENT: 0})
        merged = moves[2]
        self.assertEqual(self.failures("S1"), [("RESOURCE_ACQUISITION_FAILED", "ENVIRONMENT", True)])
        self.assertEqual(self.details("S1"), [f"merged checkout: checkout wt-S1 to {merged[:12]}: no room"])
        self.assertEqual(self.rows("S1")[-2:], [("S1:merge", True, f"merged at {merged}"),
                                                ("S1:post-merge", False, f"merged checkout: checkout wt-S1 to {merged[:12]}: no room")])
        self.assertEqual(self.merger.base(), self.base)                  # the merge was reverted
        self.assertEqual((len(self.events("proof/verified", "S1")), [a.outcome for a in r.attempts]), (1, ["ROLLBACK"]))
        self.assert_disposed("S1")

    def test_ROOT_tier_arms_I_to_IX_and_the_static_rules_hold_over_the_package(self):
        from aisef2.invariants.registry import Tier, armed
        self.assertEqual(set(armed()[Tier.ROOT]), set(__import__("aisef2.arch.enums", fromlist=["InvariantId"]).InvariantId))
        import importlib.util
        for name, rel in (("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py"),
                          ("aisef_v2_except_boundaries", "validation/v2/except_boundaries.py")):
            if name not in sys.modules:
                s = importlib.util.spec_from_file_location(name, ROOT / rel)
                m = importlib.util.module_from_spec(s)
                sys.modules[name] = m
                s.loader.exec_module(m)
        ks, eb = sys.modules["aisef_v2_kernel_static_checks"], sys.modules["aisef_v2_except_boundaries"]
        self.assertEqual(ks.check(ROOT), [])
        audit = eb.audit(ROOT)
        self.assertEqual(audit["problems"], [])
        self.assertTrue(any(b["path"].startswith("aisef2/orchestrate/") for b in audit["boundaries"]))
        with self.assertRaises(InvariantError):
            sr.run_story(self.run, self.s1_plan(), "S9", self.inputs("S9"), self.adapters(Dev()),
                         sr.Policy(LIMITS, TestsPolicy(True)))


if __name__ == "__main__":
    unittest.main()
