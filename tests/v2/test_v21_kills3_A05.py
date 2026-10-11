"""V2.1 mutation survivors, batch A05: what `confine.measure` makes of the text its probe printed (aisef2/app/confine.py,
`_probe`; docs/v2.1/SANDBOX-LINUX.md §3, §5).

The measured sandbox is the subject: the report is parsed from text the sandbox's own shell printed between two
markers, so the parse must hold for what a sandbox *can* print, not only for what a kernel's /proc files look like. Here
the probe's subprocess is answered by the test (nothing is started, nothing is written outside the test's directory):
`measure` runs as `run.execute` and `--check` call it, with a real worktree and the real command line, and the probe's
output is the test's. Four behaviours, each with its readers:

* the record states which uid the session ran as (RUN.json `confinement.inside.uid`, printed by `aisef run --check`;
  beside `operator_uid`, the host side);
* a line that is not a row of `/proc/self/status`, `/proc/net/dev` or `/proc/net/route` is no capability, no
  interface and no route, and never a crash (a crash is a traceback where the operator needs `problems`); a route is
  what refuses `network: none` ("network none has routes on [...]"), so a stray line must not become one;
* `routed_interfaces` is the set of routed interface names in a stable order, whatever the interpreter's hash seed;
* a probe that could not be started or ran out of time is refused naming what the OS or the timer said (the contract
  an operator reads in `RunRefused` and `--check`: the cause class and its message, not the punctuation between)."""

from __future__ import annotations

import itertools
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
from aisef2.runtime import process_range  # noqa: E402

M = confine.MARK
SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
ZERO = "0000000000000000"
#: what a kernel prints of /proc/self/status, /proc/net/route and /proc/net/dev (the lines the report is made of)
STATUS = ["Name:\tcat", "NoNewPrivs:\t1", "Seccomp:\t0",
          *(f"{k}:\t{ZERO}" for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))]
ROUTE_HEAD = ["Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT"]
NETDEV_HEAD = ["Inter-|   Receive                                                |  Transmit",
               " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls"]


def route_row(iface: str) -> str:
    return f"{iface}\t00000000\t0102A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0"


def netdev_row(iface: str) -> str:
    return f"{iface:>6}:  1234     12    0    0    0     0          0         0     1234     12    0    0    0     0"


def render(*, uid: str = "1000", status=STATUS, route=ROUTE_HEAD, netdev=NETDEV_HEAD) -> str:
    """The probe's output in the order its script prints it (PROBE), as far as the report reads it."""
    lines = [f"{M}uid {uid}", *(f"{M}ns {n} {n}:[40260{i}]" for i, n in enumerate(("user", "pid", "net", "ipc", "uts", "mnt")))]
    for name, body in (("status", status), ("mountinfo", []), ("route", route), ("netdev", netdev), ("home", [])):
        lines += [f"{M}section {name}", *body]
    lines += [f"{M}try workspace", "ok", f"{M}rc 0", f"{M}section sockets", f"{M}sockets listed", f"{M}end"]
    return "\n".join(lines) + "\n"


class Measured(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.bwrap = self.tmp / "bwrap"          # never started: the probe's subprocess is answered below
        self.bwrap.write_text("#!/bin/sh\nexit 97\n")
        self.bwrap.chmod(0o755)
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.tmp / "home"), "LANG": "C"}
        self.runs = 0

    def measure(self, printed: str, raises: BaseException | None = None, **spec) -> dict:
        """confine.measure of the run's own command line, the probe printing `printed` (or `raises`)."""
        real = subprocess.run

        def run(argv, *a, **k):
            if isinstance(argv, list) and confine.PROBE in argv:
                if raises is not None:
                    raise raises
                return subprocess.CompletedProcess(argv, 0, printed, "")
            if isinstance(argv, list) and argv[-1:] == ["--version"]:
                return subprocess.CompletedProcess(argv, 0, "bubblewrap 0.0.0\n", "")
            return real(argv, *a, **k)         # the measurement's own git
        self.runs += 1
        with mock.patch.object(subprocess, "run", run), mock.patch.object(process_range, "process_table", lambda: {}):
            return confine.measure({**SPEC, "bwrap": str(self.bwrap), **spec}, self.tmp / f"m{self.runs}", str(self.exe),
                                   system="linux", environ=self.env)


