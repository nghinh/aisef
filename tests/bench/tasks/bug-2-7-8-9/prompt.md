# Lỗi kho AI-SDLC — #2-7-8-9

Triệu chứng đo trên agent thật (không phải suy từ mã):

- 2: Guard `completion` chặn Stop vô hạn khi dự án chưa khai lệnh test. 7: Cấu hình client harness chép vào worktree bị tính là tệp story đổi khi dự án không gitignore `.claude/` → guard `diff-scope` chặn mọi lệnh, cổng "phạm vi ghi" trượt 3/3. 8: Lệnh test không chạy được (MODULE_NOT_FOUND) bị coi là test đỏ → guard `completion` chặn Stop ~10 lần/lượt, 3 story đốt $17. 9: `run_suite` ghi `qa:<kind>` nhưng cổng story tìm tên trần → e2e/perf/accessibility xanh thật mà cổng báo "chưa cấu hình".

Kiểm: `python3 -m unittest -v tests.test_gate tests.test_guardrails tests.test_tools` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
