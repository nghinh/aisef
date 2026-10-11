"""make_queue3.py ROOT SWEEP_RECORD[,SWEEP_RECORD...] OUT TARGETS_FILE: the campaign-3 queue — the targets listed in
TARGETS_FILE (one per line; each must be a V2.1 target of ROOT), longest expected first. Expected cost per target =
mutants x the sum of the T0 seconds of its kill files on its null mutant (what a surviving mutant pays; a killed one
pays less), from the sweep records; a (null mutant, file) pair no sweep measured counts the median measured file's
seconds and is listed. Prints the total and writes OUT (names) and OUT.tsv (target, mutants, chain seconds, bound)."""
import hashlib, importlib.util, json, pathlib, statistics, sys
root, recs, out, listed = pathlib.Path(sys.argv[1]), sys.argv[2].split(","), pathlib.Path(sys.argv[3]), pathlib.Path(sys.argv[4])
want = [x for x in listed.read_text().split("\n") if x.strip()]
spec = importlib.util.spec_from_file_location("mutation", root / "validation/v2/mutation.py")
m = importlib.util.module_from_spec(spec); sys.modules["mutation"] = m; spec.loader.exec_module(m)
t0 = {}
for rec in recs:
    for r in json.loads(pathlib.Path(rec).read_text())["rows"]:
        row = [x for x in r["rows"] if x.get("role") == "t0"]
        if row:
            t0[(r["module"], r["null"], r["file"])] = row[0]["seconds"]
median = statistics.median(t0.values())
unknown = [t for t in want if t not in m.V21_TARGETS]
assert not unknown, f"not V2.1 targets: {unknown}"
rows, guessed = [], []
for target in want:
    rel, func = target.split("::")
    src = (root / rel).read_text(encoding="utf-8")
    null = hashlib.sha256(m.null_mutant(src, func).encode()).hexdigest()
    n = len(m.mutants(src, func, m._enum_members(src, root)))
    chain = 0.0
    for f in m.V21_TARGETS[target]:
        if (rel, null, f) in t0:
            chain += t0[(rel, null, f)]
        else:
            chain += median
            guessed.append(f"{target} {f}")
    rows.append((n * chain, n, round(chain, 1), target))
rows.sort(key=lambda r: (-r[0], r[3]))
out.write_text("".join(r[3] + "\n" for r in rows))
out.with_suffix(".tsv").write_text("".join(f"{r[3]}\t{r[1]}\t{r[2]}\t{round(r[0])}\n" for r in rows))
print(f"{len(rows)} targets, {sum(r[1] for r in rows)} mutants, upper bound {sum(r[0] for r in rows) / 3600:.1f} worker-hours; "
      f"{len(guessed)} (null, file) pairs not in a sweep (median {median:.1f} s)")
