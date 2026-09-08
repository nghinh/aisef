"""Phase 6 -- DevSecOps: pre-deploy gate and operational scaffolding.

Split according to the core principle:

* **Must be guaranteed -> write code.** The pre-deploy gate and CI workflow
  have deterministic answers: are all stories done, has the verification
  suite run fully, which gates lack approval. No model needed.
* **Needs judgment -> delegate to model.** Dockerfile for this stack,
  deploy manifests, runbook for this system -- each project differs.
  Model writes, then **verify with code**: does the image build, does the
  runbook have all four required sections.

The runbook is checked for four sections because a runbook missing the
"escalation" section is only useful to someone who already knows whom to
call -- i.e. the person who does not need the runbook.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter, RunSpec
from ..config import Config
from ..control.approvals import (
    GATE_ORDER,
    PRE_DEPLOY_REPORT,
    ApprovalStore,
    Gate,
    Status,
)
from ..control.outcome import Check, Outcome
from ..control.state import StateStore, StoryStatus
from .qa import QaReport, run_suite

CI_PATH = ".github/workflows/aisef.yml"

#: How CI installs the framework. User-configurable for internal releases
#: or git-based installs.
INSTALL_SPEC = "aisef"          # PyPI package name; module/command stays `aisef`
RUNBOOK_PATH = "docs/RUNBOOK.md"

#: Four required runbook sections. Missing any one renders it useless exactly
#: when needed most -- at 3 AM, by the on-call who has never read this system.
RUNBOOK_SECTIONS = ("symptoms", "diagnosis", "remediation", "escalation")
_RUNBOOK_VI = {"triệu chứng": "symptoms", "chẩn đoán": "diagnosis",
               "xử lý": "remediation", "leo thang": "escalation"}


@dataclass
class PreDeployReport:
    checks: list[Check] = field(default_factory=list)
    qa: QaReport | None = None
    #: Reason for accepting degraded runs, if any -- gate evidence, so it is
    #: persisted alongside results, not only kept in config.
    degraded_waiver: str = ""
    #: Acceptance scope when scoring `--epic E` (decision C-a 2026-09-06):
    #: stories in/out of scope, so the signer knows what they are accepting.
    #: `None` = entire plan, as before.
    scope: dict | None = None
    #: Verification kinds explicitly waived with the declarer's reason -- gate
    #: evidence, persisted alongside results like `degraded_waiver`.
    waivers: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [c.as_dict() for c in self.checks],
            "qa": None if self.qa is None else {
                "release_ready": self.qa.release_ready,
                # Candidate SHA the project-level verification suite ran on (ADR-004 R1).
                "candidate": self.qa.candidate,
                # Tree used for verification: clean worktree from SHA (ADR-005 V6)
                # or agent tree -- gate signer must see this assurance level.
                "tree": self.qa.tree,
                "clean_tree": self.qa.clean_tree,
                "failed": [r.kind.id for r in self.qa.failed],
                "unconfigured": [r.kind.id for r in self.qa.unconfigured],
                "degraded": [r.kind.id for r in self.qa.degraded],
                # Missing guarantees per kind -- waiver signer knows what they accept.
                "missing": {r.kind.id: list(r.missing) for r in self.qa.degraded},
                "fake_tests": self.qa.fake_tests,
            },
            "degraded_waiver": self.degraded_waiver,
            "scope": self.scope,
            "waivers": self.waivers,
        }

    def write(self, artifact_root: Path | str) -> Path:
        """Persist results to disk -- this is what the signer reads before
        approving the `pre-deploy` gate, and is attached to the approval."""
        import json

        path = Path(artifact_root) / PRE_DEPLOY_REPORT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def summary(self) -> str:
        scope_label = f" (scope {self.scope['epic']})" if self.scope else ""
        lines = [f"Pre-deploy gate{scope_label}: {'PASS' if self.passed else 'FAIL'}"]
        lines += [c.line() for c in self.checks]
        if self.qa and not self.qa.release_ready:
            lines.append(self.qa.summary())
        return "\n".join(lines)


def _isolation_check(report: PreDeployReport, cfg: Config) -> Check:
    """Check whether verification ran inside Docker, and if not whether that
    is permitted.  Degraded runs name **missing guarantees** (ADR-005 V5) --
    "outside Docker" alone does not tell the waiver signer what they accept."""
    degraded = report.qa.degraded if report.qa else []
    if not degraded:
        if report.qa and not any(r.ran for r in report.qa.results):
            return Check("isolation", Outcome.UNCONFIGURED, "no runs to determine")
        return Check("isolation", True, "verification ran inside Docker")
    ten = ", ".join(
        f"{r.kind.id} (missing {', '.join(r.missing) if r.missing else 'unknown guarantees'})"
        for r in degraded
    )
    waiver = str(cfg.get("sandbox.pre_deploy_degraded_waiver", "") or "").strip()
    if waiver:
        report.degraded_waiver = waiver
        return Check(
            "isolation", True,
            f"degraded: {ten} — accepted per declaration: {waiver}",
        )
    return Check(
        "isolation", False,
        f"{ten} ran outside Docker. Pre-deploy gate does not "
        f"accept degraded runs; set up Docker, or declare a reason at "
        f"`sandbox.pre_deploy_degraded_waiver` to record in evidence.",
    )


def check_runbook(path: Path) -> Check:
    if not path.is_file():
        return Check("runbook", False, f"missing {path.name}")
    text = path.read_text(encoding="utf-8", errors="replace").lower()
    # Accept both English and Vietnamese section headings.
    found = {s for s in RUNBOOK_SECTIONS if s in text}
    for vi, en in _RUNBOOK_VI.items():
        if vi in text:
            found.add(en)
    missing = [s for s in RUNBOOK_SECTIONS if s not in found]
    if missing:
        return Check("runbook", False, f"missing sections: {', '.join(missing)}")
    return Check("runbook", True)



def _planned_but_never_run(artifact_root: Path, registered: set[str]) -> list[str]:
    """Story IDs in `stories.index.json` that have no state record at all."""
    from .run import load_plan

    plan = load_plan(artifact_root)
    if plan.error:
        return []  # no readable plan -- cannot draw further conclusions
    return [sid for sid in plan.stories if sid not in registered]

def _scope(report: PreDeployReport, artifact_root: Path, epic: str) -> set[str]:
    """Acceptance scope = stories of **one** epic in the plan (decision C-a
    2026-09-06).  Stories outside scope are not scored: not "done", not
    "missing" -- and are named, because the signer must know what they accept.
    This does not relax the gate: all other checks score identically; only the
    story set is explicitly declared.  Scope is written into the report, so
    the `pre-deploy` approval hash changes accordingly -- approving EPIC-01
    cannot be reused for the entire plan."""
    from .run import load_plan

    plan = load_plan(artifact_root)
    if plan.error:
        report.checks.append(Check("scope", False, f"--epic {epic}: {plan.error}"))
        return set()
    inside = {sid for sid, s in plan.stories.items() if s.epic_id == epic}
    if not inside:
        report.checks.append(Check(
            "scope", False, f"--epic {epic}: no stories belong to this epic in the plan"))
        return set()
    outside = sorted(sid for sid in plan.stories if sid not in inside)
    report.scope = {"epic": epic, "stories": sorted(inside), "outside": outside}
    report.checks.append(Check("scope", True, f"acceptance {epic}: {len(inside)} stories"))
    if outside:
        report.checks.append(Check(
            "outside acceptance scope", Outcome.NOT_APPLICABLE,
            f"{len(outside)} stories not scored — neither done nor missing: "
            + ", ".join(outside[:5]) + ("…" if len(outside) > 5 else ""),
        ))
    return inside


def _waiver_check(report: PreDeployReport, cfg: Config) -> Check | None:
    """Verification kinds waived at `verify.waived` must have a reason at
    `verify.waiver_reason` (scope, date, signer) -- a waiver without a
    reason is not evidence.  Outcome is WAIVED, not PASSED: that kind was
    **not** verified, only accepted by the responsible party (decision 5
    2026-09-06: e9 `mutation` UNRUNNABLE in acceptance environment, no
    extra tooling installed just for optics)."""
    waived = list(report.qa.waived) if report.qa else []
    if not waived:
        return None
    reason = str(cfg.get("verify.waiver_reason", "") or "").strip()
    ten = ", ".join(waived)
    if not reason:
        return Check(
            "explicit waiver", False,
            f"{ten} waived at `verify.waived` without a reason — declare "
            f"`verify.waiver_reason` (scope, date, signer) to record in evidence",
        )
    report.waivers = {k: reason for k in waived}
    return Check("explicit waiver", Outcome.WAIVED, f"{ten} — {reason}")


def pre_deploy(
    project: Path | str,
    *,
    config: Config | None = None,
    has_ui: bool = True,
    skip_qa: bool = False,
    epic: str = "",
) -> PreDeployReport:
    """Score the pre-deploy gate -- read-only, changes nothing.
    `epic` declares acceptance scope (see `_scope`); empty = entire plan."""
    project = Path(project)
    artifact_root = project / "_bmad-output"
    cfg = config or Config.load(project)
    report = PreDeployReport()

    inside = _scope(report, artifact_root, epic) if epic else None
    state = StateStore(artifact_root).load()
    records = [r for r in state.stories.values() if inside is None or r.id in inside]
    if not records:
        report.checks.append(Check(
            "story", False, "no stories have run" + (f" in {epic}" if epic else "")))
    else:
        # Deploy means deploying the main branch. `verified` = passed gate but
        # not merged (G12) -- for this gate it is not done, and must be named
        # separately: "not done" and "done but stuck on merge" need different fixes.
        chua_merge = [r.id for r in records if r.state is StoryStatus.VERIFIED]
        not_done = [
            r.id for r in records
            if r.state not in (StoryStatus.DONE, StoryStatus.VERIFIED)
        ]
        # Stories in the plan that were never registered are not "done":
        # e9 2026-09-05, 01-06/01-07 never ran yet gate showed pass because
        # it only counted state records.  Never ran != passed.
        chua_chay = [
            sid for sid in _planned_but_never_run(artifact_root, set(state.stories))
            if inside is None or sid in inside
        ]
        not_done += chua_chay
        detail = ""
        if not_done:
            detail = f"{len(not_done)} not done: {', '.join(not_done[:5])}"
            if chua_chay:
                detail += f" (never run: {', '.join(chua_chay[:5])})"
        if chua_merge:
            detail += ("; " if detail else "") + (
                f"{len(chua_merge)} done but not merged: {', '.join(chua_merge[:5])}"
            )
        report.checks.append(
            Check("all stories done", not not_done and not chua_merge, detail)
        )

    approvals = ApprovalStore(artifact_root)
    pending = [
        g.value for g in GATE_ORDER
        if g is not Gate.PRE_DEPLOY and approvals.status(g) is not Status.APPROVED
    ]
    report.checks.append(
        Check("human gates", not pending, "" if not pending else f"not approved: {', '.join(pending)}")
    )

    if not skip_qa:
        report.qa = run_suite(project, config=cfg, has_ui=has_ui)
        report.checks.append(
            Check(
                "verification",
                report.qa.release_ready,
                "" if report.qa.release_ready else "see details below",
            )
        )
        # Decision 2026-09-05: the pre-deploy gate does **not** accept
        # verification runs outside Docker, unless an explicit reason is
        # declared -- and that reason is recorded in the gate report as
        # evidence the signer must see.  The verification suite still runs
        # (degraded) so readers have results; only the verdict differs.
        report.checks.append(_isolation_check(report, cfg))
        mien = _waiver_check(report, cfg)
        if mien is not None:
            report.checks.append(mien)

    if skip_qa:
        report.checks.append(
            Check("isolation", Outcome.NOT_APPLICABLE, "skipped along with verification suite")
        )

    dockerfile = project / "Dockerfile"
    report.checks.append(
        Check("Dockerfile", dockerfile.is_file(), "" if dockerfile.is_file() else "missing")
    )
    report.checks.append(
        Check("CI workflow", (project / CI_PATH).is_file(),
              "" if (project / CI_PATH).is_file() else f"missing {CI_PATH}")
    )
    report.checks.append(check_runbook(project / RUNBOOK_PATH))
    return report


def write_ci_workflow(
    project: Path | str,
    *,
    aisef_bin: str = "aisef",
    install_spec: str = INSTALL_SPEC,
) -> Path:
    """Generate a CI workflow that wires up the existing gates.

    CI reruns **the same commands** the developer runs locally.  Writing a
    separate workflow for CI is a sure way for the two to drift apart, and
    then "works on my machine" becomes a debate instead of a verifiable fact.

    ``aisef_bin`` defaults to the command name on PATH, **not** the
    absolute path of the machine that generated the file: that path does
    not exist on CI runners, and the workflow breaks at the first step.
    """
    path = Path(project) / CI_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _CI_TEMPLATE.format(bin=aisef_bin, install=install_spec), encoding="utf-8"
    )
    return path


_CI_TEMPLATE = """# Generated by `aisef devsecops` — runs the same commands the developer runs locally.
name: aisef

