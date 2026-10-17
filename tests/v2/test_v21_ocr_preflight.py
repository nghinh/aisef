"""V2.1 (owner 2026-10-15, item 5, second paragraph; lane ocr-preflight): a run whose review is Open Code Review checks
the binary BEFORE it opens a developer session — and before the clone, the test interpreter and the route's preflight —
so that nobody works and pays and then finds the tool unusable.

The check is the review stage's own, the same two functions in the same order (`review_ocr.pinned`, then
`adapters._declared`): the settings name the binary by absolute path and its sha256 (`review.finder` "ocr", `review.ocr`),
and the run asks `<exe> version` in a clean environment. It is an earlier look and replaces nothing: `Reviewer._ocr`
makes both checks again at the moment of use, and a binary replaced between the preflight and the review is refused
there (`SwapAfterPreflight`: the developer session replaces it; every test of `Gate`/`Chain` in test_v21_ocr_gate.py
still holds).

What the record says, and what it does not: `ocr_identity.levels` names three levels — the bytes are the pin's
(`sha256_matches_pin`), the binary's own `version` line names the pinned release (`declared_matches_release`: a
self-declaration, a binary prints what it was built or edited to print) and `build_provenance`, "NOT_ESTABLISHED": a run
never establishes it. Nothing here says "verified build".

`review.policy` does not decide whether the binary is asked: an identity failure at the moment of use is
CapabilityUnrunnable under `advisory` as under `fix-loop`, and that ends every story. So the early check applies to
every run whose `review.finder` is "ocr", whatever the policy, and to no other run. (It does not say that every committed
story has a complete review: under `advisory` an incomplete review is recorded and does not block —
test_v21_review_chain.py, `test_under_advisory_the_incomplete_review_is_recorded_and_does_not_block`.)

The scenario is `test_app_run.ProductBase` (a one-story calc project, a fake client, a fake provider) with the finder
of `test_v21_review_chain` (a fake Open Code Review executable, pinned by sha256 like the real one) and the table of
answers of `test_v21_ocr_declared`. Nothing reaches a network, a model or a provider."""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import pathlib
import sys
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import preflight, review_ocr, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2.test_v21_ocr_declared import ANSWERS, REFUSED  # noqa: E402
from tests.v2.test_v21_review_chain import FAKE_OCR  # noqa: E402

POSIX = unittest.skipUnless(os.name == "posix", "the fake client and the fake finder are scripts started by their shebang")

#: every start of the client, whatever it was asked (`--version` of the run's client identity included), is written
#: first; a client session (`--title`) then applies swap.json — {path relative to this directory: new text} — which is
#: how a developer session replaces a file of the operator's between the run's preflight and its review
CLIENT_PREFIX = r'''import json as _json, pathlib as _pathlib, sys as _sys
_here = _pathlib.Path(__file__).parent
with (_here / "starts.jsonl").open("a", encoding="utf-8") as _fh:
    _fh.write(_json.dumps(_sys.argv[1:]) + "\n")
if "--title" in _sys.argv and (_here / "swap.json").exists():
    for _rel, _text in _json.loads((_here / "swap.json").read_text(encoding="utf-8")).items():
        (_here / _rel).write_text(_text, encoding="utf-8")
'''

#: the binary a developer session leaves in the place of the pinned one: it records that it was ever started
REPLACEMENT = "#!{python}\nimport pathlib\npathlib.Path(__file__).with_name('replacement-started').write_text('started')\n"


