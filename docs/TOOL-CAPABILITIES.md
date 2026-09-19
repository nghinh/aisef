# Default tool capabilities

Rendered from `aisef/harness/capabilities.py` by `validation/render_hardening_docs.py capabilities`; `tests/hardening/test_tool_capability.py` keeps it in sync. This is the product contract for the evidence tools AISEF selects when a project leaves `tools.<role>` empty (INV-N.DEFAULT-CAPABILITY): every tool listed as selected is executable in the environment listed for its stack, proven on real images by `validation/tool_capability_qualification.py` (`closure-evidence/hardening/tool-capability-matrix.json`).

## Configuration semantics

| `tools.<role>` | `tools.disabled` | meaning |
|---|---|---|
| empty | role not listed | **AUTO** — the stack profile below decides; this is the only meaning of empty |
| a command | role not listed | **EXPLICIT** — the project's command, probed where it runs |
| empty | role listed | **DISABLED** — typed off: never run, never evidence, recorded as such |
| a command | role listed | refused at config load (contradiction) |

Required roles (test, lint) cannot be disabled. A role a profile leaves empty (**none** below) runs nothing and says why; the gate never pretends such a tool exists.

Provision: **managed** = installed by the harness-built image at the pinned version; **toolchain** = part of the digest-pinned base image; **project** = the project declares it (the image provides the runtime); **none** = no default tool for the role.

## Profiles

### node

- markers: `package.json`
- environment: `node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`

| role | tool | command | provision | version | evidence | note |
|---|---|---|---|---|---|---|
| test | npm-test | `npm test --silent` | project | the project's own lockfile | the project's `test` script | selected only when package.json declares a `test` script |
| lint | npm-lint | `npm run lint --silent` | project | the project's own lockfile | the project's `lint` script | selected only when package.json declares `lint` (else `typecheck`: `npm run typecheck --silent`) |
| sast | — | — | none | n/a | — | no default Node SAST: `npm audit` is a dependency audit that needs the npm registry, and the security sandbox has no network (measured 2026-09-17 in node:22-alpine: `EAI_AGAIN registry.npmjs.org`); declare `tools.sast` to run a project scanner |

Runtime probes: `node --version` → `v22.23.2`, `npm --version` → `10.9.8`

### python

- markers: `pyproject.toml`, `setup.py`
- environment: `aisef-verify-python:84adf1d8eaf9` (built from `python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`)

```dockerfile
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
RUN pip install --no-cache-dir --disable-pip-version-check pytest==9.1.1 pytest-cov==7.1.0 ruff==0.16.7 bandit==1.9.4
```

| role | tool | command | provision | version | evidence | note |
|---|---|---|---|---|---|---|
| test | pytest | `pytest -q` | managed | pinned 9.1.1 | test results | — |
| lint | ruff | `ruff check .` | managed | pinned 0.16.7 | lint findings | — |
| sast | bandit | `bandit -q -r .` | managed | pinned 1.9.4 | static security findings | — |

### go

- markers: `go.mod`
- environment: `aisef-verify-go:6a26aba68eaa` (built from `golang:1.26-alpine@sha256:ce864e7223ac17b1775e6fd0b4c0db580c2eb50e7953a427916379e4b92a1628`)

```dockerfile
FROM golang:1.26-alpine@sha256:ce864e7223ac17b1775e6fd0b4c0db580c2eb50e7953a427916379e4b92a1628
RUN CGO_ENABLED=0 GOBIN=/usr/local/bin GOFLAGS=-trimpath go install github.com/securego/gosec/v2/cmd/gosec@v2.29.0
ENV GOCACHE=/tmp/go-build
```

| role | tool | command | provision | version | evidence | note |
|---|---|---|---|---|---|---|
| test | go-test | `go test ./...` | toolchain | pinned by the base image digest | test results | — |
| lint | go-vet | `go vet ./...` | toolchain | pinned by the base image digest | lint findings | — |
| sast | gosec | `gosec ./...` | managed | pinned 2.29.0 | static security findings | — |

### rust

- markers: `Cargo.toml`
- environment: `aisef-verify-rust:33cd9daabc13` (built from `rust:1-alpine@sha256:1716b3aa042d735f4566d14dc54e8037de9d69556e2d5dd58131d93a613d173d`)

