# Lỗi kho AISEF — #a2-state-4

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Preflight khớp chữ 'third-party' rồi đòi **bật** `sandbox.tools_network` cho story mà AC cấm mọi truy cập mạng — heuristic đọc chữ mà bỏ câu, biến yêu cầu bảo mật thành yêu cầu nới lỏng sandbox, chặn story là NOT_EXECUTABLE. Mặc định vốn đã là tắt mạng — không phải cấu hình gì cả.

Kiểm: `python3 -m unittest -v tests.test_approvals tests.test_preflight` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
