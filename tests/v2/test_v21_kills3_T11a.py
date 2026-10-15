"""Mutation-survivor kills, batch T11a: aisef2/app/review_ocr.py::coverage and ::findings (V2.1, owner directive B-03).

Each class states a requirement of the Open Code Review adapter that no earlier test depended on, and the mutants
(`[index]` of validation/v21 survivor_view) it pins. Fixtures: tests/v2/fixtures/ocr/{complete,partial,preview}.json.

Reasons are read by an operator, the journal and the developer's retry prompt: the checks below look for the
identifying elements as whole tokens (the ids, the counts, the code and the words OCR gave), never for a sentence."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle  # noqa: E402
from aisef2.app import review_ocr as O  # noqa: E402
from aisef2.orchestrate.adapters import CapabilityUnrunnable, ProviderOutage  # noqa: E402
from tests.v2 import test_v21_review_chain as chain  # noqa: E402  (its bundle and git builders, not its tests)

FIX = ROOT / "tests/v2/fixtures/ocr"
A = json.loads((FIX / "complete.json").read_text(encoding="utf-8"))
B = json.loads((FIX / "partial.json").read_text(encoding="utf-8"))
PREVIEW = json.loads((FIX / "preview.json").read_text(encoding="utf-8"))
BASE, HEAD = "1" * 40, "2" * 40
REQUIRED = ["src/app/api.py", "src/app/limits.py"]
GONE = object()
_SPLIT = re.compile(r"[\s,;:()\[\]'\"]+")


def tokens(c: O.Coverage) -> set[str]:
    """The whole tokens of every reason: split on whitespace, commas, colons, brackets and quotes."""
    return {t for r in c.reasons for t in _SPLIT.split(r) if t}


def mention(c: O.Coverage, sha: str) -> tuple[int, int] | None:
    """Where the reasons name `sha`: (reason, token) of the first token that is 7 or more leading digits of it. How
    many digits a reason shows is its own choice; a token that fuses two commits is not a mention of either."""
    for i, reason in enumerate(c.reasons):
        for j, t in enumerate(t for t in _SPLIT.split(reason) if t):
            if len(t) >= 7 and sha.startswith(t):
                return i, j
    return None


def cov(out=A, code=0, required=REQUIRED, base=BASE, head=HEAD, preview=None) -> O.Coverage:
    return O.coverage(out, code, required=required, base=base, head=head, preview=preview)


def changed(f, out=A) -> dict:
    out = copy.deepcopy(out)
    f(out["manifest"])
    return out


def item_id(mode: str, old: str, new: str) -> str:
    """OCR's item id (internal/session/manifest.go ItemID), derived here independently of the module under test."""
    return hashlib.sha256("\x00".join(["review", mode, old, new]).encode("utf-8")).hexdigest()


class RequiredPathsAreNamedInSortedOrder(unittest.TestCase):
    """The same candidate gives the same record in every process: the required paths are deduplicated and sorted, so
    the paths a reason names are the smallest, once each, and `not_reviewable` is in path order (usage.no_progress
    compares failure details between attempts). Pins aisef2/app/review_ocr.py::coverage [12]. Without the sort the
    order is the process's hash seed: 14 and 15 paths make a coincidence with the sorted order a 1 in 14! chance, so
    the real code cannot flake and the mutant fails in every process."""

    def test_the_paths_a_reason_names_are_the_smallest_once_each_in_order(self):
        paths = [f"pkg/m{i:02d}.py" for i in range(15)]
        shuffled = [*paths[7:], *reversed(paths[:7]), paths[3]]      # not sorted, one path twice
        out = changed(lambda m: m["coverage"].__setitem__("completed", []))
        c = cov(out, required=shuffled)
        self.assertEqual(c.status, O.INDETERMINATE)
        named = [p for r in c.reasons for p in re.findall(r"pkg/m\d\d\.py", r)]
        self.assertGreaterEqual(len(named), 3, c.reasons)       # how many it names is its own cap; which, in what order
        self.assertEqual(named, paths[:len(named)])             # is the contract: the smallest, once each, in order

    def test_the_paths_the_finder_cannot_read_are_in_path_order(self):
        docs = [f"docs/d{i:02d}.md" for i in range(14)]
        rows = [{"path": p, "will_review": False, "exclude_reason": "unsupported_ext"} for p in docs]
        c = cov(required=[*REQUIRED, *reversed(docs)], preview={"files": [*PREVIEW["files"], *rows]})
        self.assertEqual((c.status, c.reasons), (O.COMPLETE, ()))
        self.assertEqual(c.not_reviewable, tuple(docs))


