"""Survivors of aisef2/app/run.py::execute (mutation campaign 2, batch T13a): what a run writes about itself and about
the lineage it continues, what it refuses and what it hands to the finder.

Every test drives `execute` itself, offline, with the fake client and fake provider of test_app_run. A run that must
only show what it wrote at its start is stopped by a plan no calibration admits (`cals=()`): that refusal comes after
the claim, the lineage's account and the clone, and before any provider request, so those tests cost a fraction of a
run. The tests whose requirement is a run that completed (the manifest write, the finder's process, the continuation of
a finished run) share one, made once (WholeRun).

* the record a continuation writes of its predecessor (`continues`): the marker of a predecessor that never wrote its
  record, the lineage's spend at claim time, the refusals that name it;
* RUN.started.json, the identity a run killed by the OS still leaves;
* what the manifest write may and may not do to the run's own exception; the usage fault the record names;
* one clone of the project per run; every confinement problem named in the refusal; the environment the finder gets."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, confine, lineage, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from tests.v2 import test_app_run as app_run  # noqa: E402 — the module: its tests are not collected again
from tests.v2 import test_v21_review_chain as chain  # noqa: E402
from tests.v2.test_app_run import SETTINGS, provider  # noqa: E402

POSIX = unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
SPEND = ("provider_requests", "turns", "input_tokens", "output_tokens")


class Fixture(unittest.TestCase):
    """The one-story calc project, its settings and the fake client (test_app_run's own set-up, borrowed)."""

    setUp = app_run.ProductBase.setUp
    mode = app_run.ProductBase.mode

    def go(self, out: str = "out", *, admitted: bool = True, **kw) -> dict:
        kw.setdefault("transport", provider())
        return R.execute(self.project, self.settings, self.tmp / "source", self.tmp / out, client_exe=str(self.client),
                         cals=app_run.calibrations() if admitted else (), **kw)

    def stopped(self, out: str = "out", **kw) -> dict:
        """A run refused at admission: its record and RUN.started.json, as written."""
        with self.assertRaisesRegex(R.RunRefused, "not admitted"):
            self.go(out, admitted=False, **kw)
        return json.loads((self.tmp / out / "RUN.json").read_text(encoding="utf-8"))


@POSIX
class StartedDocument(Fixture):
    def test_RUN_started_json_is_the_runs_identity_document(self):
        """RUN.started.json is what a run killed by the OS (no RUN.json) still says about itself: exactly its format,
        bundle, project, plan, start time, kernel, platform and the digest of its settings — each the value the record
        will carry, the settings' digest the one the RunSpec binds (the canonical, key-sorted one). (Those keys must be
        there; a document that says more is not a different contract.)
        Pins aisef2/app/run.py::execute [234, 271, 295, 297, 298, 299, 301, 319, 321, 322, 323, 325, 336]"""
        ticks: list[float] = []

        def clock() -> float:
            ticks.append(1_000_000.0 + len(ticks))
            return ticks[-1]
        rec = self.stopped(clock=clock)
        started = json.loads((self.tmp / "out" / R.STARTED).read_text(encoding="utf-8"))
        identities = {"bundle_digest", "format", "kernel_digest", "plan_hash", "platform", "project", "settings_sha256",
                      "started"}
        self.assertEqual(sorted(identities - set(started)), [], "identities the document lacks")
        # the values, from the inputs and the environment — not from the record
        self.assertEqual(started["format"], R.FORMAT)
        self.assertEqual(started["bundle_digest"], self.project.digest)
        self.assertEqual(started["project"], self.project.name)
        self.assertEqual(started["plan_hash"], self.project.plan.plan_hash)
        self.assertIn(started["started"], ticks)        # a reading of the run's own clock
        self.assertEqual(started["kernel_digest"], R.kernel_digest())
        self.assertEqual(started["platform"], {"system": platform.system().lower(), "python": platform.python_version()})
        # the settings' digest: canonical (sorted keys) — the shared SETTINGS are not in sorted order, so a digest of the
        # document as given is another digest
        content = self.settings.content
        self.assertNotEqual(list(content), sorted(content))
        canonical = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        self.assertEqual(started["settings_sha256"], canonical)
        self.assertEqual(started["settings_sha256"], R.layers_of(self.project, self.settings)["settings_sha256"]["value"])
        # and it is a copy: the record carries the same values
        for k in started.keys() - {"settings_sha256"}:      # the record names the settings itself, not their digest
            self.assertEqual(rec[k], started[k], k)


@POSIX
class OneClone(Fixture):
    def test_a_run_clones_the_project_once_into_its_own_directory(self):
        """The run clones the project once, into <out>/repo, and checks that clone where it is: a second clone is a
        second copy of the repository in the system's temporary directory, outside the run directory that holds
        everything the run made. Counted at the one function the module reaches git through.
        Pins aisef2/app/run.py::execute [144]"""
        with mock.patch.object(R, "git", wraps=R.git) as spy:
            self.stopped()      # the clone and the checks of the repository come before admission
        clones = [c.args for c in spy.call_args_list if len(c.args) > 1 and c.args[1] == "clone"]
        self.assertEqual(len(clones), 1, clones)
        self.assertEqual(clones[0][-1], str(self.tmp / "out" / "repo"))


@POSIX
class ManifestWrite(Fixture):
    def test_a_manifest_that_cannot_be_written_never_replaces_the_runs_own_failure(self):
        """A run that already failed keeps the exception it failed with (a refusal is a status-2 refusal, an
        interruption an interruption): the manifest's OSError does not take its place.
        Pins aisef2/app/run.py::execute [183, 233]"""
        with mock.patch.object(R, "evidence_manifest", side_effect=OSError("disk full")), \
                self.assertRaisesRegex(R.RunRefused, "not admitted"):
            self.go(admitted=False)
        out = self.tmp / "out"
        self.assertEqual(json.loads((out / "RUN.json").read_text(encoding="utf-8"))["failure"]["type"], "RunRefused")
        self.assertFalse((out / R.MANIFEST).exists())


@POSIX
class UsageFault(Fixture):
    def test_a_usage_account_that_cannot_be_derived_is_named_and_not_re_derived_by_verify(self):
        """When the usage account cannot be derived the record still gets written and says so: `usage` is exactly
        {"error": "<ExceptionType>: <message>"} — the shape --verify reads (the key `error`) as a named fault it must
        not re-derive and refute the run for. A record that lost the key, the type or the message is re-derived and
        refuted, or says nothing.
        Pins aisef2/app/run.py::execute [230, 266, 267, 317]"""
        with mock.patch.object(R.usage, "usage", side_effect=RuntimeError("boom")):
            self.stopped()
        rec = json.loads((self.tmp / "out" / "RUN.json").read_text(encoding="utf-8"))
        usage = rec.get("usage") or {}
        self.assertIn("error", usage)
        self.assertRegex(str(usage.get("error")), r"RuntimeError\W+boom")     # type and message, told apart
        problems = verify(self.project, self.tmp / "out")["problems"]
        self.assertFalse([p for p in problems if "usage" in p], problems)


@POSIX
class ConfinementRefusal(Fixture):
    def test_every_problem_the_measurement_reported_is_named_in_the_refusal(self):
        """A run that asks for confinement the measurement does not confirm is refused before any provider request,
        and the refusal names every problem — told apart from one another — as the record does.
        Pins aisef2/app/run.py::execute [305]"""
        spec = {"backend": "bwrap", "bwrap": "/nonexistent/bwrap", "network": "host", "read_only": []}
        self.settings = settings.load({**SETTINGS, "confinement": spec})
        transport = provider()
        problems = ["p-one first problem", "p-two second problem"]
        with mock.patch.object(confine, "measure", lambda *a, **k: {"problems": list(problems)}), \
                self.assertRaises(R.RunRefused) as c:
            self.go(transport=transport)
        self.assertRegex(str(c.exception), r"p-one first problem\W+p-two second problem")
        self.assertEqual(transport.calls, [])
        rec = json.loads((self.tmp / "out" / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual((rec["failure"]["stage"], rec["confinement"]["problems"]), ("confinement", problems))


#: Open Code Review as a process of its own writes its whole environment next to its documents, then behaves as
#: test_v21_review_chain's finder (no findings: the candidate is committed)
DUMP_ENVIRONMENT = (
    "import json as _j, os as _o, pathlib as _p, sys as _s\n"
    "_p.Path(__file__).with_name('env-' + ('preview' if '--preview' in _s.argv else 'review') + '.json')"
    ".write_text(_j.dumps(dict(_o.environ)), encoding='utf-8')\n")
OPERATOR_SECRET = "operator-value-0123456789"
UNLISTED = "AISEF_TEST_UNLISTED_VARIABLE"      # an operator variable the settings do not name


@POSIX
class WholeRun(unittest.TestCase):
    """One run of the calc project that completed — its candidate reviewed by the Open Code Review finder, the write
    of its evidence manifest failing — made once for the class (a run costs seconds): what it did with that failure and
    handed to the finder, and, each test continuing its own copy of the run's directory (the manifest then written, as
    it would have been), what a continuation records of it."""

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        cls.tmp = pathlib.Path(t.name).resolve()
        baseline = app_run.make_repo(cls.tmp / "source")
        cls.project = bundle.load(app_run.project_bundle(baseline))
        cls.bin = cls.tmp / "client"
        cls.bin.mkdir()
        cls.client = cls.bin / "opencode"
        cls.client.write_text(f"#!{sys.executable}\nADD = {app_run.ADD!r}\nTEST = {app_run.TEST!r}\n" + app_run.FAKE_CLIENT)
        cls.client.chmod(0o755)
        (cls.bin / "mode").write_text("write")
        ocr = cls.bin / "ocr"
        ocr.write_text(f"#!{sys.executable}\n" + DUMP_ENVIRONMENT + chain.FAKE_OCR)
        ocr.chmod(0o755)
        (cls.bin / "scenarios.json").write_text(json.dumps([{}]), encoding="utf-8")
        review = {"policy": "fix-loop", "min_severity": "high", "finder": "ocr",
                  "ocr": {"exe": str(ocr), "sha256": hashlib.sha256(ocr.read_bytes()).hexdigest(), "timeout_min": 1,
                          "max_tokens": 4000}}
        cls.settings = settings.load({**SETTINGS, "client_env": ["AISEF_TEST_SECRET"], "review": review})
        for p in (mock.patch.object(ad, "scanner", lambda: ad.NoScanner()),
                  mock.patch.dict(os.environ, app_run.client_config(cls.tmp))):
            p.start()
            cls.addClassCleanup(p.stop)
        cls.operator_path = os.pathsep.join([str(cls.tmp / "operator-bin"), os.environ.get("PATH", "")])
        cls.first = cls.tmp / "first"
        cls.manifest_error = None
        cls.injected = OSError("disk full")
        operator = {"PATH": cls.operator_path, "AISEF_TEST_SECRET": OPERATOR_SECRET, UNLISTED: OPERATOR_SECRET}
        with mock.patch.dict(os.environ, operator), \
                mock.patch.object(R, "evidence_manifest", side_effect=cls.injected):   # the one write that fails
            try:
                R.execute(cls.project, cls.settings, cls.tmp / "source", cls.first, transport=provider(),
                          client_exe=str(cls.client), cals=app_run.calibrations())
            except OSError as e:
                cls.manifest_error = e
        cls.record = json.loads((cls.first / "RUN.json").read_text(encoding="utf-8"))
        cls.manifest_written = (cls.first / R.MANIFEST).exists()
        if not cls.manifest_written:    # the directory of a run whose manifest was written, for the tests that continue it
            (cls.first / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(cls.first), indent=1, sort_keys=True) + "\n",
                                                encoding="utf-8")

    def test_a_manifest_that_cannot_be_written_is_loud_for_a_completed_run(self):
        """A run that completed and cannot anchor its evidence does not return as if it had: the OSError of the
        manifest write propagates out of `execute`, the record (written first) stays, the manifest does not exist.
        Pins aisef2/app/run.py::execute [183, 233]"""
        self.assertIs(self.manifest_error, self.injected)
        self.assertEqual(self.record["delivery_verdict"], "PASS")
        self.assertFalse(self.manifest_written)

    def test_the_finder_runs_in_the_operators_environment_minus_the_clients_configuration(self):
        """Open Code Review is a process of its own: its environment is the operator's client environment (the PATH it
        finds git by, the variables the settings name — and no other variable of the operator's), without the
        client's configuration channel (OPENCODE_CONFIG_CONTENT), and its HOME is inside the run's own directory, not
        the operator's. Seen by the finder itself, in its preview and in its review.
        Pins aisef2/app/run.py::execute [169, 215, 282, 309]"""
        self.assertEqual(self.record["delivery_verdict"], "PASS", self.record)
        for name in ("env-preview.json", "env-review.json"):
            env = json.loads((self.bin / name).read_text(encoding="utf-8"))
            self.assertEqual(env.get("PATH"), self.operator_path, name)
            self.assertEqual(env.get("AISEF_TEST_SECRET"), OPERATOR_SECRET, name)
            self.assertNotIn("OPENCODE_CONFIG_CONTENT", env, name)
            self.assertNotIn(UNLISTED, env, name)
            self.assertTrue(pathlib.Path(env.get("HOME", "")).is_relative_to(self.first), (name, env.get("HOME")))

    def predecessor(self, name: str, *remove: str) -> pathlib.Path:
        """A copy of the finished run's directory, less the files named: what a run killed before its record, or a
        directory of a release that wrote no RUN.started.json, holds."""
        dst = self.tmp / name
        shutil.copytree(self.first, dst, symlinks=True)
        for r in remove:
            (dst / r).unlink()
        return dst

    def child(self, parent: pathlib.Path, name: str | None = None, **kw) -> tuple[Exception, dict, dict]:
        """Continue `parent` with a plan no calibration admits: the claim, the lineage's account and the clone come
        first; the refusal at admission comes before any provider request. (the refusal, RUN.json, RUN.started.json)"""
        name = name or f"{parent.name}-child"
        transport = provider()
        with self.assertRaises(R.RunRefused) as c:
            R.execute(self.project, self.settings, parent / "repo", self.tmp / name, transport=transport,
                      client_exe=str(self.client), cals=(), predecessor=parent, **kw)
        self.assertEqual(transport.calls, [])
        out = self.tmp / name
        self.assertTrue((out / "RUN.json").is_file(), f"refused before the run began: {c.exception}")
        return (c.exception, json.loads((out / "RUN.json").read_text(encoding="utf-8")),
                json.loads((out / R.STARTED).read_text(encoding="utf-8")))

    def test_a_predecessor_that_never_wrote_its_record_is_marked_a_finished_one_is_not(self):
        """`continues.recorded` is the explicit marker False exactly when the predecessor's directory held no RUN.json
        when the child started (what it spent is then re-derived from its streams), and is absent otherwise — in the
        child's RUN.started.json as in its RUN.json.
        Pins aisef2/app/run.py::execute [11, 35, 87, 136, 184]"""
        finished = self.predecessor("finished")
        killed = self.predecessor("killed", "RUN.json", R.MANIFEST)
        self.assertTrue((killed / R.STARTED).is_file() and not (killed / "RUN.json").exists())
        for parent, name in ((finished, "after-finished"), (killed, "after-killed")):
            _, rec, started = self.child(parent, name)
            marked = parent is killed
            for where, doc in (("RUN.json", rec["continues"]), (R.STARTED, started["continues"])):
                self.assertEqual(doc["path"], str(parent), where)
                if marked:
                    self.assertIs(doc.get("recorded"), False, where)
                else:
                    self.assertNotIn("recorded", doc, where)

    def test_a_predecessor_with_its_record_and_no_started_file_is_accepted(self):
        """--parent accepts a directory that holds either record and refuses one that holds neither: a directory with
        RUN.json and no RUN.started.json (a release before 2.1; a started file lost) is a predecessor, and is not
        marked as one that never wrote its record.
        Pins aisef2/app/run.py::execute [184]"""
        parent = self.predecessor("record-only", R.STARTED, R.MANIFEST)
        _, rec, started = self.child(parent)
        self.assertEqual(rec["failure"]["stage"], "admission")      # past the --parent check
        self.assertEqual(rec["continues"]["path"], str(parent))
        self.assertNotIn("recorded", rec["continues"])
        self.assertNotIn("recorded", started["continues"])

    def test_a_directory_with_neither_record_is_refused_naming_it_before_anything_is_made(self):
        """A --parent that holds neither RUN.json nor RUN.started.json is refused naming that directory and the cause
        (no run record there), before the run directory exists and before any provider request.
        Pins aisef2/app/run.py::execute [186]"""
        parent = self.tmp / "no-record"
        parent.mkdir()
        (parent / "notes.txt").write_text("not a run\n", encoding="utf-8")
        transport = provider()
        with self.assertRaises(R.RunRefused) as c:
            R.execute(self.project, self.settings, self.tmp / "source", self.tmp / "refused", transport=transport,
                      client_exe=str(self.client), cals=app_run.calibrations(), predecessor=parent)
        self.assertRegex(str(c.exception), re.escape(str(parent)) + r".*no run record")
        self.assertFalse((self.tmp / "refused").exists())
        self.assertEqual(transport.calls, [])

    def test_the_record_states_what_the_lineage_had_spent_when_the_claim_was_taken(self):
        """`continues.account` is the lineage's spend the run's ceilings were counted against: the four counters and
        the unaccounted list — here those of the predecessor's own record (a lineage of one run).
        Pins aisef2/app/run.py::execute [189]"""
        parent = self.predecessor("accounted")
        spent = json.loads((parent / "RUN.json").read_text(encoding="utf-8"))["budget"]["spent"]
        _, rec, _ = self.child(parent)
        account = rec["continues"]["account"]
        self.assertEqual(sorted({*SPEND, "unaccounted"} - set(account)), [], "what the account lacks")
        self.assertEqual({k: account[k] for k in SPEND}, {k: spent[k] for k in SPEND})
        self.assertTrue(all(spent[k] > 0 for k in SPEND), spent)       # a real account, not four zeros
        self.assertEqual(account["unaccounted"], [])

    def test_every_unaccounted_entry_of_the_lineage_is_named_in_the_refusal_and_told_apart(self):
        """A lineage with unknown spend starts no paid work unless the operator accepts it: the refusal carries the
        recovery instruction and every entry the operator is asked to accept, each recognisable as one entry.
        Pins aisef2/app/run.py::execute [333]"""
        parent = self.predecessor("unknown-spend")
        for log in sorted((parent / "sessions").glob("*.jsonl")):     # both sessions started; no step ever finished
            log.write_text(json.dumps({"type": "text", "part": {"text": "cut"}}) + "\n", encoding="utf-8")
        unknown = lineage.account_of(parent)["unaccounted"]
        self.assertEqual(len(unknown), 2, unknown)
        exc, rec, _ = self.child(parent)
        message = str(exc)
        self.assertIn("--accept-unaccounted", message)
        for entry in unknown:
            self.assertIn(entry, message)
        self.assertRegex(message, re.escape(unknown[0]) + r"\W+" + re.escape(unknown[1]))
        self.assertEqual(rec["failure"]["stage"], "claim")
        self.assertNotIn("accepted_unaccounted", rec["continues"])


if __name__ == "__main__":
    unittest.main()
