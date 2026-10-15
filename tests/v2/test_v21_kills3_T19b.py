"""Mutation survivors, batch T19b: `aisef2/probe/process_effect.py` (the `process_effect` scenario probe, RFC §9,
DECISION-2, B1, B6) — the refusal of a fault before a subprocess step (PM-2), the namespace-package rule of
`inside`, the controller's reading of the subject's process ending (or forging an answer and ending) while its module
is imported or its name resolved, the report of a memoryview result, the per-step `fired` fact, the evaluation
directory's layout and the parent's decision once a RESULT is read.

Each class states the requirement and names the mutants it pins as `Pins aisef2/probe/process_effect.py::<target> [i]`
(the index is the position in the target's mutant list, as `validation/v21/kill_check.py` takes it). The real probe
runs on real checkouts (a subject process and a controller process each); a test double of the owned range is used
twice only: to look at the evaluation directory before anything runs, and for the one state a real harness cannot be
held in on demand — still present when its RESULT is read.
"""

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, ProbeExecutionStatus  # noqa: E402
from aisef2.probe import process_effect as pe  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from tests.v2 import test_probe_process_effect as base  # noqa: E402
from tests.v2 import test_probe_process_effect_units as units  # noqa: E402
from tests.v2.test_c2_cli_invocation import FakeRange  # noqa: E402

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
BOOK = base.BOOK
SHA = base.SHA

#: what this file's subjects do, on top of the product the probe's own tests use (store/book.py: a Book with append,
#: count, save and a `check` command in store/__main__.py)
EXTRA = {
    # a memoryview result, a bytearray result for contrast
    "store/mv.py": "def view():\n    return memoryview(b'ab')\n\n\ndef buf():\n    return bytearray(b'ab')\n",
    # B6: the subject's and every subprocess step's temporary directory is the evaluation's own tmp/, a sibling of ws/
    "store/where.py": (
        "import os\nimport tempfile\n\n\ndef evaluation_tmp():\n"
        "    mine = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(os.getcwd())), 'tmp'))\n"
        "    return os.path.realpath(tempfile.gettempdir()) == mine\n"),
    "store/tmpcheck.py": (
        "import os\nimport sys\nimport tempfile\n\n"
        "mine = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(os.getcwd())), 'tmp'))\n"
        "sys.exit(0 if os.path.realpath(tempfile.gettempdir()) == mine else 4)\n"),
    # the subject's process ends while its module is imported, and while its declared name is resolved (a module-level
    # __getattr__ is the one piece of the subject's code that runs there: the agent's import reads vars(module))
    "store/exits.py": "import os\n\nos._exit(7)\n",
    "store/exits_late.py": "def __getattr__(name):\n    import os\n    os._exit(8)\n",
    # the same, after writing an answer to the agent's reply channel under a request number nobody asked
    # (`__main__` is the agent's own script: `send` is the agent's way of answering)
    "store/forges.py": "import os\nimport __main__\n\n__main__.send({'n': 99})\nos._exit(0)\n",
    "store/forges_late.py": ("def __getattr__(name):\n    import os\n    import __main__\n"
                            "    __main__.send({'n': 99})\n    os._exit(0)\n"),
    # PM-2: two CLIs over one `save` that renames a temporary file over its target: the fragile one lets an OSError of
    # the rename escape (exit 1), the tolerant one catches it (exit 0 either way)
    "store/saver.py": "import sys\n\nfrom store.book import Book\n\nBook(sys.argv[1]).save('a\\n')\n",
    "store/saver_quiet.py": "import sys\n\nfrom store.book import Book\n\nBook(sys.argv[1]).save_quietly('a\\n')\n",
    # a directory of the revision with no __init__.py: a namespace package, which holds no code
    "nsdir/readme.txt": "a directory without __init__.py\n",
}


def facts_of(observation):
    return json.loads(observation.detail)


class _Revision(unittest.TestCase):
    """One checkout of the product plus this file's subjects for the class."""

    @classmethod
    def setUpClass(cls):
        d = tempfile.TemporaryDirectory(prefix="aisef2-t19b-rev-", ignore_cleanup_errors=True)
        cls.addClassCleanup(d.cleanup)
        cls.root = base.checkout(d.name, {**base.PRODUCT, **EXTRA})
        cls.at = RevisionRef(SHA, cls.root)

    def see(self, s, probe=None):
        return (probe or base.P).observe(s, self.at, base.env())


