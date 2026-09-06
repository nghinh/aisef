# AISEF — AI Software Engineering Framework

Khung phát triển phần mềm bằng agent. Tên đầy đủ là **AI Software Engineering
Framework**, viết tắt **AISEF**; gói trên PyPI, module Python và lệnh đều là
`aisef`. Đầu vào của mỗi dự án là **một file**
`docs/requirements.md`; đầu ra là một ứng dụng chạy được, kèm bằng chứng
cho từng bước.

Nguyên tắc nền, xuyên suốt mọi quyết định trong kho này:

> **Cần phán đoán thì giao cho model. Cần đảm bảo thì viết code.**

Viết PRD, thiết kế kiến trúc, dựng mockup, viết code — đều cần phán đoán,
đều giao cho model. Còn "mọi yêu cầu phải có story phủ", "không được ghi
ra ngoài phạm vi", "test phải xanh sau lần sửa cuối" — đều có đáp án đúng,
nên đều là code. Hệ quả: **không bao giờ giao cho model việc giám sát
chính nó.**

## Cài

```bash
pip install aisef
```

Hoặc chạy từ bản sao kho nguồn:

```bash
git clone <repo> aisef && cd aisef && pip install -e .
python3 -m unittest discover -s tests -q   # vài phút, không mở container (tests/__init__.py)
AISEF_TEST_DOCKER=1 python3 -m unittest tests.test_sandbox tests.test_tools -q   # thêm test Docker thật
```

Kho skill tham chiếu **không cần clone tay**: `aisef setup` tự lấy về
`~/.cache/aisef/references` đúng commit mà `aisef/kit/catalog.json`
ghim (khoảng 93 MB, một lần cho mọi dự án). Máy ngoại tuyến hoặc CI trỏ
sang chỗ khác bằng `AISEF_REFERENCES=/duong/dan`, hoặc dùng
`aisef setup --no-fetch` để chỉ xài những gì đã có trên đĩa.

Không có phụ thuộc Python nào ngoài thư viện chuẩn. Tuỳ chọn:
`docker` (cách ly khi chạy test), `playwright` (trích hợp đồng thị giác
từ mockup) — thiếu thì framework **nói thẳng là thiếu** chứ không giả vờ
vẫn kiểm được.

## Hướng dẫn dùng từng bước

Người mới bắt đầu đọc `docs/HUONG-DAN-SU-DUNG.md`: chuẩn bị máy, cài, viết
`docs/requirements.md`, cấu hình lệnh test, đi hết tám cổng, đọc kết cục cổng,
xử lý sự cố, bảng lệnh và bảng khoá cấu hình đầy đủ.

## Sáu bước

```bash
cd /duong/dan/du-an-cua-ban

aisef doctor                       # môi trường có đủ chưa
aisef setup                        # dò stack, nạp skill, sinh CLAUDE.md + AGENTS.md
aisef compile                      # nối guard vào client (hook / plugin)

aisef plan                         # PRD → kiến trúc → UX → epic → story
aisef gates                        # xem cổng nào đang chờ người
aisef review prd                   # đọc artifact
aisef approve prd                  # duyệt

aisef mockup                       # mỗi màn hình một HTML + hợp đồng thị giác
aisef approve mockups
aisef approve readiness

aisef run                          # hiện thực: epic tuần tự, story song song
aisef run --verify-only --story STORY-01-07   # kiểm lại ứng viên đã đóng băng, không mở phiên developer
aisef qa                           # bộ kiểm định
aisef devsecops                    # CI + Dockerfile + triển khai + runbook
aisef pre-deploy                   # cổng cuối
aisef report                       # báo cáo nghiệm thu + sổ hành vi + INDEX.md
aisef evidence STORY-01-04         # lịch sử một story hay một hành vi (AC-…, FR-…, qa:e2e)
aisef issues --format csv          # bảng gap/hồi quy từ sổ hành vi → _bmad-output/ISSUES.csv
```

Chạy nhanh không cần người duyệt: `aisef plan --auto-approve all`. Phê duyệt
tự động **luôn** được ghi dấu `auto` để về sau truy được tài liệu nào chưa
từng có người thật xem.

## Sau khi có code

```bash
aisef doc vitest --topic coverage --story STORY-01-02
```

