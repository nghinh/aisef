"""V2.1 kills3 TO1: `aisef bundle continue` names the story that carries the committed work with a name that no
story still to run has.

The carried story is called CARRIED; when a story of the bundle already has that name `continue_from` appends `_`
until none has. A carried story that took the name of a story still to run would overwrite it in the continuation
(its tests, its dependencies, its obligation), and the operator's next `aisef run` would prove the wrong thing. The
bundle here is the operator's own naming: the story that commits is S1 and the two stories still to run are CARRIED
(the default name) and CARRIED_ (its first fallback), so that the name is free only after two steps.

Pins aisef2/app/bundle_cli.py::continue_from [20] (`while carried in project.stories` negated: with the name taken
the loop does not run and the carried story IS the story still to run; with the name free it never ends - the
campaign-2 TIMEOUT of the two existing kill files, which only ever build the free-name case) and [57] (the loop's
step emptied: the name never changes). The membership tests of `project.stories` are counted and a loop that does
not end is cut with an AssertionError after PROBES, so a variant that never settles fails here at once instead of
waiting out the runner's 900 s (the real loop settles in 3 probes).
Offline: the fake client and provider of test_app_run (a script started by its shebang: POSIX only)."""

from __future__ import annotations

import copy
import dataclasses
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
from aisef2.app import bundle, bundle_cli, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from tests.v2 import test_app_run as base  # noqa: E402
from tests.v2 import test_v21_continue_usage as two_stories  # noqa: E402

TAKEN = {"CARRIED", "CARRIED_"}      # the stories still to run: no name for the carried story
PROBES = 25


class _Probed(dict):
    """A project's `stories` that counts the membership tests made on it."""

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.probes = 0

    def __contains__(self, key) -> bool:
        self.probes += 1
        if self.probes > PROBES:
            raise AssertionError(f"{PROBES} membership tests of the bundle's stories and the carried story's name is "
                                 "still not settled: the loop does not end")
        return super().__contains__(key)


class _BoundedBundle:
    """`aisef2.app.bundle` as `bundle_cli` sees it, but `load` hands back a project whose `stories` is a `_Probed`."""

    def __getattr__(self, name):
        return getattr(bundle, name)

    @staticmethod
    def load(data):
        project = bundle.load(data)
        return dataclasses.replace(project, stories=_Probed(project.stories))


def authoring() -> dict:
    """The two-story calc bundle of test_v21_continue_usage (S1 adds, committed by the run; its S2 multiplies, renamed
    CARRIED), and a third story CARRIED_ (divides) after it: the fake client never writes `mul` or `div`."""
    doc = copy.deepcopy(two_stories.AUTHORING)
    doc["requirements"].append({"id": "R-DIV", "text": "div", "source": "docs/requirements.md 3.1"})
    doc["contracts"].append({"id": "BC-DIV", "requirement_ids": ["R-DIV"],
                             "subject": {"kind": "python_callable", "locator": "app.calc:div"},
                             "stimulus": {"args": [6, 3]}, "observable": {"returns": 2, "within_s": 10},
                             "polarity": "MUST_HOLD", "subject_absence": "REQUIRES_SUBJECT", "rationale": "6 / 3"})
    doc["stories"]["CARRIED"] = doc["stories"].pop("S2")
    doc["stories"]["CARRIED_"] = {"depends_on": ["CARRIED"], "tests": ["tests/test_div.py"], "criteria": [
        {"id": "C-DIV", "contract": "BC-DIV", "role": "INTRODUCE", "depends_on": ["C-MUL"], "why": "CARRIED_ divides",
         "facts": {"requirement": "R-DIV", "section": "§3", "clause": "3.1", "clause_text": "div", "subject": "div"}}]}
    return doc


