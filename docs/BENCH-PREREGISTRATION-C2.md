# Tiền đăng ký cột 2 — bản ghim theo digest (G5.1)

**Trạng thái: đã ghim 2026-09-14.** Đây là bản đóng của tiền đăng ký cho phép đo
cột 2 của bench A-2, promote từ một ghi chú bàn giao theo **phán quyết 7** của chủ
dự án ([PROJECT-CLOSURE-GATE.md](PROJECT-CLOSURE-GATE.md) §0, tiêu chí G5.1 ở §5).
Không một lượt gọi model nào được tiêu để viết tài liệu này.

Nguyên văn tiền đăng ký nằm ở **§2**, giữa hai mốc `PREREG-FROZEN`, và **không
được sửa** — không sửa lỗi chính tả, không làm rõ câu, không đổi ngưỡng. Một dự
đoán có sửa thì không phân biệt được với một dự đoán viết sau khi thấy dữ liệu, và
dự án này đã in ra một con số (dải nhiễu ±0,08) không sống nổi một lượt đọc lại.

Mọi thứ **học được sau** khi §2 được viết nằm ở **§3**, có ngày, tách hẳn khỏi
phần cam kết. §3 không sửa §2, không đăng ký ngưỡng mới, và không thêm một dự đoán
nào.

| | |
|---|---|
| vùng bị ghim | §2, giữa hai mốc `PREREG-FROZEN` |
| digest (sha256) | ghi ở `docs/closure-gate.json` → G5.1 → `prereg_sha256`, **không** ghi trong tệp này |
| bản lịch sử cùng nội dung | `docs/handoff/bench-real-model-wiring.md` §7, commit 2026-09-14, trước khi có một byte dữ liệu cột 2 |
| điều kiện hợp lệ của dữ liệu | G5.3 phải PASSED trước khi 72 lượt bắt đầu — §4 |
| phương pháp đã đăng ký | §5, **ngoài** vùng ghim, có lý do nêu ở đó |

## 1. Cơ chế ghim

### 1.1 Cái gì được ghim, và công thức

Digest tính trên **vùng ghim**, không trên cả tệp. Vùng ghim là phần văn bản giữa
hai mốc HTML comment `PREREG-FROZEN:BEGIN` và `PREREG-FROZEN:END` ở §2. Chuẩn hoá
đúng **hai** khoản, không có khoản thứ ba:

1. `\r\n` và `\r` → `\n`;
2. cắt dòng trống ở đầu và cuối vùng.

Ngoài hai khoản ấy, **từng byte**. Dựng lại:

```sh
python3 - <<'PY'
import hashlib, pathlib, re
CT = r"(?s)<!--\s*PREREG-FROZEN:BEGIN\s*-->\n(.*?)\n<!--\s*PREREG-FROZEN:END\s*-->"
for f in ("docs/BENCH-PREREGISTRATION-C2.md", "docs/handoff/bench-real-model-wiring.md"):
    t = pathlib.Path(f).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    v = re.findall(CT, t)
    assert len(v) == 1, f"{f}: {len(v)} vùng ghim, phải đúng 1"
    print(hashlib.sha256(v[0].strip("\n").encode("utf-8")).hexdigest(), f)
PY
```

Hai dòng in ra phải **giống nhau** và phải bằng `prereg_sha256` trong
`docs/closure-gate.json`.

### 1.2 Vì sao vùng chứ không cả tệp

Tệp này phải mọc thêm — phụ lục có ngày (§3), trạng thái G5.3 (§4), và sau cùng là
con trỏ tới báo cáo cột 2. Digest trên cả tệp thì **mỗi** lần thêm như thế làm vỡ
pin, và ai cũng phải ghi lại giá trị mới. Một pin vỡ thường xuyên thì "digest
không khớp" thành tiếng ồn, và lần sửa thật vào §2 đi qua giữa tiếng ồn ấy mà
không ai nhìn. Nên digest phủ **đúng** thứ không được đổi, và không phủ gì khác.

