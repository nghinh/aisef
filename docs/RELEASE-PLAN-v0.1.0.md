# Kế hoạch phát hành v0.1.0 — hiện trạng 06/09 12:00 và việc còn lại

Bản này trả lời ba câu: dự án đang ở đâu, còn gì trước khi phát hành, làm theo thứ tự nào. Mọi số có chỗ đọc lại: `docs/STATUS-2026-09-05.md`, `docs/ADR-004…md` §6, `docs/ADR-005…md` §9, `docs/CONFORMANCE.md`, `docs/SANDBOX-CONFORMANCE.md`, `CHANGELOG.md`, evidence e9/par trong scratchpad.

## 1. Hiện trạng

### 1.1 Framework (master `96f30ab`, 136 commit từ sáng 05/09)

| Mặt | Trạng thái |
|---|---|
| Kiến trúc | Sáu nhóm harness giữ nguyên (control · harness · phases · clients · kit · tests); CLI một lần, không daemon; agent trên host với hook, kiểm định trong Docker |
| Bất biến | Evidence-first, reviewer ≠ developer, bảo đảm phía harness, worktree cách ly, cổng người, phiên mới mỗi story, client không được tin — không bất biến nào bị nới trong hai ngày |
| Test đơn vị | 1 384 xanh ở mốc gộp ADR-004 đợt 2; sau đó thêm ≈ 200 test của đợt X (chưa chạy suite đầy đủ — mỗi luồng chỉ chạy module mình chạm) |
| Hợp quy client | C1–C10: Claude 10/10 ($1,66), OpenCode 9/10 (C9 model từ chối chạy tool — không kết luận); sandbox S1–S5: Docker 5/5, Local khai đúng 5 bảo đảm thiếu |
| Lỗi thật tìm bằng đo | 27, mỗi lỗi có test đỏ khi hoàn nguyên; 17/25 lỗi đầu là cổng/guard chấm sai — đây là động lực của ADR-005 |
| ADR-002 tri thức vận hành | xong, đo trên e9 |
| ADR-003 bàn giao/skills | xong phần đo; `skills.offer`/`inline` tắt vì không thấy gain (n=1) |
| ADR-004 (HoH) | R1–R9 + R13 hiện thực; R2/R5/R6/R7 ACCEPTED có số; R1/R4/R8/R9 đo trên agent thật; B0–B7 đo; vòng improve B1 5 vòng: +1/+1/+1 rồi −1/−2, dừng đúng `flat_loops` |
| ADR-005 (10 repo ngoài) | 7/8 luồng đợt 1 đã gộp: V1 scrub, V2 env allowlist + git credential, V3 nop control hai cấp, V4 `gate:input` + `aisdlc gate --replay`, V5 provider/guarantee, V6 QA sạch, V7 repo_map (tắt mặc định), V9 contract cổng 16 mục × 3 control, V11(A,B) tool output/exit_status, R13 `--repeat`; đang gộp: V8 bench (X7) |
| Tài liệu | SOLUTION đối chiếu mã có test meta (CLI, knob, mục cổng, STEPS, slot, guard); CHANGELOG v0.1.0 theo sáu nhóm; taxonomy 11 lớp |

### 1.2 Dogfood

| Dự án | Trạng thái | Chi phí |
|---|---|---|
| `par` (trong kho, `tests/dogfood`) | 3/3 story, mốc $3,14/story; mutation B3: hai cổng mới bắt hồi quy liên story, sổ REOPENED đúng thủ phạm | ≈ $25 tổng |
| `e9` (scratchpad) | EPIC-01 **7/7 done**; QA cấp dự án 6 loại ✅ ở `c4ac358`; sổ 44 VERIFIED · 16 GAP EPIC-01; EPIC-02..05 (11 story) **chưa chạy**; pre-deploy ✗ vì còn story chưa chạy + `mutation` không chạy được (môi trường) | ≈ $542 (story $496 + improve $46) |

### 1.3 Điều kiện phát hành (STATUS §5) — cập nhật

