"""``aisef dashboard`` — HTML conformance report from evidence.

Reads all evidence JSONL, computes guard / gate / cost statistics,
and outputs a self-contained HTML file viewable offline.
"""

from __future__ import annotations

import html
import time
from pathlib import Path

from ..harness.observe import (
    AGENT_RUN,
    EvidenceStore,
    Evidence,
    GUARD_BLOCK,
    GUARD_CHECK,
    NOTE,
    TOOL_RUN,
)
from ._common import EXIT_NOT_READY, EXIT_OK, _artifact_root


def _guard_stats(evidences: list[Evidence]) -> dict:
    """Guard statistics from GUARD_CHECK events."""
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
    """Extract gate:verdict from evidence."""
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


def _role_cost(evidences: list[Evidence]) -> dict[str, dict]:
    """Cost by role and model from AGENT_RUN events."""
    by_role: dict[str, dict] = {}
    for ev in evidences:
        for e in ev.of(AGENT_RUN):
            role = e.detail.get("role") or "unknown"
            model = e.detail.get("model") or "default"
            if role not in by_role:
                by_role[role] = {"runs": 0, "cost": 0.0, "models": {}}
            s = by_role[role]
            s["runs"] += 1
            s["cost"] += e.cost_usd
            s["models"][model] = s["models"].get(model, 0.0) + e.cost_usd
    return by_role


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
    roles = _role_cost(evidences)

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
            f'<td>{"PASS" if g["passed"] else "FAIL"}</td>'
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

    role_rows = ""
    for r in sorted(roles):
        s = roles[r]
        models = ", ".join(f"{m} (${c:.2f})" for m, c in sorted(s["models"].items()))
        role_rows += (
            f'<tr><td>{_esc(r)}</td><td>{s["runs"]}</td>'
            f'<td>${s["cost"]:.2f}</td><td>{_esc(models)}</td></tr>\n'
        )

    # ponytail: inline CSS, no external deps
    return f"""<!DOCTYPE html>
<html lang="en">
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

<h2>Cost by role</h2>
{"<p class='empty'>No agent run data with role tracking.</p>" if not role_rows else f'''
<table>
<tr><th>Role</th><th>Runs</th><th>Cost</th><th>Models</th></tr>
{role_rows}</table>'''}

<footer style="margin-top:3rem;color:#999;font-size:0.75rem;">
  Generated by <code>aisef dashboard</code> v0.5.0
</footer>
</body>
</html>"""


def _collect_projects(args) -> list[tuple[str, Path, list[Evidence]]]:
    """Collect evidence from the main project and any additional projects.

    Trả cả **thư mục tạo tác**, không chỉ tên và bằng chứng: sổ hành vi và bảng
    hợp quy đọc từ đĩa, và một bảng điều khiển nhiều dự án không thể suy ngược
    đường dẫn từ cái tên.
    """
    groups: list[tuple[str, Path, list[Evidence]]] = []
    root = _artifact_root(args)
    store = EvidenceStore(root)
    ids = store.stories()
    if ids:
        evidences = [store.read(sid) for sid in ids]
        groups.append((Path(args.project).resolve().name, root, evidences))
    for p in getattr(args, "projects", None) or []:
        pp = Path(p).resolve()
        pr = pp / "_bmad-output"
        if not pr.is_dir():
            continue
        st = EvidenceStore(pr)
        sids = st.stories()
        if sids:
            groups.append((pp.name, pr, [st.read(sid) for sid in sids]))
    return groups


def _project_summary(groups: list[tuple[str, Path, list[Evidence]]]) -> str:
    """Multi-project summary table."""
    if len(groups) <= 1:
        return ""
    rows = []
    for name, _root, evs in groups:
        stories = len(evs)
        cost = sum(e.total_cost_usd for e in evs)
        blocks = sum(len(e.of(GUARD_BLOCK)) for e in evs)
        checks = sum(len(e.of(GUARD_CHECK)) for e in evs)
        rows.append(f"<tr><td>{_esc(name)}</td><td>{stories}</td>"
                    f"<td>${cost:.2f}</td><td>{checks}</td><td>{blocks}</td></tr>")
    return (
        "<h2>Project summary</h2>"
        "<table><tr><th>Project</th><th>Story</th><th>Cost</th>"
        "<th>Guard check</th><th>Guard block</th></tr>"
        + "\n".join(rows) + "</table>"
    )


def _tuan(at: float) -> str:
    return time.strftime("%G-W%V", time.gmtime(at))


