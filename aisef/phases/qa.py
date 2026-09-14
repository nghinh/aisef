"""Phase 5 — verification: run for real, and never call unexecuted code verified.

Nine verification kinds, each a project command run in a sandbox producing
evidence. The core design principle: **"unconfigured" is not "passed"**. A
suite that reports green because all nine kinds were never run is more
dangerous than having no suite at all.

Therefore each kind has three outcomes, not two:

=================  =======================================================
``passed``         ran and green
``failed``         ran and red
``unconfigured``   no command — warning at story level, **blocked** at the
                   pre-deploy gate unless explicitly waived
=================  =======================================================

Beyond project commands there is one code-level check: **tests with no
assertions**. This is the most common form of fake test — always green,
verifies nothing, and creates a false sense of safety. Mutation testing
catches more, but it is slow and often not installed; this check is cheap
and always available.
"""

from __future__ import annotations

import re
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import split_command
from ..control.outcome import DEFAULT_REASON, Outcome
from ..control.worktree import GitError, WorktreeManager
from ..config import Config
from ..harness import sandbox
from ..harness.guardrails import head_sha, scrub_secrets
from ..harness.observe import EvidenceStore
from ..harness.tools import command_for, image_for, unrunnable_reason

#: Tree label for the verification run — recorded in evidence and `pre-deploy.json`.
TREE_CLEAN = "clean-worktree"
TREE_AGENT = "agent-tree"

#: Dependency dirs not tracked by git — clean worktree borrows them from the project.
#: ponytail: project root only; add `packages/*/node_modules` for monorepos later.
DEPS_DIRS = ("node_modules", ".venv", "venv")


@dataclass(frozen=True)
class Kind:
    id: str
    title: str
    level: sandbox.Level = sandbox.Level.WORKSPACE_WRITE
    #: Only applies when the project has a UI.
    needs_ui: bool = False
    why: str = ""


KINDS: dict[str, Kind] = {
    "unit": Kind("unit", "Unit and functional tests",
                 why="Each unit does its part correctly."),
    "sit": Kind("sit", "System integration tests",
                level=sandbox.Level.WORKSPACE_NETWORK,
                why="Components still work when assembled — where bugs hide most."),
    "api-contract": Kind("api-contract", "API contract tests",
                         level=sandbox.Level.WORKSPACE_NETWORK,
                         why="Clients rely on the contract; silent changes break others."),
    "e2e": Kind("e2e", "End-to-end", level=sandbox.Level.WORKSPACE_NETWORK, needs_ui=True,
                why="The real user journey, not the one in our heads."),
    "uat": Kind("uat", "Acceptance tests against criteria",
                level=sandbox.Level.WORKSPACE_NETWORK,
                why="What the PRD promised, expressed in user language."),
    "perf": Kind("perf", "Performance", level=sandbox.Level.WORKSPACE_NETWORK,
                 why="Thresholds from NFR; without numbers, 'fast' is an opinion."),
    "security": Kind("security", "Security", level=sandbox.Level.READ_ONLY,
                     why="Scan code, dependencies, and secrets leaked into the repo."),
    "accessibility": Kind("accessibility", "Accessibility", needs_ui=True,
                          level=sandbox.Level.WORKSPACE_NETWORK,
                          why="Keyboard and screen-reader users are users too; "
                              "missing labels make screens unusable."),
    "migration": Kind("migration", "Data migration",
                      why="A bad schema upgrade loses user data, and there is "
                          "no way back."),
    "mutation": Kind("mutation", "Mutation testing",
                     why="Catches tests that pass even when code is broken — worse than no tests."),
    "sbom": Kind("sbom", "Software bill of materials (SBOM)", level=sandbox.Level.READ_ONLY,
                 why="Not knowing which libraries you run means you cannot answer "
                     "'are we affected by that vulnerability'."),
    "image-scan": Kind("image-scan", "Deploy image scan",
                       level=sandbox.Level.WORKSPACE_NETWORK,
                       why="Most vulnerabilities live in the image base layer, not in our code."),
}

