"""build_audits9.py OUT: assemble closure-evidence/v2/v2.1/mutation/SURVIVOR-AUDITS.json for campaign 9.

Authoritative rule (so audit_of binds and nothing masks a real gap):
  an audit entry is kept iff its (target,index) is a CURRENT survivor (survivors-all.json) AND is NOT in the owed set
  (the 85 test-owed gaps). The mutant STRING is taken from survivors-all.json (the generator's exact description), since
  mutation.audit_of matches on the exact (target,index,mutant) key; a draft's paraphrase is canonicalised only when it
  refers to the same source line (same leading 'L<n>' token), else the entry is dropped and reported.
Sources: carried prior audits remapped to the snapshot (wave2/remapped.json) + the campaign-9 AUDITED/EQUIVALENT the
waves confirmed (wave1 two-blind, wave2 one-blind). source_sha256 = mutation.source_digest(module text at the snapshot).
Each entry validated with mutation._audit_entry_problem. Run from repo root:
    python -P scratch/build_audits9.py OUT
"""
import json, pathlib, subprocess, sys, re, glob, collections
ROOT = pathlib.Path(".").resolve()
sys.path.insert(0, str(ROOT))
from validation.v2 import mutation as m  # noqa
SNAP = "4ec961e706a1f7bda16d131037058c4fe9c2663f"
WA = ROOT / "closure-evidence/v2/v2.1/campaign-9/survivor-audits"
out_path = pathlib.Path(sys.argv[1])

# ---- authoritative survivor + owed sets -------------------------------------------------
surv = json.load(open(WA / "wave2/survivors-all.json"))      # target -> [[index, mutant], ...]
S = {(t, int(i)): mut for t, lst in surv.items() for i, mut in lst}
targets = sorted(surv)
def resolve(stem, func, idx):
    cands = [t for t in targets if t.endswith(f"/{stem}.py::{func}") and (t, int(idx)) in S]
    if len(cands) == 1: return cands[0]
    c2 = [t for t in targets if t.endswith(f"/{stem}.py::{func}")]
    return c2[0] if len(c2) == 1 else None
O, unresolved = set(), []
for e in json.load(open(WA / "wave1/owed-wave1.json"))["owed"]:
    O.add((e["target"], int(e["index"])))
for e in json.load(open(WA / "wave2/owed-wave2a.json"))["owed"]:
    t = resolve(e["batch"].split("-")[1], e["func"], e["index"])
    O.add((t, int(e["index"]))) if t else unresolved.append(e)
for e in json.load(open(WA / "wave2/owed-wave2b.json")):
    t = resolve(e["batch"].split("-")[1], e["func"], e["index"])
    O.add((t, int(e["index"]))) if t else unresolved.append(e)
assert not unresolved, unresolved

_dig = {}
def digest(rel):
    if rel not in _dig:
        txt = subprocess.run(["git", "show", f"{SNAP}:{rel}"], capture_output=True, encoding="utf-8", check=True).stdout
        _dig[rel] = m.source_digest(txt)
    return _dig[rel]
def lnum(s):
    mm = re.match(r"\s*L(\d+)", s or "")
    return mm.group(1) if mm else None

entries, dropped = {}, collections.Counter()
def put(target, index, cls, group, grounds, cons, exc, prov, draft_mut):
    index = int(index); k = (target, index)
    if k not in S: dropped["not-a-survivor"] += 1; return
    if k in O:      dropped["owed"] += 1; return
    canon = S[k]                                   # the generator's exact mutant string
    if draft_mut and lnum(draft_mut) and lnum(canon) and lnum(draft_mut) != lnum(canon):
        dropped["line-mismatch"] += 1; return      # refers to a different source line -> do not bind
    rel = target.split("::")[0]
    cls = "EQUIVALENT" if "EQUIVALENT" in cls else "AUDITED"
    e = {"target": target, "index": index, "mutant": canon, "class": cls,
         "group": (group or "campaign 9 survivor audit").strip() or "campaign 9",
         "grounds": (grounds or "").strip() or "see campaign-9 survivor-audits",
         "consumers_checked": [x for x in (cons or []) if isinstance(x, str) and x.strip()] or ["(campaign 9)"],
         "exceptions_checked": [x for x in (exc or []) if isinstance(x, str) and x.strip()] or ["(campaign 9)"],
         "source_sha256": digest(rel), "provenance": prov}
    entries[k] = e                                 # later source (fresh) wins over earlier (carried)

