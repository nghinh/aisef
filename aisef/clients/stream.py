"""Parse the ``stream-json`` output of Claude Code CLI.

The stream structure was established empirically (spike S1, S2 — see
``docs/SPIKE-REPORT.md``), not inferred from documentation.  Two fixtures in
``tests/fixtures/`` are real streams produced by ``claude -p``.

Observed event types::

    system/hook_started      hook execution started
    system/hook_response     hook finished: exit_code, outcome, stdout, stderr
    system/init              session initialised
    assistant                model speaks or calls a tool
    user                     tool result returned (is_error when blocked)
    rate_limit_event         rate limit information
    system/post_turn_summary turn summary
    result                   **final event** — cost, latency, usage, denials

The most valuable data is in ``result``: ``total_cost_usd``, ``duration_ms``,
``ttft_ms``, ``usage``, and ``permission_denials`` — a list of guard-blocked
tool calls, including the content the agent intended to write.  This is
machine-readable evidence for the evidence store, not the agent's self-report.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable


#: Pattern identifying messages **from hooks**, not every tool error containing
#: the word "hook".  Matching the substring "hook" is too broad: a React project
#: talks about hooks all day, and a failed ``grep`` on ``useEffect`` is enough
#: to flip the ``guard_blocked`` flag.  A false positive here goes straight into
#: the acceptance report and sends the reader chasing a non-existent defect.
GUARD_MESSAGE = re.compile(
    r"(?:Pre|Post)ToolUse:\S*\s+hook\b|\bStop:?\s*hook\b|\bhook error\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ToolUse:
    name: str
    tool_use_id: str
    input: dict


@dataclass(frozen=True)
class Denial:
    """A guard-blocked tool call.  Extracted from ``result.permission_denials``."""

    tool_name: str
    tool_use_id: str
    tool_input: dict

    @property
    def target_path(self) -> str:
        """The blocked path, if the tool has a path concept."""
        return self.tool_input.get("file_path", "")


@dataclass(frozen=True)
class HookRun:
    """A single hook execution.  ``exit_code == 2`` is Claude Code's blocking convention."""

    name: str
    event: str
    exit_code: int
    outcome: str
    stderr: str = ""

    @property
    def blocked(self) -> bool:
        return self.exit_code == 2


@dataclass
class RunResult:
    """Normalised result of one client run."""

    ok: bool = False
    text: str = ""
    session_id: str = ""
    num_turns: int = 0
    stop_reason: str = ""

    cost_usd: float = 0.0
    duration_ms: int = 0
    duration_api_ms: int = 0
    ttft_ms: int = 0

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    tool_uses: list[ToolUse] = field(default_factory=list)
    denials: list[Denial] = field(default_factory=list)
    hooks: list[HookRun] = field(default_factory=list)
    #: All assistant text segments in order.  ``text`` is only the final one —
    #: and the final segment may be a response to the Stop hook rather than to
    #: the task (conformance C4 failed because of this, 2026-09-05).
    texts: list[str] = field(default_factory=list)
    #: Messages from hooks that blocked a tool.  Taken from ``tool_result``,
    #: not ``hook_response``: observation on real streams shows Claude Code
    #: does **not** emit ``hook_response`` for blocking hooks — it puts the
    #: reason directly into the tool result for the agent to read.
    guard_messages: list[str] = field(default_factory=list)

    error: str = ""
    raw_result: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_tokens
            + self.cache_read_tokens
        )

    @property
    def guard_blocked(self) -> bool:
        """True when a **framework guard** blocked at least one action.

        This is the quality signal: the agent intended to do something forbidden.
        """
        return bool(self.guard_messages) or any(h.blocked for h in self.hooks)

    @property
    def permission_limited(self) -> bool:
        """True when the client denied a tool for permission reasons, not guard.

        Example: ``WebSearch`` blocked in a network-less environment.  This is
        an **environment limitation**, not agent misbehaviour — conflating it
        with guard blocks misreports the nature of the failure and leads to
        wrong decisions about retrying or blocking the story.
        """
        return bool(self.denials) and not self.guard_blocked

    @property
    def was_blocked(self) -> bool:
        """Whether any action was denied, regardless of reason."""
        return bool(self.denials) or self.guard_blocked

    def evidence(self) -> dict:
        """Subset to include in ``evidence/{story}.json``."""
        return {
            "ok": self.ok,
            "cost_usd": round(self.cost_usd, 6),
            "duration_ms": self.duration_ms,
            "ttft_ms": self.ttft_ms,
            "tokens": {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "cache_creation": self.cache_creation_tokens,
                "cache_read": self.cache_read_tokens,
            },
            "num_turns": self.num_turns,
            "session_id": self.session_id,
            "denials": [
                {"tool": d.tool_name, "path": d.target_path} for d in self.denials
            ],
            "guard_blocked": self.guard_blocked,
            "guard_messages": self.guard_messages,
            "permission_limited": self.permission_limited,
            "error": self.error,
        }


#: Normalised exit status across all clients (ADR-005 V11 B).  Closed set:
#: ``aisef status`` counts by it, ``Attempt.infra`` reads it instead of probing strings.
EXIT_STATUSES = ("ok", "max_turns", "timeout", "cost", "context", "permission", "infra", "error")

