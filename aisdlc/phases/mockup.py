"""Bước 3 — dựng mockup HTML cho từng màn hình, rồi trích hợp đồng thị giác.

Chia việc theo đúng nguyên tắc gốc:

* **Cần phán đoán → giao model.** Bố cục, nhịp thị giác, chọn chữ cho nút:
  mỗi màn hình một phiên riêng, chỉ nạp lát cắt của màn hình đó.
* **Cần đảm bảo → viết code.** Dựng trang trong trình duyệt, trích
  component và ràng buộc nhập liệu, kiểm đủ màn hình, sinh trang mục lục:
  đều là việc có đáp án đúng, không hỏi model.

Màn hình độc lập nhau nên chạy lại chỉ dựng phần còn thiếu — mockup đã có
thì bỏ qua, không trả tiền hai lần.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter, RunSpec
from ..config import Config
from ..control.design_contract import CONTRACT_FILE, DesignContract, build
from ..control.experience import Experience, Screen, parse_experience_file
from ..control.machine_gate import GateResult, check_design_contract
from ..harness import browser
from ..harness.prompts import load_catalog

MOCKUP_DIR = "mockups"
SKILL = "aisdlc-mockup-html"


@dataclass
class MockupResult:
    experience: Experience | None = None
    contract: DesignContract | None = None
    generated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    gate: GateResult | None = None
    index_path: Path | None = None
    cost_usd: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        if self.error or self.failed:
            return False
        return bool(self.gate and self.gate.passed)

    @property
    def needs_human(self) -> bool:
        """Cổng mockup **luôn** đáng để người nhìn: máy kiểm được có đủ
        component không, không kiểm được nó có dùng được không."""
        return True

    def machine_checks(self) -> dict[str, str]:
        checks = {"màn hình": str(len(self.experience.screens) if self.experience else 0)}
        if self.gate:
            checks["cổng máy"] = "đạt" if self.gate.passed else "không đạt"
            if self.gate.warnings:
                checks["cảnh báo"] = "; ".join(self.gate.warnings)
        return checks

    def summary(self) -> str:
        if self.error:
            return f"mockup: ✗ {self.error}"
        n = len(self.experience.screens) if self.experience else 0
        lines = [
            f"mockup: {n} màn hình — dựng mới {len(self.generated)}, "
            f"bỏ qua {len(self.skipped)}"
        ]
        for sid, why in self.failed.items():
            lines.append(f"  ✗ {sid}: {why}")
        if self.cost_usd:
            lines.append(f"  chi phí: ${self.cost_usd:.2f}")
        if self.gate:
            lines.append(self.gate.summary())
        if self.index_path:
            lines.append(f"  mở xem: {self.index_path}")
        return "\n".join(lines)


def build_prompt(screen: Screen, experience: Experience, artifact_root: Path) -> str:
    """Prompt cho một màn hình — chỉ lát cắt của nó, không phải cả tài liệu."""
    rules = [
        f"- {name}: {experience.component_rules.get(name, '')}".rstrip(": ")
        for name in screen.components
    ]
    return load_catalog().get("mockup-screen").render(
        {
            "screen_id": screen.id,
            "screen_name": screen.name,
            "purpose": screen.purpose or "(tài liệu không nêu)",
            "reached_from": screen.reached_from or "(tài liệu không nêu)",
            "route": (
                f"`{screen.route}` — đặt đúng chuỗi này vào thẻ meta aisdlc-route"
                if screen.route
                else "(tài liệu không khai — tự chọn đường dẫn hợp lý và khai vào meta)"
            ),
            "components": "\n".join(rules) or "- (tài liệu không nêu)",
            "states": ", ".join(screen.states) or "(chỉ trạng thái chính)",
            "artifact_root": artifact_root.name,
            "output": f"{artifact_root.name}/{MOCKUP_DIR}/{screen.id}.html",
        }
    )


def mockup_path(artifact_root: Path, screen_id: str) -> Path:
    return artifact_root / MOCKUP_DIR / f"{screen_id}.html"


def generate(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    force: bool = False,
    only: list[str] | None = None,
) -> MockupResult:
    """Dựng mockup còn thiếu, trích hợp đồng, chạy cổng máy."""
    from .plan import ARTIFACT_ROOT

    project = Path(project)
    root = project / ARTIFACT_ROOT
    cfg = config or Config.load(project)
    res = MockupResult()

    exp_file = root / "EXPERIENCE.md"
    if not exp_file.is_file():
        res.error = "chưa có EXPERIENCE.md — chạy `aisdlc plan` trước"
        return res

    res.experience = parse_experience_file(exp_file)
    if not res.experience.screens:
        res.error = "EXPERIENCE.md không liệt kê màn hình nào"
        return res

    (root / MOCKUP_DIR).mkdir(parents=True, exist_ok=True)

    for screen in res.experience.screens:
        if only and screen.id not in only:
            continue
        path = mockup_path(root, screen.id)
        if path.is_file() and not force:
            res.skipped.append(screen.id)
            continue

        run = client.run(
            RunSpec(
                prompt=build_prompt(screen, res.experience, root),
                workdir=project,
                max_turns=cfg["run.max_turns"],
                timeout_seconds=cfg["run.timeout_seconds"],
            )
        )
        res.cost_usd += run.cost_usd
        if not run.ok:
            res.failed[screen.id] = run.error or "lượt chạy thất bại"
            continue
        if not path.is_file():
            res.failed[screen.id] = f"chạy xong nhưng không thấy {path.name}"
            continue
        res.generated.append(screen.id)

    res.contract, gate_extra = extract(root, res.experience)
    res.gate = gate_extra
    res.index_path = write_index(root, res)
    return res


def extract(
    artifact_root: Path,
    experience: Experience,
    stories: list | None = None,
) -> tuple[DesignContract, GateResult]:
    """Dựng mockup trong trình duyệt thật rồi trích hợp đồng + chạy cổng."""
    jobs = []
    for screen in experience.screens:
        html = mockup_path(artifact_root, screen.id)
        if html.is_file():
            jobs.append({
                "id": screen.id,
                "html": str(html),
                "png": str(html.with_suffix(".png")),
            })

    rendered = browser.render(jobs, project=artifact_root.parent)
    if rendered.unavailable:
        gate = GateResult("cổng máy: mockup")
        # Không giả vờ đạt. Thiếu trình duyệt thì hợp đồng không tồn tại, và
        # bước map mockup ở GĐ-6 sẽ không có gì để đối chiếu.
        gate.errors.append(f"không trích được hợp đồng: {rendered.unavailable}")
        return DesignContract(), gate

    contract = build(experience, rendered, artifact_root=artifact_root)
    contract.write(artifact_root)
    return contract, check_design_contract(contract, experience, stories)


def write_index(artifact_root: Path, res: MockupResult) -> Path | None:
    """Trang mục lục — để người duyệt xem hết màn hình bằng một lần mở.

    Cổng mockup là cổng người: bắt họ mở lần lượt sáu file thì phần lớn sẽ
    chỉ mở file đầu.
    """
    if not res.experience:
        return None
    rows = []
    for screen in res.experience.screens:
        c = res.contract.by_id(screen.id) if res.contract else None
        html = f"{screen.id}.html"
        exists = mockup_path(artifact_root, screen.id).is_file()
        status = "—"
        if c and c.error:
            status = f'<span class="bad">{_esc(c.error)}</span>'
        elif c and c.unresolved:
            status = f'<span class="warn">{len(c.unresolved)} chỗ chưa chốt</span>'
        elif c:
            status = f'<span class="ok">{len(c.components)} component · route {_esc(c.route or "?")}</span>'
        elif not exists:
            status = '<span class="bad">chưa dựng</span>'

        shot = f'<img src="{screen.id}.png" alt="{_esc(screen.name)}">' if (
            artifact_root / MOCKUP_DIR / f"{screen.id}.png"
        ).is_file() else '<div class="noshot">chưa có ảnh</div>'

        link = f'<a href="{html}">{_esc(screen.name)}</a>' if exists else _esc(screen.name)
        rows.append(
            f'<figure><figcaption><h2>{link}</h2>'
            f'<p class="purpose">{_esc(screen.purpose)}</p>'
            f'<p class="status">{status}</p></figcaption>{shot}</figure>'
        )

    html_doc = _INDEX_TEMPLATE.format(count=len(res.experience.screens), rows="\n".join(rows))
    path = artifact_root / MOCKUP_DIR / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return path


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_INDEX_TEMPLATE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mockup — {count} màn hình</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0; padding: 2rem;
         background: Canvas; color: CanvasText; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 1.5rem; }}
  figure {{ margin: 0 0 2.5rem; }}
  figcaption h2 {{ font-size: 1.1rem; margin: 0 0 .25rem; }}
  .purpose {{ margin: 0; opacity: .75; }}
  .status {{ margin: .25rem 0 .75rem; font-size: .85rem; }}
  .ok {{ color: #1a7f37; }} .warn {{ color: #9a6700; }} .bad {{ color: #c0392b; }}
  img {{ max-width: 100%; border: 1px solid rgba(128,128,128,.4); border-radius: 6px; }}
  .noshot {{ padding: 2rem; border: 1px dashed rgba(128,128,128,.5);
            border-radius: 6px; text-align: center; opacity: .6; }}
  a {{ color: inherit; }}
</style></head>
<body>
<h1>Mockup — {count} màn hình</h1>
{rows}
</body></html>
"""


