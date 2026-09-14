# Giao thức tuyển cặp model↔CLI — bản ghim theo digest (G5.3)

**Trạng thái: đã ghim 2026-09-14, trước khi một phiên tuyển nào chạy.** Đây là
giao thức của đợt tuyển cặp mà [phán quyết 3](PROJECT-CLOSURE-GATE.md) của chủ dự
án đòi phải chạy **trước** cột 2. Không một lượt gọi model nào được tiêu để viết
tài liệu này, và không một phiên tuyển nào tồn tại khi nó được ghim.

Lý do có tài liệu này thay vì một hằng số trong mã: chủ dự án nói thẳng — *"Do
not inspect qualification results and then choose the threshold."* Một ngưỡng còn
sửa được sau khi số liệu về là một ngưỡng hậu nghiệm, và một ngưỡng hậu nghiệm
dán nhãn tiền đăng ký là đúng thứ cả tiêu chí G5.1 tồn tại để chặn. Vì thế ngưỡng,
cỡ mẫu, định nghĩa và luật phán quyết nằm trong **vùng ghim** ở §2, và số học dẫn
ra chúng nằm **cùng chỗ** — người đọc sau phải thấy được cái bar này có trước dữ
liệu, không phải tin rằng nó có trước.

| | |
|---|---|
| vùng bị ghim | §2, giữa hai mốc `QUAL-FROZEN` |
| digest (sha256) | ghi ở `docs/closure-gate.json` → G5.3 → `protocol_sha256`, **không** ghi trong tệp này |
| cơ chế ghim | dùng lại nguyên cơ chế của [BENCH-PREREGISTRATION-C2.md](BENCH-PREREGISTRATION-C2.md) §1 — xem §1 dưới đây |
| bản mã của vùng ghim | `tests/bench/_qualify.py` (hằng số đầu tệp) |
| phép kiểm tham chiếu | `tests/test_meta.py::TestGiaoThucTuyenCapBiGhim` |
| báo cáo đọc bởi probe G5.3 | `docs/BENCH-PAIR-QUALIFICATION.md`, sinh bằng lệnh ở §4 |

## 1. Cơ chế ghim — dùng lại, không phát minh lần hai

Cơ chế đã có và đã hoạt động:
[BENCH-PREREGISTRATION-C2.md](BENCH-PREREGISTRATION-C2.md) §1. Tài liệu này theo
**đúng** cơ chế ấy, chỉ đổi tên mốc, nên phần biện minh không được chép lại ở
đây — nó nằm ở §1.2 (vì sao ghim vùng chứ không cả tệp), §1.3 (vì sao từng byte
chứ không chuẩn hoá nội dung) và §1.4 (vì sao digest sống ở tệp khác) của tài liệu
ấy, và đọc nguyên văn cho tài liệu này.

Ba khoản cụ thể:

1. **Vùng ghim** = văn bản giữa `<!-- QUAL-FROZEN:BEGIN -->` và
   `<!-- QUAL-FROZEN:END -->`, đúng **một** cặp mốc trong tệp.
2. **Chuẩn hoá đúng hai khoản:** `\r\n` và `\r` → `\n`; cắt dòng trống ở đầu và
   cuối vùng. Ngoài hai khoản ấy, **từng byte** — kể cả một lỗi chính tả. Trong
   vùng ghim không có lần sửa nào hợp lệ: pin vỡ thì việc phải làm là hoàn nguyên
   văn bản, không phải ghi lại digest.
3. **Digest sống ở `docs/closure-gate.json`**, khoá `protocol_sha256` của tiêu chí
   G5.3, và **không** được nhắc lại ở bất cứ đâu trong tệp này. Một digest ghi
   trong chính tệp nó ghim thì người sửa văn bản cập nhật cả hai trong một động
   tác và không để lại dấu vết — nó không ghim gì.

Dựng lại giá trị:

```sh
python3 - <<'PY'
import hashlib, pathlib, re
CT = r"(?s)<!--\s*QUAL-FROZEN:BEGIN\s*-->\n(.*?)\n<!--\s*QUAL-FROZEN:END\s*-->"
f = "docs/BENCH-PAIR-QUALIFICATION-PROTOCOL.md"
t = pathlib.Path(f).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
v = re.findall(CT, t)
assert len(v) == 1, f"{f}: {len(v)} vùng ghim, phải đúng 1"
print(hashlib.sha256(v[0].strip("\n").encode("utf-8")).hexdigest())
PY
```

