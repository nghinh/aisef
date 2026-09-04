---
name: mockup-screen
version: 2
role: designer
---
Use the aisdlc-mockup-html skill.

Dựng mockup cho **một** màn hình.

screen_id: {{ screen_id }}
Tên màn hình: {{ screen_name }}
Mục đích: {{ purpose }}
Vào từ: {{ reached_from }}
Route: {{ route }}

Component phải có (theo EXPERIENCE.md) và luật hành vi:
{{ components }}

Trạng thái phải dựng: {{ states }}

Đọc: {{ artifact_root }}/DESIGN.md (token thị giác), {{ artifact_root }}/EXPERIENCE.md
(mục Information Architecture, Component Patterns, State Patterns),
{{ artifact_root }}/prd.md (nội dung thật để điền).

Ghi ra đúng một file: {{ output }}

Chỗ nào chưa chốt thì đánh dấu `data-unresolved` chứ đừng tự chọn.
