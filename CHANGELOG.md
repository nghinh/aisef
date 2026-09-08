# Changelog — AISEF (AI Software Engineering Framework)

Ghi theo **sáu nhóm harness** (`docs/SOLUTION.md` §5), không theo ADR hay
ngày. Mỗi dòng có chỗ đọc lại; số lỗi trỏ `docs/STATUS-2026-09-05.md` §2.4
và `docs/FAILURE-TAXONOMY.md`; số đo trỏ `docs/ADR-004-evidence-driven-epic-improvement.md` §6.

## v0.6.0 — phát hành 2026-09-08

### Quan sát (nhóm 2 — observation)

- **SKILL_USE event**: ghi sự kiện `skill_use` mỗi khi agent gọi skill
  trong phiên developer hoặc reviewer/security. `aisef status` hiển thị
  tổng hợp số lần dùng từng skill.

### Tài liệu (nhóm 6 — docs)

- **v1.0.0 readiness checklist**: `docs/V1-READINESS.md` — 10 điều kiện
  tự động DONE, 4 điều kiện cần agent run thật (BLOCKED).
- **README**: cập nhật từ 8 lên 9 guard (thêm `egress`).
- **SOLUTION.md**: cập nhật §2.2 và §11 — OpenCode `--format json` đã
  chứng minh, chi phí/lượt đo được từ `step_finish`.

## v0.5.1 — phát hành 2026-09-08

### Tài liệu (nhóm 6 — docs)

- **English usage guide**: `docs/USAGE-GUIDE.md` — 927-line translation of
  `docs/HUONG-DAN-SU-DUNG.md`. README now links both versions.
- **API stability contract**: `docs/STABILITY.md` — documents frozen surface
  (CLI commands, 57 config keys, 9 guards, gate lifecycle, evidence format,
  state file, exit codes) and internal-only components for v1.0.0.

### Kiểm thử (nhóm 3 — verification)

- **105 test mới cho 9 module chưa có test**:
  - `test_skills.py` (21): parse_frontmatter, Skill.verb, load_skill, scan
  - `test_client_base.py` (19): Support.blocks_at_source, child_env
    allowlist, RunSpec defaults, ClientAdapter utilities
  - `test_client_adapters.py` (28): ClaudeCodeAdapter.build_command (11
    biến thể), OpenCodeAdapter.build_command, parse_json_events (8 ca)
  - `test_browser.py` (14): RenderedScreen/RenderResult dataclass,
    concrete_route, availability
  - `test_parser.py` (9): build_parser, subcommand parsing, guard name
    validation
  - `test_doctor.py` (6): _hook_paths_elsewhere
  - `test_design_contract.py` (8): ScreenContract round-trip, DesignContract
    lookup/write/load
- **Tổng**: 1904 test, tăng từ 1799 (v0.5.0). Toàn bộ xanh.

## v0.5.0 — phát hành 2026-09-08

### Bảo mật (nhóm 1 — kiểm soát)

- **Distributed story claim**: `StateStore.claim()` atomic compare-and-swap
  chuyển story PENDING → RUNNING + `claimed_by` dưới `fcntl.flock`. Nhiều máy
  dùng chung `sprint-status.json` (NFS) không tranh nhau story.
  `reset_for_retry()` và `release()` xoá claim. `machine_id()` =
  `hostname:pid`. 7 test.
- **Merge lock**: `WorktreeManager._merge_lock()` — `fcntl.flock` trên
  `.aisef/merge.lock` bảo đảm chỉ một máy merge vào nhánh chính cùng lúc.
  Timeout 120s.

### Điều phối (nhóm 2 — orchestration)

- **Model routing hoàn chỉnh**: thêm `route.security_model` config key — bốn
  vai (developer/reviewer/designer/security) đều có model riêng. `agent_run`
  evidence ghi `role` và `model` vào detail.

### Quan sát (nhóm 4 — observability)

- **Cost by role**: dashboard hiển thị bảng chi phí theo vai và model —
  `_role_cost()` trích từ `AGENT_RUN` events. 2 test.

### Đã biết — chưa giải quyết

- **S1 credential isolation**: blocked — chưa có cách ly credential trong
  container mà không làm yếu sandbox. Đợi upstream Docker/Buildah hỗ trợ.
- **OpenCode first-class**: second-class cho V1 — chưa đạt hợp quy 12/12.

## v0.4.1 — phát hành 2026-09-08

### Bảo mật (nhóm 1 — kiểm soát)

- **Egress guard** (ADR-005 V12): `check_egress()` trích host từ URL trong
  tool input (WebFetch URL, Bash curl/wget/pip/npm), đối chiếu
  `sandbox.allow_hosts` (wildcard `*.example.com`). Rỗng = không kiểm. Env
  `AISEF_ALLOW_HOSTS` truyền vào session. 10 test.

### Điều phối (nhóm 2 — orchestration)

- **Multi-epic state**: `SprintState.active_epics` theo dõi nhiều epic chạy
  song song trong cùng dự án. `finish_epic()` gỡ epic khỏi danh sách active
  và fallback `current_epic`. `of_epic()` / `by_status(epic=)` lọc story theo
  epic. `aisef status` hiển thị các epic đang hoạt động. Tương thích ngược —
  state.json cũ thiếu `active_epics` tải bình thường.
- **Crash recovery tests**: 2 test xác nhận `reconcile_all()` giữ nguyên
  evidence và candidate SHA khi story bị crash giữa chừng.

### Quan sát (nhóm 4 — observability)

- **Multi-project dashboard**: `aisef dashboard --projects ../proj-b ../proj-c`
  gộp bằng chứng nhiều dự án vào một báo cáo. Bảng tổng hợp hiển thị story
  count, chi phí, guard check/block theo từng dự án. 5 test.

