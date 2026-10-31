# V2.1 — single release-blocker table (living)

---

## Final disposition — owner directive 2026-10-31 (RELEASE-DECISIONS seq 6)

The owner issued the scoped release decision (`closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` seq 6).
It resolves every Group A item below. **The table underneath is kept verbatim as the pre-decision record;
this header is the authoritative current state.** RC source `dc63478c` (`release/v2.1.0`); product tree
`5f34a3f3` = fce3d7b7, **unchanged** (no product code was touched to close any item).

| item | pre-decision | final disposition (seq 6) |
|---|---|---|
| **A-01** `cli.py::_parser` | open pending A-03 | **CLOSED** — 31/31 killed at head; sound under the A-03 **documented limitation** (option 2). No product change. |
| **A-02** `bundle_cli.py::_create` | open pending A-03 | **CLOSED** — 3/3 killed, `continue_integrity` T0 PASS this run; sound under the A-03 documented limitation. No product change. |
| **A-03** `continue_integrity` | owner-decision item (1/2/3) | **DECIDED — OPTION 2 (documented supported-envelope limitation).** Integrity under external SIGKILL in the request-sent/result-not-journaled window is outside the V2.1 supported envelope; **not** claimed fixed or verified. `V2.1-KNOWN-LIMITATIONS.json` → `A-03-CONTINUE-INTEGRITY-ENVELOPE`. |
| **A-04** release gate + suite, all platforms | gates run on macOS only | **CROSS-PLATFORM CI RUN** on the RC source `dc63478c` (tests run 41220620754: ubuntu 3.11–3.14, macOS 3.12, windows 3.11; staging run 41220620258: build + clean-install smoke Linux+Windows). True verdicts recorded in `V2.1.0-STATUS.json`; classified below. |
| **7 unaudited survivors** (mutation FAIL) | owner-decision item | **OWNER-ACCEPTED scoped residual risks** (seq 6). Identities + effects re-verified against the source at 8c7bdb44. **NOT** labelled KILLED, no fabricated audit evidence, no history modified; the machine mutation-gate verdict is **preserved FAIL (7 unaudited)**. `SURVIVOR-CLASSIFICATION.md`. |
| **ruff F541** | 1-line helper fix pending | **FIXED** (`verify_coverage_614.py:90`); `ruff check .` PASS (CI lint job PASS). |
| version / RC / decision | owner action | **version 2.1.0**; **RC1 frozen** (`V2.1.0-RC1-FREEZE.json`); seq 6 recorded. `PRODUCTION_PUBLISH NOT_AUTHORIZED`. |

### Confirmed release-blocking product defects: **NONE.**

