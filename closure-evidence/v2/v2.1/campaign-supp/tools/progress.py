"""progress.py C [--json]: supplementary campaign so far, from the workers' own output only.
Per worker: the target it is on (its last `=== ... line N TARGET` header) and every mutant line (`MUTANT {...}`, the
runner's checkpoint after each mutant) since; per class over all workers: mutants classified (KILLED / SURVIVED, and
TIMEOUT / INFRA / NOT_RUN, never counted as killed); targets finished (`TARGET: k/n killed; classes {...}`) and
whether each is clean (every mutant KILLED or SURVIVED, no error). ETA: realized worker-seconds per unit of the
queue's upper bound so far (finished targets fully, running ones by the fraction of their mutants classified),
applied to what is left, spread over the workers, but never before the slowest running target can end.
Copied from campaign-3 progress3.py; only the worker-log glob changed (w*.log)."""
import datetime, json, pathlib, re, subprocess, sys
C = pathlib.Path(sys.argv[1])
q = C.joinpath("queue.txt").read_text().split()
ub = {l.split("\t")[0]: (int(l.split("\t")[1]), float(l.split("\t")[3])) for l in C.joinpath("queue.tsv").read_text().splitlines()}
now = datetime.datetime.now(datetime.timezone.utc)
start = datetime.datetime.fromisoformat(C.joinpath("campaign.started").read_text().strip().replace("Z", "+00:00"))
cls, finished, running, unclean = {}, [], [], []
for log in sorted(C.glob("w*.log")):
    cur, since, mut = None, None, []
    for line in log.read_text(errors="replace").splitlines():
        m = re.match(r"=== (\S+) (\S+) line (\d+) (\S+)", line)
        if m:
            cur, since, mut = m.group(4), datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00")), []
        elif line.startswith("MUTANT "):
            c = json.loads(line[7:]).get("class", "?"); mut.append(c); cls[c] = cls.get(c, 0) + 1
        elif cur and line.startswith(cur + ": ") and " killed; classes " in line:
            cs = eval(line.split(" classes ", 1)[1].split("; survivors", 1)[0])
            err = " ERROR " in line
            finished.append((cur, cs, err))
            if err or any(cs.get(k) for k in ("TIMEOUT", "INFRA", "NOT_RUN")): unclean.append(line[:200])
            cur = None
    if cur:
        running.append((log.stem, cur, len(mut), ub.get(cur, (0, 0))[0], since))
done_ub = sum(ub[t][1] for t, _, _ in finished if t in ub)
run_ub = sum(ub[t][1] * (k / n if n else 0) for _, t, k, n, _ in running if t in ub)
elapsed = (now - start).total_seconds() * len(list(C.glob("w*.log")))
rate = elapsed / (done_ub + run_ub) if done_ub + run_ub else None
left_ub = sum(v[1] for v in ub.values()) - done_ub - run_ub
workers = max(1, len(running))
eta_s = rate * left_ub / workers if rate else None
pole = max((rate * ub[t][1] * (1 - k / n) for _, t, k, n, _ in running if rate and n), default=0)
free = subprocess.run(["df", "-g", "/System/Volumes/Data"], capture_output=True, text=True, encoding="utf-8").stdout.splitlines()[-1].split()[3]
out = {"at": now.isoformat(timespec="seconds"), "elapsed_h": round((now - start).total_seconds() / 3600, 2),
       "queue": len(q), "targets_finished": len(finished), "targets_running": len(running), "targets_left": len(q) - len(finished) - len(running),
       "mutants_classified": cls, "infra_or_timeout_or_not_run": sum(cls.get(k, 0) for k in ("TIMEOUT", "INFRA", "NOT_RUN")),
       "unclean_targets": unclean, "running": [{"worker": w, "target": t, "classified": k, "mutants": n} for w, t, k, n, _ in running],
       "free_gib": int(free), "realized_s_per_ub_s": round(rate, 3) if rate else None,
       "eta_h": round(max(eta_s, pole) / 3600, 1) if rate else None}
print(json.dumps(out) if "--json" in sys.argv else json.dumps(out, indent=1))