#: Default commands when the project does not declare one. Only set for kinds
#: with near-standard tooling; the rest stay empty and report "unconfigured".
_DEFAULTS: dict[str, dict[str, str]] = {
    "python": {"security": "bandit -q -r .", "mutation": "mutmut run"},
    "node": {"e2e": "npx playwright test", "mutation": "npx stryker run"},
}

#: Stack-independent commands — only used when the tool is present on the machine.
_UNIVERSAL: dict[str, str] = {
    "sbom": "syft . -o cyclonedx-json=sbom.json",
    "image-scan": "trivy fs --exit-code 1 --severity HIGH,CRITICAL .",
}

_TEST_FILE = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]+\.py$|\.(test|spec)\.[jt]sx?$")
from ..control.tdd import TEST_FUNC as _TEST_FUNC  # noqa: E402 — one regex, one place
_ASSERTION = re.compile(
    r"\bassert\b|\bexpect\s*\(|\bshould\b|assert[A-Z]\w+\(|\.to(Be|Equal|Have|Throw)"
)


@dataclass
class KindResult:
    kind: Kind
    ran: bool = False
    ok: bool = False
    detail: str = ""
    duration_ms: int = 0
    skipped: str = ""
    #: Command exists but the environment is not set up so it cannot run.
    #: Distinct from "test failed": the test did not fail, it never ran.
    #: Conflating the two makes the report point at the wrong fix — measured
    #: on e9, `pre-deploy` reported "✗ unit" when the root cause was a missing `npm ci`.
    unrunnable: str = ""
    #: The framework **determined** this kind cannot apply to this project —
    #: a fact it derived, not a gap someone left (lỗi 165). Distinct from
    #: `skipped`, which means "nobody configured a command": that is an absence
    #: and must block, while this is an answer and must not. Rendered in the
    #: report either way — not applicable never means hidden from the signer.
    not_applicable: str = ""
    #: Ran outside Docker (degraded). Results still count, but the lower
    #: isolation level must be visible — the pre-deploy gate reads this flag.
    degraded: bool = False
    #: Guarantee names this level requires but the provider lacks (`sandbox.Guarantee`) —
    #: "degraded" without naming what is missing leaves the gate unable to state what it trusts.
    missing: list[str] = field(default_factory=list)

    @property
    def configured(self) -> bool:
        return self.ran or not self.skipped

    @property
    def outcome(self) -> Outcome:
        if self.skipped:
            return Outcome.UNCONFIGURED
        if self.unrunnable:
            return Outcome.UNRUNNABLE
        if not self.ran:
            return Outcome.UNCONFIGURED
        return Outcome.PASSED if self.ok else Outcome.FAILED

    def line(self, *, waived: bool = False) -> str:
        o = self.outcome
        if waived and o.must_be_named:
            o = Outcome.WAIVED
        if o is Outcome.UNCONFIGURED:
            return f"  {o.mark} {self.kind.id:12} {self.skipped or DEFAULT_REASON[o]}"
        if o is Outcome.UNRUNNABLE:
            return f"  {o.mark} {self.kind.id:12} unrunnable — {self.unrunnable}"
        if o is Outcome.WAIVED:
            ly_do = self.skipped or self.unrunnable
            if ly_do.startswith("explicit waiver"):   # already self-describing, don't wrap again
                return f"  {o.mark} {self.kind.id:12} {ly_do}"
            return f"  {o.mark} {self.kind.id:12} explicit waiver ({ly_do})"
        extra = f" — {self.detail}" if self.detail and not self.ok else ""
        return f"  {o.mark} {self.kind.id:12} {self.kind.title}{extra}"


