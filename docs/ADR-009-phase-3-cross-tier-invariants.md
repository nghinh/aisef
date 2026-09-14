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

## The four semantic issues (reconstructed 2026-09-12)

**All four closed 2026-09-14.**  O1 — reviewer qualification scored over 145
recorded sessions.  O2 — `Behavior.gap_kind`, with the repair queue routed by
kind.  O3 — the blast-radius weight calibrated, both error rates reported, left
at 0 with the reason.  O4 — `aisef cost`, spend attributed to outcomes.  Each
subsection below carries its own closure note and measurement; the statements of
the issues are left as they were written so the reader can see what moved.

**Correction 2026-09-14 — this document broke its own rule.**  Two sentences in
this section outlived the closures and contradicted the headline above.  Kept
verbatim, because a correction that deletes the old text hides what moved:

> O3 closed on 2026-09-14; its measurement is recorded below under *Closed — O3*.
> Three remain: O1, O2, O4.

> **Status 2026-09-14: O1 is closed with its measurement below; O2–O4 remain
> open.**  The section heading still says four because that is the list as
> reconstructed; the count of *open* items is three.

Each was true when it was typed and stale by the time the next branch merged:
the four closures landed from **parallel worktrees** on one day, so every
sentence counting the survivors was counting a number only its own branch could
see.  Neither holds now.  **Zero remain**, and the list this section's own rule
demands is the four subsection headings below, all four marked CLOSED.  What
settles it is code on disk, not this paragraph:

```
python3 -c "import aisef.control.reviewer_qual"                          # O1 → silent: the scorer exists
python3 -c "from aisef.control.ledger import Behavior, gap_kind_counts"  # O2 → silent: kind + counts exist
grep -n 'story.verified_touched_weight' aisef/config.py                 # O3 → 4 lines: default, type, and the range check
python3 -m aisef.cli cost --help                                        # O4 → usage: aisef cost [-h] [--out OUT] [--project PROJECT]
```

Worth recording rather than quietly fixing: the rule holds only if something
re-reads it, and nothing does.  Prose is the one tier in this repo with no
guard.  The config-key count in `STABILITY.md` is pinned to `len(DEFAULTS)` by
`tests/test_meta.py::TestConSoTrongTaiLieuKhopNguonDocDuoc` and cannot drift; a
sentence of the form "three remain" is checked by nobody, and drifted twice in
one day.

**Provenance, stated plainly.** The pre-Phase-2 audit that produced "seven
systemic issues" was never written to disk: neither this repository nor any
reachable session transcript contains the list.  The three transactional ones
are recoverable because they became code (findings, lease, budget).  The four
semantic ones (O1–O4, each its own subsection below; this read "O1, O2, O4
below and O3 under *Closed*" from `9244229` until 2026-09-14, naming a
*Closed* section that never existed as a heading) are a **reconstruction**
from evidence that *is* on disk — the owner
decisions of 2026-09-06, the calibration note that pinned the neighbour weight
to zero, the C11 conformance probe, and the cost figures in
`docs/STATUS-2026-09-05.md`.  They are not quoted from the original audit.  If
that list resurfaces, reconcile against this section and say which items moved.

The rule that produced this section: *a statement of the form "N items remain"
must carry the list, on disk, in the same document.*

Each item names the semantic question, why it had to wait for the transactional
seams, and the measurement that closes it.

*(A status line stood here saying "O1 is closed with its measurement below;
O2–O4 remain open".  It is quoted in full, with why it went stale, under the
correction above.  All four are closed.)*

### O1 — the reviewer's verdicts are not themselves qualified — **CLOSED 2026-09-14**

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

*Closed by*: `aisef/control/reviewer_qual.py` (the scorer) and
`tests/test_reviewer_qualification.py` (six judgement classes × the same three
controls, table read by AST through the **same** reader as the gate table,
`gate.controls_in`).  Recompute at any time — the corpus is on disk, no model
call is involved:

```
python3 -m aisef.control.reviewer_qual \
  ~/Downloads/projects/{todo-cli,todo-e2e,todo-oc,todo}/_bmad-output
```

**The corpus.** 145 recorded reviewer sessions (`tool_run review` in
`_bmad-output/evidence/<story>.jsonl`) across the four dogfood projects,
2026-09-08 → 2026-09-13, every one a real client session (`ses_…`).  Which
client and model produced each session is **not** recorded — `agent_run.detail`
carries `model: ""` and no client field, and `todo-oc` has both a
`.claude/settings.json` and a `.opencode/plugin` on disk — so these rates are
across clients, not per client.  Recording client/model on `agent_run` is the
cheap fix that would let the next pass split them.  The 146
files under `reviews/` are a *smaller* corpus than this: 71 of them are reviewer
reports (the other 75 are security reports, retries included), and a re-run
overwrites the file while the evidence log keeps every session.

