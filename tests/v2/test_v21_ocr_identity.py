"""V2.1 (owner 2026-10-15, item 5, second paragraph; lane ocr-preflight): what `aisef run` knows of the Open Code Review
binary before it starts anything — `run.ocr_identity` and `run.ocr_refusal` — and `aisef run` / `aisef run --check`, the
commands that report it.

Function level, over a scripted binary (test_v21_review_chain.FAKE_OCR, pinned by sha256 like the real one) and the table
of answers of test_v21_ocr_declared: a few seconds, so it is the kill file of those two functions and of the check branch
of `cli.run`. The run itself — nothing started or sent before the refusal, the record, the ordering before the first
provider request and the claim on a predecessor, the binary replaced after the preflight — is test_v21_ocr_preflight.py
(about a minute: it makes a whole run each time).

What is established, and what is not: `levels.sha256_matches_pin` (the bytes are the operator's pin) and
`levels.declared_matches_release` (the binary's own `version` line names the pinned release and commit: a
self-declaration); `levels.build_provenance` is "NOT_ESTABLISHED" — never established by a run, and said so rather than
left as a bare false. Nothing here says "verified build".

The operator text of each refusal is tested against what the code can say: it is true of every way the check can fail
(the first review of this lane found one sentence that was false of four of the five), and the remedy it offers is one
the settings loader accepts."""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import cli, preflight, review_ocr, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2.test_v21_ocr_declared import ANSWERS, REFUSED  # noqa: E402
from tests.v2.test_v21_review_chain import FAKE_OCR  # noqa: E402

POSIX = unittest.skipUnless(os.name == "posix", "the fake finder is a script started by its shebang")
PROVENANCE = "NOT_ESTABLISHED"
NOT_ESTABLISHED = {"sha256_matches_pin": False, "declared_matches_release": False, "build_provenance": PROVENANCE}
#: a failure's reason carries one of these words; the operator text of the declared check names it in its own words
DECLARED_WAYS = {"declares itself": "another release or commit", "exited": "an error", "did not answer in time":
                 "no answer in time", "printed no version line": "no version line", "could not be started": "could not be started"}


