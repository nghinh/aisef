# SUPERSEDED_NOT_QUALIFICATION_EVIDENCE

The first Phase 12 chain (2026-09-16 23:30 → 2026-09-17 06:10) is retained here in full and is NOT qualification
evidence. Owner decision (2026-09-17, "FINALIZE PHASE 12 WITH SINGLE-KERNEL EVIDENCE" §2): the final effective
100 000-trace dataset must all execute against ONE exact `aisef/` product tree with the digest recorded by every
chunk. These chunks ran against up to three kernel states (see `kernel-split-of-the-superseded-chain.json`: chunks
00000/10000 while kernel edits were in progress on disk — not recoverable; 20000–40000 on d956249; 50000 on the
post-SS-64 tree but without a recorded digest; 60000 killed at 06:10 after 2000 of 10 000 traces when the decision
arrived) and none recorded the product-tree, model or comparator digests the final manifest requires.

What they still say, as diagnostic evidence: 59 999 of 60 000 traces matched; the single mismatch (seed 34999,
chunk 30000) is SS-64, resolved in f0cd772 (`../unexplained-34999*.json`); every chunk terminated after exactly
10 000 traces; no invariant violation was reported. The affected-seed analysis for SS-64
(`../affected-seeds-verifier-budget.json`, 4267 seeds) documents the fix's only changed path and remains diagnostic
— it is not a substitute for the full re-run.

The qualification dataset is the second chain: `../../differential-p12-*.json` + `.rows.jsonl.gz`, every chunk
carrying `kernel.aisef_tree` == PHASE12_KERNEL_DIGEST (`../PHASE12-KERNEL-IDENTITY.json`), consolidated by
`validation/p12_integrity.py` into `../PHASE12-DATASET-MANIFEST.json`.
