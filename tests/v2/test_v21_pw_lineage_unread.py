"""V2.1 (owner decision 2026-10-15, "Lineage: duyệt theo khuyến nghị"; the lineage family of docs/v2.1/REPORT.md, open
since the round-2 note of closure-evidence/v2/v2.1/mutation/ROUND-2.md): what `aisef run --parent` does with evidence
it cannot read.

A child run whose evidence is THERE and cannot be read — a directory the system will not let this process search, a
journal it will not open, one that does not reconstruct — was taken for a child that never began (UNBEGUN) and its
claim was superseded by a new generation: the lineage forked on an absence of knowledge, and the module's own rule
("a child that began is never superseded") was false exactly when the evidence of the beginning was damaged. The owner:
that evidence is a fourth state, UNREAD; it is never replaced by other evidence (not even by the claimant being
provably gone) and is superseded only by the operator naming the claim's sha256 (`--supersede-claim`, the way that
already exists). A predecessor that cannot be listed or written is a structured refusal (`LineageRefused`, exit 2
through `RunRefused`), never a traceback. A read error never releases or takes a claim, and nothing is deleted.

What is still true and is pinned beside it (the controls): what is genuinely not there, a journal of no bytes and a
record with no journal are UNBEGUN / ENDED_UNBEGUN and are superseded by evidence as before; a child whose journal
reads and holds an event is BEGUN and is never superseded, asserted or not.

Round 2 (two independent reviews of the lane found the same holes): the child's evidence is also THERE and damaged when
a link that leads nowhere, or a file, stands where the journal's path should lead; and a record that names a journal
of events (`RUN.json` with `journal.lines > 0`) makes the journal's absence or emptiness no evidence of a run that never
began — it was taken for ENDED_UNBEGUN and superseded even while its claimant was alive. The claim's refusals say
what to do (not "continue a copy", and not "restore write access" for a full volume).

The tests that need permission modes say so (a user that is not root, POSIX modes) and use real file permissions in a
temporary directory, not doubles: the refusal is what the file system answers. The rest run wherever the suite does,
including as root. Offline; no client, no provider."""

from __future__ import annotations

import contextlib
import errno
import hashlib
import io
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import cli, lineage  # noqa: E402
from tests.v2.test_app_run import SETTINGS, make_repo, project_bundle  # noqa: E402
from tests.v2.test_v21_r3_usage_no_progress import written  # noqa: E402

IS_POSIX_USER = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0
POSIX_USER = unittest.skipUnless(IS_POSIX_USER, "POSIX permission modes, as a user that is not root")
NEEDS_PS = unittest.skipUnless(os.name == "posix", "the process table (`ps`) the claimant's absence is read from")
JOURNAL = lineage.JOURNAL.as_posix()


def a_journal() -> str:
    """The text of a journal that holds events (run/begin, plan/frozen and a story that begins)."""
    return written(lambda j: j.begin())


class Lineage(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = pathlib.Path(os.path.realpath(t.name))
        self.pred = self.root / "run2"
        self.pred.mkdir()
        self.child = self.root / "run3"
        self.new = self.root / "run4"

    # -- the evidence of the claimed child, in the states the tests need ---------------------------------------------
    def journal_path(self) -> pathlib.Path:
        return self.child / lineage.JOURNAL

    def put_journal(self, text: str | bytes) -> pathlib.Path:
        self.journal_path().parent.mkdir(parents=True, exist_ok=True)
        data = text if isinstance(text, bytes) else text.encode("utf-8")
        self.journal_path().write_bytes(data)
        return self.journal_path()

    def locked(self, path: pathlib.Path, mode: int) -> None:
        """`path` made to refuse (mode), and given back before the temporary directory is removed."""
        path.chmod(mode)
        self.addCleanup(path.chmod, 0o755)

    def claim_by(self, child: pathlib.Path, *, gone: bool = True) -> bytes:
        """CONTINUED-BY.json on the predecessor naming `child`, whose claimant is provably gone (a process that ran and
        ended on this host) unless `gone` is False (this process, alive). The file's bytes."""
        if gone:
            p = subprocess.Popen([sys.executable, "-c", "pass"])
            p.wait()
            who = {"host": socket.gethostname(), "pid": p.pid, "started": "Thu Jan  1 00:00:00 2026"}
        else:
            who = lineage.claimant()
        data = (json.dumps({"run": str(child), "claimed": 1.0, "claimant": who}, sort_keys=True) + "\n").encode("utf-8")
        (self.pred / lineage.CLAIM).write_bytes(data)
        return data

    def listing(self) -> list[str]:
        return sorted(p.name for p in self.pred.iterdir())

    def link(self, target: pathlib.Path, at: pathlib.Path) -> None:
        at.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, at)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"no symbolic links here ({type(e).__name__})")

    # -- the things asserted ----------------------------------------------------------------------------------------
    def assert_not_superseded(self, claimed: bytes, **kw) -> str:
        """A new run asking for the lineage is refused, and the predecessor's directory is exactly as it was: no
        generation written, the claim byte for byte. The refusal's text."""
        before = self.listing()
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(self.pred, self.new, 2.0, **kw)
        self.assertEqual(self.listing(), before, "a refused claim wrote nothing")
        self.assertEqual((self.pred / lineage.CLAIM).read_bytes(), claimed)
        return str(c.exception)


