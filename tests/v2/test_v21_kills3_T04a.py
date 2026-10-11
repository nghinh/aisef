"""Mutation-survivor batch T04a (V2.1 campaign 2): what `aisef bundle` tells the approver and the author, pinned to the
requirement of whoever reads it.

The bundle tools run outside a run and are read by people, not by a later stage: `explain` and the `to_approve`
report are what a human approver decides from, so each field is checked against an oracle that does NOT go through the
code under test — the sealed bundle's own JSON (plan obligations, contracts, requirements, facts), the specs the
kernel compiles from the approved bundle (`bundle.load`), and the probe registry. Refusals are checked for the
identifying elements an operator acts on (the file, the extra key, the two ids), not for their wording.

Pins aisef2/app/bundle_cli.py::{_closed, _read, _spec_rows, _write_new, approve, explain, unapproved}.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
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

from aisef2.app import bundle, bundle_cli  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.calibrations import CALIBRATIONS  # noqa: E402
from aisef2.probe import catalog  # noqa: E402

CONTRACTS = ("BC-ADD", "BC-MUL", "BC-TOTAL", "BC-STDLIB")
#: the observation class each calc-3-stories contract asks of its probe (its observable: `returns` / `matches` over
#: the stimulus `imports_outside`) — written here, not derived by explain
CLASS_ASKED = {"BC-ADD": "returns", "BC-MUL": "returns", "BC-TOTAL": "returns", "BC-STDLIB": "python_imports"}
MISSING = "<key missing>"


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def tool(*argv) -> tuple[int, str, str]:
    """`aisef bundle ARGV` in-process: (exit status, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bundle_cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def dump(path: pathlib.Path, doc) -> pathlib.Path:
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _edit(authoring: dict, edit) -> dict:
    a = copy.deepcopy(authoring)
    edit(a)
    return a


def approve_all(doc: dict) -> dict:
    for c in [x["id"] for x in doc["contracts"]]:
        doc = bundle_cli.approve(doc, c, "human:t", 1.0)
    return doc


class World:
    """One sealed (unapproved) bundle, the same bundle fully approved, and the project the kernel compiles from it."""

    def __init__(self, repo: pathlib.Path, authoring: dict) -> None:
        self.sealed, self.report = bundle_cli.seal(copy.deepcopy(authoring), repo=repo)
        self.approved = approve_all(self.sealed)
        self.project = bundle.load(self.approved)

    def expected(self) -> dict[str, list[dict]]:
        """What explain tells per criterion, from the oracles: story -> its entries, in plan order."""
        contracts = {c["id"]: c for c in self.sealed["contracts"]}
        registry = catalog.registry()
        out: dict[str, list[dict]] = {}
        for o in self.sealed["plan"]["obligations"]:
            spec = self.project.specs[o["product_proof_spec_id"]]
            c, facts = contracts[spec.contract_id], self.sealed["facts"][o["criterion_id"]]
            asked = CLASS_ASKED[c["id"]]
            if registry.observation_class(spec.probe_id, spec.probe_digest, spec) != asked:
                raise AssertionError(f"the registry does not observe {c['id']} as {asked}")
            out.setdefault(o["story_id"], []).append({
                "criterion": o["criterion_id"], "role": o["role"], "spec": o["product_proof_spec_id"],
                "contract": c["id"], "probe": spec.probe_id, "class": asked, "polarity": c["polarity"],
                "subject": (c["subject"]["kind"], c["subject"]["locator"]),
                "requirement": facts["requirement"], "clause": facts["clause"], "clause_text": facts["clause_text"]})
        return out


class Calc3(unittest.TestCase):
    """calc-3-stories from `aisef bundle init`, in a git repository (as an outsider has it), sealed once per class."""

    @classmethod
    def setUpClass(cls) -> None:
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = pathlib.Path(tmp.name)
        cls.dir = cls.tmp / "calc3"
        code, _, err = tool("init", "--example", "calc-3-stories", "--out", cls.dir)
        assert code == 0, err
        for step in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "baseline")):
            git(cls.dir / "repo", *step)
        cls.repo = cls.dir / "repo"
        cls.authoring = json.loads((cls.dir / "authoring.json").read_text(encoding="utf-8"))

    def edited(self, edit) -> dict:
        return _edit(self.authoring, edit)

    def seal(self, edit=None) -> tuple[dict, dict]:
        return bundle_cli.seal(self.edited(edit) if edit else copy.deepcopy(self.authoring), repo=self.repo)


