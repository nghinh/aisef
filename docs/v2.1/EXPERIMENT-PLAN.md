# AISEF 2.1 — Kế hoạch thí nghiệm có đối chứng (chưa chạy; chờ chủ dự án duyệt ngân sách)

**Trạng thái: KẾ HOẠCH.** Không lượt chạy trả tiền nào đã được thực hiện. Harness và replay offline đã có và đã kiểm
(`validation/experiments/harness.py`, `tests/v2/test_v21_experiment.py`). Lệnh chạy thật cần chủ dự án duyệt một ngân
sách, chọn workload mới, và ký duyệt evaluator ẩn.

## Câu hỏi

Cùng một client, cùng model, cùng task, cùng ngân sách: AISEF 2.1 có giao sản phẩm đúng yêu cầu **nhiều hơn** agent chạy
trực tiếp không, và đổi lại tốn bao nhiêu (token, tiền, thời gian, công người)?

## Các cánh (một cặp chỉ khác một biến — `pair_problems` từ chối mọi khác biệt khác)

| Cánh | Là gì | Biến đang thử |
|---|---|---|
| A `direct` | `opencode run` một lần trên task công khai (requirements.md), không bundle, không contract, không stimulus ẩn; harness commit những gì client để lại | — (đối chứng) |
| B `aisef` | `aisef run` 2.1, settings không có `review` (review advisory như 2.0.0) | orchestration |
| C `aisef+` | B + `"review": {"policy": "fix-loop", "min_severity": "high"}` | đúng một cải tiến: fix loop của review |

Giữ giống nhau giữa các cánh (manifest ghi và niêm phong): nhị phân client + phiên bản, route, provider settings, commit
baseline (cây sạch, digest `git archive` + digest file sau giải nén), văn bản task công khai, trần ngân sách, wall time.

## Workload

| ID | Loại | Ghi chú |
|---|---|---|
| W1 | greenfield **mới** (chưa từng dùng phát triển AISEF) | LedgerLock **không** dùng làm bằng chứng hiệu quả: stimulus ẩn của nó đã commit công khai và là workload phát triển (360° §3.5) |
| W2 | brownfield: một repo nhỏ có sẵn + một requirements delta | để đo trên mã không do AISEF tạo |
| (tham chiếu) | LedgerLock | chỉ để so với smoke #2, đánh dấu "đã lộ đề" |

Evaluator ẩn của mỗi workload: một bundle contract **do chủ dự án duyệt**, không đưa vào bất kỳ cánh nào;
`harness.leaks()` quét mọi luồng phiên — một chuỗi stimulus lọt vào phiên làm kết quả đó `valid: false`.

## Đo gì (mỗi lượt một bản ghi kết quả trích `manifest_sha256`; lượt hỏng vẫn được giữ)

- tỉ lệ contract ẩn SATISFIED trên candidate cuối (lỗi thoát = contract ẩn không thoả trên `main` đã giao);
- **từ chối sai**: candidate bị AISEF rollback mà evaluator ẩn chấm đạt (candidate SHA có trong journal);
- token theo lớp, request, retry, wall time (`aisef2/app/usage.py`); tiền theo bảng giá trong settings — không có giá thì `null`;
- công người: số contract phải duyệt, thời gian duyệt (tự khai, phút).

## Dự toán (tính từ số đo thật, không đoán)

Hồ sơ token của **một** lượt AISEF đo được ở smoke #2 (LedgerLock, 7 story, DeepSeek V4 Pro, 64 phút):
1 617 117 input không cache · 17 188 864 cache read · 313 336 output (gồm 244 483 reasoning). Phần developer (gần cánh A):
1 175 503 · 14 253 568 · 210 664.

Bảng giá chính thức `deepseek-v4-pro` đọc ngày 2026-10-06 tại https://api-docs.deepseek.com/quick_start/pricing/
(USD / 1M token, off-peak / peak): cache hit 0,022 / 0,044 · cache miss 0,66 / 1,32 · output 1,98 / 3,96.

