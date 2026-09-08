"""Bước 5 — kiểm định: chạy thật, và không gọi thứ chưa chạy là đã kiểm.

Chín loại kiểm định, mỗi loại một lệnh của dự án chạy trong sandbox và ghi
bằng chứng. Thiết kế xoay quanh một điều: **"chưa cấu hình" không phải là
"đạt"**. Một bộ kiểm định báo xanh vì chín trên chín loại chưa từng chạy
là thứ nguy hiểm hơn không có bộ kiểm định nào.

Vì thế mỗi loại có ba kết quả, không phải hai:

===============  =========================================================
``đạt``          chạy và xanh
``không đạt``    chạy và đỏ
``chưa cấu hình``  chưa có lệnh — cảnh báo ở mức story, **chặn** ở cổng
                 trước triển khai, trừ khi được miễn tường minh
===============  =========================================================

Ngoài các lệnh của dự án còn một phép kiểm bằng code: **test không có
khẳng định nào**. Đây là kiểu test giả hay gặp nhất — luôn xanh, không
kiểm gì, và tạo cảm giác an toàn giả. Kiểm đột biến bắt được nhiều hơn,
nhưng nó chậm và thường chưa được cài; phép kiểm này rẻ và luôn chạy được.
"""

from __future__ import annotations

import re
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

from ..control.outcome import DEFAULT_REASON, Outcome
from ..control.worktree import GitError, WorktreeManager
from ..config import Config
from ..harness import sandbox
from ..harness.guardrails import head_sha, scrub_secrets
from ..harness.observe import EvidenceStore
from ..harness.tools import command_for, image_for, unrunnable_reason

#: Nhãn cây đã chạy kiểm định — vào bằng chứng và `pre-deploy.json`.
TREE_CLEAN = "clean-worktree"
TREE_AGENT = "agent-tree"

#: Thư mục phụ thuộc không nằm trong git — worktree sạch mượn của dự án.
#: ponytail: chỉ gốc dự án; monorepo có `packages/*/node_modules` thì thêm sau.
DEPS_DIRS = ("node_modules", ".venv", "venv")


@dataclass(frozen=True)
class Kind:
    id: str
    title: str
    level: sandbox.Level = sandbox.Level.WORKSPACE_WRITE
    #: Chỉ áp dụng khi dự án có giao diện.
    needs_ui: bool = False
    why: str = ""


KINDS: dict[str, Kind] = {
    "unit": Kind("unit", "Unit and functional tests",
                 why="Each unit does its part correctly."),
    "sit": Kind("sit", "System integration tests",
                level=sandbox.Level.WORKSPACE_NETWORK,
                why="Components still work when assembled — where bugs hide most."),
    "api-contract": Kind("api-contract", "API contract tests",
                         level=sandbox.Level.WORKSPACE_NETWORK,
                         why="Clients rely on the contract; silent changes break others."),
    "e2e": Kind("e2e", "End-to-end", level=sandbox.Level.WORKSPACE_NETWORK, needs_ui=True,
                why="The real user journey, not the one in our heads."),
    "uat": Kind("uat", "Acceptance tests against criteria",
                level=sandbox.Level.WORKSPACE_NETWORK,
                why="What the PRD promised, expressed in user language."),
    "perf": Kind("perf", "Performance", level=sandbox.Level.WORKSPACE_NETWORK,
                 why="Thresholds from NFR; without numbers, 'fast' is an opinion."),
    "security": Kind("security", "Security", level=sandbox.Level.READ_ONLY,
                     why="Scan code, dependencies, and secrets leaked into the repo."),
    "accessibility": Kind("accessibility", "Accessibility", needs_ui=True,
                          level=sandbox.Level.WORKSPACE_NETWORK,
                          why="Keyboard and screen-reader users are users too; "
                              "missing labels make screens unusable."),
    "migration": Kind("migration", "Data migration",
                      why="A bad schema upgrade loses user data, and there is "
                          "no way back."),
    "mutation": Kind("mutation", "Mutation testing",
                     why="Catches tests that pass even when code is broken — worse than no tests."),
    "sbom": Kind("sbom", "Software bill of materials (SBOM)", level=sandbox.Level.READ_ONLY,
                 why="Not knowing which libraries you run means you cannot answer "
                     "'are we affected by that vulnerability'."),
    "image-scan": Kind("image-scan", "Deploy image scan",
                       level=sandbox.Level.WORKSPACE_NETWORK,
                       why="Most vulnerabilities live in the image base layer, not in our code."),
}

