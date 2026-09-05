# AI-SDLC

Khung phát triển phần mềm bằng agent. Đầu vào của mỗi dự án là **một file**
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
pip install ai-sdlc
```

Hoặc chạy từ bản sao kho nguồn:

```bash
git clone <repo> ai-sdlc && cd ai-sdlc && pip install -e .
python3 -m unittest discover -s tests -q
```

Kho skill tham chiếu **không cần clone tay**: `aisdlc setup` tự lấy về
`~/.cache/ai-sdlc/references` đúng commit mà `aisdlc/kit/catalog.json`
ghim (khoảng 93 MB, một lần cho mọi dự án). Máy ngoại tuyến hoặc CI trỏ
sang chỗ khác bằng `AISDLC_REFERENCES=/duong/dan`, hoặc dùng
`aisdlc setup --no-fetch` để chỉ xài những gì đã có trên đĩa.

Không có phụ thuộc Python nào ngoài thư viện chuẩn. Tuỳ chọn:
`docker` (cách ly khi chạy test), `playwright` (trích hợp đồng thị giác
từ mockup) — thiếu thì framework **nói thẳng là thiếu** chứ không giả vờ
vẫn kiểm được.

## Sáu bước

```bash
cd /duong/dan/du-an-cua-ban

aisdlc doctor                       # môi trường có đủ chưa
aisdlc setup                        # dò stack, nạp skill, sinh CLAUDE.md + AGENTS.md
aisdlc compile                      # nối guard vào client (hook / plugin)

aisdlc plan                         # PRD → kiến trúc → UX → epic → story
aisdlc gates                        # xem cổng nào đang chờ người
aisdlc review prd                   # đọc artifact
aisdlc approve prd                  # duyệt

aisdlc mockup                       # mỗi màn hình một HTML + hợp đồng thị giác
aisdlc approve mockups
aisdlc approve readiness

