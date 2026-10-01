"""Reference model 6 — `qualification_counters` (version 1): delivery counts and the three §29 plan-quality metrics.
Spec: P3-PROJECTION-SEMANTICS.md §6; RFC §14 (PRE_SATISFIED, PLAN_DRIFT), §29 (metrics, never the verdict).

Shape of this model: one pass collects the fields; the metrics are a pure function of those fields, computed once
at the end (the spec recomputes them after every event, which is the same function of the same fields).
"""

from . import Refused, Run

_COUNTED = {"story/commit": "committed", "story/rollback": "rolled_back", "story/retry": "retries"}


def metrics(roles, admissions, drift):
    introduce = [(sid, c) for sid, disp in admissions.items() for c in disp if roles[c] == "INTRODUCE"]
    pre = [(sid, c) for sid, c in introduce if admissions[sid][c] == "PRE_SATISFIED"]
    entries = [who for per_story in drift.values() for who in per_story.values()]
    return {
        "introduce_obligations": len(introduce),
        "pre_satisfied_introduce": len(pre),
        "pre_satisfied_introduce_ratio": len(pre) / len(introduce) if introduce else None,
        "fully_pre_satisfied_stories": sum(1 for disp in admissions.values()
                                           if disp and all(d == "PRE_SATISFIED" for d in disp.values())),
        "plan_drift": len(entries),
        "unattributed_plan_drift": entries.count("UNATTRIBUTED"),
    }


def model(events):
    roles = None
    admissions, drift, failures = {}, {}, {}
    counts = {"committed": 0, "rolled_back": 0, "retries": 0}
    for e in events:
        kind, data = e["type"], e["data"]
        if kind == "plan/frozen":
            if roles is not None:
                raise Refused(f"seq {e['seq']}: a run freezes one plan")
            roles = dict(data["roles"])
        elif kind == "story/admitted":
            if roles is None:
                raise Refused(f"seq {e['seq']}: admission before any plan is frozen")
            unplanned = sorted(set(data["dispositions"]) - set(roles))
            if unplanned:
                raise Refused(f"seq {e['seq']}: admission names criteria not in the plan: {unplanned}")
            misplaced = sorted(c for c, d in data["dispositions"].items()
                               if d == "PRE_SATISFIED" and roles[c] != "INTRODUCE")
            if misplaced:
                raise Refused(f"seq {e['seq']}: PRE_SATISFIED on criteria that are not INTRODUCE: {misplaced}")
            admissions[data["story_id"]] = dict(data["dispositions"])
            # "the story's drift is cleared": read as the story leaving `drift`, not keeping an empty map (the
            # spec does not say which; the WP-3.5 report flags it)
            drift.pop(data["story_id"], None)
        elif kind == "story/plan-drift":
            sid, c = data["story_id"], data["criterion_id"]
            if admissions.get(sid, {}).get(c) != "PRE_SATISFIED":
                raise Refused(f"seq {e['seq']}: drift for {sid}/{c}, which its latest admission does not record "
                              "PRE_SATISFIED")
            drift.setdefault(sid, {})[c] = data["attributed_to"]
        elif kind in _COUNTED:
            counts[_COUNTED[kind]] += 1
        elif kind == "failure/observed":
            failures[data["owner"]] = failures.get(data["owner"], 0) + 1
    return {"roles": roles, "admissions": admissions, "drift": drift, **counts, "failures": failures,
            "metrics": metrics(roles or {}, admissions, drift)}


def _m(introduce, pre, ratio, fully, drift, unattributed):
    return {"introduce_obligations": introduce, "pre_satisfied_introduce": pre, "pre_satisfied_introduce_ratio": ratio,
            "fully_pre_satisfied_stories": fully, "plan_drift": drift, "unattributed_plan_drift": unattributed}


def _q(roles, admissions, drift, metrics_, committed=0, rolled_back=0, retries=0, failures=None):
    return {"roles": roles, "admissions": admissions, "drift": drift, "committed": committed,
            "rolled_back": rolled_back, "retries": retries, "failures": failures or {}, "metrics": metrics_}


