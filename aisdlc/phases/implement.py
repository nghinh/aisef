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
from ..control.normalize import Architecture, Story
from ..harness import mockup_verify
from ..harness.guardrails import (
    ENV_BASE_REF,
    ENV_STORY_ID,
    ENV_WRITE_SCOPE,
    changed_files,
    fork_point,
)
from ..harness.mockup_map import load_for_story, prompt_section
from ..harness.observe import EvidenceStore
from ..harness.prompts import Catalog, load_catalog
from ..harness.routing import DEVELOPER, REVIEWER, ROLES, build_spec
from ..harness.tools import describe_tools, run_tool
from .qa import find_fake_tests

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
    error: str = ""
    cost_usd: float = 0.0
    gate: story_gate.StoryGate | None = None
    review_findings: list[str] = field(default_factory=list)


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
    spec.env = {
        ENV_WRITE_SCOPE: ",".join(story.write_scope),
        ENV_STORY_ID: story.id,
        ENV_BASE_REF: base_ref,
    }

    result = client.run(spec)
    attempt.cost_usd = result.cost_usd
    evidence.agent_run(story.id, result, name=f"{story.id}#{number}")

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

    attempt.gate = story_gate.evaluate(
        story.id,
        evidence.read(story.id),
        changed=changed_now,
        write_scope=list(story.write_scope),
        screens=list(story.screens),
        review_blocking=attempt.review_findings,
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
        return ["không có thay đổi nào để rà soát"]

    context = build_context(
        story,
        project=project,
        artifact_root=artifact_root,
        architecture=architecture,
        contract=None,
        config=config,
    )
    context["diff_summary"] = review_diff(str(workdir), changed, base_ref=base_ref)

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
        ENV_WRITE_SCOPE: ",".join(story.write_scope),
        ENV_BASE_REF: base_ref,
    }

    result = client.run(spec)
    EvidenceStore(artifact_root).agent_run(story.id, result, name=f"{story.id}-review")

    if not result.ok:
        # Không rà soát được thì **không** coi như sạch.
        return [f"rà soát không chạy được: {result.error}"]
    return blocking_findings(result.text)


def blocking_findings(text: str) -> list[str]:
    """Lọc mục `[chặn]` khỏi báo cáo rà soát."""
    out = []
    for line in (text or "").splitlines():
        stripped = line.strip().lstrip("-*• ").strip()
        low = stripped.lower()
        if low.startswith("[chặn]") or low.startswith("[blocker]") or low.startswith("[block]"):
            out.append(stripped)
    return out


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


def deadlock_reason(attempts: list[Attempt]) -> str:
    """Thế bí: hai lượt liền cùng một mục chặn. Rỗng nếu chưa bí.

    Người rà soát chặn lại đúng chỗ cũ nghĩa là lượt vừa rồi không dịch
    chuyển được gì — và lượt sau, với cùng ngữ cảnh và cùng feedback,
    cũng sẽ không. Thường là mâu thuẫn nằm ngoài tầm agent: tiêu chí
    chấp nhận đòi một thứ mà ``write_scope`` cấm, hoặc hai tiêu chí đá
    nhau. Agent làm đúng chỉ dẫn — dừng và báo phạm vi khai thiếu —
    nhưng không ai đọc lời báo đó, nên vòng lặp cứ chạy hết hạn mức.

    Đo trên e9: 4 lượt y hệt nhau cho STORY-01-01, $9,85, cùng một câu
    "TCCN 1 đòi lockfile được commit; kho không có".
    """
    if len(attempts) < 2:
        return ""
    cuoi, truoc = attempts[-1], attempts[-2]
    if cuoi.infra or truoc.infra:
        return ""
    a, b = _finding_keys(cuoi), _finding_keys(truoc)
    if not a or a != b:
        return ""
    return (
        "bí: hai lượt liền bị chặn y hệt — "
        + "; ".join(cuoi.review_findings[:2])
        + ". Thử lại không gỡ được: sửa tiêu chí chấp nhận hoặc write_scope "
        "của story rồi chạy lại."
    )


def _finding_keys(attempt: Attempt) -> set[str]:
    """Mục chặn rút về khoá so sánh được.

    Bỏ số dòng và khoảng trắng: cùng một khiếm khuyết được báo ở dòng
    246 rồi 307 sau khi agent sửa chỗ khác vẫn là cùng một thế bí.
    """
    import re as _re

    out = set()
    for f in attempt.review_findings:
        k = _re.sub(r":\d+", ":", f.lower())
        out.add(" ".join(k.split())[:120])
    return out


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

        if attempt.infra:
            infra_budget -= 1
            if infra_budget <= 0:
                outcome.blocked_reason = f"lỗi hạ tầng lặp lại: {attempt.error}"
                return outcome
            continue  # không tính vào hạn mức chất lượng

        van = deadlock_reason(outcome.attempts)
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