class ExplainEntries(Calc3):
    """`aisef bundle explain` is what the approver reads: per story, in plan order, each criterion with the facts of
    the clause it answers and the contract, probe, class, polarity and subject that will judge it.

    Pins aisef2/app/bundle_cli.py::explain [8, 10, 11, 12, 15, 16, 17, 18, 22, 23, 24] and
    ::_spec_rows [9, 10, 16, 17, 20, 21, 22, 23, 27, 28, 29, 30, 33].
    Oracles: the sealed bundle's plan, contracts and facts; the specs `bundle.load` compiles (their probe ids); the
    observation class each contract's observable asks (written in CLASS_ASKED, cross-checked with the registry).
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.world = World(cls.repo, cls.authoring)

        def flip(a):    # BC-ADD claims the opposite (returns 6 MUST_NOT_HOLD): a polarity that is not the default
            a["contracts"][0]["polarity"] = "MUST_NOT_HOLD"
            a["contracts"][0]["observable"]["returns"] = 6
        cls.flipped = World(cls.repo, _edit(cls.authoring, flip))

    def told(self, doc: dict) -> dict:
        """The entries `aisef bundle explain` prints for `doc`, story -> entries."""
        n = len(list(self.tmp.glob("told-*.json")))
        code, out, err = tool("explain", dump(self.tmp / f"told-{n}.json", doc))
        self.assertEqual(code, 0, err)
        return json.loads(out)["stories"]

    @staticmethod
    def fields(stories: dict, keys: tuple[str, ...]) -> dict:
        return {s: [{k: e.get(k, MISSING) for k in keys} for e in entries] for s, entries in stories.items()}

    def each_report(self, world: World):
        """The two reports the approver meets: before any approval and after every contract is approved."""
        yield "unapproved", self.told(world.sealed), world.expected()
        yield "approved", self.told(world.approved), world.expected()

    def test_every_criterion_of_the_plan_is_reported_under_its_story_with_its_role_and_spec(self):
        for label, told, expected in self.each_report(self.world):
            with self.subTest(label):
                keys = ("criterion", "role", "spec")
                self.assertEqual(self.fields(told, keys), self.fields(expected, keys))
        # the spec an entry names is one the kernel compiles from the approved bundle
        for entries in self.told(self.world.approved).values():
            for e in entries:
                self.assertIn(e["spec"], self.world.project.specs)

    def test_stories_and_the_criteria_inside_them_come_in_plan_order(self):
        plan_order: dict[str, list[str]] = {}
        for o in self.world.sealed["plan"]["obligations"]:
            plan_order.setdefault(o["story_id"], []).append(o["criterion_id"])
        for doc in (self.world.sealed, self.world.approved):
            report = bundle_cli.explain(doc)["stories"]
            self.assertEqual(list(report), list(plan_order))
            self.assertEqual({s: [e["criterion"] for e in es] for s, es in report.items()}, plan_order)

    def test_each_entry_names_the_probe_and_class_that_judge_its_contract(self):
        for label, told, expected in self.each_report(self.world):
            with self.subTest(label):
                keys = ("probe", "class")
                self.assertEqual(self.fields(told, keys), self.fields(expected, keys))
        probes = {e["probe"] for es in self.told(self.world.approved).values() for e in es}
        self.assertEqual(len(probes), 2)      # calc-3-stories has a python_callable and a file_artifact contract

    def test_the_subject_of_an_entry_gives_its_contracts_kind_then_locator_as_separate_parts(self):
        # the approver tells what kind of subject it is from where it is: the contract's kind, then its locator, with
        # something between them (fused, the two cannot be told apart)
        for label, told, expected in self.each_report(self.world):
            with self.subTest(label):
                self.assertEqual(self.fields(told, ("criterion",)), self.fields(expected, ("criterion",)))
                for story, entries in told.items():
                    for got, want in zip(entries, expected[story], strict=True):
                        kind, locator = want["subject"]
                        self.assertRegex(got.get("subject", MISSING), rf"\A{re.escape(kind)}\W.*{re.escape(locator)}\Z",
                                         got["criterion"])

    def test_the_polarity_of_an_entry_is_its_contracts_whichever_it_is(self):
        for label, told, expected in self.each_report(self.flipped):
            with self.subTest(label):
                self.assertEqual(self.fields(told, ("polarity",)), self.fields(expected, ("polarity",)))
        polarities = {e["contract"]: e["polarity"] for es in self.told(self.flipped.approved).values() for e in es}
        self.assertEqual(polarities, {"BC-ADD": "MUST_NOT_HOLD", "BC-MUL": "MUST_HOLD", "BC-TOTAL": "MUST_HOLD",
                                      "BC-STDLIB": "MUST_HOLD"})

    def test_each_entry_carries_the_requirement_clause_and_wording_its_facts_declare(self):
        for label, told, expected in self.each_report(self.world):
            with self.subTest(label):
                keys = ("requirement", "clause", "clause_text")      # values, not key presence: a null is not the clause
                self.assertEqual(self.fields(told, keys), self.fields(expected, keys))


class ExplainFlagCalibrated(Calc3):
    """`calibrated` says "this class is qualified at the bytes that run": False when no calibration of the probe's
    executing digest and the class exists. It is what lint lists as criteria_without_calibration and what admission's
    check 9 refuses; a True for an uncalibrated class is a false assurance given to the approver.

    Pins aisef2/app/bundle_cli.py::_spec_rows [32].
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.approved = World(cls.repo, cls.authoring).approved
        cls.without_file_artifact = R.calibrations([r for r in CALIBRATIONS if r["probe_id"] != "probe.file_artifact"])

    def entries(self, doc: dict) -> dict[str, dict]:
        return {e["criterion"]: e for es in bundle_cli.explain(doc)["stories"].values() for e in es}

    def test_a_class_without_a_calibration_at_the_executing_digest_is_not_calibrated(self):
        # control: with this release's calibrations every class of the example is calibrated, so the False below is
        # what the missing calibration makes of it and not something python_imports always reports
        shipped = self.entries(self.approved)
        self.assertEqual({c: e["calibrated"] for c, e in shipped.items()}, dict.fromkeys(shipped, True))
        cals = self.without_file_artifact
        with mock.patch.object(R, "calibrations", lambda rows=None: cals):
            entries = self.entries(self.approved)
            report = bundle_cli.lint(self.approved)
        self.assertEqual(entries["C-STDLIB-1"]["class"], "python_imports")      # classified, and not calibrated
        self.assertIs(entries["C-STDLIB-1"]["calibrated"], False)
        for c in ("C-ADD", "C-MUL", "C-TOTAL", "C-ADD-3"):
            self.assertIs(entries[c]["calibrated"], True, c)
        # the flag agrees with the gate: lint lists it and admission's check 9 names that criterion's spec
        self.assertEqual(report["criteria_without_calibration"], ["C-STDLIB-1"])
        self.assertEqual(report["verdict"], "NOT_READY")
        failed = {f["check"]: f["problems"] for f in report["admission"]["failed"]}
        self.assertEqual(list(failed), ["9. probe_calibration"])
        self.assertIn(entries["C-STDLIB-1"]["spec"], " ".join(failed["9. probe_calibration"]))

    def test_with_no_calibrations_installed_no_classified_criterion_is_calibrated(self):
        with mock.patch.object(R, "calibrations", lambda rows=None: ()):
            entries = self.entries(self.approved)
            report = bundle_cli.lint(self.approved)
        self.assertEqual({c: (e["class"], e["calibrated"]) for c, e in entries.items()},
                         {"C-ADD": ("returns", False), "C-STDLIB-1": ("python_imports", False),
                          "C-MUL": ("returns", False), "C-TOTAL": ("returns", False), "C-ADD-3": ("returns", False)})
        self.assertEqual(report["criteria_without_calibration"], sorted(entries))


