"""replay_signature.py RECORD(.json|.json.xz) [OUT.json]: what the signature rule (validation/v2/mutation.py `signature`)
says about every mutant of a recorded campaign, from the rows as written — no test is run.

Run from a tree holding the runner under test (imports validation.v2.mutation from cwd).
For every mutant of every class: its recorded class; `_confirmed` under the rule now in the tree (KILLED entries must
stay confirmed: equal strings have equal signatures); and for every FAIL row that starts a bracket — whatever the
mutant's class — whether the bracket (control PASS, control PASS, re-run FAIL with the same signature) is confirmed
under the rule, and was not by the string comparison. A SURVIVED, TIMEOUT or INFRA mutant with such a bracket is one
the rule could move toward KILLED when it is measured again. The classes themselves are never rewritten: only a
re-run measures."""
import collections, hashlib, json, lzma, pathlib, sys

sys.path.insert(0, ".")
from validation.v2 import mutation as m  # noqa: E402

src = pathlib.Path(sys.argv[1])
raw = src.read_bytes()
rec = json.loads(lzma.decompress(raw) if src.suffix == ".xz" else raw)
BR = [("control", "PASS"), ("control", "PASS"), ("rerun", "FAIL")]


def bracket(rows, i):
    """(why not, (string equal, signature equal)) for the FAIL row i and the three rows after it."""
    x, nxt = rows[i], rows[i + 1:i + 1 + len(BR)]
    for k, (role, want) in enumerate(BR):
        if k >= len(nxt) or nxt[k].get("role") != role or nxt[k]["file"] != x["file"]:
            return "no bracket rows", None
        if nxt[k]["outcome"] != want:
            return f"{role} {nxt[k]['outcome']}", None
    return None, (nxt[2].get("first") == x.get("first"), m.signature(nxt[2].get("first")) == m.signature(x.get("first")))


summary, flips, bad_kills, per_class = collections.Counter(), [], [], collections.defaultdict(collections.Counter)
head_after = collections.Counter()   # where a row's recorded header stands in its kept tail: after the report's separator?
for t in rec["targets"]:
    for idx, r in enumerate(t["results"]):   # a mutant is its position in the target's list: descriptions repeat
        cls = r["class"]
        summary[cls] += 1
        if cls == "KILLED" and not m._confirmed(r):
            bad_kills.append({"target": t["target"], "index": idx, "mutant": r["mutant"]})
        rows = r.get("files", [])
        for x in rows:
            h, tail = x.get("first"), x.get("tail")
            if h and tail:
                line = h.split(" | ")[0]
                at = tail.find(line)
                if at < 0:
                    head_after["header not in the kept tail"] += 1
                elif tail[:at].endswith("=" * 70 + "\n"):
                    head_after["after the separator line"] += 1
                elif at < 71:
                    head_after["tail cut before the separator"] += 1
                else:
                    head_after["after something else"] += 1
        for i, x in enumerate(rows):
            if x.get("outcome") != "FAIL" or x.get("role") not in (None, "unconfirmed"):
                continue
            why, eq = bracket(rows, i)
            per_class[cls][why or ("confirmed by string" if eq[0] else "confirmed by signature only" if eq[1] else "different signature")] += 1
            if cls != "KILLED" and eq and eq[1] and not eq[0]:
                flips.append({"target": t["target"], "index": idx, "mutant": r["mutant"], "class": cls, "row": i, "role": x.get("role"),
                              "fresh": bool(x.get("fresh")), "string_equal": eq[0], "signature_equal": eq[1],
                              "first": x["first"], "rerun": rows[i + 3]["first"], "signature": m.signature(x["first"])})
res = {"record": src.name, "record_sha256": hashlib.sha256(raw).hexdigest(), "runner": "validation/v2/mutation.py",
       "runner_sha256_lf": hashlib.sha256(pathlib.Path("validation/v2/mutation.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
       "classes": dict(summary), "killed_not_confirmed": bad_kills,
       "fail_rows_by_class": {k: dict(v) for k, v in per_class.items()},
       "header_position_in_kept_tails": dict(head_after),
       "not_killed_mutants_the_rule_could_move_toward_killed": len({(f["target"], f["index"]) for f in flips}),
       "by_class": dict(collections.Counter(f["class"] for f in {(f["target"], f["index"]): f for f in flips}.values())),
       "by_target": dict(collections.Counter(f["target"] for f in {(f["target"], f["index"]): f for f in flips}.values())),
       "rows": flips}
if len(sys.argv) > 2:
    pathlib.Path(sys.argv[2]).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in res.items() if k != "rows"}, ensure_ascii=False, indent=1)[:3500])
