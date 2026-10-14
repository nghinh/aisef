"""scope8.py OUT_DIR: what campaign 8 measures, and why — the targets whose result is no ground at the head the read-set
was measured at (08b4ee0), and the chain that carries every other result to it.

Since campaign 7's read-set (534435f) the only code that changed is two kill files (`tests/v2/test_v21_r3_conf_policy.py`,
`tests/v2/test_v21_r4_probe_record.py`: an `encoding="utf-8"` named in two child-process calls, the suite's own rule) and
`validation/v2/checker_calibration.py` (the Q0 checker's observed text and its reference to the execution-order table).
The product (`aisef2/`) and the runner (`validation/v2/mutation.py`) are byte for byte campaign 7's.

Every target's current result comes from one of three campaigns; each has its own delta at the one head (with the read-set
of that head) and its own exact reading of the data it read:

    delta-from-289885e   campaign 5's results (snapshot of manifest 5)
    delta-from-a770fbb   campaign 6's results (snapshot of manifest 6)
    delta-from-853da4a   campaign 7's results (snapshot of manifest 7)

    role    REMEASURE  the delta of the target's own base says re-measure (the target file, its kill set, a kill-test
                       closure file or the generator changed), or a kill file of the target reads a changed file and the
                       exact reading does not clear it
            STANDS     the delta's rules and the exact reading clear it; the result is carried from its campaign

Writes OUT_DIR/SCOPE.json and OUT_DIR/targets.txt. Reads committed files only."""
import collections
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[5]
out = pathlib.Path(sys.argv[1])
E = ROOT / "closure-evidence/v2/v2.1"
D = E / "campaign-8"
BASES = {"campaign 5 (289885e)": "289885e", "campaign 6 (a770fbb)": "a770fbb", "campaign 7 (853da4a)": "853da4a"}
CODE_THAT_MAY_CHANGE = {"tests/v2/test_v21_r3_conf_policy.py", "tests/v2/test_v21_r4_probe_record.py",
                        "validation/v2/checker_calibration.py"}


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, encoding="utf-8", check=True).stdout


deltas = {tag: json.loads((D / f"delta-from-{tag}/DELTA.json").read_text()) for tag in BASES.values()}
analysis = {tag: json.loads((D / f"DATA-READ-ANALYSIS-from-{tag}.json").read_text())["targets"] for tag in BASES.values()}
heads = {d["head"] for d in deltas.values()} | {d["read_set"]["commit"] for d in deltas.values()}
assert len(heads) == 1, heads
head = heads.pop()
# the product and the runner are campaign 7's: what moved since its read-set (534435f) outside docs and evidence
moved = sorted(f for f in git("diff", "--name-only", "534435ff84fe303a202d4a340e0172e9e88d7994", head).splitlines()
               if not f.startswith(("docs/", "closure-evidence/")))
assert set(moved) == CODE_THAT_MAY_CHANGE, moved
changed_fn = json.loads((E / "campaign-6/CHANGED-FUNCTIONS.json").read_text())["modules"]
c7 = json.loads((E / "campaign-7/SCOPE.json").read_text())["targets"]
rows = {}
for t, prev in sorted(c7.items()):
    origin = "campaign 7 (853da4a)" if prev["role"] == "REMEASURE" else prev["result_from"]
    tag = BASES[origin]
    d = deltas[tag]["targets"][t]
    now = str(d["verdict"]).startswith("re-measure")
    why = list(d.get("reasons", [])) if now else []
    cleared = None
    if not now and (d.get("data_read") or d.get("read_set_not_measured")):
        a = analysis[tag].get(t)
        # a changed file the kill files OPENED that is a module whose import-time statements are unchanged
        # (reach.watch_from_diff, campaign-6/CHANGED-FUNCTIONS.json) is loaded, not executed: only the changed
        # functions are, and the traces (campaign-6, campaign-7: no kill file reached them) cover those
        if a is None or d.get("read_set_not_measured") or a["listings_that_changed"] or not all(
                changed_fn.get(f) == "unchanged" for f in a["exactly_read_and_changed"]):
            now = True
            why = ["a kill file reads a changed file: " + json.dumps(a["listings_that_changed"] + a["exactly_read_and_changed"])[:300]
                   if a else "the reading of a changed file was not measured"]
        else:
            cleared = {"by": f"campaign-8/DATA-READ-ANALYSIS-from-{tag}.json + campaign-6/CHANGED-FUNCTIONS.json",
                       "listings_that_changed": [], "opened_and_changed": a["exactly_read_and_changed"],
                       "import_time_statements": {f: changed_fn[f] for f in a["exactly_read_and_changed"]}}
    rows[t] = {"role": "REMEASURE" if now else "STANDS", "reasons": why, "result_from_base": origin,
               **({"data_read_cleared": cleared} if cleared else {}),
               "result_from": "campaign 8 (this campaign)" if now else origin}
run = sorted(t for t, r in rows.items() if r["role"] == "REMEASURE")
out.mkdir(parents=True, exist_ok=True)
(out / "SCOPE.json").write_text(json.dumps({
    "record": "AISEF V2.1 — campaign 8 scope: which targets are measured, and why", "head": head, "read_set": head,
    "delta_bases": {k: v for k, v in BASES.items()}, "code_moved_since_campaign_7_read_set": moved,
    "targets": rows}, indent=1, ensure_ascii=False) + "\n")
(out / "targets.txt").write_text("".join(t + "\n" for t in run))
print(len(run), "targets:", [t.split("::")[1] for t in run], "| result from:", dict(collections.Counter(r["result_from"] for r in rows.values())))
