#!/usr/bin/env python3 -P
"""Step 2 (owner decision 2026-10-28): reconcile the 62 MISSING V2.1 targets at fce3d7b7.

Deterministic, read-only: reads the committed MUTATION-SUMMARY.json (whose stale_excluded_results.why
were produced by the FROZEN proof() of v21_mutation_record.py, each using that result's own measured_on)
and the two resume workers' records. No proof re-run, no rule change, no measurement.

Classifies each MISSING target by what blocks reuse of its MOST BENIGN available result, reconciles the
199-target resume slice against the record, and records why the record's 180+372+62 differs from the
Oct-20 read-set plan's 262 re-measure / 352 reuse.

    python -P closure-evidence/v2/v2.1/tools/reconcile_missing_62.py
"""
import json, pathlib, re, collections

R = pathlib.Path(__file__).resolve().parents[1]              # .../closure-evidence/v2/v2.1
s = json.load(open(R / "MUTATION-SUMMARY.json"))
miss = set(s["MISSING_TARGETS"])
maf = set(s["classes"]["measured_at_final_head"])
reuse = set(s["classes"]["reused_after_mechanical_proof"])
stale = [e for e in s["stale_excluded_results"] if e["target"] in miss]

per = collections.defaultdict(list)
for e in stale:
    per[e["target"]].append(e)

def tags_of(why):
    tags, kt = set(), set()
    for w in why:
        if w.startswith("the target file changed"): tags.add("MODULE")
        elif w.startswith("its kill set is not the current one"): tags.add("KILLSET")
        elif w.startswith("kill tests changed"):
            tags.add("KILLTESTS")
            m = re.match(r"kill tests changed: (.*)", w)
            if m: kt.update(f.strip() for f in m.group(1).split(","))
        elif w.startswith("its mutants are not the current generator"): tags.add("MUTANTS")
        else: tags.add("OTHER")
    return tags, kt

SEV = {"MODULE": 4, "MUTANTS": 3, "KILLSET": 2, "KILLTESTS": 1}
def score(t): return (len(t), sum(SEV.get(x, 5) for x in t))

rows = []
for tgt in sorted(miss):
    best = None; bt = None; bkt = None; union = set()
    for e in per[tgt]:
        t, kt = tags_of(e["why"]); union |= t
        if best is None or score(t) < score(bt):
            best, bt, bkt = e, t, kt
    if "MODULE" in bt:
        h = "REMEASURE-PRODUCT"
    elif "KILLTESTS" in bt or "KILLSET" in bt:
        h = "REMEASURE-TESTS"
    elif "MUTANTS" in bt:
        h = "REMEASURE-GENERATOR"
    else:
        h = "OTHER"
    rows.append({"target": tgt, "module": tgt.split("::")[0], "best_measured_on": best["measured_on"][:10],
                 "best_blockers": sorted(bt), "union_blockers": sorted(union),
                 "kill_tests_changed": sorted(bkt), "handling": h, "n_results": len(per[tgt])})

# resume-slice reconciliation
mw = set()
for w in ("mw0", "mw1"):
    mw |= {t["target"] for t in json.load(open(R / f"mutation-workers/{w}.record.json"))["targets"]}

agg = collections.Counter(r["handling"] for r in rows)
bymod = collections.Counter(r["module"] for r in rows)
ktfreq = collections.Counter(f for r in rows for f in r["kill_tests_changed"])

