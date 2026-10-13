"""B03-R3 conf (owner decision, 2026-10-12): the write policy of aisef2/app/confine.py's judgement of a measured session.

The owner's words (docs/v2.1/decisions/B03-R3-conf.md): the developer writes the workspace and the explicitly allowed
execution resources, isolated per session; not every writable mount outside the workspace is a violation, and
devpts/mqueue are not exempt as a kind; a mount is accepted only when it is PROVED to belong to the sandbox, opens no
write path to the host or another session and has a fitting lifecycle; judged by file-system type, mount source, mount
options and namespace — never by name or by a place under /dev/; what cannot be established is refused or reported as
isolation not established.

What each class pins, as a requirement, through `confine._judge` / `confine.measure` (the entry points a run reaches):

* SandboxMade      — a pseudo file system the sandbox made for itself is accepted wherever it lies, /dev/ or not.
* HostBacked       — the same types are refused when the report shows they are the host's (a super block the host's
                     table holds, a host path or device as source, a peer group of the host), and so is anything of a
                     file system a wrapper cannot make; a place under /dev/ exempts nothing.
* NotEstablished   — what cannot be read is "isolation not established", worded so, never a pass and never "writable".
* DeviceNodes      — the execution resources `--dev` places are accepted by identity (a closed list, the character
                     device of that number, under a `--dev` destination of the command line), refused when they are not.
* ReportedData     — what the probe's call hands the judgement: the host's table read before the session (the one
                     that decides; the reading after it is information, test_v21_r3_conf_fu_before), the device
                     nodes read inside, the `--dev` destinations; the reading before lost is not a pass.
* HostTable        — `confine._host_mounts`, the reading of the host's own table.
* DevicesSection   — the probe's `devices` section, run by a real shell against a table of the test's.
* RecordedGuest    — the judgement of the reports a REAL bubblewrap run in the Linux guest produced
                     (docs/v2.1/evidence/sandbox/r3-conf): the same reports judged again, as the guest judged them.

Real vs simulated: SandboxMade/HostBacked/NotEstablished/DeviceNodes take rows built as `confine._mounts` reads the
kernel's lines (the lines in LINES are copied from the guest's /proc/self/mountinfo); ReportedData answers the probe's
call with a transcript; DevicesSection runs the probe's own shell text; RecordedGuest replays what the guest recorded.
Nothing here starts bubblewrap."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from tests.v2 import test_v21_kills3_T05b as T05b  # noqa: E402 — the module: its tests are not collected again
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

WS = pathlib.PurePosixPath("/run/confinement/ws")
#: lines of /proc/self/mountinfo as the Linux guest printed them (Docker Desktop's LinuxKit 7.0.12, bubblewrap 0.12.0)
LINES = {
    "host-proc": "178 176 0:66 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw",
    "host-dev": "179 176 0:69 / /dev rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755",
    "host-pts": "180 179 0:72 / /dev/pts rw,nosuid,noexec,relatime - devpts devpts rw,gid=5,mode=620,ptmxmode=666",
    "host-mqueue": "206 179 0:64 / /dev/mqueue rw,nosuid,nodev,noexec,relatime - mqueue mqueue rw",
    "host-shm": "207 179 0:84 / /dev/shm rw,nosuid,nodev,noexec,relatime - tmpfs shm rw,size=65536k",
    "root": "148 127 0:60 /newroot / rw,nosuid,nodev,relatime - tmpfs tmpfs rw,uid=1000,gid=1000",
    "proc": "158 148 0:61 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw",
    "dev": "159 148 0:62 / /dev rw,nosuid,nodev,relatime - tmpfs tmpfs rw,mode=755,uid=1000,gid=1000",
    "null": "160 159 0:69 /null /dev/null rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755",
    "pts": "166 159 0:63 / /dev/pts rw,nosuid,noexec,relatime - devpts devpts rw,mode=620,ptmxmode=666",
    "tmp": "167 148 0:65 / /tmp rw,nosuid,nodev,relatime - tmpfs tmpfs rw,mode=755,uid=1000,gid=1000",
}
HOST = confine._mounts([LINES[k] for k in ("host-proc", "host-dev", "host-pts", "host-mqueue", "host-shm")])
NOISE = ("cannot establish", "writable outside")


def row(at: str, line: str) -> dict:
    """A sandbox row: the kernel's line `line` read as `_mounts` reads it, placed at `at`."""
    [r] = confine._mounts([line])
    return {**r, "at": at}


