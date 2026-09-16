"""Phase 12 — differential model-based testing: REFERENCE MODEL vs REAL AISEF KERNEL.

One seed → one scripted scenario (developer / review / security step queues + a run-level environment
variant). The same script drives (a) `tests.hardening.model.Kernel` through `ModelRun`, which pops the
queues exactly as the synthetic client does, and (b) the real `implement_story` through
`SyntheticClientAdapter` in a real isolated worktree. Both sides are reduced to the same typed
`Observation` and compared field by field.

A mismatch is either attributed to a registered, still-open kernel defect (`attribute()`) or it is
UNEXPLAINED — a hard failure. `KNOWN` must be empty at W0.

CLI (the big run):  python3 -m tests.hardening.differential --traces 100000 --workers 8
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from aisef.clients.base import quote_command  # noqa: E402
from aisef.clients.synthetic import Script, Step, SyntheticClientAdapter  # noqa: E402
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.journal import JournalStore  # noqa: E402
from aisef.harness.observe import AGENT_RUN, EvidenceStore  # noqa: E402
from aisef.phases.implement import implement_story  # noqa: E402
from tests.hardening import model as M  # noqa: E402
from tests.test_retry_hygiene import SID, HygieneCase  # noqa: E402

RESULTS = ROOT / "closure-evidence/hardening/differential-results.json"

# ------------------------------------------------------------ the scenario vocabulary
# (kind, weight). Every kind has a deterministic real-kernel realisation AND a model event.
DEV = [("CHANGED", 30), ("CHANGED_RED", 8), ("CHANGED_ARTIFACT", 3), ("CHANGED_ORPHAN", 3), ("NOOP", 8), ("TIMEOUT", 4), ("CRASH", 4), ("RATE_LIMIT", 2),
       ("CONTEXT", 3), ("AUTH", 2), ("SCOPE_VIOLATION", 6), ("TRUNK_COMMIT", 1), ("ZERO_OUTPUT", 2),
       ("MAX_TURNS_WORK", 3), ("MAX_TURNS_UNTOUCHED", 3), ("BUDGET", 2)]
REV = [("PASS", 30), ("BLOCK", 7), ("BLOCK_OUTSIDE", 4), ("STUCK", 2), ("MALFORMED", 4), ("UNRUNNABLE", 5), ("MUTATE", 2),
       ("COMMIT", 2), ("BUDGET", 1), ("BLOCK_UNBOUND", 2)]
SEC = [("PASS", 30), ("BLOCK", 6), ("UNRUNNABLE", 4), ("MALFORMED", 3), ("BUDGET", 1)]

DEV_EVENT = {"CHANGED": "DEVELOP_CHANGED", "CHANGED_RED": "DEVELOP_CHANGED", "CHANGED_ARTIFACT": "DEVELOP_CHANGED",
             "CHANGED_ORPHAN": "DEVELOP_CHANGED", "NOOP": "DEVELOP_NOOP",
             "TIMEOUT": "DEVELOP_TIMEOUT", "CRASH": "DEVELOP_CRASH", "RATE_LIMIT": "DEVELOP_RATE_LIMIT",
             "CONTEXT": "DEVELOP_CONTEXT", "AUTH": "DEVELOP_AUTH", "SCOPE_VIOLATION": "DEVELOP_SCOPE_VIOLATION",
             "TRUNK_COMMIT": "DEVELOP_TRUNK_COMMIT", "ZERO_OUTPUT": "DEVELOP_ZERO_OUTPUT",
             "MAX_TURNS_WORK": "DEVELOP_MAX_TURNS_WORK", "MAX_TURNS_UNTOUCHED": "DEVELOP_MAX_TURNS_UNTOUCHED",
             "BUDGET": "DEVELOP_BUDGET"}
REV_EVENT = {"PASS": "REVIEW_PASS", "BLOCK": "REVIEW_BLOCK", "BLOCK_OUTSIDE": "REVIEW_BLOCK_OUTSIDE", "STUCK": "REVIEW_STUCK", "MALFORMED": "REVIEW_MALFORMED", "BLOCK_UNBOUND": "REVIEW_BLOCK_UNBOUND",
             "UNRUNNABLE": "REVIEW_UNRUNNABLE", "MUTATE": "REVIEW_MUTATE", "COMMIT": "REVIEW_MUTATE", "BUDGET": "REVIEW_BUDGET"}
SEC_EVENT = {"PASS": "SECURITY_PASS", "BLOCK": "SECURITY_BLOCK", "UNRUNNABLE": "SECURITY_UNRUNNABLE",
             "MALFORMED": "SECURITY_MALFORMED", "BUDGET": "SECURITY_BUDGET"}

IN_SCOPE = "ledgerlock/cli.py"
OUT_OF_SCOPE = "ledgerlock/ledger.py"


@dataclass
class Scenario:
    seed: int
    developer: list[str]
    review: list[str]
    security: list[str]
    test_tool_missing: bool = False
    max_retries: int = 1

    def summary(self) -> str:
        env = " test-tool-missing" if self.test_tool_missing else ""
        return f"dev={'/'.join(self.developer)} rev={'/'.join(self.review)} sec={'/'.join(self.security)} retries={self.max_retries}{env}"


def _pick(rng: random.Random, vocab, n: int) -> list[str]:
    kinds = [k for k, _ in vocab]
    weights = [w for _, w in vocab]
    return [rng.choices(kinds, weights=weights)[0] for _ in range(n)]


def generate(seed: int) -> Scenario:
    rng = random.Random(seed)
    return Scenario(seed, _pick(rng, DEV, rng.randint(1, 6)), _pick(rng, REV, rng.randint(1, 4)),
                    _pick(rng, SEC, rng.randint(1, 3)), test_tool_missing=rng.random() < 0.05,
                    max_retries=rng.choice([1, 2]))


def _green(n: int) -> dict[str, str]:
    return {IN_SCOPE: f"def main(argv=None):\n    return {n}\n"}


def _red(n: int) -> dict[str, str]:
    return {IN_SCOPE: f"def main(argv=None):\n    return {n}  # RED\n"}


def to_script(sc: Scenario) -> Script:
    dev = []
    for i, k in enumerate(sc.developer, 1):
        if k == "CHANGED":
            dev.append(Step("CHANGED", files=_green(i)))
        elif k == "CHANGED_RED":
            dev.append(Step("CHANGED", files=_red(i)))
        elif k == "CHANGED_ORPHAN":                 # F5: the session leaves a background process; the kernel must reap it
            dev.append(Step("CHANGED_ORPHAN", files=_green(i)))
        elif k == "CHANGED_ARTIFACT":               # F4: the session also leaves a tool artifact and a nested vendor tree —
            dev.append(Step("CHANGED", files={**_green(i), ".coverage": f"\x00{i}",   # VERIFIER-class paths, never a write
                                              "packages/web/node_modules/left-pad/index.js": "module.exports = 1\n"}))
        elif k == "SCOPE_VIOLATION":
            dev.append(Step("SCOPE_VIOLATION", files={**_green(i), OUT_OF_SCOPE: f"# reformatted {i}\n"}))
        elif k == "TRUNK_COMMIT":
            dev.append(Step("TRUNK_COMMIT", files={IN_SCOPE: f"# trunk {i}\n"}))
        elif k == "MAX_TURNS_WORK":
            dev.append(Step("MAX_TURNS", files=_green(i)))
        elif k == "MAX_TURNS_UNTOUCHED":
            dev.append(Step("MAX_TURNS"))
        else:
            dev.append(Step(k))
    rev = []
    for k in sc.review:
        if k in ("MUTATE", "COMMIT"):
            rev.append(Step(k, files={"ledgerlock/reviewer.py": "x = 2\n"}))
        elif k == "BLOCK":
            rev.append(Step("BLOCK", findings=[{"tag": "block", "file": IN_SCOPE, "line": 1,
                                                "why": "the exit code is wrong", "behavior_id": "FR-4"}]))
        elif k == "BLOCK_OUTSIDE":
            rev.append(Step("BLOCK", findings=[{"tag": "block", "file": OUT_OF_SCOPE, "line": 1,
                                                "why": "the ledger must reject a short row", "behavior_id": "FR-2"}]))
        else:
            rev.append(Step(k))
    sec = [Step(k) for k in sc.security]
    return Script(developer=dev, review=rev, security=sec)


# ------------------------------------------------------------ the observation both sides reduce to

@dataclass
class Observation:
    terminal: str                 # done | blocked:<reason class> | failed:<reason> | human:<reason> | crash:<Exc> | running
    developer_sessions: int
    review_executions: int
    security_executions: int
    quality_attempts: int
    infra_attempts: int
    candidates_frozen: int
    events: list[str] = field(default_factory=list)   # canonical stage/outcome stream (diagnostic, not compared)
    orphans_surviving: int = 0    # F5 / INV-L.1: processes a developer session left behind that outlived the story (model: 0)

    COMPARED = ("terminal", "developer_sessions", "review_executions", "security_executions", "quality_attempts",
                "infra_attempts", "candidates_frozen", "orphans_surviving")

    def diff(self, other: "Observation") -> list[str]:
        return [f"{f}: real={getattr(self, f)!r} model={getattr(other, f)!r}"
                for f in self.COMPARED if getattr(self, f) != getattr(other, f)]


# ------------------------------------------------------------ model side

class _Queue:
    """Exactly the synthetic client's `_next`: pop while more than one remains, then repeat the last."""

    def __init__(self, items):
        self.q = list(items)
        self.consumed = 0

    def next(self):
        self.consumed += 1
        return self.q.pop(0) if len(self.q) > 1 else self.q[0]


