# ADR-009 — Phase-3 cross-tier invariants: structured findings, candidate-bound server, in-flight budget reservation

Date: 2026-09-12. Status: **accepted** — three of the seven systemic
issues from the prior audit now have first-class machinery, and the
rest of the repair path is wired into the new rule.  This ADR records
the cross-tier invariants the project now relies on.

## Context

The pre-Phase-2 audit surfaced seven systemic issues. Three of them
were *transactional* defects: a reviewer could move the goalposts on
its own prescription (bug 61); two parallel runs could share a dev
server because nothing bound the server's identity to a candidate;
and a long-running expensive call could blow the monthly budget
without the orchestrator learning about it until the bill arrived.
The other four issues were *semantic* defects that depended on these
three transactional ones being fixed first.

The decision below formalises the seam at which the transactional
defects are closed: a new structured finding model, a per-run lease
on dev-server identity, and an in-flight reservation against the
budget ledger.

## Decision

### 1. Structured findings, not stringly-typed lists

Every advisory claim is now a ``Finding`` instance
(``aisef/control/findings.py``) with:

- a stable 16-hex ``id`` computed over ``(source, trust, file, line,
  body, behavior_id, scope)`` — two findings raised against the same
  defect produce the same id, regardless of how the agent rewrites
  the wording;
- an explicit lifecycle (``OPEN / CLOSED / REOPENED / SUPERSEDED /
  STUCK``);
- ``apply_transition(...)`` enforcing: closing without evidence
  requires ``force_prescription_match=True`` **and** a matching
  ``previous_prescription`` — the rule that prevents "the author did
  what I told them, and I failed them for it";
- ``agent`` trust rejected at construction time.  Reviewer/security
  records must carry a 64-hex ``contract_authority`` digest (the
  invariant is also enforced by the memory layer; see ADR-007).

The legacy ``list[str]`` callers (``attempt.review_findings`` etc.)
are kept as the line-of-text form so existing reports and dashboards
work.  A ``Finding.parse_lines`` round-trip is the bridge; callers
migrate one site at a time.

### 2. Candidate-bound dev server

Each ``AppServer`` invocation may receive optional ``lease_root`` and
``run_id`` arguments (``aisef/harness/mockup_verify.py``). When set:

- ``acquire_port_lease(root, run_id, base_url)`` takes a non-blocking
  flock over ``.aisef/lease/port-<run_id>.lock``.  Two runs sharing a
  port see one succeed, the other get None back.
- The first ``start()`` writes ``.aisef/lease/<run_id>.json`` with
  the candidate SHA, base URL, pid, and started-at timestamp.
- The poll loop probes ``GET /_aisef/identity`` on the dev server and
  refuses to declare the server "ready" if the bound run id does not
  match.  A dev server already running on the configured port
  (``vite from a removed worktree``, bug 15) is rejected with a clear
  error rather than silently answering.
- ``stop()`` releases the lease and removes the lease file.

When ``lease_root`` is unset (legacy call sites, external fixtures) the
liveness check is preserved.  ``verify_screens(...)`` derives a
``run_id`` from ``artifact_root`` + ``story_id`` automatically so the
default path is identity-bound.

### 3. In-flight budget reservation

``BudgetGuard.reserve(...)`` (``aisef/control/budget.py``) wraps every
paid client call:

- ``reserve(story_id=..., est_usd=..., est_turns=...)`` returns a
  context manager.  When no cap is configured the guard short-circuits
  with a no-op (no I/O, no lock acquisition) so projects that have
  not yet set ``run.cost_cap_usd`` pay zero overhead.
- Otherwise the guard takes an exclusive flock on
  ``_bmad-output/budget.json`` (per-project ledger), evaluates the
  cap against current ``spent_usd + est_usd``, and refuses oversized
  estimates with ``BudgetExceeded`` *before* the call dispatches.
- On ``__exit__`` (success) the actual ``cost_usd`` and ``num_turns``
  recorded by the result are settled into the ledger; the cap is
  re-checked post-call so a long-running call cannot push the project
  over budget silently.
- On ``__exit__`` (exception) the reservation is refunded and the
  ledger is rewritten, so the next attempt can still run if there is
  room.

The orchestrator wires the guard through
``aisef/phases/implement.py:_reserved_client_run`` which slots in
above every ``client.run(spec)`` call site — both the developer
attempt and the reviewer/security session.  ``review_story`` records
a synthesised failure result if the budget gate fires, so the
pipeline can still react.

### 4. Unified qualification policy

The phase-2 prior already wired ``aisef/control/qualification.py``
into ``phases/improve.py``.  Phase 3 makes the policy *opt-in* for
``phases/run.py`` via ``run.qualify_preflight=true`` (default False
so existing flows are untouched).  When enabled, ``run.py``
projects pending stories → failed before calling the policy so a
fresh project qualifies as "ready to verify" instead of falling into
the "unexpected state" branch.

