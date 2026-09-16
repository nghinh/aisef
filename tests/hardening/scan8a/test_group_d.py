"""Phase 8A group D — discovery-debt resolution for FAM-TOOL (SS-34, SS-45..48), FAM-PROCESS (SS-49..52)
and FAM-APPROVAL (SS-54..56): one deterministic test per NEEDS_TEST site listed in
closure-evidence/hardening/sibling-scan.json. Every test asserts the INVARIANT (docs/INVARIANTS.md): a red
test is CONFIRMED and marked ``expectedFailure`` under its SS id with the observed wrong behaviour; a green
one is a negative control whose comment names the guard that makes the site safe. Preconditions assert that
the suspicious path was actually exercised. No OpenCode, no network, no Docker (tests/__init__.py swaps the
host provider in; sandbox and HTTP probes are faked, port leases use unbound ports).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import tests  # noqa: E402,F401

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control import gate  # noqa: E402
from aisef.control.approvals import STORIES_INDEX, ApprovalStore, Gate, Status  # noqa: E402
from aisef.control.budget import BudgetConfig, BudgetExceeded, BudgetGuard, BudgetLedger  # noqa: E402
from aisef.control.journal import reconcile_story  # noqa: E402
from aisef.control.ledger import GAP, Behavior, Ledger  # noqa: E402
from aisef.control.outcome import Outcome  # noqa: E402
from aisef.control.preflight import provisioned  # noqa: E402
from aisef.control.state import (  # noqa: E402
    StateStore, StoryStatus, TransitionError, claim_is_orphaned, machine_id, pid_alive,
)
from aisef.harness import sandbox, verify_image  # noqa: E402
from aisef.harness.observe import TOOL_RUN, EvidenceStore  # noqa: E402
from aisef.harness.server_identity import acquire_port_lease, ready_with_identity, release_port_lease  # noqa: E402
from aisef.harness.tools import command_for, image_for  # noqa: E402
from aisef.phases.improve import stop_reason  # noqa: E402
from aisef.phases.qa import run_suite  # noqa: E402
from aisef.phases.run import _missing_tools  # noqa: E402

SID = "STORY-01-01"
ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _check(g, name):
    return next(c for c in g.checks if c.name == name)


def _pyproject(project: Path) -> None:
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")


# ---------------------------------------------------------------- FAM-TOOL / INV-N.1, INV-F.3

class TestSS34UnrunnableQaKindIsNotAFailedCheck(unittest.TestCase):
    """SS-34 — `run_suite` computes `KindResult.unrunnable` (exit 127, runner missing) and records the
    `qa:<kind>` event without it; the story gate's contract loop then scores `ran.ok` → FAILED."""

    # GREEN since F5 (SS-34: tool presence is measured, never inferred), 2026-09-17
    def test_a_missing_runner_scores_the_qa_kind_unrunnable_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp); artifacts = project / "_bmad-output"; artifacts.mkdir()
            fake = sandbox.FakeProvider([sandbox.SandboxResult(127, stderr="sh: playwright: command not found")])
            cfg = Config({**DEFAULTS, "verify.e2e": "playwright test", "sandbox.provider": "fake"})
            with sandbox.using(fake):
                rep = run_suite(project, config=cfg, only=["e2e"], has_ui=True,
                                story_id=SID, artifact_root=artifacts)
            self.assertTrue(rep.results[0].unrunnable, "precondition: the suite itself knew the kind was unrunnable")
            ev = EvidenceStore(artifacts).read(SID)
            g = gate.evaluate(SID, ev, changed=[], write_scope=[], screens=[], contract=["e2e"], review_blocking=[])
            self.assertIs(_check(g, "e2e").outcome, Outcome.UNRUNNABLE,
                          f"qa:e2e record {ev.last(TOOL_RUN, 'qa:e2e').detail!r} "
                          f"scored {_check(g, 'e2e').outcome.value}")


class TestSS45AutoDetectedToolsAreProbed(unittest.TestCase):
    """SS-45 — `check_tools` probes `declared_tools(cfg)`: non-empty config strings only. The sast command a
    python project actually runs (`command_for` → `bandit -q -r .`) is never probed, so doctor stays silent."""

    # GREEN since F5 (SS-45: tool presence is measured, never inferred), 2026-09-17
    def test_the_default_sast_command_of_a_python_project_is_probed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp); _pyproject(project)
            cfg = Config({**DEFAULTS, "sandbox.use_docker": False})
            self.assertEqual(command_for("sast", project, cfg), "bandit -q -r .", "precondition: auto-detected")
            with mock.patch.object(verify_image, "_probe_host", return_value=(False, "not on PATH")):
                out = verify_image.check_tools(project, cfg)
            self.assertTrue([tc for tc in out if "bandit" in tc.command and not tc.ok],
                            f"doctor probed {[tc.command for tc in out]!r} while `aisef tool sast` "
                            f"will run `bandit -q -r .` unprobed")


