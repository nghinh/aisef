"""V2.1 (owner decision of 2026-10-15, item 3 — RV-2, the state of the machine reader): a probe that executed and decided
nothing is its own status, INDETERMINATE, and a check that could not be carried out is never NOT_REPRODUCED.

`review_verify.verify` gives a finding one of four statuses, and each says something different:

* CONFIRMED — the probe executed and REFUTED the stated behaviour: the only status that is evidence for the finding;
* NOT_REPRODUCED — the probe executed and SATISFIED the stated behaviour: the only status that is evidence that the
  finding does not reproduce;
* INDETERMINATE — the probe executed and decided nothing (`Executed(INDETERMINATE, reason)`): evidence of nothing;
* UNVERIFIABLE — nothing was observed: no reproducer, no meaning, not calibrated, or a probe that did not execute
  (UNRUNNABLE: its harness failed or reached a limit of its own — a deadline, a cap, a worker that did not answer; or
  INVALID_SPEC). A limit of the tool is never a verdict about the product.

Pinned here: the mapping from every kind of probe result to its status (and that nothing but CONFIRMED blocks or carries
evidence, under every policy, severity and anchor); the vocabulary (what fits the statement's bound, what is stated
whole); who reads the vocabulary (a census: a new reader must be shown to handle INDETERMINATE); and the rule for old
records — a statement or an artifact written with the earlier vocabulary (an undecided probe under NOT_REPRODUCED,
beside `observed: INDETERMINATE`) still verifies, byte for byte, and is not reinterpreted or rewritten by anything.

The end to end of the new status (journal row, RUN.json, artifact) is test_v21_r5_review_indeterminate.py."""

from __future__ import annotations

import ast
import json
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason, InvalidSpec, Unrunnable  # noqa: E402
from tests.v2 import test_v21_kills3_T15a as T  # noqa: E402 — the module: its tests are not collected again
from tests.v2 import test_v21_r3_detail_artifact as A  # noqa: E402 — likewise

S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
ANCHORED = V.Anchor(V.ANCHORED, "clause R-9/3's approved outcome", ("BC-1", "BC-2"))


class EveryProbeResultHasItsStatus(T.Checkout):
    """The probe's result is injected (a sealed record replaced, a calibration present), so the status is decided by
    `verify` alone and on every platform."""

    RESULTS = (
        ("SATISFIED", Executed(S), V.NOT_REPRODUCED, "SATISFIED"),
        ("REFUTED", Executed(R), V.CONFIRMED, "REFUTED"),
        *((f"INDETERMINATE {r.value}", Executed(I, r), V.INDETERMINATE, "INDETERMINATE") for r in IndeterminateReason),
        ("UNRUNNABLE: a worker's deadline", Unrunnable("regex search DEADLINE: the search did not finish within the "
                                                       "harness watchdog (60s: timeouts_s.probe)"), V.UNVERIFIABLE, None),
        ("UNRUNNABLE: a harness failure", Unrunnable("harness timeout: no READY within 60s"), V.UNVERIFIABLE, None),
        ("UNRUNNABLE: a tool limit", Unrunnable("grep_count worker DEADLINE: the regex loop did not finish"),
         V.UNVERIFIABLE, None),
        ("INVALID_SPEC", InvalidSpec("the probe input names a developer test artefact"), V.UNVERIFIABLE, None),
    )

    def injected(self, result) -> V.Verification:
        with mock.patch.object(V, "run_probe", return_value=object()), \
                mock.patch.object(V, "bound_result", return_value=result), \
                mock.patch.object(V, "calibration_for", return_value=object()):     # the table is not what is under test
            return self.verify(T.finding(), self.tmp)

    def test_the_status_and_the_probe_s_verdict_of_every_kind_of_result(self):
        for what, result, status, observed in self.RESULTS:
            with self.subTest(what):
                v = self.injected(result)
                self.assertEqual((v.status, v.observed), (status, observed), v)

    def test_not_reproduced_is_exactly_a_satisfied_verdict(self):
        """The one status that says the finding was shown not to reproduce rests on one thing: the probe executed and
        SATISFIED the stated behaviour. A verdict that is undecided, and a probe that did not execute, are not it."""
        for what, result, _, _ in self.RESULTS:
            with self.subTest(what):
                shown = isinstance(result, Executed) and result.behavior_verdict is S
                self.assertEqual(self.injected(result).status == V.NOT_REPRODUCED, shown)

    def test_a_probe_that_did_not_execute_says_so_and_names_what_it_said(self):
        for what, result, _, _ in self.RESULTS:
            if isinstance(result, Executed):
                continue
            with self.subTest(what):
                v = self.injected(result)
                self.assertIn("did not execute the reproducer", v.reason)
                self.assertIn(result.detail[:40], v.reason)
                self.assertNotIn("does not reproduce", v.reason)

    def test_nothing_but_confirmed_blocks_or_carries_evidence(self):
        f = T.finding()
        for what, result, status, _ in self.RESULTS:
            v = self.injected(result)
            with self.subTest(what):
                self.assertEqual(v.evidence() != "", status == V.CONFIRMED)
                for policy in V.POLICIES:
                    for floor in V.SEVERITIES:
                        for sev in V.SEVERITIES:
                            blocked = V.blocks(v, {**f, "severity": sev}, policy, floor, ANCHORED)
                            want = (status == V.CONFIRMED and policy == "fix-loop"
                                    and V.SEVERITIES.index(sev) >= V.SEVERITIES.index(floor))
                            self.assertEqual(blocked, want, (policy, floor, sev))


