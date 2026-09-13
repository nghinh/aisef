# Nối bench A-2 vào model thật — bàn giao + tiền đăng ký (cột 2)

Viết 2026-09-14, **trước** khi có một byte dữ liệu nào của cột 2. Không một lượt
gọi model nào được tiêu để viết tài liệu này hay để kiểm mã trong đó.

## 0. Trạng thái thật của việc này khi tôi nhận, đo chứ không suy

Đề bài tôi nhận nói "cohort v1.3 chỉ chạy được với `SimulatedWeakAdapter`". Kho
**không** còn ở đó nữa:

```
git log --oneline -3 -- docs/BENCH-REPORT-C1.md    # 06dca24 docs(bench): the C-1 report
```

Hai cohort trên model thật đã chạy và đã đóng: **C-1** (12 task × 3 lượt × 2 điều
kiện, 12/09, 5,69 giờ phiên) và **C-1b** (3 task × 6 lượt × 2 điều kiện, 13/09,
2,0 giờ). Cả hai chạy `--client opencode` với alias `9router/mycombo`, model nền
MiniMax-M2.7 theo lời khai chủ dự án. Đường ống hai cột **đã được nối sẵn**, và
`docs/BENCH-REPORT-C1B.md` § 6 nêu đúng việc còn lại: *"Cột 2 — đổi model sau
alias — ⏳ chờ chủ dự án"*.

Nên việc của tôi không phải nối lại từ đầu; nó là **bịt bốn lỗ hổng đo lường**
còn lại rồi đưa cột 2 tới trạng thái phóng được. Cái gì tôi *không* làm và vì
sao: § 8.

Kiểm bằng lệnh, không bằng lời:

| điều đã có sẵn | chứng cứ |
|---|---|
| hai điều kiện `opencode` / `opencode-bare` | `tests/bench/_runner.py::run(bare=…)` |
| `--model` tới **cả hai** nhánh | `test_bench.py::TestModelDiVaoCaHaiDieuKien` |
| cùng một trần lượt ở hai nhánh (`TRAN_LUOT = 0`) | `test_hai_dieu_kien_chay_cung_che_do_tran_luot` |
| phiên bị CLI cắt → trạng thái `infra` | `test_phien_bi_cli_cat_ra_trang_thai_thuoc_nhom_chay_lai` |
| byte bộ dữ liệu bị ghim | `test_manifest_dong_bang_du_lieu_da_do` |

## 1. Bốn thứ tôi đổi

### 1.1 Token vào sổ kết quả (`tests/bench/_runner.py`)

`Result` nhận `tokens_in` / `tokens_out` / `tokens_cache_read` /
`tokens_cache_write` và thuộc tính `tokens`. Vì sao đây là lỗ hổng nặng nhất:
nhà cung cấp sau `mycombo` báo `cost_usd = 0` ở **mọi** bước, và hai báo cáo
C-1/C-1b vì thế nói "cột tiền vắng mặt, hãy đọc turn và giây". Nhưng token
**không** vắng mặt — chúng nằm trong bằng chứng suốt từ đầu:

```
.bench-c1b/run/opencode-bare/bug-a2-sec-1/a1/_bmad-output/evidence/bug-a2-sec-1.jsonl
  → "tokens": {"input": 98392, "output": 1487, "cache_creation": 0, "cache_read": 581444}
     "cost_usd": 0.0
```

680 nghìn token một phiên, giá 0,00 USD. Một bảng có cột `$ = 0,00` mà không có
cột token đọc ra thành "miễn phí", và đó là câu sai duy nhất mà một đợt đo "chi
phí 0" dễ sinh ra nhất. Từ giờ token đi từ `step_finish.tokens` → `RunResult` →
`Result` → `results.jsonl` → báo cáo.

`report()` có thêm mục **"Token và kiểu kết thúc"**, và mục ấy **chỉ in ra khi có
dòng mang token**. Lý do của điều kiện ấy không phải thẩm mỹ: báo cáo của cohort
đã đóng dựng lại bằng chính lệnh `report --cohort mycombo` (C-1 § 2), dòng của
chúng không mang token, và in một cột 0 vào đó là nói "không tiêu gì" — sai
ngược lại. Kiểm được:

