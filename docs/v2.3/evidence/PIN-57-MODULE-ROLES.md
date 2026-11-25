# PIN-57 — the three unregistered v2.3 checkers: module identities, callers, trust boundaries (2026-11-26)

**Status: documentation only.** This file assembles the evidence that the owner's PROPOSED Decision 2
(CONDITIONAL GO) requires — "Retain the three modules outside the calibrated checker registry only if each has an
independently demonstrated non-checker role. Document all three identities, their callers, trust boundaries and
negative tests. If any module can determine a qualification verdict, it requires proper checker
registration/calibration or a new exact Owner ruling." It confers **no owner approval** (PIN-57 ruling §4,
2026-11-25: "No implied approval is granted"). Nothing here registers, calibrates, re-pins or relaxes anything.
Every claim cites file:line at HEAD `bc8668f040823b0fea3a6875142847d493179659` (release/v2.3-big); all measurements
in this file were taken on 2026-11-26 on that tree.

---

## 1. The pinned artifact and the measured registry state

| item | value |
|---|---|
| pinned test file | `tests/v23/test_v23_q0_round.py` |
| its git blob sha1 at HEAD | `8d518bf8f392300a6d5e280d74f6a2f3e360a5d6` (verified current: `git rev-parse HEAD:tests/v23/test_v23_q0_round.py`, 2026-11-26) |
| its file sha256 | `9b9433f33c1176367a80dd2a3144f37f8f3e2250d6cd62df9a3956bb3ca8c7cb` |
| registry owner module | `validation/v2/checker_calibration.py` (blob sha1 `56bf4453ad02aa907e39c4b8e0942c3387775915`, sha256 `2d75becfe6892ecf3be7f09c4a7443386da9f8dadc0264748fd9bbac75ee2f12`) |

**The pins.**
* `tests/v23/test_v23_q0_round.py:73` — `self.assertEqual(self.result["calibrated_count"], len(cc.REGISTRY))`
  (Q0RoundV23, a `round_gate` class; `cc` is `checker_calibration` loaded via `q0_round.cc()`,
  `validation/v23/q0_round.py:67-73`).
* `tests/v23/test_v23_q0_round.py:223` — `self.assertIn("calibrated 56 of 57 registered checkers", Q.problems(fewer, …))`.
  This is a **synthetic** record (`fewer` = the committed v2.2 record with one checker dropped,
  `calibrated_count=56`, line 219); the literal `"of 57"` pins `len(cc.REGISTRY) == 57` exactly. A registration
  (`REGISTRY += V23_CHECKERS`, 57 → 60) turns this line red; line 73 turns red on any run whose calibrated count
  is not the full registry.
* The problem-string shape itself is pinned at `tests/v23/test_v23_q0_round.py:405`
  (`f"calibrated 0 of {len(cc.REGISTRY)} registered checkers"`, Q0Rules — always-run).

**Measured registry state (2026-11-26, this tree).**
* `len(cc.REGISTRY)` = **57** (measured by import at HEAD; the list is `checker_calibration.py:641-671`).
* `V23_CHECKERS = (_f5_gate, _f5_recorder, _released_evidence)` at `checker_calibration.py:680` — built, with
  committed known-bad fixtures (`tests/v2/fixtures/known_bad/f5_gate.json`, `f5_recorder.json`,
  `released_evidence.json`), and **not in REGISTRY** (measured: none of the three names appears among the 57).
