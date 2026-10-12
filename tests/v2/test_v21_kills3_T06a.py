"""V2.1 mutation survivors, batch T06a (owner directive B-03): aisef2/app/confine.py::_judge and ::argv.

Nothing here runs bubblewrap or a probe: `_judge` is given a measurement as data, and `argv`/`wrap` only build a
command line. What each class pins is the requirement the survivors' code serves:

* AcceptedMeasurement — `_judge` is a decision (accept / refuse a measured session): a clean measurement of a real
  layout is accepted, whichever network it measured, and a writable host filesystem outside the workspace is still named.
* RecordedLinuxMeasurements — the same decision on the committed measurements of a real Linux host (docs/v2.1/evidence).
* RefusalReasons — the facts a refusal carries to the operator: the exit code that was measured, and the names HOME
  shows, in a stable order and cut (the text is recorded in RUN.json and printed by the refusal: the same exposure is
  the same evidence on every run).
* SessionLine — the bubblewrap command line of a session parses the way bubblewrap parses it, and carries the pseudo
  filesystems, the cgroup namespace and the system as what it is on the host; its isolation options are those of the
  lines a real Linux host accepted.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

#: str(WS) is "/run/confinement/ws" on every host: the judge compares mount points with it as POSIX strings
WS = pathlib.PurePosixPath("/run/confinement/ws")
#: the operator's HOME as the probe was given it
HOME = "/h"
EVIDENCE = ROOT / "docs" / "v2.1" / "evidence" / "sandbox"


def mount(at: str, fs: str, access: str = "ro") -> dict:
    """A row as mountinfo gives it: a pseudo file system is the sandbox's own (its own name as source, a super block
    the host's table lacks); what is read-only or host storage is not judged by that."""
    return rows.mount(at, fs, access)


def layout() -> list[dict]:
    """The mounts a confined session sees on a real Linux host, in the shape docs/v2.1/evidence/sandbox/X3 records
    them: a tmpfs root, the system and the client read-only, a procfs, the devices, /tmp and HOME as tmpfs, the
    configuration, and the workspace read-write."""
    return [mount("/", "tmpfs", "rw"), mount("/usr", "overlay"), mount("/etc", "overlay"), mount("/etc/hosts", "ext4"),
            mount("/proc", "proc", "rw"), mount("/dev", "tmpfs", "rw"), mount("/dev/null", "tmpfs", "rw"),
            mount("/dev/pts", "devpts", "rw"), mount("/tmp", "tmpfs", "rw"), mount("/aisef-home", "tmpfs", "rw"),
            mount("/opt/client", "overlay"), mount(f"{HOME}/.config/opencode", "overlay"), mount(str(WS), "overlay", "rw")]


TARGETS = ["/usr", "/etc", "/proc", "/dev", "/tmp", "/aisef-home", "/opt/client", f"{HOME}/.config/opencode", str(WS)]


def measured(network: str = "host") -> tuple[dict, dict]:
    """(rep, tries) of a clean measurement: every check passes. With "host" the session shares the network, so the
    host's interface `eth0` has a route (every real record); with "none" it has a fresh namespace and no route."""
    zero = "0000000000000000"
    rep = {"network": network, "host_mounts": rows.HOST,
           "created_outside_workspace": dict.fromkeys(("run_directory", "kernel", "interpreter_site", "client_directory",
                                                       "git_directory"), False),
           "setsid_survivors": [],
           "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), zero),
                      "no_new_privs": "1",
                      "namespaces": {**dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                                     "net": "own" if network == "none" else "shared"},
                      "routed_interfaces": [] if network == "none" else ["eth0"],
                      "mounts": layout(), "mount_targets": list(TARGETS), "home_listing": [".config"],
                      "unix_sockets": [], "device_roots": ["/dev"], "devices": {"/dev/null": "1:3"}}}
    tries = {"read_canary": (1, "cat: canary: No such file or directory"), "read_git_directory": (0, "ref: refs/heads/main"),
             "setsid": (0, ""), "user_namespace": (1, "unshare: unshare failed: No space left on device"),
             "workspace": (0, "ok")}
    return rep, tries


