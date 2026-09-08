# API Stability — AISEF v0.5.0 → v1.0.0

This document defines what is frozen (changing it is a breaking change that
bumps the major version) and what remains internal (may change in any release).

## Frozen from v0.5.0

### CLI commands

```
aisef doctor | setup | init | compile | run | status | dashboard | guard |
       gate | replay | skill | doc | change
```

New subcommands may be added; existing ones keep their flags and exit codes.

### Config keys (57 keys)

Every key in `aisef.config.DEFAULTS` is part of the public contract. Keys may
be **added** but never removed or renamed. Type and default may not change
without a migration in `Config.load()` that preserves old `.ai/config.json`
files.

Groups: `app.*`, `clients.*`, `context.*`, `cost.*`, `coverage.*`,
`improve.*`, `review.*`, `route.*`, `run.*`, `sandbox.*`, `security.*`,
`skills.*`, `story.*`, `tools.*`, `verify.*`.

### Guards (9 guards)

| Guard | Hook | Tool matcher |
|---|---|---|
| `completion` | `Stop` | — |
| `destructive` | `PreToolUse` | `Bash` |
| `diff-scope` | `PostToolUse` | `Write\|Edit\|NotebookEdit\|Bash` |
| `egress` | `PreToolUse` | `WebFetch\|Bash` |
| `git-stage` | `PreToolUse` | `Bash` |
| `injection` | `PreToolUse` | `Write\|Edit` |
| `process-ref` | `PreToolUse` | `Write\|Edit` |
| `secret` | `PreToolUse` | `Write\|Edit` |
| `write-scope` | `PreToolUse` | `Write\|Edit\|NotebookEdit` |

New guards may be added. Existing guards keep their name, hook type, and
tool matcher.

### Gate lifecycle

```
prd → architecture → ux-spec → epics → stories → mockups → readiness → pre-deploy
```

Plus the non-linear `improve` gate for epic improvement loops. New gates may
be added at the end; existing gates keep their position and evaluation rules.

### Story gate checks

The `evaluate()` function in `control/gate.py` checks:

1. **Evidence matches candidate** — evidence must belong to the SHA being evaluated
2. **Guard presence** — at least one guard evaluation recorded
3. **Tests green** — last test run on the candidate passed
4. **Flaky tests excluded** — detected via `--repeat`
5. **Review ran** — independent reviewer session recorded
6. **Review blocking items** — no unresolved blocking feedback
7. **Security review** — independent security session recorded
8. **Write scope** — changes within declared scope only
9. **Coverage** — meets `coverage.min` threshold
10. **Preservation** — verified behaviors of other stories not regressed

### Evidence format

JSONL files in `_bmad-output/evidence/{story_id}.jsonl`. Event kinds:
`agent_run`, `tool_run`, `guard_check`, `guard_block`, `guard_seen`,
`file_change`, `note`, `behavior`, `mockup_map`.

### State file

`sprint-status.json` format: `stories` dict (keyed by story ID), each with
`id`, `epic_id`, `status`, `attempts`, `wave`, `worktree`, `evidence`,
`cost_usd`, `duration_ms`, `blocked_reason`, `claimed_by`, `updated_at`.

Status enum: `pending`, `running`, `verifying`, `verified`, `done`,
`blocked`, `failed`.

### Exit codes

- `0` — success / guard allows
- `2` — guard blocks / gate fails / not ready

## Not frozen (internal)

- Prompt templates (`aisef/harness/prompts/`)
- Skill catalog and router internals
- Client adapter internals (`aisef/clients/`)
- Dashboard HTML layout
- Evidence store internal methods
- Test infrastructure
