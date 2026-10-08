"""Linux guest checks of the session confinement and of process ownership (V2.1 F; owner 2026-10-08, item 5).

Runs INSIDE a Docker Desktop Linux container, started by linux_guest.sh (which states every docker flag) — never on
the host. The tree is mounted read-only at /repo and the container is discarded (--rm). Roles (argv[1]):

  canary NAME   a process the checks did not start (the entry shell starts it): records every catchable signal it gets
  a             a setsid descendant of a confined session, started with client.session's own calls (the argv it
                builds, confine.wrap, then ProcessRange(name, argv, cwd=, env=, output=) with the defaults — grace
                GRACE_S, no final-wait bound — and start(); the harness then waits with r.wait, not wait_within):
                seen from outside, proved by cleanup_authority (no other route to signal it is tried), gone with the
                session — when the client ends ("end"), when cleanup_authority signals the pid it proved before the
                client ends ("proved"), and when the range's release ladder stops a running one ("release"); the pids
                the session sees inside claimed, and pids that DO exist outside but are not the session's claimed as
                if reported from inside (a sibling the harness started, the canaries); then confine.measure with the
                real bubblewrap twice: the kernel at /repo as a run imports it, and a venv in the container's own
                layer whose kernel copy and site the container user can write — measured once without bubblewrap
                (the control: every probe write lands) and once with it
  b             the route test_v21_confine.measure_in_range takes for an unconfined probe's setsid sleeper — the
                range's anchor, a subreaper, adopts it; cleanup_authority proves ancestry and birth; signal_owned
                signals it — run through that very function, every signal_owned call recorded with its proof
  c             the controller SIGKILLed while a confined session and its setsid descendant run: the kernel's session
                owner (client.session) and the python that called confine.measure (in-process, as run.execute does)
  d1            tests.v2.test_v21_confine whole, with recorders around measure_in_range, cleanup_authority.signal_owned
                and host_view/host_unchanged (each calls the real one): per test its outcome, what each measurement
                built and proved, and which of the roots host_unchanged compares this user could have written
  ctl-session ARGS / ctl-measure ARGS   the controllers c starts and kills

a, b and c also claim the processes the checks did not start (docker-init, the entry shell, the canaries) through a
LIVE cleanup_authority.signal_owned: none may be signalled, and each canary must still be alive with no signal logged.
Prints one JSON object. It signals only the controllers it started (its own Popen handles) and what cleanup_authority
proves (INV-MUTATION-AUTHORITY); it removes nothing. Never runs opencode; the container has no network."""
import contextlib
import dataclasses
import json
import os
import pathlib
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO = pathlib.Path("/repo")
sys.path[:0] = [str(REPO), str(REPO / "validation" / "v2")]
from aisef2.app import client, confine  # noqa: E402
from aisef2.runtime.process_range import GRACE_S, ProcessRange, RangeEscaped, RangeNotEmpty  # noqa: E402
import cleanup_authority as ca  # noqa: E402

