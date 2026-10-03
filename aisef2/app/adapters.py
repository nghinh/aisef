"""The developer, the reviewer and the scanner the kernel's story runner calls (aisef2.orchestrate.adapters protocols).

The developer works in the kernel's checkout of the story and the harness commits what it changed (every git the
kernel runs is under the isolated configuration of aisef2.orchestrate.workspace, B4). A model review never blocks
(RFC §25): its findings carry no corroboration. The scanner is informational: ruff when the operator has it, else a
scanner that reports nothing — the record says which."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import sys

from aisef2.app import client, feedback
from aisef2.app.bundle import Project
from aisef2.arch.enums import ControlProjection
from aisef2.journal.format2 import OperationOutcome as O
from aisef2.orchestrate.adapters import Finding, Implemented, ProviderOutage, Reviewed, Scanned
from aisef2.orchestrate.workspace import commit_all, git

REVIEW_PROMPT = ("Review the implementation of story {story} of {name} in this read-only checkout against {requirements} "
                 "and these clauses:\n{clauses}\nDo not modify any file. Answer with ONLY one JSON object: "
                 '{{"findings": [{{"id": "short-id", "blocking": true or false, "summary": "one line"}}]}}')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def attempt_of(run, story_id: str) -> tuple[int, bool]:
    """The story's attempt number (the kernel's projection) and whether the journal holds an earlier failure of it."""
    st = run.state(ControlProjection.STORY_STATE).get(story_id) or {}
    prior = any(e.type == "failure/observed" and e.data.get("story_id") == story_id for e in run.events)
    return st.get("attempt", 0), prior


class Developer:
    def __init__(self, run, project: Project, logs: pathlib.Path, session_kw: dict, timeout_s: float) -> None:
        self.run, self.project, self.logs, self.kw, self.timeout_s = run, project, logs, session_kw, timeout_s
        self.sessions: list[dict] = []

    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str) -> Implemented:
        attempt, prior = attempt_of(self.run, story_id)
        prompt = feedback.task(self.project, story_id)
        if prior:
            told = feedback.retry_feedback(((e.seq, e.type, e.data) for e in self.run.events), story_id, self.project)
            prompt += f"\n\nA previous attempt of this story was not accepted; the kernel observed:\n{told}\nFix the implementation."
        parent = git(checkout, "rev-parse", "HEAD").stdout.strip()
        s = client.session(f"developer {story_id}", prompt, checkout, self.logs / f"{story_id}.developer.{attempt}.jsonl",
                           self.timeout_s, **self.kw)
        s.update(story_id=story_id, attempt=attempt, role="developer", prompt_sha256=_sha(prompt.encode("utf-8")))
        self.sessions.append(s)
        head = git(checkout, "rev-parse", "HEAD").stdout.strip()
        changed = bool(git(checkout, "status", "--porcelain").stdout.strip()) or head != parent
        s["developer_committed_itself"] = head != parent
        if s["error"] and not changed:
            raise ProviderOutage(s["error"])
        if not changed:
            return Implemented(O.FAILED, None, f"the developer changed nothing (exit {s['exit']}, timed out {s['timed_out']})")
        sha = commit_all(checkout, f"{story_id}: developer attempt {attempt}")
        s["candidate"] = sha
        return Implemented(O.COMPLETED, sha, f"opencode exit {s['exit']}, {s['turns']} turns" + (f", {s['stopped']}" if s["stopped"] else ""))


class Reviewer:
    def __init__(self, run, project: Project, logs: pathlib.Path, session_kw: dict, timeout_s: float) -> None:
        self.run, self.project, self.logs, self.kw, self.timeout_s = run, project, logs, session_kw, timeout_s
        self.sessions: list[dict] = []

    def review(self, scope, criteria: tuple[str, ...]) -> Reviewed:
        attempt, _ = attempt_of(self.run, scope.story_id)
        prompt = REVIEW_PROMPT.format(story=scope.story_id, name=self.project.name, requirements=self.project.requirements_path,
                                      clauses=feedback.clauses(self.project, scope.story_id))
        s = client.session(f"reviewer {scope.story_id}", prompt, scope.root,
                           self.logs / f"{scope.story_id}.reviewer.{attempt}.jsonl", self.timeout_s, **self.kw)
        s.update(story_id=scope.story_id, attempt=attempt, role="reviewer", prompt_sha256=_sha(prompt.encode("utf-8")))
        self.sessions.append(s)
        if s["error"] and not s["text"]:
            raise ProviderOutage(s["error"])
        found = []
        m = re.search(r"\{.*\}", s["text"], re.S)
        try:
            found = json.loads(m.group(0))["findings"] if m else []
        except (ValueError, KeyError, TypeError):
            found = []
        found = [f for f in found if isinstance(f, dict)] if isinstance(found, list) else []
        s["findings"] = found
        return Reviewed(O.COMPLETED, tuple(Finding(str(f.get("id")), bool(f.get("blocking")), ()) for f in found),
                        f"{len(found)} findings, parsed={m is not None}")


class RuffScanner:
    """ruff as an informational scanner, run by the kernel in its owned range; its findings never block."""
    name = "ruff"

    def __init__(self, exe: str) -> None:
        self.exe = exe

    def argv(self, scope, report: str) -> tuple[str, ...]:
        return (self.exe, "check", "--exit-zero", "--no-cache", "--output-format", "json", "--output-file", report, scope.root)

    def read(self, report: str, exit_code) -> Scanned:
        p = pathlib.Path(report)
        if not p.exists():
            return Scanned(False, ())
        rows = json.loads(p.read_text(encoding="utf-8") or "[]")
        return Scanned(True, tuple(Finding(f"{r.get('code')}:{pathlib.Path(r.get('filename', '')).name}:"
                                           f"{(r.get('location') or {}).get('row')}", False, ("scanner:ruff",)) for r in rows))


class NoScanner:
    """No scanner on this machine: the stage runs and reports no finding (the record names it)."""
    name = "none"

    def argv(self, scope, report: str) -> tuple[str, ...]:
        return (sys.executable, "-I", "-c", "import sys; open(sys.argv[1], 'w').write('[]')", report)

    def read(self, report: str, exit_code) -> Scanned:
        return Scanned(pathlib.Path(report).exists(), ())


def scanner():
    exe = shutil.which("ruff")
    return RuffScanner(exe) if exe else NoScanner()