def model_run(sc: Scenario, max_steps: int = 80) -> Observation:
    k = M.Kernel(sc.seed)
    M.MAX_RETRIES_SAVED = getattr(M, "MAX_RETRIES_SAVED", M.MAX_RETRIES)
    dev, rev, sec = _Queue(sc.developer), _Queue(sc.review), _Queue(sc.security)
    tree_red = False
    old = M.MAX_RETRIES
    M.MAX_RETRIES = sc.max_retries
    try:
        for _ in range(max_steps):
            s = k.s
            if s.terminal or s.status == M.WAITING_HUMAN or s.stage in (M.MERGE, M.HUMAN):
                break
            if s.stage == M.DEVELOP:
                kind = dev.next()
                tree_red = kind == "CHANGED_RED" if kind in ("CHANGED", "CHANGED_RED", "CHANGED_ARTIFACT", "CHANGED_ORPHAN", "MAX_TURNS_WORK", "SCOPE_VIOLATION") else tree_red
                ev = DEV_EVENT[kind]
            elif s.stage == M.VERIFY:
                ev = "TEST_UNRUNNABLE" if sc.test_tool_missing else ("TEST_FAIL" if tree_red else "TEST_PASS")
            elif s.stage == M.REVIEW:
                kind = rev.next()
                ev = REV_EVENT[rev.next() if kind in ("MALFORMED", "BLOCK_UNBOUND") else kind]   # the retry consumes the next step
            elif s.stage == M.SECURITY:
                kind = sec.next()
                ev = SEC_EVENT[sec.next() if kind == "MALFORMED" else kind]
            elif s.stage == M.GATE:
                ev = "GATE_EVALUATE"
            else:
                break
            k.apply(ev)
    finally:
        M.MAX_RETRIES = old
    s = k.s
    if s.status in (M.VERIFIED, M.DONE):
        terminal = "done"
    elif s.status == M.BLOCKED:
        terminal = f"blocked:{s.terminal_reason}"
    elif s.status == M.FAILED:
        terminal = f"failed:{s.terminal_reason}"
    elif s.status == M.WAITING_HUMAN:
        terminal = f"human:{s.terminal_reason}"
    else:
        terminal = f"running:{s.stage}"
    return Observation(terminal, s.developer_sessions, s.review_executions, s.security_executions, s.quality_attempts,
                       s.infra_attempts, len(s.graded_candidates), [f"{e}->{o}" for e, o, _ in s.trace])


