# Lỗi kho AI-SDLC — #21

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Harness đòi kiểm định e2e/accessibility (hợp đồng story) nhưng phạm vi ghi có hiệu lực chỉ gồm `src/**` mà kế hoạch khai → guard chặn ghi `tests/`, người rà soát đánh dấu bế tắc kế hoạch; hai story liên tiếp trượt vì harness đòi test rồi cấm viết test.

Kiểm: `python3 -m unittest -v tests.test_write_scope_verify` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