#: Lệnh mặc định khi dự án không khai. Chỉ đặt cho loại có công cụ gần như
#: chuẩn; còn lại để trống và báo "chưa cấu hình" thay vì đoán bừa.
_DEFAULTS: dict[str, dict[str, str]] = {
    "python": {"security": "bandit -q -r .", "mutation": "mutmut run"},
    "node": {"e2e": "npx playwright test", "mutation": "npx stryker run"},
}

#: Lệnh không phụ thuộc stack — chỉ dùng khi công cụ có trên máy.
_UNIVERSAL: dict[str, str] = {
    "sbom": "syft . -o cyclonedx-json=sbom.json",
    "image-scan": "trivy fs --exit-code 1 --severity HIGH,CRITICAL .",
}

_TEST_FILE = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]+\.py$|\.(test|spec)\.[jt]sx?$")
from ..control.tdd import TEST_FUNC as _TEST_FUNC  # noqa: E402 — một regex, một chỗ
_ASSERTION = re.compile(
    r"\bassert\b|\bexpect\s*\(|\bshould\b|assert[A-Z]\w+\(|\.to(Be|Equal|Have|Throw)"
)


@dataclass
class KindResult:
    kind: Kind
    ran: bool = False
    ok: bool = False
    detail: str = ""
    duration_ms: int = 0
    skipped: str = ""
    #: Lệnh có, nhưng môi trường chưa dựng nên nó không chạy nổi. Khác
    #: hẳn "test đỏ": test không trượt, nó chưa từng chạy. Gộp hai thứ
    #: lại thì báo cáo nói sai chỗ cần sửa — đo trên e9, `pre-deploy`
    #: báo "✗ unit" trong khi thật ra gốc dự án chưa `npm ci` bao giờ.
    unrunnable: str = ""
    #: Chạy ngoài Docker (suy biến). Kết quả vẫn tính, nhưng mức cách ly
    #: thấp hơn phải hiện ra — cổng trước triển khai đọc cờ này.
    degraded: bool = False
    #: Tên bảo đảm bậc này cần mà provider thiếu (`sandbox.Guarantee`) —
    #: "suy biến" không nói thiếu gì thì cổng không nói được đang tin gì.
    missing: list[str] = field(default_factory=list)

    @property
    def configured(self) -> bool:
        return self.ran or not self.skipped

    @property
    def outcome(self) -> Outcome:
        if self.skipped:
            return Outcome.UNCONFIGURED
        if self.unrunnable:
            return Outcome.UNRUNNABLE
        if not self.ran:
            return Outcome.UNCONFIGURED
        return Outcome.PASSED if self.ok else Outcome.FAILED

    def line(self, *, waived: bool = False) -> str:
        o = self.outcome
        if waived and o.must_be_named:
            o = Outcome.WAIVED
        if o is Outcome.UNCONFIGURED:
            return f"  {o.mark} {self.kind.id:12} {self.skipped or DEFAULT_REASON[o]}"
        if o is Outcome.UNRUNNABLE:
            return f"  {o.mark} {self.kind.id:12} unrunnable — {self.unrunnable}"
        if o is Outcome.WAIVED:
            ly_do = self.skipped or self.unrunnable
            if ly_do.startswith("explicit waiver"):   # already self-describing, don't wrap again
                return f"  {o.mark} {self.kind.id:12} {ly_do}"
            return f"  {o.mark} {self.kind.id:12} explicit waiver ({ly_do})"
        extra = f" — {self.detail}" if self.detail and not self.ok else ""
        return f"  {o.mark} {self.kind.id:12} {self.kind.title}{extra}"