aisdlc run                          # hiện thực: epic tuần tự, story song song
aisdlc qa                           # bộ kiểm định
aisdlc devsecops                    # CI + Dockerfile + triển khai + runbook
aisdlc pre-deploy                   # cổng cuối
aisdlc report                       # báo cáo nghiệm thu từ bằng chứng
```

Chạy nhanh không cần người duyệt: `aisdlc plan --auto-approve all`. Phê duyệt
tự động **luôn** được ghi dấu `auto` để về sau truy được tài liệu nào chưa
từng có người thật xem.

## Sau khi có code

```bash
aisdlc doc vitest --topic coverage --story STORY-01-02
```

Tra tài liệu thật của thư viện (context7, có cache) thay vì đoán tên API; có
`--story` thì lần tra vào bằng chứng. Khi yêu cầu đổi sau phát hành:

```bash
aisdlc change FR-3 "Slug phải giữ dấu gạch dưới"
```

Ghi vào `docs/requirements.md`, đánh dấu PRD (cổng `prd` và các cổng sau
thành stale), sinh story delta `STORY-CH-01` với `covers=[FR-3]` — story cũ
giữ nguyên `DONE`.

## Cổng

Tám cổng, mỗi cổng hai lớp. **Cổng máy** chạy trước — nó bắt được thứ máy
bắt tốt hơn người (chu trình phụ thuộc, yêu cầu không kiểm chứng được,
story không khai phạm vi ghi). **Cổng người** chạy sau, trên thứ đã sạch.

Phê duyệt là **trạng thái trên đĩa**, không phải câu hỏi trong phiên chat:
người duyệt có thể là người khác, lúc khác, trên máy khác. Bản ghi phê
duyệt gắn với **băm nội dung** artifact — sửa tài liệu sau khi duyệt thì
phê duyệt hết hiệu lực, và sửa tầng trên làm mọi tầng dưới thành `stale`.

## Guard

Bảy guard, mỗi guard là một lệnh trả mã thoát, nối vào ba mốc vòng đời:

| Mốc | Guard |
|---|---|
| trước mỗi tool | `write-scope` · `destructive` · `secret` · `git-stage` · `injection` · `process-ref` (luật 6: không mã story/epic trong nguồn) |
| sau mỗi tool | `diff-scope` |
| khi agent định dừng | `completion` |

Guard nằm ở phía framework, không ở phía client — client không được tin.
Cả Claude Code và OpenCode đều đã **chứng minh bằng phép thử trên agent
thật** rằng guard chặn *trước* khi tool chạy, chứ không phải phát hiện
sau. Client nào không gắn được guard tiền kiểm thì `aisdlc verify` chạy
lại toàn bộ trên diff, và `aisdlc compile` ghi rõ mức bảo đảm thấp hơn
vào báo cáo thay vì im lặng — năng lực là thứ được **khai và kiểm**, mặc
định là "chưa chứng minh", không phải "chắc là được". Trong V1, OpenCode
là client **hạng hai** theo quyết định V1: guard chặn được (hợp quy 7/7), và từ 2026-09-05 `--format json` cho luồng máy đọc được (tool, token, cost theo nhà cung cấp) — chưa lên hạng nhất vì chưa đủ số lần hợp quy hook ổn định; chi phí trước đó không đo
được từ harness; nó không chặn phát hành.

## Lỗi thật đã gặp

Mười tám lỗi tìm bằng đo trên agent thật, xếp theo bảy lớp nguyên nhân kèm phép hồi quy: `docs/FAILURE-TAXONOMY.md`. Lỗi mới thì thêm một dòng vào đó cùng commit với test.

## Hợp quy client

Hook và plugin là tạo tác **biên dịch ra** — đúng cú pháp không có nghĩa là
client chạy chúng. Bốn lỗi thật (31, 39, 40, 41) đều thuộc lớp này, và unit
test không bắt được theo định nghĩa. Bộ hợp quy chạy bảy phép thử trên
client thật, worktree thật, guard thật, `.claude/` không commit:

```bash
AISDLC_CONFORMANCE=1 python3 -m unittest tests.conformance -v
```

Kết quả ghép vào `docs/CONFORMANCE.md` — mỗi ô là một phiên agent, đọc từ
đĩa (tệp còn/mất), từ luồng `tool_use` và bằng chứng guard tự ghi, không từ
lời agent. Dự án thử và log thô từng phép giữ ở `.conformance/<client>/`
(đổi bằng `AISDLC_CONFORMANCE_DIR`) để tra lại một ô ✗ mà không phải đoán.
Bộ chạy **không** thừa hưởng biến `CLAUDE_*` của phiên gọi nó — chạy hợp
quy từ bên trong một phiên Claude là chuyện có thật, và phiên con thừa hưởng
cờ của phiên cha thì đo sai. Cổng
phát hành của chính kho này đọc bảng đó bằng code
(`AISDLC_RELEASE=1 python3 -m unittest tests.test_release_gate`): cột
`claude` phải đủ năm ô ✅ và bảng không cũ hơn 14 ngày. OpenCode là hạng
hai trong V1 — có cột, không chặn. CI: `.github/workflows/conformance.yml`
chạy tuần.

## Phát hành

Gói tên `ai-sdlc`, phát hành khi hoàn tất đợt 4 (quyết định 2026-09-05).
Điều kiện đọc bằng lệnh, không bằng cảm giác:

```bash
python3 -m unittest discover -s tests -q && AISDLC_RELEASE=1 python3 -m unittest tests.test_release_gate -q
```

```bash
uv build && uvx twine check dist/*
```

`.github/workflows/release.yml` publish bằng *trusted publishing* khi đẩy tag
`v*` — không có token nào trong kho. Việc làm **một lần bằng tay**, bằng tài
khoản tổ chức: tạo project `ai-sdlc` trên PyPI và khai trusted publisher
(kho này · workflow `release.yml` · environment `pypi`). Sau đó:

```bash
git tag v0.1.0 && git push --tags
```

Kho hồi quy dogfood (`tests/dogfood/`, bật bằng `AISDLC_DOGFOOD=1`) dựng lại
dự án thử `par` từ đầu vào trong kho và so với mốc đã đo — chạy trước mỗi tag.

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
aisdlc/
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
