"""V2.1 (owner B-03, kills round 3, batch T12b): kill tests for survivors of aisef2/app/review_ocr.py's targets
`argv`, `finding_id`, `item_id`, `pinned` and `reproducer_of`. Each class states the requirement and what it pins.

The command line is the one thing the controller hands to the external finder: a flag that loses its value (or gains a
stray token) is read as another setting, so the line is parsed strictly here, the way a flag library reads it, instead
of being searched for substrings (a membership check cannot see a flag that swallowed its neighbour)."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_ocr as O  # noqa: E402

FIX = ROOT / "tests/v2/fixtures/ocr"
COMPLETE = json.loads((FIX / "complete.json").read_text(encoding="utf-8"))
BASE, HEAD = "1" * 40, "2" * 40
REQUIRED = ["src/app/api.py", "src/app/limits.py"]
#: the flags of `ocr review` that take no value (UPSTREAM-RESEARCH.json: --no-filter, -p/--preview)
VALUELESS = ("--no-filter", "--preview")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_line(line: list[str]) -> tuple[dict[str, str], list[str]]:
    """The tokens after [exe, 'review'] read as a flag library reads them: every token is a `--flag` (or `--flag=value`),
    a flag but the valueless ones takes exactly the next token (which is not itself a flag), no flag twice. Anything
    else — a stray token, a flag at the end, a flag that took a flag — is not a command line OCR reads as intended."""
    if line[1] != "review":
        raise AssertionError(f"not an `ocr review` line: {line[:3]}")
    pairs: dict[str, str] = {}
    bare: list[str] = []
    tokens = iter(line[2:])
    for tok in tokens:
        if not tok.startswith("--"):
            raise AssertionError(f"stray token {tok!r} where a flag belongs: {line}")
        if tok in VALUELESS:
            bare.append(tok)
            continue
        tok, joined, value = tok.partition("=")            # the `--flag=value` spelling is the same setting
        if not joined:
            value = next(tokens, None)
        if value is None or value.startswith("--"):
            raise AssertionError(f"flag {tok} has no value (next: {value!r}): {line}")
        if tok in pairs:
            raise AssertionError(f"flag {tok} given twice: {line}")
        pairs[tok] = value
    return pairs, bare


class ReviewLine(unittest.TestCase):
    """argv (non-preview) — every element of the review-only part of the line, flag names and values: `--audience agent`,
    `--model`, `--effort high`, `--max-tokens`, `--max-tokens-budget`, `--concurrency 1`, `--timeout`, `--no-filter`,
    `--background-file`. Pins aisef2/app/review_ocr.py::argv [26-39, 41-52, 54]. The values are distinct on purpose: a
    number carried by the wrong flag, or a flag that took its neighbour's value, changes the mapping."""

    def line(self) -> list[str]:
        return O.argv("/opt/ocr", repo="/r", base=BASE, head=HEAD, rule="/c/rule.json", output="/c/out.json",
                      model="route-model-7", max_tokens=8123, budget_tokens=204567, timeout_min=17,
                      background_file="/c/bg.txt")

    def test_every_flag_is_followed_by_exactly_its_value(self):
        pairs, bare = parse_line(self.line())
        self.assertEqual(len(pairs), 14)
        self.assertEqual(bare, ["--no-filter"])

    def test_the_operator_s_limits_and_the_route_reach_the_flags_that_name_them(self):
        pairs, _ = parse_line(self.line())
        self.assertEqual(pairs["--model"], "route-model-7")                 # the run's one fixed route model
        self.assertEqual(pairs["--max-tokens"], "8123")                     # review.ocr.max_tokens
        self.assertEqual(pairs["--max-tokens-budget"], "204567")            # the room the run has left
        self.assertEqual(pairs["--timeout"], "17")                          # review.ocr.timeout_min, minutes per group
        self.assertEqual(pairs["--background-file"], "/c/bg.txt")           # the clauses and the reproducer request

    def test_the_controller_s_fixed_choices_are_set_not_left_to_ocr_s_defaults(self):
        pairs, bare = parse_line(self.line())
        self.assertEqual(pairs["--audience"], "agent")
        self.assertEqual(pairs["--effort"], "high")        # OCR's own default is medium: two review rounds, not three
        self.assertEqual(pairs["--concurrency"], "1")      # one group at a time: usage is known before each dispatch
        self.assertEqual(bare, ["--no-filter"])            # the LLM review filter drops comments without a record


