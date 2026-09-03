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
            f"### Màn hình `{s.id}` — {s.name}",
            f"Route phải dựng: `{s.route}`" if s.route else "Route: (hợp đồng chưa khai)",
        ]
        if s.purpose:
            lines.append(f"Mục đích: {s.purpose}")

        lines += ["", "Component **phải có** (vai trò + tên gọi, đúng như mockup):"]
        for c in s.components[:MAX_LISTED]:
            lines.append(f"- {c.role} “{c.name}”")
        if len(s.components) > MAX_LISTED:
            lines.append(f"- … và {len(s.components) - MAX_LISTED} component nữa (xem mockup)")

        if s.data_roles:
            lines += [
                "",
                "Vùng dữ liệu — phải dựng được từ dữ liệu thật, mỗi mục là "
                f"{', '.join(s.data_roles)}. Hợp đồng **không** ràng buộc nội "
                "dung ở đây (ứng dụng thật hiển thị dữ liệu khác), chỉ ràng "
                "buộc kiểu phần tử.",
            ]

        if s.fields:
            lines += ["", "Ràng buộc nhập liệu (thực thi đúng, đừng nới lỏng):"]
            for f in s.fields:
                bits = [f"type={f.get('type', '')}"]
                if f.get("required"):
                    bits.append("bắt buộc")
                for key in ("pattern", "minlength", "maxlength", "min", "max"):
                    if f.get(key):
                        bits.append(f"{key}={f[key]}")
                label = f.get("label") or f.get("name") or "(không nhãn)"
                lines.append(f"- {label}: {', '.join(bits)}")

        if s.states:
            lines += ["", "Trạng thái phải dựng: " + ", ".join(s.states)]

        if self.mockup_path:
            lines += ["", f"Mockup: `{self.mockup_path}`"]
        if self.screenshot_path:
            lines.append(f"Ảnh chụp: `{self.screenshot_path}`")

        lines += [
            "",
            "Cổng story đối chiếu ứng dụng thật với danh sách trên bằng cây "
            "accessibility. Thiếu một component đã cam kết là **trượt**; thêm "
            "component mới chỉ là cảnh báo. Tên gọi phải khớp — đó là thứ người "
            "dùng đọc và là thứ máy so.",
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
            sl.warnings.append(f"hợp đồng trỏ tới mockup không có: {screen.mockup}")

    if screen.screenshot:
        shot = root / screen.screenshot
        if shot.is_file():
            sl.screenshot_path = shot

    if not screen.components:
        sl.warnings.append(f"{screen_id}: hợp đồng không có component nào để đối chiếu")
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
            "Story này không dựng màn hình nào. Không thêm giao diện — phần "
            "giao diện thuộc story khác."
        )
    return "\n\n".join(s.as_prompt() for s in slices)
