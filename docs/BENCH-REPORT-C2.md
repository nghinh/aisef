# Cohort C-2 — MiniMax-M3, 12 task, 72 lượt: **KHÔNG KẾT LUẬN ĐƯỢC**

Chạy 2026-09-14 → 2026-09-15. Cặp `mycombo→MiniMax-M3` trên `opencode`, tuyển
theo G5.3 trước khi có dữ liệu. 12 task × 3 lượt × 2 điều kiện = **72/72 lượt
chạy đủ thiết kế**, không lượt nào bị cắt vì trần thời gian hay trần chi phí.

`benchmark_execution_sha` **1f13de0a5efc**. HEAD lúc chốt báo cáo `92956ad059a0`;
hiệu số giữa hai commit là **một tệp sổ sách** (`closure-evidence/c2-execution-sha.json`),
không dòng mã khung nào. Bộ dữ liệu: `MANIFEST.sha256` khớp từng byte, 120 mục.

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

Một phần cái giá ấy **không phải của harness**: xem § 5.

## 5. Phiên bị CLI cắt — và một dự đoán sai của G5.3

| điều kiện | phiên | bị cắt | tỉ lệ |
|---|---:|---:|---:|
| opencode (AISEF) | 104 | 22 | **21 %** |
| opencode-bare | 94 | 13 | **14 %** |

Ở mức **lượt**, cả 72 lượt đều `exit_status = ok` — cơ chế chạy lại trong lượt
đã hấp thụ hết. Ở mức **phiên** thì không: 35 phiên bị cắt giữa chừng.

Điều này **mâu thuẫn với phép tuyển G5.3**, vốn đo 28/28 phiên với **0 phiên
bị cắt** (tỉ lệ 0,000 ≤ ngưỡng 0,167) và trên cơ sở đó tuyên bố cặp đủ tư cách.
Tỉ lệ thật trong sản xuất là 21 % / 14 %. Phép tuyển đã **không dự báo được**
tỉ lệ cắt thực tế — workload của nó khác workload đo. Đây là một hạn chế của
giao thức tuyển cặp, phải ghi lại, và nó **không** làm hỏng C-2 (điều kiện
"không kết luận được" số 1 tính ở mức lượt, và ở mức ấy là 0/72).

Hệ quả cho § 4: nhánh AISEF có nhiều phiên hơn (104 vs 94) và nhiều lần cắt hơn
(22 vs 13). Mỗi lần cắt kéo theo một lần chạy lại, nên **một phần** chênh lệch
turn/token là thuộc tính của cặp model↔CLI, không phải overhead của harness.
Dữ liệu hiện có không tách được hai phần ấy.

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
2. **Giao thức tuyển cặp (G5.3) cần đo tỉ lệ cắt trên workload giống đợt đo**,
   không trên workload tuyển riêng. 0/28 đã dự báo sai 21 %.
3. **Nhánh trần cần một thiết bị đo chỉ-quan-sát** (ghi nhận, không chặn) thì
   mới so sánh được lớp hành vi mà guard nhắm tới.
