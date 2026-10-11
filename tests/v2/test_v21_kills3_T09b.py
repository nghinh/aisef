"""V2.1 (kills3 T09b): survivors of campaign 2 in aisef2/app/lineage.py — `claim`, `claims`, `continued_by`,
`lineage_account`: the decisions that name which run a lineage continues from, why a claim is refused, what a superseded
claim records and what the lineage has spent.

Every case runs on hand-built run directories (a claim file, a RUN.json, a journal holding its first event, a preflight
ledger): no run, no driver, no client, no network. The kill files of these targets drive real killed runs, whose claims
are whole and name runs that exist: a generation after the first is written by the run that ends a test and never read
back, and neither a claim that cannot be read, nor the order of generations, nor the identifiers of a refusal is
exercised.

Requirements pinned (each class says which mutants):

* a predecessor's claim generations are `CONTINUED-BY.json` and `CONTINUED-BY.<n>.json`, n >= 2, in numeric order —
  nothing else in the directory is one — and the lineage continues from the NEWEST (`claims`, read by `claim`,
  `continued_by`);
* a refused claim names, as separate identifiers, the predecessor, the run holding the claim, the claim file, the reason
  class (alive / cannot be shown gone) and the sha256 that `--supersede-claim` takes (`claim`);
* the record of a superseded claim names which child was superseded, on what evidence and whether the operator's
  assertion was what permitted it (`claim`);
* a claim that cannot be read is answered with a marker, never with an exception or a missing answer (`continued_by`,
  `lineage_account`);
* the spend of a superseded child, whose preflight may have spent, is part of the lineage, once, flagged superseded
  (`lineage_account`)."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import socket
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import lineage  # noqa: E402
from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal import format3  # noqa: E402


def delimited(text: str, ident: str) -> bool:
    """`ident` stands in `text` as an identifier of its own: after the start, a space, one of `(,:` or the end of a
    directory part (`/`, `\\`: a claim file given with its directory is still the claim file), and before the end, a
    space or one of `),:` — never run together with a neighbouring word or path."""
    return re.search(r"(?:^|[\s(,:/\\])" + re.escape(ident) + r"(?=$|[\s),:])", text) is not None


class Lineages(unittest.TestCase):
    """Fixtures (no test of its own): run directories as a run leaves them, and claims as a claimant writes them."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()

    def run_dir(self, name: str, *, begun: bool = False, recorded: bool = False, requests: int = 0,
                continues: pathlib.Path | None = None) -> pathlib.Path:
        """`begun`: its journal holds its first event; `recorded`: it ended with a RUN.json; `requests`: provider
        requests its preflight sent and had answered; `continues`: the predecessor its RUN.started.json names."""
        d = self.tmp / name
        d.mkdir()
        if begun:
            journal = d / lineage.JOURNAL
            journal.parent.mkdir(parents=True)
            w = format3.JournalWriter3(journal, clock=lambda: 0.0)
            w.append(T.RUN_BEGIN, {"journal_format": format3.FORMAT, "run_id": name})
            w.close()
        if recorded:
            (d / "RUN.json").write_text("{}\n", encoding="utf-8")
        if requests:
            ledger = d / "preflight" / "LEDGER.jsonl"
            ledger.parent.mkdir(parents=True)
            rows = [r for n in range(1, requests + 1)
                    for r in ({"n": n, "event": "sent"}, {"n": n, "event": "done", "input_tokens": 5, "output_tokens": 1})]
            ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        if continues is not None:
            (d / lineage.STARTED).write_text(json.dumps({"continues": {"path": str(continues)}}), encoding="utf-8")
        return d

    def claim_file(self, pred: pathlib.Path, generation: int, run: pathlib.Path | str,
                   who: dict | None = None) -> tuple[pathlib.Path, bytes]:
        path = pred / (lineage.CLAIM if generation == 1 else f"CONTINUED-BY.{generation}.json")
        who = who or {"host": "no-such-host.invalid", "pid": 1, "started": "t0"}
        path.write_text(json.dumps({"run": str(run), "claimed": 1.0, "claimant": who}, sort_keys=True) + "\n",
                        encoding="utf-8")
        return path, path.read_bytes()

    def assert_identified(self, text: str, *idents: str) -> None:
        for ident in idents:
            self.assertTrue(delimited(text, ident), f"{ident!r} is not an identifier of its own in {text!r}")


