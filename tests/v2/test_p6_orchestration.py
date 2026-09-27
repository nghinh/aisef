"""WP-6.2 — the single authoritative orchestration path, end to end and adversarially (ORCH-1..16), and the typed
states ARCHITECTURE-EXCEPTION-V2-005 gave it (ORCH-SCHEMA-1..10).

Every story here runs the real path: a real git repository and worktrees, the real python_callable probe for both
parties, WP-5's real test runners at the candidate, the real merger, a RunScope writing journal format 3 — with
typed test doubles only where the path meets a capability (the developer, the reviewer, the scanner). Nothing is
asserted from prose; every claim is read from the journal and its six projections.
"""

import hashlib
import importlib.util
import inspect
import json
import marshal
import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

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
from aisef2.orchestrate import adapters, merge as mg, seam, story_runner as sr  # noqa: E402
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
                 fail: bool = False, outage: bool = False, unchanged: bool = False, before_commit=None) -> None:
        self.files, self.on_trunk, self.repo, self.fail, self.outage = files or {}, on_trunk, repo, fail, outage
        self.unchanged = unchanged   # answers with the checkout's own revision: a candidate without a change
        self.before_commit = before_commit   # called with the checkout after the files are written, before the commit
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
        if self.before_commit is not None:
            self.before_commit(checkout)
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


# ------------------------------------------ P7-FINDING-001: diagnostic instrumentation (observational, owner §1-§3)

REAL_PROVE = sr.prove


def _pyc_header(data: bytes) -> dict:
    """The 16-byte header of a timestamp-based .pyc: the interpreter takes the bytecode for a source whose mtime (whole
    seconds) and size equal the header's (importlib._bootstrap_external._validate_timestamp_pyc)."""
    magic, flags, mtime, size = struct.unpack("<4sIII", data[:16])
    return {"magic_current": magic == importlib.util.MAGIC_NUMBER, "flags": flags, "source_mtime": mtime, "source_size": size}


def _shape(co):
    """A code object by what it does — its bytecode and, recursively, its constants — never by filename or line."""
    return (co.co_code, tuple(_shape(c) if isinstance(c, types.CodeType) else c for c in co.co_consts))


def _worktree_head(root: str) -> str:
    """A detached worktree's HEAD, read from its own HEAD file (no process is started before a proof)."""
    dotgit = pathlib.Path(root, ".git")
    try:
        gitdir = dotgit.read_text(encoding="utf-8").strip().removeprefix("gitdir: ") if dotgit.is_file() else str(dotgit)
        return pathlib.Path(gitdir, "HEAD").read_text(encoding="utf-8").strip()
    except OSError as e:
        return f"unreadable: {e}"


