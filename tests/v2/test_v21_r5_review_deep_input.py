"""V2.1 (owner's fix window of 2026-10-15; RV-1 of docs/v2.1/decisions/B03-R4-REVIEW.md section 6): data a model nested
deeper than the review's own contracts read is a *reason* or a typed outcome, never a `RecursionError`.

Requirement (tests/v2/test_v21_kills3_T15a.py, header and `ReproducerThatIsNotAContractIsAReason`): "a reproducer that
is not a contract is a *reason* (verify -> UNVERIFIABLE, anchor -> UNANCHORED), never an exception", because "an
exception reaches app/run.py and the story is REFUSED". Measured on the parent of this window (CPython 3.12.14 and
3.14.7, identical): a reproducer nested 3,000 levels ended `Reviewer.review` in a `RecursionError` out of the kernel's
contract walks (`freeze`, `names_test_artefact`, `plain`: dicts from ~985 levels, lists from ~494) — the review's
other findings were lost, the story was REFUSED and had no verdict. The recursion limit is never raised to make a
deeper one fit.

The bound is the module's own `DEPTH_MAX` (no probe grammar nests that far; the largest nesting of any stimulus or
observable in the repository's plans, contracts and evidence is 7 levels, 8 with the reproducer around it): what
`preserve` keeps whole, the root of that walk being the finding, so the reproducer that ran is always the one the
artifact holds. The check walks the value with a stack of its own: nothing it does recurses.

What is asserted, and who relies on it:

* every place a reproducer can nest answers verify -> UNVERIFIABLE (no probe: the root is never read), anchor ->
  UNANCHORED and `blocks` False, at depths from 70 to 20,000, and the reason names the bound and what to do;
* the refusal does not rest on a high recursion limit: with the limit lowered to the caller's depth + 300 a
  20,000-level reproducer is still refused;
* the bound is exactly what the artifact keeps: for every depth around `DEPTH_MAX` a reproducer is accepted if and only
  if `redacted` of its finding keeps it whole;
* through `Reviewer.review` such a finding is one typed, non-blocking row whose statement is bounded and whose artifact
  exists, beside the review's other findings — not an exception out of the review;
* the same holds for a finding's prose (id, severity, summary), which `str()` reads: nested past `DEPTH_MAX` it is
  written with the artifact's marker before anything reads it;
* a document the JSON parser itself cannot read (nested past its depth: ~1,000 levels on 3.11, ~10,000 on 3.12) is
  unparseable text like any other — a model's findings document: no findings, never blocking; a reproducer block: kept
  as text, carrying nothing; OCR's output: no document; a line of a session's stream: no event."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client  # noqa: E402
from aisef2.app import review_ocr as ocr  # noqa: E402
from aisef2.app import review_verify as V  # noqa: E402
from aisef2.arch.enums import ControlProjection  # noqa: E402
from aisef2.product.contract import BehaviorContract, plain  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

REQUIREMENTS = {"R-9": object()}
ROOTS = ("ledgerlock",)
MAIN = {"kind": "cli_invocation", "locator": "ledgerlock:__main__"}
PROJECT = types.SimpleNamespace(requirements=REQUIREMENTS, product_roots=ROOTS, approvals=(),
                                plan=types.SimpleNamespace(obligations=()), facts={}, specs={}, contracts={})
#: the largest nesting of a stimulus or observable of any plan, contract or evidence file of the repository, measured
#: with the reproducer around it (the reproducer is level 1)
LARGEST_REAL = 8


def nested(kind: str, levels: int, leaf="x"):
    """`leaf` inside `levels` containers, built without recursion."""
    value = leaf
    for _ in range(levels):
        value = {"a": value} if kind == "dict" else [value] if kind == "list" else (value,)
    return value


def finding(**reproducer) -> dict:
    rep = {"clause": "R-9/3", "subject": dict(MAIN), "stimulus": {"argv": ["x"]}, "observable": {"exit_code": 3, "within_s": 10}}
    return {"id": "F-1", "severity": "high", "summary": "a reviewer's finding", "reproducer": {**rep, **reproducer}}


def at_depth(levels: int) -> dict:
    """A finding whose reproducer holds containers `levels` deep, the reproducer itself being level 1."""
    return finding(stimulus={"argv": ["x"], "env": nested("dict", levels - 2, "v")})


def verify(f: dict) -> V.Verification:
    return V.verify(f, requirements=REQUIREMENTS, product_roots=ROOTS, root="/nonexistent-checkout-of-rv-1",
                    revision="0" * 40, timeout_s=5, interpreter=sys.executable)


class DeepReproducerIsAReason(unittest.TestCase):

    #: (where, how it is built, the depths). A tuple that is a mapping key is hashed to be built, so its depths stop at
    #: 3,000; every other place is built iteratively and walked by the check with a stack of its own.
    PLACES = (
        ("a stimulus key (env)", lambda n: finding(stimulus={"argv": ["x"], "env": nested("dict", n)}), (70, 984, 3000, 20_000)),
        ("a stimulus list (argv)", lambda n: finding(stimulus={"argv": nested("list", n)}), (70, 984, 3000, 20_000)),
        ("a tuple (a direct caller's)", lambda n: finding(stimulus={"argv": nested("tuple", n)}), (70, 984, 3000)),
        ("a mapping key (a direct caller's)", lambda n: finding(stimulus={nested("tuple", n): "v"}), (70, 984, 3000)),
        ("the observable", lambda n: finding(observable={"exit_code": 3, "within_s": 10, "x": nested("dict", n)}),
         (70, 984, 3000, 20_000)),
        ("the clause", lambda n: finding(clause=nested("list", n)), (70, 984, 3000, 20_000)),
        ("the subject's locator", lambda n: finding(subject={"kind": MAIN["kind"], "locator": nested("dict", n)}),
         (70, 984, 3000, 20_000)),
    )

    def test_every_place_a_reproducer_can_nest_is_refused_with_a_status(self):
        for what, build, depths in self.PLACES:
            for n in depths:
                with self.subTest(what=what, levels=n):
                    f = build(n)
                    c = V.reproducer_contract(f, REQUIREMENTS, ROOTS)
                    self.assertIsInstance(c, str)
                    self.assertIn(str(V.DEPTH_MAX - 1), c)      # the reason names the bound ...
                    self.assertIn("flatter", c)                  # ... and what to do about it
                    v = verify(f)       # refused before any probe: the root does not exist
                    a = V.anchor(f, PROJECT)
                    self.assertEqual((v.status, v.probe, v.observed), (V.UNVERIFIABLE, None, None))
                    self.assertEqual(a.status, V.UNANCHORED)
                    self.assertFalse(V.blocks(v, f, "fix-loop", "low", a))
                    self.assertLessEqual(len(c), V.WHY_MAX)      # the statement holds the whole reason

    def test_the_refusal_does_not_rest_on_a_high_recursion_limit(self):
        frame, here = sys._getframe(), 0
        while frame is not None:
            frame, here = frame.f_back, here + 1
        f = finding(stimulus={"argv": ["x"], "env": nested("dict", 20_000)})
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(here + 300)      # the check needs a frame or two; a recursive walk of 20,000 levels cannot
        try:
            c = V.reproducer_contract(f, REQUIREMENTS, ROOTS)
            a = V.anchor(f, PROJECT)
        finally:
            sys.setrecursionlimit(limit)
        self.assertIsInstance(c, str)
        self.assertEqual(a.status, V.UNANCHORED)
        self.assertEqual(sys.getrecursionlimit(), limit)

    def test_the_bound_is_what_the_artifact_keeps_whole(self):
        accepted = []
        for levels in range(V.DEPTH_MAX - 6, V.DEPTH_MAX + 6):
            f = at_depth(levels)
            with self.subTest(levels=levels):
                c = V.reproducer_contract(f, REQUIREMENTS, ROOTS)
                kept_whole = V.redacted(f)[0]["reproducer"] == f["reproducer"]
                self.assertEqual(isinstance(c, BehaviorContract), kept_whole)
                if isinstance(c, BehaviorContract):
                    accepted.append(levels)
                    self.assertEqual(plain(c.stimulus), f["reproducer"]["stimulus"])      # what ran is what was written
        self.assertEqual(accepted, list(range(V.DEPTH_MAX - 6, V.DEPTH_MAX)))      # the artifact's walk starts at the finding

    def test_what_the_repository_holds_and_every_probe_grammar_needs_is_far_inside_the_bound(self):
        self.assertGreaterEqual(V.DEPTH_MAX - 1, 4 * LARGEST_REAL)
        self.assertIsInstance(V.reproducer_contract(at_depth(LARGEST_REAL), REQUIREMENTS, ROOTS), BehaviorContract)

    def test_the_contract_a_bounded_reproducer_makes_fits_the_callers_stack(self):
        """The deepest reproducer the bound admits, of the shape that costs most frames a level (a list: its walk is a
        generator), is read with room to spare under the default recursion limit from a caller 150 frames deep."""
        f = finding(stimulus={"argv": ["x"], "args": nested("list", V.DEPTH_MAX - 3)})      # 63 levels in all
        frame, here = sys._getframe(), 0
        while frame is not None:
            frame, here = frame.f_back, here + 1
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(here + 150 + 400)
        try:
            def deeper(k):
                return V.reproducer_contract(f, REQUIREMENTS, ROOTS) if k == 0 else deeper(k - 1)
            self.assertIsInstance(deeper(150), BehaviorContract)
        finally:
            sys.setrecursionlimit(limit)


class DeepFindingsAreRows(unittest.TestCase):
    """`Reviewer.review` over findings a finder returned: a deep one is a typed row, and the others are still reviewed."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        e2e.make_repo(self.tmp / "repo")
        self.project = bundle.load(e2e.project_bundle("a" * 40))
        self.run = types.SimpleNamespace(events=[], state=lambda proj: {"S1": {"attempt": 1}}
                                         if proj is ControlProjection.STORY_STATE else None)
        self.rev = ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5,
                               review={"policy": "fix-loop", "min_severity": "low", "finder": "model", "ocr": None,
                                       "given": True})
        self.scope = types.SimpleNamespace(story_id="S1", root=str(self.tmp / "repo"))

    def review(self, found: list):
        with mock.patch.object(self.rev, "_model", return_value=(found, {"parsed": True}, None)):
            return self.rev.review(self.scope, ("C-ADD",))

    @staticmethod
    def deep_reproducer(levels: int) -> dict:
        return {"id": "F-RV1", "severity": "critical", "summary": f"the reproducer nests {levels} levels",
                "reproducer": {"clause": "R-ADD/1.1", "subject": {"kind": "python_callable", "locator": "app.calc:add"},
                               "stimulus": {"args": [nested("list", levels)]}, "observable": {"returns": 5, "within_s": 10}}}

    def test_a_reproducer_nested_3000_levels_is_a_row_and_the_review_completes(self):
        r = self.review([self.deep_reproducer(3000)])
        self.assertEqual(r.outcome.value, "COMPLETED")
        (row,) = r.findings
        self.assertFalse(row.blocks)
        self.assertLessEqual(len(row.detail), V.SUMMARY_MAX)
        stated = json.loads(row.detail)
        self.assertEqual((stated["verification"], stated["anchor"]), (V.UNVERIFIABLE, V.UNANCHORED))
        self.assertIn(str(V.DEPTH_MAX - 1), stated["why"])
        kept = self.tmp / stated["artifact"]["path"]
        self.assertTrue(kept.is_file())
        self.assertIn(f"<nested deeper than {V.DEPTH_MAX} levels>", kept.read_text(encoding="utf-8"))

    def test_the_other_findings_of_the_review_are_still_reviewed(self):
        fine = {"id": "F-OK", "severity": "low", "summary": "no reproducer"}
        r = self.review([self.deep_reproducer(3000), fine])
        self.assertEqual([(f.id, f.blocks) for f in r.findings], [("F-RV1", False), ("F-OK", False)])
        self.assertEqual(json.loads(r.findings[1].detail)["verification"], V.UNVERIFIABLE)

    def test_the_prose_of_a_finding_nested_past_the_bound_is_written_with_the_marker(self):
        """`str()` of an id, a severity or a summary of 80,000 levels is a `RecursionError` on 3.12 and 3.14 alike (3.14:
        from 69,726); the statement and the gate row are made of them."""
        deep = {"id": nested("list", 80_000), "severity": nested("list", 80_000), "summary": nested("dict", 80_000),
                "blocking": False}
        r = self.review([deep])
        (row,) = r.findings
        marker = f"<nested deeper than {V.DEPTH_MAX} levels>"
        self.assertEqual(row.id, marker)
        self.assertFalse(row.blocks)
        stated = json.loads(row.detail)
        self.assertEqual((stated["finding"], stated["summary"], stated["severity"]), (marker, marker, "low"))
        self.assertEqual(stated["verification"], V.UNVERIFIABLE)

    def test_a_finding_that_is_not_deep_is_the_object_the_finder_returned(self):
        """Nothing is copied when nothing is deep: the review's record and its callers see the finder's own objects."""
        f = {"id": "F1", "severity": "low", "summary": "s", "extra": [[1, 2], {"k": [3]}]}
        self.assertIs(V.bounded(f), f)
        self.assertEqual(V.bounded({**f, "summary": nested("list", V.DEPTH_MAX + 1)})["summary"],
                         f"<nested deeper than {V.DEPTH_MAX} levels>")

    def test_bounded_keeps_the_whole_finding_and_redacts_only_the_too_deep_field(self):
        """A finding with one field nested past the bound is returned whole, with only that field written as the
        marker. adapters.Reviewer reads id (the gate row's lineage), severity and reproducer (the verdict) and
        blocking off this object, and preserve keeps it whole, so every un-deep field must survive; dropping
        `**finding` would strip the finding to the lone marker."""
        marker = f"<nested deeper than {V.DEPTH_MAX} levels>"
        f = {"id": "F-1", "severity": "high", "summary": "a finding", "blocking": True,
             "reproducer": {"clause": "R-9/3", "subject": dict(MAIN)},
             "extra": nested("list", V.DEPTH_MAX + 1)}
        self.assertEqual(V.bounded(f), {**f, "extra": marker})