ALIVE = {"host": socket.gethostname(), "pid": 1, "started": "t0"}      # with process_started patched to answer "t0"


class ClaimGenerations(Lineages):
    """`claims`: the generations of a predecessor's claims are CONTINUED-BY.json and CONTINUED-BY.<n>.json for n >= 2,
    oldest first by n. A file that merely looks like one (a copy `.1`, `.0`, a `.x`, a `.2.3`) is not a generation: a
    reader that took it for one would reconcile a claim nobody made, or fail on it.

    Pins aisef2/app/lineage.py::claims [2, 5, 8, 9] (which names are generations) and [3] (their order)."""

    def build(self) -> tuple[pathlib.Path, list]:
        pred = self.run_dir("P")
        wanted = [(1, self.claim_file(pred, 1, "c1")[0])]
        wanted += [(n, self.claim_file(pred, n, f"c{n}")[0]) for n in (10, 3, 2)]
        for look_alike in ("CONTINUED-BY.1.json", "CONTINUED-BY.0.json", "CONTINUED-BY.x.json", "CONTINUED-BY.2.3.json"):
            (pred / look_alike).write_text(json.dumps({"run": "not-a-generation"}) + "\n", encoding="utf-8")
        return pred, sorted(wanted)

    def test_the_generations_are_the_first_claim_and_the_files_numbered_from_two(self):
        pred, wanted = self.build()
        self.assertEqual([n for n, _ in wanted], [1, 2, 3, 10])
        self.assertEqual(lineage.claims(pred), wanted)

    def test_they_are_in_numeric_order_whatever_order_the_directory_lists_them_in(self):
        pred, wanted = self.build()
        real = pathlib.Path.glob

        def descending(self, pattern, **kw):        # by name, descending: '.3', '.2', '.10' — not numeric either way
            return iter(sorted(real(self, pattern, **kw), reverse=True))
        with mock.patch.object(pathlib.Path, "glob", descending):
            got = lineage.claims(pred)
        self.assertEqual(got, wanted)

    def test_a_lineage_continued_past_a_superseded_claim_continues_from_the_newest_generation(self):
        """What the generations are for: claim 1 was superseded (its child ended unbegun), claim 2's child began. The
        lineage continues from that child — `continued_by` names it, and no run may claim past it. Pins the readers
        of `claims` [2, 8, 9]."""
        pred = self.run_dir("P")
        refused = self.run_dir("refused", recorded=True)
        began = self.run_dir("began", begun=True)
        self.claim_file(pred, 1, refused)
        self.claim_file(pred, 2, began)
        self.assertEqual(lineage.continued_by(pred), (str(began), lineage.BEGUN))
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(pred, self.tmp / "next", 3.0)
        self.assertIn("which began", str(c.exception))
        self.assert_identified(str(c.exception), str(began))
        self.assertEqual(sorted(p.name for p in pred.iterdir()), ["CONTINUED-BY.2.json", lineage.CLAIM])  # none added


