"""PM-8 (PROBE-DIAGNOSTIC-GAP-001) through `aisef run`: what a probe saw of a proof that was not SATISFIED, kept for the
operator (owner decision 2026-10-15, "PM-8: duyệt B, chỉ cho người vận hành").

One real run, offline (the fake client of test_app_run writes a calc `add` that subtracts; the real python_callable_v2
probe, the real journal, manifest and `--verify`): attempt 1 is refuted, attempt 2 is refuted, the story rolls back.
What is asserted is what the operator relies on, and what must not change:

* the files: one per executed evaluation that was not SATISFIED — the probe's own detail (the value the subject
  returned, which the sealed record `{behavior_verdict: REFUTED}` and every prompt lack), the criteria it answers, the
  sealed record's digest — and none for the expected state of what the story introduces, at its parent;
* the binding: each file names the `probe/evaluated` row of the journal that holds its record; the manifest lists it;
  `--verify` accepts the run and refuses a changed, renamed, foreign, unbound or removed file — also when the manifest
  is rewritten to match;
* the limit: same-user, not enforced — said by RUN.json and by every file, with no claim that the developer cannot read
  them; 0700/0600; outside every checkout;
* no authority: the story's outcomes, the delivery verdict, the journal's rows and the developer's prompts are what a
  run without the tap produces; a developer's retry prompt holds nothing of the directory or of what it keeps;
* fail-open: an artifact that cannot be written (or a context that cannot be read) changes no outcome, is counted and
  named in RUN.json, and is a note — not a refutation — in `--verify`;
* a review reproducer's observation, at the finding's place in the finder's list, bound to the finding's artifact —
  whatever JSON type the finder gave the finding's id (the gate row carries it as text);
* a write that fails after its sibling was made leaves the sibling, counted and named — a note in `--verify`, never a
  refutation of a run that delivered.

Pins aisef2/app/diagnostics.py, aisef2/app/run.py::probe_factories, ::story_where, ::evidence_manifest, ::execute,
aisef2/app/adapters.py::Reviewer.review, ::Reviewer._verify, aisef2/app/review_verify.py::verify (`entries`),
aisef2/app/verify.py::verify"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import shutil
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
from aisef2.arch.enums import Owner  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from tests.v2 import test_app_run as base  # noqa: E402

DIR = "probe-observations"
#: the developer's `add` subtracts: the probe's observation is `returned: -1`, which nothing else of the run holds
WRONG = "def sub(a, b):\n    return a - b\n\n\ndef add(a, b):\n    return a - b\n"
#: the fake client of test_app_run, writing every prompt it is given to prompts.jsonl beside itself
LOGGING = base.FAKE_CLIENT.replace(
    'mode = pathlib.Path(__file__).with_name("mode").read_text()\n',
    'mode = pathlib.Path(__file__).with_name("mode").read_text()\n'
    'with pathlib.Path(__file__).with_name("prompts.jsonl").open("a") as f:\n'
    '    f.write(json.dumps({"title": title, "prompt": argv[-1]}) + "\\n")\n', 1)
#: the claims the module's limit must never make (it states what is not enforced, never that nobody can read)
CLAIM = re.compile(r"cannot (be )?read|can ?not (be )?read|not readable|unreadable|inaccessible|hidden from|"
                   r"developer (can|could) ?not", re.I)
LIGHT = ("RUN.json", "RUN.started.json", "EVIDENCE.json", "run", "sessions", "preflight", "review-findings", DIR)


def untapped(sink, where) -> dict:
    """What `run.probe_factories` was before PM-8: each catalog factory, called as it is."""
    return {e.probe_id: (lambda on_range, scratch, f=e.factory: f(on_range=on_range, scratch=scratch))
            for e in catalog.CATALOG}


class Scene:
    """A calc project, a fake client writing `add`, and the means to run it into a named directory of `tmp`."""

    def __init__(self, tmp: pathlib.Path, add: str = WRONG, limit: int = 1) -> None:
        self.tmp = tmp
        self.baseline = base.make_repo(tmp / "source")
        self.project = bundle.load(base.project_bundle(self.baseline))
        self.settings = settings.load({**base.SETTINGS, "limits": {o.value: limit for o in Owner}})
        self.client = tmp / "client" / "opencode"
        self.client.parent.mkdir()
        self.client.write_text(f"#!{sys.executable}\nADD = {add!r}\nTEST = {base.TEST!r}\n" + LOGGING)
        self.client.chmod(0o755)
        (self.client.parent / "mode").write_text("write")

    def review(self, findings: list) -> None:
        (self.client.parent / "review.json").write_text(json.dumps({"findings": findings}), encoding="utf-8")

    def run(self, name: str, **patches) -> dict:
        (self.client.parent / "prompts.jsonl").write_text("", encoding="utf-8")      # each run's prompts alone
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, base.client_config(self.tmp)))
            stack.enter_context(mock.patch.object(ad, "scanner", lambda: ad.NoScanner()))
            for attr, value in patches.items():
                stack.enter_context(mock.patch.object(R, attr, value))
            rec = R.execute(self.project, self.settings, self.tmp / "source", self.tmp / name, transport=base.provider(),
                            client_exe=str(self.client), cals=base.calibrations())
        self.prompts = [json.loads(x) for x in (self.client.parent / "prompts.jsonl").read_text().splitlines()]
        return rec

    def events(self, name: str):
        return format3.reconstruct((self.tmp / name / "run" / "journals" / "aisef-run.jsonl").read_text("utf-8")).events

    def light(self, name: str, to: str) -> pathlib.Path:
        """A copy of the run's evidence files (what `--verify` reads; the repository aside)."""
        dst = self.tmp / to
        dst.mkdir()
        for rel in LIGHT:
            src = self.tmp / name / rel
            if src.exists():
                (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst / rel)
        return dst


