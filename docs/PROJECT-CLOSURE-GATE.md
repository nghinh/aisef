# AISEF Project Closure Gate

**Status: DRAFT — awaiting owner approval. Not in force.**
Drafted 2026-09-14 against `v1.6.0` + 18 commits. Every number below carries the
command that produced it; re-run them rather than trusting this document.

This document answers one question the repository could not previously answer:
**what has to be true for the AISEF engineering project to be declared
complete?** It is a product/acceptance contract, so its content is the owner's
decision, not the framework's and not an agent's.

---

## 1. Why a successor gate is needed, stated precisely

The only exit condition ever written in command-checkable form is
`docs/ACTION-PLAN-2026-09-05.md:344`:

> **Điều kiện phát hành** (đọc được bằng lệnh, không phải cảm giác):
> * 100 % test unit xanh; `CONFORMANCE.md` ≤ 14 ngày, không ô ✗;
> * `par` chạy lại trên hai client đạt mốc R5;
> * `e9` EPIC-01 xong, `ACCEPTANCE-REPORT.md` có bảng TCCN → test id, mục
>   `accessibility` là PASSED hoặc FAILED — **không** phải UNCONFIGURED;
> * `pip install aisef` trong venv sạch → `setup` → `doctor` xanh.

Bullets 2 and 3 name `par` and `e9`. Neither directory exists on this machine:

```
for d in calc par e9; do [ -d ~/Downloads/projects/$d ] && echo "$d EXISTS" || echo "$d absent"; done
# → calc absent · par absent · e9 absent
```

So two of four bullets are **permanently unsatisfiable as written**, and no
amount of work closes them. A gate that cannot be evaluated is not a gate.

**ADR-006's substitution has itself decayed.** ADR-006 (2026-09-08) already
faced this once and substituted for `e9`, resting the replacement on three
things: `par` as the Node.js corpus, the bench suite as the second project, and
a proposed third project `calc`. Today `par` is gone, `calc` was never created,
and the bench suite's discriminating power has been measured:

```
python3 validation/bench_discriminating_power.py
# → 12 of 340 cross-arm pairs informative (3.5 %); 25 of 30 tasks never separated the arms
```

This is not a criticism of ADR-006 — its reasoning was sound and is the
precedent this document follows. It is the reason a substitution must be
**re-verifiable**, not a one-time swap: the replacement corpus has to be
something a command can still find.

---

## 2. Authority, precedence, and what this document does *not* do

On approval, this document becomes the **single authoritative** closure
definition, and supersedes the closure/exit role of:

| document | what happens to it |
|---|---|
| `ACTION-PLAN-2026-09-05.md:344` | superseded **as a gate**; kept verbatim as a dated record |
| `V1-READINESS.md` §"Requires real agent runs — BLOCKED" (B1–B4) | superseded; each item re-classified in §7 |
| `ADR-006` | **not** superseded — its substitution *rule* is adopted in §3 |
| `ROADMAP-POST-1.0.md` | remains a priority list; explicitly **not** a gate |
| `RELEASE-RECORD-v1.0.0.md`, `RELEASE-CHECKLIST-v0.1.0.md`, `-v0.3.1.md` | untouched dated records of releases that did happen |

**Three things this document must not do**, and does not:

1. **No historical evidence is rewritten.** Superseded text stays where it is
   with a dated pointer here. This follows the rule `BENCH-REPORT-C1.md` already
   states as policy: observations are not corrected after the fact.
2. **No criterion is weakened to obtain PASS.** §8 reports what fails today, and
   three of six gates fail.
3. **No lost corpus is silently replaced by a convenient one.** §3 constrains
   when substitution is legitimate.

---

## 3. The substitution rule, inherited from ADR-006

ADR-006 §1 states the principle:

> The exit condition tests *framework robustness across project types*, not a
> specific project.

Adopted, with two conditions added because ADR-006's own substitution decayed:

- **R1 — same property.** A replacement corpus is legitimate only if it
  exercises the *same property* the original tested. `e9` tested "a real
  multi-story epic completes end-to-end with real agents." A living corpus that
  also completes a real multi-story epic end-to-end satisfies R1. The bench
  suite does **not** satisfy R1 for that property — it tests per-task bug
  fixing, not lifecycle completion — and counting it as "a project" was the
  weakest step in ADR-006.
- **R2 — locatable by command.** The gate names corpora by a path a command can
  resolve, and reports `UNRUNNABLE` when it cannot. A corpus named in prose that
  no command can find is how this problem arose twice.

### Living corpora, measured 2026-09-14

```
for p in ~/Downloads/projects/*/; do ... sprint-status.json, evidence/, reviews/, approvals/, pre-deploy-report.json
```

