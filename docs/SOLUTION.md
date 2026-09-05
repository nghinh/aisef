# AI-SDLC Framework — Giải pháp tổng thể

**Trạng thái:** bản chốt để duyệt trước khi thực thi diện rộng.
**Phiên bản:** 2 — viết lại sau khi rà soát, sửa 12 vấn đề của bản 1 (mục 17).

---

## 1. Yêu cầu

| # | Yêu cầu |
|---|---|
| R1 | Đầu vào mỗi dự án là **một file** `docs/requirements.md` |
| R2 | Bộ prompt **chuẩn hoá**, dùng lại cho mọi dự án |
| R3 | **Setup**: nạp BMAD + skills + agents + MCP + hooks + plugins vào dự án |
| R4 | **BMAD** sinh PRD · Architecture · UX Spec · Epics · Stories — **mỗi story một file** |
| R5 | **Mockup** HTML cho toàn bộ màn hình |
| R6 | **Coding agent** hiện thực từng story, **map với mockup** |
| R7 | Coding agent đủ **6 nhóm harness** (mục 5) — không mượn DeepSeek harness / vnpt runtime |
| R8 | Agents **deep review · test** (functional, SIT, E2E, UAT, performance) **· security** |
| R9 | Agents **DevSecOps** |
| R10 | Chạy trên **Claude Desktop · Claude CLI · OpenCode Desktop · OpenCode CLI** |
| R11 | Chuẩn hoá, chuyên nghiệp, hiện đại |
| R12 | Sản phẩm cuối **chất lượng, khớp yêu cầu** — chứng minh được, không tự khai |
| R13 | **Người duyệt từng bước**, trừ khi truyền tham số tự duyệt |
| R14 | **Chạy epic tuần tự, story song song trong epic** khi không phụ thuộc nhau |

---

## 2. Khả thi — đã kiểm chứng trên máy thật

Không giả định. Chạy `--help` và kiểm tra binary ngày 2026-09-03.

### 2.1 Bốn bề mặt, hai chế độ

Phân loại theo **chế độ chạy**, không theo tên sản phẩm — vì control plane vào bằng đường khác nhau:

| Bề mặt | Có trên máy | Chế độ | Control plane vào bằng |
|---|---|---|---|
| Claude Desktop | `/Applications/Claude.app` ✅ | agent-led | agent gọi `aisdlc` qua Bash tool |
| Claude CLI | `claude` 2.1.236 ✅ | cả hai | tương tác: qua Bash · headless: `claude -p` |
| OpenCode Desktop | `/Applications/OpenCode.app` ✅ | agent-led | agent gọi `aisdlc` qua Bash tool |
| OpenCode CLI | `opencode` ✅ | cả hai | TUI/web: qua Bash · headless: `opencode run` |

OpenCode còn có `serve` (server headless) + `attach`/`web` — nhiều client nối vào một server. Hữu ích về sau, **không cần cho V1**.

> `opencode --auto` (tự duyệt mọi quyền) **không dùng**: ta không tin cơ chế quyền của client, guard nằm ở harness (bất biến 9).

### 2.2 Năng lực từng engine


| Năng lực cần | Claude Code 2.1.236 | OpenCode | Kết luận |
|---|---|---|---|
| Chạy headless | `-p / --print` | `run`, `serve` | ✅ |
| Đọc kết quả máy | `--output-format stream-json` | `export <sessionID>` | ✅ |
| Nạp hook | `--settings <file\|json>` | `plugin` | ✅ |
| Custom agent | `--agents <json>` | `agent` | ✅ |
| Giới hạn tool | `--allowed-tools` / `--disallowed-tools` | permission config | ✅ |
| **Giới hạn thư mục** | `--add-dir` | — | ✅ Claude; OpenCode dùng guard |
| Định tuyến model | `--model` | `models` | ✅ |
| **Cost / token** | usage trong stream-json | **`stats`** | ✅ |
| Phiên, resume | `--session-id`, `--resume` | `session` | ✅ |
| Giới hạn vòng lặp | `--max-turns` | — | ✅ Claude; OpenCode dùng timeout |
| **Cách ly cấu hình máy** | `--permission-mode acceptEdits` + `--allowed-tools` kê tường minh + `--setting-sources project,local` + `--strict-mcp-config` | plugin dự án — chưa đo | ✅ Claude, đo 2026-09-05: `defaultMode: auto` toàn cục làm phiên con **mất Glob/Grep** và ghi bằng Bash heredoc né guard `Write\|Edit`; MCP + hook người dùng lọt vào. Sau cờ: Glob có, MCP 0, hook người dùng 0, guard vẫn chặn |

Hạ tầng: `docker` daemon **đang chạy** · `git worktree` dùng được · `npx` có.
Chưa có: `pytest`, `semgrep`, `trivy`, `k6` → **chạy trong container**, không cài lên máy (mục 6).

---

## 3. Nguyên tắc nền

> **Cần phán đoán → giao model. Cần đảm bảo → viết code.**

Hệ quả: **không nhờ thực thể bị giám sát tự giám sát nó.** Agent báo "test xanh" không phải bằng chứng; chỉ tiến trình ngoài chạy `pytest` và đọc exit code mới là. Toàn bộ R12 đứng trên câu này.

---

## 4. Năm quyết định kiến trúc

| # | Quyết định | Lý do | Đánh đổi chấp nhận |
|---|---|---|---|
| Đ1 | **Một phiên cho một story** (`fresh-session`) | Ngữ cảnh không tích luỹ ⇒ bỏ được rotation, capsule, resume-ACK, 11 mã blocker, SSE watch, đo usage mà vnpt phải viết | Mỗi story phải nạp lại ngữ cảnh ⇒ tốn token (mục 14) |
| Đ2 | **Control plane là CLI gọi-một-lần, không daemon** | Điều kiện duy nhất để chạy được cả trong phiên chat lẫn headless → R10 | Không có tiến trình theo dõi liên tục; trạng thái phải ở đĩa |
| Đ3 | **Một nguồn `kit/` → compile ra từng client** | Không viết 3 bản độc lập → R10, R11 | Cần golden test chống trôi |
| Đ4 | **BMAD là dependency, không phải nền móng** | Contract của framework nằm giữa; BMAD lên đời chỉ sửa normalizer | Thêm một lớp normalize |
| Đ5 | **Mỗi story song song chạy trong git worktree riêng** | Cô lập git, file, test khi chạy song song (mục 7) | Thêm bước merge tuần tự sau mỗi đợt |