def judged(rep: dict, tries: dict, home: str = HOME, ws=WS) -> list[str]:
    return confine._judge(rep, "tok", "", tries, home, ws)


class AcceptedMeasurement(unittest.TestCase):
    """`_judge` accepts what a correctly confined session measures — a run that asks for confinement is refused on any
    problem, so a problem raised on the normal measurement refuses every confined run."""

    def test_the_shared_network_with_its_route_is_not_a_problem(self):
        """network "host": the session shares the host's network so it reaches its provider, and the record says so;
        the interface that carries the route is not "a reachable network" problem. Pins confine.py::_judge [36]."""
        rep, tries = measured("host")
        self.assertEqual(rep["inside"]["routed_interfaces"], ["eth0"])      # the premise: a route is there
        self.assertEqual(judged(rep, tries), [])

    def test_a_network_namespace_of_its_own_without_a_route_is_not_a_problem(self):
        """network "none" and no routed interface is the fresh namespace --unshare-net gives. Pins _judge [36]."""
        rep, tries = measured("none")
        self.assertEqual(judged(rep, tries), [])

    def test_a_route_inside_a_network_namespace_of_its_own_is_the_problem_and_names_the_interface(self):
        """The other side of the decision: "none" with a routed interface is a reachable network, named by interface."""
        rep, tries = measured("none")
        rep["inside"]["routed_interfaces"] = ["eth0"]
        problems = judged(rep, tries)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("network none", problems[0])
        self.assertIn("eth0", problems[0])

    def test_the_procfs_bubblewrap_mounts_writable_is_not_host_storage(self):
        """A writable mount whose filesystem is not backed by host storage (the procfs at /proc, which every measured
        profile records read-write) is not "writable outside the workspace". Pins _judge [141, 156]."""
        rep, tries = measured("host")
        rep["inside"]["mounts"] = [mount("/", "tmpfs", "rw"), mount(str(WS), "ext4", "rw"), mount("/proc", "proc", "rw")]
        rep["inside"]["mount_targets"] = [str(WS), "/proc"]
        rep["inside"]["home_listing"] = []
        self.assertEqual(judged(rep, tries), [])

    def test_a_writable_host_filesystem_outside_the_workspace_is_named_and_the_procfs_is_not(self):
        """The rest of the layout stays: an ext4 mount outside the workspace is the problem, and it is the only name."""
        rep, tries = measured("host")
        rep["inside"]["mounts"].append(mount("/srv", "ext4", "rw"))
        rep["inside"]["mount_targets"].append("/srv")
        problems = judged(rep, tries)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("/srv", problems[0])
        self.assertNotIn("/proc", problems[0])


