"""V2.1 (owner B-03 round 3, item 5; reviewer's fix): the finder's own copies of a finding keep no secret of the run.

The owner asked that the reproducer be kept "đã che bí mật phù hợp" and that content that holds a secret be checked.
Open Code Review writes its documents (`preview.json`, `output.json`) and its stdout/stderr (`preview.log`, `ocr.log`)
into `<run>/review/<story>.<attempt>/`; a comment whose reproducer carries the run's secret left that secret there,
verbatim, outside the evidence manifest (measured on the implementer's tree: `review/S1.1/output.json`). Those files
are the finder's scratch, not evidence — the session stream and the statement's artifact are — but they sit in the run
directory an operator may hand to someone, so they are redacted with the run's own list once they have been read.

What a reader relies on, asserted here:

* no file under the finder's work directory holds a secret of the run (the client environment's value, and the
  provider token that is OCR's), whichever of its four files the finder wrote it to;
* the documents are still the documents — valid JSON, the comment present, the secret replaced where it was;
* the redaction came AFTER the read: the findings handed on still carry the reproducer as the finder wrote it, so the
  probe runs what was found (a redacted reproducer would reproduce something else).

Pins aisef2/app/adapters.py::Reviewer._ocr"""

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
from aisef2.app import bundle, client, review_ocr  # noqa: E402
from aisef2.arch.enums import ControlProjection  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2 import test_v21_review_chain as chain  # noqa: E402

SECRET = "s3cr3t-value-0123456789"
TOKEN = "ocr-token-5d0c77e1aa"

#: a finder that answers with one comment whose reproducer carries SECRET, and prints both secrets to stdout and to
#: stderr in its preview and in its review (what a finder that logs its environment or its prompt does)
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
print("finder says", sc["secret"], sc["token"])
print("and on stderr", sc["secret"], file=sys.stderr)
if "--preview" in argv:
    files = [{"path": p, "status": "added", "insertions": 1, "deletions": 0, "will_review": True,
              "note": "key " + sc["secret"]} for p in changed]
    pathlib.Path(out).write_text(json.dumps({"files": files, "total_files": len(files)}), encoding="utf-8")
    raise SystemExit(0)
def item(p):
    return {"item_id": hashlib.sha256("\x00".join(["review", "range", p, p]).encode("utf-8")).hexdigest(), "path": p}
done = [item(p) for p in changed]
manifest = {"schema_version": "ocr.run-manifest/v1", "operation": "review", "terminal_state": "complete",
            "input": {"mode": "range", "resolved_base": base, "resolved_head": head},
            "execution": {"ocr_version": sc["version"]},
            "coverage": {"selected": done, "completed": done, "reused": [], "failed": [], "waived": []}}
rep = {"clause": "R-CLI/1.2", "subject": {"kind": "cli_invocation", "locator": "app:__main__"},
       "stimulus": {"argv": ["1", "2", "3"], "stdin": {"text": "key=" + sc["secret"] + " token=" + sc["token"]}},
       "observable": {"exit_code": 2, "within_s": 20}}
doc = {"status": "complete", "comments": [{"path": "app/cli.py", "category": "bug", "severity": "high", "start_line": 4,
                                           "existing_code": "    return int(args[0])",
                                           "content": "uses " + sc["secret"] + "\n```aisef-reproducer\n"
                                                      + json.dumps(rep) + "\n```"}],
       "manifest": manifest, "tool_calls": {"failure_details": []},
       "summary": {"input_tokens": 300, "output_tokens": 60, "total_tokens": 360}, "message": "reviewed " + sc["secret"]}
