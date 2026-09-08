"""Map mockup — **nửa đối chiếu**: mở route thật, so với hợp đồng.

Nạp hợp đồng vào prompt mới chỉ là nói cho agent biết phải dựng gì. Nửa
này kiểm xem nó có dựng thật không — bằng cách chạy ứng dụng, mở đúng
route, và đọc cây accessibility như một người dùng màn hình đọc.

Ba mức đối chiếu, và chỉ dùng hai:

* **cấu trúc** (dùng, và chặn) — component hợp đồng đã hứa có mặt không;
* **thị giác bằng model** (chưa dùng ở đây, chỉ cảnh báo) — bố cục có hợp lý;
* **so từng điểm ảnh** (**không bao giờ dùng**) — mockup tĩnh và ứng dụng
  thật không bao giờ trùng từng điểm; cổng kiểu đó đỏ liên tục rồi bị tắt,
  mà cổng bị tắt còn tệ hơn không có cổng.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

from ..config import Config
from ..control.design_contract import DesignContract
from . import browser
from .aria import MapResult, compare, parse_aria_snapshot
from .observe import MOCKUP_MAP, EvidenceStore


@dataclass
class VerifyResult:
    results: list[MapResult] = field(default_factory=list)
    unavailable: str = ""

    @property
    def passed(self) -> bool:
        return not self.unavailable and all(r.passed for r in self.results)

    def summary(self) -> str:
        if self.unavailable:
            return f"map mockup: ✗ {self.unavailable}"
        if not self.results:
            return "map mockup: story does not build any screen"
        return "\n".join(r.summary() for r in self.results)


class AppServer:
    """Chạy dev server của dự án đủ lâu để đối chiếu, rồi tắt.

    Không dùng cổng cố định trong code: hai story chạy song song sẽ giẫm
    nhau. Cổng lấy từ cấu hình của dự án, và mỗi story chạy trong worktree
    riêng nên dự án tự quyết.
    """

    def __init__(self, command: str, base_url: str, *, cwd: Path, ready_timeout: int = 60):
        self.command = command
        self.base_url = base_url.rstrip("/") + "/"
        self.cwd = Path(cwd)
        self.ready_timeout = ready_timeout
        self.proc: subprocess.Popen | None = None
        self.log = ""

    def __enter__(self) -> "AppServer":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def already_running(self) -> bool:
        return _responds(self.base_url, timeout=2)

    def start(self) -> str:
        """Chuỗi rỗng nếu sẵn sàng; ngược lại là lý do không chạy được."""
        if self.proc is not None and self.proc.poll() is None:
            return ""  # chính mình đã dựng (gọi start() lần hai qua `with`)
        if self.already_running():
            if not self.command:
                return ""  # dự án không khai dev_command: người dùng tự chạy app, dùng luôn
            # Có dev_command mà cổng đã có người trả lời thì không nhận vơ
            # (lỗi 15, đo 2026-09-05 trên e9): vite của một worktree đã gỡ vẫn
            # giữ cổng 5199, cổng map mockup của hai lượt sau "mở app" và thấy
            # trang trống — chấm sai app, story trượt. Thứ đang trả lời ở cổng
            # này không phải app harness vừa dựng từ worktree của story.
            return (
                f"port {self.base_url} is already occupied by another process "
                f"({occupant(self.base_url)}) — not this story's app; "
                "stop it or change `app.base_url`"
            )
        if not self.command:
            return (
                "project has not declared `app.dev_command` so the app cannot "
                "be opened for mockup comparison"
            )

        import shlex

        try:
            self.proc = subprocess.Popen(
                shlex.split(self.command),
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,  # để stop() giết được cả nhóm
            )
        except OSError as e:
            return f"cannot run `{self.command}`: {e}"

        deadline = time.time() + self.ready_timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                out = (self.proc.stdout.read() if self.proc.stdout else "")[-500:]
                return f"dev server exited early (code {self.proc.returncode}): {out.strip()}"
            if _responds(self.base_url, timeout=2):
                return ""
            time.sleep(0.5)
        return f"dev server not responding at {self.base_url} after {self.ready_timeout}s"

    def stop(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            # Giết cả nhóm tiến trình: `npm run dev` chết mà `node vite` con
            # sống sót thì cổng còn bị giữ và `.vite/` được ghi lại vào
            # worktree đã gỡ (lỗi 13 + 15).
            _signal_group(self.proc, signal.SIGTERM)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _signal_group(self.proc, signal.SIGKILL)  # dev server hay bỏ qua SIGTERM
                self.proc.wait(timeout=5)
        # Đóng ống: một đợt 15 story mà mỗi story rò một mô tả tệp thì tới
        # story thứ n sẽ hỏng vì lý do chẳng liên quan gì tới story đó.
        if self.proc.stdout and not self.proc.stdout.closed:
            self.proc.stdout.close()
        self.proc = None

    def url_for(self, route: str) -> str:
        return urljoin(self.base_url, route.lstrip("/"))


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            pass


def occupant(url: str) -> str:
    """Ai đang giữ cổng — để thông báo chỉ đúng tiến trình, không bắt đoán."""
    from urllib.parse import urlparse

    port = urlparse(url).port
    if not port:
        return "unknown"
    try:
        out = subprocess.run(["lsof", "-nP", "-t", "-i", f":{port}"], capture_output=True,
                             text=True, timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if not out:
        return "unknown"
    pid = out[0]
    try:
        cwd = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", pid, "-Fn"], capture_output=True,
                             text=True, timeout=5).stdout
        where = next((l[1:] for l in cwd.splitlines() if l.startswith("n")), "")
    except (OSError, subprocess.SubprocessError):
        where = ""
    return f"pid {pid}" + (f", cwd {where}" if where else "")


def _responds(url: str, *, timeout: float = 2) -> bool:
    try:
        with closing(urllib.request.urlopen(url, timeout=timeout)):
            return True
    except (urllib.error.HTTPError,):
        return True  # có server trả lời, chỉ là mã lỗi — vẫn là "đang chạy"
    except (urllib.error.URLError, OSError, ValueError, socket.timeout):
        return False


def concrete_route(route: str) -> str:
    """Thay tham số động bằng giá trị mẫu: `/note/:id` → `/note/1`.

    Route có tham số không mở thẳng được. Giá trị mẫu là quy ước giữa
    harness và ứng dụng: dữ liệu hạt giống của môi trường dev phải có bản
    ghi `1`, nếu không đây là chỗ hỏng thật và cổng nên báo.
    """
    parts = []
    for seg in route.split("/"):
        if seg.startswith(":") or (seg.startswith("[") and seg.endswith("]")):
            parts.append("1")
        else:
            parts.append(seg)
    return "/".join(parts) or "/"


def verify_screens(
    project: Path | str,
    contract: DesignContract,
    screen_ids: list[str],
    *,
    config: Config | None = None,
    story_id: str = "",
    artifact_root: Path | str | None = None,
    candidate: str = "",
) -> VerifyResult:
    """Mở từng route thật và đối chiếu với hợp đồng.

    ``candidate`` là SHA bản đang kiểm — màn hình đối chiếu ở bản nào thì
    bằng chứng nói bản ấy (ADR-004 R1)."""
    project = Path(project)
    cfg = config or Config.load(project)
    out = VerifyResult()

    screens = [contract.by_id(s) for s in screen_ids]
    screens = [s for s in screens if s is not None]
    if not screens:
        return out

    reason = browser.availability(project)
    if reason:
        out.unavailable = reason
        return out

    server = AppServer(
        str(cfg.get("app.dev_command", "")),
        str(cfg.get("app.base_url", "http://localhost:5173")),
        cwd=project,
        ready_timeout=int(cfg.get("app.ready_timeout_seconds", 60)),
    )
    with server:
        why = server.start()
        if why:
            out.unavailable = why
            return out

        urls = {s.id: server.url_for(concrete_route(s.route or "/")) for s in screens}
        jobs = [{"id": s.id, "url": urls[s.id]} for s in screens]
        rendered = browser.render(jobs, project=project)

    if rendered.unavailable:
        out.unavailable = rendered.unavailable
        return out

    store = (EvidenceStore(artifact_root, candidate=candidate)
             if (story_id and artifact_root) else None)
    for screen in screens:
        got = rendered.by_id(screen.id)
        if got is None or got.error:
            result = compare(
                screen.components, [], screen_id=screen.id, route=screen.route,
                data_roles=screen.data_roles,
            )
        else:
            result = compare(
                screen.components,
                parse_aria_snapshot(got.snapshot),
                screen_id=screen.id,
                route=screen.route,
                data_roles=screen.data_roles,
            )
        out.results.append(result)
        if store:
            error = got.error if got else "cannot open route"
            if (got is not None and not got.error and screen.components
                    and not result.matched and not getattr(result, "extra", None)):
                # Không khớp gì và cũng không thừa gì = trang trống. Với route
                # có tham số, gần như chắc là thiếu bản ghi hạt giống `1`.
                error = f"page rendered no components at {urls[screen.id]}"
                if concrete_route(screen.route or "/") != (screen.route or "/"):
                    error += " — route has params: dev environment needs a record with id `1` (seed data)"
            store.record(story_id, _event(result, error))
    return out


def _event(result: MapResult, error: str):
    from .observe import Event

    return Event(
        kind=MOCKUP_MAP,
        name=result.screen_id,
        ok=result.passed,
        detail={**result.to_evidence(), "error": error},
    )