```
AISEF_BENCH_DIR=<bản chép .bench> python3 -m tests.bench report --cohort mycombo
# bảng so sánh ra **đúng từng số** như BENCH-REPORT-C1.md § 3, không thêm cột nào
```

### 1.2 Trạng thái thoát vào sổ kết quả (`tests/bench/_runner.py`)

`Result.exit_status` + `Result.infra_retries`. **Cách chấm không đổi một dòng**
— scorer vẫn là F2P/P2P trên test ẩn, taxonomy vẫn PASS/FAIL/INVALID/UNRUNNABLE.
Cái thêm là *xuất xứ*: một lượt FAIL vì CLI cắt phiên giờ đọc ra được khác một
lượt FAIL vì agent sửa sai, **ngay trong dòng kết quả**. C-1 phải đối chiếu kho
sqlite 3,5 GB của OpenCode mới phân biệt nổi hai thứ ấy (§ O-7), và đó là lý do
nó suýt kết luận nhầm.

Kèm theo: phép thử **hành vi** đầu tiên cho cơ chế chạy lại hạ tầng
(`test_phien_bi_cat_duoc_chay_lai_that_va_ghi_lai_so_lan` — đếm số lần client
được gọi). Cơ chế này được khai từ C-1b nhưng **không nổ lần nào** ở đó (lỗi 86),
và phép thử cũ chỉ đọc mã nguồn nên không thấy.

### 1.3 Một đợt đo một lúc (`tests/bench/__main__.py`)

`run` / `run-both` giữ khoá độc quyền `<AISEF_BENCH_DIR>/bench.lock`
(`flock` qua `aisef._compat`, đã có sẵn). Lệnh thứ hai bị từ chối với mã thoát
**3** và một câu nói rõ phải làm gì.

Lý do mạnh hơn "nhà cung cấp không thích song song": `materialize()` gọi
`remove_tree(dest)` **trước** khi dựng cây mới, nên hai tiến trình cùng một
`AISEF_BENCH_DIR` xoá cây làm việc của nhau — mất dữ liệu đo, im lặng, không lỗi
nào. Khoá không liên tiến trình với dogfood: một `aisef run` đang chạy vẫn chiếm
endpoint mà bench không thấy. Đó là việc của người vận hành, và tôi nói ra chứ
không giả vờ đã chặn.

### 1.4 Trần thời gian (`tests/bench/__main__.py`)

`run-both --max-minutes N`, cắt ở **ranh giới task** y như `--max-usd`, và in tên
task bị bỏ. Vì sao cần: điều kiện dừng duy nhất giao thức khai là `--max-usd`, và
nó **trơ** với nhà cung cấp này — `cost_usd = 0` nên trần chi phí không bao giờ
đạt. Với một model hay chạm trần lượt, mỗi lượt chạy tới hết đồng hồ 1800 s, và
72 lượt × 30 phút = **36 giờ**. Trần thời gian không đổi thứ gì trong một lượt
đã bắt đầu; nó chỉ quyết định task **kế tiếp** có chạy không.

## 2. Bộ dữ liệu, scorer, `benchmark_revision` — không chạm

```
python3 -m pytest tests/bench/test_bench.py -q -k manifest     # 6 passed
```

`MANIFEST.sha256` khớp **từng byte** sau mọi thay đổi của tôi (120 dòng = 30 task
× 4 tệp fixture). Tôi không sửa `tests/bench/tasks/**`, không sửa `_grade()`,
không sửa `validate()`, không đổi taxonomy kết cục. `benchmark_revision` không
tồn tại như một ký hiệu trong kho — thứ đóng băng dữ liệu ở đây là manifest, và
phép thử tự kiểm cũng kiểm lại nó.

## 3. Tự kiểm — chạy được, không tốn một lượt gọi model

```
python3 -m tests.bench selfcheck                     # ~13 giây, 19/19
python3 -m tests.bench selfcheck --model 9router/mycombo
```

