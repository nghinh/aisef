"""V2.1 (owner B-03, campaign 2 survivors, batch T22a): kill tests for `aisef2/app/verify.py::verify` and
`::_runspec_problems`. `aisef run --verify` re-derives what a run directory claims from its own evidence; each class
below is one behaviour of that verifier that no earlier kill file forged:

* a directory with no readable RUN.json is REFUTED by a document (never an exception, never `None`);
* a record whose settings do not load, and a journal whose capabilities cannot make a RunSpec, are REFUTED by a
  problem (the verifier never crashes on a forged record);
* the usage account and the no_progress report are re-derived from the evidence — each alone — except where the run
  itself named the fault that kept it from deriving the account, and a 2.0.0 record without one still verifies;
* the manifest problem names the paths that differ, sorted and at most five, and those only.

The executed run (one real run of the calc project with the fake client of test_app_run) is made once for the file
and copied for each forgery; the manifest and no-record cases need no run and use a directory built here.
Offline; nothing outside the temporary directories is written."""

from __future__ import annotations

import hashlib
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
from aisef2.app import bundle, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.journal import event as ev  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

POSIX = os.name == "posix"

# the fixtures, made once by setUpModule
_LIGHT_PROJECT = None      # a project, for the directories that hold no run
_RUN_PROJECT = None        # the project of the executed run
_RUN = None                # the executed run's directory (POSIX: the fake client is a script started by its shebang)


def setUpModule() -> None:
    global _LIGHT_PROJECT, _RUN_PROJECT, _RUN
    _LIGHT_PROJECT = bundle.load(e2e.project_bundle("a" * 40))
    if not POSIX:
        return
    t = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(t.cleanup)
    tmp = pathlib.Path(t.name).resolve()
    baseline = e2e.make_repo(tmp / "source")
    _RUN_PROJECT = bundle.load(e2e.project_bundle(baseline))
    client = tmp / "client" / "opencode"
    client.parent.mkdir()
    client.write_text(f"#!{sys.executable}\nADD = {e2e.ADD!r}\nTEST = {e2e.TEST!r}\n" + e2e.FAKE_CLIENT)
    client.chmod(0o755)
    (client.parent / "mode").write_text("write")
    with mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), \
            mock.patch.dict(os.environ, e2e.client_config(tmp)):
        rec = R.execute(_RUN_PROJECT, settings.load(e2e.SETTINGS), tmp / "source", tmp / "out",
                        client_exe=str(client), cals=e2e.calibrations(), transport=e2e.provider())
    assert rec["delivery_verdict"] == "PASS", rec
    _RUN = tmp / "out"


def read_json(p: pathlib.Path):
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: pathlib.Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def remake_manifest(out: pathlib.Path) -> None:
    """As if the run had written it so: EVIDENCE.json binds the directory as it is now, so the manifest cannot be what
    refutes the forgery."""
    write_json(out / R.MANIFEST, R.evidence_manifest(out))


def edit_record(out: pathlib.Path, edit) -> None:
    rec = read_json(out / "RUN.json")
    edit(rec)
    write_json(out / "RUN.json", rec)
    remake_manifest(out)


def rewrite_journal(out: pathlib.Path, edit) -> None:
    """`edit` each stored event (a dict), chain every line again, name the new digest in RUN.json, remake the manifest:
    a journal edited by hand that is still a valid chain of valid payloads."""
    rec = read_json(out / "RUN.json")
    path = out / rec["journal"]["path"]
    prev, lines = ev.GENESIS, []
    for line in (x for x in path.read_text(encoding="utf-8").split("\n") if x):
        stored = json.loads(line)
        edit(stored["event"])
        event = ev.Event(**stored["event"])
        prev = ev.link(prev, event)
        lines.append(ev.encode(event, prev))
    data = "".join(lines).encode("utf-8")
    path.write_bytes(data)
    rec["journal"]["sha256"] = hashlib.sha256(data).hexdigest()
    write_json(out / "RUN.json", rec)
    remake_manifest(out)


