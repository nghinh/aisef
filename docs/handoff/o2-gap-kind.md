# O2 — sổ hành vi ghi **loại** vắng mặt, hàng đợi sửa định tuyến theo loại

Đóng issue **O2** của `docs/ADR-009-phase-3-cross-tier-invariants.md` (mục
`## Open`). Luật "gap chỉ thiếu truy vết do harness sửa, không do story" (quyết
định chủ đầu tư 2026-09-06 §4) trước đây chỉ nằm trong văn bản quyết định; nay
nằm trong code, có số đo trên bốn kho dogfood.

> ADR-009 **không** được sửa trong lượt này: năm agent chạy song song và mục
> `## Open` là chỗ cả O1/O3/O4 đều phải chạm. Dòng "closed by" cho O2 nên do
> người gộp thêm vào.

## 1. Ba loại vắng mặt, phát hiện từ bằng chứng nào

`Behavior.gap_kind` (`aisef/control/ledger.py`) là **property chiếu từ
`source.why`** — đúng bộ câu mà chính sổ viết ra — nên nó vẫn là phép chiếu,
không phải trạng thái mới: xoá `ledger.json` rồi dựng lại từ `evidence/` cho
cùng kết quả, và `ledger.json` không có trường nào ai gõ tay được.

| loại | phát hiện từ (bằng chứng đã có trên đĩa) | hành động |
|---|---|---|
| `unbuilt` | mọi lý do còn lại: test mang mã **đỏ**; xanh trên ứng viên **chưa landed**; `qa:*` đỏ; màn hình thiếu | story sửa trả phí (như cũ) |
| `untested` | `source.why == "no test carries this code"` — lần chạy đọc được tên test, không tên nào mang mã tiêu chí | **story chỉ-viết-test**: `write_scope` đúng bằng đường test |
| `untraced` | `why` bắt đầu bằng `"cannot read test names from runner output"` (harness không có tên test nào để gắn) **hoặc** `"declared trace not in this run: <id>"` (đã khai `--link` mà test không có trong lần chạy) | **sửa siêu dữ liệu bằng harness** — ra khỏi hàng đợi trả phí |

Ba quyết định về phương pháp, nói thẳng:

1. **Không** dùng "story đã `done`/đã landed" để tách "chưa xây" khỏi "đã xây
   mà thiếu test". Story qua cổng *không* chứng minh code của tiêu chí cụ thể
   ấy tồn tại — chính vì thế sổ mới ghi gap. Dùng nó là đúng kiểu "heuristic
   trông dứt khoát mà không dứt khoát". Thay vào đó `untested` chỉ khẳng định
   điều đã đo: **cái vắng mặt được đo là test**. Nếu code cũng thiếu thật thì
   test mới sẽ đỏ, sổ ghi test đỏ, vòng sau gap thành `unbuilt` và được story
   đủ phạm vi — thang leo tự sửa, giá một vòng rẻ.
2. Loại **không xác định được thì về `unbuilt`**, tức phía đắt. Gán sai một
   defect thật thành "harness sửa" là che nó đi; gán sai chiều ngược lại chỉ
   tốn tiền.
3. `untraced` trong bốn kho **không phải** ca "test có sẵn thiếu thẻ" mà ADR mô
   tả, mà là ca harness không đọc được tên test (`tool not installed`). Cả hai
   cùng một hệ quả — không có đường nối hành vi → test — và cùng một loại hành
   động (sửa harness), nên cùng một loại. Ca "test có sẵn chứng minh đủ, chỉ
   thiếu thẻ" **không suy ra được** từ bằng chứng nếu không ai khai: nó đòi đọc
   *thân* test. Nó chỉ phát hiện được khi có khai báo trên đĩa — `traceability.json`
   (đường `WHY_TRACE_ABSENT`) hoặc người rà soát trả `[stuck] trace: <id>`.
   Bốn kho: `traceability.json` **không tồn tại** ở kho nào (`len(led.links) == 0`
   cả bốn), và không có bản ghi `trace:`/`truy vết` nào trong `reviews/` hay
   `evidence/`. Vậy kiểu thứ ba hiện đo được **0 ca đúng-nghĩa-ADR**, và 5 ca
   cùng-hành-động.

