"""V2.1 (owner B-03, kills round 3, batch T26a): what aisef2/app/settings.py's survivors of campaign 2 relied on, tested as
the requirement of whoever reads the value — the operator reading a refusal, the Reviewer and `layers_of` reading
`Settings.review`, the CLI reading a settings file — never as a sentence.

Targets: REVIEW_ABSENT, endpoint_problem, load, read. A refusal is checked for the elements an operator needs to act on it
(the setting that is wrong, the keys, the values to choose from and under which key, the host, the file) as names of their
own in the message — not glued to the text around them, whatever the quoting, joining or separator; the library's own text
(urllib's reason for an unparsable URL, the JSON decoder's position) and the connective prose are not asserted."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, cli, preflight, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.review_verify import POLICIES, SEVERITIES  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402 — the module, so its test classes are not collected again

#: a confinement setting that is only ever loaded (nothing here runs it)
CONFINEMENT = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}


def has(message: str, name: str) -> bool:
    """`name` is in `message` as a name of its own: not glued to a letter, digit, `_` or `-` on either side. So
    `provider.endpoint` has `endpoint`, `review.ocr.timeout_min` has `review.ocr`, a quoted or comma-, semicolon- or
    slash-joined `localhost` is there, and `127.0.0.1localhost` has neither of its hosts."""
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", message) is not None


def offered_under(message: str, keys: dict) -> dict:
    """{value: the key name that last precedes its first occurrence in the message} for every value of `keys`
    ({key: values}) the message names — "which list is which" without fixing the order of the keys."""
    values = {v: k for k, vs in keys.items() for v in vs}
    found, current = {}, None
    for token in re.findall(r"[\w.-]+", message):
        if token in keys:
            current = token
        elif token in values:
            found.setdefault(token, current)
    return found


def pin(**changes) -> dict:
    """A valid Open Code Review pin: the exe is absolute on every platform (the running interpreter)."""
    return {**{"exe": sys.executable, "sha256": "0" * 64, "timeout_min": 1, "max_tokens": 9}, **changes}


def document(**changes) -> dict:
    return {**copy.deepcopy(e2e.SETTINGS), **changes}


def refusal(case: unittest.TestCase, **changes) -> str:
    """The message of the SettingsError loading the shared settings document with `changes` raises."""
    with case.assertRaises(settings.SettingsError) as c:
        settings.load(document(**changes))
    return str(c.exception)


class AbsentReview(unittest.TestCase):
    """A document that names no `review` is 2.0.0's rule, and the rule says which finder reviews: the model reviewer.
    `load` itself reads that entry by key when the document also asks for confinement (which refuses Open Code Review),
    so a document with `confinement` and no `review` loads, and says "model" (the named default of settings.py's own
    documentation: the same assertion also fails REVIEW_ABSENT [7], though no production reader tells "" from "model").

    Pins aisef2/app/settings.py::REVIEW_ABSENT [2]."""

    def test_confinement_without_review_loads_and_the_finder_is_the_model(self):
        s = settings.load(document(confinement=CONFINEMENT))
        self.assertEqual(s.confinement, CONFINEMENT)
        self.assertEqual(s.review["finder"], "model")


class EndpointRefusal(unittest.TestCase):
    """An endpoint that cannot carry the provider key is refused at load with a SettingsError that names the setting —
    never loaded as str(value) ('None', '7', "['https://x/v1']") and never accepted because it does not parse; and the
    plaintext refusal gives the operator the host that is wrong and the hosts http may name, as names of their own.

    Pins aisef2/app/settings.py::endpoint_problem [5, 12, 17, 30, 32, 35]."""

    def endpoint(self, value) -> str:
        provider = {**e2e.SETTINGS["provider"], "endpoint": value}
        return refusal(self, provider=provider)

    def test_a_value_that_is_not_a_string_is_refused_not_loaded_as_its_str(self):
        for value in (None, 7, True, ["https://x/v1"], {"url": "https://x/v1"}):
            with self.subTest(endpoint=value):
                self.assertTrue(has(self.endpoint(value), "endpoint"))

    def test_the_direct_call_gives_a_reason_for_a_value_that_is_not_a_string(self):
        for value in (None, 7):
            with self.subTest(endpoint=value):
                why = settings.endpoint_problem(value)
                self.assertIsInstance(why, str)
                self.assertTrue(why)
                self.assertTrue(has(why, "endpoint"), why)

    def test_a_url_that_does_not_parse_is_refused_saying_it_is_the_endpoint(self):
        for value in ("http://127.0.0.1:abc/v1",        # a port that is not a number
                      "https://api.example.com:99999/v1",     # a port out of range
                      "http://[::1/v1"):                 # an IPv6 bracket never closed
            with self.subTest(endpoint=value):
                self.assertTrue(has(self.endpoint(value), "endpoint"))
                self.assertTrue(has(settings.endpoint_problem(value), "endpoint"))

    def test_the_plaintext_refusal_names_the_offending_host_and_each_allowed_host_apart(self):
        got = self.endpoint("http://evil.example/v1")
        for host in ("evil.example", *settings.LOOPBACK):
            self.assertTrue(has(got, host), f"{host!r} is not named in: {got}")


class ReviewShape(unittest.TestCase):
    """`review` is {policy in POLICIES, min_severity in SEVERITIES} and at most the optional keys finder and ocr: every
    other value is refused with a SettingsError — never accepted (a mistyped policy would run as advisory and nothing
    would ever block), never a TypeError/KeyError/AttributeError (read by a caller as a delivery FAIL) — and the refusal
    names the setting, its keys and every value to choose from.

    Pins aisef2/app/settings.py::load [52, 220, 221, 222]."""

    OFFERED = {"policy": POLICIES, "min_severity": SEVERITIES, "finder": settings.FINDERS}
    BAD = (None, "fix-loop", ["policy", "min_severity"], {}, {"policy": "fix-loop"}, {"min_severity": "high"},
           {"policy": "fixloop", "min_severity": "high"}, {"policy": "fix-loop", "min_severity": "urgent"},
           {"policy": "fix-loop", "min_severity": "high", "finders": "ocr"})

    def test_a_review_of_another_shape_is_refused(self):
        for review in self.BAD:
            with self.subTest(review=review):
                refusal(self, review=review)

    def test_the_refusal_names_the_setting_its_keys_and_the_values_to_choose_from(self):
        for review in self.BAD:
            with self.subTest(review=review):
                got = refusal(self, review=review)
                self.assertTrue(has(got, "review"), got)
                found = offered_under(got, self.OFFERED)
                for key, values in self.OFFERED.items():
                    for value in values:
                        self.assertEqual(found.get(value), key, f"{value!r} is not offered under {key!r}: {got}")

    def test_every_policy_with_every_floor_loads_as_given(self):
        for policy in POLICIES:
            for floor in SEVERITIES:
                with self.subTest(policy=policy, min_severity=floor):
                    s = settings.load(document(review={"policy": policy, "min_severity": floor}))
                    self.assertEqual({k: s.review[k] for k in ("policy", "min_severity", "finder", "ocr")},
                                     {"policy": policy, "min_severity": floor, "finder": "model", "ocr": None})


class ReviewFinder(unittest.TestCase):
    """The finder is one of FINDERS and `review.ocr` is given exactly when it is ocr: anything else is refused with a
    SettingsError — never run with the model reviewer as a fallback, never a pin silently dropped, never a KeyError —
    and the refusal names review.finder and its values, and for a missing or surplus pin review.ocr.

    Pins aisef2/app/settings.py::load [53, 225, 226]."""

    BASE = {"policy": "fix-loop", "min_severity": "high"}

    def review(self, **extra) -> dict:
        return {**self.BASE, **extra}

    def test_a_finder_that_is_not_one_of_the_finders_is_refused_naming_the_key_and_the_values(self):
        for finder in ("bogus", "OCR", ["ocr"]):
            with self.subTest(finder=finder):
                got = refusal(self, review=self.review(finder=finder, ocr=pin()))
                for name in ("review.finder", *settings.FINDERS):
                    self.assertTrue(has(got, name), f"{name!r} is not named in: {got}")

    def test_the_pin_is_given_exactly_when_the_finder_is_ocr_and_the_refusal_names_review_ocr(self):
        for review in (self.review(finder="model", ocr=pin()),     # a pin the model finder would silently drop
                       self.review(ocr=pin()),                   # no finder named: the model's
                       self.review(finder="ocr")):                # ocr without its pin
            with self.subTest(review=review):
                self.assertTrue(has(refusal(self, review=review), "review.ocr"))

    def test_the_two_valid_pairings_load(self):
        model = settings.load(document(review=self.review(finder="model"))).review
        self.assertEqual((model["finder"], model["ocr"]), ("model", None))
        ocr = settings.load(document(review=self.review(finder="ocr", ocr=pin()))).review
        self.assertEqual((ocr["finder"], ocr["ocr"]), ("ocr", pin()))


class ReviewOcrPin(unittest.TestCase):
    """For finder ocr, `review.ocr` is exactly {exe, max_tokens, sha256, timeout_min}: exe a str that is an absolute
    path, sha256 a str of 64 lowercase hex digits, timeout_min and max_tokens integers >= 1 (bool refused). A pin the
    run could never honour (Open Code Review is never looked up on PATH; the digest compared is hashlib's lowercase
    hexdigest) is refused at load — before the first provider request — not after the story's developer session was
    paid for; and the refusal names review.ocr, the four keys and, for a path that is not absolute, the word absolute;
    a count names its own dotted field and not the other one.

    Pins aisef2/app/settings.py::load [109, 228, 251, 252, 266, 231, 232]."""

    def review(self, ocr) -> dict:
        return {"policy": "fix-loop", "min_severity": "high", "finder": "ocr", "ocr": ocr}

    def without(self, key: str) -> dict:
        return {k: v for k, v in pin().items() if k != key}

    def test_a_pin_that_is_not_the_exact_shape_is_refused_naming_the_setting_and_the_keys(self):
        for ocr in (None, "abc", self.without("max_tokens"), {**pin(), "extra": 1}, pin(exe="ocr"), pin(exe=7),
                    pin(sha256="abc"), pin(sha256="A" * 64), pin(sha256="g" * 64), pin(sha256=5), pin(sha256="0" * 63),
                    pin(sha256="0" * 65)):
            with self.subTest(ocr=ocr):
                got = refusal(self, review=self.review(ocr))
                for name in ("review.ocr", *settings.OCR_KEYS):
                    self.assertTrue(has(got, name), f"{name!r} is not named in: {got}")

    def test_the_refusal_of_a_relative_binary_says_it_must_be_absolute(self):
        self.assertTrue(has(refusal(self, review=self.review(pin(exe="ocr"))), "absolute"))

    def test_a_pin_of_the_exact_shape_loads_as_given(self):
        s = settings.load(document(review=self.review(pin(timeout_min=3, max_tokens=7))))
        self.assertEqual(s.review["finder"], "ocr")
        self.assertEqual(s.review["ocr"], pin(timeout_min=3, max_tokens=7))

    def test_a_count_that_is_not_an_integer_of_at_least_one_is_refused_by_its_own_name(self):
        for key in ("timeout_min", "max_tokens"):
            other = "max_tokens" if key == "timeout_min" else "timeout_min"
            for bad in (0, -1, True, 1.5, "1"):
                with self.subTest(field=key, value=bad):
                    got = refusal(self, review=self.review(pin(**{key: bad})))
                    self.assertTrue(has(got, f"review.ocr.{key}"), got)
                    self.assertFalse(has(got, f"review.ocr.{other}"), got)


class ReviewLayer(unittest.TestCase):
    """The RunSpec carries the review policy as its own settings layer exactly when the settings name one: a 2.0.0
    document's RunSpec re-derives unchanged, a named review's is bound by its value (the policy, the floor and — for ocr
    — the pinned binary) and by the layer, not only by settings_sha256.

    Pins aisef2/app/settings.py::load [60, 118, 119]: the `given` entry is read by `run.layers_of` alone, and `runspec_of`
    and `verify` (app/verify.py `_runspec_problems`) both re-derive the RunSpec hash through it, so what the entry decides
    is what the hash binds."""

    X = {"policy": "fix-loop", "min_severity": "high"}

    def setUp(self) -> None:
        self.project = bundle.load(e2e.project_bundle("a" * 40))
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name)

    def layers(self, **changes) -> dict:
        return R.layers_of(self.project, settings.load(document(**changes)))

    def test_a_named_review_is_a_settings_layer_with_the_review_as_given(self):
        ocr = {**self.X, "finder": "ocr", "ocr": pin()}
        for review in (self.X, {**self.X, "policy": "advisory"}, ocr):
            with self.subTest(review=review):
                layers = self.layers(review=review)
                self.assertIn("review", layers)
                self.assertEqual(layers["review"], {"value": review, "layer": "settings"})

    def test_a_document_without_review_has_no_review_layer(self):
        self.assertNotIn("review", self.layers())

    def test_two_documents_that_differ_only_in_the_policy_have_different_layers(self):
        named, other = self.layers(review=self.X), self.layers(review={**self.X, "policy": "advisory"})
        self.assertIn("review", named)
        self.assertIn("review", other)
        self.assertNotEqual(named["review"], other["review"])

    def test_the_runspec_holds_the_layer_and_its_hash_follows_the_policy(self):
        pre = preflight.run(e2e.ROUTE, 2, e2e.provider(), self.tmp / "pre")

        def spec(**changes):
            return R.runspec_of(self.project, settings.load(document(**changes)), pre, "client-x", sys.executable,
                                ad.NoScanner())
        named, other, none = spec(review=self.X), spec(review={**self.X, "policy": "advisory"}), spec()
        self.assertIn("review", named.settings)
        self.assertEqual(named.settings["review"]["layer"], "settings")
        self.assertEqual(named.settings["review"]["value"], self.X)
        self.assertNotIn("review", none.settings)
        self.assertEqual(len({named.runspec_hash, other.runspec_hash, none.runspec_hash}), 3)


class ReadRefusal(unittest.TestCase):
    """A settings file that cannot be read, is not UTF-8 or is not JSON is a refusal — a SettingsError (exit 2 from the
    command, read by a caller as "not run", not as a delivery FAIL), never the decoder's own exception — and the refusal
    names the file's path as an element of its own and gives the cause: its exception class for a file that cannot be
    read, the word JSON for one that does not parse.

    Pins aisef2/app/settings.py::read [2, 4, 7]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = pathlib.Path(t.name)

    def refused(self, path: pathlib.Path) -> str:
        """The refusal's text but for the file's name — which the refusal gives as a name of its own (its first mention
        is not glued to the text before or after it), wherever it puts it."""
        with self.assertRaises(settings.SettingsError) as c:
            settings.read(path)
        message, name = str(c.exception), str(path)
        start = message.find(name)
        self.assertGreaterEqual(start, 0, f"the refusal does not name {name!r}: {message}")
        end = start + len(name)
        for glued in (message[start - 1:start] if start else "", message[end:end + 1]):
            self.assertIsNone(re.match(r"[\w.-]", glued), f"{name!r} is glued to the text around it: {message}")
        return message[:start] + " " + message[end:]

    def non_utf8(self) -> pathlib.Path:
        p = self.root / "latin1.json"
        p.write_bytes(b'{"route": "caf\xe9"}')
        return p

    def test_an_absent_file(self):
        self.assertTrue(has(self.refused(self.root / "absent.json"), "FileNotFoundError"))

    def test_a_file_that_is_not_utf8(self):
        self.assertTrue(has(self.refused(self.non_utf8()), "UnicodeDecodeError"))

    def test_a_file_that_is_not_json(self):
        p = self.root / "notjson.json"
        p.write_text("{not json", encoding="utf-8")
        self.assertTrue(has(self.refused(p).lower(), "json"))      # the cause's category, in any case

    def test_the_command_refuses_a_settings_file_that_is_not_utf8_with_exit_2(self):
        project = self.root / "bundle.json"
        project.write_text(json.dumps(e2e.project_bundle("a" * 40)), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.run(["--check", "--project", str(project), "--settings", str(self.non_utf8()),
                            "--repo", str(self.root / "repo")])
        self.assertEqual(code, 2, err.getvalue())
        self.assertIn("refused", err.getvalue())
        self.assertIn("latin1.json", err.getvalue())


if __name__ == "__main__":
    unittest.main()
