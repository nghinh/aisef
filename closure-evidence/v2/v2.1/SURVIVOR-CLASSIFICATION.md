# V2.1 supplementary campaign — survivor classification (FINAL disposition)

## Final disposition — owner directive 2026-10-31 (RELEASE-DECISIONS seq 6)

**93 survivors across the 90 new-measure targets; 0 CONFIRMED product defects.** Final disposition for 2.1.0:

- **86 survivors** are covered by the frozen `AUDITED` set carried from prior cycles (`mutation.AUDITED` /
  positional audits) — not gate-blocking, classified EQUIVALENT / AUDITED in the record.
- **7 survivors are OWNER-ACCEPTED scoped residual risks** (seq 6): `client.py::session` ×3 and
  `story_runner.py::_attempt` ×4. Their exact identities, positions, `source_sha256`, one-label class, and the
  effect **re-verified against the product source at 8c7bdb44** are recorded authoritatively in
  `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` seq 6 (`accepted_survivors.survivors`) and summarised in
  `V2.1-KNOWN-LIMITATIONS.json`. The `_attempt` four are S-01..S-04 below.
- **ACCEPTED EXCEPTION, not PASS:** the machine mutation gate verdict is **preserved as FAIL**
  (`UNAUDITED_SURVIVORS = 7`). The acceptance is a risk-based decision recorded *above* the gate; it does **not**
  relabel the survivors KILLED, fabricate audit evidence, or modify any historical measurement. No test or
  product code was changed to eliminate them.
- **A-03** (integrity under external SIGKILL mid-call) is a **documented supported-envelope limitation**
  (option 2), not a fix — see `V2.1-KNOWN-LIMITATIONS.json`.

The consequence × evidence analysis that grounds each acceptance is unchanged below and in `HANDOFF-INTERIM.md`
§4; one label per survivor (EQUIV / OOR-AUDITED / TEST-GAP / UNDET / BUG), the merged "EQUIV/OOR" tag retired.

---

Candidate frozen at **8c7bdb44** (product tree `5f34a3f3`, = fce3d7b7). Classification is light,
evidence-based, **no code change** (owner directive 2026-10-29, step 2). Updated as records arrive.

**This file details targets 1–3 (`_attempt`, `_ocr`, `run.py::execute`), 23 survivors.** The full ledger of
all **9 finished targets / 51 survivors**, with the owner's **consequence × evidence** risk method (risk is
*not* read off the BUG/TEST-GAP/EQUIV label; it is the possible consequence of the simulated defect bounded by
evidence of what the code actually consumes), is in **`HANDOFF-INTERIM.md`**. Campaign running.

Classes (owner 2026-10-30 — **one label per survivor**; the merged "EQUIV/OOR" tag is retired, never used
to pass over a difference):
- **BUG** = input + contract-violating behaviour demonstrated on the *original*.
- **EQUIV** = no behavioural difference under the contract in scope — an equivalent mutant that changes code
  but produces **no observable difference** in any decision, stored evidence, or journal on any reachable path.
- **OOR/AUDITED** = a real difference **does** exist but lies **outside the mandatory requirements**, stated
  with grounds that name *what* differs and *why* it is out of requirement.
- **TEST-GAP** = mutant changes meaningful behaviour the suite does not catch — **unresolved, kept public**.
- **UNDET** = insufficient evidence, not self-audited — **unresolved, kept public**.

Priority lens (owner): data · secrets · access · out-of-scope execution · story obligations · cost ·
evidence authenticity — *above* empty-string / order-change.

## Negative check (bounded, not a blanket safety claim)
**No survivor *observed so far* touches the secrets-redaction path** (`adapters.py` L243 `keys`,
L245/L252/L266 `client.redact`), nor any data-write, access-grant, or execution-authority line, within the
3 targets measured. This is a scoped negative over `_attempt`+`_ocr`+`run.py::execute`, **not** a claim that
every survivor is safety-neutral: UNDET rows (S-10) and rows carrying an open light-check stay
**provisional** until closed, and 85 targets are unmeasured. For `execute`: of the 366 mutants the engine generated, 356 were
killed and 10 survived; every *surviving* mutant is confined to run-record serialization or refusal-*message*
text, and none of the surviving mutants alters a decision. This bounds the **surviving mutants**, not the
product — a KILLED count is never evidence the product is defect-free, only that the suite distinguishes
those specific generated mutants. No row below asserts "the original is correct" — only
**"no original-code defect confirmed within the tested scope."**

## `aisef2/orchestrate/story_runner.py::_attempt` — 322/326 killed, 4 survivors

