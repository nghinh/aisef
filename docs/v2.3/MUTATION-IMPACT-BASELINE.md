# AISEF v2.3 — MUTATION IMPACT BASELINE (W0, frozen)

**What this is.** The measured mutation-qualification cost that F5 (incremental qualification, charter §1.3/§3)
must beat, the invalidation rules in force today, and the cold-vs-incremental protocol W1 must use. No mutant was
run to produce it. Every number is recomputed from committed records with `python3` (row `seconds + overhead_s`,
worker-log stamps). Numbers marked **[E]** are estimates. Numbers marked **[OP]** come from operator notes, not
committed evidence.

**Frozen identity at capture (2026-11-21).**

| item | value |
|---|---|
| HEAD | `1bf5dd2f` (branch `release/v2.3-big`) |
| `aisef2` kernel tree | `e865d65c` (= v2.2.0 RC2 kernel, `V2.2.0-STATUS.json` candidate.RC_KERNEL_TREE) |
| `validation/v2/mutation.py` | sha256 `07812c4f…` (raw = LF-normalised), 2,734 lines |
| `mutation.py --check` | **PASS**, 1.72 s wall on this host (3 informational `SUPERSEDED V2.2-B1-LIVENESS` rows) |
| capture host | Apple M1, 8 cores, 16 GiB, macOS 26.5.2, CPython 3.14.7, 25 GiB free on `/` |

Historical cost figures come from other hosts: the Linux server for B1 (four worker trees, see §1.3), the operator
Mac for campaigns 2–9 and `sw`, and native Windows 10 for 3 liveness targets. Records do not name the host (§4, row P).

---

## 0. Headline numbers F5 must beat

| quantity | value | source |
|---|---|---|
| declared targets / modules | **994 / 86** (17 phases) | `mutation.TARGETS`, `PHASE_TARGETS` |
| active V2.1 record | **667 targets, 17,322 mutants** (16,962 K / 360 S), **313.7 serial-h** | `closure-evidence/v2/v2.1/MUTATION.json` |
| v2.2 release gate (B1) | **177 targets, 5,909 mutants, 189.8 serial-h**; longest target `run.py::execute` 36.55 h | `B1-RISK-MANIFEST.json` × `MUTATION.json` |
| per mutant | median **5.8 s**, p90 **226 s**; 21.6 % of mutants (>60 s) = **87.9 %** of mutant time | `MUTATION.json` rows |
| per target | median **180 s**, p90 **2,900 s**, max **131,596 s** | `MUTATION.json` |
| historic logged campaigns | **194.6 h wall, 663.2 worker-h, 56,358 mutant runs**, 1–5 workers | `v2.1/mutation-workers/*.log` |
| whole-module blast radius, worked case | one changed line in `bundle_cli._create` staled **45 targets / 1,659 mutants / 41.87 serial-h**; wall floor **11.7 h** | ruling + `MUTATION.json` |
| function-granular lower bound, same case | `{_create, init, _write_new, main}` = **187 mutants / 4.86 serial-h** (−88 %) **[E: lower bound only]** | §3 |
| under-invalidation | kill-test bytes, transitive code, generator inputs, platform and ruling authenticity are **not bound** by `--check` | §4 |

---

## 1. Inventory — targets and mutants

### 1.1 Declared targets (`validation/v2/mutation.py`)

994 targets in 86 modules. Phase sizes: P1 19, P2 32, P3 41, P4 68, P5 45, P6 78, C2-ORCH 5, C2-P10 39, **V2.1 667**,
and 0 for C2-P1..P4, K-PRESAT-001, K-NOWORK-001, V2.0-S2 and V2.2-B1-LIVENESS (those phases hold superseded or
historical records only). There are 17 records: 14 in `RECORDS` at `mutation.py:53-63`, plus `V2.0-S2` (`:598`),
`V2.2-B1-LIVENESS` (`:1294`) and `V2.1` (`:1295`). The per-file kill timeout is 900 s (`mutation.py:70`).

### 1.2 Active record `closure-evidence/v2/v2.1/MUTATION.json` (100.8 MB, runner 2, merged by `v21_mutation_record.py`)

667 targets in 34 modules. 17,322 mutants: 16,962 KILLED and 360 SURVIVED. There are 20 distinct `tree_sha256` values
and 35 distinct `source_sha256` values. Mutants per target: median 11, p90 60, max 459.

