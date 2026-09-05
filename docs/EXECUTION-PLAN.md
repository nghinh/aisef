# Kế hoạch thực thi

**Căn cứ:** `docs/SOLUTION.md` v2 (đã duyệt).
**Nguyên tắc lập lịch:**
1. **Rủi ro cao làm trước** — giả định chưa kiểm chứng phải bị loại bỏ trước khi xây nhiều lên trên nó.
2. **Mỗi giai đoạn kết thúc bằng thứ chạy được**, không phải khung rỗng.
3. **Tiêu chí xong kiểm chứng bằng lệnh**, không phải "đã viết xong".
4. Mỗi hạng mục: code + test trong cùng một commit.

---

## Tiến độ (cập nhật 2026-09-05)

| Giai đoạn | Trạng thái |
|---|---|
| GĐ-0 Spike | ✅ **xong** — 7/7; S4 (OpenCode) kết luận 2026-09-05: guard chặn tại nguồn, có phép thử trên agent thật |
| GĐ-1 Control plane | ✅ **xong** — config · state · fsm · worktree · CLI |
| GĐ-2 Kit + Setup | ✅ **xong** — catalog · detect_stack · lọc 2 tầng · install · constitution |
| GĐ-3 Đa client | ✅ **xong** — adapter · guard · compile · báo cáo mất mát |
| GĐ-4 BMAD pipeline | ✅ 5/5 — `aisdlc plan` chạy chuỗi BMAD, dừng đúng từng cổng, tách 12 story từ epics thật |
| GĐ-5 Mockup | ✅ 6/6 — dựng bằng chromium thật, hợp đồng trích từ trang đã render |
| GĐ-6 Harness + implement | ✅ 10/10 — `aisdlc run` chạy đợt trên worktree thật, cổng story 6 điều kiện |
| GĐ-7 Kiểm định | ✅ — `aisdlc qa` 10 loại; "chưa cấu hình" ≠ "đạt" |
| GĐ-8 DevSecOps | ✅ — `aisdlc devsecops` + `pre-deploy` |
| GĐ-9 Đầu-cuối | 🔨 **một epic đã chạy trọn trên cả hai client** (`par`: 3 story song song bằng Claude, 1 story bằng OpenCode, đều merge vào main). Còn lại: mockup thật trong một dự án có giao diện, báo cáo nghiệm thu đầy đủ, và một lượt đầu-cuối từ `requirements.md` tới `pre-deploy` không can thiệp tay |

**Mốc demo đã đạt**

* *Mốc 1* — `aisdlc gates` / `approve` / `status` chạy thật.
* *Mốc 2* — thư mục trống + `docs/requirements.md` → 226 skill được cài
  (bmad 36 · security 175 · superpowers 10 · ui-ux 5), `CLAUDE.md` +
  `AGENTS.md` sinh theo stack, `doctor` xanh gồm cả bất biến "không có
  skill tấn công".

* *Mốc 3* — `aisdlc compile` sinh `.claude/settings.json`; chạy `claude -p`
  thật với nó thì guard **chặn được** một agent cố ghi ra ngoài phạm vi:
  file không được tạo, `permission_denials = 1`. Toàn chuỗi compile → hook
  → guard → chặn đã kiểm chứng trên agent thật.

* *Mốc 4* — một story đi trọn bảy cổng trên agent thật: `STORY-01-01` của
  e9 qua test · lint · phạm vi ghi · test-thật · rà soát độc lập, rồi merge
  vào nhánh chính (2 lượt, $9,76). Trước đó nó trượt 4 lần liên tiếp — mỗi
  lần vì một lỗi thật khác nhau của harness, xem mục 15–22 dưới.

* *Mốc 5* — ba story chạy **song song** trong một epic, cả ba xong ngay lượt
  đầu, merge tuần tự không đụng, $3,14 (`par`, 2026-09-05). R14 kiểm chứng
  đầu-cuối trên agent thật.

* *Mốc 6* — framework **cài được**: `pip install ai-sdlc` trong venv sạch,
  `aisdlc setup` tự lấy 5 kho skill về cache người dùng (93 MB, 14 s), cài
  120 skill, `doctor` xanh, guard chặn thật từ bản đã cài.

* *Mốc 7* — một story do agent **OpenCode** hiện thực trọn vẹn: qua bảy
  cổng, commit đúng nhánh story, merge vào nhánh chính, 18 test của dự án
  xanh (`par` STORY-02-01). R10 hết là lời khai. Bốn lỗi phải vá mới tới
  được đây — 39 (plugin gọi `.stdin()` không tồn tại nên guard chưa từng
  chạy), 41 (plugin gọi mọi guard cho mọi tool), 40 (OpenCode tự dò gốc dự
  án nên model làm việc trên thân cây), 42 (story XONG mà merge đụng thì
  mất luôn công việc).

**966 test xanh.**

---

## 0. Đã xong

| Module | Nội dung | Test |
|---|---|---|
| `aisdlc/kit/skills.py` | đọc `SKILL.md`, parser frontmatter stdlib | 3 |
| `aisdlc/kit/security_filter.py` | lọc tầng 1: 818 → 269 keep / 207 offensive / 342 out-of-scope | 11 |
| `aisdlc/control/approvals.py` | 8 cổng người duyệt, SHA-binding, cascade stale | 19 |
| `aisdlc/control/scheduler.py` | epic tuần tự, story song song theo đợt | 26 |
| `aisdlc/clients/stream.py` | đọc stream-json của Claude Code | 13 |
| `aisdlc/harness/aria.py` | đối chiếu mockup qua accessibility tree | 16 |
| `aisdlc/control/worktree.py` | cô lập story song song | 14 |
| `aisdlc/harness/sandbox.py` | 4 bậc quyền, Docker | 21 |
| `aisdlc/config.py` | 12 khoá ngưỡng | 21 |
| `aisdlc/control/state.py` | tiến độ, khoá, resume | 18 |
| `aisdlc/cli.py` | doctor · gates · review · approve · reject · status · setup | 26 |
| `aisdlc/kit/detect_stack.py` | dò công nghệ | 17 |
| `aisdlc/kit/catalog.py` | sổ đăng ký nguồn + ràng buộc license | 17 |
| `aisdlc/kit/install.py` | cài skill, idempotent | 14 |
| `aisdlc/kit/constitution.py` | sinh CLAUDE.md / AGENTS.md | 14 |
| `aisdlc/clients/base.py` | giao diện adapter + khai báo năng lực | 12 |
| `aisdlc/clients/claude_code.py` | chạy claude -p | 8 |
| `aisdlc/clients/opencode.py` | chạy opencode run | 2 |
| `aisdlc/harness/guardrails.py` | 5 guard chặn thật | 42 |
| `aisdlc/clients/compile.py` | sinh cấu hình client + báo cáo mất mát | 19 |
| `aisdlc/control/normalize.py` | BMAD markdown → mô hình framework | 23 |
| `aisdlc/control/machine_gate.py` | cổng máy, kiểm truy vết hai chiều | 22 |
| | | **386 xanh** |

---

## GĐ-0 · Spike kiểm chứng (3 ngày) — làm trước mọi thứ

Mục đích duy nhất: **giết các giả định còn lại** (7 spike). Code spike vứt đi được, chỉ giữ kết luận.

