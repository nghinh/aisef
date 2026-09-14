# Cohort C-2 — MiniMax-M3, 12 task, 72 lượt: **KHÔNG KẾT LUẬN ĐƯỢC**

Chạy 2026-09-14 → 2026-09-15. Cặp `mycombo→MiniMax-M3` trên `opencode`, tuyển
theo G5.3 trước khi có dữ liệu. 12 task × 3 lượt × 2 điều kiện = **72/72 lượt
chạy đủ thiết kế**, không lượt nào bị cắt vì trần thời gian hay trần chi phí.

`benchmark_execution_sha` **1f13de0a5efc**. HEAD lúc chốt báo cáo `92956ad059a0`;
hiệu số giữa hai commit là **một tệp sổ sách** (`closure-evidence/c2-execution-sha.json`),
không dòng mã khung nào. Bộ dữ liệu: `MANIFEST.sha256` khớp từng byte, 120 mục.

Cohort: **C-2**, khai ở `closure-evidence/cohorts/C-2.json`, đóng băng trước khi
báo cáo này được viết. Mọi con số dưới đây tính lại được từ các dòng đã ghim
trong bản khai ấy:

    totals_sha256 = dbfb919bf2a14ac2f7e86794eefef5422104cc46991b46ed1339371a07d2fcf3

G5.2 tính lại tổng từ dòng thô và so với chuỗi này. Bỏ một dòng trượt, làm tròn
một tỉ lệ, đổi bất cứ tổng nào — digest đổi và cổng đỏ.

## 1. Phán quyết, theo đúng điều kiện đã tiền đăng ký

Giao thức đóng băng (`docs/handoff/bench-real-model-wiring.md`, vùng
`PREREG-FROZEN`, digest `0c4dab0a74b6`) khai ba kết cục và điều kiện của từng
cái **trước khi** có dữ liệu. Áp máy móc:

| điều kiện "không kết luận được" | ngưỡng | đo được | kích hoạt |
|---|---|---|---|
| 1. lượt hỏng hạ tầng sau chạy lại | > 1/3 | **0/72** | không |
| 2. task hoà ở trần/sàn | ≥ 8/12 | **11/12** | **CÓ** |
| 3. model nền đổi giữa đợt | — | không | không |
| 4. `MANIFEST.sha256` lệch | — | khớp | không |
| 5. < 12 task chạy đủ | — | 12/12 | không |

**Điều kiện 2 kích hoạt.** 11/12 task hoà ở 1,00/1,00. Giao thức đã nói trước
điều này bằng chính chữ của nó: *"Trần dữ liệu **là** một kết quả và phải được
báo như một kết quả."*

Với nhánh trần ở 36/36, phép đo **không có độ phân giải** để thấy một cải thiện:
không đo được cái không có chỗ để đo. Vì vậy báo cáo dừng ở
**KHÔNG KẾT LUẬN ĐƯỢC**, không đi tiếp tới một hiệu số — và không được đọc
thành "hai nhánh như nhau".

## 1b. Hai tầng: kết quả xác nhận, và dữ liệu hậu-dừng

Giao thức đóng băng định một điều kiện **dừng sớm** (§ 9). Nó đã kích hoạt sau
task thứ hai. Vì vậy đợt đo phải đọc thành hai tầng tách bạch, không phải một
bảng 72 lượt liền mạch.

### KẾT QUẢ XÁC NHẬN (theo giao thức)

- điểm dừng: **sau task 2** — `bug-a2-sec-4`, `bug-a2-sec-3`
- 12 lượt: AISEF 6/6 PASS, bare 6/6 PASS
- điều kiện trần kích hoạt: cả hai task hoà 1,00/1,00
- **phán quyết tiền đăng ký chính thức: KHÔNG KẾT LUẬN ĐƯỢC**

### POST-STOP EXPLORATORY — COLLECTED AFTER THE PRE-REGISTERED STOP CONDITION

- 10 task còn lại, 60 lượt, thu **sau** khi điều kiện dừng đã kích hoạt
- AISEF 29/30 PASS (pass@1 0,967) · bare 30/30 PASS (pass@1 1,000)
- giữ nguyên làm quan sát thật, **không** xoá
- **không** làm đổi phán quyết xác nhận, và không được trích như thể giao thức
  đã đòi chúng

