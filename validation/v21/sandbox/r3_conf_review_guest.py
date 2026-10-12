"""B03-R3 conf, independent review: command lines and operator settings the work package's own scenarios did not try,
through `confine._probe` with the REAL bubblewrap in the Linux guest (run like r3_conf_guest.py:
`$R3/guest.sh <tree> X1 python3 -B /repo/validation/v21/sandbox/r3_conf_review_guest.py`). It prints one JSON object;
docs/v2.1/evidence/sandbox/r3-conf/review-X1.json is such an output. It never runs the real `opencode` and calls no
provider.

  extra      options added to the session's command line before `--chdir`:
             * dev-bind-null-over-null  `--dev-bind /dev/null /dev/null` — the same device the `--dev` option placed:
                                        the row is the same, so identity accepts it;
             * bind-null-at-dev-x       `--bind /dev/null /dev/x` — the device under a name outside the list;
  tty        the controller's own stdin is a terminal (a pseudo terminal): bubblewrap 0.12.0 with `--new-session` binds
             no `/dev/console` for it, so no row for it appears;
  read_only  the operator's `read_only` paths (`wrap` binds each `--ro-bind` before the workspace): `/tmp`, `/run`,
             `/dev/shm`, `/dev/pts` leave nothing to refuse; `/dev` makes `/dev/null` read-only, which stops the probe's
             own redirects (`unshare: absent`) — refused by the earlier checks too.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import pty
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("r3_conf_guest", ROOT / "validation" / "v21" / "sandbox" / "r3_conf_guest.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)
confine = g.confine

#: a place that is not below /tmp (a run directory below /tmp would be bound over by `read_only: ["/tmp"]`)
BASE = pathlib.Path("/home/op/rv-review") if os.path.isdir("/home/op") else pathlib.Path(tempfile.gettempdir())


def run(name: str, extra: list[str] | None = None, read_only: list[str] | None = None) -> dict:
    BASE.mkdir(parents=True, exist_ok=True)
    base = pathlib.Path(tempfile.mkdtemp(dir=BASE))
    lay = g.layout(base)
    spec = {"backend": "bwrap", "bwrap": g.BWRAP, "network": "host", "read_only": read_only or []}
    env = {"PATH": "/usr/bin:/bin", "HOME": str(lay["home"])}
    cmd = ["/bin/sh", "-c", confine.PROBE, "probe"]
    where = base / name
    repo, ws = confine._worktree(where, lay["repo"])
    full, inside_env = confine.wrap(spec, cmd, env, str(ws), str(lay["exe"]), system="linux")
    i = full.index("--chdir")
    full = full[:i] + (extra or []) + full[i:]
    rep = {"backend": "bwrap", "bwrap": g.BWRAP, "network": "host", "read_only": read_only or [], "client": str(lay["exe"]),
           "system": "linux", "operator_uid": os.getuid()}
    table = getattr(confine, "_host_mounts", lambda: [])     # an earlier tree has none: the comparison is then empty
    before = sorted([m["dev"], m["at"], m["fs"]] for m in table() or [])
    rep = confine._probe(spec, where, ws, full, inside_env, env, cmd, rep)
    after = sorted([m["dev"], m["at"], m["fs"]] for m in table() or [])
    g.git("-C", str(repo), "worktree", "remove", "--force", str(ws))
    writable = [{"at": m["at"], "fs": m["fs"], "source": m.get("source"), "dev": m.get("dev"),
                 "optional": m.get("optional")}
                for m in rep["inside"]["mounts"] if m["access"] == "rw" and m["at"] != str(ws)]
    return {"extra": extra or [], "read_only": read_only or [], "accepted": not rep["problems"],
            "problems": rep["problems"], "devices": rep["inside"].get("devices"), "writable_mounts_besides_the_workspace": writable,
            "table_unchanged": before == after}


def main(modes: list[str]) -> dict:
    out = {}
    if "extra" in modes:
        out["dev-bind-null-over-null"] = run("dev-bind-null-over-null", ["--dev-bind", "/dev/null", "/dev/null"])
        out["bind-null-at-dev-x"] = run("bind-null-at-dev-x", ["--bind", "/dev/null", "/dev/x"])
    if "tty" in modes:
        master, slave = pty.openpty()
        saved = os.dup(0)
        os.dup2(slave, 0)
        try:
            out["stdin-is-a-terminal"] = {**run("stdin-is-a-terminal"), "stdin": os.ttyname(0)}
        finally:
            os.dup2(saved, 0)
            os.close(saved)
            os.close(master)
            os.close(slave)
    if "read_only" in modes:
        for path in ("/tmp", "/run", "/dev/shm", "/dev/pts", "/dev"):
            out[f"read_only {path}"] = run("ro-" + path.strip("/").replace("/", "-"), read_only=[path])
    return out


if __name__ == "__main__":
    modes = sys.argv[1:] or ["extra", "tty", "read_only"]
    print(json.dumps({"environment": g.environment(), "record": main(modes)}, indent=1, sort_keys=True))
