# Thư viện tiện ích chuỗi

Ba hàm thuần, không phụ thuộc nhau, dùng chung không gì cả.

- FR-1: `slugify(s)` — đưa chuỗi về dạng slug ASCII, chữ thường, nối bằng `-`.
- FR-2: `truncate(s, n)` — cắt chuỗi còn tối đa n ký tự, thêm `…` khi bị cắt.
- FR-3: `wordCount(s)` — đếm số từ, coi mọi khoảng trắng liên tiếp là một.
