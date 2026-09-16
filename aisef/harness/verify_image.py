"""Verification images the harness builds itself, and the probes that prove
a declared tool is present before a story pays for a session.

Measured on LedgerLock (2026-09-15, lỗi 182 / D-028): the `python` preset
paired `python -m pytest` and `ruff check .` with `python:3.12-slim`, an image
that carries neither. Every tool call is a fresh `docker run --rm`, so nothing
an agent installs survives to the next call; sixteen test runs printed `No
module named pytest`, `aisef doctor` called the image "(matches stack)", and
the operator rebuilt the image by hand while the run was in progress.

Three rules follow:

* the environment a preset declares **contains every tool the preset
  declares** — the harness builds it from a recipe, it does not hope;
* the environment's identity is **pinned**: the base image by digest, each
  tool by version, and the image name carries a digest of the recipe, so two
  machines with the same name run the same toolchain;
* a declared tool is **probed** before story execution (`aisef doctor`, and
  `aisef run` when an image is declared) — a missing tool is reported as
  missing, not discovered by a session that has already been paid for.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

MANAGED_PREFIX = "aisef-verify-"

#: Seconds allowed for one `docker build` of a recipe (pip over the network).
BUILD_TIMEOUT = 900


@dataclass(frozen=True)
class Recipe:
    stack: str
    #: Base image **by digest** — a tag moves, a digest does not.
    base: str
    #: Tools by pinned version; the order is part of the identity.
    packages: tuple[str, ...]

    def dockerfile(self) -> str:
        return (
            f"FROM {self.base}\n"
            "RUN pip install --no-cache-dir --disable-pip-version-check "
            + " ".join(self.packages) + "\n"
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.dockerfile().encode("utf-8")).hexdigest()

    @property
    def name(self) -> str:
        return f"{MANAGED_PREFIX}{self.stack}:{self.digest[:12]}"


#: `python:3.12-slim` multi-arch index digest, read from Docker Hub on
#: 2026-09-15; pytest/ruff/pytest-cov at their PyPI releases of the same day.
RECIPES: dict[str, Recipe] = {
    "python": Recipe(
        stack="python",
        base="python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea",
        packages=("pytest==9.1.1", "pytest-cov==7.1.0", "ruff==0.16.7"),
    ),
}


def is_managed(image: str) -> bool:
    return str(image or "").startswith(MANAGED_PREFIX)


def recipe_for(image: str) -> Recipe | None:
    return next((r for r in RECIPES.values() if r.name == image), None)


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def present(image: str) -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return _docker("image", "inspect", image).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


_IDS: dict[str, str] = {}


def image_id(image: str) -> str:
    """The image's content id (`sha256:…`) as Docker holds it locally — what a
    tool run **actually** ran in, recorded in evidence so two runs under one
    tag can be told apart (LedgerLock F-9: the tag stayed, the image changed
    twice mid-run). Cached per process; "" when Docker cannot say."""
    if image in _IDS:
        return _IDS[image]
    got = ""
    if shutil.which("docker"):
        try:
            p = _docker("image", "inspect", "--format", "{{.Id}}", image)
            got = p.stdout.strip() if p.returncode == 0 else ""
        except (subprocess.TimeoutExpired, OSError):
            got = ""
    _IDS[image] = got
    return got


def ensure(image: str, *, build: bool = True, log=None) -> str:
    """Make a managed image present; return "" or the reason it is not.

    Not a managed image → nothing to do (the operator owns it). Present →
    "". Otherwise build it from its recipe, once — the name carries the
    recipe digest, so a present image **is** the recipe.
    """
    if not is_managed(image):
        return ""
    recipe = recipe_for(image)
    if recipe is None:
        return (f"{image} is not a recipe this version of aisef knows — "
                f"set `sandbox.image` to one of: {', '.join(r.name for r in RECIPES.values())}")
    if not shutil.which("docker"):
        return "docker is not on PATH"
    if present(image):
        return ""
    if not build:
        return f"{image} is not built yet — run `aisef doctor` to build it"
    if log is not None:
        log(f"building verification image {image} ({recipe.base}, "
            f"{', '.join(recipe.packages)})")
    try:
        p = subprocess.run(
            ["docker", "build", "--pull", "-t", image, "-"],
            input=recipe.dockerfile(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=BUILD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"docker build of {image} exceeded {BUILD_TIMEOUT}s"
    except OSError as e:
        return f"cannot invoke docker: {e}"
    if p.returncode != 0:
        tail = [l for l in (p.stderr or p.stdout).strip().splitlines() if l.strip()]
        return f"docker build of {image} failed: {tail[-1] if tail else f'exit {p.returncode}'}"
    _IDS.pop(image, None)
    return ""


# ------------------------------------------------------------- declared tools

#: Config keys whose command produces evidence a gate reads.
_TOOL_KEYS = ("tools.test", "tools.lint", "tools.sast")
_LAUNCHERS = ("python", "python3", "py")
#: Project-local runners: the binary lives in the mounted workspace, not the
#: image, and `aisef init` already checks `node_modules/.bin` on the host.
_LOCAL_RUNNERS = ("npx", "npm", "pnpm", "yarn", "bunx", "bun")


def declared_tools(cfg, project: Path | str | None = None) -> list[tuple[str, str]]:
    """`(config key, command)` for every evidence-producing command the harness will RUN — with ``project`` the
    RESOLVED command per tool (auto-detected defaults included: bandit, gosec, cargo audit, npm test — SS-45), so the
    probe measures exactly what `aisef tool <kind>` executes; without it, the configured strings only."""
    out = []
    for key in _TOOL_KEYS:
        cmd = str(cfg.get(key, "") or "").strip()
        if project is not None:
            from .tools import command_for
            try:
                cmd = str(command_for(key.split(".", 1)[1], project, cfg) or "").strip()
            except Exception:  # noqa: BLE001 — resolution needs a manifest this project lacks: keep the configured string
                pass
        if cmd:
            out.append((key, cmd))
    for key in sorted(k for k in cfg.values if k.startswith("verify.")
                      and k not in ("verify.tool_images", "verify.waived", "verify.waiver_reason",
                                    "verify.baseline", "verify.clean_tree", "verify.nop")):
        cmd = str(cfg.get(key, "") or "").strip()
        if cmd and not isinstance(cfg.get(key), bool):
            out.append((key, cmd))
    return out


def probe_command(command: str) -> list[str] | None:
    """A command that exits 0 iff the tool `command` starts with is loadable
    where it will run — no shell, no project code.

    `python -m X …` → `python -c "import X"`; a project-local runner (`npx`,
    `npm run`) → None (not the image's to provide); anything else → the
    binary on PATH.
    """
    parts = command.replace('"', " ").replace("'", " ").split()
    if not parts:
        return None
    head = Path(parts[0]).name
    if head in _LAUNCHERS or head.startswith("python"):
        if len(parts) >= 3 and parts[1] == "-m":
            return [parts[0], "-c", f"import {parts[2].split('.')[0]}"]
        return [parts[0], "--version"]
    if head in _LOCAL_RUNNERS:
        return None
    return ["sh", "-c", f"command -v {parts[0]}"]


@dataclass
class ToolCheck:
    key: str
    command: str
    ok: bool | None            # True present · False MISSING · None UNJUDGED (no probe can be built — SS-47)
    where: str
    detail: str = ""
    probe: list[str] = field(default_factory=list)

    @property
    def line(self) -> str:
        state = "present" if self.ok else ("UNJUDGED" if self.ok is None else "MISSING")
        return f"`{self.key}` = `{self.command}` — {state} in {self.where}" + (
            f": {self.detail}" if self.detail and not self.ok else "")


def check_tools(project: Path | str, cfg, *, build: bool = True, log=None) -> list[ToolCheck]:
    """Probe every declared tool where the harness will run it.

    Docker provider → inside the configured image (built first when it is a
    managed recipe); otherwise → on this host. A tool the probe cannot judge
    (project-local runner) is reported as present with a note, never as
    missing: the check must not invent a failure it did not measure.
    """
    from . import sandbox as _sb
    from .tools import image_for

    project = Path(project)
    image = image_for(project, cfg)
    spec = _sb.SandboxSpec(workspace=project, cmd=["true"], image=image,
                           use_docker=bool(cfg.get("sandbox.use_docker", True)),
                           provider=str(cfg.get("sandbox.provider", "") or ""))
    try:
        provider, _missing = _sb.select_provider(spec)
        in_sandbox = provider.id != "local"
        err = ensure(image, build=build, log=log) if provider.id == "docker" else ""
    except Exception:  # noqa: BLE001 — no provider at all: judge on the host
        in_sandbox, err = False, ""
    where = image if in_sandbox else "this host"
    out: list[ToolCheck] = []
    for key, command in declared_tools(cfg, project):
        probe = probe_command(command)
        if probe is None:
            # SS-47 / INV-N.1: a tool the probe cannot judge is UNJUDGED — stated, never reported present
            out.append(ToolCheck(key, command, None, where,
                                 "project-local runner: unmeasured here; the story's first tool run is the proof"))
            continue
        if err:
            out.append(ToolCheck(key, command, False, where, err, probe))
            continue
        if in_sandbox:
            res = _sb.run(_sb.SandboxSpec(
                workspace=project, cmd=probe, image=image, level=_sb.Level.READ_ONLY,
                timeout_seconds=120, use_docker=spec.use_docker, provider=spec.provider))
            ok = res.ok
            detail = ""
            if not ok:
                tail = (res.stderr or res.stdout).strip().splitlines()
                detail = res.provider_error or (tail[-1] if tail else f"exit {res.exit_code}")
        else:
            ok, detail = _probe_host(probe)
        out.append(ToolCheck(key, command, ok, where, str(detail)[:200], probe))
    return out


def _probe_host(probe: list[str]) -> tuple[bool, str]:
    if probe[0] == "sh":
        name = probe[-1].split()[-1]
        return (shutil.which(name) is not None), ("" if shutil.which(name) else f"{name} is not on PATH")
    exe = shutil.which(probe[0]) or (sys.executable if Path(probe[0]).name.startswith("python") else "")
    if not exe:
        return False, f"{probe[0]} is not on PATH"
    try:
        p = subprocess.run([exe, *probe[1:]], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    tail = (p.stderr or p.stdout).strip().splitlines()
    return p.returncode == 0, ("" if p.returncode == 0 else (tail[-1] if tail else f"exit {p.returncode}"))
