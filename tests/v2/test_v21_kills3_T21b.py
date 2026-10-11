"""V2.1 mutation-survivor batch T21b — the controller script of `aisef2/probe/cli_invocation.py` (HARNESS/main) on
real checkouts, in the places only a pre-step, the marker file or a process that ends itself reach.

The controller (B1) asks the subject's process one operation at a time and builds every fact itself. These tests drive
the real probe, the real controller and the real subject process:

* a pre-step answered by something other than the agent (an entry function that writes on the agent's reply
  descriptor, `import __main__` as `stallbye` does in test_c2_cli_invocation) is tampering, REFUTED like the same
  thing in the main invocation, with the facts `{subject: 'present', tampered: <reason>}` and nothing of an
  invocation whose answer was not the agent's;
* an entry function that does not exist is absent whether or not the stimulus has pre-steps;
* the facts of a failed pre-step say the subject was present, beside the index and the steps that ran;
* the marker file names each invocation in order (`PRE <i>` per pre-step, then `MAIN {"before": ...}`), the grammar
  the module docstring documents for the channel;
* a main invocation that ends its own process still carries the controller-built before and after facts of every
  named file, so an `exits_files` observable is decided over them.

Pins aisef2/probe/cli_invocation.py::HARNESS/main:
  [46, 71, 72, 73, 98, 99, 100, 117]   a stray answer in a pre-step
  [48, 74, 101]                        the absent entry function seen from a pre-step
  [75, 103, 106]                       the facts of a failed pre-step
  [51, 68, 78, 108]                    the marker file's PRE / MAIN lines
  [112, 113, 120, 121]                 before / files of a hard exit of the main invocation
"""

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, ContractSatisfaction, SubjectAbsence  # noqa: E402
from aisef2.probe.cli_invocation import CliInvocationProbe  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, classify_failure, run_probe  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason, contract_satisfaction  # noqa: E402
from tests.v2 import test_c2_cli_invocation as base  # noqa: E402  (builders only: no test class is imported)

S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
EXITS_0, BLOCKS = {"exit_code": 0}, {"blocks": True}

#: The subject: entry functions that act on the agent's own globals. `__main__.WOUT` is the agent's copy of its reply
#: pipe to the controller; what is written there is not the agent's answer.
SUBJECT = '''
import json
import os

import __main__


def main(argv):
    cmd = argv[0] if argv else "ok"
    if cmd == "wrongn":       # an object numbered otherwise than the request: not the agent's answer
        os.write(__main__.WOUT, (json.dumps({"n": 999}) + "\\n").encode("utf-8"))
    elif cmd == "junkexit":   # a stray line, then the process ends by itself: no real answer trails it
        os.write(__main__.WOUT, b"this is not json\\n")
        os._exit(3)
    elif cmd == "writeexit":  # leave a file in the workspace, then end the process by itself with a code
        with open(argv[1], "wb") as f:
            f.write(argv[2].encode("utf-8"))
        os._exit(int(argv[3]))
    return 0
'''
FILES = {**base.PRODUCT, "app/sub.py": SUBJECT}


def sha(data: bytes) -> str:
    return base.sha(data)


class _Checkouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory(prefix="aisef2-t21b-", ignore_cleanup_errors=True)
        cls.addClassCleanup(tmp.cleanup)
        for rel, text in FILES.items():
            p = pathlib.Path(tmp.name, "product", rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
        cls.at = RevisionRef(base.SHA, str(pathlib.Path(tmp.name, "product")))

    def see(self, s, probe=None, e=None):
        return (probe or base.P).observe(s, self.at, e or base.env())

    def result(self, s):
        return run_probe(base.P, s, self.at, base.env()).result


class StrayAnswerInAPreStep(_Checkouts):
    """A pre-step is an invocation of the subject like the main one: when the line the controller reads as its answer
    is not the agent's (an object numbered otherwise than the request), the observation is OBSERVED and REFUTED with
    the facts of a present subject that tampered, exactly `{subject: 'present', tampered: <reason>}` — no exit code,
    streams, pre, before or files of an invocation whose answer was not the agent's. It is neither a crash of the
    controller (UNRUNNABLE, owner ENVIRONMENT) nor, for `blocks`, a satisfied contract.

    Pins HARNESS/main [46, 71, 72, 98, 100, 117] (the stray answer is recognised and reported) and [73, 99] (the
    reason: with nothing real behind the stray line only the pre-step's own facts say why it was refuted)."""

    def assert_tampered(self, o, why):
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), f"{why}: {o.kind} {o.detail}")
        f = base.facts_of(o)
        self.assertEqual(sorted(f), ["subject", "tampered"], f"{why}: {o.detail}")
        self.assertEqual(f["subject"], "present", why)
        self.assertIsInstance(f["tampered"], str, why)
        self.assertTrue(f["tampered"], f"{why}: the reason is not empty")

    def pre(self, cmd, observable):
        return base.spec("app.sub:main", observable, {"argv": ["ok"], "pre": [{"argv": [cmd]}]})

    def test_a_pre_step_answered_by_a_stray_object_refutes_exits_and_blocks(self):
        for name, observable in (("exits", EXITS_0), ("blocks", BLOCKS)):
            with self.subTest(observable=name):
                self.assert_tampered(self.see(self.pre("wrongn", observable)), name)

    def test_blocks_is_not_satisfied_by_a_tampering_pre_step_and_the_result_is_executed_refuted(self):
        self.assertEqual(self.result(self.pre("wrongn", BLOCKS)), Executed(R))
        self.assertEqual(self.result(self.pre("wrongn", EXITS_0)), Executed(R))

    def test_with_nothing_real_behind_the_stray_line_the_facts_still_say_tampered(self):
        """The stray line, then the process ends by itself: the closing exchange has no real answer to restore the
        marker from, so the pre-step's own facts are the ones recorded."""
        for name, observable in (("exits", EXITS_0), ("blocks", BLOCKS)):
            with self.subTest(observable=name):
                self.assert_tampered(self.see(self.pre("junkexit", observable)), name)


