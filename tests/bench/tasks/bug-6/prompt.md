# Lỗi kho AI-SDLC — #6

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Hook biên dịch ghim đường dẫn tuyệt đối của dự án: chép hay di chuyển dự án thì guard ghi bằng chứng vào dự án *khác*, cổng "guard có chạy" trượt.

Kiểm: `python3 -m unittest -v tests.test_cli tests.test_guardrails tests.test_implement tests.test_meta` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
