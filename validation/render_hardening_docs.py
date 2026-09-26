"""Render the systematic-hardening documents from their machine-readable sources.

    python3 validation/render_hardening_docs.py            # all
    python3 validation/render_hardening_docs.py invariants # docs/INVARIANTS.md from aisef/invariants.yaml
    python3 validation/render_hardening_docs.py families   # docs/DEFECT-FAMILY-MAP.md from closure-evidence/hardening/defect-family-map.json
    python3 validation/render_hardening_docs.py faults     # docs/FAULT-MATRIX.md from closure-evidence/hardening/fault-matrix.json
    python3 validation/render_hardening_docs.py capabilities # docs/TOOL-CAPABILITIES.md from aisef/harness/capabilities.py

The JSON/YAML files are the sources; the markdown is derived and `tests/hardening/test_invariants_registry.py`
asserts the rendered documents are in sync.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import invariants as INV  # noqa: E402

FAMILIES = {
    "A": "Candidate identity", "B": "Story epoch", "C": "Baseline identity", "D": "Evidence provenance",
    "E": "Evidence freshness", "F": "Typed outcomes", "G": "Retry locality", "H": "No-op semantics",
    "I": "Workspace ownership", "J": "Write scope", "K": "Retry hygiene", "L": "Process lifecycle",
    "M": "Claim / lease state", "N": "Tool capability", "O": "Scheduler isolation", "P": "Approval invalidation",
    "Q": "Human arbitration", "R": "Release identity", "S": "Replay identity", "T": "Pass safety",
}


def render_invariants() -> str:
    return INV.render_markdown(INV.load(), families=FAMILIES)


def render_families() -> str:
    d = json.loads((ROOT / "closure-evidence/hardening/defect-family-map.json").read_text(encoding="utf-8"))
    md = ["# Defect family map (systematic hardening v1, Phase 2)", "",
          "Rendered from `closure-evidence/hardening/defect-family-map.json` by `validation/render_hardening_docs.py` — edit the JSON. "
          "A defect family is one architectural cause; defect ids that share it are not independent, and the unit of closure is the family. "
          "Invariant ids refer to `docs/INVARIANTS.md`.", "", "## Families", "",
          "| family | name | cause | invariants | members |", "|---|---|---|---|---|"]
    for fid, f in d["families"].items():
        md.append(f"| {fid} | {f['name']} | {f['cause']} | {', '.join(f['invariants'])} | {', '.join(d['summary'][fid])} |")
    md += ["", "## Members", "",
           "| id | title | symptom | root cause | family | missing invariants | previous fix | remaining sibling risk | current coverage | status |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for x in d["members"]:
        md.append("| " + " | ".join(str(x[k]).replace("|", "\\|") for k in (
            "id", "title", "symptom", "root_cause", "family", "missing_invariants", "previous_fix",
            "remaining_sibling_risk", "current_coverage", "status")) + " |")
    md += ["", "## Reading the map", "",
           "- **Open in the register**: D-002 (P2, FAM-JUDGE), D-003 (P2, FAM-BENCH), D-011 (P2, FAM-OWNERSHIP), D-024 (P2, FAM-PROCESS), "
           "D-035 (P1, FAM-RECOVERY). Phase 8 dispositions each as FIXED, NOT_A_DEFECT with proof, or SUPERSEDED by a family fix.",
           "- **Chains**: D-032 → D-033 → D-034 → D-035 are four symptoms of two causes — identity by recency (FAM-IDENTITY) and recovery "
           "without evidence invalidation (FAM-RECOVERY). Each narrow release removed one symptom and exposed the next; the family fix is "
           "the kernel's evidence identity + freshness model (Phases 4, 8, 9).",
           "- **Previous fixes marked local** are the sibling risk the Phase 3 sweep targets (`closure-evidence/hardening/sibling-scan.json`)."]
    return "\n".join(md) + "\n"


def render_faults() -> str:
    d = json.loads((ROOT / "closure-evidence/hardening/fault-matrix.json").read_text(encoding="utf-8"))
    md = ["# Fault-injection matrix (systematic hardening v1, Phase 7)", "",
          "Rendered from `closure-evidence/hardening/fault-matrix.json` by `validation/render_hardening_docs.py` — edit the JSON. "
          "Every required cell names the scenario, the expected typed outcome/state, the expected evidence and recovery, the "
          "invariants asserted, the test that exercises it, and its status (GREEN / RED expected-failure of a registered defect / "
          "NEEDS_TEST). Tests live under `tests/hardening/` and use the synthetic client (`aisef/clients/synthetic.py`), never a model.", "",
          "## Stage × fault grid", "", "| stage | " + " | ".join(d["faults"]) + " |", "|---|" + "---|" * len(d["faults"])]
    for stage in d["stages"]:
        cells = []
        for fault in d["faults"]:
            hits = [s for s in d["scenarios"] if s["stage"] == stage and s["fault"] == fault]
            cells.append(", ".join(f"{s['id']} ({s['status']})" for s in hits) if hits else "—")
        md.append(f"| {stage} | " + " | ".join(cells) + " |")
    md += ["", "## Scenarios", "",
           "| id | stage | fault | scenario | expected state | expected evidence | expected recovery | invariants | test | status |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for s in d["scenarios"]:
        md.append("| " + " | ".join(str(s[k]).replace("|", "\\|") for k in (
            "id", "stage", "fault", "scenario", "expected_state", "expected_evidence", "expected_recovery",
            "invariants", "test", "status")) + " |")
    counts = {}
    for s in d["scenarios"]:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    md += ["", "**Status count:** " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f" of {len(d['scenarios'])} scenarios."]
    return "\n".join(md) + "\n"


def render_capabilities() -> str:
    """The product contract for default evidence tools (SS-65) — rendered from the registry, never written by hand."""
    from aisef.harness import capabilities as C
    md = ["# Default tool capabilities", "",
          "Rendered from `aisef/harness/capabilities.py` by `validation/render_hardening_docs.py capabilities`; "
          "`tests/hardening/test_tool_capability.py` keeps it in sync. This is the product contract for the evidence "
          "tools AISEF selects when a project leaves `tools.<role>` empty (INV-N.DEFAULT-CAPABILITY): every tool listed "
          "as selected is executable in the environment listed for its stack, proven on real images by "
          "`validation/tool_capability_qualification.py` (`closure-evidence/hardening/tool-capability-matrix.json`).", "",
          "## Configuration semantics", "",
          "| `tools.<role>` | `tools.disabled` | meaning |", "|---|---|---|",
          "| empty | role not listed | **AUTO** — the stack profile below decides; this is the only meaning of empty |",
          "| a command | role not listed | **EXPLICIT** — the project's command, probed where it runs |",
          "| empty | role listed | **DISABLED** — typed off: never run, never evidence, recorded as such |",
          "| a command | role listed | refused at config load (contradiction) |", "",
          f"Required roles ({', '.join(r.value for r in C.REQUIRED_ROLES)}) cannot be disabled. A role a profile leaves "
          "empty (**none** below) runs nothing and says why; the gate never pretends such a tool exists.", "",
          "Provision: **managed** = installed by the harness-built image at the pinned version; **toolchain** = part of the "
          "digest-pinned base image; **project** = the project declares it (the image provides the runtime); "
          "**none** = no default tool for the role.", "",
          "## Profiles", ""]
    for p in C.PROFILES:
        md += [f"### {p.stack}", "",
               f"- markers: {', '.join(f'`{m}`' for m in p.markers)}",
               f"- environment: `{p.image}`" + (f" (built from `{p.base}`)" if p.managed else ""),
               ""]
        if p.managed:
            md += ["```dockerfile", p.dockerfile().rstrip(), "```", ""]
        md += ["| role | tool | command | provision | version | evidence | note |", "|---|---|---|---|---|---|---|"]
        for c in p.capabilities:
            md.append(f"| {c.role.value} | {c.tool_id if c.provision is not C.Provision.NONE else '—'} | "
                      f"{('`' + c.command + '`') if c.command else '—'} | {c.provision.value} | {c.version_policy} | "
                      f"{c.evidence or '—'} | {c.note.replace('|', '/') or '—'} |")
        if p.runtime:
            md += ["", "Runtime probes: " + ", ".join(f"`{' '.join(r.argv)}`" + (f" → `{r.expect}`" if r.expect else "")
                                                     for r in p.runtime)]
        md.append("")
    md.append("Any project without a marker runs its explicit tools in `" + C.FALLBACK_IMAGE + "`, which carries no stack tool.")
    return "\n".join(md) + "\n"


def main(argv: list[str]) -> int:
    which = set(argv[1:]) or {"invariants", "families", "faults", "capabilities"}
    if "invariants" in which:
        (ROOT / "docs/INVARIANTS.md").write_text(render_invariants(), encoding="utf-8"); print("wrote docs/INVARIANTS.md")
    if "families" in which:
        (ROOT / "docs/DEFECT-FAMILY-MAP.md").write_text(render_families(), encoding="utf-8"); print("wrote docs/DEFECT-FAMILY-MAP.md")
    if "faults" in which and (ROOT / "closure-evidence/hardening/fault-matrix.json").exists():
        (ROOT / "docs/FAULT-MATRIX.md").write_text(render_faults(), encoding="utf-8"); print("wrote docs/FAULT-MATRIX.md")
    if "capabilities" in which:
        (ROOT / "docs/TOOL-CAPABILITIES.md").write_text(render_capabilities(), encoding="utf-8"); print("wrote docs/TOOL-CAPABILITIES.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