class FaultBeforeSubprocess(_Revision):
    """DECISION-2 / `FAULTED` (PM-2): a `fault` step directly before a `subprocess` step is refused at admission
    (UNSUPPORTED -> INVALID_SPEC) and nothing runs. The stand-in is installed in the subject's own process; a subprocess
    step's child is another interpreter and never sees it, so such a scenario used to run unfaulted (`fired: false`)
    and be judged: a product that fails under the fault was SATISFIED, and nothing in the verdict said no fault had
    happened. The unfaulted subprocess step is unchanged, and the faulted call that measures the same property of
    the same code still tells a fragile product from a tolerant one.

    The 27 mutants of the controller's own-process guard `HARNESS/guarded`, 14 of which this class used to kill, left
    with the function: after the refusal nothing could reach it."""

    FILES = {"files": {BOOK: {"line_count": 1}}}

    def test_a_fault_before_a_subprocess_step_is_refused_and_nothing_runs(self):
        for cli in ("store.saver", "store.saver_quiet"):
            for fault in pe.FAULTS:   # the production table, every id
                with self.subTest(cli=cli, fault=fault):
                    scenario = base.book(base.step("fault", fault=fault),
                                         base.step("subprocess", argv=["-m", cli, BOOK]))
                    s = base.spec("store.book:Book", scenario, self.FILES)
                    self.assertIsNone(pe.spec_class(s))   # no class: the admission answer
                    with base.never_runs():   # no range is started, so no controller, no subject, no child
                        o = self.see(s)
                        self.assertEqual((o.kind, o.verdict), (K.UNSUPPORTED, None), o.detail)
                        self.assertIs(run_probe(base.P, s, self.at, base.env()).result.status,
                                      ProbeExecutionStatus.INVALID_SPEC)

    def test_a_refused_fault_does_not_refuse_the_subprocess_step_itself(self):
        # the same two CLIs, no fault: admitted, run, judged, and the trace carries neither a fault nor `fired`
        for cli in ("store.saver", "store.saver_quiet"):
            with self.subTest(cli=cli):
                scenario = base.book(base.step("subprocess", argv=["-m", cli, BOOK]))
                o = self.see(base.spec("store.book:Book", scenario, self.FILES))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
                self.assertEqual(facts_of(o)["trace"][1], {"i": 1, "kind": "subprocess", "outcome": "ok", "exit": 0})
        # the child's own exit status is judged as declared (3: the book holds 1 record, not 5), then undeclared
        declared = base.book(base.call("append", "a", 1, "r1"),
                             base.step("subprocess", argv=["-m", "store", "check", BOOK, "5"], expect_exit=3),
                             base.call("count"))
        o = self.see(base.spec("store.book:Book", declared, {"returns": 1}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual(facts_of(o)["trace"][2], {"i": 2, "kind": "subprocess", "outcome": "ok", "exit": 3})
        undeclared = base.book(base.call("append", "a", 1, "r1"),
                               base.step("subprocess", argv=["-m", "store", "check", BOOK, "5"]),
                               base.call("count"))
        o = self.see(base.spec("store.book:Book", undeclared, {"returns": 1}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        refuted = facts_of(o)["refuted"]
        self.assertEqual((refuted["step"], refuted["kind"]), (2, "subprocess"))
        self.assertIn("3", refuted["why"])   # the status the child exited with (the sentence is PE-4's to pin)
        self.assertNotIn("fault", facts_of(o)["trace"][2])

    def test_the_faulted_call_that_replaces_it_tells_a_fragile_product_from_a_tolerant_one(self):
        # what the refused scenario was meant to measure, through the one step a fault reaches: `save` renames a
        # temporary file over the target; with that rename failing once, the fragile `save` raises (a refuted step) and
        # the tolerant `save_quietly` leaves the target absent. The fault fires in both, and the trace says so.
        gone = {"files": {BOOK: {"absent": True}}}
        for method, verdict in (("save", R), ("save_quietly", S)):
            with self.subTest(method=method):
                scenario = base.book(base.step("fault", fault="os.replace"), base.call(method, "a\n"))
                o = self.see(base.spec("store.book:Book", scenario, gone))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, verdict), o.detail)
                entry = facts_of(o)["trace"][2]
                self.assertEqual((entry["kind"], entry["fault"], entry["fired"]), ("call", "os.replace", True))


class NamespacePackageIsInside(_Revision):
    """`inside(spec)`: a directory of the revision with no __init__.py is a namespace package OF the revision, so a
    name missing from it is a name the module does not define — not a module that "resolves only outside the
    revision" (which would send the operator looking for a shadowed or foreign module that is not there).

    Pins aisef2/probe/process_effect.py::HARNESS/inside [3]."""

    def test_a_missing_name_in_a_namespace_package_is_not_an_outside_module(self):
        o = self.see(base.spec("nsdir:Thing", [base.call(None)], {"returns": None}))
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R))
        self.assertIn("Thing", o.detail)           # the name that is missing
        self.assertNotIn("outside", o.detail)      # the revision's own directory is not "outside the revision"
        outside = self.see(base.spec("json:dumps", [base.call(None)], {"returns": None}))
        self.assertIn("outside", outside.detail)   # the note this one is told apart from (base PE_6 pins its text)


