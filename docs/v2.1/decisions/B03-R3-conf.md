# B03-R3 conf — the write policy of `confine._judge` and the locale of `confine.measure`

Work package `conf`, branch `v21r3/conf`, base `3dc827b`. Files: `aisef2/app/confine.py`, `docs/v2.1/SANDBOX-LINUX.md`,
the tests named in §8, the guest harness `validation/v21/sandbox/r3_conf_guest.py` and its records in
`docs/v2.1/evidence/sandbox/r3-conf/`.

## 1. The owner's decision (2026-10-12, B-03 round 3, items 2 and 3), verbatim

**Writes.**
> Tôi chọn chính sách: developer chỉ được ghi vào workspace và các tài nguyên phục vụ thực thi được cho phép rõ ràng, cô lập theo phiên.
> Không coi mọi mount ghi được ngoài workspace đều là vi phạm; cũng không miễn trừ chung cho devpts/mqueue. Chỉ chấp nhận khi chứng minh được mount/namespace thuộc sandbox, không mở đường ghi vào host hoặc phiên khác và có vòng đời dọn dẹp phù hợp.
> Đánh giá bằng loại filesystem, nguồn mount, mount options và namespace; không chỉ dựa vào tên hay vị trí dưới `/dev/`. Trường hợp không xác định được phải từ chối hoặc báo chưa đủ điều kiện cách ly.
> Áp dụng chính sách này cho 4 mutant `confine._judge`, bổ sung kiểm chứng cho cả trường hợp được phép và trường hợp có khả năng ảnh hưởng ra ngoài sandbox.

**Locale.**
> Tôi chọn locale C cho subprocess thu thập bằng chứng của `confine.measure`, nhằm có đầu ra phân tích ổn định. Ghi nhận locale sử dụng trong metadata; không thay đổi locale toàn phiên của người dùng hoặc mặc nhiên áp dụng cho ứng dụng đang được kiểm thử.
> Image chỉ có C/POSIX chưa đủ để kiểm chứng khác biệt. Dùng môi trường thử có locale khác hoặc phép thử kiểm tra chính xác môi trường được truyền xuống subprocess. Phân biệt rõ bằng chứng mô phỏng và thực chạy.

## 2. Reading, and where the code differs from the work-package text

