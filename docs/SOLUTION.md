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
| Sub-agent prompts | `kit/agents/` — 13 agent |
| PromptCatalog | `kit/prompts/` — prompt vận hành từng pha, có version, có test |

### 5.2 Tools
| Hạng mục | Hiện thực |
|---|---|
| Tool thật | `harness/tools.py` — `read_file` `write_file` `run_test` `run_lint` `run_sast` `run_scan` `git_commit` `screenshot` |
| MCP | `kit/mcp/` — context7 · serena · playwright ở chế độ **cli/on-demand**, không bật mặc định |
| **Prose quanh tool** | mỗi tool có mục "khi nào gọi / cách đọc kết quả / khi nào KHÔNG gọi" |

### 5.3 Sandboxes & execution environments
| Hạng mục | Hiện thực |
|---|---|
| Bậc quyền | `READ_ONLY` → `WORKSPACE_WRITE` → `WORKSPACE_NETWORK` → `PRIVILEGED_TEST` |
| Bộ thực thi | Docker: `--network=none` mặc định · `--cap-drop=ALL` · non-root · chỉ mount worktree của story |
| Công cụ verify | chạy **trong image**, không cài lên máy host (giải quyết việc thiếu pytest/semgrep/trivy/k6) |
| Suy biến | Không có Docker → subprocess giới hạn + **ghi rõ mức bảo đảm thấp hơn** vào evidence |

### 5.4 Orchestration logic
| Hạng mục | Hiện thực |
|---|---|
| Định tuyến model | `harness/routing.py` — theo vai; **reviewer ≠ developer** |
| Sinh sub-agent | `harness/subagent.py` |
| Bàn giao | `next` → `implement` → `verify` → `review` → `complete` |
| Luật kích hoạt | `control/fsm.py` + `control/scheduler.py` ✅ **đã xong** |

### 5.5 Guardrails / Hooks
| Mốc | Guard | Chặn gì |
|---|---|---|
| before tool call | `write-scope` | ghi ngoài phạm vi story |
| before tool call | `destructive` | `rm -rf`, `git reset --hard`, `checkout --` |
| after file edit | `diff-scope` | file không liên quan bị chạm |
| before commit | `secret` | khoá/mật khẩu/token |
| before commit | `git-stage` | `git add -A` |
| before commit | `injection` | SQL nối chuỗi, `dangerouslySetInnerHTML` |
| on stop | `completion` | kết thúc khi test chưa xanh |

Mỗi guard là **một lệnh độc lập trả exit code** → nối được vào mọi client.

### 5.6 Observability
| Hạng mục | Hiện thực |
|---|---|
| Log, trace | sự kiện có cấu trúc, có provenance |
| **Cost & latency** | token in/out · USD · giây — ghi vào mỗi `evidence/{story}.json`, cộng dồn theo epic |
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
│   ├── tools.py  sandbox.py  routing.py  subagent.py
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
└── cli.py
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
│   ├── prd.md  architecture.md  ux-spec.md  epics.md
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

```
# Setup
aisdlc setup   --project DIR
aisdlc compile --client claude|opencode
aisdlc doctor

# Tài liệu & mockup — dừng ở mỗi cổng
aisdlc plan    [--auto-approve all|<danh sách>]
aisdlc mockup

# Cổng người duyệt
aisdlc gates                          bảng trạng thái 8 cổng
aisdlc review  <gate>                 artifact + checklist
aisdlc approve <gate> [--note ...]
aisdlc reject  <gate>  --note "..."   (bắt buộc ghi chú)

# Hiện thực
aisdlc next                           story kế tiếp
aisdlc implement <story> --client X
aisdlc verify   <story>               chạy test/scan THẬT
aisdlc complete <story>
aisdlc run --epic E | --all  --client X  [--max-parallel 3] [--sequential]

# Guard — client gọi vào tại mốc vòng đời
aisdlc guard write-scope|diff-scope|secret|git-stage|destructive ...

# Kiểm định & giao hàng
aisdlc review  <story>                reviewer ≠ developer
aisdlc test    --kind unit|sit|e2e|uat|perf|api|mutation
aisdlc ship
aisdlc status                         tiến độ · chi phí · độ trễ · tỷ lệ trượt gate
```

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
| OpenCode CLI | plugin → `aisdlc guard …` | **hậu kiểm** | ✅ quyết định: chấp nhận mức này |
| OpenCode Desktop | cùng cấu hình dự án với CLI | **hậu kiểm** | ✅ quyết định: chấp nhận mức này |
| Bất kỳ, nếu hook không gắn được | `aisdlc verify` chạy lại toàn bộ guard | hậu kiểm | ✅ luôn có |