class ToApprove(Calc3):
    """The report of what is still to approve names, per (contract, requirement it cites), the two hashes an approval
    binds (`unapproved`'s own contract). Each is the bundle's own hash, and is the hash the approval that `approve`
    writes then binds. A citation of a requirement the bundle lacks is reported, with a null requirement hash, and
    never crashes the tool.

    Pins aisef2/app/bundle_cli.py::unapproved [10, 11, 12, 14, 15, 16, 17].
    """

    KEYS = ("contract", "requirement", "contract_hash", "requirement_hash")

    @classmethod
    def named(cls, entries: list[dict]) -> list[dict]:
        """The fields an approver needs of each entry (a key that is absent is MISSING, never None)."""
        return [{k: e.get(k, MISSING) for k in cls.KEYS} for e in entries]

    @staticmethod
    def pending(doc: dict) -> list[dict]:
        """Every (contract, cited requirement), in contract order, from the sealed bundle's own JSON."""
        hashes = {r["id"]: r["requirement_hash"] for r in doc["requirements"]}
        return [{"contract": c["id"], "requirement": rid, "contract_hash": c["contract_hash"],
                 "requirement_hash": hashes.get(rid)} for c in doc["contracts"] for rid in c["requirement_ids"]]

    def two_requirements(self, a: dict) -> None:
        a["contracts"][0]["requirement_ids"] = ["R-1", "R-2"]

    def test_seal_and_lint_report_each_contract_requirement_pair_with_the_hashes_an_approval_binds(self):
        doc, report = self.seal(self.two_requirements)
        expected = self.pending(doc)
        self.assertEqual([(x["contract"], x["requirement"]) for x in expected],
                         [("BC-ADD", "R-1"), ("BC-ADD", "R-2"), ("BC-MUL", "R-2"), ("BC-TOTAL", "R-3"),
                          ("BC-STDLIB", "R-4")])
        self.assertTrue(all(x["contract_hash"] and x["requirement_hash"] for x in expected))
        self.assertEqual(self.named(report["to_approve"]), expected)
        self.assertEqual(self.named(bundle_cli.lint(doc)["to_approve"]), expected)
        code, out, err = tool("lint", dump(self.tmp / "two.json", doc))
        self.assertEqual((code, json.loads(out)["verdict"], err), (1, "NOT_READY", ""))
        self.assertEqual(self.named(json.loads(out)["to_approve"]), expected)

    def test_approve_binds_exactly_the_hashes_the_report_named_and_reports_what_is_left(self):
        doc, _ = self.seal(self.two_requirements)
        before = self.pending(doc)
        code, out, err = tool("approve", dump(self.tmp / "unapproved.json", doc), "--contract", "BC-ADD",
                              "--approver", "human:t", "--out", self.tmp / "approved-one.json")
        self.assertEqual(code, 0, err)
        written = json.loads((self.tmp / "approved-one.json").read_text(encoding="utf-8"))
        bound = {(a["contract_id"], a["requirement_id"]): (a["contract_hash"], a["requirement_hash"])
                 for a in written["approvals"]}
        named = [x for x in before if x["contract"] == "BC-ADD"]
        self.assertEqual(bound, {(x["contract"], x["requirement"]): (x["contract_hash"], x["requirement_hash"])
                                 for x in named})
        self.assertEqual(self.named(json.loads(out)["still_to_approve"]),
                         [x for x in before if x["contract"] != "BC-ADD"])

    def test_a_citation_of_a_requirement_the_bundle_lacks_is_reported_without_a_requirement_hash(self):
        doc, report = self.seal(lambda a: a["contracts"][0].update(requirement_ids=["R-1", "R-404"]))
        expected = self.pending(doc)
        self.assertIsNone(expected[1]["requirement_hash"])
        self.assertEqual(expected[1]["requirement"], "R-404")
        self.assertEqual(self.named(report["to_approve"]), expected)
        lint = bundle_cli.lint(doc)
        self.assertEqual((lint["verdict"], self.named(lint["to_approve"])), ("NOT_READY", expected))
        code, out, _ = tool("lint", dump(self.tmp / "dangling.json", doc))
        self.assertEqual((code, json.loads(out)["verdict"]), (1, "NOT_READY"))


