# Campaign 9 — phạm vi đo mutation (cửa sổ sửa lỗi probe, bản ứng viên AISEF 2.1)

Lập ngày 2026-10-18 trên snapshot `69b0ea946922bcd209ffbf5a7bd943ad96080df7` (nhánh `v2.1/probe-window`; calibration probe vừa ghi một
lần trên cây mã cuối). Đây là **phạm vi**, chưa phải phép đo: chưa chạy runner, chưa quét T0, chưa ghi hàng đợi. Bản ứng viên chưa được
nghiệm thu; không push, tag, publish; không gọi provider.

Câu hỏi: trong 614 target của registry `V21_TARGETS` ở snapshot, target nào phải đo lại, target nào còn giữ kết quả đang đứng, vì sao —
đúng cách campaign 8 đã làm (`../campaign-8/README.md`, `SCOPE.json`, `tools/scope8.py`): mỗi target được so với **snapshot nơi kết quả của nó
được đo** bằng công cụ delta (`validation/qualification/v21_snapshot_delta.py`), không dùng snapshot khác.

## 1. Kết quả

| | target | mutant |
|---|---:|---:|
| Registry `V21_TARGETS` ở snapshot | **614** | **16.080** |
| **Đo ngay (`targets.txt`)** = đo lại 424 + mới 87 | **511** | **13.859** |
| — `REMEASURE`: kết quả cũ không còn là căn cứ | 424 | 11.942 |
| — `NEW`: chưa từng có kết quả (đăng ký trong cửa sổ) | 87 | 1.917 |
| `STANDS_PROVISIONAL`: luật delta để kết quả đứng, **tạm**, chờ read-set ở head cuối | 103 | 2.221 (2.207 KILLED + 14 SURVIVED đã kiểm toán) |
| `STANDS` (đứng không điều kiện) | 0 | 0 |
| Đã gỡ khỏi registry (`V21_RETIRED`) | 1 | — (`process_effect.py::HARNESS/guarded`: hàm không còn) |

Đếm hai lần, hai đường độc lập, cùng kết quả: `tools/scope9.py` (trong tiến trình) và `tools/verify9.py` (tiến trình mới, duyệt registry theo
thứ tự ngược, dựng lại vai trò chỉ từ `DELTA.json`); cả hai dùng `validation.v2.mutation.mutants` của runner, chỉ đọc. Lần thứ ba: đếm lại trên
cây `2c9488d` (cây registry trước commit snapshot) cho 614 target / 16.080 mutant (chỉ `aisef2/app/calibrations.py` đổi giữa hai cây). Khớp
với delta của snapshot cuối `5df323a` coi như một bảng: 511 đo lại / 103 đứng. Bốn bảng delta qua `v21_snapshot_delta.py --check` **ở `69b0ea9`** (cây trước khi thêm `campaign-9/`; ở commit sau đó `--check` báo stale theo thiết kế vì `closure-evidence/v2` nằm trong COPY, §5.4)
(tái dẫn xuất từng byte): PASS.

**Không có bất đồng** giữa kết luận của công cụ delta và bản ghi kết quả đang đứng (`disagreements: []` trong `SCOPE.json`). Phép kiểm cho
từng target cũ (527): `source_sha256` trong bản ghi worker của campaign mà kết quả thuộc về có bằng digest của tệp ở snapshot hay không
(delta nói "tệp đổi" ⇔ digest khác: 372/372 và 155/155), bộ kill tests và số mutant lúc đo có bằng của registry và bộ sinh hiện tại hay không
(cho 103 target đứng: có hết), và `MUTATION.json` (qua `MUTATION-SUMMARY.json` `provenance`) trích đúng một mục có cùng `source_sha256` và cùng
phân lớp (527/527).

## 2. Vì sao đo lại 511 target

