# AISEF v2.3 — B2 GROUND-TRUTH PROTOCOL (DRAFT for the freeze review)

**Status:** DRAFT (owner directive 2026-11-25 §5: "Draft and freeze the B2 ground-truth protocol before
evaluations begin" — lane L6-EVAL, started as the W6 prerequisite; plan milestone "B2 protocol freeze"
week 29/12–04/01). Once frozen, a change to this protocol is an appended, dated amendment at the end of this
file, never an edit (same rule as `W1-DESIGN.md`). Normative words (MUST / MUST NOT / SHOULD) are binding on
the L6-EVAL lane and on every B2 record. Every open point carries a default (§6); the lane builds on the
default until the owner rules otherwise.

**What B2 replaces:** today `false_acceptance = claimed ∩ not_satisfied` is computed by the same probes that
produced the claim (`validation/qualification/release_acceptance.py:140`) — structurally self-referential
(IMPROVEMENT-ROADMAP §B2; MASTER-CHECKLIST row B2: "no frozen ground-truth corpus; false_acceptance still
self-referential"). B2 measures the real false-accept / false-reject of the kernel's `delivery()`
(`aisef2/app/run.py:374-390`) against labels that the kernel never saw and could not have produced.

---

## 1. Measured facts and frozen constraints that fix this design

| # | Fact / constraint | Evidence |
|---|---|---|
| B-M1 | `delivery()` returns `PASS` only when every plan story's last outcome is its commit, the budget stopped nothing and no story was refused; `FAIL` when blocked; `NOT_REACHED` when no story reached its gate. Its claim scope is exactly the approved bundle's obligations (story × criterion). | `aisef2/app/run.py:374-390`; `productproof()` `:355-371` |
| B-M2 | The charter claim is: frozen oracle corpus + **≥3 representative repos** + **≥2 external evaluators**, false-accept/false-reject **by contract scope separately** (in-scope/out-of-scope truth not conflated), real or clearly-estimated wallclock/tokens/USD. | `RELEASE-CHARTER.md` §1.8 (:28-29), §3 (:56-57) |
| B-M3 | DAG hard edges: `B2-ORACLE-SIGNED -> B2-MEASURE [G]` (freeze + sign labels before measuring); `CODE-FREEZE -> B2-MEASURE [S]` (the oracle measures the **RC kernel's** `delivery()`); `B2-MEASURE -> RC-FREEZE [G]` — a P0/P1 false-PASS = **NO-GO with one owner decision, no loop**. | `DEPENDENCY-DAG.md` §2 (W5→W6 block), §6 W6 gate |
| B-M4 | **B2-SPEND** is a spending-authority STOP: ≥3 real repos, ≥2 external evaluators, any paid model trial (cap + ledger). Default until decided: offline seeded corpus only; no paid call. | `DEPENDENCY-DAG.md` §5b; `RELEASE-CHARTER.md` §4 (:66-67) |
| B-M5 | The preregistration machinery already freezes an **oracle sha256** as one of the twelve frozen inputs, plus kernel tree, workload identity, run count, `thresholds.delivery` and metrics; a frozen-input change invalidates unread runs and demotes read ones (one-way SEALED→EVALUATING→EXPOSED→DEVELOPMENT). A generalization needs ≥2 independently sealed workloads with sample sizes stated. | `aisef2/cohort/preregistration.py:83-98` (`SHAPES["oracle"]`), `lifecycle.py:114-197` |
| B-M6 | LedgerLock is permanently DEVELOPMENT/REGRESSION: it never seals and never backs a generalization. | `preregistration.py:100-110` (RFC §30) |
| B-M7 | `aisef2/cohort/**` is read-only in all waves; only W6 L6-EVAL may edit it, for defects #64–#66, under the DAG §4(d) amendment. B2 preregistration is those defects' only consumer. | `DEPENDENCY-DAG.md` R10, §4(d); `CODE-AUDIT.md` #64–#66 |
| B-M8 | Two dogfood projects exist and are already configured to run the framework end-to-end: `todo-oc` (browser, one `index.html`, no build step) and `todo-cli` (CLI). Both were used during development. | `docs/DOGFOOD-2026-09-13.md:9-18`; memory "Dự án dogfood todo-oc / todo-cli" |
| B-M9 | The v2.1 survivor-audit file was rewritten, not appended, in 7 of 11 commits — the measured failure mode this protocol's append-only rule exists to prevent. | `W1-DESIGN.md` M10 |
| B-M10 | Plan schedule: **B2 prep starts now** (plan §3 item 9, no spend, no external); protocol freeze 29/12–04/01; **B2-ORACLE-SIGNED 26/01–01/02** (milestone date 26/01) at CODE-FREEZE; B2-MEASURE 02/02–08/02. Risk #5: evaluator/repo lead time is outside engineering — "not started this week ⇒ the 26/01 milestone breaks". | `ACCELERATED-DELIVERY-PLAN.md` §3, §6, §7 |

**Consequence:** the oracle freeze is enforced *mechanically*, not by discipline — the signed oracle manifest's
sha256 is written into each cohort preregistration's `oracle.sha256` frozen input (B-M5), so any label change
after sealing invalidates or demotes the cohort by construction. Measurement (§4) MUST run through that
machinery.

---

## 2. CORPUS

### 2.1 Corpus item (the unit)

A corpus item MUST be the tuple `(repo snapshot, approved bundle, candidate, labelset)`:

- **repo snapshot** — a repository pinned by commit SHA, archived as a tar whose sha256 is recorded.
- **approved bundle** — requirements, plan and obligations in the shipped bundle format, sealed and approved
  before any candidate is labeled; its `plan_hash`/`requirements sha256` are the workload identity (B-M5).
- **candidate** — one worktree state (or diff against the snapshot) the kernel will judge. Candidates are
  **pre-built** (seeded by recipe §2.4 or taken as the known-good tree); B2 measurement itself generates
  nothing and needs no model call.
- **labelset** — §3.

### 2.2 Item classes (all three MUST be present per repo — the non-conflation requirement)

| Class | Content | Expected `delivery()` |
|---|---|---|
| `KNOWN_GOOD` | the candidate satisfies every in-scope criterion | PASS |
| `IN_SCOPE_DEFECT` | ≥1 seeded defect that violates a contracted criterion | FAIL |
| `OUT_OF_SCOPE_DEFECT` | seeded defect(s) only **outside** every contracted criterion | PASS — reported separately as a by-design escape (IMPROVEMENT-ROADMAP §B3), never pooled with false-accepts |

### 2.3 What a "representative external repository" MUST satisfy (measurable before selection)

Each criterion is checked and recorded in `CORPUS-MANIFEST.json` **before** the repo is proposed to the owner:

1. **Size:** 1,000–200,000 lines in the primary language (measured by `git ls-files` + line count at the
   pinned SHA).
2. **Build/test harness:** builds from a clean checkout and runs its test suite green at the pinned SHA on
   Linux **and** macOS with pinned toolchain versions, **offline** (no network, no paid service), one full
   suite run **< 10 minutes** on the reference hardware (recorded).
3. **Probe reachability:** the acceptance criteria to be contracted are expressible with the shipped probe
   catalog (CLI invocation / Python callable / process effect / file artifact) — verified by writing one
   criterion and running it before selection.
4. **License:** OSI-approved license permitting local modification and analysis.
5. **Independence:** the repo appears nowhere in AISEF's development history (no dogfood use, no fixture, no
   workload record); it shares no workload-identity component with LedgerLock (B-M6) or any sealed cohort.
6. **Pinning:** commit SHA + archive sha256 recorded; the snapshot, not the live remote, is the measured object.

The ≥3 external repos SHOULD span ≥2 primary languages and ≥2 harness styles (e.g. CLI tool, library,
web/file-artifact surface). Public repos MAY be cloned read-only without a spend entry; *selecting* a repo
into the corpus is owner-approved under B2-SPEND (§5).

### 2.4 Seeding (recipes, scope class, severity)

- Every seeded defect MUST exist as a committed **recipe**: a diff file + a one-paragraph intent, with the
  seeder's declared scope class (in/out of contract) and severity. The declaration is the seeder's claim only
  — labels (§3) are authored independently of it.
- Severity classes (frozen rubric, attached to the violated criterion):
  - **P0** — the defect causes data loss, a security violation, or a crash on a contracted path;
  - **P1** — a contracted criterion's asserted behaviour is functionally wrong (wrong result/effect);
  - **P2** — contracted behaviour degraded but the criterion's core assertion partially holds (wrong
    message/format, contracted bound missed);
  - **P3** — cosmetic, within scope.
