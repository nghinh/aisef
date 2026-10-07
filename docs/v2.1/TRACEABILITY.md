# AISEF 2.1 — Bảng truy vết cải tiến (đề xuất + báo cáo 360°), đối chiếu tại HEAD `c9c736f`

Mỗi hàng là **một** mục cải tiến của đề xuất của chủ dự án (*AISEF v2 — Đề xuất cải tiến từ nghiên cứu mã nguồn*,
06/10/2026) hoặc **một** phát hiện của [báo cáo 360°](../DANH-GIA-360-V2.0-2026-10-06.md) mà 2.1 nhận, điều chỉnh, từ
chối hoặc còn để mở: phát hiện → bằng chứng tại HEAD → reproducer → ảnh hưởng → phương án → commit → mức đạt → tiêu chí
nghiệm thu → còn thiếu. Dữ liệu máy đọc: [research/TRACEABILITY.json](research/TRACEABILITY.json) — phần
"Bảng tóm tắt" và "Từng hàng" dưới đây được **sinh** từ tệp đó, không sửa tay.

Bảng này **không** thay [STATUS.md](STATUS.md) (theo hạng mục A–F) hay [REPORT.md](REPORT.md) (mức M1–M6); nó buộc từng
mục nguồn vào commit, test và mức đã có, và ghi rõ chỗ không xác nhận được.

## Đầu vào

| Nguồn | Định danh |
|---|---|
| Đề xuất cải tiến (tệp tải lên của chủ dự án, **không** nằm trong repo) | sha256 `ad2a79443bb20f5333b89dc6aa34500527d345490174767aed5905b071929832` |
| Báo cáo 360° | `docs/DANH-GIA-360-V2.0-2026-10-06.md` tại `c9c736f` |
| Mức đạt | `docs/v2.1/REPORT.md` §2 tại `c9c736f` |
| Nghiên cứu upstream (165 xác nhận / 46 phải sửa / 1 bị bác / 1 không kiểm được) | `docs/v2.1/research/UPSTREAM-RESEARCH.json` tại `c9c736f` |
| Commit 2.1 | `git log 610a593..c9c736f` (66 commit); nhánh 2.0.1 `release/v2.0.1-prep` = `f006d3d` (local, chưa push; ghi ở `other_refs` của JSON, chỉ kiểm khi có `--with-ref`) |

## Cách đọc

- **Quyết định**: `adopted` nhận nguyên ý · `adapted` nhận có điều chỉnh (lý do ở hàng) · `declined` không làm trong 2.1
  (lý do) · `blocked` chặn trên một quyết định hay ngân sách có tên · `open` chưa làm và chưa có quyết định nào được ghi.
- **Upstream**: `repo@commit` `tệp:dòng` — nhãn của tuyên bố trong nghiên cứu (**CODE** đọc trong mã · **README** chỉ
  tài liệu nói · **INFERENCE** suy luận chưa đo · **EXPERIMENT** số đo do upstream công bố · **NOT_FOUND** đề xuất nói
  mà mã không xác nhận) và kết quả của người kiểm chứng thứ hai (confirmed / corrected / refuted). Khi "corrected" hay
  "refuted", `tệp:dòng` là của người kiểm chứng; khi người kiểm chứng phân lại tuyên bố (N19 của open-code-review,
  N-18 của MiMo), nhãn là của người kiểm chứng và nhãn gốc của nghiên cứu ghi kèm.
- **Mức (REPORT §2)**: mức của hạng mục REPORT tương ứng, chép nguyên và kiểm bằng máy; hàng không có hạng mục riêng
  trong REPORT để trống (không tự gán mức). Hàng chỉ số của 360 §7 (R-M1…R-M9) không mang mức: mức của hạng mục liên
  quan không phải mức của chỉ số. M5 (live): không mục nào. M4 của B4/B5 là lượt CLI thật, lặp lại tại `c9c736f` (xem
  "Đã chạy lại").
