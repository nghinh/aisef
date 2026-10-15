"""PM-8 (PROBE-DIAGNOSTIC-GAP-001) — what a probe saw, kept for the operator and for no decision.

`probe.protocol.classify_failure` turns an `Observation` into a `ProbeResult`, and a REFUTED, absent or expired-window
observation leaves its `detail` behind: the sealed record, the journal and every prompt say `{behavior_verdict:
REFUTED}` and no more. The step, the file and line, the exception class that made the verdict live in the
`Observation` only. This module keeps them — for each probe evaluation whose verdict is not the one its contract
expects — in a file of its own under the run directory. It changes no probe, no kernel module, no `ProbeResult` or `ProbeRecord`, no digest, no
calibration, no journal format and not one byte of what a developer is told.

    <out>/probe-observations/<story>.<attempt>.p<n>.json   a proof's: the kernel's own evaluation of a story's
                                                           obligation (its admission at the parent, its proof at the
                                                           candidate, its re-proof after the merge); `n` counts them
    <out>/probe-observations/<story>.<attempt>.r<n>.json   a review reproducer's: the finding at place `n` of the
                                                           finder's list (app/review_verify.verify)

**How.** `tapped` gives a probe class a subclass that overrides `observe()` and nothing else: it returns the very
`Observation` the probe made, after `Sink.note` has looked at it. The subclass has the probe's id, digest and execution
digest (class attributes it inherits), so the plan's specs, the calibration lookup and the sealed record are exactly
the untapped probe's; `run.runspec_of` still binds the catalog's own classes. `Sink.note` never raises an `Exception`
and returns nothing: an artifact that cannot be written is counted and named in RUN.json (`diagnostics.not_written`),
and the verdict, the retry and the budget are what they would have been.

**What is kept.** Only an evaluation the probe executed (an unrunnable or invalid-spec result's `detail` is in the
journal's own record) whose verdict is not the one the contract expects (`candidate_expectation`: the comparison
the frozen `contract_satisfaction` makes, used here to decide whether there is something to explain, never to route;
this module neither calls that function nor seals a record), and not the expected state of what the story
introduces, at its parent: the verdict the kernel recorded and the verdict expected, beside the observation (its
kind, its verdict, its detail — parsed when the probe made JSON of it), and the identity of the sealed record the
journal's `probe/evaluated` row holds (story, spec, probe and its digest, revision, enforcement, result), so
`aisef run --verify` binds the file to that row — and the criteria the spec answers. Every string in it
has the run's secrets replaced (`review_verify.redacted`, the mechanism of the review artifacts); the detail is cut at
`DETAIL_MAX` characters (`elided` says how many it left out, `detail_chars` its length) and a run writes at most
`FILES_MAX` files (`diagnostics.dropped`).

**Who reads it.** The operator — and, today, not enforcement. The directory is made 0700 and its files 0600 where the
platform has modes, which binds other users and never the operator's own; it is outside every checkout a developer
works in. Whether the *model sessions* are kept from it is decided by what the sandbox mounts (`access_of`, from the
bubblewrap command line a session gets): without confinement every process of the operator's user — the developer's
session included — can read it, and RUN.json and each artifact say `same-user, not enforced`. With confinement the
sessions do not mount it, and the statement stays that the developer's tests and the candidate a probe runs are
executed by the kernel as the operator's user and are not confined. Nothing here claims the developer is kept from it.

**What it decides: nothing.** No code in aisef2 reads this directory but `artifact_problems`, which `aisef run
--verify` calls to check the files against the journal as it checks every evidence file (a changed or unbound one makes
the *verification* REFUTED, never the delivery verdict, which the journal alone gives). The module imports no deciding
module (control, orchestrate, journal, plan), the `Sink` has no read method, and `feedback.py`, `client.py` and the
developer's prompt builders do not name it (tests/v2/test_v21_pm8_diagnostics.py)."""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import sys
from typing import Callable, Mapping

from aisef2.app import confine, review_verify
from aisef2.probe import catalog
from aisef2.probe.protocol import classify_failure
from aisef2.product.contract import plain
from aisef2.product.outcome import Executed

