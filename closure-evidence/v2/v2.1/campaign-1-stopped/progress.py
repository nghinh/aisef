"""progress.py: the V2.1 campaign so far, from the workers' logs — targets done of their shard, mutants, survivors,
errors, timeouts (each line `TARGET: K/N killed; survivors [...]` [ERROR ...] as mutation.py prints it)."""
import json, pathlib, re, sys, time
D = pathlib.Path(__file__).parent
LINE = re.compile(r"^(?P<t>\S+::\S+): (?P<k>\S+)/(?P<n>\S+) killed; survivors (?P<s>.*?)(?: ERROR (?P<e>.*))?$")
out, total = {}, {"done": 0, "of": 0, "mutants": 0, "killed": 0, "survivors": [], "errors": [], "timeouts": []}
for w in ("m21-w1", "m21-w2", "m21-w3", "m21-w4"):
    shard = (D / f"{w}.targets").read_text().split()
    log = (D / f"{w}.log").read_text(errors="replace").splitlines() if (D / f"{w}.log").exists() else []
    done = [m.groupdict() for ln in log if (m := LINE.match(ln))]
    surv = [(d["t"], d["s"]) for d in done if d["s"] not in ("[]", "None")]
    errs = [(d["t"], d["e"][:160]) for d in done if d["e"]]
    tmo = [ln[:200] for ln in log if "timed out" in ln.lower() or "TIMEOUT" in ln]
    out[w] = {"done": len(done), "of": len(shard), "finished": (D / f"{w}.finished").exists(),
              "survivors": surv, "errors": errs, "timeouts": tmo[:5]}
    total["done"] += len(done); total["of"] += len(shard)
    total["mutants"] += sum(int(d["n"]) for d in done if d["n"].isdigit())
    total["killed"] += sum(int(d["k"]) for d in done if d["k"].isdigit())
    total["survivors"] += surv; total["errors"] += errs; total["timeouts"] += tmo
started = (D / "m21-w1.started").read_text().strip() if (D / "m21-w1.started").exists() else "?"
print(f"started {started}; now {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
for w, r in out.items():
    print(f"{w}: {r['done']}/{r['of']} targets{' FINISHED' if r['finished'] else ''}; survivors {len(r['survivors'])}; errors {len(r['errors'])}")
print(f"total: {total['done']}/{total['of']} targets, {total['killed']}/{total['mutants']} mutants killed")
for t, s in total["survivors"]:
    print(f"  SURVIVOR {t}: {s}")
for t, e in total["errors"]:
    print(f"  ERROR {t}: {e}")
for x in total["timeouts"][:10]:
    print(f"  TIMEOUT? {x}")
