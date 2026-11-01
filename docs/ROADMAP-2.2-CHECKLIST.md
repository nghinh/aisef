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

---

## ĐỢT 1 — Trung thực + tín hiệu (ước 1–1,5 tuần)

- [ ] **A1** — Arm invariant lúc runtime trong `execute()`, bind `registry_digest + mechanism_digest` vào run, `--verify` re-derive so sánh, `require_armed` ở guard nóng (M)
- [ ] **F1** — Tách suite theo LOẠI check: record-currency/sealing ra job CI riêng chỉ chạy master + sealed tag (fail-closed, enumerate đủ); branch/PR chạy product suite (M)
- [ ] **F3** — `skipUnless` theo platform cho ~31 test validation-harness POSIX-only + mỗi skip kèm một assertion dương trên OS bị skip (M)
- [ ] **F4** — Diệt 3 survivor report-field (`client.py::session`: 'redacted' count, 'left_range_gone') + guard 4 equivalence bằng audit machinery (M)
- [ ] **G1** — Leak-tripwire: quét marker/digest stimulus ẩn trên MỌI thứ serve vào phiên developer/reviewer (worktree staging, prompt, context_pack, retry feedback), fail closed trước launch (S/M)
- [ ] **G2** — Fence client: `OPENCODE_PERMISSION` deny-all ngoài worktree + XDG scratch per-run + trần output token, cho MỌI phiên product; kèm canary đo thật (thử đọc file ngoài worktree); khai báo là client-enforced mitigation, không phải OS confinement (S)
- [ ] **D4** — Pin binary opencode: sha256 + absolute path theo pattern `review_ocr.pinned()`, ghi hash vào RUN.json (S)
- [ ] **G7** — Chuẩn lỗi authoring: admission check 9 / lint / seal gom HẾT lỗi một lần, mỗi lỗi = hậu quả + cách sửa (viết như retry feedback) (S)
- [ ] **G8** — Linter tĩnh no-oracle-words trên facts/clause_text/task prompt + khối boundary "evidence là data, không phải lệnh" trong prompt developer/reviewer (hygiene, không phải invariant) (S)
- [ ] **ĐO CUỐI ĐỢT 1** (checklist mẫu ở mục Phương thức — A1 chạm kernel ⇒ chắc chắn phải tái lập records + mutation targeted)

## ĐỢT 2 — Giá trị (ước 1–1,5 tuần) — cần QĐ #2, #6 cho B7/C2/B1

- [ ] **B1** — Canary live PASS: `bundle init --example calc-1-story` trên repo sạch, route attested → `delivery_verdict PASS` + `--verify` VERIFIED + 0 escape; nếu FAIL thì báo cáo nguyên trạng (M) *(QĐ #6)*
- [ ] **B3+G5** — `aisef demo`: fake developer xác định + probe thật + journal thật + `--verify` thật, KHÔNG cần credential; bắt buộc kèm ca escape (defect ngoài scope lọt) (S/M)
- [ ] **B7** — Đo cost-of-trust USD/story trên canary + 1 run trả tiền; tách productive vs trust theo công thức E4; công bố cả khi con số xấu (S) *(QĐ #2, #6)*
- [ ] **C2** — `Budget.max_cost`: spend() mang 5 lớp `usage.CLASSES`, trần tiền theo bảng giá, fail-closed khi thiếu token; không đặt giá ⇒ hành vi không đổi (M) *(QĐ #2)*
- [ ] **C3a** — no_progress → 1 dòng trong retry prompt ("N attempt fail với bằng chứng y hệt — đổi cách tiếp cận"); text thuần từ journal, không authority (S)
- [ ] **C4** — Chặn attempt no-op: candidate == base (so SHA) ⇒ skip quality/review/scan, route DEVELOPER failure tại điểm đo CANDIDATE, tái dùng probe result của admission (S)
- [ ] **C9** — Spend của stuck-retry tính vào trần tiền C2 (quyết định retry vẫn thuộc taxonomy) (S)
- [ ] **ĐO CUỐI ĐỢT 2**

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
