# Lỗi kho AISEF — #a2-sec-1

Triệu chứng đo trên agent thật (không phải suy từ mã):

- MCP server lưu vết trong thư mục riêng (`~/.mcp/state`); guard phạm vi ghi không biết thư mục ấy là tạo tác của công cụ, thấy tệp mới thì chặn cả khi MCP đã ghi — agent bị cấm đọc lại kết quả.

Kiểm: `python3 -m unittest -v tests.test_guardrails` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
