# Documentation map

AISEF 2.1 ships two surfaces: the V2 runtime (`aisef run`) and the 1.x framework, whose planning pipeline and tools
are unchanged and whose execution runs behind `aisef legacy run` / `aisef legacy improve`. Pages describe the
version they were written for; a dated record is never rewritten to match a later release.

## AISEF 2.1 — current

| page | what it is |
|---|---|
| [v2/USAGE.md](v2/USAGE.md) · [v2/USAGE.vi.md](v2/USAGE.vi.md) | using `aisef run`: the project bundle, run settings, the run directory, exit codes, known limitations |
| [architecture/AISEF-V2-ARCHITECTURE-RFC.md](architecture/AISEF-V2-ARCHITECTURE-RFC.md) | the four planes, the nine invariants, the kernel's types and why they are shaped this way |
| [v2.1/REPORT.md](v2.1/REPORT.md) · [v2.1/TRACEABILITY.md](v2.1/TRACEABILITY.md) · [v2.1/USAGE-2.1.md](v2.1/USAGE-2.1.md) | what changed in 2.1 and why, each behaviour traced to its evidence, and the 2.1 usage/migration deltas |
| [../closure-evidence/v2/v2.1/V2.1-EXECUTIVE-HANDOVER.md](../closure-evidence/v2/v2.1/V2.1-EXECUTIVE-HANDOVER.md) · [../closure-evidence/v2/v2.1/GO-NO-GO.md](../closure-evidence/v2/v2.1/GO-NO-GO.md) | the 2.1 qualification and release evidence |
| [v2/V2.1-BACKLOG.md](v2/V2.1-BACKLOG.md) | what the V2 runtime does not do yet, each item with a reproducer |
| [v2/V2-STABLE-RELEASE-CHARTER.md](v2/V2-STABLE-RELEASE-CHARTER.md) · [v2/RELEASE-PROCESS.md](v2/RELEASE-PROCESS.md) | how the V2 runtime is qualified and released |
| [../closure-evidence/v2/release/V2.0-FINAL-RELEASE-REPORT.md](../closure-evidence/v2/release/V2.0-FINAL-RELEASE-REPORT.md) | the 2.0 release evidence (same kernel 2.1 ships) |
| [SALEKIT.html](SALEKIT.html) | one-page overview for evaluators |
| [DANH-GIA-360-V2.0-2026-10-06.md](DANH-GIA-360-V2.0-2026-10-06.md) | independent 360° assessment of 2.0 (Vietnamese): eleven dimensions, findings, 2.0.1/2.1 plan |

## The 1.x framework — still shipped

| page | what it is |
|---|---|
| [USAGE-GUIDE.md](USAGE-GUIDE.md) · [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md) | step-by-step guide: requirements, gates, `aisef legacy run`, troubleshooting, command and config tables |
| [SOLUTION.md](SOLUTION.md) | the 1.x design and why it is shaped this way (Vietnamese) |
| [FAILURE-TAXONOMY.md](FAILURE-TAXONOMY.md) · [DEFECT-REGISTER.json](DEFECT-REGISTER.json) | every defect found by running, with its regression check |
| [CONFORMANCE.md](CONFORMANCE.md) · [SANDBOX-CONFORMANCE.md](SANDBOX-CONFORMANCE.md) · [TOOL-CAPABILITIES.md](TOOL-CAPABILITIES.md) | client and sandbox conformance, tool defaults |
| [PROJECT-CLOSURE-GATE.md](PROJECT-CLOSURE-GATE.md) · [closure-gate.json](closure-gate.json) | the 1.x project-closure contract scored by `aisef closure` |
| [MEMORY.md](MEMORY.md) | scoped long-term memory: off by default, frozen since 2026-09-12 |
| [INVARIANTS.md](INVARIANTS.md) · [ASSURANCE-KERNEL.md](ASSURANCE-KERNEL.md) · [DEFECT-FAMILY-MAP.md](DEFECT-FAMILY-MAP.md) · [FAULT-MATRIX.md](FAULT-MATRIX.md) · [SCALE-QUALIFICATION.md](SCALE-QUALIFICATION.md) | systematic hardening of the 1.x execution path, the groundwork for 2.0 |
| [requirements-template.md](requirements-template.md) | the template for a 1.x project's one input file |

## Dated records — describe their own date and version

- Decisions: `ADR-002` … `ADR-011`.
- Benchmarks: `BENCH-*` (v0.3.0, v1.3, C-1, C-1b, C-2), `E4-COST-DECOMPOSITION.md`, `O1-RECOMPUTE-AFTER-158.md`, `MEMORY-BENCH.md`, `MEMORY-VALIDATION.md`, `MEMORY-RESEARCH-PLAN.md`.
- Releases and plans: `RELEASE-*`, `PLAN-v0.4.0.md`, `ROADMAP-POST-1.0.md`, `V1-READINESS.md`, `STABILITY.md`, `EXECUTION-PLAN.md`, `ACTION-PLAN-2026-09-05.md`, `SPIKE-REPORT.md`, `REQUIREMENTS-EVIDENCE.md`.
- Reviews and status: `DEEP-REVIEW-2026-09-05.md`, `DANH-GIA-360-2026-09-12.md`, `DANH-GIA-360-VA-LO-TRINH.md`, `ASSESSMENT-360-v2.html`, `STATUS-2026-09-05.md`, `CLAIM-AUDIT-1.7.2.md`, `DOGFOOD-*.md`, `handoff/`.
- External validation of 1.x (G6): `EXTERNAL-VALIDATION-v1.1.0.md`, `EXTERNAL-VALIDATION-QUICKSTART.md`, `TEMPLATE-EXTERNAL-VALIDATION-REPORT.md`, `G6-RETURN-PLAYBOOK.md`.
- 2.0 / 2.1 working material: `implementation/v2/`, `research/v2/`, `v2.1/`.