---

## 5. Xương sống: 6 nhóm harness

Đây là **thước nghiệm thu**. Mọi thứ khác phục vụ sáu ô này.

### 5.1 Instructions & Rule Files
| Hạng mục | Hiện thực |
|---|---|
| Hiến pháp kỹ thuật | `kit/constitution/` → compile ra `CLAUDE.md` · `AGENTS.md` · `GEMINI.md` |
| Skill files | `kit/skills/` — 12 tự viết + import có pin: BMAD 22, superpowers 10, ui-ux 7, security (mục 8), karpathy 1 |
| Vai agent | `harness/routing.py` — 4 vai (developer · reviewer · security · designer), mỗi vai một phiên mới, prompt trong `kit/prompts/`; không có thư mục agent riêng |
| PromptCatalog | `kit/prompts/` — prompt vận hành từng pha, có version, có test |

### 5.2 Tools
| Hạng mục | Hiện thực |
|---|---|
| Tool thật | `harness/tools.py` — `read_file` `write_file` `run_test` `run_lint` `run_sast` `run_scan` `git_commit` `screenshot` |
| MCP | không có — quyết định V1: không MCP thường trú; playwright dùng qua CLI trong `harness/browser.py`, tra cứu tài liệu theo yêu cầu là việc đợt 5 (`aisdlc doc`) |
| **Prose quanh tool** | mỗi tool có mục "khi nào gọi / cách đọc kết quả / khi nào KHÔNG gọi" |

### 5.3 Sandboxes & execution environments
| Hạng mục | Hiện thực |
|---|---|
| Bậc quyền | `READ_ONLY` → `WORKSPACE_WRITE` → `WORKSPACE_NETWORK` → `PRIVILEGED_TEST` |
| Bộ thực thi | Docker: `--network=none` mặc định · `--cap-drop=ALL` · non-root · chỉ mount worktree của story |
| Công cụ verify | chạy **trong image**, không cài lên máy host (giải quyết việc thiếu pytest/semgrep/trivy/k6) |
| Ảnh | chọn theo stack dự án (`node:22-alpine`, `python:3.12-alpine`…), cấu hình đè được. `alpine` trơn không có công cụ nào, chạy `npm test` trong đó sẽ đỏ vì **thiếu công cụ** chứ không phải vì code sai — `doctor` cảnh báo đúng chỗ này |
| Mạng cho tool | tắt mặc định; dự án cần cài phụ thuộc thì khai `sandbox.tools_network` tường minh |
| Suy biến | Không có Docker → subprocess giới hạn + **ghi rõ mức bảo đảm thấp hơn** vào evidence |

### 5.4 Orchestration logic
| Hạng mục | Hiện thực |
|---|---|
| Định tuyến model | `harness/routing.py` — theo vai; **reviewer ≠ developer** |
| Sinh sub-agent | không có — mỗi vai là một phiên riêng do harness gọi (`harness/routing.py`); xem ADR-003 #15 |
| Bàn giao | `next` → `implement` → `verify` → `review` → `complete` |
| Luật kích hoạt | `control/state.py` (FSM `PENDING → RUNNING → VERIFYING → VERIFIED → DONE`) + `control/scheduler.py` (đợt theo phụ thuộc và phạm vi ghi) ✅ **đã xong** |

### 5.5 Guardrails / Hooks
| Mốc | Guard | Chặn gì |
|---|---|---|
| before tool call | `write-scope` | ghi ngoài phạm vi story |
| before tool call | `destructive` | `rm -rf`, `git reset --hard`, `checkout --` |
| after file edit | `diff-scope` | file không liên quan bị chạm |
| before commit | `secret` | khoá/mật khẩu/token |
| before commit | `git-stage` | `git add -A` |
| before commit | `injection` | SQL nối chuỗi, `dangerouslySetInnerHTML` |
| before commit | `process-ref` | mã `STORY-…`/`EPIC-…` trong mã nguồn (luật 6); test và tài liệu được phép |
| on stop | `completion` | kết thúc khi test chưa xanh |

Mỗi guard là **một lệnh độc lập trả exit code** → nối được vào mọi client.

### 5.6 Observability
| Hạng mục | Hiện thực |
|---|---|
| Log, trace | sự kiện có cấu trúc, có provenance |
| **Cost & latency** | token in/out · USD · giây — ghi vào mỗi `evidence/{story}.json`, cộng dồn theo epic |
| **Ứng viên** | mỗi phép kiểm mang `detail.candidate` = SHA bản được kiểm (ADR-004 R1) |
| Evaluation | chấm skill/prompt trên bộ mẫu, phát hiện trôi chất lượng |
| Dashboard | `aisdlc status` |

---

## 6. Hai loại cổng

Chạy nối tiếp — **máy kiểm trước** để khỏi phí thời gian người.

| | Cổng máy | Cổng người (R13) |
|---|---|---|
| Kiểm | schema · không chu trình · mọi FR được phủ · story không quá lớn · 4 điều kiện story gate | nội dung có đúng ý không |
| Ai chạy | tự động | người, bằng lệnh |
| Trượt thì | dừng, báo lỗi cụ thể | ghi `changes_requested` + ghi chú, sinh lại |

### Cổng người — phê duyệt là **trạng thái trên đĩa**, không phải prompt

Điều kiện để chạy được ở mọi nơi: CI không có người trả lời; agent trong phiên chat không thể "đợi"; người duyệt có thể ở **máy khác, lúc khác**.

**Tám cổng:** `prd` → `architecture` → `ux-spec` → `epics` → `stories` → `mockups` → `readiness` → `pre-deploy`

**Hai bảo đảm:**
1. Phê duyệt gắn với **SHA-256 nội dung**. Sửa artifact → tự thành `stale`.
2. Duyệt lại tầng trên → tầng dưới thành `stale`. Thứ tự so bằng **số thứ tự đơn điệu**, không bằng đồng hồ (bản ghi đi qua git giữa nhiều máy).

**Tự duyệt:** `--auto-approve all` hoặc `--auto-approve prd,architecture`. Luôn ghi `decided_by: auto` để truy được artifact nào chưa từng có người xem.

> Cổng người ở **mức pha**, không ở mức story. Story dùng cổng máy 4 điều kiện — nếu bắt duyệt tay 114 lần thì mất hết ý nghĩa của tự động hoá.

