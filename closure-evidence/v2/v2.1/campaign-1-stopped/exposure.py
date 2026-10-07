"""exposure.py TREE OUT: for every historical mutation record the tree's mutation.py names (RECORDS), per target: mutants,
kills, timeouts recorded as kills, and stale-bytecode EXPOSURE — mutants whose source has the same byte size as the
source written just before it in the same target (the original, then each mutant in generation order). Exposure is a
necessary condition, not proof, of a stale import (it also needs the same whole second); the record kept no timings."""
import collections, json, pathlib, sys
T, OUT = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sys.path.insert(0, str(T))
from validation.v2 import mutation as m  # noqa: E402
rows, per = [], collections.OrderedDict()
for phase, rel in m.RECORDS.items():
    p = T / rel
    if not p.exists():
        continue
    rec = json.loads(p.read_text(encoding="utf-8"))
    tot = collections.Counter()
    for t in rec["targets"]:
        if t.get("error"):
            tot["errored_targets"] += 1
            continue
        mod, fn = t["target"].split("::")
        res = t.get("results", [])
        tot["targets"] += 1; tot["mutants"] += len(res); tot["killed"] += sum(1 for r in res if r.get("killed"))
        tot["timeout_kills"] += sum(1 for r in res if r.get("timed_out"))
        try:
            src = (T / mod).read_text(encoding="utf-8")
            gen = dict(m.mutants(src, fn, m._enum_members(src, T)))
        except (Exception, SystemExit):   # noqa: BLE001 — a target whose source or name moved since its record
            tot["source_unavailable"] += 1
            continue
        prev = len(src.encode())
        for r in res:
            s = gen.get(r["mutant"])
            if s is None:
                tot["mutant_not_regenerated"] += 1
                continue
            if len(s.encode()) == prev:
                tot["exposed"] += 1
                tot["exposed_killed" if r.get("killed") else "exposed_survived"] += 1
            prev = len(s.encode())
    per[phase] = dict(tot)
OUT.write_text(json.dumps(per, indent=1) + "\n")
for ph, c in per.items():
    print(f"{ph:12s} targets {c.get('targets',0):4d} mutants {c.get('mutants',0):5d} killed {c.get('killed',0):5d} timeout-kills {c.get('timeout_kills',0):3d} exposed {c.get('exposed',0):4d} (killed {c.get('exposed_killed',0)}, survived {c.get('exposed_survived',0)}) unavailable {c.get('source_unavailable',0)} not-regen {c.get('mutant_not_regenerated',0)}")