* **Correction of the briefing premise:** the live calibrated count on HEAD is **54 of 57, not 56 of 57**.
  Measured 2026-11-26 via `q0_round.run()` (i.e. `checker_calibration.run()` inside `in_round("v2.3")`):
  `calibrated_count: 54, checker_count: 57`. The three registered-but-uncalibrated checkers, each red on its
  `clean()` (each still rejects its fixture, so these are clean-tree reds, not broken checkers):
  * `b1_bindings` — `aisef2/app/run.py::_close: aisef2/app/run.py moved since the manifest froze` (the known
    W1b wait on OD-B1B, `docs/v2.3/amendments/Q0-1-V23-ROUND.md:195-198`);
  * `currency_dag` — `P5-PROPOSAL: INVALIDATED: closure-evidence/v2/v2.3/P5-PLAN-V2.2-PROPOSAL-1.json does not
    re-derive from the tree`;
  * `mutation` — `aisef2/orchestrate/story_runner.py::_Stages.advance: measured on a dirty tree …` (F5 cut-over
    wait, same amendment).
  "calibrated **56** of 57" exists only as the synthetic pinned string at test line 223; the committed v2.2 record
  (`closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json`) is 57/57. There is no single
  registered-but-uncalibrated checker on HEAD; there are three, named above.

**The three checkers cover FOUR module files** (`checker_calibration.py:672-680`, sources at :584, :627, :638):

| unregistered checker | source module(s) |
|---|---|
| `f5_gate` | `validation/v23/ci_gate.py` + `validation/v23/impact.py` |
| `f5_recorder` | `validation/v23/observe.py` |
| `released_evidence` | `validation/v23/released_evidence_guard.py` |

**The live red this creates:** `q0_round.v23_scope_problems` (`validation/v23/q0_round.py:165-183`, rule Q0P-2)
requires every `validation/v23` module to be a registered checker's source or a member of the closed list
`NOT_CHECKERS_V23` (`q0_round.py:60-61`: `__init__.py`, `ledger_digest.py`, `q0_round.py`, `replay_v22.py`).
Measured on HEAD, it names exactly the four files above as `validation/v23 module with no calibration` — truthfully
red, as the comment at `checker_calibration.py:672-679` states. That comment also records the standing conflict:
the owner ruling 2026-11-22 §D mandates "every new validation/v23 checker registered and calibrated", while the
pinned test forbids growing the registry and ledger seq 13 forbids re-pinning `V23_PINNED`. The seq-13 R6 draft's
NOT_AUTHORIZED list additionally names "a validation/v23 module without a registered, calibrated checker"
(`docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R6.md:38`), so "retain outside the registry" needs the new exact ruling
Decision 2 proposes; it cannot be inferred from the current texts.

**Definition used below** (from the proposed Decision 2 as briefed): a module *determines a qualification verdict*
when its output alone can flip a target/record/release between QUALIFIED/accepted and NOT-QUALIFIED/refused in any
gate — B1 bindings, the Q0 round guard, P5 acceptance/reverification GUARDS/GUARDS_V23, `mutation.py --check`, the
release gates in `.github/workflows/`, or `validation/qualification/release_qualify.py`. A fail-closed guard that
can only REFUSE is still verdict-determining in the refuse direction.

**Precedent the analysis uses:** `validation/v23/q0_round.py` (a `NOT_CHECKERS_V23` member, not one of the three)
appears in `GUARDS_V23` at `validation/qualification/p5_acceptance.py:986-987`
(`"q0_round": ["validation/v23/q0_round.py", "--check"]`) — verified. Its exit code is consumed by
`guard_problems` (`p5_acceptance.py:967-981`: any non-zero exit is a problem) inside
`write_v23_reverification` (`p5_acceptance.py:1003-1018`: problems ⇒ the round-v2.3 P5 record is **refused**,
`raise SystemExit`), and by the round-gated `test_P5_REVERIFICATION`
(`tests/v23/test_v23_rounds.py:309-314` via `p5_q0_guard_problems`, :172). So q0_round is verdict-determining in
the refuse direction **by design**, and its retention outside the registry rests on the ruled
`NOT_CHECKERS_V23` + `V23_PINNED` + own-negative-tests route — the route a Decision-2 ruling would have to extend
(or not) to the modules below.

---

## 2. Module 1 — `validation/v23/ci_gate.py` (+ engine `validation/v23/impact.py`): checker `f5_gate`

### 2.1 Identity