Đầu ra mở và đóng bằng đúng một câu: **KHÔNG PHẢI KẾT QUẢ ĐO**. Nó chạy *đúng*
`R.run()` của đợt đo thật, *đúng* `OpenCodeAdapter`, *đúng* scorer — chỉ khác một
chỗ: adapter được dựng với `binary=` trỏ vào một script giả trong thư mục tạm.
Không phải PATH thủ thuật: `shutil.which` nhận đường dẫn tuyệt đối, nên CLI thật
**không thể** bị gọi kể cả khi nó có trên máy và đã đăng nhập (ở máy này:
`/Users/nghinh/.opencode/bin/opencode` 1.18.30, selfcheck in ra dòng ấy như một
bước tiền kiểm).

19 phép kiểm, nhóm theo thứ chúng bảo vệ:

| nhóm | phép kiểm |
|---|---|
| bộ dữ liệu | `MANIFEST.sha256` khớp từng byte |
| không có biến thứ hai | argv `run --format json`; `--dir` trỏ đúng cây; **cùng một model** ở hai nhánh; **đề bài giống nhau từng byte** (2 190 ký tự) |
| harness thật sự có/không có | nhánh AISEF: `AISEF_WRITE_SCOPE` + `AISEF_STORY_ID` tới được tiến trình con, `.opencode/plugin/aisef-guard.ts` có trong cây; nhánh trần: không biến nào, không plugin, không compile-report |
| scorer không nới | bản sửa đúng → PASS ở cả hai nhánh; phiên không ghi gì → FAIL |
| token | 681 323 token vào sổ trong khi `$ = 0,00`; `results.jsonl` mang `tokens_in` + `exit_status` qua JSON; báo cáo in câu "vắng mặt giá" |
| hạ tầng ≠ agent | phiên bị cắt → `infra`, chạy lại **đúng** 1 lần, và lượt ấy mang `infra` + 1 chứ không lẫn vào nhóm "agent sửa sai" |

Nó **không** chứng minh guard chặn được gì — script giả không chạy hook nào. Bằng
chứng cho việc chặn nằm ở `aisef/clients/opencode.py` (docstring, đo 2026-09-05:
`rm -rf` bị chặn và tệp còn nguyên; `Write` một tệp có `os.system` bị chặn và
không có tệp nào trên đĩa) và ở bộ hợp quy. Tôi nói ra giới hạn này thay vì để
19/19 đọc thành "guard đã được chứng minh".

Phép tự kiểm cũng nằm trong suite (`TestTuKiemDuongOng`), nên nó không mục: bốn
phép kiểm của nó là đúng những thứ đổi lặng lẽ nhất.

## 4. Lệnh phóng cột 2 — nguyên văn

Bước 1 (việc của chủ dự án, harness không tự làm được): đổi model nền sau alias
`mycombo` và **nói ra tên model mới**. Luồng JSON của OpenCode không mang tên
model (đo 12/09), nên tên ấy là **lời khai** và được ghi vào `--note` như lời
khai.

Bước 2 — từ một shell thật, **không** từ trong một phiên agent (lượt phóng đầu
của C-1 bị harness kill sau ~35 phút vì nó dọn tác vụ nền dài):

```sh
cd /Users/nghinh/Downloads/projects/ai-sdlc
mkdir -p .bench-c2
AISEF_BENCH=1 AISEF_BENCH_DIR=.bench-c2 nohup python3 -m tests.bench run-both \
    bug-a2-sec-4 bug-a2-sec-3 bug-a2-multi-1 bug-a2-multi-3 bug-a2-multi-2 \
    bug-a2-sec-2 bug-a2-sec-1 bug-a2-state-1 bug-a2-state-2 bug-a2-state-3 \
    bug-a2-state-4 bug-a2-multi-4 \
    --client opencode --attempts 3 --max-minutes 600 \
    --note "mycombo→<TÊN MODEL> (khai 2026-09-14)" \
    > .bench-c2/run.log 2>&1 &
```

Từng mảnh, và vì sao:

- **`AISEF_BENCH_DIR=.bench-c2`** — bắt buộc. `materialize()` xoá cây cũ trước khi
  dựng, nên chạy trong `.bench/` sẽ xoá đúng 12 cây làm việc mà
  `BENCH-REPORT-C1.md` đang trích dẫn làm bằng chứng. Đây là cách C-1b đã làm.