class ClaimRefusalText(Lineages):
    """`claim` refuses a claim it may not supersede without evidence. The operator reads the refusal to decide what to
    do: which run holds the claim of which predecessor (and which file), why the claimant is not shown gone — alive (wait
    for it, or stop it) or not decidable (check the other host) — and the one command that supersedes it. Identifiers
    stand apart so the operator can lift each of them; the connecting words are not the contract.

    Pins aisef2/app/lineage.py::claim [31, 44, 45, 46, 56] (the reason) and [57, 58, 59] (identifiers apart)."""

    def refuse(self, who: dict, name: str, shown):
        """`shown`: what the claimant's evidence showed — False (alive) or None (cannot be shown gone)."""
        pred = self.run_dir(f"P-{name}")
        held = self.tmp / f"held-{name}"                 # no record, no journal: it has not begun
        path, data = self.claim_file(pred, 1, held, who)
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(pred, self.tmp / f"new-{name}", 1.0)
        text = str(c.exception)
        self.assert_identified(text, str(pred), str(held), lineage.CLAIM)
        # the way forward: the command's argument is the claim's sha256, and naming it supersedes the claim
        named = re.search(r"--supersede-claim\s+([0-9a-f]{64})(?![0-9a-f])", text)
        self.assertIsNotNone(named, text)
        self.assertEqual(named[1], hashlib.sha256(data).hexdigest())
        again = lineage.claim(pred, self.tmp / f"new-{name}", 2.0, supersede=named[1])
        self.assertEqual((again["supersedes"]["sha256"], again["supersedes"]["operator_asserted"]), (named[1], True))
        self.assertIs(again["supersedes"]["claimant_gone"], shown)      # the two reasons are two values, not one
        return text.replace(str(pred), "").replace(str(held), "")       # what is left says the reason

    def test_a_claimant_that_is_alive_is_refused_as_alive(self):
        with mock.patch.object(lineage, "process_started", return_value="t0"):      # the pid shows the same start time
            reason = self.refuse(ALIVE, "alive", False)
        self.assertIn("alive", reason)
        self.assertNotIn("cannot be shown gone", reason)

    def test_a_claimant_on_another_host_is_refused_as_not_decidable(self):
        reason = self.refuse({"host": "another-host.invalid", "pid": 1, "started": "t0"}, "elsewhere", None)
        self.assertIn("cannot be shown gone", reason)
        self.assertNotIn("alive", reason)


class ClaimLostRace(Lineages):
    """The run that loses the exclusive create — another run took the claim between this one's look and its create — is
    refused and writes nothing: its detail (`rec['failure']['detail']`, printed by `aisef run`) names the predecessor
    and the claim file that was taken, each as an identifier of its own, and says a run is continued once.

    Pins aisef2/app/lineage.py::claim [64]."""

    def test_the_loser_is_told_which_predecessor_and_which_claim_file(self):
        pred = self.run_dir("P")
        first_claim, _ = self.claim_file(pred, 1, "winner")
        for first in (True, False):
            with self.subTest("first generation" if first else "a superseding generation"):
                if first:
                    taken, looked = first_claim, []        # it looked before the winner created the file
                else:      # claim 1's child ended unbegun: superseded by evidence; its generation 2 was taken meanwhile
                    self.run_dir("refused", recorded=True)
                    self.claim_file(pred, 1, self.tmp / "refused")
                    taken, _ = self.claim_file(pred, 2, "winner-2")
                    looked = [(1, pred / lineage.CLAIM)]
                before = {p.name: p.read_bytes() for p in pred.iterdir()}
                with mock.patch.object(lineage, "claims", return_value=looked):
                    with self.assertRaises(lineage.LineageRefused) as c:
                        lineage.claim(pred, self.tmp / "loser", 1.0)
                self.assert_identified(str(c.exception), str(pred), taken.name)
                self.assertIn("a run is continued once", str(c.exception))
                self.assertEqual({p.name: p.read_bytes() for p in pred.iterdir()}, before)     # nothing written


