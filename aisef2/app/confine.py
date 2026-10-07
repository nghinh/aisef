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
reports what it sees; anything not as required refuses the run. Not confined here: the kernel's own execution of the
developer's tests and the probes' execution of the candidate (they run as the operator's user); Open Code Review is
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
    out = []
    for line in lines:
        left, sep, right = line.partition(" - ")
        f, r = left.split(), right.split()
        if sep and len(f) >= 6 and r:      # mountinfo escapes a space, a tab, a newline and a backslash in octal
            at = re.sub(r"\\([0-7]{3})", lambda o: chr(int(o[1], 8)), f[4])
            out.append({"at": at, "access": "ro" if "ro" in f[5].split(",") else "rw", "fs": r[0]})
    return out


def targets(full: list[str]) -> list[str]:
    """Where a bubblewrap command line mounts something (what a session may see mounted, and nothing else)."""
    a = full[:full.index("--")]
    return [a[i + (2 if f in ("--bind", "--ro-bind") else 1)] for i, f in enumerate(a)
            if f in ("--bind", "--ro-bind", "--tmpfs", "--proc", "--dev")]


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
    run. The measurement's worktree is removed from `repo` afterwards."""
    environ = dict(os.environ if environ is None else environ)
    rep: dict = {"backend": spec["backend"], "bwrap": spec["bwrap"], "network": spec["network"],
                 "read_only": list(spec["read_only"]), "client": exe, "system": system,
                 "operator_uid": os.getuid() if hasattr(os, "getuid") else None}
    env = {k: environ[k] for k in ("PATH", "HOME", "XDG_CONFIG_HOME", "LANG") if k in environ}
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
    try:
        rep["bwrap_version"] = subprocess.run([spec["bwrap"], "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
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
            f["client_directory"], f["git_directory"], *[t for t in targets(full) if t not in ("/proc", "/dev", "/tmp", HOME)]]
    rep["argv"] = full[:-len(cmd)] + ["/bin/sh", "-c", "<PROBE>", "probe"]
    try:
        p = subprocess.run(full + args, capture_output=True, text=True, env=inside_env, timeout=PROBE_TIMEOUT)
        code, out = p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        code, out = None, f"{type(e).__name__}: {e}"
    survivors = _survivors(f"sleep {sleep}")
    created = {k: v.exists() for k, v in files.items()}
    for v in files.values():     # the probe's own empty files, if confinement failed to stop them
        if v.exists():
            v.unlink()
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
    rep["inside"] = {"uid": values.get("uid"), "capabilities": caps, "no_new_privs": status.get("NoNewPrivs"),
                     "seccomp": status.get("Seccomp"), "network_interfaces": netdev, "routed_interfaces": sorted(set(routes)),
                     "mounts": mounts, "mount_targets": targets(full),
                     "namespaces": namespaces(values.get("ns", {})),
                     "home_listing": sections.get("home", []),
                     "unix_sockets": sections.get("sockets", []) if values.get("sockets") == "listed" else None}
    rep["tried"] = {k: {"exit": rc, "output": o} for k, (rc, o) in tries.items()}
    rep["created_outside_workspace"] = created
    rep["setsid_survivors"] = survivors
    rep["operator_can"] = {f"write_{k}": os.access(v.parent, os.W_OK) for k, v in files.items()}
    if not problems:
        problems += _judge(rep, token, out, tries, home, ws)
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
    return any(path == r or path.startswith(r.rstrip("/") + "/") for r in roots)


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
    host_backed = [m for m in inside["mounts"] if m["access"] == "rw" and m["fs"] not in ("tmpfs", "proc", "devpts", "mqueue")
                   and not m["at"].startswith("/dev/") and m["at"] != str(ws)]
    if host_backed:
        bad.append(f"writable outside the workspace: {[m['at'] for m in host_backed]}")
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
