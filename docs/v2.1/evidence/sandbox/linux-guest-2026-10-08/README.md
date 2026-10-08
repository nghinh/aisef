# Linux guest checks, 2026-10-08 (V2.1 F; owner item 5)

What these files are: the output of `validation/v21/sandbox/linux_guest.sh` (harness `linux_guest.py`), run once,
on 2026-10-08 about 15:10 +07, against the tree at commit `860c02a`. They cover the sandbox checks that had never run
on Linux: (a) a setsid descendant of a confined session, (b) how the tests identify a process they own, (c) cleanup
when the controller dies, and (d) the two test modules run whole.

## The environment

The checks ran in a Linux container inside Docker Desktop's VM on a Mac. This is not a bare-metal Linux host, not
Ubuntu CI, and not a Linux VM that AISEF manages.

| Layer | What it was |
|---|---|
| host | macOS 26.5.2, Darwin 25.5.0 arm64 (`environment.txt`) |
| Docker | Docker Desktop 4.91.0 (239619), client and engine 29.8.0, engine `linux/arm64`, runc 1.4.3, cgroup v2 |
| Linux guest (Docker Desktop's VM) | kernel `Linux 7.0.12-linuxkit #1 SMP PREEMPT Thu Aug 27 14:02:21 UTC 2026 aarch64`, 8 CPUs, 7.75 GiB; AppArmor is not in this kernel (`SANDBOX-LINUX.md` §3) |
| image | `aisef-sandbox-measure`, id `sha256:568d868ab18d64f7da961ab103e604ff7e5d18fc05cfccaa1946890b0d8b15ed`, created 2026-10-07T02:35:50Z by the earlier sandbox run from `../Dockerfile.measure`: `python:3.14-slim-trixie@sha256:3353bb7e9ae99c7cce6cad2b2f2b174e8f22813ac43e3b13e7a742627d2b01d8` plus bubblewrap, git, libcap2-bin and util-linux, and user `op` (uid 1000). It was already local, so nothing was pulled or rebuilt. Inside: Python 3.14.8, bubblewrap 0.12.0 (`/usr/bin/bwrap` sha256 `b3b829e1…b976`, the same binary as the earlier evidence), and `ps from procps-ng 4.0.4` (next row). |
| `ps` | The image has no `ps`, and `cleanup_authority` needs it (`ps -A -o pid=,ppid=,pgid=,lstart=,command=`). So `ps` (sha256 `388a5062…9023`) and `libproc2.so.0` (sha256 `edb1e982…383d`) were copied with `docker cp` from the local image `postgres:16.15` (id `sha256:c1b3783309b6…`, Debian 13 trixie arm64, procps `2:4.0.4-9`, the same distribution as the measure image). They are mounted read-only into every container. |
| tree | `git archive 860c02a -- . ':(exclude)closure-evidence'` (tar sha256 `f644134d…16d7`, 1278 files, git tree `a7fb3d3e…`), extracted into the scratch directory and mounted read-only at `/repo`. `closure-evidence/` (376 MB of records) was left out; none of the checked code reads it. The copy was deleted after the run. |

**Container configuration.** Every container got these flags (`commands.txt` holds each full command):

```
--rm --init --network none --user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g --cpus 2 -w /repo
-v <tree>:/repo:ro -v <procps>/ps:/usr/local/bin/ps:ro -v <procps>/libproc2.so.0:/usr/lib/aarch64-linux-gnu/libproc2.so.0:ro
```

- `--init`: docker-init runs as PID 1 and reaps whatever is orphaned to it.
- `--network none`: the container's network namespace has only loopback, so a session with `network: host` shares a
  namespace that has no route out.
- Nothing from the host is writable: the tree and the two procps files are read-only, and everything else a check
  writes lands in the container's own layer, which `--rm` discards.
- The containers ran one after another, never two at once. The machine-wide heavy lock was not taken (this task does
  not touch it).

There are two profiles (`environment.txt`, "guest view"):

| Profile | Added flags | `/proc/self/status` | bubblewrap |
|---|---|---|---|
| **hardened** (b, d) | none | `Seccomp: 2` (Docker's filter), `CapEff`/`CapBnd` 0, `NoNewPrivs: 0` | cannot start: "No permissions to create a new namespace" (as P1 in `SANDBOX-LINUX.md` §3) |
| **X1** (a, c) | `--security-opt seccomp=unconfined --security-opt systempaths=unconfined` | `Seccomp: 0`, `CapEff`/`CapBnd` 0 | starts: this is the minimal loosening measured in §3 |

**Processes the checks did not start.** Each of a, b and c runs as a child of an entry shell
(`docker-init → sh -c ENTRY`). Before the harness starts, that shell starts two canaries: `early`, which shares the
shell's process group (and so the harness's group), and `early-setsid`, which has a session of its own. Once the
harness has established its `cleanup_authority` boundary, the shell starts a third canary, `late`. All three are
children of the shell, never of the harness. A canary handles every catchable signal by writing the signal's name to
a file. At the end of each check the harness makes a live `cleanup_authority.signal_owned` call that claims
docker-init (pid 1), the entry shell, the three canaries, and their three groups. The entry shell's group is the
harness's own. "Live" means that whatever this call proved to be the harness's, it would signal.

## Results

| Check | Profile | Result |
|---|---|---|
| a | X1 | The setsid descendant is gone as soon as the session ends, in all 3 ways a session ends. While the session runs, the descendant can be signalled only through a proof; the pids the session sees inside are refused. `confine.measure` with the real bwrap: 0 problems, `setsid_survivors: []`. |
| b | hardened | The tests' route ran on Linux: the anchor adopted the sleeper, `cleanup_authority` proved it, `signal_owned` signalled it. Its proof record is in `b.out`. |
| c | X1 | After the controller was SIGKILLed, nothing of the session was left within 6–7 ms. This held for `client.session`'s owner (1 run) and for `confine.measure`'s caller (3 runs). No process outside the session was signalled. |
| d | hardened | `tests.v2.test_v21_confine`: Ran 31 tests in 18.8 s, OK, 0 skipped. `tests.v2.p4.test_process_range`: Ran 24 tests in 19.1 s, OK, 0 skipped. |
| processes the checks did not start | (a, b, c) | In each check, `signalled: []` and all 8 claims unproven: "born before the boundary or not a descendant of the runner". All 3 canaries were alive with the same start time and had received no signal. |

All 5 containers exited 0 (`commands.txt`: 5 s, 7 s, 6 s, 21 s, 20 s). The `*.err` files of a, b and c are empty.

### (a) A setsid descendant of a confined session — `a.out`

The harness starts each session the way `client.session` does (`aisef2/app/client.py`, the `confinement.wrap` and
`ProcessRange` lines): `confine.wrap(SPEC, …)` with `SPEC = {bwrap: /usr/bin/bwrap, network: host, read_only: []}`,
then a `ProcessRange` whose target is the resulting bwrap argv (`a.out` `.end.argv`:
`--unshare-user --unshare-pid --unshare-ipc --unshare-uts --unshare-cgroup-try --share-net --disable-userns
--die-with-parent --new-session --cap-drop ALL …`). The client is a script. It starts
`setsid sleep 3600.<random>`, writes what it sees to the workspace (`inside.txt`), and waits for `./go`.

Execution path, from `.end.chain_to_runner` (outside pids):

```
harness (12) → range_anchor.py (30, its own session and group; the range) → bwrap (32, the target: the range's only
member) → bwrap's init in the new PID namespace (34, a session of its own: the range lists it as escaped) →
the client sh (36; pid 2 inside) → sleep 3600.x (37; pid 3 inside; setsid: its own session and group)
```

- **Visible from outside.** Yes, in the container's `/proc`, under its outside pid, with a parent chain to the
  harness.
- **What the range sees.** `ProcessRange.members()` is `[bwrap]`. `escaped()` is `[bwrap's init]`. The client and the
  sleeper are in neither list. The range's release signals only its group (the outer bwrap), so it never signals the
  sleeper itself.
- **Killable only through proof.** `cleanup_authority.signal_owned(boundary, pids=[37], dry_run=True)` proves the
  sleeper: `{pid 37, ppid 36, born 1791447040 ≥ since 1791447038, runner 12}`. The pids the session sees inside, 2 and
  3, are refused: "not in the host table". In mode `proved`, a live `signal_owned` signalled the proved pid (59). It
  was gone 5 ms later, and the client was still alive.
- **Dies with the session**, in all three modes. In `end`, the client exits 0, and when bwrap returned the sleeper
  was already gone at the first look (0.0 s). In `proved`, the same happened after the proved signal. In `release`,
  the client is still running when `ProcessRange.release()` runs. Its ladder needed only its first stage
  (`cooperative`, SIGINT to the group), and no `RangeEscaped` was raised. In every mode, none of the session's
  processes was alive and none was a zombie at the first look after release, and no process in the table carried the
  sleeper's marker.
- **The kernel's own measurement.** `confine.measure(SPEC, …)` with the real bubblewrap reported `problems: []` and
  `setsid_survivors: []`. Namespaces user, pid, ipc, uts and mnt were `own`, and net was `shared` (network host).

### (b) How the tests identify a process they own — `b.out`

The harness imports `tests.v2.test_v21_confine` and calls its `measure_in_range` itself. The bwrap is
`NOT_A_SANDBOX` (`fake_bwrap`), so the probe runs unconfined. That is what the tests do. The harness replaces
`cleanup_authority.signal_owned`, which is the same module object the test uses (`tc.ca is ca` is asserted), with a
recorder. The recorder reads the host table, calls the real function, and keeps its report.

Execution path: MEASURE runs in the venv in a `ProcessRange`, and the probe's `setsid sleep 120.102744` is pid 64.
When the probe's shell exits, the sleeper is reparented to the range's anchor, pid 27 (a subreaper,
`PR_SET_CHILD_SUBREAPER`). The harness's own reading of the chain is
`64 (ppid 27) → 27 range_anchor.py (ppid 13) → 13 the harness`. Then
`ca.owned(boundary)` with `ppid == r.group` gives `[64]`, and `signal_owned(pids=[64])` returns
`signalled: [{pid 64, ppid 27, pgid 64, born 1791447047 ≥ since 1791447046, runner 13, command "sleep 120.102744"}]`
with `unproven: []`. That was its only call. Afterwards:

- the signalled process is not alive (`signalled_alive_after: []`);
- the pid the measurement reported (`setsid_survivors: [64]`), claimed again, is "not in the host table";
- the measurement named the probe's 5 files in `left_on_host`, all under the test's temp dir and its venv;
- MEASURE's spy recorded the probe call `(120.102744, 60)`.

### (c) Cleanup when the controller dies — `c.out`

The observer (the harness) starts each controller as its own child, which has no session of its own and so shares
the observer's group 7 with the `early` canary. It SIGKILLs the controller through its own `Popen` handle.

1. **The kernel's session owner.** The controller calls `client.session("S1", …, confine=SPEC)` with a `Budget`. The
   session runs the same script client as (a), which never gets `./go`. Before the kill (`.session_owner.before_kill`),
   the processes were:
   - 30, the controller (group 7);
   - 31, the anchor (group 31);
   - 33, the outer bwrap (group 31);
   - 36, bwrap's init (session 36);
   - 37, the client (session 36);
   - 38, the setsid sleeper (session 38);
   - 44, a short `sleep 0.05`.

   The controller died with -9. 6 ms later none of them was alive and none was a zombie (`still_alive: []`,
   `zombies: []`), and no process carried the marker.
2. **The python that called `confine.measure`, in-process as `run.execute` calls it.** The observer scans `/proc`
   until the probe's `sleep 120.x` appears (it lives only while the probe runs), then SIGKILLs the controller. All 3
   runs caught it on the first try, with `find` still running. Before the kill, the processes were the controller,
   the outer bwrap (group 7, the controller's child), bwrap's init, the probe shell, the setsid sleeper, `find` and
   `head`. 6–7 ms later none was alive and none was a zombie.
3. **Nothing outside the session was signalled.**
   - The canaries, including `early` in the controller's own group 7, were alive with the same start time and had
     received no signal.
   - `ps_at_end` lists only docker-init, the entry shell and its subshell, the 3 canaries (state `S`), the harness and
     `ps` itself.
   - The live claim of the processes the checks did not start signalled nothing.

What (c) shows is the outcome. It does not separate the two mechanisms that both apply when the session owner dies:
the anchor's watchdog (end of file on stdin, then `killpg` of its own group) and bwrap's `--die-with-parent`. When the
measure caller dies, the only mechanism is bwrap's `--die-with-parent` (its parent is the controller).

### (d) The two test modules, whole — `d-test_v21_confine.err`, `d-test_process_range.err`

These ran with `python3 -B -m unittest -v`, cwd `/repo` (read-only), under the hardened profile, in a container of
their own. Both modules: OK, 0 skipped, 0 failures. The Linux-only paths ran:

- `test_an_orphan_the_range_adopts_is_reaped_when_it_dies` (subreaper);
- the `measure_in_range` tests, where the sleeper was proved and signalled through `cleanup_authority`;
- the `HostGuard` comparison: the guest's site-packages, `/repo/aisef2`, and the names in `/repo` and `/home/op`
  were unchanged.

The ResourceWarnings in the log come from `aisef2/orchestrate/story_runner.py`. They do not fail any test.

## What this does not show

- **Not a bare-metal Linux host, not Ubuntu CI, and not other kernels.** It is one Docker Desktop VM kernel
  (7.0.12-linuxkit, arm64). Profiles a and c need the container's seccomp filter off and its system paths unmasked
  (`SANDBOX-LINUX.md` §3).
- **No real `opencode` client and no provider.** The client is a script, and the container has no network.
- **`ps` comes from another local image** (same distribution and architecture, files and digests above). It is not
  part of the measure image.
- **Every process count comes from one run per check**, and each measure-caller kill from one try (3 runs). These are
  observations, not rates.
- **SIGSTOP is not ruled out for checks a and b.** A canary that was alive with no signal logged could not have
  received a catchable signal or SIGKILL. A SIGSTOP would leave it stopped, and the canary check reads only
  alive/dead. For check c, `ps_at_end` shows every canary in state `S`; checks a and b have no such listing.
- **Not exercised:**
  - `validation/v21/sandbox/teardown_race.py`. It still `os.kill`s pids taken from `rep['setsid_survivors']`, which
    is an INV-MUTATION-AUTHORITY pattern, and it is unchanged.
  - The docker matrix of `run.sh` (P1–P5, X1–X3) was not re-run.
  - A confined `aisef run` end to end (M6).
