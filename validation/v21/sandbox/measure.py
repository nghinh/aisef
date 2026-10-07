"""In-container measurement of the model-session confinement (V2.1 F; run by run.sh inside a Linux container).

The layout is a run's: the kernel installed in a venv (the operator's `read_only`), the client in a directory of its
own (`runtime/`), the run directory with its repository and a session worktree of it, the operator's HOME with a key
and the client's auth data, a hidden verifier file. Every operation runs under the command line a session gets —
`aisef2.app.confine.wrap` with the client and the worktree, as `client.session` calls it — and the kernel's own
`confine.measure` runs as `run.execute` calls it. Each row records the operation and what happened:

  denials    the operation FAILED inside the sandbox (its error is recorded);
  network    a host port and an abstract unix socket of the container's network namespace: failed under network
             "none", reached under "host" (what a run uses) — recorded, never called a denial;
  observed   what /proc/self/status shows (capabilities, NoNewPrivs, Seccomp) — a reading, not an operation;
  tmpfs_only the operation succeeded, but only into the sandbox's throwaway tmpfs: the real file, checked from
             outside after the run (`after`), is unchanged — not a denial;
  by_design  what a session is meant to reach (read-only), recorded so its extent is visible;
  controls   what must work (the workspace, the client from its own mounted directory).

It prints one JSON object. It never runs the real `opencode` (the client is a shell script), never calls a provider.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import threading

BASE = pathlib.Path("/tmp/aisef")
VENV = BASE / "venv"                     # the kernel "pip-installed" here: an operator read_only path

if sys.prefix == sys.base_prefix:        # first pass (the image's python): build the venv, re-run inside it
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(VENV)], check=True)
    py = str(VENV / "bin" / "python")
    site = subprocess.run([py, "-P", "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                          capture_output=True, text=True, check=True).stdout.strip()
    shutil.copytree("/repo/aisef2", pathlib.Path(site) / "aisef2", ignore=shutil.ignore_patterns("__pycache__"))
    os.execv(py, [py, "-P", __file__])

from aisef2.app import confine  # noqa: E402 — the copy in the venv's site-packages

RUN = BASE / "run-dir"                   # the kernel's run directory; outside the workspace
REPO = RUN / "repo"                      # the run's clone: its .git is read-only inside every session
WS = RUN / "work" / "ws" / "wt-S1"       # a session's workspace: a worktree of REPO, the only writable host path
RUNTIME = BASE / "runtime" / "opencode"  # the client, in a directory of its own (bound read-only)
VERIFIER = BASE / "verifier" / "hidden.json"
ANCHOR = RUN / "EVIDENCE.anchor"
CLIENT_HOME = BASE / "op-home"           # the operator's HOME, with secrets the sandbox must not read
SOCKS = BASE / "sock"                    # a host unix socket outside every mount
NETWORK = os.environ.get("NETWORK", "none")
SPEC = {"backend": "bwrap", "bwrap": os.environ.get("BWRAP", "/usr/bin/bwrap"), "network": NETWORK,
        "read_only": [str(VENV)]}
CLIENT = "#!/bin/sh\necho '{\"type\": \"text\", \"part\": {\"text\": \"done\"}}'\n"
GIT = {"HOME": "/tmp", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin"}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, env=GIT).stdout.strip()


def inside(cmd: list[str], env: dict, spec: dict = SPEC) -> dict:
    """`cmd` under a session's wrapper; its exit and output, or why the sandbox did not start it."""
    try:
        argv, e = confine.wrap(spec, cmd, env, str(WS), str(RUNTIME), system="linux")
    except confine.Unavailable as x:
        return {"started": False, "why": str(x)}
    p = subprocess.run(argv, capture_output=True, text=True, env=e, timeout=60)
    return {"started": True, "exit": p.returncode, "out": (p.stdout + p.stderr).strip()[:400]}


def listen_unix(addr) -> socket.socket:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(addr)
    s.listen(8)

    def serve():
        while True:
            try:
                s.accept()[0].close()
            except OSError:
                return
    threading.Thread(target=serve, daemon=True).start()
    return s