def judged(mounts: list[dict], host=HOST, devices=None, roots=("/dev",)) -> list[str]:
    """`_judge` over a measurement that is clean but for `mounts` (the root tmpfs and the workspace besides)."""
    own = [rows.mount("/"), {"at": str(WS), "access": "rw", "fs": "ext4"}]
    rep = {"network": "host", "created_outside_workspace": {}, "setsid_survivors": [], "host_mounts": host,
           "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0"),
                      "no_new_privs": "1",
                      "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                      "routed_interfaces": [], "home_listing": [], "unix_sockets": [], "mounts": own + mounts,
                      "mount_targets": [str(WS), *dict.fromkeys(m["at"] for m in mounts)],
                      "device_roots": list(roots), "devices": dict(devices or {})}}
    tries = {"read_canary": (1, ""), "workspace": (0, "ok"), "read_git_directory": (0, "ref: x"),
             "user_namespace": (1, "unshare failed: No space left on device")}
    return confine._judge(rep, "tok", "", tries, "/nonexistent", WS)


class SandboxMade(unittest.TestCase):
    """Requirement: a writable mount of a file system a wrapper makes for itself is accepted when the report shows it
    is the sandbox's own — its mount source the type's own name, a super block the host's table does not hold, no
    peer group of the host — wherever it lies. Pins confine.PSEUDO, `_owned`."""

    def test_each_pseudo_file_system_made_inside_is_accepted_wherever_it_lies(self):
        for fs in confine.PSEUDO:
            for at in ("/dev/x", "/alt-dev/pts", "/srv/session", "/proc", "/mq"):
                with self.subTest(fs=fs, at=at):
                    self.assertEqual(judged([rows.mount(at, fs)]), [])

    def test_the_guests_own_rows_are_accepted(self):
        """What bubblewrap 0.12.0 made in the guest: a tmpfs root (a bind of the tmpfs's /newroot), proc, /dev, devpts
        at /dev/pts, /tmp — and the device nodes it bound from the container's /dev (judged by identity below)."""
        mine = [row("/", LINES["root"]), row("/proc", LINES["proc"]), row("/dev", LINES["dev"]),
                row("/dev/pts", LINES["pts"]), row("/tmp", LINES["tmp"])]
        self.assertEqual(judged(mine), [])

    def test_a_peer_group_of_its_own_is_not_the_hosts(self):
        host = [*HOST, {"at": "/", "fs": "overlay", "dev": "0:57", "optional": ["shared:5"]}]
        self.assertEqual(judged([rows.mount("/mq", "mqueue", optional="shared:77")], host), [])

    def test_a_read_only_mount_is_not_a_write(self):
        """Only a writable mount is judged by the policy: the system and the client are read-only binds of the host."""
        ro = rows.mount("/usr", "ext4", "ro", dev="0:57", source="/dev/vda1")
        self.assertEqual(judged([ro]), [])


