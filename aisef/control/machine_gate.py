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

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEFAULTS, Config
from .normalize import PRD, is_lockfile
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

    # Kế hoạch tuyến tính hoàn toàn: mỗi story một đợt. Có thể đúng —
    # nhưng cũng là dấu hiệu người lập kế hoạch xâu chuỗi theo thói quen
    # thay vì theo phụ thuộc thật, và khi ấy toàn bộ khả năng chạy song
    # song thành không với tới được. Cảnh báo chứ không chặn: đây là fact
    # để người đọc hỏi lại, không phải kết luận máy tự tin.
    # Epic nào bị xâu thành chuỗi hoàn toàn — mỗi story một đợt. Có thể
    # đúng, nhưng cũng là dấu hiệu người lập kế hoạch xâu theo thói quen
    # thay vì theo phụ thuộc thật, và khi ấy toàn bộ khả năng chạy song
    # song thành không với tới được.
    #
    # Kiểm **theo từng epic**, vì đó là đơn vị mà bộ điều phối chia đợt:
    # epic chạy tuần tự với nhau, story chạy song song trong một epic.
    # Tính trên cả tập thì con số ra khác và không nói lên điều gì.
    #
    # Cảnh báo chứ không chặn: đây là fact để người đọc hỏi lại, không
    # phải kết luận máy tự tin.
    if not r.errors:
        chuoi = []
        for epic in sorted({s.epic_id for s in stories if s.epic_id}):
            trong = [s for s in stories if s.epic_id == epic]
            if len(trong) < 3:
                continue
            try:
                dot = build_waves(trong)
            except (CycleError, ValueError, KeyError):
                continue
            if len(dot) == len(trong):
                chuoi.append(f"{epic} ({len(trong)} story)")
        if chuoi:
            r.warnings.append(
                "epic bị xâu thành chuỗi hoàn toàn, không story nào chạy song "
                f"song được: {', '.join(chuoi)} — xem lại `depends_on`, chỉ khai "
                "khi story sau thật sự cần **kết quả** của story trước"
            )

    max_paths = cfg["story.max_write_scope_paths"]
    too_wide = [
        s.id
        for s in stories
        if len([p for p in s.write_scope if not is_lockfile(p)]) > max_paths
    ]
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