| module | targets | mutants | serial-h | | module | targets | mutants | serial-h |
|---|---:|---:|---:|---|---|---:|---:|---:|
| app/run.py | 25 | 1,087 | **62.28** | | app/review_verify.py | 28 | 608 | 4.71 |
| app/bundle_cli.py | 45 | 1,659 | **41.87** | | app/client.py | 11 | 507 | 3.57 |
| app/lineage.py | 34 | 998 | **41.60** | | runtime/process_range.py | 25 | 290 | 3.24 |
| app/feedback.py | 2 | 346 | 19.24 | | app/review_ocr.py | 24 | 451 | 2.83 |
| probe/cli_invocation.py | 94 | 1,925 | 16.87 | | app/confine.py | 30 | 1,069 | 1.66 |
| app/verify.py | 5 | 335 | 16.34 | | app/diagnostics.py | 15 | 369 | 0.92 |
| app/adapters.py | 12 | 564 | 15.53 | | orchestrate/workspace.py | 17 | 249 | 0.82 |
| app/settings.py | 10 | 426 | 14.30 | | app/preflight.py | 6 | 323 | 0.74 |
| app/bundle.py | 6 | 249 | 12.64 | | journal/fold.py | 11 | 98 | 0.40 |
| orchestrate/story_runner.py | 11 | 411 | 10.42 | | 10 other modules | 83 | 1,376 | 1.69 |
| app/usage.py | 8 | 259 | 9.87 | | | | | |
| app/cli.py | 2 | 174 | 8.66 | | **total** | **667** | **17,322** | **313.7** |
| probe/file_artifact.py | 54 | 1,119 | 8.61 | | | | | |
| probe/python_callable_v2.py | 31 | 799 | 7.43 | | | | | |
| probe/process_effect.py | 78 | 1,631 | 7.40 | | | | | |

(Paths are under `aisef2/`. The 10 other modules are tripwire, invariants/registry, orchestrate/adapters,
orchestrate/review, plan/static_admission, probe/calibration, probe/catalog and runtime/run_scope, plus
`validation/v2/cleanup_authority.py` and `validation/v2/destructive_authority.py`. Each is ≤ 0.30 h.)

The v2.1 **final** summary `MUTATION-SUMMARY.json` holds 614 targets: 90 `measured_at_final_head` and **524
`reused_after_mechanical_proof`** (85 %). It also holds 16,086 mutants, 7 unaudited survivors, `MUTATION_VERDICT FAIL`
at `8c7bdb44`, and 1,513 stale results excluded. The record grew to 667 targets later, through v2.2 B1.

### 1.3 v2.2 risk-based release gate (B1)

`B1-RISK-MANIFEST.json` froze 177 targets and 5,896 mutants in three tranches: A 150/5,603, B 24/233 and C 3/60
(Windows-only liveness). All 177 were measured: **5,909 mutants** = 5,782 K + 127 audited S (`V2.2.0-STATUS.json`
MUTATION.RECONCILIATION_177). The +13 difference is the generator at the measured source: `verify.py` was frozen at
322 and measured at 335. The 13 modules are run 25/1,087/62.3 h, bundle_cli 45/1,659/41.9 h, feedback 2/346/19.2 h,
verify 5/335/16.3 h, adapters 12/564/15.5 h, settings 10/426/14.3 h, bundle 6/249/12.6 h, client 11/507/3.6 h,
process_range 25/290/3.2 h, fold 11/98/0.4 h, run_scope 13/135/0.16 h, tripwire 8/137/0.16 h and registry
4/76/0.07 h. Measurement trees: `ce4a76fb` ×142, `ce87088a` ×14, `cb17f57f` ×6, `063e42db` ×4, `39ac1898` ×3,
`9923b34f` ×3 (Windows), and 4 other trees ×1–2. **The record itself names no tree's platform.**

---

## 2. Cost per mutant, per target, per campaign

### 2.1 From row timings (`MUTATION.json`, 91,624 mutant rows + T0 rows; serial = Σ(`seconds`+`overhead_s`))

