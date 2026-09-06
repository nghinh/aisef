"""Chạy agent bằng Claude Code CLI.

Mọi cờ dùng ở đây đã kiểm chứng bằng thực nghiệm (spike S1, S2 —
`docs/SPIKE-REPORT.md`), không suy từ tài liệu:

* ``--output-format stream-json --verbose`` cho luồng sự kiện đọc được,
  kết thúc bằng sự kiện ``result`` mang cost, latency, usage và
  ``permission_denials``;
* ``--settings`` gắn hook, và hook trả mã 2 **chặn thật** tool — kể cả khi
  chạy với ``--permission-mode acceptEdits``;
* ``< /dev/null`` là bắt buộc, nếu không CLI chờ stdin ba giây mỗi lần gọi.

**Cách ly khỏi cấu hình toàn cục của người dùng** (đo 2026-09-05, Claude Code
2.1.236, hợp quy C3/C4 trượt sau khi máy chủ bật ``permissions.defaultMode:
"auto"`` trong ``~/.claude/settings.json``): phiên con thừa hưởng chế độ ấy
thì **mất Glob/Grep** và được dặn "ưu tiên Bash" — tức ghi tệp bằng heredoc
và né sạch guard ``Write|Edit``; MCP của người dùng (Google Drive…) và hook
toàn cục cũng lọt vào phiên. Harness không tin client thì càng không tin
cấu hình máy: chế độ cố định ``acceptEdits``, tool kê tường minh
(``DEFAULT_TOOLS``), chỉ nạp settings dự án + ``--settings`` của harness,
không MCP ngoài. Đo lại cùng ngày: Glob/Grep có, MCP 0, hook người dùng 0,
guard write-scope vẫn chặn.

**Hook có tới được worktree không** (đo 2026-09-05 trên `par`, claude CLI,
`.claude/` **không** commit nên worktree không có thư mục ấy; mỗi biến thể
một phiên `-p` bảo agent Write một tệp; đếm sự kiện guard tự ghi):

=====  ==============================  ==========  ====
Biến   cwd / cờ                        guard ghi   tệp
=====  ==============================  ==========  ====
A      worktree, ``--settings <tệp>``  2           có
B      worktree, ``--settings <json>`` 2           có
C      gốc dự án (có ``.claude/``)     2           có
D      worktree, không cờ              **0**       có
=====  ==============================  ==========  ====

D là hình dạng của mọi lượt chạy trước G4: story chạy trọn, tệp ghi ra,
**không một guard nào chạy**, và bằng chứng trông y hệt agent ngoan. Vì
thế `implement.py` luôn truyền ``--settings`` (``_attach_settings``), và
cổng story có mục "guard có chạy" đọc nhịp tim ``GUARD_SEEN`` — hai lớp,
lớp sau bắt được lớp trước hỏng.

Bài học đắt hơn: lượt kiểm đầu tiên sau khi có ``--settings`` vẫn báo
"guard không chạy" — bản ghi phiên cho thấy hook chạy 17 lần nhưng agent
ghi file **chỉ bằng Bash**, nên ``write-scope`` (Write|Edit) không được
gọi và không có gì để ghi. Từ đó guard ghi nhịp tim riêng, và
``diff-scope`` ghi ``FILE_CHANGE`` cho tệp có mtime mới hơn lần test cuối.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import Capability, ClientAdapter, RunSpec, Support, child_env
from .stream import RunResult, parse_stream

BINARY = "claude"

#: Chế độ quyền cố định cho phiên con — không để chế độ toàn cục của máy quyết.
PERMISSION_MODE = "acceptEdits"
#: Tool được phép khi vai không kê riêng. `acceptEdits` tự duyệt Write/Edit
#: trong thư mục làm việc nhưng Bash thì phải kê, không thì `-p` từ chối
#: và agent không chạy nổi `aisdlc tool test`. `--disallowed-tools` của vai
#: (reviewer/security) vẫn thắng danh sách này.
DEFAULT_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "Bash", "NotebookEdit")


class ClaudeCodeAdapter(ClientAdapter):
    id = "claude"

    def __init__(self, binary: str = BINARY):
        self.binary = binary

    def available(self) -> bool:
        return bool(shutil.which(self.binary))

    def capabilities(self) -> dict[Capability, Support]:
        return {
            Capability.HEADLESS: Support.NATIVE,          # -p
            Capability.MACHINE_OUTPUT: Support.NATIVE,    # --output-format stream-json
            Capability.PRE_TOOL_GUARD: Support.NATIVE,    # --settings + PreToolUse (S2)
            Capability.TOOL_ALLOWLIST: Support.NATIVE,    # --allowed-tools
            Capability.DIR_ALLOWLIST: Support.NATIVE,     # --add-dir
            Capability.SUBAGENT: Support.NATIVE,          # --agents
            Capability.MODEL_ROUTING: Support.NATIVE,     # --model
            Capability.COST_REPORTING: Support.NATIVE,    # result.total_cost_usd
            Capability.TURN_LIMIT: Support.NATIVE,        # --max-turns
        }

    def build_command(self, spec: RunSpec) -> list[str]:
        """Dựng dòng lệnh. Tách riêng để test được mà không gọi model."""
        cmd = [
            self.binary,
            "-p", spec.prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--permission-mode", PERMISSION_MODE,
            "--setting-sources", "project,local",
            "--strict-mcp-config",
        ]
        if spec.system_prompt:
            cmd += ["--append-system-prompt", spec.system_prompt]
        if spec.model:
            cmd += ["--model", spec.model]
        if spec.max_turns:
            cmd += ["--max-turns", str(spec.max_turns)]
        cmd += ["--allowed-tools", *(spec.allowed_tools or DEFAULT_TOOLS)]
        if spec.disallowed_tools:
            cmd += ["--disallowed-tools", *spec.disallowed_tools]
        if spec.settings_file:
            cmd += ["--settings", str(spec.settings_file)]
        for d in spec.extra_dirs:
            cmd += ["--add-dir", str(d)]
        if spec.session_id:
            cmd += ["--session-id", spec.session_id]
        return cmd

    def run(self, spec: RunSpec) -> RunResult:
        """Chạy một lượt. Môi trường con là **allowlist** (`child_env`, ADR-005
        V2), không phải môi trường của tiến trình gọi: harness chạy từ bên
        trong một phiên Claude là chuyện có thật, và phiên con thừa hưởng cờ
        `CLAUDE*` của phiên cha thì tự chuyển sang Bash thay vì Read/Write
        (hợp quy C3, 2026-09-05); secret của máy thì agent không cần cầm (C9)."""
        if not self.available():
            return RunResult(ok=False, error=f"không tìm thấy lệnh {self.binary}")
        if not Path(spec.workdir).is_dir():
            return RunResult(ok=False, error=f"workdir không tồn tại: {spec.workdir}")

        try:
            proc = subprocess.run(
                self.build_command(spec),
                cwd=str(spec.workdir),
                capture_output=True,
                text=True,
                timeout=spec.timeout_seconds,
                env=child_env(spec.env, allow_prefixes=spec.env_allow),
                stdin=subprocess.DEVNULL,  # không có: CLI chờ stdin 3s mỗi lần
            )
        except subprocess.TimeoutExpired:
            # Hết giờ là lỗi hạ tầng, không phải lỗi chất lượng — phân biệt
            # được thì mới quyết đúng nên thử lại hay chặn story.
            return RunResult(ok=False, error=f"quá {spec.timeout_seconds}s")
        except OSError as e:
            return RunResult(ok=False, error=f"không chạy được: {e}")

        result = parse_stream(proc.stdout.splitlines())
        if not result.raw_result and proc.stderr.strip():
            result.error = proc.stderr.strip()[:500]
        return result
