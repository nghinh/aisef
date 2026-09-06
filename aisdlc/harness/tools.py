"""Tool thật của harness — thứ agent gọi thay vì tự gõ lệnh.

Chỉ có ở đây những việc mà **bằng chứng của lần chạy là thứ cổng đọc**:
test, lint, sast. Chụp màn hình và đối chiếu mockup do harness tự làm sau
lượt agent (nếu để agent tự chụp thì nó vừa làm vừa chấm chính mình);
commit thì agent dùng thẳng `git`, và guard `git-stage` canh ở đó.

Mỗi tool ở đây làm ba việc mà "cứ để agent chạy Bash" không làm được:

1. **Lệnh cố định theo dự án**, không do agent nghĩ ra mỗi lượt. `npm test`
   hay `pytest -q` là quyết định của dự án, không phải chỗ để phán đoán.
2. **Chạy trong sandbox** — cùng bậc quyền cho mọi story, mọi máy.
3. **Ghi bằng chứng.** Đây mới là điểm chính: cổng story và guard
   `completion` đọc bằng chứng chứ không đọc lời agent kể. Không có bản ghi
   thì coi như chưa chạy.

Mỗi tool kèm một câu "khi nào gọi" — chuỗi này đi thẳng vào prompt, vì tool
không có mô tả dùng đúng lúc thì agent sẽ gọi sai lúc.
"""

from __future__ import annotations

import json
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Config
from . import sandbox
from .guardrails import scrub_secrets
from .observe import EvidenceStore

#: Số dòng cuối ghi vào `detail.tail`. Không nâng lên: `tail` đi vào prompt
#: của cổng và guard (ngân sách B5); toàn văn nằm ở tệp `.log` cạnh sổ.
TAIL_LINES = 20

#: Ảnh sandbox theo stack. `alpine` không có node hay python, nên chạy
#: `npm test` trong đó sẽ đỏ vì **thiếu công cụ**, không phải vì code sai —
#: và một cổng báo đỏ vì lý do sai sẽ bị bỏ qua trong hai ngày.
STACK_IMAGES: list[tuple[str, str]] = [
    ("package.json", "node:22-alpine"),
    ("pyproject.toml", "python:3.12-alpine"),
    ("setup.py", "python:3.12-alpine"),
    ("go.mod", "golang:1.23-alpine"),
    ("Cargo.toml", "rust:1-alpine"),
    ("composer.json", "php:8-cli-alpine"),
    ("Gemfile", "ruby:3-alpine"),
]


def image_for(project: Path | str, config: Config | None = None) -> str:
    """Ảnh sandbox: cấu hình thắng, rồi tới ảnh hợp stack, rồi mặc định."""
    if config is not None and str(config.get("sandbox.image", "")).strip():
        return str(config["sandbox.image"]).strip()
    project = Path(project)
    for marker, image in STACK_IMAGES:
        if (project / marker).is_file():
            return image
    return sandbox.DEFAULT_IMAGE


#: Lệnh mặc định theo dấu hiệu trong dự án. Cặp (test, lint, sast).
_STACK_COMMANDS: list[tuple[str, dict[str, str]]] = [
    ("pyproject.toml", {"test": "pytest -q", "lint": "ruff check .", "sast": "bandit -q -r ."}),
    ("setup.py", {"test": "pytest -q", "lint": "ruff check .", "sast": "bandit -q -r ."}),
    ("go.mod", {"test": "go test ./...", "lint": "go vet ./...", "sast": "gosec ./..."}),
    ("Cargo.toml", {"test": "cargo test", "lint": "cargo clippy -- -D warnings", "sast": "cargo audit"}),
    ("pubspec.yaml", {"test": "flutter test", "lint": "flutter analyze", "sast": ""}),
    ("composer.json", {"test": "composer test", "lint": "composer lint", "sast": ""}),
    ("Gemfile", {"test": "bundle exec rspec", "lint": "bundle exec rubocop", "sast": "bundle exec brakeman -q"}),
]


@dataclass
class Tool:
    name: str
    when: str          # khi nào gọi — đi vào prompt
    level: sandbox.Level = sandbox.Level.WORKSPACE_WRITE


