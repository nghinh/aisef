"""Guard — code tất định chạy tại mốc vòng đời.

Đây là chỗ dành cho những điều agent **không được phép quên**, và cách duy
nhất bảo đảm là không trông vào việc nó nhớ. Mỗi guard là một hàm thuần:
nhận sự kiện, trả phán quyết. Không đọc trạng thái toàn cục, không ghi gì —
nhờ vậy kiểm được bằng test và chạy được ở mọi client.

Quy ước mã thoát theo Claude Code (đã kiểm chứng ở spike S2): **thoát 2 là
chặn**, và stderr được chuyển vào kết quả tool cho agent đọc. Vì thế lý do
chặn phải viết cho agent hiểu và sửa được, không phải viết cho log.

Phạm vi ghi của story truyền qua biến môi trường ``AISDLC_WRITE_SCOPE``.
Guard cố ý **không** tự tra `stories.index.json`: giữ nó thuần và nhanh,
việc tra cứu là của bộ chạy story.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .observe import TOOL_RUN

ENV_WRITE_SCOPE = "AISDLC_WRITE_SCOPE"
ENV_STORY_ID = "AISDLC_STORY_ID"

#: Phạm vi ghi khi **không** ở trong một story: các pha lập kế hoạch và
#: dựng mockup. Chúng có phạm vi cố định và biết trước, nên guard vẫn có
#: nghĩa — thay vì phải tắt đi ở nửa vòng đời.
PLANNING_SCOPE = ("_bmad-output", "docs")


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.allowed else 2


ALLOW = Verdict(True)


# ------------------------------------------------------------ phạm vi ghi


def _norm(p: str) -> PurePosixPath:
    return PurePosixPath(str(p).strip().strip("/"))


def _within(path: str, scope: str) -> bool:
    """`path` có nằm trong `scope` không — so theo đoạn đường dẫn.

    So tiền tố chuỗi sẽ coi `src/apidocs/x.py` là nằm trong `src/api`, mà
    đó là hai vùng khác nhau.
    """
    p, s = _norm(path), _norm(scope)
    return p == s or s in p.parents


def check_write_scope(file_path: str, scope: list[str], *, project_root: str = "") -> Verdict:
    """Chặn ghi ra ngoài phạm vi story.

    Phạm vi rỗng nghĩa là **chưa khai**, và chưa khai thì không cho ghi —
    mặc định mở sẽ biến guard thành thứ trang trí ngay lần đầu ai đó quên
    truyền biến môi trường.
    """
    if not file_path:
        return ALLOW  # không phải thao tác lên file

    if not scope:
        return Verdict(
            False,
            f"story chưa khai write_scope nên không được ghi {file_path}. "
            f"Bổ sung write_scope vào story rồi chạy lại.",
        )

    rel = str(file_path)
    if project_root:
        try:
            rel = str(Path(file_path).resolve().relative_to(Path(project_root).resolve()))
        except ValueError:
            return Verdict(
                False,
                f"{file_path} nằm ngoài thư mục dự án. Story chỉ được ghi trong "
                f"write_scope của nó: {', '.join(scope)}",
            )

    if any(_within(rel, s) for s in scope):
        return ALLOW
    return Verdict(
        False,
        f"{rel} nằm ngoài write_scope của story ({', '.join(scope)}). "
        f"Nếu story thật sự cần chạm chỗ này thì dừng lại và báo — nhiều khả "
        f"năng phạm vi khai thiếu hoặc story bị chẻ sai.",
    )


# ------------------------------------------------------------ bí mật

#: Mẫu bí mật. Nhắm vào những thứ có hình dạng đặc trưng, không đoán mò —
#: một chuỗi ngẫu nhiên dài chưa chắc là khoá, nhưng `sk-ant-...` thì chắc.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("khoá API Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("khoá API OpenAI", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("khoá truy cập AWS", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("khoá riêng tư", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("gán mật khẩu", re.compile(
        r"(?i)\b(password|passwd|pwd|pw|secret|api[_-]?key|access[_-]?token)\s*[=:]\s*"
        r"['\"][^'\"\s{}$]{8,}['\"]"
    )),
]

#: Giá trị giữ chỗ — có hình dạng bí mật nhưng rõ ràng là ví dụ.
PLACEHOLDER_MARKERS = (
    "example", "placeholder", "your-", "xxx", "changeme", "dummy",
    "<", "{{", "${", "os.environ", "process.env", "getenv",
)


def check_secrets(content: str) -> Verdict:
    """Chặn bí mật lọt vào mã nguồn.

    Bỏ qua dòng có dấu hiệu giữ chỗ hoặc đọc từ biến môi trường — chặn
    `API_KEY = os.environ["X"]` sẽ khiến người ta tắt guard đi, và một guard
    bị tắt còn tệ hơn không có.
    """
    if not content:
        return ALLOW

    for line_no, line in enumerate(content.splitlines(), 1):
        lowered = line.lower()
        if any(m in lowered for m in PLACEHOLDER_MARKERS):
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                return Verdict(
                    False,
                    f"dòng {line_no} có vẻ chứa {label}. Đọc từ biến môi trường "
                    f"hoặc kho bí mật, đừng viết thẳng vào mã nguồn.",
                )
    return ALLOW


# ------------------------------------------------------------ lệnh shell

#: Lệnh phá huỷ — chặn thẳng, kể cả khi agent nghĩ nó đang dọn dẹp.
DESTRUCTIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("git reset --hard", re.compile(r"\bgit\s+reset\s+(--\S+\s+)*--hard\b")),
    ("git checkout bỏ thay đổi", re.compile(r"\bgit\s+checkout\s+--\s")),
    ("git clean", re.compile(r"\bgit\s+clean\b.*-[a-z]*f")),
    ("git push --force", re.compile(r"\bgit\s+push\b.*(--force\b|-f\b)")),
    ("xoá đệ quy", re.compile(r"\brm\s+(-\w*\s+)*-\w*[rR]\w*f|\brm\s+-fr\b")),
    ("git stash bỏ việc", re.compile(r"\bgit\s+stash\s+(drop|clear)\b")),
]

_GIT_ADD_ALL = re.compile(r"\bgit\s+add\s+(.*\s)?(-A\b|--all\b|\.(\s|$))")


def check_git_stage(command: str) -> Verdict:
    """Chặn `git add -A` và `git add .`.

    Lệnh gộp nuốt cả file rác lẫn thay đổi của story khác đang chạy song
    song trong worktree bên cạnh.
    """
    if not command or not _GIT_ADD_ALL.search(command):
        return ALLOW
    return Verdict(
        False,
        "không dùng `git add -A` hay `git add .`. Chỉ stage đúng đường dẫn "
        "story này chạm, ví dụ: git add src/api/users.py tests/test_users.py",
    )


def check_destructive(command: str) -> Verdict:
    """Chặn lệnh phá huỷ công việc chưa lưu."""
    if not command:
        return ALLOW
    for label, pattern in DESTRUCTIVE_PATTERNS:
        if pattern.search(command):
            return Verdict(
                False,
                f"lệnh phá huỷ bị chặn ({label}). Nếu thật sự cần, dừng lại "
                f"và báo người — đừng tự chạy.",
            )
    return ALLOW


# ------------------------------------------------------------ tiêm mã

INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("nối chuỗi vào câu SQL", re.compile(
        r"""(?i)(execute|query|cursor\.execute|db\.raw)\s*\(\s*f?['"].*\b"""
        r"""(select|insert|update|delete)\b.*(\{|\+|%s\s*%|\$\{)"""
    )),
    ("chèn HTML thô", re.compile(r"dangerouslySetInnerHTML|\.innerHTML\s*=")),
    ("shell với chuỗi ghép", re.compile(
        r"(?i)(os\.system|subprocess\.\w+)\s*\(\s*f?['\"].*(\{|\+)"
    )),
]


