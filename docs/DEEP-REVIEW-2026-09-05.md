# Deep review — AISEF, 2026-09-05

> **Tài liệu lịch sử** — viết ngày 2026-09-05. v1.0.0 đã phát hành
> 2026-09-08, gói `aisef` có trên PyPI. Xem CHANGELOG.md.

Rà toàn bộ framework theo từng lớp, sau khi hai dự án thử (`e9`: 7 story
có giao diện, 77 phiên agent, $262; `par`: 4 story, 2 client) và 42 lỗi
tìm được bằng chạy thật. Mọi nhận định đánh dấu nguồn:

* **FACT** — đọc được từ mã, tài liệu, hoặc bằng chứng trên đĩa;
* **INFER** — suy luận kỹ thuật từ FACT;
* **REC** — đề xuất;
* **EXP** — ý tưởng chưa có bằng chứng đủ để làm mặc định.

Ba P0 an toàn đã **làm luôn trong lượt này** (mục G), kèm test.

---

## A. Đánh giá tổng quát

**Mạnh ở đâu.** Nguyên tắc nền "cần phán đoán → giao model, cần đảm bảo →
viết code" không nằm trên giấy: cổng story chấm từ `evidence/*.jsonl` chứ
không từ lời agent (FACT `control/gate.py`); người rà soát là phiên khác,
`build_spec` **từ chối** nối phiên cho vai rà soát (FACT `routing.py:127`);
phê duyệt gắn băm nội dung, sửa tầng trên làm tầng dưới `stale` (FACT
`approvals.py`); story song song luôn ở worktree riêng, merge tuần tự,
conflict là tín hiệu chứ không tự gỡ (FACT `worktree.py`, `run.py`). Kỷ
luật dogfood là điểm mạnh thật: 42 lỗi, mỗi lỗi có test đỏ-khi-gỡ-vá;
khai báo năng lực client chỉ nâng khi có phép thử trên agent thật (FACT
docstring `clients/opencode.py`). 966 test, 0 phụ thuộc ngoài stdlib.

**Ba điểm yếu lớn nhất.**

