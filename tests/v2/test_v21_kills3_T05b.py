"""V2.1 mutation survivors of aisef2/app/confine.py::_probe, batch T05b: what a measurement of a Linux session RECORDS
(RUN.json.confinement; SANDBOX-LINUX §4-§7, evidence/sandbox/P4-all.json) and DECIDES from what the probe printed.

The probe's one call is answered with the transcript of a correctly confined session, built from the arguments the
probe was really given (so each path in it is the session's own) and from the command line the wrapper really built
(so the mountinfo names exactly what the wrapper mounts). Bubblewrap is a file that runs nothing; git (the
measurement's own worktree) is real; the process table and the operator's namespace links, which only a Linux host
has, are supplied. Nothing executes and no /proc is read, so what is pinned is the same on every host. The boundary
itself is measured by validation/v21/sandbox (docker): nothing here claims it."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from aisef2.runtime import process_range  # noqa: E402
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

#: what PROBE's m() puts in front of each line it means to be read (the rest is a command's own output)
MARK = "@@aisef-confine "
CAPS = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
#: the five capability sets of a session as the wrapper must give it: all zero, each written with a different number
#: of digits, so that a set the record took from another line of the status shows
CAP_VALUES = {k: "0" * (16 - i) for i, k in enumerate(CAPS)}
NAMESPACES = ("user", "pid", "net", "ipc", "uts", "mnt")
#: the operator's own namespace links (what /proc/self/ns of the measuring process holds)
OUTSIDE = {n: f"{n}:[{4026531800 + i}]" for i, n in enumerate(NAMESPACES)}
#: the probe's file arguments ($2 $3 $4 $8 $9) by what each is a file of, and whether the operator can write beside it
FILES = {"run_directory": 1, "kernel": 2, "interpreter_site": 3, "client_directory": 7, "git_directory": 8}
OPERATOR_CAN = {"run_directory": True, "kernel": False, "interpreter_site": True, "client_directory": False,
                "git_directory": True}

#: /proc/self/status of a session as the wrapper must give it (no Seccomp_filters line: a kernel before 5.9 prints
#: none, and where it is printed it reads 0 like Seccomp, which would not tell a record that read it from one that did not)
STATUS = ["Name:\tsh", "Umask:\t0022", "State:\tR (running)", "Uid:\t1000\t1000\t1000\t1000", "Gid:\t1000\t1000\t1000\t1000",
          *[f"{k}:\t{v}" for k, v in CAP_VALUES.items()], "NoNewPrivs:\t1", "Seccomp:\t0"]
#: /proc/net/dev: two header lines (neither has a colon), then one row per interface
NETDEV = ["Inter-|   Receive                                                |  Transmit",
          " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier",
          "    lo:       0       0    0    0    0     0          0         0        0       0    0    0    0     0",
          "  eth0:  123456     100    0    0    0     0          0         0   123456     100    0    0    0     0"]
#: /proc/net/route: a header, then one tab-separated row per route. wlan0 has the first row and eth0 two, docker0 has
#: the last: a record that loses the first or the last row, or lists a name twice, or does not sort, shows
ROUTE = ["Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT",
         "wlan0\t0000FEA9\t00000000\t0001\t0\t0\t1000\t0000FFFF\t0\t0\t0",
         "eth0\t00000000\t0102A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0",
         "eth0\t0002A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0",
         "docker0\t000011AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0"]
#: the interfaces that have a route there, once each, sorted
ROUTED = ["docker0", "eth0", "wlan0"]

#: the options of a bubblewrap command line that mount something -> (how many arguments, which is the destination)
MOUNTS = {"--bind": (2, 1), "--ro-bind": (2, 1), "--tmpfs": (1, 0), "--proc": (1, 0), "--dev": (1, 0)}
#: the other options that take arguments
TAKES = {"--symlink": 2, "--chdir": 1, "--cap-drop": 1}
#: what each mounting option gives the session, as /proc/self/mountinfo says it: (access, file system)
KIND = {"--ro-bind": ("ro", "ext4"), "--bind": ("rw", "ext4"), "--tmpfs": ("rw", "tmpfs"), "--proc": ("rw", "proc")}


def destinations(argv: list[str]) -> list[tuple[str, str]]:
    """(option, destination) of each mount a bubblewrap command line makes, read option by option up to its `--`."""
    out, i = [], 1                  # argv[0] is bubblewrap itself
    while argv[i] != "--":
        n, at = MOUNTS.get(argv[i], (TAKES.get(argv[i], 0), None))
        if at is not None:
            out.append((argv[i], argv[i + 1 + at]))
        i += 1 + n
    return out


def mounts(argv: list[str]) -> list[tuple[str, str, str]]:
    """(at, access, fs) of what the session has mounted: the root, and one mount per option (/dev has children)."""
    out = [("/", "rw", "tmpfs")]
    for flag, at in destinations(argv):
        if flag == "--dev":
            out += [(at, "rw", "tmpfs"), (f"{at}/pts", "rw", "devpts"), (f"{at}/null", "rw", "tmpfs")]
        else:
            out.append((at, *KIND[flag]))
    return out


def mountinfo(argv: list[str]) -> list[str]:
    """The lines of /proc/self/mountinfo of that session; a space, a tab, a newline and a backslash of a path are
    written in octal, as the kernel writes them."""
    def escaped(path: str) -> str:
        return re.sub(r"[ \t\n\\]", lambda m: f"\\{ord(m[0]):03o}", path)
    return [f"{40 + i} 30 0:{50 + i} / {escaped(at)} {access},relatime shared:{i} - {fs} {fs} {access}"
            for i, (at, access, fs) in enumerate(mounts(argv))]


def devices(argv: list[str]) -> list[str]:
    """The probe's `devices` section: each node `--dev` places, read inside as the character device it must be."""
    return [f"char {number} {at}/{name}" for flag, at in destinations(argv) if flag == "--dev"
            for name, number in confine.DEVICES.items()]


