# v1.0.0 Readiness Checklist

Status as of 2026-09-08. Each item is either automated (readable by command)
or requires a manual step with real agent runs.

**CI fix (0.7.0.dev0)**: worktree race condition fixed — `git worktree add`
serialized with threading lock. v0.5.1 and v0.6.0 releases failed in CI
due to this bug (probabilistic).

## Automated — DONE

| # | Condition | Evidence |
|---|---|---|
| A1 | 100% unit tests green | 1904/1904, `python3 -m unittest discover -s tests` |
| A2 | API stability contract | `docs/STABILITY.md` — frozen surface documented |
| A3 | PyPI publish works | Trusted Publisher: v0.4.1, v0.5.0, v0.5.1, v0.6.0 all published |
| A4 | Clean install verification | `pip install aisef` → `aisef doctor` runs |
| A5 | English usage guide | `docs/USAGE-GUIDE.md` (927 lines) |
| A6 | Documentation accuracy | SOLUTION.md §2.2, §11, §13 match code; README guard count |
| A7 | Config key freeze | 57 keys, all documented in STABILITY.md |
| A8 | Guard count matches | 9 guards, all in STABILITY.md table |
| A9 | Meta tests | `test_meta.py` — every evidence kind has a producer, every EMULATED capability names its mechanism |
| A10 | Test coverage for all public modules | test_skills, test_client_base, test_client_adapters, test_browser, test_parser, test_doctor, test_design_contract |

## Requires real agent runs — BLOCKED

These need API keys and real project runs. Owner action required.

| # | Condition | What to do |
|---|---|---|
| B1 | CONFORMANCE.md ≤ 14 days | `AISEF_CONFORMANCE=1 python3 -m unittest tests.conformance` — last run 2026-09-06, expires 2026-09-20 |
| B2 | `par` dogfood baseline | Run `par` (3 stories) on both clients, record cost/turns baseline in `tests/dogfood/` |
| B3 | `e9` EPIC-01 complete | 4 remaining stories need real agent runs (~$40-60) |
| B4 | Acceptance report | `aisef pre-deploy` after B3 completes |

## Decision: what to release

Options:
1. **v1.0.0-rc1** — tag current code, document B1-B4 as pre-GA requirements
2. **v1.0.0** — wait for B1-B4 (needs owner to run agents)

v0.6.0 released 2026-09-08 with all automated conditions met.

The action plan's release conditions (R1-R5) require B1-B4. The framework
code is feature-complete and well-tested for v1.0 scope; only the
end-to-end validation on real projects remains.