| Lý do (một hàng cho mỗi target, theo thứ tự ưu tiên) | target | mutant |
|---|---:|---:|
| `NEW`: registry ở snapshot có, `campaign-8/SCOPE.json` không có | 87 | 1.917 |
| `REMEASURE`, **byte tệp target đổi** (13 tệp `aisef2/` có target cũ; cộng `diagnostics.py` và `catalog.py` chỉ có target mới là 15 tệp byte đổi của SCOPE-BEFORE-PIN; trong 372 có 64 target đổi cả bộ kill) | 372 | 10.043 |
| `REMEASURE`, tệp target và bộ kill không đổi nhưng **một tệp trong closure của kill tests đổi** (`tests/v2/ledgerlock_candidate.py` 42, `test_v21_identity.py` 39, `test_v21_continue_integrity.py` 24, `test_v21_review.py` 18, `test_v21_review_chain.py` 18, `test_s2_kills.py` 8, `test_v21_bundle_tools.py` 6, `test_v21_context_pack.py` 1) | 52 | 1.899 |
| **Cộng** | **511** | **13.859** |

Theo tệp (target đo / mutant đo; 103 target còn lại ở §3): `cli_invocation` 94/1.925, `process_effect` 78/1.631, `file_artifact` 54/1.119,
`bundle_cli` 45/1.641, `lineage` 34/998, `python_callable_v2` 31/799, `review_verify` 28/608, `run` 25/994, `review_ocr` 24/451,
`adapters` 12/557, `static_admission` 13/192, `client` 10/394, `settings` 10/343, `diagnostics` 15/369, `usage` 8/259, `bundle` 6/214,
`preflight` 6/323, `verify` 4/289, `calibration` 4/57, `catalog` 3/11, `cli` 2/174, `feedback` 2/346, `review` 2/131, `workspace` 1/34
(bảng đầy đủ: `SCOPE.json`, `totals`).

Mỗi hàng của `SCOPE.json` có `reasons` (nguyên văn lý do của delta), `result_from_base` (kết quả cũ đến từ campaign nào), `mutants`, `kill_files`,
và `standing` (bản ghi worker, digest/bộ kill/số mutant lúc đo so với hiện tại, phân lớp).

### Tie với `round-5/SCOPE-BEFORE-PIN.md` (≈ 509 target, ≈ 13.751 mutant, ≈ 103 còn nguyên)

| | SCOPE-BEFORE-PIN | ở đây | chênh |
|---|---:|---:|---|
| target phải đo lại | ≈ 509 | 511 | +2 = hai target của `lineage-r2` (`lineage.py::_recorded_spend` 48 mutant, `_evidence_gone` 58), đăng ký ở `2c9488d` sau lần đo 03:00 |
| mutant phải đo lại | ≈ 13.751 | 13.859 | +106 của hai target đó, +2 của `lineage.py::account_of` (86 → 88 mutant khi lane lineage-r2 đổi `lineage.py` sau cây `3e1e83a`; truy ra bằng cách đếm lại ở cây đó) |
| tệp byte đổi | 457 target / 11.852 mutant | 459 / 11.960 | = 457 + 2 và 11.852 + 106 + 2 (cùng hai mutant) |
| tệp không đổi, kill file đổi | 52 / 1.899 | 52 / 1.899 | khớp tuyệt đối |
| còn nguyên | ≈ 103 | 103 / 2.221 | khớp (tài liệu: 15.972 − 13.751 = 2.221) |
| registry | 612 target, 15.972 mutant (+2 target chưa đếm) | 614 target, 16.080 mutant | `REPORT.md` ghi "mutant của hai target thêm chưa đếm": là 106 |

Con số "≈ 15.980 mutant" cho 614 target trong yêu cầu của chiến dịch (15.972 cộng ≈ 8 đoán cho hai target thêm) thấp hơn số đếm của runner 100: số đúng là 16.080.

## 3. Kết quả đang đứng, và 103 target giữ tạm

**Kết quả đang đứng** (`closure-evidence/v2/v2.1/MUTATION.json` + `MUTATION-SUMMARY.json`, FINAL_HEAD `8043387`, 528 target, 13.581 mutant,
`MUTATION_VERDICT: PASS`) đến từ bốn campaign, theo chuỗi của `campaign-8/SCOPE.json` `result_from`; mỗi campaign là một **base** của một bảng delta:

| base (snapshot của manifest) | campaign | target có kết quả từ đó | đo lại | đứng tạm |
|---|---|---:|---:|---:|
| `289885e` (`REQUALIFICATION-MANIFEST-5`) | 5: đo cả 528 target | 472 | 421 | 50 |
| `a770fbb` (`-6`) | 6: đo lại 56 | 43 | 3 | 40 |
| `853da4a` (`-7`) | 7: đo lại 3 | 1 | 0 | 1 |
| `5df323a` (`-8`) | 8: đo lại 12 | 12 | 0 | 12 |
| | | **528** (= 527 trong registry + 1 đã gỡ) | **424** | **103** |

`MUTATION-SUMMARY.json` `provenance` ghi `measured_on` khác cho nhiều target: `5719f1f` 268, `289885e` 119, `f860e57` 84, `a770fbb` 43, `5df323a` 12,
`b5c2457` 1, `853da4a` 1. Đó là lần đo **sớm nhất còn dùng được trên đúng byte đó** mà bản ghi gộp trích (campaign 2/3/4 đo trước campaign 5); campaign 5
đã đo lại cả 528 target ở `289885e`. Với cả 527 target, mục được trích và mục của chuỗi có cùng `source_sha256` và cùng phân lớp (`standing.merged_record_cites`
trong `SCOPE.json`), nên base của delta là snapshot trong chuỗi, như campaign 8. Snapshot gốc của pha (`cc53596`, manifest 1) và `5719f1f`, `f860e57`,
`b5c2457` không là base của kết quả nào còn đứng: không có bảng delta cho chúng.

**Cả 103 target đứng đều là `STANDS_PROVISIONAL`**, không có `STANDS`: chưa có read-set ở head này (bản ghi nói mỗi kill file mở tệp nào), nên mọi tệp đổi nằm trong
`mutation.COPY` (`aisef2`, `tests/v2`, `validation/v2`, `docs/architecture`, `docs/implementation/v2`, **`closure-evidence/v2`, `docs/v2.1`**, `aisef`, `pyproject.toml`)
là dữ liệu mà kill tests có thể đọc. Số tệp đổi trong COPY chưa đo (`provisional.changed_files_inside_COPY_not_measured`): 2.229 (base `289885e`), 623–639 (`a770fbb`), 512 (`853da4a`), 465 (`5df323a`).

| tệp | base | target | mutant | kill tests có thể đọc tệp đổi (tìm tĩnh) | closure kill tests chứa mã `aisef2` đã đổi |
|---|---|---:|---:|---:|---:|
| `aisef2/app/confine.py` | `a770fbb` 17, `853da4a` 1, `5df323a` 12 | 30 | 1.069 | 23 | 22 |
| `aisef2/runtime/process_range.py` | `a770fbb` | 23 | 244 | 0 | 0 |
| `aisef2/orchestrate/workspace.py` | `289885e` | 16 | 215 | 0 | 16 |
| `validation/v2/cleanup_authority.py` | `289885e` | 16 | 226 | 0 | 0 |
| `aisef2/orchestrate/story_runner.py` | `289885e` | 11 | 409 | 11 | 11 |
| `aisef2/orchestrate/adapters.py` | `289885e` | 7 | 58 | 0 | 7 |
| **Cộng** | | **103** | **2.221** | **34** | **56 (1.587 mutant)** |

Tệp đổi mà kill tests *có thể đọc* (tìm tĩnh, 34 target; `provisional.found_statically_in_a_kill_closure_file`): 9 tệp `tests/v2/test_probe_process_effect_units.py`,
`test_v21_migrate_semantics.py`, `test_v21_probe_sources.py`, `test_v21_pm8_diagnostics.py`, `test_v21_review_chain.py`, `docs/v2.1/ANCHOR-THREAT-MODEL.md`,
`SANDBOX-LINUX.md`, `UPSTREAM-RESEARCH.md`, `closure-evidence/v2/v2.1/round-5/ocr-build/PROVENANCE.md`; thêm `K-NOWORK-001-REHEARSAL.json` và `PLAN-V2.2-CORRECTION-1.json`
(11 target của `story_runner`) và `aisef2/app/verify.py` (4 target). Read-set ở head cuối quyết định từng tệp: tệp nào kill file thực sự mở thì target tương ứng phải đo lại.