AUTHORING = authoring()
ADDS, MULS, DIVS = (AUTHORING["stories"][k] for k in ("S1", "CARRIED", "CARRIED_"))
ADD_CRITERION, MUL_CRITERION, DIV_CRITERION = (x["criteria"][0]["id"] for x in (ADDS, MULS, DIVS))


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class CarriedStoryName(unittest.TestCase):
    """One real run (S1 commits, CARRIED does not), continued as often as a test needs: a continuation never writes
    into the run it continues."""

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        tmp = pathlib.Path(t.name).resolve()
        source = tmp / "source"
        base.make_repo(source)
        doc, _ = bundle_cli.seal(AUTHORING, repo=source)
        for contract in AUTHORING["contracts"]:
            doc = bundle_cli.approve(doc, contract["id"], "human:t", 1.0)
        client = tmp / "client" / "opencode"
        client.parent.mkdir()
        client.write_text(f"#!{sys.executable}\nADD = {base.ADD!r}\nTEST = {base.TEST!r}\n" + base.FAKE_CLIENT)
        client.chmod(0o755)
        (client.parent / "mode").write_text("write")
        cls.doc, cls.run_dir = doc, tmp / "first"
        with mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), mock.patch.dict(os.environ, base.client_config(tmp)):
            cls.record = R.execute(bundle.load(doc), settings.load(base.SETTINGS), source, cls.run_dir,
                                   transport=base.provider(), client_exe=str(client), cals=base.calibrations())

    def continued(self) -> tuple[dict, dict]:
        with mock.patch.object(bundle_cli, "B", _BoundedBundle()):
            try:
                return bundle_cli.continue_from(self.doc, self.run_dir)
            except bundle.BundleError as e:
                self.fail(f"a bundle whose stories still to run are CARRIED and CARRIED_ has no continuation: {e}")

    def test_the_run_stopped_after_the_story_that_adds(self):
        """The premise of the other tests: S1 committed, CARRIED did not (and CARRIED_ waits for it)."""
        outcomes = self.record["story_outcomes"]
        self.assertEqual(outcomes["S1"], ["COMMIT"])
        self.assertNotIn("COMMIT", outcomes.get("CARRIED", []) + outcomes.get("CARRIED_", []))

    def test_the_carried_story_takes_a_name_no_story_still_to_run_has(self):
        """The report's `carried_as` is what the operator and the next run read; the default name and its first
        fallback are the stories still to run here, so the carried work takes a third name: no story is lost (or
        merged into the carried work) and the continuation is itself a bundle. Pins continue_from [20, 57]."""
        out, report = self.continued()
        self.assertEqual(report["carried"], ["S1"])
        self.assertNotIn(report["carried_as"], TAKEN)
        self.assertEqual(set(out["stories"]), {report["carried_as"], *TAKEN})
        self.assertIn(report["carried_as"], bundle.load(out).stories)      # the continuation is itself a bundle

    def test_the_stories_still_to_run_keep_their_names_their_tests_and_their_obligations(self):
        """A carried story that took the name `CARRIED` or `CARRIED_` would overwrite the story still to run: its tests
        and the obligation it introduces would be proved as the carried work. Pins continue_from [20]."""
        out, report = self.continued()
        carried = report["carried_as"]
        project = bundle.load(out)
        self.assertEqual({o.criterion_id: (o.story_id, o.role.value) for o in project.plan.obligations},
                         {ADD_CRITERION: (carried, "VERIFY"), MUL_CRITERION: ("CARRIED", "INTRODUCE"),
                          DIV_CRITERION: ("CARRIED_", "INTRODUCE")})
        self.assertEqual(project.stories[carried], {"depends_on": [], "tests": ADDS["tests"]})
        self.assertEqual(project.stories["CARRIED"], {"depends_on": [carried], "tests": MULS["tests"]})
        self.assertEqual(project.stories["CARRIED_"], {"depends_on": ["CARRIED"], "tests": DIVS["tests"]})
        self.assertEqual(report["remaining"], ["CARRIED", "CARRIED_"])


if __name__ == "__main__":
    unittest.main()
