#!/bin/zsh
# e2_status.sh D: one line — whether a driver runs on D, STOP, runs done/failed/refused of the campaign's total, provider
# requests and tokens summed over the RESULT.json records, and the last line of D/out/campaign.log.
D=${1:?usage: e2_status.sh D}
r=$(pgrep -f "campaign.py run --campaign $D/" | wc -l | tr -d ' ')
exec nice -n 19 /opt/homebrew/bin/python3 -P -B - "$D" "$r" <<'EOF'
import json, pathlib, sys
d, running = pathlib.Path(sys.argv[1]), sys.argv[2]
out = d / "out"
total = len(json.loads((d / "CAMPAIGN-real.json").read_text(encoding="utf-8"))["runs"]) if (d / "CAMPAIGN-real.json").exists() else 0
res = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out.glob("*/RESULT.json"))]
failed = sum(1 for x in res if x.get("error"))
refused = sum(1 for x in res if x.get("identity") in ("ENDPOINT_MISMATCH", "OPAQUE"))
requests = sum(int(((x["usage"].get("budget") or {}).get("spent") or {}).get("provider_requests") or 0) for x in res)
tokens = {}
for x in res:
    for k, v in (x["usage"].get("tokens") or {}).items():
        tokens[k] = tokens.get(k, 0) + int(v or 0)
log = out / "campaign.log"
last = (log.read_text(encoding="utf-8").splitlines() or ["-"])[-1] if log.exists() else "-"
print(f"{'RUNNING ' if running != '0' else ''}{'STOP ' if (out / 'STOP').exists() else ''}done {len(res)}/{total} failed {failed} "
      f"refused {refused} requests {requests} tokens in {tokens.get('input', 0)} out {tokens.get('output', 0)} | {last}")
EOF