class FindingIdWithoutCategory(unittest.TestCase):
    """finding_id / findings — a comment with no category (absent, None or '') is fingerprinted as category 'other',
    exactly as the one that says 'other' (OCR's SARIF derivation `category or other`, cmd/opencodereview/sarif.go; the
    adapter contract in UPSTREAM-RESEARCH.json). The id names the finding in the journal gate check `review:ocr-<12
    hex>-<n>` and in the session's finding record, so it is a known-answer value. Pins
    aisef2/app/review_ocr.py::finding_id [2]."""

    COMMENT = {"path": "p.py", "existing_code": " x ", "start_line": 3}

    def test_the_id_of_a_comment_without_a_category_is_the_fingerprint_with_other(self):
        want = sha("p.py|other|x")
        for name, comment in {"absent": self.COMMENT, "empty": dict(self.COMMENT, category=""),
                              "none": dict(self.COMMENT, category=None),
                              "other": dict(self.COMMENT, category="other")}.items():
            with self.subTest(name):
                self.assertEqual(O.finding_id(comment), want)
        self.assertNotEqual(O.finding_id(dict(self.COMMENT, category="bug")), want)    # the category is in the hash

    def test_the_finding_carries_that_id_and_reports_the_category_other(self):
        out = O.findings({"comments": [dict(self.COMMENT, content="no category here")]}, ["p.py"])
        self.assertEqual([(f["id"], f["category"]) for f in out], [(f"ocr-{sha('p.py|other|x')[:12]}-0", "other")])


class ItemIdSeparators(unittest.TestCase):
    """item_id — a path separator is normalised, never deleted: a Windows spelling of a path (backslashes) is the same
    manifest item as its slash spelling, and a path with separators never gets the id of the same characters without
    them (a file `srcappapi.py` is another file). Pins aisef2/app/review_ocr.py::item_id [6]."""

    def test_a_separator_is_never_dropped_from_the_hashed_path(self):
        # unconditional: whatever the normal form is, 'src/app/api.py' and 'srcappapi.py' are not one item
        self.assertNotEqual(O.item_id("range", "src\\app\\api.py", "src\\app\\api.py"),
                            O.item_id("range", "srcappapi.py", "srcappapi.py"))

    def test_a_manifest_row_spelled_with_backslashes_is_the_item_ocr_derived(self):
        # AISEF's own normalisation (the module reads a backslash as a separator, for its Windows side): the row's
        # item_id is OCR's, recomputed by the research from the slash spelling, so coverage must accept it
        out = copy.deepcopy(COMPLETE)
        for item in out["manifest"]["coverage"]["completed"]:
            item["path"] = item["path"].replace("/", "\\")
        required = [p.replace("/", "\\") for p in REQUIRED]
        c = O.coverage(out, 0, required=required, base=BASE, head=HEAD)
        self.assertEqual((c.status, c.reasons), (O.COMPLETE, ()))
        api = next(i for i in COMPLETE["manifest"]["coverage"]["completed"] if i["path"] == "src/app/api.py")
        self.assertEqual(O.item_id("range", "src\\app\\api.py", "src\\app\\api.py"), api["item_id"])