@dataclass
class QaReport:
    results: list[KindResult] = field(default_factory=list)
    fake_tests: list[str] = field(default_factory=list)
    waived: list[str] = field(default_factory=list)
    #: SHA bản được kiểm — bằng chứng không gắn bản thì không nói được nó
    #: chứng minh cho mã nào (ADR-004 R1).
    candidate: str = ""
    #: Cây đã chạy: `worktree-tạm` dựng từ `clean_tree` (ADR-005 V6) hay
    #: `cây agent` (kèm lý do khi không dựng được). Mức bảo đảm phải hiện ra.
    tree: str = ""
    clean_tree: str = ""

    @property
    def failed(self) -> list[KindResult]:
        """Loại đã chạy và đỏ. **Không** gồm loại không chạy nổi: chúng
        vẫn chặn, nhưng qua `unrunnable`, với lý do đúng."""
        return [r for r in self.results if r.ran and not r.ok and not r.unrunnable]

    @property
    def degraded(self) -> list[KindResult]:
        """Loại đã chạy nhưng ngoài Docker."""
        return [r for r in self.results if r.ran and r.degraded]

    @property
    def unrunnable(self) -> list[KindResult]:
        return [r for r in self.results if r.unrunnable and r.kind.id not in self.waived]

    @property
    def unconfigured(self) -> list[KindResult]:
        return [r for r in self.results if r.skipped and r.kind.id not in self.waived]

    @property
    def passed(self) -> bool:
        """Đạt ở mức story: không có loại nào chạy mà đỏ, không có test giả."""
        return not self.failed and not self.unrunnable and not self.fake_tests

    @property
    def release_ready(self) -> bool:
        """Đạt ở mức trước triển khai: mọi loại **đã chạy** và xanh."""
        return self.passed and not self.unconfigured

    def summary(self) -> str:
        lines = ["Verification:"]
        lines += [r.line(waived=r.kind.id in self.waived) for r in self.results]
        if self.fake_tests:
            lines.append(f"  ✗ fake tests: {len(self.fake_tests)} tests with no assertions")
            for t in self.fake_tests[:5]:
                lines.append(f"      {t}")
        if self.unrunnable:
            lines.append(
                "\n⚠️  unrunnable: "
                + ", ".join(r.kind.id for r in self.unrunnable)
                + " — environment not set up, not a test failure"
            )
        if self.unconfigured:
            lines.append(
                "\n⚠️  unconfigured: "
                + ", ".join(r.kind.id for r in self.unconfigured)
                + " — never ran means never verified"
            )
        if self.waived:
            lines.append(f"explicit waiver: {', '.join(self.waived)}")
        if self.tree:
            lines.append(f"verification tree: {self.tree}"
                         + (f" from {self.clean_tree[:7]}" if self.clean_tree else ""))
        return "\n".join(lines)


def command_for_kind(kind_id: str, project: Path, config: Config | None) -> str:
    """Lệnh của một loại: cấu hình thắng, rồi tới mặc định theo stack."""
    if config is not None:
        key = f"verify.{kind_id}"
        if key in config and str(config[key]).strip():
            return str(config[key]).strip()
    if kind_id == "unit":
        return command_for("test", project, config)
    if kind_id == "security":
        configured = command_for("sast", project, config)
        if configured:
            return configured
    marker = "node" if (project / "package.json").is_file() else (
        "python" if (project / "pyproject.toml").is_file() else ""
    )
    default = _DEFAULTS.get(marker, {}).get(kind_id, "")
    if default:
        return default

    # Công cụ chung chỉ dùng khi thật sự có trên máy: khai một lệnh không
    # tồn tại thì loại đó "chạy và đỏ", báo sai bản chất — nó chưa cấu hình.
    import shutil as _shutil

    universal = _UNIVERSAL.get(kind_id, "")
    if universal and _shutil.which(universal.split()[0]):
        return universal
    return ""


