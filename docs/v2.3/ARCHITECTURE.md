# AISEF v2.3 — ARCHITECTURE (W0)

**Baseline:** `release/v2.3-big` @ `1bf5dd2f`. The `aisef2/` git tree is `e865d65c`, the same as `v2.2.0:aisef2`
(measured with `git rev-parse HEAD:aisef2 v2.2.0:aisef2`). `aisef2.app.run.kernel_digest()` = `c2d356b1…`, measured at
HEAD. No product, test or validation code is changed by this document.

**Scope.** Part I describes the v2.2 architecture as shipped. Part II freezes the v2.3 target envelope: what each wave
adds or changes, and the invariants each change must preserve. Detailed per-wave design freezes at the start of each
wave (plan §5, charter §4). Wave ownership, edges and lanes: `DEPENDENCY-DAG.md`. Threats and claims:
`THREAT-MODEL.md`. Format and record contracts: `COMPATIBILITY-MATRIX.md` (`CR-n`). Neither is repeated here.

**Citation key.** A plain `path:line` was read directly for this document (list at the end). **[A]** = taken from a
W0 15-lane audit module map (`CODE-AUDIT.md` subsystem maps). **[GF]** = taken from a W0 gap-fill lane, under the
provisional IDs in `THREAT-MODEL.md` §8; still to be adjudicated and not among the 45. **#n** = `CODE-AUDIT.md`
defect n. **AO-n** = architecture observation first recorded here (§6).

---

# Part I — v2.2 as shipped

## 1. Planes → packages

The RFC splits the system into four planes (`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md:68-91`): requirement,
product, planning and record. It also states nine invariants (`:144-160`). Packages map onto the planes as follows.