class PinnedRefusals(unittest.TestCase):
    """pinned — the binary may run only when its bytes are readable and are the pinned ones: an absolute path that
    cannot be read is refused (fail closed, not 'may run'), and every refusal names the binary with the path set off
    from what follows (house style `<path>: <reason>`, as bundle.read and settings.read refuse a file; the test asks
    for the path to be recoverable, not for a delimiter), the unreadable one naming the kind (cannot be read) and the
    exception class, the mismatch the observed and the pinned digest prefixes. The reason is what the operator reads in
    the journal's `reviewer cannot run: ...` result. Pins aisef2/app/review_ocr.py::pinned [5, 8, 10]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name)

    def assertNamesThePath(self, why: str, exe: str) -> None:
        """The reason names the refused binary and sets it off from what follows (the operator reads
        `reviewer cannot run: <why>`): the character after the path does not continue a file name."""
        self.assertIn(exe, why)
        after = why[why.index(exe) + len(exe):][:1]
        self.assertFalse(after.isalnum(), why)

    def test_an_absent_binary_is_refused_naming_the_path_the_kind_and_the_exception(self):
        exe = str(self.tmp / "absent-ocr")
        why = O.pinned(exe, "0" * 64)
        self.assertIsNotNone(why)
        self.assertNamesThePath(why, exe)
        self.assertIn("cannot be read", why)
        self.assertIn("FileNotFoundError", why)

    def test_a_path_that_is_a_directory_is_refused_not_run(self):
        exe = str(self.tmp)                      # an OSError on every platform (IsADirectoryError / PermissionError)
        why = O.pinned(exe, "0" * 64)
        self.assertIsNotNone(why)
        self.assertNamesThePath(why, exe)
        self.assertIn("cannot be read", why)

    def test_other_bytes_are_refused_with_the_observed_and_the_pinned_digest_told_apart(self):
        exe = self.tmp / "ocr"
        exe.write_bytes(b"binary")
        have, pin = hashlib.sha256(b"binary").hexdigest(), "0" * 64
        why = O.pinned(str(exe), pin)
        self.assertIsNotNone(why)
        self.assertNamesThePath(why, str(exe))
        observed, _, pinned = why[why.index(str(exe)) + len(str(exe)):].partition("not the pinned")
        self.assertIn(have[:12], observed)
        self.assertNotIn(have[:12], pinned)
        self.assertIn(pin[:12], pinned)
        self.assertNotIn("cannot be read", why)


class ReproducerOfAMalformedBlock(unittest.TestCase):
    """reproducer_of / findings — a fenced aisef-reproducer block that is object-shaped but is not JSON (a trailing
    comma, single quotes, a comment: what a model writes, or an injected diff) is kept as text and carries nothing:
    reproducer_of returns (None, the whole content), and findings() returns that comment as one non-blocking finding
    with no reproducer and its text in the summary. It must not raise: Reviewer._ocr calls it unguarded, so an
    exception ends the review stage after a PROVIDER_REQUEST that never gets a result. Pins
    aisef2/app/review_ocr.py::reproducer_of [8, 9, 10]."""

    BODIES = {"trailing comma": '{"clause": "R-X/1.1",}',
              "single quotes": "{'clause': 'R-X/1.1'}",
              "a comment": '{"clause": "R-X/1.1" // the clause\n}'}

    @staticmethod
    def comment(body: str) -> str:
        return f"The sum is wrong for R-X/1.1.\n```aisef-reproducer\n{body}\n```"

    def test_a_block_that_does_not_parse_is_the_comment_unchanged_and_carries_nothing(self):
        for name, body in self.BODIES.items():
            with self.subTest(name):
                content = self.comment(body)
                self.assertEqual(O.reproducer_of(content), (None, content))

    def test_findings_reports_it_as_one_finding_without_a_reproducer_that_never_blocks(self):
        for name, body in self.BODIES.items():
            with self.subTest(name):
                content = self.comment(body)
                got = O.findings({"comments": [{"path": "a.py", "content": content, "category": "bug",
                                                "severity": "high", "existing_code": "x", "start_line": 1}]}, ["a.py"])
                self.assertEqual(len(got), 1)
                self.assertNotIn("reproducer", got[0])
                self.assertIs(got[0]["blocking"], False)
                self.assertIn("The sum is wrong for R-X/1.1.", got[0]["summary"])   # the comment's text is kept

    def test_a_well_formed_block_is_the_control(self):
        content = self.comment('{"clause": "R-X/1.1"}')
        self.assertEqual(O.reproducer_of(content), ({"clause": "R-X/1.1"}, "The sum is wrong for R-X/1.1."))


if __name__ == "__main__":
    unittest.main()
