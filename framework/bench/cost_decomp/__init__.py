"""Phân rã chi phí một dự án thật theo vai và theo lượt bị chặn.

Câu hỏi E4 của kế hoạch: "70 $/story tiêu vào đâu". Nhà cung cấp sau alias
`9router/…` **không trả về chi phí** (`cost_usd = 0` ở toàn bộ 2 214 sự kiện của
`todo-e2e`), nên ở đây đếm **token**, không bịa ra đô la. Ai có bảng giá thì
nhân vào — công thức in kèm bảng.

    python3 -m framework.bench.cost_decomp ~/Downloads/projects/todo-e2e
"""
