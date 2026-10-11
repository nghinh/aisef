"""V2.1 mutation survivors, batch T09c: the lineage's walk, its process identity and its anchor file
(aisef2/app/lineage.py: lineage_account, predecessor_of, process_started, read_anchor).

The lineage of a continued run is walked from evidence only, and a decision about another run's process is taken from
the process table or not at all:

* the walk reaches every run of the lineage and every attempt a later claim replaced, once each, the replaced ones
  reported as superseded — the inherited spend counts against the child's ceilings and `--verify` re-derives it;
* the walk does not stop at a run whose RUN.started.json is gone or torn when its RUN.json names the predecessor;
* a process table that cannot be run or read answers "unknown" — never "no such process" (None) and never an empty
  text — because only the first lets a claim be superseded by evidence;
* an anchor file that is not exactly one 64-hex line is a ValueError, whatever bytes it holds.

Offline and deterministic: hand-built run directories (no run, no journal, no driver), `subprocess.run` replaced where
the process table matters, no real `ps` and no wall clock. The existing kill files build a lineage one generation deep
from a real run; none of them has a replaced attempt along the chain, a damaged RUN.started.json, a `ps` that fails or
an anchor file of bytes."""

from __future__ import annotations

import json
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

from aisef2.app import lineage  # noqa: E402

REAL_RUN = subprocess.run
LSTART = "Thu Jan  1 00:00:00 1970"