class ReusedItemsAreReviewedItems(unittest.TestCase):
    """Module docstring: every required path is `completed` or `reused` under the item_id OCR derives for it. A path
    OCR reports under coverage.reused is reviewed (a false INDETERMINATE otherwise, and under fix-loop a story that
    can never finish), its item_id is recomputed like a completed one's, and a manifest without the list reads it as
    empty rather than raising. Pins aisef2/app/review_ocr.py::coverage [27] [60] [107]."""

    @staticmethod
    def moved() -> dict:
        def f(m):
            m["coverage"]["reused"] = [m["coverage"]["completed"].pop(0)]       # src/app/limits.py
        return changed(f)

    def test_a_required_path_under_reused_is_reviewed(self):
        out = self.moved()
        self.assertEqual([i["path"] for i in out["manifest"]["coverage"]["reused"]], ["src/app/limits.py"])
        c = cov(out)
        self.assertEqual((c.status, c.reasons), (O.COMPLETE, ()))

    def test_a_reused_item_whose_item_id_is_not_ocr_s_is_named(self):
        out = self.moved()
        out["manifest"]["coverage"]["reused"][0]["item_id"] = "0" * 64
        c = cov(out)
        self.assertEqual(c.status, O.INDETERMINATE)
        self.assertTrue(any("src/app/limits.py" in r and "item_id" in r for r in c.reasons), c.reasons)

    def test_a_manifest_without_a_reused_list_reads_it_as_empty(self):
        for name, f in {"absent": lambda m: m["coverage"].pop("reused"),
                        "null": lambda m: m["coverage"].__setitem__("reused", None)}.items():
            with self.subTest(name):
                c = cov(changed(f))
                self.assertEqual((c.status, c.reasons), (O.COMPLETE, ()))


class ATerminalStateOtherThanCompleteIsNotACompleteReview(unittest.TestCase):
    """Only `complete` — or `skipped` over a range with nothing required (a complete review of nothing) — passes
    without a reason, whatever else matches (exit 0, the pinned version, the frozen range, no failure). With nothing
    required the state still counts; `skipped` over a required path is not a review of it.
    Pins aisef2/app/review_ocr.py::coverage [48]."""

    @staticmethod
    def in_state(state) -> dict:
        def f(m):
            if state is GONE:
                del m["terminal_state"]
            else:
                m["terminal_state"] = state
        return changed(f)

    def test_with_nothing_required_a_state_that_is_not_complete_is_named(self):
        for state in ("partial", "failed", "bogus", GONE):
            with self.subTest(state=state):
                c = cov(self.in_state(state), required=[])
                self.assertEqual(c.status, O.INDETERMINATE)
                if state is not GONE:                    # a manifest without a state has none to name
                    self.assertIn(state, tokens(c))

    def test_skipped_over_nothing_is_a_complete_review_of_nothing(self):
        c = cov(self.in_state("skipped"), required=[])
        self.assertEqual((c.status, c.reasons), (O.COMPLETE, ()))

    def test_skipped_over_a_required_path_is_not_a_review(self):
        c = cov(self.in_state("skipped"), required=REQUIRED)
        self.assertEqual(c.status, O.INDETERMINATE)
        self.assertIn("skipped", tokens(c))


class OnlyOcrsOwnFailureWarningsMakeAReviewIncomplete(unittest.TestCase):
    """OCR's `manifest_error` warning (the manifest could not be written or validated) makes a run INDETERMINATE
    (docs/v2.1/research/UPSTREAM-RESEARCH.json, adapter_contract_corrections 9); the warnings that only say a comment
    was repaired or re-filed do not. Pins aisef2/app/review_ocr.py::coverage [67] [96] [115]."""

    @staticmethod
    def warned(kind: str) -> dict:
        out = copy.deepcopy(A)
        out["warnings"] = [{"type": kind, "message": "from ocr", "file": "src/app/limits.py"}]
        return out

    def test_a_manifest_error_warning(self):
        c = cov(self.warned("manifest_error"))
        self.assertEqual(c.status, O.INDETERMINATE)
        self.assertIn("manifest_error", tokens(c))

    def test_a_warning_that_only_reports_a_repaired_comment_is_not_a_gap(self):
        for kind in ("comment_refiled", "comment_args_repaired"):
            with self.subTest(kind):
                c = cov(self.warned(kind))
                self.assertEqual((c.status, c.reasons), (O.COMPLETE, ()))


