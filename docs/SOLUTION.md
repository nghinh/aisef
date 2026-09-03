# AI-SDLC Framework — Giải pháp tổng thể

**Thay thế:** `IMPLEMENTATION-PLAN.md`, `design/V1-ARCHITECTURE.md` (xoá cả hai — tránh tài liệu chồng chéo).
**Giữ nguyên hiệu lực:** `design/adr/V1-DECISIONS.md`, `design/client-capability-matrix.md`, `design/client-adapter-contract.md`, `design/principles.md`.

---

## 1. Yêu cầu

Tổng hợp từ toàn bộ trao đổi, đánh số để nghiệm thu được:

| # | Yêu cầu |
|---|---|
| R1 | Đầu vào mỗi dự án là **một file** `docs/requirements.md` |
| R2 | Bộ prompt **chuẩn hoá**, dùng lại cho mọi dự án, không viết prompt lại từng lần |
| R3 | **Bước 1 Setup**: nạp BMAD + skills + agents + MCP + hooks + plugins vào dự án |
| R4 | **Bước 2**: dùng BMAD sinh PRD, Architecture, UX Spec, Epics, Stories — **mỗi story một file** |
| R5 | **Bước 3**: sinh Mockup (HTML) cho toàn bộ màn hình |
| R6 | **Bước 4**: coding agent hiện thực từng story, **map với mockup** |
| R7 | Coding agent phải đủ **6 nhóm harness** (mục 4) — không mượn DeepSeek harness / vnpt runtime |
| R8 | **Bước 5**: agents deep review · test (functional, SIT, E2E, UAT, performance) · security |
| R9 | **Bước 6**: agents DevSecOps |
| R10 | Chạy được trên **Claude Desktop · Claude CLI · OpenCode CLI** |
| R11 | Chuẩn hoá, chuyên nghiệp, hiện đại |
| R12 | Sản phẩm cuối **chất lượng và khớp yêu cầu** — chứng minh được, không tự khai |
| R13 | **Người duyệt từng bước**: PRD · Architecture · UX Spec · Epics · Stories · Mockups — mỗi bước dừng chờ xác nhận, **trừ khi truyền tham số tự duyệt** |

---

## 2. Nguyên tắc nền

> **Cần phán đoán → giao model. Cần đảm bảo → viết code.**

Hệ quả bắt buộc: **không nhờ thực thể bị giám sát tự giám sát nó.** Agent báo "test xanh" không phải bằng chứng; chỉ tiến trình bên ngoài chạy `pytest` và đọc exit code mới là bằng chứng. Toàn bộ R12 đứng trên câu này.

Bốn quyết định suy ra:

| Quyết định | Lý do |
|---|---|
| **Một phiên cho một story** (`fresh-session`) | Ngữ cảnh không tích luỹ ⇒ xoá bỏ toàn bộ rotation, capsule, resume-ACK, 11 mã blocker, SSE watch, đo usage mà vnpt phải viết |
| **Control plane là CLI gọi-một-lần, không daemon** | Điều kiện duy nhất để chạy được cả trong phiên chat (Desktop) lẫn headless (CLI/CI) → R10 |
| **Một nguồn `kit/` → compile ra từng client** | Không viết 3 bản độc lập → R10, R11 |
| **BMAD là dependency, không phải nền móng** | Contract của framework nằm giữa; BMAD lên đời chỉ sửa normalizer |

---

## 3. Giữ gì, bỏ gì

Đánh giá thẳng, không tiếc:

