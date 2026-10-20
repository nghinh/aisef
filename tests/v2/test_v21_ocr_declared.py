"""V2.1 (owner 2026-10-15, item 5, lane ocr-gate): the pure judgement of what the Open Code Review binary says it is —
`review_ocr.declared` over `<exe> version`'s exit status and output, and the command and environment it is asked in.

No process is started here (test_v21_ocr_gate.py asks real ones, through the review stage and `aisef run`). The table
below is shared with it: each way a binary can answer, and the words a refusal of that answer must carry.

The answer is the binary's own word — a self-declaration. The sha256 is the identity of the bytes; neither says how they
were built (validation/v21/ocr/BUILD-RECIPE.md)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_ocr  # noqa: E402

PINNED_LINE = "open-code-review v1.12.12 (182898c) darwin/arm64"
REAL = f"{PINNED_LINE}\nbuilt at: 2026-10-05T00:00:00Z\nhttps://github.com/alibaba/open-code-review\n"

#: what the version question is answered with, per kind of binary: (text printed, exit status, seconds it sleeps first)
ANSWERS = {
    "pinned": (REAL, 0, 0),
    "another version": ("open-code-review v1.11.0 (182898c) darwin/arm64\n", 0, 0),
    "another commit": ("open-code-review v1.12.12 (deadbee) darwin/arm64\n", 0, 0),
    "a dev build": ("open-code-review dev (none) darwin/arm64\n", 0, 0),
    "no version command": ("", 0, 0),
    "a banner first": ("Welcome to ocr\n" + REAL, 0, 0),
    "garbage": ("\x00\x01 segmentation noise \xff\n{not a version}\n", 0, 0),
    "the right line, a failing exit": (REAL, 3, 0),
    "never answers": ("", 0, 30),
}
#: the answers that are not the pinned one, and a word each refusal must carry
REFUSED = {
    "another version": ("v1.11.0", "v1.12.12", "182898c"),
    "another commit": ("deadbee", "v1.12.12", "182898c"),
    "a dev build": ("dev", "v1.12.12", "182898c"),
    "no version command": ("no version line",),
    "a banner first": ("no version line", "Welcome"),
    "garbage": ("no version line",),
    "the right line, a failing exit": ("exited 3",),
    "never answers": ("did not answer in time",),
}


class Declared(unittest.TestCase):
    """`review_ocr.declared`: the pure judgement of `version`'s exit status and output."""

    def test_the_question_has_its_own_short_bound(self):
        self.assertEqual(review_ocr.VERSION_TIMEOUT_S, 15.0)     # a build answers at once; a hung one is not it

    def test_the_pinned_build_s_own_output_is_accepted_and_read_into_fields(self):
        seen, why = review_ocr.declared("/x/ocr", 0, REAL)
        self.assertIsNone(why)
        self.assertEqual(seen, {"version": "v1.12.12", "commit": "182898c", "platform": "darwin/arm64", "line": PINNED_LINE})

    def test_the_commit_may_be_printed_short_or_whole_and_must_be_the_pinned_one(self):
        pinned = review_ocr.OCR["commit"]
        for printed in (pinned[:7], pinned[:12], pinned):
            with self.subTest(printed=printed):
                self.assertIsNone(review_ocr.declared("/x/ocr", 0, f"open-code-review v1.12.12 ({printed}) linux/amd64\n")[1])
        for printed in (pinned[:6], "0" + pinned[1:7], pinned[:6] + "0", "182898X", pinned + "0"):
            with self.subTest(refused=printed):
                seen, why = review_ocr.declared("/x/ocr", 0, f"open-code-review v1.12.12 ({printed}) linux/amd64\n")
                self.assertIsNotNone(why)
                self.assertEqual(seen["commit"], printed)       # what it said is kept, to be named

    def test_every_answer_that_is_not_the_pinned_build_is_refused_naming_what_was_seen_and_what_is_pinned(self):
        for name, words in REFUSED.items():
            text, code, sleep = ANSWERS[name]
            with self.subTest(name):
                seen, why = review_ocr.declared("/x/ocr", None if sleep else code, text)
                self.assertIsNotNone(why)
                for word in words:
                    self.assertIn(word, why)
                self.assertIn("/x/ocr", why)

    def test_a_mismatch_names_both_the_version_and_the_commit_of_each_side(self):
        _, why = review_ocr.declared("/x/ocr", 0, "open-code-review v1.13.0 (1234567) linux/arm64\n")
        for word in ("v1.13.0", "1234567", review_ocr.OCR["version"], review_ocr.OCR["commit"][:7]):
            self.assertIn(word, why)

    def test_only_the_first_line_is_a_version_line_and_blank_lines_before_it_are_skipped(self):
        self.assertIsNone(review_ocr.declared("/x/ocr", 0, "\n\n  " + REAL)[1])
        self.assertIsNotNone(review_ocr.declared("/x/ocr", 0, "x\n" + REAL)[1])       # a version line that is not first
        self.assertIsNotNone(review_ocr.declared("/x/ocr", 0, PINNED_LINE + " and more\n")[1])   # not the whole line

    def test_only_a_newline_ends_the_line_and_what_follows_any_other_break_is_part_of_it(self):
        # str.splitlines() also breaks at \v \f \x1c-\x1e \x85 \u2028 \u2029: what follows such a break is then never read,
        # and a physical line longer than the version line was accepted as the version line
        for brk in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"):
            with self.subTest(brk=repr(brk)):
                _, why = review_ocr.declared("/x/ocr", 0, f"{PINNED_LINE}{brk}ANYTHING FOLLOWS\n{REAL}")
                self.assertIsNotNone(why)
                self.assertIn("no version line", why)
        self.assertIsNone(review_ocr.declared("/x/ocr", 0, PINNED_LINE + "\r\nbuilt at: x\r\n")[1])   # CRLF is a newline

    def test_a_long_garbage_line_is_cut_in_the_refusal(self):
        _, why = review_ocr.declared("/x/ocr", 0, "z" * 5000 + "\n")
        self.assertLess(len(why), 400)

    def test_whatever_a_binary_says_is_cut_where_it_is_named_and_where_it_is_recorded(self):
        for what, line in (("a version", "open-code-review " + "v" * 3000 + " (182898c) darwin/arm64"),
                           ("a commit", "open-code-review v1.12.12 (" + "c" * 3000 + ") darwin/arm64")):
            with self.subTest(what):
                seen, why = review_ocr.declared("/x/ocr", 0, line + "\n")
                self.assertIsNotNone(why)
                self.assertLess(len(why), 400)          # the refusal goes to the journal as written
        seen, why = review_ocr.declared("/x/ocr", 0, "open-code-review v1.12.12 (182898c) " + "p" * 3000 + "\n")
        self.assertIsNone(why)                          # the platform is not compared: it is recorded, and bounded
        self.assertLessEqual(len(seen["platform"]), 40)
        self.assertLessEqual(len(seen["line"]), 200)

    def test_the_command_is_version_alone_and_its_environment_inherits_nothing(self):
        self.assertEqual(review_ocr.version_argv("/opt/ocr"), ["/opt/ocr", "version"])
        base = {"PATH": "/home/me/bin", "HOME": "/home/me", "OCR_LLM_TOKEN": "t", "ANTHROPIC_API_KEY": "k",
                "AISEF_ANYTHING": "v", "XDG_CONFIG_HOME": "/home/me/.config"}
        env = review_ocr.version_environment("/iso", base)
        self.assertEqual(env, {"PATH": "/usr/bin:/bin", "HOME": "/iso", "USERPROFILE": "/iso", "OCR_NO_UPDATE": "1"})
        self.assertEqual(review_ocr.version_environment("/iso", {"SYSTEMROOT": r"C:\Windows"}),
                         env | {"SYSTEMROOT": r"C:\Windows"})    # the one variable a Windows process cannot start without

    def test_a_version_or_commit_mismatch_reads_as_the_binary_declaring_itself_not_the_pin(self):
        # the whole mismatch sentence, not just the values: run.ocr_identity and the operator text
        # (DECLARED_WAYS in test_v21_ocr_identity) tell this failure apart from the others by the marker
        # "declares itself"; the exe, what it said, and the pin must each be named and not run together
        _, why = review_ocr.declared("/x/ocr", 0, "open-code-review v1.11.0 (182898c) darwin/arm64\n")
        self.assertEqual(
            why,
            "/x/ocr: declares itself v1.11.0 (182898c), not the pinned v1.12.12 (182898c): no review command was run",
        )
        self.assertIn("declares itself", why)   # the marker the operator report classifies on


if __name__ == "__main__":
    unittest.main()
