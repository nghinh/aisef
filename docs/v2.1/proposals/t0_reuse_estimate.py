"""t0_reuse_estimate.py SWEEP QUEUE_TSV QUEUE_ALL_TSV FORECAST PILOT_DIR: the numbers of T0-BASELINE-REUSE.md §2, §3 and
§8. Read-only; prints only.

SWEEP: closure-evidence/v2/v2.1/T0-SWEEP-2.json (one T0 row per distinct (null mutant, kill file) pair, `targets` the
targets that hold it). QUEUE_TSV / QUEUE_ALL_TSV: campaign-2/tools/queue.tsv (the 457 queued targets) and queue-all.tsv
(all 466): target, mutants, chain = the sum of its kill files' sweep T0 seconds, in queue order. FORECAST:
pilot/attempt-2/forecast.json (`ord` per_target: the T0 load, cost ratios and survivor rate, as forecast.py derives
them). PILOT_DIR: pilot/attempt-2 (its lane records).

One basis throughout, forecast.py's: a target's T0 costs L x chain, where L = the pilot's median of (its T0 rows'
seconds + overhead_s) / chain, so L already holds the overhead and sec_p below is the sweep's `seconds` alone.
  sec_p            pair p's sweep T0 seconds; n_p = the queued targets holding p
  today            L * sum_p n_p * sec_p
  one per pair     L * sum_p sec_p                     (campaign-wide sharing: excluded by the conditions of §4)
  one per worker   L * sum_p min(n_p, 4) * sec_p       (an upper bound of the cost with an unbounded window)
  window h         a model of the queue: 4 workers take targets in queue order, each when free, a target costing
                   cost(t) = chain * L + n * (s * S + (1 - s) * K) * chain; a (target, file) T0 is saved (L * sec_p)
                   when the same worker ran an own T0 of the same pair that started at most h hours earlier (a reused
                   row is never a source). The schedule is the no-reuse one.
  phi              from the pilot's table-order lanes: the share of the sweep T0 seconds of (target, file) pairs that
                   keep their saving under §7 — a file needs a close-out run (its own T0, at the end) unless a mutant's
                   whole-file run of it PASSed; under the stricter trip it also pays its own T0 at its first FAIL.
  net window h     saved(h) * (1 - f) * phi, f = 0.1 the sentinel fraction; the cascade is listed beside it (§6 R8).
"""
import json
import pathlib
import statistics
import sys

sweep, queue_tsv, queue_all_tsv, forecast, pilot = (pathlib.Path(a) for a in sys.argv[1:6])
rows = json.loads(sweep.read_text(encoding="utf-8"))["rows"]


def tsv(p):
    return [(c[0], int(c[1]), float(c[2])) for c in (ln.split("\t") for ln in p.read_text(encoding="utf-8").splitlines())]


queue, queue_all = tsv(queue_tsv), tsv(queue_all_tsv)
fc = json.loads(forecast.read_text(encoding="utf-8"))["ord"]
pt = fc["per_target"]   # forecast.py's constants, unrounded, so the totals are forecast.json's
L = statistics.median(x["t0_load"] for x in pt)
s = sum(x["survived"] for x in pt) / sum(x["n"] for x in pt)
K = sum(x["k_ratio"] * x["killed"] for x in pt if x["k_ratio"]) / sum(x["killed"] for x in pt)
S = statistics.median(x["s_ratio"] for x in pt if x["s_ratio"] is not None)
F = 0.1


def cost(n, chain):
    return chain * L + n * (s * S + (1 - s) * K) * chain


queued = {t for t, _, _ in queue}
pairs = {}   # target -> [(pair key, sec_p)]
held = {}    # pair key -> (n_p, sec_p)
for r in rows:
    t0 = [x for x in r["rows"] if x.get("role") == "t0"]
    assert len(t0) == 1 and t0[0]["outcome"] == "PASS" and not t0[0].get("residue") and not t0[0].get("leaked"), r["key"]
    sec = t0[0]["seconds"]
    ts = [t for t in r["targets"] if t in queued]
    held[r["key"]] = (len(ts), sec)
    for t in ts:
        pairs.setdefault(t, []).append((r["key"], sec))
