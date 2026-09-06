# Kế hoạch hành động AISEF — sau deep review 2026-09-05

Nguồn: `docs/DEEP-REVIEW-2026-09-05.md`. Mục tiêu duy nhất của kế hoạch:
đóng 8 lớp lỗi D1–D8 bằng **cơ chế**, không bằng vá từng lỗi, và chứng
minh mỗi cơ chế đang chạy — trên unit test **và** trên agent thật.

Sắp theo phụ thuộc kỹ thuật, chia 5 đợt. Mỗi hạng mục có: vấn đề → cơ
chế → tệp → bất biến → test → định nghĩa xong (DoD) → ước lượng → rủi ro.
Ước lượng tính bằng **ngày-công** của một người làm toàn thời gian, dựa
trên tốc độ thực tế hai ngày qua (ba P0 kèm 21 test: ~0,3 ngày).

Quy ước xuyên suốt, không có ngoại lệ:

* mọi bản vá đi kèm test **đỏ khi gỡ vá**, commit ghi lệnh chứng minh;
* mức khai năng lực (`NATIVE`/`EMULATED`) chỉ nâng khi có phép thử trên
  client thật, ghi ngày và phiên bản client vào docstring;
* không thêm knob cấu hình nào mà không có cơ chế đọc nó.

---

## Tổng quan 5 đợt

| Đợt | Tên | Đóng lớp | Hạng mục | Ước lượng | Chặn bởi |
|---|---|---|---|---|---|
| 0 | Đã xong 2026-09-05 | D1 (phần), D3 (phần), D5 (phần) | G1 G2 G3 | — | — |
| 1 | Tin cậy & trạng thái | D1, D3, D5 | G4 G11 G12 G10a | 3,5 ngày | — |
| 2 | Hợp quy client | D2 | G6 G9 + `--format json` | 3 ngày | G4 |
| 3 | Kiểm định theo tiêu chí | D4, D6, D7 | G7 → parser → G5 → G10b → G8 | 8 ngày | G12 |
| 4 | Phát hành | — | PyPI · GĐ-9 · tài liệu · hợp quy lần 1 | 4 ngày + chi phí agent | Đợt 1–3 |
| 5 | Cách ly & vòng đời | D8 | sandbox agent · tra cứu tài liệu · `change` · guard luật 6 · chia `cli.py` | 8 ngày | Đợt 4 |

Tổng ≈ **26,5 ngày-công** cho tới hết đợt 5; **18,5 ngày** tới mốc phát
hành (hết đợt 4). Chi phí agent thật ước **$120–180** (mục "Chi phí").

Vì sao thứ tự này:

* G12 (FSM) đứng trước G5 vì G5 sẽ viết lại truy vết trong `report.py`,
  và truy vết phải hỏi "đã merge" chứ không hỏi "DONE" — làm G5 trước là
  sửa `report.py` hai lần.
* G7 (`Outcome`) đứng trước G5 và G8 vì hai hạng mục đó sinh kết cục mới
  cho cổng; không có kiểu chung thì mỗi cái tự chế một kiểu nữa — đúng lớp
  D4 đang cần xoá.
* G6 (hợp quy) chờ G4 vì phép thử "hook tới được từ worktree" chính là
  phép thử thật của G4; làm chung một lần chạy agent, tiết kiệm tiền.
* G11 (test meta) làm sớm nhất có thể vì nó rẻ (0,5 ngày) và chặn lớp
  D2/D5 tái sinh trong mọi hạng mục sau.

---

## Đợt 1 — Tin cậy & trạng thái (3,5 ngày)

### G4. Truyền `--settings` tường minh + nhịp tim guard — 1,5 ngày

**Vấn đề.** Hook Claude Code chỉ chạy nếu `.claude/settings.json` nằm
trong worktree, tức đã commit. Dự án `.gitignore` thư mục `.claude/` sẽ
chạy story với **zero guard**, và bằng chứng trông y hệt agent ngoan.
`RunSpec.settings_file` có, adapter hỗ trợ `--settings`, không nơi nào
đặt (FACT).

**Cơ chế.** Ba lớp, từ hợp tác tới bảo đảm:

