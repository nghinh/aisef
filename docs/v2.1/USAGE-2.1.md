# AISEF 2.1 — Hướng dẫn sử dụng và di trú từ 2.0.0

Áp dụng cho nhánh `v2.1/foundation` (`2.1.0.dev0`, **chưa phát hành**). Mọi lệnh dưới đây không gọi provider, trừ
`aisef run` không kèm `--check`/`--verify`.

Mục 8 và các ghi chú "cửa sổ probe" mô tả cây ứng viên `v2.1/probe-window` (2026-10-15 … 2026-10-17, từ `2d01fe4` tới
`3e1e83a`, hai đợt): *đã làm trên nhánh ứng viên, bằng chứng đo (hiệu chuẩn lại, mutation, suite đầy đủ) chưa có*. Đó
không phải bản phát hành và chủ dự án chưa nghiệm thu (REPORT §0.9). "Chỉ thị 2026-10-15, mục N" trong tài liệu này là chỉ thị
lần thứ tư của ngày ấy; văn bản nguyên văn của nó ở commit `8e6f583` của nhánh `v2.1/probe-window`, chưa nằm trong cây này (REPORT §0.9).

**Chưa sửa, và chặn mọi tuyên bố "hành trình người dùng đã đạt" hay "hỗ trợ Windows đã đạt"** (§7, REPORT §6.0): lệnh chi
phí/báo cáo của V1 (`aisef cost`, `aisef report`, `aisef status`) nhận thư mục run V2 và trả toàn số 0 với exit 0; hai điểm
CRLF trên Windows. Để đọc chi phí của một run V2 hãy đọc `RUN.json` (`usage.cost`), không chạy các lệnh V1.

## 1. Từ con số không đến một lượt chạy kiểm tra được (không cần API nội bộ)

```bash
aisef bundle init --example calc-1-story --out calc
```
Lệnh này viết `calc/authoring.json` và các tệp của repo mẫu vào `calc/repo/`. Biến `calc/repo` thành repo git và commit — commit đó là baseline:

```bash
git -C calc/repo init -q -b main
```
```bash
git -C calc/repo add -A
```
```bash
git -C calc/repo commit -q -m baseline
```
Niêm phong: mọi hash và spec id được tính bằng constructor của kernel; **chưa có approval nào**:
```bash
aisef bundle seal calc/authoring.json --repo calc/repo --out calc/bundle.json
```
Đọc từng tiêu chí trước khi duyệt:
```bash
aisef bundle explain calc/bundle.json
```
Người duyệt — một con người, đặt tên `human:<tên>` — duyệt **từng** contract:
```bash
aisef bundle approve calc/bundle.json --contract BC-ADD --approver human:alice --out calc/approved.json
```
Kiểm tra READY (approval, chín phép admission với hiệu chuẩn đi kèm bản phát hành, độ phủ theo yêu cầu/mệnh đề):
```bash
aisef bundle lint calc/approved.json
```
```bash
aisef run --check --project calc/approved.json --settings settings.json --repo calc/repo
```
Trạng thái của cây ứng viên (§8): cửa sổ probe đổi byte của bốn probe, nên các hàng hiệu chuẩn trong
`aisef2/app/calibrations.py` — ghi trước cửa sổ — không còn khớp byte đang chạy. Cho tới khi
`validation/qualification/release_calibration.py --write` được chạy một lần ở cuối cửa sổ, `aisef bundle lint` trên ví dụ
trên báo `NOT_READY` ở kiểm tra `9. probe_calibration` (`no ProbeCapabilityCalibration for
probe.python_callable_v2@0821c14651a9 executing 042fe41e8e68 class 'returns'`; đo trên `3e1e83a`).

Ví dụ 3 story (hai loại probe, hai obligation PRESERVE): `--example calc-3-stories`. Định dạng soạn:
[`bundle-authoring.schema.json`](bundle-authoring.schema.json). Mọi lệnh `aisef bundle` viết **tệp mới**, không bao giờ
ghi đè; mã thoát 0 xong / 1 lint NOT_READY / 2 từ chối.

## 2. Di trú bundle 2.0.0

Spec id đổi một lần (ba danh tính, [ADR-2](ADR-V2.1.md)). Bundle 2.0.0 nạp vào 2.1 bị từ chối với gợi ý:
```bash
aisef bundle migrate old-2.0.0-bundle.json --out candidate.json > candidate.report.json
```
`migrate` **không sửa** `old-2.0.0-bundle.json` và **không ký gì**. Nó ghi một bundle **ứng viên mới** (tệp `--out` phải
chưa tồn tại): `plan` được buộc lại theo contract đã duyệt của chính nó; requirement, contract và facts không đổi. Nó không
còn giữ một approval chỉ vì `contract_hash` không đổi (chỉ thị 2026-10-15, mục 1): ứng viên chỉ mang theo approval nào
(a) vẫn buộc đúng `requirement_hash` và `contract_hash`, và (b) mà contract của nó vẫn được đánh giá như lúc được duyệt,
theo quy tắc danh tính V2-007. Với từng contract, `migrate` đọc những thay đổi capability mà probe tự khai báo cho các
`CAPABILITY_VERSION` nằm giữa bản phát hành của bundle (`bundle_cli.RELEASES`) và bản này (`CAPABILITY_CHANGES` trong
module probe). Một thay đổi **chọn trúng** contract — theo lớp quan sát và `subject_absence`, không tên contract nào được
viết cứng — thì approval của contract đó bị giữ lại khỏi ứng viên; nó vẫn nằm nguyên trong bundle gốc, làm lịch sử. Một
`CAPABILITY_VERSION` được nâng mà không có bản khai báo đúng dạng cho nó là **đóng** (fail-closed): nó chọn mọi contract
của probe đó (cũng vậy khi probe không khai báo phiên bản, hoặc không phải probe mà bản phát hành đã dùng). Điều này
**không** phủ một thay đổi hành vi mà không nâng phiên bản: nó không bị thấy (D-2, bên dưới). Một obligation mà không bản phát
hành nào biết đến bị từ chối, không đoán.

Báo cáo (JSON ra stdout; lưu bằng `>`):

| khoá | nội dung |
|---|---|
| `semantic_changes` | mỗi contract bị chọn: lớp, từ/đến phiên bản capability, `ref` (`PM-9`, `PM-11`), điều kiện của repo làm verdict khác (`when`), verdict trước/sau, các approval cũ của nó |
| `needs_owner_reapproval` | mỗi contract một lệnh `aisef bundle approve … --approver human:NAME --out …`, nối tiếp (lệnh sau đọc tệp lệnh trước ghi), với đường dẫn thật; `then` là `aisef bundle lint` cho tệp cuối. Chỉ còn `human:NAME` để người sở hữu thay bằng `human:` và tên mình: `approve` từ chối nguyên chuỗi `human:NAME` (không ghi tệp, mã thoát 2), nên dán nguyên văn không ký gì |
| `candidate` | `bundle_digest` = sha256 JSON chuẩn tắc mà `load` gán cho project; `file_sha256` = sha256 byte của tệp vừa ghi; `plan_hash`, `approvals_kept`, `contracts_to_approve`, `loads` |
| `approvals_kept_grounds` | căn cứ giữ từng nhóm approval: probe, lớp, `subject_absence`, các phiên bản capability đã đọc |
| `approvals_withheld` | approval nào bị giữ lại, ai duyệt, lúc nào |
| `limits` | điều quy tắc **không** thấy (dưới đây) |

Mã thoát 0 nghĩa là di trú đã xong. Nếu có contract bị chọn, ứng viên **chưa nạp được** (`candidate.loads: false`) và
`aisef bundle lint candidate.json` báo `NOT_READY` (mã 1) cho tới khi người sở hữu duyệt lại đúng các contract đó. Công cụ
không bao giờ tự ký hay chuyển approval.

`aisef bundle seal … --keep-approvals-from OLD` áp cùng quy tắc: approval bị giữ lại vì thay đổi capability được nêu trong
`approvals_withheld_semantic` và contract của nó nằm trong `to_approve`. Gọi `seal()` từ mã với `approvals` thì phải
truyền cả `exposed` (`bundle_cli.exposure_of` của bundle gốc), nếu không nó bị từ chối.

**Bundle LedgerLock 2.0.0 của kho** (`closure-evidence/v2/release/LEDGERLOCK-PROJECT.json`; đo lại trên `3e1e83a`, đầu ra
vào thư mục ngoài repo, đầu vào không đổi): `migrate` thoát 0, giữ **53 trong 59** approval và giữ lại **sáu** contract —
`BC-V22-S-10-a`, `S-10-b`, `S-10-c`, `S-12-a`, `S-12-b`, `S-12-c`; `lint` ứng viên báo `NOT_READY` với đúng sáu contract
trong `to_approve` (`candidate.bundle_digest` `1010f0da…7417`, `file_sha256` `a21fa2c7…5f03`).
- **Sáu, không phải bốn.** Chủ dự án đã nêu bốn (`S-10-a`, `S-12-a`, `S-12-b`, `S-12-c`). Cả sáu là `grep_count` với
  `REQUIRES_SUBJECT`, và bộ chọn chỉ thấy lớp quan sát cùng `subject_absence`, không thấy repo hay đường dẫn: PM-9 (một lựa
  chọn không có tệp nào là chủ thể vắng) một mình đã chọn đủ sáu. PM-11 (một BOM UTF-8 không còn là ký tự của dòng 1; v2.0.0
  giải mã `utf-8`, nay `utf-8-sig`) cũng đổi verdict của `grep_count` và cũng chọn đủ sáu, nên hai contract thêm (`S-10-b`,
  `S-10-c`) không loại trừ được nếu `migrate` không đọc repo. Đó là phía an toàn. **Chấp nhận sáu hay không là quyết định
  D-1 của chủ dự án** (REPORT §7, backlog V21-75): tài liệu này không quyết.
- **50 trong 53 approval được giữ chỉ dựa vào luật phiên bản (D-2).** Ba probe `cli_invocation`, `process_effect`,
  `python_callable_v2` đã đổi hành vi kể từ 2.0.0 (PM-1, PM-2, PM-6, cờ `-S`, họ RV-1) mà `CAPABILITY_VERSION` vẫn là 1,
  nên `migrate` không thể thấy các thay đổi ấy: contract của chúng được giữ (cli 10, process_effect 34, python_callable_v2
  6; `file_artifact` 3). Lane `migrate-semantics` đo cùng một repo đồ chơi qua probe của tag `v2.0.0` rồi qua `d1460fd`: (1)
  `cli_invocation`, chủ thể gọi `exit(3)` (của module `site`): `SATISFIED` → `REFUTED`; (2) `cli_invocation` và `python_callable_v2`, chủ thể
  import một gói trong site-packages: `SATISFIED` → `REFUTED` (do `-S`); (3) `cli_invocation`, module dưới namespace
  package: `UNRUNNABLE` → `SATISFIED`; (4) `process_effect`, `fault` rồi `subprocess`: `SATISFIED` → `INVALID_SPEC`
  (đầu ra không được commit). Tham chiếu LedgerLock của kho (`tests/v2/fixtures/workloads/ledgerlock-reference`) chỉ dùng
  stdlib, không gọi `exit()` và là package thường nên không dính (1)–(3); nhưng đó là fixture, không phải mọi bản cài đặt
  của contract. Tăng `CAPABILITY_VERSION` (đổi spec id, phải làm lại hiệu chuẩn) hay chấp nhận giới hạn là **quyết định D-2
  của chủ dự án** (backlog V21-76).
- **PM-9 không được cửa sổ di trú.** 59 approval `human:owner` ở `closure-evidence/v2/cycle2/P5-CONTRACT-APPROVALS.json`
  (2026-09-30) không bị cửa sổ sửa hay thu hồi; duyệt lại các contract bị giữ lại là việc của chủ dự án.

`migrate` đọc khai báo và **không chạy probe**: một thay đổi hành vi của probe mà không tăng `CAPABILITY_VERSION` và không
khai báo thì không bị thấy, và contract của nó được giữ. Bộ chọn chọn mọi contract *có thể* gặp điều kiện (một lựa chọn
rỗng, một BOM), dù repo của bạn có gặp hay không; mỗi lần chọn kèm điều kiện `when` để người sở hữu tự đối chiếu với repo
thật. Một bundle mà một bản `migrate` cũ đã ghi ra đã mang spec id của bản này và được đọc như đã duyệt dưới bản này: hãy di
trú lại từ bản gốc (bản gốc không bao giờ bị sửa).

Cửa sổ probe nâng `CAPABILITY_VERSION` của `file_artifact` từ 2 lên 3 (PM-9, §8.1): spec id của mọi spec `file_artifact`
đổi thêm một lần. `migrate` chỉ biết bản 2.0.0 (`bundle_cli.RELEASES`): bundle 2.0.0 vẫn được buộc lại. Một bundle có spec
`file_artifact` niêm phong bằng một checkout ứng viên *trước* cửa sổ nêu spec id mà không bản phát hành nào biết: `lint`
báo kiểm tra `load` (`the plan names 1 spec(s) no approved contract compiles to under this release's probes: […] — a
bundle of an earlier release: `aisef bundle migrate``) và chính `migrate` từ chối (`refused: 1 obligation(s) name a spec no
known release (2.0.0 or this one) compiles from the bundle's approved contracts: ['C-STDLIB-1']`) — đo lại trên `3e1e83a`
với `calc-3-stories` niêm phong ở `2d01fe4`. Lối ra: niêm phong lại từ tệp soạn bằng `aisef bundle seal … --keep-approvals-from OLD`.
**Giới hạn đã đo, không do quy tắc ở trên giải quyết:** trên đúng bundle ấy lệnh `seal … --keep-approvals-from` ghi
`approvals_kept: 4`, `approvals_dropped: []`, `approvals_withheld_semantic: []` — kể cả approval của `BC-STDLIB`
(`python_imports`, `REQUIRES_SUBJECT`), contract mà PM-9 chọn. Lý do: `RELEASES` chỉ có 2.0.0 nên spec id của `BC-STDLIB`
không bản phát hành nào biết; nó lấy nguồn gốc của phần còn lại của kế hoạch (`current`) và không thay đổi capability nào
được tra cho nó (`exposure_of` trả `{}`). Với một bundle của checkout ứng viên trước cửa sổ, duyệt lại `BC-STDLIB` (nếu
nó dùng) là việc của chủ dự án (backlog V21-61).