| Tài sản | Quyết định | Lý do |
|---|---|---|
| `aisef/` (1020 LOC) | **Bỏ cấu trúc, port ~600 LOC logic đúng** | Thiết kế cho *một task*, không phải *114 story*. `MockModelProvider` là giả. Nhưng `policy.py` (deny-by-default), `hooks.py`, `artifacts.py` (provenance), `telemetry.py`, `context_engine.py` (6 layer/9 stage) là đúng — port sang cấu trúc mới, không gò cái mới vào cái cũ |
| `adapter-compiler/` | **Giữ, gộp vào `aisdlc/clients/`** | Giải đúng bài toán R10; đã emit được claude/opencode/antigravity |
| `docs/design/` (ADR, matrix, contract, principles) | **Giữ nguyên** | Nghiên cứu G1–G4 nghiêm túc, ADR đã LOCKED |
| `docs/IMPLEMENTATION-PLAN.md`, `design/V1-ARCHITECTURE.md` | **Xoá** | Bị tài liệu này thay thế |
| `benchmarks/` | **Đóng băng** | ADR: maintenance mode, không phải gate |
| `references/` (19 repo) | **Giữ** | Nguyên liệu skill |
| `bin/aisdlc` | **Giữ tên, viết lại nội dung** | Tên lệnh đã đúng |

---

## 4. Xương sống: 6 nhóm harness

Đây là **thước nghiệm thu** của framework. Mọi thứ khác phục vụ sáu ô này.

### 4.1 Instructions & Rule Files
Văn bản định nghĩa agent là ai, quan tâm gì, cấm làm gì.

| Hạng mục | Hiện thực |
|---|---|
| Hiến pháp kỹ thuật | `kit/constitution/` → compile ra `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` theo client |
| Skill files | `kit/skills/` — 12 tự viết + import có pin: BMAD 22, superpowers 10, ui-ux 7, security 20 (lọc từ 818), karpathy 1 |
| Sub-agent prompts | `kit/agents/` — 13 agent |
| **PromptCatalog** | `kit/prompts/` — prompt vận hành từng pha, prompt-as-code, có version |

### 4.2 Tools
Hàm, MCP server, API — **cộng phần văn bản dạy model khi nào và cách gọi.**

| Hạng mục | Hiện thực |
|---|---|
| Tool thật | `harness/tools.py` — `read_file` `write_file` `run_test` `run_lint` `run_sast` `run_scan` `git_commit` `screenshot` |
| MCP | `kit/mcp/` — context7, serena, playwright ở chế độ **cli/on-demand** (ADR: không MCP-by-default) |
| **Prose quanh tool** | Mỗi tool có mục "khi nào gọi / cách đọc kết quả / khi nào KHÔNG gọi" trong `kit/skills/tool-usage/` |

### 4.3 Sandboxes & execution environments
Code chạy ở đâu, chạm được gì, **không** chạm được gì.

| Hạng mục | Hiện thực |
|---|---|
| Bậc quyền | `harness/sandbox.py` — 4 bậc: `READ_ONLY` → `WORKSPACE_WRITE` → `WORKSPACE_NETWORK` → `PRIVILEGED_TEST` |
| Bộ thực thi | Docker: `--network=none` mặc định, `--cap-drop=ALL`, chạy non-root, chỉ mount `write_scope` của story |
| Suy biến | Không có Docker → subprocess giới hạn + **ghi rõ mức bảo đảm thấp hơn**, không im lặng |

### 4.4 Orchestration logic
Sinh sub-agent, định tuyến model, bàn giao giữa chuyên gia, luật khi nào cái nào chạy.

| Hạng mục | Hiện thực |
|---|---|
| Định tuyến model | `harness/routing.py` — theo vai; **reviewer ≠ developer** (ADR-020) |
| Sinh sub-agent | `harness/subagent.py` — registry + spawn + thu kết quả |
| Bàn giao | `control/` — `next` → `implement` → `verify` → `review` → `complete` |
| Luật kích hoạt | `control/fsm.py` (vòng đời story) + `control/scheduler.py` (wave: `depends_on` + đụng `write_scope`) |

### 4.5 Guardrails / Hooks
Code tất định chạy tại mốc vòng đời — chỗ dành cho thứ agent **không được phép quên**.

