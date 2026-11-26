# C-1 amendment A2′ — gate story binding and R-GATE completeness (owner ruling 2026-11-26, recorded 2026-11-26)

**Authority:** OWNER RULING 2026-11-26 (thứ tư) "C-1 AMENDMENT A2′ AND B2 EVALUATOR SOURCING" §1, issued through
the owner channel (baseline 86de73d8, recorded in `docs/v2.3/ACCELERATED-DELIVERY-PLAN.md` §7.4). Normative text,
verbatim:

> §1 **A2′ APPROVED** với điều kiện chấp nhận: schema f4 gate/check+gate/decision bắt buộc story_id non-empty, bind
> đúng attempt đang hoạt động (không phải chuỗi tùy ý), f1–3 nguyên vẹn byte+hành vi; completeness CHỈ cho
> passed:true trong scope = sau decision trước của cùng (gate, story_id) hoặc biên attempt đầu; từ chối cite
> duplicate/missing/cross-story/stale/invalid; cấm PASS rỗng bằng chứng; passed:false chỉ miễn completeness; ma trận
> test bắt buộc (C3 red-before, omit PASS/FAIL, multi-gate/story, C5 interleave, retry boundaries, E5 fault tails,
> story_id sai/cross-story/vacuous, A/R/F consistency, parity f1–3 + golden corpus); amendment dated scoped, KHÔNG
> viết lại design frozen; adversarial review độc lập TRƯỚC khi chấp nhận tích hợp; file pin nào thay đổi → tính
> transition chính xác + xin ủy quyền, không re-pin im lặng.

The amendment wording it approves (background + Phase-1 proof: `docs/v2.3/drafts/C-1-AMENDMENT-PROPOSALS.md`,
"A2 — CẬP NHẬT"), verbatim:

> A2′ (schema): In format 4, `gate/check` and `gate/decision` each gain required field `story_id` (non-empty
> string). Formats 1–3 never admit the field (CR-3). The kernel's `orchestrate/gate.py` writes it from the
> value it already closes over.
>
> A2′ (rule, replacing A2's proposed sentence): A format-4 `gate/decision` with `passed: true` MUST cite
> every `gate/check` carrying the same (`gate`, `story_id`) appended after the latest prior `gate/decision`
> of the same (`gate`, `story_id`) (after `run/begin` when none exists); refusal at append AND reconstruct
> naming event, seq and rule. A `gate/decision` with `passed: false` is EXEMPT from completeness — the E5
> contained-fault tail legitimately strands helper-emitted checks (evidence item 2) — and stays subject to
> R-GATE as frozen. The C3 attack dies for passing decisions (hiding a failed check refuses the decision);
> hiding a check under an already-failing decision changes no authority.

One refinement over the draft's parenthetical, taken from the ruling's own words ("the current attempt's decision
scope … or at the first valid attempt boundary"): when no previous (`gate`, `story_id`) decision exists the scope
opens at **the story's latest `story/begin`** (the current attempt's boundary), not at the draft's `run/begin`.
**Corrected justification (adversarial review F1, 2026-11-26 — the earlier parenthetical here was factually wrong
and is retracted):** the readings ARE distinguishable on hand-built journals (a prior UNDECIDED attempt's stranded
check sits before the latest begin: accepted under latest-begin, refused under run/begin). They are equivalent on
every KERNEL-WRITTEN journal for a different, verified reason: the kernel appends a decision in every attempt
(story_runner.py:449 precedes :457/:460) and every decision-skipping path raises out of run_story, so no later
same-story attempt can follow an undecided one. Authority impact of the divergence is bounded: the divergent
journal must still carry `failure/observed` + `story/retry`, and the same acceptance is reachable under any reading
by inserting one legal passed:false decision — no new authority is obtainable. **RESOLVED (owner ruling
2026-11-26, A2′ scope decision §1): OPTION A APPROVED** — the latest `story/begin` opens the first decision's
scope; subsequent decisions keep the decision-boundary rule. The ruling's mandated demonstration landed as
`tests/v2/test_v23_format4.py::A2OrphanAttempt` (4 legs): no silent second attempt exists (the frozen table
refuses `story/begin` out of ACTIVE at both sites), the orphaned check is uncitable from the new attempt
(R-GATE-CITE stale), the passing outcome requires the new attempt's COMPLETE evidence (partial new-scope citation
still refuses R-GATE-COMPLETE), and the orphan + `failure/observed` + `story/retry` remain visible in reconstruct
and in the journal bytes forever — orphaned checks cannot be silently converted into a successful authoritative
outcome. Demonstration SUCCEEDED; no counterexample.

