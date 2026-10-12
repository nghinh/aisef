# Linux guest checks at the round-2 head (2026-10-12)

`validation/v21/sandbox/linux_guest.sh` (campaign-3's tool, unchanged apart from the survivors set it already carried) at
the commit in `COMMIT.txt`, in Docker Desktop's Linux VM (kernel 7.0.12-linuxkit, arm64, Debian trixie image
`aisef-sandbox-measure`, Python 3.14.8, bubblewrap 0.12.0, uid 1000, no capabilities, no network, one container at a
time, tree mounted read-only). Docker was started after campaign 4 finished (owner point 6: Linux verification after the
load-sensitive measurements). Other containers present in the VM (`postgres`, `valkey`) are the operator's own and were
not touched.

| check | result |
|---|---|
| `a`, `b`, `c` (boundary, release, session owner), `d1` (host view) | each `exit 0`; `foreign: {}` (no process the checks did not start was signalled); see `a.out` ... `d1.out`, `commands.txt` |
| `tests.v2.test_v21_confine` | 34 tests OK (14.5 s) |
| `tests.v2.p4.test_process_range` | 24 tests OK (17.9 s) |
| round-1 survivor tests + confine defect tests + TO2 (`d-test_v21_confine_survivors`) | 114 tests OK, 1 skipped (1.0 s) |

**What this does not cover.** The round-2 kill files (R01-R07) and `test_v21_defects_lineage2.py` are not in the guest's
list (they do not need Linux semantics; the lineage permission tests are POSIX-only behind `skipUnless`, and ran on
macOS). The `LANG` question of `confine.measure` (ROUND-2.md, Q-LANG): the measure image holds only the locales
`C`, `C.utf8` and `POSIX`, no message catalogues (`/usr/share/locale` is empty, no `libc.mo`), and `os.strerror` is
identical under `LANG=de_DE.UTF-8` and `LANG=C` there. So on THIS image a non-English `LANG` cannot change the text of
the kernel's refusal and the possible false refusal is not reachable; on an image that does carry catalogues it remains
unmeasured. That is a statement about one image, not an answer to the owner's question.
