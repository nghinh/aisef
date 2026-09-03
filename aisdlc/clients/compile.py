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
        for p in self.written:
            lines.append(f"  ghi {p}")
        if self.guards_wired:
            lines.append(f"  guard tiền kiểm: {', '.join(self.guards_wired)}")
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
    """
    kinds = ", ".join(f'"{k}"' for k in sorted(GUARD_MATCHERS))
    return f"""// {GENERATED_NOTE}
import type {{ Plugin }} from "@opencode-ai/plugin"

const GUARDS = [{kinds}]
const BIN = {json.dumps(aisdlc_bin)}
const PROJECT = {json.dumps(str(project))}

export const AisdlcGuardPlugin: Plugin = async ({{ $ }}) => ({{
  "tool.execute.before": async (input, output) => {{
    const event = JSON.stringify({{
      tool_name: input?.tool,
      tool_input: output?.args ?? {{}},
    }})
    for (const kind of GUARDS) {{
      const res = await $`${{BIN}} --project ${{PROJECT}} guard ${{kind}}`
        .stdin(event).quiet().nothrow()
      if (res.exitCode === 2) {{
        throw new Error(String(res.stderr).trim() || `guard ${{kind}} đã chặn thao tác này`)
      }}
    }}
  }},
}})
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
