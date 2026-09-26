"""Phase 15 — adapter conformance: OpenCode and Claude Code driven by recorded streams (no model), one
provider condition at a time, the REAL ``run(RunSpec)`` on each side, and the two typed kernel outcomes
(``exit_status_of`` + the ``RunResult`` fields the story loop reads) compared side by side.

Every condition is a ``_Pair`` subclass: ``plans`` returns the recorded stream for each fake CLI,
``test_claude`` / ``test_opencode`` assert the adapter's own result, and the inherited
``test_cross_adapter_same_exit_status`` asserts both adapters land on the same status. A wrong mapping or
a disagreement is an ``@unittest.expectedFailure  # AD-xx`` — the adapters are not changed here.

Registered here (verbatim assertions in the Phase 15 report):

* AD-01 OpenCode — an empty stream with exit 0 is ``ok=True`` (no terminal event is required).
* AD-02 Claude — ``exit_status_of`` reads the session's final text (``raw_result.result``) before the
  provider's ``api_error_status``: a 502 whose last message mentions 401 is ``auth`` (SS-28, INV-F.4).
* AD-03 OpenCode — a child that dies (exit != 0, no provider error event) is ``error`` (charged to
  quality); Claude's identical death is ``infra``.
* AD-04 Claude — the child's exit code and stderr are dropped when the stream has no result event.
* AD-05 Claude — a result event arriving after the timeout kill flips ``ok=True`` / ``"ok"``;
  ``timed_out`` only rewrites ``error``.

Event shapes are copied from the adapters' parsers and from ``tests/fixtures/stream-*.jsonl`` (Claude) and
``tests/test_clients.py::TestOpenCodeLuongJson`` (OpenCode, measured 2026-09-05/09).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from aisef.clients.base import RunSpec  # noqa: E402
from aisef.clients.claude_code import ClaudeCodeAdapter  # noqa: E402
from aisef.clients.opencode import OpenCodeAdapter  # noqa: E402
from aisef.clients.stream import EXIT_STATUSES, INFRA_STATUSES, RunResult, exit_status_of, retry_delay_seconds  # noqa: E402
from aisef.harness import guardrails as g  # noqa: E402
from aisef.phases.implement import review_verdict  # noqa: E402
from tests._bin import write_exe  # noqa: E402

FAKE_CLI = Path(__file__).with_name("_fake_cli.py")
SID = "b0297b87-62cf-4fcd-ab8a-45bf5351499a"
OSID = "ses_conformance"


# ------------------------------------------------------------------ recorded event shapes

def c_result(**over) -> str:
    """Claude Code ``result`` event — the fields of ``tests/fixtures/stream-minimal.jsonl``'s last line."""
    ev = {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 3242, "duration_api_ms": 1884,
          "num_turns": 1, "result": "OK", "session_id": SID, "total_cost_usd": 0.36267, "stop_reason": "end_turn",
          "usage": {"input_tokens": 2, "cache_creation_input_tokens": 36256, "cache_read_input_tokens": 0,
                    "output_tokens": 4},
          "permission_denials": [], "terminal_reason": "completed", "api_error_status": None}
    ev.update(over)
    return json.dumps(ev)


def c_api_error(status: int, text: str, **over) -> str:
    """Provider failure as Claude Code reports it (``tests/fixtures/stream-api-error.jsonl``): ``subtype`` stays
    ``success``, ``is_error`` is set, ``terminal_reason: api_error``, the status in ``api_error_status``."""
    return c_result(is_error=True, terminal_reason="api_error", api_error_status=status, result=text,
                    total_cost_usd=0.0, **over)


def c_assistant(text: str) -> str:
    return json.dumps({"type": "assistant", "message": {"model": "claude-opus-5", "role": "assistant",
                                                        "content": [{"type": "text", "text": text}]},
                       "session_id": SID})


C_INIT = json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-5", "session_id": SID})


def o_text(text: str) -> str:
    return json.dumps({"type": "text", "timestamp": 5, "sessionID": OSID, "part": {"type": "text", "text": text}})