# ------------------------------------------------------------ real side

class _Case(HygieneCase):
    def runTest(self):
        pass

    def run_scenario(self, sc: Scenario):
        redcheck = self.project / "redcheck.py"
        redcheck.write_text("import pathlib, sys\n"
                            "sys.exit(1 if 'RED' in pathlib.Path('ledgerlock/cli.py').read_text(encoding='utf-8') else 0)\n",
                            encoding="utf-8")
        test_cmd = "aisef-no-such-test-runner-xyz" if sc.test_tool_missing else quote_command([sys.executable, str(redcheck)])
        client = SyntheticClientAdapter(to_script(sc))
        cfg = Config({**DEFAULTS, "tools.test": test_cmd, "tools.lint": "true", "run.max_retries": sc.max_retries})
        out = implement_story(self.story, project=self.project, workdir=self.work, artifact_root=self.artifacts,
                              client=client, config=cfg)
        return client, out


def _terminal_class(out, frozen: int = 0, max_retries: int = 1) -> str:
    """Classify the real kernel's terminal from TYPED facts only: `StoryOutcome.terminal` (the stage-outcome
    vocabulary, F2), the last attempt's flags and the two constant stage labels the kernel puts in front of an
    UNRUNNABLE terminal. No wording is read; an untyped terminal is a mismatch by construction."""
    from aisef.control.outcome import StageOutcome as SO
    from aisef.phases.implement import REVIEW_UNRUNNABLE, SECURITY_UNRUNNABLE
    if out.done:
        return "done"
    attempts = out.attempts
    last = attempts[-1] if attempts else None
    t, r = out.terminal, out.blocked_reason or ""
    if t == SO.ISOLATION_BREACH.value:
        return "blocked:isolation breach"
    if t == SO.AUTH_FAILURE.value:
        return "blocked:credential rejected"
    if t == SO.BUDGET.value:
        return "blocked:budget cap"
    if t == SO.PLAN_CONFLICT.value:
        return "human:plan conflict"
    if t == SO.QUALITY_BLOCK.value:
        return "failed:did not pass gate"
    if t == SO.UNRUNNABLE.value:
        return "blocked:REVIEW_UNRUNNABLE" if r.startswith(REVIEW_UNRUNNABLE) else (
            "blocked:SECURITY_UNRUNNABLE" if r.startswith(SECURITY_UNRUNNABLE) else f"blocked:UNRUNNABLE:{r[:60]}")
    if t == SO.NOOP.value:
        trailing = 0
        for a in reversed(attempts):
            if not a.noop:
                break
            trailing += 1
        if trailing >= 2:
            return "blocked:no-op: developer declined proven work twice" if frozen else "blocked:no-op: nothing to grade twice"
        return "blocked:no-op: budget exhausted"
    if t == SO.INFRA_FAILURE.value:
        return "failed:recurring infrastructure error"
    if t == SO.ENVIRONMENT_FAILURE.value:
        if last is not None and last.fatal:
            return "blocked:zero output: model cannot use tools"            # the only fatal environment exit in the vocabulary
        if last is not None and last.infra and not last.verify_only:
            return "failed:recurring infrastructure error"                  # developer sessions kept exiting on the environment
        return "blocked:environment: test tool unrunnable"                  # a tool stage that never ran
    return f"blocked:UNTYPED:{t or '-'}:{r[:70]}"


