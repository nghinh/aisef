"""Targeted REAL-KERNEL conformance for TDD proof policy V2 (owner decision 2026-09-20 §2-§4).

Phase 12's random traces compare terminal state and counters on scenarios whose fixtures set `tools.test = true`
and never write a story test file: the nop control is NOT_APPLICABLE there, so the V2 proof obligations are never
materially exercised. This module closes that gap with a small set of deterministic scenarios that drive the REAL
kernel end to end — real git project, a real `unittest` run, real `run_nop` at the parent SHA, the real gate, the real retry
and plan routing — and compares each one against a REFERENCE MODEL of the policy written from the owner decision,
not from `aisef/control/obligation.py`.

Each scenario declares, per criterion, the obligation the PLAN states and the proof state each side is built to
show. The model predicts, independently: per-AC satisfaction, failure owner, overlap, the aggregate check outcome,
the typed terminal, the next state, and whether a developer quality attempt is consumed. The real kernel's own
structured rows are read back and compared field by field — including the observed parent and candidate proof
states, so a scenario that does not produce the state it claims is a mismatch, never a silent pass.

    python3 -m tests.hardening.policy_v2 --out closure-evidence/hardening/TDD-POLICY-V2-CONFORMANCE.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from aisef.clients.base import quote_command  # noqa: E402
from aisef.clients.synthetic import Script, Step, SyntheticClientAdapter  # noqa: E402
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.normalize import Story  # noqa: E402
from aisef.control.outcome import StageOutcome  # noqa: E402
from aisef.phases.implement import implement_story  # noqa: E402

SID = "STORY-07-01"
CHECK = "tests verify story"
#: the project under test needs nothing but the interpreter — CI runs `python -m unittest discover`
TEST_COMMAND = quote_command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"])
#: a command that does not exist: the stage cannot run at all
MISSING_TOOL = "aisef-no-such-tool-xyz"
#: a tool that is absent for a whole first attempt (its baseline, candidate and nop runs) and works afterwards —
#: an environment that fails and then recovers, so the first attempt blocks on absence ALONE
FLAKY_TOOL = "FLAKY"
FLAKY_MISSING_RUNS = 3
_FLAKY_RUNNER = """import pathlib, subprocess, sys

count = pathlib.Path(__file__).with_name(".flaky_count")
n = int(count.read_text(encoding="utf-8")) if count.exists() else 0
count.write_text(str(n + 1), encoding="utf-8")
if n < 3:
    sys.stderr.write("aisef-flaky: command not found\\n")
    raise SystemExit(127)
