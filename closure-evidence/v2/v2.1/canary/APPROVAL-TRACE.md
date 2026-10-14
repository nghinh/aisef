# Canary B-09 — where the permission to run a paid model and the 5 USD ceiling come from

Written 2026-10-15 at the owner's request ("dẫn bản phê duyệt cho trần 5 USD: nội dung, thời điểm và phạm vi"). It records
what exists; it creates no approval and amends no record (`RELEASE-DECISIONS.json` is untouched: seq 1–5, the last is
2026-10-06).

## What the owner said (the session transcript; times UTC and +07 on 2026-10-15)

| time | who | words | what it is |
|---|---|---|---|
| 2026-10-14T21:51:21Z (04:51) | owner | "Chưa gọi provider trả tiền. Chuẩn bị một kế hoạch canary nhỏ để tôi duyệt B-09, gồm workload, model/client, giới hạn chi phí, số lượt tối đa, điều kiện dừng và tiêu chí thành công." | the standing position before the approval: no paid call, prepare a canary plan for approval |
| 2026-10-14T22:17Z (05:17) | agent | listed among "không nằm trong ước tính trên (cần anh quyết)": "canary B-09 với mô hình thật (đề xuất bậc 1–2, trần 5 USD)" | the proposal the owner answered; the 5 USD figure is the agent's, taken from `docs/v2.1/decisions/B-09-CANARY-THEN-CAMPAIGN.md` ("Duyệt ngay (nhỏ nhất): bậc 1 + bậc 2, trần 5 USD") |
| **2026-10-14T22:23:49Z (05:23:49)** | owner | **"Đồng ý chạy model thật"** | the approval: of that proposal as worded — real model, canary tiers 1–2, ceiling 5 USD. The owner did not restate the figure |
| 2026-10-14T22:52:18Z and 22:52:37Z (05:52) | owner | ran `t1/run-tier1.sh` and `t2/run-tier2.sh` in their own terminal | tiers 1 and 2, run by the owner (the agent session's own paid call had been refused by the permission gate) |
| 2026-10-14T22:55:59Z (05:55:59) | owner | ran `t3/run-tier2b.sh` | tier 2b (`calc-3-stories`, `review.fix-loop`, ceilings 24 requests / 2,000,000 input / 60,000 output), run by the owner |
| **2026-10-14T22:57:49Z (05:57:49)** | owner | **"Tôi uỷ quyền cho bạn toàn quyền chạy các lệnh cần thiết"** | a delegation to the agent to run the commands needed; after tier 2 and during tier 2b; it names no ceiling and no paid call |

## What was not found

* No document in the repository in which the owner states the 5 USD ceiling in their own words.
  `docs/v2.1/decisions/B-09-CANARY-THEN-CAMPAIGN.md` still reads "ĐỀ XUẤT, CHƯA DUYỆT" and was not edited.
* `RELEASE-DECISIONS.json` has no entry for B-09. The entry the agent's decision analysis proposed (a technical copy,
  seq 6) was **not** written: the figure is the agent's proposal accepted in chat, and an entry saying "the owner
  approved 5 USD" would state more than the owner said. The chat messages above are the approval, as they are.
* The 2026-09-05 directive ("ngân sách agent $120–180", `memory/ai-sdlc-directives.md` item 12) is the budget of the
  whole plan's agent work, not a canary approval; it is not relied on.

## Discrepancies, stated

1. **Tier 2b is wider than the dossier's words.** The dossier's tier 2 is "một lượt AISEF calc 1 story"; tier 2b is a
   3-story plan with a model reviewer under `fix-loop`. It stayed inside the 5 USD ceiling and the owner ran it
   themselves, but it is not a literal tier of the dossier.
2. **Tier 2's input ceiling (2,000,000) is above the dossier's (1,000,000)**, set by the agent inside the 5 USD ceiling
   (worst case 2.80 USD without cache) and stated to the owner before they ran it.
3. The dossier's preflight count (3 requests) was wrong: the preflight is 4. Tier 1's ceiling was set to 4.

## The amount

| run | `usage.cost.value` (USD) | by |
|---|---|---|
| tier 1 (preflight only) | 0.008423 | reported tokens × the price table in the settings |
| tier 2 (1 story, includes its preflight) | 0.159152 | same |
| tier 2b (3 stories, includes its preflight) | 0.431394 | same |
| **total** | **0.598969** (≈ 0.599) | |

**It is an estimate, not a bill.** Each figure is the telemetry the client reported (`unaccounted: []`) multiplied by
DeepSeek's published peak prices (`source` and `effective_date` are in each settings file) — an upper bound for a route
served by 9router, whose own price is not known here. The provider's invoice or dashboard was not consulted; nothing
confirms the amount from the provider's side.

## What the remaining ceiling is not

The unspent ceiling (5 − 0.599 = about 4.40 USD) is not an authorization for further experiments. No paid run is
authorized beyond tiers 1, 2 and 2b; the next one needs the owner's explicit approval. What the three runs prove is the
flows they ran (preflight; one story; three stories with a model reviewer that found nothing); they do not prove the
repair path, OCR review, or any benefit over a direct agent.