## 3. Settings: khoá tuỳ chọn mới (vắng = đúng hành vi 2.0.0)

```json
"review": {"policy": "fix-loop", "min_severity": "high",
           "finder": "ocr", "ocr": {"exe": "/abs/path/ocr", "sha256": "<sha256 của binary>", "timeout_min": 20,
                                    "max_tokens": 8000}},
"prices": {"currency": "USD", "input_per_mtok": 1.32, "cache_read_per_mtok": 0.044, "cache_write_per_mtok": 1.32,
           "output_per_mtok": 3.96, "source": "<trang giá>", "effective_date": "YYYY-MM-DD"}
```
- `review` vắng ⇒ review advisory như 2.0.0. `fix-loop` ⇒ một finding chỉ chặn story khi đủ **cả ba**: có
  **reproducer** mà probe của AISEF tái hiện ở candidate (CONFIRMED); kỳ vọng của nó **được neo** vào contract đã duyệt
  của mệnh đề nó trích (ANCHORED — xem ADR-7); mức ≥ `min_severity`. Khi đó: REVIEW_FINDING, retry trong giới hạn
  REVIEW, nội dung được đưa cho developer ở lượt sau. Mọi finding khác (không tái hiện, không quyết được, không chạy
  được, không neo được, mâu thuẫn với contract đã duyệt) chỉ được ghi lại để người phân loại.
- Trạng thái kiểm chứng của một finding (`verification.status`, §8.3) là một trong `CONFIRMED`, `NOT_REPRODUCED`,
  `INDETERMINATE`, `UNVERIFIABLE`. `NOT_REPRODUCED` chỉ dành cho một probe đã chạy và thấy đúng hành vi được nêu
  (`SATISFIED`). Một probe đã chạy mà không quyết được là `INDETERMINATE`; một kiểm tra không chạy được hay không quyết
  được vì giới hạn của công cụ (probe `UNRUNNABLE`, spec không có nghĩa, một regex không kết thúc trong hạn) là
  `UNVERIFIABLE`. Hai trạng thái ấy không chặn và không bao giờ là bằng chứng rằng finding không tái hiện.
- Reproducer trích mệnh đề theo dạng `<requirement>/<clause>` như danh sách mệnh đề (ví dụ `R-9/3`, `R-ADD/1.1`).
- `finder` vắng hoặc `"model"` ⇒ reviewer là phiên mô hình như 2.0.0. `"ocr"` ⇒ Open Code Review v1.12.12 (binary
  theo đường dẫn tuyệt đối; **trước mọi lệnh review** AISEF kiểm sha256 rồi hỏi chính binary `version`, §8.3): preview rồi
  review đúng thay đổi của story; coverage do AISEF kiểm. Review không phủ hết candidate (partial, hết thời gian, hết
  token budget của nó, schema manifest không hỗ trợ) ⇒ dưới `fix-loop` story không được commit (CAPABILITY_UNRUNNABLE;
  lỗi provider ⇒ PROVIDER_UNAVAILABLE); dưới `advisory` chỉ ghi lại. Một lượt OCR bị dừng vì hết giờ có chi phí không xác định ⇒ ngân sách "unaccounted", run
  không mở thêm phiên trả tiền nào.
- Với `finder: "ocr"` (dưới `fix-loop` cũng như `advisory`: binary hỏng lúc dùng kết thúc mọi story), `aisef run` hỏi
  binary **sớm nhất có thể**: sau ba việc nhỏ — từ chối nếu `--out` đã có, từ chối nếu `--parent` không có bản ghi (`no
  run record there`), tạo `--out` và ghi `RUN.started.json` — và **trước** claim của `--parent`, clone, admission,
  preflight, mở phiên developer hay gửi request provider. Ba điều phải đúng, theo thứ tự: `review.ocr.exe` là đường dẫn tuyệt đối đọc được; sha256 của nó bằng
  `review.ocr.sha256`; `<exe> version` (môi trường sạch, có giới hạn thời gian) in dòng phiên bản của Open Code Review
  v1.12.12 (182898c). Sai ⇒ từ chối trước khi chạy: mã thoát 2, không phiên nào được mở, không request nào được gửi;
  thông báo nêu check nào hỏng, giá trị mong đợi, giá trị quan sát và việc operator cần làm. Thư mục `--out` của lượt bị
  từ chối được giữ làm bản ghi và không bao giờ dùng lại ⇒ lượt kế tiếp cần `--out` mới. Hai lối ra: sửa pin (chỉ sau khi
  kiểm binary với [BUILD-RECIPE.md](../../validation/v21/ocr/BUILD-RECIPE.md)), hoặc bỏ `review.ocr` và đặt
  `finder: "model"` — một reviewer khác.
- `aisef run --check` hỏi binary theo cùng cách, in khối `ocr_identity` và `ready: false` (mã thoát 2) nếu binary không
  qua. `RUN.json` của một lượt có `finder: "ocr"` có khối `ocr_identity` nói đã thiết lập được gì:
  `sha256_matches_pin` (byte là pin của operator), `declared_matches_release` (binary **tự khai** đúng bản — lời
  tự khai, không phải bằng chứng dựng) và `build_provenance`, luôn là `NOT_ESTABLISHED` (một lượt chạy không dựng lại
  binary; mức dựng lại là một phép đo ngoài của một người, §8.3, và không bao giờ do `aisef run` thiết lập). Cả lượt qua
  (`status: PASSED`) lẫn lượt bị từ chối (`status: REFUSED`, thêm `check`, `reason`, `operator`) đều ghi khối này; lượt bị
  từ chối có `failure.stage` `ocr identity`, `delivery_verdict` `NOT_REACHED`. Đây là lần nhìn sớm, **không thay** cổng
  lúc dùng: giai đoạn review kiểm lại cả hai ngay trước mỗi lần review, nên một binary bị thay giữa chừng bị từ chối ở đó.
- Checkout được review không được đổi trong lúc review (cả với finder mô hình): đổi tệp hay commit ⇒ mọi finding bị bỏ,
  CAPABILITY_UNRUNNABLE.
- `prices` vắng ⇒ `usage.cost.value = null`, `status: unknown` — không bao giờ 0.

## 4. Sau một lượt chạy

- Lượt chạy in `evidence_anchor` (và ghi vào tệp mới với `--anchor-out FILE`); **giữ nó nơi developer không ghi được**
  — ngoài thư mục run thôi là chưa đủ khi developer chạy cùng user ([ANCHOR-THREAT-MODEL.md](ANCHOR-THREAT-MODEL.md)). Kiểm:
```bash
aisef run --verify --project bundle.json --out run1 --expect-anchor <anchor>
```
- `RUN.json` có thêm `usage` (token theo lớp, request, retry, thời gian, tiền nếu có giá) và `no_progress` (retry lặp lại
  đúng các lỗi cũ — chỉ báo cáo).
- Một run có `--parent` còn có `continues.account` (`provider_requests`, `turns`, `input_tokens`, `output_tokens` của các
  phần dòng dõi **đọc được**; `unaccounted`; `unread`; `total`; `runs`, mỗi run một hàng có `exact`) và `lineage_usage`
  (`runs[]` có chi phí từng run, `tokens`, `tokens_status`, `cost`). `total` và `lineage_usage.cost.value` là `null` khi còn
  một phần chưa biết: bốn bộ đếm khi đó là cận dưới (`tokens_status` bắt đầu bằng `lower bound`), không phải tổng. Một run
  có `exact: false` hiện bộ đếm là số đã biết (có thể 0) kèm `exact: false`, không phải `null`: đọc `exact` hay `total`,
  đừng chỉ đọc một bộ đếm.
- Thư mục: `<out>/test-python` (venv cho test của developer; probe **không** chạy trên nó), `<out>/EVIDENCE.json`,
  `<out>/review-findings/` (mỗi finding của reviewer, đầy đủ và đã che bí mật của run; dòng journal chỉ giữ bản tóm tắt
  ≤ 1.500 ký tự, nêu đường dẫn, sha256 và kích thước của tệp; `--verify` đối chiếu).
- `<out>/probe-observations/` (PM-8): điều probe thấy mà bản ghi probe niêm phong không giữ — **chỉ cho người vận hành**,
  không thẩm quyền quyết định; nằm trong manifest bằng chứng và được `--verify` đối chiếu với journal (§8.4).

## 5. Lượt chạy dừng giữa chừng: nối tiếp, không chạy lại từ đầu

```bash
aisef bundle continue bundle.json --from-run run1 --out continued.json
```
```bash
aisef run --project continued.json --repo run1/repo --parent run1 --settings settings.json --out run2
```
Baseline mới = commit cuối mà journal của `run1` xác nhận; các story đã giao thành story `CARRIED` (VERIFY) được kernel
chứng minh lại mà không gọi developer. Bundle/kernel khác ⇒ từ chối (đó là dự án mới, không phải nối tiếp).

Bảo đảm — mỗi cửa sổ được đo bằng SIGKILL thật tại một điểm đồng bộ xác định (hàm được bọc, bước của client giả), không
kill ngẫu nhiên (`test_v21_continue_integrity`):

- **Journal, nói đúng.** Mỗi sự kiện là một `write` rồi một `fsync`. `write` trả về ⇒ lần ghi *hoàn tất* (tiến trình khác
  thấy; tiến trình ghi bị giết không làm mất nó — đã đo: kill sau `write`, trước `fsync` ⇒ sự kiện còn). `fsync` trả về ⇒
  *bền* trước mất điện/OS sập (không test nào ở đây mô phỏng điều đó). **Không** có tính *nguyên tử*: một lần ghi có thể
  ngắn (mất điện, OS sập, hoặc tín hiệu chết người đến giữa một lần ghi nhiều trang) và writer chết trước khi cắt lại thì
  để lại dòng cuối bị cắt — đã đo bằng một lần ghi nửa dòng. Reader trả phần đầu đã kiểm chuỗi hash cùng `torn_tail`;
  báo cáo `continue` ghi `cut_event` (seq, số byte; nửa đầu một sự kiện chuẩn hoá thường **không** còn type lẫn story).
- **Tác dụng bên ngoài không bao giờ bị coi là chưa xảy ra.** Một sự kiện ghi lại một tác dụng đã xảy ra (git đã dời
  main; request đã tới provider). Thiếu hay cắt sự kiện ⇒ thiếu *bản ghi*, không phải thiếu *tác dụng*. `continue` đối
  soát mọi thứ journal không xác nhận (`unconfirmed`) với git và với danh tính thao tác trong journal: merge của kernel cho
  candidate đã được chứng minh (nhận ra qua cha thứ hai và thông điệp `merge <sha>`), candidate của developer trong
  worktree `wt-<story>` của kernel. Mỗi mục được nêu danh tính; story của nó chạy lại từ baseline đã xác nhận, nên tác
  dụng không lặp trên main của dòng dõi. Commit trên main mà không gì nhận ra ⇒ **từ chối**, trừ khi người vận hành nêu
  `--leave-out-unidentified` (ghi vào báo cáo).
- **Request chưa đối soát.** `provider/request` không có `provider/result`: client chưa từng chạy (không có luồng phiên)
  ⇒ không gửi gì, chi phí 0 đã biết; luồng phiên tồn tại (request đã gửi, usage chưa có hoặc result chưa ghi) ⇒ chi phí
  **unknown**. Chi phí không biết có **hai loại**, và `aisef run --parent` xử lý khác nhau:
  1. *Bằng chứng đọc được và nói rằng có thứ đã gửi mà chưa trả lời* (một request đang bay khi run bị giết; một request
     preflight không có câu trả lời): `aisef run --parent` không mở phiên trả tiền nào (từ chối trước preflight, `the
     lineage of … has spend no evidence accounts for`) trừ khi người vận hành nêu `--accept-unaccounted` — danh sách được
     ghi vào `continues.accepted_unaccounted`; tổng chi phí dòng dõi khi đó là `null`.
  2. *Bằng chứng có mặt mà không đọc được* (`unread`). Theo từng đối tượng (đo bằng `lineage.account_of` trên cây này):
     **journal** — quyền, một liên kết trỏ vào hư không hay lặp, một tệp đứng chỗ thư mục hay một thư mục đứng chỗ tệp,
     không phải văn bản, không dựng lại được; **ledger preflight** — quyền, không phải văn bản, không parse được, một thư mục đứng
     chỗ tệp; **luồng phiên** — quyền (của luồng hay của thư mục `sessions/`), một liên kết trỏ vào hư không, một thư mục
     đứng chỗ tệp. Một luồng *không phải văn bản* thì khác: nó chỉ thêm một dòng `unaccounted` (`a session that started
     finished no step`) mà `--accept-unaccounted` phủ được, không phải `unread`. Bằng chứng *thiếu hay sai hình dạng* cạnh một journal đọc được (`sessions/` là một tệp,
     một liên kết hỏng hay lặp; ledger là một liên kết hỏng hay lặp) **không** nằm trong danh sách này — quy tắc cho nó là
     R2, **[ĐANG HOÀN THIỆN]**, §8.5. Cũng là `unread`: một journal
     đọc được nhưng **không phải journal mà `RUN.json` của run nêu** (digest và số dòng: rỗng, cắt ở một dòng hay giữa
     dòng, bị thay); một record hay claim không đọc được, hỏng, không phải object hay là liên kết hỏng (nên không biết
     nó nêu run nào); một run tổ tiên mà record nêu nhưng thư mục đã mất (mất, là tệp, hay liên kết hỏng). Đây là chi phí
     unknown mà **không cờ nào chấp nhận**: `aisef run --parent` thoát 2 (`refused:`) **trước clone, admission và
     preflight, dù nêu `--accept-unaccounted`, `--supersede-claim` hay cả hai**; không phiên nào được mở, không request nào
     được gửi. Thông báo nêu thư mục run cần khôi phục (quyền của nó, hay một bản sao trung thành) và rằng nếu không khôi
     phục được thì dòng dõi không nối tiếp được (`aisef run` không `--parent` là một run mới, không kế thừa gì, trần riêng).
     Run đó vẫn không bị "đoán 0": phần đã biết của mỗi run còn nguyên và quy được về run đó.

  Chi tiêu đã biết của dòng dõi tính vào trần ngân sách của run mới (nối tiếp không bao giờ đặt lại ngân sách: muốn chạy
  tiếp một run đã chạm trần thì nâng trần trong settings — một quyết định tường minh). `aisef bundle continue` tính cả dòng
  dõi (không chỉ run được nối) và báo `spend` (`known`, `total`), `spend_by_run`, `unaccounted`, `unread` và
  `run_parent_refused`; khi có `unread`, `next` bảo khôi phục bằng chứng trước thay vì đưa một lệnh sẽ bị từ chối.
  `aisef run --verify` trên một run kế thừa mà bằng chứng của dòng dõi nay không đọc được ra `REFUTED` với lý do `the
  lineage's evidence cannot be read now, so the spend the record inherited cannot be re-derived`.
