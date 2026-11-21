# Adversarial check of the legacy-platform reconstruction (327 runner-1 entries, UNRESOLVED at I6)

Read-only. I used `git show` / `git log` / `git cat-file`, stdlib parsing, and one interpreter probe (`hasattr(os, "waitid")`).
I also listed and parsed, read-only, the out-of-tree diagnostics folder that committed evidence names (see D-1).
Nothing was edited or committed, no test or engine was run, and the main checkout is untouched. Head is `1e25ef84`;
basis `v2.2.0` is `da3ea33f`. My scripts and traces are in `check/` next to this file (sha256 values at the end).
Paths below are tree-relative. The out-of-tree folder is called `<diag>/`, and no host or home path is reproduced.

## Verdict

**SOUND_WITH_NOTES.** The core result holds: **0 PROVEN, 327 UNPROVEN, 0 I6-admissible under the current engine.**
I found no row that the current §2.4.3 rules (R-family, R-flavor, W) would make PROVEN, INVALIDATED or
contradictory. Every mechanical field I re-derived agrees, for all 327 rows: the set, the entry digest, mutants, the
intro commit, the runner fingerprint and the comment flag.

The disagreements are in the *leads* and in the *"if the engine accepted"* section:
* an optimistic D2 aggregate;
* a contradiction rule the report proposes but does not apply to its own pointers;
* hints labelled posix/darwin with no contemporaneous basis;
* one input it missed, which holds a **run-bound** reconstruction for 49 rows. That input is out of tree and
  uncommitted, so it is still not proof.

## Disagreements (most important first)

### D-1 — MEDIUM — missing input: an out-of-tree, run-bound reconstruction exists for 49 rows (1,806 mutants)

**What the report claims.**
* Searched: "No cycle-1 or cycle-2 worker history was ever committed". This is true.
* Conclusion: "Tier D only covers 4 entries well … Anything wider is an owner ruling written up as evidence, not a
  reconstruction."

**What exists.** Committed evidence names an out-of-tree diagnostics folder:
* `ARCHITECTURE-EXCEPTION-V2-006.json` `/diagnostics`;
* "operator notes in the diagnostics folder".

That folder holds, for cycle-1 P5/P6 (2026-09-24/25):
* per-run launch scripts (`launch_T/U/V.sh`, `launch_W/X/X2/X4.sh`, `launch_P6.sh`), each with an explicit run→target
  list (heredoc or `v3-targets-<run>.txt`);
* per-run output records (`<run>-P<n>-MUTATION.json`);
* per-run logs (`mut_v3<run>.log`).

**Measured** (`check/c10.py`, output `check/ootree_bound.json`). An entry is counted only if its target is in that
run's own target list AND that run's own record holds a canonical-JSON-identical entry, using the engine's
`canonical()`. 49 of the 327 are bound this way, each to exactly one run:

| run | intro | rows | mutants | targets |
|---|---|--:|--:|---|
| P6 | `116b92a3` | 14 | 606 | `validation/v2/gen_migration_table.py` ×14 |
| V1, V2 | `0f453968` | 9 | 194 | `aisef2/quality/adequacy.py` ×9 |
| W1, W2, X1, X3 | `beeb5b68` | 26 | 1,006 | P1 `routing.py` ×3, P2 `story_admission.py` ×4, P4 `story_scope.py` ×8, P5 `evidence.py` ×2, `except_boundaries.py` ×9 |

**Why these are host-bound.** Every launch script of these runs carries darwin R-flavor path tokens, the same token
classes as §2.4.3:
* it does `cd` into a checkout under `/Users/<u>/`;
* its worker trees are under `/private/tmp/…`;
* it excludes `.DS_Store`.

**Why it is still not proof.**
* None of it is committed.
* No committed record pins a launch script, a log or a worker-only record by sha256. The pins I found
  (`P4-FINAL-SEAL.json`, `P5-FINAL-SEAL.json`) are of record bytes that equal committed record versions.
* The logs and records carry no R markers: 0 frames, 0 OS tokens (`check/c8.py`).
* §2.4.3 W needs committed `mutation-workers/*.history.json` at the basis (`workers_at(B.sha)`). So committing these
  files now would still not make them W evidence.

**Effect on the report.** These 49 rows are graded D3 ("session-level hints only"). Under the report's own definition
they hold a binding stronger than its D1, because the producing run is named with its target list.

