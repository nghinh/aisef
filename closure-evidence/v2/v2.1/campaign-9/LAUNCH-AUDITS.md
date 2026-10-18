# Campaign 9 — ba kiểm toán độc lập lúc khởi chạy (2026-10-18, 08:20–08:55 +07)

Theo chỉ thị 2026-10-18 (mục 1–3). Mỗi kiểm toán do một agent làm việc chỉ-đọc trên kho (`v2.1/probe-window`, HEAD
`ff6309f`→`fbedf1b` trong lúc đo; cây `aisef2/`, `tests/`, `validation/` giống từng byte `69b0ea9` = `4ec961e`), rồi một
agent **mù thứ hai** cố bác bỏ. Không agent nào chạy `opencode`, gọi provider, đụng thư mục campaign hay tiến trình; thời
gian là đồng hồ hệ thống. Bản ghi đầy đủ: journal của workflow `wf_c5b24ebd-796` (ngoài kho). Sáu agent, 0 lỗi.

## 1. Phạm vi đo (chỉ thị mục 2) — `SCOPE_JUSTIFIED`, người bác bỏ **đồng ý** (08:29–08:54)

| kiểm | kết quả |
|---|---|
| `targets-run.txt` = `targets.txt` ∪ `PROMOTED.json`; 0 trùng; 544 ⊂ registry 614; 544 + 70 = 614 | PASS (đếm lại bằng `verify9.py` trong tiến trình mới, `nice 19`, 08:29:10–08:36:39: 614 / 16.080; 511 / 13.859; 103 / 2.221 đứng) |
| 424 REMEASURE: mỗi hàng có lý do thuộc luật delta, **bằng từng byte** với `DELTA.json` của base riêng của nó (527/527 khớp `result_from` của campaign 8); 87 NEW: không có trong `campaign-8/SCOPE.json` lẫn `MUTATION.json` | PASS |
| 33 promoted = đúng tập hàng đứng tạm có mã `aisef2/` đổi trong closure **ngoài** `process_range.py` (= `other_code_changed` của DELTA); căn cứ là mặc định của hợp đồng runner §19/§20 (không có bản ghi reach/trace) — một **luật**, không phải "cho chắc" | PASS |
| 23 chỉ có `process_range.py`: 3 kill file (`test_p6_stages`, `test_v21_orchestration`, `test_release_s2_kernel`) trong `campaign-6/trace.json` (`60a75c8`, complete, 163 file PASS) với `hits {}`; `process_range.py`, module, 3 kill file, `tests/v2/__init__.py` và **cả 107 tệp closure import** có blob giống nhau ở `60a75c8` và `4ec961e`; diff `289885e..4ec961e` của `process_range.py` là đúng một hunk `try/except` trong `_Posix.abort`, được nhãn `range._Posix.abort:gone` đánh | PASS |
| 47 không có mã đổi: `reasons []`, `changed_code []`, `source_sha256`/kill set/số mutant đúng cho **cả 70**; closure dựng lại bằng AST walker riêng ở head **và** ở base, giao với `git diff --name-only <base>..4ec961e -- aisef2 validation aisef`: 0 lệch với `SCOPE.json` | PASS |
| Target trong registry không ở danh sách nào | 0 |
| Người bác bỏ: 8 REMEASURE ngẫu nhiên (căn cứ git độc lập 8/8), 8 promoted (8/8), **cả 70** target đứng (blob module, kill set, closure ∩ mã đổi, trace) | không bác bỏ được |

Kết luận: 544 / 15.173 là đúng cái các luật đã duyệt đòi; 70 / 907 có căn cứ phụ thuộc cụ thể và vẫn **tạm** cho tới read-set ở head cuối.

## 2. Mọi sửa đã duyệt nằm trong `69b0ea9` (chỉ thị mục 3) — `ALL_IN_SNAPSHOT`, người bác bỏ **đồng ý** (08:20–08:40)

Mọi commit triển khai nêu trong `docs/v2.1/REPORT.md` §0.9 và hai bản ghi owner (round-5) đều là tổ tiên của `69b0ea9`
(`git merge-base --is-ancestor`, 32 sha mục 1–5 + 9 sha mục 6 + 5 sha bản ghi). Hành vi đọc từ mã **tại `69b0ea9`**
(`git show 69b0ea9:<path>`) cho cả bảy mục chỉ thị và các câu trả lời D-1/D-2/mặc định; tệp test ghim có mặt
(`git ls-tree 69b0ea9`). Chạy thử 4 tệp test trên `git archive 69b0ea9` trong scratch, `env -i`, PATH không có `opencode`,
`nice 19`: 84 passed, 143 subtests, 13,98 s (08:26:51–08:27:06). Không nhánh nào mang mã cửa sổ chưa gộp (các nhánh có
commit `aisef2/` ngoài `69b0ea9` đều từ 2026-10-06 trở về trước: `release/v2.0.1-prep`, `wip/v2.1-confinement`,
`scratch/blast-pth`, hai nhánh dogfood). D-2: `CAPABILITY_VERSION = 1` ở `cli_invocation.py:278`, `process_effect.py:208`,
`python_callable_v2.py:134`; giới hạn nằm trong `LIMITS[0]` (`report.limits`) và USAGE-2.1 §2. **Chưa kiểm**: full suite,
recorder Linux, `offline_groups.sh`, bản ghi dẫn xuất, E2E, OCR offline — là các bước sau campaign.

