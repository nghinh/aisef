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
import math
import re
import subprocess
from collections import Counter, defaultdict
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
#: biến cục bộ không đáng dò tham chiếu toàn kho. Nhóm 1 = loại, nhóm 2 = tên.
_EXPORTS = (
    # `[ \t]*` chứ không `\s*`: `\s` nuốt cả dòng trống phía trước và số
    # dòng của định nghĩa lệch đi chừng ấy dòng.
    re.compile(r"^[ \t]*export\s+(?:default\s+)?(?:async\s+)?"
               r"(function|class|const|let|var|interface|type|enum)\s+(\w+)", re.M),
    re.compile(r"^[ \t]*(?:public\s+|async\s+)?(def|class|func|fn)\s+(\w+)", re.M),
)

#: Tên ngắn hơn chừng này không đáng dò: `id`, `run`, `get` dính khắp kho.
MIN_NAME_LEN = 4
#: Tên định nghĩa ở nhiều hơn chừng này tệp là tên phổ biến (`save`,
#: `render`) — Aider giảm trọng ×0,1; trước đây `builtin` để chúng lấp đầy
#: `callers` rồi cắt lặng ở MAX_PER_KIND (ADR-005 §9, phát hiện 5).
COMMON_DEFS = 5


def _read(path: Path) -> str | None:
    if not path.is_file() or path.suffix not in SOURCE_EXT:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def symbols(project: Path | str, files=None) -> dict[str, list[tuple[str, int, str]]]:
    """{tệp: [(tên, dòng, loại)]} — tên xuất khẩu của từng tệp.

    Bỏ tên `_private` (Aider: không đáng dò ngoài tệp) và tên ngắn hơn
    `MIN_NAME_LEN`. ``files`` là đường dẫn tương đối; ``None`` = cả kho.
    """
    project = Path(project)
    out: dict[str, list[tuple[str, int, str]]] = {}
    for rel in (files if files is not None else _rel_files(project)):
        body = _read(project / rel)
        if body is None:
            continue
        found = []
        for pat in _EXPORTS:
            for m in pat.finditer(body):
                kind, name = m.group(1), m.group(2)
                if len(name) < MIN_NAME_LEN or name.startswith("_"):
                    continue
                found.append((name, body.count("\n", 0, m.start()) + 1, kind))
        if found:
            out[rel] = sorted(set(found), key=lambda t: t[1])
    return out


def refs(project: Path | str, names, files=None) -> dict[str, dict[str, int]]:
    """{tên: {tệp: số lần nhắc}} — **một** lượt quét kho cho mọi tên.

    Nhận nhiều tên một lần thay vì một tên mỗi lần gọi: 50 tên × 500 tệp
    quét lại từng tên là 25 000 lần đọc, gộp lại còn 500.
    """
    project = Path(project)
    names = sorted({n for n in names if n}, key=len, reverse=True)
    out: dict[str, dict[str, int]] = {n: {} for n in names}
    if not names:
        return out
    pat = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b")
    for rel in (files if files is not None else _rel_files(project)):
        body = _read(project / rel)
        if body is None:
            continue
        for name, k in Counter(pat.findall(body)).items():
            out[name][rel] = k
    return out


def weights(project: Path | str, names, files=None) -> dict[str, float]:
    """Trọng số mỗi tên theo ba luật của Aider: `_private` → 0, định nghĩa ở
    > `COMMON_DEFS` tệp → ×0,1, còn lại 1. Luật thứ ba (√số lần nhắc) áp ở
    chỗ cộng điểm, không ở đây."""
    defs: Counter = Counter()
    for syms in symbols(project, files).values():
        defs.update({n for n, _, _ in syms})
    return {
        n: 0.0 if n.startswith("_") else (0.1 if defs[n] > COMMON_DEFS else 1.0)
        for n in names
    }


def builtin(project: Path | str, changed: list[str]) -> ImpactReport:
    """Bản dựng sẵn: tìm tên xuất khẩu rồi dò tham chiếu bằng văn bản.

    Thô so với đồ thị gọi hàm thật — trùng tên là dính, gọi động không
    thấy — nhưng chạy được ngay, không cài gì, và trả lời đúng câu hỏi
    đắt nhất: **tên nào vừa đổi mà không test nào nhắc tới**. Khuôn thất
    bại lặp lại nhiều nhất trên e9 chính là loại đó.

    Điểm một tệp = Σ trọng số(tên) × √(số lần nhắc); tệp dưới 1 điểm (chỉ
    dính tên phổ biến) bị bỏ, phần còn lại xếp theo điểm rồi mới cắt ở
    `MAX_PER_KIND` — tên `save`/`render` không còn đẩy tệp gọi thật ra
    khỏi danh sách.
    """
    project = Path(project)
    rep = ImpactReport(source="dựng sẵn (dò theo tên)", degraded=True)
    doi = set(changed)

    names = sorted({n for syms in symbols(project, changed).values() for n, _, _ in syms})
    if not names:
        rep.note = "không thấy tên xuất khẩu nào trong tệp đã đổi"
        return rep
    rep.changed_symbols = names

    files = list(_rel_files(project))
    w = weights(project, names, files)
    score: dict[str, float] = defaultdict(float)
    nhac: set[str] = set()      # tên được test nhắc tới
    for name, per_file in refs(project, names, files).items():
        for rel, n in per_file.items():
            # Chính tệp vừa sửa không phải "nơi dùng" của chính nó; test
            # **trong** diff thì tính — story hay viết test cạnh code.
            if rel in doi and not is_test_path(rel):
                continue
            score[rel] += w[name] * math.sqrt(n)
            if is_test_path(rel):
                nhac.add(name)

    kept = sorted((rel for rel, s in score.items() if s >= 1.0), key=lambda r: (-score[r], r))
    rep.callers = [r for r in kept if not is_test_path(r)]
    rep.related_tests = [r for r in kept if is_test_path(r)]
    rep.untested_symbols = sorted(set(names) - nhac)
    return rep


def _rel_files(project: Path):
    """Đường dẫn tương đối (posix) của mọi tệp mã nguồn trong kho."""
    for f in _source_files(project):
        yield f.relative_to(project).as_posix()


def _source_files(project: Path):
    bo_qua = {
        "node_modules", ".git", "dist", "build", "__pycache__", ".venv",
        "venv", "target", ".next", "coverage", "_bmad-output", ".aisef", ".claude",
    }
    for f in sorted(project.rglob("*")):
        if not f.is_file() or f.suffix not in SOURCE_EXT:
            continue
        if bo_qua & set(f.parts):
            continue
        yield f


__all__ = [
    "COMMON_DEFS",
    "MAX_PER_KIND",
    "ImpactReport",
    "analyse",
    "builtin",
    "is_test_path",
    "refs",
    "symbols",
    "weights",
]