### CLI (nhóm 5 — trải nghiệm)

- **`aisef init --stack`**: preset cho react/python/go/node — test, lint,
  sandbox image, allow_hosts cấu hình sẵn. `Config.overlay()` merge preset
  lên config hiện tại. 2 test.
- **Config keys tối giản**: zero mandatory config keys — tất cả đều có default.
  Không cần khai báo gì để chạy `aisef run`.

## v0.4.0 — phát hành 2026-09-08

### Quan sát (nhóm 4 — observability)

- **Guard telemetry**: mỗi lần guard chạy ghi sự kiện `GUARD_CHECK` vào
  evidence JSONL — kind, tool, verdict (allow/block), latency (ms). Dashboard
  và phân tích hậu kỳ có dữ liệu từ mọi guard invocation, không chỉ block.
- **`aisef dashboard`**: báo cáo hợp quy HTML tự chứa — tỉ lệ hit/pass/block
  theo guard, gate verdicts, chi phí và thời lượng từng story. Xem offline,
  không phụ thuộc dịch vụ ngoài.

### CLI (nhóm 5 — trải nghiệm)

- **`aisef replay`**: lối vào nhanh cho `gate --replay` — cùng logic chấm lại
  cổng story trên bằng chứng đã ghi (ADR-005 V4), ít gõ hơn.
- **Structured guard error**: guard chặn giờ xuất JSON trên stdout
  (`{"guard", "allowed", "reason", "tool"}`) bên cạnh lý do người đọc trên
  stderr — client có thể parse programmatically.

## v0.3.1 — phát hành 2026-09-08

### Bảo mật (nhóm 1 — kiểm soát)

- **Vá shell injection** trong `context._run_provider` và `impact._run_command`:
  `shlex.split()` + `shell=False` thay `shell=True` với chuỗi lệnh từ cấu hình.
- **Vá command injection** trong `compile._guard_command`: `shlex.quote()` cho
  đường dẫn dự án (khoảng trắng, nháy đơn, ký tự đặc biệt shell).
- Thêm `.env` / `.env.*` vào `.gitignore`.
- **Regression test**: 6 test mới kiểm trực tiếp các fix trên (edge case:
  dấu cách, nháy, `$(...)` trong đường dẫn).

### Hiệu năng (nhóm 4 — quan sát)

- `observe._next_seq` đổi từ O(n) quét toàn file sang O(1) đọc cuối file —
  giảm thời gian ghi bằng chứng trên file lớn (e9: 4,3 MB).

### Đóng gói / CLI (nhóm 5 — trải nghiệm)

- `python -m aisef` hoạt động (thêm `aisef/__main__.py`).
- `README.vi.md`: sửa mô tả bí danh `aisdlc` (đã gỡ, không còn chạy).
- CI: thêm Python 3.14 vào ma trận test.
- `state._migrate_done_before_merge`: ghi nguyên tử (tmp+replace).

### Đo lường (nhóm 6)

- Benchmark v0.3.0 giữ nguyên làm evidence nền — methodology, dataset, scorer
  không đổi; không rerun.

## v0.3.0 — phát hành 2026-09-07

**Đã phát hành:** tag `v0.3.0` = `5dadc1e`, gói `aisef 0.3.0` trên PyPI.
Kiểm sau publish: venv sạch `pip install aisef==0.3.0` → `aisef --help` →
`aisef doctor` → `aisef setup` **✅**.

### Benchmark (nhóm 6 — đo lường)

- **Hạ tầng benchmark ADR-005 V8**: 16 bug-fix task từ kho, interleaved
  runner (`run-both --shuffle`), bare control mode, scorer chấm F2P/P2P
  theo tên test, Harbor export.
- **96-session benchmark** (16 task × 2 condition × 3 attempt): 100% pass@1
  cả AISEF và bare, 12 guard block, chi phí $147.89 tổng, overhead 7%.
- **Phân tích guard block**: 6 process-ref, 3 destructive, 3 completion —
  guard bắt lỗi vệ sinh thật (mã quy trình trong nguồn, xoá đệ quy, bỏ
  qua test) nhưng không thay đổi kết cục đúng sai trên tập task này.
- Giao thức đóng băng trước khi chạy (SHA `dbd3858`).
- Báo cáo: `docs/BENCH-REPORT-v0.3.0.md`.

### Guard / harness (nhóm 1 — kiểm soát)

- **Hợp quy C1-C10** đạt cả Claude và OpenCode (`docs/CONFORMANCE.md`).
- Sửa timeout runner: `Popen` + `communicate(timeout=)` thay
  `subprocess.run` — phiên hết giờ nay giữ được dữ liệu chi phí/lượt.

### Skill / kit (nhóm 3 — kỹ năng)

- **Skill scanning by agent** (`aisef skill --scan`): quét lô SKILL.md bằng
  model chỉ đọc, phát hiện injection, ghi bằng chứng, sổ đăng ký loại skill.
- **Sổ skill + router** (ADR-002): registry 5 trạng thái, router tất định +
  luật hai-tín-hiệu + abstain, đo trên e9 (156 skill, abstain 13/18).

### CLI / packaging (nhóm 5 — trải nghiệm)

- Gỡ bí danh CLI `aisdlc` (deprecated từ 0.2.0).
- Thêm `[project.urls]` Homepage/Repository vào pyproject.toml.
- Homepage: https://aisef.io/

## v0.2.0 — phát hành 2026-09-06

