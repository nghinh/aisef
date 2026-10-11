"""V2.1 mutation survivors, batch T10c: what `Reviewer._ocr` (aisef2/app/adapters.py) computes and hands to Open Code
Review, and what it records of the review. The adapter is driven through its public `review()` on a real git
repository (baseline commit, then the candidate), with the journal's `story/begin` naming the baseline as the story's
parent, a real budget over the sessions' streams, and a FAKE `ocr` executable (pinned by its sha256 like the real one).
The fake writes OCR's documents and records what it was started with: its environment, the file named by --rule and
the state of its HOME. The candidate's change set holds an added, a modified and a deleted product file and, outside
the product roots, a modified, an added and a deleted one (a `.cfg` product file the finder cannot read is added by
the one test that needs it). Each class pins one behaviour:

* OcrScope: which changed files are `required` of the review, which are `deleted`, and the decision it feeds (a review
  that omits a required file is never accepted under fix-loop, a deleted file is never required);
* OcrCoverageRecord: the coverage the session row states — status, why, and the required files the finder cannot read;
* OcrProcessInputs: the finder's environment (the route's, the endpoint, git's isolation, which wins over the route's
  own git variables), the controller's rule file and the HOME of its own;
* OcrCacheTokens: the review's cache read/write tokens, where the budget and the usage account read them;
* OcrRedaction: no secret the finder can print stays in the session's evidence.

Nothing here reaches a real model, provider or client."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client, usage  # noqa: E402
from aisef2.arch.enums import ControlProjection  # noqa: E402
from aisef2.journal.format2 import OperationOutcome as O  # noqa: E402
from aisef2.orchestrate.adapters import CapabilityUnrunnable  # noqa: E402
from aisef2.orchestrate.workspace import _ISOLATED_GIT  # noqa: E402
from tests.v2 import test_v21_review_chain as chain  # noqa: E402
from tests.v2.test_app_run import git  # noqa: E402

#: the candidate's work (None deletes): against the baseline below it adds app/__main__.py and the tests, modifies
#: app/cli.py and README.md, deletes app/legacy.py (a product file) and docs/OLD.md (outside the product roots) and adds
#: docs/CHANGES.md
CHANGE = {"app/cli.py": chain.FIXED, "app/__main__.py": chain.ENTRY, "tests/__init__.py": "",
          "tests/test_cli.py": chain.TEST, "app/legacy.py": None, "docs/OLD.md": None, "docs/CHANGES.md": "# changes\n",
          "README.md": "# calc 2\n"}
BASELINE = {"app/__init__.py": "", "app/cli.py": "def main(args):\n    return 1\n", "app/legacy.py": "VALUE = 1\n",
            "docs/requirements.md": chain.REQUIREMENTS, "docs/OLD.md": "# old\n", "README.md": "# calc\n"}
#: the product files the review must cover: added or modified under app/ and tests/, never a deleted one
REQUIRED = ["app/__main__.py", "app/cli.py", "tests/__init__.py", "tests/test_cli.py"]
ENDPOINT = "https://provider.invalid/v1"

#: Open Code Review's command line and documents (manifest v1, preview). It reviews the changed files under app/ and
#: tests/ whatever its rule holds (the rule is recorded, and asserted as data); the preview lists a deleted file the way
#: the real preview does (will_review false, exclude_reason deleted); `.cfg` is a file its finder cannot read
#: (unsupported_ext). The scenario: `omit` — a path the complete-looking manifest does not list as completed;
#: `summary_extra`; `echo_env` — variables whose values its message repeats. Every start is recorded (proc-NN.json):
#: argv, environment, the rule's content, HOME's state; and, beside it, the message it printed.
FAKE_OCR = r'''import hashlib, json, os, pathlib, subprocess, sys
argv = sys.argv[1:]
here = pathlib.Path(__file__).parent
def opt(name):
    return argv[argv.index(name) + 1]
repo, base, head, out = opt("--repo"), opt("--from"), opt("--to"), opt("--output")
rule = json.loads(pathlib.Path(opt("--rule")).read_text(encoding="utf-8"))
home = pathlib.Path(os.environ.get("HOME", ""))
(here / f"proc-{len(sorted(here.glob('proc-*.json'))):02d}.json").write_text(json.dumps({
    "preview": "--preview" in argv, "argv": argv, "env": dict(os.environ), "rule": rule,
    "home_isdir": home.is_dir(), "home_listdir": sorted(os.listdir(home)) if home.is_dir() else None}), encoding="utf-8")
rows = subprocess.run(["git", "-C", repo, "diff", "--name-status", "--no-renames", base + ".." + head],
                      capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
roots = {"app", "tests"}
changed = [r.split("\t", 1) for r in rows if "\t" in r]
selected = [(k, p) for k, p in changed if p.split("/")[0] in roots]
if "--preview" in argv:
    files = [{"path": p, "status": {"A": "added", "D": "deleted"}.get(k, "modified"), "insertions": 1, "deletions": 0,
              "will_review": k != "D" and not p.endswith(".cfg"),
              **({"exclude_reason": "deleted"} if k == "D" else {"exclude_reason": "unsupported_ext"} if p.endswith(".cfg") else {})}
             for k, p in selected]
    pathlib.Path(out).write_text(json.dumps({"files": files, "total_files": len(files)}), encoding="utf-8")
    raise SystemExit(0)
sc = json.loads((here / "scenario.json").read_text(encoding="utf-8"))
def item(p):
    return {"item_id": hashlib.sha256("\x00".join(["review", "range", p, p]).encode("utf-8")).hexdigest(), "path": p}
done = [item(p) for k, p in selected if k != "D" and not p.endswith(".cfg")]
manifest = {"schema_version": "ocr.run-manifest/v1", "operation": "review", "terminal_state": "complete" if done else "skipped",
            "input": {"mode": "range", "resolved_base": base, "resolved_head": head},
            "execution": {"ocr_version": "v1.12.12"},
            "coverage": {"selected": list(done), "completed": [i for i in done if i["path"] != sc.get("omit")],
                         "reused": [], "failed": [], "waived": []}}
doc = {"status": "complete", "comments": [], "manifest": manifest, "tool_calls": {"failure_details": []},
       "summary": {"input_tokens": 300, "output_tokens": 60, "total_tokens": 360, **sc.get("summary_extra", {})},
       "message": "reviewed " + " ".join(os.environ.get(n, "") for n in sc.get("echo_env", []))}
(here / "printed.json").write_text(json.dumps(doc["message"]), encoding="utf-8")
pathlib.Path(out).write_text(json.dumps(doc), encoding="utf-8")
raise SystemExit(0)
'''


@unittest.skipUnless(os.name == "posix", "the fake finder is a script started by its shebang")
class OcrBase(unittest.TestCase):
    """A repository with the baseline and the candidate, the project, a finder and a reviewer to run on it."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        self.change(BASELINE, "baseline")
        self.baseline = git(self.repo, "rev-parse", "HEAD")
        self.change(CHANGE, "candidate")
        self.project = bundle.load(chain.cli_bundle(self.baseline))
        self.finder = self.tmp / "bin" / "ocr"
        self.finder.parent.mkdir()
        self.finder.write_text(f"#!{sys.executable}\n" + FAKE_OCR)
        self.finder.chmod(0o755)
        self.logs = self.tmp / "out" / "sessions"
        self.scope = types.SimpleNamespace(story_id="S1", root=str(self.repo))
        self.events = [types.SimpleNamespace(seq=1, type="story/begin", data={"story_id": "S1", "parent": self.baseline})]
        self.run = types.SimpleNamespace(events=self.events, state=lambda proj: {"S1": {"attempt": 1}}
                                         if proj is ControlProjection.STORY_STATE else None)

    def change(self, files: dict, message: str) -> None:
        for rel, text in files.items():
            target = self.repo / rel
            if text is None:
                git(self.repo, "rm", "-q", "--", rel)     # the candidate deletes it: git removes it from tree and index
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)

    def review(self, policy: str = "fix-loop", *, scenario: dict | None = None, secrets: tuple[str, ...] = (),
               token: str = "route-key-0123456789", route_env: dict | None = None):
        """One review of the candidate by the reviewer the run builds (run.py): what `review()` returns, or raises."""
        (self.finder.parent / "scenario.json").write_text(json.dumps(scenario or {}), encoding="utf-8")
        review = {"policy": policy, "min_severity": "high", "finder": "ocr",
                  "ocr": {"exe": str(self.finder), "sha256": hashlib.sha256(self.finder.read_bytes()).hexdigest(),
                          "timeout_min": 1, "max_tokens": 4000}}
        self.budget = client.Budget({k: 10 ** 6 for k in client.Budget.KEYS}, dict.fromkeys(client.Budget.KEYS, 0), self.logs,
                                    lambda: 1)
        self.reviewer = ad.Reviewer(self.run, self.project, self.logs, {"budget": self.budget, "secrets": secrets}, 60,
                                    review=review, route={"url": ENDPOINT, "token": token, "model": "model-1",
                                                          "env": {"PATH": os.environ["PATH"], **(route_env or {})}})
        return self.reviewer.review(self.scope, ("C-SUM",))

    @property
    def row(self) -> dict:
        (row,) = self.reviewer.sessions
        return row

    def starts(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.finder.parent.glob("proc-*.json"))]

    def review_start(self) -> dict:
        """What the finder was started with for the review itself (the preview is the start before it)."""
        (start,) = [s for s in self.starts() if not s["preview"]]
        return start