✅ **Đã xong** — `aisdlc/control/approvals.py`, 19 test.

### Cổng máy chấm trên một **ứng viên đóng băng** (ADR-004 R1)

Ngay khi phiên developer kết thúc, harness commit worktree và ghi mốc
`candidate.frozen(sha)` — **trước** test, cổng và rà soát. Từ đó tới hết
lượt, mọi bằng chứng mang `detail.candidate` là SHA ấy, và thứ tự nhật ký
là `attempt.started → worktree.created → status.running → changes.detected
→ candidate.frozen → verification.completed → review.completed →
merge.completed → attempt.committed`.

Cổng có thêm mục **bằng chứng đúng candidate**: kết quả *mới nhất* của một
phép kiểm mà thuộc bản khác thì không được dùng để chấm, và mục ấy là
`stale` (⚠) — không phải "test đỏ", vì hai lỗi ấy sửa bằng hai cách khác
nhau. Người rà soát và rà soát bảo mật cũng bị so `git rev-parse HEAD` sau
phiên: đổi ứng viên thì lượt rà soát không được tính (hoàn nguyên cây
không thấy một `git commit`). Phép hợp quy **C8** đo đúng chuỗi này.

### Baseline trước khi sửa — mục **không làm đỏ test có sẵn** (ADR-004 R9)

Trước phiên developer đầu tiên của một story, harness chạy `tools.test` ở
HEAD worktree và ghi `tool_run test:baseline` (tên test, `red_before`,
`parent`; **không** có `candidate` vì ứng viên chưa đóng băng). Sau khi
đóng băng, cổng so tên test xanh ở baseline với lần test mới nhất mang
đúng `candidate`: xanh trước mà đỏ hoặc **mất** sau là ✗ nêu đúng tên —
test mới của story đang đỏ (TDD) không tính, test đã đỏ sẵn không tính và
được nói ra. Không so được thì kết cục theo bất biến: chưa khai lệnh /
reporter không in tên → ○, không chạy được → ⚠, tắt bởi `verify.baseline`
→ –. Chạy một lần mỗi story, không mỗi lượt: lấy ứng viên lượt trước làm
mốc thì test lượt trước vừa làm đỏ thành "đỏ sẵn" và lượt sau xoá nó là qua
cổng sạch. Ghi dưới tên riêng, không phải `test`, để guard `completion`,
TDD và sổ hành vi không đọc nhầm nó thành lần test của lượt.

---

## 7. Chạy song song và cô lập (R14) — phần dễ sai nhất

### 7.1 Lịch chạy

Epic **luôn tuần tự** (epic sau dựa vào schema/API epic trước). Trong epic chia **đợt**; story vào cùng đợt khi:
1. mọi `depends_on` đã xong, **và**
2. `write_scope` không đụng nhau.

Điều kiện 2 hay bị bỏ quên và là nguyên nhân hỏng khó lần nhất. So đường dẫn theo **đoạn**, không theo tiền tố chuỗi — `src/api` và `src/apidocs` là hai vùng khác nhau. Story không khai `write_scope` bị coi là **chạm mọi thứ**.

✅ **Đã xong** — `aisdlc/control/scheduler.py`, 26 test. Ví dụ thật: 9 story → **5 lượt** thay vì 9.

### 7.2 Cô lập — không đủ nếu chỉ chia đợt

Chia đợt tránh được đụng *nội dung file*, nhưng ba thứ sau vẫn đụng nếu chạy chung một thư mục:

| Đụng gì | Hậu quả |
|---|---|
| `git add` / `git commit` đồng thời | tranh `index.lock` → commit hỏng |
| Test đồng thời | tranh cổng mạng, CSDL, file tạm |
| Cài phụ thuộc đồng thời | `node_modules` / venv hỏng |

**Giải: mỗi story trong đợt chạy trong git worktree riêng.**

```
.aisdlc/worktrees/S-01-02/     git worktree + nhánh story/S-01-02
.aisdlc/worktrees/S-01-03/     git worktree + nhánh story/S-01-03
```

- Worktree chia sẻ `.git`, không sao chép lịch sử → tạo nhanh, tốn ít đĩa.
- Test của mỗi story chạy trong **container riêng**, mạng riêng → không tranh cổng.
- Hết đợt: **merge tuần tự** theo thứ tự id vào nhánh chính, rồi xoá worktree.

### 7.3 Merge conflict là tín hiệu, không phải sự cố

`write_scope` đã bảo đảm hai story không chạm cùng vùng, nên **merge lẽ ra không bao giờ conflict**. Nếu conflict xảy ra: đó là bằng chứng story khai `write_scope` sai.

Xử lý: **dừng, ghi vào evidence, báo người** — không tự gỡ. Đây là vòng phản hồi giúp sửa chất lượng story ở Bước 2.

### 7.4 Mặc định

`--max-parallel 3`. Tăng thì nhanh hơn nhưng dễ chạm hạn mức model và tải máy; đo bằng `aisdlc status` rồi chỉnh.

---

## 8. Skills: lọc hai tầng

**Tầng 1 — loại tấn công và ngoài phạm vi.** Dựa trên metadata thật (`subdomain`, `tags`), không đoán theo tên.

```
818 skill  →  269 keep · 207 offensive · 342 out-of-scope
```

Ba luật, thứ tự có chủ đích: subdomain tấn công → chặn; động từ tấn công (`exploiting-`, `abusing-`) → chặn; **marker cứng** (`c2`, `aadinternals`) thắng cả động từ phòng thủ; **marker mềm** (`privilege-escalation`) thua động từ phòng thủ — `auditing-rbac-privilege-escalation` là việc phòng thủ chính đáng.

**Bất biến được test:** không skill nào thuộc subdomain tấn công lọt vào danh sách cài mặc định.

**Tầng 2 — theo stack dự án.** 269 → 20–30. Dự án Python+React+Postgres+Docker chỉ cần `container-security`, `api-security`, `web-application-security`, `devsecops`, `cryptography`, `supply-chain-security`; không cần 56 skill `cloud-security` cho hạ tầng không dùng.

✅ **Tầng 1 đã xong** — `aisdlc/kit/security_filter.py`, 14 test. Tầng 2 cần `detect_stack`.

---

## 9. Cấu trúc

