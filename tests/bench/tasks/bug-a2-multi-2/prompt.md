# Lỗi kho AISEF — #a2-multi-2

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Đầu phiên chỉ ghi `START` không nói chờ bao lâu; agent kết thúc trước khi mạng chậm kịp phản hồi, phần việc xong nhưng phiên bị chấm 'failed to start' dù thực ra chỉ lâu hơn ngưỡng cấu hình.

Kiểm: `python3 -m unittest -v tests.test_runlog` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