**Đã phát hành:** tag `v0.2.0` = `7eac114`, gói `aisef 0.2.0` trên PyPI (kho
GitHub nay là `nghinh/aisef`, trusted publisher khai lại theo tên mới). Kiểm sau
publish: venv sạch `pip install aisef==0.2.0` → lệnh `aisef` (và bí danh `aisdlc`
có cảnh báo) → `setup` → `compile` → hook chặn đúng (thoát 2) và cho qua đúng
(thoát 0) → `doctor` **✅ sẵn sàng**.

**Đổi tên: gói, module và lệnh cùng là `aisef`.** 0.1.0 cài bằng `pip install
aisef` nhưng gõ `aisdlc` — hai tên cho một thứ, phải giải thích ở mọi trang tài
liệu. Từ bản này chỉ còn một tên.

| Cũ (0.1.0) | Mới (0.2.0) |
|---|---|
| lệnh `aisdlc` | lệnh **`aisef`** (bí danh `aisdlc` còn chạy, in cảnh báo, gỡ ở 0.3.0) |
| module `aisdlc/` | `aisef/` |
| biến môi trường `AISDLC_*` | `AISEF_*` (`AISEF_TEST_DOCKER`, `AISEF_RELEASE`, `AISEF_CONFORMANCE`, `AISEF_STORY_ID`, `AISEF_PROJECT`, …) |
| cache `~/.cache/ai-sdlc/{references,docs}` | `~/.cache/aisef/{references,docs}` |
| worktree `.aisdlc/worktrees/` | `.aisef/worktrees/` |
| dấu skill `.aisdlc-managed` | `.aisef-managed` (dấu cũ **vẫn được đọc**) |
| thẻ meta mockup `aisdlc-screen`/`aisdlc-route` | `aisef-screen`/`aisef-route` (thẻ cũ **vẫn đọc được**) |
| quy trình CI sinh ra `.github/workflows/aisdlc.yml` | `aisef.yml` |

Kho GitHub cũng đã đổi tên thành **`nghinh/aisef`** (2026-09-06); tag `v0.1.0`,
lịch sử CI và URL cũ (GitHub tự chuyển hướng) đều còn. **Việc phải làm tay một
lần:** trên PyPI, sửa trusted publisher của project `aisef` sang repository
`aisef` — publisher khớp theo đúng chuỗi `chủ/tên kho` lấy từ token OIDC, giữ
tên cũ thì lần publish sau bị từ chối. Workflow `release.yml` và environment
`pypi` không đổi.

Hai chỗ **giữ nguyên** có lý do: task benchmark trong `tests/bench/tasks/`
(patch áp vào commit **trước** lần đổi tên nên phải giữ đường dẫn cũ;
`_mine.SRC_PREFIXES` nhận cả hai) và fixture ghi lại phiên agent thật trong
`tests/fixtures/`.

### Khi nâng cấp lên 0.2.0 — việc phải làm

- **`aisef compile` trong từng dự án**: hook cũ gọi lệnh `aisdlc` và đặt biến
  `AISDLC_*`. Bí danh giữ cho hook cũ chạy tới 0.3.0, nhưng đừng dựa vào nó.
- **Đổi biến môi trường trong script/CI của bạn**: `AISDLC_*` → `AISEF_*`. Tên
  cũ **không** còn được đọc.
- **Kho skill tham chiếu tải lại một lần** vì cache đổi chỗ
  (`~/.cache/aisef/references`); muốn dùng lại bản cũ thì `mv ~/.cache/ai-sdlc
  ~/.cache/aisef`.
- **Worktree đang dở của bản cũ** nằm ở `.aisdlc/worktrees/`: chạy `git worktree
  prune` rồi xoá thư mục ấy sau khi story đang chạy kết thúc.

### Sửa lỗi

- **Hook của bản cài từ wheel không chạy guard nào** (lỗi 31, đo trên venv sạch
  2026-09-06): `aisef_command()` lùi về `<site-packages>/bin/aisef` — đường dẫn
  chỉ tồn tại trong kho nguồn — nên `aisef compile` ghi vào hook một lệnh không
  có thật và mọi guard im lặng không chạy. Nay kiểm tồn tại rồi mới trả, không
  có thì dùng `<python đang chạy> -m aisef.cli`. Ba phép kiểm mới trong
  `tests/test_tools.py::TestLenhGoiFramework`.

## v0.1.0 — phát hành 2026-09-06

**Đã phát hành:** tag `v0.1.0` = `a083a49`, gói `aisef 0.1.0` trên PyPI (wheel +
sdist, trusted publishing từ `release.yml`, không token trong kho). Kiểm sau
publish: `pip install aisef==0.1.0` trong venv sạch → `aisef setup` (152 skill)
→ `aisef doctor` **✅ sẵn sàng**. Điều kiện phát hành và giới hạn đã biết:
`docs/RELEASE-CHECKLIST-v0.1.0.md`.

Phiên bản trong `pyproject.toml` là `0.1.0`; chưa có bản nào trước nó. Mục
này ghi những gì đổi từ mốc `04eee9b` (đầu ngày 2026-09-05, trạng thái ở
`docs/STATUS-2026-09-05.md` §1) tới nay — hai ngày đo trên agent thật cộng
hai đợt ADR-004 (đêm 05→06/09). Nền có trước mốc ấy (sáu bước, tám cổng
người, worktree, guard, hợp quy) mô tả ở `docs/SOLUTION.md`; không lặp lại.

**Điều kiện phát hành** (`docs/STATUS-2026-09-05.md` §5, `docs/EXECUTION-PLAN.md` đợt 4 R1):
100 % unit xanh · `docs/CONFORMANCE.md` ≤ 14 ngày không ô ✗ · `par` chạy
lại đạt mốc dogfood · e9 EPIC-01 xong với báo cáo có tiêu chí → test id · `pip
install aisef` trong venv sạch → `setup` → `doctor` xanh. Tag `v0.1.0` chờ
chủ đầu tư tạo project PyPI + trusted publisher; wheel/sdist đã `twine check`.

