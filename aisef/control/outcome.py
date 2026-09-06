"""Một kiểu kết cục cho mọi cổng.

Trước đây `KindResult` có `ran/ok/skipped/unrunnable`, `Check` có
`passed/skipped` (hai bản, ở `gate` và `deploy`), còn "miễn" là một danh
sách riêng — bốn kết cục bị gộp làm hai ở ba chỗ. Hậu quả đã gặp thật
(lỗi 33/36/37): "chưa cấu hình" hiện như "đạt", "môi trường chưa dựng"
hiện như "test đỏ". Ở đây có **sáu** kết cục, ba câu hỏi, một bảng ký hiệu:

- `blocks`          — chặn cổng (FAILED, UNRUNNABLE)
- `counts_as_done`  — tính là xong (PASSED, WAIVED, NOT_APPLICABLE)
- `must_be_named`   — phải hiện ra, không được im (UNCONFIGURED, UNRUNNABLE)

Bất biến: mọi kết cục không phải PASSED đều có lý do một dòng, và
UNCONFIGURED/UNRUNNABLE không bao giờ mang cùng ký hiệu với PASSED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNRUNNABLE = "unrunnable"            # có lệnh, môi trường chưa dựng — không phải đỏ
    UNCONFIGURED = "unconfigured"        # chưa khai lệnh / chưa cấu hình — không phải đạt
    WAIVED = "waived"                    # người miễn tường minh, có lý do ghi lại
    NOT_APPLICABLE = "not-applicable"    # điều kiện không áp dụng (story không có giao diện)

    @property
    def blocks(self) -> bool:
        return self in (Outcome.FAILED, Outcome.UNRUNNABLE)

    @property
    def counts_as_done(self) -> bool:
        return self in (Outcome.PASSED, Outcome.WAIVED, Outcome.NOT_APPLICABLE)

    @property
    def must_be_named(self) -> bool:
        return self in (Outcome.UNCONFIGURED, Outcome.UNRUNNABLE)

    @property
    def mark(self) -> str:
        return MARK[self]


MARK = {
    Outcome.PASSED: "✅",
    Outcome.FAILED: "✗",
    Outcome.UNRUNNABLE: "⚠",
    Outcome.UNCONFIGURED: "○",
    Outcome.WAIVED: "◇",
    Outcome.NOT_APPLICABLE: "–",
}

DEFAULT_REASON = {
    Outcome.FAILED: "không đạt",
    Outcome.UNRUNNABLE: "không chạy được — môi trường chưa dựng, không phải test đỏ",
    Outcome.UNCONFIGURED: "chưa cấu hình — không tính là đạt",
    Outcome.WAIVED: "miễn tường minh",
    Outcome.NOT_APPLICABLE: "không áp dụng",
}


#: Loại mục cổng (ADR-005 V9, theo Inspect `Score`/TB rubric). Đóng: mục
#: mới phải chọn một — ai chấm mục này? Máy tất định (test/lint/coverage),
#: máy so cấu trúc (phạm vi, tên test, DOM), rà soát bảo mật, model làm giám
#: khảo, hay người. `human` chưa mục nào dùng; giữ tên cho waiver per-check
#: nếu có story thật cần (ADR-005 §3 P2).
CHECK_KINDS = ("deterministic", "structural", "security", "model-judge", "human")


@dataclass
class Check:
    """Một mục của cổng. `outcome` nhận cả bool cho chỗ chỉ có đạt/không:
    `Check("lint", lint.ok)` — còn chỗ nào không phải đạt/không thì phải
    nói rõ là gì, không có `skipped=True` chung chung nữa.

    `kind` và `evidence` là hợp đồng chấm tối thiểu (ADR-005 V9): `kind` một
    trong `CHECK_KINDS`; `evidence` là **con trỏ** — `seq` của sự kiện mục đã
    đọc để kết luận, không chép nội dung (nội dung nằm ở `evidence/*.jsonl`).
    Rỗng nghĩa là mục suy từ tham số truyền vào (`gate.evaluate` kwargs) chứ
    không từ sự kiện — và chỗ gọi phải nói rỗng. Không có `blocking`: chặn
    hay không là việc của `Outcome.blocks`, chưa mục nào advisory (YAGNI)."""

    name: str
    outcome: Outcome
    detail: str = ""
    kind: str = ""
    evidence: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.outcome, bool):
            self.outcome = Outcome.PASSED if self.outcome else Outcome.FAILED
        # Bất biến: kết cục không phải PASSED luôn mang lý do — điền ngay ở
        # đây để `detail` (JSON, feedback, báo cáo) và `line()` cùng nói một điều.
        if not self.detail and self.outcome is not Outcome.PASSED:
            self.detail = DEFAULT_REASON.get(self.outcome, "")

    @property
    def passed(self) -> bool:
        """Không chặn cổng. Không đồng nghĩa "đạt" — xem `outcome`."""
        return not self.outcome.blocks

    @property
    def skipped(self) -> bool:
        return self.outcome in (Outcome.UNCONFIGURED, Outcome.NOT_APPLICABLE, Outcome.WAIVED)

    def line(self) -> str:
        return f"  {self.outcome.mark} {self.name}" + (f" — {self.detail}" if self.detail else "")

    def as_dict(self) -> dict:
        return {"name": self.name, "outcome": self.outcome.value, "passed": self.passed,
                "skipped": self.skipped, "detail": self.detail,
                "kind": self.kind, "evidence": list(self.evidence)}
