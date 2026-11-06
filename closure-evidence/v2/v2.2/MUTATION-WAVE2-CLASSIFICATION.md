# Mutation survivor classification — ROADMAP-2.2 Đợt 2 (Lane M)

Owner decision #4 (2026-11-06): *complete Lane M and classify survivors by evidence; no registry change, no loosened acceptance criteria.* Owner directive #1 binding: no scope reduction, EQUIVALENT requires documented reasoning, never downgrade to beautify. Machine-readable per-mutant record: [`MUTATION-WAVE2-CLASSIFICATION.json`](./MUTATION-WAVE2-CLASSIFICATION.json).

## Campaign (frozen commit 89de4685, 4 workers)

| | mutants | killed | survived | infra | not_run |
|---|---|---|---|---|---|
| w1 `run.py::execute` | 458 | 380 | 78 | 0 | 0 |
| w2 (`_ocr`, `session`) | 493 | 470 | 23 | 0 | 0 |
| w3 (tripwire×8, registry×4, verify×2, bundle_cli.lint) | 572 | 456 | 116 | 0 | 0 |
| w4 (`settings.load`, `seal`, `bundle.load`) | 631 | 597 | 34 | 0 | 0 |
| **total** | **2154** | **1903** | **251** | **0** | **0** |

`run.py::execute`: 78 raw survivors = **74 distinct** descriptions (4 duplicate descriptions share the twin's verdict). Distinct survivors across all workers: **247**.

## Method — two independent passes per survivor

1. **Classify** (19 per-target agents for w2/w3/w4 + 4 line-range agents for `run.py::execute`): EQUIVALENT (behaviorally identical on all inputs — no test could ever kill it, with a code-grounded proof) vs SURVIVED (a real test-coverage gap). Default SURVIVED; read the frozen source and tests.
2. **Adversarial refutation** of **every** EQUIVALENT verdict: an independent agent tries to *break* the equivalence by exhibiting a distinguishing input/observable. Final EQUIVALENT only if the refutation could not.

This method moves the count the honest direction (a false "equivalent" hides a gap). The refutation overturned most first-pass equivalents:

**Two-pass funnel: 45 classified EQUIVALENT → only 11 upheld after refutation (34 flipped to real gaps).**

## Result

| | count |
|---|---|
| distinct survivors | 247 |
| **confirmed EQUIVALENT** | **11** |
| **real coverage gap (SURVIVED)** | **236** |

### Per-target

| target | survivors | equiv | real gap |
|---|---|---|---|
| `run.py::execute` | 74 | 1 | 73 |
| `registry.py::register_runtime` | 19 | 1 | 18 |
| `registry.py::registry_digest` | 18 | 0 | 18 |
| `bundle_cli.py::seal` | 16 | 6 | 10 |
| `tripwire.py::refusal` | 14 | 0 | 14 |
| `adapters.py::Reviewer._ocr` | 13 | 0 | 13 |
| `bundle.py::load` | 12 | 0 | 12 |
| `verify.py::verify` | 12 | 3 | 9 |
| `registry.py::runtime_mechanism_digest` | 12 | 0 | 12 |
| `client.py::session` | 10 | 0 | 10 |
| `tripwire.py::_bundle_hit` | 9 | 0 | 9 |
| `tripwire.py::scan_repo` | 9 | 0 | 9 |
| `settings.py::load` | 6 | 0 | 6 |
| `tripwire.py::_public_text` | 5 | 0 | 5 |
| `tripwire.py::_canonical` | 4 | 0 | 4 |
| `tripwire.py::needles_of` | 4 | 0 | 4 |
| `verify.py::_invariant_problems` | 4 | 0 | 4 |
| `tripwire.py::scan_text` | 3 | 0 | 3 |
| `bundle_cli.py::lint` | 2 | 0 | 2 |
| `tripwire.py::_fragments` | 1 | 0 | 1 |

### The 11 confirmed equivalents (each survived an adversarial refutation)

- `bundle_cli.seal` ×6 — `tuple()→list()` at L523/560/597/604 (the value is JSON-serialized, where tuple and list are the same array) and `element 0 dropped` at L553/598 (the dropped element is never observed downstream).
- `verify.verify` ×3 — L225 `dict entry 0/1 dropped` and the `'begun and never ended in the journal'` diagnostic string, none observed by any consumer or test.
- `registry.register_runtime` ×1 — L454 `Or swapped`: both operands are side-effect-free and read the same module global; logical OR is commutative, and a non-class operand raises the identical `TypeError` either way.
- `run.py::execute` ×1 — L493 `'repository'` emptied: a dead store, unconditionally overwritten at L515 before any read; STARTED/RUN.json use the live value (L577) and `sort_keys=True`.

## Interpretation (owner #1)

The **236 real gaps are not failures** — they are honest test-coverage gaps a test *could* assert but none currently does: diagnostic-string content, digest/record internals (`registry_digest`'s 18 are all real because its output is a hash input), and uncovered refusal branches (`tripwire.refusal`'s 14, the `register_runtime` guards). They are reported **as-is**: no scope reduction, no criteria loosened, no registry change. They are candidate kill-tests for a future hardening wave, not a wave-2 blocker.

## Record-currency note (relates to owner #5)

The campaign's post-run record-currency gate reported `mutation: FAIL` on `validation/v2/cleanup_authority.py` (`carriers`/`cwd_under`/`host_table`): *"target changed since the mutation run — re-run it."* This is **pre-existing staleness unrelated to the wave-2 targets** and does **not** invalidate the kill/survive verdicts above (those mutants ran to completion with 0 infra / 0 not_run). Resolving it is part of reseal, owner decision #5 (not executed).
