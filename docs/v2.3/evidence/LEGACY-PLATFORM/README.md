# Legacy platform provenance: 327 runner-1 entries (read-only reconstruction)

Owner ruling 2026-11-21, item 4: "For the 327 legacy targets with missing platform provenance, attempt a read-only
positive reconstruction from original worker histories. Do not infer platform from absence of Windows markers. Where
provenance remains unproven, preserve UNRESOLVED and remeasure when required."

* [`LEGACY-PLATFORM.md`](LEGACY-PLATFORM.md) gives the method, the per-record searches and the result.
* [`legacy-platform.json`](legacy-platform.json) has one row per entry, with what was searched and every pointer found.
* [`CHECK.md`](CHECK.md) is the adversarial check, and the `.md` records its dispositions.

**Result: 0 PROVEN, 327 UNPROVEN.**

* 49 rows (1,806 mutants) can be tied to their run and a darwin host only by evidence that was never committed to the
  repository. Using that evidence would take an owner ruling plus digest pinning.
* The ceiling if the engine admitted the in-tree evidence is 6 rows / 138 mutants (darwin).
* Every one of the 327 stays UNRESOLVED (I6).
* In the frozen scope manifest, 235 of the 327 are CHANGED_TRUST_CRITICAL and 92 are REUSE_CANDIDATE. Either way they
  are measured at the final RC on a recorded platform. No platform is inferred from the absence of a marker.

The analysis scripts are not committed: they embed local search patterns. Their sha256:

| script | sha256 |
|---|---|
| `build.py` | `ddd637f3487a80632f82008baaa5a8692b6082f9672e113d0ecccfca13c0dae6` |
| `check_consistency.py` | `26c7e176520d27a5c648306542ccaab753effee3e2024bda04eb8dd58bba5ac9` |
| `scan.py` | `f71d8c283edfb917a925c3d2cbffce3ef6b691fddb97240f200585d98f488dd4` |
| `scan_cooccur.py` | `1eb198e79c62eda4cb34fcd2abdd3ec6bd75dee338fe99e0c848295e64dc992a` |
| `scan_records_history.py` | `e18b5112080d3d0129bccda1698dc5f79bd5e029d79a70ae198285a5bb1f2714` |
| `trace_intro.py` | `51d8e6c8f9fb3a9278643add873f538b3d411bda5cb42a5a9fabeeb5b1f7f879` |
| `verify_ootree.py` | `302b430ac794fc550780dff898f9dc5ca603928e5bfa24a43a56cb72787bb030` |
| `verify_search_counts.py` | `35404cea34733cd05ac8b8076d423b1854a4cd4340ae60ef8f476ccd0f8ee436` |
| `worker_overlap.py` | `e3baf2959fe8e616e2f2f9a39b66769616a5f5d02067f37b8c06916bd1dfbd31` |
