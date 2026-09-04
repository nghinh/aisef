---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: [prd.md, architecture.md, EXPERIENCE.md]
---

# Ghi chú cục bộ - Epic Breakdown

## Overview

Phân rã PRD thành epic và story thực thi được.

## Requirements Inventory

### Functional Requirements

FR-1..FR-17 — xem prd.md.

### FR Coverage Map

| Yêu cầu | Story phủ |
|---|---|
| FR-1 | 1.1 |
| FR-2 | 1.2 |
| FR-3 | 1.3 |
| FR-4 | 1.4 |
| FR-5 | 2.1 |
| FR-6 | 2.1 |
| FR-7 | 2.2 |
| FR-8 | 3.1 |
| FR-9 | 3.2 |
| FR-10 | 3.3 |
| FR-11 | 4.1 |
| FR-12 | 4.2 |
| FR-16 | 4.3 |
| FR-17 | 4.3 |

FR-13..FR-15 chưa đưa vào story: OQ-1 chưa có lời giải.

## Epic List

1. Epic 1: Vòng đời ghi chú
2. Epic 2: Tìm kiếm
3. Epic 3: Thẻ
4. Epic 4: Ngoại tuyến và dữ liệu

## Epic 1: Vòng đời ghi chú

Người dùng tạo, sửa, xoá và duyệt ghi chú trên một thiết bị.

### Story 1.1: Tạo ghi chú bằng một thao tác

As a người dùng,
I want tạo một ghi chú mới bằng một thao tác,
So that tôi ghi lại được ý nghĩ trước khi quên.

**Acceptance Criteria:**

**Given** màn hình chính đang mở
**When** tôi bấm nút thêm
**Then** con trỏ nằm trong ô soạn thảo trống
**And** ghi chú tồn tại trong Kho cục bộ ngay khi ký tự đầu tiên được nhập

**Given** trình duyệt hoàn toàn không có mạng
**When** tôi tạo ghi chú
**Then** thao tác vẫn thành công

**Story metadata:**
- covers: FR-1
- write_scope: src/notes/, src/db/
- depends_on: none
- screens: danh-sach, soan-thao

### Story 1.2: Lưu tự động khi soạn

As a người dùng,
I want nội dung được lưu mà không phải bấm lưu,
So that tôi không mất chữ đã gõ.

**Acceptance Criteria:**

**Given** tôi đang gõ trong một ghi chú
**When** tôi ngừng gõ 1 giây
**Then** nội dung đã có trong Kho cục bộ
**And** thời điểm sửa gần nhất được cập nhật

**Story metadata:**
- covers: FR-2
- write_scope: src/notes/
- depends_on: 1.1

### Story 1.3: Xoá qua thùng rác

As a người dùng,
I want ghi chú đã xoá vào thùng rác,
So that xoá nhầm còn khôi phục được.

**Acceptance Criteria:**

**Given** một ghi chú trong danh sách
**When** tôi xoá nó
**Then** nó biến khỏi danh sách chính và nằm trong thùng rác

**Story metadata:**
- covers: FR-3
- write_scope: src/notes/, src/trash/
- depends_on: 1.1

### Story 1.4: Duyệt danh sách ghi chú

As a người dùng,
I want thấy danh sách ghi chú,
So that tôi mở lại được thứ đã viết.

**Acceptance Criteria:**

**Given** có ghi chú trong Kho cục bộ
**When** tôi mở màn hình chính
**Then** danh sách hiện theo thời điểm sửa gần nhất

**Story metadata:**
- covers: FR-4
- write_scope: src/list/
- depends_on: 1.1
- screens: danh-sach

## Epic 2: Tìm kiếm

Tìm được ghi chú trong đống ghi chú.

### Story 2.1: Truy vấn toàn văn không phân biệt dấu

As a người dùng,
I want gõ từ khoá và thấy ghi chú chứa nó,
So that tôi không phải cuộn tay.

**Acceptance Criteria:**

**Given** kho có 1000 ghi chú
**When** tôi gõ một từ khoá
**Then** kết quả trả về dưới 200ms
**And** "ca" khớp cả "cà" lẫn "Cá"

