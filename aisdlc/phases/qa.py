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

from ..config import Config
from ..harness import sandbox
from ..harness.observe import EvidenceStore
from ..harness.tools import command_for, image_for


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
_TEST_FUNC = re.compile(r"^\s*(def test_|it\(|test\(|func Test)", re.MULTILINE)
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

    @property
    def configured(self) -> bool:
        return self.ran or not self.skipped

    def line(self) -> str:
        if self.skipped:
            return f"  ○ {self.kind.id:12} {self.skipped}"
        mark = "✅" if self.ok else "✗"
        extra = f" — {self.detail}" if self.detail and not self.ok else ""
        return f"  {mark} {self.kind.id:12} {self.kind.title}{extra}"


@dataclass
class QaReport:
    results: list[KindResult] = field(default_factory=list)
    fake_tests: list[str] = field(default_factory=list)
    waived: list[str] = field(default_factory=list)

    @property
    def failed(self) -> list[KindResult]:
        return [r for r in self.results if r.ran and not r.ok]

    @property
    def unconfigured(self) -> list[KindResult]:
        return [r for r in self.results if r.skipped and r.kind.id not in self.waived]

    @property
    def passed(self) -> bool:
        """Đạt ở mức story: không có loại nào chạy mà đỏ, không có test giả."""
        return not self.failed and not self.fake_tests

    @property
    def release_ready(self) -> bool:
        """Đạt ở mức trước triển khai: mọi loại **đã chạy** và xanh."""
        return self.passed and not self.unconfigured

    def summary(self) -> str:
        lines = ["Kiểm định:"]
        lines += [r.line() for r in self.results]
        if self.fake_tests:
            lines.append(f"  ✗ test giả: {len(self.fake_tests)} test không có khẳng định nào")
            for t in self.fake_tests[:5]:
                lines.append(f"      {t}")
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
        proc = subprocess.run(
            ["git", "-C", str(project), "ls-files"],
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


def run_suite(
    project: Path | str,
    *,
    config: Config | None = None,
    only: list[str] | None = None,
    has_ui: bool = True,
    story_id: str = "",
    artifact_root: Path | str | None = None,
    changed: list[str] | None = None,
) -> QaReport:
    """Chạy bộ kiểm định."""
    project = Path(project)
    cfg = config or Config.load(project)
    waived = [
        w.strip() for w in str(cfg.get("verify.waived", "") or "").split(",") if w.strip()
    ]
    report = QaReport(waived=waived)
    store = EvidenceStore(artifact_root) if (story_id and artifact_root) else None

    for kind in KINDS.values():
        if only and kind.id not in only:
            continue
        result = KindResult(kind=kind)
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
            )
        )
        result.ran = True
        result.ok = sb.ok
        result.duration_ms = sb.duration_ms
        result.detail = "\n".join((sb.stdout + "\n" + sb.stderr).strip().splitlines()[-5:])
        report.results.append(result)
        if store:
            store.tool_run(
                story_id, f"qa:{kind.id}", ok=sb.ok, duration_ms=sb.duration_ms,
                detail={"command": command, "tail": result.detail[:500]},
            )

    report.fake_tests = find_fake_tests(project, changed)
    if store and report.fake_tests:
        store.tool_run(story_id, "qa:fake-tests", ok=False,
                       detail={"files": report.fake_tests})
    return report
