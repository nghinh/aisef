"""V2.1 (owner B-03, mutation-survivor batch T02a): what `aisef bundle seal` (aisef2/app/bundle_cli.py::seal) refuses and
reports, tested through its own entry points — `seal()` and `main([...])` — on the shipped calc-3-stories example.

`seal` turns an authoring document into a bundle. The one who relies on it is the person who wrote the document and the
script that reads its JSON report. What each of them needs, and what this file pins:

* a refusal is a `bundle.BundleError` (never a bare KeyError / TypeError / AttributeError out of the API; exit 2, nothing
  written, from the command) that says WHERE: the path of the offending object (`$.stories.S2`, `$.contracts[1]`,
  `$.stories.S3.criteria[1]`, `$.requirements_document`), or, for a failure that has no path, the part of the document;
* what the refused object is — a repository, a document path, a baseline — stands alone in the message, so it can be told
  from what follows it (`stands_alone` below: not glued to a neighbouring identifier);
* the report is the machine-readable record of what was sealed (`plan_hash`, `specs`, ...) and agrees with the bundle;
* what is sealed is what the document declares: the sha256 of the requirements document without `--repo`, the plan id
  `PLAN-<name>` the schema documents (it is bound by plan_hash).
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

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli  # noqa: E402
from aisef2.orchestrate.workspace import git as isolated_git  # noqa: E402

_FX: dict = {}
_IDENTIFIER_CHAR = re.compile(r"[\w.\[\]$/\\-]")      # what continues an identifier or a path


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def setUpModule() -> None:
    """One repository for the file: calc-3-stories' files, committed (the baseline `seal` reads; nothing writes to it)."""
    holder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    _FX["holder"] = holder
    root = pathlib.Path(holder.name) / "calc3"
    bundle_cli.init("calc-3-stories", root)
    git(root / "repo", "init", "-q", "-b", "main")
    git(root / "repo", "add", "-A")
    git(root / "repo", "commit", "-q", "-m", "baseline")
    _FX["repo"] = root / "repo"
    _FX["head"] = git(root / "repo", "rev-parse", "HEAD").strip()
    _FX["authoring"] = json.loads((root / "authoring.json").read_text(encoding="utf-8"))


def tearDownModule() -> None:
    _FX["holder"].cleanup()


def _continues(ch: str) -> bool:
    return bool(ch) and _IDENTIFIER_CHAR.fullmatch(ch) is not None


def _delimited(text: str, i: int, j: int) -> bool:
    """text[i:j] has no identifier or path character next to it (a full stop that ends a sentence is not one)."""
    before, after = text[max(i - 1, 0):i], text[j:j + 2]
    if _continues(before):
        return False
    return not _continues(after[:1]) or (after[:1] == "." and not _continues(after[1:2]))


def stands_alone(text: str, token: str) -> bool:
    """`token` occurs in `text` with neither neighbour part of an identifier or a path: it can be read off as itself."""
    return any(_delimited(text, m.start(), m.end()) for m in re.finditer(re.escape(token), text))


def commit_stands_alone(text: str, sha: str, shortest: int = 7) -> bool:
    """An abbreviation of `sha` (its first `shortest` characters or more, whatever the width) stands alone in `text`."""
    return any(sha.startswith(m.group()) and _delimited(text, m.start(), m.end())
               for m in re.finditer(re.escape(sha[:shortest]) + r"[0-9a-f]*", text))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        self.tmp = pathlib.Path(holder.name)
        self.repo = _FX["repo"]
        self.head = _FX["head"]

    def authoring(self) -> dict:
        return copy.deepcopy(_FX["authoring"])

    def refused(self, authoring, **kw) -> str:
        """seal() refuses `authoring` as a BundleError; its message."""
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.seal(authoring, repo=self.repo, **kw)
        return str(c.exception)

    def command(self, *argv) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bundle_cli.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    def seal_command(self, authoring, *extra) -> tuple[int, str, str, pathlib.Path]:
        src, dst = self.tmp / "authoring.json", self.tmp / "bundle.json"
        src.write_text(json.dumps(authoring), encoding="utf-8")
        return (*self.command("seal", src, "--out", dst, *extra), dst)


