# Lỗi kho AI-SDLC — #14

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Cổng map mockup mở route có tham số bằng giá trị mẫu `1` (`/note/:id` → `/note/1`) và coi "dev phải có bản ghi `1`" là quy ước — nhưng quy ước ấy không có trong ngữ cảnh story, agent chỉ có thể đoán.

Kiểm: `python3 -m unittest -v tests.test_mockup_map_seed` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
