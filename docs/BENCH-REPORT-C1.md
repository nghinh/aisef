# Cohort C-1 — harness có đổi kết cục khi model không phải frontier?

Đo 2026-09-12, 19:10 → <GIỜ-KẾT>, một máy, tuần tự. Chi phí nhà cung cấp báo:
**0,00 USD** ở toàn bộ dòng (xem §6).

Quan sát ghi **trong lúc chạy** nằm ở [BENCH-OBSERVATIONS-C1](BENCH-OBSERVATIONS-C1.md);
báo cáo này là tổng kết sau khi đóng đợt, và nó **không** sửa lại quan sát nào —
kể cả quan sát về sau hoá ra sai (O-2/O-3 là một giả thuyết đã bị chính số liệu
của đợt bác bỏ, và nó được giữ nguyên tại chỗ).

## 1. Câu hỏi và vì sao nó đáng đo

Ba đợt đo trước đều chạy trên model frontier và đều ra "không khác gì". Câu trả
lời ấy đúng với thứ đã đo, nhưng nó không trả lời câu hỏi trung tâm của sản
phẩm: **guard và cổng có cứu được một agent yếu hơn không?** C-1 là lần đầu
chạy với một model không phải frontier.

## 2. Giao thức — đóng băng trước khi chạy

- Giao thức: [BENCH-PROTOCOL-v1.3 § Addendum C-1](BENCH-PROTOCOL-v1.3.md), viết
  và commit **trước** lượt chạy đầu tiên.
- Dữ liệu: 12 task A-2, byte của từng task ghim bởi `tests/bench/tasks/MANIFEST.sha256`.
- Thiết kế: 12 task × 3 lượt × 2 điều kiện = 72 phiên có kế hoạch.
  - `opencode` — có harness: guard plugin, biến môi trường `AISEF_*`, công cụ `aisef tool *`.
  - `opencode-bare` — trần: cùng model, cùng đề bài, không guard, không công cụ.
- Chấm: F2P/P2P bằng **test ẩn**, áp sau khi ứng viên đã chốt; guard **không**
  tham gia phép chấm (nhánh trần không có guard — hỏi guard là hỏi sai chỗ).
- Model nền sau alias `9router/mycombo`: **MiniMax-M2.7**, theo lời khai của chủ
  dự án ngày 12/09. Harness không tự xác minh được điều này; nó là *lời khai*,
  và được ghi là lời khai.

Dựng lại bảng:

```
python3 -m tests.bench report  --cohort mycombo
python3 -m tests.bench analyze
```

## 3. Kết quả

<BẢNG-KẾT-QUẢ>

## 4. Đo lại sau đợt chạy — thứ `pass@1` không nhìn thấy

<BẢNG-ANALYZE>

## 5. Điều đợt đo này thực sự đo được

<KẾT-LUẬN>

## 6. Khai báo đầy đủ những gì **không** sạch

Mục này dài hơn người ta muốn đọc, và đó là chủ ý: một đợt đo giấu nhiễu là một
đợt đo không dùng lại được.

1. **Cột tiền vắng mặt.** Nhà cung cấp sau alias báo `cost_usd = 0` ở mọi bước.
   Không phải "rẻ", mà là **không có dữ liệu**. Mọi so sánh tài nguyên trong báo
   cáo này dùng **số lượt (turn)** và **giây**, và đó là đại lượng thay thế.
2. **Đợt đo bị giết và chạy lại theo chunk.** Lần chạy đầu bị giết ở phút ~35;
   phần còn lại chạy theo từng nhóm task. Hệ quả đo được: `multi-3` có **6 lượt**
   ở nhánh AISEF thay vì 3. Quy tắc xử lý (tuyên bố sau khi đã thấy cả 6 lượt
   đều PASS, nên không chọn được kết quả có lợi): lấy 3 lượt sớm nhất.
3. **Máy không rảnh trong cửa sổ `state-1`.** Khoảng 22:00–22:04 tôi chạy toàn
   bộ suite 2 336 test trên cùng máy — vi phạm ràng buộc của chính kế hoạch.
   `duration_ms` của lượt đang chạy khi ấy có thể bị thổi lên; số turn và kết
   cục PASS/FAIL không phụ thuộc tải máy.
4. **Một phép thử 50 tiến trình** (`test_lease_stress`) chạy ~1,5 giây trên cùng
   máy lúc ~00:2x, trong cửa sổ `state-4`. Cùng loại nhiễu, nhỏ hơn nhiều.
5. **Số phiên trong bảng "phiên bị cắt" gộp cả lượt chạy lại của chunk** — mẫu
   số lớn hơn số lượt có trong bảng kết quả.
6. **Tôi sửa một dòng `import` trong `tests/bench/_runner.py` giữa lúc đợt đo
   chạy** (dời `simulated.py`). Tiến trình đo đã nạp module từ trước nên hành vi
   không đổi; ghi ra để đủ.
7. **Mã của hệ đang đo không đổi trong suốt đợt.** Plugin guard, adapter
   OpenCode và pha `implement` bị đóng băng có chủ ý từ 21:0x tới khi đóng đợt,
   kể cả khi đã tìm ra lỗi trong đó (xem §7).

## 7. Việc kéo theo, có bằng chứng đi kèm

<VIỆC-KÉO-THEO>
