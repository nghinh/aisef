# Lỗi kho AISEF — #a2-multi-1

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Bản ghi log Playwright mặc định thử nhiều trình duyệt (`projects`); mỗi dòng mang theo `[chromium] › ` ngoài tên test. Bộ phân tích log đọc 0/99 tên trên bản ghi nhiều project, cổng gate tin log rỗng và đập phiên — sửa 7 tệp.

Kiểm: `python3 -m unittest -v tests.test_testlog` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
