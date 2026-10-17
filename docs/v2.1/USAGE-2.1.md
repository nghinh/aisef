# AISEF 2.1 — Hướng dẫn sử dụng và di trú từ 2.0.0

Áp dụng cho nhánh `v2.1/foundation` (`2.1.0.dev0`, **chưa phát hành**). Mọi lệnh dưới đây không gọi provider, trừ
`aisef run` không kèm `--check`/`--verify`.

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
Ví dụ 3 story (hai loại probe, hai obligation PRESERVE): `--example calc-3-stories`. Định dạng soạn:
[`bundle-authoring.schema.json`](bundle-authoring.schema.json). Mọi lệnh `aisef bundle` viết **tệp mới**, không bao giờ
ghi đè; mã thoát 0 xong / 1 lint NOT_READY / 2 từ chối.

## 2. Di trú bundle 2.0.0

Spec id đổi một lần (ba danh tính, [ADR-2](ADR-V2.1.md)). Bundle 2.0.0 nạp vào 2.1 bị từ chối với gợi ý:
```bash
aisef bundle migrate old-2.0.0-bundle.json --out migrated.json
```
Chỉ `plan` được buộc lại theo contract đã duyệt của chính nó; requirement, contract, approval, facts không đổi; không
cần duyệt lại. Một obligation mà không bản phát hành nào biết đến bị từ chối, không đoán.

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
  REVIEW, nội dung được đưa cho developer ở lượt sau. Mọi finding khác (không tái hiện, không neo được, mâu thuẫn với
  contract đã duyệt) chỉ được ghi lại để người phân loại.
- Reproducer trích mệnh đề theo dạng `<requirement>/<clause>` như danh sách mệnh đề (ví dụ `R-9/3`, `R-ADD/1.1`).
- `finder` vắng hoặc `"model"` ⇒ reviewer là phiên mô hình như 2.0.0. `"ocr"` ⇒ Open Code Review v1.12.12 (binary
  theo đường dẫn tuyệt đối, kiểm sha256 trước mỗi lần chạy): preview rồi review đúng thay đổi của story; coverage do
  AISEF kiểm. Review không phủ hết candidate (partial, hết thời gian, hết token budget của nó, schema manifest không hỗ
  trợ) ⇒ dưới `fix-loop` story không được commit (CAPABILITY_UNRUNNABLE; lỗi provider ⇒ PROVIDER_UNAVAILABLE); dưới
  `advisory` chỉ ghi lại. Một lượt OCR bị dừng vì hết giờ có chi phí không xác định ⇒ ngân sách "unaccounted", run
  không mở thêm phiên trả tiền nào.
- Với `finder: "ocr"` (dưới `fix-loop` cũng như `advisory`: binary hỏng lúc dùng kết thúc mọi story), `aisef run` hỏi
  binary **trước mọi việc khác** — trước khi nhận kế thừa (`--parent`), clone, mở phiên developer hay gửi request
  provider. Ba điều phải đúng, theo thứ tự: `review.ocr.exe` là đường dẫn tuyệt đối đọc được; sha256 của nó bằng
  `review.ocr.sha256`; `<exe> version` (môi trường sạch, có giới hạn thời gian) in dòng phiên bản của Open Code Review
  v1.12.12 (182898c). Sai ⇒ từ chối trước khi chạy: mã thoát 2, không phiên nào được mở, không request nào được gửi;
  thông báo nêu check nào hỏng, giá trị mong đợi, giá trị quan sát và việc operator cần làm. Thư mục `--out` của lượt bị
  từ chối được giữ làm bản ghi và không bao giờ dùng lại ⇒ lượt kế tiếp cần `--out` mới. Hai lối ra: sửa pin (chỉ sau khi
  kiểm binary với [BUILD-RECIPE.md](../../validation/v21/ocr/BUILD-RECIPE.md)), hoặc bỏ `review.ocr` và đặt
  `finder: "model"` — một reviewer khác.
- `aisef run --check` hỏi binary theo cùng cách, in khối `ocr_identity` và `ready: false` (mã thoát 2) nếu binary không
  qua. `RUN.json` của một lượt có `finder: "ocr"` có khối `ocr_identity` nói đã thiết lập được gì:
  `sha256_matches_pin` (byte là pin của operator), `declared_matches_release` (binary **tự khai** đúng bản — lời
  tự khai, không phải bằng chứng dựng) và `build_provenance`, luôn là `NOT_ESTABLISHED`. Đây là lần nhìn sớm, **không
  thay** cổng lúc dùng: giai đoạn review kiểm lại cả hai ngay trước mỗi lần review, nên một binary bị thay giữa chừng bị
  từ chối ở đó.
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
- Thư mục: `<out>/test-python` (venv cho test của developer; probe **không** chạy trên nó), `<out>/EVIDENCE.json`,
  `<out>/review-findings/` (mỗi finding của reviewer, đầy đủ và đã che bí mật của run; dòng journal chỉ giữ bản tóm tắt
  ≤ 1.500 ký tự, nêu đường dẫn, sha256 và kích thước của tệp; `--verify` đối chiếu).

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
  **unknown**. Khi dòng dõi có chi phí unknown, `aisef run --parent` không mở phiên trả tiền nào (từ chối trước preflight)
  trừ khi người vận hành nêu `--accept-unaccounted` — danh sách được ghi vào `continues.accepted_unaccounted`; tổng chi
  phí dòng dõi khi đó là `null`. Chi tiêu đã biết của dòng dõi tính vào trần ngân sách của run mới (nối tiếp không bao giờ
  đặt lại ngân sách: muốn chạy tiếp một run đã chạm trần thì nâng trần trong settings — một quyết định tường minh).
