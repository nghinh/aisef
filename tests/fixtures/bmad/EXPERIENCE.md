---
name: Ghi chú cục bộ
status: final
sources:
  - _bmad-output/prd.md
updated: 2026-09-04
---

# Ghi chú cục bộ — Experience Spine

## Foundation

Ứng dụng web một bề mặt, chạy được hoàn toàn ngoại tuyến. Không tài khoản, không máy chủ ở bản đầu.

## Information Architecture

| Surface | Reached from | Purpose |
|---|---|---|
| Danh sách | Mở ứng dụng | Toàn bộ ghi chú, mới sửa nằm trên |
| Soạn thảo | Chạm một ghi chú / nút thêm | Viết và sửa nội dung, lưu tự động |
| Tìm kiếm | Ô tìm ở đầu danh sách | Truy vấn toàn văn, hiện đoạn khớp |
| Thẻ | Nút thẻ trên thanh công cụ | Xem, đổi tên, xoá thẻ |
| Thùng rác | Menu · từ Danh sách | Khôi phục hoặc xoá hẳn ghi chú đã xoá |
| Cài đặt | Menu | Xuất dữ liệu, xem dung lượng còn lại |

Thanh công cụ luôn hiện. Trên màn hình hẹp, Danh sách và Soạn thảo là hai bước; trên màn hình rộng, hai cột.

## Component Patterns

| Component | Use | Behavioral rules |
|---|---|---|
| Dòng ghi chú | Danh sách, Tìm kiếm, Thùng rác | Chạm mở Soạn thảo. Vuốt trái hiện nút xoá. Hiện dòng đầu nội dung và thời điểm sửa. |
| Ô soạn thảo | Soạn thảo | Tự lưu sau 1 giây ngừng gõ. Không có nút lưu. |
| Ô tìm | Tìm kiếm, Danh sách | Gõ là tìm, không cần Enter. Xoá ô thì về danh sách đầy đủ. |
| Chip thẻ | Soạn thảo, Thẻ, Danh sách | Chạm để lọc. Giữ để đổi tên. |
| Chỉ báo ngoại tuyến | Global | Hiện khi mất mạng, không che nội dung. |
| Trạng thái rỗng | Anywhere | Một câu, một nút hành động chính. |

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| Chưa có ghi chú nào | Danh sách | "Chưa có gì ở đây." kèm nút tạo ghi chú đầu tiên. |
| Không tìm thấy | Tìm kiếm | "Không có ghi chú nào khớp." kèm gợi ý bỏ bớt từ khoá. |
| Ngoại tuyến | Global | Chỉ báo ở thanh công cụ; mọi thao tác vẫn chạy. |
| Sắp hết dung lượng | Cài đặt | Cảnh báo kèm nút xuất dữ liệu. |
| Thùng rác rỗng | Thùng rác | "Thùng rác trống." |

## Interaction Primitives

- Một thao tác từ Danh sách tới con trỏ trong ô soạn thảo trống.
- Ctrl/⌘+K mở Tìm kiếm.
- Esc rời ô soạn thảo, quay lại Danh sách.
