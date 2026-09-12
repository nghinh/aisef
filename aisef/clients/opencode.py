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

import os
import re
import subprocess
import time
from pathlib import Path

from .base import Capability, ClientAdapter, RunSpec, Support, _stream_with_timeout, child_env, resolve_binary
from .stream import RunResult

BINARY = "opencode"


_TOOL_NAMES = {"read": "Read", "write": "Write", "edit": "Edit", "bash": "Bash", "glob": "Glob",
               "grep": "Grep", "list": "LS", "webfetch": "WebFetch", "todowrite": "TodoWrite", "skill": "Skill"}


#: Nơi OpenCode khai model mặc định. Chỉ đọc **đúng một khoá** ``model``: tệp
#: này cũng chứa khoá API của nhà cung cấp, và một hàm tiện tay đọc cả tệp rồi
#: in ra là cách rò bí mật kinh điển.
_CONFIG_PATHS = (
    "opencode.json",
    ".opencode/opencode.json",
)


def configured_model(workdir) -> str:
    """Model OpenCode sẽ dùng khi không ai truyền ``--model``.

    Luồng JSON của OpenCode **không nói** model nào đã trả lời (đo 2026-09-12:
    không sự kiện nào mang ``modelID``/``providerID``), nên đây là *model được
    yêu cầu*, không phải model đã đáp. Với một alias định tuyến như
    ``9router/mycombo`` — đổi mô hình nền theo từng lần gọi — ghi lại lời khai
    này là điều duy nhất làm được, và bản báo cáo phải nói rõ nó là lời khai.
    """
    import json as _json
    from pathlib import Path as _Path

    ung_vien = [_Path(workdir) / p for p in _CONFIG_PATHS]
    home = os.environ.get("XDG_CONFIG_HOME") or str(_Path.home() / ".config")
    ung_vien.append(_Path(home) / "opencode" / "opencode.json")
    for path in ung_vien:
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        model = data.get("model")
        if isinstance(model, str) and model:
            return model
    return ""


#: Cú pháp gọi công cụ mà CLI **không** phân giải được. Model in nó ra như văn
#: bản thường, OpenCode coi đó là câu trả lời cuối, bước kết thúc `reason=stop`
#: và phiên dừng tại chỗ. Đo trên cohort C-1 (12/09): 20/20 phiên mang chữ ký
#: này đều chết ngay ở đó, và 7/8 lượt trượt của cả hai nhánh là kiểu hỏng ấy
#: (`docs/BENCH-OBSERVATIONS-C1.md` § O-7).
_CU_PHAP_KHONG_PHAN_GIAI = re.compile(r"<\w+:tool_call>|<invoke name=")


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
    if texts and not res.error and _CU_PHAP_KHONG_PHAN_GIAI.search(texts[-1]):
        # Không phải agent làm sai: model định gọi công cụ, CLI không hiểu cú
        # pháp, phiên chết. Xếp vào nhóm hạ tầng để lượt sau được thử lại —
        # nếu không, một lỗi tích hợp model↔CLI sẽ bị tính là "agent trượt".
        res.error = ("client could not parse the model's tool call; the session ended there "
                     "(unparsed tool-call syntax in the final message)")
        res.raw_result = {**(res.raw_result or {}), "retryable": True}
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
        # Built in order, never by index: `resolve_binary` returns **three**
        # tokens on Windows (`cmd.exe /c <shim>.cmd`), so `insert(2, …)` put
        # `--format json` among cmd.exe's own arguments and the client was
        # launched as `cmd /c --format json opencode.cmd run …`. Bug 32's
        # shape again — a command is not a word.
        cmd = [*(resolve_binary(self.binary) or [self.binary]),
               "run", "--format", "json", "--dir", str(spec.workdir)]
        if spec.model:
            cmd += ["--model", spec.model]
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

        import threading as _t
        def _feed_stdin(proc=proc, prompt=spec.prompt):
            try:
                if proc.stdin:
                    proc.stdin.write(prompt)
                    proc.stdin.close()
            except (BrokenPipeError, ValueError):
                pass
        _t.Thread(target=_feed_stdin, daemon=True).start()

        # OpenCode CLI không có cờ giới hạn lượt (`claude_code` có `--max-turns`),
        # nên trần phải do adapter thi hành: đếm `step_finish` trên luồng và dừng
        # tiến trình khi chạm. Không làm thì `run.max_turns` là con số không ai
        # đọc — đo được: khai 40, phiên chạy 61 lượt (O-10).
        cham_tran = False

        def _dem_luot(moi: list[str], _tran=int(spec.max_turns or 0)) -> bool:
            nonlocal cham_tran, luot
            luot += sum(1 for d in moi if '"type":"step_finish"' in d
                        or '"type": "step_finish"' in d)
            cham_tran = luot >= _tran
            return cham_tran

        luot = 0
        lines, stderr, timed_out = _stream_with_timeout(
            proc, timeout_seconds=spec.timeout_seconds,
            stop_when=_dem_luot if spec.max_turns else None)

        # `--format json` (measured 2026-09-05, OpenCode 1.18.26): one event per
        # line — `step_start` / `text` / `tool_use` (part.tool, state.input/output)
        # / `step_finish` (tokens, cost). Cost is the provider-reported number —
        # 9router reports 0, that is the provider's truth, not the harness's.
        res = parse_json_events(lines)
        res.ok = proc.returncode == 0 and not timed_out and not cham_tran
        res.duration_ms = int((time.monotonic() - started) * 1000)
        if cham_tran:
            # Tên trạng thái phải là `max_turns`, không phải `timeout`: hai thứ
            # ấy dẫn tới hai quyết định khác nhau ở tầng trên.
            res.error = f"max_turns: stopped at {res.num_turns or luot} turns (cap {spec.max_turns})"
        elif timed_out:
            res.error = f"exceeded {spec.timeout_seconds}s"
        elif proc.returncode != 0:
            # Keep what the stream already explained; stderr is empty here.
            res.error = res.error or stderr.strip()[:500] or "exit != 0"
        res.raw_result = {"returncode": proc.returncode, **res.raw_result}
        # Lời khai, không phải quan sát: luồng của OpenCode không mang tên
        # model. Ghi cái đã yêu cầu còn hơn để trống, miễn là nói rõ.
        res.model = spec.model or configured_model(spec.workdir)
        return res
