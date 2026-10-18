# Quyết định của chủ dự án — 2026-10-18 (chiều): chiến dịch đối chứng E2 với mô hình thật

Ghi lại nguyên văn từ phiên chat ngày 2026-10-18 (sau báo cáo đánh giá chất lượng 2.1, trong đó khoảng trống lớn nhất được
nêu là "hiệu quả so với agent chạy trực tiếp (E2) chưa có số; chiến dịch trả tiền chưa duyệt").

> Tôi đồng ý agent chạy trực tiếp với model tên mycombo trên 9router (không cần lo về chi phí)

## Cách người điều phối đọc quyết định này

- **Được duyệt:** chạy chiến dịch đối chứng E2 (`docs/v2.1/EXPERIMENT-PLAN.md`; backlog B-09) với mô hình thật
  **`mycombo` qua 9router** — cả cánh đối chứng A `direct` (agent chạy trực tiếp, điều chủ dự án nêu tên) và các cánh
  AISEF B/C cùng model, vì so sánh chỉ có nghĩa khi cùng client, cùng model, cùng task (kế hoạch E2, mục "Các cánh").
- **Chi phí:** chủ dự án nói rõ không cần lo; vẫn ghi `usage` từng lượt và báo tổng ước tính trong báo cáo cuối (số đo,
  không phải trần).
- **Không thay đổi:** không push, tag, publish, deploy, release; không tự ghi owner acceptance; không chạy trong lúc
  campaign 9 còn worker (lý do kỹ thuật: `campaign3.sh` chụp store OpenCode thật của người vận hành trước/sau để chứng
  minh campaign không đụng nó — một lượt client thật chạy song song làm bằng chứng ấy mất nghĩa). E2 bắt đầu sau khi
  `campaign.done` xuất hiện và kết quả được nhập.
- **Evaluator ẩn và workload mới (W1/W2)** — kế hoạch E2 yêu cầu chủ dự án duyệt evaluator ẩn và chọn workload mới.
  Quyết định trên không nêu; người điều phối chuẩn bị đề xuất cụ thể (workload, evaluator, manifest) và ghi rõ phần nào
  là đề xuất kỹ thuật, phần nào cần chủ dự án duyệt trước lượt chạy đầu.

Ghi lúc 2026-10-18 12:41:00 +0700 (đồng hồ hệ thống).
