"""Guard — deterministic code that runs at lifecycle checkpoints.

This is where things the agent **must not forget** live, and the only
guarantee is not relying on the agent remembering. Each guard is a pure
function: receives an event, returns a verdict. No global state reads, no
writes — so it is testable and runs on any client.

Exit code convention follows Claude Code (verified in spike S2): **exit 2
means block**, and stderr is forwarded into the tool result for the agent
to read. Therefore block reasons must be written so the agent can understand
and fix, not for logs.

Story write scope is passed via the ``AISEF_WRITE_SCOPE`` environment
variable. Guards intentionally do **not** look up `stories.index.json`:
keeps them pure and fast; lookup is the story runner's job.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..clients.base import split_command
from .observe import TOOL_RUN

ENV_WRITE_SCOPE = "AISEF_WRITE_SCOPE"
ENV_STORY_ID = "AISEF_STORY_ID"
ENV_BASE_REF = "AISEF_BASE_REF"
#: Story working tree. The harness **knows** this path — it creates the
#: worktree itself — so there is no need to ask the client. If the client
#: reports wrong (or the model sets a different `workdir`), the guard still
#: inspects the correct tree.
ENV_WORKDIR = "AISEF_WORKDIR"
#: Tools disallowed for this role, comma-separated. Claude Code has
#: `--disallowed-tools`; OpenCode claims "emulated via permission config"
#: but no code generates that config — reviewers on OpenCode can write
#: code. Blocking in the guard ensures all clients block, and Claude gets
#: an extra layer when the flag is forgotten.
ENV_DISALLOWED_TOOLS = "AISEF_DISALLOWED_TOOLS"
#: Allowed hosts for outbound connections, comma-separated. Empty = no check.
ENV_ALLOW_HOSTS = "AISEF_ALLOW_HOSTS"
#: Project root — harness declares via env. Compiled hook pins `--project`
#: as absolute; if the project is copied/moved the guard still runs but
#: writes evidence to the old project (measured A/B `par-A` 2026-09-05:
#: 4 false "guard ran" failures).
ENV_PROJECT = "AISEF_PROJECT"
#: Paths already changed in the tree **before** this session started, declared
#: by the phase that opened it.  `diff-scope` reads the whole tree, so without
#: this it blames the session for whatever the operator left uncommitted —
#: `.ai/config.json` written by `aisef setup` blocked every tool call of a
#: Windows planning run (2026-09-09) with "changed outside write_scope".
ENV_BASELINE_DIRTY = "AISEF_BASELINE_DIRTY"

#: Write scope when **not** inside a story: planning and mockup phases.
#: These have a fixed, known scope, so guards still apply — instead of
#: having to be disabled for the first half of the lifecycle.
PLANNING_SCOPE = ("_bmad-output", "docs")


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.allowed else 2


ALLOW = Verdict(True)


# ------------------------------------------------------------ write scope


#: True when this OS separates path segments with a backslash.  A module
#: constant, not a live `os.name` lookup, so a test can flip it without
#: faking `os.name` — faking that makes `pathlib` try to build a
#: `WindowsPath` and fail on Linux (CI, 3.11/3.12).
_WIN_SEP = os.sep == "\\"


def to_posix(p: str) -> str:
    """A path with `/` separators, whatever the OS handed us.

    `Path.relative_to` returns the **native** form, and every comparison
    after it — scope segments, `docs/` prefixes, the test-path pattern —
    is written in `/`.  On Windows that made
    `_bmad-output\\project-context.md` a single segment matching nothing, so
    the guard rejected a file plainly inside `_bmad-output` and stopped the
    plan phase (reported 2026-09-09).

    Translated **only on Windows**: a backslash is a legal character in a
    POSIX filename, and reading it as a directory boundary would let a file
    called `docs\\evil.sh` at the root pass as being inside `docs/`.
    """
    return p.replace("\\", "/") if _WIN_SEP else p


def _norm(p: str) -> PurePosixPath:
    return PurePosixPath(to_posix(str(p)).strip().strip("/"))


def _within(path: str, scope: str) -> bool:
    """Is `path` within `scope` — compared by path segments.

    String-prefix comparison would treat `src/apidocs/x.py` as within
    `src/api`, but those are two different areas.
    """
    p, s = _norm(path), _norm(scope)
    return p == s or s in p.parents


def check_write_scope(file_path: str, scope: list[str], *, project_root: str = "") -> Verdict:
    """Block writes outside the story's scope.

    Empty scope means **not declared**, and undeclared means no writes
    allowed — defaulting to open would turn the guard into decoration the
    first time someone forgets to pass the environment variable.
    """
    if not file_path:
        return ALLOW  # not a file operation

    if not scope:
        return Verdict(
            False,
            f"story has not declared write_scope so writing {file_path} is not allowed. "
            f"Add write_scope to the story and retry.",
        )

    rel = str(file_path)
    if project_root:
        try:
            rel = str(Path(file_path).resolve().relative_to(Path(project_root).resolve()))
        except ValueError:
            return Verdict(
                False,
                f"{file_path} is outside the project directory. Story may only write within "
                f"its write_scope: {', '.join(scope)}",
            )

    if any(_within(rel, s) for s in scope):
        return ALLOW
    return Verdict(
        False,
        f"{rel} is outside the story's write_scope ({', '.join(scope)}). "
        f"If the story truly needs to touch this, stop and report — most likely "
        f"the scope is incomplete or the story was split incorrectly.",
    )


# ------------------------------------------------------------ secrets

#: Secret patterns. Targets things with distinctive shapes, no guesswork —
#: a long random string may not be a key, but `sk-ant-...` certainly is.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    # Two patterns added for ADR-005 V1: AWS secret key (exactly 40 base64
    # chars) and Bearer token — these tend to leak into integration test
    # stdout rather than source code, so the old patterns (aimed at source)
    # never needed them.
    ("AWS secret key", re.compile(r"\bAWS_SECRET_ACCESS_KEY\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}\b")),
    ("token Bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}")),
    ("password assignment", re.compile(
        r"(?i)\b(password|passwd|pwd|pw|secret|api[_-]?key|access[_-]?token)\s*[=:]\s*"
        r"['\"][^'\"\s{}$]{8,}['\"]"
    )),
]

#: Placeholder values — shaped like secrets but clearly examples.
PLACEHOLDER_MARKERS = (
    "example", "placeholder", "your-", "xxx", "changeme", "dummy",
    "<", "{{", "${", "os.environ", "process.env", "getenv",
)


def check_secrets(content: str) -> Verdict:
    """Block secrets from leaking into source code.

    Skips lines with placeholder markers or env-var reads — blocking
    `API_KEY = os.environ["X"]` would make people disable the guard, and
    a disabled guard is worse than none.
    """
    if not content:
        return ALLOW

    for line_no, line in enumerate(content.splitlines(), 1):
        lowered = line.lower()
        if any(m in lowered for m in PLACEHOLDER_MARKERS):
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                return Verdict(
                    False,
                    f"line {line_no} appears to contain {label}. Read from environment variables "
                    f"or a secret store, do not write directly into source code.",
                )
    return ALLOW


REDACTED = "[REDACTED]"


def scrub_secrets(text: str) -> tuple[str, int]:
    """Redact all strings matching `SECRET_PATTERNS` with `[REDACTED]`; returns (text, count).

    Used for **evidence** — test/lint/qa stdout/stderr written to
    `_bmad-output`, a directory committed with the project (ADR-005 V1).
    Unlike `check_secrets`, does not skip "placeholder" lines: redacting
    an example is harmless, but missing a real key means it is already in
    git history.
    """
    if not text:
        return text, 0
    total = 0
    for _, pattern in SECRET_PATTERNS:
        text, n = pattern.subn(REDACTED, text)
        total += n
    return text, total


# ------------------------------------------------------------ shell commands

#: `git` can carry global flags before the subcommand: `-C <dir>`, `-c k=v`, `--no-pager`.
_GIT = r"\bgit\b(?:\s+-[Cc]\s+\S+|\s+-\S+)*\s+"

#: Destructive commands — blocked outright, even if the agent thinks it is cleaning up.
DESTRUCTIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("git reset --hard", re.compile(r"\bgit\s+reset\s+(--\S+\s+)*--hard\b")),
    ("git checkout bỏ thay đổi", re.compile(r"\bgit\s+checkout\s+--\s")),
    ("git clean", re.compile(r"\bgit\s+clean\b.*-[a-z]*f")),
    # ADR-005 V2: **all** forms of push (including `--dry-run`, since it still
    # authenticates with the remote) and remote changes. Push/merge is the
    # harness's job after the gate (`worktree.merge_story`); agent only
    # commits on the story branch.
    ("git push — push/merge là việc của harness sau cổng", re.compile(_GIT + r"push\b")),
    ("git remote add/set-url — remote là của harness", re.compile(_GIT + r"remote\s+(?:add|set-url)\b")),
    # `GIT_NO_CREDENTIALS` (clients/base.py) removes the helper; agent must not
    # re-enable via `-c credential.helper=...` or call `git credential(-osxkeychain)` directly.
    ("git credential — phiên agent không cầm credential của máy",
     re.compile(_GIT + r"credential(?:-\w+)?\b|\bgit\b.*\s-c\s*credential\.")),
    ("xoá đệ quy", re.compile(r"\brm\s+(-\w*\s+)*-\w*[rR]\w*f|\brm\s+-fr\b")),
    ("git stash bỏ việc", re.compile(r"\bgit\s+stash\s+(drop|clear)\b")),
]

_GIT_ADD_ALL = re.compile(r"\bgit\s+add\s+(.*\s)?(-A\b|--all\b|\.(\s|$))")


def check_git_stage(command: str) -> Verdict:
    """Block `git add -A` and `git add .`.

    Bulk-add swallows junk files and changes from other stories running
    in parallel in adjacent worktrees.
    """
    if not command or not _GIT_ADD_ALL.search(command):
        return ALLOW
    return Verdict(
        False,
        "do not use `git add -A` or `git add .`. Only stage paths this "
        "story touches, e.g.: git add src/api/users.py tests/test_users.py",
    )


#: Lời khuyên theo **loại** lệnh bị chặn. Hành vi chặn không đổi; chỉ câu chữ.
#: Lần guard nổ duy nhất của cohort C-1 là `find . -name __pycache__ -exec rm -rf
#: {} +` — dọn cache trong chính cây làm việc. Với ca ấy, "dừng lại và báo cho
#: người" là lời khuyên vô nghĩa, và một thông báo vô nghĩa dạy agent bỏ qua
#: thông báo (`docs/BENCH-OBSERVATIONS-C1.md` § O-4).
_LOI_KHUYEN = {
    "": "If truly needed, stop and report to a human — do not run it yourself.",
    "xoá đệ quy": ("Recursive delete is blocked whatever the target: a path filter cannot tell "
                   "`__pycache__` from `__pycache__/../..`. Caches do not need deleting — tests "
                   "must pass without cleaning. If a delete is genuinely required, stop and say "
                   "so; do not run it yourself."),
    "git stash bỏ việc": ("Stash entries are the only copy of work nobody committed. Leave them; "
                          "if they are in the way, say which entry and why."),
}


#: Package managers whose second token *selects* the script. `npm test`,
#: `npm test --silent` and `npm run test` are one command, and a project that
#: declares one while the agent types another must still be caught.
_TRINH_GOI = ("npm", "pnpm", "yarn", "bun")
#: Shell operators separating one command from the next — `npm test && npx eslint .`
_NGAT_LENH = re.compile(r"&&|\|\||;|\|")
#: Redirections say nothing about *which* command this is: `npm test 2>&1`.
_CHUYEN_HUONG = re.compile(r"(?:\d?>>?&?\d?|<)\s*\S*")


def _khoa_lenh(segment: str) -> tuple[str, ...]:
    """Identity of one shell command: what it runs, not how it is spelled."""
    argv = parse_command(_CHUYEN_HUONG.sub(" ", segment).strip())
    if len(argv) > 2 and argv[0] in _TRINH_GOI and argv[1] == "run":
        argv = [argv[0], *argv[2:]]
    if len(argv) >= 2 and argv[0] in _TRINH_GOI:
        return (argv[0], argv[1])
    return tuple(argv)


def check_tool_bypass(command: str, declared: dict[str, str | list[str]]) -> Verdict:
    """Block running a declared tool command directly instead of via `aisef tool`.

    The prompt already says only runs through `aisef tool` are recorded and
    that the gate reads evidence, not claims. Measured on todo-cli
    2026-09-13 (OpenCode/mycombo, session `ses_f67454ae`): the developer ran
    `npm test 2>&1` in every one of ten sessions and `aisef tool test` in
    none. Every `test` event in that story's evidence therefore came from
    the harness's own verify pass — one green run per candidate — so
    `red_before_green` had nothing to compare and the `TDD` check failed for
    ten sessions in a row over a working implementation (lỗi 116).

    Instruction the agent can ignore -> guard that blocks at source. The
    agent gets the same command run for it, plus the evidence.

    A **narrowed** run (`pytest tests/x.py -k foo`) is not blocked: it is
    debugging, not a claim about the suite, and recording it as `test` would
    make a subset look like a green suite.
    """
    if not command:
        return ALLOW
    muc_tieu: dict[tuple[str, ...], str] = {}
    for ten, lenh in declared.items():
        cach_viet = [lenh] if isinstance(lenh, str) else list(lenh)
        for c in cach_viet:
            khoa = _khoa_lenh(c) if c.strip() else ()
            if khoa:
                muc_tieu.setdefault(khoa, ten)
    if not muc_tieu:
        return ALLOW
    for doan in _NGAT_LENH.split(command):
        ten = muc_tieu.get(_khoa_lenh(doan))
        if not ten:
            continue
        from .tools import aisef_command

        return Verdict(
            False,
            f"`{doan.strip()}` is the project's {ten} command run directly, so "
            f"nothing about it is recorded — and the gate reads evidence, not "
            f"claims. Run `{aisef_command()} tool {ten}` instead: it runs the "
            f"same command and records the result, which is what the `TDD`, "
            f"`test` and `coverage` checks read. Narrowing a run for debugging "
            f"(extra arguments, a single file) is not blocked.",
        )
    return ALLOW


def _script_npm(project: Path, command: str) -> list[str]:
    """`npm test` **and** the script it runs — both are the same suite.

    Judging by the words `npm test` alone leaves the obvious way around open:
    `node --test --experimental-test-coverage`, which is what that script is.
    """
    import json as _json

    argv = parse_command(command)
    if len(argv) < 2 or argv[0] not in _TRINH_GOI:
        return []
    key = argv[2] if argv[1] == "run" and len(argv) > 2 else argv[1]
    try:
        scripts = _json.loads((project / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError):
        return []
    than = str(scripts.get(key) or "").strip()
    return [than] if than else []


def declared_commands(project: str | Path) -> dict[str, list[str]]:
    """Every spelling of the tool commands this project declares.

    The configured/detected command is what the prompt shows the agent; the
    npm script body is the same run under another name.
    """
    from ..config import Config
    from .tools import TOOLS, command_for

    project = Path(project)
    try:
        cfg = Config.load(project)
    except Exception:                       # noqa: BLE001 - a broken config must not
        cfg = None                          # break every bash call in the session
    ra = {}
    for ten in TOOLS:
        lenh = command_for(ten, project, cfg)
        ra[ten] = [lenh, *_script_npm(project, lenh)] if lenh else []
    return ra


def check_destructive(command: str) -> Verdict:
    """Block commands that destroy unsaved work."""
    if not command:
        return ALLOW
    for label, pattern in DESTRUCTIVE_PATTERNS:
        if pattern.search(command):
            return Verdict(False, f"destructive command blocked ({label}). "
                                  + _LOI_KHUYEN.get(label, _LOI_KHUYEN[""]))
    return ALLOW


# ------------------------------------------------------------ injection

#: Each risk has **two** patterns, one per language family actually encountered.
#: A guard that only knows the Python pattern is present but never fires on a
#: TypeScript project — same class of bug as "unconfigured counts as pass",
#: and worse because the report still says "7 guards wired".
#:
#: Split by family rather than one merged pattern, because interpolation
#: markers differ and merging causes cross-matches: `{` only means
#: interpolation when the string has Python's `f` prefix, while in JS it is
#: an optional object — a merged pattern falsely blocks
#: `execFileSync('git', ['ls-files'], { cwd })`, a **safe** form the guard
#: should encourage.
#:
#: JS-specific difficulty with `exec(`: RegExp's `re.exec(s)` is far more
#: common than `child_process.exec`. Distinguished by **argument**: only
#: fires when right after the paren is a string or template. `re.exec(var)`
#: passes a variable so it does not match; the trade-off is missing
#: `exec(pre_built_string)` — better to miss that than false-block every
#: regex usage.
_SQL = r"\b(select|insert|update|delete)\b"
_SHELL_PY = r"os\.system|subprocess\.\w+|commands\.getoutput"
_SHELL_JS = (
    r"execSync|execFileSync|spawnSync|child_process\.\w+|\bexec|\bspawn"
)

INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("nối chuỗi vào câu SQL", re.compile(
        rf"""(?i)(execute|query|cursor\.execute|\braw|prepare)\s*\("""
        rf"""\s*f['"].*{_SQL}.*\{{"""
    )),
    ("nối chuỗi vào câu SQL", re.compile(
        rf"""(?i)(execute|query|\braw|prepare)\s*\(\s*['"`].*{_SQL}"""
        rf""".*(\$\{{|\+|%s\s*%)"""
    )),
    ("chèn HTML thô", re.compile(
        r"dangerouslySetInnerHTML|\.(inner|outer)HTML\s*=|"
        r"\.insertAdjacentHTML\s*\(|document\.write(ln)?\s*\("
    )),
    ("shell với chuỗi ghép", re.compile(
        rf"""(?i)({_SHELL_PY})\s*\(\s*(f['"].*\{{|['"].*\+)"""
    )),
    ("shell với chuỗi ghép", re.compile(
        rf"""(?i)({_SHELL_JS})\s*\(\s*['"`].*(\$\{{|\+)"""
    )),
    ("dựng mã từ chuỗi ghép", re.compile(
        r"""(?i)(\beval|new\s+Function)\s*\(\s*(f['"].*\{|['"`].*(\$\{|\+))"""
    )),
]