### 1.3 Vì sao từng byte chứ không chuẩn hoá nội dung

`docs/closure-gate.json` có một digest khác, `onboarding_digest`, và nó chuẩn hoá
**nhiều** (gộp khoảng trắng, bỏ qua reflow) — đúng ở đó, vì nó bảo vệ công của một
người thật khỏi bị một lỗi chính tả làm mất hiệu lực. Ở đây giá trị cần bảo vệ
**ngược lại**: chính văn bản, khỏi bị sửa. Nên "sửa một lỗi chính tả làm vỡ pin"
không phải khiếm khuyết của thiết kế này, nó là **yêu cầu**: trong vùng ghim không
có lần sửa nào hợp lệ. Pin vỡ thì việc phải làm là hoàn nguyên văn bản, không phải
ghi lại digest.

Và một luật chuẩn hoá lỏng ở đây sẽ không còn là pin: vùng ghim mang ngưỡng số
trong văn xuôi (`≥ 3`, `≤ 1`, `1/3`, `±0,08`, `8/12`) và gộp khoảng trắng cho phép
đổi cách viết chúng mà digest không đổi. Khoản LF thì phải có: kho **không** có
`.gitattributes` và CI chạy cả trên Windows, nên một checkout bật `core.autocrlf`
sẽ làm digest lệch trên một tệp không ai chạm — một FAILED giả, đúng lớp tiếng ồn
mục 1.2 tránh.

### 1.4 Nơi ghi digest, và vì sao không ghi trong tệp này

Giá trị digest nằm ở `docs/closure-gate.json`, khoá `prereg_sha256` của tiêu chí
G5.1, cạnh `prereg_frozen_region` mô tả mốc và luật chuẩn hoá ở dạng máy đọc được.
Một digest ghi **trong chính tệp nó ghim** thì người sửa văn bản cập nhật luôn cả
hai trong một động tác và không để lại dấu vết — nó không ghim gì. Tách ra hai tệp
thì đổi §2 mà không bị bắt đòi sửa **hai** tệp, và phía digest là **một dòng duy
nhất**, lộ ngay trong `git log -p docs/closure-gate.json`.

Vì cùng lý do, giá trị digest **không** được nhắc lại ở đâu trong tệp này: một con
số có hai nhà là một con số sẽ lệch.

### 1.5 Probe G5.1 kiểm gì

`docs/closure-gate.json` khai `probe: aisef.control.closure:probe_prereg_digest`
với `freshness: {"kind": "pinned_digest", "source": "prereg_sha256"}`. Năm bước,
theo đúng ngữ nghĩa §4.1 của hợp đồng (không tiêu chí nào được thoả bằng sự vắng
mặt của chính nó):

| bước | không đạt thì |
|---|---|
| 1. đọc `docs/BENCH-PREREGISTRATION-C2.md` | tệp không có → `UNRUNNABLE` (chặn), không bao giờ `PASSED` |
| 2. đúng **một** cặp mốc `PREREG-FROZEN` | → `FAILED`: hai vùng ghim thì không biết vùng nào là cam kết |
| 3. digest vùng ghim == `prereg_sha256` | → `FAILED` |
| 4. cùng công thức trên `docs/handoff/bench-real-model-wiring.md` ra **cùng** giá trị | → `FAILED`: bản lịch sử đã lệch khỏi bản ghim, và bản lịch sử là thứ định ngày |
| 5. `prereg_sha256` rỗng | → `UNCONFIGURED`, mà hợp đồng §4.1 promote thành `UNRUNNABLE` |

`aisef.control.closure` **chưa tồn tại** trong kho (máy đóng gate là một hạng mục
wave 0 riêng). Phép kiểm chạy được hôm nay là
`tests/test_meta.py::TestTienDangKyCot2BiGhim`, và nó là **bản tham chiếu** của
đúng công thức trên: probe khi được viết phải đọc công thức ấy, không dựng bản thứ
hai — đúng nguyên tắc "cùng một bộ đọc" mà hợp đồng §4.2 nêu.