def find_fake_tests(project: Path | str, files: list[str] | None = None) -> list[str]:
    """Tìm test không có khẳng định nào.

    Không cố hiểu ngữ nghĩa: chỉ hỏi một câu rất cụ thể — file này có hàm
    test mà tuyệt nhiên không có khẳng định nào không. Câu hỏi hẹp nên
    hiếm báo nhầm, và kiểu test giả nó bắt được là kiểu phổ biến nhất.
    """
    project = Path(project)
    if files is None:
        files = _project_files(project)
    candidates = [project / f for f in files if _TEST_FILE.search(f)]

    out = []
    for path in sorted(candidates):
        if not path.is_file() or path.suffix not in (".py", ".js", ".ts", ".jsx", ".tsx", ".go"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _TEST_FUNC.search(text) and not _ASSERTION.search(text):
            out.append(str(path.relative_to(project)))
    return out


#: Thư mục không phải mã của dự án. Chỉ dùng khi không có git để hỏi.
_VENDOR = ("node_modules", ".git", ".venv", "venv", "dist", "build", "references",
           "__pycache__", ".aisef")


def _project_files(project: Path) -> list[str]:
    """File thuộc dự án. Hỏi git trước — nó biết chính xác cái gì được
    theo dõi, kể cả những chỗ `.gitignore` loại ra mà ta không đoán được."""
    import subprocess

    try:
        # `--others --exclude-standard` để thấy cả file **chưa commit**:
        # test giả vừa viết xong thì chưa nằm trong chỉ mục git, mà đó đúng
        # là lúc cần bắt nó nhất.
        proc = subprocess.run(
            ["git", "-C", str(project), "ls-files",
             "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            return [line for line in proc.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        pass

    out = []
    for path in project.rglob("*"):
        rel = path.relative_to(project)
        if not path.is_file() or any(part in _VENDOR for part in rel.parts):
            continue
        out.append(str(rel))
    return out


def _unrunnable_reason(exit_code: int, detail: str, provider_error: str = "") -> str:
    return unrunnable_reason("", exit_code, detail, provider_error=provider_error)


def _verification_tree(
    stack: ExitStack, project: Path, sha: str, *, clean: bool,
) -> tuple[Path, str, str, dict[str, Path]]:
    """Cây để **chạy** kiểm định: worktree tạm từ ``sha`` (ADR-005 V6) hay
    chính cây đang đứng. Trả ``(workspace, nhãn cây, SHA cây sạch, mounts)``.

    Không dựng được (không git, chưa có commit, SHA lạ) thì chạy trên cây
    đang đứng **và nói ra** trong nhãn — không chạy được ≠ trượt, và giảm
    bảo đảm không được im lặng (bất biến 10). Worktree do ``stack`` gỡ.
    """
    if not clean:
        return project, TREE_AGENT, "", {}
    if not sha:
        return project, f"{TREE_AGENT} (no git/HEAD to create clean worktree)", "", {}
    try:
        cay = stack.enter_context(WorktreeManager(project).temporary(sha))
    except GitError as e:
        return project, f"{TREE_AGENT} (could not create clean worktree: {e})", "", {}
    mounts = {d: project / d for d in DEPS_DIRS if (project / d).is_dir()}
    return cay, TREE_CLEAN, sha, mounts


def run_suite(
    project: Path | str,
    *,
    config: Config | None = None,
    only: list[str] | None = None,
    has_ui: bool = True,
    story_id: str = "",
    artifact_root: Path | str | None = None,
    changed: list[str] | None = None,
    candidate: str = "",
    clean: bool = True,
) -> QaReport:
    """Chạy bộ kiểm định.

    ``candidate`` là SHA bản đang kiểm (ADR-004 R1). Không truyền thì lấy
    HEAD của chính cây đang chạy: QA cấp dự án cũng phải trả lời được "kết
    quả này thuộc bản nào", không chỉ QA trong story.

    ``clean`` (ADR-005 V6, mặc định bật và còn cần `verify.clean_tree`): các
    lệnh chạy trong **worktree tạm dựng từ ``candidate``**, không phải cây
    đang đứng. Harbor dừng env agent rồi chạy verifier ở container tách; ở
    đây cây agent vừa sửa có thể mang shim `node_modules/.bin/vitest`,
    `pytest.ini`, `conftest.py` chưa commit — worktree từ SHA không có
    chúng. `node_modules`/`.venv` của dự án được gắn vào (Docker: bind
    mount; suy biến: symlink) như cây thường vẫn có. Giá: tệp **không theo
    dõi** mà test cần (`.env.test`, fixture sinh tay) cũng vắng — commit
    chúng, hoặc tắt `verify.clean_tree`; tắt thì `tree = "cây agent"`, ghi
    vào bằng chứng và `pre-deploy.json`. Mức story (`verify_candidate`)
    truyền ``clean=False``: cây worktree đã đóng băng, guard write-scope đã
    chặn ngoài phạm vi. `find_fake_tests` vẫn đọc cây đang đứng: test giả
    vừa viết chưa commit là đúng lúc phải bắt.
    """
    project = Path(project)
    cfg = config or Config.load(project)
    candidate = candidate or head_sha(project)
    waived = [
        w.strip() for w in str(cfg.get("verify.waived", "") or "").split(",") if w.strip()
    ]
    report = QaReport(waived=waived, candidate=candidate)
    store = (EvidenceStore(artifact_root, candidate=candidate)
             if (story_id and artifact_root) else None)

    with ExitStack() as stack:
        cay, report.tree, report.clean_tree, mounts = _verification_tree(
            stack, project, candidate, clean=clean and bool(cfg.get("verify.clean_tree", True)),
        )
        for kind in KINDS.values():
            if only and kind.id not in only:
                continue
            result = KindResult(kind=kind)
            if kind.id in waived:
                # Miễn là **quyết định của người**, đã ghi lại. Vẫn chạy rồi
                # vẫn đếm là trượt thì miễn chẳng có nghĩa gì, và báo cáo tự
                # mâu thuẫn: dòng dưới ghi "miễn tường minh" trong khi dòng
                # trên ghi ✗.
                ly_do = str(cfg.get("verify.waiver_reason", "") or "").strip()
                result.skipped = "explicit waiver (verify.waived)" + (f": {ly_do}" if ly_do else "")
                report.results.append(result)
                continue
            if kind.needs_ui and not has_ui:
                result.skipped = "project has no UI"
                report.results.append(result)
                continue

            command = command_for_kind(kind.id, project, cfg)
            if not command:
                result.skipped = "command not configured (verify.%s)" % kind.id
                report.results.append(result)
                continue

            import shlex

            sb = sandbox.run(
                sandbox.SandboxSpec(
                    workspace=cay,
                    cmd=shlex.split(command),
                    level=kind.level,
                    image=image_for(project, cfg),
                    timeout_seconds=cfg["run.timeout_seconds"],
                    allow_degraded=cfg["sandbox.allow_degraded"],
                    use_docker=cfg["sandbox.use_docker"],
                    provider=cfg["sandbox.provider"],
                    mounts=mounts,
                )
            )
            result.ran = True
            result.ok = sb.ok
            result.duration_ms = sb.duration_ms
            result.degraded = bool(getattr(sb, "degraded", False))
            result.missing = list(getattr(sb, "missing", []))
            # Dò dấu hiệu trên đầu ra **đầy đủ**, không phải phần đã cắt:
            # "Cannot find module" nằm ở đầu stack trace còn `detail` chỉ giữ
            # 5 dòng cuối. Đo trên e9: sau bản vá đầu tiên, `mutation` vẫn bị
            # đếm là test đỏ đúng vì chỗ này.
            # Che bí mật **trước** khi cắt (ADR-005 V1): `tail` đi vào
            # `_bmad-output`, thư mục được commit theo dự án.
            day_du, che = scrub_secrets((sb.stdout + "\n" + sb.stderr).strip())
            result.detail = "\n".join(day_du.splitlines()[-5:])
            result.unrunnable = _unrunnable_reason(
                getattr(sb, "exit_code", 0), day_du, getattr(sb, "provider_error", ""))
            report.results.append(result)
            if store:
                store.tool_run(
                    story_id, f"qa:{kind.id}", ok=sb.ok, duration_ms=sb.duration_ms,
                    detail={"command": command, "tail": result.detail[:500],
                            "tree": report.tree, "clean_tree": report.clean_tree,
                            **({"redacted": che} if che else {})},
                )

    report.fake_tests = find_fake_tests(project, changed)
    if store and report.fake_tests:
        store.tool_run(story_id, "qa:fake-tests", ok=False,
                       detail={"files": report.fake_tests})
    return report