**Measured, 2026-09-14.**

| | count | rate |
|---|---|---|
| judgements scored | 127 of 145 | undecided 18 (**12.4 %**) |
| reviewer blocked | 57 | **false block 6 = 10.5 %** (lower bound) |
| reviewer passed | 70 | **miss 27 = 38.6 %** |
| blocks resting on the judge's word alone | 21 of 57 (36.8 %) | todo-e2e: 15 of 17 |
| same-tree consecutive pairs | 20 | **11 reversed the verdict (55 %)** |

*Direction of the disagreement*: 27 misses against 6 false blocks — C11's single
observation ("cổng máy bắt, người máy không") is the **common** direction, by
roughly 4.5 to 1.  The reviewer is far more likely to pass a defective candidate
than to block a sound one.

*Test–retest*: of 20 consecutive pairs where `git diff` between the two
candidates is empty, 11 changed verdict — 6 `block → pass`, 5 `pass → block`.
On identical bytes the judge contradicts itself more often than it repeats
itself.  This is the number that needs no convention: the other two rates
depend on attributing the error to the earlier judgement of a reversed pair.

*Ground truth, and its limits.* A false block needs positive evidence of
reversal, read from the project's **git repo**, not from harness bookkeeping:
either the next session passed on an identical tree (the same candidate commit,
or two commits `git diff` finds no difference between), or it passed while
`git diff` never touches any file the blocking findings named (and no changed
file is named in their bodies either).  All six measured here are the first
kind, and all six are the *same commit* — the second session re-read the exact
build the first one blocked.  Both need a next session and
two resolvable commits, so 10.5 % is a floor, not an estimate.  An earlier pass
of this measurement trusted `file_change` events instead of git and reported
16 false blocks (28 %); todo-e2e/STORY-02-02 showed why that is wrong — the
second developer attempt recorded no `file_change` at all, yet `git diff`
between the two candidates changes `js/app.js`, the exact file the block named.
A miss needs a check that says the *candidate* is defective: `FAILED` only
(`UNRUNNABLE` means "could not run"), and not the `FAILED` reasons that are
themselves evidence gaps — 17 of 44 `tests verify story` failures say "no test
run at candidate" or "nothing to verify at parent SHA", and counting those
would have inflated the miss rate from 38.6 % to 48.6 %.  The 27 misses are
20 nop-control failures ("tests verify nothing — still green without story
code"), 5 preservation regressions, 3 self-reversals, 1 candidate whose test
suite was red.  Read strictly — dropping the three misses whose only failing
check is a *screen* comparison a read-only reviewer cannot run — the miss rate
is 34.3 %; the honest statement is **34–39 %**.

*One correction to §1 above.* "Two findings raised against the same defect
produce the same id, regardless of how the agent rewrites the wording" is not
what `_digest` does: `body` is part of the identity, so re-wording changes the
id.  `Finding.id` collapses verbatim restatements only; the repo's place-key
(`implement._finding_key`: tag + file + line) is what collapses re-wordings,
and it is the one that fixed lỗi 141.  Every "deduped" count here is therefore
also a lower bound on how much restatement there was.

### O2 — the ledger records that a behaviour is a GAP, never what kind of gap — **CLOSED 2026-09-14**

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

*Closes when*: `Behavior.gap_kind` exists with the three values, the repair
queue routes each kind to a different action (story / test-only story /
harness metadata fix), and `aisef issues` reports the three counts separately.

**Closed 2026-09-14** — `Behavior.gap_kind` (spelled `Behaviour.gap_kind` in
this section until 2026-09-14; the class on disk is `Behavior` —
`grep -n '^class Behav' aisef/control/ledger.py`) is a property projected from
the reason sentence the ledger already writes, so `ledger.json` gains no
hand-writable field and rebuild-from-evidence still reproduces it.  Measured
over 167 behaviours in four corpora: 40 `unbuilt`, 4 `untested`, 5 `untraced`.
Those 5 are every criterion of one story whose test reporter was not installed —
before this, `improve` would have opened **five paid repair stories for one
unconfigured reporter**.  One correction to the item as written above: the case
it describes — behaviour and test both present, only the trace tag missing — is
**not** derivable from recorded evidence, because deciding it requires reading
test bodies.  It has 0 instances on disk, and measuring it at all needs the
reviewer's trace verdict recorded machine-readably first.  Measurements in
[`docs/handoff/o2-gap-kind.md`](handoff/o2-gap-kind.md).

### O3 — preservation is scoped by file, not by behaviour — **CLOSED 2026-09-14**

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

**Correction (2026-09-14, bug 155 — the rollup defect is now fixed).**  The
paragraph above stands as what the measurement saw; what it filed as an artifact
was a real defect, and it has been repaired.  `_observe_tests` now judges a
requirement **once per test run** instead of once per story that covers it:
several stories may cover the same `FR-x`, and the requirement is green when any
story judged in that run has all its criteria green, so an absence in a later
story's own criteria can no longer erase evidence another story left in the same
event.  The absence keeps being recorded where it belongs — on that story's
criterion, as `untested`.  Re-running `validation/o3_preservation_radius.py`
unchanged: uncorroborated `REOPENED` entries **29 → 4** (todo-oc 5→0, todo-cli
5→0, todo-e2e 15→0, todo 4→4), while the 15 confirmed regressors and every number
in the calibration table below are unchanged — the fix removes false regressions
without inventing true ones.  The 4 that remain are one instant in `todo`
(STORY-02-02) where the runner never started (`tool not installed or cannot
load`), so no test name existed for any story: a different absence (`untraced`),
and a separate decision about whether a run that read nothing may flip a VERIFIED
requirement at all.

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


### O4 — spend is attributed to calls, not to outcomes — **CLOSED 2026-09-14**

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

**Closed 2026-09-14** — `aisef cost` (`aisef/control/attribution.py`) reports
it; measurements and the decomposition in
[`docs/handoff/o4-cost-per-outcome.md`](handoff/o4-cost-per-outcome.md).  Two
corrections to the item as written above.  (a) `e9` and `par` are **not on this
machine** (`ls /Users/nghinh/Downloads/projects` — `e9` and `par` absent; `find
/Users/nghinh -maxdepth 4 -type d -name e9 -o -name par` finds only caches), so
the 36x remains a historical claim, reproduced only as arithmetic over prose
records: $496/7 stories ÷ $5.79/3 stories = 36.7x, both means quoted from
`docs/STATUS-2026-09-05.md` and `docs/E4-COST-DECOMPOSITION.md`, neither
recomputable from evidence.  (b) The unit cannot be dollars on any corpus that
survives: the provider priced 0% of sessions in three of four, and 1 of 180 in
the fourth.  `aisef cost` therefore decides the unit from the evidence and
refuses to average a partial dollar record.

## Deferred

- ~~Budget cap values are surfaced in ``Config`` defaults but not yet
  validated against the per-project ledger at startup (a project
  might set ``run.cost_cap_usd=0.50`` even when prior runs already
  exceeded that).  The next iteration adds a "set down" hook in
  ``aisef doctor``~~ — **done 2026-09-14.**  ``aisef doctor`` now carries the
  check ``budget cap above recorded spend``: it compares
  ``run.cost_cap_usd`` / ``run.turn_cap`` against ``spent_usd`` /
  ``spent_turns`` in ``_bmad-output/budget.json`` and names both numbers.
  Four distinct states, not two: no cap configured prints nothing and never
  opens the ledger (the guard short-circuits there, so the check must not make
  an unconfigured project pay the I/O); cap above spend passes; cap **at or
  below** spend fails required — at equality every next call already exceeds —
  and the message says the next paid call is refused before it dispatches, so
  the operator reads it as their own number rather than as a framework bug;
  no ledger yet is ``○``, neither pass nor fail, because nothing can be
  compared.  The check is read-only, including the equality case: it never
  takes the sidecar lock and never writes the ledger — ``run`` owns it.
  Pinned by ``TestDoctorTranNganSachSoVoiSoChi`` in ``tests/test_doctor.py``,
  one test per state plus one that asserts the ledger bytes and the
  ``_bmad-output`` listing are unchanged after a ``doctor`` run.
- ``mockup_verify`` derives ``run_id`` from
  ``artifact_root / story_id``; flows where one story runs against
  multiple candidate branches (re-verify across rebases) need a
  per-branch run id.  Not urgent: ``ready_with_identity`` is
  fail-closed when the run id mismatches.
- ~~The same-UID same-filesystem hostile-simulator test
  (``_uid_filesystem_race``) was documented in the audit but not
  implemented~~ — **done 2026-09-13, this bullet corrected 2026-09-14.**
  The stress test exists as ``tests/test_lease_stress.py``, which cites this
  deferral in its own docstring and spawns real subprocesses rather than
  threads (``flock`` grants by open file description, so two threads in one
  process can both win where two processes cannot). The lease file uses
  ``os.O_CLOEXEC`` plus ``flock_ex_nb``; on a kernel that hands out different
  UIDs to different processes ``flock`` semantics still differ, and that
  cross-UID case remains unmeasured — the test covers same-UID only, which is
  what the bullet asked for.

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
