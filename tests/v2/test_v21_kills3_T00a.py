"""Kill tests for the survivors of `aisef2/app/bundle_cli.py::main` (campaign 2, batch T00a).

What the command line of `aisef bundle` promises its operator and the scripts around it, driven through
`bundle_cli.main([...])` — the entry point `aisef bundle` itself calls:

* exit status is the verdict channel (0 done / 1 lint NOT_READY / 2 refused input): a missing required argument is the
  parser's usage error (status 2, the flag named), never a crash that wears status 1 and never a quiet success; a
  document that is not a bundle is a refusal on stderr with status 2, whatever exception class refused it;
* `continue` is a registered command, writes the continuation, and prints the report where the override of an
  unidentified commit is recorded;
* `lint`/`explain` accept a bundle whatever the order of its members and refuse what is not one;
* `migrate` prints which file it wrote and the migration report (the only record of which specs were rebound).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
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
from aisef2.journal import format3  # noqa: E402
from tests.v2 import test_app_run as base  # noqa: E402
from tests.v2 import test_v21_continue_usage as cu  # noqa: E402

LEDGERLOCK_2_0_0 = ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json"


def call(*argv) -> tuple[int, str, str]:
    """(exit status, stdout, stderr) of `aisef bundle ARGV`."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bundle_cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def dump(path: pathlib.Path, doc) -> pathlib.Path:
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return path


_EXAMPLE: dict = {}


def example() -> dict:
    """`init` -> a git repository of its files -> `seal` (BC-ADD unapproved) and BC-ADD approved: built once per
    process, read-only for the tests (they write their outputs into their own directory)."""
    if not _EXAMPLE:
        tmp = tempfile.TemporaryDirectory()
        unittest.addModuleCleanup(tmp.cleanup)
        d = pathlib.Path(tmp.name).resolve() / "calc-1-story"
        code, _, err = call("init", "--example", "calc-1-story", "--out", d)
        assert code == 0, err
        base.git(d / "repo", "init", "-q", "-b", "main")
        base.git(d / "repo", "add", "-A")
        base.git(d / "repo", "commit", "-q", "-m", "baseline")
        code, _, err = call("seal", d / "authoring.json", "--repo", d / "repo", "--out", d / "sealed.json")
        assert code == 0, err
        doc = json.loads((d / "sealed.json").read_text(encoding="utf-8"))
        dump(d / "approved.json", bundle_cli.approve(doc, "BC-ADD", "human:t", 1.0))
        _EXAMPLE.update(dir=d, doc=doc, authoring=d / "authoring.json", repo=d / "repo", sealed=d / "sealed.json",
                        approved=d / "approved.json")
    return _EXAMPLE


