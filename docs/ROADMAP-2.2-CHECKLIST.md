# AISEF 2.2 — Đầu bài & checklist thi công (NGUỒN SỰ THẬT)

> **BẮT BUỘC — đọc mục này đầu MỖI phiên làm việc trên roadmap:**
> 1. Đọc lại file này TRƯỚC khi làm bất kỳ mục cải tiến nào. Trạng thái đúng là trạng thái checkbox ở đây, **không phải** trí nhớ của model hay memory file.
> 2. Làm xong mục nào → tick checkbox ngay, ghi commit hash vào Nhật ký cuối file, commit file này (commit riêng, message `chore(roadmap): tick <ID>`).
> 3. Làm theo **chế độ LÔ** (mục "Phương thức"). CẤM quay lại kiểu fix–đo–fix–đo vi mô.
> 4. Mục nào ghi "chờ QĐ #n" mà quyết định chưa chốt ở bảng Quyết định → KHÔNG làm mục đó, làm mục khác.

- **Ngày lập:** 2026-11-01 (owner giao việc trong phiên chat, sau khi 2.1.0 phát hành)
- **Nội dung chi tiết từng mục:** xem `docs/IMPROVEMENT-ROADMAP.md` (41 đề xuất review 8 lăng kính + 10 mục từ Harness², mỗi mục có vấn đề/hướng/rủi ro/invariant). File này là bản thi công: thứ tự, định nghĩa DONE, và checklist.
- **Ước lượng tổng:** 11,5–14,5 tuần cho toàn bộ; rút gọn ~8 tuần nếu bỏ phần lớn Đợt 5.

---

## Đầu bài (lời giao việc của owner)

1. Thi công các cải tiến trong `docs/IMPROVEMENT-ROADMAP.md` theo 5 đợt dưới đây.
2. **Bỏ kiểu fix–đo–fix–đo:** mỗi đợt chỉ đo MỘT lần ở cuối đợt (full suite + mutation targeted + records + CI). Trong đợt: design freeze trước → code song song theo lane → merge → một lượt kiểm chứng gộp.
3. Mọi đề xuất giữ nguyên kỷ luật bằng chứng của AISEF — không mục nào được nới lỏng invariant; mục căng invariant phải dừng ở design chờ owner.
4. Mỗi phiên làm việc phải check lại file này (chống quên do giới hạn memory/context).

## Phương thức LÔ (bắt buộc)

- **Trước đợt:** viết design spec ngắn cho cả đợt (mục nào, file nào, acceptance criteria khai báo trước), freeze — không đổi scope giữa đợt.
- **Trong đợt:** code theo lane, mỗi lane một subsystem, worktree riêng nếu song song. Không chạy full suite giữa chừng trừ khi lane chạm kernel và cần smoke cục bộ (chỉ test của module đó).
- **Cuối đợt — MỘT lượt kiểm chứng gộp (không bỏ được, đây là release-gate vật lý của repo):**
  - [ ] mẫu: `ruff` sạch + full suite xanh trên **cây chính** (không phải worktree; suite worktree yếu hơn — nhiều skip)
  - [ ] mẫu: `git status closure-evidence/` sạch sau suite (test có thể ghi đè state-model-results.json → checkout lại, KHÔNG commit)
  - [ ] mẫu: mutation targeted trên các module kernel đã đổi (worker env guard: PATH không có opencode thật + XDG scratch; cây COPY có baseline xanh trước)
  - [ ] mẫu: tái lập các record bị đỏ do kernel đổi (đỏ là CHỦ ĐÍCH của thiết kế record-currency — tái lập, không skip)
  - [ ] mẫu: CI xanh cả 6 chân (ubuntu 3.11–3.14, macOS, Windows; `gh -R nghinh/aisef`; `gh run watch` có thể chết vì network — kiểm lại bằng `gh run view`)
  - [ ] mẫu: tick checkbox + Nhật ký + commit file này
