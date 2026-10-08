"""make_queue.py ROOT SWEEP_RECORD OUT [EXCLUDE...]: the campaign-2 queue — every V2.1 target of ROOT not excluded,
longest expected first (longest-processing-time order, so the last targets to start are short ones): expected cost =
mutants x the sum of the T0 seconds of its kill files on its null mutant (what a surviving mutant pays; a killed one
pays less). Prints the total and a tsv beside OUT."""
import hashlib, importlib.util, json, pathlib, sys
root, rec, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
exclude = set(sys.argv[4:])
spec = importlib.util.spec_from_file_location("mutation", root / "validation/v2/mutation.py")
m = importlib.util.module_from_spec(spec); sys.modules["mutation"] = m; spec.loader.exec_module(m)
t0 = {}
for r in json.loads(rec.read_text())["rows"]:
    row = [x for x in r["rows"] if x.get("role") == "t0"]
    t0[(r["module"], r["null"], r["file"])] = row[0]["seconds"]
rows = []
for target, kill in m.V21_TARGETS.items():
    if target in exclude:
        continue
    rel, func = target.split("::")
    src = (root / rel).read_text(encoding="utf-8")
    null = hashlib.sha256(m.null_mutant(src, func).encode()).hexdigest()
    n = len(m.mutants(src, func, m._enum_members(src, root)))
    chain = sum(t0[(rel, null, f)] for f in kill)
    rows.append((n * chain, n, round(chain, 1), target))
rows.sort(key=lambda r: (-r[0], r[3]))
out.write_text("".join(r[3] + "\n" for r in rows))
out.with_suffix(".tsv").write_text("".join(f"{r[3]}\t{r[1]}\t{r[2]}\t{round(r[0])}\n" for r in rows))
print(f"{len(rows)} targets, {sum(r[1] for r in rows)} mutants, upper bound {sum(r[0] for r in rows) / 3600:.1f} worker-hours")