1. `implement.py`: mọi `build_spec` đặt `spec.settings_file =
   project/.claude/settings.json` nếu tệp tồn tại — cho cả ba vai.
2. `doctor`: mục "hook tới được từ worktree" — dựng worktree tạm, chạy
   `claude -p 'echo' --settings …` với một guard thử, kiểm mã thoát 2.
   Không có `claude` trên máy → ghi "chưa kiểm được", không phải xanh.
3. Cổng story mục **"guard có chạy"**: phiên developer phải có ≥ 1 sự
   kiện `GUARD_BLOCK` hoặc `FILE_CHANGE` (nay guard tự ghi). Không có →
   `passed=False`, lý do "guard chưa đánh giá thao tác nào — kiểm hook".
   Story không ghi gì cả (agent chỉ đọc rồi bỏ) cũng đỏ ở mục này, và đó
   là đúng: story không ghi gì thì không xong.

**Tệp.** `phases/implement.py`, `cli.py` (`cmd_doctor`), `control/gate.py`,
`kit/prompts/story-implement.md` (không đổi), `tests/test_implement.py`,
`tests/test_gate.py`, `tests/test_cli.py`.

**Bất biến.** *Không phiên developer nào được tính là xong khi guard chưa
từng đánh giá một thao tác ghi nào của nó.*

**Test.** Unit: `spec.settings_file` đặt khi tệp có, rỗng khi không; gate
đỏ với evidence không có sự kiện guard; `doctor` ghi "chưa kiểm được"
khi thiếu `claude`. **Thật:** trên `par`, gỡ `.claude/` khỏi git, chạy
`run --epic EPIC-01 --force` một story bằng Claude — trước vá: story chạy,
evidence không có `GUARD_BLOCK`/`FILE_CHANGE`; sau vá: có.

**DoD.** Hai lượt chạy thật (trước/sau) ghi vào docstring `claude_code.py`
kèm ngày, phiên bản Claude Code; hook chạy hai lần (project + `--settings`)
đo được độ trễ và chấp nhận nếu < 300 ms/lượt gọi.

**Rủi ro.** Claude nạp cả hai settings → guard chạy hai lần; idempotent
nhưng cần đo. Nếu `--settings` **thay thế** thay vì gộp thì không có gì
mất. Cả hai trường hợp đều chấp nhận.

### G11. Test meta chống lớp D2/D5 — 0,5 ngày

**Vấn đề.** `FILE_CHANGE`/`GUARD_BLOCK` có mô hình nhưng không ai sinh
suốt hai tuần; `TOOL_ALLOWLIST: EMULATED` khai mà không có mã. Cả hai chỉ
lộ khi có người tình cờ đọc.

**Cơ chế.** Hai test đọc chính mã nguồn:

1. `test_observe_kinds_have_producers`: với mỗi hằng `kind` trong
   `observe.py`, phải có ít nhất một tệp trong `aisef/` (ngoài
   `observe.py`) tham chiếu nó. Tạm loại trừ `NOTE` nếu cố ý.
2. `test_emulated_capabilities_name_their_mechanism`: mỗi
   `Support.EMULATED` trong `clients/*.py` phải kèm chú thích
   `# emulated by: <tên hàm>` và hàm ấy phải tồn tại (`getattr`). Sửa
   `opencode.py` cho khớp: `TOOL_ALLOWLIST` → `emulated by:
   guardrails.check_role_tool`; `MACHINE_OUTPUT` → chờ `--format json`,
   tạm hạ xuống `UNSUPPORTED` cho đúng sự thật.

**Tệp.** `tests/test_meta.py` (mới), `clients/opencode.py`.

**DoD.** Hai test xanh; hạ `MACHINE_OUTPUT` xuống `UNSUPPORTED` tới khi
đợt 2 chứng minh.

### G12. `DONE` nghĩa là đã merge — 1 ngày

**Vấn đề.** Hai nguồn sự thật cho "code đã lên nhánh chính chưa": trạng
thái (`DONE` lúc qua cổng) và nhật ký (`merge.completed`). G3 đã bắc cầu
bằng `needs_merge`; cầu là tạm.

