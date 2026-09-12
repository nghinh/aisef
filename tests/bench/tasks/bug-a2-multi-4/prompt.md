# Lỗi kho AISEF — #a2-multi-4

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Hai phiên của cùng một dự án giành nhau một tệp trạng thái; phiên đến sau ghi đè phiên đến trước và `improve` sửa trên bằng chứng phiên khác — bằng chứng ấy đã bị thay mất trước khi `improve` chạm vào.

Kiểm: `python3 -m unittest -v tests.test_improve tests.test_run` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
