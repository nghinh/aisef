# ADR-004 — Cải tiến liên tục theo bằng chứng ở cấp epic (đối chiếu Harness-of-Harness)

**Trạng thái:** PROPOSED, trừ **R2 · R5 · R6 · R7 = ACCEPTED** (2026-09-05, số đo §6: B0 và B4 hồi cứu trên evidence thật của e9 và `par`, 0 agent). **R1 · R3 · R4 · R8 · R9** hiện thực, unit xanh, chờ đo trên agent thật (§6). Ngày 2026-09-06.
**Nguồn đối chiếu:** paper *Harness-of-Harness: Multi-Day Autonomous Software Development with Continual Improvement* (arXiv 2609.01481v1, Shanghai AI Lab) và repo `Flesymeb/HarnessOfHarness` — repo tại thời điểm đọc chỉ có README + tài sản trình diễn (58 commit, MIT, "HoH-lite sẽ công bố"), **không có mã**; mọi cơ chế dưới đây lấy từ paper.
**Ràng buộc giữ nguyên:** sáu nhóm harness hiện có, evidence-first, reviewer ≠ developer, bảo đảm phía harness, worktree cách ly, cổng người, CLI gọi-một-lần/không daemon, không tin client. Không dùng HoH làm runtime. Không tự sửa framework: mọi thay đổi vẫn qua test, benchmark, ADR/evidence và cổng người/phát hành.

Ghi chú tên module: trong kho này bằng chứng nằm ở `harness/observe.py` (EvidenceStore, không có `control/evidence.py`), ngữ cảnh prompt dựng ở `phases/implement.py::build_context` (không có `harness/context.py`). Các yêu cầu dưới đây trỏ đúng tệp thật.

---

## 1. HoH nói gì, và V2 đang có gì

### 1.1 Cốt lõi của HoH (từ paper)

Một vòng = ba vai **Planner** (đọc spec 𝒮 + evidence ℰ₍t−1₎ + artifact A₍t−1₎ chỉ đọc → tài liệu phát triển D_t), **Developer** (A₍t−1₎ + D_t → ứng viên A_t), **QA Tester** (A_t **đóng băng, chỉ đọc** + Runtime tất định → ℰ_t). Trạng thái chuyển qua vòng: (A₍t−1₎, ℰ₍t−1₎) → (A_t, ℰ_t). Evidence ghi *verified behavior*, *gaps* (chưa đạt, hồi quy, thiếu bằng chứng), *reopened issues*. Planner sinh **Update Targets** (bounded, locally complete), **Preservation** (hành vi đã xác minh phải giữ) và **Validation Requirements** (tiêu chí kiểm được, black-box + white-box). Quy tắc chấp nhận: *"A criterion is verified only when candidate-bound records support the required behavior"*. Ngữ cảnh: **progressive disclosure** — chỉ mục ngắn có phân loại, chi tiết nạp khi cần. Kết quả: GameCraft-Bench 49,58 → 71,52 (HoH@3); ablation: bỏ plan update −8,13, bỏ evidence feedback −6,28, bỏ warm-start −7,85 (và tốn token hơn). Fusepoint 70 vòng: 81 issue, 65 đóng, **17 reopened**. Paper **không** có điều kiện dừng, không có schema evidence/issue, không nêu SHA/snapshot cụ thể, không có cổng cỡ task theo số đo.

### 1.2 V2 đã có (tái sử dụng được)

| Khái niệm HoH | V2 hiện có | Mức |
|---|---|---|
| Ba vai, tách quyền đọc/ghi | developer / reviewer / security mỗi vai một **phiên mới** (`harness/routing.py`), reviewer không ghi (snapshot + hoàn nguyên, `implement.py::_revert_reviewer_writes`), guard phía harness | ✅ mạnh hơn HoH (guard, không chỉ quy ước) |
| Evidence candidate-bound | `harness/observe.py`: 8 loại sự kiện theo story, `qa:<kind>`, `mockup_map`, `handoff`; `control/gate.py::evaluate` đọc evidence, không tin lời agent; `Outcome` sáu kết cục | ✅ ở **cấp story**; chưa có ở cấp hành vi/epic |
| Frozen candidate | worktree + `changed_files(base_ref)`; reviewer bất biến | ◐ **không có SHA**: thứ tự journal hiện là `changes.detected → verification.completed → review.completed → commit.created → merge.completed` — ứng viên được commit **sau** khi kiểm; bằng chứng không gắn vào một commit |
| Vòng lặp evidence → re-plan | lượt thử trong story (`run.max_retries`, feedback "Lượt trước chưa đạt"), bế tắc kế hoạch do reviewer kiểm chứng → trả về người; `aisdlc change FR-x` → `STORY-CH-nn` | ◐ chỉ **trong** story hoặc bằng tay; **không có vòng epic** QA → evidence → story sửa → kiểm lại |
| Preservation / regression | `control/impact.py` (tệp đổi → module/test ảnh hưởng), `tdd.red_before_green`, `qa:test-delta` cho reviewer | ◐ có "bề mặt hồi quy" cho reviewer, **không** có danh sách hành vi phải giữ và không đo được "đã đúng rồi lại hỏng" |
| Trạng thái hành vi VERIFIED/GAP/REOPENED | `Outcome` cho từng phép kiểm; `control/acceptance.py` nối `AC-<story>-<i>` ↔ tên test | ✗ không có sổ hành vi theo thời gian |
| Cổng cỡ task | `story.max_acceptance_criteria`, `max_write_scope_paths`, `max_screen_states` (P2-12) + **`story.max_complexity`** (R5: `control/complexity.py`, hiệu chuẩn tự ghi `complexity.json`) | ✅ năm chiều, có gợi ý chẻ tất định và cảnh báo lệch ngưỡng ở `doctor` |
| Progressive disclosure | `build_context` chọn slot theo story (handoff ghi slot + số ký tự); `aisdlc doc` nạp tài liệu khi cần | ◐ chưa có chỉ mục evidence dự án; báo cáo nghiệm thu là trang tĩnh |
| Metrics | chi phí, lượt, attempts, TCCN có test, map mockup | ✗ không có tăng trưởng năng lực đã xác minh, hồi quy, gap đã đóng, cải thiện biên |
| Runtime tất định: schema + retry | `skill_scan` kiểm JSON; reviewer trả văn bản có thẻ `[chặn]`/`[bế tắc]` (lỗi 16 vừa sửa) | ◐ chưa có schema bắt buộc + retry cho reviewer/security |

### 1.3 Gap chính (điều HoH chứng minh mà V2 chưa có)

1. **Không có vòng cải tiến cấp epic.** Khi epic "xong", V2 dừng; hồi quy do story sau gây cho story trước chỉ lộ ở `qa`/`pre-deploy` và không tự sinh việc sửa. Ablation của HoH cho thấy chính vòng evidence→plan là nguồn tăng (−6 đến −8 điểm khi bỏ).
2. **Bằng chứng không gắn commit.** Không có "candidate SHA" thì không nói được "bằng chứng này thuộc bản nào", và không có khái niệm *stale*.
3. **Không có sổ hành vi.** Không phân biệt được "chưa từng đạt" với "đã đạt rồi hỏng" — con số 17/81 reopened của Fusepoint là thứ V2 không đo nổi.
4. **Preservation không phải hợp đồng.** Developer lượt sau không được bảo "những hành vi này phải còn"; reviewer chỉ có bề mặt hồi quy theo tệp.
5. ~~**Cỡ story một chiều.**~~ Đo hôm nay: story 11–18 trạng thái chạm `max_turns`; nhưng story 0 màn hình 14 tệp cũng 61 lượt/16 lượt developer (01-01). Cần điểm tổng hợp có hiệu chuẩn. — **đã đóng bằng R5**, số đo §6.

---

## 2. Yêu cầu nâng cấp

Ký hiệu: **P0** = nền tảng, làm trước và đo; **P1** = tạo giá trị đo được sau P0; **P2** = chỉ khi P0/P1 chứng minh. Mỗi mục: rationale · module ảnh hưởng · tiêu chí chấp nhận (AC).

### P0

**R1 — Frozen Candidate SHA.**
*Rationale:* HoH đóng băng A_t khi thu evidence; V2 commit sau khi kiểm nên evidence không trỏ được vào một bản. Không có SHA thì "stale" không định nghĩa được.
*Module:* `control/journal.py` (đổi thứ tự: `commit.created` **trước** `verification.completed`; thêm bước `candidate.frozen` mang SHA), `phases/implement.py::run_attempt` (commit worktree ngay khi phiên developer kết thúc, ghi `candidate_sha`; mọi `tool_run`/`agent_run`/`mockup_map` sau đó mang `detail.candidate`), `harness/observe.py` (trường `candidate` trong `Event.detail`, `Evidence.for_candidate(sha)`), `control/gate.py` (mục mới "bằng chứng đúng candidate": mọi phép kiểm phải có `candidate == sha`; khác → UNRUNNABLE "stale"), `phases/qa.py`/`deploy.py` (QA cấp dự án ghi `candidate = HEAD` của main), reviewer/security (`implement.py`): sau phiên, `git rev-parse HEAD` của worktree phải bằng SHA, khác → lượt rà soát không tính.
*AC:* (a) unit: evidence ghi ở SHA khác → cổng ✗ "stale", cùng SHA → ✅; (b) phép hợp quy **C8**: sửa một tệp trong worktree *sau* khi test đã chạy → cổng story trượt với lý do stale, không phải "test đỏ"; (c) `ACCEPTANCE-REPORT` in SHA candidate của từng story; (d) không tăng số lượt/chi phí trên dogfood `par` (mốc 3/3, ≤ 2×$3,14).

**R2 — Sổ hành vi (ledger) với VERIFIED / GAP / REOPENED.**
*Rationale:* HoH ghi verified/gaps/reopened; V2 chỉ có kết cục theo phép kiểm. Sổ hành vi là thứ để đo hồi quy và cải tiến.
*Module:* `harness/observe.py` thêm loại sự kiện `BEHAVIOR` (`{id, status, candidate, source, prev}`); mới `control/ledger.py` (**phép chiếu** từ evidence hiện có, không phải kho mới): id hành vi = `AC-<story>-<i>` (qua `control/acceptance.py`), `FR-x`/`NFR-x` (qua `covers`), `qa:<kind>`, `mockup:<screen>`; trạng thái suy bằng code: test id xanh ở candidate → VERIFIED; đỏ/thiếu/unrunnable → GAP; VERIFIED trước đó rồi GAP ở candidate sau → **REOPENED** (kèm `regressed_by = story/candidate`); tệp `_bmad-output/ledger.json` + lịch sử `history[]` mỗi hành vi; `phases/report.py` đọc ledger.
*AC:* (a) unit: chuỗi evidence xanh → đỏ → xanh cho cùng AC sinh VERIFIED → REOPENED → VERIFIED với `regressed_by` đúng; (b) chạy lại trên evidence thật của e9 hôm nay (không cần agent): ledger tái dựng được lịch sử 01-04/01-05 và đếm được số REOPENED ≥ 0 với nguồn cụ thể; (c) không có hành vi nào VERIFIED mà không có `candidate`; (d) `aisdlc report` có cột trạng thái hành vi.

**R3 — Vòng cải tiến epic có giới hạn (`aisdlc improve --epic E --max-loops N`).**
*Rationale:* đây là cơ chế HoH chứng minh tạo gain; nhưng HoH không có điều kiện dừng — V2 phải có, bằng code.
*Module:* mới `phases/improve.py` **ghép** từ thứ có sẵn: `qa.run_suite` (thu evidence cấp dự án) → `ledger` (GAP/REOPENED thuộc epic) → **sinh story sửa bằng code** (`control/change.py` mở rộng: `STORY-RP-nn` trong `EPIC-RP-<E>`; mỗi story sửa = một hành vi GAP/REOPENED: acceptance = chính hành vi ấy, `write_scope` = tệp của story gốc + `verification_paths`, `verification_contract` = nguồn của hành vi, `preservation` = R4) → `run.run_epic` (phiên mới, worktree, cổng, reviewer — **không đổi**) → QA lại → ledger → vòng sau. Điều kiện dừng bằng code: (1) không còn GAP/REOPENED thuộc epic; (2) đủ `improve.max_loops`; (3) cải thiện biên ≤ 0 trong `improve.flat_loops` vòng liên tiếp (Δverified − Δreopened); (4) vượt `improve.cost_cap_usd`; (5) story sửa bị bế tắc kế hoạch → dừng, trả người. Mỗi vòng ghi `LOOP-REPORT-<n>.md` và cần cổng người `improve` trước vòng 2 trừ khi `--auto` (vẫn bị chặn bởi 1–5).
*AC:* (a) unit với client giả: 2 GAP → vòng 1 sửa 1, vòng 2 sửa 1, vòng 3 dừng vì "không còn gap"; flat-loops dừng đúng; cost cap dừng đúng; (b) bất biến: mọi story sửa chạy qua `run_epic` (worktree, cổng, reviewer khác developer) — kiểm bằng evidence `handoff`; (c) benchmark B1 (§5) trên e9 EPIC-01.

