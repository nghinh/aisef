# Linux guest checks, 2026-10-11 (V2.1 F; owner 2026-10-10 item 6: schedule the Docker run so it is not left open)

The output of `validation/v21/sandbox/linux_guest.sh` (harness `linux_guest.py`), run once on 2026-10-11 from 06:42:00 to
06:43:11 +07 against the tree of commit `f6bece0` (`v2.1/foundation`: the campaign-2 evidence on top of `995a295`; its
`aisef2/` is the one campaign 2 measured plus the post-snapshot changes in `campaign-2/delta/DELTA.md`). Docker Desktop
had been stopped since 2026-10-09 20:43 (memory and `fseventsd` pressure, owner-authorised) and was started for this run;
no mutation measurement was running (the campaign ended 2026-10-10 21:42), host load average 3.6–4.0 throughout.

## The environment — not bare-metal Linux, not CI

Linux containers inside Docker Desktop's VM on a Mac; every value is in `environment.txt` / `commands.txt`:
macOS 26.5.2 (Darwin 25.5.0 arm64); Docker Desktop 4.91.0 (239619), client and engine 29.8.0, containerd v2.3.4, runc
1.4.3, docker-init 0.19.0; guest kernel `Linux 7.0.12-linuxkit #1 SMP PREEMPT Thu Aug 27 14:02:21 UTC 2026 aarch64`,
8 CPUs, cgroup v2, AppArmor not in this kernel; image `aisef-sandbox-measure`
`sha256:568d868ab18d64f7da961ab103e604ff7e5d18fc05cfccaa1946890b0d8b15ed` (Debian 13.7, Python 3.14.8, bubblewrap
0.12.0), unchanged since round 2; `ps` / `libproc2.so.0` from the local `postgres:16.15` (sha256 `388a5062…9023` /
`edb1e982…383d`, the same as round 2); tree = `git archive f6bece0 -- . ':(exclude)closure-evidence'`, tar sha256
`fa132c02…65ca`, 1,312 files. Containers: `--rm --init --network none --user 1000:1000 --cap-drop ALL --pids-limit 512
--memory 1g --cpus 2`, tree and the two procps files read-only; profile X1 (a, c) adds seccomp and systempaths
unconfined, hardened (b, d1, d2) adds nothing. One container at a time; no network; `opencode` never run; no provider.
The client is a script. The other two containers in the VM (`postgres:16.15`, `valkey/valkey:9.1.1`, restarted by
Docker's policy when it started) were not touched.

## Result

All 6 containers exited 0 (10, 5, 5, 16, 16, 18 s); every `*.err` of a, b, c and d1 is empty.

| Check | Profile | Result |
|---|---|---|
| a, b, c, d1 | X1, hardened, X1, hardened | Same structure and the same values as round 2 (`../linux-guest-2026-10-08-r2/`): key sets identical, no boolean or list-length differs; the only keys that differ are the process-table rows (pids, birth times, commands). Programmatic comparison, this run's `a.out`…`d1.out` against round 2's. |
| d `tests.v2.test_v21_confine` | hardened | **Ran 34 tests in 14.6 s, OK** (`d-test_v21_confine.err`): the module's own log at this tree; round 2 measured 33 tests (the module has one more since) |
| d `tests.v2.p4.test_process_range` | hardened | Ran 24 tests in 17.9 s, OK (`d-test_process_range.err`) |

The 34-test module run replaces the commit-message-only "Ran 34 OK" of `889ce28`/`e71a102` with a log (`U-2` of the
handover draft).

## What this does and does not show

It shows the confinement measurement, the cleanup-authority claims and the two test modules behave on a Linux guest at
this tree as they did at round 2's. It does not show: a confined `aisef run` with a real model or `opencode` (no run
was made), bare-metal Linux or CI Linux, Windows, or that these files hold at a later tree — they hold at another tree
only if `aisef2/`, `validation/v21/sandbox/`, `tests/v2/test_v21_confine.py`, `tests/v2/p4/test_process_range.py` and
`tests/v2/isolated_git.py` are byte-identical there; the run is repeated at the final candidate otherwise.
Observation, not a conclusion: `fseventsd` stayed at 4–5 MB through Docker's start and this run (about 6 minutes); the
memory growth of 2026-10-09 was not reproduced in that window.
