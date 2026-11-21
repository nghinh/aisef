# AISEF v2.3 — COMPATIBILITY MATRIX (frozen at W0)

**Frozen:** 2026-11-21 on `release/v2.3-big` @ `1bf5dd2f` (kernel tree `aisef2/` = `e865d65c` = 2.2.0 RC2 kernel,
digest `c2d356b1…`; `v2.2.0` → `da3ea33f`). Governs every v2.3 wave (W1–W6). Implements RELEASE-CHARTER §4
"Compatibility" (keep the shipped 2.2.0 CLI/bundle/format readers or an explicitly versioned migration with tests;
never retroactively claim 2.2 signatures/proofs) and §2 gate "versioned-evidence read of historical 2.2 runs", under
RFC §35 (`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md:1485-1507`).

**Contract classes.** `MUST-READ-UNCHANGED` — v2.3 reads every artifact 2.2.0 wrote and reaches the same result;
additions are optional-only. `VERSIONED-MIGRATION` — a new version id plus a tested reader/migrator; the input is
never written. `NEW-ONLY` — v2.3 introduces it; no 2.2 artifact is reinterpreted under it. `IMMUTABLE` — bytes never
change; supersession only by a new record that cites the old one by sha256.

## 1. Matrix

| # | Artifact | Schema / version id | Writer (2.2.0) | Reader(s) | v2.3 contract | Test that pins it today | Gap |
|---|---|---|---|---|---|---|---|
| J1 | Journal format 1 | `journal_format` 1 (`aisef2/journal/event.py:37`) | `JournalWriter` `writer.py:31-103` (tests only) | `compat.reconstruct` `compat.py:51-72`; via `format3.reconstruct` `format3.py:309-310` | MUST-READ-UNCHANGED; never extended/upgraded | `tests/v2/test_v2_005.py` FMT3-3/5/7 (`:268-359`); `tests/v2/p3/test_format_compat.py`; fixtures `tests/v2/fixtures/journal/*.jsonl` (10) | — |
| J2 | Journal format 2 | 2 (`format2.py:31`) | `JournalWriter2` `format2.py:333-412` | `format2.reconstruct` `:302-328`; via `format3.py:311-312` | MUST-READ-UNCHANGED; `JournalWriter2` refuses other formats (`:348-350`) | `test_v2_005.py` FMT3-3/7; `tests/v2/p4/test_format2.py` | — |
| J3 | Journal format 3 — **every 2.1/2.2 run** | 3 (`format3.py:49`); `KNOWN_FORMATS (1,2,3)` `:52` | `JournalWriter3` via `RunScope.begin` `aisef2/runtime/run_scope.py:123-125`; path `run/journals/aisef-run.jsonl` (`run.py:629`, `lineage.py:115`) | `verify.py:190`; `bundle_cli._journal` `:935`; `lineage.events_of` `:165-172`, `child_evidence` `:182-194` | MUST-READ-UNCHANGED. A new **required** type/field ⇒ format 4 (RFC §35 `:1487-1489`) | `test_v2_005.py` Schemas/Messages/Taxonomy (`:364-733`) — synthetic journals | **G1**: no committed journal written by the 2.2.0 kernel (see §3) |
| J4 | Journal format 4 (only if A2/E2/E4 need new required events) | 4 | new writer | new `reconstruct` delegating 1–3 to `format3.reconstruct` unchanged | NEW-ONLY | to add: FMT4-3 analogue of FMT3-3 | — |
| J5 | Event envelope, chain, codec | `{chain,event}`; `GENESIS`=0×64; `link=sha256(prev‖event_id)` (`event.py:38,84-90,284-308`) | all writers | `event.decode` | IMMUTABLE for formats 1–3 (canonical line, `seq==index`) | `p3/test_format_compat.py` (known log heads), `p3/test_journal_writer.py` | unkeyed (CODE-AUDIT #10) — A2 adds keying, never to formats 1–3 |
| J6 | `failure/observed` code sets | 13 `FORMAT_2_CODES` (f1/f2) + 9 V2-005 (f3) (`event.py:132-134,214`; `format3.py:137-139`) | `carried` `event.py:223-235` | per-format validators | IMMUTABLE per format; new codes only in a new format | `test_v2_005.py` Taxonomy `:667-716` | — |
| J7 | Six control projections | story_state v2, budgets v2 (`budgets.py:22`, format-gated `:41-47`), failure_owner v1, retry_target v1, terminal_state v1, qualification_counters v1 | `Authority` `fold.py:134-158` | gates (`projections/__init__.py:34-39`); `verify._projection_refusal` `verify.py:41-53`; `bundle_cli._journal` `:945` | VERSIONED: semantic change ⇒ version bump; fold over formats ≤3 must equal 2.2.0's | `p3/test_control_projections.py`; `test_v2_005.py` BudgetsV2; `test_fold_oracle.py` | **G2**: E6 (#11) / E1 refactors change which historical journals verify |
| J8 | Projection cache rows | `CacheRow(projection,version,length,head,state,digest)` `fold.py:91-108` | `cache_row` (no production caller) | `resume` `:111-131` | discard-never-migrate (`:120`) kept | `test_fold_oracle.py:205-228` | — |
| B1 | Project bundle | `aisef-v2-project/1` (`bundle.py:37`), exact `KEYS` `:39-40,166-167`; digest = sha256 canonical JSON `:221` | `bundle_cli` seal/approve/migrate/continue via `_create` O_EXCL `:1066-1073` | `bundle.load` `:162-223` (compiles with **this** release's probes `:194-208`); `cli.py:76` for run/verify | MUST-READ-UNCHANGED, digest function frozen; new keys only as `/2` with dual reader | `test_b1gap2_bundle_load.py`, `test_v21_defects_bundleshape.py`, `test_v21_bundle_tools.py` | **G3**: probe-capability coupling (§3) |
| B2 | Authoring document | `aisef-v2-authoring/1` (`bundle_cli.py:109-111`; schema `docs/v2.1/bundle-authoring.schema.json`) | operator; v2.3 `bundle draft` (B4) | `seal` `:515-` | MUST-READ-UNCHANGED; B4 emits this same format, never approvals | `test_v21_bundle_tools.py` | — |
| B3 | `bundle migrate` | `RELEASES` table — **only `"2.0.0"`** (`bundle_cli.py:121-127`) | — | `migrate` `:366-449` | VERSIONED-MIGRATION: input never written (`:57-58`, `:1149-1152`); approvals withheld per declared capability change | `test_v21_migrate_semantics.py`, `test_b1gap2_bundle_cli_migrate.py`, `test_v21_kills3_T03b.py` | G3; #27 (format-only check `:372-373`) |
| S1 | Run settings | `aisef-v2-run/1` (`settings.py:34`), `KEYS` `:38-39`, `OPTIONAL` `:56` | operator | `settings.load` `:136-254`; `verify._runspec_problems` `verify.py:63` (re-loads the **record's** settings) | MUST-READ-UNCHANGED; new keys optional; validation never tightened for 2.2-valid docs | `test_b1gap_settings_optional.py`, `test_b1gap2_settings_load.py`, `test_v22_client_pin_fence.py` | C6/A2 keys must be optional |
| S2 | RunSpec layers + hash | `run/spec-resolved.runspec_hash` | `layers_of` `run.py:319-333`, `runspec_of` `:336-352` | `verify.py:69-74` (re-derives with **current** `layers_of`) | MUST-READ-UNCHANGED: 2.2 settings ⇒ 2.2 layers; a new layer only when its key is present (precedent `run.py:330-333`) | `test_v21_kills3_T14b.py:108-121` ("nine of 2.0.0") | G2 |
| R1 | Run record `RUN.json` | `aisef-v2-run-record/1` (`run.py:79`) — fields grew 2.0→2.2 with no bump | `execute` `finally` `run.py:700-727` | `verify.py:135-139` (refuses any other format); `bundle_cli._record` `:836-872`; lineage | MUST-READ-UNCHANGED; an absent field = earlier release (note, never problem: `verify.py:110-112`) | `test_app_run.py`, `test_v21_defects_verify.py`, `test_v21_kills3_T14a.py:147` | **G4** downgrade; #18 |
| R2 | `RUN.started.json` | subset of R1 + `settings_sha256` (`run.py:496-502`) | O_EXCL `open("x")` + fsync, never rewritten | `_record` fallback (journal path forced `:865-866`); `run.py:483-484`; manifest `run.py:430` | IMMUTABLE once written; MUST-READ | `test_v21_kills3_T13a.py`, `T14a.py`, `test_b1gap_bundle_cli__record.py` | verify never uses it (G4) |
| R3 | Evidence manifest + anchor | `aisef-v2-evidence/1` (`run.py:82`); RUN.json by canonical JSON (`:414-423`); anchor = sha256(canonical manifest) (`:446-448`) | `run.py:728-732` | `verify.py:141-172` (recomputes with **current** `evidence_manifest` `run.py:426-435`); `bundle_cli._authentic` `:875-908` | MUST-READ-UNCHANGED: recomputation over a 2.2 directory byte-identical (globs additive only) | `test_b1gap_run_evidence_manifest.py`, `test_v21_verify.py:90-113`, `test_b1gap_bundle_cli__authentic.py` | #22 (consistency, not authenticity) |
| R4 | Anchor file (`--anchor-out`) | one line 64-hex + LF, O_EXCL, `0o444` (`lineage.py:833-851`) | `cli.py:103-106` | `read_anchor` | IMMUTABLE format | `test_v21_continue_integrity.py:621-623` | — |
| R5 | Lineage claim `CONTINUED-BY.json` / `.<n>.json` | `{run,claimed,claimant[,supersedes]}` (`lineage.py:333`) | `claim` O_EXCL `0o444` `:335` — written **into the predecessor dir**, outside its manifest | `claims` `:146-162`, `continued_by` `:353-362` | append-only generations; existing files IMMUTABLE | `test_v21_kills_lineage.py`, `test_v21_x_lineage_gone.py`, `test_v21_kills3_T09a/b/c.py` | — |
| R6 | Session streams, preflight `LEDGER.jsonl` | `sessions/*.jsonl`, `preflight/LEDGER.jsonl` | client / preflight | `verify._spend` `verify.py:78-96`; `lineage.account_of` `:486-551` | MUST-READ-UNCHANGED: ≤2.2 spend re-derivation rule frozen | `test_v21_verify.py:50-88` | E2/E4 change Budget rules ⇒ dispatch by record version (G2); reader bodies not audited here |
| R7 | Review-finding / probe-observation files | `aisef-v2-review-finding/1` (`review_verify.py:343`), `aisef-v2-probe-observation/1` (`diagnostics.py:74`) | preserve / sink | `verify.py:206-211` | MUST-READ-UNCHANGED | `test_v21_r5_review_status.py:309-320`, `test_v21_r3_detail_artifact.py` | reader bodies not audited here |
| R8 | Usage block | RUN.json `usage`, `no_progress` | `run.py:721-722` | `verify.py:246-253` (re-derived with **current** `usage.usage`) | MUST-READ-UNCHANGED per record version | `test_v21_r3_usage_boundary.py` | G2; #44, #42 |
| K1 | `kernel_digest` | sha256 over `aisef2/**/*.py`, LF, rel path — **two implementations**: `run.py:94-100` (Path sort) and `release_rc.py:81-87` (git name sort) | — | `continue_from` `bundle_cli.py:982-984`; `verify._invariant_problems` `verify.py:122-123`; RC freeze `release_rc.py:116` | IMMUTABLE algorithm for historical trees; a fix (#41) is a named new algorithm | none directly | #41 |
| C1 | `aisef run` CLI | modes run/`--check`/`--verify`; exit 0 PASS·ready·VERIFIED / 1 FAIL·NOT_REACHED·REFUTED / 2 refused (`cli.py:10-12,78-80,95,98-100,115`); argparse errors 2 | — | operators, CI | MUST-READ-UNCHANGED; additions only (`--expect-pubkey`, `--resume`) | `test_app_run.py:351-377`, `test_app_units.py:748-758`, `test_v21_kills_cli.py:48`, `test_s2_kills.py:979` | `--anchor-out` failure ⇒ 2 after a finished run (`cli.py:113-114`); V2 runtime absent ⇒ 1 (`aisef/cli/parser.py:424`, `_common.py:21`) |
| C2 | `aisef bundle` / `demo` / `legacy` CLI | subcommands `bundle_cli.py:1083-1112`; exit 0/1/2 (`:51-52,1148,1158-1165`); routing `aisef/cli/parser.py:416-431` | — | — | MUST-READ-UNCHANGED; new subcommands additive (`draft`, `probes`, `grade`); `legacy` V1 untouched | `test_b1gap2_bundle_cli_main.py:92-95`, `test_v21_bundle_tools.py` | — |
| C3 | `bundle continue` | `continue_from` `bundle_cli.py:955-1056` | — | — | MUST-READ-UNCHANGED incl. **cross-kernel refusal** (`:982-984`) | `test_v21_continue_integrity.py`, `test_b1gap2_bundle_cli_continue_from.py` | a 2.3 kernel cannot continue a 2.2 run (by design) |
| E1 | V1 evidence | git-tracked `closure-evidence/**` minus `v2/` | — | `validation/v2/v1_evidence_guard.py:39-42` (preventive + detective, baseline `V1-EVIDENCE-BASELINE.json`, 2306 files) | IMMUTABLE | `tests/v2/test_v1_evidence_guard.py` | — |
| E2 | V2.0 / 2.1 / 2.2 evidence | `closure-evidence/v2/**` | historical validators | many | IMMUTABLE | partial: `tests/v2/p0/test_freeze_manifest.py`, `mutation.py --check`, `currency_dag.py` | **G5**: excluded from every blanket guard |
| E3 | Owner decision ledger | `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json`, `rule: "Append-only"`, 12 entries (last seq 12 `AISEF_V2_2_0_PRODUCTION_PUBLISH_AUTHORIZED_RC2`) | agent, on owner text | `v2_release_gate.py:28,61-62` (latest `PRODUCTION_PUBLISH` by seq); `mutation.py`, `p5_acceptance.py`, … | IMMUTABLE prefix + append (seq 13+) | `test_freeze_manifest.py:202-209` (seq 4 only) | **G6**: no prefix test |
| E4 | Release records per version | `V{ver}-STATUS.json`, `V{ver}-RC{n}-FREEZE.json`, `V{ver}-PROBE-CALIBRATIONS.json` | `release_rc`, `release_calibration` | `v2_release_gate.py:27`; `release_calibration.py:43-57` (path from pyproject version) | IMMUTABLE ≤2.2.0; NEW-ONLY `V2.3.0-*` | `test_c2_p5_acceptance.py`, `test_qualification_release_mode.py`, `test_v21_release_lane.py` | EVID-COUPLING-01 (#3) |
| E5 | Mutation records | `RECORDS` P1–P5, V2.0-S2, V2.2-B1-LIVENESS, V2.1 (`mutation.py:53,598,1294-1295`); runner 1/2 schemas | `mutation.py run` | `check` `:2616`; `target_problems` `:2568-2588`; binding `source_sha256` whole-module LF (`:11-12`) | IMMUTABLE entries; SUPERSEDED never re-checked (`:14-17,2595-2599`); NEW-ONLY results; runner-1 read by its own rules | `mutation.py --check`; `test_s2_mutation_record.py` | #14, #15 (VERIFIED_REUSE untested, ruling not digest-checked), #32 |
| E6 | Freeze manifests | `AISEF-V2-FREEZE-MANIFEST.json` (2.0 history), `v2.1/AISEF-V2-FREEZE-MANIFEST.json` | `validation/v2/freeze_manifest.py` | same (LF sha256) | IMMUTABLE; re-promotion only via new record (precedent `v2.2/V2-007-DOSSIER-REPROMOTION.json`, checked `test_freeze_manifest.py:215-226`) | `tests/v2/p0/test_freeze_manifest.py` | — |
| A1 | Released 2.2.0 | tag `v2.2.0`→`da3ea33f` (tag obj `92359a6d`); wheel `8c94dd6b…`, sdist `102cda44…`; RC2 src `ad0630c7`, kernel tree `e865d65c` (`release/V2.2.0-RC2-FREEZE.json`) | `release.yml` | PyPI; `v2_release_gate.py` | IMMUTABLE | release gate at tag time; `test_release_repro_dist.py` | **G7**: no standing check of tag/digests; BUILD-REPRO-01 |

## 2. Frozen rules

- **CR-1 Readers.** `format3.reconstruct` stays the reader of formats 1–3 for `--verify`, `bundle continue` and
  lineage, with 2.2.0 semantics. A v2.3 format ships as a new module whose reader delegates 1–3 to it unchanged, and a
  test shows identical outcomes on every fixture and generated journal (FMT3-3 pattern, `test_v2_005.py:268-285`).
- **CR-2 No upgrades.** A journal is never migrated, re-declared, extended under another format or rewritten (RFC
  §35 `:1505-1507`; writers `format2.py:348-350`, `format3.py:353-355`). `repair` appends only closers of the journal's
  own declared format (`aisef2/runtime/repair.py:39-41`; no production caller in 2.2.0).
- **CR-3 Forward refusal is explicit.** New required semantics go in a new format, so a 2.2.0 reader refuses a v2.3
  journal ("none of the formats this reader knows", `format3.py:313-314`) and never reads it as format 3. v2.3 never
  writes ignorable extra types into a format-3 journal.
- **CR-4 Historical verdicts frozen.** For every 2.2-written run directory, v2.3 `--verify` returns the same verdict
  and the same problems as 2.2.0. New notes may be added; a stricter finding is allowed only when it names a real
  defect and is classified in `CODE-AUDIT.md`. Every re-derivation that verify does with *current* code (projections,
  `layers_of`/`resolve`, `settings.load`, `bundle.load`, `evidence_manifest`, `usage.usage`, `Budget.spend`,
  `delivery`/`productproof`) is either unchanged or dispatched on the record's own version. If an E1/E6/E2/E4 change
  cannot reproduce 2.2.0's result, the 2.2.0 code path stays as the frozen reader for format ≤3 / run-record/1.
- **CR-5 Consistency only, never authenticity, for 2.2.** A 2.2 run verifies as consistency-only (anchor-bound when
  `--expect-anchor` is given, `verify.py:167-172`). `--expect-pubkey` on a 2.2 run is **REFUTED** with the cause
  "unsigned: a run of a release before 2.3". It is never VERIFIED-authentic.
- **CR-6 Never retro-sign.** v2.3 writes nothing into a 2.2 run directory except an exclusive new lineage claim
  (`lineage.py:335`; outside the manifest, `run.py:430-433`). No signature, key, manifest, RUN.json or journal change
  there, and no record claims a 2.2 proof or signature that 2.2 did not make.
- **CR-7 No downgrade of v2.3 runs.** The "signed run" discriminator lives inside the hash chain (e.g. format-4
  `run/begin` declares the key fingerprint), never only in a removable sidecar. For a run declaring format ≥4, a
  missing signature, `EVIDENCE.json` or `RUN.started.json` is **REFUTED**, not "an older release". The 2.1/2.2
  rule (absent manifest ⇒ note, `verify.py:144-145`, pinned by `test_v21_defects_verify.py:129-134`) stays only for
  format ≤3 runs and stays declared as a limitation.
- **CR-8 Bundles stay loadable.** Every bundle 2.2.0 loads, v2.3 loads with the same `Project.digest`. Before any
  change to a probe's `CAPABILITY_VERSION`, `CLASSES` (`DIGEST` `aisef2/probe/file_artifact.py:253`) or the compiler
  digest, add a `"2.2.0"` entry to `bundle_cli.RELEASES`. `--verify` then compiles a historical bundle for identity
  under the release that ran it, with no execution, so the 2.2 run still names its own `bundle_digest`. Without this,
  a 2.2 run's bundle fails `bundle.load` (`bundle.py:205-208`, exit 2) and its migrated copy fails "the run is not of
  this project bundle" (`verify.py:173-174`). That is lost historical verification, which is a STOP (§5).
- **CR-9 Settings / RunSpec.** Every 2.2-valid `aisef-v2-run/1` document loads unchanged. New keys are optional and
  enter the RunSpec layers only when present (`run.py:330-333`). The `resolve` hash function and `settings_sha256` rule
  (`run.py:325`) are frozen.
- **CR-10 Run directory artifacts.** `aisef-v2-run-record/1`, `RUN.started.json`, `aisef-v2-evidence/1`, the anchor
  rule and the anchor-file format are read forever. A new record or manifest version is a new id with a dual reader;
  2.2.0's verify then refuses it explicitly (`verify.py:138-139`).
- **CR-11 Lineage / resume.** Claims are append-only and never deleted. `account_of`/`lineage_account` read 2.2 run
  directories unchanged. Cross-kernel `bundle continue` stays refused (`bundle_cli.py:982-984`). G6 `--resume` applies
  only to a run whose fingerprint includes this kernel's digest and whose journal is format ≥4; a 2.2 run is never
  resumed. A run directory is otherwise never reused (`run.py:478-479`).
- **CR-12 CLI surface.** Every 2.2.0 flag, subcommand, output key and exit status keeps its meaning (`cli.py:3-12`,
  `bundle_cli.py:3-14,51-52`). Additions are new flags or subcommands only. Any change to an existing exit status is a
  CHANGELOG-declared contract change.
- **CR-13 Historical evidence byte-immutable.** V1 (guarded), and V2.0/2.1/2.2 `closure-evidence/v2/**` as committed
  at `399b775f`: no edit, delete, rename or mode change. Supersession is only by a new record citing the old one by
  sha256. Test runs that touch `closure-evidence/` are checked out, never committed (CLAUDE.md).
- **CR-14 Ledger append-only.** `RELEASE-DECISIONS.json` entries seq 1–12 stay value-identical; new entries take seq
  13+, strictly increasing. A ledger entry is not an approval: REL-GOV-01 needs the protected-environment reviewer.
- **CR-15 Version-keyed records.** `V2.2.0-*` (and older) records are never re-stamped, re-pointed or regenerated. A
  version bump never retargets a version-derived path to make an old record look current (EVID-COUPLING-01). F5
  `VERIFIED_REUSE` cites the measured record by sha256 plus an equivalence proof, never re-measures, and is never
  shown as MEASURED.
- **CR-16 Mutation evidence.** No `source_sha256` is ever rebound (charter §4). Historical entries, runner-1 rules and
  SUPERSEDED entries are read as written. New results go only into new records. Reuse checks the ruling by digest,
  not by file existence (#14), and has negative tests (#15).
- **CR-17 Released 2.2.0 artifacts.** Tag, commit, wheel/sdist digests, the kernel tree and the kernel digest are
  immutable. The 2.2 `kernel_digest` algorithm is retained for historical trees: both implementations must give
  `c2d356b1…` on `e865d65c`. The BUILD-REPRO-01 fix applies to v2.3 builds and must still rebuild `da3ea33f` from a
  fresh checkout to `8c94dd6b…`/`102cda44…`. Cross-host equality is claimed only for the tested toolchains
  (RISK-REGISTER).

## 3. Gaps (confirmed against source; owning wave) — labelled CG-n so they do not collide with roadmap IDs G1–G10

- **CG-1 (W2, gate W6).** No complete run directory produced by the 2.2.0 kernel is committed. None of the 28 stored
  `RUN.json` carries the 2.2 `invariants` field, so all are pre-2.2. The copies are partial: for example
  `closure-evidence/v2/v2.1/canary/tier-1/run/` holds `journals/` at its top and no `repo/`. The only historical
  journal any test reads is 2.0.0 `release/smoke-2` (`test_v21_r5_review_status.py:316`). The charter §2 gate has no
  input yet.
- **CG-2 (W2).** Verify re-derives through the current writer code (CR-4 list), so any W2 semantic change silently moves
  historical verdicts. No test shows this today.
- **CG-3 (W2/W4).** The probe-capability coupling (CR-8). Derived from code, not measured: by `bundle.py:194-208`, 2.2.0
  cannot `--verify` a 2.0.0 run with its own bundle. 2.1 → 2.2 survived only because `aisef2/probe` did not change
  (`git diff v2.1.0 v2.2.0 -- aisef2/probe` is empty).
- **CG-4 (W2).** Downgrade by stripping. A 2.2 run with `EVIDENCE.json` deleted verifies VERIFIED with a "before 2.1"
  note even though `RUN.started.json` (2.1+) is present. This is pinned behaviour, kept for format ≤3 runs (CR-7).
- **CG-5 (W1).** No blanket byte-immutability guard covers `closure-evidence/v2/**`: the V1 guard excludes it
  (`v1_evidence_guard.py:40`).
- **CG-6 (W1).** The ledger is append-only by convention only.
- **CG-7 (W6).** Nothing re-checks the 2.2.0 tag→commit or the frozen digests after release.
- **Minor (CLI).** `aisef run` exits 1 (= FAIL) when the V2 runtime is absent (`aisef/cli/parser.py:424`). It exits 2
  (= "refused before the run began") when only the anchor copy failed after a finished run (`cli.py:113-114`). Both are
  kept unless a CR-12 declared change is made.

## 4. Compatibility tests v2.3 must add (smallest set; no paid run)

| ID | Test | Closes | Wave |
|---|---|---|---|
| CT-1 | Golden 2.2.0 corpus: offline runs (fake client, no network) from the `v2.2.0` wheel in an isolated venv, committed NEW-ONLY under `closure-evidence/v2/v2.3/compat/` with bundle + anchor. v2.3 `--verify` gives the 2.2.0 verdict/problems; tampered copies give REFUTED; `--expect-pubkey` gives REFUTED. | CG-1, CR-4/5 | W2 (gate W6) |
| CT-2 | FMT4-3: f4 reader ≡ f3 reader on all f1–f3 fixtures and generated journals | CR-1/3 | W2 |
| CT-3 | Every E1/E6/E2/E4 change re-runs CT-1 corpus verdicts (shadow comparator) | CG-2 | W2 |
| CT-4 | Strip signature / manifest / started file from a v2.3 run → REFUTED | CG-4, CR-7 | W2 |
| CT-5 | `RELEASE-DECISIONS` entries[:12] equal `git show v2.2.0:…` entries; seq strictly increasing | CG-6, CR-14 | W1 (L1-CIGOV, `test_v23_release_governance.py`) |
| CT-6 | V2-history guard: every `closure-evidence/v2/**` blob at `399b775f` unchanged at HEAD (additions allowed), git-blob comparison, the V1 guard's method | CG-5, CR-13 | W1 (L1-CIGOV, `test_v23_release_governance.py`) |
| CT-7 | Every committed 2.2 bundle/settings (examples, tests, evidence) loads with equal digest; a `RELEASES["2.2.0"]` entry exists before any capability bump | CG-3, CR-8/9 | W2/W4 |
| CT-8 | Fresh-checkout rebuild of `da3ea33f` → `8c94dd6b…`/`102cda44…`; v2.3 tree with perturbed modes → same digest | CR-17, BUILD-REPRO-01 | W1 (L1-BUILD, `test_v23_repro_contract.py` + CI `repro` job) |
| CT-9 | Both `kernel_digest` implementations = `c2d356b1…` on `e865d65c` | CR-17, #41 | W1 (L1-BUILD, `test_v23_repro_contract.py`); the #41 fix itself is W2 L2-RECORD and must keep CT-9 green |
| CT-10 | CLI surface: the 2.2.0 `--help` flags and exit table are a subset of v2.3's, with the same meaning | CR-12 | W6 |

## 5. Reconciliation and owner STOP triggers

- CODE-AUDIT #3, #6, #10, #11, #12, #14, #15, #18, #22, #27, #32, #41, #42, #44, #45 map to the rows above. RISK
  EVID-COUPLING-01 maps to CR-15/E4, BUILD-REPRO-01 to CR-17/CT-8, REL-GOV-01 to CR-14. MASTER-CHECKLIST mappings: A2
  → CR-5/6/7, E1/E6 → CR-4/CG-2, E2/E4 → R6/CG-2, E5 → J7, F5 → CR-15/16, G6 → CR-11, B4 → B2, C6 → S1, V21-30 → R3/R6.
  None of the open OWNER_DECISION rows (9 after the W0-closure reconciliation, MASTER-CHECKLIST) is needed by this matrix.
- **STOP only if** (a) a v2.3 change would alter a historical 2.2 verdict or make a 2.2 run unverifiable (CR-4/CR-8
  cannot both hold); (b) continuing a 2.2 lineage across kernels is wanted (it reverses CR-11); (c) any immutable
  record or ledger entry would need editing (CR-13/14). None is triggered at W0.

**Read for this freeze:** `aisef2/journal/{event,compat,writer,format2,format3,fold}.py` and
`projections/{__init__,budgets}.py` in full (the other projections' `version` only); `aisef2/app/{bundle,settings,
run,verify,cli}.py` in full; `bundle_cli.py:1-230,340-470,830-1169`; `lineage.py:1-195,286-365,486-555,826-851`;
`aisef/cli/parser.py:180-199,404-439`; `run_scope.py:110-135`; `repair.py:1-25,39-41`; `release_rc.py:80-99`;
`mutation.py:1-46,2510-2619`; RFC §35; the cited test ranges. **Not audited line-by-line:** `client.py` session
reader, `preflight.accounting`, `review_verify`/`diagnostics` artifact readers, `usage.py`, `runtime/runspec.py`.
