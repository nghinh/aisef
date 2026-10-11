"""sweep.py [--dry] OUT.jsonl: the T0 sweep (§6.3, as preflight-2/sweep.py and preflight-3): every distinct (null mutant,
kill file) pair of the V2.1 targets of the tree it runs in, run once through the runner's own T0
(run_target(..., t0_only=True)) on one representative target. The JSONL it appends is turned into the committed record
by `validation/v2/execution_order.py --record`. `--dry` prints the pairs and the count only. Resumable: a key already in
OUT is skipped. Run from the repository root, under the workers' environment, on a machine with nothing else heavy."""
import hashlib, json, os, pathlib, sys, time
W = pathlib.Path(os.getcwd())
sys.path.insert(0, str(W))
sys.dont_write_bytecode = True
from validation.v2 import mutation as m  # noqa: E402

args = sys.argv[1:]
dry = "--dry" in args
out = pathlib.Path(args[-1])
pairs: dict[tuple[str, str, str], list[str]] = {}
for t, k in sorted(m.V21_TARGETS.items()):
    rel, func = t.split("::")
    src = (W / rel).read_text(encoding="utf-8")
    h = hashlib.sha256(m.null_mutant(src, func).encode()).hexdigest()
    for f in k:
        pairs.setdefault((rel, h, f), []).append(t)
print(f"{len(pairs)} pairs, {len({(r, h) for r, h, _ in pairs})} null mutants, {len({f for _, _, f in pairs})} kill files", flush=True)
if dry:
    sys.exit(0)
real = m._summary


def summary(text):   # every failing test header of the run, not only the first
    s = real(text)
    if s is not None:
        s["all_failures"] = [f"{a}: {b}" for a, b in m._HEAD.findall(text[:text.rfind("\nRan ")])]
    return s


m._summary = summary
done = {json.loads(x)["key"] for x in out.read_text().splitlines() if x.strip()} if out.exists() else set()
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
        print(f"{rows[0]['outcome'] if rows else 'STOP'} {key} "
              f"{rows[0].get('first') or rows[0].get('why') or '' if rows else r.get('error')} ({rec['seconds']}s)", flush=True)
        if r.get("stopped"):
            print("STOPPED", r["error"])
            sys.exit(3)
