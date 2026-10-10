"""account.py REPO C OUT_DIR: campaign 2's results as one V2.1 record, and what it says.

REPO: a tree holding the committed manifest (revision 2) and the pilot attempt-2 records; C: the live campaign
directory (c2-wN.record.json, the runner's own record after each target). Writes OUT_DIR/MUTATION.json (every
target's runner-2 result: the four workers' and the nine pilot `ord` results the queue left out) and
OUT_DIR/ACCOUNT.json (counts, per-target classes, what is missing or duplicated, unclean targets). Reads only; the
verdict proper is the runner's own `--check` on a tree at the snapshot holding this record."""
import collections, json, pathlib, sys

repo, C, out = (pathlib.Path(a) for a in sys.argv[1:4])
man = json.loads((repo / "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST-2.json").read_text(encoding="utf-8"))["mutation"]
sources = sorted(C.glob("c2-w*.record.json")) + sorted((repo / "closure-evidence/v2/v2.1/pilot/attempt-2").glob("l*-ord.record.json"))
seen, problems = collections.defaultdict(list), []
for s in sources:
    for t in json.loads(s.read_text(encoding="utf-8"))["targets"]:
        seen[t["target"]].append((s.name, t))
targets = []
for name, want in man["targets"].items():
    got = seen.get(name, [])
    if len(got) != 1:
        problems.append(f"{name}: {len(got)} results ({[g[0] for g in got]})")
        if not got:
            continue
    src, t = got[-1]
    if t.get("runner") != 2:
        problems.append(f"{name}: runner {t.get('runner')} ({src})")
    if t.get("kill_tests") != want["kill_tests"]:
        problems.append(f"{name}: kill set differs from the manifest ({src})")
    if t.get("mutants") != want["mutants"]:
        problems.append(f"{name}: {t.get('mutants')} mutants, the manifest says {want['mutants']} ({src})")
    targets.append(t | {"_from": src})
problems += [f"{n}: not a manifest target ({[g[0] for g in seen[n]]})" for n in seen if n not in man["targets"]]
cls = collections.Counter(r.get("class") for t in targets for r in t.get("results", []))
unclean = {t["target"]: dict(collections.Counter(r.get("class") for r in t.get("results", [])))
           for t in targets if t.get("error") or any(r.get("class") not in ("KILLED", "SURVIVED") for r in t.get("results", []))}
out.mkdir(parents=True, exist_ok=True)
record = {"record": "AISEF V2 — V2.1 MUTATION", "tool": "validation/v2/mutation.py",
          "targets": [{k: v for k, v in t.items() if k != "_from"} for t in targets]}
(out / "MUTATION.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
account = {"manifest_targets": len(man["targets"]), "manifest_mutants": man["mutant_count"], "targets_with_a_result": len(targets),
           "mutants_classified": sum(cls.values()), "classes": dict(cls), "unclean_targets": unclean,
           "survivors_by_target": {t["target"]: len([r for r in t["results"] if r.get("class") == "SURVIVED"])
                                   for t in targets if any(r.get("class") == "SURVIVED" for r in t.get("results", []))},
           "from": {s.name: sum(1 for t in targets if t["_from"] == s.name) for s in sources}, "problems": problems}
(out / "ACCOUNT.json").write_text(json.dumps(account, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in account.items() if k not in ("survivors_by_target", "problems")} |
                 {"problems": len(problems), "first_problems": problems[:5]}, ensure_ascii=False, indent=1))