#: Constitution rule 6: do not write story/epic IDs into source code.
#: Intentional exceptions: test files (`AC-<story>-<i>` **must** appear in
#: test names — G5), documentation, harness artifacts.
_PROCESS_REF = re.compile(r"\b(?:STORY|EPIC)-\d+(?:-\d+)?\b")
_REF_ALLOWED_DIRS = ("docs/", "_bmad-output/", ".ai/", ".claude/", ".opencode/", ".aisef/", "bench/")
_REF_ALLOWED_SUFFIX = (".md", ".txt", ".json", ".yaml", ".yml", ".csv")


def check_process_refs(content: str, path: str, *, project_root: str = "") -> Verdict:
    """Rule 6: process references (`STORY-01-02`, `EPIC-01`) must not appear
    in source code. Tests and docs are allowed — tests are even required to
    carry acceptance-criteria codes. Directory matching uses paths **relative
    to root**: worktree absolute paths contain `.aisef/worktrees/` and
    falsely match the allow list (conformance C6 on OpenCode, 2026-09-05)."""
    from ..control.impact import is_test_path

    rel = path.replace("\\", "/")
    if project_root:
        try:
            rel = str(Path(rel).resolve().relative_to(Path(project_root).resolve()))
        except ValueError:
            pass
    rel = to_posix(rel).lstrip("./")   # `relative_to` gave it back native separators
    if any(rel.startswith(seg) for seg in _REF_ALLOWED_DIRS) or rel.endswith(_REF_ALLOWED_SUFFIX) or is_test_path(rel):
        return ALLOW
    hit = _PROCESS_REF.search(content or "")
    if not hit:
        return ALLOW
    return Verdict(
        False,
        f"rule 6: process reference `{hit.group(0)}` in source code ({rel}). Comments should explain "
        f"*why*, not *which ticket this belongs to* — remove the reference from source.",
    )