- **Khi lượt đo cuối đợt đỏ:** bisect theo lane (mỗi lane một subsystem), sửa trong lane đó, đo lại MỘT lần. Không mở vòng lặp vi mô toàn cục.

## Quy tắc an toàn vận hành (đúc từ bài học đã trả giá — áp dụng mọi đợt)

- Không commit khi suite/campaign đang chạy trên cây chính.
- Full suite ~33 phút: chạy `nohup` tách rời, thăm bằng vòng `until` ≤600s (tác vụ nền bị giết ~30 phút).
- Cấm `git stash` khi đang fan-out nhiều worktree (stash dùng chung — agent pop mất của nhau).
- `df -h` trước việc nặng; giữ ≥15 GiB trống.
- `python3` (python là alias zsh); zsh: `${=VAR}` để word-split; commit message có backtick → `<<'EOF'` + `git commit -F`.
- Không chạy python ở /tmp (shadow stdlib); dùng scratchpad. /tmp bị macOS dọn ~7 ngày — evidence bền chuyển vào repo sớm.
- Mốc thời gian ghi theo `date` hệ thống, không dùng ETA.
- Run trả tiền: diễn tập offline bằng fake client trước; subagent phải được dặn rõ binary cấm và kiểm DB/log sau.
- README/docs đổi trên release branch làm vỡ release gate — docs đổi trên master.

## Quyết định owner (chốt một lần — cập nhật bảng này khi owner trả lời)

| # | Quyết định | Chặn mục | Trạng thái |
|---|---|---|---|
| 1 | A2: key authenticity để đâu | A2 | **CHỐT:** khoá ký per-run (ephemeral keypair), public half escrow ngoài máy như anchor hiện tại; transparency-log anchor là tuỳ chọn khi có hạ tầng |
| 2 | Bảng giá token theo route | C2, B7, C9 | **CHỐT cơ chế:** giá do operator khai trong settings per-route; bật `max_cost` mà thiếu giá/thiếu token ⇒ fail closed; số liệu route hiện hành lấy lúc Đợt 2 khởi công |
| 3 | Scope confinement | D1, D2, D3 | **CHỐT:** làm đủ D1 + D2 + D3 trong Đợt 4 |
| 4 | B5 acceptance-gate độc lập | B5 | **CHỐT:** CÓ — Đợt 5 |
| 5 | G10 developer-harness/OKL | G10 | **CHỐT:** CÓ — Đợt 5 |
| 6 | Ngân sách run trả tiền Đợt 2 | B1, B7, C7 | **CHỐT:** trần $60 |

Owner chốt 2026-11-01 ("Đồng ý, làm đi") theo mặc định đề xuất. Muốn đảo quyết định nào thì đảo **trước khi đợt liên quan khởi công**. Đợt 1 không phụ thuộc quyết định nào.