## 2. Số đo — phân bố ba loại trên bốn kho dogfood

`L.build(<kho>/_bmad-output)` rồi đếm `b.gap_kind` trên mọi hành vi
`gap`/`reopened`; `paid queue` là `improve.repair_queue(...)`:

| kho | hành vi | non-green | `unbuilt` | `untested` | `untraced` | vào hàng đợi trả phí | ngoài hàng đợi |
|---|---|---|---|---|---|---|---|
| todo-oc | 47 | 3 | 3 | 0 | 0 | 0 | 3 (`qa:*`) |
| todo-cli | 61 | 27 | 23 | 4 | 0 | 26 | 1 (`qa:sit`) |
| todo | 36 | 10 | 5 | 0 | **5** | 5 | 5 (`untraced`) |
| todo-e2e | 23 | 9 | 9 | 0 | 0 | 7 | 2 (`qa:*`) |
| **tổng** | **167** | **49** | **40** | **4** | **5** | **38** | **11** |

Đọc con số:

* **5/49 (10 %)** hành vi non-green là `untraced`: cả năm tiêu chí của
  `todo` STORY-02-02, `why = "cannot read test names from runner output: tool
  not installed…"`. Trước lượt này cả năm đều đủ điều kiện vào hàng đợi và
  `improve` sẽ mở **năm story sửa trả phí** cho một lỗi cấu hình runner. Nay
  chúng ra khỏi hàng đợi, lý do dừng nêu đúng nguyên nhân đã ghi và câu lệnh
  sửa.
* **4/49 (8 %)** là `untested` → story chỉ-viết-test, phạm vi ghi hẹp lại còn
  đường test.
* **40/49 (82 %)** là `unbuilt`, tách theo lý do đã ghi: **18** `"story criteria
  not yet green"` (yêu cầu fr/nfr đỏ qua tiêu chí), **13** `"green on unlanded
  candidate"`, **9** không có câu lý do (test đỏ / `qa:*` đỏ / màn hình thiếu).
  Đây là số đáng chú ý của bài đo: phần lớn gap của dogfood **không** phải
  "chưa viết test", mà là "đã viết, đã xanh trong worktree, không bao giờ
  landed" — 13 ca xanh-chưa-landed cộng 18 yêu cầu đỏ theo chúng.
* `qa:*` vẫn ngoài hàng đợi như QĐ B6 — không đổi.

### Thừa hưởng loại ở mức yêu cầu (fr/nfr) — đo và báo cả cái vô can

FR/NFR đỏ **qua** tiêu chí của nó, nên nó thừa hưởng loại khi mọi tiêu chí
non-green cùng một lý do, và chỉ khi bằng chứng ấy ở ứng viên **landed**. Đo
trên 18 gap mức yêu cầu của bốn kho: quy tắc này chuyển **0/18** — mọi gap mức
yêu cầu ở đây đều nằm trên bằng chứng chưa landed. Bỏ cửa `landed` thì nó
chuyển 9/18 và **chuyển sai**: chín gap của todo-cli STORY-06-01 bị rút gọn
thành "một tiêu chí thiếu test" trong khi bảy tiêu chí kia chỉ xanh trong
worktree không merge. Giữ luật (4 dòng) vì nó là câu trả lời đúng cho ca kho
chưa có — story đã landed mà tiêu chí chỉ thiếu test — và có test đơn vị phủ.

## 3. Hai defect phát hiện khi đo (không có trong đề bài)

1. **Lý do của gap bị đóng băng.** `Ledger.observe` chỉ cập nhật `source` khi
   trạng thái **đổi**. Một gap sinh ra vì "không test nào mang mã" mà lượt sau
   có test **đỏ** vẫn giữ `why` cũ → `gap_kind` đứng ở `untested` mãi, hàng đợi
   mở story chỉ-viết-test lặp lại và thang leo `untested → unbuilt` không bao
   giờ chạy. Sửa: nhánh "không đổi trạng thái" cập nhật `source` cho hành vi
   non-green (VERIFIED giữ nguồn của lần chạy đã chứng minh nó).