def check_injection(content: str) -> Verdict:
    if not content:
        return ALLOW
    for label, pattern in INJECTION_PATTERNS:
        m = pattern.search(content)
        if m:
            line_no = content[: m.start()].count("\n") + 1
            return Verdict(
                False,
                f"line {line_no}: {label}. Use parameterization / safe API instead "
                f"of string concatenation.",
            )
    return ALLOW


# ------------------------------------------------------------ orchestration


# ------------------------------------------------------------ diff scope


def check_diff_scope(changed: list[str], scope: list[str]) -> Verdict:
    """Block when files **outside scope** have been changed.

    `write-scope` blocks each write operation the harness observes. This
    guard asks a different question: after everything that happened, is the
    working tree within scope. It catches indirect paths — scripts generating
    files, file moves, or clients that cannot attach a pre-check hook
    (OpenCode is post-check only) — because it reads outcomes, not intent.
    """
    if not changed:
        return ALLOW
    if not scope:
        return Verdict(
            False,
            f"story has not declared write_scope but {len(changed)} files changed: "
            f"{', '.join(changed[:5])}",
        )

    outside = [c for c in changed if not any(_within(c, s) for s in scope)]
    if not outside:
        return ALLOW
    # Offending files **first**. The scope list runs to 27 entries once the
    # harness adds the verification directories, and every consumer folds this
    # message to one line — so the one thing the reader needs was always the
    # part that got cut (measured on `todo-e2e`, 2026-09-09).
    return Verdict(
        False,
        f"{len(outside)} files changed outside write_scope: {', '.join(outside[:5])}"
        f"{f' (+{len(outside) - 5} more)' if len(outside) > 5 else ''}. "
        f"Revert them, or stop and report that the story's scope is incomplete. "
        f"Scope: {', '.join(scope[:12])}"
        f"{f' (+{len(scope) - 12} more)' if len(scope) > 12 else ''}",
    )