class HostBacked(unittest.TestCase):
    """Requirement: a writable mount the report shows to be the host's is refused as "writable outside the workspace"
    — by its super block (the host's table holds it: a write reaches the host's file system, or another session's
    when it is a bind of the same), by its mount source (a host path or device), by its file system (one a wrapper
    cannot make), by a peer group it shares with the host — and the name of the file system or a place under /dev/
    never exempts it."""

    def refused(self, mounts, host=HOST, **kw) -> str:
        said = judged(mounts, host, **kw)
        self.assertEqual(len(said), 1, said)
        self.assertTrue(said[0].startswith("writable outside the workspace: "), said)
        return said[0]

    def test_the_hosts_devpts_is_refused_by_its_super_block_wherever_it_is_bound(self):
        said = self.refused([row("/host-pts", LINES["host-pts"])])
        self.assertIn("['/host-pts']", said)
        self.assertIn("0:72", said)                     # the super block ...
        self.assertIn("/dev/pts", said)                 # ... and where the host holds it

    def test_the_hosts_mqueue_tmpfs_and_proc_are_refused_the_same_way(self):
        for key, super_block in (("host-mqueue", "0:64"), ("host-dev", "0:69"), ("host-proc", "0:66")):
            with self.subTest(host=key):
                said = self.refused([row("/somewhere", LINES[key])])
                self.assertIn("['/somewhere']", said)
                self.assertIn(super_block, said)

    def test_a_directory_of_a_host_tmpfs_is_the_hosts_tmpfs(self):
        """A bind of a subdirectory of a host tmpfs shows another `root` and the same super block."""
        sub = row("/data", "300 176 0:69 /run/session /data rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755")
        self.assertIn("0:69", self.refused([sub]))

    def test_a_place_under_dev_exempts_nothing(self):
        self.assertEqual(self.refused([rows.mount("/dev/x", "ext4", dev="8:1", source="/dev/vda1")]),
                         "writable outside the workspace: ['/dev/x']")
        self.assertIn("0:84", self.refused([row("/dev/shm", LINES["host-shm"].replace(" shm ", " tmpfs "))]))

    def test_the_name_of_the_file_system_exempts_nothing_a_host_path_or_device_as_source_is_refused(self):
        for fs, source in (("tmpfs", "/srv/export"), ("devpts", "/dev/pts"), ("proc", "/proc"), ("mqueue", "/dev/mqueue"),
                           ("tmpfs", "shm")):
            with self.subTest(fs=fs, source=source):
                said = self.refused([rows.mount("/x", fs, source=source)])
                self.assertIn(repr(source), said)
                self.assertIn(f"not {fs}'s own", said)

    def test_a_file_system_a_wrapper_cannot_make_is_refused_whatever_else_it_shows(self):
        for fs in ("ext4", "overlay", "sysfs", "cgroup2", "devtmpfs", "fuse.sshfs", "9p", "ramfs", "virtiofs"):
            with self.subTest(fs=fs):
                self.assertEqual(self.refused([rows.mount("/x", fs, source=fs)]), "writable outside the workspace: ['/x']")

    def test_a_peer_group_the_host_holds_is_the_hosts_whichever_side_receives(self):
        host = [*HOST, {"at": "/", "fs": "overlay", "dev": "0:57", "optional": ["shared:5", "master:9"]}]
        for tag in ("shared:5", "master:5", "master:9", "propagate_from:5"):
            with self.subTest(tag=tag):
                said = self.refused([rows.mount("/mq", "mqueue", optional=tag)], host)
                self.assertIn("propagates with the host", said)
                self.assertIn(tag, said)

    def test_what_is_refused_is_named_once_each_and_only_what_is_refused(self):
        said = self.refused([rows.mount("/ok"), rows.mount("/a", "ext4"), row("/b", LINES["host-pts"])])
        self.assertTrue(said.startswith("writable outside the workspace: ['/a', '/b']"), said)
        self.assertNotIn("/ok", said)

    def test_a_mount_covered_by_another_at_the_same_path_is_named_once(self):
        said = self.refused([rows.mount("/a", "ext4"), rows.mount("/a", "ext4", dev="8:2")])
        self.assertEqual(said, "writable outside the workspace: ['/a']")


