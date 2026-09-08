# Release Record — v1.0.0

**Released:** 2026-09-08
**Tag:** v1.0.0 (SHA `577fe15`)
**PyPI:** https://pypi.org/project/aisef/1.0.0/
**CI run:** https://github.com/nghinh/aisef/actions/runs/34192397016 (build + publish: success)

## Evidence

| Item | Result |
|------|--------|
| Unit tests | 1913 passed, 18 skipped, 0 errors (Python 3.13) |
| Subtests | 606 passed |
| Conformance (Claude) | 10/10 probes, $1.49 |
| Conformance (OpenCode) | 10/10 probes, $0.00 |
| Conformance report date | 2026-09-08 (within 14-day window) |
| Release gate | PASSED (`AISEF_RELEASE=1`) |
| Twine check | PASSED (sdist + wheel) |
| Clean install | `pip install aisef==1.0.0` in fresh venv — CLI functional |
| Config keys | 58, all with defaults (0 mandatory) |
| Guards | 9 |
| External dependencies | 0 |
| Python requirement | >= 3.11 |

## Dogfood evidence

| Project | Type | Client | Result |
|---------|------|--------|--------|
| par | Node.js, 3 stories | OpenCode | Harness correctly rejected write-scope violations (.serena/ files) |
| calc | Python, 3 stories | — | Infrastructure created, not yet run |
| bench | 15+ bug-fix tasks | Framework | 96 run results from challenge set |

## Deferred to post-1.0 (ADR-006)

1. **External user validation** — requires real adoption; chicken-and-egg with shipping.
2. **Distributed execution** — multi-machine orchestration; single-machine is validated path.
3. **e9 EPIC-01 full run** — external project not on disk; substituted with diverse dogfood + bench.

## Known limitations

- Local sandbox provider does not isolate credentials (use Docker).
- OpenCode + Serena writes `.serena/` outside declared `write_scope`; harness rejects correctly.
- `turn_limit` unsupported for OpenCode.
- Distributed execution not implemented.
- No external user validation yet.

## ADR references

- ADR-006: v1.0.0 exit condition reconciliation
- ADR-005: harness absorption pattern
- ADR-004: evidence-driven epic improvement
- ADR-003: handoff contract and skill graph
- ADR-002: operational knowledge layer