| Package | Plane / role | Key entry points |
|---|---|---|
| `aisef2/app` | Driver, authoring, adapters, evidence edges | `cli.run` `cli.py:60`; `execute` `run.py:461`; `verify` `verify.py:131`; `bundle.load` `bundle.py:162`, `Project.order` `:124`; `bundle_cli.main` `:1080` (seal `:515`, approve `:651`, lint `:780`, explain `:804`, migrate `:366`, continue_from `:955`, `_create` `:1066`); `client.session` `client.py:298`, `Budget` `:130`; `preflight.run` `preflight.py:87`; `confine.measure` `confine.py:313`, `wrap` `:177`; `tripwire.needles_of` `:62`, `scan_repo` `:110`; `lineage.claim` `:290`, `lineage_account` `:708`, `write_anchor` `:833`; `adapters.Developer` `:71`, `Reviewer` `:111`, `scanner` `:402`; `review_verify.verify` `:184`, `anchor` `:292`, `blocks` `:332`; `feedback.task` `:44`, `retry_feedback` `:68`, `context_pack` `:128`; `diagnostics.Sink` `:134`, `tapped` `:237`; `demo.main` `:168`; `settings.load` `:136` |
| `aisef2/orchestrate` | Execution: the single story path | `run_story` `story_runner.py:168`, `_attempt` `:183`; `prove` `proof.py:80`; `assess` `quality.py:49`; `review` `review.py:29`; `scan` `security.py:29`; `merge` `merge.py:25`, `reprove` `:44`, `affected_preserve` `:38`; `git` `workspace.py:64`, `GitWorkspace` `:115`, `GitMerger` `:163`; protocols `adapters.py:50,113`, `confine` `:91`; `seam.admit_legacy` `seam.py:48` (dormant [A]) |
| `aisef2/journal` | Record plane, sole authority | `Event` `event.py:53`, `event_id`/`link` `:84-90`; `JournalWriter3` `format3.py:337`; `reconstruct` `format3.py:303`; `Authority` `fold.py:134-161`; the six projections `projections/__init__.py:24-31`, `project` `:34` |
| `aisef2/product` | Product plane | `BehaviorContract` `contract.py:113`; `ContractApproval` `approval.py:50`, `require_approved` `:82`; `compile_spec` `compiler.py:59`, `COMPILER_DIGEST` `:37`; `ProductProofSpec` `spec.py:29` |
| `aisef2/probe` | Harness-owned oracle | `run_probe` `protocol.py:264`; `bound_result` `:223`; `classify_failure` `:164`; `ProbeRegistry` `:246`; `CATALOG` `catalog.py:102`; `calibrate` `calibration.py:104`; four probes [A] |
| `aisef2/plan` | Planning plane + admission | `PlanObligation` `obligation.py:30`, `Plan` `:82`; `StaticPlanAdmissionEngine` `static_admission.py:288`, `ENGINE_SOURCES` `:32`, `require_admitted` `:302` (no production caller [GF]); `admit_story` `story_admission.py:139`, `classify` `:74`; `continue_story` `drift.py:71`; `plan_quality` `:116` (no production caller [GF]) |
| `aisef2/quality` | Engineering-test adequacy (never a product verdict) | `test_execution.execute` `:443`, `classify` `:195`; `vacuity.evaluate` `:238`; `relevance.measure` `:184`; `adequacy.assemble` `:188` |
| `aisef2/control` | Owner, retry, budget (pure functions) | `classify` `owner.py:163`, `flatten` `:170`; `route` `routing.py:96`, `row_for` `:107`; `charge` `budget.py:34` |
| `aisef2/runtime` | Lifetimes and OS ownership | `RunLease` `run_scope.py:58`; `RunScope` `:89` (`begin` `:111`, `append` `:144`, `retry` `:157`, `story` `:168`, `shutdown` `:180`, `interrupt` `:206`); `StoryScope` `story_scope.py:71` (`acquire` `:88`, `dispose` `:119`); `ProcessRange` `process_range.py:385`, `release` `:523`, `pid_alive` `:147`; `sentinel.preflight` `sentinel.py:112`; `runspec.resolve` `runspec.py:58`; `capability.verified/attested/opaque` `capability.py:93/98/108`; `repair` `repair.py:74` |
| `aisef2/invariants` | Invariants I–IX armed in-process | `register` `registry.py:304`, `arm` `:356`, `require_armed` `:370`, `register_runtime` `:425`, `arm_runtime` `:462`, `RUNTIME_STATEMENT` `:384`; `evidence.admit` `evidence.py:47` (0 production callers, #13) |
| `aisef2/cohort` | Preregistration / holdout seal | `EvaluationCohort` `lifecycle.py:48`, `seal` `:114`, `advance` `:133`, `generalization` `:184`. Kept out of the kernel by `COHORT_CONFINED` (`validation/v2/cohort_static_checks.py:4,91`); `run.py:713` hard-codes `generalization_claim "NONE"` |
| `aisef2/arch` | Frozen vocabularies | `Owner` `enums.py:117`, `EventType` `:133`, `InvariantId` `:165`, `ControlProjection` `:190` (closed list), `VOCABULARIES` `:201` |
| `aisef2/errors.py` | Uncontainable kernel error | `InvariantError(BaseException)` `errors.py:8` |
| V1 boundary | `aisef` routes the execution verbs to V2 | `aisef/cli/parser.py:407-431` sends `run`, `bundle` and `demo` to `aisef2`. Everything else is V1. `aisef2` imports nothing from `aisef` [A]. Runtime dependencies: none (`pyproject.toml` `dependencies = []`) |

## 2. Run data flow (`execute`, `run.py:461-733`)

One `rec["stage"]` string tracks the pipeline. The `finally` re-derives the record from the journal.

| # | Stage (`rec["stage"]`) | What happens | Lines |
|---|---|---|---|
| 0 | — | Refuses an existing `--out`. Writes `RUN.started.json` once, with O_EXCL and fsync, so it survives a SIGKILL | `run.py:478-479`, `:496-502` |
| 1 | `invariants` | `arm_runtime()`; registry and code-mechanism digests go into the record | `:515-520` |
| 2 | `ocr identity`, `client identity` | Byte-identity pins, checked before anything is sent | `:523-545` |
| 3 | `claim` | `lineage.claim` + `lineage_account`. Unread spend → refuse. Unaccounted spend → refuse unless `--accept-unaccounted` | `:546-576` |
| 4 | `repository` | `check_git`; `clone --no-hardlinks`; check the requirements; checkout the baseline as `main` | `:577-585` |
| 5 | `stimulus tripwire` | Scans the baseline tree for sealed stimulus and bundle content (G1) | `:590-594` |
| 6 | `admission` | `admit()` → `StaticPlanAdmissionEngine` (RFC §12). The result goes only to `RUN.json`; the journal does not exist yet (GF-PLAN-6) | `:114-121`, `:595-598` |
| 7 | `test interpreter` | Developer-test venv. Probes use `sys.executable -I -S` | `:599-600`, `:671` |
| 8 | `confinement` | Opt-in bwrap measurement for the two model sessions only | `:603-607` |
| 9 | `preflight` | The configured endpoint must equal the attested one; route attestation | `:612-624` |
| 10 | — | RunSpec: kernel digest (FULL); python, test-python and git; each active probe's EXECUTION_DIGEST; attested developer/reviewer models; scanner | `runspec_of` `:336-352`, `:626-627` |
| 11 | `run` | `RunScope.begin`: lease → sentinel OPEN → `run/begin` → `capability/resolved`* → `run/spec-resolved` | `:629-630`; `run_scope.py:111-137` |
| 12 | (loop) | For each story in `project.order()`: `budget.reached` → NOT_RUN; build `StoryInputs` (no `completed`, GF-PLAN-2); `run_story`. A per-story `Exception` → REFUSED; break when the run is no longer RUNNING | `:674-695` |
| 13 | `finished` / finally | `_close_run` (shutdown, or interrupt after a refused shutdown) → journal info → `delivery` from journal events → `productproof` → budget → `usage` / `no_progress` → `RUN.json` → `EVIDENCE.json`. Anchor = sha256 of the canonical manifest | `:700-732`, `:736-749`, `:446-448` |

**Story path** (`_attempt`, `story_runner.py:183-370`). Steps in order:

1. `story/begin`, with the parent as a full SHA (`:187`).
2. Acquire scratch, the implementer checkout and the verifier checkout (`:197-203`).
3. `admit_story` at the parent. Probes run; no developer is called (`:213-217`).
4. Admission `gate/check` (`:221-225`).
5. `continue_story` (`:227`), then the no-work rule (`:233`).
6. `provider/request` with `budget_owner` DEVELOPER (`:236-238`), `developer.implement` (`:240`), `provider/result` (`:243`, `:252`).
7. Move both checkouts to the candidate (`:261-262`).
8. Two-party proof at CANDIDATE of `verify_at_candidate` plus the affected PRESERVE obligations (`:271-283`).
9. `quality.assess`, skipped when there is no work (`:284-305`).
10. Confine → review → scan → unconfine (`:306-320`).
11. Merge (`:321-325`).
12. Move both checkouts to the merge; re-prove at POST_MERGE (`:326-350`).
13. `gate/decision` (`:351`).
14. `story/commit`, or `failure/observed` + `budget.charge` → `story/retry` or `story/rollback` (`:352-363`).
15. `story/dispose` (`:364`), `scope.dispose()` (`:365`), `story/end` (`:366`).

**Lines 351–366 are outside any try/finally (#2, P1).** The `measured` map built at `:367-368` has no consumer
(GF-PLAN-2).

**Every event** goes through `RunScope.append` (`run_scope.py:144-148`) → `Authority.append` (`fold.py:147-158`). The
format writer-validator and all six projection steps pre-check the event. A refused event never reaches the log.
`story_state` enforces the RFC §17 lifecycle `BEGIN→ACTIVE→outcome→DISPOSE→ENDED` (`projections/story_state.py:26-71`).
Separately, `format3._story_active` encodes "an open attempt" (`format3.py:173-177`). The lifecycle is defined twice
(#11, E6).

**Verify** (`verify.py:131`) follows this pipeline:

1. Check the RUN.json format.
2. Re-derive the EVIDENCE manifest and its anchor; apply `expect_anchor`.
3. Check the bundle digest.
4. Check the journal sha256 and line count, reconstruct it, and refuse it if any of the six projections refuses it.
5. Re-derive outcomes (`run.outcomes_from`), the runspec binding, invariant arming, spend, the delivery verdict
   (`run.delivery`), `productproof`, usage and final `main` (`verify.py:205-258`).

Nothing in the record can raise the verdict; it can only lower it (`verify.py:5-13`). The verdict loops in
`run.py:355-411` are bespoke, not a projection fold (E1).

## 3. Identities and what binds them

| Identity | Computed at | Bound into | Re-checked by |
|---|---|---|---|
| `bundle_digest` | sha256 of the canonical bundle (`bundle.py:122,221`) | RUN.json, RUN.started, RunSpec layer | `verify` |
| `plan_hash` | self-binding content digest (`obligation.py:87-102`). Not approval-bound [GF] | RunSpec layer (`run.py:323`); `plan/frozen` (`story_runner.py:157`) | `verify` (runspec) |
| `semantic_hash` | `spec.py:38` (probe id + digest + input + expectation [A]) | every `proof/verified` (`format3.py:180-211`) | writer rule `_verified` |
| `runspec_hash` | `runspec.py:52`; `capability/resolved` + `run/spec-resolved` (`run_scope.py:128-130`) | journal | `verify._runspec_problems` |
| Kernel, content form | sha256 over `aisef2/**/*.py`, LF (`run.py:93-100`). The same algorithm from git objects is `release_rc.kernel_digest_at` (`release_rc.py:81-87`) | RunSpec `kernel` FULL (`run.py:346`); RC freeze | `verify` (`:122` [A]); `release_rc.check` (`:113`) |
| Kernel, git-tree form | `HEAD:aisef2` tree SHA-1 | version-forward records (`version_forward.current_context` `:174-179`); B1 risk manifest (`b1_bindings_check.py:17-20`); p5 acceptance `aisef2_tree` (`p5_acceptance.py:892`); cohort preregistration [GF] | each checker against git |
| Probe identity | DIGEST (capability) + EXECUTION_DIGEST (bytes) [A]; calibration rows in `app/calibrations.py` | `spec.probe_digest`; RunSpec per active probe (`run.py:350`) | admission check 9 [A] |
| Engine identity | `engine_digest` over 2 files (`static_admission.py:32-40`), missing its transitive deps (GF-PLAN-3); `COMPILER_DIGEST` (`compiler.py:37`) | admission result; p5 acceptance [GF] | — |
| Journal `head` | `link = sha256(prev ‖ event_id)` (`event.py:84-90`), unkeyed | `_journal_info` (`run.py:752-759`) | `verify` reconstruct |
| Evidence anchor | sha256 of the canonical EVIDENCE.json (`run.py:446-448`), unkeyed | printed / `--anchor-out` | `verify --expect-anchor` |

## 4. Trust boundaries (summary; full statement in `THREAT-MODEL.md` TB1–TB16)

| Boundary | Enforced by (v2.2) | Ceiling / open defect |
|---|---|---|
| Model output → control | Typed adapters; `flatten` → UNKNOWN; no prose as control (VII) [A] | holds |
| Oracle → developer | `FACT_FIELDS` (`bundle.py:38`); prompts built from public facts; G1 tripwire | not enforced on disk without confinement (#21, GF-SEC-3); tripwire gaps (#19, GF-SEC-1) |
| Candidate code → host and verdicts | Probe isolation (PARTIAL) + HMAC protocol [A]; tests run unconfined | D1 (#21); the test-result channel is written by the subject (GF-QUAL-2, P1); coverage blind spots (GF-QUAL-1, P1) |
| Run dir → verifier | Unkeyed chain + unkeyed anchor; the record only lowers the verdict | consistency, not authenticity (#10, #22) → A2 |
| Spend | Re-derived from journal + streams + ledger | SIGKILL window (E2); stream not sealed (#12, E4) |
| Provider identity | One-shot preflight | #8 (C7); key reachable in the session (#9, D3); open egress (#20) |
| Process ownership | OS range; liveness that fails closed (`client.py`) [A] | Windows reader fails open in the mutation cleaner (GF-AUTH-6) |
| Continuation | Exclusive claim, evidence-gone rule | TZ/locale-dependent "gone" (GF-LIN-1, P1); emptied dir = 0 spend (GF-LIN-2) |
| Publication | Frozen-RC bytes + ledger + `pypi` env | no required reviewer (#1, REL-GOV-01) |
| Self-policing checkers | 9 AST/authority checkers | live checks gated out of `unit` (GF-AUTH-1, P1); derivation exists-semantics (GF-AUTH-2, P1) |

## 5. Validation and release machinery, and how it binds to the kernel

| Mechanism | Binds | Checker / entry | Armed in CI? |
|---|---|---|---|
| Unit suite | the tree | `unittest discover` inside `owned_run.py` (`tests.yml:52-60`); V1 evidence guard runs after (`:64`) | yes, 6 legs |
| Sealing tier | committed records = what the tree derives | `AISEF_SEALING` (`tests/v2/sealing_gate.py:20-23`), `GATED` (`:29-`) | master and tags only (`tests.yml:75-76`) |
| Mutation records | per target: `source_sha256` of the **whole module**; `tree_sha256` of the pristine copy (`mutation.py:2439`, `_pristine` `:1847-1866`) | `check` `:2616` → `problems_of` `:2602` → `target_problems` `:2568` / `_problems_v2` `:2519` | via sealing/tests [A] |
| One-off reuse | 42 `bundle_cli` targets, c15d5b10→0fdfc022 | `verified_reuse_current` `mutation.py:1623-1645`: ruling checked with `.is_file()` only (#14); no test (#15) | — |
| Record-merge reuse proof | target blob, kill set, kill-test closure, generator | `s2_mutation_record.proof` `:150-176`, `closure` `:113-148`; `v21_mutation_record.proof` `:43-68`; criteria frozen by digest (`v21:39-40`) | at record build / `--check` |
| B1 risk gate | `HEAD:aisef2` tree, registry sha, per-target source | `b1_bindings_check.problems` `:14-31` | `workflow_dispatch` [A] |
| Version-forward records | `(version_context="v2.2", source_commit, HEAD:aisef2)` (`version_forward.py:37,65,174-179`) | `currency_dag.validate` `:101`, `NODES` `:46`, `OWNER_GATED` `:85` | sealing |
| Checker calibration | 57 checkers fail on known-bad inputs | `checker_calibration.REGISTRY` `:571`, `calibrate` `:621` | gated out of `unit` (GF-AUTH-1) |
| Release calibration | path derived from the **pyproject version** | `RECORD_REL = newest_rel(_version())[0]` `release_calibration.py:57`; consumed at `p5_acceptance.py:896-898` | EVID-COUPLING-01 |
| RC freeze / dist | source SHA, `SHIPPED` trees, kernel content digest from RC objects, dist sha256 | `release_rc.freeze` `:94`, `check` `:113`, `verify_dist` `:131`; `repro_dist.normalize` `:25-45` keeps each member's mode (BUILD-REPRO-01) | `wheel` job, `release.yml` |
| Publish gate | ledger `PRODUCTION_PUBLISH` + STATUS + RC | `v2_release_gate.problems` `:32`, `main` `:73`; `release.yml` env `pypi` [A] | tag only; no reviewer (REL-GOV-01) |

**Kernel binding, three ways:**

1. **Run time.** The content digest goes into the RunSpec, plus the invariant digests; `verify` compares them.
2. **Release.** The RC freeze recomputes the content digest from the RC commit's objects, and the dist bytes are
   compared.
3. **Qualification records.** These bind to the `HEAD:aisef2` git tree (version-forward, B1) or to the module
   sha256 (mutation).

So **any `aisef2/` edit** stales every version-forward node, and every mutation target whose *module* changed. This
is why W1 (F5) comes before every kernel wave: W1a edits no `aisef2/` file; W1b lands E5 in `story_runner.py`
only after F5's gates, as the first kernel change qualified incrementally (owner ruling; `DEPENDENCY-DAG.md` R11–R12,
`W1-DESIGN.md` M4/M8).

## 6. Architecture observations (new; to adjudicate in W1)

- **AO-1 — `mutation.py --check` under-binds evidence.** `_problems_v2` (`mutation.py:2524-2526`) and
  `target_problems` (`:2578-2580`) compare only the target module's `source_sha256`. A committed target record holds
  only `{classes, kill_tests, killed, killed_by_timeout, mutants, results, runner, source_sha256, strays_reaped,
  survivors, t0, target, tree_sha256}` (read from `closure-evidence/v2/v2.1/MUTATION.json`). It has no kill-test
  digest, no generator digest, no import-closure digest and no platform/interpreter field. `tree_sha256` is
  re-checked only on the VERIFIED_REUSE path (`:1634`); grep finds no other reader in `validation/`.
  - The stronger proof (kill set, kill-test closure, generator) exists only in the per-phase record builders
    (`s2_mutation_record.py:150-176`).
  - Even there, a changed **non-test** file in the closure is informational only: it is returned as the second list
    (`:176`) and kept as `other_code_changed` (`:272-276`); it does not block reuse.
  - Net effect: the whole-module rule over-invalidates (one edit stales every target in the module) and under-binds
    (a kill-test, generator, transitive-dependency or platform change does not stale `--check`).
  - CI arming of the per-phase `--check` is not established here; F5 must enumerate it.
- **AO-2 — Two kernel identities, no declared mapping.** The content sha256 (`run.py:93-100`, `release_rc.py:81-87`)
  and the git-tree SHA-1 (`version_forward.py:174-179`, `b1_bindings_check.py:17-20`) are not comparable. GF-COH-2
  is one case of this. CT-9 (`COMPATIBILITY-MATRIX.md`) pins only the two content implementations. F5 must record
  both identities and derive one from the other (`kernel_digest_at(sha)`), never compare across them.
- **AO-3 — E1 vs the closed projection list.** RFC §21 (`AISEF-V2-ARCHITECTURE-RFC.md:1109-1121`), `ControlProjection`
  (`enums.py:190`) and `projections/__init__.py:1-6,24-31` close the gate-citable set at six. A "7th projection"
  (IMPROVEMENT-ROADMAP E1) would amend frozen vocabulary F11. `DEPENDENCY-DAG.md` §4 W2c says "NEW verdict
  projection". That must mean a **reporting fold outside `PROJECTIONS`** (§8, E1), not a seventh member.
- **AO-4 — A2 needs asymmetric signatures, and the package is stdlib-only.** `pyproject.toml` has
  `dependencies = []`, and RFC §3 forbids third-party frameworks in the kernel. QĐ#1 decided the key model: a per-run
  ephemeral keypair, with the public half escrowed off-box (`ROADMAP-2.2-CHECKLIST.md:51`). See §8, A2.
- **AO-5 — Resume vs "never reused".** `run.py:478-479` refuses an existing `--out`, and `RunScope.begin` runs once
  (`run_scope.py:113-114`). `COMPATIBILITY-MATRIX` CR-11 allows `--resume` only for format ≥4, same-kernel, unfinished
  runs. The lease, sentinel TORN preflight (`run_scope.py:116-122`) and closer repair (`repair.py:74`) already give
  the re-open path (§8, G6).
- **AO-6 — The test-adequacy gate blocks, but cannot forge a product PASS.** `TestsPolicy(True)` is set at
  `run.py:672`. A commit still requires every proof to pass first (RFC §17, `AISEF-V2-ARCHITECTURE-RFC.md:935-937`;
  `story_runner.py:279-283,351-354`). GF-QUAL-2 therefore lets an inadequate story *pass adequacy*. It cannot make an unsatisfied product
  obligation pass. Severity stays P1: the gate's claim is false. Delivery false-PASS is not implied.

---

# Part II — v2.3 target architecture

## 7. Envelope: what no wave may change

- Invariants **I–IX** (RFC §4) stay as strong or stronger, and stay uncontainable (`errors.py:8`).
- RFC §3 non-goals stay: a single writer with dense `seq` (no multi-writer journal); event-sourced state with no
  event-driven control; no kernel plugin decision; no third-party framework in the kernel.
- The journal is the sole authority. Exactly six control-critical projections (F11). Caches are never authority.
- Formats 1–3, `aisef-v2-run-record/1`, `aisef-v2-evidence/1`, `aisef-v2-project/1` and `aisef-v2-run/1` are read
  forever with 2.2.0 semantics (CR-1…CR-12). New required semantics need a new version id.
- Evidence under an old id stays valid only for that id (RFC §35). No `source_sha256` is rebound. Historical records
  and the ledger are immutable (CR-13…CR-16).
- Every claim names its weakest path (RFC §24). OPAQUE or PARTIAL is never reported as FULL.

## 8. Changes by wave

Each row gives: the change, where it lives (lane files per `DEPENDENCY-DAG.md` §4), the invariants it must
preserve, and the defects it closes.

### W1 — Evidence efficiency and CI/release foundations (W1a: no `aisef2/` edit; W1b: E5 in `story_runner.py` only)

> **W0-closure amendment:** the frozen F5 design is `W1-DESIGN.md` and supersedes this section where they differ —
> the engine lives at `validation/v23/impact.py` (outside the Q0 checker inventory), adds round-scoping (F5-ROUND) and a
> dynamic-reach tier, and E5 moves to W1b.

**F5 — incremental evidence engine.** NEW `validation/v2/impact.py`, consumed by `mutation.py` (`_problems_v2`
`:2519-2530`, `target_problems` `:2568-2580`; `verified_reuse_current` `:1623` becomes one engine case),
`currency_dag.py` and the release-record readers.

*Unit of evidence.* A recorded result `r` (path, sha256 and committing commit, as in `mutation.committed`
`:2400-2417`), measured on commit `m`, judged at head `h` on platform `p`.

*Impact inputs.* Each is recomputed; only provenance is read from `r`.

| Owner-ruling input | Concrete check (fail-closed) |
|---|---|
| Source identity + dependency closure | Compare the target file's blob at `m` and at `h`. If it differs, compute the **reach set**: the AST closure of names from the target function within the module, plus every top-level statement that runs at import. Any change in the reach set → INVALIDATED. A module with dynamic name access (`globals()`, `exec`/`eval`, non-constant `getattr`/`setattr` on a module, `importlib`) disables the reach set → INVALIDATED. A function slice alone never proves equivalence. |
| Generator inputs/config | Regenerate `mutants(src_h, func, _enum_members(...))` and compare it with the recorded mutant list (`s2_mutation_record.py:172-175`). Also bind a digest of the generator's source segments (`_SWAP` `mutation.py:1549`, `_enum_members` `:1648`, `_root` `:1689`, `mutants` `:1720`, `null_mutant` `:2369`), in the style of `criteria_sha256` (`v21_mutation_record.py:75-84`). |
| Kill-test identity + semantics | The kill set equals the declared `TARGETS` entry (`s2:162-163`). Every file of the kill-test closure (`s2:113-148`) is byte-identical between `m` and `h`. The execution-order table digest is unchanged when it was recorded. |
| Transitive behaviour-changing deps | Any changed non-test file in the import closure of the target module ∪ the kill-test closure, other than the target file → **INVALIDATED**. This is stricter than `s2:176`, which only reports such files. |
| Platform + environment | The OS family, Python minor and implementation must equal `p`. Historical records carry no platform field (AO-1), so platform is taken from provenance (worker history, ruling). If it is unknown → UNRESOLVED. A Windows result is never reused cross-platform. |
| Provenance, ruling, verdicts | `m` is an ancestor of `h`. The record bytes equal the committed blob. The recorded verdict re-checks under the existing rules **at the measured digest**. A cited owner ruling is pinned by sha256, not by `.is_file()` (#14). |

*States.* Each result gets exactly one:

- **MEASURED** — measured fresh in this campaign at `h`.
- **VERIFIED_REUSE** — every input passes. A NEW proof record under `closure-evidence/v2/v2.3/` cites `r` by sha256,
  with the input digests and the rule version; `r` keeps its measured `source_sha256`.
- **INVALIDATED** — an input changed with no equivalence proof. The result must be re-measured.
- **UNRESOLVED** — an input cannot be computed (no git or history, a parse error, a dynamic module, an unknown
  platform). The gate FAILs; UNRESOLVED is never accepted.

Reports count MEASURED and VERIFIED_REUSE separately and never sum them as "measured".

*Self-calibration.* `checker_calibration.REGISTRY` (`:571`) gains the impact checker. A clean input PASSes. Each
seeded known-bad input FAILs: a stale source, a kill-test edit, a generator edit, a dependency edit, a platform
swap, a tampered record, and a ruling that is present but altered. An always-REUSE mutant of the checker must make
the calibration FAIL.

*Order (owner ruling).*

1. Build the engine and its negative tests.
2. Replay the committed history offline. The `c15d5b10→0fdfc022` transition must give VERIFIED_REUSE for exactly
   the 42. `v2.2.0→HEAD` has no kernel change, so it must give no INVALIDATED kernel target.
3. Run a dry-run classification of the real affected scope.
4. Only then, a bounded measurement of the INVALIDATED set.

There is no full campaign. Cost and scope numbers: `MUTATION-IMPACT-BASELINE.md`.

**EVID-COUPLING-01 (P1), solved by F5 rather than an allowlist.** A version-stamped record node (`release_calibration`
`:43-57`, `p5_acceptance` `:896-898`, `v21_conformance_ruling` [A]) is keyed by its *content* inputs:

- both kernel identities;
- the deriving script's digest;
- the upstream node digests;
- for calibrations, the probes' EXECUTION_DIGESTs and the fixture shas.

The version string is not an input. A version-only bump therefore yields a typed VERIFIED_REUSE node that resolves
through the currency DAG (`DEPENDENCY-DAG.md` EVC-1). Nothing is re-stamped, and `aisef2/app/calibrations.py` stays
byte-unchanged (CR-15).

**Other W1 components:**

- **F2.** Release exceptions derived from test-declared markers, for sealing/platform-harness categories only
  (`DEPENDENCY-DAG.md` R6). A product-category marker fails the meta-test.
- **BUILD-REPRO-01.** `repro_dist.normalize` (`:25-45`) maps member modes to git semantics: regular files `0644`,
  executables `0755`, directories `0755`. A contract test rebuilds from a perturbed-mode tree and from a tree with
  ignored files present. Claim scope (corrected at the W0 freeze): exactly what the W1-DESIGN §6 CI `repro` job tests — GitHub `ubuntu-latest`
  CPython 3.11–3.14, fresh + perturbed copies, interpreter and zlib recorded per leg; the local 3.14 match was a one-off
  observation, not a test. Other deflate implementations / OSes are not claimed (RISK-REGISTER). `da3ea33f` must still rebuild to the 2.2.0 digests (CR-17).
- **REL-GOV-01.** A separate production-governance control, NEW `validation/qualification/release_governance.py`. It
  reads the `pypi` environment's protection state read-only and FAILs until a required reviewer exists. The
  checkpoint counts as verified only when an observed `publish` job enters `status: waiting`. The owner configures it;
  the agent never changes settings.
- **GF-AUTH-1.** The live destructive-authority check and the checker non-vacuity run are live-tree static checks,
  not record currency. By the gate's own rule (`sealing_gate.py:10-11`: "never a live-tree static check"), they belong in `unit`. Only their
  record comparison stays sealed. To adjudicate in W1.
- **C4.** Closes WONT_DO_WITH_OWNER_RATIONALE (directive:33) once its W1 qualifying test (candidate==base → 0 reviewer/scanner/quality calls, `test_v23_c4_noop.py`) is green. Any future no-op route must go through the E5 stage
  machine, never a pre-stage short-circuit (the 30da62a6 revert [checklist]).

**Invariants preserved:** V (reproducible qualification), VI (immutable provenance), CR-15/16, charter §4 (no
rebinding, no allowlist masking).

### W2 — Kernel lifecycle, authentic evidence, accounting

| ID | Change | Location | Must preserve | Closes |
|---|---|---|---|---|
| **E5** (W1b, owner ruling) | `_attempt` gets typed `Stage`s (ACQUIRE … END) with a monotonic `_Stages.advance` guard and **one `try … except Exception` from `story/begin` to the end of POST_MERGE, no `finally`** — W1-DESIGN §4 (H1–H9): a fault is contained (synthetic closer, constant-label false row, false `gate/decision`, `failure/observed` UNKNOWN, `story/rollback`, dispose, end, re-raise the same object) only where the journal allows it; faults while the repository state is unknown, at/after DECIDE, and every `BaseException` keep today's interrupt path | `aisef2/orchestrate/story_runner.py` + `aisef2/app/run.py:693` (refusal branch only); `merge.py`/`gate.py` unchanged | success-path journal byte-identical (W1-DESIGN §4.6); R6/R3/authority inventory/Q0 unchanged (H9) | #2, #39a |
| **E6** | One pure-value table, `state × event_type → next \| REFUSE`. Both `story_state.step` (`story_state.py:26-71`) and `format3._story_active` (`:173-177`, via `f2._attempt`) read it | NEW `journal/transitions.py` | Formats 1–3 accept and refuse exactly as in 2.2.0 (CR-1, CR-4): shadow over every fixture and corpus journal (CT-2/CT-3). No wall-clock, no prose | #11 |
| **E1** | The verdict becomes one composed **reporting fold** over the journal, with the plan as a parameter. It replaces `delivery`/`productproof`/`outcomes_from`/`unfinished` (`run.py:355-411`). `verify` runs `oracle_problems` (`fold.py:80`) on it | NEW fold module beside the projections; **not** added to `PROJECTIONS` or `ControlProjection` | F11 closed list (AO-3); 0 verdict divergence on the CT-1 corpus before cut-over. If any gate must cite it: RFC §21 amendment → **owner STOP** | E1 |
| **E7** | One `RunRecord` builder + a `Stage` enum in place of the `rec["stage"]` strings (`run.py:492-696`). `execute` splits into prepare / run_stories / finalize. Finalize is total: each field derivation is guarded on its own. `verify` re-derives through the same builder functions | `app/run.py`, `app/usage.py` | RUN.json bytes identical on existing fixtures before any new field (golden). `/1` stays readable | #18, #41 (as a *named new* algorithm, CR-17/CT-9), #42, V21-35 |
| **E2 + E4** | `provider/request` gains an owner-typed `reservation` (turn cap × max price). `provider/result` gains `stream_sha256` + segment bounds. Interrupt and repair closers charge `max(reservation, stream)`. Verify checks each segment before `_spend` (`verify.py:78`). A torn segment → UNKNOWN, never 0 | **journal format 4** (NEW `journal/format4.py`; delegates 1–3 to `format3.reconstruct` unchanged, CR-1); `client.Budget`, `run_scope.interrupt` `:224-228`, `repair` | IV (owner-typed budgets); spend never silently 0 or paid; format-3 rules frozen for old runs (CR-4) | #12, A-03 |
| **A2** | Per-run ephemeral Ed25519 keypair (QĐ#1). The public key is declared **in format-4 `run/begin`**, inside the chain (CR-7), and printed for off-box escrow **before any session runs**. At finalize, sign `(run_id, head, evidence anchor, kernel_digest, runspec_hash)`, then discard the private key. Add `--verify --expect-pubkey` | NEW `journal/sign.py`: pure-stdlib RFC 8032 (hashlib.sha512 + integer arithmetic), checked against the RFC 8032 §7.1 vectors; no new dependency (AO-4). `verify`, `cli` | Claim = "authentic w.r.t. the escrowed public key, against post-run rewrite". Not claimed against a same-user process during the run until D1/D3 (THREAT-MODEL M2). 2.2 runs → REFUTED "unsigned" under `--expect-pubkey` (CR-5/6) | #10, #22, V21-49 |
| **E3** | An OS-observed exit/signal tier: a controller-spawned subprocess whose exit or signal comes from `waitpid`, the `do_subprocess` pattern (`process_effect.py:680`). Added as a **new observation class** with a capability-version bump and `CAPABILITY_CHANGES` selectors scoped to the new class, so `migrate` keeps the approvals of every other contract (`bundle_cli._assess` `:219-264`). EXECUTION_DIGEST rows are regenerated | `probe/*` + `app/calibrations.py` (regenerated output only) | §35 (old evidence valid for the old id only); `RELEASES["2.2.0"]` entry before any capability bump (CR-8/CT-7); no claim that in-process return-value forgery is closed | E3, #16 |

**E5 rules:** superseded by W1-DESIGN §4.3 (H1–H9) — the earlier "always write `story/dispose` … `story/end`" rule is withdrawn: `story_state`/`terminal_state` refuse those events before an outcome, so a blind `finally` would mask the original fault with a `ProjectionError`.

**Order inside W2:** (E5 already landed in W1b) → {E6, E7, E2+E4} → {E1, A2 integration}. E3 is parallel; it shares no files with the others
(`DEPENDENCY-DAG.md` §4).

**One format bump.** Format 4 is opened once in W2. It also carries the C7/G6/C5 schemas, so W3/W4 need no format 5.
A schema that cannot be frozen at the W2 exit means a format 5 later. Nothing is ever added to an existing format
without a version.

### W3 — Security isolation, attestation, adapters

| ID | Change | Must preserve | Closes |
|---|---|---|---|
| **D1** | Reuse `confine.wrap` (`confine.py:177`) for the probe subject and the developer-test runner (`quality/test_execution.execute` `:443`). Policy: the worktree is writable, the rest read-only, no network. The test result channel moves out of the subject's write domain: the harness reads a pipe/fd and the lines are MAC'd, as in the probe protocol | Tests stay engineering evidence (III); confinement is measured, never assumed (`run.py:603-607` pattern); refuse on unsupported OS | #21, V21-02; GF-QUAL-2 (channel), GF-SEC-3 (PM-8 reachability) |
| **D2** | A macOS Seatbelt backend behind the same `measure()` canaries; declared best-effort. Windows keeps no backend and refuses confinement | Fail-closed on non-Linux/macOS (`confine.py:181-182` [A]); weakest path named | #43 |
| **D3** | A loopback key broker (NEW `app/keybroker.py`). The session env and client config hold no key. The client points at `127.0.0.1`; the broker injects Authorization and allowlists only the attested endpoint. `measure` asserts that no key is present | No raw key in env, config, logs or prompts (THREAT-MODEL M4); redaction stays as defence in depth | #9, #20, V21-29 |
| **C7** | The broker records the served model and fingerprint of **every** response as format-4 `provider/attestation`. A drift check covers the whole run. Any extra probes are charged through the ledger | Fingerprint = drift detector, never proof of weights (RFC §23) | #8 |
| **C8** | `ClientAdapter` with 4 methods (`argv`, `config_endpoint`, `parse_stream`, `identity`), in NEW `app/client_adapter.py`. OpenCode becomes the first adapter; `settings.CLIENTS` (`settings.py:35`) becomes the adapter registry | Byte-identical OpenCode behaviour; `usage.CLASSES` stays the token contract | C8 |
| **G3** | Client = source checkout at commit X + patch check, in the preflight, before any spend | Byte pin (D4) kept as an alternative | G3 |

**Dependency:** D3 → C7 (the broker is the attestation point). D1 raises the strength of A2's claim.

### W4 — Orchestration, durability, AI feedback

| ID | Change | Must preserve | Closes |
|---|---|---|---|
| **G6** | `aisef run --resume <out>`. Only for an unfinished, unsigned, format-4 run of **this** kernel (CR-11). Sequence: lease → sentinel TORN preflight → synthetic closers (`OUTCOME_UNKNOWN`, reservation-charged) → format-4 `run/resumed` (fingerprint: bundle, kernel, route, base, head, ledger) → stories COMMITted in the journal are reused; every other story prints `why_not`. Exclusive with a `--parent` claim (`DEPENDENCY-DAG.md` §5c) | Append-only journal, single writer; plain `--out <existing>` still refused (`run.py:478`); no unaccounted replay of a paid request (E2); a signed run is never resumed; V21-80 kept | G6 |
| **C5/G9** | Waves derived from `depends_on` + declared write-scope, after #5 is reconciled (`bundle.py:124-136` vs plan criterion deps). One worktree per story; merges serialized in plan order; one `RunScope.append` lock. Journal order = the true append order. Each story's event subsequence equals its serial run. Closing identity: every `provider/request` has exactly one accounted result; attempts = sessions | Dense `seq`, one writer (RFC §3); projections stay per-story (no cross-story commutation assumed); disjoint write-scope proved before parallelism, otherwise serial | C5, #5 |
| **C1 + C3b** | A mid-session monitor in the client wait loop grades **snapshots** (a tree written into the object store, probed in a separate checkout), never the live worktree. A stop is a typed, journaled control decision. C3b ships default-OFF until the owner ratifies it | VII (no prose control); `NO_SIDE_RETRY_COUNTER` [A]; stops cite journal events | C1, C3b |
| **C6** | A separate reviewer route with its own preflight, ledger and cost line; REVIEW budget owner (`owner.py` [A]) | D-002 (a model review never blocks alone); V21-11 is decided (owner-reconciled, MASTER-CHECKLIST: NEW_WORK W3, part of D1 — the verifier gets its sandbox and worktree from its own StoryScope); the claim wording follows what D1 measures, no further owner question | C6 |
| **C10, G10** | Owner-authored public reproducer facts (a bundle `/2` field, dual reader, CR-8). Owner-approved lessons that cite journal events. Both are tripwire-scanned and wired through `invariants.evidence.admit` as **Context**, never evidence | VIII (`evidence.py:47` gets its first production caller); III (no hidden stimulus) | C10, G10, V21-19, #13 |

**Prerequisites:** E5 (stage seam), E2/E4 (spend), A2 (signed history), GF-LIN-1 (lineage "gone" must not depend on
TZ/locale) → G6/C5/C1.

### W5 — Developer UX and the agent-independent acceptance gateway

| ID | Change | Must preserve |
|---|---|---|
| **B6a–d** | `classify_or_reason` diagnostics (NEW `probe/diagnose.py`, never on a control path); seal-time validation; `explain` shows the compiled assertions; `bundle probes [--kind] [--skeleton]`; readiness papercuts | Diagnostics never decide; `observation_class` stays the gate |
| **B4** | `aisef bundle draft REQ.md` (NEW `app/draft.py`) emits `aisef-v2-authoring/1` only. It writes no approval, hash or oracle; `seal` derives everything; approval stays `human:<name>` (`approval.py` [A]). A static check enforces "draft never approves", like MIGRATE_NEVER_APPROVES [A] | I (requirement authority). Plan approval binding is THREAT-MODEL S3 (owner STOP before B4) |
| **G4** | Retry evidence served as files in the worktree; the prompt carries a pointer; truncation attribution + a floor; tripwire-scanned; bounds `retry_feedback` | III, stimulus-free; GF-SEC-2 |
| **B5** | `aisef grade` (NEW `app/grade.py`): an approved bundle + `--base`/`--head` git refs or a diff from any agent. It reuses the E5 stage machine minus DEVELOP: ADMIT at base → PROVE_CANDIDATE (two checkouts) → QUALITY → optional REVIEW → POST_MERGE simulation → E1 verdict fold → E7 record → A2 signature. It makes no provider call and needs no ClientAdapter. The candidate runs confined (D1) | The agent's diff and claims are data (VII); the verdict comes only from the probes; `--verify` works on grade output |

### W6 — Independent evaluation and release

- **B2.** A frozen ground-truth corpus under NEW `validation/v23/ground_truth/**`. Labels are signed before
  measurement. False-accept and false-reject are reported by contract scope.
- **Release.** One frozen RC, all charter §2 gates, REL-GOV-01 observed `waiting`, CT-1…CT-10 green, and one owner
  authorization before publish.

## 9. Invariant → wave impact

| Invariant | Touched by | Preservation check |
|---|---|---|
| I Requirement authority | B4, C10 | draft-never-approves static check; approvals stay human |
| II Semantic determinism | E5, C5, C1 | stage order; snapshot-only grading; per-story subsequence equal to serial |
| III Independent evidence | D1, G4, C6, B5, V21-11 | test channel out of the subject's domain; stimulus-free files; verifier scope from its own StoryScope |
| IV Typed ownership | E2, C6, C1 | owner-typed reservation; REVIEW budget; typed stops |
| V Reproducible qualification | F5, E3, C8 | typed reuse; EXECUTION_DIGEST re-calibration; adapter identity in RunSpec |
| VI Immutable provenance | E6, A2, G6, C5 | formats 1–3 frozen; key in chain; append-only resume; single writer |
| VII No prose as control | C1, C8, B5 | typed stops; `parse_stream` typed; diff as data |
| VIII Memory ≠ evidence | G10, C10 | `evidence.admit` wired |
| IX No developer artefact at parent | E5, B5 | ADMIT precedes DEVELOP / PROVE in the stage table |

## 10. Reconciliation with the other W0 artifacts

- **CODE-AUDIT.** Every wave row names the defects it closes; wave homes for all 45 are in `DEPENDENCY-DAG.md` §1b.
  #7's diagnosis is superseded by RISK-REGISTER BUILD-REPRO-01 (`DEPENDENCY-DAG.md` R4).
- **RISK-REGISTER.** EVID-COUPLING-01 → W1 F5 (§8). REL-GOV-01 → W1 guard + owner action. BUILD-REPRO-01 → W1
  contract.
- **MASTER-CHECKLIST.** Every NEW_WORK capability in §8 is one row. E8 is NEW_WORK W5 as a written re-evaluation (MASTER-CHECKLIST); it stays a non-goal unless the B5/C8 freeze
  shows a need. In this design B5 runs locally without an executor seam, so none is shown. C3b needs a row
  (`DEPENDENCY-DAG.md` R1).
- **RELEASE-CHARTER.** §1 claims 2–7 map to W2–W5 here. §2 gates map to W6. §4 rules are the envelope in §7.
- **Correction to `DEPENDENCY-DAG.md` §4 W2c.** "NEW verdict projection" must be a reporting fold, not a seventh
  `ControlProjection` (AO-3).

**Architecture-level STOPs** (owner rules: only security guarantees, immutable evidence, spend or publication):

- E1 needing a gate-citable seventh projection (avoided by design).
- G6 in any form that appends to a finished or signed run, or reuses a plain `--out` (excluded by design).
- An E3 capability change that would withhold approvals of unaffected contracts (avoided by class-scoped
  `CAPABILITY_CHANGES`).
- Already listed elsewhere, not repeated: REL-GOV-01, DISC-1, S2 paid cron, S3 plan binding, S4 adequacy demotion
  (DEPENDENCY-DAG §5a). V21-11 is decided (W3 D1 acceptance), not a STOP.

---

**Read directly for this document:**

- `aisef2/app/run.py:1-130,255-764`
- `aisef2/orchestrate/story_runner.py` (all)
- `aisef2/runtime/run_scope.py` (all)
- `aisef2/journal/event.py:1-30,84-92`; `fold.py:130-161`; `format3.py:160-222`; `format2.py:125-135`;
  `projections/__init__.py` (all); `projections/story_state.py` (all)
- `aisef2/app/verify.py:1-40,200-260`; `bundle.py:124-137`; `client.py:340-368`; `confine.py:24-34`;
  `bundle_cli.py:219-270`; `errors.py:1-12`
- `validation/v2/mutation.py:53-60,1553-1650,1842-1866,2400-2450,2519-2632`
- `validation/qualification/s2_mutation_record.py:113-177,262-285`; `v21_mutation_record.py:1-110`
- `validation/v2/version_forward.py:30-64,174-179`; `currency_dag.py:46-60,85-100`; `b1_bindings_check.py:1-60`
- `validation/qualification/release_rc.py:81-93`; `repro_dist.py:25-45`; `p5_acceptance.py:890-900`
- `.github/workflows/tests.yml:50-66` and the job headers; `tests/v2/sealing_gate.py:10-12,20-40`
- `aisef/cli/parser.py:407-432`; `aisef2/app/cli.py:60-80`; `pyproject.toml` `[project]`
- Definition lines for the entry points in §1, located by grep
- RFC §1–§5, §17–§21, §23–§25, §34–§35; `IMPROVEMENT-ROADMAP.md:28-197`; `ROADMAP-2.2-CHECKLIST.md:47-58`
- The sibling W0 docs (`DEPENDENCY-DAG`, `COMPATIBILITY-MATRIX`, `THREAT-MODEL` §5–§8)

Everything else is marked [A] or [GF].