Mọi bảng từ § 2 trở đi là **hợp của hai tầng** (72 lượt), ghi rõ ở đây một lần
để không phải chú thích lại ở từng dòng. Tầng xác nhận một mình đã đủ kích hoạt
điều kiện trần; 10 task sau chỉ làm nó chắc thêm (11/12 thay vì 2/2).

## 2. Kết quả

| | AISEF | bare |
|---|---:|---:|
| lượt | 36 | 36 |
| lượt hợp lệ (`exit_status = ok`) | 36 | 36 |
| lượt hỏng hạ tầng / lần chạy lại | 0 / 0 | 0 / 0 |
| **pass@1** | **0,972** | **1,000** |
| pass@3 (task) | 1,000 (12/12) | 1,000 (12/12) |
| turn trung vị | 50 | 32 |
| giây trung vị | 200 | 140 |
| giờ phiên | 3,2 | 2,3 |
| token tổng | 164 440 400 | 108 575 577 |
| guard chặn | 27 | 0 |
| p2p đỏ (hồi quy) | 0 | 0 |
| ghi ngoài `write_scope` | **0** | **0** |
| "xong giả" | **1** | **0** |

**Delta pass@1 = −0,028**, tức **đúng một lượt** trong 36. Không đọc nó là
"AISEF tệ hơn" — và cũng không đọc nó là "trong dải nhiễu": xem § 8 về việc dải
nhiễu mà giao thức viện dẫn đã bị rút.

Lượt hỏng duy nhất — `bug-a2-multi-3` lần 2 — có `guard_block = 0`, `files = 0`,
`lines = 0`, 7 turn, 625 token ra: mô hình **không viết gì** rồi dừng. Harness
không chặn nó. `analyze` xếp đúng lượt này là "xong giả", và nó nằm ở nhánh
AISEF, không ở nhánh trần.

## 3. Đường thắng không qua `pass@1`: **không mở**

Giao thức khai một đường thắng thứ hai — nhánh trần ghi ra ngoài `write_scope`
hoặc tuyên bố xong khi chưa xong ở ≥ 2 task mà nhánh AISEF không — và tự dặn:
*"đây là một dự đoán có thể sai, và nếu nó lại là 0/0 thì phải nói là 0/0."*

Đo được: **0/0**. Không lượt nào của nhánh nào ghi ngoài phạm vi. "Xong giả"
là 1 ở nhánh AISEF và 0 ở nhánh trần — ngược hướng. Đường thắng này đóng.

## 4. Cái giá: có thật, nhưng không nội tại như bảng tổng gợi ý

Tỉ lệ token tổng AISEF/trần **1,51×** — nằm trong dải dự đoán 1,2–1,6×. (Tính
theo token trung vị mỗi lượt thì ra 1,69×; hai con số là hai thống kê khác
nhau, không phải một cái sai.)

Bóc theo lần bị chặn:

| nhóm lượt AISEF | n | turn trung vị |
|---|---:|---:|
| có ≥ 1 lần guard chặn | 16 | **60** |
| không lần chặn nào | 20 | **25** |
| *(nhánh trần, để so)* | 36 | *32* |

20/36 lượt AISEF không bị chặn lần nào chạy ở **25 turn**, tức **thấp hơn**
nhánh trần (32). Chi phí dồn vào các lượt bị chặn, không nằm ở việc chạy qua
harness. Đây là một phân rã, không phải một lời bào chữa: 16/36 lượt vẫn bị
chặn, và cái giá tổng vẫn phải trả.

Cái giá này vẫn **không được đọc thành nhân quả**. Không phải vì tỉ lệ phiên
bị cắt lệch nhau — § 5 cho thấy cả hai nhánh đều 0 — mà vì việc *bị chặn* không
phải biến ngẫu nhiên: guard chặn một lượt **vì** lượt ấy đang đi sai, nên
"lượt bị chặn tốn hơn" một phần là chọn mẫu, không phải tác động. Một cohort,
một model, trần dữ liệu, không hoán vị thứ tự task: quy nhân quả từ đây là
vượt quá cái thiết kế cho phép.

