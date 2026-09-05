# Changelog

Ghi theo **sáu nhóm harness** (`docs/SOLUTION.md` §5), không theo ADR hay
ngày. Mỗi dòng có chỗ đọc lại; số lỗi trỏ `docs/STATUS-2026-09-05.md` §2.4
và `docs/FAILURE-TAXONOMY.md`; số đo trỏ `docs/ADR-004-evidence-driven-epic-improvement.md` §6.

## v0.1.0 — chưa phát hành

Phiên bản trong `pyproject.toml` là `0.1.0`; chưa có bản nào trước nó. Mục
này ghi những gì đổi từ mốc `04eee9b` (đầu ngày 2026-09-05, trạng thái ở
`docs/STATUS-2026-09-05.md` §1) tới nay — hai ngày đo trên agent thật cộng
hai đợt ADR-004 (đêm 05→06/09). Nền có trước mốc ấy (sáu bước, tám cổng
người, worktree, guard, hợp quy) mô tả ở `docs/SOLUTION.md`; không lặp lại.

**Điều kiện phát hành** (`docs/STATUS-2026-09-05.md` §5, `docs/EXECUTION-PLAN.md` đợt 4 R1):
100 % unit xanh · `docs/CONFORMANCE.md` ≤ 14 ngày không ô ✗ · `par` chạy
lại đạt mốc dogfood · e9 EPIC-01 xong với báo cáo có tiêu chí → test id · `pip
install ai-sdlc` trong venv sạch → `setup` → `doctor` xanh. Tag `v0.1.0` chờ
chủ đầu tư tạo project PyPI + trusted publisher; wheel/sdist đã `twine check`.

### Khi nâng cấp — việc người dùng phải làm

- **`aisdlc compile` lại** trong mỗi dự án: guard thứ 8 `process-ref` và biến
  `AISDLC_PROJECT` (guard ưu tiên env, `--project` chỉ dự phòng — lỗi 6/P0-1)
  chỉ vào hook sau khi biên dịch lại; `aisdlc doctor` báo khi hook cũ thiếu
  guard hoặc trỏ sang dự án khác.
- **Duyệt lại `stories` và `readiness` một lần**: cách băm `stories.index.json`
  đổi (chuẩn hoá JSON, bỏ `STORY-RP-*`/`EPIC-RP-*`) nên phê duyệt đã ký trước
  bản này hiện `stale` ở `aisdlc gates` — đúng một lần, không phải lỗi (lỗi 25;
  `control/approvals.py::_artifact_hash`).
- **Xoá `story.max_context_tokens`** khỏi `.ai/config.json` — khoá đã gỡ, nạp
  vẫn được nhưng cảnh báo mỗi lần chạy (`config.RETIRED`). Khoá mới đều có
  mặc định, không cần thêm.
- **Lệnh test phải in tên test** (`vitest --reporter=verbose`, `pytest -v`,
  `node --test`): ba mục cổng `tiêu chí có test`, `bảo toàn`, `không làm đỏ
  test có sẵn` đọc tên từ output runner; không in thì ○ chưa cấu hình, không
  chặn story nhưng chặn `pre-deploy`, và sổ hành vi ghi GAP (e9 01-01/02/03:
  18 GAP cùng một lý do — ADR-004 §6 R2).
- **`verify.baseline` mặc định bật** → mỗi story chạy thêm **một** lần test
  trước phiên developer (không mỗi lượt). Bộ test chậm thì tắt; mục cổng thành
  – "tắt bởi cấu hình", không phải đạt.
- Nhật ký story cũ có bước `commit.created` vẫn đọc được (`Journal.needs_merge`);
  lượt đang dở lúc nâng cấp được `aisdlc run` hoà giải (`journal.reconcile_all`).
- Prompt lên version (`story-implement@6`, `story-review@5`,
  `story-security-review@3`): bằng chứng `agent_run` ghi version, so sánh chi
  phí giữa hai bản phải tách theo version.