| corpus | stories | evidence | reviews | upstream approvals | pre-deploy report |
|---|---|---:|---:|---:|---|
| `todo-oc` | **7 done, 0 failed** | 13 | 28 | 7 of 7 | yes (`passed: false`) |
| `todo-e2e` | 9 done, 1 failed | 16 | 44 | 7 of 7 | no |
| `todo-cli` | 7 done, 4 failed | 17 | 48 | 7 of 7 | no |
| `todo` | 3 done, 1 failed | 10 | 26 | 7 of 7 | no |
| `marks-cli` | 2 done, 1 failed | 8 | 10 | 7 of 7 | no |
| `bread`, `goe`, `todo-e3` | none / partial | 0–4 | 0 | 0–2 | no |

`todo-oc` is the only corpus with **zero failed stories**. `marks-cli` is the
corpus that surfaced this wave's defects (148, 155, 156). G4 has to choose
between complete-but-older and exercises-the-fixes-but-incomplete; §5 G4 states
how.

---

## 4. Machine-readable representation and the evaluating command

### 4.1 Vocabulary — reused, not invented

The outcome vocabulary the contract needs **already exists** in the codebase and
must be reused so the closure gate speaks the same language as every story gate:

```
python3 -c "from aisef.control.gate import Outcome; [print(o.name, o.blocks) for o in Outcome]"
# PASSED False · FAILED True · UNRUNNABLE True · UNCONFIGURED False · WAIVED False · NOT_APPLICABLE False
```

| outcome | closure meaning |
|---|---|
| `PASSED` | evidence exists, is fresh, and satisfies the criterion |
| `FAILED` | evidence exists and contradicts the criterion. **Blocks.** |
| `UNRUNNABLE` | the criterion could not be evaluated — corpus absent, command missing, evidence unreadable. **Blocks.** Never silently a pass. |
| `WAIVED` | a human approver accepted the gap, with a reason recorded. Does not block. Only where §5 marks the gate waiver-eligible. |
| `NOT_APPLICABLE` | the criterion does not apply to this project shape, with the reason recorded |
| `UNCONFIGURED` | **not accepted at closure.** Any `UNCONFIGURED` is promoted to `UNRUNNABLE` — "nobody configured the check" is not evidence of health. |

That last row is a deliberate tightening. `UNCONFIGURED.blocks` is `False` for
story gates, which is correct there (a project need not configure every
verification kind). At closure it would let an unconfigured check read as
absolution, which is the exact failure mode found in §8.

### 4.2 The criteria file — `docs/closure-gate.json`

Checked into the repository, versioned, and **digest-pinned**. Shape:

```json
{
  "contract_version": "1",
  "contract_sha256": "<digest of PROJECT-CLOSURE-GATE.md at approval time>",
  "gates": [
    {
      "id": "G3",
      "title": "Client conformance",
      "waiver_eligible": false,
      "requires_human": false,
      "criteria": [
        {
          "id": "G3.1",
          "statement": "every first-class client has a passing conformance column",
          "probe": "aisef.control.conformance:release_ready",
          "evidence": "docs/CONFORMANCE.md",
          "freshness": {"kind": "age_days", "max": 14, "source": "report.generated"}
        }
      ]
    }
  ]
}
```

`probe` names a Python callable already in the package wherever one exists, so
the gate reads the **same reader** the framework itself uses. This mirrors a
pattern the repo already relies on: the reviewer-qualification table is read
"through the **same** reader as the gate table, `gate.controls_in`". A closure
gate with its own private readers could pass while the product fails.

### 4.3 The command — `aisef closure`

```
aisef closure                 # evaluate, print table, write closure-report.json, exit 0/1
aisef closure --report        # regenerate docs/CLOSURE-REPORT.md from the last evaluation
aisef closure --waive G6.3 --reason "..."   # record a waiver (refuses without a reason)
aisef closure --approve       # human signature; refuses unless every gate is non-blocking
```

Exit codes follow the repo's existing convention (`gates` exits 2; `aisef tool`
exits 2 on a guard block): `0` closable, `1` blocked, `2` usage error.

Design constraints, each with a reason drawn from a defect this project already
paid for:

- **Read-only.** `aisef closure` evaluates and reports; it never runs a paid
  agent, never mutates a corpus, and never approves itself. `doctor` is the
  precedent.
- **No criterion may be satisfied by its own absence.** Directly from bug 154:
  the release gate's acceptance assertion skipped when `AISEF_ACCEPTANCE` was
  unset and the log read `OK (skipped=1)` — green, on the one assertion that had
  never executed. A skipped closure criterion is `UNRUNNABLE`, which blocks.