- Minimum counts per repo (default, Q1): ≥1 `KNOWN_GOOD`, ≥5 `IN_SCOPE_DEFECT` covering ≥2 severity classes
  and including ≥1 P0-or-P1, ≥3 `OUT_OF_SCOPE_DEFECT`.

### 2.5 Tiers — the offline seeded corpus is the default (no paid calls, B-M4)

- **Tier-0 (SEED, default, starts now):** `todo-oc` + `todo-cli` (B-M8) as internal seeds. They are already
  configured to run the framework, cost nothing and expose the whole pipeline (bundle → seeded candidates →
  labels → metrics) end-to-end before any external party is involved. **Stated plainly: Tier-0 does NOT
  satisfy the ≥3-external-repo requirement.** Both projects are development-exposed (B-M8), so by the same
  principle that bars LedgerLock (B-M6) they MUST NOT back the external "real value" claim (charter §3) and
  MUST NOT be pooled into the Tier-1 aggregate. Their results are reported separately, labeled
  `tier: "seed"`.
- **Tier-1 (EXTERNAL, under B2-SPEND):** ≥3 repos satisfying §2.3, supplied or approved by the owner
  (plan §7 decision pack #1 item 4: owner supplies candidates; engineering proposes the two dogfood projects
  as internal seeds only, NOT as substitutes). Everything externally visible or paid in Tier-1 is behind
  B2-SPEND (§5).

