# Phạm vi trước khi ghim snapshot (cửa sổ sửa lỗi probe, bản ứng viên AISEF 2.1)

Lập theo chỉ thị 2026-10-15 điểm 7 (`OWNER-DIRECTIVE-2026-10-15-B.md`), **trước** khi ghim. Đo lúc 2026-10-18 03:10 (Asia/Saigon)
trên nhánh `v2.1/probe-window` ở `2c9488d`. Đây là ứng viên, chưa được nghiệm thu, chưa phát hành; không có ghi nhận
nghiệm thu nào được tạo. Chưa push, tag, publish, deploy; chưa gọi provider trả tiền; Docker và `goe-*` vẫn chạy.

## 0. Hai điều phải đọc trước (chưa sửa, nên chưa được ghi là đã đạt)

| | Là gì | Đo ở đâu | Hệ quả cho lời khẳng định |
|---|---|---|---|
| **V1 chi phí/báo cáo trả toàn 0 với exit 0** | `aisef cost`, `aisef report`, `aisef status` (lệnh V1) chấp nhận thư mục run V2 và in "0 phiên, nothing spent, total cost $0.00" khi `RUN.json` ghi 0,000818 USD và 2 phiên; `aisef report` còn ghi `docs/ACCEPTANCE-REPORT.md` và `_bmad-output/` vào thư mục run hoặc repo người dùng. README còn liệt kê chúng là lệnh còn hiệu lực. Backlog V21-43, trở ngại O-2 của hành trình | `m21/n1/results/journey.json` (bước 14, 15; đo trên run thật của `e2e-linux-final`) | **Không được ghi "hành trình người dùng đã đạt".** Cách chữa (từ chối thư mục run V2 ở lệnh V1; hoặc chế độ báo cáo V2) đụng mã sản phẩm V1 và V2 và kernel digest: chưa làm, đã đưa backlog |
| **Hai vấn đề CRLF của Windows** | (1) `tests/v2/p0/test_freeze_manifest.py:171` đỏ ở checkout `core.autocrlf=true` (LF: 21/21, CRLF: 1 lỗi); (2) checker `execution_order`: `check(EXECUTION-ORDER-9.json)` trả `[]` ở LF và "T0-SWEEP-8.json is not a file committed at HEAD" ở CRLF; `test_checker_calibration` đỏ thêm đúng subtest `execution_order` | `m21/n1/results/platform.json` (mô phỏng CRLF trên macOS, ≈47 module, ≈780 test; **không phải Windows thật**) | **Không được ghi "hỗ trợ Windows đã đạt".** Windows chưa từng chạy 2.1; không có CI Windows (chưa push) |

## 1. Thay đổi đã gộp (nhánh tích hợp `v2.1/probe-window`, 15 tệp `aisef2/`, +2.614/−345; 14 tệp `validation/`; 70 tệp `tests/` (30 mới); 11 tệp `docs/`)

Mỗi làn: hai reviewer độc lập (không thấy ý của tác giả), một lượt sửa, một người kiểm cuối; test đỏ-trước/xanh-sau.

