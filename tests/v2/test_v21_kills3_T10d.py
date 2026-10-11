"""V2.1 (owner B-03, kills batch T10d): the survivors of aisef2/app/adapters.py::Reviewer._ocr — Open Code Review as the
review stage's finder. Each class states the requirement it pins and the mutants (the `[N]` of the campaign's survivor
view) that depend on it.

The unit is driven the way the review stage drives it: a real two-commit checkout, the calc project, a real
`client.Budget` over the run's session directory, and a scripted finder executable that is pinned by its sha256 like the
real one and writes OCR's documents (manifest v1, preview) from a scenario. What the orchestrator does with the result is
orchestrate/review.py's, and is pinned there and in test_v21_review_chain: `ProviderOutage` is the provider's
(PROVIDER_UNAVAILABLE), `CapabilityUnrunnable` is CAPABILITY_UNRUNNABLE, and `Reviewed.detail` is the journal's
provider/result detail. Nothing here reaches a network, a model or a real finder."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client, review_ocr, usage  # noqa: E402
from aisef2.arch.enums import ControlProjection  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2 import test_v21_review_chain as chain  # noqa: E402

#: the finder: OCR's command line and documents, scripted by scenario.json beside it. A preview lists the changed files
#: (`preview_exclude` {path: exclude_reason} marks some as not reviewed); a review records its argv and what the
#: session stream held when it started, then writes a manifest — in which a preview-excluded path is NOT completed, as
#: the real binary leaves it (`list_excluded` lists it anyway), `failed` {classes} makes it a partial run whose failed
#: items carry those classifications, and `summary` replaces the token summary.
FAKE_OCR = r'''import hashlib, json, pathlib, subprocess, sys
argv = sys.argv[1:]
here = pathlib.Path(__file__).parent
sc = json.loads((here / "scenario.json").read_text(encoding="utf-8"))
def opt(name):
    return argv[argv.index(name) + 1]
repo, base, head, out = opt("--repo"), opt("--from"), opt("--to"), opt("--output")
rows = subprocess.run(["git", "-C", repo, "diff", "--name-status", "--no-renames", base + ".." + head],
                      capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
changed = [p for k, p in (r.split("\t", 1) for r in rows if "\t" in r) if k != "D"]
excluded = sc.get("preview_exclude", {})
if "--preview" in argv:
    files = [dict({"path": p, "status": "added", "insertions": 1, "deletions": 0, "will_review": p not in excluded},
                  **({"exclude_reason": excluded[p]} if p in excluded else {})) for p in changed]
    pathlib.Path(out).write_text(json.dumps({"files": files, "total_files": len(files)}), encoding="utf-8")
    raise SystemExit(0)
(here / "argv.json").write_text(json.dumps(argv), encoding="utf-8")
log = pathlib.Path(sc["log"])
(here / "log-at-start.json").write_text(json.dumps({"exists": log.exists(), "text": log.read_text(encoding="utf-8")
                                                    if log.exists() else None}), encoding="utf-8")
def item(p):
    return {"item_id": hashlib.sha256("\x00".join(["review", "range", p, p]).encode("utf-8")).hexdigest(), "path": p}
done = [item(p) for p in changed if p not in excluded or sc.get("list_excluded")]
manifest = {"schema_version": "ocr.run-manifest/v1", "operation": "review",
            "terminal_state": "complete" if done else "skipped",
            "input": {"mode": "range", "resolved_base": base, "resolved_head": head},
            "execution": {"ocr_version": sc["version"]},
            "coverage": {"selected": done, "completed": done, "reused": [], "failed": [], "waived": []}}
doc = {"status": "complete", "comments": [], "manifest": manifest, "tool_calls": {"failure_details": []},
       "summary": sc.get("summary", {"input_tokens": 300, "output_tokens": 60, "total_tokens": 360}), "message": "reviewed"}
if sc.get("failed"):
    classes = sc["failed"]
    manifest["terminal_state"] = doc["status"] = "partial"
    manifest["coverage"]["completed"] = []
    manifest["coverage"]["failed"] = [dict(i, classification=classes[min(n, len(classes) - 1)], reason="scripted")
                                      for n, i in enumerate(done)]
pathlib.Path(out).write_text(json.dumps(doc), encoding="utf-8")
raise SystemExit(0)
'''

DEVELOPER_TOKENS = {"input": 400, "output": 30, "reasoning": 5, "cache": {"read": 20, "write": 0}}


class _Finder(unittest.TestCase):
    """A Reviewer for Open Code Review (settings review.finder = "ocr") over a base commit and a candidate commit that
    changes the calc command under the product roots (no test of its own)."""

    LIMITS = {"provider_requests": 20, "turns": 50, "input_tokens": 100000, "output_tokens": 10000}
    PREFLIGHT = {"provider_requests": 0, "turns": 0, "input_tokens": 0, "output_tokens": 0}
    EXTRA: dict = {}        # more files of the candidate
    ROUTE = {"url": "http://127.0.0.1:9/v1", "token": "sk-test-not-a-key", "model": "model-1"}

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        e2e.git(self.repo, "init", "-q", "-b", "main")
        for rel, text in {"app/__init__.py": "", "docs/requirements.md": chain.REQUIREMENTS}.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text, encoding="utf-8")
        e2e.git(self.repo, "add", "-A")
        e2e.git(self.repo, "commit", "-q", "-m", "baseline")
        self.base = e2e.git(self.repo, "rev-parse", "HEAD")
        for rel, text in {**chain.answer(chain.FIXED), **self.EXTRA}.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text, encoding="utf-8")
        e2e.git(self.repo, "add", "-A")
        e2e.git(self.repo, "commit", "-q", "-m", "candidate")
        self.head = e2e.git(self.repo, "rev-parse", "HEAD")
        self.project = bundle.load(chain.cli_bundle(self.base))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.exe = self.bin / "ocr"
        self.exe.write_text(f"#!{sys.executable}\n" + FAKE_OCR, encoding="utf-8")
        self.exe.chmod(0o755)
        self.sha = hashlib.sha256(self.exe.read_bytes()).hexdigest()
        self.logs = self.tmp / "out" / "sessions"
        self.log = self.logs / "S1.reviewer.1.jsonl"
        self.scope = types.SimpleNamespace(story_id="S1", root=str(self.repo))
        self.scenario()

    def scenario(self, **sc) -> None:
        sc = {"version": review_ocr.OCR["version"], "log": str(self.log), **sc}
        (self.bin / "scenario.json").write_text(json.dumps(sc), encoding="utf-8")

    def reviewer(self, policy: str = "fix-loop", requests: int = 2, limits: dict | None = None,
                 preflight: dict | None = None, parent: str | None = None) -> ad.Reviewer:
        """The Reviewer of story S1's first attempt; `requests` provider requests are journaled (the review's own among
        them: orchestrate.review journals the request before the finder is called)."""
        self.budget = client.Budget(limits or self.LIMITS, preflight or self.PREFLIGHT, self.logs, requests=lambda: requests)
        begin = types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": parent or self.base})
        run = types.SimpleNamespace(events=[begin], state=lambda proj: {"S1": {"attempt": 1}}
                                    if proj is ControlProjection.STORY_STATE else None)
        review = {"policy": policy, "min_severity": "high", "finder": "ocr",
                  "ocr": {"exe": str(self.exe), "sha256": self.sha, "timeout_min": 1, "max_tokens": 4000}}
        route = {**self.ROUTE, "env": {"PATH": os.environ.get("PATH", "")}}
        return ad.Reviewer(run, self.project, self.logs, {"budget": self.budget}, 60.0, review=review, route=route)

    def finder_argv(self) -> list[str]:
        return json.loads((self.bin / "argv.json").read_text(encoding="utf-8"))


POSIX = unittest.skipUnless(os.name == "posix", "the finder is a script started by its shebang")


@POSIX
class OcrPreview(_Finder):
    """Reviewer._ocr [142] [251] — "L195 string 'preview.json' emptied" (the read), "L193 string 'preview.json' emptied"
    (the write): the preview the finder is told to write is the document the controller reads, and the coverage is
    decided with it (review_ocr module docstring, "What a finder may skip"). A required path the preview excludes as
    unsupported_ext is one this finder cannot read: named in the coverage, not counted against it — the story is not
    refused for it. A required path the preview excludes for any other reason is a gap, even when the manifest lists it
    completed. Without the preview's document the first is a spurious INDETERMINATE (fail-closed) and the second is
    COMPLETE (the gap is never seen)."""

    EXTRA = {"app/settings.cfg": "mode = fast\n"}

    def test_a_file_the_finder_cannot_read_is_named_and_does_not_make_the_review_incomplete(self):
        self.scenario(preview_exclude={"app/settings.cfg": "unsupported_ext"})
        found, s, _ = self.reviewer()._ocr(self.scope, 1, self.head)      # fix-loop: an incomplete review would raise
        self.assertEqual(found, [])
        self.assertEqual(s["coverage"], {"status": review_ocr.COMPLETE, "reasons": [], "not_reviewable": ["app/settings.cfg"]})
        self.assertIn("app/settings.cfg", s["required"])                  # the scope is the controller's: still required

    def test_a_required_file_the_preview_excludes_for_another_reason_refuses_the_review_under_fix_loop(self):
        self.scenario(preview_exclude={"app/cli.py": "default_path"}, list_excluded=True)
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            self.reviewer()._ocr(self.scope, 1, self.head)
        self.assertIn("app/cli.py", str(c.exception))
        self.assertIn("default_path", str(c.exception))

    def test_under_advisory_the_excluded_file_is_recorded_in_the_coverage(self):
        self.scenario(preview_exclude={"app/cli.py": "default_path"}, list_excluded=True)
        _, s, _ = self.reviewer(policy="advisory")._ocr(self.scope, 1, self.head)
        self.assertEqual(s["coverage"]["status"], review_ocr.INDETERMINATE)
        self.assertIn("app/cli.py", " ".join(s["coverage"]["reasons"]))
        self.assertEqual(s["coverage"]["not_reviewable"], [])


@POSIX
class OcrCoverageDetail(_Finder):
    """Reviewer._ocr [185] — "L232 conditional negated" (and, incidentally, [271] — "L232 string '; ' emptied"): the
    review's detail (Reviewed.detail, the journal's provider/result detail: the only place in it that says why an
    advisory run committed on an incomplete review) lists the reasons of the coverage when there are some, apart from
    one another, and lists none for a complete review. Compared with the session's own coverage record, not with
    wording."""

    def test_an_incomplete_review_s_detail_carries_the_reasons_of_its_coverage(self):
        self.scenario(failed=["timeout"])
        rev = self.reviewer(policy="advisory")
        reviewed = rev.review(self.scope, ("C-SUM",))
        coverage = rev.sessions[-1]["coverage"]
        self.assertEqual(coverage["status"], review_ocr.INDETERMINATE)
        self.assertGreater(len(coverage["reasons"]), 1)
        self.assertLess(sum(map(len, coverage["reasons"])), 300)       # the detail's 300 characters cut none of them off
        self.assertIn("coverage INDETERMINATE", reviewed.detail)
        end = None
        for reason in coverage["reasons"]:         # every reason of the record occurs, in its order ...
            start = reviewed.detail.find(reason, end or 0)
            self.assertNotEqual(start, -1, reason)
            if end is not None:
                self.assertGreater(start, end)     # ... and is set apart from the one before it, whatever the separator
            end = start + len(reason)

    def test_a_complete_review_s_detail_lists_no_reasons(self):
        rev = self.reviewer()
        reviewed = rev.review(self.scope, ("C-SUM",))
        self.assertEqual(rev.sessions[-1]["coverage"], {"status": review_ocr.COMPLETE, "reasons": [], "not_reviewable": []})
        self.assertIn("coverage COMPLETE", reviewed.detail)
        self.assertNotIn("(", reviewed.detail.split("coverage COMPLETE", 1)[1])


class OcrGitDiffRefusal(_Finder):
    """Reviewer._ocr [190] [191] — "L169 string '..' emptied", "L169 string ' exited ' emptied": a review whose change
    cannot be listed (the journal's parent of the story is no object of the checkout) is refused as CapabilityUnrunnable,
    and the refusal names the range it could not list — the two revisions, abbreviated, joined as git writes a range —
    and git's exit status as a token of its own after it: the operator's lead to the cause. Asserted by structure
    (range, then status), not by the words around them or by how many characters of a revision are shown."""

    def test_the_refusal_names_the_range_and_the_exit_status(self):
        parent = "0" * 40
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            self.reviewer(parent=parent)._ocr(self.scope, 1, self.head)
        status = subprocess.run(["git", "-C", str(self.repo), "diff", "--name-status", "--no-renames", f"{parent}..{self.head}"],
                                capture_output=True).returncode
        self.assertNotEqual(status, 0)
        # <base>..<head>, each an abbreviated revision that ends where it ends (not run into what follows), then the status
        self.assertRegex(str(c.exception), rf"\b{parent[:7]}[0-9a-f]*\.\.{self.head[:7]}[0-9a-f]*\b.*\b{status}\b")


class OcrCeiling(_Finder):
    """Reviewer._ocr [196] — "L176 True->False" (`budget.reached(in_progress=True)`): the review is the provider request
    in progress (orchestrate.review journals it before the finder is called), so the request ceiling ends it only when
    EXCEEDED — a run whose limit is exactly the requests it needs still reviews its story; every other ceiling ends it
    at its value (app/client.Budget.reached)."""

    @POSIX
    def test_the_review_whose_request_is_the_last_one_allowed_runs(self):
        limits = {**self.LIMITS, "provider_requests": 3}
        _, s, _ = self.reviewer(requests=3, limits=limits)._ocr(self.scope, 1, self.head)      # spent == limit
        self.assertEqual(s["coverage"]["status"], review_ocr.COMPLETE)
        self.assertTrue(self.log.exists())

    def test_a_request_beyond_the_ceiling_is_refused_as_the_providers_naming_the_ceiling(self):
        limits = {**self.LIMITS, "provider_requests": 3}
        with self.assertRaises(ad.ProviderOutage) as c:
            self.reviewer(requests=4, limits=limits)._ocr(self.scope, 1, self.head)
        self.assertIn("max_provider_requests", str(c.exception))
        self.assertIn("4 of 3", str(c.exception))
        self.assertFalse(self.log.exists())                   # nothing was started

    def test_another_ceiling_at_its_value_ends_the_review(self):
        preflight = {**self.PREFLIGHT, "turns": self.LIMITS["turns"]}
        with self.assertRaises(ad.ProviderOutage) as c:
            self.reviewer(preflight=preflight)._ocr(self.scope, 1, self.head)
        self.assertIn("max_turns", str(c.exception))
        self.assertFalse(self.log.exists())


@POSIX
class OcrTokenCounts(_Finder):
    """Reviewer._ocr [211] — "L207 And swapped": OCR's summary counts become the stream's one step's tokens only when
    both are numbers; a JSON boolean is no count (a bool is an int to the readers, which would take `true` for one
    token). A step without tokens is unaccounted: the budget stops further paid work and the usage account's cost is
    unknown, rather than a spend of one token being recorded."""

    def finish(self, **summary):
        self.scenario(summary=summary)
        _, s, _ = self.reviewer()._ocr(self.scope, 1, self.head)
        return s, self.budget.spend()["unaccounted"], usage.session_tokens(self.log)

    def assert_no_token_report(self, **summary):
        s, unaccounted, used = self.finish(**summary)
        self.assertEqual(s["tokens"], {"input": 0, "output": 0})
        self.assertTrue(any("S1.reviewer.1.jsonl" in u and "report no tokens" in u for u in unaccounted), unaccounted)
        self.assertEqual((used["steps"], used["steps_without_tokens"]), (1, 1))
        self.assertEqual((used["tokens"]["input"], used["tokens"]["output"]), (0, 0))

    def test_counts_that_are_numbers_are_the_steps_tokens(self):
        s, unaccounted, used = self.finish(input_tokens=300, output_tokens=60)
        self.assertEqual((s["tokens"], unaccounted), ({"input": 300, "output": 60}, []))
        self.assertEqual((used["steps"], used["steps_without_tokens"]), (1, 0))

    def test_a_boolean_input_count_is_no_token_report(self):
        self.assert_no_token_report(input_tokens=True, output_tokens=60)

    def test_a_boolean_output_count_is_no_token_report(self):
        self.assert_no_token_report(input_tokens=300, output_tokens=True)


@POSIX
class OcrRoom(_Finder):
    """Reviewer._ocr [229] [230] — "L188 element 0 dropped", "L188 element 1 dropped": the finder's token budget
    (`--max-tokens-budget`) is what the run can still pay: its remaining input tokens PLUS its remaining output tokens
    (limit less spend, spend as the budget counts it: preflight and the streams so far — prompt and cached tokens as
    input, completion and reasoning as output). Output alone understates it and cuts a payable review short; input alone
    grants more than the output ceiling leaves."""

    def test_the_finder_is_given_the_remaining_input_and_output_tokens(self):
        preflight = {**self.PREFLIGHT, "provider_requests": 1, "input_tokens": 1000, "output_tokens": 200}
        self.logs.mkdir(parents=True)
        events = [{"type": "text", "part": {"text": "done"}}, {"type": "step_finish", "part": {"tokens": DEVELOPER_TOKENS}}]
        (self.logs / "S1.developer.1.jsonl").write_text("".join(json.dumps(x) + "\n" for x in events), encoding="utf-8")
        self.reviewer(preflight=preflight)._ocr(self.scope, 1, self.head)
        spent_in = 1000 + 400 + 20           # preflight + the developer's prompt and cache-read tokens
        spent_out = 200 + 30 + 5             # preflight + the developer's completion and reasoning tokens
        room = (self.LIMITS["input_tokens"] - spent_in) + (self.LIMITS["output_tokens"] - spent_out)
        argv = self.finder_argv()
        self.assertEqual(int(argv[argv.index("--max-tokens-budget") + 1]), room)


@POSIX
class OcrStream(_Finder):
    """Reviewer._ocr [231] [232] [252] [253] [254] [262] — "L198 dict entry 0/1 dropped", "L198 string 'type'/'finder'/
    'ocr_started'/'ocr ' emptied": the session stream (sessions/S1.reviewer.1.jsonl, evidence the record and --verify
    anchor by digest) is a stream of typed events like the client's, and it exists BEFORE the finder starts, holding
    one event that says an OCR review was started and by which finder — `finder` being the identity the session record
    (sessions[].finder) and each finding's source carry, "ocr <version>". No reader dispatches on that line (client and
    usage readers skip what they do not know; evidence_manifest hashes the file as written): what it pins is the
    evidence's schema — an event with its `type`, naming its producer — and its agreement with the record."""

    def test_the_stream_exists_before_the_finder_starts_and_names_the_finder_as_the_record_does(self):
        _, s, _ = self.reviewer()._ocr(self.scope, 1, self.head)
        self.assertEqual(s["finder"], "ocr " + review_ocr.OCR["version"])
        at_start = json.loads((self.bin / "log-at-start.json").read_text(encoding="utf-8"))
        self.assertTrue(at_start["exists"])
        first = [json.loads(x) for x in at_start["text"].splitlines()]
        self.assertTrue(first)
        # the event's name and the finder it names — what identifies the stream's producer; other keys are not pinned
        self.assertEqual((first[0].get("type"), first[0].get("finder")), ("ocr_started", s["finder"]))
        lines = [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(lines[0], first[0])              # the line that was there before the finder started stays first

    def test_the_marker_is_no_step_the_stream_reads_as_the_finders_one_session(self):
        self.reviewer()._ocr(self.scope, 1, self.head)
        seen = client.read_session(self.log)              # the budget's reader
        self.assertEqual((seen["error"], seen["text"], seen["turns"], seen["tokens"]),
                         (None, "reviewed", 1, {"input": 300, "output": 60}))
        used = usage.session_tokens(self.log)             # the usage account's reader
        self.assertEqual((used["steps"], used["steps_without_tokens"]), (1, 0))


@POSIX
class OcrProviderArm(_Finder):
    """Reviewer._ocr [266] [269] — "L227 string 'provider' emptied", "L227 string 'classification' emptied": a partial
    review in which every item that failed failed as the provider's (manifest items classified 'provider'; no
    run_failure, exit 0) is the provider's outage — ProviderOutage, PROVIDER_UNAVAILABLE, retried and limited as such —
    and not a capability failure of the review; one failed item that is not the provider's makes it the review's
    (fix-loop: CapabilityUnrunnable, CAPABILITY_UNRUNNABLE)."""

    def test_a_partial_review_every_failed_item_of_which_was_the_providers_is_an_outage(self):
        self.scenario(failed=["provider"])
        with self.assertRaises(ad.ProviderOutage):
            self.reviewer()._ocr(self.scope, 1, self.head)

    def test_a_partial_review_with_one_failed_item_that_was_not_the_providers_is_not(self):
        self.scenario(failed=["provider", "timeout"])
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            self.reviewer()._ocr(self.scope, 1, self.head)
        self.assertIn("INDETERMINATE", str(c.exception))


if __name__ == "__main__":
    unittest.main()