class OcrBase(e2e.ProductBase):
    """The one-story calc project reviewed by a fake Open Code Review; the client records every start."""

    POLICY = "fix-loop"

    def setUp(self) -> None:
        super().setUp()
        text = self.client.read_text(encoding="utf-8")
        head, body = text.split("\n", 1)
        self.client.write_text(head + "\n" + CLIENT_PREFIX + body, encoding="utf-8")
        self.bin = self.tmp / "ocr"
        self.bin.mkdir()
        self.exe = self.bin / "ocr"
        self.exe.write_text(f"#!{sys.executable}\n" + FAKE_OCR, encoding="utf-8")
        self.exe.chmod(0o755)
        (self.bin / "scenarios.json").write_text(json.dumps([{}]), encoding="utf-8")
        self.settings = self.with_pin()
        self.transport = e2e.provider()
        self.runs = 0

    def fresh(self) -> str:
        """A run directory this test has not used (a run directory is never reused)."""
        self.runs += 1
        return f"out{self.runs}"

    # -- the settings
    def with_pin(self, policy: str | None = None, *, exe: str | None = None, sha256: str | None = None) -> settings.Settings:
        pin = {"exe": exe or str(self.exe), "sha256": sha256 or hashlib.sha256(self.exe.read_bytes()).hexdigest(),
               "timeout_min": 1, "max_tokens": 4000}
        return settings.load({**e2e.SETTINGS, "review": {"policy": policy or self.POLICY, "min_severity": "high",
                                                         "finder": "ocr", "ocr": pin}})

    def forced(self, **pin) -> settings.Settings:
        """Settings whose pin `settings.load` would have refused (no path, not absolute): what the run's own check meets
        when the settings object is not the loader's."""
        s = self.with_pin()
        return dataclasses.replace(s, review={**s.review, "ocr": {**s.review["ocr"], **pin}})

    def answer(self, name: str, **more) -> None:
        text, code, sleep = ANSWERS[name]
        (self.bin / "identity.json").write_text(json.dumps({"text": text, "exit": code, "sleep": sleep, **more}),
                                                encoding="utf-8")

    # -- what happened
    def asked(self) -> list[list[str]]:
        p = self.bin / "calls.jsonl"
        return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def client_starts(self) -> list[list[str]]:
        p = self.client.parent / "starts.jsonl"
        return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def failures(self) -> list[str]:
        return [e.data["code"] for e in self.journal().events if e.type == "failure/observed"]

    def record(self, out: str = "out") -> dict:
        return json.loads((self.tmp / out / "RUN.json").read_text(encoding="utf-8"))

    def refused(self, out: str | None = None, **kw) -> tuple[str, dict]:
        """`execute` of the current settings, which must be refused (RunRefused) — and refused with nothing started and
        nothing sent: no provider request or construction of the provider's transport, no client start of any kind
        (not even `--version`), no session directory, no journal, and a record that says where and why."""
        out = out or self.fresh()
        with mock.patch.object(preflight, "http_transport", side_effect=AssertionError("the transport was constructed")) \
                as constructed, mock.patch.object(preflight, "run", side_effect=AssertionError("the preflight ran")) as ran, \
                self.assertRaises(R.RunRefused) as cm:
            self.execute(out=out, transport=None, **kw)
        constructed.assert_not_called()
        ran.assert_not_called()
        self.assertEqual(self.client_starts(), [], "no client start, not even for its version")
        for name in ("sessions", "preflight", "repo", "work", "test-python", "run"):
            self.assertFalse((self.tmp / out / name).exists(), name)
        rec = self.record(out)
        self.assertEqual((rec["failure"]["type"], rec["failure"]["stage"]), ("RunRefused", "ocr identity"))
        self.assertEqual((rec["delivery_verdict"], rec["journal"], rec["sessions"], rec["productproof"]),
                         ("NOT_REACHED", None, [], None))
        self.assertNotIn("preflight", rec)
        return str(cm.exception), rec["ocr_identity"]


