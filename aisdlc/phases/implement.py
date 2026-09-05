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

from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter
from ..config import Config
from ..control import gate as story_gate
from ..control.design_contract import DesignContract, load as load_contract
from ..control.impact import analyse as analyse_impact
from ..control.preflight import verification_contract
from ..control.security import SecurityReport
from ..control.security import parse as parse_security
from ..control.normalize import Architecture, Story, effective_write_scope
from ..harness import mockup_verify
from ..harness.guardrails import (
    ENV_WORKDIR,
    ENV_BASE_REF,
    ENV_STORY_ID,
    ENV_WRITE_SCOPE,
    changed_files,
    fork_point,
)
from ..harness.mockup_map import load_for_story, prompt_section
from ..harness.observe import EvidenceStore
from ..harness.prompts import Catalog, load_catalog
from ..harness.routing import DEVELOPER, REVIEWER, ROLES, SECURITY, build_spec
from ..harness.tools import describe_tools, run_tool
from .qa import find_fake_tests, run_suite

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
) -> dict:
    """Ngữ cảnh cho prompt story — chọn bằng tra cứu, không bằng phán đoán."""
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

    return {
        "story_id": story.id,
        "story_title": story.title,
        "story_contract": contract_text,
        "architecture_rules": (
            "\n\n".join(d.as_prompt() for d in rules)
            or "(kiến trúc không nêu quyết định nào ràng buộc story này)"
        ),
        "write_scope": "\n".join(f"- `{p}`" for p in story.write_scope) or "(chưa khai)",
        "mockup_section": prompt_section(slices),
        "tools": describe_tools(project, config),
    }