class ProcessEndsBeforeTheScenario(_Revision):
    """RFC B1: the controller outlives the subject's process. A process that ends while its module is being imported or
    while its declared name is resolved is a present subject that does not work: OBSERVED, REFUTED, the exit status in
    the facts and no step named (`refuted.step` None, trace []) — never HARNESS_FAILED, never SUBJECT_ABSENT, never a
    verdict of the declared observable.

    Pins aisef2/probe/process_effect.py::HARNESS/main [18, 19] (import) and [22, 23] (resolve)."""

    def test_the_exit_status_while_the_module_is_imported_or_the_name_resolved(self):
        for locator, code in (("store.exits:Thing", 7), ("store.exits_late:Thing", 8)):
            with self.subTest(locator=locator):
                s = base.spec(locator, [base.call(None)], {"returns": None})
                o = self.see(s)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
                f = facts_of(o)
                self.assertEqual({k: f.get(k) for k in ("subject", "hard_exit", "exit_code", "trace")},
                                 {"subject": "present", "hard_exit": True, "exit_code": code, "trace": []})
                self.assertIsNone(f["refuted"]["step"])
                self.assertEqual(run_probe(base.P, s, self.at, base.env()).result, Executed(R))


class ForgerThatThenDies(_Revision):
    """A subject that writes an answer the agent did not write and then dies is still the tamper fact — `{"subject":
    "present", "tampered": <text>}` — in each phase the controller reads an answer in (import, resolve): the controller
    carrying on over a dead agent would build the scenario's own facts and the declared observable could hold. With the
    agent alive the next ask re-derives the same fact from the leftover genuine answer, so these need the agent gone.

    Pins aisef2/probe/process_effect.py::HARNESS/main [104] (import) and [115] (resolve); [18, 19, 22, 23] also differ
    here (the exit test above pins those four)."""

    SCENARIO = [base.step("workspace", files={"keep.txt": {"text": "k"}})]
    HOLDS = {"files": {"<ws>/keep.txt": {"equals_before": True}}}

    def test_the_declared_observable_holds_for_a_subject_that_does_not_forge(self):
        o = self.see(base.spec("store.book:Book", self.SCENARIO, self.HOLDS))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    def test_a_forged_answer_then_a_hard_exit_is_the_tamper_in_either_phase(self):
        for locator in ("store.forges:Thing", "store.forges_late:Thing"):
            with self.subTest(locator=locator):
                o = self.see(base.spec(locator, self.SCENARIO, self.HOLDS))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
                f = facts_of(o)
                self.assertEqual(set(f), {"subject", "tampered"})
                self.assertEqual(f["subject"], "present")
                self.assertIn("not the agent's", f["tampered"])


