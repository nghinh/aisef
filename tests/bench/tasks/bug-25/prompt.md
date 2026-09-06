# Lỗi kho AI-SDLC — #25

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Vòng cải tiến ghi story sửa vào `stories.index.json` → cổng người `stories`/`readiness` đã duyệt thành stale, lần gọi `aisdlc improve` kế bị chính vòng trước chặn (exit 2).

Kiểm: `python3 -m unittest -v tests.test_approvals` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
