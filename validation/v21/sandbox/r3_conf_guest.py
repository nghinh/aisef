"""B03-R3 conf: the write policy and the locale of aisef2.app.confine, measured with the REAL bubblewrap in the Linux guest.

Run by `$R3/guest.sh <tree> X1 python3 -B /repo/validation/v21/sandbox/r3_conf_guest.py <mode>` (one discarded container
of the measure image, the tree mounted read-only at /repo, no network; docs/v2.1/evidence/sandbox/r3-conf/README.md has
the command lines and what each record shows). It never runs the real `opencode` (the client is a shell script) and
calls no provider. It prints one JSON object.

  scenarios   the session's own command line, and variations of it, through `confine._probe` — the kernel's own
              measurement with a real bubblewrap, a real probe and the container's real /proc/self/mountinfo as the
              host's table — each as the full report plus what is needed to judge it again (`workspace`, `home`):
              what a bubblewrap `--dev`/`--mqueue`/`--proc` makes is the sandbox's own; what is bound from the
              container (`--dev-bind`, `--bind`) or shares its namespaces is not. `table_unchanged`: the host's mount
              table read before and after each session is the same (no mount of the sandbox outlives it).
  shared-tree the same as `scenarios` inside `unshare --user --map-root-user --mount` after `mount --make-rshared /`:
              a mount namespace of the container whose tree has peer groups, as a systemd host's has (the rows the
              sandbox inherits are then `master:N` of the host's groups; the ones it makes have no propagation field).
  locale      `confine.measure` driving the real bubblewrap through a one-line wrapper that saves its `env` and then
              `exec`s it, for a caller whose environment carries LANG, LC_ALL, LC_MESSAGES and LANGUAGE of other
              locales: the environment the real bubblewrap received, and whether `os.environ` was left alone.

The guest has the locales C, C.utf8 and POSIX only: a translated message cannot be shown here (the record says so).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402

GIT = {"HOME": "/tmp", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin"}
BWRAP = os.environ.get("BWRAP", "/usr/bin/bwrap")


def git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, env=GIT, capture_output=True)


def layout(base: pathlib.Path) -> dict:
    """A run's layout, small: the client in a directory of its own, the operator's HOME with the client's
    configuration, the run repository."""
    exe = base / "runtime" / "opencode"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\necho ok\n")
    exe.chmod(0o755)
    home = base / "home"
    (home / ".config" / "opencode").mkdir(parents=True)
    repo = base / "run" / "repo"
    repo.mkdir(parents=True)
    git("-C", str(repo), "init", "-q", "-b", "main")
    git("-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    regular = base / "regular-file"
    regular.write_text("not a device\n")
    return {"exe": exe, "home": home, "repo": repo, "regular": regular}


def table() -> list[list[str]]:
    """The container's own mount table as (super block, mount point, file system), sorted."""
    return sorted([m["dev"], m["at"], m["fs"]] for m in confine._host_mounts() or [])


