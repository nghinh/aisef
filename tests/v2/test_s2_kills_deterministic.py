"""V2.0-S2 mutation: deterministic kill cases for preflight.fingerprint_fields and client.Budget.spend (owner, 2026-10-05:
'A release qualification must not knowingly depend on random ordering/chance'). Each case kills every mutant of its
target on its own, whatever the process's string-hash seed, with no clock, no randomness and no machine state:

* fingerprint_fields: the probes' model names and fingerprints are str values whose hashes the case fixes, so the set
  the function builds iterates in one known order, never name order — without sorted() the result differs every time.
* Budget.spend: the logs directory is an in-memory listing in a fixed order that is not name order, and each session's
  reading is given, not read from disk.

A file of its own, named only in those two targets' kill sets (first, so each mutant's kill comes from here), so every
other S2 result keeps a byte-identical kill-test closure (validation/qualification/s2_mutation_record.py)."""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from aisef2.app import client, preflight  # noqa: E402


class Fixed(str):
    """A str whose hash the case fixes: in a set of at most four of them with distinct hashes 1-7 each one sits in the
    slot its hash names, so the set iterates in hash order (CPython), whatever PYTHONHASHSEED is."""

    def __new__(cls, value: str, h: int) -> "Fixed":
        s = super().__new__(cls, value)
        s.h = h
        return s

    def __hash__(self) -> int:
        return self.h


def reverse_named(*names: str) -> list[Fixed]:
    """The names, hashed so that their set iterates in reverse name order."""
    ordered = sorted(names)
    return [Fixed(n, len(ordered) - ordered.index(n)) for n in names]


class FingerprintFields(unittest.TestCase):
    """aisef2.app.preflight.fingerprint_fields L115-L117: every bound field under its own name, the served models and the
    fingerprints each in name order, once each."""

    def test_the_bound_fields_in_name_order_whatever_the_set_order(self):
        served = reverse_named("model-a", "model-b", "model-c")
        prints = reverse_named("fp-a", "fp-b", "fp-c")
        for names in (served, prints):   # the premise, checked: the set's own order is not name order
            self.assertNotEqual(list(set(names)), sorted(names))
        probes = [{"served_model": served[i % 3], "system_fingerprint": prints[(i + 1) % 3]} for i in range(5)]
        obs = {"declared_model": "declared", "listing": {"id": "listed", "owned_by": "owner"}, "probes": probes}
        self.assertEqual(preflight.fingerprint_fields(obs),
                         {"declared_model": "declared", "listed_id": "listed", "owned_by": "owner",
                          "served_models": ["model-a", "model-b", "model-c"], "system_fingerprint": ["fp-a", "fp-b", "fp-c"]})


class Listing:
    """A logs directory, in memory: it holds the given session logs and lists them for '*.jsonl' in the given order."""

    def __init__(self, names: tuple[str, ...], exists: bool = True) -> None:
        self.paths, self.exists = [pathlib.PurePosixPath("logs", n) for n in names], exists

    def is_dir(self) -> bool:
        return self.exists

    def glob(self, pattern: str) -> list[pathlib.PurePosixPath]:
        return list(self.paths) if pattern == "*.jsonl" else []


def reading(turns: int, tokens_in: int, tokens_out: int, blind: int) -> dict:
    return {"error": None, "text": "", "turns": turns, "tokens": {"input": tokens_in, "output": tokens_out},
            "steps_without_tokens": blind}


#: what client.read_session would say of each log
READINGS = {"a.jsonl": reading(0, 0, 0, 0),      # started, finished no step, not the live one: unaccounted
            "b.jsonl": reading(2, 5, 7, 1),      # one finished step without a token report: unaccounted
            "c.jsonl": reading(0, 13, 17, 0)}    # the live session: no step yet is not unaccounted


class BudgetSpend(unittest.TestCase):
    """aisef2.app.client.Budget.spend L74-L87: the logs '*.jsonl' of an existing directory, read in name order; a count
    of sessions above the recorded requests, steps without a token report, and a finished non-live session with no step
    are each named; the four sums add the base."""

    LIMITS = {"provider_requests": 9, "turns": 99, "input_tokens": 999, "output_tokens": 9999}
    BASE = {"provider_requests": 1, "turns": 20, "input_tokens": 300, "output_tokens": 4000}

    def spend(self, listing: Listing, recorded: int, live: str | None) -> dict:
        b = client.Budget(self.LIMITS, self.BASE, listing, lambda: recorded)
        with mock.patch.object(client, "read_session", lambda p: READINGS[p.name]):
            return b.spend(pathlib.PurePosixPath("logs", live) if live else None)

    def test_more_sessions_than_requests_and_each_unaccounted_session_named_in_name_order(self):
        self.assertEqual(self.spend(Listing(("c.jsonl", "b.jsonl", "a.jsonl")), 1, "c.jsonl"),
                         {"provider_requests": 2, "turns": 22, "input_tokens": 318, "output_tokens": 4024,
                          "sessions_started": 3, "requests_recorded": 1,
                          "unaccounted": ["3 sessions were started but 1 provider requests are recorded",
                                          "a.jsonl: a session that started finished no step — what it sent is unknown",
                                          "b.jsonl: 1 finished steps report no tokens"]})

    def test_as_many_requests_as_sessions_and_a_live_session_without_a_step(self):
        self.assertEqual(self.spend(Listing(("c.jsonl", "b.jsonl")), 2, "c.jsonl"),
                         {"provider_requests": 3, "turns": 22, "input_tokens": 318, "output_tokens": 4024,
                          "sessions_started": 2, "requests_recorded": 2,
                          "unaccounted": ["b.jsonl: 1 finished steps report no tokens"]})

    def test_no_directory_no_sessions(self):
        self.assertEqual(self.spend(Listing(("c.jsonl",), exists=False), 0, None),
                         {"provider_requests": 1, "turns": 20, "input_tokens": 300, "output_tokens": 4000,
                          "sessions_started": 0, "requests_recorded": 0, "unaccounted": []})


if __name__ == "__main__":
    unittest.main()