### Unit-suite CI verdict (tests run 41220620754, RC source `dc63478c`): **FAIL — 0 confirmed product defects.** Every failure classified by measurement (owner §5):
- **3 release-process failures — RESOLVED.** The version bump `2.1.0.dev0`→`2.1.0` changed the probe-calibration
  record filename the release-mode qualifier reads (`V{version}-PROBE-CALIBRATIONS.json`). Only `.dev0`-named
  records existed → `test_qualification_release_mode::…q2_reads_the_calibrations…` (error) and
  `test_c2_p5_acceptance::V21Records` ×2 failed with `FileNotFoundError`. **Resolved** by regenerating the
  version-named record with `validation/qualification/release_calibration.py --write` (a deterministic
  re-derivation on the frozen tree — no provider, no campaign; rows/fixtures **identical** to the `.dev0-4`
  record, only the `aisef2_tree` pointer advances to the frozen `5f34a3f3`). The shipped `aisef2/app/calibrations.py`
  was left at its frozen bytes (reverted the tool's fresh `demonstrated_at` timestamps). All 3 tests PASS locally
  after the fix; `closure-evidence/v2/release/V2.1.0-PROBE-CALIBRATIONS.json` added (closure-evidence, **not** shipped).
- **~17 record-currency / tree-binding meta-tests** (`test_checker_calibration` ×4, `test_destructive_authority`,
  `test_freeze_manifest`, `test_invariants` ×2, `test_c2_delivery_experiment::PlanCorrection`,
  `test_c2_k_nowork_001`, `test_c2_orchestration_conformance` ×2, `test_c2_p5_acceptance::Acceptance`/`KernelProvenance`,
  `test_p5_plan_v22_proposal`, `test_p9_reproduction`, `test_v21_conformance_ruling`): each asserts "the committed
  record re-derives / binds **this** tree." RED-by-design on an intentionally-unsealed branch; green only by
  sealing/re-deriving the records = **forbidden scope expansion**. This is the exact baseline set the owner
  reviewed at 8c7bdb44 (GO-NO-GO §2.1); the kernel is frozen, so none is new. Includes `client.py:45`
  `os.kill(pid, 0)` — a **signal-0 existence probe that never signals a process** (verified in source); the
  `destructive_authority`/`INV-MUTATION-AUTHORITY` failure is the textual ledger wanting the site recorded, a
  **ledger-currency** issue, **not** an unguarded kill. FAIL preserved, not a blocker (owner §4: historical-record
  currency is not a delay reason).
- **~3 environment / fixture artifacts — measured to pass in a clean environment** (owner §5): `test_v21_read_set`
  ×2 (macOS `/var`→`/private/var` symlink TMPDIR; **PASS** with a non-symlinked TMPDIR — 29/29),
  `test_v21_mutation_runner::test_one_release_budget_per_run` (CI-host process-reaping/ownership-proof semantics;
  **PASS** locally), and `test_c2_delivery_experiment::HistoricalAttempt4` (reads the live `~/.local/share/opencode/opencode.db`).
  Not product defects.

**Net:** the suite FAIL is real and reported honestly; it contains **0 confirmed product defects**. No verdict was
converted to PASS; the mutation gate and v2-release gate keep their true FAIL.

---

Candidate frozen at **8c7bdb44** (product tree `5f34a3f3` = fce3d7b7). One consolidated table (owner
directive 2026-10-29 step 3; version-closing rules 2026-10-30). Each item: what the user hits · evidence ·
impact · scope · remediation · close condition. **Group A items are never self-moved to backlog;
undetermined cause ≠ low risk.** Goal of this pass: a **candidate set for the owner's release decision**,
not a survivor-free suite. Conclusion language is scoped: "no original-code defect confirmed within the
tested scope," never "the product is correct"; UNDET / open-light-check items stay provisional. Current
failing gates stay public; an exception is in force only with the owner's explicit approval.
Updated while the campaign runs. **Current through: 3 finished targets + the standing blockers.**
Survivor classes carry exactly one label (EQUIV · OOR/AUDITED · TEST-GAP · UNDET); the merged "EQUIV/OOR"
tag is retired — see `SURVIVOR-CLASSIFICATION.md`.

Groups: **A** = bug or missing mandatory evidence, must be handled before release · **B** = limitation
presentable to the owner for scoped acceptance · **C** = improvement for a later version.

---

## Group A — must handle before release

### A-01  `aisef2/app/cli.py::_parser` — no sound mutation evidence at head
- **User hits:** a CLI argument-parsing defect could ship undetected (the shipped parser has no sound kill-coverage measurement).
- **Evidence:** MISSING at fce3d7b7; outside the mw0/mw1 resume slice; historical symptom "no-summary" (kill run produced no clean KILLED/SURVIVED). `OLD-BLOCKERS-RECONCILIATION.md`.
- **Impact / scope:** one target, `cli.py::_parser`. **Measured at head this campaign (2026-10-31): 31/31 killed, 0 survivors, 0 INFRA/NOT_RUN** — the measurement half is now satisfied.
- **Remediation:** done (head measurement complete); only the A-03 soundness dependency remains.
- **Close:** ~~soundly measured at 8c7bdb44~~ ✅ **done (31/31 killed)** **AND** A-03 resolved — still open, because its kill set includes `test_v21_continue_integrity.py`, so the clean number is only *sound* once that T0 is sound. A-01 therefore stays in Group A pending the owner's A-03 decision, not pending more measurement.

### A-02  `aisef2/app/bundle_cli.py::_create` — no sound mutation evidence at head
- **User hits:** a bundle-creation defect could ship undetected.
- **Evidence:** MISSING at fce3d7b7; four historical results all fail reuse-proof; most benign blocked by `KILLTESTS`. The one symptom: a single T0 FAIL of `test_v21_continue_integrity.py` on a clean tree (PASS 27 / FAIL 1) — recorded exactly as **"T0 failure observed, not reproduced"** (the earlier "flaky" label was retracted). `OLD-BLOCKERS-RECONCILIATION.md`.
- **Impact / scope:** one target, `bundle_cli.py::_create`. **Measured at head this campaign (2026-10-31): 3/3 killed, 0 survivors, 0 INFRA/NOT_RUN, and all 5 T0 kill-tests PASSED — including `test_v21_continue_integrity.py` (PASS, exit 0, 212.87s)**, so the earlier observed T0 FAIL did not reproduce this run. The measurement half is now satisfied.
- **Remediation:** done (head measurement complete); only the A-03 soundness dependency remains.
- **Close:** ~~soundly measured at 8c7bdb44~~ ✅ **done (3/3 killed; continue_integrity T0 PASS this run)** **AND** A-03 resolved — still open. A clean T0 this run is evidence of a clean environment, **not** closure of the async-SIGKILL window (owner A-03 framing). A-02 stays in Group A pending the owner's A-03 decision, not pending more measurement.

### A-03  Finding `continue_integrity` — suspected lost-S2 product race, unreproduced (owner-decision item)
Scoped per owner 2026-10-30 (step 4): neither an infinite bug-hunt nor "closed because many runs PASSed."
State the four facts, then the owner picks one option. **No option is auto-approved.**
- **Observed phenomenon:** a single T0 FAIL of `test_v21_continue_integrity.py` on a clean tree — **observed, not reproduced** (not consistently reproducible on re-run). **Scope by target (evidence-based, not a blanket invalidation):** the T0 FAIL was observed **only for `bundle_cli.py::_create`** (`OLD-BLOCKERS-RECONCILIATION.md`). `cli.py::_parser`, `run.py::execute`, and the rest of the ~97 only **share** `test_v21_continue_integrity.py` in their kill sets — none has an observed T0 FAIL. `execute` measured cleanly this campaign (356/366, 0 INFRA/NOT_RUN ⇒ its control baseline, continue_integrity included, passed). So the ~97 results are **not** treated as invalidated; each carries a soundness *dependency* on this finding, nothing more, and `_create` is the one with an actual reproduced T0 symptom.
- **Unknowns:** whether any real product defect exists. Round-1 controlled fault injection (2026-10-25, `inv-ci`) ruled out the in-process `provider/request` journal boundary (before/short/after-write, after-fsync all contract-correct, 0 violations). The **external async-SIGKILL "request sent, result/usage not yet journaled"** window was **not reproduced** and is not ruled out. A clean campaign (0 TIMEOUT/INFRA) does **not** close it.
- **Affected feature:** story-completion integrity + cost accounting under abrupt external SIGKILL; as a T0 kill-test it gates the *soundness* of the A-01 / A-02 head numbers and of every target whose kill set includes it (~97 re-measure targets — a shared *dependency*, per the per-target scope above; only `_create` shows a reproduced T0 symptom). A clean campaign (0 TIMEOUT/INFRA) is evidence of a clean measurement environment, not of the race's absence.
- **Options for the owner (choose one; none applied without explicit approval):**
  1. **Fix** — one controlled fault-injection of the external async-SIGKILL window (reproduce → fix → repro test), batched into the single final fix window (step 5), **only if** a real defect is reproduced.
  2. **Limit support scope** — ship 2.1 with a documented limitation that integrity under external SIGKILL mid-call is out of the supported envelope; targets gated on it carry that scope tag.
  3. **Accept as scoped exception** — owner records the exception; the ~97 head numbers are accepted as sound under that exception.
- **Close:** owner selects 1, 2, or 3. Until then A-03 stays **open in Group A** (undetermined cause ≠ low risk; not self-moved).

### A-04  Release gate + suite at the candidate head, all platforms — not yet established
- **User hits:** the shipped artifact may not pass the release gate on macOS / Linux / Windows.
- **Evidence:** preflight ran on macOS only; `v2-gate` has **not** been run at 8c7bdb44; no Linux/Windows gate/suite at this head. The full unit suite is **RED by design** (19 record-currency/tree-binding meta-tests on the unsealed branch; green only by resealing = forbidden). `PREFLIGHT-SNAPSHOT.md`.
- **Impact / scope:** platform/release condition for the whole candidate.
- **Remediation:** at the step-4 handoff, run `v2-gate` + unit suite at 8c7bdb44 on macOS and Linux (Windows per release policy); record the true verdict — **a public FAIL/blocker is an acceptable handoff outcome**, not something to fix-to-green first.
- **RAN 2026-10-31 at 8c7bdb44 (macOS, py3.14), true verdicts recorded** — details in [GO-NO-GO.md](GO-NO-GO.md) §2/§2.1:
  - **ruff** `ruff check .` → **FAIL** (1 × F541 in `closure-evidence/v2/v2.1/tools/verify_coverage_614.py:90`, a helper not product; 1-line fix).
  - **v2-gate** `v2_release_gate.py 2.1.0.dev0` → **FAIL** (no frozen 2.1 RC; `2.1.0.dev0` not a stable X.Y.Z; no 2.1 STATUS; RELEASE-DECISIONS authorizes 2.0.0). I.e. a 2.1 release is **not prepared/authorized** — owner's call.
  - **unit suite** `unittest discover -s tests` → **FAIL** (7978 run, **19 failures**, 89 skipped). Enumerated + classified: **17 record-currency/tree-binding meta-tests** (RED-by-design on the unsealed tree, green only by sealing = forbidden) + **1 environment-specific** (live `opencode.db` has a session after the historical c2 attempt-4) + **1 macOS-TMPDIR fixture artifact** (`read_set.Merge`: FAILs under `/var`-symlinked TMPDIR, **PASSES on a non-symlinked TMPDIR — measured**). **0 confirmed product defects.** `v1_evidence_guard --check` PASS.
  - **Linux / Windows**: NOT RUN — CI only, which needs a push (out of scope under the no-push limit). A documented coverage gap, not a pass.
- **Close:** ✅ gates run at the committed head with true verdicts recorded and the meta-test / env / fixture failures correctly attributed (not resealed). The remaining release-readiness items (RC freeze, stable version, RELEASE-DECISIONS entry, all-platform CI) are owner actions, tracked in GO-NO-GO §4–§5.

---

## Group B — limitations presentable to the owner for scoped acceptance

*(None open. B-01 below was resolved by bounded analysis to EQUIV, not a limitation — kept as a record.)*

### B-01  Candidate-side PRESERVE re-proof role (V21-38) — RESOLVED to EQUIV (was a suspected gap)
- **Resolution (owner step 3, 2026-10-30):** survivors **S-01/S-02** (`ObligationRole.PRESERVE`→`INTRODUCE`/`VERIFY` at `story_runner.py::_attempt` L271) are **proven decision- and evidence-neutral** at the candidate consumption path — every CANDIDATE routing row is keyed role=`None` ([routing.py:81-86](aisef2/control/routing.py:81)), role reaches only `route()` ([proof.py:107](aisef2/orchestrate/proof.py:107)) and is neither journaled (`verified_payload`) nor stored on `Proof`. A developer regression is still caught role-independently (`contract_satisfaction`→CONTRACT_UNSATISFIED/DEVELOPER). `SURVIVOR-CLASSIFICATION.md`.
- **Therefore:** there is **no current limitation** requiring owner acceptance — nothing a developer can change on that role introduces a regression the suite would miss, because the role has no behavioural effect at the candidate. Not relabelled to clear a count (owner rule 1): shown to change no decision and no evidence.
- **Residual → C:** equivalence is contingent on the current role-agnostic CANDIDATE routing. Hardening item (C-03) pins it; not a blocker.

---

## Group C — improvements for a later version (NOT in this candidate)

- **C-01 Measurement-system backlog (step 6):** per-mutant checkpoint; atomic record write; save artifact on error; deterministic sync test; split heavy tests from small behaviour checks. Each validated separately, never deployed into a running campaign.
- **C-02 Low-stakes evidence hardening (optional tests, not blockers):** the **OOR/AUDITED** survivors are
  differences out of mandatory requirement, each with grounds — optional determinism/robustness tests, never
  release gates: `reasoning` token-dict key (S-07/S-08), refusal-message text (S-14..S-17), run-label and
  coverage-message text (S-11/S-12/S-13), `_EscapedRange` journal label (S-03/S-04), STARTED/MANIFEST
  trailing-newline and canonical key-order (S-19..S-22), and the `rec["stage"]` breadcrumb value/presence on
  the early-error path (S-18/S-23). **Still open & public (NOT closed — carried to handoff):** session-evidence
  list-ordering determinism (S-05/S-06, **TEST-GAP** — not proven out-of-requirement, so not relabelled OOR),
  missing-parent `mkdir(parents=…)` robustness (S-09, **TEST-GAP**), and `_ocr` L265 bool (S-10, **UNDET**).
  Test-only; later.
- **C-03 Pin CANDIDATE routing role-agnosticism (from S-01/S-02):** add a test asserting that at `MeasurementPoint.CANDIDATE` the obligation role does not change the route, so the candidate re-proof's role argument is covered and a future role-keyed CANDIDATE row cannot silently change behaviour unnoticed. Optionally drop or document the unused role on `story_runner.py::_attempt` L271. Test/doc-only; later.

---

## Reconciliation note
- 62 MISSING at fce3d7b7 (46 tests + 16 product; `MISSING-62-RECONCILIATION.json`) are being measured by
  the 90-target campaign; their MISSING status retires **only** as sound head measurements land, and only
  where not gated by A-03.
- Campaign progress (**9 of 90 targets finished**, 2 running, 79 pending; KILLED 1938 / SURVIVED 53; 0
  TIMEOUT/INFRA). The full ledger of all 9 finished targets and 51 survivors, assessed by **consequence ×
  evidence** (not by label — owner 2026-10-30), is in `HANDOFF-INTERIM.md`; `SURVIVOR-CLASSIFICATION.md`
  details targets 1–3. The high-consequence areas among the 9 (verdict/`verify`, confinement/`cli`,
  secrets+scope/`client.session`) were checked against what the code consumes and found evidence-bounded to no
  verdict/enforcement change; some diagnostic/probe survivors stay open on LIGHT evidence. Targets whose kill
  set includes `test_v21_continue_integrity.py` are **A-03-gated for soundness**.
- **Risk is not read off the BUG/TEST-GAP label.** "No BUG-class survivor so far" is a fact, not a safety
  verdict; it does not make a survivor non-blocking. Blocking is decided at go/no-go on the concrete result
  set, by consequence × evidence, with the owner.
- Nothing here is closed by a green campaign run alone. Group A stays A until its stated close condition
  is met or the owner decides otherwise.
