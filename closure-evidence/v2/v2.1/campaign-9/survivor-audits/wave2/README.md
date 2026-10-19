# Campaign 9 — kiểm toán survivor, đợt 2 (các target ngoài 9 target của đợt 1)

534 survivor của campaign 9; đợt 1 đã chốt 91 (9 target nặng). Đợt 2: **443 survivor / 106 target** (314 mới + 129
mang sang theo vị trí). Snapshot `4ec961e`. Phương pháp (khác đợt 1 vì ngân sách token): mỗi batch một **tác giả**
dự thảo các survivor mới + **một người phản biện mù** chạy kill file thật trên từng mutant và ra phán quyết; mục
`TEST_OWED`/bất đồng sẽ được **bản mù thứ hai** xác nhận ở lượt tập trung (đợt 1 cho thấy hai bản gần như luôn đồng
thuận; khác biệt duy nhất là nhãn chính sách report-field). Batch, dự thảo (`*-draft.json`), phản biện (`*-v.json`),
danh sách nợ (`owed-wave2a.json`), survivor gốc (`survivors-all.json`), audit remap (`remapped.json`) ở thư mục này.

## Đợt 2a — hai tệp cửa sổ sửa (bundle_cli 156 + lineage 117 survivor), đã chạy (workflow `wf_df18ef33-a1f`, 36 agent)

| | AUDITED | EQUIVALENT | NỢ TEST |
|---|---:|---:|---:|
| **bundle_cli + lineage** | 193 | 23 | **57** |

**57 nợ test** (lỗ hổng thật — hành vi quan sát được mà bộ test không pin), theo hàm:

- `bundle_cli._assess` 15, `_authentic` 7, `_ground` 5, `_declared` 4, `with_commands` 4, `_group` 3, `_record` 2,
  `_known` 1 = **41** (toàn bộ đường `migrate`/`seal`/assess của cửa sổ PM-9/ngữ nghĩa approval)
- `lineage.usage_lineage` 7, `_without_a_journal` 4, `child_evidence`/`_journal_mismatch`/`claim_unread`/`unread_runs`/
  `not_there` mỗi cái 1 = **16** (đường kế toán dòng dõi/usage của đợt hai)

Phần lớn là các trường của **bản báo cáo gửi người vận hành** (hit fail-closed, hàng `semantic_changes`, dòng
`spend_by_run`/`usage_lineage`) mà test chỉ kiểm theo *giá trị trên đường đã khai*, không kiểm *bộ khoá/cấu trúc* của
hit fail-closed hay của báo cáo. Cùng họ với lỗ hổng `seal`/`continue_from` của đợt 1.

## Ý nghĩa cho nghiệm thu

Mã **mới** của cửa sổ sửa (bundle_cli, lineage — nơi thêm ngữ nghĩa approval và kế toán dòng dõi) **thiếu test đáng
kể**: 57 (đợt 2a) + 14 (đợt 1) = **71 lỗ hổng đã xác nhận**, và đợt 2b (diagnostics, các probe, review_*, run,
adapters… ~160 survivor) chưa chạy. Đây **không** phải "thêm test cho đủ số" — là hành vi quan sát được chưa được
pin. Quyết định của chủ dự án (thay đổi nghĩa "sẵn sàng nghiệm thu"): **(a)** viết kill file cho tất cả nợ test rồi đo
lại trước khi ghim (lớn), hay **(b)** ghi là giới hạn đã-biết với bằng chứng và ghim, viết test ở backlog. Người điều
phối không tự quyết mục này.

Ghi 2026-10-19 ~21:40 +07.