class NotEstablished(unittest.TestCase):
    """Requirement: a writable mount whose ownership cannot be shown — a field not read, the host's table not read —
    is not a pass: the run is refused, and the problem says isolation is NOT ESTABLISHED (nothing was seen written),
    not that something is writable."""

    def unknown(self, mounts, host=HOST, **kw) -> str:
        said = judged(mounts, host, **kw)
        self.assertEqual(len(said), 1, said)
        self.assertTrue(said[0].startswith("cannot establish that a writable mount belongs to the sandbox "), said)
        self.assertIn("isolation not established", said[0])
        self.assertNotIn("writable outside", said[0])
        return said[0]

    def test_an_unread_host_table_establishes_nothing(self):
        for host in (None, []):
            with self.subTest(host=host):
                said = self.unknown([rows.mount("/x")], host)
                self.assertIn("/x: the host's mount table could not be read", said)

    def test_a_row_that_lacks_what_decides_is_not_established(self):
        good = rows.mount("/x")
        for field, value, why in (("source", None, "mount source was not read"), ("dev", "", "super block was not read"),
                                  ("dev", "garbage", "super block was not read"), ("dev", None, "super block was not read"),
                                  ("optional", None, "propagation was not read"),
                                  ("optional", ["master:99"], "its propagation ['master:99'] is not shown to be the "
                                                              "sandbox's own"),
                                  ("optional", ["shared:"], "its propagation ['shared:'] is not shown to be the "
                                                            "sandbox's own"),
                                  ("optional", ["unbindable"], "its propagation ['unbindable'] is not shown to be the "
                                                               "sandbox's own")):
            with self.subTest(field=field, value=value):
                self.assertIn(why, self.unknown([{**good, field: value}]))

    def test_a_missing_key_is_not_established_either(self):
        for field in ("source", "dev", "optional"):
            with self.subTest(field=field):
                bare = {k: v for k, v in rows.mount("/x").items() if k != field}
                self.unknown([bare])

    def test_a_refusal_and_a_mount_not_established_are_two_problems(self):
        said = judged([rows.mount("/a", "ext4"), {**rows.mount("/b"), "source": None}])
        self.assertEqual([p.split(":")[0] for p in said], ["writable outside the workspace",
                                                           "cannot establish that a writable mount belongs to the "
                                                           "sandbox (isolation not established, not a write that was seen)"])
        self.assertIn("/a", said[0])
        self.assertIn("/b: its mount source was not read", said[1])
        self.assertNotIn("/b", said[0])

class DeviceNodes(unittest.TestCase):
    """Requirement: the execution resources `--dev` places are accepted although they are the host's own nodes — an
    explicit, closed list, each by identity: placed under a `--dev` destination of the command line and read inside as
    the character device of that kernel number. A node that is not (a regular file, another device, a name outside the
    list, a place `--dev` did not name) is refused; one the probe did not read is not established."""

    SEEN = {f"/dev/{n}": number for n, number in confine.DEVICES.items()}

    def node(self, at: str, **kw) -> dict:
        return {**row(at, LINES["null"]), **kw}

    def test_the_closed_list_is_the_six_nodes_bubblewrap_binds(self):
        self.assertEqual(confine.DEVICES, {"null": "1:3", "zero": "1:5", "full": "1:7", "random": "1:8", "urandom": "1:9",
                                           "tty": "5:0"})

    def test_each_is_accepted_as_the_character_device_it_must_be(self):
        for name in confine.DEVICES:
            with self.subTest(name=name):
                self.assertEqual(judged([self.node(f"/dev/{name}")], devices=self.SEEN), [])

    def test_the_file_system_holding_the_node_is_not_what_decides(self):
        """On a host whose /dev is a devtmpfs, or a node on another file system: the device number is the identity."""
        for fs, source in (("devtmpfs", "udev"), ("ext4", "/dev/vda1")):
            with self.subTest(fs=fs):
                self.assertEqual(judged([self.node("/dev/null", fs=fs, source=source)], devices=self.SEEN), [])

    def test_another_device_or_a_regular_file_under_the_name_is_refused(self):
        for seen, why in (("1:5", "(read: 1:5)"), ("other", "(read: other)"), ("5:2", "(read: 5:2)")):
            with self.subTest(seen=seen):
                said = judged([self.node("/dev/null")], devices={"/dev/null": seen})
                self.assertEqual(len(said), 1, said)
                self.assertTrue(said[0].startswith("writable outside the workspace: ['/dev/null']"), said)
                self.assertIn("character device 1:3", said[0])
                self.assertIn(why, said[0])

    def test_a_node_outside_the_list_is_judged_as_any_mount(self):
        """A device node bound at /dev/sda or /dev/mem is the container's /dev tmpfs, the host's super block."""
        for name in ("sda", "mem", "kmsg", "ptmx"):
            with self.subTest(name=name):
                said = judged([self.node(f"/dev/{name}")], devices={f"/dev/{name}": "8:0"})
                self.assertEqual(len(said), 1, said)
                self.assertIn(f"['/dev/{name}']", said[0])
                self.assertIn("0:69", said[0])

    def test_a_node_where_no_dev_option_placed_it_is_not_one(self):
        said = judged([self.node("/srv/null")], devices={"/srv/null": "1:3"})
        self.assertEqual(len(said), 1, said)
        self.assertIn("['/srv/null']", said[0])
        self.assertEqual(judged([self.node("/alt/null")], devices={"/alt/null": "1:3"}, roots=("/dev", "/alt")), [])

    def test_a_node_the_probe_did_not_read_is_not_established(self):
        for devices in ({}, {"/dev/null": ""}):
            with self.subTest(devices=devices):
                said = judged([self.node("/dev/null")], devices=devices)
                self.assertEqual(len(said), 1, said)
                self.assertTrue(said[0].startswith("cannot establish that a writable mount"), said)
                self.assertIn("/dev/null: it is not shown to be the character device 1:3", said[0])