```
aisdlc/                          framework, một package Python
├── kit/                         NHÓM 1 — nội dung chuẩn hoá (nguồn canonical)
│   ├── catalog.json             sổ đăng ký skill + pin version + lý do chọn
│   ├── constitution/            → CLAUDE.md · AGENTS.md · GEMINI.md
│   ├── skills/  agents/  prompts/  hooks/  mcp/
│   ├── skills.py                ✅ đọc SKILL.md (stdlib, không cần PyYAML)
│   └── security_filter.py       ✅ lọc tầng 1
├── harness/                     NHÓM 2–6 — harness là code
│   ├── tools.py  sandbox.py  routing.py
│   ├── guardrails.py  observe.py  eval.py  context.py
├── control/                     điều phối nhiều story
│   ├── approvals.py             ✅ cổng người duyệt
│   ├── scheduler.py             ✅ đợt song song
│   ├── state.py                 sprint-status, khoá file, resume
│   ├── worktree.py              cô lập song song (mục 7)
│   ├── evidence.py  gate.py
├── clients/                     R10
│   ├── base.py  claude_code.py  opencode.py  compile.py
├── phases/                      setup · plan · mockup · implement · verify · ship
└── cli/                         bộ lệnh, một tệp mỗi pha (parser · plan · implement · harness · doctor)
```

**Sinh ra trong dự án đích:**

```
dự-án/
├── docs/requirements.md          đầu vào duy nhất
├── .ai/                          canonical (compile từ kit)
├── .claude/  .opencode/          generated — không sửa tay
├── .aisdlc/worktrees/            cô lập khi chạy song song
├── _bmad/custom/*.toml           override agent BMAD
├── _bmad-output/                 MỘT gốc artifact
│   ├── prd.md  architecture.md  DESIGN.md  EXPERIENCE.md  epics.md
│   ├── stories/EPIC-01/STORY-01-01.md …
│   ├── stories.index.json        metadata máy đọc
│   ├── design-contract.json
│   ├── approvals/*.json          cổng người duyệt
│   ├── evidence/{story}.json     bằng chứng + cost + latency
│   └── sprint-status.json        trạng thái, resume được
├── mockups/*.html
└── src/  tests/
```

> **JSON, không YAML.** Đây là file máy sinh máy đọc; JSON có sẵn trong stdlib, còn YAML kéo theo một dependency chỉ để tiết kiệm vài dấu ngoặc. Người vẫn đọc và sửa tay được.

---

## 10. Bộ lệnh

Đây là bộ lệnh **đã hiện thực** (`aisdlc --help`), không phải bản phác.

```
# Chuẩn bị
aisdlc doctor                         môi trường: python · git · client · docker · playwright
aisdlc setup   [--references DIR]     dò stack, nạp skill, sinh CLAUDE.md + AGENTS.md
aisdlc init                           ghi .ai/config.json mặc định
aisdlc compile [--client claude|opencode|all]   sinh hook/plugin từ một nguồn guard duy nhất

# Bước 2 — tài liệu, dừng ở mỗi cổng
aisdlc plan    [--auto-approve all|<danh sách>] [--force]
        project-context → prd → architecture → ux → epics → tách story

# Bước 3 — mockup
aisdlc mockup  [--only <screen_id>] [--force]

# Cổng người duyệt
aisdlc gates                          bảng trạng thái 8 cổng
aisdlc review  <gate>                 artifact, trình bày theo loại cổng
aisdlc approve <gate> [--note ...] [--force]
aisdlc reject  <gate>  --note "..."   (bắt buộc ghi chú)
aisdlc auto-approve all|<danh sách>   luôn ghi dấu `auto`

# Bước 4 — hiện thực
aisdlc run     [--epic E] [--sequential] [--no-isolate] [--force]
aisdlc tool    test|lint|sast [--story S]      agent gọi qua đây để có bằng chứng
aisdlc verify  [--write-scope ...] [--story S] hậu kiểm guard trên cây làm việc

# Bước 5 — kiểm định
aisdlc qa      [--only <loại>] [--story S] [--story-level]

# Bước 6 — giao hàng
aisdlc devsecops [--bin PATH] [--force]        CI (code) + Dockerfile/IaC/runbook (model)
aisdlc pre-deploy [--skip-qa]                  chấm cổng cuối, ghi báo cáo để người ký

# Guard — client gọi vào tại mốc vòng đời (do `compile` nối sẵn)
aisdlc guard write-scope|diff-scope|secret|git-stage|destructive|injection|process-ref|completion

# Theo dõi
aisdlc status                         tiến độ · chi phí · story tốn bất thường
aisdlc report  [--out FILE]           báo cáo nghiệm thu + sổ hành vi (`ledger.json`, `INDEX.md`)
aisdlc evidence <id> [--story S]      lịch sử một story hoặc một hành vi
                                      (STORY-01-04 · AC-STORY-01-04-2 · FR-3 · qa:e2e · mockup:notes-list)
```

`report` chiếu bằng chứng thành **sổ hành vi** (ADR-004 R2): mỗi tiêu chí,
yêu cầu, loại kiểm định và màn hình là một hành vi có trạng thái
VERIFIED / GAP / **REOPENED** — cái cuối là "đã đúng rồi hỏng", thứ mà cổng
story không nói được. `INDEX.md` là chỉ mục một dòng mỗi story; prompt
developer nhận **lát cắt epic** của chỉ mục ấy (slot `index`, trần
`context.max_index_chars`), còn lịch sử tra bằng `aisdlc evidence`.

Không có `aisdlc next` / `implement` / `complete` như bản phác: vòng lặp
story nằm trong `run`, và tách nhỏ ra thành ba lệnh chỉ tạo thêm ba chỗ
cho trạng thái lệch nhau.

---

## 11. Đa client (R10)

**Nội dung:** `kit/` → `aisdlc compile` → `.claude/` · `.opencode/`. Bắt buộc deterministic · idempotent · golden round-trip test · **khai báo loss** khi client thiếu cơ chế.

**Điều khiển:** cùng bộ lệnh, hai chế độ — đây là lý do Đ2 (CLI gọi-một-lần, không daemon) là quyết định đúng: thêm bề mặt mới **không phải sửa kiến trúc**.

| | Driver-led | Agent-led |
|---|---|---|
| Ai gọi | script / CI | chính agent, qua Bash tool |
| Bề mặt | `claude -p` · `opencode run` · cron · CI | **Claude Desktop · Claude CLI · OpenCode Desktop · OpenCode TUI/Web** |
| Lệnh | `aisdlc run --client X` | `aisdlc next` → làm → `aisdlc verify S` → `aisdlc complete S` |

