# Linux guest checks, 2026-10-08, round 2 (V2.1 F; owner item 5)

What these files are: the output of `validation/v21/sandbox/linux_guest.sh` (harness `linux_guest.py`), run once, on
2026-10-08 from 16:10:37 to 16:12:18 +07, against the tree at commit `f9249f5`. They replace the round-1 evidence
([`../linux-guest-2026-10-08/`](../linux-guest-2026-10-08/README.md), tree `860c02a`, kept as it was) after the
round-1 verifier's findings: check a's write denials and its inside-pid refusal are now discriminating, the session
is started with `client.session`'s own calls, d1 has evidence beyond its `-v` transcript, and every environment
detail is in `environment.txt`. Every check of round 1 ran again here, in the same container configuration.

`gates-f9249f5.txt` holds the pre-commit gates of the tree measured (`ruff check --no-cache .`,
`destructive_authority.py --check`, `tests.test_meta`), run on the macOS host just before `f9249f5` was committed.

## The environment

The checks ran in Linux containers inside Docker Desktop's VM on a Mac. This is not a bare-metal Linux host, not
Ubuntu CI, and not a Linux VM that AISEF manages. Every value below is in `environment.txt` or `commands.txt`.

| Layer | What it was |
|---|---|
| host | macOS 26.5.2, Darwin 25.5.0 arm64. Host load average 7.55 at the start, 10.58 at the end (one-minute figure; a mutation campaign with 4 workers ran on this machine throughout). Timings below were taken under that load. |
| Docker | Docker Desktop 4.91.0 (239619); client and engine 29.8.0 (API 1.56); engine `linux/arm64`; containerd v2.3.4; runc 1.4.3; docker-init 0.19.0; cgroup v2; default seccomp profile `builtin` |
| other containers in the same VM | `postgres:16.15` and `valkey/valkey:9.1.1`, both up 13 days, not started by these checks and not touched |
| Linux guest (Docker Desktop's VM) | kernel `Linux 7.0.12-linuxkit #1 SMP PREEMPT Thu Aug 27 14:02:21 UTC 2026 aarch64`, 8 CPUs, 8 319 770 624 bytes; `max_user_namespaces` 31880; AppArmor is not in this kernel |
| image | `aisef-sandbox-measure`, id `sha256:568d868ab18d64f7da961ab103e604ff7e5d18fc05cfccaa1946890b0d8b15ed`, created 2026-10-07T02:35:50Z from `../Dockerfile.measure`; Debian 13.7; Python 3.14.8; bubblewrap 0.12.0 (`/usr/bin/bwrap` sha256 `b3b829e18a7d43ee589dc37e351cb9480ff7301b493d8227b8c754294638b976`). Already local: nothing was pulled or built. |
| `ps` | The image has no `ps`; `cleanup_authority` needs it. `ps` (sha256 `388a50620b101a212cee94b180d867240a142a397c9270ff3d6c5244fd979023`) and `libproc2.so.0` (sha256 `edb1e9823b60ea9bc4dc244445b4802863c745ec804e4318a16a131699b5383d`) are the round-1 copies (`docker cp` from the local image `postgres:16.15`, id `sha256:c1b3783309b6499c795eed7c20135a1a4d25cae1b575c3d52c6f536129a1b109`), digests re-checked. That image is Debian **13.6** with `procps` and `libproc2-0` `2:4.0.4-9` (read in one container of it, no network); the measure image is Debian **13.7**: the same distribution (trixie), not the same point release. Both files are mounted read-only into every container. |
| tree | `git archive f9249f5 -- . ':(exclude)closure-evidence'`: tar sha256 `317088e610dbdf9150c46135153c070ab50d1c69df3b3634221a91de53d99d37`, 1291 files; the commit's tree (with `closure-evidence/`) is `836742b107f480194d06443e2fa9adcbc4101ac9`. Extracted into the scratch directory and mounted read-only at `/repo`; the copy is deleted after the run. |

**Container configuration** (each full command in `commands.txt`):

```
--rm --init --network none --user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g --cpus 2 -w /repo
-v <tree>:/repo:ro -v <procps>/ps:/usr/local/bin/ps:ro -v <procps>/libproc2.so.0:/usr/lib/aarch64-linux-gnu/libproc2.so.0:ro
```

Profiles: **hardened** (b, d1, d2) adds nothing: `Seccomp: 2`, `CapEff`/`CapBnd` 0, and bubblewrap cannot start ("No
permissions to create a new namespace"). **X1** (a, c) adds `--security-opt seccomp=unconfined --security-opt
systempaths=unconfined`: `Seccomp: 0`, `CapEff`/`CapBnd` 0, bubblewrap starts. The start test is
`bwrap --unshare-user --unshare-pid --die-with-parent --ro-bind / / --proc /proc true`. In both profiles uid 1000 can
write `/home/op` and `/tmp` and cannot write `/repo`, `/usr/local`, `/usr/local/bin`, `/usr/local/lib/python3.14` or
its `site-packages`. The containers ran one after another, never two at once.

**Processes the checks did not start**: as in round 1, the entry shell starts the canaries `early` (in the shell's
and the harness's group), `early-setsid` (a session of its own) and, after the boundary, `late`; a canary logs every
catchable signal. At the end of a, b and c a live `cleanup_authority.signal_owned` claims docker-init, the entry
shell, the three canaries and their groups.

## Results

| Check | Profile | Result |
|---|---|---|
| a | X1 | The setsid descendant is gone as soon as the session ends, in all 3 ways. `cleanup_authority` proves the outside pid; a live signal through it stops the descendant (no other route to signal it was tried). The inside pids 2 and 3 name nothing in the container's table; pids that do exist there and are not the session's are refused when they are not the runner's (the canaries) and **proved** when they are (a sibling the harness started): `cleanup_authority` proves ownership by the runner, not membership of the session. The probe writes: a control without bubblewrap writes all five targets of a container-user-writable venv construction; under bubblewrap none lands. |
| b | hardened | The tests' route: the anchor adopted the sleeper, `cleanup_authority` proved it, `signal_owned` signalled it (`b.out`). |
| c | X1 | After the controller was SIGKILLed, nothing of the session was left 6 ms later, for `client.session`'s owner (1 run) and for `confine.measure`'s caller (3 runs). |
| d1 | hardened | `tests.v2.test_v21_confine` with recorders: 33 tests, 0 failures, 0 errors, 0 skipped; each measurement's construction, proof and host comparison recorded (`d1.out`). |
| d2 | hardened | `-v` transcripts: `tests.v2.test_v21_confine` Ran 33 tests in 22.9 s, OK; `tests.v2.p4.test_process_range` Ran 24 tests in 20.5 s, OK; none skipped. |
| processes the checks did not start | a, b, c | `signalled: []`, all 8 claims unproven ("born before the boundary or not a descendant of the runner"), the 3 canaries alive with the same start time and no signal logged. |

All 6 containers exited 0 (13 s, 7 s, 7 s, 24 s, 25 s, 23 s). Every `*.err` of a, b, c and d1 is empty.

### (a) A setsid descendant of a confined session — `a.out`

**Execution path, exactly.** For each mode the harness makes `client.session`'s own calls (`aisef2/app/client.py`,
`session()`): the argv `[<client>, run, --format, json, --model, fake/model, --title, a-<mode>, --dir, <ws>, the prompt]`,
then `confine.wrap(SPEC, argv, env, ws, client)` with `SPEC = {bwrap: /usr/bin/bwrap, network: host, read_only: []}`,
then `ProcessRange("a-<mode>", argv, cwd=ws, env=env, output=<log>)` with its defaults (grace `GRACE_S` = (2.0, 2.0),
no bound on the final wait) and `start()` (`.end.process_range`). Where it differs from a session: it then waits with
`r.wait(30)`, not `wait_within` (no budget or turn-cap polling), and calls `r.release()` itself; the client is a
script that starts `setsid sleep 3600.<random>`, writes what it sees to `inside.txt` and waits for `./go`. The
`client.session` call itself is exercised by c1.

Outside chain (`.end.chain_to_runner`): harness 12 → `range_anchor.py` 32 (the range: its own session and group) →
bwrap 34 (the range's only member) → bwrap's init 36 (a session of its own; listed as escaped) → client sh 38 (pid 2
inside) → `sleep 3600.986815` 39 (pid 3 inside; setsid). Inside, the client sees pids `1 2 3 7`.

- **Proved, and signalled through the proof.** `signal_owned(boundary, pids=[39], dry_run=True)` proves it
  `{ppid 38, born 1791450642 ≥ since 1791450640, runner 12}`. In mode `proved` a live `signal_owned` signalled the
  proved pid 90; it was gone 6 ms later and the client was still alive. No other way of signalling it was tried, so
  this does not show that it cannot be signalled otherwise.
- **Gone with the session.** `end`: the client exited 0; the sleeper was gone 6 ms after bwrap returned. `proved`:
  the same after the proved signal (0.0 s). `release`: `release()` while the client still loops; the ladder's ledger
  is `['cooperative']`, no `RangeEscaped`/`RangeNotEmpty`. In each mode nothing of the session was alive or a zombie
  at the first look after release, and no process carried the marker.
- **The inside pids, and pids that do exist outside.** Claimed, the inside pids 2 and 3 are "not in the host table":
  in this container's PID namespace those numbers belong to nothing (docker-init is 1, the entry shell 7), so their
  refusal says only that. `.end.inside_pid_collision` claims, in a dry run as a report from inside would, pids that do
  exist: the canaries 9, 10 and 25 are refused, "born before the boundary or not a descendant of the runner"; the
  sibling 48 (`sleep 1.5`, the harness's own child, born 1791450642 after the boundary) is **proved** — a live claim
  would have signalled it. **Limit:** an inside pid whose number, outside, belongs to a process of the runner born
  after the boundary would be proved and signalled; `cleanup_authority` cannot tell an inside number from an outside
  one. The sibling was waited for, never signalled.
- **The probe's writes** (`.measure`, `.measure_venv`): `confine.measure` with the real bubblewrap, three times. Per
  target: could uid 1000 write the target's directory without bubblewrap (the product's `operator_can`), and did the
  probe's file appear (`created_outside_workspace`):

  | measurement | run directory | kernel | interpreter site | client directory | git directory |
  |---|---|---|---|---|---|
  | `/repo` kernel, the image's site, real bwrap | can / no file | **cannot** / no file | **cannot** / no file | can / no file | can / no file |
  | venv in `/tmp`, NOT_A_SANDBOX (the control) | can / **file** | can / **file** | can / **file** | can / **file** | can / **file** |
  | venv in `/tmp`, real bwrap | can / no file | can / no file | can / no file | can / no file | can / no file |

  The control used `test_v21_confine.measure_in_range` as the tests do — a venv in the container's writable layer
  with a copy of aisef2 in its site, so the kernel copy and the site are the container user's — with
  `NOT_A_SANDBOX`: all five files were written (`left_on_host` names them), and it reported the problems an
  unconfined probe must get. The bubblewrap run used the same construction with `/usr/bin/bwrap`: `problems: []`,
  `setsid_survivors: []`, `left_on_host: []`; namespaces user, pid, ipc, uts and mnt `own`, net `shared`. So in this
  run every denial in that row is bubblewrap's. The probe's messages: the kernel copy and the site "Directory
  nonexistent" (not mounted in the sandbox), the client and git directories "Read-only file system" (bound
  read-only). The run-directory write exited 0 and left no file on the container's side: the path exists inside the
  sandbox only (an inference from bwrap's argv: `/tmp` there is bwrap's own tmpfs, in which it makes the
  workspace's mount point). In the `/repo` row the kernel and site denials are not discriminating: uid 1000 cannot
  write either even without bubblewrap.

### (b) How the tests identify a process they own — `b.out`

As round 1, with the test module of `f9249f5`: the harness calls `test_v21_confine.measure_in_range` itself with
`NOT_A_SANDBOX`, recording every `signal_owned` call (the real one runs). The probe's `sleep 120.365992` is pid 67;
reparented to the range's anchor 30 (a subreaper); the harness's own reading: `67 (ppid 30) → 30 range_anchor.py
(ppid 13) → 13 the harness`. The one call claimed `[67]` and signalled it with proof `{ppid 30, pgid 67, born
1791450657 ≥ since 1791450656, runner 13}`, `unproven: []`. Afterwards it is not alive; the reported pid, claimed
again, is "not in the host table"; the 5 probe files are under the test's directory and its venv.

### (c) Cleanup when the controller dies — `c.out`

The harness starts each controller with its own `Popen` and SIGKILLs it through that handle.

1. **`client.session`'s owner** (the controller calls `client.session("S1", …, confine=SPEC)`). Before the kill:
   controller 31 (group 7) → anchor 32 (group and session 32) → outer bwrap 34 (group 32, **parent the anchor**) →
   bwrap's init 37 (session 37) → client 38 → `sleep 3600.643932` 39 (session 39), and a `sleep 0.05`. Controller exit
   -9; 6 ms later nothing of it alive or a zombie, no marker left. The mechanism, from the parent links: the outer
   bwrap's parent is the anchor, not the controller, so `--die-with-parent` does not react to the controller's death;
   the anchor's watchdog (end of file on its stdin, then `killpg` of its group, which holds the outer bwrap) acts
   first, and bwrap's init then dies by `--die-with-parent` from the outer bwrap. They act in series. This run shows
   the outcome; it does not time the two steps.
2. **The python that called `confine.measure` in-process** (as `run.execute` calls it), 3 runs, each caught on its
   first try with `find` still running: controller 52 → outer bwrap 57 (its child, group 7) → bwrap's init 58 → probe
   shell 59 → `sleep 120.912568` 83 (setsid), `find`, `head`. Exit -9; 6 ms later nothing alive or a zombie. The outer
   bwrap's parent is the controller, so `--die-with-parent` applies; the probe's stdout and stderr pipes to the killed
   controller (SIGPIPE or EPIPE at the next write) are a second possible route this run does not exclude.
3. Nothing outside the sessions was signalled: the canaries (`early` in the controller's group 7 too) alive with the
   same start time and no signal logged; `ps_at_end` shows them in state `S`.

### (d) The test modules — `d1.out`, `d-test_v21_confine.err`, `d-test_process_range.err`

`d1` runs the tests `python -m unittest tests.v2.test_v21_confine` loads, through recorders that call the real
functions:

- **Outcome:** 33 run, failures `[]`, errors `[]`, skipped `[]`; `sys.platform` linux, `setsid` at `/usr/bin/setsid`,
  `ps` at `/usr/local/bin/ps`, uid 1000, HOME `/home/op`.
- **The measurements** (`.measure_in_range`): the three unconfined ones (two `NOT_A_SANDBOX`, one exiting 3) each
  built its venv under its own `/tmp/tmp…` directory, the probe was called with its 120.x sleeper and 60 s limit, it
  reported a setsid survivor and 5 files left, all under that directory; `HostGuard`'s two refusals raised as they
  must ("nothing was copied into it"; "the probe would write: ['/usr/local/lib/python3.14/.aisef-confine-probe-…']").
- **The ownership route** (`.signal_owned`): for each unconfined measurement one call, claiming the survivor, which
  is signalled with a proof whose `ppid` is the range's anchor (`166 → 128 range_anchor.py → 6 the harness`, and
  likewise 222 → 185, 269 → 232), born at or after `since`; `unproven: []`.
- **The host comparison** (`.host_view`, `.host_unchanged`): 52 views, 28 comparisons; the only 4 that reported a
  change are `HostGuard`'s own doctored views, as that test requires. What was compared, and whether uid 1000 could
  write it at all: the site, `/usr/local`, `/usr/local/bin`, `/usr/local/lib/python3.14`, the kernel `/repo/aisef2`
  and the names in `/repo` — **not writable**; the names in `/home/op` — writable. So in this container only
  `/home/op` could have shown a change: the comparison of the others passes whatever the tests do.

The `-v` transcripts are the same module run plainly, plus `p4/test_process_range` (its subreaper test
`test_an_orphan_the_range_adopts_is_reaped_when_it_dies` among them). The ResourceWarnings come from
`aisef2/orchestrate/story_runner.py`; they fail nothing.

## What this does not show

- **Not a bare-metal Linux host, not Ubuntu CI, not other kernels**: one Docker Desktop VM kernel (7.0.12-linuxkit,
  arm64). Checks a and c need the container's seccomp filter off and its system paths unmasked.
- **No real `opencode` client and no provider**: the clients are scripts; the containers have no network.
- **`ps` comes from another local image** (Debian 13.6 against the measure image's 13.7).
- **One run per check** (each measure-caller kill 3 times): observations, not rates; timings under host load 7.5–10.6.
- **SIGSTOP is not ruled out for a and b's canaries** (only c lists them, in state `S`).
- **Not exercised:** `teardown_race.py` and the `run.sh` matrix (P1–P5, X1–X3); a confined `aisef run` end to end
  (M6); `client.session`'s `wait_within` around a confined session that the harness also inspects (a uses `r.wait`).
