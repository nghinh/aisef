# Lỗi kho AISEF — #a2-sec-3

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Lúc tự rà soát mình (`self-review`) hệ thống khóa cổng `block` đúng nơi, nhưng **đánh dấu khối `BLOCK` của mình là không hợp lệ** — người rà soát bỏ qua bản thân mình, bản sửa do người viết đề xuất tự đi vào giai đoạn tiếp theo mà không có phản biện nào.

Kiểm: `python3 -m unittest -v tests.test_prompts` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
