"""The scripted client of the Linux-guest end-to-end run (e2e_guest.py): the developer and the model reviewer, one
script for every scenario. e2e_guest.py puts it on PATH as `opencode`, in a directory of its own next to
scenario.json, and the script does what scenario.json says. It calls no provider and no network, and it signals
nothing (INV-MUTATION-AUTHORITY): it only starts children, tries paths, and says what the operating system answered.

Every observation is an `e2e_observation` event on its stdout. That stream is the session's evidence (EVIDENCE.json
binds it), which is where the driver reads the observations from — nothing is passed back out of band.

scenario.json: {"attempts": [[name, "create"|"read", path], ...]   `{cwd}` is this session's --dir, `{home}` its HOME
                "reviewer_attempts": same, tried by the reviewer's session instead of `attempts`
                "children": marker or null    start a background child (with a grandchild that ignores SIGINT and
                                              SIGTERM) and a setsid child, every argv ending with the marker
                "linger_s": n                 keep them running n seconds before going on (so a 20 ms look sees them)
                "legit": bool                 the developer implements the story in its workspace
                "hang_s": n                   after everything else, sleep n seconds (past the session's timeout)}"""
import errno
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-e2e-scripted")
    raise SystemExit(0)
S = json.loads(pathlib.Path(__file__).with_name("scenario.json").read_text(encoding="utf-8"))
title, cwd = argv[argv.index("--title") + 1], argv[argv.index("--dir") + 1]
role = title.split()[0]      # "developer" | "reviewer"


def say(event: dict) -> None:
    print(json.dumps(event), flush=True)


def see(name: str, **kw) -> None:
    say({"type": "e2e_observation", "name": name, "role": role, **kw})


def mounts() -> list[list[str]]:
    rows = []
    for line in pathlib.Path("/proc/self/mountinfo").read_text(encoding="utf-8", errors="replace").splitlines():
        left, _, right = line.partition(" - ")
        f, r = left.split(), right.split()
        if len(f) >= 6 and r:
            rows.append([f[4], r[0], "ro" if "ro" in f[5].split(",") else "rw"])
    return rows


def holder(path: str, rows: list[list[str]]) -> list[str] | None:
    """The mount a path lives on: the longest mount point that is the path or a prefix of it."""
    under = [m for m in rows if path == m[0] or path.startswith(m[0].rstrip("/") + "/")]
    return max(under, key=lambda m: len(m[0])) if under else None


def cmdline(pid: str) -> list[str] | None:
    try:
        return pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace").split("\0")[:-1]
    except OSError:
        return None


def comm(pid: str) -> str | None:
    try:
        return pathlib.Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def stat_fields(pid: str) -> list[str]:
    """state, ppid, pgrp, session of /proc/<pid>/stat (the fields after the command name)."""
    try:
        return pathlib.Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[:4]
    except (OSError, IndexError):
        return []


def status() -> dict:
    keep = ("Uid", "Gid", "NoNewPrivs", "Seccomp", "CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    text = pathlib.Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    rows = (ln.split(":", 1) for ln in text.splitlines() if ":" in ln)
    return {k: v.split()[0] for k, v in rows if k in keep}


def attempt(name: str, op: str, path: str, rows: list[list[str]]) -> None:
    """Create `path` exclusively (never an existing file: nothing is overwritten) or read it, and report the answer."""
    try:
        if op == "create":
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.write(fd, b"e2e probe\n")
            os.close(fd)
            see(name, op=op, path=path, ok=True, errno=0, mount=holder(path, mounts()))
        else:
            data = pathlib.Path(path).read_bytes()
            see(name, op=op, path=path, ok=True, errno=0, sha256=hashlib.sha256(data).hexdigest(), size=len(data))
    except OSError as e:
        see(name, op=op, path=path, ok=False, errno=e.errno, errname=errno.errorcode.get(e.errno), strerror=e.strerror)


def spawn_children(marker: str) -> None:
    py = sys.executable
    ignore = ("import signal, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\n"
              "signal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(300)")
    parent = ("import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])\n"
              "time.sleep(300)")
    kids = {
        "background": subprocess.Popen([py, "-c", parent, ignore, marker + "-grandchild", marker + "-background"]),
        "setsid": subprocess.Popen([py, "-c", "import time; time.sleep(300)", marker + "-setsid"],
                                   start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL),
    }
    deadline, found = time.monotonic() + 5.0, {}
    while time.monotonic() < deadline and len(found) < 3:     # each child has exec'd once its argv shows the marker
        for p in (q for q in os.listdir("/proc") if q.isdigit()):
            for tag in ("-background", "-grandchild", "-setsid"):
                if (cmdline(p) or [""])[-1] == marker + tag:
                    st = stat_fields(p)
                    found[tag[1:]] = {"pid": int(p), "state": st[0], "ppid": int(st[1]), "sid": int(st[3])}
        time.sleep(0.02)
    see("children", marker=marker, started={k: v.pid for k, v in kids.items()}, alive=found, my_pid=os.getpid(),
        my_sid=os.getsid(0))


rows = mounts()
see("self", argv=sys.argv, cwd=cwd, pid=os.getpid(), ppid=os.getppid(), uid=os.getuid(), gid=os.getgid(), groups=os.getgroups(),
    status=status(), pid1_comm=comm("1"), pid1_cmdline=cmdline("1"),
    ns={n: os.readlink(f"/proc/self/ns/{n}") for n in ("user", "pid", "net", "ipc", "uts", "mnt")},
    home=os.environ.get("HOME"), home_listing=sorted(os.listdir(os.environ["HOME"])) if os.path.isdir(
        os.environ.get("HOME", "")) else None, env_names=sorted(os.environ), mounts=rows, workspace_mount=holder(cwd, rows))
for name, op, path in S["reviewer_attempts"] if role == "reviewer" else S["attempts"]:
    attempt(name, op, path.format(cwd=cwd, home=os.environ.get("HOME", "")), rows)

if role == "developer":
    if S["children"]:
        spawn_children(S["children"])
        time.sleep(S["linger_s"])
    if S["legit"]:     # the story's implementation: in the workspace, as the developer is meant to
        root = pathlib.Path(cwd)
        (root / "app" / "cli.py").write_text("def main(args):\n    if len(args) != 2:\n        return 2\n"
                                             "    return int(args[0]) + int(args[1])\n")
        (root / "app" / "__main__.py").write_text("import sys\n\nfrom app.cli import main\n\nsys.exit(main(sys.argv[1:]))\n")
        (root / "tests").mkdir(exist_ok=True)
        (root / "tests" / "__init__.py").write_text("")
        (root / "tests" / "test_cli.py").write_text(
            "import unittest\n\nfrom app.cli import main\n\n\nclass T(unittest.TestCase):\n    def test_sum(self):\n"
            "        self.assertEqual(main(['2', '3']), 5)\n\n    def test_usage(self):\n"
            "        self.assertEqual(main([]), 2)\n")
        see("work", written=["app/cli.py", "app/__main__.py", "tests/__init__.py", "tests/test_cli.py"])
    say({"type": "text", "part": {"text": "done"}})
else:
    say({"type": "text", "part": {"text": json.dumps({"findings": []})}})
say({"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3, "cache": {"read": 10, "write": 0}}}})
if role == "developer" and S["hang_s"]:
    time.sleep(S["hang_s"])
