"""Tiêu chí chấp nhận ↔ test: hợp đồng mã ``AC-<story>-<i>``.

Truy vết cũ dừng ở "story phủ FR có test xanh" — tiêu chí 3 không ai kiểm mà
báo cáo vẫn xanh, và người rà soát được bảo "chỉ ra test nào phủ tiêu chí
nào": phán đoán ở chỗ lẽ ra là tra cứu. Giờ mỗi tiêu chí *i* của story có
mã ``AC-<story>-<i>``; mã phải xuất hiện trong **tên** ít nhất một test, và
tên test đọc từ output runner (``harness/testlog``), không từ lời agent.

Khớp nguyên mã: ``AC-S-1`` không khớp ``AC-S-10``; ``_`` và ``-`` coi như
nhau vì tên hàm pytest không chứa gạch ngang (``test_AC_S_1_chuoi_rong``).
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
    """Tiêu chí i → những test mang mã của nó (có thể rỗng)."""
    norm = [(t, t.replace("_", "-")) for t in test_ids]
    out: dict[int, list[str]] = {}
    for i in range(1, n + 1):
        rx = _pattern(ac_code(story_id, i))
        out[i] = [t for t, tn in norm if rx.search(tn)]
    return out


def missing(story_id: str, n: int, test_ids: list[str]) -> list[int]:
    return [i for i, tests in coverage(story_id, n, test_ids).items() if not tests]
