AISEF V2 — STABLE RELEASE EXECUTION ORDER
OWNER RELEASE CHARTER / SCOPE FREEZE

TARGET
======

Ship AISEF V2 as:

    distribution: aisef
    version: 2.0.0
    public CLI: aisef
    authoritative runtime: V2

The goal is a real stable release candidate and production-ready artifact,
NOT another research cycle.

This charter supersedes all prior RELEASE-TARGET rulings for AISEF V2
where they conflict with this document.

Historical evidence and historical verdicts remain immutable.

============================================================
0. OPERATING MODE — RELEASE MODE, NOT RESEARCH MODE
============================================================

From this point forward:

DO NOT perform another 360-degree architecture review.

DO NOT open new architecture research work merely because a possible edge
case can be imagined.

DO NOT introduce new assurance objectives unless they satisfy the
RELEASE-BLOCKER rule below.

DO NOT repeatedly redesign → requalify → redesign.

DO NOT optimize for proving that V2 is superior to V1.

The objective is:

    prove that AISEF 2.0.0 satisfies its own frozen release contract.

Proceed automatically through all phases below when the preceding gate
passes.

Ask Owner again ONLY when an explicit STOP condition in this charter occurs
or immediately before final production PyPI publication.

============================================================
1. RELEASE-BLOCKER RULE
============================================================

After this charter is frozen, a newly discovered finding may block V2.0 ONLY
when ALL apply:

1. there is a deterministic reproducer;
2. it affects the public V2 stable runtime, the shipped artifact, or an
   explicit V2.0 release claim;
3. impact is one of:
   - false PASS;
   - false rollback / false block;
   - evidence corruption;
   - authoritative-verdict corruption;
   - release artifact corruption;
   - credential/security exposure in the shipped execution path;
   - P0/P1 correctness failure.

Otherwise:

    record it in V2.1-BACKLOG
    continue V2.0 release.

A research concern without a reproducer does NOT block 2.0.

A defect in an experimental/non-shipped subsystem does NOT block 2.0 unless
it invalidates a release claim.

============================================================
2. V2.0 CLAIM TIER — FROZEN
============================================================

AISEF V2.0 claims:

"AISEF 2.0 provides deterministic, evidence-bound orchestration and
product verification for AI-assisted software delivery."

AISEF V2.0 DOES NOT claim:

- generalization across arbitrary workloads;
- superiority over V1;
- sealed-cohort performance;
- hostile multi-tenant isolation;
- FULL isolation against a malicious same-user host process;
- protection against a machine owner intentionally attacking the framework;
- benchmark leadership.

Threat model for V2.0:

    trusted operator;
    generated/developer code may be faulty or opportunistic;
    candidate code MUST NOT control authoritative proof/verdict channels;
    candidate code MUST NOT corrupt release evidence;
    same-user OS-level hostile isolation is NOT a V2.0 claim.

Therefore:

"all six isolation properties FULL on every OS"

is NOT a V2.0 release requirement.

Any stronger hostile-developer isolation work goes to V2.1 unless needed to
protect the authoritative verdict/evidence path.

============================================================
3. STABLE RELEASE GO CRITERIA
============================================================

V2.0 is RELEASE-GO only if ALL of the following hold.

G1 — PRODUCT VEHICLE
--------------------

- package is `aisef`;
- version is 2.0.0;
- `aisef` public CLI invokes V2 as the authoritative execution path;
- V2 code is included in wheel/sdist;
- no hidden/default V1 execution authority remains behind `aisef run`.

Legacy V1 compatibility MAY remain only as an explicitly named legacy
surface, never as the default authority.

G2 — EXACT RELEASE CANDIDATE
----------------------------

One exact RC commit is frozen.

Record:

- full source SHA;
- kernel tree digest;
- wheel digest;
- sdist digest;
- RunSpec identity where applicable.

No source change after RC freeze may retain the same RC qualification.

G3 — CORRECTNESS
----------------

On the exact RC:

- full test suite: 0 failed;
- lint/static gates green;
- all release-blocking regression tests green;
- Q0-Q5 GREEN on the exact RC;
- zero unaudited mutation survivors in changed release-critical code.

G4 — CI
-------

Exact RC CI must be green on every platform explicitly claimed by the
release.

Do not claim a platform that is not green.

A platform compatibility problem may narrow the 2.0 support statement
instead of triggering an architecture redesign, provided the public claim is
updated before RC freeze.

G5 — AUTHORITATIVE EVIDENCE
---------------------------

Candidate code MUST NOT be able to manufacture or directly control the
authoritative ProbeResult / verdict channel.

Raw authoritative run evidence required for release qualification MUST be
preserved.

Evidence identity must bind the exact candidate/spec/probe/run identities
required by current RFC semantics.

G6 — PUBLIC DELIVERY PATH
-------------------------

The canonical public workflow must run from a clean installed artifact:

    pip install aisef==2.0.0
    aisef ...

It must NOT depend on:

    validation/qualification/c2_p9.py
    forensic checkouts
    developer local paths
    qualification-only scripts

for normal public usage.

G7 — FINAL LIVE RELEASE SMOKE
-----------------------------

Exactly ONE preregistered live release smoke is required.

It is an end-to-end product smoke, NOT a generalization benchmark.

It is judged against ABSOLUTE V2 acceptance, not "V2 > V1".

Required:

- every planned story reaches a legitimate successful terminal state;
- 100% mandatory release acceptance checks;
- 100% mandatory V2 ProductProof for that workload;
- false acceptance = 0;
- framework-caused false rollback/block = 0;
- no identity stop;
- no budget stop;
- final artifact/workspace evidence preserved.

V1 oracle/result may be recorded for information only.

V1 IS NOT A RELEASE GATE.

G8 — RELEASE MECHANICS
----------------------

Before production PyPI:

- TestPyPI or equivalent non-production artifact verification path exists;
- clean environment installs exactly the built artifact;
- CLI smoke passes;
- package data is present;
- release workflow cannot accidentally publish an RC merely because any
  generic `v*` tag exists;
- release conformance/freshness gates are current or explicitly replaced by
  this V2 release charter.

G9 — GOVERNANCE
---------------

Commit this entire Owner charter verbatim as the authoritative V2 stable
release ruling.

Create a new append-only RELEASE-DECISIONS entry superseding the historical
NO_GO for purposes of this V2.0 release process.

Do NOT rewrite historical NO_GO records.

============================================================
4. EXPLICITLY DEFERRED TO V2.1+
============================================================

The following MUST NOT delay V2.0 unless a concrete V2.0 blocker is measured:

- sealed evaluation cohorts;
- generalized performance claims;
- proof that V2 outperforms V1;
- FULL hostile-developer isolation across all OSes;
- full same-user process secrecy;
- reconstructing every historical Owner ruling verbatim;
- broad branch-history archaeology not required for the release tree;
- witness-digest redesign where equal digest is legitimate content
  addressing and no integrity violation is reproduced;
- research-only benchmark improvements;
- additional architecture studies.

Record these under:

    docs/v2/V2.1-BACKLOG.md

and continue.

============================================================
5. PHASE S0 — RELEASE SCOPE FREEZE
============================================================

FIRST create and commit:

    docs/v2/V2-STABLE-RELEASE-CHARTER.md

containing this Owner charter verbatim.

Also create a machine-readable release charter containing:

- package = aisef;
- version = 2.0.0;
- authoritative runtime = V2;
- claims;
- non-claims;
- threat model;
- G1-G9;
- deferred list;
- release-blocker rule.

Create dedicated branch:

    release/v2.0.0

Do NOT use the forensic checkout as a release working tree.

Resolve and record the exact source branches/commits being incorporated.

Preserve all historical evidence branches unchanged.

============================================================
6. PHASE S1 — IMMEDIATE FAIL-CLOSED SAFETY
============================================================

Before any provider/model execution:

Close B2.

