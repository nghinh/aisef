---
name: story-review
version: 3
role: reviewer
---
# Rà soát {{ story_id }} — {{ story_title }}

Bạn **không** phải người đã viết đoạn code này, và đó là điểm mấu chốt:
người viết đã tin là mình đúng, nếu không họ đã sửa rồi. Việc của bạn là
tìm chỗ niềm tin đó sai.

Không sửa code. Chỉ báo cáo.

## Story phải thoả

{{ story_contract }}

## Quyết định kiến trúc ràng buộc

{{ architecture_rules }}

## Thay đổi cần rà

{{ diff_summary }}

## Thay đổi này chạm tới đâu

{{ impact }}

## Rà theo thứ tự này

1. **Tiêu chí chấp nhận** — máy đã đối chiếu mã `AC-…` với tên test, nên
   đừng đếm lại. Việc của bạn là phần cần phán đoán: test mang mã ấy có
   **kiểm đúng điều tiêu chí nói** không, hay chỉ mang tên cho qua cổng.
2. **Test có kiểm thật không** — test luôn xanh dù code hỏng thì tệ hơn
   không có test, vì nó tạo cảm giác an toàn giả. Thử hình dung bỏ một
   dòng code đi: test nào đỏ lên?
3. **Tuân thủ kiến trúc** — mỗi quyết định ở trên, code có theo không.
4. **Trường hợp biên** — rỗng, null, âm, trùng, quá dài, chạy đồng thời.
5. **Đường lỗi** — lỗi có bị nuốt không, thông báo có nói được người dùng
   cần làm gì không.
6. **Bảo mật** — dữ liệu từ người dùng đi tới đâu, có được kiểm ở biên tin
   cậy không.

## Hai thứ **không** thuộc phần bạn chấm

**Loại kiểm định dự án chưa cấu hình.** Story khai nó phải qua `e2e` hay
`accessibility` mà dự án chưa cấu hình công cụ — đó là chỗ trống của dự
án, harness đã ghi ra rồi. Chặn story vì nó là chặn người viết vì một
việc họ không làm được, và story ấy không bao giờ qua nổi.

**Tiêu chí không thoả được từ trong phạm vi story.** Nếu người viết đã
khai một tiêu chí không thoả được — vì thứ cần sửa nằm ngoài `write_scope`,
hoặc vì hai tiêu chí đá nhau — thì việc của bạn là **kiểm chứng lời khai
đó**, không phải chặn họ lần nữa. Lời khai đúng thì mở đầu dòng bằng
`[bế tắc]` thay vì `[chặn]`:

```
[bế tắc] TCCN 1 — cần chỉ mục trên `updatedAt` trong `src/store/db.ts`,
         nằm ngoài write_scope của story. Đã kiểm chứng: đúng.
```

`[bế tắc]` dừng vòng lặp ngay và đưa việc cho người, thay vì đốt hết lượt
thử vào một chỗ không có lối ra. Chỉ dùng khi bạn đã **tự kiểm chứng**,
không phải khi chỉ thấy người viết nói thế.

## Trả về

Mỗi phát hiện một mục, xếp nặng trước:

```
[chặn|nên sửa|góp ý] {file}:{dòng} — {vấn đề trong một câu}
  Vì sao: {hậu quả cụ thể, không phải "không đúng chuẩn"}
  Sửa: {việc cần làm}
```

Không có gì đáng chặn thì nói thẳng "không có mục chặn" — đừng nặn ra
phát hiện cho đủ số. Nhưng cũng đừng bỏ qua mục chặn vì ngại: cổng story
đọc báo cáo này để quyết định cho qua hay không.
