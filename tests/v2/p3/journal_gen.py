"""Seeded generator of valid format-1 runs, for the fold oracle (WP-3.3) and the reference-model differential (WP-3.5).

A run is built from its own small model of RFC §17 (never from the projections): a frozen plan, stories that begin,
are admitted (or blocked) at the parent, drift, call the developer on READY criteria only, fail, and end in commit,
rollback or retry — retries start a new attempt — interleaved, with post-merge failures, gate rows, interrupts and
abandonment. Owner and retryable come from the taxonomy (`event.carried`). `journal(seed)` returns stored text: read
it with `compat.reconstruct`, which validates every event.
"""

import random

from aisef2.journal.event import GENESIS, Event, carried, encode, link

SHA = "d" * 40
ROLES = ("INTRODUCE", "PRESERVE", "VERIFY")
#: blocking disposition -> the failure the story records for it
BLOCKED = {"PRECONDITION_BROKEN": "PRECONDITION_BROKEN", "PLAN_CONTRADICTION": "PLAN_CONTRADICTION",
           "PROBE_UNRUNNABLE": "PROBE_UNRUNNABLE", "PROBE_INVALID": "PROBE_INVALID_SPEC"}
ACTIVE_FAILURES = ("CONTRACT_UNSATISFIED", "SUBJECT_ABSENT_AT_CANDIDATE", "PROVIDER_UNAVAILABLE", "PROBE_UNRUNNABLE",
                   "INVALID_CREDENTIAL", "MISSING_CREDENTIAL", "UNKNOWN")
POST_MERGE = ("POST_MERGE_REGRESSION", "POST_MERGE_SUBJECT_LOST")


def _text(specs, times):
    out, prev = [], GENESIS
    for n, ((type_, data, cites), t) in enumerate(zip(specs, times, strict=True)):
        event = Event(n, type_, carried(type_, data), t, False, cites)
        prev = link(prev, event)
        out.append(encode(event, prev))
    return "".join(out)


