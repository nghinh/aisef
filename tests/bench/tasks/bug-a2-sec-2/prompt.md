# Lỗi kho AISEF — #a2-sec-2

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Thông báo vi phạm phạm vi cắt bỏ danh sách phạm vi được phép, chỉ in tên tệp sai — agent không biết **mình được phép ghi đâu** thì không sửa được.

Kiểm: `python3 -m unittest -v tests.test_guardrails` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