@POSIX
class PreflightRefuses(OcrBase):
    """A binary that is not the pinned build stops the run before the first session: each way it can be wrong."""

    def assert_structured(self, ident: dict, check: str, said: str, *, sha256: str | None = None) -> None:
        pin = sha256 or hashlib.sha256(self.exe.read_bytes()).hexdigest()
        self.assertEqual(ident["status"], "REFUSED")
        self.assertTrue(ident["check"].startswith(check), ident["check"])
        self.assertEqual(ident["expected"], {"sha256": pin, "version": review_ocr.OCR["version"],
                                             "commit": review_ocr.OCR["commit"]})
        self.assertTrue(ident["operator"] and "review.ocr" in ident["operator"])
        self.assertIn("review.finder", ident["operator"])
        self.assertEqual(ident["levels"]["build_provenance"], "NOT_ESTABLISHED")
        self.assertNotIn("verified build", json.dumps(ident))
        self.assertIn(said, ident["reason"])

    def test_no_binary_path_is_refused_before_any_session(self):
        for pin in ({"exe": ""}, {"exe": None}, {"sha256": ""}):
            with self.subTest(pin=pin):
                self.settings = self.forced(**pin)
                said, ident = self.refused()
                self.assertIn("review.ocr.exe and review.ocr.sha256 name no binary", said)
                self.assertEqual(ident["check"][:6], "pinned")
                self.assertEqual(self.asked(), [], "no binary was started")

    def test_a_path_that_is_not_absolute_is_refused_before_any_session(self):
        self.settings = self.forced(exe="ocr")
        said, ident = self.refused()
        self.assertIn("absolute path", said)
        self.assertEqual(ident["levels"], {"sha256_matches_pin": False, "declared_matches_release": False,
                                           "build_provenance": "NOT_ESTABLISHED"})
        self.assertEqual(ident["observed"], {"asked": False, "declared": None})
        self.assertEqual(self.asked(), [])

    def test_a_binary_that_cannot_be_read_is_refused_before_any_session(self):
        missing = self.bin / "no-such-ocr"
        for what, exe in (("missing", missing), ("a directory in its place", self.bin)):
            with self.subTest(what):
                self.settings = self.forced(exe=str(exe))
                said, ident = self.refused()
                self.assertIn("cannot be read", said)
                self.assertEqual(ident["levels"]["sha256_matches_pin"], False)
                self.assertEqual(self.asked(), [])

    def test_a_binary_the_run_may_not_read_is_refused_before_any_session(self):
        self.exe.chmod(0)
        self.addCleanup(self.exe.chmod, 0o755)
        real = pathlib.Path.read_bytes

        def closed(path):       # root reads a file closed to everyone: the read then fails as the system would fail it
            if path == self.exe:
                raise PermissionError(13, "Permission denied")
            return real(path)

        with mock.patch.object(pathlib.Path, "read_bytes", closed) if os.access(self.exe, os.R_OK) \
                else contextlib.nullcontext():
            said, ident = self.refused()
        self.assertIn("cannot be read (PermissionError)", said)
        self.assertFalse(ident["levels"]["sha256_matches_pin"])
        self.assertEqual(ident["check"][:6], "pinned")
        self.assertEqual(self.asked(), [])

    def test_a_path_the_system_cannot_name_is_refused_before_any_session_not_raised(self):
        # a NUL byte or a lone surrogate: the loader accepts any absolute string; the read raised ValueError out of the
        # run (a traceback, RUN.json without ocr_identity) before pinned() answered for it
        for what, exe, error in (("NUL", str(self.exe) + "\x00x", "ValueError"),
                                 ("lone surrogate", str(self.exe) + "\ud800", "UnicodeEncodeError")):
            with self.subTest(what):
                self.settings = self.forced(exe=exe)
                said, ident = self.refused()
                self.assertIn(f"cannot be read ({error})", said)
                self.assertEqual(ident["check"][:6], "pinned")
                self.assertEqual(ident["observed"], {"asked": False, "declared": None})
                self.assertEqual(self.asked(), [])

    def test_a_binary_that_cannot_be_started_is_refused_before_any_session_with_the_system_s_reason(self):
        self.exe.chmod(0o644)       # readable, so the pin holds; not executable
        said, ident = self.refused()
        self.assert_structured(ident, "declared", "`version` could not be started")
        self.assertIn("Permission denied", said)
        self.assertNotIn("(RangeError)", said, "the kernel's type name tells the operator nothing")
        self.assertEqual(ident["observed"], {"asked": True, "declared": None})
        self.assertTrue(ident["levels"]["sha256_matches_pin"])
        self.assertEqual(self.asked(), [])
        self.exe.chmod(0o755)
        self.exe.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")      # other bytes, pinned
        self.settings = self.with_pin()
        said, ident = self.refused()
        self.assertIn("`version` could not be started", said)
        self.assertIn("No such file", said)
        self.assertEqual(self.asked(), [])

    def test_the_preflight_asks_the_review_stage_s_own_two_functions_in_their_order(self):
        # no second implementation: what the functions the review stage uses say is what the preflight reports
        pin = self.settings.review["ocr"]
        with mock.patch.object(review_ocr, "pinned", return_value="sentinel-pinned: refused") as pinned, \
                mock.patch.object(ad, "_declared", side_effect=AssertionError("asked after the pin was refused")):
            said, ident = self.refused()
        pinned.assert_called_once_with(pin["exe"], pin["sha256"])
        self.assertIn("sentinel-pinned: refused", said)
        self.assertEqual(ident["check"][:6], "pinned")
        with mock.patch.object(ad, "_declared", return_value=(None, "sentinel-declared: refused")) as declared:
            said, ident = self.refused()
        declared.assert_called_once_with(pin["exe"], review_ocr.VERSION_TIMEOUT_S)
        self.assertIn("sentinel-declared: refused", said)
        self.assertEqual(ident["check"][:8], "declared")
        self.assertTrue(ident["levels"]["sha256_matches_pin"])
        self.assertEqual(self.asked(), [], "the stand-ins answered: the binary was not started")

    def test_the_refusal_comes_before_the_claim_on_a_predecessor(self):
        pred = self.tmp / "pred"
        pred.mkdir()
        (pred / "RUN.json").write_text("{}", encoding="utf-8")
        self.answer("another version")
        said, _ = self.refused(predecessor=pred)
        self.assertIn("v1.11.0", said)
        self.assertEqual(sorted(p.name for p in pred.iterdir()), ["RUN.json"], "no claim was written on the predecessor")

    def test_bytes_that_are_not_the_pin_are_refused_before_any_session_and_never_started(self):
        wrong = "0" * 64
        self.settings = self.with_pin(sha256=wrong)
        said, ident = self.refused()
        self.assert_structured(ident, "pinned", "not the pinned", sha256=wrong)
        self.assertIn(wrong, said)                       # the expected value, whole
        self.assertIn("shasum -a 256", ident["operator"])
        self.assertEqual(self.asked(), [], "bytes that are not the pin are never started, not even for `version`")

    def test_every_answer_that_is_not_the_pinned_build_is_refused_before_any_session(self):
        for name, words in REFUSED.items():
            with self.subTest(answer=name):
                self.answer(name)
                # the bound only for the binary that never answers (the script is started and then killed at it): every
                # other answer gets the real one, so a slow interpreter start under load is not "did not answer"
                bound = mock.patch.object(review_ocr, "VERSION_TIMEOUT_S", 3.0) if ANSWERS[name][2] \
                    else contextlib.nullcontext()
                before = len(self.asked())
                with bound:
                    said, ident = self.refused()
                self.assert_structured(ident, "declared", words[0])
                for word in words:
                    self.assertIn(word, said)
                self.assertTrue(ident["levels"]["sha256_matches_pin"], "the bytes are the pin's; the answer is not")
                self.assertFalse(ident["levels"]["declared_matches_release"])
                self.assertEqual(self.asked()[before:], [["version"]], "only the version question was asked")
                for word in ("expected sha256", "observed", "No session was started", "no provider request"):
                    self.assertIn(word, said)

    def test_a_mismatch_names_what_the_binary_said_in_the_record(self):
        self.answer("another version")
        _, ident = self.refused()
        self.assertEqual({k: ident["observed"]["declared"][k] for k in ("version", "commit")},
                         {"version": "v1.11.0", "commit": "182898c"})
        self.assertIn("v1.12.12", ident["reason"])

    def test_the_question_is_bounded_and_does_not_wait_for_a_binary_that_never_answers(self):
        self.answer("never answers")           # it sleeps 30 s before it prints anything
        begun = time.monotonic()
        with mock.patch.object(review_ocr, "VERSION_TIMEOUT_S", 2.0):
            said, ident = self.refused()
        self.assertLess(time.monotonic() - begun, 25, "the run waited for the binary instead of for its bound")
        self.assertIn("did not answer in time", said)
        self.assertEqual(ident["observed"]["declared"], None)

    def test_the_policy_does_not_decide_it_advisory_is_refused_too(self):
        # an identity failure at the moment of use is CapabilityUnrunnable under advisory as under fix-loop (the policy is
        # not consulted: SwapAfterPreflight shows both stories ending); a run that would end every story is refused at
        # once, not after the developer sessions
        self.answer("another commit")
        self.settings = self.with_pin("advisory")
        said, ident = self.refused()
        self.assertIn("deadbee", said)
        self.assertEqual(ident["status"], "REFUSED")

    def test_the_remedy_the_operator_text_gives_works_a_new_out_runs_and_the_same_out_does_not(self):
        good = self.settings
        self.settings = self.with_pin(sha256="0" * 64)
        self.refused(out="out-first")
        self.assertIn("give it a new --out", R.OCR_CHECKS["pinned"][1])
        self.settings = good                                   # the pin corrected, as the text says
        with mock.patch.object(preflight, "http_transport", side_effect=AssertionError("a provider was reached")), \
                self.assertRaises(R.RunRefused) as cm:
            self.execute(out="out-first", transport=None)
        self.assertIn("never reused", str(cm.exception))      # the refused run's directory is its record
        self.assertEqual(self.asked(), [], "the second attempt asked nothing: it stopped at the directory")
        rec = self.execute(out="out-second", transport=self.transport)
        self.assertEqual((rec["delivery_verdict"], rec["ocr_identity"]["status"]), ("PASS", "PASSED"))

    def test_the_settings_loader_refuses_a_pin_without_a_path_before_anything(self):
        base = {**e2e.SETTINGS, "review": {"policy": "fix-loop", "min_severity": "high", "finder": "ocr"}}
        for what, review in (("no ocr", base["review"]),
                             ("relative", {**base["review"], "ocr": {"exe": "ocr", "sha256": "a" * 64, "timeout_min": 1,
                                                                    "max_tokens": 1}}),
                             ("no path", {**base["review"], "ocr": {"exe": "", "sha256": "a" * 64, "timeout_min": 1,
                                                                   "max_tokens": 1}})):
            with self.subTest(what), self.assertRaises(settings.SettingsError):
                settings.load({**base, "review": review})