### Khi nâng cấp — việc người dùng phải làm

- **`aisef compile` lại** trong mỗi dự án: guard thứ 8 `process-ref` và biến
  `AISEF_PROJECT` (guard ưu tiên env, `--project` chỉ dự phòng — lỗi 6/P0-1)
  chỉ vào hook sau khi biên dịch lại; `aisef doctor` báo khi hook cũ thiếu
  guard hoặc trỏ sang dự án khác.
- **Duyệt lại `stories` và `readiness` một lần**: cách băm `stories.index.json`
  đổi (chuẩn hoá JSON, bỏ `STORY-RP-*`/`EPIC-RP-*` ở `stories`/`epics` **và
  `waves`**) nên phê duyệt đã ký trước bản này hiện `stale` ở `aisef gates` —
  đúng một lần, không phải lỗi (lỗi 25/28; `control/approvals.py::_artifact_hash`).
- **`verify.waived` khác rỗng thì phải có `verify.waiver_reason`** (phạm vi,
  ngày, người ký): `aisef pre-deploy` nay chặn mục "miễn tường minh" khi miễn
  không lý do; loại miễn hiện ◇, không ✅ (QĐ5 2026-09-06). Dự án chỉ nghiệm thu
  một epic: `aisef pre-deploy --epic E` rồi `aisef approve pre-deploy` — phê
  duyệt gắn với phạm vi khai.
- **Xoá `story.max_context_tokens`** khỏi `.ai/config.json` — khoá đã gỡ, nạp
  vẫn được nhưng cảnh báo mỗi lần chạy (`config.RETIRED`). Khoá mới đều có
  mặc định, không cần thêm.
- **Tiến trình client chỉ nhận allowlist biến môi trường** (ADR-005 V2):
  provider của OpenCode đọc khoá từ biến riêng (không phải `auth.json`), hay
  CI xác thực Claude bằng `CLAUDE_CODE_OAUTH_TOKEN`, thì khai tiền tố/tên vào
  `clients.env_allow` — không khai thì phiên agent không thấy biến ấy và client
  báo thiếu xác thực. `9router/mycombo` trên máy đo không cần khai gì. Agent
  cũng **không còn** `git push`/đổi remote/hỏi credential được — push là việc
  của harness sau cổng; story cũ có bước push trong prompt riêng thì bỏ.
- **Lệnh test phải in tên test** (`vitest --reporter=verbose`, `pytest -v`,
  `node --test`): ba mục cổng `tiêu chí có test`, `bảo toàn`, `không làm đỏ
  test có sẵn` đọc tên từ output runner; không in thì ○ chưa cấu hình, không
  chặn story nhưng chặn `pre-deploy`, và sổ hành vi ghi GAP (e9 01-01/02/03:
  18 GAP cùng một lý do — ADR-004 §6 R2).
- **`verify.baseline` mặc định bật** → mỗi story chạy thêm **một** lần test
  trước phiên developer (không mỗi lượt). Bộ test chậm thì tắt; mục cổng thành
  – "tắt bởi cấu hình", không phải đạt.
- Nhật ký story cũ có bước `commit.created` vẫn đọc được (`Journal.needs_merge`);
  lượt đang dở lúc nâng cấp được `aisef run` hoà giải (`journal.reconcile_all`).
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
- `aisef skill --scan`: quét SKILL.md bằng phiên model **chỉ đọc, không tool**,
  8 skill/lô, JSON kiểm schema; `injection` → `rejected` sống qua `refresh`,
  `suspicious` → cảnh báo trong sổ. Đo e9: 153 skill, $5,01, 0 injection / 8
  suspicious có trích dẫn (STATUS §2.8).
- Knob mới `skills.inline` (`false`, thí nghiệm ADR-003 cơ chế B — n = 1 không
  thấy gain, giữ tắt). `skills.offer` giữ `false` sau A/B e9 `used` 0/0 (STATUS §2.6).

### 2 · Tools

- `aisef tool` có cấu trúc (ADR-005 V11 A): tóm tắt `testlog` (xanh/đỏ/bỏ qua,
  ≤ 20 tên test đỏ) **trước** `tail`, rồi "(lược N/M dòng — toàn văn:
  `_bmad-output/evidence/<story>-<tool>-<seq>.log`)" khi output dài hơn
  `--lines`; `record()` ghi tệp log ấy khi output > 20 dòng, `tail` trong
  evidence vẫn 20 dòng.
- Che bí mật trong bằng chứng (ADR-005 V1): `tail`, log toàn văn và `qa:*`
  đi qua `guardrails.scrub_secrets` → `[REDACTED]`, `detail.redacted` = số chỗ
  che; thêm mẫu `AWS_SECRET_ACCESS_KEY=…` và `Bearer …`. Đo trước trên 42 tệp
  evidence e9/`par`: 0 khớp — vá phòng ngừa, `_bmad-output` được commit.
- **Mới** `aisef doc <package> [--topic] [--story]`: tra tài liệu thư viện qua
  context7, cache trên đĩa, bằng chứng `doc_lookup` (ACTION-PLAN S2).
- **Mới** `aisef evidence <id>`: lịch sử một story hoặc một hành vi
  (`AC-…`, `FR-x`, `qa:<kind>`, `mockup:<màn>`), ghi `note:evidence_lookup`
  (ADR-004 R6).
