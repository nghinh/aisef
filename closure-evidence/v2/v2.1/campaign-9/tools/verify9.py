"""verify9.py: the second count of campaign 9's totals, sharing no code with scope9.py.

    python -P closure-evidence/v2/v2.1/campaign-9/tools/verify9.py        (from the repository root; read only)

It (1) enumerates the mutants of every V2.1 target in a fresh interpreter, in the reverse order of the registry, with the
runner's own `mutants`; (2) re-derives each target's role from the committed DELTA.json of the base its previous result
comes from (campaign-8/SCOPE.json "result_from"), and nothing else; (3) compares both with SCOPE.json and targets.txt; (4) ties
the totals to the registry (614 targets), to the delta of the last snapshot (5df323a) taken as one table (its remeasure and
stand counts) and, as information, to the estimate of round-5/SCOPE-BEFORE-PIN.md. Exit 1 on any difference."""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[5]
E = ROOT / "closure-evidence/v2/v2.1"
D = E / "campaign-9"
COUNT = r"""
import json, sys
sys.path.insert(0, ".")
sys.dont_write_bytecode = True
from validation.v2 import mutation as m
out = {}
for t in sorted(m.V21_TARGETS, reverse=True):
    rel, func = t.split("::")
    src = open(rel, encoding="utf-8").read()
    out[t] = len(m.mutants(src, func, m._enum_members(src, m.ROOT)))
print(json.dumps({"registry": sorted(m.V21_TARGETS), "retired": list(m.V21_RETIRED), "mutants": out}))
"""
fresh = json.loads(subprocess.run([sys.executable, "-P", "-B", "-c", COUNT], cwd=ROOT, capture_output=True, encoding="utf-8",
                                  check=True).stdout)
scope = json.loads((D / "SCOPE.json").read_text())
prev = json.loads((E / "campaign-8/SCOPE.json").read_text())["targets"]
tags = {5: "289885e", 6: "a770fbb", 7: "853da4a", 8: "5df323a"}
delta = {n: json.loads((D / f"delta-from-{tag}/DELTA.json").read_text()) for n, tag in tags.items()}
bad = []


def check(ok: bool, what: str) -> None:
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        bad.append(what)


reg, mut = fresh["registry"], fresh["mutants"]
role = {}
for t in reg:
    if t not in prev:
        role[t] = "NEW"
    else:
        v = delta[int(prev[t]["result_from"].split()[1])]["targets"][t]["verdict"]
        role[t] = "REMEASURE" if v.startswith("re-measure") else "STAND"
rows = scope["targets"]
run = [t for t in reg if role[t] in ("NEW", "REMEASURE")]
standing = [t for t in reg if role[t] == "STAND"]
check(set(rows) == set(reg) and len(reg) == 614, f"SCOPE.json holds the {len(reg)} targets of the registry, none else")
check(all(rows[t]["mutants"] == mut[t] for t in reg), "every row's mutant count is the fresh enumeration's")
check(all((rows[t]["role"] == "NEW") == (role[t] == "NEW") and (rows[t]["role"] == "REMEASURE") == (role[t] == "REMEASURE")
          and (rows[t]["role"] in ("STANDS", "STANDS_PROVISIONAL")) == (role[t] == "STAND") for t in reg),
      "every row's role is the one the delta of its base gives")
check((D / "targets.txt").read_text().splitlines() == sorted(run), "targets.txt is REMEASURE + NEW, sorted, no duplicate, all in V21_TARGETS")
check(len(run) + len(standing) == 614, f"{len(run)} to measure + {len(standing)} standing = 614")
chain = delta[8]["counts"]
check(len(run) == chain["remeasure"] and len(standing) == chain["stand"],
      f"the delta of 5df323a taken as one table gives the same split ({chain['remeasure']} re-measure, {chain['stand']} stand)")
check(set(prev) - set(reg) == set(fresh["retired"]) == set(scope["retired"]) and len(fresh["retired"]) == 1,
      "the one retired target is the only old target not in the registry")
n_run, m_run, m_all = len(run), sum(mut[t] for t in run), sum(mut.values())
tot = scope["totals"]
check(tot["to_measure_now"] == {"targets": n_run, "mutants": m_run} and tot["registry_mutants"] == m_all,
      f"SCOPE.json totals: {n_run} targets / {m_run} mutants to measure, {m_all} in the registry")
check(not scope["disagreements"], "no disagreement between a delta's verdict and the standing record")
print(f"\nregistry: {len(reg)} targets, {m_all} mutants | to measure now: {n_run} targets, {m_run} mutants | standing: "
      f"{len(standing)} targets, {sum(mut[t] for t in standing)} mutants")
lin2 = [t for t in run if t.endswith(("lineage.py::_recorded_spend", "lineage.py::_evidence_gone"))]
print(f"information - round-5/SCOPE-BEFORE-PIN.md: about 509 targets / 13,751 mutants for 612 targets; without the two "
      f"lineage-r2 targets ({len(lin2)}: {sum(mut[t] for t in lin2)} mutants) here: {n_run - len(lin2)} targets / "
      f"{m_run - sum(mut[t] for t in lin2)} mutants")
sys.exit(1 if bad else 0)