---

## 3. LABELS

### 3.1 What a ground-truth label asserts

One labelset per corpus item. Per (story, criterion) of the frozen bundle, for the given candidate, a label
MUST assert:

```
{ "story": ..., "criterion": ...,
  "scope": "IN_SCOPE" | "OUT_OF_SCOPE",            # is this criterion part of the approved contract?
  "verdict": "SATISFIED" | "VIOLATED",              # is the candidate's behaviour as asserted?
  "severity": "P0".."P3" | null,                    # required iff VIOLATED
  "basis": "<the command/check the labeler ran and what it showed>" }
```

The item's **expected delivery verdict is derived mechanically, never hand-assigned**: `FAIL` iff ≥1
`IN_SCOPE` criterion is `VIOLATED`, else `PASS`. (`OUT_OF_SCOPE` violations do not change it — §2.2.)

### 3.2 Who may author

- **Tier-0:** the seeding engineer drafts; the owner reviews and signs. Declared limitation: not independent
  (§7) — Tier-0 validates the pipeline, not the claim.
- **Tier-1:** each of the **≥2 external evaluators** authors a complete labelset independently. The seeding
  engineer MUST NOT author Tier-1 labels; the recipes' declared classifications are hypotheses the evaluators
  may contradict.

### 3.3 Independence rule (what evaluators see and must not see)

Evaluators MUST be given: the repo snapshot, the approved bundle (requirements, plan, acceptance criteria),
the candidate tree/diff, the harness, and the severity rubric (§2.4). Evaluators MUST NOT be given: the
kernel's verdicts or artifacts (`delivery()` output, `RUN.json`, journal, probe observations, review
findings), the seeding recipes or their declared classes/severities, the other evaluator's labels before
commitment, or any AISEF internals beyond the shipped CLI docs. Each evaluator commits the sha256 of their
finished labelset **before** any labelset is exchanged (hash-commit, then reveal); both hashes go into the
oracle manifest.

### 3.4 Disagreement handling (adjudication rule)

- Two labels **agree** when `scope` and `verdict` match; a severity differing by one class is recorded and the
  more severe stands (default, Q10). Any other difference is a **disagreement**.
- Every disagreement goes to a recorded adjudication session: evaluators state bases; the owner decides with
  written rationale, appended to the manifest. An item whose disagreement cannot be resolved is marked
  `EXCLUDED_DISAGREEMENT` and leaves the measured corpus — counted and reported, never silently dropped.
- The raw inter-evaluator agreement rate (per field, before adjudication) MUST be reported in
  `B2-ORACLE.json`.

### 3.5 Freeze + sign (B2-ORACLE-SIGNED) — before any measurement; append-only after

- The **oracle manifest** (`closure-evidence/v2/v2.3/B2-ORACLE.json`) lists: every item (ids, snapshot
  sha256s, bundle hashes, recipe digests), every labelset sha256, evaluator identities, commitment hashes,
  adjudication records, exclusions, agreement rate, and the severity rubric digest.
