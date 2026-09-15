"""Real harness tools — what the agent calls instead of typing commands.

Only things whose **run evidence is what the gate reads** live here: test,
lint, sast. Screenshots and mockup comparison are done by the harness after
the agent turn (if the agent screenshots itself, it is both author and
grader); commits use `git` directly, and the `git-stage` guard watches there.

Each tool here does three things that "just let the agent run Bash" cannot:

1. **Fixed project commands**, not invented by the agent each turn. `npm test`
   or `pytest -q` is the project's decision, not a place for guessing.
2. **Runs in the sandbox** — same privilege level for every story, every machine.
3. **Records evidence.** This is the key point: the story gate and
   `completion` guard read evidence, not the agent's narrative. No record
   means it never ran.

Each tool includes a "when to call" string — this goes straight into the
prompt, because a tool without a correct-use description will be called at
the wrong time.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import quote_command, split_command
from ..config import Config
from . import sandbox, verify_image
from .guardrails import scrub_secrets
from .observe import EvidenceStore

#: Trailing lines written to `detail.tail`. Do not increase: `tail` goes into
#: the gate and guard prompt (budget B5); full text is in the `.log` file
#: next to the evidence store.
TAIL_LINES = 20

#: Sandbox images per stack. `alpine` has no node or python, so running
#: `npm test` in it would fail due to **missing tools**, not wrong code —
#: and a gate reporting red for the wrong reason gets ignored for two days.
STACK_IMAGES: list[tuple[str, str]] = [
    ("package.json", "node:22-alpine"),
    # A bare python image has no test runner; the harness-built image does
    # (`verify_image.RECIPES`, D-028).
    ("pyproject.toml", verify_image.RECIPES["python"].name),
    ("setup.py", verify_image.RECIPES["python"].name),
    ("go.mod", "golang:1.23-alpine"),
    ("Cargo.toml", "rust:1-alpine"),
    ("composer.json", "php:8-cli-alpine"),
    ("Gemfile", "ruby:3-alpine"),
]


def image_for(project: Path | str, config: Config | None = None) -> str:
    """Sandbox image: config wins, then stack-matching image, then default."""
    if config is not None and str(config.get("sandbox.image", "")).strip():
        return str(config["sandbox.image"]).strip()
    project = Path(project)
    for marker, image in STACK_IMAGES:
        if (project / marker).is_file():
            return image
    return sandbox.DEFAULT_IMAGE


#: Default commands by project marker file. Tuple of (test, lint, sast).
_STACK_COMMANDS: list[tuple[str, dict[str, str]]] = [
    ("pyproject.toml", {"test": "pytest -q", "lint": "ruff check .", "sast": "bandit -q -r ."}),
    ("setup.py", {"test": "pytest -q", "lint": "ruff check .", "sast": "bandit -q -r ."}),
    ("go.mod", {"test": "go test ./...", "lint": "go vet ./...", "sast": "gosec ./..."}),
    ("Cargo.toml", {"test": "cargo test", "lint": "cargo clippy -- -D warnings", "sast": "cargo audit"}),
    ("pubspec.yaml", {"test": "flutter test", "lint": "flutter analyze", "sast": ""}),
    ("composer.json", {"test": "composer test", "lint": "composer lint", "sast": ""}),
    ("Gemfile", {"test": "bundle exec rspec", "lint": "bundle exec rubocop", "sast": "bundle exec brakeman -q"}),
]


@dataclass
class Tool:
    name: str
    when: str          # when to call — goes into the prompt
    level: sandbox.Level = sandbox.Level.WORKSPACE_WRITE


TOOLS: dict[str, Tool] = {
    "test": Tool(
        "test",
        "After every code change, and required before declaring the story done. "
        "Run before writing code to see a failing test (RED) then write to make it pass.",
    ),
    "lint": Tool(
        "lint",
        "Before committing. Lint errors must be fixed, not suggestions.",
    ),
    "sast": Tool(
        "sast",
        "Before committing, when the story touches authentication, authorization, data "
        "queries, file uploads, or any data from users.",
        level=sandbox.Level.READ_ONLY,
    ),
}


@dataclass
class ToolResult:
    name: str
    ok: bool
    exit_code: int = 0
    stdout: str = ""
    #: Tool could not load (MODULE_NOT_FOUND, command not found...) — not a
    #: test failure. Dogfood par 2026-09-05: `node --test src/` failed due to
    #: wrong command, guard `completion` blocked Stop ~10 times per turn,
    #: 3 stories burned $17.
    unrunnable: str = ""
    stderr: str = ""
    duration_ms: int = 0
    skipped: str = ""      # reason it could not run (no command for this stack)
    degraded: bool = False
    detail: dict = field(default_factory=dict)
    #: Full-text log file (secrets redacted) when output exceeds `TAIL_LINES`
    #: and a story is available — `aisef tool` prints this path in the summary.
    log: str = ""

    @property
    def ran(self) -> bool:
        return not self.skipped

    def summary(self) -> str:
        if self.skipped:
            return f"{self.name}: skipped — {self.skipped}"
        mark = "✅" if self.ok else "✗"
        missing = ", ".join(self.detail.get("missing") or [])
        extra = f" (sandbox degraded — missing {missing or 'guarantees'})" if self.degraded else ""
        # "Không chạy được" phải hiện ngay ở dòng đầu, không nằm chờ trong
        # `detail`: harness đã phân loại xong mà người đọc chỉ thấy "✗ exit 127"
        # thì họ đi tìm lỗi trong mã của mình. Đo 13/09/2026 trên một dự án mới:
        # `aisef tool test` in đúng hai dòng, không dòng nào nói "chưa chạy được".
        chua_chay = f" — NOT RUNNABLE: {self.unrunnable}" if self.unrunnable else ""
        mark = "○" if self.unrunnable else mark
        return (f"{mark} {self.name} — exit {self.exit_code}, "
                f"{self.duration_ms}ms{extra}{chua_chay}")

    def output(self) -> tuple[str, int]:
        """(stdout + stderr with secrets redacted, redaction count). All printed
        or recorded output goes through here — redact **before** truncating so
        a key straddling the `tail` boundary does not leak its second half
        (ADR-005 V1)."""
        return scrub_secrets((self.stdout + "\n" + self.stderr).strip())

    def tail(self, lines: int = 40) -> str:
        """Trailing output — where errors usually appear.

        Server access logs are dropped first. Playwright's `webServer` writes
        one line per HTTP request into the same stream as the test results, so
        a failing run's last 40 lines were 40 `GET /js/app.js 200` lines and
        the reader learned nothing (measured on `todo-e2e`, 2026-09-09: four
        consecutive failures whose logged output was entirely access log).
        Nothing is lost — the full text is in the evidence log file.
        """
        all_lines = self.output()[0].splitlines()
        keep = [x for x in all_lines if not _NOISE.search(x)]
        return "\n".join((keep or all_lines)[-lines:])


def detect_commands(project: Path | str) -> dict[str, str]:
    """Detect project test/lint/sast commands from actual files on disk."""
    project = Path(project)
    pkg = project / "package.json"
    if pkg.is_file():
        return _from_package_json(pkg)
    for marker, commands in _STACK_COMMANDS:
        if (project / marker).is_file():
            return dict(commands)
    return {"test": "", "lint": "", "sast": ""}


def _from_package_json(path: Path) -> dict[str, str]:
    """Only declare scripts that **actually exist**.

    `npm test` when package.json does not define a `test` script exits non-zero
    for the wrong reason — the gate would report "test failed" when in reality
    the project has no tests. These two situations must be distinguished.
    """
    try:
        scripts = json.loads(path.read_text(encoding="utf-8")).get("scripts") or {}
    except (json.JSONDecodeError, OSError):
        scripts = {}
    out = {"test": "", "lint": "", "sast": "npm audit --omit=dev"}
    if "test" in scripts:
        out["test"] = "npm test --silent"
    if "lint" in scripts:
        out["lint"] = "npm run lint --silent"
    elif "typecheck" in scripts:
        out["lint"] = "npm run typecheck --silent"
    return out


def command_for(name: str, project: Path | str, config: Config | None = None) -> str:
    """Command for a tool: config wins, auto-detection is the fallback."""
    if config is not None:
        key = f"tools.{name}"
        if key in config:
            configured = str(config[key]).strip()
            if configured:
                return configured
    return detect_commands(project).get(name, "")


def run_tool(
    name: str,
    project: Path | str,
    *,
    story_id: str = "",
    artifact_root: Path | str | None = None,
    config: Config | None = None,
    extra_args: list[str] | None = None,
    candidate: str = "",
) -> ToolResult:
    """Run a tool in the sandbox and record evidence.

    ``candidate`` is the SHA of the build under test — stamped into evidence
    so the gate knows which build this result belongs to (ADR-004 R1)."""
    if name not in TOOLS:
        raise ValueError(f"tool does not exist: {name}. Available: {', '.join(sorted(TOOLS))}")

    project = Path(project)
    cfg = config or Config.load(project)
    command = command_for(name, project, cfg)
    if not command:
        res = ToolResult(name=name, ok=False, skipped="project has not declared a command for this tool")
        record(res, story_id, artifact_root, candidate)
        return res

    argv = split_command(command) + (extra_args or [])
    if artifact_root:
        from .runlog import run_log
        run_log(artifact_root, f"tool={name} RUN cmd={command}")
    level = TOOLS[name].level
    if cfg["sandbox.tools_network"] and level is not sandbox.Level.READ_ONLY:
        # Project needs to install deps before tests can run. Enabling
        # network is the project's explicit decision, not the default.
        level = sandbox.Level.WORKSPACE_NETWORK
    sb = sandbox.run(
        sandbox.SandboxSpec(
            workspace=project,
            cmd=argv,
            level=level,
            image=image_for(project, cfg),
            timeout_seconds=cfg["run.timeout_seconds"],
            allow_degraded=cfg["sandbox.allow_degraded"],
            use_docker=cfg["sandbox.use_docker"],
            provider=cfg["sandbox.provider"],
        )
    )
    res = ToolResult(
        name=name,
        ok=sb.ok,
        exit_code=sb.exit_code,
        stdout=sb.stdout,
        stderr=sb.stderr,
        duration_ms=sb.duration_ms,
        degraded=sb.degraded,
        detail={"command": command, **sb.to_evidence()},
    )
    if not sb.ok:
        res.unrunnable = unrunnable_reason(
            name, sb.exit_code, sb.stdout + "\n" + sb.stderr,
            provider_error=sb.provider_error,
        )
    res.log = record(res, story_id, artifact_root, candidate)
    if artifact_root:
        from .runlog import one_line, run_log
        status = "SKIP" if res.skipped else ("PASS" if res.ok else "FAIL")
        unrun = f" {outcome_kind(res)} unrunnable={res.unrunnable}" if res.unrunnable else ""
        run_log(artifact_root, f"tool={name} {status} exit={sb.exit_code} {sb.duration_ms}ms{unrun}")
        if not res.ok and not res.skipped:
            # Exit code alone does not say what broke, and the reader then has
            # to go find the evidence file to learn anything at all.
            run_log(artifact_root, f"tool={name} output: " + one_line(res.tail(TAIL_LINES)))
    return res


#: Server access logs interleaved into the test stream: Playwright's
#: `[WebServer]` tag, and the common log format any static server prints.
_NOISE = re.compile(r'^\s*(?:\[[\w -]*[Ss]erver[\w -]*\]\s*)?'
                    r'\S+ - - \[[^\]]+\] "(?:GET|POST|HEAD|PUT|DELETE) [^"]*" \d{3}')

#: Signatures of "tool could not load", not "test failed". 127 is the POSIX
#: code for command not found; the rest are how other runtimes say the same
#: thing. Conflating the two misdirects the report to the wrong fix.
MISSING_TOOL = (
    "command not found",
    "not found",
    "cannot find module",
    "module_not_found",
    "no such file or directory",
    "is not recognized as an internal or external command",
    # `python -m pytest` in an image without pytest prints
    # `/usr/local/bin/python: No module named pytest` and exits 1 — the
    # runner never started, yet 1.7.2 read it as "tests are red" and told
    # three sessions to fix code that was not at fault (LedgerLock
    # 2026-09-15, lỗi 183 / D-029). The same words from *inside* a test
    # (`ModuleNotFoundError: No module named 'x'`) are a missing project
    # dependency — `NO_DEPENDENCIES` routes those to `NO_SETUP`.
    "no module named",
)

#: What a non-passing tool run **is** (D-029). Three different next actions:
#: fix the code, install the tool, or fix the environment — and the gate,
#: the run log and the evidence must say which, not just "not ok".
TEST_FAILED = "TEST_FAILED"
TOOL_FAILED = "TOOL_FAILED"
TOOL_UNRUNNABLE = "TOOL_UNRUNNABLE"
ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"


#: Manifests whose absence means **the project is not here**, not that the
#: tool is missing. npm's `ENOENT ... package.json` matches "no such file or
#: directory" and was reported as "npm not installed" — on a machine where npm
#: had just run the same suite minutes earlier. It matters because the nop
#: control deliberately runs at the parent SHA, where a greenfield project's
#: first story has not created the manifest yet: read as "tool missing" that
#: is an environment failure the agent cannot fix, and the first story of every
#: new project failed the gate forever (measured 2026-09-09 on `todo-e2e`).
MANIFESTS = (
    "package.json", "pyproject.toml", "setup.py", "requirements.txt",
    "cargo.toml", "go.mod", "pom.xml", "build.gradle", "gemfile", "composer.json",
)

#: Markers meaning the program started fine but the **project's** own setup is
#: absent from this tree: dependencies were never installed here. The first
#: story of a JS project hits this at its baseline commit — `node_modules`
#: lives in the worktree the story is about to build, and there is nothing to
#: borrow from a project root that never installed them either.
NO_DEPENDENCIES = ("cannot find module", "cannot find package",
                   "module_not_found", "modulenotfounderror")

#: Stable prefix shared by both, so callers can tell "this commit has nothing
#: to run" from "this machine is missing the tool".
NO_SETUP = "no runnable setup in this tree"
NO_MANIFEST = f"{NO_SETUP} — there is no project manifest here"


def unrunnable_reason(name: str, exit_code: int, output: str, *, provider_error: str = "") -> str:
    """One-line reason if the run is "unrunnable"; "" if it is a real result.
    For `test`, only conclude unrunnable when **no test passed** — a failing
    test with a "not found" message is still a test failure. ``provider_error``
    is a sandbox infrastructure error (daemon, image pull) — command never ran,
    conclude immediately."""
    if provider_error:
        return f"sandbox infrastructure error ({provider_error}) — command did not run; check daemon/image and retry"
    low = output.lower()
    hit = next((m for m in MISSING_TOOL if m in low), "")
    if exit_code != 127 and not hit:
        return ""
    if name == "test":
        from .testlog import parse as parse_testlog
        if parse_testlog(output).passed:
            return ""
    if hit == "no such file or directory" and any(m in low for m in MANIFESTS):
        return NO_MANIFEST
    if any(m in low for m in NO_DEPENDENCIES):
        return (f"{NO_SETUP} — the project's dependencies are not installed here; "
                "install them at the **project root**, which is where a clean "
                "worktree resolves them from")
    return f"tool not installed or cannot load ({hit or 'exit 127'}) — set up the environment or fix the command and retry"


def outcome_kind(res: "ToolResult") -> str:
    """Classify a finished tool run: ``""`` when it passed or was skipped,
    otherwise one of `TEST_FAILED` / `TOOL_FAILED` (a real result),
    `TOOL_UNRUNNABLE` (the declared tool is absent or cannot load) or
    `ENVIRONMENT_FAILURE` (the project's setup or the sandbox itself).
    The lack of a test runner is never behavioural evidence."""
    if res.ok or res.skipped:
        return ""
    if not res.unrunnable:
        return TEST_FAILED if res.name == "test" else TOOL_FAILED
    if res.unrunnable.startswith(NO_SETUP) or res.unrunnable.startswith("sandbox infrastructure error"):
        return ENVIRONMENT_FAILURE
    return TOOL_UNRUNNABLE


#: Evidence name for baseline (ADR-004 R9) — test suite run at the parent
#: candidate **before** the developer session. Not recorded as `test`:
#: guard `completion`, TDD `red_before_green`, "criteria with tests", and
#: the behavior log all read `tool_run test` as "this turn's test run", and
#: a pre-existing red baseline would block Stop, falsely satisfy TDD, and
#: be attributed by the log as a regression caused by the story.
BASELINE_RUN = "test:baseline"

#: Evidence name for nop control (ADR-005 V3) — test suite run at the
#: **parent SHA** with the story's test files copied in, **after** freezing
#: the candidate (carries `candidate`). Same reason for not recording as
#: `test`: its expected result is **red**, and a red `test` record would
#: block Stop, falsely satisfy TDD, and be attributed as a regression.
NOP_RUN = "test:nop"


def record(res: ToolResult, story_id: str, artifact_root, candidate: str = "",
           *, name: str = "", extra: dict | None = None) -> str:
    """Record evidence. No story_id means no recording — tools run outside a
    story context (e.g. manual invocation) should not pollute story records.

    ``name`` records under a different name than the tool (baseline records as
    `test:baseline`); ``extra`` adds keys to `detail`. Record shape stays in
    one place.

    Returns the full-text log path `evidence/<story>-<tool>-<seq>.log` when
    output exceeds `TAIL_LINES` (ADR-005 V11 A), "" when nothing was
    truncated. Both `tail` and log have secrets redacted (V1);
    `detail.redacted` = redaction count."""
    if not story_id or artifact_root is None:
        return ""
    full, redacted = res.output()
    lines = full.splitlines()
    detail = {
        "exit_code": res.exit_code,
        "skipped": res.skipped,
        "unrunnable": res.unrunnable,
        "outcome": outcome_kind(res),
        "degraded": res.degraded,
        "tail": "\n".join(lines[-TAIL_LINES:]),
        **res.detail,
    }
    if redacted:
        detail["redacted"] = redacted
    if res.name == "test" and not res.skipped:
        # Which tests ran, pass/fail, coverage — the criteria gate (G5) and
        # `coverage.min` (G10b) read from here, not from stdout again.
        # Unconditional: an empty `test_format` is itself the signal the gate
        # reads to say "this reporter does not print names".
        from .testlog import parse as parse_testlog

        detail.update(parse_testlog(full).to_evidence())
    elif not res.skipped and not res.unrunnable:
        # Every other suite too, when its output is a test log we can read.
        # `testlog` has understood `playwright-list` all along, but the parse
        # only ever ran for the `test` tool — so an e2e suite recorded zero
        # test names, and a story whose criteria are browser behaviour had no
        # way to satisfy "criteria have tests" (lỗi 132). Conditional on the
        # parser recognising the format, so a non-test tool's output is not
        # dressed up as one.
        from .testlog import parse as parse_testlog

        doc = parse_testlog(full)
        if doc.format:
            detail.update(doc.to_evidence())
    detail.update(extra or {})
    store = EvidenceStore(artifact_root, candidate=candidate)
    event = store.tool_run(
        story_id, name or res.name, ok=res.ok, duration_ms=res.duration_ms, detail=detail,
    )
    if len(lines) <= TAIL_LINES:
        return ""
    # Full text next to the evidence store, filename carries `seq` to match
    # the record; `:` in `test:baseline` becomes `-` for cross-platform filenames.
    log = store.path(story_id).with_name(
        f"{story_id}-{(name or res.name).replace(':', '-')}-{event.seq}.log")
    log.write_text(full + "\n", encoding="utf-8")
    return str(log)


def _cung_ban(binary: str) -> bool:
    """Is the `aisef` on PATH the same installation the harness is running?

    It has to be. The compiled hook, and every tool the agent is told to
    call, run **that** binary while the story runs on **this** code, and
    nothing in between says so. Measured 2026-09-13 on `todo-cli`: the
    harness ran the source tree while `~/.local/bin/aisef` was a pipx
    install three minor versions behind, so every guard the whole dogfood
    recorded came from code that had none of the fixes being tested (lỗi
    119). Skew is silent by construction — the old binary answers every call
    successfully, by the old rules.

    Identity is the **path this process was started from**, not a version
    string: `__version__` comes from installed metadata, which in a source
    checkout is whatever happens to be installed and can match by accident.
    Started some other way (`python -m aisef.cli`, a test, an embedding)?
    Then the answer is no, and the fallback — this interpreter plus the
    module — is the running code by definition.
    """
    goc = sys.argv[0] if sys.argv else ""
    if not goc:
        return False
    duong = Path(goc) if (os.sep in goc or (os.altsep or "") in goc) else None
    if duong is None:
        tim = shutil.which(goc)
        if not tim:
            return False
        duong = Path(tim)
    try:
        return duong.resolve() == Path(binary).resolve()
    except OSError:
        return False


def aisef_argv() -> list[str]:
    """The framework command as **argv**, which is what every caller needs.

    Returned as a list, never a string: the last fallback is three words, and
    a three-word command squeezed into one string is later read back as one
    filename — the OpenCode plugin ran `bun: command not found: "<python> -m
    aisef.cli"` on every tool call and, because a failed guard call is not a
    block, the whole run finished with zero guards (measured 2026-09-09 on
    `todo`: 46 sessions, 0 guard events, story exhausted on "guard ran").
    """
    if (tren_path := shutil.which("aisef")) and _cung_ban(tren_path):
        return ["aisef"]
    # Source repo: `bin/aisef` sits next to the package. Wheel installs do
    # **not** have that directory — before 0.2.0 this returned
    # `<site-packages>/bin/aisef`, a non-existent path, and the compile hook
    # silently ran no guards (measured 2026-09-06 on a clean venv). Check
    # existence before returning.
    # `bin/aisef` is a POSIX shell script. It exists in a source checkout on
    # every OS, but Windows cannot execute it — `is_file()` says yes and
    # `CreateProcess` says no, which is how a hook gets written pointing at
    # something that cannot run (bug 31's shape, on the other platform).
    trong_kho = Path(__file__).resolve().parent.parent.parent / "bin" / "aisef"
    if trong_kho.is_file() and sys.platform != "win32":
        return [str(trong_kho)]
    # Always works with an installed package, even when venv is not on the
    # agent session's PATH: the running interpreter itself + module.
    return [sys.executable, "-m", "aisef.cli"]


def aisef_command() -> str:
    """The framework command the agent can **actually** type.

    Printing `aisef tool test` in the prompt is useless if `aisef` is not on
    the agent session's PATH — it will get "command not found", then run
    pytest manually, and that run will not be recorded as evidence. Prefer
    the name on PATH; if absent, use the absolute path from this repo.
    """
    return quote_command(aisef_argv())


def describe_tools(project: Path | str, config: Config | None = None) -> str:
    """Tool table for the prompt: name, actual command, and **when to call**."""
    project = Path(project)
    binary = aisef_command()
    lines = []
    for tool in TOOLS.values():
        cmd = command_for(tool.name, project, config) or "(not declared)"
        lines.append(f"- `{binary} tool {tool.name}` → `{cmd}`\n  When: {tool.when}")
    lines.append(
        f"- `{binary} doc <gói> --topic <chủ đề>` → tài liệu thật của thư viện (context7, có cache)\n"
        "  When: unsure about API names or library behaviour — look up, do not guess (rule 12). "
        "Add `--story <id>` so the lookup is recorded in evidence."
    )
    lines.append(
        f"- `{binary} ctx --story <id>` (or `--file <path>`) → code map around write scope: "
        "signatures of files in scope, callers/imports, tests referencing names\n"
        "  When: at the start of a new session, before exploring the directory tree — static hints, not ground truth."
    )
    return "\n".join(lines)