class _Dir(unittest.TestCase):
    """A scratch directory per test."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()


@unittest.skipUnless(POSIX, "the executed run needs the fake client, a script started by its shebang")
class _OnARun(_Dir):
    """A copy of the file's one executed run (PASS, one story), to forge."""

    def setUp(self) -> None:
        super().setUp()
        self.out = self.tmp / "out"
        shutil.copytree(_RUN, self.out, symlinks=True, ignore=shutil.ignore_patterns("test-python"))
        self.project = _RUN_PROJECT
        self.assertEqual(verify(self.project, self.out)["verdict"], "VERIFIED")     # the control: forged below


# ---------------------------------------------------------------------------------------- no record to verify


class NoReadableRunRecord(_Dir):
    """A run directory whose RUN.json is absent, not JSON, not UTF-8 or not a file has nothing to verify against.
    Requirement: verify returns exactly {'verdict': 'REFUTED', 'problems': [one problem]} and never raises — `aisef run
    --verify` reads v['verdict'] of it (aisef2/app/cli.py) and the release checks read v['verdict'] and v['problems']
    (validation/qualification/release_acceptance.py, release_rehearsal.py) — and the one problem names the record's
    path and the class of what could not be read, so the operator sees which file and why.
    Pins aisef2/app/verify.py::verify [44, 45, 46, 75, 76, 103, 104, 105, 167]."""

    def refusal(self, out: pathlib.Path) -> dict:
        v = verify(_LIGHT_PROJECT, out)
        self.assertIsInstance(v, dict)
        self.assertEqual(sorted(v), ["problems", "verdict"])
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertIsInstance(v["problems"], list)
        self.assertEqual(len(v["problems"]), 1, v)
        self.assertIn(str(out / "RUN.json"), v["problems"][0])
        return v

    def test_an_absent_record_is_a_refutation_naming_the_file(self):
        out = self.tmp / "out"
        out.mkdir()
        self.assertIn("FileNotFoundError", self.refusal(out)["problems"][0])

    def test_a_record_that_is_not_json_is_a_refutation_naming_the_file(self):
        out = self.tmp / "out"
        out.mkdir()
        (out / "RUN.json").write_text("{not json", encoding="utf-8")
        self.assertIn("JSONDecodeError", self.refusal(out)["problems"][0])

    def test_a_record_that_is_not_utf_8_is_a_refutation_naming_the_file(self):
        out = self.tmp / "out"
        out.mkdir()
        (out / "RUN.json").write_bytes(b"\xff\xfe{}")
        self.assertIn("UnicodeDecodeError", self.refusal(out)["problems"][0])

    def test_a_record_that_cannot_be_read_as_a_file_is_a_refutation_naming_the_file(self):
        out = self.tmp / "out"
        (out / "RUN.json").mkdir(parents=True)
        try:
            (out / "RUN.json").read_text(encoding="utf-8")
        except OSError as e:     # IsADirectoryError on POSIX, PermissionError on Windows
            named = type(e).__name__
        self.assertIn(named, self.refusal(out)["problems"][0])


# ---------------------------------------------------------------------------------------- the record's settings


class RecordSettingsThatDoNotLoad(_OnARun):
    """The settings RUN.json names are bound to the journal by loading them and re-deriving the RunSpec hash (V2-02).
    Settings that do not load cannot be bound: verify returns REFUTED with one problem that carries the loader's own
    reason and says it is the record's settings that do not load — the loader's reason names a setting key (here
    `route`), never the document — and re-derives no spend from them. A forged record must be refuted, not crash the
    verifier.
    Pins aisef2/app/verify.py::_runspec_problems [11, 19, 20, 35]."""

    def test_settings_that_do_not_load_are_a_problem_of_the_record_never_a_crash(self):
        bad = {**e2e.SETTINGS, "route": "nope"}
        with self.assertRaises(settings.SettingsError) as loader:
            settings.load(bad)
        reason = str(loader.exception)
        self.assertNotIn("settings", reason)     # the premise: the reason alone does not say what is at fault
        edit_record(self.out, lambda rec: rec.update(settings=bad))

        v = verify(self.project, self.out)

        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        self.assertIn(reason, v["problems"][0])
        self.assertIn("settings", v["problems"][0])
        self.assertFalse(any("spend" in p for p in v["problems"]), v["problems"])


