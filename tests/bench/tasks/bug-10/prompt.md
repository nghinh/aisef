# Lỗi kho AI-SDLC — #10

Triệu chứng đo trên agent thật (không phải suy từ mã):

- OpenCode gửi đường dẫn dưới khoá `filePath` và nội dung dưới `newString`, guard chỉ đọc `file_path`/`path` → mọi guard theo đường dẫn trên OpenCode thấy đường dẫn rỗng, `write-scope` cho qua như "không phải thao tác lên file". Luật 6 so đường dẫn tuyệt đối của worktree nên khớp nhầm bảng thư mục cho phép.

Kiểm: `python3 -m unittest -v tests.test_guardrails` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