def check_design_contract(
    contract,
    experience,
    stories: list | None = None,
) -> GateResult:
    """Kiểm hợp đồng thị giác trước khi mời người duyệt mockup.

    Ba câu hỏi, đều có đáp án tất định:

    1. Mọi màn hình trong EXPERIENCE.md có mockup dựng được không?
    2. Còn chỗ nào mockup tự khai là **chưa chốt** không?
    3. Story giao diện có trỏ tới màn hình **có thật** không?

    Câu 3 quan trọng vì lúc viết code, agent nạp hợp đồng theo ``screen_id``
    lấy từ story. Mã sai thì nó nạp rỗng và dựng giao diện theo phán đoán —
    đúng thứ bước map mockup sinh ra để ngăn.
    """
    r = GateResult("cổng máy: mockup")

    if not experience.screens:
        r.errors.append("EXPERIENCE.md không liệt kê màn hình nào")
        return r

    missing = [s.id for s in experience.screens if contract.by_id(s.id) is None]
    if missing:
        r.errors.append(f"màn hình chưa có trong hợp đồng: {', '.join(missing)}")

    unresolved: list[tuple[str, str]] = []
    for screen in contract.screens:
        if screen.error:
            r.errors.append(f"{screen.id}: {screen.error}")
            continue
        unresolved += [(screen.id, item) for item in screen.unresolved]
        if screen.whole_page and screen.duplicates:
            # Đo 2026-09-05 (e9 note-editor): mockup bỏ quên `data-state`, hợp
            # đồng ôm cả trang gồm 4 trạng thái → story không thể qua bước map
            # mockup, đốt $28 qua 4 lượt. Chặn ở đây rẻ hơn nhiều.
            r.errors.append(
                f"{screen.id}: mockup không đánh dấu `data-state=\"primary\"` nên hợp đồng "
                f"lấy cả trang — {len(screen.components)} component, {screen.duplicates} chỗ "
                f"trùng, tức nhiều trạng thái dựng cạnh nhau. Ứng dụng thật ở một thời điểm "
                f"chỉ ở một trạng thái nên bước map mockup sẽ không bao giờ khớp. Đánh dấu "
                f"trạng thái theo skill aisef-mockup-html (mục 7) rồi chạy `aisef mockup` "
                f"(không --force: chỉ trích lại hợp đồng)"
            )
        if not screen.route:
            r.errors.append(
                f"{screen.id}: mockup không khai route (thẻ meta aisef-route) — "
                "không đối chiếu được với ứng dụng thật"
            )
        else:
            declared = experience.by_id(screen.id)
            if declared is not None and declared.route and declared.route != screen.route:
                # Không chặn: một trong hai đúng, và người duyệt biết cái nào.
                r.warnings.append(
                    f"{screen.id}: route mockup ({screen.route}) khác route trong "
                    f"EXPERIENCE.md ({declared.route})"
                )
        if not screen.components:
            r.warnings.append(f"{screen.id}: mockup không có component nào kiểm được")

    if unresolved:
        # Gom theo **câu hỏi**, không theo chỗ đánh dấu. 52 chỗ chưa chốt
        # trên 5 màn thường quy về 4–5 câu hỏi; liệt kê từng chỗ thì người
        # duyệt thấy một bức tường, còn gom lại thì thấy đúng việc phải làm.
        by_question: dict[str, int] = {}
        for _, item in unresolved:
            m = re.search(r"\b(?:UX-)?OQ-\d+\b", item)
            key = m.group(0) if m else "không gắn mã câu hỏi"
            by_question[key] = by_question.get(key, 0) + 1
        listed = " · ".join(
            f"{q} ({n} chỗ)" for q, n in sorted(by_question.items(), key=lambda x: -x[1])
        )
        r.errors.append(
            f"mockup còn {len(unresolved)} chỗ chưa chốt trên "
            f"{len({s for s, _ in unresolved})} màn hình, quy về "
            f"{len(by_question)} câu hỏi: {listed}. Trả lời chúng trong PRD/UX "
            f"rồi dựng lại mockup — dựng code theo màn hình chưa chốt tốn gấp đôi."
        )
        # Chỗ không dẫn mã câu hỏi thì người duyệt không tra được nó thuộc
        # về đâu; nêu vài ví dụ để họ biết đang nhìn cái gì.
        loose = [item for _, item in unresolved if not re.search(r"\b(?:UX-)?OQ-\d+\b", item)]
        for item in loose[:3]:
            r.warnings.append(f"chưa chốt, không dẫn mã câu hỏi: {item[:140]}")

    extra = [s.id for s in contract.screens if experience.by_id(s.id) is None]
    if extra:
        r.warnings.append(f"hợp đồng có màn hình không nằm trong EXPERIENCE.md: {', '.join(extra)}")

    if stories is not None:
        known = set(contract.ids) | set(experience.ids)
        for story in stories:
            unknown = [sid for sid in getattr(story, "screens", []) if sid not in known]
            if unknown:
                r.errors.append(
                    f"{story.id}: trỏ tới màn hình không có thật: {', '.join(unknown)}"
                )
        used = {sid for st in stories for sid in getattr(st, "screens", [])}
        orphan = [s.id for s in experience.screens if s.id not in used]
        if orphan:
            r.warnings.append(f"màn hình chưa story nào dựng: {', '.join(orphan)}")

    return r


def check_all(results: list[GateResult]) -> GateResult:
    """Gộp nhiều kết quả cổng thành một."""
    combined = GateResult("cổng máy")
    for r in results:
        combined.errors.extend(f"[{r.name}] {e}" for e in r.errors)
        combined.warnings.extend(f"[{r.name}] {w}" for w in r.warnings)
    return combined