**Cơ chế.** Thêm trạng thái `VERIFIED` (qua cổng, chưa merge). Cạnh:
`VERIFYING → VERIFIED`, `VERIFIED → DONE` chỉ do `run.py` gọi **ngay sau**
`journal.record("merge.completed")`; `VERIFIED → PENDING` khi merge đụng
và người sửa xong. `--no-isolate`: `VERIFYING → DONE` trực tiếp vì không
có bước merge — cạnh này được phép, ghi `note="no-isolate"`.

**Ảnh hưởng.** `state.py` (FSM + `satisfies_dependents` = `DONE` **hoặc**
`VERIFIED`? — **không**: story phụ thuộc phải thấy code trên nhánh chính,
nên chỉ `DONE`), `run.py`, `cli.cmd_status`, `deploy.pre_deploy` (bỏ cầu
`needs_merge`, hỏi trạng thái), `report.py`, `scheduler.py` (đọc
`done_ids`), tài liệu SOLUTION §15.

**Bất biến.** *`DONE` xuất hiện trong `sprint-status.json` sau
`merge.completed` trong nhật ký, không bao giờ trước.* Test đọc hai tệp và
so `seq`/thời điểm.

**Test.** FSM: cạnh mới hợp lệ, cạnh cũ `VERIFYING → DONE` bị từ chối khi
có worktree; `run.py`: merge đụng → `VERIFIED`, chạy lại → merge → `DONE`;
di trú: `sprint-status.json` cũ có `DONE` + nhật ký `needs_merge` → đọc
lên thành `VERIFIED` (một lần, ghi log).

**DoD.** `par` chạy lại từ hiện trạng cũ (có story `DONE` chưa merge do
lỗi 42) → di trú đúng, merge, `DONE`. Gỡ `needs_merge` khỏi `deploy.py` và
`cli.py` (giữ ở `journal.py` cho di trú).

**Rủi ro.** Trung bình — chạm 6 tệp. Giảm bằng cách làm **sau** G4 và
**trước** G5, trong một nhánh riêng, chạy `par` cả hai client trước khi
merge.

### G10a. Gỡ `story.max_context_tokens` — 0,5 ngày

**Cơ chế.** Xoá khỏi `DEFAULTS`/`TYPES`; `Config.load` gặp khoá đã gỡ →
cảnh báo "khoá X không còn tác dụng, xoá khỏi `.ai/config.json`" thay vì
`ConfigError`. Danh sách khoá đã gỡ là một hằng `RETIRED` có ngày. Thay
bằng đo thật: `agent_run` ghi `prompt_chars` vào evidence; `status` cảnh
báo story có prompt > 3× trung vị (cùng cơ chế với chi phí).

**Tệp.** `config.py`, `harness/observe.py`, `clients/claude_code.py`,
`clients/opencode.py`, `tests/test_config.py`, SOLUTION §13.

**DoD.** Dự án cũ có khoá nạp được, in cảnh báo một lần; evidence có
`prompt_chars`. `coverage.min` **chưa** gỡ ở đây — chờ parser đợt 3.

---

## Đợt 2 — Hợp quy client (3 ngày) — chặn bởi G4

### G6. Bộ kiểm hợp quy — 2 ngày

**Vấn đề.** Lỗi 31/39/40/41 cùng lớp: tạo tác biên dịch đúng cú pháp,
chưa từng chạy trên client. Unit test không bắt được lớp này theo định
nghĩa.

**Cơ chế.** `tests/conformance/` chạy khi `AISEF_CONFORMANCE=1`, mỗi
client một lớp test, cùng **5 phép thử** — đúng những phép đã dùng tay
ngày 2026-09-05:

| # | Phép thử | Chứng minh |
|---|---|---|
| C1 | bash `rm -rf <thư mục có tệp>` | tool failed bằng stderr guard; tệp **còn** |
| C2 | Write chứa `os.system(f"…{x}")` | tool failed; **không** tệp ra đĩa |
| C3 | `glob`/`read` trong worktree | đi qua, không guard nào chặn |
| C4 | từ worktree: `pwd; git branch --show-current` | trả worktree và nhánh story |
| C5 | env vai reviewer, gọi Write | chặn bởi `check_role_tool` |

