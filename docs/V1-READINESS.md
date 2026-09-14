# v1.0.0 Readiness Checklist

> **COMPLETED.** v1.0.0 released 2026-09-08, published to PyPI.
> See CHANGELOG.md and ADR-006 for the final reconciliation.
> This document is retained as historical record of the pre-release checklist.

Status as of 2026-09-08. Each item is either automated (readable by command)
or requires a manual step with real agent runs.

**v0.8.0**: Brownfield support — `aisef baseline`, CodebaseGraphProvider
(Graphify + Basic), delta planning, `blast_radius` slot, `context.graph_provider`
config key. 26 new tests in `test_brownfield.py`.

**CI fix (0.7.0.dev0)**: worktree race condition fixed — `git worktree add`
serialized with threading lock. v0.5.1 and v0.6.0 releases failed in CI
due to this bug (probabilistic).

## Automated — DONE

| # | Condition | Evidence |
|---|---|---|
| A1 | 100% unit tests green | 1930/1930, `python3 -m unittest discover -s tests` |
| A2 | API stability contract | `docs/STABILITY.md` — frozen surface documented |
| A3 | PyPI publish works | Trusted Publisher: v0.4.1, v0.5.0, v0.5.1, v0.6.0, v0.7.0 all published |
| A4 | Clean install verification | `pip install aisef` → `aisef doctor` runs |
| A5 | English usage guide | `docs/USAGE-GUIDE.md` (927 lines) |
| A6 | Documentation accuracy | SOLUTION.md §2.2, §11, §13 match code; README guard count |
| A7 | Config key freeze | 58 keys, all documented in STABILITY.md |
| A8 | Guard count matches | 9 guards, all in STABILITY.md table |
| A9 | Meta tests | `test_meta.py` — every evidence kind has a producer, every EMULATED capability names its mechanism |
| A10 | Test coverage for all public modules | test_skills, test_client_base, test_client_adapters, test_browser, test_parser, test_doctor, test_design_contract |

## Requires real agent runs — BLOCKED

> **Superseded as a gate, 2026-09-14.** B1–B4 below are retained as a dated
> record and are no longer closure conditions. The closure gate is
> [`PROJECT-CLOSURE-GATE.md`](PROJECT-CLOSURE-GATE.md), approved by the owner on
> 2026-09-14, and §7 of that document re-classifies each of these four
> explicitly: **B2** (`par` baseline) and **B3** (`e9` EPIC-01) are
> OBSOLETE — both corpora are absent from this machine — with the property they
> tested now measured by **G4** on a living corpus; **B4** is superseded by
> G4.6/G4.7; **B1** (conformance freshness) survives as **G3**, which reads the
> framework's own `MAX_AGE_DAYS` rather than a date copied into prose.
>
> Nothing below is edited. The `**COMPLETED.**` banner at the top of this file
> refers to the v1.0.0 release, which did happen; this section's four items were
> never satisfied, and that contradiction is why a successor gate was needed.

These need API keys and real project runs. Owner action required.

| # | Condition | What to do |
|---|---|---|
| B1 | CONFORMANCE.md ≤ 14 days | `AISEF_CONFORMANCE=1 python3 -m unittest tests.conformance` — last run 2026-09-06, expires 2026-09-20. *Correct when written and left as written: the table was refreshed to 2026-09-08 four hours later the same day (`af827f4`, 12:21; this row was authored in `8095d9a`, 08:37), which moves the real expiry to **2026-09-22**. Same reason A7/A8 were left alone — this is a completed checklist, and the live expiry lives in [CONFORMANCE.md](CONFORMANCE.md) plus `aisef/control/conformance.py` `MAX_AGE_DAYS`, not here. Verified 2026-09-14.* |
| B2 | `par` dogfood baseline | Run `par` (3 stories) on both clients, record cost/turns baseline in `tests/dogfood/` |
| B3 | `e9` EPIC-01 complete | 4 remaining stories — **STORY-01-04, 01-05, 01-06, 01-07** — need real agent runs (~$40-60). *List added 2026-09-14 under the ADR-009 rule ("a statement of the form 'N items remain' must carry the list, in the same document"); the names come from [EXECUTION-PLAN R2](EXECUTION-PLAN.md), which already carried them.* |
| B4 | Acceptance report | `aisef pre-deploy` after B3 completes |

## Decision: what to release

Options:
1. **v1.0.0-rc1** — tag current code, document B1-B4 as pre-GA requirements
2. **v1.0.0** — wait for B1-B4 (needs owner to run agents)

v0.8.0 released 2026-09-08 with brownfield support and all automated conditions met.

The action plan's release conditions (R1-R5) require B1-B4. The framework
code is feature-complete and well-tested for v1.0 scope; only the
end-to-end validation on real projects remains.
