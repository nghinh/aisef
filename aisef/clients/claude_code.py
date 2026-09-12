"""Run agent via Claude Code CLI.

Every flag used here was verified empirically (spike S1, S2 —
`docs/SPIKE-REPORT.md`), not inferred from documentation:

* ``--output-format stream-json --verbose`` yields a readable event stream
  ending with a ``result`` event carrying cost, latency, usage, and
  ``permission_denials``;
* ``--settings`` wires hooks, and a hook returning exit 2 **actually blocks**
  the tool — even under ``--permission-mode acceptEdits``;
* ``< /dev/null`` is mandatory, otherwise the CLI waits on stdin for three
  seconds on every invocation.

**Isolation from user's global config** (measured 2026-09-05, Claude Code
2.1.236, conformance C3/C4 failed after host set ``permissions.defaultMode:
"auto"`` in ``~/.claude/settings.json``): a child session inheriting that
mode **loses Glob/Grep** and is told to "prefer Bash" — i.e. write files
via heredoc and bypass all ``Write|Edit`` guards; user MCP servers (Google
Drive...) and global hooks also leak in.  The harness does not trust the
client, much less the host config: fixed mode ``acceptEdits``, explicitly
listed tools (``DEFAULT_TOOLS``), load only project settings + harness
``--settings``, no external MCP.  Re-measured same day: Glob/Grep present,
MCP 0, user hooks 0, write-scope guard still blocks.

**Do hooks reach the worktree?** (measured 2026-09-05 on `par`, claude CLI,
`.claude/` **not** committed so worktree lacks that directory; each variant
runs one `-p` session telling the agent to Write a file; count self-recorded
guard events):

=====  ==============================  ==========  ====
Var    cwd / flags                     guard logs  file
=====  ==============================  ==========  ====
A      worktree, ``--settings <file>`` 2           yes
B      worktree, ``--settings <json>`` 2           yes
C      project root (has ``.claude/``) 2           yes
D      worktree, no flags              **0**       yes
=====  ==============================  ==========  ====

D is the shape of every run before G4: the story completes, files are
written, **not a single guard runs**, and evidence looks identical to a
well-behaved agent.  Therefore `implement.py` always passes ``--settings``
(``_attach_settings``), and the story gate includes a "guard ran" item
reading the ``GUARD_SEEN`` heartbeat — two layers, the second catches the
first failing.

A more expensive lesson: the first check run after adding ``--settings``
still reported "guard did not run" — session logs showed the hook fired
17 times but the agent wrote files **only via Bash**, so ``write-scope``
(Write|Edit) was never called and there was nothing to record.  Since then,
the guard writes its own heartbeat, and ``diff-scope`` records
``FILE_CHANGE`` for files whose mtime is newer than the last test run.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .base import Capability, ClientAdapter, RunSpec, Support, _stream_with_timeout, child_env, resolve_binary
from .stream import RunResult, parse_stream

BINARY = "claude"

#: Fixed permission mode for child sessions — not determined by the host's global mode.
PERMISSION_MODE = "acceptEdits"
#: Tools allowed when the role does not specify its own list.  `acceptEdits`
#: auto-approves Write/Edit in the working directory but Bash must be listed
#: explicitly, otherwise `-p` denies it and the agent cannot run `aisef tool
#: test`.  Role-level `--disallowed-tools` (reviewer/security) still win.
DEFAULT_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "Bash", "NotebookEdit")


class ClaudeCodeAdapter(ClientAdapter):
    id = "claude"

    def __init__(self, binary: str = BINARY):
        self.binary = binary

    def available(self) -> bool:
        return bool(resolve_binary(self.binary))

    def capabilities(self) -> dict[Capability, Support]:
        return {
            Capability.HEADLESS: Support.NATIVE,          # -p
            Capability.MACHINE_OUTPUT: Support.NATIVE,    # --output-format stream-json
            Capability.PRE_TOOL_GUARD: Support.NATIVE,    # --settings + PreToolUse (S2)
            Capability.TOOL_ALLOWLIST: Support.NATIVE,    # --allowed-tools
            Capability.DIR_ALLOWLIST: Support.NATIVE,     # --add-dir
            Capability.SUBAGENT: Support.NATIVE,          # --agents
            Capability.MODEL_ROUTING: Support.NATIVE,     # --model
            Capability.COST_REPORTING: Support.NATIVE,    # result.total_cost_usd
            Capability.TURN_LIMIT: Support.NATIVE,        # --max-turns
        }

    def build_command(self, spec: RunSpec) -> list[str]:
        """Build the command line.  Separated so it can be tested without calling a model."""
        # The prompt goes to **stdin**, not argv.  Windows caps a command
        # line at 32767 characters and a planning prompt is 16-23k on its own:
        # `WinError 206 the filename or extension is too long`, reported
        # 2026-09-09.  Both CLIs read the prompt from stdin when no positional
        # prompt is given (measured on both, 2026-09-09).
        cmd = [
            *(resolve_binary(self.binary) or [self.binary]),
            "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--permission-mode", PERMISSION_MODE,
            "--setting-sources", "project,local",
            "--strict-mcp-config",
        ]
        if spec.system_prompt:
            cmd += ["--append-system-prompt", spec.system_prompt]
        if spec.model:
            cmd += ["--model", spec.model]
        if spec.max_turns:
            cmd += ["--max-turns", str(spec.max_turns)]
        cmd += ["--allowed-tools", *(spec.allowed_tools or DEFAULT_TOOLS)]
        if spec.disallowed_tools:
            cmd += ["--disallowed-tools", *spec.disallowed_tools]
        if spec.settings_file:
            cmd += ["--settings", str(spec.settings_file)]
        for d in spec.extra_dirs:
            cmd += ["--add-dir", str(d)]
        if spec.session_id:
            cmd += ["--session-id", spec.session_id]
        return cmd

    def run(self, spec: RunSpec) -> RunResult:
        """Run one round.  Child environment is an **allowlist** (`child_env`,
        ADR-005 V2), not the calling process's environment: the harness running
        from inside a Claude session is a real scenario, and a child session
        inheriting the parent's `CLAUDE*` flags switches to Bash instead of
        Read/Write (conformance C3, 2026-09-05); the agent does not need the
        host's secrets (C9)."""
        if not self.available():
            return RunResult(ok=False, error=f"command not found: {self.binary}")
        if not Path(spec.workdir).is_dir():
            return RunResult(ok=False, error=f"workdir does not exist: {spec.workdir}")

        try:
            proc = subprocess.Popen(
                self.build_command(spec),
                cwd=str(spec.workdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                env=child_env(spec.env, allow_prefixes=spec.env_allow),
                # The prompt is written and stdin closed straight away; an open
                # stdin makes the CLI wait 3s on every call.
                stdin=subprocess.PIPE,
            )
        except OSError as e:
            return RunResult(ok=False, error=f"cannot run: {e}")

        # Write the prompt to stdin in a small thread so a slow stdin-writer
        # cannot deadlock the parent if the child fills its stdout pipe.
        # We close stdin immediately so the CLI exits the stdin-wait prompt.
        import threading as _t
        def _feed_stdin(proc=proc, prompt=spec.prompt):
            try:
                if proc.stdin:
                    proc.stdin.write(prompt)
                    proc.stdin.close()
            except (BrokenPipeError, ValueError):
                pass
        _t.Thread(target=_feed_stdin, daemon=True).start()

        lines, stderr, timed_out = _stream_with_timeout(proc,
                                                       timeout_seconds=spec.timeout_seconds)

        result = parse_stream(lines)
        if timed_out:
            # Infrastructure signal: keep it on the error string so the
            # caller distinguishes a hard wall-clock kill from any
            # parse-derived message.  The reader thread kept collecting
            # lines up to the kill instant, so the cost/turn signal may
            # already be in `result` regardless.
            result.error = f"exceeded {spec.timeout_seconds}s"
        if not result.raw_result and stderr.strip() and not timed_out:
            result.error = result.error or stderr.strip()[:500]
        return result