- **thứ tự 12 task** — đúng thứ tự cột 1, đọc từ `.bench/results.jsonl` chứ không
  từ ký ức: sec-4, sec-3 (hai task của hạt giống 1312), rồi multi-1, multi-3,
  multi-2, sec-2, sec-1, state-1, state-2, state-3, state-4, multi-4. Hai cách
  đếm (dòng đầu và dòng cuối của mỗi task trong sổ) cho **cùng một** thứ tự. Từ
  bản vá 12/09 bench chạy theo thứ tự tham số, nên nêu tên là chạy đúng thứ tự đó.
- **không truyền `--model`** — cột 1 cũng không truyền; model là mặc định trong
  `~/.config/opencode/opencode.json`, đọc một lần mỗi phiên bởi
  `configured_model()`. Hệ quả phải nhớ: **không sửa tệp ấy trong lúc đợt đo đang
  chạy**, nếu không nửa cột đo model này, nửa kia đo model khác, mà mọi dòng vẫn
  ghi cùng một chuỗi.
- **`--attempts 3`** — như cột 1. Đổi số lượt là đổi giao thức.
- **`--max-minutes 600`** — 10 giờ thời gian phiên, dư so với kỳ vọng 6,6 giờ. Nếu
  nó nổ thì cohort **bị cắt** và phải được báo là bị cắt; runner in tên task
  không chạy.

Bước 3 — đóng đợt (không tốn model):

```sh
AISEF_BENCH_DIR=.bench-c2 python3 -m tests.bench report --cohort "<TÊN MODEL>"
AISEF_BENCH_DIR=.bench-c2 python3 -m tests.bench analyze
```

### Số phiên và thời gian, suy từ C-1 chứ không đoán

| | |
|---|---|
| lượt theo thiết kế | 12 × 3 × 2 = **72** |
| phiên **tối thiểu** | 72 |
| phiên **kỳ vọng** | ≈ **90** — C-1b đo 9/36 lượt (25 %) kết thúc bằng một phiên bị CLI cắt, và từ bản vá 13/09 mỗi lượt như thế mua thêm một phiên chạy lại |
| thời gian phiên, C-1 | 5,69 giờ (AISEF 3,47 · trần 2,22), trung vị 184 s/phiên |
| thời gian chấm | ≈ 1,1 giờ (72 lần `materialize` + chạy test ẩn, ≈55 s/lượt) |
| **wall-clock kỳ vọng** | **7 – 8,5 giờ** |
| wall-clock xấu nhất | **36 giờ** nếu model chạm đồng hồ 1800 s ở mọi lượt — đây là lý do `--max-minutes` tồn tại |
| chi phí USD | 0,00 báo bởi nhà cung cấp. Token thì **không** 0: kỳ vọng ≈ 700 k/phiên → ≈ 60 M token cho cả cohort |

Nếu máy phải rảnh cho việc khác, chạy theo lô hai task một lần như C-1 đã làm —
nhưng **giữ nguyên thứ tự** và ghi lại lô nào chạy lúc nào, vì alias định tuyến
có thể đổi model nền giữa các lô và đó là biến không kiểm soát được.

## 5. Các confound tôi tìm thấy, và cách đường ống tránh (hoặc không tránh)