class TheVocabulary(unittest.TestCase):
    def test_the_statuses_are_these_four_and_each_fits_the_statement_whole(self):
        self.assertEqual(V.STATUSES, (V.CONFIRMED, V.NOT_REPRODUCED, V.INDETERMINATE, V.UNVERIFIABLE))
        self.assertEqual(len(set(V.STATUSES)), 4)
        self.assertEqual(sorted(V.STATUSES), ["CONFIRMED", "INDETERMINATE", "NOT_REPRODUCED", "UNVERIFIABLE"])
        f = T.finding()
        for status in V.STATUSES:
            with self.subTest(status):
                self.assertLessEqual(len(status), V.STATUS_MAX)      # or `detail` would cut it
                stated = json.loads(V.detail(f, V.Verification(status, "why", "probe.cli_invocation", None), None, None))
                self.assertEqual(stated["verification"], status)
                self.assertNotIn("elided", stated)


STATUS_NAMES = frozenset(("CONFIRMED", "NOT_REPRODUCED", "INDETERMINATE", "UNVERIFIABLE"))
#: the three names no other vocabulary of aisef2 uses: any mention, by name or by literal, is a reference
UNIQUE = frozenset(("CONFIRMED", "NOT_REPRODUCED", "UNVERIFIABLE"))
#: the two files whose own `INDETERMINATE` is another record's (review_ocr: the coverage of a finder's run; arch/enums:
#: the verdict enums): the literal may be there, as the definition of that vocabulary and as nothing else
OTHER_INDETERMINATE = ("aisef2/app/review_ocr.py", "aisef2/arch/enums.py")


def _is_review_verify(module: str | None) -> bool:
    return module is not None and (module == "review_verify" or module.endswith(".review_verify"))