| Điều kiện | Hôm nay | Còn thiếu |
|---|---|---|
| 100 % unit xanh | ✅ ở 1 384; ⬜ sau đợt X | chạy suite đầy đủ một lần, một suite một lúc |
| `CONFORMANCE.md` ≤ 14 ngày, không ô ✗ | ✅ 06/09, C1–C10 | OpenCode C9 "không kết luận" ghi rõ là hạng hai — không chặn |
| `par` chạy lại đạt mốc | ✅ 3/3 $5,79 ≤ 2×$3,14 (dòng cũ trong STATUS ghi "chờ P0-1" đã lỗi thời) | cập nhật STATUS |
| `e9` EPIC-01 xong, báo cáo có TCCN → test id, accessibility không UNCONFIGURED | ✅ 7/7, QA ✅ | pre-deploy còn ✗ vì phạm vi kế hoạch là 5 epic — **cần quyết định phạm vi nghiệm thu** (mục 3, đợt C) |
| `pip install ai-sdlc` venv sạch → setup → doctor xanh | ◐ wheel + sdist build, twine PASS | tài khoản tổ chức PyPI + trusted publisher (việc của chủ đầu tư), tag, publish, kiểm venv sạch |

### 1.4 Vấn đề tồn tại còn mở (sau khi đóng những mục đã xong)

| # | Mức | Vấn đề | Đề xuất |
|---|---|---|---|
| P1-4 | P1 | `coverage` UNCONFIGURED ở mọi dự án thử | e9: thêm `--coverage` vào `tools.test`; đo một lượt story; nếu vẫn ○ thì ghi hướng dẫn, không chặn release |
| P1-7 | P1 | e9 chưa đóng băng thành kho hồi quy | V8 bench đã mine e9 (X7) — chốt khi gộp |
| P1-3 | đóng | A/B skills không thấy gain → giữ tắt (quyết định 2 của chủ đầu tư) | ghi vào STATUS là đã đóng |
| P1-6 | đóng | Tài liệu lệch mã | W11 sửa 14 chỗ + test meta |
| P1-13 | đóng | Không kiểm-lại được ứng viên | R13 `--verify-only --repeat` đã gộp; T5 chưa đo agent thật |
| P2-8..12, P2-14 | P2 | router capabilities, script skill lỗi, A/B script trong scratch, attempts, cổng cỡ agent-splitting, hiệu chuẩn láng giềng | sau phát hành |
| mới | P1 | Suite đơn vị phụ thuộc Docker: mỗi `run_tool` trong test cũ mở container thật (6–18 s/container) → suite 25–60 phút, nhạy tải | **FakeProvider mặc định cho unit test**, Docker chỉ ở test có đánh dấu (đợt A3) |
| mới | P1 | Vòng improve chọn gap `qa:*` cấp dự án → hai vòng âm | ưu tiên gap `ac` có test id; loại `qa:*` khỏi hàng đợi tự động (đợt B) |
| mới | P2 | Rate limit phiên làm 8 subagent chết cùng lúc; một luồng dựng tải nhân tạo mồ côi | quy tắc: ≤ 4 luồng song song, cấm tải nhân tạo (đã ghi memory) |
| S1 | blocked | Sandbox credential cho agent trong container | giữ blocked/degraded rõ ràng theo quyết định 4 |

## 2. Việc còn lại trước khi phát hành — tóm tắt

1. Đóng đợt X (còn X7), suite đầy đủ xanh, tài liệu khớp mã. **Chặn release.**
2. Suite hết phụ thuộc Docker (FakeProvider mặc định). **Chặn release** — vì "100 % unit xanh" phải lặp lại được trên máy không có Docker rảnh.
3. Quyết định phạm vi nghiệm thu e9 cho v0.1.0 (EPIC-01 hay cả 5 epic) và làm pre-deploy chấm đúng phạm vi ấy. **Chặn release** (cần quyết định của chủ đầu tư).
4. Số đo còn thiếu để các V/R lên ACCEPTED có số (không chặn release, nhưng nên có trước khi tuyên bố năng lực): T3/T4 (X3), T8 A/B repo map, T9 bench run, V10 C11/C12, T5 flake.
5. PyPI: tài khoản tổ chức + trusted publisher (chủ đầu tư), tag, publish, kiểm venv sạch. **Chặn release** (việc tay).

## 3. Kế hoạch chi tiết

Ước lượng theo giờ máy/agent; tiền là chi phí agent thật. Mỗi việc có tiêu chí xong đo được.

### Đợt A — đóng đợt X, suite ổn định (06/09 chiều, ≈ 4 giờ, ≈ $0)

