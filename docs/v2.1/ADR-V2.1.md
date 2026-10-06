# AISEF 2.1 — Quyết định kiến trúc (nhánh `v2.1/foundation`, 2026-10-06)

Nguồn: chỉ thị của chủ dự án trong phiên 2026-10-06 (đề xuất cải tiến + báo cáo 360°). Mỗi quyết định nêu: vấn đề đã đo,
quyết định, phương án bị loại, hệ quả, và cái **không** tuyên bố. Giữ nguyên: một đường quyết định, taxonomy owner, journal
format 3, ràng buộc candidate↔evidence, chính sách commit/rollback. Không viết lại khung, không nhập orchestrator ngoài.

---

## ADR-1 — Probe chạy trên interpreter của kernel với `-I -S`; test của developer chạy venv riêng

**Đã đo (2.0.0, 610a593):** một `.pth` mà mã test ghi vào site-packages của `<out>/probe-python` được **thực thi bên trong**
probe `python_callable_v2` (cờ `-I -B` không tắt `site`) — kênh để mã ứng viên chạm controller giữ khoá HMAC.
Reproducer: `tests/v2/test_v21_identity.py::PthChannel` (cùng kịch bản chạy trên 610a593 cho `True`).

**Quyết định.** Mọi lần khởi chạy của probe đang hoạt động (controller, agent, subject của `cli_invocation`,
`python_callable_v2`, `process_effect`) thêm `-S`. `ExecutionEnv.interpreter` = `sys.executable` (ngoài thư mục lượt
chạy). Test của developer chạy `<out>/test-python` (`StoryInputs.test_interpreter`). RunSpec ghi cả `python` (của probe)
và `test-python`.

**Loại:** băm cây venv trước mỗi probe (TOCTOU, mã test chạy cùng user); chỉ tách venv (đường dẫn đoán được, mã test biết
`sys.executable` của chính nó). **Probe Cycle-1 (`python_callable.py`, không còn hoạt động) không đổi** — digest của nó là
lịch sử đã niêm phong.

**Không tuyên bố:** đây **không** là sandbox. Mã test chạy dưới user của người vận hành và vẫn có thể sửa interpreter của
máy hoặc gói aisef đã cài; sandbox OS (V2-05) là việc riêng.

## ADR-2 — Ba danh tính tách rời (ARCHITECTURE-EXCEPTION-V2-007)

**Vấn đề.** 2.0.0: `probe_digest` = sha256 các tệp nguồn probe; spec id, semantic hash, plan, approval-qua-plan, bản ghi
hiệu chuẩn đều buộc vào nó. Sửa một chú thích trong probe ⇒ đổi mọi spec id ⇒ mọi bundle phải buộc lại, mọi bản ghi phái
sinh đỏ (đo: chỉ thêm `-S` làm đỏ 37 test).

**Quyết định.** Ba danh tính:

| Danh tính | Định nghĩa | Ai buộc vào |
|---|---|---|
| ngữ nghĩa contract | `contract_hash` (không đổi) | approval |
| năng lực probe | `DIGEST = sha256(json([PROBE_ID, CAPABILITY_VERSION, CLASSES]))` | spec, semantic hash, plan |
| byte đang chạy | `EXECUTION_DIGEST` = sha256 các nguồn probe (công thức cũ) | hàng hiệu chuẩn (check 9), RunSpec |

Sửa byte mà không đổi điều quan sát ⇒ spec/approval/plan giữ nguyên, nhưng **phải chứng minh lại hiệu chuẩn** (test
`ThreeIdentities.test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now` đỏ cho tới khi
`release_calibration.py --write` chạy lại). Đổi điều quan sát (lớp mới, ngữ pháp stimulus, luật verdict) ⇒ tăng
`CAPABILITY_VERSION` bằng tay (file_artifact đã lên 2 khi thêm `python_imports`).

**Không tuyên bố:** digest khớp **không** chứng minh hai lần thực thi tương đương hành vi; băm AST cũng không. Bằng chứng là
tương phản hiệu chuẩn trên fixture đã commit. Kỷ luật tăng version là trách nhiệm review, không máy nào kiểm.

**Di trú:** spec id của 2.0.0 đổi một lần → `aisef bundle migrate` (LedgerLock: 59 spec, 67 obligation, admit 9/9, không
duyệt lại). Bằng chứng cũ giữ nguyên byte.

**Trạng thái của ngoại lệ:** ÁP DỤNG trên nhánh theo chỉ thị của chủ dự án ngày 2026-10-06 ("tách ba danh tính");
**chưa có phê duyệt chính thức dạng bản ghi** — không tạo bản ghi phê duyệt giả. Chủ dự án cần phê chuẩn trước khi 2.1 phát
hành (backlog B-01).

## ADR-3 — `--verify` dựng lại mọi trường có thể nâng verdict; manifest + anchor

