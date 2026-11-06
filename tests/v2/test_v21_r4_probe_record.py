"""B-03 round 4 — the measurement's report is the record: what `measure` refused with is what its `tried` says.

Two requirements of `confine.measure`'s report, stated through the real `_probe`:

1. A check that RAN is recorded with the status it ran with. A readable canary (a breach) is `read_canary` exit 0, the
   refusal says "a file of the run directory was readable", and no problem says of a check that read the file that it
   "did not run". The canary file the harness writes ends with a line feed so that the probe's status marker is at the
   start of a line; without it the marker is glued to the token and the breach is recorded as a try that never
   reported — a false first line of the refusal (RUN.json `failure.detail`, `--check`) and a record whose re-judgement
   (the suite's replay: `_judge` over `tried` alone) loses the finding.
2. What a run was refused with is what its record says when judged again: RUN.json serialises the report with sorted
   keys, and the problem that names the checks that did not run names them in one order for both.

Campaign 6 left `_probe` [109] (the canary's newline emptied) and `_judge` [45] (`sorted()` -> `list()`) SURVIVED, with
audits "the run is refused either way". Two independent skeptics refuted that: the status and the first words of the
refusal are read (the replay readers, run.sh, the operator), and no test pinned them. The first test runs the REAL probe
script through /bin/sh with every path it writes redirected into the test's own directory (INV-MUTATION-AUTHORITY: by
construction, nothing outside it can be written)."""

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

M = confine.MARK
DID_NOT_RUN = "reported no exit status: the check did not run"
READABLE = "a file of the run directory was readable"


def measured(answer):
    """(report, home, workspace) of `confine.measure` through the real `_probe`; `answer(at, tmp)` is the probe's stdout
    (`at` = the probe's arguments after PROBE: "probe", $1..$9, the targets)."""
    real = subprocess.run
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(os.path.realpath(t))
        home = tmp / "home"
        (home / ".config" / "opencode").mkdir(parents=True)
        exe = tmp / "client" / "opencode"
        exe.parent.mkdir()
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        bwrap = tmp / "bwrap"
        bwrap.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
        bwrap.chmod(0o755)
        spec = {"backend": "bwrap", "bwrap": str(bwrap), "network": "host", "read_only": []}
        environ = {"PATH": "/usr/bin:/bin", "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}

        def run(argv, *a, **k):
            if isinstance(argv, list) and argv[:1] == [str(bwrap)]:
                out = "bubblewrap 0.12.0\n" if argv[1:] == ["--version"] else answer(argv[argv.index(confine.PROBE) + 1:], tmp)
                return subprocess.CompletedProcess(argv, 0, out, "")
            return real(argv, *a, **k)
        with mock.patch.object(subprocess, "run", run):
            rep = confine.measure(spec, tmp / "run" / "confinement", str(exe), system="linux", environ=environ)
        return rep, str(home), tmp / "run" / "confinement" / "ws"


def replayed(rep, home, ws):
    """The report as RUN.json writes it (sorted keys), judged again from its `tried` alone."""
    rec = json.loads(json.dumps(rep, sort_keys=True))
    return confine._judge(rec, "tok", "", {k: (v["exit"], v["output"]) for k, v in rec["tried"].items()}, home, ws)


class TheReportIsTheRecord(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "the probe is a POSIX shell script")
    def test_a_readable_canary_is_recorded_as_read_and_is_not_a_check_that_did_not_run(self):
        def answer(at, tmp):      # the REAL probe, canary readable, every write redirected into the test's directory
            sink = tmp / "sink"
            sink.mkdir(exist_ok=True)
            args = [at[1], *(str(sink / n) for n in ("a", "b", "c")), at[5], str(sink / "d"), "0.01", str(sink / "e"),
                    str(sink / "f"), str(sink)]
            # timeout guards the harness's own real-probe subprocess; it is not the oracle. A saturated CI runner (a
            # 54-min suite was observed on ubuntu-3.12) can push the probe past a tight budget, and a timed-out probe
            # yields NO finding — indistinguishable from the campaign-6 bug this test pins — so the assertion below
            # would read a flake as a regression. Generous budget so the probe always reports; the oracle is unchanged.
            return subprocess.run(["/bin/sh", "-c", confine.PROBE, "probe", *args], capture_output=True, text=True,
                                  encoding="utf-8", timeout=300, check=False).stdout
        rep, home, ws = measured(answer)
        self.assertEqual(rep["tried"]["read_canary"]["exit"], 0)
        self.assertIn(READABLE, rep["problems"])
        self.assertFalse(any(DID_NOT_RUN in p for p in rep["problems"]), rep["problems"])
        self.assertIn(READABLE, replayed(rep, home, ws))

    @unittest.skipUnless(os.name == "posix", "confine.measure's host-side machinery (the ps scan, the POSIX PATH) is POSIX")
    def test_what_a_run_refused_with_is_what_its_record_says_when_judged_again(self):
        # two tries that never reported, in the probe's order (workspace, then user_namespace), not the alphabetical one
        out = "\n".join([f"{M}try read_canary", "cat: canary: No such file or directory", f"{M}rc 1",
                         f"{M}try read_git_directory", "ref: refs/heads/main", f"{M}rc 0",
                         f"{M}try workspace", f"ok{M}rc 0",
                         f"{M}try user_namespace", f"unshare failed: Operation not permitted{M}rc 1", f"{M}end"]) + "\n"
        rep, home, ws = measured(lambda at, tmp: out)
        live = [p for p in rep["problems"] if DID_NOT_RUN in p]
        self.assertEqual(len(live), 1, rep["problems"])
        self.assertEqual([p for p in replayed(rep, home, ws) if DID_NOT_RUN in p], live)

    def test_the_record_alone_is_judged_as_the_run_was_without_any_host_machinery(self):
        """The replay half of the test above, portable: `_judge` over the report as RUN.json serialises it (sorted
        keys, so `tried` comes back alphabetical) refuses with the very problems the live judgement over the probe's
        own order (workspace before user_namespace) refused with — `sorted()` inside `_judge`, not the dict's order,
        is what makes the two readings one record. No measure, no shell, no ps: the report is built here."""
        tried = {"read_canary": (1, "cat: canary: No such file or directory"),
                 "read_git_directory": (0, "ref: refs/heads/main"),
                 "workspace": (None, "ok"),
                 "user_namespace": (None, "unshare failed: Operation not permitted")}
        rep = {"network": "host", "setsid_survivors": [], "created_outside_workspace": {},
               "tried": {k: {"exit": rc, "output": said} for k, (rc, said) in tried.items()},
               "inside": {"mounts": [], "mount_targets": [], "home_listing": [], "unix_sockets": [],
                          "routed_interfaces": [], "no_new_privs": "1",
                          "namespaces": {n: "own" for n in ("user", "pid", "ipc", "uts", "mnt")},
                          "capabilities": {k: "0" for k in ("CapInh", "CapPrm", "CapEff", "CapAmb")}}}
        live = confine._judge(rep, "tok", "", tried, "/nonexistent", pathlib.PurePosixPath("/ws"))
        self.assertEqual([p for p in live if DID_NOT_RUN in p],
                         [f"the probe's user_namespace, workspace {DID_NOT_RUN}"])
        self.assertEqual(replayed(rep, "/nonexistent", pathlib.PurePosixPath("/ws")), live)


if __name__ == "__main__":
    unittest.main()
