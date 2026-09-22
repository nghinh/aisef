"""Reference model 5 — `terminal_state` (version 1): the run's lifecycle and each story's terminal outcome.
Spec: P3-PROJECTION-SEMANTICS.md §5; RFC §17, §18 (no story begins once shutdown has started), §20.2 (a second
interrupt abandons, and records that it did).

Shape of this model: the run's ordinary moves are an explicit (state, event) -> state table and every pair not in it
refuses; interrupts are a separate rule because they also read how many interrupts came before. Story outcomes are
held back in `pending` until `story/end` settles them.
"""

from . import Refused, Run

_FINAL = frozenset({"ENDED", "ABANDONED"})
#: (run state, event) -> next run state, for every run event but run/interrupted
_RUN = {
    ("NOT_STARTED", "run/begin"): "RUNNING",
    ("RUNNING", "run/dispose-begin"): "DISPOSING",
    ("INTERRUPTED", "run/dispose-begin"): "DISPOSING",
    ("RUNNING", "run/end"): "ENDED",
    ("DISPOSING", "run/end"): "ENDED",
    ("INTERRUPTED", "run/end"): "ENDED",
}
#: abandoned flag -> (run states it may meet, whether an earlier interrupt is required, next run state)
_INTERRUPT = {
    False: (frozenset({"RUNNING", "DISPOSING"}), False, "INTERRUPTED"),
    True: (frozenset({"INTERRUPTED", "DISPOSING"}), True, "ABANDONED"),
}
_SETTLED = {"COMMIT": "COMMIT", "ROLLBACK": "ROLLBACK", "RETRY": "OPEN"}
_OUTCOME = {"story/commit": "COMMIT", "story/rollback": "ROLLBACK", "story/retry": "RETRY"}


def model(events):
    run, interrupts, stories, pending = "NOT_STARTED", 0, {}, {}
    for e in events:
        kind, data = e["type"], e["data"]
        if run in _FINAL:
            raise Refused(f"seq {e['seq']}: {kind} after the run is {run}")
        if kind == "run/interrupted":
            legal, needs_earlier, to = _INTERRUPT[data["abandoned"]]
            if run not in legal or (interrupts >= 1) is not needs_earlier:
                raise Refused(f"seq {e['seq']}: interrupt {data} while {run} after {interrupts} interrupt(s)")
            run, interrupts = to, interrupts + 1
        elif kind.startswith("run/"):
            if (run, kind) not in _RUN:
                raise Refused(f"seq {e['seq']}: {kind} while the run is {run}")
            run = _RUN[run, kind]
        elif kind == "story/begin":
            sid = data["story_id"]
            if run != "RUNNING" or stories.get(sid, "OPEN") != "OPEN":
                raise Refused(f"seq {e['seq']}: {sid} begins while the run is {run} and it is {stories.get(sid)}")
            stories[sid] = "RUNNING"
        elif kind in _OUTCOME:
            sid = data["story_id"]
            if stories.get(sid) != "RUNNING" or sid in pending:
                raise Refused(f"seq {e['seq']}: {kind} for {sid} ({stories.get(sid)}, pending {pending.get(sid)})")
            pending[sid] = _OUTCOME[kind]
        elif kind == "story/end":
            sid = data["story_id"]
            if sid not in pending:
                raise Refused(f"seq {e['seq']}: {sid} ends with no outcome")
            stories[sid] = _SETTLED[pending.pop(sid)]
    return {"run": run, "interrupts": interrupts, "stories": stories, "pending": pending}


def _t(run, stories=None, pending=None, interrupts=0):
    return {"run": run, "interrupts": interrupts, "stories": stories or {}, "pending": pending or {}}