- **Một run được nối tiếp một lần — quyết định bằng bằng chứng.** `--parent` tạo độc quyền `CONTINUED-BY.json` *trước*
  request provider đầu tiên (run thua cuộc đua không tiêu gì — đã đo). Tạo độc quyền chỉ chứng minh một tiến trình thắng
  lúc tạo, nên một claim có sẵn được đối soát: child đã bắt đầu (journal có sự kiện) ⇒ từ chối, nối tiếp từ child, không
  bao giờ thay thế kể cả khi người vận hành yêu cầu; child kết thúc mà chưa bắt đầu, hoặc chưa bắt đầu và claimant chắc
  chắn đã mất (cùng máy, pid không còn hoặc là tiến trình khác theo thời điểm khởi động) ⇒ một thế hệ claim mới
  (`CONTINUED-BY.<n>.json`) thay thế, ghi bằng chứng; claimant còn sống, ở máy khác, hoặc không đọc được ⇒ từ chối, chỉ
  thay thế khi người vận hành nêu sha256 của claim (`--supersede-claim`, ghi là khẳng định của họ). Không xoá gì. Khẳng
  định `--supersede-claim` thay được *claim* nhưng **không làm biết** chi tiêu của một child mà bằng chứng không đọc được:
  run vẫn bị từ chối (bullet trên) cho tới khi bằng chứng ấy đọc lại được; một dòng dõi có bằng chứng không khôi phục được
  thì không nối tiếp được. Một lượt bị từ chối sau khi lấy claim để lại bản ghi riêng của nó và một thế hệ claim trên
  tiền nhiệm (nối thêm, không sửa tệp nào có sẵn); lượt sau thay thế nó bằng bằng chứng (thứ tự claim rồi mới tới cổng:
  R5, §8.5). **"Child đã bắt đầu" chỉ khi bằng chứng của nó đọc được.** Cửa sổ probe
  thêm trạng thái thứ tư `UNREAD`: bằng chứng của child *có mà không đọc được* — thư mục run không tìm kiếm được, journal
  không mở được, không phải văn bản, không dựng lại được, có byte mà không có sự kiện trọn vẹn nào; một liên kết trỏ vào hư
  không hay một tệp đứng chỗ thư mục; `RUN.json` nêu một journal có sự kiện mà journal vắng hoặc rỗng; `RUN.json` có mà
  không đọc được — **không phải** chưa bắt đầu: không bằng chứng nào thay thế nó, kể cả việc claimant đã mất; chỉ thay khi
  người vận hành nêu sha256 của claim (ghi cùng nguyên nhân). `ENDED_UNBEGUN` chỉ khi chính `RUN.json` (đọc được, là
  object) nói run kết thúc trước khi bắt đầu: không nêu journal hoặc nêu journal 0 dòng. Một lần đọc hỏng không bao giờ giải
  phóng hay lấy một claim. (Trên cây trước cửa sổ, ba biến thể bằng chứng không đọc được — thư mục mode 000, tệp journal
  mode 000, một byte hỏng giữa journal — đều bị coi là `UNBEGUN` và bị thay thế; đo ở `becf3c0`.)
- **Run bị giết vẫn nối được.** `RUN.started.json` được ghi (fsync) một lần trước mọi việc; thiếu `RUN.json`, hoặc
  `RUN.json` bị cắt (không phải JSON), thì `continue` đọc nó, báo `recorded: false`. Một `RUN.json` có mà không đọc được
  (quyền, I/O) bị từ chối `EVIDENCE_UNREADABLE`, không bị hạ xuống bản ghi yếu hơn; một `RUN.json` hay `RUN.started.json`
  không phải văn bản UTF-8 hoặc không phải object JSON là hỏng (`EVIDENCE_MALFORMED`: kernel viết ASCII, một lần kill chỉ
  cắt chứ không làm sai byte).
- **Không commit/merge lặp, không mất nghĩa vụ, chi phí mỗi run một lần.** Sau mỗi cửa sổ: mỗi story commit đúng một lần
  trong dòng dõi, số merge trên main cuối = số story đã giao, mọi nghĩa vụ được giao hoặc chứng minh lại, `lineage_usage`
  = mọi luồng phiên của dòng dõi đúng một lần (kể cả run bị thay thế), `usage` = chỉ của chính run.
- **Tiến trình của run bị giết** (đo cho đúng trường hợp đã đo): các tiến trình probe được nhận diện theo process group
  (và pid của chính candidate) — tất cả mất ngay sau kill: watchdog của range anchor giết cả nhóm khi controller mất. Một
  hậu duệ **tự tách nhóm** (`setsid`) **không** bị kiểm soát: nó sống quá run bị giết (đã đo); trong một run bình thường nó
  bị phát hiện là "escaped" (tests/v2/p4/test_process_range). Không có cách ly OS thì AISEF không tuyên bố kiểm soát nó.
- **`bundle continue` hợp lệ đúng như `--verify` (cùng hàm).** Trước cửa sổ chỉ cần journal dựng lại được chuỗi hash;
  nay: (1) journal đọc được; (2) là journal mà `RUN.json` nêu (sha256 và số dòng; bỏ qua khi run bị kill chưa có
  `RUN.json`); (3) dựng lại được (từng sự kiện, chuỗi hash, chuỗi seq); (4) không vi phạm projection mà writer của kernel áp
  (ví dụ một story commit hai lần: trên cây trước cửa sổ, `bundle continue` trả một continuation `carried [S1, S1]` còn
  `--verify` từ chối cùng thư mục; đo ở `becf3c0`). Dòng cuối bị cắt (`torn_tail`) vẫn là ngoại lệ được duyệt: lấy tiền tố
  đã kiểm chuỗi, báo `cut_event`, đối soát tác dụng với git. Mỗi cách hỏng có một mã, in ở stderr dạng
  `refused: <MÃ>: …`, mã thoát 2, không ghi tệp nào và không sửa run:

  | mã | nghĩa | việc cần làm |
  |---|---|---|
  | `EVIDENCE_UNREADABLE` | một tệp của run có hoặc được nêu tên mà không đọc được, hoặc không tìm kiếm/liệt kê được thư mục run | khôi phục quyền đọc, hoặc một bản sao trung thành của thư mục run |
  | `EVIDENCE_MALFORMED` | đọc được mà không phải thứ một run viết (không phải văn bản, một dòng, một format, một bản ghi) | khôi phục từ bản sao trung thành, hoặc chạy lại chính bundle |
  | `EVIDENCE_INTEGRITY` | journal không phải cái đã viết (chuỗi hash, seq, digest hay độ dài `RUN.json` nêu) | khôi phục; `--verify` từ chối giống hệt |
  | `EVIDENCE_PROJECTION` | chuỗi hợp lệ nhưng writer của kernel sẽ từ chối | không kernel nào viết ra nó; không mang gì từ nó |
  | `EVIDENCE_MISSING` | không có gì để nối tiếp hay xác thực: không có bản ghi run, bản ghi không nêu journal, journal không commit story nào, hoặc nêu `--expect-anchor` mà run không có `EVIDENCE.json` | chạy lại chính bundle (hoặc bỏ `--expect-anchor`) |
  | `EVIDENCE_MISMATCH` | `--expect-anchor`, hoặc manifest, không khớp thư mục run | không phải run đã in anchor đó, hoặc bằng chứng bị sửa sau khi ghi |

  (Một lượt bị từ chối trước khi có journal — `RUN.json` không nêu journal — trên cây trước cửa sổ in `the journal does not
  reconstruct (TypeError: 'NoneType' object is not subscriptable)`; nay là `EVIDENCE_MISSING`.)
- **`--expect-anchor A`** (`aisef bundle continue … --expect-anchor A`): anchor lượt chạy đã in, giữ ngoài thư mục run —
  được kiểm **trước** khi đọc `RUN.json`, journal và manifest của run (sau khi liệt kê các claim `CONTINUED-BY*.json` của nó
  và đọc bằng chứng của child: một từ chối của lần đọc ấy, hoặc một child đã `BEGUN`, được báo trước khi anchor được so);
  báo cáo ghi `anchor_checked`. Không có nó, continuation chỉ chứng minh nhất
  quán, không phải xác thực (`anchor_checked: false`: thư mục run ghi được bởi chính user của người vận hành,
  [ANCHOR-THREAT-MODEL.md](ANCHOR-THREAT-MODEL.md)). Mặc định cũng **không** đối chiếu `EVIDENCE.json` với thư mục dù nó có
  đó (`--verify` thì có): chỉ `--expect-anchor` là đường xác thực (backlog V21-54).
- **Đọc hỏng không giải phóng và không lấy một claim.** `aisef run --parent DIR` mà DIR không tìm kiếm/liệt kê được, hoặc
  chỉ-đọc và không tạo được claim: từ chối (`refused:`, mã thoát 2) kèm cách khôi phục, không phải traceback (đo ở
  `becf3c0`: `PermissionError`, mã thoát 1); không bao giờ "không có claim". Không nối tiếp từ một *bản sao* của run: bản sao
  có claim của riêng nó và run có thể bị nối tiếp hai lần.

Khác với resume tại chỗ: không có gì của `run1` được chạy tiếp hay ghi thêm vào journal của nó; `run2` là một lượt chạy
mới, journal mới, bắt đầu từ commit cuối đã xác nhận — công việc đang dở trong `run1` (một phiên, một merge chưa commit)
được làm lại từ đầu, và chi phí của nó vẫn được tính trong dòng dõi.

## 6. Thay đổi có thể làm hỏng quy trình cũ

| Thay đổi | Ảnh hưởng | Việc cần làm |
|---|---|---|
| spec id (ba danh tính) | bundle 2.0.0 bị từ chối | `aisef bundle migrate`: ghi một ứng viên mới, không ký gì; rồi duyệt lại các contract nó giữ lại (§2) |
| `<out>/probe-python` → `<out>/test-python` | script đọc đường dẫn cũ | đổi tên; probe chạy trên interpreter của aisef |
| `--check` clone repo như lượt chạy thật | một khoá git không "inert" trong repo của bạn không còn làm `--check` báo sai lý do | không |
| endpoint `http://` chỉ cho loopback (phân tích host thật) | `http://localhost.evil.example` bị từ chối | dùng https |
| preflight không theo redirect | endpoint trả 3xx ⇒ OPAQUE | dùng URL cuối cùng |
| phiên bản `2.1.0.dev0` | gate phát hành từ chối mọi bản dev | đúng chủ ý |
| `file_artifact` `CAPABILITY_VERSION` 2 → 3 (PM-9) | spec id của mọi spec `file_artifact` đổi; bundle niêm phong trước cửa sổ bị từ chối khi nạp | `seal --keep-approvals-from`; bundle 2.0.0: `migrate` (approval của contract mà một thay đổi capability đã khai báo chọn trúng bị giữ lại, §2) |
| lựa chọn không có tệp nào là chủ thể vắng (PM-9) | `grep_count`/`python_imports` `REQUIRES_SUBJECT` trên thư mục không còn tệp được chọn: trước `SATISFIED` (hoặc `REFUTED`), nay `INDETERMINATE(PRECONDITION_ABSENT)` | đọc §8.1, §8.7; chủ dự án quyết duyệt lại |
| `bundle continue` nghiêm hơn | journal mà `--verify` từ chối nay bị từ chối ở `continue`; `RUN.json` không đọc được không còn bị hạ xuống `RUN.started.json` | đọc mã `EVIDENCE_*` (§5) |
| claim: bằng chứng của child không đọc được | trước bị coi chưa bắt đầu và bị thay thế; nay `UNREAD`, chỉ thay bằng sha256 do người vận hành nêu | không (đường thoát `--supersede-claim` còn) |
| `migrate` và `seal --keep-approvals-from` không giữ approval chỉ vì `contract_hash` không đổi | trước giữ mọi approval còn buộc đúng hash; nay approval của contract mà một thay đổi capability đã khai báo chọn trúng bị giữ lại, và ứng viên chưa nạp được (`lint` `NOT_READY`) cho tới khi duyệt lại | §2; duyệt lại là việc của chủ dự án |
| trạng thái `INDETERMINATE` của kiểm chứng finding | trước: probe chạy mà không quyết được vẫn mang trạng thái `NOT_REPRODUCED`; nay `INDETERMINATE`, và `NOT_REPRODUCED` chỉ cho `SATISFIED`; bản ghi cũ được đọc như đã viết | đọc `verification.status` (§8.3) |
| regex của luồng `{"regex": r}` (`cli_invocation`) khớp trong một tiến trình con | trước: `re.search` trong chính tiến trình probe, không hạn chót (một mẫu như `(a+)+$` treo kernel); nay hết hạn / không khởi động được / chết ⇒ `UNRUNNABLE` (review: `UNVERIFIABLE`), không bao giờ `REFUTED` hay `NOT_REPRODUCED` | đơn giản hoá mẫu, hoặc nâng `timeouts_s.probe` có chủ đích (§8.3) |
| `aisef run --parent` khi bằng chứng của dòng dõi có mà không đọc được | trước cửa sổ: một journal không đọc được bị đếm như "0 request đã biết"; ở đợt đầu của cửa sổ: chi phí unknown mà `--accept-unaccounted` chấp nhận; nay thoát 2 trước clone, admission và preflight, không cờ nào mở | khôi phục bằng chứng (§5) |
| OCR bị kiểm danh tính ở đầu `aisef run` (khi `finder: "ocr"`) | trước: binary sai chỉ lộ lúc review, sau khi developer đã chạy; nay thoát 2 trước claim, clone, preflight và mọi phiên | sửa pin hoặc đổi reviewer; `--out` mới (§3) |
| `<out>/probe-observations/` mới | `EVIDENCE.json` có thêm các tệp này; `--verify` đối chiếu | không |
| OCR hỏi `version` trước mọi lệnh review | binary có sha256 đúng pin nhưng tự khai khác `v1.12.12 (182898c…)` bị từ chối trước review | dùng đúng binary đã ghim |
| `process_effect`: bước `fault` trước bước `subprocess` | trước được nhận (lỗi không bao giờ tới tiến trình con); nay `INVALID_SPEC` | bỏ bước `fault`, hoặc đặt nó trước một bước `call`/`expect_raises` |
| reproducer của review lồng quá 63 tầng | trước được chạy (đến ~980 tầng); nay `UNVERIFIABLE` | làm phẳng stimulus/observable |

