"""Common interface for all agent clients.

The framework talks to Claude Code and OpenCode through the same interface.
What differs between them — how prompts are passed, how results are read,
how guards are wired — is encapsulated in each implementation, not leaked
into the orchestration layer.

**Capabilities are declared, not assumed.**  Each client returns a
`capabilities()` table stating what it can do and at what level.  A client
that cannot wire pre-check guards must declare `POST_HOC`, so the framework
switches to post-check at the verify step and records a lower assurance
level in evidence — instead of silently running as if full coverage is in
place (invariant 10).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .stream import RunResult


class Support(str, Enum):
    """Support level for a capability."""

    NATIVE = "native"          # client has built-in support
    EMULATED = "emulated"      # framework emulates via an alternative mechanism
    POST_HOC = "post_hoc"      # can only check after the fact, cannot block at occurrence
    UNSUPPORTED = "unsupported"

    @property
    def blocks_at_source(self) -> bool:
        """Whether this level blocks at the moment the action occurs."""
        return self in (Support.NATIVE, Support.EMULATED)


class Capability(str, Enum):
    HEADLESS = "headless"              # runs without human interaction
    MACHINE_OUTPUT = "machine_output"  # machine-readable output
    PRE_TOOL_GUARD = "pre_tool_guard"  # blocks before tool execution
    TOOL_ALLOWLIST = "tool_allowlist"  # restricts allowed tools
    DIR_ALLOWLIST = "dir_allowlist"    # restricts directory access
    SUBAGENT = "subagent"              # spawns sub-agents
    MODEL_ROUTING = "model_routing"    # selects model by role
    COST_REPORTING = "cost_reporting"  # reports cost and tokens
    TURN_LIMIT = "turn_limit"          # limits turn count


@dataclass
class RunSpec:
    """A single agent run."""

    prompt: str
    workdir: Path
    system_prompt: str = ""
    model: str = ""
    max_turns: int = 0
    timeout_seconds: int = 1800
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    extra_dirs: list[Path] = field(default_factory=list)
    settings_file: Path | None = None
    session_id: str = ""
    #: Extra environment variables for the client process.  Guards run inside
    #: hooks as child processes of the client, so write scope and story ID
    #: reach the guard through exactly this path.
    env: dict[str, str] = field(default_factory=dict)
    #: Additional host env-var prefixes to pass through (`clients.env_allow`).
    #: Default empty: nothing passes beyond `ENV_KEEP`/`ENV_KEEP_PREFIXES`.
    env_allow: list[str] = field(default_factory=list)


# ------------------------------------------------------------ child environment

#: Host variables kept **as-is** for the client process — enough for a CLI
#: to run (find commands, home dir, locale, tmp, certificates), no more.
ENV_KEEP = frozenset({"PATH", "HOME", "LANG", "TERM", "TMPDIR", "SHELL", "USER", "LOGNAME",
                      "SSL_CERT_FILE",
                      # Windows equivalents.  Without `SystemRoot` a child
                      # process cannot load system DLLs or open a socket, and
                      # without `PATHEXT` it cannot resolve `.cmd`/`.exe` at
                      # all — an allowlist written for POSIX leaves a Windows
                      # child in an environment nothing runs in.
                      # Names are upper-case because that is how `os.environ`
                      # normalises them on Windows.
                      "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
                      "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
                      "PROGRAMFILES", "PROGRAMFILES(X86)", "TEMP", "TMP",
                      "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE"})
#: Prefixes kept: locale, Claude model key/URL, harness variables for guards.
#: Parent session's `CLAUDE*` is **not** here — conformance C3 showed a child
#: session inheriting them switches to Bash and bypasses Write/Edit guards (error 4).
#: `ANTHROPIC_` is **not** here: it belongs to the client that authenticates
#: with it (`ClaudeCodeAdapter.env_prefixes`). Handing it to every client
#: means a key meant for one provider reaches another — and a client that
#: reads it outranks its own login, so a session intended for the project's
#: router silently bills a different account (bug 101). A project that does
#: want it elsewhere declares `clients.env_allow`.
ENV_KEEP_PREFIXES = ("LC_", "AISEF_")
#: Git in agent sessions must not hold the host's credentials: no terminal
#: prompts, askpass always fails, and `credential.helper=` empty **clears**
#: the helper list declared at system/global — osxkeychain is not queried
#: (measured 2026-09-06, git 2.53: fake helper not called, `could not read
#: Username`).  The three `GIT_CONFIG_*` vars go together: COUNT without
#: KEY/VALUE crashes git.  Push/merge is the harness's job
#: (`worktree.merge_story`) — the harness process does not receive this set,
#: only the client process does.
GIT_NO_CREDENTIALS: dict[str, str] = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": shutil.which("false") or "/usr/bin/false",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "credential.helper",
    "GIT_CONFIG_VALUE_0": "",
}


def resolve_binary(name: str) -> list[str]:
    """The argv prefix that actually starts `name` on this OS — empty if it is
    not installed.

    `subprocess` does not search `PATHEXT`, and `CreateProcess` cannot execute
    a `.cmd`/`.bat` shim at all.  Both CLIs install as such a shim on Windows
    (npm/bun), so passing the bare name raises **WinError 2 "cannot find the
    file"** on a machine where the CLI is installed and `shutil.which` finds
    it — reported 2026-09-09 by a user running `aisef plan --client opencode`
    on Windows.  Resolve the real path, and hand a shim to the interpreter
    that can run it.
    """
    path = shutil.which(name)
    if not path:
        return []
    # `os.path.splitext`, not `Path`: building a `Path` from a Windows string
    # picks the running OS's flavour, and a test that fakes `os.name` then
    # asks pathlib for a `WindowsPath` on Linux — green on 3.14, an error on
    # 3.11/3.12 where pathlib reads `os.name` at instantiation (CI, bug 29's
    # class again).
    if sys.platform == "win32" and os.path.splitext(path)[1].lower() in (".cmd", ".bat"):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", path]
    return [path]


def split_command(command: str) -> list[str]:
    """Split a command line into argv the way the host OS would.

    `shlex.split` is POSIX: backslash escapes the next character. Windows
    paths are made of backslashes, so `C:\\hostedtoolcache\\...\\python.exe -c x`
    split into `C:hostedtoolcache...python.exe` and the program simply
    vanished -- every project command carrying an absolute path failed with
    "cannot run". Windows keeps backslashes literal and groups only with
    double quotes, so lex it that way there.
    """
    if sys.platform != "win32":
        return shlex.split(command)
    lex = shlex.shlex(command, posix=True)
    lex.whitespace_split = True
    lex.escape = ""  # backslash is an ordinary character on Windows
    lex.quotes = '"'  # cmd does not group with single quotes
    return list(lex)


#: Characters `cmd.exe` passes through untouched. Anything else gets quoted:
#: on Windows `& | ^ < > ( )` are metacharacters, so a project path holding one
#: is a broken command line at best and an injection at worst.
_WIN_BARE = re.compile(r"^[A-Za-z0-9_@%+=:,./\\-]+$")


def quote_command(argv: Iterable[str]) -> str:
    """Join argv into one command line the host shell splits back correctly.

    `shlex.quote` is POSIX: it wraps in **single** quotes, which cmd.exe treats
    as ordinary characters. On Windows that turned the framework's own command
    into `'C:\\...\\python.exe' -m aisef.cli` -- a program name that does not
    exist, printed into every prompt and every guard hook.
    """
    if sys.platform != "win32":
        return " ".join(shlex.quote(p) for p in argv)
    # A Windows path cannot contain `"`, so doubling is only for malformed input.
    return " ".join(
        p if _WIN_BARE.match(p) else '"' + p.replace('"', '""') + '"' for p in argv
    )


def runnable(cmd: list[str]) -> list[str]:
    """`cmd` with its program resolved so this OS can actually start it.

    Project commands are `npm test`, `npm run lint`, `npx playwright …` — all
    `.cmd` shims on Windows, which `CreateProcess` cannot execute and
    `subprocess` will not find because it does not search `PATHEXT`. Every one
    of them came back as `[WinError 2] The system cannot find the file
    specified`, exit 127, "tool not installed" — on a machine where npm is
    installed and working (reported 2026-09-09). Unresolvable programs are
    left untouched so the caller still reports the original error.
    """
    if not cmd:
        return cmd
    resolved = resolve_binary(cmd[0])
    return [*resolved, *cmd[1:]] if resolved else list(cmd)


#: Variables that decide **who the agent authenticates as**.  They are kept
#: (a user may legitimately authenticate this way) but they are also the first
#: suspect when a session comes back 401: a stale key in the operator's shell
#: silently outranks a working `claude.ai` login, and the CLI says so only in a
#: line that never reaches the harness (measured 2026-09-12).
AUTH_ENV_NAMES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                  "ANTHROPIC_BASE_URL")


#: Clients that actually read `AUTH_ENV_NAMES`.  Naming those variables for any
#: other client points the reader at a credential the failed request never
#: touched — and the variable being *present in the shell* is not evidence it
#: was used (lỗi 160).
ENV_AUTH_CLIENTS = ("claude",)


def auth_hint(env: dict[str, str], *, client: str = "", model: str = "") -> str:
    """One sentence naming **which path** was rejected, and what it authenticated with.

    Never the value — only the variable name, which is what the operator needs
    to act.

    The client and model come first because they are what attributes a 401 to a
    request (lỗi 160).  Measured on this repository 2026-09-14: the marks-cli
    corpus runs `client=opencode model=9router/mycombo`, an `aisef run` without
    `--client opencode` fell back to the `claude` default, and the resulting
    message named `ANTHROPIC_API_KEY`.  That was true of that session, but it
    described the *credential source* and not the *path*, and the reader
    concluded the project's key had expired — on a project whose OpenCode config
    sets `disabled_providers: ["anthropic"]` and so can never take that path at
    all.  On a project with more than one client configured, only the client and
    model attribute the failure.

    Environment variables are named only for clients that actually read them:
    `opencode` authenticates from its own config or auth store, so listing an
    Anthropic variable there sends the reader somewhere the request never went.
    """
    where = f"client `{client}`" if client else "this session"
    if model:
        where += f" with model `{model}`"
    present = [n for n in AUTH_ENV_NAMES if env.get(n)] \
        if (not client or client in ENV_AUTH_CLIENTS) else []
    if not present:
        return (f"the provider rejected the credential for {where}; it authenticated with the "
                f"client's own login or configured provider credential (no auth variable was "
                f"passed to it) — check that client's own credential, not another provider's")
    return (f"the provider rejected the credential for {where}; it authenticated with "
            + ", ".join(present)
            + " from the environment, which outranks a `claude.ai` login — unset it to fall back "
              "to that login, or replace it. If this is not the client you meant to run, pass "
              "`--client` explicitly: the wrong client is a likelier cause than a rotated key")


def child_env(spec_env: dict[str, str], *, allow_prefixes: Iterable[str] = ()) -> dict[str, str]:
    """Environment for the client process: **allowlist**, not `os.environ`
    minus a few things (ADR-005 V2).

    Before: OpenCode received the full `os.environ` (63 vars on the test
    machine), Claude only had `CLAUDE*` removed; OpenCode once logged host
    secrets to its own log.  The agent should not hold what it does not need:
    keep `ENV_KEEP` + `ENV_KEEP_PREFIXES` + the adapter's own
    `env_prefixes` + project-declared prefixes from `clients.env_allow`, plus
    the git credential disabler, then overlay harness `spec_env` on top.
    Known limitation: Claude's model token lives in the host's Keychain/OAuth,
    harness has no broker — the child session still authenticates with the
    host's account.
    """
    # An empty prefix opens all vars — drop it, not a fatal config error.
    prefixes = tuple(p for p in (*ENV_KEEP_PREFIXES, *allow_prefixes) if p)
    env = {k: v for k, v in os.environ.items() if k in ENV_KEEP or k.startswith(prefixes)}
    env.update(GIT_NO_CREDENTIALS)
    # A child Python process picks its stdout encoding from the console code
    # page; on Windows that is a legacy one and `·` or `✅` comes back
    # mangled or raises. Say it explicitly rather than inheriting a terminal's
    # opinion.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.update(spec_env)
    return env


class ClientAdapter(ABC):
    """A way to run an agent.  Implementations: Claude Code, OpenCode."""

    #: Display name, also the key used in config and reports.
    id: str = ""

    #: Host env-var prefixes **this client** authenticates with. Kept per
    #: adapter rather than global: a key belongs to the provider it pays for,
    #: and a client that reads a key it was not meant to use outranks its own
    #: login without saying so (bug 101).
    env_prefixes: tuple[str, ...] = ()

    #: Optional budget guard injected by ``phases.run``; subclasses and
    #: tests that don't need the budget path leave it ``None`` and pay
    #: no overhead.  Setter is provided so the orchestrator can wire the
    #: guard without exposing internal state to the tests that don't need it.
    _budget_guard: object | None = None

    def attach_budget_guard(self, guard: object | None) -> None:
        """Inject a ``BudgetGuard`` so every ``run`` is reserved against it.

        ``guard=None`` clears the wiring; passing the same guard twice is
        a no-op (idempotent).
        """
        self._budget_guard = guard

    @abstractmethod
    def available(self) -> bool:
        """Whether the client is installed on this machine."""

    @abstractmethod
    def capabilities(self) -> dict[Capability, Support]:
        """Honestly declare support level for each capability."""

    @abstractmethod
    def run(self, spec: RunSpec) -> RunResult:
        """Run one round, return a normalised result."""

    # ------------------------------------------------------------ utilities

    def supports(self, capability: Capability) -> Support:
        return self.capabilities().get(capability, Support.UNSUPPORTED)

    def guards_block_at_source(self) -> bool:
        """Whether this client's guards block at source or only check after."""
        return self.supports(Capability.PRE_TOOL_GUARD).blocks_at_source

    def degradations(self) -> list[str]:
        """Capabilities not at the ideal level — must be declared in reports."""
        out = []
        for cap, support in self.capabilities().items():
            if support is not Support.NATIVE:
                out.append(f"{cap.value}: {support.value}")
        return sorted(out)


