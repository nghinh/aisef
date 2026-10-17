"""V2.1 (owner B-03 survivor audit, cluster `bundlecli`): four things `aisef bundle` told its operator that were wrong
for an input it was handed. Each is the requirement of the field's reader, not of a mutant.

* `continue`'s `next` is a COMMAND LINE the operator runs: it parses as the `aisef run` that continues the run, for a
  run directory whose path holds a space, a quote or a shell character — and is the text it always was for a path that
  needs no quoting.
* `continue`'s rationale for a carried obligation names the evidence anchor in its short form, or says the run had no
  manifest in full: the cut that shortens an anchor is not applied to the words that stand for its absence.
* `explain` reports a criterion's contract as approved only when it has a contract: a criterion whose obligation names
  a spec no contract of the bundle compiles to (a bundle of an earlier release not yet migrated, a contract that left
  the bundle) has `contract: null` — and has nothing that could be approved (`lint` lists it in
  `criteria_without_contract` and says NOT_READY).
* `lint` reports a bundle whose criterion cites a requirement by a LIST or an object: NOT_READY (exit 1) with the
  criterion named, not `refused: TypeError` (exit 2) and no report — the family of the `clause` fact
  (test_v21_defects_lint).

The runs are the real one-story run of the fake client of test_app_run, made once; the other run directories are
twins of it (its directories linked, its records copied). Offline: no provider request is made."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import pathlib
import shlex
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, bundle_cli, cli, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from tests.v2.test_app_run import (ADD, FAKE_CLIENT, SETTINGS, TEST, client_config, git, make_repo,  # noqa: E402
                                   project_bundle, provider)

LEDGERLOCK_2_0_0 = ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json"
POSIX = unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")

#: the one run of the file, built by setUpModule on a POSIX host: `tmp`, `doc` (its bundle, approved), `first` (the
#: run directory) and `anchor` (the evidence anchor of its manifest)
W = types.SimpleNamespace()


def setUpModule() -> None:
    if os.name != "posix":
        return
    holder = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(holder.cleanup)
    tmp = pathlib.Path(holder.name).resolve()
    doc = project_bundle(make_repo(tmp / "source"))
    client = tmp / "client" / "opencode"
    client.parent.mkdir()
    client.write_text(f"#!{sys.executable}\nADD = {ADD!r}\nTEST = {TEST!r}\n" + FAKE_CLIENT, encoding="utf-8")
    client.chmod(0o755)
    (client.parent / "mode").write_text("write", encoding="utf-8")
    with mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), mock.patch.dict(os.environ, client_config(tmp)):
        run = R.execute(bundle.load(doc), settings.load(SETTINGS), tmp / "source", tmp / "first", transport=provider(),
                        client_exe=str(client), cals=R.calibrations())
    if run["story_outcomes"] != {"S1": ["COMMIT"]}:
        raise RuntimeError(f"the fixture run is not the one these tests need: {run['story_outcomes']}")
    (tmp / "bundle.json").write_text(json.dumps(doc), encoding="utf-8")
    W.tmp, W.doc, W.first, W.anchor = tmp, doc, tmp / "first", R.anchor_in(tmp / "first")
    if not W.anchor:
        raise RuntimeError("the finished fixture run has no evidence manifest")


def twin(name: str, *, manifest: bool = True) -> pathlib.Path:
    """A run directory of its own, `name`, that is the real run seen as: its journal, clone and the evidence its record
    counts (the session streams and the preflight's ledger: a record that holds spend whose evidence is not there is a run
    whose cost is unknown, and `bundle continue` then sends the operator to restore it) linked, its record and start
    record copied, and its evidence manifest copied when `manifest` (a run killed before it wrote one without)."""
    d = pathlib.Path(tempfile.mkdtemp(dir=W.tmp)) / name      # a parent of its own: `name` is its last component
    d.mkdir()
    for link in ("run", "repo", "sessions", "preflight"):
        os.symlink(W.first / link, d / link)
    for kept in ("RUN.json", R.STARTED, *((R.MANIFEST,) if manifest else ())):
        shutil.copyfile(W.first / kept, d / kept)
    return d


def run_main(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bundle_cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


@POSIX
class NextIsACommandLine(unittest.TestCase):
    """`next` is what the operator pastes: an `aisef run` of the continuation in the run's own clone, `--parent` the
    run, whatever characters the run directory's path holds."""

    #: run directory name -> does a POSIX shell take it as one word as it is?
    NAMES = {"a-run": True, "a run directory": False, "it's a run": False, "cost $5 & `x`; (y) #z": False,
             "tab\there": False, "chạy-lần-1": True}

    def printed(self, run_dir: pathlib.Path) -> str:
        """`next` as `aisef bundle continue` prints it for `run_dir`."""
        out = pathlib.Path(tempfile.mkdtemp(dir=W.tmp)) / "continued.json"
        code, text, err = run_main("continue", W.tmp / "bundle.json", "--from-run", run_dir, "--out", out)
        self.assertEqual((code, err), (0, ""), text)
        return json.loads(text)["next"]

    def test_it_parses_as_the_aisef_run_that_continues_that_run(self):
        for name in self.NAMES:
            with self.subTest(run_directory=name):
                run_dir = twin(name)
                line = self.printed(run_dir)
                words = shlex.split(line.replace("<this bundle>", "BUNDLE.json"))
                self.assertEqual(words[:2], ["aisef", "run"], line)
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    try:
                        a = cli._parser().parse_args(words[2:])
                    except SystemExit:
                        self.fail(f"not an aisef run command line: {line!r}: {stderr.getvalue()}")
                self.assertEqual((a.project, a.parent, a.repo), (pathlib.Path("BUNDLE.json"), run_dir, run_dir / "repo"))
                self.assertIsNotNone(a.settings)
                self.assertIsNotNone(a.out)

    def test_a_path_that_needs_no_quoting_is_printed_as_it_always_was(self):
        for name, plain in self.NAMES.items():
            if plain:
                with self.subTest(run_directory=name):
                    run_dir = twin(f"plain-{name}")
                    self.assertEqual(self.printed(run_dir), f"aisef run --project <this bundle> --repo {run_dir / 'repo'} "
                                                            f"--parent {run_dir} --settings S --out NEW")


