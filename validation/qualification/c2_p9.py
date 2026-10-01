"""QP-2.9 — LedgerLock as a DEVELOPMENT / REGRESSION benchmark on the Cycle-2 candidate (owner rulings 2026-09-30 A
and B; cycle2-manifest QP-2.9; RFC §28-§30).

    python -P validation/qualification/c2_p9.py --run      # -> closure-evidence/v2/cycle2/P10/LEDGERLOCK-REGRESSION.json

The owner-approved PLAN-V2.2 (plan 27b679d9…, the 59 contracts under the 59 real approvals) executed as it is — no
re-planning, no story split — through the authoritative path (story_runner.run_story), every obligation proved by the
probe its ProductProofSpec names (C2-ORCHESTRATION-CONFORMANCE-REPAIR). The execution profile is P10's, recorded and
accepted in Cycle 1 (p10.runspec_for): a live developer and reviewer over OpenCode on the declared route (OPAQUE: a
routing alias is never attested), ruff as an informational scanner, and P10's budget limits. The LedgerLock
repository is never written: its baseline commit is cloned into a temporary directory.

Recorder: p10's (the manifest's "p10.py recorder reused"): DEVELOPMENT_REGRESSION, generalization NONE, delivery and
plan quality separately, plan_quality_verdict NOT_CLAIMED (DECISION-5: no PlanQualityPolicy is preregistered), the
raw plan-quality metrics, the mechanical prohibitions executed. A model review never blocks (§25): the reviewer's
findings carry no corroboration.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402
from validation.qualification import p10 as P10  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/P10"
SESSIONS = "sessions"
HISTORY_REL = "closure-evidence/v2/cycle2/C2-P9-RUN-HISTORY.json"
DEV_TIMEOUT_S = 2400.0
REVIEW_TIMEOUT_S = 900.0
#: P10's limits (p10.runspec_for), the accepted Cycle-1 execution profile
LIMITS = {"DEVELOPER": 1, "PLAN": 0, "ENVIRONMENT": 1, "PROVIDER": 1, "INTEGRATION": 0, "REVIEW": 1, "SECURITY": 1}
#: the execution profiles a run may name. `qp-2.9` is the profile attempts 1 and 2 ran. `v1-aligned` is PROPOSED for the
#: controlled V1-vs-V2 delivery experiment only (owner ruling 'BOUNDED CORRECTIVE PATCH' §6): 3 total developer attempts
#: (one call and two retries), which is what the comparable V1 baseline profiles gave (max_retries 2). It is a
#: measurement-profile alignment, not a framework default: the kernel's retry semantics are untouched, and a run under
#: it has another runspec hash — it is a new profile identity, never a continuation of attempts 1 and 2.
PROFILES = {"qp-2.9": LIMITS, "v1-aligned": {**LIMITS, "DEVELOPER": 2}}
PROJECT = frozenset({"ledgerlock", "tests"})
#: V1-era control metadata in a story section of the epics (H-PROMPT-001): PLAN-V2.2 supersedes all of it
LEGACY_BLOCK = re.compile(r"^\*\*Story metadata:\*\*.*\Z", re.M | re.S)
LEGACY_KEYS = ("covers", "ac_proof", "story_type", "write_scope", "depends_on", "screens")
LEGACY_LINE = re.compile(rf"^[ \t]*[-*][ \t]*(?:{'|'.join(LEGACY_KEYS)})[ \t]*:.*$\n?", re.M)
#: a 'Scope note:' paragraph of a V1 section: story ownership and proof modes as the V1 plan had them (Story 4.1 has one)
LEGACY_NOTE = re.compile(r"^Scope note:.*?(?:\n[ \t]*\n|\Z)", re.M | re.S)
#: where a run's git objects are kept before its temporary directory is removed (ruling §7); outside this repository
PRESERVE_ENV = "AISEF_QP29_PRESERVE_ROOT"
#: what the harness changed from the attempt before (a harness defect fixed by a new harness commit, both attempts recorded)
HARNESS_CHANGES = {2: "attempt 1's developer prompt named each obligation's clause by its id only (e.g. 'R-10: R-10/1') and its "
                      "retry prompt the failure codes only; attempt 2 gives the clause's paraphrase and the requirement's "
                      "numbered section of docs/requirements.md, and on a retry each observed failure with the clause its "
                      "proof concerns — never a probe, stimulus, observable or expectation. The journal is written beside "
                      "the record before the temporary directory is removed, and a secret-like token is redacted and counted "
                      "instead of aborting the record (attempt 1 left none: NO-RECORD.json). Profile, limits, plan, specs and "
                      "kernel unchanged.",
                   3: "H-PROMPT-001: attempt 2 handed the developer each V1-era epics section whole, with its 'Story metadata' "
                      "(covers / ac_proof / story_type / write_scope / depends_on / screens) — V1 control data PLAN-V2.2 "
                      "supersedes; STORY-01-01's attempt 1 followed that write_scope and did not create ledgerlock/ledger.py. "
                      "The section is now prose context only, its metadata removed, stated as non-authoritative, and the "
                      "product subjects the story's obligations name are derived from the approved contracts. The run's git "
                      "objects (final main and every candidate) are preserved outside the temporary directory before it is "
                      "removed, and it is not removed unless they are (attempt 2's final workspace was lost). Plan, specs and "
                      "contracts unchanged; the profile is named in the record."}
#: a secret-like token: `sk-` at a token start (attempt 1's pattern had no left boundary and matched inside words such as
#: "task-…", which aborted the record of a finished run: NO-RECORD.json)
SECRET = re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}")


def known_secrets() -> set[str]:
    """The exact secret values this machine holds, in memory only — the values of key/token/secret/password environment
    variables and of such fields of the OpenCode configuration. Never printed, never recorded."""
    vals = {v for k, v in os.environ.items() if re.search(r"KEY|TOKEN|SECRET|PASSWORD", k, re.I) and len(v) >= 8}

    def walk(o, key=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from walk(v, k)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v, key)
        elif isinstance(o, str) and re.search(r"api[_-]?key|token|secret|authorization|password", key, re.I) and len(o) >= 8:
            yield o
    cfg = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or (pathlib.Path.home() / ".config")) / "opencode" / "opencode.json"
    try:
        vals |= set(walk(json.loads(cfg.read_text(encoding="utf-8"))))
    except (OSError, ValueError):
        pass
    return vals


def redact(text: str, secrets: set[str]) -> tuple[str, int]:
    """`text` with every exact known secret and every secret-like token replaced, and how many were replaced. A finished
    run is never discarded over a suspicion: the suspected bytes are removed and counted, the rest is kept."""
    n = 0
    for v in sorted(secrets, key=len, reverse=True):
        c = text.count(v)
        if c:
            text, n = text.replace(v, "<REDACTED:known-secret>"), n + c
    text, m = SECRET.subn("<REDACTED:secret-like>", text)
    return text, n + m


def attempt_dir(n: int) -> str:
    return OUT_REL if n == 1 else f"{OUT_REL}/attempt-{n}"


def attempt_record(n: int) -> str | None:
    """The record an attempt left: its regression record, or the record that it left none."""
    for name in ("LEDGERLOCK-REGRESSION.json", "NO-RECORD.json"):
        if (ROOT / attempt_dir(n) / name).exists():
            return f"{attempt_dir(n)}/{name}"
    return None


def _sha(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def test_path(story: str) -> str:
    return f"tests/test_{story.lower().replace('-', '_')}.py"


def epics_section(epics: str, story: str) -> str:
    """The V1 story's own section of _bmad-output/epics.md at the plan commit (STORY-01-05 -> '### Story 1.5:')."""
    e, n = (int(x) for x in story.split("-")[1:])
    m = re.search(rf"^### Story {e}\.{n}:.*?(?=^### |^## |\Z)", epics, re.M | re.S)
    return m.group(0).strip() if m else ""