| id | mutant | what it changes | class | prio | grounds / consumption path |
|----|--------|-----------------|-------|------|----------------------------|
| S-01 | L271 `ObligationRole.PRESERVE`→`INTRODUCE` | role of the candidate-side re-proof of an affected committed obligation (V21-38) | **EQUIV** | LOW | **Proven decision- and evidence-neutral at this consumption path — an equivalent mutant: no observable difference in any decision, stored evidence, or journal.** `role` reaches only `prove()`→`route(bound,spec,point,role)` ([proof.py:107](aisef2/orchestrate/proof.py:107)); every CANDIDATE routing row is keyed role=`None` ([routing.py:81-86](aisef2/control/routing.py:81)) and `row_for` falls back to the role-`None` row ([routing.py:125](aisef2/control/routing.py:125)), so at `point=CANDIDATE` (pinned [story_runner.py:277](aisef2/orchestrate/story_runner.py:277)) the three role values route identically. role is **not** in `verified_payload` (not journaled) nor on the `Proof` dataclass ([proof.py:29](aisef2/orchestrate/proof.py:29)). A developer regression of a committed PRESERVE obligation is still caught at the candidate via `contract_satisfaction`→UNSATISFIED→CONTRACT_UNSATISFIED/DEVELOPER, **role-independently** — so this is **not** (a) accept-a-regression nor (b) corrupt-evidence-but-still-catch; it is (c) a difference that does not affect the decision on the path in use. **Residual:** equivalence is contingent on the current role-agnostic CANDIDATE routing — a future role-keyed CANDIDATE row would make this line live → coverage-hardening note (C). |
| S-02 | L271 `ObligationRole.PRESERVE`→`VERIFY` | same site, other role value | **EQUIV** | LOW | sibling of S-01; same proof, same residual. VERIFY also routes identically at CANDIDATE (role-`None` fallback). |
| S-03 | L249 string `'developer '` emptied | descriptive label of `_EscapedRange(f"developer {story_id} range", …)` on the PL-7 `RangeEscaped` handler | **OOR/AUDITED** | LOW | **Light-check closed.** `scope.acquire`/`release` key on `resource.kind` + object identity (`self._stack[-1][0] is not resource`, [story_scope.py:112](aisef2/runtime/story_scope.py:112)); `resource.name` is only a journal payload ([story_scope.py:99](aisef2/runtime/story_scope.py:99)), never an identity/release key. Emptying one fragment keeps `{story_id}` in the name → still unique, no collision. Descriptive-only. |
| S-04 | L249 string `' range'` emptied | same label, other fragment | **OOR/AUDITED** | LOW | sibling of S-03; same resolution. |

## `aisef2/app/adapters.py::Reviewer._ocr` — 294/303 killed, 9 survivors

| id | mutant | what it changes | class | prio | grounds / consumption path |
|----|--------|-----------------|-------|------|----------------------------|
| S-05 | L219 `sorted()`→`list()` | order of `required` (non-deleted changed product paths) | **TEST-GAP** | LOW | `required` feeds `review_ocr.coverage(…, required=…)` (membership) and is stored in session evidence `s["required"]` (L272). Verdict likely order-insensitive; residual is **evidence-ordering determinism**. Not a behaviour change to coverage. |
| S-06 | L272 `sorted()`→`list()` | order of `s["deleted"]` in session evidence | **TEST-GAP** | LOW | same as S-05, for the deleted list. Evidence-ordering only. |
| S-07 | L256 dict entry 2 dropped (`"reasoning": 0` removed) | token-accounting dict shape | **OOR/AUDITED** | LOW | **Light-check closed.** Every cost/token consumer reads reasoning via `.get("reasoning") or 0` — [usage.py:64](aisef2/app/usage.py:64), priced as output [usage.py:71](aisef2/app/usage.py:71), [client.py:128](aisef2/app/client.py:128). The `_ocr` value is a constant 0 ([adapters.py:256](aisef2/app/adapters.py:256)); a missing/renamed key defaults to the same 0 → cost and accounting byte-identical. |
| S-08 | L256 string `'reasoning'` emptied (key → `""`) | same dict, key renamed | **OOR/AUDITED** | LOW | sibling of S-07; same resolution (consumers default the absent key to 0). |
| S-09 | L246 `True`→`False` | a flag on `log.parent.mkdir(parents=True, exist_ok=True)` (evidence-dir create) | **TEST-GAP** | LOW | survived ⇒ no kill-test hits the dir-exists / missing-parent case. Robustness of evidence-dir creation. |
| S-10 | L265 `True`→`False` | boolean in the log-write / evidence path (exact bool mapping uncertain at this line) | **UNDET** | LOW | line/bool mapping not confirmed by a quick read; flagged, not self-audited. |
| S-11 | L241 string `'ocr preview '` emptied | `_bounded(…, "ocr preview {story}")` run label | **OOR/AUDITED** | LOWEST | descriptive label passed to `_bounded`; no behaviour. |
| S-12 | L250 string `'ocr review '` emptied | `_bounded(…, "ocr review {story}")` run label | **OOR/AUDITED** | LOWEST | descriptive label; no behaviour. |
| S-13 | L286 string `')'` emptied | punctuation in the coverage-reason format string | **OOR/AUDITED** | LOWEST | cosmetic message formatting. |