# ---------------------------------------------------------------------------------------- the journal's capabilities


class CapabilitiesThatDoNotMakeARunSpec(_OnARun):
    """The RunSpec is re-derived from the journal's own `capability/resolved` events. A journal edited by hand so that a
    VERIFIED capability binds no digest is still a valid chain of valid payloads (formats 2 and 3 check the payload's
    kinds, not the grade's binding rule), so it reconstructs; the capability then cannot be built. Requirement: verify
    returns REFUTED with one problem that says the RunSpec does not re-derive and carries the class of the refusal
    (CapabilityError) and the capability it names — never the exception, never `None`.
    Pins aisef2/app/verify.py::_runspec_problems [14, 15, 21, 22, 41]."""

    def test_a_capability_that_binds_no_digest_is_a_problem_of_the_journal_never_a_crash(self):
        named: list[str] = []

        def drop_the_digest(event: dict) -> None:
            data = event["data"]
            if event["type"] == "capability/resolved" and data["grade"] == "VERIFIED" and not named:
                named.append(data["name"])
                del data["binding"]["digest"]
        rewrite_journal(self.out, drop_the_digest)
        self.assertEqual(len(named), 1)

        v = verify(self.project, self.out)

        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        p = v["problems"][0]
        self.assertIn("RunSpec", p)
        self.assertIn("CapabilityError", p)
        self.assertIn(named[0], p)


# ---------------------------------------------------------------------------------------- the usage account


class AccountOfUsageIsTheEvidences(_OnARun):
    """The record's usage account and its no_progress report are re-derived from the evidence (session streams,
    ledger, journal), each alone, with EVIDENCE.json made again so the manifest cannot be what refutes them: lowered
    tokens are refuted, an invented no_progress is refuted, each naming 'usage'. The one exception is the fault the
    run itself named: a usage of {'error': ...} (aisef2/app/run.py: 'a fault here never costs the record') is not an
    account to compare and verifies; a record without either field (a 2.0.0 record) verifies and verify does not raise.
    Pins aisef2/app/verify.py::verify [10, 34, 65, 66, 97, 126, 128]."""

    def test_tokens_lowered_in_the_record_are_refuted_by_the_account(self):
        def lower(rec: dict) -> None:
            rec["usage"]["tokens"]["output"] -= 1
        edit_record(self.out, lower)

        v = verify(self.project, self.out)

        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        self.assertIn("usage", v["problems"][0])

    def test_a_no_progress_report_that_the_journal_does_not_hold_is_refuted_by_the_account(self):
        self.assertEqual(read_json(self.out / "RUN.json")["no_progress"], [])     # the journal reports no repeat

        def invent(rec: dict) -> None:
            rec["no_progress"] = [{"story": "S1", "attempts_repeating_the_one_before": [2], "failures": ["X: y"]}]
        edit_record(self.out, invent)

        v = verify(self.project, self.out)

        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        self.assertIn("usage", v["problems"][0])

    def test_a_usage_the_run_named_as_a_fault_is_not_an_account_to_compare(self):
        def fault(rec: dict) -> None:     # what run.py writes when the derivation raised: no no_progress either
            rec["usage"] = {"error": "RuntimeError: the account could not be derived"}
            del rec["no_progress"]
        edit_record(self.out, fault)

        v = verify(self.project, self.out)

        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)

    def test_a_record_without_a_usage_account_verifies(self):
        def as_of_2_0_0(rec: dict) -> None:
            del rec["usage"], rec["no_progress"]
        edit_record(self.out, as_of_2_0_0)

        v = verify(self.project, self.out)

        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)


# ---------------------------------------------------------------------------------------- the manifest problem


class Fixed(str):
    """A str whose hash the case fixes: in a set of distinct small hashes each one sits in the slot its hash names, so
    the set iterates in hash order (CPython), whatever PYTHONHASHSEED is."""

    def __new__(cls, value: str, h: int) -> "Fixed":
        s = super().__new__(cls, value)
        s.h = h
        return s

    def __hash__(self) -> int:
        return self.h