def story_prose(epics: str, story: str) -> str:
    """The V1 story's section as PROSE CONTEXT ONLY (H-PROMPT-001): its 'Story metadata' block, any line of V1 control
    metadata and any 'Scope note:' paragraph are removed — covers, ac_proof, story_type, write_scope, depends_on,
    screens and the V1 plan's ownership notes belong to the V1 plan and contradict PLAN-V2.2 wherever they differ
    (STORY-01-01's write_scope has no ledger.py; PLAN-V2.2's obligations are over it). What the story must deliver, on
    which subjects and after which stories comes from the current plan only."""
    return LEGACY_LINE.sub("", LEGACY_NOTE.sub("", LEGACY_BLOCK.sub("", epics_section(epics, story)))).strip()


def subject_text(kind: str, locator: str) -> str:
    """A contract's product subject as the developer reads it: a path, `module:object`, or the CLI entry point."""
    if kind == "file_artifact":
        path = locator.removeprefix("path:")
        return f"{path}/ (the package directory)" if "." not in path.rsplit("/", 1)[-1] else path
    if kind == "cli_invocation":
        return f"python -m {locator.split(':')[0]}"
    return locator


def sections(requirements: str) -> dict[str, str]:
    """'10' -> '§10 Language / Runtime', '3.1' -> '§3.1 Key normalization (Unicode NFC)': the numbered headings of the
    requirements, so a requirement id R-<n> names the section the developer reads."""
    out = {}
    for m in re.finditer(r"^#{2,3} (\d+(?:\.\d+)?)\.? (.+)$", requirements, re.M):
        out[m.group(1)] = f"§{m.group(1)} {m.group(2).strip()}"
    return out


