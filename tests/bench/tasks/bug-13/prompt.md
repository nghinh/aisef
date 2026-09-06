# Lỗi kho AI-SDLC — #13

Triệu chứng đo trên agent thật (không phải suy từ mã):

- `WorktreeManager.create` coi thư mục có sẵn trong `.aisdlc/worktrees/` là worktree có sẵn: một tiến trình dev server sống sót sau khi gỡ worktree ghi lại `.vite/` vào đúng chỗ, lần chạy sau agent làm việc trong một thư mục thường nằm trong repo chính, guard diff-scope so với repo chính và chặn mọi Bash (16 lần, developer chạy 40 phút không làm được gì).

Kiểm: `python3 -m unittest -v tests.test_worktree` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