class Work(unittest.TestCase):
    """A scratch directory per test: the outputs a command is given to write, and the proof that none was."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.work = pathlib.Path(t.name).resolve()
        self.ex = example()

    def listing(self) -> list[str]:
        return sorted(os.listdir(self.work))


class RequiredArgumentsAreTheParsersToRefuse(Work):
    """A command invoked without a required argument is refused by the parser: SystemExit(2), nothing written, and
    the usage error names `aisef bundle` and the missing flag. Pins aisef2/app/bundle_cli.py::main [54, 57, 61, 66, 68,
    69, 71, 78, 79, 83]: with one of them not required the command goes on (a crash on a None path with status 1, a
    refusal that blames something else, or — `approve` without `--approver` over an approved contract — a copy of the
    bundle written and status 0)."""

    def refused(self, argv, flag: str | None) -> str:
        before = self.listing()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as c:
            bundle_cli.main([str(a) for a in argv])
        self.assertEqual(c.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("aisef bundle", err.getvalue())      # which tool refused
        if flag is not None:
            self.assertIn(flag, err.getvalue())             # what is missing
        self.assertEqual(self.listing(), before)            # nothing was written
        return err.getvalue()

    def test_no_command_at_all(self):
        self.refused([], None)

    def test_init_without_out(self):
        self.refused(["init"], "--out")

    def test_seal_without_out(self):
        self.refused(["seal", self.ex["authoring"], "--repo", self.ex["repo"]], "--out")

    def test_approve_without_contract(self):
        self.refused(["approve", self.ex["sealed"], "--approver", "human:t", "--out", self.work / "o.json"], "--contract")

    def test_approve_without_approver_even_when_nothing_new_would_be_minted(self):
        # BC-ADD is approved already: approve() would create nothing and write a copy with `by: null`, status 0
        self.refused(["approve", self.ex["approved"], "--contract", "BC-ADD", "--out", self.work / "o.json"], "--approver")

    def test_approve_without_out(self):
        self.refused(["approve", self.ex["sealed"], "--contract", "BC-ADD", "--approver", "human:t"], "--out")

    def test_continue_without_from_run(self):
        self.refused(["continue", self.ex["approved"], "--out", self.work / "o.json"], "--from-run")

    def test_continue_without_out(self):
        self.refused(["continue", self.ex["approved"], "--from-run", self.work], "--out")

    def test_migrate_without_out(self):
        self.refused(["migrate", self.ex["sealed"]], "--out")


class InitDefaultsToTheShippedExample(Work):
    """`aisef bundle init --out DIR` (the documented first command: `--example` is optional) writes the calc-1-story
    example. Pins aisef2/app/bundle_cli.py::main [59]: with an empty default the example `.json` is not found and the
    first command is refused (status 2)."""

    def test_init_without_example_writes_calc_1_story(self):
        out = self.work / "start"
        code, _, err = call("init", "--out", out)
        self.assertEqual((code, err), (0, ""))
        shipped = json.loads((bundle_cli.EXAMPLES / "calc-1-story.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((out / "authoring.json").read_text(encoding="utf-8")), shipped["authoring"])
        for rel, text in shipped["repo"].items():
            self.assertEqual((out / "repo" / rel).read_text(encoding="utf-8").replace("\r\n", "\n"), text.replace("\r\n", "\n"))


class RefusedDocumentsAreRefusedWithStatusTwo(Work):
    """A JSON document that loads but is not a bundle that holds is a refusal on stderr — status 2, stdout empty,
    nothing written — whichever exception class refused it (a missing member, a value of the wrong JSON type, a seal
    that does not bind its content), and the line begins with the refusal marker `refused: ` that the other `aisef`
    commands use. Pins aisef2/app/bundle_cli.py::main [50, 51, 52, 53, 128, 146]: a KeyError/TypeError/ValueError
    that escapes is a traceback with status 1 (the code a script reads as lint NOT_READY); a refusal that returns None
    is status 0 to the shell."""

    def refused(self, doc, expect: str, *, via: str = "approve") -> str:
        src = dump(self.work / "in.json", doc)
        out = self.work / "out.json"
        argv = {"approve": ["approve", src, "--contract", "BC-ADD", "--approver", "human:t", "--out", out],
                "lint": ["lint", src], "explain": ["explain", src]}[via]
        code, stdout, stderr = call(*argv)
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.startswith("refused: "), stderr)
        self.assertIn(expect, stderr)
        self.assertFalse(out.exists())
        return stderr

    def test_an_object_that_is_not_a_bundle_names_the_missing_member(self):
        self.refused({}, "KeyError")

    def test_a_document_that_is_not_an_object_names_the_type_error(self):
        self.refused([], "TypeError")

    def test_a_seal_that_does_not_bind_its_content_is_refused_by_name(self):
        edited = json.loads(json.dumps(self.ex["doc"]))
        edited["requirements"][0]["text"] = "something else than the text the hash binds"
        for via in ("approve", "lint", "explain"):
            with self.subTest(via):
                self.refused(edited, "ContractError", via=via)

    def test_a_bundle_error_refusal_carries_the_marker_and_the_object(self):
        code, stdout, stderr = call("approve", self.ex["sealed"], "--contract", "NO-SUCH-CONTRACT", "--approver", "human:t",
                                    "--out", self.work / "out.json")
        self.assertEqual((code, stdout), (2, ""))
        self.assertTrue(stderr.startswith("refused: "), stderr)
        self.assertIn("NO-SUCH-CONTRACT", stderr)
        self.assertFalse((self.work / "out.json").exists())


class LintAndExplainTakeABundleInAnyMemberOrder(Work):
    """`lint` and `explain` refuse what is not a bundle of this format (a JSON array, another format, a member too
    many or one under another name: status 2, no report, the expected format named) and accept a bundle whatever the
    order of its members (JSON member order carries no meaning; `run` loads such a file). Pins
    aisef2/app/bundle_cli.py::main [96, 122]."""

    def test_what_is_not_a_bundle_is_refused_by_both(self):
        sealed = self.ex["doc"]
        documents = {"an array": [], "another format": dict(sealed, format="aisef-v2-project/0"),
                     "an extra member": dict(sealed, extra="not a member of a bundle"),
                     # same count of members, one name different: the guard compares the names, not how many
                     "a member renamed": {("approvals_" if k == "approvals" else k): v for k, v in sealed.items()}}
        for command in ("lint", "explain"):
            for label, doc in documents.items():
                with self.subTest(command=command, document=label):
                    code, stdout, stderr = call(command, dump(self.work / "in.json", doc))
                    self.assertEqual((code, stdout), (2, ""))
                    self.assertTrue(stderr.startswith("refused: "), stderr)
                    self.assertIn(bundle.FORMAT, stderr)

    def test_the_order_of_the_members_changes_neither_status_nor_report(self):
        shuffled = dump(self.work / "reversed.json", dict(reversed(list(self.ex["doc"].items()))))
        stored = json.loads(shuffled.read_text(encoding="utf-8"))
        self.assertNotEqual(list(stored), sorted(stored))       # the fixture is not in the order the tools write
        for command, status in (("lint", 1), ("explain", 0)):    # the sealed bundle is unapproved: lint NOT_READY
            with self.subTest(command):
                want = call(command, self.ex["sealed"])
                self.assertEqual(want[0], status)
                self.assertEqual(call(command, shuffled), want)


class MigratePrintsWhatItWroteAndWhatItRebound(unittest.TestCase):
    """`aisef bundle migrate IN --out OUT` prints the file it wrote and the migration report — the only record of which
    specs were rebound from which release (the written file holds only the new plan). Pins
    aisef2/app/bundle_cli.py::main [99, 100, 109]."""

    def test_the_report_is_printed_with_the_path_written(self):
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t) / "migrated.json"
            code, stdout, stderr = call("migrate", LEDGERLOCK_2_0_0, "--out", out)
            self.assertEqual((code, stderr), (0, ""))
            self.assertTrue(out.exists())
            _, report = bundle_cli.migrate(json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8")))
            self.assertEqual(json.loads(stdout), {"written": str(out), **json.loads(json.dumps(report))})


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class ContinueThroughTheCommand(unittest.TestCase):
    """`aisef bundle continue B --from-run D --out O` over the real two-story calc run of test_v21_continue_usage
    (S1 committed, S2 did not): exit 0, the continuation written, and the report printed. Pins
    aisef2/app/bundle_cli.py::main [28, 43, 91, 92, 93, 120, 121, 138]: with the command unregistered, dispatched to
    another command's branch, unpacking the result wrongly, or printing a report without `written` / without its
    fields, the operator gets a usage error, another command's file, a refusal that blames the input, or no record of
    where the continuation is and what was left out."""

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        cls.tmp = pathlib.Path(t.name).resolve()
        base.make_repo(cls.tmp / "source")
        doc, _ = bundle_cli.seal(cu.AUTHORING, repo=cls.tmp / "source")
        for c in ("BC-ADD", "BC-MUL"):
            doc = bundle_cli.approve(doc, c, "human:t", 1.0)
        cls.doc = doc
        cls.bundle = dump(cls.tmp / "bundle.json", doc)
        client = cls.tmp / "client" / "opencode"
        client.parent.mkdir()
        client.write_text(f"#!{sys.executable}\nADD = {base.ADD!r}\nTEST = {base.TEST!r}\n" + base.FAKE_CLIENT)
        client.chmod(0o755)
        (client.parent / "mode").write_text("write")
        with mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), \
                mock.patch.dict(os.environ, base.client_config(cls.tmp)):
            rec = R.execute(bundle.load(doc), settings.load(base.SETTINGS), cls.tmp / "source", cls.tmp / "first",
                            transport=base.provider(), client_exe=str(client), cals=R.calibrations())
        assert rec["story_outcomes"]["S1"] == ["COMMIT"], rec
        cls.first = cls.tmp / "first"
        journal = format3.reconstruct((cls.first / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8"))
        cls.s1_commit = next(e.data["revision"] for e in journal.events if e.type == "story/commit")

    def target(self, name: str) -> pathlib.Path:
        return self.tmp / f"{self.id().rsplit('.', 1)[1]}-{name}"

    def test_continue_writes_the_continuation_and_prints_the_report(self):
        out = self.target("continued.json")
        code, stdout, stderr = call("continue", self.bundle, "--from-run", self.first, "--out", out)
        self.assertEqual((code, stderr), (0, ""))
        written = json.loads(out.read_text(encoding="utf-8"))
        project = bundle.load(written)                       # a bundle that holds, every seal re-checked
        self.assertEqual(sorted(project.stories), ["CARRIED", "S2"])      # S1's obligations carried, S2 as it was
        self.assertEqual(project.stories["S2"]["depends_on"], ["CARRIED"])
        self.assertEqual(project.plan.baseline, self.s1_commit)           # the journal's last commit
        self.assertEqual({o.criterion_id: (o.story_id, o.role.value) for o in project.plan.obligations},
                         {"C-ADD": ("CARRIED", "VERIFY"), "C-MUL": ("S2", "INTRODUCE")})
        printed = json.loads(stdout)
        self.assertEqual(printed["written"], str(out))
        self.assertEqual((printed["carried"], printed["remaining"], printed["baseline"]), (["S1"], ["S2"], self.s1_commit))
        doc, report = bundle_cli.continue_from(self.doc, self.first)       # read-only: the oracle for both
        self.assertEqual(written, json.loads(json.dumps(doc)))
        self.assertEqual(printed, {"written": str(out), **json.loads(json.dumps(report))})

    def test_the_override_of_unidentified_commits_is_recorded_in_the_printed_report(self):
        stray = self.tmp / "stray-run"
        shutil.copytree(self.first, stray, symlinks=True)
        (stray / "repo" / "stray.txt").write_text("an in-flight merge\n", encoding="utf-8")
        base.git(stray / "repo", "add", "-A")
        base.git(stray / "repo", "commit", "-q", "-m", "in flight")
        out = self.target("left-out.json")
        code, stdout, stderr = call("continue", self.bundle, "--from-run", stray, "--out", out)
        self.assertEqual((code, stdout), (2, ""))              # nothing identifies the commit: refused ...
        self.assertTrue(stderr.startswith("refused: "), stderr)
        self.assertIn("--leave-out-unidentified", stderr)      # ... naming the flag that continues without it
        self.assertFalse(out.exists())
        code, stdout, stderr = call("continue", self.bundle, "--from-run", stray, "--out", out, "--leave-out-unidentified")
        self.assertEqual((code, stderr), (0, ""))
        printed = json.loads(stdout)
        self.assertIs(printed["left_out_unidentified"], True)
        self.assertEqual(printed["baseline"], self.s1_commit)
        self.assertEqual([(i["operation"], i["identified"], i["subject"]) for i in printed["unconfirmed"]],
                         [("unknown", False, "in flight")])
        self.assertIsNotNone(printed["in_flight"])
        _, report = bundle_cli.continue_from(self.doc, stray, leave_out_unidentified=True)
        self.assertEqual(printed, {"written": str(out), **json.loads(json.dumps(report))})


if __name__ == "__main__":
    unittest.main()