### 1 · Instructions & rule files

- Prompt `story-implement` 3 → **6**: @4 mục "Trạng thái epic" (slot `index`,
  ADR-004 R6); @5 mục bảo toàn/kiểm định (R4); @6 "không đổi tiêu đề test có
  sẵn" — B1 cho thấy mỗi story sửa mất một lượt vì cổng R9 (ADR-004 §6 B1).
- Prompt `story-review` 3 → **5**, `story-security-review` 1 → **3**: đòi khối
  JSON `verdict` + `findings[behavior_id]` bên cạnh văn bản (R8); mục bảo toàn (R4).
- Hiến pháp: luật 6 — không mã `STORY-…`/`EPIC-…` trong mã nguồn (guard
  `process-ref` kiểm; `docs/ACTION-PLAN-2026-09-05.md` S3).
- `aisdlc skill --scan`: quét SKILL.md bằng phiên model **chỉ đọc, không tool**,
  8 skill/lô, JSON kiểm schema; `injection` → `rejected` sống qua `refresh`,
  `suspicious` → cảnh báo trong sổ. Đo e9: 153 skill, $5,01, 0 injection / 8
  suspicious có trích dẫn (STATUS §2.8).
- Knob mới `skills.inline` (`false`, thí nghiệm ADR-003 cơ chế B — n = 1 không
  thấy gain, giữ tắt). `skills.offer` giữ `false` sau A/B e9 `used` 0/0 (STATUS §2.6).

### 2 · Tools

- **Mới** `aisdlc doc <package> [--topic] [--story]`: tra tài liệu thư viện qua
  context7, cache trên đĩa, bằng chứng `doc_lookup` (ACTION-PLAN S2).
- **Mới** `aisdlc evidence <id>`: lịch sử một story hoặc một hành vi
  (`AC-…`, `FR-x`, `qa:<kind>`, `mockup:<màn>`), ghi `note:evidence_lookup`
  (ADR-004 R6).
- `run_tool` phân loại **không chạy được** (exit 127, MODULE_NOT_FOUND, không
  test nào xanh) tách khỏi đỏ → `detail.unrunnable`; guard `completion` cho
  dừng, cổng ghi ⚠ (lỗi 8). Trước đó 3 story `par` đốt $17 vì Stop bị chặn
  ~10 lần/lượt.
- **Mới** `tool_run test:baseline` (`tools.BASELINE_RUN`): harness chạy
  `tools.test` ở HEAD worktree **trước** phiên developer đầu tiên; ghi tên test,
  `red_before`, `parent`, không mang `candidate` (ADR-004 R9).
- `harness/testlog.py`: đọc tên test từ node `spec`/`tap`, vitest, pytest;
  `test_ids`/`failed_ids`/`skipped_ids`, coverage; cắt ở `MAX_IDS` = 500 và nói
  ra khi cắt.

### 3 · Sandboxes & execution environments

- Phiên con Claude **cách ly cấu hình máy**: `--permission-mode acceptEdits`,
  tool kê tường minh, `--setting-sources project,local`, `--strict-mcp-config`,
  `clean_env()` bỏ `CLAUDE_*` của phiên cha (lỗi 4, 11; hợp quy C3/C4).
- Cấu hình client harness chép vào worktree (`.claude/settings.json`,
  `.opencode`) và `_bmad-output/reviews/` là **harness-owned** — không tính là
  tệp story đổi (lỗi 1, 7; ADR-004 §6 R4).
- `WorktreeManager.create` kiểm `path/.git`; thư mục sót trong
  `.aisdlc/worktrees/` bị dọn + `worktree prune` rồi tạo thật (lỗi 13).
- `AppServer.start` từ chối cổng đã có người trả lời (nêu pid/cwd); `stop` giết
  cả nhóm tiến trình (`start_new_session` + `killpg`) (lỗi 15).