def check_injection(content: str) -> Verdict:
    if not content:
        return ALLOW
    for label, pattern in INJECTION_PATTERNS:
        m = pattern.search(content)
        if m:
            line_no = content[: m.start()].count("\n") + 1
            return Verdict(
                False,
                f"dòng {line_no}: {label}. Dùng tham số hoá / API an toàn thay "
                f"vì ghép chuỗi.",
            )
    return ALLOW


# ------------------------------------------------------------ điều phối


# ------------------------------------------------------------ phạm vi diff


def check_diff_scope(changed: list[str], scope: list[str]) -> Verdict:
    """Chặn khi file **ngoài phạm vi** đã bị đổi.

    `write-scope` chặn từng thao tác ghi mà harness nhìn thấy. Guard này
    hỏi câu khác: sau tất cả những gì đã xảy ra, cây làm việc có đúng
    phạm vi không. Nó bắt được cả đường đi vòng — script tự sinh file, lệnh
    di chuyển file, hoặc client không gắn được hook tiền kiểm (OpenCode ở
    mức hậu kiểm) — vì nó đọc kết quả chứ không đọc ý định.
    """
    if not changed:
        return ALLOW
    if not scope:
        return Verdict(
            False,
            f"story chưa khai write_scope nhưng đã đổi {len(changed)} file: "
            f"{', '.join(changed[:5])}",
        )

    outside = [c for c in changed if not any(_within(c, s) for s in scope)]
    if not outside:
        return ALLOW
    return Verdict(
        False,
        f"{len(outside)} file bị đổi ngoài write_scope ({', '.join(scope)}): "
        f"{', '.join(outside[:5])}. Hoàn nguyên chúng, hoặc dừng lại và báo "
        f"rằng phạm vi story khai thiếu.",
    )


