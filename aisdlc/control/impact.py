"""Thay đổi này chạm tới đâu — ngữ cảnh cho người rà soát.

Người rà soát nhận diff rồi vẫn phải tự trả lời: đoạn sửa này ai gọi,
test nào phủ, luồng nào đi qua. Đo trên e9, nó tốn 22–68 lượt cho việc
ấy, mỗi lượt thử lại làm lại từ đầu — STORY-01-04 chạy bốn lượt và ba
lượt trong đó cùng đi dò lại một đường đọc.

Đây là **ngữ cảnh**, không phải phán quyết. Đồ thị gọi hàm dựng bằng
phân tích tĩnh luôn thiếu: gọi động, phản chiếu, tiêm phụ thuộc đều
không hiện lên. Coi nó là chân lý thì người rà soát bỏ qua chỗ nó không
thấy — mà đó thường đúng là chỗ hỏng. Nên mọi kết quả ở đây đi kèm
nguồn và mức tin cậy, và prompt nói rõ nó chỉ là gợi ý khởi đầu.

Kiến trúc **không** buộc vào một công cụ nào. `review.impact_provider`
nhận một lệnh; lệnh ấy trả JSON theo hợp đồng dưới đây. Không cấu hình
thì dùng bản dựng sẵn — thô hơn nhiều, nhưng chạy được ngay và nói
thẳng là nó thô.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

#: Số mục tối đa mỗi loại đưa vào prompt. Đủ để định hướng, không đủ để
#: lấn át diff — người rà soát phải đọc code, không phải đọc danh sách.
MAX_PER_KIND = 12

#: Đuôi tệp coi là mã nguồn khi dò tham chiếu.
SOURCE_EXT = (
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".cs", ".swift",
)

_TEST_HINT = re.compile(r"(^|[./_-])(test|tests|spec|__tests__|e2e)([./_-]|$)", re.I)


def is_test_path(path: str) -> bool:
    return bool(_TEST_HINT.search(path))


@dataclass
class ImpactReport:
    """Ảnh hưởng của một thay đổi. Rỗng là hợp lệ, và phải nói ra."""

    #: Tên hàm/lớp/hằng xuất khẩu bị đổi trong diff.
    changed_symbols: list[str] = field(default_factory=list)
    #: Tệp có tham chiếu tới các tên đó nhưng **không** nằm trong diff.
    callers: list[str] = field(default_factory=list)
    #: Tệp test có tham chiếu tới các tên đó.
    related_tests: list[str] = field(default_factory=list)
    #: Tên bị đổi mà không tệp test nào nhắc tới. Đây là mục đáng giá
    #: nhất: khuôn thất bại lặp lại nhiều nhất trên e9 là "code có mặt
    #: nhưng không test nào chứng minh nó chạy" — `registerSW`,
    #: `roving tabindex`, `watchNotes`, điều hướng bằng phím mũi tên.
    untested_symbols: list[str] = field(default_factory=list)
    #: Luồng/đường thực thi bị chạm, nếu nhà cung cấp biết.
    flows: list[str] = field(default_factory=list)
    #: Ai tính ra kết quả này.
    source: str = ""
    #: True khi kết quả thô hơn mức mong muốn (bản dựng sẵn, hoặc lệnh
    #: ngoài hỏng). Phải nói ra: người đọc cần biết mức tin cậy.
    degraded: bool = False
    note: str = ""

    @property
    def empty(self) -> bool:
        return not (
            self.changed_symbols or self.callers
            or self.related_tests or self.untested_symbols or self.flows
        )

    def as_prompt(self) -> str:
        """Phần đưa vào prompt rà soát. Nói rõ nguồn và giới hạn."""
        if self.empty:
            return (
                "_Chưa có phân tích ảnh hưởng_ — không cấu hình "
                "`review.impact_provider`, hoặc không suy ra được gì. "
                "Tự dò từ diff."
            )
        lines = [
            f"_Nguồn: {self.source or 'không rõ'}"
            + (" · **thô**, chỉ là gợi ý khởi đầu" if self.degraded else "")
            + "._",
            "",
            "Đây là **gợi ý**, không phải chân lý: phân tích tĩnh không thấy "
            "gọi động, phản chiếu hay tiêm phụ thuộc. Đừng dừng ở đây, và "
            "đừng bỏ qua chỗ nó không nhắc tới.",
            "",
        ]
        for nhan, muc in (
            ("Tên bị đổi", self.changed_symbols),
            ("Nơi dùng chúng (ngoài diff)", self.callers),
            ("Test có liên quan", self.related_tests),
            ("Tên không test nào nhắc tới", self.untested_symbols),
            ("Luồng bị chạm", self.flows),
        ):
            if not muc:
                continue
            lines.append(f"**{nhan}:**")
            lines += [f"- `{m}`" for m in muc[:MAX_PER_KIND]]
            if len(muc) > MAX_PER_KIND:
                lines.append(f"- … còn {len(muc) - MAX_PER_KIND}")
            lines.append("")
        if self.note:
            lines.append(f"_{self.note}_")
        return "\n".join(lines).strip()

    @classmethod
    def from_json(cls, raw: dict, *, source: str) -> "ImpactReport":
        """Đọc kết quả của một nhà cung cấp ngoài.

        Khoá lạ bị bỏ qua, khoá thiếu thành rỗng: một công cụ ngoài đổi
        định dạng không đáng làm hỏng cả lượt rà soát.
        """
        def lay(*ten: str) -> list[str]:
            for t in ten:
                v = raw.get(t)
                if isinstance(v, list):
                    return [str(x) for x in v if str(x).strip()]
            return []

        return cls(
            changed_symbols=lay("changed_symbols", "symbols", "changed"),
            callers=lay("callers", "affected", "dependents", "affected_files"),
            related_tests=lay("related_tests", "tests", "affected_tests"),
            untested_symbols=lay("untested_symbols", "missing_tests", "test_gaps"),
            flows=lay("flows", "affected_flows", "processes"),
            source=source,
            note=str(raw.get("note") or ""),
        )


# ------------------------------------------------------------ nhà cung cấp


def analyse(
    project: Path | str,
    changed: list[str],
    *,
    command: str = "",
    timeout: int = 120,
) -> ImpactReport:
    """Phân tích ảnh hưởng của một tập tệp đã đổi.

    Có lệnh ngoài thì dùng nó; lệnh hỏng thì **lùi về** bản dựng sẵn và
    nói rõ, thay vì trả rỗng. Rỗng im lặng là tệ nhất: người rà soát
    không phân biệt được "không có ảnh hưởng" với "không ai tính".
    """
    project = Path(project)
    changed = [c for c in changed if c]
    if not changed:
        return ImpactReport(source="không có thay đổi")

    if command.strip():
        got = _run_command(project, changed, command, timeout)
        if got is not None:
            return got
        fallback = builtin(project, changed)
        fallback.degraded = True
        fallback.note = (
            f"`review.impact_provider` chạy hỏng, đã lùi về bản dựng sẵn: "
            f"{command.split()[0]}"
        )
        return fallback

    return builtin(project, changed)


def _run_command(
    project: Path, changed: list[str], command: str, timeout: int
) -> ImpactReport | None:
    """Chạy nhà cung cấp ngoài. ``None`` nếu không dùng được kết quả.

    Hợp đồng cố tình đơn giản để công cụ nào cũng nối được: nhận danh
    sách tệp qua stdin (mỗi dòng một tệp), trả JSON ra stdout.
    """
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=project,
            input="\n".join(changed),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    return ImpactReport.from_json(raw, source=command.split()[0])


#: Tên xuất khẩu, theo họ ngôn ngữ. Cố ý chỉ bắt **khai báo xuất khẩu**:
#: biến cục bộ không đáng dò tham chiếu toàn kho.
_EXPORTS = (
    re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?"
               r"(?:function|class|const|let|var|interface|type|enum)\s+(\w+)", re.M),
    re.compile(r"^\s*(?:public\s+|def\s+|class\s+|func\s+|fn\s+)(\w+)", re.M),
)


def builtin(project: Path | str, changed: list[str]) -> ImpactReport:
    """Bản dựng sẵn: tìm tên xuất khẩu rồi dò tham chiếu bằng văn bản.

    Thô so với đồ thị gọi hàm thật — trùng tên là dính, gọi động không
    thấy — nhưng chạy được ngay, không cài gì, và trả lời đúng câu hỏi
    đắt nhất: **tên nào vừa đổi mà không test nào nhắc tới**. Khuôn thất
    bại lặp lại nhiều nhất trên e9 chính là loại đó.
    """
    project = Path(project)
    rep = ImpactReport(source="dựng sẵn (dò theo tên)", degraded=True)
    doi = {c for c in changed}

    names: set[str] = set()
    for rel in changed:
        f = project / rel
        if not f.is_file() or f.suffix not in SOURCE_EXT:
            continue
        try:
            body = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in _EXPORTS:
            names |= {m for m in pat.findall(body) if len(m) >= 4}
    if not names:
        rep.note = "không thấy tên xuất khẩu nào trong tệp đã đổi"
        return rep
    rep.changed_symbols = sorted(names)

    callers: set[str] = set()
    tests: set[str] = set()
    nhac: set[str] = set()      # tên được test nhắc tới
    for f in _source_files(project):
        rel = str(f.relative_to(project))
        if rel in doi:
            continue
        try:
            body = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hit = {n for n in names if re.search(rf"\b{re.escape(n)}\b", body)}
        if not hit:
            continue
        if is_test_path(rel):
            tests.add(rel)
            nhac |= hit
        else:
            callers.add(rel)

    # Test **trong** diff cũng tính: story hay viết test cạnh code.
    for rel in changed:
        if not is_test_path(rel):
            continue
        f = project / rel
        if not f.is_file():
            continue
        try:
            body = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hit = {n for n in names if re.search(rf"\b{re.escape(n)}\b", body)}
        if hit:
            tests.add(rel)
            nhac |= hit

    rep.callers = sorted(callers)
    rep.related_tests = sorted(tests)
    rep.untested_symbols = sorted(names - nhac)
    return rep


def _source_files(project: Path):
    bo_qua = {
        "node_modules", ".git", "dist", "build", "__pycache__", ".venv",
        "venv", "target", ".next", "coverage", "_bmad-output", ".aisdlc",
    }
    for f in project.rglob("*"):
        if not f.is_file() or f.suffix not in SOURCE_EXT:
            continue
        if bo_qua & set(f.parts):
            continue
        yield f


__all__ = [
    "MAX_PER_KIND",
    "ImpactReport",
    "analyse",
    "builtin",
    "is_test_path",
]
