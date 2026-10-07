"""(adapted for lane c2tests: estimate source; run at the lane's final HEAD) T0 sweep (§6.3 widened, feasibility review): every distinct (null mutant, kill file) pair of the V2.1 targets, run
once through the runner's own T0 (run_target(..., t0_only=True)) on one representative target, with every failing test
header captured (not only the first). `--dry` prints the pairs and the preflight-time estimate only.

    sweep.py [--dry] [--only FILE...] OUT.jsonl
"""
import hashlib, json, os, pathlib, sys, time
W = pathlib.Path(os.getcwd())
sys.path.insert(0, str(W))
sys.dont_write_bytecode = True
from validation.v2 import mutation as m
args = sys.argv[1:]
dry = "--dry" in args
only = args[args.index("--only") + 1:-1] if "--only" in args else None
out = pathlib.Path(args[-1])
# estimate from the 6ab3c09 sweep's own seconds per file (scratchpad/m21 is not read)
pre = {}
for x in open("/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/runner-v2/impl/sweep-pre.jsonl"):
    r = json.loads(x)
    pre[r["file"]] = {"seconds": max(pre.get(r["file"], {}).get("seconds", 0), r["seconds"])}
pairs = {}
for t, k in sorted(m.V21_TARGETS.items()):
    rel, func = t.split("::")
    src = (W / rel).read_text(encoding="utf-8")
    h = hashlib.sha256(m.null_mutant(src, func).encode()).hexdigest()
    for f in k:
        if only is None or f in only:
            pairs.setdefault((rel, h, f), []).append(t)
est = sum(pre.get(f, {}).get("seconds", 60) for (_, _, f) in pairs)
print(f"{len(pairs)} pairs, {len({(r, h) for r, h, _ in pairs})} nulls, estimate {est / 3600:.2f} h", flush=True)
if dry:
    sys.exit(0)
real = m._summary
def summary(text):
    s = real(text)
    if s is not None:
        s["all_failures"] = [f"{a}: {b}" for a, b in m._HEAD.findall(text[:text.rfind("\nRan ")])]
    return s
m._summary = summary
done = {json.loads(x)["key"] for x in out.read_text().splitlines()} if out.exists() else set()
with m.tempfile.TemporaryDirectory(prefix="aisef-pristine-sweep-") as p:
    pristine = m._pristine(W, pathlib.Path(p) / "tree")
    for (rel, h, f), targets in sorted(pairs.items()):
        key = f"{rel}|{h[:16]}|{f}"
        if key in done:
            continue
        t0 = time.monotonic()
        r = m.run_target(W, targets[0], [f], pristine, t0_only=True)
        rows = [{k: v for k, v in x.items() if k not in ("tail",)} for x in r.get("t0", [])]
        orig = [{k: v for k, v in x.items() if k in ("outcome", "why", "first")} for x in r.get("original", [])]
        rec = {"key": key, "module": rel, "null": h, "file": f, "targets": targets, "rows": rows, "original": orig,
               "error": r.get("error") if r.get("stopped") or orig else None, "seconds": round(time.monotonic() - t0, 1)}
        with out.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(f"{rows[0]['outcome'] if rows else 'STOP'} {key} {rows[0].get('first') or rows[0].get('why') or '' if rows else r.get('error')} ({rec['seconds']}s)", flush=True)
        if r.get("stopped"):
            print("STOPPED", r["error"]); sys.exit(3)
