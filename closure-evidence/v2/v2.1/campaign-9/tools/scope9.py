"""scope9.py OUT_DIR: what campaign 9 measures, and why - one row per V2.1 target of the registry at the snapshot
(69b0ea9, 614 targets), and the chain that carries a standing result to it.

Campaign 8 left 528 targets with a result (campaign-8/SCOPE.json: "result_from" says which campaign measured it:
campaign 5 at 289885e, campaign 6 at a770fbb, campaign 7 at 853da4a, campaign 8 at 5df323a). Since then the probe window
changed 16 files of aisef2/, the registry (validation/v2/mutation.py: kill sets, 87 targets added, 1 retired) and the
kill tests. One delta per base, all at the one head (campaign-9/delta-from-<base>/, WITHOUT a read-set: none exists at
this head yet, so every changed file inside mutation.COPY is data whose reading is not measured):

    role    NEW                  the registry holds the target, campaign 8's SCOPE.json did not: no earlier result
            REMEASURE            the delta of the target's own base says re-measure (the target file changed, its kill
                                 set is not the current one, or a file of its kill tests' closure changed)
            STANDS_PROVISIONAL   the delta's rules leave the result standing, but changed files inside mutation.COPY
                                 may be read by its kill tests and their reading is not measured: it stands only until
                                 the read-set at the final head decides (provisional.* says which files and which
                                 changed code the kill closure holds)
            STANDS               the delta's rules leave it standing and no changed file inside COPY is open for it
                                 (none at this head: every standing target is provisional)

A target the registry retired (V21_RETIRED: the function is gone) is not a row of "targets": it is listed under
"retired", with the result it had. Every old row is also checked against the standing record itself
(mutation-workers/c<N>-w*.record.json of the campaign its result comes from): the target file's digest, the kill set
and the mutant count it was measured with, against the file, the registry and the generator at the snapshot. A
difference between the delta's verdict and that record is listed under "disagreements" (empty: none). The delta of
5df323a (the last snapshot: the chain, not a base of any result but the 12 targets of campaign 8) is compared as well.

Writes OUT_DIR/SCOPE.json, OUT_DIR/targets.txt (REMEASURE + NEW, sorted) and OUT_DIR/ESTIMATE.json (the cost of
targets.txt by the rule of campaign-3/tools/make_queue3.py, from the committed T0 sweep records). Reads committed files
only. Run from the repository root:  python -P closure-evidence/v2/v2.1/campaign-9/tools/scope9.py closure-evidence/v2/v2.1/campaign-9"""
import collections
import glob
import hashlib
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from validation.v2 import mutation as m  # noqa: E402

out = pathlib.Path(sys.argv[1])
E = ROOT / "closure-evidence/v2/v2.1"
SNAPSHOT = "69b0ea946922bcd209ffbf5a7bd943ad96080df7"
#: campaign -> (base tag of its delta, the manifest whose snapshot it is)
ORIGINS = {5: "289885e", 6: "a770fbb", 7: "853da4a", 8: "5df323a"}
LABEL = {n: f"campaign {n} ({tag})" for n, tag in ORIGINS.items()}
THIS = "campaign 9 (this campaign)"
FOUND_STATICALLY = "found statically"


def campaign_of(result_from: str) -> int:
    return int(result_from.split()[1])


# --- the inputs, all committed ----------------------------------------------------------------------------------
for n, tag in ORIGINS.items():
    snap = json.loads((E / f"REQUALIFICATION-MANIFEST-{n}.json").read_text())["snapshot"]
    assert snap.startswith(tag), (n, tag, snap)
prev = json.loads((E / "campaign-8/SCOPE.json").read_text())["targets"]
deltas = {}
for n, tag in ORIGINS.items():
    d = json.loads((E / f"campaign-9/delta-from-{tag}/DELTA.json").read_text())
    assert d["head"] == SNAPSHOT and d["base"].startswith(tag) and d["read_set"] is None, (tag, d["head"], d["read_set"])
    deltas[n] = d
records = {}   # campaign -> target -> (record file, entry)
for n in ORIGINS:
    records[n] = {}
    for f in sorted(glob.glob(str(E / f"mutation-workers/c{n}-w*.record.json"))):
        for e in json.loads(pathlib.Path(f).read_text())["targets"]:
            assert e["target"] not in records[n], (n, e["target"])
            records[n][e["target"]] = (pathlib.Path(f).name, e)
