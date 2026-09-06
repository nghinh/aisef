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
from dataclasses import dataclass, field
from pathlib import Path

from ..control.outcome import DEFAULT_REASON, Outcome
from ..config import Config
from ..harness import sandbox
from ..harness.guardrails import head_sha, scrub_secrets
from ..harness.observe import EvidenceStore
from ..harness.tools import command_for, image_for, unrunnable_reason


@dataclass(frozen=True)
class Kind:
    id: str
    title: str
    level: sandbox.Level = sandbox.Level.WORKSPACE_WRITE
    #: Chỉ áp dụng khi dự án có giao diện.
    needs_ui: bool = False
    why: str = ""


KINDS: dict[str, Kind] = {
    "unit": Kind("unit", "Kiểm thử đơn vị và chức năng",
                 why="Từng đơn vị làm đúng phần việc của nó."),
    "sit": Kind("sit", "Kiểm thử tích hợp hệ thống",
                level=sandbox.Level.WORKSPACE_NETWORK,
                why="Các thành phần ghép lại vẫn chạy — nơi lỗi hay nằm nhất."),
    "api-contract": Kind("api-contract", "Hợp đồng API",
                         level=sandbox.Level.WORKSPACE_NETWORK,
                         why="Máy khách dựa vào hợp đồng; đổi lặng lẽ là làm hỏng người khác."),
    "e2e": Kind("e2e", "Đầu-cuối", level=sandbox.Level.WORKSPACE_NETWORK, needs_ui=True,
                why="Đường đi thật của người dùng, không phải đường đi trong đầu ta."),
    "uat": Kind("uat", "Nghiệm thu theo tiêu chí chấp nhận",
                level=sandbox.Level.WORKSPACE_NETWORK,
                why="Đúng thứ PRD hứa, diễn đạt bằng ngôn ngữ người dùng."),
    "perf": Kind("perf", "Hiệu năng", level=sandbox.Level.WORKSPACE_NETWORK,
                 why="Ngưỡng lấy từ NFR; không có số thì 'nhanh' là ý kiến."),
    "security": Kind("security", "Bảo mật", level=sandbox.Level.READ_ONLY,
                     why="Quét mã, phụ thuộc và bí mật lọt vào kho."),
    "accessibility": Kind("accessibility", "Trợ năng", needs_ui=True,
                          level=sandbox.Level.WORKSPACE_NETWORK,
                          why="Người dùng bàn phím và trình đọc màn hình cũng là "
                              "người dùng; thiếu tên gọi thì màn hình không dùng được."),
    "migration": Kind("migration", "Di trú dữ liệu",
                      why="Nâng cấp lược đồ sai thì dữ liệu người dùng mất, và "
                          "không có đường lùi."),
    "mutation": Kind("mutation", "Kiểm đột biến",
                     why="Bắt test luôn xanh dù code hỏng — thứ tệ hơn không có test."),
    "sbom": Kind("sbom", "Kê khai thành phần (SBOM)", level=sandbox.Level.READ_ONLY,
                 why="Không biết mình chạy thư viện nào thì không trả lời được câu "
                     "'chúng ta có dính lỗ hổng đó không'."),
    "image-scan": Kind("image-scan", "Quét image triển khai",
                       level=sandbox.Level.WORKSPACE_NETWORK,
                       why="Lỗ hổng phần lớn nằm ở tầng nền của image, không nằm ở mã ta viết."),
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
            return f"  {o.mark} {self.kind.id:12} không chạy được — {self.unrunnable}"
        if o is Outcome.WAIVED:
            return f"  {o.mark} {self.kind.id:12} miễn tường minh ({self.skipped or self.unrunnable})"
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
        lines = ["Kiểm định:"]
        lines += [r.line(waived=r.kind.id in self.waived) for r in self.results]
        if self.fake_tests:
            lines.append(f"  ✗ test giả: {len(self.fake_tests)} test không có khẳng định nào")
            for t in self.fake_tests[:5]:
                lines.append(f"      {t}")
        if self.unrunnable:
            lines.append(
                "\n⚠️  không chạy được: "
                + ", ".join(r.kind.id for r in self.unrunnable)
                + " — môi trường chưa dựng, không phải test đỏ"
            )
        if self.unconfigured:
            lines.append(
                "\n⚠️  chưa cấu hình: "
                + ", ".join(r.kind.id for r in self.unconfigured)
                + " — chưa chạy thì không được gọi là đã kiểm"
            )
        if self.waived:
            lines.append(f"miễn tường minh: {', '.join(self.waived)}")
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
           "__pycache__", ".aisdlc")


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
) -> QaReport:
    """Chạy bộ kiểm định.

    ``candidate`` là SHA bản đang kiểm (ADR-004 R1). Không truyền thì lấy
    HEAD của chính cây đang chạy: QA cấp dự án cũng phải trả lời được "kết
    quả này thuộc bản nào", không chỉ QA trong story.
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

    for kind in KINDS.values():
        if only and kind.id not in only:
            continue
        result = KindResult(kind=kind)
        if kind.id in waived:
            # Miễn là **quyết định của người**, đã ghi lại. Vẫn chạy rồi
            # vẫn đếm là trượt thì miễn chẳng có nghĩa gì, và báo cáo tự
            # mâu thuẫn: dòng dưới ghi "miễn tường minh" trong khi dòng
            # trên ghi ✗.
            result.skipped = "miễn tường minh (verify.waived)"
            report.results.append(result)
            continue
        if kind.needs_ui and not has_ui:
            result.skipped = "dự án không có giao diện"
            report.results.append(result)
            continue

        command = command_for_kind(kind.id, project, cfg)
        if not command:
            result.skipped = "chưa cấu hình lệnh (verify.%s)" % kind.id
            report.results.append(result)
            continue

        import shlex

        sb = sandbox.run(
            sandbox.SandboxSpec(
                workspace=project,
                cmd=shlex.split(command),
                level=kind.level,
                image=image_for(project, cfg),
                timeout_seconds=cfg["run.timeout_seconds"],
                allow_degraded=cfg["sandbox.allow_degraded"],
                use_docker=cfg["sandbox.use_docker"],
                provider=cfg["sandbox.provider"],
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
                        **({"redacted": che} if che else {})},
            )

    report.fake_tests = find_fake_tests(project, changed)
    if store and report.fake_tests:
        store.tool_run(story_id, "qa:fake-tests", ok=False,
                       detail={"files": report.fake_tests})
    return report