class TheAbsentEntryFunctionSeenFromAPreStep(_Checkouts):
    """An entry function that does not exist is SUBJECT_ABSENT (REFUTED over the absent subject) whether or not the
    stimulus has pre-steps: the module resolves inside the revision, so the absence is first learned from the agent's
    answer to the first pre-step. The contract's `subject_absence` declaration then decides what it counts for
    (§10.2), exactly as for the same absence learned in the main invocation.

    Pins HARNESS/main [48, 74, 101]."""

    LOCATOR = "app.cli:gone"

    def test_the_absence_is_the_same_observation_with_and_without_pre_steps(self):
        plain = self.see(base.spec(self.LOCATOR, EXITS_0, {"argv": []}))
        self.assertEqual((plain.kind, plain.verdict), (K.SUBJECT_ABSENT, R), plain.detail)
        for pre in ([{"argv": ["echo"]}], [{"argv": ["echo", "one"]}, {"argv": ["echo", "two"]}]):
            with self.subTest(pre=len(pre)):
                o = self.see(base.spec(self.LOCATOR, EXITS_0, {"argv": [], "pre": pre}))
                self.assertEqual(o, plain)

    def test_the_contracts_declaration_decides_what_the_absence_counts_for(self):
        s_required = base.spec(self.LOCATOR, EXITS_0, {"argv": [], "pre": [{"argv": ["echo"]}]},
                               absence=SubjectAbsence.REQUIRES_SUBJECT)
        self.assertEqual(self.result(s_required), Executed(I, IndeterminateReason.PRECONDITION_ABSENT))
        o = self.see(s_required)
        forbidden = base.spec(self.LOCATOR, EXITS_0, {"argv": [], "pre": [{"argv": ["echo"]}]},
                              absence=SubjectAbsence.ABSENCE_IS_DECIDABLE, expectation=R)
        self.assertIs(contract_satisfaction(classify_failure(forbidden, o), forbidden), ContractSatisfaction.SATISFIED)
        required = base.spec(self.LOCATOR, EXITS_0, {"argv": [], "pre": [{"argv": ["echo"]}]},
                             absence=SubjectAbsence.ABSENCE_IS_DECIDABLE, expectation=S)
        self.assertIs(contract_satisfaction(classify_failure(required, o), required), ContractSatisfaction.UNSATISFIED)


class TheFactsOfAFailedPreStep(_Checkouts):
    """A pre-step that does not exit 0 refutes the observation with its index in `detail`. The facts are those of a
    present subject, like every other fact set the controller builds: `subject`, the failed step's index and the
    steps that ran up to and including it — and nothing of the main invocation, which never ran.

    Pins HARNESS/main [75, 103, 106]."""

    def test_the_facts_name_the_subject_the_index_and_the_steps_that_ran(self):
        stimulus = {"argv": ["echo"], "pre": [{"argv": ["echo", "one"]}, {"argv": ["exit", "2"]}, {"argv": ["echo", "never"]}]}
        o = self.see(base.spec("app:__main__", EXITS_0, stimulus))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        f = base.facts_of(o)
        self.assertEqual(sorted(f), ["pre", "pre_failed", "subject"])
        self.assertEqual((f["subject"], f["pre_failed"], [p["exit_code"] for p in f["pre"]]), ("present", 1, [0, 2]))