## 7. Giới hạn đã biết (đừng hiểu quá)

- **Chưa sửa — lệnh chi phí/báo cáo của V1 trả toàn 0 với exit 0 trên thư mục run V2** (backlog V21-43): `aisef cost`,
  `aisef report`, `aisef status` nhận một thư mục run V2 và trả số 0; `report` còn ghi `docs/ACCEPTANCE-REPORT.md` và
  `_bmad-output/` vào thư mục run hoặc repo của bạn. Đo trên bản sao một run thật có chi phí 0,000818 USD (2 phiên):
  `aisef cost` nói 0 phiên, nothing spent; `--verify` vẫn `VERIFIED` sau khi report V1 làm bẩn thư mục. Chưa có lệnh V2 đọc
  chi phí/báo cáo; hãy đọc `RUN.json` (`usage.cost`, `story_outcomes`) và đừng chạy các lệnh V1 trên thư mục run V2.
- **Chưa sửa — hai điểm CRLF trên Windows** (backlog V21-40): `tests/v2/p0/test_freeze_manifest.py:171` so byte của bản
  manifest đã commit với byte LF mà writer sinh (1 test đỏ dưới CRLF, 21/21 dưới LF), và checker `execution_order`
  (`validation/v2/execution_order.py`, `_committed_record`) đưa byte thô của tệp làm việc cho `mutation.committed` nên báo
  "is not a file committed at HEAD" trên checkout `core.autocrlf=true`. Cả hai đo bằng mô phỏng CRLF trên macOS, chưa phải
  Windows thật. Cho tới khi sửa, tài liệu này **không** nói hành trình người dùng hay hỗ trợ Windows đã đạt.
- Không có sandbox: developer và mã test chạy dưới user của người vận hành (V2-05 mở).
- `--verify` không có anchor chỉ chứng minh nhất quán.
- Review CONFIRMED không chứng minh người review đọc đúng yêu cầu.
- OCR đã nối vào `aisef run` và đã chạy **nhị phân thật** với một mô hình giả trên loopback: sha256 của nó khớp pin, nó tự
  khai `v1.12.12 (182898c)`, và một phép dựng lại từ commit `182898c` bằng go1.26.5 trên một máy cho ra đúng từng byte của
  nó (§8.3). **Không biết** ai và ở đâu đã dựng chính tệp được ghim; chưa có toolchain độc lập, chưa kiểm chữ ký, chưa so
  với artifact phát hành của upstream (quyết định D-OCR-1, mở), chưa có nền tảng nào ngoài darwin/arm64. Chưa chạy với mô
  hình thật.
- Ba lượt canary nhỏ với mô hình thật (≈ 0,599 USD, **ước tính**, REPORT §0.10) chỉ cho thấy đường chạy trên workload tầm
  thường: chưa chạy vòng sửa review, REFUTED thật, `--parent` sau lỗi, OCR hay cách ly Linux với mô hình thật.
- Repo giao có `__pycache__/*.pyc` trong `main`: ví dụ `bundle init` không có `.gitignore` và kernel commit những gì
  candidate để lại (canary tier 2 và 2b; backlog V21-39).
- Mã của chủ thể trả lời hộ chính nó (§8.6, PM-5): một ứng viên viết để làm vậy, hoặc nhận ra mình đang bị probe, có thể
  biến một sản phẩm hỏng thành `SATISFIED`; `delivery PASS` và `VERIFIED` không loại trừ điều đó.
- `aisef bundle continue`: một `CR`/`LF` trong đường dẫn của thư mục chứa worktree `wt-<story>` làm `reconcile` không báo
  mục `candidate` (báo cáo thiếu một dòng; kế hoạch không đổi); một dòng luồng phiên bắt đầu bằng `{`, không parse được và
  không phải dòng cuối, bị bỏ im lặng (0/176 dòng trong 8 luồng phiên mô hình thật của canary tier 2 và 2b).
- Neo kỳ vọng là quy tắc cơ học trên contract đã duyệt: nó không quyết định được một stimulus **mới** có thuộc điều kiện
  của mệnh đề hay không (giới hạn đã đo bằng test).
- Chưa có số đo hiệu quả so với agent chạy trực tiếp — xem [EXPERIMENT-PLAN.md](EXPERIMENT-PLAN.md).

## 8. Cửa sổ probe 2026-10-15: thay đổi so với `2d01fe4` (2.1.0.dev0 trước cửa sổ)

Nhánh ứng viên `v2.1/probe-window`, từ `2d01fe4` tới `3e1e83a` (cây `aisef2/` `1d4f0156…` → `168ad7d4…` ở `f69124c`,
sau đợt đầu → `28313c59…` ở `3e1e83a`, sau sáu làn của đợt hai: `migrate-semantics`, `lineage-proof`, `review-limits`,
`ocr-preflight`, `ocr-build`, `linux-recorder`). **So với cái
gì:** mỗi "trước cửa sổ" dưới đây là cây `2d01fe4`, **không** phải bản 2.0.0 đã phát hành. Nơi hành vi đó có cả ở `v2.0.0`
(tag, `ca26313`; đối chiếu trên mã) mục ghi *2.0.0 và trước cửa sổ*; nơi `v2.0.0` chưa có mã (lớp `python_imports`, hằng
`CAPABILITY_VERSION` và `EXECUTION_DIGEST`, `review_verify.py`, `review_ocr.py`, `lineage.py`, `bundle_cli.py`) mục ghi
*chưa có ở 2.0.0*. **Đã làm** = có
trong mã và test của nhánh (mỗi thay đổi hành vi có test đỏ trên mã trước cửa sổ, xanh sau, do làn tương ứng chạy). **Chưa có** =
hiệu chuẩn lại 19 hàng (§1), đo mutation, suite đầy đủ, e2e trong guest Linux và CI Windows/Linux cho cây này (REPORT §0.9).
Tên trạng thái dưới đây là tên trong mã: kết quả probe `SATISFIED`/`REFUTED`/`INDETERMINATE(PRECONDITION_ABSENT)`;
`UNRUNNABLE` (`HARNESS_FAILED` của quan sát; mã lỗi `PROBE_UNRUNNABLE`, owner `ENVIRONMENT`, retry được trong
`limits.ENVIRONMENT`); `INVALID_SPEC` (`PROBE_INVALID_SPEC`, owner `INTEGRATION`, không retry). Trạng thái *kiểm chứng
finding* của review (`CONFIRMED`, `NOT_REPRODUCED`, `INDETERMINATE`, `UNVERIFIABLE`, §8.3) là một từ vựng khác với
trạng thái *coverage* của reviewer OCR (hai bên đều có tên `INDETERMINATE`).

### 8.1 `file_artifact`: `grep_count`, `python_imports`

- **PM-9 — một lựa chọn không có tệp nào là chủ thể vắng** (chủ dự án duyệt phương án C ngày 2026-10-15;
  `CAPABILITY_VERSION` 2 → 3 so với `2d01fe4`; `v2.0.0` chưa có hằng này, danh tính khi đó là digest nguồn). *2.0.0 và trước
  cửa sổ (với `grep_count`; `python_imports` chưa có ở 2.0.0, trước cửa sổ cùng hành vi):* một đường dẫn **có** trong cây mà chọn ra 0 tệp (thư mục chỉ có `README.md` và
  JSON, một tệp `.md` đơn lẻ, `suffixes: [".py"]` trên thư mục không có `.py`) cho `Executed(SATISFIED)` khi `matches: 0`
  (`REFUTED` khi `matches` ≥ 1), không dấu hiệu nào — `files: 0` chỉ lộ cho người gọi `observe` trực tiếp; một đường dẫn
  **không** có trong cây cho `INDETERMINATE(PRECONDITION_ABSENT)`. *Nay:* cả hai là chủ thể vắng. Quan sát là
  `SUBJECT_ABSENT` (trong `detail`: `present: false`, `files: 0`, `suffixes` đã chọn) và `subject_absence` đã khai của
  contract quyết: `REQUIRES_SUBJECT` ⇒ `INDETERMINATE(PRECONDITION_ABSENT)` (kể cả khi trước là `REFUTED`);
  `ABSENCE_IS_DECIDABLE` ⇒ verdict giữ nguyên (`SATISFIED` khi M = 0). Định tuyến (`aisef2/control/routing.py`): ở parent,
  nghĩa vụ INTRODUCE ⇒ `READY`, PRESERVE/VERIFY ⇒ `PRECONDITION_BROKEN` (owner PLAN); ở candidate ⇒
  `SUBJECT_ABSENT_AT_CANDIDATE` (DEVELOPER, retry được); sau merge ⇒ `POST_MERGE_SUBJECT_LOST` (INTEGRATION). Theo mã
  (chưa đo): một story mà mọi nghĩa vụ là lệnh cấm đứng một mình không còn `PRE_SATISFIED` trên thư mục không còn `.py`.
  **Không đổi:** một tệp rỗng, tệp chỉ có BOM, tệp nhị phân đã được *chọn* vẫn là chủ thể. **Còn lại:** `grep_count` trên
  lựa chọn toàn tệp nhị phân (tệp `.py` có NUL: `files: 1`, `matches: 0`, `skipped_binary`) vẫn `SATISFIED`;
  `python_imports` trên cùng tệp là `REFUTED` (không phân tích được) — backlog V21-60. Spec/approval bị ảnh hưởng: §8.7;
  cách `migrate` xử lý approval của chúng (khai báo `CAPABILITY_CHANGES[3]`, `ref` `PM-9`): §2.
- **PM-13 — vòng khớp regex của `grep_count` có hạn chót** (chủ dự án duyệt phương án a). *2.0.0 và trước cửa sổ:* `pattern.search(line)`
  chạy trong chính tiến trình kernel, không hạn chót; một mẫu có lượng từ lồng trên một dòng dài (ví dụ `^(\w+\s?)*$` trên
  một dòng gồm chữ rồi `!`) làm `aisef run` đứng im — một lõi 100%, không dòng journal nào. Đo ở `becf3c0` (máy tải 10–16 nên
  số tuyệt đối bị thổi phồng; `within_s` = 10): 26 ký tự 5,9 s `SATISFIED`; 28 ký tự 24,5 s `REFUTED` (cửa sổ `within_s`
  hết hạn *sau* khi lần đọc xong); 30 ký tự 60 s `REFUTED`; 34 ký tự không trả về trong 180 s. *Nay:* vòng khớp chạy trong một tiến trình con (`sys.executable -I -S -B`, trong một process range, môi
  trường được lọc, chỉ nhận mẫu và byte của các tệp được chọn), bị chặn bởi `timeouts_s.probe`. Một worker không trả
  facts hợp lệ trong hạn là `HARNESS_FAILED` ⇒ **UNRUNNABLE**, không bao giờ `REFUTED`. `detail` mở bằng
  `grep_count worker <LÝ DO>:`, LÝ DO ∈ `DEADLINE` (nêu tệp, dòng đang khớp, đầu mẫu và lối ra: đơn giản hoá mẫu — không
  lượng từ lồng hay chồng lấn trên cùng văn bản — hoặc nâng `timeouts_s.probe` có chủ đích), `LAUNCH`, `CRASHED`,
  `NO_RESULT`, `BAD_RESULT`, `INPUT`. Mọi lần đọc trả về hôm nay giữ nguyên facts và verdict, kể cả PM-12 (cửa sổ
  `within_s` vẫn quyết sau khi đọc). *Giới hạn:* (1) trần thật của một quan sát `grep_count` là
  `max(timeouts_s.probe, 30 s)` cộng dọn range, vì `ProcessRange.start` chờ tối đa 30 s cố định cho target báo đã chạy —
  một range chậm khởi động dừng ở `LAUNCH` (backlog V21-63); (2) đời sống của worker (≈ 25 ms trên máy đo) tính vào thời
  gian đọc, nên một `within_s` dưới ≈ 0,1 s với cây nhỏ có thể lật so với 2.0.0 và `2d01fe4` (chi phí sở hữu worker ≈ 0,1 s đã trừ khỏi
  cửa sổ; spec trong kho dùng 5 và 30 s); (3) bộ nhớ của worker ≈ 2,2 lần đầu vào, không có trần tổng đầu vào, chỉ
  `FILE_CAP` 4 MiB mỗi tệp. Các số đo ở (2) và (3) là của làn `file-artifact-2` trên một laptop đang tải ((1) đọc từ mã); báo cáo kết quả của
  làn **chưa được commit** và `tests/v2/test_v21_fa_grep_worker.py` ghim hành vi, không ghim các con số (backlog V21-62,
  V21-63). Regex của luồng `cli_invocation` (`{"regex": r}`) không nằm trong vùng PM-13: nó có worker riêng (§8.3).
- **PM-3, PM-4 — giới hạn của parser là một từ chối có kiểu.** *Chưa có ở 2.0.0 (không có lớp `python_imports`); trước cửa sổ:* `ast.parse`
  raise `RecursionError`/`MemoryError`
  trên một tệp hợp lệ nhưng lồng sâu thoát khỏi `observe`/`run_probe` như một exception; detail của lỗi không nêu dòng
  ghi `x.py:None`. *Nay:* `python_imports` trả **UNRUNNABLE** (`PROBE_UNRUNNABLE`, owner `ENVIRONMENT`), không verdict,
  không đếm; `detail` mở bằng `'<tệp>': this interpreter's parser stopped (RecursionError|MemoryError: a nesting, stack
  or memory limit of its own) before it could say what the file is, so there is no count and no verdict (refused, not
  refuted)` và nêu lối ra (làm tệp nông hơn: tách chuỗi toán tử dài, thang `elif`, lambda lồng; hoặc chạy trên interpreter
  có giới hạn lớn hơn). Một **lỗi cú pháp thật** vẫn là `REFUTED` với `unparsable <tệp>:<dòng>`; dòng parser không nêu
  (byte NUL, cookie mâu thuẫn) ghi `<tệp>:?`. Một từ chối thắng câu trả lời riêng của mọi tệp, bất kể thứ tự liệt kê: loại
  kết quả là của cây, không phải của thứ tự reader. *Chưa làm (backlog V21-57, V21-58):* không retry cho cùng đầu vào — mỗi
  `PROBE_UNRUNNABLE` còn retry được trong `limits.ENVIRONMENT` và mỗi retry gọi lại developer (đo: giới hạn 1 → 2 lần gọi);
  và lời khắc phục không tới developer (`failure/observed.detail` chỉ là `proof of <tiêu chí>: PROBE_UNRUNNABLE`; thông
  điệp đầy đủ nằm ở `probe/evaluated` của journal).