class OcrScope(OcrBase):
    """The review's scope is AISEF's, computed from git: the candidate's added or modified files under the product
    roots. A deleted file is never required (OCR cannot complete it); a file outside the roots is not the review's; a
    review that does not complete a required file is never accepted under fix-loop (TRACEABILITY P-4.2a).
    Pins aisef2/app/adapters.py::Reviewer._ocr [45, 105, 121, 124, 195, 225, 242, 257]."""

    def test_required_is_the_changed_product_files_and_deleted_the_removed_ones(self):
        result = self.review()
        self.assertEqual(result.outcome, O.COMPLETED)       # a story that deletes a product file is not refused
        self.assertEqual(self.row.get("required"), REQUIRED)    # docs/CHANGES.md and README.md: changed, outside the roots
        # the removed product file; docs/OLD.md was removed too but is not the review's to account for
        self.assertEqual(self.row.get("deleted"), ["app/legacy.py"])
        self.assertEqual(self.row["coverage"]["status"], "COMPLETE")

    def test_a_required_file_the_review_did_not_complete_is_refused_under_fix_loop(self):
        """The manifest says complete (exit 0, the right range and version) but `completed` lacks app/cli.py."""
        with self.assertRaises(CapabilityUnrunnable) as refused:
            self.review("fix-loop", scenario={"omit": "app/cli.py"})
        self.assertIn("app/cli.py", str(refused.exception))
        self.assertIn("INDETERMINATE", str(refused.exception))
        self.assertEqual(self.row["coverage"]["status"], "INDETERMINATE")

    def test_under_advisory_the_omission_is_recorded_and_does_not_refuse(self):
        result = self.review("advisory", scenario={"omit": "app/cli.py"})
        self.assertEqual(result.outcome, O.COMPLETED)
        self.assertIn("INDETERMINATE", result.detail)
        self.assertEqual(self.row["required"], REQUIRED)
        self.assertEqual(self.row["coverage"]["status"], "INDETERMINATE")
        self.assertTrue(any("app/cli.py" in r for r in self.row["coverage"]["reasons"]), self.row["coverage"])
        self.assertFalse(any("app/legacy.py" in r for r in self.row["coverage"]["reasons"]), self.row["coverage"])


