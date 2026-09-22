"""Projection 3 — budgets: what each story consumed, derived from the journal and never counted beside it (§22;
P3-PROJECTION-SEMANTICS.md §3). Consumption only: limits come from resolved execution policy."""

from __future__ import annotations

from aisef2.arch.enums import ControlProjection, EventType as T, StoryAdmissionDisposition as D
from aisef2.journal.fold import ProjectionError


class Budgets:
    id = ControlProjection.BUDGETS.value
    version = 1

    def initial(self):
        return {"retries": {}, "developer": {}, "admission": {}, "failures": {}}

    def step(self, state, event):
        t, d = event.type, event.data
        if t == T.STORY_BEGIN.value:
            return {**state, "admission": {k: v for k, v in state["admission"].items() if k != d["story_id"]},
                    "failures": {k: v for k, v in state["failures"].items() if k != d["story_id"]}}
        if t == T.STORY_ADMITTED.value:
            ready = [c for c, v in d["dispositions"].items() if v == D.READY.value]  # frozen keys iterate sorted
            return {**state, "admission": {**state["admission"], d["story_id"]: {
                "permitted": d["developer_call_permitted"], "ready": ready}}}
        if t == T.PROVIDER_REQUEST.value:
            sid, adm = d["story_id"], state["admission"].get(d["story_id"])
            if adm is None or not adm["permitted"]:
                raise ProjectionError(f"budgets: provider/request for {sid}, whose admission permits no developer call")
            charged = [c for c in d["criteria"] if c not in adm["ready"]]
            if charged:
                raise ProjectionError(f"budgets: provider/request for {sid} charges {charged}, not admitted READY "
                                      "(§14: PRE_SATISFIED consumes no developer budget)")
            dev = state["developer"].get(sid, {"requests": 0, "criteria": {}})
            criteria = dict(dev["criteria"])
            for c in d["criteria"]:
                criteria[c] = criteria.get(c, 0) + 1
            return {**state, "developer": {**state["developer"], sid: {"requests": dev["requests"] + 1,
                                                                       "criteria": criteria}}}
        if t == T.FAILURE_OBSERVED.value:
            sid = d["story_id"]
            charge = d["owner"] if d["retryable"] else None  # the budget a retry citing it would charge
            mine = {**state["failures"].get(sid, {}), str(event.seq): charge}
            return {**state, "failures": {**state["failures"], sid: mine}}
        if t == T.STORY_RETRY.value:
            sid, cited = d["story_id"], str(event.source_seqs[0])
            failures = state["failures"].get(sid, {})
            if cited not in failures:
                raise ProjectionError(f"budgets: story/retry for {sid} cites seq {cited}, not a failure of its attempt")
            latest = max(failures, key=int)
            if cited != latest:
                raise ProjectionError(f"budgets: story/retry for {sid} cites seq {cited}, not its latest failure (seq "
                                      f"{latest}): a retry never reaches past a newer failure")
            charge = failures[cited]
            if charge is None:
                raise ProjectionError(f"budgets: story/retry for {sid} cites a non-retryable failure: no budget to "
                                      "charge (§17)")
            mine = dict(state["retries"].get(sid, {}))
            mine[charge] = mine.get(charge, 0) + 1
            return {**state, "retries": {**state["retries"], sid: mine}}
        return state
