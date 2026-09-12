# Cohort C-1b — ba task phân biệt được, sáu lượt mỗi nhánh

Đo 2026-09-13, 03:15 → 05:34. **2,0 giờ** thời gian phiên, 36 lượt, nhà cung cấp
báo **0,00 USD**. Giao thức đóng băng trước khi chạy:
[BENCH-PROTOCOL-v1.3 § Addendum C-1b](BENCH-PROTOCOL-v1.3.md). Quan sát ghi
trong lúc chạy: [BENCH-OBSERVATIONS-C1B](BENCH-OBSERVATIONS-C1B.md).

Model nền sau alias `mycombo`: **vẫn MiniMax-M2.7** (chủ dự án xác nhận 13/09).
Đây **không** phải cột 2; đây là cùng model, nhiều lượt hơn, trên đúng ba task
mà C-1 cho thấy có phân biệt.

## 1. Kết quả

| task | AISEF | trần | delta | AISEF turn | trần turn | AISEF giây | trần giây |
|---|---|---|---|---|---|---|---|
| `sec-1` | 1,00 | 1,00 | +0,00 | 16 | 9 | 148 | 78 |
| `sec-2` | 0,83 | 0,83 | +0,00 | 22 | 18 | 190 | 153 |
| `state-3` | **1,00** | 0,83 | **+0,17** | 18 | 20 | 276 | 214 |
| **tổng** | **0,94** | **0,89** | **+0,06** | 19 | 15 | 205 | 148 |

3 lượt trượt trên 36. Guard chặn **3 lần**. **0** lần ghi ngoài phạm vi ở cả hai
nhánh. **0** lượt "xong giả".

## 2. Đọc hai cohort cạnh nhau — dấu đổi chiều, và đó là điều đáng nói

| | C-1 (12 task, n=3, dữ liệu v1.3) | C-1b (3 task, n=6, dữ liệu v1.4) |
|---|---|---|
| AISEF pass@1 | 0,64 | 0,94 |
| trần pass@1 | 0,69 | 0,89 |
| **delta** | **−0,06** | **+0,06** |

Cùng model, cùng harness, hai đợt đo — và hiệu số **đổi dấu**. Đó là hình dạng
của nhiễu, không phải hình dạng của một hiệu ứng. Kết luận đúng của cả hai đợt
là **một**: trên corpus này, với model này, **không đo được cải thiện, cũng không
đo được suy giảm** về tỉ lệ giải. Ai muốn trích một trong hai con số làm bằng
chứng bán hàng thì phải trích cả hai.

Ba nguồn của sự khác nhau ấy, đã biết và đã ghi:

1. **`sec-2` là lỗi bộ dữ liệu, không phải hiệu ứng harness** — đề bài đọc được
   hai nghĩa, sửa một câu thì nhánh AISEF đi từ 0/3 lên 5/6
   ([B-3](BENCH-OBSERVATIONS-C1B.md)). Riêng task này đã chiếm phần lớn hiệu số
   âm của C-1.
2. **`sec-1` là nhiễu mẫu nhỏ** — 0,67 ở n=3 thành 1,00 ở n=6
   ([B-1](BENCH-OBSERVATIONS-C1B.md)).
3. **`state-3` là task duy nhất còn chênh** (+0,17 = một lượt trong sáu). Một
   lượt không phải một hiệu ứng.

## 3. Thứ **giống nhau** ở cả hai cohort: cái giá

| | C-1 | C-1b |
|---|---|---|
| turn, AISEF so với trần | +44 % | +27 % |
| giây, AISEF so với trần | +51 % | +39 % |

Đây là phát hiện nhất quán duy nhất qua hai đợt: **nhánh có harness tốn nhiều
hơn để tới cùng kết cục.** Con số cụ thể thay đổi, dấu thì không.

## 4. Phiên bị CLI cắt: vẫn là kiểu hỏng áp đảo

| điều kiện | phiên | bị cắt | tỉ lệ |
|---|---|---|---|
| AISEF | 69 | 22 | **32 %** |
| trần | 58 | 13 | **22 %** |

9 trong 36 lượt kết thúc bằng một phiên bị cắt — và **6 trong 9 vẫn PASS**, vì
agent đã ghi xong bản sửa trước khi phiên chết. Tỉ lệ theo phiên (32 %/22 %) gần
đúng tỉ lệ của C-1 (31 %/25 %): kiểu hỏng này không phụ thuộc cohort.

**Cơ chế chạy lại hạ tầng đã khai trong giao thức *không nổ lần nào*** — một lỗi
trong chính bản vá của tôi, tìm ra giữa đợt và ghi ở [B-4](BENCH-OBSERVATIONS-C1B.md)
(lỗi 86: phiên bị cắt vẫn để CLI thoát 0 nên `ok=True`, và `exit_status_of` trả
`"ok"` trước khi đọc tới `error`). Hệ quả cho cách đọc: **cả 36 lượt của C-1b
chạy theo đúng định nghĩa "một lượt" của C-1**, nên hai cohort so được với nhau
đúng như bảng ở §2 — khác nhau ở n và ở đề bài `sec-2`, không khác ở định nghĩa.

## 5. Khai báo nhiễu

1. **Máy không rảnh.** Trong cửa sổ `sec-2`/`state-3` tôi chạy suite đầy đủ
   (2 397 test, ~4 phút) một lần và nhiều suite con (`test_clients`,
   `test_implement`, ~2 phút mỗi lần) nhiều lần, cộng việc sửa mã và commit.
   `duration_ms` có thể bị thổi lên; số turn và kết cục không phụ thuộc tải máy.
2. **Mã của hệ đang đo đổi giữa đợt** — nhưng không tới được tiến trình đang
   chạy (cùng lý do [O-11](BENCH-OBSERVATIONS-C1.md)): tôi sửa
   `clients/opencode.py` lúc ~05:0x, và `state-3` nhánh trần chạy sau đó vẫn
   dùng mã cũ. Kiểm được bằng chính B-4: không có `bench:infra_retry` nào.
3. **`sec-2` dùng đề bài v1.4**, hai task kia không đổi byte — nên chỉ `sec-2`
   là không so trực tiếp được với C-1.
4. **Ghi vào `.bench-c1b/`** để không xoá cây làm việc của C-1; bằng chứng C-1
   còn nguyên.

## 6. Việc kéo theo

| # | Việc | Trạng thái |
|---|---|---|
| 1 | Lỗi 86 (`ok=True` che phiên bị cắt) | ✅ sửa 13/09, có hiệu lực từ đợt sau |
| 2 | Cột 2 — đổi model sau alias | ⏳ chờ chủ dự án |
| 3 | Đo trên cặp model↔CLI **không** có kiểu hỏng phiên bị cắt | ⏳ — đây là việc đáng làm nhất còn lại: 32 %/22 % phiên bị cắt làm mọi hiệu số nhỏ hơn nó trở thành vô nghĩa |
| 4 | Tuyển task theo tiêu chí "đã từng có nhánh thắng nhánh kia" | ⏳ — C-1 cho 9 lượt có thông tin trên 6 giờ; C-1b cho 36 lượt có thông tin trên 2 giờ |
