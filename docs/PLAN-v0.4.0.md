# Plan — AISEF v0.4.0

Successor to v0.3.1 (security + packaging hardening).

## Theme

**Observability & conformance depth** — the harness captures events and gates
decisions, but the user has limited visibility into *what* the harness saw and
*why* a gate passed or blocked. v0.4.0 closes that gap.

## Candidates

Drawn from `docs/DANH-GIA-360-VA-LO-TRINH.md`, `docs/STATUS-2026-09-05.md`,
and e9 field data.

### P0 — ship-or-block

1. **Conformance dashboard** (`aisef dashboard`): one-page HTML report of
   guard hit/pass rates, gate verdicts, evidence chain integrity — generated
   from the evidence store, viewable offline.
2. **Guard telemetry**: each guard writes a structured event to the evidence
   JSONL (kind, tool, verdict, latency) so dashboard and post-hoc analysis
   have data.

### P1 — strongly desired

3. **`aisef replay <story>`**: re-run a completed story's evidence through
   current guards and report regressions — catches guard drift without a live
   agent run.
4. **Structured error on guard failure**: today a blocked tool surfaces as a
   generic agent error; emit a machine-readable payload the client can render
   as an actionable message.

### P2 — nice to have

5. **OpenCode parity**: close remaining degradations (turn limit, tool
   allowlist) if OpenCode upstream ships the hooks.
6. **Multi-epic state**: `state.json` currently assumes one epic; support
   concurrent epics in the same project.

## Non-goals for v0.4.0

- PyPI org account (owner action, not code).
- New guard types (guards stabilise in v0.3.x first).
- Plugin / extension API (premature — internal surface still moving).

## Success criteria

- `aisef dashboard` produces a valid HTML file from any e9-format evidence
  store.
- Guard telemetry events present for ≥ 95 % of guard invocations in a fresh
  e9 run.
- `aisef replay` exits 0 on a clean story, exits 1 on a tampered one.
- All existing 1752+ tests still pass; new features carry their own tests.
