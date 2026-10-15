# AISEF 2.1 — Hướng dẫn sử dụng và di trú từ 2.0.0

Áp dụng cho nhánh `v2.1/foundation` (`2.1.0.dev0`, **chưa phát hành**). Mọi lệnh dưới đây không gọi provider, trừ
`aisef run` không kèm `--check`/`--verify`.

Mục 8 và các ghi chú "cửa sổ probe" mô tả cây ứng viên `v2.1/probe-window` (2026-10-15): *đã làm trên nhánh ứng viên, bằng
chứng đo (hiệu chuẩn lại, mutation, suite đầy đủ) chưa có*. Đó không phải bản phát hành và chủ dự án chưa nghiệm thu
(REPORT §0.9).

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
probe.python_callable_v2@0821c14651a9 executing 58757ffe759c class 'returns'`; đo trên `f69124c`).

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

Cửa sổ probe nâng `CAPABILITY_VERSION` của `file_artifact` từ 2 lên 3 (PM-9, §8.1): spec id của mọi spec `file_artifact`
đổi thêm một lần. `migrate` chỉ biết bản 2.0.0 (`bundle_cli.RELEASES`): bundle 2.0.0 vẫn được buộc lại. Một bundle có spec
`file_artifact` niêm phong bằng một checkout ứng viên *trước* cửa sổ nêu spec id mà không bản phát hành nào biết: `lint`
báo kiểm tra `load` (`the plan names 1 spec(s) no approved contract compiles to under this release's probes: […] — a
bundle of an earlier release: `aisef bundle migrate``) và chính `migrate` từ chối (`refused: 1 obligation(s) name a spec no
known release (2.0.0 or this one) compiles from the bundle's approved contracts: ['C-STDLIB-1']`) — đo trên `f69124c`
với `calc-3-stories` niêm phong ở `2d01fe4`. Lối ra: niêm phong lại từ tệp soạn bằng
`aisef bundle seal … --keep-approvals-from OLD` (đo lúc viết, đầu ra không được lưu: `approvals_kept: 4`, `approvals_dropped: []`; tái lập bằng đúng lệnh này trên bundle
`calc-3-stories` niêm phong ở `2d01fe4`).
**Cửa sổ không di trú, không thu hồi và không duyệt lại một approval nào** (§8.7): approval buộc `requirement_hash` và
`contract_hash` chứ không buộc probe (`product/approval.py::binding_problems`), nên `migrate` và `seal --keep-approvals-from`
giữ chúng và `lint`/`explain` vẫn báo `approved` cho một contract mà quan sát của nó vừa đổi nghĩa. Bốn lớp contract bị ảnh
hưởng và nơi kho giữ chúng: §8.7. Duyệt lại (`aisef bundle approve`) là việc của chủ dự án.

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
  theo đường dẫn tuyệt đối; **trước mọi lệnh review** AISEF kiểm sha256 rồi hỏi chính binary `version`, §8.3): preview rồi
  review đúng thay đổi của story; coverage do AISEF kiểm. Review không phủ hết candidate (partial, hết thời gian, hết
  token budget của nó, schema manifest không hỗ trợ) ⇒ dưới `fix-loop` story không được commit (CAPABILITY_UNRUNNABLE;
  lỗi provider ⇒ PROVIDER_UNAVAILABLE); dưới `advisory` chỉ ghi lại. Một lượt OCR bị dừng vì hết giờ có chi phí không xác định ⇒ ngân sách "unaccounted", run
  không mở thêm phiên trả tiền nào.
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
  **unknown**. Khi dòng dõi có chi phí unknown, `aisef run --parent` không mở phiên trả tiền nào (từ chối trước preflight)
  trừ khi người vận hành nêu `--accept-unaccounted` — danh sách được ghi vào `continues.accepted_unaccounted`; tổng chi
  phí dòng dõi khi đó là `null`. Một journal của run **có mà không đọc được** (đó là nơi các request provider được ghi) cũng
  là chi phí unknown, liệt kê kèm nguyên nhân — không phải "0 request đã biết"; `aisef run --parent` dừng ở `the lineage
  of … has spend no evidence accounts for` cho tới `--accept-unaccounted`. Chi tiêu đã biết của dòng dõi tính vào trần
  ngân sách của run mới (nối tiếp không bao giờ đặt lại ngân sách: muốn chạy tiếp một run đã chạm trần thì nâng trần
  trong settings — một quyết định tường minh).
