# evidence-discipline

A linter for figures in documentation: every number with a unit must be cited to a run id in
`infrastructure/ci/run_registry.json`, marked `target:`, or keyed to `benchmark.pending`.

```
python3 infrastructure/ci/evidence_discipline.py --root docs/capacity.md
python3 -m pytest infrastructure/ci -q
```

The requested changes are in `docs/requirements-delta.md`.