def _calibration():
    out = []

    r = Run()
    r.add("run/end", {})
    r.add("gate/check", {"gate": "commit", "check": "late", "passed": True, "detail": ""})
    out.append(r.case("nothing may follow run/end, not even an event this projection does not read", "REFUSED",
                      _t("ENDED")))                                   # defect: only named events checked

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.commit("S1")
    r.close("S1")
    r.begin("S1")
    out.append(r.case("a committed story never begins again", "REFUSED",
                      _t("RUNNING", {"S1": "RUNNING"})))              # defect: begin always reopens

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "PLAN_CONTRADICTION"})
    f1 = r.fail("S1", "PLAN_CONTRADICTION")
    r.rollback("S1", f1)
    r.close("S1")
    r.begin("S1")
    out.append(r.case("a rolled-back story never begins again", "REFUSED",
                      _t("RUNNING", {"S1": "RUNNING"})))              # defect: only COMMIT is terminal

    r = Run()
    r.begin("S1")
    r.begin("S1")
    out.append(r.case("a running story is already in an attempt", "REFUSED",
                      _t("RUNNING", {"S1": "RUNNING"})))              # defect: only terminal stories refused

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    r.retry("S1", f1)
    r.close("S1")
    r.add("run/dispose-begin", {})
    r.add("run/end", {})
    out.append(r.case("a retried story is OPEN between attempts, not terminal",
                      _t("ENDED", {"S1": "OPEN"}),
                      _t("ENDED", {"S1": "RETRY"})))                  # defect: the outcome copied verbatim

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.commit("S1")
    out.append(r.case("an outcome stays pending, the story RUNNING, until story/end",
                      _t("RUNNING", {"S1": "RUNNING"}, {"S1": "COMMIT"}),
                      _t("RUNNING", {"S1": "COMMIT"})))               # defect: commit settles at once

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    f1 = r.fail("S1", "CONTRACT_UNSATISFIED")
    r.commit("S1")
    r.rollback("S1", f1)
    out.append(r.case("one decision per attempt", "REFUSED",
                      _t("RUNNING", {"S1": "RUNNING"}, {"S1": "ROLLBACK"})))  # defect: pending overwritten

    r = Run()
    r.commit("S1")
    out.append(r.case("an outcome needs an open attempt", "REFUSED",
                      _t("RUNNING", pending={"S1": "COMMIT"})))       # defect: outcome recorded for any story

    r = Run()
    r.add("run/dispose-begin", {})
    r.begin("S1")
    out.append(r.case("no story begins once disposal has started (§18)", "REFUSED",
                      _t("DISPOSING", {"S1": "RUNNING"})))            # defect: begin ignores the run

    r = Run()
    r.begin("S1")
    r.admit("S1", {"C1": "READY"})
    r.commit("S1")
    r.add("run/dispose-begin", {})
    r.close("S1")
    r.add("run/end", {})
    out.append(r.case("a decided story still ends during disposal",
                      _t("ENDED", {"S1": "COMMIT"}),
                      "REFUSED"))                                     # defect: story events only while RUNNING

    r = Run()
    r.add("run/interrupted", {"abandoned": False})
    r.add("run/dispose-begin", {})
    r.add("run/interrupted", {"abandoned": True})
    r.add("run/end", {})
    out.append(r.case("an abandoned run is final", "REFUSED",
                      _t("ENDED", interrupts=2)))                     # defect: run/end legal from ABANDONED

    r = Run()
    r.add("run/dispose-begin", {})
    r.add("run/interrupted", {"abandoned": True})
    out.append(r.case("a first interrupt never abandons, even during disposal", "REFUSED",
                      _t("ABANDONED", interrupts=1)))                 # defect: the run state alone decides

    r = Run()
    r.add("run/interrupted", {"abandoned": False})
    r.add("run/dispose-begin", {})
    r.add("run/interrupted", {"abandoned": False})
    out.append(r.case("a second interrupt abandons (§20.2)", "REFUSED",
                      _t("INTERRUPTED", interrupts=2)))               # defect: interrupts not counted

    r = Run()
    r.add("run/interrupted", {"abandoned": False})
    r.add("run/interrupted", {"abandoned": True})
    out.append(r.case("a second interrupt abandons straight from INTERRUPTED",
                      _t("ABANDONED", interrupts=2),
                      "REFUSED"))                                     # defect: abandonment only from DISPOSING
    return out


CALIBRATION = _calibration()
