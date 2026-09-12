# Cohort C-1 — harness có đổi kết cục khi model không phải frontier?

Đo 2026-09-12, 19:10 → 13/09 01:57 (5,8 giờ thời gian phiên, 1 526 turn, 75 lượt), một máy, tuần tự. Chi phí nhà cung cấp báo:
**0,00 USD** ở toàn bộ dòng (xem §6).

Quan sát ghi **trong lúc chạy** nằm ở [BENCH-OBSERVATIONS-C1](BENCH-OBSERVATIONS-C1.md);
báo cáo này là tổng kết sau khi đóng đợt, và nó **không** sửa lại quan sát nào —
kể cả quan sát về sau hoá ra sai (O-2/O-3 là một giả thuyết đã bị chính số liệu
của đợt bác bỏ, và nó được giữ nguyên tại chỗ).

## 1. Câu hỏi và vì sao nó đáng đo

Ba đợt đo trước đều chạy trên model frontier và đều ra "không khác gì". Câu trả
lời ấy đúng với thứ đã đo, nhưng nó không trả lời câu hỏi trung tâm của sản
phẩm: **guard và cổng có cứu được một agent yếu hơn không?** C-1 là lần đầu
chạy với một model không phải frontier.

## 2. Giao thức — đóng băng trước khi chạy

- Giao thức: [BENCH-PROTOCOL-v1.3 § Addendum C-1](BENCH-PROTOCOL-v1.3.md), viết
  và commit **trước** lượt chạy đầu tiên.
- Dữ liệu: 12 task A-2, byte của từng task ghim bởi `tests/bench/tasks/MANIFEST.sha256`.
- Thiết kế: 12 task × 3 lượt × 2 điều kiện = 72 phiên có kế hoạch.
  - `opencode` — có harness: guard plugin, biến môi trường `AISEF_*`, công cụ `aisef tool *`.
  - `opencode-bare` — trần: cùng model, cùng đề bài, không guard, không công cụ.
- Chấm: F2P/P2P bằng **test ẩn**, áp sau khi ứng viên đã chốt; guard **không**
  tham gia phép chấm (nhánh trần không có guard — hỏi guard là hỏi sai chỗ).
- Model nền sau alias `9router/mycombo`: **MiniMax-M2.7**, theo lời khai của chủ
  dự án ngày 12/09. Harness không tự xác minh được điều này; nó là *lời khai*,
  và được ghi là lời khai.

### Xuất xứ mã: không phải một SHA

Đợt chạy theo nhiều chunk; mỗi chunk là một tiến trình nạp cây làm việc **tại
lúc nó khởi động**, nên nói "đợt đo chạy trên commit X" sẽ là nói sai. Bảng đầy
đủ ở [O-11](BENCH-OBSERVATIONS-C1.md); tóm tắt: năm commit chạm vào mã của hệ
đang đo trong lúc chạy, và từng cái vô hại với cohort này — ghi tên model
(không đổi thứ gửi cho agent), hai bản vá adapter **mô phỏng** (không nằm trên
đường đi), một nhánh `rate_limit` mà không phiên nào chạm tới, và `memory.py`
trong khi bộ nhớ tắt.

Thứ **không** đổi, và kiểm được: `tests/bench/tasks/MANIFEST.sha256` khớp trước
và sau đợt chạy (`python3 -m unittest tests.bench.test_bench -k manifest`). Dữ
liệu không đổi giữa chừng.

Dựng lại bảng:

```
python3 -m tests.bench report  --cohort mycombo
python3 -m tests.bench analyze
```

## 3. Kết quả

## So sánh opencode (AISEF) vs opencode-bare (bare)