def transcript_host(*readings):
    """The host's table as the readings the measurement makes of it (before the session, after it): a callable for
    `rows.host_table`; a reading is a list of rows, or None for one that failed."""
    left = list(readings)
    return lambda: left.pop(0) if len(left) > 1 else left[0]


class ReportedData(unittest.TestCase):
    """Requirement: a measurement hands the judgement what it needs, and a reading it lost is not a pass — the host's
    table read before the session (a super block it holds is the host's; the reading after the session decides
    nothing: tests/v2/test_v21_r3_conf_fu_before.py), the device nodes read inside, the `--dev` destinations of the
    command line; the report records them. Through `confine.measure`, the probe's one call answered with a transcript
    of a correctly confined session (T05b's)."""

    def measure(self, host=None, **script):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        return T05b.measure(pathlib.Path(os.path.realpath(t.name)), "host", host, **script)

    def test_a_correct_session_is_accepted_and_the_report_holds_what_decided(self):
        seen = self.measure()
        self.assertEqual(seen.rep["problems"], [])
        self.assertEqual(seen.rep["host_mounts"], rows.HOST)
        inside = seen.rep["inside"]
        self.assertEqual(inside["device_roots"], ["/dev"])
        self.assertEqual(inside["devices"], {f"/dev/{n}": number for n, number in confine.DEVICES.items()})

    def test_the_host_is_judged_by_the_reading_before_the_session_the_one_after_decides_nothing(self):
        """A super block the host held when the session started is the host's: the sandbox's /tmp (whose number the
        transcript fixes) is refused when the host's table holds it in the reading before the session, whatever the
        reading after it holds, and accepted when only the reading after it does (the number the session's own mount
        freed, taken by a host mount made since — B03-R3 FU-CONF); the report keeps the reading before as
        `host_mounts` and the rows that appeared as `host_mounts_appeared`."""
        tmp = next(m for m in self.measure().rep["inside"]["mounts"] if m["at"] == "/tmp")
        held = {"at": "/mnt/other", "fs": "tmpfs", "dev": tmp["dev"], "optional": []}
        for first, second in ((rows.HOST, rows.HOST), ([*rows.HOST, held], rows.HOST), (rows.HOST, [*rows.HOST, held]),
                              ([*rows.HOST, held], [*rows.HOST, held])):
            with self.subTest(before=len(first), after=len(second)):
                seen = self.measure(transcript_host(first, second))
                shown = [p for p in seen.rep["problems"] if p.startswith("writable outside")]
                self.assertEqual(seen.rep["host_mounts"], first)
                self.assertEqual(seen.rep["host_mounts_appeared"], [r for r in second if r not in first])
                if held in first:
                    self.assertEqual(len(shown), 1, seen.rep["problems"])
                    self.assertIn("['/tmp']", shown[0])
                    self.assertIn("/mnt/other", shown[0])
                else:
                    self.assertEqual(seen.rep["problems"], [])

    def test_a_reading_before_that_failed_leaves_no_mount_shown_to_be_the_sandboxs(self):
        """(A reading AFTER that failed refuses nothing: test_v21_r3_conf_fu_before.ReadingLost.)"""
        for reads in ((None, rows.HOST), (None, None)):
            with self.subTest(reads=reads):
                seen = self.measure(transcript_host(*reads))
                self.assertIsNone(seen.rep["host_mounts"])
                said = [p for p in seen.rep["problems"] if p.startswith("cannot establish")]
                self.assertEqual(len(said), 1, seen.rep["problems"])
                self.assertIn("the host's mount table could not be read", said[0])
                self.assertEqual([p for p in seen.rep["problems"] if "writable outside" in p], [])

    def test_a_device_node_the_probe_did_not_read_refuses_the_run_naming_it(self):
        """T05b's session has the node `--dev` places that the transcript's mountinfo lists: /dev/null."""
        [said] = self.measure(devices=[]).rep["problems"]
        self.assertTrue(said.startswith("cannot establish that a writable mount belongs to the sandbox"), said)
        self.assertIn("/dev/null: it is not shown to be the character device 1:3 (read: nothing)", said)

    def test_a_node_the_probe_found_not_to_be_a_character_device_is_refused(self):
        [said] = self.measure(devices=["other - /dev/null"]).rep["problems"]
        self.assertTrue(said.startswith("writable outside the workspace: ['/dev/null']"), said)
        self.assertIn("(read: other)", said)

    def test_a_node_of_another_number_is_refused(self):
        [said] = self.measure(devices=["char 1:5 /dev/null"]).rep["problems"]
        self.assertTrue(said.startswith("writable outside the workspace: ['/dev/null']"), said)
        self.assertIn("(read: 1:5)", said)


