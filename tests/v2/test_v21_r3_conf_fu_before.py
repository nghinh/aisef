"""B03-R3 conf, follow-up (FU-CONF): "is this super block one the host already had" is decided from the host's mount
table read BEFORE the session, never from the one read after it.

The owner's words (docs/v2.1/decisions/B03-R3-conf.md §1, W3): a writable mount is accepted only when it is proved to
belong to the sandbox and opens no write path to the host. A super block a session creates is one no live host mount
holds; the numbers are anonymous and allocated lowest-free, so when the session ends the ones it held are free again,
and an unrelated host mount made in the milliseconds before the reading AFTER the session can take one of them. Such a
row cannot tell a leak from a reused number, so it decides nothing: it is recorded (`host_mounts_appeared`) and no more.

What each class pins, through `confine.measure` (the entry point a run reaches; the probe's one call is answered with
T05b's transcript of a correctly confined session, the host's table by the test) — simulated, nothing starts
bubblewrap:

* ReadingBefore — what the reading before the session holds is the host's (refused, with the cause); what only the
                  reading after it holds is not (accepted); a rw bind of a host super block stays refused whatever the
                  reading after says, or fails to say.
* ReadingLost   — an unreadable reading before establishes nothing; an unreadable reading after refuses nothing.
* Appeared      — the report: `host_mounts` is the reading before, `host_mounts_appeared` the rows the reading after
                  has and it lacks, in the shape `_host_mounts` gives them, None when it cannot be told.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from tests.v2 import test_v21_kills3_T05b as T05b  # noqa: E402 — the module: its tests are not collected again
from tests.v2 import test_v21_r3_conf_policy as policy  # noqa: E402 — likewise
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

#: the host's own mqueue, as a host table row; a sandbox row of this super block is the host's, bound in
HOST_MQUEUE = {"at": "/dev/mqueue", "fs": "mqueue", "dev": "0:64", "optional": []}
BOUND_MQUEUE = "90 30 0:64 / /hostmq rw,relatime - mqueue mqueue rw"


class Measured(unittest.TestCase):
    """The session of T05b measured with the host's table read as `readings` (before the session, after it)."""

    def measure(self, *readings, extra_mount: str | None = None):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        tmp = pathlib.Path(os.path.realpath(t.name))
        host = policy.transcript_host(*readings)
        if extra_mount is None:
            return T05b.measure(tmp, "host", host).rep
        real = T05b.mountinfo       # a row the sandbox has besides the wrapper's own: a host mount bound in
        with mock.patch.object(T05b, "mountinfo", lambda argv: [*real(argv), extra_mount]):
            return T05b.measure(tmp, "host", host).rep

    def sandbox_tmp(self) -> dict:
        """The row the session's own /tmp has in the transcript (its super block is the transcript's number)."""
        return next(m for m in self.measure(rows.HOST, rows.HOST)["inside"]["mounts"] if m["at"] == "/tmp")

    def held_by_a_host_mount(self, dev: str, at: str = "/mnt/other") -> dict:
        return {"at": at, "fs": "tmpfs", "dev": dev, "optional": []}

    def refusals(self, rep: dict) -> list[str]:
        return [p for p in rep["problems"] if p.startswith("writable outside the workspace")]


class ReadingBefore(Measured):
    """Requirement: a writable pseudo mount is "the host's" when the host's table READ BEFORE THE SESSION holds its
    super block, and only then. A row only the reading after the session holds is a mount that appeared while the
    session ran or ended — a reused number as likely as a leak — and refuses nothing."""

    def test_a_super_block_only_the_reading_after_the_session_holds_is_not_the_hosts(self):
        """The hazard: the number the session's /tmp had is taken, at another path, by a host mount made between its
        end and the second reading. A correct session is accepted; the report records the row as having appeared."""
        held = self.held_by_a_host_mount(self.sandbox_tmp()["dev"])
        rep = self.measure(rows.HOST, [*rows.HOST, held])
        self.assertEqual(rep["problems"], [])
        self.assertEqual(rep["host_mounts"], rows.HOST)
        self.assertEqual(rep["host_mounts_appeared"], [held])

    def test_a_super_block_the_reading_before_the_session_holds_is_the_hosts(self):
        """The control: the same row in the reading before the session — a host mount that was there — refuses the
        session's /tmp as the host's, naming the mount point of the host that holds it, whatever the reading after
        holds (the mount still there, or gone)."""
        held = self.held_by_a_host_mount(self.sandbox_tmp()["dev"])
        for after in ([*rows.HOST, held], rows.HOST):
            with self.subTest(after_holds_it=held in after):
                rep = self.measure([*rows.HOST, held], after)
                [said] = self.refusals(rep)
                self.assertIn("['/tmp']", said)
                self.assertIn("is the host's (mounted there at /mnt/other)", said)
                self.assertEqual(rep["host_mounts"], [*rows.HOST, held])
                self.assertEqual(rep["host_mounts_appeared"], [])       # nothing appeared; one may have gone

    def test_a_writable_bind_of_a_super_block_the_host_held_is_refused_whatever_the_reading_after_says(self):
        """The host's own mqueue bound in at /hostmq (the container's, as `--dev-bind /dev/mqueue /hostmq` gives it):
        refused for its super block with the reading after holding it, lacking it, or failing."""
        before = [*rows.HOST, HOST_MQUEUE]
        for what, after in (("holds it", before), ("lacks it", rows.HOST), ("unreadable", None)):
            with self.subTest(after=what):
                rep = self.measure(before, after, extra_mount=BOUND_MQUEUE)
                [said] = self.refusals(rep)
                self.assertIn("['/hostmq']", said)
                self.assertIn("its super block 0:64 is the host's (mounted there at /dev/mqueue)", said)

    def test_the_same_bind_is_not_refused_for_a_super_block_the_host_never_held_before_the_session(self):
        """What the reading before decides, seen from the other side: the sandbox's own mqueue at /hostmq, whose
        number the host's table (before) does not hold, is the sandbox's — not refused for being writable."""
        rep = self.measure(rows.HOST, rows.HOST, extra_mount=BOUND_MQUEUE)
        self.assertEqual(self.refusals(rep), [])


