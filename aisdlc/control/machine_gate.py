"""Cổng máy — kiểm những gì kiểm được bằng code, trước khi mời người xem.

Chạy trước cổng người có chủ đích: bắt người đọc một tài liệu có chu trình
phụ thuộc hay có yêu cầu không ai kiểm chứng được là phí thời gian của
người, và là loại lỗi máy phát hiện tốt hơn người.

Phân biệt hai mức, vì hai mức cần hành động khác nhau:

* **Lỗi** chặn — tài liệu sai đến mức bước sau không dùng được.
* **Cảnh báo** không chặn nhưng đi vào phần tóm tắt của cổng người, để
  người quyết định có chấp nhận hay không. Câu hỏi mở chưa trả lời là ví
  dụ điển hình: nó hợp lệ, nhưng người duyệt cần biết.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import DEFAULTS, Config
from .normalize import PRD
from .scheduler import CycleError, Story, build_waves


@dataclass
class GateResult:
    name: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        head = f"{self.name}: {'ĐẠT' if self.passed else 'KHÔNG ĐẠT'}"
        lines = [head]
        for e in self.errors:
            lines.append(f"  ✗ {e}")
        for w in self.warnings:
            lines.append(f"  ⚠️  {w}")
        return "\n".join(lines)


def check_prd(prd: PRD) -> GateResult:
    """Kiểm PRD trước khi mời người duyệt."""
    r = GateResult("cổng máy: prd")

    if not prd.functional():
        r.errors.append("không có yêu cầu chức năng nào")
        return r

    untestable = prd.untestable()
    if untestable:
        ids = ", ".join(x.id for x in untestable)
        r.errors.append(
            f"yêu cầu không có tiêu chí kiểm chứng được: {ids} — "
            f"không nghiệm thu được thì không triển khai được"
        )

    empty_title = [x.id for x in prd.requirements if not x.title.strip()]
    if empty_title:
        r.errors.append(f"yêu cầu thiếu tiêu đề: {', '.join(empty_title)}")

    blocked = prd.blocked_ids()
    if blocked:
        r.warnings.append(
            f"{len(blocked)} yêu cầu đang bị câu hỏi mở chặn "
            f"({', '.join(sorted(blocked))}) — không đưa vào story trước khi chốt"
        )

    unresolved = [q.id for q in prd.open_questions]
    if unresolved:
        r.warnings.append(
            f"{len(unresolved)} câu hỏi mở cần người quyết: {', '.join(unresolved)}"
        )

    if prd.assumptions:
        r.warnings.append(f"{len(prd.assumptions)} giả định được ghi lại — xem lại khi duyệt")

    if not prd.non_functional():
        r.warnings.append("không có yêu cầu phi chức năng nào — hiếm khi đúng")

    return r


def check_stories(
    stories: list[Story],
    prd: PRD | None = None,
    *,
    config: Config | None = None,
    story_fr_map: dict[str, list[str]] | None = None,
    story_ac_count: dict[str, int] | None = None,
) -> GateResult:
    """Kiểm tập story trước khi bắt đầu viết code."""
    r = GateResult("cổng máy: stories")
    cfg = config or Config(dict(DEFAULTS))

    if not stories:
        r.errors.append("không có story nào")
        return r

    ids = [s.id for s in stories]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        r.errors.append(f"story trùng mã: {', '.join(dupes)}")

    no_scope = [s.id for s in stories if not s.write_scope]
    if no_scope:
        r.errors.append(
            f"story chưa khai write_scope: {', '.join(no_scope)} — "
            f"không xếp lịch song song được, và guard sẽ chặn mọi thao tác ghi"
        )

    # Chu trình phụ thuộc: dùng chính bộ lập lịch, để cổng và lúc chạy
    # không thể bất đồng về việc thế nào là hợp lệ.
    try:
        build_waves(stories)
    except CycleError as e:
        r.errors.append(f"phụ thuộc vòng: {e}")
    except ValueError as e:
        r.errors.append(str(e))

    max_ac = cfg["story.max_acceptance_criteria"]
    for sid, n in (story_ac_count or {}).items():
        if n > max_ac:
            r.errors.append(
                f"{sid} có {n} tiêu chí chấp nhận, vượt ngưỡng {max_ac} — chẻ nhỏ ra, "
                f"story quá lớn sẽ tràn ngữ cảnh trong một phiên"
            )

    max_paths = cfg["story.max_write_scope_paths"]
    too_wide = [s.id for s in stories if len(s.write_scope) > max_paths]
    if too_wide:
        r.errors.append(
            f"story chạm quá nhiều nơi (> {max_paths} đường dẫn): {', '.join(too_wide)}"
        )

    if prd is not None:
        covered: set[str] = set()
        for fr_ids in (story_fr_map or {}).values():
            covered |= set(fr_ids)

        blocked = prd.blocked_ids()
        expected = {x.id for x in prd.functional()} - blocked
        missing = sorted(expected - covered, key=lambda s: int(s.split("-")[1]))
        if missing:
            r.errors.append(
                f"yêu cầu chưa story nào phủ: {', '.join(missing)} — "
                f"mất truy vết từ PRD tới code"
            )

        touched_blocked = sorted(covered & blocked)
        if touched_blocked:
            r.errors.append(
                f"story đụng vào yêu cầu đang bị câu hỏi mở chặn: "
                f"{', '.join(touched_blocked)}"
            )

        unknown = sorted(covered - {x.id for x in prd.requirements})
        if unknown:
            r.warnings.append(f"story tham chiếu mã không có trong PRD: {', '.join(unknown)}")

    return r


def check_all(results: list[GateResult]) -> GateResult:
    """Gộp nhiều kết quả cổng thành một."""
    combined = GateResult("cổng máy")
    for r in results:
        combined.errors.extend(f"[{r.name}] {e}" for e in r.errors)
        combined.warnings.extend(f"[{r.name}] {w}" for w in r.warnings)
    return combined
