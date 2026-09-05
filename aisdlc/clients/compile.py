"""Biên dịch cấu hình client từ một nguồn duy nhất.

Framework mô tả guard **một lần** (`harness/guardrails.GUARD_MATCHERS`),
rồi sinh ra cấu hình cho từng client. Không duy trì ba bản `settings.json`
viết tay dễ lệch nhau — đó là quyết định Đ3.

Kết quả biên dịch là **artifact sinh ra**, không sửa tay: mỗi file mang
dòng đầu nói rõ điều đó, và lần chạy sau sẽ ghi đè.

Điều quan trọng nhất ở đây không phải sinh file, mà là **báo cáo mất mát**.
Client nào không gắn được guard tiền kiểm thì compile phải nói ra, để
người vận hành biết mức bảo đảm thật của mình — thay vì tưởng đã được bảo
vệ (bất biến 10).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..harness.guardrails import GUARD_MATCHERS
from .base import Capability, ClientAdapter, Support
from .claude_code import ClaudeCodeAdapter
from .opencode import OpenCodeAdapter

GENERATED_NOTE = "Sinh bởi `aisdlc compile` — không sửa tay, lần chạy sau sẽ ghi đè."

ADAPTERS: dict[str, type[ClientAdapter]] = {
    "claude": ClaudeCodeAdapter,
    "opencode": OpenCodeAdapter,
}


@dataclass
class CompileReport:
    client: str
    written: list[Path] = field(default_factory=list)
    guards_wired: list[str] = field(default_factory=list)
    #: Guard phải kiểm sau thay vì chặn ngay — mức bảo đảm thấp hơn.
    guards_post_hoc: list[str] = field(default_factory=list)
    degradations: list[str] = field(default_factory=list)

    @property
    def blocks_at_source(self) -> bool:
        return not self.guards_post_hoc

    def summary(self) -> str:
        lines = [f"client: {self.client}"]
        if self.client == "opencode":
            # Quyết định 2026-09-05: hạng hai trong V1. Guard chặn được (đã
            # chứng minh), nhưng chi phí và số lượt không đo được từ harness.
            lines.append(
                "  hạng hai V1: chi phí/lượt không đo được từ harness — "
                "được hỗ trợ, không chặn phát hành"
            )
        for p in self.written:
            lines.append(f"  ghi {p}")
        if self.guards_wired:
            # Không gọi hết là "tiền kiểm": `diff-scope` chạy sau mỗi thao
            # tác và `completion` chạy lúc agent định dừng. Gộp chung sẽ báo
            # sai mức bảo đảm mà client thật sự cho.
            pre = [g for g in self.guards_wired if GUARD_MATCHERS[g][0] == "PreToolUse"]
            after = [g for g in self.guards_wired if g not in pre]
            if pre:
                lines.append(f"  guard chặn trước thao tác: {', '.join(pre)}")
            if after:
                moments = ", ".join(f"{g} ({GUARD_MATCHERS[g][0]})" for g in after)
                lines.append(f"  guard chặn tại mốc khác: {moments}")
        if self.guards_post_hoc:
            lines.append(f"  ⚠️  guard chỉ hậu kiểm: {', '.join(self.guards_post_hoc)}")
            lines.append("     — chặn không xảy ra lúc ghi; `aisdlc verify` kiểm lại sau")
        if self.degradations:
            lines.append("  năng lực không đạt mức native:")
            for d in self.degradations:
                lines.append(f"     {d}")
        return "\n".join(lines)


def _guard_command(aisdlc_bin: str, project: Path, kind: str) -> str:
    return f"{aisdlc_bin} --project {project} guard {kind}"


def build_claude_settings(project: Path, aisdlc_bin: str) -> dict:
    """Dựng `.claude/settings.json` gắn mọi guard vào đúng mốc."""
    by_event: dict[str, list[dict]] = {}
    for kind, (event, matcher) in sorted(GUARD_MATCHERS.items()):
        by_event.setdefault(event, []).append(
            {
                "matcher": matcher,
                "hooks": [
                    {"type": "command", "command": _guard_command(aisdlc_bin, project, kind)}
                ],
            }
        )
    return {"_generated": GENERATED_NOTE, "hooks": by_event}


def build_opencode_plugin(project: Path, aisdlc_bin: str) -> str:
    """Dựng plugin OpenCode gọi cùng bộ guard.

    Spike S4 chưa chứng minh được việc ném lỗi ở đây có **chặn** tool hay
    chỉ ghi log, nên plugin vẫn được sinh nhưng năng lực khai là hậu kiểm.

    Guard được chia theo mốc, không đổ hết vào một chỗ. `completion` hỏi
    "test đã xanh cho đoạn code hiện tại chưa" — hỏi câu đó trước **mỗi**
    thao tác thì nó chặn cả lần chạy test đầu tiên, và một guard chặn mọi
    thứ sẽ bị gỡ ngay trong ngày. Nó thuộc về `aisdlc verify`.
    """
    pre = [k for k, (event, _) in sorted(GUARD_MATCHERS.items()) if event == "PreToolUse"]
    post = [k for k, (event, _) in sorted(GUARD_MATCHERS.items()) if event == "PostToolUse"]
    # Claude Code lọc tool bằng chính chuỗi này trong `settings.json`;
    # OpenCode không có cơ chế tương đương nên plugin phải tự lọc. Bỏ bước
    # này thì mọi guard chạy trên mọi tool: `write-scope` sẽ chấm cả `glob`
    # (tham số `path: "."`) rồi chặn thao tác **chỉ đọc**, và agent kẹt.
    #
    # Khớp không phân biệt hoa thường, có neo hai đầu: tên tool của
    # OpenCode viết thường (`write`, `edit`, `bash`), và không neo thì
    # `todowrite` cũng dính vào `Write`.
    matchers = "{ " + ", ".join(
        f'"{k}": /^({m})$/i' for k, (_, m) in sorted(GUARD_MATCHERS.items()) if m
    ) + " }"
    return f"""// {GENERATED_NOTE}
