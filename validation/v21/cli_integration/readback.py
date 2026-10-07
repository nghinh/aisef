"""D4 read-back of the integration's run1 (run.sh's last step; read only):
  1. each developer prompt run1 sent, recomputed from run1's journal by this tree's feedback (task, retry_feedback,
     context_pack, composed as Developer.implement composes them) against the prompt_sha256 RUN.json records, and the
     prompt file the fake client received (prompt-NN.txt) against the same hash;
  2. the context pack of each retry prompt, and every seq it cites read back from the journal (story, kind, fields);
  3. that the journal does not hold the pack.
    python3 -P validation/v21/cli_integration/readback.py OUT_DIR
"""
import hashlib
import json
import pathlib
import re
import sys

W = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(W))
from aisef2.app import bundle, feedback  # noqa: E402

I = pathlib.Path(sys.argv[1])
project = bundle.load(json.loads((I / "approved.json").read_text(encoding="utf-8")))
journal = (I / "run1/run/journals/aisef-run.jsonl").read_text(encoding="utf-8")
evs = [json.loads(x)["event"] for x in journal.splitlines() if x.strip()]
by_seq = {e["seq"]: e for e in evs}
reqs = [e for e in evs if e["type"] == "provider/request" and e["data"].get("budget_owner") == "DEVELOPER"]
dev = [s for s in json.loads((I / "run1/RUN.json").read_text(encoding="utf-8"))["sessions"] if s.get("role") == "developer"]
sha = lambda b: hashlib.sha256(b).hexdigest()   # noqa: E731
same = lambda ok: "EQUAL" if ok else "DIFFERENT"   # noqa: E731
bad = [] if len(reqs) == len(dev) else ["sessions and requests differ in number"]
print(f"run1: {len(dev)} developer sessions in RUN.json, {len(reqs)} DEVELOPER provider/request in the journal")
packs = []
for n, (r, s) in enumerate(zip(reqs, dev, strict=False)):   # a count mismatch is in `bad`
    seen = [(e["seq"], e["type"], e["data"]) for e in evs if e["seq"] <= r["seq"]]   # what implement saw
    prompt = feedback.task(project, s["story_id"])
    if any(t == "failure/observed" and d.get("story_id") == s["story_id"] for _, t, d in seen):
        pack = feedback.context_pack(seen, s["story_id"], project)
        prompt += (f"\n\nA previous attempt of this story was not accepted; the kernel observed:\n"
                   f"{feedback.retry_feedback(seen, s['story_id'], project)}\n" + (f"{pack}\n" if pack else "")
                   + "Fix the implementation.")
        packs.append((s, pack))
    sent = I / f"prompt-{n:02d}.txt"
    ok = (sha(prompt.encode("utf-8")) == s["prompt_sha256"], sent.is_file() and sha(sent.read_bytes()) == s["prompt_sha256"])
    bad += [f"{s['story_id']} attempt {s['attempt']}: prompt"] * (not all(ok))
    print(f"{s['story_id']} attempt {s['attempt']} (request seq {r['seq']}): recomputed prompt "
          f"{same(ok[0])} to RUN.json prompt_sha256; {sent.name} {same(ok[1])}")
FIELDS = ("story_id", "parent", "detail", "candidate", "criterion_id", "verdict", "agreement")
KINDS = ("story/begin", "provider/result", "proof/verified")
for s, pack in packs:
    print(f"\n{s['story_id']} attempt {s['attempt']}: the context pack in its prompt")
    print("\n".join("  | " + ln for ln in pack.splitlines()))
    print("  the seqs it cites, read back from run1/run/journals/aisef-run.jsonl:")
    singles = {int(q) for m in re.findall(r"\(journal seq ((?:\d+, )*\d+)\)", pack) for q in m.split(", ")}
    ends = {int(q) for m in re.findall(r"\(journal seq (\d+–\d+)\)", pack) for q in m.split("–")}
    for c in sorted(singles | ends):
        e = by_seq.get(c)
        bad += [f"seq {c}"] * (not (e and e["data"].get("story_id") == s["story_id"]))
        shown = {k: e["data"][k] for k in FIELDS if e and k in e["data"]}
        print(f"   {c} {e and e['type']} {json.dumps(shown)}"
              + ("" if e and e["data"].get("story_id") == s["story_id"] else "  <- NOT an event of this story"))
    bad += [f"seq {c} is a {by_seq[c]['type']}" for c in singles if c in by_seq and by_seq[c]["type"] not in KINDS]
    print(f"  kinds of the seqs cited one by one: {sorted({by_seq[c]['type'] for c in singles if c in by_seq})} (allowed: "
          f"{', '.join(KINDS)}); of the ends of a cited range: {sorted({by_seq[c]['type'] for c in ends if c in by_seq})}")
print(f"\nthe pack's head in the journal: {feedback.PACK_HEAD in journal}; 'context only' in the journal: {'context only' in journal}")
bad += ["the journal holds the pack"] * (feedback.PACK_HEAD in journal or "context only" in journal)
print(f"read-back: {'FAILED: ' + '; '.join(bad) if bad else 'OK'}")
sys.exit(1 if bad else 0)