for t, _, chain in queue:   # the queue's chain is the sum of its pairs' sweep seconds, rounded to 0.1 s
    assert abs(round(sum(sec for _, sec in pairs[t]), 1) - chain) < 0.11, t
used = {k: v for k, v in held.items() if v[0]}
today = L * sum(n * sec for n, sec in used.values())
one = L * sum(sec for _, sec in used.values())
per_w = L * sum(min(n, 4) * sec for n, sec in used.values())
total = sum(cost(n, c) for _, n, c in queue)
total_all = sum(cost(n, c) for _, n, c in queue_all)
t0_all = L * sum(c for _, _, c in queue_all)
print(f"queued targets {len(queue)}, pairs held {len(used)} of {len(rows)}, (target, kill file) T0 runs "
      f"{sum(n for n, _ in used.values())}; pairs held by one target {sum(1 for n, _ in used.values() if n == 1)}")
print(f"L = {L:.3f}, s = {s:.3f}, K = {K:.3f}, S = {S:.3f}; 457 queued: T0 {today / 3600:.2f} h of a model total "
      f"{total / 3600:.1f} h ({today / total:.1%}); "
      f"466: T0 {t0_all / 3600:.2f} h of {total_all / 3600:.1f} h ({t0_all / total_all:.1%}; forecast.json "
      f"{fc['forecast']['pilot']['worker_hours']} h)")
print(f"today {today / 3600:.2f} h | one per pair {one / 3600:.2f} h (saves {(today - one) / 3600:.2f}) | "
      f"one per worker <= {per_w / 3600:.2f} h (saves >= {(today - per_w) / 3600:.2f})")

# the pilot's table-order lanes: which (target, file) pairs a reuse would leave with no whole-file PASS of their own
sec_of = {(t, r["file"]): x["seconds"] for r in rows for x in r["rows"] if x.get("role") == "t0" for t in r["targets"]}
phi = {}
for mode in ("ord", "decl"):
    n = {"pairs": 0, "no run": 0, "no PASS": 0, "PASS only": 0, "PASS and FAIL": 0}
    sec = dict.fromkeys(n, 0.0)
    trips, zero = [], []
    for p in sorted(pilot.glob(f"l*-{mode}.record.json")):
        for t in json.loads(p.read_text(encoding="utf-8"))["targets"]:
            for f in t["kill_tests"]:
                every = [x for m in t["results"] for x in m.get("files", []) if x["file"] == f]
                # a whole-file run judged against the reference: a mutant's row, a fresh re-measure, a fresh control
                whole = [x for x in every if "role" not in x or (x.get("role") == "control" and x.get("fresh"))]
                kind = ("no PASS" if not any(x["outcome"] == "PASS" for x in whole) else
                        "PASS only" if all(x["outcome"] == "PASS" for x in whole) else "PASS and FAIL")
                for k in ("pairs", kind) + (("no run",) if not every else ()):
                    n[k] += 1
                    sec[k] += sec_of[(t["target"], f)]
                if not every:
                    zero.append(f"{t['target']} x {f.split('/')[-1]}")
                # the trip of §7: a whole-file outcome other than PASS or FAIL, a null control that did not pass,
                # residue or a leftover on any run of the file
                trips += [(t["target"], f) for x in every if (("role" not in x or x.get("role") == "unconfirmed")
                          and x["outcome"] not in ("PASS", "FAIL")) or (x.get("role") == "control" and
                          x["outcome"] != "PASS") or x.get("residue") or x.get("leaked")]
    phi[mode] = ((sec["PASS only"] + sec["PASS and FAIL"]) / sec["pairs"], sec["PASS only"] / sec["pairs"])
    print(f"pilot {mode}: " + ", ".join(f"{k} {n[k]} ({sec[k]:.0f} s, {sec[k] / sec['pairs']:.1%})" for k in n)
          + f"; trip events {len(trips)}; phi {phi[mode][0]:.3f} (close-out), {phi[mode][1]:.3f} (strict trip)")
    if mode == "ord":
        print("  no run besides T0:", "; ".join(zero))
phi_n, phi_s = phi["ord"]