- **PM-11 — một BOM không phải nội dung.** *`python_imports`, trước cửa sổ (chưa có ở 2.0.0):* tệp UTF-8 có BOM bị coi
  `unparsable` dù CPython biên dịch được ⇒ `REFUTED` tính cho developer. *`grep_count`, 2.0.0 và trước cửa sổ:* BOM còn là
  U+FEFF ở đầu dòng 1 nên neo `^` ở dòng đầu bị lỡ (một nghĩa vụ `^from …`, `matches: 1`, thấy 0). *Nay:* `python_imports` và `grep_count` bỏ một BOM UTF-8 đứng
  đầu tệp (như CPython). Hai hệ quả, nêu để không ai tự phát hiện từ một verdict: (1) **không pattern `grep_count` nào
  thấy BOM đầu tệp** (không phải U+FEFF, không phải lớp ngoài ASCII) — muốn cấm BOM, nêu trên byte bằng `content`;
  (2) BOM đi kèm một coding cookie nói khác UTF-8 (hoặc codec không tồn tại) là syntax error như CPython: `unparsable`
  `<tệp>:?`; một cookie không có BOM không được đọc (tệp không UTF-8 ⇒ `undecodable`, như trước). Verdict `grep_count` có thể
  đổi trên một tệp có BOM: §8.7.

### 8.2 Probe chạy chủ thể: `cli_invocation`, `process_effect`, `python_callable_v2`

- **PM-1 — module dưới thư mục không có `__init__.py`.** *2.0.0 và trước cửa sổ:* một module nằm dưới một thư mục không có
  `__init__.py` (namespace package) không bao giờ được định vị ⇒ `UNRUNNABLE` (`HARNESS_FAILED`; đo: 23 layout × 3 probe và
  6 layout `__main__`, bởi làn `effect-cli` trên mã trước cửa sổ; kết quả từng layout chưa được commit, reproducer ở
  `decisions/B03-R3-PROBE-MODULE-FINDINGS.md`). *Nay:* mỗi thành phần của tên chấm được tra bằng tên của riêng nó trong các vị trí của cha, ở mọi
  độ sâu, như hệ thống import: có ⇒ quan sát bình thường; vắng ⇒ `SUBJECT_ABSENT`; một module chỉ có trong stdlib ⇒
  `SUBJECT_ABSENT` (`resolves only outside the revision`). Một thư mục dưới tên trùng module stdlib đã nạp (`queue`,
  `types`, `os`…): `REFUTED` bằng chính lần import của agent (`ModuleNotFoundError`), như CPython.
- **PM-2 — bước `fault` đứng trước bước `subprocess`.** *2.0.0 và trước cửa sổ:* được nhận, nhưng lỗi chỉ được cài trong tiến trình của
  chủ thể còn bước `subprocess` chạy một interpreter khác nên không bao giờ thấy nó (`fired: false`); kịch bản bị phán như
  chưa khai lỗi ⇒ một sản phẩm hỏng dưới lỗi vẫn `SATISFIED`. *Nay:* `FAULTED = (call, expect_raises)`; kịch bản
  `[fault, subprocess]` không có lớp ⇒ `INVALID_SPEC` tại admission (`aisef bundle lint`, kiểm tra 9:
  `spec …: probe.process_effect does not support the observation it asks for`), không tiến trình nào được dựng. *Không
  đổi (ghi nhận):* một `fault` đứng trước một `call` mà mã gọi không chạm tới vẫn `SATISFIED` với `fired: false`.
  `CAPABILITY_VERSION` của `process_effect` giữ 1 (lựa chọn của làn theo quy ước; chủ dự án quyết lại được — backlog
  V21-71). Quét kho: 0 spec/plan/approval/bundle chứa tổ hợp này; bundle 2.0.0 trên PyPI và dự án ngoài kho không quét
  được.
- **PM-6 — lỗi máy chủ.** `open(harness.log)` (và `request.json` ở `python_callable_v2`) nằm trong khối `try`: lỗi ⇒
  `HARNESS_FAILED` `the evaluation directory cannot be prepared: <Loại>` ⇒ `UNRUNNABLE`, thư mục đánh giá được dọn.
  Một NUL trong argv của bước `subprocess` của `process_effect` ⇒ spec không có lớp (`INVALID_SPEC`, refused ở
  admission). *Còn nhận:* NUL trong argv của `cli_invocation` (và `pre`) vẫn được chuyển nguyên (verdict là phản ứng của
  chủ thể) — backlog V21-71.
- **PM-7 — nguồn của `EXECUTION_DIGEST` được đo, không ước.** Mỗi probe khai các tệp mà mã của chúng *chạy* trong một
  quan sát: `product/contract.py`, `product/outcome.py`, `runtime/process_range.py`, `runtime/range_anchor.py` (cộng
  `probe/protocol.py` và các tệp của riêng probe). Đo bằng profile hàm trên test thật, `-X importtime` trên cả hai
  tiến trình con và đọc import tĩnh; một test bền giữ cho lệch về sau bị bắt. Hệ quả: sửa một trong bốn tệp làm hàng hiệu
  chuẩn của probe không còn nhận được (trước đây 5 commit sửa `process_range.py` vẫn để 19/19 hàng "hợp lệ"). **Đây là
  danh tính, không phải quyền** (một nguồn chỉ được băm; không đọc, chạy hay sao chép cho probe) **và không phát hiện hồi
  quy**: đo trước cửa sổ, một `members()` trả `[]` hay một reaper bị tắt vẫn qua vòng chứng minh tương phản 19/19; chỉ
  test đơn vị và mutation của runtime bắt được (OWNER-DECISIONS-2026-10-15.md, PM-7). `digest năng lực` (`DIGEST`) và spec
  id không đổi vì PM-7; 19 hàng hiệu chuẩn phải được chứng minh lại một lần (cli_invocation 5, process_effect 3,
  python_callable_v2 7, file_artifact 4).
- **Họ RV-1 ở probe — dữ liệu mô hình hay ứng viên viết là một verdict hay một lý do, không bao giờ một exception.** Một
  stdout của ứng viên lồng quá parser JSON (`json_equal`) ⇒ không bằng nhau (`REFUTED`, không `UNVERIFIABLE`: ứng viên
  không được làm kiểm tra của chính nó bất định bằng cách lồng đầu ra); một regex không biên dịch được (`re.error`,
  `OverflowError`, `RecursionError`) hay một `within_s` là số nguyên không float nào chứa được làm observable vô nghĩa ngay
  lúc phân loại (không có lớp ⇒ `INVALID_SPEC`; ở review: `UNVERIFIABLE`, `gives the reproducer's observation no meaning
  (refused)`); một `streams` có phần tử không phải tên ⇒ vô nghĩa; một giá trị ứng viên trả về lồng sâu ở
  `python_callable_v2` ⇒ `REFUTED` (`unserializable`). *Còn khác nhau giữa các probe* (backlog V21-70): ở dải sát giới hạn
  đệ quy `process_effect` (từ ~500 tầng) và một dải hẹp của `python_callable_v2` (~990 tầng) trả `UNRUNNABLE` có kiểu
  (`the harness raised RecursionError`), còn các độ sâu khác là `REFUTED` (đo của làn `review-contracts` trên Python 3.11.15;
  báo cáo của làn chưa được commit).

### 8.3 Review

- **RV-1 — giới hạn độ lồng của reproducer.** Một reproducer lồng container quá 63 tầng là một lý do có cấu trúc: `verify`
  `UNVERIFIABLE` (`the reproducer nests containers deeper than 63 levels: state it with a flatter stimulus and observable
  (no probe grammar needs more)`), anchor `UNANCHORED`, không chạy probe, không chặn; các finding khác của lượt vẫn được xét
  và review `COMPLETED`. *Chưa có ở 2.0.0 (không có reproducer của review); trước cửa sổ:* `RecursionError` thoát khỏi review
  ở ~3.000 tầng. Hành vi đổi có chủ đích: reproducer
  64…~980 tầng trước đây được probe chạy (dữ liệu thật lớn nhất trong kho: 8 tầng); chủ dự án chưa xác nhận con số 63
  (backlog V21-67). Văn bản trả lời của mô hình lồng quá độ sâu parser JSON được xử như mọi văn bản không parse được
  (0 finding, `COMPLETED`): một reply cực sâu làm mất cả lượt finding của review đó.
- **RV-2 — `INDETERMINATE` là trạng thái máy đọc riêng, tách khỏi `NOT_REPRODUCED`** (chỉ thị 2026-10-15, mục 3).
  *Trước cửa sổ:* một probe đã chạy mà không quyết được vẫn mang trạng thái `NOT_REPRODUCED` (kèm `observed:
  INDETERMINATE`) và câu "the finding does not reproduce". *Nay* `verification.status` là một trong bốn giá trị của
  `review_verify.STATUSES`: `CONFIRMED` — probe `REFUTED` hành vi được nêu; `NOT_REPRODUCED` — **chỉ** khi probe
  `SATISFIED`; `INDETERMINATE` — probe đã chạy mà không quyết được (thông điệp `<probe> could not decide the stated
  behaviour (INDETERMINATE, <nguyên nhân>): neither confirmed nor ruled out`); `UNVERIFIABLE` — mọi kiểm tra không chạy
  được hoặc không quyết được vì công cụ (reproducer vô nghĩa, probe `UNRUNNABLE` hay `INVALID_SPEC`, hết hạn, nesting quá 63
  tầng). Chỉ `CONFIRMED` có bằng chứng (`Verification.evidence()`) và chỉ `CONFIRMED` (cùng ANCHORED và mức ≥
  `min_severity`) chặn: một kiểm tra không thực hiện được hay không đủ kết luận **không bao giờ** là bằng chứng rằng
  finding không tái hiện. Trạng thái có mặt ở dòng journal `verification`, ở `RUN.json` `findings[].verification.status` và
  ở artifact `review-findings/…`. Không đổi format và không cần migration: `aisef run --verify` không đọc giá trị trạng
  thái, nên bản ghi cũ (`NOT_REPRODUCED` với `observed: INDETERMINATE`) vẫn xác minh được và được đọc như đã viết, không
  bị diễn giải lại (quét kho: 28 `RUN.json`, 5 hàng review của journal và 0 thư mục `review-findings/` đã commit, không
  cái nào mang từ vựng nào của cửa sổ). Hai từ vựng cùng tên `INDETERMINATE` (kiểm chứng finding; coverage của reviewer
  OCR) là hai thứ khác nhau.
- **Regex của reproducer (và của spec) chạy dưới hạn chót** (chỉ thị 2026-10-15, mục 4). *Trước cửa sổ:* luồng
  `{"regex": r}` của `cli_invocation` chạy `re.search` trong chính tiến trình probe, không hạn chót; một mẫu như `(a+)+$`
  trên một dòng gồm toàn `a` làm kernel đứng, không verdict. *Nay* việc khớp chạy trong một worker (`REGEX_WORKER`,
  `sys.executable -I -S -B`, trong một process range riêng, nhận mẫu và byte của luồng qua tệp) dưới `ExecutionEnv.timeout_s`
  = `timeouts_s.probe` cho cả thao tác. Một worker không trả lời trong hạn — treo (`DEADLINE`), không khởi động được
  (`LAUNCH`), chết (`CRASHED`), không viết gì (`NO_RESULT`), viết thứ không phải câu trả lời (`BAD_RESULT`) hay không ghi
  được yêu cầu (`INPUT`) — là dừng của harness: thông điệp mở bằng `regex search <LÝ DO>:`, quan sát là `HARNESS_FAILED` ⇒
  `UNRUNNABLE` (owner `ENVIRONMENT`), ở review `UNVERIFIABLE`; **không bao giờ `REFUTED` hay `NOT_REPRODUCED`**. Việc khớp
  chỉ bắt đầu sau khi range của chủ thể đã `release` (các tệp của worker nằm trong một thư mục `mkdtemp` tạo lúc đó, nên
  chủ thể không với tới yêu cầu hay kết quả), và thời gian khớp không bị tính vào `within_s`. Khi worker trả lời, verdict
  giữ nguyên như `re.search` trong tiến trình (người xác minh so 151 cặp, 0 sai khác). Kiểm chứng: mẫu treo ⇒
  `HARNESS_FAILED` sau ≈ 2,5 s với `timeouts_s.probe` = 2 s, kết quả bình thường, và range được dọn sau mỗi lần (không còn
  tiến trình `regex-`). Giới hạn còn lại ở D4 dưới (`re.compile` của mẫu vẫn chạy trong kernel). Hai hàm khớp văn bản của
  mô hình bậc hai (`adapters._braces`, `review_ocr._fence`) được viết lại tuyến tính, kết quả giữ nguyên.