| # | Spike | Câu hỏi phải trả lời | Xong khi |
|---|---|---|---|
| S1 | `claude -p` một task nhỏ | Output `stream-json` có cấu trúc gì? Lấy được token/cost ở đâu? Exit code khi lỗi? | Có file mẫu `spike/claude-stream.jsonl` + hàm đọc được cost |
| S2 | Hook chặn trên Claude CLI | `--settings` với `PreToolUse` có **chặn thật** một lệnh Write không? | Chạy được ca thử: agent cố ghi ngoài scope → bị từ chối |
| S3 | Hook trên **Claude Desktop** | Desktop có nạp `.claude/settings.json` của dự án không? | Kết luận ✅/❌ ghi vào ma trận; nếu ❌ → khai báo hậu kiểm |
| S4 | OpenCode CLI + Desktop | `opencode run` đọc kết quả kiểu gì? `plugin` gắn guard được không? Desktop dùng chung cấu hình? | Kết luận cho cả 2 bề mặt |
| S5 | Worktree + sandbox | `git worktree` + chạy test trong Docker `--network=none`, mount chỉ worktree | Chạy được 2 story song song, 2 worktree, merge tuần tự sạch |
| S6 | BMAD qua CLI | Gọi được skill `bmad-prd` từ `claude -p` không? Cần cài `_bmad/` thế nào? | Sinh được một `prd.md` thật từ `docs/requirements.md` |
| S7 | Đối chiếu mockup | Playwright trích được DOM/accessibility tree của app đang chạy không? Đối chiếu với contract có tất định không? | Chạy trên một trang mẫu: liệt kê đúng component, phát hiện đúng component bị thiếu |

**Đầu ra GĐ-0:** `docs/SPIKE-REPORT.md` — mỗi spike một mục: câu hỏi · cách thử · kết quả · ảnh hưởng tới thiết kế.

**Cổng:** nếu S2/S3/S4 cho kết quả xấu (không gắn được hook ở đâu cả) → **dừng, họp lại**, vì mô hình guard tiền kiểm sụp. Phương án dự phòng: chuyển toàn bộ sang hậu kiểm ở `verify`, chấp nhận mức bảo đảm thấp hơn và ghi rõ.

---

## GĐ-1 · Nền control plane (tuần 1)

| # | Hạng mục | File | Xong khi |
|---|---|---|---|
| 1.1 | Cấu hình + ngưỡng | `aisdlc/config.py`, `.ai/config.json` | 10 khoá mục 13 SOLUTION có mặc định; override được; test đọc/ghi |
| 1.2 | Kho trạng thái | `control/state.py` | `sprint-status.json` ghi nguyên tử, khoá file chống hai tiến trình; test 2 tiến trình ghi đồng thời không hỏng |
| 1.3 | Vòng đời story | `control/fsm.py` | `pending→running→verifying→done\|blocked`; chuyển sai trạng thái bị từ chối; test đủ nhánh |
| 1.4 | Cô lập worktree | `control/worktree.py` | tạo/xoá worktree, merge tuần tự, **phát hiện conflict → dừng và báo**; test trên repo tạm |
| 1.5 | Khung CLI | `aisdlc/cli.py`, `bin/aisdlc` | `doctor` `gates` `review` `approve` `reject` `status` chạy thật |

**Mốc demo 1:** duyệt được một cổng bằng lệnh, thấy bảng trạng thái.

```bash
aisdlc gates
aisdlc approve prd --note "ok"
aisdlc status
```

---

## GĐ-2 · Kit + Setup — Bước 1 (tuần 2)

| # | Hạng mục | File | Xong khi |
|---|---|---|---|
| 2.1 | Sổ đăng ký nguồn | `kit/catalog.json`, `kit/catalog.py` | 5 nguồn có pin commit; test: mọi entry trỏ tới đường dẫn có thật |
| 2.2 | Dò stack | `kit/detect_stack.py` | Nhận diện backend/frontend/db/deploy từ `requirements.md`; test trên 3 mẫu |
| 2.3 | Lọc security tầng 2 | `kit/security_filter.py` (mở rộng) | 269 → 20–30 theo stack; test: dự án Python+React không nhận skill `cloud-security` của AWS |
| 2.4 | Hiến pháp | `kit/constitution/`, `kit/constitution.py` | Sinh `CLAUDE.md` + `AGENTS.md` từ nguồn chung; test golden |
| 2.5 | Bộ cài | `kit/install.py` | Cài vào dự án trống; **idempotent** (chạy 2 lần không nhân bản); test đếm đúng số skill |
| 2.6 | `aisdlc setup` + `doctor` | `phases/setup.py` | `doctor` trả 0; **test bất biến: không skill offensive nào trong dự án đích** |

**Mốc demo 2:** một thư mục trống + `requirements.md` → dự án đã nạp đủ skill/agent/hook.

---

## GĐ-3 · Đa client — R10 (tuần 3)

| # | Hạng mục | File | Xong khi |
|---|---|---|---|
| 3.1 | Giao diện adapter | `clients/base.py` | `run()` · `wire_guards()` · `capability()`; kết quả spike S1–S4 đổ vào đây |
| 3.2 | Claude Code | `clients/claude_code.py` | Chạy được `claude -p`, đọc `stream-json`, lấy cost/latency |
| 3.3 | OpenCode | `clients/opencode.py` | Chạy được `opencode run`, lấy kết quả + `stats` |
| 3.4 | Compiler | `clients/compile.py` | `kit/` → `.claude/` + `.opencode/`; **deterministic, idempotent**; golden round-trip test |
| 3.5 | Khai báo loss | `clients/report.py` | Bề mặt nào không gắn được hook → ghi vào compile report, **không im lặng** |

**Mốc demo 3:** `aisdlc compile --client claude` và `--client opencode` ra artifact đúng định dạng; golden test chặn trôi.

---

## GĐ-4 · BMAD pipeline — Bước 2 (tuần 4)

| # | Hạng mục | File | Xong khi |
|---|---|---|---|
| 4.1 | Bộ chạy skill BMAD | `phases/plan.py` | ✅ Chạy tuần tự `project-context → prd → architecture → ux → epics-and-stories`. **Bỏ `sprint-planning`**: xếp lịch story là việc có đáp án đúng, tính bằng `control/scheduler` |
| 4.2 | Normalizer | `control/normalize.py` | ✅ Markdown BMAD → mô hình framework (PRD + epic/story); **ranh giới giữ BMAD là dependency** |
| 4.3 | Tách story | `phases/story_split.py` | ✅ Mỗi story một file `stories/EPIC-xx/STORY-xx-yy.md` + `stories.index.json` kèm sóng song song |
| 4.4 | Cổng máy | `control/machine_gate.py` | ✅ schema · không chu trình · **mọi FR được ≥1 story phủ** · story không vượt ngưỡng |
| 4.5 | Nối cổng người | `phases/plan.py` | ✅ Dừng ở mỗi cổng; `--auto-approve` hoạt động; tự duyệt vẫn ghi lại câu hỏi mở BMAD nêu |

**Mốc demo 4:** `aisdlc plan` từ `docs/requirements.md` thật → đủ 5 artifact + `stories.index.json`, dừng đúng ở từng cổng.

*Đã đạt phần chạy khô:* epics thật → 12 story / 4 epic, cổng máy ĐẠT, sóng song song tính đúng (story cùng epic ghi vào thư mục rời nhau mới được cùng đợt). Còn lại là chạy toàn chuỗi trên agent thật ở GĐ-9.

---

## GĐ-5 · Mockup — Bước 3 (tuần 5)