merged = json.loads((E / "MUTATION-SUMMARY.json").read_text())["provenance"]   # target -> the worker entry MUTATION.json cites
_worker_records: dict[str, dict] = {}


def merged_entry(t: str) -> tuple[str, dict]:
    """The worker and the entry of it that the merged record (MUTATION.json at FINAL_HEAD 8043387) cites for `t`."""
    w = merged[t]["worker"]
    if w not in _worker_records:
        _worker_records[w] = {e["target"]: e for e in json.loads((E / f"mutation-workers/{w}.record.json").read_text())["targets"]}
    return w, _worker_records[w][t]


registry = m.V21_TARGETS
assert len(registry) == 614 and set(m.V21_RETIRED) == {t for t in prev if t not in registry}, (len(registry), m.V21_RETIRED)


def origin_of(row: dict) -> int:
    """The campaign whose measurement is the standing result of an old target (campaign 8's own re-measures: 8)."""
    return campaign_of(row["result_from"])


# --- one row per target -----------------------------------------------------------------------------------------
rows, disagreements, retired = {}, [], {}
for t in sorted(m.V21_RETIRED):
    n = origin_of(prev[t])
    retired[t] = {"role": "RETIRED", "reasons": ["V21_RETIRED: the function is gone (validation/v2/mutation.py)"],
                  "result_from": LABEL[n], "mutants": records[n][t][1]["mutants"]}
for t, kill in sorted(registry.items()):
    rel, func = t.split("::")
    src = (ROOT / rel).read_text(encoding="utf-8")
    now = len(m.mutants(src, func, m._enum_members(src, ROOT)))
    if t not in prev:
        rows[t] = {"role": "NEW", "reasons": ["no earlier result: the registry at the snapshot holds the target, campaign 8's scope "
                                              "did not (registered in the probe window)"],
                   "result_from_base": None, "result_from": THIS, "mutants": now, "kill_files": list(kill)}
        continue
    n = origin_of(prev[t])
    d = deltas[n]["targets"][t]
    rec_file, rec = records[n][t]
    verdict = str(d["verdict"])
    assert verdict.startswith(("re-measure", f"a {ORIGINS[n]} result can stand")), (t, verdict)
    remeasure = verdict.startswith("re-measure")
    standing = {"record": f"closure-evidence/v2/v2.1/mutation-workers/{rec_file}",
                "source_sha256_is_the_file_at_the_snapshot": rec["source_sha256"] == m.source_digest(src),
                "kill_set_is_the_registry_s": rec["kill_tests"] == list(kill),
                "mutants_measured": rec["mutants"], "mutants_now": now,
                "classes": {k: v for k, v in rec["classes"].items() if v}}
    mw, me = merged_entry(t)   # MUTATION.json may cite an earlier measurement of the same bytes (reused after the proof)
    standing["merged_record_cites"] = {"worker": mw, "measured_on": merged[t]["measured_on"][:7],
                                       "same_source_sha256_and_classes": (me["source_sha256"], me["classes"])
                                       == (rec["source_sha256"], rec["classes"])}
    if not standing["merged_record_cites"]["same_source_sha256_and_classes"]:
        disagreements.append({"target": t, "what": f"MUTATION.json cites {mw}, whose entry differs (source_sha256 or classes) "
                                                   f"from the {rec_file} entry the chain's campaign-8 scope names"})
    unchanged = standing["source_sha256_is_the_file_at_the_snapshot"]
    file_reason = "the target file changed since it was measured" in d["reasons"]
    if remeasure:
        row = {"role": "REMEASURE", "reasons": list(d["reasons"]), "result_from_base": LABEL[n], "result_from": THIS}
        if unchanged == file_reason:   # delta: file changed <-> record: the digest it was measured with is not the file's
            disagreements.append({"target": t, "what": "the delta says the target file "
                                  + ("changed" if file_reason else "did not change") + " since it was measured; the record "
                                  f"{rec_file} holds a source_sha256 that "
                                  + ("is" if unchanged else "is not") + " the file's at the snapshot"})
    else:
        n_data = d["read_set_not_measured"]
        row = {"role": "STANDS_PROVISIONAL" if n_data else "STANDS", "reasons": [],
               "result_from_base": LABEL[n], "result_from": LABEL[n]}
        if n_data:
            statically = sorted({r["path"] for r in deltas[n]["files"]
                                 if any(FOUND_STATICALLY in w for w in r["targets"].get(t, []))})
            row["provisional"] = {
                "until": "a measured read-set of the kill files at the final head (--read-set) decides",
                "changed_files_inside_COPY_not_measured": n_data,
                "found_statically_in_a_kill_closure_file": statically,
                "changed_code_in_the_kill_closure": list(d["other_code_changed"]),
                "also_needs_a_reach_record": bool(d["other_code_changed"]),
                "kill_files": list(kill)}
        if not (unchanged and standing["kill_set_is_the_registry_s"] and rec["mutants"] == now):
            disagreements.append({"target": t, "what": "the delta says the result can stand; the record disagrees",
                                  "file_digest_equal": unchanged, "kill_set_equal": standing["kill_set_is_the_registry_s"],
                                  "mutants_measured": rec["mutants"], "mutants_now": now})
    # the chain: the delta of the last snapshot (5df323a) against the delta of the base the result was measured at
    last = deltas[8]["targets"][t]["verdict"].startswith("re-measure")
    if n != 8 and last and not remeasure:
        disagreements.append({"target": t, "what": f"the delta of {ORIGINS[n]} says the result can stand; the delta of "
                                                   f"5df323a says re-measure"})
    if n != 8 and remeasure and not last:
        row["chain_note"] = (f"the delta of 5df323a would leave it standing; its result is from {LABEL[n]} and the delta of "
                             f"that base says re-measure: the base decides")
    rows[t] = {**row, "mutants": now, "kill_files": list(kill), "standing": standing}