on:
  pull_request:
  push:
    branches: [main, master]

jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # The absolute path from the machine that generated this workflow does
      # not exist on CI runners. Install then invoke from PATH.
      #
      # `{install}` must be something pip can actually install: a PyPI package
      # name if published, or `git+https://…` / path to the source repo if not.
      # Change via `--install-spec` when regenerating.
      - name: Install AISEF
        run: pip install --quiet {install}

      # The skill repo (~93 MB) is not bundled in the package. Cache it so
      # each CI run does not have to clone it again.
      - name: Cache skill repo
        uses: actions/cache@v4
        with:
          path: ~/.cache/aisef/references
          key: aisef-references-${{{{ hashFiles('.ai/config.json') }}}}

      - name: Environment
        run: {bin} doctor

      - name: Post-hoc guard on diff
        run: {bin} verify

      - name: Verification
        run: {bin} qa

      - name: Approval gate
        run: {bin} gates

      - name: Story status
        run: {bin} status
"""


_SECTION = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)


def build_prompt(project: Path, stack_summary: str) -> str:
    """Prompt for the model-written part: Dockerfile, IaC, observability, runbook."""
    from ..harness.prompts import load_catalog

    return load_catalog().get("devsecops").render({
        "project_name": project.name,
        "stack": stack_summary or "(not detected — read source code to determine)",
        "runbook_sections": ", ".join(RUNBOOK_SECTIONS),
        "ci_path": CI_PATH,
        "runbook_path": RUNBOOK_PATH,
    })


@dataclass
class DevSecOpsReport:
    generated: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    ci_path: Path | None = None
    cost_usd: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and not self.missing

    def summary(self) -> str:
        if self.error:
            return f"devsecops: ✗ {self.error}"
        # Count the CI workflow too: it is also a generated artifact, and
        # printing "generated 2" then listing 3 lines makes readers doubt
        # the rest of the output.
        n = len(self.generated) + (1 if self.ci_path else 0)
        lines = [f"devsecops: generated {n} artifacts"]
        if self.ci_path:
            lines.append(f"  ✅ {CI_PATH}")
        for name in self.generated:
            lines.append(f"  ✅ {name}")
        for name in self.missing:
            lines.append(f"  ✗ missing {name}")
        if self.cost_usd:
            lines.append(f"  cost: ${self.cost_usd:.2f}")
        return "\n".join(lines)


#: Required artifacts after a run. Verified by code, not by self-report.
REQUIRED_ARTIFACTS = ("Dockerfile", RUNBOOK_PATH)


def generate(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    aisef_bin: str = "aisef",
    install_spec: str = INSTALL_SPEC,
    force: bool = False,
) -> DevSecOpsReport:
    """Generate CI workflow (by code) and operational scaffolding (by model)."""
    from ..kit.detect_stack import detect_file

    # `resolve()`: prompt uses `project.name`, and `Path(".").name` is the
    # empty string. CLI already resolves at entry, but this function can be
    # called directly from other code -- the one place that needs `.name`
    # handles it itself.
    project = Path(project).resolve()
    cfg = config or Config.load(project)
    report = DevSecOpsReport()
    report.ci_path = write_ci_workflow(
        project, aisef_bin=aisef_bin, install_spec=install_spec
    )

    have = [name for name in REQUIRED_ARTIFACTS if (project / name).is_file()]
    if len(have) == len(REQUIRED_ARTIFACTS) and not force:
        report.generated = list(have)
        return report

    req = project / "docs" / "requirements.md"
    stack = detect_file(req).summary() if req.is_file() else ""

    result = client.run(
        RunSpec(
            prompt=build_prompt(project, stack),
            workdir=project,
            max_turns=cfg["run.max_turns"],
            timeout_seconds=cfg["run.timeout_seconds"],
        )
    )
    report.cost_usd = result.cost_usd
    if not result.ok:
        report.error = result.error or "run failed"
        return report

    for name in REQUIRED_ARTIFACTS:
        (report.generated if (project / name).is_file() else report.missing).append(name)

    runbook = check_runbook(project / RUNBOOK_PATH)
    if not runbook.passed and RUNBOOK_PATH not in report.missing:
        report.missing.append(f"{RUNBOOK_PATH} ({runbook.detail})")
        report.generated = [g for g in report.generated if g != RUNBOOK_PATH]
    return report
