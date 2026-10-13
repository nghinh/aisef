# AISEF 2.1 — Minimal Linux confinement of the model sessions (track F / B-07)

Scope: confine the **model sessions** the kernel's client starts — the developer and the model reviewer — so the
untrusted code they run cannot write anything of the machine beyond the one workspace it is given, and reads only
what is listed in §2. This is the first isolation code on the branch (REPORT F was M6: "chưa có mã cách ly nào trên
nhánh"). It is **opt-in** and **Linux-only**; it changes nothing when the settings do not ask for it.

Module: [`aisef2/app/confine.py`](../../aisef2/app/confine.py). Harness:
[`validation/v21/sandbox/`](../../validation/v21/sandbox/). Measured evidence:
[`evidence/sandbox/`](evidence/sandbox/) (`measure.log`, one JSON per profile, `Dockerfile.measure`), recorded at the
committed tree `764dfa2` (`measured tree: … uncommitted paths: 0` in `measure.log`); the setsid-survivor check
against the PID namespace's teardown: `teardown-race-{plain,sock}.json` and `teardown-race-{plain,sock}-2.json` (§5).

Every claim below names the operation that was tried and what happened (owner's 2026-10-06 requirement: a denied
operation, not config alone). Where an operation **succeeded** — into a throwaway tmpfs, or because a session is
meant to reach it — it is listed as such, never as a denial. What is not confined is stated as plainly as what is.

---

## 1. The layers, kept distinct

The owner's requirement: do not write "macOS always has no isolation"; name the real configuration at each layer.

| Layer | What it is here (measured, `measure.log`) | Boundary it gives the session's code |
|---|---|---|
| **macOS host** | Darwin 25.5.0 arm64, the operator's user | none of its own: bubblewrap, user namespaces and the `/proc`-based process ranges are Linux features; on macOS the kernel's session runs the client as the operator's user with **no OS boundary** (REPORT §3, DEVELOPER-CONFINEMENT-GAP-001), and a run that asks for confinement there is refused (§3). |
| **Docker Desktop VM** | `docker` 29.8.0, server `linux/arm64`; guest kernel `Linux 7.0.12-linuxkit aarch64` (Docker Desktop's LinuxKit VM) | the VM separates macOS from the Linux guest, but it is Docker's boundary, not AISEF's; AISEF does not manage it. |
| **Linux container (the guest)** | a `docker run` of the pinned `python:3.14-slim-trixie@sha256:3353bb7e…` image, `--user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g`, the tree mounted read-only | the first boundary AISEF could shape. Its seccomp profile and masked system paths decide whether a **nested** sandbox can start at all (§3). |
| **bwrap inside the guest** | `aisef2.app.confine` builds the argv; one unprivileged user + mount + pid + ipc + uts (+ net for `none`) namespace per session | the per-session boundary this track adds. **Measured in §5.** |

A `-S` interpreter flag, a git worktree, or a hash check before running is **not** a sandbox and this document never
calls one that (owner's instruction). The boundary here is kernel namespaces, measured by operations tried inside.

## 2. Threat model, and exactly what a confined session reaches

The developer (and the model reviewer) run model-written, untrusted code in a checkout. Without an OS boundary that
code runs as the operator's user and can (measured, REPORT §3): read every file the operator can read — including a
hidden experiment stimulus (DEVELOPER-CONFINEMENT-GAP-001); write the client binary (the *runtime*), the run
directory while the run is in progress, and the evidence anchor if it is reachable; leave a `setsid` child that
outlives the run (REPORT §4.2).

Trusted, and deliberately **outside** this sandbox: the kernel itself, which drives git, runs the probes and the
developer's tests, computes the evidence and the anchor. The design rule "never put the control daemon inside the
workload's area" comes from OpenSandbox — **INFERENCE on CODE** (`opensandbox-group/OpenSandbox @ c7dc78a4090e`,
design-only, never vendored; research record [`research/UPSTREAM-RESEARCH.json`](research/UPSTREAM-RESEARCH.json)
item N7: its `execd` listens on tcp4 `:44772` inside the sandbox, execd `main.go:232-235`, and the egress nft output
chain accepts `oifname lo`, `manager.go:261`, so the workload reaches its own controller). So the
confinement wraps **only the client's session**, never the kernel.

What a confined session reaches (the command line, `confine.wrap`; the reads and writes measured in §5):

| | What |
|---|---|
| **writes** (host-backed) | the developer's session: its workspace — nothing else. The model reviewer's session: **nothing** — the checkout it reviews is bound read-only as well (`confine.wrap(…, writable=False)`, §5). Everything else a session writes lands in its own tmpfs (`/`, `/tmp`, an empty HOME) and is gone when it exits. The measurement accepts a writable mount outside the workspace only when the report shows it is the sandbox's own, or one of the six device nodes `--dev` places (§6.1, the owner's 2026-10-12 policy). |
| **reads, read-only** | the system (`/usr`, `/etc`, the merged-`/usr` links); **the client's own directory**; **the workspace's common git directory — for a run's worktree that is `<out>/repo/.git`, inside the run directory: the run's clone, every object and ref of it**; the client's configuration directory (`$XDG_CONFIG_HOME/opencode` or `~/.config/opencode`); the operator's `read_only` paths. |
| **does not see** | the rest of the run directory (its canary, the anchor, the sessions' logs, other worktrees), the rest of HOME (`.ssh`, the client's auth data under `~/.local/share/opencode`), the verifier/hidden material, the kernel and the interpreter **unless they lie under the system paths or a `read_only` path** — `/usr` is bound read-only, so an interpreter or a kernel installed under `/usr` (`/usr/local` included) is readable: the harness itself runs `/usr/local/bin/python3` inside; the container's other processes. |

Two consequences, stated because they are behaviour: the git directory is read-only, so a confined developer cannot
commit — it leaves its changes in the worktree and the kernel commits them (`adapters.Developer`: `commit_all`); and a
client installed **in HOME or above the workspace** (a single-file download in `~`, or a scratch directory that also
holds the runs) is **refused** — its directory, bound read-only, would expose HOME or the runs
(`confine.wrap`: "the client's directory … holds HOME").

## 3. What each container boundary gives — and the loosening bwrap needs

Bubblewrap needs to create an **unprivileged user namespace** and mount a fresh `/proc`. Measured on this host
(`measure.log`, one JSON per profile; P2–P4 loosen cumulatively, X1/X2 single out the axes):

| Profile | Container flags added to `--user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g` | Result |
|---|---|---|
| **P1** hardened | *(none)* | bwrap **cannot start**: "No permissions to create a new namespace". Refused. |
| **P2** | `--security-opt seccomp=unconfined` | the user namespace starts, then **"Can't mount proc on /proc: Operation not permitted"**. Refused. |
| **P3** | P2 `+ apparmor=unconfined` | identical to P2. |
| **X2** | `systempaths=unconfined` only | "No permissions to create a new namespace" (as P1): seccomp is a gate on its own. |
| **X1** | `seccomp=unconfined` + `systempaths=unconfined` (AppArmor left default) | bwrap **runs**; the kernel's measurement: 0 problems. **The minimal loosening.** |
| **P4** | P3 `+ systempaths=unconfined` | as X1. |
| **X3** | X1, the session sharing the network (what a run uses, §4) | bwrap runs; 0 problems; the network is reachable (§4). |
| **P5** | P4, the session sharing the network | as X3. |

So on this kernel the gates are Docker's **seccomp** profile (the user namespace) and its **masked system paths**
(the fresh `/proc`). **AppArmor is not in this guest kernel** (`/sys/module/apparmor` absent, `measure.log`), so
`apparmor=unconfined` changes nothing here; on a kernel with AppArmor it may be a third gate — not measured.

**This is loosening the container's own boundary.** The nested sandbox is strong once it runs (§5), but on this host
the container must drop its seccomp filter and unmask system paths to let it run. So nested bwrap buys a second,
per-session boundary **only at the cost of weakening the first**. The recommendation (decision F) therefore remains:
on a real deployment prefer the **container itself as the boundary** (`--cap-drop ALL`, `--read-only`, non-root,
`--pids-limit`, seccomp kept on, the network limited to the provider — §4), and use nested bwrap only where the
kernel allows unprivileged user namespaces without that loosening. This module gives the bwrap layer; it does not
claim to replace the container profile.

### Fail-closed

When the settings ask for confinement and it cannot be provided — not Linux, no bubblewrap (a path that is not an
executable file, or one that cannot be read), a read-only path missing, a client whose directory holds HOME (the
env's, or the user's home when the env has none) or the workspace, no client to measure with, or (P1–P3, X2) the
sandbox cannot set up its namespaces — the run **refuses before the first provider request** and records why (`RUN.json.confinement.problems`, stage `confinement`); a single session refuses with
`SessionRefused` before the client starts or its log is created; `aisef run --check` is `ready: false`. A check the
measurement could not make (no `unshare`, no `find`, an exit that is not the kernel's refusal, a `/proc/self/ns` link
that could not be read on either side — `not measured`, never `own`) is a problem, never a pass; so is a probe that
exits non-zero even after reaching its end. Proven by `test_v21_confine` (macOS: one `_judge` case per check,
`test_a_namespace_counts_as_own_only_when_both_links_were_read_and_differ`, `test_no_client_no_measurement`,
`test_a_probe_that_did_not_exit_0_is_refused_even_when_it_reached_its_end`,
`test_an_unreadable_bubblewrap_is_a_problem_not_a_crash`,
`test_a_client_directory_that_holds_home_or_the_workspace_is_refused`) and by P1–P3/X2 above (the kernel's
measurement: "the sandbox did not run the probe").

## 4. The network: what a run can use

| `network` | Namespace | What it gives (measured) | Usable for a run? |
|---|---|---|---|
| `none` | its own (`--unshare-net`): a fresh loopback, no route | host port: `Network is unreachable`; the container's abstract unix socket: `Connection refused` (X1, P4) | **No.** The session cannot reach its provider endpoint either, so no model call can work. **Measurement-only**: `settings.load` refuses it ("leaves a model session no route to its provider"). |
| `host` | the container's (`--share-net`) | host port: `UP: reached host`; the container's abstract unix socket: `CONNECTED` (X3, P5) | **Yes — and egress is NOT confined.** The session reaches whatever the container's network reaches, and every abstract unix socket of that network namespace (on a bare Linux host that can mean the session bus, X11 or a container shim). The session record says `confinement: "bwrap network=host"`. |

So **no configuration shown here confines a working model session's network.** That needs an egress allowlist (only
the provider endpoint) — e.g. a default-deny sidecar such as OpenSandbox's (**CODE**, `c7dc78a4090e`: the sidecar is
created and the workload joins its network namespace, `docker_service.py:783-850`; nft rules
`manager.go:228-296`; an empty policy denies by default, `policy.go:39-45`; note packets are
enforced only in its `dns+nft` mode, the default `dns` mode redirects port 53 only — research record N8, N9, N10).
Not built here. Since `none` is refused for a run, a run never has sessions that could not reach the network, so no
such session is ever counted as unaccounted provider spend.

