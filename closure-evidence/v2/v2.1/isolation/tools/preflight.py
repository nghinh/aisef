"""preflight.py WORKTREE OUT.json [PHASE]: every distinct kill-test file of the phase's targets, run once on the
UNMUTATED tree exactly as validation/v2/mutation.py runs a kill set (its COPY tree, its ProcessRange, its env without
PYTHONPATH, failfast, its TIMEOUT, its cleanup authority) — before a long campaign, so a configuration error shows in
minutes, not after hours. Writes per file: passed, seconds, timed out, leaked; and per target: its kill set's baseline
verdict and an estimated cost (mutants x the first kill file's seconds). Run it under the worker env (env -i, PATH
without opencode, scratch HOME/XDG/TMPDIR)."""
import json, pathlib, shutil, sys, tempfile, time

W, OUT = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
PHASE = sys.argv[3] if len(sys.argv) > 3 else "V2.1"
sys.path.insert(0, str(W))
from validation.v2 import mutation as m          # noqa: E402
ca = m.ca                                          # mutation.py's own cleanup authority

targets = m.PHASE_TARGETS[PHASE]
files = sorted({f for k in targets.values() for f in k})
rows = {}
with tempfile.TemporaryDirectory() as t:
    work = pathlib.Path(t) / "tree"
    for part in m.COPY:
        src = W / part
        if src.is_dir():
            shutil.copytree(src, work / part, ignore=shutil.ignore_patterns("__pycache__"))
        elif src.exists():
            (work / part).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, work / part)
    boundary = ca.establish(work)
    for f in files:
        m._FAILED.clear(); m._TIMED_OUT.clear()
        t0 = time.monotonic()
        try:
            ok, leaked = m._run_tests(work, [f], boundary)
            err = None
        except ca.Unproven as e:
            ok, leaked, err = False, 0, f"UNPROVEN {e}"
        rows[f] = {"passed": ok, "seconds": round(time.monotonic() - t0, 1), "timed_out": bool(m._TIMED_OUT),
                   "leaked": leaked, "failed": list(m._FAILED)[:1], "error": err}
        print(f"{'OK  ' if ok and not leaked else 'FAIL'} {rows[f]['seconds']:7.1f}s {f}", flush=True)
src_cache = {}
per_target = {}
for tg, kill in sorted(targets.items()):
    rel, func = tg.split("::")
    if rel not in src_cache:
        src_cache[rel] = (W / rel).read_text(encoding="utf-8")
    n = len(m.mutants(src_cache[rel], func, m._enum_members(src_cache[rel], W)))
    base = all(rows[f]["passed"] and not rows[f]["leaked"] for f in kill)
    per_target[tg] = {"kill_tests": kill, "mutants": n, "baseline_passes": base,
                      "est_seconds": round(n * rows[kill[0]]["seconds"], 1)}
doc = {"phase": PHASE, "worktree": str(W), "timeout_s": m.TIMEOUT, "files": rows, "targets": per_target,
       "failing_files": [f for f, r in rows.items() if not r["passed"] or r["leaked"]],
       "targets_whose_baseline_fails": [t for t, r in per_target.items() if not r["baseline_passes"]],
       "mutants": sum(r["mutants"] for r in per_target.values()),
       "est_worker_hours": round(sum(r["est_seconds"] for r in per_target.values()) / 3600, 1)}
OUT.write_text(json.dumps(doc, indent=1) + "\n")
print(json.dumps({k: doc[k] for k in ("failing_files", "targets_whose_baseline_fails", "mutants", "est_worker_hours")}, indent=1))