# --- totals ------------------------------------------------------------------------------------------------------
role = collections.Counter(r["role"] for r in rows.values())
assert sum(role.values()) == 614 and set(role) <= {"NEW", "REMEASURE", "STANDS_PROVISIONAL", "STANDS"}, role
run = sorted(t for t, r in rows.items() if r["role"] in ("NEW", "REMEASURE"))
mut = {k: sum(r["mutants"] for r in rows.values() if r["role"] == k) for k in role}
by_base = {LABEL[n]: dict(collections.Counter(r["role"] for r in rows.values() if r["result_from_base"] == LABEL[n]))
           for n in ORIGINS}
why = collections.Counter()
for t in run:
    r = rows[t]
    if r["role"] == "NEW":
        why["NEW: no earlier result"] += 1
    elif "the target file changed since it was measured" in r["reasons"]:
        why["REMEASURE: the target file changed"] += 1
    elif any(x.startswith("its kill set is not the current one") for x in r["reasons"]):
        why["REMEASURE: file unchanged, kill set changed"] += 1
    else:
        why["REMEASURE: file and kill set unchanged, a file of the kill tests' closure changed"] += 1
prov = [r for r in rows.values() if r["role"] == "STANDS_PROVISIONAL"]
reach = [r for r in prov if r["provisional"]["also_needs_a_reach_record"]]
provisional = {"targets": len(prov), "mutants": sum(r["mutants"] for r in prov),
               "with_changed_code_in_the_kill_closure": {"targets": len(reach), "mutants": sum(r["mutants"] for r in reach)},
               "note": "the read-set at the final head decides the data; a target whose kill closure holds changed code of "
                       "aisef2/ (also_needs_a_reach_record) also needs the reach record of that head "
                       "(validation/v21/reach.py: does a kill file EXECUTE a changed function): the delta counts that code "
                       "as reported, not as a ground"}
out.mkdir(parents=True, exist_ok=True)
(out / "SCOPE.json").write_text(json.dumps({
    "record": "AISEF V2.1 - campaign 9 scope: which targets are measured, and why", "head": SNAPSHOT, "read_set": None,
    "delta_bases": {LABEL[n]: tag for n, tag in ORIGINS.items()},
    "harness_changed_since_each_base": {LABEL[n]: deltas[n]["harness_changed"] for n in ORIGINS},
    "totals": {"registry_targets": len(registry), "roles": dict(role), "mutants_by_role": mut,
               "registry_mutants": sum(r["mutants"] for r in rows.values()),
               "to_measure_now": {"targets": len(run), "mutants": sum(rows[t]["mutants"] for t in run)},
               "by_base_of_the_previous_result": by_base, "why_measured": dict(why),
               "provisional": provisional, "retired": len(retired), "disagreements": len(disagreements)},
    "targets": rows, "retired": retired, "disagreements": disagreements}, indent=1, ensure_ascii=False) + "\n")
