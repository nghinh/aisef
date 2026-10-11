"""V2.1 (owner B-03, mutation-survivor batch T23a): what `aisef run` (aisef2/app/cli.py) promises its caller — the
exit status, the document on stdout and the one tagged line on stderr — measured through the public function
`cli.run(argv)` with the product's own collaborators doing the real work wherever that is cheap.

The bundle and settings readers, the run itself (`R.execute`, with its real signature: a wrong keyword raises) and
`verify` are stand-ins; the evidence anchor is the real `R.anchor_in` of a manifest the stand-in run writes, and the
one end-to-end class drives the real `verify` over a minimal finished directory. Nothing here reads a network, starts
a client or a session, or writes outside its own temporary directory."""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import io
import json
import os
import pathlib
import re
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, cli, confine, lineage, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify as real_verify  # noqa: E402

#: the signatures the command must call by — taken before any test patches the names
EXECUTE = inspect.signature(R.execute)
VERIFY = inspect.signature(real_verify)
MEASURE = inspect.signature(confine.measure)
LINEAGE_KEYWORDS = ("predecessor", "accept_unaccounted", "supersede_claim")

TAG = "aisef run"
ANCHOR = "ab12" * 16                    # an evidence anchor as a run prints it: 64 lowercase hex digits
OTHER_ANCHOR = "cd34" * 16
KEYS = ("project", "delivery_verdict", "delivery_blocked_by", "story_outcomes", "final_main", "journal",
        "plan_quality_verdict")
BY_VERDICT = (("PASS", 0), ("FAIL", 1), ("NOT_REACHED", 1))


class Cmd(unittest.TestCase):
    """`aisef run` with its readers and its run replaced; `invoke` returns what a caller sees."""

    maxDiff = None

    def start(self, patcher):
        m = patcher.start()
        self.addCleanup(patcher.stop)
        return m

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.out = self.tmp / "out"
        self.project = types.SimpleNamespace(name="p", plan=types.SimpleNamespace(plan_hash="h" * 64))
        self.manifest = {"format": R.MANIFEST_FORMAT, "files": {"RUN.json": "f" * 64}}
        self.anchor = R.anchor_of(self.manifest)        # what the run prints and an operator keeps
        self.record = {k: f"{k}-value" for k in KEYS} | {"delivery_verdict": "PASS", "other": 1}
        self.bundle_read = self.start(mock.patch.object(bundle, "read", return_value=self.project))
        self.settings_read = self.start(mock.patch.object(settings, "read",
                                                          return_value=types.SimpleNamespace(route="r/m")))
        self.execute = self.start(mock.patch.object(R, "execute", autospec=True, side_effect=self.finish))
        self.verify = self.start(mock.patch.object(cli, "verify", autospec=True, return_value={"verdict": "VERIFIED"}))
        # --check: no git, no calibration set, no client lookup — the admission is the stand-in's
        self.check_git = self.start(mock.patch.object(R, "check_git"))
        self.check_repository = self.start(mock.patch.object(R, "check_repository"))
        self.admit = self.start(mock.patch.object(R, "admit", return_value={"admitted": True, "why": []}))
        self.start(mock.patch.object(R, "calibrations", return_value=()))
        self.start(mock.patch.object(R, "client_on_path", return_value="/opt/client/opencode"))
        # argparse colours its messages on a tty (3.14); the line is read as plain text
        self.start(mock.patch.dict(os.environ, {"NO_COLOR": "1", "PYTHON_COLORS": "0"}))

    def finish(self, project, s, source, out, **_):
        """The run's effect the command reads back: the run directory with the manifest whose digest is the anchor."""
        pathlib.Path(out).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(out) / R.MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")
        return self.record

    def run_argv(self, *extra: str) -> list[str]:
        return ["--project", "bundle.json", "--settings", "settings.json", "--repo", "repo", "--out", str(self.out), *extra]

    def check_argv(self, *extra: str) -> list[str]:
        return ["--check", "--project", "bundle.json", "--settings", "settings.json", "--repo", "repo", *extra]

    def verify_argv(self, *extra: str) -> list[str]:
        return ["--verify", "--project", "bundle.json", "--out", str(self.out), *extra]

    def invoke(self, *argv: str) -> types.SimpleNamespace:
        """status: what cli.run returned; exit: the SystemExit code argparse raised (one of the two is None)."""
        out, err = io.StringIO(), io.StringIO()
        status = exit_code = None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                status = cli.run(list(argv))
            except SystemExit as e:
                exit_code = e.code
        return types.SimpleNamespace(status=status, exit=exit_code, out=out.getvalue(), err=err.getvalue(),
                                     lines=[ln for ln in err.getvalue().splitlines() if ln.strip()],
                                     doc=json.loads(out.getvalue()) if out.getvalue() else None)

    def refused(self, argv: list[str], *elements: str) -> str:
        """`argv` is refused through argparse: SystemExit(2), nothing printed on stdout, nothing read or run, and the
        last stderr line (the usage above it lists every option) is the command's tagged error line, whose message —
        returned — carries each of `elements`."""
        r = self.invoke(*argv)
        self.assertEqual((r.status, r.exit, r.out), (None, 2, ""), argv)
        prefix = f"{TAG}: error: "
        self.assertTrue(r.lines and r.lines[-1].startswith(prefix), r.lines[-1:] or r.err)
        message = r.lines[-1][len(prefix):]
        for element in elements:
            self.assertIn(element, message)
        for what in (self.bundle_read, self.settings_read, self.execute, self.verify, self.check_git, self.admit):
            what.assert_not_called()
        return message

    def lineage_given(self, *, defaults: bool = False) -> dict:
        """The lineage keywords of the last R.execute call by the names R.execute declares: those the command passed
        or, with `defaults`, what the run sees (a keyword left out is the default R.execute declares for it, a path
        given as text the same run)."""
        c = self.execute.call_args
        bound = EXECUTE.bind(*c.args, **c.kwargs)
        if defaults:
            bound.apply_defaults()
        given = {k: bound.arguments[k] for k in LINEAGE_KEYWORDS if k in bound.arguments}
        if given.get("predecessor") is not None:
            given["predecessor"] = pathlib.Path(given["predecessor"])
        return given

    @staticmethod
    def tagged(r: types.SimpleNamespace) -> list[str]:
        """The stderr lines the command itself wrote (the usage and any library warning are not its lines)."""
        return [ln for ln in r.lines if ln.startswith(f"{TAG}:")]

    def document(self, **extra) -> dict:
        return {k: self.record.get(k) for k in KEYS} | {"record": str(self.out / "RUN.json")} | extra