G = pathlib.Path("/tmp/g")  # shared with the entry shell: the canaries' pid files, the boundary mark
GIT = {"HOME": "/tmp", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin"}
SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
CANARIES = ("early", "early-setsid", "late")
#: the fake client: starts a setsid sleeper, writes what it sees inside to the workspace (its only writable host
#: path), then runs until the observer creates ./go
CLIENT = """#!/bin/sh
setsid sleep {marker} </dev/null >/dev/null 2>&1 &
s=$!
sleep 0.2
{{ echo "client $$"; echo "sleeper $s"; echo "pidns $(readlink /proc/self/ns/pid)"; echo "sleeper_sid $(cut -d' ' -f6 /proc/$s/stat)";
   echo "visible $(cd /proc && echo [0-9]*)"; }} > ./inside.tmp
mv ./inside.tmp ./inside.txt
while [ ! -e ./go ]; do sleep 0.05; done
"""


def stat(pid: int) -> dict | None:
    """This harness's own reading of /proc/<pid>: identity (pid, start in clock ticks since boot), state, parent,
    group, session, command line; None when gone."""
    try:
        s = pathlib.Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        cmd = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        return None
    f = s[s.rindex(")") + 2:].split()
    return {"pid": pid, "state": f[0], "ppid": int(f[1]), "pgid": int(f[2]), "sid": int(f[3]), "start": int(f[19]),
            "cmd": cmd[:160]}


def table() -> dict[int, dict]:
    return {p["pid"]: p for p in (stat(int(n)) for n in os.listdir("/proc") if n.isdigit()) if p}


def ident(p: dict) -> tuple[int, int]:
    return p["pid"], p["start"]


def alive(i) -> bool:
    p = stat(i[0])
    return p is not None and p["start"] == i[1] and p["state"] not in ("Z", "X")


def below(t: dict, root: int) -> list[dict]:
    """Every process whose parent chain in `t` reaches `root` (not `root` itself)."""
    out, todo = [], [root]
    while todo:
        parent = todo.pop()
        kids = [p for p in t.values() if p["ppid"] == parent and p not in out]
        out += kids
        todo += [p["pid"] for p in kids]
    return out


def chain(t: dict, pid: int) -> list[dict]:
    out = []
    while pid in t and len(out) < 64:
        out.append(t[pid])
        if pid == os.getpid() or t[pid]["ppid"] == pid:
            break
        pid = t[pid]["ppid"]
    return out


def ps() -> list[str]:
    return subprocess.run(["ps", "-A", "-o", "pid,ppid,pgid,sid,stat,lstart,args"], capture_output=True, encoding="utf-8",
                          errors="replace").stdout.splitlines()


def report(r: ca.Report) -> dict:
    return {"signalled": r.signalled, "unproven": r.unproven}


def until(test, seconds: float, step: float = 0.02):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        v = test()
        if v:
            return v
        time.sleep(step)
    return test()


# ------------------------------------------------------------------------------------------- what the checks did not start

def canary(name: str) -> None:
    got = G / f"canary-{name}.signals"

    def note(sig, _):
        with open(got, "a", encoding="utf-8") as fh:
            fh.write(signal.Signals(sig).name + "\n")
    for s in signal.valid_signals():
        if s not in (signal.SIGKILL, signal.SIGSTOP):
            try:
                signal.signal(s, note)
            except (OSError, ValueError):
                pass
    me = stat(os.getpid())
    (G / f"canary-{name}.tmp").write_text(json.dumps([me["pid"], me["start"]]), encoding="utf-8")
    os.replace(G / f"canary-{name}.tmp", G / f"canary-{name}.pid")
    while True:
        signal.pause()


def establish() -> tuple[ca.Boundary, dict]:
    """The boundary, established after the early canaries and before the late one (the entry shell starts it once
    /tmp/g/boundary exists): one is older than the boundary, the other younger — neither a descendant of this runner."""
    if not until(lambda: all((G / f"canary-{n}.pid").exists() for n in CANARIES[:2]), 30):
        raise SystemExit("the early canaries did not start")
    b = ca.establish("/tmp")
    (G / "boundary").write_text(json.dumps(dataclasses.asdict(b)), encoding="utf-8")
    if not until(lambda: (G / "canary-late.pid").exists(), 30):
        raise SystemExit("the late canary did not start")
    return b, {n: tuple(json.loads((G / f"canary-{n}.pid").read_text(encoding="utf-8"))) for n in CANARIES}


def foreign(b: ca.Boundary, can: dict) -> dict:
    """Claim, LIVE, every process the checks did not start — docker-init, the entry shell, the canaries — and their
    groups (the entry shell's is this harness's own): whatever cleanup_authority proved, it would signal now."""
    t = ca.host_table()
    pids = [1, os.getppid(), *[can[n][0] for n in CANARIES]]
    groups = sorted({t[p].pgid for p in pids if p in t})
    r = ca.signal_owned(b, pids=pids, groups=groups, table=t)
    time.sleep(0.5)
    return {"claimed_pids": pids, "claimed_groups": groups, "host_rows": {p: dataclasses.asdict(t[p]) for p in pids if p in t},
            **report(r), "canaries_after": canaries(can)}


def canaries(can: dict) -> dict:
    out = {}
    for n in CANARIES:
        f = G / f"canary-{n}.signals"
        out[n] = {"pid": can[n][0], "alive_same_start": alive(can[n]),
                  "signals_received": f.read_text(encoding="utf-8").split() if f.exists() else []}
    return out


# ------------------------------------------------------------------------------------------- a confined session's world

def world(base: pathlib.Path) -> dict:
    base.mkdir(parents=True)
    repo, ws, home = base / "repo", base / "work" / "ws", base / "home"
    repo.mkdir()
    for a in (["init", "-q", "-b", "main"], ["-c", "user.name=g", "-c", "user.email=g@l", "commit", "-q", "--allow-empty", "-m", "x"],
              ["worktree", "add", "-q", "--detach", str(ws)]):
        subprocess.run(["git", "-C", str(repo), *a], check=True, env=GIT)
    (home / ".config" / "opencode").mkdir(parents=True)
    marker = f"3600.{secrets.randbelow(10**6):06d}"
    exe = base / "client" / "opencode"
    exe.parent.mkdir()
    exe.write_text(CLIENT.format(marker=marker), encoding="utf-8")
    exe.chmod(0o755)
    return {"base": str(base), "repo": str(repo), "ws": str(ws), "exe": str(exe), "marker": marker,
            "env": {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(home), "LANG": "C"}}


def inside(w: dict) -> dict:
    lines = pathlib.Path(w["ws"], "inside.txt").read_text(encoding="utf-8").splitlines()
    return {k: v for k, _, v in (ln.partition(" ") for ln in lines)}


def sleeper(w: dict) -> dict | None:
    hits = [p for p in table().values() if p["cmd"] == f"sleep {w['marker']}"]
    return hits[0] if len(hits) == 1 else None


def gone_within(ids, seconds: float) -> dict:
    """How long after now until none of `ids` is alive (zombie counts as gone), and what was still there at the end."""
    t0 = time.monotonic()
    until(lambda: not any(alive(i) for i in ids), seconds, 0.005)
    return {"seconds": round(time.monotonic() - t0, 3), "still_alive": [i for i in ids if alive(i)],
            "zombies": [i for i in ids if (p := stat(i[0])) and p["start"] == i[1] and p["state"] == "Z"]}


# ------------------------------------------------------------------------------------------- the checks

def check_a() -> dict:
    b, can = establish()
    out = {"boundary": dataclasses.asdict(b), "runner": stat(os.getpid())}
    for mode in ("end", "proved", "release"):
        out[mode] = session_a(b, can, mode)
    w = world(pathlib.Path("/tmp/a-measure"))
    # the kernel as a run imports it (/repo, read-only here) and this interpreter's site (root's): the container user
    # cannot write either even without bubblewrap (operator_can), so those two denials are not bubblewrap's
    out["measure"] = summary(confine.measure(SPEC, pathlib.Path(w["base"]) / "m", w["exe"], pathlib.Path(w["repo"]),
                                             environ=w["env"]))
    # discriminating: the tests' own construction (a venv in the container's writable layer, a copy of aisef2 in its
    # site), so the kernel copy, the site, the run, client and git directories are all the container user's
    import tests.v2.test_v21_confine as tc
    out["measure_venv"] = {}
    for name, bwrap in (("control_without_bubblewrap", None), ("bubblewrap", SPEC["bwrap"])):
        tmp = pathlib.Path(os.path.realpath(tempfile.mkdtemp(prefix=f"a-{name}-", dir="/tmp")))
        exe = tmp / "client" / "opencode"
        exe.parent.mkdir()
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        rep, probes, site = tc.measure_in_range(tmp, dict(SPEC, bwrap=bwrap or str(tc.fake_bwrap(tmp))),
                                                tmp / "run" / "confinement", exe)
        out["measure_venv"][name] = {"bwrap": bwrap or "test_v21_confine.NOT_A_SANDBOX (runs the probe unconfined)",
                                     "tmp": str(tmp), "venv_site": str(site), "probe_calls": probes, **summary(rep)}
    out["foreign"] = foreign(b, can)
    return out


def summary(rep: dict) -> dict:
    """What a measurement says about each write it tried: could the container user write there without bubblewrap
    (the product's own operator_can), did the probe's file appear (created_outside_workspace), and the probe's exit
    and message for it."""
    tried = rep.get("tried", {})
    return {**{k: rep.get(k) for k in ("problems", "setsid_survivors", "left_on_host", "bwrap_version", "bwrap_sha256",
                                       "operator_can", "created_outside_workspace")},
            "tried_writes": {k: tried.get(k) for k in tried if k.startswith("write_")},
            "namespaces": rep.get("inside", {}).get("namespaces"), "tried_setsid": tried.get("setsid")}


def session_a(b: ca.Boundary, can: dict, mode: str) -> dict:
    w = world(pathlib.Path(f"/tmp/a-{mode}"))
    name = f"a-{mode}"      # client.session's argv, then its wrap and its ProcessRange call (client.py, session())
    command = [w["exe"], "run", "--format", "json", "--model", "fake/model", "--title", name, "--dir", w["ws"], "the prompt"]
    argv, env = confine.wrap(SPEC, command, w["env"], w["ws"], w["exe"])
    rec: dict = {"argv": argv, "process_range": {"name": name, "cwd": w["ws"], "grace_s": list(GRACE_S), "wait_s": None,
                                                 "waited_with": "r.wait(30), not client.wait_within"}}
    with open(pathlib.Path(w["base"]) / "session.log", "w", encoding="utf-8") as fh:
        r = ProcessRange(name, argv, cwd=w["ws"], env=env, output=fh)
        r.start()
        try:
            if not until(lambda: pathlib.Path(w["ws"], "inside.txt").exists(), 20):
                rec["error"] = "the client did not report"
                return rec
            t, s = table(), sleeper(w)
            rec["inside"] = inside(w)
            rec["sleeper_outside"] = s
            rec["chain_to_runner"] = chain(t, s["pid"]) if s else None
            session = [ident(p) for p in below(t, r.group)]
            rec["range"] = {"anchor_pid_and_group": r.group, "target_bwrap": r.target_pid,
                            "members": [(p.pid, p.command[:80]) for p in r.members()],
                            "escaped": [(p.pid, p.command[:80]) for p in r.escaped()], "session_processes": session}
            rec["proof_of_the_outside_pid"] = report(ca.signal_owned(b, pids=[s["pid"]], dry_run=True)) if s else None
            claimed = [int(rec["inside"]["client"]), int(rec["inside"]["sleeper"])]
            rec["inside_pids_claimed"] = {"claimed": claimed, "what_they_name_outside": {p: t.get(p) for p in claimed},
                                          "dry_run": report(ca.signal_owned(b, pids=claimed, dry_run=True))}
            if mode == "end":
                rec["inside_pid_collision"] = collision(b, can)
            if mode == "proved":     # LIVE: what cleanup_authority proved, it signals; the session goes on
                rec["proved_signal"] = report(ca.signal_owned(b, pids=[s["pid"]]))
                rec["sleeper_after_proved_signal"] = gone_within([ident(s)], 2.0)
                rec["client_alive_after_proved_signal"] = alive(ident(t[s["ppid"]]))
            if mode in ("end", "proved"):
                pathlib.Path(w["ws"], "go").touch()
                rec["client_exit"] = r.wait(30)
                rec["after_bwrap_returned"] = gone_within([ident(s)], 2.0)
        finally:
            try:
                r.release()
                rec["release"] = {"raised": None, "ledger": [x["stage"] for x in r.ledger]}
            except (RangeEscaped, RangeNotEmpty) as e:
                rec["release"] = {"raised": f"{type(e).__name__}: {e}", "ledger": [x["stage"] for x in r.ledger]}
    rec["after_release"] = gone_within(session, 2.0)
    rec["marker_in_table_after"] = [p for p in table().values() if w["marker"] in p["cmd"]]
    return rec


def collision(b: ca.Boundary, can: dict) -> dict:
    """The inside pids above name nothing in this container's table, so their refusal says only that. Here pids that
    DO exist outside and are not the session's are claimed as a report from inside would claim them, in a dry run:
    the canaries (not the runner's: refused on birth and descent) and a sibling this harness starts now (the runner's
    own child, born after the boundary: cleanup_authority proves it — it proves ownership by the runner, not
    membership of the session). The sibling is waited for, never signalled."""
    sib = subprocess.Popen(["sleep", "1.5"])
    try:
        t = ca.host_table()
        pids = [sib.pid, *[can[n][0] for n in CANARIES]]
        return {"sibling": dataclasses.asdict(t[sib.pid]) if sib.pid in t else None,
                "claimed": {"sibling": sib.pid, **{n: can[n][0] for n in CANARIES}},
                "dry_run": report(ca.signal_owned(b, pids=pids, dry_run=True, table=t))}
    finally:
        sib.wait()


def check_b() -> dict:
    b, can = establish()
    import tests.v2.test_v21_confine as tc
    assert tc.ca is ca and tc.ProcessRange is ProcessRange
    calls, real = [], ca.signal_owned

    def recording(boundary, pids=(), groups=(), **k):
        t, mine = ca.host_table(), table()
        mine = {p: chain(mine, p) for p in pids}   # this harness's own reading: the claimed pid up to the runner
        r = real(boundary, pids=pids, groups=groups, table=t, **k)
        calls.append({"boundary": dataclasses.asdict(boundary), "claimed": list(pids), "groups": list(groups),
                      "host_rows": {p: dataclasses.asdict(t[p]) for p in pids if p in t}, "harness_view": mine, **report(r)})
        return r
    tmp = pathlib.Path(os.path.realpath(tempfile.mkdtemp(prefix="b-", dir="/tmp")))
    exe = tmp / "client" / "opencode"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    ca.signal_owned = recording
    try:
        rep, probes, site = tc.measure_in_range(tmp, dict(tc.SPEC, bwrap=str(tc.fake_bwrap(tmp))), tmp / "run" / "confinement", exe)
    finally:
        ca.signal_owned = real
    signalled = [ident(c["harness_view"][x["id"]][0]) for c in calls for x in c["signalled"] if c["harness_view"].get(x["id"])]
    return {"boundary": dataclasses.asdict(b), "runner": stat(os.getpid()), "signal_owned_calls": calls,
            "measurement_reported_survivors": rep["setsid_survivors"], "probe_calls": probes, "left_on_host": rep["left_on_host"],
            "venv_site": str(site), "signalled_alive_after": [i for i in signalled if alive(i)],
            "reported_claimed_again_after": report(ca.signal_owned(b, pids=rep["setsid_survivors"], dry_run=True)),
            "foreign": foreign(b, can)}


def check_d1() -> dict:
    """tests.v2.test_v21_confine whole (the tests `python -m unittest tests.v2.test_v21_confine` loads), with
    recorders that call the real functions: what each measure_in_range built (its venv site, the probe's call, what
    it reported), every cleanup_authority.signal_owned call with its proof and this harness's own reading of the
    claimed pid's parent chain, what host_view watched — with whether this user could write each root at all — and
    every host_unchanged comparison. Nothing is signalled here but by the tests' own route."""
    import unittest
    import tests.v2.test_v21_confine as tc
    assert tc.ca is ca
    now, out = [None], {"measure_in_range": [], "signal_owned": [], "host_view": None, "host_view_calls": 0,
                        "host_unchanged": []}
    real = {"mir": tc.measure_in_range, "so": ca.signal_owned, "view": tc.host_view, "same": tc.host_unchanged}

    def mir(tmp, spec, where, exe):
        rec = {"test": now[0], "tmp": str(tmp), "bwrap": spec["bwrap"]}
        with contextlib.suppress(OSError):
            rec["bwrap_is"] = {tc.RUNS_NOTHING: "RUNS_NOTHING", tc.NOT_A_SANDBOX: "NOT_A_SANDBOX"}.get(
                pathlib.Path(spec["bwrap"]).read_text(encoding="utf-8"), "another script")
        out["measure_in_range"].append(rec)
        try:
            rep, probes, site = real["mir"](tmp, spec, where, exe)
        except BaseException as e:
            rec["raised"] = f"{type(e).__name__}: {str(e)[:300]}"
            raise
        rec.update(venv_site=str(site), probe_calls=probes, setsid_survivors=rep["setsid_survivors"],
                   left_on_host=rep["left_on_host"], created_outside_workspace=rep.get("created_outside_workspace"))
        return rep, probes, site

    def so(boundary, pids=(), groups=(), **k):
        mine = table()
        r = real["so"](boundary, pids=pids, groups=groups, **k)
        out["signal_owned"].append({"test": now[0], "claimed": list(pids), "groups": list(groups), **report(r),
                                    "harness_view": {p: chain(mine, p)[:3] for p in pids}})
        return r

    def view():
        v = real["view"]()
        out["host_view_calls"] += 1
        if out["host_view"] is None:
            roots = {k: (str(REPO / "aisef2") if k == "kernel" else k.split(" ", 1)[1]) for k in v["exact"]}
            roots.update({k: k.split(" ", 1)[1] for k in v["names"]})
            out["host_view"] = {k: {"entries": len((v["exact"] | v["names"])[k]), "this_user_can_write": os.access(p, os.W_OK)}
                                for k, p in roots.items()}
        return v

    def same(before):
        try:
            real["same"](before)
            out["host_unchanged"].append({"test": now[0], "unchanged": True})
        except AssertionError as e:
            out["host_unchanged"].append({"test": now[0], "unchanged": False, "said": str(e)[:300]})
            raise

    class Result(unittest.TestResult):
        def startTest(self, test):
            now[0] = test.id().split(".", 3)[-1]
            super().startTest(test)
    tc.measure_in_range, ca.signal_owned, tc.host_view, tc.host_unchanged = mir, so, view, same
    try:
        result = Result()
        with contextlib.redirect_stdout(sys.stderr):
            unittest.defaultTestLoader.loadTestsFromModule(tc).run(result)
    finally:
        tc.measure_in_range, ca.signal_owned, tc.host_view, tc.host_unchanged = real["mir"], real["so"], real["view"], real["same"]
    out["result"] = {"ran": result.testsRun, "failures": [t.id() for t, _ in result.failures],
                     "errors": [t.id() for t, _ in result.errors], "skipped": [t.id() for t, _ in result.skipped],
                     "details": [s[-600:] for _, s in result.failures + result.errors]}
    out["platform"] = {"sys.platform": sys.platform, "setsid": shutil.which("setsid"), "ps": shutil.which("ps"),
                       "uid": os.getuid(), "HOME": os.environ.get("HOME")}
    return out


def check_c() -> dict:
    b, can = establish()
    out = {"boundary": dataclasses.asdict(b), "runner": stat(os.getpid()), "session_owner": kill_session_owner()}
    out["measure_caller"] = [kill_measure_caller(i) for i in range(3)]
    out["ps_at_end"] = ps()
    out["foreign"] = foreign(b, can)
    return out


def controller(role: str, w: dict, log: pathlib.Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-B", __file__, role, json.dumps(w)], stdout=log.open("w", encoding="utf-8"),
                            stderr=subprocess.STDOUT)


def kill_session_owner() -> dict:
    w = world(pathlib.Path("/tmp/c-session"))
    ctl = controller("ctl-session", w, pathlib.Path(w["base"]) / "ctl.log")
    rec: dict = {"controller": ctl.pid}
    if not until(lambda: pathlib.Path(w["ws"], "inside.txt").exists(), 30):
        ctl.kill()
        ctl.wait()
        return {**rec, "error": "the client did not report", "log": (pathlib.Path(w["base"]) / "ctl.log").read_text(encoding="utf-8")}
    t, s = table(), sleeper(w)
    session = [ident(t[ctl.pid]), *[ident(p) for p in below(t, ctl.pid)]]
    rec.update(inside=inside(w), sleeper_outside=s, chain_to_runner=chain(t, s["pid"]) if s else None,
               before_kill=[t[i[0]] for i in session])
    ctl.kill()                                   # SIGKILL, through this harness's own handle
    rec["controller_exit"] = ctl.wait()
    rec["after_kill"] = gone_within(session, 5.0)
    rec["marker_in_table_after"] = [p for p in table().values() if w["marker"] in p["cmd"]]
    return rec


def kill_measure_caller(n: int) -> dict:
    """SIGKILL the python running confine.measure once its probe's setsid sleeper is seen alive (the probe takes
    tens of milliseconds: each try that finished first is recorded and retried, up to 30)."""
    tries = []
    for i in range(30):
        w = world(pathlib.Path(f"/tmp/c-measure-{n}-{i}"))
        ctl = controller("ctl-measure", w, pathlib.Path(w["base"]) / "ctl.log")
        seen = None
        while ctl.poll() is None and seen is None:
            for d in os.listdir("/proc"):
                if d.isdigit():
                    try:
                        c = pathlib.Path(f"/proc/{d}/cmdline").read_bytes()
                    except OSError:
                        continue
                    if c.startswith(f"sleep\0{confine.SLEEPER}.".encode()):
                        seen = int(d)
                        break
        if seen is None:
            ctl.wait()
            tries.append({"try": i, "caught": False, "controller_exit": ctl.returncode})
            continue
        t = table()
        session = [ident(t[ctl.pid]), *[ident(p) for p in below(t, ctl.pid)]]
        ctl.kill()                               # SIGKILL, through this harness's own handle
        code = ctl.wait()
        return {"tries_before": tries, "try": i, "caught": True, "sleeper_outside": t.get(seen),
                "chain_to_runner": chain(t, seen), "before_kill": [t[x[0]] for x in session], "controller_exit": code,
                "after_kill": gone_within(session, 5.0),
                "sleeper_in_table_after": [p for p in table().values() if f"sleep {confine.SLEEPER}." in p["cmd"]]}
    return {"tries_before": tries, "caught": False}


def ctl_session(w: dict) -> None:
    logs = pathlib.Path(w["base"]) / "logs"
    budget = client.Budget({k: 100 for k in client.Budget.KEYS}, {k: 0 for k in client.Budget.KEYS}, logs, requests=lambda: 1)
    print(json.dumps(client.session("S1", "the prompt", w["ws"], logs / "S1.jsonl", 600, model="fake/model", env=w["env"],
                                    budget=budget, turn_cap=99, exe=w["exe"], confine=SPEC)))


def ctl_measure(w: dict) -> None:
    rep = confine.measure(SPEC, pathlib.Path(w["base"]) / "m", w["exe"], pathlib.Path(w["repo"]), environ=w["env"])
    print(json.dumps(rep["problems"]))


if __name__ == "__main__":
    role = sys.argv[1]
    if role == "canary":
        canary(sys.argv[2])
    elif role.startswith("ctl-"):
        {"ctl-session": ctl_session, "ctl-measure": ctl_measure}[role](json.loads(sys.argv[2]))
    else:
        print(json.dumps({"a": check_a, "b": check_b, "c": check_c, "d1": check_d1}[role](), indent=1, default=str))