# ------------------------------------------------------------ process trees
#
# Put a child in its own process group so a stop can kill the **whole tree**,
# not only the direct child. Windows has no process groups in the POSIX sense;
# `CREATE_NEW_PROCESS_GROUP` is what `taskkill /T` walks. First measured on a
# tool run that started a server (Playwright's `webServer`, lỗi 15); the same
# hazard on the agent side: `opencode.CMD` is a cmd.exe shim around node, so
# `proc.kill()` at the turn cap killed the shim, node kept the pipes, and the
# harness — blocked on their EOF — counted 186 turns against a cap of 40
# (LedgerLock 2026-09-15, lỗi 181 / D-027).
OWN_GROUP: dict = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}  # type: ignore[attr-defined]
    if sys.platform == "win32" else {"start_new_session": True}
)


def kill_tree(proc: subprocess.Popen) -> None:
    """SIGKILL the process **and everything it spawned**."""
    if sys.platform == "win32":
        # In-process first: spawning `taskkill` costs ~0.2 s on a CI runner,
        # and at one turn per 0.1 s that is one turn past the cap (measured
        # 2026-09-15, CI run 34959902843: 6 turns against a cap of 5, where
        # 1.7.2's direct TerminateProcess stopped at exactly 5). The snapshot
        # walk terminates the same tree `taskkill /T` walks, without the spawn.
        if not _kill_tree_win32(proc.pid):
            subprocess.call(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return
    import signal
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except OSError:
        proc.kill()          # group already gone, or not ours to signal


def _kill_tree_win32(root_pid: int) -> bool:
    """Terminate `root_pid` and every descendant through the Win32 API.

    One process snapshot (`CreateToolhelp32Snapshot`), a parent→children map,
    the root first (so it spawns nothing more), then every descendant found in
    the snapshot. False when the API is unavailable — the caller falls back to
    `taskkill`. A descendant created between snapshot and kill is the same
    race `taskkill /T` has; the window here is milliseconds, not a spawn.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    invalid = ctypes.c_void_p(-1).value
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)          # TH32CS_SNAPPROCESS
    if not snap or snap == invalid:
        return False
    children: dict[int, list[int]] = {}
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            children.setdefault(int(e.th32ParentProcessID), []).append(int(e.th32ProcessID))
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    order, stack = [], [root_pid]
    while stack:
        pid = stack.pop()
        order.append(pid)
        stack.extend(children.get(pid, []))
    for pid in order:                                     # root first
        h = k32.OpenProcess(0x0001, False, pid)           # PROCESS_TERMINATE
        if h:
            k32.TerminateProcess(h, 1)
            k32.CloseHandle(h)
    return True


# ------------------------------------------------------------ partial-stream capture
#
# `subprocess.communicate(timeout=)` is unsafe for clients whose output we
# must *parse* even if they time out: on `TimeoutExpired` the child is still
# writing to its stdout pipe, the framework calls `proc.kill()`, and the
# subsequent `proc.communicate()` drains only what the pipe buffer held at
# that moment.  For our adapters the cost/turn signal lives in the *last*
# line of the stream (`result` event for Claude Code, `step_finish` for
# OpenCode), so a timeout right before that line wipes the entire evidence
# of the spend — `BENCH-REPORT-v0.3.0.md` documented 14/96 sessions with
# cost=$0 because of this.
#
# `_stream_with_timeout` runs a reader thread from Popen start, accumulates
# lines into a thread-safe list as they arrive, and lets the parent enforce
# the timeout via `proc.wait(timeout=)`.  On timeout, the parent kills the
# child and waits without timeout; whatever the reader thread collected up
# to that point is the partial stream we have.  Lines are kept as-is (text
# mode, python line buffering for pipes is partial — we accept that the
# last line may be incomplete and split on newlines is the caller's
# responsibility).

def _drain(stream, lines: list[str], partial: list[str], lock: threading.Lock) -> None:
    """Read lines from a pipe stream until EOF, appending to a shared list.

    `partial` collects the trailing buffer when the last line lacks a
    newline (the child process was killed mid-write).  Callers can decide
    to drop or include it; we surface it so the parser can decide.
    """
    pending = ""
    try:
        while True:
            chunk = stream.read(1)
            if not chunk:
                if pending:
                    with lock:
                        partial.append(pending)
                return
            if chunk == "\n":
                with lock:
                    lines.append(pending)
                pending = ""
            else:
                pending += chunk
    finally:
        # Pipe owns an OS fd; releasing it at EOF silences the
        # ResourceWarning on CPython 3.13 and frees the descriptor
        # immediately instead of on GC.  Closing a pipe that was already
        # half-closed raises ValueError on CPython; swallow that case.
        try:
            stream.close()
        except ValueError:
            pass


def _stream_with_timeout(proc, *, timeout_seconds: int, stop_when=None
                         ) -> tuple[list[str], str, bool]:
    """Run `proc` to completion with a hard wall-clock deadline, returning
    ``(lines, stderr, timed_out)``.

    * ``lines`` — every newline-terminated line written to stdout up to the
      end of the process (or up to the millisecond before kill on timeout).
    * ``stderr`` — full stderr text (only read after exit; short).
    * ``timed_out`` — whether the deadline fired before the child exited.

    ``stop_when`` là **trần không phải thời gian**: một hàm nhận các dòng mới
    xuất hiện từ lần hỏi trước và trả `True` khi phải dừng tiến trình. Cần nó
    vì có CLI không có cờ giới hạn lượt nào (OpenCode), nên `run.max_turns`
    không ai thi hành — đo được trên cohort C-1: khai trần 40, phiên chạy 61
    lượt và chỉ dừng vì đồng hồ (`docs/BENCH-OBSERVATIONS-C1.md` § O-10).
    Không truyền thì đường đi cũ giữ nguyên từng dòng.
    """
    lines: list[str] = []
    partial: list[str] = []
    lock = threading.Lock()

    # The reader thread reads from the live pipe.  Even if `proc.wait`
    # times out and the child is killed, the thread keeps draining until
    # EOF, so the partial stream survives whatever event forced the kill.
    from ..harness.process_owner import reap_group, win_job
    job = win_job(proc)                        # Windows: descendants die when the job closes (F5 / D-024)
    reader = threading.Thread(
        target=_drain,
        args=(proc.stdout, lines, partial, lock),
        daemon=True,
    )
    reader.start()

    # `kill_tree`, never `proc.kill()`: the direct child may be a launcher
    # (`opencode.CMD` on Windows is a cmd.exe shim around node). Killing the
    # shim left node alive, still writing to the inherited pipes, and the
    # harness — blocked on that pipe's EOF — counted every turn it wrote:
    # 186 turns against a cap of 40 (LedgerLock 2026-09-15, lỗi 181 / D-027).
    # The adapters spawn with `OWN_GROUP` so the whole tree is addressable.
    timed_out = False
    try:
        if stop_when is None:
            try:
                proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                kill_tree(proc)
                proc.wait()
        else:
            han = time.monotonic() + timeout_seconds
            da_doc = 0
            while True:
                try:
                    proc.wait(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    pass
                with lock:
                    moi, da_doc = lines[da_doc:], len(lines)
                if moi and stop_when(moi):
                    kill_tree(proc)
                    proc.wait()
                    break
                if time.monotonic() >= han:
                    timed_out = True
                    kill_tree(proc)
                    proc.wait()
                    break
    except BaseException:
        # Ctrl-C or a dying orchestrator: the child sits in its own group and
        # would outlive us, streaming into a pipe nobody reads. Take the tree
        # down before propagating — an interrupted run must not leave a
        # session running against the worktree.
        kill_tree(proc)
        raise

    reader.join(timeout=2.0)
    # F5 / INV-L.2: members of the session's process group that outlived the leader (a dev server, a `git gc`)
    # are terminated and verified dead here, on EVERY exit — before anything removes the workspace (D-024)
    proc.aisef_reaped = reap_group(proc)
    job.close()
    if proc.stderr:
        try:
            stderr = proc.stderr.read()
            proc.stderr.close()
        except (ValueError, OSError):
            stderr = ""
    else:
        stderr = ""

    with lock:
        snapshot = list(lines)
        trailing = "".join(partial)
    if trailing:
        # The last block may be an incomplete JSON object — surface it; the
        # parser will skip it cleanly.
        snapshot.append(trailing)
    return snapshot, stderr, timed_out