class Refusals(Cmd):
    """Every refusal `run()` raises through argparse is SystemExit(2) before anything is read or run, with one
    `aisef run: error: <message>` line whose message carries the element the operator must act on. Asserted on the
    LAST stderr line: the usage above it lists every option, so a search of the whole stderr proves nothing.

    Pins aisef2/app/cli.py::_parser [12, 18] and aisef2/app/cli.py::run [20, 23, 24, 46, 47, 48, 49]."""

    def test_the_refusal_line_is_tagged_with_the_command_that_refused_like_its_other_stderr_line(self):
        """_parser [12]: `prog` is the tag of every argparse refusal (and of the usage). The command's own
        `aisef run: refused: ...` line carries the same one, so an operator reading stderr sees one command."""
        self.refused(self.check_argv("--expect-anchor", ANCHOR), "--expect-anchor")        # asserts the tagged prefix
        self.bundle_read.side_effect = bundle.BundleError("bundle.json: cannot be read")
        r = self.invoke(*self.verify_argv())
        self.assertEqual((r.status, r.exit), (2, None))
        self.assertTrue(r.lines[-1].startswith(f"{TAG}:"), r.lines)

    def test_a_command_line_without_the_project_bundle_is_refused_in_every_mode_before_any_read(self):
        """_parser [18]: `--project` is required. Optional, `bundle.read(None)` would be reached and raise a
        TypeError — a traceback with exit status 1, the code of a FAIL, for an input that is a refusal (2)."""
        for mode in ((), ("--check",), ("--verify",)):
            argv = [*mode, "--settings", "settings.json", "--repo", "repo", "--out", str(self.out)]
            with self.subTest(mode=mode or "run"):
                self.refused(argv, "--project")

    def test_an_expect_anchor_given_to_a_run_or_a_check_is_refused_naming_it_and_verify(self):
        """run [20, 46]: `--expect-anchor` belongs to `--verify`; given to a run or a check it is refused (a valid
        anchor included), not ignored, and the refusal names the option and the mode it belongs to."""
        for name, argv in (("run", self.run_argv()), ("check", self.check_argv())):
            with self.subTest(name):
                self.refused([*argv, "--expect-anchor", ANCHOR], "--expect-anchor", "--verify")

    def test_an_anchor_out_that_cannot_be_a_new_file_for_a_run_is_refused_naming_it(self):
        """run [47]: `--anchor-out` that exists, dangles, or is given to `--verify`/`--check` is refused, and the one
        message that serves the four names the option."""
        existing = self.tmp / "existing.anchor"
        existing.write_text("kept\n", encoding="utf-8")
        cases = {"an existing file": self.run_argv("--anchor-out", str(existing)),
                 "--verify": self.verify_argv("--anchor-out", str(self.tmp / "new.anchor")),
                 "--check": self.check_argv("--anchor-out", str(self.tmp / "new.anchor"))}
        dangling = self.tmp / "dangling.anchor"
        try:
            os.symlink(self.tmp / "nowhere", dangling)
        except (OSError, NotImplementedError):      # a platform that does not let this user make a link
            pass
        else:
            cases["a dangling link"] = self.run_argv("--anchor-out", str(dangling))
        for name, argv in cases.items():
            with self.subTest(name):
                self.refused(argv, "--anchor-out")
        self.assertEqual(existing.read_text(encoding="utf-8"), "kept\n")

    def test_a_lineage_flag_without_parent_is_refused_naming_parent_and_with_parent_is_accepted(self):
        """run [23, 24, 48]: `--accept-unaccounted` or `--supersede-claim S` has nothing to act on without
        `--parent` — each alone and both together — and a fresh run must not start in its place; with `--parent`
        the same flags reach the run."""
        flags = (["--accept-unaccounted"], ["--supersede-claim", OTHER_ANCHOR],
                 ["--accept-unaccounted", "--supersede-claim", OTHER_ANCHOR])
        for given in flags:
            with self.subTest(without_parent=given):
                self.refused(self.run_argv(*given), "--parent")
        for given in flags:
            with self.subTest(with_parent=given):
                r = self.invoke(*self.run_argv("--parent", str(self.tmp / "parent"), *given))
                self.assertEqual((r.status, r.exit), (0, None))
        self.assertEqual(self.execute.call_count, len(flags))

    def test_a_malformed_expect_anchor_is_refused_naming_it_and_the_limit(self):
        """run [49]: what is not the 64-lowercase-hex digest a run printed is refused before `verify` is called,
        and the line names the option and the 64 digits it takes."""
        malformed = {"63 digits": ANCHOR[:-1], "65 digits": ANCHOR + "a", "a non-hex digit": "g" * 64,
                     "uppercase": ANCHOR.upper(), "empty": "", "a word": "not-an-anchor"}
        for name, value in malformed.items():
            with self.subTest(name):
                self.refused(self.verify_argv("--expect-anchor", value), "--expect-anchor", "64")

    def test_the_anchor_out_help_points_at_a_document_that_exists(self):
        """_parser [26]: `--anchor-out` says to keep the file where the developer cannot write and cites the document
        that explains why; the identifying element is that pointer, so a removed or renamed document is caught as
        well as an emptied help. The words around it are not pinned."""
        action = next(a for a in cli._parser()._actions if "--anchor-out" in a.option_strings)
        cited = re.findall(r"docs/[\w./-]+\.md", action.help or "")
        self.assertTrue(cited, f"the help of --anchor-out cites no document: {action.help!r}")
        for path in cited:
            self.assertTrue((ROOT / path).is_file(), path)


