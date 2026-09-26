"""Stack capability profiles — the ONE source of truth for which evidence tool AISEF selects by default for a stack
and for what the managed environment of that stack carries (SS-65, INV-N.DEFAULT-CAPABILITY).

Before SS-65 these were two tables: `tools._STACK_COMMANDS` auto-selected `bandit` for every Python project while
`verify_image.RECIPES` built a Python image without it, so every default Python run stopped at the tools preflight
(W1 run 1, 2026-09-17). A `Capability` row now names the tool, the role it fills, the exact command, how the
environment provides it, the pinned version and the probe that proves it; selection (`tools.py`), image recipes and
probes (`verify_image.py`), the `init --stack` presets and the capability qualification
(`validation/tool_capability_qualification.py`) read these rows and nothing else.

Config semantics (one meaning each): `tools.<role>` empty → AUTO (this profile decides); non-empty → EXPLICIT (the
project's command); the role listed in `tools.disabled` → DISABLED (typed off, never run, never evidence). A required
role cannot be disabled, and a role cannot be both disabled and set.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

#: Images the harness builds itself carry this prefix; the tag is a digest of the rendered recipe.
MANAGED_PREFIX = "aisef-verify-"
#: The provider's image when no profile applies — it carries no stack tool.
FALLBACK_IMAGE = "alpine:latest"


class Role(str, Enum):
    TEST = "test"
    LINT = "lint"
    SAST = "sast"


#: Roles a project may not switch off: every story is scored by them (preflight `Need`s tools.test and tools.lint).
REQUIRED_ROLES = (Role.TEST, Role.LINT)


class Provision(str, Enum):
    MANAGED = "managed"      # the harness-built image installs it at a pinned version; the probe checks that version
    TOOLCHAIN = "toolchain"  # part of the digest-pinned base image; the probe checks the toolchain answers
    PROJECT = "project"      # the project declares it (an npm script); the image provides the runtime, which is probed
    NONE = "none"            # this profile selects no tool for the role — stated, never pretended


class Mode(str, Enum):
    AUTO = "auto"
    EXPLICIT = "explicit"
    DISABLED = "disabled"


@dataclass(frozen=True)
class Probe:
    argv: tuple[str, ...]
    expect: str = ""          # a substring the probe's combined output must contain (the pinned version)


@dataclass(frozen=True)
class Capability:
    tool_id: str
    role: Role
    command: str
    provision: Provision
    evidence: str                            # what a run of this tool is evidence of
    install: tuple[str, ...] = ()            # `pip:<req>` · `go:<pkg>@<v>` · `rustup:<component>` · `cargo:<crate>@<v>` · `tar:<dir>=<url>` · `env:<K>=<V>`
    version: str = ""                        # the pinned version ("" → the base image's toolchain)
    probes: tuple[Probe, ...] = ()
    note: str = ""                           # NONE: why nothing is selected · PROJECT: when it is selected

    @property
    def required(self) -> bool:
        return self.role in REQUIRED_ROLES

    @property
    def version_policy(self) -> str:
        return {Provision.MANAGED: f"pinned {self.version}",
                Provision.TOOLCHAIN: "pinned by the base image digest",
                Provision.PROJECT: "the project's own lockfile",
                Provision.NONE: "n/a"}[self.provision]


def _none(role: Role, why: str) -> Capability:
    return Capability(f"none-{role.value}", role, "", Provision.NONE, "", note=why)


@dataclass(frozen=True)
class StackProfile:
    stack: str
    markers: tuple[str, ...]
    base: str                                # image pinned by digest; "" → no managed environment for this stack
    capabilities: tuple[Capability, ...]
    runtime: tuple[Probe, ...] = ()          # what PROJECT capabilities rely on

    def capability(self, role: Role) -> Capability:
        return next(c for c in self.capabilities if c.role is role)

    @property
    def managed(self) -> bool:
        return any(c.provision is Provision.MANAGED for c in self.capabilities)

    def dockerfile(self) -> str:
        """The recipe, rendered from the capabilities in order (all pip requirements in one layer). `env:` lines
        describe the RUNTIME environment and come after every install step: set before them, the build (as root)
        populated a GOCACHE the sandbox's non-root user could not use (measured 2026-09-17)."""
        lines, pip, env = [f"FROM {self.base}"], [], []
        for spec in (s for c in self.capabilities for s in c.install):
            kind, _, arg = spec.partition(":")
            if kind == "pip":
                if not pip:
                    lines.append("__PIP__")
                pip.append(arg)
            elif kind == "go":
                lines.append(f"RUN CGO_ENABLED=0 GOBIN=/usr/local/bin GOFLAGS=-trimpath go install {arg}")
            elif kind == "rustup":
                lines.append(f"RUN rustup component add {arg}")
            elif kind == "cargo":
                crate, _, ver = arg.partition("@")
                lines.append(f"RUN cargo install {crate} --locked --version {ver} --root /usr/local")
            elif kind == "env":
                env.append(f"ENV {arg}")
            elif kind == "tar":
                dest, _, url = arg.partition("=")
                lines.append(f"RUN mkdir -p {dest} && wget -qO- {url} | tar -xz --strip-components=1 -C {dest}")
            else:
                raise ValueError(f"{self.stack}: unknown install scheme {spec!r}")
        text = "\n".join(lines + env) + "\n"
        return text.replace("__PIP__", "RUN pip install --no-cache-dir --disable-pip-version-check " + " ".join(pip))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.dockerfile().encode("utf-8")).hexdigest()

    @property
    def image(self) -> str:
        if not self.base:
            return FALLBACK_IMAGE
        return f"{MANAGED_PREFIX}{self.stack}:{self.digest[:12]}" if self.managed else self.base