Mỗi phép chạy trên worktree thật do `WorktreeManager` dựng, guard thật,
`.claude/` **không** commit (kiểm G4). Kết quả ghi vào
`docs/CONFORMANCE.md`: client, phiên bản, ngày, 5 ô ✅/✗, chi phí.

**Tệp.** `tests/conformance/__init__.py`, `test_claude.py`,
`test_opencode.py`, `docs/CONFORMANCE.md`, một job CI theo lịch (tuần) có
secret của client.

**Bất biến.** *Không phát hành khi `CONFORMANCE.md` cũ hơn 14 ngày hoặc có
ô ✗.* `pre-deploy` của **chính kho framework** (không phải dự án đích)
đọc tệp này.

**DoD.** Chạy được bằng một lệnh; kết quả lần đầu ghi vào tài liệu.

**Chi phí.** ~$1/client/lượt với model nhỏ.

### `--format json` cho OpenCode — 0,5 ngày (task đã tạo)

Theo task `task_a7530bf6`: nếu lấy được cost/turns/session → parser +
nâng `MACHINE_OUTPUT` lên `NATIVE`; không thì giữ `UNSUPPORTED` và ghi
đã thử gì. Không có bước này, `cost.warn_multiple` mù trên OpenCode mãi.

### G9. Sự kiện `skill_use` — 0,5 ngày

**Cơ chế.** `stream.py` bắt `tool_use` có `name == "Skill"` → sự kiện
`SKILL_USE{name}`; OpenCode qua `--format json` nếu có. `status` in
"skill dùng / skill cài"; `report` mục 4 (harness) nêu skill chưa từng
dùng sau N story — đầu vào cho việc tỉa catalog.

**Bất biến.** Không có. Đây là **quan sát**, không phải cổng — không chặn
gì vì skill không được dùng.

---

## Đợt 3 — Kiểm định theo tiêu chí (8 ngày) — chặn bởi G12

### G7. Một kiểu `Outcome` — 1,5 ngày

**Vấn đề.** `KindResult` có `ran/ok/skipped/unrunnable`, `Check` có
`passed/skipped`, `waived` là danh sách riêng — bốn kết cục bị gộp làm
hai ở ba chỗ (lỗi 33/36/37).

**Cơ chế.** `control/outcome.py`:

```
Outcome = PASSED | FAILED | UNRUNNABLE | UNCONFIGURED | WAIVED
```

với `blocks_release` (FAILED, UNRUNNABLE), `counts_as_done` (PASSED,
WAIVED), `must_be_named` (UNCONFIGURED, UNRUNNABLE — phải hiện ra, không
được im). `KindResult`, `Check`, `PreDeployReport` đều mang một `Outcome`;
`summary()` của ba nơi dùng một bảng ký hiệu.

**Bất biến.** *Mọi kết cục không phải PASSED đều có lý do một dòng, và
UNCONFIGURED/UNRUNNABLE không bao giờ được hiển thị bằng cùng ký hiệu với
PASSED.* Test bảng 5 × 3 nơi hiển thị.

**Rủi ro.** Refactor thuần, nhiều test hiện có khẳng định chuỗi → sửa
test theo; không đổi hành vi cổng.

### Parser output test runner — 1,5 ngày

**Vấn đề.** G5 cần biết *test nào* đã chạy và xanh; G10b cần coverage.
Cả hai đọc output runner; làm một lần.

**Cơ chế.** `harness/testlog.py`: từ stdout của lần `test`, trả
`{test_ids: [...], passed: [...], failed: [...], coverage: float | None}`.
Ba định dạng có thật trong hai dự án thử: `node --test` (TAP), `vitest`
(reporter mặc định + `--reporter=json` nếu cấu hình), `pytest` (`-v` +
`--cov` nếu có). Không nhận ra định dạng → `test_ids=[]`, và G5 ghi
"không đọc được tên test — cấu hình reporter" (UNCONFIGURED, không phải
đạt). Ghi vào evidence `tool_run test.detail.test_ids`.

