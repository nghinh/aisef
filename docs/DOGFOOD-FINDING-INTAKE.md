# Dogfood finding intake — LedgerLock on AISEF 1.7.2 + OpenCode

A classification procedure, nothing more. It exists so that whatever the
independent LedgerLock run returns is recorded in one shape, classified by one
rule set, and routed to the right decision — without anyone fixing anything on
the way in.

What this run is and is not:

- it is an AI-operated dogfood run of a real project through the **public**
  `aisef==1.7.2` with OpenCode;
- it is **not** G6. Nothing it produces is external-human validation, and
  nothing here touches `closure-evidence/external-validation/1.7.2/`;
- it does not change the product: 1.7.2 is frozen. A finding that needs a
  product change is a decision for the owner, not a patch.

## 1. One record per finding

Records live at `closure-evidence/dogfood/ledgerlock/F-<n>.json`
(`EVIDENCE_ONLY` under `docs/closure-gate.json#planes`, so committing them moves
no gate). Fields, all required; *unknown* is written as `"unknown"`, never
omitted:

| field | content |
|---|---|
| `id` | `F-1`, `F-2`, … in order of discovery |
| `observed_at` | ISO timestamp of the observation |
| `reproduction` | exact commands from a clean state, in order, with the working directory |
| `project_commit` | the LedgerLock commit or candidate SHA the observation was made on (`git rev-parse HEAD` in the project; the story's frozen candidate from `_bmad-output/evidence/<story>.jsonl` when it is a story) |
| `aisef_version` | `aisef --version` from the venv that ran it (must be `aisef 1.7.2`; if not, the run is not this intake) |
| `client` | `opencode` version (`opencode --version`), model, and route/alias if configured (`route.*` keys in `.ai/config.json`) |
| `gate_or_evidence` | the gate check, guard, probe or evidence file involved (`aisef.control.gate.CHECK_NAMES` name, guard kind, `_bmad-output/...` path) |
| `observed` | what happened, in the words of the log or the output — quote, do not paraphrase |
| `expected` | what the documentation or the gate's own statement says should happen, with the document and section |
| `hidden_oracle` | `detected` / `not_detected` / `not_applicable` — whether the run's hidden oracle (the project's own independent check, outside AISEF) caught the same behaviour |
| `severity` | P0–P3 on the ladder of `docs/EXTERNAL-VALIDATION-v1.1.0.md` § Finding classification |
| `class` | one of the ten classes in §2 |
| `affects_v1_closure` | `yes` / `no` / `unresolved` — `yes` only for a P0/P1 that is a framework defect or a false-negative gate |
| `requires_product_change` | `yes` / `no` / `unresolved` — `yes` when the fix would touch a `PRODUCT_AFFECTING` path |
| `evidence` | paths of logs, evidence JSONL lines, screenshots, or the session id in OpenCode's store |
| `register` | the `D-nnn` id if and when it enters `docs/DEFECT-REGISTER.json`; empty until then |

## 2. Classes

Exactly one per finding. When two fit, record both candidates under
`class_candidates`, set `class` to `UNRESOLVED`, and take it to the owner.