- `run_tool` phân loại **không chạy được** (exit 127, MODULE_NOT_FOUND, không
  test nào xanh) tách khỏi đỏ → `detail.unrunnable`; guard `completion` cho
  dừng, cổng ghi ⚠ (lỗi 8). Trước đó 3 story `par` đốt $17 vì Stop bị chặn
  ~10 lần/lượt.
- **Mới** `tool_run test:baseline` (`tools.BASELINE_RUN`): harness chạy
  `tools.test` ở HEAD worktree **trước** phiên developer đầu tiên; ghi tên test,
  `red_before`, `parent`, không mang `candidate` (ADR-004 R9).
- `harness/testlog.py`: đọc tên test từ node `spec`/`tap`, vitest, pytest,
  `python -m unittest -v` (bench V8 chấm task lỗi kho theo tên);
  `test_ids`/`failed_ids`/`skipped_ids`, coverage; cắt ở `MAX_IDS` = 500 và nói
  ra khi cắt.
- `harness/testlog.py` đọc **CTRF** (ctrf.io JSON — pytest-json-ctrf,
  vitest-ctrf-json-reporter, jest/playwright…): khối `{"results":{"tests":[…]}}`
  ở bất kỳ đâu trong output (`pytest --ctrf=/dev/stdout`), id ghép
  `file > suite > tên` khi reporter tách; pending/other tính là bỏ qua. Hai
  fixture thật ở `tests/fixtures/testlog/ctrf-*.json`. `aisef doctor` mục
  "lệnh test in tên test": tin bằng chứng (`test_format` lần test gần nhất),
  chưa có thì đoán từ cờ lệnh; gợi `-v`/`--reporter=verbose`/CTRF (ADR-005 V9).

### 3 · Sandboxes & execution environments

- Phiên con Claude **cách ly cấu hình máy**: `--permission-mode acceptEdits`,
  tool kê tường minh, `--setting-sources project,local`, `--strict-mcp-config`
  (lỗi 4, 11; hợp quy C3/C4).
- **Môi trường tiến trình client là allowlist** (`clients/base.py::child_env`,
  ADR-005 V2) cho cả Claude lẫn OpenCode — trước đó OpenCode nhận trọn
  `os.environ` (63 biến trên máy đo) và Claude chỉ bị bỏ `CLAUDE*`. Giữ
  `PATH HOME LANG LC_* TERM TMPDIR SHELL USER LOGNAME SSL_CERT_FILE` +
  `ANTHROPIC_*` + `AISEF_*` + `clients.env_allow`; kèm bộ vô hiệu credential
  git (`GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/usr/bin/false`,
  `GIT_CONFIG_COUNT=1` xoá `credential.helper`) — osxkeychain không được hỏi
  trong phiên agent; git của harness (`worktree.merge_story`) không nhận bộ này.
  Hợp quy **C9** (canary ngoài allowlist vắng trong bản ghi phiên, log OpenCode
  0 khớp) và **C10** (`git push` bị guard chặn; remote giả đòi auth không nhận
  `Authorization`) — `docs/CONFORMANCE.md`, ADR-005 §9 V2.
- Cấu hình client harness chép vào worktree (`.claude/settings.json`,
  `.opencode`) và `_bmad-output/reviews/` là **harness-owned** — không tính là
  tệp story đổi (lỗi 1, 7; ADR-004 §6 R4).
- `WorktreeManager.create` kiểm `path/.git`; thư mục sót trong
  `.aisef/worktrees/` bị dọn + `worktree prune` rồi tạo thật (lỗi 13).
- `AppServer.start` từ chối cổng đã có người trả lời (nêu pid/cwd); `stop` giết
  cả nhóm tiến trình (`start_new_session` + `killpg`) (lỗi 15).
- Knob mới `sandbox.pre_deploy_degraded_waiver` (`""`): `pre-deploy` không
  nhận kiểm định ngoài Docker trừ khi có lý do khai; lý do vào `pre-deploy.json`
  (quyết định 4, STATUS §2.1). `sandbox.allow_degraded` (`true`) chỉ áp cho `run`.
- **`ExecutionProvider` + `Guarantee`** (ADR-005 V5, `harness/sandbox.py`): bậc quyền
  khai **cần** (`Level.requires()`), provider khai **có** (`guarantees(level)` →
  `Support`); thiếu → `degraded` kèm **tên bảo đảm thiếu** (`SandboxResult.missing`
  vào evidence, cột "cách ly" của `pre-deploy`, `doctor`); `allow_degraded=False`
  từ chối lúc chọn provider, lệnh chưa chạy. Provider: `docker` · `local` · `fake`
  (test `qa`/`tools` không Docker) · `"mô-đun:Lớp"` qua knob `sandbox.provider`.
  `provider_error` tách lỗi hạ tầng (docker thoát 125: daemon, kéo image) khỏi lệnh
  đỏ → tool báo "không chạy được". `docs/SANDBOX-CONFORMANCE.md` S1–S5 chạy thật,
  mỗi provider một cột (`python3 -m tests.sandbox_conformance`). Sửa hai lỗi:
  `_run_degraded` mất PATH khi `env` khác rỗng (ADR-005 §9); timeout Docker giết
  CLI mà container `sleep` chạy tiếp (S5 lộ) — nay `docker rm -f` theo tên.
- `AISEF_PROJECT` truyền từ harness cho cả ba vai; guard đọc env trước (P0-1).
- **Kiểm định cấp dự án chạy ở worktree sạch từ SHA** (ADR-005 V6, theo
  Harbor): `qa.run_suite(clean=True)` — `aisef qa`, `pre-deploy`, `improve`
  chạy lệnh trong `git worktree` tách tạm dựng từ SHA đang chấm
  (`WorktreeManager.temporary`), `node_modules`/`.venv` của dự án gắn vào
  (`SandboxSpec.mounts`: Docker bind mount, suy biến symlink), gỡ sau. Shim
  `node_modules/.bin/*`, `conftest.py`, `pytest.ini` chưa commit không tới cây
  kiểm. Bằng chứng `qa:<kind>` và `pre-deploy.json` ghi `tree`
  (`worktree-tạm` | `cây agent` + lý do) và `clean_tree`. Knob
  `verify.clean_tree` (`true`) tắt khi test cần tệp không theo dõi. Mức story
  giữ cây worktree (`clean=False`).
