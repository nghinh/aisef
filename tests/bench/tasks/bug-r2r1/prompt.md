# Lỗi kho AI-SDLC — #r2r1

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Sổ hành vi ghi VERIFIED cho hành vi xanh ở ứng viên chưa landed (chưa merge) trong khi nhật ký story biết ứng viên nào đã vào nhánh chính — cùng lớp J: hai luật cho một sự thật.

Kiểm: `python3 -m unittest -v tests.test_ledger` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