- **B2-ORACLE-SIGNED** = the owner signs the manifest's sha256 (a committed owner-ledger entry naming it),
  **before** the RC kernel runs on any corpus item (B-M3). The manifest sha256 is then written into every
  cohort preregistration's `oracle.sha256` frozen input (B-M5) — a later label change mechanically
  invalidates the cohort.
- After signing, the manifest and labels are **append-only**: a disputed label becomes an appended, dated
  erratum record (`B2-ERRATUM-<n>.json`); the measured verdicts stand on the frozen oracle (B-M9 is the
  measured failure mode this forbids). Measurement results are never grounds to edit a label.

---

## 4. MEASUREMENT

### 4.1 What is measured, and when

- The oracle measures **the RC kernel's `delivery()` at CODE-FREEZE only** (B-M3). The kernel identity is the
  frozen RC tree hash, recorded as each preregistration's `kernel.aisef2_tree`. No measurement run is valid
  against any other tree; a post-freeze kernel change voids the run (and the cohort machinery enforces it).
- Measurement runs through the cohort machinery (default, Q8): one preregistration per (repo, bundle)
  workload, sealed before the first run (`seal`), each item's run recorded (`record_run`), results read once
  (`read_results`), and the cross-repo statement produced by `generalization()` — which itself refuses fewer
  than 2 independently sealed workloads and states sample sizes (B-M5). The charter's bar is ≥3 external
  workloads; the generalization record MUST list them.
- Vehicle (default, Q4): `aisef grade` (B5) on each pre-built candidate — zero OpenCode, no generation, no
  paid call. Fallback if B5 slips: offline `aisef run` with the fake/offline client on the pre-built
  candidate. Either way the route is offline; **a paid model call is not part of B2 measurement** (Q9).

### 4.2 Exact metrics (all reported per tier, per repo, and pooled over Tier-1 only)

Per item: `predicted` = `delivery()` verdict; `expected` = the derived verdict (§3.1). Classification:

| Name | Definition |
|---|---|
| **false-accept (false PASS)** | predicted PASS, expected FAIL — reported **per severity class** of the most severe violated in-scope criterion (P0/P1/P2/P3) |
| **false-reject (false FAIL)** | predicted FAIL (or blocked/refused), expected PASS — the framework-false-rollback axis of `release_acceptance.py:64` measured for real |
| true-accept / true-reject | the agreeing cells |
| **INDETERMINATE** | `NOT_REACHED` or a run refusal: counted as neither PASS nor FAIL, reported in its own class; if > 20 % of a workload's items are INDETERMINATE the workload's measurement is invalid (protocol defect, re-run after fix — the fix is in the harness, never in the labels) |
| **recall (per severity class)** | detected in-scope defective items / all in-scope defective items of that class |
| **precision** | true FAILs / all FAILs |
| **out-of-scope escape rate** | `OUT_OF_SCOPE_DEFECT` items that pass delivery — reported separately as by-design scope behaviour, never summed into false-accepts (charter: truth not conflated) |

Also recorded per item and per run: wallclock, tokens, USD — real or clearly estimated, marked which
(charter §3) — plus hardware, exactly as `W1-DESIGN.md` §10 reports cost.

### 4.3 NO-GO rule (from the DAG, not softened)

- **Any P0 or P1 false-PASS on any tier ⇒ NO-GO.** One owner decision, **no loop** (B-M3): the owner either
  rules NO-GO for v2.3.0 or rules on a remediation; there is no re-measure-until-green cycle. A remediation
  that changes the kernel re-enters at CODE-FREEZE (new RC tree, new B2-MEASURE under the same frozen oracle);
  the failed run's record stays, append-only.
- P2/P3 false-accepts, false-rejects, and escape rates are reported with no pre-committed threshold
  (default, Q11): the owner judges them at the W6 gate with the numbers in hand. They never gate silently.

### 4.4 Records (`closure-evidence/v2/v2.3/B2-*.json`, all append-only)

