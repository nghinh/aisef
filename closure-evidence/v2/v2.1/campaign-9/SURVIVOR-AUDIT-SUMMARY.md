# Campaign 9 — tổng hợp kiểm toán survivor (534 survivor) và giới hạn đã-biết

Snapshot `4ec961e` (cây mã = `69b0ea9`). 534 survivor của campaign 9 (15.173 mutant, 14.639 KILLED). Kiểm toán vị trí
(`docs/v2.1/MUTATION-RUNNER-V2.md` §16) qua ba đợt; bằng chứng từng mục ở `survivor-audits/wave1/` và `wave2/`
(dự thảo tác giả + phản biện mù, mỗi agent chạy kill file thật trên mutant trong cây `git archive` riêng).

## Kết quả cuối (cả 534)

| Lớp | Số | Nghĩa |
|---|---:|---|
| **AUDITED** | 344 | quan sát được nhưng không consumer/contract/tài liệu/người-vận-hành nào nêu tên phụ thuộc |
| **EQUIVALENT** | 57 | không khác biệt quan sát được, chứng minh từ mã |
| **NỢ TEST (gap thật)** | **85** | hành vi quan sát được mà bộ test **không pin** — phản biện mù từ chối gọi là tương đương |
| carried (audit cũ remap, chưa tái thẩm lượt này) | 48 | mang phán quyết AUDITED/EQUIVALENT của các campaign trước, remap theo vị trí |
| | **534** | |

Theo đợt: đợt 1 (9 target nặng) 54/19/14; đợt 2a (bundle_cli+lineage) 193/23/57; đợt 2b (phần còn lại) 97/15/14.
Phương pháp: đợt 1 hai bản mù; đợt 2 một bản mù (ngân sách) — đợt 1 cho thấy hai bản gần như luôn đồng thuận.

## 85 nợ test — ở đâu, là gì

Gần như toàn bộ nằm ở **mã mới/viết lại trong cửa sổ sửa** và là **trường của bản báo cáo gửi người vận hành** mà
test chỉ kiểm theo giá trị trên đường đã-khai, không kiểm bộ-khoá/cấu trúc của hit fail-closed hay của báo cáo:

- `bundle_cli` 41 (`_assess` 15, `_authentic` 7, `_ground` 5, `_declared` 4+1, `with_commands` 4, `_group` 3,
  `_record` 2, `_known` 1) — đường `migrate`/`seal`/assess của ngữ nghĩa approval PM-9 (đợt 1 thêm `seal` 4).
- `lineage` 16 (`usage_lineage` 7, `_without_a_journal` 4, `child_evidence`/`_journal_mismatch`/`claim_unread`/
  `unread_runs`/`not_there` mỗi 1) — kế toán dòng dõi/usage đợt hai.
- `continue_from` 9 + `execute` 1 (đợt 1, trường `superseded`/`--parent` của báo cáo).
- rải rác (đợt 2b) 14: `diagnostics` 5, `cli_invocation` 3, `adapters`/`client`/`file_artifact`/`review_ocr`/
  `review_verify`/`run` mỗi 1 — trong đó `diagnostics.Sink.__init__ [8]` là **rò bí mật**: bỏ một phần tử của bộ
  dạng redaction khiến bí mật chứa ký tự bị JSON-escape (quote/backslash/non-ASCII) lọt nguyên văn vào artifact
  (reproducer trong `wave2/W2-diagnostics-1-*.json`) — đáng ưu tiên khi viết test/sửa.

## Giới hạn đã-biết (quyết định chủ dự án 2026-10-19: ghi giới hạn rồi ghim)

Bản ghi mutation 2.1 **không PASS sạch**: 85 survivor là gap chưa pin (cộng 48 carried mang audit cũ chưa tái thẩm
lượt này). Chủ dự án chọn **ghi giới hạn và ghim snapshot**; viết kill file cho 85 gap (ưu tiên `diagnostics` rò bí
mật) **vào backlog**, không chặn việc ghim. Ứng viên **không** tuyên bố mutation PASS; nó khai trung thực
"còn 85 survivor chưa pin ở mã mới của cửa sổ, + 48 carried chưa tái thẩm". Đây **không** phải hạ assertion hay thêm
test lấy lệ — là đo thật và báo thật một điểm yếu thật của mã mới 2.1.

Ghi 2026-10-19 ~21:55 +07.