#: Exit statuses that are **not the agent's fault** — retries do not count
#: against the quality limit (``run.max_retries``); infra has its own limit.
INFRA_STATUSES = ("timeout", "infra")


def exit_status_of(res: RunResult) -> str:
    """Infer exit status from ``subtype``/``terminal_reason``/``stop_reason``/
    ``error``.  Pure function: reads only ``res``, does not know configured
    ``max_turns`` — the turn ceiling is what the client itself reports
    (``terminal_reason: max_turns``, e9 01-01 61/60, 01-05 91/90).

    Order is intentional: turn ceiling before infra — hitting the turn limit
    usually comes with an error message, and classifying it as "infra" would
    let turn-hungry stories retry for free.  Client killing on timeout reports
    "exceeded <n>s" (``claude_code.run``, ``opencode.run``); no ``result``
    event means the process died mid-run.
    """
    if res.ok:
        return "ok"
    raw = res.raw_result or {}
    err = (res.error or "").lower()
    why = " ".join(
        [str(raw.get(k) or "") for k in ("subtype", "terminal_reason", "stop_reason")]
        + [str(raw.get("result") or "")[:300], err]
    ).lower()
    if "max_turns" in why:
        return "max_turns"
    if err.startswith("exceeded "):
        return "timeout"
    if "budget" in why or "max_cost" in why:
        return "cost"
    if any(m in why for m in ("prompt is too long", "context window", "context_length", "max_tokens")):
        return "context"
    if raw.get("api_error_status") or any(
        m in why for m in ("api_error", "overloaded", "connection",
                           "cannot run", "without a result event")
    ):
        return "infra"
    if res.permission_limited:
        return "permission"
    return "error"


def _collect_assistant_tools(event: dict, out: list[ToolUse]) -> str:
    """Collect tool_use and text from an assistant event."""
    text_parts = []
    for block in event.get("message", {}).get("content", []) or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            out.append(
                ToolUse(
                    name=block.get("name", ""),
                    tool_use_id=block.get("id", ""),
                    input=block.get("input") or {},
                )
            )
        elif block.get("type") == "text":
            text_parts.append(block.get("text", ""))
    return "".join(text_parts)


def parse_stream(lines: Iterable[str]) -> RunResult:
    """Parse ``stream-json`` into ``RunResult``.

    Malformed lines are silently skipped rather than crashing the entire run:
    losing one log line is not worth losing the result of an entire story.
    """
    res = RunResult()
    assistant_text: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue

        etype = ev.get("type")

        if etype == "assistant":
            txt = _collect_assistant_tools(ev, res.tool_uses)
            if txt.strip():
                assistant_text.append(txt)

        elif etype == "user":
            for block in (ev.get("message", {}) or {}).get("content", []) or []:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                if not block.get("is_error"):
                    continue
                body = str(block.get("content") or "")
                if GUARD_MESSAGE.search(body):
                    res.guard_messages.append(body[:300])

        elif etype == "system" and ev.get("subtype") == "hook_response":
            res.hooks.append(
                HookRun(
                    name=ev.get("hook_name", ""),
                    event=ev.get("hook_event", ""),
                    exit_code=int(ev.get("exit_code") or 0),
                    outcome=ev.get("outcome", ""),
                    stderr=ev.get("stderr", "") or "",
                )
            )

        elif etype == "result":
            res.raw_result = ev
            res.ok = ev.get("subtype") == "success" and not ev.get("is_error")
            res.text = ev.get("result", "") or ""
            res.session_id = ev.get("session_id", "") or ""
            res.num_turns = int(ev.get("num_turns") or 0)
            res.stop_reason = ev.get("stop_reason", "") or ""

            res.cost_usd = float(ev.get("total_cost_usd") or 0.0)
            res.duration_ms = int(ev.get("duration_ms") or 0)
            res.duration_api_ms = int(ev.get("duration_api_ms") or 0)
            res.ttft_ms = int(ev.get("ttft_ms") or 0)

            usage = ev.get("usage") or {}
            res.input_tokens = int(usage.get("input_tokens") or 0)
            res.output_tokens = int(usage.get("output_tokens") or 0)
            res.cache_creation_tokens = int(usage.get("cache_creation_input_tokens") or 0)
            res.cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)

            for d in ev.get("permission_denials") or []:
                res.denials.append(
                    Denial(
                        tool_name=d.get("tool_name", ""),
                        tool_use_id=d.get("tool_use_id", ""),
                        tool_input=d.get("tool_input") or {},
                    )
                )

            if ev.get("is_error") or ev.get("api_error_status"):
                # Order is intentional.  ``subtype`` is still "success" even
                # when ``is_error`` is true, so extracting it would yield an
                # error message of "success" — meaningless to the reader and
                # to retry logic.
                res.error = str(
                    ev.get("api_error_status")
                    or ev.get("terminal_reason")
                    or (ev.get("result") or "").strip()[:200]
                    or "unknown error"
                )

    res.texts = assistant_text
    if not res.text and assistant_text:
        res.text = "\n".join(assistant_text)

    # No ``result`` event means the process died mid-run.  Must be clearly
    # distinguished from "ran to completion but failed" — the two need
    # different handling (infra error != quality error).
    if not res.raw_result:
        res.ok = False
        res.error = res.error or "stream ended without a result event"

    return res


def parse_file(path) -> RunResult:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_stream(fh)
