# AISEF 2.1 — Nghiên cứu mã nguồn upstream (2026-10-06)

Bản ghi đầy đủ (mọi tuyên bố, tệp đã đọc, dòng mã, đối chứng): [`research/UPSTREAM-RESEARCH.json`](research/UPSTREAM-RESEARCH.json).
Cách làm: mỗi repo được clone mới, đọc **mã** ở commit ghim (không chỉ README), rồi một agent thứ hai kiểm chứng đối
nghịch từng tuyên bố của agent thứ nhất trên cùng commit. Nhãn bằng chứng dùng trong tài liệu này:

| Nhãn | Nghĩa |
|---|---|
| **CODE** | đọc trong mã nguồn ở commit ghim, có `tệp:dòng` |
| **README** | chỉ do tài liệu của dự án nói, chưa thấy trong mã |
| **INFERENCE** | suy luận của người nghiên cứu từ mã, chưa đo |
| **EXPERIMENT** | kết quả đo do chính dự án upstream công bố |
| **NOT_FOUND** | tuyên bố của đề xuất mà mã không xác nhận |

## Nguồn, commit, giấy phép

| Repo | Commit đã đọc | So với commit đề xuất trích | Giấy phép | Cách AISEF dùng |
|---|---|---|---|---|
| alibaba/open-code-review | `182898cf522d` (tag v1.12.12, 2026-10-05) | giống hệt | Apache-2.0 (biểu tượng UI: MIT, NOTICE riêng) | chạy như tiến trình ngoài, ghim phiên bản + sha256 nhị phân; không vendor, không import |
| XiaomiMiMo/MiMo-Code | `6babeb0b98f9` (2026-10-03) | giống hệt | MIT (fork của opencode; README thêm điều khoản USE_RESTR) | chỉ học thiết kế, không chép mã |
| alphaXiv/OpenResearch | `951700eff475` (HEAD); đề xuất trích `d52a0536` | 4 commit sau, 4 tệp trích **byte-identical** | MIT | chỉ học thiết kế, viết lại bằng Python |
| SWE-agent/mini-swe-agent | `04d809ceab9d` (v2.4.6) | giống hệt | MIT | chỉ học thiết kế; cánh A' tuỳ chọn |
| opensandbox-group/OpenSandbox | `c7dc78a4090e` | đề xuất không trích commit nào | Apache-2.0 | chưa dùng; danh mục kiểm cho V2-05 (sandbox) |

Tổng kiểm chứng: 165 tuyên bố **xác nhận**, 46 **phải sửa**, 1 **bị bác**, 1 **không kiểm được**; 80 điểm agent thứ
nhất bỏ sót được bổ sung. Tuyên bố bị bác: "OCR không công bố số đo chất lượng" — sai; repo có bảng AACR-Bench
(**EXPERIMENT**, `pages/src/components/BenchmarkSection.tsx:43-56`): recall 11,7–20 %, precision 25,2–37,8 %. Vì vậy
AISEF coi **mọi** phát hiện của OCR là tuyên bố chưa xác minh.

## Đã dùng gì, ở đâu trong 2.1

