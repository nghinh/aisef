"""Cycle-1 implementation-plan validator and generator.

`docs/implementation/v2/cycle1-manifest.json` is the only scheduling source of truth. This module proves the
plan's dependency model is both *directionally* correct and *complete*, and regenerates every human-readable
scheduling fact from the manifest so prose cannot drift from it.

Checks (owner decision "CYCLE-1 IMPLEMENTATION PLAN CORRECTION" section 4):

    A dependency_direction_check          no dependency points into a later phase
    B phase_barrier_completeness_check    no package of phase N+1 is runnable before phase N is complete
    C guard_ancestry_check                every package after WP-0.4 has it as an EXPLICIT transitive ancestor
    D orchestration_semantics_check       WP-6.2 requires WP-2.5 explicitly, and all of P2-P5 effectively
    E qualification_chain_check           QP-7 < QP-8 < QP-9 < QP-10, each gated on the previous being complete

Run:
    python -P validation/v2/plan_validate.py --validate
    python -P validation/v2/plan_validate.py --generate
    python -P validation/v2/plan_validate.py --check
    python -P validation/v2/plan_validate.py --fixture PLANDEP-1 --validate   # expected to FAIL
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "implementation" / "v2"
MANIFEST = DOCS / "cycle1-manifest.json"

GEN_BEGIN = "<!-- GENERATED:{name} BEGIN — from cycle1-manifest.json; do not hand-edit -->"
GEN_END = "<!-- GENERATED:{name} END -->"


class PlanError(Exception):
    """A plan-level validation failure."""


# --------------------------------------------------------------------------------------- model


def load(path: pathlib.Path = MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _index(m: dict):
    pkgs = m["work_packages"]
    by = {p["id"]: p for p in pkgs}
    phase_order = {ph["id"]: i for i, ph in enumerate(m["phases"])}
    barrier = {ph["id"]: ph.get("barrier") for ph in m["phases"]}
    members = {ph["id"]: [p["id"] for p in pkgs if p["phase"] == ph["id"]] for ph in m["phases"]}
    return pkgs, by, phase_order, barrier, members


def explicit_ancestors(pid: str, by: dict) -> set[str]:
    """Transitive closure over declared `dependencies` only — barriers excluded."""
    seen: set[str] = set()
    stack = list(by[pid]["dependencies"])
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(by[cur]["dependencies"])
    return seen


def effective_ancestors(pid: str, by: dict, barrier: dict, members: dict) -> set[str]:
    """Closure over declared dependencies *and* phase barriers."""
    seen: set[str] = set()
    stack = list(by[pid]["dependencies"])
    b = barrier.get(by[pid]["phase"])
    if b:
        stack.extend(members[b])
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(by[cur]["dependencies"])
        cb = barrier.get(by[cur]["phase"])
        if cb:
            stack.extend(members[cb])
    return seen


def levels(m: dict) -> dict[str, int]:
    """Earliest completion level under package deps *and* phase barriers (unit cost per package)."""
    pkgs, by, _order, barrier, members = _index(m)
    lv: dict[str, int] = {}
    remaining = {p["id"] for p in pkgs}
    guard = 0
    while remaining:
        guard += 1
        if guard > len(pkgs) + 5:
            raise PlanError("cycle or unsatisfiable barrier in the dependency graph")
        progressed = False
        for pid in sorted(remaining):
            deps = by[pid]["dependencies"]
            b = barrier.get(by[pid]["phase"])
            need = list(deps) + (members[b] if b else [])
            if all(n in lv for n in need):
                lv[pid] = (max((lv[n] for n in need), default=0)) + 1
                remaining.discard(pid)
                progressed = True
        if not progressed:
            raise PlanError(f"cannot schedule: {sorted(remaining)}")
    return lv


def critical_path(m: dict) -> list[str]:
    _pkgs, by, _order, barrier, members = _index(m)
    lv = levels(m)
    cur = max(lv, key=lambda k: (lv[k], k))
    path = [cur]
    while True:
        b = barrier.get(by[cur]["phase"])
        need = list(by[cur]["dependencies"]) + (members[b] if b else [])
        if not need:
            break
        cur = max(need, key=lambda k: (lv[k], k))
        path.append(cur)
    path.reverse()
    return path


# --------------------------------------------------------------------------------------- checks


def check_a_direction(m: dict) -> list[str]:
    _pkgs, by, order, _b, _mem = _index(m)
    out = []
    for p in by.values():
        for d in p["dependencies"]:
            if d not in by:
                out.append(f"A: {p['id']} depends on unknown package {d}")
            elif order[by[d]["phase"]] > order[p["phase"]]:
                out.append(f"A: {p['id']} ({p['phase']}) depends on {d} ({by[d]['phase']}) — a later phase")
    return out


def check_b_barriers(m: dict) -> list[str]:
    _pkgs, by, order, barrier, members = _index(m)
    out = []
    for ph in m["phases"]:
        b = barrier.get(ph["id"])
        idx = order[ph["id"]]
        if idx == 0:
            if b is not None:
                out.append(f"B: first phase {ph['id']} must have no barrier")
            continue
        prev = m["phases"][idx - 1]["id"]
        if b != prev:
            out.append(f"B: phase {ph['id']} barrier is {b!r}, must be {prev!r}")
        if not ph.get("exit_checks"):
            out.append(f"B: phase {ph['id']} declares no exit checks")
    # Independent of the declared barrier: every package must be unable to run before the phase that
    # precedes it IN THE NORMATIVE ORDER is complete. Comparing against the declared barrier would only
    # restate the declaration; comparing against the required predecessor catches a mis-declared one.
    lv = levels(m)
    for p in by.values():
        idx = order[p["phase"]]
        if idx == 0:
            continue
        required = m["phases"][idx - 1]["id"]
        worst = max(lv[q] for q in members[required])
        if lv[p["id"]] <= worst:
            out.append(f"B: {p['id']} is runnable at level {lv[p['id']]} before {required} completes at "
                       f"level {worst}")
    return out


def check_c_guard_ancestry(m: dict) -> list[str]:
    _pkgs, by, _o, _b, _mem = _index(m)
    guard = m["scheduling_rules"]["evidence_guard_package"]
    exempt = set(m["scheduling_rules"]["evidence_guard_exempt"])
    out = []
    for p in by.values():
        if p["id"] in exempt:
            continue
        if guard not in explicit_ancestors(p["id"], by):
            out.append(f"C: {p['id']} does not have {guard} as an explicit transitive ancestor")
    return out


def check_d_orchestration(m: dict) -> list[str]:
    _pkgs, by, _o, barrier, members = _index(m)
    rule = m["scheduling_rules"]["orchestration"]
    target = rule["package"]
    out = []
    exp = explicit_ancestors(target, by)
    for req in rule["explicit_prerequisites"]:
        if req not in exp:
            out.append(f"D: {target} does not explicitly require {req}")
    eff = effective_ancestors(target, by, barrier, members)
    for ph in rule["phases_required_complete"]:
        missing = [q for q in members[ph] if q not in eff]
        if missing:
            out.append(f"D: {target} does not require completion of {ph}: missing {missing}")
    return out


def check_e_qualification_chain(m: dict) -> list[str]:
    _pkgs, by, _o, barrier, members = _index(m)
    chain = m["scheduling_rules"]["qualification_chain"]
    out = []
    for prev, nxt in itertools.pairwise(chain):
        eff = effective_ancestors(nxt, by, barrier, members)
        if prev not in eff:
            out.append(f"E: {nxt} can start without {prev} being complete")
    first = chain[0]
    eff = effective_ancestors(first, by, barrier, members)
    for q in members["P6"]:
        if q not in eff:
            out.append(f"E: {first} can start before P6 is evidence-complete (missing {q})")
    return out


# --------------------------------------------------------------------------------------- F · G

#: A clause asserting that an absent/missing subject yields REFUTED — a global missing-path rule the RFC does not
#: have (§10.2: REQUIRES_SUBJECT -> INDETERMINATE(PRECONDITION_ABSENT); ABSENCE_IS_DECIDABLE -> the verdict the
#: spec's observable implies). A clause may state it only for one spec, marked "scoped to ProductProofSpec <id>".
_ABSENCE_REFUTED = re.compile(r"(missing|absent|absence)[^;|\n]*?(⇒|->|=>|→)[^;|\n]*?\bREFUTED\b", re.I)
_SCOPED = "scoped to ProductProofSpec"
#: The WP-2.1 acceptance cases and what each must expect (owner decision before P2 authorization).
PROBE_ABS = {
    "PROBE-ABS-1": {("expect", "status"): "UNRUNNABLE", ("expect", "owner"): "ENVIRONMENT"},
    "PROBE-ABS-2": {("subject_absence",): "REQUIRES_SUBJECT", ("expect", "status"): "EXECUTED",
                    ("expect", "behavior_verdict"): "INDETERMINATE", ("expect", "reason"): "PRECONDITION_ABSENT"},
    "PROBE-ABS-3": {("subject_absence",): "ABSENCE_IS_DECIDABLE", ("expect", "status"): "EXECUTED",
                    ("expect", "contract_satisfaction"): "UNSATISFIED"},
    "PROBE-ABS-4": {("subject_absence",): "ABSENCE_IS_DECIDABLE", ("expect", "status"): "EXECUTED",
                    ("expect", "contract_satisfaction"): "SATISFIED"},
    "PROBE-ABS-5": {},
}


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _absence_refuted(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"[;|\n]", text) if _ABSENCE_REFUTED.search(c) and _SCOPED not in c]


def check_f_probe_absence_semantics(m: dict, docs: pathlib.Path | None = None) -> list[str]:
    """PLANSEM: the plan states subject absence exactly as the RFC does — never as a global 'missing -> REFUTED'."""
    docs = docs or DOCS
    out = [f"PLANSEM: manifest asserts a global missing-subject => REFUTED: {c[:100]}"
           for s in _strings(m) for c in _absence_refuted(s)]
    out += [f"PLANSEM: {d.name} asserts a global missing-subject => REFUTED: {c[:100]}"
            for d in sorted(docs.glob("*.md")) for c in _absence_refuted(d.read_text(encoding="utf-8"))]
    wp = next((p for p in m["work_packages"] if p["id"] == "WP-2.1"), None)
    cases = {c.get("id"): c for c in (wp or {}).get("acceptance_cases", [])}
    for cid, want in PROBE_ABS.items():
        case = cases.get(cid)
        if case is None:
            out.append(f"PLANSEM: WP-2.1 lacks acceptance case {cid}")
            continue
        for path, value in want.items():
            got = case
            for key in path:
                got = got.get(key) if isinstance(got, dict) else None
            if got != value:
                out.append(f"PLANSEM: {cid} {'.'.join(path)} must be {value}, is {got}")
    if not {"REQUIRES_SUBJECT", "ABSENCE_IS_DECIDABLE"} <= {c.get("subject_absence") for c in cases.values()}:
        out.append("PLANSEM: WP-2.1 acceptance cases do not distinguish REQUIRES_SUBJECT from ABSENCE_IS_DECIDABLE")
    out += [f"PLANSEM: {cid} expects a raw REFUTED for an absent subject — the verdict is the spec's, not global"
            for cid, c in cases.items() if (c.get("expect") or {}).get("behavior_verdict") == "REFUTED"]
    return out


def check_g_baseline(m: dict) -> list[str]:
    """BASELINE: the plan cites the current approved architecture — the original approval plus every amendment,
    exactly as validation/v2/freeze_manifest.py verifies the lineage."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("aisef_v2_fm_for_plan", ROOT / "validation" / "v2" / "freeze_manifest.py")
    fm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fm)
    eff, links, broken = fm.lineage(ROOT)
    ab = m["architecture_baseline"]
    out = [f"BASELINE: freeze lineage broken: {b}" for b in broken]
    for key in ("rfc_normative_digest", "freeze_table_digest"):
        if ab.get(key) != eff[key]:
            out.append(f"BASELINE: plan cites {key} {str(ab.get(key))[:16]}…, the approved lineage ends at {eff[key][:16]}…")
    if ab.get("approval_record_sha256") != links[0]["sha256"]:
        out.append("BASELINE: plan cites a different original approval record")
    if [(a.get("record"), a.get("sha256")) for a in ab.get("amendments", [])] != [(l["record"], l["sha256"]) for l in links[1:]]:
        out.append("BASELINE: plan amendments differ from the approval lineage")
    return out


