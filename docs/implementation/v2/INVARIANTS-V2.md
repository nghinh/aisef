# AISEF V2 invariants I–IX (RFC §4, F10)

Rendered from `aisef2/invariants/registry.py` by `validation/v2/invariants_doc.py` — edit the registry, not this file; `register()` refuses a registry this document has drifted from. Every invariant is armed in every tier below before the tier's first test module is imported; all are uncontainable: `InvariantError` derives from `BaseException` and every broad kernel `except` boundary re-raises it (`validation/v2/except_boundaries.py`).

**Tiers:** `tests/v2`, `tests/v2/conformance`, `tests/v2/p0`, `tests/v2/p1`, `tests/v2/p2`, `tests/v2/p3`, `tests/v2/p4`, `tests/v2/p5`, `tests/v2/plan`

| # | invariant | RFC | mechanism | kind | reference | enforces |
|---|---|---|---|---|---|---|
| **I** | Requirement Authority | §4 row I | `I.approval-binds-both-hashes` | code | `aisef2.product.approval:require_approved` | a contract is compiled only with a ContractApproval binding the requirement hash and the contract hash |
|  | |  | `I.binding-problems` | code | `aisef2.product.approval:binding_problems` | an edited requirement or contract no longer matches its approval |
|  | |  | `I.no-prose-control` | static-rule | `kernel_static_checks:NO_PROSE_CONTROL` | no kernel control path reads Requirement.text or a rationale |
|  | |  | `I.sealed-record` | code | `aisef2.probe.protocol:ProbeRecord` | authority derives from admission: a record's digest binds it; an edited record is a new record |
| **II** | Semantic Determinism | §4 row II | `II.harness-owned-probes` | code | `aisef2.probe.protocol:run_probe` | verdicts come from harness-owned probes on a ProductProofSpec, never from developer test topology |
|  | |  | `II.seq-not-time` | static-rule | `kernel_static_checks:NO_TIME_IN_PROJECTIONS` | no projection reads wall-clock time; control folds over seq |
|  | |  | `II.from-scratch-fold` | code | `aisef2.journal.fold:fold` | every control state is the pure fold of the journal prefix |
|  | |  | `II.one-signal-authority` | static-rule | `kernel_static_checks:ONE_SIGNAL_AUTHORITY` | no control on an event bus: one authority for controller signal provenance |
|  | |  | `II.deterministic-child-env` | code | `aisef2.probe.protocol:ExecutionEnv` | a probe runs with what the harness gives it: interpreter, timeout, required enforcement |
|  | |  | `II.runspec-hash` | code | `aisef2.runtime.runspec:runspec_hash` | the resolved run identity is a content hash of capabilities, grade and settings |
| **III** | Independent Evidence | §4 row III | `III.verifier-scope` | code | `aisef2.runtime.story_scope:StoryScope` | the verifier's resources are acquired by its own scope and released in reverse order |
|  | |  | `III.bound-result` | code | `aisef2.probe.protocol:bound_result` | a decision reads a sealed ProbeRecord bound to the spec, the revision and the enforcement level |
|  | |  | `III.result-only-through-binding` | static-rule | `kernel_static_checks:RESULT_ONLY_THROUGH_BINDING` | no kernel module reads a bare probe result |
|  | |  | `III.confinement-from-env` | code | `aisef2.probe.protocol:ExecutionEnv` | confinement is the typed ExecutionEnv the harness builds, never a passable developer parameter |
|  | |  | `III.developer-tests-are-not-product-proof` | code | `aisef2.quality.adequacy:assemble` | developer tests assemble engineering-test adequacy; nothing there reaches a product proof |
| **IV** | Typed Ownership | §4 row IV | `IV.taxonomy` | code | `aisef2.control.owner:classify` | owner and retryability are read from the typed taxonomy alone |
|  | |  | `IV.charge-from-journal` | code | `aisef2.control.budget:charge` | a retry charges the failure owner's own budget, decided from the journal projections |
|  | |  | `IV.retryable-only-in-taxonomy` | static-rule | `kernel_static_checks:RETRYABLE_ONLY_IN_TAXONOMY` | retryability is fixed once, in the taxonomy |
|  | |  | `IV.no-side-retry-counter` | static-rule | `kernel_static_checks:NO_SIDE_RETRY_COUNTER` | budgets are projections, never side counters |
|  | |  | `IV.adequacy-charges-only-inadequate` | code | `aisef2.quality.adequacy:assemble` | INCOMPLETE, UNRUNNABLE, ENVIRONMENT and INTEGRATION never charge the developer |
| **V** | Reproducible Qualification | §4 row V | `V.comparable` | code | `aisef2.runtime.runspec:comparable` | comparability requires the same capability tuples, grades and enforcement identity |
|  | |  | `V.runspec-hash` | code | `aisef2.runtime.runspec:runspec_hash` | the same frozen inputs give the same run identity |
|  | |  | `V.capability-identity` | code | `aisef2.runtime.capability:CapabilityIdentity` | a capability is identified by grade and binding tuple, never by a label alone |
|  | |  | `V.capability-resolved` | code | `aisef2.runtime.runspec:RunSpec.resolved` | the resolved capabilities and run identity are journaled (capability/resolved, run/spec-resolved) |
| **VI** | Immutable Provenance | §4 row VI | `VI.full-sha` | code | `aisef2.probe.protocol:RevisionRef` | a revision is a full 40-hex SHA, never a name or an abbreviation |
|  | |  | `VI.revision-in-runspec` | code | `aisef2.runtime.runspec:resolve` | the run's source revision is the full SHA |
|  | |  | `VI.journal-append-only` | code | `aisef2.journal.format2:JournalWriter2` | the journal has no update or delete verb; seq is the index |
|  | |  | `VI.record-digest` | code | `aisef2.probe.protocol:ProbeRecord` | verdict identity fields are sealed by record_digest |
|  | |  | `VI.semantic-hash` | code | `aisef2.product.spec:ProductProofSpec` | a proof spec carries its semantic_hash |
|  | |  | `VI.frozen-artefacts` | checker | `validation/v2/freeze_manifest.py:check` | a frozen artefact that drifts from the manifest identity is detected |
| **VII** | No Prose As Control State | §4 row VII | `VII.flatten-to-unknown` | code | `aisef2.control.owner:flatten` | a value from outside the taxonomy becomes UNKNOWN, the original kept as data |
|  | |  | `VII.typed-classify` | code | `aisef2.control.owner:classify` | an untyped code is refused, never mapped by its text |
|  | |  | `VII.no-prose-control` | static-rule | `kernel_static_checks:NO_PROSE_CONTROL` | no kernel control path reads prose |
|  | |  | `VII.no-raw-verdict-routing` | static-rule | `kernel_static_checks:NO_RAW_VERDICT_ROUTING` | control routes on the derived ContractSatisfaction, never on a raw verdict |
|  | |  | `VII.typed-collection-causes` | code | `aisef2.quality.test_execution:classify` | a runner's report is read as typed causes, never as prose |
| **VIII** | Memory Is Context, Never Evidence | §4 row VIII | `VIII.evidence-admission` | code | `aisef2.invariants.evidence:admit` | an evidence field admits only a harness-produced typed record; context is refused |
|  | |  | `VIII.evidence-field` | code | `aisef2.invariants.evidence:EvidenceField` | the typed field that carries evidence, admitted on construction |
|  | |  | `VIII.journal-event` | code | `aisef2.journal.event:Event` | a harness-produced record: typed, JSON-lossless, validated at the append site |
| **IX** | No Developer Artefact Is Executed At The Parent Revision | §4 row IX | `IX.candidate-only-execution` | static-rule | `kernel_static_checks:CANDIDATE_ONLY_EXECUTION` | engineering-quality code names no parent revision and drives no git |
|  | |  | `IX.no-developer-artefact-at-parent` | static-rule | `kernel_static_checks:NO_DEVELOPER_ARTEFACT_AT_PARENT` | no kernel module runs developer artefacts against a revision, and none imports the V1 gates |
|  | |  | `IX.probe-refuses-test-artefacts` | code | `aisef2.product.contract:names_test_artefact` | a probe input naming a developer test artefact is refused |
|  | |  | `IX.probe-api` | code | `aisef2.probe.protocol:run_probe` | the probe API takes a spec, a revision and an env: no developer path, command or test |
|  | |  | `IX.candidate-side-vacuity` | code | `aisef2.quality.vacuity:evaluate` | the only engineering-quality counterfactual runs at the candidate, never at the parent |

## Uncontainable

| mechanism | kind | reference | enforces |
|---|---|---|---|
| `all.invariant-error-is-base-exception` | code | `aisef2.errors:InvariantError` | derives from BaseException: no `except Exception` boundary can hold it |
| `all.except-boundary-audit` | checker | `validation/v2/except_boundaries.py:check` | every broad kernel except boundary re-raises it or cannot catch it; unknown patterns fail closed |