**Thứ pin này không chứng minh được**, nói ra để một digest khớp không đọc thành
nhiều hơn nó là: nó ghim **nội dung**, không ghim **bối cảnh** — thêm một câu ngay
ngoài mốc để đọc lại §2 theo hướng khác thì digest vẫn khớp; và nó không chứng
minh văn bản được viết trước dữ liệu, chỉ làm mọi lần sửa **sau này** lộ ra. Thứ
định ngày là commit đầu tiên của tệp này, và commit ấy phải đứng **trước** dòng
đầu tiên của sổ phiên (`closure-evidence/bench-pair-qualification.jsonl`). Trong
một kho một người thì ngày commit vẫn sửa được — đó là giới hạn thật của mọi pin
ở đây, và nó được nói ra chứ không che.

## 2. Giao thức — nguyên văn, không sửa

<!-- QUAL-FROZEN:BEGIN -->
### 2.1 Cặp hợp lệ

Một **cặp** là (model, client). Được vào đợt tuyển:

| cặp | ghi chú |
|---|---|
| (`mycombo` → model nền do người vận hành khai, `opencode`) | cặp mà lệnh phóng đã đăng ký nêu tên; đo được theo §2.2 |
| (model mặc định của Claude Code, `claude`) | được vào, nhưng §2.2 làm nó luôn ra `INCONCLUSIVE` cho tới khi có bộ phát hiện phiên bị cắt cho luồng của nó |

`simulated-weak` **không** là một cặp: nó không có model, và chiến lược của nó là
hàm thuần của số thứ tự lượt. Một cặp mới chỉ vào được bằng một **bản bổ sung có
ngày** viết ngoài vùng ghim này, và tên của nó phải được khai bằng `--note` —
`mycombo` là một alias, nên đổi mô hình nền phía nhà cung cấp không đổi một ký tự
nào trong dữ liệu.

Người vận hành khai tên model **trước** khi chạy. Một đợt tuyển không có lời khai
ấy không đọc được về sau, và công cụ từ chối chạy.

### 2.2 Thế nào là một **phiên bị cắt**

Định nghĩa vận hành, không phải mô tả: một phiên là **bị cắt** khi phần văn bản
cuối của nó mang cú pháp gọi công cụ mà CLI không phân giải được
(`<\w+:tool_call>` hoặc `<invoke name=`), nên adapter đặt `RunResult.error` =
*"client could not parse the model's tool call; the session ended there"* cùng
`retryable`, và `exit_status_of` xếp phiên ấy vào `infra`. Đo trên C-1: **11/11**
phiên mang chữ ký này có nó ở phần văn bản **cuối cùng**, không phiên nào hồi
phục (`BENCH-OBSERVATIONS-C1.md` § O-7).

Nên, bằng đúng hai điều kiện đọc được từ một dòng sổ:

    bị cắt  ⇔  exit_status ∈ INFRA_STATUSES  ∧  dấu hiệu trên có trong `error`

Bộ phát hiện ấy **chỉ tồn tại cho `opencode`** (`aisef/clients/opencode.py`). Với
client không có nó, tỉ lệ cắt **không đo được**, và phán quyết là `INCONCLUSIVE` —
**không bao giờ** `QUALIFIED`. Một tiêu chí không được thoả bằng sự vắng mặt của
chính phép đo của nó; suy "không phát hiện được" thành "tỉ lệ 0 %" là đúng lỗi mà
lỗi 86 đã mắc (phiên bị cắt vẫn để CLI thoát 0 nên `ok=True`).

### 2.3 Trần tỉ lệ cắt: **1/6 ≈ 0,167** — và số học dẫn ra nó

Thiết kế cột 2 đã đăng ký: 12 task × 3 lượt × 2 nhánh = **72 lượt**, tức **36
lượt mỗi nhánh**, với `INFRA_RETRIES = 1` (phiên hỏng hạ tầng được chạy lại đúng
một lần, không được chấm).

Với tỉ lệ cắt mỗi phiên là `p`, một **lượt** chỉ bị *chấm trên* một phiên bị cắt
khi **cả hai** phiên của nó bị cắt — xác suất `p²`. Số lượt nhiễm kỳ vọng mỗi
nhánh là `36 p²`.