def o_step(cost: float = 0.0012, inp: int = 2469, out: int = 5) -> str:
    return json.dumps({"type": "step_finish", "timestamp": 6, "sessionID": OSID,
                       "part": {"type": "step-finish", "cost": cost,
                                "tokens": {"total": inp + out, "input": inp, "output": out, "reasoning": 0,
                                           "cache": {"write": 0, "read": 0}}}})


def o_error(message: str, status: int | None = None, retryable: bool = False) -> str:
    """Provider failure as ``opencode run --format json`` reports it (``aisef/clients/opencode.py``, 2026-09-09)."""
    data: dict = {"message": message, "isRetryable": retryable}
    if status:
        data["statusCode"] = status
    return json.dumps({"type": "error", "sessionID": OSID, "error": {"name": "APIError", "data": data}})


# ------------------------------------------------------------------ running the real adapter on a fake CLI

#: One shim per adapter for the whole module, pointing at a plan file each condition rewrites. Measured
#: 2026-09-16 (macOS 25.5): the *first* exec of a freshly written script costs 0.2–0.6 s (the OS assesses a
#: new executable), the same file 15 ms after that — a shim per condition made the package 20 s instead of 6.
_BIN = tempfile.TemporaryDirectory()


def _shim(adapter_id: str) -> tuple[Path, Path]:
    d = Path(_BIN.name) / adapter_id
    plan = d / "plan.json"
    if not d.is_dir():
        d.mkdir()
        argv = " ".join(f'"{a}"' for a in (sys.executable, str(FAKE_CLI), str(plan)))
        write_exe(d / "cli", posix=f'#!/bin/sh\nexec {argv} "$@"\n', windows=f"@{argv} %*\r\n")
    exe = next(p for p in d.iterdir() if p.name.startswith("cli"))   # `cli` or `cli.cmd`
    return exe, plan


def run_fake(adapter_cls, root: Path, plan: dict, **spec) -> RunResult:
    """The REAL adapter — its real ``build_command``/``resolve_binary``/spawn/kill path — against a fake CLI that
    replays ``plan``. The fake is a Python script behind the same shim ``tests/_bin.write_exe`` gives every
    client test (``.cmd`` on Windows, so the kill has to walk the cmd.exe → python tree, as with opencode.CMD)."""
    exe, plan_file = _shim(adapter_cls.id)
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    workdir = root / adapter_cls.id
    workdir.mkdir(exist_ok=True)
    spec = {"prompt": "do the story", "workdir": workdir, "timeout_seconds": 20, **spec}
    return adapter_cls(binary=str(exe)).run(RunSpec(**spec))


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace").stdout
        return f" {pid} " in out
    try:
        os.kill(pid, 0)  # existence probe — POSIX only; on Windows signal 0 would *terminate* the process
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True,
                        text=True, encoding="utf-8", errors="replace").stdout.strip()
    return bool(st) and not st.startswith("Z")  # a zombie waiting for init is dead


def _survivors(pids, within: float = 2.0) -> list[int]:
    end = time.monotonic() + within
    left = list(pids)
    while left and time.monotonic() < end:
        left = [p for p in left if _alive(p)]
        if left:
            time.sleep(0.05)
    return left


class _Pair(unittest.TestCase):
    """One provider condition replayed to both adapters; subclasses supply the two plans."""

    SPEC: dict = {}
    POSIX_ONLY = False

    @classmethod
    def plans(cls, root: Path) -> tuple[dict, dict]:
        raise unittest.SkipTest("abstract")

    @classmethod
    def spec(cls, root: Path) -> dict:
        return dict(cls.SPEC)

    @classmethod
    def setUpClass(cls):
        if cls.POSIX_ONLY and sys.platform == "win32":
            raise unittest.SkipTest("a writer that outlives kill_tree needs its own session (setsid) — POSIX only; "
                                    "on Windows _kill_tree_win32 walks the parent chain and reaches it")
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.root = Path(tmp.name)
        claude, opencode = cls.plans(cls.root)
        spec = cls.spec(cls.root)
        cls.claude = run_fake(ClaudeCodeAdapter, cls.root, claude, **spec)
        cls.opencode = run_fake(OpenCodeAdapter, cls.root, opencode, **spec)

    def test_cross_adapter_same_exit_status(self):
        self.assertEqual(exit_status_of(self.claude), exit_status_of(self.opencode),
                         f"claude: ok={self.claude.ok} error={self.claude.error!r} | "
                         f"opencode: ok={self.opencode.ok} error={self.opencode.error!r}")


