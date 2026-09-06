# Lỗi kho AI-SDLC — #23-24

Triệu chứng đo trên agent thật (không phải suy từ mã):

- 23: Cổng "bảo toàn" hỏi test mang mã của story *sở hữu* FR, còn sổ hành vi xác minh FR *qua* story khác → UNRUNNABLE oan dù sổ nói VERIFIED. 24: Cổng "không làm đỏ test có sẵn" coi đổi tên test (developer chỉ thêm tiền tố mã tiêu chí) là mất 4 test.

Kiểm: `python3 -m unittest -v tests.test_gate tests.test_preservation` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