2. **Dấu bế tắc truy vết chỉ nhận một thứ tiếng.** `_body` dặn người rà soát
   trả `[stuck] trace: <test id>` (tiếng Anh) còn `_write_report` chỉ khớp
   `"truy vết"` → làm đúng lời dặn thì dòng chỉ đường sửa siêu dữ liệu **mất**,
   báo cáo đọc như một vòng thất bại thường. Sửa: `_TRACE_STUCK` khớp cả hai.

## 4. Thay đổi theo tệp

* `aisef/control/ledger.py`
  * hằng `UNBUILT` / `UNTESTED` / `UNTRACED` + `WHY_NO_TEST` / `WHY_UNREADABLE`
    / `WHY_TRACE_ABSENT` / `WHY_UNLANDED` (bên viết và bên đọc dùng cùng một bộ
    câu, không lệch nhau được);
  * `Behavior.gap_kind` (property) và `as_dict()` ghi kèm khi khác rỗng;
  * `ISSUE_COLUMNS` **thêm** `gap_kind` ở cuối (không chèn giữa: tracker đọc CSV
    theo vị trí vẫn đọc đúng các cột cũ); `gap_kind_counts()`; đầu `ISSUES.md`
    ghi ba số;
  * nhánh "không đọc được tên test" giữ `WHY_UNREADABLE` làm tiền tố rồi mới
    nêu nguyên nhân cụ thể;
  * ca "đã khai truy vết mà test không có trong lần chạy" ghi `why` riêng;
  * `observe`: cập nhật lý do mới nhất cho hành vi non-green (defect 1);
  * `_observe_tests`: yêu cầu thừa hưởng loại của tiêu chí khi bằng chứng landed.
* `aisef/phases/improve.py`
  * `REPAIR_ACTION` (`unbuilt` → story · `untested` → test-only story ·
    `untraced` → harness metadata fix);
  * `repair_queue` lọc `untraced` ra khỏi hàng đợi trả phí;
  * `stop_reason` tách hai loại "ngoài hàng đợi": `qa:*` → `aisef qa`;
    `untraced` → `aisef evidence <id> --link …`, kèm nguyên nhân đã ghi;
  * `repair_story`: `untested` → `write_scope` đúng bằng `verification_paths`
    (cổng phạm vi *thi hành* sự khác nhau giữa hai loại story, không phải văn
    bản story), và ghi `gap_kind` vào `stories.index.json`;
  * `_body`: dòng "Absence: <loại> → <hành động>" + đoạn "Test-only story";
  * `QGap.has_verifier` lấy đúng theo `repair_queue` để luật hợp nhất không
    thấy "gap sửa được" ở chỗ hàng đợi thấy "sửa siêu dữ liệu";
  * `_TRACE_STUCK` khớp cả `trace:` và `truy vết` (defect 2).
* `aisef/cli/implement.py` — `aisef issues` in ba số riêng.

## 5. Test mới (đỏ trước, xanh sau — hai lượt đều ghi trong báo cáo)

`tests/test_ledger.py::TestLoaiGap` (10):
`test_test_do_la_unbuilt`, `test_khong_co_test_mang_ma_la_untested`,
`test_khong_doc_duoc_ten_test_la_untraced`,
`test_khai_truy_vet_ma_test_khong_chay_la_untraced`,
`test_xanh_o_ung_vien_chua_landed_la_unbuilt`,
`test_yeu_cau_thua_huong_loai_gap_cua_tieu_chi`,
`test_ly_do_gap_khong_duoc_cu_khi_bang_chung_moi_noi_khac`,
`test_verified_thi_khong_co_loai_gap`, `test_bang_issues_dem_ba_loai_rieng`,
`test_loai_gap_vao_ledger_json_va_cot_csv`.