def prompts(plan, epics: str, requirements: str = "") -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """The developer's task per plan story: the requirements (authoritative, in the repository), the requirement clause
    of each obligation it must deliver or preserve and the product subjects those obligations name — all from the
    CURRENT plan and contracts — and the story's V1-era epics section as prose context only (`story_prose`: no V1
    control metadata, and said to yield to the clauses). The specs' probes, stimuli and expectations are not shown: the
    proof is independent of the developer."""
    from validation.qualification import p10_contracts as aid
    graph = aid.story_graph()
    specs = {s.id: sid for sid, s in _compiled().items()}
    text = {c["id"]: c["clause"] for c in aid.CLAUSES}
    secs = sections(requirements)
    out, clauses, by_criterion = {}, {}, {}
    for story in sorted({o.story_id for o in plan.obligations}):
        lines = []
        for o in (o for o in plan.obligations if o.story_id == story):
            t = aid.SPECS[specs[o.product_proof_spec_id]]
            where = secs.get(t["requirement"].removeprefix("R-"), "")
            line = (f"- [{o.role.value}] {t['requirement']} (docs/requirements.md {where}), clause {t['clause']}: "
                    f"{text.get(t['clause'], t['clause'])}")
            lines.append(line)
            by_criterion[o.criterion_id] = line
        prior = [s for s in sorted(graph.get(story, ())) if not any(o.story_id == s for o in plan.obligations)]
        clauses[story] = "\n".join(dict.fromkeys(lines))
        prior_text = "\n\n".join(story_prose(epics, s) for s in prior)
        subjects = sorted({subject_text(aid.SPECS[specs[o.product_proof_spec_id]]["kind"], aid.SPECS[specs[o.product_proof_spec_id]]["locator"])
                           for o in plan.obligations if o.story_id == story})
        out[story] = (
            f"You are the developer of LedgerLock story {story}. LedgerLock is a small Python library and CLI; "
            "docs/requirements.md in this repository is the authoritative specification. Implement this story in this "
            "repository (the package `ledgerlock/`, Python standard library only), working only inside this directory.\n\n"
            "What this story must deliver is defined by the requirement clauses listed below and by docs/requirements.md. "
            "The story description that follows is historical context only: where it names files, modules, scopes or "
            "layouts that differ from the clauses or the requirements, the clauses and the requirements govern.\n\n"
            f"The story (context only):\n\n{story_prose(epics, story)}\n\n"
            + (f"Earlier stories it builds on that no other step of this run delivers (context only; implement what is missing):\n\n{prior_text}\n\n" if prior else "")
            + "When you finish, each of the following requirement clauses is verified independently against the "
              "requirements (INTRODUCE: this story makes it true; PRESERVE: it must stay true):\n"
            + "\n".join(dict.fromkeys(lines))
            + f"\n\nThe product subjects those clauses are verified on: {', '.join(subjects)}."
            + f"\n\nWrite this story's unit tests in {test_path(story)} (unittest; `python -m unittest {test_path(story)}` "
              "must pass from the repository root) and keep every earlier test passing. Do not edit docs/requirements.md. "
              "Do not run git commit; the harness commits your working tree.")
    return out, clauses, by_criterion


_COMPILED: dict = {}


def _compiled() -> dict:
    """The 59 specs compiled under the persisted real approvals (C2-P5 acceptance), keyed by spec id."""
    if not _COMPILED:
        from aisef2.probe import catalog
        from aisef2.product.compiler import ProbeRef, compile_spec
        from validation.qualification import p5_acceptance as pa
        aid = pa._aid()
        reqs, real = aid.requirements(), pa.load_approvals()
        refs = {k: ProbeRef(e.probe_id, e.probe_digest) for k, e in catalog.active().items()}
        _COMPILED.update({sid: compile_spec(c, requirements=reqs, approvals=real, probes=refs) for sid, c in pa.contracts().items()})
    return _COMPILED


# --------------------------------------------------------------------------------------------- the live capabilities

def opencode_session(name: str, prompt: str, cwd: str, log: pathlib.Path, timeout_s: float) -> dict:
    """One `opencode run --format json` session inside a V2 process range (the kernel's own OS-owned range: every
    process it starts ends with it); the event stream goes to `log`."""
    from aisef2.runtime.process_range import ProcessRange
    exe = shutil.which("opencode")
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as fh:
        r = ProcessRange(name, [exe, "run", "--format", "json", "--dir", cwd, prompt], cwd=cwd, output=fh)
        r.start()
        try:
            code = r.wait(timeout_s)
        finally:
            r.release()
    text, error, turns, tokens = [], None, 0, {"input": 0, "output": 0}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        part = ev.get("part") or {}
        if ev.get("type") == "text":
            text.append(str(part.get("text") or ""))
        elif ev.get("type") == "error":
            info = ev.get("error") or {}
            data = info.get("data") or {}
            error = f"{info.get('name') or 'error'}: {str(data.get('message') or '')[:200]}" + (
                f" (HTTP {data['statusCode']})" if data.get("statusCode") else "")
        elif ev.get("type") == "step_finish":
            turns += 1
            tk = part.get("tokens") or {}
            tokens["input"] += int(tk.get("input") or 0)
            tokens["output"] += int(tk.get("output") or 0)
    return {"exit": code, "timed_out": code is None, "error": error, "text": "".join(text), "turns": turns, "tokens": tokens,
            "seconds": round(time.monotonic() - started, 1), "log": log.name, "log_sha256": _sha(log.read_bytes())}


