"""Chạy trình duyệt thật để dựng mockup và trích hợp đồng thị giác.

Playwright là **phụ thuộc tuỳ chọn**: thiếu nó thì framework nói thẳng là
thiếu, không giả vờ vẫn kiểm được. Cùng nguyên tắc với sandbox — thà báo
mức bảo đảm thấp hơn còn hơn im lặng chạy như thể vẫn đủ (bất biến 10).

Một lần mở trình duyệt xử lý cả danh sách màn hình: mở lại chromium cho
từng màn hình tốn vài giây mỗi lần, và dự án có hàng chục màn hình.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "assets" / "render.mjs"

#: Nơi tìm `node_modules` chứa playwright, theo thứ tự ưu tiên.
def _node_paths(project: Path) -> list[Path]:
    repo = Path(__file__).resolve().parent.parent.parent
    return [project / "node_modules", repo / "spike" / "s7" / "node_modules"]


@dataclass
class RenderedScreen:
    id: str
    html: str = ""
    url: str = ""
    png: str = ""
    route: str = ""
    title: str = ""
    snapshot: str = ""
    #: Snapshot của từng vùng `[data-sample]` — nội dung ví dụ, không phải
    #: cam kết. Trừ ra khỏi hợp đồng để cổng không đỏ vì dữ liệu khác nhau.
    sample_snapshots: list[str] = field(default_factory=list)
    fields: list[dict] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class RenderResult:
    screens: list[RenderedScreen] = field(default_factory=list)
    #: Không dựng được gì cả — thiếu node, thiếu playwright, không mở được
    #: chromium. Khác hẳn với "dựng được nhưng trang lỗi".
    unavailable: str = ""

    @property
    def ok(self) -> bool:
        return not self.unavailable and all(s.ok for s in self.screens)

    def by_id(self, screen_id: str) -> RenderedScreen | None:
        return next((s for s in self.screens if s.id == screen_id), None)


def find_playwright(project: Path | str = ".") -> Path | None:
    """Thư mục `node_modules` có playwright, nếu tìm được."""
    for base in _node_paths(Path(project)):
        if (base / "playwright" / "package.json").is_file():
            return base
    return None


def availability(project: Path | str = ".") -> str:
    """Chuỗi rỗng nếu dựng được; ngược lại là lý do không dựng được."""
    if not shutil.which("node"):
        return "chưa cài node — không dựng được mockup để trích hợp đồng"
    if find_playwright(project) is None:
        return (
            "chưa cài playwright — chạy: npm i -D playwright && npx playwright install chromium"
        )
    return ""


def render(
    jobs: list[dict],
    *,
    project: Path | str = ".",
    viewport: tuple[int, int] = (1280, 900),
    timeout: int = 300,
) -> RenderResult:
    """Dựng từng file HTML, trả về snapshot + siêu dữ liệu (và chụp ảnh)."""
    project = Path(project)
    reason = availability(project)
    if reason:
        return RenderResult(unavailable=reason)

    node_modules = find_playwright(project)
    payload = json.dumps({
        "jobs": jobs,
        "viewport": {"width": viewport[0], "height": viewport[1]},
        "playwright": str(node_modules),
    })

    try:
        proc = subprocess.run(
            ["node", str(SCRIPT)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RenderResult(unavailable=f"dựng mockup quá {timeout}s")

    if proc.returncode != 0 and not proc.stdout.strip():
        return RenderResult(unavailable=(proc.stderr or "node thất bại").strip()[:400])

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return RenderResult(unavailable=f"không đọc được kết quả node: {proc.stdout[:200]}")

    if data.get("error"):
        return RenderResult(unavailable=data["error"])

    result = RenderResult()
    for raw in data.get("screens", []):
        result.screens.append(
            RenderedScreen(
                id=raw.get("id", ""),
                html=raw.get("html", ""),
                url=raw.get("url", ""),
                png=raw.get("png", ""),
                route=raw.get("route", ""),
                title=raw.get("title", ""),
                snapshot=raw.get("snapshot", ""),
                sample_snapshots=raw.get("sample_snapshots", []) or [],
                fields=raw.get("fields", []),
                unresolved=raw.get("unresolved", []),
                console_errors=raw.get("console_errors", []),
                error=raw.get("error", ""),
            )
        )
    return result
