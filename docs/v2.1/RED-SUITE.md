# AISEF 2.1 — Từng test đỏ: kỳ vọng / thực tế / artifact / căn cứ phân loại

Nhánh `v2.1/foundation`. Mỗi lỗi dưới đây được **chạy lại riêng** và đối chiếu digest (không dùng một nhãn chung "stale
evidence"). Đo trên `4fd070a` (lỗi) và `2cad415` (digest); `51f2eb5`/`2cad415` không đổi kết quả nào ở đây
(`review_ocr.py` không là mục tiêu mutation, không có dòng thẩm quyền). Suite đầy đủ trên HEAD cuối: [REPORT.md](REPORT.md)
§5. Công cụ tạo bản ứng viên: `validation/v21/candidate_evidence.py OUT` — OUT **ngoài repo** (đo: một bộ đặt trong
repo làm `gen_migration_table` đếm bản sao P5-PROPOSAL là evidence ⇒ bảng P6 drift, và `v1_evidence_guard` báo thay đổi
evidence được bảo vệ; bộ đầu tiên `a399224` vì thế bị loại, không dùng số liệu của nó).

**Mọi consumer đọc đường dẫn cố định** (`ROOT/<REL>`): các test, q0/q2, `c2_orchestration_repair`, và — qua job `tests` của
workflow phát hành — đường phát hành. Một bản ứng viên ở chỗ khác không được ai đọc (đã kiểm:
`tests/test_v21_candidate_evidence.py`). Thay bản niêm phong là quyết định của chủ dự án.

## A. Nguyên nhân chung của năm artifact: digest của engine admission

`aisef2/plan/static_admission.py` đổi ở `919a271` (V2-007: check 9 dùng `executing(probe)`, dòng 25 và 267–269). Engine
digest băm `ENGINE_SOURCES = ("plan/static_admission.py", "plan/obligation.py")`: `a33f2aee…` (610a593) → `7668fc35…`. Mọi
`result_digest` chứa nó đổi theo; **verdict của các check (admitted, passed) không đổi**.

Đo thêm trên bản ứng viên `b72e51e` (bảng cuối tệp): digest của cả bốn probe cũng đổi (nguồn probe đổi ở `919a271` —
interpreter của kernel, `-I -S`, V2-007 — và `06d4e62` — `python_imports` trong `file_artifact`), và vì `semantic_hash` gồm `probe_digest` (`aisef2/product/spec.py:68`) nên semantic hash và spec
id của **59 spec** và plan hash đổi theo. Phần này **được ánh xạ ngược theo luật có sẵn** (`validation/qualification/rebind.py`:
124 danh tính của bản ứng viên acceptance); phần **không** được dung sai là engine digest. *(Sửa lại hai nhận định trước:
REPORT cũ quy A2/A4 cho digest probe; bản RED-SUITE trước ghi "chỉ engine digest khác" — đúng sau ánh xạ ngược cho A2/A3, sai
cho A4 vì `c2_plan_correction.check` so nguyên bản ghi.)*

| Test | Thực tế (rút gọn) | Artifact | Công cụ / đường ra | Khác ở đâu | Tái lập |
|---|---|---|---|---|---|
| `p0.test_checker_calibration` (checker `p2_evidence`) | `clean_passes False`: "P2-STATIC-ADMISSION.json is stale" | `closure-evidence/v2/P2-STATIC-ADMISSION.json` | `validation/v2/p2_evidence.py` `static_admission()`; `main()` ghi cả năm bản P2 ở đường cố định | `engine.digest`, `well_formed_plan.result_digest` (00f93384… → 0abb4768…); không gì khác | cơ học; bản P2 niêm phong ⇒ chủ dự án |
| `test_p5_plan_v22_proposal.Record.test_P5_8`; `test_c2_p5_acceptance.KernelProvenance`, `.ProbeIdentityRebinding` | "…PROPOSAL.json is not what the authoring aid derives"; `current False`; khác `identities.admission_engine_digest`, `static_admission.*.{engine,result}_digest` | `closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json` | `validation/qualification/p10_contracts.py` `record()` (:946), `--write` đường cố định (:62–63) | engine digest; `result_digest` 4bc6b1c2→06001eee, 1ce2c40a→ab2c40b0 — không dung sai. Được dung sai: cây/aid (provenance), digest probe ⇒ 59 spec ⇒ plan hash, proposal digest (ánh xạ ngược) | **bất biến theo luật** (blob phải bằng ứng viên đã chấp nhận 3ac9b8c; `p5_acceptance.proposal_currency` chỉ dung sai provenance/aid) ⇒ ruling |
| `test_c2_p5_acceptance.Acceptance` | 3 vấn đề: proposal (trên), `verification.identities.proposal_record_current`, `verification.admission.{engine,result}_digest` | `closure-evidence/v2/cycle2/C2-P5-ACCEPTANCE.json` | `validation/qualification/p5_acceptance.py` `record()` (:509) | như trên | **ghi một lần** (`--write` từ chối tệp có sẵn) ⇒ ruling |
| `test_c2_delivery_experiment.PlanCorrection` | "…PLAN-V2.2-CORRECTION-1.json is not what this tree derives" | `closure-evidence/v2/cycle2/PLAN-V2.2-CORRECTION-1.json` | `validation/qualification/c2_plan_correction.py` `record()` (:124), `--write` cố định (:31) | engine digest + 5 result digest; **và** semantic hash + spec id của 59 spec, spec id của 8 obligation dời, hai plan hash (`check()` so nguyên bản ghi, không ánh xạ ngược) | cơ học nhưng lan: bị K-NOWORK-001 `BOUND`, ghim bởi preregistration của delivery experiment |

## B. Bản ghi mutation (`p0.test_checker_calibration`, checker `mutation`)

"…::_cycle: target changed since the mutation run — re-run it", v.v. `validation/v2/mutation.py` so `source_digest` **của cả
tệp module** với `source_sha256` của từng target ⇒ một sửa bất kỳ trong module làm mọi target của module cũ. **320 target, 7
482 mutant** trên bốn bản ghi (`P2-MUTATION`, `P6-MUTATION`, `cycle2/P1-MUTATION`, `release/S2-MUTATION`); thân hàm đổi thật
(so AST với 610a593): 26 target — 294 target không đổi AST (so sánh của tôi; công cụ không chấp nhận nó, và hàm được gọi /
test diệt đã đổi). Ước thời gian (từ trạng thái worker trong `S2-MUTATION-SUMMARY.json`, ~15,5 s/mutant khi chạy song
song): **~32 giờ một worker**; chiến dịch 2.0 dùng ~10 lượt worker trong ~2 ngày. Survivor mới trên mã đổi cần test diệt mới —
không cơ học. **Không thể chỉ chạy lại**: `mutation.py run` ghi lại vào bản ghi cố định, `s2_mutation_record --check` đòi tệp
đúng như lịch sử worker dẫn xuất, và bằng chứng tái dùng đòi target giống từng byte. Đường đúng của công cụ là một **phase
mới** trong `RECORDS`/`SUPERSEDED` — thay đổi mã cần chủ dự án quyết. Module mới của 2.1 (`app/lineage.py`, `usage.py`,
`review_ocr.py`, `review_verify.py`, `bundle_cli.py`) **chưa là mục tiêu mutation** — một khoảng trống phủ, không phải test đỏ.

## C. `closure-evidence/v2/release/AUTHORITY-INVENTORY.json` (định địa chỉ theo nội dung)

Thẩm quyền chưa liệt kê, đúng hai: `aisef2/app/bundle_cli.py::migrate` (gọi `compile_spec`, PRODUCT_TRUTH) và
`aisef2/app/review_verify.py::verify` (gọi `run_probe`/`bound_result`, PRODUCT_TRUTH), cả hai ngoài `run_story`. Không dòng
nào khác đổi; 66 → 68 dòng active. Năm test của `test_no_dual_authority` (Inventory ×2, ReleaseInventory ×3) và hai subtest
checker (`old_path_audit`, `release_inventory`) đỏ vì đúng hai dòng này. Công cụ: `validation/qualification/release_inventory.py
--write` (đường cố định). Sau đó phải sửa tay `INVENTORY_SHA256` và delta phát hành trong `test_no_dual_authority.py:76–77`;
**chấp nhận hai đường PRODUCT_TRUTH mới là quyết định thẩm quyền của chủ dự án.**

## D. `closure-evidence/v2/Q0-CHECKER-CALIBRATION.json`

`test_every_checker_is_calibrated_and_the_committed_record_is_current`: bốn "NOT calibrated" (mutation, p2_evidence,
old_path_audit, release_inventory); 48/52 checker hiệu chuẩn. Chỉ tái lập được **sau** B, A1, C; và sẽ không giống từng byte
(danh sách quan sát của known-bad `old_path_audit` có thêm hai thẩm quyền mới).

## E. `closure-evidence/v2/cycle2/K-NOWORK-001-REHEARSAL.json`

`['aisef2/orchestrate/story_runner.py changed since the record']` — `story_runner.py` 30c64e6b… → db394816… (`51c5241`,
`4ea4276`, `919a271`, `91a8968` V21-38). Công cụ chạy lại các case dưới kernel trước và kernel này (~13 phút). Verdict
"REPRODUCED AND CORRECTED" có còn đúng trên kernel 2.1 không: xem bản ứng viên (REPORT.md §5). Làm sau A4 (bị BOUND).

## F. `closure-evidence/v2/cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json` (lịch sử)

`test_c2_orchestration_conformance.Record.test_15`: (d) `review.py`, `calibration.py`, `file_artifact.py` "changed since the
base and is not in the record"; (e) danh tính khác ngoài thay đổi probe của bản phát hành; (f) tóm tắt mutation khác.
`release_differences` chỉ dung sai danh sách đổi của V2.0. **Không viết lại bản ghi lịch sử**; cần một ruling nêu thay đổi
2.1, sau A2/A3 và B.

## G. `test_p9_reproduction.MultiStory.test_Q5_12` — không phải so bản ghi

`({'S0': ['COMMIT']}, ['EXTRA_MODEL_CALL: the script has no DEVELOPER_IMPLEMENT answer for request 4', …])`. Kỳ vọng nằm
trong mã: item `post-merge-regression` của `validation/qualification/q5.py:195–199`. V21-38 (`91a8968`) chứng minh PRESERVE
ở candidate ⇒ CONTRACT_UNSATISFIED (DEVELOPER) ⇒ retry ⇒ một yêu cầu developer mà script không có. Sửa = đổi item corpus
và kỳ vọng ⇒ đổi oracle (và `harness_digest`) — quyết định của chủ dự án. `release/Q5-RC2/CORPUS.json` (corpus 2.0 đóng
băng) không bao giờ sửa.

## Thứ tự khi chủ dự án ra quyết định

1. Luật cho engine digest (A2/A3) hoặc bản ghi v2.1 mới. 2. Thiết kế phase mutation và lượt chạy dài (B).
3. Tái lập P2 (A1) và inventory với sha ghim + test (C). 4. Hiệu chuẩn Q0 (D). 5. Plan correction (A4), rồi K-NOWORK (E).
6. Danh sách dung sai của conformance (F). 7. Item corpus Q5 (G).

## Nhánh 2.0.1 (`release/v2.0.1-prep`, HEAD `f006d3d`)

Suite đầy đủ trên đúng `f006d3d` (09:43 → 11:00 UTC, chờ khoá nặng tới 10:21): **Ran 5497, 4 FAIL, 80 skip** — chưa đủ
điều kiện phát hành. Không dùng kết quả của `c0ec1a5` (8 FAIL) cho commit này; lượt trên `5e46fe9` bị huỷ, không có kết
quả. Cả bốn là so bản ghi niêm phong, cùng nhóm với nhánh 2.1:

| Test | Thực tế | Nhóm |
|---|---|---|
| `p0.test_checker_calibration` `test_every_checker_has_a_committed_fixture…` (checker `mutation`) | `clean_passes False` | B |
| `p0.test_checker_calibration` `test_every_checker_is_calibrated…` | "mutation is NOT calibrated: … `aisef2/app/bundle.py::Project.order`: target changed since the mutation run — re-run it", `bundle.py::load`, … | B (D theo sau) |
| `test_c2_k_nowork_001.Record` | `['aisef2/orchestrate/story_runner.py changed since the record']` | E |
| `test_c2_orchestration_conformance.Record.test_15` | `['(f) the mutation summary differs from the record']` | F |

Bản vá này không đổi engine admission nên nhóm A không xuất hiện; không có thẩm quyền mới nên C không xuất hiện.

## Bộ evidence ứng viên trên `b72e51e`

`python3 -P validation/v21/candidate_evidence.py $SP/candidates/b72e51e2` trong worktree tách rời đúng `b72e51e` (cây sạch,
`tree_dirty: false`), macOS 25.5 arm64, Python 3.14.7, dưới khoá nặng, 18:00 → 18:19 (giờ máy). Ngoài repo; không phải bản
niêm phong, không được test hay cổng phát hành nào đọc. Bộ đầu tiên (`a399224`, viết trong repo) bị loại.

| Bản ghi | sha256 ứng viên | niêm phong | Khác (số đường JSON) | Ý nghĩa |
|---|---|---|---|---|
| P2-STATIC-ADMISSION | `aaf99bad63c0…` | `c31658f748a7…` | 2: `engine.digest`, `well_formed_plan.result_digest` | đúng A1 |
| P5-PLAN-V2.2-PROPOSAL | `772dbab21626…` | `bbb7138bda94…` | 190: 59×3 spec (probe digest, semantic hash, spec id), 4 digest probe, engine/result digest, cây, aid, plan hash, proposal digest | A2 |
| C2-P5-ACCEPTANCE | `47c5d11ecb77…` | `69c23b49f393…` | 202; **verdict ứng viên `PROBLEMS`**: proposal không hiện hành (A2) và guard `checker_calibration` exit 1 (B, C: hai thẩm quyền UNENUMERATED); ánh xạ ngược 124 danh tính probe thành công | A3 — ghi một lần |
| PLAN-V2.2-CORRECTION-1 | `44127db7a2ef…` | `365ebacfc8d2…` | 138 (như A4 ở trên) | A4 |
| AUTHORITY-INVENTORY | `9eaf87693c07…` | `6dba7d62cae2…` | 2: 245 → 247 dòng, `summary.ACTIVE_V2_AUTHORITY` | đúng C |
| Q0-CHECKER-CALIBRATION | `009b90f3bf33…` | `be035016c42b…` | 15: 48/52 hiệu chuẩn; không hiệu chuẩn: `mutation`, `p2_evidence`, `old_path_audit`, `release_inventory` | D — chỉ xanh sau B, A1, C |
| K-NOWORK-001-REHEARSAL | `c7cad8b62f51…` | `aa494ca02360…` | 6: `story_runner.py` bound, kernel digest, ba plan hash, thời gian | E — **verdict vẫn "REPRODUCED AND CORRECTED"** trên kernel 2.1 |

Không sinh: mutation (B), conformance (F), corpus Q5 (G) — lý do trong `CANDIDATE-MANIFEST.json`.

