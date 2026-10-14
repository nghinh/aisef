"""merge_audits.py: the skeptic agents' verdicts (audit/out/<batch>-<a|b>.json) per audited entry, a and b side by side."""
import collections, glob, json
OUT = "/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/r3/audit/out"
by = collections.defaultdict(dict)
for f in sorted(glob.glob(OUT + "/*.json")):
    d = json.load(open(f))
    for e in d["entries"]:
        by[(e["target"], e["index"])][d["copy"]] = {**e, "batch": d["batch"]}
rows = []
for k, v in sorted(by.items()):
    a, b = v.get("a"), v.get("b")
    va, vb = a and a["verdict"], b and b["verdict"]
    ca, cb = a and a["class_after"], b and b["class_after"]
    rows.append((k, va, vb, ca, cb, (a or b)["mutant"], (a or b)["class_before"]))
cnt = collections.Counter((r[1], r[2]) for r in rows)
print(len(rows), "entries;", dict(cnt))
bad = [r for r in rows if r[1] not in ("CONFIRMED",) or r[2] not in ("CONFIRMED",)]
for r in bad:
    print(f"{r[0][0].split('/')[-1]} #{r[0][1]} [{r[5][:40]}] before={r[6]} a={r[1]}->{r[3]} b={r[2]}->{r[4]}")
