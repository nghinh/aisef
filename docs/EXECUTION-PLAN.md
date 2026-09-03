# Kế hoạch thực thi

**Căn cứ:** `docs/SOLUTION.md` v2 (đã duyệt).
**Nguyên tắc lập lịch:**
1. **Rủi ro cao làm trước** — giả định chưa kiểm chứng phải bị loại bỏ trước khi xây nhiều lên trên nó.
2. **Mỗi giai đoạn kết thúc bằng thứ chạy được**, không phải khung rỗng.
3. **Tiêu chí xong kiểm chứng bằng lệnh**, không phải "đã viết xong".
4. Mỗi hạng mục: code + test trong cùng một commit.

---

## Tiến độ (cập nhật 2026-09-04)

| Giai đoạn | Trạng thái |
|---|---|
| GĐ-0 Spike | ✅ **xong** — 6/7 spike xanh, S4 (OpenCode) chưa kết luận, không chặn |
| GĐ-1 Control plane | ✅ **xong** — config · state · fsm · worktree · CLI |
| GĐ-2 Kit + Setup | ✅ **xong** — catalog · detect_stack · lọc 2 tầng · install · constitution |
| GĐ-3 Đa client | ✅ **xong** — adapter · guard · compile · báo cáo mất mát |
| GĐ-4 BMAD pipeline | ✅ 5/5 — `aisdlc plan` chạy chuỗi BMAD, dừng đúng từng cổng, tách 12 story từ epics thật |
| GĐ-5 Mockup | ✅ 6/6 — dựng bằng chromium thật, hợp đồng trích từ trang đã render |
| GĐ-6 Harness + implement | ✅ 10/10 — `aisdlc run` chạy đợt trên worktree thật, cổng story 6 điều kiện |
| GĐ-7 Kiểm định | ✅ — `aisdlc qa` 10 loại; "chưa cấu hình" ≠ "đạt" |
| GĐ-8 DevSecOps | ✅ — `aisdlc devsecops` + `pre-deploy` |
| GĐ-9 Đầu-cuối | 🔨 đang làm |

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

**386 test xanh.**

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
| 6.4 | 7 guard | `harness/guardrails.py` | ✅ Đủ 7; mỗi guard một lệnh, exit 2 là chặn; từng guard có test chặn thật |
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

**Đầu ra:** `docs/ACCEPTANCE-REPORT.md` — bằng chứng cho từng dòng trên.

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

**GĐ-0, S1** — chạy `claude -p` một task nhỏ, ghi lại cấu trúc `stream-json`, xác định lấy cost/latency ở đâu.
