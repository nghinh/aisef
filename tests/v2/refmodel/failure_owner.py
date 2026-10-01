"""Reference model 2 — `failure_owner` (version 1). Spec: P3-PROJECTION-SEMANTICS.md §2; RFC §17 (a rollback's owner
is the owner of the failure that caused it, never the stage that observed it).

Shape of this model: the journal is first split per story into attempts (runs of the story's events from one
`story/begin` to the next); each attempt is then read on its own. Only the last attempt's reading is the state, but
every attempt is read, because a refusal anywhere refuses the journal. Within an attempt the last citation wins.
"""

from . import Refused, Run

_NAMED = frozenset({"story/begin", "failure/observed", "story/rollback", "story/retry"})


def _attempts(events):
    """story -> list of attempts, each [begin event, later events of that story ...]. Refuses a story event that
    comes before the story's first begin."""
    out = {}
    for e in events:
        if e["type"] not in _NAMED:
            continue
        sid = e["data"]["story_id"]
        if e["type"] == "story/begin":
            out.setdefault(sid, []).append([e])
        elif sid not in out:
            raise Refused(f"seq {e['seq']}: {e['type']} for {sid}, which never began")
        else:
            out[sid][-1].append(e)
    return out


def _read(begin, rest, number):
    observed = {}               # seq (decimal string) -> [owner, code]
    decided = None              # the failure that speaks for the attempt: its seq
    cited = False
    for e in rest:
        if e["type"] == "failure/observed":
            observed[str(e["seq"])] = [e["data"]["owner"], e["data"]["code"]]
            if not cited:
                decided = e["seq"]
        else:                   # rollback or retry: exactly one cited failure/observed of the same story
            (cite,) = e["source_seqs"]
            if str(cite) not in observed:
                raise Refused(f"seq {e['seq']}: {e['type']} cites seq {cite}, not a failure of this attempt")
            decided, cited = cite, True
    owner, code = observed[str(decided)] if decided is not None else (None, None)
    return {"attempt": number, "begin_seq": begin["seq"], "observed": observed, "owner": owner, "code": code,
            "failure_seq": decided, "cited": cited}


def model(events):
    state = {}
    for sid, attempts in _attempts(events).items():
        for number, (begin, *rest) in enumerate(attempts, start=1):
            state[sid] = _read(begin, rest, number)
    return state


def _fo(attempt, begin_seq, observed, owner, code, failure_seq, cited):
    return {"attempt": attempt, "begin_seq": begin_seq, "observed": observed, "owner": owner, "code": code,
            "failure_seq": failure_seq, "cited": cited}


def _calibration():
    out = []

    r = Run()
    b = r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    f2 = r.fail("S1", "PROVIDER_UNAVAILABLE")
    r.rollback("S1", f1)
    seen = {str(f1): ["DEVELOPER", "CONTRACT_UNSATISFIED"], str(f2): ["PROVIDER", "PROVIDER_UNAVAILABLE"]}
    out.append(r.case("a rollback's owner is its cited failure's, not the latest failure's",
                      {"S1": _fo(1, b, seen, "DEVELOPER", "CONTRACT_UNSATISFIED", f1, True)},
                      {"S1": _fo(1, b, seen, "PROVIDER", "PROVIDER_UNAVAILABLE", f2, True)}))  # defect: latest wins

    r = Run()
    b = r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "SUBJECT_ABSENT_AT_CANDIDATE")
    r.rollback("S1", f1)
    f2 = r.fail("S1", "MISSING_CREDENTIAL")      # observed during disposal, after the decision
    r.close("S1")
    seen = {str(f1): ["DEVELOPER", "SUBJECT_ABSENT_AT_CANDIDATE"], str(f2): ["ENVIRONMENT", "MISSING_CREDENTIAL"]}
    out.append(r.case("a failure after the citation does not change the attempt's owner",
                      {"S1": _fo(1, b, seen, "DEVELOPER", "SUBJECT_ABSENT_AT_CANDIDATE", f1, True)},
                      {"S1": _fo(1, b, seen, "ENVIRONMENT", "MISSING_CREDENTIAL", f2, True)}))  # defect: cite not sticky

    r = Run()
    b = r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    f2 = r.fail("S1", "PROBE_UNRUNNABLE")
    seen = {str(f1): ["DEVELOPER", "CONTRACT_UNSATISFIED"], str(f2): ["ENVIRONMENT", "PROBE_UNRUNNABLE"]}
    out.append(r.case("the latest failure speaks for the attempt until one is cited",
                      {"S1": _fo(1, b, seen, "ENVIRONMENT", "PROBE_UNRUNNABLE", f2, False)},
                      {"S1": _fo(1, b, seen, "DEVELOPER", "CONTRACT_UNSATISFIED", f1, False)}))  # defect: first sticks

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    r.retry("S1", f1)
    r.close("S1")
    b = r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.rollback("S1", f1)
    out.append(r.case("a citation of an earlier attempt's failure refuses", "REFUSED",
                      {"S1": _fo(2, b, {}, "DEVELOPER", "CONTRACT_UNSATISFIED", f1, True)}))  # defect: cross-attempt

    r = Run()
    r.fail("S1", "CONTRACT_UNSATISFIED")
    out.append(r.case("a failure of a story that never began refuses", "REFUSED",
                      {}))                                                   # defect: silently ignored

    r = Run()
    b = r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.commit("S1")
    r.close("S1")
    f1 = r.fail("S1", "POST_MERGE_SUBJECT_LOST")
    out.append(r.case("a post-merge failure speaks for the committed attempt (INTEGRATION)",
                      {"S1": _fo(1, b, {str(f1): ["INTEGRATION", "POST_MERGE_SUBJECT_LOST"]}, "INTEGRATION",
                                 "POST_MERGE_SUBJECT_LOST", f1, False)},
                      {"S1": _fo(1, b, {}, None, None, None, False)}))       # defect: failures after ENDED dropped

    r = Run()
    b = r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    f2 = r.fail("S1", "PROVIDER_UNAVAILABLE")
    r.rollback("S1", f2)
    r.retry("S1", f1)                            # a second decision: story_state refuses it; here the last one wins
    seen = {str(f1): ["DEVELOPER", "CONTRACT_UNSATISFIED"], str(f2): ["PROVIDER", "PROVIDER_UNAVAILABLE"]}
    out.append(r.case("a later citation in the same attempt replaces the earlier",
                      {"S1": _fo(1, b, seen, "DEVELOPER", "CONTRACT_UNSATISFIED", f1, True)},
                      {"S1": _fo(1, b, seen, "PROVIDER", "PROVIDER_UNAVAILABLE", f2, True)}))  # defect: first cite sticks

    r = Run()
    b = r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "PROVIDER_UNAVAILABLE")
    r.commit("S1")
    r.close("S1")
    out.append(r.case("a committed attempt reports the latest failure it observed",
                      {"S1": _fo(1, b, {str(f1): ["PROVIDER", "PROVIDER_UNAVAILABLE"]}, "PROVIDER",
                                 "PROVIDER_UNAVAILABLE", f1, False)},
                      {"S1": _fo(1, b, {str(f1): ["PROVIDER", "PROVIDER_UNAVAILABLE"]}, None, None, None,
                                 False)}))                               # defect: a commit clears the owner
    return out


CALIBRATION = _calibration()
