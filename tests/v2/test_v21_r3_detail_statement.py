"""V2.1 (owner B-03 round 3, item 5): `review_verify.detail` is a bounded STATEMENT of a finding.

The owner: the 1,500-character limit applies to the summary only and must not lose what is needed to verify or
reproduce the finding; the summary states the conditions to reproduce, the expected and the actual result, that and how
much was cut, and where the artifact is; a secret is never in it, and not half of one at the cut.

Who reads the statement, and what each relies on:

* the developer, in the retry prompt (`feedback.retry_feedback` prints a blocked row's detail): which finding, which
  clause, the verification and why, the anchor, the stimulus and the expected result — as valid JSON;
* a verifier or an operator: that the statement is valid JSON of at most `SUMMARY_MAX` characters, whatever the
  finding held; that `elided` names exactly the fields that are not whole and how many characters each lost; the
  artifact reference.

So the tests assert identifying elements and machine-readable values, never whole sentences. The key set of the statement
is asserted whole where it is the contract.

Pins aisef2/app/review_verify.py::detail, ::_fit, ::redacted, ::Artifact.__post_init__"""

from __future__ import annotations

import json
import pathlib
import random
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.journal.event import canonical  # noqa: E402

MAIN = {"kind": "cli_invocation", "locator": "ledgerlock:__main__"}
SECRET = "zq9-KEY-7f3a91c2b8"
ART = V.Artifact("review-findings/S1.1.0.json", "ab" * 32, 4321)
REASON = "probe.cli_invocation refutes the behaviour R-9 is said to demand"
ANCHOR_REASON = "clause R-9/3's approved outcome {\"exit_code\":3} (BC-1, BC-2)"
KEYS = {"anchor", "anchor_why", "artifact", "artifact_why", "clause", "elided", "finding", "observed", "reproducer",
        "severity", "summary", "verification", "why"}
CONTROL = "\x01"      # six characters once encoded: the worst a character costs


def finding(stimulus=None, observable=None, subject=None, **top) -> dict:
    f = {"id": "FND-7", "severity": "high", "summary": "snapshot of a missing file must exit 3",
         "reproducer": {"clause": "R-9/3", "subject": dict(MAIN) if subject is None else subject,
                        "stimulus": {"argv": ["snapshot", "<ws>/missing.jsonl"]} if stimulus is None else stimulus,
                        "observable": {"exit_code": 3, "within_s": 10} if observable is None else observable}}
    f.update(top)
    return f


def verification(reason=REASON, status=V.CONFIRMED, observed="REFUTED") -> V.Verification:
    return V.Verification(status, reason, "probe.cli_invocation", observed)


def anchor(reason=ANCHOR_REASON, status=V.ANCHORED) -> V.Anchor:
    return V.Anchor(status, reason, ("BC-1", "BC-2"))


def stated(f=None, v=None, a=True, artifact=ART, **kw) -> tuple[str, dict]:
    text = V.detail(finding() if f is None else f, verification() if v is None else v,
                    anchor() if a is True else a, artifact, **kw)
    return text, json.loads(text)