| file | git blob sha1 at HEAD | sha256 of file bytes | one-line purpose (docstring) |
|---|---|---|---|
| `validation/v23/ci_gate.py` | `bb379f6bc383652c4ed075f1624e0315774ae4cc` | `b44fd50ed4937353cbcd44576fea068e378841a15e9923949e607e1b0d17b987` | "Two-tier F5 CI gate (owner ruling 2026-11-22 §4) — a thin wrapper over validation/v23/impact.py." (`ci_gate.py:1`) |
| `validation/v23/impact.py` | `0d82f5b93e7695ea70e7af2de143e1032322702f` | `79609ac7e1c1d09002c92ad5d9f7bedaacfee18cf186d94faedd971d5f523045` | "F5 static impact engine (AISEF v2.3 W1a, increment 1): the evidence state of every live mutation target." (`impact.py:1`) |

The `f5_gate` checker (`checker_calibration.py:576-584`) names both files as its sources, so Decision 2's
"module 1" is this pair: `impact.py` is the classification engine ("the only classification authority",
`ci_gate.py:64`), `ci_gate.py` the CI policy over one engine run.

### 2.2 Callers

`ci_gate.py`:
* **CI, subprocess, gate:** `.github/workflows/mutation-incr.yml:58` — `python -P validation/v23/ci_gate.py --tier
  develop` (job `gate`: every `release/**` push and every PR); `:81` — `--tier rc` (job `rc`: every
  `v[0-9]*.[0-9]*.[0-9]*` tag, or manual dispatch with `tier=rc`). Permissions `contents: read`, no secret.
* **Library (unregistered checker):** `validation/v2/checker_calibration.py:581` (`_f5_gate` imports it; dormant —
  see §2.4).
* **Tests:** `tests/v23/test_v23_ci_gate.py:25,47-57,167-173` (imports; drives `main()` with the engine mocked);
  `tests/v23/test_v23_release_governance.py:598-599,611` (pins the exact workflow command strings and that the
  file exists).

`impact.py`:
* **Library, gate:** `validation/v23/ci_gate.py:64,173` (`impact.report(impact.classify(impact.ROOT, impact.BASE,
  "HEAD"))` — no observations are passed).
* **Library, gate:** `validation/v2/mutation.py:2854-2859` (`--check --states`: `impact.classify` states feed
  `states_bad`); `:2866-2875+` (`--affected` / `--run-affected`: the engine selects the affected set and refuses a
  tree it classified dirty, exit 2).
* **CI, subprocess:** `.github/workflows/mutation-incr.yml:104` (job `plan`, manual dispatch:
  `impact.py --classify --affected` — listing, not a gate).
* **Round-gated tests:** `tests/v23/test_v23_rounds.py:197-199` (`_f5_states` = `impact.classify(ROOT)`),
  `:227-236` (`f5_problems`: every live entry of a historical mutation record MUST be MEASURED or VERIFIED_REUSE
  in round v2.3), `:322-331` (`test_MUTATION_historical` asserts `f5_problems == []`);
  `tests/v23/test_v23_calibration_rows.py:170`.
