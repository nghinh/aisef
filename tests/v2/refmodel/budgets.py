"""Reference model 3 — `budgets` (version 2): consumption only. Spec: P3-PROJECTION-SEMANTICS.md §3; RFC §14 (a
PRE_SATISFIED criterion consumes no developer budget), §17 (RETRY only against the budget the failure names), §22
(a retry reads the latest failure only, so it can never reach past a newer non-retryable one — D-006); V2-005 §8
(a format-3 provider request is charged to its typed budget_owner; formats 1 and 2 charge the developer, as written).

Shape of this model: the run's declared format is read once from `run/begin`; each story's own events are walked
separately with local variables for its current attempt (admission, failures) and its run-long consumption (one map
per budget owner, retries); the maps are assembled at the end from what each story holds.
"""

from . import Refused, Run

_NAMED = frozenset({"story/begin", "story/admitted", "provider/request", "failure/observed", "story/retry"})
_OWNERS = ("DEVELOPER", "REVIEW", "SECURITY")


def _walk(evs, fmt):
    admission = failures = None
    consumed = {o: None for o in _OWNERS}
    retries = {}
    for e in evs:
        kind, data = e["type"], e["data"]
        if kind == "story/begin":                       # a new attempt is admitted again
            admission = failures = None
        elif kind == "story/admitted":
            ready = sorted(c for c, d in data["dispositions"].items() if d == "READY")
            admission = {"permitted": data["developer_call_permitted"], "ready": ready,
                         "criteria": sorted(data["dispositions"])}
        elif kind == "provider/request":
            if fmt is not None and fmt >= 3:            # V2-005: the field is required; nothing defaults it
                owner = data.get("budget_owner")
                if owner not in _OWNERS:
                    raise Refused(f"seq {e['seq']}: a format-{fmt} provider request names no budget owner")
            else:
                owner = "DEVELOPER"                     # formats 1 and 2: every request is the developer's
            if admission is None:
                raise Refused(f"seq {e['seq']}: provider request before the attempt's admission")
            if owner == "DEVELOPER":
                if not admission["permitted"] or not set(data["criteria"]) <= set(admission["ready"]):
                    raise Refused(f"seq {e['seq']}: developer call on {data['criteria']} under admission {admission}")
            elif not set(data["criteria"]) <= set(admission["criteria"]):
                raise Refused(f"seq {e['seq']}: {owner} request on {data['criteria']}, not criteria of the admission")
            if consumed[owner] is None:
                consumed[owner] = {"requests": 0, "criteria": {}}
            consumed[owner]["requests"] += 1
            for c in data["criteria"]:                  # distinct by the schema
                consumed[owner]["criteria"][c] = consumed[owner]["criteria"].get(c, 0) + 1
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
    return retries, consumed["DEVELOPER"], consumed["REVIEW"], consumed["SECURITY"], admission, failures


def model(events):
    fmt = None
    per_story = {}
    for e in events:
        if e["type"] == "run/begin":
            fmt = e["data"]["journal_format"]
        elif e["type"] in _NAMED:
            per_story.setdefault(e["data"]["story_id"], []).append(e)
    state = {"format": fmt, "retries": {}, "developer": {}, "review": {}, "security": {}, "admission": {},
             "failures": {}}
    for sid, evs in per_story.items():
        for key, value in zip(("retries", "developer", "review", "security", "admission", "failures"),
                              _walk(evs, fmt), strict=True):
            if value:                                   # {} retries and None mean "no entry"
                state[key][sid] = value
    return state


def _b(retries=None, developer=None, admission=None, failures=None, review=None, security=None, fmt=1):
    return {"format": fmt, "retries": retries or {}, "developer": developer or {}, "review": review or {},
            "security": security or {}, "admission": admission or {}, "failures": failures or {}}


def _adm(ready, criteria=None, permitted=True):
    return {"permitted": permitted, "ready": ready, "criteria": criteria if criteria is not None else ready}


