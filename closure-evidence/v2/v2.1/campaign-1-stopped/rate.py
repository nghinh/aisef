"""rate.py SECONDS: per worker, how many mutants were written into its copy tree in SECONDS (mtime changes of the
mutated file), and which file — the campaign's real mutant rate on its current targets."""
import os, pathlib, sys, time, glob
D = pathlib.Path(__file__).parent
secs = int(sys.argv[1])
trees = {w: glob.glob(str(D / f"m21-{w}.env/tmp/tmp*/tree")) for w in ("w1", "w2", "w3", "w4")}
last, count, which = {}, {w: 0 for w in trees}, {}
end = time.time() + secs
while time.time() < end:
    for w, ts in trees.items():
        for t in ts:
            for f in glob.glob(t + "/aisef2/**/*.py", recursive=True):
                m = os.stat(f).st_mtime_ns
                k = (w, f)
                if k in last and m != last[k]:
                    count[w] += 1
                    which[w] = f.split("/tree/")[1]
                last[k] = m
    time.sleep(1)
for w in trees:
    print(w, f"{count[w] / 2:.0f} mutants in {secs}s (each mutant writes the file twice: mutant, then restore)", which.get(w))
