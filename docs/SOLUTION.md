# AISEF (AI Software Engineering Framework) — Giải pháp tổng thể

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
| Claude Desktop | `/Applications/Claude.app` ✅ | agent-led | agent gọi `aisef` qua Bash tool |
| Claude CLI | `claude` 2.1.236 ✅ | cả hai | tương tác: qua Bash · headless: `claude -p` |
| OpenCode Desktop | `/Applications/OpenCode.app` ✅ | agent-led | agent gọi `aisef` qua Bash tool |
| OpenCode CLI | `opencode` ✅ | cả hai | TUI/web: qua Bash · headless: `opencode run` |

OpenCode còn có `serve` (server headless) + `attach`/`web` — nhiều client nối vào một server. Hữu ích về sau, **không cần cho V1**.

> `opencode --auto` (tự duyệt mọi quyền) **không dùng**: ta không tin cơ chế quyền của client, guard nằm ở harness (bất biến 9).

### 2.2 Năng lực từng engine


| Năng lực cần | Claude Code 2.1.236 | OpenCode | Kết luận |
|---|---|---|---|
| Chạy headless | `-p / --print` | `run`, `serve` | ✅ |
| Đọc kết quả máy | `--output-format stream-json` | `--format json` (đo 2026-09-05) | ✅ |
| Nạp hook | `--settings <file\|json>` | `plugin` | ✅ |
| Custom agent | `--agents <json>` | `agent` | ✅ |
| Giới hạn tool | `--allowed-tools` / `--disallowed-tools` | permission config | ✅ |
| **Giới hạn thư mục** | `--add-dir` | — | ✅ Claude; OpenCode dùng guard |
| Định tuyến model | `--model` | `models` | ✅ |
| **Cost / token** | usage trong stream-json | `step_finish` trong `--format json` (đo 2026-09-05) | ✅ |
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
| Tool thật | `harness/tools.py` — ba tool có bằng chứng `test` · `lint` · `sast` (agent gọi `aisef tool <tên> --story S`; lệnh từ `tools.*` hoặc tự dò), phân biệt **không chạy được** với đỏ (lỗi 8); `test:baseline` là lần test do harness ghi trước phiên developer (ADR-004 R9); `harness/testlog.py` đọc tên test từ năm định dạng — node `spec`/`tap`, vitest verbose, `pytest -v`, **CTRF** JSON (ADR-005 V9; `doctor` gợi reporter khi bằng chứng ghi `test_format=""`). Đọc/ghi tệp là tool của client (guard chặn); commit ứng viên do harness làm (`phases/implement.py::freeze_candidate`); route thật/ảnh chụp qua `harness/browser.py`. Đầu ra `aisef tool` có cấu trúc (ADR-005 V11 A): tóm tắt `testlog` (xanh/đỏ/bỏ qua, ≤ 20 tên test đỏ) → `tail` → "(lược N/M dòng — toàn văn: `_bmad-output/evidence/<story>-<tool>-<seq>.log`)" khi output dài hơn `--lines`; `tail` trong evidence giữ 20 dòng, toàn văn ở tệp `.log` chỉ ghi khi có cắt. `tail`, log và `qa:*` đều đã che bí mật `[REDACTED]` (`guardrails.scrub_secrets`, ADR-005 V1) |
| MCP | không có — quyết định V1: không MCP thường trú; playwright dùng qua CLI trong `harness/browser.py`, tra cứu tài liệu theo yêu cầu là việc đợt 5 (`aisef doc`) |
| **Prose quanh tool** | mỗi tool có mục "khi nào gọi / cách đọc kết quả / khi nào KHÔNG gọi" |

### 5.3 Sandboxes & execution environments
| Hạng mục | Hiện thực |
|---|---|
| Bậc quyền | `READ_ONLY` → `WORKSPACE_WRITE` → `WORKSPACE_NETWORK` → `PRIVILEGED_TEST` |
| Bộ thực thi | `ExecutionProvider` (ADR-005 V5, `harness/sandbox.py`): `docker` mặc định (`--network=none` theo bậc · `--cap-drop=ALL` · non-root · chỉ mount worktree của story · `-e` chỉ mang `spec.env`) · `local` (chạy thẳng) · `fake` (test, kịch bản) · backend ngoài `"mô-đun:Lớp"` qua knob `sandbox.provider`. Một lệnh một lần chạy, không session. **Suite đơn vị không mở container**: `tests/__init__.py` đặt `HostProvider` (chạy thật trên máy, khai NATIVE — giả lập cách ly, chỉ cho test) vào chỗ `docker`, vì test đơn vị kiểm luật của harness chứ không kiểm Docker; `python3 -m unittest discover -s tests -q` chạy vài phút thay vì 25–60. Docker thật ở test đánh dấu `needs_docker` (`AISEF_TEST_DOCKER=1 python3 -m unittest tests.test_sandbox tests.test_tools`) và hợp quy S1–S5; `host`/`fake` không phải lựa chọn của dự án (`doctor` từ chối tên ấy) |
| Bảo đảm có tên | `Guarantee` = `network_none` · `read_only_fs` · `non_root` · `no_host_mount` · `secrets_absent`. Bậc khai **cần** (`Level.requires()`), provider khai **có** (`guarantees(level)` → `Support` native/emulated/post_hoc/unsupported của `clients/base.py`, đọc tên thật). Kiểm bằng lần chạy thật: `docs/SANDBOX-CONFORMANCE.md` S1–S5, mỗi provider một cột (`python3 -m tests.sandbox_conformance`) |
| Công cụ verify | chạy **trong image**, không cài lên máy host (giải quyết việc thiếu pytest/semgrep/trivy/k6) |
| Ảnh | chọn theo stack dự án (`node:22-alpine`, `python:3.12-alpine`…), cấu hình đè được. `alpine` trơn không có công cụ nào, chạy `npm test` trong đó sẽ đỏ vì **thiếu công cụ** chứ không phải vì code sai — `doctor` cảnh báo đúng chỗ này |
| Mạng cho tool | tắt mặc định; dự án cần cài phụ thuộc thì khai `sandbox.tools_network` tường minh |
| Môi trường tiến trình client | **allowlist** (`clients/base.py::child_env`, ADR-005 V2), không phải `os.environ` bớt vài thứ: `PATH HOME LANG LC_* TERM TMPDIR SHELL USER LOGNAME SSL_CERT_FILE` + `ANTHROPIC_*` + `AISEF_*` + tiền tố khai ở `clients.env_allow`; `CLAUDE*` của phiên cha và mọi secret khác của máy vắng (hợp quy C9). Kèm bộ vô hiệu credential git (`GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/usr/bin/false`, `GIT_CONFIG_COUNT/KEY_0/VALUE_0` xoá `credential.helper`) — osxkeychain không được hỏi trong phiên agent (C10); git của harness chạy tiến trình riêng, không nhận bộ này. Giới hạn đã biết: token model của Claude ở Keychain/OAuth của máy, không có broker |
| Suy biến | Provider thiếu bảo đảm bậc cần → `degraded=True` **kèm tên bảo đảm thiếu** (`SandboxResult.missing` vào evidence, cột "cách ly" của `pre-deploy`, `doctor`); `allow_degraded=False` từ chối **lúc chọn provider**, lệnh chưa chạy. Lỗi hạ tầng (daemon, kéo image — docker thoát 125) ghi `provider_error`; tool báo "không chạy được", không "test đỏ" |