import type {{ Plugin }} from "@opencode-ai/plugin"

const BEFORE = [{", ".join(f'"{k}"' for k in pre)}]
const AFTER = [{", ".join(f'"{k}"' for k in post)}]
const MATCH = {matchers}
const BIN = {json.dumps(aisdlc_bin)}
const PROJECT = {json.dumps(str(project))}

// Shell của OpenCode là Bun shell: nó **không** có `.stdin(...)`, chỉ nhận
// đầu vào bằng cách chuyển hướng từ một giá trị nội suy. Gọi sai thì mọi
// lần gọi tool đều ném TypeError — trông như guard chặn, thật ra là guard
// chưa từng chạy.
async function guard($, kinds, tool, event) {{
  const input = new Blob([event])
  for (const kind of kinds) {{
    if (!MATCH[kind]?.test(tool ?? "")) continue
    const res = await $`${{BIN}} --project ${{PROJECT}} guard ${{kind}} < ${{input}}`
      .quiet().nothrow()
    if (res.exitCode === 2) {{
      throw new Error(String(res.stderr).trim() || `guard ${{kind}} đã chặn thao tác này`)
    }}
  }}
}}

// `worktree` là cây agent đang thật sự đứng — khi chạy story nó là
// .aisdlc/worktrees/<story>, không phải PROJECT. Guard soi nhầm cây thì
// nó thấy toàn bộ file kế hoạch là "thay đổi ngoài phạm vi" và chặn sạch.
export const AisdlcGuardPlugin: Plugin = async ({{ $, directory, worktree }}) => {{
  // `directory` là cwd của phiên — tương ứng đúng với `cwd` mà hook của
  // Claude Code gửi. `worktree` là gốc cây git, chỉ dùng khi thiếu.
  const CWD = directory || worktree || PROJECT
  return {{
    "tool.execute.before": async (input, output) => {{
      await guard($, BEFORE, input?.tool, JSON.stringify({{
        cwd: CWD,
        tool_name: input?.tool,
        tool_input: output?.args ?? {{}},
      }}))
    }},
    "tool.execute.after": async (input, output) => {{
      await guard($, AFTER, input?.tool, JSON.stringify({{
        cwd: CWD, tool_name: input?.tool, tool_input: {{}},
      }}))
    }},
  }}
}}
"""


def compile_for(
    client: str,
    project: Path | str,
    *,
    aisdlc_bin: str = "aisdlc",
) -> CompileReport:
    """Sinh cấu hình của một client, kèm báo cáo mất mát."""
    if client not in ADAPTERS:
        raise ValueError(f"client không hỗ trợ: {client}. Có: {', '.join(sorted(ADAPTERS))}")

    project = Path(project).resolve()
    adapter = ADAPTERS[client]()
    report = CompileReport(client=client, degradations=adapter.degradations())

    blocks = adapter.supports(Capability.PRE_TOOL_GUARD).blocks_at_source
    target = report.guards_wired if blocks else report.guards_post_hoc
    target.extend(sorted(GUARD_MATCHERS))

    if client == "claude":
        path = project / ".claude" / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(build_claude_settings(project, aisdlc_bin), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        report.written.append(path)

    elif client == "opencode":
        path = project / ".opencode" / "plugin" / "aisdlc-guard.ts"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_opencode_plugin(project, aisdlc_bin), encoding="utf-8")
        report.written.append(path)

    return report


def write_compile_report(project: Path | str, reports: list[CompileReport]) -> Path:
    """Ghi báo cáo biên dịch — nguồn tra cứu mức bảo đảm thật của dự án."""
    project = Path(project)
    path = project / "_bmad-output" / "compile-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "clients": [
            {
                "client": r.client,
                "written": [str(p.relative_to(project.resolve())) for p in r.written],
                "guards_wired": r.guards_wired,
                "guards_post_hoc": r.guards_post_hoc,
                "blocks_at_source": r.blocks_at_source,
                "degradations": r.degradations,
            }
            for r in reports
        ]
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def guard_expected(project: Path | str, client_id: str) -> bool:
    """Dự án này có **kỳ vọng** guard chạy trong phiên của client này không.

    Câu trả lời nằm trong `compile-report.json`: client đã được biên dịch
    hook và khai `blocks_at_source` thì mỗi phiên developer phải để lại ít
    nhất một dấu vết guard. Chưa biên dịch thì không kỳ vọng — và cổng
    nói "chưa biên dịch", không giả vờ đã kiểm.
    """
    path = Path(project) / "_bmad-output" / "compile-report.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    for c in data.get("clients", []):
        if c.get("client") == client_id:
            return bool(c.get("blocks_at_source"))
    return False