class TestSS46PreflightProbeRunsWithoutADeclaredImage(unittest.TestCase):
    """SS-46 — `_missing_tools` returns [] when `sandbox.image` is empty although `image_for` still picks the
    stack image every tool will run in; the session is paid for before anything is probed."""

    # GREEN since F5 (SS-46: tool presence is measured, never inferred), 2026-09-17
    def test_a_stack_image_is_probed_even_when_not_declared(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp); _pyproject(project)
            cfg = Config({**DEFAULTS, "tools.test": "python -m pytest"})
            image = image_for(project, cfg)
            self.assertEqual(cfg["sandbox.image"], "")
            self.assertNotEqual(image, sandbox.DEFAULT_IMAGE, "precondition: a stack image is chosen")
            missing = verify_image.ToolCheck("tools.test", "python -m pytest", False, image, "No module named pytest")
            with mock.patch.object(verify_image, "check_tools", return_value=[missing]) as probe:
                got = _missing_tools(project, cfg)
            self.assertTrue(probe.called and got,
                            f"probe called={probe.called}, missing={got!r}: the run pays for a session in "
                            f"{image} without probing it")


class TestSS47UnjudgeableProbeIsNotPresent(unittest.TestCase):
    """SS-47 — `probe_command` returns None for a project-local runner (`npx …`) and `check_tools` reports it
    `ok=True` ("present"): a status the check did not measure."""

    # GREEN since F5 (SS-47: tool presence is measured, never inferred), 2026-09-17
    def test_a_tool_the_probe_cannot_build_is_not_reported_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config({**DEFAULTS, "tools.test": "npx vitest run", "sandbox.use_docker": False})
            self.assertIsNone(verify_image.probe_command("npx vitest run"), "precondition: no probe can be built")
            tc = verify_image.check_tools(Path(tmp), cfg)[0]
            self.assertIsNot(tc.ok, True, f"unmeasured tool reported as: {tc.line}")


class TestSS48ProvisionedMeansRunnable(unittest.TestCase):
    """SS-48 — `preflight.provisioned` marks `verify.unit` provisioned because `tools.test` is a non-empty
    string; the probe's verdict about that command is never consulted."""

    # GREEN since F5 (SS-48: tool presence is measured, never inferred), 2026-09-17
    def test_a_test_command_the_probe_reports_missing_does_not_provision_verify_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            cfg = Config({**DEFAULTS, "tools.test": "definitely-absent-runner-xyz -q", "sandbox.use_docker": False})
            probe = verify_image.check_tools(project, cfg)      # real host probe: `command -v <binary>`
            self.assertEqual([tc.ok for tc in probe], [False], "precondition: the probe says the runner is missing")
            have = provisioned(project, cfg)
            self.assertNotIn("verify.unit", have, f"provisioned from a string the probe rejects: {probe[0].line}")


# ---------------------------------------------------------------- FAM-PROCESS / INV-M.1

class TestSS49ReconcileDoesNotResetALiveClaim(unittest.TestCase):
    """SS-49 — `reconcile_story` resets every RUNNING story without an open journal attempt to pending and
    never asks `claim_is_orphaned`; a claim held by a live process is reset under it. FM-P-05."""

    # GREEN since F5 (SS-49: a claim is a lease with an owner and a term), 2026-09-17
    def test_a_running_claim_whose_owner_is_alive_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); state = StateStore(root)
            state.register(SID, "EPIC-01", wave=1)
            self.assertTrue(state.claim(SID, owner=machine_id()))          # this very process
            rec = state.load().stories[SID]
            self.assertFalse(claim_is_orphaned(rec.claimed_by), "precondition: the owner is alive")
            r = reconcile_story(SID, artifact_root=root, state=state)
            after = state.load().stories[SID]
            self.assertIs(after.state, StoryStatus.RUNNING,
                          f"live claim {rec.claimed_by} reset to {after.state.value}: {r!r}")


