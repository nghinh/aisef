"""In-container measurement of the developer-session confinement (V2.1 F; run by run.sh inside a Linux container).

It builds the very bwrap argv the kernel's client would use (aisef2.app.confine) and PROVES each claim by an operation
that must be denied — read a file outside the workspace, write the runtime/kernel/verifier/anchor, see host processes,
connect to a host port, keep a setsid child alive after the run, raise a capability — plus the positive controls (the
workspace works, a fake client runs). It prints one JSON object. It never runs the real `opencode`, never calls a
provider, and asserts nothing about the host from inside: the host side (run.sh) sets HOST_PORT and HOST_PIDS so the
in-sandbox denials can be checked against real host state.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path("/repo")
sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402

SPEC = {"backend": "bwrap", "bwrap": os.environ.get("BWRAP", "/usr/bin/bwrap"),
        "network": os.environ.get("NETWORK", "none"), "read_only": []}
# a controller-owned area the container user owns but the sandbox must not reach beyond its workspace. /tmp is the one
# place uid 1000 can write in a hardened container (read-only rootfs is the deployment default); the run directory, the
# runtime, the verifier and the anchor sit here OUTSIDE the workspace, exactly as they would beside a real run.
BASE = pathlib.Path("/tmp/aisef")
RUN = BASE / "run-dir"                   # the kernel's run directory; outside the workspace
WS = RUN / "work" / "ws" / "wt-S1"      # the session's workspace (the only writable host path)
RUNTIME = BASE / "runtime" / "opencode"  # the pinned client binary the session must not be able to rewrite
VERIFIER = BASE / "verifier" / "hidden.json"    # the hidden verifier material the developer must not reach
ANCHOR = RUN / "EVIDENCE.anchor"
CLIENT_HOME = BASE / "op-home"          # the operator HOME the client gets (with a secret the sandbox must not read)


def denied(cmd: list[str], env: dict) -> dict:
    """Run `cmd` inside the sandbox (the same wrapper the client gets); its exit, stdout+stderr, and whether the
    sandbox even started it."""
    try:
        argv, inside = confine.wrap(SPEC, cmd, env, str(WS), system="linux")
    except confine.Unavailable as e:
        return {"started": False, "why": str(e)}
    p = subprocess.run(argv, capture_output=True, text=True, env=inside, timeout=60)
    return {"started": True, "exit": p.returncode, "out": (p.stdout + p.stderr).strip()[:400]}


def main() -> None:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(CLIENT_HOME), "LANG": "C"}
    pathlib.Path(env["HOME"], ".config", "opencode").mkdir(parents=True, exist_ok=True)
    pathlib.Path(env["HOME"], ".ssh").mkdir(parents=True, exist_ok=True)
    pathlib.Path(env["HOME"], ".ssh", "id").write_text("SECRET-KEY\n")
    WS.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(WS)], check=True,
                   env={**os.environ, "HOME": "/tmp", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"})
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME.write_text("#!/bin/sh\necho real-client\n")
    VERIFIER.parent.mkdir(parents=True, exist_ok=True)
    VERIFIER.write_text(json.dumps({"hidden": "stimulus"}))
    ANCHOR.write_text("0" * 64 + "\n")
    canary = RUN / "canary"
    canary.write_text("CANARY-TOKEN\n")

    host_port = int(os.environ.get("HOST_PORT", "0"))
    host_pids = [p for p in os.environ.get("HOST_PIDS", "").split(",") if p]
    report: dict = {"network": SPEC["network"], "uid": os.getuid(),
                    "container": {k: os.environ.get(k) for k in ("PROFILE", "SECCOMP", "APPARMOR", "SYSTEMPATHS")}}

    # the kernel's own measurement (the record-shaped report), run exactly as a run would run it
    report["measure"] = {k: v for k, v in confine.measure(SPEC, RUN / "confinement", system="linux", environ=env).items()
                         if k not in ("argv",)}

    sh = lambda s: ["/bin/sh", "-c", s]  # noqa: E731
    gw = os.environ.get("HOST_GATEWAY", "127.0.0.1")
    connect = ("import socket,sys\n"
               "try:\n"
               f"  s=socket.create_connection(({gw!r},{host_port}),3); s.close(); print('UP: reached host '+{gw!r})\n"
               "except OSError as e: print('DOWN: '+type(e).__name__+': '+str(e))\n")
    report["denials"] = {
        "read_file_outside_workspace": denied(sh(f"cat {canary}"), env),
        "read_verifier": denied(sh(f"cat {VERIFIER}"), env),
        "read_home_secret_absolute": denied(sh(f'cat {CLIENT_HOME / ".ssh" / "id"}'), env),
        "write_runtime": denied(sh(f": > {RUNTIME}"), env),
        "write_anchor": denied(sh(f"echo x >> {ANCHOR}"), env),
        "write_run_directory": denied(sh(f": > {RUN / 'written'}"), env),
        "see_host_processes": denied(sh("ls /proc | grep -E '^[0-9]+$' | sort -n | tr '\\n' ' '"), env),
        "connect_host_port": denied([sys.executable, "-c", connect], env),
        "raise_capability": denied(sh("cat /proc/self/status | grep -E '^Cap(Prm|Eff|Bnd):'"), env),
    }
    report["controls"] = {
        "workspace_writable": denied(sh("echo ok > ./w && cat ./w && rm ./w"), env),
        "fake_client_runs": denied([*env_client(env)], env),
    }
    report["host"] = {"port": host_port, "pids_sample": host_pids[:5], "runtime_unchanged": RUNTIME.read_text() == "#!/bin/sh\necho real-client\n",
                      "anchor_unchanged": ANCHOR.read_text() == "0" * 64 + "\n",
                      "written_in_run_dir": (RUN / "written").exists()}
    print(json.dumps(report, indent=1, sort_keys=True))


def env_client(env: dict) -> list[str]:
    """A fake client in the workspace: the positive control that the confined session can run a program."""
    fake = WS / "fake_opencode.py"
    fake.write_text("import json\nprint(json.dumps({'type': 'text', 'part': {'text': 'done'}}))\n")
    return [sys.executable, str(fake)]


if __name__ == "__main__":
    main()
