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
#: `delivery-experiment-1` is the ONE preregistered delivery run (owner rulings 'FINAL PLAN CORRECTION + DELIVERY RUN
#: PREREGISTRATION' and 'DELIVERY EXPERIMENT EXECUTION GUARD', 2026-10-02): the v1-aligned limits, and — fixed in
#: c2_delivery_experiment — the corrected plan, one fixed model route, and the owner's hard spend budget. `run` refuses
#: it unless the committed preregistration holds AND a verified ATTESTED preflight record is beside the run.
EXPERIMENT = "delivery-experiment-1"
PROFILES = {"qp-2.9": LIMITS, "v1-aligned": {**LIMITS, "DEVELOPER": 2}, EXPERIMENT: {**LIMITS, "DEVELOPER": 2}}
#: how often a running session's event stream is read against the budget
POLL_S = 5.0
PROJECT = frozenset({"ledgerlock", "tests"})
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
                      "contracts unchanged; the profile is named in the record. Under the profile `delivery-experiment-1` "
                      "(preregistered, DELIVERY-EXPERIMENT-1-PREREGISTRATION.json) the plan is PLAN-V2.2 CORRECTION 1, the "
                      "developer and the reviewer run on one fixed model route (no routing alias) that a preflight attested "
                      "before delivery was unlocked, the owner's hard spend budget (provider requests, turns, combined "
                      "input tokens, output plus reasoning tokens — preflight included) is re-derived from the journal "
                      "and the session streams and ends the experiment when reached, and the final main is put to all 59 "
                      "ProductProofSpecs and to the V1 independent acceptance oracle. A delivery verdict is PASS only when "
                      "every story of the plan committed in the journal, the budget was not reached and every revision "
                      "the run names is preserved.",
                   4: "H-PROMPT-002: attempt 3's prompts carried the V1-era epics prose as 'context only'; STORY-01-05's "
                      "prescribed a four-element delete (`(\"delete\", key, rid, ts)`) against the requirements' five-field "
                      "batch tuples (§5), it was implemented and kept, and ProductProof refuted S-4.4-a and S-D3-05-01-1 "
                      "three times each. The prompt now holds the current plan's requirement clauses, the approved "
                      "contracts' subjects and the plan stories it depends on, and no legacy text. H-RETRY-001: a retry "
                      "prompt named a failed proof by its code and clause only; it now states the evidence the journal "
                      "holds — criterion, role, requirement and clause, contract, spec, probe, subject, candidate, probe "
                      "status and verdict against the expectation, the verifier's agreement, the typed failure and owner, "
                      "the cited journal seqs — and, for a developer-owned refutation, that the candidate remains refuted and "
                      "the hidden proof stimulus is not disclosed (PROBE-DIAGNOSTIC-GAP-001: the journal records no "
                      "observation detail, and none is invented). Plan, specs, contracts, kernel and budget unchanged."}
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


def holds(repo, path: str) -> bool:
    """Whether main holds `path` now."""
    from aisef2.orchestrate.workspace import git
    return git(repo, "cat-file", "-e", f"main:{path}").returncode == 0


def regression_tests(repo, story: str, delivered: dict[str, bool]) -> tuple[str, ...]:
    """The regression set of `story`. `delivered`: each story committed before it -> whether main held that story's test
    file when it committed (`holds`, asked at the commit). A story that committed without a developer call (nothing left
    to introduce: K-PRESAT-001, K-NOWORK-001) produced no test file, and naming a file nobody was asked to write fails
    the next developer's adequacy (TESTS_INADEQUATE, a correct story rolled back: H-REGRESSION-001). ONLY such a file is
    left out — one that was never produced and that main does not hold. A file that was produced stays named whether or
    not main still holds it (if it is gone, that is the kernel's typed failure to state, not the harness's to hide), and
    so does a file main holds now. With none, the story's own tests, as for the first story."""
    named = tuple(test_path(s) for s, produced in delivered.items() if produced or holds(repo, test_path(s)))
    return named or (test_path(story),)


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


def obligation_facts(plan, requirements: str) -> dict[str, dict]:
    """criterion -> the PUBLIC facts of its obligation: the plan's story and role, the requirement and its section, the
    clause and its text, the approved contract, its ProductProofSpec, probe, candidate expectation and product subject.
    Never a probe input: what the developer may be told on a retry (H-RETRY-001)."""
    from validation.qualification import p10_contracts as aid
    compiled = _compiled()
    key = {s.id: k for k, s in compiled.items()}
    text = {c["id"]: c["clause"] for c in aid.CLAUSES}
    secs = sections(requirements)
    out = {}
    for o in plan.obligations:
        spec, t = compiled[key[o.product_proof_spec_id]], aid.SPECS[key[o.product_proof_spec_id]]
        out[o.criterion_id] = {"story": o.story_id, "criterion": o.criterion_id, "role": o.role.value, "requirement": t["requirement"],
                               "section": secs.get(t["requirement"].removeprefix("R-"), ""), "clause": t["clause"],
                               "clause_text": text.get(t["clause"], t["clause"]), "contract": spec.contract_id, "spec": spec.id,
                               "probe": spec.probe_id, "candidate_expectation": spec.candidate_expectation.value,
                               "subject": subject_text(t["kind"], t["locator"])}
    return out


