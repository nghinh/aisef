# Wave-2 mutation hardening — implementation + KILLED evidence (owner #1 GO)

Owner #1 (2026-11-06): *Approve P1, P2, P3 in priority order, registry + acceptance criteria unchanged. Re-measure the 11 high gaps with KILLED evidence or grounded re-classification. Verify the frozen-tuple "broken in production" claim — if a product defect, STOP at the kernel. Reconcile 236 vs 238.*

## 1. The three hardening items — implemented (test-only, no product/registry/criteria change)

| item | new test file | kills |
|---|---|---|
| P1 | [tests/v2/test_v22_hardening_p1_run_pin_fence.py](../../../tests/v2/test_v22_hardening_p1_run_pin_fence.py) | 4 high (run.execute pin/fence/kw) |
| P2 | [tests/v2/test_v22_hardening_p2_tripwire.py](../../../tests/v2/test_v22_hardening_p2_tripwire.py) | 6 high (tripwire serve-surface) |
| P3 | [tests/v2/test_v22_hardening_p3_register_runtime.py](../../../tests/v2/test_v22_hardening_p3_register_runtime.py) | 1 high (register_runtime CODE resolution) |

P1 drives the real `run.execute()` end to end, offline, by reusing the `aisef2.app.demo` harness (fake developer + loopback provider — no network, no credentials, no real `opencode`). All three are green on clean HEAD (`2047205a`): P2+P3 7 tests/0.003s, P1 2 tests/4.6s. No change to `aisef2/`, to the mutation registry, or to any acceptance gate.

## 2. KILLED evidence — 11/11 (deterministic)

Method ([MUTATION-WAVE2-KILL-MATRIX.json](./MUTATION-WAVE2-KILL-MATRIX.json)): establish the green baseline, then for each high mutant apply the exact edit to HEAD, run only its mapped hardening test, require it to **FAIL** (= KILLED), and `git checkout` to revert. Bytecode caching disabled (`PYTHONDONTWRITEBYTECODE=1`) after a `.pyc`-staleness race produced one false SURVIVED on the first pass — with it off, the result is stable.

| # | mutant (as classified) | test | result |
|---|---|---|---|
| 1 | run.execute `'client_pin'` emptied | P1 mismatched-pin → `RunRefused` | KILLED |
| 2 | run.execute `'client_fence'` emptied | P1 fence xdg dirs built | KILLED |
| 3 | run.execute `pin_sha256` kw entry dropped | P1 session carries `pinned_sha256` | KILLED |
| 4 | run.execute `fence` kw entry dropped | P1 session carries declared fence | KILLED |
| 5 | `_bundle_hit` except arm → `None` | P2 marker+invalid-JSON → True | KILLED |
| 6 | `_bundle_hit` except arm `True`→`False` | P2 marker+invalid-JSON → True | KILLED |
| 7 | `_canonical` `,` emptied | P2 `_canonical([1,2,3])=='[1,2,3]'` | KILLED |
| 8 | `_canonical` `:` emptied | P2 `_canonical({"a":1})=='{"a":1}'` | KILLED |
| 9 | `scan_text` `ensure_ascii` False→True | P2 non-ASCII escaped-spelling hit | KILLED |
| 10 | `_fragments` drop `tuple` | P2 frozen-tuple recursion reaches leaf | KILLED |
| 11 | `register_runtime` CODE→STATIC_RULE | P3 missing-CODE-attr fail-closed + static not resolved | KILLED |

Source tree verified clean after the matrix (no residual mutation). The 11 high gaps are now covered by regression guards. (Line-number labels are from the frozen clone `89de4685`; the KILL matrix locates each by operation on current HEAD and records the exact old→new edit.)

## 3. Frozen-tuple "broken in production" — verified: NO product defect

The owner's special condition. Measured empirically on the **real production data shape** (a spec's `probe_input` after `freeze()`): `stimulus` is a `mappingproxy`, its nested array is a `tuple`.

- **Shipped `_fragments`** produces the nested-tuple leaf as a needle: **True** → production is correct.
- The **mutant** (drop `tuple`) drops it: leaf absent → the kill test distinguishes.
- **Shipped `_fragments`** recurses `MappingProxyType`: **True**.

**Verdict: the shipped code has no product defect.** `_fragments` uses `isinstance(value, Mapping)` and `isinstance(value, (list, tuple))`, both of which match the frozen shapes `freeze()` produces (`MappingProxyType`, `tuple`). The P2 `_fragments` item is a **regression-test gap**, not a kernel defect — so no STOP at the kernel boundary for it. **Correction to the earlier report's wording:** "silently broken in production" described the *mutant's* invisibility to the old suite (its fixtures use unfrozen lists), not the shipped code; shipped code handles frozen specs correctly.

## 4. Reconciliation — 236 real gaps vs 238 classified

- The frozen campaign: 247 distinct survivors − 11 EQUIVALENT = **236 real-gap entries**.
- Split into 26 risk-units, those 236 entries hold **228 distinct `(target, mutant)` pairs**; 8 are duplicate placements across the split functions (`run.execute` ×5 units, `registry_digest` ×2).
- The classifier returned **238 entries = 229 distinct + 9 duplicate placements**, with **0 source mutants missing** (every fed gap classified), **1 adjacent extra** picked up (`run.execute L646 True->False [exist_ok]`), and **0 severity disagreements** among the duplicates (dedup is safe).
- Net: **0 critical** under every count; the 11 high are fully enumerated and now killed. The 238/236/229/228 differences are duplicate placements + one adjacent mutant, none of which changes the risk picture.

## 5. Scope guard (owner #1)

New tests only. No `aisef2/invariants/registry.py` registration change, no new invariant, no change to `release_qualify.py` or any acceptance gate. Applying these tests is what owner #1 approved; they run in the existing `unit` CI leg.
