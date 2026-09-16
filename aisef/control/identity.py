"""Evidence identity — the one answer to "does this record speak for the state I am deciding on".

A verdict is not a property of a commit SHA. It was computed over a tree (the SHA **plus** whatever was
dirty around it), for a story contract (epoch), against a baseline, with a verifier configuration, in an
environment, by one session. Any of those changing makes the verdict a historical fact, not a decision
input. Before this module every subsystem asked its own question — "any verdict at this SHA?",
"latest test run?", "a guard trace anywhere in the story?" — and D-035, SS-02/03, SS-61 are what those
questions cost. Here there is one tuple and one function, `fresh()`; nothing else may decide freshness.

Schema: records written by ≤ 1.7.6 carry only `detail.candidate` (schema 1). They are migrated on read
to an identity with `schema_version = 1` and nothing but the candidate — deterministic, provenance kept,
and **never fresh** against a decider that binds on the fields they lack (Phase 16: old evidence does not
silently satisfy a new gate; it is stated and re-verified).
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path

SCHEMA_VERSION = 2

#: what a stage verdict (test, lint, review, security, gate, qa:*) binds on
CONTROL_FIELDS = ("story_id", "story_epoch", "candidate_sha", "tree_state_digest",
                  "verifier_config_digest", "environment_digest", "baseline_root")
#: what a session proof (guard heartbeat, guard block, file change, agent_run) binds on
SESSION_FIELDS = ("story_id", "session_id")
#: config keys whose change changes what a verdict means
VERIFIER_KEY_PREFIXES = ("tools.", "verify.", "coverage.", "security.", "review.")

#: notes that carry a candidate SHA without being a grading of it — never the candidate of record
NON_CANDIDATE_NOTES = ("retry:recovery", "evidence:invalidated")
INVALIDATED = "evidence:invalidated"


@dataclass(frozen=True)
class EvidenceIdentity:
    story_id: str = ""
    story_epoch: str = ""
    candidate_sha: str = ""
    baseline_root: str = ""
    tree_state_digest: str = ""
    verifier_config_digest: str = ""
    environment_digest: str = ""
    run_id: str = ""
    session_id: str = ""
    attempt: int = 0
    stage: str = ""
    schema_version: int = SCHEMA_VERSION

    def as_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if v not in ("", 0)}
        d["schema_version"] = self.schema_version
        return d

    @classmethod
    def from_dict(cls, d: dict | None) -> "EvidenceIdentity":
        d = dict(d or {})
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        if "attempt" in known:
            try:
                known["attempt"] = int(known["attempt"])
            except (TypeError, ValueError):
                known["attempt"] = 0
        return cls(**known)

    @classmethod
    def of(cls, event, story_id: str = "") -> "EvidenceIdentity":
        """The identity a record carries — migrated from schema 1 (`detail.candidate` only) when it has none.
        A schema-1 record lives in its story's own evidence file, so the story id is known (`story_id`);
        every other field is genuinely unknown and stays empty (Phase 16: migrated, never invented)."""
        ident = getattr(event, "identity", None) or {}
        if ident:
            return cls.from_dict(ident)
        cand = str((getattr(event, "detail", None) or {}).get("candidate") or "")
        return cls(story_id=story_id, candidate_sha=cand, schema_version=1)

    def with_(self, **changes) -> "EvidenceIdentity":
        return replace(self, **changes)

    @property
    def bound(self) -> bool:
        """Carries at least one binding field (a record with none is an unbound observation)."""
        return bool(self.candidate_sha or self.session_id)


@dataclass(frozen=True)
class Freshness:
    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


def _short(v) -> str:
    s = str(v)
    return s[:8] if len(s) > 12 else s


def fresh(event, current: EvidenceIdentity, fields: tuple[str, ...] = CONTROL_FIELDS,
          story_id: str = "") -> Freshness:
    """Does `event` speak for `current`? Every field the decider binds on (non-empty in `current`) must
    be present and equal on the record. A record lacking a field the decider binds on is a schema-1
    (or foreign) record: stated, never scored. `story_id` is the evidence file's story, the one field a
    schema-1 record is known to have."""
    rec = EvidenceIdentity.of(event, story_id or current.story_id)
    if not rec.bound:
        return Freshness(False, "unbound: the record names no candidate and no session")
    for f in fields:
        want = getattr(current, f)
        if not want:
            continue
        have = getattr(rec, f)
        if have != want:
            if not have:
                return Freshness(False, f"{f}: record lacks it (schema {rec.schema_version}) — legacy or foreign evidence, re-verify")
            return Freshness(False, f"{f}: {_short(have)} ≠ {_short(want)}")
    return Freshness(True)


def explain_stale(event, current: EvidenceIdentity, fields: tuple[str, ...] = CONTROL_FIELDS) -> str:
    return fresh(event, current, fields).reason


# ------------------------------------------------------------ digests

def _sha(parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8", "replace"))
        h.update(b"\0")
    return h.hexdigest()[:16]


#: paths whose presence or change is not the developer's tree state: the harness's own records, the client's
#: generated configuration, tool caches — they change on every step and belong to nobody's candidate
HARNESS_PATH_PREFIXES = ("_bmad-output/", ".aisef/", ".claude/", ".opencode/", ".pytest_cache/", "node_modules/",
                         ".venv/", "venv/", ".mypy_cache/", ".ruff_cache/", ".git/")
HARNESS_PATH_PARTS = ("__pycache__/",)
HARNESS_PATH_SUFFIXES = (".pyc", ".coverage", "/.coverage", ".coverage.xml", "coverage.xml", ".DS_Store")


def is_harness_path(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return (rel.startswith(HARNESS_PATH_PREFIXES) or any(part in rel for part in HARNESS_PATH_PARTS)
            or rel.endswith(HARNESS_PATH_SUFFIXES) or rel in ("_bmad-output", ".aisef", ".claude", ".opencode"))


def tree_state_digest(workdir: Path | str) -> str:
    """Digest of the working tree's deviation from HEAD: paths, statuses and content ids of every
    modified or untracked (non-ignored) file the developer could have touched. `clean` when there is none.
    Harness records, client configuration and tool caches are not tree state (`is_harness_path`). A verdict
    computed over a dirty tree is a verdict over THIS digest; hygiene that restores the tree changes it (D-035)."""
    try:
        out = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=workdir,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return "unreadable"
    if out.returncode != 0:
        return "unreadable"
    entries = [x for x in out.stdout.split("\0") if x]
    parts = []
    i = 0
    while i < len(entries):
        line = entries[i]
        status, rel = line[:2], line[3:]
        if status.startswith("R") or status.startswith("C"):
            i += 1            # renames carry the source path as the next entry
        i += 1
        if is_harness_path(rel):
            continue
        p = Path(workdir) / rel
        content = ""
        if p.is_file():
            try:
                content = hashlib.sha1(p.read_bytes()).hexdigest()[:16]
            except OSError:
                content = "unreadable"
        parts.append(f"{status} {rel} {content}")
    return _sha(sorted(parts)) if parts else "clean"


def verifier_config_digest(config) -> str:
    """Digest of the configuration that shapes a verdict (tools.*, verify.*, coverage.*, security.*, review.*)."""
    if config is None:
        return ""
    values = getattr(config, "values", None)
    if not isinstance(values, dict):
        return ""
    picked = {k: values[k] for k in sorted(values) if k.startswith(VERIFIER_KEY_PREFIXES)}
    return _sha([json.dumps(picked, sort_keys=True, default=str)])


def environment_digest(config) -> str:
    """Digest of the environment a verdict was computed in: OS, interpreter, sandbox image."""
    image = ""
    values = getattr(config, "values", None)
    if isinstance(values, dict):
        image = str(values.get("sandbox.image") or "")
    return _sha([os.name, f"{sys.version_info[0]}.{sys.version_info[1]}", image])


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


#: The identity of the attempt currently being verified in this thread. Every evidence store created while
#: it is set stamps its records with it (the tool, baseline, nop, review and security helpers build their
#: own stores with a bare candidate); set by `verify_candidate`, reset when it returns.
CURRENT: contextvars.ContextVar["EvidenceIdentity | None"] = contextvars.ContextVar("aisef_evidence_identity", default=None)


def current(*, story_id: str, story_epoch: str = "", candidate_sha: str = "", baseline_root: str = "",
            workdir: Path | str | None = None, config=None, run_id: str = "", session_id: str = "",
            attempt: int = 0, stage: str = "") -> EvidenceIdentity:
    """The identity of the state being decided on, computed once per decision point."""
    return EvidenceIdentity(
        story_id=story_id, story_epoch=story_epoch, candidate_sha=candidate_sha, baseline_root=baseline_root,
        tree_state_digest=tree_state_digest(workdir) if workdir is not None else "",
        verifier_config_digest=verifier_config_digest(config), environment_digest=environment_digest(config),
        run_id=run_id, session_id=session_id, attempt=attempt, stage=stage)
