"""Opt-in confinement of the client's model sessions on Linux (V2.1, REPORT F; docs/v2.1/SANDBOX-LINUX.md).

    "confinement": {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": ["/abs", ...]}

Each model session the client starts (the developer's, the model reviewer's) runs under bubblewrap: user, PID, IPC, UTS
and mount namespaces of its own; no capability; no_new_privs; no further user namespace; killed with its parent; and
since the client is not PID 1 of its namespace, every process it leaves — a `setsid` one too — is killed with the
namespace when the client exits. It WRITES its workspace and nothing else of the host. It READS, read-only: the system
(/usr, /etc and the library links), the client's own directory, the workspace's common git directory — for a run's
worktree that is <out>/repo/.git, inside the run directory: the run's clone, every object and ref of it — the client's
configuration directory and the operator's `read_only` paths; nothing else of the machine: not the rest of the run
directory, not HOME (an empty tmpfs), not the kernel or an interpreter unless it lies under the system paths (an
interpreter in /usr or /usr/local is readable) or a `read_only` path. A client whose directory holds HOME or the
workspace is refused (bound read-only, the directory would expose them). The model reviewer's session gets the same
wrapper with its workspace — the checkout it reviews — bound read-only too (`writable=False`): it writes nothing of
the host.

Network: a run uses "host": the session shares the host's network so that it reaches its provider, and egress is NOT
confined (the record says so). "none" (a network namespace of its own: a fresh loopback, no route) leaves a session no
way to its provider: a measurement-only profile (validation/v21/sandbox), refused in run settings.

A run that asks for confinement measures it before its first provider request (`measure`): the session's own wrapper —
the same client, a worktree of the same repository — runs a shell that tries what it must not be able to do and
reports what it sees; anything not as required refuses the run. The measurement's own subprocesses run in a fixed C
locale (`LOCALE`, recorded in the report), whatever the caller's. The only writable mounts it accepts are the workspace,
the explicitly allowed device nodes `--dev` places (`DEVICES`) and mounts shown to be the sandbox's own (`_owned`:
a file system a wrapper makes, a super block the host's mount table — read before the session starts — does not hold,
no propagation with the host);
a writable mount it cannot establish either way refuses the run too. Not confined here: the kernel's own execution of
the developer's tests and the probes' execution of the candidate (they run as the operator's user); Open Code Review is
refused together with confinement (app/settings), since it calls the model outside the client's sessions."""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import secrets
import subprocess
import sys
import sysconfig
import time
from typing import Mapping