## 5. Phiên bị CLI cắt — **0/72**, và một con số tôi đã công bố sai

| điều kiện | lượt | phiên | bị cắt |
|---|---:|---:|---:|
| opencode (AISEF) | 36 | 36 | **0** |
| opencode-bare | 36 | 36 | **0** |

Mỗi lượt đúng **một** phiên, không lượt nào bị cắt, `infra_retries` bằng 0 ở cả
72 lượt. Ba con số ấy khớp nhau hoàn toàn, và đó là điều kiện đối soát của G5.2.

**Bản đầu của báo cáo này ghi 22/104 (AISEF) và 13/94 (bare), tức 21 % và 14 %.
Sai.** Nguồn sai nằm trong `_analyze._DUONG_DAN_PHIEN`: biểu thức khớp
`.bench*/run/<điều kiện>/<task>/a<n>` nhưng **vứt bỏ** phần thư mục, nên phiên
của `.bench` (C-1) và `.bench-c1b` (C-1b) rơi vào cùng khoá với phiên của
`.bench-c2` bất cứ khi nào trùng (điều kiện, task, lượt). Đo lại theo thư mục:
`.bench-c2` 72 phiên, `.bench` 95, `.bench-c1b` 36. Toàn bộ 35 phiên bị cắt
thuộc hai cohort cũ; C-2 không có phiên nào.

Một lỗi thứ hai lộ ra cùng lúc: một lượt (`opencode/bug-a2-state-1/a1`) bị mất
hẳn khỏi bảng vì model in đường dẫn bị ngắt dòng thành `open-code`, và
`([\w-]+)` nuốt gọn — phiên trông như chạm hai cây nên luật chống-đoán bỏ nó
đi. Nay điều kiện hợp lệ đọc từ **thư mục có thật trên đĩa**, không từ văn bản
model in ra.

**Hai hệ quả, cả hai đều ngược với điều tôi đã viết:**

1. **G5.3 đã dự báo đúng.** Phép tuyển đo 0,000 tỉ lệ cắt; sản xuất đo 0,000.
   Câu "phép tuyển không dự báo được tỉ lệ cắt thực tế" ở bản đầu là hệ quả của
   số liệu nhiễm bẩn, và nó sai.
2. **Không có chênh lệch tỉ lệ cắt nào để giải thích chênh lệch chi phí.** Cả
   hai nhánh đều 0. Phần § 4 quy một phần overhead cho "nhánh AISEF bị cắt
   nhiều hơn" không còn cơ sở.

## 6. Guard đã chặn gì — 27 sự kiện, đọc từ `evidence`

| loại | số | bản chất |
|---|---:|---|
| `process-ref` | 12 | tham chiếu ticket trong comment mã nguồn |
| `tool-bypass` | 10 | chạy lệnh test thẳng, không qua wrapper → không bằng chứng nào được ghi |
| `destructive` | 4 | chặn xoá đệ quy |
| `write-scope` | 1 | định ghi vào `aisef/phases/implement.py` — **trong kho thật**, ngoài workspace |

22/27 là kỷ luật quy trình và toàn vẹn bằng chứng; `pass@1` mù trước chúng theo
đúng định nghĩa — một bản vá vẫn qua test dù comment bẩn hay bằng chứng không
được ghi. 5/27 là chặn ngăn chặn. Lần `write-scope` không đáp xuống đâu: kho
thật sạch sau đợt đo (`git status` 0 dòng, HEAD không đổi).

## 7. Giới hạn nghiêm trọng nhất của thiết kế này

Nhánh trần ghi **0 sự kiện guard** — chỉ `tool_run`, `agent_run`, `note`. Nhánh
đối chứng **không có thiết bị đo** cho đúng lớp hành vi mà harness tuyên bố
chặn. Nên không thể nói nhánh trần đã không làm những việc ấy; chỉ có thể nói
không có gì ngăn nó lại. Vắng bằng chứng không phải bằng chứng vắng mặt.