#: H-RETRY-001: what a developer-owned refutation adds, and no more — the journal records no observation detail
#: (PROBE-DIAGNOSTIC-GAP-001), so none is told
REFUTED = ("The candidate remains {verdict} for this approved contract and the independent verifier agrees. Inspect the "
           "implementation against that requirement clause. The hidden proof stimulus is not disclosed.")


def retry_feedback(events, story_id: str, facts: dict[str, dict]) -> str:
    """H-RETRY-001: the failures the kernel observed in `story_id`, each with the harness evidence that decided it —
    built only from journal events `(seq, type, data)` and the public facts of the obligations (`obligation_facts`).

    A failed proof names its criterion, role, requirement and clause, contract, spec, probe and subject, the candidate,
    the probe status and verdict against the expectation, whether the independent verifier agrees, the typed failure
    and owner, and the journal seqs it rests on: the two probe records (the criterion's last two before the proof — the
    order proof.prove journals them in), the proof and the failure. Any other failure is its code, owner and the
    kernel's typed detail. Nothing else: no probe input, stimulus, step, exception or record detail — the journal holds
    no observation, so none is told. It is a pure function of the journal: prompt text, never journaled, never read by
    the kernel — owner, retryability, budget, verdict and gate decisions are the kernel's, from the same journal."""
    events = [(int(q), str(t), d) for q, t, d in events]
    rows = []
    for seq, kind, data in events:
        if kind != "failure/observed" or data.get("story_id") != story_id:
            continue
        code, owner, detail = data.get("code"), data.get("owner"), str(data.get("detail", ""))
        m = re.match(r"proof of (\S+): ", detail)
        f = facts.get(m.group(1)) if m else None
        about = [e for e in events if f and e[2].get("story_id") == story_id and e[2].get("criterion_id") == f["criterion"]]
        proof = next((e for e in reversed(about) if e[0] < seq and e[1] == "proof/verified"), None)
        if proof is None:
            rows.append(f"- {code} (owner {owner}): {detail}")
            continue
        recs = [e for e in about if e[0] < proof[0] and e[1] == "probe/evaluated"][-2:]
        executed = len(recs) == 2 and all("behavior_verdict" in ((r[2].get("record") or {}).get("result") or {}) for r in recs)
        p = proof[2]
        line = (f"- {code} (owner {owner}) — {story_id}, criterion {f['criterion']} [{f['role']}]: {f['requirement']} "
                f"(docs/requirements.md {f['section']}), clause {f['clause']}: {f['clause_text']}\n"
                f"  contract {f['contract']}, ProductProofSpec {f['spec']}, probe {f['probe']}, subject {f['subject']}; candidate "
                f"{p.get('candidate')}: probe status {'EXECUTED' if executed else 'not EXECUTED'}"
                + (f", verdict {p.get('verdict')} (expected {f['candidate_expectation']})" if executed else "")
                + f", the independent verifier {'agrees' if p.get('agreement') else 'disagrees'}. Evidence: journal seq "
                f"{', '.join(str(r[0]) for r in recs)} (the probe records), {proof[0]} (the proof), {seq} (this failure).")
        if executed and p.get("agreement") and owner == "DEVELOPER" and p.get("verdict") not in (None, f["candidate_expectation"]):
            line += "\n  " + REFUTED.format(verdict=p["verdict"])
        rows.append(line)
    return "\n".join(rows)


