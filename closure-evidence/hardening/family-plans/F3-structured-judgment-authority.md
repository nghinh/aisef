# Fix family F3 — STRUCTURED JUDGMENT AUTHORITY

Closes (frozen defect set): SS-05, SS-23, SS-24, SS-25, SS-26, SS-27, SS-28, SS-29, SS-30, SS-31, SS-32, D-002
(SS-57 was closed by F2's rule and is re-verified here). Invariants: INV-F.2, INV-F.4, INV-B.2 (the epoch half of
SS-05), INV-Q.1, INV-R.2; INV-F.3 and INV-T.1 lose their F3 reproducers (SS-23/SS-26, SS-05/SS-26/SS-27).

Owner rule (Phase 10): *free-form prose has ZERO authority over control state.* Every control decision below reads a
structured field — a JSON verdict, a provider status, a status token, a parsed exception name, a typed check field —
and the prose it used to read becomes diagnostic text that is recorded and shown, never scored.

## 1. Findings bind to an identity (INV-F.2, D-002)

A blocking or stuck finding counts only when it binds to something the kernel can name:

| binding | source | accepted when |
|---|---|---|
| `behavior_id` | contract behaviours (`acceptance.contract`) | the id exists in this story's epoch |
| `file` (path identity) | the candidate's `changed_files` / the story's write scope | the path is in the candidate's diff, or inside the write scope for "missing" work |
| criterion code | `AC-<story>-<i>` | the code exists in the story |

`Verdict.blocking()` gains `bound_blocking(contract, changed, scope)`; an unbound blocker is recorded as
`review:unbound` (typed note, the finding kept verbatim) and does **not** block. A `block`/`stuck` verdict whose every
blocker is unbound is treated like a malformed verdict: the schema retry asks for bindings, then the review is
`REVIEW_UNRUNNABLE` (F2 machinery, bounded) — never a PASS from an unbound block, never a developer session for one.

**D-002 disposition**: the fact stays measured (judge-only blocks exist and their rate is a published property; owner
ruling 1 fixed four properties for them). F3 adds the fifth, structural one — a judge-only block names a behaviour,
path or criterion of THIS candidate, and evidence carries `review:unbound` when it does not. With that the register
row is **SUPERSEDED** by INV-F.2 + the binding rule: the remaining content of D-002 is a property, not a defect.
Proof: `closure-evidence/judge-only-audit.json` re-run on the same corpus plus the binding test; recorded in the
defect set with this reasoning.

## 2. Prose never adds or removes a blocker

- **SS-24** `_reconcile`: the review's blockers are `verdict.bound_blocking(...)` only. Text-derived `[block]` lines are
  compared for the `review:mismatch` diagnostic and shown to the developer as advisory, never unioned in. `merge_findings`
  is kept for the diagnostic and loses its authority.
- **SS-25** `_paths_outside(findings: list[dict], scope)` reads `f["file"]` from the structured findings the attempt now
  keeps (`Attempt.review_verdict: list[dict]`); `deadlock_reason` compares structured findings by `Finding.id` /
  `(tag, file, behavior_id)` and asks scope of the bound paths. No regex over prose.
- **SS-27** `is_noise(text, severity)`: the noise filter has a severity floor — a finding whose severity is in the
  blocking set (`security.block_severities`, default high/critical) is never filtered, whatever its wording; the filter
  applies to low/medium only and the drop is recorded in `filtered` with the group that matched.
- **SS-32** `Check.data: dict` (typed payload beside the prose `detail`): the gate's `tests verify story` puts
  `{"still_green": [...ids], "parent": sha}` in `data`; `nop_deadlock` reads `data["still_green"]` — the sentence can
  change freely.
- **SS-05** `_no_escalation`: an earlier advisory position demotes today's blocker only when (a) the earlier verdict
  belongs to the SAME story epoch (`identity.story_epoch`), and (b) the match is on a real binding — `behavior_id`
  non-empty, or `file` inside the write scope; findings with no binding never collide. The demotion stays recorded
  (`review:no-escalation`) and the verdict flip stays inside the epoch. A contract change starts from zero.

## 3. Structured sources for environment and status

- **SS-28** `exit_status_of`: `auth` comes from `raw.api_error_status ∈ {401, 403}` or the provider's typed error
  field (`api_error_type` / `error.type` recorded by the adapters), never from `raw["result"]` (the agent's final text).
  The agent's text is excluded from EVERY classification branch; the adapters record the provider's status where they
  see it (OpenCode: HTTP status of the failing request; Claude Code: `api_error_status` / `error.type` from the result
  event). The conformance suite (Phase 15) gets the condition "story about 401 handling → not auth".
- **SS-23** `unrunnable_reason("test", …)`: the runner ran when the parsed test log names ANY test (passed or failed);
  `not found` inside assertion text is a test failure. Unrunnable needs exit 127, or a MISSING_TOOL phrase with an
  empty test log.
- **SS-26** `_vang_ma_cua_story`: parse the missing module from the structured exception (`ModuleNotFoundError: No
  module named 'x'` / `Cannot find module 'x'`) and accept the nop's red only when `x` IS one of the story's own
  modules (path → module identity, exact); a third-party name stays an environment failure (UNRUNNABLE).
- **SS-29** closure G6.3: the status cell is parsed to a status token (first cell word after normalisation) and compared
  for equality with the RESOLVED set; `unresolved`, `not resolved`, `will be fixed` are open.
- **SS-30** stories machine gate: a criterion is a placeholder only when the WHOLE criterion is a placeholder token
  (`^\s*(TODO|TBD|FIXME|placeholder|not implemented|stub)\b[\s:.\-]*$`, plus an empty criterion); words inside a sentence
  never match — a to-do application is describable.
- **SS-31** `_NO_SURFACE`: headless is the anchored statement `Screens: none` (the line ends after the negation or an
  em-dash comment); a line that enumerates screens is never headless; the keyword list goes.

## 4. Definition of done

RED → GREEN: `test_sibling_scan.py::TestSS05/23/24/25/26/27/28/30`, `scan8a/test_group_a.py::TestSS29/31/32`, the new
binding tests (`tests/hardening/test_judgment.py`: bound block blocks; unbound block is `review:unbound` and retried;
unbound-only verdict is REVIEW_UNRUNNABLE, never PASS, never developer), adapter conformance "401 in prose is not auth";
D-002 SUPERSEDED with the re-run audit; INV-F.2, INV-F.4, INV-Q.1, INV-R.2 PROVEN; INV-B.2 keeps only F6/F1-unrelated
reds if any; INV-F.3 / INV-T.1 lose SS-23/26 and SS-05/26/27; model: a `REVIEW_BLOCK_UNBOUND` event → UNRUNNABLE
(F2 path); differential `KNOWN` stays empty; fault cell FM-T-07 GREEN; full suite, ruff, Linux + Windows CI.