| # | Hạng mục | File | Xong khi |
|---|---|---|---|
| 5.1 | Skill sinh mockup | `kit/skills/aisdlc-mockup-html/` | ✅ Skill của framework; dùng `ui-ux-pro-max`/`design-system` cho phần nghề, `DESIGN.md` thắng khi mâu thuẫn |
| 5.2 | Bộ sinh | `phases/mockup.py` | ✅ Mỗi màn hình một phiên, một HTML + `index.html` cho người duyệt |
| 5.3 | Chụp ảnh | `harness/browser.py` | ✅ Playwright qua `node_modules` của dự án; thiếu thì cổng trượt, không im lặng |
| 5.4 | Trích contract | `control/design_contract.py` | ✅ Trang **đã render** → route · component (aria) · nhãn · ràng buộc nhập liệu |
| 5.5 | Đối chiếu | `control/machine_gate.py` | ✅ Mọi màn hình có mockup · **không mục `unresolved`** · có route · story trỏ `screen_id` có thật |
| 5.6 | Chuẩn bị cho bước map | `control/design_contract.py` | ✅ `slice_for(screen_id)` trả đúng một màn hình — đầu vào của 6.7a |

**Mốc demo 5:** mở `mockups/index.html` xem được toàn bộ màn hình; `design-contract.json` hợp lệ.

*Đã đạt phần chạy khô:* 6 mockup fixture → chromium thật → hợp đồng đủ 6 màn hình; cổng chặn đúng ba lỗi cố ý (thiếu route, còn `data-unresolved`, thiếu file).

---

## GĐ-6 · Harness + Implement — Bước 4 (tuần 6–7)

Nặng nhất. Tách hai tuần.

### Tuần 6 — harness

| # | Hạng mục | File | Xong khi |
|---|---|---|---|
| 6.1 | PromptCatalog | `kit/prompts/`, `harness/prompts.py` | ✅ Prompt có version, biến rỗng là lỗi; AR-x chọn bằng mục `Binds:` chứ không phán đoán |
| 6.2 | Tool thật | `harness/tools.py` | ✅ test · lint · sast, mỗi tool có test + prose "khi nào gọi". Chụp màn hình do harness làm (agent tự chụp là tự chấm mình); commit dùng thẳng `git` + guard `git-stage` |
| 6.3 | Sandbox | `harness/sandbox.py` | ✅ Docker `--network=none` `--cap-drop=ALL` non-root; test chạy trên docker thật: không ra được mạng, không đọc được ngoài mount |
| 6.4 | 8 guard | `harness/guardrails.py` | ✅ Đủ 8 (thêm `process-ref` luật 6, 2026-09-05); mỗi guard một lệnh, exit 2 là chặn; từng guard có test chặn thật; `doctor` báo hook biên dịch thiếu guard mới |
| 6.5 | Quan sát | `harness/observe.py` | ✅ `evidence/{story}.jsonl`, `seq` do file cấp (an toàn khi chạy song song), cost + latency lấy từ luồng client |
| 6.6 | Định tuyến vai | `harness/routing.py` | ✅ `build_spec` **từ chối** `session_id` cho vai rà soát; reviewer READ_ONLY, cấm Write/Edit (gộp `subagent.py` vào đây — không cần hai file cho một việc) |

### Tuần 7 — vòng lặp story

| # | Hạng mục | File | Xong khi |
|---|---|---|---|
| 6.7 | Vòng đời story | `phases/implement.py` | ✅ Một phiên một story; harness tự chạy lại test/lint sau lượt agent |
| 6.7a | **Map mockup — nửa nạp** | `harness/mockup_map.py` | ✅ Đúng một lát cắt; test kiểm không rò màn hình khác |
| 6.7b | **Map mockup — nửa đối chiếu** | `harness/mockup_verify.py` | ✅ Chạy dev server, mở route thật bằng chromium, đối chiếu, ghi `mockup_map` |
| 6.7c | Cổng khớp mockup | `control/gate.py` | ✅ Thiếu component đã hứa → trượt; thừa chỉ cảnh báo; **vùng `data-sample` chỉ cam kết có mục, không cam kết nội dung** |
| 6.8 | Thất bại + retry | `phases/implement.py` | ✅ Lỗi hạ tầng có hạn mức riêng, không tính vào `max_retries`; lượt sau nhận đúng danh sách mục trượt |
| 6.9 | `aisdlc run` | `phases/run.py`, `cli.py` | ✅ Epic tuần tự, đợt song song, worktree riêng, merge cuối đợt, resume; `--sequential`, `--epic`, `--no-isolate`. Thêm `aisdlc verify` (hậu kiểm) và `aisdlc tool` |

*Đã đạt phần chạy khô:* điều phối chạy trên kho git + worktree thật với agent giả — story song song đúng đợt, merge tuần tự, dừng đúng chỗ khi trượt, chạy lại tiếp từ chỗ dở. Còn lại là chạy trên agent thật ở GĐ-9.

**Mốc demo 6:** `aisdlc run --epic EPIC-01` chạy hết một epic ≥5 story (trong đó **≥1 story có giao diện**) trên `references/teamflow`; có story chạy song song; story UI sinh được `mockup_map` với `missing: []`; dừng giữa chừng resume đúng chỗ.

---

## GĐ-7 · Kiểm định — Bước 5 (tuần 8)

| # | Hạng mục | Chạy thật bằng | Xong khi |
|---|---|---|---|
| 7.1 | Deep review | ✅ `phases/implement.py` — phiên mới, cấm sửa code, trả mục `[chặn]` máy đọc được |
| 7.2 | Unit/functional | ✅ `verify.unit` (mặc định lấy lệnh test của dự án) |
| 7.3 | SIT | ✅ `verify.sit`, sandbox có mạng |
| 7.4 | API contract | ✅ `verify.api-contract` |
| 7.5 | E2E | ✅ `verify.e2e`; đối chiếu màn hình vs mockup nằm ở cổng story (6.7b) |
| 7.6 | UAT | ✅ `verify.uat` |
| 7.7 | Performance | ✅ `verify.perf` |
| 7.8 | Security | ✅ `verify.security` + `sbom` + `image-scan` |
| 7.9 | Mutation | ✅ `verify.mutation`, **cộng** phép kiểm rẻ luôn chạy được: test không có khẳng định nào |
| 7.10 | Cổng story | ✅ `control/gate.py` — 6 điều kiện; test đẩy story có test giả → chặn thật |

**Nguyên tắc của cả GĐ-7:** ba kết quả chứ không phải hai — đạt · không đạt
· **chưa cấu hình**. Chưa cấu hình chỉ cảnh báo ở mức story, nhưng chặn ở
cổng trước triển khai, trừ khi được miễn tường minh.

**Mốc demo 7:** cố tình đẩy một story có secret hardcode và test giả → gate chặn, nêu đúng lý do.

---

## GĐ-8 · DevSecOps — Bước 6 (tuần 9)

| # | Hạng mục | Xong khi |
|---|---|---|
| 8.1 | Container | ✅ model viết Dockerfile + compose, khung prompt cấm root/`latest`/bí mật |
| 8.2 | CI/CD | ✅ `write_ci_workflow` sinh bằng code, chạy đúng bộ lệnh người chạy |
| 8.3 | SBOM + quét image | ✅ hai loại kiểm định `sbom`, `image-scan` |
| 8.4 | IaC | ✅ nằm trong prompt devsecops (`deploy/`), kiểm bằng cổng |
| 8.5 | Observability | ✅ prompt yêu cầu log có cấu trúc + cảnh báo theo **triệu chứng người dùng** |
| 8.6 | Runbook | ✅ kiểm đủ 4 mục bằng code |
| 8.7 | Cổng pre-deploy | ✅ `aisdlc pre-deploy` + `pre-deploy-report.json` để người ký |

