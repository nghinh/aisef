# Cột C-1 — quan sát ghi trong lúc chạy

Ghi **tại thời điểm quan sát**, kèm đường dẫn bằng chứng, trước khi có tổng kết.
Một nhận định viết sau khi nhìn bảng cuối cùng luôn có mùi chọn kết luận; mục
này tồn tại để chống điều đó.

Bối cảnh: 12 task A-2, 3 lượt × 2 điều kiện, OpenCode, model nền sau alias
`9router/mycombo` là **MiniMax-M2.7** (lời khai chủ dự án 2026-09-12). Giao
thức: `BENCH-PROTOCOL-v1.3 § Addendum C-1`, đóng băng trước khi chạy.

---

## O-1 · Năm task đầu: không có chênh lệch, và **guard không nổ lần nào**

`sec-4`, `sec-3`, `multi-1`, `multi-3`, `multi-2`: pass@1 = 1,00 ở cả hai điều
kiện, tổng **0 lần guard chặn trên 30 phiên**.

Điều đáng ghi không phải con số bằng nhau mà là con số 0 kia: harness không
những không đổi kết cục — nó **không có gì để chặn**. Model ở mức này không thử
ghi ra ngoài phạm vi, không gọi lệnh phá huỷ, không tuyên bố xong khi test còn
đỏ. Guard chỉ có giá trị khi có hành vi cần chặn.

## O-2 · `sec-2`: chênh lệch đầu tiên, và nó **ngược chiều harness**

| điều kiện | lượt 1 | lượt 2 | lượt 3 | pass@1 |
|---|---|---|---|---|
| AISEF | FAIL (15 turn) | FAIL (14 turn) | FAIL (35 turn, 491 s) | **0,00** |
| trần | PASS (15 turn) | PASS (15 turn) | FAIL (13 turn) | **0,67** |

Guard chặn: 0. Không phải harness ngăn bản sửa.

**Đọc diff mới thấy vấn đề — hai điều kiện sửa hai chỗ khác nhau:**

- Nhánh **trần** sửa `check_diff_scope` — đúng chỗ test hồi quy đòi
  (`test_ten_tep_pham_loi_dung_truoc_danh_sach_pham_vi`): đưa tên tệp phạm lỗi
  lên trước danh sách phạm vi.
  Bằng chứng: `.bench/run/opencode-bare/bug-a2-sec-2/a1`, commit `9a81ce9`.
- Nhánh **AISEF** sửa `effective_scope` ở lượt 1 và lượt 3 — hàm **tính phạm vi
  từ biến môi trường**, không phải hàm sinh thông báo.
  Bằng chứng: `.bench/run/opencode/bug-a2-sec-2/a1` commit `bb9a642`, và `a3`.
- Lượt 2 của nhánh AISEF **không ghi tệp nào**: `HEAD` vẫn là commit nền, nên
  `git show HEAD` in ra cả cây (364 tệp). Đây là lớp "phiên im lặng" mà chính
  kho này đã ghi ở lỗi 68/69 — lần này xảy ra trong bench chứ không trong story.

**Giả thuyết (chưa chứng minh, n = 1 task):** nhánh AISEF chạy **với biến
`AISEF_WRITE_SCOPE` trong môi trường và plugin guard trong cây**. Đề bài nói về
"phạm vi ghi", và agent ở nhánh ấy có một hiện thực sống của khái niệm đó ngay
trong phiên của mình — nó đi tới hàm đọc phạm vi từ env thay vì hàm in thông
báo. Nhánh trần không có gì để bị dẫn đi, nên bám vào test.

Nếu đúng, đây **không phải** kết luận về chất lượng harness mà là một **lỗ hổng
của chính bộ dữ liệu**: mọi task ở đây là lỗi của AISEF, và điều kiện AISEF đặt
trạng thái chạy của AISEF vào trong kho mà agent đang sửa. Điều kiện thí nghiệm
làm nhiễu đề bài — theo hướng **phạt nhánh AISEF**.

**Phản chứng cần tìm trước khi tin:** nếu giả thuyết đúng thì các lượt trượt
khác của nhánh AISEF cũng phải rơi vào hàm liên quan tới trạng thái chạy
(env, guard, scope), chứ không rải đều. Nếu chúng rải đều thì giả thuyết sai và
`sec-2` chỉ là một task có đề bài mơ hồ.

