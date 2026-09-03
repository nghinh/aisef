"""Cổng phê duyệt của con người (Human-In-The-Loop).

Nguyên tắc thiết kế: **phê duyệt là trạng thái trên đĩa, không phải câu hỏi
tương tác.** Đây là điều kiện để cùng một cơ chế chạy được ở mọi nơi:

* chạy nền / CI — không có người ngồi trước màn hình để trả lời;
* trong phiên chat (Claude Desktop) — agent không thể "đợi" người gõ;
* người duyệt có thể là người khác, lúc khác, trên máy khác.

Luồng: pipeline chạy tới cổng → ghi ``pending`` rồi **dừng** → người chạy
``approve``/``reject`` → chạy lại pipeline thì đi tiếp.

Hai bảo đảm quan trọng:

1. **Phê duyệt gắn với nội dung, không gắn với tên cổng.** Bản ghi lưu SHA-256
   của artifact. Sửa artifact sau khi duyệt thì phê duyệt hết hiệu lực.
2. **Sửa tầng trên làm mất hiệu lực tầng dưới.** Sửa PRD thì Architecture, UX,
   Epics, Stories, Mockups đã duyệt đều thành ``stale`` — vì chúng được duyệt
   dựa trên một bản PRD không còn nữa.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class Gate(str, Enum):
    """Các cổng cần người duyệt, theo đúng thứ tự vòng đời."""

    PRD = "prd"
    ARCHITECTURE = "architecture"
    UX_SPEC = "ux-spec"
    EPICS = "epics"
    STORIES = "stories"
    MOCKUPS = "mockups"
    READINESS = "readiness"        # chốt trước khi bắt đầu viết code
    PRE_DEPLOY = "pre-deploy"      # chốt trước khi triển khai


#: Thứ tự vòng đời. Duyệt lại một cổng làm mọi cổng phía sau thành stale.
GATE_ORDER: tuple[Gate, ...] = (
    Gate.PRD,
    Gate.ARCHITECTURE,
    Gate.UX_SPEC,
    Gate.EPICS,
    Gate.STORIES,
    Gate.MOCKUPS,
    Gate.READINESS,
    Gate.PRE_DEPLOY,
)

#: Artifact chính của mỗi cổng, tương đối so với gốc artifact.
GATE_ARTIFACTS: dict[Gate, str] = {
    Gate.PRD: "prd.md",
    Gate.ARCHITECTURE: "architecture.md",
    Gate.UX_SPEC: "ux-spec.md",
    Gate.EPICS: "epics.md",
    Gate.STORIES: "stories.index.yaml",
    Gate.MOCKUPS: "design-contract.json",
    Gate.READINESS: "sprint-status.yaml",
    Gate.PRE_DEPLOY: "sprint-status.yaml",
}


class Status(str, Enum):
    PENDING = "pending"                    # chờ người xem
    APPROVED = "approved"                  # đã duyệt, nội dung còn nguyên
    CHANGES_REQUESTED = "changes_requested"  # bị trả lại, kèm ghi chú
    STALE = "stale"                        # từng duyệt nhưng nội dung đã đổi


AUTO_APPROVER = "auto"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _current_user() -> str:
    return os.environ.get("AISDLC_APPROVER") or os.environ.get("USER") or "unknown"


def sha256_of(path: Path) -> str:
    """Băm nội dung artifact. Trả chuỗi rỗng nếu file chưa tồn tại."""
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Approval:
    """Một quyết định phê duyệt, kèm dấu vết kiểm toán."""

    gate: str
    artifact: str
    artifact_sha256: str
    status: str
    #: Số thứ tự đơn điệu trong phạm vi store. Dùng để so thứ tự các quyết
    #: định thay cho ``decided_at``: bản ghi có thể được tạo trên máy khác
    #: (đi qua git), nên đồng hồ không đáng tin, còn hai quyết định trong
    #: cùng một giây thì timestamp không phân biệt được.
    seq: int = 0
    decided_by: str = ""
    decided_at: str = ""  # chỉ để đọc, không dùng để so thứ tự
    note: str = ""
    machine_checks: dict[str, str] = field(default_factory=dict)
    history: list[dict[str, str]] = field(default_factory=list)

    @property
    def was_auto(self) -> bool:
        return self.decided_by == AUTO_APPROVER


class ApprovalStore:
    """Đọc/ghi bản ghi phê duyệt dưới ``<artifact_root>/approvals/``."""

    def __init__(self, artifact_root: Path):
        self.root = Path(artifact_root)
        self.dir = self.root / "approvals"

    def _path(self, gate: Gate) -> Path:
        return self.dir / f"{gate.value}.json"

    def artifact_path(self, gate: Gate) -> Path:
        return self.root / GATE_ARTIFACTS[gate]

    def load(self, gate: Gate) -> Approval | None:
        p = self._path(gate)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return Approval(**data)

    def save(self, approval: Approval) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(Gate(approval.gate))
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(approval), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # ghi nguyên tử — không để lại file hỏng khi bị ngắt

    # ------------------------------------------------------------ truy vấn

    def status(self, gate: Gate) -> Status:
        """Trạng thái hiệu lực *hiện tại* của một cổng.

        Tính lại từ nội dung thật trên đĩa, nên một artifact bị sửa sau khi
        duyệt sẽ tự lộ ra là ``stale`` mà không cần ai đánh dấu.
        """
        rec = self.load(gate)
        if rec is None:
            return Status.PENDING
        if rec.status == Status.CHANGES_REQUESTED.value:
            return Status.CHANGES_REQUESTED
        if rec.status != Status.APPROVED.value:
            return Status.PENDING

        if sha256_of(self.artifact_path(gate)) != rec.artifact_sha256:
            return Status.STALE  # nội dung đã đổi kể từ lúc duyệt
        if self._upstream_decided_after(gate, rec.seq):
            return Status.STALE  # tầng trên được quyết lại sau đó
        return Status.APPROVED

    def _upstream_decided_after(self, gate: Gate, seq: int) -> bool:
        """True nếu có cổng phía trước được quyết định sau cổng này."""
        idx = GATE_ORDER.index(gate)
        return any(
            (rec := self.load(up)) is not None and rec.seq > seq
            for up in GATE_ORDER[:idx]
        )

    def _next_seq(self) -> int:
        """Số thứ tự kế tiếp trong phạm vi store."""
        highest = 0
        for g in GATE_ORDER:
            rec = self.load(g)
            if rec:
                highest = max(highest, rec.seq)
        return highest + 1

    def blocking(self, gate: Gate) -> list[Gate]:
        """Các cổng phải xử lý xong trước khi `gate` được phép chạy."""
        idx = GATE_ORDER.index(gate)
        return [g for g in GATE_ORDER[:idx] if self.status(g) is not Status.APPROVED]

    def summary(self) -> list[tuple[Gate, Status, str]]:
        out = []
        for g in GATE_ORDER:
            rec = self.load(g)
            out.append((g, self.status(g), rec.decided_by if rec else ""))
        return out

    # ------------------------------------------------------------ quyết định

    def decide(
        self,
        gate: Gate,
        status: Status,
        *,
        by: str = "",
        note: str = "",
        machine_checks: dict[str, str] | None = None,
    ) -> Approval:
        """Ghi một quyết định, giữ lại toàn bộ lịch sử trước đó."""
        prev = self.load(gate)
        history = list(prev.history) if prev else []
        if prev:
            history.append({
                "status": prev.status,
                "decided_by": prev.decided_by,
                "decided_at": prev.decided_at,
                "note": prev.note,
                "artifact_sha256": prev.artifact_sha256,
            })

        rec = Approval(
            gate=gate.value,
            artifact=GATE_ARTIFACTS[gate],
            artifact_sha256=sha256_of(self.artifact_path(gate)),
            status=status.value,
            seq=self._next_seq(),
            decided_by=by or _current_user(),
            decided_at=_now(),
            note=note,
            machine_checks=machine_checks or (prev.machine_checks if prev else {}),
            history=history,
        )
        self.save(rec)
        return rec

    def approve(self, gate: Gate, *, by: str = "", note: str = "") -> Approval:
        return self.decide(gate, Status.APPROVED, by=by, note=note)

    def reject(self, gate: Gate, *, note: str, by: str = "") -> Approval:
        if not note.strip():
            raise ValueError("từ chối phải kèm ghi chú nói rõ cần sửa gì")
        return self.decide(gate, Status.CHANGES_REQUESTED, by=by, note=note)

    def auto_approve(self, gate: Gate, *, reason: str = "--auto-approve") -> Approval:
        """Duyệt máy. Luôn ghi ``decided_by=auto`` để về sau truy được
        artifact nào chưa từng có người thật xem qua."""
        return self.decide(gate, Status.APPROVED, by=AUTO_APPROVER, note=reason)


def parse_auto_approve(value: str | None) -> frozenset[Gate]:
    """Diễn giải tham số ``--auto-approve``.

    ``None``/rỗng → không cổng nào; ``all`` → tất cả; hoặc danh sách tên cổng
    ngăn cách bởi dấu phẩy (``prd,architecture``).
    """
    if not value:
        return frozenset()
    raw = value.strip().lower()
    if raw == "all":
        return frozenset(GATE_ORDER)

    gates, unknown = set(), []
    for part in (p.strip() for p in raw.split(",")):
        if not part:
            continue
        try:
            gates.add(Gate(part))
        except ValueError:
            unknown.append(part)
    if unknown:
        valid = ", ".join(g.value for g in GATE_ORDER)
        raise ValueError(f"cổng không hợp lệ: {', '.join(unknown)}. Hợp lệ: {valid}")
    return frozenset(gates)