**Caveat for any future tier.** Worker records also hold *inherited* entries, copied with the rsync'd tree: 131 of the
327 have canonical copies in some worker record, but only 49 are in that worker's own target list. Canonical identity
inside a worker record is therefore not a run binding. The run's own target list is required.

**Fix.**
* Add this input to "searched".
* Re-grade the 49 rows as a separate out-of-tree lead.
* State that admitting them needs an owner ruling plus digest-pinning, not an engine reading.

### D-2 — MEDIUM — optimistic: D2 is not homogeneous; "D1+D2 = 14 / 279 … honestly" overstates

All 10 D2 rows were re-derived (table below).

**Fixed-runner rows.** Only 2 rows carry the fixed-runner fingerprint (`killed_by_timeout` present):
* `protocol.py::Observation.__post_init__`, 61 mutants;
* `protocol.py::classify_failure`, 43 mutants.

That fingerprint is consistent with the live runs that F011 binds to the host: `P4-FINDING-011-SAFETY.json`
`/cleanup_authority_proof` and `/unrelated_process_signalled_after_fix`, and the manifest's P4-FINDING-011 status
"the live mutation runs (A3, B3, W, M, O) completed with the fixed runner".

**Pre-fix rows.** The other 8 rows carry `strays_reaped` but no `killed_by_timeout`:
* `protocol.py` ×5: `ProbeRecord.__post_init__`, `ProbeRegistry.observation_class`, `bound_result`, `comparability`,
  `run_probe` (88 mutants);
* `outcome.py` ×3 (53 mutants).

So they were produced by a runner of the `cfe14c03`..`224caa46` family. The report's lead pointers `F011_LIVE_RUNS` and
`F011_RUNS_MANIFEST` describe fixed-runner runs, so they do not apply to these 8. What is left is:
* commit prose ("local mutation re-run", "P1 18"), which §2.4.3 lists as "not evidence";
* the pre-fix incident run, a sibling that the report's own standard says "does not bind".

**Honest ceiling.** D1+D2 is at most **6 rows / 138 mutants** (4 D1 + the 2 fixed-runner rows). The other 8 rows
(141 mutants) belong with D3.

**Fix.** Split D2 by fingerprint and recompute the acceptance table.

### D-3 — MEDIUM — previously required control silently excluded: the contradiction rule is not applied to the report's own pointers

The report's proposal, item 4, says:
* "Linux / ubuntu … → posix·linux";
* "Contradiction keeps today's semantics: … both flavors, gives INVALIDATED (I6: contradictory)".

`legacy-platform.json` attaches `LINUX_CONTAINER` to every D1, D2 and default-D3 row (322 rows; all but C2-ORCH). The
pointer is P4-FINDING-004, "reproduced in a local Linux container on the exact tree". The same rows also carry darwin
pointers.

Under the rule as written, those rows are **INVALIDATED (contradictory)**, not "posix / darwin admissible" (D1, D2) or
"posix / flavor unproven" (D3). If counter-hints are meant to be outside the grammar, the asymmetry must be stated, and
it then fails on its own terms:
* `LOCAL_GATE_MACOS` ("WP-4.2 was gated locally on macOS only") is a suite-gate statement;
* `LINUX_CONTAINER` is a suite-reproduction statement;
* both are session-level, so they must count alike.

**Fix.** Compute the acceptance table under the rule the report proposes, or change the rule explicitly.

### D-4 — MEDIUM — optimistic: hard-coded hints; family "posix" from absence for 38 rows

**Hard-coded labels.** `build.py` line 159 hard-codes `family_hint: "posix"` and `flavor_hint: "darwin"` for all 327
rows. This contradicts the report's own text: D3 flavor "unproven (local Linux container)".

**Family from absence.** For 38 rows (1,124 mutants), nothing contemporaneous supports even the family:
* the rows are runner fingerprint `--`, intro commits `4afc9d10`, `ab2fc134`, `7c7f7dd8`, `f097ba16`, `5bff6ebb`,
  `c6b90530` and `88b9554a` (2026-09-21/22);
* their only pointers are `LOCAL_GATE_MACOS`, first committed at `844ffc9f` (2026-09-23 01:34), and `LINUX_CONTAINER`
  (2026-09-23);
* both pointers post-date the rows, and both are about suite runs.

