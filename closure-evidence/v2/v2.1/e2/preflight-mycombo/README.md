# E2 lane PF — the one preflight-only `aisef run` for alias `mycombo` on 9router (2026-10-18 12:54 +07)

Authority: owner chat 2026-10-18 "Tôi đồng ý agent chạy trực tiếp với model tên mycombo trên 9router (không cần lo về chi
phí)" (`round-5/OWNER-DECISION-2026-10-18-E2.md`); the lane brief allowed exactly one preflight-only run, requests capped
at 4, after checking that canary tier 1's store stats were identical (they are: both `09c621f5…`).

| | |
|---|---|
| tree | lane worktree at `2ac9b80` (branch `lane/e2-provider`), `aisef2/` unchanged by the lane; `kernel_digest` `b28ff13a…` (RUN.json) |
| command | `argv.json`: `nice -n 19 python3 -P -B -m aisef run --project calc/approved.json --settings probe-settings.json --repo calc/repo --out run --anchor-out run.anchor`, environment built by `tools/run_probe.py` (names in `env-names.txt`; the key only in the child's environment) |
| settings | `probe-settings.json` (sha256 `4f8f44c0…`) = `../settings/arm-aisef.json` of the first draft with `served_model: "mycombo"` and `budget.provider_requests: 4` (3 chat probes + 1 listing) |
| workload | stock `calc-1-story` rebuilt in scratch by `tools/build_calc.py` (init → baseline commit → seal → approve BC-ADD as `human:lane-pf-operator`, a technical approval of a stock example, **not** an owner acceptance → lint READY); `--check` ready for every settings file first |
| client | **never the real binary**: PATH = `tools/stubbin-opencode.sh` + `/opt/homebrew/bin:/usr/bin:/bin`; XDG_CONFIG_HOME = `tools/xdg-opencode.json` (provider 9router at the attested endpoint, key `{env:NINEROUTER_API_KEY}`); the operator's own OpenCode configuration was not read by the run |
| preflight verdict | **OPAQUE** → `IdentityStop`, `aisef run: refused: the route is not attested: probe 0: served by 'MiniMax-M3', not 'mycombo' (an alias or a re-route); probe 1 …; probe 2 …` (`run.stderr`), exit **2** |
| observation | listing HTTP 200, `id: mycombo`, `owned_by: combo` (listed, owner as expected); 3 probes HTTP 200, `served_model` **`MiniMax-M3` ×3**, `system_fingerprint` **NOT_EXPOSED** ×3 (`run/preflight/PREFLIGHT.json`) |
| spend | 4 provider requests, 6,147 input + 6 output tokens (each probe: 2,049 in / 2 out for a 7-word prompt — the router's accounting), `unaccounted: []`; cost **null** (`status: unknown`, "the settings give no price table") |
| run | `stage: preflight`, no session (`sessions: []`), no journal (the RunScope never began), `delivery_verdict: NOT_REACHED`, no anchor written (refused before it); wall 9.9 s |
| OpenCode store | `store-before.json` == `store-after.json` (sha256 `89dd3be3…` both; `store_stat.py` on `$HOME`) |
| secrets | every file here scanned in-process for the key's value: none holds it (`tools/inspect_record.py`); the copies are unedited |

The reading of this result, the three E2 settings files and the risks: `../PROVIDER-COMPAT-mycombo.md`.
