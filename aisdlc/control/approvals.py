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

#: Chỉ mục story đã chuẩn hoá — do bộ tách story sinh ra (GĐ-4.3).
STORIES_INDEX = "stories.index.json"

#: Kết quả chấm cổng trước triển khai — thứ người đọc trước khi ký.
PRE_DEPLOY_REPORT = "pre-deploy-report.json"


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
    #: Cổng của vòng cải tiến epic (ADR-004 R3): duyệt **tiếp tục** vòng ≥ 2
    #: sau khi đọc báo cáo vòng vừa xong. Cố ý **không** nằm trong
    #: `GATE_ORDER`: nó không phải một tầng của vòng đời — dự án chưa từng
    #: chạy `improve` không được vì nó mà kẹt ở `pre-deploy`, và nó lặp lại
    #: mỗi vòng chứ không duyệt một lần.
    IMPROVE = "improve"


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

#: Artifact của mỗi cổng, tương đối so với gốc artifact.
#:
#: Tên phải khớp **file có thật trên đĩa**, vì phê duyệt gắn với băm nội
#: dung: trỏ nhầm tên thì băm luôn rỗng và cổng không bao giờ phát hiện
#: được thay đổi — một cổng vô hại nhìn từ ngoài, nhưng không bảo vệ gì.
#:
#: Cổng UX có hai file vì BMAD sinh hai tài liệu tách vai (`DESIGN.md` là
#: hệ thống thị giác, `EXPERIENCE.md` là luồng và màn hình). Duyệt một file
#: rồi sửa file kia sẽ lọt.
GATE_ARTIFACTS: dict[Gate, tuple[str, ...]] = {
    Gate.PRD: ("prd.md",),
    Gate.ARCHITECTURE: ("architecture.md",),
    Gate.UX_SPEC: ("DESIGN.md", "EXPERIENCE.md"),
    Gate.EPICS: ("epics.md",),
    Gate.STORIES: (STORIES_INDEX,),
    Gate.MOCKUPS: ("design-contract.json",),
    # Hai cổng cuối **không** gắn vào `sprint-status.json`: file đó đổi
    # sau mỗi story, nên phê duyệt vừa ký đã thành `stale` — cổng trở thành
    # thứ báo động liên tục rồi bị bỏ qua.
    Gate.READINESS: (STORIES_INDEX, "design-contract.json"),
    Gate.PRE_DEPLOY: (PRE_DEPLOY_REPORT,),
    # Mẫu glob: mỗi vòng một báo cáo, số vòng không biết trước. Băm gộp
    # **mọi** báo cáo, nên vòng mới làm phê duyệt cũ thành `stale` — người
    # phải đọc báo cáo mới rồi mới duyệt vòng kế.
    Gate.IMPROVE: ("LOOP-REPORT-*.md",),
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


#: Tiền tố story/epic do vòng cải tiến (ADR-004 R3) sinh bằng code.
REPAIR_PREFIX = ("STORY-RP-", "EPIC-RP-")


def _artifact_hash(path: Path) -> str:
    """Băm một artifact của cổng; riêng `stories.index.json` băm **nội dung
    đã chuẩn hoá và bỏ story sửa**, không băm byte.

    Story sửa do `aisdlc improve` sinh ra và được cổng người `improve` quản.
    Băm cả chúng thì mỗi vòng cải tiến làm cổng `stories`/`readiness` đã
    duyệt thành stale, và lần gọi `improve` kế bị chính vòng trước chặn (đo
    e9 2026-09-06 05:44). Chuẩn hoá (khoá sắp xếp, không phụ thuộc khoảng
    trắng) để một lần ghi lại cùng nội dung không làm stale. Đổi cách băm
    làm phê duyệt `stories`/`readiness` đã ký trước bản này stale **một lần**
    — nói ra ở đây thay vì để người dùng đoán. Không đọc được JSON thì băm byte.
    """
    if path.name != STORIES_INDEX or not path.is_file():
        return sha256_of(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return sha256_of(path)
    if not isinstance(data, dict):
        return sha256_of(path)
    loc = dict(data)
    for key in ("stories", "epics"):
        if isinstance(loc.get(key), list):
            loc[key] = [x for x in loc[key]
                        if not (isinstance(x, dict) and str(x.get("id", "")).startswith(REPAIR_PREFIX))]
    return hashlib.sha256(json.dumps(loc, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


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

    def artifact_paths(self, gate: Gate) -> list[Path]:
        out: list[Path] = []
        for name in GATE_ARTIFACTS[gate]:
            # Mẫu glob không khớp gì thì vẫn trả chính mẫu, để "thiếu" gọi
            # được tên tệp thay vì im lặng.
            matched = sorted(self.root.glob(name)) if any(c in name for c in "*?[") else []
            out += matched or [self.root / name]
        return out

    def artifact_path(self, gate: Gate) -> Path:
        """File chính của cổng — dùng để hiển thị."""
        return self.artifact_paths(gate)[0]

    def has_artifacts(self, gate: Gate) -> bool:
        """**Mọi** file của cổng đều đã có chưa."""
        return all(p.is_file() for p in self.artifact_paths(gate))

    def content_hash(self, gate: Gate) -> str:
        """Băm gộp toàn bộ file của cổng, theo thứ tự khai báo."""
        parts = [f"{p.relative_to(self.root)}:{_artifact_hash(p)}" for p in self.artifact_paths(gate)]
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()

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

        if self.content_hash(gate) != rec.artifact_sha256:
            return Status.STALE  # nội dung đã đổi kể từ lúc duyệt
        if self._upstream_decided_after(gate, rec.seq):
            return Status.STALE  # tầng trên được quyết lại sau đó
        return Status.APPROVED

    def _upstream_decided_after(self, gate: Gate, seq: int) -> bool:
        """True nếu có cổng phía trước được quyết định sau cổng này."""
        if gate not in GATE_ORDER:
            return False  # cổng ngoài vòng đời (`improve`) không có tầng trên
        idx = GATE_ORDER.index(gate)
        return any(
            (rec := self.load(up)) is not None and rec.seq > seq
            for up in GATE_ORDER[:idx]
        )

    def _next_seq(self) -> int:
        """Số thứ tự kế tiếp trong phạm vi store."""
        highest = 0
        for g in Gate:
            rec = self.load(g)
            if rec:
                highest = max(highest, rec.seq)
        return highest + 1

    def blocking(self, gate: Gate) -> list[Gate]:
        """Các cổng phải xử lý xong trước khi `gate` được phép chạy."""
        if gate not in GATE_ORDER:
            return []
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
            artifact=", ".join(GATE_ARTIFACTS[gate]),
            artifact_sha256=self.content_hash(gate),
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
