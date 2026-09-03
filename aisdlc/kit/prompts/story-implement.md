---
name: story-implement
version: 2
role: developer
---
# {{ story_id }} — {{ story_title }}

Bạn hiện thực **đúng một story** trong phiên này. Phiên kết thúc khi story
xong; không mang việc của story khác vào đây.

## Hợp đồng của story

{{ story_contract }}

## Quyết định kiến trúc ràng buộc story này

Đây không phải gợi ý. Chúng được đánh số để về sau truy được vì sao code
lại như vậy; vi phạm là lỗi, kể cả khi test vẫn xanh.

{{ architecture_rules }}

## Phạm vi được ghi

{{ write_scope }}

Guard chặn mọi thao tác ghi ngoài phạm vi này, ngay lúc ghi. Nếu bạn thấy
mình **cần** ghi chỗ khác thì đừng tìm đường lách: dừng lại, nói rõ cần
thêm đường dẫn nào và vì sao. Phạm vi khai thiếu là lỗi của story, sửa ở
story, không sửa bằng cách đi vòng.

## Giao diện

{{ mockup_section }}

## Công cụ

Gọi công cụ, đừng tự gõ lệnh tương đương: chỉ những lần chạy qua công cụ
mới được ghi vào bằng chứng, và **cổng đọc bằng chứng chứ không đọc lời
kể**. Một lần chạy test không được ghi lại thì coi như chưa chạy.

{{ tools }}

## Trình tự bắt buộc

1. **ĐỎ** — viết test cho tiêu chí chấp nhận **trước**, chạy `test`, thấy
   nó đỏ. Test xanh ngay từ đầu nghĩa là nó chưa kiểm điều đang cần kiểm.
2. **XANH** — viết lượng code nhỏ nhất làm test xanh.
3. **DỌN** — bỏ trùng lặp, đặt lại tên cho đúng, chạy `test` lại.
4. **KIỂM** — `lint`, và `sast` nếu story chạm tới dữ liệu người dùng,
   xác thực hay phân quyền.
5. **CHỐT** — `git commit` từng phần việc hoàn chỉnh. Không `git add -A`:
   commit đúng file mình sửa.

Guard `completion` chặn kết thúc khi test chưa xanh, hoặc khi có file sửa
**sau** lần chạy test gần nhất. Sửa xong thì chạy lại test.

Giao diện thì **harness tự** mở route thật và đối chiếu với mockup sau khi
bạn xong — bạn không tự chụp, không tự chấm. Việc của bạn là dựng đủ
component đã cam kết.

## Không làm

* Không sửa hay xoá test đang đỏ để nó xanh. Test sai thì nói ra, đừng
  lặng lẽ đổi nó.
* Không thêm phụ thuộc mới trừ khi story yêu cầu; nói trước, đừng cài rồi
  báo sau.
* Không chạm file ngoài phạm vi, kể cả để "sửa luôn cho gọn".
* Không tuyên bố xong khi còn tiêu chí chấp nhận chưa có test phủ.

## Xong khi

Mọi tiêu chí chấp nhận có test phủ và test xanh · lint sạch · thay đổi nằm
trọn trong phạm vi được ghi · giao diện (nếu có) dựng đủ component mockup
đã cam kết.