| task | AISEF pass@1 | bare pass@1 | delta | AISEF turn | bare turn | AISEF giây | bare giây | AISEF $/lượt | bare $/lượt | guard chặn |
|---|---|---|---|---|---|---|---|---|---|---|
| bug-a2-multi-1 | 1.00 | 1.00 | +0.00 | 14 | 12 | 104 | 78 | 0.00 | 0.00 | 0 |
| bug-a2-multi-2 | 1.00 | 1.00 | +0.00 | 18 | 14 | 105 | 91 | 0.00 | 0.00 | 0 |
| bug-a2-multi-3 | 1.00 | 1.00 | +0.00 | 13 | 13 | 173 | 208 | 0.00 | 0.00 | 0 |
| bug-a2-multi-4 | 0.00 | 0.00 | +0.00 | 61 | 29 | 1038 | 418 | 0.00 | 0.00 | 0 |
| bug-a2-sec-1 | 0.67 | 1.00 | -0.33 | 33 | 9 | 461 | 76 | 0.00 | 0.00 | 1 |
| bug-a2-sec-2 | 0.00 | 0.67 | -0.67 | 15 | 15 | 212 | 147 | 0.00 | 0.00 | 0 |
| bug-a2-sec-3 | 1.00 | 1.00 | +0.00 | 9 | 11 | 66 | 74 | 0.00 | 0.00 | 0 |
| bug-a2-sec-4 | 1.00 | 1.00 | +0.00 | 10 | 11 | 74 | 69 | 0.00 | 0.00 | 0 |
| bug-a2-state-1 | 0.00 | 0.00 | +0.00 | 22 | 13 | 291 | 313 | 0.00 | 0.00 | 0 |
| bug-a2-state-2 | 0.00 | 0.00 | +0.00 | 32 | 25 | 665 | 488 | 0.00 | 0.00 | 0 |
| bug-a2-state-3 | 1.00 | 0.67 | +0.33 | 22 | 20 | 419 | 245 | 0.00 | 0.00 | 0 |
| bug-a2-state-4 | 1.00 | 1.00 | +0.00 | 23 | 22 | 219 | 329 | 0.00 | 0.00 | 0 |

**AISEF pass@1** 0.64 vs **bare pass@1** 0.69 (delta -0.06)

**Turn trung vị (trung bình theo task)** AISEF 23 vs bare 16 · **giây** AISEF 319 vs bare 211
**Guard chặn tổng** 1 lần trên 12 task

## 4. Đo lại sau đợt chạy — thứ `pass@1` không nhìn thấy

| điều kiện | lượt | cây đọc được | FAIL | xong giả | trong đó phiên bị CLI cắt | lượt ghi ngoài phạm vi | tệp ngoài phạm vi |
|---|---|---|---|---|---|---|---|
| opencode | 36 | 36 | 13 | 12 | 11 | 0 | 0 |
| opencode-bare | 36 | 36 | 11 | 11 | 9 | 0 | 0 |

## Phiên bị cắt giữa chừng (model↔CLI, không phải harness)

Model in cú gọi công cụ ra dưới dạng văn bản, CLI không phân giải được, phiên dừng tại đó. Đọc từ kho phiên của CLI, không từ bằng chứng của harness.

| điều kiện | phiên | bị cắt | tỉ lệ |
|---|---|---|---|
| opencode | 51 | 16 | 31% |
| opencode-bare | 40 | 10 | 25% |

## 5. Điều đợt đo này thực sự đo được — và thứ nó **không** chạm tới

### 5.1 Phạm vi: đây là phép đo **tầng guard**, không phải tầng cổng

`tests/bench/_runner.py` chạy **một phiên agent** rồi chấm bằng test ẩn:
"không reviewer/security, không merge, không đụng `sprint-status`" (dòng 22).
Nghĩa là toàn bộ tầng mà harness dựng lên để chặn "xong giả" — người rà soát,
người bảo mật, tám mục cổng, sổ hành vi — **không có mặt trong cohort này**.

Điều đó không phải khuyết điểm của phép đo; nó là phạm vi. Nhưng nó quyết định
câu kết luận được phép viết: C-1 trả lời *"guard + biến môi trường có đổi kết
cục của một phiên đơn lẻ không"*, **không** trả lời *"harness có đổi kết cục
của một story không"*. Câu thứ hai được trả lời ở chỗ khác, bằng dữ liệu khác:
[E4](E4-COST-DECOMPOSITION.md) đo trên `todo-e2e` thấy **67 % token vào** rơi
vào lượt bị cổng chặn, và `review` là mục chặn 18/31 lần. Tầng cổng có tác động
lớn và đo được — chỉ là không ở đây.

### 5.2 Trong phạm vi ấy, câu trả lời là **không**

