# Lỗi kho AI-SDLC — #4-5

Triệu chứng đo trên agent thật (không phải suy từ mã):

- 4: Phiên con thừa hưởng `CLAUDE_*` của phiên cha → agent tự chuyển sang Bash thay vì Read/Write. 5: Router chọn 8/18 story — sai cả 8: năng lực suy từ chữ trong SKILL.md, "màn hình + một chữ" đếm là hai tín hiệu.

Kiểm: `python3 -m unittest -v tests.test_clients tests.test_registry tests.test_router` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