* **Library:** `validation/v23/observe.py:960,981` (lazy import, for the recorder's own verify path).
* **Tests:** `tests/v23/test_v23_impact.py:34`, `test_v23_review1.py:27`, `test_v23_review2.py:20`,
  `test_v23_observe.py:30`.
* **Vocabulary only (no import):** `validation/qualification/release_calibration.py:82,84` copies the four state
  names and BASE as constants; it does not call the engine (verified: no `validation.v23` import there).
* **Not consumed by:** B1 bindings (`validation/v2/b1_bindings_check.py` has no `validation/v23` reference;
  `mutation-incr.yml:18` "Never runs b1_bindings_check"), `validation/qualification/release_qualify.py` (no
  reference), the P5 GUARDS/GUARDS_V23 tables (`p5_acceptance.py:552-556,986-987` — neither file appears).

### 2.3 Trust boundary — can it determine a qualification verdict?

**Yes — both directions. This is the module pair's designed job.**

* **Refuse direction.** The `rc` job of `mutation-incr.yml` fires on every release-shaped tag (`:24,61`) and runs
  `ci_gate --tier rc`; exit 1 whenever ANY live target lacks MEASURED/VERIFIED_REUSE evidence, exit 2 on checker
  malfunction / false-current reuse / negative-control regression (`ci_gate.py:44-45` exit contract;
  `main` at `:165-212`). A red `rc` job refuses the tag's incremental qualification. The `gate` job refuses PRs
  and release-branch pushes on the exit-2 conditions (it exits 0 on incomplete evidence, reporting
  `EVIDENCE: INCOMPLETE (NOT QUALIFIED)` truthfully — `ci_gate.py:209-210`). In-tree, `mutation.py --check
  --states` flips `mutation: PASS` to `FAIL` (exit 1) on any state outside MEASURED/VERIFIED_REUSE
  (`mutation.py:2858,2863-2864`) — W1-DESIGN §2.5 names `--check --states` as *the* F5 gate until the cut-over
  (`docs/v2.3/W1-DESIGN.md:220`). The round-gated `test_MUTATION_historical` goes red on the same condition
  (`tests/v23/test_v23_rounds.py:331`).
* **Accept direction.** `impact.py`'s VERIFIED_REUSE is the ONLY path by which a legacy (v2.2-and-earlier)
  mutation target counts as currently qualified without being re-measured (`impact.py:1-30` docstring;
  `tests/v23/test_v23_rounds.py:227-236`). Its classification alone flips a target from NOT-QUALIFIED
  (INVALIDATED/UNRESOLVED) to accepted (VERIFIED_REUSE) in every consumer above, and a green `--tier rc` run is
  that workflow's "evidence complete" verdict for the tag. `ci_gate.py` adds the accept-side policy: which bases
  count (`reuse_problems`, `ci_gate.py:129-150`), which states count as complete (`COMPLETE`, `:74`), and the
  four pinned in-process negative controls that must pass before anything is accepted (`CONTROLS`, `:66-71`;
  fail-closed loading, `run_controls` `:84-101`).
* Neither tier takes an exception list; the literal string "allowlist" is pinned absent from both the gate and
  the workflow (`tests/v23/test_v23_release_governance.py:605-611`).

### 2.4 Negative tests

* **Engine negatives:** `tests/v23/test_v23_impact.py::ImpactTest` (`:908` onward) — the W1-DESIGN §9 negatives
  N1–N33 plus D1–D5/F2/F3/I4 cases on toy git repositories (target slice, weakened kill test, dropped killer,
  platform claims N7a–N7g, tamper N8, shallow/missing basis N10, git failure never clean `:1173`, acceptance
  basis only on reuse `:1056`, v2.2.0 label only for the pinned sha `:1045`, …).
  `tests/v23/test_v23_review1.py::Review1/Review1Parser` (`:81,397` — SND1–SND9, AUD1–AUD2, PROV1–PROV4, STR2–STR5)
  and `tests/v23/test_v23_review2.py::Review2` (`:98` — R2-1/R2-2 case-folding and alternate-entry-point reds)
  pin the two review findings red-before/green-after.
* **Gate negatives:** `tests/v23/test_v23_ci_gate.py::Gate` (`:45-173`) — a malformed table fails either tier
  (`:101`), false-current reuse fails either tier (`:124`), a broken control fails before the engine runs
  (`:159`), controls that cannot be loaded fail closed (`:166`), rc fails on today's real (incomplete) table
  naming the count (`:80`), rc passes only a fully MEASURED/VERIFIED_REUSE table (`:86`).
* **Wiring negatives:** `tests/v23/test_v23_release_governance.py::IncrementalQualificationJob` (`:568-612`) —
  triggers/permissions/no-secret, the exact two tier commands, no campaign, no allowlist string.
* **In-gate controls:** every `ci_gate` run itself re-runs four pinned engine negatives in-process and fails
  closed if one cannot load, run, or pass (`ci_gate.py:40-43,66-71,84-101`).
* **Unpinned failure mode:** nothing exercises the `f5_gate` **Checker object** or its committed fixture
  `tests/v2/fixtures/known_bad/f5_gate.json` while it stays outside REGISTRY — no test in the tree references
  `V23_CHECKERS` or the checker name `f5_gate` (grep over `tests/`, 2026-11-26). The Q0 anti-gaming sweeps
  (always-PASS mutant, wrong-reason, stale-fixture — `tests/v23/test_v23_q0_round.py:92-124`) cover
  `cc.REGISTRY` only, so calibration drift of this checker (e.g. its fixture going stale) is currently pinned by
  nothing.

### 2.5 Verdict (module 1)

**VERDICT-DETERMINING — accept and refuse directions, by design** (the CI qualification gate and its engine, the
sole F5 classification authority). Under proposed Decision 2 this pair cannot rest on a "non-checker role": it
requires proper checker registration/calibration (the built `_f5_gate` + committed fixture make that the one-line
`REGISTRY += V23_CHECKERS`, which the PIN-57 pins forbid without a re-pin ruling) **or a new exact owner ruling**
that names it a gate/engine retained outside the registry, the way seq-13 ruled `q0_round.py` via
`NOT_CHECKERS_V23`.

---

## 3. Module 2 — `validation/v23/observe.py`: checker `f5_recorder`

### 3.1 Identity

| file | git blob sha1 at HEAD | sha256 of file bytes | one-line purpose (docstring) |
|---|---|---|---|
| `validation/v23/observe.py` | `9c70551f78ed770fb49dab18060df39cf7832b88` | `bb369c299394cdbaffa1b1f9d44bf7c78195721e180cc6d1c56cc43941fe9148` | "F5 recorder (AISEF v2.3 W1a): one observed, unmutated run of ONE kill file, and its observation record O(F)." (`observe.py:1`) |

Checker: `_f5_recorder` (`checker_calibration.py:587-627`), source `observe.py` only.

### 3.2 Callers

* **Library, optional input path only:** `validation/v23/impact.py:114` (`OBS.verify/load/public/FORMAT`), used
  solely when observations are explicitly supplied (`--observations DIR`, `impact.py:1577-1582`; API parameter
  `classify(..., observations=...)`, `:1440`).
* **Library (unregistered checker):** `validation/v2/checker_calibration.py:592` (`_f5_recorder`; dormant — §3.4).
* **Tests:** `tests/v23/test_v23_observe.py:31`, `tests/v23/test_v23_impact.py:35,172` (synthetic witnesses),
  `tests/v23/test_v23_review1.py:28`.
* **CLI:** development tool only (`observe.py:3-4,1073-1101`). **No CI workflow and no gate invokes it** (grep
  over `.github/`, 2026-11-26: zero hits), and **no wired consumer passes observations to the engine**:
  `ci_gate.py:173`, `mutation.py:2855,2868` and `tests/v23/test_v23_rounds.py:199` all call `impact.classify`
  without the parameter.
* **Not consumed by:** `validation/v2/mutation.py` record-keeping or any release gate — stated in its own
  docstring (`observe.py:6-9`) and confirmed by the grep set above; absent from GUARDS/GUARDS_V23,
  `release_qualify.py`, B1 bindings.

### 3.3 Trust boundary — can it determine a qualification verdict?

**Not in any gate as wired.** Its only verdict-capable consumer is `impact.py`'s explicit `--observations` input,
and no gate, guard, workflow, or round-gated test supplies that input today (citations in §3.2). The authority
boundary is additionally pinned in code and by owner ruling:

* Owner ruling 2026-11-21 (quoted at `observe.py:6-9` and `impact.py:30-31,135-137`): approved for development,
  **not** a VERIFIED_REUSE authority.
* A reuse that needed an observation (Δ ≠ ∅) can never carry an acceptance basis: it carries
  `observation:<sha256>@<base>` with `evidence.authority` = the "none: …" sentinel
  (`impact.py:78-80,1198-1200`); `ci_gate.reuse_problems` accepts that form only with the authority sentinel
  intact and the sha pinned to the run's own basis commit (`ci_gate.py:143-145`), and the negative test
  `test_prov1_an_observation_based_reuse_carries_no_acceptance_basis` pins it
  (`tests/v23/test_v23_review1.py:308`).

**Honesty note (the capability exists behind the unwired input):** when observations ARE fed to `impact.py`, the
record influences classification in both directions — refuse (an inadmissible/incomplete record fires R0/R1:
`impact.py:1271-1283`) and accept (a complete observation can clear a target that the no-observation default
would INVALIDATE: `tests/v23/test_v23_observe.py:111`
`test_0_a_complete_observation_reuses_n2`). So the "non-checker" status of this module is a property of the
current wiring plus the authority pins, not of the code's capability. Wiring `--observations` into any gate would
re-open the Decision-2 question for this module.

### 3.4 Negative tests

* `tests/v23/test_v23_observe.py::OwnerNegatives` (`:103-375`) — the nine owner-named failure modes: missing
  child-process tracing, dynamic import, runtime path construction, directory enumeration finding a new test,
  changed environment/platform/toolchain, a mutant branch reading a changed file, changed transitive dependency,
  missing/truncated trace files, tampered provenance, modified kill test or generator.
* `tests/v23/test_v23_observe.py::StraceParser` (`:377`), `::StraceBackend` (`:476`), and
  `::NonPosixRecorder.test_a_recording_here_is_never_admitted` (`:502-506` — a non-POSIX recording is refused).
* `tests/v23/test_v23_review1.py` SND1–SND9 / AUD1–AUD2 / PROV1–PROV4 (`:86-387`) — recorder soundness reds,
  including "a recorder whose in-memory hook differs from observe.py's writes a truthful incompleteness" (`:329`).
* `verify()` negatives (a changed witness file, a record not derived from its witness) are exercised through
  `impact.py` R0/R1 in `tests/v23/test_v23_impact.py` (`test_r0_every_inadmissible_observation`,
  `test_r1_incomplete_observations` — also two of `ci_gate`'s pinned in-process controls, `ci_gate.py:67-68`).
* **Unpinned failure mode:** as with module 1, the `f5_recorder` Checker object and its fixture
  `tests/v2/fixtures/known_bad/f5_recorder.json` are exercised by nothing while unregistered.

### 3.5 Verdict (module 2)

**NON-CHECKER ROLE DEMONSTRATED (evidence recorder / producer), with a stated condition.** It writes observation
records; it judges nothing. No gate consumes it; where the engine can consume its records, they are pinned to
authority "none" and can never become an acceptance basis, and the owner ruling of 2026-11-21 already names it a
non-authority. Under proposed Decision 2 it can be retained outside the registry on this evidence — **provided**
the condition in §3.3 is recorded: the demonstration holds only while no gate passes `--observations`; any such
wiring requires registration/calibration or a new exact owner ruling.

---

## 4. Module 3 — `validation/v23/released_evidence_guard.py`: checker `released_evidence`

### 4.1 Identity

| file | git blob sha1 at HEAD | sha256 of file bytes | one-line purpose (docstring) |
|---|---|---|---|
| `validation/v23/released_evidence_guard.py` | `0468355ef2aa9b2f859858dceb42d3e2912d2ba9` | `d625c17c815a8f1f4268f7d6d4aa986ac489b43c4065f53518ac20860dc9f251` | "Released-V2 evidence guard (CODE-AUDIT #52 (b); COMPATIBILITY-MATRIX CT-6, CR-13)." — tamper detection over every released closure-evidence/v2 record at tag v2.2.0 and the v2.3 branch base, plus the CIGOV-R1 typed append-only rule for the release-decision ledger (`released_evidence_guard.py:1-28`) |

Checker: `_released_evidence` (`checker_calibration.py:630-638`), source this file only.

### 4.2 Callers

* **CI, subprocess, guard:** `.github/workflows/tests.yml:68` — `python -P
  validation/v23/released_evidence_guard.py --check`, a step of the `unit` job on every OS of the matrix, ordered
  after the suite. `tests.yml` runs on every push/PR **and is the release gate**: "release.yml runs this whole
  workflow, on the tagged commit, as a gate before any production publish" (`tests.yml:5-7`, `workflow_call`).
  The guard's own record of this boundary: `released_evidence_guard.py:120` (`"checked_by": "… --check (tests.yml
  unit job, after the suite)"`).
* **Library (unregistered checker):** `validation/v2/checker_calibration.py:634-638` (`_released_evidence`;
  `clean = re_guard.check`, `known_bad = re_guard.ledger_problems`; dormant — §4.4).
* **Tests:** `tests/v23/test_v23_released_evidence_guard.py:31`;
  `tests/v23/test_v23_release_governance.py:41,521-531` (the CI step is pinned present, ordered after the suite
  and the V1 guard, with no `if:` and no `continue-on-error`).
* **Not consumed by:** GUARDS/GUARDS_V23, `mutation.py`, `release_qualify.py`, B1 bindings (grep set, 2026-11-26).

### 4.3 Trust boundary — can it determine a qualification verdict?

**Yes — refuse direction only.** `check()` (`released_evidence_guard.py:175-200`) returns problems;
`main --check` exits 1 on any (`:202-221`); the `unit` job step at `tests.yml:68` then fails the job, which fails
the `tests` workflow, which is `release.yml`'s pre-publish gate. So its output alone flips a push/PR/release
between accepted and refused — in the refuse direction. It is fail-closed in that direction by construction: an
unavailable released revision or branch base is itself a failure (`:179-181,192-196`). It has **no accept
direction**: a green run asserts only "no released record was altered"; it cannot mark any target, record or
release QUALIFIED, grant reuse, or satisfy any acceptance rule — exactly the `q0_round`-in-GUARDS_V23 shape
(§1, precedent), a detective guard whose only verdict power is refusal. Grade stated in-module: DETECTIVE
(`:17-18`).

### 4.4 Negative tests

* `tests/v23/test_v23_released_evidence_guard.py::ThrowawayRepo` (`:43-218`) — a committed edit fails (`:85`), a
  committed deletion fails (`:91`), a baseline edit fails (`:97`), a working-tree change fails with V1 files out
  of scope (`:110`), a missing released revision fails closed (`:119`), the branch-base pin protects post-release
  records (`:124`), CIGOV-R1: append-only ledger growth passes (`:135`) while a rewrite (`:148`), a duplicate-key
  JSON smuggle (`:175`), a staged rewrite behind a clean worktree (`:197`) and deleting/renaming the ledger
  (`:210`) all stay red.
* `::LiveRepository` (`:221-236`) — the committed baseline IS the tag's listing; HEAD keeps every released blob.
* `tests/v23/test_v23_release_governance.py::EvidenceUntouchedBySuite` (`:513-531`) — the CI step exists, cannot
  be skipped or soft-failed.
* **Unpinned failure mode:** as with the other two, the `released_evidence` Checker object and its fixture
  `tests/v2/fixtures/known_bad/released_evidence.json` are exercised by nothing while unregistered (the fixture's
  ledger-rewrite content IS covered functionally by `ThrowawayRepo`'s ledger tests, but no test proves the
  committed fixture still fails `ledger_problems` for the recorded reason).

### 4.5 Verdict (module 3)

**VERDICT-DETERMINING in the refuse direction** (a fail-closed, mandatory CI/release tamper guard; no accept
direction exists). Under the proposed Decision 2's own definition — which counts refuse-direction power — this
module does determine a qualification verdict, so it requires proper checker registration/calibration **or a new
exact owner ruling** naming it a retained guard (the q0_round/`NOT_CHECKERS_V23` route). Its non-checker *role*
(detective guard, not a calibrated qualifier) is real and documented, but under the briefed definition the role
alone does not exempt it.

---

## 5. Closing table

Directions: **A** = can flip toward accepted/QUALIFIED; **R** = can flip toward refused/NOT-QUALIFIED.

| module (checker) | role | verdict-determining? (A / R) | negative tests | disposition under proposed Decision 2 |
|---|---|---|---|---|
| `validation/v23/impact.py` (`f5_gate`, engine) | F5 evidence-state classification authority | **YES — A and R** (VERIFIED_REUSE is the only no-re-measure acceptance path; INVALIDATED/UNRESOLVED fail `mutation --check --states`, the rc tier, and round-gated `f5_problems`) | `test_v23_impact.py::ImpactTest` (N1–N33, D/F/I cases); `test_v23_review1.py`; `test_v23_review2.py` | registration/calibration or a new exact owner ruling — a non-checker role is **not** demonstrated |
| `validation/v23/ci_gate.py` (`f5_gate`, policy) | two-tier CI qualification gate over one engine run | **YES — A and R** (exit contract `ci_gate.py:44-45`; rc tier refuses a tag; green rc is the job's acceptance; exit-2 conditions refuse either tier) | `test_v23_ci_gate.py::Gate`; `test_v23_release_governance.py::IncrementalQualificationJob`; 4 pinned in-process controls per run | same as above |
| `validation/v23/observe.py` (`f5_recorder`) | observation recorder — evidence producer, no judgement | **NO in any wired gate** (no caller passes observations; authority pinned "none", never an acceptance basis). Capability behind the unwired `--observations` input: A and R via `impact.py` | `test_v23_observe.py::OwnerNegatives/StraceParser/StraceBackend/NonPosixRecorder`; `test_v23_review1.py` SND/AUD/PROV | retain outside the registry — non-checker role demonstrated, **conditional on** no gate ever wiring `--observations` without a new ruling |
| `validation/v23/released_evidence_guard.py` (`released_evidence`) | detective tamper guard over released v2 records + CIGOV-R1 ledger rule | **YES — R only** (mandatory `tests.yml:68` step; fails the release gate; no accept direction exists) | `test_v23_released_evidence_guard.py::ThrowawayRepo/LiveRepository`; `test_v23_release_governance.py::EvidenceUntouchedBySuite` | registration/calibration or a new exact owner ruling naming it a retained guard (the `q0_round`/`NOT_CHECKERS_V23` precedent) |

**Cross-cutting facts the ruling should see** (all measured 2026-11-26):
1. Live calibration on HEAD is **54/57**, not 56/57 — `b1_bindings`, `currency_dag`, `mutation` are clean-tree
   red (known waits: OD-B1B, P5-PROPOSAL currency, F5 cut-over). "56 of 57" is only the synthetic pinned string
   at `tests/v23/test_v23_q0_round.py:223`.
2. `q0_round.v23_scope_problems` names all four module files red today (Q0P-2), so *both* branches of Decision 2
   leave round v2.3 Q0 red without a new ruling: registering trips PIN-57; retaining trips Q0P-2's closed list
   (and the seq-13 R6 draft's NOT_AUTHORIZED clause, `LEDGER-SEQ-13-DRAFT-R6.md:38`).
3. The three Checker objects and their committed known-bad fixtures are exercised by **no test** while
   unregistered — the Q0 anti-gaming sweeps cover `cc.REGISTRY` only. If the ruling retains them outside the
   registry, pinning their calibration (or ruling the fixtures dormant) is an open gap.

*This file is evidence assembly for a decision the owner has not made. No implied approval is granted or taken.*