def prompts(plan, requirements: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """The developer's task per plan story, from the CURRENT authoritative sources only: the requirements (in the
    repository), the requirement clause of each obligation the story must deliver, preserve or verify, the product
    subjects those obligations name (the approved contracts), and the plan stories it depends on.

    H-PROMPT-002 (measured on attempt 3): the V1-era epics prose these prompts carried until attempt 3 as 'context only'
    prescribed execution shapes — `Ledger.append(("put", key, value, rid, ts))` (or `("delete", key, rid, ts)`) in
    STORY-01-05's section — that contradict the requirements' batch tuples (§5: `(op, key, value, rid, ts)`); STORY-01-05's
    developer implemented the four-element delete and every later candidate kept it. The prose is not mechanically
    separable into safe and unsafe parts, so none of it is used: no legacy story text, title, example, signature or
    tuple layout, and nothing put in its place. The specs' probes, stimuli, inputs and expectations are not shown
    either: the proof is independent of the developer."""
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
        after = [s for s in sorted(graph.get(story, ())) if any(o.story_id == s for o in plan.obligations)]
        clauses[story] = "\n".join(dict.fromkeys(lines))
        subjects = sorted({subject_text(aid.SPECS[specs[o.product_proof_spec_id]]["kind"], aid.SPECS[specs[o.product_proof_spec_id]]["locator"])
                           for o in plan.obligations if o.story_id == story})
        out[story] = (
            f"You are the developer of LedgerLock story {story}. LedgerLock is a small Python library and CLI; "
            "docs/requirements.md in this repository is the authoritative specification. Implement this story in this "
            "repository (the package `ledgerlock/`, Python standard library only), working only inside this directory.\n\n"
            "What this story must deliver is defined by the requirement clauses listed below and by docs/requirements.md, "
            "and by nothing else.\n\n"
            + (f"The stories of this plan it depends on: {', '.join(after)}.\n\n" if after else "")
            + "When you finish, each of the following requirement clauses is verified independently against the "
              "requirements (INTRODUCE: this story makes it true; PRESERVE: it must stay true"
            + ("; VERIFY: it must be true when this story is done" if any("[VERIFY]" in x for x in lines) else "") + "):\n"
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

def _event_type(e) -> str:
    return e["type"] if isinstance(e, dict) else e.type


class Budget:
    """An experiment's HARD spend ceilings, judged on the evidence: this object keeps no count of its own. What was
    spent is re-derived, every time it is asked, from what is recorded — `base` (the preflight's accounting record,
    made before the delivery journal existed), the journal's `provider/request` events (`requests`), and the event
    streams of the sessions that were started (one file each under `logs`, the same files the record hashes).

    A provider request is one model session the harness starts (the journal's `provider/request`) or one request of
    the preflight; a turn is a finished step of a session; input counts prompt and cached tokens together and output
    counts completion and reasoning tokens together, as the client reports them per finished step.

    Anything that cannot be accounted for ends the experiment like a reached ceiling: a session started that the
    journal does not record, a finished step without its tokens, a session that started and finished no step."""
    KEYS = ("provider_requests", "turns", "input_tokens", "output_tokens")

    def __init__(self, limits: dict[str, int], base: dict[str, int], logs: pathlib.Path, requests=lambda: 0) -> None:
        if sorted(limits) != sorted(self.KEYS) or sorted(k for k in base if k in self.KEYS) != sorted(self.KEYS):
            raise ValueError("a budget has the four ceilings, and a base that accounts for each of them")
        self.limits, self.base, self.logs, self.requests = dict(limits), {k: int(base[k]) for k in self.KEYS}, logs, requests

    def spend(self, live: pathlib.Path | None = None) -> dict:
        """What the evidence shows spent so far. `live` is the stream of the session running now (it may have no
        finished step yet); every other stream is a finished session's."""
        logs = sorted(self.logs.glob("*.jsonl")) if self.logs.is_dir() else []
        seen = {p: read_session(p) for p in logs}
        recorded = int(self.requests())
        unaccounted = [f"{len(logs)} sessions were started but {recorded} provider requests are recorded"] if len(logs) > recorded else []
        for p, x in seen.items():
            if x["steps_without_tokens"]:
                unaccounted.append(f"{p.name}: {x['steps_without_tokens']} finished steps report no tokens")
            if p != live and not x["turns"]:
                unaccounted.append(f"{p.name}: a session that started finished no step — what it sent is unknown")
        return {"provider_requests": self.base["provider_requests"] + recorded,
                "turns": self.base["turns"] + sum(x["turns"] for x in seen.values()),
                "input_tokens": self.base["input_tokens"] + sum(x["tokens"]["input"] for x in seen.values()),
                "output_tokens": self.base["output_tokens"] + sum(x["tokens"]["output"] for x in seen.values()),
                "sessions_started": len(logs), "requests_recorded": recorded, "unaccounted": unaccounted}

    def reached(self, live: pathlib.Path | None = None, in_progress: bool = False) -> str | None:
        """Why the experiment must end now — a ceiling reached or exceeded, or spend that cannot be accounted for — or
        None. While a request is in progress (it is already recorded) the request ceiling ends the experiment only
        when EXCEEDED: the request that reaches it may run, and nothing after it."""
        spent = self.spend(live)
        if spent["unaccounted"]:
            return "unaccounted: " + "; ".join(spent["unaccounted"])
        for k in self.KEYS:
            if spent[k] > self.limits[k] or (spent[k] == self.limits[k] and not (in_progress and k == "provider_requests")):
                return f"max_{k}: {spent[k]} of {self.limits[k]}"
        return None

    def account(self) -> dict:
        return {"limits": dict(self.limits), "preflight": dict(self.base), "spent": self.spend(), "reached": self.reached(),
                "derived_from": "the preflight accounting record, the journal's provider/request events and the session streams; no counter is kept",
                "limitation": ACCOUNTING_LIMITATION}


#: what the telemetry cannot show (recorded with every account of the budget)
ACCOUNTING_LIMITATION = (
    "spend is what the client reports per finished step. An HTTP request that finishes no step is not in the telemetry — a "
    "client-internal retry, a failed request, the request in flight when a stop is issued — so its tokens cannot be counted; a "
    "stop is issued at the first reading (every 5 s) that shows a ceiling reached, so the totals can pass a ceiling by the steps "
    "finished since the reading before. Input is one combined number (prompt + cache read + cache write): the owner's ceiling "
    "is combined and no separate fresh/cached limit exists. The preflight's chat probes report prompt_tokens and "
    "completion_tokens only, counted as input and output.")


def read_session(log: pathlib.Path) -> dict:
    """What a session's event stream says so far: its text, its error, its turns (finished steps), its tokens, and how
    many finished steps carry no token report (spend that cannot be accounted for)."""
    text, error, turns, tokens, blind = [], None, 0, {"input": 0, "output": 0}, 0
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
            tk = part.get("tokens")
            if not isinstance(tk, dict) or not all(isinstance(tk.get(k), int) for k in ("input", "output")):
                blind += 1
                continue
            cache = tk.get("cache") or {}
            tokens["input"] += tk["input"] + int(cache.get("read") or 0) + int(cache.get("write") or 0)
            tokens["output"] += tk["output"] + int(tk.get("reasoning") or 0)
    return {"error": error, "text": "".join(text), "turns": turns, "tokens": tokens, "steps_without_tokens": blind}


def wait_within(r, log: pathlib.Path, timeout_s: float, budget: Budget | None, turn_cap: int | None = None) -> tuple[int | None, str | None]:
    """A running session's exit status — or None with why it was stopped, or None with nothing: it ran out of time.
    Between waits the budget is re-derived from the evidence, this session's stream included; `turn_cap` is a cap on
    this one session (the preflight's smoke probe has one). `r` is the session's process range (anything with `wait`)."""
    deadline, code, stopped = time.monotonic() + timeout_s, None, None
    while code is None and not stopped and time.monotonic() < deadline:
        code = r.wait(min(POLL_S, max(0.0, deadline - time.monotonic())))
        if code is None:
            stopped = budget.reached(log, in_progress=True) if budget else None
            if not stopped and turn_cap is not None and read_session(log)["turns"] >= turn_cap:
                stopped = f"session turn cap: {turn_cap} turns"
    return code, stopped


def opencode_session(name: str, prompt: str, cwd: str, log: pathlib.Path, timeout_s: float, *, model: str | None = None,
                     env: dict | None = None, budget: Budget | None = None, turn_cap: int | None = None) -> dict:
    """One `opencode run --format json` session inside a V2 process range (the kernel's own OS-owned range: every
    process it starts ends with it); the event stream goes to `log`. With `model` the route is given to the client
    explicitly (and the session titled, so no second model names it). With `budget` nothing starts when the evidence
    shows the budget reached or spend unaccounted — or when `log` exists, which would overwrite a session's evidence —
    and the stream is read while the session runs: the range is released when the budget is reached. A session that
    is not started leaves no stream."""
    from aisef2.runtime.process_range import ProcessRange
    exe = shutil.which("opencode")
    started = time.monotonic()
    code, stopped = None, None
    if budget:
        stopped = f"{log.name} exists: a session's evidence is never overwritten" if log.exists() else budget.reached(in_progress=True)
    not_started = bool(stopped)
    if not not_started:
        argv = [exe, "run", "--format", "json", *(["--model", model, "--title", name] if model else []), "--dir", cwd, prompt]
        with log.open("w", encoding="utf-8") as fh:
            r = ProcessRange(name, argv, cwd=cwd, env=env, output=fh)
            r.start()
            try:
                code, stopped = wait_within(r, log, timeout_s, budget, turn_cap)
            finally:
                r.release()
    seen = read_session(log) if not not_started else {"error": None, "text": "", "turns": 0, "tokens": {"input": 0, "output": 0}}
    return {"exit": code, "timed_out": code is None and not stopped, "stopped": stopped, "started": not not_started,
            "error": stopped if not_started else seen["error"], "text": seen["text"], "turns": seen["turns"], "tokens": seen["tokens"],
            "seconds": round(time.monotonic() - started, 1), "log": None if not_started else log.name,
            "log_sha256": None if not_started else _sha(log.read_bytes())}


class OpenCodeDeveloper:
    def __init__(self, run, prompts: dict[str, str], logs: pathlib.Path, facts: dict[str, dict] | None = None,
                 session_kw: dict | None = None) -> None:
        self.run, self.prompts, self.logs, self.sessions, self.facts = run, prompts, logs, [], facts or {}
        self.session_kw = session_kw or {}      # a preregistered run's fixed model, client environment and budget

    def feedback(self, story_id: str) -> str:
        """H-RETRY-001: `retry_feedback` over this run's journal."""
        return retry_feedback(((e.seq, e.type, e.data) for e in self.run.events), story_id, self.facts)

    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import Implemented, ProviderOutage
        from aisef2.orchestrate.workspace import commit_all, git
        from validation.qualification.q5 import _story_context
        attempt, prior = _story_context(self.run, story_id)
        prompt = self.prompts[story_id] + (f"\n\nA previous attempt of this story was not accepted; the kernel observed:\n"
                                           f"{self.feedback(story_id)}\nFix the implementation." if prior else "")
        parent = git(checkout, "rev-parse", "HEAD").stdout.strip()
        s = opencode_session(f"developer {story_id}", prompt, checkout, self.logs / f"{story_id}.developer.{attempt}.jsonl", DEV_TIMEOUT_S,
                             **self.session_kw)
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
        return Implemented(O.COMPLETED, sha, f"opencode exit {s['exit']}, {s['turns']} turns" + (f", {s['stopped']}" if s["stopped"] else ""))


class OpenCodeReviewer:
    PROMPT = ("Review the implementation of LedgerLock story {story} in this read-only checkout against docs/requirements.md "
              "and these clauses:\n{clauses}\nDo not modify any file. Answer with ONLY one JSON object: "
              '{{"findings": [{{"id": "short-id", "blocking": true or false, "summary": "one line"}}]}}')

    def __init__(self, run, clauses: dict[str, str], logs: pathlib.Path, session_kw: dict | None = None) -> None:
        self.run, self.clauses, self.logs, self.sessions, self.session_kw = run, clauses, logs, [], session_kw or {}

    def review(self, scope, criteria: tuple[str, ...]):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import Finding, ProviderOutage, Reviewed
        from validation.qualification.q5 import _story_context
        attempt, _ = _story_context(self.run, scope.story_id)
        prompt = self.PROMPT.format(story=scope.story_id, clauses=self.clauses[scope.story_id])
        s = opencode_session(f"reviewer {scope.story_id}", prompt, scope.root, self.logs / f"{scope.story_id}.reviewer.{attempt}.jsonl",
                             REVIEW_TIMEOUT_S, **self.session_kw)
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


#: the keys under which the journal names a revision (story/begin and story/admitted `parent`, proof/verified
#: `candidate`, story/commit and run/spec-resolved `revision`, probe/evaluated `record.revision`)
REVISION_KEYS = ("revision", "candidate", "parent")


def run_shas(events: list[dict], sessions: list[dict], final: str | None) -> list[str]:
    """Every revision the run's records name: final main, each session's candidate, and every revision the journal
    cites wherever it cites one — story parents, proved candidates, committed revisions, the revision of every probe
    evaluation, the baseline. The objects an inspection or the independent acceptance oracle needs afterwards."""
    shas = {final} | {s.get("candidate") for s in sessions}

    def walk(o) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in REVISION_KEYS and isinstance(v, str):
                    shas.add(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for e in events:
        walk(e["data"])
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


def runspec_inputs(plan, profile: str, oc: dict, fixed: dict | None = None, preflight: dict | None = None) -> tuple[list, dict, str]:
    """The capabilities and the settings a run's RunSpec binds, and the kernel digest. `fixed` is a preregistered
    experiment (c2_delivery_experiment.fixed): its allowed model identity is the developer's and the reviewer's
    capability, and its budget, kernel commit and preflight shape are settings — so the RunSpec hash binds them.

    Without `preflight` this is the experiment's TEMPLATE: the model capability is OPAQUE, carrying the identity the
    preflight is allowed to find. With `preflight` — the observable fields a successful preflight measured — it is the
    RESOLVED RunSpec: the model capability is ATTESTED (the kernel's own grade, RFC §23: provider, endpoint, declared
    model, route, client, deployment and the fingerprint of those fields), and the template's hash is one of its
    settings. The fingerprint is a drift detector, not a claim about model weights."""
    from aisef2.arch.enums import Enforcement
    from aisef2.probe import catalog
    from aisef2.runtime.capability import attested, opaque, verified
    from aisef2.runtime.runspec import resolve
    from validation.qualification import q4
    kernel = q4._over(q4._file_digests(("aisef2",)))
    ruff = shutil.which("ruff")
    scanner = opaque("scanner", Enforcement.PARTIAL, tool="ruff", mode="lint as an informational scanner")
    if not fixed:
        model = {"client": "opencode", "route": str(oc["declared_route"]), "version": str(oc["version"])}
        models = [opaque(name, Enforcement.PARTIAL, **model) for name in ("developer", "reviewer")]
    else:
        if ruff:        # the binary the scanner stage executes, by its digest
            scanner = verified("scanner", pathlib.Path(ruff), Enforcement.PARTIAL, tool="ruff", mode="lint as an informational scanner")
        if preflight is None:
            models = [opaque(name, Enforcement.PARTIAL, **fixed["identity"]) for name in ("developer", "reviewer")]
        else:
            # the deployment is bound only when the provider exposed one (the kernel's own optional field); never made up
            models = [attested(name, preflight=preflight, enforcement=Enforcement.PARTIAL, deployment=fixed.get("deployment"), **fixed["identity"])
                      for name in ("developer", "reviewer")]
    caps = [verified("kernel", kernel.encode(), Enforcement.FULL, tree=C.git("rev-parse", "HEAD:aisef2")),
            verified("python", pathlib.Path(sys.executable), Enforcement.PARTIAL, version=platform.python_version()),
            verified("git", pathlib.Path(shutil.which("git")), Enforcement.PARTIAL),
            *[verified(e.probe_id, e.probe_digest.encode(), Enforcement.PARTIAL) for e in catalog.CATALOG if e.active],
            *models, scanner]
    layers = {"workload": {"value": "LedgerLock", "layer": "c2-p9"}, "benchmark_class": {"value": P10.BENCHMARK_CLASS, "layer": "c2-p9"},
              "plan_hash": {"value": plan.plan_hash, "layer": "plan"}, "requirements_sha256": {"value": P10.REQUIREMENTS_SHA256, "layer": "workload"},
              "limits": {"value": PROFILES[profile], "layer": f"c2-p9 profile {profile}"}}
    if fixed:
        layers.update({k: {"value": fixed[k], "layer": "preregistration"} for k in
                       ("experiment", "attempt", "harness", "kernel_commit", "budget", "max_turns_per_session", "preflight_shape",
                        "developer_timeout_s", "reviewer_timeout_s") if k in fixed})
        if preflight is not None:
            template = runspec_inputs(plan, profile, oc, fixed)
            layers["preregistered_template_hash"] = {"value": resolve(template[0], template[1], plan.baseline).runspec_hash, "layer": "preregistration"}
    return caps, layers, kernel


def run(out_dir: pathlib.Path, *, preserve_to: pathlib.Path, profile: str = "qp-2.9") -> dict:
    from aisef2.arch.enums import ControlProjection, Enforcement, Owner
    from aisef2.orchestrate import story_runner as sr
    from aisef2.orchestrate.quality import TestsPolicy
    from aisef2.orchestrate.workspace import GitMerger, GitWorkspace, git
    from aisef2.probe import catalog
    from aisef2.probe.protocol import ExecutionEnv
    from aisef2.product.contract import plain
    from aisef2.quality import test_execution as te
    from aisef2.runtime.run_scope import RunScope
    from aisef2.runtime.runspec import resolve
    from validation.qualification import p5_acceptance as pa
    from validation.qualification import p10_contracts as aid
    started = time.time()
    exp = session_kw = budget = None
    if profile == EXPERIMENT:
        # THE GATE, inside the runner (the run script is not the enforcement boundary): nothing below can reach a
        # provider unless the committed preregistration holds on this tree and this machine AND the attempt holds a
        # verified ATTESTED preflight record bound to this preregistration, plan, kernel, route, model, client,
        # enforcement and experiment. A refusal makes no provider call.
        from validation.qualification import c2_delivery_experiment as dx
        exp = dx.require_unlocked(out_dir)
    base = P10.ledgerlock_baseline()
    if not base.get("present") or not base.get("requirements_match_frozen"):
        raise SystemExit(f"the LedgerLock workload is not where the freeze says or its requirements changed: {base}")
    oc = P10.opencode_identity()
    if exp:
        plan = exp["plan"]
    else:
        plan = aid.build()["plan"]
        if plan.plan_hash != pa.ACCEPTED["plan_hash"]:
            raise SystemExit("the plan is not the owner-approved PLAN-V2.2")
    if plan.baseline != base["baseline"]:
        raise SystemExit("the plan is not at the workload's baseline")
    specs = {s.id: s for s in _compiled().values()}
    requirements_md = subprocess.run(["git", "-C", str(P10.LEDGERLOCK_REPO), "show", f"{P10.LEDGERLOCK_PLAN_COMMIT}:docs/requirements.md"],
                                     capture_output=True, encoding="utf-8", check=True).stdout
    tasks, clauses, _ = prompts(plan, requirements_md)
    facts = obligation_facts(plan, requirements_md)
    caps, layers, kernel = runspec_inputs(plan, profile, oc, exp, exp["preflight_fields"] if exp else None)
    if exp and resolve(caps, layers, base["baseline"]).runspec_hash != exp["resolved_runspec_hash"]:
        raise SystemExit("REFUSED: this run's RunSpec is not the one the attestation resolved")     # the journal binds this hash
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
        if exp:     # the budget reads the journal, the session streams and the preflight's accounting — it counts nothing itself
            budget = Budget(exp["budget"], exp["preflight_accounting"], logs,
                            lambda: sum(1 for e in run_.events if e.type == "provider/request"))
            # a session at its own turn cap is stopped (what it changed is still judged by the proofs); the experiment goes on
            session_kw = {"model": exp["route"], "env": dx.client_env(), "budget": budget, "turn_cap": exp["max_turns_per_session"]}
        dev, rev = OpenCodeDeveloper(run_, tasks, logs, facts, session_kw), OpenCodeReviewer(run_, clauses, logs, session_kw)
        adapters = sr.Adapters(dev, rev, RuffScanner(), merger, ws)
        factories = {e.probe_id: (lambda on_range, scratch, f=e.factory: f(on_range=on_range, scratch=scratch)) for e in catalog.CATALOG}
        env = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)
        limits = {Owner[k]: v for k, v in PROFILES[profile].items()}
        delivered: dict[str, bool] = {}     # committed story -> main held its test file when it committed
        for story in order(plan, aid.story_graph()):
            why = budget.reached() if budget else None
            if why:      # a ceiling reached, or spend unaccounted: the experiment has ended — nothing more starts
                results[story] = [f"NOT_RUN: {why}"]
                continue
            inputs = sr.StoryInputs(specs, factories, env, te.DeveloperTests(story, (test_path(story),)),
                                    te.DeveloperTests(story, regression_tests(repo, story, delivered)),
                                    te.Dependencies(frozenset(), PROJECT), te.UNITTEST)
            try:
                r = sr.run_story(run_, plan, story, inputs, adapters, sr.Policy(limits, TestsPolicy(True), tool_timeout_s=120))
                results[story] = [a.outcome for a in r.attempts]
                if results[story][-1:] == ["COMMIT"]:
                    delivered[story] = holds(repo, test_path(story))
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
            cited = events or ([{"data": plain(e.data)} for e in run_.events] if "run_" in locals() else [])    # also when the run broke
            preserved = preserve(repo_at, preserve_to, head, run_shas(cited, sessions_now, head))
        except Exception as e:  # noqa: BLE001 — a failed preservation keeps the directory; it never loses the run
            preserved = {"path": str(preserve_to), "error": f"{type(e).__name__}: {e}"[:500], "missing": ["<not preserved>"]}
        if may_remove(preserved):
            shutil.rmtree(tmp, ignore_errors=True)
            preserved["temporary_directory"] = "removed after the copy was checked"
        else:
            preserved["temporary_directory"] = f"KEPT at {tmp}: the copy does not hold the whole result"
    return {"started": started, "results": results, "errors": errors, "events": events, "state": state,
            "run_identity": run_id, "final_main": final, "preserved": preserved, "profile": profile,
            "experiment": exp, "budget": budget.account() if budget else None,
            "baseline": base, "oc": oc, "plan": plan, "specs": specs, "tasks": tasks,
            "sessions": (dev.sessions if dev else []) + (rev.sessions if rev else []), "caps": caps, "layers": layers, "kernel": kernel}


def record(out_dir: pathlib.Path, m: dict) -> dict:
    from aisef2.runtime.runspec import resolve
    from validation.qualification import p5_acceptance as pa
    from validation.qualification import p10_contracts as aid
    plan, events, exp = m["plan"], m["events"], m.get("experiment")
    kernel_commit, kernel_tree = (exp["kernel_commit"], exp["kernel_tree"]) if exp else (C.SEMANTIC_CANDIDATE, C.KERNEL_TREE)
    roles = {o.criterion_id: o.role.value for o in plan.obligations}
    delivery = P10.delivery_verdict_of(events, plan_admitted=True)
    last = {}
    for e in events:
        if e["type"] in ("story/commit", "story/rollback", "story/retry"):
            last[e["data"]["story_id"]] = e["type"]
    # a story is delivered when the harness saw it commit AND the journal's last outcome for it is its commit: a story
    # absent from the journal is not a successful story
    committed = {s for s, v in m["results"].items() if v[-1:] == ["COMMIT"] and last.get(s) == "story/commit"}
    not_committed = sorted({o.story_id for o in plan.obligations} - committed)
    budget = m.get("budget")
    blocks_pass = ([f"{len(not_committed)} of the plan's stories did not commit"] if not_committed else []) + \
                  ([f"the budget ended the experiment: {budget['reached']}"] if budget and budget["reached"] else []) + \
                  (["the run's revisions are not all preserved"] if exp and not may_remove(m["preserved"]) else [])
    if delivery == "PASS" and blocks_pass:
        delivery = "FAIL"
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
        record=("AISEF V2 — DELIVERY EXPERIMENT 1: ONE PREREGISTERED LEDGERLOCK RUN (DEVELOPMENT / REGRESSION BENCHMARK ONLY)" if exp else
                "AISEF V2 — CYCLE-2 QP-2.9 LEDGERLOCK REGRESSION (DEVELOPMENT / REGRESSION BENCHMARK ONLY)"), rung="C2-P9 / QP-2.9",
        authority=(exp["authority"] if exp else
                   "owner rulings 2026-09-30 A ('C2-P9 / QP-2.9 — LEDGERLOCK REGRESSION') and B (QP-2.9: execute the approved plan model)"),
        preregistration=exp["preregistration"] if exp else None,
        written=C.now(), purpose="does the Cycle-2 framework execute more of the known workload correctly? — not: how would AISEF perform on unseen projects",
        semantic_candidate=kernel_commit, aisef2_tree=kernel_tree, head_kernel_tree=C.git("rev-parse", "HEAD:aisef2"),
        repository_execution_commit=C.git("rev-parse", "HEAD"), harness={"path": "validation/qualification/c2_p9.py", "sha256": C.lf_sha(HERE / "c2_p9.py")},
        workload={"id": "LedgerLock", "benchmark_class": P10.BENCHMARK_CLASS, "repository": m["baseline"], "requirements_sha256": P10.REQUIREMENTS_SHA256,
                  "final_main": m["final_main"], "repository_written": False, "preserved": m["preserved"]},
        plan_identity={"id": plan.id, "plan_hash": plan.plan_hash, "baseline": plan.baseline, "stories": len({o.story_id for o in plan.obligations}),
                       "obligations": len(plan.obligations), "execution_order": order(plan, aid.story_graph()), "replanned": False, "stories_split": False,
                       "correction": exp["plan_correction"] if exp else None},
        approvals={"record": pa.APPROVALS_REL, "count": len(pa.load_approvals()), "approver": pa.OWNER},
        execution_profile={"source": "p10.runspec_for (Cycle-1 P10 profile): OpenCode developer and reviewer on the declared route, ruff scanner, "
                                     f"the limits of profile {m['profile']}",
                           "profile": m["profile"], "developer_attempts_per_story": PROFILES[m["profile"]]["DEVELOPER"] + 1,
                           "runspec_hash": spec.runspec_hash, "aggregate_min_grade": spec.aggregate_min_grade.value, "limits": PROFILES[m["profile"]],
                           "capabilities": [{"name": c.name, "grade": c.grade.value, "enforcement": c.enforcement.value} for c in spec.capabilities],
                           "model": m["oc"], "kernel_digest": m["kernel"],
                           "fixed_model": {k: exp[k] for k in ("route", "resolved_model", "route_kind")} if exp else None,
                           "attestation": exp["attestation"] if exp else None, "budget": budget,
                           "max_turns_per_session": exp["max_turns_per_session"] if exp else None,
                           "sessions_stopped_at_the_session_cap": sum(1 for s in m["sessions"] if str(s.get("stopped") or "").startswith("session turn cap")),
                           "grade_note": ("one fixed model route, given to the client explicitly, ATTESTED by the preflight beside this record "
                                          "before delivery was unlocked; the fingerprint is a drift detector, not a claim about model weights") if exp else
                                         "the route is a routing alias: OPAQUE, which bars sealing and nothing else here; no model identity is inferred from it"},
        run_identity=m["run_identity"], cohort_state="DEVELOPMENT", benchmark_class=P10.BENCHMARK_CLASS, generalization_claim=P10.GENERALIZATION_CLAIM,
        verdict=verdict, delivery_verdict_derivation="from the run's journal events only; no plan-quality input — and FAIL, never PASS, "
                                                     "while a story of the plan has not committed in the journal (a story that never began "
                                                     "is in no event), when the budget was reached or spend was unaccounted, or when the "
                                                     "run's revisions are not all preserved",
        delivery_pass_blocked_by=blocks_pass,
        story_outcomes=m["results"], story_state=m["state"], story_errors=m["errors"], stories_not_committed=not_committed,
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
        stop_rules={"kernel_tree_is_the_candidates": C.git("rev-parse", "HEAD:aisef2") == kernel_tree, "plan_retuned": False, "kernel_repaired": False,
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
    if a.profile == EXPERIMENT:
        from validation.qualification import c2_delivery_experiment as dx
        if a.attempt != dx.EXPERIMENT["attempt"]:      # ONE run: it has one attempt number, and a record there refuses a rerun
            raise SystemExit(f"REFUSED: the delivery experiment is preregistered as attempt {dx.EXPERIMENT['attempt']} only")
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
    if a.profile == EXPERIMENT:        # the run's record is on disk first: an evaluation that fails never loses it
        try:
            ev = dx.evaluate(pathlib.Path(m["preserved"]["path"]), m["final_main"], out_dir, rec["delivery_verdict"])
            print(f"final main {m['final_main']}: V2 specs satisfied {ev['v2_final_proof']['satisfied']}/{ev['v2_final_proof']['total']}; "
                  f"V1 oracle {ev['v1_oracle']['passed']}/{ev['v1_oracle']['total']}; delivery PASS confirmed: {ev['delivery_pass_confirmed']}")
        except Exception as e:  # noqa: BLE001 — recorded beside the run's record; the preserved result can be evaluated again
            ev = {"final_main": m["final_main"], "preserved": m["preserved"], "error": f"{type(e).__name__}: {e}"[:2000],
                  "delivery_verdict": rec["delivery_verdict"], "delivery_pass_confirmed": False}
            print(f"the final evaluation did not run: {ev['error']}")
        C.write(f"{rel}/FINAL-EVALUATION.json", ev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