**Điều kiện thứ hai, ngoài read-set (điều cần biết):** 56 target (1.587 mutant) có trong closure của kill tests **mã `aisef2/` đã đổi** (`provisional.changed_code_in_the_kill_closure`: `process_range.py`,
`calibrations.py`, 5 tệp probe, `run.py`, `lineage.py`, `bundle_cli.py`, …). Công cụ delta chỉ *báo* mã ngoài `tests/` (không tính vào kết luận). Campaign 5 xếp loại này là `REACH`
(đo lại trừ khi có đo lường kill file có *thực thi* hàm đã đổi hay không, chỉ thị 2026-10-12 mục 6: "nếu tái sử dụng được kết quả nào, phải có căn cứ phụ thuộc cụ thể"); campaign 6 dùng
`trace.json`; campaign 8 không cần vì mã sản phẩm và runner không đổi. Ở đây mã đã đổi (16 tệp `aisef2/`), nên các target này chỉ đứng được khi **bản ghi reach ở head cuối** (`validation/v21/reach.py`) cho thấy
không kill file nào thực thi hàm đã đổi; read-set một mình không đủ. `provisional.also_needs_a_reach_record` đánh dấu chúng. Trong 56, **23 target (273 mutant: `workspace` 16, `orchestrate/adapters` 7)**
chỉ có `process_range.py` là mã đã đổi, và `campaign-6/trace.json` (commit `60a75c8`, hoàn tất; `process_range.py` và `confine.py` ở đó giống từng byte ở snapshot) đã đo 3 kill file của chúng: 0 lần chạm đường `_Posix.abort` đã đổi — với 23 target này
bản ghi reach không thêm thông tin, chỉ còn read-set. **33 target còn lại (1.314 mutant: `confine` 22, `story_runner` 11)** có thêm mã đã đổi từ `5df323a` trở đi (`run.py`, `lineage.py`, `bundle_cli.py`, các probe, `calibrations.py` …) mà không bản đo nào phủ: cần reach mới.

Nếu tất cả lật: +103 target / +2.221 mutant (registry đầy đủ 614 / 16.080). Đây là các module nhỏ: campaign 8 đo 12 target `confine` (680 mutant) trong 26 phút, 1,1 giờ-worker.

**Runner đổi so với mọi base** (`SCOPE.json` `harness_changed_since_each_base`): `validation/v2/mutation.py` (và `aisef2/runtime/process_range.py::_Posix` so với `289885e`). Quy tắc của delta nói thẳng "không
ràng buộc mã runner". Phần đổi của `mutation.py` từ `5df323a` (đọc `git diff 5df323a..69b0ea9`): dữ liệu đăng ký (kill set của 87 target mới và các target mở rộng), `V21_RETIRED` và vòng xoá, `superseded()`
và một dòng in của `main` nói target đã gỡ. Bộ sinh mutant (`_SWAP`, `_inert`, `_script`, `_root`, `mutants`) **không đổi**: mỗi bảng delta ghi cho 103 target "same inputs (generator source, module source, enum members)".

## 4. Thời gian máy dự kiến

Quy tắc `campaign-3/tools/make_queue3.py`: chi phí một target = số mutant × tổng giây T0 của các kill file của nó trên null mutant của nó (cận trên; mutant bị giết trả ít hơn).
T0 của snapshot đang chạy ở máy, chưa có bản ghi (dự kiến `T0-SWEEP-9.json`), nên ước lượng từ các bản ghi đã commit (`T0-SWEEP.json` … `-8`, 489 cặp); `ESTIMATE.json` có từng target.

| | giờ-worker (cận trên) |
|---|---:|
| đúng quy tắc, `make_queue3.py` chạy nguyên văn trên `T0-SWEEP-8.json` (chạy thật vào scratch, khớp `ESTIMATE.json`): cặp (null, file) không có hàng tính trung vị 1,8 giây | 165,4 (1.594 trên 1.880 cặp là đoán) |
| **theo tệp** (cặp không có hàng cho null này: giây của chính kill file đó trên null cũ của module, rồi trung vị theo file, rồi trung vị): 286 cặp có hàng, 1.371 + 1 từ null cũ, 222 đoán | **610,7** (trong đó 8,0 là đoán; 28 kill file mới chưa từng đo T0) |