def _story_fallback(story: Story) -> str:
    lines = [f"# {story.id}: {story.title}", "", "## Tiêu chí chấp nhận", ""]
    lines += [f"{i}. {ac}" for i, ac in enumerate(story.acceptance_criteria, 1)]
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
    }

    # Cách ly là thứ **phải kiểm**, không phải thứ giả định. Worktree ngăn
    # story giẫm lên nhau, nhưng không có gì cấm agent `cd` ra ngoài rồi
    # commit thẳng vào thân cây. Đã gặp thật: một lượt OpenCode đưa
    # `src/reverse-words.js` lên `main` trong khi nhánh story đứng yên —
    # cổng chỉ báo "diff rỗng", còn code lạ thì đã nằm trên trunk.
    truoc = _head_of(project) if workdir != project else ""

    result = client.run(spec)
    attempt.cost_usd = result.cost_usd
    evidence.agent_run(story.id, result, name=f"{story.id}#{number}")

    sau = _head_of(project) if workdir != project else ""
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

    # Harness tự chạy lại test và lint: bằng chứng phải do harness ghi, và
    # agent có thể đã "quên" chạy lần cuối sau khi sửa.
    for tool in ("test", "lint"):
        run_tool(tool, workdir, story_id=story.id,
                 artifact_root=artifact_root, config=config)

    # Test luôn xanh vì không khẳng định gì tệ hơn không có test: nó làm
    # cổng "test xanh" mất hết ý nghĩa. Kiểm rẻ, nên chạy mỗi lượt.
    changed_now = changed_files(str(workdir), base_ref=base_ref)
    fake = find_fake_tests(workdir, changed_now)
    evidence.tool_run(
        story.id, "qa:fake-tests", ok=not fake, detail={"files": fake}
    )

    # Hợp đồng kiểm định của story: chạy đúng những loại nó phải qua.
    # Không phải pha mới — cùng bộ máy `run_suite`, chỉ giới hạn phạm vi.
    # `verify.X` để trống vẫn là **chưa cấu hình**, không phải đạt: đó là
    # điều `run_suite` đã phân biệt sẵn, và cổng đọc lại đúng như thế.
    hop_dong = [
        k for k in verification_contract(story)
        if k not in ("mockup-map", "unit", "security")
    ]
    if hop_dong:
        run_suite(
            workdir,
            config=config,
            only=hop_dong,
            has_ui=bool(story.screens),
            story_id=story.id,
            artifact_root=artifact_root,
            changed=changed_now,
        )

    if story.screens and contract:
        mockup_verify.verify_screens(
            workdir, contract, story.screens,
            config=config, story_id=story.id, artifact_root=artifact_root,
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
    )
    attempt.ok = attempt.gate.passed
    return attempt


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
) -> list[str]:
    """Rà soát độc lập — **phiên mới**, không sửa được gì.

    Trả về danh sách mục ``[chặn]``. Người viết đã tin code mình đúng; hỏi
    lại chính phiên đó chỉ nhận lại cùng niềm tin.
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
        ]

    context = build_context(
        story,
        project=project,
        artifact_root=artifact_root,
        architecture=architecture,
        contract=None,
        config=config,
    )
    context["diff_summary"] = review_diff(str(workdir), changed, base_ref=base_ref)
    # Ảnh hưởng của thay đổi: người rà soát nhận diff rồi vẫn phải tự dò
    # ai gọi, test nào phủ — đo trên e9 là 22–68 lượt, mỗi lượt thử lại
    # làm lại từ đầu. Đưa sẵn thì nó bắt đầu từ chỗ xa hơn.
    context["impact"] = analyse_impact(
        workdir, changed, command=str(config.get("review.impact_provider", "") or "")
    ).as_prompt()

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
    }

    result = client.run(spec)
    EvidenceStore(artifact_root).agent_run(story.id, result, name=f"{story.id}-review")

    if not result.ok:
        # Không rà soát được thì **không** coi như sạch.
        return [f"rà soát không chạy được: {result.error}"]
    return blocking_findings(result.text)


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
    )
    context["diff_summary"] = review_diff(str(workdir), changed, base_ref=base_ref)
    context["impact"] = analyse_impact(
        workdir, changed, command=str(config.get("review.impact_provider", "") or "")
    ).as_prompt()

    spec = build_spec(
        SECURITY,
        catalog.get(ROLES[SECURITY].prompt),
        context,
        workdir=workdir,
        config=config,
    )
    result = client.run(spec)
    EvidenceStore(artifact_root).agent_run(
        story.id, result, name=f"{story.id}-security"
    )
    if not result.ok:
        return SecurityReport(error=f"không chạy được: {result.error}")
    return parse_security(result.text)


#: Mở đầu mục chặn thường.
_BLOCK_TAGS = ("[chặn]", "[blocker]", "[block]")
#: Mở đầu mục **bế tắc**: người rà soát đã kiểm chứng rằng tiêu chí không
#: thoả được từ trong phạm vi story. Hai model độc lập cùng kết luận
#: story sai — thử tiếp là đốt tiền vào chỗ không có lối ra.
_STUCK_TAGS = ("[bế tắc]", "[be tac]", "[stuck]", "[blocked-by-plan]")


def blocking_findings(text: str) -> list[str]:
    """Lọc mục `[chặn]` và `[bế tắc]` khỏi báo cáo rà soát."""
    out = []
    for line in (text or "").splitlines():
        stripped = line.strip().lstrip("-*• ").strip()
        low = stripped.lower()
        if low.startswith(_BLOCK_TAGS) or low.startswith(_STUCK_TAGS):
            out.append(stripped)
    return out


def plan_defects(findings: list[str]) -> list[str]:
    """Mục người rà soát đánh dấu là bế tắc do kế hoạch, không do code."""
    return [f for f in findings if f.strip().lower().startswith(_STUCK_TAGS)]


def _head_of(repo: Path) -> str:
    """SHA đầu nhánh chính. Rỗng nếu không đọc được — guard mất một phần
    tầm nhìn thì tệ, nhưng chặn cả story vì không đọc được git còn tệ hơn.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


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
        head = _head_of(project)
        base_ref = fork_point(str(workdir), head) if head else ""

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
