"""Server identity lease — port ownership and ready-time identity check."""

from __future__ import annotations

import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.harness.server_identity import (  # noqa: E402
    ServerLease, write_lease, read_lease, remove_lease,
    ready_with_identity, acquire_port_lease, release_port_lease,
    port_owned_by_other_run,
)


class _IdentityHandler(BaseHTTPRequestHandler):
    body = b""
    def do_GET(self):  # noqa: N802
        if self.path == "/_aisef/identity":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(self.body)))
            self.end_headers()
            self.wfile.write(self.body)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
    def log_message(self, *args, **kwargs):
        return


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        try:
            s.close()
        except OSError:
            pass


class TestLease(unittest.TestCase):
    def test_write_read_round_trip(self):
        with _tempdir() as root:
            lease = ServerLease(run_id="r1", story_id="S1",
                                candidate="abc", base_url="http://x")
            write_lease(root, lease)
            got = read_lease(root, "r1")
            self.assertIsNotNone(got)
            self.assertEqual(got.candidate, "abc")
            remove_lease(root, "r1")
            self.assertIsNone(read_lease(root, "r1"))

    def test_corrupt_lease_returns_none(self):
        with _tempdir() as root:
            (root / ".aisef" / "lease").mkdir(parents=True)
            (root / ".aisef" / "lease" / "r1.json").write_text(
                "not json", encoding="utf-8")
            self.assertIsNone(read_lease(root, "r1"))


class TestReadyIdentity(unittest.TestCase):
    def test_ready_with_matching_id(self):
        port = _find_free_port()
        handler = type("H", (_IdentityHandler,), {"body": b"r1"})
        server = HTTPServer(("127.0.0.1", port), handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            self.assertTrue(ready_with_identity(
                f"http://127.0.0.1:{port}", "r1", attempts=3))
        finally:
            server.shutdown()
            server.server_close()

    def test_ready_with_wrong_id_rejected(self):
        port = _find_free_port()
        handler = type("H", (_IdentityHandler,), {"body": b"someone-else"})
        server = HTTPServer(("127.0.0.1", port), handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            self.assertFalse(ready_with_identity(
                f"http://127.0.0.1:{port}", "r1", attempts=2))
        finally:
            server.shutdown()
            server.server_close()


class TestPortLease(unittest.TestCase):
    def test_acquire_release(self):
        with _tempdir() as root:
            fd = acquire_port_lease(root, "r1", "http://127.0.0.1:55555")
            self.assertIsNotNone(fd)
            lease_dir = root / ".aisef" / "lease"
            self.assertTrue((lease_dir / "port-r1.lock").exists())
            self.assertTrue((lease_dir / "port-r1.lock.owner").exists())
            # Release removes both files; fd is closed too.
            release_port_lease(root, "r1", fd)
            self.assertFalse((lease_dir / "port-r1.lock").exists())
            self.assertFalse((lease_dir / "port-r1.lock.owner").exists())

    def test_other_run_owns_port(self):
        with _tempdir() as root:
            url = "http://127.0.0.1:1"  # never bound
            fd = acquire_port_lease(root, "r-other", url)
            self.assertIsNotNone(fd)
            try:
                self.assertTrue(port_owned_by_other_run(root, "r-mine", url))
            finally:
                release_port_lease(root, "r-other", fd)


# ── helpers ─────────────────────────────────────────────────────

from contextlib import contextmanager
from tempfile import TemporaryDirectory


@contextmanager
def _tempdir():
    with TemporaryDirectory() as d:
        yield Path(d)


if __name__ == "__main__":
    unittest.main()
