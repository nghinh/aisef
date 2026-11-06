# Wave-2 mutation survivor gaps — risk classification & prioritized hardening list (owner #3)

Owner #3 (2026-11-06): *Acknowledge the 236 real gaps. Classify by risk level, invariant impact, control path, and exploitability. Present a prioritized hardening list; do NOT expand the registry or change acceptance criteria.*

Method: every survivor gap was classified by an independent agent (severity / on-control-path / invariant-impact / exploitability / kill-test), and **every** hot gap (critical|high, or on-control-path, or direct-exploit) was then **adversarially re-examined** by a second agent instructed to either produce a concrete guarantee-defeating scenario (uphold) or prove it benign (downgrade). 149 of 238 gaps went through that second pass. Source data: [MUTATION-WAVE2-HARDENING-PRIORITY.json](./MUTATION-WAVE2-HARDENING-PRIORITY.json); upstream campaign classification: [MUTATION-WAVE2-CLASSIFICATION.json](./MUTATION-WAVE2-CLASSIFICATION.json).

## 0. The one-line finding

**0 critical. 11 high (all adversarially verified), 41 medium, 186 low. All 11 high gaps are killable by adding tests — no product-code change, no registry change, no acceptance-criteria change.** These are **survived mutants**: the shipped code is correct today; a survived mutant means *no test would catch a regression* on that line. So this list is regression-guard coverage, not a list of live defects.

Count note: the campaign headline was "236 real gaps" (247 distinct survivors − 11 equivalent). The classifier read 238 gap entries across the 26 units; the 2-entry difference sits at the equivalence boundary and does not change any conclusion (still 0 critical).

## 1. Severity distribution

| severity | count | on control path | direct-exploit |
|---|---|---|---|
| critical | **0** | — | — |
| high | 11 | 11 | 9 |
| medium | 41 | — | 0 |
| low | 186 | — | 0 |
| **total** | **238** | 114 | 9 |

All 9 direct-exploit gaps are high. The remaining 2 high are indirect (need a second, independent kernel-integrity defect to bite). No medium or low gap is directly exploitable.

## 2. The 11 HIGH gaps → three hardening work items

Every high gap traces to one of three test-coverage root causes. Fixing those three kills all 11 (and incidentally most of the medium cluster on the same functions).

### P1 — `run.execute()` is never driven with a pinned/fenced settings (4 high, all DIRECT)