raise SystemExit(subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"]))
"""

# ------------------------------------------------------------------ the reference model (written from the decision)
# Section 4-7 of the owner decision, as a table. Nothing here imports aisef.control.obligation: this is the second
# opinion the real kernel is measured against.
RED, GREEN, NONE = "RED", "GREEN", "NO_EVIDENCE"
PLAN, DEVELOPER, ENVIRONMENT = "PLAN", "DEVELOPER", "ENVIRONMENT"


def model_ac(mode: str, parent: str, candidate: str) -> tuple[bool, str | None, bool]:
    """(satisfied, owner, is_plan_overlap) for one criterion — the policy as the decision states it.

    CHANGE_REQUIRED  must go RED -> GREEN. Already green at the parent is PLAN_OVERLAP, owned by the PLAN (§4, §7),
                     and it must not consume a developer quality retry. A parent that shows nothing is never proof.
    PRESERVE_REQUIRED / NEGATIVE_INVARIANT  must stay GREEN -> GREEN and give no credit; green->red is a DEVELOPER
                     regression; a parent that is not green is a missing precondition, owned by the PLAN.
    """
    if mode == "CHANGE_REQUIRED":
        if parent == GREEN:
            return False, PLAN, True
        if parent != RED:                      # NO_EVIDENCE: unrunnable, not collected, aborted, absent
            return False, ENVIRONMENT, False
        return (True, None, False) if candidate == GREEN else (
            (False, ENVIRONMENT, False) if candidate == NONE else (False, DEVELOPER, False))
    if parent != GREEN:
        return False, (ENVIRONMENT if parent == NONE else PLAN), False
    return (True, None, False) if candidate == GREEN else (
        (False, ENVIRONMENT, False) if candidate == NONE else (False, DEVELOPER, False))


# ------------------------------------------------------------------ scenario vocabulary
# Each criterion kind builds one test method whose state at the PARENT (the project before the story) and at the
# CANDIDATE (the project with the story's files) is what the scenario claims. `product` is what the story writes.

@dataclass
class Crit:
    kind: str
    mode: str
    requirement: str = "FR-4"
    #: what this criterion's single test is built to show on each side
    parent: str = ""
    candidate: str = ""
    #: the SS-81 proof state the scenario intends at the parent (compared against what the kernel observed)
    parent_state: str = ""
    candidate_state: str = "GREEN_EXECUTED"


def _crit(kind: str, mode: str, **kw) -> Crit:
    spec = {
        # a behaviour the story adds: the test imports fine at the parent and fails there on the missing function
        "new": (RED, GREEN, "RED_EXECUTED", "GREEN_EXECUTED"),
        # the story adds a whole module; the parent cannot even import the test's subject
        "new_import": (RED, GREEN, "RED_COLLECTION_BOUND_TO_STORY", "GREEN_EXECUTED"),
        # already true at the parent — an upstream story owns it
        "already": (GREEN, GREEN, "GREEN_EXECUTED", "GREEN_EXECUTED"),
        # inherited behaviour the story keeps
        "keep": (GREEN, GREEN, "GREEN_EXECUTED", "GREEN_EXECUTED"),
        # inherited behaviour the story breaks
        "break": (GREEN, RED, "GREEN_EXECUTED", "RED_EXECUTED"),
        # a prohibition that holds at the parent and still holds
        "absence": (GREEN, GREEN, "GREEN_EXECUTED", "GREEN_EXECUTED"),
        # a prohibition the story violates
        "absence_broken": (GREEN, RED, "GREEN_EXECUTED", "RED_EXECUTED"),
        # the parent could not run this test at all (a dependency outside the story)
        "parent_unrunnable": (NONE, GREEN, "DEPENDENCY_UNRUNNABLE", "GREEN_EXECUTED"),
        # the parent could not collect this test's file, for a reason not bound to the story
        "parent_uncollected": (NONE, GREEN, "NOT_COLLECTED", "GREEN_EXECUTED"),
        # the behaviour the story owes: red at the parent and still red at the candidate (the developer's failure)
        "unimplemented": (RED, RED, "RED_EXECUTED", "RED_EXECUTED"),
    }[kind]
    c = Crit(kind, mode, parent=spec[0], candidate=spec[1], parent_state=spec[2], candidate_state=spec[3])
    for k, v in kw.items():
        setattr(c, k, v)
    return c


#: What the project looks like BEFORE any story (the parent SHA).
BASE_CLI = '''"""The ledger CLI."""


def main(argv=None):
    return 0


def report():
    return "ledger"
'''

#: What the story's developer session writes into `ledgerlock/cli.py`. `repair` is the new behaviour.
STORY_CLI = BASE_CLI + '''

def repair():
    return 0
'''

#: The same, but the session breaks what it inherited: `report()` no longer answers what it did (the
#: PRESERVE_REQUIRED cases) and the module now evaluates a string (the NEGATIVE_INVARIANT cases).
BROKEN_CLI = STORY_CLI.replace('return "ledger"', 'return eval("\'LEDGER\'")')

NEW_MODULE = '''def rebuild():
    return 7
'''


def _test_body(c: Crit, fn: str) -> str:
    """One test method carrying the criterion's code, built so its state is `c.parent_state` at the parent and
    green (or the declared red) at the candidate. The only difference between the two sides is the story's own
    product files. `unittest` rather than pytest: the project under test must need nothing but the interpreter,
    which is also what CI has (it runs `python -m unittest discover`)."""
    if c.kind in ("new", "unimplemented"):
        return (f"    def {fn}(self):\n        self.assertTrue(hasattr(cli, 'repair'), 'repair is not there yet')\n"
                "        self.assertEqual(cli.repair(), 0)\n")
    if c.kind == "new_import":            # imported at module level: the parent cannot even collect the file
        return f"    def {fn}(self):\n        self.assertEqual(rebuild.rebuild(), 7)\n"
    if c.kind in ("already", "keep", "parent_unrunnable", "parent_uncollected"):
        return f"    def {fn}(self):\n        self.assertEqual(cli.main(), 0)\n"
    if c.kind == "break":
        return f"    def {fn}(self):\n        self.assertEqual(cli.report(), 'ledger')\n"
    if c.kind in ("absence", "absence_broken"):        # a prohibition, not a behaviour: it must hold on both sides
        return (f"    def {fn}(self):\n        import inspect\n"
                "        self.assertNotIn('eval(', inspect.getsource(cli), 'the CLI must not evaluate strings')\n")
    raise AssertionError(c.kind)


def _test_file(c: Crit, code: str, i: int) -> tuple[str, str]:
    """(path, source) of the test file for one criterion. Guards that make the PARENT side unrunnable/uncollected are
    written so they vanish the moment the story's module exists — the file itself is identical on both sides."""
    fn = "test_" + code.replace("-", "_") + f"_{c.kind}"
    head = "import unittest\n\nfrom ledgerlock import cli\n"
    if c.kind == "new_import":
        head = "import unittest\n\nfrom ledgerlock import rebuild\n"
    elif c.kind == "parent_unrunnable":
        head = ("import importlib.util\nimport unittest\n\n"
                "if importlib.util.find_spec('ledgerlock.rebuild') is None:\n"
                "    import aisef_not_a_real_dependency_xyz  # noqa: F401\n"
                "from ledgerlock import cli\n")
    elif c.kind == "parent_uncollected":
        head = ("import importlib.util\nimport unittest\n\n"
                "if importlib.util.find_spec('ledgerlock.rebuild') is None:\n"
                "    raise RuntimeError('the parent tree cannot set this file up')\n"
                "from ledgerlock import cli\n")
    body = f"\n\nclass TestCriterion{i}(unittest.TestCase):\n" + _test_body(c, fn)
    return f"tests/test_ac_{i}.py", head + body


@dataclass
class Case:
    id: str
    title: str
    crits: list[Crit]
    story_type: str = "NORMAL"
    #: developer writes broken product code (the regression cases)
    broken: bool = False
    #: for a lifecycle case: which stage's evidence cannot be obtained ("tools" | "review" | "security")
    stage: str = "tools"
    #: for a lifecycle case with no AC rows to judge: the owner the approved policy assigns
    owner: str = ""
    #: for a plan-gate case: which deterministic gate(s) must name the defect before any model call
    plan_gates: tuple[str, ...] = ()
    #: environment knobs — a stage whose evidence cannot be obtained (the SS-96 family)
    test_tool: str = ""            # "" = the real unittest run; otherwise the command to use, or FLAKY_TOOL
    lint_tool: str = "true"
    sast_tool: str = ""
    contract: tuple[str, ...] = ()
    review_step: str = "PASS"
    security_step: str = "PASS"
    retries: int = 1
    #: the developer writes code that does NOT satisfy the criterion (a genuine quality failure)
    unimplemented: bool = False
    covers: list[str] = field(default_factory=lambda: ["FR-4"])


def obligations_of(case: Case) -> dict:
    return {f"AC-{SID}-{i}": {"ac_id": f"AC-{SID}-{i}", "proof_mode": c.mode, "requirement": c.requirement}
            for i, c in enumerate(case.crits, 1)}


# ------------------------------------------------------------------ the scenarios (owner section 2, A-N)
SCENARIOS: list[Case] = [
    Case("A", "CHANGE_REQUIRED: parent RED_EXECUTED, candidate GREEN_EXECUTED => PASS",
         [_crit("new", "CHANGE_REQUIRED")]),
    Case("B", "CHANGE_REQUIRED already green at the parent => PLAN_OVERLAP before any developer quality retry",
         [_crit("already", "CHANGE_REQUIRED")]),
    Case("C", "PRESERVE_REQUIRED: GREEN -> GREEN => PASS",
         [_crit("new", "CHANGE_REQUIRED"), _crit("keep", "PRESERVE_REQUIRED", requirement="FR-2")]),
    Case("D", "PRESERVE_REQUIRED: GREEN -> RED => DEVELOPER regression block",
         [_crit("new", "CHANGE_REQUIRED"), _crit("break", "PRESERVE_REQUIRED", requirement="FR-2")],
         broken=True),
    Case("E", "NEGATIVE_INVARIANT: GREEN -> GREEN => PASS",
         [_crit("new", "CHANGE_REQUIRED"), _crit("absence", "NEGATIVE_INVARIANT", requirement="FR-9")]),
    Case("F", "NEGATIVE_INVARIANT: GREEN -> RED => DEVELOPER regression block",
         [_crit("new", "CHANGE_REQUIRED"), _crit("absence_broken", "NEGATIVE_INVARIANT", requirement="FR-9")],
         broken=True),
    Case("G", "UNRUNNABLE parent evidence never satisfies CHANGE_REQUIRED",
         [_crit("new_import", "CHANGE_REQUIRED"), _crit("parent_unrunnable", "CHANGE_REQUIRED", requirement="FR-2")]),
    Case("H", "NOT_COLLECTED parent evidence never satisfies CHANGE_REQUIRED",
         [_crit("new_import", "CHANGE_REQUIRED"), _crit("parent_uncollected", "CHANGE_REQUIRED", requirement="FR-2")]),
    Case("I", "a mixed story: every criterion judged by its own obligation",
         [_crit("new", "CHANGE_REQUIRED"), _crit("new_import", "CHANGE_REQUIRED", requirement="FR-5"),
          _crit("keep", "PRESERVE_REQUIRED", requirement="FR-2"),
          _crit("absence", "NEGATIVE_INVARIANT", requirement="FR-9")]),
    Case("J", "CHANGE_REQUIRED green because an upstream story owns it => PLAN_OVERLAP, developer budget unchanged",
         [_crit("new", "CHANGE_REQUIRED"), _crit("already", "CHANGE_REQUIRED", requirement="FR-2")]),
    Case("K", "a normal story with zero CHANGE_REQUIRED is a plan defect, refused before the first model call",
         [_crit("keep", "PRESERVE_REQUIRED", requirement="FR-2"),
          _crit("absence", "NEGATIVE_INVARIANT", requirement="FR-9")],
         plan_gates=("machine_gate", "preflight")),
    Case("L", "a criterion whose requirement the story does not cover is a plan/readiness failure",
         [_crit("new", "CHANGE_REQUIRED", requirement="FR-77")],
         plan_gates=("machine_gate",)),
    Case("M", "a malformed proof mode is a plan/readiness failure",
         [_crit("new", "NO_SUCH_MODE")],
         plan_gates=("machine_gate", "preflight")),
    Case("N", "the gate reports every structured feedback field for each failing criterion",
         [_crit("new", "CHANGE_REQUIRED"), _crit("break", "PRESERVE_REQUIRED", requirement="FR-2")],
         broken=True),
]

# ---- the stage-lifecycle scenarios (owner decision section 7, A-I): an absence at EVERY stage that produces
# evidence, and the two controls that must still charge the developer.
SCENARIOS += [
    Case("O", "repeated NOP environment UNRUNNABLE ends on the environment, never as a quality block",
         [_crit("parent_unrunnable", "CHANGE_REQUIRED")], owner=ENVIRONMENT, stage="tools", retries=2),
    Case("P", "the test tool itself cannot run => no developer quality charge",
         [_crit("new", "CHANGE_REQUIRED")], owner=ENVIRONMENT, stage="tools", test_tool=MISSING_TOOL),
    Case("Q", "lint cannot run => no developer quality charge",
         [_crit("new", "CHANGE_REQUIRED")], owner=ENVIRONMENT, stage="tools", lint_tool=MISSING_TOOL),
    Case("R", "the reviewer did not answer => the review stage is retried, not the developer",
         [_crit("new", "CHANGE_REQUIRED")], owner=ENVIRONMENT, stage="review", review_step="UNRUNNABLE"),
    Case("S", "the security reviewer did not answer => the security stage is retried, not the developer",
         [_crit("new", "CHANGE_REQUIRED")], owner=ENVIRONMENT, stage="security", security_step="UNRUNNABLE"),
    Case("T", "a genuine behavioural failure at the candidate DOES charge the developer's quality budget",
         [_crit("unimplemented", "CHANGE_REQUIRED")], unimplemented=True, retries=1),
]

#: The cases whose verdict the PLAN gate must reach from planning data alone — no developer session at all (§8, §12).
PLAN_GATE_CASES = {"K", "L", "M"}


# ------------------------------------------------------------------ the real project

def _outcome_name(outcome) -> str:
    """The check's typed outcome as one word — PASS / FAIL / UNRUNNABLE / … Never read from wording."""
    from aisef.control.outcome import Outcome
    return {Outcome.PASSED: "PASS", Outcome.FAILED: "FAIL"}.get(outcome, getattr(outcome, "name", str(outcome)))


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


class Project:
    """A real git project at the parent SHA, with a real story worktree — the shape `run_nop` needs."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name)
        pkg = self.path / "ledgerlock"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "cli.py").write_text(BASE_CLI, encoding="utf-8")
        (self.path / "tests").mkdir()
        (self.path / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (self.path / "pyproject.toml").write_text('[project]\nname = "ledgerlock"\nversion = "0"\n', encoding="utf-8")
        _git(self.path, "init", "-q")
        _git(self.path, "config", "user.email", "t@t")
        _git(self.path, "config", "user.name", "t")
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-qm", "parent")
        self.artifacts = self.path / "_bmad-output"
        self.artifacts.mkdir()
        self.work = self.path / ".aisef" / "worktrees" / SID
        _git(self.path, "worktree", "add", "-q", str(self.work), "-b", f"story/{SID}")

    def close(self) -> None:
        subprocess.run(["git", "worktree", "remove", "--force", str(self.work)], cwd=self.path, check=False)
        self._tmp.cleanup()


def files_for(case: Case) -> dict[str, str]:
    """Everything the developer session writes: the product change and one test file per criterion."""
    out: dict[str, str] = {"ledgerlock/cli.py": BASE_CLI if case.unimplemented else
                           (BROKEN_CLI if case.broken else STORY_CLI)}
    if any(c.kind in ("new_import", "parent_unrunnable", "parent_uncollected") for c in case.crits):
        out["ledgerlock/rebuild.py"] = NEW_MODULE
    for i, c in enumerate(case.crits, 1):
        path, src = _test_file(c, f"AC-{SID}-{i}", i)
        out[path] = src
    return out


def story_for(case: Case) -> Story:
    return Story(id=SID, epic_id="EPIC-07", title="ledger repair", covers=list(case.covers),
                 acceptance_criteria=[f"criterion {i} ({c.mode})" for i, c in enumerate(case.crits, 1)],
                 write_scope=["ledgerlock", "tests"],
                 ac_proof=obligations_of(case), story_type=case.story_type)


# ------------------------------------------------------------------ running one case against the real kernel

def real_run(case: Case) -> dict:
    """Drive the real kernel and read back only TYPED facts: the check's outcome, its structured rows, the typed
    terminal, and how much developer budget the attempt consumed."""
    p = Project()
    try:
        # One developer step that repeats: a retry writes the same files again, so a scenario that must block
        # blocks on its own evidence instead of drifting into "the session wrote nothing".
        client = SyntheticClientAdapter(Script(
            developer=[Step.changed(files_for(case))],
            review=[Step(case.review_step)], security=[Step(case.security_step)]))
        test_cmd = TEST_COMMAND
        if case.test_tool == FLAKY_TOOL:
            runner = p.artifacts / "flaky_runner.py"
            runner.write_text(_FLAKY_RUNNER, encoding="utf-8")
            test_cmd = quote_command([sys.executable, str(runner)])
        elif case.test_tool:
            test_cmd = case.test_tool
        cfg = Config({**DEFAULTS, "tools.lint": case.lint_tool, "run.max_retries": case.retries,
                      "tools.test": test_cmd, "tools.sast": case.sast_tool})
        story = story_for(case)
        if case.contract:
            story.verification_contract = list(case.contract)
        out = implement_story(story, project=p.path, workdir=p.work, artifact_root=p.artifacts,
                              client=client, config=cfg)
        gate = out.attempts[-1].gate if out.attempts else None
        check = next((c for c in (gate.checks if gate else []) if c.name == CHECK), None)
        rows = list((check.data or {}).get("rows") or []) if check is not None else []
        return {"terminal": "done" if out.done else (out.terminal or ""),
                "blocked_reason": (out.blocked_reason or "")[:300],
                "check": None if check is None else _outcome_name(check.outcome),
                "check_detail": (check.detail if check is not None else "")[:600],
                "rows": rows,
                "owners": sorted((check.data or {}).get("owners") or []) if check is not None else [],
                "still_green": list((check.data or {}).get("still_green") or []) if check is not None else [],
                "developer_sessions": len([c for c in client.calls if c.role == "developer"]),
                "quality_attempts": out.quality_attempts,
                "attempts": len(out.attempts),
                # the environment/stage budget: a re-verify attempt re-runs the responsible stage and is never
                # charged to the developer (StoryOutcome.quality_attempts skips `verify_only`)
                "verify_only_attempts": len([a for a in out.attempts if a.verify_only]),
                "infra_attempts": len([a for a in out.attempts if a.infra]),
                "review_executions": len([c for c in client.calls if c.role == "review"]),
                "security_executions": len([c for c in client.calls if c.role == "security"]),
                "checks_failed": sorted({c.name for a in out.attempts for c in (a.gate.checks if a.gate else [])
                                         if _outcome_name(c.outcome) == "FAIL"}),
                "checks_unrunnable": sorted({c.name for a in out.attempts for c in (a.gate.checks if a.gate else [])
                                             if _outcome_name(c.outcome) == "UNRUNNABLE"}),
                "failures": [c.name for c in (gate.failures if gate else [])],
                "candidate_bound": bool(out.attempts and out.attempts[-1].identity.get("candidate_sha")),
                }
    finally:
        p.close()


def plan_gate(case: Case) -> dict:
    """The planning-data verdict, reached with no model call at all (§8: before the first developer call)."""
    from aisef.control.machine_gate import ac_proof_defects
    from aisef.control.normalize import PRD, Requirement
    from aisef.control.preflight import check_story

    story = story_for(case)
    prd = PRD(requirements=[Requirement(id=r, kind="functional", title=r) for r in ("FR-2", "FR-4", "FR-5", "FR-9")])
    defects = ac_proof_defects({story.id: len(story.acceptance_criteria)}, {story.id: story.ac_proof},
                               {story.id: story.story_type}, {story.id: story.covers}, prd)
    p = Project()
    try:
        needs = [n for n in check_story(story, project=p.path).needs
                 if getattr(n, "capability", "") == "ac-proof-obligation"]
    finally:
        p.close()
    return {"machine_gate_defects": defects, "preflight_needs": [getattr(n, "kind", "") for n in needs]}


# ------------------------------------------------------------------ model vs real

def lifecycle_for(owner: str | None, case: Case) -> dict:
    """The whole lifecycle the APPROVED policy requires for one failure owner (owner decision section 6).

    This is the part a model must not take from the kernel. Each owner names who can fix the failure, and that
    answer decides which budget pays for the next step and how the story ends:

        satisfied      the story is done on the session that produced it
        PLAN           a planning contradiction no code change can resolve: PLAN_CONFLICT, and the developer's
                       quality budget is not charged for it
        ENVIRONMENT    the evidence could not be obtained: the RESPONSIBLE STAGE is retried (a re-verify attempt,
                       which is not a developer session and not a quality attempt), and the story ends on the
                       environment, never as a quality block
        DEVELOPER      the only owner a developer session can satisfy: the quality budget is charged and
                       `run.max_retries` bounds it
    """
    if owner is None:
        return {"terminal": "done", "developer_sessions": 1, "quality_attempts": 1, "min_stage_retries": 0}
    if owner == PLAN:
        return {"terminal": StageOutcome.PLAN_CONFLICT.value, "developer_sessions": 1, "quality_attempts": 1,
                "min_stage_retries": 0}
    if owner == ENVIRONMENT:
        # a verifier that did not answer names its own terminal; a tool or its evidence names the environment
        term = (StageOutcome.UNRUNNABLE if case.stage in ("review", "security")
                else StageOutcome.ENVIRONMENT_FAILURE).value
        return {"terminal": term, "developer_sessions": 1, "quality_attempts": 1, "min_stage_retries": 1}
    return {"terminal": StageOutcome.QUALITY_BLOCK.value, "developer_sessions": 1 + case.retries,
            "quality_attempts": 1 + case.retries, "min_stage_retries": 0}


def model_expect(case: Case) -> dict:
    """What the reference model says the kernel must do — computed from the scenario's declared obligations and
    intended proof states through the approved policy, never from the product's own tables or observed runs."""
    acs = []
    for i, c in enumerate(case.crits, 1):
        sat, owner, overlap = model_ac(c.mode, c.parent, c.candidate)
        acs.append({"ac_id": f"AC-{SID}-{i}", "proof_mode": c.mode, "requirement": c.requirement,
                    "parent": c.parent, "candidate": c.candidate, "satisfied": sat, "owner": owner,
                    "plan_overlap": overlap, "parent_state": c.parent_state, "candidate_state": c.candidate_state})
    # The criteria decide the CHECK; a stage that could not run decides the LIFECYCLE. They are different
    # questions: lint or the reviewer being absent says nothing about whether a criterion showed its obligation.
    all_sat = all(a["satisfied"] for a in acs)
    owners = sorted({a["owner"] for a in acs if a["owner"]})
    # A criterion nobody could answer for is not the developer's failure: when EVERY blocking criterion is owned by
    # the environment the check itself could not run (F2 typed outcomes — absence is never a FAIL).
    check = "PASS" if all_sat else ("UNRUNNABLE" if owners == [ENVIRONMENT] else "FAIL")
    # The owner that decides the lifecycle is the most demanding one present: a developer failure still has to be
    # fixed by a developer even when another criterion is owned elsewhere.
    every = owners + ([case.owner] if case.owner else [])
    ruling = (DEVELOPER if DEVELOPER in every else (PLAN if PLAN in every else (ENVIRONMENT if ENVIRONMENT in every
              else None)))
    return {"acs": acs, "check": check, "owners": owners, "ruling_owner": ruling, **lifecycle_for(ruling, case)}


def compare(case: Case) -> dict:
    """One scenario: the real kernel, the model, and every field they must agree on."""
    t0 = time.time()
    model = model_expect(case)
    if case.id in PLAN_GATE_CASES:
        real = plan_gate(case)
        bad = []
        if ("machine_gate" in case.plan_gates) != bool(real["machine_gate_defects"]):
            bad.append(f"machine gate real={bool(real['machine_gate_defects'])} model={'machine_gate' in case.plan_gates}"
                       f" {real['machine_gate_defects'][:1]}")
        if ("preflight" in case.plan_gates) != bool(real["preflight_needs"]):
            bad.append(f"preflight real={bool(real['preflight_needs'])} model={'preflight' in case.plan_gates}")
        return {"case": case.id, "title": case.title, "route": "PLAN_GATE", "model": model, "real": real,
                "mismatches": bad, "elapsed_s": round(time.time() - t0, 2)}
    real = real_run(case)
    bad: list[str] = []
    by_id = {r["ac_id"]: r for r in real["rows"]}
    # A scenario whose declared failure is a STAGE that could not run is judged on its lifecycle: with the evidence
    # missing there is nothing for the criteria to be judged from, and demanding rows would only re-assert that.
    for a in ([] if case.owner else model["acs"]):
        r = by_id.get(a["ac_id"])
        if r is None:
            bad.append(f"{a['ac_id']}: the gate reported no row for it")
            continue
        sat = r["outcome"] == "SATISFIED"
        if sat != a["satisfied"]:
            bad.append(f"{a['ac_id']}: satisfied real={sat} model={a['satisfied']} ({r['outcome']})")
        if (r["owner"] or None) != a["owner"]:
            bad.append(f"{a['ac_id']}: owner real={r['owner']!r} model={a['owner']!r}")
        if (r["outcome"] == "PLAN_OVERLAP") != a["plan_overlap"]:
            bad.append(f"{a['ac_id']}: plan_overlap real={r['outcome']!r} model={a['plan_overlap']}")
        if r["parent"] != a["parent"] or r["candidate"] != a["candidate"]:
            bad.append(f"{a['ac_id']}: sides real={r['parent']}->{r['candidate']} model={a['parent']}->{a['candidate']}")
        if a["parent_state"] not in (r.get("parent_states") or []):
            bad.append(f"{a['ac_id']}: parent proof state real={r.get('parent_states')} scenario={a['parent_state']}")
        if a["candidate_state"] not in (r.get("candidate_states") or []):
            bad.append(f"{a['ac_id']}: candidate proof state real={r.get('candidate_states')} "
                       f"scenario={a['candidate_state']}")
        for f in ("requirement", "proof_mode", "expected_transition", "actual_transition"):
            if not str(r.get(f) or ""):
                bad.append(f"{a['ac_id']}: the gate's feedback carries no {f}")
    if not case.owner and real["check"] != model["check"]:
        bad.append(f"check outcome real={real['check']!r} model={model['check']!r}")
    if not case.owner and real["owners"] != model["owners"]:
        bad.append(f"owners real={real['owners']} model={model['owners']}")
    if real["terminal"] != model["terminal"]:
        bad.append(f"terminal real={real['terminal']!r} model={model['terminal']!r}")
    if real["quality_attempts"] != model["quality_attempts"]:
        bad.append(f"developer quality budget real={real['quality_attempts']} model={model['quality_attempts']}")
    if real["developer_sessions"] != model["developer_sessions"]:
        bad.append(f"developer sessions real={real['developer_sessions']} model={model['developer_sessions']}")
    # the environment budget and the retry TARGET: an absence must buy a re-verify of the responsible stage, never
    # another developer session (owner decision sections 6 and 7)
    if real["verify_only_attempts"] < model["min_stage_retries"]:
        bad.append(f"stage retries real={real['verify_only_attempts']} model>={model['min_stage_retries']} "
                   f"— the responsible stage was not re-run")
    if model["ruling_owner"] == ENVIRONMENT and real["checks_failed"]:
        bad.append(f"an absence was reported as a FAILED check: {real['checks_failed']} — a check must never "
                   f"turn evidence that did not run into a verdict against the developer")
    if case.stage == "review" and model["ruling_owner"] == ENVIRONMENT and real["review_executions"] < 2:
        bad.append(f"review executions real={real['review_executions']} — the review stage was not retried")
    if case.stage == "security" and model["ruling_owner"] == ENVIRONMENT and real["security_executions"] < 2:
        bad.append(f"security executions real={real['security_executions']} — the security stage was not retried")
    if not real["candidate_bound"]:
        bad.append("the verdict was not bound to a frozen candidate (evidence freshness)")
    # §11: what the reader is told must be the structured row, never "tests green on first run"
    if real["check"] == "FAIL":
        first = next((a for a in model["acs"] if not a["satisfied"]), None)
        for token in ([first["ac_id"], first["proof_mode"], first["requirement"]] if first else []):
            if token not in real["check_detail"]:
                bad.append(f"the gate's message does not carry {token!r}: {real['check_detail'][:120]}")
    return {"case": case.id, "title": case.title, "route": "REAL_KERNEL", "model": model, "real": real,
            "mismatches": bad, "elapsed_s": round(time.time() - t0, 2)}


def run_all(only: list[str] | None = None) -> list[dict]:
    out = []
    for case in SCENARIOS:
        if only and case.id not in only:
            continue
        try:
            out.append(compare(case))
        except Exception:                                    # noqa: BLE001 — a crash IS a result
            out.append({"case": case.id, "title": case.title, "route": "CRASH",
                        "mismatches": [traceback.format_exc()[-600:]], "model": {}, "real": {}})
    return out


def summarize(results: list[dict]) -> dict:
    modes, transitions, outcomes = set(), set(), {}
    for r in results:
        for a in (r.get("model") or {}).get("acs") or []:
            modes.add(a["proof_mode"])
            transitions.add(f"{a['parent_state']} -> {a['candidate_state']}")
        for row in (r.get("real") or {}).get("rows") or []:
            outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
    owners = {"PLAN": 0, "DEVELOPER": 0, "ENVIRONMENT": 0, "VERIFIER": 0}
    for r in results:
        for row in (r.get("real") or {}).get("rows") or []:
            if row.get("owner"):
                owners[row["owner"]] = owners.get(row["owner"], 0) + 1
    return {"scenarios": len(results),
            "proof_modes_exercised": f"{len(modes & {'CHANGE_REQUIRED', 'PRESERVE_REQUIRED', 'NEGATIVE_INVARIANT'})}/3",
            "proof_state_transitions_exercised": sorted(transitions),
            "per_ac_outcomes_exercised": outcomes,
            "outcomes_by_owner": owners,
            "plan_owned_outcomes": owners["PLAN"], "developer_owned_outcomes": owners["DEVELOPER"],
            "environment_owned_outcomes": owners["ENVIRONMENT"],
            "mixed_story_scenario": any(r["case"] == "I" and not r["mismatches"] for r in results),
            "mismatches": sum(len(r["mismatches"]) for r in results),
            "invariant_violations": 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", help="comma-separated case ids")
    a = ap.parse_args()
    t0 = time.time()
    results = run_all([s for s in a.only.split(",") if s] or None)
    summary = summarize(results)
    rec = {"artifact": "TDD-POLICY-V2-CONFORMANCE", "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "git_sha": _git(ROOT, "rev-parse", "HEAD"), "aisef_tree": _git(ROOT, "rev-parse", "HEAD:aisef"),
           "aisef_dirty": subprocess.run(["git", "status", "--porcelain", "aisef"], cwd=ROOT, capture_output=True,
                                         text=True, encoding="utf-8", errors="replace").stdout.split(),
           "elapsed_s": round(time.time() - t0, 1), "summary": summary, "results": results,
           "pass": summary["mismatches"] == 0 and summary["invariant_violations"] == 0}
    text = json.dumps(rec, ensure_ascii=False, indent=1) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(json.dumps({"summary": summary, "pass": rec["pass"],
                      "failed": [r["case"] for r in results if r["mismatches"]]}, ensure_ascii=False))
    for r in results:
        for m in r["mismatches"]:
            print(f"  {r['case']}: {m}")
    return 0 if rec["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
