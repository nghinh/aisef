"""guard.py: honesty + consistency guards on the candidate SURVIVOR-AUDITS.json against the campaign-9 survivor and
owed lists. Run from repo root: python -P scratch/guard.py"""
import json, pathlib, sys
ROOT = pathlib.Path(".").resolve()
W = ROOT / "closure-evidence/v2/v2.1/campaign-9/survivor-audits"
AUD = ROOT / "closure-evidence/v2/v2.1/mutation/SURVIVOR-AUDITS.json"

surv = json.load(open(W / "wave2/survivors-all.json"))            # target -> [[index, mutant], ...]
S = {}                                                            # (target, index) -> mutant
for t, lst in surv.items():
    for idx, mut in lst:
        S[(t, int(idx))] = mut
targets = sorted(surv)
def resolve(stem, func, idx):
    """full target for a module stem + func + index, by matching the survivor universe."""
    cands = [t for t in targets if t.endswith(f"/{stem}.py::{func}") and (t, int(idx)) in S]
    if len(cands) == 1: return cands[0]
    cands2 = [t for t in targets if t.endswith(f"/{stem}.py::{func}")]
    return cands2[0] if len(cands2) == 1 else None

# owed set O as (target, index)
O, unresolved = set(), []
for e in json.load(open(W / "wave1/owed-wave1.json"))["owed"]:
    O.add((e["target"], int(e["index"])))
for e in json.load(open(W / "wave2/owed-wave2a.json"))["owed"]:
    stem = e["batch"].split("-")[1]          # W2-<stem>-N
    t = resolve(stem, e["func"], e["index"])
    (O.add((t, int(e["index"]))) if t else unresolved.append(("2a", e)))
for e in json.load(open(W / "wave2/owed-wave2b.json")):
    stem = e["batch"].split("-")[1]
    t = resolve(stem, e["func"], e["index"])
    (O.add((t, int(e["index"]))) if t else unresolved.append(("2b", e)))

# candidate audits
aud = json.load(open(AUD))["entries"]
A = {}                                        # (target, index) -> mutant (as recorded in the audit)
dup = []
for e in aud:
    k = (e["target"], int(e["index"]))
    if k in A: dup.append(k)
    A[k] = e["mutant"]

Askeys = set(A)
print(f"survivors S={len(S)}  owed O={len(O)} (unresolved {len(unresolved)})  audits A={len(A)} (dups {len(dup)})")

# G1: no owed position is audited (honesty)
masked = sorted(O & Askeys)
print(f"G1 owed-also-audited (MUST be 0): {len(masked)}")
for k in masked[:20]: print("   MASKED", k, "| survivor-mutant:", S.get(k), "| audit-mutant:", A[k])

# G2: audits that are not current survivors (stale carried)
stale = sorted(Askeys - set(S))
print(f"G2 audits not in survivor set (stale carried, informational): {len(stale)}")
for k in stale[:20]: print("   stale", k, "| audit-mutant:", A[k])

# G3: survivors partition into audited-xor-owed
aud_surv = Askeys & set(S)
cover = aud_surv | O
print(f"G3 audited-survivors={len(aud_surv)} + owed={len(O)} = {len(aud_surv)+len(O)} (survivors={len(S)})")
uncovered = sorted(set(S) - cover)
both = sorted(aud_surv & O)
print(f"   survivors neither audited nor owed (MUST be 0): {len(uncovered)}")
for k in uncovered[:20]: print("   UNCOVERED", k, "| mutant:", S[k])
print(f"   survivors both audited and owed (MUST be 0): {len(both)}")

# G4: for audited survivors, the audit's mutant string must equal the survivor list's mutant (positional alignment)
mism = [(k, A[k], S[k]) for k in aud_surv if A[k] != S[k]]
print(f"G4 mutant-string mismatches on audited survivors (MUST be 0): {len(mism)}")
for k, a, s in mism[:20]: print("   MISMATCH", k, "| audit:", repr(a), "| survivor:", repr(s))

if unresolved:
    print("UNRESOLVED owed (could not map to a target):")
    for w, e in unresolved[:20]: print("  ", w, e)

ok = not masked and not uncovered and not both and not mism and not unresolved
print("GUARD:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
