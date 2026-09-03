---
name: aisdlc-mockup-html
description: Dựng mockup HTML tĩnh cho MỘT màn hình từ DESIGN.md + EXPERIENCE.md, kèm siêu dữ liệu để máy trích hợp đồng thị giác. Dùng ở bước 3 của AI-SDLC, trước khi viết code.
---

# Mockup HTML — một màn hình, một file

Mockup ở đây không phải bản vẽ để ngắm. Nó là **hợp đồng**: máy sẽ trích
từ nó danh sách component, nhãn và ràng buộc nhập liệu, rồi sau này đối
chiếu với ứng dụng thật. Component nào có trong mockup mà ứng dụng không
dựng thì cổng chặn.

Hệ quả: mọi thứ bạn đặt vào đây là **cam kết**, không phải gợi ý. Đừng
thêm nút cho đẹp.

## Đầu vào

| Nguồn | Lấy gì |
|---|---|
| `DESIGN.md` | token màu, chữ, bo góc, khoảng cách, đặc tả component |
| `EXPERIENCE.md` | mục đích màn hình, lối vào, component và luật hành vi, các trạng thái |
| `prd.md` | nội dung thật để điền — tên, nhãn, thông báo |

Một lượt chạy dựng **đúng một màn hình**. Không dựng kèm màn hình khác.

Nếu dự án có sẵn skill `ui-ux-pro-max`, `design-system` hoặc `ui-styling`
thì dùng chúng cho phần nghề thị giác — nhịp, thang chữ, trạng thái tương
tác. Nhưng **`DESIGN.md` thắng khi mâu thuẫn**: nó là quyết định đã chốt
của dự án này, còn skill là kiến thức chung.

## Bắt buộc

1. **Hai thẻ meta** trong `<head>` — máy đọc chúng để nối mockup với màn
   hình và với route thật:

   ```html
   <meta name="aisdlc-screen" content="{screen_id}">
   <meta name="aisdlc-route" content="/duong-dan/that">
   ```

   `aisdlc-route` là đường dẫn màn hình này sẽ có trong ứng dụng. Chưa
   chốt được thì xem mục "Chỗ chưa chốt" bên dưới — **không** bịa.

2. **Mọi phần tử tương tác phải có tên gọi đọc được.** Nút, ô nhập, liên
   kết, tab đều cần nhãn thật: `<label for>`, `aria-label`, hoặc chữ nằm
   trong phần tử. Phần tử không tên thì hợp đồng không thấy nó, và người
   dùng màn hình đọc cũng không.

3. **Ràng buộc nhập liệu viết bằng thuộc tính HTML**, không viết bằng chữ:
   `required`, `type`, `pattern`, `minlength`, `maxlength`, `min`, `max`.
   Đây là phần hợp đồng mà code phải thực thi đúng.

4. **Chạy được ngoại tuyến**: CSS đặt trong `<style>`, font hệ thống,
   không `<script>`, không tải ảnh hay font từ mạng. Cần ảnh thì dùng ô
   màu hoặc SVG nội tuyến.

5. **Nội dung thật.** Lấy từ PRD và EXPERIENCE. Không lorem ipsum, không
   "Item 1 / Item 2".

6. **Đánh dấu vùng dữ liệu** bằng `data-sample` — hàng danh sách, thẻ kết
   quả, mọi thứ ứng dụng thật sẽ vẽ ra từ dữ liệu:

   ```html
   <ul data-sample="danh sách ghi chú lấy từ Kho cục bộ"> … </ul>
   ```

   Bên trong vùng này, hợp đồng chỉ ghi nhận **có kiểu phần tử gì**, không
   ghi nhận tên gọi — vì ứng dụng thật hiển thị dữ liệu khác. Không đánh
   dấu thì "Đặt lịch khám răng" trở thành cam kết, cổng sẽ đỏ mãi mãi, và
   một cổng đỏ mãi mãi thì bị tắt.

7. **Trạng thái**: dựng trạng thái chính. Trạng thái nào EXPERIENCE.md nêu
   là load-bearing (rỗng, lỗi, đang tải) thì dựng thêm trong cùng file,
   mỗi trạng thái một `<section>` có tiêu đề rõ.

## Chỗ chưa chốt

Gặp chỗ chưa quyết được thì **đánh dấu, đừng tự chọn**:

```html
<div data-unresolved="OQ-3: ghi chú có tiêu đề riêng hay lấy dòng đầu?">
```

Cổng máy sẽ chặn khi còn dấu này. Đó là chủ ý: dựng code theo một màn hình
chưa chốt tốn gấp đôi — một lần làm, một lần làm lại.

## Không làm

* Không thêm component không có trong `Component Patterns` của
  EXPERIENCE.md. Cần thêm thì ghi `data-unresolved` và dừng.
* Không dùng framework CSS tải từ mạng.
* Không đặt chữ giả vào chỗ đáng lẽ là dữ liệu thật.
* Không dựng nhiều màn hình trong một file.

## Xong khi

File `mockups/{screen_id}.html` mở được ngoại tuyến, có hai thẻ meta, mọi
phần tử tương tác đều có tên, và mọi ràng buộc nhập liệu đều nằm ở thuộc
tính HTML.