## `aisef2/app/run.py::execute` — 356/366 killed, 10 survivors

Soundness note: this target's `kill_tests` include `test_v21_continue_integrity.py`, so the 356/366 head
number is **gated on A-03** (sound only if that T0 is sound). This run's T0 was clean (0 INFRA/NOT_RUN ⇒ the
control baseline passed, continue_integrity included) — `execute` is a *share-the-kill-test* target, not one
with an observed T0 FAIL (that was `_create` only). Scope of the 10 survivors: all in run-record
serialization or refusal-*message* text; none of the surviving mutants alters a decision, data, secret,
access, or execution-authority line. "No surviving mutant alters X" ≠ "the product has no X defect."

| id | mutant | what it changes | class | prio | grounds / consumption path |
|----|--------|-----------------|-------|------|----------------------------|
| S-14 | L484 `'--parent '` emptied | text of `RunRefused(f"--parent {predecessor}: no run record there")` | **OOR/AUDITED** | LOW | the refusal still raises on the same condition (no record at predecessor); only the message text differs. **Light-check closed by survival:** surviving all 18 kill-tests — including the lineage/refusal-path tests — is the evidence that no test or consumer matches this refusal's message string (a message-asserting test would have failed on the emptied string). |
| S-15 | L486 `'--parent '` emptied | text of `RunRefused(f"--parent {predecessor}: {e}")` (LineageRefused re-wrap) | **OOR/AUDITED** | LOW | same guard, same raise; message text only. |
| S-16 | L486 `': '` emptied | separator in the same re-wrap message | **OOR/AUDITED** | LOW | sibling of S-15. |
| S-17 | L530 `'the lineage of '` emptied | text of the `unread` lineage `RunRefused` | **OOR/AUDITED** | LOW | the `if inherited["unread"]` guard (L529) still raises; message text only. On the cost/provenance path, but the *condition* is unchanged. |
| S-18 | L492 `'repository'` emptied | `rec["stage"] = "repository"` → `""` | **OOR/AUDITED** | LOW | `rec["stage"]` is a progress breadcrumb overwritten at L512 (`"ocr identity"`) before any read. Decision-neutral. |
| S-19 | L499 `'\n'` emptied | trailing newline of the STARTED file | **OOR/AUDITED** | LOWEST | JSON parses without the trailing newline; cosmetic. |
| S-20 | L677 `'\n'` emptied | trailing newline of the MANIFEST file | **OOR/AUDITED** | LOWEST | cosmetic; MANIFEST still valid JSON. |
| S-21 | L499 `sort_keys=True`→`False` | key order of the STARTED file JSON | **OOR/AUDITED** | LOW | **Light-check closed.** verify is anchor-faithful: `evidence_manifest` records `_content_sha(STARTED)` ([run.py:434](aisef2/app/run.py:434)) — the *actual* bytes, whatever their key order — so `--verify` (content-sha vs recorded sha) is never broken by order. Order feeds only the run's own anchor *value* (via that content-sha), self-consistently; no test or consumer pins STARTED to a sorted form. Decision- and provenance-neutral. |
| S-22 | L677 `sort_keys=True`→`False` | key order of the evidence MANIFEST file JSON | **OOR/AUDITED** | LOW | **Light-check closed.** The anchor is **invariant** to the manifest file's key order: `anchor_in` does `json.loads` then `anchor_of`, which re-serializes with `sort_keys=True` before hashing ([run.py:440,447](aisef2/app/run.py:447)). Nothing recomputes the manifest expecting the file's own key order. Decision- and provenance-neutral. |
| S-23 | L491 dict entry 6 dropped | the `rec["stage"]` field (entry 6, 0-based: format,bundle_digest,project,plan_hash,settings,started,**stage**,…) | **OOR/AUDITED** | LOW | **Light-check closed; field identified = `stage`** (not `started`; dropping `started`=entry 5 was KILLED). `stage` is a per-phase progress breadcrumb reassigned at L512/519/549/558/562/566/570/590/644 and read only via `rec.get("stage")` (L666, KeyError-safe) + the RUN.json dump. On the normal path L512 recreates the key before any read → zero effect. Only an error *before* L512 leaves the record's stage breadcrumb absent/None instead of `"repository"`. Not consumed by verify, the anchor, or any decision. |