Hiệu chuẩn bằng các campaign đã chạy (`queue.tsv` + dấu started/finished của worker; `ESTIMATE.json` `calibration`): chạy/cận trên = 0,12 (c3), 0,10 (c4), **0,17 (c5: 528 target, 13.566 mutant, cận trên 589,1 giờ-worker, chạy 100,3 giờ-worker, 24,3 giờ tường)**,
0,36 / 0,21 / 0,25 (c6/c7/c8, nhỏ nên chi phí khởi động trội). Campaign 5 là campaign duy nhất cùng cỡ.

- Số theo tệp 610,7 × 0,17 ≈ **104 giờ-worker** (campaign 5: 100,3). Số đúng quy tắc 165,4 thấp hơn thực tế vì trung vị 1,8 giây đoán thấp cho các kill file nặng: không dùng.
- Giờ tường: chia đều là 26 giờ (4 worker) hoặc 21 giờ (5 worker), nhưng **target dài nhất quyết định**: `run.py::execute` cận trên 57,1 giờ (campaign 5: 51,1 giờ → worker chạy nó mất 24,3 giờ, cũng là giờ tường của cả campaign) → **≈ 27 giờ tường**,
  4 hay 5 worker như nhau. Hàng đợi sắp dài nhất trước (`make_queue3.py`), nên `execute` phải bắt đầu đầu tiên. Tiếp theo: `settings.py::load` 41,6; `verify.py::verify` 25,4; `bundle_cli.continue_from` 20,5; `Reviewer._ocr` 19,3.
- So với `SCOPE-BEFORE-PIN.md` ("đo mutation ≈ 22–32 giờ", 4 worker): cùng khoảng. Số này sẽ đổi khi T0 của snapshot có (chắc chắn nhất là 222 cặp đoán), và khi read-set/reach ở head cuối lật target tạm (§3).

## 5. Việc còn lại trước khi ghi hàng đợi (của người điều phối)

1. T0 sweep của snapshot → `execution_order.py --record` → `EXECUTION-ORDER-10`, `REQUALIFICATION-MANIFEST-9`.
2. Hàng đợi: `python -P closure-evidence/v2/v2.1/campaign-3/tools/make_queue3.py ROOT T0-SWEEP-9.json OUT closure-evidence/v2/v2.1/campaign-9/targets.txt` (chưa ghi ở đây; `make_queue3.py` chạy
   không đổi trên `targets.txt` này, đã thử vào scratch). Không có script campaign nào phải sao chép hay sửa: `campaign3.sh`, `qworker.sh`, `t0-sweep.sh`… dùng nguyên.
3. Ở head cuối: read-set (`read-set.json`) **và** reach cho 56 target (§3), rồi dẫn xuất lại bốn bảng delta với `--read-set`; target nào kill file mở tệp đổi hoặc thực thi hàm đổi chuyển sang `REMEASURE`.
   Mọi commit sau snapshot dưới `closure-evidence/v2` hoặc `docs/v2.1` — kể cả các tệp của campaign này — là tệp đổi trong COPY: read-set ở head cuối đã tính chúng, bảng delta ở đây thì chưa (ghi ở `harness`/`files` của `DELTA.json`).
4. Bảng delta của campaign này không có read-set (`read_set: null`). `--check` của cả bốn PASS ở head `69b0ea9` (cây trước khi thêm tệp nào của campaign này); ở commit thêm các tệp này nó báo `stale` (đã thử với `-5df323a`): `closure-evidence/v2` nằm trong COPY, nên chính các tệp `campaign-9/` là thay đổi sau head của bảng mà không read-set nào phủ. Đó là hành vi đúng của công cụ, không phải bảng sai: bảng cuối cùng phải dẫn xuất ở head cuối, với read-set của head đó.

## 6. Tệp