class TheStatementIsBoundedByConstruction(unittest.TestCase):
    """A finding of any size is stated as valid JSON of at most SUMMARY_MAX characters, with what decided the block in
    it — the old statement sliced its encoded text at 1,500 and lost, in that order, subject, severity, summary,
    verification and why (measured: a 3,000-character stdin gave 1,500 characters of invalid JSON)."""

    def test_a_short_finding_is_stated_whole_and_nothing_is_marked(self):
        text, d = stated()
        self.assertEqual(d, {
            "finding": "FND-7", "severity": "high", "summary": "snapshot of a missing file must exit 3", "clause": "R-9/3",
            "verification": V.CONFIRMED, "why": REASON, "observed": "REFUTED", "anchor": V.ANCHORED,
            "anchor_why": ANCHOR_REASON, "artifact": {"path": ART.path, "sha256": ART.sha256, "bytes": 4321},
            "reproducer": {"subject": MAIN, "stimulus": {"argv": ["snapshot", "<ws>/missing.jsonl"]},
                           "observable": {"exit_code": 3, "within_s": 10}}})
        self.assertNotIn("elided", d)
        self.assertLess(len(text), V.SUMMARY_MAX)

    def test_what_decided_the_block_is_there_whatever_the_size_of_the_stimulus(self):
        _, whole = stated()
        for pad in (1000, 5000, 100_000):
            with self.subTest(pad=pad):
                stimulus = {"argv": ["snapshot", "<ws>/missing.jsonl"], "stdin": {"text": "x" * pad}}
                text, d = stated(finding(stimulus=stimulus))
                self.assertLessEqual(len(text), V.SUMMARY_MAX)
                for key in ("finding", "severity", "clause", "verification", "why", "observed", "anchor", "anchor_why",
                            "artifact", "summary"):
                    self.assertEqual(d[key], whole[key], key)
                self.assertEqual(d["reproducer"]["subject"], MAIN)
                self.assertEqual(d["reproducer"]["observable"], {"exit_code": 3, "within_s": 10})
                canon = json.dumps(stimulus, ensure_ascii=False, sort_keys=True)
                shown = d["reproducer"]["stimulus"]
                self.assertIsInstance(shown, str)       # a value that does not fit is a prefix of its JSON text
                self.assertTrue(canon.startswith(shown))
                self.assertEqual(d["elided"], {"stimulus": len(canon) - len(shown)})
                self.assertIn('"argv": ["snapshot"', shown)     # the conditions to reproduce come first in the text

    def test_one_huge_field_evicts_no_other(self):
        _, whole = stated()
        big = "y" * 100_000
        cases = {
            "summary": (finding(summary=big), lambda d: d["summary"]),
            "observable": (finding(observable={"stdout": {"text": big}, "exit_code": 3, "within_s": 10}),
                           lambda d: d["reproducer"]["observable"]),
            "subject": (finding(subject={"kind": "cli_invocation", "locator": big}),
                        lambda d: d["reproducer"]["subject"]),
            "stimulus": (finding(stimulus={"argv": [big]}), lambda d: d["reproducer"]["stimulus"]),
        }
        for name, (f, field) in cases.items():
            with self.subTest(name):
                text, d = stated(f)
                self.assertLessEqual(len(text), V.SUMMARY_MAX)
                self.assertEqual(list(d["elided"]), [name])         # the one that was cut, and only it
                self.assertGreater(d["elided"][name], 99_000)       # how much it lost: almost everything
                self.assertIsInstance(field(d), str)
                for other in ("summary", "subject", "stimulus", "observable"):
                    if other != name:
                        got = d["summary"] if other == "summary" else d["reproducer"][other]
                        want = whole["summary"] if other == "summary" else whole["reproducer"][other]
                        self.assertEqual(got, want, other)
                for key in ("verification", "why", "observed", "anchor", "anchor_why", "artifact", "severity", "clause"):
                    self.assertEqual(d[key], whole[key], key)

    def test_several_huge_fields_share_what_is_left_and_all_are_marked(self):
        f = finding(stimulus={"argv": ["a" * 50_000]}, observable={"stdout": {"text": "b" * 50_000}, "exit_code": 3},
                    summary="c" * 50_000)
        text, d = stated(f)
        self.assertLessEqual(len(text), V.SUMMARY_MAX)
        self.assertEqual(sorted(d["elided"]), ["observable", "stimulus", "summary"])
        shown = {"summary": d["summary"], "stimulus": d["reproducer"]["stimulus"], "observable": d["reproducer"]["observable"]}
        for name, part in shown.items():
            self.assertGreater(len(part), 100, name)     # a share, not a token
        self.assertEqual(d["reproducer"]["subject"], MAIN)    # small: whole, it takes what it needs first

    def test_each_decisive_field_is_cut_at_its_own_bound_and_marked_exactly(self):
        bounds = {"finding": V.FINDING_MAX, "clause": V.CLAUSE_MAX, "verification": V.STATUS_MAX, "why": V.WHY_MAX,
                  "observed": V.OBSERVED_MAX, "anchor": V.STATUS_MAX, "anchor_why": V.WHY_MAX,
                  "artifact_why": V.NOT_KEPT_MAX}
        _, whole = stated()
        for filler, width in (("x", 1), (CONTROL, 6)):
            for name, bound in bounds.items():
                with self.subTest(name=name, width=width):
                    text = filler * 1000
                    f, v, a, art = finding(), verification(), anchor(), ART
                    if name == "finding":
                        f["id"] = text
                    elif name == "clause":
                        f["reproducer"]["clause"] = text
                    elif name == "verification":
                        v = verification(status=text)
                    elif name == "why":
                        v = verification(reason=text)
                    elif name == "observed":
                        v = verification(observed=text)
                    elif name == "anchor":
                        a = anchor(status=text)
                    elif name == "anchor_why":
                        a = anchor(reason=text)
                    else:
                        art = text
                    out, d = stated(f, v, a, art)
                    self.assertLessEqual(len(out), V.SUMMARY_MAX)
                    kept = bound // width
                    self.assertEqual(d[name], filler * kept)
                    self.assertEqual(d["elided"], {name: 1000 - kept})
                    if name == "artifact_why":
                        self.assertIsNone(d["artifact"])
                    for other in ("severity", "summary"):      # nothing else moved
                        self.assertEqual(d[other], whole[other])

    def test_the_bound_holds_for_a_seeded_sweep_of_adversarial_findings(self):
        rnd = random.Random(20261012)
        alphabet = ["a", "é", "中", "\U0001f600", '"', "\\", "\n", CONTROL, "\x7f", " ", "\ud800", " "]

        def text(n):
            return "".join(rnd.choice(alphabet) for _ in range(n))

        def value(depth=0):
            k = rnd.random()
            if depth > 3 or k < 0.35:
                return text(rnd.choice([0, 3, 40, 300, 5000]))
            if k < 0.5:
                return rnd.choice([0, 1, -5, 3.5, None, True])
            if k < 0.75:
                return [value(depth + 1) for _ in range(rnd.randint(0, 6))]
            return {text(rnd.randint(0, 8)): value(depth + 1) for _ in range(rnd.randint(0, 6))}
        longest = 0
        for n in range(400):
            f = {"id": text(rnd.choice([0, 5, 90, 5000])), "severity": text(3),
                 "summary": text(rnd.choice([0, 50, 2000, 100_000])),
                 "reproducer": {"clause": rnd.choice([text(10), text(300), 5, None, {"a": 1}]), "subject": value(),
                                "stimulus": value(), "observable": value()}}
            if rnd.random() < 0.15:
                f["reproducer"] = rnd.choice([{}, None, "x", [1]])
            v = V.Verification(rnd.choice([V.CONFIRMED, text(60)]), text(rnd.choice([10, 400, 3000])),
                               rnd.choice([None, "probe.x"]), rnd.choice([None, "REFUTED", text(100)]))
            a = rnd.choice([None, V.Anchor(rnd.choice([V.ANCHORED, text(70)]), text(rnd.choice([10, 600, 3000])))])
            art = rnd.choice([None, ART, text(500)])
            out = V.detail(f, v, a, art, secrets=("", text(8)))
            d = json.loads(out)
            out.encode("utf-8")
            canonical({"detail": out}).encode("utf-8")      # the journal's own line codec
            self.assertLessEqual(len(out), V.SUMMARY_MAX, n)
            self.assertLessEqual(set(d), KEYS, n)
            longest = max(longest, len(out))
        self.assertLessEqual(longest, V.SUMMARY_MAX)

    def test_the_worst_encoding_of_every_decisive_field_still_leaves_the_elastic_fields_room(self):
        f = finding(stimulus={"argv": [CONTROL * 500] * 50}, observable={"stdout": {"text": CONTROL * 500}, "exit_code": 3},
                    summary=CONTROL * 5000)
        f["id"] = f["reproducer"]["clause"] = CONTROL * 500
        v, a = verification(CONTROL * 500, CONTROL * 500, CONTROL * 500), anchor(CONTROL * 500, CONTROL * 500)
        longest_ref = V.Artifact("review-findings/" + "S" * 40 + ".9999999999.9999999999.json", "f" * 64, 9_999_999_999)
        for art in (longest_ref, CONTROL * 500):
            with self.subTest(art=type(art).__name__):
                text, d = stated(f, v, a, art)
                self.assertLessEqual(len(text), V.SUMMARY_MAX)
                self.assertEqual(sorted(d["elided"]), sorted(
                    ["anchor", "anchor_why", "clause", "finding", "observed", "observable", "stimulus", "summary",
                     "verification", "why"] + (["artifact_why"] if isinstance(art, str) else [])))
                self.assertGreater(len(d["summary"]) + len(d["reproducer"]["stimulus"])
                                   + len(d["reproducer"]["observable"]), 100)