| | Peak | Off-peak |
|---|---|---|
| một lượt AISEF (B hoặc C) | 4,13 USD | 2,07 USD |
| một lượt direct (A, ước theo phần developer) | 3,01 USD | 1,51 USD |
| **pilot 18 lượt** (2 workload × 3 cánh × 3 lần lặp) | **67,7 USD** | **33,8 USD** |
| dự phòng ×2 cho phương sai | 135 USD | 68 USD |

**Đề nghị duyệt: 140 USD** (nằm trong khoảng 120–180 USD đã nêu trước đây), chạy off-peak khi có thể. Trần cứng mỗi lượt:
input 30M, output 0,5M, 58 request, 700 turn; trường hợp xấu nhất một lượt (30M input không cache, peak) ≈ 41,6 USD — vì
thế quy tắc dừng của chiến dịch là dừng khi chi phí `known` cộng dồn chạm ngân sách duyệt.

**Giả định phải kiểm lại đúng ngày chạy:** (1) route đi thẳng DeepSeek — nếu đi qua router của chủ dự án thì giá là giá
router; (2) trang giá chính thức có ghi tên model cũ được phục vụ bởi V4.1-Flash; một nguồn thứ ba nói `deepseek-v4-pro`
cũng bị chuyển — **chưa xác nhận**: lượt chạy ghi `identity_confidence: provider_reported` và model mà provider trả về;
(3) hồ sơ token của W1/W2 khác LedgerLock — sau 3 lượt đầu, dự toán được tính lại từ `usage` thật.

## Cấu hình thử (mẫu; điền những chỗ `<...>`)

Settings của cánh C (cánh B: bỏ khoá `review`):

```json
{"format": "aisef-v2-run/1", "client": "opencode", "route": "deepseek/deepseek-v4-pro",
 "provider": {"name": "deepseek", "endpoint": "https://api.deepseek.com/v1", "api_key_env": "DEEPSEEK_API_KEY",
              "served_model": "deepseek-v4-pro", "listed_owner": "deepseek", "model_limit": {"context": 1000000, "output": 32000}},
 "client_env": [], "budget": {"provider_requests": 58, "turns": 700, "input_tokens": 30000000, "output_tokens": 500000},
 "max_turns_per_session": 80, "limits": {"PLAN": 0, "DEVELOPER": 2, "REVIEW": 1, "SECURITY": 1, "INTEGRATION": 0,
 "ENVIRONMENT": 1, "PROVIDER": 1}, "timeouts_s": {"developer": 1800, "reviewer": 900, "tool": 600, "probe": 120},
 "preflight": {"chat_probes": 2},
 "review": {"policy": "fix-loop", "min_severity": "high"},
 "prices": {"currency": "USD", "input_per_mtok": 1.32, "cache_read_per_mtok": 0.044, "cache_write_per_mtok": 1.32,
            "output_per_mtok": 3.96, "source": "api-docs.deepseek.com/quick_start/pricing (peak)", "effective_date": "<ngày chạy>"}}
```

(`limits` phải nêu mọi owner của taxonomy; mẫu trên đã được `settings.load` chấp nhận. Trang giá không có giá
"cache write" riêng — mẫu đặt bằng giá cache miss, là cận trên. Kiểm bằng `aisef run --check` trước khi chạy.) Manifest mỗi cánh: xem
`tests/v2/test_v21_experiment.py::Experiment.manifest` — khoá đóng, niêm phong, `pair_problems` phải rỗng trước khi chạy.

## Trình tự

1. Chủ dự án: duyệt ngân sách; chọn W1/W2; duyệt evaluator ẩn (`aisef bundle approve`, từng contract).
2. Đóng băng manifest 18 lượt; `harness.py pair` cho từng cặp phải PASS.
3. Replay offline lượt khô với client giả (đã có trong test) trên chính workload thật.
4. Chạy, sau mỗi lượt ghi kết quả; sau 3 lượt tính lại dự toán; dừng khi chạm ngân sách.
5. Báo cáo: mọi lượt (cả lượt hỏng), lỗi thoát, từ chối sai, chi phí, thời gian, công người — không kết luận vượt n.