| Làn / mục (quyết định của chủ dự án) | Việc | Commit gộp |
|---|---|---|
| effect-cli (PM-1, PM-2, PM-6, PM-7) | probe tìm chủ thể theo tên thành phần; fault `expect_raises` có cấu trúc; lỗi host (`harness.log`, NUL trong argv) có câu trả lời; nguồn digest được đo | `6cbd050` |
| review-contracts (RV-1, họ lỗi sâu) | giới hạn độ sâu 63, trạng thái có cấu trúc | `79a559d` |
| file-artifact, file-artifact-2 (PM-3, PM-4, PM-9, PM-11, PM-13) | tệp parser không nhận → từ chối có kiểu, không retry; lựa chọn rỗng = chủ thể vắng, `CAPABILITY_VERSION` 2→3; `utf-8-sig`; vòng regex của `grep_count` chạy trong worker dưới `timeouts_s.probe`, hết hạn = UNRUNNABLE | `084d12c`, `3ec1525` |
| ocr-gate, ocr-preflight (OCR) | cổng danh tính OCR (pin sha256, version tự khai) lúc dùng **và** ngay đầu `aisef run`, trước claim/clone/preflight/phiên | `367851f`, `0b7c299` |
| ocr-build | dựng lại từ đúng commit `182898c` (go1.26.5) cho đúng từng byte binary đã ghim — **mức "tái tạo được trên một máy"** | `ead60af` |
| pm8-diagnostics (PM-8) | `probe-observations/` chỉ cho người vận hành, bí mật bị che, ghi rõ giới hạn cùng user | `8775777` |
| lineage, lineage-proof, lineage-r2 (lineage) | bằng chứng không đọc được **hoặc đã mất** = chi phí chưa xác định (không bao giờ 0 hay số trông đã đối soát); `aisef run --parent` từ chối với mọi cờ; không sửa lịch sử, không giải phóng claim | `2ce3bdb`, `06d979d`, `68a13b4` |
| migrate-semantics (điểm 1) | `bundle migrate`/`seal --keep-approvals-from` không giữ approval cho ngữ nghĩa đã đổi; bundle ứng viên MỚI; không ký thay | `20b743b` |
| review-limits (điểm 3, 4) | trạng thái máy đọc `INDETERMINATE` riêng, `NOT_REPRODUCED` chỉ cho SATISFIED; regex của reviewer/spec chạy trong worker có deadline; biên `within_s` ghim ở nơi đã công bố | `3bd2e7d` |
| linux-recorder, linux-suite (điểm 6) | recorder không đếm đôi tiến trình con trên Linux (khoá theo định danh lần khởi chạy); `offline_groups.sh`; chạy suite trong guest Linux | `a78e8cc`, `08ca8cc` |
| PM-5 (giới hạn) | docstring, `WEAKEST_PATH` và 6 chỗ công khai (README en/vi, USAGE en/vi, landing, SALEKIT) không còn nói mã bị kiểm "không thể tự chế kết quả"; nói đúng: kênh được bảo vệ, giá trị chủ thể tự khai thì không | `f69124c`, `ae7a569`, `7b029e6` |
| tài liệu, đăng ký mutation | USAGE-2.1 §8, REPORT, ADR, backlog V21-39…88; registry **612 target / 15.972 mutant / 29 tệp / 193 kill file** | `50566bf`, `6add6c6`, `90e854e`, `2c9488d` |

Hồi quy trước khi ghim: `ruff` sạch, `test_meta` 34 xanh, `destructive_authority` PASS. Suite đầy đủ chạy thử (bản sao đã hiệu chuẩn, **không phải bằng chứng**):
lần 1 trên `8e6f583`: 7.900 test, 5.262 s, 13 đỏ = 12 bản ghi dẫn xuất chưa sinh lại + 1 test ghim `PROBE_SOURCES` (đã sửa ở `3c5a642`); lần 2 trên `2c9488d`: đang chạy.

## 2. Lỗi còn chặn snapshot

| | Trạng thái |
|---|---|
| Lỗi đã biết, bằng chứng rõ, chưa sửa, chặn tính đúng hoặc an toàn | **Không có.** (Mọi lỗi các reviewer tìm ra trong cửa sổ đã sửa, hoặc là quyết định của chủ dự án ở §5.) |
| Việc còn trước khi ghim | (a) kết quả suite chạy thử lần 2; (b) chủ dự án trả lời các quyết định đổi mã ở §5 (nếu chọn phương án B **sau** khi ghim thì phải đo lại phần bị ảnh hưởng); (c) bảng này |
| Tài liệu ngoài danh sách tệp được sửa còn câu lỗi thời | `docs/v2.1/decisions/B-01-…:21-31`, `TRACEABILITY.md:355,1013`, `research/TRACEABILITY.json:529`, `MUTATION-RUNNER-V2.md:485-488`, `decisions/B03-R3-usage.md`, `decisions/B03-R4-REVIEW.md:115`, `docs/implementation/…/CYCLE2-THREAT-AND-HIDDEN-AUTHORITY-MATRIX.md:51` (câu "bounded pattern length" sai từ trước). Không chặn mã; sửa trước hoặc sau khi ghim đều không làm mất hiệu lực phép đo mã, nhưng **thay đổi tài liệu trong cây sau `--write` buộc viết lại bản ghi mutation** (luật FINAL_HEAD) |