- **`within_s` và dữ liệu lồng sâu: giới hạn của công cụ không phải verdict về sản phẩm.** Chỉ thị 2026-10-15, mục 4: phân
  biệt giới hạn thực thi của công cụ với điều kiện thời gian mà contract đòi sản phẩm đáp ứng; áp dụng định nghĩa biên đã
  công bố; nơi chưa có định nghĩa hoặc mâu thuẫn, đưa đúng biểu thức và hai hành vi cho chủ dự án, không chọn theo test nào
  dễ xanh. *Đã áp dụng:* một `within_s` là số nguyên không float nào chứa được (400 chữ số), dữ liệu lồng quá 63 tầng và
  deadline của worker regex cho `UNVERIFIABLE` / `UNRUNNABLE`, không cho verdict; thời gian một lần khớp chậm không đổi
  verdict. Biên được **công bố** chỉ ở `file_artifact`: RFC §9.2 nói "within the bounded observation window" mà không nêu
  `<` hay `<=`, PM-12 nêu `REFUTED` khi đọc "took longer than within_s", và mã
  `expired = time.monotonic() - started - sum(hosting) > window` (`aisef2/probe/file_artifact.py:881`) là so sánh chặt,
  đồng hồ bắt đầu từ chính lần đọc, đã trừ chi phí worker. `tests/v2/test_v21_r5_window_boundary.py` (bốn test) ghim nó cho
  `exists`/`content`/`grep_count` ở {0, W−1e-6, W, W+1e-6}; các test ấy xanh cả trên mã trước, vì chúng đặc trưng hoá hành
  vi sẵn có (người xác minh đột biến `>` thành `>=` trong `file_artifact.py`: 5 lỗi). Những điểm còn lại là **quyết định của chủ dự án**, lane không chọn hành
  vi nào. Đánh số: D1–D5 theo thứ tự trình bày ở đây; lane `review-limits` đánh số hai chỗ ngược lại (D3 của lane là trần
  `within_s` = D5 ở đây; D5 của lane là toán tử biên = D3 ở đây; backlog V21-83 ghi ánh xạ) và nêu thêm D6, D7 ngoài năm
  quyết định (V21-88). Một đầu vào dưới đây là **đo** (lane hay người xác minh chạy nó) hay **đọc từ mã, chưa chạy**
  được ghi ở từng chỗ:
  - **D1 — `within_s` dưới sàn mà công cụ giữ được** (backlog V21-81). Biểu thức: `aisef2/probe/python_callable.py:108-112`
    (`window_of` chỉ đòi hữu hạn và `> 0`); `aisef2/probe/cli_invocation.py:908`
    `threading.Timer(req["window"], conclude, ({"deadline": True},))`; `cli_invocation._deadline` (`:1320`) trả
    `ON_DEADLINE[cls]` (`REFUTED` với `exits_streams`); `aisef2/app/review_verify.py:224` biến `REFUTED` thành `CONFIRMED`
    (không phân biệt `SUBJECT_DEADLINE` với sai hành vi). Đầu vào: chủ thể `echo hi`, `exit_code` 0. A (hiện tại):
    `within_s` 0,001 ⇒ `SUBJECT_DEADLINE`/`REFUTED` sau 0,39 s ⇒ review `CONFIRMED` (và nếu `ANCHORED` thì chặn dưới
    `fix-loop`); cùng chủ thể với `within_s` 0,02 hoặc 20 ⇒ `SATISFIED`. B: khai báo một sàn (ví dụ thời gian khởi động tối
    thiểu đo được); cửa sổ nhỏ hơn không có nghĩa ⇒ `UNVERIFIABLE`, như `within_s` không hữu hạn. B2 (lane ghi thêm, chỉ
    sửa anchor, không đụng probe): đưa `within_s` vào anchor, `UNANCHORED` khi cửa sổ của reviewer nhỏ hơn cửa sổ nhỏ nhất
    của các contract đã duyệt cho cùng mệnh đề. Lane đo trên reference LedgerLock, finding `R-9/3` (`snapshot
    <ws>/missing.jsonl`, kỳ vọng exit 3): `within_s` 20 ⇒ `NOT_REPRODUCED`, không chặn; `within_s` 0,001 ⇒ `CONFIRMED` +
    `ANCHORED`, chặn dưới `fix-loop` (mức `high`).
  - **D2 — stream bị cắt ở `STREAM_CAP`** (V21-82). Biểu thức: `aisef2/probe/cli_invocation.py:253`
    `STREAM_CAP = 8 * 1024 * 1024`; `:565` `"truncated": size > STREAM_CAP`; `:582-601` `_stream_matches` chỉ shape
    `text` (`:591`) kiểm `truncated`, các shape `contains`, `regex`, `lines`, `first_word` quyết trên các byte đã giữ.
    Đầu vào: chủ thể in 9 MiB `x`. A (hiện tại): `stdout` `{"regex": "x{9000000}"}` ⇒ `REFUTED` (review `CONFIRMED`);
    `x{8000000}` ⇒ `SATISFIED`. B: stream bị cắt dưới một shape không chính xác mà các byte đã giữ chưa quyết được ⇒
    `INDETERMINATE` (hay `HARNESS_FAILED`), vì phần bị cắt là giới hạn của công cụ; shape chính xác vẫn `REFUTED` như nay.
  - **D3 — toán tử biên của probe dùng timer ở đúng W** (V21-83; D5 trong số của lane). Biểu thức:
    `aisef2/probe/file_artifact.py:881` `> window` (chặt, đã công bố bởi PM-12), so với `aisef2/probe/cli_invocation.py:895-908`
    (`settle()` và `conclude()` tranh một khoá; `Timer` được bật ngay sau `DISPATCHED`, trước khi phân giải module và
    pre-step) và `aisef2/probe/python_callable_v2.py:278-291` (như vậy); `process_effect.py:907` đi qua
    `cli_invocation.py:1097` (`tag in seen`, kiểm trước `:1103` `left <= 0`: câu trả lời đã có thì thắng, nhưng chu kỳ poll
    là 20 ms); `python_callable.py:362-363` (v1, không active) kiểm `left <= 0 ⇒ TIMEOUT` trước khi đọc hàng đợi. Đầu vào
    (của lane): `{argv: ["sleep", "0.3"]}` với `within_s` 0,3. A: khi hoà thì **câu trả lời thắng** (trong W, như
    `file_artifact` và như `process_effect` khi tệp đã có dòng). B: khi hoà thì **deadline thắng** (như `python_callable`
    v1). Hiện tại: với `cli_invocation` và `python_callable_v2` là một cuộc đua giữa hai thread, không xác định, không
    test được. Còn phải chọn (lane ghi, backlog V21-83): *mốc bắt đầu* của đồng hồ (`file_artifact`: `started` trước khi dựng
    reader, gồm `git rev-parse`; harness: sau `DISPATCHED`) và *phần bị loại trừ* (chỉ hosting của worker grep; thời gian
    `git cat-file` và vòng regex trong worker tính vào cửa sổ — giới hạn đã biết PM-12). Lane giữ cho việc này một câu
    hỏi mở, không chọn toán tử theo test nào dễ xanh.
  - **D4 — trần độ dài pattern và giới hạn compile** (V21-84). Biểu thức: `re.compile(pattern)` trong `_compiles`
    (`aisef2/probe/cli_invocation.py:446`, `aisef2/probe/file_artifact.py:274`), chạy trong kernel, không hạn chót, từ
    `observation_class`; `PATTERN_CAP = 512` (`file_artifact.py:176`) chỉ được kiểm sau compile (`:864`) và
    `cli_invocation` không có trần. Đo: `(?i)` + 1000 lớp `[\u0000-\U0010ffff]` (19 KB) 3,7 s, 76 KB 15 s trong kernel
    (người xác minh: 38 KB ≈ 7,8 s); chi phí tuyến tính theo kích thước trên 10 họ pattern, không thấy siêu tuyến tính.
    A (hiện tại, đã ghi trong docstring): giữ nguyên. B: trả `None` (không có nghĩa) khi pattern dài hơn một trần (ví dụ
    512) ở cả hai classifier, trước compile. C: compile cũng trong worker.
  - **D5 — trần của `within_s` do reviewer chọn** (V21-85; D3 trong số của lane). Biểu thức:
    `aisef2/probe/python_callable.py:108-112` (`window_of`: chỉ đòi hữu hạn và `> 0`, không có trần);
    `aisef2/probe/cli_invocation.py:908` `threading.Timer(req["window"], conclude, …)` và `:1301` `time.monotonic() + window
    + env.timeout_s`; `aisef2/probe/python_callable_v2.py:291` và `:528`; `aisef2/probe/process_effect.py:907` (không có
    `timeout_s`). **Đầu vào đã đo (lane):** `within_s` 1e10 và chủ thể treo — `threading.Timer(1e10).start()` chết ngay
    (`OverflowError`; `is_alive` `False` sau 0,3 s; 1e9 thì sống), nên với một `within_s` hữu hạn ≥ `threading.TIMEOUT_MAX`
    (9223372036 s) controller không bao giờ phát deadline và bên cha chờ `window + timeouts_s.probe`; chủ thể quay lại bình
    thường thì verdict bình thường. **Đầu vào đọc từ mã, chưa chạy:** một `within_s` lớn nhưng nhỏ hơn `TIMEOUT_MAX` (lane
    viết 86400; ví dụ 3600 với chủ thể `sleep 3600`): review chờ ≈ W rồi `SUBJECT_DEADLINE` (`REFUTED`), nghĩa là một
    chủ thể treo giữ review đúng bằng cửa sổ do reviewer chọn. A (hiện tại): giữ. B1: đặt trần cho `within_s` (trị số do
    chủ dự án) trong classifier của ba probe — trên trần là không có nghĩa (`INVALID_SPEC` ở admission, `UNVERIFIABLE` ở
    review); đổi ngữ pháp, tăng `CAPABILITY_VERSION` (RFC §35) và mất hiệu lực approval/plan dùng probe. B2: chỉ đặt trần
    trong `review_verify` (ví dụ ≤ `timeouts_s.probe`) ⇒ `UNVERIFIABLE`, không đụng probe.
  - **D6 — chủ thể ở lại ghi đè tệp capture mà fact trỏ tới** (V21-88; phát hiện thêm của lane, không thuộc năm quyết định
    trên). Biểu thức: `aisef2/probe/cli_invocation.py:573-579` `_stream_bytes` đọc `min(size, STREAM_CAP)` byte từ
    `fact["path"]` mà không so `fact["sha256"]`; `:973-977` `stream_fact` đã tính `sha256`. Đầu vào đo (lane): sản phẩm in
    `bad\n`, ở lại và ghi vào chính `stdout.bin` của nó. A (hiện tại; một phần, họ PM-5): spec stdout `OK!\n` `SATISFIED`
    4/4, `bad\n` `REFUTED` 4/4 — chủ thể quyết verdict của chính nó. B: so sha256 của `size` byte đầu với fact; lệch ⇒
    `tampered` và `REFUTED` như một dòng protocol giả (quy tắc B1), hoặc `HARNESS_FAILED`; fixture fact của
    `test_c2_cli_verdicts` khi đó phải mang sha256 đúng.
  - **D7 — `_IMPORT_ERROR` bậc hai trên output test của ứng viên** (V21-88; phát hiện thêm của lane). Biểu thức:
    `aisef2/quality/test_execution.py:401` và `:416`: `.+? from` quét tới hết dòng ở mỗi `ImportError: cannot import name`.
    Đây là output test của chính ứng viên, không phải pattern của reviewer hay của tác giả spec. Đo (lane): một dòng 97 KB
    lặp cụm ấy mất 1,1 s, 388 KB mất 18,4 s; nhiều dòng ngắn 3 ms. A: để, ghi nhận. B: quét tuyến tính như
    `_fence`/`_braces` (lần mở đầu thất bại trên một dòng thì mọi lần sau trên dòng ấy cũng thất bại) cùng một test vét cạn
    so với pattern. C: chỉ tìm trong N ký tự cuối của phần thân.
- **Cổng danh tính OCR — tự khai khác bằng chứng dựng, và hỏi sớm.** *Trước cửa sổ (OCR chưa có ở 2.0.0):* chỉ kiểm sha256
  của binary. *Nay*, với `review.finder: "ocr"` (cả `advisory` lẫn `fix-loop`), AISEF kiểm hai điều, **hai lần**:
  (i) **ngay đầu `aisef run`** (và `aisef run --check`) — việc đầu tiên trong thân `try` của `run.execute` (sau các kiểm
  tra `--out` và `--parent` có bản ghi, và `RUN.started.json`), trước claim `--parent`, clone,
  admission, test interpreter, preflight provider và mọi phiên, nên một binary sai không để developer chạy rồi mới lộ (chỉ
  thị 2026-10-15, mục 5): từ chối có cấu trúc, mã thoát 2, không phiên nào, không request nào; (ii) **trước mọi lệnh
  review** — kiểm soát lúc dùng, không bị lần nhìn sớm thay thế (cùng hai hàm, `review_ocr.pinned` rồi
  `adapters._declared`, nên một binary bị thay giữa chừng bị từ chối ở đó). Hai điều: (1) `pinned` — đường dẫn tuyệt đối,
  đọc được, sha256 = pin; (2) `declared` — chạy `<exe> version` trong môi trường sạch (`PATH=/usr/bin:/bin`, HOME rỗng,
  không kế thừa gì, `OCR_NO_UPDATE=1`, tối đa 15 s); dòng đầu phải là `open-code-review <version> (<commit>) <platform>`
  với version `v1.12.12` và commit (in dạng ngắn) là tiền tố của `182898cf522da3d04157b422752d028417974e19`. Lệch ⇒ không
  lệnh review nào được chạy; thông điệp của bước (2) là một trong:

  ```
  <exe>: declares itself <version> (<commit>), not the pinned v1.12.12 (182898c): no review command was run
  <exe>: `version` did not answer in time
  <exe>: `version` exited <N>
  <exe>: `version` printed no version line (first line '<…>')
  <exe>: `version` could not be started (<ExcType>: <lý do của hệ điều hành>)
  ```

  Bước (1) có ba thông điệp riêng, nêu trước `version`: `<exe>: the OCR binary is named by an absolute path, never looked up`,
  `<exe>: cannot be read (<ExcType>)` (kể cả đường dẫn chứa NUL hay surrogate lẻ: một từ chối có lý do, không phải
  traceback) và `<exe>: sha256 <12 hex>, not the pinned <12 hex>`.

  Ở lúc dùng, mỗi thông điệp là một `CapabilityUnrunnable`, tức failure `CAPABILITY_UNRUNNABLE` (owner `ENVIRONMENT`, retry
  được trong `limits.ENVIRONMENT`) **ở cả hai `review.policy`**: khác với coverage chưa đủ — chỉ chặn dưới `fix-loop` —,
  kiểm sha256 và `version` ném trước khi chính sách được xét (`aisef2/orchestrate/review.py`), nên một binary hỏng lúc dùng
  kết thúc mọi story dưới cả hai chính sách; vì vậy lần nhìn sớm cũng áp dụng cho cả hai. Kết quả lúc dùng nằm trong phiên
  reviewer của `RUN.json`, `sessions[].identity`: `sha256_checked`, `declared` và `declared_by` = "the binary's own `version`
  output: a self-declaration, not build evidence". Lần nhìn sớm nằm ở `RUN.json` `ocr_identity` (§3): `status`, `levels`
  (`sha256_matches_pin`, `declared_matches_release`, `build_provenance: NOT_ESTABLISHED`), `expected`, `observed`. Cả hai
  lần không gọi provider nào. Không đường nào của `aisef run` đặt `build_provenance` khác `NOT_ESTABLISHED`.
  Ba lớp bằng chứng, không bao giờ gộp ([BUILD-RECIPE.md](../../validation/v21/ocr/BUILD-RECIPE.md),
  [PROVENANCE.md](../../closure-evidence/v2/v2.1/round-5/ocr-build/PROVENANCE.md)):

  | lớp | là gì | cho biết | trạng thái cho binary ghim (darwin/arm64, một binary) |
  |---|---|---|---|
  | (a) tự khai | dòng `version` do người dựng đặt bằng `-ldflags -X` | binary tự nhận là gì | `open-code-review v1.12.12 (182898c) darwin/arm64`; khớp pin; cổng chấp nhận |
  | (b) khớp hash đã ghim, cộng metadata nhúng | sha256 của tệp = pin; build info Go (`go version -m`, đọc tệp, không chạy) | `go1.26.5`, `-trimpath=true`, `vcs.revision` = commit ghim, `vcs.modified=false`, 84 phụ thuộc | sha256 khớp; đã đọc; **không** chứng minh checkout là nguồn upstream nguyên vẹn |
  | (c) dựng lại được | sha256 của bản dựng lại từ đúng commit ghim, so với binary | cách duy nhất để biết các byte này **tái tạo được** từ nguồn công khai | **`IDENTICAL` trên một máy, một toolchain**: dựng `./cmd/opencodereview` từ commit `182898cf522da3d04157b422752d028417974e19` bằng go1.26.5 (Homebrew), `-trimpath`, các cờ liên kết của Makefile upstream (ba giá trị `-X` lấy từ chính binary) cho đúng sha256 `bf38abf3…04af7`, 55 014 610 byte (3/3 lần dựng ở ba chỗ, rồi 3/3 ở lượt rà soát với GOCACHE nguội mới); mỗi đối chứng đổi đúng một thứ cho sha256 khác |

  Mức (c) có nghĩa chính xác: *các byte này tái tạo được từ commit đó, qua toolchain đó, với các cờ đó, và các module mà
  `go.sum` của upstream ghim.* **Không được xác minh** (PROVENANCE.md mục 6–7): (1) ai và ở đâu đã dựng chính tệp được ghim
  — bằng chứng không trả lời (ba dấu vết yếu chỉ phù hợp với một bản dựng cục bộ); (2) toolchain độc lập (một toolchain bị
  nhiễm vẫn cho cùng byte; chưa so với bản của go.dev); (3) hai chữ ký của tag và commit (máy không có `gpg`); (4) artifact
  phát hành của upstream: không tải, không so — workflow phát hành của upstream chạy `golang:1.26.6`, không `-trimpath` và
  ghi giờ lúc chạy vào `BuildDate`, nên artifact đó, nếu do workflow ấy dựng, **dự đoán** sẽ khác (chưa đo); (5) nền tảng
  khác: chỉ darwin/arm64 trên một máy, chưa có pin Linux/Windows; (6) `BuildDate` mô tả điều gì. Các câu cũ "dựng từ nguồn
  (`-trimpath`)" nay đúng ở mức (c) này và không hơn. **Quyết định D-OCR-1 (mở, backlog V21-86):** có tải artifact phát
  hành, `sha256sum.txt` và attestation của upstream để so không? Chỉ thị 2026-10-15 mục 5 chỉ cho tải nguồn và module.