| tệp | nội dung |
|---|---|
| `SCOPE.json` | 614 hàng (`role`: `NEW`, `REMEASURE`, `STANDS_PROVISIONAL`), `retired`, `disagreements`, `totals`, `harness_changed_since_each_base` |
| `targets.txt` | 511 target đo ngay (`REMEASURE` + `NEW`), sắp theo tên, tập con của `V21_TARGETS` |
| `ESTIMATE.json` | chi phí `targets.txt` theo quy tắc `make_queue3.py`, hiệu chuẩn c3–c8, từng target |
| `delta-from-289885e/`, `-a770fbb/`, `-853da4a/`, `-5df323a/` | `DELTA.json`, `DELTA.md` từ `v21_snapshot_delta.py --write … --base B --head 69b0ea9`, **không** `--read-set`; `-5df323a` chỉ để đối chiếu chuỗi (không là base của kết quả nào ngoài 12 target của campaign 8, nằm trong nó) |
| `tools/scope9.py` | tạo `SCOPE.json`, `targets.txt`, `ESTIMATE.json`; chỉ đọc tệp đã commit; chạy ở gốc kho (~7 phút): `python -P closure-evidence/v2/v2.1/campaign-9/tools/scope9.py closure-evidence/v2/v2.1/campaign-9` |
| `tools/verify9.py` | lần đếm thứ hai, độc lập (~6 phút), thoát 1 nếu lệch |

Bốn bảng delta tái dẫn xuất bằng `python -P validation/qualification/v21_snapshot_delta.py --write closure-evidence/v2/v2.1/campaign-9/delta-from-<base> --base <sha đầy đủ> --head 69b0ea946922bcd209ffbf5a7bd943ad96080df7`
(`<sha đầy đủ>` của `REQUALIFICATION-MANIFEST-N.json` `snapshot`, N = 5, 6, 7, 8). Mỗi bảng ~3,5 phút.

## 7. Quyết định của người điều phối sau khi gộp: 33 target được đo ngay (PROMOTED.json)

Người rà soát độc lập (F-4) chỉ ra 33 target đứng tạm (`aisef2/app/confine.py` 22, `aisef2/orchestrate/story_runner.py` 11; 1.314
mutant) mà closure kill tests có mã `aisef2/` đã đổi (`run.py`, `lineage.py`, `bundle_cli.py`, các probe, `calibrations.py`,
`catalog.py`, …) và chưa có bản ghi trace/reach nào phủ; hợp đồng của runner (`docs/v2.1/MUTATION-RUNNER-V2.md` mục 19)
đo lại theo mặc định. Để cuối cùng không phải mở một lượt đo thứ hai sau read-set, **chúng được đo cùng campaign này**
(`PROMOTED.json`), không chờ bản ghi reach. `targets.txt` giữ nguyên là cái các quy tắc của công cụ cho ra (511 target /
13.859 mutant; `scope9.py` và `verify9.py` không đổi); **danh sách chạy thật là `targets-run.txt` = `targets.txt` + `PROMOTED.json`
= 544 target / 15.173 mutant**. 23 target còn lại có mã đổi trong closure chỉ là `aisef2/runtime/process_range.py`, đã được
`campaign-6/trace.json` phủ trên cùng byte (3 kill file, 0 chạm); 47 target không có mã đổi trong closure. Hai nhóm này,
70 target / 907 mutant, đứng tạm cho tới read-set ở head cuối. Hạn mức thời gian: 13.859 → 15.173 mutant thêm khoảng 10 giờ-worker;
tường vẫn do `run.py::execute` quyết định (≈ 27 giờ).

## 8. Lượt chạy (bản ghi của người điều phối; mốc theo đồng hồ hệ thống, không phải dự kiến)

