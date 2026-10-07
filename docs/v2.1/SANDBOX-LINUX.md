# AISEF 2.1 — Minimal Linux confinement of the model sessions (track F / B-07)

Scope: confine the **model sessions** the kernel's client starts — the developer and the model reviewer — so the
untrusted code they run cannot write anything of the machine beyond the one workspace it is given, and reads only
what is listed in §2. This is the first isolation code on the branch (REPORT F was M6: "chưa có mã cách ly nào trên
nhánh"). It is **opt-in** and **Linux-only**; it changes nothing when the settings do not ask for it.

Module: [`aisef2/app/confine.py`](../../aisef2/app/confine.py). Harness:
[`validation/v21/sandbox/`](../../validation/v21/sandbox/). Measured evidence:
[`evidence/sandbox/`](evidence/sandbox/) (`measure.log`, one JSON per profile, `Dockerfile.measure`), recorded at the
committed tree `3e0409c` (`measured tree: … uncommitted paths: 0` in `measure.log`); the setsid-survivor check
against the PID namespace's teardown: `teardown-race-plain.json`, `teardown-race-sock.json` (§5).

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
| **writes** (host-backed) | the developer's session: its workspace — nothing else. The model reviewer's session: **nothing** — the checkout it reviews is bound read-only as well (`confine.wrap(…, writable=False)`, §5). Everything else a session writes lands in its own tmpfs (`/`, `/tmp`, an empty HOME) and is gone when it exits. |
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
| a setsid child dies with the session | the measurement's `setsid sleep <unique>`, then a look for it once bubblewrap returned (one found is looked at again until gone, for up to 1 s) | `setsid_survivors: []` |

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
to `SURVIVOR_GRACE` (1 s); only one still alive then (the process table drops zombies) is a survivor. Measured with X1's container flags and
the run's `network: host` (`validation/v21/sandbox/teardown_race.py`, 500 measurements each): without a socket, the first look never found
the sleeper; with the read-only socket directory, it found it in 2 of 500 (measurements 20 and 34), the second look
found it gone, and none reported a survivor — 0 of 1000. The positive control on Linux's `/proc` table: a
"bubblewrap" that confines nothing leaves its sleeper alive, and the measurement reports it after the grace (14
looks; the whole measurement 1.1 s; the pid still alive when it returned). The direction stays fail-closed: a survivor is only ever
dropped by being gone.

**Controls** (must work): the workspace (`echo ok > ./w && cat ./w` → `ok`); the client started from its own
read-only mounted directory prints its JSON.

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
  `/usrlocal-extra` within `/usr`); a namespace is `own` only when its `/proc/self/ns` link was read inside and outside
  (`<name>:[<inode>]`) and they differ; a check that did not run is a problem; a probe sleeper found when bubblewrap
  returns counts as a survivor only if still alive after up to 1 s (§5;
  `test_a_sleeper_still_dying_when_bubblewrap_returned_is_no_survivor`, `test_a_killed_sleeper_is_no_survivor_a_live_one_is`).

**Kernel change.** This touches `aisef2/` (settings, client, run, cli, and the new `confine.py`): it needs mutation
coverage and re-qualification outside the current measured snapshot. `confine.py` is **not** a mutation target today:
`validation/v2/mutation.py` has no `aisef2/app/confine.py` entry (in neither `TARGETS` nor `V21_TARGETS`), and
`run.py::client_on_path` is not one either; `tests/v2/test_v21_mutation_record.py` does not name them. Its coverage
therefore needs new target entries in `validation/v2/mutation.py` (frozen for the running campaign, so not changed
here), not only a later measurement. Against `closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST.json` (snapshot
`cc53596`), `v21_requalification.py --check` on this branch (`ac27348`) reports 5 changed V2.1 targets —
`cli.py::run`, `client.py::session`, `run.py::execute`, `settings.py::OPTIONAL`, `settings.py::load`; counted as its
`scope()` counts them (`mutation.mutants`), 116→133, 114→128, 315→337, 2→3 and 254→268 mutants (+68). Targeted mutants of this track were run on scratch copies only — not campaign evidence: 45/45 killed
at `ac27348` (the 11 that survived the previous tests at `0da842f` among them; same script, same copy method); and the
5 the round-2 verifier saw survive the 24 tests at `4e00a0d` (`_within` without its `/`, the user's home not checked
when the env has no HOME, an unreadable bubblewrap raising, a non-Linux measurement making its worktree, `--check`
measuring without the client) survive them again and are killed by the 26 at `affcefb` (tests only: `aisef2/` is
unchanged since `ac27348`). Round 3 changes `aisef2/app/confine.py` only (`_survivors`, `SURVIVOR_GRACE`; not a
mutation target; the files of the 5 targets above are unchanged since `ac27348` by `git diff`, so their counts
above stand — `--check` itself was not re-run): 6/6 targeted
mutants of the grace killed by the 28 tests at `3e0409c`; two of them — no grace (the round-2 code) and a grace of
0 — survive the 26 round-2 tests.

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
- Measured on one host and kernel (Docker Desktop's LinuxKit 7.0.12, arm64). The image's apt packages are not pinned:
  each build gets a new image ID (`measure.log`); the bubblewrap package (`0.12.0-1~deb13u1`) and the binary's
  sha256 (`b3b829e1…`, every profile's JSON) are recorded and equal to the earlier run at `58f3b4e`. A fresh netns on
  this kernel pre-creates DOWN tunnel pseudo-devices, so "no network" is judged by "no route", not by interface names.

## 8. M-levels

| Deliverable | Level | Why |
|---|---|---|
| the setting, the argv builder, fail-closed refusal of run / `--check` / session, each check of the measurement | **M3** | `test_v21_confine` (28 tests, all its own) on macOS with fake clients and providers; no OS boundary exercised on macOS. |
| the success path of a confined run (every session started through the bwrap argv, the reviewer's workspace read-only, the records saying so) | **M3** | `test_v21_confine.RunFailClosed.test_a_confined_run_starts_every_session_through_bubblewrap_and_says_so`: the **measurement stubbed** and the argv built for Linux, a recording fake bubblewrap that confines nothing — the wiring, not a boundary. |
| the confinement boundary itself inside a Linux container | **M4** | `validation/v21/sandbox/run.sh` under real `docker`: real bwrap 0.12.0, real namespaces, a real host port, the container's real processes and sockets; the kernel's own `confine.measure` and the session's `confine.wrap` run in the container; each claim an operation tried (§5). A standalone harness, not `aisef run`; the client is a script, no provider — so not M5. |
| a confined real `aisef run` on Linux end to end | **M6** | not done: the macOS host has no Linux backend to run `aisef run` itself under bwrap. |