## 3. Spec/approval cần chủ dự án duyệt lại (không có approval nào được ký hay chuyển bởi người điều phối)

| Đối tượng | Số lượng | Vì sao | Hành động |
|---|---|---|---|
| Contract LedgerLock 2.0.0 (`closure-evidence/v2/release/LEDGERLOCK-PROJECT.json`) | **6** (`BC-V22-S-10-a`, `S-10-b`, `S-10-c`, `S-12-a`, `S-12-b`, `S-12-c`); 53/59 approval giữ lại | cơ chế **suy ra** (không đặt tên): PM-9 (lựa chọn rỗng) và PM-11 (BOM) đều đổi cách `grep_count` đánh giá; chủ dự án đã nêu bốn, hai thêm là `S-10-b/c` — **quyết định D-1** | khi ghim, tôi chạy `aisef bundle migrate` để tạo bundle ứng viên (tệp + digest + `plan_hash` + `file_sha256` + diff ngữ nghĩa + tình huống đổi verdict + lệnh `bundle approve` với `human:NAME` để anh gõ); bundle và approval cũ giữ nguyên làm lịch sử |
| 59 approval `human:owner` 2026-09-30 của `P5-CONTRACT-APPROVALS` | 59 | gắn `proposal_digest`/`plan_hash`, đổi khi spec id đổi (CAPABILITY_VERSION của `file_artifact` 3) | bản ghi dẫn xuất mới trên digest mới; duyệt lại là của anh (không chuyển mapping) |
| `aisef2/app/examples/calc-3-stories.json` (`BC-STDLIB`, `python_imports` REQUIRES_SUBJECT) | 1 | verdict có thể đổi nếu thư mục không có `.py` | **giới hạn đã ghi (V21-61):** bundle niêm phong bằng checkout trước cửa sổ (capability 2) không có trong bảng `RELEASES` nên `seal --keep-approvals-from` giữ approval; 2.1 chưa phát hành nên không có người dùng ngoài |
| 54 spec `file_artifact` trong kho (quét `scan_specs.py`) | 12 `grep_count` + 3 `python_imports` loại (ii) | verdict có thể đổi | danh sách ở `lanes/fix_file-artifact-2.json` → `affected_specs_approvals` |
| Các việc đã nằm sẵn ở chủ dự án | B-02, B-04, B-08, B-09 (bậc 2c/3), B-10, F, RM-3 (ba `rm`) | `OWNER-DECISIONS-2026-10-15.md` | không thay đổi trong cửa sổ này |

## 4. Target và bằng chứng bị ảnh hưởng

**Mutation** (quy tắc runner: byte của tệp đổi → mọi target của tệp là cũ; tệp không đổi mà kill file đổi → target cũ):

| | Số |
|---|---|
| Registry (V21_TARGETS) | 612 target, 15.972 mutant, 29 tệp, 193 kill file (+2 target của lineage-r2) |
| **Phạm vi cũ tối thiểu phải đo lại** | **≈ 509 target, ≈ 13.751 mutant** (457 target / 11.852 mutant ở 15 tệp đổi byte; 52 target / 1.899 mutant ở 9 tệp không đổi nhưng có kill file đổi) |
| Còn nguyên (byte và kill file không đổi) | ≈ 103 target; kết quả đúng theo `source_sha256` |
| Tệp đổi nhiều nhất (target/mutant) | `cli_invocation` 94/1.925, `process_effect` 78/1.631, `bundle_cli` 45/1.641, `file_artifact` 54/1.119, `run` 25/994, `lineage` 34/≈900, `python_callable_v2` 31/799, `review_verify` 28/608, `adapters` 12/557 |
| Cần có trước khi đo | `release_calibration.py --write` một lần (19 hàng; hai test T0 `kills3_T15a`, `r5_review_indeterminate` chỉ qua sau đó), quét T0 cho các cặp (null, kill file) mới, `EXECUTION-ORDER-10`, `REQUALIFICATION-MANIFEST-9`, delta |

