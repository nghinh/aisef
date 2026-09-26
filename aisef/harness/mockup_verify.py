"""Map mockup — **verification half**: open the real route, compare against the contract.

Loading the contract into the prompt only tells the agent what to build. This
half checks whether it actually built it — by running the app, opening the
correct route, and reading the accessibility tree the way a screen reader does.

Three levels of comparison, only two are used:

* **structural** (used, and blocking) — are the contracted components present;
* **visual via model** (not used here, warning only) — is the layout reasonable;
* **pixel-perfect** (**never used**) — a static mockup and a live app never
  match pixel-for-pixel; such a gate stays red permanently then gets disabled,
  and a disabled gate is worse than no gate at all.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

from ..config import Config
from ..clients.base import runnable, split_command
from ..control.design_contract import DesignContract
from . import browser
from .aria import MapResult, compare, has_items, parse_aria_snapshot
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
    """Run the project's dev server long enough for verification, then stop.

    No hardcoded port: two stories running in parallel would collide. The port
    comes from the project config, and each story runs in its own worktree so
    the project decides.

    Optional ``lease_root`` + ``run_id`` arguments wire the candidate-bound
    identity check: only the dev server this run started may answer ready
    probes, and the lease file records who owns the port.
    """

    def __init__(self, command: str, base_url: str, *, cwd: Path, ready_timeout: int = 60,
                  lease_root: Path | None = None, run_id: str = ""):
        self.command = command
        self.base_url = base_url.rstrip("/") + "/"
        self.cwd = Path(cwd)
        self.ready_timeout = ready_timeout
        self.proc: subprocess.Popen | None = None
        self.log = ""
        self.lease_root = lease_root
        self.run_id = run_id
        self._lease_fd: int | None = None

    def __enter__(self) -> "AppServer":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def already_running(self) -> bool:
        return _responds(self.base_url, timeout=2)

    def start(self) -> str:
        """Empty string if ready; otherwise the reason it cannot run."""
        if self.proc is not None and self.proc.poll() is None:
            return ""  # already started by us (second start() call via `with`)
        # Reserve the port for this candidate before we spawn anything.
        # ``lease_root`` is None in tests where isolation isn't required;
        # the earlier race-free path is preserved.
        if self.lease_root is not None and self.run_id:
            from .server_identity import acquire_port_lease, write_lease, ServerLease
            now = time.time()
            self._lease_fd = acquire_port_lease(
                self.lease_root, self.run_id, self.base_url)
            if self._lease_fd is not None:
                lease = ServerLease(
                    run_id=self.run_id, story_id=self.run_id,
                    candidate=self.run_id, base_url=self.base_url,
                    pid=os.getpid(), started_at=now,
                )
                write_lease(self.lease_root, lease)
        if self.already_running():
            if not self.command:
                return ""  # project has no dev_command: user runs the app themselves, use as-is
            # Our own leftover, not a stranger. The e2e suite runs Playwright
            # with a `webServer` on this same port moments earlier and does not
            # always release it before the mockup comparison starts — measured
            # on todo-oc 2026-09-13, where the occupant's cwd was this very
            # story's worktree and the story failed `preservation` as
            # "unverifiable" (lỗi 140). The harness was racing itself, and the
            # message blamed a foreign app while printing our own directory.
            #
            # Reclaim only when the working directory matches: killing a
            # process in our own worktree is ours to do, killing anything else
            # is not (bug 15 stands — a stranger's app must never be graded).
            pid, cwd = occupant_pid_cwd(self.base_url)
            if pid and cwd and self.cwd and _cung_cay(cwd, str(self.cwd)):
                if not _giai_phong_cong(pid, self.base_url):
                    return ""               # still up, still our own tree: use it
            # dev_command is set but port already has a responder — don't claim it
            # (bug 15, measured 2026-09-05 on e9): vite from a removed worktree still
            # held port 5199, mockup-map gate in the next two rounds "opened the app"
            # and saw a blank page — graded the wrong app, story failed. The process
            # answering on this port is not the app harness just built from the story's worktree.
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

        try:
            self.proc = subprocess.Popen(
                runnable(split_command(self.command)),
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                   if sys.platform == "win32"
                   else {"start_new_session": True}),
            )
        except OSError as e:
            return f"cannot run `{self.command}`: {e}"

        deadline = time.time() + self.ready_timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                out = (self.proc.stdout.read() if self.proc.stdout else "")[-500:]
                return f"dev server exited early (code {self.proc.returncode}): {out.strip()}"
            if self.lease_root is not None and self.run_id:
                from .server_identity import ready_with_identity
                who = ready_with_identity(self.base_url, self.run_id, attempts=1)
                if who is True:
                    return ""
                if who is False:               # SS-51: a responder that echoes ANOTHER id is not our server
                    return f"another server answers at {self.base_url} (identity mismatch) — not this run's app"
                # no identity endpoint: the port was free before OUR process was launched under OUR lease, so a
                # responder now is ours by construction (the lease keeps other runs off this port)
                if self._lease_fd is not None and _responds(self.base_url, timeout=2):
                    return ""
            elif _responds(self.base_url, timeout=2):
                return ""
            time.sleep(0.5)
        return f"dev server not responding at {self.base_url} after {self.ready_timeout}s"

    def stop(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            _kill_tree(self.proc)
        # Close pipes: a batch of 15 stories each leaking one fd means story n
        # will fail for a reason completely unrelated to that story.
        if self.proc.stdout and not self.proc.stdout.closed:
            self.proc.stdout.close()
        self.proc = None
        if self.lease_root is not None and self.run_id:
            from .server_identity import release_port_lease, remove_lease
            release_port_lease(
                self.lease_root, self.run_id,
                fd=self._lease_fd if self._lease_fd is not None else -1,
            )
            remove_lease(self.lease_root, self.run_id)
            self._lease_fd = None

    def url_for(self, route: str) -> str:
        return urljoin(self.base_url, route.lstrip("/"))


def _kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.call(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.wait(timeout=10)
        return
    import signal
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        proc.wait(timeout=5)


def occupant_pid_cwd(url: str) -> tuple[str, str]:
    """(pid, cwd) of whoever holds the port — ("", "") when it cannot be told."""
    from urllib.parse import urlparse

    port = urlparse(url).port
    if not port:
        return ("", "")
    try:
        out = subprocess.run(["lsof", "-nP", "-t", "-i", f":{port}"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return ("", "")
    if not out:
        return ("", "")
    pid = out[0]
    try:
        cwd = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", pid, "-Fn"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=5).stdout
        where = next((l[1:] for l in cwd.splitlines() if l.startswith("n")), "")
    except (OSError, subprocess.SubprocessError):
        where = ""
    return (pid, where)


def occupant(url: str) -> str:
    """Who holds the port — for reporting the exact process, not guessing."""
    from urllib.parse import urlparse

    port = urlparse(url).port
    if not port:
        return "unknown"
    try:
        out = subprocess.run(["lsof", "-nP", "-t", "-i", f":{port}"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if not out:
        return "unknown"
    pid = out[0]
    try:
        cwd = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", pid, "-Fn"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=5).stdout
        where = next((l[1:] for l in cwd.splitlines() if l.startswith("n")), "")
    except (OSError, subprocess.SubprocessError):
        where = ""
    return f"pid {pid}" + (f", cwd {where}" if where else "")


def _cung_cay(a: str, b: str) -> bool:
    """Same directory, symlinks and trailing slashes aside."""
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def _giai_phong_cong(pid: str, url: str) -> bool:
    """Stop the process holding ``url`` and report whether the **port** freed.

    The port is the question, not the pid: a child of this process stays a
    zombie until reaped, so `os.kill(pid, 0)` keeps succeeding long after it
    has stopped listening.
    """
    import signal

    try:
        n = int(pid)
    except ValueError:
        return False
    # Windows has no `SIGKILL`, and `os.kill` there calls TerminateProcess for
    # any signal — one forceful pass is all there is. Escalating SIGTERM →
    # SIGKILL is the POSIX shape only. Caught by Windows CI, green on macOS:
    # the third time this repo has shipped a POSIX assumption that way
    # (lỗi 99, 115).
    buoc = ([(signal.SIGTERM, 5.0)] if sys.platform == "win32"
            else [(signal.SIGTERM, 3.0), (signal.SIGKILL, 2.0)])
    for sig, cho in buoc:
        try:
            os.kill(n, sig)
        except ProcessLookupError:
            pass
        except OSError:
            return False
        het = time.time() + cho
        while time.time() < het:
            if not _responds(url, timeout=1):
                return True
            time.sleep(0.2)
    return not _responds(url, timeout=1)


def _responds(url: str, *, timeout: float = 2) -> bool:
    try:
        with closing(urllib.request.urlopen(url, timeout=timeout)):
            return True
    except urllib.error.HTTPError:
        return True  # server responded, just an error code — still "running"
    except (urllib.error.URLError, OSError, ValueError, socket.timeout):
        return False


def concrete_route(route: str) -> str:
    """Replace dynamic params with sample values: `/note/:id` -> `/note/1`.

    Routes with params cannot be opened directly. The sample value is a
    convention between harness and app: the dev environment's seed data must
    have a record with id `1`, otherwise this is a real failure and the gate
    should report it.
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
    """Open each real route and compare against the contract.

    ``candidate`` is the SHA being verified — evidence stamps which build the
    screen was compared against (ADR-004 R1)."""
    project = Path(project)
    cfg = config or Config.load(project)
    out = VerifyResult()
    # Run-id derived from artifact_root + story for the candidate-bound
    # dev server identity check.  Optional — when unset, the legacy
    # liveness check is used (kept for backward compatibility with
    # external callers and older fixtures).
    run_id = ""
    lease_root = None
    if artifact_root and story_id:
        run_id = f"{Path(artifact_root).name}-{story_id}"
        lease_root = project / ".aisef"

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
        lease_root=lease_root,
        run_id=run_id,
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
                items_rendered=has_items(got.snapshot),
            )
        out.results.append(result)
        if store:
            error = got.error if got else "cannot open route"
            if (got is not None and not got.error and screen.components
                    and not result.matched and not getattr(result, "extra", None)):
                # No matches and no extras = blank page. For routes with params,
                # almost certainly missing the seed record with id `1`.
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
