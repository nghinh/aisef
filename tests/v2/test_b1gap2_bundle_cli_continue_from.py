"""B1 gap wave 2: mutation kill tests for `aisef bundle continue` (bundle_cli.continue_from) — the survivors the audit
classed REAL_GAP or WEAK_ASSERT. One real run is made for the whole file (the fake client of test_app_run: S1 commits,
S2 does not), as in test_v21_kills3_T01b; a refused run is a `moved` directory (symlinks plus a rewritten record), and
the lineage-account texts are pinned with `lineage_account` mocked, as test_v21_continue_usage does. Offline: the fake
client and provider of test_app_run; nothing here starts a real client.

Pins aisef2/app/bundle_cli.py::continue_from (the kernel refusal's wording, the continuation plan's id, the carried
rationale's marker, and `run_parent_refused`: its restoration clause and the `; ` between unread reasons)."""

from __future__ import annotations

import copy
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, bundle_cli, lineage, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from tests.v2.test_app_run import ADD, FAKE_CLIENT, SETTINGS, TEST, client_config, make_repo, provider  # noqa: E402
from tests.v2.test_v21_continue_usage import AUTHORING  # noqa: E402

RECORD, STARTED = "RUN.json", R.STARTED

#: AUTHORING cut to its one committing story: the run this file continues from needs only S1 (the budget of the file is
#: seconds; what continue_from does with a story that did not commit is test_v21_continue_usage's, not pinned here)
AUTHORING1 = copy.deepcopy(AUTHORING)
del AUTHORING1["stories"]["S2"]
AUTHORING1["contracts"] = [c for c in AUTHORING1["contracts"] if c["id"] == "BC-ADD"]
AUTHORING1["requirements"] = [r for r in AUTHORING1["requirements"] if r["id"] == "R-ADD"]

#: the one run of the file: `tmp`, `doc` (sealed and approved), `first` (the run directory), `record` (RUN.json bytes)
#: and `cont` = continue_from(doc, first), computed once and read by every test of the success path
FX = types.SimpleNamespace()


def setUpModule() -> None:
    if os.name != "posix":
        raise unittest.SkipTest("the fake client is a script started by its shebang")
    holder = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(holder.cleanup)
    tmp = pathlib.Path(holder.name).resolve()
    make_repo(tmp / "source")
    doc, _ = bundle_cli.seal(AUTHORING1, repo=tmp / "source")
    doc = bundle_cli.approve(doc, "BC-ADD", "human:t", 1.0)
    client = tmp / "client" / "opencode"
    client.parent.mkdir()
    client.write_text(f"#!{sys.executable}\nADD = {ADD!r}\nTEST = {TEST!r}\n" + FAKE_CLIENT, encoding="utf-8")
    client.chmod(0o755)
    (client.parent / "mode").write_text("write", encoding="utf-8")
    with mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), mock.patch.dict(os.environ, client_config(tmp)):
        run = R.execute(bundle.load(doc), settings.load(SETTINGS), tmp / "source", tmp / "first", transport=provider(),
                        client_exe=str(client), cals=R.calibrations())
    assert run["story_outcomes"]["S1"] == ["COMMIT"], run["story_outcomes"]
    FX.tmp, FX.doc, FX.first = tmp, doc, tmp / "first"
    FX.record = (FX.first / RECORD).read_bytes()
    FX.cont = bundle_cli.continue_from(FX.doc, FX.first)


def account_with(unread: list[str]) -> dict:
    """A lineage account of the shape `continue_from` reads (the keys of test_v21_continue_usage's spend rows), its one
    run's evidence unread for the given reasons."""
    spend = {k: 0 for k in lineage.SPEND}
    row = {"run": str(FX.first), "recorded": True, "unaccounted": [], "unread": list(unread), "exact": False, **spend}
    return {"runs": [row], **spend, "unaccounted": [], "unread": list(unread), "total": None}


class AnotherKernelWording(unittest.TestCase):
    # kills: L983 string '): a new project, not a continuation' emptied
    def test_the_kernel_refusal_says_a_new_project_not_a_continuation(self):
        moved = pathlib.Path(tempfile.mkdtemp(dir=FX.tmp)) / "moved"
        moved.mkdir()
        for name in ("run", "repo"):
            os.symlink(FX.first / name, moved / name)
        record = dict(json.loads(FX.record), kernel_digest="0" * 40)
        (moved / RECORD).write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(FX.doc, moved)
        self.assertIn("another kernel", str(c.exception))
        self.assertIn("): a new project, not a continuation", str(c.exception))


class ContinuationPlan(unittest.TestCase):
    # kills: L1017 string '-continued' emptied
    def test_the_continuation_plan_id_is_the_parent_plan_id_plus_continued(self):
        doc, _ = FX.cont
        self.assertEqual(doc["plan"]["id"], FX.doc["plan"]["id"] + "-continued")
        self.assertNotEqual(doc["plan"]["id"], FX.doc["plan"]["id"])

    # kills: L1013 string 'carried: ' emptied
    def test_a_carried_obligation_rationale_begins_with_the_carried_marker(self):
        doc, report = FX.cont
        carried = [o for o in bundle.load(doc).plan.obligations if o.story_id == report["carried_as"]]
        self.assertEqual([o.criterion_id for o in carried], ["C-ADD"])
        for o in carried:
            self.assertTrue(o.ownership_rationale.startswith("carried: "), o.ownership_rationale)


class RunParentRefused(unittest.TestCase):
    """`run_parent_refused`, built when the lineage holds unread evidence: the account is mocked (the pattern of
    test_v21_continue_usage::test_spend_by_run...), so each wording is reached without damaging a run."""

    def refused(self, unread: list[str]) -> str:
        with mock.patch.object(lineage, "lineage_account", return_value=account_with(unread)):
            _, report = bundle_cli.continue_from(FX.doc, FX.first)
        self.assertIsInstance(report["run_parent_refused"], str)
        return report["run_parent_refused"]

    # kills: L1045 string " (a sessions directory, a session stream or the preflight's ledger that is gone comes back from such a copy); where that cannot be done this lineage cannot be continued (a run without --parent inherits nothing): " emptied
    def test_the_text_says_the_lineage_cannot_be_continued_where_restoration_cannot_be_done(self):
        text = self.refused(["evidence of the run is gone"])
        self.assertIn("comes back from such a copy", text)
        self.assertIn("this lineage cannot be continued (a run without --parent inherits nothing)", text)

    # kills: L1047 string '; ' emptied
    def test_two_unread_reasons_are_separated_never_fused(self):
        first, second = "first reason evidence gone", "second reason stream unreadable"
        text = self.refused([first, second])
        self.assertIn(f"{first}; {second}", text)


if __name__ == "__main__":
    unittest.main()