# ------------------------------------------------------------------ conditions

VERDICT = '```json\n{"verdict": "pass", "findings": []}\n```'
REVIEW = "Review complete — every criterion has a test.\n\n" + VERDICT
PROSE = "Looks fine to me: tests are green and the scope is respected. No blockers."


class TestC01StructuredVerdict(_Pair):
    @classmethod
    def plans(cls, root):
        return ({"lines": [C_INIT, c_assistant(REVIEW), c_result(result=REVIEW, num_turns=2)]},
                {"lines": [o_text(REVIEW[:30]), o_text(REVIEW[30:]), o_step()]})

    def _check(self, res):
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.text, REVIEW)
        self.assertEqual(review_verdict(res.text).verdict, "pass")
        self.assertEqual(exit_status_of(res), "ok")

    def test_claude(self):
        self._check(self.claude)

    def test_opencode(self):
        self._check(self.opencode)


class TestC02MalformedVerdictProseOnly(_Pair):
    @classmethod
    def plans(cls, root):
        return ({"lines": [C_INIT, c_assistant(PROSE), c_result(result=PROSE)]},
                {"lines": [o_text(PROSE), o_step()]})

    def _check(self, res):
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.text, PROSE)
        self.assertIsNone(review_verdict(res.text))
        self.assertEqual((res.tool_uses, res.error), ([], ""))
        self.assertEqual(exit_status_of(res), "ok")

    def test_claude(self):
        self._check(self.claude)

    def test_opencode(self):
        self._check(self.opencode)


class TestC03EmptyResponse(_Pair):
    @classmethod
    def plans(cls, root):
        return {"lines": []}, {"lines": []}

    def _check(self, res):
        self.assertEqual(res.text, "")
        self.assertFalse(res.ok, f"an empty stream came back ok=True (turns={res.num_turns}, error={res.error!r})")
        self.assertIn(exit_status_of(res), INFRA_STATUSES)

    def test_claude(self):
        self._check(self.claude)

    # GREEN since F2 (AD-01: typed infra outcome from the adapter), 2026-09-16
    def test_opencode(self):
        self._check(self.opencode)

    # GREEN since F2 (AD-01: typed infra outcome from the adapter), 2026-09-16
    def test_cross_adapter_same_exit_status(self):
        super().test_cross_adapter_same_exit_status()


class TestC04MaxTurnsCap(_Pair):
    SPEC = {"max_turns": 2}

    @classmethod
    def plans(cls, root):
        return ({"lines": [C_INIT, c_assistant("turn 1"), c_assistant("turn 2"),
                           c_result(subtype="error_max_turns", is_error=True, terminal_reason="max_turns",
                                    num_turns=2, result="")]},
                # OpenCode has no turn flag: the adapter counts `step_finish` and kills at the cap (O-10).
                {"lines": [o_text("turn 1"), o_step(), o_text("turn 2"), o_step()], "sleep": 30})

    def _check(self, res):
        self.assertFalse(res.ok)
        self.assertEqual(exit_status_of(res), "max_turns", res.error)
        self.assertEqual(res.num_turns, 2)

    def test_claude(self):
        self._check(self.claude)

    def test_opencode(self):
        self._check(self.opencode)


