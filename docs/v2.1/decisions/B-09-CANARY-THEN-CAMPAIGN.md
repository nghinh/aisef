# B-09 — Ngân sách: canary nhỏ nhất trước, chiến dịch sau

**Trạng thái: ĐỀ XUẤT, CHƯA DUYỆT.** Chưa có lượt chạy trả tiền nào. Không có gì ở đây được chạy trước khi chủ dự án
duyệt từng bậc.

## Nguồn giá và giả định

- Giá chính thức `deepseek-v4-pro`, đọc 2026-10-06 tại https://api-docs.deepseek.com/quick_start/pricing/ (USD/1M token,
  off-peak / peak): cache hit 0,022 / 0,044 · cache miss 0,66 / 1,32 · output 1,98 / 3,96. Không có giá cache-write riêng:
  tính bằng giá cache miss (cận trên). **Kiểm lại đúng ngày chạy**; nếu route đi qua router thì dùng giá router.
- Hồ sơ token đo ở smoke #2 (một lượt AISEF, LedgerLock 7 story, 64 phút): 1 617 117 input không cache · 17 188 864 cache
  read · 313 336 output. Tỉ lệ cache read ≈ **91 %** input. **Giả định cache:** dự toán dưới đây giữ tỉ lệ đó; nếu cache
  không có tác dụng (provider/route khác), chi phí input tăng ~11 lần — xem cột "không cache".
- Số request mỗi lượt AISEF: preflight 3 + mỗi story 2 phiên (developer, reviewer) + retry. LedgerLock 7 story ≈ 17–30.

## Các bậc (mỗi bậc chỉ chạy khi bậc trước đạt điều kiện qua)

| Bậc | Chạy gì | Request | Trần cứng (settings) | Chi phí dự kiến (peak) | Xấu nhất trong trần (peak, không cache) | Điều kiện qua |
|---|---|---|---|---|---|---|
| 0 | khô: replay offline + `validation/v21/cli_integration/run.sh` (đã chạy, 0 USD) | 0 | — | 0 | 0 | đã đạt (`docs/v2.1/evidence/cli-integration-4fd070a.out`) |
| 1 | preflight thật: `aisef run` tới bước preflight với route thật, `budget.provider_requests = 3` (dừng ngay sau preflight) | 3 | 3 req, 2 000 input, 100 output | < 0,01 | < 0,01 | ATTESTED; model provider trả về = model khai báo |
| 2 | một lượt AISEF calc 1 story (ví dụ đóng gói) | ≤ 8 | 8 req, 1M input, 30k output | ≈ 0,6 (1/7 lượt smoke #2) | 1M × 1,32 + 30k × 3,96 = **1,44** | PASS hoặc thất bại có phân loại; `usage.cost.status = known`; không `unaccounted` |
| 3 | một cặp trên W1: cánh A (direct) + cánh C (AISEF+fix-loop) | ≤ 60 | mỗi lượt 30M input, 0,5M output, 58 req | ≈ 7,1 | 2 × (30M × 1,32 + 0,5M × 3,96) = **83** | quét rò rỉ sạch; `pair_problems` rỗng; dự toán tính lại từ `usage` thật |
| 4 | pilot 18 lượt (EXPERIMENT-PLAN) | ≤ 18 × 58 | như bậc 3; **dừng khi chi phí `known` cộng dồn chạm trần đã duyệt** | 67,7 (33,8 off-peak) | bị chặn bởi quy tắc dừng | báo cáo theo EXPERIMENT-PLAN |

## Đề nghị

- **Duyệt ngay (nhỏ nhất): bậc 1 + bậc 2, trần 5 USD.** Đủ để kiểm route thật, giá thật, cache thật và hồ sơ token thật
  trên một lượt nhỏ.
- Sau bậc 2, trình lại dự toán bậc 3–4 tính từ số đo thật; khi đó mới xin 140 USD (hoặc con số mới).
- Quy tắc dừng của mọi bậc: dừng khi chi phí `known` cộng dồn chạm trần; một lượt có chi phí `unknown` dừng chiến dịch
  cho tới khi được đối soát (đúng luật của `aisef run --parent`).

## Cần chủ dự án

Duyệt (hoặc sửa) bậc 1–2 và trần 5 USD; cấp credential cho route; chọn ngày chạy (off-peak nếu được).
