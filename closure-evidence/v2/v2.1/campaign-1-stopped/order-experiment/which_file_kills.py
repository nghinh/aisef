"""which_file_kills.py WORKTREE TARGET N OUT.json: for N mutants of TARGET spread across its mutant list, run EACH kill
file on its own (mutation.py's copy tree, command, env, timeout, cleanup authority) and record which files kill it and
how long each took — to see whether the kill set's order, not its content, decides the campaign's cost."""
import json, pathlib, shutil, sys, tempfile, time
W, TARGET, N, OUT = pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), pathlib.Path(sys.argv[4])
sys.path.insert(0, str(W))
from validation.v2 import mutation as m  # noqa: E402
rel, func = TARGET.split("::")
kill = m.V21_TARGETS[TARGET]
src = (W / rel).read_text(encoding="utf-8")
muts = m.mutants(src, func, m._enum_members(src, W))
pick = [muts[round(i * (len(muts) - 1) / max(N - 1, 1))] for i in range(N)]
rows = []
with tempfile.TemporaryDirectory() as t:
    work = pathlib.Path(t) / "tree"
    for part in m.COPY:
        s = W / part
        if s.is_dir():
            shutil.copytree(s, work / part, ignore=shutil.ignore_patterns("__pycache__"))
        elif s.exists():
            (work / part).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(s, work / part)
    boundary = m.ca.establish(work)
    for desc, mutated in pick:
        (work / rel).write_text(mutated, encoding="utf-8")
        per = {}
        for f in kill:
            m._FAILED.clear(); m._TIMED_OUT.clear()
            t0 = time.monotonic()
            ok, leaked = m._run_tests(work, [f], boundary)
            per[f] = {"killed": not ok, "seconds": round(time.monotonic() - t0, 1), "timed_out": bool(m._TIMED_OUT)}
        (work / rel).write_text(src, encoding="utf-8")
        rows.append({"mutant": desc, "files": per})
        print(desc, [(pathlib.Path(f).name, r["killed"], r["seconds"]) for f, r in per.items()], flush=True)
        OUT.write_text(json.dumps({"target": TARGET, "kill_tests": kill, "mutants_total": len(muts), "rows": rows}, indent=1) + "\n")
