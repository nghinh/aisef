"""Bước 6 — DevSecOps: cổng trước triển khai và bộ khung vận hành.

Chia đúng theo nguyên tắc gốc:

* **Cần đảm bảo → viết code.** Cổng trước triển khai và quy trình CI là
  những thứ có đáp án đúng: mọi story đã xong chưa, bộ kiểm định đã chạy
  đủ chưa, cổng nào chưa có người duyệt. Không hỏi model.
* **Cần phán đoán → giao model.** Dockerfile cho stack này, manifest triển
  khai, runbook cho hệ này — mỗi dự án một khác. Model viết, rồi **kiểm
  bằng code**: image có build được không, runbook có đủ bốn mục không.

Runbook bị kiểm bốn mục vì một runbook thiếu mục "leo thang" chỉ hữu ích
với người đã biết phải gọi ai — tức là người không cần runbook.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter, RunSpec
from ..config import Config
from ..control.approvals import (
    GATE_ORDER,
    PRE_DEPLOY_REPORT,
    ApprovalStore,
    Gate,
    Status,
)
from ..control.outcome import Check, Outcome
from ..control.state import StateStore, StoryStatus
from .qa import QaReport, run_suite

CI_PATH = ".github/workflows/aisdlc.yml"

#: Cách CI cài framework. Để người dùng đổi được khi họ phát hành nội bộ
#: hoặc dùng bản từ git.
INSTALL_SPEC = "ai-sdlc"
RUNBOOK_PATH = "docs/RUNBOOK.md"

#: Bốn mục một runbook phải có. Thiếu mục nào cũng làm nó vô dụng đúng lúc
#: cần nhất — lúc 3 giờ sáng, với người trực chưa từng đọc hệ này.
RUNBOOK_SECTIONS = ("triệu chứng", "chẩn đoán", "xử lý", "leo thang")


@dataclass
class PreDeployReport:
    checks: list[Check] = field(default_factory=list)
    qa: QaReport | None = None
    #: Lý do chấp nhận suy biến, nếu có — là bằng chứng của cổng, nên ghi
    #: ra đĩa cùng kết quả chứ không chỉ nằm trong cấu hình.
    degraded_waiver: str = ""

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [c.as_dict() for c in self.checks],
            "qa": None if self.qa is None else {
                "release_ready": self.qa.release_ready,
                "failed": [r.kind.id for r in self.qa.failed],
                "unconfigured": [r.kind.id for r in self.qa.unconfigured],
                "degraded": [r.kind.id for r in self.qa.degraded],
                "fake_tests": self.qa.fake_tests,
            },
            "degraded_waiver": self.degraded_waiver,
        }

    def write(self, artifact_root: Path | str) -> Path:
        """Ghi kết quả ra đĩa — đây là thứ người đọc trước khi ký cổng
        `pre-deploy`, và là nội dung phê duyệt gắn vào."""
        import json

        path = Path(artifact_root) / PRE_DEPLOY_REPORT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def summary(self) -> str:
        lines = [f"Cổng trước triển khai: {'ĐẠT' if self.passed else 'KHÔNG ĐẠT'}"]
        lines += [c.line() for c in self.checks]
        if self.qa and not self.qa.release_ready:
            lines.append(self.qa.summary())
        return "\n".join(lines)


def _isolation_check(report: PreDeployReport, cfg: Config) -> Check:
    """Kiểm định có chạy trong Docker không, và nếu không thì có được phép không."""
    degraded = [r.kind.id for r in report.qa.degraded] if report.qa else []
    if not degraded:
        if report.qa and not any(r.ran for r in report.qa.results):
            return Check("cách ly", Outcome.UNCONFIGURED, "không có lần chạy nào để biết")
        return Check("cách ly", True, "kiểm định chạy trong Docker")
    waiver = str(cfg.get("sandbox.pre_deploy_degraded_waiver", "") or "").strip()
    if waiver:
        report.degraded_waiver = waiver
        return Check(
            "cách ly", True,
            f"suy biến ({', '.join(degraded)}) — chấp nhận theo khai báo: {waiver}",
        )
    return Check(
        "cách ly", False,
        f"{', '.join(degraded)} chạy ngoài Docker. Cổng trước triển khai không "
        f"chấp nhận suy biến; dựng Docker, hoặc khai lý do ở "
        f"`sandbox.pre_deploy_degraded_waiver` để ghi vào bằng chứng.",
    )


def check_runbook(path: Path) -> Check:
    if not path.is_file():
        return Check("runbook", False, f"chưa có {path.name}")
    text = path.read_text(encoding="utf-8", errors="replace").lower()
    missing = [s for s in RUNBOOK_SECTIONS if s not in text]
    if missing:
        return Check("runbook", False, f"thiếu mục: {', '.join(missing)}")
    return Check("runbook", True)



def _planned_but_never_run(artifact_root: Path, registered: set[str]) -> list[str]:
    """Mã story trong `stories.index.json` không có bản ghi trạng thái nào."""
    from .run import load_plan

    plan = load_plan(artifact_root)
    if plan.error:
        return []  # không có kế hoạch đọc được thì không kết luận gì thêm
    return [sid for sid in plan.stories if sid not in registered]

def pre_deploy(
    project: Path | str,
    *,
    config: Config | None = None,
    has_ui: bool = True,
    skip_qa: bool = False,
) -> PreDeployReport:
    """Chấm cổng trước triển khai — chỉ đọc trạng thái, không sửa gì."""
    project = Path(project)
    artifact_root = project / "_bmad-output"
    cfg = config or Config.load(project)
    report = PreDeployReport()

    state = StateStore(artifact_root).load()
    if not state.stories:
        report.checks.append(Check("story", False, "chưa story nào chạy"))
    else:
        # Triển khai là triển khai nhánh chính. `verified` là qua cổng mà
        # chưa merge (G12) — với cổng này nó chưa xong, và phải được gọi
        # tên riêng: "chưa xong" và "xong nhưng kẹt merge" cần hai cách sửa.
        chua_merge = [
            r.id for r in state.stories.values() if r.state is StoryStatus.VERIFIED
        ]
        not_done = [
            r.id for r in state.stories.values()
            if r.state not in (StoryStatus.DONE, StoryStatus.VERIFIED)
        ]
        # Story có trong kế hoạch mà chưa từng được đăng ký thì không "xong":
        # e9 2026-09-05, 01-06/01-07 chưa chạy bao giờ mà cổng ghi ✅ vì chỉ
        # đếm bản ghi trạng thái. Chưa chạy ≠ đạt.
        chua_chay = _planned_but_never_run(artifact_root, set(state.stories))
        not_done += chua_chay
        detail = ""
        if not_done:
            detail = f"{len(not_done)} chưa xong: {', '.join(not_done[:5])}"
            if chua_chay:
                detail += f" (chưa từng chạy: {', '.join(chua_chay[:5])})"
        if chua_merge:
            detail += ("; " if detail else "") + (
                f"{len(chua_merge)} xong nhưng chưa merge: {', '.join(chua_merge[:5])}"
            )
        report.checks.append(
            Check("mọi story xong", not not_done and not chua_merge, detail)
        )

    approvals = ApprovalStore(artifact_root)
    pending = [
        g.value for g in GATE_ORDER
        if g is not Gate.PRE_DEPLOY and approvals.status(g) is not Status.APPROVED
    ]
    report.checks.append(
        Check("cổng người", not pending, "" if not pending else f"chưa duyệt: {', '.join(pending)}")
    )

    if not skip_qa:
        report.qa = run_suite(project, config=cfg, has_ui=has_ui)
        report.checks.append(
            Check(
                "kiểm định",
                report.qa.release_ready,
                "" if report.qa.release_ready else "xem chi tiết bên dưới",
            )
        )
        # Quyết định 2026-09-05: cổng trước triển khai **không** chấp nhận
        # kiểm định chạy ngoài Docker, trừ khi có lý do khai tường minh —
        # và lý do ấy ghi vào báo cáo cổng, vì đó là bằng chứng người ký
        # cổng phải nhìn thấy. Bộ kiểm định vẫn chạy (suy biến) để người
        # đọc có kết quả; chỉ phán quyết là khác.
        report.checks.append(_isolation_check(report, cfg))

    if skip_qa:
        report.checks.append(
            Check("cách ly", Outcome.NOT_APPLICABLE, "bỏ qua cùng bộ kiểm định")
        )

    dockerfile = project / "Dockerfile"
    report.checks.append(
        Check("Dockerfile", dockerfile.is_file(), "" if dockerfile.is_file() else "chưa có")
    )
    report.checks.append(
        Check("quy trình CI", (project / CI_PATH).is_file(),
              "" if (project / CI_PATH).is_file() else f"chưa có {CI_PATH}")
    )
    report.checks.append(check_runbook(project / RUNBOOK_PATH))
    return report


def write_ci_workflow(
    project: Path | str,
    *,
    aisdlc_bin: str = "aisdlc",
    install_spec: str = INSTALL_SPEC,
) -> Path:
    """Sinh quy trình CI nối đúng các cổng đã có.

    CI chạy lại **cùng bộ lệnh** người chạy trên máy mình. Viết một quy
    trình riêng cho CI là cách chắc chắn để hai bên trôi khỏi nhau, rồi
    "chạy được trên máy tôi" thành một cuộc tranh luận thay vì một sự thật
    kiểm được.

    ``aisdlc_bin`` mặc định là tên lệnh trên PATH, **không** phải đường
    dẫn tuyệt đối của máy sinh ra tệp: đường ấy không tồn tại trên máy
    chạy CI, và quy trình hỏng ngay bước đầu.
    """
    path = Path(project) / CI_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _CI_TEMPLATE.format(bin=aisdlc_bin, install=install_spec), encoding="utf-8"
    )
    return path


_CI_TEMPLATE = """# Sinh bởi `aisdlc devsecops` — chạy đúng bộ lệnh người chạy trên máy mình.
name: aisdlc