class AReasonCarriesTheValuesAReaderNeeds(unittest.TestCase):
    """A reason reaches the journal, the record's sessions[].coverage and the developer's retry prompt. It must say
    which two commits (or schemas) disagree, which classification OCR gave and what it said, which warning and its
    message: each value a whole token, none fused with its neighbour or replaced by None, and the commit OCR
    reviewed named before the commit it is compared with. The verdict is not what is pinned here. Pins
    aisef2/app/review_ocr.py::coverage [78] [80] [84] [98] [118] [130] [131] [132] [134] [135] [136]."""

    def test_the_reviewed_head_and_the_candidate_head_are_two_commits(self):
        reviewed, candidate = "abcdef012345" + "0" * 28, "123456789abc" + "0" * 28
        c = cov(changed(lambda m: m["input"].__setitem__("resolved_head", reviewed)), head=candidate)
        self.assertEqual(c.status, O.INDETERMINATE)
        at_reviewed, at_candidate = mention(c, reviewed), mention(c, candidate)
        self.assertIsNotNone(at_reviewed, c.reasons)
        self.assertIsNotNone(at_candidate, c.reasons)
        self.assertLess(at_reviewed, at_candidate)       # which is which: the commit OCR reviewed, then the candidate
        c = cov(changed(lambda m: m["input"].pop("resolved_head")), head=candidate)
        self.assertEqual(c.status, O.INDETERMINATE)      # a run that names no head is not a review of this one
        self.assertIsNotNone(mention(c, candidate), c.reasons)

    def test_the_reviewed_base_and_the_frozen_base_are_two_commits(self):
        reviewed, frozen = "0a1b2c3d4e5f" + "0" * 28, "f9e8d7c6b5a4" + "0" * 28
        c = cov(changed(lambda m: m["input"].__setitem__("resolved_base", reviewed)), base=frozen)
        self.assertEqual(c.status, O.INDETERMINATE)
        at_reviewed, at_frozen = mention(c, reviewed), mention(c, frozen)
        self.assertIsNotNone(at_reviewed, c.reasons)
        self.assertIsNotNone(at_frozen, c.reasons)
        self.assertLess(at_reviewed, at_frozen)          # which is which: the base OCR used, then the frozen one
        c = cov(changed(lambda m: m["input"].pop("resolved_base")), base=frozen)
        self.assertEqual(c.status, O.INDETERMINATE)
        self.assertIsNotNone(mention(c, frozen), c.reasons)

    def test_a_run_failure_names_its_classification_and_what_ocr_said(self):
        # OCR's words do not repeat the classification, so `provider` is a token only when it stands on its own
        out = changed(lambda m: m.__setitem__("run_failure", {"classification": "provider",
                                                              "reason": "HTTP 503 from upstream gateway"}))
        c = cov(out, code=1)
        self.assertEqual(c.status, O.INDETERMINATE)
        self.assertLessEqual({"provider", "HTTP", "503", "upstream", "gateway"}, tokens(c))

    def test_a_warning_names_its_type_and_carries_ocr_s_message(self):
        out = copy.deepcopy(A)
        out["warnings"] = [{"type": "token_budget_reached", "file": "cmd/tool/main.go",
                            "message": "stopped dispatch: projected 136000 exceeds budget 130000"}]
        c = cov(out)
        self.assertEqual(c.status, O.INDETERMINATE)
        self.assertLessEqual({"token_budget_reached", "projected", "136000", "130000"}, tokens(c))

    def test_an_unsupported_schema_names_what_was_found_and_what_is_required(self):
        found_none = cov(changed(lambda m: m.pop("schema_version")))
        self.assertEqual(found_none.status, O.INDETERMINATE)
        # an absent value is not quoted: only the reason's own separator keeps the required schema a whole token
        self.assertIn(O.MANIFEST_SCHEMA, tokens(found_none))
        found_v2 = cov(changed(lambda m: m.__setitem__("schema_version", "ocr.run-manifest/v2")))
        self.assertEqual(found_v2.status, O.INDETERMINATE)
        self.assertLessEqual({"ocr.run-manifest/v2", O.MANIFEST_SCHEMA}, tokens(found_v2))