class HostTable(unittest.TestCase):
    """Requirement: the host's table is the controller's own /proc/self/mountinfo, read whole — what a judgement
    against it needs of each mount (where, file system, super block, propagation) — or None, never a part of it."""

    def read(self, raw: bytes | None = None, error: OSError | None = None):
        """(`confine._host_mounts()`, what it asked of `Path.read_text`) with the file's bytes `raw` decoded as the real
        `read_text` decodes them: with the encoding and error handler it is given (a mount point that is not UTF-8
        must not make the table unreadable); `error` is what reading it raises."""
        asked = []

        def read_text(path, encoding=None, errors=None, **k):
            asked.append(path)
            if error is not None:
                raise error
            return raw.decode(encoding, errors or "strict")
        with mock.patch.object(confine.pathlib.Path, "read_text", read_text):
            return confine._host_mounts(), asked

    def test_the_guests_table_is_read_into_what_a_judgement_needs(self):
        table = "\n".join([LINES["host-proc"], LINES["host-pts"],
                           r"300 176 0:46 /a /w\040s rw,nosuid shared:7 master:3 - virtiofs virtiofs2 rw"]).encode()
        got, asked = self.read(table)
        self.assertEqual(got, [{"at": "/proc", "fs": "proc", "dev": "0:66", "optional": []},
                               {"at": "/dev/pts", "fs": "devpts", "dev": "0:72", "optional": []},
                               {"at": "/w s", "fs": "virtiofs", "dev": "0:46", "optional": ["shared:7", "master:3"]}])
        self.assertEqual(len(asked), 1)

    def test_a_mount_point_that_is_not_utf8_is_read_not_a_reason_to_refuse_every_run(self):
        raw = LINES["host-proc"].encode() + b"\n300 176 0:46 / /mnt/\xff\xfe rw - tmpfs tmpfs rw\n"
        got, _ = self.read(raw)
        self.assertEqual([m["dev"] for m in got], ["0:66", "0:46"])
        self.assertEqual(got[1]["at"], "/mnt/\ufffd\ufffd")

    def test_it_is_the_controllers_own_table(self):
        _, asked = self.read(b"")
        self.assertEqual([pathlib.PurePath(p) for p in asked], [pathlib.PurePath("/proc/self/mountinfo")])

    def test_one_that_cannot_be_read_whole_is_none(self):
        for text, error in ((None, FileNotFoundError(2, "No such file")), (None, PermissionError(13, "denied")), ("", None),
                            (LINES["host-proc"] + "\nnot a mountinfo line\n", None),
                            (LINES["host-proc"] + "\n\n" + LINES["host-pts"], None)):
            with self.subTest(text=text, error=error):
                self.assertIsNone(self.read(None if text is None else text.encode(), error)[0])