def accepted_records() -> list[tuple[str, dict]]:
    """[(file name, record)] of the committed measurements of a real Linux host the kernel accepted (`problems` empty);
    a record of a host that could not start the probe has no measurement to judge."""
    out = []
    for path in sorted(EVIDENCE.glob("[PX][0-9]-*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        rep = rec.get("measure") if isinstance(rec, dict) else None
        if isinstance(rep, dict) and rep.get("problems") == [] and "inside" in rep:
            out.append((path.name, rec))
    return out


class RecordedLinuxMeasurements(unittest.TestCase):
    """The measurements of a real Linux host with real bubblewrap (docs/v2.1/evidence/sandbox, validation/v21/sandbox):
    one the kernel accepted at the time (`problems` empty) is accepted again by `_judge` on the same data — the
    strongest oracle there is for "a correctly confined session is not refused". Pins _judge [36, 141, 156]."""

    def test_a_measurement_that_was_accepted_is_accepted_again(self):
        """Since B03-R3 (owner, 2026-10-12) a writable mount outside the workspace is accepted only when the report
        shows it is the sandbox's own. These four records predate that: their rows carry no mount source and no super
        block and they hold no host table, so they cannot show it. They are accepted again for everything else — the
        judge's only words are the one problem that names each such mount as NOT ESTABLISHED (fail closed, never a
        pass); the records that carry the data are replayed whole by test_v21_r3_conf_policy."""
        accepted = accepted_records()
        for name, rec in accepted:
            rep = rec["measure"]
            tries = {k: (v["exit"], v["output"]) for k, v in rep["tried"].items()}
            ws = pathlib.PurePosixPath(rep["inside"]["mount_targets"][-1])      # the workspace is bound last
            home = next(t[:-len("/.config/opencode")] for t in rep["inside"]["mount_targets"] if t.endswith("/.config/opencode"))
            writable = list(dict.fromkeys(m["at"] for m in rep["inside"]["mounts"] if m["access"] == "rw" and m["at"] != str(ws)))
            with self.subTest(record=name, network=rep["network"]):
                self.assertTrue(writable)       # the premise: the record has sandbox-made writable mounts
                self.assertEqual(judged(rep, tries, home, ws), [
                    "cannot establish that a writable mount belongs to the sandbox (isolation not established, not a "
                    "write that was seen): " + "; ".join(f"{at}: its mount source was not read" for at in writable)])
        if not accepted:
            self.skipTest(f"no accepted measurement under {EVIDENCE}")


class Fixed(str):
    """A str whose hash the case fixes: in a set of a dozen of them with distinct hashes 1-12 each one sits in the slot
    its hash names, so the set iterates in hash order (CPython), whatever PYTHONHASHSEED is."""

    def __new__(cls, value: str, h: int) -> "Fixed":
        s = super().__new__(cls, value)
        s.h = h
        return s

    def __hash__(self) -> int:
        return self.h


class RefusalReasons(unittest.TestCase):
    """What a refusal says is printed to the operator and recorded in RUN.json (`confinement.problems`)."""

    def test_the_exit_code_of_the_user_namespace_try_can_be_read_back_from_the_problem(self):
        """"no refusal of a further user namespace was measured" carries the measured exit code and the probe's own
        words as two things: an excerpt that begins with a digit must not turn "exit 1" into "exit 17". Pins _judge [131]."""
        rep, tries = measured("host")
        tries["user_namespace"] = (1, "7 unexpected arguments")
        problems = judged(rep, tries)
        self.assertEqual(len(problems), 1, problems)
        said = re.search(r"exit (\d+)", problems[0])
        self.assertIsNotNone(said, problems[0])
        self.assertEqual(said.group(1), "1", problems[0])
        self.assertIn("7 unexpected arguments", problems[0])

    def test_the_names_home_shows_are_listed_in_name_order_and_cut_after_ten(self):
        """"HOME shows more than the way to what is mounted" lists the exposed names sorted, the first ten: the same
        exposure gives the same text on every run (a set's order follows the process's hash seed), and the cut keeps
        the same ten. The names' set order is fixed here to be the reverse of name order and the listing itself is
        rotated, so only sorting gives name order. Pins _judge [162]."""
        names = [f".x{i:02d}" for i in range(12)]
        exposed = [Fixed(n, len(names) - i) for i, n in enumerate(names)]
        listing = exposed[7:] + exposed[:7]
        self.assertNotEqual(list(set(exposed))[:10], sorted(exposed)[:10])      # the premise: set order is not name order
        self.assertNotEqual(listing[:10], sorted(exposed)[:10])                 # ... nor is the listing's own order
        rep, tries = measured("host")
        rep["inside"]["home_listing"] = listing
        problems = judged(rep, tries)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("HOME", problems[0])
        listed = ast.literal_eval(problems[0][problems[0].index("["):])
        self.assertEqual(listed, sorted(names)[:10])


#: how many arguments each option of the bubblewrap command line takes (`man bwrap`; what confine.argv emits)
ARITY = {**dict.fromkeys(("--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup-try",
                          "--unshare-net", "--share-net", "--disable-userns", "--die-with-parent", "--new-session"), 0),
         **dict.fromkeys(("--cap-drop", "--proc", "--dev", "--tmpfs", "--chdir"), 1),
         **dict.fromkeys(("--symlink", "--ro-bind", "--bind"), 2)}


def options(argv: list[str]) -> list[tuple[str, tuple[str, ...]]]:
    """[(option, arguments)] of the option section of `argv` (argv[0] is bubblewrap; the section ends at `--`), read
    the way bubblewrap reads it: an option takes the next tokens whatever they are, and the first token where an option
    belongs that does not start with `-` is the command — the rest of the line would become that command's arguments
    and be applied to nothing. Raises AssertionError on such a token, an unknown or empty option, a missing or empty
    argument, or an argument that looks like an option (a shifted line)."""
    head, out, i = argv[1:argv.index("--")], [], 0
    while i < len(head):
        flag = head[i]
        n = ARITY.get(flag)
        near = head[max(i - 2, 0):i + 3]
        if n is None and flag.startswith("-"):
            raise AssertionError(f"{flag!r} is not in this file's ARITY table: if bubblewrap has the option, add it with "
                                 f"its number of arguments; near {near}")
        if n is None:
            raise AssertionError(f"{flag!r} stands where bubblewrap expects an option (it would start the command "
                                 f"there); near {near}")
        args = tuple(head[i + 1:i + 1 + n])
        if len(args) < n or "" in args or any(a.startswith("-") for a in args):
            raise AssertionError(f"{flag} is not followed by its {n} argument(s): {args}")
        out.append((flag, args))
        i += 1 + n
    return out


class SessionLine(unittest.TestCase):
    """The bubblewrap command line a session gets (`confine.wrap(...)[0]`, which client.session hands to the process
    range), built for Linux on any host: nothing runs."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_text("#!/bin/sh\nexit 97\n")        # never run: the command line is only built
        self.bwrap.chmod(0o755)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "LANG": "C"}

    def wrap(self, network: str = "host", writable: bool = True) -> list[str]:
        spec = {"backend": "bwrap", "bwrap": str(self.bwrap), "network": network, "read_only": []}
        return confine.wrap(spec, [str(self.exe), "run", "the prompt"], self.env, str(self.ws), str(self.exe),
                            system="linux", writable=writable)[0]

    def test_every_option_is_followed_by_exactly_its_arguments_and_none_is_empty(self):
        """A line bubblewrap would misparse starts no session (the measurement's probe then "did not run" and a run
        refuses): every token before `--` is an option with its own arguments, in every profile a session gets.
        Pins confine.py::argv [15-20, 35, 42-47]; the system's own lines [57-59, 64, 65, 71] when this host has a
        link among confine.SYSTEM (the two system tests below are the ones that always reach them)."""
        for network in ("host", "none"):
            for writable in (True, False):
                with self.subTest(network=network, writable=writable):
                    argv = self.wrap(network, writable)
                    self.assertTrue(options(argv))
                    self.assertEqual(argv[argv.index("--") + 1:], [str(self.exe), "run", "the prompt"])

    def test_proc_dev_and_tmp_are_mounted_at_their_own_paths_and_home_is_an_empty_tmpfs(self):
        """The probe's own reads (/proc/self/status, /proc/self/ns/*, /proc/net/route), the client's /dev/null and
        /dev/urandom and its TMPDIR=/tmp rely on these four pairs; each is a pair, not four loose tokens.
        Pins argv [15-20, 42-47]."""
        opts = options(self.wrap())
        for want in (("--proc", ("/proc",)), ("--dev", ("/dev",)), ("--tmpfs", ("/tmp",)), ("--tmpfs", (confine.HOME,))):
            with self.subTest(want=want):
                self.assertIn(want, opts)

    def test_the_session_gets_a_cgroup_namespace_of_its_own_where_the_kernel_has_one(self):
        """`--unshare-cgroup-try` (best effort: the "-try" form never refuses) is on the line once, with the other
        unshare options, in both network profiles — the session's view of /proc/self/cgroup is its own.
        Pins argv [7, 35]. The option is in every recorded session line (docs/v2.1/evidence/sandbox/*.json) and has
        been on the line since the module's first commit, but SANDBOX-LINUX.md section 6 and the module docstring do
        not list it, and no measurement checks the namespace: this pins what the builder does today."""
        for network in ("host", "none"):
            with self.subTest(network=network):
                flags = [flag for flag, _ in options(self.wrap(network))]
                self.assertEqual(flags.count("--unshare-cgroup-try"), 1)

    def test_the_line_still_carries_every_isolation_option_the_accepted_measurements_ran_under(self):
        """The records of a real Linux host (docs/v2.1/evidence/sandbox, the same four that `problems` is empty in) hold
        the session line bubblewrap parsed and the kernel accepted: read by this file's grammar (`options`), every
        option of it that names no host path — an option without arguments, `--cap-drop`, and the pseudo filesystems
        `--proc`, `--dev`, `--tmpfs` — is on the line this builder gives the same network profile. A flag dropped or
        emptied would run a session under a line nobody measured; and the grammar `options` models parses the lines
        the kernel did. Pins argv [7, 15-20, 35, 42-47] on the evidence rather than on the builder's own literals."""
        accepted = accepted_records()
        for name, rec in accepted:
            ran = {(flag, args) for flag, args in options(rec["session_argv"])
                   if not ARITY[flag] or flag in ("--cap-drop", "--proc", "--dev", "--tmpfs")}
            with self.subTest(record=name, network=rec["measure"]["network"]):
                self.assertTrue(ran)        # the premise: the record has isolation options to look for
                self.assertEqual(sorted(ran - set(options(self.wrap(rec["measure"]["network"])))), [])
        if not accepted:
            self.skipTest(f"no accepted measurement under {EVIDENCE}")

    def test_the_system_is_bound_as_what_it_is_on_this_host(self):
        """SANDBOX-LINUX.md section 6: the system read-only, "a merged-/usr symlink stays a symlink". For each name of
        confine.SYSTEM the line carries what it is on the host (the oracle is the file system): a link as
        (--symlink, its target, name), a directory as (--ro-bind, name, name), an absent name nowhere — bubblewrap
        refuses a missing source. Pins argv [41, 57-59, 64, 65, 71]."""
        opts = options(self.wrap())
        for p in confine.SYSTEM:
            with self.subTest(path=p):
                if os.path.islink(p):
                    self.assertIn(("--symlink", (os.readlink(p), p)), opts)
                elif os.path.isdir(p):
                    self.assertIn(("--ro-bind", (p, p)), opts)
                else:
                    self.assertFalse([o for o in opts if p in o[1]], f"{p} is not on this host")

    def test_a_directory_is_bound_a_link_stays_a_link_and_an_absent_name_is_left_out(self):
        """The same on a SYSTEM of the test's own, so that each branch is reached on every host (the real tuple is
        host-dependent): a directory, a symbolic link and a name that does not exist. Pins argv [41, 57-59, 64, 65, 71]."""
        directory, link, absent = self.tmp / "sysdir", self.tmp / "syslink", self.tmp / "absent"
        directory.mkdir()
        try:
            os.symlink("real", link)
        except (OSError, NotImplementedError):
            self.skipTest("this host cannot make symbolic links")
        with mock.patch.object(confine, "SYSTEM", (str(directory), str(link), str(absent))):
            opts = options(self.wrap())
        self.assertIn(("--ro-bind", (str(directory), str(directory))), opts)
        self.assertIn(("--symlink", ("real", str(link))), opts)
        self.assertFalse([o for o in opts if str(absent) in o[1]])


if __name__ == "__main__":
    unittest.main()
