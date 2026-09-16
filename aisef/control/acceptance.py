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
    r"""Mã của **đúng** story này ở tên phép thử: `AC-<story>-<i>`.

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


def contract_fingerprint(criteria) -> str:
    """Hash of the acceptance criteria — the **story epoch**: what the story's
    tests must prove. Written to the `story:contract` note (run.py) and onto
    the story baseline (D-033), so a baseline never outlives the contract it
    was captured for. Criteria only, not the whole card: harness-added scope
    paths move with framework upgrades while saying nothing about the story."""
    import hashlib
    text = "\n".join(str(c).strip() for c in (criteria or []))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def digest(text: str) -> str:
    """Vân tay nội dung của một tiêu chí — danh tính bền của nó.

    Chuẩn hoá khoảng trắng trước khi băm: thẻ story được **sinh lại** từ
    `epics.md` mỗi lần `aisef plan` chạy, nên ngắt dòng đổi mà nghĩa không đổi
    là chuyện thường; báo trượt vì một lần gói dòng là báo động giả, và một cổng
    hay báo động giả thì bị bỏ qua.
    """
    import hashlib

    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


def identities(story_id: str, criteria: list[str]) -> dict[str, str]:
    """Mã vị trí -> vân tay nội dung. Cặp `(mã, vân tay)` là danh tính bền."""
    return {ac_code(story_id, i): digest(str(c)) for i, c in enumerate(criteria, 1)}


def drift(before: dict[str, str], now: dict[str, str]) -> list[str]:
    """Mã có ở **cả hai** lần mà vân tay đã đổi — tức mã ấy giờ mang tiêu chí khác.

    Vì sao đếm là không đủ (lỗi 159, nửa sau): `orphans()` bắt được ca **rút**
    tiêu chí vì số lượng giảm để lại mã mồ côi. **Đảo thứ tự** hai tiêu chí
    không đổi số lượng và không để lại mã mồ côi nào, mà vẫn tráo bằng chứng
    của hai tiêu chí cho nhau. Chỉ nội dung trả lời được câu ấy.

    Mã **mới** (chỉ có ở `now`) không phải trượt — đó là tiêu chí thêm vào, và
    `missing()` mới là câu hỏi đúng cho nó. Mã **mất** (chỉ có ở `before`) cũng
    không phải trượt — `orphans()` đã nói.
    """
    return sorted(k for k in before.keys() & now.keys() if before[k] != now[k])


def overloaded(story_id: str, test_ids: list[str]) -> dict[str, list[str]]:
    """Phép thử -> các mã của story này mà **tên nó** mang cùng lúc (≥2).

    Một phép thử tên `AC-S-1 and AC-S-2: …` thoả `criteria have tests` cho **cả
    hai** tiêu chí trong khi chứng minh một hành vi: hai tiêu chí, một bằng
    chứng. Đó là gán nhập nhằng, và nó là một đường đạt-sai của một mục cấu
    trúc y như mã tụt bậc.

    Ngược lại, **một** tiêu chí có nhiều phép thử là chuyện bình thường và tốt.
    """
    rx = _codes_of(story_id)
    out: dict[str, list[str]] = {}
    for t in test_ids:
        found = sorted({int(m.group(1)) for m in rx.finditer(t.replace("_", "-"))})
        if len(found) > 1:
            out[t] = [ac_code(story_id, i) for i in found]
    return out
