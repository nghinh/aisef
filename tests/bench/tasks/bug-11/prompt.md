# Lỗi kho AI-SDLC — #11

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Máy bật `permissions.defaultMode: "auto"` toàn cục: phiên con Claude Code mất Glob/Grep, được dặn ưu tiên Bash nên ghi tệp bằng heredoc né sạch guard `Write|Edit`; MCP và hook toàn cục của người dùng lọt vào phiên agent. Adapter chưa từng truyền chế độ quyền dù docstring nói có.

Kiểm: `python3 -m unittest -v tests.test_clients` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
