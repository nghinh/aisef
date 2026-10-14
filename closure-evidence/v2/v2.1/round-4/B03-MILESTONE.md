# B-03 — mốc kỹ thuật đã đạt (ghi nhận, không phải nghiệm thu)

**Phạm vi của câu này:** vòng B-03 (RELEASE-DECISIONS seq 5: B-03a, b, c, d) và các việc chủ dự án giao ngày 2026-10-12 đã
đạt **các tiêu chí kỹ thuật đã kiểm chứng** liệt kê dưới đây, ở đúng các commit được nêu. Đây **không** phải nghiệm thu
sản phẩm, **không** phải phép phát hành, **không** nói gì về hiệu quả với mô hình thật. Bản ghi
`C2-P5-ACCEPTANCE-REVERIFICATION.json` giữ nguyên: **"C2-P5 ACCEPTANCE BOUNDARY RE-VERIFIED ON 2.1 — NO NEW OWNER
ACCEPTANCE"**, `claims_owner_acceptance: false`.

## Tham chiếu (từng cái một, không gộp)

| Cái được nêu | Giá trị | Nguồn kiểm |
|---|---|---|
| Cây sản phẩm `aisef2/` mà bản ghi mutation đo | tree id `1d4f0156f568f240f49fbbc10e5a366a13b18f58` — **giống nhau** ở `534435f`, `8043387`, `45554e0`, `becf3c0` | `git rev-parse <commit>:aisef2` |
| Bản ghi mutation V2.1 | `MUTATION.json` + `MUTATION-SUMMARY.json`, viết ở FINAL_HEAD `8043387c562c31429215430c6954aefb747aee72` (commit bản ghi `42e0305`); trường `snapshot` = `cc5359699c05…` là SNAPSHOT đóng băng của pha (manifest gốc) | `v21_mutation_record.py --check` |
| Kết quả bản ghi | 528 target, 13.581 mutant, 13.388 KILLED, 193 SURVIVED đã audit (136 AUDITED + 57 EQUIVALENT), 0 chưa audit, 0 TIMEOUT/INFRA/NOT_RUN, `MUTATION_VERDICT` **PASS** | `MUTATION-SUMMARY.json` |
| Nguồn từng kết quả (mỗi target tính một lần) | 472 theo đợt 5 (`289885e`), 43 theo đợt 6 (`a770fbb`), 1 theo đợt 7 (`853da4a`), 12 theo đợt 8 (`5df323a`, manifest rev 8) | `campaign-8/SCOPE.json` |
| Commit chạy **full suite** | **`45554e0c19bc56c8dc6854fa96ccdb6d34a108d4`**: Ran 7305, OK (skipped=85), 0 failure/error; hermetic; kho OpenCode thật không đổi | `round-4/SUITE.md`, `round-4/suite-45554e0/` |
| HEAD đã kiểm checker phụ thuộc bằng chứng | **`becf3c08bebc741754755df7dc046cb7021848f2`**: `v21_mutation_record.py --check` PASS; 3 bảng delta `--check` PASS; 315 test của các module đọc bằng chứng OK (hermetic) | `round-4/README.md` |
| Bản ghi phái sinh ở cây cuối | Q0 54/54 (`79cf437`); C2-P5 re-verification, K-NOWORK-001 (REPRODUCED AND CORRECTED), Q5, ruling (`c186cb2`) | `closure-evidence/v2/v2.1/*.json` |

Từ `45554e0` tới `becf3c0` chỉ có thêm tệp trong `closure-evidence/` (không đổi mã, test, tài liệu): suite **không** được
chạy lại, và kết quả suite **chỉ** đại diện cho `45554e0`.

## Không thuộc kết luận này

* **Hiệu quả / chất lượng với mô hình thật**: chưa đo. Mutation KILLED là test bắt được thay đổi nhỏ của mã; không suy ra
  chất lượng review, hiệu quả context pack hay tiết kiệm chi phí.
* **Windows, Linux CI**: chưa chạy (chưa push). Lượt Linux guest (bwrap) là bằng chứng riêng, nêu ở REPORT §0.4.
* **Sẵn sàng phát hành 2.1**: chưa — trạng thái riêng, cần các quyết định và bước còn lại ở REPORT §0.8 và §7.
* **Tồn đọng đã biết, chưa sửa/chưa quyết** (không do vòng này đóng): PM-1/2/3/4/6/11 và RV-1/RV-2 (lỗi đã xác nhận, đang
  chờ cửa sổ sửa); PM-5/7/8/9/13 và các quyết định B-02/B-04/B-08/B-09/B-10, ranh giới cách ly Linux (F), ba tệp
  probe trong `site-packages` (RM-3) — xem `docs/v2.1/REPORT.md` §0.7, §7 và `decisions/`.
* Skip của suite (85) chỉ là skip có điều kiện của test; việc có bằng chứng riêng cho từng nhóm skip được lập riêng.
* Không có gì được push, gắn tag, publish, deploy hay phát hành; không gọi provider trả tiền.