**DoD.** Ba fixture output thật (lấy từ `par`, `e9`, một dự án pytest),
parser đúng 100 % trên chúng; output lạ không ném.

### G5. Hợp đồng kiểm định mức tiêu chí chấp nhận — 3 ngày

**Vấn đề.** Truy vết hiện là "story phủ FR có test xanh". TCCN 3 không ai
kiểm mà báo cáo vẫn xanh. Reviewer được bảo "chỉ ra test nào phủ tiêu
chí nào" — phán đoán ở chỗ lẽ ra là tra cứu.

**Cơ chế.**

1. `Story` thêm `acceptance_tests: dict[int, list[str]]` — TCCN i → mã
   test. Mã theo quy ước `AC-<story>-<i>` xuất hiện trong **tên test**
   (`test('AC-STORY-01-01-2: chuỗi rỗng …')`). BMAD không cần biết: mã
   sinh bởi `story_split` từ chỉ số TCCN.
2. `story-implement.md`: bảng TCCN kèm mã; "mỗi mã phải xuất hiện trong
   tên ít nhất một test".
3. Cổng story mục **"tiêu chí có test"**: với mỗi TCCN, `test_ids` của
   lần `test` xanh cuối phải chứa mã ấy. Thiếu → FAILED nêu đúng TCCN.
   `test_ids` rỗng vì không đọc được reporter → UNCONFIGURED (không đạt,
   không đổ lỗi cho story).
4. `story-review.md`: bỏ mục 1 "chỉ ra test nào phủ" (máy làm rồi), thay
   bằng "test mang mã AC-x có **kiểm đúng điều tiêu chí nói** không" —
   đúng phần cần phán đoán.
5. `report.py`: bảng FR → story → TCCN → test id → lần chạy.

**Tệp.** `control/normalize.py`, `phases/story_split.py`,
`control/gate.py`, `phases/report.py`, hai prompt, `harness/testlog.py`,
`tests/test_gate.py`, `tests/test_report.py`, `tests/test_story_split.py`.

**Bất biến.** *Mỗi TCCN của story `DONE` có ít nhất một test id trong
output của lần `test` xanh cuối cùng.*

**Test.** Agent giả viết test cho 1/2 TCCN → cổng đỏ nêu TCCN 2; reporter
không đọc được → UNCONFIGURED; báo cáo có bảng đủ cột. **Thật:** chạy lại
một story `par` — agent Claude đặt tên test theo mã mà không cần nhắc
thêm? Đo tỉ lệ tuân thủ; dưới 100 % thì sửa prompt, không hạ cổng.

**DoD.** `par` 4/4 story qua cổng mới; `e9` STORY-01-01 chạy lại qua;
`ACCEPTANCE-REPORT.md` có bảng TCCN.

### G10b. `coverage.min` thật — 0,5 ngày

Sau parser: `tool_run test.detail.coverage` có số → cổng story so với
`coverage.min` (FAILED nếu thấp hơn); không có số → UNCONFIGURED "runner
chưa bật coverage — thêm `--coverage`/`--cov` vào `tools.test`". Không có
cơ chế thì gỡ khoá như G10a. SOLUTION §16 "coverage ≥ ngưỡng" từ đó mới
có nghĩa.

### G8. TDD kiểm được — 1,5 ngày

**Cơ chế.** Hai tín hiệu, một chặn một cảnh báo:

1. **Đỏ trước xanh** (chặn nhẹ): nếu diff của story thêm tệp test hoặc
   thêm mã `AC-…` mới, evidence phải có `tool_run test ok=False` **trước**
   lần `ok=True` cuối. Không có → mục cổng "TDD" = FAILED với lý do "test
   xanh ngay lần đầu — chưa chứng minh nó kiểm được gì". Đây là điều
   prompt đã đòi; giờ máy kiểm.
2. **Test có sẵn không bị yếu đi** (cảnh báo → ngữ cảnh reviewer):
   `qa:test-delta` đếm ca test (`test(`/`it(`/`def test_`) trong tệp test
   có ở `base_ref` so với head; giảm → ghi vào `impact` cho reviewer kèm
   danh sách ca biến mất. Không tự chặn: "cập nhật kỳ vọng" là hợp lệ và
   cần phán đoán.