- **Một run được nối tiếp một lần — quyết định bằng bằng chứng.** `--parent` tạo độc quyền `CONTINUED-BY.json` *trước*
  request provider đầu tiên (run thua cuộc đua không tiêu gì — đã đo). Tạo độc quyền chỉ chứng minh một tiến trình thắng
  lúc tạo, nên một claim có sẵn được đối soát: child đã bắt đầu (journal có sự kiện) ⇒ từ chối, nối tiếp từ child, không
  bao giờ thay thế kể cả khi người vận hành yêu cầu; child kết thúc mà chưa bắt đầu, hoặc chưa bắt đầu và claimant chắc
  chắn đã mất (cùng máy, pid không còn hoặc là tiến trình khác theo thời điểm khởi động) ⇒ một thế hệ claim mới
  (`CONTINUED-BY.<n>.json`) thay thế, ghi bằng chứng; claimant còn sống, ở máy khác, hoặc không đọc được ⇒ từ chối, chỉ
  thay thế khi người vận hành nêu sha256 của claim (`--supersede-claim`, ghi là khẳng định của họ). Không xoá gì; không khoá
  vĩnh viễn: luôn có một đường đi tiếp có ghi nhận. **"Child đã bắt đầu" chỉ khi bằng chứng của nó đọc được.** Cửa sổ probe
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
| spec id (ba danh tính) | bundle 2.0.0 bị từ chối | `aisef bundle migrate` |
| `<out>/probe-python` → `<out>/test-python` | script đọc đường dẫn cũ | đổi tên; probe chạy trên interpreter của aisef |
| `--check` clone repo như lượt chạy thật | một khoá git không "inert" trong repo của bạn không còn làm `--check` báo sai lý do | không |
| endpoint `http://` chỉ cho loopback (phân tích host thật) | `http://localhost.evil.example` bị từ chối | dùng https |
| preflight không theo redirect | endpoint trả 3xx ⇒ OPAQUE | dùng URL cuối cùng |
| phiên bản `2.1.0.dev0` | gate phát hành từ chối mọi bản dev | đúng chủ ý |
| `file_artifact` `CAPABILITY_VERSION` 2 → 3 (PM-9) | spec id của mọi spec `file_artifact` đổi; bundle niêm phong trước cửa sổ bị từ chối khi nạp | `seal --keep-approvals-from`; bundle 2.0.0: `migrate` |
| lựa chọn không có tệp nào là chủ thể vắng (PM-9) | `grep_count`/`python_imports` `REQUIRES_SUBJECT` trên thư mục không còn tệp được chọn: trước `SATISFIED` (hoặc `REFUTED`), nay `INDETERMINATE(PRECONDITION_ABSENT)` | đọc §8.1, §8.7; chủ dự án quyết duyệt lại |
| `bundle continue` nghiêm hơn | journal mà `--verify` từ chối nay bị từ chối ở `continue`; `RUN.json` không đọc được không còn bị hạ xuống `RUN.started.json` | đọc mã `EVIDENCE_*` (§5) |
| claim: bằng chứng của child không đọc được | trước bị coi chưa bắt đầu và bị thay thế; nay `UNREAD`, chỉ thay bằng sha256 do người vận hành nêu | không (đường thoát `--supersede-claim` còn) |
| `<out>/probe-observations/` mới | `EVIDENCE.json` có thêm các tệp này; `--verify` đối chiếu | không |
| OCR hỏi `version` trước mọi lệnh review | binary có sha256 đúng pin nhưng tự khai khác `v1.12.12 (182898c…)` bị từ chối trước review | dùng đúng binary đã ghim |
| `process_effect`: bước `fault` trước bước `subprocess` | trước được nhận (lỗi không bao giờ tới tiến trình con); nay `INVALID_SPEC` | bỏ bước `fault`, hoặc đặt nó trước một bước `call`/`expect_raises` |
| reproducer của review lồng quá 63 tầng | trước được chạy (đến ~980 tầng); nay `UNVERIFIABLE` | làm phẳng stimulus/observable |

## 7. Giới hạn đã biết (đừng hiểu quá)