def tries(args: list[str]) -> dict[str, tuple[int, str]]:
    """{try: (exit, what it printed)} of a session as the wrapper must give it, for the probe's arguments `args`."""
    canary, run_directory, kernel, site, _home, _file, _sleep, client, git = args[:9]
    # a file's own name, not its path: the record keeps only the first 300 characters of what a try printed (another
    # target's rule) and a session's paths have any length, so the scripted text stays well below it on every host
    leaf = os.path.basename
    denied = "probe: {}: cannot create {}: Read-only file system".format
    return {"read_canary": (1, f"cat: {leaf(canary)}: No such file or directory"),
            # observed (P4): the write lands in the session's own tmpfs; whether it reached the host is judged apart
            "write_run_directory": (0, ""),
            "write_kernel": (2, denied(11, leaf(kernel))),
            "write_interpreter_site": (2, denied(12, leaf(site))),
            "write_client_directory": (2, denied(13, leaf(client))),
            "write_git_directory": (2, denied(14, leaf(git))),
            "read_git_directory": (0, "ref: refs/heads/main"),
            "workspace": (0, "ok"),
            "user_namespace": (1, "unshare: unshare failed: No space left on device"),
            "setsid": (0, "")}


def inside_links(network: str) -> dict[str, str]:
    """readlink /proc/self/ns/* inside: a namespace of its own, the network the operator's when the run shares it."""
    own = {n: f"{n}:[{4026532000 + i}]" for i, n in enumerate(NAMESPACES)}
    return {**own, "net": own["net"] if network == "none" else OUTSIDE["net"]}


