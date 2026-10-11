"""V2.1 mutation survivors, batch T14b: what `aisef2/app/run.py` states of the bundle and the settings in the RunSpec
(`layers_of`), and which stories the journal shows refused (`unfinished`).

`layers_of` is the one source of the RunSpec's settings for the run (`runspec_of` -> the `runspec_hash` journaled in
`run/spec-resolved`) and for `--verify` (`verify._runspec_problems` re-derives the hash from the record's settings with
the same function). A same-code run -> verify round trip therefore cannot see a changed key set, key name or label:
only a check of the mapping itself, of what the hash binds, or of a verify of another bundle or other settings can.
Offline: the fake client and the fake provider of test_app_run (the run-level tests are POSIX-only for that reason)."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.arch.enums import Enforcement, Owner  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402
from aisef2.runtime.capability import verified  # noqa: E402
from aisef2.runtime.runspec import resolve  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

REV = "a" * 40
#: the e2e settings with values that tell the layers apart (every limit and the turn cap differ from one another)
LIMITS = {o.value: n for n, o in enumerate(Owner)}
SETTINGS = {**e2e.SETTINGS, "limits": LIMITS, "max_turns_per_session": 7}


def _event(seq: int, kind: str, **data) -> dict:
    return {"seq": seq, "type": kind, "data": data}


def _runspec_hash(project, st) -> str:
    """The hash of a RunSpec whose settings are the layers of `project` under `st` (the capabilities do not vary)."""
    caps = [verified("kernel", b"kernel", Enforcement.FULL)]
    return resolve(caps, R.layers_of(project, st), REV).runspec_hash


class LayersOfIsTheFrozenMapping(unittest.TestCase):
    """Pins aisef2/app/run.py::layers_of [1, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 41, 44, 47, 50, 53,
    56, 59, 62, 65]: the RunSpec's settings are exactly nine layers (and `review` only when the settings name one),
    each {value, layer} — the key, the value and the provenance label of every one are identity data, hashed into
    `runspec_hash`, so a run directory written by one release re-derives under the next only while they stand."""

    def test_the_layers_are_exactly_the_nine_with_their_values_and_labels(self):
        p, st = bundle.load(e2e.project_bundle(REV)), settings.load(SETTINGS)
        expected = {
            "workload": {"value": "calc", "layer": "bundle"},
            "bundle_digest": {"value": p.digest, "layer": "bundle"},
            "plan_hash": {"value": p.plan.plan_hash, "layer": "plan"},
            "requirements_sha256": {"value": p.requirements_sha256, "layer": "bundle"},
            "settings_sha256": {"value": hashlib.sha256(json.dumps(st.content, sort_keys=True).encode()).hexdigest(),
                                "layer": "settings"},
            "limits": {"value": LIMITS, "layer": "settings"},
            "budget": {"value": SETTINGS["budget"], "layer": "settings"},
            "max_turns_per_session": {"value": 7, "layer": "settings"},
            "timeouts_s": {"value": {k: float(v) for k, v in SETTINGS["timeouts_s"].items()}, "layer": "settings"}}
        self.assertEqual(R.layers_of(p, st), expected)
        spec = resolve([verified("kernel", b"kernel", Enforcement.FULL)], R.layers_of(p, st), REV)
        self.assertEqual(plain(spec.settings), {"revision": {"value": REV, "layer": "run"}, **expected})


class TheRunSpecHashBindsBundleAndSettings(unittest.TestCase):
    """Pins aisef2/app/run.py::layers_of [2, 5]: `runspec_hash` changes with the bundle's digest and with the settings
    document's digest. The digest layers are the only ones that bind what the other layers do not name: the
    description, contracts, approvals, facts, stories and product roots of the bundle; provider, route, client,
    client_env, preflight, prices and confinement of the settings."""

    def test_a_bundle_that_differs_only_beyond_name_plan_and_requirements_has_another_hash(self):
        doc = e2e.project_bundle(REV)
        base = bundle.load(doc)
        self.assertEqual(_runspec_hash(base, settings.load(SETTINGS)), _runspec_hash(bundle.load(doc), settings.load(SETTINGS)))
        for field, edit in (("description", {"description": "The same calculator, described otherwise."}),
                            ("stories", {"stories": {"S1": {"depends_on": [], "tests": ["tests/test_other.py"]}}}),
                            ("product_roots", {"product_roots": ["app"]})):
            with self.subTest(field):
                other = bundle.load({**doc, **edit})
                self.assertEqual((other.name, other.plan.plan_hash, other.requirements_sha256),
                                 (base.name, base.plan.plan_hash, base.requirements_sha256))
                self.assertNotEqual(_runspec_hash(other, settings.load(SETTINGS)), _runspec_hash(base, settings.load(SETTINGS)))

    def test_settings_that_differ_only_where_no_other_layer_looks_have_another_hash(self):
        p = bundle.load(e2e.project_bundle(REV))
        base = settings.load(SETTINGS)
        provider = {**SETTINGS["provider"], "served_model": "model-2"}
        for field, edit in (("client_env", {"client_env": ["AISEF_OPERATOR_VARIABLE"]}), ("provider", {"provider": provider}),
                            ("preflight", {"preflight": {"chat_probes": 3}})):
            with self.subTest(field):
                st = settings.load({**SETTINGS, **edit})
                rest = lambda s: {k: v for k, v in R.layers_of(p, s).items() if k != "settings_sha256"}  # noqa: E731
                self.assertEqual(rest(st), rest(base))      # no other layer sees the edit
                self.assertNotEqual(_runspec_hash(p, st), _runspec_hash(p, base))


class TheReviewPolicyIsALayerOnlyWhenTheSettingsNameIt(unittest.TestCase):
    """Pins aisef2/app/run.py::layers_of [10, 67, 68, 73, 76]: with `review` in the settings the RunSpec states it as
    given under the key `review`, labelled `settings` — the policy, the floor and the finder with its pinned binary are
    what decides whether a finding blocks delivery; without it the layers are the nine of 2.0.0, so a 2.0.0 run's
    RunSpec re-derives unchanged."""

    NINE = ("workload", "bundle_digest", "plan_hash", "requirements_sha256", "settings_sha256", "limits", "budget",
            "max_turns_per_session", "timeouts_s")

    def layers(self, **extra) -> dict:
        return R.layers_of(bundle.load(e2e.project_bundle(REV)), settings.load({**SETTINGS, **extra}))

    def test_without_a_review_in_the_settings_the_layers_are_the_nine_of_2_0_0(self):
        self.assertEqual(sorted(self.layers()), sorted(self.NINE))

    def test_a_review_the_settings_name_is_stated_as_given(self):
        with tempfile.TemporaryDirectory() as t:
            exe = os.fspath(pathlib.Path(t).resolve() / "ocr")
            named = {
                "model finder by default": {"policy": "fix-loop", "min_severity": "high"},
                "the 2.0.0 defaults, named": {"policy": "advisory", "min_severity": "critical"},
                "model finder, explicitly": {"policy": "fix-loop", "min_severity": "medium", "finder": "model"},
                "ocr finder": {"policy": "fix-loop", "min_severity": "low", "finder": "ocr",
                               "ocr": {"exe": exe, "sha256": "ab" * 32, "timeout_min": 7, "max_tokens": 4096}}}
            for label, review in named.items():
                with self.subTest(label):
                    layers = self.layers(review=review)
                    self.assertEqual(sorted(layers), sorted([*self.NINE, "review"]))
                    self.assertEqual(layers["review"], {"value": review, "layer": "settings"})
                    unnamed = {k: v for k, v in self.layers().items() if k != "settings_sha256"}
                    self.assertEqual({k: layers[k] for k in unnamed}, unnamed)     # naming one moves no other layer


class UnfinishedIsWhatTheJournalShowsBegunMoreOftenThanEnded(unittest.TestCase):
    """Pins aisef2/app/run.py::unfinished [4, 7, 10, 15, 16]: a story with more `story/begin` than `story/end` events
    is an attempt that broke off, and is named (its id); balanced and over-ended stories are not. `verify` turns each
    named story into a refusal that fails the delivery verdict — it reads whether there is one, never the order."""

    def test_a_story_begun_and_not_ended_is_named(self):
        self.assertEqual(R.unfinished([_event(0, "story/begin", story_id="S1")]), ["S1"])

    def test_a_story_begun_and_ended_is_not(self):
        self.assertEqual(R.unfinished([_event(0, "story/begin", story_id="S1"), _event(1, "story/end", story_id="S1")]), [])

    def test_only_the_stories_that_were_not_ended_are_named(self):
        events = [_event(0, "story/begin", story_id="S2"), _event(1, "story/begin", story_id="S3"),
                  _event(2, "story/begin", story_id="S1"), _event(3, "story/end", story_id="S3")]
        self.assertCountEqual(R.unfinished(events), ["S1", "S2"])     # which and how many; no reader takes the order

    def test_begins_and_ends_are_counted_not_collected(self):
        again = [_event(0, "story/begin", story_id="S1"), _event(1, "story/begin", story_id="S1"),
                 _event(2, "story/end", story_id="S1")]
        self.assertEqual(R.unfinished(again), ["S1"])
        self.assertEqual(R.unfinished([*again, _event(3, "story/end", story_id="S1")]), [])

    def test_an_end_without_a_begin_is_not_a_refusal_and_other_events_are_ignored(self):
        events = [_event(0, "gate/decision"), _event(1, "story/end", story_id="S3"),
                  _event(2, "story/commit", story_id="S4"), _event(3, "story/retry", story_id="S5")]
        self.assertEqual(R.unfinished(events), [])

    def test_a_committed_story_that_never_ended_fails_the_delivery(self):
        p = bundle.load(e2e.project_bundle(REV))
        begun = [_event(0, "gate/decision"), _event(1, "story/begin", story_id="S1"), _event(2, "story/commit", story_id="S1")]
        ended = [*begun, _event(3, "story/end", story_id="S1")]
        for events, verdict in ((ended, "PASS"), (begun, "FAIL")):
            with self.subTest(verdict):
                errors = [{"story": s, "error": "begun and never ended in the journal"} for s in R.unfinished(events)]
                v, blocked, _ = R.delivery(p, events, {"S1": ["COMMIT"]}, None, errors)
                self.assertEqual(v, verdict)
                self.assertEqual(bool(blocked), verdict == "FAIL")


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class VerifyRederivesTheRunFromTheJournal(unittest.TestCase):
    """One finished run (a story delivered), then forged record, bundle or journal, each refuted by `verify` alone.
    Pins aisef2/app/run.py::layers_of [2, 5] (the journal binds the exact bundle and the whole settings document) and
    aisef2/app/run.py::unfinished [4, 7, 10, 15, 16] (a story begun and never ended is refused, whatever RUN.json
    says). Each forgery re-makes the evidence manifest, so only the journal's own evidence can refute it."""

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        tmp = pathlib.Path(t.name).resolve()
        baseline = e2e.make_repo(tmp / "source")
        cls.baseline = baseline
        cls.project = bundle.load(e2e.project_bundle(baseline))
        client = tmp / "client" / "opencode"
        client.parent.mkdir()
        client.write_text(f"#!{sys.executable}\nADD = {e2e.ADD!r}\nTEST = {e2e.TEST!r}\n" + e2e.FAKE_CLIENT)
        client.chmod(0o755)
        (client.parent / "mode").write_text("write")
        with mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), mock.patch.dict(os.environ, e2e.client_config(tmp)):
            cls.rec = R.execute(cls.project, settings.load(e2e.SETTINGS), tmp / "source", tmp / "out",
                                client_exe=str(client), cals=e2e.calibrations(), transport=e2e.provider())
        cls.out = tmp / "out"

    def setUp(self) -> None:
        self.journal_path = self.out / "run" / "journals" / "aisef-run.jsonl"
        saved = {p: p.read_bytes() for p in (self.out / "RUN.json", self.out / R.MANIFEST, self.journal_path)}
        for path, data in saved.items():
            self.addCleanup(path.write_bytes, data)
        self.pristine = json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))

    def reseal(self, rec: dict) -> None:
        """RUN.json becomes `rec` and the evidence manifest is re-made over the directory as it now is."""
        (self.out / "RUN.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        (self.out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(self.out), indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")

    def test_the_run_is_what_the_scenario_says(self):
        self.assertEqual((self.rec["delivery_verdict"], self.rec["story_outcomes"]), ("PASS", {"S1": ["COMMIT"]}))
        v = verify(self.project, self.out)
        self.assertEqual((v["verdict"], v["problems"], v["delivery_verdict"]), ("VERIFIED", [], "PASS"))

    def test_a_run_is_tied_to_the_exact_bundle_by_the_journal_not_only_by_the_record(self):
        doc = e2e.project_bundle(self.baseline)
        doc["description"] = "The same calculator, described otherwise."
        other = bundle.load(doc)
        self.assertEqual((other.name, other.plan.plan_hash, other.requirements_sha256),
                         (self.project.name, self.project.plan.plan_hash, self.project.requirements_sha256))
        self.reseal({**self.pristine, "bundle_digest": other.digest})      # the record's own field forged along with it
        v = verify(other, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertTrue(any("runspec hash" in p for p in v["problems"]), v["problems"])

    def test_settings_no_other_layer_carries_are_bound_to_the_journal_too(self):
        edits = {"client_env": lambda s: {**s, "client_env": ["AISEF_OPERATOR_VARIABLE"]},
                 "provider.served_model": lambda s: {**s, "provider": {**s["provider"], "served_model": "model-2"}}}
        for field, edit in edits.items():
            with self.subTest(field):
                self.reseal({**self.pristine, "settings": edit(self.pristine["settings"])})
                v = verify(self.project, self.out)
                self.assertEqual(v["verdict"], "REFUTED", v)
                self.assertTrue(any("runspec hash" in p for p in v["problems"]), v["problems"])

    def test_a_story_the_journal_shows_begun_and_never_ended_is_refused_whatever_the_record_says(self):
        events = format3.reconstruct(self.journal_path.read_text(encoding="utf-8")).events
        ends = [e.seq for e in events if e.type == "story/end"]
        self.assertEqual(len(ends), 1)
        lines = self.journal_path.read_bytes().splitlines(keepends=True)
        data = b"".join(lines[:ends[0]])        # the run broke off after the commit: a clean prefix, the chain intact
        self.journal_path.write_bytes(data)
        journal = {**self.pristine["journal"], "sha256": hashlib.sha256(data).hexdigest(), "lines": data.count(b"\n")}
        self.reseal({**self.pristine, "journal": journal})                 # the record still says PASS
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(v["delivery_verdict"], "FAIL")
        self.assertTrue(any("re-derives FAIL" in p for p in v["problems"]), v["problems"])


if __name__ == "__main__":
    unittest.main()
