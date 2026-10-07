"""Opt-in confinement of the client's model sessions on Linux (V2.1, REPORT F; docs/v2.1/SANDBOX-LINUX.md).

    "confinement": {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "none" | "host", "read_only": ["/abs", ...]}

Each model session (the developer's, the model reviewer's) runs under bubblewrap: user, PID, IPC, UTS, mount (and with
network "none" network) namespaces of its own; no capability; no_new_privs; no further user namespace; killed with
its parent; and since the client is not PID 1 of its namespace, every process it leaves — a `setsid` one too — is
killed with the namespace when the client exits. It sees the system read-only (/usr, /etc and the library links), its
workspace read-write, read-only the client's directory, the workspace's git directory, the client's configuration
directory and the operator's `read_only` paths — nothing else of the machine: not the run directory, not the kernel,
not HOME (an empty tmpfs). Network "host" shares the host's network: the record says so; egress is then NOT confined.

A run that asks for confinement measures it before its first provider request (`measure`): the same wrapper runs a
shell that tries what it must not be able to do and reports what it sees; anything not as required refuses the run.
Not confined here: the kernel's own execution of the developer's tests, the probes' execution of the candidate, and
Open Code Review — they run as the operator's user."""

from __future__ import annotations

import hashlib
import os
import pathlib
import secrets
import subprocess
import sys
import sysconfig
from typing import Mapping

