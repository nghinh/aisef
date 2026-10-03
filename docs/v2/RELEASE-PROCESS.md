# AISEF V2 — release process

Authority: the owner charter [V2-STABLE-RELEASE-CHARTER.md](V2-STABLE-RELEASE-CHARTER.md) — G1 (product vehicle),
G2 (exact RC), G6 (public delivery path), G8 (release mechanics), §9 (productize), §10 (workflow hardening),
§18 (staging / clean install), §19 (final production hold), §22 (phase checkpoints). This page describes the
mechanics that implement them; where it and the charter differ, the charter wins.

## What ships

One distribution, `aisef`, carrying exactly two packages:

| package  | what it is | how it is reached |
|----------|------------|-------------------|
| `aisef2` | the V2 runtime, every subpackage | `aisef run …` — every argument after `run` goes to `aisef2.app.cli.run(argv)`; this is the authoritative execution path (G1). Usage: `docs/v2/USAGE.md` |
| `aisef`  | V1 and the console script `aisef = aisef.cli:main` | all other commands; V1 execution only as the explicitly named legacy surface `aisef legacy run …`, never the default |

Nothing else ships: no `tests/`, `validation/`, `closure-evidence/`. `pyproject.toml`
(`include = ["aisef", "aisef.*", "aisef2", "aisef2.*"]`) and `MANIFEST.in` (`prune tests`) say so;
`validation/v2/packaging_check.py` holds it:

```bash
python -P validation/v2/packaging_check.py --check            # the pyproject table (a calibrated Q0 checker)
python -P validation/v2/packaging_check.py --artifacts dist   # the built wheel and sdist
```

If the V2 runtime is missing from an install, `aisef run` fails with exit 1 and says so; it never falls back to V1.

## The version

`version` in `pyproject.toml` is the only place the version lives (`aisef --version` reads the installed
metadata). It stays `1.7.6` until the V2.0-RC1 freeze, where it becomes `2.0.0` in the frozen candidate itself
(charter §10, §11). A production tag must equal it.

## Tags and workflows

| event | workflow | publishes? |
|-------|----------|------------|
| push to `master` or `release/**`, any pull request | `tests.yml` | no |
| tag `v*rc*`, `v*-rc*`, `v*.dev*` (e.g. `v2.0.0rc1`, `v2.0.0-rc1`, `v2.0.0.dev1`) | `staging.yml` | **never** |
| manual run (workflow_dispatch) | `staging.yml` | **never** |
| tag exactly `vX.Y.Z` (filter `v[0-9]+.[0-9]+.[0-9]+`, re-checked by `^v[0-9]+\.[0-9]+\.[0-9]+$`) | `release.yml` | production PyPI, only behind every gate below |
| any other `v*` tag (`v2.0`, `v2.0.0-beta`, `v2.0.0.post1`) | none | no |

`tests/test_release_gate.py` (`ReleaseWorkflowsCannotPublishByAccident`) fails if the production trigger widens,
if a gate leaves the publish job's `needs`, or if any workflow other than `release.yml` gains a way to publish.

## Staging (`staging.yml`) — the non-production artifact path

1. Builds the sdist and, from it, the wheel — once (`python -m build`), `twine check`, `packaging_check --artifacts`.
2. Records their sha256 in `SHA256SUMS` and in the run's summary; uploads `dist` and `dist-sha256` as workflow
   artifacts. Those digests are what the RC freeze records as `RC_WHEEL_DIGEST` / `RC_SDIST_DIGEST` (G2, §11).
3. On `ubuntu-latest` and `windows-latest`: downloads the artifacts, checks them against `SHA256SUMS`, installs
   exactly that wheel (`--no-index --no-deps`) into a fresh venv, and runs the clean-install smoke from outside the
   checkout with the venv's interpreter, isolated:
   `python -I tests/installed_smoke.py <pyproject version> --product` — `aisef` and `aisef2` import from the
   installed artifact, `aisef --version` reports the version, V1's runtime data is packaged, and the V2 runtime
   entry `aisef2.app.cli.run` is present.

It has no publish step and no `id-token` permission. TestPyPI is not wired: the charter accepts "TestPyPI or an
equivalent non-production artifact verification path" (G8), and this is that path. Adding TestPyPI is an owner
decision (account, trusted publisher, and TestPyPI never accepts the same version twice).

## Production (`release.yml`) — gated, then held for the owner

On a `vX.Y.Z` tag, in one run:

| job | gate |
|-----|------|
| `stable-tag` | the ref is a tag of exactly `vX.Y.Z` |
| `tests` | the whole `tests.yml` on the tagged commit: unit on ubuntu (3.11, 3.12, 3.13, 3.14) + windows (3.11) inside the owned process range, the V1 evidence guard, lint, the wheel job |
| `staging` | the whole `staging.yml` above |
| `v2-gate` | `python -P validation/v2_release_gate.py <version>` |
| `publish` | needs all four; environment `pypi`; re-checks `SHA256SUMS`, then uploads exactly the files staging built and smoked (trusted publishing) |

### The V2 release gate

`validation/v2_release_gate.py <version>` exits 0 only when all of these hold:

- `<version>` is a stable `X.Y.Z` and equals `pyproject.toml`'s version;
- `closure-evidence/v2/release/V2-STABLE-STATUS.json` has `FINAL_RELEASE_READY: "PASS"` and
  `OPEN_V2_0_BLOCKERS: []` (charter §22);
- in `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json`, the latest entry (by `seq`) whose `decision` has a
  `PRODUCTION_PUBLISH` key is the owner's and authorizes exactly this version:
  `approver: "human:owner"`, `decision.PRODUCTION_PUBLISH: "AUTHORIZED"`, `decision.VERSION: "<version>"`.
  A later entry that holds or revokes publication wins over an earlier authorization.

Today it fails, by design: `FINAL_RELEASE_READY` is `NOT_STARTED`, blockers are open, and entry seq 2 rules
`PRODUCTION_PUBLISH: "HELD for the owner's final confirmation (charter §19)"`.

### It replaces the V1 conformance-freshness gate

Up to 1.7.x `release.yml` ran `AISEF_RELEASE=1 python -m unittest tests.test_release_gate`: V1 client
conformance (`docs/CONFORMANCE.md`, dated 2026-09-17) no older than `MAX_AGE_DAYS = 14`
(`aisef/control/conformance.py`), plus the V1 dogfood acceptance corpus. Charter G8 requires release
conformance/freshness gates to be "current or explicitly replaced by this V2 release charter", and §10 requires
the stale policy to be refreshed or replaced. It is **replaced**: on the V2 release path the V2 release gate above
is what authorizes publication, and the V1 gate neither blocks nor authorizes a release. Its code is kept intact for
the legacy V1 surface and its history (`tests/test_release_gate.py` `TestCongPhatHanh`; `conformance.yml` still runs
it weekly).

## How the owner confirms (charter §19)

The release lane does everything up to the hold and returns `FINAL_RELEASE_READY = YES`. Then the owner:

1. appends the authorizing entry to `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` (append-only; never
   rewrite seq 1 or 2), for example:

   ```json
   {"seq": 3, "id": "AISEF_V2_0_PRODUCTION_PUBLISH", "approver": "human:owner",
    "authority": "owner final production-publish confirmation (charter §19)",
    "decision": {"PRODUCTION_PUBLISH": "AUTHORIZED", "VERSION": "2.0.0",
                 "RC_SOURCE_SHA": "<sha>", "RC_WHEEL_DIGEST": "<sha256>", "RC_SDIST_DIGEST": "<sha256>"}}
   ```

   (the gate reads `approver`, `PRODUCTION_PUBLISH` and `VERSION`; the RC identities are the record);
2. confirms `V2-STABLE-STATUS.json` says `FINAL_RELEASE_READY: "PASS"` with no open blocker, on the commit to tag;
3. creates and pushes the stable tag on that commit: `git tag v2.0.0 <sha> && git push origin v2.0.0`;
4. approves the `publish` job's deployment to the `pypi` environment once every gate is green;
5. after publication, verifies a clean install: `pip install aisef==2.0.0`, `aisef --version`, `aisef run …`.

## One-time setup (owner)

- PyPI: project `aisef` has a trusted publisher for repository `nghinh/aisef`, workflow `release.yml`,
  environment `pypi` (renaming the repository is changing the publisher).
- GitHub: protect the `pypi` environment — required reviewer: the owner; deployment branches and tags: tags
  matching `v*.*.*` only. That approval is the human hold of §19 on top of the RELEASE-DECISIONS entry.

## Reproducing the checks locally

```bash
python -P validation/v2/packaging_check.py --check
python -m build                                   # or any PEP 517 build of the sdist, then the wheel from it
python -P validation/v2/packaging_check.py --artifacts dist
python -m venv /path/outside/checkout/venv && /path/outside/checkout/venv/bin/pip install --no-index --no-deps dist/*.whl
(cd /path/outside/checkout && venv/bin/python -I <checkout>/tests/installed_smoke.py 1.7.6 --product)
python -P validation/v2_release_gate.py 2.0.0     # fails until the owner authorizes
```
