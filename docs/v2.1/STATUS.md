# AISEF 2.1 — Bảng trạng thái đã kiểm chứng, backlog, bằng chứng kiểm thử

Nhánh `v2.1/foundation` (gốc `610a593` = master = 2.0.0 + tài liệu), bản vá `release/v2.0.1-prep`. Mỗi dòng: phát hiện →
bằng chứng trên mã 2.0 → reproducer → tác động → sửa (commit) → tiêu chí nghiệm thu → trạng thái. "Đo" = chạy thật trên
610a593; "đọc mã" = chưa đo, chỉ đọc; nguồn phát hiện: báo cáo 360° (`docs/DANH-GIA-360-V2.0-2026-10-06.md`) và đề xuất
cải tiến của chủ dự án.

**"XONG" trong các bảng dưới = đã sửa và có test offline (mức M3) trừ khi ghi khác; không có nghĩa A–E hoàn thành.** Mức
đầy đủ (module / tích hợp / offline / công cụ thật / live / chặn) cho từng hạng mục: [REPORT.md](REPORT.md) §2.

## 1. Ưu tiên A — an toàn, toàn vẹn bằng chứng, phát hành được

| # | Phát hiện | Bằng chứng 2.0 | Reproducer | Tác động | Sửa | Nghiệm thu | Trạng thái |
|---|---|---|---|---|---|---|---|
| A1 | `.pth` do mã test ghi chạy trong probe | **đo**: chạy trên 610a593, `.pth` thực thi trong probe pc2 | `test_v21_identity.PthChannel` (2.1), `test_v201_venvs` (2.0.1) | cao: kênh tới controller giữ khoá HMAC | 2.1: `-S` + interpreter của kernel `919a271`; 2.0.1: hai venv `c0ec1a5` | `.pth` không bao giờ chạy trong probe; verdict không đổi | **XONG**; còn lại: giả mạo cùng user (V2-05) |
| A2 | `RUN.json` sửa riêng vẫn VERIFIED | **đo** | `test_v21_verify` (4 FAIL + 2 ERROR trên 2.0) | cao | `ad78ce7` (+ usage `d622e71`) | mọi giả mạo bị bác; viết lại nhất quán bị bác khi có anchor | **XONG** |
| A3 | bundle/settings sai kiểu → traceback hoặc đọc sai | **đo** | `test_v21_inputs` (8 FAIL + 12 ERROR) | trung bình | `106f72d` | mã thoát 2 + đường dẫn JSON | **XONG** |
| A4 | endpoint `http://localhost.evil…` lọt | **đo** | `test_v21_inputs.Endpoint` | trung bình | `106f72d` | host loopback phân tích thật | **XONG** |
| A5 | `--check` báo sai "không có baseline" khi repo có khoá git của editor | **đo** | `RepositoryRefusal` | thấp | `106f72d` | `--check` clone như lượt chạy; lý do B4 thật | **XONG** |
| A6 | preflight gửi lại khoá API tới đích redirect | **đo** (`['Bearer sk-demo…']` tới đích) | `test_v21_transport.Redirect` | cao | `b029236` | 3xx = OPAQUE, khoá không rời đi | **XONG** |
| A7 | luồng phiên chỉ bị che khi kết thúc bình thường | **đo** | `test_v21_transport.Redaction` | cao | `b029236` | ngắt giữa chừng vẫn không còn bí mật | **XONG** |
| A8 | `git diff` lỗi → InvariantError kết thúc cả lượt | đọc mã | `test_v21_orchestration.DiffFailure` | trung bình | `51c5241` + `4ea4276` (bằng chứng tĩnh của repo bắt lỗi nhãn) | RESOURCE_ACQUISITION_FAILED, ENVIRONMENT, retry | **XONG** |
| A9 | công cụ phát hành cứng 2.0.0 | đọc mã | `test_v21_release_lane` | trung bình (không phát hành nổi 2.0.1) | `aa3c18a` | theo phiên bản; bản ghi 2.0.0 giữ tên | **XONG** |
| A10 | metadata PyPI nói về 1.x; không có LICENSE; link repo private | 360 | `packaging_check` + METADATA của wheel | thấp–TB | `b819a57` | wheel mang `License-Expression: MIT`, LICENSE | **XONG**; link tương đối của README trên PyPI: **CHẶN** (chủ dự án chọn nơi đăng tài liệu) |
| A11 | bản vá phát hành được | — | suite đầy đủ trên `c0ec1a5` + cài sạch wheel | — | `release/v2.0.1-prep` | build + `packaging_check` PASS; cài sạch: `--check` ready, `--verify` REFUTED không traceback | **CHUẨN BỊ** (`f006d3d`), **chưa đủ điều kiện phát hành**: suite trên `f006d3d` — REPORT §5; test bản ghi phái sinh đỏ ⇒ [RED-SUITE.md](RED-SUITE.md); CI/staging/RC freeze/Q0–Q5/tag/PyPI: **CHẶN** (của chủ dự án) |

## 2. Ưu tiên B–E

