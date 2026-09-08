"""Map mockup — **nửa nạp**: đưa đúng một màn hình vào phiên viết code.

Nửa còn lại (`mockup_verify`) đối chiếu ứng dụng thật với hợp đồng. Hai
nửa phải đi cùng nhau: nạp mà không đối chiếu thì mockup chỉ là gợi ý; đối
chiếu mà không nạp thì agent bị chấm điểm theo một hợp đồng nó chưa từng
đọc.

Nguyên tắc ở đây là **nạp ít**: một story dựng màn hình Danh sách thì
không được thấy hợp đồng của Cài đặt. Nạp cả tệp thì agent sẽ dựng luôn
thứ không thuộc story mình — và phần thừa đó không ai đặt hàng, không ai
kiểm, nhưng vẫn phải bảo trì.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..control.design_contract import DesignContract, ScreenContract

#: Số component liệt kê trong prompt trước khi cắt. Hợp đồng dài hàng trăm
#: dòng sẽ đẩy phần hướng dẫn ra khỏi tầm chú ý của model.
MAX_LISTED = 40


@dataclass
class ScreenSlice:
    """Lát cắt một màn hình, dạng sẵn sàng đưa vào prompt."""

    screen: ScreenContract
    mockup_path: Path | None = None
    screenshot_path: Path | None = None
    html: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.screen.id

    def as_prompt(self) -> str:
        s = self.screen
        lines = [
            f"### Screen `{s.id}` — {s.name}",
            f"Route to build: `{s.route}`" if s.route else "Route: (contract not declared)",
        ]
        if s.purpose:
            lines.append(f"Purpose: {s.purpose}")
        # Quy ước cổng phải nói ra, không để agent đoán (lỗi 14, e9 note-editor
        # 2026-09-05: cổng mở `/note/1`, app không có ghi chú `1`, trang trống,
        # story trượt 2 lượt mà không biết vì sao).
        from .mockup_verify import concrete_route

        if s.route and concrete_route(s.route) != s.route:
            lines.append(
                f"The mockup map gate will open `{concrete_route(s.route)}` (dynamic params "
                f"replaced with `1`). The dev environment (`app.dev_command`) must have a record "
                f"with id `1` for this route — seed data — otherwise the gate sees a blank "
                f"page and the story will not pass."
            )

        lines += ["", "**Required** components (role + name, exactly as in mockup):"]
        for c in s.components[:MAX_LISTED]:
            lines.append(f"- {c.role} “{c.name}”")
        if len(s.components) > MAX_LISTED:
            lines.append(f"- … and {len(s.components) - MAX_LISTED} more components (see mockup)")

        if s.data_roles:
            lines += [
                "",
                "Data region — must render from real data, each item is "
                f"{', '.join(s.data_roles)}. The contract does **not** bind "
                "content here (the real app displays different data), only "
                "the element type.",
            ]

        if s.fields:
            lines += ["", "Input constraints (enforce exactly, do not relax):"]
            for f in s.fields:
                bits = [f"type={f.get('type', '')}"]
                if f.get("required"):
                    bits.append("required")
                for key in ("pattern", "minlength", "maxlength", "min", "max"):
                    if f.get(key):
                        bits.append(f"{key}={f[key]}")
                label = f.get("label") or f.get("name") or "(no label)"
                lines.append(f"- {label}: {', '.join(bits)}")

        if s.states:
            lines += ["", "States to build: " + ", ".join(s.states)]

        if self.mockup_path:
            lines += ["", f"Mockup: `{self.mockup_path}`"]
        if self.screenshot_path:
            lines.append(f"Screenshot: `{self.screenshot_path}`")

        lines += [
            "",
            "The story gate compares the real app against the list above using the "
            "accessibility tree. Missing a committed component means **fail**; adding "
            "new components is only a warning. Names must match — that is what the "
            "user reads and what the machine compares.",
        ]
        return "\n".join(lines)


def load_slice(
    contract: DesignContract,
    screen_id: str,
    *,
    artifact_root: Path | str,
    with_html: bool = False,
) -> ScreenSlice | None:
    """Lấy lát cắt của **một** màn hình. None nếu hợp đồng không có nó."""
    screen = contract.by_id(screen_id)
    if screen is None:
        return None

    root = Path(artifact_root)
    sl = ScreenSlice(screen=screen)

    if screen.mockup:
        path = root / screen.mockup
        if path.is_file():
            sl.mockup_path = path
            if with_html:
                sl.html = path.read_text(encoding="utf-8", errors="replace")
        else:
            sl.warnings.append(f"contract points to missing mockup: {screen.mockup}")

    if screen.screenshot:
        shot = root / screen.screenshot
        if shot.is_file():
            sl.screenshot_path = shot

    if not screen.components:
        sl.warnings.append(f"{screen_id}: contract has no components to compare")
    return sl


def load_for_story(
    contract: DesignContract,
    screen_ids: list[str],
    *,
    artifact_root: Path | str,
) -> tuple[list[ScreenSlice], list[str]]:
    """Nạp lát cắt cho các màn hình story khai. Trả kèm mã không tìm thấy."""
    slices, missing = [], []
    for sid in screen_ids:
        sl = load_slice(contract, sid, artifact_root=artifact_root)
        if sl is None:
            missing.append(sid)
        else:
            slices.append(sl)
    return slices, missing


def prompt_section(slices: list[ScreenSlice]) -> str:
    """Phần "Giao diện" của prompt story."""
    if not slices:
        return (
            "This story does not build any screen. Do not add UI — the UI "
            "belongs to another story."
        )
    return "\n\n".join(s.as_prompt() for s in slices)
