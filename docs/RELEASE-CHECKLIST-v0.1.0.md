# Checklist phát hành v0.1.0 — gói `aisef` (module/lệnh `aisdlc`)

Mỗi dòng là một điều kiện của Definition of Done (quyết định chủ đầu tư
2026-09-06 11:00, `docs/RELEASE-PLAN-v0.1.0.md` §0 mục 10) kèm **lệnh hoặc
tệp** để người ký kiểm lại. Không dòng nào ✅ bằng cảm giác. Trạng thái cập
nhật lần cuối: **xem dòng "Cập nhật" cuối tệp**.

| # | Điều kiện | Cách kiểm | Trạng thái |
|---|---|---|---|
| 1 | Suite đơn vị 100 % xanh, **lặp lại được không cần Docker** | `python3 -m unittest discover -s tests -q` | ✅ 06/09 14:18 trên master `cb35ad9`: **1 671 test, 191 s, OK**, 17 skip có tên (10 `AISDLC_TEST_DOCKER` · 2 cổng phát hành · 2 dogfood · 2 hợp quy · 1 bench) |
| 2 | Test Docker/hợp quy sandbox riêng xanh | `AISDLC_TEST_DOCKER=1 python3 -m unittest tests.test_sandbox tests.test_tools -q` | ✅ 06/09 14:21: **88 test, 93 s, OK** (2 skip); S1–S5 Docker 5/5 đo sáng 06/09 |
| 3 | Hợp quy Claude không ô ✗, bảng ≤ 14 ngày | `docs/CONFORMANCE.md`; cổng ở dòng 9 đọc bảng bằng code | ✅ C1–C10 Claude 10/10 (06/09, $1,66). **C11/C12 hoãn**: mã và unit test xong ở nhánh `worktree-agent-ada8e46…` nhưng phép chạy thật mới xong C11(a)/(b) thì hết credit — không gộp vào master vì thêm phép vào bảng sẽ làm cổng đòi đủ 12 cột |
| 4 | `par` đạt mốc dogfood | `AISDLC_DOGFOOD=1 python3 -m unittest tests.dogfood -q` (đo 06/09: 3/3, $5,79 ≤ 2 × $3,14) | ✅ |
| 5 | e9 EPIC-01 7/7, QA đạt, `pre-deploy --epic EPIC-01` đạt hoặc chỉ waiver tường minh cho loại UNRUNNABLE | `AISDLC_ACCEPTANCE=<e9> AISDLC_RELEASE=1 python3 -m unittest tests.test_release_gate`; `e9/_bmad-output/pre-deploy-report.json` (`passed`, `scope`, `waivers`), `approvals/pre-deploy.json` | ✅ ĐẠT 11:29 06/09, cổng duyệt theo phạm vi; miễn có lý do: sit/api-contract/uat (không áp dụng), mutation, image-scan (không chạy được) |
| 6 | Wheel/sdist hợp lệ, cài venv sạch → `setup` → `doctor` | `uv build && uvx twine check dist/*`; venv sạch `pip install dist/aisef-0.1.0-py3-none-any.whl` → `aisdlc setup` → `aisdlc doctor` | ✅ 12:1x 06/09 (`doctor` "✅ sẵn sàng") |
| 7 | README / CHANGELOG / STATUS / SOLUTION khớp mã | `python3 -m unittest tests.test_meta tests.test_docs -q` (CLI, knob, mục cổng, STEPS, slot đọc từ mã) | ✅ xanh ở `d64dd90`; chạy lại sau A2 |
| 8 | Known limitations ghi rõ | README "Giới hạn đã biết của v0.1.0"; CHANGELOG "Khi nâng cấp" | ✅ (danh sách bên dưới) |
| 9 | Cổng phát hành trả 0 | `AISDLC_RELEASE=1 AISDLC_ACCEPTANCE=<e9> python3 -m unittest tests.test_release_gate -q` | ✅ 06/09 14:2x: 2 test OK (bảng hợp quy đủ + mới; nghiệm thu e9 đạt, duyệt đúng bản, miễn có lý do) |
| 10 | Tag `v0.1.0` → `release.yml` publish (trusted publisher) → `pip install aisef==0.1.0` venv sạch | chủ đầu tư tag sau khi nhận checklist này; tôi kiểm venv sạch | ⬜ **không tag trước khi 1–9 xanh** |

## Known limitations còn lại (khai trong README)

1. **Phạm vi nghiệm thu dogfood = e9 EPIC-01** (7 story). EPIC-02..05 (16 story) chưa chạy; báo cáo ghi "ngoài phạm vi", không phải "xong". e9 là corpus nghiệm thu, chưa phải sản phẩm nghiệm thu đủ.
2. **OpenCode hạng hai**: hợp quy 9/10 (C9 model từ chối — không kết luận), chưa có đầu ra máy đọc ổn định; claim phát hành dựa trên Claude Code.
3. **S1 — agent trong container chưa có cách ly credential** (blocked, không workaround): V1 chạy agent trên host, kiểm định trong container; `doctor`/`pre-deploy` nêu tên bảo đảm thiếu.
4. **`mutation` và `image-scan` ở môi trường nghiệm thu KHÔNG CHẠY ĐƯỢC** (stryker chưa cài; docker scout đòi đăng nhập, trivy/grype vắng) — miễn có lý do ở `verify.waiver_reason`, hiện ◇, không thành ✅. Kiểm định của e9 chạy **ngoài Docker** với waiver có lý do (node_modules macOS trong container Linux); lần cách ly thật là CI Linux.
5. **`skills.offer`/`skills.inline` tắt** (A/B không thấy gain); **`repo_map` tắt** (`context.max_repo_map_chars = 0`, A/B T8 hoãn sau v0.1.0); **bench run client thật** (T9) hoãn.
6. **`coverage`**: harness đọc số từ runner; e9 đo 84,16 % < `coverage.min` 0,85 — story kế của e9 sẽ ✗ đúng; dự án chưa bật `--coverage` thì mục cổng ○, không phải đạt.
7. **Vòng improve (R3)**: ba vòng "+1" đo trên e9 đóng gap bằng cách gắn mã vào test có sẵn — luật mới (V3 nop control, QĐ B6) không tính; gain thật của R3 phải đo lại sau v0.1.0. Hàng đợi tự động không nhận `qa:*`.
8. **V12 egress allowlist, V13, R10/R11** chưa làm (sau v0.1.0).

## Kết quả hai phép chạy thật của C11 (chưa đủ để vào bảng)

| Ca | Agent làm gì | Cổng | Ghi chú |
|---|---|---|---|
| C11(a) gắn mã vào test có sẵn | đổi tên test có sẵn để mang mã tiêu chí | ✗ **test có kiểm được story** (nop V3, cấp 1) | R9 nhận đúng đây là đổi tên, không phải mất test; **reviewer model `pass`, 0 mục** — cổng máy bắt, người máy không |
| C11(b) test không khẳng định | — | ✗ **test có kiểm được story**, không phải `test thật` | Chưa soi xong agent viết gì; ca này chưa kết luận |
| C11(c), C12 | chưa chạy (hết credit) | — | — |

Bài học sơ bộ: hai lớp phòng thủ độc lập (cổng máy vs model-judge) không thay
nhau được — dữ liệu cho ADR-005 V10.

Cập nhật: 2026-09-06 14:3x — dòng 1, 2, 9 xanh; còn dòng 10 (tag) chờ chủ đầu tư.
