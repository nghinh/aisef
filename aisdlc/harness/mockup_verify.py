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
            return "map mockup: story không dựng màn hình nào"
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
        if self.already_running():
            return ""  # người dùng đang chạy sẵn — dùng luôn, đừng chạy thêm
        if not self.command:
            return (
                "dự án chưa khai `app.dev_command` nên không mở được ứng dụng "
                "để đối chiếu với mockup"
            )

        import shlex

        try:
            self.proc = subprocess.Popen(
                shlex.split(self.command),
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as e:
            return f"không chạy được `{self.command}`: {e}"

        deadline = time.time() + self.ready_timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                out = (self.proc.stdout.read() if self.proc.stdout else "")[-500:]
                return f"dev server thoát sớm (mã {self.proc.returncode}): {out.strip()}"
            if _responds(self.base_url, timeout=2):
                return ""
            time.sleep(0.5)
        return f"dev server không phản hồi tại {self.base_url} sau {self.ready_timeout}s"

    def stop(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()  # dev server hay bỏ qua SIGTERM
                self.proc.wait(timeout=5)
        # Đóng ống: một đợt 15 story mà mỗi story rò một mô tả tệp thì tới
        # story thứ n sẽ hỏng vì lý do chẳng liên quan gì tới story đó.
        if self.proc.stdout and not self.proc.stdout.closed:
            self.proc.stdout.close()
        self.proc = None

    def url_for(self, route: str) -> str:
        return urljoin(self.base_url, route.lstrip("/"))


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
) -> VerifyResult:
    """Mở từng route thật và đối chiếu với hợp đồng."""
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

        jobs = [
            {"id": s.id, "url": server.url_for(concrete_route(s.route or "/"))}
            for s in screens
        ]
        rendered = browser.render(jobs, project=project)

    if rendered.unavailable:
        out.unavailable = rendered.unavailable
        return out

    store = EvidenceStore(artifact_root) if (story_id and artifact_root) else None
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
            store.record(
                story_id,
                _event(result, got.error if got else "không mở được route"),
            )
    return out


def _event(result: MapResult, error: str):
    from .observe import Event

    return Event(
        kind=MOCKUP_MAP,
        name=result.screen_id,
        ok=result.passed,
        detail={**result.to_evidence(), "error": error},
    )
