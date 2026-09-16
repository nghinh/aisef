# Hướng dẫn sử dụng AISEF

[Bộ nhớ dài hạn — **ĐÓNG BĂNG**, mặc định TẮT](MEMORY.md): từ phụ lục ADR-007 ngày 2026-09-12, `aisef memory` không còn là "thử nghiệm, sắp có" mà là **đóng băng**: code còn đó và vẫn được sửa lỗi/lỗ bảo mật, nhưng **không thêm năng lực mới**. Rã băng cần một yêu cầu từ bên ngoài, **hoặc** một phép đo có đối chứng cho thấy một lỗi lặp lại mà bộ nhớ hẳn đã ngăn được. Bộ nhớ **không** phải bằng chứng cho cổng. Tham khảo: [nghiên cứu/kế hoạch](MEMORY-RESEARCH-PLAN.md), [báo cáo kiểm thử](MEMORY-VALIDATION.md), [ADR-007](ADR-007-scoped-advisory-memory.md).

**AISEF** là viết tắt của **AI Software Engineering Framework**. Gói cài, module
Python và lệnh gõ đều tên `aisef`.

Hướng dẫn này viết cho người **chưa từng dùng** framework, và cố gắng không
bỏ qua bước nào. Mỗi phần có: gõ lệnh gì, chờ bao lâu, màn hình hiện gì, và
làm gì khi nó không hiện như vậy.

Quy ước đọc:

