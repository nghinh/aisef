# Post-1.0 Roadmap

## Experimental memory follow-up (2026-09-11)

Local scoped advisory memory is implemented but default OFF. [P0/P1/P2 research plan](MEMORY-RESEARCH-PLAN.md), [ADR-007](ADR-007-scoped-advisory-memory.md), [operational guide](MEMORY.md), [validation report](MEMORY-VALIDATION.md). Pending: independently reviewed security hardening, verified OpenViking protocol adapter, authorized paired long-horizon real-agent efficacy (primary repeated-error rate), signed promotion/global sharing. Scripted retrieval success is not an enablement criterion.

Written 2026-09-08, after v1.0.0 release. Items prioritized by evidence
from dogfood runs, conformance, and known limitations — not by feature wish.

---

## Cross-tier invariants (2026-09-12)

Three of the seven systemic issues surfaced in the pre-Phase-2 audit
were transactional defects that are now closed: structured findings
(anti-goalpost reviewer), candidate-bound dev-server identity lease,
and in-flight budget reservation.  Two follow-up defects in the
budget seam were caught by the wire-up harness on the same day and
closed by switching the lock carrier to a sidecar and counting
in-flight reservations in the cap math.  See
[ADR-009](ADR-009-phase-3-cross-tier-invariants.md#follow-up-two-cross-tier-defects-in-the-budget-seam).
The other four issues are *semantic* and depend on these being
correct first.  They are now written down — reconstructed from
on-disk evidence, with that provenance stated — in
[ADR-009 § Open](ADR-009-phase-3-cross-tier-invariants.md#open--the-four-remaining-semantic-issues-reconstructed-2026-09-12):
reviewer verdicts are not themselves qualified (O1), the ledger does
not record what *kind* of gap a GAP is (O2), preservation is scoped by
file rather than by behaviour (O3), and spend is attributed to calls
rather than to outcomes (O4).  Each carries the measurement that
closes it.

## 1. External user validation

**Problem:** v1.0.0 shipped without any external user running the framework
independently. All evidence is internal.

**Evidence:** ADR-006 §2 documents the chicken-and-egg: users won't adopt
a framework that never ships.

**Expected value:** Confidence that the harness works outside its creator's
mental model. Real friction points surfaced.

**Proposed solution:** Publish clear onboarding docs, share with 1–2 trusted
teams/developers, collect structured feedback.

**Verification:** At least 1 project run end-to-end by someone who did not
build the framework. Record their setup time, friction points, gate pass rate.

**Priority:** P0 — the single most important post-1.0 activity.
**Effort:** Low (framework side); depends on finding willing users.
**Risk:** No volunteers; framework assumptions don't hold outside author's projects.
**Release target:** v1.1.0

---

## 2. Stronger credential isolation (local provider)

**Problem:** Local sandbox provider honestly reports `unsupported` for S1–S4.
Docker works but adds setup friction.

**Evidence:** `tests/sandbox_conformance.py` — Docker 5/5, Local 1/5.
Every local run exposes the host's credentials to the agent.

**Proposed solution:** Investigate `unshare` (Linux) or `sandbox-exec`
(macOS) for lightweight local isolation without Docker. Alternatively,
document that Docker is required for credential-sensitive projects.

**Verification:** S1–S4 pass on local provider, or explicit documented
decision that Docker-only is acceptable.

**Priority:** P1 — security gap, even if honestly documented.
**Effort:** Medium (OS-specific sandboxing is non-trivial).
**Risk:** macOS `sandbox-exec` is deprecated; Linux `unshare` needs root.
**Release target:** v1.2.0

---

## 3. OpenCode + Serena write-scope interop

**Problem:** OpenCode's Serena plugin writes `.serena/.gitignore`,
`.serena/project.yml` into worktrees. These are outside stories' declared
`write_scope`, so the harness correctly rejects the candidate.

**Evidence:** Dogfood par-opencode run — all 3 stories failed because of
this. The harness behavior is correct; the agent ecosystem is the issue.

**Proposed solution:** Options:
  (a) Auto-add `.serena/**` to `write_scope` when client is OpenCode.
  (b) Add a `write_scope_ignore` config to exclude infrastructure files.
  (c) Document as agent-side limitation; wait for Serena fix.

**Verification:** OpenCode dogfood run completes with stories passing.

**Priority:** P1 — blocks OpenCode from completing dogfood runs.
**Effort:** Low (option a or b is a few lines).
**Risk:** Option (a) is client-specific special-casing; option (b) is generic
but might mask real scope violations.
**Release target:** v1.1.0

---

## 4. Harder benchmark / challenge set

**Problem:** Current bench suite is 15+ bug-fix tasks from a single project
(the framework itself). Not diverse enough to make strong claims.

**Evidence:** Bench report v0.3.0 — 96 runs, but all Python, all on aisef.

**Proposed solution:** Add tasks from:
  - Different languages (JavaScript/TypeScript via par, Go, Rust)
  - Different task types (feature addition, refactoring, security fix)
  - External open-source repos with known-good fixes as ground truth

**Verification:** Bench suite covers >= 3 languages, >= 3 task types, >= 30
tasks.

**Priority:** P2 — improves evidence quality, not blocking anything.
**Effort:** Medium (curating good tasks takes judgment).
**Risk:** Ground-truth quality; tasks that are too easy or too hard.
**Release target:** v1.2.0

---

## 5. Distributed execution

**Problem:** Single-machine only. No multi-machine orchestration for large
projects with many epics.

**Evidence:** ADR-006 §3 deferred this. `worktree.py` has the merge lock
primitive but no cross-machine coordination.

**Proposed solution:** Define a coordination protocol (queue + lock service),
implement worker nodes that pull stories from the queue.

**Verification:** 2 machines, 1 epic, state merges correctly, no conflicts.

**Priority:** P3 — no user has asked for this; single-machine handles all
current workloads.
**Effort:** High (distributed systems correctness is hard).
**Risk:** Over-engineering without real demand.
**Release target:** v2.0.0 (if ever demanded)

---

## 6. Reliability / maintenance

**Problem:** No production telemetry. Bug reports come from dogfood and tests.

**Evidence:** 42 bugs found during dogfood (documented in DEEP-REVIEW).
Framework is stable but untested at scale.

**Proposed solution:** Track issues from external users (item 1). Fix based
on real reports, not speculative cleanup.

**Verification:** Issue tracker active, mean time to fix < 1 week for P0/P1.

**Priority:** P2 — becomes P0 once external users exist.
**Effort:** Ongoing, low per-issue.
**Risk:** No users = no reports = false sense of stability.
**Release target:** Continuous

---

## Non-goals

- **Large refactors** without evidence of friction.
- **Version bumps** for the sake of progress.
- **New features** not driven by user feedback or evidence.
- **Config key reduction** — already at 0 mandatory, 58 total with defaults.

## Lessons from MiMo-Code (2026-09-12)

[ADR-010](ADR-010-mimo-code-lessons.md) records a study of
[MiMo-Code](https://github.com/XiaomiMiMo/MiMo-Code) — an OpenCode fork with
persistent memory, `/dream` consolidation, `/distill` skill extraction, a
QuickJS tool-batching sandbox and a harness hand-off mechanism.

Three things landed: rate limits are no longer retried instantly, the retry
delay is read from what the provider says, and a ranking harness now exists for
memory retrieval. The ranking harness is the interesting one — it was built to
justify replacing AISEF's word-overlap scorer with BM25 and instead showed no
winner across two deliberately opposed datasets, so nothing was replaced.

Four candidates carry written measurement conditions and are not enabled:
evidence-backed memory consolidation, in-session stall detection, batched tool
execution, and MiMo as a third client (which stays closed until a memory
isolation test proves a fresh story cannot inherit a previous session's state).

Rejected with evidence from MiMo's own issue tracker: automatic checkpoints and
session resume (keep-alive loops, OOM at 6–20 GB), cross-tool transcript
ingestion, and a second canonical task state.


## Re-check trigger: `phases/implement.py` (2026-09-12)

The file is 2 581 lines. By this project's own splitting rule — split on
evidence of real friction, not on a line count — **not splitting is currently
correct**: no bug in the last three waves was caused by the file's size, and a
split would move code without fixing anything.

Splitting is not free either, so the decision gets a trigger rather than a
re-argument every release:

> If **three consecutive real bugs** land in `aisef/phases/implement.py`, split
> it — and split along the seam the three bugs share, not along a tidy one.

Bugs are counted from the numbered bug log in `CHANGELOG.md`. Three bugs in one
file is the point where "the file is fine" stops being a claim about evidence
and starts being a habit.