on:
  pull_request:
  push:
    branches: [main, master]

jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # Đường dẫn tuyệt đối của máy sinh ra quy trình này không tồn tại
      # trên máy chạy CI. Cài rồi gọi từ PATH.
      #
      # `{install}` phải là thứ pip thật sự cài được: tên gói trên PyPI
      # nếu đã phát hành, hoặc `git+https://…` / đường dẫn tới bản sao kho
      # nguồn nếu chưa. Đổi bằng `--install-spec` khi sinh lại.
      - name: Cài AI-SDLC
        run: pip install --quiet {install}

      # Kho skill (~93 MB) không nằm trong gói. Cache lại để mỗi lượt CI
      # không phải clone lần nữa.
      - name: Cache kho skill
        uses: actions/cache@v4
        with:
          path: ~/.cache/ai-sdlc/references
          key: aisdlc-references-${{{{ hashFiles('.ai/config.json') }}}}

      - name: Môi trường
        run: {bin} doctor

      - name: Hậu kiểm guard trên diff
        run: {bin} verify

      - name: Kiểm định
        run: {bin} qa

      - name: Cổng phê duyệt
        run: {bin} gates

      - name: Trạng thái story
        run: {bin} status
"""


_SECTION = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)


def build_prompt(project: Path, stack_summary: str) -> str:
    """Prompt cho phần model viết: Dockerfile, IaC, quan sát, runbook."""
    from ..harness.prompts import load_catalog

    return load_catalog().get("devsecops").render({
        "project_name": project.name,
        "stack": stack_summary or "(chưa dò được — đọc mã nguồn để xác định)",
        "runbook_sections": ", ".join(RUNBOOK_SECTIONS),
        "ci_path": CI_PATH,
        "runbook_path": RUNBOOK_PATH,
    })


@dataclass
class DevSecOpsReport:
    generated: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    ci_path: Path | None = None
    cost_usd: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and not self.missing

    def summary(self) -> str:
        if self.error:
            return f"devsecops: ✗ {self.error}"
        # Đếm cả quy trình CI: nó cũng là một tạo tác sinh ra, và in "sinh
        # 2" rồi liệt kê 3 dòng làm người đọc nghi ngờ cả phần còn lại.
        n = len(self.generated) + (1 if self.ci_path else 0)
        lines = [f"devsecops: sinh {n} tạo tác"]
        if self.ci_path:
            lines.append(f"  ✅ {CI_PATH}")
        for name in self.generated:
            lines.append(f"  ✅ {name}")
        for name in self.missing:
            lines.append(f"  ✗ thiếu {name}")
        if self.cost_usd:
            lines.append(f"  chi phí: ${self.cost_usd:.2f}")
        return "\n".join(lines)


#: Tạo tác bắt buộc phải có sau khi chạy. Kiểm bằng code, không tin lời khai.
REQUIRED_ARTIFACTS = ("Dockerfile", RUNBOOK_PATH)


def generate(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    aisdlc_bin: str = "aisdlc",
    install_spec: str = INSTALL_SPEC,
    force: bool = False,
) -> DevSecOpsReport:
    """Sinh quy trình CI (bằng code) và bộ khung vận hành (bằng model)."""
    from ..kit.detect_stack import detect_file

    # `resolve()`: prompt dùng `project.name`, và `Path(".").name` là
    # chuỗi rỗng. CLI đã tuyệt đối hoá ở cửa vào, nhưng hàm này gọi được
    # thẳng từ mã khác — chỗ duy nhất cần `.name` thì tự lo lấy.
    project = Path(project).resolve()
    cfg = config or Config.load(project)
    report = DevSecOpsReport()
    report.ci_path = write_ci_workflow(
        project, aisdlc_bin=aisdlc_bin, install_spec=install_spec
    )

    have = [name for name in REQUIRED_ARTIFACTS if (project / name).is_file()]
    if len(have) == len(REQUIRED_ARTIFACTS) and not force:
        report.generated = list(have)
        return report

    req = project / "docs" / "requirements.md"
    stack = detect_file(req).summary() if req.is_file() else ""

    result = client.run(
        RunSpec(
            prompt=build_prompt(project, stack),
            workdir=project,
            max_turns=cfg["run.max_turns"],
            timeout_seconds=cfg["run.timeout_seconds"],
        )
    )
    report.cost_usd = result.cost_usd
    if not result.ok:
        report.error = result.error or "lượt chạy thất bại"
        return report

    for name in REQUIRED_ARTIFACTS:
        (report.generated if (project / name).is_file() else report.missing).append(name)

    runbook = check_runbook(project / RUNBOOK_PATH)
    if not runbook.passed and RUNBOOK_PATH not in report.missing:
        report.missing.append(f"{RUNBOOK_PATH} ({runbook.detail})")
        report.generated = [g for g in report.generated if g != RUNBOOK_PATH]
    return report