### 5.4 Orchestration logic
| Hạng mục | Hiện thực |
|---|---|
| Định tuyến model | `harness/routing.py` — theo vai; **reviewer ≠ developer** |
| Bộ nhớ tư vấn | `memory` là slot riêng, nguồn `memory`, có IDs/nguồn/điểm/ngân sách/audit; **không phải bằng chứng**. Mặc định tắt, mỗi vai truy hồi riêng, reviewer/security không nhận quan sát agent chưa xác minh; phiên vẫn mới. [ADR-007](ADR-007-scoped-advisory-memory.md), [hướng dẫn](MEMORY.md), [kiểm thử](MEMORY-VALIDATION.md), [nghiên cứu/kế hoạch](MEMORY-RESEARCH-PLAN.md) |
| Sinh sub-agent | không có — mỗi vai là một phiên riêng do harness gọi (`harness/routing.py`); xem ADR-003 #15 |
| Bàn giao | gói ngữ cảnh mỗi vai dựng từ slot có **nguồn khai** (`phases/implement.py::SLOT_SOURCE`, ghi vào bằng chứng `handoff`): `story_id` · `story_title` · `story_contract` · `architecture_rules` · `write_scope` · `mockup_section` (artifact) · `tools` (config) · `skills` (router) · `diff_summary` (git) · `impact` · `repo_map` · `blast_radius` (code — `repo_map` là bản đồ mã quanh phạm vi ghi cho cả ba vai, ADR-005 V7, trần `context.max_repo_map_chars`; `blast_radius` là impact analysis từ CodebaseGraphProvider cho brownfield, rỗng khi greenfield) · `index` (ledger — lát cắt epic) · `roadmap` (artifact — **toàn** kế hoạch, một dòng mỗi story, cho reviewer: chỉ mục bằng chứng bó trong một epic và rỗng trên dự án mới, nên không trả lời được câu "việc này của story nào" — lỗi 58) · `preservation` · `validation` (ledger — ADR-004 R4/R6) · `prior_review` (evidence — kết luận của **chính reviewer** ở candidate trước, đọc lại từ `note:review:verdict`; không có nó thì mỗi lượt rà soát lại từ đầu và tự nâng mục *nên sửa* của mình thành *chặn*, story cháy hết lượt mà không hội tụ). Reviewer/security không nhận slot nguồn `agent` (ADR-003 #9). Không có `next`/`implement`/`complete`: vòng lặp story nằm trong `run` |
| Luật kích hoạt | `control/state.py` (FSM `PENDING → RUNNING → VERIFYING → VERIFIED → DONE`) + `control/scheduler.py` (đợt theo phụ thuộc và phạm vi ghi) ✅ **đã xong** |

### 5.5 Guardrails / Hooks
| Mốc (hook · matcher) | Guard | Chặn gì |
|---|---|---|
| `PreToolUse` · `Write\|Edit\|NotebookEdit` | `write-scope` | ghi ngoài phạm vi story |
| `PreToolUse` · `Write\|Edit` | `secret` | khoá/mật khẩu/token |
| `PreToolUse` · `Write\|Edit` | `injection` | SQL nối chuỗi, `dangerouslySetInnerHTML` |
| `PreToolUse` · `Write\|Edit` | `process-ref` | mã `STORY-…`/`EPIC-…` trong mã nguồn (luật 6); test và tài liệu được phép |
| `PreToolUse` · `Bash` | `git-stage` | `git add -A` |
| `PreToolUse` · `Bash` | `destructive` | `rm -rf`, `git reset --hard`, `checkout --`; **mọi** `git push` (kể cả `--dry-run`), `git remote add/set-url`, `git credential*`/`-c credential.helper=` — push/merge là việc của harness sau cổng (ADR-005 V2, hợp quy C10) |
| `PreToolUse` · `WebFetch\|Bash` | `egress` | kết nối tới host chưa khai trong `sandbox.allow_hosts`; rỗng = không kiểm (ADR-005 V12) |
| `PostToolUse` · `Write\|Edit\|NotebookEdit\|Bash` | `diff-scope` | file không liên quan bị chạm |
| `Stop` | `completion` | kết thúc khi test chưa xanh — **cho dừng** khi test không chạy được hay chưa khai lệnh, kết cục ghi ở cổng (lỗi 2, 8) |

Mỗi guard là **một lệnh độc lập trả exit code** → nối được vào mọi client.
Tên và mốc có một nguồn duy nhất `harness/guardrails.py` (`GUARD_MATCHERS`);
`compile` sinh hook/plugin từ đó, `doctor` nhắc biên dịch lại khi hook đang
nối thiếu guard mới. OpenCode gửi `filePath`/`newString` — guard đọc cả hai
dạng khoá (lỗi 10).

### 5.6 Observability
| Hạng mục | Hiện thực |
|---|---|
| Log, trace | sự kiện có cấu trúc, có provenance |
| **Cost & latency** | token in/out · USD · giây — ghi vào mỗi `evidence/{story}.json`, cộng dồn theo epic |
| **Ứng viên** | mỗi phép kiểm mang `detail.candidate` = SHA bản được kiểm (ADR-004 R1) |
| **Sổ hành vi** | `control/ledger.py` — phép chiếu từ evidence, không phải kho mới: mỗi tiêu chí / FR / `qa:<kind>` / màn hình có trạng thái VERIFIED · GAP · REOPENED (`regressed_by`); chỉ ứng viên đã *landed* (nhật ký `merge.completed`/`attempt.committed`) mới thành VERIFIED. `ledger.json` + `INDEX.md` + mốc `loops[]`; metrics (tăng trưởng, hồi quy, gap đóng, cải thiện biên/$) ở phần 5 báo cáo (ADR-004 R2/R6/R7) |
| Bàn giao & phán quyết | `handoff` (slot · nguồn · số ký tự, `prompt_chars`), `review:verdict`/`security:verdict` (JSON), `gate:input` (13 kwargs của `gate.evaluate` JSON-hoá, ghi ngay trước phán quyết — `aisef gate --replay` chấm lại lượt cũ bằng luật mới, ADR-005 V4), `gate:verdict`; lời rà soát nguyên văn ở `_bmad-output/reviews/<story>-<vai>-<lượt>.md` (lỗi 16) |
| **Kết cục lượt** | `agent_run.detail.exit_status` ∈ ok · max_turns · timeout · cost · context · permission · infra · error — `clients/stream.py::exit_status_of`, một bảng cho cả vòng thử lại (`INFRA_STATUSES` = timeout, infra không ăn `run.max_retries`) lẫn `aisef status` ("Lượt agent: …", bản ghi cũ là "chưa ghi"); `tool_run.detail.redacted` = số bí mật đã che trong `tail`/log (ADR-005 V1/V11 B) |
| Evaluation | `tests/bench/` (ADR-005 V8): task từ 25 lỗi thật của kho (commit) + story e9 done (sinh lúc chạy); `validate` ×3 trên bản chép `git archive` một ref, F2P/P2P theo tên, flaky loại và nêu tên; `run` → pass@1/pass@k/ổn định/cost so lịch sử; `export` Harbor. Trôi chất lượng còn đo bằng dogfood `tests/dogfood/` (mốc lượt/chi phí) và hợp quy client `tests/conformance/` |
| Dashboard | `aisef status` · `aisef report` · `aisef evidence <id>` |

---

## 6. Hai loại cổng

Chạy nối tiếp — **máy kiểm trước** để khỏi phí thời gian người.

| | Cổng máy | Cổng người (R13) |
|---|---|---|
| Kiểm | schema · không chu trình · mọi FR được phủ · story không quá lớn (mục 13) · cổng story (mục 12) | nội dung có đúng ý không |
| Ai chạy | tự động | người, bằng lệnh |
| Trượt thì | dừng, báo lỗi cụ thể | ghi `changes_requested` + ghi chú, sinh lại |

### Cổng người — phê duyệt là **trạng thái trên đĩa**, không phải prompt

Điều kiện để chạy được ở mọi nơi: CI không có người trả lời; agent trong phiên chat không thể "đợi"; người duyệt có thể ở **máy khác, lúc khác**.

**Tám cổng:** `prd` → `architecture` → `ux-spec` → `epics` → `stories` → `mockups` → `readiness` → `pre-deploy`
(cộng cổng `improve` của vòng cải tiến — ADR-004 R3 — đứng **ngoài** thứ tự này: nó lặp mỗi vòng,
gắn băm mọi `LOOP-REPORT-*.md`, và dự án chưa chạy `improve` không bị nó chặn)

**Hai bảo đảm:**
1. Phê duyệt gắn với **SHA-256 nội dung**. Sửa artifact → tự thành `stale`.
2. Duyệt lại tầng trên → tầng dưới thành `stale`. Thứ tự so bằng **số thứ tự đơn điệu**, không bằng đồng hồ (bản ghi đi qua git giữa nhiều máy).

**Tự duyệt:** `--auto-approve all` hoặc `--auto-approve prd,architecture`. Luôn ghi `decided_by: auto` để truy được artifact nào chưa từng có người xem.

> Cổng người ở **mức pha**, không ở mức story. Story dùng cổng máy 4 điều kiện — nếu bắt duyệt tay 114 lần thì mất hết ý nghĩa của tự động hoá.

✅ **Đã xong** — `aisef/control/approvals.py`, 19 test.

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

✅ **Đã xong** — `aisef/control/scheduler.py`, 26 test. Ví dụ thật: 9 story → **5 lượt** thay vì 9.

### 7.2 Cô lập — không đủ nếu chỉ chia đợt

Chia đợt tránh được đụng *nội dung file*, nhưng ba thứ sau vẫn đụng nếu chạy chung một thư mục:

| Đụng gì | Hậu quả |
|---|---|
| `git add` / `git commit` đồng thời | tranh `index.lock` → commit hỏng |
| Test đồng thời | tranh cổng mạng, CSDL, file tạm |
| Cài phụ thuộc đồng thời | `node_modules` / venv hỏng |

**Giải: mỗi story trong đợt chạy trong git worktree riêng.**

```
.aisef/worktrees/S-01-02/     git worktree + nhánh story/S-01-02
.aisef/worktrees/S-01-03/     git worktree + nhánh story/S-01-03
```

- Worktree chia sẻ `.git`, không sao chép lịch sử → tạo nhanh, tốn ít đĩa.
- Test của mỗi story chạy trong **container riêng**, mạng riêng → không tranh cổng.
- Hết đợt: **merge tuần tự** theo thứ tự id vào nhánh chính, rồi xoá worktree.

### 7.3 Merge conflict là tín hiệu, không phải sự cố

`write_scope` đã bảo đảm hai story không chạm cùng vùng, nên **merge lẽ ra không bao giờ conflict**. Nếu conflict xảy ra: đó là bằng chứng story khai `write_scope` sai.

Xử lý: **dừng, ghi vào evidence, báo người** — không tự gỡ. Đây là vòng phản hồi giúp sửa chất lượng story ở Bước 2.

### 7.4 Mặc định

`--max-parallel 3`. Tăng thì nhanh hơn nhưng dễ chạm hạn mức model và tải máy; đo bằng `aisef status` rồi chỉnh.

---

## 8. Skills: lọc hai tầng

**Tầng 1 — loại tấn công và ngoài phạm vi.** Dựa trên metadata thật (`subdomain`, `tags`), không đoán theo tên.

```
818 skill  →  269 keep · 207 offensive · 342 out-of-scope
```

Ba luật, thứ tự có chủ đích: subdomain tấn công → chặn; động từ tấn công (`exploiting-`, `abusing-`) → chặn; **marker cứng** (`c2`, `aadinternals`) thắng cả động từ phòng thủ; **marker mềm** (`privilege-escalation`) thua động từ phòng thủ — `auditing-rbac-privilege-escalation` là việc phòng thủ chính đáng.

**Bất biến được test:** không skill nào thuộc subdomain tấn công lọt vào danh sách cài mặc định.

**Tầng 2 — theo stack dự án.** 269 → 20–30. Dự án Python+React+Postgres+Docker chỉ cần `container-security`, `api-security`, `web-application-security`, `devsecops`, `cryptography`, `supply-chain-security`; không cần 56 skill `cloud-security` cho hạ tầng không dùng.

✅ **Tầng 1 đã xong** — `aisef/kit/security_filter.py`, 14 test. Tầng 2 cần `detect_stack`.

---

## 9. Cấu trúc

```
aisef/                          framework, một package Python
├── kit/                         NHÓM 1 — nội dung chuẩn hoá (nguồn canonical)
│   ├── catalog.json             sổ đăng ký nguồn skill + pin + lý do chọn
│   ├── prompts/  rules/  skills/    prompt có version · luật · skill tự viết
│   ├── skills.py  catalog.py  fetch.py  install.py  detect_stack.py  constitution.py
│   ├── security_filter.py  registry.py  router.py  skill_scan.py  docs.py
├── harness/                     NHÓM 2–6 — harness là code
│   ├── tools.py  sandbox.py  routing.py  prompts.py  browser.py
│   ├── guardrails.py  observe.py  testlog.py  aria.py  mockup_map.py  mockup_verify.py
├── control/                     điều phối nhiều story
│   ├── approvals.py  scheduler.py  state.py  worktree.py  journal.py
│   ├── gate.py  machine_gate.py  outcome.py  acceptance.py  tdd.py  security.py
│   ├── ledger.py  complexity.py  preflight.py  impact.py  change.py
│   ├── normalize.py  bmad_status.py  design_contract.py  experience.py  conformance.py
├── clients/                     R10
│   ├── base.py  claude_code.py  opencode.py  compile.py  stream.py
├── phases/                      plan · story_split · mockup · implement · run · improve · qa · deploy · report
└── cli/                         bộ lệnh, một tệp mỗi pha (parser · plan · implement · harness · doctor)
```

**Sinh ra trong dự án đích:**

```
dự-án/
├── docs/requirements.md          đầu vào duy nhất
├── .ai/                          canonical (compile từ kit)
├── .claude/  .opencode/          generated — không sửa tay
├── .aisef/worktrees/            cô lập khi chạy song song
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

Đây là bộ lệnh **đã hiện thực** (`aisef --help`), không phải bản phác.

```
# Chuẩn bị
aisef doctor                         môi trường: python · git · client · docker · playwright
aisef setup   [--references DIR] [--no-fetch] [--dry-run]   dò stack, nạp skill, sinh CLAUDE.md + AGENTS.md
aisef init [--stack react|python|go|node]  ghi .ai/config.json — stack preset cấu hình sẵn test/lint/sandbox/allow_hosts
aisef compile [--client claude|opencode|all] [--bin PATH]   sinh hook/plugin từ một nguồn guard duy nhất

# Tri thức vận hành (ADR-002 / ADR-003)
aisef skill   [--story S]            sổ đăng ký skill: dựng, soi, định tuyến thử cho một story
aisef skill   --scan [--client c] [--batch N]   quét SKILL.md bằng model (chỉ đọc, không tool):
                                      injection → rejected, suspicious → cảnh báo trong sổ
aisef doc     <package> [--topic T] [--tokens N] [--story S]   tra tài liệu thư viện
                                      (context7, có cache), ghi bằng chứng doc_lookup
aisef baseline [--provider graphify|basic|auto] [--force] [--incremental]
                                      brownfield: dựng baseline mã hiện tại (hoặc --incremental cập nhật graph)

# Bước 2 — tài liệu, dừng ở mỗi cổng
aisef plan    [--client c] [--auto-approve all|<danh sách>] [--force]
        project-context → prd → architecture → ux → epics → tách story

# Bước 3 — mockup
aisef mockup  [--client c] [--only <screen_id>] [--force]

# Cổng người duyệt
aisef gates                          bảng trạng thái 8 cổng
aisef review  <gate>                 artifact, trình bày theo loại cổng
aisef approve <gate> [--note ...] [--force]
aisef reject  <gate>  --note "..."   (bắt buộc ghi chú)
aisef auto-approve all|<danh sách>   luôn ghi dấu `auto`

# Bước 4 — hiện thực
aisef run     [--client c] [--epic E] [--sequential] [--no-isolate] [--force]
aisef run     --verify-only --story S [--client c] [--repeat K]   kiểm lại ứng viên đã đóng băng (ADR-004 R13):
        không mở phiên developer; ứng viên = HEAD nhánh story; chạy lại đúng phép kiểm ✗/thiếu
        ở SHA ấy, giữ rà soát/bảo mật cùng SHA; cổng chấm đủ; đạt → merge như thường, trượt →
        failed không ăn run.max_retries. Dùng khi trượt vì môi trường đo (e2e nhạy tải máy).
        --repeat K: mỗi phép kiểm chạy lại chạy K lần trên cùng SHA (oracle ×k của Terminal-Bench);
        test đổi kết cục giữa các lần → `note verify-only.repeat {flaky_ids, stable_red, flaky_checks}`,
        mục cổng ⚠ UNRUNNABLE "không ổn định: <tên>" — không chạy được ổn định ≠ trượt ≠ đạt;
        đỏ ở mọi lần → ✗ như thường. K = 1 (mặc định) là hành vi cũ.
aisef tool    test|lint|sast [--story S] [--lines N]  agent gọi qua đây để có bằng chứng;
        in tên test đỏ trước tail, khai "(lược N/M dòng — toàn văn: …log)" khi cắt
aisef verify  [--write-scope ...] [--story S] hậu kiểm guard trên cây làm việc

# Bước 5 — kiểm định
aisef qa      [--only <loại>] [--story S] [--story-level]
        Cấp dự án (qa · pre-deploy · improve) chạy ở **worktree sạch dựng từ SHA** (ADR-005 V6,
        knob verify.clean_tree): shim node_modules/.bin, conftest.py, pytest.ini chưa commit không
        tới được cây kiểm; node_modules/.venv của dự án được gắn vào. Bằng chứng ghi
        `tree = worktree-tạm | cây agent` + `clean_tree = <sha>`; mức story giữ cây worktree.

# Vòng cải tiến epic theo bằng chứng (ADR-004 R3) — sau khi epic đã chạy
aisef improve --epic E [--max-loops N] [--auto] [--client c] [--force]
        QA cấp dự án → sổ hành vi → **một** story sửa cho một GAP/REOPENED
        (STORY-RP-nn trong EPIC-RP-<E>, sinh bằng code) → `run` (worktree, cổng,
        reviewer ≠ developer) → QA → mốc `loops[]` + LOOP-REPORT-<n>.md → vòng sau.
        Dừng bằng code: hết gap · đủ improve.max_loops · biên ≤ 0 improve.flat_loops
        vòng liền · vượt improve.cost_cap_usd · bế tắc kế hoạch (trả người).
        Cổng người `improve` trước mỗi vòng ≥ 2 (aisef review/approve improve) trừ --auto.
        Không daemon: chạy lại tiếp từ mốc cuối trong sổ.

# Bước 6 — giao hàng
aisef devsecops [--client c] [--install-spec X] [--bin PATH] [--force]
                                               CI (code) + Dockerfile/IaC/runbook (model)
aisef pre-deploy [--skip-qa] [--epic E]       chấm cổng cuối, ghi báo cáo để người ký; --epic khai
                                               phạm vi nghiệm thu: story ngoài epic nêu tên là "ngoài
                                               phạm vi" (không xong, không thiếu) — cổng scope-aware,
                                               không nới (QĐ C-a 2026-09-06)

# Sau phát hành — vòng đời thay đổi
aisef change  FR-x "mô tả"           ghi FR, stale PRD trở xuống, sinh story delta
                                      STORY-CH-nn trong EPIC-CH (sinh bằng code)

# Guard — client gọi vào tại mốc vòng đời (do `compile` nối sẵn)
aisef guard write-scope|diff-scope|secret|git-stage|destructive|egress|injection|process-ref|completion

# Theo dõi
aisef memory status|providers|audit|consolidate [--json]
aisef memory recall|search [QUERY] --story S [--role developer|reviewer|security] [--json]
aisef memory capture --story S [--json]
aisef memory show|forget ID [--json]  bộ nhớ tư vấn thử nghiệm, mặc định tắt; không ảnh hưởng cổng
aisef status                         tiến độ · chi phí · story tốn bất thường
aisef report  [--out FILE]           báo cáo nghiệm thu + sổ hành vi (`ledger.json`, `INDEX.md`)
aisef evidence <id> [--story S]      lịch sử một story hoặc một hành vi
    [--link TEST_ID --why ...]        khai truy vết: test có sẵn chứng minh hành vi — sửa siêu dữ
                                      liệu, không phải story sửa; sổ vẫn đòi test xanh ở ứng viên
                                      đã landed (`traceability.json`, QĐ B6 2026-09-06)
                                      (STORY-01-04 · AC-STORY-01-04-2 · FR-3 · qa:e2e · mockup:notes-list)
aisef ctx [--story S | --file F] [--budget N]   bản đồ mã quanh phạm vi ghi, đầy đủ (ADR-005 V7);
                                      prompt chỉ nhận bản có trần `context.max_repo_map_chars`
aisef issues [--format md|csv] [--epic E] [--status gap,reopened] [--out FILE]
                                      bảng gap/hồi quy từ sổ → `ISSUES.md|csv` (ADR-004 R12);
                                      chỉ tệp, không tạo issue ở tracker nào
aisef gate    --replay <story> [--attempt n] | --all
                                      chấm lại cổng story trên bằng chứng đã ghi (ADR-005 V4):
                                      cắt bằng chứng ở `gate:input` của lượt, gọi `gate.evaluate`
                                      của mã **hiện tại**, in bảng từng mục so với `gate:verdict`
                                      đã ghi. Luật hợp trên lời reviewer/security **đã ghi** —
                                      không gọi model, $0. Lượt trước V4 (không có `gate:input`)
                                      → "không replay được", không đoán
aisef replay  <story> [--attempt n] | --all
                                      lối vào nhanh cho `gate --replay` — cùng logic, ít gõ hơn
aisef dashboard [--out FILE] [--projects DIR…]
                                      báo cáo hợp quy HTML tự chứa — guard telemetry (hit/pass/block,
                                      latency), gate verdicts, chi phí. `--projects` gộp nhiều dự án
                                      vào một báo cáo — xem offline

# Bench (ADR-005 V8) — việc của người phát triển harness, không nối vào `aisef`
python3 -m tests.bench mine [--e9 DIR]           task lỗi kho → tests/bench/tasks/ (commit); story e9 → .bench/tasks/
python3 -m tests.bench validate [ID…] [--runs 3] base+test đỏ · base+test+gold xanh · test chập chờn loại, nêu tên
python3 -m tests.bench run --client c [--attempts 3] [ID…]   AISEF_BENCH=1; guard như hợp quy, `note mode=bench`
python3 -m tests.bench report | export ID --out DIR          pass@1/pass@k/ổn định/cost so lịch sử · thư mục Harbor
```

`report` chiếu bằng chứng thành **sổ hành vi** (ADR-004 R2): mỗi tiêu chí,
yêu cầu, loại kiểm định và màn hình là một hành vi có trạng thái
VERIFIED / GAP / **REOPENED** — cái cuối là "đã đúng rồi hỏng", thứ mà cổng
story không nói được. `INDEX.md` là chỉ mục một dòng mỗi story; prompt
developer nhận **lát cắt epic** của chỉ mục ấy (slot `index`, trần
`context.max_index_chars`), còn lịch sử tra bằng `aisef evidence`.

Không có `aisef next` / `implement` / `complete` như bản phác: vòng lặp
story nằm trong `run`, và tách nhỏ ra thành ba lệnh chỉ tạo thêm ba chỗ
cho trạng thái lệch nhau.

---

## 11. Đa client (R10)

**Nội dung:** `kit/` → `aisef compile` → `.claude/` · `.opencode/`. Bắt buộc deterministic · idempotent · golden round-trip test · **khai báo loss** khi client thiếu cơ chế.

**Điều khiển:** cùng bộ lệnh, hai chế độ — đây là lý do Đ2 (CLI gọi-một-lần, không daemon) là quyết định đúng: thêm bề mặt mới **không phải sửa kiến trúc**.

| | Driver-led | Agent-led |
|---|---|---|
| Ai gọi | script / CI | chính agent, qua Bash tool |
| Bề mặt | `claude -p` · `opencode run` · cron · CI | **Claude Desktop · Claude CLI · OpenCode Desktop · OpenCode TUI/Web** |
| Lệnh | `aisef run --client X` | cùng bộ lệnh: trong phiên do `run` mở, agent gọi `aisef tool` · `aisef verify` · `aisef doc` · `aisef evidence` qua Bash; guard nối qua hook |

`run` chỉ là vòng lặp gọi lại chính các lệnh đơn — **không có code riêng cho mỗi chế độ**.

**Nối guard:**

| Bề mặt | Cách nối | Mức | Đã kiểm chứng |
|---|---|---|---|
| Claude CLI | `--settings` hooks → `aisef guard …` | tiền kiểm | ✅ cờ có thật |
| Claude Desktop | `.claude/settings.json` của dự án | tiền kiểm | ⚠️ suy luận — phải test |
| OpenCode CLI | plugin → `aisef guard …` | tiền kiểm | ✅ chứng minh 2026-09-05 trên agent thật; quan sát chi phí/lượt: chưa |
| OpenCode Desktop | cùng cấu hình dự án với CLI | tiền kiểm | ⚠️ suy luận từ CLI — chưa test riêng |
| Bất kỳ, nếu hook không gắn được | `aisef verify` chạy lại toàn bộ guard | hậu kiểm | ✅ luôn có |

**Quyết định (2026-09-05, thay quyết định 2026-09-04; cập nhật 2026-09-08
theo ADR-006 §4): OpenCode là client hạng nhất từ v1.0.0.**
Phép thử trên agent thật (opencode 1.18.26) đã chứng minh plugin **chặn tại
nguồn** cho cả tool bash lẫn tool ghi tệp — nên hàng "hậu kiểm" ở bảng trên
không còn đúng cho guard. `--format json` (đo 2026-09-05, v0.5.0) phát luồng
sự kiện `step_finish` với token và cost — `machine_output: NATIVE`. Cái còn
thiếu: `turn_limit: unsupported` (OpenCode không có cờ giới hạn lượt). Hệ quả:

* OpenCode chạy được trọn story (STORY-02-01 của `par`, qua bảy cổng, merge
  vào main) và được hỗ trợ chính thức;
* hợp quy client (`docs/CONFORMANCE.md`) chạy cả hai client — cả hai đạt
  10/10 từ 2026-09-08;
* hạn chế đã biết: OpenCode + Serena ghi `.serena/` ngoài `write_scope` khai
  — harness từ chối đúng (vấn đề phía agent, không phải framework).

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

**Cổng story (Bước 4–5) — `control/gate.py` `evaluate`, chấm trên ứng viên
đóng băng; mỗi mục là bằng chứng chạy thật, sáu kết cục (`control/outcome.py`):**

| Mục | Đọc gì | Khi không có bằng chứng |
|---|---|---|
| `evidence matches candidate` | kết quả *mới nhất* của mỗi phép kiểm mang đúng SHA ứng viên (ADR-004 R1) | ⚠ stale — không phải "đỏ"; không truyền SHA → – |
| `guard ran` | guard đã đánh giá ít nhất một thao tác ghi trong phiên | ✗ hook không tới worktree; chưa biên dịch hook → – |
| `test` | lần test cuối xanh **và** sau lần sửa tệp cuối (`completion`) | ✗; không chạy được → ⚠ |
| `no baseline regression` | tên test xanh ở `test:baseline` còn xanh **và còn tồn tại** ở ứng viên (ADR-004 R9; đổi tên giữ tiêu đề lá không tính là mất — lỗi 24) | ○ reporter không in tên; ⚠ baseline không chạy được; – tắt bởi `verify.baseline` |
| `lint` | lần lint cuối | ✗ chưa chạy; ○ chưa cấu hình |
| `write scope` | tệp đổi ⊆ `write_scope` hiệu lực (+ thư mục test của kiểm định story đòi — lỗi 21) | ✗ |
| `mockup map` | mỗi `screen_id` có một lần đối chiếu và `missing` rỗng (mục 12bis) | ✗; story không giao diện → – |
| `real tests` | `qa:fake-tests`: không test nào rỗng khẳng định | ✗ |
| `criteria have tests` | mỗi `AC-<story>-<i>` nằm trong tên một test ở lần xanh cuối (G5) | ○ reporter không in tên |
| `coverage` | số đọc từ output runner ≥ `coverage.min` | ○ runner không in coverage |
| `TDD` | story thêm test thì có một lần đỏ trước lần xanh cuối | – story không thêm test |
| `tests verify story` | nop control (ADR-005 V3), hai cấp. **Cấp 1 ($0):** test mang `AC-<story>-i` xanh ở ứng viên phải **không** xanh sẵn ở `test:baseline` — cùng tên, hoặc tên cũ mất mà tiêu đề lá còn (đổi tên để gắn mã) → ✗ "gắn mã vào test có sẵn" nêu tên (lỗi 23 → 24); baseline của lượt chạy lại đứng ở bản của chính story (`parent` ≠ `base_ref`) thì cấp 1 không so, cấp 2 quyết. **Cấp 2 (một lần sandbox):** worktree tạm ở SHA cha (điểm rẽ) + chép tệp test story thêm/sửa → `tools.test` ghi `test:nop` mang `candidate`; test mang mã phải **đỏ hoặc không tồn tại** (lỗi import ở SHA cha = đỏ, hợp lệ) → xanh là ✗ "xanh cả khi không có mã của story". Chỉ `tools.test`, không `qa:e2e` (lỗi 22) | ⚠ nop không chạy được; ○ reporter không in tên (chỉ biết bộ test đỏ ở SHA cha); – story không thêm/sửa tệp test · tắt bởi `verify.nop` · nhật ký trước V3 |
| `<kind>` theo hợp đồng kiểm định | `qa:<kind>` rồi mới tên trần (lỗi 9): e2e · accessibility · perf … | ○ chưa cấu hình |
| `security` | phiên rà soát bảo mật riêng không còn mức trong `security.block_severities` | ○ chưa cấu hình |
| `review` | phiên rà soát độc lập không còn `[chặn]`. Trả **hai bản**: văn bản có thẻ `[chặn]`/`[bế tắc]` và khối JSON (`verdict` + `findings` mang `behavior_id`); thiếu JSON hỏi lại **đúng một lần** rồi mới đọc văn bản; hai bản lệch thì lấy **hợp**, ghi note `review:mismatch` — không nới cổng vì model quên chép (ADR-004 R8) | ✗ chưa rà soát |
| `preservation` | hành vi VERIFIED của story khác mà story này chạm tệp còn xanh ở đúng ứng viên; FR hỏi story **đã xác minh** nó (`via`, lỗi 23) (ADR-004 R4) | ⚠ không kiểm được ≠ đạt; – không chạm hành vi nào |

Ký hiệu: ✗ FAILED · ⚠ UNRUNNABLE · ○ UNCONFIGURED · – NOT_APPLICABLE. ✗ và ⚠
chặn story; ○ không chặn story nhưng phải hiện ra và chặn ở `pre-deploy`.
Truy vết code ↔ story ↔ FR không phải một mục cổng: nó nằm ở `covers` của
story (sổ hành vi chiếu `FR-x` từ tiêu chí) và nhánh `story/<id>`; harness
không kiểm nội dung commit message.

**Hợp đồng chấm tối thiểu (ADR-005 V9).** Mỗi `Check` (`control/outcome.py`)
mang `kind` — ai chấm: `deterministic` · `structural` · `security` ·
`model-judge` · `human` (`outcome.CHECK_KINDS`; bảng `gate.CHECK_KIND` một chỗ)
— và `evidence`: con trỏ `seq` của sự kiện mục đã đọc, không chép nội dung;
mục suy từ tham số (`phạm vi ghi`, `bảo mật`, `rà soát`) trỏ rỗng và nói rỗng.
Tên mục là danh sách **đóng** `gate.CHECK_NAMES` (16 tên: 15 mục trên + họ
`<kind>`). Mỗi tên có **ba control** ở
`tests/test_gate_qualification.py` — positive (bằng chứng tốt → ✅/–), negative
hay mutant (bằng chứng xấu → ✗), env (môi trường/cấu hình không kết luận được →
⚠/○ có tên) — và `gate.qualification_table()` đọc tệp ấy bằng AST; báo cáo
nghiệm thu in "mục cổng có đủ 3 control: n/N", `gate:verdict` ghi `checks[]`
với `kind`/`evidence`. Không có `blocking`: chặn hay không là `Outcome.blocks`.

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
| `skills.inline` | `false` | thí nghiệm ADR-003 cơ chế B: dán thân SKILL.md của skill cao điểm nhất vào prompt (trần 8 000 ký tự). A/B n = 1 không thấy gain — giữ tắt (ADR-003 §6) |
| `security.semantic_review` | `true` | phiên rà soát bảo mật theo ngữ nghĩa (vai `security`) chạy cùng pha kiểm định |
| `review.impact_provider` | `""` | nhà cung cấp phân tích ảnh hưởng cho người rà soát; rỗng thì dùng `control/impact.py` |
| `story.max_acceptance_criteria` | `8` | quá thì Bước 2 buộc chẻ nhỏ |
| `story.max_write_scope_paths` | `10` | story chạm quá nhiều nơi là dấu hiệu quá lớn |
| `story.max_screen_states` | 8 | Tổng trạng thái màn hình (EXPERIENCE.md) một story phải dựng. Vượt → cổng `stories` chặn với chỉ dẫn chẻ; `run` từ chối. Đo 2026-09-05 e9: 11 và 18 trạng thái đều chạm `max_turns` lượt đầu, 4–8 lượt |
| `story.max_complexity` | `16.0` | **Điểm cỡ story** tổng hợp (ADR-004 R5, `control/complexity.py`): trạng thái màn hình ×1 + tiêu chí ×1 + đường dẫn write_scope ×0,5 (không tính manifest/lockfile) + fan-in phụ thuộc ×1 + story láng giềng có hành vi VERIFIED bị chạm ×0 (ledger; chỉ ghi để hiệu chuẩn, chưa tính điểm — ADR-004 §6 R5). Vượt **hoặc** vượt `max_screen_states` → cổng `stories` chặn kèm gợi ý chẻ tất định, `run` từ chối trước khi gọi model; story đã xong bỏ qua. Hiệu chuẩn B4 hồi cứu 23 story thật: Spearman(điểm, lượt developer lượt đầu) = 0,88; 16 tách e9 01-04 (23,5) và 01-05 (18,0) khỏi 01-03 (6,5) và `par` (3,0). `run` tự ghi `_bmad-output/complexity.json` sau mỗi story và `aisef doctor` cảnh báo khi ngưỡng lệch dữ liệu |
| ~~`story.max_context_tokens`~~ | — | **gỡ 2026-09-05**: chưa từng có mã đọc. Thay bằng `prompt_chars` ghi vào evidence mỗi lượt gọi model; `aisef status` cảnh báo story nạp > 3× trung vị |
| `improve.max_loops` | `3` | số vòng `aisef improve` tối đa cho một epic, đếm từ `loops[]` của sổ hành vi (chạy lại không đếm lại từ 0). HoH chạy 70 vòng không có điều kiện dừng; ở đây trần là code (ADR-004 R3) |
| `improve.flat_loops` | `2` | dừng khi cải thiện biên Δverified − Δreopened (hai mốc `loops[]` liên tiếp) ≤ 0 chừng này vòng liền — vòng sau nhận cùng gap, cùng ngữ cảnh, sẽ cho cùng kết quả |
| `improve.cost_cap_usd` | `0` | trần tổng chi phí các vòng của epic, đọc từ bằng chứng story sửa; `0` = không giới hạn |
| `context.max_index_chars` | `2000` | trần ký tự cho slot `index` — lát cắt chỉ mục bằng chứng của epic nạp vào prompt developer. Chỉ mục, **không** phải lịch sử: agent cần chi tiết thì gọi `aisef evidence <id>` (ADR-004 R6). e9 EPIC-01 đo được 497 ký tự |
| `context.max_preservation_chars` | `1 200` | trần ký tự cho hai slot R4 `preservation` (hành vi VERIFIED của story khác mà story này chạm tệp: id · story · nguồn kiểm) và `validation` (thứ harness chạy lại ở ứng viên). Cắt chỉ cắt phần **in ra**; cổng "bảo toàn" vẫn chấm đủ danh sách — không kiểm được là UNRUNNABLE, đỏ là FAILED và sổ ghi REOPENED (ADR-004 R4). Đo trên test giả: hai slot +212 ký tự, prompt developer +13,2 % (ADR-004 §6 R4) |
| `context.max_repo_map_chars` | `0` | trần ký tự cho slot `repo_map` (ADR-005 V7, `harness/context.py`): skeleton tệp trong phạm vi ghi (Python `ast`, TS/JS chữ ký) → tệp gọi/được import 1 bước → test nhắc tên, cấp cho cả ba vai. **0 = tắt** cho tới khi A/B T8 đạt (trung vị lượt developer −20 % **và** cổng cùng kết cục): Aider không công bố số đo nào cho repo map, còn 2 000 ký tự trên baseline B5 11 537 là +17 % (vượt trần 15 %) — khi bật, thử 1 500 (+13 %). Hồi cứu e9 01-05 tại SHA `2424265`: bản đầy đủ 3 119 ký tự, ADR-005 §9. Bản đầy đủ tra bằng `aisef ctx --story S` |
| `context.map_provider` | `""` | lệnh ngoài vẽ bản đồ (tree-sitter, serena — cắm sau, không thêm gói): stdin JSON `{project, seeds, budget}` → stdout văn bản, cùng kiểu `review.impact_provider`. Rỗng = dựng sẵn stdlib; lệnh hỏng thì lùi về dựng sẵn và slot nói rõ là thô |
| `context.graph_provider` | `"auto"` | `"auto"` / `"graphify"` / `"basic"` — chọn CodebaseGraphProvider cho brownfield. `auto` ưu tiên Graphify nếu có CLI + graph, lùi về Basic. Dùng bởi `aisef baseline` và slot `blast_radius` |
| `memory.enabled` | `false` | bật thử nghiệm local advisory memory; không tái sử dụng phiên, không thay evidence |
| `memory.provider` | `"local"` | `local` hoặc `openviking`; OpenViking hiện khai unavailable, chưa có adapter |
| `memory.fallback` | `"none"` | `none` hoặc `local`; chỉ fallback tường minh, luôn ghi lý do |
| `memory.timeout_seconds` | `2` | hạn chờ khoá local 1–30 giây; chưa phải timeout dịch vụ remote |
| `memory.max_chars` | `1200` | ngân sách toàn slot 0–20000 ký tự; không phải token |
| `memory.capture` | `false` | tự chụp outcome tất định sau lifecycle; CLI capture là opt-in từng lần |
| `run.max_parallel` | `3` | số story song song trong một đợt |
| `run.max_turns` | `40` | vòng lặp tối đa của một phiên story |
| `run.timeout_seconds` | `1800` | 30 phút cho một story |
| `run.max_retries` | `2` | số lần thử lại trước khi `blocked` |
| `run.cost_cap_usd` | `0` | trần tổng chi phí các lượt gọi model trong một run (USD; `0` = không giới hạn). Bật bằng cách đặt giá trị > 0 → `BudgetGuard.reserve(...)` chặn lượt gọi vượt trần, hoàn lại reservation khi ngoại lệ. Xem `aisef/control/budget.py` |
| `run.turn_cap` | `0` | trần tổng số turn trong run (`0` = không giới hạn). Cùng cơ chế với `run.cost_cap_usd` |
| `run.wall_clock_cap_seconds` | `0` | trần tổng thời gian chạy của run, giây (`0` = không giới hạn). Đo từ lúc run bắt đầu, không tính từng lượt gọi |
| `run.qualify_preflight` | `false` | bật pre-flight qualification policy (`aisef/control/qualification.py`) trước lượt đầu. Mặc định tắt vì policy coi `pending` là "trạng thái không kỳ vọng"; `run.py` chiếu `pending → failed` để policy chuyển sang `verify` khi bật |
| `cost.warn_multiple` | `3.0` | cảnh báo khi story tốn > 3× trung vị |
| `security.block_severities` | `["critical","high"]` | mức chặn merge |

Bổ sung sau khi chạy thật — mỗi khoá ra đời từ một lần hỏng cụ thể:

| Khoá | Mặc định | Vì sao có |
|---|---|---|
| `tools.test` · `tools.lint` · `tools.sast` | `""` (tự dò) | lệnh là quyết định của dự án; rỗng thì dò từ file có thật |
| `verify.*` (12 loại: `unit` · `sit` · `api-contract` · `e2e` · `uat` · `perf` · `security` · `mutation` · `accessibility` · `migration` · `sbom` · `image-scan`) | `""` | rỗng nghĩa là **chưa cấu hình**, không phải "đạt"; thư mục test suy từ lệnh được cấp thêm vào phạm vi ghi của story đòi loại ấy (lỗi 21) |
| `verify.waived` | `""` | miễn phải là quyết định có người ký, không phải hệ quả của việc quên |
| `verify.waiver_reason` | `""` | lý do miễn (phạm vi, ngày, người ký) — `pre-deploy` đòi có khi `verify.waived` khác rỗng và ghi vào `pre-deploy-report.json`; loại miễn hiện ◇ WAIVED, không bao giờ thành ✅ (QĐ5 2026-09-06: `mutation` của e9 UNRUNNABLE ở môi trường nghiệm thu, không cài công cụ để làm đẹp) |
| `verify.baseline` | `true` | chạy bộ test ở candidate cha **trước** phiên developer đầu tiên của story (ADR-004 R9) để cổng "không làm đỏ test có sẵn" so được tên test; tắt khi bộ test quá chậm — tắt thì mục cổng là – "tắt bởi cấu hình", không phải đạt |
| `verify.clean_tree` | `true` | kiểm định **cấp dự án** (`aisef qa`, `pre-deploy`, `improve`) chạy ở `git worktree` tạm dựng từ SHA đang chấm (ADR-005 V6, theo Harbor: verifier chạy tách khỏi env agent): shim `node_modules/.bin/*`, `conftest.py`, `pytest.ini` chưa commit không tới được cây kiểm; `node_modules`/`.venv` của dự án được gắn vào (Docker bind mount, suy biến symlink). Giá: tệp **không theo dõi** mà test cần (`.env.test`, fixture sinh tay) cũng vắng — commit chúng, hoặc tắt khoá này; tắt thì bằng chứng và `pre-deploy.json` ghi `tree = "cây agent"`, không im lặng. Mức story (`run`) giữ cây worktree đã đóng băng, không đọc khoá này |
| `verify.nop` | `true` | nop control cấp 2 (ADR-005 V3): sau khi đóng băng ứng viên, chạy `tools.test` một lần ở SHA cha với tệp test của story chép vào (`test:nop`) để cổng "test có kiểm được story" thấy test mang mã đỏ khi không có mã của story; +1 lần chạy test mỗi lượt. Tắt khi bộ test quá chậm — tắt thì mục cổng là – "tắt bởi cấu hình", không phải đạt; cấp 1 ($0) vẫn chấm |
| `sandbox.image` | `""` (theo stack) | `alpine` trơn không có công cụ nào; test đỏ vì thiếu công cụ chứ không vì code sai |
| `sandbox.allow_hosts` | `[]` | danh sách host agent được phép kết nối (`["api.github.com", "*.npmjs.org"]`); rỗng = không kiểm; guard `egress` dùng danh sách này (ADR-005 V12) |
| `sandbox.tools_network` | `false` | dự án cần cài phụ thuộc mới mở mạng, và phải khai tường minh |
| `sandbox.use_docker` | `true` | tắt được cho toolchain gắn với máy chủ, nhưng luôn ghi `degraded` |
| `sandbox.allow_degraded` | `true` | `run` chấp nhận kiểm định ngoài Docker khi không có Docker, ghi `degraded` vào bằng chứng |
| `sandbox.provider` | `"docker"` | provider chạy lệnh (ADR-005 V5): `docker` · `local` · `"mô-đun:Lớp"` cho backend ngoài cùng hợp đồng `harness/sandbox.py::ExecutionProvider`; thiếu bảo đảm nào thì bằng chứng ghi tên bảo đảm ấy (`missing`). `sandbox.use_docker=false` tương đương `local` |
| `sandbox.pre_deploy_degraded_waiver` | `""` | cổng `pre-deploy` **không** nhận suy biến (QĐ4) trừ khi có lý do khai ở đây; lý do ghi vào `pre-deploy.json` |
| `app.dev_command` · `app.base_url` · `app.ready_timeout_seconds` | `""` · `http://localhost:5173` · `60` | để mở **route thật** lúc đối chiếu mockup; cổng đã có người trả lời thì từ chối, không nhận vơ (lỗi 15) |
| `route.developer_model` · `route.reviewer_model` · `route.designer_model` · `route.security_model` | `""` | chọn model theo vai; rỗng thì theo mặc định của client |
| `clients.env_allow` | `[]` | tiền tố biến môi trường của máy được cho qua **thêm** vào tiến trình client, ngoài allowlist cố định (§5.3). Rỗng nghĩa là không gì qua thêm; provider của OpenCode đọc khoá từ biến riêng, hay CI xác thực Claude bằng `CLAUDE_CODE_OAUTH_TOKEN`, thì khai tường minh (tên đầy đủ cũng là tiền tố). Đo 2026-09-06: `9router/mycombo` giữ khoá ở `auth.json` của OpenCode, không cần khai (ADR-005 §9 V2) |

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

**Ai viết báo cáo:** `aisef report` sinh `docs/ACCEPTANCE-REPORT.md` từ
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
aisef/kit/skills.py            đọc SKILL.md, stdlib
aisef/kit/security_filter.py   lọc tầng 1: 818 → 269/207/342
aisef/control/approvals.py     8 cổng người duyệt
aisef/control/scheduler.py     epic tuần tự, story song song theo đợt
```

**Còn lại** — tách rõ code và nội dung, vì hai loại việc này không thay thế nhau:

| Tuần | Code | Nội dung |
|---|---|---|
| 1 | `state` · `worktree` · `detect_stack` · `catalog` · `install` | constitution · catalog entries |
| 2 | `clients/` + `compile` + golden test | — |
| 3 | `phases/plan` + normalizer + story splitter | 3 skill BMAD pipeline |
| 4 | `phases/mockup` + contract extract | 2 skill mockup |
| 5–6 | `harness/` 6 nhóm + `guardrails` 9 guard | PromptCatalog · 3 agent |
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
