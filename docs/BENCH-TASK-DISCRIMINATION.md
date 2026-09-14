# Sức phân biệt theo task — task nào mua tín hiệu, task nào chỉ mua hoá đơn

Đóng việc còn mở ở [BENCH-REPORT-C1B](BENCH-REPORT-C1B.md) §6 dòng 4: *tuyển
task theo tiêu chí "đã từng có nhánh thắng nhánh kia"*.

Đo 2026-09-14 trên **bằng chứng đã ghi**, không một lượt gọi model nào. Bảng
1–6 là stdout của `validation/bench_discriminating_power.py`, dán nguyên — sửa
tay một con số ở đó là làm lần sinh sau lệch mà không ai thấy. Dựng lại:

```
python3 validation/bench_discriminating_power.py .bench .bench-c1b
python3 validation/bench_discriminating_power.py --tu-kiem      # không cần dữ liệu
```

Định nghĩa `lượt` / `có thông tin` / `không dùng được` nằm ở đầu script và lấy
nguyên từ [giao thức v1.3](BENCH-PROTOCOL-v1.3.md) và hai báo cáo — mục 2 dưới
đây chỉ nhắc lại chỗ then chốt.

## 1. Câu trả lời ngắn

Toàn bộ corpus bench là **339 dòng kết quả** (302 lượt phân biệt được sau khi
bỏ dòng trùng), 30 task, 4 cohort, **28,4 giờ thời gian phiên**. Trong đó:

- **12 cặp chéo nhánh trên 340** (3,5 %) mang thông tin — nghĩa là ở 3,5 % số
  cặp, hai nhánh ra kết cục khác nhau. Cả 12 cặp đến từ **một** cohort (C-1) và
  **ba** task: `bug-a2-sec-1` (3), `bug-a2-sec-2` (6), `bug-a2-state-3` (3).
  Con số này theo cách đọc (b) ở mục 2; cách đọc (a) cộng thêm 16 cặp của C-1b
  mà cả 16 đều do phiên bị CLI cắt sinh ra.
- **25 task chưa bao giờ tách được hai nhánh**: 16 task v0.3.0 (frontier, 3/3
  PASS ở cả hai nhánh) và 9 task A-2 (`multi-1..4`, `sec-3`, `sec-4`,
  `state-1`, `state-2`, `state-4`).
- **2 task chưa đo** (`bug-6`, `bug-15`) — `unknown`, không suy diễn.
- **Toàn bộ số tiền corpus ghi được, 147,89 USD, rơi vào task có `D = 0`.** Cột
  tiền chỉ tồn tại ở cohort frontier; C-1 và C-1b chạy trên nhà cung cấp báo
  `cost_usd = 0` ở mọi bước — **vắng mặt giá**, không phải miễn phí (xem mục 3).

Và cái làm hỏng chính việc tuyển chọn này:

- **C-1b, đọc theo đúng định nghĩa lượt mà giao thức của nó khai trước khi
  chạy, cho 0 cặp có thông tin.** Cả 3 lượt trượt của C-1b đều là phiên bị CLI
  cắt; bỏ chúng ra thì ba task đều 1,00/1,00 ở cả hai nhánh. 36 lượt, 2,0 giờ,
  41,9 triệu token — và không một cặp nào tách được hai nhánh.
- **Nhóm của 6 task còn lại là `unknown`**, vì 24 lượt trượt của C-1 nằm trên
  đúng 6 task ấy và [C-1 §5.2](BENCH-REPORT-C1.md) đã đo: 20 trong 24 lượt
  trượt có một phiên bị CLI cắt. Lượt nào là lượt nào thì **không nằm trong
  corpus** — adapter chưa gọi tên kiểu hỏng ấy khi C-1 chạy.

Kết luận đọc được: tuyển task đúng cách **cắt được ~3/4 hoá đơn mà không mất
một cặp thông tin nào** (mục 4), nhưng tự nó **không** cứu được đợt đo. Trên
cặp model↔CLI này, cái chặn mọi hiệu số là việc 22–32 % phiên bị cắt, chứ không
phải việc chọn sai task — nghĩa là [C-1b §6 dòng 3](BENCH-REPORT-C1B.md) (đo
trên một cặp model↔CLI **không** có kiểu hỏng ấy) phải làm **trước** dòng 4,
không song song.

