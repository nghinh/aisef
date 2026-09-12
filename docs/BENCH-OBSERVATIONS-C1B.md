# Cohort C-1b — quan sát ghi trong lúc chạy

Cùng kỷ luật như [C-1](BENCH-OBSERVATIONS-C1.md): ghi **tại thời điểm quan sát**,
kèm đường dẫn bằng chứng, trước khi có bảng cuối. Giao thức đóng băng ở
[BENCH-PROTOCOL-v1.3 § Addendum C-1b](BENCH-PROTOCOL-v1.3.md).

Bối cảnh: 3 task phân biệt được của C-1 (`sec-1`, `sec-2`, `state-3`), **6 lượt**
mỗi nhánh, bộ dữ liệu **v1.4**, `INFRA_RETRIES = 1`, model vẫn **MiniMax-M2.7**
(lời khai chủ dự án 13/09). Ghi vào `.bench-c1b/`, không chạm bằng chứng C-1.

---

## B-1 · `sec-1`: 6/6 ở **cả hai** nhánh — chênh lệch ở C-1 là nhiễu

| | C-1 (n=3) | C-1b (n=6) |
|---|---|---|
| AISEF | 0,67 | **1,00** |
| trần | 1,00 | **1,00** |

Lượt trượt duy nhất của nhánh AISEF ở C-1 (`sec-1` lượt 3) là một phiên bị CLI
cắt. Với n=6 và phiên hạ tầng được chạy lại, nó không tái diễn: **0 lần chạy lại
hạ tầng trong 12 phiên** — tức 12 phiên này không có phiên nào bị cắt.

Đây là bài học về mẫu nhỏ, không phải về harness: một task mà n=3 nói "AISEF kém
hơn 0,33" thì n=6 nói "bằng nhau". Ai đọc bảng C-1 nên trừ hao đúng chỗ này, và
báo cáo C-1 đã nói −0,06 không phân biệt được với nhiễu — đây là một ví dụ cụ thể
của chính câu ấy.

**Thứ *không* đổi: cái giá.** AISEF 16 turn / 148 s so với trần 9 turn / 78 s —
gần gấp đôi, giống hệt hình dạng đã thấy ở C-1 (33/9 turn trên cùng task). Kết
cục bằng nhau, chi phí không bằng nhau.

## B-2 · Bản vá câu chữ guard đã được kiểm **trên phiên thật**

`sec-1` lượt 4 (`.bench-c1b/run/opencode/bug-a2-sec-1/a4`): guard `destructive`
nổ, và thông báo mới xuất hiện nguyên văn trong bằng chứng:

```
destructive command blocked (xoá đệ quy). Recursive delete is blocked whatever
the target: a path filter cannot tell `__pycache__` from `__pycache__/../..`.
Caches do not need deleting — tests must pass without cleaning.
```

Cùng lệnh, cùng ca như [O-4](BENCH-OBSERVATIONS-C1.md) — nhưng lần này lượt ấy
**PASS**. Không kết luận "thông báo tốt hơn nên agent làm đúng" từ n=1; điều
kiểm được là bản vá đi tới đúng nơi nó phải tới, trong một phiên agent thật,
không phải chỉ trong unit test.
## B-3 · `sec-2`: sửa một câu đề bài, nhánh AISEF đi từ **0/3 lên 5/6**

| `sec-2` | C-1 (đề bài v1.3, n=3) | C-1b (đề bài v1.4, n=6) |
|---|---|---|
| AISEF | **0,00** (0/3) | **0,83** (5/6) |
| trần | 0,67 (2/3) | **0,83** (5/6) |

Hai nhánh nay bằng nhau. Nghĩa là hiệu số **−0,67** — chênh lệch lớn nhất của
toàn bộ cohort C-1, và là một trong hai task duy nhất mà nhánh AISEF kém hơn —
**là lỗi của bộ dữ liệu**, không phải hiệu ứng của harness. Giả thuyết ở
[O-2](BENCH-OBSERVATIONS-C1.md) đúng, và cách chữa (sửa đề bài sau khi đóng
đợt, ghi cả hai hash) là cách chữa đúng.

Hệ quả cho cách đọc C-1: trong hai task mà AISEF kém hơn, **một là đề bài mơ hồ**
(`sec-2`) và **một là nhiễu mẫu nhỏ** (`sec-1`, xem B-1). Báo cáo C-1 nói −0,06
không phân biệt được với nhiễu; C-1b cho thấy cụ thể nhiễu ấy đến từ đâu.

## B-4 · Cơ chế chạy lại hạ tầng **không nổ lần nào** — lỗi trong chính bản vá của tôi

Giao thức C-1b khai `INFRA_RETRIES = 1`. Thực tế trên 24 lượt đầu:

- **8/24 lượt** kết thúc bằng phiên bị CLI cắt (cột `ghi chú` của bảng mang
  nguyên văn `client could not parse the model's tool call…`), trong đó 6 lượt
  vẫn PASS vì agent đã ghi xong bản sửa trước khi phiên chết;
- **0 sự kiện `bench:infra_retry`** trong toàn bộ bằng chứng.

Nguyên nhân, tìm bằng đọc mã rồi kiểm bằng một tiến trình thật: khi phiên bị
cắt, OpenCode **vẫn thoát 0** — nó tưởng phiên kết thúc bình thường. `run()` đặt
`res.ok = returncode == 0 and …`, nên `ok = True`; và `exit_status_of` trả `"ok"`
**ngay dòng đầu** khi `res.ok`, không bao giờ đọc tới `error`. Bản vá "nhận diện
phiên bị cắt" vì thế đặt đúng `error` và `retryable` vào một kết quả mà không ai
hỏi nữa.

Đã sửa (`res.ok` còn đòi `not res.error`) + phép thử đi qua đúng `run()` với một
tiến trình thật thoát 0. **Nhưng bản vá không áp cho C-1b đang chạy**: tiến trình
đo nạp module lúc khởi động (cùng lý do đã ghi ở [O-11](BENCH-OBSERVATIONS-C1.md)).

**Vậy đọc C-1b thế nào:** cả 36 lượt chạy dưới **đúng định nghĩa "một lượt" của
C-1** — không có chạy lại hạ tầng. Điều này làm C-1b **dễ so với C-1 hơn**, không
khó hơn: hai đợt khác nhau đúng hai thứ đã khai (n = 6, đề bài `sec-2` v1.4).
Cơ chế chạy lại sẽ có hiệu lực từ đợt sau, và giao thức phải ghi rõ điều đó.
