# Phase 13 — targeted mutation testing of decision-critical kernel code

Tool: `validation/mutate.py` (stdlib; each mutant is one AST change at one site, run in its own copy of the
repository against the target's named tests; non-zero exit KILLS, exit 0 SURVIVES; `equivalent` entries are
reported separately and never count as survivors). Targets: `validation/mutation-targets.json` — 28 functions,
270 mutants (`--list`), operators CMP, NOT, ANDOR, BOOL, STR, VERDICT, INCR, RET, DROPCALL:

| area | functions |
|---|---|
| freshness / evidence validity | `identity.fresh`, `gate._stale_for`, `gate._latest_per_check`, `gate.verdict_recorded` |
| closure probes | `closure._is_ancestor`, `probe_review_and_security`, `probe_evidence_at_candidate` |
| approvals | `ApprovalStore.status`, `.content_hash`, `._upstream_stale` |
| leases / budget | `state.claim_is_live`, `StateStore.transition`, `budget._reservation_live`, `budget._check_caps` |
| ownership / processes | `ownership.classify`, `process_owner.reap`, `process_owner.survivors` |
| judgment / routing | `implement.deadlock_reason`, `_same_complaint`, `_paths_outside`, `finding_bound`, `Verdict.bound_blocking`, `structured_plan_defects`, `_verifier_budget_cap`, `_absent_stages`, `nop_deadlock` |
| adapters / tools | `stream.exit_status_of`, `tools.unrunnable_reason` |

Rule (owner directive): **no surviving P0/P1-significant mutation is acceptable.** Every survivor is classified:
(a) KILLED by a new deterministic test that names the mutant's site and the invariant it would have broken, or
(b) EQUIVALENT — the mutant cannot change any observable decision — listed under `equivalent` with the reason, or
(c) NOT SIGNIFICANT — the mutant changes only a message, a log line or an ordering with no control effect; listed
with the reason, and counted separately. Nothing is left unclassified. The run is executed with no other CPU-heavy
job on the machine (a timing failure would count as a kill and hide a survivor). Results:
`closure-evidence/hardening/mutation-results.json`; the survivor classification is appended to this file.