- **Waivers are signed and reasoned.** Reuse the existing rule that a waiver
  without a reason is not evidence (`test_release_gate.py` already asserts this
  for pre-deploy waivers) and that waived items render as a diamond, never a
  checkmark.
- **The report is evidence, not a claim.** `closure-report.json` records, per
  criterion: outcome, the evidence path, that evidence's digest, the timestamp,
  and the probe that produced it.

### 4.4 Staleness detection

Reuse the model already in `aisef/control/approvals.py`, which computes `STALE`
from two independent causes: the approved content's digest changed, or an
upstream gate was re-decided afterwards. Applied here:

1. **Evidence digest.** Each criterion's evidence is digested at evaluation.
   An approval binds to the set of digests; if any changes, closure is `STALE`.
2. **Declared freshness window.** Where evidence is inherently time-bound, the
   criterion declares its own window and the source field it reads. Conformance
   uses the framework's own `MAX_AGE_DAYS = 14` rather than a second number that
   could drift from it.
3. **Contract digest.** If `PROJECT-CLOSURE-GATE.md` changes after approval,
   `contract_sha256` no longer matches and closure is `STALE`. The contract
   cannot be edited into being satisfied.
4. **Explicitly not a heartbeat.** Per your instruction: the gate must **not**
   demand a re-run merely to refresh a still-valid timestamp. Within its window,
   fresh evidence stays fresh, and `aisef closure` says how many days remain.

---

## 5. The six gates

For each: why it is necessary to call the *engineering project* complete, the
exact evidence, semantics, whether a human must decide, and how staleness is
caught.

### G1 — Release integrity

**Why necessary.** A framework whose published artifact does not install and run
is not complete regardless of its source tree. This is the only gate whose
failure is invisible from inside the repository.

| criterion | evidence | probe |
|---|---|---|
| G1.1 CI green on the released tag | GitHub Actions run for `v<version>` | `gh run list --workflow=tests.yml`, matched by commit |
| G1.2 package checks green | `python -m build` + `twine check` | re-run; both must exit 0 |
| G1.3 clean-venv install from PyPI serves the released version | `pip install aisef==<version>` in an empty venv → `aisef --version` | re-run |
| G1.4 runtime package data present in the wheel | `kit/prompts`, `kit/rules`, `kit/skills`, `harness/assets`, `kit/catalog.json` non-empty via `importlib.resources` | the check `.github/workflows/tests.yml` already runs |

**Semantics.** Any FAIL blocks. Network unreachable → `UNRUNNABLE`, which blocks;
"could not check the published artifact" is not "the artifact is fine".
**Human decision:** no. **Waiver-eligible:** no — this gate is entirely
mechanical, and waiving it would waive the product's existence.

**Staleness.** Bound to the release version and the tag's commit. A new release
invalidates G1 and it must be re-evaluated.

**Today: PASSED** (verified 2026-09-14 — CI green on 7 jobs including Windows
3.11; `twine check` passed both artifacts; `pip install aisef==1.6.0` in a clean
venv reported `aisef 1.6.0`; packaged runtime data confirmed).

### G2 — Core correctness

**Why necessary.** The floor below which nothing else is meaningful.

| criterion | evidence | notes |
|---|---|---|
| G2.1 full suite green | `python3 -m pytest -q` in the **main working tree** | must record passed/skipped/subtests |
| G2.2 lint/static gate green | `ruff check .` with the rule set in `pyproject.toml` | |
| G2.3 zero open release-blocking defects | **source must be named — see below** | |
| G2.4 no known false PASS in a blocking *deterministic* check | `docs/FAILURE-TAXONOMY.md` + closed-defect audit | |

**G2.1 must run in the main tree, and the gate must say so.** Measured this
session: a git worktree skips ~61 more tests than the main checkout, because
`.gitignore` excludes `references/*`, `.bench*/`, `.conformance/`, `.dogfood/`.
Main tree: 2682 passed / **19 skipped**. A worktree: ~2608 passed / **80
skipped**. A suite count from a worktree is not comparable, and "skipped" is
indistinguishable from "passed" in pytest's summary line. The probe records the
skip count and the tree it ran in, and `UNRUNNABLE` if the tree is not the main
checkout.

**G2.3 has no source today, and that is a finding.** There is no issue tracker:
`ROADMAP-POST-1.0.md:276` lists "Issue tracker active" as its own unmet
verification. So G2.3 currently evaluates to `UNRUNNABLE`, and **creating the
source is itself a closure item** (§7, REQUIRED_FOR_CLOSE, size S). Proposal:
GitHub Issues with `P0`/`P1` labels, read via `gh issue list --label P0 --state
open`, with the empty result being a real PASS rather than an absence.