class ApproveRefusal(Calc3):
    """Approving a contract that cites a requirement the bundle lacks is refused naming the contract and the
    requirement — each as a whole identifier an operator can look up — and nothing is approved, not even the
    requirement that is there.

    Pins aisef2/app/bundle_cli.py::approve [19].
    """

    def test_the_refusal_names_the_contract_and_the_absent_requirement_and_writes_nothing(self):
        doc, _ = self.seal(lambda a: a["contracts"][0].update(requirement_ids=["R-1", "R-404"]))
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.approve(doc, "BC-ADD", "human:t", 1.0)
        for ident in ("BC-ADD", "R-404"):
            self.assertRegex(str(c.exception), rf"(?<![\w-]){re.escape(ident)}(?![\w-])")
        self.assertEqual(doc["approvals"], [])              # R-1 is cited first: it is not approved either
        code, out, err = tool("approve", dump(self.tmp / "cites-absent.json", doc), "--contract", "BC-ADD",
                              "--approver", "human:t", "--out", self.tmp / "never.json")
        self.assertEqual((code, out), (2, ""))
        self.assertFalse((self.tmp / "never.json").exists())
        for ident in ("BC-ADD", "R-404"):
            self.assertRegex(err, rf"(?<![\w-]){re.escape(ident)}(?![\w-])")


