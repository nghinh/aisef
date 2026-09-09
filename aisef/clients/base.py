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
import shutil
import sys
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
ENV_KEEP_PREFIXES = ("LC_", "ANTHROPIC_", "AISEF_")
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


def child_env(spec_env: dict[str, str], *, allow_prefixes: Iterable[str] = ()) -> dict[str, str]:
    """Environment for the client process: **allowlist**, not `os.environ`
    minus a few things (ADR-005 V2).

    Before: OpenCode received the full `os.environ` (63 vars on the test
    machine), Claude only had `CLAUDE*` removed; OpenCode once logged host
    secrets to its own log.  The agent should not hold what it does not need:
    keep `ENV_KEEP` + `ENV_KEEP_PREFIXES` + project-declared prefixes from
    `clients.env_allow`, plus the git credential disabler, then overlay
    harness `spec_env` on top.  Known limitation: Claude's model token
    lives in the host's Keychain/OAuth, harness has no broker — the child
    session still authenticates with the host's account.
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