@POSIX
class PreflightPasses(OcrBase):
    """A binary that is the pinned build: the run asks once before anything, again at each review, and says what was
    and was not established."""

    def test_the_pinned_build_passes_before_the_provider_is_asked_and_the_record_says_which_level(self):
        first_request = []
        base = self.transport

        def watching(path, body=None):      # at the run's first provider request, what had been asked of the binary
            if not first_request:
                first_request.append((list(self.asked()), list(self.client_starts())))
            return base(path, body)

        rec = self.execute(transport=watching)
        self.assertEqual((rec["delivery_verdict"], rec["story_outcomes"]), ("PASS", {"S1": ["COMMIT"]}))
        self.assertEqual(first_request, [([["version"]], [])],
                         "the binary was asked, once, before the first provider request and any client start")
        kinds = ["version" if a == ["version"] else "preview" if "--preview" in a else "review" for a in self.asked()]
        self.assertEqual(kinds, ["version", "version", "preview", "review"], "preflight, then the review's own, at use")
        ident = rec["ocr_identity"]
        self.assertEqual(ident["status"], "PASSED")
        self.assertEqual(ident["levels"], {"sha256_matches_pin": True, "declared_matches_release": True,
                                           "build_provenance": "NOT_ESTABLISHED"})
        self.assertEqual(ident["observed"]["asked"], True)
        self.assertEqual(ident["observed"]["declared"]["version"], "v1.12.12")
        self.assertEqual(ident["expected"]["sha256"], hashlib.sha256(self.exe.read_bytes()).hexdigest())
        self.assertEqual(ident["finder"], "ocr", "what the settings name; the release the run expects is in `expected`")
        self.assertEqual(ident["expected"]["version"], "v1.12.12")
        self.assertIn("self-declaration", ident["statement"])
        self.assertIn("never established by a run", ident["statement"])
        self.assertIn("not the control", ident["statement"])
        for forbidden in ("verified build", "built from source", "provenance established", "authentic"):
            self.assertNotIn(forbidden, json.dumps(ident))
        self.assertNotIn("check", ident)
        self.assertEqual(self.record()["ocr_identity"], ident)
        (s,) = [x for x in rec["sessions"] if x["role"] == "reviewer"]
        self.assertEqual(s["identity"]["declared"], ident["observed"]["declared"])     # the review's own look agrees
        self.assertEqual(verify(self.project, self.tmp / "out")["verdict"], "VERIFIED")

    def test_advisory_passes_the_same_way(self):
        self.settings = self.with_pin("advisory")
        rec = self.execute(transport=self.transport)
        self.assertEqual((rec["delivery_verdict"], rec["ocr_identity"]["status"]), ("PASS", "PASSED"))

    def test_a_run_that_does_not_review_with_ocr_is_not_asked_anything_and_has_no_record_of_it(self):
        for what, review in (("no review", None), ("model, fix-loop", {"policy": "fix-loop", "min_severity": "high"}),
                             ("model, named", {"policy": "advisory", "min_severity": "high", "finder": "model"})):
            with self.subTest(what):
                self.settings = settings.load({**e2e.SETTINGS, **({"review": review} if review else {})})
                with mock.patch.object(review_ocr, "pinned", side_effect=AssertionError("asked about a binary")), \
                        mock.patch.object(ad, "_declared", side_effect=AssertionError("asked a binary")):
                    rec = self.execute(out=self.fresh(), transport=e2e.provider())
                self.assertEqual(rec["delivery_verdict"], "PASS")
                self.assertNotIn("ocr_identity", rec)
        self.assertEqual(self.asked(), [])