class OpenCodeDeveloper:
    def __init__(self, run, prompts: dict[str, str], logs: pathlib.Path, by_criterion: dict[str, str] | None = None) -> None:
        self.run, self.prompts, self.logs, self.sessions, self.by_criterion = run, prompts, logs, [], by_criterion or {}

    def feedback(self, story_id: str) -> str:
        """The failures the kernel observed in this story, each with the requirement clause its proof concerns."""
        rows = []
        for e in self.run.events:
            if e.type == "failure/observed" and e.data.get("story_id") == story_id:
                m = re.match(r"proof of (\S+):", str(e.data.get("detail", "")))
                clause = self.by_criterion.get(m.group(1), "") if m else ""
                rows.append(f"- {e.data['code']}" + (f" — {clause.lstrip('- ')}" if clause else f": {e.data.get('detail', '')}"))
        return "\n".join(rows)

    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import Implemented, ProviderOutage
        from aisef2.orchestrate.workspace import commit_all, git
        from validation.qualification.q5 import _story_context
        attempt, prior = _story_context(self.run, story_id)
        prompt = self.prompts[story_id] + (f"\n\nA previous attempt of this story was not accepted; the kernel observed:\n"
                                           f"{self.feedback(story_id)}\nFix the implementation." if prior else "")
        parent = git(checkout, "rev-parse", "HEAD").stdout.strip()
        s = opencode_session(f"developer {story_id}", prompt, checkout, self.logs / f"{story_id}.developer.{attempt}.jsonl", DEV_TIMEOUT_S)
        s.update(story_id=story_id, attempt=attempt, role="developer", prompt_sha256=_sha(prompt.encode()))
        self.sessions.append(s)
        changed = bool(git(checkout, "status", "--porcelain").stdout.strip()) or git(checkout, "rev-parse", "HEAD").stdout.strip() != parent
        s["developer_committed_itself"] = git(checkout, "rev-parse", "HEAD").stdout.strip() != parent
        if s["error"] and not changed:
            raise ProviderOutage(s["error"])
        if not changed:
            return Implemented(O.FAILED, None, f"the developer changed nothing (exit {s['exit']}, timed out {s['timed_out']})")
        sha = commit_all(checkout, f"{story_id}: developer attempt {attempt}")
        s["candidate"] = sha
        return Implemented(O.COMPLETED, sha, f"opencode exit {s['exit']}, {s['turns']} turns")


class OpenCodeReviewer:
    PROMPT = ("Review the implementation of LedgerLock story {story} in this read-only checkout against docs/requirements.md "
              "and these clauses:\n{clauses}\nDo not modify any file. Answer with ONLY one JSON object: "
              '{{"findings": [{{"id": "short-id", "blocking": true or false, "summary": "one line"}}]}}')

    def __init__(self, run, clauses: dict[str, str], logs: pathlib.Path) -> None:
        self.run, self.clauses, self.logs, self.sessions = run, clauses, logs, []

    def review(self, scope, criteria: tuple[str, ...]):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import Finding, ProviderOutage, Reviewed
        from validation.qualification.q5 import _story_context
        attempt, _ = _story_context(self.run, scope.story_id)
        prompt = self.PROMPT.format(story=scope.story_id, clauses=self.clauses[scope.story_id])
        s = opencode_session(f"reviewer {scope.story_id}", prompt, scope.root, self.logs / f"{scope.story_id}.reviewer.{attempt}.jsonl",
                             REVIEW_TIMEOUT_S)
        s.update(story_id=scope.story_id, attempt=attempt, role="reviewer", prompt_sha256=_sha(prompt.encode()))
        self.sessions.append(s)
        if s["error"] and not s["text"]:
            raise ProviderOutage(s["error"])
        found = []
        m = re.search(r"\{.*\}", s["text"], re.S)
        try:
            found = json.loads(m.group(0))["findings"] if m else []
        except (ValueError, KeyError, TypeError):
            found = []
        s["findings"] = found
        # a model review alone never blocks (§25, D-002): no corroborating authority is attached
        return Reviewed(O.COMPLETED, tuple(Finding(str(f.get("id")), bool(f.get("blocking")), ()) for f in found if isinstance(f, dict)),
                        f"{len(found)} findings, parsed={m is not None}")


class RuffScanner:
    """ruff as an informational scanner (P10's profile): run by the kernel in its owned range; findings never block."""
    name = "ruff"

    def argv(self, scope, report: str) -> tuple[str, ...]:
        return (shutil.which("ruff"), "check", "--exit-zero", "--no-cache", "--output-format", "json", "--output-file", report, scope.root)

    def read(self, report: str, exit_code):
        from aisef2.orchestrate.adapters import Finding, Scanned
        p = pathlib.Path(report)
        if not p.exists():
            return Scanned(False, ())
        rows = json.loads(p.read_text(encoding="utf-8") or "[]")
        return Scanned(True, tuple(Finding(f"{r.get('code')}:{pathlib.Path(r.get('filename', '')).name}:{(r.get('location') or {}).get('row')}",
                                           False, ("scanner:ruff",)) for r in rows))


# ------------------------------------------------------------------------------ the product result outlives the run

def preserve_root() -> pathlib.Path:
    """Where preserved runs are kept: outside this repository and outside any temporary directory."""
    return pathlib.Path(os.environ.get(PRESERVE_ENV) or (P10.LEDGERLOCK_REPO.parent / "aisef-qp-2.9-preserved"))


def run_shas(events: list[dict], sessions: list[dict], final: str | None) -> list[str]:
    """Every revision the run's records name: final main, each committed revision, each proved candidate, each session's
    candidate — the objects an inspection or the independent acceptance oracle needs afterwards."""
    shas = {final} | {s.get("candidate") for s in sessions}
    for e in events:
        if e["type"] == "story/commit":
            shas.add(e["data"].get("revision"))
        elif e["type"] in ("proof/verified", "story/begin"):
            shas.add(e["data"].get("candidate") or e["data"].get("parent"))
    return sorted(x for x in shas if x)