class RequirementsDocumentIsAClosedObject(Base):
    """`requirements_document` is `{path}` or `{path, sha256}` and nothing else: an extra key, a non-object, an object
    without a string `path` is refused naming `$.requirements_document` and the two keys it may hold — by the API as a
    BundleError, by the command as exit 2 with nothing written. Pins aisef2/app/bundle_cli.py::seal [10, 64]."""

    BAD = {"an extra key": {"path": "docs/requirements.md", "extra": 1}, "a list": [], "a string": "docs/requirements.md",
           "null": None, "an empty object": {}, "a path that is not a string": {"path": 5},
           "a sha256 without its path": {"sha256": "0" * 64}}

    def test_each_malformed_object_is_refused_naming_the_field_and_its_keys(self):
        for what, value in self.BAD.items():
            with self.subTest(what):
                a = self.authoring()
                a["requirements_document"] = value
                message = self.refused(a)
                self.assertIn("$.requirements_document", message)
                self.assertIn("path", message)
                self.assertIn("sha256", message)

    def test_the_command_refuses_with_exit_2_and_writes_nothing(self):
        for what in ("an extra key", "a list", "an empty object"):
            with self.subTest(what):
                a = self.authoring()
                a["requirements_document"] = self.BAD[what]
                code, out, err, dst = self.seal_command(a, "--repo", self.repo)
                self.assertEqual(code, 2, err)
                self.assertIn("$.requirements_document", err)
                self.assertFalse(dst.exists())

    def test_a_path_alone_is_sealed_with_a_repository(self):
        a = self.authoring()
        a["requirements_document"] = {"path": "docs/requirements.md"}
        doc, _ = bundle_cli.seal(a, repo=self.repo)
        self.assertEqual(doc["requirements_document"]["path"], "docs/requirements.md")


class StoriesIsANonEmptyObject(Base):
    """`stories` is an object of at least one story: `{}`, a list, a string, a number and null are each refused naming
    `$.stories` — not later, by the plan, without a path. Pins aisef2/app/bundle_cli.py::seal [19, 67]."""

    def test_each_value_that_is_not_a_non_empty_object_is_refused_naming_stories(self):
        for value in ({}, [], ["S1"], "S1", 5, None):
            with self.subTest(value=value):
                a = self.authoring()
                a["stories"] = value
                self.assertIn("$.stories", self.refused(a))

    def test_the_command_exits_2_and_writes_nothing(self):
        a = self.authoring()
        a["stories"] = ["S1"]
        code, _, err, dst = self.seal_command(a, "--repo", self.repo)
        self.assertEqual(code, 2, err)
        self.assertIn("$.stories", err)
        self.assertFalse(dst.exists())


class EveryClosedObjectNamesItsPath(Base):
    """A refusal of the shape of an object leads with that object's path and then says which keys it held — the document
    (`$`), a story (`$.stories.<id>`), a contract (`$.contracts[<n>]`, n its index): with several of each the path is
    the only locator. Pins aisef2/app/bundle_cli.py::seal [28, 95, 119, 120]."""

    def test_the_document_itself(self):
        a = self.authoring()
        a["stray"] = 1
        message = self.refused(a)
        self.assertTrue(message.startswith("$:"), message)
        self.assertIn("stray", message)                    # the held keys: the one that does not belong is named
        a = self.authoring()
        del a["description"]
        self.assertTrue(self.refused(a).startswith("$:"))
        self.assertTrue(self.refused([]).startswith("$:"))

    def test_a_story(self):
        for what, change in (("an unknown key", lambda s: s.update(extra=1)),
                             ("a missing key", lambda s: s.pop("tests")),
                             ("not an object", None)):
            with self.subTest(what):
                a = self.authoring()
                if change is None:
                    a["stories"]["S2"] = 5
                else:
                    change(a["stories"]["S2"])
                message = self.refused(a)
                self.assertTrue(message.startswith("$.stories.S2:"), message)

    def test_a_contract_is_named_with_its_index(self):
        for what, change in (("an unknown key", lambda c: c.update(extra=1)),
                             ("a missing key", lambda c: c.pop("rationale")),
                             ("not an object", None)):
            with self.subTest(what):
                a = self.authoring()
                if change is None:
                    a["contracts"][1] = 5
                else:
                    change(a["contracts"][1])
                self.assertIn("$.contracts[1]", self.refused(a))


