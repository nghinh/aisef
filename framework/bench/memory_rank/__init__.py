"""A/B xếp hạng truy hồi bộ nhớ — đếm từ trùng so với BM25.

Bộ đo cũ (`aisef.memory_bench`) đã bão hoà: recall 1,0 và 0 lần lấy nhầm, nên nó
**không thể** cho biết một cách chấm điểm có hơn cách kia không. Bộ này đo đúng
thứ cách chấm quyết định: khi ngân sách chỉ đủ chứa vài bản ghi, **bản ghi nào
được chọn**.

Thiết kế: mỗi truy vấn có một bản ghi đúng và nhiều **mồi nhiễu** chia sẻ từ phổ
biến với truy vấn nhưng không mang từ hiếm quyết định. Đếm từ trùng không phân
biệt "trùng một từ hiếm" với "trùng ba từ ai cũng có"; BM25 thì có (IDF) và còn
chuẩn hoá theo độ dài bản ghi.

Chạy: ``python3 -m framework.bench.memory_rank``
"""