class UnreadContract:
    """What holds of a child whose evidence is there and cannot be read, whichever way it is damaged: UNREAD, not
    superseded by the claimant's absence, superseded only by the operator naming the claim's sha256. A mixin: the
    concrete class gives `variants()`, a name -> a function that makes the child's evidence such a state."""

    def each(self, check) -> None:
        """`check(name)` for each variant, on a predecessor, a child and a new run of its own (nothing is shared)."""
        variants = self.variants()
        self.assertTrue(variants)
        for n, (name, make) in enumerate(variants.items()):
            with self.subTest(name):
                base = self.root / f"case{n}"
                base.mkdir()
                self.pred, self.child, self.new = base / "run2", base / "run3", base / "run4"
                self.pred.mkdir()
                make()
                check(name)

    def test_the_state_is_unread_and_never_unbegun(self):
        def check(_name: str) -> None:
            self.claim_by(self.child)
            self.assertEqual(lineage.child_state(self.child), "UNREAD")
            self.assertEqual(lineage.continued_by(self.pred), (str(self.child), "UNREAD"))
        self.assertEqual(lineage.UNREAD, "UNREAD")
        self.each(check)

    def test_a_claimant_that_is_provably_gone_does_not_supersede_it(self):
        """The claimant's absence is evidence about the process, not about the child's run: a child that may have
        begun is not replaced because whoever started it is gone."""
        def check(_name: str) -> None:
            claimed = self.claim_by(self.child, gone=True)
            text = self.assert_not_superseded(claimed)
            self.assertIn("UNREAD", text)
            self.assertIn(str(self.child), text)
            self.assertIn(f"--supersede-claim {hashlib.sha256(claimed).hexdigest()}", text)
        self.each(check)

    def test_an_alive_claimant_or_none_at_all_changes_nothing(self):
        def check(_name: str) -> None:
            claimed = self.claim_by(self.child, gone=False)
            self.assertIn("UNREAD", self.assert_not_superseded(claimed))
        self.each(check)


    def test_the_operator_may_supersede_by_the_claims_sha256_and_only_by_it(self):
        def check(_name: str) -> None:
            claimed = self.claim_by(self.child)
            sha = hashlib.sha256(claimed).hexdigest()
            self.assert_not_superseded(claimed, supersede="0" * 64)          # a sha256 that is not the claim's
            self.assert_not_superseded(claimed, supersede=sha[::-1])
            doc = lineage.claim(self.pred, self.new, 3.0, supersede=sha)
            self.assertEqual(self.listing(), sorted([lineage.CLAIM, "CONTINUED-BY.2.json"]))
            self.assertEqual((self.pred / lineage.CLAIM).read_bytes(), claimed, "the history is kept, byte for byte")
            sup = doc["supersedes"]
            self.assertEqual((sup["claim"], sup["sha256"], sup["child"], sup["child_state"], sup["operator_asserted"]),
                             (lineage.CLAIM, sha, str(self.child), "UNREAD", True))
            self.assertTrue(sup["unread"], "the cause is recorded with the assertion")
            self.assertEqual(json.loads((self.pred / "CONTINUED-BY.2.json").read_text(encoding="utf-8")), doc)
            self.assertEqual([n for n, _ in lineage.claims(self.pred)], [1, 2])
        self.each(check)