def transcript(argv: list[str], args: list[str], network: str, script: dict) -> str:
    """What PROBE prints under the command line `argv` given `args` ($1 ...). `script` replaces a part: status,
    mountinfo, route, netdev, home (lists of lines), sockets (lines; "{ws}" is the workspace), listed (whether `find`
    ran), tries ({try: (exit, text)})."""
    ws = os.path.dirname(args[5])
    parts = {"status": STATUS, "mountinfo": mountinfo(argv), "devices": devices(argv), "route": ROUTE, "netdev": NETDEV,
             "home": []}
    parts.update({k: v for k, v in script.items() if k in parts})
    out = [f"{MARK}uid 1000"]
    out += [f"{MARK}ns {n} {link}" for n, link in inside_links(network).items()]
    for name, lines in parts.items():
        out += [f"{MARK}section {name}", *lines]
    for name, (rc, text) in {**tries(args), **script.get("tries", {})}.items():
        out += [f"{MARK}try {name}", *([text] if text else []), f"{MARK}rc {rc}"]
    out += [f"{MARK}section sockets", *[s.format(ws=ws) for s in script.get("sockets", [])]]
    out += [f"{MARK}sockets listed"] if script.get("listed", True) else []
    return "\n".join([*out, f"{MARK}end", ""])


def measure(tmp: pathlib.Path, network: str = "host", host=None, **script) -> types.SimpleNamespace:
    """confine.measure of the scripted session, in-process: `tmp` is a new directory of the test's. What it returns:
    rep (the measurement's report), calls (each call made to bubblewrap), argv (the command line the probe ran
    under, up to its `--`) and args (the probe's $1 ...). `host`: the host's mount table as the measurement reads it
    (v21_r3_conf_rows.host_table; a minimal host by default)."""
    bwrap = tmp / "bwrap"
    bwrap.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")     # nothing here runs it: its calls are answered below
    bwrap.chmod(0o755)
    client = tmp / "client" / "opencode"
    client.parent.mkdir()
    client.write_text("#!/bin/sh\n", encoding="utf-8")
    readable = tmp / "readable"
    readable.mkdir()
    spec = {"backend": "bwrap", "bwrap": str(bwrap), "network": network, "read_only": [str(readable)]}
    seen = types.SimpleNamespace(spec=spec, where=tmp / "run" / "confinement", client=client, readable=readable,
                                 calls=[], argv=[], args=[], can={})
    real_run, real_access, real_namespaces = subprocess.run, os.access, confine.namespaces

    def run(argv, *a, **k):
        if not (isinstance(argv, list) and argv[:1] == [str(bwrap)]):
            return real_run(argv, *a, **k)          # git: the measurement's own worktree
        seen.calls.append(list(argv))
        if argv[1:] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, "bubblewrap 0.12.0\n", "")
        if confine.PROBE not in argv:               # bubblewrap given no command to run
            return subprocess.CompletedProcess(argv, 1, "", "bwrap: No command specified\n")
        seen.argv, seen.args = argv[:argv.index("--") + 1], argv[argv.index(confine.PROBE) + 2:]
        seen.can = {str(pathlib.Path(seen.args[i]).parent): OPERATOR_CAN[key] for key, i in FILES.items()}
        return subprocess.CompletedProcess(argv, 0, transcript(seen.argv, seen.args, network, script), "")

    def access(path, mode, **k):                    # what the operator can write is the test's, per directory
        if mode == os.W_OK and os.fspath(path) in seen.can:
            return seen.can[os.fspath(path)]
        return real_access(path, mode, **k)

    def namespaces(inside, outside=None):
        return real_namespaces(inside, OUTSIDE if outside is None else outside)

    with mock.patch.object(subprocess, "run", run), mock.patch.object(os, "access", access), \
            mock.patch.object(confine, "namespaces", namespaces), mock.patch.object(process_range, "process_table", dict), \
            rows.host_table(host):
        seen.rep = confine.measure(spec, seen.where, str(client), system="linux", environ={"PATH": "/usr/bin:/bin"})
    return seen


class Measured(unittest.TestCase):
    """One scripted measurement per class (`network`, `script`); the tests read what it recorded."""

    network = "host"
    script: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        cls.seen = measure(pathlib.Path(os.path.realpath(t.name)), cls.network, **cls.script)
        cls.rep = cls.seen.rep
        cls.inside = cls.rep["inside"]


