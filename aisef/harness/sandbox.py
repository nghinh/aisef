"""Chạy lệnh trong môi trường cách ly.

Mọi thứ agent chạy — test, linter, quét bảo mật — đều đi qua đây. Mục
đích không phải chống kẻ tấn công có chủ đích, mà chặn những chuyện
thường xảy ra khi agent làm việc tự động: gọi ra mạng ngoài dự kiến, ghi
đè file ngoài phạm vi story, hay leo quyền vì một script cài đặt cẩu thả.

Bốn bậc quyền, tăng dần (SOLUTION mục 5.3). Nguyên tắc: **chọn bậc thấp
nhất đủ dùng**, không phải bậc tiện nhất.

Hai tầng tách bạch (ADR-005 V5, học từ SWE-ReX/Harbor):

* **Bậc quyền khai yêu cầu** — ``Level.requires()`` trả tập ``Guarantee``
  mà bậc ấy cần: không mạng, chỉ đọc, không root…
* **Provider khai năng lực** — ``ExecutionProvider.guarantees(level)`` nói
  thật nó bảo đảm được gì ở bậc ấy (``Support`` của ``clients/base.py``:
  đọc tên thật, không suy diễn).

``run()`` so hai tầng: thiếu bảo đảm nào thì ``degraded=True`` **kèm tên
bảo đảm thiếu** trong ``SandboxResult.missing`` — "suy biến" không nói
được thiếu gì thì người đọc bằng chứng không biết mình đang tin vào cái gì
(bất biến 10). ``allow_degraded=False`` thì hỏng ngay lúc chọn provider,
trước khi chạy lệnh nào.

Ba provider: ``docker`` (mặc định), ``local`` (chạy thẳng, mọi bảo đảm
UNSUPPORTED), ``fake`` (cho test, trả kết quả theo kịch bản). Backend ngoài
khai ``"mô-đun:Lớp"`` ở ``sandbox.provider``. Không có session, không có
daemon: một lệnh, một lần chạy. ``host`` (chạy thật trên máy, khai NATIVE)
chỉ suite đơn vị dùng — ``tests/__init__.py`` — không phải lựa chọn của dự án.

Bảo đảm của Docker đã kiểm bằng lần chạy thật, xem
``docs/SANDBOX-CONFORMANCE.md`` (S1–S5, sinh bởi
``python3 -m tests.sandbox_conformance``) và ``tests/test_sandbox.py``
``TestIsolation`` (đánh dấu ``needs_docker``).
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from ..clients.base import Support

#: Image mặc định: nhỏ, có sẵn trên máy phát triển.
DEFAULT_IMAGE = "alpine:latest"

#: Người dùng không đặc quyền bên trong container.
SANDBOX_UID_GID = "1000:1000"


class Guarantee(str, Enum):
    """Điều một provider có thể bảo đảm khi chạy lệnh."""

    NETWORK_NONE = "network_none"        # không ra được mạng, kể cả DNS
    READ_ONLY_FS = "read_only_fs"        # không ghi được workspace
    NON_ROOT = "non_root"                # không root, không capability
    NO_HOST_MOUNT = "no_host_mount"      # không thấy đĩa máy chủ (mount worktree là thiết kế → Docker cũng không có)
    SECRETS_ABSENT = "secrets_absent"    # env bên trong chỉ có `spec.env`, không thừa hưởng máy chủ


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

    def requires(self) -> set[Guarantee]:
        """Bảo đảm bậc này **cần** — provider thiếu cái nào là suy biến cái ấy.

        Mọi bậc cần ``SECRETS_ABSENT``: không bậc nào có lý do nhận bí mật
        của máy chủ. ``NO_HOST_MOUNT`` không bậc nào đòi — mount worktree
        là thiết kế, provider vẫn phải khai để bảng năng lực nói thật."""
        need = {Guarantee.SECRETS_ABSENT}
        if not self.networked:
            need.add(Guarantee.NETWORK_NONE)
        if not self.writable:
            need.add(Guarantee.READ_ONLY_FS)
        if self is not Level.PRIVILEGED_TEST:
            need.add(Guarantee.NON_ROOT)
        return need


@dataclass
class SandboxSpec:
    workspace: Path
    cmd: list[str]
    level: Level = Level.WORKSPACE_WRITE
    image: str = DEFAULT_IMAGE
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 1800
    #: Cho phép suy biến — chạy trên provider thiếu bảo đảm bậc này cần.
    #: Đặt False khi cách ly là bắt buộc và thà hỏng còn hơn chạy không
    #: có bảo đảm: lỗi nổ lúc chọn provider, trước khi chạy lệnh nào.
    allow_degraded: bool = True
    #: Dùng Docker hay không. Đặt False khi bộ công cụ của dự án chỉ chạy
    #: đúng trên máy này — ví dụ phụ thuộc có binary biên dịch theo kiến
    #: trúc máy chủ, cài trên host rồi chạy trong container Linux thì hỏng.
    #: Tương đương ``provider="local"``; giữ để cấu hình cũ còn chạy.
    use_docker: bool = True
    #: Tên provider (``docker`` · ``local`` · ``fake`` · ``"mô-đun:Lớp"``).
    #: Rỗng = ``docker``, hạ xuống ``local`` khi ``use_docker=False``.
    provider: str = ""
    #: Thư mục gắn thêm vào workspace: `đường tương đối trong workspace →
    #: đường trên máy`. Cho worktree sạch dựng từ SHA (ADR-005 V6): nó không
    #: có `node_modules`/venv — chúng không nằm trong git — nên mượn của dự án
    #: như cây thường vẫn có. Docker: bind mount cùng mode với workspace; suy
    #: biến: symlink trong workspace (chỉ khi chỗ ấy còn trống). Chỉ dùng cho
    #: cây tạm harness sở hữu — symlink là dấu vết trên cây.
    mounts: dict[str, Path] = field(default_factory=dict)


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    degraded: bool = False
    timed_out: bool = False
    #: ``"<provider>/<bậc>"`` — ví dụ ``docker/WORKSPACE_WRITE``, ``local/READ_ONLY``.
    isolation: str = ""
    #: Tên bảo đảm bậc này cần mà provider không có. Rỗng khi đủ.
    missing: list[str] = field(default_factory=list)
    #: Lỗi **hạ tầng** — daemon không trả lời, không kéo được image — khác
    #: hẳn lệnh thoát khác 0. Gộp hai thứ thì "test đỏ" hoá ra là Docker
    #: hỏng, và người sửa test trong khi chỗ cần sửa là máy (SWE-ReX 511).
    provider_error: str = ""

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
            "missing": list(self.missing),
            "timed_out": self.timed_out,
            "provider_error": self.provider_error,
        }


class ExecutionProvider(Protocol):
    """Một cách chạy lệnh. Khai thật mình bảo đảm được gì; ``run`` một lần."""

    id: str

    def available(self) -> bool: ...

    def guarantees(self, level: Level) -> dict[Guarantee, Support]: ...

    def run(self, spec: SandboxSpec) -> SandboxResult: ...


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


def build_docker_args(spec: SandboxSpec, *, name: str = "") -> list[str]:
    """Dựng dòng lệnh docker. Tách riêng để test được mà không cần chạy."""
    ws = str(Path(spec.workspace).resolve())
    mount_mode = "rw" if spec.level.writable else "ro"

    args = [
        "docker", "run", "--rm",
        "-v", f"{ws}:/workspace:{mount_mode}",
        "-w", "/workspace",
    ]
    if name:
        args += ["--name", name]
    for rel, src in spec.mounts.items():
        args += ["-v", f"{Path(src).resolve()}:/workspace/{rel}:{mount_mode}"]

    if not spec.level.networked:
        args += ["--network=none"]

    if spec.level is not Level.PRIVILEGED_TEST:
        args += ["--cap-drop=ALL", "--user", SANDBOX_UID_GID]

    # Chỉ `spec.env` đi vào container — không thừa hưởng môi trường máy
    # chủ. Đây là toàn bộ cơ sở của bảo đảm SECRETS_ABSENT; đừng thêm
    # `--env-file`/`-e KEY` (không giá trị) ở đây, docker sẽ lấy từ host.
    for k, v in spec.env.items():
        args += ["-e", f"{k}={v}"]

    args.append(spec.image)
    args += spec.cmd
    return args


class DockerProvider:
    """Container dùng một lần: mount worktree, non-root, không mạng theo bậc."""

    id = "docker"

    def available(self) -> bool:
        return docker_available()

    def guarantees(self, level: Level) -> dict[Guarantee, Support]:
        on = Support.NATIVE
        off = Support.UNSUPPORTED
        return {
            Guarantee.NETWORK_NONE: off if level.networked else on,
            Guarantee.READ_ONLY_FS: on if not level.writable else off,
            Guarantee.NON_ROOT: off if level is Level.PRIVILEGED_TEST else on,
            Guarantee.NO_HOST_MOUNT: off,  # mount worktree là thiết kế
            Guarantee.SECRETS_ABSENT: on,  # `-e` chỉ chuyển `spec.env`
        }

    def run(self, spec: SandboxSpec) -> SandboxResult:
        return _run_docker(spec)


class LocalProvider:
    """Chạy thẳng trên máy. Không bảo đảm gì — chỉ giới hạn thư mục làm việc."""

    id = "local"

    def available(self) -> bool:
        return True

    def guarantees(self, level: Level) -> dict[Guarantee, Support]:
        return {g: Support.UNSUPPORTED for g in Guarantee}

    def run(self, spec: SandboxSpec) -> SandboxResult:
        return _run_degraded(spec)


class FakeProvider:
    """Trả kết quả theo kịch bản, khai mọi bảo đảm NATIVE — cho test
    `gate`/`qa`/`tools` chạy không cần Docker. Hết kịch bản thì lặp kết
    quả cuối; không có kịch bản thì mọi lệnh xanh. ``calls`` giữ spec
    từng lần gọi để test kiểm bậc quyền và lệnh."""

    id = "fake"

    def __init__(self, outputs: list[SandboxResult] | None = None):
        self.outputs = list(outputs or [])
        self.calls: list[SandboxSpec] = []

    def available(self) -> bool:
        return True

    def guarantees(self, level: Level) -> dict[Guarantee, Support]:
        return {g: Support.NATIVE for g in Guarantee}

    def run(self, spec: SandboxSpec) -> SandboxResult:
        self.calls.append(spec)
        if not self.outputs:
            return SandboxResult(exit_code=0)
        out = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        return SandboxResult(**{k: v for k, v in vars(out).items()})


class HostProvider(LocalProvider):
    """**Chỉ cho test đơn vị** — giả lập cách ly. Chạy lệnh thật bằng
    subprocess trên máy như ``local``, nhưng khai mọi bảo đảm NATIVE nên kết
    quả không ``degraded`` dù không có container. Chấp nhận vì suite đơn vị
    kiểm **luật của harness** (bằng chứng ghi gì, cổng đọc gì, "không chạy
    được ≠ đỏ"), không kiểm Docker; Docker thật đo ở test đánh dấu
    ``needs_docker`` (``AISEF_TEST_DOCKER=1``) và hợp quy S1–S5. Mỗi
    container mất 6–18 s trên máy đo, suite đầy đủ 25–60 phút — đó là lý do
    nó tồn tại (kế hoạch phát hành A2). Không nằm trong ``PROVIDERS``:
    ``sandbox.provider = "host"`` trong dự án bị từ chối như tên lạ;
    ``tests/__init__.py`` đặt nó vào chỗ ``docker``."""

    id = "host"

    def guarantees(self, level: Level) -> dict[Guarantee, Support]:
        return {g: Support.NATIVE for g in Guarantee}


#: Provider theo tên. Test đăng ký `fake` qua `using()`; backend ngoài đi
#: qua `import_path` và được nhớ lại ở đây sau lần nạp đầu.
PROVIDERS: dict[str, ExecutionProvider] = {
    "docker": DockerProvider(),
    "local": LocalProvider(),
}


def resolve_provider(name: str) -> ExecutionProvider:
    """``docker`` · ``local`` · tên đã đăng ký · ``"mô-đun:Lớp"`` (5 dòng, như factory Harbor)."""
    if name in PROVIDERS:
        return PROVIDERS[name]
    if ":" not in name:
        raise ValueError(
            f"sandbox.provider={name!r} does not exist; available: {', '.join(sorted(PROVIDERS))} "
            "or \"module:Class\""
        )
    mod, _, cls = name.partition(":")
    provider = getattr(importlib.import_module(mod), cls)()
    PROVIDERS[name] = provider
    return provider


class using:
    """Đăng ký tạm một provider (thường là ``FakeProvider``) dưới ``provider.id``.

        with sandbox.using(FakeProvider([...])) as fake:
            run_suite(..., config=Config({**DEFAULTS, "sandbox.provider": "fake"}))
    """

    def __init__(self, provider: ExecutionProvider):
        self.provider = provider

    def __enter__(self):
        self._prev = PROVIDERS.get(self.provider.id)
        PROVIDERS[self.provider.id] = self.provider
        return self.provider

    def __exit__(self, *exc):
        if self._prev is None:
            PROVIDERS.pop(self.provider.id, None)
        else:
            PROVIDERS[self.provider.id] = self._prev


def missing_guarantees(provider: ExecutionProvider, level: Level) -> list[str]:
    """Tên bảo đảm ``level`` cần mà ``provider`` không chặn được tại nguồn."""
    have = provider.guarantees(level)
    return sorted(
        g.value for g in level.requires()
        if not have.get(g, Support.UNSUPPORTED).blocks_at_source
    )


def select_provider(spec: SandboxSpec) -> tuple[ExecutionProvider, list[str]]:
    """Chọn provider và tính bảo đảm thiếu — **trước** khi chạy lệnh nào.

    Docker không có daemon thì lùi về ``local`` như trước; nhưng lùi là
    suy biến, và ``allow_degraded=False`` từ chối ngay tại đây với tên
    bảo đảm thiếu, không đợi tới lúc chạy."""
    name = spec.provider or "docker"
    if name == "docker" and not spec.use_docker:
        name = "local"
    provider = resolve_provider(name)
    why = ""
    if not provider.available():
        if name == "local":
            raise RuntimeError("provider local not available — nothing to fall back to")
        why = "daemon not running" if name == "docker" else f"provider {name} not available"
        provider = resolve_provider("local")
    elif name == "local" and not spec.use_docker and not spec.provider:
        why = "configuration disabled Docker"

    missing = missing_guarantees(provider, spec.level)
    if missing and not spec.allow_degraded:
        raise RuntimeError(
            f"level {spec.level.value} requires isolation but provider {provider.id}"
            + (f" ({why})" if why else "")
            + f" is missing guarantees: {', '.join(missing)}"
            "; set allow_degraded=True to accept a lower assurance level"
        )
    return provider, missing


def run(spec: SandboxSpec) -> SandboxResult:
    """Chạy lệnh trên provider đã chọn; kết quả mang tên provider, bậc, và bảo đảm thiếu."""
    workspace = Path(spec.workspace)
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace does not exist: {workspace}")
    if not spec.cmd:
        raise ValueError("cmd is empty")

    provider, missing = select_provider(spec)
    result = provider.run(spec)
    result.isolation = f"{provider.id}/{spec.level.value}"
    result.missing = missing
    result.degraded = bool(missing)
    return result


#: Docker CLI thoát 125 khi **chính docker** hỏng (daemon, kéo image, cờ
#: sai) — khác 126/127 và mã của lệnh bên trong. Tài liệu `docker run`.
_DOCKER_INFRA_EXIT = 125


def _run_docker(spec: SandboxSpec) -> SandboxResult:
    name = f"aisef-{uuid.uuid4().hex[:12]}"
    args = build_docker_args(spec, name=name)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=spec.timeout_seconds
        )
    except subprocess.TimeoutExpired:
        # Giết CLI không giết container: `sleep 9999` sẽ chạy tiếp gần
        # ba giờ và giữ mount worktree. Đo ở S5 hợp quy sandbox.
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
        return SandboxResult(
            exit_code=124,
            stderr=f"exceeded {spec.timeout_seconds}s",
            duration_ms=int((time.monotonic() - started) * 1000),
            timed_out=True,
        )
    except OSError as e:
        return SandboxResult(
            exit_code=_DOCKER_INFRA_EXIT,
            stderr=str(e),
            duration_ms=int((time.monotonic() - started) * 1000),
            provider_error=f"cannot invoke docker: {e}",
        )
    provider_error = ""
    if proc.returncode == _DOCKER_INFRA_EXIT:
        last = [l for l in proc.stderr.strip().splitlines() if l.strip()]
        provider_error = (last[-1] if last else "docker exited 125").strip()[:300]
    return SandboxResult(
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=int((time.monotonic() - started) * 1000),
        provider_error=provider_error,
    )


def _link_mounts(spec: SandboxSpec) -> None:
    """Không có bind mount ngoài Docker: symlink vào workspace thay thế.
    Chỗ đã có gì (dự án commit `node_modules`? thì đó là của họ) — không đè."""
    for rel, src in spec.mounts.items():
        dst = Path(spec.workspace) / rel
        if not dst.exists() and not dst.is_symlink():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(Path(src).resolve())


def _run_degraded(spec: SandboxSpec) -> SandboxResult:
    """Chạy thẳng trên máy. Không có cách ly — chỉ giới hạn thư mục làm việc."""
    _link_mounts(spec)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            spec.cmd,
            cwd=str(spec.workspace),
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            # Thừa hưởng máy chủ rồi đè `spec.env`. Trước đây `{**spec.env}
            # or None`: env khác rỗng là mất PATH, lệnh ngoài /bin không
            # tìm thấy — và đó cũng là lý do SECRETS_ABSENT ở đây UNSUPPORTED.
            env={**os.environ, **spec.env},
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            exit_code=124,
            stderr=f"exceeded {spec.timeout_seconds}s",
            duration_ms=int((time.monotonic() - started) * 1000),
            timed_out=True,
        )
    except OSError as e:
        return SandboxResult(
            exit_code=127,
            stderr=str(e),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    return SandboxResult(
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