class ChildThatCannotBeRead(UnreadContract, Lineage):
    """A child with evidence there that cannot be read is UNREAD: not UNBEGUN, not superseded by the claimant's
    absence, and only the operator's sha256 supersedes it."""

    def variants(self) -> dict:
        """name -> a function that makes the child's evidence such a state (each on a fresh directory)."""
        def dir_without_search() -> None:
            self.put_journal(a_journal())
            self.locked(self.child, 0o000)

        def dir_read_without_search() -> None:
            self.put_journal(a_journal())
            self.locked(self.child, 0o600)

        def journal_without_read() -> None:
            self.locked(self.put_journal(a_journal()), 0o000)

        def a_byte_changed_mid_chain() -> None:
            lines = a_journal().split("\n")
            lines[1] = lines[1].replace("PLAN-1", "PLAN-9")
            self.put_journal("\n".join(lines))

        def not_a_journal() -> None:
            self.put_journal("this is not a journal\n")

        def torn_first_line() -> None:
            self.put_journal(a_journal()[:60])

        def journal_is_a_directory() -> None:
            self.journal_path().mkdir(parents=True)

        def not_text() -> None:
            self.put_journal(b"\xff\xfe\x00 not text\n")

        found = {"a byte of the journal changed in the middle of its chain": a_byte_changed_mid_chain,
                 "the journal is not a journal": not_a_journal,
                 "the journal is not text": not_text,
                 "the journal holds a torn first line and no complete event": torn_first_line,
                 "the journal's path is a directory": journal_is_a_directory}
        if IS_POSIX_USER:       # a mode is refused only to a user that is not root
            found.update({"the child's directory cannot be searched": dir_without_search,
                          "the child's directory can be read and not searched": dir_read_without_search,
                          "the journal cannot be opened": journal_without_read})
        return found

    @POSIX_USER
    def test_the_refusal_says_what_could_not_be_read_and_what_the_operator_may_do(self):
        self.claim_by(self.child)
        self.put_journal(a_journal())
        self.locked(self.journal_path(), 0o000)
        text = self.assert_not_superseded((self.pred / lineage.CLAIM).read_bytes())
        self.assertIn("PermissionError", text)          # the cause, not "the child never began"
        self.assertIn(lineage.JOURNAL.name, text)
        self.assertRegex(text, r"restore|read access|inspect")       # a way back that does not need the assertion

    @POSIX_USER
    @NEEDS_PS
    def test_an_assertion_is_the_operators_even_when_the_claimant_is_gone(self):
        """`operator_asserted` records whose statement superseded: for an unreadable child it is always the operator's,
        whatever the claimant's state (the claimant's absence is not evidence about the child)."""
        self.claim_by(self.child, gone=True)
        self.put_journal(a_journal())
        self.locked(self.journal_path(), 0o000)
        sha = hashlib.sha256((self.pred / lineage.CLAIM).read_bytes()).hexdigest()
        doc = lineage.claim(self.pred, self.new, 3.0, supersede=sha)
        self.assertIs(doc["supersedes"]["claimant_gone"], True)
        self.assertIs(doc["supersedes"]["operator_asserted"], True)

    def test_a_torn_first_line_cause_names_the_journal_and_says_it_is_incomplete(self):
        """L200: a journal present but cut before its first complete event is UNREAD, and the cause the operator
        reads (the refusal at `claim`, and the recorded `supersedes['unread']`) says the evidence is THERE and
        holds no complete event -- not a bare filename, which would not tell a damaged journal from an absence."""
        self.put_journal(a_journal()[:60])
        state, why = lineage.child_evidence(self.child)
        self.assertEqual(state, lineage.UNREAD)
        self.assertIn(lineage.JOURNAL.name, why)                  # names what could not be read
        self.assertRegex(why, r"holds bytes|no complete event")   # present but incomplete, not an absence


