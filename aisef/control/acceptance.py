"""Acceptance criteria ↔ test: the ``AC-<story>-<i>`` code contract.

Old traceability stopped at "story covers FR with green tests" — criterion 3
was never checked yet the report stayed green, and the reviewer was told
"point out which test covers which criterion": judgment where lookup was
needed. Now each criterion *i* of a story has code ``AC-<story>-<i>``; the
code must appear in the **name** of at least one test, and test names are
read from runner output (``harness/testlog``), not from agent claims.

Exact code matching: ``AC-S-1`` does not match ``AC-S-10``; ``_`` and ``-``
are treated as equivalent because pytest function names cannot contain
hyphens (``test_AC_S_1_empty_string``).
"""

from __future__ import annotations

import re


def ac_code(story_id: str, i: int) -> str:
    return f"AC-{story_id}-{i}"


def codes(story_id: str, n: int) -> list[str]:
    return [ac_code(story_id, i) for i in range(1, n + 1)]


def _pattern(code: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(code.replace('_', '-'))}(?![0-9])", re.I)


def coverage(story_id: str, n: int, test_ids: list[str]) -> dict[int, list[str]]:
    """Criterion i -> tests carrying its code (may be empty)."""
    norm = [(t, t.replace("_", "-")) for t in test_ids]
    out: dict[int, list[str]] = {}
    for i in range(1, n + 1):
        rx = _pattern(ac_code(story_id, i))
        out[i] = [t for t, tn in norm if rx.search(tn)]
    return out


def missing(story_id: str, n: int, test_ids: list[str]) -> list[int]:
    return [i for i, tests in coverage(story_id, n, test_ids).items() if not tests]


def _codes_of(story_id: str) -> re.Pattern:
    """Mã của **đúng** story này ở tên phép thử: `AC-<story>-<i>`.

    Dựng từ `story_id` đã biết, không tách chung `AC-(.+)-(\d+)`: dạng chung
    tách sai ở dấu gạch nào cũng được — không tham thì `AC-STORY-01-02-4` ra
    story=`STORY`, i=`01`; tham thì một mô tả chứa `-2` ăn vào mã.
    """
    sid = re.escape(story_id.replace("_", "-"))
    return re.compile(rf"(?<![A-Za-z0-9])AC[-_]{sid}[-_](\d+)(?![0-9])", re.I)


def orphans(story_id: str, n: int, test_ids: list[str]) -> list[str]:
    """Mã `AC-<story>-<i>` xuất hiện trong tên phép thử mà **i > n** — tức không
    còn tiêu chí nào mang mã ấy.

    Vì sao cần (lỗi 159): `ac_code` sinh mã từ **vị trí**, nên rút một tiêu chí
    làm mọi mã sau nó tụt một bậc. `missing()` chỉ hỏi "tiêu chí nào thiếu phép
    thử" và sau khi tụt bậc nó trả **rỗng** — mọi tiêu chí vẫn có phép thử mang
    mã đúng, chỉ là phép thử ấy chứng minh hành vi khác. Câu hỏi ngược lại
    ("mã nào không còn tiêu chí") là câu duy nhất phát hiện được sự dịch chuyển
    từ dữ liệu đang có, và nó không đòi danh tính bền — chỉ đòi đếm.

    Đo trên marks-cli: rút `AC-1.2-1` của STORY-01-02 (4 → 3 tiêu chí) để lại
    `AC-STORY-01-02-4` mồ côi, và `missing()` vẫn im lặng.

    Mã của story **khác** bị bỏ qua: một bộ test chứa mã của nhiều story là
    chuyện thường, và báo chúng thành mồ côi ở đây là báo động giả.
    """
    rx = _codes_of(story_id)
    seen: set[int] = set()
    for t in test_ids:
        for m in rx.finditer(t.replace("_", "-")):
            i = int(m.group(1))
            if i > n:
                seen.add(i)
    return [f"AC-{story_id}-{i}" for i in sorted(seen)]