**Quyết định (2026-09-04): OpenCode chạy ở mức hậu kiểm.** Spike S4 không chạy xong được ca thử, và thay vì đầu tư thêm để chứng minh, chủ đầu tư chấp nhận mức bảo đảm thấp hơn cho hai bề mặt OpenCode. Hệ quả cụ thể:

* plugin vẫn được sinh và vẫn gọi đúng bộ guard — nếu nó chặn được thì tốt, nhưng framework **không dựa vào điều đó**;
* `aisdlc verify` chạy lại toàn bộ guard trên diff của story, nên vi phạm vẫn bị bắt, chỉ là bắt **sau khi đã ghi** thay vì chặn lúc ghi;
* `compile-report.json` ghi `blocks_at_source: false` cho OpenCode, để mức bảo đảm thật luôn tra được, không phải nhớ.

Đổi lại quyết định này chỉ cần một phép thử thành công: chạy `opencode run` với provider phản hồi nhanh và xem hook có chặn không.

**Phạm vi V1:** 4 bề mặt của Claude Code và OpenCode (mục 2.1). Antigravity hoãn — chưa test được.

---

## 12. Sáu bước

| Bước | Nội dung | Xong khi |
|---|---|---|
| **1 Setup** | dò stack → chọn skill theo catalog → lọc security 2 tầng → cài → compile → doctor | `doctor` trả 0 · đếm đúng số skill · **không skill offensive nào lọt** · chạy lại không nhân bản |
| **2 BMAD** | `project-context → prd → architecture → ux → epics-and-stories → sprint-planning`, mỗi pha một cổng; tách mỗi story một file + `stories.index.json` | index parse được · không chu trình · **mọi FR được ≥1 story phủ** · không story vượt ngưỡng · 5 cổng `approved` |
| **3 Mockup** | ux-spec + ui-ux-pro-max → HTML → screenshot → `design-contract.json` | mỗi màn hình có đúng một mockup mở được · contract không mục treo · story frontend map tới `screen_id` thật · cổng `mockups` `approved` |
| **4 Implement** | phiên mới mỗi story · worktree riêng · **map mockup (mục 12bis)** · RED→GREEN→VERIFY · guard 3 mốc · merge tuần tự cuối đợt | guard **chặn thật** (3 test) · hai story đụng scope không cùng đợt · chạy hết 1 epic ≥5 story · dừng giữa chừng resume đúng chỗ · cổng `readiness` `approved` |
| **5 Verify** | review sâu · unit · SIT · API contract · E2E · UAT · perf · security · mutation | mỗi loại chạy thật, trả kết quả máy đọc · cổng **chặn thật** khi đẩy story lỗi |
| **6 Ship** | container · CI/CD · SBOM · IaC · observability · runbook | `docker build` chạy · CI chặn khi story fail · SBOM sạch high · runbook đủ 4 mục · cổng `pre-deploy` `approved` |

**Cổng story (Bước 4–5) — PASS chỉ khi đủ, mỗi thứ là bằng chứng chạy thật:**
1. Test xanh, coverage ≥ ngưỡng
2. Review APPROVED bởi agent khác người viết
3. Security 0 phát hiện high/critical
4. Truy vết: commit mang `FR-xx`, nối được code ↔ story ↔ requirement
5. **Khớp mockup** — chỉ áp cho story có `screen_id` (mục 12bis)

