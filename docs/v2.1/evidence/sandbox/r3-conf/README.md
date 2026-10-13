# B03-R3 conf — records of a real bubblewrap in the Linux guest (2026-10-12)

What these files are: the output of `validation/v21/sandbox/r3_conf_guest.py` (modes `scenarios`, `shared-tree`,
`locale`), run once each on 2026-10-12 against the working tree of branch `v21r3/conf` (base `3dc827b`; the tree of the
commit that adds these files, `aisef2/app/confine.py` as committed there). They back the decision
[`../../../decisions/B03-R3-conf.md`](../../../decisions/B03-R3-conf.md) and are replayed by
`tests/v2/test_v21_r3_conf_policy.py` (`RecordedGuest`) and `tests/v2/test_v21_r3_conf_locale.py` (`RecordedGuest`).

## The environment — a container in Docker Desktop's VM on a Mac, not bare-metal Linux, not CI

Each record's `environment`: guest kernel `Linux 7.0.12-linuxkit aarch64`, Debian GNU/Linux 13 (trixie), Python 3.14.8,
bubblewrap 0.12.0, uid 1000 (0 in `shared-tree`: root of a user namespace the harness made), locales `C`, `C.utf8`,
`POSIX`. One container per run, discarded: image `aisef-sandbox-measure` (the one of
`../linux-guest-2026-10-11/`), `--init --network none --user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g
--cpus 2`, the profile **X1** (`seccomp=unconfined`, `systempaths=unconfined`: what bubblewrap needs, SANDBOX-LINUX §3),
the tree read-only at `/repo`. Through `guest.sh` only (no other docker call); `opencode` is never run (the client is a
shell script) and no provider is called.

```
guest.sh <tree> X1 python3 -B /repo/validation/v21/sandbox/r3_conf_guest.py scenarios     > scenarios-X1.json
guest.sh <tree> X1 python3 -B /repo/validation/v21/sandbox/r3_conf_guest.py shared-tree   > scenarios-X1-shared-tree.json
guest.sh <tree> X1 python3 -B /repo/validation/v21/sandbox/r3_conf_guest.py locale        > locale-X1.json
```

## `scenarios-X1.json`: the judgement on twelve command lines, run for real

Each scenario is the session's own command line (`confine.wrap`, a client in a directory of its own, a worktree of a
run repository, a configuration directory) with the options of the second column added before `--chdir` (or one
dropped); the kernel's own `confine._probe` ran the real probe under the real bubblewrap, with the container's own
`/proc/self/mountinfo` as the host's table. `report` is the whole report; `table_unchanged` is the host's table before
and after the session. All twelve: `table_unchanged: true`; `setsid_survivors: []` but for `shared-pid-namespace`.

| scenario | added / dropped | `problems` about writable mounts |
|---|---|---|
| `baseline` | — | none |
| `alt-dev-sandbox-devpts` | `--dev /alt-dev` | none: bubblewrap's own tmpfs `0:86` and devpts `0:87` at `/alt-dev` |
| `mqueue-sandbox` | `--mqueue /mq` | none (`/mq`: mqueue `0:59`; "mounted beyond" only: `--mqueue` is not an option `confine.targets` knows) |
| `host-devpts-at-other-path` | `--dev-bind /dev/pts /host-pts` | `/host-pts`: its super block 0:72 is the host's (mounted there at /dev/pts) |
| `host-mqueue-bound` | `--dev-bind /dev/mqueue /hostmq` | `/hostmq`: super block 0:64 |
| `host-dev-bound` | `--dev-bind /dev /host-dev` | `/host-dev` 0:69, `/host-dev/pts` 0:72, `/host-dev/mqueue` 0:64, `/host-dev/shm` source `shm` |
| `host-shm-over-dev-shm` | `--dev-bind /dev/shm /dev/shm` | `/dev/shm`: mount source `shm`, not tmpfs's own |
| `ext4-file-at-dev-x` | `--bind /etc/hostname /dev/x` | `/dev/x` (ext4: not a file system a wrapper makes) |
| `regular-file-at-dev-null` | `--bind <regular file> /dev/null` | `/dev/null`: read `other`, not the character device 1:3 |
| `zero-at-dev-null` | `--dev-bind /dev/zero /dev/null` | `/dev/null`: read 1:5, not 1:3 |
| `ptmx-at-dev-ptmx2` | `--dev-bind /dev/ptmx /dev/ptmx2` | `/dev/ptmx2`: super block 0:72 is the host's |
| `shared-pid-namespace` | `--unshare-pid` dropped | `/proc`: super block 0:66 is the host's; also "the pid namespace is not the session's own (shared)" and the probe's sleeper survived |

(The container's own tmpfs for `/dev` is `0:69`; the host's devpts `0:72`, mqueue `0:64`, `/proc` `0:66`: values of
these containers, not constants.)

## `scenarios-X1-shared-tree.json`

