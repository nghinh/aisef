# Báo cáo Spike — GĐ-0

**Mục đích:** giết các giả định trước khi xây GĐ-3 và GĐ-6 lên trên chúng.
**Ngày:** 2026-09-03 · **Máy:** darwin 25.5.0 · Claude Code 2.1.236 · Playwright 1.59.1

| Spike | Trạng thái | Kết luận một dòng |
|---|---|---|
| S1 `claude -p` + stream-json | ✅ **XONG** | Có đủ cost, latency, usage, và cả `permission_denials` |
| S2 Hook chặn trên Claude CLI | ✅ **XONG** | Chặn thật; agent không lách; `acceptEdits` cũng không vượt được |
| S7 Đối chiếu mockup | ✅ **XONG** | `ariaSnapshot()` cho đối chiếu tất định |
| S3 Hook trên Claude Desktop | ✅ **XONG** | Desktop đọc `.claude/settings.json` của dự án, **ngay, không cần restart** |
| S4 OpenCode CLI + Desktop | ⚠️ **CHƯA KẾT LUẬN** | Cơ chế `tool.execute.before` có thật; provider quá chậm để chạy xong ca thử |
| S5 Worktree + sandbox Docker | ✅ **XONG** | Cô lập đủ ba mặt: git, file, mạng |
| S6 BMAD qua CLI | ✅ **XONG** | Chạy được; BMAD có sẵn **headless mode** trả JSON có schema |

---

## S1 — `claude -p` và luồng `stream-json`

**Câu hỏi.** Output có cấu trúc gì? Lấy cost/latency ở đâu? Exit code khi lỗi?

**Cách thử.**
```bash
claude -p "Reply with exactly the word: OK" \
  --output-format stream-json --verbose --max-turns 1 < /dev/null
```

**Kết quả.** Exit 0, 9 dòng JSON. Các loại sự kiện:

```
system/hook_started · system/hook_response · system/init
assistant · rate_limit_event · system/post_turn_summary · result
```

Sự kiện `result` (cuối cùng) chứa đủ mọi thứ cần:

| Trường | Giá trị mẫu | Dùng để |
|---|---|---|
| `total_cost_usd` | `0.36267` | ghi cost vào evidence |
| `duration_ms` / `duration_api_ms` / `ttft_ms` | `3242` / `1884` / `2040` | đo độ trễ |
| `usage` | input 2 · output 4 · cache_creation **36256** | đếm token |
| **`permission_denials`** | `[]` | bằng chứng guard đã chặn gì |
| `session_id` | uuid | resume |
| `num_turns`, `stop_reason`, `is_error` | | phân loại kết thúc |

**Ảnh hưởng thiết kế.**

1. **`permission_denials` là phát hiện ngoài dự kiến** — nó ghi cả `tool_input` (nội dung agent định ghi), tức là bằng chứng máy đọc được, không phải lời agent tự khai. Đưa thẳng vào `evidence/{story}.json`.
2. **Chi phí nền cao hơn dự đoán.** Task chỉ trả lời "OK" mà tốn **$0.36**, do `cacheCreationInputTokens: 36256` — nạp `CLAUDE.md` và ngữ cảnh dự án. Ước tính thô: 114 story × 2 phiên (dev + reviewer) × ~$0.36 nền ≈ **$82 chỉ riêng phần nạp ngữ cảnh**, chưa tính nội dung story. Phải đo lại trên epic mẫu, và ưu tiên tái dùng prefix để chuyển từ `cache_creation` sang `cache_read`.
3. Luôn thêm `< /dev/null`, nếu không CLI chờ stdin 3 giây mỗi lần gọi.

**Đã thành code.** `aisdlc/clients/stream.py` + `tests/test_stream.py` (13 test), fixture là luồng thật.

---

## S2 — Hook `PreToolUse` có chặn thật không

**Câu hỏi.** `--settings` với `PreToolUse` có chặn được một lệnh Write ra ngoài phạm vi không, hay chỉ ghi log?

**Cách thử.** Guard 10 dòng, chặn Write ngoài `src/`, exit code 2:

```json
{"hooks": {"PreToolUse": [
  {"matcher": "Write|Edit",
   "hooks": [{"type": "command", "command": "python3 .../guard.py"}]}]}}
```

