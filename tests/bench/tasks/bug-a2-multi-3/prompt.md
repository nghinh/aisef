# Lỗi kho AISEF — #a2-multi-3

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Phiên đầu tiên im lặng — không viết tệp, không gọi công cụ — vẫn được ghi là 'ứng viên' và bị rà soát: rảnh cổng `gate` rà soát phiên rỗng, cổng bận thì chính rà-soát-viên tự rà soát bản thân mình, sinh FINDING.

Kiểm: `python3 -m unittest -v tests.test_implement` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