class AFinderMaySkipOnlyWhatItCannotRead(unittest.TestCase):
    """Module docstring, 'What a finder may skip': a required path the preview excludes (will_review false) as
    `unsupported_ext` or `binary` is one this finder cannot read — named in not_reviewable, not counted against the
    coverage; any other exclusion is a gap, and a path the preview says WILL be reviewed is never exempted, whatever
    else its row carries. Pins aisef2/app/review_ocr.py::coverage [104] [126] [127]."""

    @staticmethod
    def preview(*rows: dict) -> dict:
        return {"files": [*PREVIEW["files"], *rows]}

    def test_unsupported_ext_and_binary_paths_are_named_and_not_counted(self):
        logo = {"path": "assets/logo.png", "status": "added", "will_review": False, "exclude_reason": "binary"}
        c = cov(required=[*REQUIRED, "docs/limits.md", "assets/logo.png"], preview=self.preview(logo))
        self.assertEqual((c.status, c.reasons), (O.COMPLETE, ()))
        self.assertEqual(sorted(c.not_reviewable), ["assets/logo.png", "docs/limits.md"])   # their order: class above

    def test_any_other_exclusion_of_a_required_path_is_a_gap(self):
        for why in ("too_large", "secret_exclude", "provider_directory", "user_exclude", "default_path"):
            with self.subTest(why):
                row = {"path": "src/app/x.py", "status": "modified", "will_review": False, "exclude_reason": why}
                c = cov(required=[*REQUIRED, "src/app/x.py"], preview=self.preview(row))
                self.assertEqual((c.status, c.not_reviewable), (O.INDETERMINATE, ()))
                self.assertIn("src/app/x.py", tokens(c))

    def test_a_path_the_preview_says_will_be_reviewed_is_not_exempted(self):
        row = {"path": "src/app/new.py", "status": "added", "will_review": True, "exclude_reason": "unsupported_ext"}
        c = cov(required=[*REQUIRED, "src/app/new.py"], preview=self.preview(row))
        self.assertEqual((c.status, c.not_reviewable), (O.INDETERMINATE, ()))
        self.assertIn("src/app/new.py", tokens(c))


class AnItemIdIsDerivedFromTheOldAndTheNewPath(unittest.TestCase):
    """OCR derives an item's id from the old and the new path (a renamed file's differ). A completed item carrying
    old_path is accepted under that id and refused under the one derived from (new, new). Pins
    aisef2/app/review_ocr.py::coverage [122]."""

    OLD, NEW = "src/app/old_name.py", "src/app/limits.py"

    def renamed(self, derived_from: tuple[str, str]) -> dict:
        def f(m):
            first = m["coverage"]["completed"][0]
            self.assertEqual(first["path"], self.NEW)
            first["old_path"], first["item_id"] = self.OLD, item_id("range", *derived_from)
        return changed(f)

    def test_the_rename_vector_differs_from_the_plain_one(self):
        self.assertNotEqual(item_id("range", self.OLD, self.NEW), item_id("range", self.NEW, self.NEW))

    def test_an_item_under_the_id_derived_from_its_old_and_new_path_is_accepted(self):
        c = cov(self.renamed((self.OLD, self.NEW)))
        self.assertEqual((c.status, c.reasons), (O.COMPLETE, ()))

    def test_an_item_with_an_old_path_under_the_id_of_its_new_path_alone_is_refused(self):
        c = cov(self.renamed((self.NEW, self.NEW)))
        self.assertEqual(c.status, O.INDETERMINATE)
        self.assertTrue(any(self.NEW in r and "item_id" in r for r in c.reasons), c.reasons)