### 1.6 Thứ pin này **không** chứng minh được

Nói ra chứ không để một digest khớp đọc thành nhiều hơn nó là:

1. **Pin ghim nội dung, không ghim bối cảnh.** Thêm một câu ngay **ngoài** mốc để
   đọc lại §2 theo hướng khác thì digest vẫn khớp. Không digest nào bắt được việc
   ấy. Cái bắt được là luật của tài liệu này — mọi thứ ngoài vùng ghim phải là phụ
   lục **có ngày** — cộng với `git log -p`. Di chuyển mốc thì ngược lại **có** bị
   bắt: dịch `BEGIN` xuống hay `END` lên đều đổi nội dung vùng, nên đổi digest.
2. **Pin không chứng minh văn bản được viết trước dữ liệu.** Nó chỉ làm mọi lần
   sửa **sau này** lộ ra. Thứ định ngày là bước 4 ở mục 1.5: cùng vùng ghim tồn tại
   trong ghi chú bàn giao, commit 2026-09-14, trước khi có một byte dữ liệu cột 2.
   Ngày commit thì người giữ kho vẫn sửa được — đây là giới hạn thật của mọi pin
   trong một kho một người, và nó được nói ra chứ không che.
3. **Pin không nói dự đoán đúng hay sai**, và không nói nó đủ chính xác để phán
   quyết. Chỗ chưa chính xác mà tôi tìm được nằm ở §3.4 — ghi ra, **không** sửa.

## 2. Tiền đăng ký — nguyên văn, không sửa

Vùng dưới đây là **bản ghim**. Nó trùng từng byte với `docs/handoff/bench-real-model-wiring.md`
§7, viết 2026-09-14 trước khi có một byte dữ liệu cột 2. Không sửa gì trong đây:
không lỗi chính tả, không làm rõ, không ngưỡng. Cái cần nói thêm thì nói ở §3.

<!-- PREREG-FROZEN:BEGIN -->
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
<!-- PREREG-FROZEN:END -->

## 3. Phụ lục 2026-09-14 — đo **sau** khi §2 được viết

> Phần này **không** thuộc cam kết. Nó là thứ đo được sau khi §2 đã đóng, ghi ngày
> và tách ra đúng vì thế. Nó không sửa một ký tự nào của §2, không đăng ký ngưỡng
> mới, và không thêm dự đoán nào về cột 2.

### 3.1 Ba con số

Đo trên bằng chứng đã ghi, không một lượt gọi model nào. Bảng đầy đủ ở
[BENCH-TASK-DISCRIMINATION.md](BENCH-TASK-DISCRIMINATION.md); dựng lại:

```sh
python3 validation/bench_discriminating_power.py .bench .bench-c1b
python3 validation/bench_discriminating_power.py --tu-kiem   # không cần dữ liệu
```

(`.bench` và `.bench-c1b` bị `.gitignore` loại, nên lệnh trên chỉ ra số ở bản
checkout chính; trong một git worktree nó in ra "bỏ qua, không thay bằng số nào".)

1. **Sức phân biệt của corpus.** Trên 339 dòng kết quả đã ghi, 30 task, 4 cohort:
   **12 trong 340 cặp chéo nhánh (3,5 %)** mang thông tin. Cả 12 đến từ **một**
   cohort (C-1) và **ba** task — `bug-a2-sec-1` (3), `bug-a2-sec-2` (6),
   `bug-a2-state-3` (3). **25 trong 30 task chưa bao giờ tách được hai nhánh** dù
   một lần.
