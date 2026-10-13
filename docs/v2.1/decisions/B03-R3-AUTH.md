# B-03 round 3, WP auth: the host table the mutation runner proves ownership from is not forgeable by a command line

Branch `v21r3/auth`, from the integration head `v21r3/integ` (643a6e0). Product file: `validation/v2/cleanup_authority.py`
(nothing under `aisef2/` changed). Evidence files are named relative to `$R3/out/auth/`.

## 1. The finding and the decision

INV-MUTATION-AUTHORITY (owner, 2026-09-24): *"Mutation, fault injection, test failure, probe result, or
implementation-under-test output MUST NOT expand host-side destructive authority."* A command line is implementation
output. `cleanup_authority._read()` is the root of every ownership proof of the runner (`host_table`, `owned`,
`strays`, `prove_member`, `signal_owned`, `establish`, `harness_orphans`). It split `ps` text with
`str.splitlines()` and **skipped** every line that was no row ("a continuation line of a multi-line command is no
row"). The lead's brief (FU-AUTH) asked for: read bytes, split at LF only, a strict row pattern, a typed fail-closed
error for a line that is no row, the same for the sibling readers, tests through the module's seams, and mutant evidence.
All of that is done; where my reading differs from the brief it is said in section 3.

## 2. Reproduced first (real, this host, read-only: `dry_run=True`, nothing signalled)

`repro-forged-row.py.txt` (children end by themselves when their stdin is closed; a victim is started, the boundary
is established 2.2 s later, then a carrier whose command line is `carrier<SEP><victim> <runner> <victim> <date in 2099> fabricated`).
macOS 26.5.2, `LC_ALL=en_US.UTF-8`, Python 3.14.7, the integration head:

| separator in the carrier's command | before (`repro-before.json`) | after (`repro-after.json`) |
|---|---|---|
| U+2028, U+2029 | **victim `signalled`**; the victim's row in the table is the forged one (parent = runner, born 2099) | not signalled; the victim's row is the real one; the carrier's command is whole |
| U+0085, VT, FF, FS, GS, RS, CR, LF, NBSP | not signalled (this `ps` escapes them: `M^E`, `^K`, ... `\012`, or prints NBSP raw) | not signalled |
| `carriers` (`ps -E`): a variable `A_FIRST=x<U+2028>y` before the token | **carrier not found** (the line was cut inside the environment) | found |
| `cwd_under` (`lsof -Fpn`): a cwd named `a<U+2028>b` | **not found** (the path was cut) | found |

The original finding script of WP range-fu gives, before: `signalled: [(95279, "fabricated-by-a-command-line'")]`; after
(`repro-original-after.txt`): `signalled: []`, `unproven: born before the boundary or not a descendant of the runner`.
The same matrix in the Linux guest (`repro-before-guest.json`, `repro-after-guest.json`) is **negative before and
after**: the guest's procps prints every one of these characters as `?` or `.` and LF as a space (measured, all three
locales the guest has), so there was nothing to forge there. The hazard is the BSD `ps` (macOS) in a UTF-8 locale.

## 3. Design, and where the code differed from the brief