Ngân sách là **≤ 1 lượt nhiễm mỗi nhánh**, và con số 1 ấy có hai cái neo đo được,
không phải một lựa chọn:

1. **Neo đã đo.** Cả **ba** lượt trượt của C-1b đều là phiên bị CLI cắt, và cohort
   ấy in ra `Δ = +0,06`. Ba lượt nhiễm trong một nhánh đã **tự sinh ra** một hiệu
   số cùng cỡ với cái đang đi tìm.
2. **Neo đã đăng ký.** Mốc "mua được" là trung bình delta theo task ≥ `+0,08`.
   Một lượt đổi kết cục làm delta của một task đổi `1/3`, tức trung bình đổi
   `(1/3)/12 = 0,028`. Vậy `+0,08` **chính là** 3 lượt đổi kết cục trên 36 — hiệu
   ứng nhỏ nhất mà thiết kế này phân giải được là 3 lượt.

Một phần ba của 3 là 1. Nên:

    36 p² ≤ 1   →   p ≤ 1/6 = 0,1667

**Đối chiếu với dải đã đo (22–32 % trên OpenCode/mycombo):** `p = 0,22` → 1,74
lượt nhiễm mỗi nhánh; `p = 0,32` → **3,69**. Tức ở đầu trên của dải đã đo, lượng
nhiễm kỳ vọng **bằng đúng** 3 lượt đã sinh ra `+0,06` của C-1b. Trần 1/6 vì thế
loại dải đã đo **bằng số học**, không bằng lời.

