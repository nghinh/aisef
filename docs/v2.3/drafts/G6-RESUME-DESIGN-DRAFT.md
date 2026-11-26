# AISEF v2.3 — G6 CRASH-SAFE RESUME (lane L4-RESUME, W4b) — DRAFT against the FROZEN C-1

**Status:** DRAFT, implementation-ready, written against contract C-1 (FORMAT-4 freeze, owner ruling 2026-11-26,
`docs/v2.3/amendments/C-1-FORMAT-4-FREEZE.md`) at HEAD 50960ffa. The `story/completed` schema, Q10 resolution
and CR-11 bound are FROZEN inputs; nothing here re-opens them. Changes after the lane starts are dated amendments.

**Covers:** G6 (MASTER-CHECKLIST:56: `aisef run --resume`, fingerprint-gated reuse, `why_not` per story) under
the W4 gate "resume after kill-in-window never replays unaccounted spend, never rewrites signed history, and
prints `why_not`" (DEPENDENCY-DAG.md:489). Prerequisites per DAG:214-216: C5 (run.py handoff), E5, E6/C-1,
E2/E4 (reservation/segment), A2, #41 (stable kernel_digest).

---

## 1. Measured facts that fix this design (verified in THIS tree, 2026-11-26)

| # | Fact | Evidence |
|---|---|---|
| G1 | No resume exists: `--resume`/`why_not`/fingerprint-reuse have zero hits in run.py/cli.py; a run directory is NEVER reused (`{out} exists: a run directory is never reused or overwritten`), so resumption-in-place is already impossible by construction. | grep; `aisef2/app/run.py:479` |
| G2 | Everything the resume must trust is recoverable from the journal under the `--verify` rule, already implemented for `bundle continue`: read → digest/length vs RUN.json (when recorded) → `format3.reconstruct` (chain, seq) → no control-projection refusal; a run killed before RUN.json falls back to RUN.started.json with the journal digest UNBOUND (consistency-only). A torn LAST line is the approved exception: verified prefix + `cut_event`, effects reconciled against git, never assumed undone. | `aisef2/app/bundle_cli.py:911-952` (`_journal`), `:836-872` (`_record`), docstring `:27-30`; `aisef2/app/lineage.py:389` (`reconcile`) |
| G3 | The journal alone yields, via the six projections: per-story state/attempt/admitted/outcome (StoryState), run ENDED vs ABANDONED (TerminalState), per-owner spend counters (Budgets), request→result pairing by `source_seqs`, and each commit's revision (`story/commit.revision`). What it does NOT yield today: bundle identity (RUN.json only) and route identity at run level — both enter the f4 chain (G7). | `aisef2/journal/projections/__init__.py:24-31`, `story_state.py:26-71`; `aisef2/app/run.py:384` |
| G4 | `bundle continue` already: refuses a claimed predecessor (`BEGUN` child), checks `bundle_digest == project.digest` AND `kernel_digest == R.kernel_digest()` (from RUN.json, OUTSIDE the chain), takes the journal's last commit as the new baseline, rewrites the PLAN (committed stories' obligations → one CARRIED story of VERIFY obligations), writes a NEW bundle, and tells the operator to run it with `--parent`. It is all-or-nothing on the committed set and knows nothing of route or per-story base. | `aisef2/app/bundle_cli.py:969-970,980-984,987-991,1008-1023` |
| G5 | The `--parent` claim machinery is the exclusivity + spend-inheritance mechanism: claim taken BEFORE the first provider request (V21-80 claim-before-gate), append-only CONTINUED-BY.json, one continuation per run; the lineage account charges the four SPEND counters, refuses `unread` absolutely and `unaccounted` unless `--accept-unaccounted`. Kill-in-window spend is exactly what E2/E4 seal: f4 `provider/request.reservation` + `provider/result.segment`, charged `max(reservation, stream)`. | `aisef2/app/run.py:546-576`; `aisef2/app/lineage.py:290,353,486,117`; FORMAT-4 §4.2-4.3 |
| G6f | The cheap re-proof path already exists: a story whose every obligation measures SATISFIED at the parent makes NO developer call (K-NOWORK) — the candidate is the parent, every obligation still proved by local probes, zero provider spend. This is what a committed story's re-admission at a tip that contains its merge measures to. | `aisef2/orchestrate/story_runner.py:271-277` |
| G7 | FROZEN marker (f4 §4.5): `story/completed {story_id, revision(sha), fingerprint(hex64)}`, cites exactly one same-story `story/commit`, WITHIN `{ENDED_COMMIT}`, at most one per story per run, appended by the RUN DRIVER at finalize, never `_attempt`. Fingerprint = sha256 of a canonical JSON G6 freezes HERE (§3.3) over at least (bundle digest, kernel digest, route identity, base revision). Q10 FROZEN: **no marker without a same-run commit** — a resumed run journals its OWN admission trail citing the predecessor, never a copied marker. CR-11: resume reads markers only from format ≥ 4 journals whose `run/begin.kernel_digest` matches. Q9 default: no run-level marker; R-CLOSED + `run/end` suffice. Q4 default: `bundle_digest` in f4 `run/begin` is OPTIONAL. | FORMAT-4-DESIGN-DRAFT.md §4.5, §4.1, §12 Q4/Q9/Q10; COMPATIBILITY-MATRIX CR-11 |
| G8 | A fresh `aisef run` resets the repo to the PLAN baseline (`checkout -B main project.plan.baseline`) and clones from `--repo` — the predecessor's merges exist only in the predecessor's own clone. This single line is why a plain re-run re-pays everything, and is the line resume must override. | `aisef2/app/run.py:584`, `:580` |
| G9 | The delivery verdict reads THIS run's journal only ("The delivery verdict comes from the journal only"); `delivery()` counts a plan story missing unless ITS commit is in the events. A reused story therefore MUST re-enter the resumed journal through the legal lifecycle, or the resumed run can never say PASS. | `aisef2/app/run.py:43,374-390` |
| G10 | The run's route identity is journaled at begin: `capability/resolved` rows for the attested `developer`/`reviewer` capabilities carry `{provider, endpoint, declared_model, route}`; `run/begin` (f4) carries `kernel_digest` and (when plumbed) `bundle_digest` inside the hash chain. An attempt's base is journaled: `story/begin.parent`. | `aisef2/app/run.py:340-343`; `aisef2/runtime/run_scope.py:125-130`; `aisef2/orchestrate/story_runner.py:223` |
| G11 | The writer refuses to EXTEND foreign history: a torn tail or an unknown-format journal is never appended to; `kernel_digest()` is the whole-package digest, deterministic per install. | `aisef2/journal/writer.py:37-41`; `aisef2/app/run.py:93-100` |
| G12 | Exclusivity rule (frozen as an option-set): G6 `--resume` vs V2.1 `--parent` are exclusive PER PREDECESSOR; a CONTINUED-BY-claimed run is not resumable, a run under resume is not claimable; V21-80 must be preserved, changing it is a STOP. | DEPENDENCY-DAG.md:462 |
| G13 | File ownership: W4b L4-RESUME owns `aisef2/app/{run,lineage,cli}.py` — and NOTHING else; `run.py` arrives via the hot-file handoff L2-RECORD → L3-CLIENT → L4-PARALLEL → **L4-RESUME**. `runtime/run_scope.py` (the f4 `run/begin` payload site) is owned by L2-ACCOUNTING in W2b only. | DEPENDENCY-DAG.md:376; ACCELERATED-DELIVERY-PLAN.md §2:52-54; FORMAT-4 §9 |