| | |
|---|---|
| Khởi chạy | **2026-10-18 08:17:16 +07** (`01:17:16Z`, `campaign.started`); worker 1–4 bắt đầu 01:17:20Z … 01:17:37Z |
| Snapshot của worker | `4ec961e706a1f7bda16d131037058c4fe9c2663f` (cả bốn `c3-w*.snapshot`); cây `aisef2/`, `tests/`, `validation/` giống từng byte `69b0ea9` (`git rev-parse <sha>:<tree>`: `717fab17…`, `4d5d1cf6…`, `10f6007a…`); manifest 9 `snapshot` = `4ec961e` (commit `77aa955`, `--check` PASS trước khi chạy) |
| Hàng đợi | `queue.txt` / `queue.tsv` (commit `ff6309f`): 544 target / 15.173 mutant, dài-nhất-trước theo `T0-SWEEP-9.json`, **0 cặp (null, file) đoán**, cận trên 715,1 giờ-worker; bảng thứ tự `EXECUTION-ORDER-10.json` qua `--order` |
| Lệnh | `heavy.sh campaign9 campaign3.sh C 4ec961e 4 closure-evidence/v2/v2.1/EXECUTION-ORDER-10.json` + `watchdog.sh C` + `sync9.sh C campaign-9/run` (`launch.cmd`); khoá máy `heavy.lock.d/owner` = `campaign9 42612 2026-10-18 08:17:16`; không worker cũ (`pgrep mutation.py run` = 0 trước khi chạy), không khoá cũ |
| Công cụ (sha256, 16 hex đầu) — chạy từ bản chép trong scratch, **giống từng byte** bản đã commit | `campaign-3/tools/campaign3.sh` `7d006b18c0fa4cf1`, `qworker.sh` `8387648666818245`, `watchdog.sh` `ddc6c19deb5e0432`, `progress3.py` `be252afd44bf5535`, `make_queue3.py` `706986fe81b48c16` (chạy từ kho); `campaign-9/tools/heavy.sh`, `sync9.sh` (bản bền vững của hai script scratch) |
| Worker | 4 (tối đa chủ dự án cho phép); mỗi worker: worktree detached tại snapshot, `env -i`, PATH không có `opencode`, HOME/XDG/TMPDIR riêng, `owned_run.py` bọc từng target; tên trong scratch `c3-w1..4` (script không đổi), đổi thành `c9-w1..4` khi nhập vào `mutation-workers/` như campaign 8 |
| Đĩa | 38 GiB trước khi dựng worktree → 25 GiB sau 25 giây (≈ 3 GiB/worker); `campaign3.sh` từ chối < 15 GiB lúc khởi động; worker dừng trước target kế tiếp khi < 10; `watchdog.sh` tạo STOP khi < 12, SIGTERM `mutation.py run` của đúng campaign này khi < 6; không xoá gì theo mẫu đường dẫn hay độ nhàn rỗi; janitor cũ không chạy |
| Bền vững | `sync9.sh` mirror thư mục campaign (trừ worktree/env của worker) sang `campaign-9/run/` trên đĩa thật mỗi 600 s; bản chép cuối nhập vào `results/` + `mutation-workers/` sau khi xong |
| Dự báo lúc khởi chạy (chưa đo) | 715 giờ-worker cận trên × hệ số thực/cận trên của campaign 5 (0,17) ≈ 122 giờ-worker; tường do `run.py::execute` quyết: cận trên 258.367 s = 71,8 h × 0,475 (c5: 51,1 h → 24,3 h) ≈ 34 h ⇒ **≈ 30–36 giờ tường**, kết thúc khoảng 14:00–20:00 ngày 2026-10-19 (+07). Số 27 h ở §7 dựa trên T0-SWEEP-8; T0-SWEEP-9 đo `execute` chậm hơn (705,9 s/chuỗi) |
| Quy tắc kết quả | TIMEOUT / INFRA / NOT_RUN là lớp riêng, không đếm là KILLED (`progress3.py`); hàng như vậy chạy lại một mình ở cùng snapshot như `c3b`; survivor mới kiểm toán theo vị trí (hai bản sao mù), không thêm test chỉ để đạt 100 % |
| Đọc log worker | `exit 1 line N` sau **mỗi** target là phán quyết toàn-registry của runner ở cuối `mutation.py run` (`mutation: FAIL` + một dòng `… has no mutation result` cho mỗi target chưa có kết quả trong bản ghi của worker ấy) — campaign 5 và 8 cũng vậy cho mọi dòng; **không** phải lỗi của target. Lỗi thật: `exit 3` (runner STOPPED, worker dừng), lớp TIMEOUT/INFRA/NOT_RUN trong dòng `MUTANT`, hay ` ERROR ` trong dòng tổng kết target. Target đầu xong: `settings.py::load` 268/268 KILLED (worker 2, 01:17:25Z → 02:12:38Z, 3.313 s) |