## 3. Ngữ nghĩa approval trong `bundle migrate` (chỉ thị mục 3) — `WITHHELD_NOT_EFFECTIVE`, người bác bỏ **đồng ý** (08:23–08:36)

**Mã** (`aisef2/app/bundle_cli.py`, blob `8be81aa2…` giống nhau ở `69b0ea9`, `ff6309f`, `fbedf1b`): `migrate` 409–412 lọc approval
của contract bị một thay đổi capability chọn trúng **ra khỏi** mảng `approvals` của ứng viên (không có dạng "cắm cờ nhưng
còn"); bất biến 415–420: tập chưa duyệt của ứng viên phải **bằng đúng** các contract bị chọn, thiếu hay thừa ⇒ `MigrationError`;
`candidate.loads = not reapprove`; đầu vào không bao giờ được ghi (`--out` phải chưa tồn tại, tạo bằng mở độc quyền).
`seal --keep-approvals-from` 578–592: approval bị chọn không vào bundle niêm phong (`approvals_withheld_semantic`). `lint`
719–721: `NOT_READY` khi còn contract chưa duyệt, exit 1. `_assess` đóng-khi-thiếu (probe không khai phiên bản, probe khác
của release, phiên bản không có bản ghi `CAPABILITY_CHANGES` đúng dạng ⇒ chọn mọi contract của probe); không tên contract
nào viết cứng (`grep BC-V22|S-10|S-12|LedgerLock` trên `bundle_cli.py`: 0).

**Chạy thật offline** (08:23:54 +07; worktree tại `ff6309f`, PATH không có `opencode`, HOME/TMPDIR scratch, `PYTHONPATH` = worktree
vì `aisef` không cài vào python Homebrew): `python3 -P -m aisef bundle migrate closure-evidence/v2/release/LEDGERLOCK-PROJECT.json
--out <scratch>/LEDGERLOCK-2.1-candidate.json` → exit 0; 59 spec rebound, 67 obligation; **53 approval mang sang, 6 không**
(`BC-V22-S-10-a/b/c`, `S-12-a/b/c`, `why = semantic`, chọn bởi PM-9 + PM-11); ứng viên: 6 approval ấy **vắng** trong
`approvals` (59 → 53, hiệu đúng sáu), 59 contract còn nguyên, `loads: false`, `bundle_digest 1010f0da…7417`, `file_sha256
a21fa2c7…5f03` (= số đã ghi ở USAGE-2.1 §2); `B.load(candidate)` từ chối "BC-V22-S-10-a is not approved". `bundle lint
<candidate>` → exit 1, `NOT_READY`, `to_approve` = đúng sáu. Đầu vào: sha256 `157858a0…80f3a4` trước = sau, `git status` sạch.
Ứng viên nằm trong scratch, không ghi vào kho. **Chưa kiểm**: `seal --keep-approvals-from` qua CLI trên tệp thật (chỉ có test
`test_the_command_writes_a_bundle_without_those_approvals`).

**Tài liệu**: chữ "giữ lại" (hai nghĩa) trong nghĩa withheld được thay bằng "không được mang sang ứng viên (chỉ còn trong bundle gốc,
làm lịch sử; không có hiệu lực trong ứng viên mới)" ở `docs/v2.1/USAGE-2.1.md`, `REPORT.md`, `ADR-V2.1.md`,
`decisions/B-01-V2-007-THREE-IDENTITIES.md`; một câu theo lời chủ dự án thêm vào USAGE-2.1 §2. Người bác bỏ so đa tập số, mã hex và
đoạn backtick từng tệp: **bằng nhau**; 0 thay đổi mã/test; không test nào mở `docs/v2.1/*.md`. Commit `a57742b`
(`lane/approval-wording`), gộp `c60170e`. "Giữ sáu" (D-1) là lời của chủ dự án về **số** contract, giữ nguyên. Ghi chú: hai
trích dẫn số dòng USAGE-2.1 (`validation/v21/ocr/BUILD-RECIPE.md:94` → nay :165; docstring
`tests/v2/test_v21_r3_usage_no_progress.py:9` → :87) lệch 2 dòng — không sửa trong campaign (tệp test là kill file ghim sha;
recipe được hai test OCR đọc); để backlog.
