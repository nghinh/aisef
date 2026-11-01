# AISEF — chỉ dẫn phiên làm việc

## Roadmap 2.2 (BẮT BUỘC)
- Trước khi làm BẤT KỲ việc cải tiến/roadmap nào: đọc `docs/ROADMAP-2.2-CHECKLIST.md` (nguồn sự thật — đầu bài, phương thức LÔ, trạng thái checkbox, quyết định owner còn OPEN). Chi tiết từng đề xuất: `docs/IMPROVEMENT-ROADMAP.md`.
- Làm theo chế độ LÔ: đo MỘT lần cuối mỗi đợt (full suite + mutation targeted + records + CI). CẤM fix–đo–fix–đo vi mô.
- Xong mục nào tick checkbox + ghi Nhật ký trong checklist, commit riêng (`chore(roadmap): tick <ID>`).
- Mục ghi "chờ QĐ #n" mà quyết định chưa chốt → không làm.

## Quy tắc vận hành cốt lõi
- Suite xanh chưa đủ: chạy `ruff` trước khi push; CI có job lint riêng.
- Full suite ~33 phút — chạy nohup tách rời, thăm bằng vòng until ≤600s; không commit khi suite/campaign đang chạy.
- Sau full suite: kiểm `git status closure-evidence/` — test có thể ghi đè evidence; checkout lại, không bao giờ commit thay đổi đó.
- Mutation worker: PATH không có opencode thật + XDG data/state/cache trỏ scratch; cây COPY phải có baseline xanh trước khi tin "killed".
- `python3` (python là alias zsh); zsh: `${=VAR}`, heredoc `<<'EOF'` + `git commit -F` khi message có backtick; không chạy python ở /tmp.
- `df -h` trước việc nặng, giữ ≥15 GiB; cấm `git stash` khi fan-out worktree; suite trong worktree yếu hơn — verdict tính trên cây chính.
- Docs sửa trên master; sửa README trên release branch làm vỡ release gate. `gh` dùng `-R nghinh/aisef` khi cwd lệch.
