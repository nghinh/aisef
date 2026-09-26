"""Projection 3 — budgets (version 2): what each story consumed, derived from the journal and never counted beside it (§22;
P3-PROJECTION-SEMANTICS.md §3). Consumption only: limits come from resolved execution policy.

Version 2 (ARCHITECTURE-EXCEPTION-V2-005, journal format 3): a `provider/request` is charged to its typed
`budget_owner` — DEVELOPER, as every request was, or REVIEW or SECURITY — decided by the journal's declared format:
under formats 1 and 2 every request is the developer's (their frozen semantics, unchanged); under format 3 the field is
required and nothing defaults it. A review or security request never touches the developer's maps. A failure's owner
is still the taxonomy's, whatever budget the request that preceded it charged."""

from __future__ import annotations

from aisef2.arch.enums import ControlProjection, EventType as T, StoryAdmissionDisposition as D
from aisef2.journal.fold import ProjectionError

#: budget owner -> the consumption map it charges (cycle 1: the three the format-3 schema admits)
_MAPS = {"DEVELOPER": "developer", "REVIEW": "review", "SECURITY": "security"}
_BUDGET_OWNER_FORMAT = 3


class Budgets:
    id = ControlProjection.BUDGETS.value
    version = 2

    def initial(self):
        return {"format": None, "retries": {}, "developer": {}, "review": {}, "security": {}, "admission": {},
                "failures": {}}

    def step(self, state, event):
        t, d = event.type, event.data
        if t == T.RUN_BEGIN.value:
            return {**state, "format": d["journal_format"]}
        if t == T.STORY_BEGIN.value:
            return {**state, "admission": {k: v for k, v in state["admission"].items() if k != d["story_id"]},
                    "failures": {k: v for k, v in state["failures"].items() if k != d["story_id"]}}
        if t == T.STORY_ADMITTED.value:
            ready = [c for c, v in d["dispositions"].items() if v == D.READY.value]  # frozen keys iterate sorted
            return {**state, "admission": {**state["admission"], d["story_id"]: {
                "permitted": d["developer_call_permitted"], "ready": ready, "criteria": list(d["dispositions"])}}}
        if t == T.PROVIDER_REQUEST.value:
            sid, adm = d["story_id"], state["admission"].get(d["story_id"])
            if state["format"] is not None and state["format"] >= _BUDGET_OWNER_FORMAT:
                if d.get("budget_owner") not in _MAPS:
                    raise ProjectionError(f"budgets: a format-{state['format']} provider/request for {sid} names its "
                                          "budget_owner (DEVELOPER, REVIEW or SECURITY); nothing defaults it (V2-005)")
                owner = d["budget_owner"]
            else:
                owner = "DEVELOPER"  # formats 1 and 2: every provider request is the developer's (frozen)
            if owner == "DEVELOPER":
                if adm is None or not adm["permitted"]:
                    raise ProjectionError(f"budgets: provider/request for {sid}, whose admission permits no developer "
                                          "call")
                charged = [c for c in d["criteria"] if c not in adm["ready"]]
                if charged:
                    raise ProjectionError(f"budgets: provider/request for {sid} charges {charged}, not admitted READY "
                                          "(§14: PRE_SATISFIED consumes no developer budget)")
            else:
                if adm is None:
                    raise ProjectionError(f"budgets: {owner} provider/request for {sid}, which has no admission")
                unknown = [c for c in d["criteria"] if c not in adm["criteria"]]
                if unknown:
                    raise ProjectionError(f"budgets: {owner} provider/request for {sid} names {unknown}, not criteria "
                                          "of its admission")
            key = _MAPS[owner]
            cur = state[key].get(sid, {"requests": 0, "criteria": {}})
            criteria = dict(cur["criteria"])
            for c in d["criteria"]:
                criteria[c] = criteria.get(c, 0) + 1
            return {**state, key: {**state[key], sid: {"requests": cur["requests"] + 1, "criteria": criteria}}}
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