| Cơ chế upstream (nhãn) | Thành phần 2.1 | Ghi chú |
|---|---|---|
| OCR: manifest coverage v1, `item_id` = sha256(review, mode, old, new) (**CODE** `internal/session/manifest.go:190-210`) | `aisef2/app/review_ocr.py` `coverage`, `item_id` | công thức tính lại khớp đúng giá trị fixture (đã kiểm) |
| OCR: fingerprint SARIF path\|category\|existing_code (**CODE** `cmd/opencodereview/sarif.go:280-297`) | `review_ocr.finding_id` | thêm chỉ số lần xuất hiện sau khi sắp xếp xác định |
| OCR: exit 0 cho cả `partial` (**CODE** `review_cmd.go:326-352`) | `coverage` không bao giờ đọc exit code là "đã review đủ" | `files_reviewed` không được dùng làm coverage |
| OCR: `.gitignore`/thư mục provider bị loại khỏi preview (**CODE** `diff/git.go`) | đường dẫn bắt buộc vắng trong preview ⇒ INDETERMINATE | |
| OCR: tự cập nhật qua npm, telemetry OTel (**CODE** `bin/ocr.js:89-110`, `telemetry/config.go`) | `review_ocr.environment`: OCR_NO_UPDATE=1, xoá OCR_/ANTHROPIC_/OTEL_ | |
| MiMo: trạng thái do controller sở hữu, tóm tắt của agent chỉ là gợi ý (**CODE** `memory-path-guard.ts`) | `aisef bundle continue`: sự thật là journal, không phải tóm tắt | MiMo cho agent ghi checkpoint — AISEF thì không |
| MiMo: kiểm script-sha khi resume (**CODE** `runtime.ts:1551`) — nhưng chỉ hash bản sao của chính nó (**sửa**) | `continue` so bundle digest, kernel digest, sha256 tài liệu yêu cầu với nguồn gốc | |
| OpenResearch: snapshot nguồn đánh địa chỉ nội dung, kiểm lại khi dùng (**CODE** `compute.rs`, `localrun.rs`) | `validation/experiments/harness.py` `source_identity` | thêm digest file sau giải nén (eol/filter, **sửa** của người kiểm) |
| OpenResearch: thí nghiệm anh em dưới một cha (**CODE** `store.rs`) | `pair_problems`: hai cánh chỉ khác biến đang thử | |
| OpenResearch exact/unresolved/manual — chỉ là nguồn gốc harness, không phải xác minh model (**sửa**) | `model.identity_confidence` ∈ verified/provider_reported/unverified + lý do | |
| mini-swe-agent: giữ mọi lượt thất bại, chụp workspace từ ngoài (**CODE** `programbench.py:107-115`) | `direct_arm`: harness commit cái client để lại; "xong" của agent chỉ được ghi | |
| mini-swe-agent: chi phí 0 khi không định giá được (**CODE** `models/__init__.py:25-31`) | `aisef2/app/usage.py`: giá không biết = `null`, không bao giờ 0 | |
| OpenSandbox: egress sidecar default-deny, hardening docker (**CODE**) | chưa dùng — danh mục kiểm cho sandbox V2-05 | **không** phải điều kiện của 2.1 |

## Không dùng, và vì sao

- **Nhập orchestrator nào** trong ba repo: chỉ thị của chủ dự án; AISEF giữ một đường quyết định.
- **Cơ chế MiMo cho agent ghi `checkpoint.md`/sửa trạng thái task** (**CODE** `tool/task.ts:199`): trái với "trạng thái
  do controller sở hữu".
- **Grant "always" vào ruleset cả phiên của MiMo** (**CODE** `runtime.ts:716-764`): trái INV-MUTATION-AUTHORITY.
- **execd trong sandbox của OpenSandbox** (**INFERENCE** trên **CODE** `main.go:232-235`, `manager.go:261` @ `c7dc78a4090e`;
  [research/UPSTREAM-RESEARCH.json](research/UPSTREAM-RESEARCH.json) N7): bài học ngược — controller không đặt daemon
  điều khiển trong vùng của workload.

## Rủi ro mở (chưa đo, ghi để không tuyên bố quá)

- `review_ocr` chưa chạy với nhị phân OCR thật (không có trên máy, chưa có ngân sách provider); hình dạng `rule.json`
  (`include`) là **INFERENCE** từ `system_rules.go`.
- Ngày 2026-10-06 trang giá chính thức của DeepSeek ghi tên model cũ được phục vụ bởi V4.1-Flash; một nguồn thứ ba nói
  `deepseek-v4-pro` cũng bị chuyển — **chưa xác nhận**. Mọi lượt chạy thật phải ghi danh tính model ở mức
  `provider_reported` và kiểm lại trang giá đúng ngày chạy (xem [EXPERIMENT-PLAN.md](EXPERIMENT-PLAN.md)).