@POSIX
class SwapAfterPreflight(OcrBase):
    """The early look is not the control: what changes between the preflight and the review is refused at the review,
    with nothing of it started. The developer session does the replacing — the one process that runs in between."""

    def swapped_run(self) -> dict:
        rec = self.execute(transport=self.transport)
        self.assertEqual((rec["delivery_verdict"], rec["story_outcomes"]), ("FAIL", {"S1": ["RETRY", "ROLLBACK"]}))
        self.assertEqual(self.failures(), ["CAPABILITY_UNRUNNABLE", "CAPABILITY_UNRUNNABLE"])
        self.assertEqual(rec["ocr_identity"]["status"], "PASSED", "what the preflight saw was true when it saw it")
        self.assertEqual([s["role"] for s in rec["sessions"]], ["developer", "developer"], "no reviewer session")
        self.assertEqual(e2e.git(self.tmp / "out" / "repo", "rev-parse", "main"), self.baseline)
        return rec

    def reasons(self) -> list[str]:
        return [e.data["detail"] for e in self.journal().events
                if e.type == "provider/result" and "reviewer cannot run" in e.data["detail"]]

    def test_bytes_replaced_after_the_preflight_are_refused_at_the_review_and_never_started(self):
        replacement = REPLACEMENT.format(python=sys.executable)
        (self.client.parent / "swap.json").write_text(json.dumps({"../ocr/ocr": replacement}), encoding="utf-8")
        self.swapped_run()
        said = self.reasons()
        self.assertEqual(len(said), 2)
        self.assertTrue(all("not the pinned" in d for d in said), said)
        self.assertEqual(self.asked(), [["version"]], "only the preflight's question: the replacement never ran")
        self.assertFalse((self.bin / "replacement-started").exists())
        self.assertNotEqual(hashlib.sha256(self.exe.read_bytes()).hexdigest(), self.settings.review["ocr"]["sha256"])

    def test_a_binary_that_answers_otherwise_after_the_preflight_is_refused_at_the_review(self):
        self.answer("another version", after_asks=1)      # the first question (the preflight's) is the pinned build's
        self.swapped_run()
        said = self.reasons()
        self.assertEqual(len(said), 2)
        self.assertTrue(all("v1.11.0" in d and "v1.12.12" in d for d in said), said)
        self.assertEqual(self.asked(), [["version"]] * 3, "the preflight's question and one at each of two reviews")

    def test_under_advisory_the_same_failure_at_the_review_ends_the_story_too(self):
        # the evidence for applying the early look whatever the policy: the identity check at use is made before the
        # policy is consulted (an incomplete review, by contrast, does not block under advisory)
        self.settings = self.with_pin("advisory")
        self.answer("another version", after_asks=1)
        self.swapped_run()
        said = self.reasons()
        self.assertEqual(len(said), 2)
        self.assertTrue(all("v1.11.0" in d for d in said), said)


if __name__ == "__main__":
    unittest.main()