def preserve(repo: pathlib.Path, dest: pathlib.Path, final: str, shas: list[str]) -> dict:
    """The run repository's whole git directory copied to `dest` (every object, reachable or not: a rolled-back
    candidate is on no branch) and each named revision pinned under refs/qp-2.9/, then checked in the copy. `dest` must
    not exist: a preserved run is never overwritten. The answer names what is missing; the caller removes the
    temporary directory only when nothing is (`may_remove`)."""
    if dest.exists():
        raise FileExistsError(f"{dest} exists — a preserved run is never overwritten")
    dest.parent.mkdir(parents=True, exist_ok=True)
    git_dir = subprocess.run(["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"], capture_output=True, encoding="utf-8",
                             check=True).stdout.strip()
    shutil.copytree(git_dir, dest, symlinks=True)

    def g(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "--git-dir", str(dest), *a], capture_output=True, encoding="utf-8")
    g("config", "core.bare", "true")
    g("worktree", "prune")                       # the run's checkouts lived in the temporary directory
    present, missing = [], []
    for sha in sorted(set(shas) | {final}):
        ok = g("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0 and \
            g("update-ref", f"refs/qp-2.9/{'final-main' if sha == final else 'revisions/' + sha}", sha).returncode == 0
        (present if ok else missing).append(sha)
    tree = g("rev-parse", f"{final}^{{tree}}").stdout.strip() if final in present else None
    return {"path": str(dest), "final_main": final, "final_tree": tree, "revisions_pinned": len(present), "missing": missing,
            "how_to_inspect": f"git --git-dir {dest} worktree add <dir> {final}  (the independent acceptance oracle runs in <dir>)"}


def may_remove(preserved: dict | None) -> bool:
    """The temporary directory may go only when the run's result is held elsewhere: final main and its tree present,
    nothing named missing. Otherwise it is kept — cleanup never destroys the only inspectable product result."""
    return bool(preserved and preserved.get("final_tree") and not preserved.get("missing"))


# --------------------------------------------------------------------------------------------------------- the run

def order(plan, graph) -> list[str]:
    stories = sorted({o.story_id for o in plan.obligations})
    done, out = set(), []
    while len(out) < len(stories):
        ready = [s for s in stories if s not in done and not (graph.get(s, set()) & set(stories)) - done]
        if not ready:
            raise SystemExit("the plan's story graph has a cycle")
        out.append(ready[0])
        done.add(ready[0])
    return out


def run(out_dir: pathlib.Path, *, preserve_to: pathlib.Path, profile: str = "qp-2.9") -> dict:
    from aisef2.arch.enums import ControlProjection, Enforcement, Owner
    from aisef2.orchestrate import story_runner as sr
    from aisef2.orchestrate.quality import TestsPolicy
    from aisef2.orchestrate.workspace import GitMerger, GitWorkspace, git
    from aisef2.probe import catalog
    from aisef2.probe.protocol import ExecutionEnv
    from aisef2.product.contract import plain
    from aisef2.quality import test_execution as te
    from aisef2.runtime.capability import opaque, verified
    from aisef2.runtime.run_scope import RunScope
    from aisef2.runtime.runspec import resolve
    from validation.qualification import p5_acceptance as pa
    from validation.qualification import p10_contracts as aid
    from validation.qualification import q4
    started = time.time()
    base = P10.ledgerlock_baseline()
    if not base.get("present") or not base.get("requirements_match_frozen"):
        raise SystemExit(f"the LedgerLock workload is not where the freeze says or its requirements changed: {base}")
    plan = aid.build()["plan"]
    if plan.plan_hash != pa.ACCEPTED["plan_hash"] or plan.baseline != base["baseline"]:
        raise SystemExit("the plan is not the owner-approved PLAN-V2.2 at its baseline")
    specs = {s.id: s for s in _compiled().values()}
    oc = P10.opencode_identity()
    epics = subprocess.run(["git", "-C", str(P10.LEDGERLOCK_REPO), "show", f"{P10.LEDGERLOCK_PLAN_COMMIT}:_bmad-output/epics.md"],
                           capture_output=True, encoding="utf-8", check=True).stdout
    requirements_md = subprocess.run(["git", "-C", str(P10.LEDGERLOCK_REPO), "show", f"{P10.LEDGERLOCK_PLAN_COMMIT}:docs/requirements.md"],
                                     capture_output=True, encoding="utf-8", check=True).stdout
    tasks, clauses, by_criterion = prompts(plan, epics, requirements_md)
    kernel = q4._over(q4._file_digests(("aisef2",)))
    caps = [verified("kernel", kernel.encode(), Enforcement.FULL, tree=C.git("rev-parse", "HEAD:aisef2")),
            verified("python", pathlib.Path(sys.executable), Enforcement.PARTIAL, version=platform.python_version()),
            verified("git", pathlib.Path(shutil.which("git")), Enforcement.PARTIAL),
            *[verified(e.probe_id, e.probe_digest.encode(), Enforcement.PARTIAL) for e in catalog.CATALOG if e.active],
            opaque("developer", Enforcement.PARTIAL, client="opencode", route=str(oc["declared_route"]), version=str(oc["version"])),
            opaque("reviewer", Enforcement.PARTIAL, client="opencode", route=str(oc["declared_route"]), version=str(oc["version"])),
            opaque("scanner", Enforcement.PARTIAL, tool="ruff", mode="lint as an informational scanner")]
    layers = {"workload": {"value": "LedgerLock", "layer": "c2-p9"}, "benchmark_class": {"value": P10.BENCHMARK_CLASS, "layer": "c2-p9"},
              "plan_hash": {"value": plan.plan_hash, "layer": "plan"}, "requirements_sha256": {"value": P10.REQUIREMENTS_SHA256, "layer": "workload"},
              "limits": {"value": PROFILES[profile], "layer": f"c2-p9 profile {profile}"}}
    logs = out_dir / SESSIONS
    logs.mkdir(parents=True, exist_ok=True)
    results, errors, events, state, run_id, final, preserved = {}, [], [], {}, {}, None, None
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="aisef2-c2-p9-")).resolve()   # removed below, and only once preserved
    dev = rev = None
    try:
        repo = tmp / "repo"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(P10.LEDGERLOCK_REPO), str(repo)], check=True, capture_output=True, encoding="utf-8")
        git(repo, "checkout", "-q", "-B", "main", base["baseline"])
        for n in ("ws", "merge", "run"):
            (tmp / n).mkdir()
        ws, merger = GitWorkspace(repo, tmp / "ws"), GitMerger(repo, "main", tmp / "merge")
        run_ = RunScope(tmp / "run", "c2-p9-ledgerlock", spec=lambda: resolve(caps, layers, base["baseline"]))
        run_.begin()
        dev, rev = OpenCodeDeveloper(run_, tasks, logs, by_criterion), OpenCodeReviewer(run_, clauses, logs)
        adapters = sr.Adapters(dev, rev, RuffScanner(), merger, ws)
        factories = {e.probe_id: (lambda on_range, scratch, f=e.factory: f(on_range=on_range, scratch=scratch)) for e in catalog.CATALOG}
        env = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)
        limits = {Owner[k]: v for k, v in PROFILES[profile].items()}
        delivered: list[str] = []
        for story in order(plan, aid.story_graph()):
            inputs = sr.StoryInputs(specs, factories, env, te.DeveloperTests(story, (test_path(story),)),
                                    te.DeveloperTests(story, tuple(test_path(s) for s in delivered) or (test_path(story),)),
                                    te.Dependencies(frozenset(), PROJECT), te.UNITTEST)
            try:
                r = sr.run_story(run_, plan, story, inputs, adapters, sr.Policy(limits, TestsPolicy(True), tool_timeout_s=120))
                results[story] = [a.outcome for a in r.attempts]
                if results[story][-1:] == ["COMMIT"]:
                    delivered.append(story)
            except Exception as e:  # noqa: BLE001 — a typed refusal of one story is recorded; the run goes on
                errors.append({"story": story, "error": f"{type(e).__name__}: {e}"[:2000]})
                results[story] = [f"REFUSED: {type(e).__name__}"]
                if run_._state != "RUNNING":
                    break
        state = plain(run_.state(ControlProjection.STORY_STATE))
        if run_._state == "RUNNING":
            run_.shutdown()
        events = [{"seq": e.seq, "type": e.type, "data": plain(e.data)} for e in run_.events]
        (out_dir / "JOURNAL.json").write_text(C.render(events), encoding="utf-8")   # kept whatever happens after
        run_id = {"run_id": "c2-p9-ledgerlock", "journal_events": len(events),
                  "journal_sha256": _sha(json.dumps(events, sort_keys=True, default=str).encode())}
        final = git(repo, "rev-parse", "main").stdout.strip()
    finally:
        # the product result outlives the run: whatever happened above, the repository is copied out before anything is
        # removed, and the temporary directory stays when the copy does not hold final main
        try:
            repo_at = tmp / "repo"
            head = final or subprocess.run(["git", "-C", str(repo_at), "rev-parse", "main"], capture_output=True, encoding="utf-8").stdout.strip()
            sessions_now = (dev.sessions if dev else []) + (rev.sessions if rev else [])
            preserved = preserve(repo_at, preserve_to, head, run_shas(events, sessions_now, head))
        except Exception as e:  # noqa: BLE001 — a failed preservation keeps the directory; it never loses the run
            preserved = {"path": str(preserve_to), "error": f"{type(e).__name__}: {e}"[:500], "missing": ["<not preserved>"]}
        if may_remove(preserved):
            shutil.rmtree(tmp, ignore_errors=True)
            preserved["temporary_directory"] = "removed after the copy was checked"
        else:
            preserved["temporary_directory"] = f"KEPT at {tmp}: the copy does not hold the whole result"
    return {"started": started, "results": results, "errors": errors, "events": events, "state": state,
            "run_identity": run_id, "final_main": final, "preserved": preserved, "profile": profile,
            "baseline": base, "oc": oc, "plan": plan, "specs": specs, "tasks": tasks,
            "sessions": (dev.sessions if dev else []) + (rev.sessions if rev else []), "caps": caps, "layers": layers, "kernel": kernel}


