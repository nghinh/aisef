"""Phase 17 — the replay contract (INV-S.1).

A run declares the conditions it started under — framework, client and its version, model, route, the digests of
the configuration, the requirements and every story contract, the environment, the sandbox images — in a
`ReplayManifest` written at the start of EVERY `aisef run` (`_bmad-output/replay/<run_id>.json`). A replay
(`aisef run --replay-of <run_id|manifest.json>`) compares its own manifest with the source's BEFORE the first agent
invocation: a material difference stops the run with a typed REPLAY_CONDITION_DRIFT record unless the owner names
each differing field in `--accept-drift`; an immaterial one (framework patch, host name) is recorded, never blocking.
The Claude-vs-OpenCode replay of 2026-09 ran to completion before anyone noticed the client had changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

REPLAY_DIR = "replay"
DRIFT_RECORD = "REPLAY_CONDITION_DRIFT"
#: a difference here changes what a verdict means: STOP unless the owner accepts the field by name
MATERIAL = ("client", "client_version", "model", "route", "config_digest", "requirements_digest",
            "story_contract_digests", "environment_digest", "sandbox_digests", "baseline_identities")
#: recorded, never blocking; a framework PATCH bump is immaterial too (a minor or major one changes the rules: material)
IMMATERIAL = ("host",)
COMPARED = MATERIAL + ("framework_version",) + IMMATERIAL


@dataclass(frozen=True)
class ReplayManifest:
    framework_version: str = ""
    client: str = ""
    client_version: str = ""
    model: str = ""
    route: str = ""
    config_digest: str = ""
    requirements_digest: str = ""
    story_contract_digests: dict = field(default_factory=dict)
    environment_digest: str = ""
    sandbox_digests: dict = field(default_factory=dict)
    baseline_identities: dict = field(default_factory=dict)
    source_run: str = ""
    host: str = ""
    accepted_drift: tuple = ()

    def as_dict(self) -> dict:
        d = asdict(self)
        d["accepted_drift"] = list(self.accepted_drift)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ReplayManifest":
        known = {f.name for f in fields(cls)}
        kw = {k: v for k, v in (d or {}).items() if k in known}
        kw["accepted_drift"] = tuple(kw.get("accepted_drift") or ())
        return cls(**kw)


@dataclass
class Drift:
    fields: dict = field(default_factory=dict)      # every differing field → {"source": …, "requested": …}
    material: dict = field(default_factory=dict)    # the differing MATERIAL fields the owner did not accept
    immaterial: dict = field(default_factory=dict)  # recorded, never blocking (incl. accepted material fields)
    accepted: tuple = ()

    @property
    def stop(self) -> bool:
        return bool(self.material)

    def summary(self) -> str:
        if not self.fields:
            return "no drift"
        parts = [f"{k}: {_short(v['source'])} → {_short(v['requested'])}" for k, v in self.fields.items()]
        return ("STOP — " if self.stop else "recorded — ") + "; ".join(parts)


def _short(v) -> str:
    s = json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else str(v)
    return s if len(s) <= 40 else s[:37] + "…"


def _major(version: str) -> str:
    return version.split(".")[0].strip() if version else ""


def _major_minor(version: str) -> str:
    return ".".join(version.split(".")[:2]).strip() if version else ""


def preflight(requested: ReplayManifest, source: ReplayManifest, *, accept: tuple[str, ...] = ()) -> Drift:
    """Field by field. A field the SOURCE did not record (empty) is not compared — nothing was declared. A client
    version differs materially on its major; a framework version on its major.minor (a patch is immaterial)."""
    drift = Drift(accepted=tuple(accept))
    for name in COMPARED:
        src, req = getattr(source, name), getattr(requested, name)
        if not src or src == req:
            continue
        if name == "client_version" and _major(src) == _major(req):
            continue
        if name == "framework_version" and _major_minor(src) == _major_minor(req):
            drift.immaterial[name] = {"source": src, "requested": req}
            drift.fields[name] = drift.immaterial[name]
            continue
        entry = {"source": src, "requested": req}
        drift.fields[name] = entry
        if name in IMMATERIAL or name in accept:
            drift.immaterial[name] = entry
        else:
            drift.material[name] = entry
    return drift


# ------------------------------------------------------------------ capture

def framework_version() -> str:
    try:
        from importlib.metadata import version
        return version("aisef")
    except Exception:  # noqa: BLE001 — not installed: read the checkout's pyproject
        try:
            for line in (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8").splitlines():
                if line.startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return "0"


def client_version(client) -> str:
    """`<binary> --version`, first line, for a REAL adapter (one that names its binary); "" for a synthetic or fake
    client — the probe is never inferred from a display name."""
    binary = getattr(client, "binary", None)
    binary = shutil.which(str(binary)) if binary else None
    if not binary:
        return ""
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    text = (out.stdout or out.stderr or "").strip().splitlines()
    return text[0].strip()[:80] if text else ""


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _route() -> str:
    from urllib.parse import urlparse
    for key in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "OPENCODE_BASE_URL"):
        v = os.environ.get(key) or ""
        if v:
            return urlparse(v if "://" in v else f"http://{v}").hostname or v
    return ""


def new_run_id() -> str:
    return time.strftime("run-%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{os.getpid()}"


def capture(project: Path | str, artifact_root: Path | str, config, client, *, run_id: str = "") -> ReplayManifest:
    """The conditions THIS run starts under, written to `<artifact_root>/replay/<run_id>.json`. Cheap: digests of
    files already read; the sandbox image id only when an image is declared."""
    from .acceptance import contract_fingerprint
    from .identity import environment_digest
    project, art = Path(project), Path(artifact_root)
    contracts: dict[str, str] = {}
    try:
        from ..phases.run import load_plan
        for sid, story in load_plan(art).stories.items():
            contracts[sid] = contract_fingerprint(story.acceptance_criteria)
    except Exception:  # noqa: BLE001 — no plan yet: nothing declared, nothing compared
        pass
    sandbox: dict[str, str] = {}
    image = str((getattr(config, "get", lambda k, d="": d)("sandbox.image", "") if config is not None else "") or "")
    if image:
        try:
            from ..harness import verify_image
            sandbox[image] = str(verify_image.image_id(image) or "")
        except Exception:  # noqa: BLE001 — no docker here: the name is declared, the digest unknown
            sandbox[image] = ""
    name = str(getattr(client, "name", "") or type(client).__name__)
    m = ReplayManifest(
        framework_version=framework_version(), client=name, client_version=client_version(client),
        model=str(getattr(client, "model", "") or ""), route=_route(),
        config_digest=_sha256_file(project / ".ai" / "config.json"),
        requirements_digest=_sha256_file(project / "docs" / "requirements.md"),
        story_contract_digests=contracts, environment_digest=environment_digest(config), sandbox_digests=sandbox,
        baseline_identities={}, source_run=run_id or new_run_id(), host=socket.gethostname())
    out = art / REPLAY_DIR / f"{m.source_run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m.as_dict(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return m


def load(artifact_root: Path | str, ref: str) -> ReplayManifest | None:
    """`ref` is a run id (`replay/<id>.json` under the artifact root) or a path to a manifest file."""
    path = Path(ref)
    if not path.is_file():
        path = Path(artifact_root) / REPLAY_DIR / f"{ref}.json"
    try:
        return ReplayManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def record(artifact_root: Path | str, drift: Drift, requested: ReplayManifest, source: ReplayManifest) -> Path:
    """The typed record of the comparison — written whether or not the run stops."""
    out = Path(artifact_root) / REPLAY_DIR / f"{requested.source_run}.drift.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "record": DRIFT_RECORD if drift.stop else "REPLAY_CONDITIONS_MATCH",
        "source_run": source.source_run, "requested_run": requested.source_run,
        "fields": drift.fields, "material": drift.material, "immaterial": drift.immaterial,
        "accepted": list(drift.accepted), "stop": drift.stop, "at": time.time(),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out