@dataclass
class QaReport:
    results: list[KindResult] = field(default_factory=list)
    fake_tests: list[str] = field(default_factory=list)
    waived: list[str] = field(default_factory=list)
    #: SHA of the candidate under test — evidence not tied to a revision cannot
    #: say which code it proves (ADR-004 R1).
    candidate: str = ""
    #: Tree that ran: temp worktree built from `clean_tree` (ADR-005 V6) or
    #: agent tree (with reason when clean worktree could not be created). Guarantee level must be visible.
    tree: str = ""
    clean_tree: str = ""

    @property
    def failed(self) -> list[KindResult]:
        """Kinds that ran and failed. Does **not** include unrunnable kinds:
        those still block, but via `unrunnable`, with the correct reason."""
        return [r for r in self.results if r.ran and not r.ok and not r.unrunnable]

    @property
    def degraded(self) -> list[KindResult]:
        """Kinds that ran but outside Docker."""
        return [r for r in self.results if r.ran and r.degraded]

    @property
    def unrunnable(self) -> list[KindResult]:
        return [r for r in self.results if r.unrunnable and r.kind.id not in self.waived]

    @property
    def unconfigured(self) -> list[KindResult]:
        """Kinds nobody configured — an absence, so it blocks.

        Excludes kinds the framework itself ruled inapplicable: a project with
        no UI cannot have browser E2E, and counting that as "never verified"
        would force the operator to sign a waiver for something already proven
        mechanically — which drains the meaning out of every real waiver.
        """
        return [r for r in self.results
                if r.skipped and not r.not_applicable and r.kind.id not in self.waived]

    @property
    def not_applicable(self) -> list[KindResult]:
        """Kinds the framework determined cannot apply, with the reason it derived."""
        return [r for r in self.results if r.not_applicable]

    @property
    def passed(self) -> bool:
        """Passed at story level: no kind ran red, no fake tests."""
        return not self.failed and not self.unrunnable and not self.fake_tests

    @property
    def release_ready(self) -> bool:
        """Passed at pre-deploy level: every kind **has run** and is green."""
        return self.passed and not self.unconfigured

    def summary(self) -> str:
        lines = ["Verification:"]
        lines += [r.line(waived=r.kind.id in self.waived) for r in self.results]
        if self.fake_tests:
            lines.append(f"  ✗ fake tests: {len(self.fake_tests)} tests with no assertions")
            for t in self.fake_tests[:5]:
                lines.append(f"      {t}")
        if self.unrunnable:
            lines.append(
                "\n⚠️  unrunnable: "
                + ", ".join(r.kind.id for r in self.unrunnable)
                + " — environment not set up, not a test failure"
            )
        if self.unconfigured:
            lines.append(
                "\n⚠️  unconfigured: "
                + ", ".join(r.kind.id for r in self.unconfigured)
                + " — never ran means never verified"
            )
        if self.waived:
            lines.append(f"explicit waiver: {', '.join(self.waived)}")
        if self.tree:
            lines.append(f"verification tree: {self.tree}"
                         + (f" from {self.clean_tree[:7]}" if self.clean_tree else ""))
        return "\n".join(lines)


#: Applicability verdicts. `UNRESOLVED` is a real answer and must block: it says
#: the framework could not decide, which is different from deciding "no".
APPLICABLE, NOT_APPLICABLE, UNRESOLVED = "applicable", "not_applicable", "unresolved"


#: Artefacts whose **presence** proves a project has the surface a kind targets.
#: File evidence first: it cannot be argued with, and it cannot be produced by a
#: plan forgetting to mention something.
_CAPABILITY_FILES: dict[str, tuple[str, ...]] = {
    "api-contract": ("openapi*.y*ml", "openapi*.json", "swagger*.y*ml", "swagger*.json",
                     "**/*.proto", "**/*.graphql", "schema.graphql"),
    "migration": ("migrations/**", "**/migrations/**", "**/*.sql", "alembic.ini",
                  "prisma/schema.prisma", "knexfile*"),
    "image-scan": ("Dockerfile", "Containerfile", "**/Dockerfile"),
    "sit": ("docker-compose*.y*ml", "compose*.y*ml"),
}

#: Requirement wording that **demands** a kind. Deliberately liberal, and safe to
#: be so: a wrong demand blocks and asks a person, while a wrong dismissal drops
#: a required property in silence. This is the opposite error-direction from
#: `Stack.has_ui` (lỗi 163), where a loose match wrongly *imposed* browser
#: checks — here a loose match only ever refuses to let something be skipped.
_CAPABILITY_WORDS: dict[str, str] = {
    "perf": r"(?i)\b(p50|p95|p99|latency|throughput|response time|rps|qps|"
            r"requests? per second)\b|\b\d+\s*ms\b",
    "api-contract": r"(?i)\b(rest|http api|endpoint|graphql|grpc|openapi|swagger|"
                    r"api contract)\b",
    "migration": r"(?i)\b(migrat\w+|schema upgrade|backfill)\b",
    "sit": r"(?i)\b(external service|third[- ]party service|message queue|message broker)\b",
}