| Mốc | Guard | Chặn gì |
|---|---|---|
| before tool call | `write-scope` | ghi ngoài phạm vi story |
| before tool call | `destructive` | `rm -rf`, `git reset --hard`, `checkout --` |
| **after file edit** | `diff-scope` | file không liên quan bị chạm |
| **before commit** | `secret` | khoá/mật khẩu/token lọt vào |
| **before commit** | `git-stage` | `git add -A` |
| before commit | `injection` | SQL nối chuỗi, `dangerouslySetInnerHTML` |
| on stop | `completion` | kết thúc khi test chưa xanh |

Mỗi guard là **một lệnh độc lập trả exit code** → nối được vào mọi client (mục 7).

### 4.6 Observability
Không đo thì không biết agent đang tốt hay đang **âm thầm trôi**.

| Hạng mục | Hiện thực |
|---|---|
| Log, trace | `harness/observe.py` — sự kiện có cấu trúc, provenance |
| **Cost & latency** | token in/out, USD, giây — **ghi vào mỗi `evidence/{story}.json`**, cộng dồn theo epic; cảnh báo khi story vượt n× trung vị |
| Evaluation | `harness/eval.py` — chấm skill/prompt trên bộ mẫu, phát hiện trôi chất lượng giữa các phiên bản |
| Dashboard | `aisdlc status` — tiến độ, chi phí, thời gian, tỷ lệ gate trượt |

---

## 4bis. Cổng người duyệt (R13)

Có **hai loại cổng**, chạy nối tiếp — máy kiểm trước để khỏi phí thời gian người:

| | Cổng máy | Cổng người |
|---|---|---|
| Kiểm gì | schema hợp lệ, không chu trình phụ thuộc, mọi FR được phủ, story không quá lớn | nội dung có đúng ý không |
| Ai chạy | tự động | người, bằng lệnh |
| Trượt thì | dừng, báo lỗi cụ thể | ghi `changes_requested` kèm ghi chú, sinh lại |

### Nguyên tắc: phê duyệt là **trạng thái trên đĩa**, không phải câu hỏi tương tác

Đây là điều kiện để cùng một cơ chế chạy được ở mọi nơi:
- chạy nền / CI — không có ai ngồi trước màn hình để trả lời;
- trong phiên chat (Claude Desktop) — agent không thể "đợi" người gõ;
- người duyệt có thể là **người khác, lúc khác, máy khác**.

Luồng: pipeline chạy tới cổng → ghi `pending` rồi **dừng** → người `approve`/`reject` → chạy lại thì đi tiếp.

### Tám cổng

`prd` → `architecture` → `ux-spec` → `epics` → `stories` → `mockups` → `readiness` (trước khi viết code) → `pre-deploy` (trước khi triển khai)

### Hai bảo đảm

1. **Phê duyệt gắn với nội dung, không gắn với tên cổng.** Bản ghi lưu SHA-256 của artifact; sửa file sau khi duyệt thì phê duyệt tự động hết hiệu lực (`stale`).
2. **Sửa tầng trên làm mất hiệu lực tầng dưới.** Duyệt lại PRD thì Architecture, UX, Epics, Stories, Mockups đã duyệt đều thành `stale` — chúng được duyệt dựa trên một bản PRD không còn nữa. Thứ tự quyết định so bằng **số thứ tự đơn điệu**, không bằng đồng hồ (bản ghi đi qua git giữa nhiều máy, đồng hồ không đáng tin).

### Tự duyệt

```
--auto-approve all                  bỏ qua mọi cổng (CI, chạy thử)
--auto-approve prd,architecture     chỉ bỏ qua cổng đã nêu
```

Quyết định tự động luôn ghi `decided_by: auto`, để về sau **truy được artifact nào chưa từng có người thật xem qua**.

---

## 5. Cấu trúc

