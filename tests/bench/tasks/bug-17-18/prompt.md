# Lỗi kho AI-SDLC — #17-18

Triệu chứng đo trên agent thật (không phải suy từ mã):

- 17: Cổng trước triển khai ghi "mọi story xong ✅" khi hai story trong kế hoạch chưa từng chạy — chỉ đếm bản ghi trạng thái, không đối chiếu `stories.index.json`. 18: Báo cáo nghiệm thu ghi Map mockup ✗ cho story đã qua cổng vì ô này đòi *mọi* lần đối chiếu trong lịch sử đều đạt.

Kiểm: `python3 -m unittest -v tests.test_deploy tests.test_report_mockup_cell` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