for h in (1, 2, 6, 12, 24, float("inf")):
    free, own, saved, n_reused, n_runs = [0.0] * 4, {}, 0.0, 0, 0
    reusers = {}   # (worker, pair, the source target) -> the targets that reused that source row
    for t, n, chain in queue:
        w = min(range(4), key=lambda i: (free[i], i))
        for key, sec in pairs[t]:
            n_runs += 1
            last = own.get((w, key))
            if last is not None and free[w] - last[0] <= h * 3600:
                saved, n_reused = saved + L * sec, n_reused + 1
                reusers.setdefault((w, key, last[1]), []).append(t)
            else:
                own[(w, key)] = (free[w], t)
        free[w] += cost(n, chain)
    print(f"window {h} h: reused {n_reused}/{n_runs}, saves {saved / 3600:.2f} h ({saved / today:.0%} of T0); "
          f"with sentinels {(1 - F) * saved / 3600:.2f} h; net of the close-out {(1 - F) * saved * phi_n / 3600:.2f} h, "
          f"strict trip {(1 - F) * saved * phi_s / 3600:.2f} h; makespan of the model {max(free) / 3600:.1f} h")
    if h == 6:
        c = {t: cost(n, ch) for t, n, ch in queue}
        k = sorted(len(v) for v in reusers.values())
        by_pair, by_target = {}, {}
        for (_, key, src), v in reusers.items():
            by_pair.setdefault(key, set()).update(v)
            by_target.setdefault(src, set()).update(v)
        rc, pc, tc = (sorted(sum(c[t] for t in set(v)) / 3600 for v in d.values()) for d in (reusers, by_pair, by_target))
        print(f"  6 h: {len(reusers)} source rows feed {sum(k)} reuses; reusers per source median {statistics.median(k)}, "
              f"max {k[-1]}; P(no sentinel at the median) {(1 - F) ** statistics.median(k):.2f}; expected sources "
              f"with >= 1 sentinel {sum(1 - (1 - F) ** x for x in k):.1f}")
        print(f"  cascade, re-measuring the reusers (h): of one source row median {statistics.median(rc):.2f}, mean "
              f"{statistics.mean(rc):.2f}, max {rc[-1]:.2f}; of one pair (every worker) median {statistics.median(pc):.2f}, "
              f"max {pc[-1]:.2f}; of one source target ({len(tc)} of them) median {statistics.median(tc):.2f}, mean "
              f"{statistics.mean(tc):.2f}, max {tc[-1]:.2f}; mean target {total / len(queue) / 3600:.2f}")
        net = (1 - F) * saved * phi_n / 3600
        print(f"  break-even: {net / statistics.mean(tc):.1f} source targets voided (old C7) or "
              f"{net / statistics.mean(rc):.1f} invalid source rows cancel the {net:.2f} h net of the close-out")


def ref(x):
    return (x["outcome"], x.get("ran"), x.get("skipped", 0), x.get("expected_failures", 0),
            x.get("unexpected_successes", 0), tuple(x.get("skipped_tests", [])), x.get("first_test"))


own = {}   # (target, file) -> [the sweep's row of its pair, then each pilot lane's row]
for r in rows:
    for t in r["targets"]:
        own[(t, r["file"])] = [x for x in r["rows"] if x.get("role") == "t0"]
seen = set()
for p in sorted(pilot.glob("l*-*.record.json")):
    for t in json.loads(p.read_text(encoding="utf-8"))["targets"]:
        for x in t.get("t0", []):
            own[(t["target"], x["file"])].append(x)
            seen.add((t["target"], x["file"]))
runs = [own[k] for k in sorted(seen)]
print(f"pilot: {len(runs)} (target, file) pairs, {sorted({len(v) for v in runs})} T0 rows each (sweep + lanes); "
      f"reference identical in all rows {sum(len({ref(x) for x in v}) == 1 for v in runs)}, "
      f"tail_sha256 identical {sum(len({x['tail_sha256'] for x in v}) == 1 for v in runs)}")
for k in sorted(seen):
    if len({x["tail_sha256"] for x in own[k]}) > 1:
        print("  tail differs:", k, "references", "identical" if len({ref(x) for x in own[k]}) == 1 else "DIFFER")
