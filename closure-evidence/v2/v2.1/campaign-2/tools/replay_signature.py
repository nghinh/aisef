"""replay_signature.py RECORD(.json|.json.xz) [OUT.json]: what the signature rule (validation/v2/mutation.py `signature`)
says about every mutant of a recorded campaign, from the rows as written — no test is run.

Run from a tree holding the runner under test (imports validation.v2.mutation from cwd).
For each mutant: its recorded class; `_confirmed` under the rule now in the tree (KILLED entries must stay confirmed:
equal strings have equal signatures); and for every mutant that has a FAIL row followed by a bracket: would the
bracket (control PASS, control PASS, re-run FAIL with the same signature) have been confirmed, in place and on the
fresh tree, and if not, why (a control not PASS, a re-run not FAIL, a different signature). The classes themselves are
never rewritten: only a re-run measures."""
import collections, hashlib, json, lzma, pathlib, sys

sys.path.insert(0, ".")
from validation.v2 import mutation as m  # noqa: E402

src = pathlib.Path(sys.argv[1])
raw = src.read_bytes()
rec = json.loads(lzma.decompress(raw) if src.suffix == ".xz" else raw)
BR = [("control", "PASS"), ("control", "PASS"), ("rerun", "FAIL")]


def brackets(rows):
    """[(index of the FAIL row, first, [following BR rows], fresh)] for every FAIL row that starts a bracket."""
    out = []
    for i, x in enumerate(rows):
        if x.get("outcome") == "FAIL" and x.get("role") in (None, "unconfirmed"):
            out.append((i, x))
    return out


def judge(rows, i, x):
    nxt = rows[i + 1:i + 1 + len(BR)]
    for k, (role, want) in enumerate(BR):
        if k >= len(nxt) or nxt[k].get("role") != role or nxt[k]["file"] != x["file"]:
            return "no bracket rows", None
        if nxt[k]["outcome"] != want:
            return f"{role} {nxt[k]['outcome']}", None
    same = m.signature(nxt[2].get("first")) == m.signature(x.get("first"))
    raw_same = nxt[2].get("first") == x.get("first")
    return ("confirmed" if same else "different signature"), (raw_same, same)


summary = collections.Counter()
would_kill, other = [], []
for t in rec["targets"]:
    for r in t["results"]:
        cls = r["class"]
        summary[cls] += 1
        if cls == "KILLED":
            if not m._confirmed(r):
                other.append({"target": t["target"], "mutant": r["mutant"], "problem": "KILLED not confirmed under the rule"})
            continue
        if cls != "INFRA":
            continue
        rows = r.get("files", [])
        views = []
        for i, x in brackets(rows):
            verdict, flags = judge(rows, i, x)
            views.append({"row": i, "fresh": bool(x.get("fresh")), "role": x.get("role"), "bracket": verdict})
        confirmed = any(v["bracket"] == "confirmed" for v in views)
        would_kill.append({"target": t["target"], "mutant": r["mutant"], "files": sorted({x["file"] for x in rows}),
                           "would_be_confirmed": confirmed, "brackets": views,
                           "first_difference": next(({"a": x["first"][:200], "b": rows[i + 3]["first"][:200]} for i, x in brackets(rows)
                                                      if i + 3 < len(rows) and rows[i + 3].get("role") == "rerun"), None)})
res = {"record": src.name, "record_sha256": hashlib.sha256(raw).hexdigest(),
       "runner": "validation/v2/mutation.py",
       "runner_sha256": hashlib.sha256(pathlib.Path("validation/v2/mutation.py").read_bytes()).hexdigest(),
       "classes": dict(summary), "killed_not_confirmed": [o for o in other],
       "infra": len(would_kill), "infra_would_be_confirmed": sum(w["would_be_confirmed"] for w in would_kill),
       "infra_not_confirmed": [w for w in would_kill if not w["would_be_confirmed"]],
       "infra_by_target": dict(collections.Counter(w["target"] for w in would_kill)),
       "infra_rows": would_kill}
if len(sys.argv) > 2:
    pathlib.Path(sys.argv[2]).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in res.items() if k != "infra_rows"}, ensure_ascii=False, indent=1)[:3000])
