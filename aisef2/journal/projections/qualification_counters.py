"""Projection 6 — qualification counters: delivery counts and the three §29 plan-quality metrics, over each story's
latest admission (P3-PROJECTION-SEMANTICS.md §6). The plan-quality verdict is not a projection."""

from __future__ import annotations

from aisef2.arch.enums import ControlProjection, EventType as T, ObligationRole, StoryAdmissionDisposition as D
from aisef2.journal.fold import ProjectionError
from aisef2.plan.drift import UNATTRIBUTED


def metrics(roles, admissions, drift) -> dict:
    introduce = [v for a in admissions.values() for c, v in a.items()
                 if roles is not None and roles.get(c) == ObligationRole.INTRODUCE.value]
    pre = sum(1 for v in introduce if v == D.PRE_SATISFIED.value)
    entries = [v for per in drift.values() for v in per.values()]
    return {"introduce_obligations": len(introduce), "pre_satisfied_introduce": pre,
            "pre_satisfied_introduce_ratio": pre / len(introduce) if introduce else None,
            "fully_pre_satisfied_stories": sum(1 for a in admissions.values()
                                               if a and all(v == D.PRE_SATISFIED.value for v in a.values())),
            "plan_drift": len(entries), "unattributed_plan_drift": sum(1 for v in entries if v == UNATTRIBUTED)}


class QualificationCounters:
    id = ControlProjection.QUALIFICATION_COUNTERS.value
    version = 1

    def initial(self):
        return {"roles": None, "admissions": {}, "drift": {}, "committed": 0, "rolled_back": 0, "retries": 0,
                "failures": {}, "metrics": metrics(None, {}, {})}

    def step(self, state, event):
        t, d = event.type, event.data
        new = dict(state)
        if t == T.PLAN_FROZEN.value:
            if state["roles"] is not None:
                raise ProjectionError("qualification_counters: a second plan/frozen — a run freezes one plan")
            new["roles"] = d["roles"]
        elif t == T.STORY_ADMITTED.value:
            unknown = [c for c in d["dispositions"] if state["roles"] is None or c not in state["roles"]]
            if unknown:
                raise ProjectionError(f"qualification_counters: story/admitted for {d['story_id']} names {unknown}, "
                                      "not criteria of the frozen plan")
            misplaced = [c for c, v in d["dispositions"].items()
                         if v == D.PRE_SATISFIED.value and state["roles"][c] != ObligationRole.INTRODUCE.value]
            if misplaced:
                raise ProjectionError(f"qualification_counters: story/admitted for {d['story_id']} records "
                                      f"{misplaced} PRE_SATISFIED, not INTRODUCE obligations (§13)")
            new["admissions"] = {**state["admissions"], d["story_id"]: d["dispositions"]}
            new["drift"] = {k: v for k, v in state["drift"].items() if k != d["story_id"]}
        elif t == T.STORY_PLAN_DRIFT.value:
            if state["admissions"].get(d["story_id"], {}).get(d["criterion_id"]) != D.PRE_SATISFIED.value:
                raise ProjectionError(f"qualification_counters: story/plan-drift for {d['story_id']} names "
                                      f"{d['criterion_id']}, not PRE_SATISFIED in its latest admission")
            new["drift"] = {**state["drift"], d["story_id"]: {**state["drift"].get(d["story_id"], {}),
                                                              d["criterion_id"]: d["attributed_to"]}}
        elif t == T.STORY_COMMIT.value:
            new["committed"] = state["committed"] + 1
        elif t == T.STORY_ROLLBACK.value:
            new["rolled_back"] = state["rolled_back"] + 1
        elif t == T.STORY_RETRY.value:
            new["retries"] = state["retries"] + 1
        elif t == T.FAILURE_OBSERVED.value:
            new["failures"] = {**state["failures"], d["owner"]: state["failures"].get(d["owner"], 0) + 1}
        else:
            return state
        new["metrics"] = metrics(new["roles"], new["admissions"], new["drift"])
        return new