| unit | median | p90 | other |
|---|---:|---:|---|
| mutant (all 17,322) | 5.81 s | 226.4 s | mean 60.6 s, max 5,477 s |
| KILLED mutant | 5.70 s | 205.5 s | the kill row runs with `-f`, then the bracket of 2 null controls + 1 re-run (`BRACKET`, `mutation.py:2265`) |
| SURVIVED mutant | 150.8 s | 437.2 s | the whole kill set must PASS |
| target (all 667) | 179.8 s | 2,900 s | max 131,596 s |
| T0 baseline per target | 39.9 s | 343.7 s | Σ 21.9 h |
| B1 mutant (5,909) | 6.4 s | 407.2 s | |
| B1 target (177) | 409.7 s | 6,440 s | Σ 189.8 h |

Where the 313.7 serial-h go: killing rows 238.0 h, bracket rows 33.9 h, survivor rows 19.9 h, T0 21.9 h. This
excludes the pristine copy per `run` (copy of `COPY`, `mutation.py:1543-1547`, which includes `closure-evidence/v2`
at about 1.6 GB, setup 6–7 min **[OP]**), fresh-tree rebuilds and the post-run `check()`.

**Host variance is large.** The same target, `run.py::execute`, took 5.83 h wall for 337 mutants (c5), 7.73 h for
366 (c9), 15.18 h for 337 (c2), 29.47 h for 366 (sw, 2 workers) and 36.55 serial-h for 459 (B1). A cold/incremental
pair is only comparable on one host, with the same K, the same load and the same kill set.

### 2.2 Campaign wall time (committed worker logs `closure-evidence/v2/v2.1/mutation-workers/*.log`)

Each `=== <UTC> <worker> line N <target>` line opens a target. Its `owned processes: … (<mode>, Ns)` line closes it.
The two agree: c9-w1 starts at 01:17:20, then +27,824 s, and the next target starts at 09:01:06.

| campaign | snapshot | workers | target runs | mutants | wall h | worker-h | worker-s/mutant | longest target (h) |
|---|---|---:|---:|---:|---:|---:|---:|---|
| c2 | `5719f1f8` | 4 | 457 | 12,208 | 58.9 | 235.4 | 69.4 | run.execute 15.18 |
| c3 | `f860e57f` | 4 | 199 | 7,826 | 14.5 | 58.1 | 26.7 | — |
| c3b | `f860e57f` | 1 | 2 | 67 | 0.8 | 0.8 | — | — |
| c4 | `b5c24575` | 4 | 28 | 1,378 | 2.8 | 11.1 | 29.0 | — |
| c5 | `289885ef` | 5 | 528 | 13,566 | 24.3 | 100.3 | 26.6 | story_runner._attempt 11.68 |
| c6 | `a770fbbf` | 5 | 56 | 1,419 | 0.9 | 4.3 | 10.9 | — |
| c7 | `853da4ad` | 3 | 3 | 448 | 0.4 | 0.8 | 6.4 | — |
| c8 | `5df323a3` | 4 | 12 | 680 | 0.4 | 1.1 | 5.8 | — |
| c9 | `4ec961e7` | 4 | 544 | 15,173 | **34.0** | 136.0 | 32.3 | story_runner._attempt 14.39 |
| sw (supp) | `8c7bdb44` | 2 | 90 | 3,593 | **57.6** | 115.3 | 115.5 | run.execute 29.47 |
| **Σ** | | | | **56,358** | **194.6** | **663.2** | | |

Cross-checks against narrative records: c9 is about 34 h (`v2.1/CAMPAIGN-9-CANDIDATE-REPORT.md:107`) and sw is about 57.6 h
(`v2.1/HANDOFF-INTERIM.md:13`). The per-target wall in c9 has median 264 s and p90 1,637 s. In every campaign the
longest single worker span equals the campaign wall. **A target cannot be split.** `main()`'s `run` measures whole
targets (`mutation.py:2653-2720`) and has no mutant-subset flag. The wall-time floor is therefore the longest target
in scope. In the top 5, `run.execute`, `story_runner._attempt`, `Reviewer._ocr`, `verify` and `bundle_cli.continue_from`
recur. In sw, the top 5 targets were 60.9 % of worker time.