#: Kinds no AISEF policy requires of a project. `mutation` is configurable and
#: nothing in the framework demands it, so NOT_APPLICABLE is honest — but the
#: reason must say *policy does not require it*, never "no story asked for it",
#: which would be the plan justifying its own omission.
_POLICY_OPTIONAL = {"mutation"}


def _demanded_by(kind: Kind, project: Path, *, has_ui: bool | None) -> str:
    """Evidence from a **higher authority** that this kind must be verified — "".

    Authority order (lỗi 167): requirement / architecture / project capability
    outranks an approved story contract, which outranks project-shape inference.
    A plan that simply omits a kind must never be able to prove that kind
    unnecessary — that is circular, and it fails silently.
    """
    if kind.needs_ui and has_ui:
        return "the project has screens in its design artefacts, so this UI check applies"

    for pattern in _CAPABILITY_FILES.get(kind.id, ()):
        for hit in project.glob(pattern):
            if hit.is_file() and ".aisef" not in hit.parts and "node_modules" not in hit.parts:
                return f"the project carries `{hit.relative_to(project)}`, a {kind.id} surface"

    rx = _CAPABILITY_WORDS.get(kind.id)
    if rx:
        prd_file = project / "_bmad-output" / "prd.md"
        if prd_file.is_file():
            from ..control.normalize import parse_prd_file
            import re as _re
            for req in parse_prd_file(prd_file).requirements:
                text = f"{req.title} {getattr(req, 'text', '')}"
                if _re.search(rx, text):
                    return (f"{req.id} states a {kind.id} property that must be verified: "
                            f"{text.strip()[:120]}")
    return ""


def applicability(kind: Kind, project: Path, *, has_ui: bool | None = None) -> tuple[str, str]:
    """Does this verification kind apply to this project? `(verdict, evidence)`.

    Derived from **structured, already-approved** plan artifacts — never from
    requirements prose. Sniffing prose is what made a CLI look like a web app
    (lỗi 163: `ui` matched inside the phrase "no ui"), so the authority here is
    two things a human already reviewed at the `stories` gate:

    * each story's `verification_contract` — the plan stating which kinds prove
      that story;
    * each story's `covers` against the PRD's requirement ids — whether the plan
      accounts for every requirement.

    The rule: a kind **no story declares**, on a settled plan that covers **every**
    requirement, is NOT_APPLICABLE — the plan assigned that proof to another kind.
    If any requirement is uncovered, the answer is UNRESOLVED rather than
    NOT_APPLICABLE, and that distinction is the safety net: it is exactly the
    "perf declared N/A merely because nobody configured a threshold" case, which
    must block instead of quietly passing.

    Absent or empty plan → UNRESOLVED. Nothing has been decided yet, so there is
    nothing to read a decision from.
    """
    import json as _json

    # Authority 1 — a requirement, architecture decision, or project capability
    # that demands this kind. It outranks everything below, because the plan must
    # not be able to excuse itself by leaving something out.
    doi_hoi = _demanded_by(kind, project, has_ui=has_ui)
    if doi_hoi:
        return APPLICABLE, doi_hoi

    root = project / "_bmad-output"
    index = root / "stories.index.json"
    if not index.is_file():
        return UNRESOLVED, "no stories index — nothing has been planned to read a decision from"
    try:
        stories = (_json.loads(index.read_text(encoding="utf-8")).get("stories")) or []
    except (OSError, _json.JSONDecodeError) as e:
        return UNRESOLVED, f"stories index unreadable ({e})"
    if not stories:
        return UNRESOLVED, "stories index is empty — no plan decision exists yet"

    declared = {k for s in stories for k in (s.get("verification_contract") or [])}
    if kind.id in declared:
        n = sum(1 for s in stories if kind.id in (s.get("verification_contract") or []))
        return APPLICABLE, f"{n} story/ies declare `{kind.id}` in their verification contract"

    prd_file = root / "prd.md"
    if not prd_file.is_file():
        return UNRESOLVED, "no prd.md — cannot tell whether every requirement is covered"
    from ..control.normalize import parse_prd_file

    want = {r.id for r in parse_prd_file(prd_file).requirements}
    if not want:
        return UNRESOLVED, "prd.md declares no requirement ids — nothing to check coverage against"
    covered = {c for s in stories for c in (s.get("covers") or [])}
    ho = sorted(want - covered)
    if ho:
        return UNRESOLVED, (
            f"`{kind.id}` is in no verification contract, but {len(ho)} requirement(s) are "
            f"covered by no story: {', '.join(ho[:5])} — with the plan incomplete this is "
            f"not knowable, and not knowable is not the same as not applicable")
    if kind.id in _POLICY_OPTIONAL:
        return NOT_APPLICABLE, (
            f"no AISEF policy requires `{kind.id}` of a project, and nothing in this project's "
            f"requirements or capabilities demands it — it is configurable via "
            f"`verify.{kind.id}` when wanted")
    return NOT_APPLICABLE, (
        f"no requirement, architecture decision or project capability demands `{kind.id}`, "
        f"no story declares it, and all {len(want)} requirements are covered by stories whose "
        f"contracts name {', '.join(sorted(declared)) or 'nothing'}")


