# Báo cáo Spike — GĐ-0

**Mục đích:** giết các giả định trước khi xây GĐ-3 và GĐ-6 lên trên chúng.
**Ngày:** 2026-09-03 · **Máy:** darwin 25.5.0 · Claude Code 2.1.236 · Playwright 1.59.1

| Spike | Trạng thái | Kết luận một dòng |
|---|---|---|
| S1 `claude -p` + stream-json | ✅ **XONG** | Có đủ cost, latency, usage, và cả `permission_denials` |
| S2 Hook chặn trên Claude CLI | ✅ **XONG** | Chặn thật; agent không lách; `acceptEdits` cũng không vượt được |
| S7 Đối chiếu mockup | ✅ **XONG** | `ariaSnapshot()` cho đối chiếu tất định |
| S3 Hook trên Claude Desktop | ⏳ chưa | |
| S4 OpenCode CLI + Desktop | ⏳ chưa | |
| S5 Worktree + sandbox Docker | ⏳ chưa | |
| S6 BMAD qua CLI | ⏳ chưa | |

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

## Còn lại

| Spike | Vì sao vẫn cần |
|---|---|
| S3 Claude Desktop | Chưa biết Desktop có nạp `.claude/settings.json` của dự án không. Nếu không → khai báo hậu kiểm cho bề mặt đó |
| S4 OpenCode | Chưa biết `opencode run` trả kết quả kiểu gì, `plugin` gắn guard ra sao, Desktop có dùng chung cấu hình không |
| S5 Worktree + Docker | Chưa chạy thử hai story song song ở hai worktree rồi merge tuần tự |
| S6 BMAD qua CLI | Chưa biết cần cài `_bmad/` thế nào để `claude -p` gọi được skill `bmad-prd` |

**Cổng GĐ-0 hiện tại:** S2 xanh nên mô hình guard tiền kiểm không sụp. Phương án dự phòng hậu kiểm chỉ còn cần cho bề mặt nào S3/S4 cho kết quả xấu.