### 8.4 PM-8 — điều probe thấy, cho người vận hành

*2.0.0 và trước cửa sổ:* bản ghi probe niêm phong, journal và mọi prompt chỉ nói `{behavior_verdict: REFUTED}`; bước, tệp:dòng và lớp
ngoại lệ làm nên verdict chỉ có trong `Observation` (chủ dự án duyệt phương án B, chỉ cho người vận hành). *Nay:* mỗi lần
đánh giá probe **đã thực thi** mà verdict không phải cái contract kỳ vọng (và không phải trạng thái đầu vào mà bảng định
tuyến chờ ở parent: INTRODUCE ⇒ verdict xác định hoặc `PRECONDITION_ABSENT`; VERIFY ⇒ verdict xác định) để lại một tệp
`<out>/probe-observations/<story>.<attempt>.p<n>.json` (một proof) hoặc `….r<n>.json` (một reproducer của review); một
`UNRUNNABLE`/`INVALID_SPEC` không được ghi ở đây vì `detail` của nó đã nằm trong `probe/evaluated`.

- **Tệp giữ:** loại quan sát, verdict, `detail` đã parse (bước, tệp:dòng, tên lớp ngoại lệ — không phải thông điệp),
  verdict kỳ vọng, danh tính của bản ghi mà journal giữ (story, spec, probe, digest, revision, enforcement, result) và các
  tiêu chí mà spec trả lời. Tạo một lần, ghi nguyên cả tệp rồi đổi tên; nằm trong manifest bằng chứng; `--verify` đối
  chiếu từng tệp với một dòng `probe/evaluated` (một tệp lạ, bị sửa hay lệch số đếm làm **xác minh** `REFUTED`, không đổi
  verdict giao hàng mà journal cho). RUN.json có khoá `diagnostics` (`dir`, `audience`, `access`, `permissions`,
  `authority`, `written`, `not_written`, `failures`, `dropped`, `limits`). Một tệp không ghi được chỉ được đếm và nêu tên
  (fail-open); một sibling `<tên>.json.tmp` do lần ghi lỗi để lại là một ghi chú, không bị xoá.
- **Che bí mật:** mọi chuỗi (cả khoá) thay giá trị bí mật **của run** bằng `REDACTED` — giá trị của các biến `client_env`
  và khoá API từ 8 ký tự, kể cả dạng đã escape trong JSON. **Chỉ** những giá trị đó: không có bộ dò bí mật nào khác, nên
  một chuỗi trong mã sản phẩm trông như bí mật sẽ nằm nguyên trong `detail`. `detail` cắt ở 8192 ký tự (`elided`,
  `detail_chars`); tối đa 500 tệp mỗi run (`dropped`).
- **Ai đọc được — giới hạn cùng user:** thư mục tạo 0700 và tệp 0600 (nơi nền tảng có chế độ): chỉ ràng buộc người dùng
  khác, không ràng buộc chính người vận hành. Không cách ly: mọi tiến trình của user, **gồm phiên developer**, đọc được;
  RUN.json và từng tệp ghi `same-user, not enforced`. Có cách ly: phiên model không mount thư mục (`access_of` suy từ dòng
  lệnh bubblewrap), nhưng test của developer và candidate dưới probe do kernel chạy bằng user của người vận hành và
  **không** bị cách ly. Việc "phiên model không thấy thư mục" mới được suy từ dòng lệnh, chưa được đo bằng bwrap thật.
- **Không thêm thẩm quyền quyết định:** không verdict giao hàng, retry, ngân sách, merge hay định tuyến nào đọc thư mục;
  không prompt developer nào nêu nó (test cấu trúc `tests/v2/test_v21_pm8_diagnostics.py`); không đổi probe, kernel,
  `ProbeResult`/`ProbeRecord`, digest, hiệu chuẩn hay định dạng journal. `aisef run` không in thư mục này ở stdout
  (backlog V21-72).

### 8.5 Nối tiếp (lineage)

Hành vi người dùng thấy: §5. **Đợt đầu của cửa sổ:** trạng thái `UNREAD`, mã `EVIDENCE_*`, `--expect-anchor`,
`bundle continue` hợp lệ đúng như `--verify`, `run --parent` từ chối thay vì traceback. Phạm vi: `child_state`/`claim`/
`claims`, `bundle continue`, `account_of`; `lineage.events_of` không từ chối một journal mà các projection từ chối (nó chỉ
dựng lại journal bằng `format3.reconstruct`, không qua projection nào; hai nơi gọi nó là `account_of` và `usage_lineage`,
tức chi tiêu). Lý do ghi lúc duyệt, "`child_state` dùng nó để kết luận đã bắt đầu", không còn mô tả mã: `child_state` tự
đọc journal trong `child_evidence`. Lý do còn lại là của `account_of`: nó cần thấy các request mà journal ghi (đọc mã,
chưa đo). `repair` giữ nguyên.

**Đợt hai, lane `lineage-proof`** (chỉ thị 2026-10-15, mục 2: giữ bản sửa "unknown ≠ 0" — journal không đọc được thì chi phí
là chưa xác định, không được thành 0 hay số đã đối soát; giữ phân biệt giữa chi phí đã biết của một phần dòng dõi và tổng
chi phí chưa xác định; không thay đổi lịch sử, không tự giải phóng claim, không cho mở phiên trả tiền mới bằng cách bỏ qua
phần chưa đối soát). Commit `3b738a4`, `e3fc210`, `286d511`; test `tests/v2/test_v21_x_lineage_proof.py`.
- *Chi phí chưa xác định ở mọi đầu ra:* một journal, ledger preflight hay luồng phiên có mà không đọc được; một journal đọc
  được nhưng không phải cái `RUN.json` nêu (`_journal_mismatch`: digest và số dòng); một record hay claim không đọc được,
  hỏng hoặc là liên kết hỏng; một run tổ tiên mà record nêu nhưng thư mục đã mất ⇒ `unread`, `exact: false`, `total: null`,
  `cost` `null`. Các đầu ra: `lineage.account_of` / `lineage_account` (`unread`, `exact` từng run, `total`),
  `usage_lineage` (`cost`, `tokens_status`), `RUN.json` `continues.account` và `lineage_usage`, `Budget` (nếu lineage có
  `unread` thì báo `unaccounted` và dừng mọi việc, không bao giờ tính theo `cap − known`), `aisef run --verify` (`REFUTED`
  với lý do), báo cáo của `aisef bundle continue` (`spend`, `spend_by_run`, `unread`, `run_parent_refused`).
- *`aisef run --parent` từ chối (exit 2) trước clone, admission và preflight, bất kể cờ* (`--accept-unaccounted`,
  `--supersede-claim`, cả hai): cổng ở `run.execute` đứng ngay sau `lineage.claim` và trước bước `repository`. Phần chi tiêu
  đã biết của từng run vẫn còn nguyên và quy được về run đó.
- *Lịch sử không bị viết lại:* các dòng mà `lineage.py`, `run.py`, `verify.py`, `client.py` và `cli.py` thêm từ `f69124c`
  không chứa lệnh xoá, đổi tên, ghi đè, cắt hay kill nào (đo bằng grep); chỗ ghi duy nhất của `lineage.py` vẫn là `claim()`
  (`O_EXCL|O_NOFOLLOW`) và `write_anchor`. Một lượt bị từ chối sau claim để lại bản ghi riêng của nó và một thế hệ claim
  (nối thêm). Test chụp mọi byte của cây lineage trước và sau một từ chối.
- *Chưa nằm trong registry mutation:* các hàm mới `lineage._journal_mismatch`, `_is_a_directory`, `_predecessor`,
  `unread_runs` (người xác minh đặt 8 mutant tay trên các luật chính, cả 8 bị test của lane giết; chưa đo bằng chiến dịch).

Hai thay đổi ngoài văn bản chủ dự án duyệt lúc đầu (backlog V21-55): `account_of` (commit `4d245f4`) — **chủ dự án đã xác
nhận giữ** bằng chỉ thị 2026-10-15 mục 2 — và `RUN.json` không phải UTF-8 (từ "rơi xuống `RUN.started.json`" sang
`EVIDENCE_MALFORMED`), còn chờ xác nhận.

**Quyết định của chủ dự án còn mở** (tài liệu này không quyết; mỗi hàng có mã ở backlog):
- **R2 — bằng chứng *thiếu* cạnh một journal đọc được (V21-77).** **[ĐANG HOÀN THIỆN — quy tắc cho trường hợp này đang
  được một lane khác làm; người điều phối sẽ mô tả nó ở đây khi xong. Tài liệu này chưa mô tả.]**
- **R3 — child của một claim bị thay thế mà thư mục đã mất, và tổ tiên đã bị xoá hay lưu trữ (V21-78).** Hiện: child mà
  một claim bị thay thế nêu và thư mục đã mất vẫn là `UNBEGUN` (0, không `unread`) vì `ClaimLifecycle` của
  `test_v21_continue_integrity` ghim "child vắng = `UNBEGUN`, bị thay thế, run đi tiếp"; còn một run mà *record* nêu là run
  nó nối tiếp mà thư mục đã mất thì là `unread`. Hệ quả: một tổ tiên đã bị xoá hay lưu trữ nay chặn `--parent` vĩnh viễn,
  không cờ nào qua. Phương án child: (A) giữ `UNBEGUN`; (B) coi là `unread` (phải đổi 2 test của `ClaimLifecycle` — child
  vắng, và claimant còn sống hay ở máy khác; thử áp dụng thì 3 mục của chúng đỏ). Phương án chuỗi: giữ `unread` (an toàn),
  hoặc thêm một cờ khẳng định có ghi lại (kiểu `--assume-spent-nothing PATH`), rõ ràng là lời của operator.
- **R4 — `--accept-unaccounted` trên chi tiêu đọc được là đã gửi mà chưa trả lời (V21-79).** Hiện (ADR-8): một request
  đang bay khi run bị giết mà luồng phiên đọc được ⇒ chi phí unknown; `--accept-unaccounted` mở phiên, trần tính theo `cap
  − known`, ghi `continues.accepted_unaccounted` và `budget.inherited_unaccounted`, `total` là `null`, `--verify` ghi chú
  "accepted by name". Chữ của chỉ thị 2026-10-15 mục 2 nói về journal không đọc được, không về trường hợp này; theo chữ
  "không cho mở phiên trả tiền mới bằng cách bỏ qua phần chưa đối soát" đây là đường còn lại. Phương án: (A) giữ như
  ADR-8; (B) cấm luôn khi `total` chưa biết (đảo pin ở `test_v21_continue_usage` / `test_v21_pw_lineage_spend` và câu của
  ADR-8) — nhưng một run bị giết giữa chừng gần như luôn có request đang bay, nên `--parent` không còn nối được run bị
  giết, là mục đích của tính năng; (C) cho cờ nhưng bắt khai cận trên cho phần chưa biết (ví dụ `--unaccounted-bound N`) và
  trừ vào trần: `remaining = cap − (known + N)`. Lane đề xuất C nếu chủ dự án muốn đóng hẳn, A nếu không.
