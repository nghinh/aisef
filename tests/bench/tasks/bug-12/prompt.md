# Lỗi kho AI-SDLC — #12

Triệu chứng đo trên agent thật (không phải suy từ mã):

- Mockup do agent dựng bỏ quên `data-state`/`data-annotation` (quy ước của chính skill mockup) → hợp đồng thị giác ôm cả trang gồm nhiều trạng thái (32 component, 4 lần "Thêm thẻ", cả tiêu đề gallery), bước map mockup không thể khớp; cổng máy mockup không kiểm quy ước ấy dù checklist skill có ghi.

Kiểm: `python3 -m unittest -v tests.test_design_contract_states` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