**The severity ladder need not be invented.** `EXTERNAL-VALIDATION-v1.1.0.md`
already defines P0–P3, and its P0 includes "**incorrect gate result**" — which is
precisely the false-PASS class G2.4 is about. Reuse that definition for both
G2.3 and G6.3 rather than writing a second one; two severity scales in one
contract is how they drift apart.

**G2.4 is the hardest criterion in the contract and must not be defined away.**
Taken literally — "no known false PASS in a blocking gate" — G2 can never pass,
because `review` is a blocking check and its miss rate is *measured*:

```
python3 -m aisef.control.reviewer_qual ~/Downloads/projects/{todo-cli,todo-e2e,todo-oc,todo}/_bmad-output
# → miss rate 0.3857 · false block 0.1053 (floor) · same-tree verdict reversals 11 of 20
```

The reviewer passes a defective candidate 34–39 % of the time. That *is* a known
false PASS in a blocking gate. Proposed resolution, which I believe is the honest
one rather than the convenient one — **split the criterion by check kind**:

- A false PASS in a **deterministic or structural** check is a *defect*. It must
  be fixed, or closure fails. There are 14 such checks
  (`Counter(CHECK_KIND.values())` → 8 deterministic, 6 structural).
- A measured error rate in the single **`model-judge`** check is a *published
  property*, not a defect — provided three things hold: the rate is measured and
  published, it is recomputable from evidence on disk without a model call, and
  **no blocking decision rests on the judge alone**.

That third condition is currently **not** met and is measurable: 21 of 57 blocks
(36.8 %) rested on the judge's word alone, and on `todo-e2e` 15 of 17 did. So
G2.4 decomposes into G2.4a (deterministic false PASS — today PASSED, none known)
and G2.4b (judge-alone blocking decisions — today **FAILED**). I am flagging
G2.4b as the criterion most likely to need your ruling: it can be read as a
closure blocker or as a POST_CLOSE quality target, and I have placed it as
REQUIRED_WITH_WAIVER_ALLOWED rather than deciding for you.

**Human decision:** only for G2.4b if waived. **Waiver-eligible:** G2.3 and
G2.4b yes; G2.1, G2.2, G2.4a no.

**Staleness.** G2.1/G2.2 bind to the commit digest — any commit invalidates them.
This is intentional and cheap: both are minutes to re-run.

**Today: FAILED** (G2.1 ✅ 2682/19, G2.2 ✅, G2.3 `UNRUNNABLE` no source,
G2.4a ✅, G2.4b ❌ 36.8 % judge-alone blocks).

### G3 — Client conformance

**Why necessary.** Conformance probes the one class of claim unit tests cannot
reach: that a generated hook or plugin actually *blocks* on a real client. Ten
probes, each a real agent session on a real worktree.

| criterion | evidence | freshness |
|---|---|---|
| G3.1 every first-class client has a complete, passing column | `docs/CONFORMANCE.md` via `conformance.parse` + `release_ready` | `MAX_AGE_DAYS = 14`, read from `report.generated` |

**A contradiction to reconcile, and it is in the code.** ADR-006 §4 promoted
OpenCode to **first-class** with full parity. The code disagrees:

```
python3 -c "from aisef.control.conformance import RELEASE_CLIENTS; print(RELEASE_CLIENTS)"
# → ('claude',)          # source comment: "tier 1 — blocks release"
```

`RELEASE_CLIENTS` is a leftover of the pre-ADR-006 decision that OpenCode was
"hạng hai V1". Since your G3 says *all* first-class clients, and ADR-006 says
OpenCode is first-class, the contract requires both — and the code must be
brought into line. This costs nothing today: both columns currently pass 10/10.
It is a REQUIRED_FOR_CLOSE item of size S, and it is a **correctness** change,
not a convenience one — the gate is currently weaker than the ADR it implements.

**Semantics.** Missing column → `UNRUNNABLE`. Any ✗ → `FAILED`. Table older than
the window → `FAILED` with the age. **Human decision:** no.
**Waiver-eligible:** no. A waived conformance gate is the one case where the
framework would be asserting a safety property it has not tested.

**Staleness.** Age-based, from the table's own `generated` date, using the
framework's constant. Per your instruction, no re-run is demanded while the
window is valid; the report prints days remaining.

**Today: PASSED, expiring 2026-09-22.**

```
conformance generated 2026-09-08, today 2026-09-14, age 6d, limit 14d
release_ready → (True, 'conformance complete and current')
```

Both `claude` and `opencode` columns are present and passing. **This is the only
gate with a deadline**: on 2026-09-23 it becomes `FAILED` with no work done, and
re-running costs ~20 real agent sessions (~$1.50). It is also the reason to
settle this contract promptly — an approval that arrives after the window closes
starts with a red gate.

### G4 — Real end-to-end delivery