(out / "targets.txt").write_text("".join(t + "\n" for t in run))

# --- the cost of targets.txt: campaign-3/tools/make_queue3.py's rule, from the committed T0 sweep records ---------
# cost of a target = mutants x the sum of the T0 seconds of its kill files on its null mutant (the cost of a surviving
# mutant: a killed one pays less); a (null mutant, file) pair no record holds counts the median measured file's seconds.
#   literal   exactly that rule (make_queue3.py)
#   by_file   a pair no record holds for THIS null mutant counts, in this order: the seconds of the same kill file on an
#             earlier null mutant of the same module; the median seconds of the same kill file on any module; the median
# The sweep of the snapshot (T0-SWEEP-9) does not exist yet: the queue is written from it by make_queue3.py.
sweeps = sorted(glob.glob(str(E / "T0-SWEEP*.json")),
                key=lambda p: int(pathlib.Path(p).stem.rpartition("-")[2]) if pathlib.Path(p).stem != "T0-SWEEP" else 1)


def t0_rows(path: str) -> dict:
    out_ = {}
    for r in json.loads(pathlib.Path(path).read_text())["rows"]:
        row = [x for x in r["rows"] if x.get("role") == "t0"]
        if row:
            out_[(r["module"], r["null"], r["file"])] = row[0]["seconds"]
    return out_


last_record = t0_rows(sweeps[-1])   # `literal` is make_queue3.py run on the latest record (T0-SWEEP-8.json, cumulative)
t0, same_module_file, same_file = {}, {}, collections.defaultdict(list)
for rec in sweeps:   # T0-SWEEP.json (1), -2 ... -8: a later record wins
    for (mod, nul, f), sec in t0_rows(rec).items():
        t0[(mod, nul, f)] = sec
        same_module_file[(mod, f)] = sec
for (mod, nul, f), sec in t0.items():
    same_file[f].append(sec)
median = statistics.median(t0.values())
median_last = statistics.median(last_record.values())
cost = {"literal": 0.0, "by_file": 0.0}
guessed_at_median = 0.0   # seconds of `by_file` that stand on the median because no record holds the kill file
no_record = collections.Counter()
tier = collections.Counter()
per_target = {}
for t in run:
    rel, func = t.split("::")
    src = (ROOT / rel).read_text(encoding="utf-8")
    null = hashlib.sha256(m.null_mutant(src, func).encode()).hexdigest()
    n_mut = rows[t]["mutants"]
    chain = {"literal": 0.0, "by_file": 0.0}
    for f in registry[t]:
        chain["literal"] += last_record.get((rel, null, f), median_last)
        if (rel, null, f) in t0:
            chain["by_file"] += t0[(rel, null, f)]
            tier["a T0 row on this null mutant"] += 1
        else:
            if (rel, f) in same_module_file:
                chain["by_file"] += same_module_file[(rel, f)]
                tier["no row on this null mutant; the same file on an earlier null of the module"] += 1
            elif f in same_file:
                chain["by_file"] += statistics.median(same_file[f])
                tier["no row for the module; the median of the same file on other modules"] += 1
            else:
                chain["by_file"] += median
                guessed_at_median += n_mut * median
                no_record[f] += 1
                tier["a kill file no record holds: the median"] += 1
    for k in cost:
        cost[k] += n_mut * chain[k]
    per_target[t] = {"mutants": n_mut, "kill_files": len(registry[t]),
                     "chain_seconds_literal": round(chain["literal"], 1), "chain_seconds_by_file": round(chain["by_file"], 1),
                     "cost_seconds_literal": round(n_mut * chain["literal"]), "cost_seconds_by_file": round(n_mut * chain["by_file"])}
# calibration: what the same bound came to in the campaigns that ran (queue.tsv: the bound make_queue3.py wrote;
# worker-hours: the workers' started/finished stamps, a worker being busy until the queue is empty)
import datetime as dt  # noqa: E402


def hours(a: str, b: str) -> float:
    f = lambda x: dt.datetime.strptime(x.strip(), "%Y-%m-%dT%H:%M:%SZ")   # noqa: E731
    return (f(b) - f(a)).total_seconds() / 3600