class WhatIsStatedAndHowItIsMarked(unittest.TestCase):
    def test_observed_is_the_probes_verdict_and_is_absent_when_the_probe_gave_none(self):
        _, d = stated(v=V.Verification(V.UNVERIFIABLE, "no active probe observes x"), a=None, artifact=None)
        self.assertNotIn("observed", d)
        self.assertEqual((d["verification"], d["why"]), (V.UNVERIFIABLE, "no active probe observes x"))
        _, d = stated(v=verification(observed="SATISFIED", status=V.NOT_REPRODUCED), a=None, artifact=None)
        self.assertEqual(d["observed"], "SATISFIED")

    def test_the_anchor_is_stated_only_when_there_is_one(self):
        _, d = stated(a=None)
        self.assertFalse({"anchor", "anchor_why"} & set(d))

    def test_the_artifact_is_a_reference_or_the_reason_there_is_none_or_absent(self):
        _, d = stated(artifact=ART)
        self.assertEqual(d["artifact"], {"path": ART.path, "sha256": ART.sha256, "bytes": 4321})
        self.assertNotIn("artifact_why", d)
        _, d = stated(artifact="OSError: [Errno 28] No space left on device")
        self.assertEqual((d["artifact"], d["artifact_why"]), (None, "OSError: [Errno 28] No space left on device"))
        _, d = stated(artifact=None)
        self.assertFalse({"artifact", "artifact_why"} & set(d))

    def test_a_finding_without_a_reproducer_states_none_and_a_whole_summary(self):
        f = {"id": "FND-8", "severity": "CRITICAL", "summary": "looks wrong"}
        _, d = stated(f, V.Verification(V.UNVERIFIABLE, "no reproducer: the finding states no observable behaviour"),
                      a=None, artifact=None)
        self.assertEqual(d, {"finding": "FND-8", "severity": "critical", "summary": "looks wrong", "clause": None,
                             "verification": V.UNVERIFIABLE, "why": "no reproducer: the finding states no observable "
                                                                    "behaviour", "reproducer": None})
        for malformed in ({}, None, "run it", ["x"]):
            with self.subTest(reproducer=malformed):
                self.assertIsNone(stated(finding(reproducer=malformed))[1]["reproducer"])

    def test_a_value_that_fits_is_whole_an_object_not_its_text(self):
        stimulus = {"argv": ["a", "b"], "workspace": {"<ws>/L": {"text": "x\n"}}, "pre": []}
        _, d = stated(finding(stimulus=stimulus))
        self.assertEqual(d["reproducer"]["stimulus"], stimulus)
        self.assertNotIn("elided", d)

    def test_a_clause_of_another_type_is_stated_as_text_and_none_stays_none(self):
        f = finding()
        f["reproducer"]["clause"] = {"a": 1}
        self.assertEqual(stated(f)[1]["clause"], '{"a": 1}')
        f["reproducer"]["clause"] = None
        self.assertIsNone(stated(f)[1]["clause"])
        self.assertIsNone(stated({"id": "x"}, V.Verification(V.UNVERIFIABLE, "x"), a=None)[1]["clause"])

    def test_the_characters_of_the_reviewer_are_kept(self):
        _, d = stated(finding(summary="tệp thiếu → snapshot must exit 3"))
        self.assertEqual(d["summary"], "tệp thiếu → snapshot must exit 3")
        text, _ = stated(finding(summary="tệp thiếu → snapshot must exit 3"))
        self.assertNotIn("\\u", text)

    def test_the_marker_counts_characters_of_the_text_not_of_its_encoding(self):
        summary = '"' * 3000          # each is two characters once encoded
        _, d = stated(finding(summary=summary, stimulus={"argv": []}))
        self.assertEqual(len(d["summary"]) + d["elided"]["summary"], 3000)
        self.assertLess(len(d["summary"]), 1500)

    def test_the_statement_is_deterministic_in_its_key_order(self):
        text, d = stated()
        self.assertEqual(text, json.dumps(d, ensure_ascii=False, sort_keys=True))