**Đề bài của `sec-2` có mơ hồ thật:** triệu chứng viết "thông báo cắt bỏ danh
sách phạm vi được phép, chỉ in tên tệp sai — agent không biết mình được phép
ghi đâu". Câu ấy đọc được theo hai nghĩa: *thông báo in thiếu* (đúng, chỗ
`check_diff_scope`) hoặc *phạm vi tính sai* (sai chỗ, nhưng là cách đọc tự
nhiên nếu đang sống trong một phiên có phạm vi ghi thật). Một đề bài mà hai
điều kiện đọc ra hai nghĩa khác nhau là đề bài cần sửa — nhưng **không sửa giữa
đợt đo**; ghi vào đây, sửa ở v1.4 và nêu trong báo cáo.

## O-3 · `sec-1`: giả thuyết đứng vững, nhưng vẫn chưa tách khỏi một cách đọc khác

| điều kiện | lượt 1 | lượt 2 | lượt 3 | pass@1 |
|---|---|---|---|---|
| AISEF | PASS (33 turn, 461 s) | PASS (72 turn, 1115 s) | FAIL (15 turn) | 0,67 |
| trần | PASS (8 turn, 76 s) | PASS (26 turn, 144 s) | PASS (9 turn, 74 s) | **1,00** |

Hai điều đáng ghi.

**Một: phản chứng đã được kiểm, và giả thuyết sống sót.** Ở O-2 tôi viết "nếu
các lượt trượt của nhánh AISEF rải đều thì giả thuyết sai". Chúng **không** rải
đều. Cả ba lượt trượt có ghi tệp của nhánh AISEF rơi vào đúng một họ hàm:

| task | lượt | hàm đã sửa |
|---|---|---|
| `sec-1` | 3 | `scope_from_env`, `story_from_env`, `disallowed_from_env` |
| `sec-2` | 1 | `effective_scope` |
| `sec-2` | 3 | `scope_from_env`, `story_from_env`, `effective_scope` |

Mọi hàm trong danh sách đều đọc **biến môi trường mà chính điều kiện AISEF đặt
ra**. Lượt trượt duy nhất của nhánh trần thì không ghi gì — một kiểu hỏng khác
hẳn.

**Hai: nhánh AISEF tốn nhiều hơn hẳn để tới cùng kết quả.** Trên `sec-1`, 33 và
72 turn so với 8 và 26; một lượt chạy 1115 giây. Cùng model, cùng đề bài, cùng
dữ liệu — khác nhau ở chỗ nhánh AISEF có trạng thái chạy của harness trong cây.

**Cách đọc thứ hai chưa loại được.** Các task `sec-*` **vốn nói về** mã guard và
phạm vi ghi, nên "sửa hàm đọc phạm vi" có thể chỉ là "sửa quanh chỗ lỗi", không
phải bị dẫn đi lạc. Điểm phân biệt: ở `sec-2`, nhánh trần cũng sửa trong cùng
tệp `guardrails.py` nhưng đi tới `check_diff_scope` — đúng hàm mà test hồi quy
gọi tên — còn nhánh AISEF đi tới các hàm đọc env. Cùng tệp, khác hàm, khác kết
cục.

Phép tách sạch: nhánh AISEF có trượt trên các task **không** nói về env/scope
(`multi-*`, `state-*`) hay không, và nếu có thì trượt ở đâu. Tới lúc này
`multi-*` chưa có lượt trượt nào của nhánh AISEF. Năm task còn lại quyết định.

## O-4 · Lần guard chặn đầu tiên của cả đợt — và nó là **báo động nhầm**

`sec-1`, nhánh AISEF, lượt 2 (phiên 72 turn / 1 115 s): `guard_block = 1`. Đây
là lần chặn duy nhất trong 45 phiên đã chạy tới lúc này.

Sự kiện (`.bench/run/opencode/bug-a2-sec-1/a2/_bmad-output/evidence/bug-a2-sec-1.jsonl`, seq 100–101):