class ARepliesTheParserCannotReadIsUnparseableText(unittest.TestCase):
    """json.loads raises `RecursionError`, not `ValueError`, for text nested past its depth (the parser is bounded by
    the recursion limit on 3.11 and by a C limit of ~10,000 levels on 3.12). The module's own rule for text that does not
    parse is stated at each of the four readers; a depth the parser gives up at is the same text. The parser's limit is
    simulated (a `json.loads` that raises exactly what the interpreters' do) because the real one depends on the
    interpreter; the real thing is exercised below at a depth every supported parser either reads or gives up."""

    @staticmethod
    def gives_up(*a, **k):
        raise RecursionError("maximum recursion depth exceeded while decoding a JSON array from a unicode string")

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()

    def reviewer(self):
        e2e.make_repo(self.tmp / "repo")
        project = bundle.load(e2e.project_bundle("a" * 40))
        run = types.SimpleNamespace(events=[], state=lambda proj: {"S1": {"attempt": 1}}
                                    if proj is ControlProjection.STORY_STATE else None)
        return ad.Reviewer(run, project, self.tmp / "logs", {}, 5), types.SimpleNamespace(story_id="S1", root=str(self.tmp / "repo"))

    @staticmethod
    def session(text: str):
        def fake(name, prompt, cwd, log, timeout_s, **kw):
            return {"exit": 0, "timed_out": False, "stopped": None, "started": True, "error": None, "text": text,
                    "turns": 1, "tokens": {"input": 1, "output": 1}, "seconds": 0.0, "log": log.name}
        return mock.patch.object(client, "session", fake)

    def test_the_model_reviewers_document_is_no_findings_like_any_text_that_does_not_parse(self):
        rev, scope = self.reviewer()
        with self.session('{"findings": [{"id": "F1", "blocking": true}]}'), mock.patch("json.loads", self.gives_up):
            r = rev.review(scope, ("C-ADD",))
        self.assertEqual((r.outcome.value, r.findings, r.detail), ("COMPLETED", (), "0 findings, parsed=True"))

    def test_a_reproducer_block_the_parser_cannot_read_is_kept_as_text_and_carries_nothing(self):
        content = "it fails\n```aisef-reproducer\n{\"clause\": \"R-1/1\"}\n```\n"
        with mock.patch("json.loads", self.gives_up):
            rep, text = ocr.reproducer_of(content)
        self.assertEqual((rep, text), (None, content))

    def test_an_output_document_the_parser_cannot_read_is_no_document(self):
        out = self.tmp / "output.json"
        out.write_text('{"comments": []}', encoding="utf-8")
        with mock.patch("json.loads", self.gives_up):
            self.assertIsNone(ocr.read_output(out))
        self.assertEqual(ocr.read_output(out), {"comments": []})

    def test_a_line_of_a_stream_the_parser_cannot_read_is_no_event_and_the_others_are_read(self):
        log = self.tmp / "s.jsonl"
        log.write_text('{"type": "text", "part": {"text": "kept"}}\n{"type": "deep"}\n{"type": "step_finish", "part": '
                       '{"tokens": {"input": 3, "output": 4}}}\n', encoding="utf-8")
        real = json.loads

        def only_the_deep_line(text, *a, **k):
            if '"deep"' in text:
                raise RecursionError("maximum recursion depth exceeded while decoding a JSON object from a unicode string")
            return real(text, *a, **k)
        with mock.patch("json.loads", only_the_deep_line):
            seen = client.events(log)
            account = client.read_session(log)
        self.assertEqual([e["type"] for e in seen], ["text", "step_finish"])
        self.assertEqual((account["text"], account["turns"], account["tokens"]), ("kept", 1, {"input": 3, "output": 4}))

    def test_a_reproducer_nested_12000_levels_in_the_reviewers_text_ends_in_a_typed_review(self):
        """The parser reads it (3.14) or gives up (3.11-3.13); either way the review completes, nothing blocks, and the
        row — if there is one — says the reproducer was not verified."""
        rev, scope = self.reviewer()
        deep = {"findings": [{"id": "F-D", "severity": "critical", "summary": "deep", "reproducer": {
            "clause": "R-ADD/1.1", "subject": {"kind": "python_callable", "locator": "app.calc:add"},
            "stimulus": {"args": [1, 2], "kwargs": {}}, "observable": {"returns": 3, "within_s": 10}}}]}
        text = json.dumps(deep).replace('"kwargs": {}', '"kwargs": ' + "[" * 12_000 + "]" * 12_000)
        with self.session(text):
            r = rev.review(scope, ("C-ADD",))
        self.assertEqual(r.outcome.value, "COMPLETED")
        self.assertFalse(any(f.blocks for f in r.findings))
        for f in r.findings:
            self.assertEqual(json.loads(f.detail)["verification"], V.UNVERIFIABLE)


if __name__ == "__main__":
    unittest.main()