**Bản ghi dẫn xuất sinh lại, theo thứ tự phụ thuộc (sau khi ghim):** bản ghi mutation (`--write` rồi `--check`, ~25 phút mỗi lần) → Q0 hiệu chuẩn checker → C2-P5 re-verification → K-NOWORK-001 → Q5 kernel comparison → conformance ruling → basis của kết quả còn nguyên (read-set + delta) → P5 proposal/falsifiability/plan correction.

**Bằng chứng cũ còn hiệu lực hay phải làm lại:**

| Bằng chứng | Trạng thái |
|---|---|
| B-03 milestone `bf45e0f`, suite `45554e0` (7.305 test), mutation record `42e0305` | **lịch sử, đúng cho cây cũ (`aisef2` 1d4f0156)**; không còn là bằng chứng của cây ứng viên |
| E2E Linux `e2e-linux-final` (cây 1d4f0156) | **phải làm lại** trên cây cuối (cổng danh tính OCR sớm và lineage đổi đường chạy) |
| Canary B-09 tier 1, 2, 2b (mô hình thật) | lịch sử của cây cũ; không chạy lại (không gọi provider trả tiền mới) |
| Hiệu chuẩn probe `V2.1.0.dev0-PROBE-CALIBRATIONS-2` | cũ (digest thực thi của cả 4 probe đổi); bản mới `-3` ghi một lần khi ghim |
| OCR `OCR-IDENTITY-2026-10-13.json` | lịch sử; `round-5/ocr-build/PROVENANCE.md` là bản mới (rebuild trùng byte trên một máy) |
| Suite macOS (~1,5 giờ), suite Linux trong Docker (~1–2 giờ), E2E cách ly, OCR thật offline, nhóm mockup (66) và references (97) offline, nhóm Docker-gated (10) với container của riêng test | **chạy lại trên cây cuối** |

**Dự báo (không lặp lại dự báo cũ vì phạm vi đã đổi):** thời gian **máy**: ghim, hiệu chuẩn, delta, manifest ≈ 1–1,5 giờ; **đo mutation ≈ 22–32 giờ** (campaign 5 — lượt đầy đủ gần nhất, 528 target / 13.566 mutant, 5 worker — mất 14–21 giờ mutant + 3–6 giờ T0 mỗi worker; tôi dùng 4 worker theo chỉ thị giảm đồng thời); bản ghi dẫn xuất, các suite, E2E, OCR ≈ 6–8 giờ. Tổng ≈ **30–42 giờ máy**. Thời gian **sửa lỗi** còn lại nếu anh chấp nhận các mặc định ở §5: ≈ 0 trước khi ghim; sau khi ghim chỉ mở lại vì lỗi chặn có bằng chứng (mỗi lần mở lại = đo lại tệp bị ảnh hưởng + dẫn xuất).

## 5. Quyết định của chủ dự án còn mở, và cái giá nếu chọn phương án đổi mã **sau** khi ghim

Cột "mặc định" là hành vi trong mã hôm nay; ghim với mặc định nghĩa là chấp nhận hành vi đó cho bản ứng viên này. Cột cuối là
phần phải đo lại nếu anh chọn khác sau khi ghim. Chọn **trước** khi ghim thì không tốn thêm lượt đo (các tệp này đã trong phạm vi).

