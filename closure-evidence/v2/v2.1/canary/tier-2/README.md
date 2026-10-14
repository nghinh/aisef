# Canary B-09, tier 2 — one story with a real model (2026-10-15 05:52 +07)

Authority: owner chat 2026-10-15 "Đồng ý chạy model thật" (B-09 canary, tiers 1–2, ceiling 5 USD). The owner ran
`run-tier2.sh` in their own terminal.

| | |
|---|---|
| tree | product `aisef2/` tree `1d4f0156f568f240f49fbbc10e5a366a13b18f58` (HEAD `581445d`), public CLI `python3 -m aisef` |
| workload | stock example `aisef bundle init --example calc-1-story` (one story, one `python_callable` contract BC-ADD: `app.calc.add(a, b)` returns the sum), contract approved by `human:canary-operator` — a technical approval of a stock example, **not** an acceptance of the product |
| route | `9router/ds/deepseek-v4-pro`, client `opencode` 1.18.31; preflight ATTESTED (4 requests, 6,270 input + 34 output tokens) |
| result | `delivery_verdict` **PASS**; S1 `COMMIT`; proof: C-ADD SATISFIED at `11dddc4`, agreement true; `aggregate_min_grade` ATTESTED; `story_errors` []; `no_progress` [] |
| `aisef run --verify` (offline, with the expected anchor) | **VERIFIED**, 68 journal events, no problems (`verify.out`) |
| spend | 6 provider requests (4 preflight + 2 sessions), 13 turns, input 94,505 + cache read 363,904 (= 464,679 against the 2,000,000 ceiling), output 2,096 (+425 reasoning) against 40,000; unaccounted `[]` |
| cost | **0.159152 USD** (`status: known`, DeepSeek peak table = upper bound; 9router's own price not known): developer 0.0828 (8 steps, 34.2 s), reviewer 0.0679 (5 steps), preflight 0.0084 |
| wall | 72.9 s |
| review | reviewer session ran (5 steps) and returned `{"findings": []}`; settings carry no `review` key, so the 2.0.0 rule applied (advisory): the fix-loop, the OCR finder and `--parent` continuation were **not** exercised by this run |
| OpenCode store | changed, as expected: `opencode.db` (+wal/shm), `log/`, `snapshot/` by the two client sessions (`ses_*` ids in `sessions/`, timestamps inside the run window) — direct evidence, not inferred |
| cumulative spend of the canary | tier 1 0.0084 + tier 2 0.1592 = **0.168 USD** of the 5 USD ceiling |

## What the run shows, and what it does not

* The product path install → seal → approve → lint → `run --check` → `run` → `--verify` works end to end with a real model,
  a real client and the real preflight, on one trivial story, on macOS without confinement.
* **Finding C-1 (friction, product-adjacent):** the delivered `main` commit contains four `__pycache__/*.pyc` files
  (`delivered-stat.txt`). The stock example repo has no `.gitignore`, and the kernel commits what the candidate leaves.
  A new user's first delivered repository carries bytecode.
* Not shown: review quality, a story that fails and is repaired, a multi-story plan, `--parent` continuation, OCR review,
  Linux confinement with a real model, anything about efficacy against a direct agent. One story with one function is
  not evidence about those.