`tests/test_improve.py::TestDinhTuyenTheoLoaiGap` (5):
`test_gap_untraced_khong_vao_hang_doi_sua`,
`test_untraced_thi_khong_goi_model_ma_chi_cach_sua_sieu_du_lieu` (phép kiểm
tiền: `develop_calls == []`), `test_untested_thi_story_sua_chi_duoc_ghi_duong_test`,
`test_unbuilt_thi_story_sua_duoc_ghi_ca_code`,
`test_be_tac_truy_vet_tieng_anh_cung_duoc_nhan_ra`.

Một assertion cũ được cập nhật theo thay đổi có ý thức:
`tests/test_improve.py::TestVongSuaGap::test_story_sua_la_mot_hanh_vi_dung_dinh_dang_story_split`
— gap của fixture là `untested`, nên `write_scope` nay đúng bằng `[TEST_SCRIPT]`
(chặt hơn khẳng định cũ `write_scope[0] == "src/core"`; ý định của lỗi 21 —
đòi test thì phải cho ghi test — vẫn được giữ).

Toàn bộ: `ruff check .` sạch, `python3 -m pytest -q` → **2537 passed, 80
skipped, 1025 subtests** (trước lượt này 2522 passed).

## 6. Việc còn lại

* Kiểu "test có sẵn chứng minh đủ, chỉ thiếu thẻ" chỉ phát hiện được khi có
  khai báo trên đĩa. Muốn đo nó trên kho thật thì phải **ghi thêm**: người rà
  soát trả `[stuck] trace: <test id>` phải được harness ghi thành một bản ghi
  máy đọc được (hôm nay nó chỉ là chuỗi trong `Loop.stuck` và một dòng trong
  `LOOP-REPORT-<n>.md`), rồi vòng sau đọc lại thành `WHY_TRACE_ABSENT`. Đó là
  một bản ghi mới, không phải một heuristic — nên để riêng.
* ~~`Ledger.summary()` chưa mang ba số; `aisef report` và dashboard vẫn in một
  con số `gap`.~~ Xong: `summary()["gap_kinds"]` mang ba số, `aisef report` và
  `gap tồn` của dashboard chẻ ra — **chỉ khi** corpus có hơn một loại. Ba số ấy
  đếm mọi hành vi non-green nên cộng lại bằng `gap + reopened`, *không* bằng
  `gap`: dán chúng cạnh con số `gap` thì `todo-e2e` đọc thành "1 gap · unbuilt
  9". `ledger.json` vẫn không có trường nào mới (`snapshot()` chọn khoá phẳng,
  đo lại trên cả bốn kho).

---

### Đoạn gộp vào CHANGELOG.md

**Behaviour ledger records *which kind* of absence a GAP is, and the repair
queue routes each kind to a different action (ADR-009 O2).** `Behavior.gap_kind`
projects one of `unbuilt` / `untested` / `untraced` from the `source.why`
sentence the ledger itself wrote, so it stays derivable from recorded evidence
and `ledger.json` gains no hand-writable field. `improve.repair_queue` now keeps
`untraced` gaps out of the paid queue entirely — the owner decision of
2026-09-06 §4 ("a gap that is only missing traceability is fixed by the harness,
not by a story") is code now, not prose — an `untested` gap opens a *test-only*
repair story whose `write_scope` is the verification paths only, and `unbuilt`
keeps the full repair story. `aisef issues` reports the three counts separately
(stdout, `ISSUES.md` header, and a new trailing `gap_kind` column in both `md`
and `csv`). Measured over four dogfood corpora (167 behaviours, 49 non-green):
40 `unbuilt` · 4 `untested` · 5 `untraced` — the five being every acceptance
criterion of `todo` STORY-02-02, for which `improve` would have opened five paid
repair stories to fix one unconfigured test reporter. Two defects found while
measuring were fixed with it: a gap's recorded reason no longer goes stale when
a later run shows a different absence (it used to freeze at the state
transition, so the `untested → unbuilt` escalation could never fire), and the
reviewer's "only the trace is missing" verdict is now recognised in both
languages the harness asks for (`[stuck] trace:` as prescribed in the story
body, and `[bế tắc] truy vết:` as e9 reviewers returned it) instead of silently
dropping the metadata-fix instruction for the English form.
