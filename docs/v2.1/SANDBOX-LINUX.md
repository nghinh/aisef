# AISEF 2.1 — Minimal Linux confinement of the developer session (track F / B-07)

Scope: confine the **model sessions** the kernel's client starts — the developer and the model reviewer — so the
untrusted code they run cannot read or write anything of the machine beyond the one workspace it is given. This is the
first isolation code on the branch (REPORT F was M6: "chưa có mã cách ly nào trên nhánh"). It is **opt-in** and
**Linux-only**; it changes nothing when the settings do not ask for it.

Module: [`aisef2/app/confine.py`](../../aisef2/app/confine.py). Harness:
[`validation/v21/sandbox/`](../../validation/v21/sandbox/). Measured evidence:
[`evidence/sandbox/`](evidence/sandbox/) (`measure.log`, `P1`–`P5` JSON, `Dockerfile.measure`).

Everything below that says a boundary holds is backed by a **denied operation** in `evidence/sandbox/`, not by config
alone (owner's 2026-10-06 requirement). What is not confined is stated as plainly as what is.

---

## 1. The layers, kept distinct

The owner's requirement: do not write "macOS always has no isolation"; name the real configuration at each layer.

| Layer | What it is here | Boundary it gives the developer code |
|---|---|---|
| **macOS host** | Darwin 25.5.0 arm64, the operator's user | none of its own: there is no Linux container runtime that runs the developer *on the host*. bubblewrap, user namespaces and `/proc`-based process ranges are Linux kernel features; the kernel's existing session runs the client as the operator's user with **no OS boundary** (REPORT §3, DEVELOPER-CONFINEMENT-GAP-001). |
| **Docker Desktop VM** | `docker` 29.8.0, server `linux/arm64` (a LinuxKit VM Docker Desktop runs) | the VM is a boundary between macOS and the Linux guest, but it is Docker's, not AISEF's; AISEF does not manage it. |
| **Linux container (the guest)** | a `docker run` of the pinned `python:3.14-slim-trixie` image, `--user 1000 --cap-drop ALL --pids-limit --memory`, repo mounted read-only | the container is the first boundary AISEF can shape. Its own seccomp/apparmor/masked-paths profile is what decides whether a **nested** sandbox can start (§3). |
| **bwrap inside the guest** | `aisef2.app.confine` builds the argv; one unprivileged user+mount+pid+ipc+uts(+net) namespace per session | the per-session boundary this track adds: the developer code sees only its workspace, no capability, its own PID namespace. **Measured in §4.** |

A `-S` interpreter flag, a git worktree, or a hash check before running is **not** a sandbox and this document never
calls one that (owner's instruction). The boundary here is kernel namespaces proven by denied operations.

## 2. Threat model

The developer (and the model reviewer) run model-written, untrusted code in a checkout. Without an OS boundary that
code runs as the operator's user and can (measured, REPORT §3):

- read every file the operator can read — including a hidden experiment stimulus (DEVELOPER-CONFINEMENT-GAP-001);
- write the client binary (the *runtime*), the run directory while the run is in progress, and the evidence anchor if
  it is reachable;
- leave a `setsid` child that outlives the run (REPORT §4.2).

Trusted, and deliberately **outside** this sandbox: the kernel itself, which drives git, runs the probes and the
developer's tests, computes the evidence and the anchor. Putting the control daemon inside the workload's area is the
anti-pattern OpenSandbox's `execd` demonstrates (UPSTREAM-RESEARCH; design-only reference
`opensandbox-group/OpenSandbox @ c7dc78a4090e`, never vendored). So the confinement wraps **only the client's
session**, never the kernel.

Goal: the session can read/write its workspace and run a program, and nothing else — not the run directory, not the
runtime, not the verifier/anchor, not HOME secrets, not host processes, not the network (unless explicitly shared).

## 3. What each boundary gives — and the honest loosening bwrap needs

Bubblewrap needs to create an **unprivileged user namespace** and mount a fresh `/proc`. A hardened container forbids
both. Measured on this host, going from the hardened container and loosening one axis at a time (full log:
[`evidence/sandbox/measure.log`](evidence/sandbox/measure.log)):

| Profile | Container flags added | Result |
|---|---|---|
| **P1** hardened | *(none)* `--user 1000 --cap-drop ALL --pids-limit 512 --memory 1g` | bwrap **cannot start**: "No permissions to create a new namespace … kernel does not allow non-privileged user namespaces". Every session refused. |
| **P2** | `--security-opt seccomp=unconfined` | bwrap starts the userns but **"Can't mount proc on /proc: Operation not permitted"**. Still refused. |
| **P3** | `+ --security-opt apparmor=unconfined` | **identical** to P2 — apparmor is not the gate on this kernel. Still can't mount `/proc`. |
| **P4** | `+ --security-opt systempaths=unconfined` | bwrap **runs**; measurement clean (0 problems). `systempaths=unconfined` is the axis that unmasks `/proc/*` so bwrap can mount a fresh `/proc`. |
| **P5** | P4 but `--network` shared (not `none`) | bwrap runs; **egress is NOT confined** — the session reaches a host port (§4). |

**This is loosening the container's own boundary.** The nested bwrap sandbox is strong *once it runs* (§4), but to
let it run at all this host's container must drop seccomp and unmask system paths. So nested bwrap buys a second,
per-session boundary **only at the cost of weakening the first**. The recommendation (decision F) therefore remains:
on a real deployment prefer the **container itself as the boundary** (`--network none`/egress sidecar, `--cap-drop
ALL`, `--read-only`, non-root, `--pids-limit`, seccomp kept on) and use nested bwrap only where the container must
stay hardened and the kernel allows unprivileged userns without unmasking. This module gives the bwrap layer; it does
not claim to replace the container profile.

### Fail-closed

When the settings ask for confinement and it cannot be provided — not Linux, no bwrap, a read-only path missing, or
(P1–P3) the sandbox cannot set up its namespaces — the run **refuses before the first provider request** and records
why (`RUN.json.confinement.problems`, stage `confinement`); a single session refuses with `SessionRefused` before the
client starts or its log is created. Nothing is sent to a provider. Proven by `test_v21_confine` (macOS) and by P1–P3
above (the measurement reports the sandbox did not run; a real run would raise `RunRefused`).

## 4. What is confined once bwrap runs (P4, `--network none`)

Every row is a denied operation from [`evidence/sandbox/P4-all.json`](evidence/sandbox/P4-all.json) /
[`measure.log`](evidence/sandbox/measure.log); the positive controls show the workspace still works.

| Claim | Operation attempted in the sandbox | Observed |
|---|---|---|
| read nothing outside the workspace | `cat <run-dir>/canary` | `No such file or directory` (exit 1) |
| the verifier/hidden material is unreachable | `cat <verifier>/hidden.json` | `No such file or directory` |
| HOME secrets unreachable | `cat <op-home>/.ssh/id` | `No such file or directory` (HOME is an empty tmpfs inside) |
| cannot write the runtime (client binary) | `: > <runtime>/opencode` | denied; host check: **runtime unchanged** |
| cannot write the anchor / run directory | append `<run-dir>/EVIDENCE.anchor`; create `<run-dir>/written` | lands only in the sandbox's throwaway tmpfs; host check: **anchor unchanged, no file in the real run directory** |
| cannot see host processes | `ls /proc` numeric entries | only `1 2 3 4 5 6` — its own PID namespace, not the guest's/host's hundreds |
| no network | `socket.create_connection(host-gateway)` | `Network is unreachable` (own empty net namespace; `routed_interfaces: []`) |
| no capability | `/proc/self/status` Cap* | `CapPrm/CapEff/CapBnd/CapInh/CapAmb = 0` |
| no new privileges | `/proc/self/status` NoNewPrivs | `1` |
| its own namespaces | `readlink /proc/self/ns/*` vs the guest's | user, pid, net, ipc, uts, mnt all **own** |
| a setsid child dies with the session | `setsid sleep <unique>` then look for it after | `setsid_survivors: []` — the session's own PID namespace kills every descendant when its init exits |
| **control**: the workspace works | `echo ok > ./w && cat ./w` | `ok` |
| **control**: a client can run | run a fake client in the workspace | prints its JSON |

What `--network none` denies is reachability: `routed_interfaces: []` and the connect is unreachable. (This kernel
pre-creates DOWN tunnel pseudo-devices in a fresh netns, so the proof is "no routes", not "only `lo` exists".)

**P5 (`--network` shared)** is identical except the connect **succeeds** (`UP: reached host`). So when the session is
given the guest's network, egress is not confined and the record must say so — the module reports
`confinement: "bwrap network=host"` on the session and `network` in the measurement.

## 5. The implementation

- **Setting** (`aisef2/app/settings.py`, optional, fail-closed validation):
  `"confinement": {"backend": "bwrap", "bwrap": "<absolute path>", "network": "none" | "host", "read_only": ["<abs>", ...]}`.
  Absent ⇒ a 2.0.0 run, no record key, no wrapping.
- **argv builder** (`confine.wrap`): `--unshare-user --unshare-pid --unshare-ipc --unshare-uts` (and `--unshare-net`
  for `network: none`, else `--share-net`), `--disable-userns`, `--die-with-parent`, `--new-session`, `--cap-drop
  ALL`; the system (`/usr`, `/etc`, …) read-only (a merged-`/usr` symlink stays a symlink); the client's directory,
  the worktree's **common git directory**, the client's config directory and the operator's `read_only` paths
  read-only; the workspace bound **last** read-write (so it wins even below a read-only path); HOME an empty tmpfs with
  `XDG_*` redirected under it, but `XDG_CONFIG_HOME` still pointing at the read-only `opencode` config so the client
  finds its route.
- **Wiring**: `client.session(..., confine=...)` wraps the client and refuses before the log exists when the host
  cannot confine; `run.execute` measures confinement at a new stage before the preflight and refuses the whole run on
  any problem, recording the report as `RUN.json.confinement`; `aisef run --check` measures it too (`ready: false`
  when it is not provided).
- **Measurement** (`confine.measure`): runs a probe shell under the very same wrapper and judges what it observes (the
  table in §4). It never trusts config; a "bwrap" that runs the probe unconfined is refused for *what the probe could
  do*, proven by `test_v21_confine.FailClosed.test_what_is_measured_decides_not_the_name_of_the_tool`.

**Kernel change.** This touches `aisef2/` (settings, client, run, cli, and the new `confine.py`): it needs mutation
coverage and re-qualification outside the current measured snapshot (the new module is already named in
`tests/v2/test_v21_mutation_record.py`'s V2.1 targets list for the campaign, but was not measured here).

## 6. Limits (not confined / not claimed)

- **Not confined** by this track: the kernel's own test execution and probe execution of the candidate, and Open Code
  Review — they still run as the operator's user. This track confines the *client's model sessions* only.
- **No syscall filter.** The confined process shows `Seccomp: 0` inside (the container's seccomp was unconfined to let
  bwrap start, and bwrap is not run with `--seccomp`). The boundary is namespaces + caps + no-new-privs + mounts, not
  syscall filtering. A real deployment should keep the container's seccomp on and not rely on nested bwrap (§3).
- **The loosening is real** (§3): nested bwrap on this host needs the container's seccomp dropped and system paths
  unmasked. Measured as a VM container on macOS Docker Desktop; a native Linux host or a Linux host with unprivileged
  userns enabled would not need the same loosening — not measured here.
- **Network `host`** does not confine egress (§4, P5); only `network: none` was proven to cut the network. A domain
  allowlist egress sidecar (the reusable OpenSandbox piece, UPSTREAM-RESEARCH) is not built here.
- Measured only on this one host/kernel; `--network none`'s pre-created tunnel devices are kernel-specific.

## 7. M-levels

| Deliverable | Level | Why |
|---|---|---|
| argv builder + fail-closed refusal, settings, wiring into `client`/`run`/`--check` | **M3** | `test_v21_confine` (16 tests) on macOS: the setting, the command line, and every fail-closed path, with fake clients/providers; no OS boundary exercised on macOS. |
| the confinement boundary itself (denials + controls) inside a Linux container | **M4** | `validation/v21/sandbox/run.sh` under real `docker` (real bwrap 0.12.0, real namespaces, a real host port and host process table), each claim a denied real operation; `evidence/sandbox/`. The model is still never called (fake client); no paid provider — so not M5. |
| wired into a real `aisef run` on Linux end to end | **M6** | not done here: the macOS host has no Linux backend to run `aisef run` itself under bwrap; measured only via the standalone harness inside the container. |