## 2. Hai chỗ then chốt trong định nghĩa

**`D` không phải hiệu ứng của điều kiện.** `D` = xác suất hai lượt, một mỗi
nhánh, ra kết cục khác nhau. Nó là *năng lực* tách, không phải hiệu ứng: một
task `D = 0` thì mua thêm bao nhiêu lượt cũng ra đúng một câu trả lời, nên
`D = 0` là **tiêu chí cắt**; `Δ ≠ 0` là tiêu chí giữ. Bằng chứng rằng hai thứ
ấy khác nhau nằm ngay trong Bảng 3: cohort mô phỏng có `D = 0,38–0,50` ở mọi
task trong khi `Δ = 0,00` ở mọi task — vì `simulated.py` chọn chiến lược bằng
`(attempt - 1) % 4`, một hàm thuần của số thứ tự lượt, giống hệt ở hai điều
kiện. Cohort ấy vì thế bị loại khỏi mọi phán quyết (bằng mã, không bằng lời) và
chỉ còn được đếm để phần kế toán khép kín.

**Hai cách đọc "một lượt", và vì sao bảng in cả hai.** Cột (a) *như đã chấm*
giữ mọi lượt chấm được; nó dựng lại **đúng** cột Δ đã in ở [C-1
§3](BENCH-REPORT-C1.md) (`sec-1` −0,33 · `sec-2` −0,67 · `state-3` +0,33) và
[C-1b §1](BENCH-REPORT-C1B.md) (+0,00 · +0,00 · +0,17) — đó là phép kiểm rằng
bộ đọc này không tự bịa ra một corpus khác. Cột (b) bỏ lượt hỏng hạ tầng, tức
định nghĩa mà [giao thức C-1b](BENCH-PROTOCOL-v1.3.md) khai **trước** khi chạy
và mà lỗi 86 làm cho không nổ lần nào. Hiệu số giữa (a) và (b) chính là cái giá
của lỗi ấy, và nó không nhỏ: nó đổi dấu kết luận của C-1b.

Một PASS sau phiên bị cắt **vẫn được giữ** ở cả hai cách đọc — bản sửa đã nằm
trên đĩa và test ẩn xanh, đúng cách [C-1b §4](BENCH-REPORT-C1B.md) đọc 6/9 lượt
PASS sau phiên bị cắt. Trần lượt (`max_turns`) **không** tính là hạ tầng, vì
`exit_status_of` xếp nó trước hạ tầng có chủ ý; nó có cột riêng ở Bảng 4 nên ai
muốn đọc cách khác thì tự cộng được.

## 3. Đơn vị: giá thì vắng, tài nguyên thì không

Việc còn mở nêu "C-1 cho 9 lượt có thông tin trên 6 giờ; C-1b cho 36 lượt có
thông tin trên 2 giờ". Hai con số ấy **không cùng đơn vị**, và Bảng 2 in cả hai
cách đếm để thấy: 9 là 3 task × 3 lượt của *một* nhánh, 36 là 3 × 6 × *hai*
nhánh. Cùng đơn vị thì C-1 là **9 / 18** và C-1b là **18 / 36** — và số cặp
thật sự mang thông tin là **12** (C-1) so với **0** (C-1b, cách đọc b).

Tài nguyên dùng bốn đơn vị corpus thật sự có: **lượt**, **turn**, **giây
phiên**, **token**. Token không nằm trong `results.jsonl` của C-1/C-1b (trường
ấy sinh sau) — chúng đọc từ `agent_run.tokens` trong kho bằng chứng, nơi duy
nhất còn giữ: 88,9 triệu token cho C-1, 41,9 triệu cho C-1b. Cột USD in `0.00`
ở hai cohort ấy là **vắng mặt giá**; ở cohort frontier nó là số thật, 147,89
USD. Đọc cột `$` của C-1 thành "miễn phí" là đọc sai cột.

Đối chiếu với báo cáo C-1 để kiểm bộ đọc: C-1 có **77** dòng, trong đó 2 dòng
là lượt chạy thử trước cohort (không có `model`) và 3 dòng là lượt chạy lại của
`multi-3`/`sec-3`. `report --cohort mycombo` lọc 2 dòng đầu và giữ 3 dòng sau →
**75**, đúng con số báo cáo in. Bảng ở đây lấy **dòng cuối** cho mỗi
`(task, điều kiện, lượt)` theo giao thức → **72** lượt phân biệt được.