#: Paths written by the **harness** at runtime, not the agent: evidence,
#: sprint state, approval records, worktree. Without excluding these, the
#: harness's own state writes would count as out-of-scope story writes —
#: the guard would incriminate itself and every story would fail.
#:
#: Intentionally does **not** exclude all of `_bmad-output`: planning docs
#: (PRD, architecture, epic, visual contract, story index) are things that
#: must be visible if the agent sneaks edits — editing `stories.index.json`
#: is editing the very scope that constrains it.
#: Installed dependencies and build artifacts. They appear because the story
#: **runs**, not because it **writes** — counting them in scope means every
#: story that installs dependencies fails, and the only way forward is
#: widening scope until the guard is meaningless. Projects with a correct
#: `.gitignore` already exclude these; this list is the safety net for when
#: `.gitignore` does not exist yet.
VENDOR_PATHS = (
    "node_modules", ".venv", "venv", "vendor", "target", "dist", "build",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".next", ".turbo",
    "coverage", ".gradle", "Pods",
    # Artifacts of the agent's own tooling: screenshots, traces, reports.
    # These sit at the project root but are not story products — counting
    # them in scope means opening a browser once fails the gate.
    ".playwright-mcp", "playwright-report", "test-results", ".nyc_output",
)

#: Generated files identified by **suffix**, not by directory. Same reason as
#: `VENDOR_PATHS`: they appear because the story ran a tool, not because it
#: wrote them. `tsc` rewrites `*.tsbuildinfo` on every build, so a TypeScript
#: story failed `write scope` on its own compiler output — and the reviewer
#: spent 2 of its 7 blocking findings telling the author to revert a file the
#: next build recreates (reported from Windows 2026-09-09).
GENERATED_SUFFIXES = (".tsbuildinfo",)

