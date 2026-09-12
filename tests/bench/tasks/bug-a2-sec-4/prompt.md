# Lỗi kho AISEF — #a2-sec-4

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Người rà soát viết nhận xét trên cả kế hoạch nhưng `prompts` chỉ đưa về story đơn; người rà soát thấy ngoài phạm vi rồi dán nhãn nhầm cho một story khác trong lúc thiếu thông tin — scope của prompt không khớp scope họ nhìn.

Kiểm: `python3 -m unittest -v tests.test_prompts` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