ARTIFACT_DIR = "probe-observations"
ARTIFACT_FORMAT = "aisef-v2-probe-observation/1"
#: the characters of an observation's detail one artifact keeps, and the artifacts one run writes: deliberate bounds
DETAIL_MAX = 8192
FILES_MAX = 500
#: what RUN.json names of the artifacts that could not be written (the count is whole)
FAILURES_MAX = 20
#: who can read the directory, as a closed vocabulary: what is enforced and what is not
SAME_USER = "same-user, not enforced"
#: confinement is asked for and what its sessions mount could not be inspected (not a Linux host, bubblewrap or a
#: read-only path not there): nothing is claimed of the sessions, and this is as little as SAME_USER says
NOT_INSPECTED = SAME_USER + " (confinement is asked for; what its sessions mount could not be inspected)"
SESSIONS_CONFINED = ("model sessions confined, the directory is not mounted in them; same-user, not enforced for the "
                     "developer's tests and the candidate under a probe, which the kernel runs as the operator's user")
PERMISSIONS = "directory 0700, files 0600" if os.name == "posix" else "platform default (modes are not applied)"
AUTHORITY = "none: no verdict, retry, budget, merge or route reads these files"
_NAME = re.compile(r"[A-Za-z0-9_-]{1,49}\.\d{1,6}\.[pr]\d{1,6}\.json")


def access_of(folder, confinement, env: Mapping, exe: str | None, system: str = sys.platform) -> str:
    """Who of the run's own model sessions can read `folder` (never more than the sandbox's command line says):
    `SAME_USER` without confinement, or when a directory a session mounts is `folder` or holds it (an operator's
    `read_only` path above the run directory); `NOT_INSPECTED` when confinement is asked for and its command line could
    not be built or read here; else `SESSIONS_CONFINED`. The command line is the one `confine.wrap` builds for a
    session — the workspace is one of the run's, `<out>/work/ws`."""
    if confinement is None:
        return SAME_USER
    try:
        full, _ = confine.wrap(confinement, ["true"], dict(env), str(pathlib.Path(folder).parent / "work" / "ws"), exe,
                               system=system)
        here = os.path.realpath(folder)
        for mounted in confine.targets(full, host=True):
            root = os.path.realpath(mounted)
            if here == root or here.startswith(root.rstrip(os.sep) + os.sep):
                return SAME_USER
    except Exception:  # noqa: BLE001 — what cannot be shown is not claimed: the statement is the weaker one
        return NOT_INSPECTED
    return SESSIONS_CONFINED


def _parsed(detail: str):
    """A probe's detail as JSON data when it is an object or a list, else the text (secrets are replaced after)."""
    try:
        value = json.loads(detail)
    except (ValueError, RecursionError):
        return detail
    return value if isinstance(value, (dict, list)) else detail