```
guard_check destructive  verdict=block
guard_block destructive  "destructive command blocked (xoá đệ quy)."
```

Lệnh bị chặn (khôi phục từ kho phiên của OpenCode, `part` có `callID =
call_function_3rex724gvu7d_1`):

```
cd …/bug-a2-sec-1/a2 && find . -name "*.pyc" -delete \
  && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; python3 -m unittest …
```

Tức là **dọn cache Python trong chính cây làm việc** — vô hại. Guard chặn mọi
`rm -rf` đệ quy không xét đích, nên nó chặn cả cái này. Giá phải trả: một turn;
seq 102 đã `allow` trở lại và phiên vẫn PASS.

Hai điều rút ra, ghi lại chứ **chưa sửa**:

1. Câu khuyên trong thông báo sai ngữ cảnh: "stop and report to a human" là
   đúng cho `rm -rf /` nhưng vô lý cho `__pycache__`. Sửa câu chữ thì rẻ.
2. Nới chính sách để cho phép xoá đệ quy "có vẻ vô hại" thì **không** rẻ:
   `__pycache__/../..` cũng khớp mọi bộ lọc theo tên. Đề xuất hiện tại là giữ
   nguyên hành vi chặn, chỉ sửa thông báo.

**Không đụng vào `guardrails.py` trước khi đợt đo kết thúc**: plugin guard là
một phần của điều kiện thí nghiệm; đổi nó giữa chừng là đổi hệ đang đo.

## O-5 · `sec-1` lượt 3: nhánh AISEF **làm đỏ** đúng bài test về phạm vi

Lượt trượt duy nhất có ghi tệp của nhánh AISEF trên `sec-1` không chỉ *sửa* hàm
đọc env — nó phá một bài test P2P:

```
p2p_red = ['tests.test_guardrails.TestEffectiveScope.test_planning_scope_when_no_story']
```

Đây là bằng chứng mạnh hơn O-3 một bậc: không phải "sửa quanh chỗ lỗi" mà là
**đổi ngữ nghĩa `effective_scope`** tới mức hồi quy. Ba lượt trượt có ghi tệp
của nhánh AISEF nay đều quy về một điểm: khái niệm *phạm vi ghi* — thứ mà chính
điều kiện AISEF đang hiện thực hoá sống trong phiên của agent.

Vẫn chưa đủ để kết luận. Phép tách vẫn là `state-*`/`multi-4`.

## O-6 · Khai báo nhiễu: những gì **không** sạch trong đợt này

Ghi ra vì chúng có thể ảnh hưởng tới con số, kể cả khi tôi tin là ảnh hưởng nhỏ.

- **Máy không rảnh trong cửa sổ `state-1`.** Khoảng 22:00–22:04 ngày 12/09 tôi
  chạy toàn bộ suite (2 336 test, 240 s) trên cùng máy với đợt đo — vi phạm
  chính ràng buộc "không chạy suite đầy đủ trong lúc đo" đã ghi ở kế hoạch. Hệ
  quả có thể có: `duration_ms` của lượt đang chạy khi đó bị thổi lên. Số turn,
  kết cục PASS/FAIL, `f2p`/`p2p` **không** phụ thuộc tải máy. Không sửa số,
  không chạy lại — ghi vào đây để người đọc trừ hao đúng chỗ.
- **`multi-3` có 6 lượt ở nhánh AISEF thay vì 3**, hệ quả của lần đợt đo bị giết
  rồi chạy lại theo chunk. Quy tắc xử lý: **lấy 3 lượt sớm nhất theo thứ tự
  ghi**. Quy tắc này được tuyên bố *sau* khi đã thấy cả 6 lượt đều PASS, nên nó
  không chọn được kết quả nào có lợi — mọi cách lấy đều cho 3/3. Ghi rõ để lần
  sau tuyên bố trước.
- **Cột `cost_usd` là 0,00 ở toàn bộ 45 dòng.** OpenCode không trả chi phí qua
  9router cho alias này, nên mọi so sánh "tỉ lệ chi phí" trong đợt C-1 **không
  có dữ liệu**; dùng số turn và giây làm đại lượng thay thế, và nói rõ đó là đại
  lượng thay thế.