- Khối `bash` là lệnh gõ vào terminal. Gõ từng khối một, đọc kết quả rồi mới sang khối sau.
- `dấu ✅ ○ ⚠ ✗ –` là **sáu kết cục** của framework, không phải trang trí. Ý nghĩa ở [§10](#10-đọc-cổng-story-sáu-kết-cục).
- Chỗ nào viết "chờ vài phút" nghĩa là có phiên agent đang chạy và **tốn tiền**; chi phí thật ở [§14](#14-chi-phí-thật-và-cách-giảm).

---

## Mục lục

1. [Framework này làm gì](#1-framework-này-làm-gì)
2. [Chuẩn bị máy](#2-chuẩn-bị-máy)
3. [Cài đặt](#3-cài-đặt)
4. [Tạo dự án và viết đầu vào](#4-tạo-dự-án-và-viết-đầu-vào)
5. [`aisef setup` — nạp skill, sinh luật](#5-aisef-setup--nạp-skill-sinh-luật)
6. [Cấu hình `.ai/config.json`](#6-cấu-hình-aiconfigjson)
7. [`aisef compile` và `aisef doctor`](#7-aisef-compile-và-aisef-doctor)
8. [Bước lập kế hoạch: `aisef plan`](#8-bước-lập-kế-hoạch-aisef-plan)
9. [Bước mockup (dự án có giao diện)](#9-bước-mockup-dự-án-có-giao-diện)
10. [Đọc cổng story: sáu kết cục](#10-đọc-cổng-story-sáu-kết-cục)
11. [Bước hiện thực: `aisef run`](#11-bước-hiện-thực-aisef-run)
12. [Kiểm định, đóng gói, nghiệm thu](#12-kiểm-định-đóng-gói-nghiệm-thu)
13. [Vòng cải tiến và thay đổi sau phát hành](#13-vòng-cải-tiến-và-thay-đổi-sau-phát-hành)
14. [Chi phí thật và cách giảm](#14-chi-phí-thật-và-cách-giảm)
15. [Xử lý sự cố](#15-xử-lý-sự-cố)
16. [Tra cứu: toàn bộ lệnh](#16-tra-cứu-toàn-bộ-lệnh)
17. [Tra cứu: toàn bộ khoá cấu hình](#17-tra-cứu-toàn-bộ-khoá-cấu-hình)
18. [Thuật ngữ](#18-thuật-ngữ)

---

## 1. Framework này làm gì

Bạn đưa vào **một tệp** mô tả bạn muốn phần mềm gì (`docs/requirements.md`).
Framework điều phối agent đi hết vòng đời: viết tài liệu sản phẩm, thiết kế,
dựng mockup, chia story, viết code, chạy kiểm định, đóng gói, và **để lại
bằng chứng cho từng bước**.

Nguyên tắc nền, giải thích vì sao mọi thứ được xếp như bạn thấy:

> Cần phán đoán thì giao cho model. Cần đảm bảo thì viết code.

Vì thế có **hai loại cổng**:

- **Cổng máy**: code chấm, không hỏi ai. Ví dụ "mọi yêu cầu phải có story phủ",
  "không được ghi ra ngoài phạm vi", "test phải xanh sau lần sửa cuối". Máy
  chấm xong mới tới người.
- **Cổng người**: bạn đọc và ký. Có **tám** cổng trên đường tới phát hành, theo
  đúng thứ tự:
  `prd → architecture → ux-spec → epics → stories → mockups → readiness → pre-deploy`.
  (Còn một cổng thứ chín, `improve`, không nằm trên đường ấy: nó hỏi trước mỗi
  vòng cải tiến — [§13](#13-vòng-cải-tiến-và-thay-đổi-sau-phát-hành).)

Phê duyệt là **trạng thái trên đĩa**, không phải câu trả lời trong một phiên
chat. Nó gắn với **băm nội dung** của tài liệu: sửa tài liệu sau khi duyệt thì
phê duyệt tự hết hiệu lực (`stale`), và duyệt lại tầng trên làm mọi tầng dưới
thành `stale`. Bạn không cần nhớ điều này — `aisef gates` luôn nói.

Ba câu bất biến, gặp lại nhiều lần trong hướng dẫn:

- **chưa cấu hình ≠ đạt** — không khai lệnh test thì mục cổng là ○, không phải ✅.
- **không chạy được ≠ trượt** — thiếu Docker là ⚠, không phải ✗.
- **chưa sửa ≠ không sửa được** — story trượt được ghi lại kèm lý do, không bị xoá.

---

## 2. Chuẩn bị máy

Bốn thứ, chỉ **hai** là bắt buộc.

| Thứ | Bắt buộc? | Kiểm bằng | Thiếu thì sao |
|---|---|---|---|
| Python ≥ 3.11 | **có** | `python3 --version` | không cài được gói |
| `git` | **có** | `git --version` | không chạy được `aisef run` (mỗi story cần một worktree riêng) |
| Một client agent: `claude` (khuyến nghị) hoặc `opencode` | **có, để chạy agent** | `claude --version` | các lệnh gọi agent dừng với mã 2 và câu "chưa cài claude trên máy này" |
| Docker | không | `docker info` | test chạy thẳng trên máy; framework ghi rõ là **suy biến** kèm tên bảo đảm thiếu |
| Playwright + Chromium | không, trừ khi dự án có giao diện | `npx playwright --version` | không trích được hợp đồng thị giác từ mockup |

Cài client Claude Code theo hướng dẫn của Anthropic, rồi đăng nhập một lần:

```bash
claude --version
```

Nếu lệnh này chưa chạy được thì mọi bước gọi agent bên dưới sẽ dừng — hãy làm
xong phần này trước.

---

## 3. Cài đặt

Nên cài trong môi trường ảo để không đụng Python hệ thống:

```bash
python3 -m venv ~/.venvs/aisef
source ~/.venvs/aisef/bin/activate
pip install aisef
```

Kiểm tra cài được:

```bash
aisef --help
```

Bạn phải thấy danh sách lệnh con (`setup`, `doctor`, `plan`, `run`, …). Gói,
module Python và lệnh đều tên `aisef`. `aisef --version` in số bản; muốn biết cả
môi trường thì dùng `aisef doctor`.

Nếu bạn từng cài bản 0.1.0 (lệnh khi đó tên `aisdlc`): bí danh cũ đã bị gỡ từ
0.3.0. Chạy `aisef compile` trong từng dự án để hook trỏ đúng tên mới.

Framework **không có phụ thuộc Python nào** ngoài thư viện chuẩn.

### Mười phút đầu tốn bao lâu — số đo, không phải ước lượng

Bấm đồng hồ ngày 12/09/2026 trên macOS (Darwin 25.5, Python 3.14.7, kho pip
**trống** để không ăn gian bằng cache):

| bước | lệnh | đo được |
|---|---|---|
| tạo môi trường ảo | `python3 -m venv .venv` | 2,0 s |
| cài | `pip install --no-cache-dir aisef` | 2,1 s |
| khởi tạo dự án | `aisef init --stack python` | 0,1 s |
| chẩn đoán | `aisef doctor` | 1,2 s |
| **viết `docs/requirements.md`** | — | **phần việc của người**, không đo được bằng máy |
| chẩn đoán lại | `aisef doctor` | 1,1 s → `✅ ready` |

Tức là **khoảng 6 giây máy**. "Mười phút" nằm gần như trọn ở một việc: viết ra
mình muốn gì. Một tệp `requirements.md` bốn dòng đủ để `doctor` chuyển sang
`✅ ready`.

Hai điều `doctor` nói ngay ở lần chạy đầu và **nên đọc kỹ**:

- `docker daemon — not running` và `sandbox provider — local`: công cụ chạy
  ngoài cách ly, bằng chứng bị đánh dấu *degraded*. Chạy thử thì được; nghiệm
  thu thật thì bật Docker.
- `tools.test` mà `init` ghi sẵn **không in coverage**, nên mục kiểm coverage
  của cổng ra "chưa cấu hình" cho tới khi bạn thêm plugin. Phần tên test thì
  preset đã có `-v` sẵn từ 1.3.1 — bản 1.3.0 thì chưa, và `doctor` sẽ nói.

Số khoá `init` ghi vào `.ai/config.json`: **4** (`tools.test`, `tools.lint`,
`sandbox.image`, `sandbox.allow_hosts`), trong đó **1 khoá bắt buộc khai** là
`tools.test`. Bản **1.3.0 trên PyPI ghi cả 68 khoá** — đúng bằng toàn bộ số khoá
mặc định *của bản 1.3.0*, đây là câu về **quá khứ**, không phải con số hiện tại
(1.7.2 có **70** khoá, xem [§17](#17-tra-cứu-toàn-bộ-khoá-cấu-hình)). Đã sửa từ
**1.3.1** và đo lại trên `1.7.2` ngày 2026-09-15:

```bash
aisef --project <dir> init --stack python
python3 -c "import json;print(list(json.load(open('<dir>/.ai/config.json'))))"
# → ['tools.test', 'tools.lint', 'sandbox.image', 'sandbox.allow_hosts']
```

Xem [§6](#6-cấu-hình-aiconfigjson).

Bản dành cho người muốn sửa framework:

```bash
git clone <repo> aisef && cd aisef && pip install -e .
python3 -m unittest discover -s tests -q
```

---

## 4. Tạo dự án và viết đầu vào

Framework làm việc **trong một thư mục dự án**. Thư mục ấy phải là một kho
git (vì mỗi story chạy trong một `git worktree` riêng).

```bash
mkdir ~/du-an/ghi-chu && cd ~/du-an/ghi-chu
git init
mkdir docs
```

Bây giờ viết đầu vào duy nhất: `docs/requirements.md`. Đây là **văn xuôi**,
bạn không cần theo khuôn mẫu nào — pha lập kế hoạch sẽ biến nó thành tài liệu
sản phẩm có mã `FR-1`, `FR-2`… Càng cụ thể thì càng ít câu hỏi mở về sau.

Ví dụ đầy đủ, đủ để chạy thật:

```markdown
# Ứng dụng ghi chú cá nhân

Một ứng dụng web chạy hoàn toàn trên máy người dùng, không có tài khoản,
không có máy chủ. Dữ liệu lưu trong trình duyệt.

## Người dùng và việc họ làm

Người dùng là một cá nhân ghi chú nhanh trong ngày. Họ cần tạo ghi chú, sửa
nội dung, tìm lại bằng từ khoá, và xoá thứ không cần nữa.

## Yêu cầu chức năng

- Tạo ghi chú mới với tiêu đề và nội dung.
- Sửa ghi chú, tự lưu sau khi ngừng gõ 800 mili giây.
- Xoá ghi chú, có bước xác nhận, có thùng rác giữ 7 ngày.
- Tìm toàn văn trên tiêu đề và nội dung, không phân biệt hoa thường và dấu.
- Danh sách ghi chú sắp theo lần sửa gần nhất.

## Ràng buộc

- Chạy được khi mất mạng.
- Không gửi dữ liệu ra ngoài máy.
- Trình duyệt hỗ trợ: bản mới nhất của Chrome, Firefox, Safari.

## Công nghệ mong muốn

React + TypeScript + Vite, kiểm thử bằng Vitest, kiểm thử đầu-cuối bằng Playwright.
```

Ba lời khuyên cho tệp này:

1. **Nói rõ ràng buộc** (ngoại tuyến, quyền riêng tư, trình duyệt) — chúng sẽ
   thành yêu cầu phi chức năng và được kiểm.
2. **Nói công nghệ nếu bạn có ý kiến.** Không nói thì agent tự chọn, và bạn
   khó phàn nàn về sau.
3. **Đừng viết thiết kế.** Đừng mô tả bảng cơ sở dữ liệu hay tên hàm; đó là
   việc của bước kiến trúc.

### Dự án **đã có code**: chạy `aisef baseline` trước

Bước lập kế hoạch chỉ đọc `docs/requirements.md` và **không đọc gì khác**. Trong
một thư mục đã có code, nó vì thế lập kế hoạch như thư mục trống. Đo trên một đợt
chạy thật: story đầu tiên là "Initialize Node.js project structure", với một tiêu
chí mở đầu bằng "Given a fresh directory with no files", cho một kho mà
`package.json` đã có sẵn đúng mọi trường tiêu chí ấy đòi. Test của nó xanh ngay ở
điểm nhánh, đối chứng nop từ chối đúng, và **ba lượt thử cùng mười tám phiên agent**
đi vào việc đã xong rồi.

Vì thế `aisef plan` cảnh báo trước khi tiêu tiền:

```
⚠️  this project already has files (…) and there is no `_bmad-output/baseline.md`.
   Planning reads only `docs/requirements.md`, so it will write stories for work
   that may already exist.
   Build the baseline first:  aisef baseline
```

Lệnh này đọc code hiện có và ghi `_bmad-output/baseline.md` cho bước lập kế hoạch.
Nó **không gọi model** — toàn bộ là code, nên không tốn tiền và chạy trong vài giây:

```bash
aisef baseline                  # dự án đã có code
aisef baseline --force          # bắt dựng baseline cả khi dự án trông như trống
aisef baseline --incremental    # cập nhật đồ thị, không dựng lại baseline
```

Đầu ra thật trên corpus dogfood `todo-cli`:

```
Baseline: 13 source · 6 test · config: package.json · langs: js(13)
  provider: basic
  wrote: .../_bmad-output/baseline.md
  103 lines
```

Dự án trống thì nó **từ chối và chỉ đúng chỗ**, không dựng một baseline rỗng:

```
Greenfield: 0 source files — use `aisef plan` instead of `aisef baseline`.
  (use --force to build baseline even for greenfield)
```

`--provider graphify|basic|auto` chọn bộ dựng đồ thị mã; `auto` (mặc định) dùng
Graphify nếu có, `basic` nếu không. `basic` chỉ dùng thư viện chuẩn.

---

## 5. `aisef setup` — nạp skill, sinh luật

```bash
aisef setup
```

Lệnh này: dò công nghệ dự án từ `docs/requirements.md`, chọn skill phù hợp từ
danh mục, **lọc bỏ skill tấn công**, cài chúng vào dự án, sinh `CLAUDE.md` và
`AGENTS.md` (luật mà agent phải theo), và ghi `.ai/config.json` mặc định.

Lần đầu chạy trên một máy, nó tải kho skill tham chiếu về
`~/.cache/aisef/references` (khoảng 91 MB theo `du -sh` ngày 15/09/2026, dùng chung cho mọi dự án). Máy
không có mạng:

```bash
aisef setup --no-fetch          # chỉ dùng thứ đã có trên đĩa
AISEF_REFERENCES=/duong/dan aisef setup   # trỏ sang kho đã tải sẵn
```

Muốn xem trước, không ghi gì:

```bash
aisef setup --dry-run
```

Kết thúc bạn sẽ thấy dòng tổng kết dạng `cài mới 152 · giữ nguyên 0 · gỡ 0`,
dòng `quy tắc: CLAUDE.md, AGENTS.md`, và đường dẫn `.ai/config.json` vừa ghi.
Chạy lại `aisef setup` **không** nhân bản skill.

Lưu ý quan trọng: `.ai/config.json` sinh ra với **mọi lệnh để trống**
(`tools.test`, `tools.lint`, `verify.*`). Framework cố ý không đoán lệnh test
của bạn — "chưa cấu hình" phải nhìn thấy được, chứ không được im lặng thành
"đạt". Bước kế tiếp là điền chúng.

---

## 6. Cấu hình `.ai/config.json`

Đây là bước hay bị bỏ qua nhất, và bỏ qua thì cổng sẽ báo ○ "chưa cấu hình"
suốt. Mở tệp `.ai/config.json` và khai **lệnh thật** của dự án bạn.

Bốn nhóm khoá cần quan tâm ngay:

| Khoá | Nghĩa | Ví dụ (React + Vitest) |
|---|---|---|
| `tools.test` | lệnh chạy test mà agent và cổng dùng | `npm test --silent` |
| `tools.lint` | lệnh lint / kiểm kiểu | `npx tsc --noEmit` |
| `verify.unit`, `verify.e2e`, … | lệnh của **từng loại kiểm định** ở bước 5 | `npx playwright test tests/e2e` |
| `app.dev_command`, `app.base_url` | cách mở ứng dụng để đối chiếu mockup và chạy e2e | `npm run dev -- --port 5199 --strictPort`, `http://localhost:5199` |

Ví dụ một cấu hình đủ dùng cho dự án React:

```json
{
  "tools.test": "npx vitest run --reporter=verbose --coverage",
  "tools.lint": "npx tsc --noEmit",
  "verify.unit": "npx vitest run --reporter=verbose",
  "verify.e2e": "npx playwright test tests/e2e",
  "verify.accessibility": "npx playwright test tests/a11y",
  "verify.perf": "npm run bench",
  "app.dev_command": "npm run dev -- --port 5199 --strictPort",
  "app.base_url": "http://localhost:5199",
  "coverage.min": 0.85,
  "run.max_retries": 2
}
```

Và cho dự án Python:

```json
{
  "tools.test": "python -m pytest -v --cov=src --cov-report=term",
  "tools.lint": "ruff check .",
  "verify.unit": "python -m pytest -v",
  "coverage.min": 0.85
}
```

Ba điều đáng biết ngay:

- **Lệnh test phải in ra tên từng test.** Cổng "tiêu chí có test" đọc tên test
  để biết tiêu chí nào đã được chứng minh. Vitest cần `--reporter=verbose`,
  pytest cần `-v`. Không in tên thì mục cổng là ○, không phải ✅.
- **Muốn có số coverage thì lệnh test phải in nó** (`--coverage` hoặc `--cov`);
  không in thì mục `coverage` là ○ kèm câu chỉ đúng chỗ sửa.
- **Loại kiểm định để trống nghĩa là "chưa cấu hình"**, và cổng trước triển khai
  sẽ chặn vì nó. Nếu loại ấy thật sự không áp dụng (ví dụ dự án không có API
  thì không có `api-contract`), hãy **miễn tường minh**:

```json
{
  "verify.waived": "api-contract,uat",
  "verify.waiver_reason": "2026-09-06, ứng dụng local-first không có backend nên hai loại này không áp dụng — người ký: Nghi"
}
```

Miễn mà không có lý do thì cổng chặn. Loại được miễn hiện ◇, **không bao giờ**
thành ✅ — bạn nhận trách nhiệm, không phải kiểm nó.

Toàn bộ khoá có ở [§17](#17-tra-cứu-toàn-bộ-khoá-cấu-hình).

---

## 7. `aisef compile` và `aisef doctor`

```bash
aisef compile
```

Sinh hook/plugin cho client, tức là nối **mười guard** của framework vào phiên
agent. Guard chạy ở phía framework, không phía client — client không được tin.

| Lúc nào | Guard | Chặn gì |
|---|---|---|
| trước mỗi lần agent dùng tool | `write-scope` | ghi ra ngoài phạm vi story được cấp |
| | `destructive` | lệnh phá huỷ (`rm -rf`, `git push`, đổi remote…) |
| | `secret` | ghi khoá API, token, private key vào tệp |
| | `git-stage` | tự ý stage/commit ngoài luồng |
| | `injection` | nội dung có chỉ dẫn tiêm vào agent |
| | `process-ref` | viết mã story/epic vào mã nguồn |
| | `egress` | kết nối tới host không khai trong `sandbox.allow_hosts` (`localhost` luôn được miễn). **Danh sách rỗng = không kiểm gì** — mặc định là rỗng |
| | `tool-bypass` | chạy thẳng lệnh test/lint/sast của dự án thay vì qua `aisef tool` |
| sau mỗi tool | `diff-scope` | thay đổi thực tế vượt phạm vi |
| khi agent định dừng | `completion` | dừng khi test chưa xanh sau lần sửa cuối |

Đây là danh sách máy in ra, không phải danh sách viết tay:

```bash
python3 -c "from aisef.harness.guardrails import GUARD_MATCHERS; print(len(GUARD_MATCHERS), sorted(GUARD_MATCHERS))"
# → 10 ['completion', 'destructive', 'diff-scope', 'egress', 'git-stage',
#       'injection', 'process-ref', 'secret', 'tool-bypass', 'write-scope']
```

Đầu ra thật của `aisef compile` trên một dự án vừa `init`, có cả hai client:

```
client: claude
  wrote .../.claude/settings.json
  guards blocking before action: destructive, egress, git-stage, injection, process-ref, secret, tool-bypass, write-scope
  guards blocking at other hooks: completion (Stop), diff-scope (PostToolUse)
client: opencode
  second-tier in V1: cost/turns not measurable from harness — supported, does not block release
  wrote .../.opencode/plugin/aisef-guard.ts
  guards blocking before action: destructive, egress, git-stage, injection, process-ref, secret, tool-bypass, write-scope
  guards blocking at other hooks: diff-scope (PostToolUse)
  ⚠️  guards post-hoc only: completion
     — not wired into this client's hooks at all; the rule is re-asked afterwards from evidence (story gate, `aisef verify`), which cannot stop the action, only fail the story
  capabilities not at native level:
     dir_allowlist: unsupported
     tool_allowlist: emulated
     turn_limit: unsupported
```

Hai điều đáng đọc kỹ trong khối trên:

- **`capabilities not at native level`** không phải lỗi. Nó nói: client này không
  tự giới hạn được vài thứ, nên framework ghi đúng mức bảo đảm nó đạt được thay
  vì giả vờ. Guard chính (chặn ghi sai phạm vi, chặn lệnh phá huỷ) vẫn chạy.
- **Trên OpenCode chỉ 9 trong 10 guard chặn tại nguồn.** API plugin của OpenCode
  không có chỗ chặn tương đương `Stop`, nên `completion` chỉ được hỏi lại **sau**
  từ bằng chứng: nó không ngăn được hành động, chỉ làm story trượt. Vì thế
  `blocks_at_source` trong `compile-report.json` báo `false` cho OpenCode — cờ ấy
  nghĩa là *tất cả* đều chặn tại nguồn, không phải *phần lớn*.

### `tool-bypass`: vì sao có guard này

Guard mới ở 1.6.0, và là guard dễ làm người dùng bối rối nhất, nên nó cần lý do
cụ thể. Trên `todo-cli`, qua **mười phiên liên tiếp**, agent gõ `npm test` mười
lần và `aisef tool test` **không lần nào**. Mọi sự kiện `test` trong bằng chứng
của story vì thế đến từ lượt kiểm của chính framework — một lần chạy xanh cho mỗi
ứng viên — nên phép "đỏ trước xanh sau" **không có gì để so**, và mục cổng `TDD`
trượt mười phiên liền trên một bản cài đặt vốn đã chạy được.

Luật mà chỉ prompt nói thì không phải luật. Guard nói ra đúng lệnh cần dùng:

```bash
python3 -c "
from aisef.harness.guardrails import check_tool_bypass
d = {'test': 'npm test', 'lint': 'npx eslint .'}
for c in ['npm test', 'npx eslint src/notes.js', 'git status']:
    v = check_tool_bypass(c, d)
    print(('ALLOW' if v.allowed else 'BLOCK'), '|', c)
"
# → BLOCK | npm test
# → ALLOW | npx eslint src/notes.js
# → ALLOW | git status
```

Lý do nó trả về khi chặn:

```
`npm test` is the project's test command run directly, so nothing about it is
recorded — and the gate reads evidence, not claims. Run `aisef tool test`
instead: it runs the same command and records the result, which is what the
`TDD`, `test` and `coverage` checks read. Narrowing a run for debugging (extra
arguments, a single file) is not blocked.
```

**Thu hẹp một lần chạy để gỡ lỗi thì không bị chặn** — chạy một tệp hay một tên
test là gỡ lỗi, không phải một khẳng định về cả bộ test, và ghi một tập con vào
bằng chứng dưới nhãn `test` sẽ làm một phần bộ test trông như cả bộ đã xanh.

Cách nhận diện "thu hẹp" phụ thuộc hình dạng lệnh bạn khai, và đây là chỗ dễ
ngạc nhiên — đo trên chính hàm ấy:

```bash
python3 -c "
from aisef.harness.guardrails import check_tool_bypass
for d, cs in [({'test': 'python -m pytest -v'},
               ['python -m pytest -v', 'python -m pytest -v tests/test_notes.py']),
              ({'test': 'npm test'},
               ['npm test', 'npm test -- tests/notes.test.js'])]:
    for c in cs:
        print(('ALLOW' if check_tool_bypass(c, d).allowed else 'BLOCK'), '|', c)
"
# → BLOCK | python -m pytest -v
# → ALLOW | python -m pytest -v tests/test_notes.py
# → BLOCK | npm test
# → ALLOW | npm test -- tests/notes.test.js
```

Với lệnh gọi thẳng (`pytest`, `npx vitest run …`) thì thêm đối số là một lệnh
khác và được cho qua. Với `npm`/`pnpm`/`yarn`/`bun` cũng vậy **kể từ lỗi 156**:
`npm test -- <tệp>` được cho qua, còn khác biệt **chỉ-cờ** (`npm test --silent`)
thì không — đó vẫn là chạy cả bộ, chỉ viết khác đi.

> **Sửa 2026-09-14 (lỗi 156).** Trước bản này, `_khoa_lenh` gộp trình gọi về
> `(trình gọi, script)` nên mọi đối số sau tên script bị xoá, và
> `npm test -- <tệp>` **bị chặn** — trong khi chính thông báo chặn mà người viết
> mã đọc được lại kết thúc bằng "Narrowing a run for debugging … is not blocked".
> Trên dự án Node, người viết mã do đó không còn nước đi hợp lệ nào để chạy hẹp
> mà gỡ lỗi: đúng lớp lỗi 118. Phép gộp vẫn giữ (để `npm test --silent` không
> lách được), nhưng nay phân biệt bằng **đối số vị trí** — token không mở đầu
> bằng `-` sau tên script, hay bất cứ thứ gì sau `--`.

Guard này chỉ áp dụng khi **có mã story** trong phiên. Phiên rà soát cố ý không
có mã story — `aisef tool test` cũng sẽ không ghi được gì cho nó — nên
`tool-bypass` không nổ trong phiên rà soát.

Một chi tiết đi kèm: `aisef tool test` **ngoài** một phiên story trước đây chạy
lệnh rồi không ghi gì mà vẫn in như một lần chạy đã ghi. Từ 1.6.0 nó nói rõ:

```
⚠️  not recorded as evidence: no story id — pass `--story <id>`
    (the harness sets AISEF_STORY_ID inside a story session)
```

Chạy `aisef compile` lại mỗi khi nâng cấp gói.

```bash
aisef doctor
```

Đọc từng dòng như sau:

- `✅` — đủ.
- `○` — thiếu thứ **tuỳ chọn**, kèm câu lệnh để cài. Ví dụ `○ playwright + chromium`
  chỉ ảnh hưởng dự án có giao diện.
- `✗` — thiếu thứ **bắt buộc**; dòng cuối sẽ nói `✗ thiếu: …`.

Dòng cuối cùng là kết luận: `✅ ready` hoặc danh sách thứ còn thiếu. (CLI in
tiếng Anh — hướng dẫn này là tiếng Việt, màn hình thì không.)

---

## 8. Bước lập kế hoạch: `aisef plan`

```bash
aisef plan
```

Lệnh này chạy **năm pha liên tiếp**, mỗi pha là một phiên agent và dừng lại ở
cổng người kế tiếp:

| Pha | Sinh ra tệp | Cổng chờ bạn duyệt |
|---|---|---|
| `project-context` | `project-context.md` | (không có cổng) |
| `prd` | `prd.md` | `prd` |
| `architecture` | `architecture.md` | `architecture` |
| `ux` | `DESIGN.md`, `EXPERIENCE.md` | `ux-spec` |
| `epics` | `epics.md` | `epics` |
| (chẻ story — code, không phải phiên agent) | `stories.index.json` + mỗi story một tệp | `stories` |

Năm pha là năm phiên agent; dòng cuối bảng **không** phải pha thứ sáu — nó là bước
chẻ story do code làm, không tốn tiền:

```bash
python3 -c "from aisef.phases.plan import PHASES; print([p.id for p in PHASES])"
# → ['project-context', 'prd', 'architecture', 'ux', 'epics']
```

Mọi tệp nằm trong thư mục `_bmad-output/` của dự án.

Khi lệnh dừng, xem cổng nào đang chờ:

```bash
aisef gates
```

Bảng hiện tám cổng, ví dụ ở một dự án vừa tạo:

```
Approval gates — <dự án>/_bmad-output

  ⏳ prd            pending              [missing: prd.md]
  ⏳ architecture   pending              [missing: architecture.md]
  ⏳ ux-spec        pending              [missing: DESIGN.md, EXPERIENCE.md]
  ⏳ epics          pending              [missing: epics.md]
  ⏳ stories        pending              [missing: stories.index.json]
  ⏳ mockups        pending              [missing: design-contract.json]
  ⏳ readiness      pending              [missing: stories.index.json, design-contract.json]
  ⏳ pre-deploy     pending              [missing: pre-deploy-report.json]

Next gate to handle: prd
  aisef review prd
```

Lệnh này trả **mã thoát 2** khi còn cổng chưa đạt — đúng như [§15](#15-xử-lý-sự-cố)
nói, `2` nghĩa "chưa sẵn sàng", không phải lỗi.

Bốn trạng thái: `pending` (chờ), `approved` (đã duyệt), `stale` (đã duyệt nhưng
tài liệu đổi sau đó, hoặc tầng trên vừa duyệt lại), `changes_requested` (bạn đã
trả lại kèm ghi chú). Dòng cuối luôn nói việc kế tiếp.

Đọc tài liệu của một cổng:

```bash
aisef review prd
aisef review prd --lines 200      # xem nhiều dòng hơn
```

Duyệt, hoặc trả lại kèm lý do:

```bash
aisef approve prd --note "đã đọc, đồng ý phạm vi"
aisef reject prd --note "thiếu yêu cầu xoá mềm; bổ sung FR về thùng rác"
```

Rồi chạy tiếp:

```bash
aisef plan
```

Lệnh `plan` luôn **chạy tiếp từ chỗ đang dở**, không làm lại pha đã có tài liệu.
Muốn ép làm lại một pha thì thêm `--force`.

Bạn nên đọc gì ở từng cổng:

- **`prd`** — danh sách `FR-…` có đúng thứ bạn muốn không, có thừa không. Đây
  là nơi rẻ nhất để cắt phạm vi.
- **`architecture`** — công nghệ và ranh giới module. Sai ở đây thì mọi story
  đều sai.
- **`ux-spec`** — `EXPERIENCE.md` liệt kê **màn hình**; số màn hình quyết định
  chi phí bước mockup.
- **`epics`** — chia epic và story; đọc để thấy thứ tự làm.
- **`stories`** — `stories.index.json` là thứ máy đọc: mỗi story có tiêu chí
  chấp nhận, `covers` (yêu cầu nó phủ), `write_scope` (thư mục nó được ghi),
  `depends_on`. Cổng máy đã kiểm: không có chu trình phụ thuộc, mọi `FR` đều
  có story phủ, không story nào vượt ngưỡng kích cỡ.

Chạy nhanh, không dừng ở cổng nào (chỉ nên dùng khi thử nghiệm):

```bash
aisef plan --auto-approve all
```

Phê duyệt tự động **luôn** bị đánh dấu `auto`, để sau này biết tài liệu nào
chưa từng có người thật đọc.

---

## 9. Bước mockup (dự án có giao diện)

Bỏ qua phần này nếu dự án không có giao diện.

```bash
aisef mockup
```

Mỗi màn hình trong `EXPERIENCE.md` thành một tệp HTML, được chụp màn hình, rồi
trích thành `design-contract.json` — **hợp đồng thị giác** mà story frontend
phải khớp. Chi phí thật khoảng 1,5–2,3 đô la mỗi màn hình, nên với 20 màn hình
hãy dựng theo đợt:

```bash
aisef mockup --only man-hinh-danh-sach,man-hinh-soan-thao
aisef mockup --force --only man-hinh-danh-sach      # dựng lại một màn
```

Duyệt hai cổng còn lại:

```bash
aisef review mockups
aisef approve mockups
aisef approve readiness
```

`readiness` là cổng chốt cuối cùng trước khi viết code — sau nó là tiền thật
và code thật.

---

## 10. Đọc cổng story: sáu kết cục

Khi một story chạy xong, framework in một bảng. Sáu ký hiệu, mỗi ký hiệu một
nghĩa **khác nhau**, và chỉ hai trong số đó chặn:

| Ký hiệu | Tên | Nghĩa | Có chặn story? |
|---|---|---|---|
| ✅ | PASSED | có bằng chứng, và bằng chứng nói đạt | không |
| ✗ | FAILED | có bằng chứng, và bằng chứng nói không đạt | **chặn** |
| ⚠ | UNRUNNABLE | không chạy được: thiếu công cụ, thiếu môi trường | **chặn** |
| ○ | UNCONFIGURED | chưa khai lệnh; **chưa cấu hình ≠ đạt** | không chặn story, nhưng chặn ở `pre-deploy` |
| ◇ | WAIVED | người miễn tường minh, có lý do ghi lại | không |
| – | NOT_APPLICABLE | không áp dụng (story không có giao diện…) | không |

Cổng story có **16 mục**, và mỗi mục được chứng nhận bằng **ba** đối chứng
(`positive` — nó có bắt được lỗi thật; `negative` — nó không báo động giả;
`env` — nó nói thật khi không chạy được), tức 48 ô chứng nhận:

```bash
python3 -c "from aisef.control.gate import qualification_table, CONTROLS; t=qualification_table(); print(len(t), CONTROLS, len(t)*len(CONTROLS))"
# → 16 ('positive', 'negative', 'env') 48
```

Đủ 16 mục, theo đúng thứ tự chúng in ra:

| Mục | Nó hỏi gì |
|---|---|
| `bằng chứng đúng candidate` | mọi kết quả kiểm có đúng là chạy trên bản code đang chấm không |
| `guard có chạy` | guard đã thật sự đánh giá thao tác ghi trong phiên chưa |
| `test` | lần chạy test cuối có xanh, và có sau lần sửa tệp cuối không |
| `không làm đỏ test có sẵn` | test đã xanh từ trước còn xanh và còn tồn tại không |
| `lint` | lint có sạch không |
| `phạm vi ghi` | story có ghi ra ngoài `write_scope` không |
| `map mockup` | màn hình thật có khớp hợp đồng thị giác không |
| `test thật` | có test nào rỗng khẳng định không |
| `tiêu chí có test` | mỗi tiêu chí chấp nhận có test mang mã của nó không |
| `coverage` | coverage có đạt `coverage.min` không |
| `TDD` | có test đỏ trước khi có code làm nó xanh không |
| `test có kiểm được story` | test ấy có **thật sự** kiểm phần story vừa viết không, hay chỉ gắn mã vào test cũ |
| `<loại>` | loại kiểm định story tự khai (e2e, accessibility…) có đạt không |
| `bảo mật` | phiên rà soát bảo mật có phát hiện mức cao không |
| `rà soát` | phiên rà soát độc lập có mục chặn nào không |
| `bảo toàn` | hành vi của story khác có bị story này làm hỏng không |

Trong 16 mục, **15 là máy chấm** (8 mục tất định, 6 mục cấu trúc, 1 mục bảo mật);
`rà soát` là mục **duy nhất** do model phán đoán. Điều đó quan trọng — xem ngay
dưới đây.

Mục `test có kiểm được story` hay làm người mới bối rối. Nó tồn tại vì một
cách gian dễ gặp: gắn mã tiêu chí vào một test **đã xanh từ trước** rồi bảo
"tiêu chí đã có test". Framework chạy một đối chứng: nếu test ấy vẫn xanh khi
chưa có phần cài đặt của story thì nó không chứng minh gì, và mục cổng ✗ kèm
tên test.

Từ 1.6.0, mục `TDD` **không còn chặn thứ mà đối chứng nop đã cho qua**: "đỏ trước
xanh sau" chỉ là phép đo gián tiếp cho câu hỏi "test này có kiểm được story
không", và đối chứng nop hỏi thẳng câu ấy. Khi nop đạt thì `TDD` đạt, kèm tên
bằng chứng đã chứng minh. Khi nop ra ⚠ / – / ○ thì nó chưa trả lời được, nên
`TDD` vẫn tự đứng.

### Mục `rà soát` **không** phải lưới an toàn

Đây là mục duy nhất một model phán đoán, và từ 1.6.0 chính nó cũng bị đem ra đo
bằng đúng ba đối chứng như các mục máy — 6 lớp phán đoán × 3 đối chứng = 18 ô nữa:

```bash
python3 -c "from aisef.control.reviewer_qual import qualification_table as q, CLASSES; print(len(q()), len(CLASSES)*3, CLASSES)"
# → 6 18 ('clean pass', 'miss', 'block corroborated', 'block uncorroborated', 'false block', 'undecided')
```

Số đo trên **145 phiên rà soát đã ghi** của bốn dự án dogfood — chấm lại bất cứ
lúc nào, không gọi model, không tốn tiền:

```bash
python3 -m aisef.control.reviewer_qual <dự-án-1>/_bmad-output <dự-án-2>/_bmad-output …
# → false block rate: 0.1053      (6 trong 57 lần chặn — đây là **sàn**, không phải ước lượng)
# → miss rate: 0.3857             (27 trong 70 lần cho qua; đọc nghiêm ngặt thì 34,3 % → nói thật là **34–39 %**)
# → undecided share: 0.1241       (không bao giờ được tính là "đạt")
# → same-tree consecutive pairs: 20
# → same-tree verdict reversals: 11
```

Đọc thẳng: **người rà soát bỏ sót 34–39 % ứng viên có lỗi**, và trên **20 lần rà
soát liên tiếp cùng một cây code y hệt nhau, 11 lần nó đổi kết luận**. Chặn sai
10,5 % là **sàn** — con số thật cao hơn, chỉ là phần còn lại không chứng minh được
từ bằng chứng trên đĩa.

Kết luận thực dụng cho bạn: **thứ giữ chất lượng là 15 mục máy chấm, không phải
mục `rà soát`.** Một `rà soát` ✅ không có nghĩa code đúng; một `rà soát` ✗ có
khoảng một phần mười khả năng là báo động giả. Nếu bạn đang tin cổng rà soát như
một lưới an toàn thì bạn đang tin sai chỗ — hãy khai đủ `tools.test`,
`tools.lint`, `verify.*` và `coverage.min`, vì đó là phần đo được.

---

## 11. Bước hiện thực: `aisef run`

```bash
aisef run
```

Chuyện xảy ra với **mỗi** story:

1. Framework tạo một `git worktree` riêng và một nhánh `story/<mã>`.
2. Mở một phiên agent **mới hoàn toàn** (không mang ngữ cảnh story trước).
3. Agent viết test đỏ trước, rồi code cho xanh; guard chặn ngay khi nó định
   ghi ra ngoài phạm vi.
4. Framework **đóng băng** bản code ấy (một SHA cụ thể) và chạy mọi phép kiểm
   trên đúng bản đó.
5. Một phiên **rà soát độc lập** đọc lại thay đổi; và một phiên rà soát bảo mật riêng.
6. Cổng story chấm. Đạt thì merge vào nhánh chính; không đạt thì thử lại tối đa
   `run.max_retries` lần, mỗi lần kèm lý do trượt cụ thể.

Các dạng chạy:

```bash
aisef run --epic EPIC-01        # chỉ một epic
aisef run --sequential          # tắt chạy song song (dễ đọc log hơn)
aisef run --force               # chạy dù cổng stories chưa duyệt (chỉ để thử)
```

Xem tiến độ và chi phí bất cứ lúc nào (lệnh này **không** tốn tiền):

```bash
aisef status
```

Dự án chưa chạy story nào thì nó nói thẳng `No stories registered.` Dự án đã chạy
thì nó in dạng dưới đây — đây là đầu ra thật trên corpus dogfood `todo-cli`, đã
cắt cho gọn:

```
Progress: 7/13 stories done (2 not started)
Active epics: EPIC-03, EPIC-04, EPIC-05, EPIC-06

  done        7
  failed      4

Cost: $0.00
Agent runs: ok 150 · infra 12 · max_turns 3

✗ 4 stories not passing:
    STORY-03-02      failed   deadlock due to plan: criteria AC-STORY-03-02-1, … are
                              already satisfied at the branch point — their tests pass
                              with the story's code absent, and a second session
                              confirmed it. Either another story already shipped this
                              behaviour (check the epic index) or the criteria describe
                              something the code already does. … fix the criteria or
                              drop the story, then re-run.
    STORY-05-02      failed   sessions kept producing nothing to grade: the session
                              wrote nothing (8 turns) — the tree is exactly as the
                              session found it, so the gate has nothing to grade.
                              Re-running it would return the verdict it already returned.
```

Ba dòng cần biết cách đọc:

- **`Cost: $0.00` không có nghĩa là miễn phí.** Nó có nghĩa nhà cung cấp không báo
  giá cho phiên nào. Muốn biết tiền đi đâu thì dùng `aisef cost` ([§14](#14-chi-phí-thật-và-cách-giảm)).
- **`Agent runs: ok 150 · infra 12 · max_turns 3`** chẻ riêng ba loại phiên: chạy
  xong, phiên mất vì client (502, rate limit, lời gọi tool CLI không đọc được), và
  phiên hết trần lượt. Chúng có cách xử khác nhau — xem ngay dưới.
- **Lý do trượt bây giờ nói ra chẩn đoán, không chỉ "đã thử 3 lần"** — `deadlock due
  to plan` và `sessions kept producing nothing to grade` là hai chẩn đoán mới ở
  1.6.0, và cả hai đều nói **bạn** phải sửa gì.

**Khi một story trượt**, làm theo thứ tự này:

```bash
aisef evidence STORY-01-03           # lịch sử: mục nào ✗, vì sao
aisef gate STORY-01-03               # chấm lại trên bằng chứng đã ghi, không gọi model
```

Rồi phân loại:

- **Trượt vì môi trường đo** (ví dụ test đầu-cuối nhạy tải máy): không cần trả
  tiền cho một phiên viết code mới, chỉ kiểm lại đúng bản đã có:

  ```bash
  aisef run --verify-only --story STORY-01-03 --repeat 3
  ```

  `--repeat 3` chạy mỗi phép kiểm ba lần; nếu kết quả đổi giữa các lần thì cổng
  ghi ⚠ "không ổn định" kèm tên test, thay vì kết tội story.

- **Trượt vì kế hoạch sai** (story thiếu quyền ghi vào tệp nó buộc phải sửa,
  tiêu chí mâu thuẫn): sửa `_bmad-output/stories.index.json` và tệp story, duyệt
  lại cổng `stories`, rồi chạy lại.

  Từ 1.6.0 framework **tự nhận ra và dừng sớm** dạng bế tắc phổ biến nhất thay vì
  đốt hết ngân sách: hai lượt chấm liền trượt `test có kiểm được story` trên cùng
  bộ tiêu chí thì nó dừng story ngay với chẩn đoán `deadlock due to plan` và nêu
  tên từng tiêu chí. Nguyên nhân gần như luôn là **một story trước đã làm xong
  hành vi ấy** — không test nào viết cho nó có thể đỏ ở điểm nhánh nữa. Sửa hoặc bỏ
  tiêu chí, đừng thử lại. (Đo trên một đợt chạy sáu epic: 4 trong 13 story chết vì
  đúng lý do này, nhiều hơn mọi nguyên nhân khác cộng lại.)

  Đi kèm: `aisef plan` bây giờ **cảnh báo** khi hai story trong cùng một epic khai
  y hệt một `write_scope` — chỉ cảnh báo, không chặn, vì chẻ một tệp thành hai
  story đôi khi là đúng. Và cổng `stories` **chặn** story nào có **không** tiêu chí
  nào, hoặc tiêu chí chỉ mô tả một bản nháp/giàn giáo ("not implemented"): một
  story như thế không nhỏ, nó là story **không kiểm được**.

  Còn một chuyện đáng biết khi bạn sửa tiêu chí: nhánh của lượt trước bị **bỏ**, và
  `run.log` nói ra. Framework lấy dấu tay của bộ tiêu chí mỗi lần chạy; tiêu chí
  đổi thì các commit cũ đang trả lời một câu hỏi không còn được hỏi nữa.
  `--verify-only` được miễn — nó chấm đúng ứng viên đang có.

- **Phiên không viết gì** (`sessions kept producing nothing to grade`): đây là một
  **quyết định**, không phải một lần chạy hỏng. Mở lại phiên với đúng ngữ cảnh ấy
  thì nó trả về đúng quyết định ấy, nên hai phiên không-viết-gì liên tiếp sẽ dừng
  story. Đọc `aisef evidence <story>` để biết nó thấy gì, rồi sửa kế hoạch.

- **Phiên hết trần lượt** (`max_turns` trong dòng `Agent runs`): từ 1.6.0 nó
  **được chấm** nếu có commit trong worktree, thay vì bị coi là phiên hỏng. Hết
  *lượt* không đồng nghĩa với viết code tệ — cổng sẽ nói; việc dở dang vẫn trượt
  `test`, `tiêu chí có test`, đối chứng nop và rà soát. Trước 1.6.0 những phiên này
  ăn hết ngân sách chất lượng mà không để lại kết luận cổng nào, nên lượt sau không
  có phản hồi gì để đọc.

- **Phiên mất vì client** (`infra` trong dòng `Agent runs`): 502, rate limit, lời
  gọi tool CLI không đọc được. Chúng không chấm điểm gì nên không tiêu tốn
  `run.max_retries`, nhưng **trước 1.6.0 chúng dùng chung ngân sách ấy** — chịu
  đựng một client hay rớt phiên đồng nghĩa với phải trả tiền cho thêm lượt chất
  lượng. Bây giờ có `run.infra_retries` riêng; mặc định `-1` giữ đúng cách ghép cũ.
  Chỉ nên tăng khi bạn **đã đo** tỉ lệ rớt phiên của client mình (đo được trên
  OpenCode/mycombo ngày 2026-09-13: 22–32 %).

- **Người rà soát không chạy được** (`REVIEW_UNRUNNABLE`, từ 1.7.4): các phép kiểm
  tất định xanh nhưng phiên rà soát kết thúc không có verdict — bị cắt ở
  `max_turns`, hết giờ, lỗi đường truyền, không đọc được verdict. Cổng ghi `review`
  ⚠ (không chạy được), **không** ✗; ứng viên được giữ nguyên đúng SHA đã đóng băng và
  chỉ **giai đoạn rà soát** được chạy lại trên chính SHA ấy, tối đa hai lần nữa.
  Không mở phiên developer cho việc này — developer không có gì để sửa. (Trước
  1.7.4 phiên developer bị mở lại ấy không viết gì, bị tính là no-op, hai lần thì
  story chết với `sessions kept producing nothing to grade` — D-032, lần chạy
  LedgerLock thứ hai tìm ra.) Nếu người rà soát vẫn không ra verdict, story kết thúc
  `REVIEW_UNRUNNABLE` kèm lỗi cuối; `aisef run --verify-only --story <mã>` chạy lại
  giai đoạn rà soát sau đó trên đúng ứng viên ấy, và `aisef run` thường sẽ tiếp
  tục story ấy từ giai đoạn rà soát. Verdict `block` có cấu trúc vẫn là verdict và
  vẫn trả story về developer.

- **Mốc "trước" của story là bất biến trong một epoch** (từ 1.7.5): mục `no
  baseline regression` so ứng viên với bộ test **ở cha tích hợp lúc story bắt
  đầu**. Mốc ấy chụp một lần cho mỗi hợp đồng story và được dùng lại khi thử lại,
  chạy tiếp hay `--verify-only` (`baseline REUSED` trong `run.log`); ứng viên do
  chính story tạo ra không bao giờ thành mốc của nó, nên đổi tên hay bỏ một test
  do story tự viết không phải hồi quy, còn mất một test đã có lúc story bắt đầu
  thì vẫn là. Mốc mới chỉ có khi tiêu chí đổi — nhánh bị bỏ và story chạy lại từ
  gốc. Nếu có bản ghi mốc nhưng không bản nào chụp ở cha cho hợp đồng hiện tại,
  mục ấy ra ⚠ `BASELINE_UNAVAILABLE` và chặn, thay vì lấy chính bản build của
  story làm mốc. (Trước 1.7.5 story chạy tiếp tự chụp mốc ở ứng viên cũ của
  mình, và một ứng viên đúng không thể qua — D-033, replay OpenCode của lần
  chạy LedgerLock thứ hai tìm ra.)

- **Trượt vì code sai**: để framework thử lại, hoặc chạy vòng cải tiến ở [§13](#13-vòng-cải-tiến-và-thay-đổi-sau-phát-hành).

Muốn biết mục cổng nào sẽ **đổi kết cục** nếu chấm lại bằng luật hiện tại — hữu ích
sau khi nâng cấp gói — thì dùng `aisef replay` (không gọi model, không tốn tiền):

```bash
aisef replay STORY-01-02
```

```
replay: re-score gate rules (gate.evaluate from current code) on recorded evidence
        and reviewer/security findings — no model calls

STORY-01-02 attempt 2 · candidate 4bf26de · recorded: FAIL · now: PASS
  check                            | recorded | now
  ...
  TDD                              |   ✗    | ✅ ≠
  tests verify story               |   ✅    | ✅
  ...
  diff: TDD
```

Dấu `≠` là chỗ luật đã đổi. Ví dụ trên là thật, lấy từ `todo-cli`: lượt ấy từng
trượt vì `TDD`, và luật 1.6.0 (nop đạt thì `TDD` đạt) cho nó qua. `aisef replay
--all` chấm lại mọi story có bằng chứng; `aisef gate <story> --replay` là lối vào
tương đương.

Muốn xem agent đang được cho những gì:

```bash
aisef ctx --story STORY-01-03        # bản đồ mã quanh phạm vi ghi
aisef skill --story STORY-01-03      # skill được định tuyến cho story
```

---

## 12. Kiểm định, đóng gói, nghiệm thu

```bash
aisef qa
```

Chạy toàn bộ loại kiểm định đã khai: `unit`, `sit`, `api-contract`, `e2e`,
`uat`, `perf`, `security`, `mutation`, `accessibility`, `migration`, `sbom`,
`image-scan`. Loại chưa khai lệnh hiện ○ và **không** được tính là đạt.

```bash
aisef qa --only unit,e2e             # chạy vài loại
aisef qa --story STORY-01-03         # ghi bằng chứng cho một story
```

Một trường hợp hay gặp và trước 1.6.0 bị báo sai: bạn khai
`verify.accessibility = "npx playwright test --grep @a11y"` nhưng chưa story nào
viết test `@a11y`. Lệnh ấy chạy được và **không tìm thấy test nào** — đó không
phải một test trượt. Bây giờ nó ra ⚠ (không chạy được) kèm lý do nêu cả hai khả
năng, chứ không còn báo mọi story là accessibility đã trượt:

```
the command matched no tests — it started and found nothing to run, which is not
a failing test. Either no story has written tests of this kind yet, or the
selector in the configured command matches nothing
```

⚠ vẫn **chặn** story — đó là kết cục trung thực: "chưa cấu hình ≠ đạt" và
"không chạy được ≠ trượt" là hai câu khác nhau, và cả hai đều không phải ✅.

Sinh tạo tác vận hành:

```bash
aisef devsecops
```

Sinh quy trình CI, `Dockerfile`, cấu hình triển khai và `docs/RUNBOOK.md`.
Runbook phải có đủ bốn mục: triệu chứng, chẩn đoán, xử lý, leo thang — thiếu
mục nào thì cổng cuối chặn.

Cổng cuối:

```bash
aisef pre-deploy
```

Nó chấm: mọi story đã xong, mọi cổng người đã duyệt, bộ kiểm định đạt, kiểm
định có chạy trong Docker không, có `Dockerfile`, có CI, có runbook.

Nghiệm thu **một phần** dự án (ví dụ chỉ epic đầu tiên):

```bash
aisef pre-deploy --epic EPIC-01
```

Story ngoài phạm vi khai được liệt kê là "ngoài phạm vi nghiệm thu" — **không
xong, cũng không thiếu**. Đây không phải nới cổng, mà là bắt bạn nói rõ mình
đang nghiệm thu cái gì; phạm vi được ghi vào báo cáo và phê duyệt gắn với nó.

```bash
aisef approve pre-deploy --note "nghiệm thu EPIC-01 theo báo cáo ngày …"
aisef report
```

`aisef report` sinh `docs/ACCEPTANCE-REPORT.md`: bảng truy vết yêu cầu → story
→ có test hay chưa, bảng cổng, chi phí, và sổ hành vi.

Tra một thứ cụ thể:

```bash
aisef evidence FR-3                  # đường đời một yêu cầu
aisef evidence AC-STORY-01-02-1      # một tiêu chí chấp nhận
aisef evidence qa:e2e                # một loại kiểm định
aisef issues --format csv            # bảng gap/hồi quy ra tệp
```

---

## 13. Vòng cải tiến và thay đổi sau phát hành

**Vòng cải tiến** đóng dần các khoảng trống (GAP) mà sổ hành vi ghi lại:

```bash
aisef improve --epic EPIC-01 --max-loops 3
```

Mỗi vòng: chạy kiểm định → đọc sổ hành vi → sinh **một** story sửa cho **một**
hành vi đang GAP → chạy story ấy như story thường → chạy lại kiểm định → ghi
`LOOP-REPORT-<n>.md`. Vòng dừng bằng code khi: hết gap, đủ số vòng, hai vòng
liền không cải thiện, vượt trần chi phí, hoặc story sửa bế tắc vì kế hoạch.

Trước mỗi vòng từ thứ hai, framework dừng lại hỏi bạn (`aisef approve improve`);
thêm `--auto` để không dừng.

### Một GAP nói rõ **loại vắng mặt** của nó (mới ở 1.6.0)

"GAP" từng là một nhãn duy nhất cho ba tình huống có giá tiền rất khác nhau. Từ
1.6.0 mỗi hành vi không-xanh mang thêm một `gap_kind`:

| `gap_kind` | Nghĩa | `improve` làm gì |
|---|---|---|
| `unbuilt` | không có gì đã hạ cánh chứng minh được hành vi: test đỏ, test xanh trên ứng viên chưa merge, phép kiểm dự án đỏ | một story sửa bình thường |
| `untested` | lần chạy đọc được, và **không** tên test nào mang mã này | một story **chỉ viết test**, phạm vi ghi *chính là* các đường dẫn kiểm định |
| `untraced` | harness **không nối được** hành vi → test: không đọc được tên test từ đầu ra runner, hoặc trace khai ra không có trong lần chạy ấy | **không** mở story nào |

`untraced` **không mở story trả tiền**, và đây là chỗ tiết kiệm thật. Đo trên bốn
corpus dogfood: 167 hành vi, 49 không xanh — **40 `unbuilt` · 4 `untested` ·
5 `untraced`** — và cả 5 `untraced` ấy là **toàn bộ tiêu chí của một story duy
nhất mà trình báo cáo test chưa được cài**. Nếu không chẻ ra, `improve` sẽ mở năm
story sửa trả tiền cho một lỗi cấu hình. Việc cần làm ở đó là sửa siêu dữ liệu:

```bash
aisef evidence AC-STORY-01-02-1 --link "<tên test>" --why "…"
```

`gap_kind` là **hình chiếu**, không phải trường bạn ghi tay: nó đọc lại đúng câu lý
do mà sổ hành vi vốn đã viết, nên `ledger.json` **không** có thêm khoá nào để sửa.
Loại không đoán được thì mặc định là `unbuilt` — gán nhầm một lỗi thật thành "sửa
siêu dữ liệu cho rẻ" sẽ che lỗi đi, chiều ngược lại chỉ tốn tiền.

Xem đếm theo loại bằng `aisef issues` (đầu ra thật trên `todo-cli`):

```bash
aisef issues
# → .../_bmad-output/ISSUES.md · 27 behaviours (5 regressions) · unbuilt 23 · untested 4 · untraced 0
```

**Đọc cẩn thận dòng ấy.** Ba loại phủ **mọi** hành vi không xanh, nên chúng cộng
lại bằng `gap + reopened`, **không** bằng `gap`. Đặt chúng cạnh riêng số `gap` sẽ
ra một dòng vô nghĩa. Cột `gap_kind` được **thêm vào cuối** bảng CSV, nên công cụ
theo dõi nào đang đọc theo vị trí cột vẫn đọc đúng như trước.

Một sửa lỗi đi kèm đáng biết nếu bạn commit `ledger.json`: trước 1.6.0 lý do của
một gap **đóng băng ở lần quan sát đầu**, nên `gap_kind` không bao giờ leo thang
được; và `ledger.json` chỉ được ghi lại bởi `aisef report` và vòng cải tiến, nên
giữa các đợt chạy nó đứng yên — sau một đợt sáu epic nó nói mọi hành vi đều là
`gap` trong khi hình chiếu từ bằng chứng có 34 `VERIFIED`. Tệp ấy là **hình chiếu**
mọi thứ đều dựng lại từ bằng chứng; bây giờ nó được làm mới khi đợt chạy kết thúc.

**Thay đổi yêu cầu sau khi đã phát hành**:

```bash
aisef change FR-3 "Slug phải giữ dấu gạch dưới"
```

Lệnh ghi thay đổi vào `docs/requirements.md`, đánh dấu cổng `prd` và mọi cổng
sau đó là `stale`, và sinh một story delta (`STORY-CH-01`) phủ đúng `FR-3`.
Story cũ **giữ nguyên** trạng thái `DONE` — lịch sử không bị viết lại.

---

## 14. Chi phí thật và cách giảm

Số đo thật trên một dự án ghi chú (client Claude Code):

| Việc | Chi phí |
|---|---|
| `project-context` | ~1,5 đô la |
| `prd` | ~1,9 đô la |
| `architecture` | ~2,8 đô la |
| `ux` | ~3,7 đô la |
| `epics` (18 story) | ~4,5 đô la |
| mockup, mỗi màn hình | 1,5–2,3 đô la |
| story backend, mỗi lượt thử | 2–2,7 đô la |

Hai điều đáng nhớ: lập kế hoạch tốn khoảng 14 đô la **trước khi có dòng code
nào**, và mockup đắt hơn cảm giác vì mỗi màn đọc lại toàn bộ tài liệu thiết kế.

Cách giảm:

- Chạy thử **một epic** trước khi chạy tất cả; số của dự án bạn không suy ra
  được từ bảng trên.
- Dựng mockup theo đợt bằng `--only`, duyệt sớm.
- Cắt phạm vi ở cổng `prd`, không cắt ở lúc đang chạy story.
- Đặt trần cho vòng cải tiến: `improve.cost_cap_usd`; trần cho cả đợt chạy:
  `run.cost_cap_usd`, `run.turn_cap`, `run.wall_clock_cap_seconds`.
- Story trượt vì môi trường thì dùng `--verify-only`, đừng chạy lại cả story.

### `aisef cost` — tiền **đã** đi đâu (mới ở 1.6.0)

`aisef status` cho bạn tổng số. `aisef cost` trả lời câu khác và khó hơn: **tiền
mua được gì**. Lệnh đọc bằng chứng đã ghi, **không gọi model**, nên chạy bao nhiêu
lần cũng miễn phí:

```bash
aisef cost                  # hoặc: aisef cost --out docs/COST.md
```

Đầu ra thật trên corpus dogfood `todo-cli`, cắt lấy phần quan trọng:

```
# Spend attribution — `todo-cli`

Unit: **input tokens** — the provider priced 0% of 165 sessions (0.00 USD recorded
in total), so dollars here would be invented. With `p` = price per 1M input tokens
and `q` = per 1M output:

    cost ≈ 17.80 × p + 0.309 × q

Cache reads are 84% of prompt tokens (90,821,604 cached vs 17,803,950 fresh); most
price lists charge them far less, so they are counted separately.

Net VERIFIED per M input tokens: **1.63**

34 verified · 22 gap · 5 reopened → net **29** behaviours for 17,803,950 across
165 sessions (1,653 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 27 | 244 | 716,654 | 4% |
| gate-blocked | 104 | 911 | 5,617,595 | 32% |
| turn-cap | 3 | 120 | 9,330,721 | 52% |
| env-failed | 12 | 205 | 283,322 | 2% |
| no-verdict | 6 | 94 | 1,412,859 | 8% |
| planning | 13 | 79 | 442,799 | 2% |

Spend on stories that ended with a net VERIFIED behaviour: **14%**.
```

**Phần hay nhất của lệnh này là chỗ nó từ chối.** Nó tự quyết đơn vị từ bằng chứng,
và **không** chịu bình quân một bản ghi tiền dở dang: ở `todo-cli` nhà cung cấp báo
giá cho **0 %** của 165 phiên, nên nếu in ra đô la thì con số ấy là **bịa**. Thay vì
thế nó chuyển đơn vị sang **token đầu vào** và đưa bạn công thức `cost ≈ 17,80 × p
+ 0,309 × q` để tự nhân với bảng giá của mình. Đơn vị được nêu **theo từng corpus**
và không bao giờ bình quân giữa các loại — ba trong bốn corpus dogfood có **0 %**
phiên được báo giá, corpus thứ tư là **1 %** của 180 phiên (tổng 0,79 đô la ghi
được). Bình quân bốn corpus lại với nhau thì con số đô la ấy là bịa đặt.

Nó cũng cảnh báo khi con số không so sánh được. Trên `todo-oc` (OpenCode), chỉ 4 %
prompt token là cache đọc lại:

```
⚠ At 4% cache, this client bills re-sent context as fresh `input`: the totals below
  are a sum over turns of the whole prompt and are **not** comparable with a corpus
  that caches.
```

Số đo nên đọc trước khi bạn quyết chi tiền cho một đợt chạy lớn — bốn corpus
dogfood, lấy trực tiếp từ hàng `passed`:

| corpus | `passed` | `gate-blocked` | `turn-cap` | `env-failed` |
|---|---:|---:|---:|---:|
| `todo-cli` | **4 %** | 32 % | 52 % | 2 % |
| `todo` | **16 %** | 44 % | — | 37 % |
| `todo-e2e` | **20 %** | 67 % | — | — |
| `todo-oc` | **22 %** | 46 % | 32 % | 0 % |

Nói thẳng: **chỉ 4–22 % chi phí mua được một lượt thử mà cổng cho qua**; 78–96 %
rơi vào những phiên chưa cổng nào cho qua. Nguyên nhân được **nêu tên**, không dồn
vào một ô "còn lại": hết trần lượt, story kết thúc với net ≤ 0, làm lại vì cổng
chặn, lỗi môi trường. Vòng thử lại của rà soát và bảo mật dưới **0,15 %** ở mọi
corpus — tức là chúng *không* phải chỗ tiền đi.

Bảng `Where the spend went` chính là bản đồ việc cần làm:

- **`turn-cap` cao** (52 % ở `todo-cli`, gom trong **3** phiên trên 165) — story quá
  lớn cho một phiên. Chẻ story; ngưỡng ở `story.max_complexity`.
- **`gate-blocked` cao** — làm lại vì cổng chặn. Đọc bảng `What the gate blocked on`
  mà lệnh in ngay bên dưới: nó xếp hạng mục cổng nào chặn nhiều nhất.
- **`env-failed` cao** (37 % ở `todo` so với 2 % ở `todo-cli`) — vấn đề môi trường
  của bạn, không phải chất lượng agent. Dựng Docker, sửa cổng, chạy `--verify-only`.
- **Bảng `Per story`** chỉ ra story nào ngốn tiền mà net = 0. Lưu ý dòng cảnh báo của
  chính lệnh: cột sổ hành vi **chồng nhau** giữa các story (một FR có thể do hai
  story phủ), nên chúng **không** cộng lại thành số của cả corpus.

---

## 15. Xử lý sự cố

Thông báo trong bảng này là **nguyên văn tiếng Anh** như CLI in ra.

| Bạn thấy | Nghĩa là | Làm gì |
|---|---|---|
| `✗ claude is not installed on this machine`, lệnh trả mã 2 | máy chưa có client agent | cài client, chạy `claude --version` cho tới khi được |
| `✗ docs/requirements.md` trong `aisef doctor` | chưa có đầu vào | tạo tệp theo [§4](#4-tạo-dự-án-và-viết-đầu-vào) |
| `⚠️ this project already has files … and there is no _bmad-output/baseline.md` | dự án đã có code mà chưa dựng baseline | `aisef baseline` **trước** khi `aisef plan` ([§4](#4-tạo-dự-án-và-viết-đầu-vào)) |
| Guard chặn `npm test` / lệnh test của bạn | `tool-bypass`: chạy thẳng thì không có gì được ghi | dùng `aisef tool test`; chạy hẹp thì gọi trực tiếp runner, đừng qua script npm ([§7](#7-aisef-compile-và-aisef-doctor)) |
| `⚠️ not recorded as evidence: no story id` | `aisef tool …` chạy ngoài một phiên story | thêm `--story <mã>` nếu bạn muốn nó thành bằng chứng |
| `deadlock due to plan: criteria … are already satisfied at the branch point` | một story trước đã làm xong hành vi ấy | **sửa hoặc bỏ tiêu chí**, đừng thử lại ([§11](#11-bước-hiện-thực-aisef-run)) |
| Mục cổng ⚠ `no baseline regression` — `BASELINE_UNAVAILABLE: …` | có bản ghi mốc nhưng không bản nào chụp ở cha tích hợp cho hợp đồng hiện tại của story (1.7.5) | chạy lại story từ gốc — `aisef run` bỏ nhánh khi tiêu chí đổi; không thêm hay khôi phục test để qua cổng |
| `REVIEW_UNRUNNABLE: the reviewer did not produce a verdict …` | phép kiểm tất định xanh; phiên rà soát không ra verdict sau ba lần trên cùng ứng viên (1.7.4) | không có gì phải sửa trong code — ứng viên được giữ. Xem client rà soát (`run.max_turns`, hết giờ, nhà cung cấp), rồi `aisef run --verify-only --story <mã>` chạy lại giai đoạn rà soát trên ứng viên ấy |
| `sessions kept producing nothing to grade` | phiên đã **quyết định** không viết gì, hai lần liền | đọc `aisef evidence <story>`, sửa kế hoạch — mở lại phiên sẽ ra đúng kết quả ấy |
| `the command matched no tests` | lệnh chạy được nhưng bộ chọn không khớp test nào | chưa story nào viết loại test ấy, hoặc bộ chọn sai — sửa `verify.<loại>` |
| `Cost: $0.00` trong `aisef status` | nhà cung cấp không báo giá phiên nào | dùng `aisef cost`: nó đổi sang token và cho công thức ([§14](#14-chi-phí-thật-và-cách-giảm)) |
| `infra` cao trong dòng `Agent runs` | client rớt phiên (502, rate limit, tool call không đọc được) | đã **đo** tỉ lệ rớt thì đặt `run.infra_retries`; đừng tăng `run.max_retries` |
| `aisef gates` báo `stale` | tài liệu đổi sau khi duyệt, hoặc tầng trên vừa được duyệt lại | đọc lại rồi `aisef approve <cổng>` |
| Cổng `stories` không cho chạy | cổng máy đã bắt lỗi kế hoạch | đọc lý do, sửa `stories.index.json`, duyệt lại |
| Mục cổng ○ `coverage` | lệnh test không in số coverage | thêm `--coverage` (vitest/c8) hoặc `--cov` (pytest) vào `tools.test` |
| Mục cổng ○ `tiêu chí có test` | runner không in tên test | thêm `--reporter=verbose` (vitest) hoặc `-v` (pytest) |
| Mục cổng ✗ `test có kiểm được story` | test chỉ gắn mã vào test có sẵn | yêu cầu story viết test mới cho tiêu chí; nếu test cũ thật sự đã chứng minh đủ thì khai truy vết: `aisef evidence <mã> --link "<tên test>" --why "…"` |
| Mục cổng ⚠ kèm "không chạy được" | thiếu công cụ hoặc môi trường | dựng môi trường rồi chạy lại; **không** đổi ngưỡng để cho qua |
| Kiểm định báo "suy biến" | chạy ngoài Docker, thiếu vài bảo đảm | dựng Docker; hoặc khai `sandbox.pre_deploy_degraded_waiver` với lý do thật |
| `Port ... is already in use` khi chạy e2e | một tiến trình dev cũ còn sống | tìm và tắt nó (`lsof -nP -i :5199`), rồi chạy lại |
| Story `blocked` sau nhiều lượt | thường là kế hoạch sai, không phải code sai | đọc `aisef evidence <story>`, sửa story/phạm vi ghi, duyệt lại cổng `stories` |
| Merge conflict cuối đợt | hai story khai `write_scope` chồng nhau | đó là tín hiệu kế hoạch sai — tách phạm vi rồi chạy lại |
| Chi phí một story cao bất thường | story quá lớn cho một phiên | chẻ story; ngưỡng kích cỡ ở `story.max_complexity` |

Mã thoát của mọi lệnh: `0` xong, `1` bạn gọi sai hoặc thiếu đầu vào, `2` chưa
sẵn sàng (cổng chưa đạt, thiếu công cụ).

---

## 16. Tra cứu: toàn bộ lệnh

Mọi lệnh nhận `--project <thư mục>` (mặc định: thư mục hiện tại). Danh sách đầy đủ
`aisef --help` in ra **34 lệnh con**; 33 lệnh dưới đây là của một dự án, lệnh thứ 34 — `aisef closure` — chấm cổng đóng dự án của chính kho framework, mô tả ở `docs/SOLUTION.md` và `docs/PROJECT-CLOSURE-GATE.md`. `aisef --help` luôn là bản chuẩn:

```bash
aisef --help
```

**Chuẩn bị**

```bash
aisef doctor                              # kiểm môi trường
aisef setup [--references DIR] [--no-fetch] [--dry-run]
aisef init [--stack react|python|go|node] # ghi .ai/config.json mặc định (4 khoá)
aisef compile [--client claude|opencode|all] [--bin PATH]
aisef baseline [--provider graphify|basic|auto] [--force] [--incremental]
```

**Lập kế hoạch và cổng người**

```bash
aisef plan [--client c] [--auto-approve all|<danh sách>] [--force]
aisef mockup [--client c] [--only <screen_id>] [--auto-approve ...] [--force]
aisef gates
aisef review <cổng> [--lines N]
aisef approve <cổng> [--note "..."] [--force]
aisef reject <cổng> --note "..."
aisef auto-approve all|<danh sách>
```

**Hiện thực**

```bash
aisef run [--client c] [--epic E] [--sequential] [--no-isolate] [--force]
aisef run --verify-only --story S [--repeat K]
aisef improve --epic E [--max-loops N] [--auto] [--client c] [--force]
aisef tool test|lint|sast [--story S] [--lines N]
aisef verify [--write-scope ...] [--story S]
aisef gate <story> [--attempt n] | --all | --replay
aisef replay [<story> | --all] [--attempt n]   # lối vào riêng của `gate --replay`
aisef guard <tên guard>                   # framework tự gọi qua hook
```

`aisef guard` nhận đúng mười tên: `completion`, `destructive`, `diff-scope`,
`egress`, `git-stage`, `injection`, `process-ref`, `secret`, `tool-bypass`,
`write-scope`.

**Kiểm định và phát hành**

```bash
aisef qa [--only <loại>] [--story S] [--story-level]
aisef devsecops [--client c] [--install-spec X] [--bin PATH] [--force]
aisef pre-deploy [--skip-qa] [--epic E]
```

**Quan sát**

```bash
aisef status [--attempts]
aisef cost [--out FILE]                   # tiền đi đâu, chẻ theo kết cục (§14)
aisef dashboard [--out FILE] [--projects DIR ...]   # HTML hợp quy, gộp nhiều dự án
aisef report [--out FILE]
aisef evidence <id> [--story S] [--link TEST --why "..." --by ai]
aisef issues [--format md|csv] [--epic E] [--status gap,reopened] [--out FILE]
aisef ctx [--story S | --file F] [--budget N]
aisef skill [--story S] [--scan --client c --batch N]
aisef doc <gói> [--topic T] [--tokens N] [--story S]
aisef change FR-x "mô tả"
```

Không lệnh nào trong nhóm này gọi model, nên chạy bao nhiêu lần cũng không tốn tiền
(`aisef doc` có gọi mạng — HTTP tới context7, có cache — nhưng không gọi model).
`aisef dashboard` in ra đầu ra thật như sau (trên `todo-cli`):

```
dashboard: .../dashboard.html

Vận hành:
  chi phí/tuần   — nhà cung cấp không báo chi phí (mọi sự kiện $0)
  VERIFIED ròng  34 (— (chi phí $0))
  gap tồn        27 · unbuilt 23 · untested 4
  tuổi hợp quy   6 ngày (trần 14) ✅
```

Dòng **`tuổi hợp quy`** là thứ đáng nhìn: bảng hợp quy client có hạn dùng **14
ngày**. Quá hạn thì bảo đảm "client này chặn được ngần này thứ" là số cũ, và
dashboard nói ra.

**Bộ nhớ (đóng băng, mặc định TẮT)**

```bash
aisef memory status|recall|search|show|capture|consolidate|audit|forget|providers
```

`aisef memory` **đóng băng** theo phụ lục ADR-007 ngày 2026-09-12: code còn đó, lỗi
và lỗ bảo mật vẫn được sửa, **không thêm năng lực mới**. Nó không phải "thử nghiệm,
sắp có". Bộ nhớ **không bao giờ** là bằng chứng cho cổng. Chi tiết ở
[MEMORY.md](MEMORY.md).

---

## 17. Tra cứu: toàn bộ khoá cấu hình

Giá trị trong ngoặc là mặc định.

**Kiểm định và ngưỡng**

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `tools.test` · `tools.lint` · `tools.sast` | `""` | lệnh thật của dự án; rỗng nghĩa là chưa cấu hình |
| `verify.<loại>` (12 loại) | `""` | lệnh cho từng loại kiểm định |
| `verify.waived` | `""` | loại được miễn, ngăn bởi dấu phẩy |
| `verify.waiver_reason` | `""` | lý do miễn; bắt buộc khi có miễn |
| `verify.baseline` | `true` | chạy test ở bản gốc trước khi story sửa, để biết test nào vốn đã xanh |
| `verify.nop` | `true` | bật đối chứng "test có kiểm được story" |
| `verify.clean_tree` | `true` | kiểm định cấp dự án chạy ở worktree sạch dựng từ SHA |
| `coverage.min` | `0.85` | ngưỡng coverage |
| `security.block_severities` | `["critical","high"]` | mức phát hiện bảo mật đủ để chặn |
| `security.semantic_review` | `true` | bật phiên rà soát bảo mật riêng |

**Kích cỡ story**

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `story.max_acceptance_criteria` | `8` | trần số tiêu chí một story |
| `story.max_write_scope_paths` | `10` | trần số đường dẫn trong phạm vi ghi |
| `story.max_screen_states` | `8` | trần số trạng thái màn hình |
| `story.max_complexity` | `16.0` | điểm phức tạp tối đa; vượt thì cổng chặn và đòi chẻ story |
| `story.verified_touched_weight` | `0.0` | bán kính mục `bảo toàn`: trọng số của hành vi VERIFIED chỉ *chạm* tệp mà story sửa. **Đừng tăng mà không có bảng đo riêng** — xem dưới |

`story.verified_touched_weight` là khoá mới ở 1.6.0 và mặc định **0**, có chủ ý. Bảng
hiệu chỉnh nằm ngay cạnh nó trong `aisef/config.py`, sinh lại từ bằng chứng bằng
`validation/o3_preservation_radius.py`. Đo được: **không** trọng số nào ≤ 1,0 làm đổi
một kết luận nào; kết luận **đầu tiên** bị đổi khi tăng lên trên 1,0 lại là một lần
**chặn sai**; bắt được 11 trong 15 story thật sự gây hồi quy thì phải chặn oan 7
trong 17 story sạch. Phát hiện quan trọng hơn cả hệ số: **27 trong 32 story có chồng
tệp**, nên số tệp chồng nhau không xếp hạng được 47 % story gây hồi quy. Đó là vấn đề
của *vị từ* — `bảo toàn` cần được khoanh theo **hành vi** — không phải vấn đề trọng số.

**Chạy**

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `run.max_parallel` | `3` | số story chạy song song |
| `run.max_turns` | `40` | trần số lượt trong một phiên agent; từ 1.7.3 lệnh dừng giết cả cây tiến trình (shim `opencode.CMD` trên Windows từng chết mà node vẫn chạy) |
| `run.timeout_seconds` | `1800` | trần thời gian một phiên |
| `run.max_retries` | `2` | số lần thử lại một story (lượt **chất lượng**) |
| `run.infra_retries` | `-1` | ngân sách thử lại riêng cho **phiên mất vì client** (502, rate limit, tool call không đọc được). `-1` giữ cách ghép cũ: dùng chung ngân sách với `run.max_retries`. Chỉ tăng khi đã **đo** tỉ lệ rớt phiên của client mình |
| `run.cost_cap_usd` | `0.0` | trần chi phí cả đợt chạy; `0` là tắt |
| `run.turn_cap` | `0` | trần tổng số lượt cả đợt chạy; `0` là tắt |
| `run.wall_clock_cap_seconds` | `0.0` | trần thời gian thực cả đợt chạy; `0` là tắt |
| `run.qualify_preflight` | `false` | chạy chính sách chứng nhận trước lượt thử đầu tiên (tuỳ chọn, mặc định tắt) |
| `cost.warn_multiple` | `3.0` | cảnh báo khi một story tốn hơn ngần này lần trung vị |

**Ứng dụng và mockup**

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `app.dev_command` | `""` | lệnh mở ứng dụng để đối chiếu màn hình |
| `app.base_url` | `http://localhost:5173` | địa chỉ ứng dụng |
| `app.ready_timeout_seconds` | `60` | chờ ứng dụng sẵn sàng bao lâu |

**Cách ly**

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `sandbox.provider` | `"docker"` | nơi chạy lệnh: `docker` hoặc `local` |
| `sandbox.use_docker` | `true` | dùng container cho tool |
| `sandbox.allow_degraded` | `true` | cho phép chạy khi thiếu bảo đảm, có ghi rõ |
| `sandbox.image` | `""` | ảnh container. Preset python đặt ảnh do khung **tự dựng** và ghim (`aisef-verify-python:<digest>`: `python:3.12-slim` ghim theo digest + pytest, pytest-cov, ruff ghim theo phiên bản) vì `python:3.12-slim` trơn không có pytest; `aisef doctor` dựng ảnh và dò từng công cụ đã khai ngay trong ảnh, `aisef run` từ chối mở phiên khi ảnh đã khai thiếu công cụ đã khai (1.7.3) |
| `sandbox.allow_hosts` | `[]` | host mà tool được phép kết nối tới (`egress` đọc danh sách này; `localhost` luôn được miễn) |
| `sandbox.tools_network` | `false` | cho tool ra mạng hay không |
| `sandbox.pre_deploy_degraded_waiver` | `""` | lý do chấp nhận kiểm định chạy ngoài Docker ở cổng cuối |

**Ngữ cảnh, vòng cải tiến, client**

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `context.max_index_chars` | `2000` | trần ký tự cho chỉ mục bằng chứng nạp vào prompt |
| `context.max_preservation_chars` | `1200` | trần ký tự cho danh sách hành vi phải giữ |
| `context.max_repo_map_chars` | `0` | trần cho bản đồ mã; `0` là tắt |
| `context.map_provider` | `""` | lệnh ngoài dựng bản đồ mã (nhận JSON qua stdin, in text). Rỗng = bản dựng sẵn bằng thư viện chuẩn; lệnh lỗi thì quay về bản dựng sẵn và nói rõ là thô |
| `context.graph_provider` | `"auto"` | bộ dựng đồ thị mã cho dự án đã có code: `auto`, `graphify`, `basic` |
| `review.impact_provider` | `""` | lệnh ngoài phân tích tác động cho phiên rà soát |
| `improve.max_loops` | `3` | số vòng cải tiến tối đa cho một epic |
| `improve.flat_loops` | `2` | dừng khi ngần này vòng liền không cải thiện |
| `improve.cost_cap_usd` | `0.0` | trần chi phí vòng cải tiến; `0` là không giới hạn |
| `route.developer_model` · `route.reviewer_model` · `route.designer_model` · `route.security_model` | `""` | ép model cho từng vai |
| `clients.env_allow` | `[]` | biến môi trường được phép truyền vào phiên agent |
| `skills.offer` | `false` | gợi ý skill cho agent; đo chưa thấy lợi nên tắt. Cơ chế thứ hai (`skills.inline`) đã **gỡ** ở 1.4.0 sau hai lần A/B cho `used` 0/0 |
| `memory.*` (6 khoá) | TẮT | bộ nhớ đóng băng, mặc định TẮT — [MEMORY.md](MEMORY.md) |

Tổng số khoá là **69** ở 1.6.0. Đây là số máy đếm, không phải số viết tay:

```bash
python3 -c "from aisef.config import DEFAULTS; print(len(DEFAULTS))"   # → 69
```

---

## 18. Thuật ngữ

- **Story** — một đơn vị công việc có tiêu chí chấp nhận, phạm vi ghi và phụ
  thuộc riêng. Mỗi story chạy trong một phiên agent mới.
- **Epic** — nhóm story. Epic chạy tuần tự, story trong epic chạy song song
  khi phạm vi ghi không chồng nhau.
- **Tiêu chí chấp nhận (AC)** — câu mô tả điều kiện đạt của story, được đánh mã
  `AC-<story>-<số>` và phải xuất hiện trong tên test.
- **Ứng viên (candidate)** — bản code cụ thể (một SHA) mà mọi phép kiểm chạy
  trên đó. Bằng chứng không gắn ứng viên thì không chứng minh cho bản nào.
- **Cổng máy / cổng người** — xem [§1](#1-framework-này-làm-gì).
- **Sổ hành vi (ledger)** — bảng theo dõi từng hành vi: `VERIFIED` (đã chứng
  minh), `GAP` (chưa), `REOPENED` (từng đúng, nay hỏng lại). Mọi hành vi không
  xanh còn mang một **`gap_kind`**: `unbuilt` (chưa làm), `untested` (đã làm,
  chưa có test mang mã), `untraced` (harness không nối được hành vi → test).
  Chỉ hai loại đầu mở story trả tiền — xem [§13](#13-vòng-cải-tiến-và-thay-đổi-sau-phát-hành).
- **Bằng chứng (evidence)** — tệp `.jsonl` ghi mọi lần chạy tool, phiên agent,
  kết luận cổng. Đây là thứ mọi báo cáo đọc lại, không phải lời agent.
- **Guard** — lệnh của framework chặn thao tác sai ngay trước khi nó xảy ra.
- **Suy biến (degraded)** — chạy được nhưng thiếu vài bảo đảm cách ly; luôn
  được nêu tên bảo đảm thiếu, không im lặng.
- **Miễn tường minh (waiver)** — người nhận trách nhiệm cho một loại kiểm định
  không chạy, kèm lý do ghi vào bằng chứng. Hiện ◇, không bao giờ thành ✅.
- **Worktree** — bản sao cây làm việc riêng của một story, để hai story chạy
  song song không giẫm lên nhau.

---

Tài liệu liên quan trong kho: `README.md` (tóm tắt, tiếng Anh) và `README.vi.md` (bản tiếng Việt), `docs/SOLUTION.md` (thiết
kế đầy đủ), `docs/FAILURE-TAXONOMY.md` (lỗi thật đã gặp và cách chặn tái diễn),
`CHANGELOG.md` (đổi gì giữa các phiên bản, và phải làm gì khi nâng cấp).