class OcrCoverageRecord(OcrBase):
    """The session row's coverage is an auditor's evidence of the review's central decision: its status, why it was not
    complete, and which required files the finder could not read (named, not counted against it).
    Pins aisef2/app/adapters.py::Reviewer._ocr [47, 48, 113, 114]."""

    def test_a_complete_review_states_no_reason_and_no_unreadable_file(self):
        self.review()
        cov = self.row["coverage"]
        self.assertEqual((cov.get("status"), cov.get("reasons"), cov.get("not_reviewable")), ("COMPLETE", [], []), cov)

    def test_an_incomplete_review_states_why(self):
        self.review("advisory", scenario={"omit": "tests/test_cli.py"})
        cov = self.row["coverage"]
        self.assertEqual(cov.get("status"), "INDETERMINATE")
        self.assertIsInstance(cov.get("reasons"), list)
        self.assertTrue(any("tests/test_cli.py" in r for r in cov["reasons"]), cov)
        self.assertEqual(cov.get("not_reviewable"), [])

    def test_a_required_file_the_finder_cannot_read_is_named_and_not_counted_against_the_review(self):
        self.change({"app/settings.cfg": "[calc]\n"}, "a file OCR cannot read")
        result = self.review("fix-loop")
        self.assertEqual(result.outcome, O.COMPLETED)
        self.assertEqual(self.row["required"], sorted([*REQUIRED, "app/settings.cfg"]))
        cov = self.row["coverage"]
        self.assertEqual((cov.get("status"), cov.get("reasons")), ("COMPLETE", []), cov)
        self.assertEqual(cov.get("not_reviewable"), ["app/settings.cfg"])