| File | Shape (top-level keys) |
|---|---|
| `B2-ORACLE.json` | `record`, `id`, `authority` (owner ledger seq + text, mirroring `CONFORMANCE-RULING-1.json`), `rubric_sha256`, `items[]` (ids, snapshot/bundle/recipe digests, labelset sha256s, derived expected verdict), `evaluators[]` (identity, commitment hash), `adjudications[]`, `excluded[]`, `agreement_rate` |
| `B2-PREREG-<workload>.json` | the sealed preregistration record (schema `aisef2.cohort.preregistration/1`), `oracle.sha256` = B2-ORACLE.json digest |
| `B2-MEASURE.json` | `kernel_tree`, `oracle_sha256`, per item: `item_id`, `predicted`, `blocked[]`, `expected`, `class` (TA/TR/FP/FN/INDETERMINATE), `severity`, `cost` (wallclock/tokens/USD + estimated-or-real); aggregates of §4.2; `generalization` (the `lifecycle.generalization()` output); hardware |
| `B2-SPEND.json` | `cap` (owner-set), `entries[]` (date, step, counterparty class, amount, authorization ref) — every externally-visible or paid step |
| `B2-ERRATUM-<n>.json` | appended label disputes (§3.5) |

---

## 5. SPEND / AUTHORITY

### 5.1 The B2-SPEND gate (B-M4)

Behind B2-SPEND (owner cap + ledger, `B2-SPEND.json`): **every externally-visible or paid step** —
contacting or recruiting evaluators, agreeing terms or compensation, sharing the candidate repo list or any
project material outside the repo, acquiring/selecting external repos into the corpus, and any paid model
trial (none is planned, Q9). Not behind it (free, not externally visible): Tier-0 work, read-only cloning of
public repos for *feasibility checks* under §2.3, and drafting this protocol. Evaluator compensation, if any,
comes out of the cap. The two one-time owner **acts** at the gate line: approving the repo list + evaluator
slate + cap (one decision, plan §7 pack #1 item 4), and signing the oracle (§3.5 — an act, not a decision,
per DAG §5b).

### 5.2 Evaluator recruitment timeline — back-calculation from the 26/01 oracle-sign milestone

Working back from **B2-ORACLE-SIGNED ≤ 2027-01-26** (B-M10):

| Latest date | Step (duration) |
|---|---|
| **26/01** | Owner signs the oracle manifest (B2-ORACLE-SIGNED) |
| 19/01 → 26/01 | Adjudication of disagreements, exclusions, manifest assembly, owner review (1 wk) |
| 05/01 → 19/01 | Independent labeling by ≥2 evaluators over ≥3 repos × ≥9 items, hash-commit then reveal (2 wk) |
| 29/12 → 05/01 | Evaluator onboarding: terms signed, access, harness walk-through, one pilot item on Tier-0 (1 wk) |
| 08/12 → 29/12 | Recruitment: identify, contact, agree terms — **crosses the holiday weeks**, so 2 wk nominal + 1 wk holiday buffer (3 wk) |
| **≤ 08/12** | Owner B2-SPEND decision: repo list + evaluator slate + cap — the last responsible moment |
| 25/11 → 08/12 | In parallel, engineering: Tier-0 corpus + tooling under `validation/v23/ground_truth/**`, §2.3 feasibility checks on owner candidates; seeding + bundles for approved repos complete by 05/01 |

**Zero slack after 08/12.** This matches plan §7 risk 5 ("not started this week ⇒ 26/01 breaks"): the
candidate-gathering and owner B2-SPEND package MUST start now (week 25/11), so the 08/12 decision date is met
with the two intervening weeks as the only buffer. Labeling is the critical path once evaluators exist;
seeding is off the critical path only if repo approval lands by 15/12.

---

## 6. Open questions — each with the default the lane builds on