Rồi bảo agent ghi vào `secret_area/leak.txt`, chạy với `--permission-mode acceptEdits`.

**Kết quả.**

```
assistant → TOOL_USE Write: .../secret_area/leak.txt
user      → TOOL_RESULT is_error=True: "CHẶN: ... nằm ngoài write_scope"
assistant → "Blocked by the project's guard hook"
result    → permission_denials: [{tool_name, tool_use_id, tool_input}]
```

**File không tồn tại trên đĩa.**

**Ảnh hưởng thiết kế.**

1. Mô hình guard tiền kiểm **đứng vững** — không cần dự phòng hậu kiểm cho Claude CLI.
2. `--permission-mode acceptEdits` **không vượt được** hook. Guard nằm trên quyền của client, đúng như bất biến 9.
3. Agent nhận thông báo lỗi và **dừng đúng cách**, không thử đường vòng.
4. Quy ước: **exit 2 = chặn**, stderr được chuyển vào `tool_result` cho agent đọc. Guard phải viết lý do vào stderr, ngắn gọn và nói rõ cách sửa.

---

## S7 — Đối chiếu mockup có tất định không

**Câu hỏi.** Trích được cấu trúc màn hình đang chạy không? Đối chiếu với hợp đồng có lặp lại được không?

**Cách thử.** Ba trang: mockup (hợp đồng), app đủ, app **thiếu** checkbox và **thừa** một nút. Trích bằng `page.locator('body').ariaSnapshot()`.

```
- main:
  - heading "Đăng nhập" [level=1]
  - textbox "Email"
  - textbox "Mật khẩu"
  - checkbox "Ghi nhớ đăng nhập"
  - button "Đăng nhập"
  - link "Quên mật khẩu?"
```

**Kết quả.**

| Ca | Verdict | missing | extra |
|---|---|---|---|
| app đủ | PASS | `[]` | `[]` |
| app thiếu | **FAIL** | `checkbox "Ghi nhớ đăng nhập"` | `button "Đăng nhập bằng Google"` |

**Ảnh hưởng thiết kế.**

1. **Accessibility tree là đơn vị đối chiếu đúng** — bền trước đổi class, mang ý nghĩa ngữ nghĩa, và kiểm luôn khả năng tiếp cận. Xác nhận quyết định bỏ pixel diff.
2. So theo **tập hợp**, không theo thứ tự: mockup và app sắp xếp khác nhau vẫn đúng hợp đồng. Vị trí là việc của người đánh giá thị giác.
3. Sai vai trò tính là thiếu: `link "Tìm"` không thoả hợp đồng `button "Tìm"`.
4. Bỏ node `text:` thuần và node không tên — component không có tên gọi thì không kiểm chứng được, và đó cũng là dấu hiệu vấn đề a11y.
5. Playwright + chromium **đã có sẵn trên máy**, không phải tải.

**Đã thành code.** `aisdlc/harness/aria.py` + `tests/test_aria.py` (16 test), fixture là snapshot thật từ chromium.

---

## S3 — Claude Desktop có đọc settings của dự án không

**Câu hỏi.** Hook chạy được trong Desktop, nhưng đó là hook user-level. Desktop có đọc `.claude/settings.json` của **dự án** không?

**Cách thử.** Tạo `.claude/settings.json` trong repo với một `PreToolUse` chỉ ghi log (luôn exit 0, không chặn gì), rồi gọi một tool Bash ngay trong phiên Desktop đang chạy.

**Kết quả.**
```
00:04:10 | project-level hook đã chạy
```

**Ảnh hưởng thiết kế.**

1. Desktop đọc settings cấp dự án, và **nạp ngay** — không cần khởi động lại phiên. Nghĩa là `aisdlc compile` ghi `.claude/settings.json` xong là guard có hiệu lực liền.
2. Ba trong bốn bề mặt (Claude Desktop, Claude CLI, và CLI headless) đều gắn được guard **tiền kiểm**. Phương án dự phòng hậu kiểm chỉ còn cần cho OpenCode nếu S4 xấu.
3. Hook user-level hiện có 12 loại (`PreToolUse`, `PostToolUse`, `SubagentStart/Stop`, `Stop`, `PermissionRequest`, `PostCompact`…) — đủ cho cả ba mốc vòng đời ta cần.

---

## S4 — OpenCode