2. **C-1b không mua một cặp thông tin nào.** Cả **ba** lượt trượt của C-1b đều là
   phiên bị CLI cắt (9/36 lượt kết thúc bằng một phiên bị cắt; 6 trong 9 vẫn
   PASS). Đọc theo đúng định nghĩa lượt mà **chính giao thức C-1b khai trước khi
   chạy** — phiên hỏng hạ tầng được chạy lại, không được chấm — cả ba task đọc
   **1,00/1,00 ở cả hai nhánh**: 36 lượt, 2,0 giờ phiên, 41,9 triệu token, **0**
   cặp mang thông tin. Con số **+0,06** đã in là hiện vật của lỗi 86 (phiên bị cắt
   vẫn để CLI thoát 0 nên `ok=True`), sửa 13/09 — **sau** khi C-1b chạy.
3. **Hệ quả cho ±0,08.** Dải nhiễu ấy được suy ra từ "hiệu số **đổi dấu** giữa C-1
   và C-1b". Lần đổi dấu ấy không tồn tại trên lượt chấm được, nên **xuất xứ của
   ±0,08 không đứng được**. Một cohort (C-1, −0,06) không cho ra một dải nhiễu.

### 3.2 Hệ quả cho cách đọc cột 2

Số học trên dữ liệu **đã có**, không phải dự đoán cho cột 2:

- Trong 12 task của danh sách đã đăng ký (§5), **9 task** nằm trong nhóm "chưa bao
  giờ tách được hai nhánh" (`multi-1..4`, `sec-3`, `sec-4`, `state-1`, `state-2`,
  `state-4`). Ba task còn lại — `sec-1`, `sec-2`, `state-3` — là **toàn bộ** các
  task từng tách được hai nhánh trong cả corpus.
- Điều kiện "không kết luận được" số 2 của §2 đếm ≥ 8/12 task cùng 1,00/1,00 hoặc
  cùng 0,00/0,00. Hai con số đặt cạnh nhau ở đây là số của dữ liệu **đã có**
  (9/12 chưa từng tách) và ngưỡng **đã đăng ký** (8/12) — đặt cạnh nhau để người
  đọc thấy chúng, thế thôi. Điều kiện ấy vẫn chỉ được quyết bằng dữ liệu cột 2, và
  đoạn này **không** dự đoán nó sẽ nổ.
- Ngưỡng `±0,08` ở §2 vẫn nguyên và vẫn quyết được — chúng là số. Cái mất là câu
  biện minh "tức ra ngoài dải nhiễu **đã đo**". Báo cáo cột 2 phải nói đúng thế:
  một hiệu số nằm trong dải ấy là "trong một dải mà độ rộng **chưa** được đo",
  không phải "trong dải nhiễu đã đo".

### 3.3 Thứ phụ lục này cố ý **không** làm

- **Không sửa §2** — không một ký tự, kể cả chỗ §3.4 chỉ ra là chưa chính xác.
- **Không đăng ký dải nhiễu mới, không đổi ngưỡng.** Sau khi đã thấy dữ liệu thì
  mọi ngưỡng mới là ngưỡng hậu nghiệm, và một ngưỡng hậu nghiệm dán nhãn tiền đăng
  ký là đúng thứ mà cả tiêu chí G5.1 tồn tại để chặn.
- **Không dự đoán gì về cột 2.**
- **Không đặt ngưỡng tuyển cặp cho G5.3** (§3.5 mục 2).

### 3.4 Chỗ chưa chính xác trong §2 — ghi ra, **không** sửa

Tìm được khi đọc lại để ghim. Mỗi mục nói cái đọc ra được, rồi dừng.

1. **Xuất xứ của `±0,08` bị bác** — §3.1 mục 3. Ngưỡng vẫn quyết được; câu biện
   minh thì không còn.