| # | confound | xử lý |
|---|---|---|
| 1 | hai cột chạy hai model khác nhau | `--model` đi vào **cả hai** nhánh (`TestModelDiVaoCaHaiDieuKien`); selfcheck kiểm argv của hai nhánh giống nhau. Không truyền `--model` thì cả hai đọc cùng một tệp cấu hình. |
| 2 | model nền sau alias đổi **giữa** đợt đo | Không chặn được bằng mã: luồng JSON không mang tên model. Giảm thiểu: `--note` là lời khai có ngày, và ràng buộc vận hành "không đổi model khi một cột đang chạy". Đã ghi trong giao thức. |
| 3 | hai cột nhận đề bài khác nhau | Selfcheck so **từng byte** prompt của hai nhánh. Nhánh trần cũng được nói "guard chặn ghi ngoài phạm vi" dù không có guard — **có chủ ý**: cùng đầu vào là điều kiện của so sánh. |
| 4 | trần lượt khác nhau giữa hai cột (hoặc so với cột 1) | `TRAN_LUOT = 0` cho cả hai nhánh, có phép thử ghim đếm đúng hai chỗ dùng. |
| 5 | tệp do harness ghi làm lệch `files`/`lines` | Commit ứng viên loại `_bmad-output`, `.claude`, `.aisef`, `.opencode` (đã có từ C-1). |
| 6 | phiên hỏng hạ tầng bị chấm thành lượt trượt của agent | § 6. |
| 7 | hai tiến trình bench xoá cây của nhau | Khoá (§ 1.3). |
| 8 | cột 2 xoá bằng chứng của cột 1 | `AISEF_BENCH_DIR=.bench-c2`. |
| 9 | mã của hệ đang đo đổi giữa đợt | Không chặn được (C-1 § O-11: mỗi chunk nạp mã lúc nó khởi động). Giảm thiểu: **đừng commit vào nhánh chính trong lúc đợt đo chạy**, và ghi lại nếu có. |
| 10 | `sec-2` đổi byte đề bài ở v1.4 | Cột 2 chạy trên v1.4, nên `sec-2` của cột 2 **không so trực tiếp** với `sec-2` của cột 1. 11 task còn lại so được. Đã ghi trong giao thức. |
| 11 | máy không rảnh làm `duration_ms` phồng lên | Không chặn được. Khai ra khi báo cáo; `turns` và kết cục không phụ thuộc tải máy. |

Thứ tôi **không** coi là confound sau khi đo: HTTP 524. Bản ghi 524 của dự án
này là hiện tượng của `stream:false` (Cloudflare cắt một sinh dài không có byte
nào chảy) trên đường HTTP trực tiếp, **không** nằm trên đường đi của bench — ở
đây CLI sở hữu transport và luôn stream (`--format json`, một sự kiện một dòng).
Không có `_parse_sse` nào trong kho này. Nếu 524 vẫn xảy ra, nó về như một sự
kiện `error` mang `statusCode` → `raw["api_error_status"]` → `exit_status_of` trả
`infra` → được chạy lại một lần. Đường ấy có phép thử.

## 6. Hạ tầng hỏng ≠ task trượt: cách phân biệt

Ba tầng, không một tầng nào sửa scorer:

1. **Nhận dạng.** `parse_json_events` xếp bốn kiểu hỏng vào nhóm hạ tầng: cú
   pháp gọi công cụ CLI không phân giải được (`<minimax:tool_call>`, kiểu hỏng áp
   đảo — 31 %/25 % phiên ở C-1, 32 %/22 % ở C-1b), lỗi nhà cung cấp mang
   `statusCode` (502/524…), 429, và timeout. `exit_status_of` chuẩn hoá thành
   `timeout` / `infra` / `rate_limit` = `INFRA_STATUSES`.
2. **Chạy lại.** `INFRA_RETRIES = 1`: phiên hỏng hạ tầng được chạy lại **một**
   lần trên cây làm việc mới, và `bench:infra_retry` vào bằng chứng. Một lần là
   đủ để không mất lượt, và đủ nhỏ để nhà cung cấp đang hỏng không kéo đợt đo dài
   vô hạn.
3. **Ghi lại.** Mới từ bản này: `exit_status` + `infra_retries` nằm trong **từng
   dòng** `results.jsonl` và được tổng kết trong mục "Token và kiểu kết thúc".

Cái tôi **không** làm: loại phiên hỏng hạ tầng khỏi `pass@1`. Định nghĩa "một
lượt" đã đóng băng, và tự ý đổi nó sau khi thấy dữ liệu là đúng cái giao thức cấm.
Người đọc có đủ số để tự làm phép kiểm độ nhạy — và phải làm, vì C-1b đo được
**6/9 lượt có phiên bị cắt vẫn PASS** (agent đã ghi xong bản sửa trước khi phiên
chết), nên "loại hết phiên bị cắt" không phải một phép sửa trung tính.

## 7. Tiền đăng ký — viết trước khi có dữ liệu