class TheMarkerFileNamesEachInvocation(_Checkouts):
    """The channel's marker file follows the grammar the module docstring documents: READY, DISPATCHED, one
    `PRE <i>` line per pre-step in order, then `MAIN {"before": <the named files before the main invocation>}`, then
    RESULT and END. Nothing in the parent reads PRE and MAIN (it waits for DISPATCHED and RESULT), so they are the
    channel's record of which invocation was running: what a reader of a kept evaluation directory has when the
    controller ended without a result.

    Pins HARNESS/main [68] (PRE), [51] (MAIN), [78, 108] (the body of MAIN)."""

    def test_the_lines_follow_the_documented_grammar(self):
        scratch = tempfile.TemporaryDirectory(prefix="aisef2-t21b-scratch-", ignore_cleanup_errors=True)
        self.addCleanup(scratch.cleanup)
        observable = {"exit_code": 0, "files": {"<ws>/note.txt": {"equals_before": True},
                                                "<ws>/out.txt": {"absent": True}}}
        stimulus = {"argv": ["echo", "main"], "workspace": {"note.txt": {"text": "hello"}},
                    "pre": [{"argv": ["echo", "zero"]}, {"argv": ["echo", "one"]}]}
        o = self.see(base.spec("app:__main__", observable, stimulus), probe=CliInvocationProbe(scratch=scratch.name))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        logs = sorted(pathlib.Path(scratch.name).glob("*/protocol.log"))
        self.assertEqual(len(logs), 1)
        lines = []
        for line in logs[0].read_bytes().decode("utf-8").splitlines():
            parts = line.split(" ", 4)   # <mark> <tag> <nonce> <mac> [<body>]
            lines.append((parts[1], parts[4] if len(parts) == 5 else ""))
        tags = [tag for tag, _ in lines]
        # the parent concludes on RESULT and then stops the controller: END is written right after RESULT, but this
        # file is read the moment the observation returns, so an END the controller was stopped before writing is
        # not a defect (RESULT is always there: it is what the observation was concluded on)
        self.assertEqual(tags[:6], ["READY", "DISPATCHED", "PRE", "PRE", "MAIN", "RESULT"])
        self.assertIn(tags[6:], ([], ["END"]))
        self.assertEqual([body for tag, body in lines if tag == "PRE"], ["0", "1"])
        main = [body for tag, body in lines if tag == "MAIN"]
        before = {"note.txt": {"sha256": sha(b"hello")}, "out.txt": {"absent": True}}
        self.assertEqual([json.loads(b) for b in main], [{"before": before}])
        self.assertEqual(base.facts_of(o)["before"], before)   # the observation's own `before` is the same snapshot


class AHardExitOfTheMainInvocationKeepsTheFiles(_Checkouts):
    """A CLI that ends its own process (`os._exit`) after doing its work is observed like any other: the controller
    outlives the subject's process and still builds, itself, the before and after facts of every named file, so an
    `exits_files` observable is decided over them. Were they missing, `equals_before` and `absent` could never hold of
    a program that ends itself, and the contract would be refuted for no fault of the product.

    Pins HARNESS/main [112, 113, 120, 121]."""

    def test_the_files_are_decided_over_the_before_and_after_facts_of_the_named_files(self):
        files = {"<ws>/keep.txt": {"equals_before": True}, "<ws>/out.txt": {"text": "made"},
                 "<ws>/none.txt": {"absent": True}}
        stimulus = {"argv": ["writeexit", "<ws>/out.txt", "made", "3"], "workspace": {"keep.txt": {"text": "kept"}}}
        s = base.spec("app.sub:main", {"exit_code": 3, "files": files}, stimulus)
        o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        f = base.facts_of(o)
        self.assertEqual((f["subject"], f["exit_code"], f["hard_exit"]), ("present", 3, True))
        kept = {"sha256": sha(b"kept")}
        self.assertEqual(f["before"], {"keep.txt": kept, "none.txt": {"absent": True}, "out.txt": {"absent": True}})
        self.assertEqual(f["files"], {"keep.txt": kept, "none.txt": {"absent": True},
                                      "out.txt": {"sha256": sha(b"made")}})
        self.assertEqual(self.result(s), Executed(S))

    def test_a_file_the_process_left_differently_is_still_refuted(self):
        """The same facts decide the other way: the file the process wrote is not what `equals_before` says."""
        stimulus = {"argv": ["writeexit", "<ws>/keep.txt", "changed", "3"], "workspace": {"keep.txt": {"text": "kept"}}}
        s = base.spec("app.sub:main", {"exit_code": 3, "files": {"<ws>/keep.txt": {"equals_before": True}}}, stimulus)
        o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        self.assertEqual(base.facts_of(o).get("files"), {"keep.txt": {"sha256": sha(b"changed")}})


if __name__ == "__main__":
    unittest.main()
