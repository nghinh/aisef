"""The probe's RUN.json: failure, stage, preflight verdict, usage, budget, sessions; and a secret scan of every file
the record will carry (the key's value must appear nowhere). Prints nothing of the key."""
import json
import os
import pathlib

here = pathlib.Path(__file__).resolve().parent / "preflight-mycombo"
rec = json.loads((here / "run" / "RUN.json").read_text(encoding="utf-8"))
for k in ("stage", "failure", "delivery_verdict", "delivery_blocked_by", "story_outcomes", "budget_stop", "sessions",
          "final_main", "kernel_digest", "platform", "started", "finished"):
    print(k, "=", json.dumps(rec.get(k), sort_keys=True)[:600])
print("usage =", json.dumps(rec.get("usage"), sort_keys=True, indent=1))
print("budget.spent =", json.dumps((rec.get("budget") or {}).get("spent"), sort_keys=True))
print("preflight.verdict =", (rec.get("preflight") or {}).get("verdict"), "problems =", (rec.get("preflight") or {}).get("problems"))
print("journal =", rec.get("journal"))
key = os.environ.get("NINEROUTER_API_KEY", "")
files = [p for p in here.rglob("*") if p.is_file() and "test-python" not in p.parts and "repo" not in p.parts]
hits = [str(p.relative_to(here)) for p in files if key and key in p.read_bytes().decode("utf-8", "replace")]
print("files scanned:", len(files), "files holding the key value:", hits)
print("files:", sorted(str(p.relative_to(here)) for p in files))