| Mã | Câu hỏi | Mặc định hôm nay | Nếu đổi sau khi ghim phải đo lại |
|---|---|---|---|
| D-1 | giữ **sáu** contract LedgerLock (an toàn hơn) hay thu về bốn | sáu | `bundle_cli` (45 target) + `file_artifact` (54) ≈ 100 target, 2,8k mutant (~5 giờ) |
| D-2 | ba probe (`cli_invocation`, `process_effect`, `python_callable_v2`) đã đổi hành vi từ 2.0.0 mà `CAPABILITY_VERSION` vẫn 1: 50/53 approval giữ lại chỉ dựa trên luật phiên bản | chấp nhận giới hạn đã ghi | **lớn:** đổi `CAPABILITY_VERSION` đổi spec id, hiệu chuẩn, bản ghi dẫn xuất và đo lại ba probe (203 target, 4,4k mutant, ~8–9 giờ) |
| R2-D1/D2/D3 | lineage: request đã trả lời không luồng khi không có `RUN.json`; hai lỗi cùng lúc; cách đọc "và/hoặc" | luật hẹp như đã gộp | `lineage` + `run` + `verify` (≈ 70 target) |
| R3, R4, R5 | lineage: child của claim bị thay thế mà thư mục đã mất; `--accept-unaccounted` trên chi tiêu đọc được; thứ tự claim–cổng | giữ như luồng đã duyệt 15/10 vòng 2 | `lineage`, `run`, `bundle_cli` |
| D1–D5 | `within_s` dưới sàn công cụ; stream cắt ở `STREAM_CAP`; toán tử biên của timer ở đúng W; trần độ dài/compile pattern; trần `within_s` của reviewer | hành vi hiện tại (biểu thức và hai hành vi ở USAGE-2.1 §8.3) | `cli_invocation` + `python_callable_v2` + `file_artifact` ≈ 180 target, 3,8k mutant |
| D-OCR-1 | tải artifact phát hành và attestation của upstream để so (quyền hiện tại chỉ phủ mã nguồn và dependency) | không tải | không đổi mã (chỉ bằng chứng) |
| V21-65 | giữ lối ra "finder model" trong lời từ chối của cổng OCR sớm | giữ | `run` (25 target) |
| PM-9 nhị phân, PM-13 bắt tay khởi động | lựa chọn toàn tệp nhị phân của `grep_count`; chặn bắt tay `ProcessRange` (30 s cố định) bằng `timeouts_s.probe` | giữ như hiện nay | PM-13 khởi động: `process_range` là nguồn digest của **cả bốn** probe → đo lại cả bốn |
| Recorder Linux | "định danh tiến trình thực tế" = định danh lần khởi chạy (không có pid ở hai sự kiện); `os.spawnv` không được đếm | chấp nhận cách đọc này | `read_set`, `reach` (validation, không trong COPY) |

## 6. Phần chủ động để bản sau (không chặn snapshot)

| Mục | Ghi chú |
|---|---|
| **Lệnh V1 `cost`/`report`/`status` trên thư mục run V2** (V21-43, O-2) | **giữ nổi bật.** chữa = từ chối ở lệnh V1 hoặc thêm `aisef run --report DIR`; đụng mã sản phẩm, kernel digest, mutation |
| **Hai vấn đề CRLF Windows** (§0) | **giữ nổi bật.** chữa = đọc nhị phân/LF-cố-định trong `freeze_manifest` và `execution_order`; cần CI Windows |
| C-1 (`.gitignore` trong `bundle init`) | backlog theo chỉ thị |
| Hành trình người dùng O-1…O-12 (cài đặt PyPI, settings, `opencode.json`, OCR…) | `docs/v2/V2.1-BACKLOG.md` |
| `catalog.py::CATALOG` (46 mutant dữ liệu) chưa đăng ký; `file_artifact._capability_changes` (mutant chuỗi mô tả, chưa có test giết) | quyết định của chủ dự án nếu muốn đo |
| Windows/Linux CI lần đầu cho 2.1, push, tag, phát hành | chưa được phép |

## 7. Thứ tự sau khi ghim (một lượt có kiểm soát, theo chỉ thị điểm 7)

1. `test_meta`, lint, hồi quy liên quan (đã chạy ở bản sao; chạy lại ở commit cuối).
2. Ghim snapshot → `release_calibration.py --write` (một lần) → quét T0 các cặp mới → `EXECUTION-ORDER-10` → delta + `REQUALIFICATION-MANIFEST-9`.
3. Đo lại **đúng phạm vi §4** (4 worker, theo RAM/đĩa/tải; dừng cấp việc mới nếu đĩa < 10 GiB và giữ checkpoint).
4. Sinh bản ghi dẫn xuất theo thứ tự §4.
5. Suite macOS và Linux (Docker), E2E cách ly (guest Linux), OCR thật offline qua đường sản phẩm trên cây cuối.
6. Tạo bundle ứng viên LedgerLock (`aisef bundle migrate`) và gửi diff ngữ nghĩa cùng định danh để anh duyệt cụ thể.