## Scope (dated 2026-11-26; format 4 ONLY — formats 1–3 byte- and behavior-compatible)

| File | Change |
|---|---|
| `aisef2/journal/format4.py` | the A2′ schema and rules (below) |
| `tests/v2/test_v23_format4.py` | the required matrix (21 new tests; the 3 frozen R-GATE pins updated to the A2′ payload) |
| `closure-evidence/v2/v2.3/AUTHORITY-INVENTORY.json` + `validation/qualification/release_inventory.py` | per-era inventory regenerated (one new row, below) and its pin updated — recorded here, not silent |

**The frozen design files are NOT rewritten.** `docs/v2.3/drafts/FORMAT-4-DESIGN-DRAFT.md` (blob `41506829d2…`)
and `FORMAT-4-FREEZE-PACKAGE.md` stay byte-identical to the C-1 freeze record; the frozen transition table
(`aisef2/journal/transitions.py`, `TABLE_DIGEST 1107b689…`) is untouched — the binding is an A2′ *rule* that reads
the table, never a table edit. The kernel (`orchestrate/gate.py`, `story_runner.py`) is untouched: its `story_id`
hunk lands with the production writer flip (the flip stays gated on the ruling §5 install/signing gates and the
independent adversarial review), so **historical writers emit nothing new** — a `story_id` on a format-≤3 gate
event is refused by the sealed readers (pinned by test).

## Implementation summary (file:line at this landing)

- **A2′ (schema)** — `aisef2/journal/format4.py:170` (`_gate_schema`: the f3 base schema plus required non-empty
  `story_id`, extended at the f4 layer only) wired at `:190-191` into the f4 `SCHEMAS` override.
- **A2′ (rule, binding)** — `:284` (`_ATTEMPT_OPEN = {"BEGIN", "BEGIN_REFUSED", "ACTIVE"}`) and `:287`
  (`_gate_bound4`), registered for `gate/check` at `:388`. State derivation below.
- **A2′ (rule, completeness + citation validity)** — `:298` (`_gate4`, registered for `gate/decision` at `:389`):
  binding, then cross-story (`:314`) and stale (`:323`) citation refusals for BOTH verdicts, then the frozen
  R-GATE failed-cited-check refusal, then R-GATE-COMPLETE (`:334`) for `passed: true` only.
- Both sites share the one `validate` (`format4.py`), so every refusal lands at append (`JournalWriter4.append`)
  AND reconstruct (`format4.reconstruct`) with the same message; the test helper `refused` asserts both on every
  red case.

### The binding state set (derived, with citations)

`_ATTEMPT_OPEN = {BEGIN, BEGIN_REFUSED, ACTIVE}` — the frozen table's states between an attempt's `story/begin`
and the outcome move (`story/commit|retry|rollback`) that decides it. This is exactly the kernel's real emission
surface, verified 2026-11-26:

- the kernel has ONE gate id for every story and attempt: `GATE = "story"` (`orchestrate/gate.py:10`); every
  check/decision is attempt-scoped (`checks` initialised per attempt at `story_runner.py:226`, decided at `:449`);
- the resources check (`story_runner.py:244`) lands in **BEGIN** (after `story/begin` `:223`, before any
  admission);
- the admission check (`:263`) lands in **ACTIVE** or **BEGIN_REFUSED** — the sink's `story/admitted` precedes it
  (`plan/story_admission.py:168`);
- the E5 contained-fault tail (`:429-443`) appends its one stage row in whichever of the three states the fault
  left; the decision (`:449`) is appended before the `story/commit` (`:451`) / `story/retry` (`:457`) /
  `story/rollback` (`:460`) that moves the state out of the set.

A `story_id` outside this set (unknown story, decided/disposed/ended story, another attempt phase) is refused —
"an arbitrary story_id" in the ruling's words.

### Exact refusal strings added

- `R-GATE-BIND (A2'): {kind} at seq {N} names {story_id} in state {STATE}: a format-4 gate event binds to a story
  in an open attempt (BEGIN, BEGIN_REFUSED or ACTIVE)`