**Mốc demo 8:** `aisdlc pre-deploy` trên dự án chưa xong → nêu đúng thứ còn thiếu; đủ điều kiện → mời ký.

---

## GĐ-9 · Đầu-cuối (tuần 10)

Một dự án thật, quy mô nhỏ nhưng đủ hình dạng: **3 epic · ~15 story · có UI · có API · có DB**.

| Kiểm | Đạt khi |
|---|---|
| Truy vết | Mọi FR trong PRD → story → code → test, nối được |
| Chất lượng | Coverage ≥ ngưỡng; 0 phát hiện high/critical |
| Thị giác | Màn hình thật khớp mockup |
| Vận hành | Chi phí và thời gian đo được từng story |
| Bền bỉ | Ngắt giữa chừng, chạy lại tiếp đúng chỗ |
| 6 nhóm harness | Cả sáu ô có bằng chứng chạy (mục 16 SOLUTION) |
| R1–R14 | Mỗi R có ≥1 test hoặc artifact chứng minh |

**Đầu ra:** `docs/ACCEPTANCE-REPORT.md` — sinh bằng `aisdlc report`, mọi số
đọc từ artifact và bằng chứng trên đĩa.

### Chạy thật lần 1 — những gì nó dạy

Chạy `aisdlc plan` trên một dự án trống (chỉ có `docs/requirements.md`),
client thật, không giả lập:

| Pha | Kết quả | Chi phí |
|---|---|---|
| project-context | `complete`, 10 câu hỏi mở, 11 giả định | $1.52 |
| prd | bỏ qua (đã có từ spike S6) | — |
| architecture | bỏ qua (đã có) | — |
| ux | `partial`, 5 câu hỏi mở → tự duyệt **có ghi lại** lý do | $3.71 |
| epics | **api_error** giữa chừng | $2.69 |

Bốn lỗi thật chỉ lộ ra khi chạy thật, đã sửa:

1. **Guard chặn cả BMAD ghi PRD** — ngoài story không có `write_scope`, mà
   phạm vi rỗng nghĩa là chặn. Cách duy nhất để chạy tiếp sẽ là tắt guard ở
   nửa đầu vòng đời.
2. **Bảng màn hình đọc sai cột** — BMAD sinh `screen_id | Route | Đến từ |
   Mục đích`, khác thứ tự trong mẫu của chính nó; đọc theo thứ tự thì route
   mất hẳn.
3. **Pha lập kế hoạch không thử lại khi lỗi hạ tầng** — mất $2.69 vì một
   lần đứt kết nối, trong khi vòng lặp story đã có cơ chế này.
4. **Ảnh sandbox `alpine` trơn** — `npm test` trong đó đỏ vì thiếu công cụ
   chứ không phải vì code sai.
5. **Chi phí lập kế hoạch không vào bằng chứng** — báo cáo nghiệm thu hiện
   $0.00 trong khi lượt chạy tốn $7.92; với dự án nhỏ đó là phần đắt nhất.
6. **Prompt gọi `aisdlc tool test`** trong khi `aisdlc` không nằm trên PATH
   của phiên agent — agent sẽ tự chạy pytest bằng tay, lần chạy đó không
   vào bằng chứng, rồi guard `completion` chặn nó kết thúc vì "chưa chạy
   test bao giờ".

7. **Bản đồ phủ nhận nhầm câu văn xuôi** — dòng thật của BMAD là
   "FR-13 → KHÔNG CÓ STORY. … Khớp nối AR-18 ở Story 1.2"; parser thấy "có
   mã FR + có số hiệu story" nên gán FR-13 cho story 1.2, rồi cổng máy chặn
   cả 18 story vì một câu văn xuôi.

8. **`aisdlc run` đòi sai cổng** — chỉ đòi `stories`, nên story khai
   `screens` vẫn chạy được khi chưa có mockup nào, rồi trượt vì "chưa đối
   chiếu" sau khi đã tiêu tiền viết xong code. Nay đòi `readiness`.
9. **Phụ thuộc cài đặt bị tính vào diff của story** — `node_modules`,
   `dist` xuất hiện vì story **chạy**, không phải vì story **viết**; tính
   vào phạm vi thì mọi story cài phụ thuộc đều trượt.
10. **Hợp đồng thị giác gộp mọi trạng thái** — mockup thật dựng "Mở nguội",
    "Tìm kiếm chưa sẵn sàng", "Có kết quả" cạnh nhau trong một file (đúng
    như skill yêu cầu), nhưng ứng dụng thật ở một thời điểm chỉ ở **một**
    trạng thái. Gộp hết thì không màn hình nào khớp nổi. Nay mockup khai
    `data-state="primary"` và `data-annotation`.

11. **Bộ bắt test giả bỏ sót file chưa commit** — `git ls-files` trơn chỉ
    thấy file đã theo dõi, mà test giả vừa viết xong thì chưa nằm trong chỉ
    mục git; đó đúng là lúc cần bắt nó nhất.
12. **Skill trong dự án cũ hơn kho framework** — dự án giữ một **bản sao**
    skill từ lần `setup`; sửa skill mà không cài lại thì agent vẫn chạy bản
    cũ. Lộ ra khi dựng lại mockup mất $2.56 mà vẫn theo quy ước cũ. `doctor`
    nay so bản sao với bản gốc.

13. **Ràng buộc nhập liệu lấy cả trang** — một ô tìm kiếm dựng lại ở 11
    trạng thái thành 11 ràng buộc giống hệt nhau; người đọc hợp đồng không
    biết đó là một hay mười một ô.
14. **Tạo tác của công cụ bị tính vào diff** — agent mở trình duyệt để xem
    trang thì Playwright MCP để lại `.playwright-mcp/` ở gốc worktree; mở
    trình duyệt một lần là trượt cổng phạm vi.

15. **Guard soi nhầm cây** — hook được biên dịch một lần vào
    `.claude/settings.json` với `--project` là gốc dự án, nhưng story chạy
    trong worktree riêng. `diff-scope` đi đọc `git status` của cây khác,
    thấy 600 file tài liệu kế hoạch chưa commit và chặn **mọi** lệnh Bash.
    Người viết vật lộn 61 lượt rồi chạm `max_turns`. Nay lấy `cwd` từ chính
    sự kiện hook.
16. **Người rà soát không nhận `write_scope`** — chỉ lượt của người viết
    đặt `spec.env`. `scope_from_env` rỗng đẩy `diff-scope` vào nhánh "chưa
    khai phạm vi mà đã đổi file", chặn mọi lệnh Bash của người rà soát. Nay
    truyền phạm vi, nhưng **không** truyền mã story: mã story kích guard
    `completion`, chặn người rà soát dừng lại khi test đang đỏ — đúng lúc
    nó có nhiều thứ đáng báo cáo nhất.
17. **Ba cổng cùng mù sau khi agent commit** — `changed_files` so cây làm
    việc với `HEAD`, mà prompt khuyến khích agent tự commit từng phần vì
    merge chỉ thấy thứ đã commit. Đo trên e9: **0 file so với HEAD, 11 file
    so với điểm rẽ nhánh**. Phạm vi ghi đạt vô điều kiện, test-thật không
    còn gì để kiểm, người rà soát nhận diff rỗng rồi phải mò cả repo — 43
    và 51 lượt, $4,5 mỗi phiên. Nay so với `merge-base`, không với đầu
    nhánh: story trước có thể đã merge khi story sau đang chạy.