pathlib.Path(out).write_text(json.dumps(doc), encoding="utf-8")
raise SystemExit(0)
'''


@unittest.skipUnless(os.name == "posix", "the finder is a script started by its shebang")
class TheFindersOwnFilesKeepNoSecret(unittest.TestCase):
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
        for rel, text in chain.answer(chain.FIXED).items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text, encoding="utf-8")
        e2e.git(self.repo, "add", "-A")
        e2e.git(self.repo, "commit", "-q", "-m", "candidate")
        self.head = e2e.git(self.repo, "rev-parse", "HEAD")
        self.project = bundle.load(chain.cli_bundle(self.base))
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        exe = bin_ / "ocr"
        exe.write_text(f"#!{sys.executable}\n" + FAKE_OCR, encoding="utf-8")
        exe.chmod(0o755)
        (bin_ / "scenario.json").write_text(json.dumps({"version": review_ocr.OCR["version"], "secret": SECRET,
                                                        "token": TOKEN}), encoding="utf-8")
        self.logs = self.tmp / "out" / "sessions"
        limits = {"provider_requests": 20, "turns": 50, "input_tokens": 100000, "output_tokens": 10000}
        budget = client.Budget(limits, {"provider_requests": 0, "turns": 0, "input_tokens": 0, "output_tokens": 0},
                               self.logs, requests=lambda: 2)
        begin = types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": self.base})
        run = types.SimpleNamespace(events=[begin], state=lambda proj: {"S1": {"attempt": 1}}
                                    if proj is ControlProjection.STORY_STATE else None)
        review = {"policy": "fix-loop", "min_severity": "high", "finder": "ocr",
                  "ocr": {"exe": str(exe), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "timeout_min": 1,
                          "max_tokens": 4000}}
        route = {"url": "http://127.0.0.1:9/v1", "token": TOKEN, "model": "model-1", "env": {"PATH": os.environ.get("PATH", "")}}
        self.reviewer = ad.Reviewer(run, self.project, self.logs, {"budget": budget, "secrets": (SECRET,)}, 60.0,
                                    review=review, route=route)
        self.scope = types.SimpleNamespace(story_id="S1", root=str(self.repo))
        self.work = self.tmp / "out" / "review" / "S1.1"

    def test_no_file_of_the_finder_holds_a_secret_of_the_run(self):
        found, s, _ = self.reviewer._ocr(self.scope, 1, self.head)
        files = sorted(p for p in self.work.rglob("*") if p.is_file())
        names = {p.name for p in files}
        self.assertGreaterEqual(names, {"preview.json", "preview.log", "output.json", "ocr.log"})
        for p in [*files, *self.logs.glob("*.jsonl")]:
            data = p.read_bytes()
            with self.subTest(file=p.name):
                self.assertNotIn(SECRET.encode(), data)
                self.assertNotIn(TOKEN.encode(), data)
        # the secret was there to be removed: each of the four files had it, and now has the marker in its place
        for name in ("preview.json", "preview.log", "output.json", "ocr.log"):
            with self.subTest(marked=name):
                self.assertIn(client.REDACTED, (self.work / name).read_bytes())
        self.assertEqual(len(found), 1)
        self.assertTrue(s["redacted"] > 0)

    def test_the_documents_are_still_documents_and_were_read_before_they_were_redacted(self):
        found, _, _ = self.reviewer._ocr(self.scope, 1, self.head)
        output = review_ocr.read_output(self.work / "output.json")
        preview = review_ocr.read_output(self.work / "preview.json")
        self.assertIsNotNone(output)
        self.assertIsNotNone(preview)
        (comment,) = output["comments"]
        self.assertEqual(comment["category"], "bug")
        self.assertIn(client.REDACTED.decode(), comment["content"])
        self.assertIn("app/cli.py", [f["path"] for f in preview["files"]])
        self.assertTrue(all(f["note"] == f"key {client.REDACTED.decode()}" for f in preview["files"]))
        # what was handed on is the finder's reproducer as written: the probe runs this, not the redacted copy
        (f,) = found
        self.assertEqual(f["reproducer"]["stimulus"]["stdin"]["text"], f"key={SECRET} token={TOKEN}")


if __name__ == "__main__":
    unittest.main()
