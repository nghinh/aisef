"""Kiểm tra các kho tham chiếu đã ghim còn đứng yên hay đã chạy tiếp.

`references/PINS.md` ghim commit của 13 kho ngoài. Khi thượng nguồn chạy tiếp,
kết luận rút ra từ bản đã đọc **không tự sai**, nhưng nó hết là kết luận về
`main` — và lớp quét skill ngoài phải chạy lại trên phần mới. Việc của mô-đun
này chỉ là **phát hiện**: hỏi GitHub HEAD hiện tại, so với bảng, in ra cái nào
đã chạy. Quyết định quét lại (tốn tiền, cần khoá) là của người.
"""