18. **Cờ `guard_blocked` khớp chữ "hook"** — nó bật khi thấy chuỗi con
    "hook" trong bất kỳ `tool_result` lỗi nào. Dự án React nói về hook suốt
    ngày; "Invalid hook call" là thông báo thường gặp. Cờ sai đi thẳng vào
    báo cáo nghiệm thu và đã tốn một vòng chẩn đoán đuổi theo lần chặn
    không có thật. Nay nhận theo đúng định dạng hook của Claude Code, và
    `guard_messages` được lưu vào bằng chứng.
19. **Người rà soát chỉ nhận danh sách tên file** — phải Read từng cái để
    tự dựng lại diff, thứ harness đã biết sẵn. Nay đưa thẳng
    `git diff <base>` kèm `--stat`.
20. **Story tự mâu thuẫn, vòng lặp không nhận ra** — TCCN 1 đòi "lockfile
    được commit", `write_scope` chỉ khai `package.json`. Guard chặn ghi
    ngoài phạm vi, agent làm **đúng** chỉ dẫn (hoàn nguyên lockfile rồi báo
    phạm vi khai thiếu), người rà soát chặn **đúng** vì TCCN 1 không đạt.
    Không mắt xích nào sai, kết quả vẫn là 4 lượt y hệt nhau và $9,85.
    Hai chỗ sửa: lockfile đi theo manifest của nó (7 cặp; không đếm vào
    ngưỡng "chạm quá nhiều nơi" vì đó là hệ quả tự động), và vòng lặp dừng
    khi hai lượt liền cùng một mục chặn.
21. **Chạy lại story `failed` thì bản ghi không theo kịp** — máy trạng thái
    không có cạnh `failed → running`, và `_safe_transition` nuốt lỗi bằng
    `except TransitionError: pass`. Story chạy lại xong, merge xong, wave
    sau khởi động — mà `aisdlc status` vẫn báo "failed", và $9,76 chi phí
    lượt mới không vào sổ. Nay về `pending` trước khi chạy, và bước nhảy bị
    từ chối thì **nói ra**.
22. **Tiêu đề báo cáo nghiệm thu cụt** — CLI mặc định `--project .`, mà
    `Path(".").name` là chuỗi rỗng.
23. **Guard tiêm mã chỉ biết Python** — trên dự án TypeScript, đúng loại
    dự án framework vừa chạy thật, `execSync(\`rm -rf ${dir}\`)` đi qua
    sạch trong khi báo cáo vẫn ghi "7 guard đã nối". Guard có mặt mà không
    bao giờ nổ là "chưa cấu hình bị đếm là đạt", chỉ khó thấy hơn. Nay tách
    mẫu theo họ ngôn ngữ — gộp lại thì `{` của object tuỳ chọn JS bị đọc
    thành nội suy f-string và chặn oan `execFileSync('git', [...], { cwd })`,
    đúng dạng **an toàn** guard lẽ ra phải khuyến khích. Kiểm chứng trên
    agent thật: `PreToolUse:Write` chặn, `permission_denials=1`, tệp không
    được tạo.

Đây chính là giá trị của việc chạy thật: hai mươi ba lỗi trên đều
**không** lộ ra trong 776 test, vì test nào cũng dựng sẵn đúng điều kiện mà
thực tế không tự có.

Đáng chú ý: **lỗi 17, 18 và 21 không làm chậm gì cả — chúng làm báo cáo nói
sai.** Cùng một nguồn gốc: chỗ nào nuốt lỗi hoặc suy ra trạng thái bằng
phép xấp xỉ, chỗ đó nói dối. Chi phí thật của guard đo được là **110 ms mỗi
thao tác** (khởi động Python) và **0,03 s** cho `git status` trên 12.873
file — tức 26 giây cho cả một story. Cái đắt chưa bao giờ là guard, mà là
guard chặn oan và cổng chấm mù.

### Chạy thật — dựng mockup 5 màn hình

`aisdlc mockup` trên `EXPERIENCE.md` thật: **5 màn, $9.22, 15–25 phút**.
Mỗi mockup 28–34KB, đủ hai thẻ meta, không lỗi JavaScript, mọi phần tử
tương tác có tên gọi, ràng buộc nhập liệu nằm ở thuộc tính HTML.

Cổng **chặn** với 52 chỗ `data-unresolved` — và đó là kết quả đúng:

* 21 chỗ quy về hai câu hỏi UX chưa ai trả lời (dark mode; tên sản phẩm mà
  PRD ghi "cần xác nhận");
* **31 chỗ còn lại là lỗ hổng mới** mà việc dựng mockup phát hiện trong
  chính `DESIGN.md` — thiếu trạng thái "gỡ thẻ" cho `tag-chip` mà FR-8 đòi,
  không bề mặt nào chứa nổi thông báo ghi hỏng, màn `tags` cần một hàng
  quản lý thẻ mà đặc tả không định nghĩa.

Hai bài học đưa thẳng vào code:

1. Cổng cũ in một dòng mỗi màn với trích đoạn đầu — năm dòng giống hệt
   nhau. Nay gom theo **mã câu hỏi**, nên người duyệt thấy "trả lời 2 câu là
   mở khoá 21 chỗ" thay vì một bức tường.
2. Mockup dựng nhiều trạng thái cạnh nhau nên chú thích của chính tài liệu
   ("Mở nguội", "notes-list — các trạng thái") lọt vào hợp đồng. Nay có quy
   ước `data-state="primary"` và `data-annotation`.

### Chạy thật — hiện thực một story trên agent thật

Story `STORY-01-01` chạy trong worktree riêng, guard bật đầy đủ:

* agent viết **test trước** rồi mới viết code, mọi file nằm trong
  `write_scope` — guard không phải chặn lần nào;
* code nó viết dẫn chiếu đúng bốn quyết định kiến trúc mà bộ chọn ngữ cảnh
  đưa vào prompt (AR-1 một đường ghi · AR-2 hướng phụ thuộc · AR-5 `rev`
  thay đồng hồ · AR-15 không nuốt lỗi) — bằng chứng rằng chọn AR theo mục
  `Binds:` là **tra cứu** chứ không phải trang trí;
* test nó viết có ca patch `socket` để chứng minh tạo ghi chú chạy được khi
  mất mạng hoàn toàn — đúng tiêu chí chấp nhận, không phải test giả;
* lượt 1 **hết số lượt** (31/30, $2.74) vì kẹt ở guard `completion`: guard
  bảo chạy `aisdlc tool test` mà `aisdlc` không có trên PATH của phiên;
* harness tự chạy lại test sau lượt agent và bắt được một lần trượt mà
  agent không thấy → story vào lượt thử thứ hai, đúng thiết kế.

**Kết cục: story bị chặn, và bị chặn vì đúng lý do.** Sau hai lượt ($4.06):

```
STORY-01-01: CHƯA XONG
  ✅ test   ✅ lint   ✅ phạm vi ghi   ✅ test thật
  ✗ map mockup — chưa đối chiếu: danh-sach, soan-thao
  ✗ rà soát — [chặn] toàn bộ story hiện thực bằng Python + sqlite3, trong
    khi kiến trúc chốt TypeScript 5 strict / React 19 / Vite 7 / IndexedDB
```

Mục chặn thứ hai là **người rà soát độc lập bắt được, không phải cổng máy**.
Và nó bắt đúng một lỗi của *người vận hành*: `.ai/config.json` của lượt thử
khai `tools.test = python3 -m unittest`, agent theo cái gợi ý công cụ đó
thay vì theo kiến trúc. Không có phiên rà soát riêng — cấm sửa code, ngữ
cảnh sạch — thì một story "test xanh, lint sạch, đúng phạm vi" đã được tính
là xong, với ngôn ngữ sai hoàn toàn.