2. **"Tổng delta" không được định nghĩa.** Tiêu chí "mua được" đòi *"Tổng delta ≥
   +0,08"*, tiêu chí "không mua được gì" đòi *"|tổng delta| ≤ 0,08"* — nhưng không
   nói đó là **tổng** các delta theo task, **trung bình** của chúng, hay pass@1 gộp
   trên mọi lượt. Với 12 task hai cách đọc lệch nhau 12 lần. Cách đọc **khôi phục
   được từ bảng đã in**, chứ không phải do tôi chọn: C-1 in −0,06 = (−0,33 − 0,67 +
   0,33)/12 và C-1b in +0,06 = (0,00 + 0,00 + 0,17)/3 — cả hai là **trung bình
   delta theo task**. Ghi ở đây để người đọc sau không phải đoán; chữ "tổng" trong
   §2 giữ nguyên.
3. **Hai mệnh đề của tiêu chí "mua được" chọi nhau ở biên.** Mệnh đề hướng cho
   phép *"≥ 3 task thắng ≥ 1/3 **và** ≤ 1 task lệch ngược"*; mệnh đề tổng đòi
   ≥ +0,08. Cấu hình tối thiểu mà mệnh đề hướng cho qua **có** một task ngược:
   3 × (+1/3) + 1 × (−1/3) = +0,67, chia 12 = **+0,056 < 0,08** → mệnh đề tổng
   chặn. Nên trên thực tế *"≤ 1 task ngược hướng"* là *"0 task ngược hướng"*: chỉ
   3 thắng và 0 ngược mới vừa đủ (+1,0/12 = +0,083). Không mâu thuẫn — cả ba mệnh
   đề đều phải đạt — nhưng mệnh đề hướng không phải mệnh đề ràng buộc.
4. **"6/6 phiên" ở luật dừng sớm trộn hai đơn vị.** Đợt đã đăng ký chạy
   `--attempts 3`, nên một task có 3 **lượt** × 2 điều kiện = 6 **phiên**. Câu
   *"hai task đầu đều 6/6 phiên PASS ở cả hai điều kiện"* đọc ra được là 3/3 ở mỗi
   nhánh, nhưng nó dùng "phiên" ở chỗ phần còn lại của tài liệu dùng "lượt".
5. **Đường thắng không qua `pass@1` thiếu một trường đo được cho "xong giả".**
   Vế "ghi ra ngoài `write_scope`" có `guard_block` đếm được; vế "tuyên bố xong khi
   chưa xong" chỉ trỏ tới `analyze` mà không nói đọc trường nào. Chọn một trường
   bây giờ là chọn sau khi đã biết trường nào có sẵn, nên nó được để nguyên.

### 3.5 Chỗ §2 **không phủ** — khoảng trống, không lấp

Phán quyết 7 cấm viết lại dự đoán; nó cũng cấm **thêm** một dự đoán chưa từng có.
Hai chỗ dưới đây là việc mà cổng đóng dự án cần mà tiền đăng ký không nói, và
chúng được **báo** chứ không được lấp:

1. **Dự đoán gắn với một model chưa được nêu tên.** §2 viết *"Với M3 (model được
   khai là mạnh hơn M2.7)"*. Phán quyết 3 nói cột 2 chỉ chạy trên cặp model↔CLI mà
   G5.3 tuyển được, và cặp ấy có thể **không** phải M3 sau alias `mycombo`. Nếu
   G5.3 tuyển ra một cặp khác thì tiền đề của dự đoán không thoả và **tiền đăng ký
   này không phủ đợt đo ấy**. Việc đúng khi đó là một tiền đăng ký **mới**, viết
   trước khi chạy, ghim theo đúng cơ chế §1 — không phải một bản sửa của §2.
2. **Ngưỡng tuyển cặp của G5.3 không có ở đây.** Số duy nhất đã đăng ký về tỉ lệ
   hỏng là *"> 1/3 số lượt kết thúc với `exit_status ∈ INFRA_STATUSES` **sau** lần
   chạy lại"*, và nó là điều kiện **không kết luận được của đợt 72 lượt**, không
   phải ngưỡng qua/trượt của một đợt tuyển cặp. G5.3 đòi một ngưỡng khai trước cho
   đợt tuyển ấy. Tài liệu này **không** đặt ngưỡng đó.

