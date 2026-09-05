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
from .outcome import Check, Outcome
from .security import DEFAULT_BLOCKING
from ..harness.observe import MOCKUP_MAP, TOOL_RUN, Evidence


@dataclass
class StoryGate:
    story_id: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(c.outcome.blocks for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.outcome.blocks]

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
    contract: list[str] | None = None,
    review_blocking: list[str] | None = None,
    review_ran: bool = True,
    security=None,
    block_severities=None,
    guard_expected: bool = False,
) -> StoryGate:
    """Chấm một story từ bằng chứng đã ghi."""
    gate = StoryGate(story_id=story_id)

    # Hook sinh ra ≠ hook chạy. Claude Code chỉ đọc `.claude/settings.json`
    # của cây nó đứng; worktree không có thư mục ấy (dự án không commit) thì
    # story chạy với zero guard — và bằng chứng trông y hệt agent ngoan, vì
    # không có gì để ghi. Nay guard tự ghi `GUARD_BLOCK`/`FILE_CHANGE`, nên
    # "guard chưa từng đánh giá một thao tác ghi nào" là điều đo được.
    if not guard_expected:
        gate.checks.append(Check(
            "guard có chạy", Outcome.NOT_APPLICABLE,
            "chưa biên dịch hook cho client này — không kỳ vọng",
        ))
    else:
        gate.checks.append(Check(
            "guard có chạy", evidence.guard_reached,
            "" if evidence.guard_reached else (
                "guard chưa đánh giá thao tác ghi nào trong phiên — hook không "
                "tới được worktree? (.claude/ chưa commit, hoặc --settings không "
                "được truyền). Story không ghi gì cũng rơi vào đây, và đó là đúng."
            ),
        ))

    completion = check_completion(evidence)
    gate.checks.append(Check("test", completion.allowed, completion.reason.split("\n")[0]))

    lint = evidence.last(TOOL_RUN, "lint")
    if lint is None:
        gate.checks.append(Check("lint", False, "chưa chạy lint lần nào"))
    elif lint.detail.get("skipped"):
        gate.checks.append(
            Check("lint", Outcome.UNCONFIGURED, str(lint.detail["skipped"]))
        )
    else:
        gate.checks.append(
            Check("lint", lint.ok, "" if lint.ok else str(lint.detail.get("tail", ""))[:300])
        )

    scope = check_diff_scope(changed, write_scope)
    gate.checks.append(Check("phạm vi ghi", scope.allowed, scope.reason))

    if not screens:
        gate.checks.append(Check("map mockup", Outcome.NOT_APPLICABLE, "story không có giao diện"))
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

    # Hợp đồng kiểm định của story. Loại chưa cấu hình được ghi là **chưa
    # cấu hình**, không phải đạt — nó chặn ở cổng trước triển khai, và ở
    # đây nó phải hiện ra để người đọc biết chỗ trống nằm đâu.
    for kind in contract or []:
        if kind in ("unit", "mockup-map", "security"):
            continue  # đã có mục riêng ở trên
        ran = evidence.last(TOOL_RUN, kind)
        if ran is None:
            gate.checks.append(Check(kind, Outcome.UNCONFIGURED))
        elif ran.detail.get("skipped"):
            gate.checks.append(Check(kind, Outcome.UNCONFIGURED, str(ran.detail["skipped"])))
        else:
            gate.checks.append(Check(
                kind, ran.ok, "" if ran.ok else str(ran.detail.get("tail", ""))[:200]
            ))

    # Bảo mật: chưa chạy thì **chưa cấu hình**, không phải đạt. Bỏ mục
    # này khi không có kết quả sẽ làm cổng im lặng ở đúng chỗ nó phải
    # nói to nhất.
    if security is None:
        gate.checks.append(
            Check("bảo mật", Outcome.UNCONFIGURED, "chưa cấu hình rà soát bảo mật")
        )
    elif security.error:
        gate.checks.append(Check("bảo mật", False, security.error))
    else:
        chan = security.blocking(block_severities or DEFAULT_BLOCKING)
        gate.checks.append(Check(
            "bảo mật",
            not chan,
            "" if not chan else f"{len(chan)} mục chặn: {chan[0].line()[:200]}",
        ))

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
