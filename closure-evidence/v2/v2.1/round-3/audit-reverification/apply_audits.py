"""apply_audits.py OUT.json: the campaign-5 remapped audit file with the two-copy re-verification applied.

For each re-verified entry (both copies of audit/out): CONFIRMED/REVISED in both -> the entry stays (class unchanged),
carries `reverification` (both verdicts, the report files) and the first REVISED copy's grounds/consumers/exceptions
(the earlier ones kept as `grounds_before`); REFUTED in both with class_after KILLED/SURVIVED(test owed) -> the entry is
dropped (a kill file now covers it, or it is not audited); a disagreement is refused (printed, exit 3)."""
import collections, glob, json, pathlib, sys
SP = pathlib.Path("/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad")
base = json.loads((SP / "m21/c5/audits-remapped.json").read_text())["mapped"]
by = collections.defaultdict(dict)
for f in sorted(glob.glob(str(SP / "m21/r3/audit/out/*.json"))):
    d = json.load(open(f))
    for e in d["entries"]:
        by[(e["target"], e["index"])][d["copy"]] = {**e, "report": f"audit-reverification/{d['batch']}-{d['copy']}.json"}
# entries REFUTED in both copies whose registration was done (see mutation.py _V21_R3_APPEND) or whose test was written
DROP_BECAUSE = {
    ("aisef2/app/confine.py::wrap", 42): "test_v21_r3_conf_locale registered for wrap",
    ("aisef2/app/confine.py::wrap", 43): "test_v21_r3_conf_locale registered for wrap",
    ("aisef2/app/confine.py::wrap", 44): "test_v21_r3_conf_locale registered for wrap",
    ("aisef2/app/review_ocr.py::findings", 52): "test_v21_kills3_T12b registered for findings",
    ("aisef2/app/review_verify.py::_canon", 4): "tests/v2/test_v21_r4_anchor_nonascii.py",
    ("aisef2/app/review_verify.py::verify", 24): "tests/v2/test_v21_r4_uncalibrated_qualifier.py",
}
out, dropped, revised, confirmed, problems = [], [], 0, 0, []
seen = set()
for e in base["entries"]:
    k = (e["target"], e["index"])
    v = by.get(k)
    if v is None:
        out.append(e)
        continue
    seen.add(k)
    if k in DROP_BECAUSE:
        dropped.append({"target": k[0], "index": k[1], "mutant": e["mutant"], "was": e["class"], "now": DROP_BECAUSE[k],
                        "verdicts": {c: x["verdict"] for c, x in sorted(v.items())}})
        continue
    verdicts = {c: x["verdict"] for c, x in v.items()}
    if set(verdicts.values()) - {"CONFIRMED", "REVISED"} or {x["class_after"].split(" ")[0] for x in v.values()} != {e["class"]}:
        problems.append((k, verdicts, {c: x["class_after"] for c, x in v.items()}))
        continue
    pick = next((v[c] for c in ("a", "b") if v[c]["verdict"] == "REVISED"), v["a"])
    new = dict(e)
    if pick["verdict"] == "REVISED":
        new["grounds_before"] = e["grounds"]
        new["consumers_checked_before"] = e.get("consumers_checked")
    new["grounds"] = pick["grounds"]
    for f in ("consumers_checked", "exceptions_checked"):
        if pick.get(f):
            new[f] = pick[f]
    new["reverification"] = {"snapshot": "289885ef1", "workflow": "wf_412c149a-c87",
                             "copies": {c: {"verdict": x["verdict"], "class": x["class_after"], "report": x["report"]} for c, x in sorted(v.items())}}
    revised += pick["verdict"] == "REVISED"
    confirmed += pick["verdict"] == "CONFIRMED"
    out.append(new)
missing = [k for k in by if k not in seen]
print(f"entries in: {len(base['entries'])}  out: {len(out)}  dropped: {len(dropped)}  revised(first-copy): {revised}  confirmed: {confirmed}")
print("re-verified keys not in the remapped file:", missing)
print("problems:", problems)
if problems or missing:
    sys.exit(3)
doc = {**base, "entries": out, "campaign_5_reverification": {
    "workflow": "wf_412c149a-c87", "snapshot": "289885ef1", "entries_reverified": len(by), "copies_per_entry": 2,
    "dropped_because_a_test_now_kills_them": dropped,
    "rule": "two independent skeptic agents per batch each re-derived every claim at the snapshot, applied the mutant "
            "and ran the tests; an entry stays only if neither refuted it; an entry refuted in both is not an audit"}}
pathlib.Path(sys.argv[1]).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