- Không có sandbox: developer và mã test chạy dưới user của người vận hành (V2-05 mở).
- `--verify` không có anchor chỉ chứng minh nhất quán.
- Review CONFIRMED không chứng minh người review đọc đúng yêu cầu.
- OCR đã nối vào `aisef run` và đã chạy **nhị phân thật** với một mô hình giả trên loopback: sha256 của nó khớp pin và
  nó tự khai `v1.12.12 (182898c)`; **chưa có bằng chứng về cách nó được dựng** (dựng lại từ nguồn: `NOT_PERFORMED`, §8.3).
  Chưa chạy với mô hình thật.
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

Nhánh ứng viên `v2.1/probe-window`, từ `2d01fe4` tới `f69124c` (cây `aisef2/` `1d4f0156…` → `168ad7d4…`). **So với cái
gì:** mỗi "trước cửa sổ" dưới đây là cây `2d01fe4`, **không** phải bản 2.0.0 đã phát hành. Nơi hành vi đó có cả ở `v2.0.0`
(tag, `ca26313`; đối chiếu trên mã) mục ghi *2.0.0 và trước cửa sổ*; nơi `v2.0.0` chưa có mã (lớp `python_imports`, hằng
`CAPABILITY_VERSION` và `EXECUTION_DIGEST`, `review_verify.py`, `review_ocr.py`, `lineage.py`, `bundle_cli.py`) mục ghi
*chưa có ở 2.0.0*. **Đã làm** = có
trong mã và test của nhánh (mỗi thay đổi hành vi có test đỏ trên mã trước cửa sổ, xanh sau, do làn tương ứng chạy). **Chưa có** =
hiệu chuẩn lại 19 hàng (§1), đo mutation, suite đầy đủ, e2e trong guest Linux và CI Windows/Linux cho cây này (REPORT §0.9).
Tên trạng thái dưới đây là tên trong mã: kết quả probe `SATISFIED`/`REFUTED`/`INDETERMINATE(PRECONDITION_ABSENT)`;
`UNRUNNABLE` (`HARNESS_FAILED` của quan sát; mã lỗi `PROBE_UNRUNNABLE`, owner `ENVIRONMENT`, retry được trong
`limits.ENVIRONMENT`); `INVALID_SPEC` (`PROBE_INVALID_SPEC`, owner `INTEGRATION`, không retry).

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
  `python_imports` trên cùng tệp là `REFUTED` (không phân tích được) — backlog V21-60. Spec/approval bị ảnh hưởng: §8.7.
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
  V21-63). Regex của luồng `cli_invocation` (`{"regex": r}`) **không** nằm trong vùng này.
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
- **RV-2 — câu nói cho INDETERMINATE.** Một probe chạy mà không quyết được không còn được nói là "the finding does not
  reproduce": thông điệp nay là `<probe> could not decide the stated behaviour (INDETERMINATE, <nguyên nhân>): neither
  confirmed nor ruled out`. Trạng thái vẫn là `NOT_REPRODUCED` (token giữ nguyên, backlog V21-66), `observed` và luật
  chặn không đổi: không block.
- **Cổng danh tính OCR — tự khai khác bằng chứng dựng.** *Trước cửa sổ (OCR chưa có ở 2.0.0):* chỉ kiểm sha256 của binary. *Nay*, trước mọi lệnh
  review (cả `advisory` lẫn `fix-loop`): (1) `pinned` — đường dẫn tuyệt đối, đọc được, sha256 = pin; (2) `declared` — chạy
  `<exe> version` trong môi trường sạch (`PATH=/usr/bin:/bin`, HOME rỗng, không kế thừa gì, `OCR_NO_UPDATE=1`, tối đa
  15 s); dòng đầu phải là `open-code-review <version> (<commit>) <platform>` với version `v1.12.12` và commit (in dạng
  ngắn) là tiền tố của `182898cf522da3d04157b422752d028417974e19`. Lệch ⇒ không lệnh review nào được chạy; thông điệp của
  bước (2) là một trong:

  ```
  <exe>: declares itself <version> (<commit>), not the pinned v1.12.12 (182898c): no review command was run
  <exe>: `version` did not answer in time
  <exe>: `version` exited <N>
  <exe>: `version` printed no version line (first line '<…>')
  <exe>: `version` could not be started (<ExcType>)
  ```

  Bước (1) có ba thông điệp riêng, nêu trước `version`: `<exe>: the OCR binary is named by an absolute path, never looked up`,
  `<exe>: cannot be read (<ExcType>)` và `<exe>: sha256 <12 hex>, not the pinned <12 hex>`.

  Mỗi thông điệp là một `CapabilityUnrunnable`, tức failure `CAPABILITY_UNRUNNABLE` (owner `ENVIRONMENT`, retry được trong
  `limits.ENVIRONMENT`) **ở cả hai `review.policy`**: khác với coverage chưa đủ — chỉ chặn dưới `fix-loop` —, kiểm sha256
  và `version` ném trước khi chính sách được xét (`aisef2/orchestrate/review.py`). Kết quả nằm trong phiên reviewer của
  `RUN.json`, `sessions[].identity`: `sha256_checked`, `declared` và `declared_by` = "the binary's own `version` output: a
  self-declaration, not build evidence". Cổng không gọi provider nào.
  Ba lớp bằng chứng, không bao giờ gộp (`validation/v21/ocr/BUILD-RECIPE.md`):

  | lớp | là gì | cho biết | trạng thái cho binary ghim (darwin/arm64, một binary) |
  |---|---|---|---|
  | (a) tự khai | dòng `version` do người dựng đặt bằng `-ldflags -X` | binary tự nhận là gì | khớp pin; cổng chấp nhận |
  | (b) metadata nhúng | build info Go (`go version -m`, đọc tệp, không chạy) | `go1.26.5`, `-trimpath=true`, `vcs.revision` = commit ghim, `vcs.modified=false`, 84 phụ thuộc | đã đọc; **không** chứng minh checkout là nguồn upstream nguyên vẹn |
  | (c) dựng lại được | sha256 của bản dựng offline từ đúng commit ghim, so với binary | **bằng chứng duy nhất** về cách tạo ra các byte | `NOT_PERFORMED`: không có nguồn upstream, module cache 0 tệp, không mạng; `-ldflags` của bản dựng gốc chưa biết |

  sha256 là sự thật về *byte*, không về nguồn gốc. Câu "dựng từ nguồn (`-trimpath`)" là lời của dự án: phù hợp (a) và (b),
  chưa được chứng minh. Chưa có phép so với artifact phát hành upstream; chưa có pin cho Linux/Windows.

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

Xem §5: trạng thái `UNREAD`, mã `EVIDENCE_*`, `--expect-anchor`, `bundle continue` hợp lệ đúng như `--verify`, chi phí
unknown cho journal không đọc được, `run --parent` từ chối thay vì traceback. Phạm vi: `child_state`/`claim`/`claims`,
`bundle continue`, `account_of`; `lineage.events_of` không từ chối một journal mà các projection từ chối (nó chỉ dựng lại
journal bằng `format3.reconstruct`, không qua projection nào; hai nơi gọi nó là `account_of` và `usage_lineage`, tức
chi tiêu). Lý do ghi lúc duyệt, "`child_state` dùng nó để kết
luận đã bắt đầu", không còn mô tả mã: `child_state` tự đọc journal trong `child_evidence`. Lý do còn lại là của `account_of`:
nó cần thấy các request mà journal ghi (đọc mã, chưa đo). `repair` giữ nguyên. Hai thay đổi nằm ngoài văn bản chủ dự án duyệt và
chờ xác nhận (backlog V21-55): `account_of` (commit `4d245f4`, lấy ra được bằng một `git revert`) và `RUN.json` không phải
UTF-8 (từ "rơi xuống `RUN.started.json`" sang `EVIDENCE_MALFORMED`).

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
  (không đổi hành vi; giữ cụm "isolation, not a sandbox" mà test ghim). Các câu công khai ngoài tài liệu này (README,
  `docs/v2/USAGE*.md`, landing) chưa nằm trong phạm vi của tài liệu này: xem backlog V21-26.

### 8.7 Spec và approval bị ảnh hưởng

| Thay đổi | `CAPABILITY_VERSION` / digest | spec id | verdict có thể đổi | hiệu chuẩn |
|---|---|---|---|---|
| PM-9 (và PM-3/4/11/13 cùng tệp) | `file_artifact` 2 → 3 (`DIGEST` đổi) | đổi, một lần | có, ở ba lớp dưới đây (PM-9; PM-11; PM-3/PM-13) | 4 hàng `file_artifact` |
| PM-1, PM-2, PM-6, PM-7, họ RV-1 | giữ 1 (`DIGEST` không đổi); `EXECUTION_DIGEST` của 3 probe đổi (và của `file_artifact`, dòng trên) | không đổi | PM-2: tổ hợp bị từ chối; PM-1: layout trước `UNRUNNABLE` nay quan sát được | 15 hàng (cli 5, process_effect 3, python_callable_v2 7) |

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
| `closure-evidence/v2/release/LEDGERLOCK-PROJECT.json` | bundle 2.0.0 của LedgerLock; 9 contract `file_artifact`: `BC-V22-S-10-a`, `S-12-a`, `S-12-b`, `S-12-c` (`grep_count`, `matches: 0`, `REQUIRES_SUBJECT`, `path:ledgerlock`, `.py`) thuộc lớp PM-9; `S-10-b`, `S-10-c` (một tệp, `matches: 1`) và `S-13-a/b/c` (`exists`) thì không thuộc lớp PM-9 | PM-9: chỉ khi `ledgerlock/` không chọn ra `.py` nào (hôm nay có). PM-11: `S-10-a/b/c`, `S-12-a/b` (neo `^`) chỉ khi một tệp `.py` được chọn có BOM đứng đầu (chưa đo) | mang theo qua `migrate` theo `contract_hash`; **không** bị cửa sổ này thu hồi hay duyệt lại |
| `closure-evidence/v2/v2.1/P5-PLAN-V2.2-PROPOSAL.json`, `closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json`, `closure-evidence/v2/v2.1/PLAN-V2.2-CORRECTION-1.json` | cùng 4 contract và 5 contract không bị ảnh hưởng của kế hoạch PLAN-V2.2 | như trên | `closure-evidence/v2/cycle2/P5-CONTRACT-APPROVALS.json`: 59 approval `human:owner` (2026-09-30); `binds` nêu `proposal_digest`, `plan_hash`, baseline, bản ghi đề xuất và candidate: `proposal_digest` và `plan_hash` đổi khi spec id đổi (đề xuất và kế hoạch nêu 59 spec id PPS). `spec_id` của mỗi approval là mã tiêu chí `S-*`, không phải spec id PPS, và nằm ngoài bảy trường của digest approval, nên không đổi; cửa sổ không dựng lại chúng |
| `aisef2/app/examples/calc-3-stories.json` | `BC-STDLIB`: `python_imports` trên `path:app`, `matches: 0`, `REQUIRES_SUBJECT` (ví dụ sống) | chỉ khi `app/` không còn `.py` (canary 2b chạy mẫu này trên lựa chọn không rỗng: không bị ảnh hưởng) | ví dụ không mang approval của chủ dự án |
| `docs/v2.1/drafts/LEDGERLOCK-BC-V22-S-10-a-r2.DRAFT.json` | bản nháp r2 của `BC-V22-S-10-a`: hai contract `python_imports` `REQUIRES_SUBJECT`, `matches: 0` | như trên | bản nháp chưa duyệt (B-04) |

Không bị ảnh hưởng: các fixture hiệu chuẩn `tests/v2/fixtures/calibration/file_artifact/*` (verdict không đổi; chỉ bản
ghi hiệu chuẩn buộc `EXECUTION_DIGEST` nên phải sinh lại) và các spec `exists`/`content` còn lại. Bundle 2.0.0 ngoài kho
(đã phát hành trên PyPI) và dự án ngoài kho không quét được: một ghi chú phát hành cần nói rằng lựa chọn rỗng của một
lệnh cấm `REQUIRES_SUBJECT` nay là `INDETERMINATE`.

**Cửa sổ này không di trú, không thu hồi và không duyệt lại một approval nào.** Một `ContractApproval` buộc
`requirement_hash` và `contract_hash`, không buộc probe, nên một bundle được buộc lại vẫn báo `approved` cho contract mà
quan sát của nó vừa đổi nghĩa; không có cơ chế nào trong công cụ đánh dấu approval đó là cũ (có nên có không: backlog
V21-61). Duyệt lại bốn contract trên (`aisef bundle approve`, trên digest mới) là **việc của chủ dự án**, không phải của
bất kỳ lệnh nào ở đây.
