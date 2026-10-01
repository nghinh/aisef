"""WP-3.2 — the committed format-compatibility fixtures, built deterministically (run this module to rewrite them).

Each fixture is a journal a real writer could leave: stored lines with valid chain links, so what a reader refuses
it refuses for the reason named here, never for a broken link. "Old" is journal format 1; "new" is what a format-2
writer might add: a required type, an ignorable type, a new field on a known type, or a second format declaration.

    python -P tests/v2/p3/journal_fixtures.py        # rewrite tests/v2/fixtures/journal/*.jsonl
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.journal.event import GENESIS, Event, encode, link  # noqa: E402

DIR = ROOT / "tests" / "v2" / "fixtures" / "journal"
SHA = "c" * 40
RUN = ("run/begin", {"journal_format": 1, "run_id": "fixture"})
BEGIN = ("story/begin", {"story_id": "S1", "parent": SHA})
FAIL = ("failure/observed", {"story_id": "S1", "code": "PROBE_UNRUNNABLE", "owner": "ENVIRONMENT", "retryable": True,
                             "detail": "interpreter absent"})
PROGRESS = ("report/progress", {"done": 1, "of": 3}, True)       # a new ignorable type
CHECKPOINT = ("story/checkpoint", {"story_id": "S1"})            # a new required type
RETRY = ("story/retry", {"story_id": "S1"}, False, (2,))


def lines(*specs) -> str:
    """Stored lines for (type, data[, ignorable[, source_seqs]]) specs, seq == index, chained from GENESIS."""
    out, prev = [], GENESIS
    for n, spec in enumerate(specs):
        type_, data, ignorable, cites = (*spec, *(False, ())[len(spec) - 2:])
        event = Event(n, type_, data, float(n), ignorable, cites)
        prev = link(prev, event)
        out.append(encode(event, prev))
    return "".join(out)


#: name -> (text, expectation): "OK" (with the seqs skipped) or the reason the reader refuses.
FIXTURES = {
    "known_log": (lines(RUN, BEGIN, FAIL, RETRY), ("OK", ())),
    "unknown_required": (lines(RUN, BEGIN, CHECKPOINT, FAIL), ("REFUSE", "unknown event type 'story/checkpoint' is "
                                                                       "not marked ignorable")),
    "unknown_ignorable": (lines(RUN, BEGIN, PROGRESS, FAIL, ("story/retry", {"story_id": "S1"}, False, (3,))),
                          ("OK", (2,))),
    "malformed_known": (lines(RUN, ("story/begin", {"story_id": "S1", "parent": SHA[:12]})),
                        ("REFUSE", "story/begin: fields of the wrong kind or enum ['parent']")),
    "version_mismatch": (lines(("run/begin", {"journal_format": 2, "run_id": "fixture"}), BEGIN),
                         ("REFUSE", "journal format 2 is not format 1")),
    "newer_schema_field": (lines(RUN, ("story/begin", {"story_id": "S1", "parent": SHA, "attempt": 2})),
                           ("REFUSE", "not in the schema ['attempt']")),
    "mixed_stream_second_declaration": (lines(RUN, BEGIN, ("run/begin", {"journal_format": 2, "run_id": "fixture"}),
                                              CHECKPOINT),
                                        ("REFUSE", "a journal begins with run/begin, and only once")),
    "mixed_stream_new_required": (lines(RUN, BEGIN, FAIL, PROGRESS, CHECKPOINT, RETRY),
                                  ("REFUSE", "unknown event type 'story/checkpoint' is not marked ignorable")),
    "mixed_stream_new_ignorable": (lines(RUN, PROGRESS, BEGIN, PROGRESS, FAIL, ("story/retry", {"story_id": "S1"},
                                                                                 False, (4,))),
                                   ("OK", (1, 3))),
    "known_type_marked_ignorable": (lines(RUN, BEGIN, (*FAIL, True)),
                                    ("REFUSE", "failure/observed is a required event in format 1; it is never "
                                               "ignorable")),
    "torn_tail": (lines(RUN, BEGIN, FAIL)[:-40], ("OK_TORN", ())),
}


def write() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    for name, (text, _) in FIXTURES.items():
        (DIR / f"{name}.jsonl").write_bytes(text.encode("utf-8"))


if __name__ == "__main__":
    write()
