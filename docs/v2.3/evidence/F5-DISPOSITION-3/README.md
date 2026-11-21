# F5 disposition 3: the integrated W1 head (supersedes disposition 2)

Produced by `validation/v23/impact.py --classify --base da3ea33f3b695aaca73e87a704145a0193aced23 --head
acece68b863f520a3d7896b7cbf10295ff5146e6 --json`. The head is the W1 integration commit, with tracks A and D and lanes
L1-BUILD/F2/TESTENV/CIGOV/QUAL merged. The engine is the one after recorder reviews 1–2 (`impact.py` sha256
`79609ac7…`). It ran in a clean detached worktree of that commit; the main checkout carries ignored `.DS_Store` files
under COPY roots, which the engine correctly refuses as `dirty`. It took 982 s on darwin arm64 with CPython 3.14.7. No
observations were passed.

| F5 state · component | Targets | Mutants |
|---|--:|--:|
| VERIFIED_REUSE | **0** | 0 |
| INVALIDATED · R2 (static R2S) | **667** | **17,322** |
| UNRESOLVED · I6 | **327** | **10,078** |

* **Why R2 (R2S) now.** Under the COPY roots, Δ since v2.2.0 is exactly the 9 files added under `closure-evidence/v2`
  after the tag. 15 files of every S(F) name that directory by a literal path (e.g. `tests/v2/test_p9_reproduction.py`).
  R2S therefore invalidates every target that passes I6, before any observation is read.
* **Observations do not change it.** The bounded strace observation of the 97 posix/linux kill files
  ([`../f5-observe/BOUNDED-OBSERVATION-2026-11-22.json`](../f5-observe/BOUNDED-OBSERVATION-2026-11-22.json)) gave the same
  table. A complete observation of all 262 kill files would also give it, because R2S and I6 fire first.
* **Platform (I6):** 461 posix/darwin, 63 posix/linux, 140 posix/unproven, 3 windows/unproven, 327 unknown.
* **Labels.** `run` is `v2.2.0-accepted` because the basis is the pinned tag. No non-reuse row carries an acceptance basis.
* **Authority.** The recorder is approved for development only. Nothing here is a VERIFIED_REUSE authority, and nothing
  is wired into `validation/v2/mutation.py check()` or any release gate.
* **Eligible for VERIFIED_REUSE today: 0.** The minimal defensible MUST_REMEASURE set and its cost are in
  [`../QUALIFICATION-SCOPE-MANIFEST/`](../QUALIFICATION-SCOPE-MANIFEST/README.md).