#: Đường dẫn do **harness** ghi trong lúc chạy, không phải agent: bằng
#: chứng, trạng thái đợt, bản ghi phê duyệt, worktree. Không loại chúng ra
#: thì chính việc harness ghi trạng thái lại bị tính là story ghi ra ngoài
#: phạm vi — guard tự tố cáo mình và mọi story đều trượt.
#:
#: Cố ý **không** loại cả `_bmad-output`: tài liệu kế hoạch (PRD, kiến
#: trúc, epic, hợp đồng thị giác, chỉ mục story) là thứ agent sửa trộm thì
#: phải lộ ra — sửa `stories.index.json` là sửa chính phạm vi ràng buộc nó.
#: Phụ thuộc cài đặt và tạo tác build. Chúng xuất hiện vì story **chạy**,
#: không phải vì story **viết** — tính vào phạm vi thì mọi story cài phụ
#: thuộc đều trượt, và cách duy nhất chạy tiếp là nới phạm vi đến mức guard
#: không còn nghĩa gì. Dự án có `.gitignore` đúng thì git đã loại sẵn;
#: danh sách này là lưới an toàn cho lúc `.gitignore` chưa kịp có.
VENDOR_PATHS = (
    "node_modules", ".venv", "venv", "vendor", "target", "dist", "build",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".next", ".turbo",
    "coverage", ".gradle", "Pods",
    # Tạo tác của chính công cụ agent dùng để làm việc: ảnh chụp, trace,
    # báo cáo. Chúng ở gốc dự án nhưng không phải sản phẩm của story —
    # tính vào phạm vi thì mở trình duyệt một lần là trượt cổng.
    ".playwright-mcp", "playwright-report", "test-results", ".nyc_output",
)

HARNESS_OWNED = (
    "_bmad-output/evidence",
    "_bmad-output/approvals",
    "_bmad-output/sprint-status.json",
    "_bmad-output/sprint-status.json.lock",
    "_bmad-output/compile-report.json",
    ".aisdlc",
    *VENDOR_PATHS,
)