@POSIX
class Identity(unittest.TestCase):
    """`run.ocr_identity(settings)` and `run.ocr_refusal(identity)`."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.bin = pathlib.Path(t.name).resolve()
        self.exe = self.bin / "ocr"
        self.exe.write_text(f"#!{sys.executable}\n" + FAKE_OCR, encoding="utf-8")
        self.exe.chmod(0o755)
        self.sha = hashlib.sha256(self.exe.read_bytes()).hexdigest()

    def settings(self, policy: str = "fix-loop", **pin) -> settings.Settings:
        """Settings the loader accepts, the pin then changed as `pin` says (what the loader would have refused too)."""
        s = settings.load({**e2e.SETTINGS, "review": {"policy": policy, "min_severity": "high", "finder": "ocr",
                                                      "ocr": {"exe": str(self.exe), "sha256": self.sha, "timeout_min": 1,
                                                              "max_tokens": 4000}}})
        return dataclasses.replace(s, review={**s.review, "ocr": {**s.review["ocr"], **pin}})

    def answer(self, name: str) -> None:
        text, code, sleep = ANSWERS[name]
        (self.bin / "identity.json").write_text(json.dumps({"text": text, "exit": code, "sleep": sleep}), encoding="utf-8")

    def asked(self) -> list[list[str]]:
        p = self.bin / "calls.jsonl"
        return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def test_a_review_that_is_not_open_code_review_has_no_binary_to_ask(self):
        absent = settings.load(e2e.SETTINGS)
        model = settings.load({**e2e.SETTINGS, "review": {"policy": "fix-loop", "min_severity": "high"}})
        named = settings.load({**e2e.SETTINGS, "review": {"policy": "advisory", "min_severity": "low", "finder": "model"}})
        with mock.patch.object(review_ocr, "pinned", side_effect=AssertionError("asked about a binary")), \
                mock.patch.object(ad, "_declared", side_effect=AssertionError("asked a binary")):
            self.assertEqual([R.ocr_identity(s) for s in (absent, model, named, object())], [None] * 4)

    def test_the_pinned_build_passes_and_the_record_names_each_level_it_does_and_does_not_establish(self):
        for policy in ("fix-loop", "advisory"):        # the policy decides what a finding does, not whether the binary is asked
            with self.subTest(policy):
                ident = R.ocr_identity(self.settings(policy))
                self.assertEqual(ident, {
                    "finder": "ocr", "exe": str(self.exe), "when": ident["when"], "statement": R.OCR_STATEMENT,
                    "status": "PASSED",
                    "levels": {"sha256_matches_pin": True, "declared_matches_release": True, "build_provenance": PROVENANCE},
                    "expected": {"sha256": self.sha, "version": "v1.12.12", "commit": review_ocr.OCR["commit"]},
                    "observed": {"asked": True,
                                 "declared": {"version": "v1.12.12", "commit": "182898c", "platform": "darwin/arm64",
                                              "line": "open-code-review v1.12.12 (182898c) darwin/arm64"}}})
                # true of `aisef run` and of `aisef run --check` alike: it names no run that has begun
                self.assertEqual(ident["when"], "before any session is opened or any provider request is sent")
        self.assertEqual(self.asked(), [["version"]] * 2, "the version question, once for each look, and nothing else")
        for words in ("self-declaration", "NOT_ESTABLISHED: never established by a run", "not the control",
                      "separate observations of the path", "not a proof that the bytes hashed are the bytes later started"):
            self.assertIn(words, R.OCR_STATEMENT)
        for forbidden in ("verified build", "built from source", "provenance established", "authentic"):
            self.assertNotIn(forbidden, json.dumps(ident))

    def test_every_answer_that_is_not_the_pinned_build_is_refused_at_the_declared_check(self):
        for name, words in REFUSED.items():
            with self.subTest(answer=name):
                self.answer(name)
                before = len(self.asked())
                with mock.patch.object(review_ocr, "VERSION_TIMEOUT_S", 2.0) if ANSWERS[name][2] else contextlib.nullcontext():
                    ident = R.ocr_identity(self.settings())
                self.assertEqual(self.asked()[before:], [["version"]])
                self.assertEqual((ident["status"], ident["levels"]),
                                 ("REFUSED", {**NOT_ESTABLISHED, "sha256_matches_pin": True}))
                self.assertTrue(ident["observed"]["asked"], "the question was put, whatever the answer")
                self.assertEqual(ident["check"], R.OCR_CHECKS["declared"][0])
                self.assertEqual(ident["operator"], R.OCR_CHECKS["declared"][1])
                self.assertEqual(ident["expected"], {"sha256": self.sha, "version": "v1.12.12",
                                                     "commit": review_ocr.OCR["commit"]})
                for word in words:
                    self.assertIn(word, ident["reason"])
                said = R.ocr_refusal(ident)
                for part in (ident["check"], f"expected sha256 {self.sha}", "naming v1.12.12 (182898c)",
                             f"observed {ident['reason']}", ident["operator"],
                             "No session was started and no provider request was sent."):
                    self.assertIn(part, said)

    def test_a_binary_that_declares_itself_otherwise_names_what_it_said(self):
        self.answer("another commit")
        ident = R.ocr_identity(self.settings())
        self.assertEqual({k: ident["observed"]["declared"][k] for k in ("version", "commit")},
                         {"version": "v1.12.12", "commit": "deadbee"})

    def test_every_way_the_pin_fails_is_refused_at_the_pinned_check_and_the_binary_is_never_started(self):
        directory = self.bin / "a-directory"
        directory.mkdir()
        cases = {"the bytes are not the pin": ({"sha256": "0" * 64}, "not the pinned"),
                 # the loader accepts any absolute string; the system cannot name these: a refusal, never a traceback
                 "a NUL byte in the path": ({"exe": str(self.bin) + "/o\x00cr"}, "cannot be read (ValueError)"),
                 "a lone surrogate in the path": ({"exe": str(self.bin) + "/ocr\ud800"},
                                                  "cannot be read (UnicodeEncodeError)"),
                 "a relative path": ({"exe": "ocr"}, "absolute path"),
                 "no path": ({"exe": ""}, "name no binary"), "no path at all": ({"exe": None}, "name no binary"),
                 "no pin": ({"sha256": ""}, "name no binary"), "a path that is not a file": (
                     {"exe": str(self.bin / "no-such-ocr")}, "cannot be read"),
                 "a directory": ({"exe": str(directory)}, "cannot be read")}
        for what, (pin, said) in cases.items():
            with self.subTest(what):
                ident = R.ocr_identity(self.settings(**pin))
                self.assertEqual((ident["status"], ident["levels"], ident["observed"]),
                                 ("REFUSED", NOT_ESTABLISHED, {"asked": False, "declared": None}))
                self.assertEqual((ident["check"], ident["operator"]), R.OCR_CHECKS["pinned"])
                self.assertIn(said, ident["reason"])
                self.assertIn(said, R.ocr_refusal(ident))
                self.assertIn("shasum -a 256", R.ocr_refusal(ident))
        self.assertEqual(self.asked(), [], "a binary that is not the pin is never started, not even for `version`")
        self.assertEqual(R.ocr_refusal(R.ocr_identity(self.settings(exe=""))).count("(none given)"), 0)
        self.assertIn("expected sha256 (none given)", R.ocr_refusal(R.ocr_identity(self.settings(sha256=""))))

    def test_each_check_says_what_it_is_and_what_the_operator_does(self):
        # the words an operator reads in a refusal (the tests above compare with these tables, never with themselves)
        self.assertEqual(set(R.OCR_CHECKS), {"pinned", "declared"})
        what, do = R.OCR_CHECKS["pinned"]
        self.assertTrue(what.startswith("pinned: review.ocr.exe is an absolute path, readable, and its sha256 is "))
        for word in ("review.ocr.exe", "review.ocr.sha256", "shasum -a 256", "python -c", "hashlib", "BUILD-RECIPE.md",
                     "Find out why before changing the pin", "Re-pin only a file you have checked",
                     'remove review.ocr and set review.finder to "model"', "a different reviewer",
                     "give it a new --out", "a run directory is never reused", "run again"):
            self.assertIn(word, do)
        self.assertNotIn("to that file's sha256", do, "an instruction to pin whatever sits at the path defeats the pin")
        what, do = R.OCR_CHECKS["declared"]
        self.assertTrue(what.startswith("declared: `<exe> version`") and what.endswith("prints the pinned release and commit"))
        for word in ("review.ocr.sha256", "v1.12.12", "182898c", "`<exe> version` yourself", 'review.finder to "model"',
                     "pin the sha256 of a build of Open Code Review v1.12.12 (182898c)", "give it a new --out", "run again"):
            self.assertIn(word, do)
        self.assertNotIn("its own `version` line is not", do, "false of every failure but a version line of another release")
        self.assertNotIn("pin the sha256 of a build of that release", do, "'that release' reads as the one the binary named")

    def test_the_declared_operator_text_is_true_of_every_way_the_check_fails(self):
        # the sentence that sat beside the observed value said the binary's `version` line was not the pinned one even
        # when no line was ever seen (could not be started, exited non-zero, no answer in time, no version line)
        do = R.OCR_CHECKS["declared"][1]
        for phrase in DECLARED_WAYS.values():
            self.assertIn(phrase, do)
        met = set()
        for name in REFUSED:
            self.answer(name)
            with mock.patch.object(review_ocr, "VERSION_TIMEOUT_S", 2.0) if ANSWERS[name][2] else contextlib.nullcontext():
                reason = R.ocr_identity(self.settings())["reason"]
            (marker,) = [m for m in DECLARED_WAYS if m in reason]
            met.add(marker)
        self.exe.chmod(0o644)       # readable, so the pin holds; not a program this machine can start
        reason = R.ocr_identity(self.settings())["reason"]
        self.assertIn("could not be started", reason)
        self.assertEqual(met | {"could not be started"}, set(DECLARED_WAYS), "every way the code can fail is one the text names")

    def test_a_binary_that_cannot_be_started_is_refused_at_the_declared_check_with_the_system_s_reason(self):
        # not the kernel's type name ("RangeError"): what the operating system said, so the operator can act on it
        self.exe.chmod(0o644)
        ident = R.ocr_identity(self.settings())
        self.assertEqual((ident["status"], ident["levels"], ident["observed"]),
                         ("REFUSED", {**NOT_ESTABLISHED, "sha256_matches_pin": True}, {"asked": True, "declared": None}))
        self.assertEqual(ident["check"], R.OCR_CHECKS["declared"][0])
        self.assertIn("`version` could not be started", ident["reason"])
        self.assertIn("Permission denied", ident["reason"])
        self.exe.chmod(0o755)
        self.exe.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")       # bytes that are the pin, re-pinned
        ident = R.ocr_identity(self.settings(sha256=hashlib.sha256(self.exe.read_bytes()).hexdigest()))
        self.assertEqual((ident["status"], ident["levels"]["sha256_matches_pin"]), ("REFUSED", True))
        self.assertIn("`version` could not be started", ident["reason"])
        self.assertIn("No such file", ident["reason"])
        self.assertEqual(self.asked(), [], "neither was ever running")
        self.assertIn(ident["reason"], R.ocr_refusal(ident))

    def test_the_hash_command_the_operator_text_gives_for_any_system_prints_the_files_sha256(self):
        # `shasum` is not on every system the project runs on; the other command is run as written (quoted as a shell
        # would hand it over: the program text between the double quotes)
        code = re.search(r'python -c "(.*)" <exe>', R.SHA256_OF).group(1)
        got = subprocess.run([sys.executable, "-I", "-c", code, str(self.exe)], capture_output=True, text=True,
                             encoding="utf-8", check=True)
        self.assertEqual(got.stdout.strip(), self.sha)
        self.assertIn("shasum -a 256 <exe>", R.SHA256_OF)

    def test_the_other_reviewer_the_operator_text_offers_is_one_the_loader_accepts(self):
        # "remove review.ocr and set review.finder to "model"" — and only that: the loader refuses a model finder that
        # still carries a review.ocr
        review = {"policy": "fix-loop", "min_severity": "high"}
        ocr = {"exe": str(self.exe), "sha256": self.sha, "timeout_min": 1, "max_tokens": 4000}
        self.assertEqual(settings.load({**e2e.SETTINGS, "review": {**review, "finder": "model"}}).review["finder"], "model")
        with self.assertRaises(settings.SettingsError):
            settings.load({**e2e.SETTINGS, "review": {**review, "finder": "model", "ocr": ocr}})

    def test_the_two_checks_are_the_review_stage_s_own_functions_and_the_pin_comes_first(self):
        pin = self.settings().review["ocr"]
        with mock.patch.object(review_ocr, "pinned", return_value="sentinel-pinned") as pinned, \
                mock.patch.object(ad, "_declared", side_effect=AssertionError("asked after the pin was refused")):
            ident = R.ocr_identity(self.settings())
        pinned.assert_called_once_with(pin["exe"], pin["sha256"])
        self.assertEqual((ident["reason"], ident["check"]), ("sentinel-pinned", R.OCR_CHECKS["pinned"][0]))
        with mock.patch.object(ad, "_declared", return_value=({"version": "x"}, "sentinel-declared")) as declared:
            ident = R.ocr_identity(self.settings())
        declared.assert_called_once_with(pin["exe"], review_ocr.VERSION_TIMEOUT_S)
        self.assertEqual((ident["reason"], ident["check"], ident["observed"]),
                         ("sentinel-declared", R.OCR_CHECKS["declared"][0],
                          {"asked": True, "declared": {"version": "x"}}))
        self.assertTrue(ident["levels"]["sha256_matches_pin"])
        self.assertFalse(ident["levels"]["declared_matches_release"])

    def test_a_version_output_that_is_not_utf8_is_read_as_no_version_line_not_raised(self):
        # the binary's `version` output is its own word: a build that prints bytes that are not UTF-8 (a crash dump,
        # a non-UTF-8 locale) must be decoded best-effort and refused as "no version line", never raise and crash the
        # identity gate (adapters._declared decodes with errors="replace", outside its OSError/RangeError guard).
        exe = self.bin / "bytes-ocr"
        exe.write_text(f"#!{sys.executable}\n"
                       "import sys\n"
                       "sys.stdout.buffer.write(b'\\xff\\xfe\\x80 not a version line\\n')\n", encoding="utf-8")
        exe.chmod(0o755)
        seen, why = ad._declared(str(exe), review_ocr.VERSION_TIMEOUT_S)
        self.assertIsNone(seen)
        self.assertIsNotNone(why)
        self.assertIn("no version line", why)
        self.assertIn(str(exe), why)

    def test_the_declared_text_opens_by_saying_the_bytes_matched_the_pin_but_the_version_line_did_not(self):
        # the declared refusal must distinguish itself from the pinned one: the sha256 DID match the pin, and it was
        # the `<exe> version` self-declaration that failed -- the operator needs this to choose the right remedy
        # (re-pin a correct build vs. fix a wrong path). Without the opening sentence the remedy reads as a dangling
        # fragment ("line of Open Code Review v1.12.12 ...").
        do = R.OCR_CHECKS["declared"][1]
        self.assertIn(
            "The file's bytes are the ones review.ocr.sha256 pins, but `<exe> version` did not print the version",
            do,
        )


@POSIX
class Command(unittest.TestCase):
    """`aisef run` and `aisef run --check`: what the operator reads."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        baseline = e2e.make_repo(self.tmp / "source")
        (self.tmp / "project.json").write_text(json.dumps(e2e.project_bundle(baseline)), encoding="utf-8")
        self.exe = self.tmp / "bin" / "ocr"
        self.exe.parent.mkdir()
        self.exe.write_text(f"#!{sys.executable}\n" + FAKE_OCR, encoding="utf-8")
        self.exe.chmod(0o755)
        (self.exe.parent / "scenarios.json").write_text("[{}]", encoding="utf-8")
        self.sha = hashlib.sha256(self.exe.read_bytes()).hexdigest()
        xdg = mock.patch.dict(os.environ, e2e.client_config(self.tmp))
        xdg.start()
        self.addCleanup(xdg.stop)

    def settings_file(self, **pin) -> str:
        review = {"policy": "fix-loop", "min_severity": "high", "finder": "ocr",
                  "ocr": {"exe": str(self.exe), "sha256": self.sha, "timeout_min": 1, "max_tokens": 4000, **pin}}
        path = self.tmp / "settings.json"
        path.write_text(json.dumps({**e2e.SETTINGS, "review": review}), encoding="utf-8")
        return str(path)

    def cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.run([*argv])
        return code, out.getvalue(), err.getvalue()

    def args(self, settings_path: str, *more: str) -> tuple[str, ...]:
        return ("--project", str(self.tmp / "project.json"), "--settings", settings_path, "--repo", str(self.tmp / "source"),
                *more)

    def test_a_run_with_a_binary_that_is_not_the_pin_is_refused_with_status_2_and_says_what_to_do(self):
        with mock.patch.object(R, "calibrations", e2e.calibrations), \
                mock.patch.object(preflight, "http_transport", side_effect=AssertionError("no request")), \
                mock.patch("shutil.which", side_effect=AssertionError("an executable was looked up on PATH: the run went past its identity check")):
            code, out, err = self.cli(*self.args(self.settings_file(sha256="f" * 64), "--out", str(self.tmp / "out")))
        self.assertEqual((code, out), (2, ""))
        for text in ("aisef run: refused: review.finder is ocr and its binary fails the identity check before the run",
                     "pinned: review.ocr.exe is an absolute path, readable, and its sha256 is review.ocr.sha256",
                     "expected sha256 " + "f" * 64, "not the pinned", "Find out why before changing the pin",
                     "set review.ocr.exe to its absolute path and review.ocr.sha256 to its sha256",
                     'remove review.ocr and set review.finder to "model"', "give it a new --out",
                     "No session was started and no provider request was sent."):
            self.assertIn(text, err)
        record = json.loads((self.tmp / "out" / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual(record["failure"]["stage"], "ocr identity")
        self.assertEqual((record["ocr_identity"]["status"], record["ocr_identity"]["check"][:6]), ("REFUSED", "pinned"))
        self.assertEqual(record["delivery_verdict"], "NOT_REACHED")

    def test_check_asks_the_binary_too_and_is_not_ready_without_it(self):
        with mock.patch.object(R, "calibrations", e2e.calibrations), \
                mock.patch.object(preflight, "http_transport", side_effect=AssertionError("no request")):
            code, out, _ = self.cli("--check", *self.args(self.settings_file()))
            ok = json.loads(out)
            code_bad, out_bad, _ = self.cli("--check", *self.args(self.settings_file(sha256="0" * 64)))
        self.assertEqual((code, ok["ready"], ok["ocr_identity"]["status"]), (0, True, "PASSED"))
        self.assertEqual(ok["ocr_identity"]["levels"],
                         {"sha256_matches_pin": True, "declared_matches_release": True, "build_provenance": PROVENANCE})
        bad = json.loads(out_bad)
        self.assertEqual((code_bad, bad["ready"], bad["ocr_identity"]["status"]), (2, False, "REFUSED"))
        self.assertTrue(bad["admission"]["admitted"], "everything else was ready: only the binary stops it")

    def test_a_path_the_system_cannot_name_is_refused_with_status_2_not_raised(self):
        # a NUL byte or a lone surrogate in review.ocr.exe: the settings file can say it, the loader accepts any
        # absolute string; the first look at the binary must refuse it as it refuses a missing file
        for what, exe in (("NUL", str(self.exe) + "\x00x"), ("lone surrogate", str(self.exe) + "\ud800")):
            with self.subTest(what), mock.patch.object(R, "calibrations", e2e.calibrations), \
                    mock.patch.object(preflight, "http_transport", side_effect=AssertionError("no request")):
                path = self.settings_file(exe=exe)
                code, out, err = self.cli(*self.args(path, "--out", str(self.tmp / f"out-{what[:3]}")))
                self.assertEqual((code, out), (2, ""))
                self.assertIn("aisef run: refused: review.finder is ocr and its binary fails the identity check", err)
                self.assertIn("cannot be read", err)
                self.assertIn("No session was started and no provider request was sent.", err)
                record = json.loads((self.tmp / f"out-{what[:3]}" / "RUN.json").read_text(encoding="utf-8"))
                self.assertEqual((record["failure"]["type"], record["failure"]["stage"]), ("RunRefused", "ocr identity"))
                self.assertEqual(record["ocr_identity"]["status"], "REFUSED")
                code, out, _ = self.cli("--check", *self.args(path))
                bad = json.loads(out)
                self.assertEqual((code, bad["ready"], bad["ocr_identity"]["status"]), (2, False, "REFUSED"))
                self.assertIn("cannot be read", bad["ocr_identity"]["reason"])

    def test_check_of_a_run_that_does_not_use_ocr_says_nothing_of_it(self):
        path = self.tmp / "settings.json"
        path.write_text(json.dumps(e2e.SETTINGS), encoding="utf-8")
        with mock.patch.object(R, "calibrations", e2e.calibrations):
            code, out, _ = self.cli("--check", *self.args(str(path)))
        self.assertEqual((code, json.loads(out)["ready"], "ocr_identity" in json.loads(out)), (0, True, False))


if __name__ == "__main__":
    unittest.main()