| # | mutant | what regresses undetected | invariant |
|---|---|---|---|
| 1 | `run.py` `'client_pin'` emptied | pre-run binary-pin check (`review_ocr.pinned` → `RunRefused`) disabled; run silently uses PATH binary; `rec['client_pin']` absent from RUN.json | D4 pinned-client gate; adjacent INV-MUTATION-AUTHORITY (authority only from operator's pin) |
| 2 | `run.py` `'client_fence'` emptied | a **declared** client fence (run-scoped XDG + OPENCODE_PERMISSION allow-list + output-token ceiling) silently ignored; client runs host-wide while operator believes it's fenced | IV Typed Ownership / confinement bound |
| 3 | `run.py` pin_sha256 kw entry dropped (×2) | per-session moment-of-use re-check (`client.py` `pinned()` → `SessionRefused`) dead; a binary swapped between pre-run check and exec runs unverified while RUN.json still attests `client_pin: PASSED` (TOCTOU provenance forgery) | D4, spirit of VI Immutable Provenance |

**Root cause:** no test drives `run.execute()` with a `settings` carrying `client_pin`/`client_fence`. The existing `tests/v2/test_v22_client_pin_fence.py` exercises `settings.load`, `client.environment`, and `client.session` **directly** (passing the fence/pin itself), so the glue in `execute()` that wires them is untested, and `getattr(settings,'',None)==None` is indistinguishable from "absent" in the stand-in settings the other tests use.

**Hardening (test-only, highest priority):** one integration test that drives `run.execute()` with a settings declaring both a `client_pin` (mismatched → assert `RunRefused` names `client_pin`, no session/request started; matched → assert `rec['client_pin'].status=='PASSED'`, resolved exe == `pin['exe']`, and the session kw carries `pin_sha256`) and a `client_fence` (assert `out/client-xdg/{data,state,cache}` built and the session kw `fence` carries `str(repo)` in its allow-list + the token ceiling). A stronger variant swaps the binary after the pre-run check and asserts `SessionRefused`. This single test kills all 4 and most of the 21 medium `execute` gaps.

### P2 — tripwire serve-surface fixtures are too clean (6 high: 5 DIRECT, 1 indirect)

| # | mutant | what regresses undetected | invariant |
|---|---|---|---|
| 5 | `_bundle_hit` `except ValueError` → `None` / `False` | the deliberate fail-closed ("refuse rather than guess") for a **marker-bearing but non-JSON** bundle flips to CLEAN; a corrupted/partial project bundle in the served tree is no longer refused | III developer-independence / DEVELOPER-CONFINEMENT-GAP-001 |
| 6 | `_canonical` `,` / `:` separator emptied | composite (list/dict) needles lose their JSON separators and can never match a correctly-serialized leak; all-scalar observables (`grep_count`, `python_imports`, `exists`) are fully blinded | same |
| 7 | `scan_text` `ensure_ascii` False→True | the JSON-escaped-spelling clause scans for the `\uXXXX` form while the kernel serializes everything `ensure_ascii=False`; a non-ASCII sealed needle in its real spelling scans CLEAN | same |
| 8 | `_fragments` drop `tuple` from `isinstance(value,(list,tuple))` | **frozen** specs (production runs `freeze()` → every array is a tuple) stop recursing into array elements; nested string leaves never become needles. Invisible in the suite because fixtures use unfrozen lists | same (II harness-owned-probes) |

**Root cause:** the tripwire fixtures feed valid JSON, all-ASCII needles, and plain (unfrozen) lists — so the fail-closed `except` arm, the comma/colon separators, the non-ASCII escaped spelling, and the frozen-tuple recursion are never asserted. The `_fragments` one is the most important: it is **silently broken in production** (specs are frozen) while every test passes.

**Hardening (test-only):** four targeted assertions — `_bundle_hit('aisef-v2-project/1 {not json', project) is True`; `_canonical([1,2,3])=='[1,2,3]'` and `_canonical({"a":1})=='{"a":1}'`; a non-ASCII+JSON-metachar needle hit through the escaped clause; `'…leaf…' in _fragments((('expect','…leaf…'),))` (frozen-tuple recursion). No product change.

### P3 — `register_runtime` missing-CODE-attribute not asserted fail-closed (1 high, INDIRECT)

| # | mutant | what regresses undetected | invariant |
|---|---|---|---|
| 9 | `register_runtime` `MechanismKind.CODE`→`STATIC_RULE` | the runtime loop stops resolving each CODE enforcement attribute; a CODE mechanism whose module still imports but whose attribute was deleted/renamed no longer fails closed, yet RUN.json's RUNTIME_STATEMENT still attests "every CODE mechanism resolved" | §4 registry invariant + runtime-arming attestation |

Indirect: it only bites when a *second* kernel-integrity defect (a missing-but-importable CODE attribute) is present — exactly the condition this guard exists to catch. A fully non-importable module is still caught by `runtime_mechanism_digest`; an actively-invoked mechanism still crashes at its call site.

**Hardening (test-only):** `assertRaises(RegistrationError)` when a full I–IX registry has one Invariant whose CODE mechanism ref names a present module but a missing attribute; plus assert `register_runtime` still succeeds when a STATIC_RULE ref is broken but every CODE mechanism resolves.

## 3. Medium (41) and low (186)

- **Medium (41):** 21 on `run.execute` (same pin/fence/record-field cluster as P1 — the P1 test covers most), 6 on `register_runtime` (operator/condition mutants dominated by the P3 test or by the unmutated id-list check), the rest scattered diagnostic/record-field drops with `exploitability=none`. None directly exploitable; none change a verdict oracle.
- **Low (186):** diagnostic strings, record formatting, digest-internal byte arrangements with a downstream digest that re-derives, and error-message wording. By design `reserve LOW for pure diagnostic with no downstream consumer`. No hardening warranted; listed for completeness in the JSON.

## 4. Recommended order & scope guard

1. **P1** — `run.execute` pin/fence integration test (kills 4 high direct + ~21 medium). Execution-authority + declared-confinement + TOCTOU provenance — the highest-value single test.
2. **P2** — tripwire serve-surface fixtures (kills 6 high). Prioritize the `_fragments` frozen-tuple case (production-silent).
3. **P3** — `register_runtime` fail-closed test (kills 1 high indirect).

**Scope guard (owner #3):** all three are **new tests only**. No change to `aisef2/invariants/registry.py` registrations, no new invariant, no change to `validation/.../release_qualify.py` or any acceptance gate. These tests would run in the existing `unit` CI leg. This is a hardening *plan*; applying it is a separate owner go (it adds tests, touches no product code, so it does not require the frozen-kernel approval that FINDING-WIN-OSKILL-001 does).
