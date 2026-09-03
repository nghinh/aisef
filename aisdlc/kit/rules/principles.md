# Nguyên tắc kỹ thuật

Bốn nguyên tắc đầu diễn đạt lại quan sát của Andrej Karpathy về cách làm việc
với agent lập trình (nguồn: `multica-ai/andrej-karpathy-skills`). Viết lại bằng
ngôn ngữ của framework này vì kho gốc không kèm giấy phép — tham chiếu được,
đóng gói lại thì không.

## 1. Hiểu trước khi viết

Đọc yêu cầu, lần theo luồng thực tế, xác định đúng chỗ phải sửa — rồi mới gõ
dòng đầu tiên. Phần lớn lỗi không đến từ việc viết code kém, mà từ việc viết
đúng một giải pháp cho sai vấn đề.

Khi yêu cầu có nhiều cách hiểu: nêu ra, đừng chọn thầm. Khi có cách đơn giản
hơn: nói. Không có người trong vòng lặp thì ghi giả định vào artifact và đi
tiếp, không dừng chờ.

## 2. Đơn giản trước

Viết đúng lượng code giải quyết vấn đề hôm nay. Không lớp trừu tượng cho một
chỗ dùng, không tham số hoá cho một giá trị chưa từng đổi, không khung sườn
cho việc chưa ai yêu cầu.

Thư viện chuẩn trước thư viện ngoài. Tính năng sẵn có của nền tảng trước code
tự viết. Một dòng hơn năm dòng — nhưng chỉ khi một dòng đó vẫn đúng ở các
trường hợp biên.

## 3. Sửa đúng chỗ phải sửa

Chạm đúng thứ nhiệm vụ đòi hỏi. Không "tiện tay" chỉnh format, đổi tên, hay
dọn code lân cận trong cùng một thay đổi — việc đó làm diff phình ra và che
mất thứ thực sự thay đổi.

Sửa lỗi thì tìm nguyên nhân gốc, không vá triệu chứng ở một nhánh gọi. Một
lần sửa ở chỗ mọi nhánh đi qua nhỏ hơn nhiều lần vá ở từng nhánh, và không bỏ
sót nhánh nào.

## 4. Bám mục tiêu, không bám câu chữ

Biết việc này phục vụ điều gì. Khi câu chữ của nhiệm vụ mâu thuẫn với mục
tiêu của nó, nêu mâu thuẫn ra thay vì làm theo câu chữ rồi giao một thứ vô
dụng.

## 5. Bằng chứng, không tự khai

Không tuyên bố "xong", "đã sửa", "test xanh" khi chưa có kết quả chạy thật và
còn tươi. Định nghĩa tiêu chí thành công đo được **trước** khi bắt tay. Viết
test tái hiện lỗi trước khi sửa lỗi.

Nguyên tắc này là nền của mọi cổng chất lượng trong framework: cổng chỉ đọc
kết quả tiến trình bên ngoài chạy, không bao giờ đọc lời agent tự đánh giá.

## 6. Dừng khi mâu thuẫn

Tài liệu đá nhau, mockup lệch kiến trúc, yêu cầu tự phủ định nhau — dừng và
báo. Không tự chọn một bên rồi đi tiếp im lặng.

Thứ tự khi phải phân xử: kiến trúc > đặc tả UX > hợp đồng thị giác từ mockup.

## 7. Thiếu thì khai báo

Không có cơ chế nào đó (sandbox không chạy được, hook không gắn được, reviewer
không độc lập) thì ghi rõ mức bảo đảm thấp hơn vào artifact. Im lặng vờ như
vẫn đủ là kiểu hỏng tệ nhất, vì nó lấy đi cả khả năng biết mình đang thiếu.
