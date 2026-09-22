"""Reference model 3 — `budgets` (version 1): consumption only. Spec: P3-PROJECTION-SEMANTICS.md §3; RFC §14 (a
PRE_SATISFIED criterion consumes no developer budget), §17 (RETRY only against the budget the failure names), §22
(a retry reads the latest failure only, so it can never reach past a newer non-retryable one — D-006).

Shape of this model: each story's own events are walked separately with local variables for its current attempt
(admission, failures) and its run-long consumption (developer calls, retries); the four maps are assembled at the
end from what each story holds.
"""

from . import Refused, Run

_NAMED = frozenset({"story/begin", "story/admitted", "provider/request", "failure/observed", "story/retry"})


def _walk(evs):
    admission = failures = developer = None
    retries = {}
    for e in evs:
        kind, data = e["type"], e["data"]
        if kind == "story/begin":                       # a new attempt is admitted again
            admission = failures = None
        elif kind == "story/admitted":
            ready = sorted(c for c, d in data["dispositions"].items() if d == "READY")
            admission = {"permitted": data["developer_call_permitted"], "ready": ready}
        elif kind == "provider/request":
            if admission is None or not admission["permitted"] \
                    or not set(data["criteria"]) <= set(admission["ready"]):
                raise Refused(f"seq {e['seq']}: developer call on {data['criteria']} under admission {admission}")
            if developer is None:
                developer = {"requests": 0, "criteria": {}}
            developer["requests"] += 1
            for c in data["criteria"]:                  # distinct by the format-1 schema
                developer["criteria"][c] = developer["criteria"].get(c, 0) + 1
        elif kind == "failure/observed":
            if failures is None:
                failures = {}
            failures[str(e["seq"])] = data["owner"] if data["retryable"] else None
        else:                                           # story/retry
            (cite,) = e["source_seqs"]
            latest = None if failures is None else max(int(k) for k in failures)
            if cite != latest or failures[str(cite)] is None:
                raise Refused(f"seq {e['seq']}: retry cites seq {cite}; the attempt's latest failure is {latest}, "
                              f"budget {None if latest is None else failures[str(latest)]}")
            budget = failures[str(cite)]
            retries[budget] = retries.get(budget, 0) + 1
    return retries, developer, admission, failures


def model(events):
    per_story = {}
    for e in events:
        if e["type"] in _NAMED:
            per_story.setdefault(e["data"]["story_id"], []).append(e)
    state = {"retries": {}, "developer": {}, "admission": {}, "failures": {}}
    for sid, evs in per_story.items():
        for key, value in zip(("retries", "developer", "admission", "failures"), _walk(evs), strict=True):
            if value:                                   # {} retries and None mean "no entry"
                state[key][sid] = value
    return state


def _b(retries=None, developer=None, admission=None, failures=None):
    return {"retries": retries or {}, "developer": developer or {}, "admission": admission or {},
            "failures": failures or {}}


