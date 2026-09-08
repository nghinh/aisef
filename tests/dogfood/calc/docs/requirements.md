# calc — a pure-Python expression evaluator

A small library that evaluates arithmetic expressions from strings.
No external dependencies. Python ≥ 3.11.

## Users and personas

| Persona | Description | Primary goal |
|---------|-------------|--------------|
| Developer | Python programmer embedding calc in their app | Evaluate user-input expressions safely |

## Functional requirements

- FR-1: `evaluate("2 + 3")` returns `5.0`. Supports `+`, `-`, `*`, `/`, `**`, parentheses.
- FR-2: `evaluate("1 / 0")` raises `CalcError`, not `ZeroDivisionError`.
- FR-3: `tokenize("2 + 3")` returns a list of `Token` objects with type and value.

## Non-functional requirements

- NFR-1: No `eval()` or `exec()` — the parser must be hand-written.
- NFR-2: Expressions up to 1000 characters evaluate in under 10ms.

## Constraints

- Pure Python, no external dependencies.
- Python ≥ 3.11.

## Technology preferences

| Layer | Choice | Reason |
|-------|--------|--------|
| Language | Python 3.11+ | project standard |
| Testing | unittest | stdlib only |

## Out of scope

- Variables, assignments, functions (sin, cos, etc.)
- REPL or CLI interface
- Persistent state