**Owner directive 2026-11-04 — duyệt khép Đợt 1 + khởi công Đợt 2** (spec đông cứng: `docs/implementation/v2/ROADMAP-2.2-WAVE-2-SPEC.md`):
- Mutation: duyệt bổ sung kill test đã có vào TARGETS; re-run target bị ảnh hưởng, phân loại KILLED/SURVIVED/**EQUIVALENT**; KHÔNG giảm phạm vi / nới tiêu chí; lưu evidence trước+sau.
- CI: 4 nhóm đỏ (Proc×2, FailClosed, read_set) vào Đợt 2 xử lý gốc; KHÔNG allowlist mới nếu chưa chứng minh không ảnh hưởng correctness; phân biệt lỗi thật/flaky/platform/sealing-chủ-đích; **KHÔNG tuyên bố CI PASS khi job bắt buộc còn đỏ**.
- Thứ tự Đợt 2: **C2 (gate) → B1 → B3+G5 → B7 → C3a/C4/C9**. Trần 2 lượt paid ≤ **$60**. **C2 chưa chứng minh kiểm soát chi phí ⇒ chưa được live paid run.**
- Findings: os.kill(pid,0) Windows lập finding + phân tích tác động trước khi đề xuất sửa kernel; freeze_manifest + Q5-COMPARISON giữ OPEN có phương án evidence; KHÔNG reseal/tag v2.2 nếu chưa phê duyệt riêng.
- Báo cáo cuối Đợt 2: commit SHA, CI, mutation, live PASS/FAIL, verification, USD thật, blocker, QĐ cần owner. KHÔNG tự sang Đợt 3.

---

## ĐỢT 1 — Trung thực + tín hiệu (ước 1–1,5 tuần)

- [x] **A1** — Arm invariant lúc runtime trong `execute()`, bind `registry_digest + mechanism_digest` vào run, `--verify` re-derive so sánh, `require_armed` ở guard nóng (M) — be7b1700 (register_runtime CODE-only: wheel không có tests/validation/docs)
- [x] **F1** — Tách suite theo LOẠI check: record-currency/sealing ra job CI riêng chỉ chạy master + sealed tag (fail-closed, enumerate đủ); branch/PR chạy product suite (M) — 9a3d1377 (sealing_gate.GATED 18 id + test closure 2 chiều + job `sealing` expected-RED trên master)
- [x] **F3** — `skipUnless` theo platform cho ~31 test validation-harness POSIX-only + mỗi skip kèm một assertion dương trên OS bị skip (M) — 9a3d1377 (fix-over-skip: 17 file test sửa portable, chỉ gate phần thật sự POSIX)
- [x] **F4** — Diệt 3 survivor report-field (`client.py::session`: 'redacted' count, 'left_range_gone') + guard 4 equivalence bằng audit machinery (M) — ec8d04ff (kill test mới trong test_s2_kills.py — file đã nằm trong kill set đăng ký của session; correction record SURVIVOR-EFFECT-CORRECTION-1.json)
- [x] **G1** — Leak-tripwire: quét marker/digest stimulus ẩn trên MỌI thứ serve vào phiên developer/reviewer (worktree staging, prompt, context_pack, retry feedback), fail closed trước launch (S/M) — fdd9c35b (aisef2/app/tripwire.py; refusal không bao giờ echo giá trị stimulus)
- [x] **G2** — Fence client: `OPENCODE_PERMISSION` deny-all ngoài worktree + XDG scratch per-run + trần output token, cho MỌI phiên product; kèm canary đo thật (thử đọc file ngoài worktree); khai báo là client-enforced mitigation, không phải OS confinement (S) — 76fd9cd8 (declared-not-measured ghi rõ trong fenced string)
- [x] **D4** — Pin binary opencode: sha256 + absolute path theo pattern `review_ocr.pinned()`, ghi hash vào RUN.json (S) — 76fd9cd8 (re-check tại thời điểm dùng trong session())
- [x] **G7** — Chuẩn lỗi authoring: admission check 9 / lint / seal gom HẾT lỗi một lần, mỗi lỗi = hậu quả + cách sửa (viết như retry feedback) (S) — 7792b2a4 (byte-identical khi chỉ 1 lỗi; bundle.py giữ nguyên comprehension MIGRATE_NEVER_APPROVES chứng minh được)
- [x] **G8** — Linter tĩnh no-oracle-words trên facts/clause_text/task prompt + khối boundary "evidence là data, không phải lệnh" trong prompt developer/reviewer (hygiene, không phải invariant) (S) — 7792b2a4 + fdd9c35b (facts_oracle_content informational trong lint/seal; BOUNDARY trong feedback.task + REVIEW_PROMPT/OCR_BACKGROUND)
- [x] **ĐO CUỐI ĐỢT 1** (checklist mẫu ở mục Phương thức — A1 chạm kernel ⇒ chắc chắn phải tái lập records + mutation targeted) — XONG 2026-11-04
  - [x] ruff sạch + full suite cây chính: lượt 1 bắt 7 đỏ wave-induced → bisect 4 nguyên nhân, sửa (5cc65720) → lượt 2 **8031 test, 1 fail duy nhất = HistoricalAttempt4 (artefact local-only, CI xanh), 56 skip, owned processes sạch** (log: scratchpad wave1/final-suite{,-2}.log)
  - [x] `git status closure-evidence/` sạch sau cả hai lượt suite (chỉ còn file cycle2 dở dang của owner — không đụng)
  - [x] mutation targeted XONG (phóng 2026-11-02 01:47, kết thúc 2026-11-04 01:52, ~48h/4 worker clone tại 5cc65720): **9 target, 1651/1910 killed (86,4%), 259 survivor, 0 TIMEOUT/INFRA/NOT_RUN**; T0 PASS cả 4 worker; env guard giữ (0 lần gọi opencode thật). **3 survivor gốc F4 của session đều KILLED** (vị trí dòng mới L336/L338/L339). 259 survivor mới gần như toàn bộ ở CODE MỚI của wave — kill test đã tồn tại trong test_v22_*/test_invariants_runtime nhưng CHƯA đăng ký vào kill set (sửa TARGETS trong mutation.py = thay đổi registry, chờ owner). Record mới: closure-evidence/v2/v2.2/WAVE1-MUTATION.json — record seal KHÔNG bị ghi đè
  - [x] record bị đỏ do kernel đổi: Classify.test_historical_records_read_as_before vào sealing tier (đỏ-chủ-đích thuộc về job `sealing`; tái lập record P1..V2.0-S2 là quyền owner — KHÔNG tự reseal)
  - [x] CI: 3 lượt (41338480741 @5cc65720 → 41345810672 @b94b53fb → 41352680305 @5ff67a33). Chốt: lint + wheel + **unit windows-3.11 XANH HOÀN TOÀN**; `sealing` ĐỎ-có-tên-riêng đúng thiết kế; 0 hồi quy wave còn lại. Hồi quy Windows 0→11 của lượt 1 (fixture F3 sai tiền đề validator + 2 test v22) sửa hết phía test (79660c8f, 5ff67a33). Còn trên ubuntu/macos: nhóm đỏ CÓ SẴN trước wave, bị 22 đỏ record-currency che tới giờ — `mutation_runner.Proc` ×2 (ubuntu, ổn định), `confine.FailClosed` (flake teardown, nhảy chân), `read_set.ToyRecord` (3.11/3.12/macos, intermittent), `pm8` depth 3.11 (ĐÃ sửa lượt này) — ứng viên Đợt 2, không thuộc scope wave 1
  - [x] tick checkbox + Nhật ký + commit file này

