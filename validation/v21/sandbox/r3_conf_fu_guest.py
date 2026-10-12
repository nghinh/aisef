"""B03-R3 conf follow-up (FU-CONF): the host's super blocks are judged by the reading BEFORE the session — measured
with the REAL bubblewrap in the Linux guest (run like r3_conf_guest.py:
`$R3/guest.sh <tree> X1 python3 -B /repo/validation/v21/sandbox/r3_conf_fu_guest.py`). It prints one JSON object. It never
runs the real `opencode` and calls no provider.

The hazard: anonymous device numbers are allocated lowest-free; when a session ends the numbers of its own tmpfs / devpts
/ proc mounts are free again, and a host mount made before `confine._probe` reads the host's table AFTER the session can
take one of them — the sandbox's own mount then looks like the host's. What is real here: bubblewrap, the probe, the
kernel's allocation of the numbers and the mounts that take them. What is simulated: the "unrelated host activity" — the
driver itself mounts `FLOOD` tmpfs file systems in the controller's mount namespace (a user and mount namespace of the
container, `unshare --user --map-root-user --mount`, as r3_conf_guest.py shared-tree) in place of the second reading of
`confine._host_mounts`, as a container start would, and unmounts them after.

  reuse     a correct session (the baseline command line) with the flood before the second reading; the same with no flood
            (control); and a session that binds the container's own mqueue read-write (a host super block the table held
            BEFORE the session) with the flood (control: refused whatever the second reading holds).

Per run: `accepted`, `problems`, which of the sandbox's super blocks the flooded rows took (`collisions`), the report's
`host_mounts_appeared` when the tree has it (absent from a tree before FU-CONF).
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("r3_conf_guest", ROOT / "validation" / "v21" / "sandbox" / "r3_conf_guest.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)
confine = g.confine

#: how many file systems an unrelated container start mounts between the session's end and the second reading
FLOOD = 48


def run(name: str, extra: list[str], flood: int) -> dict:
    base = pathlib.Path(tempfile.mkdtemp())
    lay = g.layout(base)
    spec = {"backend": "bwrap", "bwrap": g.BWRAP, "network": "host", "read_only": []}
    env = {"PATH": "/usr/bin:/bin", "HOME": str(lay["home"])}
    cmd = ["/bin/sh", "-c", confine.PROBE, "probe"]
    where = base / name
    repo, ws = confine._worktree(where, lay["repo"])
    full, inside_env = confine.wrap(spec, cmd, env, str(ws), str(lay["exe"]), system="linux")
    i = full.index("--chdir")
    full = full[:i] + extra + full[i:]
    rep = {"backend": "bwrap", "bwrap": g.BWRAP, "network": "host", "read_only": [], "client": str(lay["exe"]),
           "system": "linux", "operator_uid": os.getuid()}
    real, readings, mounted, errors = confine._host_mounts, [], [], []

    def second_reading_after_a_container_start():
        """The first call is the reading before the session; the second is the one after it ended."""
        first = not readings
        if not first and flood:
            for k in range(flood):
                d = base / f"unrelated-{k}"
                d.mkdir()
                p = subprocess.run(["mount", "-t", "tmpfs", "tmpfs", str(d)], capture_output=True, text=True)
                if p.returncode == 0:
                    mounted.append(d)
                else:
                    errors.append(p.stderr.strip()[:200])
        got = real()
        readings.append(got)
        for d in mounted:
            subprocess.run(["umount", str(d)], capture_output=True, text=True)
        mounted.clear()
        return got
    confine._host_mounts = second_reading_after_a_container_start
    try:
        rep = confine._probe(spec, where, ws, full, inside_env, env, cmd, rep)
    finally:
        confine._host_mounts = real
    g.git("-C", str(repo), "worktree", "remove", "--force", str(ws))
    before, after = readings[0] or [], readings[1] or []
    held = {r["dev"] for r in before}
    new = [r for r in after if r not in before]
    sandbox = {m["dev"]: m["at"] for m in rep["inside"]["mounts"] if m["access"] == "rw"}
    return {"extra": extra, "flood_requested": flood, "flood_mounted": len(new), "mount_errors": errors[:3],
            "accepted": not rep["problems"], "problems": rep["problems"],
            "collisions": [{"dev": r["dev"], "sandbox_mount": sandbox[r["dev"]], "unrelated_host_mount": r["at"]}
                           for r in new if r["dev"] in sandbox],
            "collisions_with_the_reading_before": sorted(d for d in sandbox if d in held),
            "host_mounts_appeared": rep.get("host_mounts_appeared", "absent (the tree predates FU-CONF)"),
            "host_mounts_rows": len(rep["host_mounts"] or [])}


def reuse() -> dict:
    return {"baseline-no-flood": run("baseline-no-flood", [], 0),
            "baseline-flood": run("baseline-flood", [], FLOOD),
            "host-mqueue-bound-flood": run("host-mqueue-bound-flood", ["--dev-bind", "/dev/mqueue", "/hostmq"], FLOOD),
            "host-mqueue-bound-no-flood": run("host-mqueue-bound-no-flood", ["--dev-bind", "/dev/mqueue", "/hostmq"], 0)}


if __name__ == "__main__":
    if sys.argv[1:] != ["reuse"] and sys.argv[1:] != ["reuse", "inner"]:
        raise SystemExit(__doc__)
    if sys.argv[2:] != ["inner"]:
        os.execvp("unshare", ["unshare", "--user", "--map-root-user", "--mount", "python3", "-B",
                              str(pathlib.Path(__file__).resolve()), "reuse", "inner"])
    print(json.dumps({"environment": g.environment(), "tree": str(ROOT), "flood": FLOOD, "record": reuse()},
                     indent=1, sort_keys=True))
