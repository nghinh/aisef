"""A deterministic, scripted client — the Phase 5 synthetic agent harness.

It never calls a model. Each role (developer, reviewer, security) consumes a queue of
scripted steps; the last step repeats when the queue is exhausted. Every call is
recorded (`calls`), so a test can assert which stage ran, how often, and with which
environment. Orchestration failure paths become cheap and exact:

    SyntheticClientAdapter(Script(
        developer=[Step.changed({"src/a.py": "x = 1\\n"}), Step.noop()],
        review=[Step.unrunnable(), Step.passes()],
        security=[Step.passes()],
    ))

Step kinds — developer: CHANGED(files), NOOP, TIMEOUT, MAX_TURNS(files=None), CRASH, AUTH,
CONTEXT, RATE_LIMIT, BUDGET, SCOPE_VIOLATION(files) (same as CHANGED; the scope is the gate's
business), TRUNK_COMMIT(files) (writes and commits on the project trunk — isolation breach);
review: PASS, BLOCK(findings), STUCK(findings), MALFORMED, UNRUNNABLE (timeout), MUTATE(files),
COMMIT(files), BUDGET; security: PASS, BLOCK(findings as `[sev] text` lines), UNRUNNABLE,
MALFORMED, BUDGET. Scripts can also be given as plain data (`Script.from_data`), e.g.
{"developer": ["CHANGED", "NOOP"], "review": ["UNRUNNABLE", "PASS"], "security": ["PASS"]}
with per-step options as {"kind": "CHANGED", "files": {...}}.

Role detection follows the prompt catalogue (first line `# Review` / `# Security review`),
the same rule the test doubles in tests/ have used since 1.4.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..control.budget import BudgetExceeded
from .base import Capability, ClientAdapter, RunSpec, Support
from .stream import RunResult

DEVELOPER, REVIEW, SECURITY = "developer", "review", "security"
DEFAULT_FILES = {"src/a.py": "x = 1\n"}
#: `aisef run --client synthetic` reads its script from this JSON file (`Script.from_data` shape).
ENV_SCRIPT = "AISEF_SYNTHETIC_SCRIPT"
#: What the security parser accepts as "reviewed, clean" (control/security.py clean_phrases).
SECURITY_CLEAN = ("Reviewed the diff for injection, secrets, auth and data exposure: no findings.\n"
                  '```json\n{"verdict": "pass", "findings": []}\n```\n')


@dataclass
class Step:
    kind: str
    files: dict[str, str] | None = None
    findings: list[dict] | None = None
    text: str = ""
    turns: int = 3
    cost_usd: float = 0.5

    # developer
    @classmethod
    def changed(cls, files: dict[str, str] | None = None, **kw): return cls("CHANGED", files=dict(files) if files else None, **kw)
    @classmethod
    def noop(cls, **kw): return cls("NOOP", **kw)
    @classmethod
    def timeout(cls, **kw): return cls("TIMEOUT", **kw)
    @classmethod
    def max_turns(cls, files: dict[str, str] | None = None, **kw): return cls("MAX_TURNS", files=files, **kw)
    @classmethod
    def crash(cls, **kw): return cls("CRASH", **kw)
    @classmethod
    def auth(cls, **kw): return cls("AUTH", **kw)
    @classmethod
    def context(cls, **kw): return cls("CONTEXT", **kw)
    @classmethod
    def rate_limit(cls, **kw): return cls("RATE_LIMIT", **kw)
    @classmethod
    def budget(cls, **kw): return cls("BUDGET", **kw)
    @classmethod
    def scope_violation(cls, files: dict[str, str], **kw): return cls("SCOPE_VIOLATION", files=dict(files), **kw)
    @classmethod
    def trunk_commit(cls, files: dict[str, str] | None = None, **kw): return cls("TRUNK_COMMIT", files=dict(files or {"len-thang.py": "x\n"}), **kw)
    # review / security
    @classmethod
    def passes(cls, **kw): return cls("PASS", **kw)
    @classmethod
    def block(cls, findings: list[dict] | None = None, **kw): return cls("BLOCK", findings=findings, **kw)
    @classmethod
    def stuck(cls, findings: list[dict] | None = None, **kw): return cls("STUCK", findings=findings, **kw)
    @classmethod
    def malformed(cls, **kw): return cls("MALFORMED", **kw)
    @classmethod
    def unrunnable(cls, **kw): return cls("UNRUNNABLE", **kw)
    @classmethod
    def mutate(cls, files: dict[str, str] | None = None, **kw): return cls("MUTATE", files=dict(files or {"src/reviewer.py": "x = 2\n"}), **kw)
    @classmethod
    def commit(cls, files: dict[str, str] | None = None, **kw): return cls("COMMIT", files=dict(files or {"src/reviewer.py": "x = 2\n"}), **kw)

    @classmethod
    def from_data(cls, item) -> "Step":
        if isinstance(item, str):
            return cls(item.upper())
        d = dict(item)
        kind = str(d.pop("kind")).upper()
        return cls(kind, **d)


@dataclass
class Script:
    developer: list[Step] = field(default_factory=lambda: [Step.changed()])
    review: list[Step] = field(default_factory=lambda: [Step.passes()])
    security: list[Step] = field(default_factory=lambda: [Step.passes()])

    @classmethod
    def from_data(cls, data: dict) -> "Script":
        return cls(**{role: [Step.from_data(x) for x in data.get(role, [])] or getattr(cls(), role)
                      for role in (DEVELOPER, REVIEW, SECURITY)})


@dataclass
class Call:
    role: str
    step: str
    workdir: str
    env: dict[str, str]
    prompt_head: str


def _block_findings(findings: list[dict] | None, *, default_file: str) -> list[dict]:
    return findings if findings is not None else [
        {"tag": "block", "file": default_file, "line": 1, "why": "the behaviour is wrong", "behavior_id": "FR-1"}]


class SyntheticClientAdapter(ClientAdapter):
    """Scripted, model-free client. `id` is `synthetic`; guards are never compiled for it, so the gate
    reads `guard ran` as not expected — the kernel's own decisions are what this client exercises."""

    id = "synthetic"

    def __init__(self, script: Script | dict | None = None):
        if script is None and os.environ.get(ENV_SCRIPT):
            script = json.loads(Path(os.environ[ENV_SCRIPT]).read_text(encoding="utf-8"))
        self.script = script if isinstance(script, Script) else Script.from_data(script or {})
        self._queues = {DEVELOPER: list(self.script.developer), REVIEW: list(self.script.review),
                        SECURITY: list(self.script.security)}
        self.calls: list[Call] = []
        self.develop_calls = 0
        self._served: dict[int, int] = {}

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    # ------------------------------------------------------------ dispatch
    def _next(self, role: str) -> Step:
        q = self._queues[role]
        step = q.pop(0) if len(q) > 1 else q[0]
        self._served[id(step)] = self._served.get(id(step), 0) + 1
        return step

    @staticmethod
    def _role_of(spec: RunSpec) -> str:
        head = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
        if head.startswith("# Security review"):
            return SECURITY
        if head.startswith("# Review"):
            return REVIEW
        return DEVELOPER

    def run(self, spec: RunSpec) -> RunResult:
        role = self._role_of(spec)
        step = self._next(role)
        self.calls.append(Call(role, step.kind, str(spec.workdir), dict(spec.env),
                               spec.prompt.lstrip().splitlines()[0][:80] if spec.prompt.strip() else ""))
        if role == DEVELOPER:
            self.develop_calls += 1
            return self._developer(step, spec)
        if role == REVIEW:
            return self._review(step, spec)
        return self._security(step, spec)

    # ------------------------------------------------------------ roles
    @staticmethod
    def _write(workdir: Path, files: dict[str, str]) -> None:
        for rel, content in files.items():
            p = workdir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

    def _developer(self, step: Step, spec: RunSpec) -> RunResult:
        wd = Path(spec.workdir)
        k = step.kind
        if k in ("CHANGED", "SCOPE_VIOLATION"):
            files = dict(step.files or DEFAULT_FILES)
            if (step.files is None and self.develop_calls > 1) or self._served.get(id(step), 0) > 1:
                # A real developer's retry changes something; writing identical bytes again is a no-op
                # to the kernel (correctly), which is not what CHANGED means — also when the script's last
                # step is being served again.
                files = {rel: f"{body}# attempt {self.develop_calls}\n" for rel, body in files.items()}
            self._write(wd, files)
            return RunResult(ok=True, text=step.text or "done", num_turns=step.turns, cost_usd=step.cost_usd, output_tokens=200)
        if k == "NOOP":
            # A real no-op session reads and reasons (tool calls happen) and writes nothing; the stream
            # token count is what separates it from ZERO_OUTPUT (tokens, no tools, no files — a model
            # that cannot use tools), so a scripted no-op reports none.
            return RunResult(ok=True, text=step.text or "nothing to change: the candidate already satisfies the story",
                             num_turns=step.turns, cost_usd=step.cost_usd, output_tokens=0)
        if k == "ZERO_OUTPUT":
            return RunResult(ok=True, text=step.text or "I would implement this by …", num_turns=2, output_tokens=300)
        if k == "MAX_TURNS":
            if step.files:
                files = step.files if self._served.get(id(step), 0) <= 1 else {
                    rel: f"{body}# attempt {self.develop_calls}\n" for rel, body in step.files.items()}
                self._write(wd, files)
            return RunResult(ok=False, error="max_turns: stopped at 80 turns (cap 80)", num_turns=80, cost_usd=step.cost_usd,
                             raw_result={"terminal_reason": "max_turns"})
        if k == "TIMEOUT":
            return RunResult(ok=False, error="exceeded 1800s", num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "CRASH":
            return RunResult(ok=False, error="api_error: connection reset by peer", num_turns=0, cost_usd=0.0,
                             raw_result={"api_error_status": "500"})
        if k == "AUTH":
            return RunResult(ok=False, error="authentication_error: 401 invalid x-api-key", num_turns=0,
                             raw_result={"api_error_status": "401"})
        if k == "CONTEXT":
            return RunResult(ok=False, error="prompt is too long: 210000 tokens > 200000 maximum", num_turns=1)
        if k == "RATE_LIMIT":
            return RunResult(ok=False, error="429 rate limit exceeded, retry after 1s", num_turns=0,
                             raw_result={"api_error_status": "429", "retry_after": 1})
        if k == "BUDGET":
            raise BudgetExceeded("synthetic cap reached")
        if k == "TRUNK_COMMIT":
            project = Path(spec.env.get("AISEF_PROJECT") or wd)
            self._write(project, step.files or {})
            for cmd in (["git", "add", *step.files.keys()], ["git", "commit", "-q", "-m", "synthetic trunk write"]):
                subprocess.run(cmd, cwd=project, check=False, capture_output=True)
            return RunResult(ok=True, text="done", num_turns=step.turns, cost_usd=step.cost_usd, output_tokens=200)
        raise ValueError(f"unknown developer step {k}")

    def _review(self, step: Step, spec: RunSpec) -> RunResult:
        wd = Path(spec.workdir)
        k = step.kind
        if k == "PASS":
            return RunResult(ok=True, text=step.text or 'Looks correct.\n```json\n{"verdict": "pass", "findings": []}\n```\n',
                             num_turns=step.turns, cost_usd=step.cost_usd)
        if k in ("BLOCK", "STUCK"):
            tag = "block" if k == "BLOCK" else "stuck"
            findings = _block_findings(step.findings, default_file="src/a.py")
            if k == "STUCK":
                findings = [{**f, "tag": "stuck"} for f in findings]
            body = json.dumps({"verdict": tag, "findings": findings})
            lines = "\n".join(f"- [{tag}] {f.get('file', '')}:{f.get('line', 1)} — {f.get('why', '')}" for f in findings)
            return RunResult(ok=True, text=f"{lines}\n```json\n{body}\n```\n", num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "BLOCK_UNBOUND":              # a `block` verdict whose findings name no file, behaviour or criterion (F3)
            findings = [{"tag": "block", "file": "", "line": "", "why": "the overall approach is wrong"}]
            return RunResult(ok=True, text="- [block] the overall approach is wrong\n```json\n"
                             + json.dumps({"verdict": "block", "findings": findings}) + "\n```\n",
                             num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "MALFORMED":
            return RunResult(ok=True, text=step.text or "I think this is mostly fine but I am not sure about the edge cases.",
                             num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "UNRUNNABLE":
            return RunResult(ok=False, error="exceeded 1800s", num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "MUTATE":
            self._write(wd, step.files or {})
            return RunResult(ok=True, text='```json\n{"verdict": "pass", "findings": []}\n```\n', num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "COMMIT":
            self._write(wd, step.files or {})
            for cmd in (["git", "add", "-A", "--", *step.files.keys()], ["git", "commit", "-q", "-m", "reviewer"]):
                subprocess.run(cmd, cwd=wd, check=False, capture_output=True)
            return RunResult(ok=True, text='```json\n{"verdict": "pass", "findings": []}\n```\n', num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "BUDGET":
            raise BudgetExceeded("synthetic cap reached")
        raise ValueError(f"unknown review step {k}")

    def _security(self, step: Step, spec: RunSpec) -> RunResult:
        k = step.kind
        if k == "PASS":
            return RunResult(ok=True, text=step.text or SECURITY_CLEAN, num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "BLOCK":
            findings = step.findings or [{"severity": "high", "text": "src/a.py: unsanitised input reaches a shell"}]
            # prose lines AND the structured envelope: a block without the JSON verdict is "no verdict" to the
            # harness (security:no-schema → one retry), not a block
            body = "\n".join(f"[{f['severity']}] {f['text']}" for f in findings)
            env = {"verdict": "block", "findings": [{"severity": f["severity"], "file": f["text"].split(":")[0],
                                                     "why": f["text"].split(":", 1)[-1].strip()} for f in findings]}
            return RunResult(ok=True, text=body + "\n```json\n" + json.dumps(env) + "\n```\n",
                             num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "UNRUNNABLE":
            return RunResult(ok=False, error="exceeded 1800s", num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "MALFORMED":
            return RunResult(ok=True, text="Security wise it seems okay to me.", num_turns=step.turns, cost_usd=step.cost_usd)
        if k == "BUDGET":
            raise BudgetExceeded("synthetic cap reached")
        raise ValueError(f"unknown security step {k}")
