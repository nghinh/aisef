# AISEF 2.1 — Báo cáo cuối phiên (2026-10-06)

Phạm vi: chỉ thị lead-engineer của chủ dự án ngày 2026-10-06 (đề xuất cải tiến + báo cáo 360°). Nhánh `v2.1/foundation`
(gốc `610a593` = master = 2.0.0 + tài liệu) và bản vá `release/v2.0.1-prep`. **Không có gì được đẩy, gắn tag, phát hành
hay chạy trả tiền.** Chi tiết từng phát hiện: [STATUS.md](STATUS.md); quyết định: [ADR-V2.1.md](ADR-V2.1.md); sử dụng và di
trú: [USAGE-2.1.md](USAGE-2.1.md); nguồn upstream: [UPSTREAM-RESEARCH.md](UPSTREAM-RESEARCH.md); thí nghiệm:
[EXPERIMENT-PLAN.md](EXPERIMENT-PLAN.md).

## 1. Đã triển khai và đã kiểm chứng

| Mục tiêu | Việc | Commit | Kiểm chứng (test, đỏ trên 2.0 → xanh) |
|---|---|---|---|
| 2 developer không giả được verifier/bằng chứng | `.pth` không chạy trong probe (`-I -S`, interpreter của kernel; test của developer ở `test-python`) | `919a271` | `test_v21_identity.PthChannel` — trên 2.0 `.pth` chạy trong probe |
| 2 | `--verify` dựng lại mọi trường nâng verdict; `EVIDENCE.json` + anchor | `ad78ce7`, `d622e71` | `test_v21_verify` (4 FAIL + 2 ERROR trên 2.0) |
| 2 | preflight không theo redirect; luồng phiên bị che dù ngắt giữa chừng | `b029236` | `test_v21_transport` (khoá tới đích redirect trên 2.0) |
| 1 | bundle/settings sai kiểu: mã thoát 2 + đường dẫn JSON; endpoint loopback thật; `--check` clone như lượt chạy | `106f72d` | `test_v21_inputs` (8 FAIL + 12 ERROR trên 2.0) |
| 1 | `git diff` lỗi = RESOURCE_ACQUISITION_FAILED (ENVIRONMENT), không kết thúc lượt chạy | `51c5241`, `4ea4276` | `test_v21_orchestration.DiffFailure` |
| 1 | PRESERVE của story đã commit được chứng minh ở candidate (V21-38) | `91a8968` | `PreserveAtCandidate`, ORCH_9 |
| 1 | `python_imports`: import đếm bằng cú pháp (V21-37) | `06d4e62` | `test_v21_python_imports` — regex cũ bác sai trên reference |
| 1 | review: finding chỉ chặn khi probe của AISEF tái hiện; vòng sửa có biên; OCR v1.12.12 ghim | `e897437` | `test_v21_review` (5 lỗi đã ship trong smoke #2: CONFIRMED trên dạng lỗi, NOT_REPRODUCED trên reference), `test_v21_review_ocr` |
| 3 người ngoài tạo bundle | `aisef bundle init/seal/approve/lint/explain/migrate`, schema soạn, 2 ví dụ đóng gói | `620bde7`, `919a271` | `test_v21_bundle_tools` (init→seal→approve→lint→`--check` ready, không API nội bộ) |
| 4 resume + chi phí | `aisef bundle continue` + `aisef run --parent` (record `continues`); `usage` (không biết = `null`, không bao giờ 0); `no_progress` chỉ báo cáo | `d622e71`, `6634d6d` | `test_v21_continue_usage` |
| 5 so với agent trực tiếp | harness thí nghiệm: manifest niêm phong, cặp một biến, cánh trực tiếp, evaluator ẩn, quét rò rỉ, replay offline | `a29e82b` | `test_v21_experiment` |
| phát hành được | công cụ phát hành theo phiên bản; metadata 2.x; LICENSE MIT | `aa3c18a`, `b819a57` | `test_v21_release_lane`, `packaging_check` |
| danh tính | ba danh tính (ngữ nghĩa contract / năng lực probe / byte đang chạy) | `919a271`, `06d4e62`, `4d4c53a` | `test_v21_identity.ThreeIdentities`; bản ghi hiệu chuẩn mới `V2.1.0.dev0-PROBE-CALIBRATIONS{,-2}.json` (bản 2.0.0 không đổi) |
| bất biến tĩnh | ba vi phạm thật do suite đầy đủ bắt (bộ đếm retry phụ, tên `parent`, xoá trong test) | `6634d6d` | `test_invariants`, `test_destructive_authority` |

Giữ nguyên: một đường quyết định (`_attempt`), taxonomy owner, journal format 3 (không đổi schema), ràng buộc
candidate↔evidence, chính sách commit/rollback. Không nhập orchestrator ngoài; không thêm dependency runtime.

## 2. Chưa kiểm chứng (đã làm hoặc đã thiết kế, chưa đo)

- Bộ chuyển OCR chưa chạy với nhị phân `ocr` thật; chưa nối vào `aisef run` (B-05).
- Chất lượng reproducer do reviewer LLM viết (precision/recall) — cần replay có trả phí (B-06).
- Hiệu quả AISEF so với agent trực tiếp — harness xong, **không có số đo** (E2, B-09).
- Suite trên Windows/Linux cho nhánh 2.1 — chỉ chạy trên macOS; CI chưa chạy vì chưa đẩy nhánh.
- Resume tại chỗ (cần format journal mới) — thay bằng nối tiếp (ADR-8).
- Gói ngữ cảnh kiểu MiMo (D4) — không có bằng chứng cần.

## 3. Bằng chứng kiểm thử

Máy: macOS Darwin 25.5.0 arm64, Python 3.14.7 (`/opt/homebrew/bin/python3`). Suite đầy đủ chạy hermetic: worktree tách
rời đúng SHA, `env -i`, HOME/XDG mới, PATH không có thư mục chứa `opencode`, dưới khoá nặng toàn máy; bằng chứng
trước/sau về kho OpenCode thật của người vận hành (không đổi).

| Commit | Bắt đầu → kết thúc (UTC) | Kết quả | Ghi chú |
|---|---|---|---|
| `919a271` | 04:27 → 05:05 | Ran 5507, 62 F, 80 skip | trước `4d4c53a` (test buộc digest cũ) |
| `d622e71` | 05:12 → 05:51 | Ran 5550, 76 F + 2 E, 80 skip | phần lớn sửa ở `4d4c53a`, `6634d6d` |
| `6634d6d` | 06:31 → 07:09 (chờ khoá nặng từ 06:05) | Ran 5555, 18 F, 80 skip | HEAD của phần mã; cả 18 thuộc §3.1, không lỗi mã nào |
| `c0ec1a5` (2.0.1) | 05:52 → 06:30 (chờ khoá nặng từ 05:38) | Ran 5496, 8 F, 80 skip | 3 lỗi thật (hai bất biến tĩnh) sửa ở `5e46fe9`; 5 còn lại: §4 |

### 3.1 Test đỏ có chủ đích trên `6634d6d` — chờ vòng tái thẩm định 2.1 (B-03)

Không test nào bị bỏ, nới hay đổi oracle. Mỗi test dưới đây so một **bản ghi phái sinh đã niêm phong** (của 2.0.0 hoặc
Cycle 2) với cây hiện tại; cây 2.1 khác có chủ đích, nên bản ghi mới phải được viết trong vòng tái thẩm định, **không ghi
đè** bản ghi cũ.

| Test (số lỗi) | Bản ghi niêm phong | Vì sao cây 2.1 khác |
|---|---|---|
| `p0.test_checker_calibration` (5: `mutation`, `p2_evidence`, `old_path_audit`, `release_inventory`, record) | bản ghi mutation, `P2-STATIC-ADMISSION.json`, `AUTHORITY-INVENTORY.json` | mục tiêu mutation đổi (vd `static_admission._cycle`); check 9 theo execution digest; hai thẩm quyền mới |
| `test_no_dual_authority` (5: Inventory ×2, ReleaseInventory ×3) | `closure-evidence/v2/release/AUTHORITY-INVENTORY.json` (định địa chỉ theo nội dung) | thẩm quyền mới `aisef2/app/bundle_cli.py::migrate`, `aisef2/app/review_verify.py::verify` chưa có dòng |
| `test_c2_p5_acceptance` (3) + `test_p5_plan_v22_proposal` P5_8 (1) | `P5-PLAN-V2.2-PROPOSAL.json` | digest engine admission, cây `aisef2`, digest probe đổi |
| `test_c2_delivery_experiment.PlanCorrection` (1) | `PLAN-V2.2-CORRECTION-1.json` | dẫn xuất từ cây hiện tại (spec id theo ba danh tính) |
| `test_c2_k_nowork_001.Record` (1) | bản ghi K-NOWORK-001 | `story_runner.py` đổi (V21-38, DiffFailure) |
| `test_c2_orchestration_conformance.Record` test_15 (1) | bản ghi conformance | `review.py` đổi (detail của finding) |
| `test_p9_reproduction` Q5_12 (1) | corpus Q5 (`Q5-RC2/CORPUS.json`) | V21-38: hồi quy của S2 giờ bị bắt ở candidate (DEVELOPER, retry) ⇒ kernel xin thêm một câu trả lời developer mà script 2.0 không có. Corpus 2.1 cần item mới; corpus cũ không sửa |

Đã kiểm từng nhóm: lỗi nằm ở so sánh bản ghi, không ở hành vi (test hành vi tương ứng xanh: `test_v21_*`,
`test_invariants`, `test_destructive_authority`, `test_v2_005`, ORCH_9). Ba vi phạm bất biến thật mà suite trên
`d622e71` bắt đã được sửa ở `6634d6d`, không xếp vào đây.

## 4. Bản vá 2.0.1 (`release/v2.0.1-prep` = `c0ec1a5`) — chuẩn bị xong, chưa phát hành

- Nội dung: các sửa ưu tiên A không đổi danh tính (`3f1907a` … `deda047`) + `.pth` bằng **hai venv** (probe-python và
  test-python) — không đổi mã probe, nên spec id, bundle và approval của 2.0.0 không đổi. Phiên bản `2.0.1`, CHANGELOG
  ghi "unreleased".
- Build cục bộ (không phải bản RC): wheel `884a1163a08f2053d63d9fd881c99a0cbb7a08206a980b5ae3e5a0a4de1ce5a0`, sdist
  `7b1f55743ab8c9d46f0bc332b284d52616ad20d38a9dfee7b3864a6a826479ba`. `packaging_check` PASS. Cài sạch wheel vào venv mới:
  `aisef --version` 2.0.1, `--check` ready trên bundle mẫu, `--verify` của thư mục giả mạo REFUTED không traceback.
- Suite đầy đủ trên `c0ec1a5`: 8 lỗi. Ba lỗi là vi phạm bất biến tĩnh thật trong test mới (xoá tệp không có dòng ledger;
  ranh giới except mới của `run.py` chưa ghim) — sửa ở `5e46fe9`, có mutant kiểm chứng (probe chạy trên venv của test ⇒
  test đỏ). **Năm lỗi còn lại chặn phát hành 2.0.1**: chúng so bản ghi phái sinh đã niêm phong với kernel đã đổi —
  hiệu chuẩn checker ×3 (bản ghi mutation: mục tiêu đã đổi, ví dụ `aisef2/app/bundle.py::Project.order`), bản ghi
  K-NOWORK-001 (`story_runner.py` đổi), conformance test_15 (tóm tắt mutation). Job unit của CI sẽ đỏ cho tới khi các
  bản ghi này được lập lại bằng chính công cụ sinh của chúng (mutation có mục tiêu + tái lập bản ghi). Việc đó thay tệp
  ở đường dẫn cố định ⇒ cần chủ dự án cho phép (B-02); tôi không tự làm.
- Kho OpenCode thật trước/sau suite: chỉ `log/opencode.log` đổi mtime (ghi lúc 05:10:13 và 06:10:14 UTC — đúng một giờ,
  OpenCode.app của người vận hành đang chạy); `opencode.db` không đổi. Suite chạy với HOME riêng, PATH không có
  `opencode` ⇒ không do suite (suy luận từ nhịp một giờ, không đo trực tiếp tiến trình ghi).
- Còn lại (chủ dự án, B-02): đẩy nhánh, CI 14 job, staging SHA256SUMS, `release_rc --freeze`, Q0–Q5 theo charter, quyết
  định phát hành, tag `v2.0.1`. Build của CI mới là byte được phát hành; digest ở trên chỉ để đối chiếu.

## 5. Bị chặn — cần chủ dự án quyết định

| # | Quyết định | Vì sao tôi không tự làm | Đã chuẩn bị |
|---|---|---|---|
| B-01 | phê chuẩn ARCHITECTURE-EXCEPTION-V2-007 (ba danh tính) | không tạo phê duyệt giả | ADR-2, migrate, bản ghi hiệu chuẩn mới |
| B-02 | phát hành 2.0.1 — gồm cho phép lập lại 5 bản ghi phái sinh (§4) | publish/tag và thay bản ghi niêm phong là của chủ dự án | §4, `5e46fe9` |
| B-03 | mở vòng tái thẩm định 2.1 (sau B-01) | ghi bản ghi phái sinh mới là quyết định niêm phong | §3.1 |
| B-04 | chọn bản nháp S-10-a (A: §10 trừ `unittest`; B: toàn stdlib) và duyệt | approval là của con người | `drafts/LEDGERLOCK-BC-V22-S-10-a-r2.DRAFT.json` |
| B-08 | K-NOWORK-001: story không có thay đổi vẫn một lượt review (story CARRIED) | luật của chủ dự án | ghi trong ADR-8 |
| B-09 | ngân sách E2: đề nghị **140 USD** (pilot 18 lượt ≈ 67,7 USD giá cao điểm / 33,8 USD thấp điểm, ×2 dự phòng) | không chạy chiến dịch trả tiền khi chưa duyệt | EXPERIMENT-PLAN, settings mẫu đã qua `settings.load` |
| B-10 | nơi đăng tài liệu công khai (repo private ⇒ link tương đối trên PyPI 404) | quyền repository | metadata không còn link repo |
| — | dòng chủ sở hữu bản quyền trong `LICENSE` (hiện "The AISEF authors") | pháp lý | LICENSE MIT |

## 6. Không tuyên bố

- Không có sandbox: developer và mã test chạy dưới user của người vận hành; `-S` chặn `.pth`, không chặn việc sửa
  interpreter hay gói đã cài (V2-05, B-07).
- `--verify` không có anchor chỉ chứng minh **nhất quán**; anchor phải được giữ ngoài thư mục lượt chạy.
- Digest/AST khớp không chứng minh tương đương hành vi; tăng `CAPABILITY_VERSION` là kỷ luật review.
- Review CONFIRMED chứng minh candidate làm điều finding nêu, không chứng minh finding đọc đúng yêu cầu.
- Chưa có số đo nào cho thấy AISEF tốt hơn hay rẻ hơn agent chạy trực tiếp.