**Bất biến.** *Story thêm test mà chưa từng có lần test đỏ thì không
`VERIFIED`.*

**Rủi ro.** Dương tính giả với story chỉ refactor (không thêm test) —
loại trừ đúng bằng điều kiện "diff thêm test". Story sửa test có sẵn cho
đúng hành vi mới → có lần đỏ tự nhiên.

---

## Đợt 4 — Phát hành (4 ngày + chi phí agent)

| # | Việc | Chi tiết | Ước lượng |
|---|---|---|---|
| R1 | **Đưa gói lên PyPI** | Quyết định của chủ đầu tư: tên `aisef` (kiểm còn trống), tài khoản, token trong CI. Tới lúc đó CI sinh ra dùng `--install-spec git+https://…@<tag>`. | 0,5 ngày + quyết định |
| R2 | **GĐ-9 đầu-cuối trên dự án có giao diện** | Chạy nốt EPIC-01 của `e9` (4 story, ước $40–60) với toàn bộ cơ chế đợt 1–3; rồi `qa` (cấu hình `e2e` + `accessibility` thật bằng playwright + axe), `devsecops`, `pre-deploy`, `report`. Đây là lần đầu `accessibility` và `mutation` chạy được. | 1,5 ngày + $60–90 |
| R3 | **Hợp quy lần 1** | Chạy G6 trên hai client, ghi `CONFORMANCE.md`. | 0,5 ngày + $2 |
| R4 | **Tài liệu đúng sự thật** | SOLUTION §5.1 liệt kê `kit/agents/` 13 agent và `kit/mcp/` — không tồn tại; §11 "OpenCode hậu kiểm" đã lỗi thời; §13 bảng knob; README mục guard. Sửa cho khớp mã, không thêm. | 1 ngày |
| R5 | **Kho hồi quy dogfood** | Đóng băng `par` và `e9` thành `tests/dogfood/` có script chạy lại + mốc so sánh (3/3 lượt đầu, chi phí ≤ 2× mốc, `main` chỉ đổi qua merge). | 0,5 ngày |

**Điều kiện phát hành** (đọc được bằng lệnh, không phải cảm giác):

* 100 % test unit xanh; `CONFORMANCE.md` ≤ 14 ngày, không ô ✗;
* `par` chạy lại trên hai client đạt mốc R5;
* `e9` EPIC-01 xong, `ACCEPTANCE-REPORT.md` có bảng TCCN → test id, mục
  `accessibility` là PASSED hoặc FAILED — **không** phải UNCONFIGURED;
* `pip install aisef` trong venv sạch → `setup` → `doctor` xanh.

---

## Đợt 5 — Cách ly & vòng đời thay đổi (8 ngày, sau phát hành)

| # | Việc | Cơ chế | Ước lượng |
|---|---|---|---|
| S1 | **Spike sandbox tiến trình agent** (D8) | Claude Code trong container: mount worktree + thư mục cấu hình đăng nhập chỉ-đọc, `--network` chỉ tới API, `--cap-drop=ALL`. Đo: có chạy được `-p`? độ trễ? OAuth còn hiệu lực? Kết quả quyết định có thành mặc định hay không — **không** hứa trước. | 2 ngày |
| S2 | **Tra cứu tài liệu theo yêu cầu** (luật 12) | `aisef doc <gói>` gọi context7 CLI hoặc cache cục bộ; prompt developer nhắc lệnh; evidence ghi `doc_lookup`. Không MCP thường trú. | 1,5 ngày |
| S3 | **Guard luật 6** | Chặn `STORY-\d+-\d+`/`EPIC-\d+` trong tệp nguồn ngoài `docs/`, `_bmad-output/`, tệp test. | 0,5 ngày |
| S4 | **Vòng đời thay đổi sau phát hành** | `aisef change FR-x "mô tả"`: đánh stale đúng tầng (PRD → xuống), sinh story delta có `covers=[FR-x]`, giữ story cũ `DONE`. Cascade stale đã có; thiếu đường vào có tên. | 2 ngày |
| S5 | **Chia `cli.py`** | Thuần cơ học: `cli/` với một tệp mỗi pha; không đổi hành vi; test CLI hiện có là lưới an toàn. | 1 ngày |
| S6 | **Kiểm nội dung skill ngoài theo tiêm prompt** | Quét 120 skill đã cài bằng chính `story-security-review` ở chế độ "tài liệu": dòng nào bảo agent bỏ qua luật, gọi mạng, đọc bí mật → chặn cài, ghi vào `catalog.json` `quarantine`. Chạy một lần mỗi commit ghim. | 1 ngày |