- **R5 — thứ tự claim rồi mới tới cổng (V21-80).** Hiện (luồng chủ đã duyệt 2026-10-15, vòng 2): `aisef run --parent` lấy
  claim *trước*, rồi cổng `unread` từ chối; lượt bị từ chối để lại một thế hệ claim trên tiền nhiệm (với `--supersede-claim`
  là lời khẳng định của operator, được ghi). Tái hiện của người xác minh: (1) chạy thường ⇒ từ chối, 0 request; (2)
  `--supersede-claim <sha>` ⇒ từ chối, 0 request, tiền nhiệm có thêm `CONTINUED-BY.2.json`; (3) khôi phục journal của child
  (nay `BEGUN`) rồi chạy thường ⇒ chạy, `PASS`, 3 request preflight, và dòng dõi đếm child như một anh em bị thay thế (chi
  tiêu của nó vào trần) — tức một continuation chạy dù có child `BEGUN`. Phương án: (A) giữ; (B) cổng trước claim: lượt bị
  từ chối không ghi gì vào tiền nhiệm, nhưng `--supersede-claim` lên một child `UNREAD` vô nghĩa cho tới khi child đọc được
  (khi đó hoặc `BEGUN` ⇒ không thay, hoặc `UNBEGUN` ⇒ thay bằng bằng chứng); (C) giữ khẳng định nhưng `claim()` kiểm lại
  mọi thế hệ bị thay thế bằng khẳng định: nếu child nay đọc ra `BEGUN` thì từ chối "tiếp tục từ nó". Lane đề xuất B hoặc C.

### 8.6 PM-5 — mã của chủ thể trả lời hộ chính nó (mô tả một giới hạn, không phải chấp nhận rủi ro)

Kênh của probe do controller giữ và được xác thực (HMAC); điều bị giả được là **nội dung** của những câu trả lời mà tiến
trình của chủ thể đưa về chính nó: mã thoát, giá trị trả về, ngoại lệ được ném. Mã của ứng viên chạy trong tiến trình đó.
Đo (`closure-evidence/v2/v2.1/round-3/probes/repro-5.py.txt`, `repro-5.out`): với một sản phẩm có `main()` raise và
`compute() == 999`, đối chứng trung thực cho `REFUTED` ×3; một mô-đun ứng viên viết để ghi đè `__main__.OPS`/`send` cho
`SATISFIED` ×3 (`cli_invocation` `exits {exit_code: 0}`, `process_effect` `returns 1`, `python_callable_v2` `returns 1`).
Lượt đo sau (ứng viên không đụng tên giao thức nào, chỉ đọc `sys.flags.isolated` — cờ `-I` mà probe luôn bật) cũng
`SATISFIED` ×3, và kết quả y hệt trên cây nguồn của tag `v2.0.0` (OWNER-DECISIONS-2026-10-15.md, PM-5; đo trên cây nguồn,
không phải wheel trên PyPI). Nghĩa là câu "mã đang bị kiểm không thể tự chế ra kết quả đạt" quá rộng: mã đó không viết được
verdict hay kênh của nó, nhưng khai sai được về chính nó.

- **Người vận hành thấy:** `delivery_verdict` PASS, `aisef run --verify --expect-anchor` in `VERIFIED`, journal ghi `COMMIT`.
  **Người dùng cuối** cài sản phẩm và chạy thì gặp traceback hay mã thoát 1. Bản ghi probe chỉ giữ verdict — không có mã
  thoát mà chủ thể đã khai — nên người vận hành không thấy dấu vết nào. Reviewer chạy cùng probe cho reproducer, nên một
  finding thật cũng có thể không được `CONFIRMED` (đọc mã, chưa đo).
- **Tần suất: chưa đo.** Quan sát được 0 trường hợp: 3 phiên developer của attempt 4 chạm tới tài liệu của probe — một đọc nguồn
  (`process_effect.py`, 47.255 ký tự), một đọc scratch của probe (`request.json`, `protocol.log`), hai tìm probe trên máy
  (một trong hai là phiên đọc scratch) — và không phiên nào đổi gì (`DEVELOPER-CONFINEMENT-GAP-001` mục 1, 4, 5 và 7);
  trong 4 phiên developer của canary tier 2 và 2b (1 + 3), 0 dòng nhắc `aisef2/probe`, `OPS`, `request.json` hay
  `protocol.log` (đếm bằng grep). N nhỏ, workload tầm thường: không phải bằng chứng vắng mặt.
- **Biện pháp thật nằm ở chỗ khác:** không cho developer đọc probe và máy chủ (V21-02, B-07, F), review độc lập. Một thiết
  kế chạy sản phẩm đúng như người dùng chạy là việc khác hẳn, không thuộc 2.1.
- Docstring của `cli_invocation`, `process_effect`, `python_callable_v2` và hằng `WEAKEST_PATH` đã được sửa ở `f69124c`
  (không đổi hành vi; giữ cụm "isolation, not a sandbox" mà test ghim). Các câu công khai "the code under test cannot
  manufacture a passing result" được sửa sau đó, ở `5f6b7e9` (`README.md`, `README.vi.md`, `docs/v2/USAGE.md`,
  `docs/v2/USAGE.vi.md`, `landingpage/index.html`) và `7b029e6` (`docs/SALEKIT.html`): chúng nay nói bảo đảm là về kênh,
  không về giá trị mà chủ thể khai (backlog V21-26).

### 8.7 Spec và approval bị ảnh hưởng

| Thay đổi | `CAPABILITY_VERSION` / digest | spec id | verdict có thể đổi | hiệu chuẩn |
|---|---|---|---|---|
| PM-9 (và PM-3/4/11/13 cùng tệp) | `file_artifact` 2 → 3 (`DIGEST` đổi) | đổi, một lần | có, ở ba lớp dưới đây (PM-9; PM-11; PM-3/PM-13) | 4 hàng `file_artifact` |
| PM-1, PM-2, PM-6, PM-7, họ RV-1 | giữ 1 (`DIGEST` không đổi); `EXECUTION_DIGEST` của 3 probe đổi (và của `file_artifact`, dòng trên) | không đổi | PM-2: tổ hợp bị từ chối; PM-1: layout trước `UNRUNNABLE` nay quan sát được | 15 hàng (cli 5, process_effect 3, python_callable_v2 7) |
| đợt hai: khai báo `CAPABILITY_CHANGES` và `_compiles` (`file_artifact.py`), worker regex (`cli_invocation.py`) | `CAPABILITY_VERSION` và `DIGEST` không đổi (3, 1, 1, 1); `EXECUTION_DIGEST` của **cả bốn** probe đổi nữa (đo trên `3e1e83a`: `file_artifact` `d0630797…`, `python_callable_v2` `042fe41e…`, `cli_invocation` `82d95f1f…`, `process_effect` `c3ea1ca6…`; `file_artifact` và `cli_invocation` vì chính tệp của chúng đổi, còn `process_effect` và `python_callable_v2` vì `probe/cli_invocation.py` nằm trong `PROBE_SOURCES` của cả hai — đo bằng `grep` và bằng import) | không đổi | chỉ ở đầu vào mà trước là một exception hay một lần treo: regex không kết thúc ⇒ `UNRUNNABLE`; pattern làm `re.compile` raise `OverflowError`/`RecursionError` ⇒ không có nghĩa | cùng 19 hàng, phải chứng minh lại một lần cho các byte cuối. Văn bản `CAPABILITY_CHANGES` nằm trong `EXECUTION_DIGEST` của `file_artifact`: sửa lời về sau lại làm cũ hiệu chuẩn |

**Lớp contract mà verdict có thể đổi (PM-9):** contract `file_artifact` ở lớp `grep_count` hoặc `python_imports` mà đường
dẫn có thể chọn ra 0 tệp. Với `subject_absence: REQUIRES_SUBJECT`: `SATISFIED` (matches 0) hoặc `REFUTED` (matches ≥ 1)
đổi thành `INDETERMINATE(PRECONDITION_ABSENT)`. Với `ABSENCE_IS_DECIDABLE`: verdict giữ nguyên, chỉ nhãn quan sát đổi
sang `SUBJECT_ABSENT`. Lớp `exists`/`content` không đổi.

**Lớp thứ hai (PM-11, `grep_count`):** mẫu có neo đầu dòng (`^`, tác dụng ở dòng 1) hoặc nêu U+FEFF, trên một tệp được chọn
mà byte đầu là BOM UTF-8. Trước cửa sổ (và ở 2.0.0) dòng 1 mang U+FEFF nên `^from …` không khớp ở dòng đó — một nghĩa vụ `matches: 1` thấy 0 và
`REFUTED`; nay khớp. Ngược lại một mẫu cấm BOM (`matches: 0`) trước bắt được BOM, nay không bao giờ khớp (`SATISFIED`; muốn
cấm BOM phải nêu trên byte, bằng `content`). Với `python_imports`: một tệp có BOM trước `REFUTED` (`unparsable`), nay được
đếm. Trong kho, `BC-V22-S-10-a`, `S-10-b`, `S-10-c` và nhánh đầu của `S-12-a`, `S-12-b` có neo `^`; không spec, bản nháp
hay tệp ví dụ nào nêu hoặc mang U+FEFF (đếm byte `EF BB BF` và `\ufeff` trong `calc-*`, `LEDGERLOCK-PROJECT.json` và bản
nháp: 0). **Chưa đo:** tệp `.py` của LedgerLock có BOM hay không (cây đó không nằm trong kho).

**Lớp thứ ba (PM-13, PM-3):** `grep_count` có vòng khớp chạy quá `timeouts_s.probe` (mẫu lồng lượng từ hoặc đầu vào lớn):
trước cửa sổ là treo hoặc `REFUTED` muộn, nay `UNRUNNABLE`; `python_imports` trên tệp lồng sâu tới mức parser dừng: trước là
một exception, nay `UNRUNNABLE`. Mẫu `grep` của LedgerLock không có lượng từ lồng nhau (đọc mẫu, chưa đo trên cây thật).

| Nơi kho giữ | Gì | verdict có thể đổi | approval |
|---|---|---|---|
| `closure-evidence/v2/release/LEDGERLOCK-PROJECT.json` | bundle 2.0.0 của LedgerLock; 9 contract `file_artifact`: `BC-V22-S-10-a`, `S-12-a`, `S-12-b`, `S-12-c` (`grep_count`, `matches: 0`, `REQUIRES_SUBJECT`, `path:ledgerlock`, `.py`) thuộc lớp PM-9; `S-10-b`, `S-10-c` (một tệp, `matches: 1`) và `S-13-a/b/c` (`exists`) thì không thuộc lớp PM-9 | PM-9: chỉ khi `ledgerlock/` không chọn ra `.py` nào (hôm nay có). PM-11: `S-10-a/b/c`, `S-12-a/b` (neo `^`) chỉ khi một tệp `.py` được chọn có BOM đứng đầu (chưa đo) | `migrate` (đợt hai) mang 53 trong 59 approval theo luật danh tính và **giữ lại** approval của sáu contract (`S-10-a`, `S-10-b`, `S-10-c`, `S-12-a`, `S-12-b`, `S-12-c`) khỏi ứng viên — bộ chọn không thấy đường dẫn nên chọn cả `S-10-b`, `S-10-c` (§2); bundle gốc và approval của nó không bị sửa; duyệt lại là việc của chủ dự án |
| `closure-evidence/v2/v2.1/P5-PLAN-V2.2-PROPOSAL.json`, `closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json`, `closure-evidence/v2/v2.1/PLAN-V2.2-CORRECTION-1.json` | cùng 4 contract và 5 contract không bị ảnh hưởng của kế hoạch PLAN-V2.2 | như trên | `closure-evidence/v2/cycle2/P5-CONTRACT-APPROVALS.json`: 59 approval `human:owner` (2026-09-30); `binds` nêu `proposal_digest`, `plan_hash`, baseline, bản ghi đề xuất và candidate: `proposal_digest` và `plan_hash` đổi khi spec id đổi (đề xuất và kế hoạch nêu 59 spec id PPS). `spec_id` của mỗi approval là mã tiêu chí `S-*`, không phải spec id PPS, và nằm ngoài bảy trường của digest approval, nên không đổi; cửa sổ không dựng lại và không di trú chúng sang digest mới |
| `aisef2/app/examples/calc-3-stories.json` | `BC-STDLIB`: `python_imports` trên `path:app`, `matches: 0`, `REQUIRES_SUBJECT` (ví dụ sống) | chỉ khi `app/` không còn `.py` (canary 2b chạy mẫu này trên lựa chọn không rỗng: không bị ảnh hưởng) | ví dụ không mang approval của chủ dự án |
| `docs/v2.1/drafts/LEDGERLOCK-BC-V22-S-10-a-r2.DRAFT.json` | bản nháp r2 của `BC-V22-S-10-a`: hai contract `python_imports` `REQUIRES_SUBJECT`, `matches: 0` | như trên | bản nháp chưa duyệt (B-04) |

Không bị ảnh hưởng: các fixture hiệu chuẩn `tests/v2/fixtures/calibration/file_artifact/*` (verdict không đổi; chỉ bản
ghi hiệu chuẩn buộc `EXECUTION_DIGEST` nên phải sinh lại) và các spec `exists`/`content` còn lại. Bundle 2.0.0 ngoài kho
(đã phát hành trên PyPI) và dự án ngoài kho không quét được: một ghi chú phát hành cần nói rằng lựa chọn rỗng của một
lệnh cấm `REQUIRES_SUBJECT` nay là `INDETERMINATE`.

**Cửa sổ này không duyệt lại và không thu hồi approval nào của kho, và không di trú approval PM-9 nào sang digest mới.**
Một `ContractApproval` buộc `requirement_hash` và `contract_hash`, không buộc probe, nên một bundle được buộc lại vẫn báo
`approved` cho contract mà quan sát của nó vừa đổi nghĩa nếu approval ấy còn trong bundle: `lint`/`explain` không có cơ chế
đánh dấu approval cũ (có nên có không: backlog V21-61). Đợt hai thêm một cơ chế **ở lúc di trú, không ở lúc đọc**:
`migrate` và `seal --keep-approvals-from` không còn mang approval của contract mà một thay đổi capability đã khai báo chọn
trúng (§2). Duyệt lại (`aisef bundle approve`, trên digest mới) là **việc của chủ dự án**, không phải của bất kỳ lệnh nào ở
đây: sáu contract của LedgerLock ở §2 nếu chủ dự án chấp nhận sáu (D-1).