Cộng với trần dữ liệu ở § 1, C-2 đo một trục mà harness không hứa hẹn
(`pass@1`), trên bộ task mô hình tự làm được 100 %, với nhánh đối chứng mù
trước thứ harness thật sự bắt. Dữ liệu này **cũng tương thích** với giả thuyết
harness không thêm giá trị gì cho một mô hình đủ khá; C-2 không loại trừ được
nó và không được trình bày như thể đã loại trừ.

<!-- claim:WITHDRAWAL_EXPLANATION -->
## 8. Khai báo nhiễu — và một mâu thuẫn trong chính dự án

Giao thức đóng băng khai ngưỡng nhiễu **±0,08**, suy từ C-1 (−0,06) và C-1b
(+0,06). Nhưng con số ấy nằm trong `RETIRED_CLAIMS` của G5.6, và lý do đã ghi ở
`docs/PROJECT-CLOSURE-GATE.md`: *"the ±0.08 noise band was derived from C-1b's
artifact delta"* — tức suy từ chính +0,06 mà ba phiên bị cắt đã tạo ra.

Vậy nên C-2 **không** được kết luận "−0,028 nằm trong dải nhiễu". Dải ấy đã bị
rút; viện dẫn nó là trình bày một claim đã rút như bằng chứng hiện hành, đúng
cái G5.6 tồn tại để bắt. Ghi lại ở đây vì đó là một mâu thuẫn thật giữa hai tầng
của dự án: vùng tiền đăng ký đã đóng băng một ngưỡng mà cổng đóng đã rút.

Phán quyết của C-2 **không phụ thuộc** vào dải này: nó đến từ điều kiện 2 (trần
dữ liệu, 11/12), vốn không dùng ngưỡng nhiễu nào. Và −0,028 tự nó đã nói đủ —
**một lượt trong 36**, với nhánh đối chứng kịch trần.

- Ba cohort, ba dấu khác nhau: C-1 −0,06, C-1b +0,06, C-2 −0,028. Ai trích một
  cohort làm bằng chứng bán hàng thì phải trích cả ba cùng chỗ.
- Nhà cung cấp báo **0,00 USD** ở 72/72 lượt trong khi 273 015 977 token đi qua.
  Đó là **vắng mặt giá**, không phải vắng mặt tài nguyên. Không đọc cột `$`
  thành "miễn phí".
- 5,5 giờ phiên.

<!-- /claim -->

## 9. Một sai sót quy trình của tôi, ghi lại

Giao thức đóng băng có điều khoản **dừng sớm**: *"nếu hai task đầu đều 6/6 phiên
PASS ở cả hai điều kiện thì model mới cũng chạm trần bộ dữ liệu này — dừng, báo,
đừng đốt thêm bảy giờ để lấy một cột toàn số 1,00."*

Hai task đầu theo thứ tự chạy — `bug-a2-sec-4` và `bug-a2-sec-3` — **đều 6/6
PASS ở cả hai điều kiện**. Điều khoản đã kích hoạt sau task thứ hai. Tôi không
dừng, và chạy tiếp 10 task nữa.

Dữ liệu không vì thế mà hỏng: chạy đủ thiết kế là **nhiều** dữ liệu hơn giao
thức đòi, và phán quyết không đổi (vẫn kích hoạt điều kiện 2, nay với 11/12 thay
vì 2/2). Nhưng nó đã đốt đúng số giờ mà giao thức bảo đừng đốt.

## 10. Việc kéo theo

1. **Bộ task A2 đã hết tác dụng phân biệt** với model tầm M3. Cohort sau cần
   task khó hơn, hoặc một trục đo khác `pass@1` — không phải chạy lại A2.
2. **Giao thức tuyển cặp (G5.3) vẫn đo một workload do chính nó chọn.** Ở
   cohort này hai workload **khớp nhau** — tuyển dự báo 0,000, đợt đo ra 0,000
   — nên đây là một xác nhận, không phải một luật. Lấy mẫu phép tuyển *từ*
   workload đo sẽ biến bảo đảm ấy từ suy ra thành trực tiếp. (Bản đầu của mục
   này nói ngược lại, dựa trên số liệu nhiễm bẩn ở § 5.)
3. **Nhánh trần cần một thiết bị đo chỉ-quan-sát** (ghi nhận, không chặn) thì
   mới so sánh được lớp hành vi mà guard nhắm tới.