TOOLS: dict[str, Tool] = {
    "test": Tool(
        "test",
        "Sau mỗi lần sửa code, và bắt buộc trước khi tuyên bố story xong. "
        "Chạy trước khi viết code để thấy test đỏ (RED) rồi mới viết cho xanh.",
    ),
    "lint": Tool(
        "lint",
        "Trước khi commit. Lỗi lint là lỗi phải sửa, không phải gợi ý.",
    ),
    "sast": Tool(
        "sast",
        "Trước khi commit, khi story chạm tới xác thực, phân quyền, truy vấn "
        "dữ liệu, tải file lên, hoặc bất kỳ dữ liệu nào đến từ người dùng.",
        level=sandbox.Level.READ_ONLY,
    ),
}


@dataclass
class ToolResult:
    name: str
    ok: bool
    exit_code: int = 0
    stdout: str = ""
    #: Công cụ không nạp được (MODULE_NOT_FOUND, command not found…) — không
    #: phải test đỏ. Dogfood par 2026-09-05: `node --test src/` đỏ vì lệnh sai,
    #: guard `completion` chặn Stop ~10 lần mỗi lượt, 3 story đốt $17.
    unrunnable: str = ""
    stderr: str = ""
    duration_ms: int = 0
    skipped: str = ""      # lý do không chạy được (không có lệnh cho stack này)
    degraded: bool = False
    detail: dict = field(default_factory=dict)
    #: Tệp log toàn văn (đã che bí mật) khi output dài hơn `TAIL_LINES` và
    #: có story để ghi — `aisdlc tool` in đường dẫn này ở dòng "lược".
    log: str = ""

    @property
    def ran(self) -> bool:
        return not self.skipped

    def summary(self) -> str:
        if self.skipped:
            return f"{self.name}: bỏ qua — {self.skipped}"
        mark = "✅" if self.ok else "✗"
        thieu = ", ".join(self.detail.get("missing") or [])
        extra = f" (sandbox suy biến — thiếu {thieu or 'bảo đảm'})" if self.degraded else ""
        return f"{mark} {self.name} — thoát {self.exit_code}, {self.duration_ms}ms{extra}"

    def output(self) -> tuple[str, int]:
        """(stdout + stderr đã che bí mật, số chỗ che). Mọi thứ in ra hay ghi
        lại đi qua đây — che **trước** khi cắt, để một khoá nằm vắt qua mép
        `tail` không lọt nửa sau (ADR-005 V1)."""
        return scrub_secrets((self.stdout + "\n" + self.stderr).strip())

    def tail(self, lines: int = 40) -> str:
        """Phần cuối output — chỗ lỗi thường nằm."""
        return "\n".join(self.output()[0].splitlines()[-lines:])


def detect_commands(project: Path | str) -> dict[str, str]:
    """Lệnh test/lint/sast của dự án, dò từ file có thật trên đĩa."""
    project = Path(project)
    pkg = project / "package.json"
    if pkg.is_file():
        return _from_package_json(pkg)
    for marker, commands in _STACK_COMMANDS:
        if (project / marker).is_file():
            return dict(commands)
    return {"test": "", "lint": "", "sast": ""}


def _from_package_json(path: Path) -> dict[str, str]:
    """Chỉ khai lệnh script **thật sự có**.

    `npm test` khi package.json không định nghĩa script `test` sẽ thoát khác
    0 vì lý do sai — cổng sẽ báo "test đỏ" trong khi thực ra dự án chưa có
    test. Hai chuyện đó cần được phân biệt.
    """
    try:
        scripts = json.loads(path.read_text(encoding="utf-8")).get("scripts") or {}
    except (json.JSONDecodeError, OSError):
        scripts = {}
    out = {"test": "", "lint": "", "sast": "npm audit --omit=dev"}
    if "test" in scripts:
        out["test"] = "npm test --silent"
    if "lint" in scripts:
        out["lint"] = "npm run lint --silent"
    elif "typecheck" in scripts:
        out["lint"] = "npm run typecheck --silent"
    return out


def command_for(name: str, project: Path | str, config: Config | None = None) -> str:
    """Lệnh cho một tool: cấu hình thắng, dò tự động là dự phòng."""
    if config is not None:
        key = f"tools.{name}"
        if key in config:
            configured = str(config[key]).strip()
            if configured:
                return configured
    return detect_commands(project).get(name, "")