class ShellWord(unittest.TestCase):
    """The one place a path becomes a word of the printed command line (all platforms: the host is a parameter)."""

    def test_posix_leaves_a_plain_path_and_quotes_every_other(self):
        for text in ("/tmp/run1/repo", "run-2/repo", "a+b=c,d@e:f%g.h_i", "/home/dự-án/chạy", "run-\u0663/Ωmega_ß", "名前/日本語"):
            with self.subTest(plain=text):
                self.assertEqual(bundle_cli._shell_word(text, windows=False), text)
        for text in ("/tmp/a run", "it's", "$HOME/x", "a&b", "`x`", "a\nb", "a\tb", "~x", "a;b", "(x)", "a#b", "*", "a\\b",
                     'a"b', "a b's $c", "chạy lần 1", "\u00a0nbsp", "", "a!b", "{a,b}", "[ab]", "a?b", "a<b", "a>b", "a|b",
                     "a^b", "a\u2014b", "run \u0663"):
            with self.subTest(quoted=text):
                word = bundle_cli._shell_word(text, windows=False)
                self.assertNotEqual(word, text)
                self.assertEqual(shlex.split(word), [text])      # one word, the text itself

    def test_windows_wraps_a_path_with_whitespace_in_double_quotes_and_leaves_the_rest(self):
        self.assertEqual(bundle_cli._shell_word("C:\\Users\\x\\run1\\repo", windows=True), "C:\\Users\\x\\run1\\repo")
        self.assertEqual(bundle_cli._shell_word("C:\\Users\\Some One\\run 1\\repo", windows=True),
                         '"C:\\Users\\Some One\\run 1\\repo"')
        self.assertEqual(bundle_cli._shell_word("C:\\a\tb", windows=True), '"C:\\a\tb"')

    def test_the_host_is_the_default(self):
        self.assertEqual(bundle_cli._shell_word("/a b"), "'/a b'" if sys.platform != "win32" else '"/a b"')
        self.assertEqual(bundle_cli._shell_word(pathlib.PurePosixPath("/a/b"), windows=False), "/a/b")


@POSIX
class CarriedRationaleIsNotCutThroughAWord(unittest.TestCase):
    def carried(self, run_dir: pathlib.Path) -> tuple[dict, str]:
        """(the report, the ownership_rationale of the one carried obligation of the continuation of `run_dir`)."""
        doc, report = bundle_cli.continue_from(W.doc, run_dir)
        [o] = [o for o in bundle.load(doc).plan.obligations if o.story_id == report["carried_as"]]
        return report, o.ownership_rationale

    def test_a_run_without_a_manifest_says_so_in_full(self):
        report, text = self.carried(twin("no-manifest", manifest=False))
        self.assertIsNone(report["evidence_anchor"])
        self.assertIn("without a manifest", text)
        self.assertIn("C-ADD", text)      # which criterion the obligation is, after the anchor, as always

    def test_a_run_with_a_manifest_names_the_first_16_hex_digits_of_its_anchor(self):
        report, text = self.carried(W.first)
        self.assertEqual(report["evidence_anchor"], W.anchor)
        self.assertEqual(len(W.anchor), 64)
        self.assertIn(f"anchored {W.anchor[:16]} (C-ADD)", text)
        self.assertNotIn(W.anchor[:17], text)