## 2. Scope and non-goals

- N1. No in-place resumption: a resumed run is a NEW run directory (G1); the predecessor's journal, record and
  streams are never written — signed history is never rewritten (the resume never even opens a writer on it, G11).
- N2. No marker fabrication, ever: Q10 is frozen (G7). A predecessor commit without a marker is reused only
  through re-admission (§3.5), never by synthesizing `story/completed`.
- N3. No cross-run verdict: the resumed run's verdict is its own journal's (G9). RUN.json carries the resume
  report; the verdict does not read the predecessor.
- N4. No resume of format ≤ 3 journals (CR-11): `bundle continue` remains their path; the refusal says so.
- N5. Signature VERIFICATION of the predecessor is C-2/A2-INT (L2-AUTH); until it lands, resume proves
  consistency (+ optional `--expect-anchor` authenticity), exactly continue's documented stance (G2). The
  seam is left: the predecessor-verification step takes the same journal object A2's verifier will hand over.
- N6. No run-level completion marker (Q9 default, frozen).

## 3. The resume protocol (normative)

`aisef run --resume PRED_DIR --project BUNDLE --settings S --out NEW [--expect-anchor A] [--accept-unaccounted]`

### 3.1 Run-level admission of the predecessor (each check fail-closed, in this order)

1. **Evidence** — `_record`/`_journal`/`_authentic` rule, reused from bundle_cli (G2; imported read-only —
   bundle_cli.py is not edited): unreadable → refuse (EVIDENCE_UNREADABLE); projection refusal → refuse (no
   kernel wrote it); torn last line → verified prefix + `cut_event`, effects reconciled against git (G2).