| # | Việc | Ai | Xong khi |
|---|---|---|---|
| A1 | Gộp X7 (V8 bench) sau khi rebase và xanh module (X3 đã gộp 96f30ab) | tôi | master có 8/8; `git worktree list` = 1 |
| A2 | **FakeProvider mặc định cho unit test**: `tests/` dùng `sandbox.using(FakeProvider)`/`AISDLC_TEST_PROVIDER=fake`; test cần Docker thật đánh dấu `@docker` như hợp quy; giữ ≥ 8 test Docker thật (S1–S5 + tools/qa) | 1 subagent | suite đầy đủ < 5 phút trên máy không có Docker rảnh; số test không giảm; test đỏ khi hoàn nguyên FakeProvider |
| A3 | Suite đầy đủ trên master, **một suite một lúc**, load < 20 | tôi | `OK`, số test ghi vào STATUS §5 |
| A4 | `test_meta` khớp mã sau 8 luồng (CLI, knob, mục cổng 16, STEPS, slot, guard) | tôi | xanh; SOLUTION §10/§12/§13 cập nhật |
| A5 | STATUS §2.10 đợt X + §5, CHANGELOG chốt mục v0.1.0, artifact trạng thái | tôi | trang trạng thái cập nhật |

### Đợt B — số đo còn thiếu (06–07/09, ≈ 6 giờ, ≈ $80–110)

| # | Việc | Chi phí | Xong khi |
|---|---|---|---|
| B1 | T3 hồi cứu nop trên e9 + T4 replay trên evidence mới (X3 giao số) | $0 | ADR-005 §9 V3/V4 có số |
| B2 | V10 hợp quy C11 (agent cố gian 3 cách → cổng ✗) + C12 (story có lỗi cài sẵn → reviewer block, security ≥ high) | ≈ $3 | `CONFORMANCE.md` 12 phép hai client |
| B3 | T5 flake: dựng story trượt trên `par` (mutation có sẵn), `--verify-only --repeat 3` dưới tải có kiểm soát (không dùng `yes`, dùng chính suite Docker) | ≈ $4 | `flaky_ids` nêu tên, cổng ⚠ "không ổn định" |
| B4 | T8 A/B repo map: `par` ×3 + e9 01-02/03/06 × {0, 1500}, n ≥ 3/nhánh | ≈ $40 | quyết định bật (lượt −20 % trung vị, cổng cùng kết cục) hay giữ 0 |
| B5 | T9 bench run: task lỗi kho (≥ 20) × 1 client × attempts 3 | ≈ $30 | pass@1/pass@3, ổn định ≥ 80 %; mốc cho mọi A/B sau |
| B6 | Improve: ưu tiên gap `ac` có test id, loại `qa:*` khỏi hàng đợi tự động; **và** xử lý mâu thuẫn V3 × B1: ba vòng improve đầu đóng gap bằng cách *gắn mã vào test có sẵn* (RP-02/03/04), điều nop control (V3) nay chấm ✗ vì test ấy xanh cả khi không có mã của story → story sửa phải viết test mới mang mã, hoặc kế hoạch khai "chỉ gắn mã" (quyết định của chủ đầu tư); chạy lại 2 vòng trên e9 với luật mới | ≈ $20 | Δ ≥ 0 ở hai vòng; ADR-004 §6 R3 cập nhật |
| B7 | P1-4 coverage: e9 `tools.test` thêm `--coverage`, một story RP | ≈ $8 | mục coverage ✅ hoặc lý do rõ |

### Đợt C — nghiệm thu e9 cho v0.1.0 (cần quyết định chủ đầu tư)

Hai lựa chọn, tôi khuyến nghị **C-a**:

| | C-a: phạm vi v0.1.0 = EPIC-01 | C-b: cả 5 epic |
|---|---|---|
| Việc | thêm `aisdlc pre-deploy --epic E` (pre-deploy chấm "mọi story xong" trong phạm vi khai; story ngoài phạm vi liệt kê là "ngoài phạm vi nghiệm thu", không phải "chưa xong"); chạy qa → devsecops → pre-deploy → report cho EPIC-01 | chạy EPIC-02..05 (11 story) trên framework đã gộp, rồi nghiệm thu |
| Chi phí | ≈ $0 + 2 giờ | ≈ $400–600, 1–2 ngày máy, nhiều lượt trượt/chẻ story (cổng cỡ R5 chặn 3 story sát ngưỡng) |
| Bằng chứng cho release | 7/7 story có SHA, sổ hành vi, hợp quy, bench từ chính e9 | thêm app đầy đủ; giá trị đo thêm chủ yếu cho R5/B1 |
| Rủi ro | pre-deploy phải nói rõ phạm vi để không thành "cổng đã nới" | ngân sách/thời gian; không đổi điều kiện §5 |

