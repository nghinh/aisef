"""Bản ghi và truy vấn cho phép đo xếp hạng.

Lấy từ **chất liệu thật của kho này** — lỗi, quyết định và bài học đã ghi trong
`docs/FAILURE-TAXONOMY.md` và các ADR — chứ không phải câu bịa, để phân bố từ
ngữ giống thứ bộ nhớ thật sẽ chứa.

Mỗi truy vấn có đúng một bản ghi trả lời. Các bản ghi còn lại là **mồi nhiễu**
cùng chủ đề: chúng chia sẻ từ phổ biến ("test", "story", "guard", "chạy") nhưng
không mang từ hiếm quyết định. Đây là tình huống mà đếm từ trùng thua: nó không
phân biệt trùng một từ hiếm với trùng ba từ ai cũng có.
"""

from __future__ import annotations

RECORDS: list[str] = [
    # 0
    "Guard completion không chặn khi lệnh test chưa cấu hình: chặn ở đó chỉ đốt lượt "
    "vì agent không sửa được lệnh test của dự án.",
    # 1
    "Trên Windows cờ O_CLOEXEC không tồn tại; lock file phải mở qua _compat.open_lock_fd "
    "để chọn O_NOINHERIT.",
    # 2
    "os.replace trên Windows bị từ chối khi còn handle mở tệp đích; hoàn nguyên phải đi "
    "qua git checkout để git áp lại bộ lọc autocrlf.",
    # 3
    "Reviewer không được từ chối chính đơn thuốc mình kê: luật chống đổi cột mốc nay phủ "
    "cả ca ấy và trả kết cục stuck.",
    # 4
    "Một lượt agent ghi 0 dòng vẫn bị tính là ứng viên và chạy đủ cổng, tốn thêm hai phiên "
    "review và security cho một nguyên nhân.",
    # 5
    "Playwright chạy 99 test bị đọc thành 0 vì cấu hình có projects nên mỗi dòng mang tiền "
    "tố chromium.",
    # 6
    "Chi phí mỗi story trên e9 khoảng 70 đô la, trong khi par chỉ 1,9 — chưa ai phân rã "
    "khoảng cách ba mươi sáu lần ấy.",
    # 7
    "Bản ghi nhiễu: chạy test cho story này rồi chạy lại test sau khi sửa, test vẫn chạy "
    "và story vẫn chạy.",
    # 8
    "Bản ghi nhiễu: guard chạy trước mỗi tool, guard ghi log, guard chạy lại khi story "
    "chạy lại, log guard ghi vào evidence.",
    # 9
    "Bản ghi nhiễu: story chạy test, test chạy trong worktree, worktree của story, story "
    "ghi evidence, evidence của story.",
    # 10
    "Ngân sách đặt chỗ trước khi gọi model và hoàn lại khi lỗi; khoá sổ qua sidecar để "
    "sống sót os.replace đổi inode.",
    # 11
    "Bản ghi nhiễu: chi phí chạy story, chi phí chạy test, chi phí mỗi lượt, chi phí "
    "review, chi phí security, chi phí chạy lại.",
    # 12
    "Alias mycombo đổi mô hình nền giữa các lần gọi nên hai cột đo trông giống hệt nhau "
    "nếu không khai nhãn cohort.",
    # 13
    "Bản ghi nhiễu: model chạy nhanh, model chạy chậm, model chạy lại, chạy model cho "
    "story, story gọi model, model ghi tệp.",
]

QUERIES: list[dict] = [
    {"query": "lock file trên windows dùng cờ nào", "answer": 1},
    {"query": "hoàn nguyên tệp mà git vẫn báo đã sửa", "answer": 2},
    {"query": "reviewer chặn đúng thứ nó vừa yêu cầu sửa", "answer": 3},
    {"query": "phiên agent không ghi gì mà vẫn tốn tiền chạy cổng", "answer": 4},
    {"query": "đọc tên test từ playwright nhiều trình duyệt", "answer": 5},
    {"query": "vì sao chi phí mỗi story chênh lệch lớn giữa hai dự án", "answer": 6},
    {"query": "giữ khoá sổ ngân sách khi tệp bị thay thế", "answer": 10},
    {"query": "vì sao hai đợt đo cùng alias không phân biệt được", "answer": 12},
    {"query": "chặn hoàn tất khi dự án chưa khai lệnh test", "answer": 0},
]

#: Họ thứ hai, dựng để **chống lại** kết luận của họ thứ nhất.
#:
#: Ở họ trên, mồi nhiễu nhồi từ khoá — tình huống mà đếm-từ-riêng-biệt thắng vì
#: nó không thưởng tần suất. Một bộ đo chỉ có tình huống ấy là bộ đo thiên vị.
#: Họ này dựng tình huống ngược: mồi nhiễu **dài và đa dạng**, chia sẻ nhiều từ
#: phổ biến với truy vấn nhưng mỗi từ chỉ một lần, còn bản ghi đúng chỉ chia sẻ
#: **một từ hiếm**. Đếm từ trùng phải thua ở đây; nếu không thì giả thuyết về
#: IDF sai.
RECORDS_RARE: list[str] = [
    # 0 — đúng: chỉ chia sẻ đúng một từ hiếm "flock"
    "Hai tiến trình cùng giữ flock vì os.replace đổi inode dưới chân fd đang khoá.",
    # 1 — nhiễu dài, chia sẻ nhiều từ phổ biến
    "Khi một tiến trình chạy và một tiến trình khác cũng chạy trên cùng một dự án, "
    "trạng thái ghi vào tệp có thể bị hai bên cùng sửa nếu không có gì điều phối.",
    # 2 — nhiễu dài khác
    "Một tiến trình ghi tệp trạng thái trong khi tiến trình khác đọc tệp ấy, và cả hai "
    "cùng chạy trên cùng một dự án nên kết quả phụ thuộc thứ tự.",
    # 3 — đúng: từ hiếm "autocrlf"
    "Cây làm việc lấy ra theo autocrlf nên ghi thẳng blob làm tệp khác chính nó.",
    # 4 — nhiễu
    "Tệp trong cây làm việc được ghi rồi đọc lại, và nội dung tệp ấy khác với nội dung "
    "đã ghi nếu có một lớp chuyển đổi ở giữa.",
    # 5 — đúng: từ hiếm "abstain"
    "Router trả abstain khi hai tín hiệu không cùng chỉ về một kỹ năng.",
    # 6 — nhiễu
    "Khi hệ thống không chắc chắn thì nó có thể chọn một trong nhiều khả năng, hoặc "
    "không chọn gì cả và để người dùng quyết định điều đó.",
]

QUERIES_RARE: list[dict] = [
    {"query": "hai tiến trình cùng giữ khoá trên một tệp trạng thái", "answer": 0},
    {"query": "tệp trong cây làm việc khác chính nó sau khi ghi", "answer": 3},
    {"query": "khi không chắc chắn thì hệ thống chọn gì", "answer": 5},
]