1. **Quan sát mang hình dạng của client, không của harness.** `cost`,
   `turns`, `guard_blocked` trích từ luồng `stream-json` của Claude Code.
   Trên OpenCode, cả 4 phiên của STORY-02-01 ghi `cost=0, turns=0,
   guard_blocked=False` trong khi guard chặn 4 lần (FACT: bằng chứng `par`
   so với sqlite của OpenCode). Sự kiện `FILE_CHANGE` có mô hình, có 6 test,
   nhưng **không nơi nào sinh ra nó** (FACT: `grep file_change(` chỉ có
   trong `observe.py` và test) → luật 3 của guard `completion` ("file sửa
   sau lần test cuối") chưa từng chạy ngoài test. 120 skill được cài, không
   có một sự kiện nào ghi skill nào được kích hoạt (FACT: không có "skill"
   trong `observe.py`/`stream.py`).
2. **Kiểm định được thiết kế sau, và phần lớn chưa cấu hình.** 12 loại kiểm
   định có mô hình; mặc định 12/12 là chuỗi rỗng (FACT `config.py`). Trên
   e9: `test` 171 lần, `lint` 99, `sast` 22, `e2e` 6, `perf` 1, `mutation`
   0, `accessibility` 0 (FACT). `coverage.min = 0.85` tồn tại nhưng không
   có mã nào đo coverage (FACT: 0 chỗ đọc). Truy vết yêu cầu trong báo cáo
   nghiệm thu là "story phủ FR có test xanh", không phải "tiêu chí chấp
   nhận X có test Y" (FACT `report.py:build`).
3. **Cách ly dừng ở git.** Tiến trình agent chạy trần trên máy người dùng,
   với đủ bí mật của người dùng (FACT: `sandbox.run` chỉ được gọi từ
   `tools.py` và `qa.py`; hai adapter client gọi `subprocess.run` trực
   tiếp). 120 skill từ 4 kho ngoài được nạp làm **chỉ dẫn** cho agent, lọc
   bằng metadata và động từ tên skill (FACT `security_filter.py`), chưa có
   bước kiểm nội dung theo tiêm prompt.

**Ba cơ hội tạo giá trị lớn nhất.**

1. Bằng chứng do harness tự ghi, không phụ thuộc client — **đã làm một
   phần hôm nay** (guard tự ghi `GUARD_BLOCK` và `FILE_CHANGE`).
2. Thiết kế kiểm định **trước** khi viết code ở mức tiêu chí chấp nhận:
   mỗi TCCN → một mã test có tên → cổng kiểm test đó *tồn tại, đã chạy,
   xanh*. Biến "người rà soát kiểm coverage" (phán đoán) thành truy vết máy.
3. Bộ kiểm hợp quy client: tạo tác biên dịch ra được **thực thi** trên
   client thật theo lịch. Bốn lỗi 39/40/41/42 cùng một lớp — mã sinh ra
   đúng cú pháp, chưa từng chạy.

**Lỗi kiến trúc phải sửa trước khi mở rộng.** Hai cái, cùng bản chất
"trạng thái ghi trước điểm không quay lại": `DONE` ghi lúc qua cổng, trước
merge (lỗi 42); `guard_blocked` ghi từ client, không từ guard. Cơ chế
chung: **chuyển trạng thái phải do bước nhật ký dẫn**, không do pha nào
"cảm thấy xong".

---

## B. Bảng điểm

| Lớp | Điểm | Bằng chứng cho điểm |
|---|---|---|
| Phương pháp luận | 7 | Vòng đời đủ PRD→kiến trúc→UX→epic/story→mockup→code→QA→DevSecOps→nghiệm thu, 8 cổng gắn băm. Thiếu: vòng đời **thay đổi sau phát hành** (không có đường "yêu cầu đổi → tầng nào stale → chạy lại từ đâu" ngoài cascade stale), mô hình đe doạ không phải artifact, NFR không có bước thiết kế kiểm định trước. |
| Harness | 7 | 7 guard tại 3 mốc, vai có quyền, worktree, nhật ký giao dịch + reconcile 3 nhánh. Trừ: agent không sandbox; OpenCode không giới hạn lượt (`turn_limit: unsupported`) — chỉ timeout chặn; `settings_file` của Claude **không bao giờ được truyền**, hook chạy nhờ `.claude/settings.json` đã commit vào repo (FACT: grep `settings_file` ngoài adapter = 0; e9 và par đều commit `.claude/`). |
| Ngữ cảnh | 6 | Chọn quyết định kiến trúc bằng **tra cứu** `Binds:` chứ không phán đoán (FACT `normalize.py:603`) — đúng hướng. Hợp đồng story, lát mockup, ảnh hưởng thay đổi cho người rà soát. Thiếu: ngân sách (`story.max_context_tokens` không ai đọc), nguồn gốc từng khối ngữ cảnh, và gói ngữ cảnh story không được lưu để truy sau. |
| Quy trình viết code | 7 | TDD, phạm vi ghi, `[bế tắc]`, phát hiện bế tắc theo danh từ riêng, `untested_symbols` bắt đúng khuôn lỗi lặp trên e9. TDD **chỉ trong prompt**: không kiểm "đỏ trước xanh". |
| UX | 7 | Mockup → hợp đồng trích từ trang **đã dựng** → đối chiếu cây accessibility của màn hình thật (FACT `aria.py`). Đây là phần ít framework nào có. Trừ: `accessibility` chưa chạy lần nào; playwright tuỳ chọn. |
| QA | 5 | Xem điểm yếu 2. Điểm cộng: bất biến "chưa cấu hình ≠ đạt", "không chạy được ≠ trượt" đã có mã và test. |
| Bảo mật | 6 | Guard bí mật/tiêm, rà soát bảo mật ngữ nghĩa phiên riêng coi diff là dữ liệu không tin (FACT prompt), lọc skill hai tầng. Trừ: `tools.sast` mặc định rỗng; SBOM/quét image chưa thấy chạy; agent trên host; skill ngoài chưa kiểm tiêm prompt. |
| DevSecOps | 5 | Sinh CI + Dockerfile + runbook (runbook có kiểm cấu trúc), cổng trước triển khai 7 mục. Trừ: CI gọi `pip install aisef` — gói chưa phát hành; không có gói bằng chứng phát hành; không có rollback; IaC ngoài phạm vi. |
| Quan sát | 5 | Xem điểm yếu 1. Cộng: chi phí theo story, cảnh báo 3× trung vị, ghi `degraded` khi sandbox suy biến và báo cáo nêu ra (FACT `report.py:_isolation_note`). |
| Đa client | 6 | Một nguồn compile ra hai client, khai năng lực có kỷ luật chứng minh. Trừ: OpenCode mù chi phí; `TOOL_ALLOWLIST: EMULATED "qua permission config"` nhưng **không có mã sinh config đó** — người rà soát trên OpenCode ghi được (FACT; đã vá hôm nay); không có bộ kiểm hợp quy. |
| DX | 6 | `doctor`/`setup`/`status`/`gates` nói được người cần làm gì; guard chặn kèm lệnh gõ được. Trừ: 20 lệnh con; hai knob cấu hình chết; không có `explain`/`resume` tường minh; log phiên agent không lộ ra khi story trượt. |
| Bảo trì | 7 | Stdlib, 966 test, chú thích nói *vì sao*. Trừ: `cli.py` 1010 dòng, `implement.py` ~700; các regex trong `preflight.py` sẽ mục theo thời gian (đã sửa 3 lần trong 2 ngày). |

---

## C. Giữ nguyên (đóng băng)

| Quyết định | Vì sao giữ |
|---|---|
| Đ1 một phiên một story | Bỏ được rotation/capsule/resume; chi phí đo được $3,44/phiên dev trên e9 — chấp nhận được. |
| Đ2 CLI gọi-một-lần, không daemon | Điều kiện duy nhất chạy được cả trong chat lẫn CI; trạng thái ở đĩa đã chứng minh resume đúng (reconcile 3 nhánh). |
| Đ3 một nguồn → compile | Golden test chống trôi; mở rộng client thứ ba là thêm adapter, không thêm bản. |
| Đ4 BMAD là dependency | Normalizer che được thay đổi upstream; `bmad_status.py` đọc schema headless của BMAD. |
| Đ5 worktree + merge tuần tự + conflict là tín hiệu | Lỗi 40 cho thấy giá trị: khi cách ly bị lách, mọi cổng mù ngay. |
| Cổng người ở mức pha, cổng máy ở mức story | 114 lần duyệt tay là vô nghĩa; cổng máy story 7 mục đã bắt được mọi lỗi thật trên e9. |
| Phê duyệt gắn băm, cascade stale | Cơ chế đúng cho "tài liệu đổi sau khi duyệt". |
| Guard là lệnh trả mã thoát | Đã nối được vào hai cơ chế hook khác nhau (settings hook, Bun plugin). |
| Người rà soát ≠ người viết, cấm ghi | Dữ liệu e9: reviewer là 46% chi phí **và** là nơi bắt mọi lỗi thật — trái lời khuyên "reviewer rẻ" của tài liệu Osmani. |
| "chưa cấu hình ≠ đạt", "không chạy được ≠ trượt" | Hai bất biến này đã có mã ở `qa.py`, `gate.py` và test. |
| Không MCP mặc định, không YAML | Đúng với ngân sách phức tạp của framework. |

---

## D. Lỗ hổng nghiêm trọng — theo **lớp lỗi**, không theo lỗi đơn lẻ

| # | Lớp lỗi | Bằng chứng | Hậu quả | Cơ chế loại bỏ cả lớp |
|---|---|---|---|---|
| D1 | **Còn tin client cho thứ harness đã biết** | Lỗi 15 (cwd), 40 (`workdir` do model đặt), 41 (matcher), `settings_file` không truyền | Guard soi nhầm cây, hoặc không chạy, mà bằng chứng trông y hệt "agent ngoan" | Harness **khai** qua env (`AISEF_WORKDIR` ✅, `AISEF_DISALLOWED_TOOLS` ✅ hôm nay); truyền `--settings` tường minh (P0 chờ kiểm trên agent thật); "nhịp tim guard": phiên developer không có một lần guard đánh giá nào → cờ đỏ |
| D2 | **Tạo tác sinh ra nhưng chưa từng thực thi** | Lỗi 31 (CI hardcode path), 39 (`.stdin()`), 41 (matcher), OpenCode `TOOL_ALLOWLIST` khai emulated nhưng không có mã | Bảo đảm tồn tại trên giấy | Bộ kiểm hợp quy client chạy trên client thật (P1) + test meta "mỗi mức khai `EMULATED` phải trỏ tới mã mô phỏng" |
| D3 | **Trạng thái ghi trước điểm không quay lại** | Lỗi 21, 42; `pre_deploy` chỉ nhìn `DONE` | Story "xong" mà code chưa lên main; CI xanh trên sprint hỏng | Chuyển trạng thái do bước nhật ký dẫn: `needs_merge` ✅ hôm nay ở `status`/`pre-deploy`; bước tiếp: `DONE` chỉ sau `merge.completed` (P1, đổi FSM) |
| D4 | **Bốn kết cục bị gộp làm hai** | Lỗi 33, 36, 37 | Thiếu công cụ = trượt; waived vẫn chạy | Một kiểu `Outcome{passed, failed, unrunnable, unconfigured, waived}` dùng chung `qa`/`gate`/`report` (P1 refactor) |
| D5 | **Bằng chứng có mô hình nhưng không có người sinh** | `FILE_CHANGE`, `GUARD_BLOCK` (đến hôm nay), skill | Luật đã test nhưng chết trong tích hợp | Guard tự ghi ✅ hôm nay; test meta "mỗi hằng `kind` trong `observe.py` phải có ít nhất một nơi gọi ngoài test" (P1) |
| D6 | **Heuristic đóng vai bảo đảm** | `preflight.py` regex sửa 3 lần/2 ngày (lỗi 27, 29); deadlock theo danh từ (24/25) | Dương tính giả chặn story tốt, âm tính giả để lọt | Heuristic chỉ là **tín hiệu tư vấn** cho người rà soát, kèm độ tin cậy; không bao giờ là mục chặn duy nhất — trừ chỗ regex đủ (story không khai scope) |
| D7 | **Kiểm định theo loại, không theo tiêu chí** | `report.py` truy vết ở mức story; TCCN không có test id | "Mọi FR có test xanh" đúng mà TCCN 3 vẫn không ai kiểm | Hợp đồng kiểm định ở mức TCCN (P1, mục E2) |
| D8 | **Agent chạy trên host** | Adapter gọi `subprocess.run` trần | Bí mật của người dùng trong tầm tay agent; lỗi 40 là bằng chứng agent với tới ngoài worktree | Chạy client trong container có mount worktree (P2, cần spike vì Claude Code cần đăng nhập) |

---

## E. Mười cải tiến giá trị nhất

Xếp theo giá trị / giảm rủi ro / đòn bẩy. Phân loại theo yêu cầu: KEEP ·
STRENGTHEN · REFACTOR · ADD · REMOVE · EXP.

| # | Cải tiến | Loại | Value | Cplx | Risk | Ưu tiên |
|---|---|---|---|---|---|---|
| E1 | Cấm tool theo vai ở harness (`AISEF_DISALLOWED_TOOLS`) | STRENGTHEN | High | Low | Low | **P0 ✅** |
| E2 | Guard tự ghi `GUARD_BLOCK` + `FILE_CHANGE` — hồi sinh luật 3 `completion`, hết mù trên OpenCode | STRENGTHEN | High | Low | Low | **P0 ✅** |
| E3 | "Xong" phải là "đã merge" ở `status`/`pre-deploy` | STRENGTHEN | High | Low | Low | **P0 ✅** |
| E4 | Truyền `--settings` tường minh cho Claude + nhịp tim guard | STRENGTHEN | Critical | Low | Med | **P0** (chờ kiểm trên agent thật) |
| E5 | Hợp đồng kiểm định ở mức **tiêu chí chấp nhận**: TCCN → test id → cổng | ADD | Critical | Med | Med | **P1** |
| E6 | Bộ kiểm hợp quy client (5 phép thử chạy trên client thật, có lịch) | ADD | High | Med | Low | **P1** |
| E7 | Một kiểu `Outcome` 5 giá trị dùng chung | REFACTOR | High | Med | Med | **P1** |
| E8 | TDD kiểm được: story thêm test thì phải có lần `test` đỏ trước lần xanh cuối; test có sẵn không được giảm số ca | STRENGTHEN | Med | Low | Med | **P1** |
| E9 | Sự kiện `skill_use`: skill nào được kích hoạt, ở phiên nào | ADD | Med | Low | Low | **P1** |
| E10 | Gỡ knob chết (`coverage.min`, `story.max_context_tokens`) có di trú, hoặc nối chúng vào cơ chế thật | REMOVE | Med | Low | Low | **P1** |

Ngoài bảng, hai việc P2 đáng ghi: sandbox tiến trình agent (D8), và tra
cứu tài liệu thư viện theo yêu cầu bằng CLI (luật 12 "không bịa API" hiện
chỉ là lời nhắc).

---

## F. Thay đổi kiến trúc thật sự cần

Chỉ ba, đều **giữ** năm quyết định Đ1–Đ5.

1. **Chuyển trạng thái do nhật ký dẫn** (ảnh hưởng: `state.py`, `run.py`).
   Hiện `DONE` ghi lúc qua cổng; nhật ký ghi `merge.completed` sau. Hai
   nguồn sự thật cho một câu hỏi. Đề xuất: thêm cạnh `DONE → MERGED` hoặc
   đổi nghĩa `DONE` thành "đã merge" và thêm `VERIFIED` cho "qua cổng".
   Hôm nay đã bắc cầu bằng `needs_merge`; thay đổi FSM là P1 vì đụng
   `status`, `report`, `pre_deploy`, `scheduler` (story phụ thuộc).
2. **Bằng chứng do harness sinh, client chỉ bổ sung** (ảnh hưởng:
   `observe.py`, `cli.cmd_guard`, adapter). Đã làm phần guard. Phần còn
   lại: `cost`/`turns` cho OpenCode qua `--format json` (lead đã ghi thành
   task riêng), `skill_use`.
3. **Hợp đồng kiểm định ở mức TCCN** (ảnh hưởng: `normalize.Story`,
   `story_split`, `gate.py`, `report.py`, prompt `story-implement`). Story
   mang `acceptance_tests: {tccn_index: test_id}`; agent đặt tên test theo
   id; cổng kiểm từng id có trong output test runner. Đây là chỗ biến phán
   đoán "test này phủ tiêu chí kia không" thành tra cứu.

Không đề xuất: đổi BMAD, đổi client runtime, thêm daemon, thêm MCP mặc
định, rewrite CLI.

---

## G. Backlog

### P0 — đã làm trong lượt này (966 → 987 test)

**G1. Cấm tool theo vai ở harness** — `harness/guardrails.py`
(`ENV_DISALLOWED_TOOLS`, `check_role_tool`, kiểm ở tầng điều phối),
`phases/implement.py` (reviewer + security khai env). Bất biến: *vai rà
soát không ghi được trên bất kỳ client nào*. Test: `TestCamToolTheoVai`
(5), `TestVaiRaSoatKhaiToolBiCam` (3). DoD: guard trả 2 cho `write`/`Write`
khi env có; im lặng khi không có; security vẫn không mang mã story.

**G2. Guard tự ghi bằng chứng** — `guardrails.record_outcome`,
`cli.cmd_guard`, `observe.Evidence.guard_blocks`. Bất biến: *mỗi lần
chặn có một `GUARD_BLOCK`; mỗi Write/Edit được cho qua có một
`FILE_CHANGE`*. Test: `TestGuardTuGhiBangChung` (4) — trong đó
`test_cho_ghi_thi_ghi_file_change_va_luat_3_song_lai` chứng minh luật 3
của `completion` giờ chặn thật. DoD: `stale_since_last_test()` khác rỗng
sau một Write được phép.

**G3. Xong ≠ đã merge** — `journal.Journal.needs_merge`,
`deploy.pre_deploy`, `cli.cmd_status`. Bất biến: *cổng trước triển khai
không qua khi có story DONE mà nhật ký có `worktree.created` và không có
`merge.completed`*. Test: `TestCanMerge` (4), `TestXongPhaiLaDaMerge` (3),
`TestStatusNoiRoChuaMerge` (1). DoD: `--no-isolate` không bị đòi merge.

### P0 — chưa làm, cần kiểm trên agent thật

**G4. Truyền `--settings` tường minh + nhịp tim guard.**
*Vấn đề:* hook Claude Code chỉ chạy nếu `.claude/settings.json` nằm trong
worktree, tức đã commit. Dự án `.gitignore` thư mục `.claude/` sẽ chạy
story với **zero guard**, và bằng chứng trông y hệt agent ngoan.
*Gốc:* `RunSpec.settings_file` có, adapter hỗ trợ `--settings`, nhưng
không nơi nào đặt nó. *Cơ chế:* `implement.py` đặt
`spec.settings_file = project/.claude/settings.json` nếu có; `doctor`
kiểm hook tới được từ một worktree; cổng story thêm mục "guard có chạy":
phiên developer phải có ≥1 `GUARD_BLOCK` hoặc `FILE_CHANGE` (nay guard
ghi được), không có → `skipped=False, passed=False` "guard chưa từng
đánh giá thao tác nào — kiểm hook". *Rủi ro:* Claude nạp cả settings
project lẫn `--settings` → hook chạy hai lần (idempotent, +110 ms/lần).
Phải đo trên `par` với `.claude/` gỡ khỏi git trước khi nâng lên xanh.
*Test:* `spec.settings_file` được đặt; gate mục "guard có chạy" đỏ khi
evidence không có sự kiện guard nào; kiểm thật trên agent.

### P1

**G5. Hợp đồng kiểm định mức TCCN** (E5). Files: `normalize.py`,
`story_split.py`, `gate.py`, `report.py`, `kit/prompts/story-implement.md`,
`kit/prompts/story-review.md`. Bất biến: *mọi TCCN có ít nhất một test id
xuất hiện trong output của lần `test` xanh cuối*. Test: story 2 TCCN, agent
giả chỉ viết test cho 1 → cổng đỏ nêu đúng TCCN thiếu. Phụ thuộc: cần
parser output test runner theo stack (node:test/vitest/pytest — tối thiểu
tên test). DoD: báo cáo nghiệm thu có bảng FR → TCCN → test id.

**G6. Bộ kiểm hợp quy client** (E6). File mới `tests/conformance/` chạy
bằng cờ `AISEF_CONFORMANCE=1`, một job CI theo lịch. Năm phép thử trên
mỗi client thật: (a) `rm -rf` bị chặn, tệp còn; (b) Write chứa
`os.system(f"…{x}")` bị chặn, không tệp; (c) `glob`/`read` đi qua; (d) từ
worktree, `pwd` và `git branch --show-current` là worktree/nhánh story;
(e) vai reviewer gọi write → chặn. DoD: bảng kết quả ghi vào
`docs/CONFORMANCE.md` kèm ngày và phiên bản client.

**G7. `Outcome` 5 giá trị** (E7). `qa.py`, `gate.py`, `report.py`,
`deploy.py`. Loại `KindResult.unrunnable`/`skipped`/`waived` rời rạc. Test:
bảng 5×(gate, pre-deploy, report) khẳng định cách hiện.

**G8. TDD kiểm được** (E8). `gate.py`: nếu diff thêm/sửa tệp test →
evidence phải có `test ok=False` trước `test ok=True` cuối; `qa:test-delta`:
đếm ca test trong tệp test có sẵn ở base vs head, giảm → cảnh báo vào ngữ
cảnh reviewer (không tự chặn — "cập nhật kỳ vọng" là hợp lệ). Test: agent
giả viết test + code một lượt, xanh ngay → cổng ghi "không có lần đỏ".

**G9. `skill_use`** (E9). `stream.py` bắt `tool_use name=Skill`;
OpenCode qua `--format json` (task riêng). `status` in "skill được dùng /
skill cài".

**G10. Knob chết** (E10). `coverage.min`: nối vào parser coverage theo
stack (`c8`/`coverage.py`) **hoặc** gỡ khỏi `DEFAULTS` với `Config.load`
cảnh báo khoá cũ thay vì lỗi. `story.max_context_tokens`: gỡ, hoặc đo
`len(prompt)/4` và ghi vào evidence `agent_run` để cảnh báo. Không để knob
tồn tại mà không có cơ chế — đó chính là "chưa cấu hình ≠ đạt" áp cho
cấu hình.

**G11. Test meta cho D2/D5.** (a) mỗi `Support.EMULATED` trong adapter
phải kèm tên hàm mô phỏng tồn tại; (b) mỗi hằng `kind` trong `observe.py`
có ít nhất một caller ngoài `observe.py` và `tests/`.

**G12. `DONE → MERGED`** (F1). Sau G3 ổn định.

### P2

* Sandbox tiến trình agent (D8) — spike: Claude Code trong container với
  OAuth token mount, worktree mount, `--network` chỉ tới API.
* Tra cứu tài liệu theo yêu cầu (`aisef doc <package>` gọi context7 CLI
  hoặc cache cục bộ) — cho luật 12.
* Guard "mã tham chiếu quy trình" (luật 6): chặn `STORY-\d+-\d+` trong
  tệp nguồn ngoài `docs/`.
* Vòng đời thay đổi sau phát hành: `aisef change <FR>` → đánh stale đúng
  tầng, sinh story delta.
* Chia `cli.py` theo pha (thuần cơ học).

---

## H. Kế hoạch hồi quy / đánh giá

1. **Mỗi lỗi 15–42 đã có test đỏ-khi-gỡ-vá** — giữ quy ước: commit vá
   phải nêu lệnh chứng minh test đỏ khi bỏ vá.
2. **Bộ kiểm hợp quy client** (G6) chạy theo lịch — vì lớp D2 không bắt
   được bằng unit test.
3. **Test meta** (G11) — bắt lớp D5 ngay lúc thêm sự kiện/năng lực mới.
4. **Kho hồi quy dogfood:** giữ `par` (3 story độc lập + 1 story OpenCode)
   làm dự án chuẩn; mỗi phát hành chạy `run --epic EPIC-01 --force` trên
   cả hai client, so với mốc: 3/3 xong lượt đầu, chi phí trong 2× mốc
   ($3,14), `main` chỉ đổi qua merge. `e9` giữ làm kho hồi quy cho giao
   diện (mockup-map, `[bế tắc]`, deadlock).
5. **Eval cho prompt:** ba prompt vận hành có `version`; thêm bộ mẫu
   (diff thật từ e9 + phán quyết người) để mỗi lần đổi prompt reviewer đo
   được tỉ lệ bắt mục chặn thật — hiện đổi prompt không có thước.
6. **Chi phí là telemetry, không phải mục tiêu:** giữ cảnh báo 3× trung
   vị; không thêm gate chi phí.

---

## I. Không nên làm bây giờ

| Thứ hấp dẫn | Vì sao không |
|---|---|
| MCP bật mặc định (context7, serena, gitnexus) | Thêm bề mặt tin cậy và ngữ cảnh cho mọi phiên; `review.impact_provider` đã là khe cắm cho gitnexus/serena **khi cần**, qua lệnh, không qua giao thức thường trú. |
| Đổi reviewer sang model rẻ | Dữ liệu e9: reviewer bắt mọi lỗi thật. Chỉ thử A/B trên security reviewer và designer, có thước (H5) trước. |
| Tự gỡ merge conflict | Conflict là bằng chứng `write_scope` sai; gỡ hộ là xoá bằng chứng. |
| Cổng do LLM chấm | Trái nguyên tắc nền. Model chỉ **cấp tín hiệu** (review, impact), cổng đọc bằng chứng. |
| RAG vector trên codebase | `Binds:` tra cứu + `write_scope` + impact report đã trả lời "cần đọc gì"; vector thêm phán đoán vào chỗ đang là tra cứu. |
| Daemon / server điều phối | Phá Đ2; resume từ đĩa đã chứng minh đủ. |
| OpenSpec/spec-kit cạnh BMAD | Hai nguồn sự thật cho kế hoạch. |
| Đổi FSM lớn ngay | G3 đã bắc cầu; đổi FSM khi có G5 để làm một lần. |
| Sinh thêm 13 "agent prompt" như SOLUTION §5.1 liệt kê | Hiện có 5 prompt vận hành và chúng đủ; `kit/agents/` không tồn tại (FACT) — cập nhật tài liệu, không tạo thêm. |

---

## J. Ngôi sao dẫn đường

**Khác gì BMAD + skill + MCP + coding agent ghép lại?** Bốn thứ đó cộng
lại cho ra một cỗ máy *sinh* tốt. Thứ chúng không có, và AISEF có (hoặc
đang tiến tới), là **chuỗi bằng chứng không cắt**: yêu cầu → quyết định
kiến trúc có mã → story có phạm vi và hợp đồng kiểm định → worktree có
guard → cổng đọc bằng chứng do harness ghi → merge có nhật ký → báo cáo
nghiệm thu sinh từ đĩa. Ở mỗi mắt xích, câu hỏi không phải "agent nói gì"
mà "đĩa ghi gì". Ghép bốn thứ kia lại vẫn phải tin lời agent ở ít nhất
ba mắt xích.

**Bốn năng lực phải vượt trội để có cơ sở gọi là hàng đầu:**

1. **Truy vết máy từ tiêu chí chấp nhận tới test đã chạy** (G5) — không
   phải "có test", mà "tiêu chí này, test này, lần chạy này, xanh".
2. **Bằng chứng độc lập với client** (G2 ✅, G4, G9) — đổi Claude sang
   OpenCode sang client thứ ba, bằng chứng cùng hình dạng, cổng cùng
   phán quyết.
3. **Cách ly được chứng minh, không giả định** (D1 ✅ phần lớn, D8) —
   worktree, guard, và sau này container; mỗi lớp có phép thử trên client
   thật.
4. **Thất bại được đặt tên đúng** (D4, "chưa cấu hình ≠ đạt", "không chạy
   được ≠ trượt", "chưa sửa ≠ không sửa được", `[bế tắc]`) — framework
   không bao giờ báo xanh vì im lặng, và không bao giờ đốt tiền vào chỗ
   không có lối ra.

Giữ bốn điều này, framework không cần thêm tính năng để khác biệt — nó
cần mỗi tính năng đã có **chứng minh được là đang chạy**.