class SupersedeRecord(Lineages):
    """What a superseding claim records about the claim it replaces — the record `aisef verify` and the operator read
    in `continues.claim.supersedes`: the claim file, its sha256, WHICH child was superseded and in which state, whether
    the claimant was shown gone, and whether the operator's assertion was what permitted it. An assertion made while the
    evidence already sufficed was not what permitted it: it is not recorded as the authority.

    Pins aisef2/app/lineage.py::claim [17, 34] (the child) and [38] (the assertion)."""

    def superseded(self, name: str, who: dict | None = None, assert_it: bool = False):
        pred = self.run_dir(f"P-{name}")
        held = self.run_dir(f"held-{name}", recorded=True)    # a record and no journal: ended before it began
        path, data = self.claim_file(pred, 1, held, who)
        sha = hashlib.sha256(data).hexdigest()
        new = self.tmp / f"new-{name}"
        doc = lineage.claim(pred, new, 2.0, supersede=sha if assert_it else None)
        written = json.loads((pred / "CONTINUED-BY.2.json").read_text(encoding="utf-8"))
        self.assertEqual((doc, written["run"], written["claimed"]), (written, str(new), 2.0))
        self.assertEqual(path.read_bytes(), data)                   # kept
        return doc["supersedes"], held, sha

    def test_the_record_names_the_superseded_child_and_the_evidence(self):
        sup, held, sha = self.superseded("evidence")
        self.assertEqual(sup, {"claim": lineage.CLAIM, "sha256": sha, "child": str(held),
                               "child_state": lineage.ENDED_UNBEGUN, "claimant_gone": True, "operator_asserted": False})

    def test_an_assertion_made_when_the_evidence_sufficed_is_not_recorded_as_the_authority(self):
        sup, held, _ = self.superseded("both", assert_it=True)
        self.assertEqual((sup["child"], sup["claimant_gone"], sup["operator_asserted"]), (str(held), True, False))

    def test_an_assertion_that_was_the_only_ground_is_recorded_as_such(self):
        with mock.patch.object(lineage, "process_started", return_value="t0"):     # alive: no evidence of its own
            pred = self.run_dir("P-alive")
            held = self.tmp / "held-alive"
            _, data = self.claim_file(pred, 1, held, ALIVE)
            sha = hashlib.sha256(data).hexdigest()
            with self.assertRaises(lineage.LineageRefused):
                lineage.claim(pred, self.tmp / "new-alive", 2.0)
            sup = lineage.claim(pred, self.tmp / "new-alive", 2.0, supersede=sha)["supersedes"]
        self.assertEqual((sup["child"], sup["child_state"], sup["claimant_gone"], sup["operator_asserted"]),
                         (str(held), lineage.UNBEGUN, False, True))


class ContinuedByUnreadableClaim(Lineages):
    """`continued_by` of a predecessor whose newest claim cannot be read — a claimant killed between creating the file
    and writing it leaves 0 bytes; a directory or a locked file cannot be opened — answers with a marker run and no
    state, never an exception and never nothing: `aisef bundle continue` unpacks the pair, reports the marker as
    `already_continued_by` (only a non-empty run is reported, so an empty marker would report "never continued" for a
    run that has a claim) and carries on; `aisef run --parent` is then refused by `claim` until the operator names it.

    Pins aisef2/app/lineage.py::continued_by [8] (OSError), [9] (ValueError), [10, 13, 14] (the shape of the answer)
    and [15] (a marker that is not empty)."""

    CASES = (("a claim of 0 bytes", lambda p: p.write_bytes(b"")),
             ("a claim that is not JSON", lambda p: p.write_text('{"run": "', encoding="utf-8")),
             ("a directory in its place", lambda p: p.mkdir()))

    def test_an_unreadable_newest_claim_is_a_marker_and_no_state(self):
        for name, make in self.CASES:
            with self.subTest(name):
                pred = self.run_dir("P-" + re.sub(r"\W", "", name))
                make(pred / lineage.CLAIM)
                got = lineage.continued_by(pred)
                self.assertIsInstance(got, tuple)
                self.assertEqual(len(got), 2, got)
                marker, state = got
                self.assertIsNone(state)
                self.assertIsInstance(marker, str)
                self.assertTrue(marker)
                self.assertIn("unreadable", marker)

    def test_it_is_the_newest_claim_that_is_read_and_a_run_never_claimed_has_none(self):
        """An unreadable newest claim is not passed over for an older one that reads (it would say `continued by
        <began>`); and "never claimed" stays the answer `(None, None)`, apart from the marker."""
        pred = self.run_dir("P")
        began = self.run_dir("began", begun=True)
        self.claim_file(pred, 1, began)                       # readable, but generation 2 is the newest
        (pred / "CONTINUED-BY.2.json").write_bytes(b"")
        marker, state = lineage.continued_by(pred)
        self.assertIsNone(state)
        self.assertIn("unreadable", marker)
        self.assertEqual(lineage.continued_by(self.run_dir("never-claimed")), (None, None))