class WhatStaysAsItWas(Lineage):
    """The controls: absence is not unreadable, and a child that reads is decided as before."""

    @NEEDS_PS
    def test_a_child_that_is_not_there_is_unbegun_and_superseded_by_evidence(self):
        claimed = self.claim_by(self.child)
        self.assertEqual(lineage.child_state(self.child), lineage.UNBEGUN)
        doc = lineage.claim(self.pred, self.new, 2.0)
        self.assertEqual((doc["supersedes"]["child_state"], doc["supersedes"]["claimant_gone"],
                          doc["supersedes"]["operator_asserted"]), (lineage.UNBEGUN, True, False))
        self.assertEqual((self.pred / lineage.CLAIM).read_bytes(), claimed)
        self.assertNotIn("unread", doc["supersedes"])

    @NEEDS_PS
    def test_a_journal_of_no_bytes_is_unbegun(self):
        self.claim_by(self.child)
        self.put_journal(b"")
        self.assertEqual(lineage.child_state(self.child), lineage.UNBEGUN)
        self.assertEqual(lineage.claim(self.pred, self.new, 2.0)["supersedes"]["child_state"], lineage.UNBEGUN)

    def test_a_child_with_a_record_and_no_journal_is_ended_unbegun(self):
        self.claim_by(self.child)
        self.child.mkdir()
        (self.child / "RUN.json").write_text("{}", encoding="utf-8")
        self.assertEqual(lineage.child_state(self.child), lineage.ENDED_UNBEGUN)
        self.assertEqual(lineage.claim(self.pred, self.new, 2.0)["supersedes"]["child_state"], lineage.ENDED_UNBEGUN)

    def test_a_child_whose_journal_reads_and_holds_an_event_is_begun_and_never_superseded(self):
        claimed = self.claim_by(self.child)
        self.put_journal(a_journal())
        self.assertEqual(lineage.child_state(self.child), lineage.BEGUN)
        sha = hashlib.sha256(claimed).hexdigest()
        for kw in ({}, {"supersede": sha}):
            self.assertIn("which began", self.assert_not_superseded(claimed, **kw))

    def test_a_begun_child_with_a_torn_last_line_is_begun(self):
        """The reader's verified prefix holds events: the child began, and the torn line changes nothing about that."""
        claimed = self.claim_by(self.child)
        self.put_journal(a_journal() + '{"chain": "cut')
        self.assertEqual(lineage.child_state(self.child), lineage.BEGUN)
        self.assertIn("which began", self.assert_not_superseded(claimed))


class PredecessorThatCannotBeListedOrWritten(Lineage):
    """`claims` / `claim` on a predecessor the system refuses: LineageRefused with the cause, never a PermissionError;
    nothing taken, nothing released."""

    @POSIX_USER
    def test_a_predecessor_that_cannot_be_searched_refuses(self):
        for mode in (0o000, 0o400):
            with self.subTest(oct(mode)):
                self.pred.chmod(0o755)
                self.locked(self.pred, mode)
                with self.assertRaises(lineage.LineageRefused) as c:
                    lineage.claims(self.pred)
                self.assertIn("PermissionError", str(c.exception))
                with self.assertRaises(lineage.LineageRefused):
                    lineage.claim(self.pred, self.new, 2.0)

    @POSIX_USER
    def test_a_predecessor_that_can_be_searched_and_not_listed_refuses_rather_than_missing_generations(self):
        """`glob` answers an empty listing for a directory it cannot list: generation 2 and later were not seen, and
        generation 1 — found by its exact name — was taken for the newest."""
        (self.pred / lineage.CLAIM).write_text('{"run": "x"}\n', encoding="utf-8")
        (self.pred / "CONTINUED-BY.2.json").write_text('{"run": "y"}\n', encoding="utf-8")
        self.locked(self.pred, 0o300)
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claims(self.pred)
        self.assertIn("PermissionError", str(c.exception))

    @POSIX_USER
    def test_a_read_only_predecessor_refuses_with_the_cause_and_takes_nothing(self):
        self.locked(self.pred, 0o500)
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(self.pred, self.new, 2.0)
        text = str(c.exception)
        self.assertIn(str(self.pred), text)
        self.assertIn("PermissionError", text)
        self.assertIn(lineage.CLAIM, text)          # what could not be created
        self.pred.chmod(0o755)
        self.assertEqual(self.listing(), [], "nothing was created in the predecessor")

    @POSIX_USER
    def test_a_read_only_predecessor_whose_child_began_is_refused_for_that_first(self):
        """The reconciliation comes before the write: the operator is told the lineage continues from the child."""
        self.claim_by(self.child)
        self.put_journal(a_journal())
        self.locked(self.pred, 0o500)
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(self.pred, self.new, 2.0)
        self.assertIn("which began", str(c.exception))

    def test_a_predecessor_that_is_not_there_is_not_a_refusal_of_claims(self):
        """`claims` of what is not there is no claims (as before); `claim` then fails to create, as a run that is not
        a run — not a read error."""
        self.assertEqual(lineage.claims(self.root / "nowhere"), [])
        f = self.root / "a-file"
        f.write_text("x", encoding="utf-8")
        self.assertEqual(lineage.claims(f), [])

    @POSIX_USER
    def test_the_lineages_account_lists_what_it_cannot_list_and_does_not_raise(self):
        """`lineage_account` iterates `claims` of every run of the chain: a directory it cannot list is spend it
        cannot see (superseded children), listed as unaccounted — never a raise out of the account, never a known 0."""
        self.locked(self.pred, 0o300)
        got = lineage.lineage_account(self.pred)
        self.assertTrue(got["unaccounted"], got)
        self.assertTrue(any("claim" in u for u in got["unaccounted"]), got["unaccounted"])

    def test_not_there_takes_the_windows_answers_for_absence_but_not_a_refusal(self):
        """The guard forks absence from a refusal to look. pathlib's Windows answers for 'nothing there' -- an invalid
        name (123), a drive not ready (21), a reparse point that does not resolve (1921) -- are absence even though
        their errno is not one of _NOT_THERE; a permission refusal is not. _look / _predecessor / account_of fork
        UNBEGUN (superseded by evidence) from UNREAD / LineageRefused on exactly this."""
        class Win(OSError):
            def __init__(self, winerror: int) -> None:
                super().__init__(errno.EINVAL, "no")   # EINVAL is not one of _NOT_THERE
                self.winerror = winerror
        for win in lineage._NOT_THERE_WINERROR:        # (21, 123, 1921): absence via the winerror branch
            self.assertTrue(lineage.not_there(Win(win)), win)
        for err in lineage._NOT_THERE:                 # the errno branch still answers absence
            self.assertTrue(lineage.not_there(OSError(err, "no")), err)
        self.assertFalse(lineage.not_there(OSError(errno.EACCES, "denied")))   # a refusal, not absence
        self.assertFalse(lineage.not_there(Win(999)))                          # a winerror outside the set is a refusal


