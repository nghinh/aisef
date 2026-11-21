# AISEF v2.3 — W1 FROZEN DESIGN (F5 incremental qualification + the P1 dependencies)

**Status:** frozen with the W0 freeze. A change to this design is an appended, dated amendment at the end of this
file, never an edit. **Scope order (owner ruling 2026-11-21):** W1a = F5 first (+ EVID-COUPLING-01, REL-GOV-01,
BUILD-REPRO-01, F2, test-env); W1b = E5, the first kernel change, qualified *through* F5. No mutation campaign runs
before W1a's negative tests and affected-scope proof pass.

## 1. Measured facts that fix this design

| # | Fact | Evidence |
|---|---|---|
| M1 | Mutation currency today = "whole target file LF-sha256 equals `source_sha256`" (or the 42-target Option C table). `--check` never compares the recorded `kill_tests` with the current kill set, never hashes a kill file, the generator, the enum modules the generator reads, or the platform. → over-strict (any byte in the file stales every target in it) **and** under-strict (a weakened kill test or changed generator stays "current"). | `validation/v2/mutation.py:2524-2526, 2578-2580`; F5 map §1–§4 (W0 lane `f5:input`) |
| M2 | Kill-set drift of the 994 live targets vs the current `TARGETS`: **965 identical, 21 same set/other order, 8 recorded ⊂ current** (kill set grew by `tests/v2/test_v2_005.py`), **0 dropped or different**. | `killset_drift.py` over `mutation.RECORDS` at `1bf5dd2f` |
| M3 | Between `v2.2.0` (`da3ea33f`) and HEAD no mutation record, no `aisef2/`, `tests/`, `validation/v2/`, `validation/v21/` byte changed. | `git diff --stat da3ea33f HEAD -- <records> aisef2 tests validation/v2 validation/v21` = empty |
| M4 | **Kernel-change blast radius (measured):** one behaviour-neutral comment line appended to `aisef2/orchestrate/story_runner.py` (throwaway worktree, probe commit `62cba92b`, never pushed) → `mutation --check` 11 targets / 411 mutants stale; Q0 `checker_calibration --check` FAIL (mutation + currency_dag "not calibrated", Q0 record stale); `b1_bindings_check` FAIL ("kernel is not the frozen e865d65c"); `currency_dag` rc 2 (5 nodes upstream-unresolvable); `p5_acceptance --check-v22` and `v21_conformance_ruling --check-v22` FAIL; **13 of 18 sealing-GATED tests FAIL**. `release_calibration --check` stays PASS. | `scratchpad/blast.out` (8 m 47 s on M1/8 cores) |
| M5 | A version-only bump fails 3 unit tests on every leg through `release_calibration.RECORD_REL = newest_rel(_version())[0]`; consumers `p5_acceptance.py:896-898`, `q2.py:37`, `v21_conformance_ruling.py:402`; `--write` rewrites `aisef2/app/calibrations.py` (only `demonstrated_at` differs). | CI run `44845163565`; RISK-REGISTER `EVID-COUPLING-01` |
| M6 | The Q0 record renders each checker's `clean_problems` and known-bad `observed` **message strings** — changing a checker's message text or its clean verdict stales the owner-gated, write-once Q0 record. | `validation/v2/checker_calibration.py:621-655, 688-692`; `currency_dag.py:85-94` (Q0 OWNER_GATED) |
| M7 | A correct reuse proof already exists at merge time — `s2_mutation_record.proof()` (target blob identical, kill set current, kill-test closure byte-identical, generator yields the same descriptions) — but it does not gate `--check`, ignores changed non-test modules in the closure, and is pinned by `FROZEN_CRITERIA_SHA256` (call it, never edit it). | `s2_mutation_record.py:113-175, 57`; `v21_mutation_record.py:39-68` |

| M8 | **154 of 262** distinct kill files (not "55 of 116") have `story_runner.py` in their static closure. That gives **640 dependent targets / 17,897 mutants / 276.96 rows-h + 21.11 T0-h**. Its own module adds 11 / 411 / 9.96 + 0.46. Name-based tier S clears none of the 640: `run_story` (which calls `_attempt`) is referenced from outside the module in all 154 closures (through `aisef2/app/run.py`). | `fix2/D5/cost3.py`, `cost.py` (S2.closure at HEAD) |
| M9 | Baseline costs: per mutant median 5.8 s / p90 226 s; per target median 180 s / p90 2,900 s; `run.py::execute` alone 36.55 serial-h; one-line `bundle_cli._create` staled 45 targets / 1,659 mutants / 41.87 serial-h vs a function-granular lower bound of 187 mutants / 4.86 serial-h. Generator edits would invalidate ~17,322 mutants; a `calibrations.py` edit would expose 353 targets / 9,379 mutants / 181 serial-h to a truthful closure rule. | `MUTATION-IMPACT-BASELINE.md` §0, §3, §7 |
| M10 | The v2.1 positional audit file was **rewritten, not appended**. In 7 of its 11 commits the previous version is not a prefix of the next. `abbd88b5` changed 5 `bundle_cli._journal` entries (index 30/38/45/46/47) by editing **only** `source_sha256` (`c15d5b10…`→`0fdfc022…`); the grounds bytes did not change. 197 of the 557 entries cover no current survivor (185 sit at a digest the target no longer has; 12 are no longer survivors). All 360 current survivors are covered. Review strength is free text: 313 `one-blind`, 63 `two-blind`, 46 `carried:remapped`, 2 "NOT two-blind; pending independent re-verification", 130 with none. | git history of `closure-evidence/v2/v2.1/mutation/SURVIVOR-AUDITS.json`; `mutation.py:1465-1539` |
| M11 | The runner measures in a copy of `mutation.COPY` only (`mutation.py:1543-1547`, `_pristine` `:1847-1866`, `tree_sha256` = digest of that copy). Its environment keeps no `PYTHONPATH` and gets a fresh `HOME` (`:1804-1806`, `:1938-1943`). None of the 146 committed versions of `mutation.py` put `validation/qualification/` in COPY, nor any `tests/` path outside `tests/v2/`. `test_v21_pm8_diagnostics.py:878-879` skips its `authority_limits` test in the runner tree for exactly this reason. | `git log -- validation/v2/mutation.py` (COPY of every version) |
| M12 | The README shipped in `v2.2.0`'s wheel and sdist (`release_rc.SHIPPED`, `release_rc.py:73`, which also makes it the PyPI long description) is the **2.1** README: `v2.2.0:README.md:12,19,27` say "AISEF 2.1" and `pip install aisef==2.1.0`. The 2.2 README landed on master after the tag (`55f5e368`, 2026-11-21, not an ancestor of `v2.2.0`). | `git show v2.2.0:README.md`; `git branch/tag --contains 55f5e368` |
| M13 | `story_runner.py::_attempt` (9.75 h, the longest W1a target) has `test_c2_k_nowork_001.py` and `test_c2_orchestration_conformance.py` in its kill set. So the `sealing_gate.py` edit and the `version_forward.py` edit re-open it in **W1a**, before E5 touches it. W1a ∩ E5-upper = 41 targets. | `mutation.TARGETS[...::_attempt]`; `cost3.json` |

**M4 corrections (lane D4):** the 13 failure lines are spread over **11 of 18** GATED entries (2 are Q0 subtests); `currency_dag.py --check` exits 2 from argparse (only `--json` exists) — its real verdict is rc 1 with 5 problems; a re-shaping (not comment-only) edit also moves `execution_order`.

**Conclusion from M4:** under the current coupling, E5 (or any W2–W5 kernel edit) turns the sealing tier red until a
release-time regeneration — the exact v2.2 NO-GO pattern ("10 cross-record-currency fails"). F5 must therefore cover
**rounds** (historical evidence replays at its own release; the branch is gated by input identity), not only
mutation targets. That is the incremental-qualification architecture the owner ruling requires for EVID-COUPLING-01.

## 2. F5 — evidence identity and states

### 2.1 States (the only four; every consumer prints the state and its basis)

| State | Meaning | Gate |
|---|---|---|
| `MEASURED` | Measured **in v2.3** by the F5-aware runner; every recorded identity component equals the one recomputed now. | passes |
| `VERIFIED_REUSE` | Not measured in v2.3. Reused because the engine **re-derived now** that every impact input the evidence depends on is unchanged since the evidence's basis point (or differs only outside its proven impact set). Carries `basis` + the list of compared components. `source_sha256` and audits stay at the measured digest. | passes |
| `INVALIDATED` | An impact input changed inside the impact set, the record differs from its committed bytes, or the platform does not match the claim. Carries the first reason. Must be re-measured. | fails |
| `UNRESOLVED` | The engine cannot compute an identity (no git history / shallow clone, basis commit missing, unparsable source, malformed record, unknown platform). Never treated as current. | fails |

Never: a reused verdict reported as `MEASURED`; a stored "reuse" claim trusted without re-derivation; a new state
added by a lane. A legacy (pre-v2.3) record can never be `MEASURED` — it was not measured in v2.3.

### 2.2 Identity components (impact inputs)

All file digests are sha256 of LF-normalised bytes (same convention as `source_digest`, so a CRLF checkout compares
equal). Segments are the **exact source text** of top-level statements (`ast.get_source_segment`, decorators
included), not `ast.dump` — stable across CPython 3.11–3.14.

| # | Component | Computed as | A change means |
|---|---|---|---|
| I1 | **Target slice** | the target's top-level segment + every same-module segment it reaches by name reference (transitively) + `<imports>` + module-level statements | `INVALIDATED` |
| I2 | **Product code in the closure** (every non-test `.py` of S(F), including the target module's other segments; this is wider than reach.SCOPE, `reach.py:124`) | For each file, call `validation/v21/reach.changed(basis_src, now_src)` (do not copy it). It returns `names`: defs whose own code (the body) differs. It returns `module`: the import-time statements (decorators, defaults, non-deferred annotations, class bodies, module statements, docstring). Each change is judged per kill file F by §2.9. | If any §2.9 rule fires for any F of the target, the target takes that rule's state. Otherwise it is reusable: tier S lists the change in `basis.unreferenced_changes`, tier R in `basis.unreached_changes`, plus `basis.observation = {F: sha256(O(F))}`. |
| I3 | **Kill set** | recorded `kill_tests` vs current `TARGETS[target]` | recorded ⊆ current **and** every KILLED mutant's `killed_by.file` ∈ current → reusable (basis `kill-set-superset`); a dropped killer → `INVALIDATED` |
| I4 | **Kill-test closure + observed reads** | S(F) (§2.9 D2) at basis ∪ now; tests/ files are segmented as before. O(F) (§2.9 D3). | A changed or removed existing segment of a tests/ file in S(F) → `INVALIDATED`. Added-only segments → `additive-test-change`, **iff** R2–R5 fire for no kill file of the target. A test file that another kill file reads as data, lists or discovers is not additive for that kill file. |
| I5 | **Generator** | output equivalence: descriptions **and** mutated target-slice text of every mutant, generated at the basis (basis-commit `mutation.py` generator + basis enum modules) and now (current generator + current enums) | any difference → `INVALIDATED` |
| I6 | **Platform** | `C(t)` above vs the entry's family. A v2.3 entry carries `identity.platform.family`; a legacy entry gets its family from the D3.3 derivation, re-derived at every check. A stored label is never trusted. | family ≠ `C(t)`, or contradictory evidence → `INVALIDATED`. No evidence → `UNRESOLVED` |
| I7 | **Provenance / tamper** | canonical-JSON digest of the record entry vs the same entry at its basis commit (legacy: `v2.2.0`; v2.3: the commit that first added it) | differs → `INVALIDATED ("record entry differs from its committed bytes")`; uncommitted v2.3 entry at gate time → `UNRESOLVED` |
| I8 | **Authorization** | an owner-ruled reuse (Option C) is honoured only if the ruling file's sha256 equals the digest pinned in the engine and its scope (targets, transition, platform) matches | otherwise not a basis |
| I9 | **Runner settings** (W0-freeze correction) | digest of the runner's verdict-affecting constants and code at the entry's basis (`measured_on` for v2.3 entries; `v2.2.0` for legacy) vs now: `TIMEOUT`, `BRACKET`, `ENV_KEEP`, `_FRESH`, `SETTLE_S`, `CLASSES`, and the segments of `_run_file`, `_classify`/classification, `_confirmed`, `null_mutant`, `_env` in `validation/v2/mutation.py` | any difference → `INVALIDATED (I9)`. **Constraint:** W1's own `mutation.py` edits MUST NOT touch any I9 component (else every target re-opens); N33 |

**Tier C (copy scope, lane D5).** * I2 and I4 MUST be computed over **closure ∩ COPY-at-measurement**. A file outside the runner's COPY roots was absent from the tree the verdict was measured in (the entry's `tree_sha256` digests exactly that copy), so a change to it is not an impact input for that entry.
* New v2.3 entries record `identity.copy`. Legacy entries use the COPY of HEAD's `mutation.py`, which is a superset of every historical COPY (M11).
* The §2.7(1) read-set sample MUST also show that no kill file opens a repository path outside its own tree. A kill file that does is `UNRESOLVED` until it is declared.
* Effect, measured: every `validation/qualification/*` edit and `tests/installed_product_smoke.py` re-open **0** targets. Without tier C they re-open 21–31 targets, up to 58.21 rows-h.

`identity.python` (CPython version) and the runner's `tree_sha256` are recorded for new runs as **provenance only**
(the platform claim is OS-family; I5 output equivalence makes the generator interpreter-independent). If W1
measurement shows `ast.unparse` output differs across the CI Python versions for any target, I5 already reports it.

### 2.3 Decision procedure (fail-closed, first failing rule wins)

1. A malformed record or a consistency problem is reported as today: every existing `_problems_v2` / `target_problems` rule except the **source-currency rule** (`mutation.py:2524-2526`, `:2578-2580`). F5 replaces that rule whenever a state is supplied. Keeping it would make `VERIFIED_REUSE` unreachable, because a whole-file digest mismatch fires before the engine is consulted.

**Source rule (normative, `validation/v2/mutation.py`):**

```python
def state_problems(name, s):                      # s: validation/v23/impact.State
    if s.state in ("MEASURED", "VERIFIED_REUSE"):
        return []
    if s.state == "INVALIDATED" and s.component in ("I1", "I2"):
        return [f"{name}: target changed since the mutation run — re-run it"]   # today's text, byte for byte (M6)
    return [f"{name}: {s.state} ({s.component}): {s.reason} — re-run it"]
```

- `_problems_v2(t, root, state=None)` and `target_problems(t, root=ROOT, state=None)`:
  - `state is None` MUST execute lines 2524-2526 / 2578-2580 verbatim. That covers every direct caller: unit tests, Q0's known-bad `target_problems(run_target(...), root)` at `checker_calibration.py:338`, the frozen per-phase builders (`c2_*`, `s2_/v21_mutation_record`), `p3_evidence.py:551`, and the v2.2 replay.
  - Otherwise MUST use `out += state_problems(name, state)`.
- `problems_of(record, root=ROOT, phase="P1", states=None)` passes `states.get(target)`. A target missing from `states` is `UNRESOLVED ("no F5 state computed")`, never a pass.
- `check(root=ROOT, *, states=None)` computes `states = impact.states(root, live)` when `None`. That makes `mu.check(ROOT)` (Q0 clean, `checker_calibration.py:326-327`), `c2_orchestration_repair.py:512,713` and `q2.py:73` engine-backed. The engine never raises: no git, a toy root, or a missing basis gives `UNRESOLVED`. Existing toy tests that call `m.main(["run", …])` assert only rc 3 / `!= 3` or `WARNING`-prefixed lines (`test_v21_mutation_runner.py:533,1592,1622,1961`), so they stay green.
- The state table is printed by `--check --states` (JSON). The legacy text stays in `check()`.
2. Basis unavailable (git missing, shallow, basis commit absent) → `UNRESOLVED`.
3. I7 tamper → `INVALIDATED`. 4. I6 platform → `INVALIDATED`/`UNRESOLVED`.
5. New-format (v2.3) entry: `MEASURED` only if the recomputed I1–I5 and I9 equal the recorded identity **and** the §2.9 rules R0–R8, run with basis = the entry's `measured_on`, fire nothing (so a data read, listing or child of a kill file is judged for v2.3 entries too). Otherwise continue with rule 6 using `measured_on` as the basis.
   **"Now" is HEAD:** every comparison reads `HEAD` (git), and any `mutation.COPY` path whose working-tree bytes differ from `HEAD` (or is untracked inside a COPY root) makes every target `UNRESOLVED ("dirty tree: <path>")` — an uncommitted edit can never be reported as current (N32).
6. Otherwise compare basis vs now: I1 changed → `INVALIDATED`; I3 dropped killer → `INVALIDATED`; I4 test file
   changed → `INVALIDATED`; I5 differs → `INVALIDATED`; I9 differs → `INVALIDATED (I9)`; any §2.9 rule fires (in its rule order) → that rule's state.
7. All unchanged or only unreferenced I2 changes → `VERIFIED_REUSE` with `basis` = `v2.2.0-accepted@da3ea33f` /
   `ruling:<id>@<sha>` / `v2.3-measured@<commit>`, plus `compared: [I1..I9]` and `unreferenced_changes`.