Tra tài liệu thật của thư viện (context7, có cache) thay vì đoán tên API; có
`--story` thì lần tra vào bằng chứng. Khi yêu cầu đổi sau phát hành:

```bash
aisef change FR-3 "Slug phải giữ dấu gạch dưới"
```

Ghi vào `docs/requirements.md`, đánh dấu PRD (cổng `prd` và các cổng sau
thành stale), sinh story delta `STORY-CH-01` với `covers=[FR-3]` — story cũ
giữ nguyên `DONE`.

```bash
aisef improve --epic EPIC-01 --max-loops 3      # [--auto] không dừng ở cổng người
```

Vòng cải tiến theo bằng chứng (ADR-004 R3): QA → sổ hành vi → **một** story
sửa cho một hành vi GAP/REOPENED (`STORY-RP-01` trong `EPIC-RP-01`, sinh bằng
code) → `run` như story thường → QA → mốc `loops[]` + `LOOP-REPORT-<n>.md`.
Dừng bằng code: hết gap, đủ `improve.max_loops`, cải thiện biên ≤ 0
`improve.flat_loops` vòng liền, vượt `improve.cost_cap_usd`, hay story sửa bế
tắc kế hoạch (trả người kèm lời reviewer). Trước mỗi vòng ≥ 2 cần
`aisef approve improve` trừ `--auto`.

```bash
aisef run --verify-only --story STORY-01-07
```

Story trượt chỉ vì môi trường đo (e2e nhạy tải máy) thì không cần trả tiền
cho một phiên developer để dựng lại mã đã có (ADR-004 R13): lượt kiểm-lại
lấy ứng viên ở HEAD nhánh story, chạy lại đúng phép kiểm ✗/thiếu ở SHA ấy,
giữ rà soát và bảo mật đã có ở cùng SHA, chấm đủ cổng; đạt thì merge như lượt
thường, trượt thì `failed` và không ăn vào `run.max_retries`.

## Cổng

Tám cổng, mỗi cổng hai lớp. **Cổng máy** chạy trước — nó bắt được thứ máy
bắt tốt hơn người (chu trình phụ thuộc, yêu cầu không kiểm chứng được,
story không khai phạm vi ghi). **Cổng người** chạy sau, trên thứ đã sạch.

Phê duyệt là **trạng thái trên đĩa**, không phải câu hỏi trong phiên chat:
người duyệt có thể là người khác, lúc khác, trên máy khác. Bản ghi phê
duyệt gắn với **băm nội dung** artifact — sửa tài liệu sau khi duyệt thì
phê duyệt hết hiệu lực, và sửa tầng trên làm mọi tầng dưới thành `stale`.

## Guard

Tám guard, mỗi guard là một lệnh trả mã thoát, nối vào ba mốc vòng đời:

| Mốc | Guard |
|---|---|
| trước mỗi tool | `write-scope` · `destructive` · `secret` · `git-stage` · `injection` · `process-ref` (luật 6: không mã story/epic trong nguồn) |
| sau mỗi tool | `diff-scope` |
| khi agent định dừng | `completion` |

Guard nằm ở phía framework, không ở phía client — client không được tin.
Cả Claude Code và OpenCode đều đã **chứng minh bằng phép thử trên agent
thật** rằng guard chặn *trước* khi tool chạy, chứ không phải phát hiện
sau. Client nào không gắn được guard tiền kiểm thì `aisef verify` chạy
lại toàn bộ trên diff, và `aisef compile` ghi rõ mức bảo đảm thấp hơn
vào báo cáo thay vì im lặng — năng lực là thứ được **khai và kiểm**, mặc
định là "chưa chứng minh", không phải "chắc là được". Trong V1, OpenCode
là client **hạng hai** theo quyết định V1: guard chặn được (hợp quy 7/7), và từ 2026-09-05 `--format json` cho luồng máy đọc được (tool, token, cost theo nhà cung cấp) — chưa lên hạng nhất vì chưa đủ số lần hợp quy hook ổn định; chi phí trước đó không đo
được từ harness; nó không chặn phát hành.

## Lỗi thật đã gặp