Neo từ ba đợt trước, để ngưỡng dưới đây không phải bốc ra: v0.3.0 (frontier, task
dễ) 100 % vs 100 %; C-1 delta **−0,06**; C-1b delta **+0,06**. Hai cohort cùng
model, cùng harness, hiệu số **đổi dấu** — đó là hình dạng của nhiễu, và nó định
nghĩa dải nhiễu đã đo được: **±0,08**. Thứ nhất quán duy nhất qua hai đợt là cái
giá: turn +44 % / +27 %, giây +51 % / +39 %.

### Thế nào là harness **mua được** cái gì

Phải đạt **cả ba**:

1. **Hướng.** ≥ 3 trong 12 task có AISEF pass@1 > trần pass@1 cách nhau ≥ 1/3 (một
   lượt), **và** ≤ 1 task lệch theo hướng ngược lại. Tổng delta ≥ +0,08, tức ra
   ngoài dải nhiễu đã đo.
2. **Sống sót phép kiểm độ nhạy.** Dấu của hiệu số giữ nguyên khi đọc lại theo hai
   cách: (a) chỉ các lượt có `exit_status = ok`, (b) toàn bộ lượt. Nếu đổi dấu
   giữa hai cách đọc thì thứ đo được là tỉ lệ phiên bị cắt, không phải harness.
3. **Cơ chế nêu được tên.** Với mỗi task thắng, chỉ ra được guard nào chặn cái gì
   (`guard_block > 0` trên đúng task ấy, hoặc `analyze` cho thấy nhánh trần ghi
   ngoài phạm vi / "xong giả" ở đúng task ấy trong khi nhánh AISEF không). Một
   hiệu số không có cơ chế là một hiệu số chờ cohort sau xoá đi.

Có một đường thắng **không qua `pass@1`**, và nó được tính: nếu nhánh trần ghi ra
ngoài `write_scope` hoặc tuyên bố xong khi chưa xong ở ≥ 2 task mà nhánh AISEF
không, thì harness chặn được một lớp thiệt hại mà `pass@1` không nhìn thấy. C-1
đo cả hai nhánh **0 lượt** ghi ngoài phạm vi, nên đây là một dự đoán có thể sai,
và nếu nó lại là 0/0 thì phải nói là 0/0.

### Thế nào là harness **không mua được gì**

- |tổng delta| ≤ 0,08 **và** không task nào lệch ≥ 2/3 theo bất kỳ hướng nào;
- 0 lượt ghi ngoài phạm vi và 0 lượt "xong giả" *riêng* ở nhánh trần;
- token/lượt của nhánh AISEF > nhánh trần — cái giá có thật và đo được, trong khi
  lợi ích thì không.

Đây là kết cục **có khả năng nhất** theo ba đợt trước, và nó vẫn là một kết quả
phải báo. Ai muốn trích C-1b (+0,06) làm bằng chứng bán hàng thì phải trích cả
C-1 (−0,06) cùng chỗ.

### Thế nào là **không kết luận được**

Bất kỳ điều nào dưới đây, và khi đó báo cáo dừng ở "không kết luận được" chứ
không đi tiếp tới một hiệu số:

1. > 1/3 số lượt kết thúc với `exit_status ∈ INFRA_STATUSES` **sau** lần chạy lại
   — tỉ lệ hỏng của cặp model↔CLI lớn hơn mọi hiệu ứng đang tìm;
2. ≥ 8/12 task cùng 1,00/1,00 hoặc cùng 0,00/0,00 (trần hoặc sàn của bộ dữ liệu —
   C-1 đã ở hình dạng này: 9/12 không nói được gì). Trần dữ liệu **là** một kết
   quả và phải được báo như một kết quả;
3. model nền đổi giữa đợt, hoặc đợt bị chia qua nhiều ngày;
4. `MANIFEST.sha256` không còn khớp;
5. < 12 task chạy đủ thiết kế (cắt vì `--max-minutes`, vì bị kill, vì gì cũng vậy)
   — bảng bị cắt phải đọc ra là bị cắt.

**Dừng sớm, chốt trước** (giao thức đã khai): nếu **hai task đầu** đều 6/6 phiên
PASS ở cả hai điều kiện thì model mới cũng chạm trần bộ dữ liệu này — dừng, báo,
đừng đốt thêm bảy giờ để lấy một cột toàn số 1,00.

### Dự đoán, để sau này đối chiếu được