class CriterionWithoutAContract(unittest.TestCase):
    """`explain`: `approved` is a statement about the criterion's contract. Without one there is none to be approved."""

    approved: dict      # calc-3-stories, sealed, every contract approved

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        d = pathlib.Path(t.name) / "calc"
        bundle_cli.init("calc-3-stories", d)
        for step in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "baseline")):
            git(d / "repo", *step)
        doc, _ = bundle_cli.seal(json.loads((d / "authoring.json").read_text(encoding="utf-8")), repo=d / "repo")
        for c in [c["id"] for c in doc["contracts"]]:
            doc = bundle_cli.approve(doc, c, "human:t", 1.0)
        cls.approved = doc

    @staticmethod
    def entries(doc: dict) -> dict[str, dict]:
        return {e["criterion"]: e for es in bundle_cli.explain(doc)["stories"].values() for e in es}

    def test_a_criterion_whose_contract_left_the_bundle_is_not_approved(self):
        doc = copy.deepcopy(self.approved)
        doc["contracts"] = [c for c in doc["contracts"] if c["id"] != "BC-STDLIB"]     # C-STDLIB-1's contract
        entry = self.entries(doc)["C-STDLIB-1"]
        self.assertIsNone(entry["contract"])
        self.assertIsNot(entry["approved"], True, entry)
        self.assertIsNone(entry["approved"])      # no contract: neither approved nor waiting for an approval (see below)
        # lint says the same of it: no contract, NOT_READY — and nothing of it to approve
        report = bundle_cli.lint(doc)
        self.assertEqual((report["criteria_without_contract"], report["verdict"]), (["C-STDLIB-1"], "NOT_READY"))
        self.assertNotIn("BC-STDLIB", [x["contract"] for x in report["to_approve"]])

    def test_every_criterion_that_has_its_approved_contract_is_still_approved(self):
        doc = copy.deepcopy(self.approved)
        doc["contracts"] = [c for c in doc["contracts"] if c["id"] != "BC-STDLIB"]
        rows = self.entries(doc)
        self.assertTrue(rows)
        for cid, e in rows.items():
            with self.subTest(criterion=cid):
                self.assertEqual((e["contract"] is None, e["approved"]), (True, None) if cid == "C-STDLIB-1" else (False, True))
        # and an approval taken away is False — a contract that is waiting for its approval, not a missing one
        doc = copy.deepcopy(self.approved)
        doc["approvals"] = [a for a in doc["approvals"] if a["contract_id"] != "BC-ADD"]
        for cid, e in self.entries(doc).items():
            with self.subTest(unapproved=cid):
                self.assertEqual(e["approved"], e["contract"] != "BC-ADD", e)

    def test_a_bundle_of_the_earlier_release_names_no_contract_and_approves_nothing_until_migrated(self):
        doc = json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8"))
        rows = self.entries(doc)
        self.assertTrue(rows)
        self.assertEqual({e["contract"] for e in rows.values()}, {None})
        self.assertEqual([c for c, e in rows.items() if e["approved"] is True], [])
        self.assertEqual(bundle_cli.lint(doc)["verdict"], "NOT_READY")
        migrated, report = bundle_cli.migrate(doc)      # the contracts are untouched, and so are the approvals nothing selects
        rows = self.entries(migrated)
        withheld = {r["contract"] for r in report["approvals_withheld"]}
        self.assertEqual(len(withheld), 6)     # what a declared capability change evaluates differently: waiting for the owner
        self.assertEqual({e["contract"] is None for e in rows.values()}, {False})
        self.assertEqual({e["contract"] for e in rows.values() if e["approved"] is False}, withheld)
        self.assertEqual({e["approved"] for e in rows.values()} - {False}, {True})
        self.assertFalse(withheld & {e["contract"] for e in rows.values() if e["approved"] is True})


