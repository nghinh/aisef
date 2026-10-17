# Câu trả lời của chủ dự án, 2026-10-18 (sau bảng phạm vi `SCOPE-BEFORE-PIN.md`) — nguyên văn

Trả lời bốn câu hỏi đóng khung trong phiên làm việc, nhận khoảng 2026-10-18 03:20 (Asia/Saigon). Câu hỏi và lựa chọn do người
điều phối soạn; **các lựa chọn dưới đây là của chủ dự án**. Không có ghi nhận nghiệm thu nào được tạo từ nó.

| Câu hỏi (rút gọn) | Câu trả lời của chủ dự án |
|---|---|
| Có ghim snapshot với hành vi mặc định hiện tại không? | **"Ghim với mặc định (Recommended)"** — ghim khi suite chạy thử lần 2 xanh; giữ hành vi hiện tại cho mọi quyết định còn mở ở §5 của bảng phạm vi; điểm nào anh chọn khác sau đó thì đo lại phần bị ảnh hưởng |
| D-1: `bundle migrate` suy ra SÁU contract LedgerLock cần duyệt lại (S-10-a/b/c, S-12-a/b/c), không phải bốn | **"Giữ sáu (Recommended)"** — phía an toàn: chủ dự án duyệt thêm hai contract bằng hai lệnh `bundle approve`; không đổi mã |
| D-2: ba probe `cli_invocation`, `process_effect`, `python_callable_v2` đã đổi hành vi từ 2.0.0 mà `CAPABILITY_VERSION` vẫn 1 (50/53 approval giữ lại chỉ nhờ luật "version không đổi") | **"Chấp nhận, ghi giới hạn (Recommended)"** — giữ `CAPABILITY_VERSION` 1; giới hạn nằm trong `report.limits` và USAGE-2.1 |
| Nhóm lineage và giới hạn công cụ: R2-D1/D2/D3, R3, R4, R5, D1–D5 | **"Giữ mặc định (Recommended)"** — ghim với hành vi hiện tại cho cả nhóm; điểm nào đổi mã sau này sẽ đo lại tệp bị ảnh hưởng |

Hệ quả cho bản ghi: các mục này **không còn là quyết định mở**; chúng là quyết định đã chốt giữ hành vi hiện tại của bản ứng viên.
Không có gì ở đây thay đổi mã. Chưa được hỏi và vẫn mở: D-OCR-1 (tải artifact phát hành và attestation của upstream để so; mặc định
không tải), V21-65 (lối ra "finder model" trong lời từ chối của cổng OCR sớm; mặc định giữ), PM-9 nhị phân, PM-13 bắt tay khởi động,
B-02, B-04, B-08, B-09 (bậc 2c/3), B-10, F, RM-3.