def put(path: pathlib.Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def preflight_ledger(run: pathlib.Path, requests: int, unanswered: int = 0) -> None:
    """`requests` preflight requests, each sent and answered, then `unanswered` sent and never answered: what
    `account_of` counts as that run's spend, and what it cannot know."""
    rows = []
    for n in range(1, requests + 1):
        rows += [{"n": n, "event": "sent", "kind": "chat"},
                 {"n": n, "event": "done", "http": 200, "input_tokens": 1, "output_tokens": 1}]
    for n in range(requests + 1, requests + unanswered + 1):
        rows.append({"n": n, "event": "sent", "kind": "chat"})
    path = run / "preflight" / "LEDGER.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def names(account: dict) -> list[str]:
    return [pathlib.Path(r["run"]).name for r in account["runs"]]


class Dirs(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)

    def run_dir(self, name: str, requests: int = 0, unanswered: int = 0) -> pathlib.Path:
        d = self.root / name
        d.mkdir()
        if requests or unanswered:
            preflight_ledger(d, requests, unanswered)
        return d

    def claim(self, predecessor: pathlib.Path, generation: int, child: pathlib.Path) -> None:
        name = lineage.CLAIM if generation == 1 else f"CONTINUED-BY.{generation}.json"
        put(predecessor / name, {"run": str(child), "claimed": 1.0, "claimant": {}})

    def continues(self, run: pathlib.Path, predecessor: pathlib.Path, file: str = lineage.STARTED) -> None:
        put(run / file, {"continues": {"path": str(predecessor)}})


class ReplacedAttemptAlongTheChain(Dirs):
    """A lineage of depth 2 whose oldest run A was continued three times: its first claim named D and its second E —
    both replaced — and its third is B, which continues A. C asks to continue B. What D and E spent is part of what the
    lineage spent (their preflight may have spent; E's last request was never answered): the account lists B, D, E
    and A once each, D and E as superseded, sums their requests and lists E's unknown spend instead of dropping it;
    the report (`lineage_usage.runs[].superseded`) says which attempts were replaced. The inherited spend counts
    against the child's ceilings and an unaccounted item stops paid work (aisef2/app/run.py), so a replaced attempt
    that goes missing is spend the next run is not charged for.

    Pins aisef2/app/lineage.py::lineage_account [35, 38, 41, 42]."""

    def setUp(self) -> None:
        super().setUp()
        self.a, self.b = self.run_dir("A", requests=5), self.run_dir("B", requests=1)
        self.c, self.d = self.run_dir("C"), self.run_dir("D", requests=2)
        self.e = self.run_dir("E", requests=2, unanswered=1)
        self.claim(self.a, 1, self.d)
        self.claim(self.a, 2, self.e)
        self.claim(self.a, 3, self.b)
        self.continues(self.b, self.a)

    def test_every_replaced_attempt_is_listed_once_and_its_spend_summed(self):
        acct = lineage.lineage_account(self.b, self.c)
        self.assertEqual(sorted(names(acct)), ["A", "B", "D", "E"])
        self.assertEqual(acct["provider_requests"], 5 + 1 + 2 + 3)

    def test_the_unknown_spend_of_a_replaced_attempt_is_listed_not_dropped(self):
        acct = lineage.lineage_account(self.b, self.c)
        unknown = {pathlib.Path(r["run"]).name: len(r["unaccounted"]) for r in acct["runs"]}
        self.assertEqual(unknown, {"A": 0, "B": 0, "D": 0, "E": 1})
        self.assertEqual(len(acct["unaccounted"]), 1)

    def test_the_replaced_attempts_are_marked_superseded_and_the_runs_of_the_chain_are_not(self):
        acct = lineage.lineage_account(self.b, self.c)
        flag = {pathlib.Path(r["run"]).name: r.get("superseded") for r in acct["runs"]}
        self.assertIs(flag["D"], True)
        self.assertIs(flag["E"], True)
        self.assertFalse(flag["A"])
        self.assertFalse(flag["B"])

    def test_the_usage_report_carries_the_flag(self):
        report = lineage.usage_lineage(self.b, self.c, {"tokens": {}, "cost": {}}, None)
        flag = {pathlib.Path(e["run"]).name: e["superseded"] for e in report["runs"]}
        self.assertEqual(flag, {"A": False, "B": False, "D": True, "E": True, "this run": False})


class PredecessorFromTheRecord(Dirs):
    """RUN.started.json is read first and RUN.json is its fallback: a run whose started file is absent, torn (a
    process killed between create and write leaves 0 bytes or a cut object) or not UTF-8 still names its predecessor
    through its record, and the walk of a lineage goes on through it. A run that names none has none — no exception.

    Pins aisef2/app/lineage.py::predecessor_of [1, 3, 7]; lineage_account [via predecessor_of]."""

    DAMAGE = {"empty": b"", "cut off": b'{"format": 3, "continues": {"pa', "not json": b"not json at all",
              "not utf-8": b"\xff\xfe\x00\x01"}

    def test_the_record_names_it_when_the_started_file_is_absent(self):
        a, b = self.run_dir("A"), self.run_dir("B")
        self.continues(b, a, "RUN.json")
        self.assertEqual(lineage.predecessor_of(b), a)

    def test_the_record_names_it_when_the_started_file_is_damaged(self):
        a = self.run_dir("A")
        for name, raw in self.DAMAGE.items():
            with self.subTest(name):
                b = self.run_dir("B-" + name.replace(" ", "-"))
                (b / lineage.STARTED).write_bytes(raw)
                self.continues(b, a, "RUN.json")
                self.assertEqual(lineage.predecessor_of(b), a)

    def test_a_run_that_names_none_has_none_whatever_its_files_hold(self):
        plain = self.run_dir("plain")
        put(plain / lineage.STARTED, {"format": 3})
        put(plain / "RUN.json", {"format": 3})
        nothing = self.run_dir("nothing")
        torn = self.run_dir("torn")                  # killed between create and write: 0 bytes, and no record yet
        (torn / lineage.STARTED).write_bytes(b"")
        both = self.run_dir("both")
        (both / lineage.STARTED).write_bytes(b"")
        (both / "RUN.json").write_bytes(b"\xff\xfe\x00")
        for run in (plain, nothing, torn, both):
            with self.subTest(run.name):
                self.assertIsNone(lineage.predecessor_of(run))

    def test_the_walk_goes_on_through_the_damaged_run(self):
        a = self.run_dir("A", requests=4)
        c = self.run_dir("C")
        for name, raw in {"absent": None, **self.DAMAGE}.items():
            with self.subTest(name):
                b = self.run_dir("B-" + name.replace(" ", "-"), requests=1)
                if raw is not None:
                    (b / lineage.STARTED).write_bytes(raw)
                self.continues(b, a, "RUN.json")
                acct = lineage.lineage_account(b, c)
                self.assertEqual(sorted(names(acct)), sorted([b.name, "A"]))
                self.assertEqual(acct["provider_requests"], 1 + 4)


def selected(argv: list[str]) -> int | None:
    """The pid a POSIX ps is asked for: through `-p <pid>` or `-p<pid>` only; a bare operand selects nothing."""
    for i, arg in enumerate(argv):
        if arg == "-p" and i + 1 < len(argv):
            return int(argv[i + 1])
        if arg.startswith("-p") and arg[2:].isdigit():
            return int(arg[2:])
    return None


def fake_ps(table: dict[int, str]):
    """A `ps` that selects processes only through `-p` and prints nothing, with a failing status, for a pid that is
    not in the table."""
    def run(argv, **kw):
        started = table.get(selected(argv))
        return subprocess.CompletedProcess(argv, 0 if started else 1, stdout=f"{started}\n" if started else "", stderr="")
    return run


def failing_ps(exc: BaseException):
    return mock.patch.object(lineage.subprocess, "run", side_effect=exc)


class ProcessTableAnswers(unittest.TestCase):
    """What `process_started` answers is the identity protocol of a claim's claimant: the start text of a live
    process, None for 'no such process', "unknown" when the table cannot be read. Pins
    aisef2/app/lineage.py::process_started [2, 3, 4, 10, 8]."""

    FAILURES = (FileNotFoundError(2, "no ps on this host"), PermissionError(13, "ps may not run"),
                OSError(24, "too many open files"), subprocess.TimeoutExpired(["ps"], 30))

    def test_a_table_that_cannot_be_run_answers_exactly_unknown(self):
        for exc in self.FAILURES:
            with self.subTest(type(exc).__name__), failing_ps(exc):
                self.assertEqual(lineage.process_started(4242), "unknown")

    def test_a_pid_is_asked_for_through_the_selector_every_ps_has(self):
        with mock.patch.object(lineage.subprocess, "run", fake_ps({4242: LSTART})):
            self.assertEqual(lineage.process_started(4242), LSTART)
            self.assertIsNone(lineage.process_started(4243))      # no such process: not "unknown"


class ClaimantOfAnUnreadableTable(Dirs):
    """A claim whose child never began is superseded by evidence only when its claimant is provably gone. A process
    table that cannot be read proves nothing: the claim is refused (the operator may name it), no generation is
    added; the same claim is superseded when the table answers that no such process exists.

    Pins aisef2/app/lineage.py::process_started [2, 3, 4, 10] through lineage.claim."""

    def held(self, name: str) -> pathlib.Path:
        pred = self.run_dir(name)
        who = {"host": socket.gethostname(), "pid": 4242, "started": LSTART}
        put(pred / lineage.CLAIM, {"run": str(self.root / "never-began"), "claimed": 1.0, "claimant": who})
        return pred

    def test_the_claimant_of_a_table_that_cannot_be_read_is_not_displaced(self):
        for exc in ProcessTableAnswers.FAILURES:
            with self.subTest(type(exc).__name__):
                pred = self.held("pred-" + type(exc).__name__)
                with failing_ps(exc), self.assertRaises(lineage.LineageRefused) as c:
                    lineage.claim(pred, self.root / "second", 2.0)
                self.assertIn("cannot be shown gone", str(c.exception))
                self.assertEqual([n for n, _ in lineage.claims(pred)], [1])

    def test_the_same_claim_is_superseded_when_the_table_says_no_such_process(self):
        pred = self.held("pred")
        with mock.patch.object(lineage.subprocess, "run", fake_ps({})):
            doc = lineage.claim(pred, self.root / "second", 2.0)
        self.assertIs(doc["supersedes"]["claimant_gone"], True)
        self.assertEqual([n for n, _ in lineage.claims(pred)], [1, 2])


class LocalisedProcessStart(unittest.TestCase):
    """`ps` prints a localised `lstart` on some hosts, bytes that are not UTF-8: the start text is still read (the
    undecodable bytes replaced), identical on two calls, so a live claimant is recognised as the one that claimed.

    Pins aisef2/app/lineage.py::process_started [17]."""

    def test_a_start_text_that_is_not_utf8_is_read_and_comparable(self):
        code = "import sys; sys.stdout.buffer.write(b'Thu \\xe9\\xff 1 00:00:00 1970\\n')"

        def ps(argv, **kw):
            return REAL_RUN([sys.executable, "-c", code], **kw)

        with mock.patch.object(lineage.subprocess, "run", ps):
            first, again = lineage.process_started(4242), lineage.process_started(4242)
            me = lineage.claimant()
            gone = lineage._gone(me)
        self.assertIsInstance(first, str)
        self.assertTrue(first)
        self.assertEqual(first, again)
        self.assertEqual(me["started"], first)
        self.assertIs(gone, False)


class AnchorFileOfAnyBytes(Dirs):
    """An evidence-anchor file is exactly one 64-hex line and a newline; anything else is refused with ValueError
    (the class an operator's script catches), however foreign its bytes — invalid bytes, a UTF-8 BOM before a valid
    anchor, a valid anchor in UTF-16 — and the refusal names the file. Pins aisef2/app/lineage.py::read_anchor [4]."""

    ANCHOR = "0123456789abcdef" * 4

    def test_foreign_bytes_are_a_value_error_naming_the_file(self):
        cases = ((b"\xff" * 64 + b"\n"), (b"\xef\xbb\xbf" + self.ANCHOR.encode("ascii") + b"\n"),
                 (self.ANCHOR + "\n").encode("utf-16"))
        for n, raw in enumerate(cases):
            with self.subTest(n):
                p = self.root / f"foreign-{n}.anchor"
                p.write_bytes(raw)
                with self.assertRaises(ValueError) as c:
                    lineage.read_anchor(p)
                self.assertIn(str(p), str(c.exception))

    def test_the_anchor_written_is_read_back(self):
        p = self.root / "good.anchor"
        lineage.write_anchor(p, self.ANCHOR)
        self.assertEqual(lineage.read_anchor(p), self.ANCHOR)


if __name__ == "__main__":
    unittest.main()