**Why necessary.** This is the gate that tests the product's actual claim. Every
other gate could pass on a framework that has never delivered software.

**Criterion.** At least one **living** corpus completes the canonical lifecycle
with real agents: requirements → plan → stories → implementation →
deterministic verification → independent review/security → merge → pre-deploy.

| criterion | evidence |
|---|---|
| G4.1 corpus resolvable by path (R2) | directory exists, `_bmad-output/` present |
| G4.2 upstream human gates approved, not stale | `ApprovalStore.status(g) is APPROVED` for all of `GATE_ORDER[:-1]` |
| G4.3 every planned story reaches `done` | `sprint-status.json`, and `_planned_but_never_run` empty |
| G4.4 independent review **and** security ran per story | `evidence/<story>.jsonl` carries `tool_run review` and `tool_run security` |
| G4.5 deterministic verification bound to the merged candidate | gate checks recorded at the merged SHA, not a stale one |
| G4.6 `pre-deploy` report exists and passes, with scope declared | `_bmad-output/pre-deploy-report.json`, `passed: true`, `scope.epic` set |
| G4.7 `PRE_DEPLOY` gate approved against **that** report | `ApprovalStore` + report digest |

**The choice this gate forces, stated rather than hidden.** Your brief prefers a
corpus exercising this wave's fixes. Those pull in opposite directions:

- `todo-oc` — **complete**: 7 of 7 done, zero failed, 7 of 7 upstream approvals,
  28 review artifacts, and a pre-deploy report already generated. But it ran
  *before* bugs 148/154/155/156 were fixed, so it does not exercise them.
- `marks-cli` — **exercises the fixes** (bug 148 was found there, and 155/156
  affect it), but sits at 2 done / 1 failed / 4 never run.

Completing `marks-cli` needs paid agent sessions, which your instruction
forbids until this contract is approved. So G4 is presently blocked on a
decision, not on work. My recommendation, for your ruling: require **one**
corpus to satisfy G4.1–G4.7, prefer `marks-cli` because it exercises the fixes,
and permit `todo-oc` as the fallback if completing `marks-cli` reveals further
defects — with the fallback recorded as a named substitution under R1, not as a
silent swap.

**`todo-oc`'s pre-deploy currently fails for corpus reasons, not framework
reasons** — measured 2026-09-14: `scope`, `all stories done` and `human gates`
pass; `Dockerfile`, `CI workflow`, `runbook`, `isolation` and `verification`
fail because `aisef devsecops` was never run there and Docker is down. Those are
three artifacts and a daemon, not defects.

**Semantics.** No qualifying corpus → `UNRUNNABLE` (blocks). Corpus present but
a criterion contradicted → `FAILED`. **Human decision: yes** — G4.7 is a
signature and `aisef closure` must never auto-approve it. An agent generated
`todo-oc`'s report this session and correctly refused to approve the gate.
**Waiver-eligible:** G4.6's *isolation* sub-check only, via the existing
`sandbox.pre_deploy_degraded_waiver` with its reason, since Docker availability
is an environment fact. G4.1–G4.5 and G4.7: no.

**Staleness.** Report digest + approval binding, exactly as `ApprovalStore`
already does it: re-running `pre-deploy` produces a new digest and the approval
goes `STALE`. Also stale if the corpus's merged SHA moves.

**Today: FAILED** — no living corpus satisfies G4.6/G4.7.

### G5 — Benchmark integrity

**Why necessary.** The benchmark is the project's only quantitative claim about
itself. It does **not** need to show AISEF beating bare — your framing is right,
and this session's measurement makes it the only defensible framing. What must
be true is that the benchmark is honest and reproducible, because a dishonest
benchmark is worse than none.

| criterion | evidence |
|---|---|
| G5.1 methodology pre-registered before data exists | `docs/handoff/bench-real-model-wiring.md` §7, **digest-pinned** |
| G5.2 cut sessions not silently mixed with valid ones | `Result.exit_status` per row; `pass@1` excludes nothing silently |
| G5.3 valid model↔CLI pairing established | a cohort whose cut-session rate is below a declared threshold |
| G5.4 evidence reproducible | `MANIFEST.sha256` matches; `python3 -m tests.bench selfcheck` 19/19 |
| G5.5 noise and inconclusive results reported as such | report states the band or states that the corpus cannot resolve one |
| G5.6 no unreproducible historical claim presented as current evidence | audit of `README*`, `landingpage/`, `docs/SALEKIT.html`, `BENCH-*` |

**G5.1's artifact exists but is mis-housed.** The pre-registration is real —
buy / don't-buy / inconclusive definitions and a recorded prediction, written
before any column-2 data — but it lives in a *handoff* document, which is a
working note. For it to function as pre-registration it must be digest-pinned so
it cannot be edited once data exists. Moving or pinning it is a
REQUIRED_FOR_CLOSE item of size S.

