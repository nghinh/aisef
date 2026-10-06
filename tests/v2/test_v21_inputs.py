"""V2.1 (A, V2-04): the product's inputs refuse what they cannot run, with the place that is wrong — never a traceback,
never a silent misreading. Each case here was measured on 2.0.0 by the 360° assessment (usability W3/W4, security W8,
claims W5): a wrongly typed bundle or settings field raised AttributeError/TypeError/KeyError (exit 1, read as a
delivery FAIL) or was silently misparsed; a plaintext endpoint whose host merely began with "localhost" passed; and
`--check` refused a repository carrying an editor's git key with a false "does not hold the baseline". Offline: no
client, no provider."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, cli, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from tests.v2.test_app_run import SETTINGS, git, make_repo, project_bundle  # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.baseline = make_repo(self.root / "repo")
        self.bundle = project_bundle(self.baseline)

    def write(self, name: str, doc) -> pathlib.Path:
        p = self.root / name
        p.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
        return p

    def cli(self, *argv: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.run(list(argv))
        return code, err.getvalue()


class BundleShape(_Tmp):
    """Every wrongly typed field is a BundleError naming its JSON path."""

    def refused(self, mutate, where: str) -> None:
        doc = copy.deepcopy(self.bundle)
        mutate(doc)
        with self.assertRaises(bundle.BundleError) as ctx:
            bundle.load(doc)
        self.assertIn(where, str(ctx.exception))

    def test_facts_as_a_list(self):
        self.refused(lambda d: d.__setitem__("facts", list(d["facts"].values())), "$.facts")

    def test_stories_as_a_list(self):
        self.refused(lambda d: d.__setitem__("stories", [d["stories"]["S1"]]), "$.stories")

    def test_requirements_document_as_a_string(self):
        self.refused(lambda d: d.__setitem__("requirements_document", "docs/requirements.md"), "$.requirements_document")

    def test_requirements_document_without_sha256(self):
        self.refused(lambda d: d["requirements_document"].pop("sha256"), "$.requirements_document.sha256")

    def test_story_without_tests(self):
        self.refused(lambda d: d["stories"]["S1"].pop("tests"), "$.stories.S1")

    def test_product_roots_as_a_string_is_not_split_into_letters(self):
        self.refused(lambda d: d.__setitem__("product_roots", "app"), "$.product_roots")

    def test_story_tests_as_a_string_is_not_split_into_letters(self):
        self.refused(lambda d: d["stories"]["S1"].__setitem__("tests", "tests/test_add.py"), "$.stories.S1.tests")

    def test_depends_on_an_unknown_story(self):
        self.refused(lambda d: d["stories"]["S1"].__setitem__("depends_on", ["S9"]), "$.stories.S1.depends_on")

    def test_requirements_as_an_object(self):
        self.refused(lambda d: d.__setitem__("requirements", {"R-ADD": d["requirements"][0]}), "$.requirements")

    def test_a_valid_bundle_still_loads(self):
        self.assertEqual(bundle.load(copy.deepcopy(self.bundle)).name, "calc")


class InputFiles(_Tmp):
    """An input file that cannot be read or is not JSON is a refusal (exit 2), not a traceback (exit 1)."""

    def test_bundle_not_json(self):
        p = self.write("bundle.json", "{not json")
        with self.assertRaises(bundle.BundleError) as ctx:
            bundle.read(p)
        self.assertIn("not JSON", str(ctx.exception))

    def test_bundle_is_a_directory(self):
        with self.assertRaises(bundle.BundleError):
            bundle.read(self.root)

    def test_settings_missing(self):
        with self.assertRaises(settings.SettingsError):
            settings.read(self.root / "absent.json")

    def test_cli_exit_2_for_unreadable_inputs(self):
        b = self.write("bundle.json", self.bundle)
        s = self.write("settings.json", "[1, 2")
        code, err = self.cli("--check", "--project", str(b), "--settings", str(s), "--repo", str(self.root / "repo"))
        self.assertEqual((code, "refused" in err), (2, True), err)
        code, err = self.cli("--check", "--project", str(self.root / "nope.json"), "--settings", str(s),
                             "--repo", str(self.root / "repo"))
        self.assertEqual(code, 2, err)

    def test_verify_of_a_directory_without_a_record_is_refuted_not_a_traceback(self):
        b = self.write("bundle.json", self.bundle)
        (self.root / "out").mkdir()
        code, _ = self.cli("--verify", "--project", str(b), "--out", str(self.root / "out"))
        self.assertEqual(code, 1)


class Endpoint(unittest.TestCase):
    """https anywhere; plaintext http only to a loopback host — decided on the parsed host, not a string prefix."""

    def load(self, endpoint: str):
        doc = copy.deepcopy(SETTINGS)
        doc["provider"]["endpoint"] = endpoint
        return settings.load(doc)

    def test_lookalike_hosts_are_refused(self):
        for e in ("http://localhost.evil.example/v1", "http://127.0.0.1.nip.io/v1", "http://localhostx:8080/v1",
                  "http://user:pw@127.0.0.1/v1", "ftp://127.0.0.1/v1", "https:///v1"):
            with self.subTest(e), self.assertRaises(settings.SettingsError):
                self.load(e)

    def test_loopback_and_https_are_accepted(self):
        for e in ("http://127.0.0.1:8080/v1", "http://localhost/v1", "http://[::1]:9/v1", "https://api.example.com/v1"):
            with self.subTest(e):
                self.assertEqual(self.load(e).endpoint, e)


class RepositoryRefusal(_Tmp):
    """`--check` checks the repository the way the run does (a clone of it), and a refusal names its real cause."""

    def test_an_editor_key_does_not_make_check_claim_the_baseline_is_missing(self):
        git(self.root / "repo", "config", "branch.main.vscode-merge-base", "origin/main")
        project = bundle.load(copy.deepcopy(self.bundle))
        R.check_repository(project, self.root / "repo")     # the run clones; so does --check: no refusal
        with self.assertRaises(R.RunRefused) as ctx:     # checked in place, the key's refusal is named for what it is
            R.check_repository(project, self.root / "repo", clone=False)
        self.assertIn("not inert", str(ctx.exception))
        self.assertNotIn("does not hold", str(ctx.exception))

    def test_check_mode_on_such_a_repository_is_ready(self):
        git(self.root / "repo", "config", "branch.main.vscode-merge-base", "origin/main")
        b = self.write("bundle.json", self.bundle)
        s = self.write("settings.json", SETTINGS)
        code, err = self.cli("--check", "--project", str(b), "--settings", str(s), "--repo", str(self.root / "repo"))
        self.assertEqual(code, 0, err)

    def test_a_repository_without_the_baseline_is_still_refused(self):
        other = self.root / "other"     # a different history: the plan's baseline is not in it
        other.mkdir()
        git(other, "init", "-q", "-b", "main")
        (other / "README").write_text("another project\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "unrelated")
        project = bundle.load(copy.deepcopy(self.bundle))
        with self.assertRaises(R.RunRefused) as ctx:
            R.check_repository(project, self.root / "other")
        self.assertIn("does not hold the plan's baseline", str(ctx.exception))
        with self.assertRaises(R.RunRefused):
            R.check_repository(project, self.root / "absent")


if __name__ == "__main__":
    unittest.main()