class VerifyExpectAnchor(Cmd):
    """`aisef run --verify --project B --out D --expect-anchor A` hands A to `verify()` unchanged — the keyword the
    real signature declares — and exits 0 for VERIFIED, 1 for REFUTED; without it `verify()` is given no anchor.

    Pins aisef2/app/cli.py::run [20, 65, 99, 113]."""

    def test_the_anchor_the_run_printed_reaches_verify_by_its_keyword_and_the_verdict_sets_the_exit(self):
        for verdict, code in (("VERIFIED", 0), ("REFUTED", 1)):
            with self.subTest(verdict):
                self.verify.reset_mock()
                self.verify.return_value = {"verdict": verdict, "problems": []}
                r = self.invoke(*self.verify_argv("--expect-anchor", ANCHOR))
                self.assertEqual((r.status, r.exit, r.doc["verdict"]), (code, None, verdict))
                c = self.verify.call_args
                bound = VERIFY.bind(*c.args, **c.kwargs).arguments        # a keyword verify does not declare raises
                self.assertEqual((bound["project"], bound["out"], bound["expect_anchor"]),
                                 (self.project, self.out, ANCHOR))

    def test_without_an_expected_anchor_verify_is_given_none(self):
        r = self.invoke(*self.verify_argv())
        self.assertEqual((r.status, r.exit), (0, None))
        c = self.verify.call_args
        self.assertIsNone(VERIFY.bind(*c.args, **c.kwargs).arguments.get("expect_anchor"))

    def test_only_the_64_lowercase_hex_digest_is_accepted(self):
        accepted = ("0" * 64, "f" * 64, ANCHOR)
        for value in accepted:
            with self.subTest(accepted=value):
                self.assertEqual(self.invoke(*self.verify_argv("--expect-anchor", value)).status, 0)
        self.assertEqual(self.verify.call_count, len(accepted))
        for value in ("", ANCHOR[:-1], ANCHOR + "0", "g" * 64, ANCHOR.upper(), f" {ANCHOR}", ANCHOR + "\n"):
            with self.subTest(refused=value):
                self.verify.reset_mock()
                r = self.invoke(*self.verify_argv("--expect-anchor", value))
                self.assertEqual((r.status, r.exit), (None, 2))
                self.verify.assert_not_called()


