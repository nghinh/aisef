"""Đối chiếu màn hình thật với hợp đồng thị giác lấy từ mockup.

Đây là nửa sau của bước map mockup (SOLUTION mục 12bis) và là điều kiện
thứ 5 của cổng story.

**Vì sao dùng accessibility tree, không dùng CSS selector hay pixel diff:**

* selector CSS gãy mỗi lần đổi class — bắt lỗi giả, bỏ lọt lỗi thật;
* pixel diff giữa mockup tĩnh và ứng dụng thật **không bao giờ** trùng,
  cổng kiểu đó đỏ liên tục rồi bị tắt, mà một cổng bị tắt còn tệ hơn
  không có cổng;
* accessibility tree mang **ý nghĩa ngữ nghĩa** (vai trò + tên gọi), bền
  trước thay đổi giao diện, và kiểm luôn được khả năng tiếp cận.

Đầu vào là kết quả `page.locator('body').ariaSnapshot()` của Playwright —
định dạng đã xác lập bằng thực nghiệm ở spike S7.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Vai trò mang hợp đồng. Node `text:` thuần và node bố cục bị bỏ qua:
#: chúng là chi tiết trình bày, không phải thứ mockup cam kết.
CONTRACT_ROLES = frozenset({
    "button", "textbox", "checkbox", "radio", "link", "combobox",
    "listbox", "option", "slider", "switch", "spinbutton", "searchbox",
    "tab", "menuitem", "heading", "img", "table", "progressbar", "alert",
})

_LINE = re.compile(r'^\s*-\s+([a-z]+)(?:\s+"([^"]*)")?')


@dataclass(frozen=True)
class Component:
    role: str
    name: str

    def __str__(self) -> str:
        return f'{self.role} "{self.name}"'


@dataclass
class MapResult:
    """Kết quả đối chiếu một màn hình."""

    screen_id: str = ""
    route: str = ""
    contract: list[Component] = field(default_factory=list)
    actual: list[Component] = field(default_factory=list)
    missing: list[Component] = field(default_factory=list)
    extra: list[Component] = field(default_factory=list)
    #: Vai trò hợp đồng hứa có trong vùng dữ liệu nhưng ứng dụng không dựng
    #: mục nào. So theo tên ở vùng này là vô nghĩa (dữ liệu khác nhau), còn
    #: không so gì thì bỏ lọt cả một danh sách rỗng.
    missing_data_roles: list[str] = field(default_factory=list)

    @property
    def matched(self) -> int:
        return len(self.contract) - len(self.missing)

    @property
    def passed(self) -> bool:
        """Chỉ `missing` mới chặn.

        Ứng dụng thật được phép có thêm phần tử hợp lý (nút phụ, banner),
        nhưng **không được thiếu** thứ hợp đồng đã hứa.
        """
        return not self.missing and not self.missing_data_roles

    def to_evidence(self) -> dict:
        return {
            "screen_id": self.screen_id,
            "route": self.route,
            "contract_components": len(self.contract),
            "matched": self.matched,
            "missing": [str(c) for c in self.missing],
            "missing_data_roles": self.missing_data_roles,
            "extra": [str(c) for c in self.extra],
            "passed": self.passed,
        }

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        parts = [f"{self.screen_id or 'screen'}: {verdict} ({self.matched}/{len(self.contract)})"]
        if self.missing:
            parts.append("  thiếu: " + ", ".join(str(c) for c in self.missing))
        if self.missing_data_roles:
            parts.append(
                "  vùng dữ liệu không dựng mục nào kiểu: "
                + ", ".join(self.missing_data_roles)
            )
        if self.extra:
            parts.append("  thừa (cảnh báo): " + ", ".join(str(c) for c in self.extra))
        return "\n".join(parts)


def parse_aria_snapshot(text: str) -> list[Component]:
    """Đọc cây aria của Playwright thành danh sách component có hợp đồng.

    Bỏ node không thuộc `CONTRACT_ROLES` và node không có tên gọi — một
    phần tử không tên thì không kiểm chứng được, và cũng là dấu hiệu vấn
    đề khả năng tiếp cận.
    """
    out: list[Component] = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        role, name = m.group(1), (m.group(2) or "").strip()
        if role in CONTRACT_ROLES and name:
            out.append(Component(role, name))
    return out


def compare(
    contract: list[Component],
    actual: list[Component],
    *,
    screen_id: str = "",
    route: str = "",
    data_roles: list[str] | None = None,
) -> MapResult:
    """So hợp đồng với thực tế.

    So theo **tập hợp** chứ không theo thứ tự: mockup và ứng dụng thật có
    thể sắp xếp khác nhau mà vẫn đúng hợp đồng. Vị trí là chuyện của
    người đánh giá thị giác, không phải của cổng tất định.
    """
    want, have = set(contract), set(actual)
    roles_present = {c.role for c in actual}
    return MapResult(
        screen_id=screen_id,
        route=route,
        contract=list(contract),
        actual=list(actual),
        missing=[c for c in contract if c not in have],
        extra=[c for c in actual if c not in want],
        missing_data_roles=[r for r in (data_roles or []) if r not in roles_present],
    )


def compare_snapshots(
    contract_snapshot: str,
    actual_snapshot: str,
    *,
    screen_id: str = "",
    route: str = "",
    data_roles: list[str] | None = None,
) -> MapResult:
    """Tiện ích: đối chiếu trực tiếp hai chuỗi aria snapshot."""
    return compare(
        parse_aria_snapshot(contract_snapshot),
        parse_aria_snapshot(actual_snapshot),
        screen_id=screen_id,
        route=route,
        data_roles=data_roles,
    )