def specs(seed: int, *, stories: int = 4, max_attempts: int = 3) -> list[tuple[str, dict, tuple[int, ...]]]:
    rng = random.Random(seed)
    out: list[tuple[str, dict, tuple[int, ...]]] = []

    def emit(type_, data, cites=()):
        out.append((type_, data, tuple(cites)))
        return len(out) - 1

    emit("run/begin", {"journal_format": 1, "run_id": f"gen-{seed}"})
    roles = {f"C{s}.{k}": rng.choice(ROLES) for s in range(1, stories + 1) for k in range(1, rng.randint(1, 3) + 1)}
    emit("plan/frozen", {"plan_id": f"PLAN-{seed}", "plan_hash": "e" * 64, "roles": roles})
    live = {f"S{s}": {"phase": "new", "attempt": 0, "failures": []} for s in range(1, stories + 1)}
    mine = {sid: [c for c in roles if c.startswith(f"C{sid[1:]}.")] for sid in live}
    ended_commit = []

    def disposition(role):
        r = rng.random()
        if role == "INTRODUCE":
            return "READY" if r < .55 else "PRE_SATISFIED" if r < .9 else rng.choice(["PROBE_UNRUNNABLE", "PROBE_INVALID"])
        if role == "PRESERVE":
            return "READY" if r < .85 else rng.choice(["PRECONDITION_BROKEN", "PLAN_CONTRADICTION"])
        return "READY" if r < .9 else "PRECONDITION_BROKEN"

    def fail(sid, code):
        extra = {"original": rng.choice(["OSError", "KeyError", "TimeoutError"])} if code == "UNKNOWN" else {}
        seq = emit("failure/observed", {"story_id": sid, "code": code, "detail": f"{code.lower()} in {sid}", **extra})
        live[sid]["failures"].append((seq, carried("failure/observed", {"story_id": sid, "code": code,
                                                                        "detail": ""})["retryable"]))
        return seq

    def finish(sid, outcome, cite=None):
        emit(f"story/{outcome}", {"story_id": sid, **({"revision": SHA} if outcome == "commit" else {})},
             () if cite is None else (cite,))
        live[sid].update(phase="dispose", outcome=outcome)  # disposal interleaves with other stories

    def close(sid):
        emit("story/end", {"story_id": sid})
        st, outcome = live[sid], live[sid]["outcome"]
        if outcome == "retry" and st["attempt"] < max_attempts:
            st.update(phase="new", failures=[])
        else:
            st["phase"] = "done"
            if outcome == "commit":
                ended_commit.append(sid)

    def advance(sid):
        st = live[sid]
        if st["phase"] == "dispose":
            emit("story/dispose", {"story_id": sid})
            st["phase"] = "end"
        elif st["phase"] == "end":
            close(sid)
        elif st["phase"] == "new":
            st["attempt"] += 1
            st["failures"] = []
            emit("story/begin", {"story_id": sid, "parent": SHA})
            st["phase"] = "begun"
        elif st["phase"] == "begun":
            for c in mine[sid]:
                if rng.random() < .5:
                    emit("probe/evaluated", {"story_id": sid, "criterion_id": c, "record": {"result": {"status": "x"}}})
            d = {c: disposition(roles[c]) for c in mine[sid]}
            blocked = [v for v in d.values() if v in BLOCKED]
            ready = [c for c, v in d.items() if v == "READY"]
            emit("story/admitted", {"story_id": sid, "parent": SHA, "admitted": not blocked,
                                    "developer_call_permitted": not blocked and bool(ready), "dispositions": d})
            st.update(ready=ready, permitted=not blocked and bool(ready), pre=[c for c, v in d.items()
                                                                              if v == "PRE_SATISFIED"])
            if blocked:
                for c in [c for c, v in d.items() if v == "PRE_SATISFIED"]:  # a blocked story still records drift
                    if rng.random() < .5:
                        emit("story/plan-drift", {"story_id": sid, "criterion_id": c, "spec_id": f"PPS-{c}",
                                                  "attributed_to": "UNATTRIBUTED", "candidates": []})
                seq = fail(sid, BLOCKED[blocked[0]])
                retryable = st["failures"][-1][1]
                finish(sid, "retry" if retryable and st["attempt"] < max_attempts and rng.random() < .7 else "rollback",
                       seq)
            else:
                st["phase"] = "active"
        elif st["phase"] == "active":
            r = rng.random()
            if st["pre"] and r < .25:
                c = st["pre"].pop(rng.randrange(len(st["pre"])))
                cands = rng.choice([[], [f"S{rng.randint(1, stories)}"], ["S1", "S2"]])
                emit("story/plan-drift", {"story_id": sid, "criterion_id": c, "spec_id": f"PPS-{c}",
                                          "attributed_to": cands[0] if len(cands) == 1 else "UNATTRIBUTED",
                                          "candidates": cands})
            elif st["permitted"] and r < .55:
                emit("provider/request", {"story_id": sid,
                                          "criteria": sorted(rng.sample(st["ready"], rng.randint(1, len(st["ready"]))))})
            elif r < .72:
                fail(sid, rng.choice(ACTIVE_FAILURES))
            elif r < .78:
                emit("gate/check", {"gate": "commit", "check": f"{sid}-proof", "passed": rng.random() < .8,
                                    "detail": ""})
            else:
                if st["failures"] and rng.random() < .5:
                    latest, retryable = st["failures"][-1]  # a retry answers the latest failure, never an older one
                    if retryable and st["attempt"] < max_attempts and rng.random() < .6:
                        finish(sid, "retry", latest)
                    else:
                        finish(sid, "rollback", rng.choice([s for s, _ in st["failures"]]))
                else:
                    finish(sid, "commit")

    while any(st["phase"] != "done" for st in live.values()):
        sid = rng.choice([s for s, st in live.items() if st["phase"] != "done"])
        advance(sid)
        if ended_commit and rng.random() < .03:
            fail(rng.choice(ended_commit), rng.choice(POST_MERGE))
    checks = [n for n, (t, d, _) in enumerate(out) if t == "gate/check" and d["gate"] == "commit"]
    if checks:
        emit("gate/decision", {"gate": "commit", "passed": all(out[n][1]["passed"] for n in checks),
                               "projections": ["story_state", "budgets", "failure_owner"]}, checks)
    ending = rng.random()
    if ending < .15:
        emit("run/interrupted", {"abandoned": False})
        if rng.random() < .5:
            emit("run/dispose-begin", {})
            emit("run/interrupted", {"abandoned": True})
            return out
    if ending < .8:
        emit("run/dispose-begin", {})
    emit("run/end", {})
    return out


def journal(seed: int, *, stories: int = 4, times=None, **kw) -> str:
    """Stored text of run `seed`; `times` maps n -> the event's wall-clock time (default: n)."""
    s = specs(seed, stories=stories, **kw)
    return _text(s, [float(n) if times is None else float(times(n)) for n in range(len(s))])