def scenarios() -> dict:
    base = pathlib.Path(tempfile.mkdtemp())
    lay = layout(base)
    spec = {"backend": "bwrap", "bwrap": BWRAP, "network": "host", "read_only": []}
    env = {"PATH": "/usr/bin:/bin", "HOME": str(lay["home"])}
    cmd = ["/bin/sh", "-c", confine.PROBE, "probe"]
    #: name -> (options added to the session's command line before its --chdir, an option dropped, what it shows)
    variants = {
        "baseline": ([], None, "the session's own command line"),
        "alt-dev-sandbox-devpts": (["--dev", "/alt-dev"], None,
                                   "a second --dev: bubblewrap makes its own tmpfs and devpts at /alt-dev (a devpts "
                                   "outside /dev/, the sandbox's own)"),
        "mqueue-sandbox": (["--mqueue", "/mq"], None, "bubblewrap's own mqueue at /mq (a sandbox-made mqueue)"),
        "host-devpts-at-other-path": (["--dev-bind", "/dev/pts", "/host-pts"], None,
                                      "the container's own devpts bound read-write at /host-pts"),
        "host-mqueue-bound": (["--dev-bind", "/dev/mqueue", "/hostmq"], None, "the container's mqueue bound at /hostmq"),
        "host-dev-bound": (["--dev-bind", "/dev", "/host-dev"], None,
                           "the container's /dev (a tmpfs, with its submounts) bound at /host-dev"),
        "host-shm-over-dev-shm": (["--dev-bind", "/dev/shm", "/dev/shm"], None, "the container's /dev/shm bound over it"),
        "ext4-file-at-dev-x": (["--bind", "/etc/hostname", "/dev/x"], None,
                               "a host file of an ext4 file system, writable, placed under /dev/"),
        "regular-file-at-dev-null": (["--bind", str(lay["regular"]), "/dev/null"], None,
                                     "a regular file bound over /dev/null"),
        "zero-at-dev-null": (["--dev-bind", "/dev/zero", "/dev/null"], None, "/dev/zero's node bound over /dev/null"),
        "ptmx-at-dev-ptmx2": (["--dev-bind", "/dev/ptmx", "/dev/ptmx2"], None,
                              "a device node outside the allowed list, bound at /dev/ptmx2"),
        "shared-pid-namespace": ([], "--unshare-pid", "no PID namespace of its own: /proc is the container's"),
    }
    out = {}
    for name, (extra, drop, shows) in variants.items():
        where = base / name
        repo, ws = confine._worktree(where, lay["repo"])
        full, inside_env = confine.wrap(spec, cmd, env, str(ws), str(lay["exe"]), system="linux")
        if drop:
            full.remove(drop)
        i = full.index("--chdir")
        full = full[:i] + extra + full[i:]
        rep = {"backend": "bwrap", "bwrap": BWRAP, "network": "host", "read_only": [], "client": str(lay["exe"]),
               "system": "linux", "operator_uid": os.getuid()}
        before = table()
        rep = confine._probe(spec, where, ws, full, inside_env, env, cmd, rep)
        out[name] = {"shows": shows, "extra": extra, "dropped": drop, "workspace": str(ws), "home": str(lay["home"]),
                     "table_unchanged": table() == before, "report": rep}
        git("-C", str(repo), "worktree", "remove", "--force", str(ws))
    return out


def locale() -> dict:
    base = pathlib.Path(tempfile.mkdtemp())
    lay = layout(base)
    saved = base / "env-of-bubblewrap"
    saved.mkdir()
    wrapper = base / "bwrap-saving-its-env"
    wrapper.write_text(f'#!/bin/sh\n/usr/bin/env > "{saved}/$$.env"\nexec {BWRAP} "$@"\n')
    wrapper.chmod(0o755)
    caller = {"PATH": "/usr/bin:/bin", "HOME": str(lay["home"]), "LANG": "vi_VN.UTF-8", "LC_ALL": "de_DE.UTF-8",
              "LC_MESSAGES": "fr_FR.UTF-8", "LANGUAGE": "ja"}
    before = dict(os.environ)
    rep = confine.measure({"backend": "bwrap", "bwrap": str(wrapper), "network": "host", "read_only": []},
                          base / "run" / "confinement", str(lay["exe"]), lay["repo"], system="linux", environ=caller)
    calls = []
    for path in sorted(saved.glob("*.env")):
        env = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
        calls.append({"locale_family": {k: v for k, v in env.items() if k.startswith(("LC_", "LANG"))},
                      "keys": sorted(env)})
    return {"caller": {k: v for k, v in caller.items() if k not in ("PATH", "HOME")},
            "locales_in_the_guest": subprocess.run(["locale", "-a"], capture_output=True, text=True).stdout.split(),
            "os_environ_unchanged": dict(os.environ) == before,
            "report": {k: rep.get(k) for k in ("locale", "bwrap_version", "problems")},
            "bubblewrap_calls": calls}


def environment() -> dict:
    """What the records were made on, as the guest says it."""
    def out(*cmd: str) -> str:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    release = dict(ln.split("=", 1) for ln in pathlib.Path("/etc/os-release").read_text().splitlines() if "=" in ln)
    return {"kernel": " ".join(os.uname()[i] for i in (0, 2, 4)), "os": release.get("PRETTY_NAME", "").strip('"'),
            "python": sys.version.split()[0], "bubblewrap": out(BWRAP, "--version"), "uid": os.getuid(),
            "locales": out("locale", "-a").split()}


if __name__ == "__main__":
    mode = sys.argv[1:]
    if mode == ["shared-tree"]:
        os.execvp("unshare", ["unshare", "--user", "--map-root-user", "--mount", "sh", "-c",
                              f"mount --make-rshared / && exec python3 -B {pathlib.Path(__file__).resolve()} scenarios"])
    if mode not in (["scenarios"], ["locale"]):
        raise SystemExit(__doc__)
    print(json.dumps({"environment": environment(), "record": {"scenarios": scenarios, "locale": locale}[mode[0]]()},
                     indent=1, sort_keys=True))
