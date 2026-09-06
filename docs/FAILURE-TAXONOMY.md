# Phân loại lỗi thật của AISEF — để không tái diễn

Hai mươi lăm lỗi tìm được trong hai ngày 2026-09-05 → 06 — 21 trong ngày
05/09, và 22–25 đêm 05→06/09 khi đo hai đợt ADR-004 trên agent thật (e9
STORY-01-07 và `aisef improve`) — **tất cả bằng đo trên agent thật**, không
lỗi nào bằng đọc code. Mỗi lỗi có một phép hồi quy đỏ khi hoàn nguyên, trừ
lỗi 22 (lý do ở lớp I); bảng này nhóm chúng theo *lớp nguyên nhân* để lần
sau, khi một triệu chứng mới xuất hiện, người sửa hỏi đúng câu hỏi trước.

Chi tiết từng lỗi (lộ ra ở đâu, sửa gì): `docs/STATUS-2026-09-05.md` §2.4;
lỗi 22–25 còn có số đo ở `docs/ADR-004-evidence-driven-epic-improvement.md` §6.

## Mười một lớp nguyên nhân

| Lớp | Câu hỏi phải hỏi | Lỗi | Phép hồi quy |
|---|---|---|---|
| **A. Ranh giới tin cậy — harness nhận vơ thứ không phải của mình** | "Thứ đang trả lời / đang tồn tại này có đúng là thứ harness vừa dựng không?" | 13 thư mục còn sót ≠ worktree · 15 cổng có người trả lời ≠ app của story · 6 hook ghim đường dẫn dự án cũ | `test_worktree.test_stray_dir_is_not_a_worktree` · `test_mockup_map.TestAppServerTrust` · `test_guardrails` (ENV_PROJECT) |
| **B. Rò môi trường vào phiên agent** | "Phiên con đang thừa hưởng gì từ máy / phiên cha mà spec không nói?" | 4 `CLAUDE_*` của phiên cha · 11 `defaultMode: auto`, MCP, hook toàn cục của người dùng | `test_clients.test_isolated_from_user_config`; hợp quy C3/C4 (`docs/CONFORMANCE.md`) |
| **C. Vòng đời tiến trình** | "Ai giết con của tiến trình này khi cha chết?" | 15 `npm` chết, `node vite` sống giữ cổng (gốc của 13) | `test_mockup_map.test_stop_kills_whole_process_group` |
| **D. Quy ước máy đòi mà không nói ra cho agent** | "Cổng đòi điều này ở đâu trong ngữ cảnh story? Nếu không có, agent chỉ có thể đoán." | 12 mockup không đánh dấu `data-state` (cổng máy không kiểm quy ước của chính skill) · 14 bản ghi hạt giống `1` cho route có tham số · 21 đòi test e2e/a11y nhưng cấm ghi `tests/` | `test_design_contract_states` · `test_mockup_map_seed` · `test_write_scope_verify` |
| **E. Phân loại kết cục sai — "không chạy được" bị coi là "trượt", "chưa cấu hình" bị coi là "đạt"** | "Kết cục này thuộc sáu loại nào? Ai đặt tên cho nó?" | 2 completion chặn vô hạn khi chưa khai test · 8 MODULE_NOT_FOUND coi là test đỏ · 9 cổng tìm tên trần bỏ qua `qa:<kind>` · 17 "mọi story xong" khi story trong kế hoạch chưa từng chạy · 18 báo cáo lấy lịch sử (mọi lần) thay vì trạng thái mới nhất · 24 cổng R9 đọc **đổi tên** test (gắn mã `AC_…:`) là **mất** test | `test_guardrails` (skipped/unrunnable → ALLOW) · `test_tools` (unrunnable) · `test_gate` (`qa:<kind>`) · `test_deploy.TestPlannedButNeverRun` · `test_report_mockup_cell` · `test_gate.TestKhongLamDoTestCoSan.test_doi_ten_test_giu_tieu_de_la_khong_phai_mat` |
| **G. Bằng chứng không đọc lại được** | "Kết luận này người đọc kiểm lại bằng gì? Nguyên văn nằm ở đâu?" | 16 lời người rà soát không lưu, mục nhiều dòng cụt ở dòng đầu | `test_findings` (persist_verdict, nối dòng) |
| **H. Cổng chấm trạng thái, không chấm thay đổi — không có mốc "trước" do máy ghi** | "Kết quả này so với **trước khi story chạm vào** thì sao? Mốc ấy ai ghi, ghi ở đâu?" | (hồi cứu B0, ADR-004 §6 R2, trên evidence e9 — không phải lỗi đánh số) STORY-01-05 và 01-06 làm đỏ tiêu chí của 01-04 giữa lượt rồi tự sửa, không để lại dấu vết; và khi không tự sửa thì cổng chỉ nói "test đỏ", không phân biệt test mới đang đỏ (TDD) với test có sẵn vừa hỏng | `test_gate.TestKhongLamDoTestCoSan` · `test_implement.TestBaselineTruocKhiSua` (ADR-004 R9) |
| **F. Hình dạng dữ liệu giữa hai bên khác nhau** | "Khoá/định dạng bên gửi có đúng là khoá bên nhận đọc không? Đã đo trên bên gửi thật chưa?" | 10 OpenCode gửi `filePath`, guard đọc `file_path` · 1 worktree không có cấu hình client · 7 cấu hình client bị tính là file story · 3 reviewer sửa cây qua Bash · 5 router suy năng lực từ chữ · 19 parser PRD chỉ nhận tiêu đề khối tiêu chí tiếng Anh, agent viết tiếng Việt · 20 preflight coi `a.b` bất kỳ là tệp | `test_guardrails` (`filePath`/`newString`, HARNESS_OWNED) · `test_worktree` (`_carry_client_config`) · `test_implement` (snapshot/hoàn nguyên) · `test_router` (khai năng lực) · `test_prd_headings` · `test_preflight.TestDottedNamesAreNotFiles` |
| **I. Bằng chứng đúng, môi trường đo sai** | "Chạy lại *đúng phép kiểm ấy* trên *đúng ứng viên ấy* lúc máy rảnh thì còn đỏ không? Phép nào trong bộ này nhạy thời gian?" | 22 e2e `autosave.spec.ts:210` (≥ 800 ms) đỏ khi máy gánh 3 bộ test + Docker (load 40–150); cùng ứng viên `a60612e` ở load 17: 10/10 xanh. Story trượt vì hết `run.max_retries`, $28,76 cho một lượt developer dựng lại thứ đã có | **không có bằng code** — cổng chấm *đúng* theo bằng chứng lúc ấy, không có gì để hoàn nguyên. Chặn bằng bài học 5 dưới đây, và bằng khoảng trống đã ghi: ADR-004 R13 `aisef run --story S --verify-only` (STATUS P1-13, chưa làm) để kiểm-lại ứng viên đã đóng băng mà không mở phiên developer |
| **J. Hai luật cho một sự thật — sổ và cổng suy cùng một hành vi bằng hai cách** | "Sự thật này còn chỗ nào khác suy nó không? Hai chỗ có dùng chung một hàm, một trường không? Nếu không, chỗ nào là luật?" | 23 cổng "bảo toàn" hỏi test mang mã của story **sở hữu** FR, sổ xác minh FR **qua** story khác (`source.story`) → sổ nói VERIFIED, cổng nói UNRUNNABLE oan; cùng lớp, không đánh số: R2×R1 (sổ ghi VERIFIED ở ứng viên chưa landed trong khi nhật ký biết), R5×R2 (sổ không ghi tệp, cổng cỡ tra tệp) | `test_preservation.TestCongBaoToan.test_fr_hoi_story_da_xac_minh_no_khong_hoi_story_so_huu` · `test_ledger.TestUngVienChuaLanded` |
| **K. Cơ chế mới ghi vào artifact mà cổng người cũ đang băm** | "Bước này ghi vào tệp nào? Tệp ấy có cổng người nào băm không? Ai duyệt lại, và có phải mỗi lần không?" | 25 `aisef improve` ghi story sửa vào `stories.index.json` → `stories`/`readiness` đã duyệt thành stale → lần gọi kế bị chính vòng trước chặn (exit 2), 28 | `test_approvals.TestStorySuaKhongLamStaleCongStories` (thêm story sửa không stale; sửa story thật vẫn stale) |

