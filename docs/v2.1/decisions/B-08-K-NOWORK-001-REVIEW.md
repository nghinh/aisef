# B-08 — K-NOWORK-001: review cho story không có việc của developer

**Trạng thái: ĐỀ XUẤT, CHƯA DUYỆT.** Luật hiện hành (owner ruling 2026-10-02, "K-NOWORK-001 MEASURED ARCHITECTURE
CORRECTION") không đổi trong 2.1.

## Hiện trạng (đọc mã + đo)

`story_runner._attempt`: khi mọi obligation của story SATISFIED ở parent (`no_work`), developer không được gọi, candidate =
parent, engineering-quality bỏ qua — **nhưng review vẫn chạy** (một provider request, owner REVIEW) trên checkout của
parent. Đo:

- continuation: story `CARRIED` (VERIFY) tốn đúng một REVIEW request, không developer request
  (`test_v21_continue_usage.Continue`).
- với finder OCR (2.1): khoảng rỗng `parent..parent` — binary thật trả `skipped`, exit 0, 0 token, không gọi model
  (`RealBinary.test_an_empty_range_is_skipped_without_a_model_call`); adapter coi đó là review hoàn tất của "không gì cả"
  (`51f2eb5`; trước đó nó sẽ chặn sai mọi story không đổi dưới `fix-loop`).
- với finder mô hình: reviewer đọc toàn bộ checkout không đổi; tốn một phiên đầy đủ (smoke #2: một phiên reviewer ≈ một
  phần lớn của chi phí story).

## Hai khái niệm cần tách

1. **Story không đổi mã** — candidate = parent: không có thay đổi nào của story để review.
2. **Story có thể tái dùng một review hợp lệ** — đã có một review trước đó của *đúng nội dung* này, theo *đúng chính sách*,
   bởi *đúng reviewer*, với *đúng mệnh đề yêu cầu*. Một review chỉ còn hợp lệ khi tất cả những gì nó phụ thuộc không đổi.

## Review phụ thuộc vào gì — và khi cái đó đổi

| Thay đổi | Review cũ còn dùng được? | Lý do |
|---|---|---|
| base (parent) đổi, nội dung story không đổi | **không** chắc chắn | review OCR/mô hình xét *thay đổi* so với base; base khác ⇒ diff khác, tương tác khác |
| dependency (story trước) đổi | không | mã quanh thay đổi đã khác |
| policy (`fix-loop`/`advisory`, `min_severity`) đổi | finding thì còn, **quyết định** thì phải tính lại | chặn hay không là hàm của policy |
| reviewer đổi (finder, model, binary OCR, prompt/background) | không | danh tính người tìm là một phần của bằng chứng |
| mệnh đề / bundle đổi | không | neo kỳ vọng (ADR-7) dựa trên contract đã duyệt |
| không gì đổi (cùng tree hash, base, policy, reviewer digest, bundle digest) | có | khi đó review thứ hai là lặp lại thuần |

## Phương án

| | Nội dung | Ưu | Nhược |
|---|---|---|---|
| A. Giữ nguyên K-NOWORK-001 | review mọi story kể cả không đổi | đơn giản; không phải định nghĩa "review hợp lệ" | trả tiền cho review không có gì để xét (finder mô hình); với OCR chi phí ≈ 0 |
| **B. Bỏ review khi candidate = parent** (khuyến nghị) | story `no_work` không gửi review request; gate ghi "no change to review" | không tốn tiền vô ích; đúng với nghĩa "review một thay đổi" | là thay đổi của kernel (`story_runner`) ⇒ cần ruling mới, tái lập bản ghi K-NOWORK-001 và conformance |
| C. Tái dùng review theo khoá | khoá = (tree hash, base, policy, reviewer digest, bundle digest); trùng ⇒ tái dùng, ghi nguồn | tiết kiệm cả cho story có đổi mà chạy lại | phức tạp; khoá sai = dùng review hết hạn; cần định dạng bằng chứng mới |

**Khuyến nghị: B**, với điều kiện ghi rõ trong gate row rằng không có review vì không có thay đổi, và giữ A cho đến khi có
ruling. C không đề xuất cho 2.1: chưa có bằng chứng chi phí đủ lớn để bù rủi ro tái dùng sai.

## Cần chủ dự án

Ruling A/B/C. B động tới kernel ⇒ thuộc vòng tái thẩm định (B-03).