def _calibration():
    out = []

    r = Run()
    r.plan({"C1": "INTRODUCE", "C2": "INTRODUCE"})
    r.begin("S1")
    r.admit("S1", {"C1": "READY", "C2": "PRE_SATISFIED"})
    r.request("S1", ["C1", "C2"])
    out.append(r.case("a PRE_SATISFIED criterion is never charged developer budget (§14)", "REFUSED",
                      _b(developer={"S1": {"requests": 1, "criteria": {"C1": 1, "C2": 1}}},
                         admission={"S1": {"permitted": True, "ready": ["C1"]}})))  # defect: checks permitted only

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "INVALID_CREDENTIAL")
    r.retry("S1", f1)
    out.append(r.case("a retry of a non-retryable failure has no budget (D-006)", "REFUSED",
                      _b(retries={"S1": {"ENVIRONMENT": 1}}, admission={"S1": {"permitted": True, "ready": ["C1"]}},
                         failures={"S1": {str(f1): None}})))           # defect: charges the owner regardless

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.request("S1", ["C1"])
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    f2 = r.fail("S1", "UNKNOWN")
    r.retry("S1", f1)
    out.append(r.case("a retry cannot reach past a newer non-retryable failure (D-006)", "REFUSED",
                      _b(retries={"S1": {"DEVELOPER": 1}}, developer={"S1": {"requests": 1, "criteria": {"C1": 1}}},
                         admission={"S1": {"permitted": True, "ready": ["C1"]}},
                         failures={"S1": {str(f1): "DEVELOPER", str(f2): None}})))  # defect: any retryable failure

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "PROVIDER_UNAVAILABLE")
    f2 = r.fail("S1", "MISSING_CREDENTIAL")
    r.retry("S1", f1)
    out.append(r.case("a retry citing an older retryable failure refuses: only the latest is the target", "REFUSED",
                      _b(retries={"S1": {"PROVIDER": 1}}, admission={"S1": {"permitted": True, "ready": ["C1"]}},
                         failures={"S1": {str(f1): "PROVIDER", str(f2): "ENVIRONMENT"}})))  # defect: cite in attempt

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.request("S1", ["C1"])
    f1 = r.fail("S1", "PROVIDER_UNAVAILABLE")
    f2 = r.fail("S1", "CONTRACT_UNSATISFIED")
    r.retry("S1", f2)
    r.close("S1")
    common = {"developer": {"S1": {"requests": 1, "criteria": {"C1": 1}}},
              "admission": {"S1": {"permitted": True, "ready": ["C1"]}},
              "failures": {"S1": {str(f1): "PROVIDER", str(f2): "DEVELOPER"}}}
    out.append(r.case("a retry charges one budget: its cited (latest) failure's owner",
                      _b(retries={"S1": {"DEVELOPER": 1}}, **common),
                      _b(retries={"S1": {"PROVIDER": 1, "DEVELOPER": 1}}, **common)))  # defect: every retryable one

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.request("S1", ["C1"])
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    r.retry("S1", f1)
    r.close("S1")
    r.begin("S1")
    r.request("S1", ["C1"])
    out.append(r.case("a new attempt is admitted again before the developer is called", "REFUSED",
                      _b(retries={"S1": {"DEVELOPER": 1}}, developer={"S1": {"requests": 2, "criteria": {"C1": 2}}},
                         admission={"S1": {"permitted": True, "ready": ["C1"]}},
                         failures={"S1": {str(f1): "DEVELOPER"}})))    # defect: begin clears nothing

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C2": "READY", "C1": "READY"})
    r.request("S1", ["C2"])
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    r.retry("S1", f1)
    r.close("S1")
    r.begin("S1")
    r.admit("S1", {"C1": "READY", "C2": "PRE_SATISFIED"})
    r.request("S1", ["C1"])
    out.append(r.case("developer consumption accumulates across attempts; begin drops the attempt's failures",
                      _b(retries={"S1": {"DEVELOPER": 1}}, developer={"S1": {"requests": 2, "criteria": {"C1": 1,
                                                                                                         "C2": 1}}},
                         admission={"S1": {"permitted": True, "ready": ["C1"]}}),
                      _b(retries={"S1": {"DEVELOPER": 1}}, developer={"S1": {"requests": 1, "criteria": {"C1": 1}}},
                         admission={"S1": {"permitted": True, "ready": ["C1"]}})))  # defect: consumption per attempt

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    r.retry("S1", f1)
    r.close("S1")
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.retry("S1", f1)
    out.append(r.case("a retry citing an earlier attempt's failure refuses", "REFUSED",
                      _b(retries={"S1": {"DEVELOPER": 2}}, admission={"S1": {"permitted": True, "ready": ["C1"]}},
                         failures={"S1": {str(f1): "DEVELOPER"}})))    # defect: failures survive begin
    return out


CALIBRATION = _calibration()