doc = {
 "record": "Step 2 — reconciliation of the 62 MISSING V2.1 targets at fce3d7b7 (owner decision 2026-10-28)",
 "final_head": s["FINAL_HEAD"], "qualifier_snapshot_frozen": s["snapshot"],
 "method": ("proof()'s own why strings (frozen criteria, each vs its result's measured_on); per target the most "
            "benign result; no proof re-run, no rule change, no measurement"),
 "accounting_at_head": {"total": s["TOTAL_TARGETS"], "measured_at_final_head": len(maf),
                        "reused_after_mechanical_proof": len(reuse), "missing": len(miss)},
 "handling_breakdown": dict(agg),
 "by_module": dict(bymod),
 "kill_test_files_implicated": dict(ktfreq.most_common()),
 "resume_slice_reconciliation": {
   "mw0_mw1_measured_at_head": len(mw),
   "of_those_chosen_measured_at_final_head": len(mw & maf),
   "of_those_a_cleaner_reuse_was_chosen_instead": len(mw & reuse),
   "of_those_missing": len(mw & miss),
   "missing_inside_slice": len(miss & mw),
   "missing_outside_slice": len(miss - mw),
   "note": ("the resume campaign measured a 199-target slice at fce3d7b7; 180 were kept as measured_at_final_head, "
            "19 were superseded by a cleaner reused result (a fresh result with a survivor still pending audit does "
            "not win over a clean reusable one). ALL 62 MISSING are OUTSIDE the slice."),
 },
 "why_the_total_differs_from_the_oct20_262_352_plan": [
   "The 262 re-measure / 352 reuse split (memory aisef-trang-thai-2026-10-20) was a PLAN from the read-set/delta "
   "tool (validation/qualification/v21_snapshot_delta.py --read-set): a target whose changed module bytes are not in "
   "the kill tests' MEASURED runtime read-set at head was ruled reuse-OK.",
   "This record is built by the FROZEN proof() of v21_mutation_record.py (criteria_sha256 "
   + s["qualifier"]["criteria_sha256"][:16] + "), which is STATIC and FILE-level: any byte change to the module file "
   "or to a kill-test closure file disqualifies reuse. It does not consult the runtime read-set. The two gates are "
   "different frozen criteria and classify ~20 targets differently in each direction (reuse 352->372, remeasure "
   "262->242).",
   "Under proof() at fce3d7b7: 614 = 372 reusable + 242 must-measure-at-head (= 180 measured_at_final_head + 62 "
   "MISSING). The must-measure set is 242, not 262.",
   "Operationally dominant: the resume campaign completed a 199-target slice of the must-measure set (disk blocker "
   "cut it from 4 workers to 2; see memory 2026-10-21). 180 of the 199 are kept at head; the 62 MISSING are the "
   "must-measure targets the slice did not cover.",
   "The owner's premise 'product snapshot did not change' holds for 46 of the 62 (module byte-identical at head; only "
   "the kill-test closure changed — the owed kill tests in commit fd1a1658, added AFTER the campaign snapshot). It "
   "does NOT hold for 16: their product module changed between the frozen snapshot and head (fd1a1658 PL-7 teardown "
   "hardening; fce3d7b7 calibration re-derivation).",
 ],
 "rows": rows,
}
(R / "MISSING-62-RECONCILIATION.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

# human-readable
L = []
L.append("# V2.1 MISSING-62 reconciliation at fce3d7b7 — owner decision 2026-10-28 (step 2)\n")
L.append(f"**Accounting (614):** {len(maf)} measured_at_final_head + {len(reuse)} reuse + {len(miss)} MISSING. "
         f"Verdict **{s['MUTATION_VERDICT']}**.\n")
L.append("## Handling of the 62 MISSING (by frozen proof()'s own reasons)\n")
for k, v in agg.most_common():
    L.append(f"- **{v} {k}**")
L.append("\n  - REMEASURE-TESTS: module byte-identical at head; kill-test closure changed (owed kill tests, fd1a1658).")
L.append("  - REMEASURE-PRODUCT: product module changed vs every available measurement.\n")
L.append("## Resume-slice reconciliation\n")
rs = doc["resume_slice_reconciliation"]
L.append(f"- mw0+mw1 measured **{rs['mw0_mw1_measured_at_head']}** targets at head "
         f"→ {rs['of_those_chosen_measured_at_final_head']} kept at-head, "
         f"{rs['of_those_a_cleaner_reuse_was_chosen_instead']} superseded by cleaner reuse, "
         f"{rs['of_those_missing']} missing.")
L.append(f"- MISSING inside slice: **{rs['missing_inside_slice']}**; outside slice: **{rs['missing_outside_slice']}**.\n")
L.append("## Why 180+372+62 ≠ the Oct-20 262/352 plan\n")
for p in doc["why_the_total_differs_from_the_oct20_262_352_plan"]:
    L.append(f"- {p}")
L.append("\n## By module\n")
for k, v in bymod.most_common():
    L.append(f"- {v}  `{k}`")
L.append("\n## Kill-test files implicated (file → #MISSING targets whose best result they block)\n")
for f, n in ktfreq.most_common():
    L.append(f"- {n}  `{f}`")
(R / "MISSING-62-RECONCILIATION.md").write_text("\n".join(L) + "\n", encoding="utf-8")

print("handling:", dict(agg))
print("slice:", rs["of_those_chosen_measured_at_final_head"], "at-head,",
      rs["of_those_a_cleaner_reuse_was_chosen_instead"], "reuse,", "outside-slice MISSING:", rs["missing_outside_slice"])
print("wrote MISSING-62-RECONCILIATION.json + .md")