## 4. Tuyển chọn đề nghị, và cái nó cắt được

**Không xoá task nào.** Tuyển chọn là một **danh sách tên** đưa cho harness;
`tests/bench/tasks/` và `MANIFEST.sha256` không đổi một byte, nên hai cohort đã
đóng vẫn dựng lại được nguyên trạng.

```
python3 -m tests.bench run-both bug-a2-sec-1 bug-a2-sec-2 bug-a2-state-3 \
    --client opencode --attempts 6 --note "..."
```

Harness đã nhận danh sách tên và chạy **theo thứ tự đã nêu**, nên không cần
thêm gì. Một chỗ đã sửa, vì tuyển chọn theo tên chỉ đáng tin khi đánh sai tên
thì nổ: tên task không có trong bộ dữ liệu trước đây bị **lặng lẽ bỏ qua** —
`run-both` sẽ chạy ít task hơn mà báo cáo vẫn khai là đã chạy tuyển chọn ấy.
Nay nó in tên sai ra stderr và trả mã 2, không chạy gì. Danh sách hợp lệ thì
hành vi không đổi.

| phần | task | vì sao |
|---|---|---|
| **giữ để đo** | `bug-a2-sec-1`, `bug-a2-sec-2`, `bug-a2-state-3` | ba task duy nhất từng có `Δ ≠ 0` |
| **cắt** | 16 task v0.3.0 (`bug-2-7-8-9` … `bug-r2r1`) | frontier 3/3 PASS ở cả hai nhánh, 144 cặp, 0 cặp có thông tin |
| **cắt** | `multi-1`, `multi-2`, `multi-3`, `sec-3`, `sec-4`, `state-4` | chạm trần ở C-1: 1,00/1,00, 54 cặp, 0 cặp có thông tin |
| **chuyển sang đợt chẩn đoán** | `multi-4`, `state-1`, `state-2` | 0,00/0,00 ở C-1 — nhưng 18 trong 24 lượt trượt của C-1 nằm ở đây, và 20/24 lượt trượt ấy có phiên bị cắt. Chưa biết là task khó hay hạ tầng hỏng: 1 lượt/task trên cặp model↔CLI sạch trước khi tính là "bất khả" |
| **để nguyên** | `bug-6`, `bug-15` | chưa đo; `invalid_reason` đã ghi trong `task.json` |

Cái cắt được, bằng đơn vị corpus có thật (Bảng 5):

| cohort | cắt | lượt | turn | giờ phiên | token | USD |
|---|---|---|---|---|---|---|
| C-1 | 9 / 12 task | 54 / 72 (**75 %**) | 1 086 / 1 486 (**73 %**) | 4,23 / 5,69 (**74 %**) | 63,4 M / 88,9 M (**71 %**) | vắng mặt |
| frontier | 17 / 17 task | 98 / 98 | 2 936 / 2 936 | 20,66 / 20,66 | cây đã xoá | **147,89 / 147,89** |
| cả corpus | 25 / 30 task | 224 / 302 (**74 %**) | — | 24,91 / 28,38 (**88 %**) | — | **100 %** |

Số cặp có thông tin mất đi khi cắt: **0**.

Con số này là **phép chiếu**, không phải lời khai "C-1 đáng ra tốn ít hơn":
tuyển chọn được rút ra từ chính kết quả của C-1, nên C-1 là cái giá phải trả để
biết nó. Nó nói một cohort **hình dạng như C-1** sẽ tốn bao nhiêu nếu chỉ chạy
phần giữ lại. Với 147,89 USD của cohort frontier thì lời khai mạnh hơn được:
tiền ấy mua một kết quả null đã báo (task dễ, frontier, 100 %/100 %) — nó
**không** mua một cặp nào tách được hai nhánh, và mua thêm lượt trên 16 task ấy
sẽ tiếp tục không mua.

## 5. Hàng nào quá mỏng để hành động

Nói ra kèm số, vì một kết luận dựa trên vài lượt là một kết luận có khoảng tin
rộng:

- `bug-a2-sec-1`: `Δ = −0,33` ở C-1 là **một lượt** trong ba. Ở C-1b với n = 6
  nó về 1,00/1,00. Giữ lại vì tiêu chí là "đã từng", nhưng bằng chứng giữ nó là
  một lượt duy nhất — nếu phải cắt thêm một task, cắt task này.
