"""One source for the E2 settings (mycombo on 9router): arm-direct, arm-aisef, arm-aisef-plus into the worktree's
closure-evidence/v2/v2.1/e2/settings/, and the preflight-only probe variant (budget.provider_requests 4) into scratch.
Derived from canary tier-2b's settings-t3.json; budget and timeouts are EXPERIMENT-PLAN's hard ceilings; no `prices`
(the router's price is unknown: cost must be reported null, never 0)."""
import copy
import hashlib
import json
import pathlib
import sys

W = pathlib.Path("/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/wf_830a4f0d-db8-1")
S = pathlib.Path(__file__).resolve().parent

BASE = {
    "format": "aisef-v2-run/1",
    "client": "opencode",
    "route": "9router/mycombo",
    "provider": {"name": "9router", "endpoint": "https://9router.vnteki.com/v1", "api_key_env": "NINEROUTER_API_KEY",
                 # the preflight-only probe (2026-10-18 12:54 +07, preflight-mycombo/) was refused with served_model
                 # "mycombo": the router reports the BACKING model in every answer ("MiniMax-M3", 3 of 3 probes). The
                 # kernel attests only when every probe's reported model equals served_model (preflight.py:136-137), so
                 # the templates name the observed backing model; a run whose preflight sees another one is refused
                 # (exit 2, recorded, 4 requests spent) — see PROVIDER-COMPAT-mycombo.md, risks
                 "served_model": "MiniMax-M3", "listed_owner": "combo",
                 # not in the listing's mycombo row (it carries no context_length / max_completion_tokens): carried over
                 # from canary tier-2b, NOT verified for mycombo
                 "model_limit": {"context": 200000, "output": 32768}},
    "client_env": ["NINEROUTER_API_KEY"],
    "budget": {"provider_requests": 58, "turns": 700, "input_tokens": 30000000, "output_tokens": 500000},
    "max_turns_per_session": 80,
    "limits": {"PLAN": 0, "DEVELOPER": 2, "REVIEW": 1, "SECURITY": 1, "INTEGRATION": 0, "ENVIRONMENT": 1, "PROVIDER": 1},
    "timeouts_s": {"developer": 1800, "reviewer": 900, "tool": 600, "probe": 120},
    "preflight": {"chat_probes": 3},
}

arms = {
    "arm-direct": copy.deepcopy(BASE),
    "arm-aisef": copy.deepcopy(BASE),
    "arm-aisef-plus": {**copy.deepcopy(BASE), "review": {"policy": "fix-loop", "min_severity": "high", "finder": "model"}},
}
dest = W / "closure-evidence/v2/v2.1/e2/settings"
dest.mkdir(parents=True, exist_ok=True)
for name, doc in arms.items():
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    (dest / f"{name}.json").write_text(text, encoding="utf-8")
    print(f"{name}.json sha256 {hashlib.sha256(text.encode()).hexdigest()}")

# probe-settings.json (served_model "mycombo", budget.provider_requests 4) was written by the first revision of this
# script and is the file the one probe ran with: it is kept as run (sha256 4f8f44c0…), never regenerated
if not (S / "probe-settings.json").exists():
    probe = copy.deepcopy(arms["arm-aisef"])
    probe["budget"]["provider_requests"] = 4       # 1 listing + 3 chat probes: the first session request would exceed it
    text = json.dumps(probe, indent=1, sort_keys=True) + "\n"
    (S / "probe-settings.json").write_text(text, encoding="utf-8")
    print(f"probe-settings.json sha256 {hashlib.sha256(text.encode()).hexdigest()}")

# the probe's isolated client configuration (XDG_CONFIG_HOME): provider 9router at the attested endpoint, key by env ref —
# the operator's own ~/.config/opencode/opencode.json is never read by the probe
(S / "xdg" / "opencode").mkdir(parents=True, exist_ok=True)
(S / "xdg" / "opencode" / "opencode.json").write_text(json.dumps(
    {"provider": {"9router": {"options": {"baseURL": "https://9router.vnteki.com/v1", "apiKey": "{env:NINEROUTER_API_KEY}"}}}},
    indent=1) + "\n", encoding="utf-8")
print("xdg config written")