## Cross-tier invariants

- **Evidence ≠ memory.** ``Finding`` evidence lives on the canonical
  line shape and never shares a write path with the budget ledger
  (``_bmad-output/evidence/`` vs. ``_bmad-output/budget.json``).  The
  separation test in ``tests/test_phase3_integration.py`` pins this.
- **Memory = context, never evidence.** A reviewer/security capture
  into memory must carry a 64-hex ``contract_authority`` digest of the
  contract under review (ADR-007 §3).  Without it the record is
  advisory-only and cannot be promoted to evidence.
- **Lease idempotence.** Acquiring a lease twice from the same run
  returns the same ``fd``; releasing twice is a no-op.  Two distinct
  runs see exactly one winner.
- **Budget refund is exception-safe.** If the paid call raises, the
  reservation is refunded before the exception propagates.  An
  unhandled error therefore never desyncs the ledger from the actual
  billing.

## Trade-offs

- **Opt-in for the pre-flight qualify gate.** Auto-enabling
  ``run.qualify_preflight`` would have rejected every existing test in
  the harness (a fresh project's stories are *pending*, which the
  policy does not yet understand).  Keeping it default-False preserves
  backward compatibility for fixtures while letting operators turn it
  on when they're ready to depend on it.
- **Findings as ``list[str]`` in the report.**  The gate consumes the
  canonical line shape today; migrating every read site to ``Finding``
  instances would have churned the scoreboard for marginal benefit.
  The bridge (``parse_lines``) keeps the wire format a stable
  intermediate representation.

## Open — the three remaining semantic issues (reconstructed 2026-09-12)

O3 closed on 2026-09-14; its measurement is recorded below under *Closed — O3*.
Three remain: O1, O2, O4.

**Provenance, stated plainly.** The pre-Phase-2 audit that produced "seven
systemic issues" was never written to disk: neither this repository nor any
reachable session transcript contains the list.  The three transactional ones
are recoverable because they became code (findings, lease, budget).  The four
semantic ones (O1, O2, O4 below and O3 under *Closed*) are a **reconstruction**
from evidence that *is* on disk — the owner
decisions of 2026-09-06, the calibration note that pinned the neighbour weight
to zero, the C11 conformance probe, and the cost figures in
`docs/STATUS-2026-09-05.md`.  They are not quoted from the original audit.  If
that list resurfaces, reconcile against this section and say which items moved.

The rule that produced this section: *a statement of the form "N items remain"
must carry the list, on disk, in the same document.*

Each item names the semantic question, why it had to wait for the transactional
seams, and the measurement that closes it.

### O1 — the reviewer's verdicts are not themselves qualified

`review` is the only `model-judge` check in `CHECK_NAMES`.  Every other check
has three controls certifying the *check*; nothing certifies the *judgement*.
Conformance probe C11 already showed the reviewer model passing a candidate
that the machine gate blocked, which is evidence the two layers disagree — but
not a measurement of how often, or in which direction.

*Why it waited*: counting "findings raised vs findings that were real" is
meaningless while a reviewer can restate the same complaint in new words.
Stable `Finding.id` (§1) makes the count well-defined.

*Closes when*: a reviewer-qualification table exists with the same three
controls as the machine checks, scored over a corpus of recorded reviews —
false-block rate and miss rate both reported, neither hidden behind a pass.

### O2 — the ledger records that a behaviour is a GAP, never what kind of gap