`run` chỉ là vòng lặp gọi lại chính các lệnh đơn — **không có code riêng cho mỗi chế độ**.

**Nối guard:**

| Bề mặt | Cách nối | Mức | Đã kiểm chứng |
|---|---|---|---|
| Claude CLI | `--settings` hooks → `aisdlc guard …` | tiền kiểm | ✅ cờ có thật |
| Claude Desktop | `.claude/settings.json` của dự án | tiền kiểm | ⚠️ suy luận — phải test |
| OpenCode CLI | plugin → `aisdlc guard …` | tiền kiểm | ✅ chứng minh 2026-09-05 trên agent thật; quan sát chi phí/lượt: chưa |
| OpenCode Desktop | cùng cấu hình dự án với CLI | tiền kiểm | ⚠️ suy luận từ CLI — chưa test riêng |
| Bất kỳ, nếu hook không gắn được | `aisdlc verify` chạy lại toàn bộ guard | hậu kiểm | ✅ luôn có |

**Quyết định (2026-09-05, thay quyết định 2026-09-04): OpenCode là client hạng hai trong V1.**
Phép thử trên agent thật (opencode 1.18.26) đã chứng minh plugin **chặn tại
nguồn** cho cả tool bash lẫn tool ghi tệp — nên hàng "hậu kiểm" ở bảng trên
không còn đúng cho guard. Cái còn thiếu là **quan sát**: OpenCode không phát
luồng sự kiện có cấu trúc, nên chi phí, số lượt và giới hạn lượt không đo
được từ harness (`turn_limit: unsupported`, `machine_output` chưa chứng
minh). Hệ quả:

* OpenCode chạy được trọn story (STORY-02-01 của `par`, qua bảy cổng, merge
  vào main) và được hỗ trợ — nhưng `compile --client opencode` ghi rõ "hạng
  hai V1: chi phí/lượt không đo được";
* hợp quy client (`docs/CONFORMANCE.md`) chạy cả hai client, nhưng **điều
  kiện phát hành chỉ đọc cột Claude**; OpenCode không chặn phát hành;
* nâng hạng nhất sau release, khi `--format json` được chứng minh và bộ hợp
  quy hook chạy ổn định qua nhiều phiên bản.

**Phạm vi V1:** 4 bề mặt của Claude Code và OpenCode (mục 2.1). Antigravity hoãn — chưa test được.

---

## 12. Sáu bước

| Bước | Nội dung | Xong khi |
|---|---|---|
| **1 Setup** | dò stack → chọn skill theo catalog → lọc security 2 tầng → cài → compile → doctor | `doctor` trả 0 · đếm đúng số skill · **không skill offensive nào lọt** · chạy lại không nhân bản |
| **2 BMAD** | `project-context → prd → architecture → ux → epics-and-stories`, mỗi pha một cổng; rồi **framework** tách mỗi story một file + `stories.index.json` (không dùng `bmad-sprint-planning`: xếp lịch tính được chắc chắn từ phụ thuộc + `write_scope`, không cần model) | index parse được · không chu trình · **mọi FR được ≥1 story phủ** · không story vượt ngưỡng · 5 cổng `approved` |
| **3 Mockup** | ux-spec + ui-ux-pro-max → HTML → screenshot → `design-contract.json` | mỗi màn hình có đúng một mockup mở được · contract không mục treo · story frontend map tới `screen_id` thật · cổng `mockups` `approved` |
| **4 Implement** | phiên mới mỗi story · worktree riêng · **map mockup (mục 12bis)** · RED→GREEN→VERIFY · guard 3 mốc · merge tuần tự cuối đợt | guard **chặn thật** (3 test) · hai story đụng scope không cùng đợt · chạy hết 1 epic ≥5 story · dừng giữa chừng resume đúng chỗ · cổng `readiness` `approved` |
| **5 Verify** | review sâu · unit · SIT · API contract · E2E · UAT · perf · security · mutation | mỗi loại chạy thật, trả kết quả máy đọc · cổng **chặn thật** khi đẩy story lỗi |
| **6 Ship** | container · CI/CD · SBOM · IaC · observability · runbook | `docker build` chạy · CI chặn khi story fail · SBOM sạch high · runbook đủ 4 mục · cổng `pre-deploy` `approved` |

**Cổng story (Bước 4–5) — PASS chỉ khi đủ, mỗi thứ là bằng chứng chạy thật:**
1. Test xanh, coverage ≥ ngưỡng
2. Review APPROVED bởi agent khác người viết — báo cáo trả **hai bản**:
   văn bản có thẻ `[chặn]`/`[bế tắc]` cho người đọc, và một khối JSON
   (`verdict` + `findings` mang `behavior_id`) cho máy đọc. Thiếu khối JSON
   thì harness hỏi lại **đúng một lần** rồi mới lùi về đọc văn bản; hai bản
   lệch nhau thì lấy **hợp** hai nguồn và ghi note `review:mismatch` — không
   nới lỏng cổng vì model quên chép một mục sang JSON (ADR-004 R8)
3. Security 0 phát hiện high/critical
4. Truy vết: commit mang `FR-xx`, nối được code ↔ story ↔ requirement
5. **Khớp mockup** — chỉ áp cho story có `screen_id` (mục 12bis)

---

## 12bis. Map với mockup — bước bắt buộc của story có giao diện

**Mockup còn là một lớp kiểm định đặc tả.** Lượt chạy thật (5 màn, $9.22)
sinh ra 52 chỗ `data-unresolved`, và 31 chỗ trong đó **không** thuộc câu
hỏi mở nào đã biết — chúng là lỗ hổng agent phát hiện khi cố dựng: `tag-chip`
không có trạng thái "gỡ thẻ" mà FR-8 đòi; không bề mặt nào trong
`DESIGN.md.Components` chứa nổi thông báo ghi hỏng; màn `tags` cần một hàng
quản lý thẻ mà đặc tả không định nghĩa.

Đó là những thứ chỉ lộ ra khi có người (hoặc agent) phải dựng thật. Phát
hiện chúng ở bước mockup rẻ hơn nhiều so với phát hiện ở bước viết code —
và rẻ hơn rất nhiều so với phát hiện sau khi giao hàng.