- Knob mới `sandbox.pre_deploy_degraded_waiver` (`""`): `pre-deploy` không
  nhận kiểm định ngoài Docker trừ khi có lý do khai; lý do vào `pre-deploy.json`
  (quyết định 4, STATUS §2.1). `sandbox.allow_degraded` (`true`) chỉ áp cho `run`.
- `AISDLC_PROJECT` truyền từ harness cho cả ba vai; guard đọc env trước (P0-1).

### 4 · Orchestration logic

- **Đổi hành vi — thứ tự nhật ký** (`control/journal.py::STEPS`, ADR-004 R1):
  `attempt.started → worktree.created → status.running → changes.detected →
  candidate.frozen → verification.completed → review.completed →
  merge.completed → attempt.committed`. `commit.created` **biến mất khỏi
  `STEPS`** (tên cũ vẫn đọc được); ứng viên được commit **ngay khi phiên
  developer kết thúc**, trước test/cổng/rà soát (`implement.freeze_candidate`;
  `--no-isolate` không commit). Reviewer/security bị so `git rev-parse HEAD` sau
  phiên; lệch → lượt không tính.
- **Mới** `aisdlc improve --epic E [--max-loops N] [--auto] [--client] [--force]`
  (`phases/improve.py`, ADR-004 R3): QA cấp dự án → sổ hành vi → **một** story
  sửa `STORY-RP-nn` trong `EPIC-RP-<E>` sinh bằng code → `run` (worktree, cổng,
  reviewer ≠ developer) → QA → mốc `loops[]` + `LOOP-REPORT-<n>.md`. Dừng bằng
  code: hết gap · đủ `improve.max_loops` · biên ≤ 0 `improve.flat_loops` vòng
  liền · vượt `improve.cost_cap_usd` · bế tắc kế hoạch. Không daemon: gọi lại
  chạy tiếp từ mốc cuối. B1 trên e9 EPIC-01: +1 verified/vòng, $8,5/vòng, 0
  hồi quy (ADR-004 §6 B1).
- **Mới cổng người `improve`** (`Gate.IMPROVE`): ngoài `GATE_ORDER`, artifact là
  glob `LOOP-REPORT-*.md` — duyệt **mỗi** vòng ≥ 2 trừ `--auto`; dự án chưa
  chạy `improve` không bị nó chặn `pre-deploy` (ADR-004 §6 R3).
- **Đổi hành vi — băm `stories.index.json`** (lỗi 25): chuẩn hoá JSON, bỏ
  story/epic sửa; phê duyệt `stories`/`readiness` cũ stale một lần.
- **Mới** `aisdlc change FR-x "mô tả"`: ghi FR, stale PRD trở xuống, sinh story
  delta `STORY-CH-nn` trong `EPIC-CH` (ACTION-PLAN S4).
- **Cổng cỡ story v2** (ADR-004 R5, `control/complexity.py`): điểm = trạng thái
  màn hình + tiêu chí + 0,5 × đường dẫn scope + fan-in (+ láng giềng VERIFIED
  ×0 tới khi hiệu chuẩn); knob `story.max_complexity` (`16.0`) và
  `story.max_screen_states` (`8`, P2-12; màn story khác đã dựng tính 1). Vượt →
  cổng `stories` chặn kèm gợi ý chẻ, `run` từ chối trước khi gọi model; story
  đã xong bỏ qua. `run` ghi `_bmad-output/complexity.json`, `doctor` cảnh báo
  ngưỡng lệch dữ liệu. Hồi cứu 23 story: Spearman 0,88 (ADR-004 §6 R5).
- **Slot bàn giao mới** (`implement.SLOT_SOURCE`, nguồn `ledger`): `index` (lát
  cắt chỉ mục epic, trần `context.max_index_chars` = 2000), `preservation`
  (hành vi VERIFIED của story khác bị chạm tệp: id · story · nguồn kiểm) và
  `validation` (thứ harness chạy lại ở ứng viên), trần
  `context.max_preservation_chars` = 1500 chỉ cắt phần in ra. Tính một lần
  trước phiên developer, ba vai nhận cùng bản. Prompt developer +13,2 % trên
  test giả, ≈ +4 % trên e9 (ADR-004 §6 R4/R6).