**G5.3 is why the 72-attempt run must not start.** Measured this session:

```
python3 validation/bench_discriminating_power.py
```

All three of C-1b's failing attempts were sessions the CLI **cut**. Under the
attempt definition C-1b's own protocol pre-registered — infra sessions retried,
not graded — all three of its tasks read 1.00/1.00 in **both** arms: 36
attempts, 2.0 hours, 41.9 M tokens, **zero** informative pairs. Its published
+0.06 is an artifact of bug 86, fixed after it ran. Launching column 2 on a pair
with a 22–32 % cut rate buys exactly what C-1b bought. Your instruction not to
run it is therefore also what the evidence says; G5.3 encodes it as a gate
rather than as a note.

**G5.6 already has two confirmed instances, both fixed this session**, which is
why it is a criterion and not an assumption: the landing page asserted
"near-zero measured cost overhead" in the bullet *after* one stating +44 % turns
(C-1 measured +44 % turns, +51 % time), and the ±0.08 noise band was derived
from C-1b's artifact delta. The "36× cost gap" between `e9` and `par` is the
standing example of a historical claim that cannot be reproduced and is now
labelled as such.

**Semantics.** G5.1/G5.4 mechanical. G5.3 `UNRUNNABLE` until a qualifying pair
exists — blocking, and honestly so. G5.6 `FAILED` on any instance found.
**Human decision:** no, except to waive G5.3. **Waiver-eligible:** G5.3 only,
because it can require an endpoint the project cannot procure; waiving it means
closing with the second column unrun, which must be stated in the closure record
rather than implied.

**Today: FAILED** (G5.3 `UNRUNNABLE` — no cut-session-free pair established;
G5.1 needs pinning; G5.2, G5.4, G5.5 pass; G5.6 passes as of this session's
corrections).

### G6 — External validation

**Why necessary.** Every other gate is the author measuring the author. ADR-006
§2 deferred this for v1.0.0 on a sound argument — users will not adopt a
framework that never ships — but that argument expires once the framework *has*
shipped, which it has: v1.0.0 through v1.6.0 are on PyPI. The chicken-and-egg is
resolved, so the deferral no longer holds.

**Criterion.** At least one person who did not implement AISEF executes the
canonical public workflow, with a record containing: install success; time to
first success; undocumented steps encountered; author interventions required;
framework defects found; user blockers.

**The protocol for this gate already exists and does not need designing.**
`docs/EXTERNAL-VALIDATION-v1.1.0.md` is a **protocol, not a record** — it opens
with "v1.1.0 ships when an external user completes the full lifecycle without
author intervention" and its exit criteria are a checklist of **unchecked boxes**
(`grep -c '^- \[ \]'`). So it is the plan for G6, and G6 is an *execution* gap.
Three things there are directly reusable, which is why G6 needs less new
machinery than I first assumed:

- its **Metrics** table already collects every field your brief requires
  (install success, time to first success, undocumented steps discovered,
  clarification requests, framework bugs, full lifecycle completed) plus cost and
  confidence;
- its **Finding classification** already defines P0/P1/P2/P3 — P0 is "cannot
  install, data loss, security issue, **incorrect gate result**", P1 is "cannot
  complete lifecycle without author assistance";
- it already declares the record's path:
  `docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md`, which does **not** yet exist.

| criterion | evidence |
|---|---|
| G6.1 the validation **report** exists at the path the protocol declares | `docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md`, carrying the protocol's Metrics fields |
| G6.2 the participant did not implement AISEF | stated in the report; the protocol's own wording is "genuinely external" |
| G6.3 no unresolved P0/P1 onboarding blocker | severities per the protocol's Finding classification, each resolved or waived |

I am **not** counting the protocol's existence as satisfying this gate, and the
distinction matters: a protocol is a design, a report is evidence.

Two of that protocol's own exit criteria are now independently satisfied and can
be marked so without re-running anything: "Clean `pip install aisef` verified on
fresh venv" (G1.3, verified 2026-09-14) and "OpenCode+Serena write-scope
behaviour resolved or documented" (`".serena"` is in `HARNESS_OWNED`, fixed in
v1.3.0). A third — "Claude Code **and** OpenCode conformance green (10/10)" — is
independent support for the `RELEASE_CLIENTS` correction in G3: this protocol
already treats both clients as release-relevant.

**Semantics.** No record → `UNRUNNABLE` (blocks). Record present with an
unresolved P0/P1 → `FAILED` unless waived. **Human decision: yes** — G6.3's
waiver is explicitly yours per your brief. **Waiver-eligible:** G6.3 yes; G6.1
and G6.2 no, because waiving the existence of external validation returns the
project to measuring only itself.

