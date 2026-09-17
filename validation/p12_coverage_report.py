"""Phase 12 coverage report (owner item 6 — coverage, not just count), rendered from phase12/integrity.json and the
dataset manifest. Nothing here is typed by hand: every number is read from the consolidation.

    python3 validation/p12_coverage_report.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "closure-evidence/hardening/phase12"


def main() -> int:
    d = json.loads((P / "integrity.json").read_text(encoding="utf-8"))
    m = json.loads((P / "PHASE12-DATASET-MANIFEST.json").read_text(encoding="utf-8"))
    c = d["consolidated"]
    cov, comp = c["transition_coverage"], c["compound_fault_coverage"]
    lines = ["# Phase 12 — coverage report (100 000 single-kernel traces)", "",
             f"Rendered {time.strftime('%Y-%m-%d %H:%M %z')} from `phase12/integrity.json` and `phase12/PHASE12-DATASET-MANIFEST.json` by "
             "`validation/p12_coverage_report.py`. Kernel: `aisef/` tree `" + m["PHASE12_KERNEL_DIGEST"][:12] + "…` (PHASE12_KERNEL_DIGEST), the only digest "
             "in the dataset (`" + ", ".join(k[:12] for k in m["kernel_digests_seen"]) + "`).", "",
             "## Totals", "",
             "| traces | matched | unexplained | invariant violations | exceptions | silent skips | chunks complete | ranges |", "|---|---|---|---|---|---|---|---|",
             f"| {c['total_traces']} | {c['matched']} | {c['mismatches']} | {c['invariant_violations']} | {c['exceptions']} | {c['silent_skips']} | "
             f"{sum(1 for e in m['chunks'] if e['completion_status'] == 'COMPLETE')}/10 | overlap={c['ranges_overlap']}, missing={c['missing_intended_ranges']} |", "",
             "## Transitions T1–T34 + T6′ (docs/ASSURANCE-KERNEL.md §6)", "",
             f"Reachable in the single-story differential: **{c['reachable_transitions']['hit']} / {c['reachable_transitions']['total']} hit**. "
             f"Unhit reachable: {c['unhit_reachable'] or 'none'}.", "",
             "| transition | reachable here | model hits | first seed | covered by |", "|---|---|---|---|---|"]
    for t, v in cov.items():
        lines.append(f"| {t} | {'yes' if v['reachable_in_differential'] else 'no'} | {v['model_hits']} | {v['first_seed'] if v['first_seed'] is not None else '—'} | {v['covered_by']} |")
    lines += ["", "### Unreachable here, with justification and deterministic cover", ""]
    for t, why in c["reachable_transitions"]["unreachable_with_justification"].items():
        lines.append(f"- **{t}** — {why}")
    lines += ["", "## Typed outcomes, terminal classes, event and fault kinds", "",
              f"- typed outcomes hit ({len(c['typed_outcomes_hit'])}): {', '.join(c['typed_outcomes_hit'])}",
              f"- terminal classes, model: {c['unique_model_terminal_classes']}; kernel: {c['unique_real_terminal_classes']}",
              f"- model event kinds hit ({len(c['fault_event_kinds_hit'])}): {', '.join(c['fault_event_kinds_hit'])}",
              f"- injected fault kinds hit: {len(c['fault_kinds_hit'])} / {len(c['fault_kinds_possible'])} possible"
              + (f" — unhit: {sorted(set(c['fault_kinds_possible']) - set(c['fault_kinds_hit']))}" if set(c['fault_kinds_possible']) - set(c['fault_kinds_hit']) else " (all)"),
              "", "## Compound-fault coverage", "",
              f"- traces with ≥ 2 distinct injected faults: {comp['traces_with_2plus_distinct_faults']}",
              f"- distinct fault pairs hit: {comp['distinct_pairs_hit']} / {comp['possible_pairs']} possible" + (f" — unhit: {comp['pairs_unhit']}" if comp["pairs_unhit"] else " (all)"),
              "", "## Saturation by 10k", "", "| after seeds | transitions seen | new in this chunk |", "|---|---|---|"]
    for s in c["saturation_by_chunk"]:
        lines.append(f"| {s['after_seeds']} | {s['transitions_seen']} | {', '.join(s['new_here']) or '—'} |")
    lines += ["", "## Per chunk", "", "| chunk | seeds | traces | transitions | runtime s | mismatches | violations | rows | product tree | comparator |", "|---|---|---|---|---|---|---|---|---|---|"]
    for e in m["chunks"]:
        lines.append(f"| {e['chunk'][-5:]} | {e['seed_range'][0]}–{e['seed_range'][1]} | {e['trace_count']} | {e['transition_count']} | {e['runtime_s']} | {e['mismatches']} | "
                     f"{e['invariant_violations']} | {e['rows_count']} | {e['product_tree_digest'][:12]} | {e['comparator_digest'][:12]} |")
    lines += ["", "## Superseded runs (not qualification evidence)", "",
              f"`{m['superseded_runs']['marker']}` — {len(m['superseded_runs']['files'])} files under `phase12/superseded/` (see its README).", ""]
    (P / "COVERAGE-REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote", P / "COVERAGE-REPORT.md", "| reachable", c["reachable_transitions"]["hit"], "/", c["reachable_transitions"]["total"], "| pairs", comp["distinct_pairs_hit"], "/", comp["possible_pairs"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