Every qualification/delivery profile MUST fail closed unless explicitly
authorized by a frozen experiment/release-smoke record.

No default path may start:

- default model;
- inherited uncontrolled environment;
- unlimited turns;
- unlimited tokens;
- unattested route.

Tests required for:

- default qp-2.9;
- v1-aligned;
- delivery profiles;
- direct runner invocation.

No provider call in these tests.

After this fix:

    UNAUTHORIZED_LIVE_RUN_POSSIBLE = NO

============================================================
7. PHASE S2 — ONE AND ONLY ONE PRE-RC FIX WINDOW
============================================================

This is the ONLY planned kernel/harness correction window before RC freeze.

Close the following measured blockers.

------------------------------------------------------------
B1 — authoritative verdict forgery
------------------------------------------------------------

Required property:

    candidate code cannot manufacture, spoof, emit, overwrite or directly
    control the authoritative ProbeResult/verdict channel.

The fix MAY use:

- process separation;
- private parent/verifier channel;
- IPC;
- capability separation;
- another minimal mechanism.

Do NOT require full hostile-host isolation.

Add deterministic red/green attack fixtures for every affected probe kind.

A forged RESULT must be rejected.

------------------------------------------------------------
B3 — raw journal preservation
------------------------------------------------------------

Preserve the authoritative chained journal before cleanup.

It must survive:

- normal completion;
- Exception;
- BaseException / invariant failure;
- refused shutdown;
- interrupted run.

The committed/release evidence must permit hash-chain integrity verification.

A projection may exist but may not replace the authoritative raw journal.

------------------------------------------------------------
B4 — git configuration escape
------------------------------------------------------------

Qualification/session git operations must not execute developer-controlled
git config hooks/filters/fsmonitor/includes.

Use isolated git configuration.

Regression fixtures must cover at minimum:

- core.fsmonitor;
- clean filters;
- include.path / config inclusion;
- gitfile indirection if relevant.

------------------------------------------------------------
B6 — measured execution-boundary escapes
------------------------------------------------------------

Close the measured paths that can corrupt qualification/evidence:

- ignored files surviving checkout transitions;
- writable .pth / unintended host Python startup injection where applicable;
- uncontrolled host /tmp artifacts that can influence proof execution;
- inherited environment/path contamination affecting probes.

Use the smallest deterministic correction.

Do NOT turn this into a general-purpose hostile-host sandbox project.

------------------------------------------------------------
B7 — merge/revert defect
------------------------------------------------------------

When:

    candidate == base/tip

do NOT create a logical merge that later allows revert to reset the previous
story's merge.

No-change stories must preserve prior trunk history.

Add a deterministic reproducer:

    prior story committed
    next story candidate == base
    simulated post-merge failure
    previous story remains present

Required GREEN.

------------------------------------------------------------
B15 / WIP suite failures
------------------------------------------------------------

Fix encoding/destructive-authority/conformance issues introduced by accepted
WIP before it enters the release branch.

------------------------------------------------------------
B12 — delivery execution code
------------------------------------------------------------

Separate:

    PRODUCT runtime
from
    qualification/research harness.

Do NOT ship c2_p9.py as the user's required runtime.

Reusable runtime mechanisms required by `aisef run` belong in product code
with normal tests/qualification.

Qualification wrappers remain development tooling.

============================================================
8. FIX-WINDOW EXIT RULE
============================================================

At the end of S2:

- run targeted regression tests;
- run targeted mutation over changed control code;
- zero unaudited survivors;
- run one full local suite.

Then FREEZE THE KERNEL DESIGN.

After this point:

NO new kernel feature work before 2.0.

If a new finding appears, apply §1 RELEASE-BLOCKER RULE.

If it is not a release blocker:

    backlog it
    continue.

============================================================
9. PHASE S3 — PRODUCTIZE V2 BEFORE QUALIFICATION
============================================================

Productize V2 now, BEFORE final Q0-Q5.

Required:

- include V2 implementation in `aisef` wheel;
- make V2 the authoritative `aisef run` path;
- remove/disable hidden default V1 authority;
- update package data;
- update CLI/version surfaces;
- update installation docs;
- update migration notes from V1;
- update packaging_check;
- update wheel CI job;
- add clean-install fixture.

Do NOT qualify first and package afterward.

The shipped source tree must be the tree that is qualified.

============================================================
10. RELEASE WORKFLOW HARDENING
============================================================

Correct release mechanics before RC freeze.

Required:

- production publication must not occur from arbitrary `v*` RC tags;
- add a TestPyPI / staging publication path OR an equivalent safe artifact
  installation workflow;
- stable production publish must require the release gates;
- refresh/replace stale conformance policy consistently with this charter;
- set package version to 2.0.0 only in the final stable candidate flow.

Do not create an accidental production PyPI upload during this task.

============================================================
11. PHASE S4 — FREEZE EXACT RC
============================================================

When S0-S3 are green:

create exactly one release candidate:

    V2.0-RC1

Freeze:

- full source SHA;
- V2 kernel tree;
- package source tree;
- wheel build inputs;
- requirements/contracts/specs;
- release acceptance suite;
- qualification configuration.

Then perform any mechanically necessary qualification re-pin in a separate
harness-only commit following existing precedent.

The re-pin MUST NOT change product/kernel semantics.

Qualification tools must run from the RC/release workspace, NOT the forensic
main checkout.

Record:

RC_SOURCE_SHA
RC_KERNEL_DIGEST
RC_WHEEL_DIGEST when built
RC_SDIST_DIGEST when built

============================================================
12. PHASE S5 — FINAL DETERMINISTIC QUALIFICATION
============================================================

On EXACT RC1:

1. full suite;
2. lint/static checks;
3. CI on claimed release platforms;
4. Q0;
5. Q1;
6. Q2;
7. Q3;
8. Q4 fresh;
9. Q5 fresh/reproduction as required by existing semantics;
10. clean wheel build;
11. wheel digest binding.

Q0-Q5 GREEN must refer to this exact RC candidate.

Do not cite the historical c11615a qualification as current RC evidence.

Historical c11615a remains historical evidence only.

If deterministic qualification fails:

- classify the exact failure;
- apply Release-Blocker Rule.

If a true P0/P1 release blocker requires a kernel change:

    RC1 = REJECTED
    STOP
    report exact root cause to Owner.

Do NOT silently patch RC1 and keep its identity.

Do NOT start RC2 automatically.

============================================================
13. ABSOLUTE RELEASE ACCEPTANCE — NOT V1 NON-REGRESSION
============================================================

Create/freeze:

    V2-RELEASE-ACCEPTANCE.json

before the live release smoke.

It must define product correctness independently of V1 implementation.

For the selected release-smoke workload:

- requirements are frozen;
- mandatory acceptance checks are deterministic;
- required ProductProofSpecs are frozen;
- pass/fail threshold is frozen before provider execution.

DO NOT require:

    V2 oracle score > V1 oracle score.

V1 comparison is informational only.

If V1 oracle and V2 acceptance are mutually incompatible, this does NOT
block V2 unless the conflicting V1 behavior is itself an explicit V2.0
requirement.

============================================================
14. RELEASE-SMOKE WORKLOAD
============================================================

To avoid opening another benchmark project:

LedgerLock MAY be used exactly once as a PUBLIC DEVELOPMENT /
RELEASE-SMOKE workload.

This charter supersedes the earlier:

    LEDGERLOCK_FURTHER_RELEASE_ATTEMPTS = NOT_AUTHORIZED

ONLY for:

    V2.0 RELEASE SMOKE #1

LedgerLock remains:

    DEVELOPMENT_REGRESSION / PUBLIC RELEASE SMOKE

It is NOT:

    HOLDOUT
    SEALED
    GENERALIZATION EVIDENCE

Public/exposed stimuli do not invalidate its use as an end-to-end smoke
because no generalization/model-quality claim is made from it.

Do NOT use hiddenness as a claim.