def chi_phi_theo_tuan(groups, *, so_tuan: int = 4) -> list[tuple[str, float]]:
    """Chi phí thật theo tuần ISO, mới nhất trước. Tuần không có sự kiện không hiện."""
    theo: dict[str, float] = {}
    for _name, _root, evs in groups:
        for ev in evs:
            for e in ev.events:
                if e.cost_usd:
                    theo[_tuan(e.at)] = theo.get(_tuan(e.at), 0.0) + e.cost_usd
    return sorted(theo.items(), reverse=True)[:so_tuan]


def tuoi_hop_quy(goc_framework: Path | None = None) -> tuple[int, str]:
    """(số ngày, lý do nếu không đọc được). -1 nghĩa là không đọc được.

    Bảng hợp quy là của **framework**, không của dự án đích, và bản cài từ gói
    không mang `docs/` — nên "không đọc được" là kết cục hợp lệ, không phải lỗi.
    """
    from datetime import date

    from ..control import conformance as C

    goc = goc_framework or Path(__file__).resolve().parents[2]
    p = goc / C.REPORT_PATH
    if not p.is_file():
        return -1, f"không có {C.REPORT_PATH} (bản cài từ gói không mang docs/)"
    ngay = C.parse(p.read_text(encoding="utf-8")).generated
    try:
        sinh = date.fromisoformat(str(ngay))
    except ValueError:
        return -1, f"bảng ghi ngày sinh không đọc được: {ngay!r}"
    return (date.today() - sinh).days, ""


def tom_tat_van_hanh(groups) -> str:
    """Bốn con số vận hành, in ra terminal — thứ người vận hành hỏi hằng tuần."""
    from ..control import ledger as L

    dong = ["", "Vận hành:"]
    tuan = chi_phi_theo_tuan(groups)
    if tuan:
        dong.append("  chi phí/tuần   " + " · ".join(f"{t} ${v:.2f}" for t, v in tuan))
    else:
        dong.append("  chi phí/tuần   — nhà cung cấp không báo chi phí (mọi sự kiện $0)")

    tong_verified = tong_gap = 0
    tong_tien = 0.0
    tong_loai: dict[str, int] = {}
    for name, root, evs in groups:
        s = L.build(root).summary()
        tong_verified += s["verified"]
        tong_gap += s["gap"] + s["reopened"]
        for loai, n in s["gap_kinds"].items():
            tong_loai[loai] = tong_loai.get(loai, 0) + n
        tien = sum(e.total_cost_usd for e in evs)
        tong_tien += tien
        if len(groups) > 1:
            dong.append(f"    {name}: VERIFIED {s['verified']} · gap {s['gap']} "
                        f"· reopened {s['reopened']} · ${tien:.2f}")
    moi_do = f"{tong_verified / tong_tien:.1f} hành vi/$" if tong_tien else "— (chi phí $0)"
    dong.append(f"  VERIFIED ròng  {tong_verified} ({moi_do})")
    # Chẻ `gap tồn` theo loại vắng mặt (ADR-009 O2) **chỉ khi** có hơn một loại:
    # `unbuilt 2 · untested 0 · untraced 0` đọc thành "đã chẻ rồi mà không thấy
    # gì" (quy ước của `reviewer_qual.report` và mục token của báo cáo bench).
    # Loại đếm 0 bị bỏ, nên các số in ra luôn cộng đúng bằng `gap tồn`.
    co = {k: v for k, v in tong_loai.items() if v}
    che = " · " + " · ".join(f"{k} {v}" for k, v in co.items()) if len(co) > 1 else ""
    dong.append(f"  gap tồn        {tong_gap}{che}")

    ngay, vi_sao = tuoi_hop_quy()
    if ngay < 0:
        dong.append(f"  tuổi hợp quy   không đọc được — {vi_sao}")
    else:
        from ..control.conformance import MAX_AGE_DAYS
        dau = "✅" if ngay <= MAX_AGE_DAYS else "⚠"
        dong.append(f"  tuổi hợp quy   {ngay} ngày (trần {MAX_AGE_DAYS}) {dau}")
    return "\n".join(dong)


def cmd_dashboard(args) -> int:
    groups = _collect_projects(args)
    if not groups:
        print("✗ no evidence found — run `aisef run` first", file=__import__("sys").stderr)
        return EXIT_NOT_READY

    all_evidences = [e for _, _root, evs in groups for e in evs]
    multi_summary = _project_summary(groups)
    project_label = ", ".join(n for n, _r, _e in groups) if len(groups) > 1 else groups[0][0]
    content = generate_html(all_evidences, project=project_label,
                            extra_sections=multi_summary)

    root = _artifact_root(args)
    out = Path(args.out) if getattr(args, "out", "") else root / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"dashboard: {out}")
    print(tom_tat_van_hanh(groups))
    return EXIT_OK