HARNESS_OWNED = (
    "_bmad-output/evidence",
    "_bmad-output/journal",
    "_bmad-output/approvals",
    "_bmad-output/sprint-status.json",
    "_bmad-output/sprint-status.json.lock",
    "_bmad-output/compile-report.json",
    "_bmad-output/run.log",
    # Verbatim review verdicts (`implement.persist_verdict`) — written by the
    # harness, not the agent. Exposed when two stories share one tree
    # (`--no-isolate`): the previous story's file appears as "outside write
    # scope" for the next story.
    "_bmad-output/reviews",
    ".aisef",
    # Client config the harness copies into the worktree
    # (`WorktreeManager._carry_client_config`) — if the project does not
    # gitignore `.claude/` it shows up as untracked and the `diff-scope`
    # guard blocks every command for "outside write scope" (dogfood par
    # 2026-09-05: 3/3 stories failed "write scope" because of this file).
    ".claude/settings.json",
    ".opencode",
    # State the agent's own MCP servers write into the tree they are pointed
    # at. Serena writes `.serena/memories/*.md` on its first call, which is
    # every session — so on `todo-e2e` 2026-09-09 the `diff-scope` guard
    # blocked every command the agent ran, all three attempts, and the story
    # died having produced almost nothing. The framework does not choose the
    # user's MCP servers; it must not fail their stories for having them.
    ".serena",
    *VENDOR_PATHS,
)


