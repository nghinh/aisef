# V2.1 — consolidated go/no-go for the owner

---

## FINAL DECISION — owner directive 2026-10-31 (RELEASE-DECISIONS seq 6)

**Verdict: RELEASE PREPARED AND VALIDATED · PRODUCTION PUBLICATION ON HOLD (owner-scoped, not defect-driven).**

The owner issued the scoped decision "CLOSE V2.1 AND COMPLETE RELEASE HANDOVER" (seq 6), superseding the
no-acceptance posture of the pre-decision analysis below. Executed exactly as authorized, nothing beyond:

- **A-03** → **option 2**, documented supported-envelope limitation (not claimed fixed/verified).
- **7 unaudited survivors** → **owner-accepted scoped residual risks**; identities + effects re-verified against
  the frozen source; **not** labelled KILLED, no fabricated audit, no history modified; mutation gate **preserved FAIL**.
- **ruff F541** → fixed (1-line helper). **version** → `2.1.0`. **RC1** → frozen (`V2.1.0-RC1-FREEZE.json`).
- **Release-branch push** (authorized for CI only) → done; cross-platform CI + staging run.

**True gate verdicts (preserved — nothing reworded to PASS):**

| gate | verdict | note |
|---|---|---|
| ruff `ruff check .` | **PASS** | F541 fixed; CI lint job PASS |
| staging build + clean-install smoke (Linux + Windows) | **PASS** | staging run 41220620258 |
| `release_rc.py --check` (shipped trees == frozen RC) | **PASS** | wheel `80310413…`, sdist `5039c602…` |
| **mutation record** | **FAIL (7 unaudited)** | **ACCEPTED EXCEPTION** (seq 6); verdict preserved, not a blocker |
| **v2 release gate** `v2_release_gate.py 2.1.0` | **FAIL by design** | publish withheld (`PRODUCTION_PUBLISH NOT_AUTHORIZED`) — the correct state, not a defect |
| **unit suite** (cross-platform CI 41220620754) | **FAIL — 0 confirmed product defects** | 3 version-bump failures resolved; rest = record-currency (forbidden to seal) + env artifacts (pass in clean env). Breakdown: `RELEASE-BLOCKER-TABLE.md` final-disposition header |

**Confirmed release-blocking product defects: NONE.**

**Why HOLD and not GO:** production publication is **deliberately withheld by the owner** (seq 6), not blocked by
any defect. Publishing (`v2.1.0` tag → `release.yml`, the `pypi` environment approval, the upload) requires a
**separate explicit owner authorization**. Everything preparable without that authorization is done: version,
frozen RC, decisions, cross-platform validation, and the handover package. 2.0.0 remains the live PyPI release.

Deliverables: this file · `RELEASE-BLOCKER-TABLE.md` · `SURVIVOR-CLASSIFICATION.md` · `V2.1-KNOWN-LIMITATIONS.json`
· `V2.1-EXECUTIVE-HANDOVER.md` · `closure-evidence/v2/release/{V2.1.0-STATUS.json, V2.1.0-RC1-FREEZE.json, V2.1.0-PROBE-CALIBRATIONS.json}`
· `V2.1-OPERATIONS.md` · `RELEASE-DECISIONS.json` seq 6 · `CHANGELOG.md` 2.1.0.

The pre-decision analysis below is retained verbatim as the record the owner reviewed at 8c7bdb44.

---

**Status: COMPLETE.** This is the single decision artifact the
owner asked for (2026-10-30, decision point 5): the concrete final result set, the true gate verdicts, the items
that actually block a 2.1 release, the minimal fix + re-measure scope + cost for each, and the
release-or-narrow-scope choice. **It records no acceptance.** All standing limits hold: no push / tag / publish /
paid provider / `APPROVE.sh` / self-acceptance / reseal; the candidate `aisef2/` tree is frozen at 8c7bdb44
(`5f34a3f3` = `fce3d7b7`). Nothing here audits a survivor or authorizes a release; those are the owner's calls.

Prepared 2026-10-31 ~17:10 +07, after the supplementary mutation campaign completed.

---

## 1. The final result set (measurement — complete and honest)

- **Coverage: 614 / 614 targets, 0 MISSING.** 90 measured-at-head this campaign + 524 reused after mechanical
  proof (162 measured + 362 reused) = 614; RERUN_TARGETS 0. The 62-target MISSING gap that opened V2.1 is closed
  **by measurement**, not by acceptance (`MUTATION-SUMMARY.json`, FINAL_HEAD `8c7bdb44`, criteria hashes frozen
  and unchanged).
- **Campaign: 90 targets, 3593 mutants, KILLED 3500 / SURVIVED 93, kill rate 97.41%, 0 infra / timeout /
  not-run.** 62 of the 90 targets fully killed. Reconciled: every queue line has a result and a `done` marker;
  both workers finished cleanly (process teardown `released_empty=True`).
