"""``aisef dashboard`` — báo cáo hợp quy dạng HTML từ bằng chứng.

Đọc toàn bộ evidence JSONL, tính thống kê guard / gate / chi phí,
xuất một file HTML tự chứa xem được offline.
"""

from __future__ import annotations

import html
import json
import time
from pathlib import Path

from ..harness.observe import (
    AGENT_RUN,
    BEHAVIOR,
    EvidenceStore,
    Evidence,
    GUARD_BLOCK,
    GUARD_CHECK,
    GUARD_SEEN,
    NOTE,
    TOOL_RUN,
)
from ._common import EXIT_NOT_READY, EXIT_OK, _artifact_root


def _guard_stats(evidences: list[Evidence]) -> dict:
    """Thống kê guard từ GUARD_CHECK events."""
    by_kind: dict[str, dict] = {}
    for ev in evidences:
        for e in ev.of(GUARD_CHECK):
            k = e.name
            if k not in by_kind:
                by_kind[k] = {"total": 0, "allow": 0, "block": 0,
                              "total_ms": 0, "max_ms": 0}
            s = by_kind[k]
            s["total"] += 1
            if e.ok:
                s["allow"] += 1
            else:
                s["block"] += 1
            s["total_ms"] += e.duration_ms
            s["max_ms"] = max(s["max_ms"], e.duration_ms)
    for s in by_kind.values():
        s["avg_ms"] = s["total_ms"] // s["total"] if s["total"] else 0
    return by_kind


def _gate_verdicts(evidences: list[Evidence]) -> list[dict]:
    """Trích gate:verdict từ bằng chứng."""
    rows = []
    for ev in evidences:
        for e in ev.of(NOTE, "gate:verdict"):
            fails = e.detail.get("failures") or []
            rows.append({
                "story": ev.story_id,
                "attempt": e.detail.get("attempt", "?"),
                "passed": len(fails) == 0,
                "failures": fails,
                "candidate": str(e.detail.get("candidate") or "")[:7],
                "seq": e.seq,
            })
    return rows


def _story_summary(evidences: list[Evidence]) -> list[dict]:
    rows = []
    for ev in evidences:
        checks = len(ev.of(GUARD_CHECK))
        blocks = len(ev.of(GUARD_BLOCK))
        tests = ev.of(TOOL_RUN, "test")
        test_pass = sum(1 for t in tests if t.ok)
        cost = ev.total_cost_usd
        dur = ev.total_duration_ms
        rows.append({
            "story": ev.story_id,
            "guard_checks": checks,
            "guard_blocks": blocks,
            "test_runs": len(tests),
            "test_pass": test_pass,
            "cost_usd": cost,
            "duration_s": dur // 1000,
            "events": len(ev.events),
        })
    return rows


def _esc(s) -> str:
    return html.escape(str(s))