The same scenarios inside `unshare --user --map-root-user --mount` after `mount --make-rshared /`: the container's mount
tree then has peer groups, as a systemd host's has. What it shows: the host's table holds `shared:N` groups; the rows
the sandbox **inherits** are `master:N` of them (the device nodes `master:7`, the system and the workspace `master:5`);
the rows it **makes** (`/`, `/proc`, `/dev`, `/dev/pts`, `/tmp`, `/aisef-home`) have no propagation field; every
verdict is the same as in `scenarios-X1.json`. This is a namespace of the container that imitates a systemd host's
propagation; it is not a systemd host.

## `locale-X1.json`

`confine.measure` with its `bwrap` a one-line wrapper that saves its own `env` and `exec`s `/usr/bin/bwrap`, for a
caller whose environment carries `LANG=vi_VN.UTF-8`, `LC_ALL=de_DE.UTF-8`, `LC_MESSAGES=fr_FR.UTF-8`, `LANGUAGE=ja`
(each locale absent from the guest). The real bubblewrap received two calls (`--version`, the probe), both with
`LANG=C` and `LC_ALL=C` and no other `LANG*` / `LC_*` variable; `os.environ` of the harness was unchanged; the
measurement's `problems` is empty (its refusal of a further user namespace read under C) and `report.locale` is
`{"LANG": "C", "LC_ALL": "C"}`.

## What this does not show

* **A translated message.** The guest has only `C`, `C.utf8` and `POSIX`: that a non-English `unshare` message differs and
  would not match `USERNS_REFUSED` was not observed. It needs an image with a non-English locale generated and the
  util-linux catalogue for it under the sandbox's `/usr`, and the `unshare --user true` probe run under it and under C.
* **Bare-metal Linux, CI Linux, a systemd host, a devtmpfs `/dev`, Windows, macOS** (no backend there).
* A confined `aisef run` end to end (no provider, no `opencode`).
* That these hold at another tree: they hold at one where `aisef2/app/confine.py`, `PROBE` and the harness are
  byte-identical.

## `review-X1.json` (the independent review's run, 2026-10-13)

`guest.sh <tree> X1 python3 -B /repo/validation/v21/sandbox/r3_conf_review_guest.py > review-X1.json`: command lines and
operator settings the scenarios above did not try, through `confine._probe` with the real bubblewrap 0.12.0, at the tree
of the review's commit (the tree of `scenarios-X1.json` plus the one change recorded in `decisions/B03-R3-conf.md` §12,
which no row of these records reaches). Each entry: `accepted`, the `problems`, the nodes read inside, every writable
mount besides the workspace (accepted or not), and `table_unchanged`.

| entry | what it shows |
|---|---|
| `dev-bind-null-over-null` | `--dev-bind /dev/null /dev/null` gives the same row as `--dev` placed: accepted (identity decides, not the option) |
| `bind-null-at-dev-x` | the same device under a name outside the list: refused (the container's `/dev` super block) — the earlier clause accepted it by place |
| `stdin-is-a-terminal` | the controller's stdin is a pseudo terminal: no `/dev/console` row, accepted |
| `read_only /tmp`, `/run`, `/dev/shm`, `/dev/pts` | accepted: nothing writable is added |
| `read_only /dev` | refused by the earlier checks as before (`unshare: absent`, no `find`): a read-only `/dev/null` stops the probe's own redirects |

Not shown: that a translated message differs (a hand-built German `libc.mo` on a tmpfs over `/usr/share/locale` was not
loaded by the guest's glibc 2.41, so no translated text was produced); another namespace's super block bound in
(`/proc/<pid>/root` of a process in a user namespace of its own is refused with EACCES for an unprivileged caller).

## `fu-X1.json` (the follow-up FU-CONF's run, 2026-10-13)

`guest.sh <tree> X1 python3 -B /repo/validation/v21/sandbox/r3_conf_fu_guest.py reuse` at the tree of `c05d19c` (the
review head, with the driver copied in) and at the tree of `5012420` (the follow-up), plus the drivers above
(`scenarios`, `shared-tree`, `locale`, `r3_conf_review_guest.py`), `validation/v21/sandbox/measure.py`
(`NETWORK=host|none`) and the confinement tests under the `hardened` profile at `5012420`, condensed here (the raw
outputs are not kept: they hold temporary directory names and the whole reports of the records above). What it shows:

* `reuse`: 48 unrelated tmpfs file systems mounted by the driver, in the controller's own mount namespace, in place of the
  second reading of the host's table (after the session ended). They took six of the session's own super block numbers.
  Before the change the correct session is refused (six mounts "the host's"); after it, accepted. The container's mqueue
  bound read-write is refused by its super block in both, with and without the mounts. Real bubblewrap and real kernel
  numbers; the unrelated host activity is the driver's (simulated).
* the twelve scenarios (both modes) and the eight review ones: the same verdicts and problems as the records above (but
  for super block numbers and a pid), `host_mounts_appeared: []`, `table_unchanged: true`.
* `measure.py`: `problems: []` for both networks, `host_mounts_appeared` a list; `hardened`: 179 tests OK (skipped=1).
