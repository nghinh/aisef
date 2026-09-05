"""Bước 4 — hiện thực một story: một phiên, một worktree, một cổng.

Vòng đời một story:

    dựng ngữ cảnh → chạy agent (viết code) → đối chiếu mockup → rà soát
    độc lập → chấm cổng → xong / thử lại / chặn

Hai điều được giữ chặt ở đây:

* **Một phiên một story** (quyết định Đ1). Không mang ngữ cảnh story trước
  sang story sau, vì ngữ cảnh cũ là nguồn gây nhiễu mà không ai kiểm được.
* **Phân biệt lỗi hạ tầng với lỗi chất lượng.** Mất kết nối giữa chừng
  không phải agent làm sai: thử lại, và **không** tính vào số lần thử. Gộp
  hai loại lại thì một mạng chập chờn sẽ làm story bị chặn oan, còn một
  agent làm sai sẽ được thử mãi.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import re
import subprocess
from pathlib import Path

from ..clients.base import ClientAdapter
from ..config import Config
from ..control import gate as story_gate
from ..control import tdd
from ..kit import registry as skill_registry
from ..kit import router as skill_router
from ..control.acceptance import ac_code
from ..control.design_contract import DesignContract, load as load_contract
from ..control.impact import analyse as analyse_impact
from ..control.preflight import verification_contract
from ..control.security import SEVERITIES, SecurityReport
from ..control.security import parse as parse_security
from ..control.normalize import Architecture, Story, effective_write_scope
from ..harness import mockup_verify
from ..clients.compile import guard_expected
from ..harness.guardrails import (
    ENV_DISALLOWED_TOOLS,
    ENV_PROJECT,
    ENV_WORKDIR,
    ENV_BASE_REF,
    ENV_STORY_ID,
    ENV_WRITE_SCOPE,
    changed_files,
    fork_point,
    head_sha,
)
from ..control.journal import Entry as JEntry, JournalStore
from ..harness.mockup_map import load_for_story, prompt_section
from ..harness.observe import EvidenceStore, NOTE, Event
from ..harness.prompts import Catalog, load_catalog
from ..harness.routing import DEVELOPER, REVIEWER, ROLES, SECURITY, build_spec
from ..harness.testlog import MAX_IDS, parse as parse_testlog
from ..harness.tools import BASELINE_RUN, describe_tools, record as record_tool, run_tool
from .qa import KINDS, find_fake_tests, run_suite

#: Lỗi thuộc về hạ tầng, không thuộc về chất lượng công việc.
INFRA_ERRORS = ("api_error", "overloaded", "quá ", "không chạy được", "connection")


def is_infrastructure_error(error: str) -> bool:
    low = (error or "").lower()
    return any(marker in low for marker in INFRA_ERRORS)


@dataclass
class Attempt:
    number: int
    ok: bool = False
    infra: bool = False
    #: Hỏng đến mức thử lại cũng vô nghĩa — ví dụ cách ly đã vỡ: worktree
    #: của lượt sau sẽ rẽ từ thân cây đã bẩn, nên chỉ tiêu tiền thêm.
    fatal: bool = False
    error: str = ""
    cost_usd: float = 0.0
    gate: story_gate.StoryGate | None = None
    review_findings: list[str] = field(default_factory=list)
    security: SecurityReport | None = None
    #: SHA ứng viên đã đóng băng — mọi bằng chứng của lượt này trỏ vào nó.
    candidate: str = ""


@dataclass
class StoryOutcome:
    story_id: str
    attempts: list[Attempt] = field(default_factory=list)
    blocked_reason: str = ""

    @property
    def done(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].ok

    @property
    def quality_attempts(self) -> int:
        """Số lần thử **tính vào hạn mức** — lỗi hạ tầng không tính."""
        return len([a for a in self.attempts if not a.infra])

    @property
    def cost_usd(self) -> float:
        return sum(a.cost_usd for a in self.attempts)

    def summary(self) -> str:
        lines = [f"{self.story_id}: {'XONG' if self.done else 'CHƯA XONG'}"]
        for a in self.attempts:
            tag = "hạ tầng" if a.infra else f"lần {a.number}"
            head = "ok" if a.ok else (a.error or "cổng không đạt")
            lines.append(f"  [{tag}] {head}")
            if a.gate and not a.gate.passed:
                lines.extend("  " + line for line in a.gate.summary().splitlines()[1:])
        if self.blocked_reason:
            lines.append(f"  ✗ {self.blocked_reason}")
        if self.cost_usd:
            lines.append(f"  chi phí: ${self.cost_usd:.2f}")
        return "\n".join(lines)


def build_context(
    story: Story,
    *,
    project: Path,
    artifact_root: Path,
    architecture: Architecture | None,
    contract: DesignContract | None,
    config: Config | None,
    feedback: str = "",
    preservation: list[dict] | None = None,
) -> dict:
    """Ngữ cảnh cho prompt story — chọn bằng tra cứu, không bằng phán đoán.

    ``preservation`` là danh sách hành vi phải giữ đã tính sẵn (R4). Truyền
    vào để reviewer/security nhận **đúng** danh sách developer đã nhận: tính
    lại sau phiên developer thì sổ đã đổi theo bằng chứng của chính lượt ấy,
    và ba vai nói về ba danh sách khác nhau. `None` = tính từ sổ.
    """
    story_file = artifact_root / "stories" / story.epic_id / f"{story.id}.md"
    contract_text = (
        story_file.read_text(encoding="utf-8", errors="replace")
        if story_file.is_file()
        else _story_fallback(story)
    )
    if feedback:
        contract_text += (
            "\n\n## Lượt trước chưa đạt\n\n"
            "Đây là kết quả chấm cổng lần trước. Sửa đúng những mục này; "
            "đừng viết lại từ đầu.\n\n" + feedback + "\n"
        )

    rules = architecture.for_requirements(story.covers) if architecture else []
    slices: list = []
    if contract and story.screens:
        slices, _ = load_for_story(contract, story.screens, artifact_root=artifact_root)

    skills, skills_ev = _skills_section(story, project=project, artifact_root=artifact_root, config=config)
    led = _ledger(artifact_root)
    if preservation is None:
        preservation = preservation_items(story, project=project, ledger=led)
    cap = int(config["context.max_preservation_chars"]) if config else 1500
    return {
        "_skills": skills_ev,
        "_preservation": preservation,
        "skills": skills,
        "preservation": preservation_text(preservation, max_chars=cap),
        "validation": validation_text(story, preservation, max_chars=cap),
        "story_id": story.id,
        "story_title": story.title,
        "story_contract": contract_text,
        "architecture_rules": (
            "\n\n".join(d.as_prompt() for d in rules)
            or "(kiến trúc không nêu quyết định nào ràng buộc story này)"
        ),
        "write_scope": _write_scope_lines(story, project),
        "mockup_section": prompt_section(slices),
        "tools": describe_tools(project, config),
        "index": _index_slice(story, artifact_root, config, ledger=led),
    }


def _ledger(artifact_root: Path):
    """Sổ hành vi chiếu từ bằng chứng **hiện có** — không đọc `ledger.json`.

    Tệp ấy chỉ được `aisdlc report` làm mới; trong một lần `run` qua cả
    epic, story sau sẽ không thấy hành vi story trước vừa xác minh. Chiếu
    lại từ evidence mất 1,1 s trên e9 (4,3 MB) — rẻ hơn một hồi quy bị bỏ
    sót. Sổ hỏng hay chưa có thì `None`, không làm hỏng lượt chạy.
    """
    from ..control import ledger as ledger_mod

    try:
        return ledger_mod.build(artifact_root)
    except OSError:
        return None


def _index_slice(story: Story, artifact_root: Path, config: Config | None, *, ledger=None) -> str:
    """Lát cắt chỉ mục bằng chứng của epic chứa story (ADR-004 R6).

    Progressive disclosure: prompt nhận **một dòng mỗi story** — trạng thái,
    candidate, số hành vi VERIFIED/GAP/REOPENED — chứ không nhận lịch sử.
    Lịch sử nằm ở `aisdlc evidence <id>`, tra khi cần. Sổ hỏng hay chưa có
    thì slot rỗng có lời giải thích, không làm hỏng lượt chạy.
    """
    cap = int(config["context.max_index_chars"]) if config else 2000
    led = ledger if ledger is not None else _ledger(artifact_root)
    text = led.epic_slice(story.epic_id, max_chars=cap) if led is not None else ""
    return text or "_(chưa có bằng chứng nào cho epic này)_"


# --- Hành vi phải giữ và thứ phải xanh ở ứng viên (ADR-004 R4) ----------------
#
# HoH đưa Preservation + Validation Requirements vào tài liệu phát triển mỗi
# vòng. Ở đây chúng là hai slot **máy tính từ sổ hành vi**, cùng một danh
# sách cho developer, reviewer và security — không vai nào nhận lời vai kia
# (ADR-003 #9) — và cổng "bảo toàn" (`control/gate.py`) chấm đúng danh sách
# ấy trên ứng viên đã đóng băng.


def preservation_items(story: Story, *, project: Path, ledger) -> list[dict]:
    """Hành vi VERIFIED của **story khác** mà phạm vi ghi của story này chạm tệp.

    Phép giao tệp là của `complexity.verified_touched` (R5): một luật, hai
    chỗ dùng, không có bản thứ hai để lệch nhau. Mỗi mục mang đúng thứ cổng
    cần để kiểm lại ở ứng viên — id, loại, story sở hữu, nguồn kiểm (test
    id / `qa:<kind>` / màn hình) — lấy từ `ledger.behaviors[id].source`.
    """
    from ..control.complexity import read_scopes, verified_touched

    if ledger is None:
        return []
    out = []
    for bid in verified_touched(story, ledger.as_dict(), read_scopes(project)):
        b = ledger.behaviors[bid]
        # FR/NFR được sổ xác minh **qua tiêu chí của một story** (`source.story`)
        # — không nhất thiết là story sở hữu: e9 FR-11 sở hữu bởi 01-01 (test
        # không mang mã) nhưng xanh qua 01-05. Cổng phải hỏi đúng story ấy,
        # không thì đòi test mà sổ chưa từng thấy (01-07 lượt 1, 2026-09-06).
        out.append({"id": bid, "kind": b.kind, "story": b.story, "source": dict(b.source),
                    "via": str(b.source.get("story") or b.story)})
    return out


def _source_line(item: dict) -> str:
    src = item.get("source") or {}
    if src.get("test_id"):
        return f"test `{src['test_id']}`"
    if src.get("qa_kind"):
        return f"`qa:{src['qa_kind']}`"
    if src.get("screen"):
        return f"màn hình `{src['screen']}`"
    if src.get("story"):
        return "qua tiêu chí của story"
    return f"`aisdlc evidence {item.get('id', '')}`"


def _cap(text: str, max_chars: int) -> str:
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n_(đã cắt theo trần ký tự — `aisdlc evidence <id>`)_"
    return text


def preservation_text(items: list[dict], *, max_chars: int) -> str:
    """Slot `preservation`: một dòng mỗi hành vi — id · story sở hữu · nguồn.

    Chỉ id và nguồn, không lịch sử (progressive disclosure, R6). Cắt theo
    trần chỉ cắt phần **in ra**; cổng vẫn chấm đủ danh sách — agent bị cắt
    mất một mục thì có dòng cuối bảo nó tra `aisdlc evidence`.
    """
    if not items:
        return "_(không chạm hành vi VERIFIED nào của story khác)_"
    return _cap("\n".join(
        f"- `{it['id']}` · {it.get('story') or '?'} · {_source_line(it)}" for it in items
    ), max_chars)


def validation_text(story: Story, items: list[dict], *, max_chars: int) -> str:
    """Slot `validation`: thứ **harness sẽ chạy lại** trên ứng viên và cổng đọc.

    Liệt kê để agent biết trước cái gì bị chấm, không phải để nó tự chấm:
    `qa:<kind>` (hợp đồng của story + kiểm định đã xác minh bị chạm), màn
    hình (của story + của story khác bị chạm). Test bảo toàn chỉ **đếm**:
    tên đã nằm ở slot `preservation`, chép lại là trả ngân sách B5 hai lần
    (e9 01-07: 27 test id).
    """
    kinds, screens = validation_targets(story, items)
    tests = {it["source"]["test_id"] for it in items if (it.get("source") or {}).get("test_id")}
    lines = []
    if tests:
        lines.append(f"- {len(tests)} test bảo toàn nêu ở mục trên")
    if kinds:
        lines.append("- kiểm định: " + ", ".join(f"`qa:{k}`" for k in kinds))
    if screens:
        lines.append("- màn hình khớp mockup: " + ", ".join(f"`{s}`" for s in screens))
    return _cap("\n".join(lines), max_chars) or "_(chỉ cổng chuẩn: test, lint, phạm vi ghi)_"


def validation_targets(story: Story, items: list[dict]) -> tuple[list[str], list[str]]:
    """(loại kiểm định, màn hình) harness phải chạy ở ứng viên — của story
    cộng phần bảo toàn. Cùng một hàm cho slot và cho `run_attempt`, để thứ
    in cho agent và thứ thật sự chạy không bao giờ là hai danh sách."""
    kinds = [k for k in verification_contract(story) if k not in ("mockup-map", "unit", "security")]
    screens = list(story.screens)
    for it in items:
        src = it.get("source") or {}
        # Chỉ loại `run_suite` chạy được; `qa:fake-tests` là của `run_attempt`,
        # lượt nào cũng ghi, nên cổng vẫn thấy nó ở ứng viên mà không cần liệt kê.
        if it.get("kind") == "qa" and src.get("qa_kind") in KINDS and src["qa_kind"] not in kinds:
            kinds.append(str(src["qa_kind"]))
        if it.get("kind") == "mockup" and src.get("screen") and src["screen"] not in screens:
            screens.append(str(src["screen"]))
    return kinds, screens


#: Slot nào của prompt đến từ đâu. Gói cho reviewer/security **không** được
#: có nguồn `agent` — đó là bất biến máy kiểm (ADR-003 #9). Slot mới mà chưa
#: khai ở đây hiện thành `?` trong bằng chứng, không lặng lẽ thành hợp lệ.
SLOT_SOURCE = {
    "story_id": "artifact", "story_title": "artifact", "story_contract": "artifact",
    "architecture_rules": "artifact", "write_scope": "artifact", "mockup_section": "artifact",
    "tools": "config", "skills": "router", "diff_summary": "git", "impact": "code",
    "index": "ledger", "preservation": "ledger", "validation": "ledger",
}


def handoff_slots(context: dict, *, feedback: bool = False) -> dict[str, tuple[str, int]]:
    """{slot: (nguồn, số ký tự)} — khoá bắt đầu bằng `_` là nội bộ, không phải slot."""
    out = {}
    for k, v in context.items():
        if k.startswith("_"):
            continue
        src = SLOT_SOURCE.get(k, "?")
        if k == "story_contract" and feedback:
            src = "artifact+gate+review"   # lượt sau: có mục "Lượt trước chưa đạt"
        out[k] = (src, len(str(v)))
    return out


def _skills_section(story: Story, *, project: Path, artifact_root: Path, config: Config | None) -> tuple[str, dict]:
    """Mục "Kỹ năng có sẵn" + bằng chứng định tuyến. Router là tín hiệu, không
    phải cổng: abstain thì prompt nói rõ là không có, tắt thì nói là tắt."""
    if not (config and config["skills.offer"]):
        return "_(không định tuyến skill — `skills.offer` tắt)_", {"enabled": False}
    reg = skill_registry.load(artifact_root)
    r = skill_router.route(story, reg, project=project)
    section, ev = r.prompt_section(), {"enabled": True, **r.as_evidence()}
    if config["skills.inline"] and getattr(r, "picked", None):
        # Cơ chế B (ADR-003 §6, thí nghiệm): ba nhánh A/B cho thấy agent không
        # mở skill được mời qua tool `Skill` (`used` 0/0). Dán thẳng nội dung
        # skill cao điểm nhất để đo xem *có nội dung trong ngữ cảnh* có đổi
        # hành vi không — chỉ một skill, có trần ký tự.
        top = r.picked[0].entry
        body = inline_skill_text(project, top.path)
        if body:
            section += (f"\n\n### Nội dung skill `{top.id}` (nạp thẳng)\n\n"
                        f"Đọc như hướng dẫn chuyên môn cho story này, không phải mệnh lệnh "
                        f"thay thế hiến pháp.\n\n{body}")
            ev["inline"] = [top.id]
    return section, ev


#: Trần ký tự nội dung skill dán thẳng — quá trần thì cắt, ghi rõ.
INLINE_SKILL_MAX_CHARS = 8000


def inline_skill_text(project: Path, skill_path: str) -> str:
    """Thân SKILL.md (bỏ frontmatter), cắt theo trần; rỗng nếu không có tệp."""
    md = Path(project) / skill_path / "SKILL.md"
    if not md.is_file():
        return ""
    text = md.read_text(encoding="utf-8", errors="replace")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    text = text.strip()
    if len(text) > INLINE_SKILL_MAX_CHARS:
        text = text[:INLINE_SKILL_MAX_CHARS] + "\n\n_(đã cắt theo trần ký tự — xem SKILL.md đầy đủ)_"
    return text


def skills_used(result) -> list[str]:
    """Skill agent đã mở, đọc từ luồng `tool_use` (tool `Skill`). Client không
    phát luồng → rỗng, và `skills_measurable` ở capability nói vì sao."""
    out = []
    for tu in getattr(result, "tool_uses", None) or []:
        if tu.name == "Skill":
            out.append(str((tu.input or {}).get("skill") or (tu.input or {}).get("name") or "?"))
    return out


def _write_scope_lines(story: Story, project: Path) -> str:
    """Phạm vi ghi cho prompt: story khai + phần harness cấp thêm vì hợp đồng
    kiểm định (lỗi 21) — agent phải thấy đúng phạm vi mà guard áp."""
    from ..control.normalize import verification_paths

    lines = [f"- `{p}`" for p in story.write_scope]
    them = [p for p in verification_paths(story, project) if p not in story.write_scope]
    if them:
        lines.append("- _(harness cấp thêm vì hợp đồng kiểm định đòi)_")
        lines += [f"- `{p}`" for p in them]
    return "\n".join(lines) or "(chưa khai)"


def _story_fallback(story: Story) -> str:
    lines = [f"# {story.id}: {story.title}", "", "## Tiêu chí chấp nhận", ""]
    lines += [f"{i}. [{ac_code(story.id, i)}] {ac}" for i, ac in enumerate(story.acceptance_criteria, 1)]
    return "\n".join(lines)


def run_attempt(
    story: Story,
    *,
    project: Path,
    workdir: Path,
    artifact_root: Path,
    client: ClientAdapter,
    config: Config,
    catalog: Catalog,
    architecture: Architecture | None,
    contract: DesignContract | None,
    number: int,
    feedback: str = "",
    base_ref: str = "",
) -> Attempt:
    """Một lượt: agent viết code, rồi harness tự kiểm."""
    attempt = Attempt(number=number)
    evidence = EvidenceStore(artifact_root)

    context = build_context(
        story,
        project=project,
        artifact_root=artifact_root,
        architecture=architecture,
        contract=contract,
        config=config,
        feedback=feedback,
    )
    evidence.handoff(story.id, frm="plan" if number == 1 else "gate", to=DEVELOPER,
                     attempt=number, slots=handoff_slots(context, feedback=bool(feedback)))
    # R4: danh sách hành vi phải giữ chốt **một lần** ở đây, trước phiên
    # developer; reviewer, security và cổng nhận đúng bản này — tính lại sau
    # phiên thì sổ đã đổi theo bằng chứng của chính lượt này.
    preservation = list(context.get("_preservation") or [])
    spec = build_spec(
        DEVELOPER,
        catalog.get(ROLES[DEVELOPER].prompt),
        context,
        workdir=workdir,
        config=config,
    )
    # Guard chạy trong hook — tiến trình con của client — nên phạm vi ghi
    # và mã story chỉ tới được nó qua môi trường.
    scope = effective_write_scope(story, project)
    spec.env = {
        ENV_WRITE_SCOPE: ",".join(scope),
        ENV_STORY_ID: story.id,
        ENV_BASE_REF: base_ref,
        ENV_WORKDIR: str(workdir),
        ENV_PROJECT: str(project),
    }

    # Cách ly là thứ **phải kiểm**, không phải thứ giả định. Worktree ngăn
    # story giẫm lên nhau, nhưng không có gì cấm agent `cd` ra ngoài rồi
    # commit thẳng vào thân cây. Đã gặp thật: một lượt OpenCode đưa
    # `src/reverse-words.js` lên `main` trong khi nhánh story đứng yên —
    # cổng chỉ báo "diff rỗng", còn code lạ thì đã nằm trên trunk.
    truoc = head_sha(project) if workdir != project else ""

    _attach_settings(spec, project)
    result = client.run(spec)
    attempt.cost_usd = result.cost_usd
    evidence.agent_run(
        story.id, result, name=f"{story.id}#{number}", prompt_chars=len(spec.prompt),
        skills={**context.get("_skills", {}), "used": skills_used(result)},
    )

    sau = head_sha(project) if workdir != project else ""
    if truoc and sau != truoc:
        attempt.error = (
            f"lượt chạy đã đổi nhánh chính của dự án ({truoc[:8]} → {sau[:8]}). "
            f"Story phải làm việc trong worktree riêng; công việc trên thân cây "
            f"không qua cổng nào cả. Hoàn nguyên rồi chạy lại."
        )
        attempt.infra = True   # story chưa hề được chấm
        attempt.fatal = True   # nhưng thử lại cũng vô nghĩa
        evidence.tool_run(
            story.id, "cách ly", ok=False,
            detail={"truoc": truoc, "sau": sau, "attempt": number},
        )
        return attempt

    if not result.ok:
        attempt.error = result.error or "lượt chạy thất bại"
        attempt.infra = is_infrastructure_error(attempt.error)
        return attempt

    # Phiên developer đã kết thúc: **đóng băng ứng viên ngay**, trước khi
    # kiểm bất cứ thứ gì (ADR-004 R1). Kiểm trước rồi mới chốt thì bằng
    # chứng không trỏ vào bản nào cả, và "stale" không định nghĩa được.
    changed_now = changed_files(str(workdir), base_ref=base_ref)
    attempt.candidate = freeze_candidate(
        workdir, story=story, scope=scope, isolated=workdir != project,
        evidence=evidence, artifact_root=artifact_root, number=number,
        changed=changed_now,
    )
    evidence.candidate = attempt.candidate

    # Harness tự chạy lại test và lint: bằng chứng phải do harness ghi, và
    # agent có thể đã "quên" chạy lần cuối sau khi sửa.
    for tool in ("test", "lint"):
        run_tool(tool, workdir, story_id=story.id, artifact_root=artifact_root,
                 config=config, candidate=attempt.candidate)

    # Test luôn xanh vì không khẳng định gì tệ hơn không có test: nó làm
    # cổng "test xanh" mất hết ý nghĩa. Kiểm rẻ, nên chạy mỗi lượt.
    fake = find_fake_tests(workdir, changed_now)
    evidence.tool_run(
        story.id, "qa:fake-tests", ok=not fake, detail={"files": fake}
    )

    # Hợp đồng kiểm định của story: chạy đúng những loại nó phải qua.
    # Không phải pha mới — cùng bộ máy `run_suite`, chỉ giới hạn phạm vi.
    # `verify.X` để trống vẫn là **chưa cấu hình**, không phải đạt: đó là
    # điều `run_suite` đã phân biệt sẵn, và cổng đọc lại đúng như thế.
    # R4: cộng thêm kiểm định và màn hình của hành vi phải giữ — cổng "bảo
    # toàn" chỉ chấm được thứ đã chạy ở ứng viên này, và "không chạy" thì
    # nó nói UNRUNNABLE chứ không nói đạt.
    hop_dong, man_hinh = validation_targets(story, preservation)
    if hop_dong:
        run_suite(
            workdir,
            config=config,
            only=hop_dong,
            has_ui=bool(man_hinh),
            story_id=story.id,
            artifact_root=artifact_root,
            changed=changed_now,
            candidate=attempt.candidate,
        )

    if man_hinh and contract:
        mockup_verify.verify_screens(
            workdir, contract, man_hinh,
            config=config, story_id=story.id, artifact_root=artifact_root,
            candidate=attempt.candidate,
        )

    attempt.review_findings = review_story(
        story,
        workdir=workdir,
        base_ref=base_ref,
        project=project,
        artifact_root=artifact_root,
        client=client,
        config=config,
        catalog=catalog,
        architecture=architecture,
        number=number,
        candidate=attempt.candidate,
        preservation=preservation,
    )
    # Mục chặn phải nằm trong bằng chứng, không chỉ trong bản tóm tắt in
    # ra màn hình — bản tóm tắt cắt ngắn, và khi cần biết lượt này với
    # lượt trước có bị chặn vì cùng một chuyện không thì phải đọc được
    # nguyên văn. Thiếu chỗ này thì lối duy nhất là mò nhật ký phiên.
    evidence.tool_run(
        story.id,
        "review",
        ok=not attempt.review_findings,
        detail={"findings": attempt.review_findings, "attempt": number},
    )

    if config.get("security.semantic_review", True):
        attempt.security = security_review(
            story,
            workdir=workdir,
            base_ref=base_ref,
            project=project,
            artifact_root=artifact_root,
            client=client,
            config=config,
            catalog=catalog,
            architecture=architecture,
            number=number,
            candidate=attempt.candidate,
            preservation=preservation,
        )
        evidence.tool_run(
            story.id,
            "security",
            ok=not (attempt.security.error
                    or attempt.security.blocking(config["security.block_severities"])),
            detail={
                "findings": [f.line() for f in attempt.security.findings],
                "filtered": len(attempt.security.filtered),
                "error": attempt.security.error,
                "attempt": number,
            },
        )

    attempt.gate = story_gate.evaluate(
        story.id,
        evidence.read(story.id),
        changed=changed_now,
        write_scope=scope,
        screens=list(story.screens),
        contract=verification_contract(story),
        review_blocking=attempt.review_findings,
        security=attempt.security,
        block_severities=config["security.block_severities"],
        guard_expected=guard_expected(project, getattr(client, "id", "")),
        acceptance=len(story.acceptance_criteria),
        coverage_min=float(config["coverage.min"]),
        added_tests=tdd.added_tests(workdir, base_ref=base_ref, changed=changed_now, story_id=story.id),
        candidate=attempt.candidate,
        preservation=preservation,
    )
    attempt.ok = attempt.gate.passed
    # Kết cục cổng đi vào bằng chứng, mang SHA ứng viên: sổ hành vi (R2) coi
    # "qua cổng ở ứng viên này" là dấu landed ở mức lượt — implement không
    # merge, và `attempt.committed` đóng giao dịch kể cả khi trượt.
    evidence.record(story.id, Event(
        kind=NOTE, name="gate:verdict", ok=attempt.ok,
        detail={"failures": [c.name for c in attempt.gate.failures][:20], "attempt": number},
    ))
    return attempt


def run_baseline(story: Story, *, workdir: Path, artifact_root: Path, config: Config) -> None:
    """Chạy bộ test ở **candidate cha** trước khi developer sửa gì (ADR-004 R9).

    HoH bảo developer "establish a baseline before editing"; ở đây harness
    làm, vì lời developer không phải bằng chứng. Ghi dưới tên `test:baseline`
    (xem `tools.BASELINE_RUN` vì sao không phải `test`), kèm `parent` = HEAD
    lúc chạy và `red_before` = test đã đỏ sẵn — cổng không tính chúng là hồi
    quy, và người đọc thấy ngay vì sao.

    Chạy **một lần cho cả story**, trước lượt đầu, không phải mỗi lượt: lượt 2
    mà lấy ứng viên lượt 1 làm mốc thì test lượt 1 vừa làm đỏ thành "đỏ sẵn",
    và lượt 2 xoá nó đi là qua cổng sạch. Mốc là trạng thái trước khi story
    chạm vào — và chi phí là một lần chạy test mỗi story, không phải mỗi lượt.

    Không có lệnh test thì bản ghi mang `skipped` (cổng đọc thành chưa cấu
    hình), không phải baseline xanh. Tắt bằng `verify.baseline` thì ghi rõ là
    tắt, để cổng nói "không áp dụng" chứ không im.
    """
    if not config.get("verify.baseline", True):
        EvidenceStore(artifact_root).tool_run(story.id, BASELINE_RUN, ok=False, detail={
            "baseline": True, "disabled": True,
            "skipped": "tắt bởi cấu hình `verify.baseline`",
        })
        return
    res = run_tool("test", workdir, config=config)   # story_id rỗng: ghi bên dưới, dưới tên riêng
    log = parse_testlog(res.stdout + "\n" + res.stderr)
    record_tool(res, story.id, artifact_root, name=BASELINE_RUN, extra={
        "baseline": True, "parent": head_sha(workdir), "red_before": log.failed[:MAX_IDS],
    })


def freeze_candidate(
    workdir: Path,
    *,
    story: Story,
    scope: list[str],
    isolated: bool,
    evidence: EvidenceStore,
    artifact_root: Path,
    number: int,
    changed: list[str],
) -> str:
    """Chốt công việc của phiên developer thành **một bản** và trả SHA của nó.

    Đây là điểm HoH gọi là *frozen candidate*: từ đây tới hết lượt, không
    gì được sửa cây nữa, và mọi phép kiểm nói về đúng bản này. Trước ADR-004
    R1 harness commit **sau** khi kiểm và rà soát — bằng chứng không trỏ
    vào bản nào, nên "test này chạy trên mã nào" không có câu trả lời.

    Không có gì để commit thì ứng viên là HEAD hiện tại (agent đã tự chốt).
    Chạy thẳng trong dự án (`--no-isolate`) thì **không** commit: không có
    nhánh riêng, và commit vào thân cây người dùng không phải việc của một
    lượt thử.
    """
    from ..control.worktree import GitError, commit_paths

    loi = ""
    if isolated:
        try:
            commit_paths(Path(workdir), f"{story.id}: ứng viên lượt {number}", paths=scope)
        except GitError as e:
            loi = str(e)
    sha = head_sha(workdir)

    journal = JournalStore(artifact_root)
    # Số hiệu **của giao dịch đang mở**, không phải số lượt thử trong story:
    # `open_attempt()` đóng một lượt bằng cách so số hiệu, nên ghi số khác
    # vào đây sẽ để lại một lượt "chưa đóng" và lần chạy sau đi dọn oan.
    giao_dich = journal.read(story.id).attempt_no or number
    journal.record(story.id, JEntry(
        step="changes.detected", attempt=giao_dich,
        data={"luot": number, "files": changed[:50], "count": len(changed)}))
    journal.record(story.id, JEntry(
        step="candidate.frozen", attempt=giao_dich,
        data={"luot": number, "sha": sha, "error": loi}))
    if loi or not sha:
        # Không chốt được thì bằng chứng phía sau gắn vào một bản **không**
        # chứa công việc. Nói ra ở bằng chứng; im lặng ở đây là để lại một
        # cổng chấm trên nền cát.
        evidence.tool_run(story.id, "candidate:frozen", ok=False,
                          detail={"error": loi or "không đọc được HEAD", "attempt": number})
    return sha


#: Trần ký tự cho diff đưa vào prompt rà soát. Đủ cho một story đúng cỡ;
#: vượt trần thì story quá to, và cắt ở đây tốt hơn là tràn ngữ cảnh.
REVIEW_DIFF_CHARS = 60_000


def review_diff(workdir: str, changed: list[str], *, base_ref: str = "") -> str:
    """Diff thật để rà soát, lùi về danh sách tên file khi không lấy được.

    Đưa mỗi tên file thì người rà soát phải tự đọc lại từng cái — đo trên
    e9 là 31–43 lượt và 12 phút cho một story nhỏ, phần lớn tiêu vào việc
    dựng lại thứ harness đã biết. Diff không thay việc đọc code xung
    quanh, nó chỉ bỏ bớt đoạn mò mẫm ban đầu.
    """
    names = "\n".join(f"- {c}" for c in changed[:50])
    if not base_ref:
        return names
    lines = _git_lines_text(workdir, ["diff", "--stat", base_ref])
    body = _git_lines_text(workdir, ["diff", base_ref])
    if not body:
        return names
    if len(body) > REVIEW_DIFF_CHARS:
        body = body[:REVIEW_DIFF_CHARS] + "\n… (diff bị cắt, đọc thẳng file phần còn lại)"
    ket = [names, ""]
    if lines:
        ket += ["```", lines.strip(), "```", ""]
    ket += ["```diff", body, "```"]
    return "\n".join(ket)


def _git_lines_text(workdir: str, args: list[str]) -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", *args], cwd=workdir, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def review_story(
    story: Story,
    *,
    workdir: Path,
    base_ref: str = "",
    project: Path,
    artifact_root: Path,
    client: ClientAdapter,
    config: Config,
    catalog: Catalog,
    architecture: Architecture | None,
    number: int = 0,
    candidate: str = "",
    preservation: list[dict] | None = None,
) -> list[str]:
    """Rà soát độc lập — **phiên mới**, không sửa được gì.

    Trả về danh sách mục ``[chặn]``. Người viết đã tin code mình đúng; hỏi
    lại chính phiên đó chỉ nhận lại cùng niềm tin.

    Chữ ký giữ nguyên cho luồng gọi cũ; bản máy đọc lấy ở `review_story_v2`.
    """
    return review_story_v2(
        story, workdir=workdir, base_ref=base_ref, project=project,
        artifact_root=artifact_root, client=client, config=config,
        catalog=catalog, architecture=architecture, number=number,
        candidate=candidate, preservation=preservation,
    )[0]


def _review_session(
    client: ClientAdapter, spec, *, store: EvidenceStore, story_id: str,
    artifact_root: Path, workdir: Path, name: str, role: str, number: int,
):
    """Một phiên rà soát: chạy, ghi bằng chứng, hoàn nguyên cây nếu bị sửa.

    Ghi nguyên văn **sau** khi đã so cây: artifact có thể nằm trong chính
    cây làm việc (không cách ly) và tệp lời rà soát không phải là "người
    rà soát sửa cây".
    """
    truoc = _tree_snapshot(workdir)
    result = client.run(spec)
    store.agent_run(story_id, result, name=name, prompt_chars=len(spec.prompt))
    da_sua = _revert_reviewer_writes(workdir, truoc, _tree_snapshot(workdir))
    persist_verdict(artifact_root, story_id, role, number, result)
    return result, da_sua


def _with_schema(client: ClientAdapter, spec, result, *, store: EvidenceStore,
                 story_id: str, artifact_root: Path, workdir: Path, role: str,
                 number: int):
    """Đòi khối JSON theo schema; thiếu thì hỏi lại **đúng một lần** (R8).

    Trả `(text, verdict)`: `text` là lời được dùng làm bản người đọc — lượt
    hai nếu lượt ấy đúng schema, còn không thì lời lượt đầu.
    """
    verdict = review_verdict(result.text)
    if verdict is not None:
        return result.text, verdict
    lai, da_sua = _review_session(
        client, replace(spec, prompt=spec.prompt + SCHEMA_REMINDER), store=store,
        story_id=story_id, artifact_root=artifact_root, workdir=workdir,
        name=f"{story_id}-{role}-retry", role=f"{role}-retry", number=number,
    )
    lech = _candidate_moved(workdir, store.candidate)
    if lech:
        # Lượt hỏi lại cũng bị soi ứng viên (R1): đổi bản thì lời không tính.
        store.tool_run(story_id, f"{role}:candidate", ok=False,
                       detail={"expected": store.candidate, "got": lech,
                               "attempt": number, "retry": True})
        return result.text, None
    if da_sua:
        # Lượt hỏi lại cũng bị bất biến "rà soát không ghi cây" soi; bỏ lời
        # của nó, và nói ra — hoàn nguyên im lặng thì không ai biết.
        store.tool_run(
            story_id, f"{role}:immutable", ok=False,
            detail={"changed": da_sua[:20], "retry": True},
        )
    if da_sua or not lai.ok:
        return result.text, None
    verdict = review_verdict(lai.text)
    return (lai.text, verdict) if verdict is not None else (result.text, None)


def review_story_v2(
    story: Story,
    *,
    workdir: Path,
    base_ref: str = "",
    project: Path,
    artifact_root: Path,
    client: ClientAdapter,
    config: Config,
    catalog: Catalog,
    architecture: Architecture | None,
    number: int = 0,
    candidate: str = "",
    preservation: list[dict] | None = None,
) -> tuple[list[str], Verdict | None]:
    """Như `review_story`, nhưng trả kèm bản máy đọc (`behavior_id`…).

    Luồng sổ hành vi (R2) đọc `note:review:verdict` trong bằng chứng để ghi
    GAP nguồn `reviewer`; ở đây chỉ cần trả ra cho người gọi nào cần.
    """
    changed = changed_files(str(workdir), base_ref=base_ref)
    if not changed:
        # Nói đúng hai khả năng. "Không có gì để rà" thường không phải
        # agent lười: hay gặp hơn là công việc của story đã nằm trên
        # nhánh chính rồi — worktree rẽ từ đó nên diff rỗng — và lúc ấy
        # lời khuyên "sửa write_scope" dẫn người đọc đi sai đường.
        return [
            "không có thay đổi nào để rà soát: hoặc lượt chạy không viết "
            "gì, hoặc công việc của story đã nằm trên nhánh chính rồi "
            "(worktree rẽ từ đó nên diff rỗng). Kiểm nhánh chính trước; "
            "nếu công việc đã ở đó thì story này xong rồi."
        ], None

    context = build_context(
        story,
        project=project,
        artifact_root=artifact_root,
        architecture=architecture,
        contract=None,
        config=config,
        preservation=preservation,
    )
    context["diff_summary"] = review_diff(str(workdir), changed, base_ref=base_ref)
    # Ảnh hưởng của thay đổi: người rà soát nhận diff rồi vẫn phải tự dò
    # ai gọi, test nào phủ — đo trên e9 là 22–68 lượt, mỗi lượt thử lại
    # làm lại từ đầu. Đưa sẵn thì nó bắt đầu từ chỗ xa hơn.
    context["impact"] = analyse_impact(
        workdir, changed, command=str(config.get("review.impact_provider", "") or "")
    ).as_prompt()
    # Test có sẵn bị bớt ca (G8): đưa cho người rà soát, không tự chặn —
    # "cập nhật kỳ vọng" là hợp lệ, "xoá cho xanh" thì không; đó là phán đoán.
    mat = tdd.test_delta(workdir, base_ref=base_ref, changed=changed)
    store = EvidenceStore(artifact_root, candidate=candidate)
    store.record(
        story.id, Event(kind=NOTE, name="qa:test-delta", ok=not mat, detail={"files": mat})
    )
    if mat:
        context["impact"] += (
            "\n\n**Test có sẵn bị bớt ca** — hỏi vì sao, đừng mặc định là hợp lệ: "
            + "; ".join(mat)
        )

    store.handoff(story.id, frm=DEVELOPER, to=REVIEWER, attempt=number,
                  slots=handoff_slots(context))
    spec = build_spec(
        REVIEWER,
        catalog.get(ROLES[REVIEWER].prompt),
        context,
        workdir=workdir,
        config=config,
    )
    # Phạm vi ghi — nhưng **không** mã story. Không truyền phạm vi thì
    # guard `diff-scope` rơi vào nhánh "chưa khai phạm vi mà đã đổi file"
    # và chặn mọi lệnh Bash của người rà soát; truyền mã story thì guard
    # `completion` lại chặn nó dừng khi test đang đỏ — đúng lúc nó có
    # nhiều thứ để báo cáo nhất.
    spec.env = {
        ENV_WRITE_SCOPE: ",".join(effective_write_scope(story, project)),
        ENV_BASE_REF: base_ref,
        ENV_WORKDIR: str(workdir),
        ENV_PROJECT: str(project),
        ENV_DISALLOWED_TOOLS: ",".join(ROLES[REVIEWER].disallowed_tools),
    }

    _attach_settings(spec, project)
    result, da_sua = _review_session(
        client, spec, store=store, story_id=story.id, artifact_root=artifact_root,
        workdir=workdir, name=f"{story.id}-review", role="review", number=number,
    )
    if da_sua:
        store.tool_run(
            story.id, "review:immutable", ok=False, detail={"changed": da_sua[:20]},
        )
        return [
            "[chặn] người rà soát đã sửa cây làm việc "
            f"({', '.join(da_sua[:3])}) — đã hoàn nguyên; lượt rà soát này không "
            "được tính. Rà soát là báo cáo, không phải sửa."
        ], None

    lech = _candidate_moved(workdir, candidate)
    if lech:
        # Hoàn nguyên chỉ đưa **cây** về như cũ; một `git commit` thì nó không
        # thấy. Ứng viên đã đổi nghĩa là người rà soát vừa đọc một bản khác
        # bản được chấm — lượt rà soát ấy không nói gì về ứng viên.
        store.tool_run(story.id, "review:candidate", ok=False,
                       detail={"expected": candidate, "got": lech, "attempt": number})
        return [
            f"[chặn] ứng viên đổi trong phiên rà soát ({candidate[:7]} → {lech[:7]}) — "
            "lượt rà soát này không được tính. Rà soát đọc bản đã đóng băng, "
            "không tạo bản mới."
        ], None

    if not result.ok:
        # Không rà soát được thì **không** coi như sạch.
        return [f"rà soát không chạy được: {result.error}"], None

    text, verdict = _with_schema(
        client, spec, result, store=store, story_id=story.id,
        artifact_root=artifact_root, workdir=workdir, role="review", number=number,
    )
    return _reconcile(story.id, store, text, verdict, role="review"), verdict


def _reconcile(story_id: str, ev: EvidenceStore, text: str,
               verdict: Verdict | None, *, role: str) -> list[str]:
    """Đối chiếu bản máy đọc với bản người đọc, ghi bằng chứng, trả **hợp**."""
    tu_van_ban = blocking_findings(text)
    if verdict is None:
        # Hai lượt đều không có schema: dùng văn bản như trước R8, và nói
        # ra là đã phải lùi — im lặng thì lần sau không ai biết để sửa prompt.
        ev.record(story_id, Event(kind=NOTE, name=f"{role}:no-schema", ok=False,
                                  detail={"findings": tu_van_ban, "retried": True}))
        return tu_van_ban
    tu_json = verdict.blocking()
    hop, lech = merge_findings(tu_van_ban, tu_json)
    if lech:
        ev.record(story_id, Event(
            kind=NOTE, name=f"{role}:mismatch", ok=False,
            detail={"text": tu_van_ban, "json": tu_json},
        ))
    ev.record(story_id, Event(
        kind=NOTE, name=f"{role}:verdict", ok=not hop,
        detail={"verdict": verdict.verdict, "findings": verdict.findings},
    ))
    return hop


def security_review(
    story: Story,
    *,
    workdir: Path,
    base_ref: str,
    project: Path,
    artifact_root: Path,
    client: ClientAdapter,
    config: Config,
    catalog: Catalog,
    architecture: Architecture | None,
    number: int = 0,
    candidate: str = "",
    preservation: list[dict] | None = None,
) -> SecurityReport:
    """Rà soát bảo mật theo ngữ nghĩa — **phiên riêng**, chỉ đọc.

    Không gộp vào lượt rà soát chung: một phiên phải giữ hai bộ câu hỏi
    khác nhau trong đầu thì bộ nào cũng bị làm qua loa, và bảo mật là bộ
    thường bị bỏ trước.

    Phiên này đọc mã do agent khác vừa viết — **dữ liệu không tin được**.
    Nó không có quyền ghi (vai `security` cấm Write/Edit), và không nhận
    biến môi trường nào của story: mã story đang chạy không việc gì phải
    tới tay nó. Cách ly khỏi bí mật của máy thì cần sandbox thật, không
    làm được ở tầng ngôn ngữ — đó là giới hạn, và nó được ghi ra thay vì
    giấu đi.
    """
    changed = changed_files(str(workdir), base_ref=base_ref)
    if not changed:
        return SecurityReport(error="không có thay đổi nào để rà")

    context = build_context(
        story,
        project=project,
        artifact_root=artifact_root,
        architecture=architecture,
        contract=None,
        config=config,
        preservation=preservation,
    )
    context["diff_summary"] = review_diff(str(workdir), changed, base_ref=base_ref)
    context["impact"] = analyse_impact(
        workdir, changed, command=str(config.get("review.impact_provider", "") or "")
    ).as_prompt()

    store = EvidenceStore(artifact_root, candidate=candidate)
    store.handoff(story.id, frm=REVIEWER, to=SECURITY, attempt=number,
                  slots=handoff_slots(context))
    spec = build_spec(
        SECURITY,
        catalog.get(ROLES[SECURITY].prompt),
        context,
        workdir=workdir,
        config=config,
    )
    # Cùng tổ hợp đã chứng minh trên e9 cho người rà soát: phạm vi để
    # `diff-scope` không chặn mọi lệnh Bash, cây làm việc để guard soi đúng
    # cây, tool bị cấm để mọi client đều cấm — và **không** mã story.
    spec.env = {
        ENV_WRITE_SCOPE: ",".join(effective_write_scope(story, project)),
        ENV_BASE_REF: base_ref,
        ENV_WORKDIR: str(workdir),
        ENV_PROJECT: str(project),
        ENV_DISALLOWED_TOOLS: ",".join(ROLES[SECURITY].disallowed_tools),
    }
    _attach_settings(spec, project)
    result, da_sua = _review_session(
        client, spec, store=store, story_id=story.id, artifact_root=artifact_root,
        workdir=workdir, name=f"{story.id}-security", role="security", number=number,
    )
    if da_sua:
        store.tool_run(
            story.id, "security:immutable", ok=False, detail={"changed": da_sua[:20]},
        )
        return SecurityReport(error=f"người rà soát bảo mật đã sửa cây làm việc ({', '.join(da_sua[:3])}) — đã hoàn nguyên, lượt này không được tính")
    lech = _candidate_moved(workdir, candidate)
    if lech:
        store.tool_run(story.id, "security:candidate", ok=False,
                       detail={"expected": candidate, "got": lech, "attempt": number})
        return SecurityReport(
            error=f"ứng viên đổi trong phiên rà soát bảo mật ({candidate[:7]} → "
                  f"{lech[:7]}) — lượt này không được tính"
        )
    if not result.ok:
        return SecurityReport(error=f"không chạy được: {result.error}")

    text, verdict = _with_schema(
        client, spec, result, store=store, story_id=story.id,
        artifact_root=artifact_root, workdir=workdir, role="security", number=number,
    )
    return _reconcile_security(story.id, store, text, verdict)


def _reconcile_security(story_id: str, ev: EvidenceStore, text: str,
                        verdict: Verdict | None) -> SecurityReport:
    """Cùng luật với `_reconcile`, nhưng đơn vị là mức nghiêm trọng.

    Mục JSON không có trong văn bản được đưa lại qua `parse_security` để
    đúng một bộ lọc nhiễu chấm cả hai nguồn.
    """
    rep = parse_security(text)
    if verdict is None:
        ev.record(story_id, Event(kind=NOTE, name="security:no-schema", ok=False,
                                  detail={"findings": [f.line() for f in rep.findings],
                                          "retried": True}))
        return rep

    tu_van_ban = [f.line() for f in rep.findings + rep.filtered]
    tu_json = [f"[{f['severity']}] " + _finding_body(f)
               for f in verdict.findings if f.get("severity")]
    hop, lech = merge_findings(tu_van_ban, tu_json)
    them = hop[len(tu_van_ban):]
    if them:
        bo_sung = parse_security("\n".join(them))
        rep.findings.extend(bo_sung.findings)
        rep.filtered.extend(bo_sung.filtered)
        rep.findings.sort(key=lambda f: -f.rank)
    # Khối JSON hợp lệ **là** báo cáo đúng định dạng: lỗi "sai định dạng"
    # của bản văn bản không còn đúng nữa.
    rep.error = ""
    if lech:
        ev.record(story_id, Event(kind=NOTE, name="security:mismatch", ok=False,
                                  detail={"text": tu_van_ban, "json": tu_json}))
    ev.record(story_id, Event(
        kind=NOTE, name="security:verdict", ok=not rep.blocking(),
        detail={"verdict": verdict.verdict, "findings": verdict.findings},
    ))
    return rep


#: Mở đầu mục chặn thường.
_BLOCK_TAGS = ("[chặn]", "[blocker]", "[block]")
#: Mở đầu mục **bế tắc**: người rà soát đã kiểm chứng rằng tiêu chí không
#: thoả được từ trong phạm vi story. Hai model độc lập cùng kết luận
#: story sai — thử tiếp là đốt tiền vào chỗ không có lối ra.
_STUCK_TAGS = ("[bế tắc]", "[be tac]", "[stuck]", "[blocked-by-plan]")


#: Thư mục giữ nguyên văn lời người rà soát — bằng chứng chặn phải đọc lại được.
REVIEWS_DIR = "reviews"


def persist_verdict(artifact_root: Path | str, story_id: str, role: str, number: int, result) -> Path:
    """Ghi nguyên văn báo cáo của người rà soát / rà soát bảo mật.

    Lỗi 16 (e9 STORY-01-05, 2026-09-05): lý do bế tắc trong sprint-status kết
    thúc ở "— không." vì chỉ dòng đầu của mục được giữ, còn lời đầy đủ thì
    không nằm ở đâu cả — bằng chứng chặn một story mà người đọc không kiểm
    lại được thì không phải bằng chứng.
    """
    d = Path(artifact_root) / REVIEWS_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{story_id}-{role}-{number}.md"
    head = (
        f"# {role} — {story_id}, lượt {number}\n\n"
        f"session: {getattr(result, 'session_id', '')} · lượt hội thoại: "
        f"{getattr(result, 'num_turns', 0)} · ${getattr(result, 'cost_usd', 0.0):.2f}"
        f"{' · LỖI: ' + result.error if getattr(result, 'error', '') else ''}\n\n---\n\n"
    )
    path.write_text(head + (getattr(result, "text", "") or ""), encoding="utf-8")
    return path


def blocking_findings(text: str) -> list[str]:
    """Lọc mục `[chặn]` và `[bế tắc]` khỏi báo cáo rà soát.

    Một mục có thể dài nhiều dòng: dòng tiếp theo không mở đầu bằng dấu
    gạch đầu dòng hay thẻ mới thì thuộc về mục trước (lỗi 16 — trước đây
    chỉ giữ dòng đầu, lý do bế tắc cụt ở "— không.").
    """
    out: list[str] = []
    dang_mo = False
    for line in (text or "").splitlines():
        raw = line.rstrip()
        stripped = raw.strip().lstrip("-*• ").strip()
        low = stripped.lower()
        if low.startswith(_BLOCK_TAGS) or low.startswith(_STUCK_TAGS):
            out.append(stripped)
            dang_mo = True
            continue
        if not stripped:
            dang_mo = False
            continue
        la_muc_moi = raw.lstrip().startswith(("-", "*", "•", "#")) or low.startswith("[")
        if dang_mo and not la_muc_moi:
            out[-1] = out[-1] + " " + stripped
        else:
            dang_mo = False
    return out


def plan_defects(findings: list[str]) -> list[str]:
    """Mục người rà soát đánh dấu là bế tắc do kế hoạch, không do code."""
    return [f for f in findings if f.strip().lower().startswith(_STUCK_TAGS)]


# --- Bản máy đọc của lời rà soát (ADR-004 R8) -------------------------------
#
# Văn bản là bản người đọc; khối JSON là bản máy đọc. Hai bản phải khớp — và
# khi lệch thì **hợp** hai nguồn chứ không nới lỏng: một mục chặn bị mất vì
# model quên chép sang JSON thì cổng cũng mất luôn, và đó là kiểu hỏng im
# lặng tệ nhất.

#: Kết luận hợp lệ. Ngoài ba giá trị này là sai schema.
VERDICTS = ("pass", "block", "stuck")
#: Thẻ trong JSON tương ứng hai loại mục chặn của văn bản.
_JSON_BLOCK_TAGS = ("chặn", "chan", "block", "blocker")
_JSON_STUCK_TAGS = ("bế tắc", "be tac", "stuck", "blocked-by-plan")

#: Nhắc lại schema khi lượt đầu không có khối JSON. Đúng **một** lần: lần
#: hai vẫn thiếu thì model ấy không làm được, thử tiếp là đốt tiền.
SCHEMA_REMINDER = (
    "\n\n---\n\n**Thiếu khối JSON theo schema.** Lượt trước bạn trả lời bằng "
    "văn bản nhưng không kèm khối JSON máy đọc được, nên cổng không đọc được "
    "kết luận của bạn. Trả lời **lại** đầy đủ như yêu cầu ở trên, và kết thúc "
    "bằng đúng một khối ```json``` theo schema đã nêu. Bản JSON và bản văn "
    "bản phải khớp nhau.\n"
)

_decoder = json.JSONDecoder()


@dataclass
class Verdict:
    """Bản máy đọc của một báo cáo rà soát."""

    verdict: str
    findings: list[dict] = field(default_factory=list)

    def blocking(self) -> list[str]:
        """Mục chặn/bế tắc, viết đúng dạng dòng của bản văn bản."""
        out = []
        for f in self.findings:
            if f["tag"] in _JSON_STUCK_TAGS:
                out.append("[bế tắc] " + _finding_body(f))
            elif f["tag"] in _JSON_BLOCK_TAGS:
                out.append("[chặn] " + _finding_body(f))
        if self.verdict != "pass" and not out:
            # Kết luận nói chặn mà không nêu mục nào: giữ kết luận, đừng
            # cho qua. Không tin client — kể cả khi nó tự mâu thuẫn.
            tag = "[bế tắc]" if self.verdict == "stuck" else "[chặn]"
            out.append(f"{tag} người rà soát kết luận `{self.verdict}` "
                       "nhưng không nêu mục nào trong khối JSON")
        return out


def _finding_body(f: dict) -> str:
    """`{file}:{line} — {why}` — cùng dạng với dòng người rà soát tự viết."""
    where = f.get("file") or ""
    if where and f.get("line"):
        where += f":{f['line']}"
    why = f.get("why") or ""
    return f"{where} — {why}".strip(" —") if where else why


def review_verdict(text: str) -> Verdict | None:
    """Khối JSON đầu tiên có `verdict` hợp lệ; mục sai schema bỏ, không sập.

    Cùng cách làm với `kit/skill_scan.parse_verdicts`, nhưng dùng
    `raw_decode`: nó tự dừng đúng chỗ JSON kết thúc nên chữ thừa phía sau
    (và hàng rào ```json) không làm hỏng việc.
    """
    for m in re.finditer(r"\{", text or ""):
        try:
            data, _ = _decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if not isinstance(data, dict) or "verdict" not in data:
            continue
        ket = str(data.get("verdict", "")).strip().lower()
        if ket not in VERDICTS:
            return None
        out = []
        for item in data.get("findings") or []:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag", "")).strip().lower()
            sev = str(item.get("severity", "")).strip().lower()
            if not tag and sev not in SEVERITIES:
                continue
            f = {
                "tag": tag,
                "file": str(item.get("file", ""))[:200],
                "line": str(item.get("line", "") or "")[:10],
                "why": str(item.get("why", ""))[:500],
                "behavior_id": str(item.get("behavior_id", ""))[:80],
            }
            if sev in SEVERITIES:
                f["severity"] = sev
            out.append(f)
        return Verdict(ket, out)
    return None


def _finding_key(line: str) -> tuple[str, str]:
    """Khoá đối chiếu giữa hai bản: (loại thẻ, tệp).

    Không so nguyên văn: bản JSON và bản văn bản không bao giờ trùng từng
    chữ, nhưng cùng nói về một chỗ trong một tệp thì là một mục.
    """
    m = re.match(r"\s*\[([^\]]*)\]\s*(\S*)", line or "")
    if not m:
        return ("", "")
    tag = m.group(1).strip().lower()
    loai = tag
    if tag in _JSON_STUCK_TAGS:
        loai = "stuck"
    elif tag in _JSON_BLOCK_TAGS:
        loai = "block"
    tep = m.group(2).strip().rstrip(":,;")
    tep = re.sub(r":\d+(-\d+)?$", "", tep)
    return (loai, tep)


def merge_findings(text_items: list[str], json_items: list[str]) -> tuple[list[str], bool]:
    """Hợp hai nguồn và nói có lệch không. Văn bản trước, JSON bù vào sau."""
    khoa_text = {_finding_key(x) for x in text_items}
    khoa_json = {_finding_key(x) for x in json_items}
    them = [x for x in json_items if _finding_key(x) not in khoa_text]
    return text_items + them, khoa_text != khoa_json



#: Cấu hình hook mà `aisdlc compile` sinh cho Claude Code.
CLAUDE_SETTINGS = Path(".claude") / "settings.json"


def _attach_settings(spec, project: Path) -> None:
    """Truyền tệp hook **tường minh** cho client, thay vì trông vào việc nó
    tự tìm thấy.

    Claude Code đọc `.claude/settings.json` của cây nó đang đứng. Story
    chạy trong worktree, và worktree chỉ có thư mục ấy nếu dự án **commit**
    nó. Dự án `.gitignore` `.claude/` sẽ chạy mọi story với zero guard —
    và bằng chứng trông y hệt agent ngoan, vì không có gì để ghi. e9 và
    par đều commit `.claude/`, nên lỗ hổng này chưa lộ; đó là may, không
    phải thiết kế.

    Adapter không hỗ trợ cờ (OpenCode) bỏ qua trường này — plugin của nó
    nạp theo đường khác, đã chứng minh.
    """
    path = Path(project) / CLAUDE_SETTINGS
    if path.is_file():
        spec.settings_file = path


def _tree_snapshot(workdir: Path) -> dict[str, bytes | None]:
    """Ảnh chụp cây làm việc: đường dẫn → nội dung của mọi tệp git thấy là
    đã đổi hoặc chưa theo dõi (None nếu quá lớn để giữ). Bỏ qua thứ harness
    tự ghi (`_bmad-output/`, `.aisdlc/`): bằng chứng của chính phiên này
    được ghi trong lúc phiên chạy, tính vào là dương tính giả."""
    from ..harness.guardrails import HARNESS_OWNED
    out: dict[str, bytes | None] = {}
    try:
        r = subprocess.run(["git", "status", "--porcelain", "-z", "-uall"],
                           cwd=workdir, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return out
    for item in r.stdout.split("\0"):
        if len(item) < 4:
            continue
        rel = item[3:]
        if rel.startswith((".aisdlc/", *[f"{h}/" for h in HARNESS_OWNED])) or rel in HARNESS_OWNED:
            continue
        p = Path(workdir) / rel
        try:
            out[rel] = p.read_bytes() if p.is_file() and p.stat().st_size <= 5_000_000 else None
        except OSError:
            out[rel] = None
    return out


def _revert_reviewer_writes(workdir: Path, truoc: dict, sau: dict) -> list[str]:
    """Người rà soát mà sửa được code thì nó thành lượt viết thứ hai.

    Cấm `Write`/`Edit` ở guard là lớp một; đo hợp quy 2026-09-05 cho thấy
    lớp ấy bị lách **trên cả hai client** bằng Bash (`echo > tệp`) — và Bash
    thì không cấm được, người rà soát cần nó để chạy test. Nên lớp hai là
    hoàn nguyên: mọi khác biệt của cây sau phiên rà soát bị đưa về như
    trước, ghi lại, và lượt rà soát ấy **không được tính** — cùng cơ chế
    "hoàn nguyên hạt thô" của worktree.
    """
    doi = sorted({k for k in sau if k not in truoc or sau[k] != truoc[k]}
                 | {k for k in truoc if k not in sau})
    if not doi:
        return []
    for rel in doi:
        p = Path(workdir) / rel
        if rel in truoc and truoc[rel] is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(truoc[rel])           # tệp đã đổi hoặc chưa theo dõi: trả nội dung
        elif rel in truoc:
            subprocess.run(["git", "checkout", "--", rel], cwd=workdir,
                           capture_output=True, timeout=30)   # quá lớn để chụp: nhờ git
        elif p.exists():
            try:
                p.unlink()                       # tệp mới do người rà soát tạo
            except OSError:
                pass
    return doi


def _candidate_moved(workdir: Path, candidate: str) -> str:
    """HEAD hiện tại nếu nó đã rời khỏi ứng viên; "" nếu còn đúng bản ấy.

    Không kiểm được (chưa đóng băng, hoặc không đọc được git) thì trả "":
    một lượt rà soát bị huỷ oan vì harness mù còn tệ hơn."""
    if not candidate:
        return ""
    bay_gio = head_sha(workdir)
    return bay_gio if bay_gio and bay_gio != candidate else ""


def deadlock_reason(attempts: list[Attempt], write_scope: list[str] | None = None) -> str:
    """Thế bí: hai lượt liền chặn vì cùng một chuyện. Rỗng nếu chưa bí.

    Người rà soát chặn lại đúng chỗ cũ nghĩa là lượt vừa rồi không dịch
    chuyển được gì — và lượt sau, với cùng ngữ cảnh và cùng feedback,
    cũng sẽ không. Thường là mâu thuẫn nằm ngoài tầm agent: tiêu chí
    chấp nhận đòi một thứ mà ``write_scope`` cấm.

    So bằng **độ tương đồng**, không bằng chuỗi y hệt. Người rà soát là
    một model: cùng một khiếm khuyết được nó viết lại bằng từ khác mỗi
    lượt. Đo trên e9, STORY-01-02 bị chặn 4 lượt vì đúng một chuyện —
    `fake-indexeddb` không được khai trong `package.json` — mà không cặp
    diễn đạt nào trùng nhau, nên bộ dò so chuỗi im lặng suốt và story
    đốt hết hạn mức: $10,39.
    """
    if len(attempts) < 2:
        return ""
    cuoi, truoc = attempts[-1], attempts[-2]
    if cuoi.infra or truoc.infra:
        return ""
    if not cuoi.review_findings or not truoc.review_findings:
        return ""
    if not _same_complaint(cuoi.review_findings, truoc.review_findings):
        return ""

    # Lặp lại **và** trỏ ra ngoài phạm vi ghi mới là bí. Trong phạm vi thì
    # đó là "chưa sửa", không phải "không sửa được" — và đo trên e9,
    # STORY-01-02 qua ở lượt 3 sau hai lượt trượt, còn STORY-01-04 bị chặn
    # hai lượt liền vì cùng một vi phạm AR-7 trên `src/app/list-notes.ts`,
    # tệp nằm ngay trong phạm vi của nó. Dừng ở đó là cắt ngang một story
    # còn cứu được; cứ để hạn mức lượt thử làm việc của nó.
    ngoai = _paths_outside(cuoi.review_findings, write_scope or [])
    if not ngoai:
        return ""
    return (
        "bí: hai lượt liền bị chặn vì cùng một chuyện — "
        + "; ".join(cuoi.review_findings[:2])
        + f". Mục chặn trỏ tới {', '.join(ngoai)} — không nằm trong "
        f"write_scope của story, nên agent không sửa được dù có thử bao "
        f"nhiêu lượt. Nới write_scope hoặc sửa tiêu chí chấp nhận rồi "
        f"chạy lại."
    )


#: Hai mục chặn là "cùng một chuyện" khi chúng chia nhau **danh từ riêng**
#: — tên tệp, tên gói, định danh — chứ không khi văn bản giống nhau.
#: Người rà soát là một model: cùng một khiếm khuyết được nó viết lại bằng
#: từ khác mỗi lượt, nên so văn bản thì không bao giờ khớp. Nhưng
#: `fake-indexeddb` và `package.json` thì lượt nào nó cũng phải nhắc.
#:
#: Đòi **hai** danh từ riêng chung, không phải một: chỉ chung `package.json`
#: thì "thiếu khai X" và "khai sai Y" cũng khớp — mà đó là có dịch chuyển,
#: không phải bí. Hệ số phủ đi kèm loại nốt trường hợp mục chặn dài nhắc
#: qua loa tới thứ mục kia nói chính.
SAME_COMPLAINT_NOUNS = 2
SAME_COMPLAINT_OVERLAP = 0.4


def _same_complaint(a: list[str], b: list[str]) -> bool:
    """Có mục chặn nào của lượt này nói cùng chuyện với lượt trước không."""
    for x in (_tokens(i) for i in a):
        for y in (_tokens(j) for j in b):
            if not x or not y:
                continue
            if x == y:
                return True  # lặp nguyên văn thì khỏi bàn
            chung = x & y
            if len(_rieng(chung)) < SAME_COMPLAINT_NOUNS:
                continue
            if len(chung) / min(len(x), len(y)) >= SAME_COMPLAINT_OVERLAP:
                return True
    return False


def _rieng(tokens: set[str]) -> set[str]:
    """Danh từ riêng: có dấu phân cách của định danh, đủ dài để không phải
    dấu câu dính vào từ."""
    return {t for t in tokens if len(t) >= 4 and any(c in t for c in "./-_@")}


#: Từ xuất hiện ở gần như mọi mục chặn nên không phân biệt được gì.
_NHIEU = frozenset(
    "chặn blocker block và or không có là của một các cả cho khi thì mà "
    "nhưng nó này đó ở trong ngoài với từ đến được bị phải nào đâu nữa "
    "the a an is are not no this that it".split()
)


def _tokens(finding: str) -> set[str]:
    """Rút mục chặn về tập từ so được. Bỏ số dòng và từ quá phổ biến."""
    import re as _re

    # Bỏ số dòng, giữ mọi số khác: "TCCN 1" và "TCCN 7" là hai chuyện
    # khác nhau, gộp chúng lại thì bộ dò báo bí trong khi có dịch chuyển.
    low = _re.sub(r":\d+", " ", finding.lower())
    words = _re.findall(r"[\w./@-]+", low)
    return {
        w for w in words
        if w not in _NHIEU and (len(w) >= 2 or w.isdigit())
    }


def _paths_outside(findings: list[str], scope: list[str]) -> list[str]:
    """Tệp mà mục chặn nhắc tới nhưng story không được ghi.

    Đây là câu trả lời cụ thể cho "vì sao thử lại cũng vô ích", và nó
    đọc ra từ dữ liệu đã có chứ không đoán.
    """
    import re as _re

    from ..harness.guardrails import _within

    out: list[str] = []
    for f in findings:
        for m in _re.findall(r"[\w./-]+\.[a-z]{2,4}\b", f):
            if m in out or "/" not in m and "." not in m:
                continue
            if not any(_within(m, s) for s in scope):
                out.append(m)
    return out[:3]


def implement_story(
    story: Story,
    *,
    project: Path | str,
    workdir: Path | str | None = None,
    artifact_root: Path | str | None = None,
    client: ClientAdapter,
    config: Config | None = None,
    catalog: Catalog | None = None,
    architecture: Architecture | None = None,
    contract: DesignContract | None = None,
) -> StoryOutcome:
    """Chạy một story tới khi đạt cổng hoặc hết lượt thử."""
    project = Path(project)
    workdir = Path(workdir) if workdir else project
    root = Path(artifact_root) if artifact_root else project / "_bmad-output"
    cfg = config or Config.load(project)
    cat = catalog or load_catalog()
    contract = contract if contract is not None else load_contract(root)

    outcome = StoryOutcome(story_id=story.id)
    max_retries = cfg["run.max_retries"]
    infra_budget = max_retries + 1  # lỗi hạ tầng có hạn mức riêng
    feedback = ""

    # Điểm story rẽ khỏi nhánh chính. Tính một lần, trước lượt đầu: agent
    # sẽ commit trong worktree, và mọi cổng phải nhìn công việc từ mốc này
    # chứ không từ HEAD đang chạy theo nó. Chạy thẳng trong dự án
    # (`--no-isolate`) thì không có nhánh riêng, rỗng là đúng.
    base_ref = ""
    if workdir != project:
        head = head_sha(project)
        base_ref = fork_point(str(workdir), head) if head else ""

    # Mốc test trước khi story chạm vào — một lần, trước lượt đầu (ADR-004 R9).
    run_baseline(story, workdir=workdir, artifact_root=root, config=cfg)

    while True:
        attempt = run_attempt(
            story,
            project=project,
            workdir=workdir,
            artifact_root=root,
            client=client,
            config=cfg,
            catalog=cat,
            architecture=architecture,
            contract=contract,
            number=outcome.quality_attempts + 1,
            feedback=feedback,
            base_ref=base_ref,
        )
        outcome.attempts.append(attempt)

        if attempt.ok:
            return outcome

        if attempt.fatal:
            outcome.blocked_reason = attempt.error
            return outcome

        if attempt.infra:
            infra_budget -= 1
            if infra_budget <= 0:
                outcome.blocked_reason = f"lỗi hạ tầng lặp lại: {attempt.error}"
                return outcome
            continue  # không tính vào hạn mức chất lượng

        # Người rà soát đã **tự kiểm chứng** rằng tiêu chí không thoả được
        # từ trong phạm vi story. Hai model độc lập cùng kết luận story
        # sai; lượt thứ ba sẽ nhận cùng ngữ cảnh và cho cùng kết quả.
        loi_ke_hoach = plan_defects(attempt.review_findings)
        if loi_ke_hoach:
            outcome.blocked_reason = (
                "bế tắc do kế hoạch, người rà soát đã kiểm chứng: "
                + "; ".join(loi_ke_hoach[:2])
                + ". Sửa tiêu chí chấp nhận hoặc write_scope của story rồi "
                "chạy lại — thử tiếp không gỡ được."
            )
            return outcome

        van = deadlock_reason(outcome.attempts, effective_write_scope(story, project))
        if van:
            outcome.blocked_reason = van
            return outcome

        if outcome.quality_attempts > max_retries:
            outcome.blocked_reason = (
                f"đã thử {outcome.quality_attempts} lần vẫn không qua cổng"
            )
            return outcome

        feedback = attempt.gate.feedback() if attempt.gate else attempt.error
        if attempt.review_findings:
            feedback += "\n" + "\n".join(f"- {f}" for f in attempt.review_findings[:10])
