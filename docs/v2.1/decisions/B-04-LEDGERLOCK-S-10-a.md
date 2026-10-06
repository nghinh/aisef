# B-04 — LedgerLock S-10-a: chọn bản sửa của contract import

**Trạng thái: ĐỀ XUẤT, CHƯA DUYỆT.** Bản nháp: `docs/v2.1/drafts/LEDGERLOCK-BC-V22-S-10-a-r2.DRAFT.json` (hai phương án,
đều chưa có approval).

## Yêu cầu gốc (REQUIREMENTS.md §10, nguyên văn)

> - Python 3.11+ required (use `from __future__ import annotations`).
> - Stdlib only. Allowed: `hashlib`, `json`, `os`, `sys`, `pathlib`, `tempfile`, `argparse`, `unittest`, `typing`,
>   `unicodedata`, `uuid`.
> - No `pip install` of any runtime dependency.

Facts của criterion S-10-a trong bundle: requirement `R-10`, clause `R-10/1`, "stdlib only; the allowed modules", subject
`ledgerlock/`.

## Contract đang được duyệt (2.0.0) và lỗi của nó (V21-37)

`file_artifact` grep `^\s*(?:import|from)\s+(?!(?:hashlib|json|…|ledgerlock)\b|\.)[A-Za-z_]` trên `*.py`, kỳ vọng 0
khớp. Đếm **theo dòng chữ**: một dòng trong docstring hay chú thích bắt đầu bằng `from …`/`import …` bị tính là import.
Đo ở smoke #2: một docstring làm LedgerLock bị bác sai (tái hiện trên reference: `test_v21_python_imports`).

## Hai phương án (đều dùng lớp mới `python_imports`: đếm import theo cú pháp `ast`)

| | A — danh sách §10 | B — toàn stdlib |
|---|---|---|
| allowed | `hashlib json os sys pathlib tempfile argparse typing unicodedata uuid __future__ ledgerlock` | `ledgerlock` + `stdlib: true` (`sys.stdlib_module_names` của interpreter quan sát, ghi trong detail) |
| `unittest` | **không** được phép (bất biến IX: contract không được nêu tên artefact test — `aisef2.product.contract._TEST_ARTEFACT`) | được phép (thuộc stdlib) |
| so với §10 | **chặt hơn** đúng một chỗ: `import unittest` trong `ledgerlock/` bị bác dù §10 cho phép | **rộng hơn**: cho mọi module stdlib, §10 chỉ cho 11 module |
| dòng docstring `from x import y` | không phải import ⇒ SATISFIED | SATISFIED |
| `import yaml` | REFUTED | REFUTED |
| `import sqlite3` | REFUTED (đúng §10) — đo | **SATISFIED** (sai so với danh sách §10) — đo |
| `import unittest` trong package | **REFUTED** (sai so với §10) — đo | SATISFIED — theo luật (unittest thuộc stdlib), không đo riêng |
| `importlib.import_module("yaml")` | không thấy (cả hai) — giới hạn đã nêu của lớp cú pháp (ADR-5), không đo | không thấy |

Các ô ghi "đo" có trong `tests/v2/test_v21_python_imports.py::Controls`. Đo trên reference LedgerLock: cả A và B SATISFIED; với dòng docstring của smoke #2
cả hai SATISFIED (regex cũ REFUTED); với `import yaml` cả hai REFUTED.

## Khuyến nghị: A

Căn cứ: §10 ghi "Stdlib only. Allowed: …" — danh sách là phần **có tính quy định**; B mở ra 200+ module mà yêu cầu không
liệt kê, tức thay đổi nghĩa của yêu cầu theo hướng rộng. A chỉ lệch §10 ở `unittest` *trong package sản phẩm* — nơi
`unittest` không có lý do xuất hiện (test nằm ở `tests/`, ngoài subject `path:ledgerlock`). Lệch chặt hơn còn hơn lệch rộng
hơn: một lần bác sai do `unittest` sẽ hiện ra rõ ràng (REFUTED kèm tên module), không âm thầm cho qua.

Nếu chủ dự án muốn khớp §10 tuyệt đối: cần một phương án C — sửa bất biến IX để phân biệt "stimulus nêu tên một module
test" với "contract là artefact test" — đó là một ngoại lệ kiến trúc, không đề xuất ở đây.

## Cần chủ dự án

Chọn A hoặc B (hoặc không), rồi `aisef bundle approve` contract đã chọn (contract_hash ở trên). Không cần `migrate`: một
contract mới là một approval mới.