## Carry-forward

**Tally by class (23 survivors, owner split — exactly one label each):** **EQUIV** 2 (S-01, S-02) ·
**OOR/AUDITED** 17 (S-03, S-04, S-07, S-08, S-11–S-23) · **TEST-GAP** 3, open & public (S-05, S-06, S-09) ·
**UNDET** 1, open & public (S-10) · **BUG** 0. No HIGH-priority survivor through `_attempt`+`_ocr`+`execute`;
`execute`'s decision logic was fully killed (356/366), survivors are record-serialization + diagnostic-text
only. No original-code defect confirmed within the tested scope. **`BUG 0` is not the risk measure** (owner
2026-10-30): risk is consequence × evidence — the full 9-target consequence×evidence assessment is in
`HANDOFF-INTERIM.md`, and some rows there stay open on LIGHT evidence rather than being called safe.

**S-01 / S-02 — final-conclusion argument (owner: must be traceable from the initial TEST-GAP finding):**
  1. *Initial finding:* **HIGH TEST-GAP** — a candidate-side re-proof of a committed PRESERVE obligation
     (V21-38) whose role argument the suite did not pin; suspected it could let a developer regression through.
  2. *Bounded impact analysis (owner step 3; no code/test):* traced `role` through the candidate path — it
     reaches only `route()` ([proof.py:107](aisef2/orchestrate/proof.py:107)); every CANDIDATE routing row is
     role-agnostic (keyed `None`, [routing.py:81-86](aisef2/control/routing.py:81), with a role-`None`
     fallback at [routing.py:125](aisef2/control/routing.py:125)); `role` is not in `verified_payload` and not
     on the `Proof` dataclass ([proof.py:29](aisef2/orchestrate/proof.py:29)); the loop pins
     `point=CANDIDATE` ([story_runner.py:277](aisef2/orchestrate/story_runner.py:277)).
  3. *Answer to the 3-way question:* **(c)** — decision-neutral on the path in use; **not** (a)
     accept-a-regression and **not** (b) corrupt-evidence-but-still-catch. A developer regression of the
     PRESERVE obligation is still caught role-independently via `contract_satisfaction`→
     CONTRACT_UNSATISFIED/DEVELOPER.
  4. *Final class:* **EQUIV** — the differing role value produces no observable difference in any decision,
     stored evidence, or journal. Not a test gap relabelled to pass (owner rule 1): shown to change nothing
     observable, not merely declared equivalent. *Residual:* the equivalence is contingent on the current
     role-agnostic CANDIDATE routing; a future role-keyed CANDIDATE row would make the line live → **C-03**
     hardening note (pin it with a test), **not** a release blocker.

**Light-checks closed by reading code + evidence (2026-10-30) — each a difference *out of mandatory
requirement, with grounds*, i.e. OOR/AUDITED, not EQUIV:** S-03/S-04 (journal label only, not an
identity/release key); S-07/S-08 (`reasoning` folds into the CLASSES-fixed totals, defaulted to 0 by every
consumer — cost byte-identical; only the transient per-call dict shape differs); S-14..S-17 (refusal raises
on the same condition, only the message text differs; survival shows no consumer matches the string);
S-18/S-23 (`stage` breadcrumb value/presence, overwritten on the normal path, differs only on an early-error
path); S-19..S-22 (STARTED/MANIFEST trailing newline and key order — verify is content-sha-faithful to the
actual bytes, the MANIFEST anchor re-sorts and is invariant to file key-order).

**Still open & public (carried to the final handoff, no per-group decision round):** S-05, S-06 (session
evidence list ordering determinism — **not** proven out-of-requirement, so it stays **TEST-GAP**, not
relabelled OOR); S-09 (missing-parent `mkdir(parents=…)` robustness — **TEST-GAP**); S-10 (`_ocr` L265 bool
mapping unconfirmed — **UNDET**, not self-audited).

- `verify.py::verify` (w1, in progress) and the remaining 85 targets append rows here as records land, each
  carrying exactly one class.