```
aisdlc/                          ← framework, một package Python duy nhất
│
├── kit/                         ← NHÓM 1: nội dung chuẩn hoá (nguồn canonical)
│   ├── catalog.yaml             sổ đăng ký skill + pin version + lý do chọn
│   ├── constitution/            hiến pháp → CLAUDE.md / AGENTS.md / GEMINI.md
│   ├── skills/                  skill ta viết + import có pin
│   ├── agents/                  13 sub-agent prompt
│   ├── prompts/                 PromptCatalog (prompt-as-code, versioned)
│   ├── hooks/                   khai báo mốc → lệnh guard
│   └── mcp/                     cấu hình MCP (cli/on-demand)
│
├── harness/                     ← NHÓM 2–6: harness là code
│   ├── tools.py                 tool thật + schema
│   ├── sandbox.py               Docker executor, 4 bậc quyền
│   ├── routing.py               định tuyến model theo vai
│   ├── subagent.py              registry + spawn
│   ├── guardrails.py            7 guard, 3 mốc vòng đời
│   ├── observe.py               trace + cost + latency
│   ├── eval.py                  chấm chất lượng, phát hiện trôi
│   └── context.py               6 layer, 9 stage, provider fresh-session
│
├── control/                     ← điều phối NHIỀU story
│   ├── state.py                 sprint-status.yaml, khoá file, resume
│   ├── fsm.py                   pending→running→verifying→done|blocked
│   ├── scheduler.py             wave: topo-sort + đụng write_scope
│   ├── evidence.py              chạy thật, thu bằng chứng
│   └── gate.py                  4 điều kiện, chặn thật
│
├── clients/                     ← R10: đa client
│   ├── base.py                  ClientAdapter (run · guard-wire · capability)
│   ├── claude_code.py           Desktop + CLI
│   ├── opencode.py              OpenCode CLI
│   └── compile.py               kit/ → .claude/ · .opencode/ · .agents/
│
├── phases/                      ← 6 bước
│   ├── setup.py  plan.py  mockup.py  implement.py  verify.py  ship.py
│
└── cli.py
```

**Sinh ra trong dự án đích:**

```
dự-án/
├── docs/requirements.md         ← đầu vào duy nhất (R1)
├── .ai/                         canonical (compile từ kit)
├── .claude/  .opencode/         generated — không sửa tay
├── _bmad/custom/*.toml          override agent BMAD
├── _bmad-output/                MỘT gốc artifact
│   ├── prd.md  architecture.md  ux-spec.md  epics.md
│   ├── stories/EPIC-01/STORY-01-01.md …      ← mỗi story 1 file (R4)
│   ├── stories.index.yaml       metadata máy đọc
│   ├── design-contract.json     hợp đồng thị giác
│   ├── evidence/{story}.json    bằng chứng + cost + latency
│   └── sprint-status.yaml       trạng thái, resume được
├── mockups/*.html               (R5)
└── src/  tests/
```

---

## 6. Bộ lệnh

```
# Bước 1
aisdlc setup   --project DIR          nạp kit vào dự án
aisdlc compile --client claude|opencode
aisdlc doctor                         kiểm tra sau cài

# Bước 2–3 — dừng ở mỗi cổng chờ người duyệt
aisdlc plan                           BMAD pipeline → _bmad-output/
aisdlc plan --auto-approve all        chạy thẳng, không dừng
aisdlc mockup                         HTML + screenshot + design-contract.json

# Cổng người duyệt (R13)
aisdlc gates                          bảng trạng thái 8 cổng
aisdlc review  prd                    mở artifact + checklist review
aisdlc approve prd [--note "..."]
aisdlc reject  prd  --note "cần sửa..."   (bắt buộc có ghi chú)

# Bước 4
aisdlc next                           → story kế tiếp (JSON)
aisdlc implement STORY-ID --client X
aisdlc verify   STORY-ID              chạy test/scan THẬT → verdict
aisdlc complete STORY-ID
aisdlc run [--epic E] --client X      vòng lặp 4 lệnh trên

# Guard — client gọi vào tại mốc vòng đời
aisdlc guard write-scope --story S --path P
aisdlc guard diff-scope  --story S
aisdlc guard secret      --staged
aisdlc guard git-stage   --cmd "..."

# Bước 5–6
aisdlc review STORY-ID                reviewer ≠ developer
aisdlc test   --kind unit|sit|e2e|uat|perf|api|mutation
aisdlc ship                           container · CI · SBOM · IaC · runbook
aisdlc status                         tiến độ · chi phí · độ trễ · tỷ lệ trượt gate
```

