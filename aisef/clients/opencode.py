"""Run agent via OpenCode CLI.

**Proven to actually block** (2026-09-05, opencode 1.18.26, model
``9router/mycombo``, agent standing in a project subdirectory):

* ``rm -rf /tmp/moi-thu-nghiem`` -> tool reported failed with the exact
  guard stderr, and the files in that directory **still exist** after the run;
* ``Write ping.py`` containing ``os.system(f"ping -c 1 {host}")`` -> tool
  reported failed with the exact guard stderr, and **no file was written to
  disk**.

The second test was necessary because the earlier API-key-write test was
worthless: the model refused on its own before calling the tool, so it proved
the model is obedient, not that the guard blocks.  The test must be something
the model is willing to do.

Also confirmed that the plugin in ``.opencode/plugin/`` at project level is
loaded when the agent runs from a subdirectory — exactly the story worktree
scenario.

Therefore ``PRE_TOOL_GUARD`` is declared ``NATIVE``.  The remaining two items
are honestly downgraded: OpenCode has no turn limit and does not emit a
structured event stream, so cost must be queried separately.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .base import Capability, ClientAdapter, RunSpec, Support, child_env, resolve_binary
from .stream import RunResult

BINARY = "opencode"


_TOOL_NAMES = {"read": "Read", "write": "Write", "edit": "Edit", "bash": "Bash", "glob": "Glob",
               "grep": "Grep", "list": "LS", "webfetch": "WebFetch", "todowrite": "TodoWrite", "skill": "Skill"}


def parse_json_events(lines) -> RunResult:
    """`opencode run --format json` stream to normalised `RunResult`.  Non-JSON
    lines (banners, warnings) are silently skipped, never raised."""
    import json as _json

    from .stream import ToolUse

    res = RunResult()
    texts: list[str] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = _json.loads(line)
        except ValueError:
            continue
        part = ev.get("part") or {}
        kind = ev.get("type")
        if kind == "text":
            texts.append(str(part.get("text") or ""))
        elif kind == "tool_use":
            name = str(part.get("tool") or "")
            state = part.get("state") or {}
            res.tool_uses.append(ToolUse(name=_TOOL_NAMES.get(name.lower(), name), tool_use_id=str(part.get("callID") or ""),
                                         input=dict(state.get("input") or {})))
            if state.get("status") == "error":
                res.guard_messages.append(str(state.get("output") or state.get("error") or "")[:300])
        elif kind == "error":
            # OpenCode reports a provider failure as a JSON event and exits
            # non-zero with an empty stderr, so the harness used to record
            # `exit != 0` and nothing else — the reason ("Bad Gateway", 502,
            # retryable) sat in OpenCode's own log file where no operator
            # looks. Measured 2026-09-09: a planning phase died permanently on
            # a transient 502 because the status never reached
            # `exit_status_of`, which would have classified it as infra and
            # retried.
            info = ev.get("error") or {}
            data = info.get("data") or {}
            ten = str(info.get("name") or "error")
            msg = str(data.get("message") or "")[:200]
            code = data.get("statusCode")
            res.error = f"{ten}: {msg}" + (f" (HTTP {code})" if code else "")
            raw = dict(res.raw_result or {})
            if code:
                raw["api_error_status"] = code
            if data.get("isRetryable"):
                raw["retryable"] = True
            res.raw_result = raw
        elif kind == "step_finish":
            res.num_turns += 1
            tk = part.get("tokens") or {}
            res.input_tokens += int(tk.get("input") or 0)
            res.output_tokens += int(tk.get("output") or 0)
            cache = tk.get("cache") or {}
            res.cache_read_tokens += int(cache.get("read") or 0)
            res.cache_creation_tokens += int(cache.get("write") or 0)
            res.cost_usd += float(part.get("cost") or 0.0)
        if ev.get("sessionID") and not res.session_id:
            res.session_id = str(ev["sessionID"])
    res.text = "".join(texts)
    return res


class OpenCodeAdapter(ClientAdapter):
    id = "opencode"

    def __init__(self, binary: str = BINARY):
        self.binary = binary

    def available(self) -> bool:
        return bool(resolve_binary(self.binary))

    def capabilities(self) -> dict[Capability, Support]:
        return {
            Capability.HEADLESS: Support.NATIVE,            # opencode run
            # Evidence `par` STORY-02-01: cost=0, turns=0 across all four sessions.
            # `--format json` is in `--help` but was unproven — until then, declare
            # honestly as absent. (upgrade task open, see ACTION-PLAN batch 2)
            Capability.MACHINE_OUTPUT: Support.NATIVE,     # --format json, measured 2026-09-05
            Capability.PRE_TOOL_GUARD: Support.NATIVE,     # proven 2026-09-05, see docstring
            Capability.TOOL_ALLOWLIST: Support.EMULATED,  # emulated by: guardrails.check_role_tool
            Capability.DIR_ALLOWLIST: Support.UNSUPPORTED,  # no equivalent flag
            Capability.SUBAGENT: Support.NATIVE,            # opencode agent
            Capability.MODEL_ROUTING: Support.NATIVE,       # --model
            # `opencode stats` exists but no code calls it or writes to evidence;
            # real evidence records cost=0. No emulation code -> do not declare emulated.
            Capability.COST_REPORTING: Support.NATIVE,     # step_finish.cost/tokens — provider-reported
            Capability.TURN_LIMIT: Support.UNSUPPORTED,     # use timeout instead
        }

    def build_command(self, spec: RunSpec) -> list[str]:
        # `--dir` not just `cwd=`: OpenCode discovers the project root on its
        # own, and with a worktree inside `<project>/.aisef/worktrees/` it
        # walks up to the project root then **tells the model that is the
        # working directory**. The model then reads/writes using absolute paths
        # into the project root and sets each bash command's `workdir` there —
        # work lands directly on the main tree, worktree stays empty. Observed
        # in session logs:
        #
        #   {"tool":"read","input":{"filePath":"/…/par/src/reverse-words.js"}}
        #   {"tool":"bash","input":{"command":"git add … && git commit …",
        #                           "workdir":"/…/par"}}
        # The prompt goes to **stdin**, not argv: Windows caps a command line
        # at 32767 characters and a planning prompt is 16-23k on its own
        # (`WinError 206`, reported 2026-09-09).  `opencode run` with no
        # message reads the prompt from stdin — measured 2026-09-09.
        cmd = [*(resolve_binary(self.binary) or [self.binary]),
               "run", "--dir", str(spec.workdir)]
        if spec.model:
            cmd += ["--model", spec.model]
        cmd.insert(2, "--format")
        cmd.insert(3, "json")
        return cmd

    def run(self, spec: RunSpec) -> RunResult:
        if not self.available():
            return RunResult(ok=False, error=f"command not found: {self.binary}")
        if not Path(spec.workdir).is_dir():
            return RunResult(ok=False, error=f"workdir does not exist: {spec.workdir}")

        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                self.build_command(spec),
                cwd=str(spec.workdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                # Allowlist, not `os.environ` (ADR-005 V2): OpenCode once received
                # the full host environment and logged secrets to its own log.
                # Providers reading keys from custom env vars declare `clients.env_allow`.
                env=child_env(spec.env, allow_prefixes=spec.env_allow),
                stdin=subprocess.PIPE,
            )
        except OSError as e:
            return RunResult(ok=False, error=f"cannot run: {e}")

        timed_out = False
        try:
            stdout, stderr = proc.communicate(input=spec.prompt, timeout=spec.timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            timed_out = True

        # `--format json` (measured 2026-09-05, OpenCode 1.18.26): one event per
        # line — `step_start` / `text` / `tool_use` (part.tool, state.input/output)
        # / `step_finish` (tokens, cost). Cost is the provider-reported number —
        # 9router reports 0, that is the provider's truth, not the harness's.
        res = parse_json_events(stdout.splitlines())
        res.ok = proc.returncode == 0 and not timed_out
        res.duration_ms = int((time.monotonic() - started) * 1000)
        if timed_out:
            res.error = f"exceeded {spec.timeout_seconds}s"
        elif proc.returncode != 0:
            # Keep what the stream already explained; stderr is empty here.
            res.error = res.error or stderr.strip()[:500] or "exit != 0"
        res.raw_result = {"returncode": proc.returncode, **res.raw_result}
        return res