class TheOperatorSeesARefusalNotATraceback(Lineage):
    """`aisef run --parent`, through the CLI: exit 2 and `aisef run: refused: <cause>` — the claim stage's refusals
    all arrive as `RunRefused`."""

    def setUp(self) -> None:
        super().setUp()
        self.source = self.root / "source"
        self.bundle = self.root / "bundle.json"
        self.bundle.write_text(json.dumps(project_bundle(make_repo(self.source))), encoding="utf-8")
        self.settings = self.root / "settings.json"
        self.settings.write_text(json.dumps(SETTINGS), encoding="utf-8")
        (self.pred / lineage.STARTED).write_text("{}\n", encoding="utf-8")

    def run_cli(self, name: str, *extra: str, parent: pathlib.Path | None = None) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.run(["--project", str(self.bundle), "--settings", str(self.settings), "--repo", str(self.source),
                            "--out", str(self.root / name), "--parent", str(parent or self.pred), *extra])
        return code, err.getvalue()

    @POSIX_USER
    def test_an_unread_child_is_refused_and_no_generation_is_written(self):
        claimed = self.claim_by(self.child)
        self.locked(self.put_journal(a_journal()), 0o000)
        code, err = self.run_cli("out-unread")
        self.assertEqual(code, 2, err)
        self.assertRegex(err, r"^aisef run: refused: ")
        self.assertIn("UNREAD", err)
        self.assertIn(f"--supersede-claim {hashlib.sha256(claimed).hexdigest()}", err)
        self.assertEqual(self.listing(), sorted([lineage.CLAIM, lineage.STARTED]), "no generation written")

    @POSIX_USER
    def test_the_operators_assertion_by_the_claims_sha256_takes_the_claim_through_the_cli(self):
        """The way that already exists, for the new state: the generation is written (the later stages of the run are not
        this test's: the client is not on the PATH here, and the run is refused there, after the claim)."""
        claimed = self.claim_by(self.child)
        self.locked(self.put_journal(a_journal()), 0o000)
        sha = hashlib.sha256(claimed).hexdigest()
        _, err = self.run_cli("out-wrong", "--supersede-claim", "0" * 64)
        self.assertIn("UNREAD", err)
        self.assertEqual(self.listing(), sorted([lineage.CLAIM, lineage.STARTED]))
        _, err = self.run_cli("out-asserted", "--supersede-claim", sha)
        self.assertNotIn("UNREAD", err)
        doc = json.loads((self.pred / "CONTINUED-BY.2.json").read_text(encoding="utf-8"))
        self.assertEqual((doc["supersedes"]["child_state"], doc["supersedes"]["operator_asserted"], doc["run"]),
                         ("UNREAD", True, str(self.root / "out-asserted")))
        self.assertEqual((self.pred / lineage.CLAIM).read_bytes(), claimed)

    @POSIX_USER
    def test_a_read_only_predecessor_is_refused_not_a_traceback(self):
        self.locked(self.pred, 0o500)
        code, err = self.run_cli("out-readonly")
        self.assertEqual(code, 2, err)
        self.assertRegex(err, r"^aisef run: refused: ")
        self.assertIn("PermissionError", err)
        self.assertNotIn("Traceback", err)

    def test_a_predecessor_that_is_not_there_keeps_its_own_refusal(self):
        """Absence is not a read error: the refusal it always had, and no claim anywhere."""
        code, err = self.run_cli("out-absent", parent=self.root / "never-made")
        self.assertEqual(code, 2, err)
        self.assertIn("no run record there", err)
        self.assertNotIn("PermissionError", err)

    @POSIX_USER
    def test_a_predecessor_that_cannot_be_searched_is_refused_naming_the_cause(self):
        """On 3.14 `Path.is_file` answers False for it and the run said "no run record there"; on 3.11-3.13 it raised."""
        self.locked(self.pred, 0o000)
        code, err = self.run_cli("out-unsearchable")
        self.assertEqual(code, 2, err)
        self.assertIn("PermissionError", err)
        self.assertNotIn("no run record there", err)


