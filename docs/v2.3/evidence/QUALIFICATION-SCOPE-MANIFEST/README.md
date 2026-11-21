# v2.3 qualification-scope manifest (frozen by digest)

Owner direction 2026-11-21 ("W1 integration and evidence integrity", item 3): freeze an explicit v2.3
qualification-scope manifest. It must reconcile the 994 registry targets, the 667 active historical targets, the 327
legacy targets, the 891 proposed scope targets, and the changed and new code, and it must return the minimal defensible
MUST_REMEASURE set and its cost. It authorizes no measurement: no 667-, 891- or 994-target campaign may start without a
separate owner authorization.

* [`QUALIFICATION-SCOPE-MANIFEST.md`](QUALIFICATION-SCOPE-MANIFEST.md) holds the frozen rules, the reconciliation, the
  cross-tab, the minimal set, cost and levers, the owner decisions with their trust-keeping defaults, and the checker
  dispositions.
* [`SCOPE-MANIFEST.json`](SCOPE-MANIFEST.json) holds one row per registry entry (994), the MEASURE_NEW and
  EDITED_NO_V220_TARGET rows, and an inventory-only section that promotes nothing.
* **Manifest digest:** `632c3ac459746db89cf0fd000a309b0c8cb26287acf231a4ac1aca0c5eccac61`. The one-line verifier is in
  the `.md`. It was recomputed independently at integration and matched.
* Pin: `release/v2.3-big` @ `1e25ef84`, basis v2.2.0 = `da3ea33f`. Every input is a git object.
* **Review history.** The analysis was checked adversarially through two lenses, reconciliation/non-promotion and
  cost/minimality. All 12 findings were accepted in one bounded correction pass (§10). No row left the default set; one
  was added.
* **Generator scripts** are not committed, because they are analysis tooling and not product. They are kept by sha256:

  | script | sha256 |
  |---|---|
  | `manifest.py` | `03595bb702f5c40bd220e029dbe74e584abdeb87a2a5a1e6c6f549a70ccc8c8a` |
  | `render_md.py` | `3b939aba06cb5ff06c4900169f9b1d4762bad590a015f0e5098b4eee5a49af67` |
  | `t0_legacy.py` | `e6430db810f704898f00def26f3be3e3f7c06ebdf9eb38ec3d8c74e1cbce3676` |
  | `verify_counts.py` | `7d8fede861a1b44f9cb3ad35a383eb51bfbb9f97b4a509329adf5c11ae612abd` |
  | `verify_counts_edited.py` | `58d744d1421e35de7823e074edb88a4a4e0b7cd32cef77909088c5b8c1dffbdd` |

## Headline (from the manifest)

| | targets | mutants | serial worker-hours (point, band) |
|---|--:|--:|---|
| Registry (v2.2.0-enforced, all 994) | 994 | 27,400 | — |
| = ACTIVE_HISTORICAL + LEGACY_UNPROVEN | 667 + 327 | 17,322 + 10,078 | 291.7 + 17.1 |
| = CHANGED_TRUST_CRITICAL + REUSE_CANDIDATE | 891 + 103 | 24,236 + 3,164 | 299.0 + 9.8 |
| **Minimal defensible MUST_REMEASURE at the final RC** | **1,011** | **28,292** | **322.2 (159.5–500.1)** |

* Wall time at the point estimate is 80.6 h with 4 workers and 40.3 h with 8.
  * Each worker needs 3.1 GiB steady and 4.6 GiB at peak, so 8 workers need about 57 GiB free. That is a SCALE-1 host,
    not this one.
* The F5 engine proves VERIFIED_REUSE for none of the entries today; see
  [`../f5-observe/BOUNDED-OBSERVATION-2026-11-22.json`](../f5-observe/BOUNDED-OBSERVATION-2026-11-22.json).
* The 322 h figure holds only if the owner decides OD-WAVE (measure each target once, at the final RC).
  * Under the DAG §6 default, every changed target is also measured at every wave exit. The programme then costs
    1,363–3,154 h.