class TheItemsOcrFailedAreTheVerdictsOwn(unittest.TestCase):
    """Coverage.failed is the manifest's failed items with the classification OCR gave each: the adapter decides
    whose an incomplete review is from them (the provider's outage, or the capability's failure). Pins
    aisef2/app/review_ocr.py::coverage [70] [119]."""

    def test_the_failed_items_and_their_classification_are_in_the_verdict(self):
        c = cov(B, required=["pkg/store/db.go", "pkg/store/cache.go"], base="3" * 40, head="4" * 40)
        self.assertEqual(c.status, O.INDETERMINATE)
        want = B["manifest"]["coverage"]["failed"]
        self.assertEqual(c.failed, tuple(want))
        self.assertEqual({i["path"]: i["classification"] for i in c.failed},
                         {"pkg/store/cache.go": "provider", "cmd/tool/main.go": "budget"})


OCR_SCRIPT = r'''import json, pathlib, sys
argv = sys.argv[1:]
if argv == ["version"]:      # the identity gate asks before any review command
    print("open-code-review v1.12.12 (182898c) darwin/arm64")
    raise SystemExit(0)
doc = json.loads(pathlib.Path(__file__).with_name("scenario.json").read_text(encoding="utf-8"))
out = pathlib.Path(argv[argv.index("--output") + 1])
if "--preview" in argv:
    out.write_text(json.dumps({"files": doc["preview"]}), encoding="utf-8")
    raise SystemExit(0)
out.write_text(json.dumps(doc["output"]), encoding="utf-8")
raise SystemExit(doc["exit"])
'''


class _Budget:
    """No ceiling is near: the adapter reads the room left and whether the run must stop."""
    limits = {"input_tokens": 10 ** 6, "output_tokens": 10 ** 6}

    def reached(self, live=None, in_progress=False):
        return None

    def spend(self, live=None):
        return {"input_tokens": 0, "output_tokens": 0}