## 5. What is confined once bwrap runs

Rows from [`evidence/sandbox/X3-seccomp-systempaths-net-host.json`](evidence/sandbox/X3-seccomp-systempaths-net-host.json)
(the run profile: minimal loosening, shared network); X1/P4/P5 are identical except the network rows (§4). Every
operation runs under the command line a session gets (`confine.wrap` with the client and a worktree of the run's
repository; the reviewer's rows with `writable=False` on a second worktree, the checkout it reviews); the kernel's own
`confine.measure`, run as `run.execute` runs it, reports 0 problems in X1, X3, P4, P5 (namespaces read as links on
both sides: user, pid, ipc, uts, mnt `own`; net `own` with `none`, `shared` with `host`).

**Denied** (the operation failed inside; `after` = checked from outside the sandbox when the run ended):

| Claim | Operation tried inside | Observed |
|---|---|---|
| the run directory is unreadable | `cat <run-dir>/canary` | `No such file or directory` |
| the verifier/hidden material is unreachable | `cat <verifier>/hidden.json`; `: > <verifier>/hidden.json` | `No such file or directory`; `Directory nonexistent` (not mounted) |
| HOME secrets unreachable | `cat ~/.ssh/id`; `cat ~/.local/share/opencode/auth.json` | `No such file or directory` (HOME shows only `.config`, the way to the client's configuration) |
| the runtime cannot be rewritten | `: > <runtime>/opencode`; `: > <runtime>/x` | `Read-only file system`; after: runtime unchanged, nothing created |
| the kernel / interpreter cannot be written | `: > <venv site-packages>/aisef2/…` (a path the operator **can** write: `operator_can` true) | `Read-only file system` (the venv is a `read_only` path); after: nothing created |
| the git directory cannot be written | `: > <out>/repo/.git/HEAD` | `Read-only file system`; after: HEAD unchanged |
| the reviewer cannot write the checkout it reviews (its write bits kept here: only the mount refuses) | reviewer's wrapper: `(: > ./x); (echo x >> ./candidate.py)` (each in a subshell, so both are tried: sh exits at a failed redirection of `:`); `chmod u+w ./candidate.py` | `cannot create ./x: Read-only file system`, `cannot create ./candidate.py: Read-only file system`; `chmod: … Read-only file system`; after: the checkout's listing and `candidate.py` unchanged |
| a unix socket outside every mount is unreachable | connect `<base>/sock/ctl` | `FileNotFoundError` |
| no further user namespace (the route back to capabilities) | `unshare --user --map-root-user true` | `unshare failed: No space left on device` (`--disable-userns`) |
| the container's processes are not visible | look for a container-side `sleep 987.654` (seen outside: `after.container_sleeper_seen_outside` true) by its command line in `/proc/*/cmdline` | found **0** times; `/proc` lists only `1 2 9 10 11 12` — the session's own PID namespace (the measurement: `namespaces.pid` "own", a different `/proc/self/ns/pid` from the container's) |
| a setsid child dies with the session | the measurement's `setsid sleep 120.<unique>` (it outlives the probe's 60 s limit), then a look for it once bubblewrap returned (one found is looked at again until gone, for up to 1 s) | `setsid_survivors: []` |

**Succeeds only into the sandbox's throwaway tmpfs** (not a denial; the real file is unchanged):

| Operation | Inside | After (outside) |
|---|---|---|
| append to `<run-dir>/EVIDENCE.anchor` | exit 0, the file reads `x` | anchor unchanged |
| create `<run-dir>/written` | exit 0, `<run-dir>` lists `repo work written` | nothing in the real run directory |

**Observed** (a reading of `/proc/self/status`, not an operation): `CapInh/CapPrm/CapEff/CapBnd/CapAmb = 0`,
`NoNewPrivs: 1`, `Seccomp: 0` (§7); namespaces user, pid, ipc, uts, mnt **own** (net own with `none`, shared with
`host`).

**Reached by design** (read-only): `<out>/repo/.git/HEAD` reads `ref: refs/heads/main`; `git status` works in the
workspace; the client's configuration directory lists `opencode.json`; the reviewer reads the checkout it reviews
(`cat ./candidate.py`, `git status` → `?? candidate.py`).

**Sockets.** Filesystem sockets: none is listed under any host directory bound in (the measurement's
`inside.unix_sockets: []`). A read-only mount does **not** stop a connect: the same `<base>/sock/ctl`, bound in
read-only, is `CONNECTED` — and the kernel's measurement refuses that setting ("a unix socket outside the workspace
is reachable"), recorded as `by_design.measure_with_a_read_only_mounted_socket`. Abstract sockets: §4.

**Survivors and the teardown.** When bubblewrap returns, the kernel may still be killing the PID namespace's
processes, so a single look can find the probe's sleeper alive: the round-2 verifier saw it once in 400
measurements on `affcefb`'s code (pid gone at the first re-check), and the kernel's measurement then refused for
"a process the session left outlived it". Since `3e0409c` a sleeper found is looked at again every 0.05 s for up
to `SURVIVOR_GRACE` (1 s); only one still alive then is a survivor. A killed one no longer matches for two reasons,
each enough: the process table leaves zombies out, and a zombie no longer shows the sleeper's command line (measured:
in the measurement image a killed, unreaped `sleep` reads state `Z` and an empty `/proc/<pid>/cmdline`; on this macOS
host `ps` prints `Z <defunct>`). Since `764dfa2` the sleeper lives 120.x s (`SLEEPER`), twice the probe's 60 s limit
(`PROBE_TIMEOUT`). Before, it lived 30.x s, so a real survivor of a probe that exited 0 more than about 29 s after
starting it would have died of its own sleep within the grace and gone unreported (a whole measurement here takes
about 30 ms: 500 in 14.7 s). Now a probe that exits 0 has done so within 60 s and the last look ends about 1 s later,
so the sleeper is still alive at it; a probe that reaches the limit is refused anyway
(`test_the_sleeper_outlives_a_probe_that_used_all_its_time_and_the_grace`).

Measured with X1's container flags and the run's `network: host`, 500 measurements per run, under the heavy lock, on
a git archive of the tree (`validation/v21/sandbox/teardown_race.py`; the `docker run` command is in its docstring,
`python3 -B /race.py 500` and `… 500 sock`):

| tree | run | first look found the sleeper: no socket | with the read-only socket directory | reported a survivor |
|---|---|---|---|---|
| `3e0409c` | round 3 (the files at `f026f6b`) | 0 of 500 | 2 of 500 | 0 of 1000 |
| `3e0409c` | the round-3 verifier's identical re-run (its scratch, not committed) | 2 of 500 (measurements 10, 12) | 2 of 500 | 0 of 1000 |
| `764dfa2` | `teardown-race-plain.json`, `teardown-race-sock.json` | 0 of 500 | 1 of 500 (18) | 0 of 1000 |
| `764dfa2` | `teardown-race-plain-2.json`, `teardown-race-sock-2.json` | 0 of 500 | 3 of 500 (25, 31, 101) | 0 of 1000 |

The first look finds the sleeper in either configuration (2 of 2000 without the socket, 8 of 2000 with it, over
these four runs); at these counts no difference between the two is claimed. Round 3's statement that without a
socket the first look never found it did not reproduce and is withdrawn: the race also reaches a measurement that
would otherwise pass, which is why the grace applies to every run. In every measurement where the first look found
it, the second look found it gone. The positive control on Linux's `/proc` table, in each of these eight `docker run`s: a
"bubblewrap" that confines nothing leaves its sleeper alive, and the measurement reports it after the grace (14
looks; the whole measurement 1.0–1.1 s; the pid still alive when it returned). The direction stays fail-closed: a
survivor is only ever dropped by being gone, and within the grace it can no longer be gone by reaching its own
end.

**Controls** (must work): the workspace (`echo ok > ./w && cat ./w` → `ok`); the client started from its own
read-only mounted directory prints its JSON.

**Linux guest checks (2026-10-08).** The checks below ran on tree `f9249f5` (round 2; round 1, on `860c02a`, is kept
and marked superseded), in containers of the measure image on Docker Desktop's LinuxKit 7.0.12 arm64 guest. The
containers ran as uid 1000 with no capabilities and no network, the tree read-only. The details, including every
docker flag and component version and the execution path of each check, are in
[`evidence/sandbox/linux-guest-2026-10-08-r2/README.md`](evidence/sandbox/linux-guest-2026-10-08-r2/README.md); the
harness is `validation/v21/sandbox/linux_guest.py`.

- **A setsid descendant of a session started with `client.session`'s own calls** (its argv, `confine.wrap`, its
  `ProcessRange` call with the defaults; the harness then waits with `r.wait`, not `wait_within`). It shows in the
  container's process table under its outside pid, with a parent chain to the controller. The range sees only bwrap:
  the outer bwrap is its member, and bwrap's init is listed as escaped. `cleanup_authority` proves the descendant,
  and a signal through that proof stops it (no other route was tried). The pids the session sees inside (2, 3) name
  nothing in the container's table and are refused for that; claimed pids that do exist there are refused when they
  are not the runner's, and proved when they are — `cleanup_authority` proves ownership by the runner, not
  membership of the session, so an inside number that collides with a runner's process would be signalled. The
  descendant is gone as soon as the session ends: when the client exits, after a proved signal, and under the
  release ladder.
