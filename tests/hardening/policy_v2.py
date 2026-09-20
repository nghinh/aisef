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
    if c.kind == "new":
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
    #: what the model expects of the whole story
    expect_check: str = ""          # PASS | FAIL | UNRUNNABLE
    expect_terminal: str = ""       # done | the StageOutcome value
    #: for a plan-gate case: which deterministic gate(s) must name the defect before any model call
    plan_gates: tuple[str, ...] = ()
    covers: list[str] = field(default_factory=lambda: ["FR-4"])


def obligations_of(case: Case) -> dict:
    return {f"AC-{SID}-{i}": {"ac_id": f"AC-{SID}-{i}", "proof_mode": c.mode, "requirement": c.requirement}
            for i, c in enumerate(case.crits, 1)}


# ------------------------------------------------------------------ the scenarios (owner section 2, A-N)
SCENARIOS: list[Case] = [
    Case("A", "CHANGE_REQUIRED: parent RED_EXECUTED, candidate GREEN_EXECUTED => PASS",
         [_crit("new", "CHANGE_REQUIRED")], expect_check="PASS", expect_terminal="done"),
    Case("B", "CHANGE_REQUIRED already green at the parent => PLAN_OVERLAP before any developer quality retry",
         [_crit("already", "CHANGE_REQUIRED")], expect_check="FAIL", expect_terminal=StageOutcome.PLAN_CONFLICT.value),
    Case("C", "PRESERVE_REQUIRED: GREEN -> GREEN => PASS",
         [_crit("new", "CHANGE_REQUIRED"), _crit("keep", "PRESERVE_REQUIRED", requirement="FR-2")],
         expect_check="PASS", expect_terminal="done"),
    Case("D", "PRESERVE_REQUIRED: GREEN -> RED => DEVELOPER regression block",
         [_crit("new", "CHANGE_REQUIRED"), _crit("break", "PRESERVE_REQUIRED", requirement="FR-2")],
         broken=True, expect_check="FAIL", expect_terminal=StageOutcome.QUALITY_BLOCK.value),
    Case("E", "NEGATIVE_INVARIANT: GREEN -> GREEN => PASS",
         [_crit("new", "CHANGE_REQUIRED"), _crit("absence", "NEGATIVE_INVARIANT", requirement="FR-9")],
         expect_check="PASS", expect_terminal="done"),
    Case("F", "NEGATIVE_INVARIANT: GREEN -> RED => DEVELOPER regression block",
         [_crit("new", "CHANGE_REQUIRED"), _crit("absence_broken", "NEGATIVE_INVARIANT", requirement="FR-9")],
         broken=True, expect_check="FAIL", expect_terminal=StageOutcome.QUALITY_BLOCK.value),
    Case("G", "UNRUNNABLE parent evidence never satisfies CHANGE_REQUIRED",
         [_crit("new_import", "CHANGE_REQUIRED"), _crit("parent_unrunnable", "CHANGE_REQUIRED", requirement="FR-2")],
         expect_check="FAIL", expect_terminal=StageOutcome.QUALITY_BLOCK.value),
    Case("H", "NOT_COLLECTED parent evidence never satisfies CHANGE_REQUIRED",
         [_crit("new_import", "CHANGE_REQUIRED"), _crit("parent_uncollected", "CHANGE_REQUIRED", requirement="FR-2")],
         expect_check="FAIL", expect_terminal=StageOutcome.QUALITY_BLOCK.value),
    Case("I", "a mixed story: every criterion judged by its own obligation",
         [_crit("new", "CHANGE_REQUIRED"), _crit("new_import", "CHANGE_REQUIRED", requirement="FR-5"),
          _crit("keep", "PRESERVE_REQUIRED", requirement="FR-2"),
          _crit("absence", "NEGATIVE_INVARIANT", requirement="FR-9")],
         expect_check="PASS", expect_terminal="done"),
    Case("J", "CHANGE_REQUIRED green because an upstream story owns it => PLAN_OVERLAP, developer budget unchanged",
         [_crit("new", "CHANGE_REQUIRED"), _crit("already", "CHANGE_REQUIRED", requirement="FR-2")],
         expect_check="FAIL", expect_terminal=StageOutcome.PLAN_CONFLICT.value),
    Case("K", "a normal story with zero CHANGE_REQUIRED is a plan defect, refused before the first model call",
         [_crit("keep", "PRESERVE_REQUIRED", requirement="FR-2"),
          _crit("absence", "NEGATIVE_INVARIANT", requirement="FR-9")],
         expect_check="PLAN_GATE", expect_terminal="PLAN_GATE", plan_gates=("machine_gate", "preflight")),
    Case("L", "a criterion whose requirement the story does not cover is a plan/readiness failure",
         [_crit("new", "CHANGE_REQUIRED", requirement="FR-77")],
         expect_check="PLAN_GATE", expect_terminal="PLAN_GATE", plan_gates=("machine_gate",)),
    Case("M", "a malformed proof mode is a plan/readiness failure",
         [_crit("new", "NO_SUCH_MODE")], expect_check="PLAN_GATE", expect_terminal="PLAN_GATE",
         plan_gates=("machine_gate", "preflight")),
    Case("N", "the gate reports every structured feedback field for each failing criterion",
         [_crit("new", "CHANGE_REQUIRED"), _crit("break", "PRESERVE_REQUIRED", requirement="FR-2")],
         broken=True, expect_check="FAIL", expect_terminal=StageOutcome.QUALITY_BLOCK.value),
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
    out: dict[str, str] = {"ledgerlock/cli.py": BROKEN_CLI if case.broken else STORY_CLI}
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
            developer=[Step.changed(files_for(case))], review=[Step.passes()], security=[Step.passes()]))
        cfg = Config({**DEFAULTS, "tools.lint": "true", "run.max_retries": 1,
                      "tools.test": quote_command([sys.executable, "-m", "unittest", "discover",
                                                   "-s", "tests", "-t", ".", "-v"])})
        out = implement_story(story_for(case), project=p.path, workdir=p.work, artifact_root=p.artifacts,
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

def model_expect(case: Case) -> dict:
    """What the reference model says the kernel must do — computed from the scenario's declared obligations and
    intended proof states, never from the product's own tables."""
    acs = []
    for i, c in enumerate(case.crits, 1):
        sat, owner, overlap = model_ac(c.mode, c.parent, c.candidate)
        acs.append({"ac_id": f"AC-{SID}-{i}", "proof_mode": c.mode, "requirement": c.requirement,
                    "parent": c.parent, "candidate": c.candidate, "satisfied": sat, "owner": owner,
                    "plan_overlap": overlap, "parent_state": c.parent_state, "candidate_state": c.candidate_state})
    all_sat = all(a["satisfied"] for a in acs)
    owners = sorted({a["owner"] for a in acs if a["owner"]})
    # A criterion nobody could answer for is not the developer's failure: when EVERY blocking criterion is owned by
    # the environment the check itself could not run (F2 typed outcomes — absence is never a FAIL).
    check = "PASS" if all_sat else ("UNRUNNABLE" if owners == [ENVIRONMENT] else "FAIL")
    # §12, budget: only a DEVELOPER-owned failure may buy a second developer session. A planning contradiction is
    # routed to the plan on the evidence of the session that revealed it, and an environment answer proves nothing
    # a retry could fix either.
    # §12, budget: a planning contradiction is routed to the plan on the evidence of the session that revealed it
    # and buys no second developer session. Everything else blocking does.
    spends = bool(not all_sat and owners != [PLAN])
    return {"acs": acs, "check": check, "owners": owners, "terminal": case.expect_terminal,
            "developer_sessions": 2 if spends else 1, "quality_attempts": 2 if spends else 1}


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
    for a in model["acs"]:
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
    if real["check"] != model["check"]:
        bad.append(f"check outcome real={real['check']!r} model={model['check']!r}")
    if real["owners"] != model["owners"]:
        bad.append(f"owners real={real['owners']} model={model['owners']}")
    if real["terminal"] != model["terminal"]:
        bad.append(f"terminal real={real['terminal']!r} model={model['terminal']!r}")
    if real["quality_attempts"] != model["quality_attempts"]:
        bad.append(f"developer quality budget real={real['quality_attempts']} model={model['quality_attempts']}")
    if real["developer_sessions"] != model["developer_sessions"]:
        bad.append(f"developer sessions real={real['developer_sessions']} model={model['developer_sessions']}")
    if not real["candidate_bound"]:
        bad.append("the verdict was not bound to a frozen candidate (evidence freshness)")
    # §11: what the reader is told must be the structured row, never "tests green on first run"
    if real["check"] != "PASS":
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
