# Lỗi kho AI-SDLC — #16

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Lời người rà soát không được lưu nguyên văn; mục `[chặn]`/`[bế tắc]` nhiều dòng chỉ giữ dòng đầu → lý do bế tắc trong sprint-status cụt ở "— không.", bằng chứng chặn story mà người đọc không kiểm lại được.

Kiểm: `python3 -m unittest -v tests.test_findings` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