class OcrProcessInputs(OcrBase):
    """What the finder is started with is the controller's: the route's environment (the operator's PATH and the
    variables the settings name), the attested endpoint, git's B4 isolation (the finder runs git in the candidate's
    checkout), a HOME of its own, and the rule that selects the product roots.
    Pins aisef2/app/adapters.py::Reviewer._ocr [62, 63, 133, 136, 197, 198, 199, 248]."""

    NAMED = "operator-named-value-0123"
    TOKEN = "route-key-for-ocr-0123456789"

    def setUp(self) -> None:
        super().setUp()
        self.operator_path = os.environ["PATH"]
        # the route's environment is the operator's (client.environment): its HOME, its XDG directories and, here, git
        # variables too; the controller's isolation (a HOME of its own, B4) must win over every one of them
        self.operator_home = str(self.tmp / "operator-home")
        result = self.review(token=self.TOKEN, route_env={
            "AISEF_TEST_NAMED": self.NAMED, "XDG_CONFIG_HOME": str(self.tmp), "HOME": self.operator_home,
            "GIT_CONFIG_GLOBAL": str(self.tmp / "operator.gitconfig"), "GIT_TERMINAL_PROMPT": "1"})
        self.assertEqual(result.outcome, O.COMPLETED)
        self.env = self.review_start()["env"]

    def test_the_finder_has_the_routes_environment(self):
        self.assertEqual(self.env.get("PATH"), self.operator_path)
        self.assertEqual(self.env.get("AISEF_TEST_NAMED"), self.NAMED)

    def test_the_finder_reaches_the_route_and_inherits_no_client_configuration(self):
        self.assertEqual((self.env["OCR_LLM_URL"], self.env["OCR_LLM_TOKEN"], self.env["OCR_LLM_MODEL"]),
                         (ENDPOINT, self.TOKEN, "model-1"))
        self.assertEqual(self.env["OCR_NO_UPDATE"], "1")
        self.assertEqual([k for k in self.env if k.startswith(("XDG_", "ANTHROPIC_", "OTEL_"))], [])

    def test_git_run_by_the_finder_is_under_the_isolated_configuration(self):
        """B4: no system or global configuration, no prompt, and the forced settings (hooks path, fsmonitor, signing,
        autocrlf, maintenance) at command scope — for the git the finder runs as for every git the kernel runs, and
        whatever the operator's route says about them."""
        self.assertEqual(self.env.get("GIT_CONFIG_NOSYSTEM"), "1")
        self.assertEqual(self.env.get("GIT_CONFIG_GLOBAL"), os.devnull)       # not the operator's gitconfig
        self.assertEqual(self.env.get("GIT_TERMINAL_PROMPT"), "0")            # not the operator's "1"
        for key, value in _ISOLATED_GIT.items():
            self.assertEqual(self.env.get(key), value, key)

    def test_the_finder_has_a_home_of_its_own_that_is_empty_when_it_starts(self):
        starts = self.starts()
        self.assertEqual({s["preview"] for s in starts}, {True, False})       # the preview and the review itself
        for start in starts:
            self.assertNotEqual(start["env"].get("HOME"), self.operator_home)
            self.assertIs(start["home_isdir"], True, start["env"].get("HOME"))
            self.assertEqual(start["home_listdir"], [])

    def test_the_rule_the_finder_reads_selects_every_product_root(self):
        for start in self.starts():
            self.assertEqual(sorted(start["rule"].get("include") or []), ["app/**", "tests/**"])