**What `ps` prints, measured** (not assumed): macOS escapes LF (`\012`) and CR (`^M`) (VT, FF, FS, GS, RS and U+0085 by WP range-fu's measurement); it
prints U+2028, U+2029, NBSP and U+3000 raw (UTF-8 locale). Its `lstart` column is padded with **five** spaces before the
command (procps: one), the day is space-padded (`Oct  6`), and **`lstart` is printed in the locale's own words**
(`LC_ALL=de_DE.UTF-8`: `Di. 13 Okt. 08:03:59 2026`; ja_JP, fr_FR alike). `ps -E` escapes LF in an environment string and
prints U+2028 raw. `lsof -F` escapes LF and CR in a name (`\n`, `\r`) and prints U+2028 raw; `-F0` ends each field at
NUL and each set at LF (its man page: NUL cannot be in a path).

**The rule, for every reader**: bytes; a line ends at LF and nowhere else; each line is decoded with replacement and
is a row of the tool's documented column format or the whole reading is refused with `TableUnreadable`.

* `_read` (`ps -A -o pid=,ppid=,pgid=,lstart=,command=`): `_PS_ROW` = ASCII digits ×3 (`[0-9]`, not `\d` or
  `str.isdigit`, which accept `²` and Arabic-Indic digits), `lstart` = `Www Mmm +dd HH:MM:SS yyyy`, then ASCII spaces and
  the command **as printed**. Only ASCII spaces are separators: the old `split(None, 8)` also ate the Unicode whitespace
  at the start of a command (NBSP, U+3000, U+2028...). The date must also be a date (`time.strptime`, then `mktime`:
  `Feb 31` and a year `mktime` cannot hold are refusals, not an `OverflowError` out of the reader). A pid listed twice is
  refused: a made-up row for a pid that is also listed cannot be told from a real one by its shape, and a process is
  listed once. A failed `ps` is refused **without reading its text**; a table that does not list its reader is refused (as
  before). No partial table is ever returned.
* `_ps_env`: `ps` runs with `LC_TIME=C`. Measured on this host: de/ja/fr locales made *every* row unparsable and the old
  code said `ps -A exited 0 and did not list itself` (`real-ps-rows-host-before.json`); with the pin all five locales read
  the whole table (`real-ps-rows-host-after.json`). `LC_ALL` would override it, so its value is handed to `LC_CTYPE`
  (the category that decides how a command's bytes are printed). I did not pin `LC_ALL=C`: that changes how non-ASCII
  is printed, and `strays` matches the work tree by substring (not measured, so not risked).
* `_windows_table`: **base64 instead of the brief's `-replace`.** The script prints the command line as
  `[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$_.CommandLine))`; a row is
  `pid|ppid|seconds|base64`. Reasons: (a) the grammar is closed: the output is ASCII, one row per line, so no character
  of a command can end a row or begin another, whatever the script's `-replace` would have missed; a raw CR/LF reaching
  Python (a wrong script) is a line that is no row and is refused; (b) the exact command survives (the old reading
  decoded the console's OEM code page as UTF-8 with replacement); (c) it needs no judgement about what to replace a CR
  with. Python splits at LF after turning the CR LF terminators into LF, so a lone CR stays data. **Not run.** A
  PowerShell that cannot start or times out still returns `({}, -1)` (nothing provable), as before.
* `carriers` (`ps -E -ww -A -o pid=,command=`, macOS): `_PS_ENV_ROW` = digits, then the command and the environment
  as printed; non-row line, pid twice, failed `ps`, reader not listed: `TableUnreadable`. The Linux branch
  (`/proc/<pid>/environ`, NUL split) was not changed.
* `cwd_under` (macOS): `lsof ... -F0pn`, parsed by NUL into `p<digits>`, `f...`, `n...` fields (the LF after a NUL is
  the set terminator); output that stops inside a field, a field of another letter, a `p` that is not digits, an `n`
  before any `p` are `TableUnreadable`; "does not list this process" stays a refusal, now typed. The Linux branch
  (`readlink /proc/<pid>/cwd`) was not changed.

**The error class**: `TableUnreadable(OSError)`, also raised for the two conditions that were a plain `OSError`
(failed tool, reader not listed). Every caller already stops on `OSError` as "the table cannot be read":
`mutation.py:1330/1356` (`_clean`, `_settle`: `except OSError`) -> `_Stop("HOST_TABLE_UNREADABLE")`; `:2048` (`_earlier`, before the first
target) -> `STOPPED ... HOST_TABLE_UNREADABLE`, exit 3; `:1816` (`establish`, inside the target's `try`) -> `_Stop
RUNNER_EXCEPTION`, no mutant run. A `ValueError` or a new unrelated type would have been the old defect
(`RUNNER_EXCEPTION` out of the reader, batch T23a) or an uncaught traceback (VS-4). The one `except (OSError,
RangeError)` that "goes on" (`mutation.py:1545`) wraps `ProcessRange.start()`, which never calls this module.

**Callers** (every one of `host_table`, `_read`, `establish`, `carriers`, `cwd_under`, `strays`, `signal_*`):

| file:line | what it does with `TableUnreadable` |
|---|---|
| `validation/v2/mutation.py:1317` `_watch` | not caught here; called by `_clean` (in its `try`) and `_earlier` (caught by its caller) |
| `:1328` `_clean` (`signal_owned`, `_watch`) | `except OSError` (`:1330`) -> `_Stop("HOST_TABLE_UNREADABLE: ...")` |
| `:1342-1344` `_leftovers` (`strays`, `carriers`, `cwd_under`) | inside `_settle`'s `try` at `:1354`: `except OSError` -> `_Stop("HOST_TABLE_UNREADABLE")` |
| `:1375-1378` `_earlier` | its caller `:2047-2050`: `except OSError` -> "STOPPED before the first target", exit 3 |
| `:1816` `establish(scratch)` | inside the target's `try`/`except Exception` -> `_Stop("RUNNER_EXCEPTION: TableUnreadable(...)")`; no mutant runs (an `OSError` read the same before) |
| `validation/v21/read_set.py:367`, `validation/v2/checker_calibration.py:261`, `validation/qualification/q3.py:409,412`, `validation/v21/sandbox/linux_guest.py:160,170,320,336` | not caught: the tool or the check fails loudly (before: the same for an `OSError`) |
| tests: `p4/test_mutation_safety.py`, `p4/test_process_range.py`, `test_v21_confine.py`, `test_v21_read_set.py`, `test_v21_snapshot_delta.py`, `test_v21_mutation_runner.py:564-593` | pass a `table=`, or read the real host; `assertRaises(OSError, ...)` still holds (subclass) |

**Alternatives rejected.** (1) *Keep skipping, but join a continuation line to the previous row*: a forged row is
exactly a line that looks like a row; it cannot be told from a real one, and a skip is "a process the table cannot see".
(2) *A separator-safe `ps` output*: macOS `ps` has no NUL-terminated mode. (3) *A second source (sysctl via ctypes)*:
heavier than the finding needs; the residual in section 8 is for a `ps` nobody measured. (4) *`-Fpn` and LF for `lsof`*
(it escapes LF here): `-F0` is the documented terminator no path holds, and costs one `split`. (5) *Skip instead of refuse
in `carriers`/`cwd_under`* (they only yield candidates): a candidate lost silently is a leftover never cleaned while the
runner reports "no stray left"; refusing stops the target, which is the runner's own rule for an unreadable table.

## 4. Requirement -> test

| requirement | test (file: class.test) |
|---|---|
| a row ends at LF only; the command is whatever `ps` printed, separators included | `ps_table`: `RowIsALine.test_a_command_holding_a_separator_is_one_row_with_the_whole_command`, `..._the_separator_ends_nothing_even_at_the_end_or_the_start_...`, `..._a_carriage_return_is_data_never_a_line_end` |
| a command starting with a Unicode space keeps it | `RowIsALine.test_a_command_that_starts_with_a_unicode_space_keeps_it` |
| columns: five-field `lstart`, space-padded day, 5- and 1-space padding, empty command, invalid UTF-8, blank lines | `RowIsALine.*` (the other six) |
| a line that is no row (19 shapes, three positions), a date that is no date, a clock that overflows | `NotARow.test_every_line_that_is_no_row_...`, `..._a_date_the_clock_cannot_hold_...`, `..._the_error_names_the_line_cut_to_eighty_characters` |
| a pid listed twice; a failed `ps`; no reader; the class is an `OSError`, not a `ValueError` | `NotARow.test_a_pid_listed_twice_...`, `..._a_failed_ps_is_never_...`, `..._the_failure_says_which_...`, `..._the_error_is_an_oserror_...`, `..._establish_and_host_table_refuse_alike` |
| `ps` runs with LC_TIME=C; LC_ALL moves to LC_CTYPE; this process's environment is untouched | `PsRunsInTheCLocaleForItsDates.*` (4), real: `TheRealPs.test_a_locale_that_words_its_dates_is_still_a_table` |
| **a process born before the boundary is never in `owned`/`prove_member`/the signalled list, however the command lines are arranged** (13 separators, forgery at either end, a forged row for the reader and for a pid that is not there) | `ACommandLineIsNeverAuthority.*` (5) |
| the same through the real `ps` and real children | `TheRealPs.test_a_real_command_line_with_separators_and_a_row_forges_nothing` |
| Windows: any command is one row with its exact command; a non-row, a bad base64, a pid twice, a raw-command script are refused; a shell that cannot run proves nothing; the proofs hold over a Windows table; the script encodes the command | `other_readers`: `WindowsTable.*` (9) |
| `carriers`: a token after a separator is found; row-shaped environment text makes no candidate; refusals | `Carriers.*` (8), `CarriersOnLinux.*` (2), real: `TheRealHost.test_a_token_after_...` |
| `cwd_under`: a path with a separator is one field; field-shaped path text makes no process; refusals; the argv; the Linux branch | `CwdUnder.*` (11), `CwdUnderOnLinux.*` (2), real: `TheRealHost.test_a_process_working_in_a_directory_with_a_separator_...` |

**Wrong implementations tried** (`wrong_impls.py.txt`, one edit each of the fixed module; the file must fail, and does,
`wrong-impls-ps-table.txt`): `str.splitlines()` of the decoded text (the old bug), `bytes.splitlines()` (cuts at CR),
skipping a non-row, skipping a bad date, the later row of a pid wins, `lstrip()` of the command, `ps` in the user's locale,
reading a failed `ps`, a reader that need not list itself, `\d` for the digits. All ten fail.

## 5. Real, simulated, neither

* **Real, macOS 26.5.2 host**: the reproduction (section 2); every row of the real `ps` parses (`real-ps-rows-host-after.json`:
  713 rows, 712 in an independent `ps -A` call taken just before (processes come and go); 40 commands equal `ps -p PID -o command=`; the five
  locales); `ps -E`, `lsof -F0pn` formats; `TheRealPs`, `TheRealHost` (real children, real tools).
* **Real, Linux guest** (`$R3/guest.sh`, Debian procps copied into the image, Linux 7.0.12-linuxkit aarch64, Python
  3.14.8): the separator probe (`probe_ps.py.txt`: C, C.utf8, POSIX); `many_rows.py.txt` (`guest-many-rows.json`: 60 children
  with separators, a 3000-character argument and non-UTF-8 bytes + the 3 system processes = 63 rows, the independent call
  63, 60/60 commands equal `ps -p`); `linux_guest.py` roles a, b, c, d1 and the modules, on the archive of
  `ee51eda` (`guest-run/`): roles exit 0 with the same pattern as the recorded 2026-10-08 evidence (the runner's own
  child proved, the canaries unproven and alive, nothing outside signalled); `test_v21_confine` 34 OK,
  `p4/test_process_range` 24 OK, `test_v21_defects_runner` 3 OK, both new files 30 + 34 OK,
  `test_destructive_authority` 13 OK. **One guest failure, not mine**: `p4/test_mutation_safety`
  `test_MUT_SAFE_6` asserts "the host has more than 50 processes" and the container has 2; the same test fails
  identically at the integration head in the guest (`guest-integ-mutation-safety.err`).
  **One finding from the guest**: my first test used year 0001 for "a clock that cannot hold the year"; glibc's `mktime`
  holds it, macOS's raises. The refusal is now exercised by making `mktime` raise (commit `ee51eda`).
* **Simulation**: the hermetic tests (a `Popen`/`run` that returns the bytes a tool printed); everything about
  Windows; the Linux branches of `carriers`/`cwd_under` when run on macOS (a fake `/proc`); the locale refusal on Linux.
* **Neither**: the PowerShell script on a real Windows; any `ps` other than macOS 26.5.2's and the guest's procps;
  procps under a locale other than C/C.utf8/POSIX (the guest has no others).

## 6. Mutants (`validation/v21/kill_check.py`, T0 PASS for both files)

Every mutant of every function I changed or added, with `tests/v2/test_v21_r3_auth_ps_table.py` and
`tests/v2/test_v21_r3_auth_other_readers.py` (`kc-<function>.json`): **12 functions, 222 mutants, 222 KILLED, 0
SURVIVED.** Survivors of my first runs were all strings an operator reads or a contract with the tool (`ps` message
prefixes, the `lsof` argv, the Linux-branch `/proc/` paths, `OverflowError` in the `except`); each was killed by a test
added for it, none was dispositioned as equivalent or audited.

| function | mutants | killed | killed by |
|---|---|---|---|
| `_lines` 4, `_not_a_row` 2, `_twice` 3, `_ps_env` 8, `_ps_rows` 25 | 42 | 42 | `ps_table` |
| `_read` | 23 | 23 | `ps_table` 22, `other_readers` 1 (the Windows branch) |
| `_win_rows` 15, `_windows_table` 20, `_env_rows` 8, `_lsof_cwds` 27 | 70 | 70 | `other_readers` |
| `carriers` 39, `cwd_under` 48 | 87 | 87 | `other_readers` |

`validation/v2/cleanup_authority.py` is **not** a registered mutation target (`grep` in `mutation.py`: only the import),
so there is no registered kill set to add to; the files above are the kill files to register if the lead wants it.
`TableUnreadable` has no logic; `establish`, `host_table` changed in docstrings only.

## 7. Existing test changed (one)

`tests/v2/test_v21_defects_runner.py`: (a) `FakePs.communicate` returns the **bytes** `ps` printed (what a binary-mode
`Popen` returns; the module no longer reads text); (b) `ContinuationLines.test_a_continuation_line_that_reads_as_a_date_is_no_row`
-> `..._refuses_the_reading_with_a_typed_error`: three non-row lines were skipped and the table was `[100, 31337]`; now each
of them, alone and together, is a `TableUnreadable` that is an `OSError` and not a `ValueError` (the original defect was
the `ValueError`). Required by the brief: "a non-blank line that is not a row [is] a typed fail-closed error" and by
INV-MUTATION-AUTHORITY ("a skipped line is a process the table cannot see"). The other two tests are unchanged.

## 8. Not established / residual

* **A `ps` that prints a raw LF inside a command** is the one way left to put a row-shaped line into the table: by
  shape it cannot be told from a real row. None was measured (macOS: `\012`; procps: a space). What is closed for it is
  the case where the forged pid is also listed (refused as a pid listed twice); a forged row for a pid that is not
  listed (and might be reused) is not caught. Closing it needs a second source (sysctl/`/proc`), which I did not build.
* **Windows is not run.** The script, the base64 decode and the strictness were tested against the format only. If the
  script is wrong the failure is an empty or refused table: no authority is expanded, but the Windows path may be
  unusable until it is run once on a real Windows (PowerShell 5.1 and 7).
* The pin `LC_TIME=C` is measured on macOS only; for glibc `ps` it follows from `strftime`, not from a measurement.
* The `lstart` of a process, and so every birth, is still a whole second in local time (unchanged); the 0.5 s slack
  and the boundary rule are untouched.
* `mutation.py:1816` reports an unreadable table at `establish` as `RUNNER_EXCEPTION`, not `HOST_TABLE_UNREADABLE`
  (unchanged behaviour; the file is not mine).
* Sealed records, K-NOWORK, Q0 and the calibration record are stale after any product change; in this tree
  `p0/test_checker_calibration` (4 failures) and `test_v21_mutation_runner.Classify.test_historical_records_read_as_before`
  (1) fail on `process_range.py` targets "changed since the mutation run", i.e. from WP range-fu, not from this file.