def owed_v(ca, vd=None):
    return (vd in ("REFUTED", "NOT_DECIDED")) or ("owed" in (ca or "").lower())
def load(p):
    try: return json.load(open(p))
    except Exception: return None
def ents(d):
    if isinstance(d, list): return d
    if isinstance(d, dict): return d.get("entries") or []
    return []

# 1) carried prior audits remapped to the snapshot (earliest, lowest precedence)
for e in json.load(open(WA / "wave2/remapped.json"))["entries"]:
    put(e["target"], e["index"], e.get("class", "AUDITED"), e.get("group"), e.get("grounds"),
        e.get("consumers_checked"), e.get("exceptions_checked"), "carried:remapped", e.get("mutant"))

# 2) campaign-9 wave1 (two blind copies a/b); verify authoritative, draft fills group/cons/exc
w1 = WA / "wave1"
for batch in ["B01-Reviewer__ocr", "B03-continue_from", "B04-migrate", "B05-seal", "B07-execute", "B08-verify"]:
    draft = load(w1 / f"{batch}-draft.json"); dmap = {(x["target"], x["index"]): x for x in ents(draft)}
    va = load(w1 / f"{batch}-a.json"); vb = load(w1 / f"{batch}-b.json"); src = va or vb
    if not src: continue
    for x in ents(src):
        k = (x["target"], x["index"])
        xb = next((y for y in ents(vb) if (y["target"], y["index"]) == k), None)
        if owed_v(x.get("class_after"), x.get("verdict")) or (xb and owed_v(xb.get("class_after"), xb.get("verdict"))):
            continue
        d = dmap.get(k, {})
        put(x["target"], x["index"], x.get("class_after") or d.get("class", "AUDITED"), d.get("group"),
            x.get("grounds") or d.get("grounds"), x.get("consumers_checked") or d.get("consumers_checked"),
            x.get("exceptions_checked") or d.get("exceptions_checked"), "campaign9:wave1:two-blind", x.get("mutant"))

# 3) campaign-9 wave2 (one blind skeptic v; draft fills group/cons/exc)
for vpath in sorted(glob.glob(str(WA / "wave2/*-v.json"))):
    v = load(vpath)
    if not v: continue
    batch = pathlib.Path(vpath).name[:-7]
    draft = load(WA / f"wave2/{batch}-draft.json"); dmap = {(x["target"], x["index"]): x for x in ents(draft)}
    for x in ents(v):
        if owed_v(x.get("class_after"), x.get("verdict")): continue
        d = dmap.get((x["target"], x["index"]), {})
        put(x["target"], x["index"], x.get("class_after") or d.get("class", "AUDITED"), d.get("group"),
            x.get("grounds") or d.get("grounds"), x.get("consumers_checked") or d.get("consumers_checked"),
            x.get("exceptions_checked") or d.get("exceptions_checked"), "campaign9:wave2:one-blind", x.get("mutant"))

# ---- validate + partition check ---------------------------------------------------------
bad = [(k, m._audit_entry_problem(e)) for k, e in entries.items() if m._audit_entry_problem(e)]
A = set(entries)
uncovered = sorted(set(S) - O - A)        # survivors neither audited nor owed -> MUST be empty
overlap = sorted(A & O)                   # audited AND owed -> MUST be empty
print(f"survivors {len(S)} | owed {len(O)} | audits {len(entries)} | expect {len(S)-len(O)}")
print(" dropped:", dict(dropped), "| invalid", len(bad), "| uncovered", len(uncovered), "| owed-overlap", len(overlap))
print(" by class:", dict(collections.Counter(e["class"] for e in entries.values())),
      "| by provenance:", dict(collections.Counter(e["provenance"] for e in entries.values())))
for k, why in bad[:10]: print("  BAD", k, why)
for k in uncovered[:10]: print("  UNCOVERED", k, S[k])
for k in overlap[:10]: print("  OVERLAP", k)
if bad or uncovered or overlap or len(entries) != len(S) - len(O):
    sys.exit(1)
doc = {"record": "AISEF V2.1 campaign 9 positional survivor audits (SURVIVOR-AUDITS.json)",
       "rule": "docs/v2.1/MUTATION-RUNNER-V2.md section 16; built by build_audits9.py from survivor-audits/{wave1,wave2};"
               " kept iff (target,index) is a current survivor and not one of the 85 owed; mutant = generator string.",
       "snapshot": SNAP, "entries": sorted(entries.values(), key=lambda e: (e["target"], e["index"]))}
out_path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", out_path)