Đây là bất biến 6 ("người viết code không tự duyệt code") hoạt động trên
tiền thật, không phải trên test.

Mục chặn thứ nhất cũng đúng: story khai `screens` nhưng dự án chưa có
mockup nào, nên không có gì để đối chiếu. Chính vì ca này mà `aisdlc run`
được sửa để đòi cổng `readiness` — cổng gắn vào **cả** chỉ mục story lẫn
hợp đồng thị giác — thay vì chỉ đòi `stories`.

### Chạy thật lần 2 — chuỗi lập kế hoạch chạy hết

Sau khi sửa, `aisdlc plan` đi hết chuỗi trên `epics.md` thật (1078 dòng,
BMAD sinh, $4.45 cho pha epics):

* **18 story / 5 epic**, mỗi story một file, `covers` · `write_scope` ·
  `depends_on` · `screens` đọc được hết;
* cổng máy **ĐẠT**, và trước đó nó đã chặn đúng một lần vì một story đụng
  vào FR-13 — yêu cầu đang bị OQ-1 chặn;
* truy vết: 14/17 FR có story phủ; ba FR còn lại (FR-13..FR-15) chính là
  phần PRD ghi rõ là ngoài phạm vi MVP;
* pipeline dừng đúng ở cổng `stories` chờ người duyệt.

---

## Tổng thời gian

```
GĐ-0  spike           3 ngày
GĐ-1  control plane   tuần 1
GĐ-2  kit + setup     tuần 2
GĐ-3  đa client       tuần 3
GĐ-4  BMAD pipeline   tuần 4
GĐ-5  mockup          tuần 5
GĐ-6  harness+impl    tuần 6–7   ← nặng nhất
GĐ-7  kiểm định       tuần 8
GĐ-8  devsecops       tuần 9
GĐ-9  đầu-cuối        tuần 10
```

**≈ 10 tuần** (9 tuần + 3 ngày spike). Spike không phải phần thêm — nó mua lại rủi ro phải làm lại GĐ-3 và GĐ-6.

---

## Phụ thuộc

```
GĐ-0 ──► GĐ-3 (kết quả spike đổ vào adapter)
     └─► GĐ-6 (mô hình guard, sandbox)
GĐ-1 ──► mọi GĐ sau (state, config, worktree)
GĐ-2 ──► GĐ-4 (phải có skill BMAD đã nạp)
GĐ-4 ──► GĐ-5 (cần ux-spec)  ──► GĐ-6 (cần story + design-contract)
GĐ-6 ──► GĐ-7 (cần code)     ──► GĐ-8 (cần cổng)
```

Chạy song song được: GĐ-2 và GĐ-3 (khác vùng); GĐ-5 và phần harness của GĐ-6.

---

## Cách làm việc

| Quy tắc | Chi tiết |
|---|---|
| TDD | Test trước, mỗi hạng mục code + test cùng một commit |
| Commit | Một hạng mục một commit, message nêu rõ đã kiểm chứng gì |
| Không scaffold rỗng | Không tạo file khung chưa dùng tới |
| Ngưỡng ở config | Không hardcode số trong code |
| Bằng chứng | Mỗi "xong khi" phải chạy được bằng một lệnh |

---

## Rủi ro theo giai đoạn

| GĐ | Rủi ro | Dấu hiệu sớm | Dự phòng |
|---|---|---|---|
| 0 | Hook không gắn được ở bề mặt nào | S2/S3/S4 đỏ | Chuyển sang hậu kiểm ở `verify`, khai báo mức thấp hơn |
| 3 | Compiler trôi giữa các client | Golden test đỏ | Khoá định dạng, thêm round-trip test |
| 4 | BMAD sinh story quá lớn | Cổng máy chặn liên tục | Thêm bước chẻ story tự động, hoặc chỉnh prompt |
| 6 | Merge conflict cuối đợt | Conflict xảy ra | Là bằng chứng `write_scope` sai → sửa ở GĐ-4 |
| 6 | Chi phí vượt dự kiến | Cost/story > 3× trung vị | Giảm `max_parallel`, cắt ngữ cảnh nạp, đo lại |
| 7 | Công cụ verify không chạy trong container | Image build lỗi | Cố định version trong image, pin digest |
| 9 | Đầu-cuối lộ lỗi kiến trúc | Nhiều story blocked | Dừng, phân tích nguyên nhân gốc, sửa trước khi mở rộng |

---

## Việc kế tiếp

Theo `docs/ACTION-PLAN-2026-09-05.md` (5 đợt, xuất phát từ
`docs/DEEP-REVIEW-2026-09-05.md`). Đợt 0 xong (G1 G2 G3, commit `297282e`).
Bước tiếp: **đợt 1 — G4** truyền `--settings` tường minh + nhịp tim guard,
đo trước/sau trên `par` với `.claude/` gỡ khỏi git.

| Hạng mục | Unit test | Kiểm thật | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| G1 G2 G3 | 21 | — (guard thuần) | `297282e` | ✅ |
| QĐ4 pre-deploy không suy biến | 5 | — (cổng thuần) | | ✅ |
| G4 mảnh 1 `settings_file` | 2 | `par`, `.claude/` không commit. **Trước** (wheel e7b618e): story XONG, 6 phiên, 0 sự kiện guard. Đầu dò A–D: worktree không cờ → 0; `--settings` tệp/json → 2; gốc dự án → 2 | docstring `claude_code.py` | ✅ |
| G4 mảnh 2 cổng "guard có chạy" | 13 | Lượt "sau" đầu tiên báo trượt **sai**: hook chạy 17 lần nhưng agent ghi file chỉ bằng Bash → sửa: nhịp tim `GUARD_SEEN` + `diff-scope` ghi `FILE_CHANGE` theo mtime. **SAU-2**: XONG lần 1, $0,50, evidence `guard_seen=1, file_change=1` | docstring `claude_code.py` | ✅ |
| G4 mảnh 3 `doctor` hook trong worktree | 2 | — (kiểm tĩnh) | | ✅ |
| G11 test meta | 3 | — | | ✅ |
| G6 hợp quy client — `tests/conformance/`, `control/conformance.py`, `test_release_gate`, CI tuần | 12 | **Lần 1** (2026-09-05): Claude 3/5, OpenCode 1/5 — lộ 3 lỗi thật + 2 tiêu chí sai (ba dòng dưới). **Lần 2**: Claude **5/5**, $1,25; OpenCode 4/5 rồi **5/5** sau khi đọc đúng dòng `✗ Write … failed`. Bảng hai cột xanh, log thô giữ ở `.conformance/` | `docs/CONFORMANCE.md` | ✅ |
| G6 phát hiện 1 — worktree **mang** `.claude/settings.json` + `.opencode/` chưa commit (`WorktreeManager._carry_client_config`) | 2 | Hợp quy lần 1: OpenCode C1 `rm -rf` chạy thật, tệp mất, `.opencode/` không có trong worktree → guard không tới. Đây là G4 cho OpenCode, sửa ở harness nên client nào cũng hưởng | `docs/CONFORMANCE.md` lần 2 | ✅ |
| G6 phát hiện 2 — guard `completion` chặn Stop vô hạn khi dự án **chưa cấu hình** test | 1 | Hợp quy lần 1: Stop bị chặn 2 lần/phép trên dự án không khai lệnh test, agent đốt hết lượt. Sửa: `skipped` → cho dừng, cổng story vẫn ghi "chưa cấu hình" (D4 — bốn kết cục gộp hai) | log thô `.conformance/claude/…/S-C2.log` | ✅ |
| G6 phát hiện 3 — bộ chạy: giữ tạo tác `.conformance/`, đọc `tool_uses` thay vì lời agent, lọc `completion` khỏi guard-tool, không thừa hưởng `CLAUDE_*` của phiên cha, chi phí sống qua lần ghép | 3 | C3 lần 1 trượt **giả**: phiên con thừa hưởng env của phiên Claude đang chạy bộ hợp quy → tự chuyển sang Bash. C2 lần 1 trượt **giả**: guard đã chặn, agent viết lại bản an toàn — tiêu chí "không tệp" sai, đúng là "nội dung bị chặn không ra đĩa" | | ✅ |
| G12 `VERIFIED`, `DONE` chỉ sau merge | 11 | SAU-2 trên `par`: `verified → done` sau `merge.completed`; `status` 5/5 done, không `verified` sót. Di trú sổ cũ: unit test (par không có sổ cũ cần di trú) | | ✅ |
| G10a gỡ `max_context_tokens`, đo `prompt_chars` | 5 | — | | ✅ |

