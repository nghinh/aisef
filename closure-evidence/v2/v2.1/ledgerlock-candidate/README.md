# LedgerLock 2.1 candidate bundle (migrated, not signed)

`aisef bundle migrate` re-binds the sealed 2.0.0 LedgerLock project bundle
(`closure-evidence/v2/release/LEDGERLOCK-PROJECT.json`) to this release's spec ids. The approvals of every contract a
**declared capability change** evaluates differently are withheld (owner decision 2026-10-15, item 1), so the candidate
does **not** load until the owner approves them again. Nothing here is signed or sealed — it is a candidate for review.

## Migration result (from the sealed 2.0.0 bundle, deterministic)

| | count |
|---|---:|
| approvals kept | 53 |
| approvals withheld (need owner re-approval) | 6 |

The 6 withheld contracts, all driven by the same semantic change — `probe.file_artifact` class `grep_count`, whose
2.1 capability (PM-9 absence-is-decidable, PM-11 BOM dropped before read, PM-13 grep_count runs under
`timeouts_s.probe`) evaluates these contracts differently from 2.0.0:

| contract | requirement |
|---|---|
| BC-V22-S-10-a / -b / -c | R-10 |
| BC-V22-S-12-a / -b / -c | R-12 |

A fresh migrate refuses to load the candidate with, e.g., `contract BC-V22-S-10-a is not approved: R-10: no approval
binds requirement_hash and contract_hash` — the withholding working as intended.

## Files

- `APPROVE.sh` — the owner's re-approval. It re-migrates from the **sealed** 2.0.0 bundle (so no loose candidate is
  trusted), approves the 6 contracts as the named human (chained, each `aisef bundle approve` reads the one before),
  and lints the result.

  ```sh
  zsh closure-evidence/v2/v2.1/ledgerlock-candidate/APPROVE.sh human:<your-name> [OUT_DIR]
  ```

  Verified here with a stand-in approver: lint `verdict: READY`, `to_approve: []`, and the approved bundle loads.
  Swap in the owner's own `human:<name>`; the stand-in approval is not the owner's and is kept by nothing.
- `LEDGERLOCK-CANDIDATE-BUNDLE.tar.gz` — for inspection: the migrated candidate (`LEDGERLOCK-CANDIDATE.json`, with the 6
  withheld) and the full migration report (`MIGRATE-REPORT.json`). A `.tar.gz` so no record generator's tree scan reads
  a loose candidate bundle as evidence.

Built at commit `f666bdfb` (aisef 2.1 probe-window). Not a release; no PyPI, no tag, no signature.

Written 2026-10-20.