---

## 7. Đa client (R10)

**Trục nội dung** — một nguồn, nhiều đích:

```
kit/  ──► aisdlc compile ──┬──► .claude/    (Desktop + CLI)
                            ├──► .opencode/
                            └──► .agents/    (Antigravity — sau)
```
Bắt buộc: deterministic · idempotent · golden round-trip test · **khai báo loss** khi client thiếu cơ chế.

**Trục điều khiển** — cùng bộ lệnh, hai chế độ:

| | Driver-led | Agent-led |
|---|---|---|
| Ai gọi | script / CI | chính agent, qua Bash |
| Chỗ chạy | terminal, cron | **Claude Desktop**, Claude CLI, OpenCode CLI |
| Lệnh | `aisdlc run --client X` | `aisdlc next` → làm → `aisdlc verify S` → `aisdlc complete S` |

`run` chỉ là vòng lặp gọi lại chính các lệnh đơn — **không có code riêng cho mỗi chế độ**.

**Nối guard theo client:**

| Client | Cách nối | Mức |
|---|---|---|
| Claude Code (Desktop + CLI) | `settings.json` hooks → `aisdlc guard …` | tiền kiểm — chặn ngay lúc ghi |
| OpenCode | plugin → `aisdlc guard …` | tiền kiểm |
| Client thiếu hook | `aisdlc verify` chạy lại toàn bộ guard | hậu kiểm — yếu hơn, **ghi vào compile report** |

**Phạm vi V1:** Claude Code + OpenCode (matrix ghi `N` ở mọi cơ chế cần). Antigravity hoãn — còn nhiều `?`, không khai hỗ trợ thứ chưa test.

---

## 8. Sáu bước

### Bước 1 — Setup (R3)
Dò stack từ `requirements.md` → chọn skill theo `catalog.yaml` → **lọc 818 skill security xuống ~20 appsec** (loại red-team/ICS/darkweb, có test danh sách chặn) → cài vào dự án → compile ra client → `doctor`.

**Xong khi:** `doctor` trả 0 · đếm đúng số skill · không skill offensive nào lọt · chạy lại không nhân bản.

### Bước 2 — BMAD sinh tài liệu (R4)
`project-context → prd → architecture → ux → epics-and-stories → sprint-planning`, mỗi pha một cổng. **Tách mỗi story một file** + trích `stories.index.yaml` (`depends_on`, `write_scope`, `FR-xx`, `AR-xx`, `screen_id`, `slice`).

**Xong khi:** mỗi story một file có AC + `write_scope` · index parse được · đồ thị phụ thuộc không chu trình · **mọi FR trong PRD được ít nhất một story phủ** · không story nào vượt ngưỡng kích thước (chống tràn ngữ cảnh) · **cổng `prd`, `architecture`, `ux-spec`, `epics`, `stories` đều `approved`** (hoặc tự duyệt tường minh).

### Bước 3 — Mockup (R5)
`ux-spec` + `ui-ux-pro-max` → `mockups/{screen}.html` → screenshot → trích `design-contract.json` → map story ↔ `screen_id`.

**Xong khi:** mỗi màn hình trong ux-spec có đúng một mockup mở được · contract hợp lệ schema, không mục treo · mọi story frontend map tới `screen_id` có thật · **cổng `mockups` `approved`**.