- `bug-a2-state-3`: `Δ = +0,33` (C-1) rồi `+0,17` (C-1b, cách đọc a) — cả hai
  đều là **một lượt** trong 3 và trong 6, và ở cách đọc b cả hai về 0,00. Đây
  là task có bằng chứng dày nhất, và nó vẫn chỉ là một lượt mỗi lần.
- `bug-a2-sec-2`: 6 cặp có thông tin của nó là số lớn nhất corpus, nhưng
  [C-1b §2](BENCH-REPORT-C1B.md) đã quy cho **lỗi bộ dữ liệu** (đề bài đọc được
  hai nghĩa, sửa ở v1.4). Bỏ 6 cặp ấy ra thì cả corpus còn **6 cặp có thông
  tin trên 340** (1,8 %). `sec-2` cũng là task duy nhất **không so ngang** được
  giữa C-1 và C-1b — byte đề bài khác — nên Bảng 1 in `D` theo từng cohort chứ
  không gộp.
- Cohort frontier có 16 lượt hỏng hạ tầng (14 lượt bị đồng hồ 1800 s cắt, 2
  lượt 401) trong 98. Cả 14 lượt timeout đều PASS nên vẫn dùng được; 2 lượt 401
  là `bug-a2-sec-3` và chúng là lý do task ấy xuất hiện trong danh sách "giữ"
  của cách đọc (a) — một lỗi xác thực trông y như biến động của task. Đó chính
  là lý do tuyển chọn lấy từ cách đọc (b), không phải (a).

## 6. Thứ cố ý không chạm, và vì sao

- **`tests/bench/tasks/`, `MANIFEST.sha256`** — hai báo cáo đã đóng khai dựng
  lại được nguyên byte bằng cách chạy lại harness. Xoá task là làm lời khai ấy
  sai về sau. Tuyển chọn vì thế là danh sách tên, không phải phép xoá.
- **Scorer, `pass@1`, `TRAN_LUOT`, `--attempts`, `run.timeout_seconds`, thứ tự
  task** — biến đã ghim của hai cohort.
- **`_analyze.cut_sessions`** — nó khoá theo `(điều kiện, task, lượt)` mà
  **không mang tên sổ**, nên với `.bench` và `.bench-c1b` cùng có
  `sec-1`/`sec-2`/`state-3` thì số phiên của hai cohort trộn vào nhau ở đúng ba
  task đáng quan tâm nhất. Đã không sửa: hai báo cáo đang trích số của nó, và
  sửa keying là làm một lần chạy lại `analyze` in ra bảng khác bảng đã in. Ghi
  ở đây làm việc kéo theo cho cohort sau.
- **Kho phiên của OpenCode** (`~/.local/share/opencode/opencode.db`, 4 GB) —
  nguồn duy nhất còn biết lượt nào của C-1 bị cắt. Không dùng: nó nằm ngoài
  corpus, thay đổi theo thời gian (nên script sẽ không dựng lại được cùng con
  số ngày mai), và `cut_sessions` trộn hai cohort như trên. Trạng thái bị cắt
  của từng lượt C-1 vì thế là **`unknown`**, và mục 1 nói rõ nó làm nhóm của 6
  task thành `unknown` theo.
Sinh bằng `python3 validation/bench_discriminating_power.py`. Không một lượt gọi model nào: mọi số dưới đây đọc từ `results.jsonl` và kho bằng chứng của các cohort đã đóng. Định nghĩa `lượt` / `có thông tin` / `không dùng được` nằm ở đầu script và lấy từ giao thức, không phát minh thêm.

> Dòng trùng (một `(task, điều kiện, lượt)` chạy nhiều lần; giữ dòng **cuối** theo giao thức): C-1/`bug-a2-multi-3` +3, C-1/`bug-a2-sec-3` +2, mô phỏng v1.3/`bug-a2-sec-1` +4, mô phỏng v1.3/`bug-a2-state-1` +28.

## Bảng 1 — ba mươi task

