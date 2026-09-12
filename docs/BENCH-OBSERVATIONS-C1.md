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
## O-7 · Nguyên nhân thật của gần như mọi lượt trượt: **model tự cắt phiên**

Đây là quan sát quan trọng nhất của đợt, và nó lật lại cách đọc ở O-2/O-3.

Đọc kho phiên của OpenCode (`~/.local/share/opencode/opencode.db`, bảng `part`)
cho 66 phiên đã ánh xạ được về đợt C-1, thấy một chữ ký lặp lại:

```
{"type":"text","text":"<think>\n</think>\n\n<minimax:tool_call>\n<invoke name=\"read\">…</invoke>\n</minimax:tool_call>"}
{"reason":"stop", …}
```

Model in **cú gọi công cụ theo cú pháp riêng của MiniMax ra dưới dạng văn bản**.
OpenCode không phân giải được nên coi đó là câu trả lời cuối; bước kết thúc với
`reason = "stop"` và phiên dừng ngay tại đó. Trong **11/11** phiên có chữ ký
này, nó là phần văn bản **cuối cùng** — không phiên nào hồi phục.

**Nó giải thích gần hết các lượt trượt:**

| | lượt trượt | trong đó kết thúc bằng chữ ký trên |
|---|---|---|
| AISEF | 7 | 6 |
| trần | 1 | 1 |

7/8 lượt trượt của cả hai nhánh là **phiên bị cắt giữa chừng**, không phải agent
sửa sai. Lượt còn lại (`sec-2` AISEF lượt 2) kết thúc bình thường mà không ghi gì.

**Tỉ lệ theo phiên, và nó lệch giữa hai nhánh:**

| điều kiện | phiên | phiên bị cắt | tỉ lệ |
|---|---|---|---|
| AISEF (`opencode`) | 39 | 10 | 26 % |
| trần (`opencode-bare`) | 27 | 2 | 7 % |

Chỉ tính ba task mà chữ ký này xuất hiện (`sec-1`, `sec-2`, `state-1`): AISEF
10/14, trần 2/7. Năm task còn lại: **0 phiên bị cắt ở cả hai nhánh**.

**Ba cách giải thích đã đo và bị loại:**

- *"Nhánh AISEF nhồi ngữ cảnh dài hơn nên model hỏng sớm hơn."* Không đúng theo
  số: trung vị đỉnh token mỗi phiên là **40 314** (AISEF) so với **40 138**
  (trần) — bằng nhau. Trung bình lệch nhẹ (48 356 / 44 632) do đuôi dài.
- *"`aisef ctx` bơm ngữ cảnh khổng lồ."* Có một lần in 55 351 ký tự — nhưng
  **đúng một lần trong 66 phiên**. Không phải nguyên nhân hệ thống. Ghi cả cái
  vô can vào đây để lần sau khỏi nghi oan.
- *"Prompt của AISEF mồi cho model dùng cú pháp XML."* Prompt là Markdown
  thuần, không có `<invoke`, không có thẻ công cụ nào —
  `.bench/run/opencode/bug-a2-state-1/a1` lưu nguyên văn.

Vậy **vì sao nhánh AISEF dính nhiều hơn thì chưa có câu trả lời có bằng chứng**.
Ghi là câu hỏi mở, không suy diễn.

**Một điều nhánh AISEF làm được mà nhánh trần không:** trên `sec-1` lượt 1 và 2,
phiên đầu chết vì chữ ký này, harness mở **phiên thứ hai** và lượt đó vẫn PASS.
Nhánh trần có đúng một phiên cho mỗi lượt: phiên chết là lượt trượt. Đây là
phần "33 và 72 turn" ở O-3 — cái giá của việc chạy lại chính là thứ đã cứu hai
lượt ấy.

**Hệ quả cho đợt đo.** Cột C-1 đang đo **lỗi tích hợp giữa model và CLI** ít
nhất ngang với đo chất lượng harness. Không đổi gì giữa chừng; đợt chạy tiếp tục
tới hết, và câu hỏi "cột này có công bố được không" để dành cho báo cáo.

**Việc phải làm sau khi đợt đo kết thúc** (không làm bây giờ — guard và adapter
là một phần của hệ đang đo): dạy `aisef/clients/opencode.py` nhận ra chữ ký
`reason=stop` + văn bản cuối chứa cú pháp công cụ chưa phân giải + không có
`file_change`, và xếp nó vào nhóm trạng thái **hạ tầng, chạy lại được**, thay vì
coi là một phiên đã hoàn thành. Đây đúng là mục "phát hiện đứng máy trong phiên"
đã hoãn ở [ADR-010 §8](ADR-010-mimo-code-lessons.md) — nay có chữ ký đo được.
## O-8 · `state-1`: phép tách đã chạy — **cả hai nhánh cùng trượt 0/3**

Ở O-3 tôi viết: phép tách sạch cho giả thuyết "điều kiện AISEF dẫn agent đi lạc
vào hàm đọc env" là các task **không** nói về env/scope. `state-1` là task đầu
tiên như vậy, và kết quả không ủng hộ giả thuyết:

| điều kiện | lượt 1 | lượt 2 | lượt 3 | pass@1 |
|---|---|---|---|---|
| AISEF | FAIL (22 turn, 291 s, 0 tệp) | FAIL (15 turn, 229 s, 0 tệp) | FAIL (46 turn, 826 s, 1 tệp) | **0,00** |
| trần | FAIL (11 turn, 313 s, 0 tệp) | FAIL (30 turn, 408 s, 0 tệp) | FAIL (13 turn, 184 s, 0 tệp) | **0,00** |

Guard chặn: 0. Ghi ngoài phạm vi: 0. **Năm trong sáu lượt không ghi một tệp
nào**, và cả sáu phiên đều mang chữ ký O-7 — model in cú gọi công cụ ra dưới
dạng văn bản rồi phiên dừng.

Ba điều chốt lại từ đây:

1. **Giả thuyết "dữ liệu phạt nhánh AISEF" không còn giải thích được số liệu.**
   Nó dựng lên để giải thích `sec-1`/`sec-2`; trên task không nói gì về env thì
   hai nhánh trượt như nhau. Cách đọc còn sống là cách đọc O-7: cái đang quyết
   định kết cục là phiên bị cắt, không phải điều kiện thí nghiệm.
2. **Lượt trượt duy nhất có ghi tệp đi vào `run_attempt`/`verify_candidate`/
   `implement_story`** — vòng lặp của harness, không phải hàm đọc env. Đây cũng
   là bằng chứng ngược với mẫu ở O-3.
3. **Tỉ lệ phiên bị cắt của hai nhánh đang xích lại gần nhau** khi có thêm dữ
   liệu: 26 %/7 % ở O-7 (sau 7 task) thành **27 % (11/41) và 14 % (4/28)** sau
   `state-1`. Chênh lệch còn đó nhưng nhỏ hơn một nửa so với lúc đầu; đừng xây
   kết luận trên nó cho tới khi hết 12 task.

Từ lúc này chỉ số "phiên bị cắt" **được đo bằng mã, không bằng SQL gõ tay**:
`python3 -m tests.bench analyze` in ra bảng ấy (`tests/bench/_analyze.py ::
cut_sessions`), nên con số trong báo cáo là con số dựng lại được.