Story nào có `screen_id` phải đi qua **hai nửa** của bước map. Thiếu nửa nào cũng không tính là xong.

### Nửa trước khi code — nạp hợp đồng thị giác

Prompt của story được bổ sung, không phải để tham khảo mà là ràng buộc:

| Nạp gì | Từ đâu |
|---|---|
| Lát cắt contract của đúng màn hình đó | `design-contract.json#screens[screen_id]` |
| Mockup HTML | `mockups/{screen_id}.html` |
| Ảnh chụp mockup | `mockups/{screen_id}.png` |
| Danh sách component bắt buộc, route, nhãn, quy tắc validation | trích từ contract |

Nạp **đúng một màn hình**, không nạp cả contract — giữ ngân sách ngữ cảnh (mục 14).

### Nửa sau khi code — đối chiếu màn hình thật

1. Dựng ứng dụng, mở **route thật** bằng Playwright.
2. Trích DOM / accessibility tree.
3. Đối chiếu từng component trong contract: có mặt không · nhãn đúng không · route đúng không.
4. Chụp ảnh màn hình thật, đặt cạnh ảnh mockup trong evidence.
5. Reviewer nhìn cặp ảnh và ghi nhận xét.

### Ba mức đối chiếu — và vì sao chỉ một mức được chặn

| Mức | Cách làm | Vai trò |
|---|---|---|
| **Cấu trúc** | component trong contract có mặt trong cây accessibility thật | **CHẶN** — tất định, lặp lại được |
| Thị giác bằng model | reviewer nhìn hai ảnh, ghi nhận xét | cảnh báo, không chặn |
| ~~Pixel diff~~ | so ảnh từng điểm ảnh | **không dùng** |

Không dùng pixel diff vì mockup HTML tĩnh và ứng dụng thật không bao giờ trùng từng điểm ảnh; gate kiểu đó đỏ liên tục, rồi người ta tắt nó đi — một cổng bị tắt còn tệ hơn không có cổng.

**Dữ liệu mẫu tách khỏi khung giao diện.** Cùng lý do đó, hàng danh sách
trong mockup mang nội dung ví dụ mà ứng dụng thật không bao giờ hiển thị
lại. Mockup đánh dấu vùng đó bằng `data-sample`; hợp đồng tách
`components` (cam kết theo **vai trò + tên gọi**) khỏi `data_roles` (chỉ
cam kết **có mục thuộc kiểu đó**). Không tách thì "Đặt lịch khám răng" trở
thành cam kết và cổng đỏ vĩnh viễn; tách quá tay thì một danh sách rỗng
cũng "đạt" — nên vùng dữ liệu rỗng vẫn là trượt.

### Kết quả ghi vào evidence

```json
"mockup_map": {
  "screen_id": "SCREEN-03",
  "route": "/login",
  "contract_components": 7,
  "matched": 7,
  "missing": [],
  "extra": ["banner-promo"],
  "missing_data_roles": [],
  "screenshot_mockup": "mockups/SCREEN-03.png",
  "screenshot_actual": "_bmad-output/evidence/shots/STORY-01-04.png",
  "visual_note": "bố cục khớp; nút Sign In nằm phải thay vì trái"
}
```

**Luật cổng:** `missing` rỗng → PASS. `extra` chỉ cảnh báo — ứng dụng thật được phép có thêm phần tử hợp lý, nhưng **không được thiếu** thứ contract đã hứa.

**Khi mockup mâu thuẫn tài liệu:** thứ tự sự thật là architecture > ux-spec > design-contract. Gặp mâu thuẫn thì **dừng và báo**, không tự chọn.

---

## 13. Ngưỡng và cấu hình

Không để chữ "ngưỡng" chung chung. Mặc định trong `.ai/config.json`, chỉnh được theo dự án:

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `coverage.min` | `0.85` | coverage tối thiểu — số đọc từ output runner; không có số thì mục cổng là **chưa cấu hình**, không đạt không trượt |
| `tools.test` | theo stack | lệnh test; muốn `coverage.min` có nghĩa thì lệnh phải **in coverage**: `node --test --experimental-test-coverage`, `vitest run --coverage`, `pytest --cov` — harness không tự thêm cờ |
| `skills.offer` | `false` | đưa mục "Kỹ năng có sẵn" (router chọn) vào prompt story; bật sau khi A/B có số (ADR-003 §6) |
| `story.max_acceptance_criteria` | `8` | quá thì Bước 2 buộc chẻ nhỏ |
| `story.max_write_scope_paths` | `10` | story chạm quá nhiều nơi là dấu hiệu quá lớn |
| `story.max_screen_states` | 8 | Tổng trạng thái màn hình (EXPERIENCE.md) một story phải dựng. Vượt → cổng `stories` chặn với chỉ dẫn chẻ; `run` từ chối. Đo 2026-09-05 e9: 11 và 18 trạng thái đều chạm `max_turns` lượt đầu, 4–8 lượt |
| `story.max_complexity` | `16.0` | **Điểm cỡ story** tổng hợp (ADR-004 R5, `control/complexity.py`): trạng thái màn hình ×1 + tiêu chí ×1 + đường dẫn write_scope ×0,5 (không tính manifest/lockfile) + fan-in phụ thuộc ×1 + story láng giềng có hành vi VERIFIED bị chạm ×0 (ledger; chỉ ghi để hiệu chuẩn, chưa tính điểm — ADR-004 §6 R5). Vượt **hoặc** vượt `max_screen_states` → cổng `stories` chặn kèm gợi ý chẻ tất định, `run` từ chối trước khi gọi model; story đã xong bỏ qua. Hiệu chuẩn B4 hồi cứu 23 story thật: Spearman(điểm, lượt developer lượt đầu) = 0,88; 16 tách e9 01-04 (23,5) và 01-05 (18,0) khỏi 01-03 (6,5) và `par` (3,0). `run` tự ghi `_bmad-output/complexity.json` sau mỗi story và `aisdlc doctor` cảnh báo khi ngưỡng lệch dữ liệu |
| ~~`story.max_context_tokens`~~ | — | **gỡ 2026-09-05**: chưa từng có mã đọc. Thay bằng `prompt_chars` ghi vào evidence mỗi lượt gọi model; `aisdlc status` cảnh báo story nạp > 3× trung vị |
| `context.max_index_chars` | `2000` | trần ký tự cho slot `index` — lát cắt chỉ mục bằng chứng của epic nạp vào prompt developer. Chỉ mục, **không** phải lịch sử: agent cần chi tiết thì gọi `aisdlc evidence <id>` (ADR-004 R6). e9 EPIC-01 đo được 497 ký tự |
| `run.max_parallel` | `3` | số story song song trong một đợt |
| `run.max_turns` | `40` | vòng lặp tối đa của một phiên story |
| `run.timeout_seconds` | `1800` | 30 phút cho một story |
| `run.max_retries` | `2` | số lần thử lại trước khi `blocked` |
| `cost.warn_multiple` | `3.0` | cảnh báo khi story tốn > 3× trung vị |
| `security.block_severities` | `["critical","high"]` | mức chặn merge |

