# Campaign 9 — kiểm toán survivor, đợt 1 (9 target đầu xong lúc 16:48 +07, 18/10)

Kiểm toán vị trí (`docs/v2.1/MUTATION-RUNNER-V2.md` §16) cho 91 survivor của 9 target campaign 9 hoàn tất sớm nhất
(`settings.load` không có survivor nên 8 batch). Snapshot đo `4ec961e`. Mỗi survivor: 38 có audit cũ mang sang theo
vị trí (`remap_audits.py`), 53 mới. Một tác giả dự thảo 53 mới; **hai bản mù độc lập** (a, b) tái thẩm cả 91, mỗi
agent chạy kill file thật trên mutant trong cây `git archive` riêng (`nice 19`, PATH không có `opencode`). Workflow
`wf_4655cf59-c2f`, 18 agent, 0 lỗi (ba lần gián đoạn hạn mức, resume từ cache).

## Kết quả hợp nhất (hai bản mù)

| batch (target) | AUDITED | EQUIVALENT | NỢ TEST |
|---|---:|---:|---:|
| B01 `adapters.Reviewer._ocr` | 9 | 0 | 0 |
| B02 `bundle.shape_problems` | (2 carried, chưa tái thẩm đợt này — xem §ghi chú) | | |
| B03 `bundle_cli.continue_from` | 4 | 1 | 9 |
| B04 `bundle_cli.migrate` | 24 | 6 | 0 |
| B05 `bundle_cli.seal` | 2 | 5 | 4 |
| B06 `cli.run` | (2 carried, chưa tái thẩm đợt này) | | |
| B07 `run.execute` | 8 | 2 | 1 |
| B08 `verify.verify` | 7 | 5 | 0 |
| **Cộng** | **54** | **19** | **14** |

AUDITED/EQUIVALENT **không** phải kill; `AUDITED` = quan sát được nhưng không consumer/contract nào nêu tên phụ thuộc,
`EQUIVALENT` = không khác biệt quan sát được, chứng minh từ mã. Mỗi mục có `grounds`, `consumers_checked`,
`exceptions_checked` riêng. Mọi mục đều kèm phép chạy kill file (SURVIVED đúng như campaign ghi; không kill file nào
giết được — nếu có thì đã ghi là lỗi đo, không có trường hợp nào).

## 14 trường hợp NỢ TEST — lỗ hổng thật (`owed-wave1.json`)

Đây **không** phải "thêm test cho đủ số": là hành vi quan sát được mà bộ test không pin.

- **`seal` [128,130,150,152] — hai bản mù đồng thuận REFUTED.** Hàng của `report['approvals_withheld_semantic']`
  (lệnh `bundle seal --keep-approvals-from`) bị bỏ/đổi tên trường `requirement` và `approved_at`. USAGE-2.1 §2 hứa
  hàng này cho người vận hành biết "ai duyệt, lúc nào"; không test nào so khớp bộ 4 trường
  `(contract, requirement, approver, approved_at)` của hàng.
- **`continue_from` [158,175,179,191,193,194,195,196,197] — một bản gọi "nợ test", một bản gọi AUDITED.**
  Không phải bất đồng về sự thật: cả hai đồng ý mutant đổi một trường **hiển thị cho người vận hành** trong báo cáo
  `spend_by_run` (cờ `superseded` của một hàng chi tiêu) mà **chỉ bản ghi** được test `T08b` pin, báo cáo thì không.
  Khác nhau ở nhãn. Theo luật round-3 của chủ dự án (một status/phần tử định danh được người vận hành đọc thì đáng
  pin), giữ cách đọc nghiêm: cần một test pin trường `superseded` trên hàng báo cáo. **Nếu chủ dự án muốn xếp các
  trường chỉ-người-vận-hành-thấy là AUDITED thay vì nợ test, đó là một quyết định** (giảm 9 mục này).
- **`execute` [358] — một bản "nợ test", một bản AUDITED**, cùng dạng (trường báo cáo không có reader mã).

## Việc tiếp theo (sau khi campaign 9 xong, có đủ survivor của mọi target)

1. Một đợt kiểm toán **đầy đủ** cho survivor của các target xong sau 16:48 (B02/B06 carried cũng gộp vào đây để tái thẩm).
2. Với các NỢ TEST đã chốt: viết kill file mới (`tests/v2/test_v21_kills9_*`), đăng ký cho đúng target trong
   `V21_TARGETS`, rồi **đo lại chỉ các target bị ảnh hưởng** (một campaign nhỏ như campaign 8), không mở lại toàn bộ.
3. Các mục cờ-báo-cáo của `continue_from`/`execute`: chờ chủ dự án quyết pin hay xếp AUDITED trước khi viết test.

Ghi 2026-10-18 ~22:50 +07. Dữ liệu: `*-draft.json`, `*-a.json`, `*-b.json` (nguyên văn mỗi agent), `owed-wave1.json`,
`survivors-wave1.json`, `batches/` = `B*.json`.