The report itself says Windows is excluded only by the code comment or by "the absence of any local Windows host". For
these 38 rows there is no comment, so the "+D3 → 327 posix" row of the acceptance table infers their family from
absence.

**Fix.**
* For D3, print `flavor_hint: unproven`.
* For the 38, print `family_hint: unproven`, and leave them out of any family-assigning tier.

### D-5 — LOW — wrong row field: 24 rows flagged "older than the runner comment" were produced by a newer runner

Rows: `aisef2/journal/format2.py::*` ×24, intro `affae7da` (2026-09-22 22:15), 488 mutants.
* `runner_comment_present_at_intro` is `false` for all 24.
* Every one carries `strays_reaped`. The runner committed at `affae7da` never writes that key (0 occurrences).
* The key first appears in `mutation.py` at `cfe14c03`, 12 minutes later, in the same commit that adds the "run on CI,
  not on the developer machine" comment.
* All 32 P4 entries committed at `affae7da` carry the key, and the commit message says "the WP-4.1 targets of the full
  P4 run".

So these entries were measured by an **uncommitted** runner at least as new as `cfe14c03`'s, which most likely carried
the comment. The pre-comment group is 38 rows / 1,124 mutants by fingerprint, not 62 / 1,612.

This is also direct proof that the committed runner at an intro commit is not the producing runner. The flag must come
from the fingerprint bracket, not from the intro commit. The direction is pessimistic, but the field is wrong.

### D-6 — LOW — overstatement in the D2 evidence description

"Three committed records place the V2-003 P2/P4 mutation re-run 'A3/B3' on a macOS host" is wrong for one of the three.
* `P4-RUN-HISTORY.json` `/entries/60` (seq 61) is a **Linux CI row** (`unit (ubuntu-latest, 3.14)` at `2f7f93bc`). It
  says only that A3/B3 "was still running".
* The two records that do bind are `P4-FINDING-011-SAFETY.json` and the manifest's P4-FINDING-011 status.
* The manifest names five fixed-runner live runs, A3, B3, W, M and O. The report discusses only A3/B3.

**Measured, supporting the fingerprint method.** At `e137aa36`, exactly 9 P4 entries carry `killed_by_timeout`, which is
A3's "9 range targets". 10 P2 entries carry it: 2 `protocol.py` + 8 `python_callable.py`. So "B3 = 7 probe targets"
cannot be mapped to the 2 `protocol.py` rows; W, M or O could equally account for them.

### D-7 — LOW — incomplete search lists (results unchanged)

**Compressed records.** The W scan of "all 86 *.record.json" omits compressed records:
* `closure-evidence/v2/v2.1/campaign-2/results/c2-w{1..4}.record.json.xz`;
* `campaign-2/results/MUTATION.json.xz`.

I decompressed them with stdlib `lzma`: 0 canonical-identical entries and 0 of the 327 targets. Their mentions of 327
modules are traceback frames of other targets. Also, "86 versions" is 86 path×commit pairs (74 distinct blobs).

**Record version counts.** "C2-P10 4, C2-ORCH 3" are commit counts with `--full-history`. The distinct blobs are 1
and 2.

### D-8 — LOW — missing input: F5-PILOT-1 re-measured 2 of the 327

`docs/v2.3/evidence/F5-PILOT-1/compare.json` re-measured 2 of the 327:
* `aisef2/plan/drift.py::attribute` (P2, 15/15);
* `aisef2/journal/compat.py::reconstruct` (P3, 25/25).

The pilot host is macOS 26.5.2, CPython 3.14.7 (`PILOT-1.json` `/host`), with the same mutant list and 0 outcome
differences. This is not evidence for the legacy bytes' platform: they are different bytes, measured after the basis.
It is relevant to the cost of re-measuring the 327 and to the row commentary, and the report does not mention it.

### D-9 — LOW — kill-file gating claim has no trace and is too coarse

"Kill sets run on every OS (or mock the platform), so a killed mutant does not imply a family" has no supporting trace
in the folder.

**Counter-example.** `tests/v2/p4/test_process_range.py` at `65dc6435` has at least 5 `@skipUnless(POSIX)` tests. One of
them is the reaper test, which uses a real `os.waitid` in a subprocess. Whether any mutant is killable only by a
POSIX-only test cannot be decided read-only.

