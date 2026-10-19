# E2 — the real controlled campaign (mycombo on 9router), 18 runs

Owner approval 2026-10-18 (`round-5/OWNER-DECISION-2026-10-18-E2.md`): run the controlled experiment directly with the
real model `mycombo` on 9router, cost not a concern. Launched 2026-10-20 from aisef `f666bdfb` with the operator's key
in the environment (never printed, never an argument); provisional approver `human:orchestrator-provisional` (the owner
adopts their own approvals with `e2/w1-a/APPROVE.sh` + `e2/w2/APPROVE.sh` and `e2_setup.py --adopt-owner`, then replay).

- Real client: `/Users/nghinh/.opencode/bin/opencode` v1.18.31. Real provider: `https://9router.vnteki.com/v1`, route
  `9router/mycombo`, served `MiniMax-M3`; no price table, so every `cost` is `null` (never 0).
- Design: {w1-a, w2} × {direct, aisef, aisef+} × 3 reps = 18 runs, rep-major.
- Driver exit 0 (wall ~7023 s for reps 2–3; ~2 h total). **replay exit 0** (the sealed manifests reproduce).
- **Isolation/safety: secret scan — 0 of 277 recorded files hold the key's value; `store_stat $HOME before == after: True`
  (the operator's own OpenCode store untouched); `refused_identity 0` on every arm (the preflight identity attestation
  held — the provider served what the settings declared).**

## Result (summary.txt), per arm × workload, n = 3

| workload | arm | delivered 12/12 | failed (rolled back) | escaped_defects | false_rollbacks | satisfied_mean | tokens in | requests |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| w1-a | direct | 1 | 0 | **2** | 0 | 0.944 | 2.24 M | 15 |
| w1-a | aisef  | 1 | 2 | 0 | 1 | 1.000 | 9.09 M | 38 |
| w1-a | aisef+ | 1 | 2 | 0 | 1 | 1.000 | 7.76 M | 39 |
| w2   | direct | 3 | 0 | 0 | 0 | 1.000 | 2.41 M | 15 |
| w2   | aisef  | 1 | 2 | 0 | 1 | 1.000 | 16.85 M | 36 |
| w2   | aisef+ | 3 | 0 | 0 | 0 | 1.000 | 15.50 M | 35 |

**valid = true on all 18 runs** — the kernel's handling was correct in every one. Totals: 53.8 M input / 642 K output
tokens, 178 requests, 6 delivery-FAIL (all the kernel rolling back a plan whose developer left a story uncommitted —
fail-closed, not a kernel defect), 2 escaped defects (direct, w1-a).

## Reading (honest, n = 3)

- **The kernel never shipped a defect**: aisef and aisef+ had 0 escaped defects across all runs; when the developer's
  work was incomplete they rolled back (delivery FAIL), rather than deliver. The **direct** arm shipped **2 escaped
  defects** on the hard workload w1-a (delivered 11/12, the evaluator finding a criterion unmet).
- **At a cost**: the kernel arms used ~4–7× the tokens (verification + multi-round orchestration) and had **false
  rollbacks** (1 per failing cell) — rolling back runs a lenient evaluator might have accepted. Fail-closed strictness
  trades those against the escaped defects it prevents.
- **w1-a is hard for the model**: every arm struggled there (direct 1/3 clean, kernel arms 1/3 delivered), so at n = 3
  the model's non-determinism dominates any clean arm effect; this is a signal to run more reps, not a verdict.

Evidence: `e2-records.tar.gz` (the driver's 277-file record copy: SETUP, APPROVALS, CAMPAIGN, per-run MANIFEST/RESULT/
journals, launch records with store-before/after, INDEX) and `summary.txt` (the aggregate above). Not a release.

Written 2026-10-20.