Measurements with no committed wall time:
- mw0/mw1 (`fce3d7b7`, 2 workers, 6,257 mutant lines, no `===` stamps) and l1–l4-ord (240).
- **B1 server campaign:** its logs are not in the repo. **`B1-LINUX-AGGREGATE.json` does not exist** (`git ls-files` finds no aggregate).
- wave-2 (`89de4685`, 4 workers, 2,154 mutants; `v2.2/MUTATION-WAVE2-CLASSIFICATION.md:5-14`).
- wave-1 (9 targets, 1,910 mutants, 110.8 serial-h; `v2.2/WAVE1-MUTATION.json`).

**[OP]** The B1 `execute` lane ran about 450 mutants in 34.8 h active, about 12.9 mutants/h on one worker. The
42-target Option-A estimate was 37.2 h single-process, with an 11.4 h floor. This doc recomputes those from the
record: **40.7 serial-h**, floor `continue_from` **42,191 s = 11.7 h**.

---

## 3. Whole-module invalidation — blast radius

**Rule.** `run_target` stores `source_sha256 = source_digest(whole module)` (`mutation.py:2439`). `source_digest` is
an LF-normalised sha256 (`:1553-1554`). Both verdict paths re-hash the whole live file and compare it to that value
(`_problems_v2` `:2524`, legacy `target_problems` `:2578`). Any byte change other than CRLF→LF stales **every**
target in the module: a comment, a docstring or another function. The only exception is the one-off
`verified_reuse_current` (`:1557-1645`).

**Worked case (measured, v2.2.0).** `bundle_cli.py::_create` gained `newline=""`. That is one line, and `_create` is
itself a target (ruling `source_transition.only_changed_function`).

| view | targets | mutants | serial-h | note |
|---|---:|---:|---:|---|
| staled by today's rule | **45** (all of bundle_cli) | **1,659** | **41.87** | wall floor `continue_from` 11.7 h at K ≥ 2 |
| dispositioned MEASURED | 3 (`_create` 3, `_journal` 48, `init` 12) | 63 | 1.17 | at `0fdfc022`; `init` 12/12 on macOS and Linux |
| dispositioned VERIFIED_REUSE (owner Option C) | 42 | 1,596 | 40.7 | one-off; ruling `governed_by`: the full re-run "materially exceeded its approval basis" |
| static callers of `_create` (`bundle_cli.py:832` init, `:1077` `_write_new`, `:1124-1152` main) + itself | 4 | 187 | 4.86 | **[E] lower bound** of a function-granular set |

The lower bound is not the F5 answer. A target is also exposed when its **kill tests execute** the changed
function, even if the target never calls it. Example: a `lint` test that first runs `init`. That set needs a
`reach.py` run at the transition. It has not been measured.

**Per-module blast radius.** This is the cost of a change to any one function under today's rule; §1.2 has the full
table. run.py 25 targets/1,087 mutants/62.3 h. bundle_cli 45/1,659/41.9 h. lineage 34/998/41.6 h. feedback 2/346/19.2 h.
cli_invocation 94/1,925/16.9 h. verify 5/335/16.3 h. adapters 12/564/15.5 h. settings 10/426/14.3 h.
story_runner 11/411/10.4 h. E5 lands in story_runner, and its `_attempt` alone took 11.2–14.4 h wall per run.

**B1 amplifier.** `b1_bindings_check.py:20-21` refuses when `HEAD:aisef2` differs from the frozen tree, so every
kernel commit needs a binding amendment. There are 10 (`v2.2/B1-BINDING-AMENDMENT-1..10.json`, 2026-11-14 →
11-20). It hashes **raw bytes** (`:29`), while `mutation.source_digest` LF-normalises. A CRLF checkout therefore
fails the bindings but passes `--check`, so there are two digests for one identity.

---

## 4. What invalidates a record today — and what does not