| task | cohort thật đã chạy | lượt ghi | lượt dùng được | cặp | có thông tin | cùng PASS | cùng FAIL | D theo cohort | không dùng được | nhóm |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| `bug-10` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-11` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-12` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-13` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-14` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-15` | – | 0 | 0 | 0 | 0 | 0 | 0 | – | 0 | **chưa đo** |
| `bug-16` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-17-18` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-19` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-2-7-8-9` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-20` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-21` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-23-24` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-25` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-26-27` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-4-5` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |
| `bug-6` | – | 0 | 0 | 0 | 0 | 0 | 0 | – | 0 | **chưa đo** |
| `bug-a2-multi-1` | C-1 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (C-1) | 0 | chạm trần |
| `bug-a2-multi-2` | C-1 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (C-1) | 0 | chạm trần |
| `bug-a2-multi-3` | C-1 | 9 | 6 | 9 | 0 | 9 | 0 | 0,00 (C-1) | 0 | chạm trần |
| `bug-a2-multi-4` | C-1 | 6 | 5 | 6 | 0 | 0 | 6 | 0,00 (C-1) | 1 | sàn |
| `bug-a2-sec-1` | C-1, C-1b | 18 | 18 | 45 | 3 | 42 | 0 | 0,33 (C-1) · 0,00 (C-1b) | 0 | phân biệt được |
| `bug-a2-sec-2` | C-1, C-1b | 18 | 16 | 34 | 6 | 25 | 3 | 0,67 (C-1) · 0,00 (C-1b) | 2 | phân biệt được |
| `bug-a2-sec-3` | frontier v0.3.0/v1.3, C-1 | 10 | 6 | 9 | 0 | 9 | 0 | – (frontier v0.3.0/v1.3) · 0,00 (C-1) | 2 | chạm trần |
| `bug-a2-sec-4` | C-1 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (C-1) | 0 | chạm trần |
| `bug-a2-state-1` | C-1 | 6 | 6 | 9 | 0 | 0 | 9 | 0,00 (C-1) | 0 | sàn |
| `bug-a2-state-2` | C-1 | 6 | 6 | 9 | 0 | 0 | 9 | 0,00 (C-1) | 0 | sàn |
| `bug-a2-state-3` | C-1, C-1b | 18 | 17 | 39 | 3 | 36 | 0 | 0,33 (C-1) · 0,00 (C-1b) | 1 | phân biệt được |
| `bug-a2-state-4` | C-1 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (C-1) | 0 | chạm trần |
| `bug-r2r1` | frontier v0.3.0/v1.3 | 6 | 6 | 9 | 0 | 9 | 0 | 0,00 (frontier v0.3.0/v1.3) | 0 | chạm trần |

## Bảng 2 — tổng theo cohort

| cohort | task | lượt ghi | lượt dùng được | cặp (b) | cặp có thông tin (a) | cặp có thông tin (b) | lượt trên task phân biệt (1 nhánh / 2 nhánh) | giờ phiên | turn | token | USD nhà cung cấp báo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| frontier v0.3.0/v1.3 | 17 | 98 | 96 | 144 | 0 | 0 | 0 / 0 | 20.66 | 2936 | – (cây đã xoá) | 147.89 |
| C-1 | 12 | 77 | 71 | 105 | 12 | 12 | 9 / 18 | 5.69 | 1486 | 88 930 672 | 0.00 |
| mô phỏng v1.3 | 12 | 128 | 96 | 192 | 90 | 90 | 12 / 24 | 0.02 | 96 | – (cây đã xoá) | 0.00 |
| C-1b | 3 | 36 | 33 | 91 | 16 | 0 | 18 / 36 | 2.01 | 669 | 41 867 812 | 0.00 |

## Bảng 3 — theo từng cohort × task, hai cách đọc

**(a)** như đã chấm — cột Δ ở đây phải trùng đúng bảng đã in của hai báo cáo. **(b)** bỏ lượt hỏng hạ tầng — định nghĩa lượt mà giao thức C-1b khai *trước* khi chạy.