============================================================
15. PHASE S6 — PREREGISTER ONE LIVE RELEASE SMOKE
============================================================

Only after S5 is completely green:

create:

    V2.0-RELEASE-SMOKE-1-PREREGISTRATION

Bind:

- exact RC SHA;
- exact wheel digest;
- exact plan;
- exact acceptance suite;
- exact ProductProof set;
- exact model route;
- exact identity grade;
- exact prompts;
- exact client;
- exact retry policy;
- exact budgets;
- exact stop rules;
- raw journal preservation;
- workspace/object preservation.

Budget:

derive a recommended envelope from the offline rehearsal.

Use:

    actual deterministic estimate + 25% headroom

but NEVER exceed these Owner hard ceilings:

    MAX_PROVIDER_REQUESTS = 60
    MAX_TOTAL_TURNS = 700
    MAX_COMBINED_INPUT_TOKENS = 60000000
    MAX_OUTPUT_PLUS_REASONING_TOKENS = 400000

Retain per-session maximum:

    MAX_TURNS_PER_SESSION = 80

No automatic budget expansion.

============================================================
16. ONE LIVE RELEASE SMOKE AUTHORIZATION
============================================================

This charter authorizes EXACTLY ONE paid:

    V2.0 RELEASE SMOKE #1

after all previous gates are GREEN.

No Owner round-trip is required immediately before starting it.

Preflight must:

- resolve/attest the fixed model route;
- bind resolved RunSpec;
- enforce budget;
- preserve journal/evidence;
- refuse on identity mismatch.

During the run:

NO repair.
NO prompt change.
NO plan change.
NO budget increase.
NO route change.
NO retry beyond preregistered policy.
NO second release smoke.

============================================================
17. LIVE RELEASE-SMOKE PASS CONDITIONS
============================================================

RELEASE_SMOKE_PASS = YES only if ALL frozen acceptance requirements hold.

At minimum:

- all planned stories legitimate successful terminal states;
- mandatory ProductProof = 100%;
- frozen release acceptance suite = 100%;
- false acceptance = 0;
- framework false rollback/block = 0;
- no evidence-integrity violation;
- no provider identity violation;
- no budget stop;
- raw journal preserved and verified;
- final main/workspace preserved;
- all referenced revisions preserved.

V1 result:

    INFORMATIONAL_ONLY

Do not turn it into a gate.

If release smoke FAILS:

    RELEASE_GO = NO
    STOP

Do NOT run another paid attempt.

Do NOT fix-to-green automatically.

Return root cause to Owner.

============================================================
18. PHASE S7 — TESTPYPI / CLEAN INSTALL
============================================================

If Release Smoke PASS:

Build wheel + sdist from the already qualified exact release candidate.

Verify digests are the frozen expected values.

Publish to TestPyPI/staging, not production.

Create a completely clean environment.

Verify:

- install succeeds;
- `aisef --version` reports intended V2 release;
- `aisef` CLI starts;
- canonical public workflow works;
- package data/resources exist;
- no dependency on repository checkout;
- no dependency on qualification files;
- no accidental V1 default authority.

Run release artifact smoke from the installed package, not the source tree.

============================================================
19. FINAL PRODUCTION RELEASE HOLD
============================================================

Do EVERYTHING up to production release automatically.

DO NOT publish production PyPI yet.

DO NOT create the final production `v2.0.0` tag yet.

When all gates are complete, return:

    FINAL_RELEASE_READY = YES

and STOP for Owner's final production-publish confirmation.

Owner confirmation will authorize:

- final stable tag;
- production PyPI publish;
- post-publish clean-install verification;
- release notes publication.

============================================================
20. REVIEW DISCIPLINE
============================================================

Do NOT create another swarm of research agents.

Maximum before RC freeze:

- one implementation reviewer;
- one adversarial/release reviewer.

At RC qualification:

- at most two independent reviewers against THIS frozen charter.

Their job is NOT to invent new requirements.

They may only identify:

- violation of this charter;
- deterministic release blocker under §1;
- evidence inconsistency.

Anything else goes to V2.1 backlog.

============================================================
21. RECORD NEW FINDINGS WITHOUT DERAILING RELEASE
============================================================

For every new finding record:

ID:
REPRODUCER:
AFFECTED_SHIPPED_PATH:
AFFECTED_V2_CLAIM:
SEVERITY:
RELEASE_BLOCKER_RULE_1: YES|NO
RELEASE_BLOCKER_RULE_2: YES|NO
RELEASE_BLOCKER_RULE_3: YES|NO
V2_0_DISPOSITION:
    BLOCK | V2.1_BACKLOG

No "needs more research" state is allowed unless the release-blocker
classification itself cannot be determined.

============================================================
22. REQUIRED PHASE CHECKPOINTS
============================================================

Maintain one machine-readable:

    closure-evidence/v2/release/V2-STABLE-STATUS.json

Fields:

S0_SCOPE_FREEZE:
S1_FAIL_CLOSED:
S2_FIX_WINDOW:
S3_PRODUCTIZED:
S4_RC_FROZEN:
S5_QUALIFIED:
S6_RELEASE_SMOKE:
S7_TESTPYPI:
FINAL_RELEASE_READY:

Each:

    NOT_STARTED | RUNNING | PASS | FAIL | BLOCKED

Also record:

CURRENT_RELEASE_BRANCH:
CURRENT_SHA:
CURRENT_KERNEL_DIGEST:
CURRENT_WHEEL_DIGEST:
OPEN_V2_0_BLOCKERS:
V2_1_BACKLOG_COUNT:
PROVIDER_CALLS:
PAID_RELEASE_SMOKES_USED:

============================================================
23. PROHIBITED BEFORE FINAL OWNER CONFIRMATION
============================================================

NO:

- second paid release smoke;
- V2 architecture redesign;
- sealed cohort;
- new generalization benchmark;
- V1 superiority experiment;
- broad new mutation campaign unrelated to changed code;
- post-RC silent kernel patch;
- production PyPI publish;
- final stable production tag.

============================================================
24. FINAL RETURN TO OWNER
============================================================

Return one concise release report:

RELEASE_BRANCH:
RELEASE_CHARTER_COMMIT:

FIX_WINDOW_COMMITS:
PRODUCTIZATION_COMMIT:
RC_SOURCE_SHA:
RC_KERNEL_DIGEST:
RC_WHEEL_DIGEST:
RC_SDIST_DIGEST:

B1_VERDICT_CHANNEL:
B2_ALL_PROFILE_HOLD:
B3_RAW_JOURNAL:
B4_GIT_CONFIG:
B6_BOUNDARY_HARDENING:
B7_MERGE_REVERT:
B12_PRODUCT_RUNTIME:
B13_RELEASE_WORKFLOW:
B14_EXACT_RC_CI:
B15_SUITE:

FULL_SUITE:
CI_PLATFORMS:
Q0:
Q1:
Q2:
Q3:
Q4:
Q5:

LIVE_RELEASE_SMOKE:
STORIES:
PRODUCT_PROOF:
ABSOLUTE_RELEASE_ACCEPTANCE:
FALSE_ACCEPTANCE:
FALSE_ROLLBACK_OR_BLOCK:
BUDGET_USED:
RAW_JOURNAL_VERIFIED:

TESTPYPI:
CLEAN_INSTALL:
PUBLIC_CLI_SMOKE:

V1_COMPARISON_INFORMATIONAL:

OPEN_V2_0_BLOCKERS:
DEFERRED_V2_1_ITEMS:

PROVIDER_CALLS_TOTAL:
PAID_RELEASE_SMOKES_USED:

FINAL_RELEASE_READY:
YES | NO

IF NO:
EXACT_BLOCKER:
REPRODUCER:
REQUIRED_OWNER_DECISION:

IF YES:
NEXT_ACTION:
OWNER_CONFIRM_PRODUCTION_TAG_AND_PYPI