def checkout_facts(root: str, spec) -> dict:
    """What one checkout holds for the module a spec's locator names, read without running anything: HEAD, the
    source's mtime and size, and the bytecode beside it — its header, whether the interpreter would take it for this
    source (`bytecode_valid_for_source`: header mtime and size equal the source's, at one-second resolution), and
    whether it was compiled from this source at all (`bytecode_stale`: the code it holds is not the source's)."""
    module = spec.probe_input["subject"]["locator"].partition(":")[0]
    src = pathlib.Path(root, *module.split("."))
    src = src / "__init__.py" if src.is_dir() else src.with_suffix(".py")
    facts = {"root": root, "head": _worktree_head(root), "source": str(src.relative_to(root)) if src.exists() else None}
    if not src.exists():
        return facts
    st = src.stat()
    text = src.read_text(encoding="utf-8")
    facts.update(source_mtime_ns=st.st_mtime_ns, source_mtime_s=int(st.st_mtime) & 0xFFFFFFFF, source_size=st.st_size,
                 source_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
    pyc = pathlib.Path(importlib.util.cache_from_source(str(src)))
    facts["bytecode"] = str(pyc.relative_to(root)) if pyc.exists() else None
    if pyc.exists():
        data = pyc.read_bytes()
        header = _pyc_header(data)
        valid = (header["magic_current"] and header["flags"] == 0 and header["source_mtime"] == facts["source_mtime_s"]
                 and header["source_size"] == (st.st_size & 0xFFFFFFFF))
        try:
            stale = _shape(marshal.loads(data[16:])) != _shape(compile(text, str(src), "exec"))
        except Exception as e:  # noqa: BLE001 — bytecode this interpreter cannot read is reported as such, not decoded
            stale = f"undecodable: {type(e).__name__}"
        facts.update(bytecode_header=header, bytecode_sha256=hashlib.sha256(data).hexdigest(),
                     bytecode_valid_for_source=valid, bytecode_stale=stale)
    return facts


def _reads_stale(facts: dict) -> bool:
    return bool(facts.get("bytecode_valid_for_source")) and facts.get("bytecode_stale") is True


def predicted_divergence(before: dict) -> dict:
    """What the two checkouts' facts imply for the proof: a party whose checkout holds bytecode the interpreter takes
    for the source, compiled from another source, observes that other source's behaviour."""
    a, b = _reads_stale(before["implementer"]), _reads_stale(before["verifier"])
    return {"implementer_reads_stale_bytecode": a, "verifier_reads_stale_bytecode": b, "divergence": a != b}


def _party_view(record: dict) -> dict:
    result = record["result"]
    executed = "behavior_verdict" in result
    return {"execution_status": "EXECUTED" if executed else "NOT_EXECUTED (Unrunnable or InvalidSpec: the sealed record carries its detail)",
            "behavior_verdict": result.get("behavior_verdict"), "reason": result.get("reason"), "detail": result.get("detail"),
            "revision": record["revision"], "record_digest": record["record_digest"], "enforcement": record["enforcement"],
            "probe_id": record["probe_id"], "probe_digest": record["probe_digest"], "semantic_hash": record["semantic_hash"],
            "spec_id": record["spec_id"]}


def _bytes_of(root: str, *args: str) -> bytes:
    return subprocess.run(["git", "-C", root, *args], capture_output=True).stdout


def disagreement_evidence(run, plan, entry: dict, scope_held: tuple) -> dict:
    """Owner §2: everything already recorded that reconstructs a divergence, typed, from the journal and the two
    checkouts — no prose diagnosis."""
    events = run.events
    story, cid = entry["story_id"], entry["criterion_id"]
    a, b = (events[s].data["record"] for s in (entry["implementer_seq"], entry["verifier_seq"]))
    instrument = ("probe_id", "probe_digest", "enforcement", "semantic_hash")
    begin = max(e.seq for e in events if e.type == "story/begin" and e.data["story_id"] == story)
    last = events[-1].seq
    checks = [(e.seq, e.data["check"], e.data["passed"], e.data["detail"]) for e in events
              if e.type == "gate/check" and e.data["check"].startswith(story + ":")]
    committed = frozenset(e.data["story_id"] for e in events if e.type == "story/commit")
    tag = f"{cid}/{entry['point']}"
    ranges = [(e.seq, e.type, e.data["resource"]) for e in events
              if e.type in ("story/resource-acquired", "story/resource-released") and e.data.get("story_id") == story
              and e.data.get("kind") == "PROCESS_RANGE" and tag in e.data["resource"]]
    journal = pathlib.Path(run.journal_path)
    lines = journal.read_bytes().splitlines(keepends=True) if journal.exists() else []
    checkouts = {}
    for party in ("implementer", "verifier"):
        root = entry["before"][party]["root"]
        checkouts[party] = {"name": pathlib.Path(root).name, "root": root, "head": _worktree_head(root),
                            "status_porcelain": _bytes_of(root, "status", "--porcelain").decode("utf-8", "replace"),
                            "before": entry["before"][party], "after": entry["after"][party]}
    bytecode_at_revision = []
    for ln in _bytes_of(entry["before"]["implementer"]["root"], "ls-tree", "-r", entry["candidate"]).decode().splitlines():
        mode, kind, blob, path = ln.split(maxsplit=3)
        if path.endswith(".pyc"):
            data = _bytes_of(entry["before"]["implementer"]["root"], "cat-file", "blob", blob)
            bytecode_at_revision.append({"path": path, "blob": blob, "header": _pyc_header(data), "sha256": hashlib.sha256(data).hexdigest()})
    return {
        "finding": "P7-FINDING-001", "story_id": story, "criterion_id": cid, "spec_id": entry["spec_id"],
        "semantic_hash": a["semantic_hash"], "probe_id": a["probe_id"], "probe_digest": a["probe_digest"],
        "measurement_point": entry["point"], "revision": entry["candidate"],
        "implementer": _party_view(a), "verifier": _party_view(b),
        "instrument_identical": all(a[k] == b[k] for k in instrument), "results_equal": a["result"] == b["result"],
        "proof_failure": entry["failure"],
        "probe_evaluated_seqs": [entry["implementer_seq"], entry["verifier_seq"]], "proof_verified_seq": entry["verified_seq"],
        "proof_verified": dict(events[entry["verified_seq"]].data) if entry["verified_seq"] is not None else None,
        "gate_checks": checks, "affected_preserve": {k: list(v) for k, v in mg.affected_preserve(plan, story, committed).items()},
        "committed_stories": sorted(committed), "attempt": run.state(P.STORY_STATE)[story]["attempt"],
        "scope_held_at_capture": list(scope_held), "event_seq_interval": [begin, last],
        "journal_path": str(journal), "journal_prefix_lines": last + 1,
        "journal_prefix_sha256": hashlib.sha256(b"".join(lines[:last + 1])).hexdigest(),
        "process_ranges": ranges, "checkouts": checkouts, "bytecode_at_revision": bytecode_at_revision,
        "predicted_divergence": entry["predicted_divergence"],
    }


class ProofObserver:
    """The instrumentation the owner's P7-FINDING-001 diagnostic authorized (§1-§3): observational only. Wraps the
    real `prove` where the story runner and the merge module call it; before each proof it reads what the two
    checkouts hold for the spec's module (`checkout_facts`), and after `prove` has returned — its decision made — it
    records the proof and, on a disagreement or a mismatch, assembles the typed evidence (`disagreement_evidence`).
    No argument, timeout, ordering, process lifetime or result is touched; nothing here reaches the decision."""

    def __init__(self, run, plan) -> None:
        self.run, self.plan, self.proofs, self.disagreements = run, plan, [], []
        self.story_failures: dict = {}

    def __enter__(self):
        self._patches = [mock.patch.object(sr, "prove", self._prove), mock.patch.object(mg, "prove", self._prove)]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        for e in self.run.events:
            if e.type == "failure/observed":
                self.story_failures.setdefault(e.data["story_id"], []).append((e.data["code"], e.data["owner"], e.data["retryable"], e.data["detail"]))
        return False

    def _prove(self, run, story_id, criterion_id, spec, role, *, implementer, verifier, candidate, implementer_root,
               verifier_root, env, point):
        before = {"implementer": checkout_facts(implementer_root, spec), "verifier": checkout_facts(verifier_root, spec)}
        p = REAL_PROVE(run, story_id, criterion_id, spec, role, implementer=implementer, verifier=verifier, candidate=candidate,
                       implementer_root=implementer_root, verifier_root=verifier_root, env=env, point=point)
        entry = {"story_id": story_id, "criterion_id": criterion_id, "spec_id": spec.id, "point": point.value,
                 "candidate": candidate, "agreement": p.agreement, "failure": p.failure.code.value if p.failure else None,
                 "implementer_seq": p.implementer_seq, "verifier_seq": p.verifier_seq, "verified_seq": p.verified_seq,
                 "before": before, "predicted_divergence": predicted_divergence(before)}
        self.proofs.append(entry)
        if not p.agreement:
            entry["after"] = {"implementer": checkout_facts(implementer_root, spec), "verifier": checkout_facts(verifier_root, spec)}
            self.disagreements.append(disagreement_evidence(run, self.plan, entry, tuple(implementer.scope.held)))
        return p

    def report(self) -> str:
        """For an assertion message: every disagreement's evidence and every proof's facts, between markers a CI log
        hands back (validation/qualification/diag_orch9.py reads the same)."""
        body = json.dumps({"disagreements": self.disagreements, "proofs": self.proofs, "story_failures": self.story_failures},
                          sort_keys=True, default=str)
        return f"\n===AISEF-DIAG-EVIDENCE===\n{body}\n===AISEF-DIAG-END===\n"


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

    def assertAttempts(self, result, outcomes):
        """The attempt outcomes — and, when they differ, every failure the journal holds for the story (its code and
        detail), so a run on another machine says why."""
        story = result.story_id
        self.assertEqual([a.outcome for a in result.attempts], outcomes,
                         f"failures of {story}: {self.failures(story)} {self.details(story)}")

    def details(self, story):
        return [e.data["detail"] for e in self.events("failure/observed", story)]

    def proofs(self, story):
        """Every proof of the story with the two cited probe records' results: what a disagreement looked like, on
        any machine."""
        return [(e.data["criterion_id"], e.data["agreement"],
                 [(self.run.events[s].data["record"]["revision"][:7], self.run.events[s].data["record"]["result"]) for s in e.source_seqs])
                for e in self.events("proof/verified", story)]

    def assertCommitted(self, result):
        """The story committed — and if not, every failure and every proof record the journal holds for it."""
        story = result.story_id
        self.assertTrue(result.committed, f"{story} not committed: failures {self.failures(story)} {self.details(story)}; "
                                          f"proofs {self.proofs(story)}")

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
        self.assertCommitted(r)
        self.assertEqual(r.revision, self.merger.base())         # the merge landed on main
        self.assertNotEqual(r.revision, self.base)
        self.assertAttempts(r, ["COMMIT"])
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
        self.assertCommitted(r)
        legacy = seam.resolve("C1", "CHANGE_REQUIRED", table, SubjectAbsence.REQUIRES_SUBJECT)
        self.assertEqual((legacy.role, legacy.polarity, legacy.subject_absence),
                         (ObligationRole.INTRODUCE, Polarity.MUST_HOLD, SubjectAbsence.REQUIRES_SUBJECT))

    def test_ORCH_14_a_change_of_engineering_adequacy_leaves_the_product_proof_unchanged(self):
        # the product proof passes while the developer's own test is wrong: INADEQUATE, DEVELOPER — only the policy blocks
        dev = Dev({"app/calc.py": CALC + ADD, "tests/test_s1.py": TEST_ADD_WRONG})
        r = self.story(self.s1_plan(), "S1", dev, tests_block=False)
        self.assertCommitted(r)
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
        self.assertCommitted(r)

    def test_ORCH_8_and_SCHEMA_3_a_merge_conflict_is_MERGE_CONFLICT_INTEGRATION_with_zero_developer_charge(self):
        dev = self.s1_dev(on_trunk={"app/calc.py": CALC + "\n\ndef add(a, b):\n    return b + a\n"}, repo=self.repo)
        r = self.story(self.s1_plan(), "S1", dev)
        self.assertFalse(r.committed)
        self.assertEqual(self.failures("S1"), [("MERGE_CONFLICT", "INTEGRATION", False)])
        self.assertEqual(self.details("S1"), ["merge: MERGE_CONFLICT"])
        self.assertAttempts(r, ["ROLLBACK"])
        self.assertEqual(self.run.state(P.BUDGETS)["retries"], {})
        merge_check = next(e for e in self.events("gate/check") if e.data["check"] == "S1:merge")
        self.assertEqual((merge_check.data["passed"], "app/calc.py" in merge_check.data["detail"]), (False, True))
        self.assert_disposed("S1")

    def test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back(self):
        plan = plan_of(self.base, obligation("C1", self.s1.id, "S0", ObligationRole.INTRODUCE),
                       obligation("C0", self.s0.id, "S0", ObligationRole.PRESERVE),
                       obligation("C2", self.s2.id, "S2", ObligationRole.INTRODUCE))
        with ProofObserver(self.run, plan) as seen:   # P7-FINDING-001: observed; the messages below carry its evidence
            r0 = self.story(plan, "S0", self.s1_dev(), inputs=self.inputs("S0"))
            self.assertTrue(r0.committed, seen.report())
            self.assertEqual([e.data["check"] for e in self.events("gate/check") if e.data["check"].startswith("S0:post")],
                             ["S0:post-merge:C1", "S0:post-merge:C0"])
            tip = self.merger.base()
            breaking = Dev({"app/mul.py": MUL, "tests/test_s2.py": TEST_MUL,
                            "app/calc.py": "def sub(a, b):\n    return a + b\n"})       # breaks S0's preserved behaviour
            r2 = self.story(plan, "S2", breaking, inputs=self.inputs("S2", tests=("tests/test_s2.py",), regressions=("tests/test_other.py",)),
                            tests_block=False)
        self.observed = seen   # read back by validation/qualification/diag_orch9.py after the case ran
        self.assertFalse(r2.committed, seen.report())
        codes = self.failures("S2")
        self.assertEqual(codes, [("POST_MERGE_REGRESSION", "INTEGRATION", False)], seen.report())
        self.assertEqual(self.details("S2"), ["post-merge C0: POST_MERGE_REGRESSION"], seen.report())
        self.assertEqual(self.merger.base(), tip)           # the merge was rolled back
        checks = [(e.data["check"], e.data["passed"]) for e in self.events("gate/check") if e.data["check"].startswith("S2:post")]
        self.assertEqual(checks, [("S2:post-merge:C2", True), ("S2:post-merge:C0", False)])   # the prior story's PRESERVE, re-proved
        self.assertAttempts(r2, ["ROLLBACK"])
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
        self.assertCommitted(r)

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
        self.assertAttempts(r, ["RETRY", "COMMIT"])
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
        self.assertAttempts(r, ["RETRY", "ROLLBACK"])   # PROVIDER limit 1: one retry, then no
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
        self.assertAttempts(r, ["ROLLBACK"])
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
        self.assertCommitted(r)
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
        self.assertAttempts(r, ["RETRY", "COMMIT"])
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
        self.assertAttempts(r, ["ROLLBACK"])
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
        self.assertAttempts(r, ["ROLLBACK"])

    def test_ORCH_SCHEMA_4_tests_that_cannot_run_are_TESTS_UNRUNNABLE_with_no_developer_charge(self):
        absent = te.Runner("absent", ("-m", "aisef2_no_such_runner", "{out}"), te._read_unittest)
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), inputs=self.inputs("S1", runner=absent))
        self.assertEqual(self.failures("S1"), [("TESTS_UNRUNNABLE", "ENVIRONMENT", True)] * 2)
        self.assertEqual(self.details("S1"), ["engineering quality: TESTS_UNRUNNABLE"] * 2)
        self.assertEqual([x for x in self.rows("S1") if x[0] == "S1:quality"], [("S1:quality", False, "no AdequacyOutcome")] * 2)
        self.assertAttempts(r, ["RETRY", "ROLLBACK"])
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
        self.assertAttempts(r, ["ROLLBACK"])
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
        self.assertCommitted(r)
        self.assertEqual(self.run.state(P.BUDGETS)["retries"], {})

    def test_ORCH_SCHEMA_7_a_review_request_charges_the_REVIEW_budget_and_blocks_only_with_corroboration(self):
        advisory = Rev([Finding("style", True, ())])                       # a model review alone: never the sole authority
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), reviewer=advisory)
        self.assertCommitted(r)
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
        self.assertAttempts(r, ["ROLLBACK"])
        self.assertEqual(self.run.state(P.BUDGETS)["review"]["S1"]["requests"], 1)
        self.assertEqual(self.events("tool/invoked", "S1"), [])                # security never ran: review stopped the story

    def test_ORCH_7_and_SCHEMA_8_a_scanner_that_ran_and_found_is_EXECUTED_and_SECURITY_FINDING(self):
        finding = Scan(self.script, [Finding("hardcoded-secret", True, ("scanner:scan",))])
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), scanner=finding, limits={**LIMITS, Owner.SECURITY: 1})
        self.assertEqual(self.failures("S1"), [("SECURITY_FINDING", "SECURITY", True)] * 2)
        self.assertEqual(self.details("S1"), ["security: SECURITY_FINDING"] * 2)
        self.assertAttempts(r, ["RETRY", "ROLLBACK"])
        self.assertEqual(self.run.state(P.BUDGETS)["retries"], {"S1": {"SECURITY": 1}})
        results = self.events("tool/result", "S1")
        self.assertEqual([e.data["outcome"] for e in results], ["COMPLETED", "COMPLETED"])   # ran and found: EXECUTED
        row = next(e for e in self.events("gate/check") if e.data["check"] == "S1:security:hardcoded-secret")
        self.assertFalse(row.data["passed"])

    def test_ORCH_6_and_SCHEMA_9_a_reviewer_environment_failure_is_CAPABILITY_UNRUNNABLE_ENVIRONMENT_never_DEVELOPER(self):
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), reviewer=Rev(unrunnable=True), limits={**LIMITS, Owner.ENVIRONMENT: 0})
        self.assertEqual(self.failures("S1"), [("CAPABILITY_UNRUNNABLE", "ENVIRONMENT", True)])
        self.assertEqual(self.events("provider/result", "S1")[-1].data["outcome"], "FAILED")
        self.assertAttempts(r, ["ROLLBACK"])

    def test_ORCH_2b_a_reviewer_outage_stays_PROVIDER(self):
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), reviewer=Rev(outage=True), limits={**LIMITS, Owner.PROVIDER: 0})
        self.assertEqual(self.failures("S1"), [("PROVIDER_UNAVAILABLE", "PROVIDER", True)])
        self.assertAttempts(r, ["ROLLBACK"])

    def test_ORCH_SCHEMA_10_a_resource_that_cannot_be_acquired_is_RESOURCE_ACQUISITION_FAILED(self):
        class NoRoom(GitWorkspace):
            def checkout(self, name, revision):
                raise ResourceUnavailable(f"checkout {name}: no disk")
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), workspace=NoRoom(self.repo, self.tmp / "ws"),
                       limits={**LIMITS, Owner.ENVIRONMENT: 0})
        self.assertEqual(self.failures("S1"), [("RESOURCE_ACQUISITION_FAILED", "ENVIRONMENT", True)])
        self.assertEqual(self.details("S1"), ["resources: checkout wt-S1: no disk"])
        self.assertEqual(self.rows("S1"), [("S1:resources", False, "resources: checkout wt-S1: no disk")])
        self.assertAttempts(r, ["ROLLBACK"])
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

    # ---- P7-FINDING-001: the mechanism, measured (owner's diagnostic authorization §5-§7, §10)

    def orch_9_plan(self):
        return plan_of(self.base, obligation("C1", self.s1.id, "S0", ObligationRole.INTRODUCE),
                       obligation("C0", self.s0.id, "S0", ObligationRole.PRESERVE),
                       obligation("C2", self.s2.id, "S2", ObligationRole.INTRODUCE))

    def orch_9_breaking(self, **kw):
        return Dev({"app/mul.py": MUL, "tests/test_s2.py": TEST_MUL, "app/calc.py": "def sub(a, b):\n    return a + b\n"}, **kw)

    def bytecode_blob(self, revision: str, module: str) -> bytes:
        path = f"app/__pycache__/{module}.{sys.implementation.cache_tag}.pyc"
        return subprocess.run(["git", "-C", self.repo, "cat-file", "blob", f"{revision}:{path}"], capture_output=True).stdout

    def test_DIAG_1_the_merged_revision_of_S0_carries_bytecode_the_observation_wrote_and_the_developer_committed(self):
        """Measured, not assumed: S0's admission probes ran the harness in wt-S0 under `-I`, which discards the
        PYTHONDONTWRITEBYTECODE=1 the kernel sets, so importing app.calc wrote app/__pycache__/calc.*.pyc into the
        checkout; the developer's `git add -A` committed it; the merge kept it. The revision then holds bytecode of
        CALC (32 bytes) beside a source of CALC + ADD (66 bytes): stale, and not valid for that source."""
        plan = self.orch_9_plan()
        with ProofObserver(self.run, plan) as seen:
            r0 = self.story(plan, "S0", self.s1_dev(), inputs=self.inputs("S0"))
        self.assertTrue(r0.committed, seen.report())
        merged = self.merger.base()
        tag = sys.implementation.cache_tag
        tree = git(self.repo, "ls-tree", "-r", "--name-only", merged).stdout.split()
        self.assertEqual(sorted(p for p in tree if "__pycache__" in p),
                         [f"app/__pycache__/__init__.{tag}.pyc", f"app/__pycache__/calc.{tag}.pyc"])
        blob = self.bytecode_blob(merged, "calc")
        self.assertEqual(git(self.repo, "show", f"{merged}:app/calc.py").stdout, CALC + ADD)
        self.assertEqual(_pyc_header(blob)["source_size"], len(CALC.encode("utf-8")))
        self.assertEqual(_shape(marshal.loads(blob[16:])), _shape(compile(CALC, "app/calc.py", "exec")))
        self.assertNotEqual(_shape(marshal.loads(blob[16:])), _shape(compile(CALC + ADD, "app/calc.py", "exec")))
        p = subprocess.run([sys.executable, "-I", "-c", "import sys; print(sys.dont_write_bytecode)"],
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), "False")   # -I discards the variable the harness environment sets
        # before the first proof at each revision (C1) both checkouts held the committed bytecode — stale, never valid
        # for the 66-byte source; before the second (C0) each held bytecode of the source, fresh and valid: the C1
        # proof's harness compiled it and wrote it into the checkout it observed
        for e in seen.proofs:
            for party in ("implementer", "verifier"):
                f = e["before"][party]
                self.assertEqual((f["bytecode_stale"], f["bytecode_valid_for_source"]),
                                 (True, False) if e["criterion_id"] == "C1" else (False, True), (e["criterion_id"], e["point"], party, f))

    def test_DIAG_2_a_developer_file_dated_to_the_committed_bytecode_splits_the_two_parties_at_one_merged_revision(self):
        """The mechanism, constructed — a product-state construction, no timing change: S2's developer writes
        app/calc.py (32 bytes, the size the committed bytecode's source had) dated to that bytecode's header second,
        and commits (the index records that date, so the kernel's forced checkouts leave the file alone, as they leave
        any file whose stat matches). The implementer's checkout is the developer's, so the interpreter takes the
        bytecode: sub(3, 1) == 2, SATISFIED; the verifier's own checkout dates the file at its checkout, so it compiles
        the source: 4, REFUTED. Same spec, same semantic hash, same probe digest, same enforcement, same merged revision
        in both checkouts — VERIFIER_DISAGREEMENT at post-merge C0, rolled back: P7-FINDING-001's symptom, from a
        revision that carries bytecode of another source."""
        plan = self.orch_9_plan()
        with ProofObserver(self.run, plan) as seen:
            r0 = self.story(plan, "S0", self.s1_dev(), inputs=self.inputs("S0"))
            self.assertTrue(r0.committed, seen.report())
            tip = self.merger.base()
            second = _pyc_header(self.bytecode_blob(tip, "calc"))["source_mtime"]
            dated = self.orch_9_breaking(before_commit=lambda checkout: os.utime(pathlib.Path(checkout, "app", "calc.py"), (second, second)))
            r2 = self.story(plan, "S2", dated,
                            inputs=self.inputs("S2", tests=("tests/test_s2.py",), regressions=("tests/test_other.py",)), tests_block=False)
        self.assertFalse(r2.committed, seen.report())
        self.assertEqual(self.failures("S2"), [("VERIFIER_DISAGREEMENT", "INTEGRATION", False)], seen.report())
        self.assertEqual(self.details("S2"), ["post-merge C0: VERIFIER_DISAGREEMENT"], seen.report())
        self.assertEqual(self.merger.base(), tip)
        self.assertAttempts(r2, ["ROLLBACK"])
        [ev] = seen.disagreements
        self.assertEqual((ev["criterion_id"], ev["measurement_point"], ev["proof_failure"]), ("C0", "POST_MERGE", "VERIFIER_DISAGREEMENT"))
        self.assertEqual((ev["implementer"]["behavior_verdict"], ev["verifier"]["behavior_verdict"]), ("SATISFIED", "REFUTED"))
        self.assertEqual((ev["implementer"]["execution_status"], ev["verifier"]["execution_status"]), ("EXECUTED", "EXECUTED"))
        self.assertTrue(ev["instrument_identical"])
        self.assertEqual({ev["revision"], ev["implementer"]["revision"], ev["verifier"]["revision"],
                          ev["checkouts"]["implementer"]["head"], ev["checkouts"]["verifier"]["head"]}, {ev["revision"]})
        self.assertEqual(ev["predicted_divergence"], {"implementer_reads_stale_bytecode": True, "verifier_reads_stale_bytecode": False, "divergence": True})
        before = ev["checkouts"]["implementer"]["before"]
        self.assertEqual((before["source_mtime_s"], before["bytecode_header"]["source_mtime"], before["bytecode_valid_for_source"], before["bytecode_stale"]),
                         (second, second, True, True))
        before = ev["checkouts"]["verifier"]["before"]
        self.assertEqual((before["bytecode_valid_for_source"], before["bytecode_stale"]), (False, True))
        self.assertEqual(ev["affected_preserve"], {"C0": ["S0", self.s0.id]})
        self.assertEqual([b["header"]["source_size"] for b in ev["bytecode_at_revision"] if b["path"].endswith(f"calc.{sys.implementation.cache_tag}.pyc")], [32])
        self.assertEqual(ev["proof_verified"]["agreement"], False)
        self.assertEqual(len(ev["process_ranges"]), 4)   # acquired and released, each party
        self.assert_disposed("S2")

    def test_DIAG_3_on_the_natural_path_a_proof_diverges_exactly_when_one_checkout_reads_stale_bytecode(self):
        """Owner §7 as a check: ORCH_9_and_10's flow, untouched, observed — for every proof, the divergence the two
        checkouts' pre-proof facts predict is the one the proof shows, and the story's outcome is the one the
        predictions imply. On a machine where S0's checkout and S2's developer write fall in the same second the
        prediction is a divergence (VERIFIER_DISAGREEMENT); where both checkouts read the stale bytecode S2 commits;
        elsewhere POST_MERGE_REGRESSION. Never a divergence without the difference in what the checkouts hold."""
        plan = self.orch_9_plan()
        with ProofObserver(self.run, plan) as seen:
            r0 = self.story(plan, "S0", self.s1_dev(), inputs=self.inputs("S0"))
            self.assertTrue(r0.committed, seen.report())
            r2 = self.story(plan, "S2", self.orch_9_breaking(),
                            inputs=self.inputs("S2", tests=("tests/test_s2.py",), regressions=("tests/test_other.py",)), tests_block=False)
        for e in seen.proofs:
            self.assertEqual(not e["agreement"], e["predicted_divergence"]["divergence"], seen.report())
        c0 = [e["predicted_divergence"] for e in seen.proofs if (e["story_id"], e["criterion_id"], e["point"]) == ("S2", "C0", "POST_MERGE")]
        if any(p["divergence"] for p in c0):
            self.assertEqual(self.failures("S2"), [("VERIFIER_DISAGREEMENT", "INTEGRATION", False)], seen.report())
        elif any(p["implementer_reads_stale_bytecode"] and p["verifier_reads_stale_bytecode"] for p in c0):
            self.assertTrue(r2.committed, seen.report())
        else:
            self.assertEqual(self.failures("S2"), [("POST_MERGE_REGRESSION", "INTEGRATION", False)], seen.report())


if __name__ == "__main__":
    unittest.main()