**Probe.** I checked the claim "macOS has no `os.waitid`" on this host. Homebrew CPython 3.14.7 has `os.waitid`;
3.12.14 does not. So the reaper kill set separates neither darwin from linux at 3.14 nor family from version.

The claim does not change any verdict. State it as unexamined.

### D-10 — LOW — a second POSIX-only runner window is not mentioned

P4-FINDING-005 is `process_range` evaluating `signal.SIGKILL` at import. It existed from `cfe14c03` and was fixed at
`844ffc9f` (`P4-RUN-HISTORY` seq 17). Runner-1 imports `ProcessRange` for every kill-test run, so in that window it could
not run on Windows. This is like the `a4136fba` window the report does cite.

As with `a4136fba`, no row's producing runner can be pinned into the window, so no row changes.

### D-11 — LOW — cosmetic and wording

* The report says "All 327 kill files are `tests/v2` modules". It means the 35 distinct kill files of the 327 entries.
  I verified all 35 are under `tests/v2/`.
* "25 pointers … each … + blob sha": 7 of them are commit-message pointers with `blob_sha256: null`. Each is bound by
  its commit id instead.
* The `F011_WORKTREE` token includes its JSON key, so it is not inside the value at its JSON pointer. It is correct at
  line level.

## Rows re-derived

### All 327 rows, mechanical fields

Every value was recomputed from primary sources.
* The set equals DISPOSITION-2's `UNRESOLVED` rows: 327, 10,078 mutants, all `I6 · no platform evidence`.
* The engine's `canonical()` (`validation/v23/impact.py:144`) applied to the HEAD record bytes gives every
  `entry_sha256`, 327/327. Mutants match, 327/327.
* The record bytes at HEAD equal `da3ea33f` for all 8 records.

**Intro commits** were re-derived by my own walk, `check/c2.py`. It walks topo order over `--full-history`, tracks
presence and absence per commit, and is a different method from the report's.
* 327/327 agree with the report.
* No final digest re-appears after a different or absent version.
* No entry is absent after its first presence.
* There are 24 intro commits, from 2026-09-21 to 2026-10-01.

**Fingerprint vs intro-commit runner** (`killed_by_timeout` / `strays_reaped` keys):
* 303 rows are consistent;
* the 24 `affae7da` rows carry a key their intro runner never writes (D-5).

### Sampled rows (42), including every row in the minority classes D1 (4), D2 (10) and C2-ORCH (5)

Column key:
* **fp**: `k` means `killed_by_timeout` is present, `s` means `strays_reaped` is present.
* **cmt@intro**: whether the runner comment is present at the intro commit.
* **report fields agree**: intro, mutants, both fingerprint keys and the comment flag all match `legacy-platform.json`.
* **my grade note** points to the disagreement that applies (D-n).

