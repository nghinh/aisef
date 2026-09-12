# Lỗi kho AISEF — #a2-state-3

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Sau khi phiên bị ngắt (timeout, khởi động lại), lượt kế tiếp gửi lại **ứng viên đã bị bác** của lượt trước; rà-soát-viên lại phải dò lại từ đầu dù lý do bác vẫn còn trên bằng chứng.

Kiểm: `python3 -m unittest -v tests.test_implement` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