_ADVISORY_DB = "/usr/local/share/advisory-db"
_ADVISORY_SHA = "f58ccfe51a5954186716998f01360d1079a8a3a5"   # rustsec/advisory-db main, 2026-09-17

#: Order matters: the first profile whose marker exists wins (package.json first, as before SS-65).
PROFILES: tuple[StackProfile, ...] = (
    StackProfile(
        "node", ("package.json",),
        base="node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32",
        runtime=(Probe(("node", "--version"), "v22.23.2"), Probe(("npm", "--version"), "10.9.8")),
        capabilities=(
            Capability("npm-test", Role.TEST, "npm test --silent", Provision.PROJECT, "the project's `test` script",
                       note="selected only when package.json declares a `test` script"),
            Capability("npm-lint", Role.LINT, "npm run lint --silent", Provision.PROJECT, "the project's `lint` script",
                       note="selected only when package.json declares `lint` (else `typecheck`: `npm run typecheck --silent`)"),
            _none(Role.SAST, "no default Node SAST: `npm audit` is a dependency audit that needs the npm registry, and "
                             "the security sandbox has no network (measured 2026-09-17 in node:22-alpine: "
                             "`EAI_AGAIN registry.npmjs.org`); declare `tools.sast` to run a project scanner"),
        )),
    StackProfile(
        "python", ("pyproject.toml", "setup.py"),
        base="python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea",
        capabilities=(
            Capability("pytest", Role.TEST, "pytest -q", Provision.MANAGED, "test results",
                       install=("pip:pytest==9.1.1", "pip:pytest-cov==7.1.0"), version="9.1.1",
                       probes=(Probe(("pytest", "--version"), "pytest 9.1.1"),
                               Probe(("python", "-c", "import pytest_cov; print('pytest-cov', pytest_cov.__version__)"),
                                     "pytest-cov 7.1.0"))),
            Capability("ruff", Role.LINT, "ruff check .", Provision.MANAGED, "lint findings",
                       install=("pip:ruff==0.16.7",), version="0.16.7", probes=(Probe(("ruff", "--version"), "ruff 0.16.7"),)),
            Capability("bandit", Role.SAST, "bandit -q -r .", Provision.MANAGED, "static security findings",
                       install=("pip:bandit==1.9.4",), version="1.9.4", probes=(Probe(("bandit", "--version"), "bandit 1.9.4"),)),
        )),
    StackProfile(
        "go", ("go.mod",),
        base="golang:1.26-alpine@sha256:ce864e7223ac17b1775e6fd0b4c0db580c2eb50e7953a427916379e4b92a1628",
        capabilities=(
            # The sandbox runs as a non-root user without a home: the toolchain's default build cache
            # (`$HOME/.cache/go-build`) is not writable there (measured 2026-09-17: every go command failed).
            Capability("go-test", Role.TEST, "go test ./...", Provision.TOOLCHAIN, "test results",
                       install=("env:GOCACHE=/tmp/go-build",),
                       probes=(Probe(("go", "version"), "go1.26.8"), Probe(("go", "env", "GOCACHE"), "/tmp/go-build"))),
            Capability("go-vet", Role.LINT, "go vet ./...", Provision.TOOLCHAIN, "lint findings",
                       probes=(Probe(("go", "tool", "-n", "vet"), "vet"),)),
            Capability("gosec", Role.SAST, "gosec ./...", Provision.MANAGED, "static security findings",
                       install=("go:github.com/securego/gosec/v2/cmd/gosec@v2.29.0",), version="2.29.0",
                       probes=(Probe(("go", "version", "-m", "/usr/local/bin/gosec"), "v2.29.0"),)),
        )),
    StackProfile(
        "rust", ("Cargo.toml",),
        base="rust:1-alpine@sha256:1716b3aa042d735f4566d14dc54e8037de9d69556e2d5dd58131d93a613d173d",
        capabilities=(
            Capability("cargo-test", Role.TEST, "cargo test", Provision.TOOLCHAIN, "test results",
                       probes=(Probe(("cargo", "--version"), "cargo 1.98.1"),)),
            Capability("clippy", Role.LINT, "cargo clippy -- -D warnings", Provision.MANAGED, "lint findings",
                       install=("rustup:clippy",), version="0.1.98",
                       probes=(Probe(("cargo", "clippy", "--version"), "clippy 0.1.98"),)),
            # `--no-yanked`: the yanked-crate check reads the crates.io index, which the offline security sandbox cannot
            # reach (measured: `failed to obtain lock file '/usr/local/cargo/.package-cache'`); the advisory check is kept.
            Capability("cargo-audit", Role.SAST, f"cargo audit --no-fetch --stale --no-yanked --db {_ADVISORY_DB}", Provision.MANAGED,
                       f"known-vulnerability findings for Cargo.lock (rustsec advisory-db {_ADVISORY_SHA[:12]}, baked in)",
                       install=("cargo:cargo-audit@0.22.2",
                                f"tar:{_ADVISORY_DB}=https://github.com/rustsec/advisory-db/archive/{_ADVISORY_SHA}.tar.gz"),
                       version="0.22.2",
                       probes=(Probe(("cargo", "audit", "--version"), "0.22.2"),
                               Probe(("test", "-d", f"{_ADVISORY_DB}/crates")))),
        )),
    StackProfile(
        "ruby", ("Gemfile",),
        base="ruby:3-alpine@sha256:c5a5064d190055633011c03aa800170cc36945ff3afb5f6c915329f92d6f1e00",
        runtime=(Probe(("ruby", "--version"), "ruby 3.4.10"), Probe(("bundle", "--version"), "2.6.9")),
        capabilities=tuple(_none(r, "no default Ruby tool: `bundle exec rspec/rubocop/brakeman` run the project's own gems, "
                                    "which ruby:3-alpine does not carry and the offline sandbox cannot install (measured "
                                    "2026-09-17: none present); declare `tools.*` and a `sandbox.image` carrying the bundle")
                           for r in Role)),
    StackProfile(
        "php", ("composer.json",),
        base="php:8-cli-alpine@sha256:dae77e6aa4934d22b903da93e0e506c34032f5d8f8f91693d2cbf6e2724ddf73",
        runtime=(Probe(("php", "--version"), "PHP 8.5.10"),),
        capabilities=tuple(_none(r, "no default PHP tool: `composer test/lint` need composer, absent from php:8-cli-alpine "
                                    "(measured 2026-09-17), and the project's vendor tree; declare `tools.*` and a "
                                    "`sandbox.image` that carries them")
                           for r in Role)),
    StackProfile(
        "flutter", ("pubspec.yaml",), base="",
        capabilities=tuple(_none(r, "no managed Flutter environment: the fallback image carries no flutter (measured "
                                    "2026-09-17); declare `tools.*` and a `sandbox.image` carrying the SDK")
                           for r in Role)),
)