class TestC05Timeout(_Pair):
    SPEC = {"timeout_seconds": 1}

    @classmethod
    def plans(cls, root):
        return ({"lines": [C_INIT], "grandchild": True, "pids": str(root / "claude.pids"), "sleep": 30},
                {"lines": [o_text("working")], "grandchild": True, "pids": str(root / "opencode.pids"), "sleep": 30})

    def _check(self, res, pids_file: Path):
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "exceeded 1s")
        self.assertEqual(exit_status_of(res), "timeout")
        pids = [int(x) for x in pids_file.read_text(encoding="utf-8").split()]
        self.assertEqual(len(pids), 2, "the fake CLI and the sleeper it spawned")
        self.assertEqual(_survivors(pids), [], "process tree not fully killed")

    def test_claude(self):
        self._check(self.claude, self.root / "claude.pids")

    def test_opencode(self):
        self._check(self.opencode, self.root / "opencode.pids")


class TestC06AuthRejected(_Pair):
    @classmethod
    def plans(cls, root):
        msg = 'API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}'
        return ({"lines": [C_INIT, c_api_error(401, msg)]},
                {"lines": [o_error("Unauthorized: invalid API key", 401)], "exit": 1})

    def _check(self, res):
        self.assertFalse(res.ok)
        self.assertEqual(exit_status_of(res), "auth", res.error)
        self.assertIn("401", res.error)

    def test_claude(self):
        self._check(self.claude)

    def test_opencode(self):
        self._check(self.opencode)


PROSE_401 = "I added the 401 Unauthorized handler for invalid API key requests and its tests."


class TestC06bProviderErrorWithAuthProse(_Pair):
    """Same provider condition on both sides — a 502 — while the session's final text talks about 401 handling.
    The status must come from the provider field (INV-F.4), never from the prose (SS-28)."""

    @classmethod
    def plans(cls, root):
        return ({"lines": [C_INIT, c_assistant(PROSE_401), c_api_error(502, PROSE_401)]},
                {"lines": [o_text(PROSE_401), o_error("Bad Gateway", 502, True)], "exit": 1})

    def _check(self, res):
        self.assertFalse(res.ok)
        self.assertEqual(exit_status_of(res), "infra", f"error={res.error!r} raw={res.raw_result}")

    # GREEN since F3 (AD-02 / SS-28: the status comes from the provider's fields, never the agent's text), 2026-09-16
    def test_claude(self):
        self._check(self.claude)

    def test_opencode(self):
        self._check(self.opencode)

    # GREEN since F3 (AD-02 / SS-28: the status comes from the provider's fields, never the agent's text), 2026-09-16
    def test_cross_adapter_same_exit_status(self):
        super().test_cross_adapter_same_exit_status()


class TestC07ContextOverflow(_Pair):
    @classmethod
    def plans(cls, root):
        too_long = "prompt is too long: 213021 tokens > 200000 maximum"
        msg = f'API Error: 400 {{"type":"error","error":{{"type":"invalid_request_error","message":"{too_long}"}}}}'
        return ({"lines": [C_INIT, c_api_error(400, msg)]},
                {"lines": [o_error(too_long, 400)], "exit": 1})

    def _check(self, res):
        self.assertFalse(res.ok)
        self.assertEqual(exit_status_of(res), "context", res.error)

    def test_claude(self):
        self._check(self.claude)

    def test_opencode(self):
        self._check(self.opencode)


class TestC08RateLimit(_Pair):
    @classmethod
    def plans(cls, root):
        msg = ('API Error: 429 {"type":"error","error":{"type":"rate_limit_error",'
               '"message":"Too many requests. Retry after 30 seconds."}}')
        return ({"lines": [C_INIT, c_api_error(429, msg)]},
                {"lines": [o_error("Rate limit exceeded. Retry after 30 seconds.", 429, True)], "exit": 1})

    def _check(self, res):
        self.assertFalse(res.ok)
        self.assertEqual(exit_status_of(res), "rate_limit", res.error)
        self.assertEqual(retry_delay_seconds(res), 30.0, res.error)

    def test_claude(self):
        self._check(self.claude)

    def test_opencode(self):
        self._check(self.opencode)