**Staleness.** Bound to the released version the participant used. A record
against a version more than one minor behind should be flagged, not auto-failed
— the onboarding path changes slowly. I suggest you set that tolerance; I have
put one minor version in the draft schema and flag it as a value I chose
arbitrarily.

**Today: UNRUNNABLE** — no audited record. This is the gate with the longest
lead time, because it needs a volunteer, and it is the one item no amount of
engineering effort can buy.

---

## 6. Summary of today's honest verdict

| gate | today | blocking reason |
|---|---|---|
| G1 Release integrity | **PASSED** | — |
| G2 Core correctness | **FAILED** | G2.3 no defect source; G2.4b 36.8 % judge-alone blocks |
| G3 Client conformance | **PASSED** | expires 2026-09-22 |
| G4 Real end-to-end delivery | **FAILED** | no corpus with a passing, approved pre-deploy |
| G5 Benchmark integrity | **FAILED** | G5.3 no cut-session-free model↔CLI pair |
| G6 External validation | **UNRUNNABLE** | no audited record |

**2 of 6 pass.** I have not softened anything to improve that ratio; where a
criterion looked unpassable I split it by kind and said so (G2.4) rather than
lowering it.

---

## 7. Classification of every remaining item

Sources reconciled: `ACTION-PLAN-2026-09-05.md`, `V1-READINESS.md`, `ADR-006`,
`ROADMAP-POST-1.0.md`, ADR-009 §Deferred, every `docs/handoff/*` "left open"
section, and the release/evidence records.

### REQUIRED_FOR_CLOSE

| item | gate | size | source |
|---|---|---|---|
| Name a release-blocking-defect source (tracker + labels) | G2.3 | S | new — G2 has no source today |
| `RELEASE_CLIENTS` to include `opencode`, matching ADR-006 §4 | G3 | S | code contradicts ADR-006 |
| Pin the bench pre-registration by digest | G5.1 | S | `handoff/bench-real-model-wiring.md` §7 |
| Establish a model↔CLI pair without session-cut contamination | G5.3 | M | `BENCH-REPORT-C1B.md:98` |
| Complete one living corpus through pre-deploy | G4 | M | §3, §5 G4 |
| `aisef devsecops` artefacts for the G4 corpus (Dockerfile, CI, runbook) | G4.6 | S | measured on `todo-oc` |
| One external participant runs the public workflow | G6 | L (calendar) | ROADMAP #1 |
| Conformance re-run **if** the window lapses | G3 | S | deadline 2026-09-22 |
| Implement `aisef closure` + `docs/closure-gate.json` | all | M | this document |

### REQUIRED_WITH_WAIVER_ALLOWED

| item | gate | why a waiver is defensible |
|---|---|---|
| Judge-alone blocking decisions (36.8 %) | G2.4b | a measured, published property of a model-judge check; **your ruling requested** |
| Column-2 benchmark run | G5.3 | may require an endpoint the project cannot procure |
| Sandbox isolation in the G4 pre-deploy | G4.6 | Docker availability is an environment fact; mechanism already exists |
| Unresolved P0/P1 onboarding blockers | G6.3 | explicitly yours per the brief |
| The 4 remaining uncorroborated REOPENED entries | G2.4a | one run where the test tool never started; a distinct semantics decision |

### POST_CLOSE

Benchmark expansion to ≥3 languages / ≥3 task classes · behaviour-scoped
preservation replacing file-overlap · distributed execution · PyPI organisation
account · `aisef skill --scan` · tool/CLI optimisation · machine-readable
`[stuck] trace:` record (O2) · per-branch `run_id` for `mockup_verify` ·
cross-UID `flock` · retire `framework/bench/cost_decomp` · `write_scope_ignore`
escape hatch · `_analyze.cut_sessions` ledger-name collision · `aisef cost`
becoming a threshold · `Ledger.summary()` consumers beyond report/dashboard.
Reasoning for the six you named is in §8.

### OBSOLETE / SUPERSEDED

| item | why |
|---|---|
| `ACTION-PLAN:344` bullets 2 and 3 (`par` R5, `e9` EPIC-01) | corpora absent; superseded by G4 under R1. **Text preserved** as a dated record |
| `V1-READINESS` B2 (`par` baseline) | corpus absent; property now tested by G4 |
| `V1-READINESS` B3 (`e9` EPIC-01, 4 stories) | corpus absent; property now tested by G4 |
| `V1-READINESS` B4 (acceptance report after B3) | depends on B3; superseded by G4.6/G4.7 |
| The 15 `e9` gaps | evidence tree gone; already labelled unverifiable in ADR-004 |
| The 36× `e9`/`par` cost gap | unreproducible; already labelled historical in ADR-009 |
| ADR-006 §1's "bench suite counts as the second project" | fails R1 — the bench tests per-task bug fixing, not lifecycle completion. ADR-006 otherwise stands |
| ADR-006 §1's proposed `calc` project | never created; `todo-*` corpora serve the purpose |
| ROADMAP memory "pending" queue | superseded by ADR-007's FROZEN addendum |
| `V1-READINESS` as a gate | superseded entirely; retained as historical record |

