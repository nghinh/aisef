"""The setsid-survivor check against the PID namespace's teardown (V2.1 F, round 3): with X1's container flags
(seccomp and system paths loosened, uid 1000) and the run's network "host", call the kernel's confine.measure N times
and count the measurements whose FIRST look at the process table, as soon as bubblewrap returned, found the probe's
sleeper (the teardown race: one the kernel is still killing), and what the grace (confine.SURVIVOR_GRACE) then
reported. Then one measurement with a "bubblewrap" that confines nothing: its sleeper really outlives the session and
must still be reported on Linux's /proc table.
Run under the heavy lock, with the tree at /repo read-only (the round-3 run: a git archive of 3e0409c):

  docker run --rm --user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g --security-opt seccomp=unconfined \
    --security-opt systempaths=unconfined -v <tree>:/repo:ro -v <this file>:/race.py:ro aisef-sandbox-measure \
    python3 -B /race.py 500 [sock]

"sock" adds a unix socket directory to read_only (every measurement then refuses for it; the round-2 race was seen
there). It prints one JSON object; never runs the real opencode, never calls a provider."""
import json, os, pathlib, signal, socket, subprocess, sys, threading, time
sys.path.insert(0, "/repo")
from aisef2.app import confine
from aisef2.runtime import process_range
B = pathlib.Path("/tmp/r")
G = {"HOME": "/tmp", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin"}
repo = B / "repo"; repo.mkdir(parents=True)
for a in (["init", "-q", "-b", "main"], ["-c", "user.name=v", "-c", "user.email=v@l", "commit", "-q", "--allow-empty", "-m", "x"]):
    subprocess.run(["git", "-C", str(repo), *a], check=True, env=G)
exe = B / "runtime" / "opencode"; exe.parent.mkdir(); exe.write_text("#!/bin/sh\n"); exe.chmod(0o755)
home = B / "home"; (home / ".config" / "opencode").mkdir(parents=True)
env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(home), "LANG": "C"}
spec = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
sd = B / "sock"; sd.mkdir(); ls = socket.socket(socket.AF_UNIX); ls.bind(str(sd / "ctl")); ls.listen(8)
threading.Thread(target=lambda: [ls.accept()[0].close() for _ in iter(int, 1)], daemon=True).start()
if len(sys.argv) > 2:
    spec["read_only"] = [str(sd)]

real_table, looks = process_range.process_table, []


def counted():
    t = real_table()
    looks.append(t)
    return t


process_range.process_table = counted
t0 = time.time()
raced, reported, problem_counts = [], [], {}
for i in range(N):
    looks.clear()
    rep = confine.measure(spec, B / f"m{i}", str(exe), repo, system="linux", environ=env)
    first = [p for p, pr in looks[0].items() if f"sleep {confine.SLEEPER}." in pr.command] if looks else []
    if first:
        raced.append({"i": i, "first_look": first, "looks": len(looks), "reported": rep["setsid_survivors"]})
    if rep["setsid_survivors"]:
        reported.append({"i": i, "survivors": rep["setsid_survivors"], "problems": rep["problems"]})
    for p in rep["problems"]:
        problem_counts[p] = problem_counts.get(p, 0) + 1
out = {"measurements": N, "read_only_socket": len(sys.argv) > 2, "elapsed": round(time.time() - t0, 2),
       "first_look_found_a_sleeper": len(raced), "raced": raced, "reported_survivors": reported,
       "problem_counts": problem_counts}

# the positive control: an unconfined "bubblewrap" (drops every option, runs the command)
fake = B / "fake-bwrap"
fake.write_text('#!/bin/sh\nwhile [ $# -gt 0 ] && [ "$1" != "--" ]; do shift; done\n[ $# -gt 0 ] || exit 0\nshift\nexec "$@"\n')
fake.chmod(0o755)
looks.clear()
t1 = time.time()
rep = confine.measure(dict(spec, bwrap=str(fake), read_only=[]), B / "unconfined", str(exe), repo, system="linux", environ=env)
alive = {p: pathlib.Path(f"/proc/{p}/stat").exists() for p in rep["setsid_survivors"]}
for p in rep["setsid_survivors"]:
    try:
        os.kill(p, signal.SIGKILL)
    except ProcessLookupError:
        pass
out["unconfined_control"] = {"survivors": rep["setsid_survivors"], "alive_after_measure": alive, "looks": len(looks),
                             "seconds": round(time.time() - t1, 2),
                             "survivor_problem": [p for p in rep["problems"] if p.startswith("a process the session left")]}
print(json.dumps(out, indent=1))