## 4. Điều kiện hợp lệ của dữ liệu: G5.3 trước, rồi mới phóng

Một tiền đăng ký lờ đi điều kiện hợp lệ của chính dữ liệu nó sẽ đọc thì chưa đủ,
nên điều kiện ấy được nêu ở đây dù nó thuộc một tiêu chí khác.

**Phán quyết 3 của chủ dự án (2026-09-14), nguyên văn hiệu lực:** G5.3 **không**
được miễn trước. Một đợt tuyển cặp model↔CLI **có biên**, rẻ so với cả đợt đo,
chạy **trước**. Cột 2 không bắt đầu cho tới khi G5.3 PASSED. Không cặp nào đạt →
G5.3 thành `WAIVER_PENDING`, đợt 72 lượt **không** chạy, dừng lại cho chủ dự án
quyết. Trích: *"An honest INCONCLUSIVE benchmark is acceptable. A contaminated
benchmark presented as meaningful is not."*

Vì sao điều kiện ấy đứng trước phép đo chứ không đứng trong báo cáo: phóng cột 2
trên một cặp có 22–32 % phiên bị cắt mua đúng thứ C-1b đã mua — 36 lượt, 2,0 giờ,
41,9 triệu token, 0 cặp thông tin (§3.1). Dữ liệu sinh ra trước khi G5.3 đạt không
đọc được theo tiêu chí ở §2; nó phải được báo là **nhiễm**, không phải là đo.

Trạng thái hôm nay (2026-09-14): G5.3 `UNRUNNABLE` — chưa có cặp nào được tuyển.
Báo cáo tuyển cặp, khi có, nằm ở `docs/BENCH-PAIR-QUALIFICATION.md` theo
`docs/closure-gate.json`.

## 5. Phương pháp đã đăng ký — lệnh phóng, nguyên văn

Chép nguyên văn từ `docs/handoff/bench-real-model-wiring.md` §4 bước 2 (bước 1 —
lời khai tên model — và bước 3 — hai lệnh đóng đợt — ở nguyên trong ghi chú ấy):

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

**Vì sao lệnh này được chép vào đây.** Tiêu chí G5.1 nói *"phương pháp được
tiền đăng ký trước khi có dữ liệu"*, và một phương pháp mà người kiểm phải đi tìm
ở một tệp khác là một phương pháp trôi được. Ở đây nó nằm cạnh tiêu chí đọc nó,
nên phương pháp **đã đăng ký** và phương pháp **đã chạy** so được bằng một lượt
`diff`, không bằng trí nhớ.

**Vì sao nó nằm *ngoài* vùng ghim.** Lệnh này khai một cặp model↔CLI —
`--client opencode`, model mặc định sau alias `mycombo` — mà phán quyết 3 nói chỉ
được chốt **sau** khi G5.3 tuyển xong. Ghim nó lại là đóng băng một quyết định
chưa được phép ra; và một pin buộc phải ghi lại khi quyết định ấy ra thì không còn
là pin (§1.2). Nên nó được chép vào đây như **phương pháp đã đăng ký ngày
2026-09-14**, và mọi thay đổi của nó là một **bản bổ sung có ngày** ghi ngay dưới
đây — không bao giờ là một lần sửa đè lên lệnh trên. `git diff` phải đọc ra được
cái đã đăng ký và cái đã chạy.

Những biến **không** được đổi nếu còn muốn so với cột 1 — đã cố định từ C-1 và
nhắc lại ở ghi chú bàn giao §8: 12 tên task **đúng thứ tự trên**, `--attempts 3`,
cùng một model và đề bài giống nhau từng byte ở cả hai nhánh, `TRAN_LUOT = 0`,
`run.timeout_seconds`, `AISEF_BENCH_DIR` riêng (`.bench-c2`, để không xoá bằng
chứng của C-1), và `MANIFEST.sha256` khớp từng byte.