```dockerfile
FROM rust:1-alpine@sha256:1716b3aa042d735f4566d14dc54e8037de9d69556e2d5dd58131d93a613d173d
RUN rustup component add clippy
RUN cargo install cargo-audit --locked --version 0.22.2 --root /usr/local
RUN mkdir -p /usr/local/share/advisory-db && wget -qO- https://github.com/rustsec/advisory-db/archive/f58ccfe51a5954186716998f01360d1079a8a3a5.tar.gz | tar -xz --strip-components=1 -C /usr/local/share/advisory-db
```

| role | tool | command | provision | version | evidence | note |
|---|---|---|---|---|---|---|
| test | cargo-test | `cargo test` | toolchain | pinned by the base image digest | test results | — |
| lint | clippy | `cargo clippy -- -D warnings` | managed | pinned 0.1.98 | lint findings | — |
| sast | cargo-audit | `cargo audit --no-fetch --stale --no-yanked --db /usr/local/share/advisory-db` | managed | pinned 0.22.2 | known-vulnerability findings for Cargo.lock (rustsec advisory-db f58ccfe51a59, baked in) | — |

### ruby

- markers: `Gemfile`
- environment: `ruby:3-alpine@sha256:c5a5064d190055633011c03aa800170cc36945ff3afb5f6c915329f92d6f1e00`

| role | tool | command | provision | version | evidence | note |
|---|---|---|---|---|---|---|
| test | — | — | none | n/a | — | no default Ruby tool: `bundle exec rspec/rubocop/brakeman` run the project's own gems, which ruby:3-alpine does not carry and the offline sandbox cannot install (measured 2026-09-17: none present); declare `tools.*` and a `sandbox.image` carrying the bundle |
| lint | — | — | none | n/a | — | no default Ruby tool: `bundle exec rspec/rubocop/brakeman` run the project's own gems, which ruby:3-alpine does not carry and the offline sandbox cannot install (measured 2026-09-17: none present); declare `tools.*` and a `sandbox.image` carrying the bundle |
| sast | — | — | none | n/a | — | no default Ruby tool: `bundle exec rspec/rubocop/brakeman` run the project's own gems, which ruby:3-alpine does not carry and the offline sandbox cannot install (measured 2026-09-17: none present); declare `tools.*` and a `sandbox.image` carrying the bundle |

Runtime probes: `ruby --version` → `ruby 3.4.10`, `bundle --version` → `2.6.9`

### php

- markers: `composer.json`
- environment: `php:8-cli-alpine@sha256:dae77e6aa4934d22b903da93e0e506c34032f5d8f8f91693d2cbf6e2724ddf73`

| role | tool | command | provision | version | evidence | note |
|---|---|---|---|---|---|---|
| test | — | — | none | n/a | — | no default PHP tool: `composer test/lint` need composer, absent from php:8-cli-alpine (measured 2026-09-17), and the project's vendor tree; declare `tools.*` and a `sandbox.image` that carries them |
| lint | — | — | none | n/a | — | no default PHP tool: `composer test/lint` need composer, absent from php:8-cli-alpine (measured 2026-09-17), and the project's vendor tree; declare `tools.*` and a `sandbox.image` that carries them |
| sast | — | — | none | n/a | — | no default PHP tool: `composer test/lint` need composer, absent from php:8-cli-alpine (measured 2026-09-17), and the project's vendor tree; declare `tools.*` and a `sandbox.image` that carries them |

Runtime probes: `php --version` → `PHP 8.5.10`

### flutter

- markers: `pubspec.yaml`
- environment: `alpine:latest`

| role | tool | command | provision | version | evidence | note |
|---|---|---|---|---|---|---|
| test | — | — | none | n/a | — | no managed Flutter environment: the fallback image carries no flutter (measured 2026-09-17); declare `tools.*` and a `sandbox.image` carrying the SDK |
| lint | — | — | none | n/a | — | no managed Flutter environment: the fallback image carries no flutter (measured 2026-09-17); declare `tools.*` and a `sandbox.image` carrying the SDK |
| sast | — | — | none | n/a | — | no managed Flutter environment: the fallback image carries no flutter (measured 2026-09-17); declare `tools.*` and a `sandbox.image` carrying the SDK |

Any project without a marker runs its explicit tools in `alpine:latest`, which carries no stack tool.