class TestSS50TransitionIsBoundToTheClaimHolder(unittest.TestCase):
    """SS-50 — `claim` has no lease term and `transition` takes no owner: any process moves a story that
    another process holds."""

    # GREEN since F5 (SS-50: a claim is a lease with an owner and a term), 2026-09-17
    def test_a_non_owner_cannot_move_a_claimed_story(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = StateStore(Path(tmp)); state.register(SID, "EPIC-01", wave=1)
            self.assertTrue(state.claim(SID, owner="host-a:111"))
            try:
                state.transition(SID, StoryStatus.VERIFYING, owner="host-b:222")
                refused = False
            except TransitionError:
                refused = True
            except TypeError:                  # no owner parameter at all: the write is unattributed
                state.transition(SID, StoryStatus.VERIFYING)
                refused = False
            rec = state.load().stories[SID]
            self.assertTrue(refused or rec.state is StoryStatus.RUNNING,
                            f"host-b:222 moved a story claimed by {rec.claimed_by} to {rec.state.value}")


class TestSS51OneBaseUrlOneLease(unittest.TestCase):
    """SS-51 — the port lease is keyed by run_id (`port-<run_id>.lock`): two runs contending for one base_url
    lock two files and both win; and `ready_with_identity` answers True to a 404."""

    URL = "http://127.0.0.1:1"      # never bound

    # GREEN since F5 (SS-51: a claim is a lease with an owner and a term), 2026-09-17
    def test_a_second_run_contending_for_the_same_base_url_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = acquire_port_lease(root, "run-a", self.URL)
            self.assertIsNotNone(a)
            b = acquire_port_lease(root, "run-b", self.URL)
            try:
                self.assertIsNone(b, f"run-b also holds {self.URL}: lock files "
                                     f"{sorted(p.name for p in (root / '.aisef' / 'lease').glob('port-*.lock'))}")
            finally:
                release_port_lease(root, "run-a", a)
                if b is not None:
                    release_port_lease(root, "run-b", b)

    # GREEN since F5 (SS-51: a claim is a lease with an owner and a term), 2026-09-17
    def test_a_404_from_the_server_does_not_prove_identity(self):
        err = urllib.error.HTTPError(self.URL + "/_aisef/identity", 404, "Not Found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err) as opened:
            ready = ready_with_identity(self.URL, "run-a", attempts=1)
        self.assertTrue(opened.called, "precondition: the identity endpoint was asked")
        self.assertFalse(ready, "a responder that cannot echo run-a is accepted as run-a's server")


class TestSS52ReservationsOfADeadRunDoNotCountForever(unittest.TestCase):
    """SS-52 — a reservation carries no owner and no TTL; a run SIGKILLed inside `reserve` leaves an estimate
    that `_check_caps` counts against the cap on every later call."""

    # GREEN since F5 (SS-52: a claim is a lease with an owner and a term), 2026-09-17
    def test_a_killed_runs_reservation_does_not_block_the_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            BudgetGuard(BudgetLedger(root)).configure(BudgetConfig(cap_usd=1.0))
            child = subprocess.Popen([sys.executable, "-c", (
                f"import sys, time; sys.path.insert(0, {str(ROOT)!r})\n"
                "from pathlib import Path\nfrom aisef.control.budget import BudgetGuard, BudgetLedger\n"
                f"with BudgetGuard(BudgetLedger(Path({str(root)!r}))).reserve(story_id='S-killed', est_usd=0.9):\n"
                "    time.sleep(60)\n")])
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not BudgetLedger(root).load().reservations:
                time.sleep(0.05)
            child.kill(); child.wait()
            left = BudgetLedger(root).load().reservations
            self.assertEqual([r["story"] for r in left], ["S-killed"], "precondition: the estimate outlived its process")
            self.assertFalse(pid_alive(child.pid), "precondition: the reserving process is dead")
            try:
                with BudgetGuard(BudgetLedger(root)).reserve(story_id=SID, est_usd=0.5):
                    pass
            except BudgetExceeded as e:
                self.fail(f"dead run's reservation still counts: {e}")


# ---------------------------------------------------------------- FAM-APPROVAL / INV-P.1

class TestSS54RepairStoriesAreCoveredByAnApproval(unittest.TestCase):
    """SS-54 — `_artifact_hash` drops `STORY-RP-*` from the stories/readiness digest (deliberate, bugs 25/28);
    the `improve` gate is the compensating approval and `stop_reason` waives it under `--auto` (and never
    asks before round 1). The repair story must still be covered by some approval's digest."""

    @unittest.expectedFailure   # SS-54 — improve.py:441 `not auto` waives the gate; no digest (stories/readiness/improve) sees STORY-RP-01
    def test_under_auto_a_new_repair_story_is_covered_by_a_gate_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = ApprovalStore(root)
            index = {"stories": [{"id": SID, "epic_id": "EPIC-01"}], "epics": [{"id": "EPIC-01"}]}
            (root / STORIES_INDEX).write_text(json.dumps(index), encoding="utf-8")
            (root / "design-contract.json").write_text("{}", encoding="utf-8")
            store.approve(Gate.STORIES, by="nghi"); store.approve(Gate.READINESS, by="nghi")
            led = Ledger(loops=[{"epic": "EPIC-01", "n": "loop-0", "epic_verified": 0, "epic_reopened": 0},
                                {"epic": "EPIC-01", "n": "loop-1", "epic_verified": 1, "epic_reopened": 0}])
            gaps = [Behavior(id="AC-STORY-01-01-2", kind="ac", story=SID, status=GAP)]
            ask = dict(max_loops=10, flat_loops=3, cost_cap=0.0, approvals=store)
            self.assertIn("awaiting human approval", stop_reason(led, "EPIC-01", gaps, None, auto=False, **ask))
            self.assertEqual(stop_reason(led, "EPIC-01", gaps, None, auto=True, **ask), "",
                             "precondition: --auto waives the improve gate for round 2")
            before = {g: store.content_hash(g) for g in Gate}
            index["stories"].append({"id": "STORY-RP-01", "epic_id": "EPIC-RP-EPIC-01", "repair_of": "AC-STORY-01-01-2"})
            (root / STORIES_INDEX).write_text(json.dumps(index), encoding="utf-8")
            seen = [g.value for g in Gate if store.content_hash(g) != before[g]]
            self.assertTrue(seen, f"STORY-RP-01 entered the index under --auto and no gate digest changed; "
                                  f"readiness={store.status(Gate.READINESS).value}")


class TestSS55GateConfigIsBoundByReadiness(unittest.TestCase):
    """SS-55 — no gate digest covers `.ai/config.json`; weakening `coverage.min` / `security.block_severities`
    after the readiness approval reinterprets the approved plan and nothing goes stale. FM-A-03."""

    @unittest.expectedFailure   # SS-55 — approvals.py:79-96 GATE_ARTIFACTS has no entry for .ai/config.json; readiness stays approved
    def test_weakening_coverage_min_after_readiness_approval_makes_it_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp); root = project / "_bmad-output"; root.mkdir()
            conf = project / ".ai" / "config.json"; conf.parent.mkdir()
            conf.write_text(json.dumps({"coverage.min": 0.85, "security.block_severities": ["critical", "high"]}),
                            encoding="utf-8")
            (root / STORIES_INDEX).write_text('{"stories": []}', encoding="utf-8")
            (root / "design-contract.json").write_text("{}", encoding="utf-8")
            store = ApprovalStore(root); store.approve(Gate.READINESS, by="nghi")
            conf.write_text(json.dumps({"coverage.min": 0.1, "security.block_severities": ["critical"]}),
                            encoding="utf-8")
            self.assertEqual(Config.load(project, env={})["coverage.min"], 0.1,
                             "precondition: the run would read the weaker threshold")
            self.assertIs(store.status(Gate.READINESS), Status.STALE,
                          "coverage.min 0.85→0.1 and block_severities narrowed after approval; readiness still approved")


class TestSS56UpstreamContentEditStalesDownstream(unittest.TestCase):
    """SS-56 — `status()` cascades only on a new upstream *decision* (`_upstream_decided_after`), not on an
    upstream *content edit*: after `prd.md` changes, `architecture` still reports APPROVED to programmatic
    callers (CLI entry points compensate through `blocking()`)."""

    @unittest.expectedFailure   # SS-56 — approvals.py:279-287 compares upstream `seq` only; PRD edited, no new PRD decision → APPROVED
    def test_editing_the_prd_makes_the_approved_architecture_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = ApprovalStore(root)
            (root / "prd.md").write_text("# PRD v1\n", encoding="utf-8")
            (root / "architecture.md").write_text("# Arch v1\n", encoding="utf-8")
            store.approve(Gate.PRD, by="nghi"); store.approve(Gate.ARCHITECTURE, by="nghi")
            (root / "prd.md").write_text("# PRD v2 — new scope\n", encoding="utf-8")
            self.assertIs(store.status(Gate.PRD), Status.STALE, "precondition: the upstream edit is detected")
            self.assertIn(Gate.PRD, store.blocking(Gate.ARCHITECTURE), "precondition: the CLI path would block")
            self.assertIs(store.status(Gate.ARCHITECTURE), Status.STALE,
                          "architecture approved against PRD v1 reports APPROVED after the PRD changed")


if __name__ == "__main__":
    unittest.main()
