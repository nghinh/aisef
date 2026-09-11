"""Lock the framework candidate + effective config hash + arm-toggle signature.

The lock file pins four invariants of the harness run:

1. ``candidate_sha`` — `git rev-parse HEAD` at the time the lock was authored.
   Subsequent harness runs verify that HEAD has not moved; if it has, the
   harness refuses to run unless ``AISEF_MEMORY_BENCH_FORCE=1`` is set.
   Memory is benchmark of *this* framework candidate, not HEAD.

2. ``effective_config_snapshot`` — names of relevant config keys with their
   default values, plus a deterministic JSON digest. Any drift in the keys
   listed here (rename, default flip, range change) shifts the hash and tells
   reviewers that the prior results are no longer comparable.

3. ``toggle_signature`` — per-arm deterministic signature derived from the
   exact value of `AISEF_MEMORY_ARMS` (default ``A,B,C``) and from the union
   of provider/toggle names. A runs that flip one arm are not re-runnable
   against the prior results without a new run.

4. ``signature`` — the deterministic aggregated signature
   (candidate_sha, config_hash, toggle_signature, lockfile schema version).
   Embedded in every per-arm result file so reviewers can compare runs.

The lock file itself is committed alongside the harness. It is the *single*
authoritative source of what counts as the same framework candidate.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

LOCK_SCHEMA_VERSION = 1
LOCK_PATH = Path(__file__).resolve().parent / "lock.json"
DEFAULT_ARMS = ("A", "B", "C")
_VALID_TOGGLE = re.compile(r"^[A-Z]([,_-][A-Z])*$")


def _candidate_sha(repo_root: Path) -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo_root),
        capture_output=True, text=True, check=True,
    )
    sha = out.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        raise RuntimeError("candidate_sha: unexpected format from git rev-parse")
    return sha


def _config_keys() -> tuple[tuple[str, object], ...]:
    """Subset of `aisef.config.Config` keys that affect memory behavior.

    Changes to any default here shift the hash and void prior run comparisons.
    The values here are *defaults derived from Config.empty() after load*,
    re-captured at lock-authoring time. The actual values recorded come from
    a short static snapshot below to avoid exercising the whole Config class
    at lock load (which has its own validation and filesystem assumptions).
    """
    return (
        ("memory.enabled", False),
        ("memory.provider", "local"),
        ("memory.fallback", "none"),
        ("memory.timeout_seconds", 2),
        ("memory.max_chars", 1200),
        ("memory.capture", False),
        ("memory.toggle_arms", list(DEFAULT_ARMS)),
    )


def _config_hash(keys: Iterable[tuple[str, object]]) -> str:
    payload = json.dumps([list(item) for item in keys], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _toggle_signature(arms: Iterable[str], provider: str = "local") -> str:
    arm_list = tuple(a.strip() for a in arms if a.strip())
    if not arm_list or not _VALID_TOGGLE.match(",".join(arm_list)):
        raise ValueError(f"invalid toggle signature: {list(arms)!r}")
    payload = {"arms": list(arm_list), "provider": provider, "schema": LOCK_SCHEMA_VERSION}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


@dataclass(frozen=True)
class LockSnapshot:
    candidate_sha: str
    effective_config_snapshot: tuple[tuple[str, object], ...]
    toggle_signature: str
    signature: str
    schema_version: int

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": self.schema_version,
            "candidate_sha": self.candidate_sha,
            "effective_config_snapshot": [list(item) for item in self.effective_config_snapshot],
            "config_hash": _config_hash(self.effective_config_snapshot),
            "toggle_signature": self.toggle_signature,
            "signature": self.signature,
            "default_arms": list(DEFAULT_ARMS),
        }, sort_keys=True, indent=2) + "\n"


def _aggregate_signature(candidate_sha: str, config_hash: str, toggle_sig: str) -> str:
    payload = json.dumps(
        {"candidate_sha": candidate_sha, "config_hash": config_hash,
         "toggle_signature": toggle_sig, "schema_version": LOCK_SCHEMA_VERSION},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def lock_signature(repo_root: Path, *, arms: Iterable[str] = DEFAULT_ARMS,
                   provider: str = "local",
                   config_keys: Iterable[tuple[str, object]] | None = None) -> LockSnapshot:
    cfg = tuple(config_keys) if config_keys is not None else _config_keys()
    candidate = _candidate_sha(repo_root)
    cfg_hash = _config_hash(cfg)
    tog_sig = _toggle_signature(arms, provider=provider)
    signature = _aggregate_signature(candidate, cfg_hash, tog_sig)
    return LockSnapshot(
        candidate_sha=candidate,
        effective_config_snapshot=cfg,
        toggle_signature=tog_sig,
        signature=signature,
        schema_version=LOCK_SCHEMA_VERSION,
    )


class LockMismatch(RuntimeError):
    """Refusal to run because the lock and the working tree disagree."""


def _read_lock(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict) or "schema_version" not in data:
        raise RuntimeError(f"lock file malformed: {path}")
    return data


def verify_lock(repo_root: Path, lock_path: Path = LOCK_PATH,
                arms: Iterable[str] | None = None,
                provider: str = "local") -> LockSnapshot:
    """Refuse to run if HEAD moved since the lock was authored.

    The arms/provider arguments are accepted so the caller can confirm that
    the *run-time* toggle signature matches the lock. If they differ, that is
    not automatically a refusal (the harness tolerates a subset) but the
    result file will record the difference.
    """
    if not lock_path.is_file():
        raise LockMismatch(f"missing lock file: {lock_path}")
    data = _read_lock(lock_path)
    actual_candidate = _candidate_sha(repo_root)
    expected_candidate = data.get("candidate_sha", "")
    if expected_candidate != actual_candidate and not os.environ.get("AISEF_MEMORY_BENCH_FORCE"):
        raise LockMismatch(
            f"candidate SHA drift: lock says {expected_candidate[:12]} but HEAD is "
            f"{actual_candidate[:12]}. Refusing to run; set AISEF_MEMORY_BENCH_FORCE=1 "
            f"to override."
        )
    expected_sig = data.get("signature", "")
    arms_list = tuple(arms) if arms is not None else tuple(data.get("default_arms", DEFAULT_ARMS))
    expected_toggle = data.get("toggle_signature", "")
    expected_provider = data.get("effective_config_snapshot", [])
    provider_value = next((v for k, v in expected_provider if k == "memory.provider"), provider)
    actual_toggle = _toggle_signature(arms_list, provider=str(provider_value))
    if actual_toggle != expected_toggle and not os.environ.get("AISEF_MEMORY_BENCH_FORCE"):
        raise LockMismatch(
            f"toggle signature drift: lock says {expected_toggle} but the configured "
            f"arms {list(arms_list)} yield {actual_toggle}."
        )
    return LockSnapshot(
        candidate_sha=expected_candidate,
        effective_config_snapshot=tuple(tuple(item) for item in data.get("effective_config_snapshot", [])),
        toggle_signature=expected_toggle,
        signature=expected_sig,
        schema_version=int(data.get("schema_version", LOCK_SCHEMA_VERSION)),
    )


# Module-level constants; populated when the lock file is read on import.
# Authoring of the lock file happens once (`framework/bench/memory_compare/lock.json`
# is committed). Tests that need to regenerate the lock use
# `framework/bench/memory_compare/__main__.py --write-lock`.
def _bootstrap_constants() -> tuple[str, str, dict, str, str]:
    if not LOCK_PATH.is_file():
        return ("", "", {}, "", "")
    data = _read_lock(LOCK_PATH)
    return (
        data.get("candidate_sha", ""),
        data.get("config_hash", _config_hash(_config_keys())),
        data.get("effective_config_snapshot", {}),
        data.get("toggle_signature", ""),
        data.get("signature", ""),
    )


_CANDIDATE, _CFG_HASH, _CFG_SNAPSHOT, _TOG, _SIG = _bootstrap_constants()
CANDIDATE_SHA: str = _CANDIDATE
CONFIG_HASH: str = _CFG_HASH
EFFECTIVE_CONFIG_SNAPSHOT: Mapping[str, object] = dict(_CFG_SNAPSHOT) if isinstance(_CFG_SNAPSHOT, dict) else {}
TOGGLE_SIGNATURE: str = _TOG
SIGNATURE: str = _SIG