class VerifyAgainstTheAnchorEndToEnd(unittest.TestCase):
    """The real `verify` behind the command, over a minimal finished directory (a record, its journal and the
    manifest that binds them): the anchor the run printed gives VERIFIED / exit 0, a consistent rewrite of the whole
    directory passes without an anchor (consistency, not authenticity) and is REFUTED / exit 1 with the anchor the
    run printed — with a problem that names the anchor expected — and so is any other valid anchor.

    Pins aisef2/app/cli.py::run [99, 113] (the real-signature form of the wiring is VerifyExpectAnchor)."""

    DIGEST = "d" * 64

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.out = pathlib.Path(t.name).resolve() / "out"
        (self.out / "run" / "journals").mkdir(parents=True)
        (self.out / "run" / "journals" / "j.jsonl").write_bytes(b"")
        self.seal(extra={})
        self.printed = R.anchor_in(self.out)
        project = types.SimpleNamespace(name="p", digest=self.DIGEST, plan=types.SimpleNamespace(obligations=[]), specs={})
        patch = mock.patch.object(bundle, "read", return_value=project)
        patch.start()
        self.addCleanup(patch.stop)
        env = mock.patch.dict(os.environ, {"NO_COLOR": "1", "PYTHON_COLORS": "0"})
        env.start()
        self.addCleanup(env.stop)

    def seal(self, extra: dict) -> None:
        """Write the run record and the manifest of the directory as it is: what a finished run leaves."""
        rec = {"format": R.FORMAT, "bundle_digest": self.DIGEST, "delivery_verdict": "NOT_REACHED",
               "journal": {"path": "run/journals/j.jsonl", "sha256": hashlib.sha256(b"").hexdigest(), "lines": 0}, **extra}
        (self.out / "RUN.json").write_text(json.dumps(rec), encoding="utf-8")
        (self.out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(self.out)), encoding="utf-8")

    def verify(self, *extra: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            status = cli.run(["--verify", "--project", "bundle.json", "--out", str(self.out), *extra])
        return status, json.loads(out.getvalue())

    def test_the_printed_anchor_verifies_the_directory(self):
        status, doc = self.verify("--expect-anchor", self.printed)
        self.assertEqual((status, doc["verdict"], doc["problems"]), (0, "VERIFIED", []))

    def test_a_consistently_rewritten_directory_is_refuted_by_the_anchor_the_run_printed(self):
        self.seal(extra={"rewritten": "after the run"})      # record and manifest rewritten together
        status, doc = self.verify()
        self.assertEqual((status, doc["verdict"]), (0, "VERIFIED"))
        status, doc = self.verify("--expect-anchor", self.printed)
        self.assertEqual((status, doc["verdict"]), (1, "REFUTED"))
        self.assertTrue(any(self.printed[:12] in p for p in doc["problems"]), doc["problems"])

    def test_another_valid_anchor_is_refuted_naming_the_anchor(self):
        status, doc = self.verify("--expect-anchor", OTHER_ANCHOR)
        self.assertEqual((status, doc["verdict"]), (1, "REFUTED"))
        self.assertTrue(any(OTHER_ANCHOR[:12] in p for p in doc["problems"]), doc["problems"])


class AnchorCopy(Cmd):
    """A finished run prints its evidence anchor and, with `--anchor-out NEW`, also keeps it in a new read-only file
    outside the run directory; the exit status stays the verdict's (0 PASS, 1 otherwise) and only a copy that was
    asked for and not made turns it into 2 (docs/v2.1/ANCHOR-THREAT-MODEL.md 'Tệp anchor').

    Pins aisef2/app/cli.py::run [15, 36, 38, 76, 96, 97, 111] and, for the copy that fails, [17, 58, 59, 106, 107, 109]."""

    def copy_failure_line(self, r: types.SimpleNamespace, path) -> str:
        """The stderr line about the copy that was asked for, found by the path it names: the command's own, saying the
        anchor was not written, with the path ended where it ends (not run into the word after it; its first mention,
        the exception's own text names it again)."""
        line = next((ln for ln in r.lines if str(path) in ln), "")
        self.assertTrue(line, r.err)
        self.assertTrue(line.startswith(f"{TAG}:"), line)
        self.assertRegex(line, re.compile(r"\bnot\b.*\bwritten\b", re.I))
        self.assertNotRegex(line.partition(str(path))[2], r"^[\w./\\-]", line)
        return line

    def test_without_anchor_out_the_run_prints_its_anchor_and_returns_its_verdict(self):
        """[15, 36]: with an anchor and no `--anchor-out` no copy is attempted (`write_anchor(None, ...)` would raise
        after the run and before the document); [96, 111]: the printed document carries the anchor as
        `evidence_anchor` and no `anchor_written_to`."""
        for verdict, code in BY_VERDICT:
            with self.subTest(verdict):
                self.record["delivery_verdict"] = verdict
                r = self.invoke(*self.run_argv())
                self.assertEqual((r.status, r.exit, self.tagged(r)), (code, None, []))
                self.assertEqual(r.doc, self.document(evidence_anchor=self.anchor))

    def test_with_anchor_out_the_anchor_is_in_a_new_read_only_file_and_the_document_says_where(self):
        """[36, 38]: the copy is made and the exit status is the verdict's, never 2; [76, 97]: the document names
        the file under `anchor_written_to`; the file holds exactly the anchor and a newline and is not writable."""
        for n, (verdict, code) in enumerate(BY_VERDICT):
            new = self.tmp / f"keep-{n}.anchor"
            with self.subTest(verdict):
                self.record["delivery_verdict"] = verdict
                r = self.invoke(*self.run_argv("--anchor-out", str(new)))
                self.assertEqual((r.status, r.exit, self.tagged(r)), (code, None, []))
                self.assertEqual(r.doc, self.document(evidence_anchor=self.anchor, anchor_written_to=str(new)))
                self.assertEqual(new.read_bytes(), (self.anchor + "\n").encode("ascii"))
                self.assertEqual(lineage.read_anchor(new), self.anchor)
                mode = stat.S_IMODE(new.stat().st_mode)
                self.assertEqual(mode & 0o222, 0, oct(mode))
                self.assertTrue(mode & 0o400, oct(mode))

    def test_a_copy_that_cannot_be_written_exits_2_whatever_the_verdict_and_the_printed_anchor_stays(self):
        """[17, 38]: the failed copy outranks the verdict (a PASS and a FAIL alike exit 2 — never None, never 0);
        [58]: an OSError is the copy failing, not a crash that loses the printed anchor (and no `anchor_written_to`
        is claimed); [106, 107, 109]: the stderr line says the anchor was not written, names the requested path (set
        off from what follows it) and the exception, and points at the anchor that was printed."""
        missing = self.tmp / "absent" / "run.anchor"
        for verdict in ("PASS", "FAIL"):
            with self.subTest(verdict):
                self.record["delivery_verdict"] = verdict
                r = self.invoke(*self.run_argv("--anchor-out", str(missing)))
                self.assertEqual((r.status, r.exit), (2, None))
                self.assertEqual(r.doc, self.document(evidence_anchor=self.anchor))
                self.assertFalse(missing.parent.exists())
                line = self.copy_failure_line(r, missing)
                self.assertIn("FileNotFoundError", line)
                self.assertIn("printed", line)

    def test_a_writer_that_refuses_the_anchor_is_also_only_the_copy_failing(self):
        """[59]: `write_anchor` documents a second refusal, a ValueError (an anchor that is not one; a path os.open
        will not take). It is handled as the copy failing — exit 2, the document with the anchor, the line on
        stderr — not raised out of `run()`."""
        refusing = mock.patch.object(lineage, "write_anchor", side_effect=ValueError("not an evidence anchor: 'x'"))
        cases = [("the writer refuses", str(self.tmp / "new.anchor"), refusing)]
        if os.name == "posix":      # os.open: ValueError for it, and the parse-time lexists is False for it
            cases.append(("an embedded NUL", str(self.tmp / "a\0b"), contextlib.nullcontext()))
        for name, path, patch in cases:
            with self.subTest(name), patch:
                r = self.invoke(*self.run_argv("--anchor-out", path))
                self.assertEqual((r.status, r.exit), (2, None))
                self.assertEqual(r.doc, self.document(evidence_anchor=self.anchor))
                self.copy_failure_line(r, path)


class ParentWiring(Cmd):
    """`--parent P [--accept-unaccounted] [--supersede-claim S]` reaches the run as exactly `predecessor=Path(P)`,
    `accept_unaccounted=True|False` and `supersede_claim=S|None`, under the names `R.execute` declares; a run without
    `--parent` starts a fresh run for it: no predecessor, no flag, no claim, no inherited spend.

    Pins aisef2/app/cli.py::run [91, 92, 93, 103, 104, 105]."""

    def test_the_lineage_flags_reach_the_run_under_the_names_execute_declares(self):
        parent = self.tmp / "parent"
        cases = (([], False, None),
                 (["--accept-unaccounted"], True, None),
                 (["--supersede-claim", OTHER_ANCHOR], False, OTHER_ANCHOR),
                 (["--accept-unaccounted", "--supersede-claim", OTHER_ANCHOR], True, OTHER_ANCHOR))
        for flags, accept, supersede in cases:
            with self.subTest(flags=flags):
                self.execute.reset_mock()
                r = self.invoke(*self.run_argv("--parent", str(parent), *flags))
                self.assertEqual((r.status, r.exit), (0, None))
                self.assertEqual(self.lineage_given(defaults=True),
                                 {"predecessor": parent, "accept_unaccounted": accept, "supersede_claim": supersede})

    def test_a_run_without_parent_is_a_fresh_run(self):
        r = self.invoke(*self.run_argv())
        self.assertEqual((r.status, r.exit), (0, None))
        self.assertEqual(self.execute.call_count, 1)
        self.assertEqual(self.lineage_given(defaults=True),
                         {"predecessor": None, "accept_unaccounted": False, "supersede_claim": None})


class CheckMeasuresInANewDirectory(Cmd):
    """`aisef run --check` measures the confinement in a directory of its own — a NEW path inside an existing one,
    which is what `confine.measure` documents for `where` and makes (`mkdir`, no `exist_ok`); handed the temporary
    directory itself, which already exists, the measurement refuses with a traceback instead of reporting readiness.

    Pins aisef2/app/cli.py::run [115]."""

    def test_check_hands_the_measurement_a_directory_that_does_not_exist_yet(self):
        spec = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
        self.settings_read.return_value = types.SimpleNamespace(route="r/m", confinement=spec)
        seen = []

        def measure(*args, **kwargs):
            given = MEASURE.bind(*args, **kwargs).arguments        # a keyword measure does not declare raises
            where = pathlib.Path(given["where"])
            seen.append((given["spec"], where.exists(), where.parent.is_dir(), given.get("exe")))
            return {"problems": []}

        with mock.patch.object(confine, "measure", measure):
            r = self.invoke(*self.check_argv())
        self.assertEqual((r.status, r.exit, r.doc["ready"]), (0, None, True))
        self.assertEqual(seen, [(spec, False, True, "/opt/client/opencode")])


if __name__ == "__main__":
    unittest.main()