class TextThatIsNotUtf8AndKeysThatAreNotStrings(unittest.TestCase):
    """json.loads yields a lone surrogate from a model's "\\ud800"; the journal line is canonical(...).encode("utf-8")
    and failed on the old statement (measured: UnicodeEncodeError, a crashed story). A reproducer with keys of two
    types raised TypeError in sort_keys."""

    def assert_statable(self, f, **kw):
        text, d = stated(f, **kw)
        text.encode("utf-8")
        canonical({"detail": text}).encode("utf-8")
        self.assertLessEqual(len(text), V.SUMMARY_MAX)
        return d

    def test_a_lone_surrogate_anywhere_is_written_as_its_escape(self):
        f = finding(summary="bad \ud800 char", stimulus={"argv": ["\udfff"], "\ud800": 1})
        f["id"] = "id-\ud83d"
        d = self.assert_statable(f, v=verification(reason="why \ud800"), a=anchor(reason="a \udc00"))
        self.assertEqual(d["summary"], "bad \\ud800 char")
        self.assertEqual(d["finding"], "id-\\ud83d")
        self.assertEqual(d["why"], "why \\ud800")
        self.assertEqual(d["reproducer"]["stimulus"], {"argv": ["\\udfff"], "\\ud800": 1})

    def test_keys_that_are_not_strings_are_stated_by_type_and_never_raise(self):
        d = self.assert_statable(finding(stimulus={1: "a", "b": 2, None: 3, (1, 2): 4, 2.5: 5}))
        self.assertEqual(sorted(d["reproducer"]["stimulus"]),
                         sorted(["<int>1", "b", "<NoneType>None", "<tuple>(1, 2)", "<float>2.5"]))

    def test_values_that_are_not_json_data_are_stated_as_their_repr(self):
        d = self.assert_statable(finding(stimulus={"a": float("nan"), "b": {1, 2}, "c": b"x", "d": float("inf")}))
        self.assertEqual(d["reproducer"]["stimulus"], {"a": "nan", "b": "{1, 2}", "c": "b'x'", "d": "inf"})

    def test_a_structure_nested_deeper_than_any_grammar_is_stated_with_a_marker_not_a_traceback(self):
        deep = cur = []
        for _ in range(5000):
            cur.append([])
            cur = cur[0]
        d = self.assert_statable(finding(stimulus={"argv": deep}))
        self.assertIn("nested deeper than", json.dumps(d))

    def test_two_keys_that_become_one_are_both_kept(self):
        out, n = V.redacted({"a": 1, "<int>1": 2, 1: 3})
        self.assertEqual((sorted(out.values()), n), ([1, 2, 3], 0))
        out, n = V.redacted({SECRET: 1, V.REDACTED: 2}, (SECRET,))
        self.assertEqual((sorted(out.values()), n, SECRET in json.dumps(out)), ([1, 2], 1, False))