**Câu hỏi.** `opencode run` trả kết quả kiểu gì? Plugin chặn được tool không? Desktop dùng chung cấu hình?

**Đã xác định.**

* OpenCode có hook `tool.execute.before` — tương đương `PreToolUse`. Plugin viết TypeScript, `import type { Plugin } from "@opencode-ai/plugin"`.
* Plugin nhận `(input, output)` và **sửa được `output.args`** trước khi tool chạy (ví dụ `rtk.ts` có sẵn trên máy viết lại câu lệnh bash).
* Máy đã cấu hình 9 provider (Anthropic oauth, OpenAI, Google, 9router…), mặc định `9router/mycombo`.
* `opencode stats` cho token và chi phí; `opencode export <sessionID>` xuất phiên ra JSON.

**Chưa kết luận được.** Hai lần chạy `opencode run` với ca thử "ghi file ngoài scope" đều không xong trong 60–120 giây (provider `9router/*` phản hồi chậm). Vì thế **chưa chứng minh** được hai điều:

* ném lỗi trong `tool.execute.before` có **chặn** tool hay chỉ ghi log;
* plugin đặt ở `.opencode/plugin/` cấp dự án có được nạp không.

**Không ghi ✅ khi chưa chứng minh** (bất biến 10). Cách thử tiếp: chạy lại với provider Anthropic oauth trực tiếp thay vì gateway, hoặc dùng `opencode serve` rồi gọi API để tách phần chờ model khỏi phép thử.

**Ảnh hưởng thiết kế.** Chưa có. Nếu hoá ra plugin không chặn được, OpenCode xuống mức **hậu kiểm** và điều đó phải ghi vào compile report, không im lặng.

---

## S5 — Cô lập khi chạy song song

**Câu hỏi.** Worktree có đủ cô lập cho story chạy song song không? Docker chặn được mạng và ghi ngoài phạm vi không?

**Kết quả.**

| Phép thử | Kết quả |
|---|---|
| 2 worktree, `write_scope` rời nhau → merge tuần tự | sạch, cả hai thay đổi vào nhánh chính |
| 2 worktree cùng sửa một file → merge | **conflict**, abort, cây về trạng thái sạch |
| `--network=none` + `wget example.com` | `bad address` — chặn cả phân giải tên miền |
| mount chỉ worktree, `cat` đường dẫn ngoài | `No such file or directory` |
| `--cap-drop=ALL --user 1000:1000` | ghi workspace OK, `touch /etc/nope` bị từ chối |
| bind mount | file ghi trong container hiện đúng ở host |

**Ảnh hưởng thiết kế.**

1. Quyết định Đ5 đứng vững — worktree cô lập đủ cả ba mặt git, file, mạng.
2. Conflict **abort được sạch**, nên xử lý "dừng và báo" khả thi: cây không kẹt ở trạng thái nửa merge.
3. Chạy công cụ verify **trong image** giải quyết luôn việc máy chưa có `pytest`/`semgrep`/`trivy`/`k6`.

**Đã thành code.** `control/worktree.py` + `harness/sandbox.py`, 35 test.

**Một bug do test bắt được:** thư mục worktree nằm trong kho làm `git status` bẩn (`?? .aisdlc/`), phá luôn phép kiểm "cây sạch sau abort". Sửa bằng cách tự đặt `.gitignore` chứa `*` ngay trong thư mục worktree — module tự lo, không bắt người dùng nhớ.

---

## S6 — BMAD qua CLI

**Câu hỏi.** Gọi được skill `bmad-prd` từ `claude -p` không? Cần cài `_bmad/` thế nào?

**Cách thử.** Copy `bmad-prd` vào `.claude/skills/`, viết một `docs/requirements.md` nhỏ (ứng dụng ghi chú), rồi:

```
claude -p 'headless: true
Use the bmad-prd skill. intent: "create". Read docs/requirements.md as the brief.
doc_workspace: _bmad-output ...'
```

**Kết quả.** Chạy xong sau 507 giây, 22 lượt, **$1.88**. Sinh 5 artifact:

```
prd.md 33KB · addendum.md · reconcile-requirements.md · review-self.md · .memlog.md
tokens: out 33.001 · cache_create 63.619 · cache_read 831.900
JSON status: {"status": "partial", "intent": "create", ...}
```