def rewrite_manifest(out: pathlib.Path) -> None:
    """The manifest as an operator with write access could make it match the run directory as it now is."""
    (out / "EVIDENCE.json").write_text(json.dumps(R.evidence_manifest(out), indent=1, sort_keys=True) + "\n",
                                       encoding="utf-8")


class FailingOs:
    """`os` as the diagnostics module sees it, with the named functions made to fail (the sibling is made, the rename is
    not: a full disk, a lock on Windows)."""

    def __init__(self, **failing) -> None:
        self._failing = failing

    def __getattr__(self, name):
        return self._failing.get(name) or getattr(os, name)


def normalized(events) -> list:
    """The journal's rows as a run that differs in nothing but time and commit ids has them."""
    return [(e.type, e.data.get("story_id"), e.data.get("criterion_id"), (e.data.get("record") or {}).get("result"),
             e.data.get("code")) for e in events]


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class ARefutedProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._t.cleanup)
        cls.tmp = pathlib.Path(cls._t.name).resolve()
        cls.scene = Scene(cls.tmp)
        cls.rec = cls.scene.run("out")
        cls.out = cls.tmp / "out"
        cls.prompts = cls.scene.prompts
        cls.events = cls.scene.events("out")
        cls.files = sorted((cls.out / DIR).glob("*.json"))
        cls.docs = [json.loads(p.read_text(encoding="utf-8")) for p in cls.files]

    # ----------------------------------------------------------------------------------------------- the files

    def test_the_run_refuted_and_rolled_back_the_story(self):
        self.assertEqual((self.rec["story_outcomes"], self.rec["delivery_verdict"]), ({"S1": ["RETRY", "ROLLBACK"]}, "FAIL"))

    def test_each_executed_evaluation_that_was_not_satisfied_has_its_file_with_what_the_probe_saw(self):
        # attempt 1 and 2, the implementer's and the verifier's evaluation of the one obligation at the candidate
        self.assertEqual([p.name for p in self.files], ["S1.1.p1.json", "S1.1.p2.json", "S1.2.p1.json", "S1.2.p2.json"])
        for d in self.docs:
            with self.subTest(file=f"S1.{d['attempt']}.p{d['index']}"):
                self.assertEqual((d["format"], d["origin"], d["story_id"], d["criteria"], d["at_parent"]),
                                 ("aisef-v2-probe-observation/1", "proof", "S1", ["C-ADD"], False))
                self.assertEqual(d["observation"]["kind"], "OBSERVED")
                self.assertEqual(d["observation"]["verdict"], "REFUTED")
                self.assertEqual(d["observation"]["detail"]["returned"], -1)    # the value: in no record, in no prompt
                self.assertEqual((d["observation"]["elided"], d["observation"]["detail_chars"] > 0), (0, True))
                self.assertEqual(d["expected"], "SATISFIED")
                self.assertEqual(d["result"], {"behavior_verdict": "REFUTED", "reason": None})
                self.assertEqual((d["probe_id"], d["enforcement"], d["redacted"]), ("probe.python_callable_v2", "PARTIAL", 0))

    def test_the_sealed_record_and_the_journal_do_not_hold_what_the_file_does(self):
        rows = [e.data for e in self.events if e.type == "probe/evaluated"
                and e.data["record"]["result"]["behavior_verdict"] == "REFUTED"]
        self.assertEqual(len(rows), len(self.docs))
        self.assertNotIn("returned", repr(rows))

    def test_each_file_names_the_probe_record_the_journal_holds(self):
        keys = ("spec_id", "probe_id", "probe_digest", "revision", "enforcement")
        held = [(e.data["story_id"], *(e.data["record"][k] for k in keys), dict(e.data["record"]["result"]))
                for e in self.events if e.type == "probe/evaluated"]
        for d in self.docs:
            self.assertIn((d["story_id"], *(d[k] for k in keys), d["result"]), held, d["spec_id"])

    def test_the_expected_state_of_what_the_story_introduces_at_its_parent_is_not_a_finding(self):
        begin = next(e.data["parent"] for e in self.events if e.type == "story/begin")
        at_parent = [e.data["record"] for e in self.events
                     if e.type == "probe/evaluated" and e.data["record"]["revision"] == begin]
        # measured: `add` is not there at the parent (INDETERMINATE: the subject is required), the expected state…
        self.assertEqual([r["result"]["behavior_verdict"] for r in at_parent][:1], ["INDETERMINATE"])
        self.assertFalse([d for d in self.docs if d["revision"] == begin])      # …and not kept as a finding

    # ----------------------------------------------------------------------------------------------- the limit

    def test_RUN_json_says_what_is_and_is_not_enforced_and_how_many(self):
        d = json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))["diagnostics"]
        self.assertEqual((d["dir"], d["audience"], d["access"]), (DIR, "operator", "same-user, not enforced"))
        self.assertEqual((d["written"], d["not_written"], d["dropped"], d["failures"]), (4, 0, 0, []))
        self.assertEqual(d["permissions"], "directory 0700, files 0600")
        self.assertTrue(d["authority"].startswith("none"))
        self.assertEqual({doc["diagnostics_access"] for doc in self.docs}, {"same-user, not enforced"})

    def test_nothing_it_says_claims_the_developer_cannot_read_it(self):
        said = [json.dumps(json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))["diagnostics"]),
                *(p.read_text(encoding="utf-8") for p in self.files), self.module_text()]
        for text in said:
            self.assertIsNone(CLAIM.search(text), CLAIM.search(text) and text[max(0, CLAIM.search(text).start() - 60):][:160])

    @staticmethod
    def module_text() -> str:
        return (ROOT / "aisef2" / "app" / "diagnostics.py").read_text(encoding="utf-8")

    def test_the_directory_is_private_and_in_no_checkout(self):
        folder = self.out / DIR
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual({p.stat().st_mode & 0o777 for p in self.files}, {0o600})
        self.assertEqual(sorted(p for p in self.out.rglob(DIR)), [folder])      # not in a worktree, nor the clone
        for checkout in ("repo", "work", "test-python", "sessions", "preflight", "run"):
            self.assertFalse(folder.is_relative_to(self.out / checkout), checkout)
        self.assertNotIn(DIR, base.git(self.out / "repo", "ls-tree", "-r", "--name-only", "main"))

    # --------------------------------------------------------------------------------------------- the binding

    def test_the_manifest_lists_every_file_by_its_sha256(self):
        import hashlib
        manifest = json.loads((self.out / "EVIDENCE.json").read_text(encoding="utf-8"))["files"]
        for p in self.files:
            self.assertEqual(manifest[f"{DIR}/{p.name}"], hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(R.anchor_in(self.out), R.anchor_of(R.evidence_manifest(self.out)))

    def test_verification_accepts_the_run_as_it_is(self):
        v = verify(self.scene.project, self.out)
        self.assertEqual((v["verdict"], v["problems"], v["notes"], v["delivery_verdict"]), ("VERIFIED", [], [], "FAIL"))

    def test_a_changed_file_is_refuted_by_the_manifest(self):
        copy = self.scene.light("out", "changed")
        p = copy / DIR / "S1.1.p1.json"
        p.write_bytes(p.read_bytes().replace(b'"returned": -1', b'"returned": -2'))
        v = verify(self.scene.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("evidence manifest does not match" in x and "S1.1.p1.json" in x for x in v["problems"]),
                        v["problems"])

    def test_a_file_whose_record_the_journal_does_not_hold_is_refuted_even_with_the_manifest_rewritten(self):
        copy = self.scene.light("out", "unbound")
        p = copy / DIR / "S1.1.p1.json"
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["result"] = {"behavior_verdict": "SATISFIED", "reason": None}      # what the journal's record does not say
        p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        rewrite_manifest(copy)
        v = verify(self.scene.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("S1.1.p1.json names a probe record" in x and "none of the journal's" in x
                            for x in v["problems"]), v["problems"])

    def test_a_file_of_another_spec_probe_revision_or_level_than_its_record_is_refuted(self):
        for field, value in (("spec_id", "PPS-" + "1" * 64), ("revision", "f" * 40), ("probe_digest", "0" * 64),
                             ("probe_id", "probe.other"), ("enforcement", "FULL"), ("story_id", "S2")):
            with self.subTest(field=field):
                copy = self.scene.light("out", f"other-{field}")
                p = copy / DIR / "S1.2.p2.json"
                doc = json.loads(p.read_text(encoding="utf-8"))
                doc[field] = value
                p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                rewrite_manifest(copy)
                v = verify(self.scene.project, copy)
                self.assertEqual(v["verdict"], "REFUTED")
                self.assertTrue(any(x.startswith("diagnostic artifact probe-observations/S1.2.p2.json") for x in v["problems"]),
                                (field, v["problems"]))

    def test_a_renamed_file_or_one_this_release_does_not_write_is_refuted(self):
        copy = self.scene.light("out", "renamed")
        (copy / DIR / "S1.1.p1.json").rename(copy / DIR / "S1.1.p9.json")
        (copy / DIR / "stray.json").write_text("{}", encoding="utf-8")
        rewrite_manifest(copy)
        v = verify(self.scene.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("S1.1.p9.json is not named for its story, attempt and place" in x for x in v["problems"]),
                        v["problems"])
        self.assertTrue(any("stray.json is not a file this release writes" in x for x in v["problems"]), v["problems"])

    def test_a_removed_file_is_refuted_by_the_manifest_and_by_the_count_the_record_states(self):
        copy = self.scene.light("out", "removed")
        (copy / DIR / "S1.2.p2.json").rename(copy / "taken-away.json")      # no longer where the manifest has it
        v = verify(self.scene.project, copy)
        self.assertTrue(any("evidence manifest does not match" in x for x in v["problems"]), v["problems"])
        rewrite_manifest(copy)      # the operator's rewrite hides it from the manifest; the record's count does not
        v = verify(self.scene.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("RUN.json states 4 written, the directory holds 3" in x for x in v["problems"]), v["problems"])

    def test_a_copy_without_the_directory_is_not_this_runs_evidence(self):
        copy = self.scene.light("out", "without")
        (copy / DIR).rename(copy / "taken-away")
        v = verify(self.scene.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("evidence manifest does not match" in x for x in v["problems"]), v["problems"])

    # ----------------------------------------------------------------------------------------------- no authority

    def test_a_run_without_the_tap_decides_exactly_as_this_one_did(self):
        rec = self.scene.run("untapped", probe_factories=untapped)
        self.assertFalse((self.tmp / "untapped" / DIR).exists())
        for key in ("story_outcomes", "delivery_verdict", "delivery_blocked_by", "story_errors", "budget_stop"):
            self.assertEqual(rec[key], self.rec[key], key)
        self.assertEqual(rec["budget"]["spent"], self.rec["budget"]["spent"])
        self.assertEqual(normalized(self.scene.events("untapped")), normalized(self.events))
        # and the developer is told exactly what it is told with the tap (a commit id differs between two runs)
        def told(prompts):
            return [re.sub(r"\b[0-9a-f]{12,40}\b", "<sha>", p["prompt"]) for p in prompts]
        self.assertEqual(told(self.scene.prompts), told(self.prompts))
        self.assertEqual(verify(self.scene.project, self.tmp / "untapped")["verdict"], "VERIFIED")

    def test_a_retry_prompt_holds_nothing_of_the_directory_or_of_what_it_keeps(self):
        dev = [p["prompt"] for p in self.prompts if p["title"].startswith("developer")]
        self.assertEqual(len(dev), 2)
        self.assertIn("A previous attempt of this story was not accepted", dev[1])      # a retry prompt it is
        for text in dev:
            for banned in (DIR, str(self.out), "probe-observation", "diagnostics", "returned"):
                self.assertNotIn(banned, text, banned)

    # ----------------------------------------------------------------------------------------------- fail-open

    def test_an_artifact_that_cannot_be_written_changes_nothing_and_is_named(self):
        from aisef2.app import diagnostics as D
        with mock.patch.object(D.Sink, "_keep", side_effect=OSError("no space left on device")):
            rec = self.scene.run("unwritable")
        out = self.tmp / "unwritable"
        self.assertFalse((out / DIR).exists())
        for key in ("story_outcomes", "delivery_verdict", "delivery_blocked_by"):
            self.assertEqual(rec[key], self.rec[key], key)
        self.assertEqual(normalized(self.scene.events("unwritable")), normalized(self.events))
        d = rec["diagnostics"]
        self.assertEqual((d["written"], d["not_written"]), (0, 4))
        self.assertEqual([f["story_id"] for f in d["failures"]], ["S1"] * 4)
        self.assertTrue(all("OSError: no space left on device" in f["why"] for f in d["failures"]))
        v = verify(self.scene.project, out)
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []))
        self.assertTrue(any("4 probe observation(s) could not be written" in n for n in v["notes"]), v["notes"])

    def test_a_write_that_fails_after_its_sibling_was_made_leaves_it_and_is_a_note_not_a_refutation(self):
        from aisef2.app import diagnostics as D

        def full_disk(*args, **kw):
            raise OSError(28, "No space left on device")
        with mock.patch.object(D, "os", FailingOs(replace=full_disk)):
            rec = self.scene.run("halfwritten")
        out = self.tmp / "halfwritten"
        # nothing removed (INV-MUTATION-AUTHORITY): the four siblings stay, none of them an artifact
        self.assertEqual(sorted(p.name for p in (out / DIR).iterdir()),
                         [f"S1.{a}.p{n}.json.tmp" for a in (1, 2) for n in (1, 2)])
        for key in ("story_outcomes", "delivery_verdict", "delivery_blocked_by"):
            self.assertEqual(rec[key], self.rec[key], key)
        self.assertEqual((rec["diagnostics"]["written"], rec["diagnostics"]["not_written"]), (0, 4))
        v = verify(self.scene.project, out)
        self.assertEqual((v["verdict"], v["problems"], v["delivery_verdict"]), ("VERIFIED", [], "FAIL"))
        self.assertEqual(len([n for n in v["notes"] if ".json.tmp" in n]), 4, v["notes"])
        self.assertTrue(any("4 probe observation(s) could not be written" in n for n in v["notes"]), v["notes"])

    def test_a_context_that_cannot_be_read_changes_nothing_and_is_named(self):
        def broken(run, project, story):
            def where():
                raise RuntimeError("the journal could not be read")
            return where
        rec = self.scene.run("blind", story_where=broken)
        for key in ("story_outcomes", "delivery_verdict", "delivery_blocked_by"):
            self.assertEqual(rec[key], self.rec[key], key)
        # every evaluation of the run (the parent's too: with no context nothing can be told to be expected)
        evaluated = [e for e in self.events if e.type == "probe/evaluated"]
        self.assertEqual((rec["diagnostics"]["written"], rec["diagnostics"]["not_written"]), (0, len(evaluated)))
        self.assertIn("RuntimeError: the journal could not be read", rec["diagnostics"]["failures"][0]["why"])
        self.assertEqual(verify(self.scene.project, self.tmp / "blind")["verdict"], "VERIFIED")


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class AReviewersReproducer(unittest.TestCase):
    """The finder's reproducer (python_callable `add(2, 2)` returns 5) is verified by the kernel's own probe; the
    developer's `add` is right, so the probe REFUTES the reviewer's expectation — and what it saw is kept."""

    FINDING = {"id": "F1", "blocking": False, "severity": "high", "summary": "add(2, 2) must be 5",
               "reproducer": {"clause": "R-ADD/1", "subject": {"kind": "python_callable", "locator": "app.calc:add"},
                              "stimulus": {"args": [2, 2]}, "observable": {"returns": 5, "within_s": 10}}}
    #: the second place of the finder's list: a different finding, a different value seen (add(1, 1) returns 2)
    SECOND = {**FINDING, "id": "F2", "summary": "add(1, 1) must be 5",
              "reproducer": {**FINDING["reproducer"], "stimulus": {"args": [1, 1]}}}

    @classmethod
    def setUpClass(cls) -> None:
        cls._t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._t.cleanup)
        cls.tmp = pathlib.Path(cls._t.name).resolve()
        cls.scene = Scene(cls.tmp, add=base.ADD)
        cls.scene.review([cls.FINDING, cls.SECOND])
        cls.rec = cls.scene.run("out")
        cls.out = cls.tmp / "out"

    def test_the_story_is_delivered_and_the_finding_did_not_block(self):
        self.assertEqual((self.rec["story_outcomes"], self.rec["delivery_verdict"]), ({"S1": ["COMMIT"]}, "PASS"))
        # the proof held: none; the finder's two reproducers, at their two places
        self.assertEqual(sorted(p.name for p in (self.out / DIR).glob("*")), ["S1.1.r0.json", "S1.1.r1.json"])

    def test_the_file_holds_what_the_probe_saw_of_the_reproducer_at_the_findings_place(self):
        for index, (finding, returned) in enumerate((("F1", 4), ("F2", 2))):
            with self.subTest(index=index):
                d = json.loads((self.out / DIR / f"S1.1.r{index}.json").read_text(encoding="utf-8"))
                self.assertEqual((d["origin"], d["story_id"], d["attempt"], d["index"], d["finding"]),
                                 ("review", "S1", 1, index, finding))
                self.assertEqual((d["observation"]["kind"], d["observation"]["verdict"]), ("OBSERVED", "REFUTED"))
                self.assertEqual(d["observation"]["detail"]["returned"], returned)
                self.assertEqual(d["probe_id"], "probe.python_callable_v2")
                self.assertNotIn("criteria", d)
                kept = json.loads((self.out / "review-findings" / f"S1.1.{index}.json").read_text(encoding="utf-8"))
                self.assertEqual((kept["finding"]["id"], kept["finding"]["verification"]["status"], kept["revision"]),
                                 (finding, "CONFIRMED", d["revision"]))
        self.assertEqual(self.rec["diagnostics"]["written"], 2)

    def test_verification_binds_it_to_the_finding_and_refuses_another(self):
        self.assertEqual(verify(self.scene.project, self.out)["verdict"], "VERIFIED")
        copy = self.scene.light("out", "moved")
        p = copy / DIR / "S1.1.r0.json"
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["finding"] = "F2"      # the second finding's name at the first place: each place holds its own finding
        p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        rewrite_manifest(copy)
        v = verify(self.scene.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertEqual([x for x in v["problems"] if "S1.1.r1.json" in x], [])
        self.assertTrue(any("S1.1.r0.json: the finding it observes is not at review-findings/S1.1.0.json" in x
                            for x in v["problems"]), v["problems"])


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class AFindersIdThatIsNotAString(unittest.TestCase):
    """A finder writes the id it likes. The gate row carries `str(id)` (adapters.Reviewer.review), the finding's own
    artifact the id as JSON: the observation's file is bound to the finding by the one text both say, not by a type."""

    ABSENT = object()

    def test_the_run_is_verified_whatever_json_value_the_finding_s_id_is(self):
        cases = (("a string", "F1", "F1"), ("a number", 5, "5"), ("a fraction", 1.5, "1.5"), ("null", None, "None"),
                 ("no id at all", self.ABSENT, "None"), ("a list", [1, 2], "[1, 2]"))
        for name, value, shown in cases:
            with self.subTest(id=name), tempfile.TemporaryDirectory() as t:
                tmp = pathlib.Path(t).resolve()
                scene = Scene(tmp, add=base.ADD)
                finding = {**AReviewersReproducer.FINDING}
                if value is self.ABSENT:
                    finding.pop("id")
                else:
                    finding["id"] = value
                scene.review([finding])
                rec = scene.run("out")
                out = tmp / "out"
                self.assertEqual((rec["story_outcomes"], rec["delivery_verdict"]), ({"S1": ["COMMIT"]}, "PASS"))
                d = json.loads((out / DIR / "S1.1.r0.json").read_text(encoding="utf-8"))
                self.assertEqual(d["finding"], shown)
                kept = json.loads((out / "review-findings" / "S1.1.0.json").read_text(encoding="utf-8"))["finding"]
                self.assertEqual(str(kept.get("id")), shown)      # the artifact holds it as JSON: not always text
                v = verify(scene.project, out)
                self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), name)


if __name__ == "__main__":
    unittest.main()