---

## Chi phí agent thật (ước)

| Việc | Lượt | Ước |
|---|---|---|
| G4 trước/sau | 2 story Claude | $4 |
| G6 hợp quy | 5 phép × 2 client, lặp 2 | $4 |
| G5 tuân thủ mã test | 2 story `par` | $4 |
| G12 di trú `par` | 1 lượt 2 client | $3 |
| R2 `e9` EPIC-01 + qa | 4 story + qa | $60–90 |
| R5 mốc `par` 2 client | 2 lượt | $6 |
| S1 spike sandbox | 3–5 lượt nhỏ | $5 |
| Dự phòng thử lại | | $30–60 |
| **Tổng** | | **$120–180** |

Chi phí là telemetry: không cắt lượt review, không hạ model reviewer để
tiết kiệm. Chỗ duy nhất được thử model rẻ là A/B trên security reviewer
và designer, **sau** khi có thước (đợt 3 cho bộ mẫu diff thật của e9).

---

## Quyết định của chủ đầu tư (chốt 2026-09-05)

1. **PyPI** — tên `aisef`; publish khi **hoàn tất đợt 4**, không public
   sớm hơn; tài khoản **tổ chức/team**, không dùng cá nhân nếu có lựa chọn.
   → R1 giữ `INSTALL_SPEC = "aisef"`; tới lúc publish CI của dự án đích
   dùng `--install-spec git+https://…@<tag>`.
2. **Ngân sách agent** — duyệt **$120–180** toàn kế hoạch. Không tự bó
   xuống nếu chất lượng cần thêm lượt review/test.
3. **OpenCode = hạng hai cho V1** — ghi rõ mức bảo đảm thấp hơn, **không
   chặn phát hành**. Nâng hạng nhất sau release khi `--format json` + hợp
   quy hook đủ chắc. Hệ quả trong kế hoạch:
   * G6: hợp quy OpenCode vẫn chạy nhưng là **thông tin**, không phải điều
     kiện phát hành; điều kiện phát hành chỉ đọc cột Claude của
     `CONFORMANCE.md`;
   * G11: `MACHINE_OUTPUT` của OpenCode hạ về `UNSUPPORTED` cho đúng sự
     thật tới khi `--format json` được chứng minh;
   * `compile --client opencode` in dòng "hạng hai V1: chi phí/lượt không
     đo được, không chặn phát hành" — SOLUTION §11 và README ghi cùng câu.
4. **Docker ở `pre-deploy`** — mặc định **không cho suy biến**. Chỉ cho
   phép khi có khai báo tường minh `sandbox.pre_deploy_degraded_waiver =
   "<lý do>"` và lý do được **ghi vào `pre-deploy.json`** (bằng chứng của
   cổng). `run` thường giữ `sandbox.allow_degraded = True`. → Đã cài
   cùng ngày, xem commit.

Thứ tự 5 đợt được duyệt nguyên: G4 + G11 sớm, rồi G6/G7/G5/G8.

## Đo tiến độ

Một bảng, cập nhật mỗi lần commit hạng mục, trong `EXECUTION-PLAN.md`:

| Hạng mục | Unit test | Kiểm thật | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| G1 G2 G3 | 21 | — (guard thuần) | commit `297282e` | ✅ |
| G4 | | `par` trước/sau | | |
| … | | | | |

Cột "Kiểm thật" là **bắt buộc điền** cho mọi hạng mục chạm client, cổng
hay bằng chứng — để trống thì hạng mục chưa xong, dù test xanh.