### Bước 4 — Coding agent (R6, R7)
Với mỗi story: phiên mới → nạp story + `design-contract` + `AR-x` → RED → GREEN → VERIFY → commit mang `FR-xx`. Guard chặn tại 3 mốc vòng đời. Sandbox Docker cho test. Wave cho story độc lập.

**Xong khi:** guard **chặn thật** (test: ghi ngoài scope bị từ chối; secret bị từ chối; `git add -A` bị từ chối) · hai story đụng `write_scope` **không** vào cùng wave · chạy hết một epic ≥5 story trên `references/teamflow` · dừng giữa chừng chạy lại tiếp đúng story dở · **cổng `readiness` `approved` trước khi story đầu tiên chạy**.

### Bước 5 — Kiểm định (R8, R12)
| Loại | Chạy thật bằng |
|---|---|
| Deep review | agent ngữ cảnh sạch, **khác người viết code** |
| Functional / unit | pytest · jest · vitest + coverage |
| SIT | docker-compose dựng phụ thuộc thật |
| API contract | schemathesis (property-based trên OpenAPI) |
| E2E | Playwright — **đối chiếu màn hình thật với mockup** |
| UAT | kịch bản sinh từ AC, chạy theo hành trình người dùng |
| Performance | k6 (API) + Lighthouse (web), ngưỡng lấy từ NFR trong PRD |
| Security | Semgrep + Trivy + quét secret + đối chiếu threat model |
| Mutation | mutmut — bắt test xanh mà vô nghĩa |

**Cổng story — PASS chỉ khi đủ bốn, mỗi thứ là bằng chứng chạy thật:**
1. Test xanh, coverage ≥ ngưỡng
2. Review APPROVED bởi agent khác người viết
3. Security 0 phát hiện high/critical
4. Truy vết: commit mang `FR-xx`, nối được code ↔ story ↔ requirement

### Bước 6 — DevSecOps (R9)
Dockerfile · compose · CI/CD gắn đúng cổng Bước 5 · SBOM CycloneDX · quét image · k8s/Terraform · metric + log + alert · runbook (triệu chứng → chẩn đoán → xử lý → leo thang) · cổng tiền-triển-khai.

**Xong khi:** `docker build` chạy được · CI **chặn** khi có story fail · SBOM sạch high · runbook đủ 4 mục · **cổng `pre-deploy` `approved`**.

---

## 9. Vòng đời một story

```
aisdlc next
  ├ đọc stories.index.yaml + sprint-status.yaml
  ├ topo-sort depends_on · loại story đụng write_scope với story đang chạy
  └ → STORY-01-02 {AC, write_scope, screen_id, arch_refs, slice}

aisdlc implement STORY-01-02 --client claude-cli
  ├ PromptCatalog dựng prompt: story + design-contract + AR-x + hiến pháp
  ├ spawn phiên MỚI, ngữ cảnh sạch
  ├ guard chặn tại 3 mốc: before-tool · after-edit · before-commit
  ├ test chạy trong Docker (network=none, cap-drop, non-root)
  ├ agent RED → GREEN → VERIFY, commit mang FR-xx
  └ ghi cost + latency

aisdlc verify STORY-01-02
  ├ chạy THẬT: pytest --cov · semgrep · trivy · e2e (nếu có screen_id)
  ├ dispatch reviewer (ngữ cảnh sạch, khác người viết)
  ├ 4 điều kiện
  └ → evidence/STORY-01-02.json {verdict, coverage, findings, cost, latency}

aisdlc complete STORY-01-02
  ├ PASS  → done · cập nhật sprint-status
  └ FAIL  → blocked + lý do · story quay lại hàng đợi
```

---

## 10. Nghiệm thu

**Theo 6 nhóm harness** — framework chỉ được coi là xong khi cả sáu ô đều có bằng chứng chạy:

