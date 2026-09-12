# Lỗi kho AISEF — #a2-state-2

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Lượt kế tiếp khi phiên agent im lặng và không ghi tệp nào thì cổng 'no-op' lại đập ngược — cây chưa ai chạm vẫn được đem đi rà soát, REVIEWER rảnh thì rà một bản trống, REVIEWER bận thì tự rà phiên trước.

Kiểm: `python3 -m unittest -v tests.test_implement` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