def record(out_dir: pathlib.Path, m: dict) -> dict:
    from aisef2.runtime.runspec import resolve
    from validation.qualification import p5_acceptance as pa
    from validation.qualification import p10_contracts as aid
    plan, events = m["plan"], m["events"]
    roles = {o.criterion_id: o.role.value for o in plan.obligations}
    delivery = P10.delivery_verdict_of(events, plan_admitted=True)
    metrics = P10.plan_quality_metrics(events, roles)
    policy, at, policy_path = P10.preregistered_policy(out_dir)
    if policy_path is not None:
        raise SystemExit("DECISION-5: no PlanQualityPolicy may be preregistered for LedgerLock")
    plan_quality = P10.plan_quality_verdict_of(metrics, policy, policy_preregistered_at=at, run_started_at=m["started"])
    verdict = P10.RunVerdict(delivery, plan_quality)
    prohibitions = {}
    for target in ("SEALED", "HOLDOUT", "EVALUATING"):
        try:
            P10.LEDGERLOCK.transition(target)
            prohibitions[target] = "ACCEPTED (defect)"
        except P10.SealingRefused as e:
            prohibitions[target] = f"REJECTED: {e}"
    for name, kw in (("generalization_claim=POSITIVE", {"generalization_claim": "POSITIVE"}), ("qualification_sample_size", {"qualification_sample_size": 1})):
        try:
            P10.Recorder().record(**{"benchmark_class": P10.BENCHMARK_CLASS, "generalization_claim": "NONE", "cohort_state": "DEVELOPMENT", "verdict": verdict, **kw})
            prohibitions[name] = "ACCEPTED (defect)"
        except P10.ClaimRefused as e:
            prohibitions[name] = f"REJECTED: {e}"
    try:
        P10.overall_verdict(verdict)
        prohibitions["overall_verdict"] = "ACCEPTED (defect)"
    except P10.ClaimRefused as e:
        prohibitions["overall_verdict"] = f"REJECTED: {e}"
    # the ProductProof account per obligation, from the journal: the last verified proof of each criterion
    proofs = {}
    for e in events:
        if e["type"] == "proof/verified":
            proofs[(e["data"].get("story_id"), e["data"].get("criterion_id"))] = {"candidate": e["data"].get("candidate"), "seq": e["seq"],
                                                                                   "agreement": e["data"].get("agreement"),
                                                                                   "verdict": e["data"].get("verdict")}
    committed = {s for s, v in m["results"].items() if v[-1:] == ["COMMIT"]}
    obligations = []
    for o in plan.obligations:
        spec = m["specs"][o.product_proof_spec_id]
        proof = proofs.get((o.story_id, o.criterion_id))
        satisfied = bool(proof and proof["agreement"] and proof["verdict"] == spec.candidate_expectation.value)
        obligations.append({"story": o.story_id, "criterion": o.criterion_id, "role": o.role.value, "spec": o.product_proof_spec_id,
                            "probe_id": spec.probe_id, "candidate_expectation": spec.candidate_expectation.value, "last_proof": proof,
                            "satisfied_at_last_proof": satisfied, "delivered": satisfied and o.story_id in committed})
    prop = json.loads((ROOT / pa.PROPOSAL_REL).read_text(encoding="utf-8"))
    clauses = prop["clauses"]
    spec_req = {sid: t["requirement"] for sid, t in aid.SPECS.items()}
    covered = sorted({spec_req[sid] for sid in pa.contracts()})
    by_class = {}
    for c in clauses:
        by_class.setdefault(c["class"], []).append(c["id"])
    sessions = m["sessions"]
    spec = resolve(m["caps"], m["layers"], m["baseline"]["baseline"])
    rec = P10.Recorder().record(
        record="AISEF V2 — CYCLE-2 QP-2.9 LEDGERLOCK REGRESSION (DEVELOPMENT / REGRESSION BENCHMARK ONLY)", rung="C2-P9 / QP-2.9",
        authority="owner rulings 2026-09-30 A ('C2-P9 / QP-2.9 — LEDGERLOCK REGRESSION') and B (QP-2.9: execute the approved plan model)",
        written=C.now(), purpose="does the Cycle-2 framework execute more of the known workload correctly? — not: how would AISEF perform on unseen projects",
        semantic_candidate=C.SEMANTIC_CANDIDATE, aisef2_tree=C.KERNEL_TREE, head_kernel_tree=C.git("rev-parse", "HEAD:aisef2"),
        repository_execution_commit=C.git("rev-parse", "HEAD"), harness={"path": "validation/qualification/c2_p9.py", "sha256": C.lf_sha(HERE / "c2_p9.py")},
        workload={"id": "LedgerLock", "benchmark_class": P10.BENCHMARK_CLASS, "repository": m["baseline"], "requirements_sha256": P10.REQUIREMENTS_SHA256,
                  "final_main": m["final_main"], "repository_written": False, "preserved": m["preserved"]},
        plan_identity={"id": plan.id, "plan_hash": plan.plan_hash, "baseline": plan.baseline, "stories": len({o.story_id for o in plan.obligations}),
                       "obligations": len(plan.obligations), "execution_order": order(plan, aid.story_graph()), "replanned": False, "stories_split": False},
        approvals={"record": pa.APPROVALS_REL, "count": len(pa.load_approvals()), "approver": pa.OWNER},
        execution_profile={"source": "p10.runspec_for (Cycle-1 P10 profile): OpenCode developer and reviewer on the declared route, ruff scanner, "
                                     f"the limits of profile {m['profile']}",
                           "profile": m["profile"], "developer_attempts_per_story": PROFILES[m["profile"]]["DEVELOPER"] + 1,
                           "runspec_hash": spec.runspec_hash, "aggregate_min_grade": spec.aggregate_min_grade.value, "limits": PROFILES[m["profile"]],
                           "capabilities": [{"name": c.name, "grade": c.grade.value, "enforcement": c.enforcement.value} for c in spec.capabilities],
                           "model": m["oc"], "kernel_digest": m["kernel"],
                           "grade_note": "the route is a routing alias: OPAQUE, which bars sealing and nothing else here; no model identity is inferred from it"},
        run_identity=m["run_identity"], cohort_state="DEVELOPMENT", benchmark_class=P10.BENCHMARK_CLASS, generalization_claim=P10.GENERALIZATION_CLAIM,
        verdict=verdict, delivery_verdict_derivation="from the run's journal events only; no plan-quality input",
        story_outcomes=m["results"], story_state=m["state"], story_errors=m["errors"],
        productproof={"obligations": obligations, "total": len(obligations),
                      "with_a_verified_proof": sum(1 for o in obligations if o["last_proof"]),
                      "satisfied_at_last_proof": sum(1 for o in obligations if o["satisfied_at_last_proof"]),
                      "delivered_in_committed_stories": sum(1 for o in obligations if o["delivered"]),
                      "rule": "satisfied = the two parties agree and the verdict is the spec's candidate expectation; delivered = "
                              "satisfied in a story whose last outcome is COMMIT"},
        requirements={"covered_by_productproof": covered,
                      "unsupported": {"clauses": by_class.get(aid.U, []), "rule": "remain UNSUPPORTED_FOR_FULL_ENFORCEMENT; never counted as passes"},
                      "engineering_test_only": by_class.get(aid.E, []), "classes": {k: len(v) for k, v in by_class.items()},
                      "known_ambiguities": prop["requirement_risks"]},
        plan_quality_metrics=metrics, plan_drift={"attributed": metrics["attributed_plan_drift"], "unattributed": metrics["unattributed_plan_drift"]},
        plan_quality_policy={"preregistered": False, "decision": "DECISION-5: DO_NOT_PREREGISTER", "path": None},
        model_sessions={"count": len(sessions), "by_role": {r: sum(1 for s in sessions if s["role"] == r) for r in ("developer", "reviewer")},
                        "sessions": [{k: v for k, v in s.items() if k != "text"} for s in sessions],
                        "tokens": {k: sum(s["tokens"][k] for s in sessions) for k in ("input", "output")}},
        prohibitions=prohibitions, residual_processes={"owned_range": "see the owned-run record beside this file"},
        platform={"system": platform.system().lower(), "python": platform.python_version()},
        stop_rules={"kernel_tree_is_the_candidates": C.git("rev-parse", "HEAD:aisef2") == C.KERNEL_TREE, "plan_retuned": False, "kernel_repaired": False,
                    "historical_evidence_rewritten": False, "cohort_sealed": False, "generalization_claimed": False},
        finished=C.now(),
    )
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", required=True)
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="qp-2.9")
    a = ap.parse_args(argv)
    rel = attempt_dir(a.attempt)
    out_dir = ROOT / rel
    if attempt_record(a.attempt):
        raise SystemExit(f"REFUSED: {attempt_record(a.attempt)} exists — a rerun is a new attempt, never an overwrite")
    prior = [attempt_record(n) for n in range(1, a.attempt)]
    if None in prior:
        raise SystemExit(f"REFUSED: attempt {a.attempt} without a record of every earlier attempt")
    preserve_to = preserve_root() / f"attempt-{a.attempt}.git"
    if preserve_to.exists():    # before any model call: a run whose result could not be kept is not started
        raise SystemExit(f"REFUSED: {preserve_to} exists — the result of attempt {a.attempt} would have nowhere to be preserved")
    m = run(out_dir, preserve_to=preserve_to, profile=a.profile)
    rec = record(out_dir, m)
    rec["attempt"] = a.attempt
    rec["harness_change_from_prior_attempt"] = HARNESS_CHANGES.get(a.attempt)
    rec["prior_attempts"] = [{"path": r, "sha256": C.lf_sha(ROOT / r),
                              "delivery_verdict": json.loads((ROOT / r).read_text(encoding="utf-8")).get("delivery_verdict", "NO_RECORD")}
                             for r in prior]
    secrets, redactions = known_secrets(), {}
    for p in [*sorted((out_dir / SESSIONS).glob("*.jsonl")), out_dir / "JOURNAL.json"]:
        text, n = redact(p.read_text(encoding="utf-8", errors="replace"), secrets)
        if n:
            p.write_text(text, encoding="utf-8")
            redactions[p.name] = n
    body, n = redact(json.dumps(rec, default=str), secrets)
    rec = json.loads(body)
    for s in rec["model_sessions"]["sessions"]:
        if s.get("log"):
            s["log_sha256"] = _sha((out_dir / SESSIONS / s["log"]).read_bytes())   # the bytes kept, after any redaction
    rec["journal_file"] = {"path": f"{rel}/JOURNAL.json", "sha256": C.lf_sha(out_dir / "JOURNAL.json")}
    rec["secret_scan"] = {"known_secret_values_checked": len(secrets), "redactions_in_files": redactions, "redactions_in_record": n,
                          "rule": "exact known secret values and sk- tokens are replaced and counted; nothing is discarded"}
    C.write(f"{rel}/LEDGERLOCK-REGRESSION.json", rec)
    print(f"delivery {rec['delivery_verdict']}; plan quality {rec['plan_quality_verdict']}; outcomes {rec['story_outcomes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