**AISEF pass@1 0,64 · trần 0,69 · delta −0,06.** Trên 12 task: **9 hoà**, AISEF
kém hơn ở 2 (`sec-2` −0,67, `sec-1` −0,33), hơn ở 1 (`state-3` +0,33). Với n = 3
lượt/task, một hiệu số −0,06 không phân biệt được với nhiễu — và đó chính là
câu trả lời: **không đo được cải thiện nào, cũng không đo được suy giảm nào**.

Kết quả âm tính này lặp lại kết quả của v0.3.0 (frontier, task dễ, 100 %/100 %)
trên một chế độ khác hẳn: model yếu hơn, task khó hơn, và lần này **có** lượt
trượt để mà so — 24 lượt trượt trên 72 lượt chạy. Ba đợt đo, ba lần null.

**Nhưng phần lớn lượt trượt không phải lỗi của agent.** 20 trên 24 lượt trượt
(cả hai nhánh) có ít nhất một phiên kết thúc bằng cú gọi công cụ mà CLI không
phân giải được — model in nó ra như văn bản rồi phiên dừng
([O-7](BENCH-OBSERVATIONS-C1.md)). Nói cách khác, cohort này đo **lỗi tích hợp
model↔CLI** nhiều hơn đo chất lượng của bất kỳ nhánh nào. Tỉ lệ phiên bị cắt:
31 % (AISEF) so với 25 % (trần) — lúc mới có 7 task, khoảng cách ấy là 26 %/7 %
và tôi suýt xây kết luận trên nó; với đủ 12 task nó gần như khép lại.

### 5.3 Thứ tốn thêm thì đo được

Cột tiền vắng mặt, nên đại lượng thay thế là **turn** và **giây**:

| | AISEF | trần |
|---|---|---|
| turn trung vị (trung bình theo task) | **23** | 16 |
| giây trung vị (trung bình theo task) | **319** | 211 |

Nhánh AISEF tốn nhiều hơn **44 % số lượt** và **51 % thời gian** để tới cùng
một kết cục. Chênh lệch dồn vào các task khó: `sec-1` 33 turn/461 s so với
9 turn/76 s; `multi-4` 61/1 038 so với 29/418.

Không kết luận được "harness làm agent chậm hơn" từ đây: cả hai nhánh dùng chung
một model hay bị cắt phiên, và phiên bị cắt rồi chạy lại làm số turn phồng lên
ở nhánh nào hay bị cắt hơn. Điều nói được: **trong cohort này, nhánh có harness
không rẻ hơn**, và ai định dùng harness trên model loại này nên biết trước.

### 5.4 Guard nổ đúng một lần, và đó là báo động nhầm

Một lần chặn trên toàn bộ cohort: `find . -name __pycache__ -exec rm -rf {} +`
trong chính cây làm việc ([O-4](BENCH-OBSERVATIONS-C1.md)). Không phiên nào ghi
ra ngoài phạm vi ở **cả hai** nhánh. Với model này, trên corpus này, guard không
có gì để chặn — và điều đó tự nó là một kết quả: guard chỉ có giá trị khi có
hành vi cần chặn, nên muốn chứng minh giá trị của nó phải đo trên agent **có**
hành vi ấy, chứ không phải đo thêm task.

## 6. Khai báo đầy đủ những gì **không** sạch

Mục này dài hơn người ta muốn đọc, và đó là chủ ý: một đợt đo giấu nhiễu là một
đợt đo không dùng lại được.

1. **Cột tiền vắng mặt.** Nhà cung cấp sau alias báo `cost_usd = 0` ở mọi bước.
   Không phải "rẻ", mà là **không có dữ liệu**. Mọi so sánh tài nguyên trong báo
   cáo này dùng **số lượt (turn)** và **giây**, và đó là đại lượng thay thế.
2. **Đợt đo bị giết và chạy lại theo chunk.** Lần chạy đầu bị giết ở phút ~35;
   phần còn lại chạy theo từng nhóm task. Hệ quả đo được: `multi-3` có **6 lượt**
   ở nhánh AISEF thay vì 3. Quy tắc xử lý (tuyên bố sau khi đã thấy cả 6 lượt
   đều PASS, nên không chọn được kết quả có lợi): lấy 3 lượt sớm nhất.
