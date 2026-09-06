# Lỗi kho AI-SDLC — #15

Triệu chứng đo trên agent thật (không phải suy từ mã):

- `AppServer.start` nhận vơ bất kỳ thứ gì trả lời ở `app.base_url` là app của story ("người dùng đang chạy sẵn — dùng luôn"); `stop` chỉ giết `npm` chứ không giết cả nhóm tiến trình, `node vite` sống sót giữ cổng sau khi worktree đã gỡ — cổng map mockup mở vào app ma, thấy trang trống, chấm sai app.

Kiểm: `python3 -m unittest -v tests.test_mockup_map` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
