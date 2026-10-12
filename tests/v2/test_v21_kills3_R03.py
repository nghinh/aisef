"""V2.1 (kills3 R03): survivors of campaign 3 in aisef2/app/lineage.py — the two words an operator reads in what the
lineage readers say about a file they cannot read: the refusal of `claim` for a claim that cannot be read, and the entry
`account_of` lists for a session stream that does not read.

Both texts reach the operator. `claim`'s is the detail of the refusal `aisef run --parent` prints and records
(`rec["failure"]["detail"]`, run.py `RunRefused(str(e))`); `account_of`'s entry is what `--accept-unaccounted` makes the
operator accept (`rec["continues"]["accepted_unaccounted"]`, the refusal's list, `aisef bundle continue`'s
`unaccounted`). The runs here are hand-built directories: no run, no client, no network.

Requirements pinned:

* a claim that cannot be read is refused, and the refusal names — each as an identifier of its own, never run together
  with a neighbour — the predecessor, the claim file (the NEWEST generation's own name: the one that cannot be read, not
  the first generation's) and the OS error's class, and says which kind of refusal it is: the claim is not superseded
  without evidence (the module docstring's own name for it, and the sibling refusal of `claim` says the same:
  test_v21_continue_integrity / test_v21_kills3_T09a assert it);
* a session stream the reader refuses is listed as unknown spend, naming the run and the failing reader's exception
  class, and saying that what the sessions spent is unknown: the account's own figures leave the stream's turns and
  tokens out, so a 0 there is not a measurement and this entry is the only place that says so.

What is not pinned: the closing parenthesis, the connecting words, the order of the clauses."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import client, lineage  # noqa: E402


def delimited(text: str, ident: str) -> bool:
    """`ident` stands in `text` as an identifier of its own: after the start, a space, one of `(,:` or the end of a
    directory part (`/`, `\\`), and before the end, a space or one of `),:` — never run together with a neighbouring
    word or path."""
    return re.search(r"(?:^|[\s(,:/\\])" + re.escape(ident) + r"(?=$|[\s),:])", text) is not None


class Scratch(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()

    def assert_identified(self, text: str, *idents: str) -> None:
        for ident in idents:
            self.assertTrue(delimited(text, ident), f"{ident!r} is not an identifier of its own in {text!r}")


class UnreadableClaimRefusal(Scratch):
    """`claim` of a predecessor whose claim file cannot be read refuses: with no content there is no child to
    reconcile and no digest to name, so only evidence could supersede it and none can be had. The operator reads which
    predecessor, which claim file (the one that cannot be read: the newest generation's), why it could not be read (the
    OS error's class: a directory in its place, a file closed to its user) and that the claim stands.

    Pins aisef2/app/lineage.py::claim [68, 69] (the identifiers stand apart) and [70] (the claim is not superseded
    without evidence)."""

    def refusal(self, name: str, make, generation: int = 1) -> tuple[pathlib.Path, str, str, str]:
        """(the predecessor, the name of the claim file that cannot be read, what reading it raises, the refusal's
        text). `make` puts the unreadable claim there: generation `generation`, after claims that do read."""
        pred = self.tmp / f"pred-{name}"
        pred.mkdir()
        files = [lineage.CLAIM] + [f"CONTINUED-BY.{n}.json" for n in range(2, generation + 1)]
        for n, earlier in enumerate(files[:-1], 1):         # the generations before it: claims that read
            (pred / earlier).write_text(json.dumps({"run": str(self.tmp / f"ended-{name}-{n}")}) + "\n", encoding="utf-8")
        unreadable = files[-1]
        make(pred / unreadable)
        try:
            (pred / unreadable).read_bytes()
        except OSError as e:
            cause = type(e).__name__
        else:
            self.fail("the fixture is a claim that can be read")
        before = {p.name for p in pred.iterdir()}
        with self.assertRaises(lineage.LineageRefused) as c:       # not an OSError out of `aisef run --parent`
            lineage.claim(pred, self.tmp / f"next-{name}", 1.0)
        self.assertEqual({p.name for p in pred.iterdir()}, before)        # nothing was claimed or superseded
        return pred, unreadable, cause, str(c.exception)

    def check(self, name: str, make, generation: int = 1) -> None:
        pred, unreadable, cause, text = self.refusal(name, make, generation)
        self.assert_identified(text, str(pred), unreadable, cause)    # which predecessor, which file, why
        self.assertIn("not superseded without evidence", text)        # and what the refusal means for the claim

    def test_a_directory_where_the_claim_is(self):
        self.check("directory", lambda p: p.mkdir())

    def test_it_is_the_newest_generation_that_is_named(self):
        """Generation 1 reads; generation 2 is the claim that does not: the refusal names `CONTINUED-BY.2.json`, the
        file the operator has to look at, not the first generation's `CONTINUED-BY.json`."""
        self.check("second", lambda p: p.mkdir(), generation=2)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                         "a file closed to its owner is unreadable only to a user that is not root, on POSIX")
    def test_a_claim_closed_to_its_user(self):
        def closed(p: pathlib.Path) -> None:
            p.write_text(json.dumps({"run": str(self.tmp / "gone")}) + "\n", encoding="utf-8")
            p.chmod(0)
            self.addCleanup(p.chmod, 0o644)
        self.check("closed", closed)


class UnreadableSessionStream(Scratch):
    """`account_of` of a run with a session stream the reader refuses — a step whose part is a list, a stream that is
    a directory — lists it as unknown spend, never as a 0 shown as known: the entry names the run, the exception class
    the reader raised (as an identifier of its own) and says that what the sessions spent is unknown. The account's
    figures leave the stream out (its turns stay 0), so the entry is what tells the operator the 0 is no measurement.

    Pins aisef2/app/lineage.py::account_of [54]."""

    def entry(self, name: str, make) -> tuple[pathlib.Path, str, dict]:
        """(the run, the exception class the reader raises on its stream, the account)."""
        run = self.tmp / name
        stream = run / "sessions" / "S1.developer.1.jsonl"
        stream.parent.mkdir(parents=True)
        make(stream)
        try:
            client.read_session(stream)
        except Exception as e:  # noqa: BLE001 — whatever the reader refuses with is the cause class the entry names
            cause = type(e).__name__
        else:
            self.fail("the fixture is a stream that reads")
        return run, cause, lineage.account_of(run)

    def check(self, name: str, make) -> None:
        run, cause, acct = self.entry(name, make)
        self.assertEqual(len(acct["unaccounted"]), 1, acct["unaccounted"])
        entry = acct["unaccounted"][0]
        self.assert_identified(entry, run.name, cause)               # which run, why the stream did not read
        self.assertTrue(delimited(entry, "unknown"), entry)          # what that makes of the sessions' spend
        self.assertEqual(acct["turns"], 0)                           # ... and the figure it qualifies is left out

    def test_a_step_whose_part_is_a_list(self):
        self.check("list", lambda p: p.write_text('{"type": "step_finish", "part": [1]}\n', encoding="utf-8"))

    def test_a_stream_that_cannot_be_opened_as_a_file(self):
        self.check("directory", lambda p: p.mkdir())


if __name__ == "__main__":
    unittest.main()