class ChildEvidenceThatIsThereAndDamaged(UnreadContract, Lineage):
    """Round 2, the first hole: the system answers "nothing there" for a link that leads nowhere, for a link that loops,
    and for a name below a file — and that answer was taken for a child that never began, so its claim was superseded
    by the claimant's absence. Something stands on the journal's path: it is evidence there and damaged (UNREAD). What
    is genuinely not there stays an absence (`WhatStaysAsItWas`, `NothingOnThePathIsStillAbsent`)."""

    def variants(self) -> dict:
        def dangling_link() -> None:
            self.link(self.child / "nowhere.jsonl", self.journal_path())

        def looping_link() -> None:
            self.link(self.journal_path(), self.journal_path())

        def link_to_nothing_in_place_of_the_directory() -> None:
            (self.child / "run").mkdir(parents=True)
            self.link(self.root / "no-such-directory", self.child / "run" / "journals")

        def the_child_is_a_file() -> None:
            self.child.write_text("not a run directory", encoding="utf-8")

        def run_is_a_file() -> None:
            self.child.mkdir()
            (self.child / "run").write_text("not a directory", encoding="utf-8")

        def journals_is_a_file() -> None:
            (self.child / "run").mkdir(parents=True)
            (self.child / "run" / "journals").write_text("not a directory", encoding="utf-8")

        return {"the journal is a link that leads nowhere": dangling_link,
                "the journal is a link that loops": looping_link,
                "journals is a link that leads nowhere": link_to_nothing_in_place_of_the_directory,
                "the child's path is a file": the_child_is_a_file,
                "run is a file": run_is_a_file,
                "journals is a file": journals_is_a_file}

    def test_the_cause_says_what_stands_where_the_journal_should_be(self):
        def check(_name: str) -> None:
            self.claim_by(self.child)
            state, why = lineage.child_evidence(self.child)
            self.assertEqual(state, lineage.UNREAD)
            self.assertRegex(why, r"link that leads nowhere|is not a directory")
            self.assertIn(str(self.child), why)
            self.assertIn(why, self.assert_not_superseded((self.pred / lineage.CLAIM).read_bytes()))
        self.each(check)