class CorrectlyConfinedSession(Measured):
    """A session as the wrapper must give it (host network), measured. The measurement accepts it, and the record
    holds what the probe printed, each under its name: RUN.json.confinement.inside is what an operator reads to see
    what was observed (SANDBOX-LINUX §5 'Observed', §7 'Seccomp: 0'). A reading lost from the record, or kept under
    another name, is a measurement that no longer says what it saw; a reading the verdict is made from that is not
    read refuses every Linux measurement (or, where the key is read, crashes it).
    Pins aisef2/app/confine.py::_probe [31, 32, 33, 35, 68, 69, 70, 72, 115, 117, 118, 119, 121, 122, 144, 148, 151,
    153, 154, 162, 164, 165, 166, 174]."""

    def test_it_is_not_refused(self):
        """The verdict is made from the probe's sections: status (capabilities, NoNewPrivs), mountinfo, the namespace
        links, the socket listing. A section that is not read is a check that 'could not run': a problem."""
        self.assertEqual(self.rep["problems"], [])

    def test_the_record_has_each_reading_under_its_name(self):
        """What a reader of RUN.json.confinement.inside looks for by name (a field added later is not this test's)."""
        named = {"uid", "capabilities", "no_new_privs", "seccomp", "network_interfaces", "routed_interfaces", "mounts",
                 "mount_targets", "namespaces", "home_listing", "unix_sockets"}
        self.assertEqual(named - set(self.inside), set())

    def test_the_uid_is_what_id_printed(self):
        """The uid the session ran as (P4: 1000, the operator's own, not root): the record's `uid` is `id -u` inside."""
        self.assertEqual(self.inside["uid"], "1000")

    def test_the_capabilities_are_the_five_sets_the_status_reports(self):
        """CapBnd is recorded though not judged (SANDBOX-LINUX §5: CapInh/CapPrm/CapEff/CapBnd/CapAmb = 0). Each set is
        the one its own line of the status gave (they are all zero, written with different widths)."""
        self.assertEqual(self.inside["capabilities"], CAP_VALUES)

    def test_no_new_privs_and_seccomp_are_the_status_values(self):
        """Seccomp '0' is the honest limit of this boundary (no syscall filter): the record says what was read."""
        self.assertEqual((self.inside["no_new_privs"], self.inside["seccomp"]), ("1", "0"))

    def test_network_interfaces_are_the_names_in_proc_net_dev_in_order(self):
        """The rows after the two header lines, the name before the colon (SANDBOX-LINUX §4: the data behind 'a fresh
        loopback, no route')."""
        self.assertEqual(self.inside["network_interfaces"], ["lo", "eth0"])

    def test_the_mounts_are_what_mountinfo_says_and_their_targets_what_the_wrapper_names(self):
        """The judgement's 'mounted beyond what the wrapper names' compares the one with the other; the targets are
        read off the command line the record carries, option by option."""
        # a row is what mountinfo's line says of the mount, the fields the write policy decides from included (B03-R3)
        self.assertEqual(self.inside["mounts"],
                         [{"at": at, "access": access, "fs": fs, "dev": f"0:{50 + i}", "root": "/", "source": fs,
                           "options": [access, "relatime"], "super_options": [access], "optional": [f"shared:{i}"]}
                          for i, (at, access, fs) in enumerate(mounts(self.seen.argv))])
        self.assertEqual(self.inside["mount_targets"], [at for _, at in destinations(self.rep["argv"])])
        for named in ("/proc", "/dev", "/tmp", str(self.seen.where / "ws"), str(self.seen.readable),
                      str(self.seen.client.parent)):
            self.assertIn(named, self.inside["mount_targets"])

    def test_the_namespaces_are_own_except_the_shared_network(self):
        self.assertEqual(self.inside["namespaces"],
                         {"user": "own", "pid": "own", "net": "shared", "ipc": "own", "uts": "own", "mnt": "own"})

    def test_a_listing_that_found_no_socket_is_an_empty_list_not_unknown(self):
        """`m sockets listed` after an empty section: the check ran and found nothing (None is 'could not list')."""
        self.assertEqual(self.inside["unix_sockets"], [])
        self.assertEqual(self.inside["home_listing"], [])

    def test_the_interfaces_with_a_route_are_recorded_once_each_sorted(self):
        """/proc/net/route has one row for wlan0, two for eth0 and one for docker0 (host network: not judged, but
        recorded)."""
        self.assertEqual(self.inside["routed_interfaces"], ROUTED)