@unittest.skipUnless(os.name == "posix", "the finder is a script started by its shebang")
class WhoOwnsAnIncompleteReview(unittest.TestCase):
    """Reviewer._ocr over a scripted finder whose run exits 0 with a manifest in state `failed`, no run_failure and
    failed items: when every failed item is the provider's, the incomplete review is the provider's outage whatever
    the policy (raised before the policy is read); with one item that is not, it is the capability's failure under
    fix-loop and a recorded INDETERMINATE under advisory. Pins aisef2/app/review_ocr.py::coverage [70] [119]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        chain.git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "app").mkdir()
        (self.repo / "app" / "__init__.py").write_text("")
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "requirements.md").write_text(chain.REQUIREMENTS)
        chain.git(self.repo, "add", "-A")
        chain.git(self.repo, "commit", "-q", "-m", "baseline")
        self.base = chain.git(self.repo, "rev-parse", "HEAD")
        (self.repo / "app" / "cli.py").write_text(chain.FIXED)
        (self.repo / "app" / "util.py").write_text("VALUE = 1\n")
        chain.git(self.repo, "add", "-A")
        chain.git(self.repo, "commit", "-q", "-m", "candidate")
        self.head = chain.git(self.repo, "rev-parse", "HEAD")
        self.project = bundle.load(chain.cli_bundle(self.base))
        self.runs = 0

    def finder(self, classifications: dict[str, str]) -> pathlib.Path:
        """A finder that reviewed nothing: `classifications` maps each changed path to why its item failed."""
        self.runs += 1
        bin_ = self.tmp / f"bin{self.runs}"
        bin_.mkdir()
        items = [{"item_id": item_id("range", p, p), "path": p, "classification": c, "reason": f"{c} failure"}
                 for p, c in classifications.items()]
        manifest = {"schema_version": O.MANIFEST_SCHEMA, "operation": "review", "terminal_state": "failed",
                    "input": {"mode": "range", "resolved_base": self.base, "resolved_head": self.head},
                    "execution": {"ocr_version": O.OCR["version"]},
                    "coverage": {"selected": items, "completed": [], "reused": [], "failed": items, "waived": []}}
        output = {"status": "failed", "comments": [], "manifest": manifest, "tool_calls": {"failure_details": []},
                  "summary": {"input_tokens": 10, "output_tokens": 2}, "message": "review failed"}
        preview = [{"path": p, "status": "added", "will_review": True} for p in classifications]
        (bin_ / "scenario.json").write_text(json.dumps({"exit": 0, "output": output, "preview": preview}), encoding="utf-8")
        exe = bin_ / "ocr"
        exe.write_text(f"#!{sys.executable}\n" + OCR_SCRIPT, encoding="utf-8")
        exe.chmod(0o755)
        return exe

    def review(self, exe: pathlib.Path, policy: str):
        run = SimpleNamespace(events=[SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": self.base})])
        pin = {"exe": str(exe), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "timeout_min": 1, "max_tokens": 1000}
        review = {"policy": policy, "min_severity": "high", "finder": "ocr", "ocr": pin}
        reviewer = ad.Reviewer(run, self.project, self.tmp / f"run{self.runs}" / "logs", {"budget": _Budget()}, 60.0,
                               review=review, route={"url": "http://127.0.0.1:9/v1", "token": "t", "model": "m"})
        scope = SimpleNamespace(story_id="S1", root=str(self.repo))
        return reviewer._ocr(scope, 0, self.head), reviewer

    def test_every_failed_item_the_providers_is_the_providers_outage_under_either_policy(self):
        for policy in ("fix-loop", "advisory"):
            with self.subTest(policy):
                exe = self.finder({"app/cli.py": "provider", "app/util.py": "provider"})
                with self.assertRaises(ProviderOutage):
                    self.review(exe, policy)

    def test_one_failed_item_that_is_not_the_providers_is_not_an_outage(self):
        exe = self.finder({"app/cli.py": "provider", "app/util.py": "budget"})
        with self.assertRaises(CapabilityUnrunnable):
            self.review(exe, "fix-loop")
        (found, session, note), reviewer = self.review(self.finder({"app/cli.py": "provider", "app/util.py": "budget"}),
                                                       "advisory")
        self.assertEqual((found, session["coverage"]["status"]), ([], O.INDETERMINATE))
        self.assertIn(O.INDETERMINATE, note)


class ARepeatedCommentIsOneFinding(unittest.TestCase):
    """OCR reviews a group once per round and the same comment can come back: a comment repeated word for word (the
    same fingerprint and the same content) is one finding — one id, one probe run, one journal row — and a comment
    at the same place that says something else takes the next occurrence index, whatever the input order, and the same
    words at another place are another finding (the repeat is judged on the pair, not on either half). Pins
    aisef2/app/review_ocr.py::findings [14] [15] [16] [17]."""

    C = A["comments"][0]
    OTHER = dict(C, content="the same place, said differently")

    def ids(self, comments: list[dict]) -> list[str]:
        return [f["id"] for f in O.findings({**A, "comments": comments}, REQUIRED)]

    def test_a_word_for_word_repeat_is_one_finding(self):
        want = f"ocr-{O.finding_id(self.C)[:12]}-0"
        self.assertEqual(self.ids([self.C, dict(self.C)]), [want])
        self.assertEqual(self.ids([self.C, dict(self.C), dict(self.C)]), [want])

    def test_the_same_words_at_another_place_are_another_finding(self):
        elsewhere = dict(self.C, path="src/app/api.py", existing_code="    return limit")
        found = O.findings({**A, "comments": [dict(self.C), dict(elsewhere)]}, REQUIRED)
        self.assertEqual(sorted(f["id"] for f in found),
                         sorted([f"ocr-{O.finding_id(self.C)[:12]}-0", f"ocr-{O.finding_id(elsewhere)[:12]}-0"]))
        self.assertEqual(sorted(f["path"] for f in found), ["src/app/api.py", "src/app/limits.py"])

    def test_another_content_at_the_same_place_is_the_next_occurrence_in_any_input_order(self):
        fid = O.finding_id(self.C)[:12]
        want = {f"ocr-{fid}-0": self.C["content"], f"ocr-{fid}-1": self.OTHER["content"]}
        for order in ([self.C, self.C, self.OTHER], [self.OTHER, self.C, self.C], [self.C, self.OTHER, self.C]):
            with self.subTest(order=[c["content"][:8] for c in order]):
                found = O.findings({**A, "comments": [dict(c) for c in order]}, REQUIRED)
                self.assertEqual({f["id"]: f["summary"] for f in found}, want)
                self.assertEqual(len(found), 2)


if __name__ == "__main__":
    unittest.main()
