"""progress2.py C: campaign 2 so far — lines claimed / done of the queue, per worker; the targets finished with their
classes (from each `TARGET: k/n killed; classes {...}` line the runner prints), survivors, and anything not KILLED or
SURVIVED; the expected cost done vs left (queue.tsv's upper bound) and the free disk."""
import collections, pathlib, re, subprocess, sys
C = pathlib.Path(sys.argv[1])
q = C.joinpath("queue.txt").read_text().split()
cost = {l.split("\t")[0]: float(l.split("\t")[3]) for l in C.joinpath("queue.tsv").read_text().splitlines()} if C.joinpath("queue.tsv").exists() else {}
claims = sorted(C.glob("claims/*"), key=lambda p: int(p.name))
done = [p for p in claims if (p / "done").exists()]
cls, surv, bad = collections.Counter(), [], []
for log in sorted(C.glob("c2-w*.log")):
    for m in re.finditer(r"^(\S+::\S+): (\d+)/(\d+) killed; classes (\{.*?\}); survivors (\[.*?\])(.*)$", log.read_text(), re.M):
        c = eval(m.group(4)); cls.update(c)
        if c.get("SURVIVED"): surv.append((m.group(1), c["SURVIVED"]))
        if m.group(6).strip() or any(c.get(k) for k in ("TIMEOUT", "INFRA", "NOT_RUN")): bad.append((m.group(1), c, m.group(6)[:160]))
by = collections.Counter((p / "by").read_text().split()[0] for p in claims if (p / "by").exists())
cd = sum(cost.get(q[int(p.name) - 1], 0) for p in done)
print(f"queue {len(q)}; claimed {len(claims)}; done {len(done)}; per worker {dict(by)}")
print(f"classes so far {dict(cls)}; targets with survivors {len(surv)}; not clean {len(bad)}")
for b in bad: print("  NOT CLEAN", b)
if cost: print(f"upper-bound cost done {cd / 3600:.1f} h of {sum(cost.values()) / 3600:.1f} h")
print(subprocess.run(["df", "-g", "/System/Volumes/Data"], capture_output=True, text=True, encoding="utf-8").stdout.splitlines()[-1])