class NothingOnThePathIsStillAbsent(Lineage):
    """The controls of the above: a child directory that is not there, an empty one, one with `run` and nothing below
    it are what a run that never began looks like — UNBEGUN, superseded by evidence as before."""

    @NEEDS_PS
    def test_each_is_unbegun_and_superseded_by_evidence(self):
        def nothing() -> None:
            pass

        def empty_directory() -> None:
            self.child.mkdir()

        def run_only() -> None:
            (self.child / "run").mkdir(parents=True)

        def journals_only() -> None:
            self.journal_path().parent.mkdir(parents=True)

        for n, (name, make) in enumerate({"the child is not there": nothing, "an empty directory": empty_directory,
                                          "run with nothing below": run_only,
                                          "journals with no journal": journals_only}.items()):
            with self.subTest(name):
                base = self.root / f"case{n}"
                base.mkdir()
                self.pred, self.child, self.new = base / "run2", base / "run3", base / "run4"
                self.pred.mkdir()
                make()
                self.claim_by(self.child)
                self.assertEqual(lineage.child_evidence(self.child), (lineage.UNBEGUN, None))
                doc = lineage.claim(self.pred, self.new, 2.0)
                self.assertEqual((doc["supersedes"]["child_state"], doc["supersedes"]["operator_asserted"]),
                                 (lineage.UNBEGUN, False))

    def test_a_name_no_file_can_have_is_not_a_child_that_cannot_be_read(self):
        self.assertEqual(lineage.child_evidence(pathlib.Path(str(self.child) + "\x00x")), (lineage.UNBEGUN, None))


class RecordThatNamesAJournalOfEvents(UnreadContract, Lineage):
    """Round 2, the second hole (the reviewer's MAJOR): `RUN.json` is the run's own account. When it names a journal of
    events (`journal.lines > 0`) the run began — and the journal's absence, or its having no bytes, was read as "a record
    and no journal: refused before it began" (ENDED_UNBEGUN), which is superseded by evidence even with its claimant
    alive. A record that cannot be read or is not a record says nothing that would let the absence be taken so either."""

    def record(self, doc) -> None:
        self.child.mkdir(parents=True, exist_ok=True)
        (self.child / "RUN.json").write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")

    def names(self, lines) -> dict:
        return {"journal": {"path": JOURNAL, "sha256": "0" * 64, "lines": lines, "closed": "SHUTDOWN"}}

    def variants(self) -> dict:
        def journal_absent() -> None:
            self.record(self.names(5))

        def journal_of_no_bytes() -> None:
            self.record(self.names(5))
            self.put_journal(b"")

        def record_cut() -> None:
            self.record('{"journal": {"path": "run/jour')

        def record_not_text() -> None:
            self.child.mkdir()
            (self.child / "RUN.json").write_bytes(b"\xff\xfe\x00")

        def record_is_a_directory() -> None:
            self.child.mkdir()
            (self.child / "RUN.json").mkdir()

        def record_is_no_object() -> None:
            self.record("[1, 2]")

        def journal_entry_is_no_record() -> None:
            self.record({"journal": "run/journals/aisef-run.jsonl"})

        def line_count_is_no_number() -> None:
            self.record({"journal": {"path": JOURNAL, "lines": "5"}})

        def record_without_read() -> None:
            self.record({})
            self.locked(self.child / "RUN.json", 0o000)

        found = {"the record names a journal of 5 lines and there is none": journal_absent,
                 "the record names a journal of 5 lines and the file has no bytes": journal_of_no_bytes,
                 "the record was cut": record_cut,
                 "the record is not text": record_not_text,
                 "the record is a directory": record_is_a_directory,
                 "the record is JSON and no object": record_is_no_object,
                 "the record's journal is not a journal record": journal_entry_is_no_record,
                 "the record's line count is not a number": line_count_is_no_number}
        if IS_POSIX_USER:
            found["the record cannot be opened"] = record_without_read
        return found

    def test_the_cause_says_what_the_record_says_and_what_is_not_there(self):
        self.record(self.names(5))
        self.claim_by(self.child)
        state, why = lineage.child_evidence(self.child)
        self.assertEqual(state, lineage.UNREAD)
        self.assertIn("5 lines", why)
        self.assertIn(lineage.JOURNAL.name, why)
        self.assertIn("is not there", why)
        self.put_journal(b"")
        self.assertIn("holds no bytes", lineage.child_evidence(self.child)[1])

    def test_a_record_that_says_the_run_ended_before_it_began_is_still_ended_unbegun(self):
        """What the record says in its own words: it names no journal, or one of no lines — superseded by evidence
        whatever the claimant is (it is done: it wrote its record)."""
        cases = {"no journal key": {}, "journal null": {"journal": None}, "journal empty": {"journal": {}},
                 "a journal of no lines": self.names(0)}
        for n, (name, doc) in enumerate(cases.items()):
            for alive in (False, True):
                with self.subTest(name, claimant_alive=alive):
                    base = self.root / f"case{n}-{alive}"
                    base.mkdir()
                    self.pred, self.child, self.new = base / "run2", base / "run3", base / "run4"
                    self.pred.mkdir()
                    self.record(doc)
                    self.claim_by(self.child, gone=not alive)
                    self.assertEqual(lineage.child_evidence(self.child), (lineage.ENDED_UNBEGUN, None))
                    got = lineage.claim(self.pred, self.new, 2.0)["supersedes"]
                    self.assertEqual((got["child_state"], got["operator_asserted"]), (lineage.ENDED_UNBEGUN, False))

    def test_a_record_of_events_and_a_journal_that_reads_is_begun(self):
        self.record(self.names(5))
        self.put_journal(a_journal())
        self.assertEqual(lineage.child_state(self.child), lineage.BEGUN)

    def test_the_cause_names_what_about_the_record_cannot_be_read(self):
        """The UNREAD cause is the operator's own diagnosis of RUN.json (the run's own account): it names what about
        the record made the journal's absence no evidence of a run that never began, not a bare exception. Each
        record variant's words (round 2: a record that cannot be read or is not a record says nothing)."""
        cases = {
            "[1, 2]": "RUN.json is there and is not a record (a JSON object)",            # JSON, no object (L243)
            '{"journal": {"path": "run/jour': "RUN.json is there and is not a record",    # cut: not a record (L241)
            '{"journal": "run/journals/x.jsonl"}': "RUN.json's journal is not a journal record",  # no count (L252)
        }
        for n, (doc, cause) in enumerate(cases.items()):
            with self.subTest(cause):
                self.child = self.root / f"rec{n}"
                self.record(doc)
                state, why = lineage.child_evidence(self.child)
                self.assertEqual(state, lineage.UNREAD)
                self.assertIn(cause, why)
                self.assertIn(lineage.JOURNAL.name, why)
        # RUN.json itself cannot be opened: a directory stands in its place (a non-ENOENT OSError; no mode needed) (L239)
        self.child = self.root / "rec-dir"
        self.child.mkdir()
        (self.child / "RUN.json").mkdir()
        state, why = lineage.child_evidence(self.child)
        self.assertEqual(state, lineage.UNREAD)
        self.assertIn("RUN.json cannot be read", why)
        self.assertIn(lineage.JOURNAL.name, why)


