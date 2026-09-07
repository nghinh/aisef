# Release Checklist — AISEF v0.3.1

Release commit: `cda67461f095bd762a9b45b6c8ea1440acee7f28`
Release date: 2026-09-08

## Pre-release gates

| Gate | Status | Evidence |
|------|--------|----------|
| Version bump `0.3.1.dev0` → `0.3.1` | PASS | `pyproject.toml` line 7 |
| CHANGELOG v0.3.1 entry | PASS | `CHANGELOG.md` §v0.3.1 |
| Full test suite | PASS | 1752 tests, 17 skipped, 0 failures (186s) |
| Release gate test | PASS | version not `.dev`, CHANGELOG entry present |
| Security regression tests | PASS | 6 new tests in `test_compile`, `test_context`, `test_impact` |
| Build (wheel + sdist) | PASS | `twine check` clean |
| Clean install from wheel | PASS | `aisef --help`, `python -m aisef --help`, `aisef doctor` all work, version = 0.3.1 |
| Consistency audit (stale refs) | PASS | No stale version/name references found |
| `.gitignore` includes `.env` | PASS | Added in 360° audit commit `d177420` |

## Security fixes verified

| Fix | File | Method |
|-----|------|--------|
| `shlex.split` + `shell=False` | `context._run_provider` | Source + regression test |
| `shlex.split` + `shell=False` | `impact._run_command` | Source + regression test |
| `shlex.quote` for paths | `compile._guard_command` | Source + 4 edge-case tests (spaces, quotes, `$(...)`, bin path) |

## Packaging

| Item | Value |
|------|-------|
| Package name | `aisef` |
| Version | `0.3.1` |
| Python requires | `>=3.11` |
| Dependencies | none (stdlib only) |
| Entry point | `aisef = aisef.cli:main` |
| `python -m aisef` | yes (`__main__.py`) |

## Publish

| Step | Status | Detail |
|------|--------|--------|
| Tag `v0.3.1` | PENDING | |
| Push tag | PENDING | |
| Trusted Publisher (GitHub Actions) | PENDING | `release.yml`, environment `pypi` |
| PyPI install verification | PENDING | |

## Post-publish

| Step | Status | Detail |
|------|--------|--------|
| `pip install aisef==0.3.1` from PyPI | PENDING | |
| `aisef --help` | PENDING | |
| `aisef doctor` | PENDING | |
| Bump to next dev version | PENDING | |