**R4 — Preservation Constraints, Update Targets, Validation Requirements trong gói bàn giao.**
*Rationale:* HoH đưa ba thứ này vào D_t; V2 chỉ có tiêu chí story + luật kiến trúc + impact theo tệp.
*Module:* `phases/implement.py::build_context` thêm slot `preservation` (nguồn `ledger`): hành vi VERIFIED có tệp giao với `effective_write_scope` của story hoặc nằm trong `impact.builtin(...)` của thay đổi trước; slot `validation` = test id / `qa:<kind>` / màn hình phải xanh ở candidate; `SLOT_SOURCE` + `handoff` ghi hai slot; reviewer và security nhận cùng slot (không nhận lời developer — bất biến ADR-003 #9); `control/gate.py` thêm mục "bảo toàn": mọi hành vi trong `preservation` vẫn VERIFIED ở candidate, không thì FAILED và ledger ghi REOPENED.
*AC:* (a) unit: story chạm tệp của hành vi VERIFIED → slot có đúng hành vi đó, kèm test id; (b) mutation test có chủ đích trên `par`: story sửa làm đỏ test của story trước → cổng "bảo toàn" ✗ + ledger REOPENED `regressed_by` đúng story; (c) prompt_chars tăng ≤ 15 % (đo bằng `handoff`) với cùng kết cục cổng trên dogfood.

**R5 — Story Complexity Gate v2 (trước coding, có hiệu chuẩn).**
*Rationale:* P2-12 chỉ đo trạng thái màn hình; số đo hôm nay còn cho thấy scope 14 tệp và 7 tiêu chí cũng làm story dài. HoH không có cổng này (chỉ "bounded, locally complete" theo phán đoán planner) — V2 làm bằng code.
*Module:* `control/preflight.py::story_size_defect` → `control/complexity.py`: điểm = trạng thái màn hình (đã có) + tiêu chí + tệp trong scope + số hành vi VERIFIED bị chạm (ledger) + fan-in phụ thuộc; ngưỡng `story.max_complexity`; **bảng hiệu chuẩn tự ghi** `_bmad-output/complexity.json`: điểm dự đoán ↔ lượt developer lượt đầu / attempts thật (từ evidence) — `doctor` cảnh báo khi ngưỡng lệch dữ liệu; gợi ý chẻ tất định (theo màn hình/trạng thái, hoặc theo cụm tiêu chí) đưa vào `stories.gate.json` (memo epics đã có).
*AC:* (a) hồi cứu trên 23 story thật (e9 18 + par 5): điểm dự đoán tương quan dương với lượt developer lượt đầu (Spearman ≥ 0,5) và tách được 01-04/01-05 khỏi 01-03/par; (b) unit: story vượt ngưỡng bị chặn ở cổng `stories` **và** ở `run`; story đã xong bỏ qua; (c) hiệu chuẩn cập nhật sau mỗi story xong.

### P1

**R6 — Progressive disclosure cho trạng thái/evidence dự án.**
*Rationale:* HoH: chỉ mục ngắn có phân loại, chi tiết khi cần. V2 nạp story contract + kiến trúc + mockup + impact; chưa có chỉ mục evidence và sẽ tràn nếu R2/R4 đổ cả lịch sử vào prompt.
*Module:* `control/ledger.py::index()` sinh `_bmad-output/INDEX.md` (≤ 1 dòng/story: trạng thái, candidate, VERIFIED/GAP/REOPENED, đường dẫn evidence); `build_context` chỉ nạp lát cắt epic của chỉ mục + `preservation` của story; CLI `aisdlc evidence <story|behavior-id>` để agent tra khi cần (ghi `note:evidence_lookup` như `doc_lookup`); trần ký tự cho slot mới.
*AC:* (a) prompt_chars developer không vượt +15 % so với hôm nay trên `par` và e9 01-05; (b) unit: chỉ mục ≤ N dòng, tra một hành vi trả đúng lịch sử; (c) cổng giữ nguyên kết cục trên dogfood.

**R7 — Metrics cải tiến liên tục.**
*Rationale:* không đo thì không biết vòng lặp có tạo gain hay chỉ đốt tiền (HoH đo bằng benchmark điểm; V2 cần metric nội tại).
*Module:* `control/ledger.py` snapshot mỗi vòng/mỗi story xong; `phases/report.py` thêm: *verified capability growth* (số hành vi VERIFIED duy nhất theo thời gian), *reopened regressions* (số và tỷ lệ trên hành vi VERIFIED), *resolved gaps*, *marginal improvement per loop* = (ΔVERIFIED − ΔREOPENED) / $ vòng; `LOOP-REPORT` in bảng này.
*AC:* (a) unit từ ledger giả; (b) chạy trên evidence e9 thật hôm nay cho ra bảng có số; (c) R3 dùng đúng metric này làm điều kiện dừng.

**R8 — Schema bắt buộc + retry cho đầu ra rà soát.**
*Rationale:* HoH "outputs that violate the required schema trigger a retry"; lỗi 16 hôm nay cho thấy văn bản tự do của reviewer mất thông tin.
*Module:* `phases/implement.py::review_story/security_review`: prompt đòi khối JSON `{"verdict": "pass|block|stuck", "findings": [{"tag","file","line","why","behavior_id"}]}` bên cạnh văn bản; parser (như `skill_scan.parse_verdicts`); thiếu/sai schema → retry **một** lần rồi mới "rà soát không chạy được"; `persist_verdict` giữ nguyên văn (đã có).
*AC:* unit: đầu ra thiếu JSON → retry đúng 1 lần; JSON có `behavior_id` → ledger ghi GAP với nguồn `reviewer`; hồi quy trên `par`: số lượt rà soát không đổi.

**R9 — Baseline trước khi sửa (shift-left bằng harness, không bằng lời dặn).**
*Rationale:* HoH bảo developer "establish a baseline before editing"; V2 đã có `tdd.red_before_green` cho test mới. Bổ sung: harness chạy bộ test **trước** phiên developer (ở candidate cha) và ghi `baseline` test ids; sau phiên so với test ids ở candidate → hồi quy trong lượt lộ ngay, vào feedback lượt sau.
*Module:* `phases/implement.py::run_attempt` (một `tool_run test` với `detail.baseline=True` trước khi gọi model), `harness/testlog.py` (đã có test ids), `control/gate.py` (mục "không làm đỏ test có sẵn" — tách khỏi "test").
*AC:* unit: baseline xanh 10 test, sau lượt 9 xanh + 1 đỏ → cổng nêu đúng tên test hồi quy; chi phí thêm = một lần chạy test.

### P2

**R10 — Planner agent cho story sửa** (chỉ khi R3 đo được gain nhưng story sinh bằng code quá thô): agent viết lại tiêu đề/tiêu chí story sửa từ gap + preservation, vẫn qua cổng `stories` và cổng cỡ.
**R11 — Vòng cấp dự án nhiều epic** (T vòng qua nhiều epic) — sau khi R3 ổn trên một epic.
**R12 — Xuất issue table** (GitHub Issues/CSV) từ ledger — tiện theo dõi, không ảnh hưởng cổng.
**R13 — Lượt kiểm-lại trên ứng viên đã đóng băng** (`aisdlc run --story S --verify-only`) — **hiện thực 2026-09-06, unit xanh trên client giả, chưa đo agent thật (§6)**: không mở phiên developer; ứng viên = HEAD nhánh story; chạy lại đúng các phép kiểm có bằng chứng ✗/thiếu ở ứng viên ấy (rà soát/bảo mật đã ✅ ở cùng SHA thì giữ, theo luật stale của R1). Cần vì: e9 STORY-01-07 2026-09-06 trượt lượt 3 chỉ vì e2e nhạy tải máy, ứng viên `a60612e` đo lại 10/10 xanh (§6). Không nới cổng: vẫn chấm đủ, chỉ không trả tiền cho việc dựng lại mã đã có.

---

## 3. Không áp dụng (và vì sao)

| Ý tưởng HoH | Không áp dụng vì |
|---|---|
| HoH/HoH-lite làm runtime | repo chưa có mã; và V2 đã có harness mạnh hơn ở guard/cổng — chỉ hấp thụ pattern |
| Vòng lặp không có điều kiện dừng (T = 70) | vi phạm kỷ luật ngân sách; R3 bắt buộc dừng bằng code |
| Planner LLM tự chọn scope mỗi vòng | "cần đảm bảo → viết code": story sửa sinh tất định từ gap; agent chỉ vào ở R10 sau khi đo |
| QA Tester LLM là thẩm quyền chấp nhận | V2 chấp nhận bằng máy (test id, qa kind, mockup map) + reviewer độc lập; QA agent chỉ là *nguồn evidence thêm*, không thay cổng |
| Warm-start trong cùng phiên / bộ nhớ dài | phá fresh-session per story; V2 warm-start bằng git (artifact) + ledger (evidence) là đủ và kiểm được |
| Developer self-test làm tiêu chí "sẵn sàng" | lời developer không phải bằng chứng; baseline làm bằng harness (R9) |
| Module bộ nhớ riêng | progressive disclosure bằng chỉ mục + tra cứu (R6), đúng như HoH cũng chọn |
| Framework tự sửa từ evidence | mọi thay đổi framework vẫn qua test/benchmark/ADR/cổng người; ledger chỉ sửa **dự án**, không sửa harness |

---

## 4. ADR / contract / schema cần thêm hoặc sửa

- **ADR-004** (tệp này) → ACCEPTED từng mục khi có số đo §5.
- **ADR-003** sửa: bảng slot bàn giao thêm `preservation`, `validation`, `index` với nguồn `ledger`; bất biến #9 mở rộng: reviewer nhận `preservation` từ ledger, không từ developer.
- **Schema `ledger.json`**: `{"version":1, "behaviors": {"<id>": {"kind":"ac|fr|nfr|qa|mockup", "status":"verified|gap|reopened", "candidate":"<sha>", "since":"<story>#<attempt>|loop-n", "source":{"test_id"|"qa_kind"|"screen"|"reviewer"}, "history":[{"at","status","candidate","story","source"}]}}, "loops":[{"n","at","verified","gap","reopened","cost_usd"}]}`.
- **Evidence Event**: `detail.candidate` bắt buộc cho `tool_run test/qa:*`, `mockup_map`, `agent_run` vai review/security; loại mới `behavior`.
- **Journal**: thứ tự bước mới `attempt.started → worktree.created → status.running → changes.detected → candidate.frozen(sha) → verification.completed → review.completed → merge.completed → attempt.committed`; `commit.created` trở thành `candidate.frozen`.
- **`stories.index.json`**: story thêm `repair_of` (hành vi), `loop`, `preservation` (danh sách id); waves cho `EPIC-RP-<E>`.
- **Config**: `improve.max_loops` (3), `improve.flat_loops` (2), `improve.cost_cap_usd`, `story.max_complexity`, `context.max_preservation_chars`.
- **CLI**: `aisdlc improve --epic E [--max-loops N] [--auto]`, `aisdlc evidence <id>`, `aisdlc report` mở rộng; `aisdlc run --story S --verify-only [--client c]` (R13).
- **Cổng người mới `improve`** trong `control/approvals.py` (giữa `readiness` và `pre-deploy`): duyệt tiếp tục vòng ≥ 2.
- **Hợp quy**: phép **C8** (stale candidate) vào `docs/CONFORMANCE.md`.

---

## 5. Test và benchmark để chứng minh giá trị so với baseline

Baseline hôm nay (đã có số): e9 EPIC-01 — 01-04 8 lượt/$79,67; 01-05 xong sau sửa kế hoạch, tổng ≈ $51; số hồi quy **không đo được** (không có ledger); dogfood `par` 3/3, $5,79; prompt_chars developer ≈ 13,5k (off) / 22,4k (inline).

| Mã | Nâng cấp | Cách đo | Đạt khi |
|---|---|---|---|
| B0 | R2 hồi cứu | Chạy `ledger` trên evidence e9 + par hiện có (0 agent) | Tái dựng được lịch sử VERIFIED/GAP/REOPENED của 01-04, 01-05, 01-06 với nguồn; đếm được REOPENED thật |
| B1 | R3 vòng epic | e9 EPIC-01 sau khi 7/7: `improve --max-loops 3` so với không chạy | ΔVERIFIED > 0 hoặc REOPENED → 0 với chi phí ≤ 1 story trung bình/vòng; dừng đúng điều kiện; mọi story sửa có `handoff` reviewer≠developer |
| B2 | R1 SHA | unit + hợp quy C8 trên Claude và OpenCode | C8 ✅ hai cột; dogfood par không tăng lượt |
| B3 | R4 bảo toàn | mutation có chủ đích trên `par` (story sửa làm đỏ test story trước) | cổng "bảo toàn" ✗, ledger REOPENED `regressed_by` đúng; không có ✗ oan trên chạy sạch |
| B4 | R5 hiệu chuẩn | hồi cứu 23 story thật + dogfood | Spearman(điểm, lượt developer lượt đầu) ≥ 0,5; 0 story ≤ ngưỡng chạm `max_turns` ở par |
| B5 | R6 ngữ cảnh | `handoff` prompt_chars trước/sau trên par + e9 01-05 | ≤ +15 %, cổng cùng kết cục |
| B6 | R7 metrics | ledger e9 thật | bảng growth / reopened / resolved / marginal có số, khớp tay đếm |
| B7 | R8 schema | unit + par | retry đúng 1 lần; số lượt rà soát không đổi |
| B8 | R9 baseline | unit + par | hồi quy trong lượt được gọi tên; +1 lần chạy test/lượt |

Thứ tự làm: R1 → R2 (B0) → R4 → R3 (B1) → R5 (B4) → R6/R7 → R8/R9 → P2. Mỗi bước một ADR-004 §6 "số đo" trước khi bước sau.

## 6. Số đo (điền khi hiện thực)

**R13 — Lượt kiểm-lại trên ứng viên đã đóng băng (`aisdlc run --story S --verify-only`): hiện thực 2026-09-06, unit xanh trên client giả, chưa đo agent thật.**

* Đường đi: `run.run_verify_only` → `run_epic(verify_only=True)` với kế hoạch thu về **một đợt một story** → `_run_wave` tạo lại worktree từ nhánh story mà **không** mang nhánh chính vào (`WorktreeManager.create(refresh=False)` — một commit merge là một bản mới, mọi bằng chứng cũ thành stale) → `implement.verify_only` (cùng chữ ký `implement_story`, gọi thay thế) → merge, `done`, `attempt.committed`, dọn worktree **cùng mã** với lượt thường. Không có đường riêng để lệch.
* `implement.verify_candidate(reuse=…)`: nửa sau của `run_attempt` (đóng băng xong → test/lint → `qa:*` → mockup → rà soát → bảo mật → cổng → `gate:verdict`) tách ra; `run_attempt` gọi với `reuse=False` (chạy đủ như trước), lượt kiểm-lại gọi `reuse=True`. Luật giữ/chạy: test · lint · `qa:fake-tests` · `qa:<kind>` · `mockup:<screen>` **giữ** khi bằng chứng *mới nhất* của phép ấy mang đúng SHA và xanh thật (không `skipped`, không `unrunnable` — hai thứ ấy chạy lại rẻ và có thể đã đổi); rà soát/bảo mật **giữ** khi có `agent_run <story>-review|-security` **và** `tool_run review|security` cùng SHA — kể cả kết luận chặn: người rà soát đã nói về đúng bản này, hỏi lại là trả tiền cho cùng câu trả lời, muốn qua thì phải đổi mã, tức một lượt developer. Mốc là `tool_run review` chứ không phải `note review:verdict`: bản ghi ấy là đúng đầu vào cổng đã dùng và có cả khi model không trả JSON (client giả, nhật ký trước R8).
* Bổ sung 2026-09-06 (ADR-005 V3): `test:nop` đi cùng luật giữ/chạy — giữ khi có kết quả thật ở SHA (kể cả "story không thêm/sửa tệp test"), chạy lại khi thiếu, không chạy được hay tắt bởi cấu hình; `kept` của `note verify-only` có thêm tên này.
* Bằng chứng: `candidate.frozen` mang `data.verify_only=True` (không có phiên developer trước nó); `note verify-only` `{reran, kept, attempt, main_ahead}` — `main_ahead` = SHA nhánh chính khi nó đã tiến lên sau ứng viên (vẫn chấm ứng viên, vì đó là bản được chấm; merge cuối lượt gặp phần mới). `Attempt.verify_only` → `quality_attempts` không đếm, `StoryRecord.attempts` không tăng, không ghi hiệu chuẩn R5, `run.max_retries` nguyên vẹn cho lượt developer sau.
* Từ chối bằng code: không có nhánh `story/<id>` hoặc chưa có `candidate.frozen` ("chưa có ứng viên để kiểm lại"); story `done`; `--verify-only` không có `--story`; `--no-isolate`.
* **Số đo trên client giả** (`tests/test_run.py::TestVerifyOnly` 6 phép + `tests/test_cli.py` 2 phép; "e2e nhạy tải" = lệnh `sit` đọc tệp cờ ngoài kho): story trượt lượt 1 chỉ vì `qa:sit` ✗ → kiểm lại chạy lại **đúng 1** phép (`qa:sit`), giữ 5 (test, lint, qa:fake-tests, review, security), **0** phiên developer, **0** lượt model, cổng ✅, merge vào main, `attempt.committed`; nhánh story tiến thêm một commit → reviewer + security được gọi lại ở SHA mới, vẫn 0 developer; trượt lần nữa → `failed` với lý do nêu tên mục, `attempts` không đổi; nhánh chính tiến lên → ứng viên giữ nguyên SHA, `main_ahead` có, merge vẫn mang phần mới của main.
* **`--repeat k` (bổ sung ADR-005 §3, hiện thực 2026-09-06):** `implement._repeat_runs(k, chạy)` bọc từng lời gọi chạy lại (test · lint · `qa:<kind>`) — k `tool_run` thật, mỗi lần mang candidate; `_repeat_note` đọc lại k bản ghi ở đúng SHA và ghi `note verify-only.repeat {k, checks, flaky_ids, stable_red, flaky_checks}`: `flaky_ids` = test (theo tên `test_ids`/`failed_ids`) xanh lần này đỏ lần khác, `stable_red` = đỏ ở **mọi** lần, `flaky_checks` = phép kiểm mà `ok` đổi (cho lint/`qa:*` không in tên). Cổng (`gate._khong_on_dinh`): có flaky và không có `stable_red` → mục "test" ⚠ UNRUNNABLE "không ổn định qua k lần chạy trên cùng SHA: <tên>" — mã không đổi giữa các lần thì không phải đỏ, mà không chạy được ổn định thì cũng không phải đạt; `stable_red` → ✗ như thường (lần cuối đỏ); lint/`qa:<kind>` trong `flaky_checks` → ⚠ cùng lý do; mục "không làm đỏ test có sẵn" không tính test flaky (nói ra). k = 1 không ghi gì. `--repeat` từ chối khi không có `--verify-only` hay k < 1. Lý do: lỗi 22 — TB đo flake bằng oracle ×k. **Số đo trên client giả** (`tests/test_run.py::TestVerifyOnlyRepeat` 4 phép, `tests/test_gate.py::TestKhongOnDinh` 4 phép, `tests/test_cli.py` 2 phép; lệnh test in tên `pytest -v`, lần gọi thứ i cho kết cục chữ thứ i của mẫu): mẫu `GR|GGR` → "test" ⚠ nêu đúng `test_on`, không nêu `test_lung`, baseline không ✗, 3 `tool_run test` mang candidate, 0 phiên developer; `GR|RRR` → ✗, `stable_red=[test_on]`; `GR|GGG` → ✅ `done`; k = 1 → không có note. **Chưa đo (T5):** agent thật trên e9 `a60612e` dưới tải — người điều phối chạy; giới hạn đã biết: `autosave.spec.ts:210` là e2e Playwright, `testlog` chưa đọc tên test Playwright nên nó sẽ hiện ở mức phép (`flaky_checks=[qa:e2e]`), chưa hiện tên.
* **Chưa đo:** agent thật. Đích là kịch bản e9 01-07 `a60612e` (§6 mục R1·R8): kỳ vọng lượt kiểm-lại = một lần chạy e2e, $0 model, thay cho ~$10–15 developer + $4–6 rà soát/bảo mật của một lượt thường. Cũng chưa đo: `mockup:<screen>` thật qua trình duyệt; story `verified` (đi qua `run_epic` chỉ merge lại, không chấm lại).

**R1 — Frozen Candidate SHA: hiện thực, unit xanh, chưa đo agent** (2026-09-05).

Đã có: thứ tự nhật ký mới (`changes.detected → candidate.frozen(sha) →
verification.completed → review.completed → merge.completed`, `commit.created`
biến mất khỏi `STEPS`, tên cũ vẫn đọc được cho nhật ký đã ghi); harness commit
worktree **ngay khi phiên developer kết thúc** (`implement.freeze_candidate`,
không có gì để commit thì ứng viên = HEAD; `--no-isolate` không commit); mọi
bằng chứng sau đóng băng mang `detail.candidate` (đóng dấu một chỗ ở
`EvidenceStore`); `Evidence.for_candidate(sha)` + thuộc tính `candidate`; mục
cổng **bằng chứng đúng candidate** (`gate.evaluate(candidate=…)`, rỗng =
không kiểm nên chỗ gọi cũ không đổi hành vi); reviewer/security bị so
`git rev-parse HEAD` sau phiên, lệch → lượt không tính +
`tool_run review:candidate|security:candidate ok=False`; QA cấp dự án ghi
`candidate = HEAD` (`qa.run_suite`, vào cả `pre-deploy.json`); `report` in cột
SHA 7 ký tự; phép hợp quy **C8** (tất định, $0).

Chưa có (cần lượt agent thật): AC (d) *không tăng số lượt/chi phí trên dogfood
`par`* và bảng hợp quy C8 trên hai client — B2 chỉ mới xanh ở nửa unit.

### R5 — Story Complexity Gate v2 (B4, hồi cứu 2026-09-05, 0 agent, $0)

**Hiện thực:** `control/complexity.py` (điểm + gợi ý chẻ + bảng hiệu chuẩn),
`control/preflight.py::story_size_defect` gọi sang đó, ngưỡng
`story.max_complexity` = 16,0 (`story.max_screen_states` = 8 giữ nguyên và
vẫn chặn riêng), `phases/run.py` ghi `_bmad-output/complexity.json` sau
`verification.completed`, `phases/story_split.py` đưa gợi ý chẻ vào
`stories.gate.json` khoá `splits`, `aisdlc doctor` cảnh báo lệch ngưỡng.

**Điểm** = trạng thái màn hình ×1 + tiêu chí chấp nhận ×1 + đường dẫn
`write_scope` ×0,5 (không tính manifest/lockfile) + fan-in phụ thuộc ×1 +
story láng giềng có hành vi VERIFIED bị chạm ×**0** (đọc `ledger.json` nếu có; đếm theo story sở hữu và chỉ **ghi** vào bảng hiệu chuẩn, chưa tính điểm — đo 2026-09-06 trên sổ thật e9: 01-07 chạm 31 hành vi của 3 story, đếm hành vi ×0,5 thì bị chặn oan ở 28,0; đếm láng giềng ×0,5 thì ba story sát ngưỡng 02-03/03-03/05-01 lên 17,0–17,5 và bị chặn bằng trọng số chưa có số lượt nào chứng minh, vì bảng B4 dựng khi sổ còn rỗng. Bật trọng số khi đủ story vừa có sổ vừa có lượt, thiếu thì 0).
Trạng thái màn hình giữ đúng luật `screen_owners`: màn story khác đã dựng
tính 1.

**Dữ liệu:** 23 story thật (e9 18 + `par` 5), chỉ đọc, từ `stories.index.json`,
`EXPERIENCE.md`, `evidence/*.jsonl`. "Lượt đầu" = `turns` của `agent_run`
`<story>#1` **đầu tiên** trong sổ bằng chứng.

| dự án | story | trạng thái | tiêu chí | scope | fan-in | **điểm** | lượt đầu | lượt thử | chạm `max_turns` |
|---|---|---|---|---|---|---|---|---|---|
| e9 | 01-01 | 0 | 7 | 9 | 1 | 12,5 | 61 | 4 | có (trần 60 lúc ấy) |
| e9 | 01-02 | 0 | 7 | 10 | 2 | 14,0 | 42 | 4 | không |
| e9 | 01-03 | 0 | 4 | 3 | 1 | 6,5 | 57 | 1 | không |
| e9 | **01-04** | 9 | 7 | 13 | 1 | **23,5** | 89 / 90 | 4 | không (89 < 90; $79,67) |
| e9 | **01-05** | 5 | 7 | 10 | 1 | **18,0** | 91 | 4 | **có** |
| e9 | 01-06 | 1 | 7 | 6 | 2 | 13,0 | 84 | 3 | không |
| e9 | 01-07 | 2 | 6 | 4 | 2 | 12,0 | — | — | chưa chạy |
| e9 | 02-01 | 0 | 4 | 2 | 1 | 6,0 | — | — | chưa chạy |
| e9 | 02-02 | 0 | 5 | 5 | 2 | 9,5 | — | — | chưa chạy |
| e9 | 02-03 | 1 | 8 | 10 | 1 | 15,0 | — | — | chưa chạy |
| e9 | 02-04 | 1 | 6 | 6 | 1 | 11,0 | — | — | chưa chạy |
| e9 | 03-01 | 1 | 7 | 8 | 1 | 13,0 | — | — | chưa chạy |
| e9 | 03-02 | 1 | 7 | 9 | 2 | 14,5 | — | — | chưa chạy |
| e9 | 03-03 | 4 | 7 | 7 | 1 | 15,5 | — | — | chưa chạy |
| e9 | 04-01 | 2 | 7 | 8 | 1 | 14,0 | — | — | chưa chạy |
| e9 | 04-02 | 3 | 7 | 7 | 1 | 14,5 | — | — | chưa chạy |
| e9 | 05-01 | 5 | 7 | 6 | 1 | 16,0 | — | — | chưa chạy |
| e9 | 05-02 | 2 | 7 | 6 | 0 | 12,0 | — | — | chưa chạy |
| par | 01-01 | 0 | 2 | 2 | 0 | 3,0 | 24 | 2 | không |
| par | 01-02 | 0 | 2 | 2 | 0 | 3,0 | 41 | 2 | **có** (trần 40) |
| par | 01-03 | 0 | 2 | 2 | 0 | 3,0 | 37 | 1 | không |
| par | 02-01 | 0 | 2 | 2 | 0 | 3,0 | (0) | 2 | client không báo `turns` |
| par | 03-01 | 0 | 2 | 2 | 0 | 3,0 | 8 | 1 | không |

**Spearman(điểm, lượt developer lượt đầu) = 0,88** trên n = 10 story có số
lượt (loại `par` STORY-02-01 vì `turns = 0` — client không báo, không phải
"nhanh"). Kể cả nó vào mẫu thì ρ = 0,89. Ngưỡng AC là ≥ 0,5 → **đạt**.

**Tách được 01-04/01-05 khỏi 01-03 và `par`:** ngưỡng 16 chặn đúng hai
story ấy (23,5 và 18,0) và không chạm 01-01 (12,5), 01-02 (14,0), 01-03
(6,5), 01-06 (13,0) hay `par` (3,0). Trên cả 18 story e9 nó chỉ chặn hai
story ấy; story sát ngưỡng nhất chưa chạy là 05-01 (16,0, đúng bằng ngưỡng
nên không chặn). Ngưỡng 15 sẽ chặn thêm 03-03 và 05-01, ngưỡng 18 mất
01-05 — 16 là khoảng rộng nhất còn tách đúng.

**Nói thật phần không khớp.** Hai lần chạm `max_turns` nằm **dưới** ngưỡng:

* e9 01-01 (điểm 12,5) chạm trần ở 61 lượt — nhưng trần lúc ấy là 60, còn
  trần hiện tại là 90. Ở cấu hình hôm nay lần chạy đó không chạm.
* `par` 01-02 (điểm 3,0) chạm trần ở 41 lượt với `run.max_turns` = 40;
  cùng story ấy xong trong 17, 20, 21, 24 lượt ở bốn lần chạy khác. Đây là
  phương sai phiên cộng trần thấp, không phải cỡ story: một story hai tệp,
  hai tiêu chí không chẻ nhỏ hơn được.

Nghĩa là AC (b) của B4 — *"0 story ≤ ngưỡng chạm `max_turns` ở `par`"* —
**không đạt theo nghĩa đen** trên dữ liệu lịch sử, và cách sửa đúng là
`run.max_turns` của `par`, không phải hạ `story.max_complexity` (hạ xuống 3
thì chặn cả 23 story). Cổng ghi nhận: điểm cỡ nói được story nào **luôn
luôn** đắt, không nói được lượt nào **xui**.

**Cũng đo được, và là lý do có cổng v2:** chiều màn hình một mình bỏ sót
e9 01-01 — 0 màn hình, 9 đường dẫn, 7 tiêu chí, 61 lượt lượt đầu và 4 lượt
thử; điểm 12,5 xếp nó trên 01-03 (6,5, 57 lượt/1 lượt thử) đúng thứ tự chi
phí thật.

**Hiệu chuẩn tự ghi.** `_bmad-output/complexity.json` giữ mỗi story một
dòng {điểm, từng thành phần, ngưỡng lúc chấm, lượt đầu, số lượt thử, có
chạm `max_turns`}. `aisdlc doctor` cảnh báo khi ≥ 2 story dưới ngưỡng mà
chạm `max_turns` ("ngưỡng quá cao") hoặc ≥ 2 story trên ngưỡng mà xong
ngay lượt đầu dưới nửa trần ("ngưỡng quá thấp"). Một story lệch không đủ
kết luận — đúng như hai trường hợp ở trên.

**Test:** `tests/test_story_size.py` 30 phép (từng thành phần điểm, story
đã xong bỏ qua, hai ngưỡng, gợi ý chẻ ba lối, hiệu chuẩn ghi/đọc, doctor
cảnh báo, Spearman) + `tests/test_run.py` 2 phép (chặn ở `run`, bảng hiệu
chuẩn được ghi sau khi story xong). Bộ đầy đủ: **1 256 test, OK**
(skipped 56).

**Gộp đợt 2 (2026-09-06 03:05, master 658997c):** suite đầy đủ trên master **1 384 test OK, 4 skip** (1 608 s); hợp quy chạy lại hai client **16/16** với C8 mới (Claude $1,08, OpenCode $0) — C8 trên agent thật: A đạt, B stale ✗ đúng mục `bằng chứng đúng candidate`, cả hai client.

**R4 · R9 — đo trên agent thật, e9 STORY-01-07 chạy lại lần 3 (2026-09-06 03:25–04:20, $17,88, 2 lượt thử, máy rảnh).**

| lượt | ứng viên | rà soát | bảo mật | e2e | bảo toàn (R4) | không làm đỏ test có sẵn (R9) | kết cục |
|---|---|---|---|---|---|---|---|
| 1 | `a60612e` (không đổi so với lần trước — developer 18 lượt, không sửa gì) | ✅ JSON `pass` | ✅ | ✅ (10/10 — xác nhận lỗi 22 là tải máy) | ⚠ **UNRUNNABLE oan**: `FR-11` "không có test mang mã" | ✅ | ✗ chỉ vì bảo toàn |
| 2 | `8e0a5fd` | ✗ 2 chặn + `[bế tắc]` AC-1 vế menu | ✅ | ✅ | ✅ 30 hành vi còn xanh | ✗ **"mất 4 test"** — thực ra developer đổi tên để gắn mã `AC_STORY_01_01_6:` | ✗, dừng epic vì bế tắc kế hoạch |

Baseline R9 chạy trước phiên developer: 440 test id ở bản cha, 0 đỏ sẵn; slot R4 vào bàn giao: `preservation` 1 552 ký tự (chạm trần), `validation` 138, `index` 506.

**Lần chạy 4 (04:45–05:20, sau sửa lỗi 23/24 + đổi lời AC-1): 01-07 XONG ở lượt 1** — developer 23 lượt $1,55 (làm tiếp trên nhánh story còn ứng viên cũ), rà soát 43 lượt $5,50 JSON `pass`, bảo mật 12 lượt $1,47, cổng ✅ đủ 16 mục kể cả *bảo toàn* (30 hành vi của story khác còn xanh ở `c4ac358`) và *không làm đỏ test có sẵn*; merge vào main. **EPIC-01 7/7.** Tổng 01-07 qua 4 lần chạy ≈ $58 (lượt 1 bế tắc phạm vi, lần 2 tải máy, lần 3 lỗi 23/24, lần 4 xong); tổng e9 $495,90.

Hai lỗi thật của đợt 2 lộ ra ngay lượt đầu trên agent thật, sửa cùng đêm (commit sau 0eb65ee):
* **Lỗi 23 (R4):** cổng hỏi test mang mã của story *sở hữu* FR (01-01, story không có test mang mã), trong khi sổ xác minh FR-11 *qua* 01-05 (`source.story`). Sổ và cổng dùng hai luật → sổ nói VERIFIED, cổng nói không kiểm được. Sửa: mục bảo toàn mang `via` = story đã xác minh, cổng hỏi đúng story ấy (test `test_fr_hoi_story_da_xac_minh_no_khong_hoi_story_so_huu`).
* **Lỗi 24 (R9):** đổi tên test giữ nguyên tiêu đề lá bị đọc thành "mất test". Chính lỗi 23 xui developer làm việc ấy (gắn mã vào test của story khác để cổng hết kêu). Sửa: cùng tiêu đề lá còn ở ứng viên → "đổi tên", không phải mất; xoá thật vẫn bị bắt (test `test_doi_ten_test_giu_tieu_de_la_khong_phai_mat`).
* Bế tắc kế hoạch lượt 2 là thật ở mức tiêu chí: AC-1 đòi "menu là lối duy nhất *tới*" ba màn hình chưa có route (FR-3/10/16, story sau). Chủ dự án sửa lời tiêu chí (e9 1597e3d). Reviewer trả JSON `block` nhưng văn bản có `[bế tắc]` → harness dừng epic theo văn bản: đúng luật hợp (không nới), và đúng việc — tiêu chí không thoả được trong phạm vi là việc của người.

**R1 · R8 — đo trên agent thật, e9 STORY-01-07 chạy lại 2026-09-06 01:03–02:14 (Claude, $28,76, 3 lượt thử).**

| lượt | developer | ứng viên | review (lượt · $) | JSON review | security (lượt · $) | JSON security | kết cục cổng |
|---|---|---|---|---|---|---|---|
| 1 | 47 lượt · $4,43 | `689af33` | 32 · $4,27 | có, `block` | 6 · $0,79 | có, `pass` | ✗ rà soát |
| 2 | 57 · $5,53 | `37ec429` | 44 · $5,82 | có, `block` | 9 · $1,12 | có, `pass` | ✗ rà soát |
| 3 | 25 · $2,60 | `a60612e` | 18 · $2,83 | có, `pass` | 8 · $1,37 | có, `pass` | ✗ e2e |

* R1: nhật ký có `changes.detected → candidate.frozen` mỗi lượt, mọi bằng chứng sau phiên developer (lint, test, `qa:*`, mockup_map, rà soát, bảo mật) mang đúng SHA của lượt; mục "bằng chứng đúng candidate" ✅ ở cả 3 lượt; không lượt rà soát nào bị huỷ vì đổi HEAD. Không có phiên agent nào thêm — AC (d) "không tăng lượt/chi phí" **đạt** trên story này (chi phí thêm = 3 lần `git commit`).
* R8 / B7: 6/6 phiên rà soát trả khối JSON đúng schema ngay lượt đầu, **0** lần hỏi lại (`review:no-schema`/`*-retry` không xuất hiện); 0 `review:mismatch` — bản văn bản và bản máy đọc khớp theo khoá (thẻ, tệp). Chi phí thêm của R8 trên agent thật = 0 lượt.
* Kết cục story: **trượt** sau 3 lượt (`run.max_retries` = 2). Lượt 3 rà soát ✅, bảo mật ✅, chỉ e2e ✗ ở `tests/e2e/autosave.spec.ts:210` ("Đã lưu đứng ít nhất 800 ms", test của STORY-01-06). Đo lại ngay sau đó trên đúng ứng viên `a60612e` (worktree tách riêng, cùng node_modules, load 17): **10/10 e2e xanh, 15,3 s**. Lúc cổng chạy, máy đang gánh ba bộ test đầy đủ của ba luồng ADR-004 + Docker (load 40–150). Kết luận: trượt vì môi trường đo, không vì mã; harness chấm đúng theo bằng chứng nó có, và bằng chứng ấy đúng cho thời điểm ấy.
* Điều thiếu lộ ra (ghi thành P2 R13 ở §2): **không có cách chạy lại phép kiểm trên ứng viên đã đóng băng** mà không mở phiên developer mới — R1 đã làm cho việc ấy có nghĩa (bằng chứng rà soát ở `a60612e` vẫn hợp lệ), nhưng `aisdlc run` chỉ biết "lượt mới = developer mới". Giá của khoảng trống này hôm nay: một lượt developer nữa (~$10–15) để dựng lại thứ đã có.

**R8 — schema bắt buộc + retry cho đầu ra rà soát: hiện thực, unit xanh,
chưa đo trên `par`.** (2026-09-05)

* Prompt `story-review@4` và `story-security-review@2` đòi thêm một khối
  JSON ở cuối (`verdict` + `findings` mang `tag`/`file`/`line`/`why`/
  `behavior_id`, bảo mật thêm `severity`); phần văn bản có thẻ `[chặn]`/
  `[bế tắc]` giữ nguyên — bản người đọc và bản máy đọc, hai bản phải khớp.
* `implement.py::review_verdict` lấy khối JSON đầu tiên có `verdict` bằng
  `json.JSONDecoder.raw_decode` (bền hơn cách cắt dần của
  `skill_scan.parse_verdicts`: hàng rào ```json và chữ thừa hai đầu không
  làm hỏng việc); mục sai schema bỏ, không sập.
* Thiếu/sai schema → hỏi lại **đúng một lần** (`SCHEMA_REMINDER` nối vào
  chính prompt cũ), ghi thêm một `agent_run` tên `<story>-review-retry` /
  `<story>-security-retry` (chi phí vào bằng chứng) và một bản nguyên văn
  `reviews/<story>-review-retry-<lượt>.md`. Lần hai vẫn thiếu → dùng văn
  bản như trước, note `review:no-schema`.
* Xung đột JSON ↔ văn bản: **hợp** hai nguồn (khoá đối chiếu = thẻ + tệp),
  note `review:mismatch`. Không nới lỏng: JSON `pass` mà văn bản có `[chặn]`
  thì vẫn chặn, và `verdict` khác `pass` mà không nêu mục nào cũng thành
  một mục chặn.
* `behavior_id` ra ngoài qua note `review:verdict` / `security:verdict`
  (`detail={"verdict", "findings"}`) — đầu vào cho sổ hành vi R2 nguồn
  `reviewer`. `review_story` giữ nguyên chữ ký; bản máy đọc lấy ở
  `review_story_v2 -> (findings, verdict)`. `persist_verdict` không đổi.
* **Unit:** 17 test ở `tests/test_findings.py` (JSON hợp lệ không hỏi lại ·
  thiếu JSON hỏi lại đúng 1 lần · hai lượt đều thiếu thì dùng văn bản ·
  lệch thì hợp hai nguồn · bảo mật với `severity` + lọc nhiễu) + 2 test
  vòng đời ở `tests/test_implement.py`. Toàn bộ bộ test xanh.
* **Chưa đo (B7):** số lượt rà soát trên `par` với agent thật. Client giả
  không trả JSON nên trong unit mỗi vai rà soát tốn thêm đúng 1 lượt —
  đúng thiết kế; agent thật đọc prompt mới phải không cần lượt ấy, và đó
  chính là thứ B7 phải chứng minh trước khi R8 chuyển ACCEPTED.

### R4 — Preservation / Validation trong gói bàn giao + cổng "bảo toàn" (2026-09-06, unit + mutation trên client giả, 0 agent)

**Hiện thực.** `implement.build_context` thêm hai slot nguồn `ledger`:

* `preservation` = hành vi VERIFIED của **story khác** mà `write_scope` của
  story chạm tệp — phép giao tệp **tái dùng** `complexity.verified_touched`
  (R5), không có bản thứ hai. Mỗi dòng: id · story sở hữu · nguồn kiểm
  (`test_id` / `qa:<kind>` / màn hình, đọc từ `ledger.behaviors[id].source`).
  Sổ được **chiếu lại từ evidence** mỗi lượt (`ledger.build`, 1,1 s trên
  e9) chứ không đọc `ledger.json`: tệp ấy chỉ `aisdlc report` làm mới, nên
  trong một lần `run` qua cả epic story sau sẽ không thấy hành vi story
  trước vừa xác minh. Danh sách tính **một lần trước phiên developer** và
  truyền nguyên cho reviewer, security và cổng (`build_context(...,
  preservation=)`) — tính lại sau phiên thì sổ đã đổi theo bằng chứng của
  chính lượt ấy và ba vai nói về ba danh sách; test
  `test_ba_vai_nhan_cung_mot_danh_sach_tu_harness` khoá điều này.
* `validation` = thứ harness **chạy lại** ở ứng viên: số test bảo toàn
  (tên đã ở slot trên, không chép lại — e9 01-07 có 27 test id), `qa:<kind>`
  (hợp đồng story ∪ kiểm định đã xác minh bị chạm), màn hình (story ∪ bị
  chạm). `validation_targets()` cấp cùng lúc cho slot và cho `run_attempt`
  (`run_suite(only=…)`, `verify_screens(…)`), nên thứ in cho agent và thứ
  thật sự chạy là một danh sách.
* Không thêm slot `targets`: ADR chỉ đòi hai slot; tiêu chí story đã ở
  `story_contract`, GAP/REOPENED của story đã ở `index` (V/G/R).
* Knob `context.max_preservation_chars` = 1500, áp cho cả hai slot; **chỉ
  cắt phần in ra** — cổng vẫn chấm đủ danh sách (test riêng).
* Cổng `gate.evaluate(preservation=)` thêm mục **bảo toàn**, ba kết cục:
  test mang mã / `qa:<kind>` / `mockup_map` **ở đúng SHA ứng viên** đỏ →
  FAILED; không có bằng chứng ở ứng viên (test bị xoá/đổi tên, qa bỏ qua,
  màn chưa đối chiếu, bằng chứng ở bản khác) → UNRUNNABLE — không kiểm được
  không phải đạt; còn lại PASSED. Rỗng → NOT_APPLICABLE, chỗ gọi cũ không
  đổi kết cục. `FR`/`NFR` chấm theo cùng luật với sổ: đỏ khi một tiêu chí
  của story sở hữu đỏ.
* **REOPENED không ghi tay.** Cổng đọc đúng `tool_run test` /
  `qa:<kind>` / `mockup_map` mà `ledger.build()` cũng đọc; nhánh "story
  khác chỉ bị chấm tiêu chí thực sự thấy test" của `_observe_tests` (R2)
  suy `REOPENED` với `regressed_by = <story đang chấm>#<lượt>@<sha>` từ chính
  bằng chứng ấy. Ghi thêm `BEHAVIOR` ở cổng là ghi hai lần cùng một sự thật
  và tạo chỗ cho hai bản lệch nhau. Mutation test kiểm cả hai đầu: cổng ✗
  **và** sổ `REOPENED` + `cross_reopens` đúng thủ phạm.
* Prompt: `story-implement@5`, `story-review@5`, `story-security-review@3`
  thêm hai mục ngắn. Phát hiện kèm: `_bmad-output/reviews` (harness ghi)
  chưa nằm trong `HARNESS_OWNED` — lộ khi hai story chạy chung một cây
  (`--no-isolate`): tệp lời rà soát của story trước thành "ngoài phạm vi
  ghi" của story sau. Đã thêm.

**Số đo (c) — prompt_chars trước/sau, cùng kịch bản trên client giả**
(`tests/test_preservation.py`: story A xanh 1 tiêu chí + FR-1 + `qa:fake-tests`,
story B chạm cùng `src/`; đo bằng `agent_run.prompt_chars` và slot của
`handoff`; docker tắt để runner giả in tên test `pytest -v`):

| vai | trước (370ea23) | sau | Δ do R4 | Δ % | phần khung prompt | phần slot |
|---|---|---|---|---|---|---|
| developer | 4 125 | 4 837 | +544 | **+13,2 %** | +332 | +212 (`preservation` 180 · `validation` 32) |
| reviewer | 3 702 | 4 091 | +389 | +10,5 % | +177 | +212 |
| security | 4 017 | 4 328 | +411 | +10,5 % | +199 | +212 |

Δ do R4 = khung + slot, đối chiếu với số đo thô: developer thô +712, trong
đó 168 là slot `tools` in đường dẫn tuyệt đối `bin/aisdlc` của worktree dài
hơn kho chính (4 dòng × 42) — không phải R4; security thô +311 vì ở bản
370ea23 tệp lời rà soát `_bmad-output/reviews/STORY-01-02-review*.md` (đã
ghi trước phiên bảo mật) lọt vào `diff_summary`/`impact` của chính phiên
ấy (+100) — lỗi `HARNESS_OWNED` nói trên, nay đã đóng nên số "sau" không
có phần ấy. Bản nháp đầu là +22 % (validation chép lại từng test id, khung
dài); rút xuống bằng cách đếm test thay vì liệt kê và rút khung. Trên e9
(prompt developer ≈ 13,5k) cùng lượng thêm này là ≈ +4 %; với 31 hành vi
của 01-07 slot chạm trần 1 500 → tối đa ≈ +13,6 %. Test
`test_hai_slot_moi_khong_qua_15_phan_tram_prompt` giữ ngân sách cho lần
sửa prompt sau.

**AC (a)** đạt (`test_story_cham_tep_cua_hanh_vi_verified_thi_slot_neu_dung_hanh_vi_va_test_id`):
slot có đúng `AC-STORY-01-01-1` + `FR-1` kèm test id, không có hành vi của
chính story. **AC (b)** đạt trên client giả
(`test_cong_bao_toan_chan_va_so_ghi_reopened_dung_thu_pham`): B ghi đè
`src/a.py`, test của A đỏ → cổng "bảo toàn" ✗ nêu đúng test, sổ
`AC-STORY-01-01-1` và `FR-1` REOPENED với `regressed_by = STORY-01-02#1@…`,
`cross_reopens` = 2; chạy sạch → ✅ và `reopen_events = 0` (nửa "không ✗
oan" của B3). Cổng unit 7 phép ở `TestCongBaoToan`.

**B5 hồi cứu trên e9 (2026-09-06, chỉ đọc `evidence/STORY-01-07.jsonl` +
`STORY-RP-01/02.jsonl`, 0 agent, $0).** 01-07 chạy bốn lần; `handoff` ghi
`chars` từng slot và `agent_run` ghi `prompt_chars` ở **mọi** lần, kể cả
lần cũ, nên tách được phần khung prompt (= `prompt_chars` − Σ slot) khỏi
phần slot mà không cần chạy lại gì:

| lần chạy (giờ máy) | slot nguồn `ledger` trong bàn giao | khung developer / reviewer / security |
|---|---|---|
| 1 · 09-05 23:41 – 00:13, 1 lượt | — | 2 484 / 1 184 / 1 465 |
| 2 · 09-06 01:04 – 02:05, 3 lượt | `index` 500–506 (R6) | 2 796 / 1 661 / 1 876 |
| 3 · 03:20 – 03:52, 2 lượt | + `preservation` 1 552 · `validation` 138 (R4) | 3 128 / 1 838 / 2 075 |
| 4 · 04:21 – 04:37, 1 lượt | như lần 3 | như lần 3 |

Khung không đổi giữa các lượt của cùng lần chạy, và bước nhảy 2→3
(+332 / +177 / +199) **trùng đúng** cột "phần khung" đo bằng unit ở bảng
trên — hai phép đo độc lập cho cùng một số. So lượt 1 của lần 2 với lượt 1
của lần 3 (cùng `story_contract` 3 121, `index` 506 ± 6):

| vai | trước R4 (lần 2 #1) | sau R4 (lần 3 #1) | Δ thô | Δ do R4 = khung + slot | **Δ % do R4** | phần không phải R4 |
|---|---|---|---|---|---|---|
| developer | 11 537 | 13 565 | +2 028 | +332 + 1 690 = +2 022 | **+17,5 %** | `index` +6 |
| reviewer | 51 258 | 71 158 | +19 900 | +177 + 1 690 = +1 867 | +3,6 % | `diff_summary` +18 002 · `impact` +31 |
| security | 51 473 | 71 395 | +19 922 | +199 + 1 690 = +1 889 | +3,7 % | như reviewer |

Kết luận: trần +15 % **không đạt ở vai developer** trên 01-07 — +17,5 %
so với lượt 1, và vẫn +15,7 % nếu lấy mẫu số là prompt lượt 3 của lần 2
(12 868, đã có phản hồi cổng/rà soát). Reviewer/security đạt dư vì mẫu số
của họ là `diff_summary` 43–61k. Ước lượng "≈ +13,6 % tối đa" ở trên sai
mẫu số: prompt developer thật của e9 lúc chưa có R4 là 11,5k, không phải
13,5k. Phần lớn số thêm là `preservation` chạm trần (1 552 = 1 500 + ghi
chú cắt); với 30 hành vi bảo toàn nó chạm trần ở **mọi** lượt về sau
(01-07 lần 3/4, RP-01, RP-02 đều 1 552), nên trên e9 giá của R4 là hằng số
≈ 2 020 ký tự mỗi lượt developer, không tăng theo epic. Về dưới trần với
mẫu số này cần bớt ≈ 290 ký tự: `context.max_preservation_chars` ≈ 1 200,
hoặc rút khung (+332 → ≤ 40). Chưa làm — đó là việc của lượt sửa prompt
sau; ghi ở đây để không phải đo lại.

Story sửa của vòng cải tiến (RP-01/02) chỉ có bản "sau": slot R4 chiếm
14,6 % / 14,4 % prompt developer lượt 1 (1 690 / 11 607 và 11 758) — tỉ
trọng, không phải Δ, vì hai story ấy chưa từng chạy không có R4.

Điều bằng chứng **không** cho suy: chi phí token/USD do R4. `agent_run`
ghi `prompt_chars` và tổng token, không tách token đầu vào theo slot; số
lượt và USD giữa bốn lần chạy khác nhau vì lý do khác (bế tắc phạm vi, tải
máy, lỗi 23/24), nên không quy phần nào cho R4 được.

**Chưa đo:** B3 trên `par` với agent thật (mutation có chủ đích và "không
✗ oan trên chạy sạch" ở dogfood) — cần lượt agent, cùng lô với R1 (d) và
R8 (B7). Chưa có story nào của e9/`par` có `mockup:*`/`qa:e2e` VERIFIED
bị story sau chạm, nên nhánh `verify_screens` cho màn hình bảo toàn mới
chỉ xanh ở unit (`test_qa_va_mockup_theo_cung_ba_ket_cuc`).

### R12 — Xuất bảng gap/hồi quy (`aisdlc issues`) · hiện thực 2026-09-06, unit xanh, 0 agent

`Ledger.issues(epic=, statuses=)` là phép chiếu thứ hai của cùng sổ (không
kho mới): một dòng mỗi hành vi chưa xanh — id · loại · trạng thái · story
sở hữu · `regressed_by` · nguồn kiểm (test id / `qa:<kind>` / màn hình) ·
lý do · candidate · `since` · số lần đổi trạng thái; hồi quy xếp trước gap.
`issues_text()` ra Markdown hoặc CSV chuẩn (`csv`), cùng cột; mặc định
`_bmad-output/ISSUES.md|csv`, lọc `--epic` / `--status`. Chỉ tệp — không
tạo issue ở tracker nào, không chạm cổng. 4 test ở `tests/test_ledger.py::TestXuatBangGap`.
Khói trên e9 (chỉ đọc, 2026-09-06 06:00): 64 hành vi → 14 dòng gap, 0 reopened
(38 lần hồi quy trong lịch sử đều đã đóng), 13 thuộc EPIC-01 — 13 tiêu chí của
01-01/02/03 "không đọc được tên test từ output runner" (bằng chứng trước khi
có reporter) và `qa:mutation` ở mốc `loop-0`.

**B3 trên `par`, agent thật (2026-09-06, `tests/dogfood/test_par_mutation.py`,
Claude, $3,72 cả hai story).** Story A = `STORY-01-01` (`slugify`, nối `-`)
chạy tới `done`; story B = `STORY-01-04` "Slug nối bằng gạch dưới": FR-4
hợp lệ về sản phẩm ("đổi FR-1 về dấu nối: `_` để slug dùng được làm tên
biến/tên tệp"), phạm vi ghi `src/slugify.js` + `src/slugify-underscore.test.js`
— trùng tệp mã của A, **không** có test của A; tiêu chí ghim
`slugify('Hello World') === 'hello_world'` khi không truyền thêm tham số,
nên không cài đặt nào thoả B mà 5 test `AC-STORY-01-01-1` của A
(`hello-world`) còn xanh. Story không nhắc gì tới test của A.

| | A `STORY-01-01` | B `STORY-01-04` |
|---|---|---|
| lượt developer · turn | 1 · 15 | 1 · 30 — guard `completion` chặn Stop 3 lần, agent lật `slugify.js` 3 lần, **không** chạm `slugify.test.js`, không chạm `max_turns` |
| chi phí dev / review / security | $0,58 / $0,85 / $0,25 | $1,23 / $0,53 / $0,29 |
| baseline R9 | ○ chưa có test | ✅ 6 test xanh ở `f1f2ac6` |
| cổng | ✅ | ✗ 6 mục: test · **không làm đỏ test có sẵn** · tiêu chí có test · TDD · rà soát · **bảo toàn** |
| mục "bảo toàn" | – không chạm story nào | ✗ `AC-STORY-01-01-1 (AC-STORY-01-01-1: chữ thường và nối bằng dấu gạch ngang)`, `FR-1 (…)` |
| mục "không làm đỏ test có sẵn" | ○ | ✗ "làm đỏ 5 test xanh ở baseline: …chữ thường và nối bằng dấu gạch ngang, …bỏ dấu tiếng Việt về ASCII, …ký tự không phải chữ hay số…, …gộp dấu nối liên tiếp…, …ký tự ngoài ASCII…" |
| reviewer | ✅ | `[bế tắc]` `behavior_id = AC-STORY-01-01-1`: tự chạy `npm test`, chỉ đúng `src/slugify.test.js:7`, kết luận "hai tiêu chí đòi hai giá trị cho cùng lời gọi — việc của người: rút điều khoản dấu nối của FR-1 khỏi sổ bảo toàn rồi cấp `slugify.test.js` vào write_scope" → `plan_defects` → story `failed` sau lượt 1, **không đốt lượt 2** |
| sổ `ledger.build()` | AC-1, AC-2, FR-1 VERIFIED @`25c3e34` | `AC-STORY-01-01-1`, `FR-1` **REOPENED**, `regressed_by = STORY-01-04#1`, `candidate = 516d81d`, `cross_reopens = 2` |
| merge | FF lên main | **không** — main giữ `f1f2ac6` |

AC (b) đạt trên agent thật: cả hai cổng mới ✗ nêu đúng tên test của A, sổ
REOPENED đúng thủ phạm, không merge; lời feedback cho lượt sau (không xảy
ra vì reviewer bế tắc) có tên test ở ba mục. Nửa "không ✗ oan trên chạy
sạch" với agent thật: e9 01-07 lần 4 (cổng ✅ 16 mục kể cả bảo toàn và
baseline, STATUS §2.9). `AISDLC_DOGFOOD_REUSE=1` chạy lại chỉ B từ bản chụp
`par-mutation.A` (≈ $2). Dữ liệu nói thêm ba điều:

* `regressed_by` **không mang `@sha`**: lần đỏ đầu tiên của test A là lần
  `aisdlc tool test` agent tự chạy giữa phiên (chưa đóng băng); lần đỏ ở
  ứng viên `516d81d` sau đó không đổi trạng thái nên chỉ cập nhật
  `candidate`. Đúng hợp đồng R2 (`[@candidate]` tuỳ chọn), SHA tra được ở
  `candidate` — không sửa.
* **Lỗi 26** — cùng lần chạy giữa phiên ấy làm `AC-STORY-01-04-1/2`, `FR-4`
  của B **VERIFIED** dù B trượt và chưa merge (`verified = 5`): `build()`
  coi sự kiện không mang candidate là landed (luật cho bằng chứng trước
  R1), trong khi với story đã đóng băng thì sự kiện không mang candidate
  chính là lần chạy **trước** khi đóng băng. Story sau chạm `src/slugify.js`
  sẽ phải "bảo toàn" một test chưa từng lên main → UNRUNNABLE oan. Sửa:
  story có `candidate.frozen` → chỉ SHA landed mới tính; không nhật ký /
  chưa từng đóng băng → như cũ. Trên `par-mutation` sau sửa: B 0 VERIFIED
  (3 GAP), A không đổi, `unlanded_green` 5 → 34.
* **Lỗi 27** — danh sách bảo toàn cho **lượt 2** tính từ sổ đã có B#1 chỉ
  còn `[AC-STORY-01-01-2, qa:fake-tests]`: `verified_touched` bỏ REOPENED,
  nên hành vi B vừa làm hỏng biến mất khỏi slot và khỏi mục "bảo toàn" của
  lượt sau (mục ấy sẽ ✅ "1 hành vi còn xanh" trong khi test A còn đỏ; chỉ
  R9 và mục "test" còn giữ). Sửa: REOPENED có `regressed_by` bắt đầu bằng
  chính story → vẫn phải giữ; REOPENED do story khác → không, để khỏi ✗
  oan. Sau sửa lượt 2 nhận `[AC-STORY-01-01-1, AC-STORY-01-01-2, FR-1,
  qa:fake-tests]`.

**Chưa đo:** (c) prompt_chars trên dogfood/e9 01-05 với agent thật. Chưa có
story nào của e9/`par` có `mockup:*`/`qa:e2e` VERIFIED bị story sau chạm,
nên nhánh `verify_screens` cho màn hình bảo toàn mới chỉ xanh ở unit
(`test_qa_va_mockup_theo_cung_ba_ket_cuc`).

### R3 — Vòng cải tiến epic (`phases/improve.py`, `aisdlc improve`) · hiện thực 2026-09-06, unit xanh, **B1 chưa đo**

**Ghép, không thêm pha.** Mỗi vòng: `qa.run_suite` ở HEAD (bằng chứng ghi
dưới mốc `evidence/loop-<n>.jsonl` — sổ đọc nó, `since = loop-n` đúng
schema §4, nhưng **không** dựng dòng chỉ mục cho nó) → `ledger.build()` →
GAP/REOPENED mà story sở hữu thuộc epic (REOPENED trước, rồi theo id) →
**một** story sửa sinh bằng code → `run.run_epic(EPIC-RP-<E>)` → QA lại →
`ledger.snapshot("loop-n", cost)` → vòng sau. `run.py`/`implement.py`
không đổi một dòng; story sửa đi qua đúng tiền kiểm của story thường (cỡ
R5, năng lực, phạm vi) ở `run_epic`.

**Một story sửa mỗi vòng = một hành vi.** B1 đòi chi phí ≤ 1 story trung
bình/vòng, và một hành vi là đơn vị nhỏ nhất cổng chấm được. Story sửa
`STORY-RP-nn` (`control/change.register_story`, cùng cơ chế với
`STORY-CH-nn`): tiêu đề nêu hành vi + trạng thái + story sở hữu; tiêu chí
= chính hành vi, **giữ id gốc** trong câu (`AC-STORY-01-04-1 xanh lại: …`)
và tệp story dặn test phải mang cả mã mới lẫn mã gốc — sổ khớp lại theo
mã gốc, cổng chấm theo mã mới; `write_scope` = phạm vi story sở hữu +
`verification_paths`; `verification_contract` = hợp đồng story sở hữu
(+ `<kind>` với gap `qa:<kind>`, + màn hình với gap `mockup:`);
`depends_on` rỗng; chỉ mục thêm `repair_of`, `loop`, `preservation`
(`complexity.verified_touched`, ghi vào tệp story mục "Bảo toàn" — R4 nạp
vào slot), `source`. Đợt của `EPIC-RP-<E>` chỉ gồm story của vòng này;
story sửa **chưa xong** của cùng hành vi được chạy lại thay vì đẻ bản sao.

**Điều kiện dừng đọc từ đĩa, không từ bộ nhớ tiến trình** — nên một lần
gọi chạy tối đa `max_loops` vòng rồi thoát, chạy lại tiếp từ mốc cuối:
(1) hết gap thuộc epic; (2) số vòng của epic trong `loops[]` ≥
`improve.max_loops` (đếm **cả** lần gọi trước — gọi lại với cùng
`--max-loops` không tốn thêm vòng nào); (3) Δverified − Δreopened ≤ 0 trong
`improve.flat_loops` vòng liền, đọc từ hai mốc liên tiếp; (4) tổng
`cost_usd` các vòng của epic > `improve.cost_cap_usd` (chi phí = hiệu
`total_cost_usd` bằng chứng của story sửa trước/sau vòng); (5) `plan_defects`
trên lời rà soát của story sửa → dừng, `stopped` mang nguyên lời reviewer.
Cổng người `improve` chặn trước vòng ≥ 2 trừ `--auto`.

**Hai chỗ lệch với phác thảo §2/§4, có số:**

* *Δ tính trên hành vi thuộc epic, không phải toàn sổ.* Bản đầu dùng
  `Ledger.metrics()` (Δ toàn cục, R7): trên client giả, một vòng **không
  sửa gì** vẫn ra V+1 vì chính story sửa đẻ thêm hành vi (`AC-STORY-RP-01-1`
  xanh, `qa:fake-tests` xanh) — điều kiện (3) không bao giờ tới, chỉ còn
  `max_loops` giữ. Mốc `loops[]` nay ghi thêm `epic`, `epic_verified`,
  `epic_gap`, `epic_reopened`, `story`, `behavior`; R7 vẫn đọc cột toàn cục.
  Mốc xuất phát `loop-0` được ghi khi sổ rỗng, khi sổ đã đổi giữa hai lần
  gọi, hoặc khi mốc cuối thuộc epic khác — để "hai mốc liên tiếp" luôn cùng
  epic và Δ không gộp việc của story thường chạy giữa chừng.
* *Cổng `improve` đứng ngoài `GATE_ORDER`.* §4 đặt nó giữa `readiness` và
  `pre-deploy`; làm thế thì `blocking(pre-deploy)` đòi duyệt `improve` ở
  mọi dự án chưa từng chạy vòng nào. Nó là `Gate.IMPROVE` trong enum,
  artifact là mẫu glob `LOOP-REPORT-*.md` (băm gộp mọi báo cáo → vòng mới
  làm phê duyệt cũ `stale` → duyệt **mỗi** vòng, không duyệt một lần cho
  cả chuỗi), `blocking()` rỗng, băm tám cổng cũ không đổi (có test).

**Số đo trên client giả** (`tests/test_improve.py`, 22 phép, kho git thật,
không Docker, ~25 s). Gap xuất phát là loại có thật ở HEAD đã merge — bộ
test xanh nhưng *chưa có test mang mã* (chính 18 gap của e9); test đỏ trên
main không tới được vòng này vì cổng story đã chặn trước merge. Kết quả:
2 GAP → vòng 1 đóng `AC-…-1`, vòng 2 đóng `AC-…-2`, vòng 3 dừng "không còn
GAP/REOPENED"; mỗi vòng Δ = +1, $1.40 (developer 1,0 + reviewer 0,1 + bảo
mật 0,1 + hai lượt hỏi lại schema R8 0,2 — từ bằng chứng), `loops[] =
[loop-0, loop-1, loop-2]`, hai `LOOP-REPORT`; story sửa **qua cổng của nó
mà không đóng gap** (test chỉ mang mã mới) → Δ toàn sổ dương nhưng Δ epic
= 0, dừng sau đúng 2 vòng phẳng; story sửa trượt → vòng sau chạy lại chính
`STORY-RP-01`, chỉ mục không có bản sao; trần $1 → dừng sau vòng 1 ($1.40);
`[bế tắc]` → dừng sau vòng 1, `stopped` chứa `src/store/db.ts` của
reviewer, không thử tiếp; không `--auto` → dừng chờ cổng sau vòng 1,
duyệt rồi gọi lại → vòng 2, báo cáo vòng 2 làm cổng `stale`; gọi lại với
cùng `max_loops` → 0 vòng; sổ đổi giữa hai lần gọi → mốc `loop-0` mới.
Bất biến (b): mỗi `STORY-RP-nn` có `worktree.created` + `merge.completed`
trong nhật ký và `handoff developer→reviewer` trong bằng chứng.

Một điều đo được và **chưa** sửa (thuộc R2, không thuộc R3): bằng chứng
của một lượt story sửa *trượt cổng* (test xanh trong worktree, reviewer
chặn) vẫn làm hành vi gốc VERIFIED trong sổ dù code chưa merge — sổ ghi
"quan sát cuối cùng", không hỏi bản ấy đã lên nhánh chính chưa. R1 có
`candidate` cho việc này; sổ chưa lọc theo nó.
  **Đã sửa 2026-09-06** (gộp đợt 2, `control/ledger.py`): sổ đọc nhật ký R1 — ứng viên chỉ *landed* khi giao dịch đóng băng nó kết thúc bằng `attempt.committed`/`merge.completed`; xanh ở ứng viên chưa landed **không** thành VERIFIED (đếm vào `unlanded_green` trong summary, hành vi chưa có thì ghi GAP với lý do), đỏ vẫn tính là hồi quy. Bằng chứng không có nhật ký (QA cấp dự án, mốc vòng) hoặc không khai bản giữ luật cũ. Test: `tests/test_ledger.py::TestUngVienChuaLanded`.

**B1 đo thật (2026-09-06 04:0x–05:0x, `aisdlc improve --epic EPIC-01 --max-loops 2 --auto --client claude`, trần $80):**

| vòng | story sửa | hành vi | lượt thử | developer (lượt) | chi phí | Δverified − Δreopened | gap epic |
|---|---|---|---|---|---|---|---|
| 0 | — (QA + sổ) | — | — | — | $0 | — | 17 |
| 1 | STORY-RP-01 | AC-STORY-01-01-1 | 2 | 42 + 16 | $8,87 | **+1** (R = 0) | 17 → 16 |
| 2 | STORY-RP-02 | AC-STORY-01-01-2 | 2 | 26 + 13 | $8,09 | **+1** (R = 0) | 16 → 15 |

Dừng đúng điều kiện (2): đủ `improve.max_loops`. Bất biến (b) giữ: cả hai story sửa có `worktree.created`, `handoff developer→reviewer→security`, `merge.completed`; cổng đủ 16 mục, *bảo toàn* 33 hành vi story khác còn xanh. Sổ toàn dự án 42 → 46 VERIFIED, 18 → 16 GAP, 0 REOPENED. Dự báo "dừng ở bế tắc vì reporter" **sai**: gap của 01-01 là test không mang mã, developer gắn mã trong phạm vi được (`vite.config.ts` thuộc write_scope 01-01). Cả hai vòng trượt lượt 1 ở *không làm đỏ test có sẵn* ("mất 1 test": developer đổi cả tiêu đề lá khi gắn mã) rồi lượt 2 trả tên cũ, chỉ thêm mã — feedback R9 làm đúng việc, giá ≈ $3–5 mỗi vòng. Chi phí một vòng ≈ $8,5 ≈ 1/5 story trung bình EPIC-01 ($70) → AC "≤ 1 story/vòng" đạt; cải thiện biên +1/vòng, chưa thấy phẳng.

**Lỗi 25 (R3 × cổng người), lộ khi gọi `improve` lần hai (05:44):** story sửa ghi vào `stories.index.json` làm phê duyệt `stories`/`readiness` stale → lần gọi kế bị chặn bởi chính vòng trước. Sửa: `approvals._artifact_hash` băm chỉ mục chuẩn hoá và bỏ `STORY-RP-*`/`EPIC-RP-*` (story sửa do cổng `improve` quản); một lần duyệt lại cho dự án đã có phê duyệt cũ (e9 làm 05:5x). Test `TestStorySuaKhongLamStaleCongStories`.

**B1 tiếp (vòng 3–5, 05:48–07:1x, `--max-loops 8`, trần $150) — đường cong phẳng rồi âm, dừng đúng điều kiện (3):**

| vòng | story sửa | hành vi | kết cục | chi phí | Δverified − Δreopened | gap epic |
|---|---|---|---|---|---|---|
| 3 | STORY-RP-03 | AC-STORY-01-01-3 | XONG | $3,43 | **+1** | 15 → 14 |
| 4 | STORY-RP-04 | AC-STORY-01-01-4 | CHƯA XONG (3 lượt, hết `max_retries`) | $14,63 | **−1** (R+1: lượt trượt làm đỏ một hành vi láng giềng — sổ ghi REOPENED dù chưa landed, đúng luật "đỏ vẫn tính") | 14 → 14 |
| 5 | STORY-RP-05 | `qa:e2e` (gap cấp dự án) | CHƯA XONG | $11,25 | **−2** (V−2 R+2) | 14 → 16 |

Dừng: "cải thiện biên ≤ 0 trong 2 vòng liền (loop-4, loop-5)" — `improve.flat_loops` = 2 làm đúng việc, trước khi chạm `max_loops` 8 và trần $150. Tổng B1 5 vòng ≈ $46: ba vòng đầu +1/vòng ($3–9), hai vòng sau âm ($11–15) khi hành vi còn lại không còn là "test thiếu mã" mà là `qa:*` cấp dự án và tiêu chí cần màn hình/route của story sau. Bài học cho R3: (a) thứ tự chọn gap nên ưu tiên `ac` có test id rõ trước `qa:*`; (b) một story sửa `qa:e2e` là bài toán khác hẳn (không có test AC để gắn) — cân nhắc loại `qa:*` khỏi hàng đợi sửa tự động, để người quyết (ghi P2, đo khi có bench). Sổ toàn dự án sau 5 vòng: 46 → 44 VERIFIED (hai hành vi bị lượt trượt làm đỏ, chưa ai chữa — chính là việc của vòng kế nếu mở lại).

**QĐ B6 (chủ đầu tư, 2026-09-06 11:00) — hiện thực cùng ngày, unit xanh, chưa chạy lại vòng thật:** (a) `qa:*` cấp dự án **ra khỏi** hàng đợi sửa tự động (`improve.repair_queue`), thứ tự REOPENED → `ac` → `fr`/`nfr` → `mockup`; lý do dừng nêu gap ngoài hàng đợi. (b) **Không nới V3**: cách RP-02/03/04 đóng gap (gắn mã story vào test có sẵn) không được tính — test vẫn xanh khi bỏ phần cài đặt của story sửa; story sửa phải tạo/đổi một hành vi chứng minh bằng đối chứng nop (story body nói rõ). (c) Gap chỉ thiếu truy vết (test có sẵn đã chứng minh đủ) **không** thành story sửa: người rà soát trả `[bế tắc] truy vết: <test id>`, harness xử lý như sửa siêu dữ liệu — `aisdlc evidence <AC> --link TEST --why …` ghi `traceability.json`, sổ vẫn đòi test ấy xanh ở ứng viên landed, nguồn ghi `via: traceability`. Hệ quả cho B1: ba vòng "+1" đầu **không tái hiện được** dưới luật mới (chúng là (b)); số đo R3 hợp lệ còn lại là: dừng đúng điều kiện, chi phí/vòng, 0 hồi quy — gain thật phải đo lại trên gap loại (a)/(c) sau v0.1.0 (một smoke loop nếu rẻ).

**Chưa đo:** đường cong nhiều vòng hơn (còn 15 gap; kỳ vọng phẳng khi tới các gap cần route/màn hình của story sau), và B3/B5/B6 trên `par`.

**Chưa đo (B1):** e9 EPIC-01 với agent thật — ΔVERIFIED, REOPENED → 0,
chi phí/vòng so với story trung bình. Rủi ro đã thấy trước: 18 GAP của e9
01-01/02/03 cùng một gốc (vitest không in tên test) — story sửa cho
`AC-STORY-01-01-1` có `write_scope` của 01-01, còn chỗ sửa là cấu hình
reporter ngoài phạm vi → kỳ vọng dừng ở (5) và trả người; đó là kết cục
đúng của thiết kế, và là thứ R10 (planner agent) mới nới được.

**R9 — baseline trước khi sửa: hiện thực, unit xanh, chưa đo trên agent
thật.** (2026-09-06)

* `implement.run_baseline` chạy `tools.test` của dự án ở HEAD worktree
  **trước phiên developer đầu tiên** và ghi `tool_run test:baseline` với
  `detail.baseline=True`, `detail.parent` (SHA HEAD lúc chạy, rỗng nếu
  không đọc được), `detail.red_before` (test đã đỏ sẵn), tên test theo
  `harness/testlog.py` (thêm `skipped_ids` — bỏ qua không phải xanh) và
  `duration_ms` của sự kiện. **Không** mang `detail.candidate`: ứng viên
  chưa đóng băng. Tái dùng `run_tool` + `tools.record` (công khai hoá
  `_record`, thêm `name`/`extra`), không có đường ghi thứ hai.
* Hai chỗ **lệch** so với câu chữ §2 R9, cả hai có lý do đo được:
  1. Tên bản ghi là `test:baseline`, không phải `test` + cờ. Guard
     `completion`, `tdd.red_before_green`, mục "tiêu chí có test", sổ R2
     (`_observe_tests` chỉ nhận `name == "test"`) và `report` đều đọc
     `tool_run test` như "lần test của lượt": một baseline đỏ sẵn (test
     của story khác đang hỏng) sẽ chặn Stop tới hết lượt (lớp E trong
     `FAILURE-TAXONOMY`), làm TDD "đỏ trước xanh" đạt oan, và bị sổ quy
     thành hồi quy do story này gây ra — trước khi nó viết một dòng. Đổi
     tên thì không chỗ nào phải thêm điều kiện lọc.
  2. Chạy **một lần mỗi story** (trong `implement_story`, trước vòng lượt),
     không phải mỗi lượt trong `run_attempt`. Mỗi lượt thì lượt 2 lấy ứng
     viên lượt 1 làm mốc: test lượt 1 vừa làm đỏ thành "đỏ sẵn", lượt 2
     xoá nó là qua cổng sạch. Mốc là trạng thái trước khi story chạm vào,
     và chi phí là +1 lần chạy test mỗi story (B8 nói mỗi lượt — rẻ hơn).
* Cổng thêm mục **không làm đỏ test có sẵn** (`gate._baseline_check`, ngay
  sau mục "test"): test xanh ở baseline mà đỏ hoặc **mất** ở lần test mới
  nhất mang đúng `detail.candidate` → ✗ nêu đúng tên (tối đa 5 tên + số
  còn lại). Mất test cũng là ✗: story chưa có chỗ khai "xoá test", nên
  không suy được thì không cho qua và nói rõ vì sao. Kết cục khi không so
  được, theo bất biến: chưa khai lệnh test hoặc reporter không in tên → ○
  chưa cấu hình (không đạt, không chặn, phải hiện); baseline hoặc lần test
  ứng viên **không chạy được** → ⚠ không chạy được (chặn với lý do môi
  trường); tắt bởi `verify.baseline` hoặc harness không ghi baseline nào
  (chạy tay, nhật ký cũ) → – không áp dụng, có lý do. Test đỏ sẵn ở
  baseline: ✅ kèm "n test đã đỏ sẵn, không tính: …". Danh sách bị cắt ở
  `MAX_IDS` = 500 thì chỉ so đỏ, không kết luận "mất" — nói ra.
* Hồi quy vào feedback lượt sau qua đường có sẵn: `gate.feedback()` liệt
  kê mục ✗ kèm `detail`, nên tên test hồi quy nằm trong mục "Lượt trước
  chưa đạt" của prompt developer lượt kế — có test chứng minh.
* Knob `verify.baseline` (bool, mặc định `true`) — tắt khi bộ test quá
  chậm; tắt thì harness vẫn ghi một `test:baseline` mang `disabled` để
  cổng nói "tắt bởi cấu hình", không im.
* **Số đo trên test giả** (`tests/test_implement.py::TestBaselineTruocKhiSua`,
  bộ test giả in dạng `pytest -v` từ một tệp developer giả ghi đè): baseline
  10 xanh → sau lượt 9 xanh + `test_10` đỏ → cổng ✗ nêu đúng
  `tests/test_a.py::test_10`, không nêu `test_9`; 10 xanh + `test_11` mới
  đỏ → mục này ✅, mục "test" ✗ (TDD); baseline 9 xanh + `test_10` đỏ sẵn và
  vẫn đỏ → ✅, `red_before = [test_10]`; xoá `test_10` → ✗ "mất 1 test";
  hai lượt thử → đúng 1 `test:baseline` + 2 `test`; tắt knob → 1 lần chạy
  test thay vì 2, mục cổng –. Cổng: 12 phép ở `tests/test_gate.py`. Bộ
  đầy đủ: **1 341 test, OK** (skipped 56; 171 phép của gate/implement/
  testlog/config/candidate chạy 865 s vì mỗi `run_tool` đi qua Docker).
* **Chưa đo (B8 nửa `par`):** thời gian baseline thật trên `par`/e9 (bộ
  `node --test` ~1 s, vitest e9 lâu hơn — `duration_ms` đã có chỗ ghi), và
  liệu tên test hồi quy trong feedback có làm giảm số lượt so với "test
  đỏ" chung chung hay không. Sổ R2 **cố ý** không đọc `test:baseline`: nó
  là quan sát về bản cha, đã có trong bằng chứng của story trước.

### R2 — Sổ hành vi (`control/ledger.py`) · **B0 hồi cứu, 0 agent**

Hiện thực: `control/ledger.py` là **phép chiếu** từ `evidence/` — không có
sự kiện nào chỉ nó ghi được, xoá `ledger.json` rồi dựng lại phải ra đúng
cái cũ (trừ `loops[]`, xem R7). `build(artifact_root)` đọc mọi `evidence/*.jsonl`, sắp theo
`(at, story, seq)` — `seq` chỉ có nghĩa **trong** một tệp — rồi suy trạng
thái bằng code. Bốn nguồn: tên test ở `tool_run test` (qua
`control/acceptance.py`) → `AC-<story>-<i>`; `covers` của story →
`FR-x`/`NFR-x`; `tool_run` tên `qa:<kind>` → `qa:<kind>`; `mockup_map` →
`mockup:<màn>`. Lịch sử chỉ ghi khi **đổi** trạng thái (e9 có ~100 lần chạy
× ~280 tên test; ghi mọi quan sát thì sổ to hơn bằng chứng nó chiếu ra) —
kết quả: `ledger.json` 57 KB cho 4,3 MB `evidence/`, tức 1,3 %; dựng lại mất
1,1 s.
`harness/observe.py` thêm loại `BEHAVIOR` + `EvidenceStore.behavior(...)`
để pha sau ghi thêm nguồn — sổ đọc cả hai, và không ghi cũng không mất gì.

Hai luật chống kết tội oan, cả hai đo được: (1) lần chạy test **không đọc
được tên** là GAP với lý do, không phải "đạt" — cùng luật với cổng; (2) một
lần chạy chỉ chấm tiêu chí của story khác **khi thực sự thấy test của story
ấy**, nên bộ test chạy một phần không biến story không liên quan thành hồi quy.

| Kho | Hành vi | VERIFIED | GAP | REOPENED (hiện tại) | Gap đã đóng | Lần hồi quy | **Hồi quy liên story** |
|---|---|---|---|---|---|---|---|
| e9 `_bmad-output` (6 story có bằng chứng / 18 trong chỉ mục) | 49 | 31 | 18 | 0 | 47 | 19 | **6** |
| `par` (5 story) | 16 | 1 | 15 | 0 | 0 | 0 | 0 |

e9 theo loại: 39 `ac` · 4 `fr` · 4 `qa` · 2 `mockup` (0 `nfr` — PRD e9 không
có NFR nào được story `covers`).

**REOPENED thật, có nguồn** (hành vi xanh ở story A, đỏ lại trong bằng chứng
của story B ≠ A — đúng con số HoH đo 17/81 ở Fusepoint):

| Hành vi | Xanh ở | Đỏ lại ở |
|---|---|---|
| `AC-STORY-01-04-1` | STORY-01-04 | STORY-01-05#1 |
| `AC-STORY-01-04-3` | STORY-01-04 | STORY-01-05#1 |
| `FR-4` | STORY-01-04 | STORY-01-05#1 |
| `AC-STORY-01-04-1` | STORY-01-05 | STORY-01-06#1 |
| `AC-STORY-01-04-3` | STORY-01-05 | STORY-01-06#1 |
| `FR-4` | STORY-01-05 | STORY-01-06#1 |

Nguồn của cả hai lần: cùng một test đỏ,
`src/store/notes.test.ts > Đọc danh sách theo cửa sổ, không quét toàn kho
(AC-STORY-01-04-1, AC-STORY-01-04-3, AR-7, AR-9)` — `aisdlc evidence
AC-STORY-01-04-1` in ra đúng chuỗi gap → verified → reopened → verified →
reopened → verified kèm tên test của từng bước.

Đọc được ba điều mà báo cáo hôm qua không nói được:

1. **STORY-01-05 và STORY-01-06 mỗi story làm đỏ tiêu chí của STORY-01-04**
   ở lượt đầu, rồi tự sửa trong cùng lượt. Cả hai story vẫn qua cổng và vẫn
   `done`; hồi quy chỉ tồn tại *giữa chừng* và **không để lại dấu vết nào**
   trong `ACCEPTANCE-REPORT` cũ. Đây chính là gap §1.3 #3.
2. **STORY-01-01/02/03 không có một tiêu chí nào được xác minh** (18 GAP,
   lý do đồng nhất: `vitest` reporter mặc định không in tên test). Ba story
   `done` với 0/7, 0/7, 0/4 tiêu chí có bằng chứng — trước sổ này con số ấy
   nằm trong ô `?/n` của báo cáo và không ai cộng lại. `par` cũng vậy: 15/16
   hành vi GAP, chỉ `qa:fake-tests` xanh.
3. Tổng 19 lần hồi quy, nhưng **13 trong số đó là đỏ-lại trong chính lượt
   của story mình** — TDD bình thường, không phải hồi quy. Vì thế sổ tách
   `reopen_events` khỏi `cross_reopens`; chỉ số thứ hai mới so được với HoH.

Hai lỗi quy kết oan **bị chính B0 bắt** và đã sửa trước khi chốt số: (a)
`regressed_by` từng ghi story *sở hữu* tiêu chí thay vì story *làm hỏng* nó
— nay `observe()` tách `story` (quan sát) khỏi `owner` (sở hữu); (b) trạng
thái `FR-x` từng đọc `ok` của **cả lần chạy**, nên một lần chạy đỏ vì story
khác biến `FR-1`/`FR-11` của STORY-01-05 thành hồi quy — nay yêu cầu chỉ đỏ
khi **tiêu chí của chính nó** đỏ. Con số trước khi sửa là 36 lần / 8 liên
story; sau khi sửa là 19 / 6. VERIFIED và GAP không đổi.

Chưa suy được từ bằng chứng hôm nay: **candidate rỗng cho mọi hành vi** (R1
đang làm ở luồng khác) — nên `ledger.json` ghi `candidate: ""` và cột
candidate của `INDEX.md` là `—`. AC-(c) của R2 ("không hành vi nào VERIFIED
mà không có candidate") **chưa đạt được** và chỉ đạt sau R1; sổ đã sẵn chỗ
(`detail.candidate` đọc ở mọi sự kiện, rỗng là hợp lệ với bằng chứng cũ).

### R6 — Progressive disclosure (chỉ mục + `aisdlc evidence`)

`Ledger.index()` sinh `_bmad-output/INDEX.md`: **một dòng mỗi story**
(trạng thái · candidate 7 ký tự · V/G/R · đường dẫn evidence) + một dòng mỗi
epic. e9: 23 dòng cho 18 story / 5 epic; `par`: 8 dòng cho 5 story / 3 epic.
`build_context` thêm slot `index` (nguồn `ledger`) = **lát cắt epic chứa
story**, trần `context.max_index_chars` (mặc định 2000) — e9 EPIC-01 là 8
dòng / 497 ký tự, tức ~3,7 % prompt developer hôm nay (13,5k), trong ngưỡng
+15 % của B5. Lịch sử **không** vào prompt: `aisdlc evidence <story|hành vi>`
in đường đời đầy đủ khi cần, và ghi `note:evidence_lookup` như `doc_lookup`.
`story-implement` lên v4 với mục "Trạng thái epic".

### R7 — Metrics cải tiến liên tục

`Ledger.metrics()` + phần 5 của `ACCEPTANCE-REPORT`: *verified capability
growth* (số hành vi duy nhất từng VERIFIED theo thời gian — e9 31 điểm),
*reopened* (19 lần · tỷ lệ 0,61 trên hành vi từng xác minh · 6 liên story),
*resolved gaps* (47), và *marginal improvement* = (ΔVERIFIED − ΔREOPENED)/$
giữa hai mốc `loops[]` (`Ledger.snapshot(label, cost)`). Không có chi phí thì
`marginal` là `None`, không phải 0 — không mẫu số thì không có tỷ số.
Trên e9 hôm nay `loops[]` rỗng: các lượt chạy cũ không chốt mốc nào, nên cột
biên chỉ có số từ R3 trở đi. B6 đạt phần "bảng có số"; phần "marginal" phải
đợi vòng đầu tiên của R3.

`loops[]` là phần **duy nhất** của sổ không suy được từ bằng chứng (mốc và
chi phí của một vòng là quyết định của người điều phối, không nằm trong
`evidence/`), nên `build()` mang nó sang từ sổ cũ. Không làm thế thì một lần
`aisdlc report` — vốn chiếu lại sổ mỗi lần chạy — sẽ xoá sạch mốc mà vòng R3
vừa chốt; có test riêng cho đúng điều này.

**Quyết định sau B5 (2026-09-06 06:25):** hạ mặc định `context.max_preservation_chars` 1 500 → 1 200 để Δ developer về ≈ +15 %; chưa đo lại trên agent thật — story kế trên e9 sẽ cho số.