| class | meaning | typical consequence |
|---|---|---|
| `FRAMEWORK_PRODUCT_DEFECT` | AISEF code or packaged data behaves contrary to its own documented or stated behaviour; the fix is in `aisef/` | register; P0/P1 → **STOP, owner** (§4) |
| `FRAMEWORK_ASSURANCE_DEFECT` | a test, recorder, closure/validation procedure, template or evidence tooling is wrong; the product behaved as documented | register; fix is assurance-plane; no release |
| `PLANNING_DEFECT` | the planning artifacts (PRD, architecture, epics, stories, write scopes, criteria) produced by the run are wrong in a way the machine gates accepted | record; check whether a machine gate *should* have caught it (→ `FALSE_NEGATIVE_GATE` candidate) |
| `CLIENT_ADAPTER_DEFECT` | the OpenCode adapter, plugin or stream parsing misreads or mishandles the client (guard not wired, turn cap not enforced, cut session misclassified) | register; it is product code (`aisef/clients/`) → treat as `FRAMEWORK_PRODUCT_DEFECT` for consequences |
| `MODEL_FAILURE` | the model produced wrong code, ignored instructions, emitted an unparseable tool call, or looped — and AISEF classified it correctly (blocked, cut, infra, max_turns) | record as run evidence; not a framework defect |
| `PROJECT_REQUIREMENT_AMBIGUITY` | LedgerLock's own requirements admit more than one reading and the run picked one | record; not a framework defect unless the PRD gate should have flagged an open question |
| `ENVIRONMENT/INFRA` | Docker, network, credentials, provider outage, disk, OS, tool missing on the machine | record; check that AISEF labelled it (`UNRUNNABLE`, `degraded`, `infra`) rather than as a product failure — if it did not, that is a `FRAMEWORK_PRODUCT_DEFECT` |
| `FALSE_POSITIVE_GATE` | a gate or guard blocked something that was correct (a false block) | register; severity by cost to the run; product fix if the rule is code |
| `FALSE_NEGATIVE_GATE` | AISEF marked a story or the project PASS/done while behaviour is wrong — especially when the hidden oracle detected what the gate did not | register with `false_pass=true`; **STOP, owner** (§4) |
| `NOT_A_FRAMEWORK_DEFECT` | the project's implementation was wrong and AISEF **correctly** blocked or reported it | record as positive evidence for the framework; no register entry |

## 3. Procedure

1. Write the record (§1) from the raw material before forming an opinion.
2. Reproduce once from a clean state with the recorded commands; if it does
   not reproduce, say so in `reproduction` and keep the record.
3. Classify (§2). Two candidates → `UNRESOLVED` → owner.
4. Decide `affects_v1_closure` and `requires_product_change` from the class
   and the plane of the paths a fix would touch — never from how inconvenient
   the answer is.
5. If it enters the register: one row in `docs/DEFECT-REGISTER.json` (with
   `false_pass`, `check`, `taxonomy`) and one row in `docs/FAILURE-TAXONOMY.md`
   in the same commit, as the repository's rule says. The register is
   `EVIDENCE_ONLY`; the taxonomy is `DOCUMENTATION`; neither moves a gate.
6. Do not fix. Not the project, not the framework, not the documentation, not
   "just the typo". A fix is a decision (§4).

## 4. Stop conditions

- **P0/P1 `FRAMEWORK_PRODUCT_DEFECT` or `CLIENT_ADAPTER_DEFECT`** in AISEF
  1.7.2: STOP, return to the owner with the record. If confirmed, it is a new
  patch release (product identity moves) and a new G6 bundle and execution;
  the owner decides.
- **`FALSE_NEGATIVE_GATE`** at any severity where the hidden oracle proves
  important behaviour wrong while AISEF said PASS: STOP, return to the owner.
  This is the class the framework exists to prevent, and it is registered with
  `false_pass=true` so G2.4a can read it.
- **`UNRESOLVED` class**: return to the owner with both candidates.

Everything else is recorded and reported in the batch summary; the run
continues.

## 5. What counts as positive evidence

A finding of class `NOT_A_FRAMEWORK_DEFECT` — LedgerLock's code was wrong and a
gate, guard or reviewer blocked it with the reason on disk — is evidence *for*
the framework and is reported as such, with the same record shape, so that the
positive and negative observations of the run are counted the same way.

## 6. Batch summary

When the run ends (or the owner asks), one table: id · class · severity ·
hidden oracle · affects closure · requires product change · register id. Counts
per class. Any STOP condition raised is listed first. The summary is a derived
record (`closure-evidence/dogfood/ledgerlock/SUMMARY.md`); the per-finding
records are the evidence.