- **Tiêu chí nghiệm thu**: chép từ chỗ nguồn *nêu* tiêu chí — đề xuất §10 (cột "Nghiệm thu cụ thể"), §4.3 ("Nghiệm thu
  bước đầu"), §12 (gate); 360 §6 ("Thước đo xong"), §7 ("Mục tiêu 2.1"); "(§n)" ở cuối ghi mục lấy. Mục mà nguồn không
  nêu tiêu chí ghi rõ "Đề xuất không ghi tiêu chí nghiệm thu cho mục này" (hay "360 không ghi…") rồi nói bảng đối chiếu
  với câu nào; `—` chỉ ở hàng `declined`.
- **Còn thiếu**: mọi hàng trừ `declined` ghi phần còn thiếu so với tiêu chí, hoặc ghi rõ "Không còn…" và dựa vào đâu.
- **Kiểm cơ học**: chuỗi phải có / không được có trong một tệp tại HEAD (hoặc commit ghi kèm, hoặc — "đi cùng bảng" —
  tệp bằng chứng commit cùng bảng này sau HEAD) — bằng chứng cho các câu về mã hiện tại.
- **Chưa xác nhận được**: phần của hàng dựa vào lời của tài liệu khác mà repo không cho kiểm lại.

## Kiểm lại

```sh
python3 -P validation/v21/traceability_check.py                       # mọi hàng tại c9c736f + khối sinh của tệp này
python3 -P validation/v21/traceability_check.py --proposal <tệp đề xuất>  # thêm: mục và tiêu chí của đề xuất, đúng sha256
python3 -P validation/v21/traceability_check.py --at HEAD             # cùng các khẳng định ở một commit mới hơn
python3 -P validation/v21/traceability_check.py --with-ref release/v2.0.1-prep  # thêm: 7 ô đọc trên nhánh 2.0.1 (local)
```

Bộ kiểm: commit tồn tại, là tổ tiên của HEAD (hoặc của `f006d3d` với nhánh 2.0.1) và chạm đúng các đường dẫn ghi (danh
sách không rỗng); mỗi reproducer tồn tại (AST); mỗi "kiểm cơ học" đúng và có đúng một khẳng định (chuỗi `contains`/`lacks`
từ 4 ký tự, `exists` là true/false); mức khớp REPORT §2; mỗi nguồn upstream là một tuyên bố của nghiên cứu với đúng nhãn
(của người kiểm chứng khi họ phân lại), đúng kết quả kiểm chứng, đúng commit đã đọc (≥ 7 chữ số hex), và mỗi `tệp:dòng`
là một dòng mà bằng chứng của nghiên cứu (của người kiểm chứng khi corrected/refuted) nêu **cho chính tệp đó** (số dòng
thuộc về tệp được nhắc gần nhất trước nó); mục 360° đúng nguyên văn; mọi hàng trừ `declined` ghi phần còn thiếu (có chữ,
không phải `—`); tiêu chí nghiệm thu nằm trong một đoạn nêu tiêu chí của nguồn, đúng mục khi có "(§n)", hoặc ghi rõ nguồn
không nêu (tiêu chí của đề xuất chỉ kiểm khi có `--proposal`); "Mục còn mở" và tập hàng `open`/`blocked` trùng nhau. Khoá
lạ — ở cấp trên cùng, trong `sources`, trong mục còn mở, hàng, commit, kiểm cơ học hay upstream — là lỗi, không bị bỏ qua;
mọi revision phải là mã commit hex (`--at`, `--with-ref` do git phân giải trước). Bộ kiểm **không** phân định được một
câu chép từ đoạn tiêu chí có phải toàn bộ tiêu chí, hay tiêu chí đã đạt chưa: đó là phán đoán, ghi ở "Còn thiếu".

Mặc định bộ kiểm chỉ đọc object tới được từ HEAD, nên chạy được trên mọi clone của nhánh; 7 ô đọc trên nhánh 2.0.1 local
(commit `c0ec1a5`, `f006d3d` và reproducer ở `f006d3d`, hàng P-V2-01, P-GATE-2.0.1, R-P0-1) chỉ được kiểm khi có
`--with-ref release/v2.0.1-prep`, và dòng OK nói rõ chúng chưa được kiểm. Test: `tests/test_v21_traceability.py`.

**Đã chạy lại (vòng 2, trên clone sạch tại `c9c736f`, không provider trả tiền, không `opencode` thật):**
- 97 reproducer bảng trích tại HEAD: `Ran 97 tests … OK (skipped=1)`; test bị bỏ qua là
  `RealBinary.test_a_full_review_against_a_scripted_model` (cần `AISEF_TEST_OCR_EXE`), và với nhị phân OCR đã ghim cả lớp
  `RealBinary` `Ran 3 tests … OK` — từng test ở
  [`evidence/traceability-reproducers-c9c736f.out`](evidence/traceability-reproducers-c9c736f.out). Reproducer ở `f006d3d`
  (P-V2-01) không chạy lại. Bộ kiểm vẫn chỉ kiểm reproducer *tồn tại*; lượt chạy là của commit này, không tự lặp lại.
- `validation/v21/cli_integration/run.sh` (CLI thật, OCR thật, provider giả trên loopback, developer giả):
  [`evidence/cli-integration-c9c736f.out`](evidence/cli-integration-c9c736f.out). So với output tại `b72e51e`, chỉ khác giá
  trị băm (commit của repo `git init` mới, plan_hash, anchor, sha256), pid, mốc thời gian và dòng cuối bị cắt ở 3000 ký
  tự. Giữa `b72e51e` và `c9c736f` chỉ hai commit chạm `aisef2/` hoặc `aisef/` — `a912be6` và `3061ec0`, đổi đường ghi của
  `aisef2/app/bundle_cli.py` (init/seal/approve/migrate ghi qua `_create`, tạo độc quyền O_EXCL) và một chú thích trong
  `review_verify.py` — nên M4 của B4/B5 nay là của chính byte tại `c9c736f`.

**Giới hạn:** các mức khác là của REPORT, không đo lại ngoài hai lượt trên; lượt CLI vẫn không có khoá git của editor
(A5) và không ghi journal ra output (C1, D5: xem "Chưa xác nhận được" ở từng hàng).

## Điều đối chiếu tìm thấy (so với tài liệu hiện có)

1. **Phát hiện 360° §3.1 vẫn đúng tại HEAD** ([R-3.1](#r-31)): `EXECUTION_DIGEST` của `process_effect` chỉ băm 4 tệp probe;
   `aisef2/runtime/process_range.py` (được import) và `range_anchor.py` (được chạy) nằm ngoài. Vì vậy V2-08 chưa đạt
   mục 3 của §9.2 đề xuất ("đúng byte của probe/runtime/dependency"). Sửa sẽ chạm kernel.
2. **Nghiệm thu của V2-09 chỉ đạt 4/5** ([P-V2-09](#p-v2-09)): lỗi lịch sử thứ năm (trích R-7/1) là UNANCHORED nên theo luật
   neo vẫn lọt gate; ADR-7 có ghi điều này nhưng STATUS ghi C1 "XONG". Vì điều kiện neo là điều chỉnh của chủ dự án, hàng
   ghi `adapted` (như P-ADJ-3, R-P1-8).
3. **M4 của A5 không tái hiện điều kiện của A5** ([P-V2-04](#p-v2-04)): repo trong lượt CLI thật không có khoá git của
   editor; điều kiện đó chỉ có ở test (M3).
4. **Hai khẳng định M4 không thấy được trong output đã commit**: chuỗi finding ⇒ CONFIRMED ⇒ ANCHORED ⇒ REVIEW_FINDING của
   REPORT §4.1 (output chỉ có S1 RETRY → COMMIT) và tệp anchor 0444 của D5 — ghi ở cột "Chưa xác nhận được". (Lượt
   `RealBinary` 3/3 mà REPORT §4.1 chỉ nêu thì nay đã chạy lại: xem "Đã chạy lại".)
5. **Thứ tự §10 của đề xuất** ("05/06/08/11/12 → 07/09 → 10 → 13"): 06, 08, 11 rồi 07, 09, 10 đã làm (13: chỉ
   harness); **05 (sandbox) và 12 (corpus ghi thật) — hai mục đứng đầu — chưa làm.**
6. **Kế toán reasoning: số đo có, kết luận là suy luận** ([P-11.3](#p-113)): trên 270 step của smoke #2, `total` =
   input + output + reasoning + cache ở 270/270 step (lệnh đo ghi ở hàng). *Nếu* `total` là số provider trả về thì
   `output` của client không gồm `reasoning` và `usage._usd` không đếm hai lần; nếu OpenCode 1.18.31 tự cộng `total` từ
   các trường của nó thì đẳng thức đúng bất kể `output` chứa gì. Repo không có mã OpenCode để phân định: INFERENCE.
   Có test chạy `aisef run` với bảng giá trên step có reasoning ≠ 0 (`test_v21_continue_integrity`), nhưng không test nào
   khẳng định số USD của một step như thế.
7. Các mục khác không có trong STATUS: action chưa ghim SHA và không có mục sổ cho phán quyết "FINAL RELEASE EXECUTION"
   ([R-P0-4](#r-p0-4)); link GitHub còn trên landing, salekit, README.vi ([R-P0-5](#r-p0-5)); `estimated` không có trạng
   thái riêng và request HTTP lỗi không có trong telemetry ([P-V2-11](#p-v2-11)); không có đề xuất sửa contract sinh từ
   finding ([P-4.3a](#p-43a)); không có bậc kiểm độ đặc hiệu của contract ([P-9.3](#p-93)).
8. **REPORT §1 ghi "mã cuối `b72e51e`"**, không còn đúng tại `c9c736f` (a912be6, 3061ec0 đổi `aisef2/`); lượt CLI đã được
   chạy lại tại `c9c736f` với cùng kết quả (xem "Đã chạy lại").
9. **Harness thí nghiệm chỉ khoá khung** ([P-6.2a](#p-62a)): `harness.check` đòi đúng tập khoá cấp trên cùng, seal, mức
   danh tính model kèm lý do và evaluator ẩn; nội dung các trường §6.2 (snapshot digest, adapter version, image digest…)
   không được đòi.

10. **Review thiếu tệp bắt buộc chỉ bị chặn dưới `fix-loop`** ([P-4.2a](#p-42a), [P-4.2b](#p-42b)): dưới `advisory` — cũng
    là luật khi settings không khai `review` — review INDETERMINATE được ghi mà story vẫn COMMIT; và tệp bắt buộc mà preview
    của OCR loại vì `unsupported_ext` hay `binary` không tính là thiếu (`review_ocr.NOT_REVIEWABLE`), không test nào phủ
    nhánh đó. Đề xuất §4.2 nêu cả tệp bị lọc vì extension: P-4.2b ghi `adapted`.

Không mục nào ở đây được sửa hay triển khai lại trong lúc lập bảng.

<!-- rows:begin — generated by validation/v21/traceability_check.py --render; do not edit by hand -->
Tổng: 88 hàng (đề xuất 57, báo cáo 360° 31); adopted 21, adapted 20, declined 16, blocked 18, open 13.

## Mục còn mở

- **Linux sandbox (F / B-07)**: [P-V2-05](#p-v2-05), [P-ADJ-4](#p-adj-4), [P-7c](#p-7c), [P-12-1](#p-12-1), [R-P1-12](#r-p1-12), [R-M5](#r-m5)
- **Gói ngữ cảnh / checkpoint theo MiMo (D4)**: [P-5.3a](#p-53a)
- **Lượt chạy live (provider thật)**: [P-ADJ-5](#p-adj-5), [P-11.2](#p-112), [R-P1-11](#r-p1-11), [R-M1](#r-m1), [R-M2](#r-m2), [R-M3](#r-m3)
- **So sánh hiệu quả có đối chứng (E2)**: [P-V2-13](#p-v2-13), [P-11.1](#p-111), [R-M6](#r-m6)
- **Khác — chưa làm, chưa có quyết định (open)**: [P-V2-12](#p-v2-12), [P-4.3a](#p-43a), [P-9.3](#p-93), [P-GATE-2.1](#p-gate-21), [R-P0-4](#r-p0-4), [R-P1-9](#r-p1-9), [R-P1-10](#r-p1-10), [R-P2-20](#r-p2-20), [R-3.1](#r-31), [R-M4](#r-m4), [R-M8](#r-m8), [R-M9](#r-m9)
- **Khác — bị chặn (blocked)**: [P-GATE-2.0.1](#p-gate-201), [R-P2-17](#r-p2-17), [R-M7](#r-m7)

## Bảng tóm tắt

| ID | Mục | Quyết định | Mức (REPORT §2) | Còn thiếu |
|---|---|---|---|---|
| [P-V2-01](#p-v2-01) | Đóng startup injection và tách trusted runtime | adapted | A1 M3 | Không có ranh giới hệ điều hành (F/B-07). Canary qua đường app thật với provider thật: chưa chạy. |
| [P-V2-02](#p-v2-02) | `RUN.json` thành projection kiểm được | adopted | A2 M4 | Không có anchor thì chỉ chứng minh nhất quán, không xác thực; nơi giữ anchor tin cậy chưa có (REPORT §4.3, §7… |
| [P-V2-03](#p-v2-03) | Làn release 2.0.x, metadata và quyền publish | adapted | A9 M4, A10 M4 | CI, staging, RC: M6 (chủ dự án). Action chưa ghim SHA. Trang PyPI của 2.0.0 chỉ đổi khi có bản phát hành mới. |
| [P-V2-04](#p-v2-04) | Sửa loader, preflight, redaction, phân loại lỗi môi trường | adopted | A3 M3, A4 M3, A5 M4, A6 M3, A7 M3, A8 M3 | Preflight thật mới chỉ tới loopback, chưa gặp redirect thật (REPORT §2 A6–A7). Điều kiện của A5 (khoá git của… |
| [P-V2-05](#p-v2-05) | Linux sandbox developer và candidate | blocked | F M6 | Toàn bộ. MỞ. |
| [P-V2-06](#p-v2-06) | PRESERVE trước merge + sửa spec import | adopted | B1 M3, B3 M3 | Contract S-10-a sửa: M6 (B-04 chưa duyệt). 'Biến thể hợp lệ không bị bác nhầm' chỉ kiểm cho hai bản nháp S-10… |
| [P-V2-07](#p-v2-07) | Bundle API/schema/example/coverage | adopted | B4 M4, B5 M4 | Chưa người ngoài nào thử (chưa đo). Độ phủ chỉ trên mệnh đề do tiêu chí khai — lint tự ghi 'AISEF does not pa… |
| [P-V2-08](#p-v2-08) | Tách compatibility và execution identity | adapted | B6 M3 | EXECUTION_DIGEST bỏ sót `runtime/process_range.py` và `range_anchor.py` — phát hiện 360 §3.1 vẫn đúng tại HEA… |
| [P-V2-09](#p-v2-09) | OCR adapter + confirmed finding feedback | adapted | C1 M4, C2 M4, C3 M4 | Chỉ 4/5 lỗi lịch sử neo được nên bị chặn; lỗi thứ năm (trích R-7/1, contract quan sát tệp) là UNANCHORED và t… |
| [P-V2-10](#p-v2-10) | Resume từ journal/checkpoint | adapted | D1 M4 | Resume tại chỗ: M6. Mất điện / OS sập không mô phỏng; trên macOS `fsync` không ép cache ổ. Tiến trình con đã … |
| [P-V2-11](#p-v2-11) | Cost ledger + no-progress limits | adapted | D2 M4, D3 M3 | Giá thật: M6. Không có trạng thái 'estimated' (chỉ known / partial / unknown). Request HTTP không kết thúc st… |
| [P-V2-12](#p-v2-12) | Replay corpus qua app và adapter contract | open | — | Toàn bộ. |
| [P-V2-13](#p-v2-13) | Paired experiment và holdout | blocked | E1 M3, E2 M6 | E2: MỞ. 'Held-out không được developer đọc' hiện chỉ phát hiện sau sự việc (`leaks` quét chuỗi đặc trưng), kh… |
| [P-V2-14](#p-v2-14) | Client thứ hai và `assess` độc lập | declined | — | Toàn bộ (2.2). |
| [P-ADJ-3](#p-adj-3) | LLM finding chưa xác minh chỉ phản hồi; lỗi đã xác minh, thuộc phạm vi, mức nghiêm trọng … | adapted | C1 M4 | Mặc định (không khai `review`) vẫn advisory. Neo sai khi một stimulus mới bị xếp sai mệnh đề (ADR-7). |
| [P-ADJ-4](#p-adj-4) | Đưa Linux sandbox tối thiểu trước thí nghiệm dùng hidden tests; macOS native làm sau | blocked | F M6, E2 M6 | Sandbox: MỞ. |
| [P-ADJ-5](#p-adj-5) | Dùng 1–3 lượt để canary; phép so sánh hiệu quả phải có thêm lượt lặp có ngân sách | blocked | E2 M6 | Live: MỞ. |
| [P-ADJ-6](#p-adj-6) | Làm sau; nếu tái sử dụng evidence phải tính cả phụ thuộc và công cụ kiểm | adopted | — | Chiến dịch chưa xong: tại HEAD không có kết quả mutation 2.1 nào để tuyên bố. |
| [P-4.2a](#p-42a) | Reviewer trả thiếu manifest hoặc schema lạ → `INDETERMINATE`, không coi là review sạch. | adopted | C2 M4 | Tiêu chí chỉ đạt dưới `fix-loop`: dưới `advisory` — cũng là luật khi settings không khai `review` (ADR-V2.1) … |
| [P-4.2b](#p-42b) | Không lấy tập `selected` của OCR làm toàn bộ phạm vi bắt buộc một cách mặc nhiên | adapted | C2 M4 | Tệp bắt buộc bị loại vì extension hay nhị phân không được review mà review vẫn có thể COMPLETE. Không test nà… |
| [P-4.2c](#p-42c) | Không cho reviewer quyền commit, merge, thay contract hay cập nhật verdict. | adopted | — | Không có ranh giới OS: finder chạy dưới cùng user; thay đổi bị phát hiện và loại, không bị ngăn (REPORT §3). |
| [P-4.3a](#p-43a) | Nếu finding phát hiện một yêu cầu chưa có trong contract, tạo **đề xuất sửa contract có p… | open | — | Toàn bộ phần tạo đề xuất. |
| [P-4.3b](#p-43b) | Reproducer chạy thành công **chưa đủ**: còn phải xác nhận kỳ vọng của nó đúng theo requir… | adopted | C1 M4 | Giới hạn đã đo: stimulus mới xếp sai mệnh đề vẫn neo được (test_known_limit_…). |
| [P-4.3c](#p-43c) | Branch đích đổi thì dựng cây tích hợp mới và kiểm lại. | adopted | — | Không còn so với tiêu chí trên: sau merge, mọi obligation của story và PRESERVE của các story đã commit được … |
| [P-5.2a](#p-52a) | AISEF phải tự chạy lệnh đánh giá được cố định, đọc kết quả có schema và ràng buộc digest. | adopted | E1 M3 | Chưa chạy trên workload thật (E2). |
| [P-5.2b](#p-52b) | Có thể dùng để nhắc agent còn việc; không dùng thay acceptance hoặc để cấp `delivery_verd… | declined | — | — |
| [P-5.2c](#p-52c) | AISEF cần tạo run con, giữ parent và bằng chứng cũ. | adopted | D1 M4 | Claimant ở máy khác: chỉ thay khi người vận hành nêu sha256 của claim (REPORT §4.2). |
| [P-5.3a](#p-53a) | Checkpoint tối thiểu nên chứa các tham chiếu: `run_id`, `attempt_id`, `journal_sequence`,… | open | D4 M6 | Toàn bộ. MỞ. Nếu làm, tránh hai lỗi đã thấy ở upstream: agent chính ghi được checkpoint (N-04), writer chép n… |
| [P-5.3b](#p-53b) | Hành động merge/commit phải có operation ID để không lặp tác dụng khi crash xảy ra giữa t… | adapted | D1 M4 | Nhận diện dựa vào quy ước của kernel (tên worktree, thông điệp merge); một commit tay giống quy ước chưa được… |
| [P-5.3c](#p-53c) | nếu một số bước liên tiếp không tạo thay đổi mã, bằng chứng mới hoặc giả thuyết mới có că… | adapted | D3 M3 | Đơn vị đo là attempt (cùng lỗi), không phải bước/lượt trong một phiên; ngưỡng chưa hiệu chỉnh. |
| [P-6.2a](#p-62a) | Mỗi thử nghiệm cần khóa các trường sau trước khi chạy: | adapted | E1 M3 | `harness.check` không đòi nội dung các trường §6.2 liệt kê: Workload ID, baseline commit, candidate snapshot … |
| [P-6.2b](#p-62b) | Không suy ra danh tính model thực chỉ từ chuỗi tên provider trả về. | adopted | E1 M3 | Chỉ trong harness thí nghiệm; preflight của `aisef run` không đổi trong 2.1 về điểm này. |
| [P-6.2c](#p-62c) | Tránh đưa dashboard, multi-cloud scheduler hoặc hàng loạt compute backend vào đường găng … | declined | — | — |
| [P-7a](#p-7a) | Giới hạn tiền kiểm trước lượt kế tiếp nên có thể vượt trần bởi một request đang thực hiện… | adopted | — | Không đặt trước ngân sách request; sai số không được định lượng. |
| [P-7b](#p-7b) | Đối chứng chính phải là cùng model, client, nhiệm vụ và tài nguyên chạy trực tiếp. mini l… | adapted | E1 M3 | Cánh mini: chưa làm. |
| [P-7c](#p-7c) | MVP nên là Linux executor, có thể điều khiển từ máy macOS. | blocked | F M6 | Toàn bộ. MỞ. |
| [P-8](#p-8) | Mũi tên phản hồi về kernel không cho phép plugin trực tiếp ghi verdict. | adopted | — | Checker là phân tích tĩnh trên mã Python; tiến trình ngoài (OCR) không bị ràng buộc ở mức OS. |
| [P-9.1](#p-91) | CLI dự kiến, **chưa tồn tại trong v2.0 theo báo cáo**: | adapted | B4 M4, B5 M4, D1 M4 | `assess --candidate`: chưa có. |
| [P-9.3](#p-93) | Positive controls: nhiều triển khai đúng khác cấu trúc vẫn pass. | open | — | Toàn bộ, trừ S-10-a. |
| [P-11.1](#p-111) | Cùng coding client/model chạy trực tiếp, cùng task và sandbox | blocked | E1 M3, E2 M6 | E2: MỞ; sandbox chung: MỞ. |
| [P-11.2](#p-112) | Canary trước: một story, ngân sách nhỏ, đi qua cài package → CLI → client → probe → revie… | blocked | — | Canary live: MỞ. Bước 'cài package' chưa có trong lượt offline. |
| [P-11.3](#p-113) | Cost ledger phải phân biệt input không cache, cache-read, cache-write và output; reasonin… | adopted | D2 M4 | Phép đo chỉ cho một phiên bản client (OpenCode 1.18.31 theo 360 §3.5); client/provider khác phải đo lại. Chưa… |
| [P-12-1](#p-12-1) | Controller/runtime/evidence/key ở miền developer không ghi được; workload không cùng quyề… | blocked | F M6 | Toàn bộ. MỞ. |
| [P-12-2](#p-12-2) | `-S` có kiểm thử đường app thật và cách nạp dependency rõ ràng. | adopted | A1 M3 | Không có lượt live qua đường app thật. |
| [P-12-3](#p-12-3) | Candidate code chạy trong tiến trình/môi trường riêng, không được nạp vào process giữ khó… | adopted | — | Cùng user: không phải môi trường riêng ở mức OS. |
| [P-12-4](#p-12-4) | Journal hash chain phát hiện một số sửa đổi khi có checkpoint đáng tin; không tự chống kẻ… | adopted | A2 M4, D5 M4 | Nơi giữ anchor tin cậy chưa có (REPORT §7). |
| [P-12-5](#p-12-5) | Git tree, image và artifact digest kiểm ngay tại ranh giới sử dụng, không chỉ khi người v… | adapted | — | Cùng user: giữa lúc kiểm và lúc dùng vẫn có thể bị thay (TOCTOU) — chỉ ranh giới OS đóng được. |
| [P-GATE-2.0.1](#p-gate-201) | **2.0.1:** reproducer lỗi đã biết được xử lý; release lane và metadata đúng; loader/prefl… | blocked | A11 M3 | Gate chưa đạt. |
| [P-GATE-2.1](#p-gate-21) | **2.1 pilot:** người ngoài tạo và chạy bundle nhỏ; một workload chưa thấy hoàn tất không … | open | F M6, E2 M6, D1 M4, C1 M4, D2 M4 | Sáu trên bảy điều kiện chưa đạt hoặc chưa đo. |
| [P-GATE-2.2](#p-gate-22) | **2.2 mở rộng:** thêm client và chế độ kiểm PR/candidate độc lập sau khi có bằng chứng pi… | declined | — | Toàn bộ (2.2). |
| [P-13-1](#p-13-1) | Viết lại toàn bộ kernel bằng framework khác hoặc kết hợp ba orchestrator vào một runtime. | declined | — | — |
| [P-13-2](#p-13-2) | Cho LLM tự sửa acceptance, tự cấp approval hoặc tự kết luận metric đạt. | declined | — | — |
| [P-13-3](#p-13-3) | Chạy nhiều developer song song trước khi sửa PRESERVE, resume và ranh giới ghi. | declined | — | — |
| [P-13-4](#p-13-4) | Mở thêm Q/mutation để tăng con số thay vì tái hiện lỗi sử dụng. | declined | — | — |
| [P-13-5](#p-13-5) | Dùng AST hash như chứng minh đủ của tương đương chương trình. | declined | — | — |
| [P-13-6](#p-13-6) | Xây memory tự học xuyên dự án trước khi có nguồn gốc, phạm vi và kiểm soát rò hidden test. | declined | — | — |
| [P-13-7](#p-13-7) | Dashboard lớn, nhiều compute backend và sandbox Windows trước bằng chứng hiệu quả trên Li… | declined | — | — |
| [R-P0-1](#r-p0-1) | Chạy controller và test runner với `-S` | adopted | A1 M3 | Chưa đo một vụ giả mạo end-to-end qua `.pth` trong `aisef run` thật (360 §9) — giờ đã đóng ở mức cơ chế, OS c… |
| [R-P0-2](#r-p0-2) | Trang PyPI đúng 2.0: README V2 làm long description, liên kết tuyệt đối, summary/classifi… | adapted | A10 M4 | Trang PyPI của 2.0.0 không đổi được nếu không phát hành (B-02); B-10 chưa quyết. |
| [R-P0-3](#r-p0-3) | Làn vá 2.0.x: tham số hoá `release_rc.py`/`v2_release_gate.py` theo phiên bản; runbook vá… | adapted | A9 M4 | Runbook vá (3 tầng) và runbook yank: chưa có. |
| [R-P0-4](#r-p0-4) | Người duyệt bắt buộc cho môi trường `pypi`, bảo vệ tag `v*`, ghim SHA mọi action | open | — | Toàn bộ. |
| [R-P0-5](#r-p0-5) | gỡ hoặc thay mọi liên kết GitHub trên aisef.io, salekit và `project.urls` của PyPI | adapted | — | Link trên landing, salekit, README.vi: còn. |
| [R-P1-6](#r-p1-6) | V21-37 + V21-38 cùng lúc: tiêu chí import theo AST; chứng minh PRESERVE của story trước *… | adopted | B1 M3, B3 M3 | Contract S-10-a: B-04 chưa duyệt. |
| [R-P1-7](#r-p1-7) | Công cụ bundle: API công khai + `aisef bundle init/seal/lint/rebind`, ví dụ ship kèm, tài… | adapted | B4 M4, B5 M4, B6 M3 | Người ngoài: chưa đo. |
| [R-P1-8](#r-p1-8) | Chính sách review: không chặn, nhưng **đưa phát hiện thành phản hồi cho developer**, ghi … | adapted | C1 M4 | Precision của reviewer: chưa đo. Precision/recall với mô hình thật: M6 (B-06, ngân sách). |
| [R-P1-9](#r-p1-9) | Bậc "độ đặc hiệu" cho spec: mỗi spec phải SATISFIED trên ≥2 cài đặt đúng độc lập + đối ch… | open | — | Toàn bộ, trừ S-10-a. |
| [R-P1-10](#r-p1-10) | Corpus "ghi thật" phát lại qua đường sản phẩm (`app.run.execute`, parser client thật, pre… | open | — | Toàn bộ. |
| [R-P1-11](#r-p1-11) | Điểm dữ liệu thứ hai **có giá tiền**: cùng bundle, model khác (0 dòng mã) + lặp lại DeepS… | blocked | E2 M6 | Live: MỞ. |
| [R-P1-12](#r-p1-12) | Giới hạn developer: ít nhất kiểm toán "tầm với" vào `RUN.json` và đưa bundle ra khỏi thư … | blocked | A2 M4, F M6 | Sandbox: MỞ. |
| [R-P1-13](#r-p1-13) | Bộ nạp an toàn: mọi lỗi đầu vào → mã 2 kèm đường dẫn JSON; `--check` trả đúng lý do B4; e… | adopted | A3 M3, A4 M3, A5 M4, A6 M3, A7 M3, A8 M3 | Như P-V2-04: Preflight thật mới chỉ tới loopback, chưa gặp redirect thật (REPORT §2 A6–A7). Điều kiện của A5 … |
| [R-P2-14](#r-p2-14) | Tách 1.x thành `aisef-legacy` (hoặc chỉ giữ `aisef legacy …`); `doctor` biết V2 | declined | — | Toàn bộ (2.2). |
| [R-P2-15](#r-p2-15) | Client thứ hai (Claude Code hoặc Codex CLI); probe chạy với phụ thuộc đã khoá của dự án | declined | — | Toàn bộ (2.2). |
| [R-P2-16](#r-p2-16) | Định vị lại thành **nhân kiểm chứng / cổng chấp nhận** dùng được cho PR của bất kỳ agent … | declined | — | Toàn bộ (2.2). |
| [R-P2-17](#r-p2-17) | Chính sách phát hành cân xứng: tầng vá, một canary live rẻ ở **đầu** mỗi RC, ngân sách tr… | blocked | — | Chính sách chưa được duyệt. |
| [R-P2-18](#r-p2-18) | Ăn kiêng bằng chứng: digest + tóm tắt trong git, luồng phiên thô và chunk Q4 sang release… | declined | — | Toàn bộ. |
| [R-P2-19](#r-p2-19) | Mutation: ràng buộc theo AST của từng hàm thay vì sha256 nguyên file; thêm toán tử xoá câ… | declined | — | Toán tử xoá câu lệnh / biên số / handler: chưa có. |
| [R-P2-20](#r-p2-20) | Giảm bus factor: runbook người bảo trì trong repo; một người review kernel không phải chủ… | open | — | Toàn bộ. |
| [R-NOW](#r-now) | **Không làm bây giờ (nói ra để khỏi bị hút vào)**: thêm bậc Q, chạy lại Q4 với cùng seed,… | adapted | — | Không còn việc với mục này (danh sách 'không làm'); điều chỉnh duy nhất là mutation, theo RELEASE-DECISIONS s… |
| [R-3.1](#r-31) | Băm lại bỏ sót `runtime/process_range.py`, `range_anchor.py` — mã quyết định quan sát có … | open | — | Toàn bộ. Sửa sẽ chạm `aisef2/probe` (kernel): cần mutation + hiệu chuẩn lại, ngoài snapshot đang đo. |
| [R-M1](#r-m1) | Lượt live đạt `delivery_verdict PASS` (không miễn trừ) | blocked | — | Chưa đạt: 0 lượt live trong 2.1 (mục tiêu ≥ 1 trên workload chưa từng thấy). |
| [R-M2](#r-m2) | Workload × route × hệ điều hành đã chạy live | blocked | — | Chưa đạt: vẫn 1 × 1 × macOS, không có Linux (mục tiêu ≥ 2 × 2, có Linux). |
| [R-M3](#r-m3) | Lỗi do review tìm thấy mà vẫn vào `main` | blocked | — | Chưa đo live, chưa báo cạnh 59/59. Offline: 1/5 dạng lỗi lịch sử (R-7/1) UNANCHORED nên vẫn lọt gate (P-V2-09… |
| [R-M4](#r-m4) | Mệnh đề requirement được contract phủ | open | — | RUN.json chưa mang độ phủ: mục tiêu 2.1 chưa đạt (chỉ `aisef bundle lint` báo, trên mệnh đề do tiêu chí khai). |
| [R-M5](#r-m5) | Đọc ra ngoài workspace của developer | blocked | — | Chưa đo; không có ranh giới hệ điều hành (F/B-07). |
| [R-M6](#r-m6) | USD / story giao được | blocked | — | Chưa có số: 0 lượt live để chia USD cho story giao được. |
| [R-M7](#r-m7) | Thời gian từ bản vá đến PyPI | blocked | — | Chưa đo: chưa phát hành bản nào trong 2.1 (B-02). |
| [R-M8](#r-m8) | Người dùng ngoài | open | — | Chưa đạt: 0 người dùng ngoài theo những gì repo cho biết (mục tiêu ≥ 1 đối tác thiết kế). |
| [R-M9](#r-m9) | Mục backlog có reproducer | open | — | Chưa đo lại: 38 mục của `docs/v2/V2.1-BACKLOG.md` chưa được đối chiếu với tiêu chí 'có reproducer'. |

## Từng hàng

### P-V2-01

> Đóng startup injection và tách trusted runtime

- **Nguồn:** đề xuất §10 V2-01; §3 bảng điều chỉnh, hàng `.pth`
- **Bằng chứng tại HEAD:** Mọi lần khởi chạy probe đang hoạt động mang `-I -S` (cli_invocation, python_callable_v2, process_effect); probe chạy trên `sys.executable` ngoài thư mục lượt chạy, test của developer trên `<out>/test-python` (ADR-1). Trên 610a593 `.pth` chạy trong probe (STATUS A1: đo). Nhánh 2.0.1 (`c0ec1a5`, chưa phát hành): hai venv, không có `-S`.
- **Kiểm cơ học:** `aisef2/probe/process_effect.py` chứa `"-I", "-S", "-B"`; `docs/v2.1/STATUS.md` chứa `` `.pth` do mã test ghi chạy trong probe ``
- **Reproducer:** `tests/v2/test_v21_identity.py::PthChannel::test_the_mechanism_minus_I_runs_it_minus_S_does_not`, `tests/v2/test_v21_identity.py::PthChannel::test_every_active_probe_launch_carries_minus_S`, `tests/v2/test_v21_identity.py::PthChannel::test_a_probe_on_an_interpreter_holding_a_pth_never_runs_it`, `tests/v2/test_v21_identity.py::PthChannel::test_the_run_gives_the_probes_this_interpreter_and_the_tests_their_own`, `f006d3d1b23ef9d318078642d16c7bdfa7687a98:tests/v2/test_v201_venvs.py::TwoVenvs::test_a_pth_written_from_the_tests_interpreter_never_runs_in_a_probe`
- **Ảnh hưởng:** cao: kênh để mã ứng viên chạy bên trong controller giữ khoá HMAC (360 §3.4)
- **Quyết định:** adapted — Nhận `-S` + interpreter của kernel; loại băm cây venv (TOCTOU) đúng như §3 của đề xuất. Nửa sau (tách trusted runtime khỏi nơi developer ghi được) KHÔNG đạt: developer và test chạy cùng user (REPORT §3).
- **Commit:** `919a271`: aisef2/probe/cli_invocation.py, aisef2/probe/python_callable_v2.py, aisef2/probe/process_effect.py, aisef2/app/run.py, tests/v2/test_v21_identity.py; `c0ec1a5` (trên `f006d3d`): aisef2/app/run.py, tests/v2/test_v201_venvs.py
- **Mức (REPORT §2):** A1 = M3 — Khớp REPORT. Test tồn tại tại HEAD (kiểm bằng AST); không chạy lại trong phiên lập bảng.
- **Tiêu chí nghiệm thu:** `.pth` không chạy trong controller; developer không ghi được interpreter/import tree của verifier; chạy canary qua đường app thật
- **Còn thiếu:** Không có ranh giới hệ điều hành (F/B-07). Canary qua đường app thật với provider thật: chưa chạy.

### P-V2-02

> `RUN.json` thành projection kiểm được

- **Nguồn:** đề xuất §10 V2-02
- **Bằng chứng tại HEAD:** `--verify` dựng lại outcome từ journal, settings qua `runspec_hash`, chi tiêu từ luồng phiên + ledger preflight; trường chỉ có trong record chỉ được hạ verdict; `EVIDENCE.json` + anchor, `--expect-anchor` (ADR-3). Lượt CLI thật trên b72e51e (cây sạch): hai lần `--verify --expect-anchor` VERIFIED.
- **Kiểm cơ học:** `docs/v2.1/evidence/cli-integration-b72e51e.out` chứa `commit: b72e51eadd87bee56b916c70c4ac24649f49071e dirty: 0`; `docs/v2.1/evidence/cli-integration-b72e51e.out` chứa `"verdict": "VERIFIED"`; `docs/v2.1/evidence/cli-integration-c9c736f.out` (đi cùng bảng) chứa `commit: c9c736fd638511b5cfd23d4d75ceb311c47b0759 dirty: 0`; `docs/v2.1/evidence/cli-integration-c9c736f.out` (đi cùng bảng) chứa `"verdict": "VERIFIED"`
- **Reproducer:** `tests/v2/test_v21_verify.py::RecordAlone::test_a_budget_stop_removed_from_the_record_is_refuted`, `tests/v2/test_v21_verify.py::RecordAlone::test_raising_the_ceiling_in_the_record_is_refuted`, `tests/v2/test_v21_verify.py::RecordAlone::test_story_outcomes_that_are_not_the_journal_s_are_refuted`, `tests/v2/test_v21_verify.py::RecordAlone::test_a_rewritten_manifest_is_refuted_only_against_the_anchor_the_operator_kept`, `tests/v2/test_v21_continue_integrity.py::AnchorThreatModel::test_the_limit_an_attacker_who_can_write_the_store_too_is_not_detected`
- **Ảnh hưởng:** cao: trên 2.0 sửa riêng `RUN.json` vẫn VERIFIED (STATUS A2: đo)
- **Quyết định:** adopted — Đúng phạm vi đề xuất; không đổi format journal.
- **Commit:** `ad78ce7`: aisef2/app/verify.py, aisef2/app/run.py, aisef2/app/cli.py, tests/v2/test_v21_verify.py; `d622e71`: aisef2/app/verify.py, aisef2/app/usage.py; `872e83c`: aisef2/app/lineage.py, aisef2/app/verify.py
- **Mức (REPORT §2):** A2 = M4 — Khớp REPORT: output CLI đã commit có hai VERIFIED với `--expect-anchor`.
- **Tiêu chí nghiệm thu:** Sửa riêng trường outcome/budget/error trong RUN bị phát hiện; tái dựng từ nguồn chuẩn đầy đủ
- **Còn thiếu:** Không có anchor thì chỉ chứng minh nhất quán, không xác thực; nơi giữ anchor tin cậy chưa có (REPORT §4.3, §7).

### P-V2-03

> Làn release 2.0.x, metadata và quyền publish

- **Nguồn:** đề xuất §10 V2-03
- **Bằng chứng tại HEAD:** `release_rc`/`v2_release_gate` theo phiên bản trong pyproject (aa3c18a); metadata mô tả 2.x, `license = "MIT"`, tệp LICENSE, bỏ link tới repo private (b819a57). Action trong workflow vẫn ghim theo tag (`actions/checkout@v4`, `pypa/gh-action-pypi-publish@release/v1`), không theo SHA; không commit 2.1 nào sửa `.github/`.
- **Kiểm cơ học:** `.github/workflows/release.yml` chứa `pypa/gh-action-pypi-publish@release/v1`; `.github/workflows/release.yml` không đổi so với `610a593`; `pyproject.toml` chứa `license = "MIT"`
- **Reproducer:** `tests/v2/test_v21_release_lane.py::Subject::test_a_patch_version_has_its_own_candidates_never_2_0_0_s`, `tests/v2/test_v21_release_lane.py::Freeze::test_freeze_writes_the_version_s_next_candidate_and_never_rewrites_one`, `tests/v2/test_v21_release_lane.py::Gate::test_a_patch_passes_on_its_own_status_and_candidate`
- **Ảnh hưởng:** trung bình: không phát hành nổi 2.0.1 nếu không sửa công cụ (360 §3.7)
- **Quyết định:** adapted — Nhận phần công cụ + metadata. 'CI action ghim' chưa làm; 'quyền phát hành có kiểm soát' (người duyệt môi trường `pypi`, bảo vệ tag) là thiết lập GitHub của chủ dự án.
- **Commit:** `aa3c18a`: validation/qualification/release_rc.py, validation/v2_release_gate.py, tests/v2/test_v21_release_lane.py; `b819a57`: pyproject.toml, LICENSE, validation/v2/packaging_check.py
- **Mức (REPORT §2):** A9 = M4, A10 = M4 — Khớp REPORT (M4 = build + `packaging_check` tại máy; CI/RC là M6).
- **Tiêu chí nghiệm thu:** Dựng bản vá không sửa hardcode phiên bản; metadata đúng; CI action ghim; quyền phát hành có kiểm soát
- **Còn thiếu:** CI, staging, RC: M6 (chủ dự án). Action chưa ghim SHA. Trang PyPI của 2.0.0 chỉ đổi khi có bản phát hành mới.

### P-V2-04

> Sửa loader, preflight, redaction, phân loại lỗi môi trường

- **Nguồn:** đề xuất §10 V2-04
- **Bằng chứng tại HEAD:** Đầu vào sai ⇒ mã thoát 2 + đường dẫn JSON; endpoint loopback phân tích thật; `--check` clone như lượt chạy (106f72d). Preflight không theo redirect; luồng phiên được che dù ngắt (b029236). `git diff` lỗi ⇒ RESOURCE_ACQUISITION_FAILED, owner ENVIRONMENT, retry được (51c5241, 4ea4276).
- **Kiểm cơ học:** `validation/v21/cli_integration/run.sh` chứa `git init -q -b main`
- **Reproducer:** `tests/v2/test_v21_inputs.py::BundleShape::test_product_roots_as_a_string_is_not_split_into_letters`, `tests/v2/test_v21_inputs.py::InputFiles::test_cli_exit_2_for_unreadable_inputs`, `tests/v2/test_v21_inputs.py::Endpoint::test_lookalike_hosts_are_refused`, `tests/v2/test_v21_inputs.py::RepositoryRefusal::test_an_editor_key_does_not_make_check_claim_the_baseline_is_missing`, `tests/v2/test_v21_transport.py::Redirect::test_a_redirect_is_refused_and_the_key_never_reaches_its_target`, `tests/v2/test_v21_transport.py::Redaction::test_an_interrupted_session_still_leaves_no_secret`, `tests/v2/test_v21_orchestration.py::DiffFailure::test_a_diff_git_cannot_produce_is_RESOURCE_ACQUISITION_FAILED`
- **Ảnh hưởng:** cao (khoá API tới đích redirect; bí mật còn trong bằng chứng sau ngắt) đến thấp (`--check` báo sai lý do) — STATUS §1
- **Quyết định:** adopted — Đúng đề xuất và 360 #13.
- **Commit:** `106f72d`: aisef2/app/bundle.py, aisef2/app/settings.py, aisef2/app/run.py, tests/v2/test_v21_inputs.py; `b029236`: aisef2/app/preflight.py, aisef2/app/client.py, tests/v2/test_v21_transport.py; `51c5241`: aisef2/orchestrate/story_runner.py, aisef2/orchestrate/workspace.py, tests/v2/test_v21_orchestration.py; `4ea4276`: aisef2/orchestrate/story_runner.py
- **Mức (REPORT §2):** A3 = M3, A4 = M3, A5 = M4, A6 = M3, A7 = M3, A8 = M3 — Khớp REPORT. Lưu ý khi kiểm lại: M4 của A5 dựa vào `--check` ready qua CLI thật, nhưng repo của lượt đó được dựng bằng `git init` sạch, HOME riêng (validation/v21/cli_integration/run.sh) — không có khoá git của editor; M4 cho thấy đường clone chạy qua CLI thật, điều kiện của A5 chỉ được tái hiện ở test (M3).
- **Tiêu chí nghiệm thu:** Dữ liệu sai có lỗi vị trí; redirect không làm lộ auth; log đã redact kể cả lỗi/ngắt có xử lý; git lỗi không giả thành product defect
- **Còn thiếu:** Preflight thật mới chỉ tới loopback, chưa gặp redirect thật (REPORT §2 A6–A7). Điều kiện của A5 (khoá git của editor) chỉ tái hiện ở test (M3): repo của lượt CLI thật (`git init` sạch) không có khoá đó.

### P-V2-05

> Linux sandbox developer và candidate

- **Nguồn:** đề xuất §10 V2-05
- **Upstream:** opensandbox-group/OpenSandbox@c7dc78a4090e `manager.go:253-296; config.py:1005; example.config.toml:98` — INFERENCE (kiểm chứng: confirmed; claim P10)
- **Bằng chứng tại HEAD:** Không có mã cách ly nào tại HEAD (REPORT §2 F, §6). REPORT §6 ghi một phép đo môi trường (bwrap trong container chỉ chạy khi nới seccomp/apparmor/systempaths) — không có bản ghi đã commit cho phép đo đó.
- **Kiểm cơ học:** `docs/v2.1/REPORT.md` chứa `chưa có mã cách ly nào trên nhánh`
- **Reproducer:** Không có (chưa triển khai).
- **Ảnh hưởng:** cao: developer đọc được stimulus ẩn, bundle, journal (DEVELOPER-CONFINEMENT-GAP-001; 360 §3.4: 69 lời gọi / 4 phiên ở smoke #2)
- **Quyết định:** blocked — Chưa có mã; phương án ranh giới (a container là ranh giới / b bwrap trong container đã nới / c máy-VM riêng) chờ chủ dự án (REPORT §7 hàng F; khuyến nghị (a) chưa đo).
- **Mức (REPORT §2):** F = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Bài kiểm truy cập hidden bundle/runtime/key bị từ chối; không chạm host process; egress theo policy
- **Còn thiếu:** Toàn bộ. MỞ.

### P-V2-06

> PRESERVE trước merge + sửa spec import

- **Nguồn:** đề xuất §10 V2-06
- **Bằng chứng tại HEAD:** PRESERVE của story đã commit được chứng minh ở candidate ⇒ CONTRACT_UNSATISFIED, owner DEVELOPER, retry, tiêu chí vào prompt retry (ADR-4, 91a8968); vẫn chứng minh lại sau merge cho thay đổi do merge (INTEGRATION). Lớp `python_imports` đếm import bằng `ast` (06d4e62); contract S-10-a sửa chỉ là bản nháp chưa duyệt.
- **Kiểm cơ học:** `aisef2/probe/file_artifact.py` chứa `CLASSES = ("exists", "content", "grep_count", "python_imports")`; `docs/v2.1/drafts/LEDGERLOCK-BC-V22-S-10-a-r2.DRAFT.json` tồn tại
- **Reproducer:** `tests/v2/test_v21_orchestration.py::PreserveAtCandidate::test_a_regression_the_developer_made_is_the_developer_s_and_never_merged`, `tests/v2/test_v21_orchestration.py::PreserveAtCandidate::test_a_retry_that_repairs_it_commits`, `tests/v2/test_v21_python_imports.py::Controls::test_the_approved_regex_reproduces_the_false_rollback`, `tests/v2/test_v21_python_imports.py::Controls::test_each_draft_holds_on_the_smoke2_shape_and_refutes_a_real_import`, `tests/v2/test_p6_orchestration.py::Orchestration::test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back`
- **Ảnh hưởng:** cao: smoke #2 rollback sai một story đúng (V21-37); lỗi hồi quy của developer thành INTEGRATION, không chạy lại (V21-38)
- **Quyết định:** adopted — Đúng đề xuất; contract LedgerLock không tự sửa — chủ dự án chọn A/B (B-04).
- **Commit:** `91a8968`: aisef2/orchestrate/story_runner.py, tests/v2/test_v21_orchestration.py; `06d4e62`: aisef2/probe/file_artifact.py, tests/v2/test_v21_python_imports.py, docs/v2.1/drafts/LEDGERLOCK-BC-V22-S-10-a-r2.DRAFT.json
- **Mức (REPORT §2):** B1 = M3, B3 = M3 — Khớp REPORT. Test tồn tại tại HEAD (kiểm bằng AST); không chạy lại trong phiên lập bảng.
- **Tiêu chí nghiệm thu:** Candidate làm hỏng story trước nhận phản hồi đúng; biến thể hợp lệ/docstring không bị bác nhầm; vẫn kiểm cây tích hợp khi base đổi
- **Còn thiếu:** Contract S-10-a sửa: M6 (B-04 chưa duyệt). 'Biến thể hợp lệ không bị bác nhầm' chỉ kiểm cho hai bản nháp S-10-a trên dạng smoke #2, không tổng quát (xem P-9.3).

### P-V2-07

> Bundle API/schema/example/coverage

- **Nguồn:** đề xuất §10 V2-07
- **Bằng chứng tại HEAD:** `aisef bundle init/seal/approve/lint/explain`, JSON Schema `aisef-v2-authoring/1`, hai ví dụ ship trong wheel (1 story, 3 story) (620bde7). Lượt CLI thật b72e51e: seal → approve ×3 → lint READY → `--check` ready; bundle thứ hai seal → approve ×4.
- **Kiểm cơ học:** `docs/v2.1/evidence/cli-integration-b72e51e.out` chứa `"verdict": "READY"`; `pyproject.toml` chứa `"aisef2" = ["app/examples/*.json"]`; `docs/v2.1/evidence/cli-integration-b72e51e.out` chứa `AISEF does not parse the requirements document`; `aisef2/app/bundle_cli.py` @ b72e51e không chứa `def _create(`; `aisef2/app/bundle_cli.py` chứa `def _create(`; `docs/v2.1/evidence/cli-integration-c9c736f.out` (đi cùng bảng) chứa `"verdict": "READY"`; `docs/v2.1/evidence/cli-integration-c9c736f.out` (đi cùng bảng) chứa `AISEF does not parse the requirements document`
- **Reproducer:** `tests/v2/test_v21_bundle_tools.py::Outsider::test_each_example_from_init_to_a_ready_check`, `tests/v2/test_v21_bundle_tools.py::Schema::test_the_schema_and_the_tool_agree_on_every_closed_key_set`, `tests/v2/test_v21_bundle_tools.py::Refusals::test_an_uncovered_requirement_is_named_where_admission_refuses_it`, `tests/v2/test_v21_bundle_tools.py::Refusals::test_an_edited_contract_loses_its_approval_on_reseal`
- **Ảnh hưởng:** cao: không có đường soạn bundle được hỗ trợ (360 §3.6)
- **Quyết định:** adopted — Đúng đề xuất.
- **Commit:** `620bde7`: aisef2/app/bundle_cli.py, aisef2/app/examples/calc-1-story.json, aisef2/app/examples/calc-3-stories.json, docs/v2.1/bundle-authoring.schema.json, tests/v2/test_v21_bundle_tools.py
- **Mức (REPORT §2):** B4 = M4, B5 = M4 — Khớp REPORT: output đã commit có seal, approve, lint READY, `--check` ready. M4 là của lượt CLI thật tại `b72e51e` (docs/v2.1/evidence/cli-integration-b72e51e.out); `aisef2/app/bundle_cli.py` đổi sau lượt đó ở a912be6 và 3061ec0 (đường ghi của init/seal/approve/migrate chuyển sang tạo độc quyền `_create`), lượt lặp lại tại c9c736f (`docs/v2.1/evidence/cli-integration-c9c736f.out`, vòng 2 của bảng này: cùng `run.sh`, cùng nhị phân OCR, clone sạch tại c9c736f) cho cùng output — khác nhau chỉ ở giá trị băm (commit của repo `git init` mới, plan_hash, anchor, sha256), pid, mốc thời gian và dòng cuối bị cắt ở 3000 ký tự: M4 tại c9c736f.
- **Tiêu chí nghiệm thu:** Người ngoài tạo bundle 3 story không import private constructor; mọi mệnh đề có trạng thái coverage rõ
- **Còn thiếu:** Chưa người ngoài nào thử (chưa đo). Độ phủ chỉ trên mệnh đề do tiêu chí khai — lint tự ghi 'AISEF does not parse the requirements document'.
- **Chưa xác nhận được:** Tài liệu ngữ pháp contract cho 18 lớp quan sát: không kiểm trong phiên này.

### P-V2-08

> Tách compatibility và execution identity

- **Nguồn:** đề xuất §10 V2-08; §3 bảng điều chỉnh, hàng identity; §9.2
- **Bằng chứng tại HEAD:** Ba danh tính: `contract_hash` (approval), DIGEST = năng lực probe (spec, plan), EXECUTION_DIGEST = byte nguồn probe (hàng hiệu chuẩn, RunSpec) (ADR-2, 919a271); `aisef bundle migrate`. Chủ dự án duyệt V2-007 (RELEASE-DECISIONS seq 4, dc9774f — kỹ thuật chép, chủ dự án không ký). Tại HEAD, PROBE_SOURCES của process_effect là 4 tệp probe: `aisef2/runtime/process_range.py` (process_effect import) và `range_anchor.py` (process_range chạy) không nằm trong EXECUTION_DIGEST.
- **Kiểm cơ học:** `aisef2/probe/process_effect.py` chứa `PROBE_SOURCES = ("probe/protocol.py", "probe/python_callable.py", "probe/cli_invocation.py", "probe…`; `aisef2/probe/process_effect.py` chứa `from aisef2.runtime.process_range import ProcessRange`; `aisef2/runtime/process_range.py` chứa `ANCHOR = pathlib.Path(__file__).with_name("range_anchor.py")`; `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` chứa `AISEF_V2_1_B01_ARCHITECTURE_EXCEPTION_V2_007`
- **Reproducer:** `tests/v2/test_v21_identity.py::ThreeIdentities::test_a_spec_binds_the_capability_and_the_bytes_are_their_own_digest`, `tests/v2/test_v21_identity.py::ThreeIdentities::test_calibrations_of_other_bytes_admit_nothing`, `tests/v2/test_v21_identity.py::ThreeIdentities::test_the_runspec_binds_each_probe_s_bytes`, `tests/v2/test_v21_identity.py::Migrate::test_migration_rebinds_the_plan_and_nothing_else`, `tests/test_v21_bundle_dispatch.py::BundleIsV2::test_migrate_through_the_aisef_command`
- **Ảnh hưởng:** cao: trên 2.0 sửa một byte probe (kể cả docstring) làm gãy mọi bundle (360 §3.1, §3.10)
- **Quyết định:** adapted — Nhận tách ba danh tính; năng lực probe là CAPABILITY_VERSION tăng bằng tay, không băm AST (ADR-2: băm AST không chứng minh tương đương). Execution digest chỉ phủ byte nguồn probe, chưa phủ runtime/dependency như §9.2 mục 3.
- **Commit:** `919a271`: aisef2/probe/calibration.py, aisef2/app/calibrations.py, aisef2/app/bundle_cli.py, validation/qualification/release_calibration.py; `06d4e62`: aisef2/app/calibrations.py; `4d4c53a`: tests/v2/test_v21_identity.py; `16d85e7`: closure-evidence/v2/v2.1/ARCHITECTURE-EXCEPTION-V2-007.json, closure-evidence/v2/v2.1/AISEF-V2-RFC-AMENDMENT-V2-007.json; `dc9774f`: closure-evidence/v2/cycle2/RELEASE-DECISIONS.json
- **Mức (REPORT §2):** B6 = M3 — Khớp REPORT. Test tồn tại tại HEAD (kiểm bằng AST); không chạy lại trong phiên lập bảng.
- **Tiêu chí nghiệm thu:** Patch không đổi capability dùng được bundle cũ; đổi semantics bị chặn hoặc migrate có duyệt; run cũ kiểm được
- **Còn thiếu:** EXECUTION_DIGEST bỏ sót `runtime/process_range.py` và `range_anchor.py` — phát hiện 360 §3.1 vẫn đúng tại HEAD (xem R-3.1). Kỷ luật tăng CAPABILITY_VERSION không máy nào kiểm (ADR-2). Tuyên bố 'một `-S` làm đỏ 37 test' chưa đo (STATUS B6).

### P-V2-09

> OCR adapter + confirmed finding feedback

- **Nguồn:** đề xuất §10 V2-09; §4.1–4.3
- **Upstream:** alibaba/open-code-review@182898cf522d `internal/session/manifest.go:231-237, 854-858` — CODE (kiểm chứng: confirmed; claim P7); alibaba/open-code-review@182898cf522d `internal/session/manifest.go:165-170, 941-958` — CODE (kiểm chứng: confirmed; claim P8); alibaba/open-code-review@182898cf522d `cmd/opencodereview/review_cmd.go:326-352; internal/agent/agent.go:705-716` — CODE (kiểm chứng: corrected; claim P11); alibaba/open-code-review@182898cf522d `cmd/opencodereview/sarif.go:195-211, 288-297` — CODE (kiểm chứng: confirmed; claim N3); alibaba/open-code-review@182898cf522d `internal/agent/agent.go:479-482, 919-927` — CODE (kiểm chứng: confirmed; claim N6); alibaba/open-code-review@182898cf522d `người kiểm: EXPERIMENT pages/src/components/BenchmarkSection.tsx:43-56 (recall 11,7–20 %, precision 25,2–37,8 %)` — EXPERIMENT (kiểm chứng: refuted, người kiểm chứng phân lại; nghiên cứu ghi NOT_FOUND; claim N19)
- **Bằng chứng tại HEAD:** OCR v1.12.12 (182898c) chạy như tiến trình ngoài, ghim sha256, môi trường đã xoá biến OCR_/ANTHROPIC_/OTEL_; coverage do AISEF tính từ manifest, exit 0 không bao giờ là 'đã review đủ'; `finding_id` theo fingerprint SARIF; finding chỉ chặn khi CONFIRMED ∧ ANCHORED ∧ ≥ `min_severity` (ADR-7). Lượt CLI thật b72e51e: nhị phân OCR thật, settings `fix-loop` + `finder: ocr`, S1: RETRY → COMMIT, verify VERIFIED. `RealBinary` 3/3 OK với nhị phân OCR đã ghim, chạy lại tại c9c736f (vòng 2; `docs/v2.1/evidence/traceability-reproducers-c9c736f.out`).
- **Kiểm cơ học:** `docs/v2.1/evidence/cli-integration-b72e51e.out` chứa `ocr: open-code-review v1.12.12 (182898c) darwin/arm64 sha256 bf38abf320ead4e106b71c1582446364020711…`; `validation/v21/cli_integration/make_inputs.py` chứa `"review": {"policy": "fix-loop", "min_severity": "high", "finder": "ocr",`; `tests/v2/test_v21_review.py` chứa `{"repair-utf8-crash": V.UNANCHORED}`; `docs/v2.1/evidence/cli-integration-c9c736f.out` (đi cùng bảng) chứa `ocr: open-code-review v1.12.12 (182898c) darwin/arm64 sha256 bf38abf320ead4e106b71c1582446364020711…`; `docs/v2.1/evidence/traceability-reproducers-c9c736f.out` (đi cùng bảng) chứa `# run 2 summary: Ran 3 tests in`; `docs/v2.1/evidence/traceability-reproducers-c9c736f.out` (đi cùng bảng) chứa `tests.v2.test_v21_review_chain.RealBinary.test_a_full_review_against_a_scripted_model: ok`
- **Reproducer:** `tests/v2/test_v21_review.py::HistoricalDefects::test_each_shipped_defect_is_confirmed_on_its_shape_and_not_on_the_reference`, `tests/v2/test_v21_review_chain.py::IncompleteReview::test_partial`, `tests/v2/test_v21_review_chain.py::NotABlocker::test_a_finding_that_does_not_reproduce_does_not_block`, `tests/v2/test_v21_review_ocr.py::Coverage::test_exit_0_is_not_a_full_review`, `tests/v2/test_v21_review_ocr.py::Findings::test_ids_are_ocr_s_sarif_fingerprint_stable_under_order_and_numbered_when_repeated`, `tests/v2/test_v21_review_chain.py::RealBinary::test_a_full_review_against_a_scripted_model` `RealBinary` cần `AISEF_TEST_OCR_EXE`: bỏ qua trong suite hermetic (REPORT §4.1).
- **Ảnh hưởng:** cao: 5 lỗi review tìm thấy, tái hiện được, vẫn vào `main` (360 §3.5)
- **Quyết định:** adapted — Điều chỉnh: finding chỉ chặn khi CONFIRMED ∧ ANCHORED ∧ mức ≥ `min_severity` — điều kiện neo theo chỉ thị chủ dự án (xem P-ADJ-3, P-4.3b). Vì điều kiện đó, lỗi lịch sử thứ năm (UNANCHORED) vẫn lọt gate: tiêu chí '5 lỗi lịch sử không lọt gate' cố ý chỉ đạt 4/5.
- **Commit:** `e897437`: aisef2/app/review_ocr.py, aisef2/app/review_verify.py, aisef2/app/feedback.py, aisef2/orchestrate/review.py, tests/v2/test_v21_review.py, tests/v2/test_v21_review_ocr.py; `390f07c`: aisef2/app/review_verify.py, aisef2/app/review_ocr.py; `929598f`: tests/v2/test_v21_review_chain.py; `181d68e`: aisef2/app/adapters.py; `51f2eb5`: aisef2/app/review_ocr.py
- **Mức (REPORT §2):** C1 = M4, C2 = M4, C3 = M4 — Khớp REPORT về mức. Output đã commit xác nhận nhị phân OCR thật, settings fix-loop và S1 RETRY → COMMIT.
- **Tiêu chí nghiệm thu:** 5 lỗi lịch sử không lọt gate; partial review không PASS; false finding không tự thành blocker
- **Còn thiếu:** Chỉ 4/5 lỗi lịch sử neo được nên bị chặn; lỗi thứ năm (trích R-7/1, contract quan sát tệp) là UNANCHORED và theo luật neo vẫn lọt gate (ADR-7; test_v21_review.py dòng 8–9, 117). Chất lượng finding của mô hình thật: M6 (B-05, B-06).
- **Chưa xác nhận được:** Chuỗi 'finding ⇒ CONFIRMED ⇒ ANCHORED ⇒ REVIEW_FINDING' của REPORT §4.1 không có trong output đã commit (journal của lượt không được commit) — không xác nhận được từ repo.

### P-V2-10

> Resume từ journal/checkpoint

- **Nguồn:** đề xuất §10 V2-10
- **Upstream:** XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/workflow/runtime.ts:1562-1563, :588; persistence.ts:292-297` — CODE (kiểm chứng: confirmed; claim P-11); XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/workflow/runtime.ts:1539-1545; workflow.sql.ts:6-31` — CODE (kiểm chứng: confirmed; claim N-16); alibaba/open-code-review@182898cf522d `internal/session/resume_identity.go:79-128; cmd/opencodereview/review_cmd.go:182-188` — CODE (kiểm chứng: confirmed; claim P9)
- **Bằng chứng tại HEAD:** Thay resume tại chỗ bằng nối tiếp: `aisef bundle continue` + `aisef run --parent`; claim theo thế hệ (`O_EXCL`); tác dụng ngoài được đối soát với git; chi phí chưa đối soát chặn phiên trả tiền (ADR-8). Lượt CLI thật b72e51e: SIGKILL thật (exit 137) ⇒ continue ⇒ `--parent` bị từ chối (exit 2) ⇒ `--accept-unaccounted` ⇒ COMMIT ⇒ continue lần nữa bị từ chối ⇒ verify VERIFIED.
- **Kiểm cơ học:** `docs/v2.1/evidence/cli-integration-b72e51e.out` chứa `exit 137 (137 = SIGKILL)`; `docs/v2.1/evidence/cli-integration-b72e51e.out` chứa `is already continued by`; `docs/v2.1/evidence/cli-integration-c9c736f.out` (đi cùng bảng) chứa `exit 137 (137 = SIGKILL)`; `docs/v2.1/evidence/cli-integration-c9c736f.out` (đi cùng bảng) chứa `is already continued by`
- **Reproducer:** `tests/v2/test_v21_continue_integrity.py::CommitWindows::test_the_merge_moved_main_the_journal_never_committed_it`, `tests/v2/test_v21_continue_integrity.py::JournalAppendWindows::test_a_short_write_is_a_torn_tail_whose_effect_is_still_reconciled`, `tests/v2/test_v21_continue_integrity.py::ClaimLifecycle::test_two_runs_at_once_one_claims_and_the_other_spends_nothing`, `tests/v2/test_v21_continue_integrity.py::ProviderRequestWindows::test_its_usage_reported_its_result_never_journaled`, `tests/v2/test_v21_continue_integrity.py::ProcessesOfAKilledRun::test_the_probe_processes_are_identified_and_die_with_the_run`, `tests/v2/test_v21_continue_usage.py::Continue::test_a_continuation_verifies_given_its_directory_relative_or_absolute`
- **Ảnh hưởng:** cao: 2.0 không có đường resume (`--out` phải mới), một lượt dài hỏng là mất (360 §3.1, §3.7)
- **Quyết định:** adapted — Resume tại chỗ cần format journal mới (schema đóng) ⇒ chọn nối tiếp + dòng dõi (ADR-8). 'Đổi policy tạo lineage mới' đạt bằng run con.
- **Commit:** `d622e71`: aisef2/app/bundle_cli.py, aisef2/app/cli.py; `7e0aac0`: aisef2/app/bundle_cli.py, tests/v2/test_v21_continue_integrity.py; `872e83c`: aisef2/app/lineage.py, aisef2/app/bundle_cli.py; `b72e51e`: aisef2/app/lineage.py, validation/v21/cli_integration/run.sh
- **Mức (REPORT §2):** D1 = M4 — Khớp REPORT: output đã commit có exit 137, lần từ chối, VERIFIED.
- **Tiêu chí nghiệm thu:** Ngắt trước/sau commit và giữa probe; không commit/charge hai lần; chống hai process resume; đổi policy tạo lineage mới
- **Còn thiếu:** Resume tại chỗ: M6. Mất điện / OS sập không mô phỏng; trên macOS `fsync` không ép cache ổ. Tiến trình con đã `setsid` sống sau lượt bị giết (REPORT §4.2, §6).

### P-V2-11

> Cost ledger + no-progress limits

- **Nguồn:** đề xuất §10 V2-11
- **Upstream:** SWE-agent/mini-swe-agent@04d809ceab9d `src/minisweagent/agents/default.py:132, 148-150` — CODE (kiểm chứng: confirmed; claim P7); SWE-agent/mini-swe-agent@04d809ceab9d `src/minisweagent/models/litellm_model.py:110-125` — CODE (kiểm chứng: corrected; claim N2); SWE-agent/mini-swe-agent@04d809ceab9d `src/minisweagent/models/utils/retry.py:19-25` — CODE (kiểm chứng: confirmed; claim N3); alibaba/open-code-review@182898cf522d `cmd/opencodereview/output.go:270-280; internal/agent/estimate.go:92-93` — CODE (kiểm chứng: corrected; claim N14)
- **Bằng chứng tại HEAD:** `aisef2/app/usage.py`: token theo lớp (input, cache_read, cache_write, output, reasoning), request, retry, wall time; tiền chỉ khi bảng giá đủ khoá (có nguồn + ngày hiệu lực), không biết ⇒ `null`; phiên có step thiếu token ⇒ partial. `no_progress` chỉ báo cáo; retry do taxonomy quyết định.
- **Kiểm cơ học:** `aisef2/app/usage.py` chứa `` an unknown price is `null` with its reason, never 0 ``; `aisef2/app/usage.py` chứa `NO_SIDE_RETRY_COUNTER`; `docs/v2.1/evidence/cli-integration-b72e51e.out` chứa `"status": "unknown: some run's cost is not known (not 0)"`; `docs/v2.1/evidence/cli-integration-c9c736f.out` (đi cùng bảng) chứa `"status": "unknown: some run's cost is not known (not 0)"`
- **Reproducer:** `tests/v2/test_v21_continue_usage.py::Usage::test_without_prices_cost_is_unknown_never_zero`, `tests/v2/test_v21_continue_usage.py::Usage::test_with_prices_known_and_a_blind_step_makes_it_partial`, `tests/v2/test_v21_continue_usage.py::Usage::test_a_price_table_is_complete_or_refused`, `tests/v2/test_v21_continue_usage.py::Usage::test_retries_that_change_nothing_are_reported`
- **Ảnh hưởng:** cao với mọi quyết định ngân sách: trên 2.0 mọi bước giá 0 (360 §2, §3.5)
- **Quyết định:** adapted — Ledger nhận đủ. No-progress chỉ báo cáo, không phải 'limit' dừng lượt — dừng vẫn do trần ngân sách và taxonomy.
- **Commit:** `d622e71`: aisef2/app/usage.py, tests/v2/test_v21_continue_usage.py; `6634d6d`: aisef2/app/usage.py
- **Mức (REPORT §2):** D2 = M4, D3 = M3 — Khớp REPORT. D2 M4: output đã commit có `lineage_usage.cost` unknown, không bao giờ là tổng từng phần.
- **Tiêu chí nghiệm thu:** USD known/estimated/unknown rõ ràng; stop có lý do; giữ cả request lỗi và retry; không mặc định unknown = 0
- **Còn thiếu:** Giá thật: M6. Không có trạng thái 'estimated' (chỉ known / partial / unknown). Request HTTP không kết thúc step (retry của client, request lỗi) không có trong telemetry (`client.LIMITATION`) ⇒ 'giữ cả request lỗi' chưa đạt đầy đủ.

### P-V2-12

> Replay corpus qua app và adapter contract

- **Nguồn:** đề xuất §10 V2-12
- **Bằng chứng tại HEAD:** Không có corpus ghi thật phát lại qua `app.run.execute` tại HEAD: trong `git diff --name-only 610a593 c9c736f` không tệp nào mang tên replay/corpus/transcript. B-03d (`v21_q5_changes.py`) chỉ truy vết các mục corpus Q5 của 2.0 mà 2.1 đổi kỳ vọng.
- **Kiểm cơ học:** `validation/qualification/v21_q5_changes.py` chứa `every q5.CORPUS item whose expectation 2.1 changed or`
- **Reproducer:** Không có (chưa triển khai).
- **Ảnh hưởng:** cao: xanh offline hai lần không đoán được hành vi live (RC1 chết ở preflight; 360 §3.3)
- **Quyết định:** open — Chưa làm; không có quyết định nào được ghi lại.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** Transcript thật tái hiện parser/preflight/cancellation lỗi; fixture schema mới bị từ chối rõ ràng
- **Còn thiếu:** Toàn bộ.

### P-V2-13

> Paired experiment và holdout

- **Nguồn:** đề xuất §10 V2-13; §6
- **Upstream:** alphaXiv/OpenResearch@d52a05365622 `src/compute.rs:168-182, 41-49` — CODE (kiểm chứng: confirmed; claim P4); alphaXiv/OpenResearch@d52a05365622 `src/compute.rs:77-123` — CODE (kiểm chứng: confirmed; claim P5); alphaXiv/OpenResearch@d52a05365622 `src/local/experiments.rs:178-237` — CODE (kiểm chứng: confirmed; claim P7); alphaXiv/OpenResearch@d52a05365622 `src/compute.rs:46-47, 134; git.rs:162-171` — INFERENCE (kiểm chứng: confirmed; claim N1); alphaXiv/OpenResearch@d52a05365622 `src/model.rs:66-86; store.rs:229-250` — INFERENCE (kiểm chứng: confirmed; claim N18); SWE-agent/mini-swe-agent@04d809ceab9d `src/minisweagent/run/benchmarks/programbench.py:46-60, 107-115` — CODE (kiểm chứng: corrected; claim N10)
- **Bằng chứng tại HEAD:** `validation/experiments/harness.py`: manifest niêm phong (`aisef.experiment/1`), cặp chỉ khác biến đang thử (`pair_problems`), cánh direct do harness commit, evaluator ẩn + `leaks`, replay offline; nguồn là commit sạch. Không có lượt trả tiền nào (EXPERIMENT-PLAN: KẾ HOẠCH).
- **Kiểm cơ học:** `docs/v2.1/EXPERIMENT-PLAN.md` chứa `**Trạng thái: KẾ HOẠCH.**`
- **Reproducer:** `tests/v2/test_v21_experiment.py::Experiment::test_a_pair_differs_in_the_variable_under_test_only`, `tests/v2/test_v21_experiment.py::Experiment::test_the_source_is_a_clean_commit`, `tests/v2/test_v21_experiment.py::Experiment::test_the_direct_arm_from_task_to_evaluated_result_and_its_replay`, `tests/v2/test_v21_experiment.py::Experiment::test_a_session_that_saw_the_hidden_stimulus_invalidates_the_result`
- **Ảnh hưởng:** quyết định: chưa có đối chứng nào cho V2 (360 §3.5)
- **Quyết định:** blocked — Harness nhận (E1). Chiến dịch chặn trên ngân sách của chủ dự án (B-09: canary bậc 1–2 trần 5 USD trước, 140 USD sau) và trên sandbox để evaluator ẩn thật sự ẩn (V2-05).
- **Commit:** `a29e82b`: validation/experiments/harness.py, tests/v2/test_v21_experiment.py
- **Mức (REPORT §2):** E1 = M3, E2 = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** So cùng client/model/budget; công bố cả run fail; held-out không được developer đọc
- **Còn thiếu:** E2: MỞ. 'Held-out không được developer đọc' hiện chỉ phát hiện sau sự việc (`leaks` quét chuỗi đặc trưng), không ngăn được.

### P-V2-14

> Client thứ hai và `assess` độc lập

- **Nguồn:** đề xuất §10 V2-14
- **Bằng chứng tại HEAD:** Không có lệnh `aisef assess`; client duy nhất là OpenCode. Không commit 2.1 nào cho mục này.
- **Kiểm cơ học:** `aisef2/app/cli.py` không chứa `assess`
- **Reproducer:** Không có (không triển khai).
- **Ảnh hưởng:** trung bình cho 2.1; cao cho thị trường (360 §3.9)
- **Quyết định:** declined — Hoãn sang 2.2 theo chính đề xuất (§10 ưu tiên P2; §12 gate 2.2) và 360 §6.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** OpenCode + một client khác tạo candidate được kiểm bằng cùng policy/evaluator; checker không cần điều phối toàn bộ SDLC
- **Còn thiếu:** Toàn bộ (2.2).

### P-ADJ-3

> LLM finding chưa xác minh chỉ phản hồi; lỗi đã xác minh, thuộc phạm vi, mức nghiêm trọng đủ cao phải chặn theo chính sách duyệt trước

- **Nguồn:** đề xuất §3 bảng điều chỉnh, hàng review
- **Bằng chứng tại HEAD:** `review.policy: fix-loop` + `min_severity`: chặn ⇔ CONFIRMED (probe của AISEF tái hiện) ∧ ANCHORED (contract đã duyệt neo kỳ vọng) ∧ mức ≥ ngưỡng; settings không có `review` ⇒ luật 2.0.0 (advisory), ghi trong record (ADR-7).
- **Kiểm cơ học:** `aisef2/app/review_verify.py` chứa `def blocks(`
- **Reproducer:** `tests/v2/test_v21_review.py::Triage::test_severity_floor_and_policy`, `tests/v2/test_v21_review.py::Triage::test_a_misread_requirement_is_confirmed_and_never_blocks`, `tests/v2/test_v21_review.py::ProductPath::test_without_a_review_policy_the_same_review_is_advisory_as_in_2_0_0`, `tests/v2/test_v21_review_chain.py::FixLoop::test_a_correct_anchored_finding_is_fixed_before_the_merge`
- **Ảnh hưởng:** cao (360 §3.5)
- **Quyết định:** adapted — Theo đề xuất, không theo 360 #8 ('không chặn'); điều chỉnh: thêm điều kiện neo (ANCHORED) theo chỉ thị chủ dự án (ADR-7), như R-P1-8.
- **Commit:** `e897437`: aisef2/app/review_verify.py; `390f07c`: aisef2/app/review_verify.py
- **Mức (REPORT §2):** C1 = M4 — Khớp REPORT (xem P-V2-09 về phần không xác nhận được từ output đã commit).
- **Tiêu chí nghiệm thu:** có các finding sai để chứng minh gate không chặn chỉ vì LLM nói có lỗi (§4.3)
- **Còn thiếu:** Mặc định (không khai `review`) vẫn advisory. Neo sai khi một stimulus mới bị xếp sai mệnh đề (ADR-7).

### P-ADJ-4

> Đưa Linux sandbox tối thiểu trước thí nghiệm dùng hidden tests; macOS native làm sau

- **Nguồn:** đề xuất §3 bảng điều chỉnh, hàng sandbox
- **Bằng chứng tại HEAD:** Chưa có sandbox (F) và chưa chạy thí nghiệm hidden-test nào (E2): thứ tự chưa bị vi phạm vì cả hai chưa chạy.
- **Kiểm cơ học:** `docs/v2.1/REPORT.md` chứa `chưa có mã cách ly nào trên nhánh`
- **Reproducer:** Không có.
- **Ảnh hưởng:** cao: không thể gọi evaluator là độc lập khi developer đọc được đề
- **Quyết định:** blocked — Như P-V2-05 (phương án F chờ chủ dự án) và P-V2-13 (ngân sách).
- **Mức (REPORT §2):** F = M6, E2 = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với cột 'Lý do' của cùng hàng §3: Không thể gọi một bộ đánh giá là độc lập khi developer đọc được đề và runtime của verifier
- **Còn thiếu:** Sandbox: MỞ.

### P-ADJ-5

> Dùng 1–3 lượt để canary; phép so sánh hiệu quả phải có thêm lượt lặp có ngân sách

- **Nguồn:** đề xuất §3 bảng điều chỉnh, hàng lượt trả tiền
- **Bằng chứng tại HEAD:** B-09 đề xuất các bậc: bậc 0 offline đã đạt (0 USD); bậc 1–2 (preflight thật + 1 story, trần 5 USD) chờ duyệt; pilot 18 lượt (2 workload × 3 cánh × 3 lặp) dự toán từ hồ sơ token smoke #2. Không lượt trả tiền nào đã chạy.
- **Kiểm cơ học:** `docs/v2.1/decisions/B-09-CANARY-THEN-CAMPAIGN.md` chứa `**Trạng thái: ĐỀ XUẤT, CHƯA DUYỆT.**`
- **Reproducer:** Không có.
- **Ảnh hưởng:** quyết định: canary chứng minh đường chạy, không đủ để kết luận hơn baseline
- **Quyết định:** blocked — Chặn trên ngân sách của chủ dự án (B-09 chưa duyệt).
- **Mức (REPORT §2):** E2 = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với cột 'Lý do' của cùng hàng §3: Canary chứng minh đường chạy; không đủ để kết luận hơn baseline
- **Còn thiếu:** Live: MỞ.

### P-ADJ-6

> Làm sau; nếu tái sử dụng evidence phải tính cả phụ thuộc và công cụ kiểm

- **Nguồn:** đề xuất §3 bảng điều chỉnh, hàng mutation
- **Bằng chứng tại HEAD:** B-03b (chủ dự án cho phép, RELEASE-DECISIONS seq 5): phase mutation V2.1 = 443 target / 11 365 mutant (55a6b74); một kết quả cũ chỉ được dùng lại khi tệp target, kill set, mọi tệp trong closure của kill test và generator đều giữ nguyên (`v21_mutation_record.proof`); tiêu chí đóng băng trước mọi kết quả (c9c736f). Không dùng ràng buộc AST từng hàm. Tại HEAD chưa có `closure-evidence/v2/v2.1/MUTATION-SUMMARY.json`.
- **Kiểm cơ học:** `validation/qualification/v21_mutation_record.py` chứa `FROZEN_CRITERIA_SHA256 = "9e6f9d39bee3b76549071a326bd32dd85d50d705ed18c396c8764a4c10b3dbdf"`; `validation/qualification/v21_mutation_record.py` chứa `every file of the kill tests' closure is byte-identical`; `closure-evidence/v2/v2.1/MUTATION-SUMMARY.json` không tồn tại
- **Reproducer:** `tests/v2/test_v21_mutation_record.py::Proof::test_a_different_kill_set_a_different_mutant_list_an_error_or_another_phase_is_not`, `tests/v2/test_v21_mutation_record.py::Phase::test_the_criteria_and_the_snapshot_are_frozen_before_any_result`, `tests/v2/test_v21_mutation_record.py::Account::test_every_v21_target_is_accounted_for_exactly_once_and_a_survivor_never_passes`
- **Ảnh hưởng:** trung bình: mutation 2.0 ràng buộc sha256 cả tệp (360 §3.2)
- **Quyết định:** adopted — Tái sử dụng tính cả phụ thuộc (closure) và công cụ (generator); không theo 360 #19 (AST từng hàm).
- **Commit:** `55a6b74`: validation/qualification/v21_mutation_record.py, validation/v2/mutation.py; `c9c736f`: validation/qualification/v21_mutation_record.py, tests/v2/test_v21_mutation_record.py; `16d4899`: closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST.json
- **Mức (REPORT §2):** REPORT §2 không có hạng mục cho B-03b.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với STATUS §3 B-03: suite đầy đủ xanh trên ứng viên 2.1
- **Còn thiếu:** Chiến dịch chưa xong: tại HEAD không có kết quả mutation 2.1 nào để tuyên bố.

### P-4.2a

> Reviewer trả thiếu manifest hoặc schema lạ → `INDETERMINATE`, không coi là review sạch.

- **Nguồn:** đề xuất §4.2
- **Upstream:** alibaba/open-code-review@182898cf522d `internal/session/manifest.go:20-23; cmd/opencodereview/review_cmd.go:296; output.go:669-695` — CODE (kiểm chứng: confirmed; claim P15)
- **Bằng chứng tại HEAD:** `review_ocr.coverage`: manifest thiếu, schema khác `ocr.run-manifest/v1`, partial, hết token, timeout ⇒ INDETERMINATE; dưới fix-loop là lỗi năng lực hoặc ProviderOutage; dưới advisory ghi lại, không chặn (REPORT §4.1).
- **Kiểm cơ học:** `aisef2/app/review_ocr.py` chứa `NOT_REVIEWABLE = ("unsupported_ext", "binary")`
- **Reproducer:** `tests/v2/test_v21_review_chain.py::IncompleteReview::test_an_unsupported_manifest_schema`, `tests/v2/test_v21_review_chain.py::IncompleteReview::test_its_token_budget_spent`, `tests/v2/test_v21_review_chain.py::IncompleteReview::test_timed_out_and_its_spend_unknown`, `tests/v2/test_v21_review_ocr.py::Coverage::test_a_manifest_that_does_not_hold_together_is_indeterminate`, `tests/v2/test_v21_review_chain.py::IncompleteReview::test_under_advisory_the_incomplete_review_is_recorded_and_does_not_block`
- **Ảnh hưởng:** cao: exit 0 của OCR gồm cả `partial` (OCR P11)
- **Quyết định:** adopted — Đúng đề xuất.
- **Commit:** `e897437`: aisef2/app/review_ocr.py, tests/v2/fixtures/ocr/partial.json; `390f07c`: aisef2/app/review_ocr.py
- **Mức (REPORT §2):** C2 = M4 — M4 là mức của hạng mục C2; riêng các nhánh INDETERMINATE chỉ có test offline (REPORT §4.1).
- **Tiêu chí nghiệm thu:** review thiếu một file bắt buộc không được thành PASS (§4.3)
- **Còn thiếu:** Tiêu chí chỉ đạt dưới `fix-loop`: dưới `advisory` — cũng là luật khi settings không khai `review` (ADR-V2.1) — review thiếu được ghi INDETERMINATE mà story vẫn COMMIT (`IncompleteReview::test_under_advisory_the_incomplete_review_is_recorded_and_does_not_block`). Tệp bắt buộc mà preview loại vì `unsupported_ext` hay `binary` không tính là thiếu (xem P-4.2b).

### P-4.2b

> Không lấy tập `selected` của OCR làm toàn bộ phạm vi bắt buộc một cách mặc nhiên

- **Nguồn:** đề xuất §4.2
- **Upstream:** alibaba/open-code-review@182898cf522d `internal/agent/selection.go:52-58, 92-95; agent.go:2042-2052; compression.go:29-31 (lý do loại theo kích thước/extension/đường dẫn; default_exclude_patterns.json)` — CODE (kiểm chứng: confirmed; claim P14); alibaba/open-code-review@182898cf522d `internal/diff/git.go:28-41, 80-82; config/rules/system_rules.go:288-369` — CODE (kiểm chứng: confirmed; claim N9)
- **Bằng chứng tại HEAD:** Phạm vi bắt buộc do AISEF tính từ journal (khoảng base..candidate đã đóng băng); đường dẫn bắt buộc vắng trong preview (bị `.gitignore`/thư mục provider loại) ⇒ INDETERMINATE (UPSTREAM-RESEARCH.md).
- **Kiểm cơ học:** `aisef2/app/review_ocr.py` chứa `NOT_REVIEWABLE = ("unsupported_ext", "binary")`; `aisef2/app/review_ocr.py` chứa `cannot read (named in the coverage, not counted against it)`
- **Reproducer:** `tests/v2/test_v21_review_ocr.py::Coverage::test_the_preview_s_exclusions_and_omissions_are_named`, `tests/v2/test_v21_review_ocr.py::Coverage::test_a_complete_run_of_the_frozen_range_covering_every_required_path`, `tests/v2/test_v21_review_ocr.py::Process::test_the_command_reviews_exactly_the_frozen_range_into_a_fresh_file`
- **Ảnh hưởng:** cao: tệp bị OCR lọc vẫn có thể quan trọng với AISEF
- **Quyết định:** adapted — Phạm vi bắt buộc do AISEF tính từ git (khoảng base..candidate đã đóng băng), không lấy tập `selected` của OCR. Điều chỉnh: tệp bắt buộc mà preview loại vì `unsupported_ext` hay `binary` được ghi tên trong coverage nhưng không tính là thiếu (docstring và `NOT_REVIEWABLE` của `review_ocr`); đề xuất nêu cả tệp bị lọc vì extension.
- **Commit:** `e897437`: aisef2/app/review_ocr.py, tests/v2/fixtures/ocr/preview.json
- **Mức (REPORT §2):** C2 = M4 — M4 là mức của C2; hành vi riêng này có test offline.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với câu liền trước của cùng đoạn §4.2: Định nghĩa mẫu số từ chính sách AISEF trước khi gọi OCR.
- **Còn thiếu:** Tệp bắt buộc bị loại vì extension hay nhị phân không được review mà review vẫn có thể COMPLETE. Không test nào đặt một tệp bắt buộc như thế rồi khẳng định kết quả (`grep` tests/: không test nào đọc `unreadable` hay `NOT_REVIEWABLE`; fixture `tests/v2/fixtures/ocr/preview.json` có `docs/limits.md` = `unsupported_ext` nhưng không test nào đặt nó là bắt buộc).

### P-4.2c

> Không cho reviewer quyền commit, merge, thay contract hay cập nhật verdict.

- **Nguồn:** đề xuất §4.2
- **Bằng chứng tại HEAD:** Reviewer chụp HEAD + mọi tệp của checkout trước finder, so lại sau finder và sau probe kiểm chứng; đổi ⇒ bỏ mọi finding (ADR-7). `review_verify.verify` nằm trong inventory PRODUCT_TRUTH với giới hạn (không commit/merge, không journal, một đường quyết định), do checker theo module, fail-closed cưỡng chế (B-03c).
- **Kiểm cơ học:** `closure-evidence/v2/v2.1/AUTHORITY-INVENTORY.json` chứa `review_verify`; `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` chứa `* Cả hai không trực tiếp commit/merge sản phẩm hoặc tạo đường quyết định cuối thứ hai.`
- **Reproducer:** `tests/v2/test_v21_review_chain.py::CandidateChangedDuringReview::test_a_file_edited_by_the_finder_discards_the_review_and_never_reaches_main`, `tests/v2/test_v21_review_chain.py::CandidateChangedDuringReview::test_a_commit_made_by_the_finder_discards_the_review`, `tests/v2/test_v21_authority_limits.py::NoCommitOrMerge::test_verify_committing_or_journaling_is_caught`, `tests/v2/test_v21_authority_limits.py::OneDecisionPath::test_a_second_caller_of_verify_blocks_or_migrate_is_caught`
- **Ảnh hưởng:** cao: reviewer là mô hình, không có thẩm quyền sự thật sản phẩm
- **Quyết định:** adopted — Đúng đề xuất; owner B-03c (RELEASE-DECISIONS seq 5).
- **Commit:** `390f07c`: aisef2/app/review_verify.py; `a912be6`: validation/qualification/authority_limits.py, closure-evidence/v2/v2.1/AUTHORITY-INVENTORY.json, tests/v2/test_v21_authority_limits.py, aisef2/app/review_verify.py; `1711c07`: validation/qualification/authority_limits.py; `0b4e740`: validation/qualification/authority_limits.py
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng (B-03c thuộc §7). Test tồn tại tại HEAD (kiểm bằng AST); không chạy lại trong phiên lập bảng.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chỉ thị B-03c của chủ dự án (RELEASE-DECISIONS seq 5): Cả hai không trực tiếp commit/merge sản phẩm hoặc tạo đường quyết định cuối thứ hai.
- **Còn thiếu:** Không có ranh giới OS: finder chạy dưới cùng user; thay đổi bị phát hiện và loại, không bị ngăn (REPORT §3).

### P-4.3a

> Nếu finding phát hiện một yêu cầu chưa có trong contract, tạo **đề xuất sửa contract có phiên bản**.

- **Nguồn:** đề xuất §4.3
- **Bằng chứng tại HEAD:** Finding CONFIRMED mà UNANCHORED được ghi lại (triage) kèm lý do, không chặn. Không có mã nào tạo đề xuất sửa contract có phiên bản từ một finding.
- **Kiểm cơ học:** `aisef2/app/review_verify.py` không chứa `amend`
- **Reproducer:** `tests/v2/test_v21_review_chain.py::NotABlocker::test_a_reproduced_finding_whose_clause_shows_no_constant_outcome_does_not_block` Test chỉ cho thấy finding được ghi và không chặn; phần tạo đề xuất không có test vì chưa có.
- **Ảnh hưởng:** trung bình: yêu cầu thiếu trong contract chỉ nằm trong triage
- **Quyết định:** open — Chưa làm. Phần 'không để cùng agent nới tiêu chí' được giữ bằng `approve` chỉ nhận `human:<tên>` (ADR-6, xem P-13-2).
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §4.3: Cập nhật đã duyệt áp dụng cho run mới; giữ nguyên lịch sử run cũ.
- **Còn thiếu:** Toàn bộ phần tạo đề xuất.

### P-4.3b

> Reproducer chạy thành công **chưa đủ**: còn phải xác nhận kỳ vọng của nó đúng theo requirement/chính sách đã duyệt.

- **Nguồn:** đề xuất §4.3 bước 4
- **Bằng chứng tại HEAD:** `review_verify.anchor`: ANCHORED / CONTRADICTS_APPROVED / UNANCHORED quyết định chỉ từ contract đã duyệt và mệnh đề đã niêm phong của bundle, không từ chữ của reviewer (ADR-7).
- **Kiểm cơ học:** `aisef2/app/review_verify.py` chứa `def anchor(`
- **Reproducer:** `tests/v2/test_v21_review.py::Triage::test_a_stimulus_an_approved_contract_decides_otherwise_is_a_false_finding`, `tests/v2/test_v21_review_chain.py::NotABlocker::test_a_reproduced_finding_an_approved_contract_contradicts_does_not_block`, `tests/v2/test_v21_review.py::Triage::test_known_limit_a_new_stimulus_under_the_wrong_clause_anchors`
- **Ảnh hưởng:** cao: finding tái hiện được nhưng hiểu sai yêu cầu không được thành blocker
- **Quyết định:** adopted — Đúng đề xuất và chỉ thị chủ dự án.
- **Commit:** `390f07c`: aisef2/app/review_verify.py, tests/v2/test_v21_review.py
- **Mức (REPORT §2):** C1 = M4 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** có các finding sai để chứng minh gate không chặn chỉ vì LLM nói có lỗi
- **Còn thiếu:** Giới hạn đã đo: stimulus mới xếp sai mệnh đề vẫn neo được (test_known_limit_…).

### P-4.3c

> Branch đích đổi thì dựng cây tích hợp mới và kiểm lại.

- **Nguồn:** đề xuất §4.3 bước 7
- **Bằng chứng tại HEAD:** Có từ 2.0: chứng minh lại sau merge (`merge.affected_preserve`), thất bại ⇒ INTEGRATION (STATUS B2: 'ĐÃ KIỂM, không cần sửa', đọc mã). 2.1 giữ nó cạnh PRESERVE ở candidate (ADR-4).
- **Kiểm cơ học:** `aisef2/orchestrate/merge.py` chứa `def affected_preserve(`; `docs/v2.1/STATUS.md` chứa `**ĐÃ KIỂM**, không cần sửa`; `aisef2/orchestrate/merge.py` chứa `point=MeasurementPoint.POST_MERGE`; `docs/v2.1/evidence/traceability-reproducers-c9c736f.out` (đi cùng bảng) chứa `tests.v2.test_p6_orchestration.Orchestration.test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_…`
- **Reproducer:** `tests/v2/test_p6_orchestration.py::Orchestration::test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back`
- **Ảnh hưởng:** trung bình
- **Quyết định:** adopted — Đã có trong 2.0, không triển khai lại.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này. Test tồn tại tại HEAD (kiểm bằng AST); không chạy lại trong phiên lập bảng.
- **Tiêu chí nghiệm thu:** vẫn kiểm cây tích hợp khi base đổi (§10 V2-06)
- **Còn thiếu:** Không còn so với tiêu chí trên: sau merge, mọi obligation của story và PRESERVE của các story đã commit được chứng minh lại ở revision đã merge (`merge.reprove`, POST_MERGE). Dựa vào đọc mã và test ORCH_9/10 (chạy lại xanh tại c9c736f, vòng 2).

### P-5.2a

> AISEF phải tự chạy lệnh đánh giá được cố định, đọc kết quả có schema và ràng buộc digest.

- **Nguồn:** đề xuất §5.2 (metric do agent tự báo)
- **Upstream:** XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/workflow/builtin/research-experiment.js:39-48, 102-123` — CODE (kiểm chứng: confirmed; claim P-09)
- **Bằng chứng tại HEAD:** Thí nghiệm: `harness.evaluate` chạy evaluator ẩn bằng probe của AISEF trên candidate đã đóng băng; 'xong' của agent chỉ được ghi. Review: reproducer do AISEF chạy bằng probe đã hiệu chuẩn.
- **Reproducer:** `tests/v2/test_v21_experiment.py::Experiment::test_the_direct_arm_from_task_to_evaluated_result_and_its_replay`, `tests/v2/test_v21_review.py::HistoricalDefects::test_each_shipped_defect_is_confirmed_on_its_shape_and_not_on_the_reference`
- **Ảnh hưởng:** cao: metric tự báo không phải phép đo độc lập
- **Quyết định:** adopted — Đúng đề xuất.
- **Commit:** `a29e82b`: validation/experiments/harness.py; `e897437`: aisef2/app/review_verify.py
- **Mức (REPORT §2):** E1 = M3 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §5.2: Agent chỉ đề xuất giả thuyết/candidate.
- **Còn thiếu:** Chưa chạy trên workload thật (E2).

### P-5.2b

> Có thể dùng để nhắc agent còn việc; không dùng thay acceptance hoặc để cấp `delivery_verdict PASS`.

- **Nguồn:** đề xuất §5.2 (LLM judge)
- **Upstream:** XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/session/goal.ts:64-79, 159-215` — CODE (kiểm chứng: confirmed; claim P-10); XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/session/prompt.ts:4140, 4142-4150, 4175-4188` — INFERENCE (kiểm chứng: corrected, người kiểm chứng phân lại; nghiên cứu ghi CODE; claim N-18)
- **Bằng chứng tại HEAD:** Không có LLM judge nào trong 2.1; review của mô hình không bao giờ tự chặn.
- **Kiểm cơ học:** `aisef2/app/review_verify.py` chứa `a model review alone never blocks`
- **Reproducer:** Không có (không xây gì).
- **Ảnh hưởng:** cao nếu sao chép: judge của MiMo dùng cùng model với phiên (CODE, prompt.ts:4140). Lỗi judge (mạng, schema) có được tính là đạt hay không: INFERENCE theo người kiểm chứng (N-18) — ý định fail-open có ghi trong chú thích, nhưng lỗi provider có thể lan ra thay vì fail-open; chưa kiểm.
- **Quyết định:** declined — Không sao chép; verdict chỉ từ obligation do probe chứng minh.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** —

### P-5.2c

> AISEF cần tạo run con, giữ parent và bằng chứng cũ.

- **Nguồn:** đề xuất §5.2 (resume làm mất lịch sử)
- **Upstream:** XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/workflow/runtime.ts:1562-1563; persistence.ts:292-297` — CODE (kiểm chứng: confirmed; claim P-11); XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/workflow/runtime.ts:1515-1537; util/lock.ts:1-21` — CODE (kiểm chứng: confirmed; claim P-12)
- **Bằng chứng tại HEAD:** Run con qua `--parent`; bằng chứng run cũ giữ nguyên byte (chỉ thêm tệp claim); claim `O_EXCL` theo thế hệ: hai tiến trình cùng yêu cầu ⇒ đúng một lấy được (ADR-8).
- **Reproducer:** `tests/v2/test_v21_continue_integrity.py::ClaimLifecycle::test_the_predecessors_evidence_stays_byte_identical_but_the_claim`, `tests/v2/test_v21_continue_integrity.py::ClaimLifecycle::test_two_runs_at_once_one_claims_and_the_other_spends_nothing`, `tests/v2/test_v21_continue_integrity.py::ClaimLifecycle::test_a_child_that_began_is_never_superseded_the_lineage_continues_from_it`
- **Ảnh hưởng:** cao
- **Quyết định:** adopted — Đúng đề xuất (khoá liên tiến trình, không chỉ trong tiến trình).
- **Commit:** `7e0aac0`: tests/v2/test_v21_continue_integrity.py; `872e83c`: aisef2/app/lineage.py; `7fe1062`: tests/v2/test_v21_continue_integrity.py
- **Mức (REPORT §2):** D1 = M4 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §5.2: AISEF cần chống hai controller ở hai tiến trình cùng resume.
- **Còn thiếu:** Claimant ở máy khác: chỉ thay khi người vận hành nêu sha256 của claim (REPORT §4.2).

### P-5.3a

> Checkpoint tối thiểu nên chứa các tham chiếu: `run_id`, `attempt_id`, `journal_sequence`, `candidate_digest`, `contract_digest`, `phase`, `open_findings`, `next_action`, `context_refs`.

- **Nguồn:** đề xuất §5.3
- **Upstream:** XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/session/checkpoint-templates.ts:4-57, 88-100` — CODE (kiểm chứng: corrected; claim P-03); XiaomiMiMo/MiMo-Code@6babeb0b98f9 `README.md:156-160 (không có số đo nào trong repo)` — README (kiểm chứng: confirmed; claim P-04); XiaomiMiMo/MiMo-Code@6babeb0b98f9 `thiết kế của AISEF; người kiểm: checkpoint.ts:1424-1451, 1453-1489` — INFERENCE (kiểm chứng: confirmed; claim P-14); XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/memory/memory-path-guard.ts:126-139` — CODE (kiểm chứng: confirmed; claim N-04); XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/agent/prompt/checkpoint-writer.txt:54-57` — CODE (kiểm chứng: confirmed; claim N-06)
- **Bằng chứng tại HEAD:** Không có gói ngữ cảnh / checkpoint hỗ trợ nào tại HEAD (REPORT D4: M6). Phần 'trạng thái chuẩn do controller sở hữu' có qua `bundle continue`: sự thật là journal, không phải tóm tắt của agent (UPSTREAM-RESEARCH.md).
- **Kiểm cơ học:** `docs/v2.1/REPORT.md` chứa `\| D4 \| gói ngữ cảnh kiểu MiMo \| **M6** \|`; `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` chứa `context/checkpoint theo MiMo`
- **Reproducer:** Không có (chưa triển khai).
- **Ảnh hưởng:** trung bình: smoke #2 một phiên đốt 7,0 M input không sửa gì (360 §3.5) — chưa chứng minh gói ngữ cảnh sẽ giảm điều đó
- **Quyết định:** open — REPORT/STATUS ghi 'chưa có bằng chứng cần'; chủ dự án yêu cầu báo riêng trạng thái context/checkpoint theo MiMo (RELEASE-DECISIONS seq 5). Chưa có quyết định đóng mục.
- **Mức (REPORT §2):** D4 = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §5.3: Controller tự điền các trường định danh; phần văn xuôi không được ghi đè chúng.
- **Còn thiếu:** Toàn bộ. MỞ. Nếu làm, tránh hai lỗi đã thấy ở upstream: agent chính ghi được checkpoint (N-04), writer chép nguyên văn khoá API (N-06).

### P-5.3b

> Hành động merge/commit phải có operation ID để không lặp tác dụng khi crash xảy ra giữa thực thi và ghi nhận.

- **Nguồn:** đề xuất §5.3
- **Bằng chứng tại HEAD:** Đối soát: candidate trong worktree `wt-<story>` của kernel và merge của kernel (cha thứ hai + 'merge <sha12>') được nhận diện với git; không nhận diện được ⇒ từ chối trừ khi người vận hành nêu `--leave-out-unidentified` (ADR-8).
- **Kiểm cơ học:** `aisef2/app/bundle_cli.py` chứa `--leave-out-unidentified`
- **Reproducer:** `tests/v2/test_v21_continue_integrity.py::CommitWindows::test_the_developers_candidate_committed_nothing_journaled`, `tests/v2/test_v21_continue_integrity.py::CommitWindows::test_the_merge_moved_main_the_journal_never_committed_it`, `tests/v2/test_v21_continue_integrity.py::CommitWindows::test_a_commit_on_main_nothing_identifies_is_refused_unless_left_out_by_name`
- **Ảnh hưởng:** cao: commit/merge lặp sau crash
- **Quyết định:** adapted — Không thêm trường operation ID vào journal (schema đóng); dùng danh tính thao tác sẵn có của kernel (worktree, thông điệp merge).
- **Commit:** `872e83c`: aisef2/app/lineage.py, tests/v2/test_v21_continue_integrity.py
- **Mức (REPORT §2):** D1 = M4 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §5.3: Không tự chạy lại tác dụng ngoài hệ thống nếu chưa biết lần trước đã xảy ra hay chưa.
- **Còn thiếu:** Nhận diện dựa vào quy ước của kernel (tên worktree, thông điệp merge); một commit tay giống quy ước chưa được xét.
- **Chưa xác nhận được:** Khả năng một commit do người/agent tạo trùng quy ước nhận diện: không kiểm trong phiên này.

### P-5.3c

> nếu một số bước liên tiếp không tạo thay đổi mã, bằng chứng mới hoặc giả thuyết mới có căn cứ, giảm ngữ cảnh và đổi chiến thuật một lần; vẫn lặp thì dừng với lý do.

- **Nguồn:** đề xuất §5.3 (no-progress detector)
- **Upstream:** XiaomiMiMo/MiMo-Code@6babeb0b98f9 `packages/cli/src/workflow/builtin/research-experiment.js:81-90` — CODE (kiểm chứng: corrected; claim P-07)
- **Bằng chứng tại HEAD:** `usage.no_progress` báo các attempt liên tiếp có cùng tập lỗi, ghi vào RUN.json; không giảm ngữ cảnh, không đổi chiến thuật, không dừng.
- **Kiểm cơ học:** `aisef2/app/run.py` chứa `rec["usage"], rec["no_progress"] = usage.usage(`
- **Reproducer:** `tests/v2/test_v21_continue_usage.py::Usage::test_retries_that_change_nothing_are_reported`
- **Ảnh hưởng:** trung bình: một phiên chạm trần 80 lượt không sửa gì (360 §3.5)
- **Quyết định:** adapted — Chỉ báo cáo: retry thuộc taxonomy — khớp câu 'không đặt thêm cơ chế retry độc lập trong adapter' của đề xuất; phần giảm ngữ cảnh / đổi chiến thuật / dừng không làm.
- **Commit:** `d622e71`: aisef2/app/usage.py
- **Mức (REPORT §2):** D3 = M3 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §5.3: Mọi retry tiếp tục đi qua taxonomy hiện có; không đặt thêm cơ chế retry độc lập trong adapter.
- **Còn thiếu:** Đơn vị đo là attempt (cùng lỗi), không phải bước/lượt trong một phiên; ngưỡng chưa hiệu chỉnh.

### P-6.2a

> Mỗi thử nghiệm cần khóa các trường sau trước khi chạy:

- **Nguồn:** đề xuất §6.2
- **Upstream:** alphaXiv/OpenResearch@d52a05365622 `src/compute.rs:168-182, 41-49` — CODE (kiểm chứng: confirmed; claim P4); alphaXiv/OpenResearch@d52a05365622 `src/model.rs:66-86; store.rs:229-250` — INFERENCE (kiểm chứng: confirmed; claim N18)
- **Bằng chứng tại HEAD:** Manifest `aisef.experiment/1` có khoá đóng (format, experiment_id, parent_experiment_id, pair, workload, source, evaluator, bundle, policy, command, client, model, environment, variable_under_test, limits, stop_rule, created_at), niêm phong bằng sha256 JSON chuẩn hoá; sửa ⇒ seal hỏng.
- **Kiểm cơ học:** `validation/experiments/harness.py` chứa `FORMAT = "aisef.experiment/1"`; `validation/experiments/harness.py` chứa `"command", "client", "model", "environment", "variable_under_test", "limits", "stop_rule", "created…`; `validation/experiments/harness.py` không chứa `adapter_version`
- **Reproducer:** `tests/v2/test_v21_experiment.py::Experiment::test_a_manifest_is_sealed_and_an_edit_breaks_the_seal`
- **Ảnh hưởng:** cao cho tính đối chiếu
- **Quyết định:** adapted — Nhận khung: khoá đóng ở cấp trên cùng, niêm phong sha256, `model.identity_confidence` kèm lý do, `evaluator.exposed_to_developer` = false (`harness.check`). Nội dung bên trong các khoá khác không được đòi; không có quyết định nào ghi lại cho phần đó.
- **Commit:** `a29e82b`: validation/experiments/harness.py
- **Mức (REPORT §2):** E1 = M3 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục: mọi trường §6.2 liệt kê được khoá trước khi chạy (gạch đầu dòng cuối của danh sách đó, 'Kết quả từng obligation, finding, chi phí, thời gian và sự cố môi trường', là một trường phải khoá, không phải tiêu chí).
- **Còn thiếu:** `harness.check` không đòi nội dung các trường §6.2 liệt kê: Workload ID, baseline commit, candidate snapshot digest, digest requirements/bundle/evaluator/policy, nguồn gốc bộ test, client + phiên bản, adapter version, thông tin provider thực trả, environment image digest, dependency lock, mạng, quyền ghi, giới hạn thời gian/token/tiền. Chưa dùng cho lượt thật nào.

### P-6.2b

> Không suy ra danh tính model thực chỉ từ chuỗi tên provider trả về.

- **Nguồn:** đề xuất §6.2
- **Upstream:** alphaXiv/OpenResearch@d52a05365622 `src/compute.rs:877-924` — CODE (kiểm chứng: corrected; claim N13); alphaXiv/OpenResearch@d52a05365622 `src/chat/mod.rs:7642-7653; store/telemetry.rs:12-47, 50-57` — CODE (kiểm chứng: confirmed; claim N12)
- **Bằng chứng tại HEAD:** `model.identity_confidence` ∈ verified / provider_reported / unverified, bắt buộc kèm lý do (`harness.check`).
- **Kiểm cơ học:** `validation/experiments/harness.py` chứa `IDENTITY = ("verified", "provider_reported", "unverified")`
- **Reproducer:** `tests/v2/test_v21_experiment.py::Experiment::test_a_manifest_is_sealed_and_an_edit_breaks_the_seal` Test chỉ chạy manifest hợp lệ (`unverified`); không có test âm riêng cho trường thiếu.
- **Ảnh hưởng:** trung bình
- **Quyết định:** adopted — Đúng đề xuất.
- **Commit:** `a29e82b`: validation/experiments/harness.py
- **Mức (REPORT §2):** E1 = M3 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §6.2: ghi `provider-reported`/`unverified` đúng phạm vi, không gọi là xác thực model đầy đủ
- **Còn thiếu:** Chỉ trong harness thí nghiệm; preflight của `aisef run` không đổi trong 2.1 về điểm này.
- **Chưa xác nhận được:** 'preflight không đổi về điểm này': suy từ danh sách commit 2.1 (b029236 chỉ sửa redirect), chưa đọc lại preflight.

### P-6.2c

> Tránh đưa dashboard, multi-cloud scheduler hoặc hàng loạt compute backend vào đường găng 2.1.

- **Nguồn:** đề xuất §6.2
- **Upstream:** alphaXiv/OpenResearch@d52a05365622 `người kiểm: README.md:105-107@d52a053; up.rs:57-62, 790-830; remote_host.rs:749` — INFERENCE (kiểm chứng: corrected; claim P11)
- **Bằng chứng tại HEAD:** Không có dashboard, scheduler hay compute backend nào được thêm (danh sách tệp đổi 610a593..c9c736f).
- **Reproducer:** Không có (không xây gì).
- **Ảnh hưởng:** —
- **Quyết định:** declined — Giữ đúng đề xuất.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** —

### P-7a

> Giới hạn tiền kiểm trước lượt kế tiếp nên có thể vượt trần bởi một request đang thực hiện; AISEF cần ghi rõ sai số hoặc đặt trước ngân sách request.

- **Nguồn:** đề xuất §7 mini-SWE-agent
- **Upstream:** SWE-agent/mini-swe-agent@04d809ceab9d `src/minisweagent/agents/default.py:132, 148-150; tests/agents/test_default.py:530-544` — CODE (kiểm chứng: confirmed; claim P7)
- **Bằng chứng tại HEAD:** Có từ 2.0: `client.LIMITATION` ghi rằng tổng có thể vượt trần bởi các step kết thúc kể từ lần đọc trước, và request không kết thúc step không có trong telemetry; ghi kèm mỗi bản kế toán ngân sách.
- **Kiểm cơ học:** `aisef2/app/client.py` @ 610a593 chứa `so totals can pass a ceiling by the steps`; `aisef2/app/client.py` chứa `so totals can pass a ceiling by the steps`
- **Reproducer:** Không có test riêng; bằng chứng là mã (giới hạn được ghi, không được đo).
- **Ảnh hưởng:** trung bình
- **Quyết định:** adopted — Đã có trong 2.0 (ghi sai số), không triển khai lại.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục: AISEF cần ghi rõ sai số hoặc đặt trước ngân sách request
- **Còn thiếu:** Không đặt trước ngân sách request; sai số không được định lượng.

### P-7b

> Đối chứng chính phải là cùng model, client, nhiệm vụ và tài nguyên chạy trực tiếp. mini là đối chứng phụ

- **Nguồn:** đề xuất §7 mini-SWE-agent
- **Upstream:** SWE-agent/mini-swe-agent@04d809ceab9d `src/minisweagent/models/litellm_model.py:66-71` — INFERENCE (kiểm chứng: confirmed; claim P2); SWE-agent/mini-swe-agent@04d809ceab9d `— (INFERENCE: nghiên cứu không dẫn tệp:dòng nào cho tuyên bố này)` — INFERENCE (kiểm chứng: confirmed; claim P10)
- **Bằng chứng tại HEAD:** Cánh `direct` của harness: cùng client, cùng settings/route, task công khai; harness commit những gì client để lại. Không có cánh mini-SWE-agent trong `ARMS`.
- **Kiểm cơ học:** `validation/experiments/harness.py` chứa `ARMS = ("direct", "aisef", "aisef+")`
- **Reproducer:** `tests/v2/test_v21_experiment.py::Experiment::test_the_direct_arm_from_task_to_evaluated_result_and_its_replay`
- **Ảnh hưởng:** cao cho kết luận hiệu quả
- **Quyết định:** adapted — Đối chứng chính nhận; mini là tuỳ chọn, chưa làm (UPSTREAM-RESEARCH.md: 'cánh A' tuỳ chọn').
- **Commit:** `a29e82b`: validation/experiments/harness.py
- **Mức (REPORT §2):** E1 = M3 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục (diễn đạt lại): Đối chứng chính là cùng model, client, nhiệm vụ và tài nguyên chạy trực tiếp
- **Còn thiếu:** Cánh mini: chưa làm.

### P-7c

> MVP nên là Linux executor, có thể điều khiển từ máy macOS.

- **Nguồn:** đề xuất §7 OpenSandbox
- **Upstream:** opensandbox-group/OpenSandbox@c7dc78a4090e `server/opensandbox_server/services/docker/docker_service.py:783-850; container_ops.py:362-400, 402-496` — CODE (kiểm chứng: confirmed; claim P1); opensandbox-group/OpenSandbox@c7dc78a4090e `container_ops.py:362-400, 429-443; config.py:1216-1231, 1232-1247` — CODE (kiểm chứng: confirmed; claim P8); opensandbox-group/OpenSandbox@c7dc78a4090e `config.py:1200-1204 (mặc định network host)` — CODE (kiểm chứng: confirmed; claim N1); opensandbox-group/OpenSandbox@c7dc78a4090e `components/execd/pkg/flag/parser.go:42,62-71; router.go:218-221` — CODE (kiểm chứng: confirmed; claim N4); opensandbox-group/OpenSandbox@c7dc78a4090e `docker_service.py:899-922; container_ops.py:422-424` — CODE (kiểm chứng: confirmed; claim N13); opensandbox-group/OpenSandbox@c7dc78a4090e `config.py:1118-1145, 995-1000, 1386-1396` — INFERENCE (kiểm chứng: confirmed; claim N25)
- **Bằng chứng tại HEAD:** Không có executor Linux tại HEAD. Mã OpenSandbox (c7dc78a) được đọc làm danh mục kiểm, không làm backend: mặc định network host, execd không xác thực trên Docker, chế độ bwrap nới container (UPSTREAM-RESEARCH.md).
- **Kiểm cơ học:** `docs/v2.1/UPSTREAM-RESEARCH.md` chứa `danh mục kiểm cho V2-05`
- **Reproducer:** Không có (chưa triển khai).
- **Ảnh hưởng:** cao (như P-V2-05)
- **Quyết định:** blocked — Như P-V2-05.
- **Mức (REPORT §2):** F = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §7: Developer không nhận host HOME, socket Docker, credential, verifier runtime hoặc hidden bundle.
- **Còn thiếu:** Toàn bộ. MỞ.

### P-8

> Mũi tên phản hồi về kernel không cho phép plugin trực tiếp ghi verdict.

- **Nguồn:** đề xuất §8
- **Bằng chứng tại HEAD:** B-03c: `bundle_cli.migrate`, `review_verify.verify` trong AUTHORITY-INVENTORY.json; checker theo module, fail-closed bắt mọi đường commit/merge/journal/approve và đường quyết định thứ hai. Module mới nằm trong `aisef2/app`, không tách package (§8: 'chưa phải yêu cầu tạo ngay sáu package').
- **Kiểm cơ học:** `closure-evidence/v2/v2.1/AUTHORITY-INVENTORY.json` chứa `bundle_cli`; `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` chứa `Cập nhật inventory và kiểm tra kiến trúc để cưỡng chế các giới hạn này.`
- **Reproducer:** `tests/v2/test_v21_authority_limits.py::RealTree::test_the_tree_is_inside_the_limits_and_the_closure_crosses_modules`, `tests/v2/test_v21_authority_limits.py::OneDecisionPath::test_a_second_caller_of_verify_blocks_or_migrate_is_caught`, `tests/v2/test_v21_authority_limits.py::MigrateNeverApproves::test_calling_approve_is_caught_with_everything_approve_then_reaches`, `tests/v2/test_v21_authority_limits.py::Calibration::test_the_q0_checker_rejects_its_known_bad_fixture_and_an_always_pass_mutant_fails_calibration`
- **Ảnh hưởng:** cao: một đường quyết định là tài sản chính của 2.0 (360 §3.1)
- **Quyết định:** adopted — Đúng đề xuất và owner B-03c.
- **Commit:** `a912be6`: validation/qualification/authority_limits.py, closure-evidence/v2/v2.1/AUTHORITY-INVENTORY.json, aisef2/app/bundle_cli.py; `1711c07`: validation/qualification/authority_limits.py, tests/v2/test_v21_authority_limits.py; `0b4e740`: validation/qualification/authority_limits.py, tests/v2/test_v21_authority_limits.py
- **Mức (REPORT §2):** REPORT §2 không có hạng mục (B-03c chấp nhận ở RELEASE-DECISIONS seq 5). Test tồn tại tại HEAD (kiểm bằng AST); không chạy lại trong phiên lập bảng.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chỉ thị B-03c của chủ dự án (RELEASE-DECISIONS seq 5): Cập nhật inventory và kiểm tra kiến trúc để cưỡng chế các giới hạn này.
- **Còn thiếu:** Checker là phân tích tĩnh trên mã Python; tiến trình ngoài (OCR) không bị ràng buộc ở mức OS.

### P-9.1

> CLI dự kiến, **chưa tồn tại trong v2.0 theo báo cáo**:

- **Nguồn:** đề xuất §9.1
- **Bằng chứng tại HEAD:** `aisef bundle` có init, seal, approve, lint, explain, continue, migrate; `aisef run` có `--parent`, `--accept-unaccounted`, `--anchor-out`, `--expect-anchor`. Không có `run --resume`, không có `assess --candidate`.
- **Kiểm cơ học:** `aisef2/app/bundle_cli.py` chứa `sub.add_parser("continue"`; `aisef2/app/bundle_cli.py` chứa `sub.add_parser("migrate"`; `aisef2/app/cli.py` chứa `"--parent"`
- **Reproducer:** `tests/v2/test_v21_bundle_tools.py::Outsider::test_each_example_from_init_to_a_ready_check`, `tests/test_v21_bundle_dispatch.py::BundleIsV2::test_migrate_through_the_aisef_command`, `tests/v2/test_v21_continue_usage.py::Continue::test_the_continuation_inherits_what_the_journal_committed_and_proves_it_again_for_free`
- **Ảnh hưởng:** cao (360 §3.6)
- **Quyết định:** adapted — `run --resume` thay bằng `bundle continue` + `run --parent` (ADR-8); `assess` hoãn sang 2.2 (P-V2-14); thêm `approve` (duyệt từng contract, `human:<tên>`, ADR-6).
- **Commit:** `620bde7`: aisef2/app/bundle_cli.py; `d622e71`: aisef2/app/bundle_cli.py, aisef2/app/cli.py; `919a271`: aisef/cli/parser.py, aisef2/app/bundle_cli.py
- **Mức (REPORT §2):** B4 = M4, B5 = M4, D1 = M4 — Khớp REPORT. B4/B5: M4 là của lượt CLI thật tại `b72e51e` (docs/v2.1/evidence/cli-integration-b72e51e.out); `aisef2/app/bundle_cli.py` đổi sau lượt đó ở a912be6 và 3061ec0 (đường ghi của init/seal/approve/migrate chuyển sang tạo độc quyền `_create`), lượt lặp lại tại c9c736f (`docs/v2.1/evidence/cli-integration-c9c736f.out`, vòng 2 của bảng này: cùng `run.sh`, cùng nhị phân OCR, clone sạch tại c9c736f) cho cùng output — khác nhau chỉ ở giá trị băm (commit của repo `git init` mới, plan_hash, anchor, sha256), pid, mốc thời gian và dòng cuối bị cắt ở 3000 ký tự: M4 tại c9c736f. (kiểm cơ học ở P-V2-07)
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với câu cuối của §9.1: `seal` chỉ niêm phong phiên bản đã duyệt, không thay thế duyệt.
- **Còn thiếu:** `assess --candidate`: chưa có.

### P-9.3

> Positive controls: nhiều triển khai đúng khác cấu trúc vẫn pass.

- **Nguồn:** đề xuất §9.3
- **Bằng chứng tại HEAD:** Chưa có bậc kiểm contract theo ≥ 2 triển khai đúng, metamorphic hay false-rejection tổng quát. Hiệu chuẩn hiện có là theo lớp probe (fixture dương/âm cho mỗi lớp, ví dụ `python_imports`). Riêng S-10-a: hai bản nháp giữ trên dạng smoke #2 và bác một import thật.
- **Kiểm cơ học:** `tests/v2/fixtures/calibration/file_artifact/python_imports/positive/request.json` tồn tại
- **Reproducer:** `tests/v2/test_v21_python_imports.py::Controls::test_each_draft_holds_on_the_smoke2_shape_and_refutes_a_real_import`
- **Ảnh hưởng:** cao: S-10-a QUALIFIED trên một bản tham chiếu + một mutant rồi bác nhầm một story đúng (360 §3.3)
- **Quyết định:** open — Chưa làm; không có quyết định nào được ghi lại.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một gạch đầu dòng khác của §9.3: Kiểm false rejection bên cạnh false acceptance.
- **Còn thiếu:** Toàn bộ, trừ S-10-a.

### P-11.1

> Cùng coding client/model chạy trực tiếp, cùng task và sandbox

- **Nguồn:** đề xuất §11.1 (nhánh A)
- **Bằng chứng tại HEAD:** Harness có ba cánh `direct`, `aisef`, `aisef+`; EXPERIMENT-PLAN: A direct, B aisef, C aisef+ fix-loop. Không có sandbox chung cho các cánh.
- **Kiểm cơ học:** `validation/experiments/harness.py` chứa `ARMS = ("direct", "aisef", "aisef+")`
- **Reproducer:** `tests/v2/test_v21_experiment.py::Experiment::test_a_pair_differs_in_the_variable_under_test_only`
- **Ảnh hưởng:** quyết định
- **Quyết định:** blocked — Chặn trên ngân sách (B-09) và sandbox (F).
- **Commit:** `a29e82b`: validation/experiments/harness.py
- **Mức (REPORT §2):** E1 = M3, E2 = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với đoạn dưới bảng §11.1: Ghi patch set của B; không gắn nhãn B là v2.0.0 nguyên bản.
- **Còn thiếu:** E2: MỞ; sandbox chung: MỞ.

### P-11.2

> Canary trước: một story, ngân sách nhỏ, đi qua cài package → CLI → client → probe → review → kết quả cuối.

- **Nguồn:** đề xuất §11.2
- **Bằng chứng tại HEAD:** Bậc 0 offline đã chạy trên b72e51e: CLI thật + OCR thật + preflight HTTP tới provider giả trên loopback + developer giả; chạy bằng `python -m aisef` với PYTHONPATH của cây, không cài từ package. Bậc 1–2 (provider thật) chờ duyệt (B-09).
- **Kiểm cơ học:** `validation/v21/cli_integration/run.sh` chứa `PYTHONPATH=$W`
- **Reproducer:** Không có test (là lượt chạy; output đã commit).
- **Ảnh hưởng:** cao: RC1 qua mọi kiểm offline rồi chết ở preflight live (360 §3.3)
- **Quyết định:** blocked — Chặn trên ngân sách của chủ dự án (B-09).
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §11.2: Canary xanh mới mở thí nghiệm paired nhỏ trên một route.
- **Còn thiếu:** Canary live: MỞ. Bước 'cài package' chưa có trong lượt offline.

### P-11.3

> Cost ledger phải phân biệt input không cache, cache-read, cache-write và output; reasoning không đếm hai lần nếu provider đã gộp.

- **Nguồn:** đề xuất §11.3
- **Bằng chứng tại HEAD:** `usage.CLASSES` = input, cache_read, cache_write, output, reasoning; tiền = (output + reasoning) × giá output (`usage._usd`). Đo trong phiên lập bảng (lệnh ở cột reproducer) trên 270 step của luồng phiên smoke #2 (closure-evidence/v2/release/smoke-2/run-1/sessions): `total` = input + output + reasoning + cache.read + cache.write ở 270/270 step; 200 step có reasoning > 0 và ở cả 200 `total` ≠ input + output + cache; output 68 853 + reasoning 244 483 = 313 336 (con số output của EXPERIMENT-PLAN). Suy luận (INFERENCE): nếu `total` là số provider trả về thì `output` của client không gồm `reasoning` và `_usd` không đếm hai lần; nếu OpenCode tự cộng `total` từ chính các trường của nó thì đẳng thức đúng bất kể `output` chứa gì, và phép đo này không phân định được.
- **Kiểm cơ học:** `aisef2/app/usage.py` chứa `CLASSES = ("input", "cache_read", "cache_write", "output", "reasoning")`; `docs/v2.1/EXPERIMENT-PLAN.md` chứa `313 336 output (gồm 244 483 reasoning)`; `tests/v2/test_v21_continue_integrity.py` chứa `self.settings_doc = {**SETTINGS, "prices": PRICES}`; `tests/v2/test_v21_continue_integrity.py` chứa `"output": 7, "reasoning": 3,`
- **Reproducer:** `tests/v2/test_v21_continue_usage.py::Usage::test_without_prices_cost_is_unknown_never_zero` Test trên chỉ cho thấy tách 5 lớp token. Không test nào khẳng định số USD của một step có reasoning ≠ 0: số USD duy nhất được khẳng định (1.0, trong `Usage::test_with_prices_known_and_a_blind_step_makes_it_partial`) là của step o=0, r=0, cr=0. `tests/v2/test_v21_continue_integrity.py` (LineageBase) chạy `aisef run` với bảng giá (`"prices": PRICES`) và client giả báo reasoning 3 mỗi step, nhưng chỉ khẳng định token, và `cost.value` None khi chi tiêu không rõ. Phép đo token (không phải test), chạy ở gốc repo: `python3 -P -c "import glob,json;e=[json.loads(x) for f in sorted(glob.glob('closure-evidence/v2/release/smoke-2/run-1/sessions/*.jsonl')) for x in open(f,encoding='utf-8')];k=[x['part']['tokens'] for x in e if x.get('type')=='step_finish'];s=lambda t:t['input']+t['output']+t['cache']['read']+t['cache']['write'];r=[t for t in k if t['reasoning']];print(len(k),sum(t['total']==s(t)+t['reasoning'] for t in k),sum(t['output'] for t in k),sum(t['reasoning'] for t in k),len(r),sum(t['total']!=s(t) for t in r))"` in ra `270 270 68853 244483 200 200`.
- **Ảnh hưởng:** cao cho USD/story
- **Quyết định:** adopted — Đúng đề xuất.
- **Commit:** `d622e71`: aisef2/app/usage.py
- **Mức (REPORT §2):** D2 = M4 — Khớp REPORT (mức của D2, không của phép đo token); phép đo token là đo lại trong phiên này, không phải test.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §11.3: Lưu nguồn giá và ngày hiệu lực; với 9router/combo không có rate card, để unknown và báo token.
- **Còn thiếu:** Phép đo chỉ cho một phiên bản client (OpenCode 1.18.31 theo 360 §3.5); client/provider khác phải đo lại. Chưa test nào khẳng định số USD của một step có reasoning ≠ 0; 'không đếm hai lần' chưa được xác nhận trong mã OpenCode.
- **Chưa xác nhận được:** Cách OpenCode 1.18.31 điền `tokens.total` (số provider trả hay tự cộng từ các trường của nó): repo không chứa mã nguồn OpenCode — vì vậy kết luận 'không đếm hai lần' là INFERENCE.

### P-12-1

> Controller/runtime/evidence/key ở miền developer không ghi được; workload không cùng quyền kiểm soát với verifier.

- **Nguồn:** đề xuất §12 phải làm ngay
- **Bằng chứng tại HEAD:** Không đạt: developer và mã test chạy dưới user của người vận hành, sửa được mọi tệp user đó ghi được (REPORT §3).
- **Kiểm cơ học:** `docs/v2.1/REPORT.md` chứa `Điều **không** có: ranh giới hệ điều hành.`
- **Reproducer:** Không có.
- **Ảnh hưởng:** cao
- **Quyết định:** blocked — Như P-V2-05.
- **Mức (REPORT §2):** F = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này (§12 'Phần phải làm ngay' nêu yêu cầu, không kèm tiêu chí); bảng đối chiếu với chính mục.
- **Còn thiếu:** Toàn bộ. MỞ.

### P-12-2

> `-S` có kiểm thử đường app thật và cách nạp dependency rõ ràng.

- **Nguồn:** đề xuất §12 phải làm ngay
- **Bằng chứng tại HEAD:** Test đi qua `run` (probe nhận interpreter của kernel, test nhận venv riêng); probe chỉ stdlib (360 §3.6). Không có lượt live.
- **Reproducer:** `tests/v2/test_v21_identity.py::PthChannel::test_the_run_gives_the_probes_this_interpreter_and_the_tests_their_own`
- **Ảnh hưởng:** cao
- **Quyết định:** adopted — Đúng đề xuất ở mức offline.
- **Commit:** `919a271`: aisef2/app/run.py, tests/v2/test_v21_identity.py
- **Mức (REPORT §2):** A1 = M3 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §12: Không khẳng định chỉ thêm flag là giải quyết confinement.
- **Còn thiếu:** Không có lượt live qua đường app thật.

### P-12-3

> Candidate code chạy trong tiến trình/môi trường riêng, không được nạp vào process giữ khóa.

- **Nguồn:** đề xuất §12 phải làm ngay
- **Bằng chứng tại HEAD:** Có từ 2.0: subject chạy trong tiến trình riêng do controller sinh, kênh phán quyết HMAC (360 §3.4 'Mạnh'). 2.1 thêm `-S` cho mọi lần khởi chạy đó.
- **Kiểm cơ học:** `aisef2/probe/process_effect.py` chứa `agent = subprocess.Popen([req["interpreter"], "-I", "-S", "-B"`
- **Reproducer:** `tests/v2/test_v21_identity.py::PthChannel::test_every_active_probe_launch_carries_minus_S`
- **Ảnh hưởng:** cao
- **Quyết định:** adopted — Đã có trong 2.0; không triển khai lại.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này (§12 'Phần phải làm ngay' nêu yêu cầu, không kèm tiêu chí); bảng đối chiếu với chính mục.
- **Còn thiếu:** Cùng user: không phải môi trường riêng ở mức OS.
- **Chưa xác nhận được:** Các test tấn công của 2.0 ('20 test tấn công', 360 §3.4) không được định danh lại trong phiên này.

### P-12-4

> Journal hash chain phát hiện một số sửa đổi khi có checkpoint đáng tin; không tự chống kẻ cùng quyền viết lại cả chuỗi.

- **Nguồn:** đề xuất §12 phải làm ngay
- **Bằng chứng tại HEAD:** Anchor = sha256 của `EVIDENCE.json` in ra cuối lượt; `--verify --expect-anchor` bác việc viết lại nhất quán cả thư mục; tệp anchor `O_CREAT|O_EXCL|O_NOFOLLOW`, 0444 (ADR-3, ANCHOR-THREAT-MODEL.md).
- **Kiểm cơ học:** `docs/v2.1/ANCHOR-THREAT-MODEL.md` tồn tại
- **Reproducer:** `tests/v2/test_v21_continue_integrity.py::AnchorThreatModel::test_an_attacker_who_cannot_write_the_store_is_refuted`, `tests/v2/test_v21_continue_integrity.py::AnchorThreatModel::test_the_limit_an_attacker_who_can_write_the_store_too_is_not_detected`, `tests/v2/test_v21_continue_integrity.py::AnchorThreatModel::test_the_anchor_file_is_new_exact_and_never_through_a_link`
- **Ảnh hưởng:** cao
- **Quyết định:** adopted — Đúng đề xuất: tuyên bố giới hạn ở 'toàn vẹn so với một giá trị'.
- **Commit:** `ad78ce7`: aisef2/app/verify.py; `872e83c`: aisef2/app/lineage.py
- **Mức (REPORT §2):** A2 = M4, D5 = M4 — Khớp REPORT về mức.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với một câu khác của cùng đoạn §12: Nếu tuyên bố tính xác thực, cần trust anchor/checkpoint ký hoặc dịch vụ append được bảo vệ bên ngoài miền workload.
- **Còn thiếu:** Nơi giữ anchor tin cậy chưa có (REPORT §7).
- **Chưa xác nhận được:** D5 'CLI thật: tệp 0444' (REPORT §2): output đã commit chỉ có `anchor_written_to`, không có mode của tệp.

### P-12-5

> Git tree, image và artifact digest kiểm ngay tại ranh giới sử dụng, không chỉ khi người viết báo xong.

- **Nguồn:** đề xuất §12 phải làm ngay
- **Bằng chứng tại HEAD:** Nhị phân OCR chạy chỉ khi đúng sha256 đã ghim, theo đường dẫn tuyệt đối; checkout được chụp trước và so lại sau finder; nguồn thí nghiệm phải là commit sạch.
- **Kiểm cơ học:** `aisef2/app/review_ocr.py` chứa `def pinned(`
- **Reproducer:** `tests/v2/test_v21_review_ocr.py::Process::test_the_binary_runs_only_as_the_pinned_bytes_by_absolute_path`, `tests/v2/test_v21_review_chain.py::CandidateChangedDuringReview::test_a_finder_binary_that_is_not_the_pinned_one_does_not_run`, `tests/v2/test_v21_experiment.py::Experiment::test_the_source_is_a_clean_commit`
- **Ảnh hưởng:** cao
- **Quyết định:** adapted — Làm cho các ranh giới mới của 2.1 (OCR, review, thí nghiệm); không có image nào để kiểm.
- **Commit:** `e897437`: aisef2/app/review_ocr.py; `390f07c`: aisef2/app/review_ocr.py; `a29e82b`: validation/experiments/harness.py
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** Đề xuất không ghi tiêu chí nghiệm thu cho mục này (§12 'Phần phải làm ngay' nêu yêu cầu, không kèm tiêu chí); bảng đối chiếu với chính mục.
- **Còn thiếu:** Cùng user: giữa lúc kiểm và lúc dùng vẫn có thể bị thay (TOCTOU) — chỉ ranh giới OS đóng được.

### P-GATE-2.0.1

> **2.0.1:** reproducer lỗi đã biết được xử lý; release lane và metadata đúng; loader/preflight không làm mất phân loại; canary từ package thật chạy được.

- **Nguồn:** đề xuất §12 gate
- **Bằng chứng tại HEAD:** `release/v2.0.1-prep` = f006d3d (local, chưa push): suite đầy đủ Ran 5497, 4 F (so bản ghi niêm phong), 80 skip (REPORT §5); chưa CI/RC/Q0–Q5/tag; chưa canary từ package thật.
- **Kiểm cơ học:** `docs/v2.1/REPORT.md` chứa `Ran 5497, **4 F**, 80 skip`
- **Reproducer:** `f006d3d1b23ef9d318078642d16c7bdfa7687a98:tests/v2/test_v201_venvs.py::TwoVenvs::test_a_pth_written_from_the_tests_interpreter_never_runs_in_a_probe`
- **Ảnh hưởng:** cao
- **Quyết định:** blocked — B-02: phát hành 2.0.1 là quyết định của chủ dự án (chưa duyệt).
- **Commit:** `c0ec1a5` (trên `f006d3d`): aisef2/app/run.py, aisef2/orchestrate/story_runner.py, CHANGELOG.md; `f006d3d` (trên `f006d3d`): aisef2/app/run.py, tests/v2/test_v201_relative_paths.py
- **Mức (REPORT §2):** A11 = M3 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** reproducer lỗi đã biết được xử lý; release lane và metadata đúng; loader/preflight không làm mất phân loại; canary từ package thật chạy được (§12; STATUS B-02 thêm: gate `v2_release_gate 2.0.1` PASS, byte PyPI = byte RC)
- **Còn thiếu:** Gate chưa đạt.

### P-GATE-2.1

> **2.1 pilot:** người ngoài tạo và chạy bundle nhỏ; một workload chưa thấy hoàn tất không miễn trừ; LedgerLock repo thật được kiểm; lỗi review confirmed không bị bỏ qua; chi phí minh bạch; Linux isolation đủ cho holdout; resume qua các điểm crash định trước.

- **Nguồn:** đề xuất §12 gate
- **Bằng chứng tại HEAD:** Người ngoài: chưa đo. Workload chưa thấy: không có lượt live. LedgerLock repo thật: chưa. Review confirmed: M4 offline, 4/5 lỗi lịch sử. Chi phí: M4 offline, chưa có giá thật. Linux isolation: M6. Resume qua điểm crash: M4 (nối tiếp, không tại chỗ).
- **Kiểm cơ học:** `docs/v2.1/REPORT.md` chứa `**Chưa đủ điều kiện phát hành.**`
- **Reproducer:** Xem các hàng tương ứng.
- **Ảnh hưởng:** quyết định phát hành
- **Quyết định:** open — Gate chưa đạt; không có quyết định phát hành nào.
- **Mức (REPORT §2):** F = M6, E2 = M6, D1 = M4, C1 = M4, D2 = M4 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** người ngoài tạo và chạy bundle nhỏ; một workload chưa thấy hoàn tất không miễn trừ; LedgerLock repo thật được kiểm; lỗi review confirmed không bị bỏ qua; chi phí minh bạch; Linux isolation đủ cho holdout; resume qua các điểm crash định trước (§12)
- **Còn thiếu:** Sáu trên bảy điều kiện chưa đạt hoặc chưa đo.

### P-GATE-2.2

> **2.2 mở rộng:** thêm client và chế độ kiểm PR/candidate độc lập sau khi có bằng chứng pilot;

- **Nguồn:** đề xuất §12 gate
- **Bằng chứng tại HEAD:** Không có commit 2.1 nào cho client thứ hai hay chế độ kiểm độc lập.
- **Reproducer:** Không có.
- **Ảnh hưởng:** —
- **Quyết định:** declined — Ngoài phạm vi 2.1 theo chính đề xuất.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** Toàn bộ (2.2).

### P-13-1

> Viết lại toàn bộ kernel bằng framework khác hoặc kết hợp ba orchestrator vào một runtime.

- **Nguồn:** đề xuất §13 việc nên hoãn
- **Bằng chứng tại HEAD:** Không có: ADR-V2.1 giữ một đường quyết định, 'Không viết lại khung, không nhập orchestrator ngoài'; OCR chạy như tiến trình ngoài.
- **Kiểm cơ học:** `docs/v2.1/ADR-V2.1.md` chứa `Không viết lại khung, không nhập orchestrator ngoài.`
- **Reproducer:** Không có (không xây gì).
- **Ảnh hưởng:** —
- **Quyết định:** declined — Hoãn theo đề xuất; tại HEAD được giữ.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** —

### P-13-2

> Cho LLM tự sửa acceptance, tự cấp approval hoặc tự kết luận metric đạt.

- **Nguồn:** đề xuất §13 việc nên hoãn
- **Bằng chứng tại HEAD:** `aisef bundle approve` chỉ nhận `human:<tên>`; `seal` không bao giờ duyệt; checker B-03c bắt mọi đường `migrate` tạo/sửa approval.
- **Reproducer:** `tests/v2/test_v21_bundle_tools.py::Refusals::test_an_approver_that_is_not_a_human_identity_is_refused`, `tests/v2/test_v21_authority_limits.py::MigrateNeverApproves::test_an_approval_created_rather_than_re_loaded_is_caught`
- **Ảnh hưởng:** —
- **Quyết định:** declined — Hoãn theo đề xuất; tại HEAD được giữ.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** —
- **Chưa xác nhận được:** Công cụ không biết ai gõ lệnh: phải giữ bundle và lệnh ngoài tầm developer agent (ADR-6) — chưa có ranh giới OS.

### P-13-3

> Chạy nhiều developer song song trước khi sửa PRESERVE, resume và ranh giới ghi.

- **Nguồn:** đề xuất §13 việc nên hoãn
- **Bằng chứng tại HEAD:** Không commit 2.1 nào thêm developer song song (danh sách commit 610a593..c9c736f).
- **Reproducer:** Không có (không xây gì).
- **Ảnh hưởng:** —
- **Quyết định:** declined — Hoãn theo đề xuất; tại HEAD được giữ.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** —
- **Chưa xác nhận được:** Suy từ tiêu đề commit; không đọc lại mã của runner.

### P-13-4

> Mở thêm Q/mutation để tăng con số thay vì tái hiện lỗi sử dụng.

- **Nguồn:** đề xuất §13 việc nên hoãn
- **Bằng chứng tại HEAD:** Không thêm bậc Q mới. Có mở phase mutation V2.1 (443 target / 11 365 mutant, 55a6b74) như phần tái thẩm định B-03b do chủ dự án cho phép (RELEASE-DECISIONS seq 5) — vì 2.1 sửa kernel mà bằng chứng 2.0 ràng buộc theo byte.
- **Kiểm cơ học:** `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` chứa `AISEF_V2_1_B03_REQUALIFICATION_ROUND`
- **Reproducer:** Không có (không xây gì).
- **Ảnh hưởng:** —
- **Quyết định:** declined — Hoãn theo đề xuất; tại HEAD được giữ.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** —
- **Chưa xác nhận được:** Có phải 'tăng con số' hay không là đánh giá của chủ dự án; bảng chỉ ghi sự việc.

### P-13-5

> Dùng AST hash như chứng minh đủ của tương đương chương trình.

- **Nguồn:** đề xuất §13 việc nên hoãn
- **Bằng chứng tại HEAD:** ADR-2 'Không tuyên bố': digest khớp không chứng minh tương đương; băm AST cũng không. STATUS B7.
- **Kiểm cơ học:** `docs/v2.1/ADR-V2.1.md` chứa `băm AST cũng không`
- **Reproducer:** Không có (không xây gì).
- **Ảnh hưởng:** —
- **Quyết định:** declined — Hoãn theo đề xuất; tại HEAD được giữ.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** —

### P-13-6

> Xây memory tự học xuyên dự án trước khi có nguồn gốc, phạm vi và kiểm soát rò hidden test.

- **Nguồn:** đề xuất §13 việc nên hoãn
- **Bằng chứng tại HEAD:** Không có memory xuyên dự án nào (danh sách tệp đổi 610a593..c9c736f).
- **Reproducer:** Không có (không xây gì).
- **Ảnh hưởng:** —
- **Quyết định:** declined — Hoãn theo đề xuất; tại HEAD được giữ.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** —

### P-13-7

> Dashboard lớn, nhiều compute backend và sandbox Windows trước bằng chứng hiệu quả trên Linux.

- **Nguồn:** đề xuất §13 việc nên hoãn
- **Bằng chứng tại HEAD:** Không có (danh sách tệp đổi 610a593..c9c736f).
- **Reproducer:** Không có (không xây gì).
- **Ảnh hưởng:** —
- **Quyết định:** declined — Hoãn theo đề xuất; tại HEAD được giữ.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** —

### R-P0-1

> Chạy controller và test runner với `-S`

- **Nguồn:** báo cáo 360° §5 P0 #1
- **Bằng chứng tại HEAD:** Như P-V2-01: `-S` + interpreter của kernel trên 2.1; hai venv trên 2.0.1 (c0ec1a5, chưa phát hành).
- **Reproducer:** `tests/v2/test_v21_identity.py::PthChannel::test_a_probe_on_an_interpreter_holding_a_pth_never_runs_it`, `f006d3d1b23ef9d318078642d16c7bdfa7687a98:tests/v2/test_v201_venvs.py::TwoVenvs::test_a_pth_written_from_the_tests_interpreter_never_runs_in_a_probe`
- **Ảnh hưởng:** cao (360 §3.4; mức 'low' của V21-28 được nâng)
- **Quyết định:** adopted — Xem P-V2-01.
- **Commit:** `919a271`: aisef2/probe/process_effect.py; `c0ec1a5` (trên `f006d3d`): tests/v2/test_v201_venvs.py
- **Mức (REPORT §2):** A1 = M3 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; theo chính mục: controller và test runner chạy với `-S` (hoặc băm cây venv trước mỗi probe; venv riêng cho test của developer)
- **Còn thiếu:** Chưa đo một vụ giả mạo end-to-end qua `.pth` trong `aisef run` thật (360 §9) — giờ đã đóng ở mức cơ chế, OS chưa.

### R-P0-2

> Trang PyPI đúng 2.0: README V2 làm long description, liên kết tuyệt đối, summary/classifier, thêm `LICENSE`

- **Nguồn:** báo cáo 360° §5 P0 #2
- **Bằng chứng tại HEAD:** Metadata 2.x + classifiers + LICENSE (b819a57); README tự chứa cho PyPI được chuẩn bị bằng `validation/v21/public_readme.py` (2cad415), chưa dùng cho bản phát hành nào.
- **Kiểm cơ học:** `pyproject.toml` chứa `Development Status :: 4 - Beta`
- **Reproducer:** `tests/test_v21_public_readme.py::PublicReadme::test_the_self_contained_readme_has_no_relative_link`
- **Ảnh hưởng:** trung bình (trang công khai duy nhất nói sai sản phẩm)
- **Quyết định:** adapted — Metadata/LICENSE xong; README trên PyPI chờ chủ dự án chọn nơi đăng tài liệu (B-10).
- **Commit:** `b819a57`: pyproject.toml, LICENSE; `2cad415`: validation/v21/public_readme.py, tests/test_v21_public_readme.py
- **Mức (REPORT §2):** A10 = M4 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với STATUS B-10: không link 404
- **Còn thiếu:** Trang PyPI của 2.0.0 không đổi được nếu không phát hành (B-02); B-10 chưa quyết.

### R-P0-3

> Làn vá 2.0.x: tham số hoá `release_rc.py`/`v2_release_gate.py` theo phiên bản; runbook vá (3 tầng: tài liệu / mã ngoài kernel / kernel) và runbook yank

- **Nguồn:** báo cáo 360° §5 P0 #3
- **Bằng chứng tại HEAD:** Công cụ theo phiên bản (aa3c18a). Không có runbook vá/yank mới: danh sách tệp `docs/` đổi trong 610a593..c9c736f không có.
- **Reproducer:** `tests/v2/test_v21_release_lane.py::Gate::test_each_release_has_its_own_status_file`
- **Ảnh hưởng:** trung bình
- **Quyết định:** adapted — Công cụ xong; runbook chưa viết, không có quyết định ghi lại.
- **Commit:** `aa3c18a`: validation/qualification/release_rc.py, validation/v2_release_gate.py
- **Mức (REPORT §2):** A9 = M4 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; theo chính mục: `release_rc.py`/`v2_release_gate.py` nhận phiên bản làm tham số; có runbook vá 3 tầng và runbook yank
- **Còn thiếu:** Runbook vá (3 tầng) và runbook yank: chưa có.

### R-P0-4

> Người duyệt bắt buộc cho môi trường `pypi`, bảo vệ tag `v*`, ghim SHA mọi action

- **Nguồn:** báo cáo 360° §5 P0 #4
- **Bằng chứng tại HEAD:** Workflow vẫn dùng tag (`actions/checkout@v4`, `pypa/gh-action-pypi-publish@release/v1`); sổ RELEASE-DECISIONS có seq 4–5 (B-01, B-03), không có mục cho phán quyết 'FINAL RELEASE EXECUTION'. Cài đặt môi trường/tag trên GitHub: không kiểm được từ repo.
- **Kiểm cơ học:** `.github/workflows/release.yml` chứa `actions/checkout@v4`; `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` không chứa `FINAL RELEASE EXECUTION`
- **Reproducer:** Không có.
- **Ảnh hưởng:** cao: cổng con người khi phát hành là mềm (360 §3.4, §3.8)
- **Quyết định:** open — Không có commit 2.1; phần GitHub settings là của chủ dự án; ghim SHA chưa làm.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; theo chính mục: môi trường `pypi` có người duyệt bắt buộc, tag `v*` được bảo vệ, mọi action ghim SHA, phán quyết 'FINAL RELEASE EXECUTION' có trong RELEASE-DECISIONS
- **Còn thiếu:** Toàn bộ.

### R-P0-5

> gỡ hoặc thay mọi liên kết GitHub trên aisef.io, salekit và `project.urls` của PyPI

- **Nguồn:** báo cáo 360° §5 P0 #5
- **Bằng chứng tại HEAD:** `project.urls` chỉ còn Homepage aisef.io (b819a57). Còn link `github.com/nghinh/aisef` trong README.vi.md, docs/SALEKIT.html, landingpage/index.html tại HEAD.
- **Kiểm cơ học:** `pyproject.toml` chứa `Homepage = "https://aisef.io/"`; `landingpage/index.html` chứa `github.com/nghinh/aisef`; `docs/SALEKIT.html` chứa `github.com/nghinh/aisef`
- **Reproducer:** Không có.
- **Ảnh hưởng:** cao về uy tín (360 §3.9)
- **Quyết định:** adapted — Metadata gói xong; trang công khai chờ B-10 (chủ dự án).
- **Commit:** `b819a57`: pyproject.toml
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với STATUS B-10: không link 404
- **Còn thiếu:** Link trên landing, salekit, README.vi: còn.

### R-P1-6

> V21-37 + V21-38 cùng lúc: tiêu chí import theo AST; chứng minh PRESERVE của story trước **ở bước ứng viên**

- **Nguồn:** báo cáo 360° §5 P1 #6
- **Bằng chứng tại HEAD:** Như P-V2-06.
- **Reproducer:** `tests/v2/test_v21_orchestration.py::PreserveAtCandidate::test_a_regression_the_developer_made_is_the_developer_s_and_never_merged`, `tests/v2/test_v21_python_imports.py::Controls::test_the_approved_regex_reproduces_the_false_rollback`
- **Ảnh hưởng:** cao
- **Quyết định:** adopted — Xem P-V2-06.
- **Commit:** `91a8968`: aisef2/orchestrate/story_runner.py; `06d4e62`: aisef2/probe/file_artifact.py
- **Mức (REPORT §2):** B1 = M3, B3 = M3 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục: lỗi DEVELOPER, có phản hồi
- **Còn thiếu:** Contract S-10-a: B-04 chưa duyệt.

### R-P1-7

> Công cụ bundle: API công khai + `aisef bundle init/seal/lint/rebind`, ví dụ ship kèm, tài liệu ngữ pháp contract cho 18 lớp quan sát; danh tính probe = phiên bản + băm AST không docstring

- **Nguồn:** báo cáo 360° §5 P1 #7
- **Bằng chứng tại HEAD:** Như P-V2-07 và P-V2-08. `rebind` có dưới tên `migrate`. Danh tính probe = CAPABILITY_VERSION (không băm AST).
- **Reproducer:** `tests/v2/test_v21_bundle_tools.py::Outsider::test_each_example_from_init_to_a_ready_check`, `tests/v2/test_v21_identity.py::ThreeIdentities::test_a_spec_binds_the_capability_and_the_bytes_are_their_own_digest`
- **Ảnh hưởng:** cao
- **Quyết định:** adapted — Băm AST bị loại theo đề xuất §3 và ADR-2 (không chứng minh tương đương).
- **Commit:** `620bde7`: aisef2/app/bundle_cli.py; `919a271`: aisef2/probe/calibration.py
- **Mức (REPORT §2):** B4 = M4, B5 = M4, B6 = M3 — Khớp REPORT. B4/B5: M4 là của lượt CLI thật tại `b72e51e` (docs/v2.1/evidence/cli-integration-b72e51e.out); `aisef2/app/bundle_cli.py` đổi sau lượt đó ở a912be6 và 3061ec0 (đường ghi của init/seal/approve/migrate chuyển sang tạo độc quyền `_create`), lượt lặp lại tại c9c736f (`docs/v2.1/evidence/cli-integration-c9c736f.out`, vòng 2 của bảng này: cùng `run.sh`, cùng nhị phân OCR, clone sạch tại c9c736f) cho cùng output — khác nhau chỉ ở giá trị băm (commit của repo `git init` mới, plan_hash, anchor, sha256), pid, mốc thời gian và dòng cuối bị cắt ở 3000 ký tự: M4 tại c9c736f. (kiểm cơ học ở P-V2-07)
- **Tiêu chí nghiệm thu:** một người ngoài dựng bundle cho một dự án 3 story không cần đọc mã nguồn (360 §6)
- **Còn thiếu:** Người ngoài: chưa đo.
- **Chưa xác nhận được:** Tài liệu ngữ pháp cho 18 lớp quan sát: không kiểm trong phiên này.

### R-P1-8

> Chính sách review: không chặn, nhưng **đưa phát hiện thành phản hồi cho developer**, ghi vào journal, đo precision

- **Nguồn:** báo cáo 360° §5 P1 #8
- **Bằng chứng tại HEAD:** Như P-ADJ-3: chặn khi CONFIRMED ∧ ANCHORED (fix-loop); phát hiện vào prompt retry. 5 phát hiện lịch sử của smoke #2 tái hiện trên dạng lỗi của chúng (CONFIRMED) và không tái hiện trên bản tham chiếu (NOT_REPRODUCED) — regression offline của bộ kiểm chứng; precision của reviewer chưa đo trong 2.1.
- **Reproducer:** `tests/v2/test_v21_review.py::HistoricalDefects::test_each_shipped_defect_is_confirmed_on_its_shape_and_not_on_the_reference`
- **Ảnh hưởng:** cao
- **Quyết định:** adapted — Đề xuất (§3) thay 'không chặn' bằng chặn có điều kiện; chủ dự án thêm điều kiện neo.
- **Commit:** `e897437`: aisef2/app/feedback.py; `390f07c`: aisef2/app/review_verify.py
- **Mức (REPORT §2):** C1 = M4 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục: đo precision (smoke #2: 5/5)
- **Còn thiếu:** Precision của reviewer: chưa đo. Precision/recall với mô hình thật: M6 (B-06, ngân sách).

### R-P1-9

> Bậc "độ đặc hiệu" cho spec: mỗi spec phải SATISFIED trên ≥2 cài đặt đúng độc lập + đối chứng âm cú pháp

- **Nguồn:** báo cáo 360° §5 P1 #9
- **Bằng chứng tại HEAD:** Như P-9.3: chưa có.
- **Reproducer:** `tests/v2/test_v21_python_imports.py::Controls::test_each_draft_holds_on_the_smoke2_shape_and_refutes_a_real_import`
- **Ảnh hưởng:** cao
- **Quyết định:** open — Chưa làm; không có quyết định nào được ghi lại.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục: mỗi spec SATISFIED trên ≥ 2 cài đặt đúng độc lập, kèm đối chứng âm cú pháp (spec không bác nhầm)
- **Còn thiếu:** Toàn bộ, trừ S-10-a.

### R-P1-10

> Corpus "ghi thật" phát lại qua đường sản phẩm (`app.run.execute`, parser client thật, preflight) từ các luồng đã có trong smoke

- **Nguồn:** báo cáo 360° §5 P1 #10
- **Bằng chứng tại HEAD:** Như P-V2-12: chưa có.
- **Reproducer:** Không có.
- **Ảnh hưởng:** cao
- **Quyết định:** open — Chưa làm; không có quyết định nào được ghi lại.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục.
- **Còn thiếu:** Toàn bộ.

### R-P1-11

> Điểm dữ liệu thứ hai **có giá tiền**: cùng bundle, model khác (0 dòng mã) + lặp lại DeepSeek để đọc phương sai; ghi bảng giá, báo USD/story

- **Nguồn:** báo cáo 360° §5 P1 #11
- **Bằng chứng tại HEAD:** Không có lượt live nào trong 2.1 (REPORT: 'Không mục nào đạt M5'). Bảng giá DeepSeek đọc ngày 2026-10-06 có trong EXPERIMENT-PLAN; ledger tiền (D2) sẵn sàng.
- **Kiểm cơ học:** `docs/v2.1/REPORT.md` chứa `Không mục nào đạt M5`
- **Reproducer:** Không có.
- **Ảnh hưởng:** quyết định
- **Quyết định:** blocked — Ngân sách của chủ dự án (B-09).
- **Mức (REPORT §2):** E2 = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** USD/story được báo (360 §6)
- **Còn thiếu:** Live: MỞ.

### R-P1-12

> Giới hạn developer: ít nhất kiểm toán "tầm với" vào `RUN.json` và đưa bundle ra khỏi thư mục cha của workspace; sau đó sandbox thật cho cả macOS và Linux (V21-02/06)

- **Nguồn:** báo cáo 360° §5 P1 #12
- **Bằng chứng tại HEAD:** Sửa `RUN.json` giờ bị `--verify` bác (A2). Sandbox: không có (F M6). Thí nghiệm có `leaks` (phát hiện, không ngăn).
- **Reproducer:** `tests/v2/test_v21_verify.py::RecordAlone::test_story_outcomes_that_are_not_the_journal_s_are_refuted`
- **Ảnh hưởng:** cao (69 lời gọi ra ngoài workspace ở smoke #2)
- **Quyết định:** blocked — Như P-V2-05.
- **Mức (REPORT §2):** A2 = M4, F = M6 — Khớp REPORT.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: 0 (hoặc được báo) (360 §7, chỉ số 'Đọc ra ngoài workspace của developer')
- **Còn thiếu:** Sandbox: MỞ.
- **Chưa xác nhận được:** 'Đưa bundle ra khỏi thư mục cha của workspace': không kiểm trong phiên này bundle nằm ở đâu so với workspace của developer.

### R-P1-13

> Bộ nạp an toàn: mọi lỗi đầu vào → mã 2 kèm đường dẫn JSON; `--check` trả đúng lý do B4; endpoint qua `urlparse`; `redact` trong `finally`; lỗi git → ENVIRONMENT

- **Nguồn:** báo cáo 360° §5 P1 #13
- **Bằng chứng tại HEAD:** Như P-V2-04.
- **Reproducer:** `tests/v2/test_v21_inputs.py::InputFiles::test_cli_exit_2_for_unreadable_inputs`, `tests/v2/test_v21_inputs.py::RepositoryRefusal::test_check_mode_on_such_a_repository_is_ready`, `tests/v2/test_v21_inputs.py::Endpoint::test_loopback_and_https_are_accepted`, `tests/v2/test_v21_transport.py::Redaction::test_an_interrupted_session_still_leaves_no_secret`, `tests/v2/test_v21_orchestration.py::DiffFailure::test_a_retry_budget_takes_the_story_to_its_next_attempt`
- **Ảnh hưởng:** trung bình–cao
- **Quyết định:** adopted — Xem P-V2-04.
- **Commit:** `106f72d`: aisef2/app/bundle.py; `b029236`: aisef2/app/client.py; `51c5241`: aisef2/orchestrate/workspace.py
- **Mức (REPORT §2):** A3 = M3, A4 = M3, A5 = M4, A6 = M3, A7 = M3, A8 = M3 — Khớp REPORT; xem ghi chú về A5 ở P-V2-04.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục: mọi lỗi đầu vào → mã 2 kèm đường dẫn JSON
- **Còn thiếu:** Như P-V2-04: Preflight thật mới chỉ tới loopback, chưa gặp redirect thật (REPORT §2 A6–A7). Điều kiện của A5 (khoá git của editor) chỉ tái hiện ở test (M3): repo của lượt CLI thật (`git init` sạch) không có khoá đó.

### R-P2-14

> Tách 1.x thành `aisef-legacy` (hoặc chỉ giữ `aisef legacy …`); `doctor` biết V2

- **Nguồn:** báo cáo 360° §5 P2 #14
- **Bằng chứng tại HEAD:** Không tách. 2.1 chỉ thêm `aisef bundle` đi vào V2 (919a271 sửa aisef/cli/parser.py).
- **Reproducer:** `tests/test_v21_bundle_dispatch.py::BundleIsV2::test_a_refusal_is_exit_2`
- **Ảnh hưởng:** trung bình
- **Quyết định:** declined — Kế hoạch 2.2 (360 §6).
- **Commit:** `919a271`: aisef/cli/parser.py
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** Toàn bộ (2.2).

### R-P2-15

> Client thứ hai (Claude Code hoặc Codex CLI); probe chạy với phụ thuộc đã khoá của dự án

- **Nguồn:** báo cáo 360° §5 P2 #15
- **Bằng chứng tại HEAD:** Như P-V2-14: không có.
- **Reproducer:** Không có.
- **Ảnh hưởng:** cao cho thị trường
- **Quyết định:** declined — Kế hoạch 2.2 (360 §6).
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** Toàn bộ (2.2).

### R-P2-16

> Định vị lại thành **nhân kiểm chứng / cổng chấp nhận** dùng được cho PR của bất kỳ agent nào (CI check)

- **Nguồn:** báo cáo 360° §5 P2 #16
- **Bằng chứng tại HEAD:** Không có chế độ kiểm candidate độc lập.
- **Reproducer:** Không có.
- **Ảnh hưởng:** cao cho thị trường
- **Quyết định:** declined — Kế hoạch 2.2 (360 §6; đề xuất V2-14).
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** Toàn bộ (2.2).

### R-P2-17

> Chính sách phát hành cân xứng: tầng vá, một canary live rẻ ở **đầu** mỗi RC, ngân sách trả tiền cộng dồn có điểm dừng

- **Nguồn:** báo cáo 360° §5 P2 #17
- **Bằng chứng tại HEAD:** Công cụ theo phiên bản (aa3c18a); B-09 đề xuất canary trước, quy tắc dừng theo chi phí `known` cộng dồn — chưa duyệt.
- **Kiểm cơ học:** `docs/v2.1/decisions/B-09-CANARY-THEN-CAMPAIGN.md` chứa `` dừng khi chi phí `known` cộng dồn chạm trần ``
- **Reproducer:** Không có.
- **Ảnh hưởng:** trung bình
- **Quyết định:** blocked — Chủ dự án (B-02, B-09).
- **Commit:** `aa3c18a`: validation/qualification/release_rc.py
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục.
- **Còn thiếu:** Chính sách chưa được duyệt.

### R-P2-18

> Ăn kiêng bằng chứng: digest + tóm tắt trong git, luồng phiên thô và chunk Q4 sang release asset/LFS; tách test đọc bằng chứng khỏi bộ unit

- **Nguồn:** báo cáo 360° §5 P2 #18
- **Bằng chứng tại HEAD:** Không làm. Bộ evidence ứng viên của 2.1 được ghi ra ngoài repo (88fc7fb) — để không làm nhiễu checker, không phải để giảm kích thước.
- **Kiểm cơ học:** `validation/v21/candidate_evidence.py` tồn tại
- **Reproducer:** Không có.
- **Ảnh hưởng:** trung bình
- **Quyết định:** declined — Kế hoạch 2.2 (360 §5 P2).
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** Toàn bộ.

### R-P2-19

> Mutation: ràng buộc theo AST của từng hàm thay vì sha256 nguyên file; thêm toán tử xoá câu lệnh, biên số, handler

- **Nguồn:** báo cáo 360° §5 P2 #19
- **Bằng chứng tại HEAD:** Như P-ADJ-6: tái sử dụng theo byte của tệp target + closure của kill test + generator; không AST từng hàm.
- **Reproducer:** `tests/v2/test_v21_mutation_record.py::Proof::test_a_result_measured_at_head_is_usable`
- **Ảnh hưởng:** trung bình
- **Quyết định:** declined — Đề xuất §3: AST từng hàm bỏ sót global/import/fixture/dependency. Toán tử mutation mới: không có trong 2.1.
- **Commit:** `55a6b74`: validation/qualification/v21_mutation_record.py
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** —
- **Còn thiếu:** Toán tử xoá câu lệnh / biên số / handler: chưa có.
- **Chưa xác nhận được:** 'Không có toán tử mới': suy từ commit 55a6b74 chỉ thêm target, chưa đọc diff của mutation.py.

### R-P2-20

> Giảm bus factor: runbook người bảo trì trong repo; một người review kernel không phải chủ dự án mỗi bản minor

- **Nguồn:** báo cáo 360° §5 P2 #20
- **Bằng chứng tại HEAD:** Không làm.
- **Reproducer:** Không có.
- **Ảnh hưởng:** cao (360 §8)
- **Quyết định:** open — Việc của chủ dự án; không có quyết định nào được ghi lại.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với chính mục.
- **Còn thiếu:** Toàn bộ.

### R-NOW

> **Không làm bây giờ (nói ra để khỏi bị hút vào)**: thêm bậc Q, chạy lại Q4 với cùng seed, mở rộng mutation trước khi có điểm dữ liệu live thứ hai; sandbox Windows; "cohort" niêm phong

- **Nguồn:** báo cáo 360° §5 'Không làm bây giờ'
- **Bằng chứng tại HEAD:** Không thêm bậc Q, không sandbox Windows, không cohort. Phase mutation V2.1 (443 target) chạy trước khi có điểm dữ liệu live thứ hai, như phần tái thẩm định B-03b do chủ dự án cho phép (RELEASE-DECISIONS seq 5).
- **Kiểm cơ học:** `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` chứa `AISEF_V2_1_B03_REQUALIFICATION_ROUND`
- **Reproducer:** Không có.
- **Ảnh hưởng:** —
- **Quyết định:** adapted — Giữ, trừ mutation: chủ dự án quyết định mở B-03b (tái thẩm định bắt buộc vì bằng chứng 2.0 ràng buộc byte kernel).
- **Commit:** `dc9774f`: closure-evidence/v2/cycle2/RELEASE-DECISIONS.json
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này (danh sách 'không làm bây giờ').
- **Còn thiếu:** Không còn việc với mục này (danh sách 'không làm'); điều chỉnh duy nhất là mutation, theo RELEASE-DECISIONS seq 5.
- **Chưa xác nhận được:** 'Không chạy lại Q4 cùng seed': không kiểm riêng trong phiên này.

### R-3.1

> Băm lại bỏ sót `runtime/process_range.py`, `range_anchor.py` — mã quyết định quan sát có thể đổi mà danh tính không đổi.

- **Nguồn:** báo cáo 360° §3.1 Yếu
- **Bằng chứng tại HEAD:** Vẫn đúng tại HEAD: PROBE_SOURCES (→ EXECUTION_DIGEST) của process_effect = protocol, python_callable, cli_invocation, process_effect; process_effect import `aisef2.runtime.process_range`, process_range chạy `range_anchor.py`.
- **Kiểm cơ học:** `aisef2/probe/process_effect.py` chứa `PROBE_SOURCES = ("probe/protocol.py", "probe/python_callable.py", "probe/cli_invocation.py", "probe…`; `aisef2/probe/process_effect.py` chứa `from aisef2.runtime.process_range import ProcessRange`; `aisef2/runtime/process_range.py` chứa `ANCHOR = pathlib.Path(__file__).with_name("range_anchor.py")`
- **Reproducer:** Không có test nào ràng buộc hai tệp runtime vào EXECUTION_DIGEST (phát hiện chưa sửa).
- **Ảnh hưởng:** trung bình: byte quyết định quan sát của process_effect đổi được mà hàng hiệu chuẩn/RunSpec không đổi
- **Quyết định:** open — Không có commit 2.1 và không có quyết định nào được ghi lại.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** 360 không ghi tiêu chí nghiệm thu cho mục này; bảng đối chiếu với định nghĩa ở đề xuất §9.2 mục 3 (định nghĩa, không phải tiêu chí nghiệm thu): Execution digest: đúng byte của probe/runtime/dependency đã dùng tạo bằng chứng
- **Còn thiếu:** Toàn bộ. Sửa sẽ chạm `aisef2/probe` (kernel): cần mutation + hiệu chuẩn lại, ngoài snapshot đang đo.

### R-M1

> Lượt live đạt `delivery_verdict PASS` (không miễn trừ)

- **Nguồn:** báo cáo 360° §7 bảng chỉ số
- **Bằng chứng tại HEAD:** 0 lượt live trong 2.1 (REPORT: không mục nào đạt M5).
- **Kiểm cơ học:** `docs/v2.1/REPORT.md` chứa `Không mục nào đạt M5`
- **Reproducer:** Chỉ số, không phải hành vi: không có reproducer.
- **Ảnh hưởng:** theo dõi
- **Quyết định:** blocked — Ngân sách (B-09).
- **Mức (REPORT §2):** Chỉ số: REPORT §2 không chấm mức cho chỉ số. Hạng mục liên quan: E2 — mức của hạng mục đó không phải mức của chỉ số này.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: ≥ 1 trên workload chưa từng thấy
- **Còn thiếu:** Chưa đạt: 0 lượt live trong 2.1 (mục tiêu ≥ 1 trên workload chưa từng thấy).

### R-M2

> Workload × route × hệ điều hành đã chạy live

- **Nguồn:** báo cáo 360° §7 bảng chỉ số
- **Bằng chứng tại HEAD:** Không đổi so với 2.0 (1 × 1 × macOS): không có lượt live trong 2.1.
- **Reproducer:** Chỉ số, không phải hành vi: không có reproducer.
- **Ảnh hưởng:** theo dõi
- **Quyết định:** blocked — Ngân sách (B-09); Linux: F.
- **Mức (REPORT §2):** Chỉ số: REPORT §2 không chấm mức cho chỉ số. Hạng mục liên quan: E2, F — mức của hạng mục đó không phải mức của chỉ số này.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: ≥ 2 × 2, có Linux
- **Còn thiếu:** Chưa đạt: vẫn 1 × 1 × macOS, không có Linux (mục tiêu ≥ 2 × 2, có Linux).

### R-M3

> Lỗi do review tìm thấy mà vẫn vào `main`

- **Nguồn:** báo cáo 360° §7 bảng chỉ số
- **Bằng chứng tại HEAD:** Đo offline trên dạng 5 lỗi smoke #2: 4 neo được ⇒ chặn, 1 UNANCHORED (P-V2-09). Chưa đo live.
- **Reproducer:** Chỉ số, không phải hành vi: không có reproducer.
- **Ảnh hưởng:** theo dõi
- **Quyết định:** blocked — Số đo live cần ngân sách (B-05, B-06, B-09). Fix-loop (C1) có; phép thử offline trên 5 dạng lỗi smoke #2 là regression, không phải số đo live của chỉ số.
- **Mức (REPORT §2):** Chỉ số: REPORT §2 không chấm mức cho chỉ số. Hạng mục liên quan: C1 — mức của hạng mục đó không phải mức của chỉ số này.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: đo và báo cạnh 59/59
- **Còn thiếu:** Chưa đo live, chưa báo cạnh 59/59. Offline: 1/5 dạng lỗi lịch sử (R-7/1) UNANCHORED nên vẫn lọt gate (P-V2-09).

### R-M4

> Mệnh đề requirement được contract phủ

- **Nguồn:** báo cáo 360° §7 bảng chỉ số
- **Bằng chứng tại HEAD:** `aisef bundle lint` báo độ phủ theo mệnh đề do tiêu chí khai; RUN.json không mang độ phủ (run.py ghi usage, no_progress).
- **Kiểm cơ học:** `docs/v2.1/evidence/cli-integration-b72e51e.out` chứa `"limit": "clauses are the ones the criteria's facts declare; AISEF does not parse the requirements …`; `docs/v2.1/evidence/cli-integration-c9c736f.out` (đi cùng bảng) chứa `"limit": "clauses are the ones the criteria's facts declare; AISEF does not parse the requirements …`
- **Reproducer:** Chỉ số, không phải hành vi: không có reproducer.
- **Ảnh hưởng:** theo dõi
- **Quyết định:** open — Độ phủ được báo ở `aisef bundle lint` (B5); báo trong RUN.json chưa làm và không có quyết định nào được ghi lại (STATUS, ADR-V2.1, REPORT không nhắc).
- **Mức (REPORT §2):** Chỉ số: REPORT §2 không chấm mức cho chỉ số. Hạng mục liên quan: B5 — mức của hạng mục đó không phải mức của chỉ số này.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: báo bằng máy trong `RUN.json`
- **Còn thiếu:** RUN.json chưa mang độ phủ: mục tiêu 2.1 chưa đạt (chỉ `aisef bundle lint` báo, trên mệnh đề do tiêu chí khai).

### R-M5

> Đọc ra ngoài workspace của developer

- **Nguồn:** báo cáo 360° §7 bảng chỉ số
- **Bằng chứng tại HEAD:** Không có ranh giới; `leaks` của harness chỉ quét chuỗi stimulus trong luồng phiên của thí nghiệm. Chưa đo.
- **Reproducer:** Chỉ số, không phải hành vi: không có reproducer.
- **Ảnh hưởng:** theo dõi
- **Quyết định:** blocked — Như P-V2-05.
- **Mức (REPORT §2):** Chỉ số: REPORT §2 không chấm mức cho chỉ số. Hạng mục liên quan: F — mức của hạng mục đó không phải mức của chỉ số này.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: 0 (hoặc được báo)
- **Còn thiếu:** Chưa đo; không có ranh giới hệ điều hành (F/B-07).

### R-M6

> USD / story giao được

- **Nguồn:** báo cáo 360° §7 bảng chỉ số
- **Bằng chứng tại HEAD:** Ledger tiền có (D2); chưa có lượt live để báo số.
- **Reproducer:** Chỉ số, không phải hành vi: không có reproducer.
- **Ảnh hưởng:** theo dõi
- **Quyết định:** blocked — Ngân sách (B-09).
- **Mức (REPORT §2):** Chỉ số: REPORT §2 không chấm mức cho chỉ số. Hạng mục liên quan: D2, E2 — mức của hạng mục đó không phải mức của chỉ số này.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: có
- **Còn thiếu:** Chưa có số: 0 lượt live để chia USD cho story giao được.

### R-M7

> Thời gian từ bản vá đến PyPI

- **Nguồn:** báo cáo 360° §7 bảng chỉ số
- **Bằng chứng tại HEAD:** Công cụ theo phiên bản (A9); chưa phát hành bản nào nên chưa đo.
- **Reproducer:** Chỉ số, không phải hành vi: không có reproducer.
- **Ảnh hưởng:** theo dõi
- **Quyết định:** blocked — B-02 (chủ dự án).
- **Mức (REPORT §2):** Chỉ số: REPORT §2 không chấm mức cho chỉ số. Hạng mục liên quan: A9 — mức của hạng mục đó không phải mức của chỉ số này.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: < 1 ngày, không sửa công cụ phát hành
- **Còn thiếu:** Chưa đo: chưa phát hành bản nào trong 2.1 (B-02).

### R-M8

> Người dùng ngoài

- **Nguồn:** báo cáo 360° §7 bảng chỉ số
- **Bằng chứng tại HEAD:** 0 (không thay đổi, theo những gì repo cho biết).
- **Reproducer:** Chỉ số, không phải hành vi: không có reproducer.
- **Ảnh hưởng:** theo dõi
- **Quyết định:** open — Ngoài phạm vi mã.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: ≥ 1 đối tác thiết kế
- **Còn thiếu:** Chưa đạt: 0 người dùng ngoài theo những gì repo cho biết (mục tiêu ≥ 1 đối tác thiết kế).

### R-M9

> Mục backlog có reproducer

- **Nguồn:** báo cáo 360° §7 bảng chỉ số
- **Bằng chứng tại HEAD:** STATUS §1–2 có cột reproducer (D4, E2: '—'); `docs/v2/V2.1-BACKLOG.md` (38 mục) không đổi trong 2.1.
- **Kiểm cơ học:** `docs/v2/V2.1-BACKLOG.md` không đổi so với `610a593`
- **Reproducer:** Chỉ số, không phải hành vi: không có reproducer.
- **Ảnh hưởng:** theo dõi
- **Quyết định:** open — Chưa đo lại trên backlog 38 mục.
- **Mức (REPORT §2):** REPORT §2 không có hạng mục riêng cho mục này.
- **Tiêu chí nghiệm thu:** Mục tiêu 2.1: tất cả mục ≥ medium
- **Còn thiếu:** Chưa đo lại: 38 mục của `docs/v2/V2.1-BACKLOG.md` chưa được đối chiếu với tiêu chí 'có reproducer'.
<!-- rows:end -->
