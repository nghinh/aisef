# Lỗi kho AI-SDLC — #20

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Preflight coi mọi token có dấu chấm trong tiêu chí (`tools.lint`, `Note.text`, `save.done`, `search.clear`) là tệp chưa tồn tại phải nằm trong write_scope → 6/21 story "không chạy được", cổng stories chặn cả kế hoạch thật.

Kiểm: `python3 -m unittest -v tests.test_preflight` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