PRD có 13 mục, **64 tham chiếu FR có mã** (`FR-1`…`FR-17`), 7 NFR, 8 câu hỏi mở.

**Phát hiện quan trọng nhất của cả GĐ-0: BMAD đã có sẵn headless mode.**

`references/headless.md` của skill quy định: *"Do not ask… Do not greet"*, và kết thúc bằng JSON theo schema trong `assets/headless-schemas.md`:

```json
{"status": "complete|partial|blocked", "intent": "create",
 "prd": "...", "assumptions": [], "open_questions": []}
```

PRD sinh ra có sẵn mục **Câu hỏi mở** với cấu trúc dùng được ngay:

> **OQ-1 (chặn FR-13..FR-15)** — Đồng bộ nhiều thiết bị định danh người dùng bằng cách nào khi tài khoản không bắt buộc? … Chủ: PM. Cần chốt trước khi bước sang kiến trúc.

**Ảnh hưởng thiết kế — lớn.**

1. **Không phải hack gì cả.** BMAD thiết kế sẵn cho runner tự động. Normalizer đọc JSON status thay vì mò trong markdown.
2. **`status` ánh xạ thẳng vào cổng người duyệt:** `complete` → đủ điều kiện tự duyệt; `partial` + `open_questions[]` → **bắt buộc người xem**, và chính `open_questions` là checklist review; `blocked` → dừng, báo.
3. **`open_questions` có mã và có phạm vi ảnh hưởng** (`chặn FR-13..FR-15`) → map được sang việc chặn story ở GĐ-4, không cần ta tự nghĩ ra cơ chế.
4. `assumptions[]` đi thẳng vào evidence — đúng nguyên tắc "ghi lại giả định thay vì bịa".
5. Skill có phụ thuộc `_bmad/scripts/resolve_customization.py` (chạy bằng `uv`) nhưng **có đường lui**: SKILL.md ghi rõ "nếu script lỗi thì tự hợp nhất ba file TOML". Chạy thử không cần cài `uv`.
6. **BMAD tự phát hiện mâu thuẫn trong brief và không tự quyết.** Brief nói "đồng bộ khi có mạng" (cần định danh) lẫn "không bắt buộc tài khoản" (không có định danh). BMAD giữ FR-13..FR-15 nhưng đẩy ra ngoài MVP sau OQ-1, kèm câu "your call to reverse" — thay vì âm thầm cắt một yêu cầu đã nêu, hoặc âm thầm bịa ra mô hình tài khoản. Đúng bất biến 4.
7. **BMAD tự khai báo thiếu sót của chính nó.** Vì subagent bị tắt, nó ghi ngay đầu `review-self.md`: *"the reviewer pass is self-review, not an independent gate"*. Đúng bất biến 10 — và xác nhận rằng **reviewer ≠ developer phải do framework bảo đảm bằng phiên riêng**, không trông vào skill tự lo.
8. **Chi phí thấp hơn lo ngại ở S1.** `cache_read` 831.900 token so với `cache_create` 63.619 — prompt caching hoạt động tốt trong một phiên dài. Một PRD hoàn chỉnh hết $1.88. Ước tính $82 ở S1 là cho trường hợp xấu nhất (mỗi phiên nạp lại từ đầu); thực tế nằm giữa, vẫn phải đo trên epic mẫu.

---

## Tổng kết GĐ-0

**Cổng GĐ-0: ĐẠT.** Mô hình guard tiền kiểm đứng vững trên cả ba bề mặt Claude. Không có kết quả nào buộc phải sửa kiến trúc.

Một hạng mục còn treo (S4/OpenCode) và nó **không chặn** GĐ-1 → GĐ-3, vì adapter được thiết kế theo giao diện chung; OpenCode chỉ là một hiện thực, và mức bảo đảm của nó sẽ được khai báo trung thực khi biết.

**Điều chỉnh cần đưa vào kế hoạch:**

| Từ spike | Điều chỉnh |
|---|---|
| S6 | GĐ-4 dùng **BMAD headless JSON** làm giao diện, không parse markdown mò |
| S6 | `open_questions[]` trở thành checklist tự sinh của cổng người duyệt |
| S1 | Ước tính chi phí lại: ~$0.36/phiên chỉ riêng nạp ngữ cảnh nền |
| S4 | Thêm việc "chạy lại S4 với provider trực tiếp" vào đầu GĐ-3 |