def references(source: str, rel: str) -> set[str]:
    """Every way `source` (the file `rel` of aisef2) names a verification status of `review_verify`: the module's
    attribute (`review_verify.X`, through any alias of the module), a name imported from it (through any alias), the three
    names no other vocabulary has (as a name or a string), and the literal "INDETERMINATE" outside the two files whose
    own INDETERMINATE is another record's. A reader of `Verification.status` has to say one of these to compare it with
    anything, so a reader that is new fails the census whichever way it is written."""
    tree = ast.parse(source)
    modules, imported, found = set(), {}, set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            modules |= {a.asname or a.name for a in n.names if _is_review_verify(a.name)}
        elif isinstance(n, ast.ImportFrom):
            if _is_review_verify(n.module):
                for a in n.names:
                    if a.name in STATUS_NAMES | {"STATUSES"}:
                        imported[a.asname or a.name] = a.name
                        found.add(f"review_verify.{a.name}")
            else:
                modules |= {a.asname or a.name for a in n.names if a.name == "review_verify"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in STATUS_NAMES | {"STATUSES"} and (
                (isinstance(n.value, ast.Name) and n.value.id in modules)
                or (isinstance(n.value, ast.Attribute) and n.value.attr == "review_verify")):
            found.add(f"review_verify.{n.attr}")
        elif isinstance(n, ast.Name) and (n.id in UNIQUE or n.id in imported):
            found.add(n.id if n.id in UNIQUE else f"review_verify.{imported[n.id]}")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and (
                n.value in UNIQUE or (n.value == "INDETERMINATE" and rel not in OTHER_INDETERMINATE)):
            found.add(repr(n.value))
    return found


def only_defined(source: str) -> bool:
    """Whether every "INDETERMINATE" literal of `source` is (an element of) the value of an assignment — the definition of
    a vocabulary — and nowhere else: in a comparison, a call, a subscript or a collection key it would be a reader."""
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and n.value == "INDETERMINATE":
            up = parents[n]
            held = up.elts if isinstance(up, ast.Tuple) else [n]
            holder = parents[up] if isinstance(up, ast.Tuple) else up
            if not (isinstance(holder, ast.Assign) and (holder.value is n or holder.value is up) and n in held):
                return False
    return True


class WhoReadsTheVocabulary(unittest.TestCase):
    """The census of who names a verification status in aisef2. Nothing reads the value of `verification.status` but
    `review_verify` itself (`blocks`, `evidence`, `detail`): `artifact_problems` binds an artifact to a row by bytes and
    identity, never by status; the adapter stores what `verify` answered; RUN.json and the journal row carry it. A new
    reader would have to be shown to handle INDETERMINATE (and every status a later release adds), so it fails here —
    whether it names the status through the module, through a name imported from it, through the three names no other
    vocabulary has, or through the literal "INDETERMINATE" (F5 of the review: the first version of this census watched
    `review_verify.INDETERMINATE` only, so `from aisef2.app.review_verify import INDETERMINATE` and
    `status == "INDETERMINATE"` passed it)."""

    #: the only references outside review_verify.py: the adapter answers a finding with no reproducer UNVERIFIABLE
    ALLOWED = {"aisef2/app/adapters.py": {"review_verify.UNVERIFIABLE"}}

    def census(self) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        for path in sorted((ROOT / "aisef2").rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel != "aisef2/app/review_verify.py" and (names := references(path.read_text(encoding="utf-8"), rel)):
                found[rel] = names
        return found

    def test_no_reader_of_the_status_but_the_one_that_answers_a_finding_without_a_reproducer(self):
        self.assertEqual(self.census(), self.ALLOWED)

    def test_the_two_files_with_an_indeterminate_of_their_own_only_define_it(self):
        for rel in OTHER_INDETERMINATE:
            with self.subTest(rel):
                self.assertTrue(only_defined((ROOT / rel).read_text(encoding="utf-8")), rel)

    def test_the_census_sees_every_way_to_name_a_status(self):
        """Each way a new reader could be written, as source: found. And what is not a reader: not."""
        readers = {
            "a name imported from the module": "from aisef2.app.review_verify import INDETERMINATE\nif s == INDETERMINATE: pass\n",
            "... under another name": "from aisef2.app.review_verify import INDETERMINATE as UNDECIDED\nx = UNDECIDED\n",
            "the module's attribute": "from aisef2.app import review_verify\nx = review_verify.INDETERMINATE\n",
            "... through an alias of the module": "from aisef2.app import review_verify as rv\nx = rv.INDETERMINATE\n",
            "... through import as": "import aisef2.app.review_verify as rv\nx = rv.STATUSES\n",
            "... through the dotted path": "import aisef2.app.review_verify\nx = aisef2.app.review_verify.INDETERMINATE\n",
            "a literal compared with a status": "def f(v):\n    return v.status == 'INDETERMINATE'\n",
            "a literal in a collection": "X = ('CONFIRMED', 'INDETERMINATE')\n",
            "a name no other vocabulary has": "def f(v):\n    return v.status == CONFIRMED\n",
            "the literal of one of them": "def f(v):\n    return v.status != 'NOT_REPRODUCED'\n",
        }
        for what, source in readers.items():
            with self.subTest(what):
                self.assertTrue(references(source, "aisef2/app/new_reader.py"), source)
        not_readers = {
            "the module's other names": "from aisef2.app import review_verify\nx = review_verify.ARTIFACT_DIR\n",
            "a class of the module": "from aisef2.app.review_verify import Verification\nx = Verification\n",
            "another vocabulary's attribute": "from aisef2.arch.enums import BehaviorVerdict\nx = BehaviorVerdict.INDETERMINATE\n",
            "a sentence that holds the word": "x = 'vacuity is INDETERMINATE'\n",
        }
        for what, source in not_readers.items():
            with self.subTest(what):
                self.assertEqual(references(source, "aisef2/app/new_reader.py"), set(), source)
        self.assertEqual(references("COMPLETE, INDETERMINATE = 'COMPLETE', 'INDETERMINATE'\n", OTHER_INDETERMINATE[0]), set())

    def test_the_definition_check_sees_a_reader_in_the_files_that_are_allowed_the_literal(self):
        self.assertTrue(only_defined("COMPLETE, INDETERMINATE = 'COMPLETE', 'INDETERMINATE'\nINDETERMINATE = 'INDETERMINATE'\n"))
        for source in ("def f(s):\n    return s == 'INDETERMINATE'\n", "X = f('INDETERMINATE')\n",
                       "X = {'INDETERMINATE': 1}\n", "if s in ('INDETERMINATE',):\n    pass\n"):
            with self.subTest(source):
                self.assertFalse(only_defined(source))

    def test_the_other_indeterminate_is_a_different_record(self):
        """review_ocr's INDETERMINATE is the COVERAGE of a finder's run (`session.coverage.status`: the candidate was not
        fully reviewed), a record of its own that no verification reads or writes."""
        from aisef2.app import review_ocr
        self.assertEqual((review_ocr.COMPLETE, review_ocr.INDETERMINATE), ("COMPLETE", "INDETERMINATE"))
        tree = ast.parse((ROOT / "aisef2/app/review_ocr.py").read_text(encoding="utf-8"))
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in {"CONFIRMED", "NOT_REPRODUCED",
                                                                                          "UNVERIFIABLE", "Verification"}])