KEYS = ("backend", "bwrap", "network", "read_only")
NETWORKS = ("none", "host")
HOME = "/aisef-home"
#: the system a client needs, read-only: a link (merged /usr) stays a link
SYSTEM = ("/usr", "/etc", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32")
MARK = "@@aisef-confine "
#: what the measurement runs inside the wrapper: $1 canary (its CONTENT is the secret token, so its leak is seen even
#: though a denial may echo a file's path), $2 run-directory file, $3 kernel file, $4 site-packages file, $5 the
#: operator's HOME, $6 workspace file, $7 a sleep duration no other process has. The probe-file paths carry a nonce,
#: never the token, so a "cannot create <path>" message can never look like a canary leak.
PROBE = r'''m() { printf '@@aisef-confine %s\n' "$*"; }
m uid "$(id -u)"
for n in user pid net ipc uts mnt; do m ns "$n" "$(readlink /proc/self/ns/$n 2>&1)"; done
m section status; cat /proc/self/status 2>&1
m section mountinfo; cat /proc/self/mountinfo 2>&1
m section route; cat /proc/net/route 2>&1
m section netdev; cat /proc/net/dev 2>&1
m section home; if [ -e "$5" ]; then ls -A -- "$5" 2>&1; fi
m try read_canary; cat -- "$1" 2>&1; m rc $?
m try write_run_directory; (: > "$2") 2>&1; m rc $?
m try write_kernel; (: > "$3") 2>&1; m rc $?
m try write_interpreter_site; (: > "$4") 2>&1; m rc $?
m try workspace; (echo ok > "$6" && cat -- "$6" && rm -f -- "$6") 2>&1; m rc $?
m try user_namespace
if command -v unshare >/dev/null 2>&1; then unshare --user true 2>&1; m rc $?; else echo "unshare: absent"; m rc 127; fi
m try setsid
if command -v setsid >/dev/null 2>&1; then setsid sleep "$7" </dev/null >/dev/null 2>&1 & else (sleep "$7" </dev/null >/dev/null 2>&1 &); fi
m rc 0
m end
'''


class Unavailable(Exception):
    """Confinement was asked for and cannot be given: nothing starts."""


def problem(spec) -> str | None:
    """Why `spec` is not a confinement setting, or None."""
    if not isinstance(spec, Mapping) or sorted(spec) != sorted(KEYS):
        return f"confinement is {{{', '.join(KEYS)}}}"
    if spec["backend"] != "bwrap":
        return "confinement.backend is bwrap (the only backend)"
    if not isinstance(spec["bwrap"], str) or not spec["bwrap"].startswith("/"):
        return "confinement.bwrap is the absolute path of bubblewrap"
    if spec["network"] not in NETWORKS:
        return f"confinement.network is one of {list(NETWORKS)}"
    ro = spec["read_only"]
    if not isinstance(ro, list) or not all(isinstance(p, str) and p.startswith("/") for p in ro):
        return "confinement.read_only is a list of absolute paths"
    return None


def git_dir(workspace: str) -> str | None:
    """The common git directory of a worktree checkout (its `.git` is a file naming the worktree's own directory,
    which lies inside the common one), or None: a plain checkout's `.git` is inside the workspace already."""
    gitfile = pathlib.Path(workspace, ".git")
    if not gitfile.is_file():
        return None
    text = gitfile.read_text(encoding="utf-8", errors="replace").strip()
    if not text.startswith("gitdir: "):
        return None
    own = pathlib.Path(workspace, text[len("gitdir: "):]).resolve()
    common = own / "commondir"
    return str((own / common.read_text(encoding="utf-8").strip()).resolve() if common.is_file() else own)


def config_dir(env: Mapping[str, str]) -> tuple[str | None, str | None]:
    """(XDG_CONFIG_HOME, the client's configuration directory) as app.client.configured_provider resolves them."""
    base = env.get("XDG_CONFIG_HOME") or (os.path.join(env["HOME"], ".config") if env.get("HOME") else None)
    d = os.path.join(base, "opencode") if base else None
    return base, (d if d and os.path.isdir(d) else None)


def argv(spec: Mapping, command: list[str], workspace: str, read_only: list[str]) -> list[str]:
    """The bubblewrap command line: namespaces, privileges, the system read-only, `read_only`, the workspace last
    (read-write, even below a read-only path), the command in the workspace."""
    a = [spec["bwrap"], "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup-try",
         *(["--unshare-net"] if spec["network"] == "none" else ["--share-net"]),
         "--disable-userns", "--die-with-parent", "--new-session", "--cap-drop", "ALL"]
    for p in SYSTEM:
        if os.path.islink(p):
            a += ["--symlink", os.readlink(p), p]
        elif os.path.isdir(p):
            a += ["--ro-bind", p, p]
    a += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", HOME]
    for p in dict.fromkeys(read_only):
        a += ["--ro-bind", p, p]
    return [*a, "--bind", workspace, workspace, "--chdir", workspace, "--", *command]


def wrap(spec: Mapping, command: list[str], env: Mapping[str, str], workspace: str, exe: str | None = None,
         system: str = sys.platform) -> tuple[list[str], dict]:
    """(argv, env) of `command` confined to `workspace`; Unavailable when this host cannot confine (fail closed)."""
    if not system.startswith("linux"):
        raise Unavailable(f"confinement is Linux-only (bubblewrap); this host is {system}: no backend")
    if not os.access(spec["bwrap"], os.X_OK):
        raise Unavailable(f"bubblewrap is not an executable at {spec['bwrap']}")
    missing = [p for p in spec["read_only"] if not os.path.exists(p)]
    if missing:
        raise Unavailable(f"confinement.read_only names paths that do not exist: {missing}")
    base, cfg = config_dir(env)
    ro = [*([os.path.dirname(os.path.realpath(exe))] if exe else []), *filter(None, [git_dir(workspace), cfg]),
          *spec["read_only"]]
    inside = {k: v for k, v in env.items() if k not in ("USERPROFILE", "TEMP", "TMP")}
    inside.update(HOME=HOME, TMPDIR="/tmp", XDG_DATA_HOME=f"{HOME}/.local/share", XDG_STATE_HOME=f"{HOME}/.local/state",
                  XDG_CACHE_HOME=f"{HOME}/.cache", XDG_CONFIG_HOME=base if cfg else f"{HOME}/.config")
    return argv(spec, command, workspace, ro), inside


def _sections(out: str) -> tuple[dict, dict, dict]:
    """The probe's output: its single values, its sections, its tries {name: (rc, output)}."""
    values, sections, tries, cur, name = {}, {}, {}, None, None
    for line in out.splitlines():
        if not line.startswith(MARK):
            if cur is not None:
                cur.append(line)
            continue
        word, _, rest = line[len(MARK):].partition(" ")
        if word == "section":
            cur = sections.setdefault(rest, [])
        elif word == "try":
            cur = tries.setdefault(rest, [])
            name = rest
        elif word == "rc" and name in tries:
            tries[name] = (int(rest), "\n".join(tries[name]).strip()[:300])
            cur = None
        elif word == "ns":
            n, _, v = rest.partition(" ")
            values.setdefault("ns", {})[n] = v
            cur = None
        else:
            values[word] = rest
            cur = None
    return values, sections, tries


def _mounts(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        left, sep, right = line.partition(" - ")
        f, r = left.split(), right.split()
        if sep and len(f) >= 6 and r:
            out.append({"at": f[4], "access": "ro" if "ro" in f[5].split(",") else "rw", "fs": r[0]})
    return out


def measure(spec: Mapping, where: pathlib.Path, system: str = sys.platform, environ: Mapping[str, str] | None = None) -> dict:
    """Run the probe under the very wrapper the sessions get, with `where` (a new directory in the run directory) as
    the run directory and `where/ws` as the workspace: what it saw, what it was denied, and the problems — any one
    refuses the run."""
    environ = dict(os.environ if environ is None else environ)
    rep: dict = {"backend": spec["backend"], "bwrap": spec["bwrap"], "network": spec["network"],
                 "read_only": list(spec["read_only"]), "system": system, "operator_uid": os.getuid() if hasattr(os, "getuid") else None}
    env = {k: environ[k] for k in ("PATH", "HOME", "XDG_CONFIG_HOME", "LANG") if k in environ}
    ws = where / "ws"
    try:
        ws.mkdir(parents=True)
        cmd = ["/bin/sh", "-c", PROBE, "probe"]
        full, inside_env = wrap(spec, cmd, env, str(ws), system=system)
    except Unavailable as e:
        return {**rep, "problems": [str(e)]}
    exe = pathlib.Path(spec["bwrap"])
    rep["bwrap_sha256"] = hashlib.sha256(exe.read_bytes()).hexdigest()
    try:
        rep["bwrap_version"] = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        rep["bwrap_version"] = f"unavailable: {type(e).__name__}"
    token, nonce = secrets.token_hex(16), secrets.token_hex(8)   # token: only the canary's content; nonce: the file paths
    canary, written = where / "canary", where / f"written-{nonce}"
    canary.write_text(token + "\n", encoding="utf-8")
    kernel = pathlib.Path(__file__).resolve().parents[1] / f".aisef-confine-probe-{nonce}"
    site = pathlib.Path(sysconfig.get_paths()["purelib"]) / f".aisef-confine-probe-{nonce}"
    home = env.get("HOME") or "/nonexistent"
    sleep = f"30.{int(nonce, 16) % 10**6:06d}"
    args = [str(canary), str(written), str(kernel), str(site), home, str(ws / ".aisef-confine-probe"), sleep]
    rep["argv"] = full[:-len(cmd)] + ["/bin/sh", "-c", "<PROBE>", "probe"]
    try:
        p = subprocess.run(full + args, capture_output=True, text=True, env=inside_env, timeout=60)
        code, out = p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        code, out = None, f"{type(e).__name__}: {e}"
    from aisef2.runtime.process_range import process_table
    survivors = [pr.pid for pr in process_table().values() if f"sleep {sleep}" in pr.command]
    created = {name: p.exists() for name, p in (("run_directory", written), ("kernel", kernel), ("interpreter_site", site))}
    for p in (written, kernel, site):     # the probe's own empty files, if confinement failed to stop them
        if p.exists():
            p.unlink()
    values, sections, tries = _sections(out)
    problems = []
    if code != 0 or "end" not in values:
        problems.append(f"the sandbox did not run the probe (exit {code}): {out.strip()[:300]}")
    status = dict(line.split(":", 1) for line in sections.get("status", []) if ":" in line)
    status = {k: v.strip() for k, v in status.items()}
    caps = {k: status.get(k) for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")}
    mounts = _mounts(sections.get("mountinfo", []))
    netdev = [ln.split(":", 1)[0].strip() for ln in sections.get("netdev", [])[2:] if ":" in ln]
    # /proc/net/route rows after the header: an interface with a route. A fresh netns (--unshare-net) has none, even
    # though this kernel pre-creates DOWN tunnel pseudo-devices, so routes — not interface names — show reachability.
    routes = [ln.split("\t")[0] for ln in sections.get("route", [])[1:] if "\t" in ln]
    outside_ns = {n: (os.readlink(f"/proc/self/ns/{n}") if os.path.exists(f"/proc/self/ns/{n}") else None)
                  for n in values.get("ns", {})}
    rep["inside"] = {"uid": values.get("uid"), "capabilities": caps, "no_new_privs": status.get("NoNewPrivs"),
                     "seccomp": status.get("Seccomp"), "network_interfaces": netdev, "routed_interfaces": sorted(set(routes)),
                     "mounts": mounts,
                     "namespaces": {n: ("own" if v != outside_ns.get(n) else "shared") for n, v in values.get("ns", {}).items()},
                     "home_listing": sections.get("home", [])}
    rep["tried"] = {k: {"exit": rc, "output": o} for k, (rc, o) in tries.items()}
    rep["created_outside_workspace"] = created
    rep["setsid_survivors"] = survivors
    rep["operator_can"] = {"write_kernel": os.access(kernel.parent, os.W_OK), "write_interpreter_site": os.access(site.parent, os.W_OK)}
    if not problems:
        problems += _judge(rep, token, out, tries, values, home, ws)
    rep["problems"] = problems
    return rep


def _judge(rep: dict, token: str, out: str, tries: dict, values: dict, home: str, ws: pathlib.Path) -> list[str]:
    """What the measurement shows that confinement must not allow."""
    inside, bad = rep["inside"], []
    if token in out or tries.get("read_canary", (0,))[0] == 0:
        bad.append("a file of the run directory was readable")
    bad += [f"a file was created in the {k.replace('_', ' ')}" for k, v in rep["created_outside_workspace"].items() if v]
    if tries.get("workspace", (1, ""))[0] != 0 or "ok" not in tries.get("workspace", (1, ""))[1]:
        bad.append("the workspace was not writable")
    if tries.get("user_namespace", (1,))[0] == 0:
        bad.append("a user namespace could be created")
    if rep["setsid_survivors"]:
        bad.append(f"a process the session left outlived it: {rep['setsid_survivors']}")
    for k in ("CapInh", "CapPrm", "CapEff", "CapAmb"):
        if inside["capabilities"][k] is None or int(inside["capabilities"][k], 16) != 0:
            bad.append(f"{k} is {inside['capabilities'][k]}, not 0")
    if inside["no_new_privs"] != "1":
        bad.append(f"NoNewPrivs is {inside['no_new_privs']}, not 1")
    need = ("user", "pid", "ipc", "uts", "mnt", *(("net",) if rep["network"] == "none" else ()))
    bad += [f"the {n} namespace is not the session's own" for n in need if inside["namespaces"].get(n) != "own"]
    if rep["network"] == "none" and inside["routed_interfaces"]:
        bad.append(f"network none has routes on {inside['routed_interfaces']} (a reachable network)")
    host_backed = [m for m in inside["mounts"] if m["access"] == "rw" and m["fs"] not in ("tmpfs", "proc", "devpts", "mqueue")
                   and not m["at"].startswith("/dev/") and m["at"] != str(ws)]
    if host_backed:
        bad.append(f"writable outside the workspace: {[m['at'] for m in host_backed]}")
    names = {pathlib.PurePosixPath(m["at"]).relative_to(home).parts[0] for m in inside["mounts"]
             if pathlib.PurePosixPath(m["at"]).is_relative_to(home) and m["at"] != home}
    shown = set(inside["home_listing"])
    if home != "/nonexistent" and not shown <= names:
        bad.append(f"HOME shows more than the way to what is mounted: {sorted(shown - names)[:10]}")
    if not inside["mounts"]:
        bad.append("the mounts could not be read")
    return bad