`mutation` UNRUNNABLE (môi trường) ở e9: giữ waiver có lý do như Docker degraded, hoặc cài `stryker` cho e9 (≈ 1 giờ) — làm nếu còn thời gian.

### Đợt D — phát hành v0.1.0 (sau A, C; ≈ 3 giờ, việc tay của chủ đầu tư ở D3)

| # | Việc | Ai | Xong khi |
|---|---|---|---|
| D1 | Chốt CHANGELOG (mục "Khi nâng cấp": compile lại hook, duyệt lại `stories`/`readiness` một lần, `verify.baseline` +1 lần test, prompt version), README, phiên bản | tôi | test meta docs xanh |
| D2 | `uv build` + `twine check`; cài wheel vào venv sạch → `aisdlc setup` → `aisdlc doctor` xanh (không Docker: doctor phải nói "local provider, 5 bảo đảm thiếu", không đỏ) | tôi | log kèm trong STATUS |
| D3 | Tạo project PyPI (tài khoản tổ chức) + trusted publisher (GitHub Actions) | **chủ đầu tư** | publisher hiện trong PyPI |
| D4 | Cổng phát hành bằng lệnh: suite xanh + `CONFORMANCE.md` ≤ 14 ngày không ô ✗ + STATUS §5 đủ ✅ | tôi | lệnh trả 0 |
| D5 | `git tag v0.1.0`, workflow publish, kiểm `pip install ai-sdlc==0.1.0` venv sạch | chủ đầu tư tag, tôi kiểm | §5 dòng cuối ✅ |
| D6 | Trang trạng thái phát hành + ghi nhận giới hạn đã biết: OpenCode hạng hai, S1 blocked, mutation cần môi trường, repo_map tắt mặc định nếu A/B chưa thắng | tôi | artifact cập nhật |

### Đợt E — sau phát hành (không chặn)

V12 egress allowlist (spike S7), V13 theo điều kiện, R10 planner cho story sửa, R11 vòng nhiều epic, P2-8..14, OpenCode hạng nhất (`--format json` đã đo), e9 EPIC-02..05 làm bench liên tục, A/B skills n=3 bằng bench (ADR-003 #1).

## 4. Rủi ro và cách né

| Rủi ro | Đã thấy | Cách né |
|---|---|---|
| Rate limit phiên giết mọi subagent cùng lúc | 09:00 hôm nay, 8 luồng | ≤ 4 luồng song song; luồng commit sớm từng bước |
| Suite Docker chậm/nhạy tải (6–18 s/container) | cả ngày | A2 FakeProvider; một suite một lúc; container khác đã dừng |
| e2e timing trượt oan (lỗi 22) | 01-07 lần 2 | không chạy suite khi có lượt agent thật; R13 `--repeat` |
| Tải nhân tạo mồ côi | 07:20–09:03 | cấm subagent dựng tải; T5 dùng tải thật có kiểm soát |
| Cổng chấm sai lớp E/J | 17/27 lỗi | V3 nop + V4 replay + V9 qualification — đo trước khi tuyên bố |
| Nop control (V3) chặn cách vòng improve đang đóng gap (gắn mã vào test có sẵn) | hồi cứu T3: RP-02/03/04 sẽ ✗ | quyết định B6 trước khi chạy improve tiếp; không nới V3 |
| Phạm vi nghiệm thu mơ hồ | pre-deploy ✗ hiện nay | quyết định C-a/C-b trước D |

## 5. Lịch đề xuất

| Khi | Gì |
|---|---|
| 06/09 chiều | Đợt A (A1–A5) |
| 06/09 tối → 07/09 sáng | Đợt B (B1–B7), song song ≤ 3 luồng, một suite Docker một lúc |
| 07/09 | Quyết định C; làm C-a (2 giờ) hoặc bắt đầu C-b (1–2 ngày) |
| 07/09 chiều (nếu C-a) | Đợt D: D1–D2 tôi; D3 chủ đầu tư; D4–D6 |
| sau đó | Đợt E |

Ngân sách agent còn lại trong kế hoạch: đợt B ≈ $80–110; C-b nếu chọn ≈ $400–600; D ≈ $2 (hợp quy chạy lại nếu quá 14 ngày).