class MemoryviewResult(_Revision):
    """A memoryview result is neither JSON nor bytes: it is reported by its type name — `last_unserializable` ==
    "memoryview", a bound one is `{"unserializable": "memoryview"}` — and never equals anything: two bound memoryviews
    of equal content are REFUTED under returns_name/equals_name, a lone one under `returns_bytes_hex` (a bytearray of
    the same content is SATISFIED).

    This is this probe's own rule ("anything else by its type name"; the harness before the controller/agent split
    reported a memoryview so too, and the branch under test carries it over) — not python_callable_v2's, whose
    `returns_bytes` reads a memoryview as bytes: if the owner aligns the two, this class moves with the change.
    Pins aisef2/probe/process_effect.py::HARNESS/reported [9, 15, 16, 20, 21]."""

    def test_two_bound_memoryviews_of_equal_content_are_not_equal(self):
        s = base.spec("store.mv:view", [base.call(None, bind="v1"), base.call(None, bind="v2")],
                      {"returns_name": "v1", "equals_name": "v2"})
        o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        marker = {"unserializable": "memoryview"}
        self.assertEqual(facts_of(o).get("bound"), {"v1": marker, "v2": marker})

    def test_a_lone_memoryview_is_its_type_name_not_bytes(self):
        o = self.see(base.spec("store.mv:view", [base.call(None)], {"returns_bytes_hex": "6162"}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        f = facts_of(o)
        self.assertEqual(f.get("last_unserializable"), "memoryview")
        self.assertNotIn("last_returned_bytes_hex", f)
        self.assertNotIn("last_returned", f)
        # the bytearray of the same content is bytes: SATISFIED, reported as hex
        o = self.see(base.spec("store.mv:buf", [base.call(None)], {"returns_bytes_hex": "6162"}))
        self.assertEqual((o.verdict, facts_of(o).get("last_returned_bytes_hex")), (S, "6162"))


class FiredIsPerStep(_Revision):
    """The step's trace records the fault and whether it fired — per step: a fault that fires nowhere is recorded as
    not fired even when an earlier fault of the same scenario fired. No class observable reads the field: it is
    evidence, read from the observation's detail by whoever decides whether a scenario that names a fault measured it
    (DECISION-1's bounded witness).

    Pins aisef2/probe/process_effect.py::HARNESS/run [32]."""

    def test_a_fault_that_fires_nowhere_after_one_that_fired_is_not_fired(self):
        scenario = base.book(base.step("fault", fault="os.replace"), base.expect("save", "OSError", "x"),
                             base.step("fault", fault="os.rename"), base.call("count"))
        o = self.see(base.spec("store.book:Book", scenario, {"returns": 0}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        trace = facts_of(o)["trace"]
        self.assertEqual([(e.get("fault"), e.get("fired")) for e in trace],
                         [(None, None), (None, None), ("os.replace", True), (None, None), ("os.rename", False)])


class EvaluationDirectoryLayout(_Revision):
    """The evaluation directory holds, empty, before anything runs: ws/ (the subject's cwd and HOME), tmp/ (B6: the
    subject's and every subprocess step's TMPDIR/TEMP/TMP, so tempfile.gettempdir() is that directory) and the two
    fresh bytecode caches pycache/ (controller) and pycache-agent/ (subject), side by side and outside the checkout.
    FM2_PYC_EFFECT_4 pins the controller's cache only; test_c2_cli_verdicts pins the same layout for cli_invocation's
    `_prepare`. [7] pins the documented layout: with -B nothing is written under the subject's cache prefix and an
    absent directory is as free of stale bytecode as an empty one, so no isolation property rides on it ([8] does:
    the next class).

    Pins aisef2/probe/process_effect.py::_prepare [7, 8]."""

    def test_four_empty_directories_exist_when_the_range_starts(self):
        seen = {}

        class Look(FakeRange):
            def start(self):   # the evaluation directory is disposed when observe returns: look now
                req = json.loads(pathlib.Path(self.argv[-1]).read_text(encoding="utf-8"))
                argv = self.argv
                pycache = argv[argv.index("-X") + 1].removeprefix("pycache_prefix=")
                named = {"workspace": req["ws"], "temporary": req["env"]["TMPDIR"], "controller bytecode": pycache,
                         "subject bytecode": req["agent_pycache"]}
                seen["work"], seen["env"] = req["work"], req["env"]
                seen["layout"] = {what: (path, os.path.isdir(path), os.listdir(path) if os.path.isdir(path) else None)
                                  for what, path in named.items()}
                return super().start()
        fake = Look(("READY", "DISPATCHED", 'RESULT {"subject": "absent"}'), 0)
        with mock.patch.object(pe, "ProcessRange", fake):
            self.assertEqual(self.see(base.spec("store.book:Book", [base.call(None)], {"returns": None})).kind,
                             K.SUBJECT_ABSENT)
        for what, (path, is_dir, listing) in seen["layout"].items():
            with self.subTest(what=what):
                self.assertTrue(is_dir, path)
                self.assertEqual(listing, [])
                self.assertEqual(os.path.dirname(path), seen["work"])   # in the evaluation directory, not the checkout
        self.assertEqual({os.path.basename(p) for p, _, _ in seen["layout"].values()},
                         {"ws", "tmp", "pycache", "pycache-agent"})
        self.assertEqual({seen["env"][k] for k in ("TMPDIR", "TEMP", "TMP")}, {seen["env"]["TMPDIR"]})


class TemporaryFilesAreTheEvaluations(_Revision):
    """B6, observed from the subject: `tempfile.gettempdir()` in the subject's process and in a subprocess step is the
    evaluation's own tmp/ — a directory that exists, so that tempfile uses it instead of falling back to the host's
    shared temporary directory (where nothing disposes of what the subject leaves).

    Pins aisef2/probe/process_effect.py::_prepare [8]."""

    def test_the_subject_and_a_subprocess_step_use_the_evaluations_tmp(self):
        scenario = [base.call(None), base.step("subprocess", argv=["-m", "store.tmpcheck"])]
        o = self.see(base.spec("store.where:evaluation_tmp", scenario, {"returns": True}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual([e.get("exit") for e in facts_of(o)["trace"]], [None, 0])


class _Watch(unittest.TestCase):
    """The parent's decision after DISPATCHED (cli_invocation's watch over this probe's lines)."""

    @classmethod
    def setUpClass(cls):
        d = tempfile.TemporaryDirectory(prefix="aisef2-t19b-watch-", ignore_cleanup_errors=True)
        cls.addClassCleanup(d.cleanup)
        pathlib.Path(d.name, "store").mkdir()
        cls.at = RevisionRef(SHA, d.name)


class ResultReadDecides(_Watch):
    """The parent's table: RESULT read -> the observation. A scenario that completed inside its window is not REFUTED
    because the harness has not yet exited when the window ends: the RESULT line is read as it arrives, the exit being
    lifecycle evidence read afterwards. A harness still present with its RESULT in the file is the verdict of the
    facts — SATISFIED here, REFUTED when the facts say so — never SUBJECT_DEADLINE. The double has every line in the
    file at once, so it tells the awaited line apart from one that never arrives (the emptied tag, END), not from an
    earlier line of the same run (STEP, DISPATCHED): the real harness's tests in the target's kill set do that.

    Pins aisef2/probe/process_effect.py::_watch [17]."""

    class Running(FakeRange):
        """The harness's process is still there (no exit status, a member of the range) when it is polled."""

        def wait(self, timeout=None):
            return None

        def members(self):
            return [object()]

    def observe(self, last_returned):
        lines = ("READY", "DISPATCHED", "STEP 0", "STEP 1",
                 "RESULT " + json.dumps({"subject": "present", "trace": [], "last_returned": last_returned}))
        s = units.spec([units.NEW, units.CALL], {"returns": 1}, window=0.2)
        with mock.patch.object(pe, "ProcessRange", self.Running(lines, None)):
            return base.P.observe(s, self.at, units.env())

    def test_a_result_read_while_the_harness_is_present_is_the_observation(self):
        for returned, verdict in ((1, S), (2, R)):
            with self.subTest(returned=returned):
                o = self.observe(returned)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, verdict), o.detail)
                self.assertEqual(facts_of(o)["last_returned"], returned)


if __name__ == "__main__":
    unittest.main()
