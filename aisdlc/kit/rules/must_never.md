# Tuyệt đối không

Danh sách này khác phần nguyên tắc ở chỗ: nguyên tắc cần phán đoán, còn những
điều dưới đây **không có ngoại lệ** và phần lớn được cưỡng chế bằng hook, chứ
không trông vào việc agent nhớ.

## Với mã nguồn

1. **Không ghi ra ngoài `write_scope` của story.** Cần chạm chỗ khác thì dừng
   và báo — nhiều khả năng story bị chẻ sai, hoặc phạm vi khai thiếu.
2. **Không `git add -A`, không `git add .`.** Chỉ stage đúng đường dẫn story
   đó chạm. Lệnh gộp nuốt cả file rác lẫn thay đổi của story khác.
3. **Không đưa bí mật vào mã nguồn, log, hay trace.** Khoá, mật khẩu, token
   đọc từ biến môi trường hoặc kho bí mật.
4. **Không nối chuỗi vào câu truy vấn.** Tham số hoá, không ngoại lệ.
5. **Không sửa test cho nó xanh**, trừ khi nhiệm vụ chính là cập nhật kỳ vọng
   của test. Test đỏ là thông tin, không phải chướng ngại.
6. **Không để lại mã tham chiếu quy trình trong nguồn** — không ghi số hiệu
   story, epic, hay ghi chú kế hoạch vào comment. Comment giải thích *vì sao*,
   không phải *việc này thuộc phiếu nào*.

## Với kho mã

7. **Không chạy lệnh phá huỷ khi chưa hỏi**: `git reset --hard`,
   `git checkout -- .`, `rm -rf` trong kho, `git push --force`.
8. **Không tự gỡ xung đột merge cuối đợt.** Xung đột nghĩa là hai story chạm
   cùng vùng, tức phạm vi khai sai — việc cần sửa nằm ở khâu chẻ story, không
   phải ở lần merge này.

## Với quy trình

9. **Người viết code không tự duyệt code của mình.** Reviewer phải là phiên
   khác, ngữ cảnh sạch.
10. **Không bỏ qua cổng.** Không tuyên bố story xong khi chưa đủ bằng chứng;
    không sang pha sau khi cổng trước chưa duyệt.
11. **Không sửa file gốc của nguồn ngoài.** Tuỳ biến BMAD ghi ở
    `_bmad/custom/`, không sửa `customize.toml` trong kho gốc — bản nâng cấp
    sau sẽ đè mất.
12. **Không bịa số liệu, tên API, hay hành vi thư viện.** Không chắc thì tra;
    tra không ra thì ghi vào phần giả định.