class WhatWasTried(Measured):
    """The record says, for each operation tried, what happened (the owner's 2026-10-06 rule: every claim names the
    operation and what the session saw), and which denials the operator could have written beside: a denial is
    evidence only where the operator could write (SANDBOX-LINUX §5). `operator_can` pairs with `tried` by the name of
    the write try. Pins aisef2/app/confine.py::_probe [80, 83, 126, 129]."""

    def test_each_try_has_its_exit_and_the_text_it_printed(self):
        want = {name: {"exit": rc, "output": text} for name, (rc, text) in tries(self.seen.args).items()}
        self.assertEqual(self.rep["tried"], want)
        self.assertIn("cannot create", self.rep["tried"]["write_kernel"]["output"])     # a denial names its operation

    def test_operator_can_is_one_per_write_try_under_the_same_name(self):
        self.assertEqual(self.rep["operator_can"], {f"write_{k}": v for k, v in OPERATOR_CAN.items()})
        self.assertEqual({k for k in self.rep["tried"] if k.startswith("write_")}, set(self.rep["operator_can"]))


class BubblewrapRelease(Measured):
    """The readable release of the bubblewrap the measurement ran (bwrap_sha256 is the binding; the version is what a
    reader can name). It is what `<bwrap> --version` printed, stripped: a record that has no such field, or a
    wrong value that looks like a read, is not evidence of which bubblewrap was measured.
    Pins aisef2/app/confine.py::_probe [87, 167, 168, 176]."""

    def test_the_release_is_asked_of_bubblewrap_with_its_version_option(self):
        self.assertIn([self.seen.spec["bwrap"], "--version"], self.seen.calls)

    def test_the_record_holds_what_it_printed(self):
        self.assertEqual(self.rep["bwrap_version"], "bubblewrap 0.12.0")


class RoutesUnderNetworkNone(Measured):
    """network 'none' (the measurement-only profile of validation/v21/sandbox) and a /proc/net/route that has routes:
    a fresh network namespace has none, so a session that has some is not on one — the measurement says so, naming
    the interfaces. Without it the profile's claim 'no route' could never be refused.
    Pins aisef2/app/confine.py::_probe [33, 70, 119, 151, 165]."""

    network = "none"

    def test_a_route_refuses_the_measurement_naming_each_interface_once(self):
        self.assertEqual(len(self.rep["problems"]), 1, self.rep["problems"])
        problem = self.rep["problems"][0]
        self.assertIn("network none has routes on", problem)
        for name in ROUTED:
            self.assertEqual(problem.count(name), 1, problem)

    def test_the_record_holds_the_interfaces_with_a_route(self):
        self.assertEqual(self.inside["routed_interfaces"], ROUTED)
        self.assertEqual(self.inside["namespaces"]["net"], "own")


class AFreshNetworkNamespace(Measured):
    """network 'none' and a /proc/net/route of only its header, though /proc/net/dev lists the kernel's DOWN tunnel
    pseudo-devices (SANDBOX-LINUX §4, P4): accepted, no interface routed. Reachability is judged by routes, never by
    interface names, so this is the other side of the decision RoutesUnderNetworkNone pins ([119, 165] are killed
    there; here is what keeps a fix of them from refusing a fresh namespace for its interface names)."""

    network = "none"
    script = {"route": ROUTE[:1],
              "netdev": [*NETDEV[:2], "    lo:       0       0    0    0    0     0", "tunl0:       0       0    0    0",
                         " gre0:       0       0    0    0"]}

    def test_it_is_not_refused(self):
        self.assertEqual(self.rep["problems"], [])

    def test_interfaces_are_listed_and_none_is_routed(self):
        self.assertEqual(self.inside["network_interfaces"], ["lo", "tunl0", "gre0"])
        self.assertEqual(self.inside["routed_interfaces"], [])


if __name__ == "__main__":
    unittest.main()