class AnotherFormatIsRefusedByName(Base):
    """A document of another format (a sealed bundle's format id on authoring keys) is refused naming the field and the
    format `seal` accepts. Pins aisef2/app/bundle_cli.py::seal [83]."""

    def test_the_field_and_the_accepted_format_are_named(self):
        for value in (bundle.FORMAT, "x"):
            with self.subTest(value):
                a = self.authoring()
                a["format"] = value
                message = self.refused(a)
                self.assertIn("$.format", message)
                self.assertIn(bundle_cli.AUTHORING_FORMAT, message)


class RequirementsDocumentHashWithoutARepository(Base):
    """Without `--repo` the requirements document's sha256 is the one the document declares (the schema: "only without
    --repo; with it, read at the baseline"): the sealed bundle is the bundle `--repo` seals, with the same hash. With
    `--repo` the repository wins: a wrong declared hash is never written. The value is what `aisef run --check`
    compares with the blob at the baseline — integrity data. Pins aisef2/app/bundle_cli.py::seal [36, 86]."""

    def setUp(self) -> None:
        super().setUp()
        a = self.authoring()
        a["baseline"] = self.head
        self.undeclared = a
        self.from_repo, _ = bundle_cli.seal(copy.deepcopy(a), repo=self.repo)
        self.declared = self.from_repo["requirements_document"]["sha256"]

    def test_the_declared_hash_is_sealed_as_declared(self):
        a = copy.deepcopy(self.undeclared)
        a["requirements_document"]["sha256"] = self.declared
        doc, _ = bundle_cli.seal(a)                       # no repository
        self.assertEqual(doc["requirements_document"]["sha256"], self.declared)
        self.assertEqual(doc, self.from_repo)

    def test_without_a_declared_hash_and_without_a_repository_the_document_is_refused(self):
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.seal(copy.deepcopy(self.undeclared))
        self.assertIn("sha256", str(c.exception))

    def test_with_a_repository_the_hash_of_the_blob_wins_over_a_declared_one(self):
        a = copy.deepcopy(self.undeclared)
        a["requirements_document"]["sha256"] = "0" * 64
        doc, _ = bundle_cli.seal(a, repo=self.repo)
        self.assertEqual(doc["requirements_document"]["sha256"], self.declared)
        self.assertEqual(doc, self.from_repo)


class AContractOrRequirementThatDoesNotBuildIsRefused(Base):
    """A requirement or contract the kernel's constructors cannot build — a missing key (KeyError), a value of the wrong
    kind (TypeError), a value outside its enum or a kernel refusal (ValueError, ContractError) — is refused as a
    BundleError, never as the bare exception, and the refusal names the exception type, the key and — for a contract,
    whose failures carry no path of their own (`KeyError: 'kind'`) — that it is the contract that failed. Pins
    aisef2/app/bundle_cli.py::seal [40, 41, 42, 121]."""

    def contract_with(self, **change) -> dict:
        a = self.authoring()
        a["contracts"][0].update(change)
        return a

    def test_a_subject_without_its_kind_names_the_key_and_the_contract(self):
        a = self.contract_with(subject={"locator": "app.calc:add"})
        message = self.refused(a)
        self.assertIn("KeyError", message)
        self.assertIn("'kind'", message)
        self.assertIn("contract", message)

    def test_a_requirement_that_does_not_build_names_the_kind_of_failure_and_the_key(self):
        a = self.authoring()
        a["requirements"][0]["extra"] = 1                  # Requirement.create(**r): TypeError
        message = self.refused(a)
        self.assertIn("TypeError", message)
        self.assertIn("extra", message)

    def test_each_kind_of_failure_is_a_bundle_error(self):
        cases = {"requirement_ids that is not a list (TypeError)": self.contract_with(requirement_ids=5),
                 "a subject that is null (TypeError)": self.contract_with(subject=None),
                 "a polarity outside its enum (ValueError)": self.contract_with(polarity="SIDEWAYS"),
                 "a subject absence outside its enum (ValueError)": self.contract_with(subject_absence="MAYBE"),
                 "no requirement id (ContractError)": self.contract_with(requirement_ids=[]),
                 "a rationale that is not a string (ContractError)": self.contract_with(rationale=5)}
        for what, a in cases.items():
            with self.subTest(what):
                message = self.refused(a)
                self.assertIn("contract", message)

    def test_the_command_refuses_with_exit_2_and_writes_nothing(self):
        code, _, err, dst = self.seal_command(self.contract_with(subject={"locator": "app.calc:add"}), "--repo", self.repo)
        self.assertEqual(code, 2, err)
        self.assertIn("'kind'", err)
        self.assertIn("contract", err)          # main's own fallback would print "KeyError: 'kind'" alone
        self.assertFalse(dst.exists())