2. **Format** — the verified prefix's `run/begin.journal_format` ≥ 4, else refuse: "format {n}: resume reads
   closed-story markers from format ≥ 4 journals only (CR-11); use `aisef bundle continue`" (N4).
3. **Kernel** — `run/begin.kernel_digest` (the CHAIN's, not RUN.json's) == this process's `kernel_digest()`,
   else refuse: another kernel is a new project, as continue rules (G4).
4. **Bundle** — `run/begin.bundle_digest` present AND == `project.digest`, else refuse (NO_BUNDLE_IDENTITY_IN_CHAIN
   when absent — see the plumbing hunk, §4; RUN.json's copy is corroboration, never the authority).
5. **Exclusivity + claim (V21-80)** — `lineage.continued_by(pred)` must name no child (a claimed run is not
   resumable, G12); then `lineage.claim(pred, NEW, clock)` is taken BEFORE any provider request — the SAME
   CONTINUED-BY mechanism, so a run under resume is automatically not claimable and not doubly resumable.
   One mechanism, both directions of G12.
6. **Spend** — `lineage.lineage_account(pred)` inherited into the Budget exactly as `--parent` (G5): `unread`
   → absolute refusal; `unaccounted` → refusal unless `--accept-unaccounted`. Kill-in-window spend arrives as
   the reservation (E2) and is charged, so it is never replayed unaccounted — the W4 gate's first clause.
7. **Baseline** — source repo := `PRED_DIR/repo`; main := the reconciled tip (the journal's last confirmed
   commit; unidentified commits refused as continue refuses them, G2/G4) — this replaces run.py:584's reset to
   the plan baseline (G8). `check_repository` still verifies the plan baseline and requirements blob are held.

### 3.2 Per-story reuse decision → `why_not`

For every plan story, over the predecessor's VERIFIED PREFIX, in plan order; each row printed and recorded in
RUN.json `resume.stories[sid]`:

| Condition (first that fails names the row) | why_not |
|---|---|
| story has a `story/commit` in the prefix | `NOT_COMMITTED` (open, rolled back, or crash mid-story) |
| a `story/completed` marker exists in the prefix | `MARKER_ABSENT` (crash post-commit pre-marker; pre-marker finalize) |
| marker cites that same-story commit (f4 guarantees it; defense) | `MARKER_CITATION_BROKEN` |
| marker.fingerprint == fingerprint recomputed FROM THE PREDECESSOR'S OWN CHAIN (§3.3) | `FINGERPRINT_FORGED` → refuse the WHOLE resume (evidence inconsistent with itself: tampering class, as EVIDENCE_PROJECTION) |
| predecessor fingerprint == THIS run's prospective fingerprint for that story | `IDENTITY_DRIFT(<field>)` — names exactly which of bundle/kernel/route/base differs |
| marker.revision is held by the repo and is an ancestor of the resumed main | `REVISION_NOT_ON_MAIN` (a revert or reconcile cut removed it) |
| all pass | **REUSED** (mechanism §3.5) |

A story that is not REUSED simply RUNS (full path); `why_not` is transparency, not a block. Dependency note:
waves/order are the bundle's as always — a reused story satisfies its dependents' edges by committing (§3.5).

### 3.3 The fingerprint — exact composition, frozen by THIS design (fills §4.5's "G6 freezes at W4")

`fingerprint = sha256(canonical_json({"base": <story/begin.parent of the attempt whose commit the marker cites>,
"bundle": <run/begin.bundle_digest>, "kernel": <run/begin.kernel_digest>, "route": {"provider": p, "endpoint": e,
"declared_model": m, "route": r}}))` — canonical JSON = sorted keys, `,`/`:` separators, UTF-8 (the house
`product.contract.digest` rule). The route four-tuple is read from the chain's `capability/resolved` row for
the `developer` capability (G10) on the predecessor side, and from the resumed run's own settings identity on
the prospective side. All four inputs live INSIDE the predecessor's hash chain — nothing outside the chain
gates reuse. `signer` is deliberately NOT an input: it is run-ephemeral by A2 design and would void every
reuse by construction. The emitting side (§3.6) computes it from the same chain-held values of its own run.

### 3.4 Crash taxonomy (what each kill leaves, and what resume does)

| # | Kill point | Journal state | Resume behavior |
|---|---|---|---|
| K1 | mid-story, before `provider/request` | story open, no spend | `NOT_COMMITTED` → re-run; nothing inherited for it |
| K2 | provider window (request, no result) | request + reservation, no result (SIGKILL writes no closer; repair appends f4 closers under CR-2) | spend inherited as `max(reservation, stream)` via the account (G5); story `NOT_COMMITTED` → re-run; never replayed unaccounted |
| K3 | mid-append (torn line) | torn tail; writer refuses extension (G11) | verified prefix only; `cut_event` reconciled against git (G2); any commit/marker at-or-after the cut does not exist for §3.2 |
| K4 | post-commit, pre-marker | `story/commit`, state ENDED_COMMIT, no `story/completed` | `MARKER_ABSENT` → re-run, which re-admits at a tip CONTAINING the merge → K-NOWORK: zero provider spend (G6f); commits again; gets its marker in the NEW run (Q10) |
| K5 | post-marker, pre-`run/end` | marker present, run not ENDED | per-story reuse unaffected (reusability is per story, not per run-terminal) |
| K6 | during RUN.json write | RUN.started.json fallback: journal digest unbound | consistency-only resume (G2); `--expect-anchor` refused with "a run killed before its record has none" (bundle_cli:883-885 rule) |
| K7 | no kill (clean, all committed + marked) | ENDED | every story REUSED → whole run re-commits via §3.5 at zero provider spend; idempotence test |

### 3.5 Reuse-without-replay — the admission trail (Q10's resolution, applied)

A REUSED story is NOT skipped: it is dispatched through `run_story` on the resumed run like any story —
and because the resumed main CONTAINS its merge (§3.1.7 + §3.2 ancestor check), its admission measures every
obligation SATISFIED at the parent → the K-NOWORK path (G6f): **no developer call, no provider request, zero
paid spend** — "without replay" means without PROVIDER replay. The probes re-prove locally; their events ARE
the resumed run's own admission trail; the story commits (candidate == parent) and the resumed run appends its
OWN `story/completed` with its OWN fingerprint (Q10: marker only on a same-run commit). The predecessor
CITATION is recorded in RUN.json `resume.stories[sid]` = {predecessor journal sha256, marker seq, fingerprint,
decision} — operator-facing provenance; the journal needs no new event kind, which is exactly why this fits
under C-1's closed vocabulary. **REUSE_BROKEN control:** a REUSED story whose admission then finds work (the
repo at the same tip measures differently) commits nothing silently — it runs the full path and RUN.json flags
`resume.stories[sid].broken = true`: identity said unchanged, measurement disagreed — a loud finding, never
masked. `ponytail:` re-proof by local probes is retained cost (seconds per story); skipping probes too would
need a new trusted-copy event kind = a C-1 amendment, not bought by this lane.