- **Tests — suite đơn vị không mở container** (kế hoạch phát hành A2):
  `HostProvider` (`harness/sandbox.py`, chỉ cho test: chạy thật trên máy, khai
  NATIVE) được `tests/__init__.py` đặt vào chỗ `docker` khi không có
  `AISEF_TEST_DOCKER=1`; module chạm sandbox `import tests`. Đo tuần tự trên
  máy đo (load 4–7): 8 module 2 536 s → 106 s (`test_implement` 1 213 → 19 s,
  `test_run` 1 088 → 58 s, `test_tools` 77 → 0 s); suite đầy đủ 1 668 test
  167 s. Docker thật ở test đánh dấu `needs_docker` (`test_sandbox
  TestIsolation` 8, `test_tools TestRunToolQuaDockerThat` 2) + hợp quy S1–S5;
  `sandbox.provider = "host"`/`"fake"` trong dự án bị từ chối. Số test không giảm.

### 4 · Orchestration logic

- **`aisef run --story S --verify-only --repeat K`** (ADR-004 R13 + ADR-005
  §3, lỗi 22): mỗi phép kiểm chạy lại chạy K lần trên cùng SHA
  (`implement._repeat_runs`/`_repeat_note`); `note verify-only.repeat
  {flaky_ids, stable_red, flaky_checks}`; cổng ghi ⚠ UNRUNNABLE "không ổn
  định: <tên>" thay vì ✗ khi test đổi kết cục giữa các lần
  (`gate._khong_on_dinh`), đỏ mọi lần vẫn ✗. K = 1 là hành vi cũ.

- **`aisef pre-deploy --epic E`** (QĐ C-a 2026-09-06, `phases/deploy.py::_scope`):
  cổng **scope-aware, không nới** — chỉ chấm "mọi story xong" trên story của
  epic khai; story ngoài phạm vi thành mục "ngoài phạm vi nghiệm thu"
  (– NOT_APPLICABLE, nêu tên: không xong, không thiếu); phạm vi ghi vào
  `pre-deploy-report.json` (`scope{epic, stories, outside}`) nên băm phê duyệt
  `pre-deploy` đổi theo phạm vi; `aisef report` in phạm vi ở §6. v0.1.0 nghiệm
  thu e9 **EPIC-01** bằng cách này; EPIC-02..05 chưa nghiệm thu.

- **Vòng improve — hàng đợi sửa tự động** (QĐ B6 2026-09-06,
  `phases/improve.py::repair_queue`): `qa:*` cấp dự án **đứng ngoài** hàng đợi
  (đo B1 e9: vòng 4–5 nhận `qa:*`, Δ −1/−2); thứ tự REOPENED → `ac` → `fr`/`nfr`
  → `mockup`; lý do dừng nêu gap ngoài hàng đợi thay vì "hết gap". Story sửa
  phải viết **test mới mang mã** (đối chứng nop V3 chấm ✗ khi gắn mã vào test
  có sẵn); gap chỉ thiếu truy vết thì **không** thành story sửa — người rà soát
  trả `[bế tắc] truy vết: <test id>`, báo cáo vòng chỉ sang `aisef evidence
  --link` (sửa siêu dữ liệu, không giả thành cải tiến chức năng).

- **Đổi hành vi — thứ tự nhật ký** (`control/journal.py::STEPS`, ADR-004 R1):
  `attempt.started → worktree.created → status.running → changes.detected →
  candidate.frozen → verification.completed → review.completed →
  merge.completed → attempt.committed`. `commit.created` **biến mất khỏi
  `STEPS`** (tên cũ vẫn đọc được); ứng viên được commit **ngay khi phiên
  developer kết thúc**, trước test/cổng/rà soát (`implement.freeze_candidate`;
  `--no-isolate` không commit). Reviewer/security bị so `git rev-parse HEAD` sau
  phiên; lệch → lượt không tính.
- **Mới** `aisef improve --epic E [--max-loops N] [--auto] [--client] [--force]`
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
- **Nop control** (ADR-005 V3, `implement.run_nop`, gọi từ `verify_candidate`
  ngay sau đóng băng): worktree tạm ở SHA cha (điểm rẽ) + chép tệp test story
  thêm/sửa → `tools.test` ghi `test:nop` mang `candidate`; `--verify-only` giữ
  khi đã có kết quả ở SHA. `run_baseline` ghi thêm `base_ref` để cổng biết
  baseline của lượt chạy lại đứng ở bản của chính story.
- **Đầu vào cổng vào bằng chứng** (ADR-005 V4): `note gate:input` = 13 kwargs
  của `gate.evaluate` ngay trước `gate:verdict`; `aisef gate --replay` chấm lại
  lượt cũ bằng luật hiện tại, không gọi model (`control/replay.py`).
- **Đổi hành vi — băm `stories.index.json`** (lỗi 25): chuẩn hoá JSON, bỏ
  story/epic sửa; phê duyệt `stories`/`readiness` cũ stale một lần.
- **Mới** `aisef change FR-x "mô tả"`: ghi FR, stale PRD trở xuống, sinh story
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
  `context.max_preservation_chars` = 1 200 chỉ cắt phần in ra. Tính một lần
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
- Router: năng lực phải khai, không suy từ chữ (lỗi 5); `aisef skill --story S`
  in kết quả định tuyến.

