"""isolation_compare.py OUT.json ALONE CONCURRENT...: the isolation proof of the V2.1 campaign (owner B-03b: "Chỉ chạy đồng
thời khi cơ chế cách ly và quyền sở hữu tài nguyên đã được kiểm chứng"). ALONE is a worker that ran the sample targets
by itself; each CONCURRENT worker ran the SAME targets at the same time as the others, each in its own worktree, HOME,
XDG_* and TMPDIR. Isolation holds when, for every target, every concurrent worker's per-mutant verdicts (killed,
timed_out) equal ALONE's, no run errored, no cleanup signalled a process (each signal would carry its ownership proof),
and each worker's owned_run record shows no escaped process and no orphan; the operator's real OpenCode store is
compared by the caller (store_stat before/after)."""
import json, pathlib, sys

D = pathlib.Path("/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21")
out_path, alone, conc = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3:]


def record(w):
    return {t["target"]: t for t in json.loads((D / w / "closure-evidence/v2/v2.1/MUTATION.json").read_text())["targets"]}


def verdicts(t):
    return [(r["mutant"], r["killed"], bool(r.get("timed_out"))) for r in t.get("results", [])]


base = record(alone)
problems, rows = [], {}
for w in [alone, *conc]:
    rec = record(w)
    owned = json.loads((D / f"{w}.owned.json").read_text()) if (D / f"{w}.owned.json").exists() else {}
    if not owned:
        problems.append(f"{w}: no owned_run record")
    for key in ("escaped", "residual", "owned_after", "harness_orphans_after"):
        if owned.get(key):
            problems.append(f"{w}: owned_run {key} = {owned[key]}")
    for tg, t in rec.items():
        if t.get("error"):
            problems.append(f"{w} {tg}: error {t['error'][:200]}")
        if any(r.get("cleanup") for r in t.get("results", [])):
            problems.append(f"{w} {tg}: a cleanup signalled a process: {[r.get('cleanup') for r in t['results'] if r.get('cleanup')][:2]}")
        if w != alone and verdicts(t) != verdicts(base.get(tg, {})):
            problems.append(f"{w} {tg}: verdicts differ from the worker that ran alone")
    if set(rec) != set(base):
        problems.append(f"{w}: targets {sorted(set(rec) ^ set(base))} differ from the alone worker's")
    rows[w] = {"targets": len(rec), "mutants": sum(len(t.get("results", [])) for t in rec.values()),
               "killed": sum(1 for t in rec.values() for r in t.get("results", []) if r["killed"]),
               "baseline_failures": {tg: t.get("baseline") for tg, t in rec.items() if t.get("error")},
               "timeouts": sum(1 for t in rec.values() for r in t.get("results", []) if r.get("timed_out")),
               "owned": {k: owned.get(k) for k in ("exit", "owned_before", "owned_at_exit", "owned_after", "escaped", "residual", "released_empty", "harness_orphans_before", "harness_orphans_after")}}
doc = {"alone": alone, "concurrent": conc, "workers": rows, "problems": problems, "isolation": "HOLDS" if not problems else "FAILS"}
out_path.write_text(json.dumps(doc, indent=1) + "\n")
print(json.dumps({k: doc[k] for k in ("workers", "problems", "isolation")}, indent=1)[:4000])