**Đợt 3 — cổng kiểm được theo tiêu chí:**

| Hạng mục | Unit test | Kiểm thật | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| G7 một kiểu `Outcome` (`control/outcome.py`): 6 kết cục, 3 câu hỏi (`blocks`/`counts_as_done`/`must_be_named`), một bảng ký hiệu; `Check` dùng chung cho `gate` + `deploy`, `KindResult.outcome`; hết `skipped=True` chung chung | 8 | — (refactor thuần, cổng không đổi hành vi: 196 test cũ xanh) | | ✅ |
| Parser output runner (`harness/testlog.py`): node `spec`/`tap`, vitest verbose/mặc định, pytest `-v`/`-q`, coverage pytest-cov/istanbul; không nhận ra → `test_ids=[]`, không đoán | 13 + 1 | Fixture là output **thật** của `par` (node 26), `e9` (vitest 5), pytest 9.1; ghi vào `tool_run test.detail.test_ids/failed_ids/coverage` qua `tools._record` | `tests/fixtures/testlog/` | ✅ |

| G5 hợp đồng tiêu chí ↔ test (`control/acceptance.py`): mã `AC-<story>-<i>` in vào story `.md` và prompt; cổng "tiêu chí có test" đọc `test_ids` của lần xanh cuối — thiếu → FAILED nêu đúng mã; không đọc được tên test → UNCONFIGURED nêu reporter cần bật; báo cáo cột "TCCN có test" `k/n` (`?/n` khi chưa đọc được); prompt rà soát bỏ việc đếm, giữ phần phán đoán | 13 | `par` EPIC-04, 2 story × 2 nhánh A/B (4 lượt Claude thật, 2026-09-05): **12/12** tiêu chí có test mang mã trong tên (`AC-STORY-04-01-1: …`), không nhắc thêm ngoài prompt; cổng "tiêu chí có test" ✅ cả 4; test_ids 23–25/lượt đọc từ `node --test` | evidence `par-A/B` (scratch) | ✅ |
| G10b `coverage.min` thật: số từ output runner; không có số → UNCONFIGURED "thêm `--coverage`/`--cov`"; thấp hơn → FAILED `60% < 85%` | 4 | — | | ✅ |
| G8 TDD kiểm được (`control/tdd.py`): story thêm test (tệp mới hoặc dòng mới mang `AC-…`) mà không có lần `test` đỏ trước lần xanh cuối → mục "TDD" FAILED; refactor không thêm test → không áp dụng; test có sẵn bớt ca → ghi `qa:test-delta` + đưa vào ngữ cảnh người rà soát, không tự chặn | 14 | cùng 4 lượt trên: lần chạy test đầu **đỏ** ở 4/4 story (ĐỎ→ok…), mục "TDD" ✅ cả 4; `qa:test-delta` ghi 4/4 (không bớt ca) | evidence `par-A/B` | ✅ |

**ADR-003 (đối chiếu Repo-To-Skill / AREX-Skill / Swarm — 3 mục ADOPT/ADAPT, còn lại KEEP/REJECT/PROPOSED có lý do):**

| Hạng mục | Unit test | Kiểm thật | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| #1 router vào prompt (`skills.offer`, mặc định tắt) + telemetry `skills.offered/abstained/used` trong `AGENT_RUN` — `used` đọc từ luồng `tool_use` `Skill` | 4 | A/B `par` EPIC-04 xong: A (tắt) $2,72 · B (bật) $2,74 — **+0,7 %**, router abstain cả 2 story (đã xét 118), `used` 0/0 **theo cấu trúc** (catalog không có skill khớp); telemetry `skills{enabled,offered,abstained,considered,used}` ghi đủ 4/4 lượt. **Đo lại router trước đó**: e9 chọn 8/18, cả 8 sai → sửa gốc → 0/20 (ADR-002 §6.1). Kết luận: mục kỹ năng vô hại khi abstain; "được dùng" chưa đo được — cần dự án có skill khớp (R2 e9 + cài `ui-ux`) | | ◐ |
| #2 scripts của skill phải **biên dịch được** trước khi `verified` (`py_compile`-tương-đương, `sh -n`, `node --check`) | 2 | `par`: 120 skill, 83 có scripts, **1** rớt; `e9`: 156 / 119 / **1** — cùng một skill (`building-vulnerability-dashboard-with-defectdojo`, `scripts/process.py` không parse được); 1,1–1,5 s cho cả bộ | | ✅ |
| #9 `HANDOFF` evidence: vai nào nhận slot nào từ nguồn nào; bất biến máy kiểm — gói reviewer/security không có nguồn `agent`, slot chưa khai nguồn hiện `?`; báo cáo in chuỗi bàn giao | 6 | — (bất biến, không phải số đo) | | ✅ |

**Bước 0 + đợt 4 (sau STATUS 2026-09-05):**