| cohort | task | (a) A/B | (a) p@1 A | (a) p@1 B | (a) Δ | (a) D | (b) A/B | (b) p@1 A | (b) p@1 B | (b) Δ | (b) D | turn | giây phiên | token |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| frontier v0.3.0/v1.3 | `bug-10` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 136 | 4187 | – |
| frontier v0.3.0/v1.3 | `bug-11` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 210 | 4913 | – |
| frontier v0.3.0/v1.3 | `bug-12` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 234 | 5858 | – |
| frontier v0.3.0/v1.3 | `bug-13` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 117 | 5217 | – |
| frontier v0.3.0/v1.3 | `bug-14` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 111 | 1218 | – |
| frontier v0.3.0/v1.3 | `bug-16` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 246 | 6838 | – |
| frontier v0.3.0/v1.3 | `bug-17-18` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 211 | 4822 | – |
| frontier v0.3.0/v1.3 | `bug-19` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 197 | 3554 | – |
| frontier v0.3.0/v1.3 | `bug-2-7-8-9` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 164 | 4455 | – |
| frontier v0.3.0/v1.3 | `bug-20` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 180 | 2491 | – |
| frontier v0.3.0/v1.3 | `bug-21` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 228 | 6027 | – |
| frontier v0.3.0/v1.3 | `bug-23-24` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 210 | 4384 | – |
| frontier v0.3.0/v1.3 | `bug-25` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 154 | 3331 | – |
| frontier v0.3.0/v1.3 | `bug-26-27` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 196 | 6730 | – |
| frontier v0.3.0/v1.3 | `bug-4-5` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 217 | 6059 | – |
| frontier v0.3.0/v1.3 | `bug-a2-sec-3` | 1/1 | 0,00 | 0,00 | +0,00 | 0,00 | 0/0 | – | – | – | – | 2 | 354 | 0 |
| frontier v0.3.0/v1.3 | `bug-r2r1` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 123 | 3940 | – |
| C-1 | `bug-a2-multi-1` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 80 | 534 | 2 633 550 |
| C-1 | `bug-a2-multi-2` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 90 | 580 | 3 502 347 |
| C-1 | `bug-a2-multi-3` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 90 | 1436 | 4 230 589 |
| C-1 | `bug-a2-multi-4` | 3/3 | 0,00 | 0,00 | +0,00 | 0,00 | 2/3 | 0,00 | 0,00 | +0,00 | 0,00 | 262 | 4831 | 21 136 139 |
| C-1 | `bug-a2-sec-1` | 3/3 | 0,67 | 1,00 | -0,33 | 0,33 | 3/3 | 0,67 | 1,00 | -0,33 | 0,33 | 163 | 2180 | 10 078 663 |
| C-1 | `bug-a2-sec-2` | 3/3 | 0,00 | 0,67 | -0,67 | 0,67 | 3/3 | 0,00 | 0,67 | -0,67 | 0,67 | 107 | 1306 | 4 858 988 |
| C-1 | `bug-a2-sec-3` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 59 | 409 | 1 909 819 |
| C-1 | `bug-a2-sec-4` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 69 | 487 | 2 296 593 |
| C-1 | `bug-a2-state-1` | 3/3 | 0,00 | 0,00 | +0,00 | 0,00 | 3/3 | 0,00 | 0,00 | +0,00 | 0,00 | 137 | 2251 | 10 032 249 |
| C-1 | `bug-a2-state-2` | 3/3 | 0,00 | 0,00 | +0,00 | 0,00 | 3/3 | 0,00 | 0,00 | +0,00 | 0,00 | 162 | 3153 | 9 792 103 |
| C-1 | `bug-a2-state-3` | 3/3 | 1,00 | 0,67 | +0,33 | 0,33 | 3/3 | 1,00 | 0,67 | +0,33 | 0,33 | 130 | 1767 | 10 633 181 |
| C-1 | `bug-a2-state-4` | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 3/3 | 1,00 | 1,00 | +0,00 | 0,00 | 137 | 1546 | 7 826 451 |
| mô phỏng v1.3 | `bug-a2-multi-1` | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 8 | 7 | – |
| mô phỏng v1.3 | `bug-a2-multi-2` | 4/4 | 0,25 | 0,25 | +0,00 | 0,38 | 4/4 | 0,25 | 0,25 | +0,00 | 0,38 | 8 | 7 | – |
| mô phỏng v1.3 | `bug-a2-multi-3` | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 8 | 6 | – |
| mô phỏng v1.3 | `bug-a2-multi-4` | 4/4 | 0,25 | 0,25 | +0,00 | 0,38 | 4/4 | 0,25 | 0,25 | +0,00 | 0,38 | 8 | 7 | – |
| mô phỏng v1.3 | `bug-a2-sec-1` | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 8 | 6 | – |
| mô phỏng v1.3 | `bug-a2-sec-2` | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 8 | 6 | – |
| mô phỏng v1.3 | `bug-a2-sec-3` | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 8 | 6 | – |
| mô phỏng v1.3 | `bug-a2-sec-4` | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 8 | 7 | – |
| mô phỏng v1.3 | `bug-a2-state-1` | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 8 | 7 | – |
| mô phỏng v1.3 | `bug-a2-state-2` | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 8 | 7 | – |
| mô phỏng v1.3 | `bug-a2-state-3` | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 4/4 | 0,50 | 0,50 | +0,00 | 0,50 | 8 | 6 | – |
| mô phỏng v1.3 | `bug-a2-state-4` | 4/4 | 0,25 | 0,25 | +0,00 | 0,38 | 4/4 | 0,25 | 0,25 | +0,00 | 0,38 | 8 | 6 | – |
| C-1b | `bug-a2-sec-1` | 6/6 | 1,00 | 1,00 | +0,00 | 0,00 | 6/6 | 1,00 | 1,00 | +0,00 | 0,00 | 175 | 2015 | 10 351 755 |
| C-1b | `bug-a2-sec-2` | 6/6 | 0,83 | 0,83 | +0,00 | 0,28 | 5/5 | 1,00 | 1,00 | +0,00 | 0,00 | 246 | 2243 | 12 057 897 |
| C-1b | `bug-a2-state-3` | 6/6 | 1,00 | 0,83 | +0,17 | 0,17 | 6/5 | 1,00 | 1,00 | +0,00 | 0,00 | 248 | 2964 | 19 458 160 |

