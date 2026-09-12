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