| # | Question | Default |
|---|---|---|
| Q1 | Minimum item counts per repo | ≥1 known-good, ≥5 in-scope (≥2 severity classes, ≥1 P0/P1), ≥3 out-of-scope (§2.4) |
| Q2 | Evaluator count and qualification | exactly 2 external evaluators (the charter floor) + owner as adjudicator; qualification: professional engineer, no AISEF contribution/dogfood history |
| Q3 | Severity taxonomy | the P0–P3 rubric of §2.4, frozen with this protocol |
| Q4 | Measurement vehicle | `aisef grade` (B5) on pre-built candidates; fallback offline fake-client `aisef run` |
| Q5 | INDETERMINATE accounting | own class, neither PASS nor FAIL; > 20 % of a workload ⇒ that workload's measurement invalid (§4.2) |
| Q6 | Do Tier-0 (dogfood) results enter the headline numbers? | measured and reported, labeled `tier: "seed"`, **never pooled** into the Tier-1 claim (§2.5) |
| Q7 | Evaluator compensation / confidentiality terms | owner's call at B2-SPEND; default: compensated inside the cap, terms limited to non-disclosure of unreleased material |
| Q8 | Run measurement through `aisef2/cohort` preregistration/seal? | YES (§4.1); the #64–#66 fixes it depends on are W6 L6-EVAL work under the §4(d) amendment (B-M7) |
| Q9 | Any paid model call in B2? | NO — candidates are pre-built; measurement is offline; a paid trial would be a separate B2-SPEND line |
| Q10 | Severity disagreement within one class | the more severe label stands, recorded; larger gaps adjudicate (§3.4) |
| Q11 | Pre-committed thresholds for P2/P3 false-accepts, false-rejects, escape rate | none — reported to the owner at the W6 gate; only the P0/P1 false-PASS NO-GO is pre-committed (§4.3) |
| Q12 | Repo count above the floor | exactly 3 external repos unless the owner supplies more; more repos trade against the 26/01 date |

## 7. Declared limitations (written into every B2 report)

1. **Tier-0 labels are not independent** (seeder-authored, owner-reviewed); Tier-0 validates the pipeline and
   never the external claim.
2. B2 measures the **end-to-end delivery verdict**, not each probe's soundness: a criterion whose probe
   cannot express the defect contributes a labeled limitation, not a kernel defect.
3. The corpus is bounded and seeded; B2 supports no solve-rate or general-capability claim — only the
   `generalization()` statement over the sealed workloads, with sample sizes (B-M5).
4. Severity at class boundaries is judgment; mitigated by the frozen rubric, two independent labelers and
   recorded adjudication — residual subjectivity is declared, not hidden.
5. Out-of-scope escapes pass `delivery()` **by design**; B2 reports the rate and the non-claim, it does not
   score it.
6. External repos are public; since measurement generates nothing, memorization does not touch B2 itself —
   but if a drafted bundle (B4) is ever used on a corpus repo, that bundle MUST be disclosed in the manifest.

## 8. Exact file-touch list (B2 prep + W6)

- **NEW `validation/v23/ground_truth/**` only** (prep, starts now): `corpus.py` (manifest build + §2.3 checks),
  `labels.py` (label schema, commitment hashing, derived-verdict rule, agreement/adjudication records),
  `metrics.py` (§4.2 classification + aggregates), `seed_recipes/**` (diffs + intents), `CORPUS-MANIFEST.json`,
  fixtures for the Tier-0 items; their tests under `tests/v2/` (NEW files only).
- NEW `closure-evidence/v2/v2.3/B2-*.json` (§4.4), append-only, created at their gates — never edited.
- This file, `docs/v2.3/drafts/B2-GROUND-TRUTH-PROTOCOL-DRAFT.md` (lands on master per the docs rule).
- **`aisef2/cohort/**` edits (#64–#66) are W6-only** under the DAG §4(d) amendment (B-M7) — NOT part of prep.
- **No other `aisef2/**` byte changes**: any kernel byte change would trigger F5 qualification of the batch
  (KERNEL-COUPLING-01) and is not B2's to make.

## 9. Freeze gates for this protocol

1. Owner reviews this draft; the freeze is the owner's written acceptance (directive §5) — after it, §0's
   amendment rule applies.
2. At freeze, defaults Q1–Q12 become binding unless individually overruled in the acceptance.
3. The B2-SPEND decision package (repo candidates, evaluator slate, cap — §5.2) is presented with, or before,
   the freeze; it is a separate owner decision, not implied by the freeze.

## 10. STOP points (genuine; everything else proceeds on defaults)

- **B2-SPEND** (spending authority, B-M4): every §5.1 step waits for the owner's cap + list. Prep proceeds
  Tier-0-only until then.
- **B2-ORACLE-SIGNED** (owner act at a gate): measurement waits for the signature; nothing about this STOP is
  delegable.
- **Label immutability** (immutable evidence contract): any need to change a signed label is a STOP — the
  remedy is an appended erratum (§3.5), and if that cannot preserve the measurement's validity, the owner
  decides; the manifest is never edited.
- **Cohort edits outside W6** (B-M7): if prep finds #64–#66 blocking before W6 opens, STOP for an owner
  scheduling ruling — never edit `aisef2/cohort/**` out of lane.