### 3.6 Marker emission at finalize (the producer side G6 owns, FORMAT-4 §9 row `app/run.py`)

In `execute`'s NORMAL path only — after the story loop, before `rec["stage"] = "finished"` (run.py:699) and
before `_close_run`'s shutdown (after `run/end` nothing appends, run_scope.py:144-148): for every story whose
STORY_STATE is ENDED with outcome COMMIT, append `story/completed {story_id, revision: <its commit's revision>,
fingerprint: §3.3}` citing that commit's seq. At most one per story (frozen rule; the driver iterates the
projection, which holds one terminal state per story). The interrupted/exception path writes NO markers — that
is crash case K4 by design, and resume handles it. Emission applies to EVERY f4 run (serial, parallel, resumed
alike); on a format-3 run (pre-flip) the driver emits nothing (vocabulary pin, §4.10).

### 3.7 What `bundle continue` already does vs what G6 adds

| | `bundle continue` + `--parent` (V2.1, stays) | `aisef run --resume` (G6) |
|---|---|---|
| artifact | NEW bundle, plan rewritten (CARRIED story of VERIFY obligations) (G4) | SAME bundle, same plan, one command |
| identity gate | bundle+kernel digest from RUN.json (outside the chain) (G4) | bundle+kernel+route+base from INSIDE the hash chain (G7/G10), per story |
| granularity | all-or-nothing on the committed set | per story, `why_not` printed per story |
| baseline | operator runs the new bundle against PRED/repo by hand | resolved automatically (§3.1.7) |
| spend | `--parent` claim + lineage account | same machinery, same flags (G5) |
| trust anchor | RUN.json digest binding + optional anchor | chain-held marker + fingerprint; anchor optional; A2 signature when C-2 lands (N5) |