def tool_image_for(kind_id: str, config: Config | None) -> str:
    """Pinned image this kind's tool runs in — "" means use the project image.

    Keeps tooling risk out of product risk (lỗi 168). The network a scanner needs
    to fetch its vulnerability database is not the network the application under
    verification is granted: different trust boundaries, and conflating them is
    what made an image scan look impossible.
    """
    raw = str((config or {}).get("verify.tool_images", "") or "") if config is not None else ""
    for phan in raw.split(","):
        if "=" in phan:
            k, _, v = phan.partition("=")
            if k.strip() == kind_id:
                return v.strip()
    return ""


def _tool_present(command: str, project: Path) -> bool:
    """Is the tool this command actually runs installed here?

    Declaring a command whose tool is absent makes the kind report "ran and
    red", which misreports the root cause: the project did not fail a check, the
    machine could not run one. That is `unconfigured`.

    `which(argv[0])` is not enough for a launcher. `npx playwright test` has
    argv[0] = `npx`, which *is* installed — npx would then try to **download**
    playwright, and inside a network-isolated verification sandbox that surfaces
    as a failing test run. For a launcher the honest question is whether the tool
    resolves **locally**, so `npx X` is checked against `node_modules/.bin/X`
    (and a global X, for a tool installed machine-wide).
    """
    import shutil as _shutil

    argv = command.split()
    if not argv:
        return False
    if argv[0] == "npx" and len(argv) > 1:
        # Project-local only, deliberately — **not** a host-PATH fallback. The
        # command runs inside the verification sandbox, and a globally installed
        # npm bin does not exist in that container; `node_modules/` travels with
        # the workspace, so it is the only signal that survives the boundary.
        # Measured: playwright is on this host's PATH
        # (~/.npm-global/bin/playwright) while the Docker run still reported
        # "tool not installed" — asking the host would have answered a question
        # about the wrong machine.
        return (project / "node_modules" / ".bin" / argv[1]).exists()
    return bool(_shutil.which(argv[0]))


def command_for_kind(kind_id: str, project: Path, config: Config | None) -> str:
    """Command for a kind: explicit config wins, then stack-based defaults."""
    if config is not None:
        key = f"verify.{kind_id}"
        if key in config and str(config[key]).strip():
            return str(config[key]).strip()
    if kind_id == "unit":
        return command_for("test", project, config)
    if kind_id == "security":
        configured = command_for("sast", project, config)
        if configured:
            return configured
    marker = "node" if (project / "package.json").is_file() else (
        "python" if (project / "pyproject.toml").is_file() else ""
    )
    # Inferred commands — stack and universal alike — only when the tool is
    # actually present. The rule was already written for `_UNIVERSAL` one branch
    # below; `_DEFAULTS` returned unconditionally and so broke it (lỗi 164).
    # Measured on marks-cli: `npx stryker run` was handed back with stryker
    # absent, and `mutation` reported FAILED — `npm error EAI_AGAIN …
    # registry.npmjs.org` — because the verification sandbox is correctly
    # network-isolated. A missing tool recorded as a failing verification of the
    # project inverts what a red gate means.
    default = _DEFAULTS.get(marker, {}).get(kind_id, "")
    if default and _tool_present(default, project):
        return default

    universal = _UNIVERSAL.get(kind_id, "")
    if universal and _tool_present(universal, project):
        return universal
    return ""