Writes. A writable mount outside the workspace is acceptable only when the report **shows** it belongs to the sandbox, by
(a) its file-system type, (b) its mount source, (c) its mount options and (d) its namespace; the name of the file system
and a place under `/dev/` decide nothing; anything the report cannot show is refused (or reported as isolation not
established). The four mutants of `_judge` (#142, #143, #157, #158: `devpts` and `mqueue` dropped from the exempt tuple)
die with the clause they were mutants of.

Locale. The probe (and `bwrap --version`, the other evidence-collecting subprocess `measure` starts itself) runs in
`LC_ALL=C LANG=C`; nothing else of the LANG/LANGUAGE/LC_* family reaches it; the report records the locale; `os.environ`
and what a *session* gets are untouched. The two mutants of `measure` (#40, #49: `LANG` in the passed-through keys) die
with that pass-through.

Where the code differs from the work-package text (the code and the owner's words won):

1. **bubblewrap 0.12.0 can create an mqueue** (`--mqueue DEST`, `bwrap --help` in the guest). The work package says it
   cannot, so a sandbox-owned mqueue would be simulated only. It is real here (`mqueue-sandbox` in the guest record:
   `/mq`, `mqueue`, source `mqueue`, super block `0:59`, not the container's `0:64`).
2. **The device nodes are `tmpfs` rows in the guest, not `devtmpfs`**: Docker's `/dev` is a tmpfs, so
   `/dev/null` is a rw bind of a node of that tmpfs (`0:69 /null`, the container's own `/dev` super block), with
   `nosuid` and without `nodev`. On a bare host the same rows say `devtmpfs`. A rule that names a file-system type for the
   nodes would be right on one of them only; identity (§4.2, class D) is the same on both.
3. **The sandbox's root row has `root` = `/newroot`**, not `/` (bubblewrap binds a directory of the tmpfs it made). A
   rule "a mount made inside is the root of its file system" would refuse the sandbox's own root.
4. **The old clause accepted the host's `/dev/pts`, `/dev/mqueue`, `/dev`, `/dev/shm` and `/proc`**, bound in or shared
   (§3): it accepted all twelve measured variants, nine of which are write paths the new clause refuses — it was not only
   "unproven", it was wrong.

## 3. What the old clause did, measured

`aisef2/app/confine.py` at `3dc827b` judged a writable mount by the file system's *name* (`tmpfs`, `proc`, `devpts`,
`mqueue` exempt) and by its *place* (anything under `/dev/` exempt). Run on the twelve reports the guest produced
(real bubblewrap 0.12.0, `scenarios-X1.json`; the report's rows carry the old clause's three fields), the old clause
and the new one:

| Scenario (what the command line was changed to) | old clause | new clause |
|---|---|---|
| `baseline`: the session's own line | accepts | accepts |
| `alt-dev-sandbox-devpts`: a second `--dev /alt-dev` (a sandbox-made devpts outside `/dev/`) | accepts (by name) | **accepts (proved)** |
| `mqueue-sandbox`: `--mqueue /mq` (a sandbox-made mqueue) | accepts (by name) | **accepts (proved)** |
| `host-devpts-at-other-path`: the container's devpts `--dev-bind`ed at `/host-pts` | accepts (by name) | **refuses**: its super block `0:72` is the host's |
| `host-mqueue-bound`: the container's mqueue at `/hostmq` | accepts (by name) | **refuses**: `0:64` is the host's |
| `host-dev-bound`: the container's `/dev` (tmpfs + submounts) at `/host-dev` | accepts (by name) | **refuses** each of the four |
| `host-shm-over-dev-shm`: the container's `/dev/shm` over `/dev/shm` | accepts (by place and name) | **refuses**: source `shm` |
| `ext4-file-at-dev-x`: a writable ext4 file at `/dev/x` | accepts (by place) | **refuses**: not a pseudo file system |
| `regular-file-at-dev-null`: a regular file over `/dev/null` | accepts (by place) | **refuses**: read `other`, not 1:3 |
| `zero-at-dev-null`: `/dev/zero`'s node over `/dev/null` | accepts (by place) | **refuses**: read 1:5, not 1:3 |
| `ptmx-at-dev-ptmx2`: a node outside the list | accepts (by place) | **refuses**: the host's devpts `0:72` |
| `shared-pid-namespace`: no `--unshare-pid` (the container's `/proc`) | accepts (by name) | **refuses**: `0:66` is the host's |

Reproduce: `python3 -B validation/v21/sandbox/r3_conf_old_judge.py 3dc827b docs/v2.1/evidence/sandbox/r3-conf/scenarios-X1.json`
(it loads `git show 3dc827b:aisef2/app/confine.py` under another module name and gives its `_judge` each record's report;
the rows of a record hold the three fields that clause read).

## 4. Design

### 4.1 What a row and the report carry

`_mounts` keeps, besides `at`, `access` and `fs`, what the policy decides from: `dev` (major:minor — the super block,
shared by every mount of a file system, a bind included), `root`, `source`, `options` (per-mount), `super_options`,
`optional` (the propagation fields). `access` is still `ro` only when a *per-mount* option says so.

`_probe` records, new: `host_mounts` (the controller's own `/proc/self/mountinfo` — "the host" — as `{at, fs, dev,
optional}` per mount, read before the session starts and again after it ended; a super block held at either moment
counts; `None` when either reading failed or a line did not parse), `inside.devices` (what the probe read of each
mount point named like a device node: `{path: "1:3" | "other"}`), `inside.device_roots` (the destinations of `--dev` in
the command line) and `locale`. The report is the record: a verifier re-derives every acceptance from `inside.mounts`,
`host_mounts`, `inside.devices` and `inside.device_roots` (`RecordedGuest` does).

### 4.2 The policy (`_owned`, called by `_writes` for each `rw` mount other than the workspace)

| Class | Accepted when (all) | Evidence it rests on |
|---|---|---|
| **W** the workspace | `at == str(ws)` (unchanged: the one host-backed writable mount) | the command line's last `--bind` |
| **D** an execution resource | the name is one of `null zero full random urandom tty` and its parent directory is a `--dev` destination of the command line, **and** the probe read the node, inside, as a character device of exactly the number the kernel gives that name (`1:3 1:5 1:7 1:8 1:9 5:0`) | `inside.device_roots` (the option made it), `inside.devices` (`[ -c ]` and `stat -L -c %t:%T`, run inside) |
| **P** a mount the sandbox made | the file system is one a wrapper can make (`tmpfs proc devpts mqueue`) **and** its mount source is that file system's own name **and** its super block is not one the host's table holds **and** no peer group of the host propagates into or out of it (each optional field is `shared:N` of a group the host does not hold, or none) | `inside.mounts[].fs/source/dev/optional`, `host_mounts` |
| anything else | refused (known: it is the host's) or *not established* (an unread field, an unreadable table) | — |

How P answers each part of the owner's text:

* *belongs to the sandbox / opens no path to the host or another session*: a tmpfs, devpts instance, proc or mqueue
  mounted inside the sandbox is a super block of its own. The kernel gives every `tmpfs` mount its own super block and every
  `devpts` mount a new instance; a `proc` super block is keyed by the PID namespace and an `mqueue` one by the IPC
  namespace. A mount of any of them that **shares** the host's namespace is the host's super block, which the table
  holds — measured: `shared-pid-namespace` gives `/proc` as `0:66`, the container's, and `host-mqueue-bound` `0:64`. So
  "its super block is not the host's" is the proof that a write cannot reach the host's file system, and — the
  sandbox's mounts being reachable only from its own mount namespace — not another session's, with the one gap of §11
  (another namespace's super block bound in by an option).
* *namespace*: for the file systems that live in a namespace (devpts, tmpfs: mount; mqueue: IPC; proc: PID) the
  judgement already refuses the session unless that namespace is its own (`need` in `_judge`, unchanged); a row of a
  namespace that is not the session's would also carry the host's super block. Both are in the record of
  `shared-pid-namespace`.
* *mount options*: the per-mount `ro`/`rw` decides whether a mount is a write at all. The others (`nosuid`, `nodev`,
  `noexec`, `relatime`, the super block's `size=`, `mode=` …) are recorded and do not change what a write can reach,
  so nothing is decided from them; a super block that says `ro` is deliberately not credited when the mount says
  `rw` (a remount of the super block from the host would make it writable).
* *lifecycle*: see §6.

Class D is an allowance, not a proof of ownership: bubblewrap binds the host's own device nodes, so they are host-backed
(`0:69`, the container's `/dev`, in the guest). They are accepted because they are an explicitly allowed list of
execution resources, each by what it *is* (the character device of that number, read inside) and by the option that
placed it (`--dev`) — not by its name alone, and not by the file system it sits on. A
regular file, another device, a name outside the list, a node `--dev` did not place and a node the probe could not
read are refused (the last as *not established*).

### 4.3 What an operator reads

* `writable outside the workspace: ['/a', '/b']` — as before for a mount that is writable host storage; when the mount's
  file system is a pseudo one, a parenthetical gives the reason per mount (`its super block 0:72 is the host's (mounted
  there at /dev/pts)`, `its mount source is '/srv/export', not tmpfs's own`, `it propagates with the host's peer group
  ['shared:5']`, `it is not shown to be the character device 1:3 (read: 1:5)`).
* `cannot establish that a writable mount belongs to the sandbox (isolation not established, not a write that was
  seen): /x: the host's mount table could not be read; …` — for what is not shown either way. It is a refusal of the
  run (any problem is), worded so it cannot be mistaken for a measured write.

### 4.4 The probe's `devices` section

`PROBE` adds, after the mount table, a section that reads — inside the sandbox — every mount point of the table whose
last component is one of the six names: `char <major:minor> <path>` when `[ -c <path> ]`, `other - <path>` when it
is not, nothing for another name. It needs no new argument (the positions `$1…$9` and the host directories are
unchanged) and reads the table the session sees.

### 4.5 The locale

`LOCALE = {"LC_ALL": "C", "LANG": "C"}`. `_probe` builds the subprocesses' environment as the session wrapper's result
(`inside_env`) with every `LANG*` and `LC_*` entry removed and `LOCALE` added, uses it for the probe and for
`bwrap --version`, and records the family it actually passed as `rep["locale"]`. `measure` no longer lists `LANG` among
the caller's variables it takes over; `wrap` (shared with real sessions) is not touched, so a session keeps the
locale of its own environment. The git commands of the measurement (`workspace.git`) and the process table are other
modules' and not parsed for text; they are not changed.

## 5. Alternatives considered and rejected (with the evidence)

1. **Exempt devpts/mqueue by type** (the "option A" draft in `closure-evidence/.../round-2-drafts`): the owner declined
   it, and §3 shows it is a write path (the container's `/dev/pts` and `/dev/mqueue` rows).
2. **Exempt what lies under `/dev/`** ("option b"): `ext4-file-at-dev-x` is a writable host file.
3. **Require `root == "/"` for a sandbox-made mount**: the sandbox's own root is `/newroot` (§2.3).
4. **Refuse a mount whose destination is also a `--bind`/`--ro-bind` destination** (a rule built from the command line
   alone, to catch another namespace's super block): it refuses the covered `--tmpfs /tmp` row whenever the operator
   sets `read_only: ["/tmp"]`, which mountinfo lists beneath the bind (`test_v21_defects_confine`,
   `SocketsBelowAHostDirectoryBoundAtASyntheticMount`). Dropped; the gap is stated in §9.
5. **Judge the device nodes by file system** (`tmpfs`/`devtmpfs`): right on one host and wrong on the other (§2.2); and
   by `root`'s base name: refuses a `/dev` that is a bind of a sub-directory.
6. **Prove a node a character device from the controller's `stat` of its own `/dev/<name>`**: it proves the host's node,
   not what the session has at the mount point (a bound regular file). The in-sandbox `stat` proves the latter.
7. **Read the host table once, before the session**: a super block the host mounts between the reading and the start of
   bubblewrap, or one it drops while a session holds it, is missed by one reading. Two readings, union.

## 6. The lifecycle claim, and what it rests on

*Measured* (real guest): after each of the twelve sessions the host's table equals the table before it
(`table_unchanged: true` in every record) — no mount of the sandbox outlives it in the host's namespace — and
`setsid_survivors` is `[]` except in `shared-pid-namespace`, where the probe's sleeper survived: the PID namespace
was the container's, and the judgement names it (`a process the session left outlived it`). The refusal of a further
user namespace and the namespaces' `own` checks are the existing ones.

*Kernel behaviour relied on, not measured here*: a tmpfs, devpts instance, proc or mqueue super block lives as long as
a mount of it exists in some mount namespace; the sandbox's only mounts of its own are in its mount namespace, which
is destroyed when its last process exits; proc's and mqueue's super blocks additionally die with the PID / IPC
namespace. With `--die-with-parent`, bubblewrap's init as PID 1 of the PID namespace and `setsid_survivors == []`,
nothing keeps that namespace alive. Not shown: a process of the host holding an open `/proc/<pid>/ns/mnt` of the
session keeps the namespace (and its RAM-backed file systems) alive; nothing here looks for one.

## 7. Requirement → test

| Requirement | Test (`tests/v2/…`) |
|---|---|
| a pseudo file system the sandbox made is accepted wherever it lies | `test_v21_r3_conf_policy.SandboxMade` |
| the host's devpts / mqueue / tmpfs / proc, a host path or device as source, a file system a wrapper cannot make, a peer group of the host: refused, with the reason; a place under `/dev/` exempts nothing | `…policy.HostBacked` |
| what cannot be read is "isolation not established", never a pass, never "writable" | `…policy.NotEstablished`, `…policy.ReportedData` |
| the execution resources are accepted by identity and refused when not | `…policy.DeviceNodes`, `…policy.DevicesSection` (real shell and `stat`) |
| the host's table is read before and after, whole, or not at all; the report records it | `…policy.HostTable`, `…policy.ReportedData` |
| the real guest's reports are judged again as they were (accepted and refused) | `…policy.RecordedGuest` |
| the exact environment handed to the probe and to `bwrap --version`; the report's `locale`; `os.environ` and the session's environment untouched | `test_v21_r3_conf_locale.PassedDown`, `…AtTheExecBoundary`, `…RecordedGuest` |
| rows carry what the policy decides from | `test_v21_kills3_T07a.MountInfo`, `test_v21_kills3_T05b` |

## 8. Real, simulated, neither

Also run for real in the guest at the committed code: `validation/v21/sandbox/measure.py` (the 2.1 boundary harness) with
`NETWORK=host` and `NETWORK=none`, profile X1: the kernel's own measurement `problems: []` in both, `locale` `{LANG: C,
LC_ALL: C}`, 13 writable mounts (the root, `/proc`, `/dev`, the six device nodes, `/dev/pts`, `/tmp`, HOME, the
workspace); and the confinement test modules (`test_v21_r3_conf_policy`, `…_locale`, T05a/b/c, T06a, T07a, A06, defects,
`test_v21_confine`: 167 tests) with the profile `hardened`: `Ran 167 tests in 20.9 s, OK (skipped=1)`, the skip being
an existing one (`test_a_mount_that_only_shares_its_prefix_is_still_beyond`: the guest's temp directory lies below
`/tmp`).

| Evidence | Class |
|---|---|
| `scenarios-X1.json`, `scenarios-X1-shared-tree.json`: the session's command line and eleven variants, real bubblewrap 0.12.0, real probe, the container's real `/proc/self/mountinfo` as the host table, in the Linux guest (`validation/v21/sandbox/r3_conf_guest.py scenarios`) | **real run in the guest** |
| `locale-X1.json`: `confine.measure` with the real bubblewrap behind a wrapper that saves its `env` | **real run in the guest** |
| `scenarios-X1-shared-tree.json` runs the same inside `unshare --user --map-root-user --mount` after `mount --make-rshared /`: a mount tree with peer groups, as on a systemd host | **real run in the guest, in a namespace of the container that imitates a systemd host's propagation** (not a systemd host) |
| `SandboxMade`, `HostBacked`, `NotEstablished`, `DeviceNodes`: rows read by `confine._mounts` from lines copied from the guest, or built with `v21_r3_conf_rows.mount`; `_judge` is real | **unit** (no run); `shared:N`/`master:N` of the host's group, a missing field and an unreadable table cannot be produced by bubblewrap: **simulated** |
| `ReportedData`: `confine.measure` with the probe's call answered by a transcript | **simulated** (the probe's text is the guest-checked shape) |
| `DevicesSection`: the probe's own shell text run by `/bin/sh` and `stat` on the test's host against a table of the test's | **real shell, simulated table** |
| `PassedDown`: `subprocess.run` is a recorder | **simulated** |
| `AtTheExecBoundary`: a stand-in executable saves its environment | **simulated bubblewrap, real exec** |
| a translated message under a non-C locale; a bare-metal host's `devtmpfs` `/dev`; macOS or Windows (no backend) | **neither — not measured** |

## 9. Existing tests changed (rule 5)

Every one is a fixture or an exact row comparison made necessary by the owner's policy (files: `test_v21_confine`,
`test_v21_defects_confine`, `test_v21_kills3_A06`, `…_T05a`, `…_T05b`, `…_T06a`, `…_T07a`; `report.json`
`existing_tests_changed` names each test and the sentence): a hand-built or transcribed `tmpfs`/`proc`/`devpts` row with no source or super block, and no host table,
can no longer be accepted ("trường hợp không xác định được phải từ chối"). The assertions are not weakened: the
rows' equality now includes the new fields; `RecordedLinuxMeasurements` of the four 2.1 records (which predate the policy and hold no
host table) now asserts the one problem the judge must give them — that each writable mount is not established, and
nothing else.

## 10. Mutants (`validation/v21/kill_check.py`, the runner's bracket)

Over every mutant of each changed or new name, with the files of §7 and the confinement kill set (the order of the
kill files: the new ones first). Source `aisef2/app/confine.py` sha256 `375489e7…`.

| Name | Mutants | Killed | Survived | Of which |
|---|---|---|---|---|
| `_owned` (new) | 107 | 107 | 0 | |
| `_writes` (new) | 18 | 18 | 0 | |
| `_host_mounts` (new) | 16 | 16 | 0 | |
| `_device_roots` (new) | 6 | 6 | 0 | |
| `PSEUDO`, `DEVICES`, `LOCALE`, `_DEV`, `_PEER` (new) | 4, 12, 4, 1, 1 | all | 0 | |
| `_mounts` | 44 | 44 | 0 | |
| `measure` | 60 | 59 | 1 | `L315 string '/' emptied` — EQUIVALENT (old audit `measure` 51) |
| `_probe` | 215 | 212 | 3 | `'sleep '` AUDITED (old 110), `': '` AUDITED (old 167), `'.git'` EQUIVALENT (old 175) |
| `_judge` | 175 | 168 | 7 | `'/nonexistent'` AUDITED (old 92), `rc in (None, 127)` element 0 AUDITED (old 97), the workspace defaults ×4 EQUIVALENT (old 125, 126, 128, 129), `')'` AUDITED (old 132) |

The 11 survivors (1 + 3 + 7) are the old campaign's, each with its audit in
`closure-evidence/v2/v2.1/mutation/SURVIVOR-AUDITS.json` (indices there are the old ones); this work package changed no
line they stand on. The four mutants the owner named (`_judge` 142, 143, 157, 158) and the two of `measure` (40, 49) are
not in the new code. Three of the first batch's results were not final: two survivors of `_host_mounts` (`encoding`
and `errors` of the read: a test that mocked `read_text` with a mock that accepts anything), and four `LOCALE` and one
`_probe` mutant the bracket could not confirm (INFRA: a subtest label held a process id, so the same failure had two
signatures). The tests were changed (a `read_text` that decodes with what it is given, a mount point that is not UTF-8;
a label by index) and those mutants — with the ones the changed classes had killed — run again: all killed.

## 11. Not established, residual risks, decisions needed

* **A super block of another mount namespace** (another session's tmpfs, reached through `/proc/<pid>/root` in a `--bind`)
  is not the host's and is not excluded by observation. `wrap` binds only the workspace read-write, so no command line
  it builds can do it; a different wrapper could. Not established; no rule is added (§5.4).
* **Covered mounts**: two rows at one path are judged by what the probe sees at the path.
* **The host table is the controller's own**: in a container, the container's. A host of another mount namespace than
  the controller's is outside what a session's binds can come from.
* **A translated message** is not measured (the guest has C, C.utf8 and POSIX only); the C locale is chosen so it need
  not be. What would show it: an image with `de_DE.UTF-8` generated and util-linux's catalogue installed under `/usr`,
  the `unshare --user true` probe under `LC_ALL=de_DE.UTF-8` (the text no longer matches `USERNS_REFUSED`) and under C.
* **A bare-metal host** (devtmpfs `/dev`, systemd's shared tree) is not measured; the shared tree is imitated in a
  namespace of the container.
* **`rep.host_mounts` is in `RUN.json`**: trimmed to four fields per mount; for a host with hundreds of mounts that is
  tens of kilobytes. Decision for the lead if it should be elided from `RUN.json` and kept in the measurement's own
  evidence only.