| target | record | mut | intro | date | fp | cmt@intro | report grade | report fields agree | my grade note |
|---|---|--:|---|---|---|---|---|---|---|
| range_anchor.py::_die | P4 | 3 | 65dc6435 | 09-26 | ks | yes | D1 | yes | D1 ok (target named by "the other three anchor targets", harness doc l.97-98) |
| range_anchor.py::_reap_adopted | P4 | 8 | 65dc6435 | 09-26 | ks | yes | D1 | yes | D1 ok |
| range_anchor.py::_subreaper | P4 | 5 | 65dc6435 | 09-26 | ks | yes | D1 | yes | D1 ok (kill test mocks `sys.platform`: no family signal) |
| range_anchor.py::main | P4 | 18 | 65dc6435 | 09-26 | ks | yes | D1 | yes | D1 ok (V2-006 `/anchor_watchdog/after/main` = 18/18, src 78e76c39…) |
| protocol.py::Observation.__post_init__ | P2 | 61 | e137aa36 | 09-23 | ks | yes | D2 | yes | D2 ok (fixed-runner fp) |
| protocol.py::ProbeRecord.__post_init__ | P2 | 14 | e137aa36 | 09-23 | -s | yes | D2 | yes | **D3** (D-2) |
| protocol.py::ProbeRegistry.observation_class | P2 | 5 | e137aa36 | 09-23 | -s | yes | D2 | yes | **D3** (D-2) |
| protocol.py::bound_result | P2 | 21 | e137aa36 | 09-23 | -s | yes | D2 | yes | **D3** (D-2) |
| protocol.py::classify_failure | P2 | 43 | e137aa36 | 09-23 | ks | yes | D2 | yes | D2 ok (fixed-runner fp) |
| protocol.py::comparability | P2 | 9 | e137aa36 | 09-23 | -s | yes | D2 | yes | **D3** (D-2) |
| protocol.py::run_probe | P2 | 39 | e137aa36 | 09-23 | -s | yes | D2 | yes | **D3** (D-2) |
| outcome.py::__post_init__ | P1 | 13 | 2f7f93bc | 09-23 | -s | yes | D2 | yes | **D3** (prose only) |
| outcome.py::contract_satisfaction | P1 | 21 | 2f7f93bc | 09-23 | -s | yes | D2 | yes | **D3** (prose only) |
| outcome.py::on_subject_absent | P1 | 19 | 2f7f93bc | 09-23 | -s | yes | D2 | yes | **D3** (prose only) |
| proof.py::Party.__init__ | C2-ORCH | 9 | ac88f366 | 09-30 | ks | yes | D3 | yes | D3 ok (builder `sys.platform`; record sha 56940fea… equal at ac88f366/cacaa6bd/da3ea33f; field darwin/3.14.7 in all 7 versions) |
| proof.py::Party.run | C2-ORCH | 9 | ac88f366 | 09-30 | ks | yes | D3 | yes | D3 ok |
| proof.py::Ranged.__init__ | C2-ORCH | 4 | ac88f366 | 09-30 | ks | yes | D3 | yes | D3 ok |
| proof.py::obligations_of | C2-ORCH | 4 | ac88f366 | 09-30 | ks | yes | D3 | yes | D3 ok |
| proof.py::prove | C2-ORCH | 108 | ac88f366 | 09-30 | ks | yes | D3 | yes | D3 ok |
| contract.py::canonical | P1 | 8 | 4afc9d10 | 09-21 | -- | no | D3 | yes | family hint unproven (D-4) |
| compiler.py::compile_spec | P1 | 16 | ab2fc134 | 09-21 | -- | no | D3 | yes | family hint unproven (D-4) |
| drift.py::attribute | P2 | 15 | 7c7f7dd8 | 09-21 | -- | no | D3 | yes | D-4; pilot re-measured on darwin (D-8) |
| writer.py::JournalWriter.__init__ | P3 | 9 | f097ba16 | 09-22 | -- | no | D3 | yes | D-4 |
| compat.py::Journal.head | P3 | 10 | 5bff6ebb | 09-22 | -- | no | D3 | yes | D-4 |
| projections/__init__.py::project | P3 | 4 | c6b90530 | 09-22 | -- | no | D3 | yes | D-4 |
| refmodel/failure_owner.py::_attempts | P3 | 12 | 88b9554a | 09-22 | -- | no | D3 | yes | D-4 |
| format2.py::CLOSERS | P4 | 8 | affae7da | 09-22 | -s | no | D3 | yes (flag copied from intro) | **flag wrong** (D-5) |
| format2.py::validate | P4 | 47 | affae7da | 09-22 | -s | no | D3 | yes (flag copied from intro) | **flag wrong** (D-5) |
| budget.py::charge | P4 | 41 | 224caa46 | 09-23 | -s | yes | D3 | yes | D3 ok |
| tool.py::ToolCall._data | P4 | 9 | d234be91 | 09-23 | -s | yes | D3 | yes | D3 ok |
| relevance.py::ChangedArtefact.__post_init__ | P5 | 22 | b8a7d2d0 | 09-24 | ks | yes | D3 | yes | D3 ok |
| vacuity.py::Hunk.side | P5 | 7 | 56c84863 | 09-24 | ks | yes | D3 | yes | D3 ok |
| adequacy.py::Assembly.__post_init__ | P5 | 3 | 0f453968 | 09-24 | ks | yes | D3 | yes | **out-of-tree run-bound (run V2)** (D-1) |
| routing.py::_EXECUTED | P1 | 260 | beeb5b68 | 09-24 | ks | yes | D3 | yes | **out-of-tree run-bound (run W2)** (D-1) |
| except_boundaries.py::check | P5 | 2 | beeb5b68 | 09-24 | ks | yes | D3 | yes | **out-of-tree run-bound (run X1)** (D-1) |
| gen_migration_table.py::_loss_code | P6 | 17 | 116b92a3 | 09-25 | ks | yes | D3 | yes | **out-of-tree run-bound (run P6)** (D-1) |
| owner.py::TAXONOMY | P1 | 638 | 175ba3a8 | 09-25 | ks | yes | D3 | yes | D3 ok |
| format3.py::JournalWriter3.append | P6 | 27 | abfe99df | 09-25 | ks | yes | D3 | yes | D3 ok |
| old_path_audit.py::_capabilities | P6 | 27 | 6099a816 | 09-26 | ks | yes | D3 | yes | D3 ok |
| python_callable.py::ON_DEADLINE | P2 | 12 | 71141778 | 09-27 | ks | yes | D3 | yes | D3 ok (P7 re-measure; no host statement) |
| cohort/lifecycle.py::DEMOTED | C2-P10 | 6 | 8d6ab04c | 10-01 | ks | yes | D3 | yes | D3 ok (P10-COHORT-MACHINERY has no platform field) |
| cohort/preregistration.py::workload_identity | C2-P10 | 13 | 8d6ab04c | 10-01 | ks | yes | D3 | yes | D3 ok |