| Nhóm | Bằng chứng nghiệm thu |
|---|---|
| 1. Instructions | `compile` ra đủ client, golden test xanh, skill đếm đúng, không skill offensive |
| 2. Tools | mỗi tool có test; prose "khi nào gọi" tồn tại cho từng tool |
| 3. Sandbox | test: tiến trình trong sandbox **không** ra được mạng, **không** ghi được ngoài `write_scope` |
| 4. Orchestration | test: reviewer ≠ developer; hai story đụng scope không cùng wave; resume đúng story dở |
| 5. Guardrails | test: mỗi guard trong 7 guard **chặn thật** ở đúng mốc |
| 6. Observability | mỗi `evidence/{story}.json` có cost + latency; `status` hiện tổng; eval phát hiện được trôi chất lượng |

**Theo yêu cầu R1–R12:** mỗi R có ít nhất một test hoặc một artifact chứng minh.

**Đầu-cuối:** một dự án thật đi từ `docs/requirements.md` tới ứng dụng chạy được, với: mọi FR truy vết được tới code và test · coverage ≥ ngưỡng · 0 high security · mockup khớp màn hình thật · chi phí và thời gian đo được từng story.

---

## 11. Quy mô và lộ trình

```
port từ aisef (policy, hooks, artifacts, telemetry, context)     ~600 LOC
kit: 12 skill tự viết · 13 agent · PromptCatalog · catalog        (nội dung)
harness: tools, sandbox, routing, subagent, guardrails,
         observe, eval, context                                  ~1300 LOC
control: state, fsm, scheduler, evidence, gate                    ~900 LOC
clients: base, claude_code, opencode, compile                     ~500 LOC
phases: setup, plan, mockup, implement, verify, ship              ~600 LOC
cli                                                               ~200 LOC
                                                                 ─────────
                                                                 ~4100 LOC
```

| Tuần | Việc | Cột mốc |
|---|---|---|
| 1 | Bước 1 + `clients/` + compile | Nạp kit vào dự án trống, golden test xanh |
| 2 | Bước 2 | Mỗi story một file, index không chu trình |
| 3 | Bước 3 | Mockup + design-contract khớp ux-spec |
| 4–5 | **Bước 4 + harness 6 nhóm** | Chạy hết một epic thật, guard chặn thật |
| 6 | Bước 5 | Cổng chặn được story lỗi |
| 7 | Bước 6 | Triển khai được |
| 8 | Đầu-cuối | Một dự án thật từ `requirements.md` |

**≈ 8 tuần.**

---

## 12. Rủi ro

| Rủi ro | Mức | Chặn bằng |
|---|---|---|
| Hai story ghi đè nhau khi song song | **Cao** | wave so `write_scope` hai chiều + guard mức chặn |
| Client bypass hook (bài học baseline auto-accept) | **Cao** | guard harness-side; `verify` kiểm lại độc lập, không tin client |
| Story quá lớn → tràn ngữ cảnh trong một phiên | **Cao** | cổng Bước 2 chặn story vượt ngưỡng, buộc chẻ nhỏ |
| Test xanh nhưng vô nghĩa | Trung bình | mutation gate |
| Chi phí vượt tầm kiểm soát | Trung bình | cost metering per story + cảnh báo n× trung vị |
| Agent trôi chất lượng âm thầm | Trung bình | eval trên bộ mẫu giữa các phiên bản skill/prompt |
| Lọt skill offensive | Trung bình | danh sách chặn + test khẳng định |
| Mockup lệch tài liệu | Trung bình | thứ tự sự thật: architecture > ux-spec > design-contract; xung đột thì **dừng và báo** |
| BMAD nâng cấp làm vỡ override | Thấp | chỉ ghi `_bmad/custom/`; test hợp nhất sau nâng cấp |

---

## 13. Bất biến

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
11. Không bước nào đi tiếp khi cổng phía trước chưa duyệt — trừ khi tự duyệt được truyền tường minh, và khi đó phải ghi lại là `auto`.
