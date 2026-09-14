# ADR-007 — Scoped advisory long-term memory

Date: 2026-09-11. Status: **FROZEN, default OFF** (this header read
**EXPERIMENTAL, default OFF** until 2026-09-14; the *Addendum — frozen (2026-09-12)*
below changed the status two days earlier and the header was not followed up).
Research: [inspected sources and P0/P1/P2 plan](MEMORY-RESEARCH-PLAN.md).

## Decision

Preserve fresh sessions and all existing evidence/ledger/journal/gate authority. Add a dependency-free local provider for small, deterministic, source-linked memory records. Memory is context **never evidence**; present requirements/architecture and authoritative source always outrank recalled text. No memory event is a gate check, behavioral verification, or permission to change scope.

Adopt OpenViking's tiering, Graphiti's explicit validity/provenance, LangMem's storage-independent API and Letta's inspectability without importing their runtimes. Reject shared mutable agent identity, transcripts, autonomous promotion and external transmission. A real OpenViking adapter is deferred: retrieved API documentation establishes find/read/delete, not verified full schema-preserving lifecycle semantics. Report unavailable, optionally use explicitly configured local fallback with a visible reason, never label local results OpenViking.

## Contract

Provider: recall/get/put/update/forget/search/consolidate/health/stats. Store version 1, project identity bound to canonical local root, required taxonomy/lifecycle/trust and complete scope/provenance. IDs are deterministic hashes. Forget removes payload and keeps a tombstone preventing recapture. Consolidation invalidates changed references, never upgrades unverified observations. Missing/corrupt/unknown schema fail closed without erasing data. Interprocess locked atomic writes, size limits and symlink/traversal rejection.

Taxonomy: decision, lesson, failure, trajectory, tool, codebase, preference, review_pattern, security_pattern, environment. Lifecycle: active, stale, superseded, revoked, unverified. Trust order: human, deterministic, gate, security, reviewer, landed, agent. Ranking is only relevance; it cannot validate an assertion. Agent records remain unverified. Reviewer/security receive neither agent-trust nor unverified observations. The reviewer-eligibility set is `REVIEWER_TRUST = {'gate','security','reviewer','landed','human'}`; `deterministic` alone never qualifies a record for reviewer/security even with a contract digest — that term is only a trust ranking hint, not a producer role. Active reviewer/security records additionally require a non-empty `contract_authority` digest (64-hex SHA-256 of the authoritative project files) captured at `make_record` time.

Every injectable record requires project, epic, story applicability, roles, paths, tools; provenance source reference/type/digest/time/origin story and candidate when applicable. Wildcard applicability must be explicit, never imply cross-project. Sources are safe local references, screened at write and recall; authoritative document digest changes invalidate records conservatively. No global storage in this release.

L0/L1 packets are bounded deterministically with IDs, source types, scores and audit metadata; L2 is explicit CLI retrieval. Optional packet is appended only when enabled and selected. Disabled mode does not read/write memory or alter rendered prompts. Sessions remain fresh. Capture distills deterministic outcomes linked to authoritative journal/evidence; it must distinguish verified-but-unlanded from landed and failed.

## Security and consequences

Local memory files are not an authentication boundary against an attacker controlling the same OS account. Regex screening is defense in depth, not a proof against semantic injection. Avoid raw transcripts and credential paths, minimize payloads, reject suspicious records at store and recall, and redact query/audit errors. Review independence remains a harness invariant. Corruption/unavailability is visible advisory failure, not a story gate failure.

Lexical retrieval is predictable but misses paraphrases. Conservative invalidation loses useful recall after benign edits. No remote/model calls or new dependencies. Default remains OFF until paired real-agent repeated-error measurements support enabling it. Retrieval-only scores do not satisfy that condition. Implementation and remaining gaps are tracked in the memory guide and benchmark report, not backfilled into historical ADRs.

## Implementation references (linking forward, not rewriting)

These references describe how the decision above is enforced today; the ADR itself is not modified retroactively.

- Operational behavior of the local provider, security boundary, capture pipeline and disabled-mode prompt contract: `docs/MEMORY.md`.
- Updated trust posture cross-checked against an independent-audit report, including exercised adversarial tests, ablations, precision/recall and unchanged 17 pre-existing lint findings: `docs/MEMORY-VALIDATION.md`.
- Research and verified upstream `main` commit/release metadata used for the comparison table: `docs/MEMORY-RESEARCH-PLAN.md` (see § "Verified upstream metadata snapshot").

## Addendum — frozen (2026-09-12)

Status changes from **EXPERIMENTAL, default OFF** to **FROZEN, default OFF**.
The decision, contract and security posture above stand unmodified; what
changes is the investment policy, and only forward.

Why now. The enabling condition this ADR wrote for itself — "paired real-agent
repeated-error measurements" — has not been met in the year since, and two
things measured since argue against spending more on it before it is:

- The retrieval scorer was put on a bench built to replace it
  ([MEMORY-BENCH](MEMORY-BENCH.md), [ADR-010 §3](ADR-010-mimo-code-lessons.md)).
  BM25 and an IDF-weighted variant were measured against the current
  word-overlap scorer on two deliberately opposed datasets. No candidate won
  both. Nothing was replaced, and the honest reading is that ranking is not
  the binding constraint — having something worth recalling is.
- No external user has run the lifecycle end to end yet (tracking table,
  [DANH-GIA-360](DANH-GIA-360-2026-09-12.md) §6). A feature default-OFF with no
  external user generates no demand signal, so further work on it would be
  guesswork dressed as a roadmap.

What frozen means, concretely:

| | |
|---|---|
| Code | stays. `aisef memory` keeps working; the store format keeps its version |
| Default | stays OFF |
| Bug fixes | yes, if it breaks (bug 75's scope-comparison fix is exactly this case) |
| Security fixes | yes, unconditionally |
| New capability | no — no new providers, no new taxonomy, no ranking work |
| Deletion | no. Freezing costs a paragraph; deleting costs a migration, and the contract has no known defect |

Thaw condition, written now so it is not argued later: an external user asks
for it **or** a paired measurement on a real agent shows a repeated error the
memory would have prevented. Retrieval-only scores still do not count — that
was true when this ADR was written and the MEMORY-BENCH result is why it stays
true.