class TheClaimsRefusalsSayWhatToDo(Lineage):
    """Round 2: each refusal of `claim` names the way back — and none suggests a way round the one continuation a run
    may have (a copy of the run has claims of its own: two copies of one run, both unclaimed, are both continuable)."""

    @POSIX_USER
    def test_a_claim_that_cannot_be_read_says_to_make_it_readable_and_that_nothing_was_taken(self):
        self.claim_by(self.child)
        self.locked(self.pred / lineage.CLAIM, 0o000)
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(self.pred, self.new, 2.0)
        text = str(c.exception)
        self.assertIn("PermissionError", text)
        self.assertRegex(text, r"readable again")
        self.assertIn("nothing was taken", text)
        self.assertEqual(self.listing(), [lineage.CLAIM])

    def test_a_full_volume_is_told_to_free_space_not_to_restore_write_access(self):
        import errno
        real = os.open

        def full(path, flags, *a, **kw):
            if str(path).endswith(lineage.CLAIM):
                raise OSError(errno.ENOSPC, "No space left on device")
            return real(path, flags, *a, **kw)
        with mock.patch.object(lineage.os, "open", full):
            with self.assertRaises(lineage.LineageRefused) as c:
                lineage.claim(self.pred, self.new, 2.0)
        text = str(c.exception)
        self.assertIn("No space left on device", text)
        self.assertIn("free space", text)
        self.assertNotIn("restore write access", text)
        self.assertNotIn("writable copy", text)
        self.assertIn("nothing was taken", text)
        self.assertEqual(self.listing(), [])

    @POSIX_USER
    def test_a_read_only_predecessor_is_not_advised_to_continue_a_copy(self):
        self.locked(self.pred, 0o500)
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(self.pred, self.new, 2.0)
        text = str(c.exception)
        self.assertIn("restore write access", text)
        self.assertNotIn("writable copy", text)
        self.assertRegex(text, r"[Nn]ot from a copy")


if __name__ == "__main__":
    unittest.main()