class RecordsOfTheEarlierVocabulary(A.Scratch):
    """Before the owner's decision an undecided probe was written NOT_REPRODUCED, beside `observed: INDETERMINATE` — with
    the sentence "observes the stated behaviour: the finding does not reproduce" (a release of this window's parent) or
    with the corrected "could not decide" one (this window's first part). Such a statement and its artifact verify as
    they always did, are not rewritten, and mean what they say through `observed`: nothing is migrated, because nothing
    reads the status. The format of the artifact (`aisef-v2-review-finding/1`) names a shape, and the shape is unchanged."""

    EARLIER = (
        ("the sentence of the parent", V.Verification(
            V.NOT_REPRODUCED, "probe.cli_invocation observes the stated behaviour: the finding does not reproduce",
            "probe.cli_invocation", "INDETERMINATE")),
        ("the corrected sentence", V.Verification(
            V.NOT_REPRODUCED, "probe.cli_invocation could not decide the stated behaviour (INDETERMINATE, "
                              "PRECONDITION_ABSENT): neither confirmed nor ruled out", "probe.cli_invocation",
            "INDETERMINATE")),
    )

    def written(self, v: V.Verification, attempt: int):
        f = A.finding(verification={"status": v.status, "why": v.reason, "probe": v.probe, "observed": v.observed})
        art = self.keep(f, attempt=attempt)
        return f, art, V.detail(f, v, ANCHORED, art)

    def test_such_a_row_and_its_artifact_verify_and_stay_as_written(self):
        for attempt, (what, v) in enumerate(self.EARLIER, 1):
            with self.subTest(what):
                f, art, text = self.written(v, attempt)
                path = self.out / art.path
                before = path.read_bytes()
                kept = json.loads(before)["finding"]["verification"]
                self.assertEqual((kept["status"], kept["observed"]), (V.NOT_REPRODUCED, "INDETERMINATE"))
                for passed in (True, False):
                    self.assertEqual(V.artifact_problems(self.out, [A.row(9, "S1", "FND-7", f"informational — {text}",
                                                                          passed)]), ([], []))
                self.assertEqual(path.read_bytes(), before)       # not rewritten by the check
                self.assertEqual(json.loads(text)["verification"], V.NOT_REPRODUCED)     # nor by the statement

    def test_such_a_status_never_blocks_under_any_policy(self):
        for what, v in self.EARLIER:
            for policy in V.POLICIES:
                with self.subTest(what, policy=policy):
                    self.assertFalse(V.blocks(v, A.finding(), policy, "low", ANCHORED))
                    self.assertEqual(v.evidence(), "")

    def test_the_binding_is_to_bytes_and_identity_never_to_a_status(self):
        """So a status a later release adds needs no change in the reader: the row binds the file whatever it says."""
        for attempt, status in enumerate((*V.STATUSES, "A_STATUS_OF_A_LATER_RELEASE"), 1):
            with self.subTest(status):
                f = A.finding()
                v = V.Verification(status, "why", "probe.cli_invocation", "REFUTED")
                art = V.preserve(self.out, {**f, "verification": {"status": status}}, story="S1", attempt=attempt,
                                 index=0, revision=A.HEAD)
                text = V.detail(f, v, None, art)
                self.assertEqual(V.artifact_problems(self.out, [A.row(9, "S1", "FND-7", f"informational — {text}")]),
                                 ([], []))


class RecordsOfTheReleaseBeforeTheStatements(unittest.TestCase):
    """The review rows of a committed 2.0.0 journal (closure-evidence/v2/release/smoke-2) carry no statement at all —
    "advisory: ..." or "informational" — so there is no status in them and nothing to bind: `--verify` takes them as it
    always did. (The 28 RUN.json tracked in closure-evidence hold no finding with a `verification`: no committed
    record carries the vocabulary of 2.1, old or new.)"""

    def test_its_review_rows_are_no_problem_and_no_note(self):
        path = ROOT / "closure-evidence/v2/release/smoke-2/run-1/aisef-run.jsonl"
        events = [json.loads(line)["event"] for line in path.read_text(encoding="utf-8").splitlines() if ":review:" in line]
        self.assertTrue(events)
        self.assertTrue(all(" — " not in e["data"]["detail"] for e in events))
        self.assertEqual(V.artifact_problems(path.parent, events), ([], []))


if __name__ == "__main__":
    unittest.main()