- **Mới slot `repo_map`** (ADR-005 V7, `harness/context.py`, nguồn `code`, cả
  ba vai): bản đồ mã quanh phạm vi ghi bằng stdlib — skeleton tệp trong phạm vi
  (Python `ast`; TS/JS chữ ký, thân → `…`), tệp gọi/được import một bước, test
  nhắc tên; xếp hạng √ref, ×0,1 tên định nghĩa ở > 5 tệp, ×10 tên tệp khớp định
  danh story. **Tắt mặc định** (`context.max_repo_map_chars` = 0) tới khi A/B T8
  có số; `context.map_provider` cắm lệnh ngoài (stdin JSON → stdout). Prompt
  `story-implement@7` · `story-review@6` · `story-security-review@4` có mục
  "Bản đồ mã quanh phạm vi — gợi ý tĩnh, không phải chân lý", chỉ hiện khi slot
  khác rỗng. **Mới** `aisef ctx --story S | --file F [--budget N]`: bản đầy đủ,
  ghi `note:ctx_lookup` khi gọi trong phiên. Hồi cứu $0 lỗi 21 ở ADR-005 §9:
  bản đồ **không** tự lộ `tests/e2e` khi phạm vi chỉ `src/**` — spec e2e của e9
  không nhắc tên nào của `src`; thứ lộ nó là `verification_paths` (sửa lỗi 21).
- **Đổi hành vi — `control/impact.py`** (ADR-005 §9 phát hiện 5): tách
  `symbols()` / `refs()` / `weights()`, `builtin` chấm tệp = Σ trọng số × √số
  lần nhắc — tên định nghĩa ở > 5 tệp ×0,1, `_private` bỏ; tệp chỉ dính tên
  phổ biến (`save`, `render`) không còn lấp `callers` rồi bị cắt lặng ở 12 mục.
  Sửa số dòng định nghĩa lệch khi có dòng trống phía trước (`^\s*` → `^[ \t]*`).

### 5 · Guardrails / hooks

- **Guard thứ 8 `process-ref`** (`PreToolUse` · `Write|Edit`): mã story/epic
  trong mã nguồn; test và tài liệu được phép. Cần `aisef compile` lại.
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
- **Hợp đồng chấm tối thiểu** (ADR-005 V9): `Check.kind` (deterministic ·
  structural · security · model-judge · human — `outcome.CHECK_KINDS`,
  `gate.CHECK_KIND` một chỗ) và `Check.evidence` (con trỏ `seq` sự kiện đã đọc;
  13/16 mục trỏ, `phạm vi ghi`/`bảo mật`/`rà soát` rỗng vì suy từ tham số);
  `gate.CHECK_NAMES` danh sách đóng 16 tên (15 mục + họ `<kind>`, tính cả V3);
  `tests/test_gate_qualification.py` mỗi tên 3 control positive · negative ·
  env + test meta (tên lạ trong `gate.py`, thiếu control, `CHECK_KIND` lệch);
  `gate.qualification_table()` đọc AST tệp test; `gate:verdict` ghi `checks[]`
  đủ `kind`/`evidence`; báo cáo in "mục cổng có đủ 3 control: 16/16". Không có
  `blocking` (YAGNI). `Check("lint", True)` cũ không đổi.
- **Mục cổng `test có kiểm được story`** (ADR-005 V3, ngay sau `TDD`): test
  mang `AC-<story>-i` phải đỏ khi không có mã của story — cấp 1 $0 so với
  `test:baseline` (xanh sẵn cùng tên hoặc đổi tên để gắn mã → ✗ nêu tên; lượt
  chạy lại `parent` ≠ `base_ref` thì không so), cấp 2 đọc `test:nop` (xanh ở SHA
  cha → ✗; không chạy được ⚠; không in tên ○; không thêm test / tắt / nhật ký
  cũ –). Hồi cứu e9: 01-07 lần chạy 3 (40 test xanh sẵn — lượt chạy lại) và
  RP-02/03/04 (gắn mã vào test có sẵn) sẽ ✗ (ADR-005 §9 V3).
- Hợp quy client: phép **C6** (luật 6), **C7** (ghi ngoài scope), **C8** (ứng
  viên stale) — 16/16 hai client 2026-09-06 (`docs/CONFORMANCE.md`).
- `destructive` chặn **mọi** `git push` (không chỉ `--force`; kể cả `--dry-run`),
  `git remote add/set-url`, `git credential*` và `-c credential.helper=` — thông
  điệp nói push/merge là việc của harness sau cổng (ADR-005 V2; hợp quy C10).
  Regex nhận cờ toàn cục trước lệnh con (`git -C w push`, `git -c k=v push`).

### 6 · Observability

- **Truy vết người khai** (`control/ledger.py::TRACE_FILE`, QĐ B6 2026-09-06):
  `aisef evidence <AC> --link "<test id>" --why … [--by]` ghi
  `traceability.json` {test_id, why, by, at}; sổ hành vi coi test ấy là test
  của tiêu chí **nhưng vẫn đòi nó xanh ở ứng viên đã landed** — nguồn ghi
  `via: traceability, by, why` để ai đọc cũng thấy đây là khai, không phải đo.

- **`pre-deploy-report.json`** thêm `scope` (phạm vi nghiệm thu) và `waivers`
  (loại miễn → lý do từ `verify.waiver_reason`); mục ◇ "miễn tường minh" chặn
  khi `verify.waived` khác rỗng mà không có lý do (QĐ5 2026-09-06: `mutation`
  của e9 UNRUNNABLE ở môi trường nghiệm thu, không cài công cụ để làm đẹp).