def generate_html(evidences: list[Evidence], *, project: str = "",
                   extra_sections: str = "") -> str:
    guard = _guard_stats(evidences)
    gates = _gate_verdicts(evidences)
    stories = _story_summary(evidences)

    total_checks = sum(s["total"] for s in guard.values())
    total_blocks = sum(s["block"] for s in guard.values())
    total_cost = sum(s["cost_usd"] for s in stories)
    gate_pass = sum(1 for g in gates if g["passed"])

    now = time.strftime("%Y-%m-%d %H:%M:%S")

    guard_rows = ""
    for k in sorted(guard):
        s = guard[k]
        rate = f'{s["allow"] / s["total"] * 100:.0f}%' if s["total"] else "—"
        guard_rows += (
            f'<tr><td>{_esc(k)}</td><td>{s["total"]}</td><td>{s["allow"]}</td>'
            f'<td class="block">{s["block"]}</td><td>{rate}</td>'
            f'<td>{s["avg_ms"]}</td><td>{s["max_ms"]}</td></tr>\n'
        )

    gate_rows = ""
    for g in gates:
        cls = "pass" if g["passed"] else "fail"
        fails = ", ".join(str(f) for f in g["failures"]) if g["failures"] else "—"
        gate_rows += (
            f'<tr class="{cls}"><td>{_esc(g["story"])}</td><td>{g["attempt"]}</td>'
            f'<td>{_esc(g["candidate"])}</td>'
            f'<td>{"DAT" if g["passed"] else "KHONG DAT"}</td>'
            f'<td>{_esc(fails)}</td></tr>\n'
        )

    story_rows = ""
    for s in stories:
        story_rows += (
            f'<tr><td>{_esc(s["story"])}</td><td>{s["events"]}</td>'
            f'<td>{s["guard_checks"]}</td><td>{s["guard_blocks"]}</td>'
            f'<td>{s["test_runs"]}</td><td>{s["test_pass"]}</td>'
            f'<td>${s["cost_usd"]:.2f}</td><td>{s["duration_s"]}s</td></tr>\n'
        )

    # ponytail: inline CSS, no external deps
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AISEF Dashboard — {_esc(project)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #fafafa; color: #1a1a1a; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  .meta {{ color: #666; font-size: 0.85rem; margin-bottom: 2rem; }}
  .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 2rem; }}
  .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
           padding: 1rem 1.5rem; min-width: 140px; }}
  .card .num {{ font-size: 2rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .card .label {{ font-size: 0.8rem; color: #666; text-transform: uppercase;
                  letter-spacing: 0.05em; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; font-size: 0.9rem; }}
  th {{ text-align: left; padding: 0.5rem; border-bottom: 2px solid #333;
       font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  td {{ padding: 0.5rem; border-bottom: 1px solid #e8e8e8;
       font-variant-numeric: tabular-nums; }}
  tr:hover {{ background: #f5f5f5; }}
  .block {{ color: #c62828; font-weight: 600; }}
  .pass td:nth-child(4) {{ color: #2e7d32; }}
  .fail td:nth-child(4) {{ color: #c62828; font-weight: 600; }}
  h2 {{ font-size: 1.1rem; margin: 2rem 0 0.5rem; border-bottom: 1px solid #ddd;
       padding-bottom: 0.25rem; }}
  .empty {{ color: #999; font-style: italic; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #1a1a1a; color: #e0e0e0; }}
    .card {{ background: #2a2a2a; border-color: #444; }}
    .card .label {{ color: #aaa; }}
    .meta {{ color: #999; }}
    th {{ border-bottom-color: #888; }}
    td {{ border-bottom-color: #333; }}
    tr:hover {{ background: #2a2a2a; }}
    h2 {{ border-bottom-color: #444; }}
  }}
</style>
</head>
<body>
<h1>AISEF Conformance Dashboard</h1>
<p class="meta">{_esc(project)} &middot; {now}</p>

<div class="cards">
  <div class="card"><div class="num">{len(evidences)}</div><div class="label">Stories</div></div>
  <div class="card"><div class="num">{total_checks}</div><div class="label">Guard checks</div></div>
  <div class="card"><div class="num">{total_blocks}</div><div class="label">Blocks</div></div>
  <div class="card"><div class="num">{gate_pass}/{len(gates)}</div><div class="label">Gates passed</div></div>
  <div class="card"><div class="num">${total_cost:.2f}</div><div class="label">Total cost</div></div>
</div>

{extra_sections}

<h2>Guard telemetry</h2>
{"<p class='empty'>No guard telemetry data (GUARD_CHECK events). Run stories with v0.4.0+ to collect.</p>" if not guard_rows else f'''
<table>
<tr><th>Guard</th><th>Total</th><th>Allow</th><th>Block</th><th>Pass rate</th><th>Avg ms</th><th>Max ms</th></tr>
{guard_rows}</table>'''}

<h2>Gate verdicts</h2>
{"<p class='empty'>No gate verdicts recorded.</p>" if not gate_rows else f'''
<table>
<tr><th>Story</th><th>Attempt</th><th>Candidate</th><th>Verdict</th><th>Failures</th></tr>
{gate_rows}</table>'''}

<h2>Story summary</h2>
{"<p class='empty'>No stories found.</p>" if not story_rows else f'''
<table>
<tr><th>Story</th><th>Events</th><th>Guard checks</th><th>Blocks</th>
<th>Test runs</th><th>Tests OK</th><th>Cost</th><th>Duration</th></tr>
{story_rows}</table>'''}

<footer style="margin-top:3rem;color:#999;font-size:0.75rem;">
  Generated by <code>aisef dashboard</code> v0.4.0
</footer>
</body>
</html>"""


def _collect_projects(args) -> list[tuple[str, list[Evidence]]]:
    """Thu thập bằng chứng từ dự án chính và các dự án bổ sung."""
    groups: list[tuple[str, list[Evidence]]] = []
    root = _artifact_root(args)
    store = EvidenceStore(root)
    ids = store.stories()
    if ids:
        evidences = [store.read(sid) for sid in ids]
        groups.append((Path(args.project).resolve().name, evidences))
    for p in getattr(args, "projects", None) or []:
        pp = Path(p).resolve()
        pr = pp / "_bmad-output"
        if not pr.is_dir():
            continue
        st = EvidenceStore(pr)
        sids = st.stories()
        if sids:
            groups.append((pp.name, [st.read(sid) for sid in sids]))
    return groups


def _project_summary(groups: list[tuple[str, list[Evidence]]]) -> str:
    """Bảng tổng hợp nhiều dự án."""
    if len(groups) <= 1:
        return ""
    rows = []
    for name, evs in groups:
        stories = len(evs)
        cost = sum(e.total_cost_usd for e in evs)
        blocks = sum(len(e.of(GUARD_BLOCK)) for e in evs)
        checks = sum(len(e.of(GUARD_CHECK)) for e in evs)
        rows.append(f"<tr><td>{_esc(name)}</td><td>{stories}</td>"
                    f"<td>${cost:.2f}</td><td>{checks}</td><td>{blocks}</td></tr>")
    return (
        "<h2>Tổng hợp dự án</h2>"
        "<table><tr><th>Dự án</th><th>Story</th><th>Chi phí</th>"
        "<th>Guard check</th><th>Guard block</th></tr>"
        + "\n".join(rows) + "</table>"
    )


def cmd_dashboard(args) -> int:
    groups = _collect_projects(args)
    if not groups:
        print("✗ không có bằng chứng nào — chạy `aisef run` trước", file=__import__("sys").stderr)
        return EXIT_NOT_READY

    all_evidences = [e for _, evs in groups for e in evs]
    multi_summary = _project_summary(groups)
    project_label = ", ".join(name for name, _ in groups) if len(groups) > 1 else groups[0][0]
    content = generate_html(all_evidences, project=project_label,
                            extra_sections=multi_summary)

    root = _artifact_root(args)
    out = Path(args.out) if getattr(args, "out", "") else root / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"dashboard: {out}")
    return EXIT_OK