CHECKS = [
    ("A dependency_direction", check_a_direction),
    ("B phase_barrier_completeness", check_b_barriers),
    ("C guard_ancestry", check_c_guard_ancestry),
    ("D orchestration_semantics", check_d_orchestration),
    ("E qualification_chain", check_e_qualification_chain),
    ("F probe_absence_semantics", check_f_probe_absence_semantics),
    ("G architecture_baseline", check_g_baseline),
]


def validate(m: dict) -> list[str]:
    problems: list[str] = []
    for _name, fn in CHECKS:
        problems.extend(fn(m))
    # F-item coverage is a plan-completeness property too
    covered = {f: [p["id"] for p in m["work_packages"] if f in p["frozen_items"]]
               for f in m["architecture_baseline"]["frozen_items"]}
    for f, pk in covered.items():
        if not pk:
            problems.append(f"COVERAGE: frozen item {f} has no work package")
    for p in m["work_packages"]:
        if not p["exit_criteria"]:
            problems.append(f"EXIT: {p['id']} declares no exit criterion")
    return problems


# --------------------------------------------------------------------------------------- fixtures


def apply_fixture(m: dict, name: str) -> dict:
    """Negative fixtures for the PLANDEP plan-level adversarial tests."""
    m = copy.deepcopy(m)
    by = {p["id"]: p for p in m["work_packages"]}
    if name == "PLANDEP-1":  # remove WP-0.4 ancestry from a P1 package
        by["WP-1.1"]["dependencies"] = []
    elif name == "PLANDEP-2":  # let P3 start before P2 exit
        for ph in m["phases"]:
            if ph["id"] == "P3":
                ph["barrier"] = "P1"
    elif name == "PLANDEP-3":  # drop WP-2.5 from WP-6.2's prerequisites
        by["WP-6.2"]["dependencies"] = [d for d in by["WP-6.2"]["dependencies"] if d != "WP-2.5"]
        m["scheduling_rules"]["orchestration"]["explicit_prerequisites"] = ["WP-2.5"]
    elif name == "PLANDEP-4":  # let QP-8 run before QP-7
        by["QP-8"]["dependencies"] = []
        for ph in m["phases"]:
            if ph["id"] == "P8":
                ph["barrier"] = "P6"
    elif name == "PLANSEM-1":  # the manifest back to: missing subject => EXECUTED + REFUTED
        by["WP-2.1"]["adversarial_tests"].insert(1, "missing subject -> EXECUTED + REFUTED (observation), never UNRUNNABLE")
    elif name == "PLANSEM-2":  # drop the REQUIRES_SUBJECT / ABSENCE_IS_DECIDABLE distinction from the P2 cases
        for c in by["WP-2.1"]["acceptance_cases"]:
            c["subject_absence"] = "any"
    else:
        raise PlanError(f"unknown fixture {name}")
    return m