- **Mới** `agent_run.detail.exit_status` ∈ {ok, max_turns, timeout, cost,
  context, permission, infra, error} (`clients/stream.py::exit_status_of`,
  ADR-005 V11 B); `Attempt.infra` và vòng thử lại `plan` đọc cùng
  `INFRA_STATUSES` thay cho bảng chuỗi `INFRA_ERRORS` (đã gỡ) — lượt `429`
  hạn mức API từng bị tính là lỗi chất lượng (e9 RP-05). `aisef status` in
  "Lượt agent: ok n · max_turns n · … · chưa ghi n". Đếm trên e9: max_turns
  4 lượt/3 story, khớp đếm tay ADR-004 §6 trong phạm vi EPIC-01.
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
  `review:verdict`/`security:verdict` (JSON), `gate:input` (ADR-005 V4),
  `gate:verdict`, `evidence_lookup`, `doc_lookup`; `tool_run test:nop` (V3).
- Báo cáo: ô Map mockup lấy kết quả **mới nhất** từng màn (lỗi 18); cột tiêu
  chí có test `n/n`; SHA ứng viên.
- OpenCode `--format json` → `MACHINE_OUTPUT`/`COST_REPORTING` NATIVE (vẫn hạng
  hai V1 — SOLUTION §11).
- Kho hồi quy chạy lại được từ kho: `tests/dogfood/` (`par`, mốc 3/3 lượt đầu,
  ≤ 2 × $3,14) và `tests/conformance/` (10 phép, hai client); release gate
  `AISEF_RELEASE=1 tests.test_release_gate`.
- **Mới** `tests/bench/` (ADR-005 V8, Benchmark Factory): task từ hai mỏ —
  lỗi thật của kho (`tests/bench/tasks/`, commit; commit sửa tìm bằng
  `git log -S<tên test>`, base = cha, test hồi quy giữ, nguồn hoàn nguyên) và
  story e9 `done` (sinh lúc chạy từ `AISEF_BENCH_E9`, base = `test:baseline.parent`
  hoặc commit `main` trước lượt đầu, test = `is_test_path`, gold = phần còn lại).
  Lint rò: SHA, URL, `STORY-RP-*`, tên commit sửa. `validate` ×3 trên bản chép
  `git archive` (một ref — worktree thấy `story/*` = gold): F2P/P2P theo tên,
  test đổi kết cục → `flaky_ids` loại và nêu tên, không F2P → INVALID. `run`: một
  phiên client, guard như hợp quy, `note mode=bench`, hoàn nguyên test agent
  chạm rồi áp test ẩn, chấm ở ứng viên đóng băng. `report` pass@1/pass@k/ổn
  định/cost so lịch sử; `export` thư mục Harbor (adapter ngoài). Số đo: ADR-005 §9.
- `aisef doctor`: hook trỏ đúng dự án, hook thiếu guard mới, ngưỡng cỡ story
  lệch dữ liệu, gợi ý lệnh test in coverage, gợi reporter in tên/CTRF (V9).

### Knob cấu hình mới (mặc định) — `aisef/config.py::DEFAULTS`, ý nghĩa ở SOLUTION §13

| Khoá | Mặc định | Từ |
|---|---|---|
| `story.max_screen_states` | `8` | P2-12 |
| `story.max_complexity` | `16.0` | ADR-004 R5 |
| `context.max_index_chars` | `2000` | ADR-004 R6 |
| `context.max_preservation_chars` | `1 200` | ADR-004 R4 |
| `context.max_repo_map_chars` · `context.map_provider` | `0` (tắt) · `""` | ADR-005 V7 |
| `improve.max_loops` · `improve.flat_loops` · `improve.cost_cap_usd` | `3` · `2` · `0.0` | ADR-004 R3 |
| `verify.baseline` | `true` | ADR-004 R9 |
| `verify.clean_tree` | `true` | ADR-005 V6 |
| `verify.nop` | `true` | ADR-005 V3 |
| `skills.inline` | `false` | ADR-003 §6 |
| `sandbox.pre_deploy_degraded_waiver` | `""` | quyết định 4 |
| `verify.waiver_reason` | `""` | quyết định 5 (2026-09-06) |
| `sandbox.provider` | `"docker"` | ADR-005 V5 |
| `clients.env_allow` | `[]` | ADR-005 V2 |

Gỡ: `story.max_context_tokens` (chưa từng có mã đọc; `RETIRED`, cảnh báo rồi bỏ qua).

### Lệnh CLI mới — `aisef/cli/parser.py`, bộ lệnh đủ ở SOLUTION §10

`aisef improve` · `aisef evidence` · `aisef ctx` · `aisef doc` · `aisef change` ·
`aisef skill --scan` · `aisef guard process-ref` · `aisef run --verify-only
--story S [--repeat K]` · `aisef gate --replay` (ADR-005 V4) · `aisef pre-deploy
--epic E` (QĐ C-a) · `aisef evidence <AC> --link TEST --why …` (QĐ B6). Gói
`aisef/cli/` tách từ một tệp `cli.py` (S5), không đổi hành vi.

### Lỗi thật tìm bằng đo trong đợt này

30 lỗi, không lỗi nào bằng đọc code; bảng và lớp nguyên nhân ở
`docs/FAILURE-TAXONOMY.md`, chi tiết ở STATUS §2.4. Lỗi 22 (e2e nhạy tải máy)
đóng bằng R13 `run --story S --verify-only --repeat`; 26/27 (sổ/bảo toàn, đo
trên `par` agent thật) và 28 (băm chỉ mục quên `waves` của epic sửa) sửa kèm
test đỏ-khi-hoàn-nguyên.