- **Một run được nối tiếp một lần — quyết định bằng bằng chứng.** `--parent` tạo độc quyền `CONTINUED-BY.json` *trước*
  request provider đầu tiên (run thua cuộc đua không tiêu gì — đã đo). Tạo độc quyền chỉ chứng minh một tiến trình thắng
  lúc tạo, nên một claim có sẵn được đối soát: child đã bắt đầu (journal có sự kiện) ⇒ từ chối, nối tiếp từ child, không
  bao giờ thay thế kể cả khi người vận hành yêu cầu; child kết thúc mà chưa bắt đầu, hoặc chưa bắt đầu và claimant chắc
  chắn đã mất (cùng máy, pid không còn hoặc là tiến trình khác theo thời điểm khởi động) ⇒ một thế hệ claim mới
  (`CONTINUED-BY.<n>.json`) thay thế, ghi bằng chứng; claimant còn sống, ở máy khác, hoặc không đọc được ⇒ từ chối, chỉ
  thay thế khi người vận hành nêu sha256 của claim (`--supersede-claim`, ghi là khẳng định của họ). Không xoá gì; không khoá
  vĩnh viễn: luôn có một đường đi tiếp có ghi nhận.
- **Run bị giết vẫn nối được.** `RUN.started.json` được ghi (fsync) một lần trước mọi việc; thiếu `RUN.json` thì
  `continue` đọc nó, báo `recorded: false`.
- **Không commit/merge lặp, không mất nghĩa vụ, chi phí mỗi run một lần.** Sau mỗi cửa sổ: mỗi story commit đúng một lần
  trong dòng dõi, số merge trên main cuối = số story đã giao, mọi nghĩa vụ được giao hoặc chứng minh lại, `lineage_usage`
  = mọi luồng phiên của dòng dõi đúng một lần (kể cả run bị thay thế), `usage` = chỉ của chính run.
- **Tiến trình của run bị giết** (đo cho đúng trường hợp đã đo): các tiến trình probe được nhận diện theo process group
  (và pid của chính candidate) — tất cả mất ngay sau kill: watchdog của range anchor giết cả nhóm khi controller mất. Một
  hậu duệ **tự tách nhóm** (`setsid`) **không** bị kiểm soát: nó sống quá run bị giết (đã đo); trong một run bình thường nó
  bị phát hiện là "escaped" (tests/v2/p4/test_process_range). Không có cách ly OS thì AISEF không tuyên bố kiểm soát nó.

Khác với resume tại chỗ: không có gì của `run1` được chạy tiếp hay ghi thêm vào journal của nó; `run2` là một lượt chạy
mới, journal mới, bắt đầu từ commit cuối đã xác nhận — công việc đang dở trong `run1` (một phiên, một merge chưa commit)
được làm lại từ đầu, và chi phí của nó vẫn được tính trong dòng dõi.

## 6. Thay đổi có thể làm hỏng quy trình cũ

| Thay đổi | Ảnh hưởng | Việc cần làm |
|---|---|---|
| spec id (ba danh tính) | bundle 2.0.0 bị từ chối | `aisef bundle migrate` |
| `<out>/probe-python` → `<out>/test-python` | script đọc đường dẫn cũ | đổi tên; probe chạy trên interpreter của aisef |
| `--check` clone repo như lượt chạy thật | một khoá git không "inert" trong repo của bạn không còn làm `--check` báo sai lý do | không |
| endpoint `http://` chỉ cho loopback (phân tích host thật) | `http://localhost.evil.example` bị từ chối | dùng https |
| preflight không theo redirect | endpoint trả 3xx ⇒ OPAQUE | dùng URL cuối cùng |
| phiên bản `2.1.0.dev0` | gate phát hành từ chối mọi bản dev | đúng chủ ý |

## 7. Giới hạn đã biết (đừng hiểu quá)

- Không có sandbox: developer và mã test chạy dưới user của người vận hành (V2-05 mở).
- `--verify` không có anchor chỉ chứng minh nhất quán.
- Review CONFIRMED không chứng minh người review đọc đúng yêu cầu.
- OCR đã nối vào `aisef run` và đã chạy **nhị phân thật** (build từ commit đã ghim) với một mô hình giả trên loopback;
  chưa chạy với mô hình thật (cần ngân sách).
- Neo kỳ vọng là quy tắc cơ học trên contract đã duyệt: nó không quyết định được một stimulus **mới** có thuộc điều kiện
  của mệnh đề hay không (giới hạn đã đo bằng test).
- Chưa có số đo hiệu quả so với agent chạy trực tiếp — xem [EXPERIMENT-PLAN.md](EXPERIMENT-PLAN.md).
