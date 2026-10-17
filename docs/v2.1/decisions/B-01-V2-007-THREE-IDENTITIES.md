# B-01 — ARCHITECTURE-EXCEPTION-V2-007: ba danh tính của probe

**Trạng thái: ĐỀ XUẤT, CHƯA DUYỆT.** Đã áp dụng trên nhánh `v2.1/foundation` theo chỉ thị 2026-10-06 ("tách ba danh
tính"); không có bản ghi phê duyệt nào được tạo. Không có gì ở đây là phê duyệt của chủ dự án.

> **Hiệu đính 2026-10-18** (phần còn lại của tệp giữ nguyên văn đề xuất): trạng thái trên là của lúc đề xuất. Chủ dự án đã duyệt B-01
> trong chat ngày 2026-10-06 (kỹ thuật chép vào `RELEASE-DECISIONS.json` seq 4, chủ dự án không ký; STATUS B6, ADR-2). Câu "không duyệt
> lại" ở mục Tương thích cũng không còn đúng: xem hiệu đính ngay sau mục ấy.

## Quy tắc cũ / mới

| | 2.0.0 (`610a593`) | 2.1 (`919a271`, `06d4e62`) |
|---|---|---|
| `DIGEST` của probe | `_probe_digest()` = sha256 các tệp nguồn của probe | `sha256(json([PROBE_ID, CAPABILITY_VERSION, list(CLASSES)]))` — **năng lực** |
| byte đang chạy | = `DIGEST` | `EXECUTION_DIGEST = _probe_digest()` (công thức cũ) |
| spec id, semantic hash, plan, approval-qua-plan | buộc vào byte | buộc vào **năng lực** |
| hàng hiệu chuẩn (check 9 của admission), RunSpec | buộc vào byte | buộc vào **byte** (`calibration.executing(probe)`) |
| đổi một chú thích trong probe | đổi mọi spec id ⇒ mọi bundle buộc lại, mọi bản ghi phái sinh đỏ (đo: một `-S` làm đỏ 37 test) | spec/approval/plan giữ nguyên; **phải hiệu chuẩn lại** (check 9 từ chối byte chưa hiệu chuẩn) |
| đổi điều quan sát (lớp, ngữ pháp stimulus, luật verdict) | tự động đổi digest | **tăng `CAPABILITY_VERSION` bằng tay** (đã làm: file_artifact → 2 khi thêm `python_imports`) |
| probe Cycle-1 `python_callable.py` | — | không đổi (digest `1961e84d…` là lịch sử đã niêm phong) |

## Tác động bảo mật

- **Rủi ro mới:** một thay đổi *ngữ nghĩa* của probe mà người viết quên tăng `CAPABILITY_VERSION` giữ nguyên spec id ⇒
  approval cũ áp vào hành vi quan sát mới mà không ai duyệt lại. 2.0.0 không có rủi ro này (mọi byte đổi ⇒ id đổi).
- **Chặn bằng cơ chế:** byte đổi ⇒ `EXECUTION_DIGEST` đổi ⇒ check 9 từ chối plan cho tới khi có hàng hiệu chuẩn mới ở
  đúng byte đó, chứng minh tương phản trên fixture đã commit (dương SATISFIED, âm REFUTED) cho **mọi** lớp. Một thay đổi
  ngữ nghĩa làm lệch verdict trên fixture sẽ đỏ ở đây.
- **Không chặn được:** thay đổi ngữ nghĩa mà fixture hiệu chuẩn không phủ (fixture vẫn đúng, hành vi ngoài fixture đổi).
  Đó là kỷ luật review, không máy nào kiểm. Digest/AST khớp không chứng minh tương đương hành vi.

## Tương thích

- Bundle 2.0.0 bị từ chối khi nạp vào 2.1, kèm gợi ý; `aisef bundle migrate` buộc lại một lần (đo trên LedgerLock: 59
  spec, 67 obligation, admit 9/9, không duyệt lại — approval buộc `contract_hash`, không đổi).
- Run 2.0.0 vẫn verify được: bằng chứng cũ giữ nguyên byte; RunSpec của 2.0.0 dựng lại không đổi.
- Không đổi format journal, taxonomy, đường quyết định.

> **Hiệu đính 2026-10-18** (đoạn trên giữ nguyên làm lịch sử: nó là phép đo lúc đề xuất). Câu "không duyệt lại — approval buộc
> `contract_hash`, không đổi" và "admit 9/9" **không còn đúng**. Từ chỉ thị 2026-10-15 mục 1 (`d1460fd`), `aisef bundle migrate`
> không giữ một approval chỉ vì `contract_hash` không đổi: nó ghi một bundle **ứng viên mới**, chỉ mang approval nào mà contract
> không bị một thay đổi capability đã khai báo (`CAPABILITY_CHANGES`) chọn trúng. Trên LedgerLock 2.0.0: giữ 53 trong 59 approval,
> giữ lại **sáu** contract (`BC-V22-S-10-a`, `S-10-b`, `S-10-c`, `S-12-a`, `S-12-b`, `S-12-c`); ứng viên chưa nạp được (`lint`
> `NOT_READY`) cho tới khi chủ dự án duyệt lại sáu contract ấy, và admission thật chỉ chứng minh được sau khi hiệu chuẩn sinh lại
> (USAGE-2.1 §1, §2). Chủ dự án đã giữ sáu ngày 2026-10-18 (D-1). Rủi ro "quên tăng `CAPABILITY_VERSION`" ở mục Tác động bảo mật đã xảy ra
> với ba probe `cli_invocation`, `process_effect`, `python_callable_v2` (D-2): chủ dự án chấp nhận giới hạn ngày 2026-10-18, nên 50 trong 53
> approval được giữ vẫn chỉ dựa vào luật phiên bản (`closure-evidence/v2/v2.1/round-5/OWNER-ANSWERS-2026-10-18.md`).

## Phương án

| | Nội dung | Ưu | Nhược |
|---|---|---|---|
| **A. Phê chuẩn V2-007** (khuyến nghị) | giữ ba danh tính; thêm vào charter kỷ luật "đổi ngữ nghĩa ⇒ tăng CAPABILITY_VERSION" và test hiệu chuẩn buộc mọi lớp | sửa probe không làm đổ mọi bundle/bản ghi; bảo mật/ổn định của probe cải thiện được | rủi ro "quên tăng version" (giảm nhờ check 9 + fixture) |
| B. Bác, quay về một danh tính | revert phần danh tính của `919a271`/`06d4e62`, giữ `-S` (đổi spec id thêm một lần nữa) | không có rủi ro trên | mỗi bản vá probe = migrate mọi bundle + tái lập mọi bản ghi |
| C. Ba danh tính + hash AST cho `DIGEST` | `DIGEST` = hash AST nguồn probe | tự phát hiện mọi thay đổi mã | đổi định dạng/chú thích không đổi hash nhưng đổi tên biến thì đổi — không đo được ngữ nghĩa; thêm phức tạp |

**Khuyến nghị: A.** Căn cứ: đã đo chi phí của một danh tính (37 test đỏ vì một cờ `-S`); check 9 đã buộc byte vào bằng chứng
hiệu chuẩn; rủi ro còn lại được nêu và có người chịu trách nhiệm (review).

## Rollback (nếu chọn B sau khi đã dùng 2.1)

1. Revert phần danh tính (giữ `-S` và hai venv), tái lập `aisef2/app/calibrations.py` theo byte.
2. Bundle đã migrate sang id 2.1 phải migrate ngược: bảng `bundle_cli.RELEASES` giữ digest của 2.0.0, đủ để ánh xạ ngược
   (công cụ ngược chưa viết — ước tính nhỏ, cùng cơ chế `_mint`).
3. Mọi bản ghi phái sinh 2.1 tái lập lại. Bằng chứng 2.0.0 không bị đụng.

## Cần chủ dự án

Chọn A/B/C; nếu A: ký một bản ghi phê duyệt (chủ dự án tạo, không phải tôi).
