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

ENV_WRITE_SCOPE = "AISDLC_WRITE_SCOPE"
ENV_STORY_ID = "AISDLC_STORY_ID"


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


def scope_from_env(env: dict[str, str] | None = None) -> list[str]:
    raw = (env or os.environ).get(ENV_WRITE_SCOPE, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def run_guard(kind: str, event: dict, *, env: dict[str, str] | None = None,
              project_root: str = "") -> Verdict:
    """Chạy một guard trên sự kiện hook của client.

    ``event`` theo hình dạng Claude Code gửi: ``tool_name`` và ``tool_input``.
    """
    tool_input = event.get("tool_input") or {}
    file_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
    content = str(tool_input.get("content") or tool_input.get("new_string") or "")
    command = str(tool_input.get("command") or "")

    if kind == "write-scope":
        return check_write_scope(file_path, scope_from_env(env), project_root=project_root)
    if kind == "secret":
        return check_secrets(content)
    if kind == "injection":
        return check_injection(content)
    if kind == "git-stage":
        return check_git_stage(command)
    if kind == "destructive":
        return check_destructive(command)
    raise ValueError(f"guard không tồn tại: {kind}")


#: Guard nào gắn vào mốc nào, và khớp tool nào.
GUARD_MATCHERS: dict[str, tuple[str, str]] = {
    "write-scope": ("PreToolUse", "Write|Edit|NotebookEdit"),
    "secret": ("PreToolUse", "Write|Edit"),
    "injection": ("PreToolUse", "Write|Edit"),
    "git-stage": ("PreToolUse", "Bash"),
    "destructive": ("PreToolUse", "Bash"),
}


def parse_command(command: str) -> list[str]:
    """Tách lệnh shell an toàn; trả rỗng nếu không phân tích được."""
    try:
        return shlex.split(command)
    except ValueError:
        return []