- **The probe's writes, discriminating.** Built as the tests build it (a venv in the container's writable layer with
  a copy of aisef2), a control without bubblewrap wrote all five targets — run, kernel, interpreter site, client and
  git directories; under bubblewrap none landed and the measurement had no problem. Measured with the kernel at
  `/repo` and the image's site instead, those two denials do not discriminate: uid 1000 cannot write them anyway.
- **The tests' route** (the anchor, a subreaper, adopts the sleeper; `cleanup_authority` proves it; `signal_owned`
  signals it) ran through `measure_in_range` itself, with its proof record.
- **The controller SIGKILLed** (`client.session`'s owner, and the python inside `confine.measure`). Nothing of the
  session was left 6 ms later. For the session owner the anchor's watchdog and bwrap's `--die-with-parent` act in
  series (the outer bwrap's parent is the anchor).
- In every one of these checks, a live claim of the processes the checks did not start signalled nothing.
- `test_v21_confine` (33 tests) ran whole there with recorders (each measurement's construction and proof, and which
  roots the host comparison could have seen change: only `/home/op` is writable by uid 1000), and with `-v`
  together with `p4/test_process_range` (24 tests); none failed or was skipped.

This is a container in Docker Desktop's VM. It is not a bare-metal Linux host and it is not CI.

## 6. The implementation

- **Setting** (`aisef2/app/settings.py`, optional, fail-closed validation):
  `"confinement": {"backend": "bwrap", "bwrap": "<absolute path>", "network": "host", "read_only": ["<abs>", ...]}`.
  `network: "none"` is refused for a run (§4); confinement together with `review.finder: "ocr"` is refused — Open
  Code Review calls the model outside the client's sessions, unconfined. Absent ⇒ a 2.0.0 run, no record key, no
  wrapping.
- **argv builder** (`confine.wrap`): `--unshare-user --unshare-pid --unshare-ipc --unshare-uts` (and `--unshare-net`
  for `none`, else `--share-net`), `--disable-userns`, `--die-with-parent`, `--new-session`, `--cap-drop ALL`; the
  system read-only (a merged-`/usr` symlink stays a symlink); the client's directory, the worktree's common git
  directory, the client's configuration directory and the operator's `read_only` paths read-only; the workspace bound
  **last** read-write (so it wins even below a read-only path); HOME an empty tmpfs with `XDG_*` redirected under it,
  `XDG_CONFIG_HOME` still pointing at the read-only configuration so the client finds its route.
- **Wiring**: `run.execute` resolves the client first and measures confinement at a stage of its own before the
  preflight, **with the sessions' client and a worktree of `<out>/repo`** (removed afterwards), so the measured
  command line binds exactly what a session's binds (`test_v21_confine.CommandLine.test_the_measured_wrapper_is_the_sessions_own`);
  any problem refuses the run, the report kept as `RUN.json.confinement`. `client.session(..., confine=...)` wraps
  the client and refuses before the log exists when the host cannot confine; each confined session's record carries
  `confinement`. The model reviewer's sessions get `workspace_writable=False` (`run.execute`), so the checkout they
  review is bound read-only and their record says `bwrap network=host workspace=read-only`
  (`RunFailClosed.test_a_confined_run_starts_every_session_through_bubblewrap_and_says_so`). `aisef run --check`
  measures with the client on the run's PATH and a worktree of a new repository
  (`Check.test_check_measures_with_the_client_on_the_runs_path`).
- **Measurement** (`confine.measure`): a probe shell under that wrapper; judged on what it observes, never on config —
  a "bubblewrap" that runs the probe unconfined is refused for what the probe could do. Besides §5's checks it
  requires the mounts seen inside to lie within what the command line names, and no unix socket outside the workspace
  under any bound directory (within: the path itself or below it — `/w/ws2` is not within `/w/ws`, nor
  `/usrlocal-extra` within `/usr`); every writable mount outside the workspace must be shown to be the sandbox's own (§6.1); a namespace is `own` only when its `/proc/self/ns` link was read inside and outside
  (`<name>:[<inode>]`) and they differ; a check that did not run is a problem; a file the probe made outside the
  workspace (confinement did not stop it) is never removed — the subject made it (INV-MUTATION-AUTHORITY) — but left
  where it was made, listed in `left_on_host` and named in a problem for the operator to remove; a probe sleeper found when bubblewrap
  returns counts as a survivor only if still alive after up to 1 s, and the sleeper outlives the probe's 60 s limit
  plus that second (§5; `test_a_sleeper_still_dying_when_bubblewrap_returned_is_no_survivor`,
  `test_a_killed_sleeper_is_no_survivor_a_live_one_is`, which does not single out the zombie filter: a killed sleeper's
  command line is gone too; `test_the_sleeper_outlives_a_probe_that_used_all_its_time_and_the_grace`; and the grace
  `_survivors` actually uses is `SURVIVOR_GRACE`, on a clock of the test's own:
  `test_the_grace_used_is_survivor_grace_so_a_sleeper_ending_just_after_it_is_still_a_survivor`).

**Kernel change.** This touches `aisef2/` (settings, client, run, cli, and the new `confine.py`): it needs mutation
coverage and re-qualification outside the current measured snapshot. On this track's branch `confine.py` was **not** a
mutation target: `validation/v2/mutation.py` had no `aisef2/app/confine.py` entry (in neither `TARGETS` nor
`V21_TARGETS`), and `run.py::client_on_path` was not one either; `tests/v2/test_v21_mutation_record.py` did not name
them. **Since `34db934` on `v21/integ` they are V2.1 targets**: confine.py's 20 names (808 mutants there; `_probe`
184 since the INV-MUTATION-AUTHORITY fix, 814 in all) with kill set `test_v21_confine.py`, `client_on_path` with that
file last, which is also appended to the kill sets of the 5 changed targets below. Against `closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST.json` (snapshot
`cc53596`), `v21_requalification.py --check` on this branch (`ac27348`) reports 5 changed V2.1 targets —
`cli.py::run`, `client.py::session`, `run.py::execute`, `settings.py::OPTIONAL`, `settings.py::load`; counted as its
`scope()` counts them (`mutation.mutants`), 116→133, 114→128, 315→337, 2→3 and 254→268 mutants (+68). Targeted mutants of this track were run on scratch copies only — not campaign evidence: 45/45 killed
at `ac27348` (the 11 that survived the previous tests at `0da842f` among them; same script, same copy method); and the
5 the round-2 verifier saw survive the 24 tests at `4e00a0d` (`_within` without its `/`, the user's home not checked
when the env has no HOME, an unreadable bubblewrap raising, a non-Linux measurement making its worktree, `--check`
measuring without the client) survive them again and are killed by the 26 at `affcefb` (tests only: `aisef2/` is
unchanged since `ac27348`). Round 3 changes `aisef2/app/confine.py` only (`_survivors`, `SURVIVOR_GRACE`; not then a
mutation target; the files of the 5 targets above are unchanged since `ac27348` by `git diff`, so their counts
above stand — `--check` itself was not re-run): 6/6 targeted
mutants of the grace killed by the 28 tests at `3e0409c`; two of them — no grace (the round-2 code) and a grace of
0 — survive the 26 round-2 tests. Round 4 changes `aisef2/app/confine.py` only (`PROBE_TIMEOUT`, `SLEEPER`, a docstring) and
adds one test; on a scratch copy of `764dfa2`, after a green baseline (Ran 29 OK): 6/6 targeted mutants of the new
bound killed by `test_the_sleeper_outlives_a_probe_that_used_all_its_time_and_the_grace` alone (the sleeper back to
30 s; 61 s; a limit of 150 s; the probe's timeout not `PROBE_TIMEOUT`; the sleep not `SLEEPER`; a grace of 60 s);
a sleeper of 62 s survives and is not a violation (62.x s still outlives 60 + 1 + 1 s). The earlier rounds' 96
mutants: 94 killed, the 2 judged equivalent before survive again; round 3's 6 grace mutants killed. Three survive and
are stated: a grace of 40 s, no longer fail-open (the 120 s sleeper still outlives 60 + 40 s; only a measurement
with a survivor is slower), and dropping the zombie filter from the macOS table (equivalent for `_survivors`: a
killed sleeper's command line is gone, §5); "no deadline" hangs the always-alive case (a timeout). In the first mutant
job, the "no deadline" run was killed at its 150 s timeout and left a probe file in the copy's `aisef2/`; that file
failed `test_what_is_measured_decides_not_the_name_of_the_tool` in every later run (the zombie-filter mutant read
as killed for that reason alone), so the mutants after it were run again on a clean copy, removing such a file after
each run; the counts above are from the clean runs.

Round 5 (`2cd02e9`) adds one test and changes no code.
`test_the_grace_used_is_survivor_grace_so_a_sleeper_ending_just_after_it_is_still_a_survivor` runs `_survivors` on a
clock of its own (`confine.time` replaced: `monotonic` reads it, `sleep` advances it) against a sleeper alive until
`SURVIVOR_GRACE` + 0.5 s, and requires it reported, only once the grace has passed: the look that decides comes
after `SURVIVOR_GRACE` and before `SURVIVOR_GRACE` + 0.5 s, whatever grace and settling between looks `_survivors`
uses. The relation that makes the grace safe is pinned, since `764dfa2`, by
`test_the_sleeper_outlives_a_probe_that_used_all_its_time_and_the_grace`, from the probe's own call (the sleep and
the timeout passed to it) and the constant: sleep > timeout + `SURVIVOR_GRACE` + 1 s
for the last look — the grace stays below the window in which a real survivor of a probe that exited 0 just inside
its limit is still alive, `SLEEPER`.x − `PROBE_TIMEOUT` − 1 = 120.x − 60 − 1 = 59.x s. The two together pin it on
the grace used, not only on the constant; no third test is added for it. Mutants, one at a time on scratch copies of
`0e2582a` and `2cd02e9`, each after a green baseline (Ran 29 OK; Ran 30 OK), judged by
`env PATH=<a PATH without opencode> PYTHONPATH=<copy> python3 -P -m unittest tests.v2.test_v21_confine` in the copy:
the effective grace ×100 with the constant unchanged (`deadline = time.monotonic() + SURVIVOR_GRACE * 100`) survives
the 29 tests at `0e2582a` (the relation test reads the constant; no other grace test has an upper bound) and is
killed by the 30 at `2cd02e9`, by the clock test alone; at `2cd02e9`, a grace just above the window
(`SURVIVOR_GRACE = 60.0`: 60 + 60 + 1 = 121 > 120.x) and one of the sleeper's whole lifetime (`120.0`) are each killed
by the relation test alone. A grace of 40 s (`SURVIVOR_GRACE = 40.0`) survives at both commits and is no
violation: it satisfies the relation, 60 + 40 + 1 = 101 s < 120.x s, so a survivor is still alive at the last look;
only a measurement with a survivor is slower (the module takes 134 s instead of 17 s). Pinning the constant's value
would kill it, but would test a number, not the behaviour, so it is not pinned. The unmutated module at `2cd02e9`, in
the worktree: Ran 30 OK.

### 6.1 The write policy and the locale (B03-R3, owner 2026-10-12)

Decision and evidence: [`decisions/B03-R3-conf.md`](decisions/B03-R3-conf.md); records of a real bubblewrap in the Linux
guest: [`evidence/sandbox/r3-conf/`](evidence/sandbox/r3-conf/).

**Writes.** The developer writes the workspace and the execution resources explicitly allowed; every other writable mount
must be **shown** to belong to the sandbox. The judgement decides from the mount's file-system type, mount source, mount
options and namespace — never from the file system's name alone or from a place under `/dev/` (the earlier clause
exempted `tmpfs`, `proc`, `devpts` and `mqueue` by name and anything under `/dev/` by place, and so accepted the
container's own `/dev/pts`, `/dev/mqueue`, `/dev/shm`, `/dev` and `/proc`: it accepted all twelve variants measured in
the guest, nine of which are write paths). A writable mount outside the workspace is accepted when it is:

| Class | Accepted when |
|---|---|
| the workspace | its mount point is the workspace (the one host-backed writable mount) |
| an execution resource | the name is `null`, `zero`, `full`, `random`, `urandom` or `tty`, it lies under a `--dev` destination of the command line, and the probe read it inside as the character device of that kernel number (`1:3`, `1:5`, `1:7`, `1:8`, `1:9`, `5:0`). These are bubblewrap's binds of the host's own nodes: allowed for being an explicit list of what an execution needs, each by identity |
| a mount the sandbox made | a `tmpfs`, `proc`, `devpts` or `mqueue` whose mount source is its own name, whose super block (major:minor) is not one the host's own mount table holds (read just before the session starts: a super block a session creates is one no live host mount holds; the reading after the session decides nothing), and that no peer group of the host propagates into or out of |

Anything else is refused: `writable outside the workspace: [...]` when the report shows it is the host's (a super block
the host holds, a host path or device as source, a file system a wrapper cannot make, a peer group of the host, a node
that is not the device it must be), and `cannot establish that a writable mount belongs to the sandbox (isolation not
established …)` when a field could not be read or the host's table is unreadable or incomplete — never a pass. Why a super block that is not the
host's is the sandbox's own: the kernel gives each `tmpfs` mount its own super block and each `devpts` mount a new
instance, a `proc` super block is keyed by the PID namespace and an `mqueue` one by the IPC namespace, so one that shares
the host's namespace is the host's (measured: no `--unshare-pid` gives `/proc` as the container's `0:66`); the judgement
already requires those namespaces to be the session's own. Lifecycle: the host's table is the same after each session
as before it in every recorded run, and `setsid_survivors` is empty; a super block goes with the mount namespace
(proc's and mqueue's with the PID and IPC one) when the session's last process exits — kernel behaviour relied on, not
measured here.

The report records what decided: `host_mounts` (the host's table as `{at, fs, dev, optional}`, read before the session),
`inside.mounts` rows with `dev`, `root`, `source`, `options`, `super_options` and `optional`, `inside.devices` and
`inside.device_roots`; and, as information only, `host_mounts_appeared` (the rows the host's table gained while the
measurement ran, read after it; `None` when either reading failed — it refuses nothing).

**Locale.** The measurement's own subprocesses — the probe and `bwrap --version` — run with `LC_ALL=C` and `LANG=C`
(`confine.LOCALE`), so the text the judgement parses (the probe's output, the user-namespace refusal `USERNS_REFUSED`
matches) does not depend on the caller's locale; nothing else of `LANG`, `LANGUAGE` or `LC_*` reaches them. The report
records it (`locale`). The caller's `os.environ` and the environment a session gets (`confine.wrap`) are untouched.

**What was measured.** With the real bubblewrap 0.12.0 in the guest, the session's own command line and eleven variants
(`scenarios-X1.json`; the same in a mount namespace with a shared tree, `scenarios-X1-shared-tree.json`):
a second `--dev` (a devpts outside `/dev/`) and `--mqueue` are accepted; the container's devpts, mqueue, `/dev`,
`/dev/shm` and `/proc` bound or shared in, a writable ext4 file at `/dev/x`, a regular file or another device over
`/dev/null` and a node outside the list are each refused for what they are. The environment the real bubblewrap
received, with a caller carrying `LANG=vi_VN.UTF-8`, `LC_ALL=de_DE.UTF-8`, `LC_MESSAGES=fr_FR.UTF-8`, `LANGUAGE=ja`, is
`LC_ALL=C LANG=C` and nothing else of the family (`locale-X1.json`). **Not measured:** a translated message (the guest has
only the locales `C`, `C.utf8` and `POSIX`).

## 7. Limits (not confined / not claimed)

- **Not confined** by this track: the kernel's own execution of the developer's tests and the probes' execution of
  the candidate — they still run as the operator's user. Open Code Review is not confined either; it is refused
  together with confinement.
- **The network of a working session is not confined** (§4): `host` is the only usable mode and its egress is open;
  `none` is measurement-only. No egress allowlist is built.
- **The run's own measurement covers the developer's wrapper.** The model reviewer's differs only by its workspace
  bound read-only (and its path); that wrapper is measured by the harness (§5), not again at each run. The runner's
  read-only scope of the reviewed checkout (`orchestrate.adapters.confine`: write bits cleared) is not a boundary — a
  process of the operator's user can give them back; under confinement the read-only mount is what refuses (§5), and
  without confinement only the after-check (`adapters._unchanged`) detects a change.
- **No syscall filter.** The confined process shows `Seccomp: 0` (the container's seccomp was unconfined to let bwrap
  start, and bwrap is not run with `--seccomp`). The boundary is namespaces + capabilities + no-new-privs + mounts.
- **The loosening is real** (§3): on this host nested bwrap needs the container's seccomp dropped and system paths
  unmasked. A Linux host that allows unprivileged user namespaces under its container profile might not — not
  measured here.
- **The session reads the run's clone** (`<out>/repo/.git`, every object and ref) and the client's configuration
  directory: whatever the operator keeps there is readable by the model's code.
- **The write policy decides from what the report shows.** A super block of another mount namespace than the
  controller's (another session's tmpfs reached through `/proc/<pid>/root` in a bind) is not the host's and is not
  excluded by observation; `confine.wrap` binds only the workspace read-write, so no command line it builds does that.
  Two mounts at one path are judged by what the probe sees at the path. The host's table is the controller's own: in a
  container, the container's. It is read once, just before the session starts: a host mount made after that reading and
  before bubblewrap bound its parent in read-write (`confine.wrap` binds only the workspace so) is not told from the
  sandbox's own; it lies inside the workspace tree (B03-R3-conf §13).
- **No translated message was measured** (§6.1): the measurement's locale is fixed to C so that none need be.
- Measured on one host and kernel (Docker Desktop's LinuxKit 7.0.12, arm64). The image's apt packages are not pinned:
  each build gets a new image ID (`measure.log`); the bubblewrap package (`0.12.0-1~deb13u1`) and the binary's
  sha256 (`b3b829e1…`, every profile's JSON) are recorded and equal to the earlier run at `58f3b4e`. A fresh netns on
  this kernel pre-creates DOWN tunnel pseudo-devices, so "no network" is judged by "no route", not by interface names.

## 8. M-levels

| Deliverable | Level | Why |
|---|---|---|
| the setting, the argv builder, fail-closed refusal of run / `--check` / session, each check of the measurement | **M3** | `test_v21_confine` (30 tests, all its own; 31 since `c624c54`, 33 since `0cc47b3`) on macOS with fake clients and providers; no OS boundary exercised on macOS. Since 2026-10-08 the module has also run whole in the Linux guest (§5), still with fake clients. |
| the success path of a confined run (every session started through the bwrap argv, the reviewer's workspace read-only, the records saying so) | **M3** | `test_v21_confine.RunFailClosed.test_a_confined_run_starts_every_session_through_bubblewrap_and_says_so`: the **measurement stubbed** and the argv built for Linux, a recording fake bubblewrap that confines nothing — the wiring, not a boundary. |
| the confinement boundary itself inside a Linux container | **M4** | `validation/v21/sandbox/run.sh` under real `docker`: real bwrap 0.12.0, real namespaces, a real host port, the container's real processes and sockets; the kernel's own `confine.measure` and the session's `confine.wrap` run in the container; each claim an operation tried (§5). A standalone harness, not `aisef run`; the client is a script, no provider — so not M5. |
| a confined real `aisef run` on Linux end to end | **M6** | not done: the macOS host has no Linux backend to run `aisef run` itself under bwrap. |