class ClosedKeySets(Calc3):
    """An authoring object outside its closed key set is refused as a BundleError that says what the object held: the
    extra key, or the type that is not an object — so an author finds it; a non-object never escapes as a TypeError.

    Pins aisef2/app/bundle_cli.py::_closed [4].
    """

    def refused(self, edit) -> str:
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.seal(self.edited(edit), repo=self.repo)
        return str(c.exception)

    def test_an_extra_key_is_named_with_the_path_of_its_object(self):
        msg = self.refused(lambda a: a["stories"]["S1"]["criteria"][0].update(spec="PPS-x"))
        self.assertIn("$.stories.S1.criteria[0]", msg)
        self.assertIn("spec", msg)       # not in the closed set (nor in the path): it appears only as what the object held

    def test_a_story_that_is_a_list_is_refused_naming_the_type(self):
        msg = self.refused(lambda a: a["stories"].update(S1=["tests/test_add.py"]))
        self.assertIn("$.stories.S1", msg)
        self.assertIn("list", msg)

    def test_a_story_that_is_a_number_is_a_bundle_error_naming_the_type(self):
        msg = self.refused(lambda a: a["stories"].update(S1=5))
        self.assertIn("$.stories.S1", msg)
        self.assertIn("int", msg)


class UnreadableDocument(Calc3):
    """A file that is not JSON is refused by every command that reads a document, with status 2, nothing written, and
    the file named as one copyable path followed by the kind of failure.

    Pins aisef2/app/bundle_cli.py::_read [3, 5].
    """

    def test_every_command_refuses_a_file_that_is_not_json_naming_the_file(self):
        bad = self.tmp / "not-json.json"
        bad.write_text("{not json", encoding="utf-8")
        out = self.tmp / "unreadable-out.json"
        commands = {
            "lint": ("lint", bad),
            "explain": ("explain", bad),
            "approve": ("approve", bad, "--contract", "BC-ADD", "--approver", "human:t", "--out", out),
            "seal": ("seal", bad, "--repo", self.repo, "--out", out),
            "continue": ("continue", bad, "--from-run", self.tmp, "--out", out),
            "migrate": ("migrate", bad, "--out", out),
        }
        for name, argv in commands.items():
            with self.subTest(name):
                code, stdout, err = tool(*argv)
                self.assertEqual((code, stdout), (2, ""))
                self.assertRegex(err, re.escape(str(bad)) + r"(?![\w-])")     # the path, not the path run into a word
                self.assertIn("JSONDecodeError", err)
                self.assertFalse(out.exists())


class WrittenFiles(Calc3):
    """The files the tools write are the documents a human approver reads: characters are written as UTF-8, not as
    \\uXXXX escapes, and the file parses back to the document written.

    Pins aisef2/app/bundle_cli.py::_write_new [2].
    """

    def test_init_and_seal_write_utf8_not_escapes(self):
        example = json.loads((bundle_cli.EXAMPLES / "calc-3-stories.json").read_text(encoding="utf-8"))["authoring"]
        sealed = self.tmp / "sealed-utf8.json"
        code, _, err = tool("seal", self.dir / "authoring.json", "--repo", self.repo, "--out", sealed)
        self.assertEqual(code, 0, err)
        for path in (self.dir / "authoring.json", sealed):
            with self.subTest(path.name):
                raw = path.read_bytes()
                self.assertIn("§".encode("utf-8"), raw)       # the section sign of facts.section, as itself
                self.assertNotIn(b"\\u00a7", raw)
        self.assertEqual(json.loads((self.dir / "authoring.json").read_text(encoding="utf-8")), example)


if __name__ == "__main__":
    unittest.main()