**Per-class conclusion.**
* **D1 (4/4):** facts confirmed.
  * The macOS statement is about W26/W29/W30, which stopped with RESIDUAL_OWNERSHIP_UNKNOWN.
  * The "after" block binds `main`'s bytes, but names no host.
  * The pointer area is unchanged at the basis.
* **D2 (10/10):** facts confirmed, but the grade holds for only 2 rows (D-2).
* **C2-ORCH (5/5):** confirmed.

## Checked and found correct

* **Copies on other refs.** No canonical copy of any of the 327 exists in any committed JSON on any ref outside the 8
  records. I scanned 7,733 evidence/doc blobs (`check/c3.py`).
* **Tails and platform fields.** No committed dict for a 327 target carries `tail`, `t0`, `original`, `platform` or
  `identity`. The only exception is the v2.3 pilot (D-8).
* **Per-OS Q2 files.** `Q2-<os>-py*.json` mention the 327 targets, but `q2.py:74` reads `RECORDS`. They restate the
  records and are not measurements.
* **Text blobs.** No committed text blob binds an OS to these targets' runs. Worker logs mention the 5 C2-ORCH targets
  only as `SUPERSEDED … taken over by C2-ORCH` check lines.
* **Intro commits.** The 24 intro commits' touched files carry no machine-written `platform`, `python`, `host`,
  `machine` or `uname` key (`check/c6.py`).
* **CI workflows.** No workflow file in any version from 09-15 to 10-02 mentions mutation. I checked all 5 workflow
  commits, not just 2.
* **Run histories.** Every row that names `mutation.py` is a suite or CI row: C2-P10 seq 1–2 (`where: local`, lane full
  suite), P4 #72, C2-P2 #10–14.
* **Runner-1 behaviour.** At `65dc6435` it refuses on red baseline kill tests and has an explicit `os.name != "posix"`
  path.
* **`killed_by_timeout`.** Introduced at `2f7f93bc` (0 occurrences at its parent) and always written from then on.
* **POSIX-only window.** The `a4136fba` window is real: `2f7f93bc` 16:35 → `a4136fba` 17:14, and `a4136fba` is an
  ancestor of `e137aa36`.
* **Pointers.** All 25 have their token present and their blob sha correct, and their JSON pointers resolve.
* **Superseded evidence.** The pointer areas are unchanged at the basis: V2-006 `/anchor_watchdog`, the F011 record,
  and the manifest status, which changed only the safety-record digest. No pointer is false-current.
* **Kill files and R6.** The 35 distinct kill files are all in `tests/v2`, and `tests/v2/__init__.py` arms
  `registry.py` (`TESTS_V2 = "tests/v2"`). The R6 expectation is plausible (not measured by me either).
* **V2.1 overlap.** V2.1, both the live record and campaign-2, has no target in any of the 327 modules.

## Traces (scratch only)

All of them are in `check/` next to this file.
* `intro_check.json` `3816c879…`
* `ootree_bound.json` `3927ca3f…`
* `ootree_hits.json` `dfdb6e4c…`
* scripts `c1.py`–`c10.py`

`diag_shas.txt` lists only folder-relative names and digests. None of it is for commit. Any later commit of the
out-of-tree material must be normalized first, because its launch scripts hold home and temp paths.