calibration = {}
for n in (3, 4, 5, 6, 7, 8):
    r = E / f"campaign-{n}/results"
    q = [x.split("\t") for x in (r / "queue.tsv").read_text().splitlines()]
    wh = sum(hours((w).read_text(), (w.with_suffix(".finished")).read_text()) for w in sorted(r.glob(f"c{n}-w*.started")))
    bound = sum(float(x[3]) for x in q) / 3600
    calibration[f"campaign {n}"] = {
        "targets": len(q), "mutants": sum(int(x[1]) for x in q), "queue_bound_worker_hours": round(bound, 1),
        "wall_hours": round(hours((r / "campaign.started").read_text(), (r / "campaign.finished").read_text()), 1),
        "worker_hours_run": round(wh, 1), "run_over_bound": round(wh / bound, 3),
        "longest_target": {"target": q[0][0], "bound_hours": round(float(q[0][3]) / 3600, 1)}}
ratio = calibration["campaign 5"]["run_over_bound"]   # the one campaign of the size of this one (528 targets, 13,566 mutants)
bound_h = cost["by_file"] / 3600
top = sorted(per_target.items(), key=lambda kv: -kv[1]["cost_seconds_by_file"])[:8]
c5 = calibration["campaign 5"]
longest_ratio = c5["wall_hours"] / c5["longest_target"]["bound_hours"]   # its longest target ran as long as the campaign
longest_h = top[0][1]["cost_seconds_by_file"] / 3600 * longest_ratio
(out / "ESTIMATE.json").write_text(json.dumps({
    "record": "AISEF V2.1 - campaign 9: the cost of targets.txt by the rule of campaign-3/tools/make_queue3.py",
    "rule": "cost of a target = mutants x sum of the T0 seconds of its kill files on its null mutant: an upper bound "
            "(a killed mutant pays less)",
    "sweep_records": [pathlib.Path(p).name for p in sweeps], "t0_pairs_in_the_records": len(t0),
    "median_file_seconds": {"all_records": median, "latest_record": median_last},
    "targets": len(run), "mutants": sum(rows[t]["mutants"] for t in run),
    "kill_file_pairs_of_the_targets": sum(tier.values()), "pairs_by_basis": dict(tier),
    "upper_bound_worker_hours": {"literal": round(cost["literal"] / 3600, 1), "by_file": round(bound_h, 1),
                                 "by_file_of_which_guessed_at_the_median": round(guessed_at_median / 3600, 1)},
    "kill_files_no_record_holds": dict(sorted(no_record.items())),
    "literal_is": "make_queue3.py's rule on the latest record alone (T0-SWEEP-8.json, which is cumulative)",
    "calibration": calibration,
    "expected": {"basis": "by_file upper bound x campaign 5's run/bound ratio (the only earlier campaign of this size)",
                 "run_over_bound": ratio, "worker_hours": round(bound_h * ratio, 1),
                 "wall_hours_balanced_by_workers": {str(w): round(bound_h * ratio / w, 1) for w in (4, 5)},
                 "longest_target_wall_hours_if_it_runs_as_in_campaign_5": round(longest_h, 1),
                 "wall_hours_by_workers": {str(w): round(max(bound_h * ratio / w, longest_h), 1) for w in (4, 5)},
                 "longest_targets_by_file_bound_hours": {t: round(v["cost_seconds_by_file"] / 3600, 1) for t, v in top},
                 "note": "the wall is bounded below by the longest target: in campaign 5 the longest (bound 51.1 h) ran "
                         "24.3 h, the campaign's wall"},
    "per_target": per_target}, indent=1, ensure_ascii=False) + "\n")
print(f"registry {len(registry)} | roles {dict(role)} | mutants by role {mut}")
print(f"to measure now: {len(run)} targets, {sum(rows[t]['mutants'] for t in run)} mutants | retired {len(retired)} | "
      f"disagreements {len(disagreements)}")
print("why:", dict(why))
print("by base:", by_base)
print(f"upper bound: literal {cost['literal'] / 3600:.1f} worker-hours, by file {bound_h:.1f}; pairs: {dict(tier)}")
print(f"expected {bound_h * ratio:.1f} worker-hours (ratio {ratio}); balanced wall at 4/5 workers: {bound_h * ratio / 4:.1f} / "
      f"{bound_h * ratio / 5:.1f} h; the longest target alone {longest_h:.1f} h")
print("provisional:", provisional)
