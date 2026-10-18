"""From the one saved listing: the rows whose id names minimax (the backing model the probes reported), with limits."""
import json
import pathlib

here = pathlib.Path(__file__).resolve().parent / "listing"
rows = json.loads((here / "models.json").read_text(encoding="utf-8"))["data"]
mm = [r for r in rows if "minimax" in str(r.get("id", "")).lower() or str(r.get("owned_by")) == "minimax"]
for r in mm:
    print(json.dumps({k: r.get(k) for k in ("id", "owned_by", "context_length", "max_completion_tokens")}, sort_keys=True))
combo = [r for r in rows if str(r.get("owned_by")) == "combo"]
print("combo-owned rows:", [r.get("id") for r in combo])
print("combo rows carrying limits:", sum(1 for r in combo if "context_length" in r))
(here / "models-minimax.json").write_text(json.dumps(mm, indent=1, sort_keys=True) + "\n", encoding="utf-8")