| # | Phát hiện | Bằng chứng 2.0 | Reproducer / test | Sửa | Trạng thái |
|---|---|---|---|---|---|
| B1 | PRESERVE chỉ kiểm sau merge (V21-38) | **đo** smoke #2 seq 387–393 | `test_v21_orchestration.PreserveAtCandidate`, ORCH_9/DIAG_2/c2 conformance | `91a8968` | **XONG** |
| B2 | kiểm lại cây tích hợp khi nhánh đích dịch | đọc mã: post-merge reprove đã có | ORCH_9 (main dịch dưới candidate sạch ⇒ INTEGRATION) | — (test) | **ĐÃ KIỂM**, không cần sửa |
| B3 | contract regex từ chối sai (V21-37) | **đo** smoke #2; tái hiện trên reference | `test_v21_python_imports` | `06d4e62` | lớp mới **XONG**; contract sửa: **CHẶN** (chủ dự án chọn A/B và duyệt) |
| B4 | không tạo bundle được nếu thiếu API nội bộ | 360 usability | `test_v21_bundle_tools` (init→seal→approve→lint→`--check` ready) | `620bde7` | **XONG** |
| B5 | độ phủ theo mệnh đề | 360: 30/54 mệnh đề | `lint.coverage` | `620bde7` | **XONG**, giới hạn: chỉ mệnh đề tác giả khai |
| B6 | ba danh tính | **đo**: một `-S` làm đỏ 37 test | `test_v21_identity` | `919a271`, `06d4e62` | **XONG**; phê chuẩn V2-007: **CHẶN** (chủ dự án) |
| B7 | hash AST ≠ tương đương hành vi | thiết kế | test hiệu chuẩn theo byte | ADR-2 | **XONG** (không tuyên bố tương đương) |
| C1 | finding của review không bao giờ được kiểm; 5 lỗi đã ship | **đo** session smoke #2 | `test_v21_review` (5 CONFIRMED trên dạng lỗi, NOT_REPRODUCED trên reference) | `e897437` | **XONG** |
| C2 | bộ chuyển OCR có phiên bản | — | `test_v21_review_ocr` (10) | `e897437`, `390f07c`, `929598f`, `51f2eb5` | nối vào `aisef run` (`review.finder: "ocr"`); nhị phân thật v1.12.12 + mô hình kịch bản qua CLI thật: **M4**; mô hình thật: **CHƯA** (ngân sách) |
| C3 | vòng sửa có biên, có ngân sách | — | ProductPath (2 lần REVIEW_FINDING → ROLLBACK) | `e897437` | **XONG** |
| D1 | resume kiểm danh tính, không commit trùng, giữ run cũ, dòng dõi | — | `test_v21_continue_usage.Continue` | `d622e71`, `7e0aac0`, `872e83c`, `b72e51e` | nối tiếp + claim theo thế hệ + đối soát với git: **M4** (SIGKILL thật qua CLI thật, REPORT §4.2); resume tại chỗ: **CHƯA** (cần format journal mới) |
| D2 | request/token/cache/thời gian/retry/chi phí; không biết ≠ 0 | 360: "mọi bước giá 0" | `Usage` | `d622e71` | **XONG** |
| D3 | phát hiện lặp không tiến triển | 360: một phiên 80 lượt không sửa gì | `no_progress` | `d622e71` | **XONG** (chỉ báo cáo; taxonomy quyết định) |
| D4 | gói ngữ cảnh kiểu MiMo | — | — | — | **CHƯA** (chưa có bằng chứng cần) |
| E1 | thí nghiệm có đối chứng | 360: không có nhánh đối chứng V2 | `test_v21_experiment` | `a29e82b` | harness + replay **XONG** |
| E2 | chiến dịch trả tiền | — | — | [EXPERIMENT-PLAN.md](EXPERIMENT-PLAN.md) | **CHẶN** (ngân sách: đề nghị 140 USD) |

## 3. Backlog theo thứ tự (phụ thuộc → tiêu chí nghiệm thu)

| ID | Việc | Phụ thuộc | Nghiệm thu |
|---|---|---|---|
| B-01 | Chủ dự án phê chuẩn ARCHITECTURE-EXCEPTION-V2-007 (ADR-2) | — | bản ghi phê duyệt do chủ dự án ký |
| B-02 | Phát hành 2.0.1: đẩy `release/v2.0.1-prep`, CI 14 job, staging SHA256SUMS, `release_rc --freeze`, Q0–Q5 theo charter, quyết định phát hành, tag (chủ dự án) | — | gate `v2_release_gate 2.0.1` PASS; byte PyPI = byte RC |
| B-03 | Vòng tái thẩm định 2.1 (§4): inventory thẩm quyền 2.1, kiểm định checker, mutation có mục tiêu, acceptance 2.1 tiền đăng ký — **bản ghi mới**, không ghi đè | B-01 | suite đầy đủ xanh trên ứng viên 2.1 |
| B-04 | Chọn bản nháp S-10-a (A hoặc B) và duyệt | — | LedgerLock không còn rollback sai trên dạng smoke #2 |
| B-05 | OCR trong `aisef run`: đã nối (M4); còn một lượt với mô hình thật | ngân sách | coverage COMPLETE trên một lượt thật; finding vào triage |
| B-06 | Đo chất lượng reproducer của reviewer (precision/recall trên replay smoke #2) | ngân sách | số đo + phương sai |
| B-07 | Sandbox V2-05 (danh mục OpenSandbox) | — | developer không đọc được ngoài workspace (đo) |
| B-08 | Xem lại K-NOWORK-001 (review cho story không có thay đổi) | chủ dự án | quyết định ghi lại |
| B-09 | Chiến dịch E2 | ngân sách | báo cáo theo EXPERIMENT-PLAN |
| B-10 | Nơi đăng tài liệu công khai; link tuyệt đối trên PyPI | chủ dự án | không link 404 |
| B-11 | README/USAGE/landing cho 2.1 khi phát hành | B-02/B-03 | mọi tuyên bố có bằng chứng |

## 4. Bằng chứng kiểm thử (máy: macOS Darwin 25.5, arm64, Python 3.14.7; suite hermetic: `env -i`, HOME/XDG mới, không có `opencode` trên PATH)

Xem [REPORT.md](REPORT.md) §5 — kết quả suite đầy đủ theo commit; từng test đỏ: [RED-SUITE.md](RED-SUITE.md).