Both survive: continue is the cross-format and cross-bundle-era tool (N4); resume is the same-identity fast path.

## 4. File-touch list — single-writer schedule and registry flags

F5 rule: every file with registered targets edited here lands inside the G6 measured batch (KERNEL-COUPLING-01,
one batch one measurement). Counts measured 2026-11-26 against `validation.v2.mutation.TARGETS` (994).

| File | Edit | Owner/phase | Registry targets |
|---|---|---|---|
| NEW `aisef2/app/resume.py` | predecessor admission (§3.1, reusing bundle_cli's `_record`/`_journal`/`_authentic` by IMPORT), fingerprint (§3.3), per-story decision + `why_not` (§3.2) | L4-RESUME W4b | 0 today — REGISTER new targets (each §3.1 gate, the fingerprint, each `why_not` row) with kill file `test_v23_resume.py` |
| `aisef2/app/run.py` | `--resume` path in `execute` (claim, baseline override of :584, resume record), marker emission at finalize (§3.6) | L4-RESUME W4b, AFTER the L4-PARALLEL handoff (plan §2:53) | **25** |
| `aisef2/app/cli.py` | `--resume PRED` argument; `--resume` + `--parent` together = parser error (G12: one predecessor relation per run); `--resume` + `--repo` = error (the repo is the predecessor's) | L4-RESUME W4b | **2** |
| `aisef2/app/lineage.py` | expected NO edit (claim/account reused as-is, §3.1.5-6) — declared so the diff reviewer flags any | L4-RESUME W4b | **34** |
| `aisef2/runtime/run_scope.py` | **REQUESTED HUNK, not G6's:** `begin` payload gains `bundle_digest` (Q4's optional field, plumbed: execute passes `project.digest` into the RunScope spec/ctor). Owner: L2-ACCOUNTING, whose W2b flip window is open NOW — request it rides the JournalWriter4 flip batch (CORE-2), or the integrator logs a single-writer exception. Without it, §3.1.4 fails closed on every run and resume is inert. | L2-ACCOUNTING W2b | **13** |
| `aisef2/app/bundle_cli.py` | NO edit (imported only; W2c touched `continue_from`/`_authentic` — read the post-W2c form before import wiring) | L2-AUTH W2c / L4-PARALLEL W4a | 45 |
| NEW `tests/v2/test_v23_resume.py` + fixtures `tests/v2/fixtures/journal/*resume*.jsonl` (f4 journals cut at K1-K6 points) | §5 | L4-RESUME W4b | kill file |

## 5. Test plan — crash fault matrix

`tests/v2/test_v23_resume.py` (offline; predecessor journals built through JournalWriter4 and cut byte-exactly):
| # | Injection | Expected |
|---|---|---|
| R1-R7 | the K1-K7 taxonomy rows (§3.4), one fixture each — K2 with reservation vs stream divergence, K3 with the cut landing (a) mid-commit-line and (b) mid-marker-line | each row's exact behavior; K3b: the marker does not exist, `MARKER_ABSENT`; spend equals the account's `max(reservation, stream)` |
| R8 | fingerprint drift, one field at a time (bundle, kernel, route.endpoint, base) | `IDENTITY_DRIFT(<field>)` naming that field; story runs, not reused |
| R9 | marker.fingerprint edited in the fixture (chain re-linked = EVIDENCE_INTEGRITY; chain-consistent forge impossible without re-signing — simulated by recomputation mismatch) | whole-resume refusal `FINGERPRINT_FORGED` (or EVIDENCE_INTEGRITY upstream — either refusal is fail-closed, the test accepts only refusal) |
| R10 | format-3 predecessor | refusal naming CR-11 and `aisef bundle continue` |
| R11 | claimed predecessor; then resume-then-parent on the same predecessor | both second operations refused (G12 both directions); CONTINUED-BY generations append-only |
| R12 | `run/begin` without `bundle_digest` | refusal `NO_BUNDLE_IDENTITY_IN_CHAIN` (fail-closed on the Q4 optionality) |
| R13 | REUSE_BROKEN: repo file mutated after the predecessor ended, same tip | story runs full path; `broken: true` recorded; no silent commit |
| R14 | predecessor with `unread` evidence / `unaccounted` spend | absolute refusal / refusal unless `--accept-unaccounted` (reuses the --parent controls verbatim) |
| R15 | marker emission: normal end vs interrupted end | markers for every ENDED_COMMIT story, exactly one each, before `run/end`; interrupted run emits none |
| R16 | signed-history invariant | after any resume, the predecessor directory byte-compare == before (minus the appended CONTINUED-BY claim file, which is append-only history) |

Freeze-package §4 controls REUSED (not re-written): §4.5 rows (missing fingerprint, wrong citation, non-commit
citation), T8/T8b (marker state + duplicate), §4.1 `run/begin` field controls, R-CLOSED companion (K5 fixture
ends without `run/end`). Mutant classes for `resume.py`: drop a §3.1 gate → its R-row; swap a fingerprint field
→ R8; accept an unmarked commit as REUSED → R1/K4.

## 6. Declared limitations

- L1. Until C-2/A2-INT lands, resume (like continue) proves consistency, not authenticity, without
  `--expect-anchor` (N5); the fingerprint is tamper-EVIDENT inside the chain, not operator-proof.
- L2. Reuse is not free: local probes re-prove every reused story (§3.5). The saved cost is exactly the
  provider spend, which is the cost that matters (E5 measurements: provider wall time dominates).
- L3. `why_not` explains the predecessor's side only; a story that is reusable but whose DEPENDENCY re-runs
  and lands a different merge simply re-measures at the new tip (the kernel's normal rule) — resume adds no
  cross-story reasoning.
- L4. A pre-f4 or unflipped-production predecessor is never resumable (N4); the flip's pacing (C-1 conditions:
  independent adversarial review + A2 gates) therefore paces G6's first production use — schedule note, not a
  design dependency (fixtures are f4 regardless).

## 7. Open questions, each with its default (no STOP)

- **QG1 marker emission timing:** normal path only, before shutdown (§3.6). Default stands; markers on the
  interrupt path are rejected (an interrupted run is not a successful termination, run_scope.py:206-211,
  and K4 handles the gap safely).
- **QG2 fingerprint composition:** §3.3 as written. STOP only if the owner wants `signer` included — default
  NO (run-ephemeral by A2 design; including it voids all reuse). Decided at the G6 batch review, recorded as
  a one-line amendment to §4.5's "at least" clause if the owner adds fields.
- **QG3 the run_scope `bundle_digest` hunk:** default = ride L2-ACCOUNTING's CORE-2 flip batch (request filed
  at design time — this document is the request). Fallback: a dated single-writer exception at W4b; the WORSE
  fallback (read bundle identity from RUN.started.json, outside the chain) is rejected as violating the
  chain-only trust rule (§3.3).