`mutation.check()` keeps its exact message for a changed target ("target changed since the mutation run — re-run
it") so the Q0 render does not move (M6); the state table is a separate output (`--check --states`, JSON).

### 2.4 Legacy evidence (v2.2 and earlier) — what is claimed and what is not

* Basis = the `v2.2.0` release commit `da3ea33f`, where the owner-approved release gate accepted every live entry
  (mutation `--check` PASS, BASELINE.md). Rule 7 labels them `VERIFIED_REUSE (v2.2.0-accepted)` — never `MEASURED`.
  The 42 Option C targets carry `basis: v2.2.0-accepted via ruling AISEF-V2.2-B1-MUTATION-EVIDENCE-REUSE-RULING`.
* From the basis forward every impact input I1–I9 is bound. **Before** the basis, legacy records carry no kill-file,
  generator or platform identity; that pre-basis window is a declared limitation (no retro-tagging — F5 map §8). M2
  bounds it: 0 legacy targets lost a kill file; 8 gained one.
* Platform: the frozen provenance table of the first draft is **withdrawn** (it was wrong for V2.1); platform is derived per entry from evidence, below.

#### 2.4.1 What v2.2.0 actually claimed (measured, base `1bf5dd2f`)
* v2.2.0's mutation claim is **POSIX (Linux + macOS)** for every non-Windows target, plus **native Windows** for the 3 liveness targets. Sources:
  * ruling `B1-MUTATION-EVIDENCE-REUSE-RULING.json:605` says "All mutation measurement is POSIX";
  * `:622` limits the scope to "the c15d5b10 -> 0fdfc022 transition on POSIX";
  * `:49` says "Freshly re-measured on POSIX";
  * `V2.2.0-STATUS.json:20,:39` say "POSIX/Linux", and `:34` gives Windows 60/60;
  * `README.md:158-159` and RELEASE-DECISIONS seq 9 name no platform for the 177.
* v2.2.0's own 177-target gate holds **3 macOS-measured entries** (`bundle_cli::_create`, `::_journal`, `settings::OPTIONAL`, imported `abbd88b5`, Homebrew CPython 3.14 frames). It holds them alongside Linux entries, `migrate`, and 3 Windows entries.
* "linux" is only the provenance label of the 42 Option C targets (`mutation.py:1574-1576`, ruling `:13`). `VERIFIED_REUSE_PLATFORM` is never read (CODE-AUDIT #14).
* **Withdrawn:** §2.2 I6 "Linux POSIX mutation claim", and the §2.4 table "P1–P6, cycle-2, S2, V2.1, V2.2 B1 → linux". A Linux-only claim narrows what v2.2.0 claimed, and 462 live entries contradict it.

#### 2.4.2 Claim platform (normative)
* `C(t) = windows` for `app/client.py::_is_gone`, `runtime/process_range.py::_win_liveness` and `::pid_alive`. Their kill set is Win32-native (`mutation.py:1296-1298`, taken over into V2.1 at `:1415-1421`).
* `C(t) = posix` for every other target. The claim belongs to the target, not to the host running the check.
* I6 MUST compare the OS **family** only.
* Flavor (`darwin`/`linux`) and interpreter MUST be recorded and printed per entry as provenance. They are never gate inputs.
* A report MUST NOT label a darwin-flavor or flavor-unproven entry "Linux".
* A claim narrower than `posix` is a claim change and needs its own amendment. It would INVALIDATE every darwin entry.

**§2.2 row I6 (replace):**

| I6 | **Platform** | `C(t)` above vs the entry's family. A v2.3 entry carries `identity.platform.family`; a legacy entry gets its family from the D3.3 derivation, re-derived at every check. A stored label is never trusted. | family ≠ `C(t)`, or contradictory evidence → `INVALIDATED`. No evidence → `UNRESOLVED` |

#### 2.4.3 Per-entry derivation (the engine re-derives on the committed bytes, after I7; no frozen table)
The first tier that yields a value wins:
1. **R-family:** a traceback frame in any `tail` of the entry (`results[].files[]`, `t0[]`, `original[]`).
   * `File "<tree>/` means posix; `File "<tree>\` means windows.
   * `<tree>` is the runner's own redaction of its tree root (`mutation.py:2126-2133`), so the separator is the measuring interpreter's `os.sep`.
2. **R-flavor** (posix only): a path token at token start.
   * darwin: `/opt/homebrew/`, `Python.framework/Versions/`, `/Users/<u>/`, `/private/{tmp,var}/`, `/var/folders/`.
   * linux: `/usr/lib/python3.N/`, `/home/<u>/`, `/root/`.
   * Fixture strings MUST NOT count: `C:\Users\x\run1` inside assertions, `<run>/tmp/<mkdtemp>/home/.config`.
3. **W (worker):** a canonical-JSON-identical entry in a committed `closure-evidence/**/mutation-workers/*.record.json`. Its `*.history.json` `log.sha256` and `record.sha256` MUST match the files, and those artifacts MUST carry R markers. The entry then takes that worker's family and flavor.
4. Otherwise the platform is **unknown**, giving `UNRESOLVED (I6: no platform evidence)`.

What does not count:
* **Contradictory evidence** gives `INVALIDATED (I6: contradictory platform evidence)`: both separators in one entry, both darwin and linux markers, or W disagreeing with R.
* **Not evidence, may only be printed as a flavor hint:**
  * co-occurrence with a flavored entry (same `tree_sha256` or the same import commit). `tree_sha256` hashes only path + bytes (`mutation.py:1847-1866`), so it is platform-free;
  * commit messages, such as "local mutation re-run" in `2f7f93bc`;
  * code comments (`mutation.py:252-253`);
  * worker-directory names.
* **I8 (Option C):** the ruling's scope is POSIX (`:622`). Its per-target `platform: linux` is checked only for non-contradiction (no darwin R/W evidence in the entry), together with the pinned tree digest (`mutation.py:1577-1620`).

#### 2.4.4 Measured provenance of the 994 live entries (what `check()` reads, `mutation.py:2595-2622`)

| Record (phase) | live | mutants | R-family | flavor proven (R-flavor/W) | flavor unproven | unknown → UNRESOLVED | other evidence in the repo |
|---|---|---|---|---|---|---|---|
| P1, P2, P3, P4, P5, P6 | 19/32/41/68/45/78 | 1,151/1,069/1,752/1,292/1,232/2,753 | none (rows hold only `killed`/`survivors`) | 0 | 0 | 283 | header has only `record`/`tool`; no worker artifacts; only committer statements ("local") |
| C2-ORCH, C2-P10 | 5/39 | 134/695 | none | 0 | 0 | 44 | same as above |
| V2.1, macOS campaigns (c2–c9, mw0/mw1, sw, l-ord; imports `8fae707b`, `879a234b`, `dc63478c`, `eaa5e4cc`, `70a5badf`, `42e03052`) | 460 | 10,517 | 460 posix | 459 darwin (124 R + 335 W) | 1 (`confine::_sections`) | 0 | every worker log/record is darwin (CPython 3.14.7 Homebrew); 36/36 history digests match |
| V2.1, B1-era imports (`352aaac9`, `a60137b1`, `b1fb8580`, `7546401d`, `abbd88b5`) | 207 | 6,805 | 204 posix + 3 windows | 62 linux (CPython 3.12 `/usr/lib`, `/home/<u>/…/w3`) + 2 darwin | 140 (138 with a linux hint, 1 with a darwin hint, `migrate`) | 0 | server logs not in repo; `B1-LINUX-AGGREGATE.json` does not exist |
| **Total** | **994** | **27,400** | 664 posix + 3 windows | 461 darwin, 62 linux | 141 | **327** (10,078 mutants) | — |

Subsets:
* **177-target gate:** posix 174 (2 darwin, 49 linux, 123 flavor-unproven) and windows 3.
* **Option C 42:** all 42 posix. Flavor: 9 linux, 33 unproven, 0 darwin, so non-contradiction holds 42/42.
* **Not read by `check()`** (`PHASE_TARGETS` empty; replay only): C2-P1..P4, K-PRESAT-001, K-NOWORK-001, V2.0-S2 and V2.2-B1-LIVENESS.
  * V2.0-S2 has no rows; workers A–K9/RC2A/RC2B carry no markers, and `RC2-finalize.log` has 2 darwin markers.
  * V2.2-B1-LIVENESS has `<tree>\` frames, so it is windows.
  * `WAVE1-MUTATION.json` is not in `RECORDS` and is macOS (`environment_guard` PATH `/opt/homebrew/bin`).

#### 2.4.5 UNRESOLVED set and how it is resolved
* **327 entries are `UNRESOLVED (I6)`:** P1–P6, C2-ORCH and C2-P10, 10,078 mutants. None of them is in v2.2.0's 177-target gate. v2.2.0 carried them by `--check` currency only, never under a platform claim.
* **Owner-free resolution: re-measurement only** (→ `MEASURED` with `identity.platform`).
  * §2.5 changes from "measure INVALIDATED or new" to: the runner MUST measure `INVALIDATED` ∪ `UNRESOLVED(I6: no platform evidence)` ∪ new targets. Other UNRESOLVED causes, such as a shallow clone, are fixed in the environment, not measured.
  * The 327 join W1's single targeted run, after the W1a negative tests. Scope and cost MUST be printed in the W1 report before that run.
  * Cost **[E]**: 16.2 serial-h at the V2.1 per-mutant median (5.8 s) up to 182.5 serial-h at the V2.1 mean (65.2 s per mutant). None of their modules appears in V2.1, so no closer estimate is possible. This is **not** inside §10's "3–6 h".
* **Owner-only alternative:** an I8-pinned ruling for exactly these 327 targets accepting "platform-unbound v2.2.0 currency". State `VERIFIED_REUSE`, basis `ruling:<id>@<sha>`, report line `platform: unbound`. Without such a ruling, the re-measure default applies. No fifth state and no allowlist.
* **Owner-free reuse covers all 667 V2.1 entries:** 664 under `posix` and 3 under `windows`, entirely from row and worker evidence.

#### 2.4.6 Env binding
**New v2.3 entries.**
* They record `identity.platform = {family, sys_platform, release, machine}`.
* They record `identity.env = {python: sys.version, implementation, env_keep: ENV_KEEP, fresh: sorted(_FRESH), timeout: TIMEOUT, settle_s: SETTLE_S, bracket: BRACKET, copy: COPY, tree_sha256, runner_sha256}`, where `runner_sha256` is the LF-sha256 of `mutation.py`.
* Host paths stay redacted.

**Rule 5 (`MEASURED`).**
* It MUST also require `identity.env` to equal the values recomputed now.
* A difference in an **I9 key** (`TIMEOUT`, `SETTLE_S`, `BRACKET`, `ENV_KEEP`, `_FRESH`, classification code) → `INVALIDATED (I9)`, never a demotion. A difference only in the interpreter version or OS flavor/release/machine demotes the entry to `VERIFIED_REUSE` with basis `v2.3-measured@<commit>` and `env_differs: [keys]` (provenance; I6 still gates the family).
* Interpreter version and OS flavor are provenance only; the runner's verdict-affecting settings are impact input **I9** (§2.2) and DO invalidate. Only `family` gates platform (I6).

**Legacy entries:** env is **not bound**; see limitation 4.

### 2.5 New v2.3 measurements

* **Record.** `V23_REL = "closure-evidence/v2/v2.3/MUTATION.json"`, `{"record", "tool", "entries": [...]}`. Each entry is a runner-2 result plus `identity` (§2.5 bullet 2) plus `supersedes: {path, entry_sha256}` (the canonical-JSON digest of the entry it replaces).
* **Not added to `RECORDS`, `PHASE_TARGETS`, `SUPERSEDED` or `V21_TARGETS`.** Import-time tables MUST stay byte-identical. Measured blockers:
  - `test_v21_mutation_record.py:27` requires V2.1 to be last in `RECORDS`.
  - `:28-36` requires every S2 target to stay in `V21_TARGETS`. All 11 `story_runner.py` targets are S2 targets living in V2.1, so a takeover would break it.
  - GATED `test_v21_mutation_runner.py:1692-1694` requires every non-V2.1 `RECORDS` phase to carry no `runner` key.
  - `q2.py:74-75` reads every `RECORDS` path with no existence check.
  - `p6_evidence.py:80` lets the last record listing a target win.
* **Supersession is read-time.**
  - `v23_newest(root)` gives, per target, the last entry present in `git show HEAD:<V23_REL>`.
  - Committed entries MUST be a prefix of the working list. A target whose newest entry is uncommitted is `UNRESOLVED` (I7) and never falls back to an older entry.
  - `check()` substitutes `v23.get(t["target"], t)` into each phase record before `problems_of`. Phase-record bytes are never touched; replaced entries are history.
  - A v2.3 entry for a target not in `TARGETS ∪ V23_NEW_TARGETS` is a problem.
  - New targets (`aisef2/plan/obligation.py`) go in `V23_NEW_TARGETS`, outside `PHASE_TARGETS`/`TARGETS`. `check()` requires a v2.3 entry for each ("… has no mutation result").
* **Writer.** `--run-affected` MUST only append (prefix rule); the existing `run` phase loop never writes `V23_REL`.
* **FS-4.** `_pristine` (`mutation.py:1851`) MUST also exclude `V23_REL` and `V23_AUDITS_REL`.
* **Audits.** Survivors of re-measured targets are audited in append-only `closure-evidence/v2/v2.3/SURVIVOR-AUDITS.json`. `audits_at`/`audit_of` (`:1497`, `:1535`) read both files; the positional key includes `source_sha256`, so keys cannot collide.
* **Staged cut-over (resolves the D3/D4 interaction):** `check()` becomes engine-backed only once every live target is `MEASURED`/`VERIFIED_REUSE` — before that, the 327 `UNRESOLVED (I6)` targets would turn Q0's mutation clean (`mu.check(ROOT)`) red. Until the cut-over, `check()` keeps the v2.2 rule unchanged (no weakening) and the F5 gate is `--check --states` (CI `mutation-incr` job), which fails truthfully. The cut-over commit lands with the measurements (or the owner ruling) that clear the 327.
* Each entry adds `identity = {platform, python, measured_on, dirty, slice, closure:{path:sha}, kill_files:{path:sha},
  generator:{descriptions_sha, mutated_slices_sha}, enum_modules:{path:sha}, platform:{family, sys_platform, release, machine}, env:{…}}` — platform/env exactly as §2.4.6. `measured_on` = `git rev-parse HEAD`;
  a run from a dirty tree records `dirty: true` and can never become `MEASURED` (it is `UNRESOLVED` until re-run).
* The runner measures **only** `INVALIDATED` ∪ `UNRESOLVED (I6: no platform evidence)` ∪ new targets (other UNRESOLVED causes, e.g. a shallow clone, are fixed in the environment, not measured). `mutation.py` gains
  `--affected` (print the INVALIDATED set with reasons, measure nothing) and `--run-affected` (measure exactly it).

### 2.6 Rounds — historical evidence vs the v2.3 branch (F5-ROUND, lane D4)

**Selection model (supersedes "selection key = declared input identity").** The design keeps every v2.2 check's own strictness and changes only *selection*.

- In round v2.2, a record is chosen by `(round, HEAD:aisef2)` (`version_forward.py:144-171`).
- In round v2.3, the record is the **verified head of its own chain**, and currency is the node's unchanged v2.2 check function run in round v2.3.
- This is sound because every node check either re-derives its body and compares exactly, or carries its own identity guard (table below). The kernel-tree selection was the only guard for none of them.
- A per-file declared-input inventory is therefore not needed, with one exception (P5-FALSIFIABILITY, below).

**`validation/v2/version_forward.py`.** `CURRENT_ROUND = "v2.2"` stays; it appears in Q0 messages and v2.2 bodies. The changes:

- New `ROUND = ContextVar(default=CURRENT_ROUND)`, `BRANCH_ROUND = "v2.3"`, and `in_round(r)` (a context manager).
- `load_series` (`:186-195`): in v2.3 it appends `closure-evidence/v2/v2.3/<stem of v22_rel>-<k>.json`, k = 1…, in k order. Otherwise unchanged.
- `select_for_tree` (`:144-171`): in v2.3 it runs `validate_chain`, then returns the last element if it is a non-base record whose digest recomputes. A base-only series raises `LookupError("no record in the series of <base> for round 'v2.3' …")`. The `version_context`/`kernel_digest` arguments are ignored in that round. A head is never chosen across series. The default round runs today's code, so the messages at `:167-168` stay byte-identical.
- `write_supersession` (`:198-218`): in v2.3 the predecessor is the head. Output goes to the next `-<k>.json` with `open(…, "x")`. It binds `version_context "v2.3"`, `source_commit` = HEAD, and `kernel_digest` = HEAD:aisef2 (provenance only). A body equal to the head's writes nothing.
- `validate_chain` (`:116-119`): v2.3 blocks are de-duplicated on `(version_context, source_commit)` with their own message. The v2.2 key and message are unchanged.
- `check_supersession`, `resolve_upstream`, `current_context` and `bind` stay byte-unchanged. They become round-aware only through `select_for_tree`/`load_series`.

**`validation/v2/currency_dag.py`** (fan-out 0):

- `validate(root=ROOT, *, kernel_digest=None, round=None)`, with `round = round or ("v2.2" if kernel_digest is not None else "v2.3")`.
- Round v2.2 runs `:106-140` verbatim. Q0's known-bad `validate(ROOT, kernel_digest="f"*40)` (`checker_calibration.py:190`) therefore renders byte-identical text, including `round 'v2.2'`.
- Round v2.3 works as follows:
  - Nodes are visited in topological order.
  - For each node it runs `CHECKS[nid]` under `vf.in_round("v2.3")`.
  - An exception gives `UNRESOLVED`.
  - A dependency not in {MEASURED, VERIFIED_REUSE} gives `INVALIDATED ("upstream not current for round 'v2.3': …")`.
  - Problems give `INVALIDATED` with the first problem.
  - A pass gives `MEASURED` when the head is a v2.3 record, else `VERIFIED_REUSE` (basis `v2.2.0-accepted@da3ea33f; re-checked in round v2.3`).
  - Q0's clean `validate(ROOT)["problems"]` takes this path.
- `main` gains `--round v2.2 --kernel TREE` and `--affected`. Note that `--check` has never existed (`:150`).
- `OWNER_GATED` is unchanged.

**Nodes** (all 10 checks run at 1bf5dd2f with an audit hook: all PASS).

| Node | `CHECKS` (owner fn, run in v2.3) | reads story_runner (measured) | own identity guard | W1a state [derived] | after E5 [derived] | re-derive (existing writer under `in_round`) |
|---|---|---|---|---|---|---|
| P5-PROPOSAL | `p5_acceptance.check_v22_proposal` | no | full re-derive | VR | VR | — |
| P5-FALSIFIABILITY | `p5_falsifiability.check_v22` | no; derivation parent: 228 files, no `aisef2/orchestrate`, 1055 s | `aisef2_tree == HEAD:aisef2` (`:499-500`) | VR | **INVALIDATED unless edited** | edit (below); else `write_v22` (1055 s), which cascades PLAN and P5-REVERIFICATION (bodies embed fals path and sha) |
| P5-REVERIFICATION | `p5_acceptance.reverification_v22_problems` | no | re-derive; recorded `GUARDS` (`:552-556`) are Q0 checkers or Q0 itself, checked live by gate 3 | VR | VR | — |
| PLAN | `c2_plan_correction.check_v22` | no | re-derive | VR | VR | — |
| K-NOWORK | `c2_k_nowork_001.check_v22` | yes | BOUND bytes + kernel content digest (`:471,478`) | VR | INVALIDATED | `write_v22`, no edit |
| CONFORMANCE-RULING | `v21_conformance_ruling.check_version_forward` | yes | rows bound by LF sha (`:349`); the v2.2 rows include `validation/v2/mutation.py` and `story_runner.py` | **INVALIDATED (W1a mutation.py edit)** | INVALIDATED | **edit + STOP ROUND-AUTH** |
| ORCH | `c2_orchestration_repair.release_differences_v22` | yes | checker-only (`:659-725`) | INVALIDATED via the ruling | same | none; passes once the v2.3 ruling head names the bytes |
| P10-PROFILE | `c2_p10_profile.check_version_forward` | no | re-derive | VR | VR | — |
| P10-COHORT | `c2_p10_cohort.check_version_forward` | yes (census of 5,687 files) | re-derive; body = census result + digests of cohort sources only | VR | VR | `write_v22` if the body ever differs |
| Q5 | `v21_q5_compare.check_v22` | yes | `bindings` (kernel content digests) | VR | INVALIDATED | `write_v22` (commit-then-verify), no edit |

Required owner-script edits:

- **`v21_conformance_ruling.py`** (already in the L1-QUAL list):
  - v2.3 row reasons for `mutation.py` (F5 hunk) and `story_runner.py` (E5).
  - An authority block quoting the v2.3 ledger entry verbatim.
  - `tolerated_v22()` (`:289-297`) reads the round's chain head through `vf.load_series`/`select_for_tree`, not `V22_REL` directly. ORCH's `release_differences_v22` then works unchanged under `in_round`. The `select_for_tree` call at `:516` is already head-aware.
- **`p5_falsifiability.py`** (recommended, to stop the cascade): in round v2.3, `check_v22` replaces `:499-500` with: the LF blobs of `s2_mutation_record.closure(ROOT, rev, ("validation/qualification/p5_falsifiability.py",))` (98 files, no `story_runner.py`; called, not edited) plus the measured data inputs (workload fixtures and mutants) are equal at the record's `source_commit` and at HEAD.
  - Declared limitation: the parent read set is the audit hook's; the 20,385 children (`python -P …/aisef2/runtime/range_anchor.py`, git) are covered only statically. The static closures of `range_anchor` and every probe module exclude `aisef2/orchestrate/story_runner.py` (measured).

Other node scripts stay byte-unchanged: `c2_plan_correction`, `c2_k_nowork_001`, `c2_p10_*`, `v21_q5_compare`, `c2_orchestration_repair`, and `p5_acceptance` unless the cascade happens. NEW `validation/v23/rounds.py write NODE` runs the node's existing `write_v22*` under `in_round("v2.3")`, in topological order, with P10-COHORT last.

**Q0 byte-identity (exit gate 3).** On an *earlier* E5-shaped probe (`_attempt` body under try/finally, `import enum`, `Stage` IntEnum, `_Stages.advance`, committed in a copy; HEAD:aisef2 04c55b6a — not the final §4 shape, which has no `finally` and a plain `Enum`; `test_v23_q0_byte_identity` (ii) MUST be re-run on the real E5 commit before gate 3 is claimed), exactly 4 of 57 entries move. Each MUST be fixed as stated:

| Entry | Moves because | Fix |
|---|---|---|
| mutation clean | 11 story_runner targets "target changed" | F5 source rule + v2.3 entries for the INVALIDATED set (all 11: E5 adds an import, which is in every I1 slice) |
| currency_dag clean | 5 nodes "no record declared for round 'v2.2' binds this tree" | round-v2.3 path above (needs ROUND-AUTH) |
| b1_bindings known-bad `observed[0]` | `"kernel 04c55b6a72de is not the frozen 000000000000"`: `b1_bindings_check.py:17-20` reads the live tree | `problems(man, targets=None, *, kernel=None)`. `checker_calibration._b1_bindings` known-bad passes `kernel=git rev-parse da3ea33f:aisef2` (= e865d65c), the B1 manifest's own round. Clean (`:181`) unchanged. |
| execution_order clean | `null_mutant` digests of re-shaped targets leave the T0 sweep (`execution_order.py:64`); "EXECUTION-ORDER-9.json is not what T0-SWEEP-8.json derives now" | `table(…, at=None)` / `check(table_path, *, at=None)` read sources at `at`. Q0 clean and known-bad pass `at=V2_2_0`, the round the -9 table serves. The known-bad message is identical, since it names `T0-SWEEP-8`. A v2.3 table, if any run uses one, is checked live in NEW tests. |

- The other 53 entries were byte-identical on the probe, including kernel_static_checks, except_boundaries, old_path_audit/release_inventory, arch_catalog, migration_table, invariants_doc, cycle2_baseline and freeze_manifest.
- `version_forward` Q0 is untouched: `CURRENT_ROUND` and the v2.2 `validate_chain` are unchanged.
- No new `validation/v2/*.py` file may be added (`checker_calibration.py:610-613`).
- The real E5 MUST add no `enums.VOCABULARIES` member and no event type. Any other moved entry is STOP Q0-1.
- **Verdict:** byte-identity is mechanically feasible for every checker. Q0-1 is not triggered.

**Sealing-GATED tests (all 18 files byte-unchanged; only `tests/v2/sealing_gate.py` edited).**

- New `V22_REPLAYED` (11 ids).
- `sealing` becomes a function: the id is built from the repo-relative path of the defining module's `__file__` plus `__qualname__`. Do not use `__module__`: `discover -s tests` yields `v2.test_x`.
- Replayed ids get `unittest.skip("round v2.2 history: replayed at v2.2.0 …; round v2.3 = tests/v2/test_v23_rounds.py")`; all others keep `skipUnless(SEALING)`.
- `test_sealing_gate.py`'s AST closure still holds.

| Runs at HEAD (7) | Why it holds across W1 |
|---|---|
| `p0/test_checker_calibration::CheckerCalibration` | gate 3, per the table above |
| `p0/test_destructive_authority::Checker.test_this_tree_passes…` and `p5/test_invariants::MutationAuthority…` | live-tree; L1-AUTHCHK MUST keep `da.check == []` |
| `p0/test_freeze_manifest::…V2_007…` | git-history facts; only ledger seq 4 is read |
| `test_c2_orchestration_conformance::Record.test_15b` | fully mocked (`tolerated_v22` mocked) |
| `test_cycle2_wp201::Baseline…` | binds cycle-2 files W1 does not edit |
| `test_p9_reproduction::…Q5_18…` | synthetic, derived bindings |

| Replayed at v2.2.0 (11) | Why it cannot run at HEAD |
|---|---|
| PlanCorrection, k_nowork Record, orchestration `test_15`, p10_cohort Record, p10_profile Checker, p5 Acceptance, p5 KernelProvenance, P5_8, Q5_19, conformance CommittedRuling | v2.2-round binding by HEAD tree; red on any kernel or ruling-row edit (blast: all failed on a comment) |
| `test_v21_mutation_runner::Classify.test_historical_records_read_as_before` | whole-file legacy rule via `problems_of` without states (`:1697`). L1-AUTHCHK edits `validation/v2/except_boundaries.py`, which carries 9 live P5 targets. |

- **Replay:** NEW `validation/v23/replay_v22.py`:
  1. `git clone --shared --no-checkout ROOT T`, then `checkout --detach da3ea33f`.
  2. Run `AISEF_SEALING=1 python -P validation/v2/owned_run.py -- python -m unittest <ids>` with opencode absent from PATH and scratch XDG directories.
  3. Exit non-zero on any failure.
- Measured: all 18 GATED tests at v2.2.0 rc 0 in 360 s (macOS, CPython 3.14); clone checkout 1.8 GB.
- A gated NEW test in `test_v23_rounds.py` calls the replay.
- Cheap in-tree companion check (no clone): `currency_dag.validate(ROOT, kernel_digest=<da3ea33f:aisef2>)["problems"] == []`, which proves v2.2 selection over the committed records is intact under HEAD's mechanism.

**NEW tests** (no existing test file edited, §2.8).

`tests/v2/test_v23_rounds.py`:
- one gated test per node asserting its v2.3 state ∈ {MEASURED, VERIFIED_REUSE};
- red-before cases per node in a copy: tampered head (`record_digest`); one guarded input byte changed (story_runner for K-NOWORK/Q5/CONF; a probe source for P5-FALS; `aisef2/plan/obligation.py` for P5-PROPOSAL) gives INVALIDATED; a broken link gives UNRESOLVED;
- an always-VERIFIED_REUSE mutant of `_validate_v23` is rejected;
- `V22_REPLAYED ⊆ GATED`, each id has a v2.3 counterpart, and the replay step is wired.

`tests/v2/test_v23_q0_byte_identity.py`:
- **(i) in-tree, cheap:** for currency_dag, version_forward, mutation, b1_bindings and execution_order, `calibrate(make())["observed"]` equals the committed record's.
- **(ii) gated copy test, steps:**
  1. Refuse if the tracked tree is dirty.
  2. `clone --shared` + `checkout --detach HEAD`.
  3. Append `\n# v2.3 Q0 byte-identity probe: no behaviour\n` to `aisef2/orchestrate/story_runner.py` and commit inside the copy.
  4. Run Q0 in a subprocess in the copy.
- **(ii) red-before assertions:** the render differs from the committed record only in the currency_dag entry and `calibrated_count`. The clean problems name exactly CONFORMANCE-RULING, K-NOWORK, Q5 and ORCH (plus P5-FALS, PLAN and P5-REVERIFICATION if the p5_falsifiability edit has not landed). The mutation entry is identical: a comment changes no segment, so all 11 targets are VERIFIED_REUSE. b1_bindings and execution_order are identical.
- **(ii) re-derive and final assertions:**
  1. Run `rounds.py write` for each listed node in the copy, committing each record.
  2. Assert `render(run())` == `(ROOT/OUT_REL).read_bytes()`.
  3. Assert `checker_calibration.py --check` rc 0.
  4. Assert `mutation.py --check --states` shows 0 INVALIDATED/UNRESOLVED.
  5. Assert ROOT's `git status --porcelain` is unchanged.
- **(ii) status and cost:** red until ROUND-AUTH exists (the CONF writer refuses), which is truthful. Cost: 2 × Q0 at 263–279 s (measured) plus K-NOWORK/Q5/CONF re-derivation [E].

### 2.7 Declared limitations (written into the engine docstring and every report)

1–2. Closure, reach and name tiers: see §2.9 (normative). Residuals:
- C code that reads tree files is seen only through `os_trace`.
- A process SIGKILLed between a failed append and the next one loses the `lost` count.
- Hash-only reads (`kernel_digest`, `mechanism_digest` at `registry.py:295`) are data reads. A DIGEST-READ discount would need its own proof and an owner ruling. It is NOT in W1; the stake is given below.
3. Tamper detection is anchored to git history; it proves the entry equals what was committed, not who measured it.
   Signed provenance is A2 (W2), not W1.

4. **Legacy env is unbound.**
   * All 327 legacy entries were imported between 2026-09-21 and 2026-10-01 by runner 1, which does not classify.
   * They ran with `TIMEOUT = 120` (`4afc9d10`). It became 300 at `29860a54` (2026-10-03) and 900 at `55a6b74c` (2026-10-06).
   * They ran before the `ENV_KEEP` allowlist and `SETTLE_S` existed (`e15cad67`, 2026-10-07).
   * V2.1's `tree_sha256` covers `validation/v2` (COPY, `mutation.py:1543-1547`), so it covers the runner constants. Trees are never reconstructed (§8), so this is provenance only.
   * The interpreter is derivable for 176 of 994 entries: 115 darwin CPython 3.14.7, 61 linux CPython 3.12. Verdicts are assumed to be the same across CPython 3.11–3.14.
5. **`posix` means "measured on a POSIX host", not "killed on every POSIX flavor".**
   * At least 5 kill files branch on flavor: `p4/test_process_range.py:439` (`waitid`), `test_v21_kills3_T07b.py:75,87` (`/proc/self/ns`), `test_v21_r3_range_fu_linux_table.py:112` (linux), `test_v21_r3_range_fu_ps_table.py:237` (darwin), `test_v21_r3_conf_policy.py:448`.
   * They are used by at least 38 targets / 1,068 mutants: 16 darwin, 18 linux, 4 unknown. This is a lower bound from a literal scan.
   * A skipped killer reports PASS, so the mutant is SURVIVED and the audit rule catches it. A kill that only happens on one flavor is the declared residue, and the report prints each entry's flavor.
6. **Row evidence depends on tails keeping their traceback frames.** 5 V2.1 entries have no `<tree>` frame: 1 is resolved by R-flavor and 4 by W.

### 2.8 W1's own edits are qualified like any other change (measured fan-out, `w0fix/fan_w1.py`)

Under I2/I4 an edit to an existing file in a kill-test closure re-opens the targets that depend on it. Measured on
`1bf5dd2f` (262 kill files, 994 targets): `tests/v2/test_app_run.py` 81 kill files / 495 targets / 14,804 mutants;
`tests/v2/sealing_gate.py` 5 / 47 / 1,661; `tests/__init__.py`, `tests/v2/__init__.py` every target; a typical single
test file (e.g. `test_v21_mutation_runner.py`, `test_c2_p5_acceptance.py`) 1 / 5 / 497 (one meta kill file names
every `tests/` file by literal); `validation/v2/mutation.py`, `execution_order.py`, `repro_dist.py` 1 / 5 / 497;
`version_forward.py`, `release_calibration.py`, `p5_acceptance.py` 3 / 21 / 1,042; `currency_dag.py`,
`destructive_authority.py` 0. **Rule:** new behaviour gets NEW test files; an existing test file is edited only
additively (I4) unless the lane's deliverable needs a changed segment, in which case `--affected` lists the re-opened
targets and they join W1's single targeted run. No W1 lane edits `tests/v2/test_app_run.py` or any `__init__.py`.

### 2.9 I2/I4 soundness (normative, lane D2)

**D1 Δ.**
- Δ is every path under a `mutation.COPY` root that is added, removed, or whose LF-sha256 differs between basis and now.
- COPY means all ten roots (`validation/v2/mutation.py:1543-1547`), plus `validation/v23` for new runs.
- Every file type counts, and so do comments and whitespace.
- Paths outside COPY are not in the runner's tree (`_pristine`, `mutation.py:1847-1866`). So they are not in Δ, and R0 also covers reads of them.
- Example: `tests/__init__.py` is outside COPY and the runner uses `-t tests`, so it never runs. A change to it is not a dependence; the §2.8 rule "every target" is over-strict here.

**D2 S(F)** is the fixpoint of the following:
- (a) `s2_mutation_record.closure()`, called at basis and at now.
- (b) Literal paths, in **every** file of S(F), tests/ and non-test alike. Note that s2 resolves only tests/ literals to tests/ paths (`s2_mutation_record.py:138-143`).
  - Any file or directory under **any** COPY root, named by one string constant or by consecutive string constants joined as a path (`/`, `os.path.join`, `Path(...)`, f-string literal parts).
  - Relative to the repository root or to a directory above the file.
  - This is the static rule of `v21_snapshot_delta._info/_names` (`:359-410`), reused.
  - A directory adds every file under it.
- (c) Dotted names in string constants: `a.b`, `a.b:attr`, `-m a.b`, where the first part is in s2 `ROOTS` and the name resolves to a module or package file. Example: the registry refs at `aisef2/invariants/registry.py:172-174`.
- (d) Discovery set:
  - Every `__init__.py` of every package directory under `dirname(F)`, the runner's `-s` (`mutation.py:2168-2169`).
  - Every file there with F's basename.
  - Reason: `unittest discover` imports every package under the start directory whatever `-p` says (`TestLoader._find_test_path`, checked on 3.14.7).
- (e) The module and name domains of every `RESOLVED_SITES` entry (R8) whose site is in S(F).

**D2 check:** `O(F).loaded ∪ (O(F).opened ∩ *.py) ⊆ S(F)` must hold; otherwise `UNRESOLVED ("S(F) misses <path>")`. On the `c186cb22` read-set, the s2 closure alone fails this check:
- for 166/166 kill files, because of `aisef2/invariants/evidence.py`, which `registry.resolve` imports from a string (`registry.py:221`);
- for 162/162 top-level `tests/v2` kill files, because of all 9 `tests/v2/*/__init__.py`.

**D3 O(F)** is one unmutated run of F by `mutation._run_file`, on the claim platform. It is recorded by NEW `validation/v23/observe.py`, which imports the `reach.HOOK` and `read_set.HOOK` mechanisms. `observe.py` MUST NOT edit `validation/v21/*`: that directory is in COPY and its bytes are pinned by kill files (`mutation.py:1544`). O(F) holds:
- **`executed` = E_full:** every def of every `.py` in S(F) whose code object started in a hooked process. The watch list MUST be all defs of S(F). reach.py's diff watch list holds only changed defs (`reach.py:15-24`), so its E contains no unchanged caller and cannot seed tier R.
- **`loaded`.**
- **`opened`, tagged:**
  - `load` = the import system's source read (`SourceLoader.get_data` under `get_code`).
  - `data` = every other open or stat of a tree path, including `linecache`, `inspect` and `tokenize`.
- **`listed` + `listed_by`.**
- **`children`:** hooked / unhooked_python / other.
  - Plus `os.exec*`, `os.fork` and `os.forkpty` events, which are not counted today (`reach.py:72-74`, `read_set.py:67-69`).
  - Plus the argv words of every unhooked and every other child.
- **`lost`:** the number of failed appends, written at the next successful append and at exit. Today they are dropped silently (`reach.py:84`, `:365-366`).
- **`os_trace`** (Linux claim): the file and exec syscalls of the whole process tree (`strace -f` class). [E] availability on the worker is not measured.
- **`platform`, `python`, `tree_sha256`, `outcome`, witness, row sha256.**

**Rule order.** For target t, every F in t's kill set is judged. A target is reusable only if no rule fires for any F. Δ = ∅ → no rule applies. Order:
1. Rules that need no O(F): R4, R5, R6.
2. R0, then the D2 check.
3. R1, then R2 and R3.
4. R7, with R8 setting its scope.

| R | Escape closed | Rule |
|---|---|---|
| R0 | stale or foreign observation | `UNRESOLVED ("no admissible observation of F")` if any of these holds: no O(F) of the comparison tree; F is under `not_passed` or `not_measured`; the witness is missing; O's OS family ≠ the claim's; O's python minor ≠ the runner's; or a process opened the source checkout outside the run's tree. All 10 committed read-set / reach / trace records are darwin/3.14.7, so none is admissible for the Linux mutation claim (`reach.py:94`, `read_set.py:102`). |
| R1 | unhooked and non-Python children; launches with no audit event; lost hits (`reach.py:70-89`, `read_set.py:60-97`, `trace_paths.py:5-6`) | O(F) is **complete** iff `lost = 0`, `unparsed_lines = 0`, and every child is hooked or covered by `os_trace`. Without `os_trace`, S(F) must also hold none of `_posixsubprocess`, `multiprocessing`, `os.fork`, `os.exec*`, `os.spawn*`, `os.fwalk`, `dir_fd=`, `os.access`, `os.readlink`, `RLIMIT_NOFILE`. A traced pid that did not run the hook is observed for data only: every tree path it opened, stat'ed, listed or exec'd joins data(F) / listed(F). Incomplete and Δ ≠ ∅ → `INVALIDATED ("F has n unobserved processes: any path of the tree may be read or run")`. No tier rescues this, because a child's argv, env and cwd are computed. |
| R2 | data reads (`reach.py:34-35`) | f ∈ Δ ∩ data(F) → `INVALIDATED ("F reads f as data")`. Bytes count, not AST, so a comment counts: `kernel_digest` hashes every `aisef2/**.py` (`aisef2/app/run.py:93-100`). A removed f ∈ opened(F), load or data → `INVALIDATED`. Until the load/data tag exists, every opened path counts as data. |
| R3 | directory listings | f ∈ Δ lying in or under a directory listed by F → `INVALIDATED` (read through the listing; `DirEntry.stat` is not seen, `read_set.py:92-97`). **Exception (registry discount):** every listing of that directory is attributed by `listed_by` to exactly `aisef2/invariants/registry.py`, registry.py ∉ Δ, and the first/last-test-module rule passes. This is `v21_snapshot_delta.RULES["data"]` and `_listing_rule` (`:94-126`, `:462`), reused together with their tests. |
| R4 | discovery imports (D2 d) | A file of F's discovery set added, removed or changed → `INVALIDATED`. A NEW test file with another basename, directly in an existing test directory, is not in the discovery set. |
| R5 | import resolution (FileFinder listings are left out of read-sets, `read_set.py:42-48`) | An added or removed `x.py` or `x/__init__.py` → `INVALIDATED` when its dotted name is, or is a package of, a module named by an import, an import string (D2 c) or an R8 domain in S(F). This covers package-over-module precedence and `try: import x` fallbacks. |
| R6 | import-time code (`reach.py:26-32`) | f ∈ Δ ∩ S(F) with `reach.changed()["module"] ≠ "unchanged"` → `INVALIDATED ("import-time statements of f changed")`. The docstring counts, since `__doc__` is readable. This replaces top-level-segment granularity: a def's decorators, defaults and annotations are import-time; its body is its own code. |
| R7 | name tiers | Applies to what remains: own-code changes of a def g (bare name b) in f ∈ Δ.<br>**Reference:** b occurs as a Name, Attribute, alias, keyword, def or class name in a file of S(F), or as a whole token `[A-Za-z_]\w*` of a string constant in S(F) or of a text file in data(F). A reference reaches every def named b; the test is name-based, so it covers overriding and dispatch.<br>**Tier S:** b is unreferenced → cleared. Tier S does not mean "no run": it still needs R0–R6 and R8.<br>**Tier R:** g ∉ E_full, and b is not in the transitive reference closure, within S(F), of E_full ∪ {target} ∪ the module code of loaded(F) → cleared.<br>Otherwise `INVALIDATED (I2)`. |
| R8 | computed names. §2.7.2's "inside E" is unsound: a mutant can reach an unexecuted def in closure(E). | **Dynamic sites:** `getattr`, `hasattr`, `setattr`, `delattr`, `attrgetter`, `methodcaller` with a non-literal name; `import_module`, `__import__`, `spec_from_file_location`, `runpy.*`, or child argv with a non-literal module or path; `exec`, `eval`, `compile`; `globals`, `vars`, `locals`, `dir`, `inspect.getmembers`, `__dict__[…]`; `from x import *`; `pickle` and `marshal` loads.<br>**Scope:** tier S → all of S(F); tier R → closure(E_full ∪ {target}).<br>A site in scope that is not in the engine's frozen `RESOLVED_SITES` makes that tier unavailable → `INVALIDATED`.<br>**`RESOLVED_SITES` entry:** (file, enclosing qualname, `ast.dump` of the call) → a domain function that computes the reachable (module, names) from literals only. Example: `registry.resolve`, `_load_script` and `runtime_mechanism_digest` take their domain from the `ref` strings of `REGISTRY` and `UNCONTAINABLE`.<br>If the domain differs between basis and now, or the call's dump changed → the site is not resolved.<br>`registry.py:206,221,225,227` are in every kill file's S(F) (`tests/v2/__init__.py:4` → `arm`). Without entries for them, no target has any tier. |

**Residual (goes in the engine docstring):**
- C code that reads tree files is seen only through `os_trace`.
- A process SIGKILLed between a failed append and the next one loses the `lost` count.
- Hash-only reads (`kernel_digest`, `mechanism_digest` at `registry.py:295`) are data reads. A DIGEST-READ discount would need its own proof and an owner ruling. It is NOT in W1; the stake is given below.

**What the committed records show for E5, and what W1 MUST measure:**

Sources:
- `closure-evidence/v2/v2.1/campaign-8/read-set.json` at `c186cb22`, darwin 3.14.7, 166 kill files, complete.
- `campaign-5/reach.json` at `57c5d3d2`, 161 kill files.
- Kill sets and mutant counts from `mutation.TARGETS` / `RECORDS` at HEAD; mutant counts are the newest entry per target.
- Since `c186cb22`, 26 `aisef2/` files changed (+3,598 / −417 lines; `story_runner.py` +25 / −1). These figures are indicative only, not admissible under R0.

| Fact | Value |
|---|---|
| HEAD kill files with a read-set row | 166 / 262. The other 96 put 521 targets / 17,664 mutants into R0 `UNRESOLVED`. |
| Kill files that open `story_runner.py` (load or data; the record has no tag) | 80 / 166. All 80 have it in the s2 closure. 19 more have it statically but never open it. |
| Whole-kernel data readers: open 91/91 `aisef2/**.py` and list all 15 `aisef2` directories | 31 / 166. `listed_by`: `app/run.py` (kernel_digest) 28, plus `bundle_cli`, `except_boundaries`, `kernel_static_checks` and test scanners. Under R2 they invalidate **444 targets / 13,482 mutants for any byte of any `aisef2/**.py`**. `test_v21_identity.py` alone is in 333 kill sets. |
| Openers with unobserved children | 60 / 80. Every one of the 505 targets that names an opener also names an opener with unobserved children, so with the committed recorders **tier R clears 0 E5 dependents**. |
| Kill files with unobserved children, all | Read-set: 102 / 166. Reach: unhooked_python > 0 in 56, other > 0 in 98, either in 100 / 161. |
| Targets whose kill files are all fully observed | 1 target (17 mutants) of the 473 that lie fully inside the read-set. Without `os_trace`, R1 invalidates the other 472 for **any** Δ, including a `pyproject.toml` version bump. |
| `tests/v2` listings | 166 / 166, all by `registry.py` only. The R3 discount is what keeps §2.8's NEW-test-file rule cheap. |
| Recording cost | 1,862 s wall for 166 files (darwin). 262 files ≈ 2,940 s [E, linear]. `os_trace` overhead [E, unmeasured]. |

**Consequential edits to W1-DESIGN:**
- **§4 (b):** dependents are bounded by R0–R8, not by reach alone.
- **N13 expected:** for the M4 probe (a comment appended to `story_runner.py`), R6 and R7 fire on nothing. The targets invalidated are those with a data reader of `story_runner.py` (R2) or an incomplete O (R1), each listed with its reason. The 11 own targets are invalidated only through those rules.
- **§10 "version bump: 0 mutants"** holds only when every kill file has a complete observation.
- **§2.8:** under D2(d), an edit to any `tests/v2/*/__init__.py` re-opens every top-level `tests/v2` kill file (162/162). W1 edits none of them.

**W1 MUST, before the E5 targeted run:**
1. Build `observe.py` with its controls: reach controls a–k, the read-set own-walk control, and the N16–N31 fixtures.
2. Record O(F) for all 262 kill files at the pre-E5 commit, on the Linux worker.
3. Report per F: data and load of `story_runner.py`, unobserved processes, `lost`, and |E_full|.
4. Print the E5 scope under R0–R8 next to the M8 static bound (640 / 17,897 / 277 serial-h).
5. If the scope is ≥ M8, report §4 (b) and exit gate 8 (≥ 50 % for one-function kernel changes) as **not met**. Never narrow it by relaxing R1 or R2. [E] R2 alone gives ≥ 444 targets / 13,482 mutants.

### 2.10 Survivor audits — append-only, never rebound (lane D5)

**Store.**
* NEW `closure-evidence/v2/v2.3/SURVIVOR-AUDITS.jsonl`. One canonical JSON object per line (`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`, LF line endings).
* Append-only: every committed version of the file MUST be a byte prefix of every later committed version and of the working file. This is checked by walking `git log --format=%H -- <path>`. Any other change is a problem, and then **no** line counts.
* `mutation.AUDITS_REL` (the v2.1 file) stays byte-identical. Editing it is a released-evidence-guard FAIL (CT-6).

**Line schema, `kind: "audit"`:**

| Field | Rule |
|---|---|
| `target, index, mutant, class, group, grounds, consumers_checked, exceptions_checked` | Same as v2.1 (`MUTATION-RUNNER-V2.md` §16). Validated by **calling** `mutation._audit_entry_problem`, never by a copy of it. |
| `source_sha256` | MUST equal the bound entry's `source_sha256`. |
| `result` | `{record: "closure-evidence/v2/v2.3/MUTATION.json", measured_on: <40-hex>, entry_sha256: sha256(canonical JSON of the bound entry)}`. The entry MUST be committed (I7). `results[index]` MUST be `SURVIVED` with description `mutant`. The target MUST NOT be in `NO_AUDIT`. |
| `snapshot` | MUST equal `result.measured_on`. Each `path:line` cite MUST resolve at `snapshot` (the path exists and the line is ≤ its length). There MUST be ≥ 1 cite. |
| `cited` | `{path: LF-sha256 at snapshot}` for every cited path. |
| `review` | `{auditor, refuter, mode ∈ {"two-blind","reaffirm"}, refuter_verdict: "NOT_REFUTED", refuter_attempts: [text, ≥1]}`. `auditor ≠ refuter`, both non-empty session/workflow ids. Ids are provenance, not authentication (§2.7(3)). |
| `prior` | Optional `{path, entry_sha256}` of a v2.1 or v2.3 entry. Provenance only, never a basis. If present it MUST resolve. |

* A `kind: "revoke"` line `{line_sha256, why, review}` makes the named line count for nothing from then on. Revocation only removes coverage; no line can ever widen another line's coverage.

**Reading old and new records.**
* `mutation.audit_of`, `audits_at` and `AUDITS_REL` stay byte-unchanged, so the frozen consumer `v21_mutation_record.py:104-126` keeps its accounting.
* NEW `validation/v23/audits.py` provides `covers(root, entry, index, mutant) -> line_sha | None` and `problems(root)`.
* `mutation._problems_v2` `:2534` dispatches on the record kind:
  * An entry **with `identity`** (v2.3) is covered **only** by a valid v2.3 line bound to its `entry_sha256`. It is never covered by `AUDITED` (keyed by description) or by a v2.1 entry, **even at an equal `source_sha256`**: the target was re-measured because some other impact input changed.
  * A legacy entry is read as today, plus the currency check below.
  * The message text stays unchanged (`unaudited survivor {d!r}`, M6), and no fifth state is added.
* `problems_of` for the v2.3 phase appends `audits.problems(root)`, the same way `:2611-2612` does for V2.1.

**Audit currency** (per survivor, printed by `--check --states`):
* Sub-status is one of `AUDITED(v2.3 line)`, `AUDITED(legacy @ measured digest)`, `UNAUDITED`, `AUDIT_INVALIDATED(<path> changed)`.
* A v2.3 line is invalidated when any `cited` digest differs at the gate head.
* A legacy entry is invalidated when a resolvable path it cites changed since `v2.2.0`. Today 212 of the 360 live entries cite ≥ 1 resolvable path (118 distinct files), and **0** of those files changed between `da3ea33f` and HEAD, so exit gate 2 is unaffected.
* An invalidated audit means re-audit, never re-measure.
* The 148 live legacy entries with no resolvable cite are a declared limitation (§2.7).

**Consequence.** No path exists to rebind an audit: v2.1 lines are immutable, and a v2.3 line is immutable and covers exactly one committed measurement whose own `source_sha256` is tamper-checked (I7).

**Writing an audit for a re-measured target's survivor (who and what):**
1. `--run-affected` appends the measurement, and the integrator commits it.
2. `python3 -P validation/v23/audits.py --packets <target>…` (read-only) emits one packet per SURVIVED mutant that has no valid line. A packet holds: the binding; the mutated slice against the original (generator output, nothing executed); the kill files; the I-inputs that caused the re-open; and any v2.1 entry at the same (target, index, mutant), labelled "prior — not evidence".
3. Auditor A (an agent session, read-only on the repo) classifies the mutant as EQUIVALENT, AUDITED or REAL_GAP, with grounds and cites at `snapshot`.
4. Refuter B (an independent session; two-blind means B classifies before reading A) tries to kill the mutant. A REFUTED verdict needs a reproducer.
5. REAL_GAP or REFUTED is **never** written as an audit. The fix is a NEW kill-test file (§2.8), appended to the target's kill set (the amendment pattern at `mutation.py:1396-1439`). The target is then re-measured, which produces a new entry and new packets.
6. A NOT_REFUTED verdict goes through `audits.py --append`:
   * it validates the line against every rule above;
   * it writes with `open(path, "a")`;
   * it refuses unless the working file equals HEAD's blob plus the new lines;
   * the line is committed alone, and an uncommitted line counts for nothing.
7. `mode: "reaffirm"` is the cheaper path. It is allowed only when all of these hold:
   * a prior entry exists at the **same** `source_sha256`, index and description;
   * every path the prior cites is byte-identical between the prior's adding commit and `snapshot`;
   * the new kill set ⊇ the prior result's kill set.
   One adversarial refuter review is still required. The line is new (its own `result`, `snapshot` and `cited`); it may quote the prior's grounds, never reuse its binding.
8. INV-MUTATION-AUTHORITY: for targets in `validation/v2/{destructive_authority,cleanup_authority}.py`, an `AUDITED` line MUST name in `exceptions_checked` the fail-closed re-validation that bounds the mutant (precedent: the `discover` L224 entries). Otherwise the mutant is REAL_GAP.
9. No bulk accept: one line per (entry, index). `group` may share reasoning but never replaces the two cite lists. The W1 report counts lines per class and per mode.

**Workload** (current survivors of the re-opened targets): W1 lean = 6; W1 upper = 360. These are agent-review hours, not mutants.

**Negative tests** — NEW `tests/v2/test_v23_survivor_audits.py`:

| Case | Mutation | Expected |
|---|---|---|
| NA1 | Replay `abbd88b5`: copy a live v2.1 entry, set the new `source_sha256`, append it as a v2.3 line | refused (no `result`/`review`). The same edit in place in `AUDITS_REL` → released-evidence guard FAIL. |
| NA2 | Edit a committed v2.3 line | "committed line N changed"; no line counts |
| NA3 | A valid v2.1 entry at equal `source_sha256` against a v2.3 entry | `unaudited survivor` |
| NA4 | A line bound to an older v2.3 entry of the target | does not cover the newest entry |
| NA5 | `auditor == refuter`; or verdict ≠ NOT_REFUTED; or a cite unresolvable at `snapshot` | problem |
| NA6 | A cited file changed after `snapshot` | `AUDIT_INVALIDATED` |
| NA7 | A line for a `NO_AUDIT` target | problem |
| NA8 | A revoke line | removes coverage; a revoke naming a missing line is a problem |
| NA9 | `v21_mutation_record` accounting of the V2.1 record | byte-identical before and after |

## 3. EVID-COUPLING-01 (P1) — resolved by identity, not by version

* `release_calibration.resolve()` → `(record_path, state, basis)`: a record **written in v2.3** whose rows, fixtures-tree digest and probe digests equal the current ones (`MEASURED`) — a record merely named by the current version string is never `MEASURED` on that basis (the branch still reads `2.2.0`); otherwise else the newest record of the nearest earlier version whose `KEYS` rows equal the shipped
  `calibrations.py` rows **and** whose fixtures-tree digest and probe digests equal the current ones
  (`VERIFIED_REUSE`, basis `identical-inputs:V<prev>`); else `INVALIDATED`. `RECORD_REL` = `resolve()[0]` (consumers
  `p5_acceptance.py:896-898`, `q2.py:37`, `v21_conformance_ruling.py:402` unchanged at the call site).
* `--write` writes nothing and leaves `aisef2/app/calibrations.py` byte-unchanged when `resolve()` is `VERIFIED_REUSE`;
  it rewrites `calibrations.py` only when rows actually change (then it *is* a kernel change, qualified by F5).
* Every version-keyed consumer is enumerated by a test that bumps a scratch `pyproject` to `2.3.0.dev0`, then (a) all
  three consumers + the 3 tests of M5 pass with `calibrations.py` untouched, (b) the same bump plus one changed
  calibration fixture yields `INVALIDATED` and the tests fail for that reason. `release_rc` / `v2_release_gate` /
  `release.yml` stay version-keyed by design (release identity) — unchanged.
* Ledger seq 8 ("no automatic migration of gated tests onto new records"): the resolution is a typed, re-derived
  `VERIFIED_REUSE`, never a silent re-point; it is reported per record (DAG `EVC-1`). No allowlist.

## 4. E5 (P1) — W1b, after W1a's F5 gate passes

*(Replaces §4. If the freeze rule at W1-DESIGN.md:3-4 applies, paste this as a dated amendment that supersedes §4. See 4.9 for the edits it forces elsewhere.)*

**Why there is no `try/finally`.** `RunScope.append` folds every event through the six projections before it writes (run_scope.py:144-148, fold.py:147-158). These are the constraints the old design ignored:

- `story/dispose` is legal only at COMMIT/ROLLBACK/RETRY (story_state.py:54-57).
- `story/end` is legal only after `story/dispose` with an outcome pending (story_state.py:58-61, terminal_state.py:48-50).
- `gate/decision` must cite at least one `gate/check` (event.py:218-219, :266-275).
- `story/rollback` must cite a `failure/observed` of the same attempt (event.py:208, failure_owner.py:34-37).

A `finally` that always writes dispose → `scope.dispose()` → end therefore raises `ProjectionError` on every fault before the outcome and on every `BaseException`, and that error replaces the original. Rules for E5:

- E5 MUST work out what it writes from where the attempt is in the journal.
- E5 MUST NOT write anything on a `BaseException`.

**Charter wording.** RELEASE-CHARTER claim 2 says "typed stage lifecycle and deterministic `finally` (E5/E6/E7)". It is met as a *deterministic closure*: E5's attempt handler (H1–H9) closes every attempt the journal allows, and E7's total run-level finalize closes the run. E5 itself has no `finally` by design. A one-line charter erratum ("deterministic closure") is proposed for the owner; it does not change the claim's strength.

### 4.1 Lifecycle: journal positions and legal events

| Pos | story_state / terminal_state | E5 may write | Refused, so never attempted |
|---|---|---|---|
| P1 after `story/begin`, not admitted | BEGIN / story RUNNING, no outcome pending | `provider/result` closer, `gate/check`, `gate/decision` (≥ 1 check cited), `failure/observed`, `story/rollback` | `story/commit` (needs ACTIVE, story_state.py:10); `story/dispose`; `story/end` |
| P2 admitted | ACTIVE | as P1 | `story/dispose`, `story/end` |
| P3 after `gate/decision`, no outcome yet | unchanged | **nothing**: one decision per attempt (R6); an outcome after a passed decision, or one not backed by the decision, would be fabricated | a second decision; dispose; end |
| P4 after outcome | COMMIT/ROLLBACK/RETRY, outcome pending | `story/dispose` | any second outcome (story_state.py:49-53, terminal_state.py:44-46); `story/end` |
| P5 after `story/dispose` | DISPOSE | `story/resource-released` (format2.py:168-179 has no dispose/end check), `story/end` | a second `story/dispose` |
| P6 after `story/end` | ENDED | nothing for this attempt (`story/begin` only after RETRY, story_state.py:37-41) | everything |

ROLLBACK is the only outcome E5 ever writes on its own:

- It is legal from BEGIN and ACTIVE (story_state.py:10-11).
- UNKNOWN is INTEGRATION and never retryable (owner.py:129-131), so `budget.charge` never grants a retry for it.

### 4.2 Typed stages

`class Stage(Enum)` (a plain `Enum`, so `_enum_members` detects it and every `Stage.X` reference in `_attempt` gets the enum-swap mutants: ≈ +156 mutants on `_attempt`, costed in §10) defines `ACQUIRE=1, ADMIT, CONTINUE, DEVELOP, MOVE_CANDIDATE, PROVE_CANDIDATE, QUALITY, REVIEW_SCAN, MERGE, POST_MERGE, DECIDE, DISPOSE, END=13`.

`_Stages.advance(s)` MUST:

- raise `InvariantError` when `s.value <= at.value`, before that stage's first write;
- allow skips (no-work stories skip DEVELOP and QUALITY; a typed failure jumps to DECIDE).

Every stage entry below calls it. DECIDE, DISPOSE and END call it too, so a second dispose is impossible in three independent ways:

- the guard refuses it;
- story_state.py:54-56 refuses it;
- `StoryScope.dispose` returns its cached report and writes nothing (story_scope.py:122-123).

| Stage | Entered at (today) | Writes | Fault-row label (R6 evidence call) |
|---|---|---|---|
| ACQUIRE | story_runner.py:198 | resource-acquired ×3; typed row `resources` | `resources` (`acquire`) |
| ADMIT | :205 | probe/evaluated, story/admitted, ranges; row `admission` | `admission` (`admit_story`) |
| CONTINUE | :227 | story/plan-drift | `admission` |
| DEVELOP | :236 (not no-work) | provider/request + result; `_EscapedRange` acquire (:249); row `developer` | `developer` (`implement`) |
| MOVE_CANDIDATE | :261 | row `candidate` | `candidate` (`move`) |
| PROVE_CANDIDATE | :271 | probe/evaluated, proof/verified, rows `proof:<cid>` | `candidate` |
| QUALITY | :289 (not no-work) | tests/adequacy, ranges, rows `candidate` / `quality` | `quality` (`assess`) |
| REVIEW_SCAN | :307 | REVIEW provider/request + result, tool/invoked + result, review/security rows | `review` (`review`) |
| MERGE | :322 | row `merge` (written by merge.py) | `merge` (`merge`) |
| POST_MERGE | :327 | rows `post-merge`, `post-merge:<cid>`, proofs | `post-merge` (`move`) |
| DECIDE | :351 | gate/decision, then story/commit, or failure/observed + story/retry \| story/rollback | (none) |
| DISPOSE / END | :364 / :366 | story/dispose, releases / story/end | (none) |

### 4.3 The attempt handler (normative)

- **H1. Scope of the handler.** One `try … except Exception` MUST run from just after `story/begin` (:187) to the end of POST_MERGE.
  - `story/begin`, `number` and `scope` stay outside it: a refused begin opens nothing.
  - There is no `finally`.
  - `BaseException` is never caught: `InvariantError` (errors.py:8-11), `KeyboardInterrupt`, `SystemExit`.
- **H2. Repository state** is one of `clean`, `landed(rev)` or `unknown`:
  - `unknown` from just before `merge(...)` until it returns, and from just before each `merger.revert(...)` until it returns;
  - `landed(merged)` after a merge whose `merged != candidate` (B7, :334/:347), until a revert returns or the story commits;
  - otherwise `clean`.
- **H3. Fault while the repository state is `unknown`.** E5 MUST write nothing and re-raise. This attempt's merge may be on main, so no outcome can be backed. The story stays open, and `_close_run` interrupts the run (run.py:736-749).
- **H4. Otherwise, contain the fault, in this order:**
  1. If `landed(rev)`: call `merger.revert(rev)` once.
  2. Close every `provider/request` of this attempt that has no `provider/result`: write `{outcome: OUTCOME_UNKNOWN, synthetic: true, detail: "<STAGE> raised <Type> before its result"}` citing the request. This is the same closer as run_scope.py:224-228. It is derived from the journal, so a later `interrupt` does not repeat it (format2.py:228-232). Without it, a clean shutdown would leave the request open (sentinel.py:105-108).
  3. Set `failure = classify(FailureCode.UNKNOWN)` and `detail = f"{stage.name} raised {type(e).__name__}"`. The last token is the type, so `_fail` records `original` = the type, unchanged (:163-164). A foreign fault replaces a typed failure set earlier in the same attempt; the typed rows stay in the journal.
  4. Write one row, `checks.append(gate.check(run, story_id, "<label>", False, detail))`, using the stage's **constant** label from 4.2.
  5. Fall through to today's DECIDE unchanged: one false `gate/decision` citing `checks`, `failure/observed` UNKNOWN, `budget.charge` (no retry), `story/rollback`.
  6. Then DISPOSE and END.
  7. Then re-raise the **same object** `e` out of `run_story`, to run.py:691-695, which records it in `story_errors`.
- **H5. Faults at or after DECIDE** (the decision, `_fail`, `budget.charge`, `run.retry`, the outcome, `story/dispose`, `scope.dispose()`, `story/end`): E5 MUST write nothing more and propagate. These are reachable only through a journal that refuses appends, or through an `InvariantError`.
- **H6. Double fault.** Once H4 has started, any later `Exception` (in H4, in DECIDE or in the closure) stops all writing. The **original** propagates, with the later one attached as a note: `e.add_note(f"E5: the attempt could not be closed: {type(x).__name__}: {x}")`, then `raise e from None`. The original is never masked. A later `BaseException` propagates as itself.
- **H7. `scope.dispose()` raising.** `StoryScope.dispose` records FAILED/RESIDUAL per resource, and marks a release the journal refused as `unrecorded` (story_scope.py:142-150). It raises only `InvariantError` (:159-161, :173-174). If it raises, H5/H6 apply:
  - the story stays at DISPOSE;
  - the resource being released is named "acquired … never released" by the next preflight (sentinel.py:96-101);
  - `interrupt`/`shutdown` resume the rest of the disposal (story_scope.py:122-140; run_scope.py:188, :233).
- **H8. `BaseException` path (unchanged behaviour).**
  - Inner `finally` blocks still run: `_Held.release` (:216-217, :300-301), `unconfine` (:319-320).
  - run.py:697-699 → `_close_run` → shutdown is refused because the story is open (run_scope.py:184-187) → `RunScope.interrupt` (run_scope.py:206-249) closes calls and requests, disposes every scope graceful-first, and ends the run; the sentinel stays OPEN.
  - Inside `run.interruptible()`, a `KeyboardInterrupt` goes straight to `interrupt` (run_scope.py:198-204).
- **H9. Static shape.** All of these MUST hold unchanged, with **no checker edit**:
  - **R6** (old_path_audit.py:705-735, tables :242-244): every `gate.check` in `_attempt` is an argument of `checks.append`, has a label from STAGE_EVIDENCE/STAGE_PREFIX_EVIDENCE, and comes after its stage call; there is exactly one `gate.decision(run, checks, …)`; `budget.charge` comes before `run.retry`. A dynamic label such as `ROWS[stage]` or `stage.value` fails R6, hence one constant-label call per label.
  - **R3** (:652-676): `assess` comes after `move(verifier_wt, …)`.
  - **Authority inventory** (compare at :823-842, run by release_inventory.py:54-66): the rows `_attempt`, `_fail` and `run_story` keep their ids, dispositions and kinds. `Stage` and `_Stages` call no CONTROL_FUNCTIONS and write no CONTROL_EVENTS (:181-221). No new top-level helper may write gate/failure/outcome events or build `Attempt`.
  - **Q0.** Both checks feed Q0: old_path_audit's clean check *is* `release_inventory.check` (checker_calibration.py:378-392). So old_path_audit.py MUST NOT be edited, and any violation is STOP Q0-1.
  - **Consequence.** `_attempt` cannot be split into helpers, so V21-23's complexity reduction is **not claimed**.

Sketch (every existing statement, row and payload stays as it is):

```python
    begun = run.append(T.STORY_BEGIN, {...}); number = ...; scope = run.story(story_id)
    st, repo, fault = _Stages(), None, None          # repo: None | landed revision | _UNKNOWN
    try:
        st.advance(Stage.ACQUIRE)  # ... today's body, st.advance(Stage.X) at each entry, repo tracked per H2
    except Exception as e:                            # §22 at the attempt boundary, as merge() does (merge.py:26-31)
        fault = e
        if repo is _UNKNOWN:
            raise                                     # H3
        try:
            ...                                       # H4 i–iv; iv = one constant-label branch per row of 4.2
        except Exception as x:
            e.add_note(...); raise e from None        # H6
    try:
        ...                                           # DECIDE, DISPOSE, END: today's code plus the three advance() calls
    except Exception as x:
        if fault is None: raise
        fault.add_note(...); raise fault from None    # H6
    if fault is not None:
        raise fault                                   # H4 vii
```

### 4.4 Minimal file set

| File | Change | Why |
|---|---|---|
| `aisef2/orchestrate/story_runner.py` | `Stage`, `_Stages`, the `_attempt` handler | E5 |
| `aisef2/app/run.py` | The refusal branch at :693 only: `results[story]` = the journal's outcome words for that story (`outcomes_from`, :393-401) when it has any, else `["REFUSED: <T>"]` | Without this, every story E5 closes makes `--verify` report "the record's story outcomes are not the journal's" (verify.py:212-216 compares exact lists). It also fixes the existing RETRY-then-raise mismatch. test_s2_kills.py:521-526 (mocked `run_story`, no journal outcome) stays green. |
| `validation/v2/mutation.py` | Append-only hunk, same pattern as :1422-1437: new target `_Stages.advance` only (`Stage` and `_Stages.__init__` have 0 mutation sites — `_root` does not resolve a class body, and a target with no mutants fails "no mutants generated" — so they are covered through `_attempt`'s enum swaps, not as targets); `test_v23_story_lifecycle.py` appended **last** to the kill sets of `_attempt` and `run.py::execute` | Otherwise the new code goes unmeasured |
| NEW `tests/v2/test_v23_story_lifecycle.py` | Fault matrix (4.5) | Kill file |
| NEW `tests/v2/test_v23_story_golden.py` | Byte-identity differential (4.6) | **Not** a kill file |

**Not changed:**

- `gate.py`: `check` and `decision` are used as they are (gate.py:15-22). A false decision always cites at least one row, because H4 step 4 writes its row first.
- `merge.py`: `merge()` already flattens merger exceptions (merge.py:26-31), and E5 needs nothing new from it.
- Also unchanged: `run_scope.py`, `story_scope.py`, the projections, `old_path_audit.py`, `destructive_sites.json`, and every existing test file.

**#39 is split.** The merge branch writes `original` as "UNKNOWN", because it is the last token of `"merge: UNKNOWN"` (:163-164, :325). Fixing it needs the merger's exception type passed as data (`Merged.original`, merge.py), so it becomes #39b: `Merged.original` is added in W2a by L2-LIFECYCLE (owns `merge.py`), and the `story_runner.py:325` hunk that passes it lands in W2b by L2-ACCOUNTING (owns `story_runner.py` in W2b) (DEPENDENCY-DAG.md §1b, §4). That keeps W1b byte-identical on every path that does not raise. The W1b part of #39: every UNKNOWN that E5 writes names the real type.

Option (A), "contain and return a ROLLBACK, change story_runner.py only", is rejected. It drops the refusal text from `story_errors` (the tripwire/pin `SessionRefused` at client.py:310-352, `RangeEscaped`), and that breaks e2e_guest.py:690 `control_the_kernel_reports_the_escape`.

### 4.5 Fault-injection matrix (`test_v23_story_lifecycle.py`)

**How faults are injected:**

- `mock.patch.object(sr, "<callee>", side_effect=RuntimeError("E5"))` for `admit_story`, `continue_story`, `prove`, `assess`, `review`, `scan`, `merge`, `reprove`;
- adapter doubles that raise: `Workspace.scratch/checkout/move/diff`, `Dev.implement`, `Merger.revert`;
- a `run.append` wrapper that raises `JournalError` on a chosen event type.

**Fixtures:**

- imported from `tests.v2.test_p6_orchestration` and from `EscapedDev` in test_b1gap5_story_runner_attempt.py; neither file is edited;
- temp dirs only through `TemporaryDirectory`. No `shutil.rmtree`/`os.kill`: every such site under tests/v2 must be ledgered (destructive_authority.py:33, :40).

**Expected outcome codes used in the table:**

- **C (contained).** The tail is:
  - `[provider/result{OUTCOME_UNKNOWN, synthetic}]`, then
  - `gate/check{<sid>:<L>, false, "<STAGE> raised RuntimeError"}`, then
  - `gate/decision{false, cites every check of the attempt}`, then
  - `failure/observed{UNKNOWN, INTEGRATION, retryable false, original "RuntimeError"}`, then
  - `story/rollback`, `story/dispose`, `story/resource-released`×k, `story/end`.

  Then: `run_story` raises the injected object (`is`); `scope.state == "DISPOSED"`; `open_stories() == []`; `sentinel.residuals(journal)` is exactly as stated; `run.shutdown()` succeeds.
- **P (propagated).** No event of the attempt after the faulting stage's own writes; the exception propagates (`is`); the story is open and the scope ACTIVE. Then `run.interrupt()` disposes the scope (every acquired resource is released or named), closes requests, and writes `run/end`.

| # | Stage | Fault | Label | Expected |
|---|---|---|---|---|
| F1 | ACQUIRE | `ws.scratch` raises | resources | C, k=0 |
| F2 | ACQUIRE | second `ws.checkout` raises | resources | C, scratch RELEASED |
| F3 | ADMIT | `admit_story` raises | admission | C; admission ranges released before the row |
| F4 | CONTINUE | `continue_story` raises | admission | C |
| F5 | DEVELOP | `implement` raises after provider/request | developer | C; tail starts with the closer citing the request; no "has no result" residual |
| F6 | DEVELOP | `RangeEscaped` (EscapedDev) | developer | C, original "RangeEscaped"; `developer S1 range`, both worktrees and scratch RESIDUAL; directories still exist; residuals name exactly these four |
| F7 | MOVE_CANDIDATE | `ws.move` raises | candidate | C |
| F8 | PROVE_CANDIDATE | `prove` raises | candidate | C |
| F9 | QUALITY | `assess` raises | quality | C; test ranges released first |
| F10 | REVIEW_SCAN | `review` raises; then a variant where `scan` raises | review | C; `unconfine` called exactly once (spy) |
| F11 | REVIEW_SCAN | `ToolCall.finish` raises after dispatch | review | C, plus a declared residual "tool call … has no result"; a later `interrupt()` closes it without error |
| F12 | MERGE | `merge` raises | (none) | P (H3, repository state unknown); no outcome |
| F13 | POST_MERGE | `ws.move(impl, merged)` raises, merged ≠ candidate | post-merge | `revert` called once, main == parent, then C |
| F14 | POST_MERGE | `reprove` raises, merged ≠ candidate | post-merge | revert once, then C |
| F15 | POST_MERGE | B7: merged == candidate, `reprove` raises | post-merge | `revert` never called; C |
| F16 | POST_MERGE | typed `ResourceUnavailable`, then `revert` raises `Residual` | (none) | P (H3); last event is the typed `post-merge` row |
| F17 | DECIDE | append refuses `gate/decision` | (none) | P (H5) |
| F18 | DECIDE | append refuses `story/commit` | (none) | P; last event `gate/decision{true}`; no rollback |
| F19 | DISPOSE | append refuses `story/dispose` | (none) | P; scope ACTIVE |
| F20 | DISPOSE | a held resource's release raises `InvariantError` | (none) | P; `story/dispose` present, `story/end` absent; `interrupt()` resumes the rest |
| F21 | END | append refuses `story/end` | (none) | P; scope DISPOSED, state DISPOSE |
| F22 | PROVE | `prove` raises `InvariantError` | (none) | P (H8): no gate/decision, failure or rollback |
| F23 | DEVELOP | `KeyboardInterrupt` inside `run.interruptible()` | (none) | E5 writes nothing; run/interrupted, synthetic closer from run_scope, disposal, run/end; no rollback |
| F24 | DEVELOP | F5 plus append refusing `gate/check` | (none) | `RuntimeError` (`is`) propagates with a note naming the `JournalError`; closer present; no decision |
| F25 | DEVELOP | F5 plus append refusing `story/rollback` | (none) | as F24; last event `failure/observed` UNKNOWN |
| G1 | guard | DEVELOP then ADMIT; DISPOSE twice | (none) | `InvariantError`; journal length unchanged |
| G2 | double dispose | after an attempt: append `story/dispose`; call `scope.dispose()` again | (none) | `ProjectionError`; identical report, no events |
| R1 | run | `run.execute` (hermetic harness of test_b1gap4_run_execute.py, imported), developer raises `RuntimeError` | (none) | RUN.json `story_outcomes {S1:["ROLLBACK"]}`, `story_errors` names the RuntimeError, journal closed `SHUTDOWN`; `verify` reports no "story outcomes are not the journal's" |

K-NOWORK (V21-13) and test_b1gap5 stay green unchanged; test_b1gap5's `try/except RangeEscaped` at :61-64 still holds.

### 4.6 Golden success-path byte-identity (`test_v23_story_golden.py`, not a kill file)

**Setup:**

- Reference module: `git show da3ea33f:aisef2/orchestrate/story_runner.py`, loaded under a private name that MUST be registered in `sys.modules` before `exec`, or `@dataclass(slots=True)` raises (measured).
- CI unit legs have the history they need (fetch-depth 0, tests.yml:37). If the blob is unavailable the test FAILS; it never skips.
- Each arm: a fresh `TemporaryDirectory`; env `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` fixed, `GIT_CONFIG_GLOBAL=os.devnull`, `GIT_CONFIG_NOSYSTEM=1`; clock `iter(range(10**6))`.

**Scenarios.** Every non-raising typed path the p6 doubles reach (test_p6_orchestration.py:105-190), at least:

- ORCH-1 (COMMIT); caught (CONTRACT_UNSATISFIED, RETRY → ROLLBACK);
- ORCH-2 outage; ORCH-3 admission refusal; ORCH-4 / K-NOWORK;
- ORCH-8 merge conflict; ORCH-9/10 post-merge regression with revert;
- SCHEMA-4, -5, -7b, -8, -9; SCHEMA-10, -10b, -10c;
- merger-raises UNKNOWN.

**Assertions, per scenario:**

1. Reference module twice: identical bytes. If not, fail and name the scenario ("harness not deterministic").
2. Current module: raw bytes equal to the reference (sha256; print the first differing line on failure).

**Cost [E]:** 3 runs per scenario × about 4 s measured per run.

### 4.7 Qualification through F5 (written to the W1 report before the targeted run)

**(a) Targets whose slice changed (I1):**

- All **11** story_runner targets / **411** mutants. `from enum import Enum` changes `<imports>`, which is in every slice. Without the import it would be `_attempt` 326 + `run_story` 11 = **337**. The other 8 targets (74 mutants, `_fail` among them) would stay reusable.
- Plus `run.py::execute`, 459 mutants (its slice includes the hunk).
- Plus the new target `_Stages.advance`, measured as new (`Stage`/`_Stages.__init__` are not targets: 0 sites).

**(b) Dependent targets (I2 tier R):** targets whose kill files' unmutated traced function set *E*, taken at the E5 commit, contains `_attempt` or `execute`, or reaches them through the static closure of *E* ∪ {target} (N15). Upper bound: M8's 640 / 17,897 / 277 serial-h. `run.py::execute` is in both (a) and (b), so the run.py hunk adds no mutants.

  - **Withdrawn at the W0 freeze:** an earlier draft asked F5 to treat import-time execution of added bindings as not reaching dependents. That is unsound (an added import can have import-time side effects) and conflicts with R6. **R6 is strict:** the added `from enum import Enum` and the new top-level `Stage`/`_Stages` change `story_runner.py`'s import-time code, so every kill file that loads it is judged by R6 → `INVALIDATED`; E5's dependent scope is therefore the R0–R8 result, expected at or near the M8 bound (640 / 17,897) — SCALE-1. N13's "added import + added class" variant MUST show exactly that.


**(c) Currency nodes (F5-ROUND)** whose declared inputs include story_runner.py.

  - Literal binders, measured by grep: `validation/v2/{mutation,old_path_audit,p6_evidence}.py`; `validation/qualification/{c2_closure_audit,c2_final_integration,c2_k_nowork_001,c2_orchestration_repair,c2_p9,c2_p9_preflight,q5,v21_conformance_ruling}.py`; plus the kernel-digest binders (`b1_bindings_check`, M4).
  - Binders of run.py: not measured; the audit hook declares them [E].
  - The v2.2 round replays at v2.2.0 byte-identically.
  - The release authority inventory and the six static proofs MUST hold without regeneration (H9), or STOP Q0-1.

**Then:** `--run-affected` measures (a)+(b) on Linux workers, with no paid calls; (c) is re-derived; everything else stays VERIFIED_REUSE.

**Baselines for the E5 row of §10:**

- (i) v2.2 rule: 36 targets / 1,498 mutants (whole files: story_runner 11/411 plus run.py 25/1,087).
- (ii) sound-cold: ≥ 651 / 18,308 / 287 serial-h for story_runner (M8), plus run.py's static dependents (not measured; `--affected` reports them).

### 4.8 Disclosed behaviour changes and declared limits

1. **A raising attempt is now closed in the journal** (closer, row, false decision, UNKNOWN, rollback, dispose, end). For such runs, RUN.json changes:
   - `story_outcomes`: the journal's words instead of `REFUSED: <T>`;
   - `delivery_verdict`: FAIL instead of NOT_REACHED (a decision now exists, run.py:381, :389);
   - the journal closes `SHUTDOWN` and the sentinel CLEAN, instead of "INTERRUPTED after a refused shutdown";
   - residuals are still named (sentinel.py:86-108).

   The committed S3c runs ×2 are history and stay unchanged. e2e_guest.py:690 still passes, because `story_errors` keeps `RangeEscaped`.
2. A foreign fault in POST_MERGE now reverts this attempt's merge. Today the merge is left on main and the story open.
3. `InvariantError` raisers, including CODE-AUDIT #2's probe raisers, keep today's interrupt path by design.
4. A tool call left DISPATCHED by a fault inside `finish` is not closed by E5. Its closer belongs to the `ToolCall` object (tool.py:94-108; the only user is security.py:39-45). A closer written from the journal would make a later `interrupt` write it twice (format2.py:212-224), so the call stays named by the next preflight (sentinel.py:102-104).
5. An exception raised by an inner `finally` replaces the one in flight (Python semantics); E5 records whatever reaches the attempt boundary.
6. After H3, H5 or a double fault the run continues to the next story with this story open. This is existing run.py:691-695 behaviour.
7. "Event-type sequence identical on every existing path" (ARCHITECTURE.md:306) holds for every path that does not raise out of `_attempt` today (4.6). Paths that raise change by design (#2).

### 4.8b Import discipline and the single targeted run (lane D5)

* E5 MUST NOT edit or remove any existing import or module-level statement of `story_runner.py` (it only adds). Under strict R6 (§4.7(b)) the additions still re-open every loader; I1 re-opens all 11 own targets (`<imports>` is in every slice) — 11 / 411 + ≈156 enum-swap mutants.
* W1 has **one** targeted run, after W1b lands, over W1a ∪ W1b. Measuring W1a's re-opens first would measure the 41 shared targets twice, `_attempt` included (M13).
* §4.7 (b): dependents are bounded by the §2.9 rules R0–R8, not by reach alone (lane D2).

### 4.9 Consequential edits for the integrator

- **W1-DESIGN.md:298 (§8 L1-LIFECYCLE):** add `aisef2/app/run.py` (refusal branch only), the `validation/v2/mutation.py` append-only hunk, and the two new tests.
- **W1-DESIGN.md:351 (§11 gate 5) and DEPENDENCY-DAG.md:** "`aisef2/` changed only in `story_runner.py` and run.py's refusal branch".
- **DEPENDENCY-DAG.md:** #39b = `Merged.original` in W2a L2-LIFECYCLE (`merge.py`) + the `story_runner.py:325` hunk in W2b L2-ACCOUNTING (applied).
- **ARCHITECTURE.md:306/:314-320:** E5 location becomes `story_runner.py` + run.py:693 (not merge/gate); add the H3/H5 "no outcome" cases to the rules.

### 4.10 Evidence

**Measured** (`python3 -P`, scripts under `<scratch>/fix2/D1/`):

- **Committed run records:** 28 committed `RUN.json` under closure-evidence (`runs.py`). Exactly 2 are on the exception path: `v2.1/e2e-linux{,-final}/guest-X1/S3c`, with `REFUSED: RangeEscaped`, `story_errors` RangeEscaped, closed "INTERRUPTED after a refused shutdown"; e2e-X1.json records `delivery_verdict NOT_REACHED`. All others are SHUTDOWN runs or refusals before any story.
- **Mutant counts** (`sr_cost.py`, `targets.py`; newest record V2.1 for all):
  - story_runner.py: 11 targets / 411 mutants (`_attempt` 326, `_fail` 34, `run_story` 11, other 8 targets 40).
  - run.py: 25 targets / 1,087 mutants (`execute` 459).
  - merge.py: 3 targets / 72 mutants (`merge` 36); gate.py: 3 targets / 21 mutants. Both P6 record, one kill file `test_p6_stages.py`.
- **Golden feasibility** (`golden.py`, 2026-11-21T04:44Z, Apple M1, 8 cores):
  - Journals are byte-identical across 2 runs and across distinct temp paths: ORCH-1 COMMIT (58 lines), caught RETRY → ROLLBACK (62 lines).
  - The frozen `da3ea33f` module equals the current one byte for byte; neither the temp path nor `sys.executable` appears in the journal.
  - 3.5–4.2 s per run.
- **Reference blob:** the v2.2.0 story_runner.py blob equals HEAD; its last change is 30da62a6.

**Read (path:line):**

- `aisef2/runtime/run_scope.py`: :144-148, :168-173, :180-195, :198-204, :206-249.
- `aisef2/journal/fold.py`: :147-158.
- `aisef2/journal/projections/story_state.py`: :10-16, :37-61; `terminal_state.py`: :44-53; `failure_owner.py`: :34-40; `budgets.py`: :73-86.
- `aisef2/journal/event.py`: :184-193, :208-209, :218-219, :266-275.
- `aisef2/journal/format2.py`: :104-110, :140-179, :202-232; `format3.py`: :173-177.
- `aisef2/control/owner.py`: :129-131, :163-172; `aisef2/errors.py`: :8-11.
- `aisef2/runtime/story_scope.py`: :88-177; `aisef2/runtime/sentinel.py`: :86-108; `aisef2/runtime/tool.py`: :54-108.
- `aisef2/orchestrate/security.py`: :35-56; `story_runner.py`: :161-165, :183-370; `merge.py`: :25-35; `gate.py`: :15-22.
- `aisef2/app/run.py`: :374-411, :687-699, :736-749; `aisef2/app/verify.py`: :212-217; `aisef2/app/client.py`: :83, :300-352.
- `validation/v2/old_path_audit.py`: :181-244, :652-735, :823-842; `validation/v2/checker_calibration.py`: :378-392, :621-697; `validation/qualification/release_inventory.py`: :1-66.
- `validation/v2/destructive_authority.py`: :1-40; `validation/v2/mutation.py`: :350-361, :1415-1440; `validation/v2/p6_evidence.py`: :268-300.
- `validation/v21/cli_integration/e2e_guest.py`: :670-692.
- `tests/v2/test_b1gap5_story_runner_attempt.py`: :29-67; `tests/v2/test_s2_kills.py`: :521-526; `tests/v2/test_p6_orchestration.py`: :74-190, :379-466; `tests/v2/__init__.py`.
- `.github/workflows/tests.yml`: :28-37.
- `docs/v2.3/ARCHITECTURE.md`: :280-325; `docs/v2.3/DEPENDENCY-DAG.md`: :32, :180-184, :337, :351, :483; `docs/v2.3/CODE-AUDIT.md` rows #2, #39.

**Found, not part of the E5 design:**

- run.py:693 overwrites a story's outcome history with `["REFUSED: <T>"]`. `--verify` already flags any story that RETRYed before it raised (verify.py:212-216). The 4.4 run.py hunk fixes this.
- Repo untouched: `git status` shows only the pre-existing docs changes.

## 5. REL-GOV-01 (P1) — a verified manual approval checkpoint (separate control)

* **Guard (L1-CIGOV).** NEW `validation/qualification/release_governance.py`: pure `problems(env, policies) -> list[str]`
  — FAIL unless `pypi` has a `required_reviewers` rule with ≥ 1 reviewer, `deployment_branch_policy.custom_branch_policies`
  is true and every policy from `GET /environments/pypi/deployment-branch-policies` has `type == "tag"`; reports
  `can_admins_bypass` and `prevent_self_review`. `release.yml` gains a `governance` job (with `permissions: actions: read` if the environments endpoint needs it; else the public endpoint unauthenticated); `publish.needs` includes it; a
  static test asserts the dependency and that no publish path bypasses it. Negative tests: mocked `protection_rules: []`,
  a branch-type policy, no policies → FAIL; a reviewer + one tag policy → PASS. (If the workflow token cannot read the
  policies endpoint, the tag restriction rests on the negative probe below and the guard says so.)
* **Owner configuration (persistent — this is the control):** `pypi` → Required reviewers = owner; prevent self-review
  **off** (the owner is the only reviewer and the tagger); admin bypass **off**; deployment tags = one rule, type tag,
  pattern `v[0-9]*.[0-9]*.[0-9]*`. The agent never changes repository settings.
* **W1 probe — verifies the pause itself, owner-run, publishes nothing.** Release.yml has no `workflow_dispatch` and a
  dispatch from a branch is refused by a tag-only policy, so the probe is a **tag push** of a commit **P parented on
  `origin/master` (`399b775f`) that adds only `.github/workflows/relgov-probe.yml`** — no DISC-1 dependency (no v2.3
  content). The probe workflow triggers on tags `v0.0.0-relgov-probe-*` and `relgov-probe-neg-*`, has
  `permissions: {}` (no id-token), `environment: pypi`, and one `echo` step (no checkout, no `uses:`). Independent
  barriers: no OIDC token; PyPI trusted publishing is bound to `release.yml` + `pypi`; no probe tag matches
  `release.yml:29` or the staging tags; the owner rejects.
  1. Pre-check (read-only): env + policies JSON; `release_governance.py` PASS; no remote `*relgov-probe*` tags.
  2. Positive: push `v0.0.0-relgov-probe-1` → poll (≤ 600 s loops) until the job is `status: waiting`; snapshot run,
     jobs, `pending_deployments` with `date -u`; **owner rejects**; snapshot `approvals` (rejected) and final jobs (no step ran).
  3. Negative: push `relgov-probe-neg-1` → the job fails without ever `waiting` (proves the tag restriction).
  4. Cleanup: delete both remote tags; runs and the rejected review are kept as evidence.
  Evidence: `closure-evidence/v2/v2.3/REL-GOV-01-W1-PROBE.json` (env/policies raw + sha256, probe commit + parent,
  positive/negative run ids and JSON, observed-at timestamps, cleanup, verdict `CHECKPOINT_PAUSES`+`TAG_RESTRICTED`).
* **W6 — the charter's observation (RELEASE-CHARTER §2):** after the owner pushes `v2.3.0`, `publish` (release.yml's own
  job) must be observed in `status: waiting` with every other job green, `pypi.org/pypi/aisef/2.3.0/json` = 404, all
  snapshotted **before** the owner approves; recorded as `REL-GOV-01-W6-OBSERVED.json`. If `publish` ever runs without
  `waiting`: STOP. W6 has a hard DISC-1 dependency (the tag publishes the branch history).

## 6. BUILD-REPRO-01 — explicit reproducibility contract (every clause tested)

* `repro_dist.py`: member mode normalised to git semantics (`0755` if any execute bit else `0644`; dirs `0755`).
* **Where the text lives and lands (lane D5):**
* **Drafting (W1, L1-BUILD).** L1-BUILD drafts the contract in NEW `docs/v2.3/drafts/BUILD-REPRO-CONTRACT.md`. It contains:
  * (a) the paragraph that replaces `docs/v2/RELEASE-PROCESS.md:97-99`;
  * (b) the README sentence and the 2.3 release-table row. The historical rows `README.md:131/:144/:161` stay untouched.
* **Pinning test.** `tests/v2/test_v23_repro_contract.py` pins the draft's clauses to the `repro` job: the interpreter list equals the matrix, and the two perturbation lines and the `v2.2.0` rebuild step are present. The text therefore cannot claim more than CI runs.
* **No branch edits.** `README.md` and `docs/v2/**` are never edited on `release/v2.3-big` (CLAUDE.md; DAG L6-RELEASE).
* **Landing (W6, L6-RELEASE, owner-authorized, on master).** README is SHIPPED (`release_rc.py:73`). It is frozen into `shipped_trees` at RC-FREEZE (`:105`), and a later change is caught by `:118-121` ("a new candidate is needed"). So the README part MUST be on master and merged into the branch **before RC-FREEZE**; the DAG needs the edge `PUBLIC-DOCS(README) → RC-FREEZE`, not only `→ PUBLISH`.
* **Owner decision at the W6 freeze (not a W1 STOP).** Charter §4 keeps master untouched until the final owner authorization (`RELEASE-CHARTER.md:70`), so landing the README early is the owner's publication call:
  * (i) authorize the README commit on master before RC-FREEZE — this is the default;
  * (ii) ship 2.3.0 with the 2.2 README and land the 2.3 README after PUBLISH. This must be recorded as a decision, because 2.2.0 ended up this way without one (M12).
* `RELEASE-PROCESS.md` is not shipped (`MANIFEST.in` comment at `:2`: the sdist = `aisef` + `aisef2` + metadata). It lands in the same master commit.
* README and `docs/v2` are outside COPY and outside I4, so they re-open 0 mutation targets. `repro` compares builds of a single commit and is unaffected.
* **Contract** (replaces `docs/v2/RELEASE-PROCESS.md:97-99`'s unscoped "builds are reproducible"):
  > The wheel and sdist of a commit are reproduced byte for byte by `SOURCE_DATE_EPOCH=$(python -P
  > validation/qualification/release_rc.py --epoch) python -m build` + `repro_dist.py`, with the pinned
  > `setuptools==84.0.0`, on GitHub-hosted `ubuntu-latest` CPython 3.11, 3.12, 3.13 and 3.14 — each build records its
  > interpreter and runtime zlib version — from a fresh checkout and from a copy at another path whose files carry
  > non-git permission bits and which contains `__pycache__/`, a stale `aisef.egg-info/`, `dist/` and `build/`. The
  > frozen and published digests are those of the CPython 3.12 staging build; the published 2.2.0 files are rebuilt
  > from tag `v2.2.0` on the same four interpreters. **Not claimed:** equality under another deflate implementation
  > (e.g. zlib-ng) or another OS; a changed execute bit or a file added inside the shipped trees is a different source.
* **Tests:** unit — two tars differing only in member modes normalise to identical bytes (0600→0644, 0700 dir→0755,
  exec→0755); CI — NEW `staging.yml` job `repro` (needs `build`; matrix 3.11–3.14): record toolchain JSON
  (`sys.version`, `zlib.ZLIB_RUNTIME_VERSION`/`ZLIB_VERSION`, `build` version, image), rebuild from the fresh checkout
  and from the perturbed copy and `sha256sum -c` against the 3.12 `build` digests, then rebuild tag `v2.2.0`
  (`SOURCE_DATE_EPOCH` from `V2.2.0-RC2-FREEZE.json`) and compare to its frozen digests; the same toolchain record is
  added to `build`. A static test (`tests/v2/test_v23_repro_contract.py`) pins `[build-system].requires == ["setuptools==84.0.0"]`, the toolchain-record step in **both** `build` and `repro`, `runs-on: ubuntu-latest`, the matrix, `needs`, both checks, the
  perturbation lines and the v2.2.0 step, so the coverage cannot be removed silently. The perturbed leg is red-before
  until `repro_dist` normalises modes. Cost: ~3 runner-minutes × 4 legs, free on a public repo; it runs on
  `release/**` pushes, so it needs DISC-1. A diverging leg is a measurement: fix it or amend the contract explicitly
  and narrow the matrix — never drop the leg silently.
* Claim check: this narrows only the never-tested "any host" reading (already false for working-tree builds) and
  widens what is tested (one interpreter → four; mode/path/`__pycache__`/egg-info independence). It is explicit, so the
  published claim is not silently weakened.

## 7. Other W1 items

* **F2:** typed test markers (`category ∈ {sealing, platform-harness}`, `id`, `reason`) generate the release exception
  set; a meta-test fails on a product-category marker, a marker without a checklist ID, or an unmarked exception.
  The v2.1.0 56-row allowlist is history, not reused.
* **L1-TESTENV (V21-36, #34):** kill tests never see a real `opencode` on PATH; arming state reset per test module;
  platform-parity preflight (run the W1 targeted tests on macOS + Linux server + Windows CI before integration).
* **#38:** in **round v2.3 only**, a node whose own supersession is missing becomes a problem (stale negative); the v2.2 path (`currency_dag.py:121-124`) is unchanged so Q0's known-bad `observed` does not move. **#14/#15:** Option C pins
  the ruling digest and uses its platform constant; first tests for `verified_reuse_current`.
* **C4:** qualifying test (candidate==base → 0 reviewer/scanner/quality calls), then `WONT_DO` on the existing
  directive (DAG §5a). **Lane-M:** roadmap box reconciled, no re-measure.
* **L1-AUTHCHK (gap-fill, 12 defects):** tightening-only hardening of the authority checkers (exists-semantics
  derivation, fail-open discovery of aliased/shell/`getattr` destructive calls, `SCOPES` missing `validation/v21` +
  `validation/qualification` with 5 unledgered process sites, POSIX-unguarded signal-0, Windows host-table read
  failing open, `except_boundaries` false PASS shapes, relative-import escape, signal/clock static-check bypasses,
  `authority_limits` dynamic denylist). Red-before fixture per defect; Q0 byte-identity or STOP Q0-1.
* **CI-INCR-JOB (L1-CIGOV; the `mutation.py` hunk via L1-F5):** NEW `.github/workflows/mutation-incr.yml` on the
  `b1-linux.yml` pattern (opencode-absent guard, XDG dirs under `runner.temp`, `contents: read`, `fetch-depth: 0` —
  a shallow clone is UNRESOLVED, N10; never runs `b1_bindings_check`). Job `gate` (push `release/**`, PR):
  `mutation.py --check --states`, fails on any INVALIDATED/UNRESOLVED. Job `plan` (dispatch): `--affected --json`.
  Job `measure` (dispatch only, `needs: plan`): `--run-affected` on the listed scope. A static test pins guard,
  permissions, no `secrets.`, and the dispatch-only measure.
* **V21-40 (L1-F5):** read side only — `execution_order.py:75` hashes the committed **LF** form
  (`m.committed(ROOT, path, _lf(path.read_bytes()))`) and `:52` likewise; `mutation.committed()` unchanged; no message
  change (Q0 byte-identical). Test: commit the sweep record LF, rewrite it CRLF → `check()==[]`, `from.sha256` = LF blob
  digest (red-before: "not a file committed at HEAD").
* **#6 non-A2 part (L1-CIGOV):** `tests/installed_product_smoke.py` runs `aisef demo` and asserts the three printed rows
  (exit status alone proves nothing: `demo.main` returns 0); `--writer <2.2.0 aisef>` writes the run with the 2.2.0
  wheel and verifies it with the candidate, asserting RUN.json `kernel_digest` = `c2d356b1…` (historical-2.2 read).
  A meta-test in `test_v23_release_governance.py` pins both steps in `staging.yml` (red-before).
* **#17 (L1-QUAL, append-only, not a STOP):** NEW `c2_closure_audit.py --erratum` writes once (`open "x"`)
  `closure-evidence/v2/v2.3/C2-FINAL-FREEZE-ERRATUM.json` (state `INVALIDATED`, frozen 43 vs committed 35 entries,
  reason: `history_freeze()` counted working-tree entries); `check()` accepts the mismatching C2-FINAL row only when
  the erratum names it with state INVALIDATED; the C2 freeze candidate is never edited. Red-before: `--check` today
  reports "C2-FINAL: the first 43 entries are not the frozen ones".
* **#29 (L1-CIGOV):** `conformance.yml` loses its weekly `schedule:` (dispatch-only); a static test forbids any
  scheduled workflow from referencing a secret other than `GITHUB_TOKEN` (red-before on `ANTHROPIC_API_KEY`). The master
  cron keeps firing until the owner-authorized master merge (owner notice).
* **#30:** ACCEPTED_LIMITATION — `diagnostic.yml` is a legacy reproducer, not a v2.3 gate (BASELINE CI note).
* **V21-36 (L1-TESTENV; guard hunk via L1-F5):** no test file is edited (fan-out §2.8); `mutation.main` refuses
  (exit 3) when an executable `opencode` is resolvable on `PATH`, before any `run_target`. NEW `test_v23_testenv.py`.
* **#34 (L1-TESTENV):** NEW AST scan — any test that patches `_ARMED` must also patch `_RUNTIME_ARMED` (known-bad inline
  source red-before); the three named tests pass after `arm_runtime()` in one interpreter. No existing file edited.
* **V21-74, V21-87:** closed NOT_APPLICABLE by the delegated ruling (OWNER-DIRECTIVE-2026-10-15-B.md:50, owner item 6):
  skips counted per group offline (`offline_groups.sh`), Docker group unrun (running it is a W3 privileged-ops item).
* **C4 (L1-TESTENV):** the qualifying test is a NEW file (`test_v23_c4_noop.py`), not an edit of `test_app_run.py`.
* **Compatibility tests:** CT-5 (ledger entries 1–12 value-identical to `v2.2.0`, seq strictly increasing) and CT-6
  (no committed `closure-evidence/v2` row of `399b775f` changed at HEAD) in NEW `test_v23_release_governance.py`
  (L1-CIGOV); CT-8 (tag `v2.2.0` rebuilds to `8c94dd6b…`/`102cda44…` with the current `repro_dist.py`, §6) and CT-9
  (both `kernel_digest` implementations = `c2d356b1…` on `e865d65c`; #41 itself stays W2 L2-RECORD) in NEW
  `test_v23_repro_contract.py` (L1-BUILD).
* **#46 (lane D5):** * #46 MUST be implemented as NEW ungated test file(s), e.g. `tests/v2/test_v23_live_tree_checks.py`, that call the live-tree checks directly.
  * `GATED` and every gated test body stay byte-identical; `tests/v2/sealing_gate.py` changes **only** for `V22_REPLAYED` (§2.6), and that commit waits for ROUND-AUTH (ledger seq 8, §12). `tests/v2/test_sealing_gate.py` is not edited.
  * Editing `sealing_gate.py` changes an existing segment of a test file (I4, no tier applies) and re-opens 47 / 1,661 / 10.24 rows-h, `_attempt` included (M13). Do it only if the owner rejects the duplicate live check staying inside the sealed tests.
* **Gap-fill W1 items in other lanes:** a unit-leg step fails when a test leaves `closure-evidence/` dirty (L1-CIGOV);
  `aisef2/plan/obligation.py` gets mutation targets (L1-F5 — new targets are measured in W1's targeted run);
  `release_calibration --check` runs in CI (L1-QUAL + L1-CIGOV).

## 8. Exact affected files

| Lane | Edits (only these) | New |
|---|---|---|
| L1-F5 (W1a) | `validation/v2/{mutation,currency_dag,version_forward,execution_order,checker_calibration,b1_bindings_check}.py` (mutation.py: F5 source rule, read-time v2.3 supersession, audit dispatch, V21-36 guard, `--states/--affected/--run-affected`; checker_calibration: `V2_2_0`, b1 known-bad `kernel=`, execution_order `at=`); `validation/qualification/p5_falsifiability.py` (round-v2.3 guard); `tests/v2/sealing_gate.py` (`V22_REPLAYED` only — re-opens 47 targets / 1,661 mutants, all inside the single targeted run, M13; commit waits for ROUND-AUTH); `tests/v2/p0/test_freeze_manifest.py` (V21-40: read the committed LF form at :163; inside the same 47) | `validation/v23/{__init__,impact,observe,rounds,replay_v22,audits}.py`; `tests/v2/{test_v23_impact,test_v23_rounds,test_v23_q0_byte_identity,test_v23_survivor_audits,test_v23_live_tree_checks,test_v23_execution_order_lf}.py`; `closure-evidence/v2/v2.3/{MUTATION.json,SURVIVOR-AUDITS.jsonl,<node>-<k>.json}` (append-only) |
| L1-QUAL | `validation/qualification/{release_calibration,p5_acceptance,v21_conformance_ruling,q2,c2_closure_audit}.py`; additive-only `tests/v2/{test_c2_p5_acceptance,test_qualification_release_mode}.py` | `tests/v2/{test_v23_version_bump,test_v23_calibration_rows,test_v23_c2_freeze_erratum}.py`, `closure-evidence/v2/v2.3/C2-FINAL-FREEZE-ERRATUM.json` |
| L1-CIGOV | `.github/workflows/{release,staging,tests,conformance}.yml`; `tests/installed_product_smoke.py` | `.github/workflows/mutation-incr.yml`, `.github/workflows/relgov-probe.yml` (only in the owner's probe commit P, never on the branch), `validation/qualification/release_governance.py`, `validation/v23/released_evidence_guard.py`, `tests/v2/{test_v23_release_governance,test_v23_released_evidence_guard}.py`, `closure-evidence/v2/v2.3/REL-GOV-01-W1-PROBE.json` |
| L1-BUILD | `validation/qualification/repro_dist.py`; additive-only `tests/v2/test_release_repro_dist.py` | `tests/v2/test_v23_repro_contract.py`; `docs/v2.3/drafts/BUILD-REPRO-CONTRACT.md` (lands on master at W6, §6) |
| L1-F2 | `validation/qualification/release_qualify.py` | `validation/qualification/test_markers.py`, `tests/v2/test_v23_markers_meta.py` |
| L1-TESTENV | none (no existing test file, no `__init__.py`, §2.8) | `tests/v2/{test_v23_testenv,test_v23_c4_noop,test_v23_platform_parity}.py` |
| L1-LIFECYCLE (W1b) | `aisef2/orchestrate/story_runner.py` (`Stage`, `_Stages`, the `_attempt` handler; imports only added); `aisef2/app/run.py` (the refusal branch at :693 only, §4.4); the append-only kill-set/target hunk in `validation/v2/mutation.py` goes through L1-F5 | `tests/v2/{test_v23_story_lifecycle,test_v23_story_golden}.py` |
| L1-AUTHCHK | `validation/v2/{destructive_authority,cleanup_authority,except_boundaries,refmodel_independence,kernel_static_checks,probe_static_checks}.py`, `validation/qualification/authority_limits.py`, `destructive_sites.json` (append only), their tests | red-before fixtures under `tests/v2/fixtures/` |

`mutation.py` `COPY` gains `validation/v23` (new runs only; old `tree_sha256` values are provenance, never re-checked).
Read-only in W1: `validation/qualification/{s2_mutation_record,v21_mutation_record}.py` (frozen criteria), every
existing `closure-evidence/**` file, `aisef2/**` except `story_runner.py` and `run.py:693` (refusal branch) in W1b.

## 9. Negative-test catalogue (each must FAIL for the named reason — red-before where it is a behaviour change)

| Case | Mutation | Expected |
|---|---|---|
| N1 stale target | edit a line inside a target's slice | `INVALIDATED (I1)` |
| N2 unrelated edit | edit an unreferenced helper in the same module | `VERIFIED_REUSE` + `unreferenced_changes` (today: stale) |
| N3 referenced helper | edit a helper the target or a kill test calls | `INVALIDATED (I2)` |
| N4 weakened kill test | replace a kill test body with `pass` | `INVALIDATED (I4)` — **today PASSES `--check`** (red-before) |
| N5 dropped killer | remove the `killed_by` file from the kill set | `INVALIDATED (I3)` — today passes |
| N6 generator change | change an operator in `mutants()` / an imported Enum's members | `INVALIDATED (I5)` — today passes |
| N7a | a windows entry for a `posix` target; a posix entry for a `windows` target | `INVALIDATED (I6)` |
| N7b | a darwin entry for a `posix` target | passes I6, report prints `darwin`. Red-before: frozen §2.4 would INVALIDATE it |
| N7c | a legacy row-less entry with no worker artifact | `UNRESOLVED (I6)` |
| N7d | an entry with both `<tree>/` and `<tree>\`, or with both `/opt/homebrew/` and `/usr/lib/python3.12/` | `INVALIDATED` (contradictory) |
| N7e | a path that only appears in a fixture or assertion | not evidence |
| N7f | a worker history digest mismatch | W refused → `UNRESOLVED` |
| N7g | shares a `tree_sha256` with a linux entry but has no evidence of its own | `UNRESOLVED` (co-occurrence refused) |
| N8 tamper | flip a `SURVIVED` entry to `KILLED` with a consistent-looking bracket | `INVALIDATED (I7)` |
| N9 unauthorized | add a target to the Option C table / alter the ruling file | not reused → `INVALIDATED` |
| N10 shallow clone | basis commit unavailable | `UNRESOLVED`, gate FAIL |
| N11 version bump | `pyproject` → `2.3.0.dev0`, no other change | calibrations `VERIFIED_REUSE`; M5 tests green; `calibrations.py` unchanged |
| N12 bump + fixture | N11 + one calibration fixture byte | `INVALIDATED`, tests fail for that reason |
| N13 kernel neutral edit | (a) the M4 probe (comment appended) | R6/R7 fire on nothing; invalidated = targets with a data reader of `story_runner.py` (R2) or an incomplete observation (R1), each listed with its reason; v2.2 replay PASS |
| N13b added import + added class | `from enum import Enum` + a new top-level class added to `story_runner.py` | R6 → `INVALIDATED` for every kill file that loads `story_runner.py` (strict R6, §4.7(b)) |
| N15 reach soundness | a dependent whose kill file calls the changed function only through a branch the unmutated run does not take | `INVALIDATED` (the function is in the static closure of *E*) |
| N32 dirty tree | an uncommitted edit to a target file or any COPY path | every target `UNRESOLVED ("dirty tree")` — never `VERIFIED_REUSE` |
| N33 runner settings | change `TIMEOUT` or `_confirmed` | `INVALIDATED (I9)` for every target |
| N34 version-named record | a v2.2-era `V<cur>-PROBE-CALIBRATIONS.json` under the current version string | not `MEASURED`; resolved through the identity path |
| N14 always-PASS engine | an engine whose `state()` returns `VERIFIED_REUSE` | rejected by the engine's calibration suite |
| N16 unhooked child | test_k runs `subprocess.run([sys.executable, "-c", "from aisef2 import toy; toy.g()"], env={"PATH": …})` (reach control d) → change the body of `g` | `INVALIDATED (R1)`. With `os_trace`: R2 (the child opened toy.py). Red-before: "unreached". |
| N17 non-Python child | test_k asserts the output of `wc -l aisef2/toy.py` → append a comment line | `INVALIDATED (R1)`; with `os_trace`: R2. Red-before: no segment changed. |
| N18 import-time | toy2 (imported by toy) gains `sys.setrecursionlimit(60)`. Variant: remove `@register` from an unreferenced `h` while test_k asserts `len(toy.REG) == 1`. | `INVALIDATED (R6)`. Red-before: reusable. |
| N19 data read | test_k does `assertNotIn("TODO", Path(toy.__file__).read_text())` → add `# TODO` between two top-level defs | `INVALIDATED (R2)`. Red-before: no segment changed. |
| N20 listing | test_k asserts the sorted `aisef2/*.py` names → add `aisef2/new.py` | `INVALIDATED (R3)`. Positive: adding `tests/v2/test_new.py` gives `VERIFIED_REUSE` (discount). Negative: adding `tests/v2/newdir/test_x.py` gives `INVALIDATED`. |
| N21 discovery | add `tests/v2/zz/__init__.py` = `raise SystemExit(1)`. Variant: add `tests/v2/p9/test_k.py` with a failing test. | `INVALIDATED (R4)`. Red-before: not in the s2 closure. |
| N22 resolution | test_k uses `toy.watched` → add an empty `aisef2/toy/__init__.py` | `INVALIDATED (R5)`, decided statically. |
| N23 computed name | `run(k) = getattr(sys.modules[__name__], "_do_" + k)()`; `pick(x) = "b" if x > 1 else "a"`; test_k calls `run(pick(1))` → change the body of `_do_b` | `INVALIDATED (R8)`. Red-before: tier S reusable. Positive: a `RESOLVED_SITES` entry for `registry.resolve` clears an unreferenced def in `evidence.py`. Negative: change that site's call text → `INVALIDATED`. |
| N24 closure of E | the N23 site sits in a def reached only through a branch the unmutated run does not take | `INVALIDATED (R8)`. A reach.py changed-only watch used as E → tier R unavailable. |
| N25 platform | present `campaign-8/read-set.json` for the Linux claim | `UNRESOLVED (R0)`. Same for python minor 3.14 vs the runner's 3.12. |
| N26 copy run | test_k copies toy.py to a temp dir and runs it with `python -I -B` (the `test_v21_confine` pattern, `docs/v2.1/decisions/B03-R3-REACH.md:101-105`) → change the body of the copied function | `INVALIDATED`: R1; with `os_trace`, R2. |
| N27 lost hit | test_k lowers `RLIMIT_NOFILE` to the open count, calls `g`, then restores it | `lost > 0` → `INVALIDATED (R1)`. |
| N28 test as data | kill file F2 of the target counts `def test_` in every `tests/v2/test_*.py` → add a test method to test_k | `INVALIDATED (R2 for F2)`. Red-before: `additive-test-change`. |
| N29 enumeration | test_k asserts `[n for n in dir(toy) if n.startswith("check_")] == ["check_a"]` → add `def check_b(): pass` (module status stays unchanged, `reach.py:146`) | `INVALIDATED (R8, dir())`. |
| N30 D2 check | `aisef2/reg.py` does `importlib.import_module("aisef2.plug")`; no change | With the s2 closure only: `UNRESOLVED ("S(F) misses aisef2/plug.py")`. With D2(c): the check passes. |
| N31 non-code root | test_k reads `ROOT / "docs" / "v2.1" / "schema.json"` → change one byte of it | `INVALIDATED` (R2; and statically in S(F) by D2(b)). Red-before: literals are resolved only under aisef2/, validation/, tests/. |

Survivor-audit negatives (`tests/v2/test_v23_survivor_audits.py`, §2.10):

| Case | Mutation | Expected |
|---|---|---|
| NA1 | Replay `abbd88b5`: copy a live v2.1 entry, set the new `source_sha256`, append it as a v2.3 line | refused (no `result`/`review`). The same edit in place in `AUDITS_REL` → released-evidence guard FAIL. |
| NA2 | Edit a committed v2.3 line | "committed line N changed"; no line counts |
| NA3 | A valid v2.1 entry at equal `source_sha256` against a v2.3 entry | `unaudited survivor` |
| NA4 | A line bound to an older v2.3 entry of the target | does not cover the newest entry |
| NA5 | `auditor == refuter`; or verdict ≠ NOT_REFUTED; or a cite unresolvable at `snapshot` | problem |
| NA6 | A cited file changed after `snapshot` | `AUDIT_INVALIDATED` |
| NA7 | A line for a `NO_AUDIT` target | problem |
| NA8 | A revoke line | removes coverage; a revoke naming a missing line is a problem |
| NA9 | `v21_mutation_record` accounting of the V2.1 record | byte-identical before and after |

## 10. Measurement protocol and expected cost

* Hardware reported per run (Apple M1 8-core/16 GB local; `<mutation-server>` server for mutation workers; GitHub free
  runners for CI). Cold = what the v2.2 rule forces for the change (re-measure every target of every touched module
  + release-time regeneration of the currency DAG); incremental = F5 classification + re-measure/re-derive of the
  `INVALIDATED` set only. Change classes: no-op/version bump (N11), one-function kernel change (E5 itself),
  shared-helper change, kill-test change, cross-platform record. Wall time, mutants run, targets reused/re-measured.
* **Two baselines, reported side by side, never mixed:** (i) the v2.2 rule (whole target file; under-strict on
  dependencies, M1) and (ii) the sound conservative rule without F5 precision (re-measure every target whose kill-test
  static closure contains a changed file, M8). F5 must beat (ii) by ≥ 50 % wall time on the scoped classes and must
  never accept less than (ii) detects. Where F5 costs more than (i) — dependency changes (i) never re-checked — the
  difference is reported as added detection, not as a regression.
Rows-h = Σ(`seconds` + `overhead_s`) over `results[].files` (the fanout.py / M8 convention). T0-h = the `t0` + `original` rows. `MUTATION-IMPACT-BASELINE` §2.1 serial = rows-h + T0-h.

The 327 runner-1 targets (P1–P6, C2-ORCH, C2-P10) have no row timings. Their cost is **[E]** in two parts:
* "est": estimated from each kill file's median T0 PASS time, scaled by the actual/estimate ratio 0.764 calibrated on the 667 timed targets;
* "unest": targets whose kill files have no T0 row anywhere, priced at the per-mutant median–mean, 5.81–60.64 s. `test_no_dual_authority.py`, the kill file of the 5 `old_path_audit` targets (497 mutants), is untimed in every record.

Measured at `1bf5dd2f`.

| Re-open (lane) | Rule | Targets | Mutants | Surv | Rows-h | T0-h | Untimed tgt/mut → [E] h | Longest target (h) |
|---|---|--:|--:|--:|--:|--:|---|--:|
| `tests/v2/sealing_gate.py` (#46, as in v1 design) | I4, no tier | 47 | 1,661 | 5 | 10.24 | 0.48 | 23/901 → 2.22 est + 0.89–9.33 unest | 9.75 `_attempt` |
| `validation/v2/{mutation,execution_order}.py` | closure∩COPY; tier S leaves the same 5 | 5 | 497 | 0 | – | – | 5/497 → 0.80–8.37 | – |
| `validation/v2/version_forward.py` | closure∩COPY | 21 | 1,042 | 2 | 9.96 | 0.46 | 10/631 → 0.99 + 0.80–8.37 | 9.75 |
| same, edit confined to `CURRENT_ROUND`, `select_for_tree`, `current_context`, `resolve_upstream` | + tier S | 5 | 497 | 0 | – | – | 5/497 → 0.80–8.37 | – |
| `validation/v2/currency_dag.py` | closure | 0 | | | | | | |
| `validation/qualification/{release_calibration,p5_acceptance,v21_conformance_ruling}.py` | S2 closure → tier C | 21 → **0** | 1,042 → 0 | | 9.96 → 0 | | | |
| `validation/qualification/authority_limits.py` (L1-AUTHCHK) | S2 closure → tier C | 31 → **0** | 1,797 → 0 | | 58.21 → 0 | 1.26 → 0 | | |
| `q2.py`, `repro_dist.py` / `c2_closure_audit.py`, `release_qualify.py`, `tests/installed_product_smoke.py`, workflows, README, docs | closure → tier C | 5 / 0 → **0** | | | | | | |
| L1-AUTHCHK own targets: `destructive_authority` 6/202, `cleanup_authority` 16/230, `except_boundaries` 9/166 | I1 upper bound (every target of the module) | 31 | 598 | 4 | 0.40 | 0.02 | 9/166 → 0.96 | 0.06 |
| `cleanup_authority.py` dependents | closure∩COPY | 5 (`old_path_audit`, same 5) | 497 | 0 | – | – | 5/497 | – |
| 7 additive-only test edits (§8) | I4 additive | 0 (5/497 each if any existing segment changes) | | | | | | |
| NEW `aisef2/plan/obligation.py` targets | generator only, nothing executed | 7 | 89 | – | [E] 0.07 (plan-module rate 2.87 s/mutant) – 1.50 (mean) | | | |
| E5 own module: `_attempt` + `run_story` (additive imports, §4) | I1 | 2 | 337 | 2 | 9.83 | 0.11 | – | 9.75 |
| E5 enum-swap mutants added to `_attempt` by `Stage(Enum)` (§4.2) | generator only, nothing executed | — | ≈ +156 | – | [E] 0.25 (median 5.81 s) – 2.6 (mean 60.64 s) | | | |
| E5 own module: all 11 (imports or module statements edited) | I1 | 11 | 411 | 2 | 9.96 | 0.46 | – | 9.75 |
| E5 dependents (upper bound; tier S clears 0; tier R measured in W1, ≤ 25 min) | closure∩COPY | 640 | 17,897 | 354 | 276.96 | 21.11 | 81/2,353 → 4.65 est + 2.68–27.96 unest | 36.55 `run.py::execute` |

**W1 totals.** Unions, so a target re-opened twice counts once. Obligation targets are added in the sum columns.

| Scope | Targets | Mutants | Rows-h + T0-h | [E] untimed + obligation | Serial-h total | Wall floor |
|---|--:|--:|--:|--:|--:|--:|
| Baseline (ii): W1a under the S2 static closure, no F5 tiers | 89 | 3,191 | 68.71 + 1.75 | 23 untimed / 901 mutants | ≥ 70.5 | – |
| W1a as designed (closure∩COPY, `sealing_gate.py` edited) | 63 | 1,891 | 10.50 + 0.49 | 2.22 + 0.89–9.33 + 0.07–1.50 | **14.2–24.0** | 9.75 h |
| W1a lean — **not attainable** (needs `sealing_gate.py` unchanged, but gate 3 needs `V22_REPLAYED`) | 36 | 1,095 | 0.40 + 0.02 | 0.96 + 0.80–8.37 + 0.07–1.50 | **2.3–11.3** | per-target ≤ 0.06 h timed (`old_path_audit` untimed) |
| W1b E5 upper bound | 651 | 18,308 | 286.92 + 21.57 | 4.65 + 2.68–27.96 | 315.8–341.1 | 36.55 h |
| **W1 total, upper** (W1a as designed ∪ E5 upper) | 673 | 18,740 | 287.32 + 21.58 | 4.65 + 2.68–27.96 + 0.07–1.50 | **316.3–343.0** | 36.55 h |
| W1 total, lean floor — **not attainable** (strict R6 re-opens all 11 own targets and every loader; see SCALE-1) | 38 (+7 new) | 1,432 (+89) | 10.22 + 0.13 | 0.96 + 0.80–8.37 + 0.07–1.50 | **12.2–21.2**, + tier-R E5 dependents (0 … 640 targets / ≤ 306.9) | 9.75 h, or 36.55 h if `execute` is in the reach set |

* This replaces "≈ 3–6 h at 2–4 workers". A single target runs serially, so W1a as designed cannot finish under 9.75 h wall: `_attempt` is in its re-open set (M13).
* Against baseline (ii), W1a falls by −85 % rows-h (tier C alone) to −99 % (lean). Both are computed from the records, not run. The run itself happens once, after W1b (§4).
* The E5 term is decided by tier R. Its scope and the serial-hour price of the reached set MUST be written to the W1 report before the targeted run.
* Survivors in the measured scope feed the §2.9 audit workload.
* **Realistic scale with today's recorders (lanes D2/D3 — this is what the owner decides, §12 SCALE-1):**
  * 31 kill files hash the whole kernel (`kernel_digest`, `run.py:93-100`): under R2 any `aisef2/**.py` byte — E5
    included — re-opens **≥ 444 targets / 13,482 mutants**.
  * 60 of the 80 kill files that open `story_runner.py` spawn unobserved children: without `os_trace` (`strace -f`,
    Linux only) tier R clears **0** E5 dependents, and R1 re-opens 472 targets for *any* Δ under a COPY root.
  * 327 legacy targets (10,078 mutants) are `UNRESOLVED (I6)`: re-measure **[E] 16.2–182.5 serial-h**, or an owner ruling.
  * The union is well over half of the 27,400 live mutants — close to the full campaign the owner ruled out without
    approval. Complete observations need Linux hardware (SRV-1 or, after DISC-1, GitHub runners).
* Editing `validation/v2/mutation.py` stales its row in `v2.2/CONFORMANCE-RULING.json`; F5-ROUND gives it a v2.3
  conformance round (no mutants).

## 11. W1 exit gates (in addition to the DAG §6 common gate)

1. N1–N34 and NA1–NA9 behave as specified; every red-before case is shown red on the base.
2. **On the unchanged base**, `mutation.py --check --states` MUST print exactly:
   * 994 targets in total;
   * **667 `VERIFIED_REUSE`**, of which 625 are `v2.2.0-accepted` and 42 come via the ruling. 664 are `posix` (flavor: 461 darwin, 62 linux, 141 unproven) and 3 are `windows`;
   * **327 `UNRESOLVED (I6: no platform evidence)`**;
   * 0 `INVALIDATED`.

   These figures come before other lanes' rules (I1–I5, I8) are applied to the base.

   **CI is truthfully FAIL until then.** The `mutation-incr` `gate` job MUST fail for exactly those 327 targets, with no allowlist.

   **W1 exit** requires all 994 to be in {`MEASURED`, `VERIFIED_REUSE`}: the 327 are either measured by W1's targeted run or covered by an owner I8 ruling. The v2.2 round MUST replay byte-identically.
3. **Q0:** the record is byte-unchanged **and** `checker_calibration --check` PASSes at HEAD with the mutation and
   currency_dag cleans computed in round v2.3 (after the staged cut-over, §2.5); the 11 `V22_REPLAYED` tests PASS at
   v2.2.0; `test_v23_q0_byte_identity` (i) and (ii) PASS. Needs ROUND-AUTH (§12).
4. EVID-COUPLING-01: N11/N12.
5. E5 landed with the fault matrix (§4.5) and the golden byte-identity test (§4.6); `aisef2/` changed only in
   `story_runner.py` and `run.py`'s refusal branch; qualified through F5 — `currency_dag --affected` lists only nodes
   whose own guard fired, re-derived as MEASURED; no other Q0 entry moves.
6. REL-GOV guard in `release.yml`, truthful FAIL until the owner configures `pypi`; W1 probe evidence recorded once run.
7. BUILD-REPRO contract tests + v2.2.0 sdist rebuild bit-identical on the four CI interpreters.
8. Measured cold-vs-incremental table. The ≥ 50 % target is judged per change class against baseline (ii); a class
   that does not reach it (expected: one-function kernel change, §10) is reported **not met** — never narrowed by
   relaxing R1/R2.
9. Full suite (main tree) + CI 6 legs + sealing + lint + wheel green (needs DISC-1).

## 12. STOP points (genuine; everything else proceeds)

* **DISC-1 (publication control):** the W1 exit CI (6 unit legs, sealing, the new `repro` and `mutation-incr` jobs)
  needs the branch on GitHub, and the branch holds security findings (`CODE-AUDIT.md`, `THREAT-MODEL.md`,
  `RISK-REGISTER.md`) → owner chooses: (a) push `release/v2.3-big` after a disclosure review, or (b) a sanitised CI
  branch without those three files (fix commits written neutrally). Work proceeds locally until then.
* **REL-GOV-01 (publication control):** owner configures `pypi` (§5) and runs the W1 tag-push probe on a commit
  parented on `origin/master` (no DISC-1 dependency); the agent prepares the probe file and the evidence script only.
* **ROUND-AUTH (owner authority ledger; also covers the `V22_REPLAYED` gated-test wiring that ledger seq 8 reserves for owner approval — `C4_SEPARATE`, no automatic migration; draft: `docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT.md`):** W1a's `mutation.py` edit stales the `mutation.py` row of
  `v2.2/CONFORMANCE-RULING.json`; a v2.3 CONFORMANCE-RULING (which ORCH needs) MUST quote a committed owner ledger entry
  for the v2.3 qualification round, and the ledger holds seq 1–12 only. The agent drafts seq 13; the owner commits it.
  Blocks exit gate 3, not the start of W1a/W1b.
* **SCALE-1 (scope of requalification; the owner ruled out a full campaign without approval):** the honest F5 scope
  for W1 is close to a full campaign (§10). Owner chooses: (a) one targeted run of the computed scope on Linux
  (free compute; needs SRV-1 or DISC-1 + GitHub runners); (b) PLAT-1 — an I8-pinned ruling accepting
  "platform-unbound v2.2.0 currency" for the 327 legacy targets; (c) a DIGEST-READ discount ruling for kill files that
  only hash the kernel (needs its own proof); or a combination. Default until decided: build and prove the engine
  (W1a, all local); measure nothing large.
* Not a STOP — **SRV-1 (notice):** user-level mutation workers on `<mutation-server>` (no root, cron or Docker; disk guard ≥ 15 GiB; backups untouched) are allowed; the owner is told and may veto.
* **Q0-1 (immutable evidence contract, conditional):** only if a W1 change cannot keep the Q0 record byte-identical (M6).
* Not STOPs: the 9 open OWNER_DECISION rows and the 7 W0-closure items (DAG §5a) are asked at their own W2–W5 design
  freezes with defaults already chosen; spending stays 0 (no paid provider call in W1; GitHub CI free on the public repo).

## Amendment A1 (2026-11-21, W1a increment 1) — §2.9 R5–R8 scope; erratum §2.4.4 / §11 exit gate 2

*Appended under the freeze rule (line 3). It amends §2.9 R6 — and, because they share its scope, R5, R7 and R8 — and
corrects the flavor figures of §2.4.4 and §11 exit gate 2. Nothing above is edited. I4, the D2 check and the R1 static
scan keep all of S(F) exactly as frozen.*

### A1.1 §2.9 R5–R8 judge the code F's processes run, not every file of S(F)

**Why.** At real scale S(F) is degenerate. D2 (b) adds every file under a directory named by one whole constant, and
`registry.py`'s `TESTS_V2 = "tests/v2"` lies in every kill file's S(F) (through `tests/v2/__init__.py`). So every S(F)
holds every `tests/v2` file.
- Measured at basis `da3ea33f3b69…` ∪ the increment's head: all 262 kill files reach `registry.py` by import, so every
  S(F) holds all 569 `tests/v2` files.
- The import-reached part, code(F) below, holds 321–978 files (median 338).
- The adversarial review measured the exact S(F) of two kill files at 7,547 files.

Under the frozen R6 letter ("f ∈ Δ ∩ S(F)"), any NEW `tests/v2` file has module
status "new" and re-opens every target. The first real run of this increment showed it: 667 / 667 targets
INVALIDATED (R6), all because of the increment's own new test file. That letter contradicts two frozen rules, the N20
positive ("adding `tests/v2/test_new.py` gives VERIFIED_REUSE") and §2.8 ("new behaviour gets NEW test files"). The R3
registry discount exists to keep exactly those files cheap.

**Rule.** It replaces the scope of R5, R6, R7 and R8 only.
- **code(F)** is the fixpoint of D2 (a) the s2 closure, (c) dotted import strings and (d) the discovery set, at basis ∪ now.
  This is what F's process imports. D2 (b) literal paths are not followed.
- **ran(F)** = code(F) ∪ (S(F) ∩ (`O(F).loaded` ∪ every `.py` path of `O(F).opened` tagged `load`)).
- R5 and R6 are judged on code(F) before any observation. After R0–R3 they are judged again on ran(F) \ code(F).
- R7's reference test and R8's tier-S scope are ran(F).
- With no observation, R1 fires for any Δ ≠ ∅ before R7 and R8 are reached.
- An `opened` path tagged `load` that is not a `.py` file counts as data for R2, as does a path with any tag other than `load`.
- R6 also fires when a top-level name's binding statements in f ∈ Δ are the same texts in another order. The later
  binding wins, and `reach.changed()` cannot see the swap: it compares a name's defs as a sorted multiset and leaves
  plain defs out of the module code. I1 likewise keeps the slice in statement order.

**Soundness argument (for the observed, unmutated run).** Take f ∈ Δ ∩ S(F) with f ∉ ran(F).
1. If O(F) is missing, inadmissible or incomplete, R0 or R1 already gives UNRESOLVED or INVALIDATED for any Δ ≠ ∅
   ("any path of the tree may be read or run"). They fire before R5–R8 decide anything, so the narrowing changes
   nothing in that case.
2. Now let O(F) be admissible and complete. R0 passes; `lost = 0`; `unparsed_lines = 0`; every child is hooked or
   covered by `os_trace`; and, without `os_trace`, no R1_UNSEEN word appears in S(F). Then every process of F's run is
   observed. Every tree file a hooked process executes as Python source was read by the import system (tagged `load`)
   or opened some other way (data). The D2 check keeps both inside S(F).
3. A file read as data and then executed (exec or compile of its text) is caught by R2 whenever it is in Δ, since R2
   counts bytes.
4. So suppose f is never imported statically by F (f ∉ code(F)) and no observation saw it loaded or load-opened.
   Then f was not executed in any process of F's observed run, and its import-time statements and defs cannot have
   influenced that run.

**Residuals (declared in the engine docstring).**
- **Mutant-only execution (new with this amendment).** A Δ file named only by a literal (D2 b) could be executed only
  under a mutant, through a literal-path loader that the unmutated run never reached: `spec_from_file_location`,
  `SourceFileLoader` or `run_path` with all-literal arguments, or a child `[sys.executable, "<path>"]`. The frozen
  R6/R7 letter covered this case statically; this amendment does not.
  - The frozen design already carries the same class for R1–R3, which judge only the unmutated run: a data read,
    listing or child that only a mutant makes is never observed.
  - A loader site whose module name or path is not a literal is an R8 site (W1a increment 1 widened R8 to every
    argument).
  - A literal dotted module name is D2 (c), so it is in code(F).
- **The argument rests on the recorder.** It assumes every module whose source a hooked process executes appears in
  `loaded` or is opened `load`. That includes a script a child runs by path, and a module executed from a bytecode
  cache whose source the process did not open. The runner's tree is a fresh copy with no `__pycache__`.
- C code that executes tree files is seen only through `os_trace` (§2.7, unchanged).

**Effect on the measured counts: none in this increment.** No recorder exists yet, so every target with Δ ≠ ∅ under
COPY stops at R1 before R7 and R8.
- Real run at W1a increment 1 (basis `da3ea33f3b69…`, the pinned full v2.2.0 sha; head = the increment's engine
  commit; Δ = 10 added files, no `.py` under `aisef2/`):
  - 667 INVALIDATED (R1) / 17,322 mutants;
  - 327 UNRESOLVED (I6) / 10,078 mutants;
  - 0 VERIFIED_REUSE, 0 MEASURED.
- The increment's first real run, under the frozen R6 letter, gave the same 667 as INVALIDATED (R6), all because of
  `tests/v2/test_v23_impact.py`. The state and mutant totals are the same; only the component differs.
- Calibration (Δ = ∅) is unaffected.
- With future observations, the frozen letter would re-open every target for every new `tests/v2` file.

**Measured precision cost of keeping I4 and the R1 static scan on all of S(F)** (fail-safe, unchanged; measured at
basis `da3ea33f3b69…` ∪ the increment's head):

| Change | Frozen rule over S(F): kill files / targets / mutants | Same rule over code(F), for comparison only |
|---|--:|--:|
| one changed existing segment of `tests/v2/sealing_gate.py` (I4) | 262 / 994 / 27,400 | 5 / 47 / 1,661 |
| … of `tests/v2/test_app_run.py` (I4) | 262 / 994 / 27,400 | 81 / 495 / 14,804 |
| … of `tests/v2/test_v21_mutation_runner.py`, or of `test_c2_p5_acceptance.py` (I4, each) | 262 / 994 / 27,400 | 1 / 5 / 497 |
| any Δ, complete observation without `os_trace` (R1 static scan) | 262 / 994 / 27,400 | 262 / 994 / 27,400 |

How the figures were computed:
- The S(F) column is a lower bound: code(F) ∪ every `tests/v2` file, which D2 (b) adds through `TESTS_V2`. It already
  reaches every target, so it is exact.
- The code(F) column reproduces the s2-closure figures of §2.8 exactly. §2.8 and §10 used the s2 closure, which has no
  D2 (b).

What they mean:
- Under I4 as frozen, a changed segment of any existing `tests/v2` file re-opens every live target: 994, which includes
  all 667 that pass I6. So W1a's planned `sealing_gate.py` edit re-opens 667 targets, not 47.
- Without `os_trace`, the R1 static scan alone keeps every target from reuse even with complete observations, and
  under either scope: `os.readlink` in `aisef2/app/adapters.py` is in every import closure. §10's "version bump:
  0 mutants" therefore needs `os_trace` for every kill file.

These are the frozen rules' costs, reported and not narrowed, because both rules fail safe. Narrowing I4 or the R1
scan would need its own amendment and soundness argument, and none is made here.

### A1.2 Erratum §2.4.4 and §11 exit gate 2 (flavor split)

Measured on the engine over the 994 live entries:
- The total is **63 linux / 140 flavor-unproven** (the frozen text says 62 / 141). Darwin stays 461, windows 3, unknown 327.
- The extra linux entry is `aisef2/runtime/process_range.py::_Posix.escaped`, which belongs to the B1-era imports and
  to the 177-target gate. One of its kill rows quotes a genuine host process listing inside an assertion diff. That
  listing carries a `/home/<u>/` path token at token start. It is a real R-flavor marker, not a fixture string.

Corrected figures:
- §2.4.4, B1-era row: **63 linux** + 2 darwin, **139** flavor-unproven. The hint sub-split of that column is provenance
  and is not re-derived.
- §2.4.4, total row: 461 darwin, **63 linux**, **140** flavor-unproven.
- §2.4.4, 177-target gate subset: posix 174 = 2 darwin, **50 linux**, **122** flavor-unproven; windows 3.
- §2.4.4, Option C 42 subset: unchanged (9 linux, 33 unproven, 0 darwin).
- §11 exit gate 2: "664 are `posix` (flavor: 461 darwin, **63** linux, **140** unproven) and 3 are `windows`". All
  other figures of the gate stand.
- Calibration run at W1a increment 1 (Δ = ∅): 667 VERIFIED_REUSE / 17,322 mutants (625 via the basis, 42 via the
  ruling), 327 UNRESOLVED (I6) / 10,078, 0 INVALIDATED.
- Flavor is provenance only, never a gate input (§2.4.2).
