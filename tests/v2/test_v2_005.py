"""ARCHITECTURE-EXCEPTION-V2-005 — the amendment-specific tests the owner's resolution requires before WP-6.2 resumes.

FMT3-1..8 (journal format 3, its catalog, and the formats it leaves exactly as written), the exact nine failure codes
of RFC §22.1 with their owner, retryability and budget, `budget_owner` on a format-3 provider request and the version-2
budgets projection that charges it, the version-2 story_state, `invariant/violated` as evidence that no projection
reads, the runtime writing format 3 while reading and repairing every format as written, the reference models on
format-3 traces, and the amendment lineage itself (V2-003 -> V2-005; V2-004 superseded, never applied).
"""

import importlib.util
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict as V, ControlProjection as P, Enforcement as E, EventType as T, Owner,
    Relevance as R, TestExecutionStatus as X, TestOutcome as TO, TestSelection as TS, Vacuity as VA,
)
from aisef2.control import budget  # noqa: E402
from aisef2.control.owner import (  # noqa: E402
    FORMAT_2_CODES, TAXONOMY, V2_005_CODES, FailureCode, Retryability, classify, flatten,
)
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.journal import compat, event as ev, format2 as f2, format3 as f3  # noqa: E402
from aisef2.journal.event import GENESIS, Event, JournalError, carried, encode, link  # noqa: E402
from aisef2.journal.fold import Authority, ProjectionError, fold  # noqa: E402
from aisef2.journal.projections import PROJECTIONS  # noqa: E402
from aisef2.journal.projections.budgets import Budgets  # noqa: E402
from aisef2.journal.projections.story_state import StoryState  # noqa: E402
from aisef2.journal.writer import JournalWriter  # noqa: E402
from aisef2.probe.protocol import ProbeRecord  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402
from aisef2.product.outcome import Executed, Unrunnable  # noqa: E402
from aisef2.quality.adequacy import assemble  # noqa: E402
from aisef2.quality.test_execution import TestExecution, to_json  # noqa: E402
from aisef2.runtime import repair as rp, sentinel  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from tests.v2.p3 import journal_gen as gen  # noqa: E402
from tests.v2.p3 import test_reference_models as h  # noqa: E402
from tests.v2.p4.test_run_scope import spec as RUN_SPEC  # noqa: E402
from tests.v2.p4.world import closed_after  # noqa: E402
from tests.v2.refmodel import CALIBRATIONS, MODELS  # noqa: E402

SHA = "a" * 40
NINE = {"VERIFIER_DISAGREEMENT": ("INTEGRATION", False), "PROBE_MISMATCH": ("INTEGRATION", False),
        "MERGE_CONFLICT": ("INTEGRATION", False), "TESTS_UNRUNNABLE": ("ENVIRONMENT", True),
        "TESTS_INADEQUATE": ("DEVELOPER", True), "REVIEW_FINDING": ("REVIEW", True), "SECURITY_FINDING": ("SECURITY", True),
        "CAPABILITY_UNRUNNABLE": ("ENVIRONMENT", True), "RESOURCE_ACQUISITION_FAILED": ("ENVIRONMENT", True)}
THIRTEEN = ("PROBE_UNRUNNABLE", "PROBE_INVALID_SPEC", "CONTRACT_UNSATISFIED", "SUBJECT_ABSENT_AT_CANDIDATE",
            "PRECONDITION_BROKEN", "PLAN_CONTRADICTION", "POST_MERGE_REGRESSION", "POST_MERGE_SUBJECT_LOST",
            "NON_CONTROLLER_SIGNAL", "MISSING_CREDENTIAL", "INVALID_CREDENTIAL", "PROVIDER_UNAVAILABLE", "UNKNOWN")
FOUR_NEW = ("plan/static-admitted", "proof/verified", "tests/adequacy", "invariant/violated")
V2 = ROOT / "validation/v2"
EVIDENCE = ROOT / "closure-evidence/v2"


def _load(name, rel):
    if name in sys.modules:
        return sys.modules[name]
    s = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(s)
    sys.modules[name] = m
    s.loader.exec_module(m)
    return m


# --------------------------------------------------------------------------------------- journal builders

def text_of(*specs, fmt=3, run_id="v2-005"):
    """Stored text of a journal declaring `fmt`: run/begin, then (type, data[, cites]) specs; owner/retryable carried."""
    all_specs = [("run/begin", {"journal_format": fmt, "run_id": run_id}, ())] + [(*s, ())[:3] for s in specs]
    return gen._text(all_specs, [float(n) for n in range(len(all_specs))])


def events_of(*specs, fmt=3):
    return f3.reconstruct(text_of(*specs, fmt=fmt)).events


def raw_text(specs):
    """Stored text from (type, data, cites, ignorable) specs — unknown types included, as a foreign writer would."""
    out, prev = [], GENESIS
    for n, (type_, data, cites, ignorable) in enumerate(specs):
        event = Event(n, type_, carried(type_, data), float(n), ignorable, tuple(cites))
        prev = link(prev, event)
        out.append(encode(event, prev))
    return "".join(out)


def outcome(fn, text):
    try:
        j = fn(text)
        return ("OK", j.events, j.chain, j.skipped, j.torn_tail)
    except JournalError as e:
        return (type(e).__name__, str(e))


def plan(roles=None):
    return ("plan/frozen", {"plan_id": "PLAN-1", "plan_hash": "b" * 64,
                            "roles": roles or {"C1": "INTRODUCE", "C2": "INTRODUCE"}})


def begin(s="S1"):
    return ("story/begin", {"story_id": s, "parent": SHA})


def admit(s="S1", d=None):
    d = {"C1": "READY", "C2": "PRE_SATISFIED"} if d is None else d
    blocked = any(v in ("PRECONDITION_BROKEN", "PLAN_CONTRADICTION", "PROBE_UNRUNNABLE", "PROBE_INVALID")
                  for v in d.values())
    return ("story/admitted", {"story_id": s, "parent": SHA, "admitted": not blocked,
                               "developer_call_permitted": not blocked and "READY" in d.values(), "dispositions": d})


def request(s, criteria, owner="DEVELOPER"):
    data = {"story_id": s, "criteria": list(criteria)}
    if owner is not None:
        data["budget_owner"] = owner
    return ("provider/request", data)


def fail(s, code):
    return ("failure/observed", {"story_id": s, "code": code, "detail": "",
                                 **({"original": "OSError"} if code == "UNKNOWN" else {})})


def story(t, s, *cites):
    return (f"story/{t}", {"story_id": s, **({"revision": SHA} if t == "commit" else {})}, tuple(cites))


def record(verdict=V.SATISFIED, spec="PPS-C1", probe="probe.x", digest="d" * 64, sh="c" * 64, rev=SHA, enf=E.FULL):
    result = Executed(verdict) if verdict is not None else Unrunnable("no interpreter")
    return plain(ProbeRecord.create(spec_id=spec, semantic_hash=sh, probe_id=probe, probe_digest=digest, revision=rev,
                                    enforcement=enf, result=result))


def evaluated(s, c, rec):
    return ("probe/evaluated", {"story_id": s, "criterion_id": c, "record": rec})


def verified(s, c, cites, agreement=True, verdict="SATISFIED", **over):
    d = {"story_id": s, "criterion_id": c, "spec_id": "PPS-C1", "semantic_hash": "c" * 64, "candidate": SHA,
         "agreement": agreement, **over}
    if verdict is not None:
        d["verdict"] = verdict
    return ("proof/verified", d, tuple(cites))


RAN = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None, "ran")
FAILED = TestExecution(X.EXECUTED, TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER, "failed")
UNRUNNABLE = TestExecution(X.UNRUNNABLE, None, None, Owner.ENVIRONMENT, "no interpreter")
INTEGRATION_GAP = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION, "cause unknown")


def adequacy_payload(s, assembly):
    """RFC §15.3 (V2-005): the typed assembly, field for field — the orchestration seam's serialisation."""
    a = assembly.adequacy
    d = {"story_id": s, "execution": to_json(a.execution), "vacuity": a.vacuity.value if a.vacuity else None,
         "relevance": a.relevance.value if a.relevance else None, "regressions": to_json(a.regressions),
         "outcome": a.outcome.value if a.outcome else None, "owner": assembly.owner.value if assembly.owner else None,
         "may_block": assembly.may_block, "developer_chargeable": assembly.developer_chargeable}
    if assembly.chronology is not None:
        d["chronology"] = dict(assembly.chronology)
    return d


