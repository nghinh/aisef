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