class Sink:
    """The artifacts of one run. It only writes: it has no method that reads a file back, and `report()` is what
    RUN.json says of it."""

    def __init__(self, out, secrets=(), access: str = SAME_USER, files_max: int = FILES_MAX) -> None:
        self.folder = pathlib.Path(out) / ARTIFACT_DIR
        self.secrets, self.access, self.files_max = tuple(secrets), access, files_max
        self.written = self.dropped = self.not_written = 0
        self.failures: list[dict] = []
        self._counted: dict[tuple, int] = {}

    def note(self, where, spec, at, probe, observation) -> None:
        """Keep what `probe` saw (`observation`, made at `at` for `spec`) when it is a finding (module docstring).
        `where` is a mapping — or a callable giving one, read now — naming the story, the attempt and the origin. Never
        raises an `Exception`: a diagnostic that cannot be kept is counted and named, and nothing else changes."""
        ctx: Mapping = {}
        try:
            ctx = where() if callable(where) else where
            made = self._document(ctx, spec, at, probe, observation)
            if made is not None:
                self._keep(*made)
        except Exception as e:  # noqa: BLE001 — fail open: a diagnostic's fault is a mark in RUN.json, never a verdict
            self.not_written += 1
            if len(self.failures) < FAILURES_MAX:
                self.failures.append({"story_id": str(ctx.get("story_id")) if isinstance(ctx, Mapping) else None,
                                      "spec_id": str(getattr(spec, "id", None)),
                                      "why": f"{type(e).__name__}: {e}"[:200]})

    def _document(self, ctx: Mapping, spec, at, probe, observation) -> tuple[str, dict] | None:
        result = classify_failure(spec, observation)
        if not isinstance(result, Executed):      # unrunnable, invalid spec: the journal's record holds its detail
            return None
        if result.behavior_verdict is spec.candidate_expectation:      # what the contract expects: nothing to explain
            return None
        proof = ctx["origin"] == "proof"
        at_parent = proof and at.sha == ctx.get("parent")
        if at_parent and spec.id in ctx.get("introduces", ()):
            return None      # what the story introduces is not there yet at its parent: the expected state, no finding
        story, attempt = ctx["story_id"], ctx["attempt"]
        if proof:
            key = (story, attempt)
            index = self._counted[key] = self._counted.get(key, 0) + 1
        else:
            index = ctx["index"]
        doc = {"format": ARTIFACT_FORMAT, "origin": ctx["origin"], "story_id": story, "attempt": attempt, "index": index,
               "spec_id": spec.id, "probe_id": probe.id, "probe_digest": probe.digest, "revision": at.sha,
               "enforcement": probe.enforcement().value, "expected": spec.candidate_expectation.value,
               "result": plain(result),
               "observation": {"kind": observation.kind.value,
                               "verdict": observation.verdict.value if observation.verdict is not None else None,
                               "detail": _parsed(observation.detail)},
               "audience": "operator", "diagnostics_access": self.access,
               **({"at_parent": at_parent, "criteria": list(ctx.get("criteria", {}).get(spec.id, ()))} if proof
                  else {"finding": ctx.get("finding")})}
        body, count = review_verify.redacted(doc, self.secrets)     # keys, values, the finder's own id: all of it
        shown = body["observation"]
        text = shown["detail"] if isinstance(shown["detail"], str) else json.dumps(shown["detail"], sort_keys=True,
                                                                                    ensure_ascii=False)
        shown["detail_chars"], shown["elided"] = len(text), max(0, len(text) - DETAIL_MAX)
        if shown["elided"]:
            shown["detail"] = text[:DETAIL_MAX]
        body["redacted"] = count
        return f"{review_verify.artifact_stem(story)}.{attempt}.{'p' if proof else 'r'}{index}.json", body

    def _keep(self, name: str, doc: dict) -> None:
        """Create-only, written whole to a sibling and renamed over, private to the operator's user where the platform
        has modes. Nothing is removed (INV-MUTATION-AUTHORITY): a sibling a failed write leaves stays, unlisted."""
        if self.written >= self.files_max:
            self.dropped += 1
            return
        data = (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("ascii")
        self.folder.mkdir(mode=0o700, exist_ok=True)
        if os.name == "posix":
            os.chmod(self.folder, 0o700)
        final, sibling = self.folder / name, self.folder / f"{name}.tmp"
        if final.exists():
            raise FileExistsError(f"{name} exists: an artifact is never overwritten")
        with os.fdopen(os.open(sibling, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(sibling, final)
        self.written += 1

    def entries(self, where) -> dict:
        """The catalog's active entries (subject kind -> entry), each with its probe tapped (`review_verify.verify`)."""
        return {kind: dataclasses.replace(e, factory=tapped(e.factory, self, where))
                for kind, e in catalog.active().items()}

    def report(self) -> dict:
        """RUN.json's `diagnostics`: where, for whom and by what means, and how many files — or how many could not be."""
        return {"dir": ARTIFACT_DIR, "audience": "operator", "access": self.access, "permissions": PERMISSIONS,
                "authority": AUTHORITY, "written": self.written, "not_written": self.not_written,
                "failures": list(self.failures), "dropped": self.dropped,
                "limits": {"detail_chars": DETAIL_MAX, "files": self.files_max}}


def tapped(factory: Callable, sink: Sink, where):
    """`factory` (a probe class) as a subclass that overrides `observe()` only: the `Observation` it returns is the
    probe's own, unchanged, after `sink.note` saw it. Anything that is not a class with an `observe` is returned as it
    is — there is nothing to see through."""
    if not isinstance(factory, type) or not callable(getattr(factory, "observe", None)):
        return factory

    def observe(self, spec, at, env):
        observation = factory.observe(self, spec, at, env)
        sink.note(where, spec, at, self, observation)
        return observation
    return type(factory.__name__, (factory,), {"observe": observe, "__module__": factory.__module__,
                                               "__doc__": factory.__doc__})


def _identity(story, record: Mapping) -> str:
    """What a probe record and an artifact both say of the evaluation: the story, the spec, the probe and its digest, the
    revision, the enforcement level and the result — as one canonical text (an artifact is one of these, plus its
    observation)."""
    return json.dumps([story, *(record.get(k) for k in ("spec_id", "probe_id", "probe_digest", "revision", "enforcement",
                                                       "result"))], sort_keys=True, default=str)


def artifact_problems(out: pathlib.Path, events: list[dict], rec: Mapping) -> tuple[list[str], list[str]]:
    """(problems, notes) of the diagnostic artifacts of the run directory `out` against its journal (`events`:
    `{seq, type, data}`) and record `rec` (`aisef run --verify`). The manifest already binds each file's bytes; this
    binds what it says: a file that is not one this release writes, whose name is not its content's, a proof's that
    names a probe record no `probe/evaluated` row of the journal holds (another spec, probe, revision, enforcement
    or result is another record), a review's whose finding is not the one at its place in `review-findings/` (a finding
    whose artifact could not be kept has none: a note — the review was refused and the journal says why). A run that
    broke (`rec['failure']`) may hold an observation whose row was never journaled: a note. What was not written is a
    note — it decided nothing."""
    problems, notes = [], []
    folder = pathlib.Path(out) / ARTIFACT_DIR
    rows = {_identity(d.get("story_id"), d["record"]) for e in events if e.get("type") == "probe/evaluated"
            and isinstance(d := e.get("data"), dict) and isinstance(d.get("record"), dict)}
    for path in sorted(folder.glob("*")) if folder.is_dir() else []:
        what = f"diagnostic artifact {ARTIFACT_DIR}/{path.name}"
        if not _NAME.fullmatch(path.name):
            problems.append(f"{what} is not a file this release writes")
            continue
        try:
            doc = json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, ValueError):
            doc = None
        if not isinstance(doc, dict) or doc.get("format") != ARTIFACT_FORMAT or doc.get("origin") not in ("proof", "review"):
            problems.append(f"{what} is not a probe observation of format {ARTIFACT_FORMAT}")
            continue
        proof = doc["origin"] == "proof"
        stem = review_verify.artifact_stem(str(doc.get("story_id")))
        if path.name != f"{stem}.{doc.get('attempt')}.{'p' if proof else 'r'}{doc.get('index')}.json":
            problems.append(f"{what} is not named for its story, attempt and place")
        elif not proof:
            finding = pathlib.Path(out) / review_verify.ARTIFACT_DIR / f"{stem}.{doc['attempt']}.{doc['index']}.json"
            if not finding.is_file():      # a finding that could not be preserved is refused, and the journal says so
                notes.append(f"{what}: the artifact of the finding it observes was not kept "
                             f"({review_verify.ARTIFACT_DIR}/{finding.name})")
                continue
            try:
                held = json.loads(finding.read_bytes().decode("utf-8")).get("finding", {}).get("id")
            except (OSError, ValueError, AttributeError):
                held = None
            if held is None or held != doc.get("finding"):
                problems.append(f"{what}: the finding it observes is not at {review_verify.ARTIFACT_DIR}/{finding.name}")
        elif not events:
            notes.append(f"{what}: the journal was not re-derived, so the record it names was not checked")
        elif _identity(doc.get("story_id"), doc) not in rows:
            (notes if rec.get("failure") else problems).append(
                f"{what} names a probe record (spec {str(doc.get('spec_id'))[:16]}, revision "
                f"{str(doc.get('revision'))[:12]}) that none of the journal's probe/evaluated rows of this story holds"
                + (" (the run broke: the observation may not have been journaled)" if rec.get("failure") else ""))
    kept = rec.get("diagnostics")
    present = sum(1 for p in folder.glob("*.json") if p.is_file() and _NAME.fullmatch(p.name)) if folder.is_dir() else 0
    if isinstance(kept, dict) and isinstance(kept.get("written"), int) and kept["written"] != present:
        (notes if rec.get("failure") else problems).append(
            f"RUN.json states {kept['written']} written, the directory holds {present}")
    if isinstance(kept, dict) and kept.get("not_written"):
        notes.append(f"{kept['not_written']} probe observation(s) could not be written ({ARTIFACT_DIR} is incomplete; "
                     "no verdict depends on it): see RUN.json diagnostics.failures")
    if isinstance(kept, dict) and kept.get("dropped"):
        notes.append(f"{kept['dropped']} probe observation(s) were not kept: the run's file limit was reached")
    return problems, notes