| Hạng mục | Unit test | Kiểm thật | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| P0-1 hook ghim đường dẫn tuyệt đối → `AISDLC_PROJECT` từ harness (3 vai), guard ưu tiên env, `doctor` mục "hook trỏ đúng dự án" | 4 | A/B `par-A`/`par-B`: 4 lượt trượt "guard có chạy" sai, bằng chứng nằm ở `par` gốc — nguyên nhân; kiểm lại qua dogfood (dự án dựng ở `.dogfood/`, hook biên dịch tại chỗ) | | ✅ |
| P0-2 test song song flaky | — | không tái hiện: 20/20 riêng + bộ đầy đủ 1 155 OK có log trọn vẹn | log scratch | ◐ hạ P2, giữ mở |
| R4 tài liệu khớp mã: 5 đường dẫn lệch trong SOLUTION (`kit/agents/`, `kit/mcp/`, `control/fsm.py`, `phases/ship`, `phases/verify`) + test meta chặn tái diễn | 1 | — | | ✅ |
| R1 chuẩn bị PyPI: `uv build` wheel+sdist, `twine check` PASS, `release.yml` trusted publishing, README "Phát hành" | — | việc tay còn lại: tài khoản tổ chức tạo project + khai publisher, rồi `git tag v0.1.0` | `dist/` (ignore) | ◐ chờ chủ đầu tư |
| R5 kho dogfood `tests/dogfood/par` (đầu vào từ commit nền, hook biên dịch tại chỗ, mốc $3,14 / 3 story lượt đầu, `main` chỉ đổi qua merge) | — | **Lần 1 (2026-09-05): 0/3, $17,3** — hai nguyên nhân, cả hai đáng tiền: (1) đầu vào lấy `tools.test = node --test src/` ở commit trước bản vá → MODULE_NOT_FOUND bị coi là *test đỏ*, guard `completion` chặn Stop ~10 lần/lượt, 28–42 lượt/phiên (lỗi kit + lỗi phân loại); (2) `.claude/settings.json` harness chép vào worktree bị tính là "file ngoài phạm vi ghi" khi dự án không gitignore `.claude/` → 3/3 trượt "phạm vi ghi" (lỗi harness thật, chưa từng lộ vì `par`/`e9` đều ignore). Điểm sáng: reviewer tự kiểm chứng và gọi đúng tên "[bế tắc] .ai/config.json (tools.test)"; `main` không đổi ngoài merge; 01-02 đặt tên test đúng mã 2/2 | `.dogfood/par` | ✅ **lần 2** (sau sửa): **3/3 xong**, $5,63 (≤ 2 × $3,14), tiêu chí có test mang mã 6/6, HANDOFF đủ, 0 guard block sai, `main` chỉ đổi qua worktree (01-01 FF, còn lại merge); 2/3 qua lượt đầu — 01-02 lượt 2 vì reviewer bắt lỗi thật (`slice` vỡ cặp thay thế UTF-16) |
| Sửa từ dogfood: `tools.run_tool` phân loại **không chạy được** (exit 127 / MODULE_NOT_FOUND / command not found, và với `test`: không test nào xanh) → `detail.unrunnable`; guard `completion` cho dừng; cổng "test" ghi UNRUNNABLE (chặn, đúng lý do); `HARNESS_OWNED` += `.claude/settings.json`, `.opencode` | 6 | dogfood lần 2: 3/3, không còn vòng lặp completion, không còn "phạm vi ghi" giả | `.dogfood/par` | ✅ |
| R3 hợp quy lần cuối trước tag | — | **2026-09-05 13:33** sau toàn bộ sửa trong ngày: Claude **5/5** ($1,07) · OpenCode **5/5**; `AISDLC_RELEASE=1 … test_release_gate` xanh | `docs/CONFORMANCE.md` | ✅ |
| R2 e9 EPIC-01 đầu-cuối: `verify.e2e` + `verify.accessibility` **thật** (playwright + axe), không miễn; 4 story còn lại (01-04..01-07) | 1 | **Lượt 1** (STORY-01-04, $7,25): mọi mục máy ✅ kể cả "tiêu chí có test", TDD; evidence có `qa:e2e` ✅ `qa:perf` ✅ `qa:accessibility` ✅ — **lần đầu accessibility chạy thật** — nhưng cổng in "chưa cấu hình" vì tìm tên trần (lỗi 9, đã sửa). Reviewer kiểm chứng bế tắc: AC-3 đòi bài đo AR-16 mà `bench/` ngoài write_scope → sửa kế hoạch (thêm `bench/` vào scope), chạy lại | `e9/_bmad-output` | 🔨 **Lượt 2** ($10,16): reviewer bắt 2 lỗi UX thật ở lần 1 (grid phình, focus kéo ngược) — lần 2 sửa xong, rồi bế tắc kiểm chứng: `package.json` ngoài scope — **nguyên nhân là R2 prep của tôi** (`tests/` playwright bị `vitest run` nhặt; phiên bản cài `^` trái quy ước ghim). Sửa gốc trên `main` (vitest exclude `tests/**`, ghim, `--reporter=verbose`), chạy lượt 3 từ nhánh story còn nguyên công việc |

**Đợt 5 — làm sớm vì song song được (2026-09-05 chiều):**

| Hạng mục | Unit test | Kiểm thật | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| S1 spike sandbox tiến trình agent | — | `docker run node:22-slim`: cài `@anthropic-ai/claude-code` 2.1.261 + khởi động trong ~20 s; `claude -p` trả "Not logged in · Please run /login" — Keychain macOS không mount được vào container, cần token riêng (`claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`, hoặc API key tổ chức). **Kết luận**: khả thi về cơ chế, **chặn ở cấp phát credential** — quyết định của chủ đầu tư; chưa làm mặc định | log scratch `b5zf6dn5v` | ◐ chờ token |
| S3 guard luật 6 (`process-ref`): `STORY-\d+-\d+`/`EPIC-\d+` trong mã nguồn bị chặn ở Write/Edit; test, docs, artifact, `bench/` được phép (test còn **phải** mang mã `AC-…`) | 4 | hợp quy lần sau sẽ biên dịch guard này vào hook (8 guard) | | ✅ |
| OpenCode `--format json` → `MACHINE_OUTPUT`/`COST_REPORTING` NATIVE (chip `task_a7530bf6`): parser `tool_use`/`step_finish`/`text`, tool có tên chuẩn, tokens + cost (số của nhà cung cấp — 9router báo 0) | 3 | đo trên OpenCode 1.18.26 với `read`; hợp quy lần sau đọc tool từ luồng thay vì bản in | | ✅ |
| P1-4 `doctor` mục "lệnh test in coverage" | 2 | — | | ✅ |
| S2 `aisdlc doc <gói> --topic <chủ đề> [--story]` — context7 qua HTTP (`/api/v1/search`, `/api/v1/<id>?type=txt&topic=`), cache `~/.cache/ai-sdlc/docs/`, bằng chứng `doc_lookup`; prompt developer nhắc lệnh trong bảng tool | 6 | đo tay 2026-09-05: `vitest`/`coverage` trả tài liệu thật kèm nguồn; không cần khoá | | ✅ |
| S4 `aisdlc change FR-x "mô tả"` — ghi vào `docs/requirements.md`, đánh dấu `prd.md` → cổng PRD và các cổng sau tự `stale` (cascade sẵn có), sinh `STORY-CH-nn` trong `EPIC-CH` với `covers=[FR-x]`, `write_scope` trống để người khai; story cũ giữ `DONE` | 4 | — | | ✅ |
| S6 quét skill ngoài theo tiêm prompt | — | lớp heuristic đã có trong `registry.verify_structure` (câu tiêm, bí mật, offensive): e9 loại 3/156, par 2/120; quét bằng agent (prompt `story-security-review` chế độ tài liệu) **hoãn** — chi phí ~156 phiên, làm khi có ngân sách riêng | | ◐ |
| S5 chia `cli.py` | — | hoãn tới khi không còn lượt agent nào chạy (hook nhập `aisdlc.cli` mỗi lần gọi; đổi bố cục giữa chừng là cửa sổ lỗi thật) | | ⬜ |

**Đợt OKL (ADR-002 — tầng tri thức vận hành, sau paper Repo-To-Skill):**

| Hạng mục | Unit test | Kiểm thật | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| ADR-002 + đo e9 (156 skill, 11 lần gọi/4 skill) | — | e9 evidence | `docs/ADR-002` | ✅ |
| Registry + vòng đời 5 trạng thái + verify cấu trúc | 15 | dựng trên 156 skill thật e9; 3 skill có bí mật → rejected | `skill-registry.json` | ✅ |
| Router hai-tín-hiệu + abstain + progressive disclosure | 12 | e9: abstain 13/18 (catalog security không có skill app ghi chú — đúng); lộ & sửa 2 va chạm keyword (crypto-migration↔schema, "performative"↔perf) | `aisdlc skill --story` | ✅ |
| Kích hoạt: router → prompt story + telemetry `skills_offered`/`skills_used` | | **chưa** — cần kiểm agent thật | | ⏳ đợt sau |
| Chưng cất + học từ trace (ADR §5) | | | | ⏳ đợt 2 (PROPOSED) |
