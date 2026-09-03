"""Hợp đồng thị giác — cầu nối giữa mockup và code.

Mockup là thứ người nhìn; hợp đồng là thứ máy kiểm. Nó được trích từ
**mockup đã dựng trong trình duyệt thật**, không đọc HTML bằng regex: cái
người dùng thấy mới là cam kết, còn thẻ nằm trong HTML mà CSS ẩn đi thì
không.

Hai chỗ dùng, và đó là lý do file này tồn tại:

* **cổng mockup (GĐ-5)** — mọi màn hình trong EXPERIENCE.md phải có mockup,
  không còn chỗ nào tự khai là chưa chốt;
* **bước map mockup (GĐ-6.7a)** — agent viết một story chỉ được nạp
  ``slice_for(screen_id)``: đúng một màn hình. Nạp cả tệp thì nó sẽ dựng
  luôn thứ không thuộc story mình.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..harness.aria import Component, parse_aria_snapshot
from .experience import Experience, Screen

CONTRACT_FILE = "design-contract.json"
CONTRACT_VERSION = 1


@dataclass
class ScreenContract:
    id: str
    name: str = ""
    route: str = ""
    purpose: str = ""
    mockup: str = ""
    screenshot: str = ""
    #: Khung giao diện — cam kết theo (vai trò, tên gọi).
    components: list[Component] = field(default_factory=list)
    #: Vai trò xuất hiện trong vùng dữ liệu mẫu. Ứng dụng thật hiển thị dữ
    #: liệu khác, nên chỉ cam kết **có mặt**, không cam kết tên gọi.
    data_roles: list[str] = field(default_factory=list)
    fields: list[dict] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    #: Chỗ mockup tự khai là chưa chốt (`data-unresolved`). Còn mục nào thì
    #: cổng chặn: dựng code theo một màn hình chưa chốt là làm lại hai lần.
    unresolved: list[str] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "route": self.route,
            "purpose": self.purpose,
            "mockup": self.mockup,
            "screenshot": self.screenshot,
            "components": [{"role": c.role, "name": c.name} for c in self.components],
            "data_roles": self.data_roles,
            "fields": self.fields,
            "states": self.states,
            "unresolved": self.unresolved,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScreenContract":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            route=data.get("route", ""),
            purpose=data.get("purpose", ""),
            mockup=data.get("mockup", ""),
            screenshot=data.get("screenshot", ""),
            components=[
                Component(c.get("role", ""), c.get("name", ""))
                for c in data.get("components", [])
            ],
            data_roles=data.get("data_roles", []),
            fields=data.get("fields", []),
            states=data.get("states", []),
            unresolved=data.get("unresolved", []),
            error=data.get("error", ""),
        )


@dataclass
class DesignContract:
    screens: list[ScreenContract] = field(default_factory=list)
    version: int = CONTRACT_VERSION

    def by_id(self, screen_id: str) -> ScreenContract | None:
        return next((s for s in self.screens if s.id == screen_id), None)

    @property
    def ids(self) -> list[str]:
        return [s.id for s in self.screens]

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "screens": [s.as_dict() for s in self.screens],
        }

    def slice_for(self, screen_id: str) -> dict | None:
        """Lát cắt một màn hình — đầu vào của bước map mockup lúc viết code."""
        screen = self.by_id(screen_id)
        return screen.as_dict() if screen else None

    def write(self, artifact_root: Path | str) -> Path:
        path = Path(artifact_root) / CONTRACT_FILE
        path.write_text(
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path


def load(artifact_root: Path | str) -> DesignContract:
    path = Path(artifact_root) / CONTRACT_FILE
    if not path.is_file():
        return DesignContract()
    data = json.loads(path.read_text(encoding="utf-8"))
    return DesignContract(
        version=int(data.get("version") or CONTRACT_VERSION),
        screens=[ScreenContract.from_dict(s) for s in data.get("screens", [])],
    )


def build(
    experience: Experience,
    rendered,
    *,
    artifact_root: Path | str = ".",
) -> DesignContract:
    """Ghép danh sách màn hình (EXPERIENCE.md) với kết quả dựng mockup.

    Màn hình có trong EXPERIENCE.md mà chưa dựng được vẫn **có mặt** trong
    hợp đồng, kèm lý do. Bỏ nó đi thì hợp đồng trông đầy đủ trong khi thực
    tế thiếu một màn hình — đúng loại lỗi mà cổng sinh ra để bắt.
    """
    root = Path(artifact_root)
    contract = DesignContract()

    for screen in experience.screens:
        contract.screens.append(_one(screen, rendered.by_id(screen.id) if rendered else None, root))
    return contract


def _rel(root: Path, path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return path


def _one(screen: Screen, rendered, root: Path) -> ScreenContract:
    out = ScreenContract(
        id=screen.id,
        name=screen.name,
        purpose=screen.purpose,
        states=list(screen.states),
    )
    if rendered is None:
        out.error = "chưa dựng được mockup cho màn hình này"
        return out
    if rendered.error:
        out.error = rendered.error
        return out

    out.route = rendered.route
    out.mockup = _rel(root, rendered.html)
    out.screenshot = _rel(root, rendered.png)
    everything = parse_aria_snapshot(rendered.snapshot)
    in_samples = [
        c for snap in getattr(rendered, "sample_snapshots", []) or []
        for c in parse_aria_snapshot(snap)
    ]
    sample_set = set(in_samples)
    out.components = [c for c in everything if c not in sample_set]
    out.data_roles = sorted({c.role for c in in_samples})
    out.fields = rendered.fields
    out.unresolved = list(rendered.unresolved)
    if rendered.console_errors:
        out.error = f"mockup lỗi javascript: {rendered.console_errors[0][:200]}"
    return out