class RequirementFactThatIsNotAnId(unittest.TestCase):
    """A criterion whose `requirement` fact is a list or an object cites no requirement of the bundle: the finding
    lint already makes for a missing one. Every bundle is calc-3-stories, sealed (and approved), facts edited."""

    sealed: dict
    approved: dict
    ADD, ADD_PRESERVED = "C-ADD", "C-ADD-3"      # the two criteria of requirement R-1

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        d = pathlib.Path(t.name) / "calc"
        bundle_cli.init("calc-3-stories", d)
        for step in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "baseline")):
            git(d / "repo", *step)
        cls.sealed, _ = bundle_cli.seal(json.loads((d / "authoring.json").read_text(encoding="utf-8")), repo=d / "repo")
        cls.approved = cls.sealed
        for c in [c["id"] for c in cls.sealed["contracts"]]:
            cls.approved = bundle_cli.approve(cls.approved, c, "human:t", 1.0)

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name)

    def lint(self, base: dict, requirement: dict) -> dict:
        """The report `aisef bundle lint` printed for `base` with the `requirement` fact of each criterion of
        `requirement` set, after checking it exited NOT_READY (1) with nothing on stderr."""
        doc = copy.deepcopy(base)
        for cid, value in requirement.items():
            doc["facts"][cid]["requirement"] = value
        path = self.tmp / "bundle.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        code, out, err = run_main("lint", path)
        self.assertEqual((code, err), (1, ""), out)
        return json.loads(out)

    def test_one_criterion_citing_a_list_is_reported_and_the_other_still_covers_the_requirement(self):
        for value in (["R-1"], {"id": "R-1"}, [], {}):
            with self.subTest(requirement=value):
                report = self.lint(self.approved, {self.ADD_PRESERVED: value})
                self.assertEqual(report["verdict"], "NOT_READY")
                self.assertEqual(report["coverage"]["criteria_citing_no_requirement_of_the_bundle"], [self.ADD_PRESERVED])
                r1 = report["coverage"]["requirements"]["R-1"]
                self.assertEqual((r1["status"], r1["criteria"]), ("COVERED", [self.ADD]))

    def test_every_criterion_of_a_requirement_citing_a_list_leaves_it_uncovered(self):
        report = self.lint(self.approved, {self.ADD: ["R-1"], self.ADD_PRESERVED: {"id": "R-1"}})
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual(report["coverage"]["criteria_citing_no_requirement_of_the_bundle"], [self.ADD, self.ADD_PRESERVED])
        self.assertEqual(report["coverage"]["requirements"]["R-1"]["status"], "UNCOVERED")

    def test_the_same_before_the_contracts_are_approved(self):      # admission is "not run": still a report
        report = self.lint(self.sealed, {self.ADD: ["R-1"]})
        self.assertTrue(report["to_approve"])
        self.assertTrue(report["admission"].startswith("not run"), report["admission"])
        self.assertEqual(report["coverage"]["criteria_citing_no_requirement_of_the_bundle"], [self.ADD])

    def test_the_kernel_load_check_names_the_facts_once_every_contract_is_approved(self):
        report = self.lint(self.approved, {self.ADD: ["R-1"]})
        self.assertEqual([f["check"] for f in report["admission"]["failed"]], ["load"])

    def test_a_requirement_and_a_clause_that_are_both_lists_are_one_report(self):      # the two facts of one criterion
        doc = copy.deepcopy(self.approved)
        doc["facts"][self.ADD].update({"requirement": ["R-1"], "clause": ["1.1"]})
        path = self.tmp / "both.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        code, out, err = run_main("lint", path)
        self.assertEqual((code, err), (1, ""), out)
        report = json.loads(out)
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual(report["coverage"]["criteria_citing_no_requirement_of_the_bundle"], [self.ADD])
        self.assertEqual(report["coverage"]["requirements"]["R-1"]["clauses"], {"1.1": [self.ADD_PRESERVED]})

    def test_what_was_already_a_finding_is_the_same_finding(self):      # hashable, so never died: unchanged
        for value in (None, 7, 1.5, True, "R-404", ""):
            with self.subTest(requirement=value):
                report = self.lint(self.approved, {self.ADD: value})
                self.assertEqual(report["coverage"]["criteria_citing_no_requirement_of_the_bundle"], [self.ADD])

    def test_a_caller_in_process_gets_the_finding_not_a_traceback(self):
        facts = {"C1": {"requirement": ["R1"], "clause": "1.1"}, "C2": {"requirement": "R1", "clause": "1.1"},
                 "C3": {"requirement": {"a": 1}}}
        report = bundle_cli.coverage({"requirements": [{"id": "R1"}], "facts": facts})
        self.assertEqual(report["criteria_citing_no_requirement_of_the_bundle"], ["C1", "C3"])
        self.assertEqual((report["requirements"]["R1"]["status"], report["requirements"]["R1"]["criteria"]),
                         ("COVERED", ["C2"]))
        json.dumps(report, sort_keys=True, default=str)      # printable, as main prints it


if __name__ == "__main__":
    unittest.main()