`improve` picks one GAP and writes one repair story.  But three different
absences are all recorded as GAP: the behaviour was never built, the behaviour
exists but no test exercises it, and the behaviour and its test both exist but
the trace linking them is missing.  Only the first deserves a paid repair
story; the owner decision of 2026-09-06 §4 had to say so in prose ("a gap that
is only missing traceability is fixed by the harness, not by a story"), and
that rule still lives in a decision record rather than in code.

*Why it waited*: distinguishing the three requires the evidence for one
candidate to be trustworthy, which is what the SHA-bound checks and the nop
control provide.

*Closes when*: `Behaviour.gap_kind` exists with the three values, the repair
queue routes each kind to a different action (story / test-only story /
harness metadata fix), and `aisef issues` reports the three counts separately.

### O4 — spend is attributed to calls, not to outcomes

With reservations correct, the ledger can say what a run cost.  It still cannot
say what the money bought.  The two dogfood corpora differ by a factor of
thirty-six per story (`e9` ≈ $70, `par` ≈ $1.9) and nobody has decomposed the
difference; `docs/ROADMAP-POST-1.0.md` asks for "net VERIFIED behaviour per
dollar" and no command computes it.

*Why it waited*: attribution needs a cost record that is complete at the moment
of the call rather than reconciled afterwards — the in-flight reservation is
exactly that record.

*Closes when*: one command reports, per story, the spend split across attempt
outcomes (plan-blocked / code-failed / environment-failed / passed) and the net
VERIFIED behaviours the spend produced.

## Closed — O3: preservation radius, calibrated (2026-09-14)

*The issue, as it stood:* preservation is scoped by file, not by behaviour —
`complexity.verified_touched` answers "did this story touch a file owned by a
verified behaviour of another story" by looking the file up through the owning
story's `write_scope`, which is a proxy for whether the behaviour still holds,
and the neighbour weight that would widen the blast radius was pinned to 0
because 0.5 blocked three innocent `e9` stories.  It waited on §3 because
widening the radius multiplies re-verification cost, unbounded until the budget
seam could reserve and refund.

O3 asked for that weight to be calibrated on a recorded corpus with **both**
error rates reported, and for the chosen value to be a config knob with
the measurement next to it.  Done: the knob is
`story.verified_touched_weight`, its default is **0.0**, and the table below is
in `aisef/config.py` beside it.  `validation/o3_preservation_radius.py`
regenerates every number from `_bmad-output/` — no model calls, no network.

**The `e9` corpus the pinning note cited is gone.** `find` over
`~/Downloads/projects` and over `~` finds no `e9` directory (only unrelated npm
and Messages caches).  The three stories the note names (02-03 15.0→17.0,
03-03 15.5→17.0, 05-01 16.0→17.5) are therefore **not** reproducible on this
machine and are not carried into the table.  The corpora used instead are
`todo-oc`, `todo-cli`, `todo` and `todo-e2e`.  `marks-cli` is excluded because
it was mid-run while this was measured (92 files written in the preceding two
hours), so its rows would not be stable between two runs of the script.

**A stale input had to be fixed before any weight could be calibrated.**
`complexity.read_ledger` read `ledger.json`, a file refreshed only at the end of
a sprint or by `aisef report` — while the gate's preservation check and the
developer's preservation slot both reproject from evidence
(`implement._ledger`).  Consequence, measured: **24 of 32** recorded stories
were scored against fewer neighbours than the evidence projection held; todo-e2e
STORY-05-01 recorded 0 while the projection held 9, and **12 of the 15** stories
that really broke a neighbour were scored at 0 — a weight cannot multiply a zero,
so on the recorded input the dimension was inert exactly where it mattered.
Calibrating a weight on that input would have been calibrating on a bug, so
`read_ledger` now returns the
same projection the gate reads, with `ledger.json` filling in only behaviours
evidence does not mention.  Cost 44–350 ms per call on 0.8–6 MB of evidence.

**Ground truth — how "was this story actually fine" was derived.** Two
independent, SHA-bound sources, unioned:

1. the gate's own `preservation` check recorded `failed` in a `gate:verdict`
   note, which means a VERIFIED behaviour of another story was red at that
   candidate;
2. a ledger `REOPENED` entry **corroborated** by red evidence at the same
   instant — for an `ac` behaviour the named criterion red, for `fr`/`nfr` a
   criterion of the owning story red, for `qa:*`/`mockup:` a red run.

Corroboration is not ceremony: **29 REOPENED entries across the four corpora
are not corroborated** and are reported as artifacts rather than counted as
regressions.  todo-cli STORY-06-01 is the clearest — five requirements flipped
to REOPENED while every one of its 65 tests was green, because that story
`covers` the same requirements as three earlier stories and had one criterion
with no test, so its own rollup wrote them red; `Ledger.observe` then kept the
red and discarded the green that followed it in the same loop (green on an
unlanded candidate returns early).  That is a defect in the requirement rollup,
not a regression, and not O3 — it is recorded here for whoever takes O2.

**The calibration.** 32 scored stories, 15 confirmed regressors, 17 clean.
Blocked = the story's score crosses `story.max_complexity` (16.0) once the
neighbour dimension is weighted.

| weight | blocked | innocent blocked | regressors caught | regressions missed |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 | 15 |
| 0.25 | 0 | 0 | 0 | 15 |
| 0.5 | 0 | 0 | 0 | 15 |
| 1.0 | 0 | 0 | 0 | 15 |
| 1.5 | 3 | 2 | 1 | 14 |
| 2.0 | 6 | 3 | 3 | 12 |
| 2.5 | 7 | 3 | 4 | 11 |
| 3.0 | 10 | 4 | 6 | 9 |
| 4.0 | 14 | 6 | 8 | 7 |
| 5.0 | 18 | 7 | 11 | 4 |

**Why 0.0 is the chosen value.**  No weight at or below 1.0 changes a single
verdict on these corpora — including the 0.5 the note pinned back, which here is
indistinguishable from 0.  The first verdict any larger weight changes is a
false one: todo-oc STORY-04-03 crosses the threshold once w passes 1.08 and broke
nothing, while the first true positive (todo-e2e STORY-05-01) only arrives at
1.11.  From there the two error rates move together, never apart: buying 11 of
the 15 regressors costs blocking 7 of the 17 clean stories, and blocking 18 of
32 stories is not a gate, it is a stop.  Spearman(neighbour count, broke a
neighbour) = **0.235**; mean neighbour count 3.13 for regressors against 2.12
for clean stories.  The count barely ranks the risk it is meant to measure, so
no positive default is defensible — the knob exists for a project that measures
its own table and finds otherwise.

**What the measurement says about O3's real question.** The weight was never
the lever, because the predicate underneath it is nearly always true: **27 of
the 32** stories touch at least one neighbour — 15 of 15 regressors, but also 12
of 17 clean stories.  A signal that fires on 84% of stories cannot rank the 47%
that regress, whatever it is multiplied by; that is what ρ = 0.235 means in one
sentence.  Widening the radius therefore moves cost, not recall.

The direction that would move recall is scoping preservation by behaviour
instead of by file — re-verify the neighbour's criteria at the candidate, which
the ledger already knows how to do — and that is a change to the predicate, not
to its weight.  Two recorded observations say where it bites.  First, file
overlap answers a question about *paths* while the ledger's requirement records
have no paths at all: they are reached only through the owning story's declared
write scope, which is why todo-cli STORY-06-01 — one changed file, a new
integration test — overlapped nothing on either its declared scope or its actual
changed files, yet five requirements of three other stories changed status
during its run.  Second, the declared scope it was measured against is a plan
artifact: it need not match what the story changed.  Until the predicate is
behaviour-shaped, leave this weight at 0.

## Deferred

- Budget cap values are surfaced in ``Config`` defaults but not yet
  validated against the per-project ledger at startup (a project
  might set ``run.cost_cap_usd=0.50`` even when prior runs already
  exceeded that).  The next iteration adds a "set down" hook in
  ``aisef doctor``.
- ``mockup_verify`` derives ``run_id`` from
  ``artifact_root / story_id``; flows where one story runs against
  multiple candidate branches (re-verify across rebases) need a
  per-branch run id.  Not urgent: ``ready_with_identity`` is
  fail-closed when the run id mismatches.
- The same-UID same-filesystem hostile-simulator test
  (``_uid_filesystem_race``) was documented in the audit but not
  implemented; the lease file uses ``os.O_CLOEXEC`` plus
  ``flock_ex_nb`` but on a kernel that hands out different UIDs to
  different processes, ``flock`` semantics differ — a stress test is
  the right next step before any multi-tenant deployment.

## Follow-up: two cross-tier defects in the budget seam

Two transactional gaps surfaced once the reservation lock was
exercised end-to-end.  Both were uncovered by the new
``validation/phase3_wireup_e2e.py`` step-7 scenarios and closed in
``595c731`` (``fix(phase 3+): lock BudgetGuard ledger via sidecar
to survive os.replace``) and ``dee903b`` (``fix(phase 3+):
BudgetGuard cap check counts in-flight reservations``).  Each fix is
pinned by a pair of unit tests in ``tests/test_budget.py`` and the
matching ``7.lock sidecar serialises concurrent reserves`` /
``7.cap check counts outstanding reservations`` checks in the
validation harness.

### ``os.replace`` orphans the held flock

``BudgetLedger.save()`` rebuilds the state file via ``os.replace``
for atomic durability.  On filesystems where ``os.replace`` swaps
the inode (macOS APFS, several network FS), the exclusive ``flock``
held on the previous fd is left holding a lock on an orphan inode
while a new fd on the replacement inode slips past.  Two concurrent
``reserve()`` calls then both held the *exclusive* lock at the same
time.

Fix: sidecar lock file at ``budget.json.lock``, never replaced,
matching the pattern already in use by ``state.py`` and
``worktree.py``.  ``BudgetLedger.lock_path`` exposes it; ``reserve()``
opens the sidecar, not the state file.

This supersedes one bullet of the original *Deferred* list
("lock carrier might lose the inode on os.replace") which the prior
ADR omitted; future audits should treat the sidecar rule as the
canonical write-under-lock pattern across ``_bmad-output``.

### In-flight reservations did not count toward the cap

``_check_caps`` was a per-call check looking only at
``state.spent_usd + est_usd``.  Two parallel calls each below cap
(e.g. 0.06 + 0.06 vs cap 0.10) sailed through, ran, and only tripped
at settle — by which point both had already spent.

Fix: sum ``state.reservations[].est_usd`` (and ``est_turns``) into
the cap math.  Direct ``_check_caps`` unit tests bypass the lock
so the cap-math gap is reproducible even when concurrency happens
to serialise.  ``7.cap check counts outstanding reservations`` in the
validation harness exercises the same scenario.