**Story metadata:**
- covers: FR-5, FR-6
- write_scope: src/search/
- depends_on: 1.4
- screens: tim-kiem

### Story 2.2: Trình bày kết quả tìm kiếm

As a người dùng,
I want thấy đoạn khớp trong kết quả,
So that tôi chọn đúng ghi chú cần mở.

**Acceptance Criteria:**

**Given** một truy vấn có kết quả
**When** danh sách kết quả hiện ra
**Then** mỗi dòng hiện đoạn văn bản chứa từ khoá được tô đậm

**Story metadata:**
- covers: FR-7
- write_scope: src/search/, src/list/
- depends_on: 2.1

## Epic 3: Thẻ

Phân loại ghi chú bằng thẻ.

### Story 3.1: Gắn và gỡ thẻ

As a người dùng,
I want gắn thẻ cho ghi chú,
So that tôi nhóm được theo chủ đề.

**Acceptance Criteria:**

**Given** một ghi chú đang mở
**When** tôi gắn một thẻ
**Then** thẻ hiện trên ghi chú và tồn tại sau khi tải lại

**Story metadata:**
- covers: FR-8
- write_scope: src/tags/
- depends_on: 1.1

### Story 3.2: Lọc theo thẻ

As a người dùng,
I want lọc danh sách theo thẻ,
So that tôi thấy đúng nhóm cần xem.

**Acceptance Criteria:**

**Given** có ghi chú mang thẻ "việc"
**When** tôi chọn thẻ đó
**Then** danh sách chỉ còn ghi chú mang thẻ ấy

**Story metadata:**
- covers: FR-9
- write_scope: src/tags/, src/list/
- depends_on: 3.1

### Story 3.3: Quản lý thẻ

As a người dùng,
I want đổi tên và xoá thẻ,
So that danh sách thẻ không loạn.

**Acceptance Criteria:**

**Given** một thẻ đang dùng ở nhiều ghi chú
**When** tôi đổi tên thẻ
**Then** mọi ghi chú mang thẻ đó cập nhật theo

**Story metadata:**
- covers: FR-10
- write_scope: src/tags/
- depends_on: 3.1

## Epic 4: Ngoại tuyến và dữ liệu

Ứng dụng dùng được khi mất mạng, và dữ liệu lấy ra được.

### Story 4.1: Chạy đầy đủ khi không có mạng

As a người dùng,
I want dùng ứng dụng khi mất mạng,
So that ghi chú không phụ thuộc kết nối.

**Acceptance Criteria:**

**Given** trình duyệt ở chế độ ngoại tuyến
**When** tôi mở ứng dụng
**Then** mọi chức năng tạo, sửa, xoá, tìm đều dùng được

**Story metadata:**
- covers: FR-11
- write_scope: src/pwa/, public/
- depends_on: 1.1

### Story 4.2: Chỉ báo trạng thái mạng

As a người dùng,
I want biết mình đang ngoại tuyến,
So that tôi không hiểu nhầm là dữ liệu đã đồng bộ.

**Acceptance Criteria:**

**Given** mất kết nối
**When** tôi nhìn thanh trạng thái
**Then** chỉ báo ngoại tuyến hiện rõ

**Story metadata:**
- covers: FR-12
- write_scope: src/status/
- depends_on: 4.1

### Story 4.3: Xuất dữ liệu và cảnh báo rủi ro lưu trữ

As a người dùng,
I want xuất toàn bộ ghi chú và được cảnh báo khi sắp hết chỗ,
So that tôi không mất dữ liệu.

**Acceptance Criteria:**

**Given** kho có ghi chú
**When** tôi bấm xuất dữ liệu
**Then** tôi nhận một tệp chứa toàn bộ ghi chú và thẻ

**Given** dung lượng còn lại dưới ngưỡng
**When** tôi mở ứng dụng
**Then** cảnh báo rủi ro lưu trữ hiện ra

**Story metadata:**
- covers: FR-16, FR-17
- write_scope: src/export/, src/status/
- depends_on: 1.1