class OcrCacheTokens(OcrBase):
    """The review's cache read and write tokens are billed classes: they are reported in the stream's finished step,
    where the usage account (by class) and the budget (input counts cache) read them.
    Pins aisef2/app/adapters.py::Reviewer._ocr [76, 155, 156, 157, 212, 213, 263, 264]."""

    def test_cache_tokens_of_the_summary_reach_the_stream_the_usage_account_and_the_budget(self):
        result = self.review(scenario={"summary_extra": {"cache_read_tokens": 40, "cache_write_tokens": 10}})
        self.assertEqual(result.outcome, O.COMPLETED)
        log = self.logs / "S1.reviewer.1.jsonl"
        (step,) = [e for e in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if e["type"] == "step_finish"]
        tokens = step["part"]["tokens"]
        self.assertEqual((tokens.get("input"), tokens.get("output"), tokens.get("cache")), (300, 60, {"read": 40, "write": 10}))
        by_class = usage.session_tokens(log)["tokens"]
        self.assertEqual([by_class[k] for k in ("input", "cache_read", "cache_write", "output")], [300, 40, 10, 60])
        self.assertEqual((self.row["tokens"]["input"], self.row["tokens"]["output"]), (350, 60))   # input counts the cache
        spent = self.budget.spend()
        self.assertEqual((spent["input_tokens"], spent["output_tokens"], spent["unaccounted"]), (350, 60, []))

    def test_a_summary_without_cache_fields_counts_none(self):
        self.review()
        by_class = usage.session_tokens(self.logs / "S1.reviewer.1.jsonl")["tokens"]
        self.assertEqual([by_class[k] for k in ("input", "cache_read", "cache_write", "output")], [300, 0, 0, 60])
        self.assertEqual((self.row["tokens"]["input"], self.row["tokens"]["output"]), (300, 60))


class OcrRedaction(OcrBase):
    """A secret the finder prints (its environment holds the operator's named variables and the provider key) is never
    left in the session's evidence: the operator's secrets from the session kwargs and the route's token by name,
    whatever its length. Pins aisef2/app/adapters.py::Reviewer._ocr [87, 88, 238]."""

    SECRET = "operator-secret-value-0123456789"
    SHORT_KEY = "zq7xk"        # under 8 characters: run.py keeps it out of the kwargs' secrets, so only its name redacts it

    def test_no_secret_the_finder_printed_stays_in_the_stream(self):
        result = self.review(scenario={"echo_env": ["OCR_LLM_TOKEN", "AISEF_TEST_NAMED"]}, secrets=(self.SECRET,),
                             token=self.SHORT_KEY, route_env={"AISEF_TEST_NAMED": self.SECRET})
        self.assertEqual(result.outcome, O.COMPLETED)
        printed = json.loads((self.finder.parent / "printed.json").read_text(encoding="utf-8"))
        self.assertIn(self.SECRET, printed)        # the finder did print both: otherwise nothing here is tested
        self.assertIn(self.SHORT_KEY, printed)
        stream = (self.logs / "S1.reviewer.1.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(self.SECRET, stream)
        self.assertNotIn(self.SHORT_KEY, stream)
        self.assertGreater(self.row.get("redacted") or 0, 0)
        self.assertEqual(self.row["redacted"], stream.count(client.REDACTED.decode("utf-8")))   # replacements, by their mark
        self.assertNotIn(self.SECRET, self.row["text"])
        self.assertNotIn(self.SHORT_KEY, self.row["text"])


if __name__ == "__main__":
    unittest.main()