class LineageAccountOfSupersededChildren(Lineages):
    """`lineage_account` sums every run of the lineage once and every child a superseded claim names (its preflight may
    have spent), flagged `superseded`, wherever the claims are: on the predecessor itself (the siblings of the run
    asking) or on an earlier run of the chain. A claim file that cannot be read (0 bytes after a kill, garbage, a
    directory) names no run and does not stop the account: the claims after it are still read (a superseded claim
    after a torn one — the operator named the torn one — names a child whose preflight may have spent).

    Pins aisef2/app/lineage.py::lineage_account [34, 36, 39, 40] (the predecessor's own claims) and [28, 29]
    (unreadable ones there), [31, 32] (unreadable ones on an earlier run of the chain)."""

    def claims_with_torn_ones(self, holder: pathlib.Path, dead: pathlib.Path, later: pathlib.Path,
                              last: pathlib.Path) -> None:
        """Six generations: `dead`, three that cannot be read, `later` (readable, AFTER the torn ones), `last`."""
        self.claim_file(holder, 1, dead)
        (holder / "CONTINUED-BY.2.json").write_bytes(b"")                         # killed between create and write
        (holder / "CONTINUED-BY.3.json").write_text("{not json\n", encoding="utf-8")
        (holder / "CONTINUED-BY.4.json").mkdir()                                  # cannot be read as a file
        self.claim_file(holder, 5, later)
        self.claim_file(holder, 6, last)

    def test_the_superseded_children_of_the_predecessor_are_in_the_lineage_once(self):
        pred = self.run_dir("P", recorded=True, requests=1)
        dead = self.run_dir("D", recorded=True, requests=2)     # refused after its preflight, superseded by evidence
        later = self.run_dir("D2", recorded=True, requests=1)
        asking = self.tmp / "C"
        self.claims_with_torn_ones(pred, dead, later, asking)
        got = lineage.lineage_account(pred, asking)
        self.assertEqual([(pathlib.Path(r["run"]).name, bool(r.get("superseded"))) for r in got["runs"]],
                         [("P", False), ("D", True), ("D2", True)])
        self.assertEqual([r["provider_requests"] for r in got["runs"]], [1, 2, 1])
        self.assertEqual((got["provider_requests"], got["input_tokens"], got["output_tokens"]), (4, 20, 4))

    def test_the_superseded_children_of_an_earlier_run_of_the_chain_are_in_the_lineage_once(self):
        a = self.run_dir("A", recorded=True)
        dead = self.run_dir("D", recorded=True, requests=2)
        later = self.run_dir("D2", recorded=True, requests=1)
        b = self.run_dir("B", recorded=True, continues=a)       # B continued A; D, D2 were A's superseded attempts
        asking = self.tmp / "C"
        self.claims_with_torn_ones(a, dead, later, b)
        got = lineage.lineage_account(b, asking)
        self.assertEqual([(pathlib.Path(r["run"]).name, bool(r.get("superseded"))) for r in got["runs"]],
                         [("B", False), ("D", True), ("D2", True), ("A", False)])
        self.assertEqual(got["provider_requests"], 3)

    def test_the_report_of_which_runs_were_replaced_flags_the_superseded_ones(self):
        """The reader of the flag: `lineage_usage.runs[*].superseded` of the continuation's record."""
        pred = self.run_dir("P", recorded=True)
        dead = self.run_dir("D", recorded=True, requests=2)
        later = self.run_dir("D2", recorded=True, requests=1)
        asking = self.tmp / "C"
        self.claims_with_torn_ones(pred, dead, later, asking)
        report = lineage.usage_lineage(pred, asking, {"tokens": {}, "cost": {}}, None)
        self.assertEqual([(pathlib.Path(r["run"]).name, r["superseded"]) for r in report["runs"]],
                         [("P", False), ("D", True), ("D2", True), ("this run", False)])


if __name__ == "__main__":
    unittest.main()
