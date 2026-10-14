# Canary B-09, tier 1 — real preflight only (2026-10-15 05:52 +07)

Authority: owner chat 2026-10-15 "Đồng ý chạy model thật" (B-09 canary, tiers 1–2, ceiling 5 USD, per
`docs/v2.1/decisions/B-09-CANARY-THEN-CAMPAIGN.md`). The owner ran `run-tier1.sh` in their own terminal; the paid call was
not made by the agent session.

| | |
|---|---|
| tree | product `aisef2/` tree `1d4f0156f568f240f49fbbc10e5a366a13b18f58` (HEAD `bf45e0f`), public CLI `python3 -m aisef run` |
| route | `9router/ds/deepseek-v4-pro` (provider `9router`, client `opencode` 1.18.31, sha256 `16c960ba…`) |
| preflight verdict | **ATTESTED**: listing `ds/deepseek-v4-pro`, owned_by `ds`; 3 probes HTTP 200, `served_model` = `deepseek-v4-pro`, one `system_fingerprint` |
| spend | 4 provider requests, 6,270 input + 37 output tokens, unaccounted `[]`; cost **0.008423 USD** (`status: known`, DeepSeek peak price table — an upper bound; 9router's own price is not known here), wall 12.8 s |
| run | stopped by its budget as designed (`max_provider_requests: 4 of 4`); no session started (`sessions_started: 0`); `delivery_verdict: NOT_REACHED` (not a failure of the product) |
| OpenCode store | stat before/after identical (`store-before.json`, `store-after.json`): the preflight is the kernel's own HTTP, no client session |
| finding | the preflight needs **4** requests (3 chat probes + 1 listing); the dossier's tier 1 said 3 — corrected here, to be corrected in B-09 |
| not shown | anything about review quality, delivery, or cost of a story: tier 2 |

Raw files: `run/` (RUN.json, EVIDENCE.json, preflight, journal), `settings-t1.json`, stdout/stderr, anchor.