**Vì sao không lấy con số duy nhất đã đăng ký.** Điều kiện "không kết luận được"
số 1 của tiền đăng ký là *"> 1/3 số lượt kết thúc với `exit_status ∈
INFRA_STATUSES` sau lần chạy lại"*. Dịch sang `p`: `p² > 1/3` → `p > 0,577`. Một
trần 0,577 **nhận** đúng cặp 22–32 % đã mua 0 cặp thông tin, nên nó không thể là
trần tuyển cặp — và chính tiền đăng ký nói nó không phải (§3.5 mục 2).

**Vì sao không lấy chặt hơn.** Đọc điều kiện "không kết luận được" số 5 (*"< 12
task chạy đủ thiết kế"*) theo nghĩa chặt nhất — không lượt nào được kết thúc bằng
hạ tầng sau chạy lại — thì để 9 trong 10 đợt sạch cần `(1 − p²)^72 ≥ 0,9`, tức
`p ≤ 0,038`. Không một đợt tuyển có biên nào **chứng nhận** nổi 0,038: 28 phiên
sạch liên tiếp vẫn để lại biên trên 95 % là 0,102 (§2.4). Một trần thấp hơn thứ
cỡ mẫu quyết được là một trần luôn ra `NOT_QUALIFIED` bất kể cặp tốt hay xấu — đó
không phải phép đo. Vậy 1/6 là cái chặt nhất trong ba mà một đợt tuyển có biên
**quyết được**.

**Trần thứ hai, không phải của tôi.** Mọi kiểu hỏng hạ tầng gộp lại
(cắt + `timeout` + `rate_limit` + `infra`) trên số phiên hợp lệ phải **≤ 1/3** —
đây là chính con số của tiền đăng ký ở trên, đọc trên phiên thay vì trên lượt. Một
cặp không cắt phiên nào nhưng hỏng 40 % vì timeout cũng không dùng được, và trần
1/6 một mình không nói gì về chuyện ấy.

### 2.4 Cỡ mẫu: **28 phiên hợp lệ mỗi cặp** — và số học dẫn ra nó

Luật quyết định: đạt khi `số phiên bị cắt / số phiên hợp lệ ≤ 1/6`, tức
`≤ ⌊N/6⌋` phiên bị cắt.

Hai giả thuyết cần tách: một cặp **tốt** ở `p = 0,05` và một cặp **thuộc dải đã
đo** ở `p = 0,30`. Yêu cầu **cả hai** sai số ≤ 5 %: cặp 0,30 lọt qua ≤ 5 %, cặp
0,05 bị loại ≤ 5 %. Nhị thức chính xác:

| N | ngưỡng chấp nhận ⌊N/6⌋ | cặp 0,30 lọt qua | cặp 0,05 bị loại |
|---:|---:|---:|---:|
| 17 | 2 | 0,077 | 0,050 |
| 23 | 3 | 0,054 | 0,026 |
| 27 | 4 | 0,059 | 0,010 |
| **28** | **4** | **0,047** | **0,012** |

**28 là N nhỏ nhất thoả cả hai** — 17, 23 và 27 đều để cặp 0,30 lọt qua trên
5 %. Vì thế 28 vừa là cỡ mẫu, vừa là **sàn**: dưới 28 phiên hợp lệ thì hai sai số
trên không còn đúng, nên một cohort thiếu phiên là `INCONCLUSIVE`, **không** phải
`NOT_QUALIFIED`.

**Khoảng, không chỉ một điểm.** Báo cáo in biên trên Clopper–Pearson một phía
95 % cho tỉ lệ quan sát được: `0/28` → `p ≤ 0,102`; `4/28` → `p ≤ 0,298`;
`5/28` → `p ≤ 0,339`. Đọc ra được: một cohort **hoàn hảo** cũng chỉ nói "không
loại được 10 %", nên "đạt" ở đây nghĩa là *"không nhiễm ở mức làm hỏng phép đo"*,
**không** nghĩa là "sạch".

**Giá, bằng đơn vị nhà cung cấp này thật sự báo.** 28 phiên × 258 s/phiên (đo trên
C-1, `bug-a2-state-4`) ≈ **2,0 giờ phiên** và ≈ **36,5 triệu token**: ≈ 35 % giờ
phiên và ≈ 41 % token của cột 2 đã đăng ký (72 lượt, 5,7 giờ, 88,9 M token trên
C-1). Cột USD của nhà cung cấp này là **0,00 ở mọi bước** — vắng mặt **giá**,
không phải vắng mặt tài nguyên; đọc nó thành "miễn phí" là đọc sai cột.

**Dừng sớm, một phía.** Khi số phiên bị cắt vượt `⌊N/6⌋`, không phiên còn lại nào
cứu được phán quyết nữa, nên đợt **dừng ngay** và ghi `NOT_QUALIFIED`. Một cặp
30 % vì thế thường tốn ≈ 17 phiên (≈ 1,2 giờ) chứ không 28. Không có luật dừng
sớm theo hướng ngược: "đạt" đòi đủ mẫu số.

### 2.5 Task để tuyển: **`bug-a2-state-4`**, một task, và vì sao

Tỉ lệ cắt là tính chất của **cặp**, không của task — nhưng **độ dài phiên** là
tính chất của task, và phiên dài hơn thì nhiều lượt gọi công cụ hơn, tức nhiều cơ
hội hơn để model in ra cú pháp CLI không phân giải được. Nên chọn task là chọn
mức thiên của phép đo, và nó phải được khai trước.

Ba tiêu chí, theo thứ tự:

1. **Không thiên xuống.** Task rẻ nhất của bộ 12 (`sec-3`: 9,8 turn · 68 s mỗi
   phiên) cho một `p` thấp hơn thực tế của cohort. `state-4` là 22,8 turn · 258 s
   mỗi phiên, **trên** trung vị của 12 task đã đăng ký (19,8 turn · 248 s).
2. **Không mua nổi thông tin, nên không thể bị đọc thành thông tin.** `state-4` là
   1,00/1,00 ở cả hai nhánh tại C-1, nằm trong nhóm 25/30 task chưa bao giờ tách
   được hai nhánh. Phiên tuyển vì thế không thể bị trích như một kết quả A/B —
   một task tuyển **không cần** phân biệt được, và tốt hơn là không.
3. **Cùng hình dạng với cohort.** Nó nằm trong 12 task đã đăng ký, nên đề bài,
   phạm vi ghi và bộ công cụ của phiên tuyển là đúng của cột 2.

Một task, không phải ba: mục tiêu là biên có kiểm soát, và ba task chia đôi cỡ mẫu
mỗi task thì không task nào quyết được gì. Phiên tuyển chạy ở **nhánh AISEF**
(guard + env), không nhánh trần: C-1 đo tỉ lệ cắt của nhánh AISEF gấp ≈ 2 lần
nhánh trần (27 % so với 14 %), và một cổng hợp lệ không được tuyển cặp trên chân
dễ hơn của nó.

### 2.6 Chạy lại, và cách xử lý từng kiểu hỏng

**Đợt tuyển không chạy lại phiên nào** (`INFRA_RETRIES` hiệu lực = 0). Phép đo cần
tỉ lệ cắt **thô** của từng phiên; chính sách chạy lại của cohort (1 lần) đi vào
*số học* của ngưỡng ở §2.3 (`p²`), không đi vào phép đo. Một phiên = một dòng sổ,
ghi ngay sau khi phiên kết thúc.

| trạng thái thoát | vào mẫu số? | cột |
|---|---|---|
| có dấu hiệu cắt (§2.2) | **có** | `phiên bị cắt` |
| `timeout`, `rate_limit`, `infra` không có dấu hiệu cắt | **có** | `hỏng hạ tầng` — chịu trần 1/3 ở §2.3 |
| `auth`, `permission` | **không** | `loại khỏi mẫu`, đếm và nêu tên |
| `max_turns` | **có** | phiên hợp lệ, không cắt |
| `ok`, `context`, `cost`, `error` | **có** | phiên hợp lệ, không cắt |

`auth` và `permission` bị loại vì chúng không là tính chất của cặp mà là việc của
người vận hành: một khoá bị từ chối sẽ bị từ chối y như thế ở lần sau, và
`exit_status_of` đã xếp `auth` **trước** hạ tầng đúng vì lý do ấy. Để chúng vào
mẫu số là để một khoá hết hạn đọc thành "cặp này sạch". Chúng bị đếm và nêu tên
chứ không bị giấu: nếu chúng làm phiên hợp lệ tụt xuống dưới 28 thì phán quyết là
`INCONCLUSIVE` và lý do được in ra.

`max_turns` **không** tính là hạ tầng — `exit_status_of` xếp nó trước hạ tầng có
chủ ý, và trần lượt của phiên tuyển là 0 (chỉ đồng hồ chặn) đúng như cohort, nên
nó không được nổ; nếu nó nổ thì đó là một sự thật về cặp, ghi vào cột phiên hợp lệ.

Trần thời gian cả đợt là **180 phút** (1,5× dự phóng 2,0 giờ). Không có nó thì
trần thật là 28 × `run.timeout_seconds` = 14 giờ. Đợt bị trần cắt cho ra
`INCONCLUSIVE` nếu chưa đủ 28 phiên hợp lệ, không cho ra `NOT_QUALIFIED`.

### 2.7 Ba kết cục, đúng ba

| kết cục | điều kiện |
|---|---|
| `QUALIFIED` | client đo được (§2.2) **và** phiên hợp lệ ≥ 28 **và** tỉ lệ cắt ≤ 1/6 **và** tỉ lệ hỏng hạ tầng ≤ 1/3 |
| `NOT_QUALIFIED` | phiên hợp lệ ≥ 28 **và** một trong hai tỉ lệ vượt trần (kể cả khi biết được nhờ dừng sớm) |
| `INCONCLUSIVE` | client không đo được, **hoặc** phiên hợp lệ < 28 vì bất cứ lý do gì (phiên bị loại, trần thời gian, bị kill) |

Nối vào cổng đóng dự án: **≥ 1 cặp `QUALIFIED`** → G5.3 `PASSED`, cột 2 chạy trên
cặp được chọn theo §2.8. **Không cặp nào `QUALIFIED`** → G5.3 `WAIVER_PENDING`:
đợt 72 lượt **không** chạy, báo cáo nêu đúng cái đã thử và vì sao từng cặp trượt,
và việc tiếp theo là quyết định miễn trừ của chủ dự án — không phải một đợt đo.
`INCONCLUSIVE` **không** là `NOT_QUALIFIED` và cũng **không** là một giấy phép:
nó chặn y như nhau.

### 2.8 Nhiều cặp cùng đạt thì chọn cái nào

Khai trước để không phải chọn sau khi thấy số: **tỉ lệ cắt thấp nhất**; bằng nhau
thì **ít hỏng hạ tầng hơn**; bằng nhau thì **thứ tự chữ của (client, model)**. Ba
khoản, quyết định được bằng máy, không có khoản "người đo thấy cặp nào hợp hơn".

### 2.9 Thứ giao thức này **không** chứng minh được

Nói ra, để một dòng `QUALIFIED` không đọc thành nhiều hơn nó là:

1. **Tỉ lệ cắt không dừng tại chỗ.** Nó là tính chất của một nhà cung cấp sau một
   alias, và nhà cung cấp đổi mô hình nền mà không đổi một ký tự nào trong dữ
   liệu. Đợt tuyển **định ngày** cho lời khai, không gia hạn nó. Cột 2 chạy cách
   đợt tuyển càng xa thì lời khai càng yếu, và khoảng cách ấy phải được ghi.
2. **Nó không nói cặp ấy giải được gì.** Ở đây không có scorer, không `pass@1`.
   Một cặp đạt vẫn có thể chạm trần bộ dữ liệu — 25/30 task chưa bao giờ tách
   được hai nhánh — và khi ấy cột 2 phải báo "không kết luận được", đúng như tiền
   đăng ký đã khai.
3. **28 phiên trên một task.** Task được chọn để không thiên xuống (§2.5), nhưng
   một task có phiên dài hơn `state-4` nhiều vẫn có thể cắt nhiều hơn. Báo cáo in
   tên task để chỗ hở này nhìn thấy được, chứ không lấp nó bằng lời.
4. **Nó không chứng nhận 0,038** — mức mà điều kiện "không kết luận được" số 5 đọc
   theo nghĩa chặt nhất đòi. Ngay cả `0/28` chỉ cho biên trên 95 % là 0,102.

### 2.10 Bảng hằng số — bản mã phải khớp từng con số

| hằng số | giá trị |
|---|---|
| `NGUONG_TI_LE_CAT` | 1/6 |
| `SO_PHIEN_TUYEN` | 28 |
| `NGUONG_HONG_HA_TANG` | 1/3 |
| `TASK_TUYEN` | bug-a2-state-4 |
| `TRAN_PHUT` | 180 |
| `CLIENT_DO_DUOC` | opencode |

Bản mã là `tests/bench/_qualify.py`. Đổi một con số ở đó mà không ghim lại văn bản
này thì `tests/test_meta.py::TestGiaoThucTuyenCapBiGhim` đỏ; ghim lại thì digest
đổi và `git log -p docs/closure-gate.json` chỉ đúng một dòng. Đó là cách một hằng
số vẫn **sửa được bởi người** mà không sửa được trong im lặng.
<!-- QUAL-FROZEN:END -->

## 3. Chín khoản chủ dự án đòi: cái đã có, cái tài liệu này nói lần đầu

Phán quyết bổ sung (2026-09-14) liệt kê chín khoản phải được khai **trước khi có
dữ liệu**. Bảng dưới nói khoản nào tiền đăng ký cột 2 đã chốt, khoản nào chưa —
để không ai phải đọc hai tài liệu rồi đoán.

| # | khoản | [BENCH-PREREGISTRATION-C2.md](BENCH-PREREGISTRATION-C2.md) đã chốt | tài liệu này |
|---|---|---|---|
| 1 | cặp hợp lệ | **một phần**: §5 khai `--client opencode` + model mặc định sau `mycombo` như *phương pháp đã đăng ký*, nhưng §3.5 mục 1 nói rõ cặp chỉ được chốt **sau** G5.3 | chốt danh sách vào đợt tuyển, và khai luôn rằng `claude` vào được nhưng không đo được (§2.1–2.2) |
| 2 | cỡ mẫu tối thiểu mỗi cặp | **không** | 28, với số học (§2.4) |
| 3 | thế nào là một phiên bị cắt | **một phần**: §3.1 gọi tên hiện tượng ("phiên bị CLI cắt") và trỏ tới C-1 § O-7; định nghĩa vận hành thì nằm trong mã (`aisef/clients/opencode.py`), chưa ở tài liệu nào | viết thành hai điều kiện đọc được từ một dòng sổ, và nói rõ client nào không có bộ phát hiện (§2.2) |
| 4 | xử lý timeout / infra / permission | **một phần**: điều kiện "không kết luận được" số 1 gộp mọi `INFRA_STATUSES` trên **lượt** của đợt 72 | tách ba cột và nói rõ cái nào vào mẫu số, cái nào không, kèm lý do (§2.6) |
| 5 | chính sách chạy lại | **cho cohort**: `INFRA_RETRIES = 1`, phiên hỏng được chạy lại, không được chấm | cho **đợt tuyển**: 0 lần chạy lại; chính sách của cohort đi vào số học `p²`, không vào phép đo (§2.6, §2.3) |
| 6 | trần tỉ lệ cắt | **không** — §3.5 mục 2 nói thẳng: *"Tài liệu này **không** đặt ngưỡng đó"* | 1/6, suy từ 36 lượt/nhánh × `p²` ≤ 1 lượt nhiễm, với hai neo đo được (§2.3) |
| 7 | số phiên hợp lệ tối thiểu | **không** | 28 — cùng con số với cỡ mẫu, vì dưới nó hai sai số của luật không còn đúng (§2.4) |
| 8 | luật chọn khi nhiều cặp đạt | **không** | ba khoản quyết định được bằng máy (§2.8) |
| 9 | `QUALIFIED` / `NOT_QUALIFIED` / `INCONCLUSIVE` | **không** — phán quyết 3 nói "đạt/không đạt → `WAIVER_PENDING`", chưa có kết cục thứ ba | ba kết cục và cách nối vào G5.3 (§2.7) |

Hai chỗ đáng nói thêm, cùng thuộc loại "khoảng trống được báo chứ không được lấp":

- Tiền đăng ký cột 2 gắn dự đoán của nó vào **M3**, một model chưa được nêu tên
  (§3.5 mục 1). Nếu đợt tuyển này chọn ra một cặp **khác**, tiền đăng ký ấy
  **không phủ** đợt đo cột 2, và việc đúng là một tiền đăng ký **mới** ghim theo
  cùng cơ chế — không phải một bản sửa. Tài liệu này không sửa điều đó và cũng
  không tự nhận phủ nó: nó chỉ tuyển cặp.
- Con số `±0,08` vẫn quyết được vì nó là một con số, nhưng câu biện minh "tức ra
  ngoài dải nhiễu **đã đo**" thì không còn đứng (§3.1 mục 3 của tiền đăng ký).
  §2.3 ở trên vì thế dùng `+0,08` như **mốc đã đăng ký**, không như "dải nhiễu đã
  đo".

## 4. Lệnh — dự toán trước, chạy sau

```sh
cd /Users/nghinh/Downloads/projects/ai-sdlc