---

## 8. Explicit BLOCK vs POST_CLOSE rulings on the six items you named

You asked me not to make these blockers merely because a roadmap lists them.

**1. Benchmark expansion to ≥3 languages and ≥3 task classes — POST_CLOSE.**
Currently 1 language, 1 source project, 30 tasks, so only the count bar is met.
It stays out because **G5 asks for honesty, not coverage**. An expanded corpus
would improve external validity; it does not make the existing measurement more
truthful, and this session's finding is that the bottleneck is not breadth but
resolution — 25 of 30 tasks never separated the arms. Expanding before fixing
the cut-session contamination would add 3 more languages of noise. Blocking
closure on it would also conflict with G5's explicit "does NOT require AISEF to
beat Bare".

**2. Behaviour-scoped preservation replacing file-overlap — POST_CLOSE.**
Tempting to block, because the measurement is damning: file overlap holds for 27
of 32 stories and ρ = 0.235, so the predicate barely ranks the risk it exists to
measure. It stays POST_CLOSE because the current behaviour is **conservative in
the safe direction** — the weight is 0.0, so the dimension is inert and blocks
nothing incorrectly. It is a missed-detection weakness, not a false-pass defect,
and G2.4a is about false passes. It is the strongest POST_CLOSE candidate on
this list and I would expect it to be the first post-closure work.

**3. Distributed execution — POST_CLOSE, and arguably OBSOLETE.**
ADR-006 §3 already ruled it out of v1.0, and `ROADMAP-POST-1.0.md:235` marks it
P3 "no user has asked for this". Nothing has changed. Blocking closure on
unrequested distributed-systems work would be the clearest possible case of
letting a roadmap entry masquerade as a requirement.

**4. PyPI organisation account — POST_CLOSE.**
The property that matters to closure is "the published artifact installs and
runs", which G1.3 tests directly and which **passes today** under the current
publishing identity. Account ownership is governance, not engineering
completeness. It should still be done — a single-owner trusted publisher is a
continuity risk — but as an operational task, not a closure blocker.

**5. Skill scanning (`aisef skill --scan`) — POST_CLOSE.**
It refreshes the skill registry against upstream sources. No closure gate
depends on skill freshness, `skills.offer` is off by default, and its
"used" path has never been measured on a real run. Blocking on a paid refresh of
an optional, default-off subsystem inverts the priority.

**6. Tool/CLI optimisation — POST_CLOSE.**
No gate measures latency or ergonomics, and none should: "the project is
complete" is a claim about correctness and honesty, not polish. If a specific
CLI defect blocks onboarding it arrives through G6.3 as a P0/P1 blocker, which
is the correct route.

---

## 9. What I did not do, and the decisions I am handing you

**Not done, deliberately:** I wrote no code. `aisef closure`,
`docs/closure-gate.json`, and the `Gate.CLOSURE` approval entry are *designed*
in §4 and unimplemented, per your instruction. No paid run was launched. No
historical document was edited — this document names what it supersedes and
nothing else changed.

**Decisions I need from you:**

1. **G2.4b** — is a 36.8 % judge-alone blocking rate a closure blocker or a
   published property? I placed it as waiver-eligible rather than deciding.
2. **G4's corpus** — complete `marks-cli` (exercises this wave's fixes, needs
   paid runs) or accept `todo-oc` (complete, predates the fixes) as a named R1
   substitution?
3. **G5.3** — is closing with column 2 unrun acceptable via waiver, or must a
   clean model↔CLI pair be found first?
4. **G6's staleness tolerance** — I put "one minor version" in the draft
   schema. That number is arbitrary and yours to set.
5. **G3's deadline** — conformance expires **2026-09-22**. Approving after that
   date starts with a red gate and a ~$1.50 re-run.

**One thing I want to flag as a risk in my own draft.** G2.3 and G5.1 are items
this document *creates* — a defect-tracking source and a pinned
pre-registration. Neither existed before I wrote this. That is legitimate: a
gate may require the evidence it needs to exist. But it means approving this
contract commits to two small pieces of work that no prior document asked for,
and you should approve them knowingly rather than discover them during
evaluation.