## Lỗi 22–31 — triệu chứng, gốc, bài học

| # | Lớp | Triệu chứng | Gốc | Bài học | Chặn tái diễn |
|---|---|---|---|---|---|
| 22 | I | 01-07 lượt 3: rà soát ✅, bảo mật ✅, chỉ một e2e của story *khác* đỏ; trượt vì hết lượt thử | phép kiểm đo thời gian thật, máy đang gánh ba suite + Docker; bằng chứng đúng cho thời điểm ấy, sai cho mã | "trượt" và "mã sai" là hai câu; khi mục đỏ là phép kiểm nhạy tải của story khác, đo lại đúng ứng viên trước khi trả tiền cho lượt developer mới | không chạy suite đầy đủ song song với lượt agent có e2e timing (bài học 5); R13 chưa làm |
| 23 | J | 01-07 lượt 1 (lần chạy 3): mọi mục ✅, riêng "bảo toàn" ⚠ `FR-11` "không có test mang mã" dù sổ nói VERIFIED | sổ dùng `source.story` (story đã xác minh), cổng dùng story sở hữu trên giấy — hai luật cho một hành vi; hệ quả phụ: developer gắn mã của story khác vào test có sẵn để cổng hết kêu → sinh lỗi 24 | mục bảo toàn mang `via` = story đã xác minh; cổng hỏi đúng story ấy. Một hành vi, một luật, một chỗ suy | `test_fr_hoi_story_da_xac_minh_no_khong_hoi_story_so_huu` |
| 24 | E | 01-07 lượt 2: "không làm đỏ test có sẵn" ✗ "mất 4 test" — developer chỉ đổi tên (thêm `AC_STORY_01_01_6:`) | cổng so *tên đầy đủ*; đổi tên và xoá trông y hệt ở đó | so tiêu đề lá: còn ở ứng viên là đổi tên, không tính mất; xoá thật vẫn bắt. Khi hai việc khác nhau trông giống nhau ở dữ liệu cổng đọc, tìm trường phân biệt được chúng trước khi chặn | `test_doi_ten_test_giu_tieu_de_la_khong_phai_mat`; prompt `story-implement@6` dặn không đổi tiêu đề test có sẵn (B1: mỗi story sửa mất một lượt vì đây) |
| 25 | K | gọi `improve` lần hai: exit 2 "cổng `stories`/`readiness` stale" ngay sau khi vòng 1 xong | vòng cải tiến ghi `STORY-RP-*`/`EPIC-RP-*` vào chính tệp mà hai cổng người băm; băm byte nên mọi lần ghi lại đều stale | băm chỉ mục **chuẩn hoá và bỏ story sửa** (cổng `improve` quản chúng, duyệt mỗi vòng); đổi cách băm làm phê duyệt cũ stale **một lần** — nói ra trong docstring và CHANGELOG, không để người dùng đoán | `TestStorySuaKhongLamStaleCongStories` |
| 28 | K | `aisef gates` e9 06:50: `stories`/`readiness` stale **lại** sau vòng improve 4/5, dù lỗi 25 đã lọc story/epic sửa | `register_story(wave=[sid])` thay `waves[EPIC-RP-01]` mỗi vòng; băm lọc chỉ nhìn `stories`/`epics` — cùng tệp, một khoá quên | khi lọc một artifact theo tiền tố, hỏi "cơ chế ấy còn ghi vào **khoá nào khác** của cùng tệp?" — liệt kê mọi chỗ `register_story` ghi | `approvals._artifact_hash` lọc `waves` cùng tiền tố; `test_dot_chay_cua_epic_sua_doi_moi_vong_khong_stale` |
| 29 | E/F | Bản đồ mã rỗng cho story có phạm vi ghi `src/**` — nhưng chỉ trên Python ≤ 3.12; máy đo (3.14) luôn xanh | `Path.glob("src/**")` khớp thư mục ở ≤ 3.12, khớp cả tệp từ 3.13; gói khai hỗ trợ ≥ 3.11 nên nửa số bản chạy sai lặng lẽ | phép kiểm chạy trên **mọi** bản Python đã khai hỗ trợ, không chỉ bản của máy đo; API stdlib đổi hành vi giữa các bản là chuyện thật | chuẩn hoá `**` → `**/*`; `test_hai_dau_sao_cho_cung_ket_qua_tren_moi_ban_python` |
| 30 | I | `test_without_experience_file` đỏ trên CI, xanh trên máy đo | phép kiểm gọi lệnh cần client; máy CI không cài `claude` nên dừng sớm với mã 2 — nó đo môi trường chứ không đo lệnh | phép kiểm lệnh phải tự dựng đủ điều kiện của lệnh, không mượn máy | `CliTestCase.stub_client()`; chạy lại với `PATH` không có `claude` vẫn xanh |
| 31 | A | Bản cài từ wheel: `aisef compile` ghi hook trỏ `<site-packages>/bin/aisef` — không tồn tại — nên **không guard nào chạy**, và không có thông báo nào | `aisef_command()` lùi về đường dẫn `bin/` chỉ có trong kho nguồn; không ai kiểm tồn tại trước khi ghi vào hook | đường dẫn ghi vào tạo tác cho tiến trình khác gọi phải được **kiểm tồn tại** ngay lúc ghi; "đã sinh ra tệp" chưa phải "lệnh chạy được" | kiểm `is_file()` rồi mới trả, không thì `<python> -m aisef.cli`; `TestLenhGoiFramework` ba phép; đo lại bằng venv sạch + chạy đúng lệnh trong hook |