# --------------------------------------------------------------------------------------- generation


def _table(rows: list[tuple[str, ...]], head: tuple[str, ...]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def gen_evidence_table(m: dict, phases: tuple[str, ...]) -> str:
    return "\n".join(_table([(p["evidence_label"], p["evidence_asserts"]) for p in m["work_packages"]
                              if p["phase"] in phases], ("artefact", "asserts")))


def gen_baseline(m: dict) -> str:
    ab = m["architecture_baseline"]
    amend = "; ".join(f"[`{a['record'].rsplit('/', 1)[-1]}`](../../../{a['record']}) (`{a['sha256'][:16]}…`, "
                      f"changes {', '.join(a['frozen_items_changed'])})" for a in ab.get("amendments", []))
    return (f"**Architecture baseline — frozen.**\n"
            f"[`{ab['rfc']}`](../../architecture/{ab['rfc'].rsplit('/', 1)[-1]}), approved at commit `2fe672c`. "
            f"Approval record\n[`{ab['approval_record']}`](../../../{ab['approval_record']}), content-addressed "
            f"`{ab['approval_record_sha256'][:16]}…`, amended by {amend or 'nothing'}.\n"
            f"Current RFC normative digest `{ab['rfc_normative_digest'][:16]}…`; freeze-table digest "
            f"`{ab['freeze_table_digest'][:16]}…` (originally `{ab['original_rfc_normative_digest'][:16]}…` / "
            f"`{ab['original_freeze_table_digest'][:16]}…`). **F1–F11 frozen.**")


def gen_phase_table(m: dict) -> str:
    _pkgs, by, _o, barrier, members = _index(m)
    rows = []
    for ph in m["phases"]:
        n = len(members[ph["id"]])
        rows.append((f"**{ph['id']}** {ph['name']}", str(n), barrier.get(ph["id"]) or "—", ph["exit"]))
    return "\n".join(_table(rows, ("phase", "packages", "barrier", "exit condition")))


def gen_parallel_sets(m: dict) -> str:
    """Parallel sets are derived: packages at the same level, within one phase, with disjoint write scopes."""
    _pkgs, by, _o, _b, members = _index(m)
    lv = levels(m)
    buckets: dict[tuple[str, int], list[str]] = {}
    for p in by.values():
        buckets.setdefault((p["phase"], lv[p["id"]]), []).append(p["id"])
    rows = []
    for (ph, level), ids in sorted(buckets.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if len(ids) > 1:
            rows.append((ph, str(level), ", ".join(f"`{i}`" for i in sorted(ids))))
    if not rows:
        return "_No two packages share a level within a phase; the plan is fully sequential._"
    return "\n".join(_table(rows, ("phase", "level", "packages that may run in parallel")))


def gen_critical_path(m: dict) -> str:
    path = critical_path(m)
    body = " → ".join(f"`{p}`" for p in path)
    return f"**Length {len(path)} packages.**\n\n{body}"


def gen_dependency_graph_doc(m: dict) -> str:
    _pkgs, by, _o, barrier, members = _index(m)
    lv = levels(m)
    L = [
        "# AISEF V2 — Cycle-1 dependency graph",
        "",
        "**Generated from [`cycle1-manifest.json`](cycle1-manifest.json) by `validation/v2/plan_validate.py`.**",
        "Do not hand-edit: `--check` fails on drift.",
        "",
        "Scheduling model: a package is runnable when every declared dependency is complete **and** its phase's",
        "barrier phase is evidence-complete. Parallelism is permitted **within a phase only**.",
        "",
        "---",
        "",
        "## 1. Phase barriers",
        "",
        gen_phase_table(m),
        "",
        "A phase is complete only when all of its packages are complete, all required evidence artefacts exist,",
        "and all of its exit checks are green.",
        "",
        "## 2. Phase exit checks",
        "",
    ]
    for ph in m["phases"]:
        L.append(f"**{ph['id']}** — " + "; ".join(ph.get("exit_checks", [])))
        L.append("")
    L += ["## 3. Package graph", "", "| package | phase | level | declared dependencies |", "|---|---|---|---|"]
    for p in sorted(m["work_packages"], key=lambda p: (lv[p["id"]], p["id"])):
        deps = ", ".join(f"`{d}`" for d in p["dependencies"]) or "—"
        L.append(f"| `{p['id']}` | {p['phase']} | {lv[p['id']]} | {deps} |")
    L += ["", "*Level* is the earliest completion step under barriers, unit cost per package.", "",
          "## 3a. Additional scheduling constraints", ""]
    L += _table([(c["rule"], c["why"], c["enforced_by"])
                 for c in m["scheduling_rules"].get("additional_constraints", [])],
                ("constraint", "why", "enforced by"))
    L += ["",
          "## 4. Critical path", "", gen_critical_path(m), "",
          "Barriers make the path longer than a purely semantic graph would. That is deliberate:",
          "correctness and evidence ordering have priority over elapsed time.", "",
          "## 5. Parallel sets", "", gen_parallel_sets(m), "",
          "Parallel execution additionally requires disjoint write scopes and disjoint evidence scopes, and is",
          "never permitted across a phase barrier. `WP-3.5` carries an extra authorship-independence constraint.",
          "",
          "## 6. Validation results", "",
          "| check | result |", "|---|---|"]
    problems = validate(m)
    for name, fn in CHECKS:
        errs = fn(m)
        L.append(f"| {name} | **{'PASS' if not errs else 'FAIL'}** |")
    L.append(f"| F1–F11 coverage | **{len(m['architecture_baseline']['frozen_items'])}/11** |")
    L.append(f"| total problems | **{len(problems)}** |")
    L.append("")
    return "\n".join(L)


def gen_traceability_doc(m: dict) -> str:
    ab = m["architecture_baseline"]
    P = m["work_packages"]
    _pkgs, by, _o, _b, _mem = _index(m)
    L = [
        "# AISEF V2 — Cycle-1 traceability matrix",
        "",
        "**Generated from [`cycle1-manifest.json`](cycle1-manifest.json) by `validation/v2/plan_validate.py`.**",
        "Do not hand-edit: `--check` fails on drift.",
        "",
        f"Architecture baseline: RFC normative digest `{ab['rfc_normative_digest'][:16]}…`, freeze-table digest",
        f"`{ab['freeze_table_digest'][:16]}…`, approval record `{ab['approval_record_sha256'][:16]}…` amended by "
        + (", ".join(f"`{a['record'].rsplit('/', 1)[-1]}`" for a in ab.get("amendments", [])) or "nothing") + ".",
        "",
        f"**{m['counts']['implementation_packages']} implementation + {m['counts']['qualification_packages']} "
        f"qualification = {m['counts']['total']} packages. F1–F11 coverage: 11/11.**",
        "",
        "---",
        "",
        "## 1. Frozen item → packages → tests → evidence → V1 defect families",
        "",
    ]
    for f in ab["frozen_items"]:
        pk = [p for p in P if f in p["frozen_items"]]
        fams = sorted({x for p in pk for x in p["v1_defect_families"]})
        L += [f"### {f} — {len(pk)} packages", ""]
        L += _table([(f"`{p['id']}`", ", ".join(p["rfc_sections"]),
                      "; ".join(p["adversarial_tests"][:2]) or "—", f"`{p['evidence_artifact']}`") for p in pk],
                    ("package", "RFC §§", "key adversarial tests", "evidence artifact"))
        L += ["", "**V1 defect families:** "
              + (", ".join("`" + x + "`" for x in fams) if fams else "— (structural item)"), ""]
    L += ["---", "", "## 2. Package → phase → dependencies → evidence", ""]
    L += _table([(f"`{p['id']}`", p["phase"],
                  ", ".join("`" + d + "`" for d in p["dependencies"]) or "—",
                  f"`{p['evidence_artifact']}`") for p in P],
                ("package", "phase", "depends on", "evidence"))
    L += ["", "---", "", "## 3. V1 defect family → packages", ""]
    allf = sorted({x for p in P for x in p["v1_defect_families"]})
    L += _table([(f"`{fam}`", ", ".join("`" + p["id"] + "`" for p in P if fam in p["v1_defect_families"]))
                 for fam in allf], ("family", "packages"))
    L += ["",
          f"{len(allf)} of the 22 registered families are directly addressed by cycle-1 packages. The remainder",
          "are measured rather than prevented (`FAM-PROVIDER`, `FAM-MODEL-CAPABILITY`), governed by the",
          "evaluation-cohort lifecycle which is deferred (`FAM-BENCH`), or addressed by the ladder as a whole.",
          ""]
    return "\n".join(L)


GENERATED_FILES = {
    "AISEF-V2-CYCLE1-DEPENDENCY-GRAPH.md": gen_dependency_graph_doc,
    "AISEF-V2-CYCLE1-TRACEABILITY.md": gen_traceability_doc,
}

GENERATED_BLOCKS = {
    "AISEF-V2-CYCLE1-IMPLEMENTATION-PLAN.md": {
        "architecture-baseline": gen_baseline,
        "phase-table": gen_phase_table,
        "parallel-sets": gen_parallel_sets,
        "critical-path": gen_critical_path,
    },
    "AISEF-V2-CYCLE1-EVIDENCE-PLAN.md": {
        "phase-exit-checks": lambda m: "\n".join(
            _table([(ph["id"], "; ".join(ph.get("exit_checks", []))) for ph in m["phases"]],
                   ("phase", "exit checks — all must be green before the next phase may start"))),
        **{f"evidence-{name}": (lambda m, ph=phases: gen_evidence_table(m, ph)) for name, phases in (
            ("P0", ("P0",)), ("P1", ("P1",)), ("P2", ("P2",)), ("P3", ("P3",)), ("P4", ("P4",)), ("P5", ("P5",)),
            ("P6", ("P6",)), ("P7-P10", ("P7", "P8", "P9", "P10")))},
    },
}


def render_blocks(text: str, name: str, body: str) -> str:
    begin, end = GEN_BEGIN.format(name=name), GEN_END.format(name=name)
    if begin not in text or end not in text:
        raise PlanError(f"missing generated-block markers for {name!r}")
    head, rest = text.split(begin, 1)
    _old, tail = rest.split(end, 1)
    return f"{head}{begin}\n\n{body}\n\n{end}{tail}"


def check_evidence_names(m: dict) -> list[str]:
    """Every evidence artefact the evidence plan names must be declared by some package in the manifest."""
    import re
    text = (DOCS / "AISEF-V2-CYCLE1-EVIDENCE-PLAN.md").read_text(encoding="utf-8")
    declared = " ".join(p["evidence_artifact"] for p in m["work_packages"])
    named = set(re.findall(r"`([A-Z0-9][A-Za-z0-9/_-]*\.(?:json|md))`", text))
    return [f"EVIDENCE-PLAN names {n!r}, which no package declares" for n in sorted(named) if n not in declared]


def generate(m: dict, write: bool) -> list[str]:
    drift = list(check_evidence_names(m))
    for fname, fn in GENERATED_FILES.items():
        path = DOCS / fname
        want = fn(m)
        have = path.read_text(encoding="utf-8") if path.exists() else None
        if have != want:
            drift.append(f"{fname}: generated content differs")
            if write:
                path.write_text(want, encoding="utf-8")
    for fname, blocks in GENERATED_BLOCKS.items():
        path = DOCS / fname
        text = path.read_text(encoding="utf-8")
        want = text
        for name, fn in blocks.items():
            want = render_blocks(want, name, fn(m))
        if want != text:
            drift.append(f"{fname}: generated block(s) differ")
            if write:
                path.write_text(want, encoding="utf-8")
    return drift


# --------------------------------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--fixture")
    a = ap.parse_args(argv)

    m = load()
    if a.fixture:
        m = apply_fixture(m, a.fixture)

    rc = 0
    if a.validate or not (a.generate or a.check):
        problems = validate(m)
        for name, fn in CHECKS:
            errs = fn(m)
            print(f"{'PASS' if not errs else 'FAIL'}  {name}")
            for e in errs:
                print(f"      {e}")
        print(f"\ncritical path: {len(critical_path(m))} packages")
        print(f"total problems: {len(problems)}")
        rc |= 1 if problems else 0
    if a.generate or a.check:
        drift = generate(m, write=a.generate)
        if drift:
            for d in drift:
                print(f"{'REGENERATED' if a.generate else 'DRIFT'}  {d}")
            rc |= 0 if a.generate else 1
        else:
            print("generated artefacts in sync")
    return rc


if __name__ == "__main__":
    sys.exit(main())