Hai mươi lăm lỗi tìm bằng đo trên agent thật, xếp theo mười một lớp nguyên nhân kèm phép hồi quy: `docs/FAILURE-TAXONOMY.md`. Lỗi mới thì thêm một dòng vào đó cùng commit với test. Thay đổi theo phiên bản, kèm việc phải làm khi nâng cấp: `CHANGELOG.md`.

## Hợp quy client

Hook và plugin là tạo tác **biên dịch ra** — đúng cú pháp không có nghĩa là
client chạy chúng. Bốn lỗi thật (31, 39, 40, 41) đều thuộc lớp này, và unit
test không bắt được theo định nghĩa. Bộ hợp quy chạy bảy phép thử trên
client thật, worktree thật, guard thật, `.claude/` không commit:

```bash
AISEF_CONFORMANCE=1 python3 -m unittest tests.conformance -v
```

Kết quả ghép vào `docs/CONFORMANCE.md` — mỗi ô là một phiên agent, đọc từ
đĩa (tệp còn/mất), từ luồng `tool_use` và bằng chứng guard tự ghi, không từ
lời agent. Dự án thử và log thô từng phép giữ ở `.conformance/<client>/`
(đổi bằng `AISEF_CONFORMANCE_DIR`) để tra lại một ô ✗ mà không phải đoán.
Bộ chạy **không** thừa hưởng biến `CLAUDE_*` của phiên gọi nó — chạy hợp
quy từ bên trong một phiên Claude là chuyện có thật, và phiên con thừa hưởng
cờ của phiên cha thì đo sai. Cổng
phát hành của chính kho này đọc bảng đó bằng code
(`AISEF_RELEASE=1 python3 -m unittest tests.test_release_gate`): cột
`claude` phải đủ năm ô ✅ và bảng không cũ hơn 14 ngày. OpenCode là hạng
hai trong V1 — có cột, không chặn. CI: `.github/workflows/conformance.yml`
chạy tuần.

## Phát hành

Gói, module Python và lệnh cùng tên **`aisef`** (từ 0.2.0; 0.1.0 cài `aisef` nhưng gõ `aisdlc` — bí danh cũ còn chạy tới 0.3.0, có cảnh báo).
Điều kiện đọc bằng lệnh, không bằng cảm giác:

```bash
python3 -m unittest discover -s tests -q && AISEF_RELEASE=1 AISEF_ACCEPTANCE=<dự án nghiệm thu> python3 -m unittest tests.test_release_gate -q
```

`AISEF_ACCEPTANCE` trỏ vào dự án dogfood đã nghiệm thu (v0.1.0: `e9`, phạm vi
EPIC-01): cổng đọc `pre-deploy-report.json` (đạt, có phạm vi, miễn có lý do)
và phê duyệt `pre-deploy` trên đúng bản ấy. Không đặt thì bỏ qua có nêu tên —
không tính là đạt.

```bash
uv build && uvx twine check dist/*
```

`.github/workflows/release.yml` publish bằng *trusted publishing* khi đẩy tag
`v*` — không có token nào trong kho. Việc làm **một lần bằng tay**, bằng tài
khoản tổ chức: tạo project `aisef` trên PyPI và khai trusted publisher
(kho này · workflow `release.yml` · environment `pypi`). Sau đó:

```bash
git tag v0.1.0 && git push --tags
```

Kho hồi quy dogfood (`tests/dogfood/`, bật bằng `AISEF_DOGFOOD=1`) dựng lại
dự án thử `par` từ đầu vào trong kho và so với mốc đã đo — chạy trước mỗi tag.

### Giới hạn đã biết của v0.1.0

Khai ở đây vì mọi claim phải có bằng chứng; thứ chưa chứng minh gọi là chưa
chứng minh (quyết định chủ đầu tư 2026-09-06, `docs/RELEASE-PLAN-v0.1.0.md` §0):

- **Phạm vi nghiệm thu dogfood là EPIC-01 của `e9`** (7 story, `aisef
  pre-deploy --epic EPIC-01`). EPIC-02..05 (16 story) chưa chạy — báo cáo ghi
  "ngoài phạm vi", không phải "xong". `e9` chưa phải sản phẩm được nghiệm thu
  hoàn chỉnh; nó là corpus nghiệm thu của framework.
- **OpenCode là client hạng hai**: hợp quy 9/10 (C9 model từ chối, không kết
  luận), không có đầu ra máy đọc ổn định; claim phát hành dựa trên Claude Code.