**Đã đo:** sửa riêng `RUN.json` (bỏ `budget_stop`, đặt PASS) vẫn VERIFIED trên 2.0.0. **Quyết định:** outcome lấy từ
journal; settings buộc vào journal bằng cách dựng lại `runspec_hash`; chi tiêu dựng lại từ luồng phiên + ledger preflight;
story bắt đầu mà không kết thúc = bị từ chối; trường chỉ có trong record **chỉ được hạ** verdict. `EVIDENCE.json` băm record
(JSON chuẩn hoá), journal, mọi phiên, preflight; digest của nó là **anchor** in ra cho người vận hành giữ ngoài thư mục;
`--verify --expect-anchor` bác bỏ cả việc viết lại nhất quán toàn thư mục. Không đổi format journal.
**Không tuyên bố:** không có anchor thì verify chỉ chứng minh *nhất quán*, không chứng minh *xác thực*.

## ADR-4 — PRESERVE của story đã commit được chứng minh ở candidate (V21-38)

Lỗi hồi quy do developer gây ra được tìm **trước merge**: CONTRACT_UNSATISFIED, owner DEVELOPER, retry được, tiêu chí được
đưa vào prompt retry. Chứng minh lại sau merge vẫn giữ, cho thay đổi do chính merge gây ra (INTEGRATION). Chi phí: mỗi spec
PRESERVE được chứng minh hai lần mỗi story.

## ADR-5 — `python_imports`: import đếm bằng cú pháp (V21-37)

Lớp mới của `file_artifact` (`ast`, loại import tương đối, tệp không parse ⇒ không có số đếm). Hợp đồng LedgerLock sửa đổi
chỉ là **bản nháp chưa duyệt**, hai phương án (A: danh sách §10 trừ `unittest` vì bất biến IX; B: toàn stdlib) — chủ dự án
chọn và duyệt. **Không thấy:** `importlib.import_module`/`__import__`.

## ADR-6 — Định dạng soạn bundle + công cụ (mục tiêu 3)

`aisef-v2-authoring/1` = bundle trừ những gì kernel dẫn xuất. `seal` dùng chính constructor của kernel; **không bao giờ
duyệt**; `approve` một contract mỗi lệnh, `human:<tên>`. **Không tuyên bố:** công cụ không biết ai gõ lệnh — giữ bundle và
lệnh ngoài tầm developer agent.

## ADR-7 — Review: tìm thì tự do, chặn chỉ khi probe tái hiện

Finding có thể kèm **reproducer** (hành vi mệnh đề yêu cầu, theo ngữ pháp probe); AISEF chạy bằng probe của chính nó, đã
hiệu chuẩn, ở candidate. CONFIRMED ⇔ probe bác hành vi đã nêu — chính là "thẩm quyền chứng thực" D-002 đòi. Chính sách
`fix-loop`: CONFIRMED ≥ `min_severity` chặn (REVIEW_FINDING, giới hạn REVIEW của taxonomy làm vòng sửa có biên), nội dung vào
prompt retry. Settings **không có** `review` ⇒ luật 2.0.0 (advisory), ghi rõ trong record — không đổi hành vi âm thầm.
OCR (v1.12.12, Apache-2.0) chỉ là bên tìm; coverage do AISEF kiểm. **Không tuyên bố:** xác nhận chứng minh candidate không
làm điều finding nói — không chứng minh finding đọc đúng yêu cầu (đã đo trong test).

## ADR-8 — Nối tiếp thay cho resume tại chỗ; chi phí không biết là `null`

Journal có schema đóng; resume tại chỗ cần đổi format. Thay vào đó `aisef bundle continue`: baseline = commit cuối journal
xác nhận (merge chưa commit bị loại và báo); obligation đã giao thành story VERIFY mà kernel chứng minh lại, không gọi
developer (một lượt review mà luật K-NOWORK-001 của chủ dự án giữ — không đổi); `aisef run --parent` ghi dòng dõi. Thư
mục lượt cũ không bị sửa. `usage`: token theo lớp, request, retry, thời gian; tiền chỉ từ bảng giá trong settings.

## ADR-9 — Thí nghiệm: niêm phong trước khi tiêu

Manifest niêm phong, cặp chỉ khác một biến, cánh trực tiếp do harness chụp, evaluator ẩn + quét rò rỉ, replay offline.
Không có lượt trả tiền nào khi chưa có ngân sách duyệt ([EXPERIMENT-PLAN.md](EXPERIMENT-PLAN.md)).

## ADR-10 — Làn phát hành theo phiên bản; lịch sử bằng chứng không bao giờ ghi đè

`release_rc`/`v2_release_gate`/`release_calibration` theo phiên bản pyproject; bản ghi 2.0.0 giữ tên. Nhánh này là
`2.1.0.dev0` (bản build không bao giờ tự nhận là 2.0.0). Bản ghi mới được đánh số (`…-PROBE-CALIBRATIONS-2.json`), không ghi
đè. Các test buộc bản ghi phái sinh vào cây hiện tại (proposal P5, rebind, acceptance C2-P5, kiểm định checker, mutation,
inventory thẩm quyền) **đỏ có chủ đích** tới vòng tái thẩm định 2.1 — xem [STATUS.md](STATUS.md) §4.