def adequacy(s, execution=RAN, vacuity=VA.NON_VACUOUS, relevance=R.RELEVANT, regressions=RAN, **over):
    if execution.status is X.UNRUNNABLE:
        vacuity = relevance = None  # §15.0 rule 1: nothing is measured
    return ("tests/adequacy", {**adequacy_payload(s, assemble(execution, vacuity, relevance, regressions)), **over})


def static_admitted(plan_id="PLAN-1", passed=True, n=9, **over):
    checks = [{"number": i, "name": f"check-{i}", "passed": passed, "problems": [] if passed else ["x"]}
              for i in range(1, n + 1)]
    return ("plan/static-admitted", {"plan_id": plan_id, "engine_digest": "e" * 64, "admitted": passed, "checks": checks,
                                     "result_digest": "f" * 64, **over})


def violated(inv="IV", ctx=None):
    return ("invariant/violated", {"invariant": inv, "module": "tests.v2.test_v2_005",
                                   "context": {"note": "diagnostic"} if ctx is None else ctx})


def cap(name="dev", grade="VERIFIED", enforcement="FULL"):
    return ("capability/resolved", {"name": name, "grade": grade, "enforcement": enforcement,
                                    "binding": {"digest": "d" * 64}, "identity": "e" * 64})


def acquired(s, resource, kind="SESSION"):
    return ("story/resource-acquired", {"story_id": s, "resource": resource, "kind": kind})


def released(s, resource, cite, kind="SESSION"):
    return ("story/resource-released", {"story_id": s, "resource": resource, "kind": kind, "status": "RELEASED",
                                        "detail": "", "synthetic": False}, (cite,))


ACTIVE = (plan(), begin(), admit())  # seq 1, 2, 3 in a fresh journal


def moved(state):
    """A projection state with every seq it names doubled: what interleaving one ignored event before every real one
    does to the seqs, and nothing else."""
    if isinstance(state, dict):
        return {(str(2 * int(k)) if k.isdigit() else k): (2 * v if (k.endswith("seq") or k == "observed")
                                                        and isinstance(v, int) else moved(v)) for k, v in state.items()}
    if isinstance(state, list):
        return [moved(v) for v in state]
    return state


# --------------------------------------------------------------------------------------- FMT3-1, FMT3-2

