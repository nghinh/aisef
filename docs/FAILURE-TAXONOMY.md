# Phân loại lỗi thật — để không tái diễn

Mười sáu lỗi tìm được trong ngày 2026-09-05, **tất cả bằng đo trên agent
thật**, không lỗi nào bằng đọc code. Mỗi lỗi có một phép hồi quy đỏ khi
hoàn nguyên; bảng này nhóm chúng theo *lớp nguyên nhân* để lần sau, khi một
triệu chứng mới xuất hiện, người sửa hỏi đúng câu hỏi trước.

Chi tiết từng lỗi (lộ ra ở đâu, sửa gì): `docs/STATUS-2026-09-05.md` §2.4.

## Bảy lớp nguyên nhân

| Lớp | Câu hỏi phải hỏi | Lỗi | Phép hồi quy |
|---|---|---|---|
| **A. Ranh giới tin cậy — harness nhận vơ thứ không phải của mình** | "Thứ đang trả lời / đang tồn tại này có đúng là thứ harness vừa dựng không?" | 13 thư mục còn sót ≠ worktree · 15 cổng có người trả lời ≠ app của story · 6 hook ghim đường dẫn dự án cũ | `test_worktree.test_stray_dir_is_not_a_worktree` · `test_mockup_map.TestAppServerTrust` · `test_guardrails` (ENV_PROJECT) |
| **B. Rò môi trường vào phiên agent** | "Phiên con đang thừa hưởng gì từ máy / phiên cha mà spec không nói?" | 4 `CLAUDE_*` của phiên cha · 11 `defaultMode: auto`, MCP, hook toàn cục của người dùng | `test_clients.test_isolated_from_user_config`; hợp quy C3/C4 (`docs/CONFORMANCE.md`) |
| **C. Vòng đời tiến trình** | "Ai giết con của tiến trình này khi cha chết?" | 15 `npm` chết, `node vite` sống giữ cổng (gốc của 13) | `test_mockup_map.test_stop_kills_whole_process_group` |
| **D. Quy ước máy đòi mà không nói ra cho agent** | "Cổng đòi điều này ở đâu trong ngữ cảnh story? Nếu không có, agent chỉ có thể đoán." | 12 mockup không đánh dấu `data-state` (cổng máy không kiểm quy ước của chính skill) · 14 bản ghi hạt giống `1` cho route có tham số | `test_design_contract_states` · `test_mockup_map_seed` |
| **E. Phân loại kết cục sai — "không chạy được" bị coi là "trượt", "chưa cấu hình" bị coi là "đạt"** | "Kết cục này thuộc sáu loại nào? Ai đặt tên cho nó?" | 2 completion chặn vô hạn khi chưa khai test · 8 MODULE_NOT_FOUND coi là test đỏ · 9 cổng tìm tên trần bỏ qua `qa:<kind>` | `test_guardrails` (skipped/unrunnable → ALLOW) · `test_tools` (unrunnable) · `test_gate` (`qa:<kind>`) |
| **G. Bằng chứng không đọc lại được** | "Kết luận này người đọc kiểm lại bằng gì? Nguyên văn nằm ở đâu?" | 16 lời người rà soát không lưu, mục nhiều dòng cụt ở dòng đầu | `test_findings` (persist_verdict, nối dòng) |
| **F. Hình dạng dữ liệu giữa hai bên khác nhau** | "Khoá/định dạng bên gửi có đúng là khoá bên nhận đọc không? Đã đo trên bên gửi thật chưa?" | 10 OpenCode gửi `filePath`, guard đọc `file_path` · 1 worktree không có cấu hình client · 7 cấu hình client bị tính là file story · 3 reviewer sửa cây qua Bash · 5 router suy năng lực từ chữ | `test_guardrails` (`filePath`/`newString`, HARNESS_OWNED) · `test_worktree` (`_carry_client_config`) · `test_implement` (snapshot/hoàn nguyên) · `test_router` (khai năng lực) |

## Ba bài học vận hành đi kèm

1. **Đo trước khi kết luận, và đo cả thứ vô can.** Lỗi 14 được "tìm ra" khi
   truy trang trống của nhánh off, nhưng trang trống thật ra do lỗi 15;
   nhánh on qua 3/3 với cùng route. Quy ước hạt giống vẫn phải nói ra, song
   nếu dừng ở nguyên nhân hợp lý đầu tiên thì lỗi 15 còn nguyên.
2. **Chạy song song nhiều bản chép dự án**: `rsync` mang theo `.git/worktrees`
   và `.aisdlc/worktrees` còn sót; dev server của lượt trước giữ cổng chung.
   Trước mỗi lượt: `git worktree prune`, xoá thư mục sót, `lsof -i :<cổng>`.
3. **Không giết tiến trình cha có pipe stdout** — con `claude` chết theo vì
   EPIPE giữa chừng và bằng chứng cụt. Giết cả cây, từ lá lên.

## Khi thêm lỗi mới

Một dòng vào bảng trên (lớp, câu hỏi, số lỗi, phép hồi quy) **cùng commit**
với phép hồi quy. Lỗi không xếp được vào lớp nào là tín hiệu cần một lớp
mới — và một câu hỏi mới.