Bổ sung sau khi chạy thật — mỗi khoá ra đời từ một lần hỏng cụ thể:

| Khoá | Mặc định | Vì sao có |
|---|---|---|
| `tools.test` · `tools.lint` · `tools.sast` | `""` (tự dò) | lệnh là quyết định của dự án; rỗng thì dò từ file có thật |
| `verify.*` (10 loại) | `""` | rỗng nghĩa là **chưa cấu hình**, không phải "đạt" |
| `verify.waived` | `""` | miễn phải là quyết định có người ký, không phải hệ quả của việc quên |
| `verify.baseline` | `true` | chạy bộ test ở candidate cha **trước** phiên developer đầu tiên của story (ADR-004 R9) để cổng "không làm đỏ test có sẵn" so được tên test; tắt khi bộ test quá chậm — tắt thì mục cổng là – "tắt bởi cấu hình", không phải đạt |
| `sandbox.image` | `""` (theo stack) | `alpine` trơn không có công cụ nào; test đỏ vì thiếu công cụ chứ không vì code sai |
| `sandbox.tools_network` | `false` | dự án cần cài phụ thuộc mới mở mạng, và phải khai tường minh |
| `sandbox.use_docker` | `true` | tắt được cho toolchain gắn với máy chủ, nhưng luôn ghi `degraded` |
| `app.dev_command` · `app.base_url` | `""` · `localhost:5173` | để mở **route thật** lúc đối chiếu mockup |
| `route.<vai>_model` | `""` | chọn model theo vai; rỗng thì theo mặc định của client |

---

## 14. Chi phí

Đ1 (mỗi story một phiên sạch) đánh đổi token lấy sự đơn giản. Phải đo, không đoán.

**Ngữ cảnh nạp mỗi story:** hiến pháp + architecture (phần liên quan) + story + design-contract (nếu có UI) + code trong `write_scope`. Kích thước nạp thật được ghi vào evidence (`prompt_chars`), không đặt ngưỡng trước.

**Giảm chi phí:**
- Chỉ nạp phần architecture mà `arch_refs` của story trỏ tới, không nạp cả file.
- Chỉ nạp code trong `write_scope` và các file nó import trực tiếp.
- Reviewer là phiên riêng, ngữ cảnh sạch → **nhân đôi chi phí mỗi story**; đây là cái giá của "reviewer ≠ developer" và không cắt được.

**Bắt buộc:** ghi `cost` + `latency` vào mỗi `evidence/{story}.jsonl`, cộng dồn theo epic. **Đo trên một epic mẫu trước khi chạy toàn bộ** — con số thật của dự án bạn không suy ra được từ lý thuyết.

**Số đo thật** (dự án ghi chú, PRD 33KB · kiến trúc 26KB · UX 41KB, Claude Code):

| Việc | Chi phí | Thời gian |
|---|---|---|
| `project-context` | $1.52 | ~2 phút |
| `prd` | $1.88 | ~8 phút |
| `architecture` | $2.78 | ~8 phút |
| `ux` (DESIGN + EXPERIENCE) | $3.71 | ~10 phút |
| `epics` (18 story) | $4.45 | ~12 phút |
| **mockup, mỗi màn hình** | **$1.5–2.3** | 3–5 phút |
| story backend, mỗi lượt thử | $2–2.7 | 6–15 phút |

Hai điều số này dạy:

* **Lập kế hoạch không rẻ** — ~$14 trước khi viết dòng code nào, và với dự
  án nhỏ đó là phần đắt nhất. Vì thế chi phí pha lập kế hoạch cũng phải vào
  bằng chứng, không chỉ chi phí story.
* **Mockup đắt hơn tưởng** ($2/màn) vì mỗi màn đọc lại DESIGN + EXPERIENCE +
  PRD. Dự án 20 màn hình là ~$40 — đủ để đáng cân nhắc dựng theo đợt và
  duyệt sớm, thay vì dựng hết rồi mới xem.

---

## 15. Xử lý thất bại

| Tình huống | Xử lý |
|---|---|
| Story trượt cổng | thử lại tối đa `max_retries`, mỗi lần kèm ghi chú lỗi cụ thể vào prompt |
| Vẫn trượt | đánh `blocked` + lý do; **đợt vẫn chạy tiếp** với story khác |
| Story phụ thuộc story `blocked` | cũng `blocked` (lan theo đồ thị), không chạy mù |
| Hết epic còn story `blocked` | **dừng, tổng hợp, chờ người** — không tự sang epic sau |
| Merge conflict cuối đợt | dừng, ghi evidence, báo người — là bằng chứng `write_scope` khai sai (mục 7.3) |
| Model lỗi / chạm hạn mức | backoff rồi thử lại; hết lượt thì `blocked` với lý do phân biệt rõ **lỗi hạ tầng** ≠ **lỗi chất lượng** |
| Ngắt giữa chừng | trạng thái ở đĩa; chạy lại tiếp đúng story dở (đã có trong scheduler) |

---

## 16. Nghiệm thu

**Theo 6 nhóm harness** — framework chỉ xong khi cả sáu ô có bằng chứng chạy:

| Nhóm | Bằng chứng |
|---|---|
| 1 Instructions | `compile` ra đủ client, golden test xanh, không skill offensive |
| 2 Tools | mỗi tool có test; prose "khi nào gọi" tồn tại |
| 3 Sandbox | test: tiến trình trong sandbox **không** ra được mạng, **không** ghi ngoài `write_scope` |
| 4 Orchestration | test: reviewer ≠ developer; hai story đụng scope không cùng đợt; resume đúng chỗ |
| 5 Guardrails | test: mỗi guard **chặn thật** ở đúng mốc |
| 6 Observability | mỗi evidence có cost + latency; `status` hiện tổng; eval phát hiện được trôi |

