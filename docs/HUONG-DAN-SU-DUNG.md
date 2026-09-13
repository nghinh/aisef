# Hướng dẫn sử dụng AISEF

[Bộ nhớ dài hạn thử nghiệm](MEMORY.md): `aisef memory` mặc định TẮT. Hướng dẫn gồm cấu hình, CLI, nguồn/phạm vi, bảo mật và giới hạn benchmark; bộ nhớ không phải bằng chứng cho cổng. Tham khảo: [nghiên cứu/kế hoạch](MEMORY-RESEARCH-PLAN.md), [báo cáo kiểm thử](MEMORY-VALIDATION.md), [ADR-007](ADR-007-scoped-advisory-memory.md).

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
- **Cổng người**: bạn đọc và ký. Có **tám** cổng, theo đúng thứ tự:
  `prd → architecture → ux-spec → epics → stories → mockups → readiness → pre-deploy`.

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
`tools.test`. Bản **1.3.0 trên PyPI ghi cả 68 khoá**; đã sửa từ **1.3.1** và
đo lại trên `1.5.0` ngày 2026-09-14 — `aisef --project <dir> init --stack python`
ghi đúng 4 khoá ấy. (Câu này từng nói "sẽ có ở bản kế"; ba bản đã ra từ đó.) Xem
[§6](#6-cấu-hình-aiconfigjson).

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

---

## 5. `aisef setup` — nạp skill, sinh luật

```bash
aisef setup
```

Lệnh này: dò công nghệ dự án từ `docs/requirements.md`, chọn skill phù hợp từ
danh mục, **lọc bỏ skill tấn công**, cài chúng vào dự án, sinh `CLAUDE.md` và
`AGENTS.md` (luật mà agent phải theo), và ghi `.ai/config.json` mặc định.

Lần đầu chạy trên một máy, nó tải kho skill tham chiếu về
`~/.cache/aisef/references` (khoảng 93 MB, dùng chung cho mọi dự án). Máy
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

Sinh hook/plugin cho client, tức là nối **tám guard** của framework vào phiên
agent. Guard chạy ở phía framework, không phía client — client không được tin.

| Lúc nào | Guard | Chặn gì |
|---|---|---|
| trước mỗi lần agent dùng tool | `write-scope` | ghi ra ngoài phạm vi story được cấp |
| | `destructive` | lệnh phá huỷ (`rm -rf`, `git push`, đổi remote…) |
| | `secret` | ghi khoá API, token, private key vào tệp |
| | `git-stage` | tự ý stage/commit ngoài luồng |
| | `injection` | nội dung có chỉ dẫn tiêm vào agent |
| | `process-ref` | viết mã story/epic vào mã nguồn |
| sau mỗi tool | `diff-scope` | thay đổi thực tế vượt phạm vi |
| khi agent định dừng | `completion` | dừng khi test chưa xanh sau lần sửa cuối |

Cuối lệnh nó in một báo cáo năng lực, ví dụ:

```
  năng lực không đạt mức native:
     dir_allowlist: unsupported
     tool_allowlist: emulated
     turn_limit: unsupported
```

Đây **không phải lỗi**. Nó nói: client này không tự giới hạn được vài thứ, nên
framework ghi đúng mức bảo đảm nó đạt được thay vì giả vờ. Guard chính (chặn
ghi sai phạm vi, chặn lệnh phá huỷ) vẫn chạy.

Chạy `aisef compile` lại mỗi khi nâng cấp gói.

```bash
aisef doctor
```

Đọc từng dòng như sau:

- `✅` — đủ.
- `○` — thiếu thứ **tuỳ chọn**, kèm câu lệnh để cài. Ví dụ `○ playwright + chromium`
  chỉ ảnh hưởng dự án có giao diện.
- `✗` — thiếu thứ **bắt buộc**; dòng cuối sẽ nói `✗ thiếu: …`.

Dòng cuối cùng là kết luận: `✅ sẵn sàng` hoặc danh sách thứ còn thiếu.

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
| `stories` | `stories.index.json` + mỗi story một tệp | `stories` |

Mọi tệp nằm trong thư mục `_bmad-output/` của dự án.

Khi lệnh dừng, xem cổng nào đang chờ:

```bash
aisef gates
```

Bảng hiện tám cổng, ví dụ ở một dự án vừa tạo:

```
  ⏳ prd            pending              [thiếu: prd.md]
  ⏳ architecture   pending              [thiếu: architecture.md]
  ⏳ ux-spec        pending              [thiếu: DESIGN.md, EXPERIENCE.md]
  ⏳ epics          pending              [thiếu: epics.md]
  ⏳ stories        pending              [thiếu: stories.index.json]
  ⏳ mockups        pending              [thiếu: design-contract.json]
  ⏳ readiness      pending              [thiếu: stories.index.json, design-contract.json]
  ⏳ pre-deploy     pending              [thiếu: pre-deploy-report.json]

Cổng kế tiếp cần xử lý: prd
  aisef review prd
```

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

Các mục cổng bạn sẽ gặp nhiều nhất:

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
| `test có kiểm được story` | test ấy có **thật sự** kiểm phần story vừa viết không, hay chỉ gắn mã vào test cũ |
| `rà soát` | phiên rà soát độc lập có mục chặn nào không |
| `bảo mật` | phiên rà soát bảo mật có phát hiện mức cao không |
| `bảo toàn` | hành vi của story khác có bị story này làm hỏng không |

Mục `test có kiểm được story` hay làm người mới bối rối. Nó tồn tại vì một
cách gian dễ gặp: gắn mã tiêu chí vào một test **đã xanh từ trước** rồi bảo
"tiêu chí đã có test". Framework chạy một đối chứng: nếu test ấy vẫn xanh khi
chưa có phần cài đặt của story thì nó không chứng minh gì, và mục cổng ✗ kèm
tên test.

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

Dự án chưa chạy story nào thì nó nói thẳng `Chưa có story nào được đăng ký.`
Dự án đang chạy thì nó in dạng:

```
Tiến độ: 10/12 story xong
Epic hiện tại: EPIC-RP-01

  done        10
  failed      2

Chi phí: $254.11
⚠️  1 story tốn hơn 3.0× trung vị:
    STORY-01-04      $79.67

✗ 2 story chưa qua được:
    STORY-RP-04      failed   đã thử 3 lần vẫn không qua cổng
```

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

- **Trượt vì code sai**: để framework thử lại, hoặc chạy vòng cải tiến ở [§13](#13-vòng-cải-tiến-và-thay-đổi-sau-phát-hành).

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
- Đặt trần cho vòng cải tiến: `improve.cost_cap_usd`.
- Story trượt vì môi trường thì dùng `--verify-only`, đừng chạy lại cả story.

---

## 15. Xử lý sự cố

| Bạn thấy | Nghĩa là | Làm gì |
|---|---|---|
| `✗ chưa cài claude trên máy này`, lệnh trả mã 2 | máy chưa có client agent | cài client, chạy `claude --version` cho tới khi được |
| `✗ không có docs/requirements.md` | chưa có đầu vào | tạo tệp theo [§4](#4-tạo-dự-án-và-viết-đầu-vào) |
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

Mọi lệnh nhận `--project <thư mục>` (mặc định: thư mục hiện tại).

**Chuẩn bị**

```bash
aisef doctor                              # kiểm môi trường
aisef setup [--references DIR] [--no-fetch] [--dry-run]
aisef init                                # ghi .ai/config.json mặc định
aisef compile [--client claude|opencode|all] [--bin PATH]
```

**Lập kế hoạch và cổng người**

```bash
aisef plan [--client c] [--auto-approve all|<danh sách>] [--force]
aisef mockup [--client c] [--only <screen_id>] [--force]
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
aisef guard <tên guard>                   # framework tự gọi qua hook
```

**Kiểm định và phát hành**

```bash
aisef qa [--only <loại>] [--story S] [--story-level]
aisef devsecops [--client c] [--install-spec X] [--bin PATH] [--force]
aisef pre-deploy [--skip-qa] [--epic E]
```

**Quan sát**

```bash
aisef status
aisef report [--out FILE]
aisef evidence <id> [--story S] [--link TEST --why "..." --by ai]
aisef issues [--format md|csv] [--epic E] [--status gap,reopened] [--out FILE]
aisef ctx [--story S | --file F] [--budget N]
aisef skill [--story S] [--scan --client c --batch N]
aisef doc <gói> [--topic T] [--story S]
aisef change FR-x "mô tả"
```

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

**Chạy**

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `run.max_parallel` | `3` | số story chạy song song |
| `run.max_turns` | `40` | trần số lượt trong một phiên agent |
| `run.timeout_seconds` | `1800` | trần thời gian một phiên |
| `run.max_retries` | `2` | số lần thử lại một story |
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
| `sandbox.image` | `""` | ảnh container |
| `sandbox.tools_network` | `false` | cho tool ra mạng hay không |
| `sandbox.pre_deploy_degraded_waiver` | `""` | lý do chấp nhận kiểm định chạy ngoài Docker ở cổng cuối |

**Ngữ cảnh, vòng cải tiến, client**

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `context.max_index_chars` | `2000` | trần ký tự cho chỉ mục bằng chứng nạp vào prompt |
| `context.max_preservation_chars` | `1200` | trần ký tự cho danh sách hành vi phải giữ |
| `context.max_repo_map_chars` | `0` | trần cho bản đồ mã; `0` là tắt |
| `improve.max_loops` | `3` | số vòng cải tiến tối đa cho một epic |
| `improve.flat_loops` | `2` | dừng khi ngần này vòng liền không cải thiện |
| `improve.cost_cap_usd` | `0.0` | trần chi phí vòng cải tiến; `0` là không giới hạn |
| `route.developer_model` · `route.reviewer_model` · `route.designer_model` | `""` | ép model cho từng vai |
| `clients.env_allow` | `[]` | biến môi trường được phép truyền vào phiên agent |
| `skills.offer` | `false` | gợi ý skill cho agent; đo chưa thấy lợi nên tắt. Cơ chế thứ hai (`skills.inline`) đã **gỡ** ở 1.4.0 sau hai lần A/B cho `used` 0/0 |

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
  minh), `GAP` (chưa), `REOPENED` (từng đúng, nay hỏng lại).
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
