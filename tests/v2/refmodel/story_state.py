"""Reference model 1 — `story_state` (version 1): §17's lifecycle per story. Spec: P3-PROJECTION-SEMANTICS.md §1.

Shape of this model: one table says, for each story event, the lifecycle states it is legal in and the state it moves
the story to; begin, admission and plan drift, whose rules also read `outcome` or `admitted`, are spelled out below.
"""

from . import Refused, Run

_ANY = frozenset({"BEGIN", "ACTIVE", "COMMIT", "ROLLBACK", "RETRY", "DISPOSE", "ENDED"})
_OPEN = frozenset({"BEGIN", "ACTIVE"})
#: event type -> (states it may meet, state it moves to or None, whether that state is also the outcome)
_TABLE = {
    "story/commit": (frozenset({"ACTIVE"}), "COMMIT", True),
    "story/rollback": (_OPEN, "ROLLBACK", True),
    "story/retry": (_OPEN, "RETRY", True),
    "story/dispose": (frozenset({"COMMIT", "ROLLBACK", "RETRY"}), "DISPOSE", False),
    "story/end": (frozenset({"DISPOSE"}), "ENDED", False),
    "probe/evaluated": (_OPEN, None, False),
    "provider/request": (frozenset({"ACTIVE"}), None, False),
    "failure/observed": (_ANY, None, False),   # a post-merge failure follows ENDED
}


def model(events):
    stories = {}
    for e in events:
        kind, data = e["type"], e["data"]
        if kind not in ("story/begin", "story/admitted", "story/plan-drift") and kind not in _TABLE:
            continue
        sid = data["story_id"]
        cur = stories.get(sid)
        if kind == "story/begin":
            if cur is not None and (cur["state"], cur["outcome"]) != ("ENDED", "RETRY"):
                raise Refused(f"seq {e['seq']}: {sid} begins again from {cur['state']}/{cur['outcome']}")
            stories[sid] = {"state": "BEGIN", "attempt": 1 if cur is None else cur["attempt"] + 1, "admitted": None,
                            "outcome": None}
            continue
        if cur is None:
            raise Refused(f"seq {e['seq']}: {kind} for {sid}, which never began")
        if kind == "story/admitted":
            if cur["state"] != "BEGIN" or cur["admitted"] is not None:
                raise Refused(f"seq {e['seq']}: {sid} admitted in {cur['state']}, admitted={cur['admitted']}")
            cur["admitted"] = data["admitted"]
            if data["admitted"]:
                cur["state"] = "ACTIVE"
            continue
        if kind == "story/plan-drift":          # after the attempt's admission, even a refused one (§14)
            if cur["state"] != "ACTIVE" and (cur["state"], cur["admitted"]) != ("BEGIN", False):
                raise Refused(f"seq {e['seq']}: drift for {sid} in {cur['state']}, admitted={cur['admitted']}")
            continue
        legal, to, is_outcome = _TABLE[kind]
        if cur["state"] not in legal:
            raise Refused(f"seq {e['seq']}: {kind} for {sid} in {cur['state']}")
        if to is not None:
            cur["state"] = to
            if is_outcome:
                cur["outcome"] = to
    return stories


def _st(state, attempt, admitted, outcome):
    return {"state": state, "attempt": attempt, "admitted": admitted, "outcome": outcome}


def _calibration():
    out = []

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "PRECONDITION_BROKEN"})
    r.fail("S1", "PRECONDITION_BROKEN")
    r.add("probe/evaluated", {"story_id": "S1", "criterion_id": "C1", "record": {"result": {"status": "x"}}})
    out.append(r.case("a blocked admission keeps the story in BEGIN",
                      {"S1": _st("BEGIN", 1, False, None)},
                      {"S1": _st("ACTIVE", 1, False, None)}))           # defect: any admission activates

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "PLAN_CONTRADICTION"})
    r.commit("S1")
    out.append(r.case("a blocked story cannot commit", "REFUSED",
                      {"S1": _st("COMMIT", 1, False, "COMMIT")}))       # defect: commit legal from BEGIN like rollback

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.commit("S1")
    r.close("S1")
    r.begin("S1")
    out.append(r.case("a committed story never begins again", "REFUSED",
                      {"S1": _st("BEGIN", 2, None, None)}))             # defect: any ENDED story may begin

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f = r.fail("S1", "CONTRACT_UNSATISFIED")
    r.retry("S1", f)
    r.close("S1")
    r.begin("S1")
    out.append(r.case("a retry's next begin is a new, unadmitted attempt",
                      {"S1": _st("BEGIN", 2, None, None)},
                      {"S1": _st("BEGIN", 2, True, "RETRY")}))          # defect: begin keeps admitted and outcome

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.admit("S1", {"C1": "READY"})
    out.append(r.case("an attempt is admitted once", "REFUSED",
                      {"S1": _st("ACTIVE", 1, True, None)}))            # defect: re-admission accepted

    r = Run()
    r.begin("S1")
    r.request("S1", ["C1"])
    out.append(r.case("no developer call precedes the admission (§13)", "REFUSED",
                      {"S1": _st("BEGIN", 1, None, None)}))             # defect: provider/request legal in BEGIN

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "PRE_SATISFIED", "C2": "PRECONDITION_BROKEN"})
    r.drift("S1", "C1", [])
    out.append(r.case("a blocked story still records its drift (§14)",
                      {"S1": _st("BEGIN", 1, False, None)},
                      "REFUSED"))                                       # defect: drift legal in ACTIVE only

    r = Run()
    r.begin("S1")
    r.drift("S1", "C1", ["S2"])
    out.append(r.case("no drift before the attempt's admission", "REFUSED",
                      {"S1": _st("BEGIN", 1, None, None)}))             # defect: drift legal in any BEGIN

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "PRE_SATISFIED", "C2": "PLAN_CONTRADICTION"})
    r.request("S1", ["C1"])
    out.append(r.case("a blocked story makes no developer call", "REFUSED",
                      {"S1": _st("BEGIN", 1, False, None)}))            # defect: request allowed wherever drift is

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.commit("S1")
    r.close("S1")
    r.fail("S1", "POST_MERGE_REGRESSION")
    out.append(r.case("a post-merge failure follows ENDED",
                      {"S1": _st("ENDED", 1, True, "COMMIT")},
                      "REFUSED"))                                       # defect: failures only while BEGIN/ACTIVE
    return out


CALIBRATION = _calibration()