def connect_py(family: str, addr: str) -> list[str]:
    target = f"'\\0' + {addr!r}" if family == "abstract" else repr(addr)
    return ["python3", "-c", "import socket\n"
            "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
            f"try:\n  s.connect({target}); print('CONNECTED')\n"
            "except OSError as e: print('REFUSED: ' + type(e).__name__ + ': ' + str(e))\n"]


def main() -> None:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(CLIENT_HOME), "LANG": "C"}
    (CLIENT_HOME / ".config" / "opencode").mkdir(parents=True)
    (CLIENT_HOME / ".config" / "opencode" / "opencode.json").write_text('{"provider": {}}\n')
    (CLIENT_HOME / ".ssh").mkdir()
    (CLIENT_HOME / ".ssh" / "id").write_text("SECRET-KEY\n")
    (CLIENT_HOME / ".local" / "share" / "opencode").mkdir(parents=True)
    (CLIENT_HOME / ".local" / "share" / "opencode" / "auth.json").write_text('{"provider": "SECRET-AUTH"}\n')
    REPO.mkdir(parents=True)
    git("-C", str(REPO), "init", "-q", "-b", "main")
    git("-C", str(REPO), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    git("-C", str(REPO), "worktree", "add", "-q", "--detach", str(WS))
    RUNTIME.parent.mkdir(parents=True)
    RUNTIME.write_text(CLIENT)
    RUNTIME.chmod(0o755)
    VERIFIER.parent.mkdir(parents=True)
    VERIFIER.write_text(json.dumps({"hidden": "stimulus"}))
    ANCHOR.write_text("0" * 64 + "\n")
    canary = RUN / "canary"
    canary.write_text("CANARY-TOKEN\n")
    kernel_file = pathlib.Path(confine.__file__).resolve().parents[1] / "written-by-session"
    SOCKS.mkdir()
    keep = [listen_unix(str(SOCKS / "ctl")), listen_unix("\0aisef-measure-" + str(os.getpid()))]
    sleeper = subprocess.Popen(["sleep", "987.654"])     # a process of the container, outside the sandbox
    before = {p: p.read_bytes() for p in (RUNTIME, ANCHOR, VERIFIER, REPO / ".git" / "HEAD")}

    report: dict = {"network": NETWORK, "uid": os.getuid(), "spec": SPEC,
                    "container": {k: os.environ.get(k) for k in ("PROFILE", "SECCOMP", "APPARMOR", "SYSTEMPATHS")},
                    "guest": {"uname": " ".join(os.uname()[i] for i in (0, 2, 4)),
                              "apparmor_in_kernel": os.path.exists("/sys/module/apparmor"),
                              "max_user_namespaces": _read("/proc/sys/user/max_user_namespaces")}}
    # the kernel's own measurement, as run.execute calls it: the sessions' client and the run's repository
    report["measure"] = confine.measure(SPEC, RUN / "confinement", str(RUNTIME), REPO, system="linux", environ=env)
    report["session_argv"] = confine.wrap(SPEC, [str(RUNTIME), "run", "<prompt>"], env, str(WS), str(RUNTIME),
                                          system="linux")[0]

    sh = lambda s: ["/bin/sh", "-c", s]  # noqa: E731
    port, gw = int(os.environ.get("HOST_PORT", "0")), os.environ.get("HOST_GATEWAY", "127.0.0.1")
    connect = ("import socket\ntry:\n"
               f"  socket.create_connection(({gw!r},{port}),3).close(); print('UP: reached host '+{gw!r})\n"
               "except OSError as e: print('DOWN: '+type(e).__name__+': '+str(e))\n")
    report["denials"] = {
        "read_run_directory_file": inside(sh(f"cat {canary}"), env),
        "read_verifier": inside(sh(f"cat {VERIFIER}"), env),
        "read_home_ssh_key": inside(sh(f"cat {CLIENT_HOME / '.ssh' / 'id'}"), env),
        "read_client_auth_data": inside(sh(f"cat {CLIENT_HOME / '.local' / 'share' / 'opencode' / 'auth.json'}"), env),
        "write_runtime": inside(sh(f": > {RUNTIME}"), env),
        "write_client_directory": inside(sh(f": > {RUNTIME.parent / 'x'}"), env),
        "write_verifier": inside(sh(f": > {VERIFIER}"), env),
        "write_kernel": inside(sh(f": > {kernel_file}"), env),
        "write_git_directory": inside(sh(f": > {REPO / '.git' / 'HEAD'}"), env),
        # the container's sleeper by its command line (the pattern never matches the probe's own: 98[7]), then the PIDs
        "see_container_process": inside(sh("for f in /proc/[0-9]*/cmdline; do tr '\\0' ' ' < $f; echo; done "
                                           "| grep -c 'sleep 98[7][.]654'; ls /proc | grep -E '^[0-9]+$' | sort -n | tr '\\n' ' '"), env),
        "connect_unmounted_unix_socket": inside(connect_py("path", str(SOCKS / "ctl")), env),
        "new_user_namespace": inside(sh("unshare --user --map-root-user true"), env),
    }
    # reached or not by network: denied with network none, reached with host (a run's) — never called a denial there
    report["network"] = {
        "connect_host_port": inside(["python3", "-c", connect], env),
        "connect_abstract_unix_socket": inside(connect_py("abstract", f"aisef-measure-{os.getpid()}"), env),
    }
    report["observed"] = {
        "capabilities": inside(sh("grep -E '^(Cap(Inh|Prm|Eff|Bnd|Amb)|NoNewPrivs|Seccomp):' /proc/self/status"), env),
    }
    report["tmpfs_only"] = {
        "append_anchor": inside(sh(f"echo x >> {ANCHOR} && cat {ANCHOR}"), env),
        "create_in_run_directory": inside(sh(f": > {RUN / 'written'} && ls {RUN}"), env),
    }
    report["by_design"] = {
        "read_git_directory": inside(sh(f"cat {REPO / '.git' / 'HEAD'}"), env),
        "git_status_in_workspace": inside(sh("git status --porcelain --branch"), env),
        "read_client_configuration": inside(sh(f"ls -A {CLIENT_HOME / '.config' / 'opencode'}"), env),
        "home_listing": inside(sh(f"ls -A {CLIENT_HOME}"), env),
        # a read-only mount does not stop a connect: the same socket, bound in read-only, is reachable — and the
        # kernel's measurement refuses such a setting (its problems are recorded)
        "connect_read_only_mounted_unix_socket": inside(connect_py("path", str(SOCKS / "ctl")), env,
                                                        dict(SPEC, read_only=[str(VENV), str(SOCKS)])),
        "measure_with_a_read_only_mounted_socket": confine.measure(dict(SPEC, read_only=[str(VENV), str(SOCKS)]),
                                                                   RUN / "confinement-sock", str(RUNTIME), REPO,
                                                                   system="linux", environ=env)["problems"],
    }
    report["controls"] = {
        "workspace_writable": inside(sh("echo ok > ./w && cat ./w && rm ./w"), env),
        "client_runs_from_its_mounted_directory": inside([str(RUNTIME), "run", "--format", "json"], env),
    }
    sleeper_outside = any("sleep\x00987.654" in _read(f"/proc/{p}/cmdline") for p in os.listdir("/proc") if p.isdigit())
    sleeper.kill()
    report["after"] = {"unchanged": {str(p): p.read_bytes() == b for p, b in before.items()},
                       "written_in_run_directory": (RUN / "written").exists(),
                       "written_in_kernel": kernel_file.exists(),
                       "written_in_client_directory": (RUNTIME.parent / "x").exists(),
                       "container_sleeper_seen_outside": sleeper_outside,
                       "measure_pid_outside": os.getpid()}
    for s in keep:
        s.close()
    print(json.dumps(report, indent=1, sort_keys=True))


def _read(path: str) -> str:
    try:
        return pathlib.Path(path).read_text(errors="replace").strip()
    except OSError as e:
        return f"unreadable: {type(e).__name__}"


if __name__ == "__main__":
    main()