def profile_for(project: Path | str) -> StackProfile | None:
    project = Path(project)
    return next((p for p in PROFILES if any((project / m).is_file() for m in p.markers)), None)


def profile_by_stack(stack: str) -> StackProfile:
    return next(p for p in PROFILES if p.stack == stack)


def _npm_scripts(project: Path) -> dict:
    try:
        return json.loads((project / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return {}


def auto_command(profile: StackProfile | None, role: Role, project: Path | str) -> tuple[str, Capability | None, str]:
    """(command, capability, why-empty) the profile selects for `role` in this project."""
    if profile is None:
        return "", None, "no stack profile matches this project (no marker file)"
    cap = profile.capability(role)
    if cap.provision is Provision.NONE:
        return "", cap, cap.note
    if cap.provision is Provision.PROJECT:
        scripts = _npm_scripts(Path(project))
        if role is Role.TEST and "test" in scripts:
            return cap.command, cap, ""
        if role is Role.LINT and "lint" in scripts:
            return cap.command, cap, ""
        if role is Role.LINT and "typecheck" in scripts:
            return "npm run typecheck --silent", cap, ""
        return "", cap, cap.note
    return cap.command, cap, ""


@dataclass(frozen=True)
class Resolved:
    role: Role
    mode: Mode
    command: str                  # "" → nothing runs for this role
    capability: Capability | None # the profile row when AUTO
    stack: str
    image: str
    why: str = ""                 # why nothing runs (NONE / DISABLED / no profile)

    @property
    def key(self) -> str:
        return f"tools.{self.role.value}"


class CapabilityConfigError(ValueError):
    """A contradictory or forbidden tool configuration."""


def disabled_roles(cfg) -> set[Role]:
    raw = (cfg.get("tools.disabled", []) if cfg is not None else []) or []
    out = set()
    for item in raw:
        try:
            out.add(Role(str(item)))
        except ValueError:
            raise CapabilityConfigError(f"tools.disabled: unknown role {item!r} (roles: test, lint, sast)") from None
    return out


def validate(values: dict) -> None:
    """Config-load check: `tools.disabled` names known, optional roles that are not also set explicitly."""
    for role in disabled_roles(values):
        if role in REQUIRED_ROLES:
            raise CapabilityConfigError(f"tools.disabled: `{role.value}` is required and cannot be disabled")
        if str(values.get(f"tools.{role.value}", "") or "").strip():
            raise CapabilityConfigError(f"`tools.{role.value}` is set and also listed in tools.disabled — choose one")


def resolve(project: Path | str, cfg) -> list[Resolved]:
    """The authoritative tool selection for this project: one row per role."""
    project = Path(project)
    profile = profile_for(project)
    declared_image = str((cfg.get("sandbox.image", "") if cfg is not None else "") or "").strip()
    image = declared_image or (profile.image if profile else FALLBACK_IMAGE)
    stack = profile.stack if profile else ""
    off = disabled_roles(cfg)
    rows = []
    for role in Role:
        explicit = str((cfg.get(f"tools.{role.value}", "") if cfg is not None else "") or "").strip()
        if explicit:
            rows.append(Resolved(role, Mode.EXPLICIT, explicit, None, stack, image))
        elif role in off:
            rows.append(Resolved(role, Mode.DISABLED, "", None, stack, image, "disabled by `tools.disabled`"))
        else:
            command, cap, why = auto_command(profile, role, project)
            rows.append(Resolved(role, Mode.AUTO, command, cap, stack, image, why))
    return rows