class Catalog(unittest.TestCase):
    def test_FMT3_1_every_event_type_has_a_format_3_schema(self):
        self.assertEqual(set(f3.SCHEMAS), {t.value for t in T})
        self.assertEqual((len(f3.SCHEMAS), len(f3.WRITABLE), f3.FORMAT, tuple(f3.KNOWN_FORMATS)), (29, 29, 3, (1, 2, 3)))
        self.assertEqual(f3.WRITABLE, frozenset(f3.SCHEMAS))
        for t in FOUR_NEW:
            with self.subTest(type=t):
                self.assertIn(t, f3.SCHEMAS)
                self.assertNotIn(t, ev.SCHEMAS)
                self.assertNotIn(t, f2.SCHEMAS)
        # formats 1 and 2 are exactly what they were: 18 and 25 writable types, the same schema objects
        self.assertEqual((len(ev.SCHEMAS), len(f2.WRITABLE)), (18, 25))
        untouched = set(f2.WRITABLE) - {"run/begin", "failure/observed", "provider/request"}
        for t in untouched:
            self.assertIs(f3.SCHEMAS[t], f2.SCHEMAS.get(t, ev.SCHEMAS.get(t)), t)

    def test_FMT3_2_a_missing_schema_fails_the_catalog_check_and_the_reader(self):
        fc = _load("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
        rfc = fc.RFC((ROOT / fc.RFC_REL).read_text(encoding="utf-8"))
        self.assertEqual(fc._journal_format_3_matches_rfc(rfc)["state"], fc.PASS)
        for missing in FOUR_NEW + ("failure/observed", "gate/check"):
            with self.subTest(missing=missing):
                short = {k: v for k, v in f3.SCHEMAS.items() if k != missing}
                with mock.patch.object(f3, "SCHEMAS", short), mock.patch.object(f3, "WRITABLE", frozenset(short)):
                    self.assertEqual(fc._journal_format_3_matches_rfc(rfc)["state"], fc.FAIL)
                    with self.assertRaisesRegex(JournalError, f"{missing} is not in the event vocabulary"):
                        f3.validate(Event(1, missing, {}, 1.0, False, ()), events_of()[:1])
        # the writer refuses the same event before the log grows
        with tempfile.TemporaryDirectory(prefix="aisef2-v2005-") as d:
            w = f3.JournalWriter3(pathlib.Path(d) / "j.jsonl", clock=lambda: 0.0)
            w.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r"})
            size = (pathlib.Path(d) / "j.jsonl").stat().st_size
            short = {k: v for k, v in f3.SCHEMAS.items() if k != "plan/static-admitted"}
            with mock.patch.object(f3, "SCHEMAS", short):
                with self.assertRaisesRegex(JournalError, "is not in the event vocabulary"):
                    w.append(T.PLAN_STATIC_ADMITTED, static_admitted()[1])
            w.close()
            self.assertEqual((pathlib.Path(d) / "j.jsonl").stat().st_size, size)


# --------------------------------------------------------------------------------------- FMT3-3, FMT3-5, FMT3-7

class Compatibility(unittest.TestCase):
    FIXTURES = ROOT / "tests/v2/fixtures/journal"

    def test_FMT3_3_every_format_1_and_format_2_journal_reads_identically_through_the_format_3_reader(self):
        seen = {1: 0, 2: 0}
        for path in sorted(self.FIXTURES.glob("*.jsonl")):
            text = path.read_bytes().decode("utf-8")
            fmt = f3.declared_format(text)
            with self.subTest(fixture=path.name, format=fmt):
                own = f2.reconstruct if fmt == 2 else compat.reconstruct
                self.assertEqual(outcome(f3.reconstruct, text), outcome(own, text))
                seen[fmt if fmt in seen else 1] += 1
        for seed in range(40):
            text = gen.journal(seed, stories=2 + seed % 4)
            with self.subTest(seed=seed):
                self.assertEqual(outcome(f3.reconstruct, text), outcome(compat.reconstruct, text))
        two = text_of(cap(), *ACTIVE, acquired("S1", "wt"), request("S1", ["C1"], None), released("S1", "wt", 5),
                      story("commit", "S1"), story("dispose", "S1"), story("end", "S1"), ("run/end", {}), fmt=2)
        self.assertEqual(outcome(f3.reconstruct, two), outcome(f2.reconstruct, two))
        self.assertEqual(outcome(f3.reconstruct, two)[0], "OK")
        self.assertTrue(seen[1] >= 1)

    def test_FMT3_5_a_reader_reads_a_journal_under_its_declared_format_and_guesses_nothing(self):
        three = text_of(*ACTIVE, request("S1", ["C1"]), fail("S1", "MERGE_CONFLICT"))
        self.assertEqual(outcome(f3.reconstruct, three)[0], "OK")
        self.assertEqual(outcome(compat.reconstruct, three),
                         ("JournalError", "run/begin: journal format 3 is not format 1: refused, never read under "
                                          "another format"))
        self.assertEqual(outcome(f2.reconstruct, three),
                         ("JournalError", "journal format 3 is neither format 1 nor format 2: refused"))
        for fmt in (0, 4, 99):
            with self.subTest(format=fmt):
                self.assertEqual(outcome(f3.reconstruct, text_of(fmt=fmt)),
                                 ("JournalError", f"journal format {fmt} is none of the formats this reader knows "
                                                  "[1, 2, 3]: refused"))
        # format-3 semantics in a format-1 or format-2 journal are refused by every reader, never read as format 3
        for fmt in (1, 2):
            for name, spec in (("a V2-005 code", fail("S1", "VERIFIER_DISAGREEMENT")),
                               ("budget_owner", request("S1", ["C1"], "REVIEW")),
                               ("a proof", verified("S1", "C1", (2, 3), verdict=None, agreement=False)),
                               ("an adequacy", adequacy("S1"))):
                with self.subTest(format=fmt, semantics=name):
                    text = text_of(*ACTIVE, spec, fmt=fmt)
                    own = compat.reconstruct if fmt == 1 else f2.reconstruct
                    self.assertEqual(outcome(own, text)[0], "JournalError")
                    self.assertEqual(outcome(f3.reconstruct, text), outcome(own, text))
        # the same events are legal in format 3
        recs = (evaluated("S1", "C1", record()), evaluated("S1", "C1", record()))
        ok = text_of(*ACTIVE, *recs, verified("S1", "C1", (4, 5)), request("S1", ["C1"], "REVIEW"), adequacy("S1"),
                     fail("S1", "VERIFIER_DISAGREEMENT"))
        self.assertEqual(outcome(f3.reconstruct, ok)[0], "OK")

    def test_FMT3_7_no_format_1_or_format_2_journal_is_rewritten_extended_or_upgraded(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-v2005-") as d:
            d = pathlib.Path(d)
            one, two = d / "one.jsonl", d / "two.jsonl"
            w = JournalWriter(one, clock=lambda: 0.0)
            w.append(T.RUN_BEGIN, {"journal_format": 1, "run_id": "r"})
            w.close()
            w = f2.JournalWriter2(two, clock=lambda: 0.0)
            w.append(T.RUN_BEGIN, {"journal_format": 2, "run_id": "r"})
            w.append(T.PLAN_FROZEN, plan()[1])
            w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
            w.append(T.STORY_ADMITTED, admit()[1])
            w.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"]})
            w.close()
            before = {p: p.read_bytes() for p in (one, two)}
            for p in (one, two):
                fmt = f3.declared_format(p.read_bytes().decode("utf-8"))
                with self.assertRaisesRegex(JournalError, f"is a format-{fmt} journal: it is read, never extended "
                                                          "under another format"):
                    f3.JournalWriter3(p)
            self.assertEqual({p: p.read_bytes() for p in (one, two)}, before)
            # repair writes format-2 closers for the format-2 journal, format-3 closers for a format-3 one
            fixed = rp.repair(two.read_bytes().decode("utf-8"))
            self.assertTrue(fixed.startswith(before[two].decode("utf-8")))
            closers = f2.reconstruct(fixed).events[5:]
            self.assertEqual([e.type for e in closers], ["provider/result", "run/interrupted", "run/end"])
            # a closer of either format is validated by the same schema object: repair validates once, under format 3
            for closer in ("provider/result", "story/resource-released", "tool/result", "run/interrupted", "run/end"):
                self.assertIs(f3.SCHEMAS[closer], f2.SCHEMAS[closer], closer)
            for e in closers:  # the format-2 closers written for the format-2 journal validate under format 2 alone
                f2.validate(e, f2.reconstruct(fixed).events[:e.seq])
            self.assertNotIn("budget_owner", json.dumps(fixed))
            self.assertEqual(f3.declared_format(fixed), 2)
            with self.assertRaisesRegex(rp.RepairError, "a format-1 journal is read, never extended"):
                rp.repair(one.read_bytes().decode("utf-8"))
            self.assertEqual({p: p.read_bytes() for p in (one, two)}, before)
            # a format-3 journal is never extended by the format-2 writer either
            three = d / "three.jsonl"
            w = f3.JournalWriter3(three, clock=lambda: 0.0)
            w.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r"})
            w.close()
            with self.assertRaisesRegex(JournalError, "journal format 3 is neither format 1 nor format 2: refused"):
                f2.JournalWriter2(three)


# --------------------------------------------------------------------------------------- FMT3-4, FMT3-6, FMT3-8

class Schemas(unittest.TestCase):
    def refused(self, msg, *specs, prefix=ACTIVE):
        with self.assertRaisesRegex(JournalError, msg):
            events_of(*prefix, *specs)

    def test_FMT3_4_a_missing_required_field_refuses_the_append_before_the_log_grows(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-v2005-") as d:
            p = pathlib.Path(d) / "j.jsonl"
            w = f3.JournalWriter3(p, clock=lambda: 0.0)
            w.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r"})
            for spec in ACTIVE:
                w.append(T(spec[0]), spec[1])
            size, n = p.stat().st_size, len(w.events)
            cases = {
                "provider/request without budget_owner": (T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"]},
                                                          "fields missing \\['budget_owner'\\]"),
                "proof/verified without agreement": (T.PROOF_VERIFIED, {k: v for k, v in verified("S1", "C1", ())[1].items()
                                                                        if k != "agreement"}, "fields missing \\['agreement'\\]"),
                "tests/adequacy without may_block": (T.TESTS_ADEQUACY, {k: v for k, v in adequacy("S1")[1].items()
                                                                        if k != "may_block"}, "fields missing \\['may_block'\\]"),
                "plan/static-admitted without checks": (T.PLAN_STATIC_ADMITTED, {k: v for k, v in static_admitted()[1].items()
                                                                                 if k != "checks"}, "fields missing \\['checks'\\]"),
                "invariant/violated without module": (T.INVARIANT_VIOLATED, {"invariant": "I", "context": {}},
                                                      "fields missing \\['module'\\]"),
                "a field outside the schema": (T.INVARIANT_VIOLATED, {**violated()[1], "owner": "DEVELOPER"},
                                               "not in the schema \\['owner'\\]"),
            }
            for name, (t, data, msg) in cases.items():
                with self.subTest(case=name):
                    with self.assertRaisesRegex(JournalError, msg):
                        w.append(t, data)
                    self.assertEqual((p.stat().st_size, len(w.events)), (size, n))
            w.close()

    def test_FMT3_6_a_format_3_provider_request_names_one_of_the_three_budget_owners(self):
        self.assertIn("budget_owner", f3.SCHEMAS["provider/request"].required)
        self.assertNotIn("budget_owner", ev.SCHEMAS["provider/request"].required)
        self.assertEqual([o.value for o in f3.BUDGET_OWNERS], ["DEVELOPER", "REVIEW", "SECURITY"])
        for owner in ("DEVELOPER", "REVIEW", "SECURITY"):
            with self.subTest(owner=owner):
                self.assertEqual(events_of(*ACTIVE, request("S1", ["C1"], owner))[-1].data["budget_owner"], owner)
        self.refused("fields missing \\['budget_owner'\\]", request("S1", ["C1"], None))
        for owner in ("PLAN", "ENVIRONMENT", "PROVIDER", "INTEGRATION", "developer", "", None, 1):
            with self.subTest(owner=owner):
                self.refused("fields of the wrong kind or enum \\['budget_owner'\\]",
                             ("provider/request", {"story_id": "S1", "criteria": ["C1"], "budget_owner": owner}))

    def test_FMT3_8_the_context_of_an_invariant_violation_cannot_affect_any_projection(self):
        hostile = [{"owner": "DEVELOPER", "retryable": True, "story_id": "S1", "code": "CONTRACT_UNSATISFIED"},
                   {"journal_format": 1, "dispositions": {"C1": "READY"}, "developer_call_permitted": True},
                   {"budget_owner": "DEVELOPER", "criteria": ["C1"], "gate": "commit", "passed": False}, {}, {"x": [1, 2]}]
        base = (*ACTIVE, request("S1", ["C1"]), fail("S1", "REVIEW_FINDING"), story("retry", "S1", 5),
                story("dispose", "S1"), story("end", "S1"))
        noisy = []
        for n, (t, data, *cites) in enumerate(base):
            noisy += [violated(["I", "IV", "VII", "IX"][n % 4], hostile[n % len(hostile)]),
                      (t, data, tuple(2 * c for c in (cites[0] if cites else ())))]
        noisy.append(violated("VIII", hostile[0]))
        clean, loud = events_of(*base), events_of(*noisy)
        self.assertEqual(len(loud), len(clean) + len(base) + 1)
        self.assertEqual(loud[10].type, "failure/observed")
        for pid, p in PROJECTIONS.items():
            with self.subTest(projection=pid.value):
                a, b = plain(fold(p, clean)), plain(fold(p, loud))
                self.assertEqual(moved(a), b)  # every seq-keyed fact moved by exactly the interleaving; nothing else
        # the Authority pre-check admits it in every run state, and no projection names it
        with tempfile.TemporaryDirectory(prefix="aisef2-v2005-") as d:
            w = f3.JournalWriter3(pathlib.Path(d) / "j.jsonl", clock=lambda: 0.0)
            auth = Authority(w, PROJECTIONS.values())
            auth.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r"})
            auth.append(T.INVARIANT_VIOLATED, violated("II", hostile[0])[1])
            for spec in ACTIVE:
                auth.append(T(spec[0]), spec[1])
            auth.append(T.INVARIANT_VIOLATED, violated("III", hostile[1])[1])
            auth.append(T.RUN_DISPOSE_BEGIN, {})
            auth.append(T.INVARIANT_VIOLATED, violated("V", hostile[2])[1])
            self.assertEqual(auth.state(P.BUDGETS.value)["developer"], {})
            w.close()
        src = "".join((ROOT / "aisef2/journal/projections" / f).read_text(encoding="utf-8")
                      for f in os.listdir(ROOT / "aisef2/journal/projections") if f.endswith(".py"))
        self.assertNotIn("INVARIANT_VIOLATED", src)
        self.assertNotIn("invariant/violated", src)

    def test_a_static_admission_is_the_typed_result_once_per_plan(self):
        e = events_of(static_admitted())[-1]
        self.assertEqual((e.data["admitted"], len(e.data["checks"])), (True, 9))
        self.assertEqual(events_of(static_admitted(passed=False))[-1].data["admitted"], False)
        self.refused("admitted is true exactly when every check passed", static_admitted(admitted=False), prefix=())
        self.refused("fields of the wrong kind or enum \\['checks'\\]", static_admitted(n=0), prefix=())
        self.refused("^plan/static-admitted: plan 'PLAN-1' is statically admitted once per run$", static_admitted(),
                     static_admitted(), prefix=())
        bad = static_admitted()[1]["checks"]
        bad[3] = {**bad[3], "passed": False}  # passed with no problems
        self.refused("fields of the wrong kind or enum \\['checks'\\]", ("plan/static-admitted", {**static_admitted()[1],
                                                                                                   "checks": bad}), prefix=())

    def test_a_proof_is_two_cited_sealed_records_with_one_instrument_and_the_agreement_they_state(self):
        a, b = evaluated("S1", "C1", record()), evaluated("S1", "C1", record())
        e = events_of(*ACTIVE, a, b, verified("S1", "C1", (4, 5)))[-1]
        proof = f3.verified_proof(e, events_of(*ACTIVE, a, b)[:6])
        self.assertEqual(proof, {"spec_id": "PPS-C1", "candidate_sha": SHA, "implementer_result": a[1]["record"]["result"],
                                 "verifier_result": b[1]["record"]["result"], "agreement": True, "verdict": "SATISFIED"})
        # lossless: nothing but the two immutable records and the event's own fields
        self.assertEqual(set(proof), {"spec_id", "candidate_sha", "implementer_result", "verifier_result", "agreement", "verdict"})
        # disagreement: agreement False, no verdict; the story's failure is VERIFIER_DISAGREEMENT, never arbitrated
        c = evaluated("S1", "C1", record(V.REFUTED))
        e = events_of(*ACTIVE, a, c, verified("S1", "C1", (4, 5), agreement=False, verdict=None),
                      fail("S1", "VERIFIER_DISAGREEMENT"))
        self.assertEqual(f3.verified_proof(e[-2], e[:-2])["verdict"], None)
        self.assertEqual((e[-1].data["owner"], e[-1].data["retryable"]), ("INTEGRATION", False))
        self.refused("^proof/verified: agreement is False by the two records, not True$", a, c, verified("S1", "C1", (4, 5)))
        self.refused("a verdict is set only when agreement is true", a, c,
                     verified("S1", "C1", (4, 5), agreement=False, verdict="REFUTED"))
        u = evaluated("S1", "C1", record(None))  # two UNRUNNABLE results agree and carry no verdict
        self.assertEqual(f3.verified_proof(events_of(*ACTIVE, u, u, verified("S1", "C1", (4, 5), verdict=None))[-1],
                                           events_of(*ACTIVE, u, u))["verdict"], None)
        self.refused("the two results carry no verdict: none is set", u, u, verified("S1", "C1", (4, 5)))
        self.refused("the verdict is 'SATISFIED' by the two records", a, b, verified("S1", "C1", (4, 5), verdict="REFUTED"))
        self.refused("the verdict is 'SATISFIED' by the two records", a, b, verified("S1", "C1", (4, 5), verdict=None))
        # instrument identity: any mismatch is PROBE_MISMATCH — a failure, never a proof
        for field, other in (("probe", "probe.y"), ("digest", "9" * 64), ("enf", E.PARTIAL)):
            with self.subTest(mismatch=field):
                m = evaluated("S1", "C1", record(**{field: other}))
                self.refused("PROBE_MISMATCH is a failure/observed, never a proof", a, m, verified("S1", "C1", (4, 5)))
        self.refused("^proof/verified: cites 4: the record answers PPS-C1 at aaaaaaaaaaaa, not this spec at this candidate$",
                     a, b, verified("S1", "C1", (4, 5), candidate="b" * 40))
        self.refused("^proof/verified: cites 3: not a probe/evaluated of S1 / C1$", a, b, verified("S1", "C1", (3, 4)))
        self.refused("^proof/verified: cites exactly two probe/evaluated records: the implementer's, then the verifier's "
                     "\\(§16\\)$", a, b, verified("S1", "C1", (4,)))
        self.refused("^proof/verified: cites 5: its record is not a sealed ProbeRecord$", a,
                     evaluated("S1", "C1", {"result": {"status": "x"}}), verified("S1", "C1", (4, 5)))
        for key in ("spec_id", "semantic_hash", "revision", "result", "probe_id", "probe_digest", "enforcement"):
            with self.subTest(missing=key):  # every field of the sealed record is required, none is optional
                partial = {k: v for k, v in record().items() if k != key}
                self.refused("^proof/verified: cites 5: its record is not a sealed ProbeRecord$", a,
                             evaluated("S1", "C1", partial), verified("S1", "C1", (4, 5)))
        self.refused("S1 has no open attempt", a, b, story("commit", "S1"), story("dispose", "S1"), story("end", "S1"),
                     verified("S1", "C1", (4, 5)))

    def test_an_adequacy_record_is_the_typed_assembly_under_the_two_axis_rules(self):
        cases = {
            "ADEQUATE": (dict(), ("ADEQUATE", None, False, False)),
            "INADEQUATE": (dict(execution=FAILED), ("INADEQUATE", "DEVELOPER", True, True)),
            "UNRUNNABLE story tests": (dict(execution=UNRUNNABLE), (None, "ENVIRONMENT", False, False)),
            "UNRUNNABLE regressions": (dict(regressions=UNRUNNABLE), (None, "ENVIRONMENT", False, False)),
            "INCOMPLETE (integration-owned collection)": (dict(regressions=INTEGRATION_GAP), ("INCOMPLETE", None, False, False)),
            "INCOMPLETE (indeterminate vacuity)": (dict(vacuity=VA.INDETERMINATE), ("INCOMPLETE", None, False, False)),
        }
        for name, (kw, want) in cases.items():
            with self.subTest(case=name):
                d = events_of(*ACTIVE, adequacy("S1", **kw))[-1].data
                self.assertEqual((d["outcome"], d["owner"], d["may_block"], d["developer_chargeable"]), want)
        self.refused("^tests/adequacy: only INADEQUATE may block, under project policy \\(§15.3\\)$",
                     adequacy("S1", regressions=INTEGRATION_GAP, may_block=True))
        self.refused("developer_chargeable is exactly a DEVELOPER-owned result",
                     adequacy("S1", regressions=INTEGRATION_GAP, developer_chargeable=True))
        self.refused("an UNRUNNABLE mandatory execution produces no AdequacyOutcome",
                     adequacy("S1", execution=UNRUNNABLE, outcome="INADEQUATE"))
        self.refused("INADEQUATE is owned by DEVELOPER", adequacy("S1", execution=FAILED, owner=None))
        self.refused("ADEQUATE is charged to nobody", adequacy("S1", owner="DEVELOPER"))
        self.refused("both mandatory executions EXECUTED: the AdequacyOutcome is defined", adequacy("S1", outcome=None))
        self.refused("^tests/adequacy: S1 has no open attempt$", adequacy("S1"), prefix=(plan(),))
        # chronology is recorded verbatim, read for nothing
        d = events_of(*ACTIVE, ("tests/adequacy", adequacy_payload("S1", assemble(RAN, VA.NON_VACUOUS, R.RELEVANT, RAN,
                                                                                    chronology={"red": 1, "green": 2}))))[-1].data
        self.assertEqual(dict(d["chronology"]), {"red": 1, "green": 2})


class Validators(unittest.TestCase):
    """The format-3 payload validators are total boolean functions: every refusal branch answers False (never None,
    never an exception), and only the typed shape answers True."""

    def test_checks_answers_False_on_every_malformed_shape_and_True_on_the_typed_result(self):
        ok = tuple({"number": i, "name": f"c{i}", "passed": True, "problems": ()} for i in (1, 2))
        self.assertIs(f3._checks(ok), True)
        self.assertIs(f3._checks(ok + ({"number": 3, "name": "c3", "passed": False, "problems": ("x",)},)), True)
        bad = {"not a tuple": list(ok), "empty": (), "a non-mapping element": (5,), "a string element": ("check",),
               "wrong keys": ({"number": 1, "name": "c", "passed": True},), "an extra key": ({**ok[0], "detail": ""},),
               "misnumbered": ({**ok[0], "number": 2},), "numbered from 0": ({**ok[0], "number": 0},),
               "unnamed": ({**ok[0], "name": 7},), "passed not a bool": ({**ok[0], "passed": 1},),
               "problems not strings": ({**ok[0], "problems": (1,)},), "problems a list": ({**ok[0], "problems": []},),
               "passed with problems": ({**ok[0], "problems": ("x",)},), "failed without problems": ({**ok[0], "passed": False},),
               "second element wrong": (ok[0], 5)}
        for name, v in bad.items():
            with self.subTest(case=name):
                self.assertIs(f3._checks(v), False)

    def test_execution_answers_False_on_every_malformed_shape_and_True_on_the_typed_result(self):
        ran, unr = to_json(RAN), to_json(UNRUNNABLE)
        self.assertIs(f3._execution(ran), True)
        self.assertIs(f3._execution(unr), True)
        self.assertIs(f3._execution({**ran, "reason": None, "owner_on_failure": "DEVELOPER"}), True)
        bad = {"not a mapping": 5, "a string": "EXECUTED", "a list": list(ran.items()), "an extra key": {**ran, "extra": 1},
               "a missing key": {k: v for k, v in ran.items() if k != "reason"}, "bad status": {**ran, "status": "RAN"},
               "bad reason": {**ran, "reason": 7}, "bad owner": {**ran, "owner_on_failure": "OPS"},
               "unrunnable with an outcome": {**unr, "outcome": "PASSED"},
               "unrunnable with a selection": {**unr, "selection": "STORY_TESTS_RAN"},
               "unrunnable owned by the developer": {**unr, "owner_on_failure": "DEVELOPER"},
               "unrunnable without a reason": {**unr, "reason": None},
               "executed without an outcome": {**ran, "outcome": None}, "executed with a bad outcome": {**ran, "outcome": "OK"},
               "executed without a selection": {**ran, "selection": None}, "executed with a bad selection": {**ran, "selection": "ALL"}}
        for name, v in bad.items():
            with self.subTest(case=name):
                self.assertIs(f3._execution(v), False)


class Messages(unittest.TestCase):
    """Every refusal of format 3 names its rule exactly: the type, the seq, the rule (§20.4, §35)."""

    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-v2005-")
        self.addCleanup(self._d.cleanup)
        self.path = pathlib.Path(self._d.name) / "j.jsonl"

    def writer(self):
        w = f3.JournalWriter3(self.path, clock=lambda: 0.0)
        self.addCleanup(w.close)
        return w

    def test_a_writer_refuses_a_run_begin_that_declares_another_format(self):
        w = self.writer()
        for fmt in (1, 2, 4):
            with self.subTest(format=fmt):
                with self.assertRaisesRegex(JournalError, f"^run/begin: journal format {fmt} is not format 3: refused, never "
                                                          "read under another format$"):
                    w.append(T.RUN_BEGIN, {"journal_format": fmt, "run_id": "r"})
        self.assertEqual((w.events, self.path.stat().st_size), ((), 0))

    def test_validate_names_the_seq_rule_the_ignorable_rule_and_the_first_event_rule(self):
        prior = events_of()
        with self.assertRaisesRegex(JournalError, "^plan/frozen at seq 5, but the journal holds 1 events: seq == index$"):
            f3.validate(Event(5, "plan/frozen", plan()[1], 1.0, False, ()), prior)
        with self.assertRaisesRegex(JournalError, "^plan/frozen is a required event in format 3; it is never ignorable$"):
            f3.validate(Event(1, "plan/frozen", plan()[1], 1.0, True, ()), prior)
        with self.assertRaisesRegex(JournalError, "^plan/frozen at seq 0: a journal begins with run/begin, and only once$"):
            f3.validate(Event(0, "plan/frozen", plan()[1], 1.0, False, ()), ())
        with self.assertRaisesRegex(JournalError, "^run/begin at seq 1: a journal begins with run/begin, and only once$"):
            f3.validate(Event(1, "run/begin", {"journal_format": 3, "run_id": "r"}, 1.0, False, ()), prior)
        with self.assertRaisesRegex(JournalError, "^run/begin: fields missing \\['run_id'\\], not in the schema \\[\\]$"):
            f3.validate(Event(0, "run/begin", {"journal_format": 3}, 1.0, False, ()), ())
        with self.assertRaisesRegex(JournalError, "^run/begin: fields of the wrong kind or enum \\['run_id'\\]$"):
            f3.validate(Event(0, "run/begin", {"journal_format": 3, "run_id": 7}, 1.0, False, ()), ())

    def test_citations_are_checked_by_count_type_and_key_with_exact_reasons(self):
        with self.assertRaisesRegex(JournalError, "^plan/frozen cites no event in format 3$"):
            events_of(("plan/frozen", plan()[1], (0,)))
        result = {"story_id": "S1", "outcome": "COMPLETED", "synthetic": False, "detail": ""}
        with self.assertRaisesRegex(JournalError, "^provider/result cites exactly one provider/request$"):
            events_of(*ACTIVE, request("S1", ["C1"]), request("S1", ["C1"]), ("provider/result", result, (4, 5)))
        with self.assertRaisesRegex(JournalError, "^provider/result cites exactly one provider/request$"):
            events_of(*ACTIVE, request("S1", ["C1"]), ("provider/result", result, ()))
        with self.assertRaisesRegex(JournalError, "^gate/decision cites at least one gate/check$"):
            events_of(("gate/decision", {"gate": "commit", "passed": True, "projections": ["budgets"]}, ()))
        with self.assertRaisesRegex(JournalError, "^provider/result cites \\[4\\]: not a provider/request with the same story_id$"):
            events_of(*ACTIVE, request("S1", ["C1"]), ("provider/result", {**result, "story_id": "S2"}, (4,)))
        with self.assertRaisesRegex(JournalError, "^provider/result cites \\[3\\]: not a provider/request with the same story_id$"):
            events_of(*ACTIVE, request("S1", ["C1"]), ("provider/result", result, (3,)))

    def test_the_reader_reads_text_only_skips_ignorable_unknowns_and_refuses_required_unknowns(self):
        with self.assertRaisesRegex(JournalError, "^a journal is read as text$"):
            f3.reconstruct(b"{}\n")
        j = f3.reconstruct(text_of(*ACTIVE))
        self.assertEqual([type(x) for x in (j.events, j.chain, j.skipped)], [tuple, tuple, tuple])
        specs = [("run/begin", {"journal_format": 3, "run_id": "r"}, (), False), (*plan(), (), True),
                 ("x/ignored", {"a": 1}, (), True), (*begin(), (), False)]
        with self.assertRaisesRegex(JournalError, "^plan/frozen is a required event in format 3; it is never ignorable$"):
            f3.reconstruct(raw_text(specs))
        specs[1] = (*plan(), (), False)
        j = f3.reconstruct(raw_text(specs))
        self.assertEqual(([e.type for e in j.events], j.skipped, len(j.chain)),
                         (["run/begin", "plan/frozen", "story/begin"], (2,), 4))
        specs[2] = ("x/required", {"a": 1}, (), False)
        with self.assertRaisesRegex(JournalError, "^seq 2: unknown event type 'x/required' is not marked ignorable — this "
                                                  "reader refuses to reconstruct the journal \\(§20.4\\)$"):
            f3.reconstruct(raw_text(specs))

    def test_the_writer_names_why_it_refuses_untyped_failed_and_closed(self):
        w = self.writer()
        w.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r"})
        with self.assertRaisesRegex(JournalError, "^an event has a typed EventType$"):
            w.append("plan/frozen", plan()[1])
        size = self.path.stat().st_size
        with mock.patch("aisef2.journal.format3.os.write", return_value=3):
            with self.assertRaisesRegex(JournalError, "^append of plan/frozen at seq 1 failed \\(OSError: short write: 3 of "
                                                      "[0-9]+ bytes\\); the journal did not grow$"):
                w.append(T.PLAN_FROZEN, plan()[1])
        self.assertEqual((self.path.stat().st_size, len(w.events)), (size, 1))
        with self.assertRaisesRegex(JournalError, "^the writer failed \\(OSError: short write: 3 of [0-9]+ bytes\\) and "
                                                  "accepts nothing more$"):
            w.append(T.PLAN_FROZEN, plan()[1])
        closed = f3.JournalWriter3(pathlib.Path(self._d.name) / "k.jsonl", clock=lambda: 0.0)
        closed.close()
        with self.assertRaisesRegex(JournalError, "^the writer is closed$"):
            closed.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r"})

    def test_verified_proof_reconstructs_a_proof_only(self):
        with self.assertRaisesRegex(JournalError, "^story/begin is not a proof/verified$"):
            f3.verified_proof(events_of(*ACTIVE)[2], events_of(*ACTIVE)[:2])


# --------------------------------------------------------------------------------------- the nine codes (§7, §13)

class Taxonomy(unittest.TestCase):
    def test_FailureCode_is_exactly_the_thirteen_historical_codes_and_the_nine_of_V2_005(self):
        self.assertEqual([c.value for c in FailureCode], [*THIRTEEN, *NINE])
        self.assertEqual((set(FORMAT_2_CODES), set(V2_005_CODES)), (set(THIRTEEN), set(NINE)))
        self.assertEqual(set(TAXONOMY), set(FailureCode))
        self.assertFalse(set(FORMAT_2_CODES) & set(V2_005_CODES))
        self.assertNotIn("TESTS_NOT_COLLECTABLE_UNDETERMINED", {c.value for c in FailureCode})

    def test_each_of_the_nine_has_one_owner_one_retryability_and_its_own_budget(self):
        for code, (owner, retryable) in NINE.items():
            with self.subTest(code=code):
                c = classify(FailureCode(code))
                self.assertIs(c.code, FailureCode(code))
                self.assertEqual((c.owner.value, c.retryability is Retryability.RETRYABLE), (owner, retryable))
                self.assertEqual(c.budget, Owner(owner) if retryable else None)
                self.assertIn("V2-005", c.rule)
                written = carried("failure/observed", {"story_id": "S", "code": code, "detail": ""})
                self.assertEqual((written["owner"], written["retryable"]), (owner, retryable))
        self.assertEqual({o.value: [c.value for c, k in TAXONOMY.items() if k.owner is o and c.value in NINE] for o in Owner},
                         {"PLAN": [], "DEVELOPER": ["TESTS_INADEQUATE"],
                          "ENVIRONMENT": ["TESTS_UNRUNNABLE", "CAPABILITY_UNRUNNABLE", "RESOURCE_ACQUISITION_FAILED"],
                          "PROVIDER": [], "REVIEW": ["REVIEW_FINDING"], "SECURITY": ["SECURITY_FINDING"],
                          "INTEGRATION": ["VERIFIER_DISAGREEMENT", "PROBE_MISMATCH", "MERGE_CONFLICT"]})

    def test_no_call_site_supplies_owner_or_retryability_and_no_prose_becomes_a_code(self):
        ks = _load("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
        self.assertEqual(ks.check(ROOT, ("RETRYABLE_ONLY_IN_TAXONOMY", "NO_PROSE_CONTROL", "NO_SIDE_RETRY_COUNTER")), [])
        with self.assertRaisesRegex(JournalError, "owner and retryable come from the taxonomy, never from the call site"):
            carried("failure/observed", {"story_id": "S", "code": "REVIEW_FINDING", "owner": "DEVELOPER", "detail": ""})
        with self.assertRaisesRegex(JournalError, "not a taxonomy code; a foreign error flattens to UNKNOWN"):
            carried("failure/observed", {"story_id": "S", "code": "merge conflict in src/x.py", "detail": ""})
        for text in ("CONFLICT (content): Merge conflict in x.py", "VERIFIER_DISAGREEMENT", "tests could not run"):
            with self.subTest(text=text):
                code, original = flatten(RuntimeError(text))
                self.assertEqual((code, str(original)), (FailureCode.UNKNOWN, text))
        for value in ("REVIEW", "SECURITY", "review_finding", None):
            with self.subTest(value=value):
                with self.assertRaises(InvariantError):
                    classify(value)

    def test_formats_1_and_2_carry_only_the_thirteen_and_format_3_carries_all(self):
        for code in NINE:
            with self.subTest(code=code):
                for fmt in (1, 2):
                    self.assertEqual(outcome(f3.reconstruct, text_of(*ACTIVE, fail("S1", code), fmt=fmt))[1],
                                     "failure/observed: fields of the wrong kind or enum ['code']")
                self.assertEqual(outcome(f3.reconstruct, text_of(*ACTIVE, fail("S1", code)))[0], "OK")
        for code in THIRTEEN:
            with self.subTest(code=code):
                for fmt in (1, 2, 3):
                    self.assertEqual(outcome(f3.reconstruct, text_of(*ACTIVE, fail("S1", code), fmt=fmt))[0], "OK")

    def test_the_conformance_subcheck_pins_the_table_and_rejects_a_swapped_owner_or_retryability(self):
        fc = _load("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
        import aisef2.control.owner as ow
        rfc = fc.RFC((ROOT / fc.RFC_REL).read_text(encoding="utf-8"))
        self.assertEqual(fc._failure_taxonomy_matches_rfc(rfc)["state"], fc.PASS)
        swaps = {"MERGE_CONFLICT": ("DEVELOPER", Retryability.NOT_RETRYABLE), "REVIEW_FINDING": ("DEVELOPER", Retryability.RETRYABLE),
                 "VERIFIER_DISAGREEMENT": ("INTEGRATION", Retryability.RETRYABLE), "TESTS_UNRUNNABLE": ("DEVELOPER", Retryability.RETRYABLE)}
        for code, (owner, r) in swaps.items():
            with self.subTest(swap=code):
                k = TAXONOMY[FailureCode(code)]
                bad = {**TAXONOMY, FailureCode(code): type(k)(k.code, Owner(owner), r, k.rule)}
                with mock.patch.object(ow, "TAXONOMY", bad):
                    self.assertEqual(fc._failure_taxonomy_matches_rfc(rfc)["state"], fc.FAIL)
        with mock.patch.object(ow, "FORMAT_2_CODES", frozenset(FORMAT_2_CODES | {"MERGE_CONFLICT"})):
            self.assertEqual(fc._failure_taxonomy_matches_rfc(rfc)["state"], fc.FAIL)


# --------------------------------------------------------------------------------------- budgets v2 (§8, §14)

class BudgetsV2(unittest.TestCase):
    def state(self, *specs, fmt=3):
        return plain(fold(PROJECTIONS[P.BUDGETS], events_of(*specs, fmt=fmt)))

    def step(self, fmt, *specs, then):
        """The projection alone, on a hand-built event the schema would refuse: its own refusal, not the schema's."""
        b = Budgets()
        st = b.initial()
        for e in events_of(*specs, fmt=fmt):
            st = b.step(st, e)
        return b.step(st, Event(99, then[0], then[1], 0.0, False, ()))

    def test_version_2_reads_the_declared_format_and_charges_a_format_3_request_to_its_budget_owner(self):
        self.assertEqual(Budgets.version, 2)
        st = self.state(*ACTIVE, request("S1", ["C1"]), request("S1", ["C1", "C2"], "REVIEW"), request("S1", ["C2"], "SECURITY"),
                        request("S1", ["C2"], "REVIEW"))
        self.assertEqual(st["format"], 3)
        self.assertEqual(st["developer"], {"S1": {"requests": 1, "criteria": {"C1": 1}}})
        self.assertEqual(st["review"], {"S1": {"requests": 2, "criteria": {"C1": 1, "C2": 2}}})
        self.assertEqual(st["security"], {"S1": {"requests": 1, "criteria": {"C2": 1}}})
        self.assertEqual(st["admission"], {"S1": {"permitted": True, "ready": ["C1"], "criteria": ["C1", "C2"]}})

    def test_nothing_defaults_a_missing_or_foreign_budget_owner_under_format_3(self):
        for owner in (None, "PLAN", "ENVIRONMENT", "PROVIDER", "INTEGRATION", "developer"):
            with self.subTest(owner=owner):
                with self.assertRaisesRegex(ProjectionError, "budgets: a format-3 provider/request for S1 names its "
                                                             "budget_owner \\(DEVELOPER, REVIEW or SECURITY\\); nothing defaults "
                                                             "it \\(V2-005\\)"):
                    self.step(3, *ACTIVE, then=request("S1", ["C1"], owner))

    def test_under_formats_1_and_2_every_request_is_the_developers_as_frozen(self):
        for fmt in (1, 2):
            with self.subTest(format=fmt):
                st = self.state(*ACTIVE, request("S1", ["C1"], None), fmt=fmt)
                self.assertEqual((st["format"], st["developer"], st["review"], st["security"]),
                                 (fmt, {"S1": {"requests": 1, "criteria": {"C1": 1}}}, {}, {}))
                # a budget_owner that somehow reached the projection under an old format changes nothing
                st = self.step(fmt, *ACTIVE, then=request("S1", ["C1"], "REVIEW"))
                self.assertEqual((st["developer"]["S1"]["requests"], st["review"]), (1, {}))

    def test_a_review_or_security_request_needs_the_admission_and_names_only_its_criteria(self):
        for owner in ("REVIEW", "SECURITY"):
            with self.subTest(owner=owner):
                with self.assertRaisesRegex(ProjectionError, f"budgets: {owner} provider/request for S1, which has no admission"):
                    self.step(3, plan(), begin(), then=request("S1", ["C1"], owner))
                with self.assertRaisesRegex(ProjectionError, f"budgets: {owner} provider/request for S1 names \\['C9'\\], not "
                                                             "criteria of its admission"):
                    self.state(*ACTIVE, request("S1", ["C1", "C9"], owner))
                # a reviewer may examine a PRE_SATISFIED criterion; the developer may not be charged for it
                self.assertEqual(self.state(*ACTIVE, request("S1", ["C2"], owner))[owner.lower()]["S1"]["criteria"], {"C2": 1})
        with self.assertRaisesRegex(ProjectionError, "charges \\['C2'\\], not admitted READY"):
            self.state(*ACTIVE, request("S1", ["C2"]))
        with self.assertRaisesRegex(ProjectionError, "whose admission permits no developer call"):
            self.state(plan(), begin(), admit("S1", {"C1": "PRE_SATISFIED"}), request("S1", ["C1"]))

    def test_a_retry_charges_the_failures_own_owner_and_never_the_developer_for_review_or_security(self):
        limits = {o: 3 for o in Owner}
        for code, (owner, retryable) in NINE.items():
            with self.subTest(code=code):
                events = events_of(*ACTIVE, request("S1", ["C1"]), request("S1", ["C1"], "REVIEW"), fail("S1", code))
                c = budget.charge(events, "S1", limits)
                self.assertEqual((c.retry, c.budget), (retryable, owner if retryable else None))
                if retryable:
                    st = self.state(*ACTIVE, request("S1", ["C1"]), request("S1", ["C1"], "REVIEW"), fail("S1", code),
                                    story("retry", "S1", 6))
                    self.assertEqual(st["retries"], {"S1": {owner: 1}})
                    self.assertEqual(st["developer"], {"S1": {"requests": 1, "criteria": {"C1": 1}}})
                else:
                    with self.assertRaisesRegex(ProjectionError, "cites a non-retryable failure: no budget to charge"):
                        self.state(*ACTIVE, request("S1", ["C1"]), fail("S1", code), story("retry", "S1", 5))

    def test_the_reference_model_agrees_on_format_3_traces_and_its_V2_005_calibration(self):
        for pid, model in MODELS.items():
            with self.subTest(model=pid):
                self.assertEqual(h.calibration_problems(model, CALIBRATIONS[pid]), [])
        cal = {pid: [c["name"] for c in cases if "V2-005" in c["name"] or "format-3" in c["name"] or "review" in c["name"]
                     or "security" in c["name"]] for pid, cases in CALIBRATIONS.items()}
        self.assertGreaterEqual(len(cal["budgets"]), 4)
        self.assertGreaterEqual(len(cal["story_state"]), 2)
        diff = {pid: 0 for pid in MODELS}
        seen = {"REVIEW": 0, "SECURITY": 0, "codes": set(), "violations": 0}
        for seed in range(60):
            events = f3.reconstruct(gen.journal(seed, stories=2 + seed % 5, journal_format=3)).events
            for e in events:
                if e.type == "provider/request" and e.data["budget_owner"] in seen:
                    seen[e.data["budget_owner"]] += 1
                if e.type == "failure/observed":
                    seen["codes"].add(e.data["code"])
                if e.type == "invariant/violated":
                    seen["violations"] += 1
            for pid, model in MODELS.items():
                diff[pid] += h.projection_answer(PROJECTIONS[P(pid)], events) != h.model_answer(model, events)
        self.assertEqual(diff, {pid: 0 for pid in MODELS})
        self.assertTrue(seen["REVIEW"] > 5 and seen["SECURITY"] > 5 and seen["violations"] > 5, seen)
        self.assertTrue(set(NINE) & seen["codes"], seen["codes"])


# --------------------------------------------------------------------------------------- story_state v2

class StoryStateV2(unittest.TestCase):
    def test_version_2_admits_a_proof_and_an_adequacy_record_in_an_active_attempt_only(self):
        self.assertEqual(StoryState.version, 2)
        a, b = evaluated("S1", "C1", record()), evaluated("S1", "C1", record())
        st = plain(fold(PROJECTIONS[P.STORY_STATE], events_of(*ACTIVE, a, b, verified("S1", "C1", (4, 5)), adequacy("S1"))))
        self.assertEqual(st, {"S1": {"state": "ACTIVE", "attempt": 1, "admitted": True, "outcome": None}})
        p = StoryState()
        for where, specs in (("BEGIN", (plan(), begin())), ("COMMIT", (*ACTIVE, story("commit", "S1"))),
                             ("ENDED", (*ACTIVE, story("commit", "S1"), story("dispose", "S1"), story("end", "S1")))):
            for t, data in (("proof/verified", verified("S1", "C1", ())[1]), ("tests/adequacy", adequacy("S1")[1])):
                with self.subTest(state=where, type=t):
                    st = fold(p, events_of(*specs))
                    with self.assertRaisesRegex(ProjectionError, f"{t} for story S1 in state {where}"):
                        p.step(st, Event(99, t, data, 0.0, False, ()))
        with self.assertRaisesRegex(ProjectionError, "for story S9"):
            p.step(fold(p, events_of(*ACTIVE)), Event(99, "tests/adequacy", adequacy("S9")[1], 0.0, False, ()))


# --------------------------------------------------------------------------------------- the runtime (format 3)

class Runtime(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-v2005-")
        self.addCleanup(self._d.cleanup)
        self.root = pathlib.Path(self._d.name)

    def test_the_run_scope_writes_format_3_and_its_journal_is_read_and_repaired_as_format_3(self):
        r = closed_after(self, RunScope(self.root, "run-3", spec=RUN_SPEC, clock=lambda: 1.0))
        r.begin()
        for spec in ACTIVE:
            r.append(T(spec[0]), spec[1])
        req = r.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"], "budget_owner": "REVIEW"})
        r.append(T.INVARIANT_VIOLATED, violated("VI")[1])
        r.append(T.FAILURE_OBSERVED, {"story_id": "S1", "code": "CAPABILITY_UNRUNNABLE", "detail": ""})
        text = r.journal_path.read_bytes().decode("utf-8")
        self.assertEqual(f3.declared_format(text), 3)
        self.assertEqual(outcome(f2.reconstruct, text), ("JournalError", "journal format 3 is neither format 1 nor format 2: refused"))
        self.assertEqual(r.state(P.BUDGETS)["review"], {"S1": {"requests": 1, "criteria": {"C1": 1}}})
        self.assertEqual(sentinel.residuals(text), (f"S1: provider/request at seq {req.seq} has no result",))
        with self.assertRaisesRegex(JournalError, "fields missing \\['budget_owner'\\]"):
            r.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"]})
        r._writer.close()
        fixed = rp.repair(text)
        self.assertTrue(fixed.startswith(text))
        closers = f3.reconstruct(fixed).events[len(r.events):]
        self.assertEqual([e.type for e in closers], ["provider/result", "run/interrupted", "run/end"])
        self.assertEqual(closers[0].source_seqs, (req.seq,))
        self.assertEqual(rp.repair(fixed), fixed)
        self.assertEqual(sentinel.residuals(fixed), ())
        with self.assertRaisesRegex(rp.RepairError, "a format-1 journal is read, never extended"):
            rp.repair(text_of(fmt=1))

    def test_closers_release_every_story_in_story_order_whatever_the_journal_order(self):
        names = [f"S{n}" for n in (8, 3, 6, 1, 7, 2, 5, 4)]
        specs = [plan()]
        for s in names:
            specs += [begin(s), acquired(s, f"wt-{s}", "WORKTREE"), acquired(s, f"session-{s}")]
        released = [d["story_id"] for t, d, _ in rp.closers(events_of(*specs)) if t is T.STORY_RESOURCE_RELEASED]
        self.assertEqual(released, [s for s in sorted(names) for _ in (0, 1)])  # sorted, never the set's order
        self.assertEqual([d["resource"] for t, d, _ in rp.closers(events_of(*specs)) if t is T.STORY_RESOURCE_RELEASED][:2],
                         ["session-S1", "wt-S1"])  # each story's resources in reverse acquisition order

    def test_a_rerun_of_the_run_scope_reads_the_previous_format_3_journal_at_preflight(self):
        r = closed_after(self, RunScope(self.root, "run-a", spec=RUN_SPEC, clock=lambda: 1.0))
        r.begin()
        for spec in ACTIVE:
            r.append(T(spec[0]), spec[1])
        req = r.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"], "budget_owner": "SECURITY"})
        r._writer.close()  # died mid-story: the sentinel stays OPEN, the request has no result
        r.lease.release()
        second = closed_after(self, RunScope(self.root, "run-b", spec=RUN_SPEC, clock=lambda: 2.0))
        second.begin()
        self.assertEqual((second.preflight.previous, second.preflight.residuals),
                         ("TORN", (f"S1: provider/request at seq {req.seq} has no result",)))


# --------------------------------------------------------------------------------------- the lineage (§1, §15, §16)

class Lineage(unittest.TestCase):
    def test_V2_005_is_the_fourth_link_after_V2_003_changing_exactly_F1(self):
        fm = _load("aisef_v2_freeze_manifest", "validation/v2/freeze_manifest.py")
        self.assertEqual(fm.check(ROOT), [])
        eff, links, problems = fm.lineage(ROOT)
        self.assertEqual(problems, [])
        self.assertEqual([pathlib.Path(x["record"]).name for x in links],
                         ["AISEF-V2-RFC-APPROVAL.json", "AISEF-V2-RFC-AMENDMENT-V2-001.json", "AISEF-V2-RFC-AMENDMENT-V2-002.json",
                          "AISEF-V2-RFC-AMENDMENT-V2-003.json", "AISEF-V2-RFC-AMENDMENT-V2-005.json"])
        self.assertEqual(links[-1]["frozen_items_changed"], ["F1"])
        self.assertFalse((EVIDENCE / "AISEF-V2-RFC-AMENDMENT-V2-004.json").exists())
        self.assertFalse((EVIDENCE / "ARCHITECTURE-EXCEPTION-V2-004.json").exists())
        amd = json.loads((EVIDENCE / "AISEF-V2-RFC-AMENDMENT-V2-005.json").read_text(encoding="utf-8"))
        exc = json.loads((EVIDENCE / "ARCHITECTURE-EXCEPTION-V2-005.json").read_text(encoding="utf-8"))
        self.assertEqual(amd["amends"]["path"], "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-003.json")
        self.assertEqual(exc["status"], "APPROVED — APPLIED")
        self.assertEqual((exc["frozen_items_changed_mechanically"], exc["supersedes"]["status"]),
                         (["F1"], "SUPERSEDED — NEVER APPLIED"))
        self.assertEqual(exc["promoted_from"]["sha256"], fm._lf_sha(ROOT / exc["promoted_from"]["path"]))
        self.assertEqual(exc["supersedes"]["sha256"], fm._lf_sha(ROOT / exc["supersedes"]["path"]))
        self.assertTrue((ROOT / exc["supersedes"]["path"]).read_text(encoding="utf-8")
                        .startswith("# ARCHITECTURE-EXCEPTION-V2-004 — SUPERSEDED / NOT APPLIED"))
        rfc = (ROOT / fm.RFC_REL).read_text(encoding="utf-8")
        self.assertEqual(rfc.count("*(amended — ARCHITECTURE-EXCEPTION-V2-005)*"), 18)
        table = fm.freeze_items(rfc)
        self.assertIn("V2-005", next(i["item"] for i in table if i["id"] == "F1"))
        self.assertEqual([i["id"] for i in table if "V2-005" in i["item"]], ["F1"])
        conf = json.loads((EVIDENCE / "F-CONFORMANCE.json").read_text(encoding="utf-8"))
        states = {s["id"]: s["state"] for s in conf["subchecks"]}
        self.assertEqual((states["F1.failure_taxonomy"], states["F1.journal_format_3"]), ("PASS", "PASS"))
        self.assertEqual(conf["summary"], {"PASS": 11, "PENDING": 0, "FAIL": 0})

    def test_the_sealed_P5_records_are_verified_by_identity_never_rewritten(self):
        p5 = _load("aisef_v2_p5_evidence", "validation/v2/p5_evidence.py")
        bound = p5.sealed(ROOT)
        self.assertEqual(sorted(pathlib.Path(k).name for k in bound),
                         ["P5-ADEQUACY.json", "P5-INVARIANTS.json", "P5-RELEVANCE.json", "P5-TEST-EXECUTION.json", "P5-VACUITY.json"])
        self.assertEqual(p5.check(ROOT), [])
        seal = json.loads((EVIDENCE / "P5-FINAL-SEAL.json").read_text(encoding="utf-8"))

        def p5_root(d, without=None):  # a fresh root holding the sealed records, the seal and the builders' modules
            root = pathlib.Path(d)
            for rel in (*bound, p5.SEAL_REL, *(needs for _, _, needs in p5.BUILDERS.values())):
                if rel != without:
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / rel, root / rel)
            return root
        with tempfile.TemporaryDirectory(prefix="aisef2-v2005-") as d:
            root = p5_root(d)
            self.assertEqual(p5.check(root), [])
            inv = root / "closure-evidence/v2/P5-INVARIANTS.json"
            rec = json.loads(inv.read_text(encoding="utf-8"))
            rec["registry"]["mechanism_digest"] = "0" * 64
            inv.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            self.assertEqual(p5.check(root), ["closure-evidence/v2/P5-INVARIANTS.json differs from the sha256 bound by "
                                              "closure-evidence/v2/P5-FINAL-SEAL.json: a sealed record is never rewritten"])
        with tempfile.TemporaryDirectory(prefix="aisef2-v2005-") as d:  # a root that never held one record
            self.assertIn("closure-evidence/v2/P5-VACUITY.json is missing",
                          p5.check(p5_root(d, without="closure-evidence/v2/P5-VACUITY.json")))
        self.assertEqual(seal["invariants"]["mechanism_digest"], json.loads(
            (EVIDENCE / "P5-INVARIANTS.json").read_text(encoding="utf-8"))["registry"]["mechanism_digest"])


if __name__ == "__main__":
    unittest.main()