def describe_contract(data: dict, artifact_root: Path) -> str:
    """Tóm tắt hợp đồng thị giác cho người duyệt.

    Người duyệt mockup cần **nhìn**, nên thứ đầu tiên phải là đường dẫn
    trang mục lục; phần chữ chỉ nói cái mắt không thấy: component nào đã
    thành cam kết máy sẽ kiểm.
    """
    lines = [f"Mở xem: {artifact_root / MOCKUP_DIR / 'index.html'}", ""]
    for screen in data.get("screens", []):
        head = f"{screen['id']:14} {screen.get('name', '')}"
        if screen.get("error"):
            lines.append(f"  ✗ {head} — {screen['error']}")
            continue
        lines.append(f"  {head}  route {screen.get('route') or '?'}")
        comps = screen.get("components", [])
        shown = ", ".join(f"{c['role']} \"{c['name']}\"" for c in comps[:6])
        more = f" … +{len(comps) - 6}" if len(comps) > 6 else ""
        lines.append(f"      cam kết: {shown or '(không có)'}{more}")
        req = [f["label"] or f["name"] for f in screen.get("fields", []) if f.get("required")]
        if req:
            lines.append(f"      bắt buộc nhập: {', '.join(req)}")
        for u in screen.get("unresolved", []):
            lines.append(f"      ⚠️  chưa chốt: {u}")
    return "\n".join(lines)