class ManifestProblemNamesTheFilesThatDiffer(_Dir):
    """EVIDENCE.json binds the record, the journal, each session stream and the preflight's files. When the directory
    is not what it binds, the one problem names the paths that differ — in the stored manifest and in the directory,
    whichever side lacks them — sorted, at most five, and no path that agrees: it is the only place that says which
    file was changed or went missing.
    Pins aisef2/app/verify.py::verify [80, 156, 169, 171]."""

    def setUp(self) -> None:
        super().setUp()
        self.out = self.tmp / "out"
        for name, text in (("RUN.json", json.dumps({"format": R.FORMAT})), ("RUN.started.json", "{}"),
                           ("run/journals/aisef-run.jsonl", ""), ("sessions/S1.developer.1.jsonl", "{}\n"),
                           ("sessions/S1.reviewer.1.jsonl", "{}\n{}\n"), ("preflight/LEDGER.jsonl", ""),
                           ("preflight/PREFLIGHT.json", "{}")):
            (self.out / name).parent.mkdir(parents=True, exist_ok=True)
            (self.out / name).write_text(text, encoding="utf-8")
        self.fresh = R.evidence_manifest(self.out)
        self.paths = sorted(self.fresh["files"])
        self.assertEqual(len(self.paths), 7)
        # the paths are told apart by plain containment in a problem
        self.assertFalse([a for a in self.paths for b in self.paths if a != b and a in b])
        write_json(self.out / R.MANIFEST, self.fresh)
        self.assertFalse(any("manifest" in p for p in verify(_LIGHT_PROJECT, self.out)["problems"]))

    def manifest_problem(self) -> str:
        found = [p for p in verify(_LIGHT_PROJECT, self.out)["problems"] if "manifest" in p]
        self.assertEqual(len(found), 1, found)
        return found[0]

    def test_a_changed_file_is_named_and_the_files_that_agree_are_not(self):
        changed = self.paths[-1]
        stored = read_json(self.out / R.MANIFEST)
        stored["files"][changed] = "0" * 64
        write_json(self.out / R.MANIFEST, stored)

        problem = self.manifest_problem()

        self.assertIn(changed, problem)
        for agreeing in self.paths[:-1]:
            self.assertNotIn(agreeing, problem)

    def test_a_file_the_manifest_binds_and_the_directory_lacks_is_named(self):
        bare = self.tmp / "bare"       # the directory as it is without that stream, the manifest as it was
        shutil.copytree(self.out, bare, ignore=shutil.ignore_patterns("S1.reviewer.1.jsonl"))
        self.assertFalse((bare / "sessions" / "S1.reviewer.1.jsonl").exists())
        self.out = bare

        problem = self.manifest_problem()

        self.assertIn("sessions/S1.reviewer.1.jsonl", problem)
        for agreeing in (p for p in self.paths if p != "sessions/S1.reviewer.1.jsonl"):
            self.assertNotIn(agreeing, problem)

    def test_the_paths_are_the_first_five_in_sorted_order_whatever_the_hash_seed(self):
        names = [f"sessions/S{i:02d}.developer.1.jsonl" for i in range(8)]
        # hashed so that the set the problem is built from iterates in reverse name order: the order of a set is
        # nobody's contract, the problem's is sorted
        manifest = {"format": R.MANIFEST_FORMAT,
                    "files": {Fixed(n, len(names) - i): "0" * 64 for i, n in enumerate(names)}}
        self.assertEqual(list(set() | set(manifest["files"])), sorted(names, reverse=True))     # the premise
        write_json(self.out / R.MANIFEST, {"format": R.MANIFEST_FORMAT, "files": {}})

        with mock.patch.object(R, "evidence_manifest", lambda out: manifest):
            problem = self.manifest_problem()

        listed = [n for n in names if n in problem]
        self.assertEqual(listed, names[:5], problem)
        self.assertEqual(sorted(problem.index(n) for n in listed), [problem.index(n) for n in listed], problem)


if __name__ == "__main__":
    unittest.main()
