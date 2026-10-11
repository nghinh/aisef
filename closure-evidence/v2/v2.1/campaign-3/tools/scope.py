"""scope.py OUT_DIR IMPACT_SAMPLE.json: what campaign 3 measures, and why — one row per target of the 468 V2.1 targets.

    role        REMEASURE      the delta (campaign-3/delta/DELTA.json, head = the read-set's commit) says re-measure
                IMPACT_SAMPLE  a target whose campaign-2 result STANDS, measured again on purpose: the check that
                               the runner's changes (signature, positional audits, ps parser) moved no class
                STANDS         campaign 2's result stands (the delta's reasons: none of its inputs changed)
    reasons     the delta's reasons; kill_added / kill_removed: the kill set at head against rev 2's manifest
    base        campaign 2's classes for the target (None: a target campaign 2 did not have)

Writes OUT_DIR/SCOPE.json (every row), OUT_DIR/targets.txt (the targets campaign 3 runs, one per line, sorted) and
prints the counts. Reads only committed files; the head mutant counts come from the runner's own generator."""
import collections, json, lzma, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from validation.v2 import mutation as m  # noqa: E402

out, sample = pathlib.Path(sys.argv[1]), set(json.loads(pathlib.Path(sys.argv[2]).read_text()))
E = ROOT / "closure-evidence/v2/v2.1"
delta = json.loads((E / "campaign-3/delta/DELTA.json").read_text())
old = json.loads((E / "REQUALIFICATION-MANIFEST-2.json").read_text())["mutation"]["targets"]
base = {e["target"]: e for e in json.loads(lzma.open(E / "campaign-2/results/MUTATION.json.xz").read())["targets"]}
rows = {}
for t, kill in sorted(m.V21_TARGETS.items()):
    rel, func = t.split("::")
    src = (ROOT / rel).read_text(encoding="utf-8")
    d = delta["targets"][t]
    remeasure = d["verdict"].startswith("re-measure")
    was = old.get(t, {}).get("kill_tests")
    rows[t] = {
        "role": "REMEASURE" if remeasure else ("IMPACT_SAMPLE" if t in sample else "STANDS"),
        "reasons": d.get("reasons", []), "verdict": d["verdict"],
        "kill_files": list(kill),
        "kill_added": sorted(set(kill) - set(was or [])), "kill_removed": sorted(set(was or []) - set(kill)),
        "mutants": len(m.mutants(src, func, m._enum_members(src, ROOT))),
        "base": ({"mutants": len(base[t]["results"]), "classes": {k: v for k, v in base[t]["classes"].items() if v}}
                 if t in base else None)}
assert sample <= {t for t, r in rows.items() if r["role"] == "IMPACT_SAMPLE"}, "a sample target is not a standing target"
run = sorted(t for t, r in rows.items() if r["role"] != "STANDS")
out.mkdir(parents=True, exist_ok=True)
(out / "SCOPE.json").write_text(json.dumps({"record": "AISEF V2.1 — campaign 3 scope: which targets are measured, and why",
                                            "delta_head": delta["head"], "read_set": delta["read_set"]["commit"],
                                            "targets": rows}, indent=1, ensure_ascii=False) + "\n")
(out / "targets.txt").write_text("".join(t + "\n" for t in run))
c = collections.Counter(r["role"] for r in rows.values())
print(dict(c), "| run:", len(run), "targets,", sum(rows[t]["mutants"] for t in run), "mutants | stand:",
      sum(1 for r in rows.values() if r["role"] == "STANDS"), "targets,",
      sum(r["mutants"] for r in rows.values() if r["role"] == "STANDS"), "mutants")