class ACriterionThatDoesNotBuildIsRefusedAtItsPath(Base):
    """A criterion whose obligation cannot be built — `depends_on` that is not a list (TypeError), a role outside the
    enum (ValueError), a `why` that is not a string (kernel ContractError) — is refused as a BundleError that names the
    criterion path `$.stories.<id>.criteria[<n>]` as an identifier of its own (with many criteria the author finds the
    one from it) and the class of the failure. Pins aisef2/app/bundle_cli.py::seal [103, 104, 148]."""

    PATH = "$.stories.S3.criteria[1]"

    def test_each_failure_names_the_criterion(self):
        for what, change, cause in (("depends_on that is not a list", {"depends_on": 5}, "TypeError"),
                                    ("a role outside the enum", {"role": "BOGUS"}, "ValueError"),
                                    ("a why that is not a string", {"why": 5}, "ContractError")):
            with self.subTest(what):
                a = self.authoring()
                a["stories"]["S3"]["criteria"][1].update(change)
                message = self.refused(a)
                self.assertTrue(stands_alone(message, self.PATH), message)
                self.assertIn(cause, message)          # what failed, after where: the class of the kernel's refusal

    def test_the_command_exits_2_and_writes_nothing(self):
        a = self.authoring()
        a["stories"]["S3"]["criteria"][1]["role"] = "BOGUS"
        code, _, err, dst = self.seal_command(a, "--repo", self.repo)
        self.assertEqual(code, 2, err)
        self.assertTrue(stands_alone(err, self.PATH), err)
        self.assertFalse(dst.exists())


class ACriterionOfAContractNoProbeObservesIsRefusedAtSeal(Base):
    """A criterion whose contract's subject kind has no active probe is refused when sealed (not later, when the plan
    is compiled), naming the criterion path and the kind, each as an identifier of its own, and that it is a probe
    that is missing. Pins aisef2/app/bundle_cli.py::seal [134]."""

    def test_the_criterion_and_the_kind_are_named(self):
        a = self.authoring()
        a["contracts"][1]["subject"] = {"kind": "http_route", "locator": "GET /mul"}      # BC-MUL: S2's criterion 0
        message = self.refused(a)
        self.assertTrue(stands_alone(message, "$.stories.S2.criteria[0]"), message)
        self.assertTrue(stands_alone(message, "http_route"), message)
        self.assertIn("probe", message)               # what is missing: without it the two names say nothing of the cause


class ApprovalsToKeepThatDoNotLoad(Base):
    """`--keep-approvals-from OLD` hands approvals to be kept. One that does not load — not an object, a missing or
    unknown field, an approver that is not `human:<name>`, a timestamp that is not a number — refuses the whole seal as
    a BundleError (exit 2, nothing written): it is neither kept nor quietly listed as dropped (dropped is for approvals
    that load and no longer bind). The refusal says that it is an approval that failed: the kernel's detail
    (`approved_at must be a finite timestamp`) names neither the file nor the object. Pins
    aisef2/app/bundle_cli.py::seal [75, 76, 137]."""

    def setUp(self) -> None:
        super().setUp()
        sealed, _ = bundle_cli.seal(self.authoring(), repo=self.repo)
        self.old = bundle_cli.approve(sealed, "BC-ADD", "human:t", 1.0)
        self.good = self.old["approvals"][0]

    def bad(self) -> dict:
        without = {k: v for k, v in self.good.items() if k != "contract_hash"}
        return {"not an object": 5, "an unknown field": {**self.good, "extra": 1}, "a missing field": without,
                "an agent as approver": {**self.good, "approver": "agent:dev"},
                "a timestamp that is not a number": {**self.good, "approved_at": "x"}}

    def test_a_loading_approval_is_kept(self):
        _, report = bundle_cli.seal(self.authoring(), repo=self.repo, approvals=[self.good])
        self.assertEqual((report["approvals_kept"], report["approvals_dropped"]), (1, []))

    def test_each_one_that_does_not_load_refuses_the_seal(self):
        for what, approval in self.bad().items():
            with self.subTest(what):
                self.refused(self.authoring(), approvals=[self.good, approval])

    def test_the_refusal_names_an_approval_even_when_the_kernel_detail_does_not(self):
        message = self.refused(self.authoring(), approvals=[{**self.good, "approved_at": "x"}])
        self.assertIn("approval", message)

    def test_the_command_refuses_an_agent_approval_with_exit_2_and_writes_nothing(self):
        old = {**self.old, "approvals": [{**self.good, "approver": "agent:dev"}]}
        keep = self.tmp / "old.json"
        keep.write_text(json.dumps(old), encoding="utf-8")
        code, _, err, dst = self.seal_command(self.authoring(), "--repo", self.repo, "--keep-approvals-from", keep)
        self.assertEqual(code, 2, err)
        self.assertIn("human", err)
        self.assertFalse(dst.exists())