def real_run(sc: Scenario) -> Observation:
    case = _Case("runTest")
    case.setUp()
    try:
        try:
            client, out = case.run_scenario(sc)
        except Exception as e:  # noqa: BLE001 — a crash IS an observation (SS-12)
            return Observation(f"crash:{type(e).__name__}", 0, 0, 0, 0, 0, 0, [traceback.format_exc()[-400:]])
        frozen = {e.data.get("sha") for e in JournalStore(case.artifacts).read(SID).entries
                  if e.step == "candidate.frozen" and e.data.get("sha")}
        # the "nothing to grade" budget: infra cuts AND no-op sessions spend it (fatal exits end the story instead)
        infra = len([a for a in out.attempts if a.infra and not a.fatal])
        events = [f"{c.role}:{c.step}" for c in client.calls]
        events.append(out.summary().replace("\n", " | ")[:300])
        runs = [e.name for e in EvidenceStore(case.artifacts).read(SID).of(AGENT_RUN)]
        surviving = [p for p in client.orphans if p.poll() is None]       # F5: the attempt owns the process tree
        for p in surviving:                                                # never leak a sleeper into the next trace
            p.kill(); p.wait()
        return Observation(_terminal_class(out, len(frozen), sc.max_retries), client.develop_calls,
                           runs.count(f"{SID}-review"), runs.count(f"{SID}-security"),   # executions, not sessions
                           out.quality_attempts, infra, len(frozen), events, len(surviving))
    finally:
        case.tearDown()


