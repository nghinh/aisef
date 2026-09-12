# Lỗi kho AISEF — #a2-state-1

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Lượt viết cùng nội dung như lượt trước được tính là 'đã sửa', cổng chấm PASS mà không phân biệt; phiên tiếp theo của cùng story sẽ đốt vì cổng đã đánh dấu xong.

Kiểm: `python3 -m unittest -v tests.test_implement` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