def _calibration():
    out = []

    roles = {"C1": "INTRODUCE", "C2": "INTRODUCE"}
    r = Run()
    r.plan(roles)
    r.begin("S1")
    r.admit("S1", {"C1": "PROBE_UNRUNNABLE", "C2": "READY"})
    f1 = r.fail("S1", "PROBE_UNRUNNABLE")
    r.retry("S1", f1)
    r.close("S1")
    r.begin("S1")
    r.admit("S1", {"C1": "PRE_SATISFIED", "C2": "READY"})
    r.drift("S1", "C1", [])
    r.request("S1", ["C2"])
    r.commit("S1")
    r.close("S1")
    fields = (roles, {"S1": {"C1": "PRE_SATISFIED", "C2": "READY"}}, {"S1": {"C1": "UNATTRIBUTED"}})
    counts = {"committed": 1, "retries": 1, "failures": {"ENVIRONMENT": 1}}
    out.append(r.case("the plan-quality ratio reads each story's latest admission, once",
                      _q(*fields, _m(2, 1, 0.5, 0, 1, 1), **counts),
                      _q(*fields, _m(4, 1, 0.25, 0, 1, 1), **counts)))       # defect: every admission summed

    roles = {"C1.1": "INTRODUCE", "C2.1": "INTRODUCE", "C2.2": "INTRODUCE"}
    r = Run()
    r.plan(roles)
    r.begin("S1")
    r.admit("S1", {"C1.1": "READY"})
    r.request("S1", ["C1.1"])
    r.commit("S1")
    r.close("S1")
    r.begin("S2")
    r.admit("S2", {"C2.1": "PRE_SATISFIED", "C2.2": "PRE_SATISFIED"})
    r.drift("S2", "C2.1", ["S1", "S3"])                                     # two candidates: UNATTRIBUTED (§14)
    r.drift("S2", "C2.2", ["S1"])
    r.commit("S2")
    r.close("S2")
    fields = (roles, {"S1": {"C1.1": "READY"}, "S2": {"C2.1": "PRE_SATISFIED", "C2.2": "PRE_SATISFIED"}},
              {"S2": {"C2.1": "UNATTRIBUTED", "C2.2": "S1"}})
    out.append(r.case("UNATTRIBUTED drift is read from attributed_to, ambiguous candidates included",
                      _q(*fields, _m(3, 2, 2 / 3, 1, 2, 1), committed=2),
                      _q(*fields, _m(3, 2, 2 / 3, 1, 2, 0), committed=2)))   # defect: counts only empty candidates

    roles = {"C1": "INTRODUCE"}
    r = Run()
    r.plan(roles)
    r.begin("S1")
    r.admit("S1", {"C1": "PRE_SATISFIED"})
    r.drift("S1", "C1", ["S2"])
    r.drift("S1", "C1", [])
    fields = (roles, {"S1": {"C1": "PRE_SATISFIED"}}, {"S1": {"C1": "UNATTRIBUTED"}})
    out.append(r.case("drift counts the latest entry per story and criterion, not drift events",
                      _q(*fields, _m(1, 1, 1.0, 1, 1, 1)),
                      _q(*fields, _m(1, 1, 1.0, 1, 2, 1))))                  # defect: one count per drift event

    roles = {"C1": "INTRODUCE", "C2": "INTRODUCE"}
    r = Run()
    r.plan(roles)
    r.begin("S1")
    r.admit("S1", {"C1": "PRE_SATISFIED", "C2": "PRE_SATISFIED"})
    r.drift("S1", "C1", ["S2"])
    r.drift("S1", "C2", [])
    f1 = r.fail("S1", "PROVIDER_UNAVAILABLE")
    r.retry("S1", f1)
    r.close("S1")
    r.begin("S1")
    r.admit("S1", {"C1": "PRE_SATISFIED", "C2": "PRE_SATISFIED"})
    r.drift("S1", "C1", [])
    admissions = {"S1": {"C1": "PRE_SATISFIED", "C2": "PRE_SATISFIED"}}
    counts = {"retries": 1, "failures": {"PROVIDER": 1}}
    out.append(r.case("a re-admission clears the story's drift: drift belongs to the latest admission",
                      _q(roles, admissions, {"S1": {"C1": "UNATTRIBUTED"}}, _m(2, 2, 1.0, 1, 1, 1), **counts),
                      _q(roles, admissions, {"S1": {"C1": "UNATTRIBUTED", "C2": "UNATTRIBUTED"}},
                         _m(2, 2, 1.0, 1, 2, 2), **counts)))                # defect: drift kept across admissions

    r = Run()
    r.plan({"C1": "INTRODUCE", "C2": "PRESERVE"})
    r.begin("S1")
    r.admit("S1", {"C1": "PRE_SATISFIED", "C2": "PRECONDITION_BROKEN"})
    r.drift("S1", "C1", ["S2"])
    fields = ({"C1": "INTRODUCE", "C2": "PRESERVE"}, {"S1": {"C1": "PRE_SATISFIED", "C2": "PRECONDITION_BROKEN"}},
              {"S1": {"C1": "S2"}})
    out.append(r.case("a blocked story's PRE_SATISFIED criterion still drifts",
                      _q(*fields, _m(1, 1, 1.0, 0, 1, 0)),
                      "REFUSED"))                                           # defect: drift only when admitted

    r = Run()
    r.plan({"C1": "INTRODUCE"})
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.drift("S1", "C1", [])
    out.append(r.case("drift is only for a PRE_SATISFIED criterion of the latest admission", "REFUSED",
                      _q({"C1": "INTRODUCE"}, {"S1": {"C1": "READY"}}, {"S1": {"C1": "UNATTRIBUTED"}},
                         _m(1, 0, 0.0, 0, 1, 1))))                          # defect: drift not checked

    r = Run()
    r.plan({"C1": "INTRODUCE", "C2": "PRESERVE"})
    r.begin("S1")
    r.admit("S1", {"C1": "READY", "C2": "PRE_SATISFIED"})
    out.append(r.case("PRE_SATISFIED only on an INTRODUCE criterion (§13)", "REFUSED",
                      _q({"C1": "INTRODUCE", "C2": "PRESERVE"}, {"S1": {"C1": "READY", "C2": "PRE_SATISFIED"}}, {},
                         _m(1, 0, 0.0, 0, 0, 0))))                          # defect: role never cross-checked

    roles = {"C1": "INTRODUCE", "C2": "INTRODUCE", "C3": "INTRODUCE"}
    r = Run()
    r.plan(roles)
    r.begin("S1")
    r.admit("S1", {"C1": "PRE_SATISFIED", "C2": "READY"})
    r.begin("S2")
    r.admit("S2", {"C3": "PRE_SATISFIED"})
    fields = (roles, {"S1": {"C1": "PRE_SATISFIED", "C2": "READY"}, "S2": {"C3": "PRE_SATISFIED"}}, {})
    out.append(r.case("a fully pre-satisfied story has every disposition PRE_SATISFIED",
                      _q(*fields, _m(3, 2, 2 / 3, 1, 0, 0)),
                      _q(*fields, _m(3, 2, 2 / 3, 2, 0, 0))))                # defect: any PRE_SATISFIED counts

    roles = {"C1": "PRESERVE", "C2": "VERIFY"}
    r = Run()
    r.plan(roles)
    r.begin("S1")
    r.admit("S1", {"C1": "READY", "C2": "READY"})
    r.commit("S1")
    r.close("S1")
    fields = (roles, {"S1": {"C1": "READY", "C2": "READY"}}, {})
    out.append(r.case("the ratio is null when there is no INTRODUCE obligation",
                      _q(*fields, _m(0, 0, None, 0, 0, 0), committed=1),
                      _q(*fields, _m(0, 0, 0.0, 0, 0, 0), committed=1)))     # defect: 0/0 read as 0.0

    r = Run()
    r.plan({"C1": "INTRODUCE"})
    r.plan({"C1": "PRESERVE"})
    out.append(r.case("a run freezes one plan", "REFUSED",
                      _q({"C1": "PRESERVE"}, {}, {}, _m(0, 0, None, 0, 0, 0))))  # defect: a second plan replaces

    r = Run()
    r.plan({"C1": "INTRODUCE"})
    r.begin("S1")
    r.admit("S1", {"C1": "READY", "C9": "READY"})
    out.append(r.case("an admission names only criteria of the frozen plan", "REFUSED",
                      _q({"C1": "INTRODUCE"}, {"S1": {"C1": "READY", "C9": "READY"}}, {},
                         _m(1, 0, 0.0, 0, 0, 0))))                          # defect: unplanned criteria not checked

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.plan({"C1": "INTRODUCE"})
    out.append(r.case("an admission before the plan is frozen refuses", "REFUSED",
                      _q({"C1": "INTRODUCE"}, {"S1": {"C1": "READY"}}, {},
                         _m(1, 0, 0.0, 0, 0, 0))))                          # defect: roles checked only at the end
    return out


CALIBRATION = _calibration()