- `R-GATE-CITE (A2'): gate/decision at seq {N} of {story_id} cites {seqs}: a gate/check of another story is never
  this decision's evidence`
- `R-GATE-CITE (A2'): gate/decision at seq {N} cites {seqs}: stale — before this decision's scope, the events
  after seq {S} ({its previous gate/decision | the attempt boundary} of ({gate}, {story_id}))`
- `R-GATE-COMPLETE (A2'): gate/decision at seq {N} with passed true leaves gate/check {seqs} of ({gate},
  {story_id}) uncited in its scope: a passing decision cites every check of its gate and story`

Two of the ruling's refusals need no new string because a FROZEN rule already refuses them structurally, stated
here as-is (no second gate was added for either):

- **duplicate citations** — the Event invariant (`journal/event.py:78-80`): `{kind}: source_seqs cite earlier
  events, each once, in order` (fires at construction, both sites);
- **vacuous PASS** (zero citations) — the frozen citation-count rule (`journal/event.py _cites`, applied by f4):
  `gate/decision cites at least one gate/check` (it refuses the vacuous FAIL too). **invalid citations**
  (non-`gate/check`, wrong gate) stay the frozen cites rule's, as the ruling requires:
  `gate/decision cites {seqs}: not a gate/check with the same gate`.

## The negative-control matrix (all in `tests/v2/test_v23_format4.py`; module total 79 tests, all green)

Every RED row asserts the refusal at BOTH sites (append + reconstruct) through the `refused` helper, matching the
rule name and inspecting kind and seq content in the message.