# 1. hoá đơn: in ra sẽ tiêu gì, KHÔNG gọi client
python3 -m tests.bench qualify --client opencode --du-toan

# 2. chứng minh đường ống bằng `opencode` GIẢ — 0 phiên thật, 0 đồng
python3 -m tests.bench qualify --tu-kiem

# 3. đợt tuyển thật (chủ dự án phóng, sau khi digest §2 đã được ghi)
AISEF_BENCH=1 python3 -m tests.bench qualify --client opencode \
    --note "mycombo→<TÊN MODEL> (khai 2026-09-14)"

# 4. dựng lại báo cáo từ sổ, không chạy phiên nào
python3 -m tests.bench qualify --bao-cao
```

Lệnh 3 lấy **cùng** khoá độc quyền với `run`/`run-both` (`.bench/bench.lock`): thứ
khoá bảo vệ là endpoint, không phải thư mục, và một đợt tuyển chạy song song với
một đợt đo làm hỏng **cả hai** phép đo. Sổ phiên nằm ở `.aisef-qual/` — **không**
ở `.bench*/`, vì phiên tuyển không phải dữ liệu cohort và trộn chúng vào
`.bench*/results.jsonl` là đúng thứ G5.2 tồn tại để chặn. Bản được commit của sổ
là `closure-evidence/bench-pair-qualification.jsonl`, và cột `evidence` của báo
cáo trỏ vào đó chứ không vào thư mục bị gitignore.

Báo cáo **từ chối** ghi vào `docs/BENCH-PAIR-QUALIFICATION.md` khi sổ có phiên do
binary giả phát: đó là tệp probe G5.3 đọc, và một bảng sinh từ client giả ghi vào
đúng chỗ ấy là bằng chứng bịa, dù có banner.

## 5. Luật sửa tài liệu này

1. Trong vùng ghim §2: **không sửa gì**. Pin vỡ thì hoàn nguyên văn bản, không ghi
   lại digest.
2. Ngoài vùng ghim: chỉ **thêm**, và mỗi phần thêm phải có ngày và phải nói rõ nó
   là hậu nghiệm.
3. Thêm một cặp vào đợt tuyển, đổi task, đổi ngưỡng: **bản bổ sung có ngày** ở
   §6 nếu nó chưa đọc một dòng dữ liệu nào; nếu dữ liệu đã có thì đó là một giao
   thức **mới**, ghim riêng, không phải một bản sửa của §2.

## 6. Bản bổ sung (trống tới khi có)

| ngày | đổi gì | vì sao | ai |
|---|---|---|---|
| – | – | – | – |