def run_tool(
    name: str,
    project: Path | str,
    *,
    story_id: str = "",
    artifact_root: Path | str | None = None,
    config: Config | None = None,
    extra_args: list[str] | None = None,
    candidate: str = "",
) -> ToolResult:
    """Chạy một tool trong sandbox và ghi bằng chứng.

    ``candidate`` là SHA bản đang kiểm — đóng vào bằng chứng để cổng biết
    kết quả này thuộc bản nào (ADR-004 R1)."""
    if name not in TOOLS:
        raise ValueError(f"tool không tồn tại: {name}. Có: {', '.join(sorted(TOOLS))}")

    project = Path(project)
    cfg = config or Config.load(project)
    command = command_for(name, project, cfg)
    if not command:
        res = ToolResult(name=name, ok=False, skipped="dự án chưa khai lệnh cho tool này")
        record(res, story_id, artifact_root, candidate)
        return res

    argv = shlex.split(command) + (extra_args or [])
    level = TOOLS[name].level
    if cfg["sandbox.tools_network"] and level is not sandbox.Level.READ_ONLY:
        # Dự án phải cài phụ thuộc trước khi chạy test được. Mở mạng là
        # quyết định của dự án, khai tường minh, không phải mặc định.
        level = sandbox.Level.WORKSPACE_NETWORK
    sb = sandbox.run(
        sandbox.SandboxSpec(
            workspace=project,
            cmd=argv,
            level=level,
            image=image_for(project, cfg),
            timeout_seconds=cfg["run.timeout_seconds"],
            allow_degraded=cfg["sandbox.allow_degraded"],
            use_docker=cfg["sandbox.use_docker"],
            provider=cfg["sandbox.provider"],
        )
    )
    res = ToolResult(
        name=name,
        ok=sb.ok,
        exit_code=sb.exit_code,
        stdout=sb.stdout,
        stderr=sb.stderr,
        duration_ms=sb.duration_ms,
        degraded=sb.degraded,
        detail={"command": command, **sb.to_evidence()},
    )
    if not sb.ok:
        res.unrunnable = unrunnable_reason(
            name, sb.exit_code, sb.stdout + "\n" + sb.stderr,
            provider_error=sb.provider_error,
        )
    res.log = record(res, story_id, artifact_root, candidate)
    return res


#: Dấu hiệu "công cụ không nạp được", không phải "test đỏ". 127 là mã POSIX
#: cho lệnh không tìm thấy; phần còn lại là cách các hệ chạy khác nói cùng
#: một chuyện. Gộp hai loại lại thì báo cáo chỉ sai chỗ cần sửa.
MISSING_TOOL = (
    "command not found",
    "not found",
    "cannot find module",
    "module_not_found",
    "no such file or directory",
    "is not recognized as an internal or external command",
)


def unrunnable_reason(name: str, exit_code: int, output: str, *, provider_error: str = "") -> str:
    """Lý do một dòng nếu lần chạy là "không chạy được"; "" nếu là kết quả thật.
    Với `test`, chỉ kết luận khi **không test nào xanh** — một test đỏ có
    thông báo "not found" vẫn là test đỏ. ``provider_error`` là lỗi hạ tầng
    sandbox (daemon, kéo image) — lệnh chưa từng chạy, kết luận ngay."""
    if provider_error:
        return f"hạ tầng sandbox lỗi ({provider_error}) — lệnh chưa chạy; kiểm daemon/image rồi chạy lại"
    low = output.lower()
    hit = next((m for m in MISSING_TOOL if m in low), "")
    if exit_code != 127 and not hit:
        return ""
    if name == "test":
        from .testlog import parse as parse_testlog
        if parse_testlog(output).passed:
            return ""
    return f"công cụ chưa cài hoặc không nạp được ({hit or 'exit 127'}) — dựng môi trường hoặc sửa lệnh rồi chạy lại"


#: Tên bản ghi của baseline (ADR-004 R9) — bộ test chạy ở candidate cha
#: **trước** phiên developer. Không ghi là `test`: guard `completion`, TDD
#: `red_before_green`, mục "tiêu chí có test" và sổ hành vi đều đọc
#: `tool_run test` như "lần test của lượt này", và một baseline đỏ sẵn sẽ
#: chặn Stop, làm TDD đạt oan, và bị sổ quy thành hồi quy do story gây ra.
BASELINE_RUN = "test:baseline"

#: Tên bản ghi của nop control (ADR-005 V3) — bộ test chạy ở **SHA cha** với
#: tệp test của story chép vào, **sau** khi đóng băng ứng viên (mang
#: `candidate`). Cùng lý do không ghi là `test`: kết quả mong đợi của nó là
#: **đỏ**, và một lần `test` đỏ sẽ chặn Stop, làm TDD đạt oan, bị sổ quy
#: thành hồi quy.
NOP_RUN = "test:nop"


