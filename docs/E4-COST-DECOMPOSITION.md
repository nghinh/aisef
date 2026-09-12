# E4 — "70 $/story tiêu vào đâu"

Thí nghiệm E4 của [kế hoạch 360](DANH-GIA-360-2026-09-12.md) § đợt 1. Chi phí:
0 $ — chỉ đọc lại bằng chứng đã lưu.

**Đổi dự án đo, và nói rõ vì sao.** Kế hoạch ghi "phân rã chi phí e9". Cây bằng
chứng của e9 **không còn** (chỉ còn `node_modules`), nên corpus 496 $ ấy không
kiểm toán được nữa. Đo trên `todo-e2e` — dự án thật, 10 story, vòng đời đầy đủ,
bằng chứng còn nguyên. Kết luận dưới đây là về `todo-e2e`, không phải về e9.

**Nhà cung cấp không trả về chi phí.** `cost_usd = 0` ở toàn bộ 2 214 sự kiện
(9router). Nên ở đây đếm **token** và in công thức quy đổi, không bịa ra đô la.

Dựng lại:

    python3 -m framework.bench.cost_decomp ~/Downloads/projects/todo-e2e

---


## Theo vai

| vai | phiên | token vào | token ra | cache đọc | % token vào |
|---|---|---|---|---|---|
| developer | 34 | 10,465,207 | 127,244 | 30,774,272 | 69% |
| khác | 8 | 2,061,987 | 34,946 | 1,845,888 | 14% |
| reviewer | 27 | 1,682,030 | 45,037 | 9,231,488 | 11% |
| security | 27 | 999,435 | 11,654 | 4,711,296 | 7% |

## Theo phán quyết của cổng cho lượt đó

| lượt | phiên | token vào | token ra | cache đọc | % token vào |
|---|---|---|---|---|---|
| lượt bị cổng chặn | 61 | 10,176,854 | 138,428 | 32,857,600 | 67% |
| lượt cổng cho qua | 27 | 2,969,818 | 45,507 | 11,859,456 | 20% |
| chưa tới cổng | 8 | 2,061,987 | 34,946 | 1,845,888 | 14% |

## Cổng chặn vì gì

| mục kiểm | số lần chặn |
|---|---|
| review | 18 |
| tests verify story | 3 |
| criteria have tests | 2 |
| TDD | 2 |
| guard ran | 1 |
| security | 1 |
| test | 1 |
| e2e | 1 |
| accessibility | 1 |
| preservation | 1 |

## Quy ra tiền

Không có giá thật thì không in ra số tiền giả. Công thức, với `p` = giá 1 triệu token vào và `q` = giá 1 triệu token ra:

    chi phí ≈ 15.21 × p + 0.219 × q     (toàn dự án)
    chi phí mỗi story ≈ 0.95 × p + 0.014 × q

Token đọc từ cache tính riêng vì phần lớn bảng giá tính nó rẻ hơn nhiều; dự án này đọc cache 46,562,944 token.


---

## Phân bố theo story: trung bình là con số vô nghĩa ở đây

| story | phiên | token vào | % toàn dự án |
|---|---|---|---|
| STORY-01-02 | 14 | 7 264 566 | **48 %** |
| STORY-01-01 | 3 | 1 989 747 | 13 % |
| STORY-02-01 | 15 | 947 270 | 6 % |
| `plan-*` + `mockup-*` (11 phiên) | 11 | 2 061 987 | 14 % |
| 7 story còn lại | 53 | ~2,9 M | 19 % |

Và bên trong STORY-01-02, **một phiên duy nhất** chiếm gần hết:

| phiên | turn | token vào |
|---|---|---|
| `STORY-01-02#1` (lần chạy đầu) | **77** | **6 390 823** |
| 13 phiên còn lại của story ấy | 1–27 | 873 743 |

6,39 triệu token vào trong một phiên = **42 % toàn bộ token vào của cả dự án**.
"70 $/story" không phải một chi phí trung bình cho mỗi story; nó là một phiên
chạy lồng kéo trung bình lên.

## Ba kết luận

1. **Hai phần ba token mua về một lượt bị cổng chặn** (67 % token vào). Đây
   không phải lãng phí thuần — cổng chặn là thứ đang giữ chất lượng — nhưng nó
   là chỗ tiền đi, và nó đo được.
2. **`review` là mục chặn áp đảo**: 18 trên 31 lần chặn, gấp sáu lần mục thứ
   hai. Trùng với `aisef status --attempts` trên cùng dự án (18/19 lần chặn ở
   cổng là `review`). Muốn giảm chi phí thật thì phải làm việc với vòng lặp
   review, không phải với prompt.
3. **Trần lượt có được khai, nhưng không ai thi hành.** ~~`run.max_turns = 40`
   không được truyền ở `phases/implement.py`~~ — **sai, sửa 13/09**: spec của
   pha implement dựng ở `harness/routing.py:152` và nó **có**
   `max_turns=cfg["run.max_turns"]`. Lỗi thật nằm một tầng dưới:
   `clients/opencode.py` không có cách nào **thi hành** con số ấy, vì OpenCode
   CLI không có cờ giới hạn lượt (`claude_code.py` có `--max-turns`). Nên với
   client này `run.max_turns` là một knob không ai đọc, và thứ duy nhất chặn
   phiên 77 turn kia là `run.timeout_seconds = 1800`. Một trần theo thời gian
   không phải trần theo chi phí.

   Bằng chứng độc lập tìm được sau đó, trên đợt đo C-1: khai trần 40, một phiên
   chạy **61 lượt** rồi chỉ dừng vì đồng hồ ([O-10](BENCH-OBSERVATIONS-C1.md)).
   Đã sửa 13/09: adapter đếm `step_finish` trên luồng và dừng tiến trình khi
   chạm trần, báo `exit_status = max_turns`.

## Việc phải làm (quyết định, chưa thực hiện)

Đang có đợt đo C-1 chạy; `implement.py` và adapter OpenCode nằm trong hệ đang
đo, nên **không sửa giữa chừng**. Sau khi đợt đo đóng:

| # | Việc | Vì sao ngay bây giờ thì không |
|---|---|---|
| 1 | ~~`implement.py` truyền `run.max_turns`~~ — **không cần**: `harness/routing.py` đã truyền | chẩn đoán sai, sửa 13/09 |
| 2 ✅ | Adapter OpenCode tự đếm lượt trên luồng sự kiện và dừng tiến trình khi chạm trần, báo `exit_status = max_turns` | **xong 13/09** (`_stream_with_timeout(stop_when=…)`); phép thử giết tiến trình thật ở lượt thứ 5 |
| 3 | Ghi cảnh báo khi một phiên vượt **x lần** trung vị token của dự án | cần số trung vị từ chính bảng trên, làm sau là đúng thứ tự |

Ba việc trên đều là **giảm chi phí mà không hạ cổng nào** — trần lượt chặn phiên
chạy lồng, không nới một mục kiểm nào.