def changed_files(project_root: str, *, ignore: tuple[str, ...] = HARNESS_OWNED) -> list[str]:
    """File đã đổi so với HEAD, kể cả file mới chưa theo dõi.

    Bỏ qua phần harness tự ghi. Phần còn lại của ``_bmad-output`` **không**
    được bỏ qua: agent sửa PRD hay hợp đồng thị giác giữa lúc viết code là
    chuyện phải lộ ra.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
            cwd=project_root or ".",
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []

    out: list[str] = []
    for entry in proc.stdout.split("\0"):
        if len(entry) <= 3:
            continue
        path = entry[3:]
        if any(_within(path, skip) or skip in Path(path).parts for skip in ignore):
            continue
        out.append(path)
    return out


# ------------------------------------------------------------ hoàn thành


def check_completion(evidence) -> Verdict:
    """Chặn agent kết thúc khi test chưa xanh cho **đoạn code hiện tại**.

    Ba câu hỏi, theo thứ tự nghiêm dần:

    1. Có lần chạy test nào chưa? Chưa chạy mà tuyên bố xong là tự khai.
    2. Lần gần nhất có xanh không?
    3. Có file nào sửa **sau** lần chạy đó không? Test xanh trước khi sửa
       không nói gì về đoạn vừa viết — đây là kiểu "xanh" hay gặp nhất khi
       agent vội kết thúc.
    """
    last = evidence.last(TOOL_RUN, "test")
    if last is None:
        # Nói đúng lệnh gõ được. Guard chặn bằng một chỉ dẫn không chạy được
        # thì agent kẹt: nó không dừng được, cũng không làm được điều được
        # bảo — và cứ thế đốt hết số lượt.
        from .tools import aisdlc_command

        return Verdict(
            False,
            f"chưa có lần chạy test nào cho story này. Chạy `{aisdlc_command()} "
            f"tool test` rồi mới kết thúc — bằng chứng nằm ở kết quả chạy, "
            f"không ở lời kể.",
        )
    if not last.ok:
        tail = str(last.detail.get("tail") or "")[:400]
        return Verdict(
            False,
            "lần chạy test gần nhất còn đỏ, chưa được kết thúc story.\n" + tail,
        )

    stale = evidence.stale_since_last_test()
    if stale:
        from .tools import aisdlc_command

        return Verdict(
            False,
            f"{len(stale)} file đã sửa sau lần chạy test gần nhất "
            f"({', '.join(stale[:5])}). Chạy lại `{aisdlc_command()} tool test` "
            f"rồi mới kết thúc.",
        )
    return ALLOW


def scope_from_env(env: dict[str, str] | None = None) -> list[str]:
    raw = (env or os.environ).get(ENV_WRITE_SCOPE, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def story_from_env(env: dict[str, str] | None = None) -> str:
    return (env or os.environ).get(ENV_STORY_ID, "")


def effective_scope(env: dict[str, str] | None = None) -> list[str]:
    """Phạm vi ghi đang có hiệu lực.

    Trong một story: đúng phạm vi story khai, và **rỗng thì chặn** — quên
    truyền biến môi trường không được biến guard thành đồ trang trí.

    Ngoài story (pha lập kế hoạch, dựng mockup): phạm vi cố định của
    framework. Không có nhánh này thì guard chặn cả BMAD ghi PRD, và cách
    duy nhất để chạy tiếp là tắt guard ở nửa đầu vòng đời — nửa mà tài
    liệu quyết định mọi thứ phía sau.
    """
    scope = scope_from_env(env)
    if scope or story_from_env(env):
        return scope
    return list(PLANNING_SCOPE)


def run_guard(kind: str, event: dict, *, env: dict[str, str] | None = None,
              project_root: str = "", artifact_root: str = "") -> Verdict:
    """Chạy một guard trên sự kiện hook của client.

    ``event`` theo hình dạng Claude Code gửi: ``tool_name`` và ``tool_input``.
    Hai guard cuối cần trạng thái ngoài (git, bằng chứng); phần **quyết
    định** của chúng vẫn là hàm thuần, chỗ này chỉ đi lấy dữ liệu.
    """
    tool_input = event.get("tool_input") or {}
    file_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
    content = str(tool_input.get("content") or tool_input.get("new_string") or "")
    command = str(tool_input.get("command") or "")

    if kind == "write-scope":
        return check_write_scope(
            file_path, effective_scope(env), project_root=project_root
        )
    if kind == "secret":
        return check_secrets(content)
    if kind == "injection":
        return check_injection(content)
    if kind == "git-stage":
        return check_git_stage(command)
    if kind == "destructive":
        return check_destructive(command)
    if kind == "diff-scope":
        return check_diff_scope(changed_files(project_root), scope_from_env(env))
    if kind == "completion":
        story = story_from_env(env)
        if not story or not artifact_root:
            # Không biết đang làm story nào thì không kết luận được. Chặn ở
            # đây sẽ chặn cả những lượt chạy ngoài vòng đời story.
            return ALLOW
        from .observe import EvidenceStore

        return check_completion(EvidenceStore(artifact_root).read(story))
    raise ValueError(f"guard không tồn tại: {kind}")


#: Guard nào gắn vào mốc nào, và khớp tool nào.
GUARD_MATCHERS: dict[str, tuple[str, str]] = {
    "write-scope": ("PreToolUse", "Write|Edit|NotebookEdit"),
    "secret": ("PreToolUse", "Write|Edit"),
    "injection": ("PreToolUse", "Write|Edit"),
    "git-stage": ("PreToolUse", "Bash"),
    "destructive": ("PreToolUse", "Bash"),
    "diff-scope": ("PostToolUse", "Write|Edit|NotebookEdit|Bash"),
    "completion": ("Stop", ""),
}


def parse_command(command: str) -> list[str]:
    """Tách lệnh shell an toàn; trả rỗng nếu không phân tích được."""
    try:
        return shlex.split(command)
    except ValueError:
        return []