def _git_lines(project_root: str, args: list[str]) -> list[str]:
    """Run a git command returning NUL-separated results. Returns empty on error."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=project_root or ".",
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [e for e in proc.stdout.split("\0") if e]


def changed_files(
    project_root: str,
    *,
    ignore: tuple[str, ...] = HARNESS_OWNED,
    base_ref: str = "",
) -> list[str]:
    """Files changed by the story: diff against the **fork point**, including
    new untracked files.

    Without ``base_ref`` this only diffs against ``HEAD`` — and that breaks.
    The agent is encouraged to make incremental commits (merge only sees
    committed work), so after a few commits "diff against HEAD" returns
    nearly empty. Three gates read this list: write scope passes
    unconditionally, real tests have nothing to check, and the reviewer
    gets an empty diff and has to search the whole repo — blind and
    expensive. Diffing against the fork point keeps committed work visible.

    Skips harness-owned paths. The rest of ``_bmad-output`` is **not**
    skipped: an agent sneaking edits to the PRD or visual contract while
    writing code must be visible.
    """
    paths: list[str] = []
    seen: set[str] = set()

    # `git status` includes untracked files — which `git diff` does not see.
    for entry in _git_lines(
        project_root, ["status", "--porcelain", "-z", "--untracked-files=all"]
    ):
        if len(entry) > 3:
            paths.append(entry[3:])

    # `git diff <base>` compares the **working tree** against the fork point,
    # so it covers both committed and uncommitted work.
    if base_ref:
        paths += _git_lines(project_root, ["diff", "--name-only", "-z", base_ref])

    out: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if path.endswith(GENERATED_SUFFIXES):
            continue
        if any(_within(path, skip) or skip in Path(path).parts for skip in ignore):
            continue
        out.append(path)
    return out


def fork_point(workdir: str, upstream: str) -> str:
    """Fork point where the story branched off the main branch. Empty if unable to compute.

    Uses ``merge-base`` instead of the main branch tip: within a sprint,
    an earlier story may have merged into main while a later story is still
    running — comparing against the tip would attribute the earlier story's
    work to the later one.
    """
    if not upstream:
        return ""
    got = _git_lines(workdir, ["merge-base", "HEAD", upstream])
    return got[0].strip() if got else ""


def head_sha(workdir: str | Path) -> str:
    """SHA of HEAD. Empty if git is unreadable.

    Empty must mean **unable to check**, not "different version": losing
    git visibility and blocking the entire story is worse.
    """
    got = _git_lines(str(workdir), ["rev-parse", "HEAD"])
    return got[0].strip() if got else ""


# ------------------------------------------------------------ completion


def check_completion(evidence) -> Verdict:
    """Block agent from finishing when tests are not green for the **current code**.

    Three questions, in increasing strictness:

    1. Has any test run been recorded? Claiming done without running tests
       is self-incriminating.
    2. Did the most recent run pass?
    3. Were any files changed **after** that run? Tests passing before
       edits say nothing about the code just written — this is the most
       common false "green" when the agent rushes to finish.
    """
    last = evidence.last(TOOL_RUN, "test")
    if last is None:
        # Name the exact command to run. A guard that blocks with an
        # unrunnable instruction traps the agent: it cannot stop, nor do
        # what it was told — and burns all its turns.
        from .tools import aisef_command

        return Verdict(
            False,
            f"no test run recorded for this story. Run `{aisef_command()} "
            f"tool test` before finishing — evidence is in the run result, "
            f"not in claims.",
        )
    if last.detail.get("unrunnable"):
        # Unrunnable != red: the agent cannot fix the test environment/command
        # (outside write scope), blocking Stop only burns turns. The story
        # gate records UNRUNNABLE and still blocks — with the right reason.
        return ALLOW
    if last.detail.get("skipped"):
        # Not configured != red. Blocking here means the agent cannot fix
        # anything (test command is the project's concern) and just burns
        # turns — measured in conformance: Stop blocked twice in a row on a
        # project with no test command declared. The story gate still records
        # "unit not configured", does not count as pass.
        return ALLOW
    if not last.ok:
        tail = str(last.detail.get("tail") or "")[:400]
        return Verdict(
            False,
            "the most recent test run is still failing, the story cannot be finished.\n" + tail,
        )

    stale = evidence.stale_since_last_test()
    if stale:
        from .tools import aisef_command

        return Verdict(
            False,
            f"{len(stale)} files changed since the most recent test run "
            f"({', '.join(stale[:5])}). Re-run `{aisef_command()} tool test` "
            f"before finishing.",
        )
    return ALLOW


def project_root_from(env: dict[str, str] | None, fallback: str) -> str:
    """Project root for guards: harness env wins, compiled `--project` is fallback."""
    root = (env if env is not None else os.environ).get(ENV_PROJECT, "").strip()
    return root or fallback


def scope_from_env(env: dict[str, str] | None = None) -> list[str]:
    raw = (env or os.environ).get(ENV_WRITE_SCOPE, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def story_from_env(env: dict[str, str] | None = None) -> str:
    return (env or os.environ).get(ENV_STORY_ID, "")


def disallowed_from_env(env: dict[str, str] | None = None) -> list[str]:
    raw = (env or os.environ).get(ENV_DISALLOWED_TOOLS, "")
    return [t.strip() for t in raw.split(",") if t.strip()]


def check_role_tool(tool_name: str, disallowed: list[str]) -> Verdict:
    """Is this role allowed to call this tool. Case-insensitive matching:
    Claude sends `Write`, OpenCode sends `write`."""
    if not tool_name or not disallowed:
        return ALLOW
    cam = {t.lower() for t in disallowed}
    if tool_name.lower() not in cam:
        return ALLOW
    return Verdict(
        False,
        f"this role is not allowed to use tool {tool_name} — it reviews, not edits. "
        f"Report findings instead of fixing them yourself.",
    )


# ------------------------------------------------------------ egress

_URL_RE = re.compile(r"https?://([^/:@\s#?]+)")
_NET_COMMANDS = re.compile(
    r"\b(curl|wget|fetch|http|nc|ncat|ssh|scp|rsync|git\s+clone"
    r"|git\s+push|git\s+pull|git\s+fetch|npm\s+install|npm\s+ci"
    r"|npx|yarn|pnpm|pip\s+install|uv\s+pip|poetry\s+install"
    r"|apt|apt-get|brew)\b"
)


def _extract_hosts(tool_name: str, tool_input: dict) -> list[str]:
    """Extract hostnames from a tool event."""
    hosts: list[str] = []
    if tool_name in ("WebFetch", "webfetch"):
        url = str(tool_input.get("url") or tool_input.get("URL") or "")
        for m in _URL_RE.finditer(url):
            hosts.append(m.group(1).lower())
    elif tool_name in ("WebSearch", "websearch"):
        pass  # web search is a search engine query, not a direct connection
    else:
        cmd = str(tool_input.get("command") or "")
        if cmd and _NET_COMMANDS.search(cmd):
            for m in _URL_RE.finditer(cmd):
                hosts.append(m.group(1).lower())
    return hosts


def _host_matches(host: str, allowed: list[str]) -> bool:
    """Host matches allowlist — exact match or suffix (*.example.com)."""
    for pat in allowed:
        p = pat.lower().strip()
        if p.startswith("*."):
            suffix = p[1:]  # ".example.com"
            if host == p[2:] or host.endswith(suffix):
                return True
        elif host == p:
            return True
    return False


def check_egress(tool_name: str, tool_input: dict, allow_hosts: list[str]) -> Verdict:
    """V12: block connections to undeclared hosts. Empty allowlist = no check."""
    if not allow_hosts:
        return ALLOW
    hosts = _extract_hosts(tool_name, tool_input)
    if not hosts:
        return ALLOW
    for h in hosts:
        if not _host_matches(h, allow_hosts):
            return Verdict(
                False,
                f"host {h} is not in the allowed list "
                f"(sandbox.allow_hosts). Add it to .ai/config.json if "
                f"the project needs to connect to this host.",
            )
    return ALLOW


def allow_hosts_from_env(env: dict[str, str] | None = None) -> list[str]:
    raw = (env or os.environ).get(ENV_ALLOW_HOSTS, "")
    return [h.strip() for h in raw.split(",") if h.strip()] if raw else []


def workdir_from_env(env: dict[str, str] | None = None) -> str:
    """Working tree declared by the harness. Empty means not running inside a story."""
    return (env or os.environ).get(ENV_WORKDIR, "")


def baseline_dirty_from_env(env: dict[str, str] | None = None) -> tuple[str, ...]:
    raw = (env or os.environ).get(ENV_BASELINE_DIRTY, "")
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def base_from_env(env: dict[str, str] | None = None) -> str:
    return (env or os.environ).get(ENV_BASE_REF, "")


def effective_scope(env: dict[str, str] | None = None) -> list[str]:
    """Currently effective write scope.

    Inside a story: the scope declared by the story, and **empty means
    block** — forgetting the env variable must not turn the guard into
    decoration.

    Outside a story (planning, mockup phases): the framework's fixed scope.
    Without this branch the guard would block BMAD from writing the PRD,
    and the only way forward would be disabling the guard for the first
    half of the lifecycle — the half where documents determine everything
    downstream.
    """
    scope = scope_from_env(env)
    if scope or story_from_env(env):
        return scope
    return list(PLANNING_SCOPE)


def _escaped_workdir(tool_input: dict, root: str) -> Verdict | None:
    """Does the command specify a directory outside the agent's working tree.

    Returns ``None`` when there is nothing to say — no `workdir`, unknown
    root, or `workdir` is within the tree. Worktree isolation only has value
    when nobody can step outside it.
    """
    wd = str(tool_input.get("workdir") or tool_input.get("cwd") or "")
    if not wd or not root:
        return None
    try:
        trong = Path(wd).resolve()
        cay = Path(root).resolve()
    except OSError:
        return None
    if trong == cay or cay in trong.parents:
        return None
    return Verdict(
        False,
        f"command specifies directory {wd}, outside the working tree ({root}). "
        f"Story may only work within its worktree — work placed outside "
        f"bypasses all gates. Remove the directory parameter and retry.",
    )


def run_guard(kind: str, event: dict, *, env: dict[str, str] | None = None,
              project_root: str = "", artifact_root: str = "") -> Verdict:
    """Run a guard on a client hook event.

    ``event`` follows the shape Claude Code sends: ``tool_name`` and ``tool_input``.
    The last two guards need external state (git, evidence); their **decision**
    logic is still pure, this function only fetches the data.
    """
    tool_input = event.get("tool_input") or {}
    # Claude Code sends `file_path`; OpenCode sends `filePath` (measured in
    # conformance C6 2026-09-05: guard saw empty path -> write-scope passed as
    # "not a file operation"). Key name is the client's concern, not the rule's.
    file_path = str(tool_input.get("file_path") or tool_input.get("filePath") or tool_input.get("path") or "")
    content = str(tool_input.get("content") or tool_input.get("new_string") or tool_input.get("newString") or "")
    command = str(tool_input.get("command") or "")

    # The tree to inspect is the one the agent is standing in, not the tree
    # at hook compile time. Stories run in their own worktree, but the hook
    # is written once into `.claude/settings.json` with `--project` as the
    # project root — using that means the guard reads `git status` of a
    # different tree, sees all uncommitted planning docs, and blocks every
    # operation. `--porcelain` always returns paths relative to the repo
    # root so being in a subdirectory is fine.
    # Trust order: harness-declared tree -> client-reported tree -> compile-
    # time tree. The harness declaration comes first because it is **truth**:
    # the client may report the project root instead of the worktree, and
    # OpenCode's model even sets `workdir` per command.
    root = workdir_from_env(env) or str(event.get("cwd") or "") or project_root

    # OpenCode's `bash` tool accepts a per-**command** `workdir`, and the
    # model sets it on its own — seen in practice: story runs in a worktree
    # but `git add ... && git commit` carries `workdir` as the project root,
    # so work lands straight on `main` with no gate seeing it (worktree
    # stays empty, diff is empty, story fails for the wrong reason).
    #
    # Checked here, at the orchestration layer, so it applies to **all**
    # guards and all clients: whichever guard runs first can block. Going
    # into a subdirectory is allowed — escaping the tree is the issue.
    if (thoat := _escaped_workdir(tool_input, root)):
        return thoat

    # A reviewer role that can edit code becomes a second write pass, with
    # nobody left to review. Checked at the orchestration layer so all
    # guards, all clients block — not relying on per-client CLI flags.
    vai = check_role_tool(str(event.get("tool_name") or ""), disallowed_from_env(env))
    if not vai.allowed:
        return vai

    if kind == "write-scope":
        return check_write_scope(
            file_path, effective_scope(env), project_root=root
        )
    if kind == "secret":
        return check_secrets(content)
    if kind == "injection":
        return check_injection(content)
    if kind == "process-ref":
        return check_process_refs(content, file_path, project_root=root)
    if kind == "git-stage":
        return check_git_stage(command)
    if kind == "destructive":
        return check_destructive(command)
    if kind == "tool-bypass":
        # Only in a story session. The guard exists so a run becomes evidence,
        # and evidence is recorded per story — a reviewer has no story id on
        # purpose, so `aisef tool test` would record nothing for it either.
        # Blocking there costs the reviewer turns and, worse, stops it from
        # checking a claim against the code, which is exactly what the
        # `proven` slot now asks it to do (lỗi 125, seen the same run the slot
        # landed: `npm test 2>&1` blocked inside a review session).
        if not story_from_env(env):
            return ALLOW
        return check_tool_bypass(command, declared_commands(root or project_root or "."))
    if kind == "egress":
        return check_egress(
            str(event.get("tool_name") or ""), tool_input,
            allow_hosts_from_env(env),
        )
    if kind == "diff-scope":
        # Subtract what was already dirty when the session opened: this guard
        # asks "did **this** session step outside its scope", and a file the
        # operator left modified is not this session's doing.
        return check_diff_scope(
            changed_files(root, base_ref=base_from_env(env),
                          ignore=HARNESS_OWNED + baseline_dirty_from_env(env)),
            scope_from_env(env),
        )
    if kind == "completion":
        story = story_from_env(env)
        if not story or not artifact_root:
            # Cannot determine which story is running, so no conclusion is
            # possible. Blocking here would block runs outside the story
            # lifecycle too.
            return ALLOW
        from .observe import EvidenceStore

        return check_completion(EvidenceStore(artifact_root).read(story))
    raise ValueError(f"guard does not exist: {kind}")


def record_outcome(
    kind: str,
    event: dict,
    verdict: Verdict,
    *,
    env: dict[str, str] | None = None,
    artifact_root: str = "",
    duration_ms: int = 0,
) -> None:
    """Guard self-records into evidence — the only client-independent source.

    Two gaps with the same root: (1) `guard_blocked` was extracted only from
    Claude Code's event stream, so on OpenCode it was always False even when
    the guard actually blocked — measured on `par`: 4 blocks, evidence
    recorded False for all four; (2) the `FILE_CHANGE` event had a model and
    tests but **nobody wrote it**, so the "files changed since last test"
    rule in the `completion` guard never fired.

    Recorded here because the guard is the point all clients pass through.
    No story ID (review sessions intentionally omit it) means no recording
    — avoids polluting the record.
    """
    story = story_from_env(env)
    if not artifact_root:
        return
    if not story:
        # Planning and mockup sessions have no story, so nothing was recorded
        # — including the blocks.  A guard that stops the UX phase then leaves
        # its reason only inside the client's own session log, where the
        # operator cannot see it: reported 2026-09-09 from Windows as "the ux
        # phase is blocked" with no way to learn which path or which rule.
        if not verdict.allowed:
            from .runlog import one_line, run_log
            run_log(artifact_root, f"guard {kind} BLOCK "
                    + one_line(f"{event.get('tool_name') or '?'} · {verdict.reason}"))
        return
    from .observe import GUARD_BLOCK, GUARD_CHECK, GUARD_SEEN, TOOL_RUN, EvidenceStore, Event

    store = EvidenceStore(artifact_root)
    tool_input = event.get("tool_input") or {}
    tool = str(event.get("tool_name") or "")
    hien_co = store.read(story)

    # Heartbeat: once per story. Measured on `par`: sessions using only Bash
    # to write files have no Write/Edit going through `write-scope`, and
    # nothing gets blocked — evidence is empty despite the hook running 17
    # times. "Hook reachable" must be its own event, not inferred from others.
    if not hien_co.of(GUARD_SEEN):
        store.record(story, Event(kind=GUARD_SEEN, name=kind, detail={"tool": tool}))

    store.record(story, Event(
        kind=GUARD_CHECK, name=kind, ok=verdict.allowed,
        duration_ms=duration_ms,
        detail={"tool": tool, "verdict": "allow" if verdict.allowed else "block"},
    ))

    if not verdict.allowed:
        store.record(story, Event(
            kind=GUARD_BLOCK, name=kind, ok=False,
            detail={"tool": tool, "reason": verdict.reason[:300]},
        ))
        return
    if kind == "write-scope":
        path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        if path:
            store.file_change(story, path, detail={"tool": tool})
        return
    if kind == "diff-scope":
        # The only guard that sees files changed by **Bash**. Only records
        # files with mtime newer than the last `test` run: that is exactly
        # the definition of "changed since last test" that the `completion`
        # guard needs, and avoids re-recording previously changed files.
        last = hien_co.last(TOOL_RUN, "test")
        moc = last.at if last else 0.0
        root = workdir_from_env(env) or str(event.get("cwd") or "")
        # After the last test **by position**, not by `seq` — same reason as
        # `stale_since_last_test`.
        da_ghi = {str(e.detail.get("path") or e.name)
                  for e in hien_co.after_last(TOOL_RUN, "test") if e.kind == "file_change"}
        for rel in changed_files(root, base_ref=base_from_env(env)) if root else []:
            try:
                mtime = (Path(root) / rel).stat().st_mtime
            except OSError:
                continue
            if mtime > moc and rel not in da_ghi:
                store.file_change(story, rel, detail={"tool": tool})


#: Which guard attaches to which hook point, and matches which tool.
GUARD_MATCHERS: dict[str, tuple[str, str]] = {
    "write-scope": ("PreToolUse", "Write|Edit|NotebookEdit"),
    "secret": ("PreToolUse", "Write|Edit"),
    "injection": ("PreToolUse", "Write|Edit"),
    "process-ref": ("PreToolUse", "Write|Edit"),
    "git-stage": ("PreToolUse", "Bash"),
    "destructive": ("PreToolUse", "Bash"),
    "tool-bypass": ("PreToolUse", "Bash"),
    "egress":      ("PreToolUse", "WebFetch|Bash"),
    "diff-scope": ("PostToolUse", "Write|Edit|NotebookEdit|Bash"),
    "completion": ("Stop", ""),
}


def parse_command(command: str) -> list[str]:
    """Safely split a shell command; returns empty if unparseable."""
    try:
        return split_command(command)
    except ValueError:
        return []
