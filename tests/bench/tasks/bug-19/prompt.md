# Lỗi kho AI-SDLC — #19

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Parser PRD chỉ nhận tiêu đề khối tiêu chí `**Consequences (testable):**`; lượt plan thật thứ hai agent viết `**Hệ quả kiểm chứng được:**` → cổng PRD loại cả 14 FR "không có tiêu chí" dù có.

Kiểm: `python3 -m unittest -v tests.test_prd_headings` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
