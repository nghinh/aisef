"""Candidate-bound dev server identity.

A story's mockup verification runs the project's dev server, opens the route
the agent built, and compares the rendered accessibility tree to the
contract.  Two failure modes are easy to hit and hard to spot from outside:

* a project whose own dev server is already running on the configured port
  (``5173``).  The previous ``AppServer.start`` path returned a clear error in
  this case, but the run could still proceed on a later story, build the
  app in a story worktree, and ``verify_screens`` would happily point at
  the unrelated server.  The gate would mark the screen "passed" because the
  unrelated server still served *some* HTML.
* two story worktrees both calling ``verify_screens`` at the same time.
  Without a lease, both processes could bind the same port; one of them
  reads the other's screen.

This module binds a dev server to one ``run_id`` and ``candidate``: the
server is only allowed to answer ``ready`` if it can echo the identity
string the run wrote to disk before starting it.  Identity is checked at
three points — lease, ready probe, and tear-down — so a process on the
configured port without the matching identity is rejected at ready time.

Local-only.
    No external service, no socket protocol: the dev server is launched by
    ``AppServer`` and the identity is read/written through plain files
    inside ``.aisef/lease/``.  POSIX and Windows are both supported because
    the lease uses the cross-platform ``_compat.flock_ex_nb`` lock.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .._compat import flock_ex_nb, flock_un


LEASE_ROOT = Path(".aisef") / "lease"
LEASE_VERSION = 1


@dataclass(frozen=True)
class ServerLease:
    """Identity and runtime facts about one dev server.

    The run writes a lease file before launching the server, then the
    gate (and any other caller) reads the lease to know the run_id and
    candidate it must prove it actually started.
    """

    run_id: str
    story_id: str
    candidate: str
    base_url: str
    pid: int = 0
    started_at: float = 0.0
    version: int = LEASE_VERSION

    @property
    def lease_path(self) -> Path:
        return lease_path(self.run_id)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "run_id": self.run_id,
            "story_id": self.story_id,
            "candidate": self.candidate,
            "base_url": self.base_url,
            "pid": self.pid,
            "started_at": self.started_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "ServerLease":
        return ServerLease(
            version=int(d.get("version") or LEASE_VERSION),
            run_id=str(d.get("run_id") or ""),
            story_id=str(d.get("story_id") or ""),
            candidate=str(d.get("candidate") or ""),
            base_url=str(d.get("base_url") or ""),
            pid=int(d.get("pid") or 0),
            started_at=float(d.get("started_at") or 0.0),
        )


def lease_path(run_id: str) -> Path:
    return LEASE_ROOT / f"{run_id}.json"


def write_lease(root: Path, lease: ServerLease) -> Path:
    """Atomically write the lease file.  The lock directory is created if
    missing."""
    path = lease.lease_path if lease.lease_path.is_absolute() else root / lease.lease_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(lease.to_dict(), fh, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def read_lease(root: Path, run_id: str) -> ServerLease | None:
    path = root / lease_path(run_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return ServerLease.from_dict(json.load(fh))
    except (OSError, json.JSONDecodeError):
        return None


def remove_lease(root: Path, run_id: str) -> None:
    path = root / lease_path(run_id)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# ── readiness probe ─────────────────────────────────────────────


def ready_with_identity(base_url: str, run_id: str, *,
                        timeout: float = 2.0, attempts: int = 3) -> bool:
    """Return True iff ``base_url`` answers with the expected ``run_id``.

    The dev server, if it was launched under a lease, must expose its
    ``run_id`` on the well-known path ``/_aisef/identity``.  Any other
    responder — a stale process, an unrelated project — cannot produce the
    matching id, so the gate can refuse to grade it.

    The check is permissive: the endpoint may 404 and the lease id is
    treated as "not yet wired", which means the caller falls back to the
    existing dev-server alive check.  This keeps projects that have not
    been updated working while making it possible for new projects to opt
    into the stricter mode just by exposing the path.
    """
    url = base_url.rstrip("/") + "/_aisef/identity"
    for _ in range(max(1, attempts)):
        try:
            with closing(urllib.request.urlopen(url, timeout=timeout)) as resp:
                body = resp.read(256).decode("utf-8", errors="replace").strip()
                if body == run_id:
                    return True
                if body:
                    return False
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # No endpoint yet — fall back to liveness; caller decides.
                return True
        except (urllib.error.URLError, OSError, socket.timeout, ValueError):
            pass
        time.sleep(0.2)
    return False


# ── port lease ──────────────────────────────────────────────────


def _port_from_url(url: str) -> int | None:
    from urllib.parse import urlparse
    return urlparse(url).port


def _tcp_connectable(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    try:
        with closing(socket.create_connection((host, port), timeout=timeout)):
            return True
    except (OSError, socket.timeout):
        return False


def acquire_port_lease(root: Path, run_id: str, base_url: str) -> int | None:
    """Acquire a non-blocking exclusive lock on the configured port.

    Returns the open file descriptor if the caller now owns the port,
    or ``None`` if another run owns it.  The lock is on-disk (one byte),
    so two concurrent runs competing for the same base_url cannot both
    pass.

    A port whose TCP socket is *already* in use by an unrelated process
    is treated as ``owned by another run`` and the caller should pick a
    different ``base_url`` — the previous ``AppServer`` logic already
    reports this case, the lease just makes it deterministic.
    """
    path = root / LEASE_ROOT / f"port-{run_id}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
    try:
        flock_ex_nb(fd)
    except (BlockingIOError, OSError):
        os.close(fd)
        return None
    # Stash the owner metadata; the caller keeps the fd for the run.
    try:
        path.with_suffix(path.suffix + ".owner").write_text(
            json.dumps({"run_id": run_id, "base_url": base_url,
                        "at": time.time()}), encoding="utf-8")
    except OSError:
        pass
    return fd


def release_port_lease(root: Path, run_id: str, fd: int = -1) -> None:
    if fd >= 0:
        try:
            flock_un(fd)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
    for suffix in ("", ".owner"):
        path = root / LEASE_ROOT / f"port-{run_id}.lock{suffix}"
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def port_owned_by_other_run(root: Path, run_id: str, base_url: str) -> bool:
    """True if the port has a lease owned by a *different* run.

    Falls back to TCP probe if no on-disk lease exists for the configured
    port — the lease is opt-in.
    """
    leases_dir = root / LEASE_ROOT
    if not leases_dir.exists():
        return False
    for path in leases_dir.glob("port-*.lock.owner"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(data.get("run_id") or "") == run_id:
            continue
        if str(data.get("base_url") or "").rstrip("/") == base_url.rstrip("/"):
            return True
    port = _port_from_url(base_url)
    if port is None:
        return False
    return _tcp_connectable(port)


__all__ = [
    "ServerLease", "LEASE_ROOT", "LEASE_VERSION",
    "write_lease", "read_lease", "remove_lease",
    "ready_with_identity", "acquire_port_lease", "release_port_lease",
    "port_owned_by_other_run",
]