- **Both prior Group-A measurement blockers are now measured clean at head, 0 survivors:**
  - **A-01 `cli.py::_parser` — 31/31 killed.**
  - **A-02 `bundle_cli.py::_create` — 3/3 killed**, and **all 5 of its T0 kill-tests PASSED this run, including
    `test_v21_continue_integrity.py` (PASS, 212.87 s)** — the earlier observed T0 FAIL did not reproduce.
  - Both remain **A-03-gated for soundness** (a clean run is a clean environment, not closure of the
    external-SIGKILL window — owner's A-03 framing).
- **93 survivors, all triaged by consequence × evidence** (`HANDOFF-INTERIM.md` §4, `SURVIVOR-CLASSIFICATION.md`):
  **none is a CONFIRMED defect of a verdict, an obligation, data, a secret, an access boundary, or evidence
  integrity.** The delivery-verdict function `run.py::delivery` is fully killed (0 survivors), independently
  corroborating the verdict-path coverage. Open items are low-consequence and kept public (§4 below).

## 2. True gate verdicts at 8c7bdb44 (nothing fixed to green)

| gate | verdict | cause (listed, not fixed) |
|---|---|---|
| **mutation record** (`v21_mutation_record --write`) | **FAIL** | 7 **unaudited** survivors in 2 targets — `client.session` ×3, `story_runner._attempt` ×4. The other 86 survivors match the frozen `AUDITED` set from prior cycles. |
| **ruff** (`ruff check .`, 0.16.4) | **FAIL** | 1 error, **F541** (f-string without placeholders) at `closure-evidence/v2/v2.1/tools/verify_coverage_614.py:90` — a **helper script, not product** `aisef2/`. 1-line fix. |
| **v2 release gate** (`v2_release_gate.py 2.1.0.dev0`) | **FAIL** | No frozen 2.1 RC (charter G2); `2.1.0.dev0` is not a stable X.Y.Z; no `V2.1.0.dev0-STATUS.json`; `RELEASE-DECISIONS` seq 3 authorizes **2.0.0**, not 2.1. I.e. **a 2.1 release is simply not prepared or authorized** — owner's call, not a product defect. |
| **unit suite** (`unittest discover -s tests`, macOS, py3.14) | **FAIL (19 failures / 7978 run / 89 skipped, ~77 min, rc=1)** | breakdown in §2.1 — **0 confirmed product defects**: 17 record-currency/tree-binding meta-tests (RED-by-design, green only by sealing = forbidden) + 1 environment-specific + 1 macOS-TMPDIR test artifact. Clean process teardown (`released_empty=True`); `v1_evidence_guard --check` **PASS** (V1 evidence not touched). |
| **unit suite — Linux / Windows** | **NOT RUN** | these run only in CI, which requires a push — **out of scope under the no-push limit**. A documented gap, **not** a pass. |

### 2.1 Suite failure breakdown (all 19 enumerated and classified — measured, not assumed)
- **17 record-currency / tree-binding / provenance meta-tests** (`test_checker_calibration` ×4, `test_destructive_authority`,
  `test_freeze_manifest`, `test_invariants` ×2, `test_c2_delivery_experiment::PlanCorrection`, `test_c2_k_nowork_001`,
  `test_c2_orchestration_conformance` ×2, `test_c2_p5_acceptance` ×2, `test_p5_plan_v22_proposal`, `test_p9_reproduction`,
  `test_v21_conformance_ruling`): each asserts "the committed record re-derives on / binds this tree." They FAIL because the
  working tree is unsealed and `MUTATION.json` was just regenerated — **green only by committing/sealing, which is forbidden**.
  Expected RED-by-design.
- **1 environment-specific** (`test_c2_delivery_experiment::HistoricalAttempt4::…external_copies…`): asserts the c2 experiment's
  external store has no session after attempt 4, but the **user's live `~/.local/share/opencode/opencode.db` has a session created
  since** — the test reads the real machine DB. Test-fixture staleness, **not a product defect**.
- **1 macOS-TMPDIR test artifact** (`test_v21_read_set::Merge::test_paths_are_made_relative…`): **measured** — with the default
  macOS TMPDIR (`/var/folders`, where `/var`→`/private/var` is a symlink) it FAILS; with a non-symlinked TMPDIR it **PASSES (OK)**.
  The read_set path-merge logic is correct; the test fixture is macOS-`/var`-fragile. **Not a product defect**, and unrelated to the
  campaign's reuse proof (which uses git-blob SHAs, not this path-merge).

**Net: the suite surfaces no confirmed defect in the frozen candidate at 8c7bdb44.** The FAIL is real and reported honestly, but
every one of the 19 is a meta-test on an (intentionally) unsealed tree or an environment/fixture artifact.

## 3. What actually blocks a 2.1 release (consequence × evidence, not the label)

**No CONFIRMED product defect blocks release.** The RED gates above decompose into:

1. **Release not prepared/authorized (v2-gate).** Expected and entirely the owner's to resolve: there is no 2.1 RC
   freeze, no stable version bump, no RELEASE-DECISIONS entry for 2.1. This is the top-level "is 2.1 a go?"
   decision, not a defect.
2. **7 unaudited survivors (mutation FAIL).** All 7 were read against their consumers and bound to no
   verdict/enforcement change: `client.session` ×3 are **report-field** mutations (redaction via `redact()` and
   scope-disposal via `_release_session()` run unconditionally — enforcement intact; only the result's report of
   them changes); `_attempt` S-01/S-02 (`PRESERVE→INTRODUCE/VERIFY`) are **decision- and evidence-neutral at
   `MeasurementPoint.CANDIDATE`** (role is role-agnostic there, not journaled, not on `Proof`), and S-03/S-04
   (`L249 'developer '/' range'`) are journal **label text**. **They are not audited here** — the owner decides
   whether to formally audit them (the analysis is in `SURVIVOR-CLASSIFICATION.md`) or to leave the gate RED.
3. **1 lint error (ruff).** Trivial F541 in a coverage **helper**, not the product. 1-line fix.
4. **A-03 `continue_integrity`** — the real open question (below), gating the *soundness* of A-01/A-02 and of
   every target whose kill set includes that T0.

**The macOS unit suite adds no blocking item:** all 19 failures are record-currency meta-tests on the unsealed
tree or environment/fixture artifacts (§2.1), and the V1-evidence guard passed. The one gap it leaves is coverage
— the Linux/Windows suite has not run at this head (CI, push-gated).

## 4. Owner decision items

1. **A-03 `continue_integrity` (the one substantive call).** Observed-not-reproduced external-SIGKILL
   "request-sent, result/usage-not-yet-journaled" window. A clean campaign (0 TIMEOUT/INFRA, `_create` T0 PASS
   this run) is evidence of a clean environment, **not** closure of the window. Choose one (none applied without
   your explicit approval): **(1) fix** — one controlled fault-injection of that window, reproduce → fix → repro
   test, batched into a single final fix-window, only if a real defect reproduces; **(2) limit scope** — ship 2.1
   with a documented limitation that integrity under external SIGKILL mid-call is out of the supported envelope;
   **(3) accept as a scoped exception** — you record the exception and the A-01/A-02 head numbers are accepted as
   sound under it.
2. **The 7 unaudited survivors.** Audit/accept them on the recorded consequence×evidence analysis, or leave the
   mutation gate RED and ship with them listed as open. (I will not audit them for you.)
3. **ruff F541.** Approve the 1-line fix in the helper, or leave it listed.
4. **Release authorization for 2.1** — only you can create the RC freeze, the stable version, and the
   RELEASE-DECISIONS entry. Until then v2-gate stays FAIL by definition.

## 5. Unified fix plan (only if you choose to release 2.1; one batched window)

If the decision is "prepare a 2.1 release," the **minimal** set is:

| item | minimal fix | re-measure scope | cost |
|---|---|---|---|
| A-03 (if option 1) | one controlled external-SIGKILL fault-injection; fix only if it reproduces | if a product fix lands: re-measure only the targets whose kill set includes `test_v21_continue_integrity.py` (~the A-03-gated set), not the whole 90 | the fault-injection harness (hours); re-measure of the gated subset only |
| 7 unaudited survivors | owner audit decision (no code) — or, if any is to be covered, add the one targeted test | none for an audit decision; if a test is added, re-measure only that target | minutes (audit) / one target (test) |
| ruff F541 | remove the `f` prefix at `verify_coverage_614.py:90` | none (helper, not measured) | 1 line |
| version + RC + release decision | bump `2.1.0.dev0`→`2.1.0`, freeze the RC, add the RELEASE-DECISIONS entry | none | owner action |
| Linux/Windows gate+suite | run in CI on the release branch | none | one CI run (requires a push — your authorization) |

**No "fix-each-survivor-then-rerun-the-giants."** Re-measure only genuinely-affected targets, once, after any
product change. No loosening of the proof/oracle/timeout; the candidate tree stays frozen until a fix window is
explicitly opened.

## 6. Release-or-narrow-scope

- **Release 2.1 now:** not available as an unconditional go — v2-gate is FAIL (no RC/version/decision) and the
  mutation + ruff gates are RED. A release requires at least items 4 (A-03), 3, and the version/RC/decision in §5,
  plus the CI gate on all platforms.
- **Narrow scope (recommended framing, your call):** ship 2.1 with A-03 as a documented supported-envelope
  limitation (option 2), the 7 survivors audited or listed, the 1-line ruff fix, and a CI gate run — i.e. a
  release whose open items are stated, not hidden. This is a decision for you on this concrete set, not something
  I can take.
- **Hold:** keep 2.1 unreleased; the measurement gap is closed and the evidence stands regardless.

---

**Footer.** No survivor is audited or accepted here; no release is authorized here; A-03 is not resolved here. The
candidate is frozen at 8c7bdb44. Gate RED states are reported as causes, never substituted by a release note. All
no-push / tag / publish / paid-provider / APPROVE.sh / reseal limits hold.