class Uid(Measured):
    def test_the_record_says_which_uid_the_session_ran_as(self):
        """The first thing the probe reports is `id -u`; the record keeps it under `inside.uid`, the session's side of
        `operator_uid`. Pins aisef2/app/confine.py::_probe [28, 65, 120]."""
        for uid in ("1000", "0"):
            with self.subTest(uid=uid):
                self.assertEqual(self.measure(render(uid=uid))["inside"]["uid"], uid)


class Rows(Measured):
    def test_a_status_line_that_is_not_a_key_value_row_is_skipped_not_a_crash(self):
        """A line without a colon among the status lines must not stop the measurement (a ValueError out of `measure`
        is a traceback, not a `problems` entry) and must not hide the rows around it. Pins _probe [163]."""
        rep = self.measure(render(status=["Name:\tcat", "stray: not here", "Killed", *STATUS[1:]]))
        inside = rep["inside"]
        self.assertEqual((inside["no_new_privs"], inside["seccomp"]), ("1", "0"))
        self.assertEqual(inside["capabilities"], dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), ZERO))

    def test_a_netdev_line_that_is_not_an_interface_row_is_no_interface(self):
        """/proc/net/dev's rows are `<name>: counters`; a line after the two header lines that is not one names no
        interface. Pins _probe [150]."""
        rep = self.measure(render(netdev=[*NETDEV_HEAD, netdev_row("lo"), "this is not an interface row",
                                          netdev_row("eth0")]))
        self.assertEqual(rep["inside"]["network_interfaces"], ["lo", "eth0"])

    def test_a_route_line_that_is_not_a_route_row_is_no_route_and_refuses_nothing(self):
        """A line without the row's tabs is no route: with `network: none` it must not make the refusal that a
        reachable network exists, and next to a real row it is not listed. Pins _probe [152]."""
        stray = "this is not a route row"
        alone = self.measure(render(route=[*ROUTE_HEAD, stray]), network="none")
        self.assertEqual(alone["inside"]["routed_interfaces"], [])
        self.assertFalse([p for p in alone["problems"] if "has routes" in p], alone["problems"])
        both = self.measure(render(route=[*ROUTE_HEAD, stray, route_row("eth0")]), network="none")
        self.assertEqual(both["inside"]["routed_interfaces"], ["eth0"])
        # the refusal names the cause (a route exists under `network: none`) and the interface it is on, not the stray line
        [refusal] = [p for p in both["problems"] if "has routes" in p]
        self.assertIn("eth0", refusal)
        self.assertNotIn(stray, refusal)


class Order(Measured):
    def test_routed_interfaces_are_the_unique_names_in_a_stable_order(self):
        """The same observation gives the same list whatever the interpreter's hash seed: a set's order is a function
        of it, so the names are taken from a pool until their set does not iterate in sorted order in this process —
        then the sorted list is the only answer. Pins _probe [76]."""
        pool = ("eth0", "eth1", "wlan0", "docker0", "br-1a2b", "veth9f3c", "tun0", "tap1")
        names = next(list(p) for p in itertools.permutations(pool, 6) if list(set([*p, p[0]])) != sorted(set(p)))
        rows = [route_row(n) for n in names] + [route_row(names[0])]      # one name routed twice
        rep = self.measure(render(route=[*ROUTE_HEAD, *rows]))
        self.assertEqual(rep["inside"]["routed_interfaces"], sorted(names))


class NotRun(Measured):
    def test_a_probe_that_could_not_run_is_refused_naming_the_cause_and_what_it_said(self):
        """Nothing was measured, so the run is refused for that and only that: "exit None" (no exit status, the probe
        never ran) with the exception's class and its message — for an OS refusal the errno text and the path it named,
        for the timer the class that says time ran out. The contract is those identifying elements, not the separator
        between class and message (_probe [161] is AUDITED against it: the mutant keeps every element)."""
        for exc, elements in ((OSError(8, "Exec format error", "/opt/bwrap"), ("OSError", "Exec format error", "/opt/bwrap")),
                              (subprocess.TimeoutExpired(["bwrap"], 60), ("TimeoutExpired",))):
            with self.subTest(exc=type(exc).__name__):
                [reason] = self.measure("", raises=exc)["problems"]
                self.assertTrue(reason.startswith("the sandbox did not run the probe (exit None): "), reason)
                for element in elements:
                    self.assertIn(element, reason)


if __name__ == "__main__":
    unittest.main()