class TestC09BudgetCap(_Pair):
    """OpenCode has no cost cap (no `--max-budget-usd`, no budget event), so the closest representable condition
    is a provider/router error that names the budget; Claude's is the CLI's own `error_max_budget_usd`."""

    @classmethod
    def plans(cls, root):
        return ({"lines": [C_INIT, c_result(subtype="error_max_budget_usd", is_error=True,
                                            terminal_reason="max_budget_usd", total_cost_usd=5.02, num_turns=7,
                                            result="")]},
                {"lines": [o_step(cost=5.02), o_error("Budget exceeded: max_cost 5.00 USD reached for this key", 402)],
                 "exit": 1})

    def _check(self, res):
        self.assertFalse(res.ok)
        self.assertEqual(exit_status_of(res), "cost", res.error)
        self.assertAlmostEqual(res.cost_usd, 5.02, places=3)

    def test_claude(self):
        self._check(self.claude)

    def test_opencode(self):
        self._check(self.opencode)


class TestC10ProviderError5xx(_Pair):
    @classmethod
    def plans(cls, root):
        msg = 'API Error: 502 {"type":"error","error":{"type":"api_error","message":"Bad Gateway"}}'
        return ({"lines": [C_INIT, c_api_error(502, msg)]},
                {"lines": [o_error("Bad Gateway", 502, True)], "exit": 1})

    def _check(self, res):
        self.assertFalse(res.ok)
        self.assertEqual(exit_status_of(res), "infra", res.error)

    def test_claude(self):
        self._check(self.claude)

    def test_opencode(self):
        self._check(self.opencode)


class TestC11PartialStream(_Pair):
    """The child dies mid-JSON line (exit 1, no newline). `run()` must return — an exception here would surface as
    an error in `setUpClass` — with ok=False and a status from the closed set."""

    @classmethod
    def plans(cls, root):
        return ({"lines": [C_INIT, c_assistant("half way")], "trailing": '{"type":"result","subtype":"succ', "exit": 1},
                {"lines": [o_text("half way"), o_step()], "trailing": '{"type":"step_fin', "exit": 1})

    def _check(self, res):
        self.assertFalse(res.ok)
        self.assertTrue(res.error)
        self.assertIn(exit_status_of(res), EXIT_STATUSES)
        self.assertIn(exit_status_of(res), INFRA_STATUSES, f"a child dying mid-line is infra, got error={res.error!r}")

    def test_claude(self):
        self._check(self.claude)

    # GREEN since F2 (AD-03: typed infra outcome from the adapter), 2026-09-16
    def test_opencode(self):
        self._check(self.opencode)

    # GREEN since F2 (AD-03: typed infra outcome from the adapter), 2026-09-16
    def test_cross_adapter_same_exit_status(self):
        super().test_cross_adapter_same_exit_status()


class TestC12ProcessDeath(_Pair):
    @classmethod
    def plans(cls, root):
        stderr = "FATAL ERROR: Reached heap limit — JavaScript heap out of memory\n"
        return ({"lines": [C_INIT], "stderr": stderr, "exit": 3},
                {"lines": [o_text("starting")], "stderr": stderr, "exit": 3})

    def _check(self, res):
        self.assertFalse(res.ok)
        self.assertNotEqual(exit_status_of(res), "ok")
        self.assertTrue("3" in res.error or res.raw_result.get("returncode") == 3,
                        f"exit code not recorded: error={res.error!r} raw={res.raw_result}")
        self.assertIn(exit_status_of(res), INFRA_STATUSES, f"a dead child is infra, got error={res.error!r}")

    # GREEN since F2 (AD-04: exit code and stderr recorded when no result event), 2026-09-16
    def test_claude(self):
        self._check(self.claude)

    # GREEN since F2 (AD-03: typed infra outcome from the adapter), 2026-09-16
    def test_opencode(self):
        self._check(self.opencode)

    # GREEN since F2 (AD-03: typed infra outcome from the adapter), 2026-09-16
    def test_cross_adapter_same_exit_status(self):
        super().test_cross_adapter_same_exit_status()