- **Rà soát trả JSON có schema** (ADR-004 R8): thiếu/sai → hỏi lại **đúng một
  lần** (`<story>-review-retry`), vẫn thiếu → đọc văn bản, note
  `review:no-schema`; JSON ↔ văn bản lệch → **hợp** hai nguồn, note
  `review:mismatch`. Agent thật: 6/6 phiên trả JSON ngay, 0 hỏi lại.
- Lời rà soát lưu nguyên văn `_bmad-output/reviews/<story>-<vai>-<lượt>.md`;
  mục `[chặn]`/`[bế tắc]` nhiều dòng không cụt (lỗi 16).
- Phạm vi ghi hiệu lực += thư mục test suy từ `verify.<kind>` của hợp đồng
  story (`verification_paths`) — hết cảnh "đòi e2e nhưng cấm ghi `tests/`" (lỗi 21).
- `sprint-status.attempts` = số lượt developer, không phải số lần `run` chạm
  story (P2-11).
- Cổng máy: mockup không đánh dấu `data-state`/`data-annotation` bị chặn kèm
  cách sửa (lỗi 12); parser PRD nhận tiêu đề khối tiêu chí Anh/Việt (lỗi 19);
  preflight chỉ coi đuôi tệp thật là đường dẫn (lỗi 20); mockup-map nói rõ
  route sẽ mở và bản ghi hạt giống `1` (lỗi 14).
- `pre-deploy`: story trong kế hoạch **chưa từng chạy** không phải "xong" (lỗi 17).
- Router: năng lực phải khai, không suy từ chữ (lỗi 5); `aisdlc skill --story S`
  in kết quả định tuyến.

### 5 · Guardrails / hooks

- **Guard thứ 8 `process-ref`** (`PreToolUse` · `Write|Edit`): mã story/epic
  trong mã nguồn; test và tài liệu được phép. Cần `aisdlc compile` lại.
- `completion` **cho dừng** khi test không chạy được hoặc chưa khai lệnh —
  kết cục ghi ở cổng, không chặn Stop vô hạn (lỗi 2, 8).
- Guard đọc cả `filePath`/`newString` (OpenCode) lẫn `file_path`/`content`
  (lỗi 10; hợp quy C7).
- **Cổng story thêm mục** (`control/gate.py`, bảng đủ ở SOLUTION §12):
  `bằng chứng đúng candidate` (⚠ stale khi phép kiểm mới nhất thuộc bản khác —
  R1, hợp quy C8), `không làm đỏ test có sẵn` (so tên test baseline ↔ ứng viên;
  đổi tên giữ tiêu đề lá không tính mất — R9, lỗi 24), `bảo toàn` (hành vi
  VERIFIED của story khác còn xanh ở ứng viên; FR hỏi story đã xác minh qua
  `via` — R4, lỗi 23), `tiêu chí có test` (G5), `coverage` (G10b), `TDD` (G8),
  `test thật`, `guard có chạy`; hợp đồng kiểm định đọc `qa:<kind>` trước tên
  trần (lỗi 9). Cổng ghi `gate:verdict` vào bằng chứng.
- Hợp quy client: phép **C6** (luật 6), **C7** (ghi ngoài scope), **C8** (ứng
  viên stale) — 16/16 hai client 2026-09-06 (`docs/CONFORMANCE.md`).

### 6 · Observability

- **Mới sổ hành vi** `control/ledger.py` (ADR-004 R2): phép chiếu từ
  `evidence/` — `AC-<story>-<i>` (tên test), `FR-x`/`NFR-x` (`covers`),
  `qa:<kind>`, `mockup:<màn>` → VERIFIED · GAP · REOPENED với `regressed_by`;
  chỉ ứng viên **đã landed** (nhật ký) mới VERIFIED, xanh ở ứng viên chưa
  landed đếm `unlanded_green`. `_bmad-output/ledger.json` (e9: 57 KB cho 4,3 MB
  bằng chứng), tách `reopen_events` khỏi `cross_reopens`. B0 trên e9: 6 hồi
  quy liên story mà báo cáo cũ không thấy.