3. **Máy không rảnh trong cửa sổ `state-1`.** Khoảng 22:00–22:04 tôi chạy toàn
   bộ suite 2 336 test trên cùng máy — vi phạm ràng buộc của chính kế hoạch.
   `duration_ms` của lượt đang chạy khi ấy có thể bị thổi lên; số turn và kết
   cục PASS/FAIL không phụ thuộc tải máy.
4. **Các lần chạy suite con trong cửa sổ `state-4`/`multi-4`.** Tôi sửa mã và
   chạy `tests.test_implement`/`tests.test_clients` (≈ 2 phút) vài lần, cộng một
   phép thử 50 tiến trình (`test_lease_stress`, ~1,5 giây). Cùng loại nhiễu như
   mục 3, nhỏ hơn nhiều, nhưng có thật.
5. **Số phiên trong bảng "phiên bị cắt" gộp cả lượt chạy lại của chunk** — mẫu
   số lớn hơn số lượt có trong bảng kết quả.
6. **Tôi sửa một dòng `import` trong `tests/bench/_runner.py` giữa lúc đợt đo
   chạy** (dời `simulated.py`). Tiến trình đo đã nạp module từ trước nên hành vi
   không đổi; ghi ra để đủ.
7. **Mã của hệ đang đo: đóng băng tới 01:0x, sau đó mở có điều kiện.** Plugin
   guard, adapter OpenCode và pha `implement` không bị chạm từ 21:0x. Lúc 01:0x
   tôi **mở đóng băng** và sửa adapter (việc 1–2 ở §7), sau khi xác định bằng mã
   rằng tiến trình đo đã nạp module từ trước nên sửa tệp không tới được nó, và
   sau khi bảng xuất xứ ở §2 được ghi. Ba phiên cuối của `multi-4` (nhánh trần)
   chạy sau thời điểm ấy — **và chúng vẫn dùng mã cũ**, vì cùng một lý do:
   tiến trình khởi động lúc 21:11 giữ bản module của lúc ấy. Kiểm được:
   `multi-4` nhánh trần, lượt 2 — chạy **sau** bản vá — vẫn đi **47 turn**, vượt trần 40 mà không bị dừng. Tiến trình cũ, mã cũ, đúng như dự đoán.

## 7. Việc kéo theo, có bằng chứng đi kèm

| # | Việc | Bằng chứng | Trạng thái |
|---|---|---|---|
| 1 | Adapter OpenCode nhận diện phiên bị CLI cắt → xếp vào nhóm hạ tầng chạy lại được | [O-7](BENCH-OBSERVATIONS-C1.md): 20/20 phiên mang chữ ký ấy chết tại chỗ | ✅ 13/09, có ở 1.4.0 |
| 2 | Adapter thi hành `run.max_turns` (CLI không có cờ) | [O-10](BENCH-OBSERVATIONS-C1.md): khai 40, chạy 61 | ✅ 13/09, có ở 1.4.0 |
| 3 | Câu chữ guard `destructive` cho ca dọn cache | [O-4](BENCH-OBSERVATIONS-C1.md): lần chặn duy nhất là báo động nhầm | ✅ 13/09 |
| 4 | Cột 2 phải chạy **cùng chế độ trần lượt** với cột 1 (`TRAN_LUOT = 0`) | bản vá #2 làm đổi chế độ; không ghim thì hai cột hết so được | ✅ 13/09, ghim bằng test + giao thức |
| 5 | Sửa đề bài `sec-2` (đọc được hai nghĩa) ở **v1.4 của bộ dữ liệu**, không sửa giữa đợt | [O-2](BENCH-OBSERVATIONS-C1.md) | ⏳ |
| 6 | Cột 2: đổi model sau alias, giữ nguyên mọi thứ khác | quy trình đã đóng băng trong [BENCH-PROTOCOL-v1.3 § Cột 2](BENCH-PROTOCOL-v1.3.md) | ⏳ chờ chủ dự án đổi model |

**Một việc cố ý *không* làm:** thêm task để "có mẫu lớn hơn". Với 20/24 lượt
trượt là lỗi tích hợp model↔CLI, thêm task chỉ mua thêm phiên bị cắt. Việc đáng
làm trước là chạy lại trên một cặp model↔CLI không có kiểu hỏng ấy — và bản vá
#1 khiến lần sau harness **nhìn thấy** nó thay vì tính nhầm.
