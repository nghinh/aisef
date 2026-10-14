# B-03 round 3 — the owner's decisions of 2026-10-12 on the nine open mutants: what was decided, done, verified, and not

Status: **written before the re-measurement it names** (the numbers of the measurement are in `closure-evidence/v2/v2.1/`
and in `docs/v2.1/REPORT.md` §0 once it is done). This file is the index; each decision has its own document.

Rule of the round (owner): the aim is the right behaviour and the evidence for it; the mutation record turning PASS is
never a reason to choose a requirement. Nothing was pushed, tagged or published; no paid provider was called; Docker
Desktop and the containers `goe-postgres-1` / `goe-valkey-1` were not touched.

## 1. The nine mutants, as they stood at `3dc827b` (module digests at that commit)

| # | id = `target#index @ module-sha12` | source line | what the mutant changes | requirement | owner decision applied | verified by |
|---|---|---|---|---|---|---|
| 1–4 | `aisef2/app/confine.py::_judge#142 / #143 / #157 / #158` `@048485811e26` | `confine.py:409` | element 2 / 3 dropped, `'devpts'` / `'mqueue'` emptied in `("tmpfs","proc","devpts","mqueue")` — what a writable mount outside the workspace may be | a session writes the workspace and nothing else of the host | **provenance, not name or place**: a rw mount outside the workspace is accepted only when shown to belong to the sandbox (type, source, super block not the host's, peer groups, namespaces) or to be one of six explicitly allowed device nodes; anything not established is refused (B03-R3-conf.md) | the old clause and its mutants are gone; 118 mutants of `_owned` and the other new names killed by tests of both the allowed and the escaping cases; real bubblewrap 0.12.0 in the Linux guest (12 command lines, the old clause accepted all 12 and 9 are write paths) |
| 5–6 | `aisef2/app/confine.py::measure#40 / #49` `@048485811e26` | `confine.py:255` | element 3 dropped / `'LANG'` emptied in the passed-through environment keys | the evidence-collecting subprocess has a stable locale | **locale C for the measurement subprocess**, recorded in `rep["locale"]`; the session's and the user's locales untouched | exact environment checked at the exec boundary (simulation) and with the real bubblewrap (guest); a translated message was NOT measured (the guest has only C/POSIX) |
| 7–8 | `aisef2/app/usage.py::no_progress#13 / #23` `@d037098c55ba` | `usage.py:130` | `story/commit` no longer closes an attempt (element dropped / string emptied) | "consecutive failed attempts with the same failures" | **domain = every journal the projections admit**, a committed attempt is progress and is never reported; journals the projections refuse are refused by `--verify` at a named boundary (B03-R3-usage.md) | the old function is gone (13/23 dissolved, not counted as killed); the new function's mutants killed by behaviour; boundary run over 89 format-3 journals + the 2.0.0 smoke journal: 0 false refusals |
| 9 | `aisef2/app/review_verify.py::detail#22` `@a9aa9f55306f` | `review_verify.py:257` | `sort_keys=True` → `False` | the journaled statement of a finding | **the 1,500-character bound is on the statement only**; the full redacted reproducer is a create-only artifact named by the row and listed in the evidence manifest; no artifact ⇒ no block (B03-R3-detail.md) | 12,000 adversarial findings (longest statement 1,492); a decisive field after character 1,500; secrets (string, number, straddling the cut); real runs |

Also decided in the same message and done: `ProcessRange.release()` under concurrent callers is fixed (B03-R3-range.md);
a real `aisef run` in the Linux guest (B03-R3-E2E.md); OCR identity; the probe-module findings classified
(B03-R3-PROBE-MODULE-FINDINGS.md); the three probe files in site-packages (exact paths and provenance; **not removed**).

## 2. Defects the verification found, beyond the nine (each fixed with a test of the requirement, kept separate)

| defect | where | how found | kept in |
|---|---|---|---|
| the host's own `/dev/pts`, `/dev/mqueue`, `/dev`, `/dev/shm`, `/proc` were accepted as "writable outside the workspace is fine" | `confine._judge` | real bubblewrap, 12 variants | B03-R3-conf.md |
| a spurious, rare refusal: a super block freed at the session's end reused by an unrelated host mount before the second reading | `confine._probe` | review of conf | B03-R3-conf.md §13 |
| `--verify` printed VERIFIED / delivery PASS for a chained, schema-valid journal whose story committed twice | `verify.verify` | usage WP | B03-R3-usage.md |
| two finding ids that read alike made one artifact file name and the review of the second story was refused on every attempt; the finder's own work files kept the secret verbatim; a secret of digits written as a JSON number stayed in the statement | `review_verify.preserve`, `Reviewer._ocr`, `redacted` | review of detail | B03-R3-detail.md |
| `ProcessRange._ps_table`: `str.splitlines()` cut a `ps` row at U+2028/U+2029 — a raise, a silently cut command, or a made-up process | `process_range._ps_table` | review of detail, conf-fu, range-fu | B03-R3-range.md §11 |
| the same on Linux: a process named with bytes that are not UTF-8 made the whole table raise | `process_range._linux_table` | range-fu, real in the guest | B03-R3-range.md §11 |
| **the mutation runner's own ownership root** accepted a command line that forged a row: a process born before the boundary was classified *signalled* (dry run) | `cleanup_authority._read` | range-fu | B03-R3-AUTH.md |
| a session-stream event holding U+2028/U+2029/U+0085 was cut and dropped silently (the model reviewer's findings, a usage step) | `client.read_session`, `usage.session_tokens`, `confine._sections/_mounts/_host_mounts`, `lineage.reconcile` | range-fu, client WP | B03-R3-CLIENT.md |