---

## 12bis. Map với mockup — bước bắt buộc của story có giao diện

Story nào có `screen_id` phải đi qua **hai nửa** của bước map. Thiếu nửa nào cũng không tính là xong.

### Nửa trước khi code — nạp hợp đồng thị giác

Prompt của story được bổ sung, không phải để tham khảo mà là ràng buộc:

| Nạp gì | Từ đâu |
|---|---|
| Lát cắt contract của đúng màn hình đó | `design-contract.json#screens[screen_id]` |
| Mockup HTML | `mockups/{screen_id}.html` |
| Ảnh chụp mockup | `mockups/screenshots/{screen_id}.png` |
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
| **Cấu trúc** | component trong contract có mặt trong DOM thật | **CHẶN** — tất định, lặp lại được |
| Thị giác bằng model | reviewer nhìn hai ảnh, ghi nhận xét | cảnh báo, không chặn |
| ~~Pixel diff~~ | so ảnh từng điểm ảnh | **không dùng** |

Không dùng pixel diff vì mockup HTML tĩnh và ứng dụng thật không bao giờ trùng từng điểm ảnh; gate kiểu đó đỏ liên tục, rồi người ta tắt nó đi — một cổng bị tắt còn tệ hơn không có cổng.

### Kết quả ghi vào evidence

```json
"mockup_map": {
  "screen_id": "SCREEN-03",
  "route": "/login",
  "contract_components": 7,
  "matched": 7,
  "missing": [],
  "extra": ["banner-promo"],
  "screenshot_mockup": "mockups/screenshots/SCREEN-03.png",
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
| `coverage.min` | `0.85` | coverage tối thiểu để story PASS |
| `story.max_acceptance_criteria` | `8` | quá thì Bước 2 buộc chẻ nhỏ |
| `story.max_write_scope_paths` | `10` | story chạm quá nhiều nơi là dấu hiệu quá lớn |
| `story.max_context_tokens` | `40000` | ước tính ngữ cảnh phải nạp; vượt thì chẻ nhỏ |
| `run.max_parallel` | `3` | số story song song trong một đợt |
| `run.max_turns` | `40` | vòng lặp tối đa của một phiên story |
| `run.timeout_seconds` | `1800` | 30 phút cho một story |
| `run.max_retries` | `2` | số lần thử lại trước khi `blocked` |
| `cost.warn_multiple` | `3.0` | cảnh báo khi story tốn > 3× trung vị |
| `security.block_severities` | `["critical","high"]` | mức chặn merge |

---

## 14. Chi phí

Đ1 (mỗi story một phiên sạch) đánh đổi token lấy sự đơn giản. Phải đo, không đoán.

**Ngữ cảnh nạp mỗi story:** hiến pháp + architecture (phần liên quan) + story + design-contract (nếu có UI) + code trong `write_scope`. Đây là lý do có `story.max_context_tokens`.

**Giảm chi phí:**
- Chỉ nạp phần architecture mà `arch_refs` của story trỏ tới, không nạp cả file.
- Chỉ nạp code trong `write_scope` và các file nó import trực tiếp.
- Reviewer là phiên riêng, ngữ cảnh sạch → **nhân đôi chi phí mỗi story**; đây là cái giá của "reviewer ≠ developer" và không cắt được.

**Bắt buộc:** ghi `cost` + `latency` vào mỗi `evidence/{story}.json`, cộng dồn theo epic. **Đo trên một epic mẫu trước khi chạy toàn bộ** — con số thật của dự án bạn không suy ra được từ lý thuyết.

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

**Theo R1–R14:** mỗi R có ít nhất một test hoặc artifact chứng minh.

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
| 5–6 | `harness/` 6 nhóm + `guardrails` 7 guard | PromptCatalog · 3 agent |
| 7 | `evidence` · `gate` · `phases/verify` | 5 agent kiểm định |
| 8 | `phases/ship` | 3 agent DevSecOps · runbook |
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
