# Canary B-09, tier 2b — three stories, review fix-loop, real model (2026-10-15 05:55–05:59 +07)

Authority: owner chat 2026-10-15 "Đồng ý chạy model thật" and "Tôi uỷ quyền cho bạn toàn quyền chạy các lệnh cần thiết"
(B-09 canary, ceiling 5 USD). The owner ran `run-tier2b.sh` in their own terminal.

| | |
|---|---|
| tree | product `aisef2/` tree `1d4f0156f568f240f49fbbc10e5a366a13b18f58` (HEAD `ce6ea87`), public CLI `python3 -m aisef` |
| workload | stock `calc-3-stories`: S1 (INTRODUCE `add`, PRESERVE stdlib-only `file_artifact`), S2 (`mul`), S3 (`total`, PRESERVE `add`); 4 contracts approved by `human:canary-operator` — a technical approval of a stock example, not an acceptance |
| settings | route `9router/ds/deepseek-v4-pro`; `review: {policy: fix-loop, min_severity: low, finder: model}`; ceilings 24 requests, 300 turns, 2,000,000 input, 60,000 output |
| result | `delivery_verdict` **PASS**; S1, S2, S3 `COMMIT`; **5/5 obligations delivered and SATISFIED at the last proof**, agreement true (two probe classes: `python_callable_v2`, `file_artifact`) |
| `aisef run --verify` (offline, expected anchor) | **VERIFIED**, 212 journal events, no problems (`verify.out`) |
| spend | 10 provider requests (4 preflight + 6 sessions), 37 turns; input 266,109 + cache read 1,036,160 (1,308,539 against the 2,000,000 ceiling); output 5,657 (+930 reasoning) against 60,000; unaccounted `[]` |
| cost | **0.431394 USD** (`status: known`, DeepSeek peak table = upper bound; 9router's own price unknown): developers 0.0978 / 0.0706 / 0.0707, reviewers 0.0598 / 0.0617 / 0.0624 (+ preflight 0.0084) |
| wall | 214.6 s; no retries; every session attempt 1 |
| review | three reviewer sessions under `fix-loop`, each `findings: []` — the repair loop was configured and **never triggered**, because nothing was found |
| OpenCode store | changed by the six client sessions (`opencode.db`, wal/shm, `log/`, `snapshot/`); direct evidence: the `ses_*` ids in `sessions/` |
| cumulative canary spend | 0.0084 + 0.1592 + 0.4314 = **0.599 USD** of the 5 USD ceiling |

## What it shows, and what it does not

* A multi-story plan with two probe classes, PRESERVE obligations and a model reviewer runs end to end with a real model
  and verifies offline; cost per story ≈ 0.14 USD, ~70 s.
* **Finding C-1 repeated:** the delivered `main` again carries `__pycache__/*.pyc` (`delivered-files.txt`).
* **Not shown:** the repair path. All three stories were delivered on attempt 1 with no findings, so `fix-loop`, `--parent`
  continuation after a failure, a refused candidate, a REFUTED probe with a real model, and OCR review remain unexercised
  with a real model. A workload that makes the model fail first (a spec with a subtle clause) is needed for that; it is
  proposed in `docs/v2.1/` as the next canary step, not run.
* Nothing here is evidence about efficacy against a direct agent, or about LedgerLock-sized work.
