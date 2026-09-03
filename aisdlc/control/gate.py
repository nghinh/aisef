"""Cổng story — điều kiện để một story được coi là xong.

Cổng đọc **bằng chứng**, không đọc lời agent kể. Agent nào cũng kết thúc
bằng câu "đã hoàn thành"; câu đó không mang thông tin. Thứ mang thông tin
là: có lần chạy test nào không, nó xanh hay đỏ, chạy trước hay sau lần sửa
cuối, cây git có nằm trong phạm vi không, màn hình thật có đủ component đã
hứa không.

Năm điều kiện, mỗi điều kiện trả lời được bằng dữ liệu có sẵn:

1. test xanh, và xanh **sau** lần sửa file cuối cùng;
2. lint sạch;
3. thay đổi nằm trong ``write_scope``;
4. màn hình khớp hợp đồng thị giác (chỉ story có giao diện);
5. rà soát độc lập không còn mục chặn;
6. không có test giả — test không khẳng định gì làm điều kiện 1 rỗng nghĩa.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..harness.guardrails import check_completion, check_diff_scope
from ..harness.observe import MOCKUP_MAP, TOOL_RUN, Evidence


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    #: Điều kiện không áp dụng cho story này (ví dụ story không có giao diện).
    skipped: bool = False

    def line(self) -> str:
        if self.skipped:
            return f"  ○ {self.name} — {self.detail or 'không áp dụng'}"
        mark = "✅" if self.passed else "✗"
        return f"  {mark} {self.name}" + (f" — {self.detail}" if self.detail else "")


@dataclass
class StoryGate:
    story_id: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed or c.skipped for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not (c.passed or c.skipped)]

    def summary(self) -> str:
        head = f"cổng story {self.story_id}: {'ĐẠT' if self.passed else 'KHÔNG ĐẠT'}"
        return "\n".join([head, *(c.line() for c in self.checks)])

    def feedback(self) -> str:
        """Phần đưa lại cho agent ở lượt thử tiếp theo."""
        return "\n".join(f"- {c.name}: {c.detail}" for c in self.failures)


def evaluate(
    story_id: str,
    evidence: Evidence,
    *,
    changed: list[str],
    write_scope: list[str],
    screens: list[str],
    review_blocking: list[str] | None = None,
    review_ran: bool = True,
) -> StoryGate:
    """Chấm một story từ bằng chứng đã ghi."""
    gate = StoryGate(story_id=story_id)

    completion = check_completion(evidence)
    gate.checks.append(Check("test", completion.allowed, completion.reason.split("\n")[0]))

    lint = evidence.last(TOOL_RUN, "lint")
    if lint is None:
        gate.checks.append(Check("lint", False, "chưa chạy lint lần nào"))
    elif lint.detail.get("skipped"):
        gate.checks.append(
            Check("lint", True, str(lint.detail["skipped"]), skipped=True)
        )
    else:
        gate.checks.append(
            Check("lint", lint.ok, "" if lint.ok else str(lint.detail.get("tail", ""))[:300])
        )

    scope = check_diff_scope(changed, write_scope)
    gate.checks.append(Check("phạm vi ghi", scope.allowed, scope.reason))

    if not screens:
        gate.checks.append(Check("map mockup", True, "story không có giao diện", skipped=True))
    else:
        maps = {e.name: e for e in evidence.of(MOCKUP_MAP)}
        missing_runs = [s for s in screens if s not in maps]
        if missing_runs:
            gate.checks.append(
                Check("map mockup", False, f"chưa đối chiếu: {', '.join(missing_runs)}")
            )
        else:
            failed = [s for s in screens if not maps[s].ok]
            detail = ""
            if failed:
                first = maps[failed[0]].detail
                detail = (
                    f"{failed[0]} thiếu: "
                    + ", ".join(first.get("missing", []) + first.get("missing_data_roles", []))
                )
            gate.checks.append(Check("map mockup", not failed, detail))

    fake = evidence.last(TOOL_RUN, "qa:fake-tests")
    if fake is not None and not fake.ok:
        files = fake.detail.get("files") or []
        gate.checks.append(
            Check("test thật", False,
                  f"{len(files)} test không có khẳng định nào: {', '.join(files[:3])}")
        )
    else:
        gate.checks.append(Check("test thật", True))

    if not review_ran:
        gate.checks.append(Check("rà soát", False, "chưa rà soát độc lập"))
    else:
        blocking = review_blocking or []
        gate.checks.append(
            Check(
                "rà soát",
                not blocking,
                "" if not blocking else f"{len(blocking)} mục chặn: {blocking[0][:200]}",
            )
        )

    return gate