Với M3 (model được khai là mạnh hơn M2.7): nhiều task chạm trần hơn C-1 (đoán
7–9/12 hoà ở 1,00), tổng delta trong [−0,08, +0,08], và **tỉ lệ token AISEF/trần
1,2–1,6×** (suy từ tỉ lệ turn +44 %/+27 %). Nếu token của nhánh AISEF ra **thấp
hơn** nhánh trần thì đó không phải phát hiện — đó là báo động về đường ống, vì
nhánh AISEF nhận cùng đề bài **cộng** thông điệp guard, nên nó không thể tiêu ít
context hơn.

## 8. Thứ tôi cố ý **không** làm

- **Không back-fill token cho C-1/C-1b.** Token của chúng nằm trong bằng chứng
  (§ 1.1) và `analyze` đọc được — nhưng thêm một cột vào bảng của `analyze` làm
  câu "dựng lại bảng bằng `python3 -m tests.bench analyze`" trong hai báo cáo đã
  đóng thành sai. Muốn con số ấy thì tính trong một tài liệu mới, đừng đổi công cụ.
- **Không đổi `pass@1` để loại phiên hỏng hạ tầng** (§ 6).
- **Không đổi `run.timeout_seconds`, `TRAN_LUOT`, `--attempts`, thứ tự task.** Mỗi
  cái là một biến cột 1 đã cố định.
- **Không chạy model.** Không `aisef run`, không `aisef plan`, không `tests.bench
  run*` với client thật. Con số duy nhất trong tài liệu này đến từ đợt đo cũ, từ
  bằng chứng trên đĩa, và từ selfcheck với fixture.

## 9. Kiểm lại trước khi bàn giao

```
ruff check .                                  # All checks passed!
python3 -m pytest -q                          # 2532 passed, 80 skipped, 1025 subtests
python3 -m pytest tests/bench/test_bench.py -q # 63 passed, 1 skipped (nền: 53 passed)
python3 -m tests.bench selfcheck              # 19/19
python3 -m pytest tests/bench/test_bench.py -k manifest -q   # 8 passed
```

Phép thử mới đều được chạy **đỏ trước, xanh sau**: 6/7 đỏ trước khi có mã (phép
thứ bảy — "không có token thì không in mục tài nguyên" — xanh từ đầu, đúng như
phải thế), và `--max-minutes` đỏ với `SystemExit: 2` (cờ chưa tồn tại) trước khi
có cờ.

---

## Đoạn cho CHANGELOG.md

**The bench ledger records what the run actually spent, and what actually ended
it.** The provider behind `mycombo` reports `cost_usd = 0` for every step, so the
C-1 and C-1b reports fell back to turns and wall-clock and called the dollar
column absent. Tokens were never absent: the evidence store held 98 392 input,
1 487 output and 581 444 cache-read tokens for a single session that cost $0.00.
A bench row now carries those four token counts, plus the normalised exit status
and the number of infrastructure retries it took, and the report grows a **"Token
và kiểu kết thúc"** section that says in one line that $0.00 is an absent price
rather than an absent resource. The section appears only when rows actually carry
tokens, so every closed cohort's table still reproduces byte-for-byte. Two
measurement hazards close with it: a FAIL caused by the CLI cutting the session
mid-run is now distinguishable from a FAIL caused by the agent, inside the row
itself rather than by cross-referencing OpenCode's 3.5 GB session store, and the
infrastructure-retry path declared during C-1b — which fired zero times there —
has its first behavioural test. `run`/`run-both` now hold an exclusive lock on
the bench directory, because two concurrent runs delete each other's kept
worktrees, and `run-both --max-minutes` gives the run a stopping rule that works
for a provider whose cost is always zero. Scorer, dataset bytes and outcome
taxonomy are untouched — `MANIFEST.sha256` still matches exactly. A new
`python3 -m tests.bench selfcheck` drives the real pipeline against a fake
`opencode` binary in ~13 seconds and 19 checks, proving the two columns differ in
exactly the harness and nothing else — same model argv, byte-identical prompt,
guard plugin and `AISEF_*` env on one side only — without spending a single model
call, and labelled **KHÔNG PHẢI KẾT QUẢ ĐO** at both ends of its output.