class SecretsAreOutBeforeAnythingIsCut(unittest.TestCase):
    """The owner's second named case: content that holds a secret. The statement is journaled and printed into the
    developer's prompt: a secret in it is a leak (measured on 3dc827b: a secret in an OCR comment's stimulus reached
    RUN.json, the journal and the retry prompt). It is replaced before the cut: one that straddles a bound is not left
    half there."""

    def assert_clean(self, text):
        self.assertNotIn(SECRET, text)
        self.assertNotIn(SECRET[:6], text)      # not half of it either

    def test_a_secret_is_replaced_wherever_the_statement_carries_prose_of_the_reviewer_or_the_probe(self):
        f = finding(stimulus={"argv": ["--key", SECRET], "stdin": {"text": f"k={SECRET}"}, SECRET: 1},
                    summary=f"uses {SECRET}", observable={"stdout": {"contains": [SECRET]}, "exit_code": 3})
        f["id"] = f"id-{SECRET}"
        f["reproducer"]["clause"] = f"R-9/3 {SECRET}"
        f["reproducer"]["subject"] = {"kind": "cli_invocation", "locator": f"a:{SECRET}"}
        text, d = stated(f, verification(reason=f"probe saw {SECRET}"), anchor(reason=f"outcome {SECRET}"),
                         artifact=f"OSError: {SECRET}", secrets=(SECRET,))
        self.assert_clean(text)
        self.assertEqual(d["why"], f"probe saw {V.REDACTED}")
        self.assertEqual(d["anchor_why"], f"outcome {V.REDACTED}")
        self.assertEqual(d["reproducer"]["stimulus"]["argv"], ["--key", V.REDACTED])
        self.assertIn(V.REDACTED, d["reproducer"]["stimulus"])      # the key
        self.assertEqual(d["artifact_why"], f"OSError: {V.REDACTED}")
        self.assertEqual(d["finding"], f"id-{V.REDACTED}")

    def test_a_secret_that_straddles_the_cut_is_not_half_leaked(self):
        """Every offset: some of them put the cut of the stimulus inside the secret — redacting after the cut would
        leave its first characters."""
        for pad in range(300, 1000, 7):
            with self.subTest(pad=pad):
                stimulus = {"argv": ["x" * pad + SECRET + "y" * 5000]}
                text, d = stated(finding(stimulus=stimulus), secrets=(SECRET,))
                self.assert_clean(text)
                self.assertIn("stimulus", d["elided"])
                canon = json.dumps({"argv": ["x" * pad + V.REDACTED + "y" * 5000]}, ensure_ascii=False, sort_keys=True)
                self.assertEqual(d["elided"]["stimulus"], len(canon) - len(d["reproducer"]["stimulus"]))

    def test_a_secret_straddling_a_decisive_fields_own_bound_is_not_half_leaked(self):
        for bound, field in ((V.WHY_MAX, "why"), (V.FINDING_MAX, "finding"), (V.WHY_MAX, "anchor_why")):
            for pad in range(bound - len(SECRET) - 2, bound + 2):
                with self.subTest(field=field, pad=pad):
                    text = "x" * pad + SECRET + "tail"
                    f, v, a = finding(), verification(), anchor()
                    if field == "why":
                        v = verification(reason=text)
                    elif field == "anchor_why":
                        a = anchor(reason=text)
                    else:
                        f["id"] = text
                    out, d = stated(f, v, a, secrets=(SECRET,))
                    self.assert_clean(out)
                    want = "x" * pad + V.REDACTED + "tail"      # what the cut is made of: the text, redacted first
                    self.assertEqual(d[field], want[:bound])
                    self.assertEqual(d.get("elided", {}).get(field, 0), max(0, len(want) - bound))

    def test_the_longest_secret_goes_first_and_an_empty_or_missing_one_is_ignored(self):
        text, _ = stated(finding(summary="a SECRETLONG b"), secrets=("SECRET", "SECRETLONG", "", None))
        self.assertIn(f"a {V.REDACTED} b", json.loads(text)["summary"])
        text, d = stated(finding(summary="a b"), secrets=("", None))
        self.assertEqual(d["summary"], "a b")

    def test_the_marker_is_the_one_the_session_streams_carry(self):
        from aisef2.app import client
        self.assertEqual(V.REDACTED.encode("utf-8"), client.REDACTED)