@unittest.skipUnless(os.name == "posix", "the probe is a POSIX shell script")
class DevicesSection(unittest.TestCase):
    """Requirement: the probe reads, inside, each mount point named like one of the nodes `--dev` places: `char <major:
    minor> <path>` when it is a character device, `other - <path>` when it is not (a regular file, a directory),
    nothing for another name. The probe's own text, run by a real shell against a mount table of the test's (the
    probe's /proc/self/mountinfo replaced by that file)."""

    def run_probe(self, lines: list[str]) -> list[str]:
        block = confine.PROBE.split("m section devices\n")[1].split("m section route")[0]
        with tempfile.TemporaryDirectory() as t:
            table = pathlib.Path(t) / "mountinfo"
            table.write_text("\n".join(lines) + "\n", encoding="utf-8")
            p = subprocess.run(["/bin/sh", "-c", block.replace("/proc/self/mountinfo", str(table))], capture_output=True,
                               text=True, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}, timeout=30)
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        return p.stdout.splitlines()

    def test_a_character_device_a_regular_file_a_directory_and_a_name_that_is_not_a_node(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(os.path.realpath(t))
            (d / "a").mkdir()
            (d / "a" / "null").symlink_to("/dev/null")        # a link to a character device: the device (stat -L)
            (d / "b").mkdir()
            (d / "b" / "zero").write_text("not a device\n")
            (d / "c" / "full").mkdir(parents=True)
            (d / "d").mkdir()
            (d / "d" / "passwd").write_text("x\n")
            lines = [f"1 0 0:5 / {d}/{rest} rw - tmpfs tmpfs rw" for rest in ("a/null", "b/zero", "c/full", "d/passwd")]
            got = self.run_probe(lines)
        self.assertEqual(len(got), 3, got)
        self.assertTrue(got[0].startswith("char "), got)
        self.assertTrue(got[0].endswith(f" {d}/a/null"), got)
        if sys.platform.startswith("linux"):
            self.assertEqual(got[0], f"char 1:3 {d}/a/null")      # stat -c %t:%T: the kernel's numbers
        self.assertEqual(got[1:], [f"other - {d}/b/zero", f"other - {d}/c/full"])

    def test_every_name_of_the_list_is_looked_at_and_no_other(self):
        lines = [f"1 0 0:5 / /nonexistent/{n} rw - tmpfs tmpfs rw" for n in (*confine.DEVICES, "sda", "nullx", "xnull")]
        self.assertEqual(self.run_probe(lines), [f"other - /nonexistent/{n}" for n in confine.DEVICES])


class RecordedGuest(unittest.TestCase):
    """Requirement: the reports a REAL bubblewrap run produced in the Linux guest (validation/v21/sandbox/
    r3_conf_guest.py scenarios; docs/v2.1/evidence/sandbox/r3-conf) are judged now as they were then, and each says
    what the policy is for: a sandbox-made devpts (bubblewrap's second `--dev`) or mqueue is accepted, the container's
    own devpts / mqueue / tmpfs / shm / proc bound or shared in, a writable ext4 file under /dev/, a regular file over
    /dev/null, another device over it and a node outside the list are each refused for what they are."""

    EVIDENCE = ROOT / "docs" / "v2.1" / "evidence" / "sandbox" / "r3-conf"
    #: scenario -> the mount points of the sandbox the problems name as writable outside the workspace
    REFUSED = {"baseline": [], "alt-dev-sandbox-devpts": [], "mqueue-sandbox": [],
               "host-devpts-at-other-path": ["/host-pts"],
               "host-mqueue-bound": ["/hostmq"],
               "host-dev-bound": ["/host-dev", "/host-dev/pts", "/host-dev/mqueue", "/host-dev/shm"],
               "host-shm-over-dev-shm": ["/dev/shm"], "ext4-file-at-dev-x": ["/dev/x"],
               "regular-file-at-dev-null": ["/dev/null"], "zero-at-dev-null": ["/dev/null"],
               "ptmx-at-dev-ptmx2": ["/dev/ptmx2"], "shared-pid-namespace": ["/proc"]}

    def records(self) -> dict:
        found = {}
        for path in sorted(self.EVIDENCE.glob("scenarios-*.json")):
            found[path.name] = json.loads(path.read_text(encoding="utf-8"))["record"]
        self.assertTrue(found, f"no recorded guest scenarios under {self.EVIDENCE}")
        return found

    def judge(self, rec: dict) -> list[str]:
        rep = rec["report"]
        tries = {k: (v["exit"], v["output"]) for k, v in rep["tried"].items()}
        return confine._judge(rep, "tok", "", tries, rec["home"], pathlib.PurePosixPath(rec["workspace"]))

    def test_every_recorded_report_is_judged_again_as_it_was(self):
        for name, scenarios in self.records().items():
            self.assertEqual(sorted(scenarios), sorted(self.REFUSED))
            for scenario, rec in scenarios.items():
                with self.subTest(record=name, scenario=scenario):
                    self.assertEqual(self.judge(rec), rec["report"]["problems"])

    def test_what_each_scenario_shows(self):
        for name, scenarios in self.records().items():
            for scenario, at in self.REFUSED.items():
                with self.subTest(record=name, scenario=scenario):
                    problems = self.judge(scenarios[scenario])
                    writable = [p for p in problems if p.startswith("writable outside the workspace")]
                    unknown = [p for p in problems if p.startswith("cannot establish")]
                    self.assertEqual(unknown, [])
                    if not at:
                        self.assertEqual(writable, [])
                        continue
                    self.assertEqual(len(writable), 1, problems)
                    named = writable[0].split("(", 1)[0]
                    for mount in at:
                        self.assertIn(f"'{mount}'", named)
                    self.assertEqual(named.count("'") // 2, len(at), named)

    def test_a_proc_of_the_hosts_pid_namespace_is_refused_twice_over(self):
        """Without `--unshare-pid` bubblewrap's /proc is the container's: the pid namespace is not the session's own
        (the judgement's namespace check) AND the proc mount is the host's super block (the write policy)."""
        for name, scenarios in self.records().items():
            with self.subTest(record=name):
                problems = self.judge(scenarios["shared-pid-namespace"])
                self.assertIn("the pid namespace is not the session's own (shared)", problems)
                self.assertTrue(any(p.startswith("writable outside the workspace: ['/proc']") for p in problems), problems)

    def test_a_session_of_the_guest_holds_only_what_the_policy_accepts(self):
        """Every writable mount of the baseline, by the file system and what showed it the sandbox's: the workspace and
        the device nodes are the two host-backed ones; all else is a pseudo file system of its own super block."""
        for name, scenarios in self.records().items():
            rep = scenarios["baseline"]["report"]
            held = {m["dev"] for m in rep["host_mounts"]}
            with self.subTest(record=name):
                for m in rep["inside"]["mounts"]:
                    if m["access"] != "rw" or m["at"] == scenarios["baseline"]["workspace"]:
                        continue
                    if m["at"].startswith("/dev/") and m["at"][5:] in confine.DEVICES:
                        self.assertIn(m["dev"], held)       # the container's own nodes: host-backed, allowed by identity
                    else:
                        self.assertIn(m["fs"], confine.PSEUDO)
                        self.assertEqual(m["source"], m["fs"])
                        self.assertNotIn(m["dev"], held)

    def test_in_a_tree_with_peer_groups_what_the_sandbox_made_propagates_nowhere(self):
        """The shared-tree record (the container's mount tree made `rshared`, as a systemd host's is): the host's table
        holds peer groups; what the sandbox inherited is a slave of them (`master:N`, the device nodes among it) and
        what it made itself has no propagation field — the premise of the policy's "no peer group of the host"."""
        rep = json.loads((self.EVIDENCE / "scenarios-X1-shared-tree.json").read_text(encoding="utf-8"))["record"][
            "baseline"]["report"]
        groups = {t.split(":")[1] for h in rep["host_mounts"] for t in h["optional"] if t.startswith("shared:")}
        self.assertTrue(groups)
        made = {"/", "/proc", "/dev", "/dev/pts", "/tmp", "/aisef-home"}
        seen = {m["at"] for m in rep["inside"]["mounts"] if m["at"] in made}
        self.assertEqual(seen, made)
        for m in rep["inside"]["mounts"]:
            with self.subTest(at=m["at"]):
                if m["at"] in made:
                    self.assertEqual(m["optional"], [])
                for tag in m["optional"]:
                    self.assertEqual(tag.split(":")[0], "master")
                    self.assertIn(tag.split(":")[1], groups)
        self.assertEqual(rep["problems"], [])

    def test_no_mount_of_a_session_outlives_it_in_the_hosts_table(self):
        for name, scenarios in self.records().items():
            for scenario, rec in scenarios.items():
                with self.subTest(record=name, scenario=scenario):
                    self.assertTrue(rec["table_unchanged"])
                    self.assertEqual(rec["report"]["setsid_survivors"] == [], scenario != "shared-pid-namespace")


if __name__ == "__main__":
    unittest.main()