def record(res: ToolResult, story_id: str, artifact_root, candidate: str = "",
           *, name: str = "", extra: dict | None = None) -> str:
    """Ghi bằng chứng. Không có story_id thì không ghi — tool chạy ngoài
    ngữ cảnh story (ví dụ người gõ tay) không nên làm bẩn hồ sơ story.

    ``name`` ghi dưới tên khác tên tool (baseline ghi `test:baseline`);
    ``extra`` là khoá thêm vào `detail`. Hình dạng bản ghi vẫn ở một chỗ.

    Trả đường dẫn tệp log toàn văn `evidence/<story>-<tool>-<seq>.log` khi
    output dài hơn `TAIL_LINES` (ADR-005 V11 A), "" khi không có gì bị cắt.
    Cả `tail` lẫn log đều đã che bí mật (V1); `detail.redacted` = số chỗ che."""
    if not story_id or artifact_root is None:
        return ""
    full, redacted = res.output()
    lines = full.splitlines()
    detail = {
        "exit_code": res.exit_code,
        "skipped": res.skipped,
        "unrunnable": res.unrunnable,
        "degraded": res.degraded,
        "tail": "\n".join(lines[-TAIL_LINES:]),
        **res.detail,
    }
    if redacted:
        detail["redacted"] = redacted
    if res.name == "test" and not res.skipped:
        # Tên test nào chạy, xanh/đỏ, coverage — cổng tiêu chí (G5) và
        # `coverage.min` (G10b) đọc từ đây, không đọc lại stdout.
        from .testlog import parse as parse_testlog

        detail.update(parse_testlog(full).to_evidence())
    detail.update(extra or {})
    store = EvidenceStore(artifact_root, candidate=candidate)
    event = store.tool_run(
        story_id, name or res.name, ok=res.ok, duration_ms=res.duration_ms, detail=detail,
    )
    if len(lines) <= TAIL_LINES:
        return ""
    # Toàn văn cạnh sổ bằng chứng, tên mang `seq` để khớp đúng bản ghi;
    # `:` của `test:baseline` đổi thành `-` vì tên tệp phải mở được ở mọi hệ.
    log = store.path(story_id).with_name(
        f"{story_id}-{(name or res.name).replace(':', '-')}-{event.seq}.log")
    log.write_text(full + "\n", encoding="utf-8")
    return str(log)


def aisdlc_command() -> str:
    """Lệnh gọi framework mà agent gõ được **thật**.

    Prompt in ra `aisdlc tool test` là vô dụng nếu `aisdlc` không nằm trên
    PATH của phiên agent — nó sẽ nhận "command not found", rồi tự chạy
    pytest bằng tay, và lần chạy đó không vào bằng chứng. Ưu tiên tên trên
    PATH, không có thì dùng đường dẫn tuyệt đối của chính kho này.
    """
    found = shutil.which("aisdlc")
    if found:
        return "aisdlc"
    return str(Path(__file__).resolve().parent.parent.parent / "bin" / "aisdlc")


def describe_tools(project: Path | str, config: Config | None = None) -> str:
    """Bảng tool cho prompt: tên, lệnh thật, và **khi nào gọi**."""
    project = Path(project)
    binary = aisdlc_command()
    lines = []
    for tool in TOOLS.values():
        cmd = command_for(tool.name, project, config) or "(dự án chưa khai)"
        lines.append(f"- `{binary} tool {tool.name}` → `{cmd}`\n  Khi nào: {tool.when}")
    lines.append(
        f"- `{binary} doc <gói> --topic <chủ đề>` → tài liệu thật của thư viện (context7, có cache)\n"
        "  Khi nào: không chắc tên API hay hành vi thư viện — tra, đừng đoán (luật 12). "
        "Thêm `--story <mã>` để lần tra được ghi vào bằng chứng."
    )
    lines.append(
        f"- `{binary} ctx --story <mã>` (hoặc `--file <tệp>`) → bản đồ mã quanh phạm vi ghi: "
        "chữ ký tệp trong phạm vi, tệp gọi/được import, test nhắc tên\n"
        "  Khi nào: vào phiên mới, trước khi tự dò cây thư mục — gợi ý tĩnh, không phải chân lý."
    )
    return "\n".join(lines)
