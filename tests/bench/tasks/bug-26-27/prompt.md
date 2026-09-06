# Lỗi kho AI-SDLC — #26-27

Triệu chứng đo trên agent thật (không phải suy từ mã):

- 26: Sổ hành vi coi bằng chứng không mang candidate là landed; với story đã đóng băng thì đó là lần `aisdlc tool test` agent tự chạy giữa phiên — xanh ở đó làm 3 hành vi của story trượt, chưa merge thành VERIFIED. 27: `verified_touched` bỏ hành vi REOPENED → lượt 2 của chính story gây hồi quy không còn thấy hành vi nó vừa làm hỏng trong slot lẫn mục "bảo toàn" (mục ấy ✅ trong khi test story trước còn đỏ).

Kiểm: `python3 -m unittest -v tests.test_ledger tests.test_story_size` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisdlc/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisdlc tool test` để lần chạy vào bằng chứng.