KEYS = ("backend", "bwrap", "network", "read_only")
NETWORKS = ("none", "host")
HOME = "/aisef-home"
#: the system a client needs, read-only: a link (merged /usr) stays a link
SYSTEM = ("/usr", "/etc", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32")
MARK = "@@aisef-confine "
#: what the measurement runs inside the wrapper: $1 canary (its CONTENT is the secret token, so its leak is seen even
#: though a denial may echo a file's path), $2 run-directory file, $3 kernel file, $4 site-packages file, $5 the
#: operator's HOME, $6 workspace file, $7 a sleep duration no other process has, $8 a file in the client's directory,
#: $9 a file in the workspace's common git directory, then every host directory bound in (the unix sockets below them
#: are listed: a read-only mount does not stop a connect to one). The probe-file paths carry a nonce, never the token,
#: so a "cannot create <path>" message can never look like a canary leak.
PROBE = r'''m() { printf '@@aisef-confine %s\n' "$*"; }
m uid "$(id -u)"
for n in user pid net ipc uts mnt; do m ns "$n" "$(readlink /proc/self/ns/$n 2>&1)"; done
m section status; cat /proc/self/status 2>&1
m section mountinfo; cat /proc/self/mountinfo 2>&1
m section devices
cat /proc/self/mountinfo 2>/dev/null | while read -r _ _ _ _ at _; do
  case $at in */null|*/zero|*/full|*/random|*/urandom|*/tty)
    if [ -c "$at" ]; then echo "char $(stat -L -c '%t:%T' -- "$at" 2>/dev/null) $at"; else echo "other - $at"; fi ;;
  esac
done
m section route; cat /proc/net/route 2>&1
m section netdev; cat /proc/net/dev 2>&1
m section home; if [ -e "$5" ]; then ls -A -- "$5" 2>&1; fi
m try read_canary; cat -- "$1" 2>&1; m rc $?
m try write_run_directory; (: > "$2") 2>&1; m rc $?
m try write_kernel; (: > "$3") 2>&1; m rc $?
m try write_interpreter_site; (: > "$4") 2>&1; m rc $?
m try write_client_directory; (: > "$8") 2>&1; m rc $?
m try write_git_directory; (: > "$9") 2>&1; m rc $?
m try read_git_directory; cat -- "$(dirname -- "$9")/HEAD" 2>&1; m rc $?
m try workspace; (echo ok > "$6" && cat -- "$6" && rm -f -- "$6") 2>&1; m rc $?
m try user_namespace
if command -v unshare >/dev/null 2>&1; then unshare --user true 2>&1; m rc $?; else echo "unshare: absent"; m rc 127; fi
m try setsid
if command -v setsid >/dev/null 2>&1; then setsid sleep "$7" </dev/null >/dev/null 2>&1 & else (sleep "$7" </dev/null >/dev/null 2>&1 &); fi
m rc 0
shift 9
m section sockets
if command -v find >/dev/null 2>&1; then find "$@" -type s -print 2>/dev/null | head -n 50; m sockets listed; fi
m end
'''
#: how long a probe's sleeper found once bubblewrap returned may take to die before it counts as a survivor: the PID
#: namespace's teardown can still be killing it then (measured: 1 in 400 measurements, the pid gone at once after)
SURVIVOR_GRACE = 1.0
#: the probe's time limit (s) and how long its setsid sleeper lives: longer than the limit plus SURVIVOR_GRACE plus a
#: look, so a sleeper that outlived the session is still alive at the last look even after a probe that exited just
#: inside its limit (one that reached it is refused anyway) — a survivor is dropped only by being killed, never by
#: reaching its own end
PROBE_TIMEOUT, SLEEPER = 60, 120
#: what a kernel that refuses a further user namespace says (--disable-userns: ENOSPC; a seccomp or LSM refusal: EPERM)
USERNS_REFUSED = re.compile(r"No space left on device|Operation not permitted")
#: the locale of the measurement's own subprocesses (the probe, `bwrap --version`): fixed, so the text they print — the
#: probe's output, what USERNS_REFUSED matches — does not depend on the caller's, and recorded in the report
#: (`locale`). Nothing of the caller's LANG, LANGUAGE or LC_* reaches them; the sessions' environment (`wrap`, shared
#: with real sessions) and the caller's own are not touched.
LOCALE = {"LC_ALL": "C", "LANG": "C"}
#: the file systems a wrapper can make for itself (kernel pseudo file systems): the mount source of each is its own name,
#: never a host path or device. A writable mount of one of these is the sandbox's only as `_owned` shows.
PSEUDO = ("tmpfs", "proc", "devpts", "mqueue")
#: the execution resources `--dev` places: bubblewrap binds the HOST's own nodes there, so they are host-backed and are
#: accepted for being explicitly allowed — a closed list, each the character device of that kernel number (devices.txt)
DEVICES = {"null": "1:3", "zero": "1:5", "full": "1:7", "random": "1:8", "urandom": "1:9", "tty": "5:0"}
#: a super block number (major:minor) and a propagation tag of mountinfo's optional fields
_DEV = re.compile(r"\d+:\d+")
_PEER = re.compile(r"(shared|master|propagate_from):(\d+)")


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
    if spec["network"] == "none":
        return ("confinement.network none leaves a model session no route to its provider: it is a measurement-only "
                "profile (validation/v21/sandbox); a run uses host, whose egress is NOT confined")
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


def argv(spec: Mapping, command: list[str], workspace: str, read_only: list[str], writable: bool = True) -> list[str]:
    """The bubblewrap command line: namespaces, privileges, the system read-only, `read_only`, the workspace last
    (read-write — even below a read-only path — unless not `writable`), the command in the workspace."""
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
    return [*a, "--bind" if writable else "--ro-bind", workspace, workspace, "--chdir", workspace, "--", *command]


def wrap(spec: Mapping, command: list[str], env: Mapping[str, str], workspace: str, exe: str | None = None,
         system: str = sys.platform, writable: bool = True) -> tuple[list[str], dict]:
    """(argv, env) of `command` confined to `workspace` (bound read-only when not `writable`: the reviewer's);
    Unavailable when this host cannot confine (fail closed)."""
    if not system.startswith("linux"):
        raise Unavailable(f"confinement is Linux-only (bubblewrap); this host is {system}: no backend")
    if not (os.path.isfile(spec["bwrap"]) and os.access(spec["bwrap"], os.X_OK)):
        raise Unavailable(f"bubblewrap is not an executable file at {spec['bwrap']}")
    missing = [p for p in spec["read_only"] if not os.path.exists(p)]
    if missing:
        raise Unavailable(f"confinement.read_only names paths that do not exist: {missing}")
    client = os.path.dirname(os.path.realpath(exe)) if exe else None
    if client:
        held = [what for what, p in (("HOME", env.get("HOME")), ("HOME", os.path.expanduser("~")), ("the workspace", workspace))
                if p and os.path.commonpath([client, os.path.realpath(p)]) == client]
        if held:
            raise Unavailable(f"the client's directory {client} holds {held[0]}: bound read-only it would expose it; "
                              f"give the client a directory of its own")
    base, cfg = config_dir(env)
    ro = [*filter(None, [client, git_dir(workspace), cfg]), *spec["read_only"]]
    inside = {k: v for k, v in env.items() if k not in ("USERPROFILE", "TEMP", "TMP")}
    inside.update(HOME=HOME, TMPDIR="/tmp", XDG_DATA_HOME=f"{HOME}/.local/share", XDG_STATE_HOME=f"{HOME}/.local/state",
                  XDG_CACHE_HOME=f"{HOME}/.cache", XDG_CONFIG_HOME=base if cfg else f"{HOME}/.config")
    return argv(spec, command, workspace, ro, writable), inside


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
    """The rows of a mountinfo table (proc(5): id, parent, major:minor, root, mount point, per-mount options, optional
    fields, `-`, type, source, super options) as what a judgement needs: where (`at`), whether writable (`access`: `ro`
    only when a PER-MOUNT option says so), the file system (`fs`), the super block (`dev`: shared by every mount of the
    same file system, a bind included), what of it is mounted (`root`), its `source`, the per-mount `options`, the
    `super_options` and the propagation `optional` fields. A line that is not of that shape is skipped."""
    def text(s: str) -> str:      # mountinfo escapes a space, a tab, a newline and a backslash in octal
        return re.sub(r"\\([0-7]{3})", lambda o: chr(int(o[1], 8)), s)
    out = []
    for line in lines:
        left, sep, right = line.partition(" - ")
        f, r = left.split(), right.split()
        if sep and len(f) >= 6 and r:
            out.append({"at": text(f[4]), "access": "ro" if "ro" in f[5].split(",") else "rw", "fs": r[0], "dev": f[2],
                        "root": text(f[3]), "source": text(r[1]) if len(r) > 1 else None, "options": f[5].split(","),
                        "super_options": r[2].split(",") if len(r) > 2 else [], "optional": f[6:]})
    return out


def _host_mounts() -> list[dict] | None:
    """The host's mount table as the controller sees it — its own /proc/self/mountinfo, the table every host bind of a
    session comes from — as the rows' `at`, `fs`, `dev` and `optional` (what a judgement of a sandbox's mounts against
    it uses and a verifier needs), or None when it cannot be read whole (a line that does not parse is a mount it
    cannot rule out)."""
    try:
        lines = pathlib.Path("/proc/self/mountinfo").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    rows = _mounts(lines)
    if not rows or len(rows) != len(lines):
        return None
    return [{k: r[k] for k in ("at", "fs", "dev", "optional")} for r in rows]


def _device_roots(full: list[str]) -> list[str]:
    """Where a bubblewrap command line has `--dev` place its device nodes (which option made a mount is the option's,
    never the path's)."""
    a = full[:full.index("--")]
    return [a[i + 1] for i, f in enumerate(a) if f == "--dev"]


def targets(full: list[str], host: bool = False) -> list[str]:
    """Where a bubblewrap command line mounts something (what a session may see mounted, and nothing else); `host`:
    only where it binds a directory of the HOST (--bind, --ro-bind), not what the sandbox makes itself (--tmpfs,
    --proc, --dev). Which is which is the option's, never the path's: the host's /tmp bound over `--tmpfs /tmp` is a
    host directory."""
    a = full[:full.index("--")]
    return [a[i + (2 if f in ("--bind", "--ro-bind") else 1)] for i, f in enumerate(a)
            if f in ("--bind", "--ro-bind") or (not host and f in ("--tmpfs", "--proc", "--dev"))]


def _worktree(where: pathlib.Path, repo: pathlib.Path | None) -> tuple[pathlib.Path, pathlib.Path]:
    """(repository, workspace): the measurement's workspace is a worktree, as a session's is — of the run's own
    repository when given (its common git directory is what the sessions read), else of a new one in `where`."""
    from aisef2.orchestrate.workspace import git
    where.mkdir(parents=True)
    if repo is None:
        repo = where / "repo"
        repo.mkdir()
        for args in (("init", "-q"), ("-c", "user.name=aisef", "-c", "user.email=aisef@localhost", "commit", "-q",
                                      "--allow-empty", "-m", "confinement measurement")):
            if git(repo, *args).returncode != 0:
                raise Unavailable(f"the measurement repository could not be made in {repo}")
    p = git(repo, "worktree", "add", "-q", "--detach", str(where / "ws"))
    if p.returncode != 0:
        raise Unavailable(f"the measurement workspace could not be made a worktree of {repo}: {p.stderr.strip()[:200]}")
    return repo, where / "ws"


def measure(spec: Mapping, where: pathlib.Path, exe: str | None = None, repo: pathlib.Path | None = None,
            system: str = sys.platform, environ: Mapping[str, str] | None = None) -> dict:
    """Run the probe under the wrapper a session gets — the client `exe`'s directory, a worktree of `repo` (the run's
    repository; a new one when None) as the workspace, so the same read-only mounts — with `where` (a new directory in
    the run directory) as the run directory: what it saw, what it was denied, and the problems — any one refuses the
    run. The probe and the `--version` query run in the fixed C `LOCALE`, whatever `environ` holds (recorded as
    `locale`). The measurement's worktree is removed from `repo` afterwards; a file the probe made outside the
    workspace is not removed: it is named (`left_on_host`) and refuses the run."""
    environ = dict(os.environ if environ is None else environ)
    rep: dict = {"backend": spec["backend"], "bwrap": spec["bwrap"], "network": spec["network"],
                 "read_only": list(spec["read_only"]), "client": exe, "system": system,
                 "operator_uid": os.getuid() if hasattr(os, "getuid") else None}
    env = {k: environ[k] for k in ("PATH", "HOME", "XDG_CONFIG_HOME") if k in environ}
    cmd = ["/bin/sh", "-c", PROBE, "probe"]
    made = None
    try:
        if not system.startswith("linux"):
            wrap(spec, cmd, env, "/", system=system)        # raises: no backend; nothing is made on the host
        made = _worktree(where, repo)
        full, inside_env = wrap(spec, cmd, env, str(made[1]), exe, system=system)
        if not exe:
            raise Unavailable("the client (opencode) is not on the PATH the run gives it: the session's wrapper "
                              "cannot be measured")
        try:
            rep["bwrap_sha256"] = hashlib.sha256(pathlib.Path(spec["bwrap"]).read_bytes()).hexdigest()
        except OSError as e:
            raise Unavailable(f"bubblewrap at {spec['bwrap']} could not be read: {type(e).__name__}") from None
        return _probe(spec, where, made[1], full, inside_env, env, cmd, rep)
    except Unavailable as e:
        return {**rep, "problems": [str(e)]}
    finally:
        if made is not None:
            from aisef2.orchestrate.workspace import git
            git(made[0], "worktree", "remove", "--force", str(made[1]))


def _probe(spec: Mapping, where: pathlib.Path, ws: pathlib.Path, full: list[str], inside_env: dict, env: dict,
           cmd: list[str], rep: dict) -> dict:
    # what the measurement's subprocesses get: the session's environment (`inside_env`) but for the locale, fixed
    run_env = {**{k: v for k, v in inside_env.items() if not re.match(r"LC_|LANG", k)}, **LOCALE}
    rep["locale"] = {k: v for k, v in run_env.items() if re.match(r"LC_|LANG", k)}
    try:
        rep["bwrap_version"] = subprocess.run([spec["bwrap"], "--version"], capture_output=True, text=True, timeout=30,
                                              env=run_env).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        rep["bwrap_version"] = f"unavailable: {type(e).__name__}"
    token, nonce = secrets.token_hex(16), secrets.token_hex(8)   # token: only the canary's content; nonce: the file paths
    probe_file = f".aisef-confine-probe-{nonce}"
    canary = where / "canary"
    canary.write_text(token + "\n", encoding="utf-8")
    files = {"run_directory": where / f"written-{nonce}",
             "kernel": pathlib.Path(__file__).resolve().parents[1] / probe_file,
             "interpreter_site": pathlib.Path(sysconfig.get_paths()["purelib"]) / probe_file,
             "client_directory": pathlib.Path(os.path.dirname(os.path.realpath(rep["client"]))) / probe_file,
             "git_directory": pathlib.Path(git_dir(str(ws)) or ws / ".git") / probe_file}
    home = env.get("HOME") or "/nonexistent"
    sleep = f"{SLEEPER}.{int(nonce, 16) % 10**6:06d}"
    f = {k: str(v) for k, v in files.items()}
    args = [str(canary), f["run_directory"], f["kernel"], f["interpreter_site"], home, str(ws / probe_file), sleep,
            f["client_directory"], f["git_directory"], *targets(full, host=True)]
    rep["argv"] = full[:-len(cmd)] + ["/bin/sh", "-c", "<PROBE>", "probe"]
    before = _host_mounts()      # the host's table as it is when the session starts: what decides; read again after it ends
    try:
        p = subprocess.run(full + args, capture_output=True, text=True, env=run_env, timeout=PROBE_TIMEOUT)
        code, out = p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:      # its own text starts with the whole command line: cut, it never reaches the limit
        code, out = None, f"TimeoutExpired: timed out after {PROBE_TIMEOUT} seconds"
    except (OSError, subprocess.SubprocessError) as e:
        code, out = None, f"{type(e).__name__}: {e}"
    after = _host_mounts()
    survivors = _survivors(f"sleep {sleep}")
    created = {k: v.exists() for k, v in files.items()}
    values, sections, tries = _sections(out)
    problems = []
    if code != 0 or "end" not in values:
        problems.append(f"the sandbox did not run the probe (exit {code}): {out.strip()[:300]}")
    status = dict(line.split(":", 1) for line in sections.get("status", []) if ":" in line)
    status = {k: v.strip() for k, v in status.items()}
    caps = {k: status.get(k) for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")}
    mounts = _mounts(sections.get("mountinfo", []))
    devices = {}       # "<char|other> <major:minor|-> <path>": what the probe found at each device node's mount point
    for ln in sections.get("devices", []):
        kind, _, rest = ln.partition(" ")
        number, _, path = rest.partition(" ")
        devices[path] = number if kind == "char" else kind
    netdev = [ln.split(":", 1)[0].strip() for ln in sections.get("netdev", [])[2:] if ":" in ln]
    # /proc/net/route rows after the header: an interface with a route. A fresh netns (--unshare-net) has none, even
    # though this kernel pre-creates DOWN tunnel pseudo-devices, so routes — not interface names — show reachability.
    routes = [ln.split("\t")[0] for ln in sections.get("route", [])[1:] if "\t" in ln]
    rep["inside"] = {"uid": values.get("uid"), "capabilities": caps, "no_new_privs": status.get("NoNewPrivs"),
                     "seccomp": status.get("Seccomp"), "network_interfaces": netdev, "routed_interfaces": sorted(set(routes)),
                     "mounts": mounts, "mount_targets": targets(full),
                     "device_roots": _device_roots(full), "devices": devices,
                     "namespaces": namespaces(values.get("ns", {})),
                     "home_listing": sections.get("home", []),
                     "unix_sockets": sections.get("sockets", []) if values.get("sockets") == "listed" else None}
    # the host's mount table (the report is the record: a verifier sees which super blocks the host held) is the reading
    # BEFORE the session: a super block the session creates is one no live host mount holds, so one the host already
    # had is not the sandbox's. None when it failed, so that no mount is shown to be the sandbox's own. The reading
    # after the session decides nothing — the numbers the session held are free again by then, and a host mount made
    # in the milliseconds after its end can take one; a row that appeared cannot tell that from a leak — it is
    # recorded: the rows the host gained meanwhile (None when either reading failed: nothing to tell it from)
    rep["host_mounts"] = before
    rep["host_mounts_appeared"] = None if before is None or after is None else [r for r in after if r not in before]
    rep["tried"] = {k: {"exit": rc, "output": o} for k, (rc, o) in tries.items()}
    rep["created_outside_workspace"] = created
    rep["setsid_survivors"] = survivors
    rep["operator_can"] = {f"write_{k}": os.access(v.parent, os.W_OK) for k, v in files.items()}
    # INV-MUTATION-AUTHORITY: a file the probe made where confinement did not stop it exists because of the subject;
    # nothing here removes it — the measurement refuses the run and names each one for the operator to remove
    rep["left_on_host"] = [f[k] for k, v in created.items() if v]
    if not problems:
        problems += _judge(rep, token, out, tries, home, ws)
    if rep["left_on_host"]:
        problems.append(f"the probe's files are left where confinement did not stop them; nothing was removed, the "
                        f"operator removes them: {rep['left_on_host']}")
    rep["problems"] = problems
    return rep


def _survivors(command: str) -> list[int]:
    """The live processes whose command line holds `command`, once each has had SURVIVOR_GRACE seconds to die: one the
    PID namespace's teardown is still killing did not outlive the session; one still alive after it did. A killed one
    no longer matches: the table drops it, and its command line is gone anyway (macOS `ps`: `<defunct>`; Linux:
    an empty /proc/<pid>/cmdline)."""
    from aisef2.runtime.process_range import process_table
    deadline = time.monotonic() + SURVIVOR_GRACE
    while True:
        found = sorted(pr.pid for pr in process_table().values() if command in pr.command)
        if not found or time.monotonic() >= deadline:
            return found
        time.sleep(0.05)


def namespaces(inside: Mapping[str, str], outside: Mapping[str, str | None] | None = None) -> dict:
    """Each namespace the probe read: "own" when both links are read (`user:[4026531837]`) and differ, "shared" when
    equal, "not measured" otherwise — an error text or a link that could not be read never passes as "own"."""
    if outside is None:
        outside = {n: (os.readlink(f"/proc/self/ns/{n}") if os.path.exists(f"/proc/self/ns/{n}") else None) for n in inside}
    return {n: ("not measured" if not (_link(n, v) and _link(n, outside.get(n))) else "own" if v != outside[n] else "shared")
            for n, v in inside.items()}


def _link(n: str, v) -> bool:
    return isinstance(v, str) and re.fullmatch(rf"{n}:\[\d+\]", v) is not None


def _within(path: str, roots) -> bool:
    """`path` is a root or lies below one; a root written with a trailing slash (`read_only` is bound as written, the
    kernel prints its mount point without it) is the same directory."""
    return any(path == r or path.startswith(r + "/") for r in (r.rstrip("/") for r in roots))


def _owned(m: dict, inside: dict, host: list[dict] | None) -> tuple[bool, str] | None:
    """Whether the writable mount `m` (not the workspace) is shown to belong to the sandbox — the owner's write policy
    (docs/v2.1/decisions/B03-R3-conf.md): None when it is, else (known, why): `known` when what was read shows it is
    NOT (it can write beyond the sandbox), not known when the data to show either way is missing. The file system's
    name and the mount's place under /dev decide nothing. A mount is the sandbox's when

    * it is one of the explicitly allowed execution resources — the name of a device `--dev` places (a closed list),
      under a `--dev` destination of the command line, and the probe read it inside as the character device of exactly
      that kernel number (the host's own node: host-backed, allowed for being allowed); or
    * its file system is one a wrapper makes for itself, its mount source is that file system's own name (not a host
      path or device), its super block is not one the host's mount table holds (so it was made inside the sandbox: a
      write cannot reach the host, and the super block goes with the mount namespace — proc's with the PID namespace,
      mqueue's with the IPC one) and no peer group of the host propagates into it or out of it.

    Everything else — an unread field, an unreadable or incomplete host table — is not established: not a pass."""
    at, fs = m["at"], m["fs"]
    parent, _, name = at.rpartition("/")
    if name in DEVICES and parent in inside.get("device_roots", ()):
        seen = inside.get("devices", {}).get(at)
        if seen == DEVICES[name]:
            return None
        return bool(seen), f"it is not shown to be the character device {DEVICES[name]} (read: {seen or 'nothing'})"
    if fs not in PSEUDO:
        return True, ""
    if m.get("source") is None:
        return False, "its mount source was not read"
    if m["source"] != fs:
        return True, f"its mount source is {m['source']!r}, not {fs}'s own"
    if not host:
        return False, "the host's mount table could not be read"
    if not all(isinstance(h, dict) and isinstance(h.get("dev"), str) and _DEV.fullmatch(h["dev"])
               and isinstance(h.get("optional"), list) for h in host):
        # a row that shows neither its super block nor its peer groups rules nothing out: not a table to judge against
        return False, "the host's mount table has a row that does not show its super block or peer groups"
    dev = m.get("dev")
    if not (isinstance(dev, str) and _DEV.fullmatch(dev)):
        return False, "its super block was not read"
    shared = next((h for h in host if h.get("dev") == dev), None)
    if shared:
        return True, f"its super block {dev} is the host's (mounted there at {shared['at']})"
    tags = m.get("optional")
    if not isinstance(tags, list):
        return False, "its propagation was not read"
    groups = {t.partition(":")[2] for h in host for t in h.get("optional") or () if _PEER.fullmatch(t)}
    leaks = [t for t in tags if t.partition(":")[2] in groups and _PEER.fullmatch(t)]
    if leaks:
        return True, f"it propagates with the host's peer group {leaks}"
    if not all(re.fullmatch(r"shared:\d+", t) for t in tags):
        return False, f"its propagation {tags} is not shown to be the sandbox's own"
    return None


def _writes(inside: dict, host: list[dict] | None, ws: pathlib.Path) -> list[tuple[str, bool, str]]:
    """(mount point, known, why) of each writable mount outside the workspace that `_owned` does not show to be the
    sandbox's."""
    out = []
    for m in inside["mounts"]:
        if m["access"] == "rw" and m["at"] != str(ws) and (no := _owned(m, inside, host)) is not None:
            if (m["at"], *no) not in out:     # a mount covered by another at the same path is judged as that path is
                out.append((m["at"], *no))
    return out


def _judge(rep: dict, token: str, out: str, tries: dict, home: str, ws: pathlib.Path) -> list[str]:
    """What the measurement shows that confinement must not allow — or did not measure (a check that could not run
    is a problem, never a pass)."""
    inside, bad = rep["inside"], []
    if token in out or tries.get("read_canary", (0,))[0] == 0:
        bad.append("a file of the run directory was readable")
    bad += [f"a file was created in the {k.replace('_', ' ')}" for k, v in rep["created_outside_workspace"].items() if v]
    if tries.get("workspace", (1, ""))[0] != 0 or "ok" not in tries.get("workspace", (1, ""))[1]:
        bad.append("the workspace was not writable")
    if tries.get("read_git_directory", (1,))[0] != 0:
        bad.append("the workspace's git directory was not readable (git would not work in the session)")
    rc, said = tries.get("user_namespace", (None, ""))
    if rc == 0:
        bad.append("a user namespace could be created")
    elif rc in (None, 127) or not USERNS_REFUSED.search(said):
        bad.append(f"no refusal of a further user namespace was measured (exit {rc}: {said[:120]})")
    if rep["setsid_survivors"]:
        bad.append(f"a process the session left outlived it: {rep['setsid_survivors']}")
    for k in ("CapInh", "CapPrm", "CapEff", "CapAmb"):
        if inside["capabilities"][k] is None or int(inside["capabilities"][k], 16) != 0:
            bad.append(f"{k} is {inside['capabilities'][k]}, not 0")
    if inside["no_new_privs"] != "1":
        bad.append(f"NoNewPrivs is {inside['no_new_privs']}, not 1")
    need = ("user", "pid", "ipc", "uts", "mnt", *(("net",) if rep["network"] == "none" else ()))
    bad += [f"the {n} namespace is not the session's own ({inside['namespaces'].get(n, 'not measured')})" for n in need
            if inside["namespaces"].get(n) != "own"]
    if rep["network"] == "none" and inside["routed_interfaces"]:
        bad.append(f"network none has routes on {inside['routed_interfaces']} (a reachable network)")
    if not inside["mounts"]:
        bad.append("the mounts could not be read")
    beyond = [m["at"] for m in inside["mounts"] if m["at"] != "/" and not _within(m["at"], inside["mount_targets"])]
    if beyond:
        bad.append(f"mounted beyond what the wrapper names: {beyond[:10]}")
    unowned = _writes(inside, rep.get("host_mounts"), ws)
    if refused := [(at, why) for at, known, why in unowned if known]:
        # a mount whose file system is not a pseudo one is writable host storage, whatever else: nothing more to say
        said = [f"{at}: {why}" for at, why in refused if why]
        bad.append(f"writable outside the workspace: {[at for at, _ in refused]}" + (f" ({'; '.join(said)})" if said else ""))
    if unknown := [f"{at}: {why}" for at, known, why in unowned if not known]:
        bad.append("cannot establish that a writable mount belongs to the sandbox (isolation not established, not a "
                   f"write that was seen): {'; '.join(unknown)}")
    names = {pathlib.PurePosixPath(m["at"]).relative_to(home).parts[0] for m in inside["mounts"]
             if pathlib.PurePosixPath(m["at"]).is_relative_to(home) and m["at"] != home}
    shown = set(inside["home_listing"])
    if home != "/nonexistent" and not shown <= names:
        bad.append(f"HOME shows more than the way to what is mounted: {sorted(shown - names)[:10]}")
    if inside["unix_sockets"] is None:
        bad.append("the reachable unix sockets could not be listed (no find in the sandbox)")
    else:
        reach = [x for x in inside["unix_sockets"] if not _within(x, [str(ws)])]
        if reach:
            bad.append(f"a unix socket outside the workspace is reachable (read-only does not stop a connect): {reach[:10]}")
    return bad