| # | input | bound by `mutation.py --check`? | where | consequence |
|---|---|---|---|---|
| S | target module bytes (LF-normalised) | **yes** (whole module) | `:2524`, `:2578`; exception `:1623-1645` | over-invalidates (§3) |
| R | record self-consistency: all mutants listed, counts, classes, confirmed bracket, T0 PASS | yes | `:2527-2565`, `_confirmed :2505` | — |
| A | survivor audits: by position, at the measured digest, NO_AUDIT | yes | `audit_of :1535-1539`, `:2531-2535` | an audit dies with any module edit |
| O | execution-order table: committed, sha256 | yes | `:2544-2550` | — |
| M | missing result / V2.1 non-runner-2 | yes | `problems_of :2606-2610` | — |
| K1 | kill-set **names** vs current `TARGETS` | **no** (only `v21_mutation_record.proof :56`) | `run_target :2432` stores the names | a re-declared kill set is not noticed |
| K2 | kill-test **file content** + its closure | **no** (only `proof :58-63`, `tests/` only) | — | **empirical, below** |
| T | transitive product code (callees, helpers, fixtures) | **no**; `proof` lists it as `other_code_changed`, never folds it in (`:68`) | — | **346 of 524** reused v2.1 results (66 %) had it (`MUTATION-SUMMARY.json` provenance) |
| G | generator: `mutants`, `_SWAP`, `_inert`, `_script`, `_root`, plus enum members of imported aisef2 modules (`_enum_members :1648-1657`) | **no**; `proof :64-67` regenerates | — | `aisef2/arch/enums.py` (not a target) is imported directly by kill files of 538 targets |
| P | platform / interpreter | **not recorded** (row keys: file, exit, seconds, outcome, why, ran, failures/errors, first, tail_sha256, overhead_s) | `VERIFIED_REUSE_PLATFORM :1575` is unused (CODE-AUDIT #14) | Windows evidence is identifiable only by tree `9923b34f` |
| W | `tree_sha256` (whole `COPY` tree incl. evidence) | recorded `:2439`/`:1862-1865`; checked only by `:1634` | — | too coarse to serve as an impact key |
| U | owner-ruling authenticity | presence only (`.is_file()` `:1642`) | CODE-AUDIT #14; no test #15 | `{}` at that path passes |
| H | runner / harness code | no (`v21_snapshot_delta` lists it as `outside_the_proof`) | — | but `v2.2/CONFORMANCE-RULING.json` pins `mutation.py` sha256 `07812c4f…` → editing `mutation.py` stales `--check-v22` |

**Net.** Today's gate **over-invalidates** (S: whole module) and **under-invalidates** (K1, K2, T, G, P, U) at the
same time.

**Empirical evidence for K2/T (natural experiment over committed worker records, no new run).** Pairs of results
for the same target were compared. Each pair has the same target digest, the same kill-set names and the same mutant
list, but was measured at different snapshots:

| older → newer | comparable targets / mutants | targets with a changed class | direction |
|---|---|---:|---|
| c2 `5719f1f8` → c5 `289885ef` | 269 / 4,706 | 0 | — |
| c5 → c9 `4ec961e7` | 63 / 2,308 | 0 | — |
| c2 → c9 | 35 / 790 | 0 | — |
| c9 → mw `fce3d7b7` | 170 / 5,930 | **28** | 102 S→K, **1 K→S** |
| c9 → sw `8c7bdb44` | 74 / 2,860 | 6 | 6 S→K |

The K→S flip is `diagnostics.py::access_of`, the mutant at position 11, `L106 True->False`. At c9-w4 it was KILLED, bracket confirmed,
by `test_v21_pm8_diagnostics.py`. At mw1 that test PASSed. The target file is identical. Between the two snapshots
the kill file grew by 57 lines, and 4 kernel files changed: `calibrations.py`, `client.py`, `story_runner.py` and
`process_range.py`. **The cause has not been established.** A reused KILLED verdict would have been false-current
under `--check` alone. The S→K flips fit kill-test strengthening. For c9→sw, `v2.1/SUPPLEMENTARY-SCOPE.json`
`merged_head` names 2 kill-test edits; this was not checked per flip.

A stricter replay ran `v21_mutation_record.proof(c5 result, 289885ef → 4ec961e7)` for every c5 target. Only
**10 targets / 85 mutants** would stand, all 10 with `other_code_changed`, and all 10 have identical c9 verdicts
(0 flips). The replay took 972 s on this host (script:
`<scratch>/w0/flips.py`).

---

## 5. Machinery that already exists (F5 reuses it; it does not rebuild it)

| tool | what it decides | measured cost |
|---|---|---|
| `validation/qualification/v21_mutation_record.py` `proof` `:43-68` | reuse iff target blob, kill set, kill-test `tests/` closure and generator output are unchanged | v2.1 final: 524 of 614 reused |
| `validation/qualification/v21_snapshot_delta.py` | per base→head table: remeasure / stand / provisional; `GENERATOR :79`, `HARNESS :77` | — |
| `validation/v21/read_set.py` | which files each kill file opens or lists | 133–166 kill files: **1,381–1,450 test-s** per head (`v2.1/campaign-3..8/read-set.json`, darwin py3.14) |
| `validation/v21/reach.py` | which **changed functions** each kill file executes (AST own-code diff) | 161 kill files: **1,392 s** (`v2.1/campaign-5/reach.json`) |
| `validation/v21/trace_paths.py` | whether a kill file runs a changed *path*, children included | — |

Historic incremental deltas (`v2.1/campaign-N/delta/DELTA.json` counts):

| delta (base→head) | targets | remeasure | stand | stand with `other_code_changed` | same-numbered campaign |
|---|---:|---:|---:|---:|---|
| c2 `5719f1f`→`32ff9cb` | 466 | 30 | 436 (all provisional) | — | — |
| c3 `5719f1f`→`8d2bf01` | 468 | 179 | 289 | 255 | c3: 199 runs, 14.5 h |
| c4 `f860e57`→`c621add` | 469 | 28 | 441 | 407 | c4: 28 runs, 2.8 h |
| c5 `b5c2457`→`9f336fb` | 528 | 170 | 358 | 358 | c5 |
| c6 `289885e`→`537f0b5` | 528 | 56 | 472 | 456 | c6: 56 runs, 0.9 h |

Remeasure reasons in c3: kill set changed 123, target file changed 112, kill tests changed 26. In c5: target 108,
new target 59, kill tests 29.

**Gaps F5 must close.**
1. Results that stand while `other_code_changed` is non-empty are not proven. Under F5 they are UNRESOLVED or
   INVALIDATED until reach/trace clears them.
2. The gated record (`MUTATION.json`) carries **no per-target provenance class**. Only the SUMMARY does. As a result,
   reused results cannot be told apart from measured ones in the file the gate reads.

---

## 6. Cold-vs-incremental protocol (binding on F5 in W1)

**Fixed for both arms.** These are reported in the result:
- base = the W0 freeze SHA;
- the host (CPU, cores, RAM, OS, Python, free disk ≥ 15 GiB);
- the same worker count K;
- isolation (no `opencode` on PATH, scratch XDG data/state/cache, scratch TMPDIR);
- `TIMEOUT` 900 s;
- LPT queue order.

Wall time is read from the runner's own `(…, Ns)` lines and the start/end stamps. Both arms run on an isolated
worktree branch. They are never merged, and nothing is committed while an arm runs.

**Arms.**
- **C0 (today):** the set `mutation.py --check` reports stale at H. It can be **0** for classes the gate cannot see.
- **C1 (sound cold):** C0 ∪ every target whose kill-test closure contains a changed file. This is what a truthful
  gate without F5 must re-measure. **The ≥ 50 % claim is measured against C1.** C0 is reported alongside it to show
  where today's gate is unsound.
- **I (incremental):** F5 classifier wall time (AST diff, generator check, platform check, read-set and reach for the
  affected kill files only), plus a re-measure of every INVALIDATED and every UNRESOLVED target. Reuse never counts
  as measurement.
- **Detection unchanged.** On the cohort, each target I reuses must match the fresh C1 re-measure mutant for mutant.
  **0 flips** are allowed, and every KILLED result keeps its bracket.

**Change classes.** Cohort candidates are chosen so both arms are cheap and measured; serial costs are from
`MUTATION.json`.

| class | recipe | C0 | C1 | expected I | acceptance |
|---|---|---|---|---|---|
| **N0** no-op outside every closure | docs/ or a non-record evidence file; plus a `pyproject` version-only bump (EVID-COUPLING-01) | 0 | 0 | classifier only | all VERIFIED_REUSE, 0 mutants run, no mutation record orphaned |
| **N1** AST-neutral edit inside a target module | a comment or blank line in `aisef2/journal/fold.py` | 11 targets / 98 mut / 1,426 s | same | 0 mutants **[E]** | VERIFIED_REUSE; measured `source_sha256` kept, never rebound |
| **O** one function | body edit of one target function in `aisef2/runtime/run_scope.py` (13 targets / 135 mut / 576 s, 4 kill files) | 13 targets / 576 s | 13 + any target whose kill-test closure imports run_scope | the edited target + targets whose kill files **execute** it (reach) **[E]** | INVALIDATED set ⊇ the executors; reach run recorded |
| **S** shared helper | a function that the kill tests of several targets execute, picked with F5's own closure tool so that C1 ≤ ~2 serial-h. The cheapest measured kill-file envelopes are `tests/v2/p2/test_static_admission.py` (13 targets / 192 mut / 0.18 h) and `tests/v2/p4/test_interruption.py` (4 / 59 / 0.08 h). The empty `__init__.py` files do not qualify. | **0** (blind) | targets whose kill tests import the helper | executors only **[E]** | C0 = 0 ⇒ F5 must INVALIDATE; reuse only after a reach proof |
| **K** kill-test edit | add or alter a test in `tests/v2/p4/test_run_scope.py` (9 targets / 81 mut / 0.09 h) | **0** (blind, names only) | the 9 targets | SURVIVED mutants re-run; KILLED kept only if the killing test and its executed code are unchanged **[E]** | the c9→mw K→S shape (§4) is caught |
| **X** cross-platform | (a) a Linux result consumed on darwin/Windows; (b) an edit inside `_win_liveness` / `pid_alive` (3 targets / 60 mut / 785 s on native Win10, `v2.2/B1-LIVENESS-MUTATION.json`); (c) a CRLF checkout | 0 for (a) and (c) | the Windows 3 need native Windows | (a) UNRESOLVED, (b) native Windows re-measure, (c) one canonical digest | a POSIX run never stands in for a Windows-only kill set |
| **Replay** (no mutants) | the `c15d5b10→0fdfc022` transition; `v2.2.0→HEAD`; the §4 natural experiments | — | — | classification only | see the reconciliation note below |

**Negative controls (offline, 0 mutants; each must FAIL):**
- a stale target;
- a tampered record (verdict, digest or class edited);
- a ruling replaced by `{}` (#14);
- a mismatched platform;
- reuse for a target outside the authority set;
- a generator edit (the mutant list differs);
- a kill-set rename;
- missing provenance.

The seeded known-bad calibration (`checker_calibration` REGISTRY, 57/57) must still FAIL.

**Reconciliation note for `ARCHITECTURE.md` §8 W1 — RESOLVED at the W0 freeze by `W1-DESIGN.md` §2.4/I8:** the 42 Option C targets are `VERIFIED_REUSE (v2.2.0-accepted via ruling AISEF-V2.2-B1-MUTATION-EVIDENCE-REUSE-RULING)`; the basis point is v2.2.0, where `bundle_cli.py` is already `0fdfc022`, so the pre-basis `_create` transition is covered by the ruling (pinned by digest), not by the reach rule. The original note follows.

1. `ARCHITECTURE.md:255` expects the replay to give VERIFIED_REUSE for "exactly the 42". Its own reach-set rule
   (`:229`) would INVALIDATE `main` and `_write_new`, because both statically call `_create` (`bundle_cli.py:1077`,
   `:1124-1152`). Their reuse rests on the owner's semantic POSIX-no-op proof, which is not mechanisable. The expected
   mechanical answer is therefore at most 40 VERIFIED_REUSE plus 2 INVALIDATED. The alternative is to cite the pinned
   ruling as the authority for those 2.
2. The reach set is rooted at the target function. It misses changed same-module code that the kill tests execute
   (§3); that needs execution reach (`reach.py`).
3. The rule "any changed non-test file in the import closure → INVALIDATED" (`:232`) is sound but costly. Kill files
   that directly import `calibrations.py` reach 353 targets / 181 serial-h; `errors.py` 154 / 165 h; `arch/enums.py`
   538 / 287 h; `app/__init__.py` 553 / 297 h. These are lower bounds, counting direct imports only. Without
   execution-reach narrowing, the S class cannot meet ≥ 50 %.

---

## 7. Expected W1 qualification cost (all **[E]**, 0 USD, 0 paid provider calls)

| item | cost |
|---|---|
| F5 classifier + negative controls + calibration | minutes of CPU, **0 mutants** |
| impact inputs (read-set + reach) for the cohort's kill files (≤ ~10 files) | < 5 min per head; ≤ ~25 min each if all 160+ kill files are run (measured 1,381–1,450 s and 1,392 s) |
| record replay (`_create` transition, `v2.2.0→HEAD`, §4 pairs) | minutes to ~1 h of git and AST work; the v21-`proof` replay of c5→c9 (528 targets) took 972 s on this host |
| benchmark cold arms on the cohort (fold 1,426 s + run_scope 576 s + tripwire 570 s = 2,572 serial-s from Linux-server rows) | 20–90 min per sweep on this M1 (an unknown 0.5–2× host factor); N1, O and K share cold sets |
| benchmark incremental arms | ≤ cold |
| **total W1 machine time** | **~3–6 h at K = 2–4** |
| X(b), native Windows (optional) | about 15 min of test time; needs a Windows runner. Running it through CI means a branch push, which needs a disclosure review because of `CODE-AUDIT.md` (owner ruling D) |

**Not in W1 (owner ruling: no full campaign before the design is proven):**
- a full re-measure of 17,322 mutants (313.7 serial-h; 34–59 h wall at 2–4 workers on past hosts);
- a B1 cold re-run (189.8 serial-h; floor `run.execute` 36.5 h).

**Re-qualification that W1's own edits trigger:**
1. F5 edits `validation/v2/mutation.py`. That file is not a target module, so no mutation record goes stale. It
   **does** stale the `mutation.py` row of `v2.2/CONFORMANCE-RULING.json`, which needs a v2.3 conformance round
   (no mutants).
2. Touching generator semantics (`mutants`, `_SWAP`, `_inert`, `_script`, `_root`, `_enum_members`) would shift the
   mutant lists record-wide: about 17,322 mutants INVALIDATED. Keep the generator byte-identical in W1, or prove that
   the per-target mutant lists are unchanged (`proof :64-67`, AST only).
3. Editing `aisef2/app/calibrations.py` for EVID-COUPLING-01 is invisible to today's gate. A truthful F5 would expose
   353 targets / 9,379 mutants / 181 serial-h (direct-import lower bound). Keep W1 out of `aisef2/`
   (`ARCHITECTURE.md:216`, CR-15).

---

## 8. Reproduce

All of these are read-only: no mutant runs, and no product, test or validation file is edited.

- `python3 -P validation/v2/mutation.py --check` gives PASS in 1.72 s.
- The figures in §1–§2.1 come from loading `closure-evidence/v2/v2.1/MUTATION.json` and summing
  `seconds + overhead_s` per row (`t0`, `original`, `results[].files`). Medians and p90 are linear-interpolated.
- The figures in §2.2 come from parsing `closure-evidence/v2/v2.1/mutation-workers/*.log`: `=== <ts> … <target>` opens
  a target and `owned processes: … (<mode>, Ns)` closes it.
- The §4 pairs come from the worker `*.record.json` files, grouped by worker prefix, keeping only pairs with an equal
  `source_sha256`, an equal `kill_tests` list and an equal mutant list, and comparing `class` per position.
- The §5 deltas are the `counts` and `targets[].reasons` of each `DELTA.json`.
- The §6 S and §7 lower bounds come from a direct-import regex over the 235 kill files at HEAD. They exclude transitive
  imports, so they understate the real reach.

Cross-references:
- `CODE-AUDIT.md` #14 and #15 (VERIFIED_REUSE authority and tests), #32 (`require_armed` record known-stale), #38
  (`currency_dag` leaf `missing`);
- `RISK-REGISTER.md` EVID-COUPLING-01;
- `RELEASE-CHARTER.md` §1.3, §3, §4;
- `MASTER-CHECKLIST.md` F5 row;
- `docs/IMPROVEMENT-ROADMAP.md` §F5.

## 9. Correction at the W0 freeze (lane D3)

The statements that the V2.1 record "names no platform" / is "Windows only by tree 9923b34f" are superseded: V2.1 rows carry platform evidence — 659 entries have `<tree>/` traceback frames, 3 have `<tree>\` frames and 176 carry an interpreter path (W1-DESIGN §2.4.4). The row-less legacy records (P1–P6, C2-ORCH, C2-P10) carry none.

Also superseded by `W1-DESIGN.md` §10/§2.8 (measured with the sound rules): §7's "~3–6 h total W1 machine time" and "editing `mutation.py` stales no record" — `mutation.py` is in the closure of 5 targets / 497 mutants (tier C), and the honest W1 scope is decided by SCALE-1.