- **QG4 `--resume` + explicit `--out` collision semantics:** default = identical to today's rule (G1): an
  existing out dir refuses; resume never names its own out.
- **QG5 route identity source for the prospective side:** the resumed run's settings identity (§3.3), read
  BEFORE preflight; the preflight still attests it as today (run.py:610-624) — a route that fails attestation
  refuses the run before any reuse decision matters. Default stands.

---

## Addendum 2026-11-26 — fold-before-trust is LOAD-BEARING (adversarial review C1)

The independent adversarial review of the C-1 landing (2026-11-26, evidence aisef-private-evidence/2026-11-26-
advrev-f4/) CONFIRMED: a `story/completed` marker appended AFTER `run/end` is accepted by both the f4 writer and
`format4.reconstruct`; only the projection fold refuses it. G2's verify rule already contains the fold leg ("no
control-projection refusal") — this addendum makes it NORMATIVE, not incidental: **the resume MUST fold the
predecessor's control projections (TerminalState included) and refuse on any projection refusal BEFORE trusting
any marker; reconstruct alone is NEVER sufficient.** A marker in the reconstructed stream that the fold refuses
(e.g. after `run/end`) ⇒ the FINGERPRINT_FORGED / tampering class: refuse the whole resume. This holds
regardless of whether the owner issues the proposed C-1 amendment A1 (the §4.5 run/end bound) — defense in depth,
not an alternative to it.
