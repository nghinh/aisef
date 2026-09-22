"""WP-3.4 — the six control-critical projections (RFC §17, §21, §22, §29; F11), rule by rule against
docs/implementation/v2/P3-PROJECTION-SEMANTICS.md. Kill set for each projection's `step`."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ControlProjection as P  # noqa: E402
from aisef2.journal.compat import reconstruct  # noqa: E402
from aisef2.journal.event import GENESIS, Event, carried, encode, link  # noqa: E402
from aisef2.journal.fold import ProjectionError, fold  # noqa: E402
from aisef2.journal.projections import PROJECTIONS  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402
from tests.v2.p3 import journal_gen as gen  # noqa: E402

SHA = "a" * 40
RUN = ("run/begin", {"journal_format": 1, "run_id": "r"})


def run(*specs):
    """Events of a run: run/begin, then (type, data[, cites]) specs; failure owner/retryable carried."""
    out, prev = [], GENESIS
    for n, spec in enumerate((RUN, *specs)):
        type_, data, cites = (*spec, ())[:3]
        event = Event(n, type_, carried(type_, data), 0.0, False, cites)
        prev = link(prev, event)
        out.append(encode(event, prev))
    return reconstruct("".join(out)).events


def begin(s):
    return ("story/begin", {"story_id": s, "parent": SHA})


def admit(s, d):
    blocked = any(v in ("PRECONDITION_BROKEN", "PLAN_CONTRADICTION", "PROBE_UNRUNNABLE", "PROBE_INVALID")
                  for v in d.values())
    return ("story/admitted", {"story_id": s, "parent": SHA, "admitted": not blocked,
                               "developer_call_permitted": not blocked and "READY" in d.values(), "dispositions": d})


def fail(s, code="PROBE_UNRUNNABLE"):
    return ("failure/observed", {"story_id": s, "code": code, "detail": ""})


def story(t, s, *cites):
    return (f"story/{t}", {"story_id": s, **({"revision": SHA} if t == "commit" else {})}, tuple(cites))


def request(s, *criteria):
    return ("provider/request", {"story_id": s, "criteria": list(criteria)})


def drift(s, c, cands):
    return ("story/plan-drift", {"story_id": s, "criterion_id": c, "spec_id": f"PPS-{c}",
                                 "attributed_to": cands[0] if len(cands) == 1 else "UNATTRIBUTED", "candidates": cands})


def plan(**roles):
    return ("plan/frozen", {"plan_id": "PLAN", "plan_hash": "e" * 64, "roles": roles})


class _Case(unittest.TestCase):
    projection = None

    def state(self, *specs):
        return plain(fold(PROJECTIONS[self.projection], run(*specs)))

    def refused(self, *specs, msg=""):
        with self.assertRaisesRegex(ProjectionError, msg):
            self.state(*specs)


class Registry(unittest.TestCase):
    def test_six_stateless_projections_with_their_own_ids(self):
        self.assertEqual([k.value for k in PROJECTIONS], [p.value for p in P])
        for k, p in PROJECTIONS.items():
            with self.subTest(projection=k.value):
                self.assertEqual((p.id, p.version), (k.value, 1))
                self.assertEqual(vars(p), {})  # no side counter: every value is a fold of the journal
        with self.assertRaises(TypeError):
            PROJECTIONS[P.BUDGETS] = None

    def test_events_a_projection_does_not_name_leave_it_unchanged(self):
        other = ("gate/check", {"gate": "g", "check": "c", "passed": True, "detail": ""})
        for k, p in PROJECTIONS.items():
            with self.subTest(projection=k.value):
                self.assertEqual(fold(p, run(other)), fold(p, run()))


def only(specs, story):
    """The run's own events plus one story's, re-sequenced with citations remapped; and new seq -> old seq."""
    keep = [n for n, (t, d, _) in enumerate(specs) if "story_id" not in d or d["story_id"] == story]
    new = {old: i for i, old in enumerate(keep)}
    return [(specs[n][0], specs[n][1], tuple(new[c] for c in specs[n][2])) for n in keep], keep


def events_of(specs):
    return run(*specs[1:])  # run() adds its own run/begin


def back(entry, m):
    """A story's entry with the seqs of its own re-sequenced run mapped back to the whole run's."""
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    for k in ("begin_seq", "failure_seq"):
        if out.get(k) is not None:
            out[k] = m[out[k]]
    if "observed" in out:
        out["observed"] = {str(m[int(k)]): v for k, v in out["observed"].items()}
    return out


class Independence(unittest.TestCase):
    """A story's entry depends on its own events only: other stories' events never drop or change it."""

    def test_every_story_folds_alone_to_its_entry_in_the_run(self):
        keyed = {P.STORY_STATE: lambda st, s, m: st.get(s), P.FAILURE_OWNER: lambda st, s, m: back(st.get(s), m),
                 P.RETRY_TARGET: lambda st, s, m: back(st.get(s), m),
                 P.BUDGETS: lambda st, s, m: {k: ({str(m[int(q)]): v for q, v in st[k][s].items()}
                                                  if k == "failures" and s in st[k] else st[k].get(s)) for k in st},
                 P.TERMINAL_STATE: lambda st, s, m: (st["stories"].get(s), st["pending"].get(s)),
                 P.QUALIFICATION_COUNTERS: lambda st, s, m: (st["admissions"].get(s), st["drift"].get(s))}
        identity = range(10 ** 4)
        for seed in range(25):
            specs = gen.specs(seed, stories=4)
            whole = events_of(specs)
            for pid, entry in keyed.items():
                full = plain(fold(PROJECTIONS[pid], whole))
                for s in ("S1", "S2", "S3", "S4"):
                    alone_specs, keep = only(specs, s)
                    with self.subTest(seed=seed, projection=pid.value, story=s):
                        alone = plain(fold(PROJECTIONS[pid], events_of(alone_specs)))
                        self.assertEqual(entry(full, s, identity), entry(alone, s, keep))


class StoryState(_Case):
    projection = P.STORY_STATE

    def test_the_lifecycle(self):
        self.assertEqual(self.state(begin("S1")), {"S1": {"state": "BEGIN", "attempt": 1, "admitted": None,
                                                          "outcome": None}})
        self.assertEqual(self.state(begin("S1"), admit("S1", {"C": "READY"}))["S1"]["state"], "ACTIVE")
        blocked = self.state(begin("S1"), admit("S1", {"C": "PRECONDITION_BROKEN"}))["S1"]
        self.assertEqual((blocked["state"], blocked["admitted"]), ("BEGIN", False))
        done = self.state(begin("S1"), admit("S1", {"C": "READY"}), story("commit", "S1"), story("dispose", "S1"),
                          story("end", "S1"))
        self.assertEqual(done, {"S1": {"state": "ENDED", "attempt": 1, "admitted": True, "outcome": "COMMIT"}})
        again = self.state(begin("S1"), fail("S1"), story("retry", "S1", 2), story("dispose", "S1"),
                           story("end", "S1"), begin("S1"))
        self.assertEqual(again, {"S1": {"state": "BEGIN", "attempt": 2, "admitted": None, "outcome": None}})
        for t, s in (("rollback", "ROLLBACK"), ("retry", "RETRY")):
            for before in ((), (admit("S1", {"C": "READY"}),)):
                with self.subTest(outcome=t, admitted=bool(before)):
                    got = self.state(begin("S1"), *before, fail("S1"), story(t, "S1", 2 + len(before)))["S1"]
                    self.assertEqual((got["state"], got["outcome"]), (s, s))
        self.assertEqual(self.state(begin("S1"), begin("S2"))["S2"]["attempt"], 1)

    def test_events_inside_a_story(self):
        a = (begin("S1"), admit("S1", {"C": "READY", "D": "PRE_SATISFIED"}))
        self.assertEqual(self.state(*a, request("S1", "C"), drift("S1", "D", []), fail("S1"),
                                    ("probe/evaluated", {"story_id": "S1", "criterion_id": "C", "record": {}})),
                         self.state(*a))
        self.state(begin("S1"), ("probe/evaluated", {"story_id": "S1", "criterion_id": "C", "record": {}}))
        blocked = (begin("S1"), admit("S1", {"C": "PRE_SATISFIED", "D": "PRECONDITION_BROKEN"}))
        self.assertEqual(self.state(*blocked, drift("S1", "C", [])), self.state(*blocked))  # §14: still recorded
        ended = (*a, story("commit", "S1"), story("dispose", "S1"), story("end", "S1"))
        self.assertEqual(self.state(*ended, fail("S1", "POST_MERGE_REGRESSION")), self.state(*ended))

    def test_what_is_not_a_transition_refuses(self):
        msg = "^story_state: {} for story S1 in state {}: not a §17 transition$"
        cases = [((begin("S1"), begin("S1")), "story/begin", "BEGIN"),
                 ((begin("S1"), admit("S1", {"C": "READY"}), story("commit", "S1"), story("dispose", "S1"),
                   story("end", "S1"), begin("S1")), "story/begin", "ENDED"),
                 ((begin("S1"), fail("S1"), story("rollback", "S1", 2), story("dispose", "S1"), story("end", "S1"),
                   begin("S1")), "story/begin", "ENDED"),
                 ((admit("S1", {"C": "READY"}),), "story/admitted", "None"),
                 ((begin("S1"), admit("S1", {"C": "READY"}), admit("S1", {"C": "READY"})), "story/admitted", "ACTIVE"),
                 ((begin("S1"), admit("S1", {"C": "PROBE_INVALID"}), admit("S1", {"C": "READY"})), "story/admitted",
                  "BEGIN"),
                 ((begin("S1"), story("commit", "S1")), "story/commit", "BEGIN"),
                 ((begin("S1"), admit("S1", {"C": "READY"}), story("commit", "S1"), story("commit", "S1")),
                  "story/commit", "COMMIT"),
                 ((begin("S1"), admit("S1", {"C": "READY"}), story("commit", "S1"), fail("S1"),
                   story("rollback", "S1", 4)), "story/rollback", "COMMIT"),
                 ((begin("S1"), fail("S1"), story("retry", "S1", 2), story("dispose", "S1"), fail("S1"),
                   story("retry", "S1", 5)), "story/retry", "DISPOSE"),
                 ((begin("S1"), story("dispose", "S1")), "story/dispose", "BEGIN"),
                 ((begin("S1"), admit("S1", {"C": "READY"}), story("end", "S1")), "story/end", "ACTIVE"),
                 ((begin("S1"), admit("S1", {"C": "READY"}), story("commit", "S1"), story("end", "S1")), "story/end",
                  "COMMIT"),
                 ((begin("S1"), admit("S1", {"C": "READY"}), story("commit", "S1"),
                   ("probe/evaluated", {"story_id": "S1", "criterion_id": "C", "record": {}})), "probe/evaluated",
                  "COMMIT"),
                 ((begin("S1"), drift("S1", "C", [])), "story/plan-drift", "BEGIN"),
                 ((begin("S1"), request("S1", "C")), "provider/request", "BEGIN"),
                 ((fail("S1"),), "failure/observed", "None")]
        for specs, t, at in cases:
            with self.subTest(event=t, state=at, n=len(specs)):
                self.refused(*specs, msg=msg.format(t, at))


class FailureOwner(_Case):
    projection = P.FAILURE_OWNER

    def test_the_latest_failure_speaks_until_one_is_cited(self):
        got = self.state(begin("S1"), fail("S1"), fail("S1", "CONTRACT_UNSATISFIED"))["S1"]
        self.assertEqual(got, {"attempt": 1, "begin_seq": 1, "observed": {"2": ["ENVIRONMENT", "PROBE_UNRUNNABLE"],
                                                                         "3": ["DEVELOPER", "CONTRACT_UNSATISFIED"]},
                               "owner": "DEVELOPER", "code": "CONTRACT_UNSATISFIED", "failure_seq": 3, "cited": False})

    def test_a_rollback_carries_its_cited_failures_owner_never_a_later_one(self):
        got = self.state(begin("S1"), fail("S1"), fail("S1", "CONTRACT_UNSATISFIED"), story("rollback", "S1", 2),
                         fail("S1", "POST_MERGE_REGRESSION"))["S1"]
        self.assertEqual((got["owner"], got["code"], got["failure_seq"], got["cited"]),
                         ("ENVIRONMENT", "PROBE_UNRUNNABLE", 2, True))
        self.assertEqual(len(got["observed"]), 3)
        retry = self.state(begin("S1"), fail("S1", "PROVIDER_UNAVAILABLE"), story("retry", "S1", 2))["S1"]
        self.assertEqual((retry["owner"], retry["cited"]), ("PROVIDER", True))

    def test_a_new_attempt_starts_clean_and_cannot_cite_the_last_ones_failure(self):
        a = (begin("S1"), fail("S1"), story("retry", "S1", 2), story("dispose", "S1"), story("end", "S1"), begin("S1"))
        self.assertEqual(self.state(*a)["S1"], {"attempt": 2, "begin_seq": 6, "observed": {}, "owner": None,
                                                "code": None, "failure_seq": None, "cited": False})
        self.refused(*a, story("rollback", "S1", 2), msg="^failure_owner: story/rollback for story S1 cites seq 2, not "
                                                          "a failure of its attempt 2$")
        self.refused(fail("S1"), msg="^failure_owner: failure/observed for story S1, which has not begun$")


class Budgets(_Case):
    projection = P.BUDGETS

    def test_developer_budget_charges_ready_criteria_only(self):
        a = (begin("S1"), admit("S1", {"C": "READY", "D": "READY", "E": "PRE_SATISFIED"}))
        got = self.state(*a, request("S1", "C"), request("S1", "C", "D"))
        self.assertEqual(got["developer"], {"S1": {"requests": 2, "criteria": {"C": 2, "D": 1}}})
        self.assertEqual(got["admission"], {"S1": {"permitted": True, "ready": ["C", "D"]}})
        self.refused(*a, request("S1", "C", "E"), msg=r"^budgets: provider/request for S1 charges \['E'\], not admitted "
                                                      r"READY \(§14: PRE_SATISFIED consumes no developer budget\)$")
        self.refused(begin("S1"), request("S1", "C"), msg="^budgets: provider/request for S1, whose admission permits "
                                                          "no developer call$")
        self.refused(begin("S1"), admit("S1", {"E": "PRE_SATISFIED"}), request("S1", "E"), msg="permits no developer")
        self.refused(*a, fail("S1"), story("retry", "S1", 3), story("dispose", "S1"), story("end", "S1"),
                     begin("S1"), request("S1", "C"), msg="permits no developer call")

    def test_a_retry_charges_its_cited_failures_budget(self):
        got = self.state(begin("S1"), fail("S1"), fail("S1", "PROVIDER_UNAVAILABLE"), story("retry", "S1", 3),
                         story("dispose", "S1"), story("end", "S1"), begin("S1"), fail("S1"), story("retry", "S1", 8))
        self.assertEqual(got["retries"], {"S1": {"PROVIDER": 1, "ENVIRONMENT": 1}})
        self.refused(begin("S1"), fail("S1", "PROVIDER_UNAVAILABLE"), fail("S1", "INVALID_CREDENTIAL"),
                     story("retry", "S1", 2), msg=r"^budgets: story/retry for S1 cites seq 2, not its latest failure "
                                                  r"\(seq 3\): a retry never reaches past a newer failure$")
        self.refused(begin("S1"), fail("S1", "PROVIDER_UNAVAILABLE"), fail("S1", "CONTRACT_UNSATISFIED"),
                     story("retry", "S1", 2), msg="not its latest failure")
        self.assertEqual(got["failures"], {"S1": {"8": "ENVIRONMENT"}})
        self.assertEqual(self.state(begin("S1"), fail("S1", "PLAN_CONTRADICTION"))["failures"], {"S1": {"2": None}})
        self.refused(begin("S1"), fail("S1", "INVALID_CREDENTIAL"), story("retry", "S1", 2),
                     msg=r"^budgets: story/retry for S1 cites a non-retryable failure: no budget to charge \(§17\)$")
        self.refused(begin("S1"), fail("S1"), story("retry", "S1", 2), story("dispose", "S1"), story("end", "S1"),
                     begin("S1"), story("retry", "S1", 2), msg="^budgets: story/retry for S1 cites seq 2, not a failure "
                                                              "of its attempt$")

    def test_the_initial_state(self):
        self.assertEqual(self.state(), {"retries": {}, "developer": {}, "admission": {}, "failures": {}})
        self.assertEqual(self.state(begin("S1"), admit("S1", {"C": "READY"}), begin("S2"))["admission"],
                         {"S1": {"permitted": True, "ready": ["C"]}})


class RetryTarget(_Case):
    projection = P.RETRY_TARGET

    def test_the_budget_a_retry_would_charge(self):
        self.assertEqual(self.state(begin("S1")), {"S1": {"budget": None, "failure_seq": None}})
        self.assertEqual(self.state(begin("S1"), fail("S1")), {"S1": {"budget": "ENVIRONMENT", "failure_seq": 2}})
        self.assertEqual(self.state(begin("S1"), fail("S1"), fail("S1", "INVALID_CREDENTIAL")),
                         {"S1": {"budget": None, "failure_seq": 3}})
        self.assertEqual(self.state(begin("S1"), fail("S1", "CONTRACT_UNSATISFIED"), begin("S2"))["S1"]["budget"],
                         "DEVELOPER")
        self.assertEqual(self.state(begin("S1"), fail("S1"), story("retry", "S1", 2), story("dispose", "S1"),
                                    story("end", "S1"), begin("S1"))["S1"], {"budget": None, "failure_seq": None})
        self.refused(fail("S1"), msg="^retry_target: failure/observed for story S1, which has not begun$")


class TerminalState(_Case):
    projection = P.TERMINAL_STATE
    FIRST, SECOND = ("run/interrupted", {"abandoned": False}), ("run/interrupted", {"abandoned": True})

    def test_the_run(self):
        self.assertEqual(self.state(), {"run": "RUNNING", "interrupts": 0, "stories": {}, "pending": {}})
        first, second = self.FIRST, self.SECOND
        for specs, want, n in (((("run/dispose-begin", {}),), "DISPOSING", 0), ((first,), "INTERRUPTED", 1),
                               ((first, ("run/dispose-begin", {})), "DISPOSING", 1), ((first, second), "ABANDONED", 2),
                               ((first, ("run/dispose-begin", {}), second), "ABANDONED", 2),
                               ((("run/dispose-begin", {}), first), "INTERRUPTED", 1),
                               ((("run/dispose-begin", {}), first, second), "ABANDONED", 2),
                               ((("run/end", {}),), "ENDED", 0), ((("run/dispose-begin", {}), ("run/end", {})), "ENDED", 0),
                               ((first, ("run/end", {})), "ENDED", 1)):
            with self.subTest(events=[x[0] + str(x[1].get("abandoned", "")) for x in specs]):
                got = self.state(*specs)
                self.assertEqual((got["run"], got["interrupts"]), (want, n))
        for specs, msg in (((second,), "^terminal_state: run/interrupted while the run is RUNNING$"),
                           ((("run/dispose-begin", {}), second), r"^terminal_state: run/interrupted with abandoned True "
                                                                 r"after 0 interrupts: only a second interrupt abandons "
                                                                 r"\(§20.2\)$"),
                           ((first, ("run/dispose-begin", {}), first), "abandoned False after 1 interrupts"),
                           ((first, first), "run/interrupted while the run is INTERRUPTED"),
                           ((("run/dispose-begin", {}), ("run/dispose-begin", {})), "run/dispose-begin while the run "
                                                                                     "is DISPOSING"),
                           ((("run/end", {}), begin("S1")), "^terminal_state: story/begin after the run is ENDED$"),
                           ((("run/end", {}), ("gate/check", {"gate": "g", "check": "c", "passed": True, "detail": ""})),
                            "gate/check after the run is ENDED"),
                           ((first, second, ("run/end", {})), "run/end after the run is ABANDONED")):
            with self.subTest(msg=msg):
                self.refused(*specs, msg=msg)

    def test_each_story(self):
        commit = (begin("S1"), admit("S1", {"C": "READY"}), story("commit", "S1"), story("dispose", "S1"),
                  story("end", "S1"))
        self.assertEqual(self.state(*commit), {"run": "RUNNING", "interrupts": 0, "stories": {"S1": "COMMIT"},
                                               "pending": {}})
        self.assertEqual(self.state(*commit[:3])["pending"], {"S1": "COMMIT"})
        self.assertEqual(self.state(begin("S1"))["stories"], {"S1": "RUNNING"})
        retry = (begin("S2"), fail("S2"), story("retry", "S2", 2), story("dispose", "S2"), story("end", "S2"))
        self.assertEqual(self.state(*retry)["stories"], {"S2": "OPEN"})
        self.assertEqual(self.state(*retry, begin("S2"))["stories"], {"S2": "RUNNING"})
        self.assertEqual(self.state(begin("S3"), fail("S3"), story("rollback", "S3", 2), story("dispose", "S3"),
                                    story("end", "S3"))["stories"], {"S3": "ROLLBACK"})
        overlap = self.state(begin("S1"), begin("S2"), admit("S1", {"C": "READY"}), admit("S2", {"D": "READY"}),
                             story("commit", "S1"), story("commit", "S2"), story("dispose", "S1"), story("end", "S1"))
        self.assertEqual((overlap["stories"], overlap["pending"]), ({"S1": "COMMIT", "S2": "RUNNING"}, {"S2": "COMMIT"}))
        begin_msg = "^terminal_state: story/begin for {} \\({}\\) while the run is {}$"
        for specs, msg in ((commit + (begin("S1"),), begin_msg.format("S1", "COMMIT", "RUNNING")),
                           ((begin("S3"), fail("S3"), story("rollback", "S3", 2), story("dispose", "S3"),
                             story("end", "S3"), begin("S3")), begin_msg.format("S3", "ROLLBACK", "RUNNING")),
                           ((begin("S1"), begin("S1")), begin_msg.format("S1", "RUNNING", "RUNNING")),
                           ((("run/dispose-begin", {}), begin("S1")), begin_msg.format("S1", "None", "DISPOSING")),
                           ((self.FIRST, begin("S1")), begin_msg.format("S1", "None", "INTERRUPTED")),
                           ((story("commit", "S9"),), "^terminal_state: story/commit for S9, which has no open attempt "
                                                      "without an outcome$"),
                           ((begin("S1"), fail("S1"), story("rollback", "S1", 2), story("retry", "S1", 2)),
                            "story/retry for S1, which has no open attempt"),
                           ((*retry, story("commit", "S2")), "story/commit for S2, which has no open attempt"),
                           ((begin("S1"), story("end", "S1")), "^terminal_state: story/end for S1 with no transaction "
                                                               "outcome$")):
            with self.subTest(msg=msg):
                self.refused(*specs, msg=msg)


class QualificationCounters(_Case):
    projection = P.QUALIFICATION_COUNTERS

    def test_the_metrics_over_the_latest_admissions(self):
        p = plan(A="INTRODUCE", B="INTRODUCE", C="PRESERVE", D="INTRODUCE", E="VERIFY")
        got = self.state(p, begin("S1"), admit("S1", {"A": "PRE_SATISFIED", "B": "READY", "C": "READY"}),
                         begin("S2"), admit("S2", {"D": "PRE_SATISFIED"}), drift("S2", "D", []),
                         drift("S1", "A", ["S0"]), drift("S1", "A", []), begin("S3"), admit("S3", {"E": "READY"}))
        self.assertEqual(got["metrics"], {"introduce_obligations": 3, "pre_satisfied_introduce": 2,
                                          "pre_satisfied_introduce_ratio": 2 / 3, "fully_pre_satisfied_stories": 1,
                                          "plan_drift": 2, "unattributed_plan_drift": 2})
        self.assertEqual(got["drift"], {"S2": {"D": "UNATTRIBUTED"}, "S1": {"A": "UNATTRIBUTED"}})
        retried = self.state(p, begin("S1"), admit("S1", {"A": "PRE_SATISFIED", "B": "READY"}), fail("S1"),
                             story("retry", "S1", 4), story("dispose", "S1"), story("end", "S1"), begin("S1"),
                             admit("S1", {"A": "READY", "B": "READY"}))
        self.assertEqual((retried["metrics"]["pre_satisfied_introduce"], retried["metrics"]["introduce_obligations"]),
                         (0, 2))
        self.assertEqual(self.state(p)["metrics"]["pre_satisfied_introduce_ratio"], None)
        q = plan(A="INTRODUCE", B="INTRODUCE", D="INTRODUCE", F="INTRODUCE", G="INTRODUCE", H="INTRODUCE")
        two = self.state(q, begin("S1"), admit("S1", {"A": "READY"}), begin("S2"), admit("S2", {"B": "READY"}),
                         begin("S5"), admit("S5", {"H": "READY"}), begin("S3"), admit("S3", {"D": "PRE_SATISFIED"}),
                         drift("S3", "D", ["S1"]), begin("S4"), admit("S4", {"F": "PRE_SATISFIED", "G": "READY"}),
                         drift("S4", "F", []))
        self.assertEqual((two["metrics"]["fully_pre_satisfied_stories"], two["metrics"]["plan_drift"],
                          two["metrics"]["unattributed_plan_drift"]), (1, 2, 1))
        self.assertEqual(two["drift"], {"S3": {"D": "S1"}, "S4": {"F": "UNATTRIBUTED"}})

    def test_drift_belongs_to_the_latest_admission(self):
        p = plan(A="INTRODUCE", B="INTRODUCE", C="PRESERVE")
        first = (p, begin("S1"), admit("S1", {"A": "PRE_SATISFIED", "B": "PRE_SATISFIED"}), drift("S1", "A", []),
                 drift("S1", "B", []))
        self.assertEqual(self.state(*first)["drift"], {"S1": {"A": "UNATTRIBUTED", "B": "UNATTRIBUTED"}})
        again = self.state(*first, fail("S1"), story("retry", "S1", 6), story("dispose", "S1"), story("end", "S1"),
                           begin("S1"), admit("S1", {"A": "READY", "B": "READY"}))
        self.assertEqual((again["drift"], again["metrics"]["plan_drift"]), ({}, 0))
        self.refused(p, begin("S1"), admit("S1", {"A": "READY"}), drift("S1", "A", []),
                     msg="^qualification_counters: story/plan-drift for S1 names A, not PRE_SATISFIED in its latest "
                         "admission$")
        self.refused(p, begin("S1"), drift("S1", "A", []), msg="names A, not PRE_SATISFIED")
        self.refused(p, begin("S1"), admit("S1", {"C": "PRE_SATISFIED"}),
                     msg=r"^qualification_counters: story/admitted for S1 records \['C'\] PRE_SATISFIED, not "
                         r"INTRODUCE obligations \(§13\)$")

    def test_the_delivery_counts(self):
        got = self.state(plan(A="INTRODUCE"), begin("S1"), admit("S1", {"A": "READY"}), story("commit", "S1"),
                         begin("S2"), fail("S2"), fail("S2", "CONTRACT_UNSATISFIED"), story("rollback", "S2", 6),
                         begin("S3"), fail("S3"), story("retry", "S3", 10))
        self.assertEqual({k: got[k] for k in ("committed", "rolled_back", "retries", "failures")},
                         {"committed": 1, "rolled_back": 1, "retries": 1,
                          "failures": {"ENVIRONMENT": 2, "DEVELOPER": 1}})
        self.assertEqual(got["roles"], {"A": "INTRODUCE"})
        self.assertEqual(got["admissions"], {"S1": {"A": "READY"}})

    def test_the_plan_is_frozen_once_and_admissions_name_its_criteria(self):
        self.refused(plan(A="INTRODUCE"), plan(A="INTRODUCE"), msg="^qualification_counters: a second plan/frozen — a "
                                                                  "run freezes one plan$")
        self.refused(begin("S1"), admit("S1", {"A": "READY"}), msg=r"^qualification_counters: story/admitted for S1 "
                                                                   r"names \['A'\], not criteria of the frozen plan$")
        self.refused(plan(A="INTRODUCE"), begin("S1"), admit("S1", {"A": "READY", "Z": "READY"}), msg=r"\['Z'\]")


if __name__ == "__main__":
    unittest.main()