## ĐỢT 2 — Giá trị (ước 1–1,5 tuần) — cần QĐ #2, #6 cho B7/C2/B1

- [ ] **B1** — Canary live PASS: `bundle init --example calc-1-story` trên repo sạch, route attested → `delivery_verdict PASS` + `--verify` VERIFIED + 0 escape; nếu FAIL thì báo cáo nguyên trạng (M) *(QĐ #6)*
- [x] **B3+G5** — `aisef demo`: fake developer xác định + probe thật + journal thật + `--verify` thật, KHÔNG cần credential; bắt buộc kèm ca escape (defect ngoài scope lọt) (S/M) — `aisef2/app/demo.py` + dispatch `aisef/cli/parser.py`. Dùng ĐƯỜNG THẬT: `bundle init --example calc-1-story` → git init → `seal(repo=)` → `approve` mỗi contract → `bundle.load` → `R.execute` (transport loopback, client_exe fake, XDG cô lập) → `verify`. 3 kịch bản thật: **correct** (add=a+b) → PASS/COMMIT/VERIFIED; **caught** (add=a−b, hồi quy trong scope) → FAIL/[RETRY,ROLLBACK]/VERIFIED; **escape G5** (add=`return 5`) → PASS/COMMIT/VERIFIED **nhưng** exec code đã giao: `add(1,1)==5` (≠2) — ranh giới trung thực: kernel chứng minh hợp đồng ĐÃ VIẾT, không chứng minh đúng ngoài đó. Test tests/v2/test_v22_demo.py (2 test, posix, 34s). 126 test CLI xanh, ruff sạch
- [ ] **B7** — Đo cost-of-trust USD/story trên canary + 1 run trả tiền; tách productive vs trust theo công thức E4; công bố cả khi con số xấu (S) *(QĐ #2, #6)*
- [x] **C2** — `Budget.max_cost`: spend() mang 5 lớp `usage.CLASSES`, trần tiền theo bảng giá, fail-closed khi thiếu token; không đặt giá ⇒ hành vi không đổi (M) *(QĐ #2)* — 9d1c1314. **GATE PAID THOẢ MÃN:** proof offline 10/10 (test_v22_max_cost) gồm 2 e2e fake-client (run DỪNG trước story → NOT_REACHED + budget_stop max_cost; cap rộng → PASS). settings.max_cost optional (đòi prices, fail-closed ở load). Budget mutation (Budget.*/_cost mới) để ĐO CUỐI ĐỢT 2
- [x] **C3a** — no_progress → 1 dòng trong retry prompt ("N attempt fail với bằng chứng y hệt — đổi cách tiếp cận"); text thuần từ journal, không authority (S) — c3429f6e (feedback.no_progress_note ghép ở adapters.implement; retry_feedback/context_pack giữ nguyên pin conformance; dòng chỉ hiện khi journal có lặp)
- [ ] **C4** — Chặn attempt no-op (S) — **REVERTED** (commit revert sau 9f0f7dc1). Full suite CI bắt 2 hồi quy mà test cục bộ bỏ sót: (1) **vi phạm invariant `ALL_CONTROL_DECISIONS_JOURNAL_BACKED`** — gate row 'candidate' đặt trước typed-call của stage (static proof đòi gate row theo sau stage call); owner CẤM đổi invariant. (2) phá `context_pack.ThroughTheRun` (skip proof ⇒ mất "changed nothing" feedback). **Phát hiện then chốt:** flow HIỆN CÓ đã skip quality/review(paid)/scan cho no-op (prove ở candidate==base fail ⇒ `failure` set ⇒ các stage sau gated bỏ qua) — C4 gần như vô ích mà lại phá invariant. **Chờ owner:** bỏ hẳn C4 hay thiết kế lại route no-op qua stage machinery đúng chuẩn (không short-circuit trước stage)
- [x] **C9** — Spend của stuck-retry tính vào trần tiền C2 (quyết định retry vẫn thuộc taxonomy) (S) — 2196edbb (thoả bởi thiết kế C2: spend() tổng mọi session log gồm retry; test pin lại, KHÔNG side counter)
- [ ] **Lane M (mutation registry)** — đăng ký kill test v22/invariants đã có vào TARGETS + target mới (tripwire, registry arming, _invariant_problems); re-measure; phân loại KILLED/SURVIVED/EQUIVALENT; evidence trước+sau *(owner item 1)*
- [x] **Lane CI (root-cause)** — root-cause + phân loại 3 nhóm (evidence: closure-evidence/v2/v2.2/CI-REDS-TRIAGE.json), fix test-only, KHÔNG product/allowlist: read_set = **platform** (pathlib pre-3.13 stat rglob root; version-gate; verified 3.12+3.14), Proc×2 = **platform** (Linux subreaper vs macOS launchd; test platform-aware; macOS verified, Linux qua CI), FailClosed = **flaky** (teardown race setsid dưới tải; cleanup signal mọi proven-owned; confine module verified macOS, Linux qua CI); sealing = **đỏ-chủ-đích** giữ nguyên, KHÔNG tính vào "CI PASS" *(owner item 2)*
- [x] **Findings** — os.kill(pid,0) Windows (finding + phân tích, chưa sửa kernel); freeze_manifest V2_007 + Q5-COMPARISON (OPEN, phương án evidence) *(owner item 4)* — closure-evidence/v2/v2.2/FINDINGS.json. FINDING-WIN-OSKILL-001: os.kill(pid,0) trên Windows = TerminateProcess(0) (giết, không dò) ở client.py:46 _is_gone; latent (test range POSIX-gated, aisef run claimed Linux/macOS) nhưng reachable nếu chạy thật trên Windows; remediation (ctypes OpenProcess/GetExitCodeProcess, KHÔNG terminate) đề xuất — chờ owner, kernel frozen. 2 OPEN item có phương án evidence
- [ ] **ĐO CUỐI ĐỢT 2** — ruff + full suite + mutation + CI (KHÔNG tuyên bố PASS khi job bắt buộc đỏ) + USD thật + báo cáo owner (commit/CI/mutation/PASS-FAIL/verification/USD/blocker/QĐ)

## ĐỢT 3 — Adoption / authoring (ước 2–2,5 tuần)

- [ ] **B6a** — `classify_or_reason`: sibling diagnostic cho mỗi probe (class gần nhất, field sai, shape mong đợi, thiếu within_s); `observation_class()` giữ nguyên là gate thuần; diagnostic không bao giờ thành control path (M)
- [ ] **B6b** — Validate tại `seal` (từ chối trước khi ghi) + `explain` hiển thị assertion đã compile (subject, stimulus cụ thể, expected observable, within_s) để approve là review thật (M)
- [ ] **B6c** — `aisef bundle probes [--kind]`: catalog grammar + ví dụ tối thiểu + trạng thái calibration; `--skeleton KIND.CLASS` emit contract mẫu (M)
- [ ] **B6d** — Papercuts: authoring-doc → "chạy seal"; chưa approve → nêu lệnh; "không phải git repo" ≠ "không tồn tại"; `run --check` in readiness client (S)
- [ ] **B4** — `aisef bundle draft REQ.md`: model đề xuất contracts/plan/facts (format authoring) + render ngôn ngữ thường; model không ký gì; seal derive hash; cổng approve người giữ nguyên (L)
- [ ] **G3** — Nâng cấp pin client: hỗ trợ "client = source checkout tại commit X" + preflight kiểm pin/patch trước khi tiêu tiền (M)
- [ ] **G4** — Evidence-as-files: retry evidence (diff attempt trước, failure detail, dòng no_progress) thành file trong worktree, mission chỉ là pointer; truncation-attribution + sàn truncation; tuyệt đối stimulus-free (M)
- [ ] **ĐO CUỐI ĐỢT 3**

## ĐỢT 4 — Kernel / evidence / security (ước 4–5 tuần; 2 lượt tái định chuẩn) — cần QĐ #1, #3

- [ ] **E5** — `_attempt` thành chuỗi Stage có kiểu + `finally` luôn ghi `story/dispose + story/end` (fault không còn làm hỏng cả run); land cùng full suite + mutation re-run (L) *(làm TRƯỚC C1/C5)*
- [ ] **A2** — Keyed chain / signed head (MAC/chữ ký trên run_id + head + anchor + kernel_digest, key ngoài thư mục ghi được) + external anchoring hạng nhất; `--verify --expect-pubkey` (L) *(QĐ #1)*
- [ ] **E1** — Verdict = projection/fold của tập projection đóng; `oracle_problems()` chạy trong verify; shadow trên toàn bộ evidence hiện có trước khi cắt chuyển (M)
- [ ] **E2** — Write-ahead spend reservation qua cửa sổ SIGKILL (A-03): reservation owner-typed lúc request, reconcile lúc result, repair charge max(reservation, stream) (M)
- [ ] **E3** — Tier quan sát OS cho contract exit/signal: controller spawn một-shot subprocess, lấy exit/signal từ waitpid; không bán là đóng forgery in-process (M)
- [ ] **E4** — Digest đoạn session-stream vào `provider/result`; verify check từng segment trước khi re-derive spend; định nghĩa segment cho ca torn-tail (M)
- [ ] **E6** — Một bảng chuyển trạng thái story (pure value) cho cả writer `_story_active` và projection `StoryState.step` (M)
- [ ] **C1** — Grade giữa phiên: stall-cutoff khi `git status` rỗng sau K turn + chấm sớm speculative trên snapshot (không probe cây đang bị ghi) (L) *(sau E5)*
- [ ] **C7** — Attest model xuyên phiên trả tiền: probe attestation xen kẽ, journal `provider/attestation`, drift check phủ cả run; chi phí qua ledger (M)
- [ ] **C8** — `ClientAdapter` 4 method (argv / config_endpoint / parse_stream / identity); OpenCode = adapter đầu; `usage.CLASSES` là contract token (L)
- [ ] **D1** — Confine probe subject + developer-test bằng `confine.wrap()` (worktree writable, còn lại RO, key qua fd) (L) *(QĐ #3)*
- [ ] **D2** — Backend Seatbelt/sandbox-exec cho macOS, nghiệm thu bằng `confine.measure` canary; khai báo best-effort (L) *(QĐ #3)*
- [ ] **D3** — Loopback key-broker: key không vào env phiên; egress allowlist tới endpoint attested; measure assert env không có key (M) *(QĐ #3)*
- [ ] **F2** — Allowlist release sinh từ marker test tự khai + meta-test đối chiếu category; hết vá tay theo version (L)
- [ ] **F5** — Mutation incremental trong CI: chỉ target có module/kill-test closure đổi; tái dùng sealed result (L)
- [ ] **B2** — Corpus ground-truth: cây known-good / defect trong scope / ngoài scope, oracle độc lập đóng băng trước khi đo; báo false-accept/false-reject thật (M)
- [ ] **G6** — `aisef run --resume`: reuse story đã đóng chỉ khi fingerprint (bundle_hash, kernel_digest, route, base) khớp; in `why_not` per story (L)
- [ ] **ĐO GIỮA ĐỢT 4** (sau cụm E5+E1+E2+E6 — kernel core) và **ĐO CUỐI ĐỢT 4**

## ĐỢT 5 — XL / chiến lược (ước 3–4 tuần) — cần QĐ #4, #5

- [ ] **C5** — Story wave song song theo DAG `depends_on` + write-scope; journal append tuần tự hoá (mẫu G9: chạy song song, ghi sổ theo thứ tự + closing identity check) (XL)
- [ ] **B5** — Acceptance-gate độc lập: entrypoint "grade cây/diff này theo bundle đã duyệt" cho PR của agent bất kỳ (XL) *(QĐ #4)*
- [ ] **G10** — Tầng developer-harness owner-duyệt học xuyên story (OKL/ADR-002): lesson bắt buộc {cue, lesson, evidence→journal event}; tripwire G1 chặn rò verdict/stimulus; gate vẫn là probe (L/XL) *(QĐ #5)*
- [ ] **C6** — Reviewer trên route/model thứ hai, attest + ledger riêng; default = same route (M)
- [ ] **C10** — Transcript ví dụ PUBLIC owner-authored per clause trong task()/retry_feedback (yếu hơn & khác stimulus ẩn) (M)
- [ ] **E7** — RunRecord builder duy nhất + Stage enum + tách execute() (thuần refactor, không đổi byte RUN.json) (L)
- [x] ~~**E8** — Executor seam attested~~ — **LOẠI kỳ này** (căng non-goal; chỉ xét lại nếu B5 được duyệt và cần)
- [ ] **ĐO CUỐI ĐỢT 5**

---

## Nhật ký thi công (append-only — mỗi dòng một sự kiện)

| Ngày | Sự kiện | Commit / evidence |
|---|---|---|
| 2026-11-01 | Lập đầu bài + checklist; roadmap chi tiết tại docs/IMPROVEMENT-ROADMAP.md | 99949738 |
| 2026-11-01 | Owner duyệt toàn bộ ("Đồng ý, làm đi") — 6 QĐ chốt theo mặc định. **KHỞI CÔNG ĐỢT 1**: recon đọc code + baseline full suite, sau đó freeze WAVE-1 spec | (commit này) |
| 2026-11-01 | WAVE-1 spec freeze + baseline suite (7981 test, 21 fail đã biết) | 6cc3ba43 |
| 2026-11-01 | Thi công 9 mục Đợt 1 theo lane, 7 commit | be7b1700, 76fd9cd8, fdd9c35b, ec8d04ff, 7792b2a4, 9a3d1377 |
| 2026-11-02 | ĐO CUỐI ĐỢT 1 lượt 1: 7 đỏ wave-induced → bisect 4 nguyên nhân (anchor import adapters; fixture A22 thiếu kernel_digest+invariants; 2 test p5 cần clear cả _RUNTIME_ARMED; Classify historical = record-currency → sealing tier) | 5cc65720 |
| 2026-11-02 | ĐO CUỐI ĐỢT 1 lượt 2 XANH: 8031 test, 1 fail = HistoricalAttempt4 (local-only), 56 skip, owned processes sạch. Push master dd95a762→5cc65720; mutation targeted 9 target/1622 mutant phóng 01:47 trên 4 worker clone | 5cc65720, CI 41338480741 |
| 2026-11-02 | CI lượt 1 lộ Windows 0→11 đỏ (hồi quy wave: fixture F3 + 2 test v22) → sửa test-side 2 nhịp; chốt **unit windows-3.11 XANH**, POSIX chỉ còn đỏ-có-sẵn (Proc×2, FailClosed flake, read_set intermittent); pm8 depth 3.11 sửa xong | 79660c8f, 5ff67a33, CI 41352680305 |
| 2026-11-04 | Mutation targeted XONG (~48h): 9 target / 1651/1910 killed / 259 survivor (code mới, kill test chưa đăng ký) / 0 INFRA; 3 survivor gốc F4 KILLED; record mới v2.2/WAVE1-MUTATION.json. **ĐỢT 1 KHÉP** — chờ owner duyệt báo cáo + quyết 3 việc: đăng ký kill set mới, nhóm đỏ CI có sẵn vào Đợt 2, khởi công Đợt 2 | db922fed |
| 2026-11-04 | CI @db922fed đúng hình: lint+wheel+windows XANH, sealing đỏ-chủ-đích, 3.13 chỉ còn đỏ-có-sẵn (Proc×2, FailClosed), macos bị runner huỷ (hạ tầng). 0 đỏ mới từ commit evidence | run 41698412997 |
| 2026-11-04 | **Owner duyệt khép Đợt 1 + khởi công Đợt 2.** Model đổi sang Opus 4.8. Freeze WAVE-2 spec (7 lane: M mutation, CI, C2 gate, B3+G5, C3a/C4/C9, PAID B1+B7, Findings). C2 là gate paid; trần $60 | d98f2115 |
| 2026-11-04 | CI @30da62a6 (sau revert C4): ubuntu 3.11–3.14 + windows 3.11 + lint + wheel XANH; sealing đỏ-chủ-đích; còn **1 đỏ macos-3.12**: `test_one_release_budget_per_run` — runner refuse ĐÚNG bằng `RESIDUAL_OWNERSHIP_UNKNOWN` (macOS không chứng minh được ownership của helper rejoin-group dưới tải) thay vì "range would not empty" kỳ vọng; product đúng, kỳ vọng test quá hẹp cho macOS + phụ thuộc tải → Lane-CI round 3 | run 41768704712 |
| 2026-11-04 | **B3+G5 `aisef demo` XONG** (offline, no-credential). Đường thật init→seal→approve→load→execute→verify trên example đóng gói; 3 verdict thật (PASS/FAIL/escape-PASS) + exec code escape chứng minh add(1,1)=5. Test xanh, ruff sạch, 126 test CLI xanh | (commit này) |