| Test | Condition | Refusal shape | Verdict |
|---|---|---|---|
| `A2GateSchema.test_gate_check_without_story_id_refused` | pre-A2′ f4 `gate/check` payload (no `story_id`) — the schema's red-before/green-after; the pre-A2′ validator ACCEPTED it | `gate/check: fields missing ['story_id']` | RED (refused) |
| `A2GateSchema.test_gate_decision_without_story_id_refused` | pre-A2′ f4 `gate/decision` payload | `gate/decision: fields missing ['story_id']` | RED |
| `A2GateSchema.test_empty_story_id_refused_on_both_kinds` | `story_id: ""` on either kind | `…: fields of the wrong kind or enum ['story_id']` | RED |
| `A2GateSchema.test_formats_1_to_3_are_untouched_historical_writers_emit_nothing_new` | f3 gate stream without `story_id` via f3 AND f4 readers; same stream WITH `story_id` | equal Journals (delegation); `not in the schema ['story_id']` by both readers | GREEN / RED |
| `A2GateBinding.test_unknown_story_refused` | `gate/check` naming a story the journal never began | `R-GATE-BIND … in state ABSENT` | RED |
| `A2GateBinding.test_story_of_a_closed_attempt_refused` | `gate/check` after the story reached ENDED_COMMIT | `R-GATE-BIND … in state ENDED_COMMIT` | RED |
| `A2GateBinding.test_decision_for_a_story_after_unwind_refused` | `gate/decision` after rollback/dispose/end | `R-GATE-BIND … in state ENDED_ROLLBACK` | RED |
| `A2GateBinding.test_gate_events_legal_in_all_three_open_states` | checks + decisions in BEGIN, BEGIN_REFUSED and ACTIVE (the kernel's real surface) | — | GREEN (accepted, reconstructs) |
| `A2GateCompleteness.test_c3_attack_passing_decision_hiding_a_failed_check_refused` | the ORIGINAL C3 probe: `passed:true` citing the passing check, FAILED same-(gate,story) check in scope uncited (pre-A2′: ACCEPTED — probe at `aisef-private-evidence/2026-11-26-advrev-f4/`) | `R-GATE-COMPLETE … leaves gate/check [failed seq] … uncited` | RED |
| `A2GateCompleteness.test_omitted_passing_check_refused` | `passed:true` omitting an in-scope PASSING check | `R-GATE-COMPLETE … [omitted seq]` | RED |
| `A2GateCompleteness.test_omitted_failed_check_refused_even_when_every_cited_check_passes` | `passed:true` citing two passes, omitting the failed third | `R-GATE-COMPLETE … [failed seq]` | RED |
| `A2GateCompleteness.test_duplicate_citation_refused_for_both_verdicts` | same check cited twice, `passed` true and false | frozen Event invariant: `source_seqs cite earlier events, each once, in order` | RED |
| `A2GateCompleteness.test_vacuous_pass_citing_zero_checks_refused` | `passed:true`, zero citations, checks in scope | frozen cites rule: `gate/decision cites at least one gate/check` | RED |
| `A2GateCompleteness.test_completeness_is_per_gate_a_second_gate_id_scopes_apart` | second gate id "G2" (the rule is per (gate, story_id) though the kernel has one id): own-gate decisions complete → accepted; own-gate omission → refused naming ONLY the own-gate seq | `R-GATE-COMPLETE … gate/check [own seq] of` | GREEN / RED |
| `A2GateCompleteness.test_c5_interleaved_stories_completeness_is_own_story_exactly` | two stories' checks interleaved in one journal (C5 shape): omission refused naming exactly the own-story set; citing the other story refused; both own-set decisions accepted | `R-GATE-COMPLETE … gate/check [own seq] of`; `R-GATE-CITE … another story` | RED / RED / GREEN |
| `A2GateCompleteness.test_cross_story_citation_refused` | decision of story A citing story B's check | `R-GATE-CITE … cites [seq]: a gate/check of another story…` | RED |
| `A2GateCompleteness.test_retry_the_new_attempts_decision_scopes_from_the_previous_decision` | decision → `story/retry` → new attempt's checks → second decision citing only the new attempt = ACCEPTED; reaching back across the boundary | `R-GATE-CITE … stale — before this decision's scope` | GREEN / RED |
| `A2GateCompleteness.test_e5_fault_tail_false_decision_with_stranded_checks_is_accepted` | **the non-negotiable kernel-reality control**: stage checks, helper-emitted checks stranded by a raise, ONE handler-appended failed check, decision `passed:false` citing only the captured list, uncited same-gate checks in scope | — | GREEN (accepted at A and R; full journal reconstructs) |
| `A2GateCompleteness.test_second_decision_of_the_same_attempt_scopes_from_the_first` | repeated decisions inside one attempt: second owes only post-first checks; citing a pre-first check | `R-GATE-CITE … stale` | GREEN / RED |
| `A2GateCompleteness.test_failing_decision_still_subject_to_binding_and_citation_rules` | `passed:false` is exempt from COMPLETENESS only: a stale cite on a false decision | `R-GATE-CITE … stale` | RED |
| `GateRule.test_t9_passing_decision_over_a_failed_check_refused` (updated payload) | frozen R-GATE: `passed:true` CITING a failed check | `R-GATE: … cites failed gate/check [seq]` | RED |
| `FoldHasNoGateLeg.test_every_projection_ignores_gate_events` | fold consistency, stated honestly: NO control projection folds gate kinds — all six fold identically with and without the gate events, so the A/R verdicts are the whole A2′ surface and **the fold has no gate leg** (no false three-site claim; the pin goes red if a projection ever grows one) | — | GREEN |
| `Reader.test_t16_fmt4_3_ct2_delegation_identical_on_every_committed_fixture` + `test_t16_delegation_identical_on_generated_f2_and_f3_journals` | golden-corpus / historical parity: every committed fixture journal and generated f2/f3 journal reads identically through f3 and f4 | — | GREEN (run at this landing) |

No committed fixture journal contains a format-4 gate event (the fixtures are formats 1–2), and **no production
format-4 journal exists yet** — the production writer flip is still gated — so the schema's intended break
(refusing pre-A2′ f4 gate events) owes no migration.

## Verification at this landing (2026-11-26)

- `ruff check aisef2/journal/format4.py tests/v2/test_v23_format4.py validation/qualification/release_inventory.py` — clean.
- `python3 -m unittest tests.v2.test_v23_format4` — **79 tests, OK** (21 of them the A2′ matrix).
- `python3 -m unittest tests.v2.test_v23_transitions` — 21 tests, OK (frozen table untouched).
- `python3 -m unittest tests.v2.test_v23_story_lifecycle` — 29 tests, OK (the kernel E5 matrix: the fault tail the
  exemption protects still runs green against the real runner).
- `python3 -P validation/qualification/release_inventory.py --check` — PASS after the per-era regeneration: the
  inventory gained exactly one row, `aisef2/journal/format4.py::_gate4` (ACTIVE_V2_AUTHORITY), and the existing
  `::_rules` row's evidence line now lists GATE_CHECK (summary 73 → 74 active authorities); file digest
  `7ceb1b87…` → `456c6136165d4d567f43ceb4064f2ab0fb6137220a3d0e1854eab85f0a4e479c`, pin updated in the same change
  (`release_inventory.py INVENTORY_SHA256`). `closure-evidence/v2/v2.1/**` and `P6-AUTHORITY-INVENTORY.json`
  untouched.

Per ruling §1, the independent adversarial review runs AFTER this implementation and BEFORE integration
acceptance; this record claims no such review and flips nothing to production.

## Independent-review disposition (appended 2026-11-26 per owner ruling "A2′ Closure, Cohort Defect Disposition and RC Preparation" §1)

**Reviewed diff (exact):** commit `f0c230f33499ec314b4bb1968c3e952385262302` on `release/v2.3-big` — 5 files,
643 insertions / 13 deletions: `aisef2/journal/format4.py` (+76), `tests/v2/test_v23_format4.py` (+390), this
record (+170), `closure-evidence/v2/v2.3/AUTHORITY-INVENTORY.json` (73→74 active authorities, +`_gate4` row),
`validation/qualification/release_inventory.py` (pin → `456c6136…`). The reviewer's final confirmation ran on this
exact diff; `aisef2/journal/format4.py` at integration is **byte-identical** to the reviewed copy (git blob
`f43eac9302b0df76f9ba4eb34e1b484b1c2f7119`, verified by hash at confirm time).

**Reviewer evidence identity:** independent adversarial review of 2026-11-26 (in-session reviewer isolated from the
implementation context), two passes: (1) full review — 46 probes against the A2′ surface plus 6 targeted mutants on
`_gate_schema`/`_gate_bound4`/`_gate4` (**6/6 KILLED** by the committed matrix); verdict **ACCEPT** conditional on
the F1 record correction; (2) final pass on the exact integrated diff above; verdict **CONFIRM INTEGRATION, no
blocker**. One disclosed side effect: an unreferenced loose git blob (`6a4cf498…`) created by the reviewer's own
`git hash-object -w` during byte comparison — harmless, gc-prunable, no ref points at it.

**The four declared deviations and their dispositions:**

| # | Declared deviation (vs the ruling's literal text) | Reviewer finding | Fix | Disposition |
|---|---|---|---|---|
| 1 | First-decision scope opens at the story's **latest `story/begin`**, not the draft's `run/begin` | **F1:** this record's original equivalence parenthetical was factually false (the readings differ on hand-built journals) | Parenthetical retracted; corrected, verified justification written (kernel-written journals cannot carry an undecided earlier attempt); question escalated to the owner | **RESOLVED** — owner approved OPTION A and mandated the orphan negative control; `A2OrphanAttempt` (4 legs) SUCCEEDED, no counterexample |
| 2 | Duplicate-citation refusal rides the frozen Event invariant (`event.py:78-80`); no new A2′ string | **F2:** the original duplicate test was vacuous in the harness (the writer path cannot construct the input) | `test_duplicate_citation_refused_at_reconstruct_on_raw_bytes`: a validly encoded line's `source_seqs` tampered to a duplicate, fed to `reconstruct` — the invariant fires on raw bytes | **ACCEPTED** (proven at both sites) |
| 3 | Vacuous-PASS refusal rides the frozen cites rule ("cites at least one gate/check"); no new string | None — coverage confirmed, pinned by test | — | **ACCEPTED** as declared |
| 4 | A/R/F consistency declared honestly as "the fold has no gate leg" (no projection folds gate kinds), not a three-site claim | **F3:** the `FoldHasNoGateLeg` tripwire fixture lacked a `passed: true` decision, weakening the pin | Fixture extended with a passing decision | **ACCEPTED** after fix |

Reporting correction by the reviewer: the integrator's claimed test count (85) was wrong; the measured count is 84.

**Measurements, both retained:** **79 tests** was the landing-time measurement of this record's "Verification at
this landing" section (correct when observed, before review hardening); **84 tests** is the final post-review
measurement at `f0c230f3` (`python3 -m unittest tests.v2.test_v23_format4` → `Ran 84 tests … OK`): +4
`A2OrphanAttempt` legs and +1 raw-bytes duplicate test. The earlier observation is not rewritten.

**Engineering CI closure** requires a successful full `tests` workflow on `f0c230f3` exactly; at the time of this
appendix that run is queued and is reported as such, not as PASS.