**Bản bổ sung cho §5** (trống tới khi G5.3 tuyển xong):

| ngày | đổi gì | vì sao | ai |
|---|---|---|---|
| – | – | – | – |

## 6. Luật sửa tài liệu này

1. Trong vùng ghim §2: **không sửa gì**. Pin vỡ thì hoàn nguyên văn bản, không ghi
   lại digest.
2. Ngoài vùng ghim: chỉ **thêm**, và mỗi phần thêm phải có ngày và phải nói rõ nó
   là hậu nghiệm.
3. Một tiền đăng ký mới (ví dụ khi G5.3 tuyển ra một cặp khác — §3.5 mục 1) là một
   **tài liệu mới**, ghim riêng, không phải một bản sửa của §2.
4. `docs/handoff/bench-real-model-wiring.md` §7 là bản lịch sử. Nó giữ nguyên tại
   chỗ và phải tiếp tục ra **cùng** digest; probe kiểm điều ấy (§1.5 bước 4).

## 7. Phụ lục 2026-09-14 (muộn) — probe đã được viết, và một chỗ lệch §1.5

Hậu nghiệm, ngoài vùng ghim, thêm chứ không sửa — theo đúng luật §6.

**§1.5 đã cũ ở một câu.** Nó viết `aisef.control.closure` *chưa tồn tại* và
`tests/test_meta.py::TestTienDangKyCot2BiGhim` là bản tham chiếu chạy được. Máy
đóng gate nay đã có, và `probe_prereg_digest` dùng lại đúng công thức ấy qua
`closure.frozen_region_digest`, lấy mốc **từ dữ liệu** (`prereg_frozen_region`
trong `docs/closure-gate.json`) chứ không viết cứng trong mã — nên vẫn không có
bản thứ hai của công thức, đúng yêu cầu §1.1.

**Một chỗ lệch, nêu ra chứ không lặng lẽ.** §1.5 bước 2 nói số vùng ghim khác 1
thì `FAILED`. Probe trả `UNRUNNABLE`. Lý do: không có một vùng duy nhất thì không
có gì để so, còn `FAILED` khẳng định một sự việc — rằng văn bản đã bị viết lại —
mà phép đo chưa hề dựng được. Cả hai đều **chặn**, nên không một kết cục đóng dự
án nào đổi theo chỗ lệch này; ghi ra vì một tài liệu nói khác mã là một tài liệu
sẽ bị tin sai lần sau.

**Một khiếm khuyết đã sửa, ghi lại vì nó là đúng lớp lỗi §1.2 cảnh báo.** Cho đến
hôm nay `probe_prereg_digest` đọc `prereg_sha256` ở **mức trên cùng** của
`docs/closure-gate.json`, và giá trị ở đó là digest **cả tệp**
(`36c6b4c5eba1…`), trong khi digest **vùng ghim** (`0c4dab0a74b6…`) nằm ở mức
tiêu chí và không ai đọc. Một con số có hai nhà, đúng thứ §1.4 nói sẽ lệch. Hệ
quả thật: phụ lục §7 này — một phần thêm mà §6 cho phép — sẽ làm G5.1 `FAILED`,
và đó là FAILED giả mà §1.2 dựng cơ chế vùng để tránh. `aisef closure --pin` nay
ghi digest vùng ghim vào **tiêu chí** và xoá khoá ở mức trên cùng; khoá ấy đã
được xoá khỏi kho. Phép kiểm: phụ lục này thêm vào mà G5.1 vẫn `PASSED`.

Probe cũng kiểm bước 4 thật sự từ hôm nay: thiếu `docs/handoff/bench-real-model-wiring.md`
là `UNRUNNABLE` (pin chứng minh văn bản không đổi, nhưng **không** chứng minh nó
có trước dữ liệu), và bản lịch sử lệch là `FAILED`.