def find_fake_tests(project: Path | str, files: list[str] | None = None) -> list[str]:
    """Find tests with no assertions.

    No semantic analysis: just one narrow question — does this file have a
    test function with absolutely no assertions. The narrow scope keeps false
    positives rare, and the fake-test pattern it catches is the most common one.
    """
    project = Path(project)
    if files is None:
        files = _project_files(project)
    # `.claude` holds 155 installed skills, and the project must commit them,
    # so git lists them among its own files. A skill's test script is not the
    # project's test, and this check blocks a story (bug 113's family).
    candidates = [project / f for f in files
                  if _TEST_FILE.search(f) and not f.startswith(_KHUNG)]

    out = []
    for path in sorted(candidates):
        if not path.is_file() or path.suffix not in (".py", ".js", ".ts", ".jsx", ".tsx", ".go"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _TEST_FUNC.search(text) and not _ASSERTION.search(text):
            # `/` always. `relative_to` yields the native form, and every
            # consumer — evidence, the gate, git output it is compared with —
            # speaks `/`. On Windows this returned `tests\\test_a.py` and
            # matched nothing.
            out.append(path.relative_to(project).as_posix())
    return out


#: The framework's own directories inside a project. Committed on purpose —
#: a story worktree is a checkout — and therefore listed by git as project
#: files, which they are not.
_KHUNG = (".claude/", ".opencode/", ".aisef/", "_bmad-output/")

#: Non-source vendor directories. Only used when git is unavailable.
_VENDOR = ("node_modules", ".git", ".venv", "venv", "dist", "build", "references",
           "__pycache__", ".aisef", ".claude", ".opencode")


def _project_files(project: Path) -> list[str]:
    """Project files. Ask git first — it knows exactly what is tracked,
    including paths excluded by `.gitignore` that we cannot guess."""
    import subprocess

    try:
        # `--others --exclude-standard` to also see **uncommitted** files:
        # a freshly written fake test is not in the git index yet, and that is
        # exactly when it most needs to be caught.
        proc = subprocess.run(
            ["git", "-C", str(project), "ls-files",
             "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if proc.returncode == 0:
            return [line for line in proc.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        pass

    out = []
    for path in project.rglob("*"):
        rel = path.relative_to(project)
        if not path.is_file() or any(part in _VENDOR for part in rel.parts):
            continue
        # `/` always: the git branch above returns POSIX paths and every
        # consumer's pattern is written that way. `str(rel)` gave
        # `tests\test_a.py` on Windows, `_TEST_FILE` matched nothing, and the
        # fake-test check silently found zero files in any project without git.
        out.append(rel.as_posix())
    return out


#: A runner that started fine and matched **zero** tests. Not a red result and
#: not the story's fault: `verify.accessibility` is `playwright test --grep
#: @a11y`, and until some story writes an `@a11y` test that command finds
#: nothing. Reported as FAILED it read as "accessibility is broken" on every
#: story of the project (lỗi 134, todo-oc 2026-09-13) — the same "not
#: configured != red" rule the `test` tool has had since lỗi 2/8, applied to
#: the other verification kinds.
_KHONG_CO_TEST = ("no tests found", "no tests ran", "found no tests",
                  "no tests were found", "collected 0 items")


def _unrunnable_reason(exit_code: int, detail: str, provider_error: str = "") -> str:
    ly_do = unrunnable_reason("", exit_code, detail, provider_error=provider_error)
    if ly_do:
        return ly_do
    low = detail.lower()
    if any(m in low for m in _KHONG_CO_TEST):
        return ("the command matched no tests — it started and found nothing to run, "
                "which is not a failing test. Either no story has written tests of "
                "this kind yet, or the selector in the configured command matches "
                "nothing")
    return ""


def _verification_tree(
    stack: ExitStack, project: Path, sha: str, *, clean: bool,
) -> tuple[Path, str, str, dict[str, Path]]:
    """Tree to **run** verification in: temp worktree from ``sha`` (ADR-005 V6) or
    the current working tree. Returns ``(workspace, tree label, clean SHA, mounts)``.

    When a clean worktree cannot be created (no git, no commits, unknown SHA),
    falls back to the current tree **and says so** in the label — inability to
    create a worktree is not a test failure, and reduced guarantees must not be
    silent (invariant 10). The worktree is cleaned up by ``stack``.
    """
    if not clean:
        return project, TREE_AGENT, "", {}
    if not sha:
        return project, f"{TREE_AGENT} (no git/HEAD to create clean worktree)", "", {}
    try:
        cay = stack.enter_context(WorktreeManager(project).temporary(sha))
    except GitError as e:
        return project, f"{TREE_AGENT} (could not create clean worktree: {e})", "", {}
    mounts = {d: project / d for d in DEPS_DIRS if (project / d).is_dir()}
    return cay, TREE_CLEAN, sha, mounts


def run_suite(
    project: Path | str,
    *,
    config: Config | None = None,
    only: list[str] | None = None,
    has_ui: bool = True,
    story_id: str = "",
    artifact_root: Path | str | None = None,
    changed: list[str] | None = None,
    candidate: str = "",
    clean: bool = True,
) -> QaReport:
    """Run the verification suite.

    ``candidate`` is the SHA under test (ADR-004 R1). When omitted, HEAD of the
    current tree is used: project-level QA must also answer "which revision does
    this result belong to", not only story-level QA.

    ``clean`` (ADR-005 V6, on by default and also requires `verify.clean_tree`):
    commands run in a **temp worktree built from ``candidate``**, not the current
    working tree. Harbor stops the env agent then runs the verifier in a separate
    container; here the agent tree may carry uncommitted shims like
    `node_modules/.bin/vitest`, `pytest.ini`, `conftest.py` — the worktree from
    SHA does not have them. The project's `node_modules`/`.venv` are mounted in
    (Docker: bind mount; degraded: symlink) as the tree normally has. Cost:
    **untracked** files tests need (`.env.test`, hand-generated fixtures) are also
    absent — commit them, or disable `verify.clean_tree`; disabling sets
    `tree = "agent-tree"`, recorded in evidence and `pre-deploy.json`. Story level
    (`verify_candidate`) passes ``clean=False``: the worktree is already frozen and
    the write-scope guard blocks out-of-scope changes. `find_fake_tests` still reads
    the current tree: a freshly written fake test not yet committed is exactly when
    it needs to be caught.
    """
    project = Path(project)
    cfg = config or Config.load(project)
    candidate = candidate or head_sha(project)
    waived = [
        w.strip() for w in str(cfg.get("verify.waived", "") or "").split(",") if w.strip()
    ]
    report = QaReport(waived=waived, candidate=candidate)
    store = (EvidenceStore(artifact_root, candidate=candidate)
             if (story_id and artifact_root) else None)

    with ExitStack() as stack:
        cay, report.tree, report.clean_tree, mounts = _verification_tree(
            stack, project, candidate, clean=clean and bool(cfg.get("verify.clean_tree", True)),
        )
        for kind in KINDS.values():
            if only and kind.id not in only:
                continue
            result = KindResult(kind=kind)
            if kind.id in waived:
                # Waiver is a **human decision**, already recorded. Running and
                # still counting as failed makes the waiver meaningless, and the
                # report contradicts itself: one line says "explicit waiver" while
                # another says ✗.
                ly_do = str(cfg.get("verify.waiver_reason", "") or "").strip()
                result.skipped = "explicit waiver (verify.waived)" + (f": {ly_do}" if ly_do else "")
                report.results.append(result)
                continue
            if kind.needs_ui and not has_ui:
                # Derived from the settled plan (screens across every story),
                # not from operator judgement — so it is `not_applicable`, which
                # is stated in the report but does not block release_ready.
                result.skipped = result.not_applicable = "project has no UI"
                report.results.append(result)
                continue

            command = command_for_kind(kind.id, project, cfg)
            if not command:
                # No command: the kind's fate is an applicability question, not a
                # shrug. Derived from the settled plan (lỗi 167) — NOT_APPLICABLE
                # is an answer and does not block; UNRESOLVED means the framework
                # could not decide and blocks exactly as an unconfigured kind does.
                verdict, vi_sao = applicability(kind, project, has_ui=has_ui)
                if verdict == NOT_APPLICABLE:
                    result.skipped = result.not_applicable = vi_sao
                else:
                    result.skipped = ("command not configured (verify.%s) — %s"
                                      % (kind.id, vi_sao))
                report.results.append(result)
                continue


            anh_cong_cu = tool_image_for(kind.id, cfg)
            if artifact_root:
                from ..harness.runlog import run_log
                run_log(artifact_root, f"qa:{kind.id} RUN cmd={command}"
                        + (f" image={anh_cong_cu}" if anh_cong_cu else ""))
            sb = sandbox.run(
                sandbox.SandboxSpec(
                    workspace=cay,
                    cmd=split_command(command),
                    level=kind.level,
                    image=anh_cong_cu or image_for(project, cfg),
                    entrypoint="" if anh_cong_cu else None,
                    timeout_seconds=cfg["run.timeout_seconds"],
                    allow_degraded=cfg["sandbox.allow_degraded"],
                    use_docker=cfg["sandbox.use_docker"],
                    provider=cfg["sandbox.provider"],
                    mounts=mounts,
                )
            )
            result.ran = True
            result.ok = sb.ok
            result.duration_ms = sb.duration_ms
            result.degraded = bool(getattr(sb, "degraded", False))
            result.missing = list(getattr(sb, "missing", []))
            # Detect signals on the **full** output, not the truncated tail:
            # "Cannot find module" appears at the top of the stack trace while
            # `detail` only keeps the last 5 lines. Measured on e9: after the
            # first patch, `mutation` was still counted as a real test failure
            # because of this.
            # Scrub secrets **before** truncation (ADR-005 V1): `tail` goes into
            # `_bmad-output`, a directory committed with the project.
            day_du, che = scrub_secrets((sb.stdout + "\n" + sb.stderr).strip())
            # Drop the dev server's access log before taking the tail. Playwright's
            # `webServer` writes one line per HTTP request into the same stream, so
            # the last five lines of a failing e2e run were five `GET / 200` lines
            # and the gate message taught the reader nothing (lỗi 137). Exactly the
            # problem `ToolResult.tail` was given `_NOISE` for on 2026-09-09 — for
            # the `test` tool only; this path kept its own truncation.
            from ..harness.tools import _NOISE

            moi = [x for x in day_du.splitlines() if not _NOISE.search(x)]
            result.detail = "\n".join((moi or day_du.splitlines())[-5:])
            result.unrunnable = _unrunnable_reason(
                getattr(sb, "exit_code", 0), day_du, getattr(sb, "provider_error", ""))
            report.results.append(result)
            if artifact_root:
                from ..harness.runlog import one_line, run_log
                status = "PASS" if sb.ok else "FAIL"
                unrun = " unrunnable" if result.unrunnable else ""
                run_log(artifact_root, f"qa:{kind.id} {status} {sb.duration_ms}ms{unrun}")
                if not sb.ok:
                    run_log(artifact_root, f"qa:{kind.id} output: " + one_line(result.detail))
            if store:
                # Test **names**, when this suite's output is a log we can read.
                # The criteria gate reads names to match `AC-<story>-<i>`, and a
                # story whose criteria are browser behaviour can only name them
                # in e2e titles (lỗi 132). `record()` in `harness/tools` does
                # this for the `test` tool; this path never went through it.
                ten: dict = {}
                from ..harness.testlog import parse as parse_testlog

                doc = parse_testlog(day_du)
                if doc.format:
                    ten = doc.to_evidence()
                store.tool_run(
                    story_id, f"qa:{kind.id}", ok=sb.ok, duration_ms=sb.duration_ms,
                    detail={"command": command, "tail": result.detail[:500],
                            "tree": report.tree, "clean_tree": report.clean_tree,
                            **ten,
                            **({"redacted": che} if che else {})},
                )

    report.fake_tests = find_fake_tests(project, changed)
    if store and report.fake_tests:
        store.tool_run(story_id, "qa:fake-tests", ok=False,
                       detail={"files": report.fake_tests})
    return report
