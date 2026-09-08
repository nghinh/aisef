"""Đọc JSON status mà BMAD trả về khi chạy ở chế độ headless.

BMAD tự định nghĩa hợp đồng này (`assets/headless-schemas.md` trong mỗi
skill), và nó khớp gần như một-một với cổng phê duyệt của framework:

===============  ==========================================================
``complete``     artifact đứng được một mình → đủ điều kiện tự duyệt
``partial``      có artifact nhưng còn ``open_questions`` → **phải** người xem
``blocked``      không sinh được artifact → dừng, báo lý do
===============  ==========================================================

Nghĩa là ta không phải tự nghĩ ra cơ chế "khi nào cần hỏi người" — BMAD
đã trả lời sẵn, chỉ cần đọc cho đúng.

BMAD đặt JSON ở cuối phần trả lời, thường trong khối ```json nhưng không
phải lúc nào cũng có rào. Bộ đọc này quét mọi object ở tầng ngoài cùng và
lấy **object cuối cùng có khoá ``status``** — phần văn xuôi phía trước
thường trích dẫn cả schema lẫn ví dụ.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_DECODER = json.JSONDecoder()


@dataclass
class HeadlessStatus:
    status: str = ""  # complete | partial | blocked
    intent: str = ""  # create | update | validate
    reason: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def parsed(self) -> bool:
        """Có đọc được JSON status không."""
        return bool(self.status)

    @property
    def produced_artifact(self) -> bool:
        return self.status in ("complete", "partial")

    @property
    def needs_human(self) -> bool:
        """Có bắt buộc người xem trước khi đi tiếp không.

        ``partial`` nghĩa là BMAD tự nói artifact chưa đứng được một mình.
        Tự duyệt một tài liệu như vậy là bỏ qua đúng chỗ mà cổng người sinh
        ra để bảo vệ.
        """
        return self.status == "partial" or bool(self.open_questions)

    def declared_paths(self) -> list[str]:
        """Mọi đường dẫn BMAD tự khai là đã sinh ra.

        Dùng để đối chiếu với đĩa: khai mà không có file là một dạng thất
        bại im lặng, và chỉ lộ ra nếu ta chịu kiểm.
        """
        return sorted(set(self.artifacts.values()))

    def summary(self) -> str:
        if not self.parsed:
            return "could not parse BMAD JSON status"
        parts = [f"status={self.status}"]
        if self.artifacts:
            parts.append("artifact: " + ", ".join(sorted(self.artifacts)))
        if self.open_questions:
            parts.append(f"{len(self.open_questions)} open questions")
        if self.assumptions:
            parts.append(f"{len(self.assumptions)} assumptions")
        if self.reason:
            parts.append(f"reason: {self.reason}")
        return " · ".join(parts)


#: Khoá mang nghĩa khác, không bao giờ là artifact.
_NON_ARTIFACT_KEYS = frozenset(
    {"status", "intent", "reason", "assumptions", "open_questions",
     "external_handoffs", "conflicts_with_prior_decisions", "offer_to_update",
     "doc_workspace", "altitude", "purpose"}
)

_PATH_LIKE = re.compile(r"[/\\]|\.[A-Za-z0-9]{1,5}$")


def _is_path(value) -> bool:
    """Chuỗi này có hình dạng đường dẫn không.

    Mỗi skill BMAD đặt tên khoá artifact một kiểu (``spine``, ``design``,
    ``experience``, ``companions``…), nên không thể liệt kê hết. Xét hình
    dạng giá trị thì đúng hơn: danh sách khoá cấm sẽ luôn thiếu, còn
    ``"feature"`` hay ``"build-substrate"`` thì không bao giờ giống một
    đường dẫn.
    """
    return isinstance(value, str) and bool(value) and bool(_PATH_LIKE.search(value))


def _as_str_list(value) -> list[str]:
    """Chuẩn hoá về danh sách chuỗi.

    ``open_questions`` có khi là danh sách chuỗi, có khi là danh sách đối
    tượng ``{id, text}`` — chấp nhận cả hai thay vì bắt BMAD viết một kiểu.
    """
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str):
            out.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("text") or item.get("question") or ""
            ident = item.get("id") or ""
            out.append(f"{ident}: {text}".strip(": ").strip())
    return [x for x in out if x]


def _top_level_objects(text: str) -> list[dict]:
    """Mọi object JSON ở tầng ngoài cùng trong một đoạn văn bản.

    Quét từ trái sang, mỗi lần đọc được một object thì nhảy qua hết thân
    nó. Nhờ vậy object lồng bên trong không bị đếm thành ứng viên riêng —
    nếu không, một ``{"id": ..., "status": ...}` nằm trong ``open_questions``
    sẽ bị nhầm là status của cả lượt chạy.
    """
    out: list[dict] = []
    i = 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return out
        try:
            value, end = _DECODER.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(value, dict):
            out.append(value)
        i = end


def parse_headless_status(text: str) -> HeadlessStatus:
    """Trích JSON status từ phần trả lời của BMAD.

    Lấy **object cuối cùng có khoá ``status``**: phần văn xuôi phía trước
    thường trích dẫn schema hoặc ví dụ, còn status thật luôn nằm ở cuối.
    """
    if not text:
        return HeadlessStatus()

    for data in reversed(_top_level_objects(text)):
        if "status" not in data:
            continue

        artifacts: dict[str, str] = {}
        for k, v in data.items():
            if k in _NON_ARTIFACT_KEYS:
                continue
            if _is_path(v):
                artifacts[k] = v
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if _is_path(item):
                        artifacts[f"{k}[{i}]"] = item

        return HeadlessStatus(
            status=str(data.get("status", "")),
            intent=str(data.get("intent", "")),
            reason=str(data.get("reason", "")),
            artifacts=artifacts,
            assumptions=_as_str_list(data.get("assumptions")),
            open_questions=_as_str_list(data.get("open_questions")),
            raw=data,
        )

    return HeadlessStatus()