def _calibration():
    out = []

    r = Run()
    r.plan({"C1": "INTRODUCE", "C2": "INTRODUCE"})
    r.begin("S1")
    r.admit("S1", {"C1": "READY", "C2": "PRE_SATISFIED"})
    r.request("S1", ["C1", "C2"])
    out.append(r.case("a PRE_SATISFIED criterion is never charged developer budget (§14)", "REFUSED",
                      _b(developer={"S1": {"requests": 1, "criteria": {"C1": 1, "C2": 1}}},
                         admission={"S1": _adm(["C1"], ["C1", "C2"])})))  # defect: checks permitted only

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "INVALID_CREDENTIAL")
    r.retry("S1", f1)
    out.append(r.case("a retry of a non-retryable failure has no budget (D-006)", "REFUSED",
                      _b(retries={"S1": {"ENVIRONMENT": 1}}, admission={"S1": _adm(["C1"])},
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
                         admission={"S1": _adm(["C1"])},
                         failures={"S1": {str(f1): "DEVELOPER", str(f2): None}})))  # defect: any retryable failure

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "PROVIDER_UNAVAILABLE")
    f2 = r.fail("S1", "MISSING_CREDENTIAL")
    r.retry("S1", f1)
    out.append(r.case("a retry citing an older retryable failure refuses: only the latest is the target", "REFUSED",
                      _b(retries={"S1": {"PROVIDER": 1}}, admission={"S1": _adm(["C1"])},
                         failures={"S1": {str(f1): "PROVIDER", str(f2): "ENVIRONMENT"}})))  # defect: cite in attempt

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.request("S1", ["C1"])
    f1 = r.fail("S1", "PROVIDER_UNAVAILABLE")
    f2 = r.fail("S1", "CONTRACT_UNSATISFIED")
    r.retry("S1", f2)
    r.close("S1")
    common = {"developer": {"S1": {"requests": 1, "criteria": {"C1": 1}}}, "admission": {"S1": _adm(["C1"])},
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
                         admission={"S1": _adm(["C1"])},
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
                         admission={"S1": _adm(["C1"], ["C1", "C2"])}),
                      _b(retries={"S1": {"DEVELOPER": 1}}, developer={"S1": {"requests": 1, "criteria": {"C1": 1}}},
                         admission={"S1": _adm(["C1"], ["C1", "C2"])})))  # defect: consumption per attempt

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
                      _b(retries={"S1": {"DEVELOPER": 2}}, admission={"S1": _adm(["C1"])},
                         failures={"S1": {str(f1): "DEVELOPER"}})))    # defect: failures survive begin

    # ---- V2-005: format 3 charges the typed budget owner
    r = Run(journal_format=3)
    r.begin("S1")
    r.admit("S1", {"C1": "READY", "C2": "PRE_SATISFIED"})
    r.request("S1", ["C1"], "DEVELOPER")
    r.request("S1", ["C1", "C2"], "REVIEW")
    r.request("S1", ["C2"], "SECURITY")
    out.append(r.case("a format-3 request is charged to its budget_owner: REVIEW and SECURITY never touch the developer",
                      _b(developer={"S1": {"requests": 1, "criteria": {"C1": 1}}},
                         review={"S1": {"requests": 1, "criteria": {"C1": 1, "C2": 1}}},
                         security={"S1": {"requests": 1, "criteria": {"C2": 1}}},
                         admission={"S1": _adm(["C1"], ["C1", "C2"])}, fmt=3),
                      _b(developer={"S1": {"requests": 3, "criteria": {"C1": 2, "C2": 2}}},
                         admission={"S1": _adm(["C1"], ["C1", "C2"])}, fmt=3)))  # defect: every request is developer

    r = Run(journal_format=3)
    r.begin("S1")
    r.admit("S1", {"C1": "READY", "C2": "PRE_SATISFIED"})
    r.request("S1", ["C2"], "DEVELOPER")
    out.append(r.case("a format-3 DEVELOPER request is still charged READY criteria only (§14)", "REFUSED",
                      _b(developer={"S1": {"requests": 1, "criteria": {"C2": 1}}},
                         admission={"S1": _adm(["C1"], ["C1", "C2"])}, fmt=3)))  # defect: owner named ⇒ unchecked

    r = Run(journal_format=3)
    r.begin("S1")
    r.request("S1", ["C1"], "SECURITY")
    out.append(r.case("a security request before the attempt's admission is refused", "REFUSED",
                      _b(security={"S1": {"requests": 1, "criteria": {"C1": 1}}}, fmt=3)))  # defect: no admission needed

    r = Run(journal_format=3)
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.request("S1", ["C1", "C9"], "REVIEW")
    out.append(r.case("a review request names criteria of the story's admission only", "REFUSED",
                      _b(review={"S1": {"requests": 1, "criteria": {"C1": 1, "C9": 1}}}, admission={"S1": _adm(["C1"])},
                         fmt=3)))                                     # defect: review requests are unchecked

    return out


CALIBRATION = _calibration()