class ReadingLost(Measured):
    """Requirement: without the reading before the session no mount is shown to be the sandbox's own (not
    established: the run is refused, worded so, never "writable"); without the reading after it nothing is lost —
    only the record of what appeared."""

    def test_an_unreadable_reading_before_establishes_nothing(self):
        for reads in ((None, rows.HOST), (None, None)):
            with self.subTest(reads=reads):
                rep = self.measure(*reads)
                self.assertIsNone(rep["host_mounts"])
                self.assertIsNone(rep["host_mounts_appeared"])
                [said] = [p for p in rep["problems"] if p.startswith("cannot establish")]
                self.assertIn("the host's mount table could not be read", said)
                self.assertEqual(self.refusals(rep), [])

    def test_an_unreadable_reading_after_refuses_nothing(self):
        rep = self.measure(rows.HOST, None)
        self.assertEqual(rep["problems"], [])
        self.assertEqual(rep["host_mounts"], rows.HOST)
        self.assertIsNone(rep["host_mounts_appeared"])


class Appeared(Measured):
    """Requirement: `host_mounts` is the host's table as it was before the session — each row `{at, fs, dev,
    optional}` — and `host_mounts_appeared` the rows the reading after it has that the one before lacks, in the
    order they were read: information for the record, decided on by nobody."""

    NEW = [{"at": "/run/user/7", "fs": "tmpfs", "dev": "0:88", "optional": ["shared:3"]},
           {"at": "/mnt/usb", "fs": "vfat", "dev": "8:17", "optional": []}]

    def test_the_rows_that_appeared_are_those_after_that_were_not_before_in_the_order_read(self):
        gone = {"at": "/mnt/gone", "fs": "ext4", "dev": "8:33", "optional": []}
        rep = self.measure([*rows.HOST, gone], [self.NEW[0], *rows.HOST, self.NEW[1]])
        self.assertEqual(rep["problems"], [])
        self.assertEqual(rep["host_mounts"], [*rows.HOST, gone])        # the reading before, whole, nothing of the after
        self.assertEqual(rep["host_mounts_appeared"], self.NEW)         # not `gone`: only what appeared

    def test_nothing_appeared_is_an_empty_list_not_none(self):
        rep = self.measure(rows.HOST, rows.HOST)
        self.assertEqual(rep["host_mounts_appeared"], [])

    def test_the_report_holds_the_real_readings_of_the_controllers_own_table(self):
        """Through the real `_host_mounts`: the controller's /proc/self/mountinfo read before the session and again
        after it (a table of the test's, the second with a mount more), the rows shaped as `_host_mounts` shapes them."""
        first = [policy.LINES["host-proc"], policy.LINES["host-pts"]]
        second = [*first, r"300 176 0:46 /a /w\040s rw,nosuid shared:7 - tmpfs tmpfs rw"]
        texts = ["\n".join(first) + "\n", "\n".join(second) + "\n"]
        real_read_text, real_host_mounts = pathlib.Path.read_text, confine._host_mounts

        def read_text(path, *args, **kwargs):
            if pathlib.PurePath(path) == pathlib.PurePath("/proc/self/mountinfo"):
                return texts.pop(0)
            return real_read_text(path, *args, **kwargs)
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        with mock.patch.object(pathlib.Path, "read_text", read_text):
            rep = T05b.measure(pathlib.Path(os.path.realpath(t.name)), "host", lambda: real_host_mounts()).rep
        self.assertEqual(texts, [])         # two readings, no more
        self.assertEqual(rep["host_mounts"], [{"at": "/proc", "fs": "proc", "dev": "0:66", "optional": []},
                                              {"at": "/dev/pts", "fs": "devpts", "dev": "0:72", "optional": []}])
        self.assertEqual(rep["host_mounts_appeared"],
                         [{"at": "/w s", "fs": "tmpfs", "dev": "0:46", "optional": ["shared:7"]}])


if __name__ == "__main__":
    unittest.main()