class TestC13LateOutputAfterTimeout(_Pair):
    """A writer holding the stdout pipe outlives the kill (D-027's shape: the shim died, node kept the pipes)
    and prints a complete, successful event *after* the adapter decided `timeout`."""

    POSIX_ONLY = True
    SPEC = {"timeout_seconds": 1}

    @classmethod
    def plans(cls, root):
        return ({"lines": [C_INIT], "survivor": c_result(result="late verdict"), "sleep": 30},
                {"lines": [o_text("working")], "survivor": o_text(" late verdict"), "sleep": 30})

    def _check(self, res, arrived: bool):
        self.assertTrue(arrived, "precondition: the late line never reached the reader — scenario not exercised")
        self.assertFalse(res.ok, f"late output turned a timed-out session into ok=True (error={res.error!r})")
        self.assertEqual(exit_status_of(res), "timeout")
        self.assertEqual(res.error, "exceeded 1s")

    # GREEN since F2 (AD-05: typed infra outcome from the adapter), 2026-09-16
    def test_claude(self):
        self._check(self.claude, self.claude.raw_result.get("result") == "late verdict")

    def test_opencode(self):
        self._check(self.opencode, "late verdict" in self.opencode.text)

    # GREEN since F2 (AD-05: typed infra outcome from the adapter), 2026-09-16
    def test_cross_adapter_same_exit_status(self):
        super().test_cross_adapter_same_exit_status()


class TestC14GuardStamping(_Pair):
    """What `implement.py` puts in `RunSpec.env` for the guard hooks must reach the child exactly as
    `aisef/harness/guardrails.py`'s readers expect it; Claude also carries `--settings`/`--session-id` on argv.
    OpenCode has no session-id flag — its session id is whatever the stream's `sessionID` says."""

    STAMP = {g.ENV_WRITE_SCOPE: "src/a.py,src/b.py", g.ENV_STORY_ID: "STORY-01-01", g.ENV_BASE_REF: "abc1234",
             g.ENV_ALLOW_HOSTS: "pypi.org"}

    @classmethod
    def spec(cls, root):
        wt = root / "wt"
        wt.mkdir()
        (root / "settings.json").write_text("{}", encoding="utf-8")
        return {"workdir": wt, "settings_file": root / "settings.json", "session_id": SID,
                "env": {**cls.STAMP, g.ENV_WORKDIR: str(wt), g.ENV_PROJECT: str(root)}}

    @classmethod
    def plans(cls, root):
        return ({"lines": [C_INIT, c_result()], "dump": str(root / "claude.dump.json")},
                {"lines": [o_text("OK"), o_step()], "dump": str(root / "opencode.dump.json")})

    def _dump(self, name: str) -> dict:
        return json.loads((self.root / f"{name}.dump.json").read_text(encoding="utf-8"))

    def _check(self, res, dump: dict):
        env = dump["env"]
        self.assertTrue(res.ok, res.error)
        self.assertEqual(dump["prompt"], "do the story")
        self.assertEqual(g.scope_from_env(env), ["src/a.py", "src/b.py"])
        self.assertEqual(g.story_from_env(env), "STORY-01-01")
        self.assertEqual(g.base_from_env(env), "abc1234")
        self.assertEqual(g.workdir_from_env(env), str(self.root / "wt"))
        self.assertEqual(g.project_root_from(env, ""), str(self.root))
        self.assertEqual(g.allow_hosts_from_env(env), ["pypi.org"])

    def test_claude(self):
        dump = self._dump("claude")
        self._check(self.claude, dump)
        argv = dump["argv"]
        self.assertEqual(argv[argv.index("--settings") + 1], str(self.root / "settings.json"))
        self.assertEqual(argv[argv.index("--session-id") + 1], SID)
        self.assertEqual(self.claude.session_id, SID)

    def test_opencode(self):
        dump = self._dump("opencode")
        self._check(self.opencode, dump)
        argv = dump["argv"]
        self.assertEqual(argv[argv.index("--dir") + 1], str(self.root / "wt"))
        self.assertEqual(self.opencode.session_id, OSID)


if __name__ == "__main__":
    unittest.main(verbosity=2)