**Theo R1–R14:** mỗi R có ít nhất một test hoặc artifact chứng minh — bảng
đầy đủ ở `docs/REQUIREMENTS-EVIDENCE.md`, kèm một test đọc chính bảng đó và
trượt khi có dòng trỏ tới lớp test không còn tồn tại.

**Ai viết báo cáo:** `aisdlc report` sinh `docs/ACCEPTANCE-REPORT.md` từ
artifact và bằng chứng trên đĩa. Không mục nào viết tay — một báo cáo
nghiệm thu viết tay chỉ chứng minh người viết tin là mình đúng. Mục sandbox
ghi mức cách ly **quan sát được**, nên chạy suy biến thì báo cáo nói suy
biến.

**Đầu-cuối:** một dự án thật từ `docs/requirements.md` tới ứng dụng chạy được, với: mọi FR truy vết tới code và test · coverage ≥ ngưỡng · 0 high security · mockup khớp màn hình thật · chi phí và thời gian đo được từng story.

---

## 17. Bản 1 sai ở đâu

Ghi lại để không lặp lại:

| # | Vấn đề | Sửa |
|---|---|---|
| 1 | Tham chiếu `docs/design/`, `aisef/`, `adapter-compiler/` — đều đã bị xoá khi reset | Bỏ mục "giữ gì bỏ gì"; chỉ nói về cái đang tồn tại |
| 2 | **Không xử lý xung đột git/test khi chạy song song** | Thêm Đ5 + mục 7: worktree riêng, merge tuần tự |
| 3 | Dùng `.yaml` nhưng môi trường không có PyYAML | Chuyển sang JSON cho file máy sinh |
| 4 | Giả định về `claude -p`, OpenCode chưa kiểm chứng | Mục 2: kiểm chứng thật bằng `--help` |
| 5 | "ngưỡng" không có số | Mục 13: bảng cấu hình có mặc định |
| 6 | Không có chiến lược thất bại / retry | Mục 15 |
| 7 | Không ước tính chi phí của `fresh-session` | Mục 14 |
| 8 | Không rõ cổng người ở mức story hay pha | Mục 6: **mức pha**; story dùng cổng máy |
| 9 | Liệt kê công cụ verify chưa có trên máy | Mục 5.3: chạy trong container |
| 10 | Không nói merge conflict xử lý ra sao | Mục 7.3: là tín hiệu `write_scope` sai |
| 11 | Lộ trình không tách phần viết nội dung | Mục 18 |
| 12 | Không ghi phần nào đã làm xong | Đánh dấu ✅ ở mục 5, 6, 7, 8 |

---

## 18. Lộ trình

**Đã xong** (59 test xanh):

```
aisdlc/kit/skills.py            đọc SKILL.md, stdlib
aisdlc/kit/security_filter.py   lọc tầng 1: 818 → 269/207/342
aisdlc/control/approvals.py     8 cổng người duyệt
aisdlc/control/scheduler.py     epic tuần tự, story song song theo đợt
```

**Còn lại** — tách rõ code và nội dung, vì hai loại việc này không thay thế nhau:

| Tuần | Code | Nội dung |
|---|---|---|
| 1 | `state` · `worktree` · `detect_stack` · `catalog` · `install` | constitution · catalog entries |
| 2 | `clients/` + `compile` + golden test | — |
| 3 | `phases/plan` + normalizer + story splitter | 3 skill BMAD pipeline |
| 4 | `phases/mockup` + contract extract | 2 skill mockup |
| 5–6 | `harness/` 6 nhóm + `guardrails` 8 guard | PromptCatalog · 3 agent |
| 7 | `harness/observe.py` · `control/gate.py` · `phases/qa.py` | kiểm định theo hợp đồng story |
| 8 | `phases/deploy.py` | DevSecOps · runbook · cổng trước triển khai |
| 9 | chạy đầu-cuối trên dự án mẫu | hiệu chỉnh |

**≈ 9 tuần.** Bản 1 ghi 8 tuần vì quên phần viết nội dung (12 skill + 13 agent prompt).

---

## 19. Rủi ro

| Rủi ro | Mức | Chặn bằng |
|---|---|---|
| Hai story ghi đè nhau khi song song | **Cao** | scheduler so `write_scope` hai chiều ✅ + worktree riêng + guard |
| Client bypass hook | **Cao** | guard harness-side; `verify` kiểm lại độc lập, không tin client |
| Story quá lớn → tràn ngữ cảnh | **Cao** | ngưỡng ở mục 13, cổng Bước 2 chặn |
| Chi phí vượt dự kiến | **Cao** | đo trên epic mẫu trước; cost metering + cảnh báo 3× trung vị |
| Test xanh nhưng vô nghĩa | Trung bình | mutation gate |
| Agent trôi chất lượng âm thầm | Trung bình | eval trên bộ mẫu giữa các phiên bản |
| Lọt skill offensive | Trung bình | ✅ danh sách chặn + test bất biến |
| Mockup lệch tài liệu | Trung bình | thứ tự sự thật: architecture > ux-spec > design-contract; xung đột thì **dừng và báo** |
| BMAD nâng cấp làm vỡ override | Thấp | chỉ ghi `_bmad/custom/`; test hợp nhất sau nâng cấp |

---

## 20. Bất biến

1. Bằng chứng, không tự khai.
2. Một gốc artifact: `_bmad-output/`.
3. Xương sống kiến trúc `AR-x` thắng mọi nguồn khác.
4. Xung đột thì dừng và báo, không đoán.
5. Không `git add -A`; chỉ stage đúng đường dẫn story chạm.
6. Người viết code không tự duyệt code.
7. Chỉ ghi ở `_bmad/custom/`, không sửa file gốc BMAD.
8. Control plane không bao giờ là daemon.
9. Client không được tin — mọi đảm bảo nằm harness-side.
10. Thiếu cơ chế thì **khai báo**, không im lặng giả vờ đủ.
11. Không bước nào đi tiếp khi cổng phía trước chưa duyệt — trừ khi tự duyệt tường minh, và phải ghi là `auto`.
12. Story song song **luôn** ở worktree riêng; merge tuần tự.
13. Story có `screen_id` **luôn** đi qua hai nửa của bước map mockup; thiếu component contract đã hứa thì không PASS.
