"""Chạy lệnh trong môi trường cách ly.

Mọi thứ agent chạy — test, linter, quét bảo mật — đều đi qua đây. Mục
đích không phải chống kẻ tấn công có chủ đích, mà chặn những chuyện
thường xảy ra khi agent làm việc tự động: gọi ra mạng ngoài dự kiến, ghi
đè file ngoài phạm vi story, hay leo quyền vì một script cài đặt cẩu thả.

Bốn bậc quyền, tăng dần (SOLUTION mục 5.3). Nguyên tắc: **chọn bậc thấp
nhất đủ dùng**, không phải bậc tiện nhất.

Đã kiểm chứng ở spike S5: ``--network=none`` chặn cả phân giải tên miền;
mount chỉ worktree thì đường dẫn ngoài không tồn tại trong container;
``--cap-drop=ALL --user 1000:1000`` vẫn ghi được workspace nhưng không
ghi được ``/etc``.

Không có Docker thì **suy biến** về subprocess và đánh dấu ``degraded``.
Kết quả vẫn dùng được, nhưng evidence phải ghi rõ mức bảo đảm thấp hơn —
im lặng giả vờ vẫn cách ly là kiểu hỏng tệ nhất (bất biến 10).
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

#: Image mặc định: nhỏ, có sẵn trên máy phát triển.
DEFAULT_IMAGE = "alpine:latest"

#: Người dùng không đặc quyền bên trong container.
SANDBOX_UID_GID = "1000:1000"


class Level(str, Enum):
    """Bậc quyền, tăng dần."""

    READ_ONLY = "READ_ONLY"                  # chỉ đọc, không mạng
    WORKSPACE_WRITE = "WORKSPACE_WRITE"      # ghi trong workspace, không mạng
    WORKSPACE_NETWORK = "WORKSPACE_NETWORK"  # ghi + mạng (cài phụ thuộc)
    PRIVILEGED_TEST = "PRIVILEGED_TEST"      # cho test cần quyền cao

    @property
    def writable(self) -> bool:
        return self is not Level.READ_ONLY

    @property
    def networked(self) -> bool:
        return self in (Level.WORKSPACE_NETWORK, Level.PRIVILEGED_TEST)


@dataclass
class SandboxSpec:
    workspace: Path
    cmd: list[str]
    level: Level = Level.WORKSPACE_WRITE
    image: str = DEFAULT_IMAGE
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 1800
    #: Cho phép suy biến về subprocess khi không có Docker. Đặt False khi
    #: cách ly là bắt buộc và thà hỏng còn hơn chạy không có bảo đảm.
    allow_degraded: bool = True
    #: Dùng Docker hay không. Đặt False khi bộ công cụ của dự án chỉ chạy
    #: đúng trên máy này — ví dụ phụ thuộc có binary biên dịch theo kiến
    #: trúc máy chủ, cài trên host rồi chạy trong container Linux thì hỏng.
    #: Kết quả vẫn ghi `degraded=True`: mức bảo đảm thấp hơn phải hiện ra,
    #: không được im lặng (bất biến 10).
    use_docker: bool = True


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    degraded: bool = False
    timed_out: bool = False
    isolation: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_evidence(self) -> dict:
        return {
            "exit_code": self.exit_code,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
            "isolation": self.isolation,
            "degraded": self.degraded,
            "timed_out": self.timed_out,
        }


def docker_available() -> bool:
    """True khi có cả CLI lẫn daemon đang chạy."""
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10
        ).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def build_docker_args(spec: SandboxSpec) -> list[str]:
    """Dựng dòng lệnh docker. Tách riêng để test được mà không cần chạy."""
    ws = str(Path(spec.workspace).resolve())
    mount_mode = "rw" if spec.level.writable else "ro"

    args = [
        "docker", "run", "--rm",
        "-v", f"{ws}:/workspace:{mount_mode}",
        "-w", "/workspace",
    ]

    if not spec.level.networked:
        args += ["--network=none"]

    if spec.level is not Level.PRIVILEGED_TEST:
        args += ["--cap-drop=ALL", "--user", SANDBOX_UID_GID]

    for k, v in spec.env.items():
        args += ["-e", f"{k}={v}"]

    args.append(spec.image)
    args += spec.cmd
    return args


def run(spec: SandboxSpec) -> SandboxResult:
    """Chạy lệnh, ưu tiên Docker, suy biến khi cần."""
    workspace = Path(spec.workspace)
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace không tồn tại: {workspace}")
    if not spec.cmd:
        raise ValueError("cmd rỗng")

    if spec.use_docker and docker_available():
        return _run_docker(spec)

    if not spec.allow_degraded:
        raise RuntimeError(
            "cần cách ly bằng Docker nhưng "
            + ("cấu hình tắt Docker" if not spec.use_docker else "daemon không chạy")
            + "; đặt allow_degraded=True nếu chấp nhận mức bảo đảm thấp hơn"
        )
    return _run_degraded(spec)


def _run_docker(spec: SandboxSpec) -> SandboxResult:
    args = build_docker_args(spec)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=spec.timeout_seconds
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            exit_code=124,
            stderr=f"quá {spec.timeout_seconds}s",
            duration_ms=int((time.monotonic() - started) * 1000),
            timed_out=True,
            isolation=f"docker/{spec.level.value}",
        )
    return SandboxResult(
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=int((time.monotonic() - started) * 1000),
        isolation=f"docker/{spec.level.value}",
    )


def _run_degraded(spec: SandboxSpec) -> SandboxResult:
    """Chạy thẳng trên máy. Không có cách ly — chỉ giới hạn thư mục làm việc."""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            spec.cmd,
            cwd=str(spec.workspace),
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            env={**spec.env} or None,
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            exit_code=124,
            stderr=f"quá {spec.timeout_seconds}s",
            duration_ms=int((time.monotonic() - started) * 1000),
            degraded=True,
            timed_out=True,
            isolation="subprocess/degraded",
        )
    except OSError as e:
        return SandboxResult(
            exit_code=127,
            stderr=str(e),
            duration_ms=int((time.monotonic() - started) * 1000),
            degraded=True,
            isolation="subprocess/degraded",
        )
    return SandboxResult(
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=int((time.monotonic() - started) * 1000),
        degraded=True,
        isolation="subprocess/degraded",
    )
