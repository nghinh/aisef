# Lỗi kho AISEF — #a2-sec-2

Triệu chứng đo trên agent thật (không phải suy từ mã):

- **Câu thông báo** guard trả về khi từ chối một lần ghi bị cắt: nó in tên tệp phạm lỗi nhưng **bỏ mất danh sách phạm vi được phép**, nên agent đọc thông báo không biết chỗ nào thì được ghi. Phạm vi *tính* đúng — chỉ câu chữ báo lại là thiếu.

Kiểm: `python3 -m unittest -v tests.test_guardrails` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