## Bảng 4 — kiểu kết thúc của lượt

| cohort | lượt | `ok` | `tran_luot` | `ha_tang` | `phien_cat` | `khong_cham_duoc` |
|---|---:|---:|---:|---:|---:|---:|
| frontier v0.3.0/v1.3 | 98 | 50 | 32 | 16 | 0 | 0 |
| C-1 | 72 | 71 | 0 | 1 | 0 | 0 |
| mô phỏng v1.3 | 96 | 96 | 0 | 0 | 0 | 0 |
| C-1b | 36 | 27 | 0 | 0 | 9 | 0 |

## Bảng 5 — giá của phần bị cắt

Giữ theo **định nghĩa lượt đã khai** (bỏ lượt hỏng hạ tầng) — đây là tuyển chọn được đề nghị: `bug-a2-sec-1`, `bug-a2-sec-2`, `bug-a2-state-3`.
Đối chiếu, giữ theo cách đọc **như đã chấm**: `bug-a2-sec-1`, `bug-a2-sec-2`, `bug-a2-sec-3`, `bug-a2-state-3`.

| cohort | phần | task | lượt | turn | giây phiên | token | USD nhà cung cấp báo |
|---|---|---:|---:|---:|---:|---:|---:|
| frontier v0.3.0/v1.3 | cắt | 17 | 98 | 2936 | 74378 | 0 (thiếu) | 147.89 |
| C-1 | giữ | 3 | 18 | 400 | 5252 | 25 570 832 | 0.00 |
| C-1 | cắt | 9 | 54 | 1086 | 15228 | 63 359 840 | 0.00 |
| mô phỏng v1.3 | giữ | 3 | 24 | 24 | 19 | 0 (thiếu) | 0.00 |
| mô phỏng v1.3 | cắt | 9 | 72 | 72 | 60 | 0 (thiếu) | 0.00 |
| C-1b | giữ | 3 | 36 | 669 | 7222 | 41 867 812 | 0.00 |

## Bảng 6 — task không quyết được

- `bug-15`: **unknown** — base+test+gold còn đỏ: tests.test_mockup_map.TestLoadHalf.test_loads_only_the_named_screen, tests.test_mockup_map.TestLoadHalf.test_sample_data_is_not_a_commitment, tests.test_mockup_map.TestLoadHalf.test_slice_carries_r
- `bug-6`: **unknown** — chưa đo (không phải oracle hỏng): bộ test ở snapshot gọi Docker thật trong từng ca (~9 phút/lần chạy, 6 lần ≈ 1 giờ) — dừng 2026-09-06 để không chen luồng đo thời gian; chạy lại khi máy rảnh: python3 -m tests.bench valid