class TheReportDescribesTheBundleWritten(Base):
    """What `seal` prints is a JSON report a script reads: the `plan_hash` of the plan it sealed (the one `aisef run`
    prints for the project, so the two can be compared), the number of distinct `specs` that plan names, and what became
    of the approvals; and the plan id is `PLAN-<name>` as the schema documents (the id is bound by plan_hash).
    Pins aisef2/app/bundle_cli.py::seal [55, 56, 78, 79, 126]."""

    def sealed(self) -> tuple[dict, dict]:
        code, out, err, dst = self.seal_command(self.authoring(), "--repo", self.repo)
        self.assertEqual(code, 0, err)
        return json.loads(out), json.loads(dst.read_text(encoding="utf-8"))

    def test_the_report_agrees_with_the_bundle(self):
        report, doc = self.sealed()
        wanted = {"written", "plan_hash", "specs", "approvals_kept", "approvals_dropped", "to_approve"}
        self.assertEqual(wanted - set(report), set())
        self.assertEqual(report["plan_hash"], doc["plan"]["plan_hash"])
        distinct = {o["product_proof_spec_id"] for o in doc["plan"]["obligations"]}
        self.assertEqual(report["specs"], len(distinct))
        self.assertLess(len(distinct), len(doc["plan"]["obligations"]))     # PRESERVE reuses BC-ADD: not a count of rows

    def test_the_command_prints_what_the_api_returns(self):
        report, _ = self.sealed()
        _, api = bundle_cli.seal(self.authoring(), repo=self.repo)
        self.assertEqual({k: v for k, v in report.items() if k != "written"}, api)

    def test_the_plan_id_is_the_documented_one(self):
        _, doc = self.sealed()
        self.assertEqual(doc["plan"]["id"], "PLAN-" + self.authoring()["name"])


class RepositoryRefusals(Base):
    """A repository that cannot give the baseline or the requirements document is refused naming what failed, each
    object as an identifier of its own: the field path, the document path, the repository and an abbreviation of the
    baseline (so the reader can tell which commit was looked at; its width is not the contract); the API raises a
    BundleError, never the raw exception of building the message. Pins aisef2/app/bundle_cli.py::seal
    [112, 115, 116, 117, 141]."""

    def test_a_document_that_is_not_at_the_baseline(self):
        a = self.authoring()
        a["requirements_document"]["path"] = "docs/NOPE.md"
        message = self.refused(a)
        for token in ("$.requirements_document.path", "docs/NOPE.md", str(self.repo)):
            with self.subTest(token):
                self.assertTrue(stands_alone(message, token), message)
        self.assertTrue(commit_stands_alone(message, self.head), message)

    def test_the_command_exits_2_and_writes_nothing(self):
        a = self.authoring()
        a["requirements_document"]["path"] = "docs/NOPE.md"
        code, _, err, dst = self.seal_command(a, "--repo", self.repo)
        self.assertEqual(code, 2, err)
        self.assertTrue(stands_alone(err, "docs/NOPE.md"), err)
        self.assertFalse(dst.exists())

    def test_a_repository_with_no_commit_is_named_and_gives_git_own_reason(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        git(empty, "init", "-q", "-b", "main")
        why = isolated_git(empty, "rev-parse", "--verify", "HEAD^{commit}")
        self.assertNotEqual(why.returncode, 0)
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.seal(self.authoring(), repo=empty)
        message = str(c.exception)
        self.assertTrue(stands_alone(message, str(empty)), message)
        self.assertIn(why.stderr.strip()[:200], message)


if __name__ == "__main__":
    unittest.main()