class Redacted(unittest.TestCase):
    def test_it_returns_plain_data_and_how_many_secrets_it_replaced(self):
        value = {"a": [SECRET, ("x", SECRET)], "k" + SECRET: {"deep": f"{SECRET}-{SECRET}"}, "n": 3, "t": True, "z": None}
        out, n = V.redacted(value, (SECRET,))
        self.assertEqual(n, 5)
        self.assertEqual(out, {"a": [V.REDACTED, ["x", V.REDACTED]], "k" + V.REDACTED: {"deep": f"{V.REDACTED}-{V.REDACTED}"},
                               "n": 3, "t": True, "z": None})
        self.assertEqual(json.loads(json.dumps(out)), out)

    def test_the_input_is_not_changed_and_no_secret_means_no_count(self):
        value = {"a": [SECRET]}
        out, n = V.redacted(value)
        self.assertEqual((n, value, out), (0, {"a": [SECRET]}, {"a": [SECRET]}))
        self.assertIsNot(out["a"], value["a"])

    def test_a_secret_that_contains_another_is_replaced_whole(self):
        out, n = V.redacted("x ABCDEFGH y", ("ABCD", "ABCDEFGH"))
        self.assertEqual((out, n), (f"x {V.REDACTED} y", 1))


class FitMeasuresTheEncoding(unittest.TestCase):
    def test_widths_and_the_count_of_what_was_left_out(self):
        self.assertEqual(V._fit("abcdef", 4), ("abcd", 2))
        self.assertEqual(V._fit("abcdef", 6), ("abcdef", 0))
        self.assertEqual(V._fit("abcdef", 100), ("abcdef", 0))
        self.assertEqual(V._fit('a"b"c', 4), ('a"b', 2))                  # a quote is two
        self.assertEqual(V._fit("ab\ncd", 3), ("ab", 3))                  # a newline is two
        self.assertEqual(V._fit("a" + CONTROL * 3, 13), ("a" + CONTROL * 2, 1))   # a control character is six
        self.assertEqual(V._fit("é中\U0001f600", 2), ("é中", 1))     # a character is one, whatever its bytes
        self.assertEqual(V._fit("abc", 0), ("", 3))
        self.assertEqual(V._fit("", 5), ("", 0))

    def test_the_cut_prefix_always_encodes_within_the_room(self):
        rnd = random.Random(5)
        for _ in range(200):
            text = "".join(rnd.choice(['a', '"', "\\", "\n", CONTROL, "é"]) for _ in range(rnd.randint(0, 80)))
            room = rnd.randint(0, 120)
            shown, left = V._fit(text, room)
            self.assertLessEqual(len(json.dumps(shown, ensure_ascii=False)) - 2, room)
            self.assertEqual(len(shown) + left, len(text))
            self.assertTrue(text.startswith(shown))
            if left:     # the next character would not have fit
                self.assertGreater(len(json.dumps(text[:len(shown) + 1], ensure_ascii=False)) - 2, room)


class AnArtifactReferenceHasAShape(unittest.TestCase):
    """The statement's bound relies on the reference's shape; a reference of another shape cannot be built."""

    def test_a_reference_is_a_path_inside_the_directory_a_sha256_and_a_size(self):
        V.Artifact("review-findings/S-1.2.3.json", "0" * 64, 0)
        bad = (("review-findings/../RUN.json", "0" * 64, 1), ("review-findings/a/b.json", "0" * 64, 1),
               ("/review-findings/a.json", "0" * 64, 1), ("review-findings/a.txt", "0" * 64, 1),
               ("sessions/a.json", "0" * 64, 1), ("review-findings/" + "a" * 90 + ".json", "0" * 64, 1),
               ("review-findings/a.json", "0" * 63, 1), ("review-findings/a.json", "G" * 64, 1),
               ("review-findings/a.json", "0" * 64, -1), ("review-findings/a.json", "0" * 64, 10 ** 10),
               ("review-findings/a.json", "0" * 64, True), ("review-findings/a.json", "0" * 64, "5"))
        for args in bad:
            with self.subTest(args=args), self.assertRaises(ValueError):
                V.Artifact(*args)


if __name__ == "__main__":
    unittest.main()
