"""Reference model 4 — `retry_target` (version 1): the budget a retry of the story's current attempt would charge.
Spec: P3-PROJECTION-SEMANTICS.md §4; RFC §22 (the retry engine reads only a failure's `owner` and `retryable`).

Shape of this model: two collections over the whole journal — each story's begin seqs and each story's failures —
then the answer per story is the last failure after its last begin, read for owner and retryable only.
"""

from . import Refused, Run


def model(events):
    begins, failures = {}, {}
    for e in events:
        if e["type"] == "story/begin":
            begins.setdefault(e["data"]["story_id"], []).append(e["seq"])
        elif e["type"] == "failure/observed":
            failures.setdefault(e["data"]["story_id"], []).append(e)
    for sid, fs in failures.items():
        if sid not in begins or fs[0]["seq"] < begins[sid][0]:
            raise Refused(f"seq {fs[0]['seq']}: failure of {sid} before it ever began")
    state = {}
    for sid, seqs in begins.items():
        current = [f for f in failures.get(sid, ()) if f["seq"] > seqs[-1]]
        if not current:
            state[sid] = {"budget": None, "failure_seq": None}
        else:
            last = current[-1]
            state[sid] = {"budget": last["data"]["owner"] if last["data"]["retryable"] else None,
                          "failure_seq": last["seq"]}
    return state


def _calibration():
    out = []

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "INVALID_CREDENTIAL")
    out.append(r.case("a non-retryable failure names no retry budget",
                      {"S1": {"budget": None, "failure_seq": f1}},
                      {"S1": {"budget": "ENVIRONMENT", "failure_seq": f1}}))   # defect: owner regardless of retryable

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "PROVIDER_UNAVAILABLE")
    f2 = r.fail("S1", "UNKNOWN")
    out.append(r.case("the latest failure decides, even a non-retryable one",
                      {"S1": {"budget": None, "failure_seq": f2}},
                      {"S1": {"budget": "PROVIDER", "failure_seq": f1}}))      # defect: only retryable ones move it

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "MISSING_CREDENTIAL")
    r.retry("S1", f1)
    r.close("S1")
    r.begin("S1")
    out.append(r.case("a new attempt starts with no retry target",
                      {"S1": {"budget": None, "failure_seq": None}},
                      {"S1": {"budget": "ENVIRONMENT", "failure_seq": f1}}))   # defect: begin does not reset

    r = Run()
    r.fail("S1", "PROBE_UNRUNNABLE")
    out.append(r.case("a failure of a story that never began refuses", "REFUSED",
                      {}))                                                     # defect: silently ignored

    r = Run()
    r.begin("S1")
    r.begin("S2")
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    f2 = r.fail("S2", "PROBE_INVALID_SPEC")
    out.append(r.case("the target is the story's own latest failure",
                      {"S1": {"budget": "DEVELOPER", "failure_seq": f1}, "S2": {"budget": None, "failure_seq": f2}},
                      {"S1": {"budget": None, "failure_seq": f2},
                       "S2": {"budget": None, "failure_seq": f2}}))            # defect: one run-wide latest failure
    return out


CALIBRATION = _calibration()
