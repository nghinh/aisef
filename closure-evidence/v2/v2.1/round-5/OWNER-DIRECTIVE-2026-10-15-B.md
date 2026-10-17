# Chỉ thị của chủ dự án, 2026-10-15 (lần thứ tư trong ngày) — nguyên văn

Nhận trong chat ngày 2026-10-15 (giờ Asia/Saigon), sau khi các làn tài liệu và đăng ký đợt 1 của cửa sổ sửa lỗi được gộp.
Công cụ không ghi giờ chính xác của tin nhắn. Văn bản dưới đây là nguyên văn; đây là chỉ thị của chủ dự án, không phải
của người điều phối. Không có ghi nhận nghiệm thu nào được tạo từ nó.

---

Tiếp tục hoàn tất bản ứng viên 2.1. Các quyết định dưới đây nhằm đóng những vấn đề đã phát hiện trước khi ghim snapshot, không mở thêm một vòng nghiên cứu tổng quát.
1. D-PM9-APPROVALS: không giữ approval cho ngữ nghĩa đã thay đổi
Tôi duyệt sửa bundle migrate trong cửa sổ này: không được giữ approval chỉ vì contract_hash không đổi nếu capability mới làm thay đổi ý nghĩa đánh giá của contract.
Với bốn contract LedgerLock đã xác định có verdict có thể đổi:

* Tạo bundle ứng viên mới, giữ nguyên bundle và approval cũ làm lịch sử.
* Đánh dấu cần chủ sở hữu duyệt lại; không tự ký hoặc chuyển approval.
* Cung cấp diff ngữ nghĩa, tình huống làm verdict khác và định danh bundle mới để tôi duyệt cụ thể.

Kiểm tra cơ chế migration có nhận diện được sự thay đổi capability semantics nói chung hay không; không hard-code riêng bốn contract. Những approval không bị ảnh hưởng chỉ được giữ khi có căn cứ theo hợp đồng định danh đã duyệt.
Đây là lỗi tính đúng, cần xử lý trước khi chốt snapshot. Việc thêm .gitignore C-1 vẫn ở backlog.
2. Lineage: giữ bản sửa unknown ≠ 0
Tôi xác nhận giữ bản sửa: journal không đọc được thì chi phí phải là chưa xác định, không được thành 0 hoặc số đã đối soát.
Giữ phân biệt giữa chi phí đã biết của một phần lineage và tổng chi phí chưa xác định. Không thay đổi lịch sử, không tự giải phóng claim, không cho mở phiên trả tiền mới bằng cách bỏ qua phần chưa đối soát.
3. RV-2: sửa cả trạng thái máy đọc
Tôi duyệt phân biệt INDETERMINATE với NOT_REPRODUCED ở kết quả máy đọc, không chỉ ở câu thông báo.
Rà các bên đọc, schema và bằng chứng cũ. Nếu thay đổi từ vựng cần version/migration thì thực hiện theo quy tắc tương thích hiện hành; không âm thầm diễn giải lại bản ghi lịch sử.
Một lần kiểm tra không thực hiện được hoặc không đủ kết luận không được trở thành bằng chứng rằng finding không tái hiện.
4. ReDoS trong reproducer: xử lý trong cửa sổ này
Regex do model reviewer cung cấp cũng phải có giới hạn thực thi. Tôi duyệt áp dụng cơ chế deadline và quản lý tiến trình phù hợp cho đường này, tái sử dụng phần đã có nếu cùng hợp đồng.
Timeout, lỗi thực thi hoặc vượt giới hạn phải cho kết quả không xác định/không thực hiện được theo taxonomy hiện hành; không được biến thành NOT_REPRODUCED hoặc REFUTED về sản phẩm.
Kiểm chứng regex gây treo, kết quả bình thường và việc dọn tiến trình thuộc lượt kiểm tra. Không tạo thêm framework tổng quát nếu cơ chế hiện có đáp ứng được.
Với within_s và dữ liệu lồng sâu:

* Phân biệt giới hạn thực thi của công cụ với điều kiện thời gian mà contract yêu cầu sản phẩm đáp ứng.
* Lỗi/giới hạn của công cụ không phải verdict về sản phẩm.
* Áp dụng định nghĩa biên đã công bố; nếu chưa có hoặc mâu thuẫn, đưa đúng biểu thức và hai hành vi khác nhau để tôi quyết. Không tự chọn theo test nào dễ xanh.

5. OCR: cho phép tải nguồn để xác minh build
Tôi cho phép tải mã nguồn công khai của open-code-review tại đúng commit đã ghim và các dependency cần để build, trong thư mục làm việc riêng. Không thay bản cài hệ thống, không chạy script cài đặt toàn cục và không sử dụng thông tin đăng nhập không cần thiết.
Ghi commit đầy đủ, toolchain, dependency và lệnh build. Phân biệt:

* Binary tự khai phiên bản.
* Binary khớp hash đã ghim.
* Binary có nguồn gốc build được xác minh.

Nếu build không tái tạo byte-identical, báo khác biệt và mức bằng chứng đạt được; không tự tuyên bố nguồn gốc đã xác minh đầy đủ.
Với review bắt buộc, kiểm tra định danh OCR ngay ở preflight trước khi mở phiên developer để tránh làm việc rồi mới phát hiện công cụ không dùng được. Vẫn bảo đảm binary thực sự được chạy đáp ứng pin; kiểm tra sớm không thay thế kiểm soát tại thời điểm sử dụng.
Không gọi provider trả tiền mới.
6. Linux và tài nguyên: chủ động xử lý phần kỹ thuật
Sửa recorder đếm đôi tiến trình con trên Linux theo định danh tiến trình thực tế, có test tái hiện; không sửa số đếm để khớp kỳ vọng.
Chạy các test mockup nếu chúng thuộc suite hỗ trợ, thực hiện được offline và không ảnh hưởng dịch vụ thật. Nếu không, ghi rõ lý do skip theo từng nhóm. Không cần hỏi tôi các lựa chọn kỹ thuật này.
Rà tiến trình “giữ ≥8 GiB”: chỉ được dọn tài nguyên tạm của chiến dịch đã chứng minh quyền sở hữu và không còn sử dụng. Không tự xoá bằng chứng, worktree đang hoạt động hoặc dữ liệu người dùng. Khi thiếu dung lượng, ngừng cấp việc mới và giữ checkpoint.
Giảm số tác vụ đồng thời theo RAM, đĩa và tải thực tế. Không mở thêm agent phân tích tổng quát; hoàn tất và tích hợp các làn hiện có.
7. Chốt phạm vi, rồi kiểm chứng một lượt có kiểm soát
Trước khi ghim snapshot, xuất một bảng duy nhất:

* Thay đổi đã gộp.
* Lỗi còn chặn snapshot.
* Spec/approval cần duyệt lại.
* Target và bằng chứng bị ảnh hưởng.
* Phần chủ động để bản sau.

Trong đó phải giữ nổi bật lỗi lệnh chi phí/báo cáo V1 trả toàn 0 với exit 0 và hai vấn đề CRLF Windows. Chúng chưa được sửa thì không được ghi hành trình người dùng hoặc hỗ trợ Windows đã đạt.
Sau khi đóng các mục trên và các làn hiện tại:

1. Chạy test_meta, lint và hồi quy liên quan.
2. Chốt snapshot, hiệu chuẩn, delta và manifest.
3. Đo lại đúng phạm vi bị ảnh hưởng.
4. Sinh bản ghi phụ thuộc.
5. Chạy suite macOS/Linux, E2E cách ly và OCR thật offline trên bản ứng viên.

Không ghim snapshot khi còn một thay đổi đã duyệt chắc chắn sẽ làm mất hiệu lực phép đo. Sau khi ghim, chỉ mở lại vì lỗi chặn có bằng chứng; cải tiến khác đưa backlog.
Báo tiến độ bằng kết quả đã hoàn thành và bước đang chặn, kèm thời điểm đo. Tách thời gian máy chạy khỏi thời gian sửa lỗi; không lặp lại dự báo cũ khi phạm vi đã đổi.
Giữ Docker và goe-* hoạt động. Chưa push, tag, publish, deploy, phát hành hoặc gọi provider trả tiền mới. Không tự ghi nhận owner acceptance.