- **Agent trong container chưa có cách ly credential** (S1 blocked): V1 chạy
  agent trên host, chỉ kiểm định trong container; `doctor`/`pre-deploy` nêu
  tên bảo đảm thiếu, không im lặng.
- **`mutation` ở môi trường nghiệm thu là KHÔNG CHẠY ĐƯỢC** (công cụ chưa cài);
  được miễn có lý do ở `verify.waiver_reason`, hiện ◇, không bao giờ thành ✅.
  `image-scan` cùng loại (docker scout đòi đăng nhập, trivy/grype vắng).
- **`skills.offer`/`skills.inline` tắt** (A/B không thấy gain), **`repo_map`
  tắt** (`context.max_repo_map_chars = 0`, A/B hoãn sau v0.1.0).
- **`coverage`**: harness đọc số từ runner (`--coverage`/`--cov`); dự án chưa
  bật thì mục cổng là ○ chưa cấu hình, không phải đạt.

## Khi cổng chặn

Cổng chặn là framework đang làm việc, không phải framework hỏng. Ba ca hay
gặp và cách xử đúng:

| Cổng báo | Nghĩa là | Làm gì |
|---|---|---|
| `mockup còn N chỗ chưa chốt` | mockup gặp câu hỏi chưa ai trả lời và **đánh dấu** thay vì tự quyết | trả lời câu hỏi (thường nằm ở `open_questions` của PRD/UX), sửa tài liệu, dựng lại mockup |
| `story đụng vào yêu cầu đang bị câu hỏi mở chặn` | epic gán một FR mà PRD ghi là chưa quyết được | trả lời câu hỏi, hoặc bỏ FR đó khỏi story |
| `merge đụng …` | hai story cùng sửa một file | `write_scope` khai sai — sửa ở story, **không** gỡ conflict cho xong |

`--force` có ở `approve` và `run` cho trường hợp cố ý bỏ qua. Dùng nó là
một quyết định, và nó được ghi lại: bản ghi phê duyệt giữ ghi chú, báo cáo
nghiệm thu hiện đúng trạng thái từng cổng.

## Chạy song song

Epic chạy tuần tự. Trong một epic, hai story chỉ được cùng đợt khi **hết
phụ thuộc** *và* **phạm vi ghi rời nhau** — thiếu điều kiện thứ hai thì hai
story cùng sửa một file và người thua là người merge sau. Mỗi story chạy
trong worktree git riêng; merge tuần tự cuối đợt. Conflict lúc merge không
được tự gỡ: nó là **bằng chứng `write_scope` khai sai**.

## Cấu trúc

```
aisef/
  cli/              bộ lệnh chia theo pha, mọi lệnh gọi-một-lần, không daemon
  config.py         ngưỡng và cấu hình, có kiểu, có kiểm
  clients/          Claude Code · OpenCode; năng lực được **khai**, không giả định
  control/          cổng, phê duyệt, xếp lịch, worktree, chuẩn hoá tài liệu BMAD
  harness/          prompt · tool · sandbox · guard · quan sát · map mockup
  kit/              catalog skill, lọc bảo mật hai tầng, hiến pháp, prompt, skill riêng
  phases/           plan · mockup · implement · run · qa · deploy · report
docs/
  SOLUTION.md              giải pháp tổng thể và vì sao chọn như vậy
  EXECUTION-PLAN.md        kế hoạch thực thi, trạng thái từng hạng mục
  REQUIREMENTS-EVIDENCE.md R1–R14 → test chạy được
  SPIKE-REPORT.md          kết quả 7 spike kiểm chứng khả thi
```

## Bằng chứng, không tự khai

Mọi cổng đọc `_bmad-output/evidence/{story}.jsonl` — lần chạy test, lần
sửa file, lần gọi model kèm chi phí và độ trễ, lần đối chiếu mockup. Câu
"đã hoàn thành" của agent không được tính là gì cả.

Cụ thể, một story chỉ xong khi: test xanh **và** xanh sau lần sửa cuối ·
lint sạch · thay đổi nằm trong phạm vi khai báo · màn hình thật dựng đủ
component mockup đã hứa · rà soát độc lập (phiên khác, cấm sửa code) không
còn mục chặn · không có test nào rỗng khẳng định.