- **Mới** `_bmad-output/INDEX.md` một dòng mỗi story/epic (R6); metrics ở phần 5
  `ACCEPTANCE-REPORT.md`: tăng trưởng VERIFIED, hồi quy, gap đã đóng, cải
  thiện biên/$ giữa hai mốc `loops[]` (R7); `LOOP-REPORT-<n>.md` mỗi vòng.
- Mọi bằng chứng sau đóng băng mang `detail.candidate` (đóng dấu một chỗ ở
  `EvidenceStore`); `Evidence.for_candidate(sha)`; QA cấp dự án ghi
  `candidate = HEAD`; báo cáo in cột SHA 7 ký tự (R1).
- Loại sự kiện mới `BEHAVIOR`; `HANDOFF` (có từ ADR-003) ghi thêm ba slot
  `ledger` và `prompt_chars` thay cho knob đã gỡ; note mới
  `review:verdict`/`security:verdict` (JSON), `gate:verdict`,
  `evidence_lookup`, `doc_lookup`.
- Báo cáo: ô Map mockup lấy kết quả **mới nhất** từng màn (lỗi 18); cột tiêu
  chí có test `n/n`; SHA ứng viên.
- OpenCode `--format json` → `MACHINE_OUTPUT`/`COST_REPORTING` NATIVE (vẫn hạng
  hai V1 — SOLUTION §11).
- Kho hồi quy chạy lại được từ kho: `tests/dogfood/` (`par`, mốc 3/3 lượt đầu,
  ≤ 2 × $3,14) và `tests/conformance/` (8 phép, hai client); release gate
  `AISDLC_RELEASE=1 tests.test_release_gate`.
- `aisdlc doctor`: hook trỏ đúng dự án, hook thiếu guard mới, ngưỡng cỡ story
  lệch dữ liệu, gợi ý lệnh test in coverage.

### Knob cấu hình mới (mặc định) — `aisdlc/config.py::DEFAULTS`, ý nghĩa ở SOLUTION §13

| Khoá | Mặc định | Từ |
|---|---|---|
| `story.max_screen_states` | `8` | P2-12 |
| `story.max_complexity` | `16.0` | ADR-004 R5 |
| `context.max_index_chars` | `2000` | ADR-004 R6 |
| `context.max_preservation_chars` | `1500` | ADR-004 R4 |
| `improve.max_loops` · `improve.flat_loops` · `improve.cost_cap_usd` | `3` · `2` · `0.0` | ADR-004 R3 |
| `verify.baseline` | `true` | ADR-004 R9 |
| `skills.inline` | `false` | ADR-003 §6 |
| `sandbox.pre_deploy_degraded_waiver` | `""` | quyết định 4 |

Gỡ: `story.max_context_tokens` (chưa từng có mã đọc; `RETIRED`, cảnh báo rồi bỏ qua).

### Lệnh CLI mới — `aisdlc/cli/parser.py`, bộ lệnh đủ ở SOLUTION §10

`aisdlc improve` · `aisdlc evidence` · `aisdlc doc` · `aisdlc change` ·
`aisdlc skill --scan` · `aisdlc guard process-ref`. Gói `aisdlc/cli/` tách từ
một tệp `cli.py` (S5), không đổi hành vi.

### Lỗi thật tìm bằng đo trong đợt này

25 lỗi, không lỗi nào bằng đọc code; bảng và lớp nguyên nhân ở
`docs/FAILURE-TAXONOMY.md`, chi tiết ở STATUS §2.4. Chưa sửa: lỗi 22 (e2e nhạy
tải máy — cần R13 `run --story S --verify-only`, STATUS P1-13).