## Bài học vận hành đi kèm

1. **Đo trước khi kết luận, và đo cả thứ vô can.** Lỗi 14 được "tìm ra" khi
   truy trang trống của nhánh off, nhưng trang trống thật ra do lỗi 15;
   nhánh on qua 3/3 với cùng route. Quy ước hạt giống vẫn phải nói ra, song
   nếu dừng ở nguyên nhân hợp lý đầu tiên thì lỗi 15 còn nguyên.
2. **Chạy song song nhiều bản chép dự án**: `rsync` mang theo `.git/worktrees`
   và `.aisef/worktrees` còn sót; dev server của lượt trước giữ cổng chung.
   Trước mỗi lượt: `git worktree prune`, xoá thư mục sót, `lsof -i :<cổng>`.
3. **Không commit lên nhánh chính của dự án đang có lượt chạy.** Harness kiểm
   bất biến «main không đổi trong lượt» và huỷ lượt (e9 01-06, $12,22 bỏ) —
   đúng luật, nhưng là tiền mất vì người điều phối chạy song song ẩu. Mọi
   sửa phía chủ dự án (kế hoạch, mockup, duyệt cổng) làm *trước* hoặc *giữa*
   hai lượt, không làm *trong*.
4. **Không giết tiến trình cha có pipe stdout** — con `claude` chết theo vì
   EPIPE giữa chừng và bằng chứng cụt. Giết cả cây, từ lá lên.
5. **Không chạy bộ test đầy đủ của framework song song với lượt agent thật
   có e2e đo thời gian** (lỗi 22). Cổng chấm đúng theo bằng chứng, và bằng
   chứng ấy phụ thuộc tải máy; giá là một lượt developer (~$10–30) dựng lại
   thứ đã có. Trước lượt agent: `uptime` load < số lõi, không suite nào
   khác đang chạy; đo lại đúng ứng viên trước khi kết luận "mã sai".

## Khi thêm lỗi mới

Một dòng vào bảng trên (lớp, câu hỏi, số lỗi, phép hồi quy) **cùng commit**
với phép hồi quy. Lỗi không xếp được vào lớp nào là tín hiệu cần một lớp
mới — và một câu hỏi mới.