# ------------------------------------------------------------ attribution of a mismatch to an OPEN defect
# Each rule: (defect id, predicate over the scenario). Emptied as families close (W0: KNOWN == {}).
# Removed: D-035 (F1, 2026-09-16 — the no-op decision reads a fresh verdict; the kernel agrees with the model).
KNOWN: dict = {
    # F2 (2026-09-16) removed SS-12, SS-13, SS-14, SS-15, SS-21, SS-57, SS-59: typed outcomes and stage-local retry
    # landed; the model and the kernel must now agree on every one of those scenarios.
}


def attribute(sc: Scenario) -> list[str]:
    return [d for d, pred in KNOWN.items() if pred(sc)]


def run_one(seed: int) -> dict:
    sc = generate(seed)
    real, model = real_run(sc), model_run(sc)
    diff = real.diff(model)
    return {"seed": seed, "scenario": sc.summary(), "diff": diff, "attributed": attribute(sc) if diff else [],
            "real": asdict(real), "model": asdict(model), "model_steps": len(model.events),
            "real_events": len(real.events) - 1}


def _worker(seeds: list[int]) -> list[dict]:
    out = []
    for i, s in enumerate(seeds, 1):
        out.append(run_one(s))
        if i % 250 == 0:                                     # Phase 12 watchdog: measurable progress per worker
            print(f"progress worker seeds={seeds[0]}.. done={i}/{len(seeds)}", file=sys.stderr, flush=True)
    return out


def run_many(traces: int, workers: int = 1, start: int = 0) -> dict:
    t0 = time.time()
    seeds = list(range(start, start + traces))
    if workers <= 1:
        rows = _worker(seeds)
    else:
        chunks = [seeds[i::workers] for i in range(workers)]
        rows = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for part in ex.map(_worker, chunks):
                rows.extend(part)
    rows.sort(key=lambda r: r["seed"])
    elapsed = time.time() - t0
    matched = [r for r in rows if not r["diff"]]
    attributed = Counter(a for r in rows if r["diff"] and r["attributed"] for a in r["attributed"][:1])
    unexplained = [r for r in rows if r["diff"] and not r["attributed"]]
    _rows = rows
    return {"traces": traces, "workers": workers, "elapsed_s": round(elapsed, 1),
            "traces_per_s": round(traces / elapsed, 2) if elapsed else None,
            "model_transitions": sum(r["model_steps"] for r in rows),
            "real_stage_events": sum(r["real_events"] for r in rows),
            "_rows": _rows,
            "matched": len(matched), "mismatched_attributed": dict(attributed),
            "unexplained_count": len(unexplained), "unexplained": unexplained[:100],
            "known_deviations": sorted(KNOWN), "vocabulary": {"developer": DEV, "review": REV, "security": SEC}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", type=int, default=200)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--out", default=str(RESULTS))
    ap.add_argument("--seed", type=int, help="run one seed verbosely")
    a = ap.parse_args(argv)
    if a.seed is not None:
        print(json.dumps(run_one(a.seed), ensure_ascii=False, indent=1))
        return 0
    res = run_many(a.traces, a.workers, a.start)
    rows = res.pop("_rows", [])
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if rows:                                                 # Phase 12 integrity: one compact record per trace, beside the summary
        with open(str(Path(a.out).with_suffix(".rows.jsonl")), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps({"seed": r["seed"], "scenario": r["scenario"], "diff": r["diff"],
                                     "real_terminal": r["real"]["terminal"], "model_terminal": r["model"]["terminal"],
                                     "model_events": r["model"]["events"], "real_events": r["real"]["events"][:-1],
                                     "counts": {k: r["real"][k] for k in ("developer_sessions", "review_executions", "security_executions",
                                                                          "quality_attempts", "infra_attempts", "candidates_frozen", "orphans_surviving")}},
                                    ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k not in ("unexplained", "vocabulary")}, ensure_ascii=False))
    for r in res["unexplained"][:15]:
        print("UNEXPLAINED", r["seed"], r["scenario"], r["diff"])
    return 1 if res["unexplained_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
