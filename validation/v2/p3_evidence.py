"""P3 evidence records — computed from the code, never written by hand, with a --check twin.

Same contract as `p2_evidence.py`: each record carries `properties`, named facts measured on the implementation;
`--check` re-derives every record and fails if it differs from the committed one or if any property is false. Records
hold outcomes only — never a temporary path, a duration or a wall-clock time — so a rebuild is byte-identical.

    python -P validation/v2/p3_evidence.py            # write every record whose package is implemented
    python -P validation/v2/p3_evidence.py --check    # fail on drift or on a false property
"""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import inspect
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Callable
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _module(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _raises(fn, exc) -> str | None:
    """The message `fn` raised `exc` with, or None when it did not raise."""
    try:
        fn()
    except exc as e:
        return str(e)
    return None


@contextlib.contextmanager
def _journal_dir():
    with tempfile.TemporaryDirectory(prefix="aisef2-p3-evidence-") as d:
        yield pathlib.Path(d)


def _conformance(sub: str) -> dict:
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    s = next(x for x in fc.evaluate(*fc.load_inputs())["subchecks"] if x["id"] == sub)
    return {"state": s["state"], "detail": s["detail"]}


# --------------------------------------------------------------------------------------- WP-3.1

def journal_writer() -> dict:
    from aisef2.arch.enums import EventType as T
    from aisef2.journal import event as ev
    from aisef2.journal import writer as wr
    from aisef2.journal.compat import reconstruct
    from aisef2.journal.event import Event, JournalError
    begin = {"journal_format": ev.FORMAT, "run_id": "evidence"}
    ticks = iter(float(n) for n in range(10 ** 6))

    def writer(path):
        w = wr.JournalWriter(path, clock=lambda: next(ticks))
        if not w.events:
            w.append(T.RUN_BEGIN, begin)
        return w

    def check(n):
        return {"gate": "g", "check": f"c{n}", "passed": True, "detail": ""}

    with _journal_dir() as d:
        # four layers of seq == index
        w = writer(d / "long.jsonl")
        fsyncs = []
        real_fsync = os.fsync
        with mock.patch.object(wr.os, "fsync", lambda fd: (fsyncs.append(fd), real_fsync(fd))):
            for n in range(1, 300):
                w.append(T.GATE_CHECK, check(n))
        long_ok = [e.seq for e in w.events] == list(range(300)) and \
            reconstruct((d / "long.jsonl").read_text(encoding="utf-8")).events == w.events
        w.close()
        w2 = writer(d / "append.jsonl")
        with mock.patch.object(wr.JournalWriter, "_assign", lambda self: len(self._events) + 1):
            layer_append = _raises(lambda: w2.append(T.RUN_END, {}), JournalError)
        w2.close()
        lines = (d / "long.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
        (d / "gap.jsonl").write_text("".join(lines[:5] + lines[6:]), encoding="utf-8")
        layer_seed = _raises(lambda: wr.JournalWriter(d / "gap.jsonl"), JournalError)
        layer_decode = _raises(lambda: ev.decode(lines[5].rstrip("\n"), 6, ev.GENESIS), JournalError)
        (d / "reordered.jsonl").write_text("".join([lines[0], lines[2], lines[1]] + lines[3:]), encoding="utf-8")
        journal_1 = {name: _raises(lambda n=name: reconstruct((d / n).read_text(encoding="utf-8")), JournalError)
                     for name in ("gap.jsonl", "reordered.jsonl")}
        conflicting = lines[1].replace('"c1"', '"cX"')
        journal_2 = {
            "duplicated line": _raises(lambda: reconstruct("".join(lines[:2] + [lines[1]])), JournalError),
            "same seq, other content": _raises(lambda: reconstruct("".join(lines[:1] + [conflicting])), JournalError),
            "same seq twice": _raises(lambda: reconstruct("".join(lines[:2] + [conflicting])), JournalError)}
        # append-site validation: nothing bad reaches the log
        w3 = writer(d / "validation.jsonl")
        size = (d / "validation.jsonl").stat().st_size
        refused = {
            "non-lossless payload (NaN)": _raises(lambda: w3.append(T.STORY_BEGIN, {"story_id": "S", "parent": "a" * 40,
                                                                                    "x": float("nan")}), JournalError),
            "unknown enum member": _raises(lambda: w3.append(T.STORY_ADMITTED, {
                "story_id": "S", "parent": "a" * 40, "admitted": True, "developer_call_permitted": True,
                "dispositions": {"C1": "MAYBE"}}), JournalError),
            "owner supplied by the call site": _raises(lambda: w3.append(T.FAILURE_OBSERVED, {
                "story_id": "S", "code": "PROBE_UNRUNNABLE", "owner": "DEVELOPER", "detail": ""}), JournalError),
            "a foreign error code": _raises(lambda: w3.append(T.FAILURE_OBSERVED, {
                "story_id": "S", "code": "OSError", "detail": ""}), JournalError),
            "abbreviated parent SHA": _raises(lambda: w3.append(T.STORY_BEGIN, {"story_id": "S", "parent": "a" * 12}),
                                              JournalError),
            "type outside the vocabulary": _raises(lambda: w3.append("story/bogus", {}), JournalError),
            "vocabulary type with no format-1 schema": _raises(lambda: w3.append(T.TOOL_INVOKED, {}), JournalError),
            "a seventh projection cited by a gate": _raises(lambda: w3.append(T.GATE_DECISION, {
                "gate": "g", "passed": True, "projections": ["progress_report"]}), JournalError),
            "rejected by the pre-append check": _raises(lambda: w3.append(T.RUN_END, {}, check=mock.Mock(
                side_effect=JournalError("refused by the projections"))), JournalError),
        }
        validation_log_unchanged = (d / "validation.jsonl").stat().st_size == size and len(w3.events) == 1
        w3.close()
        # fault injection: the log never grows on a failed write; the writer is poisoned
        faults = {}
        for name, patch in (("disk full on append", ("write", OSError(errno.ENOSPC, "No space left on device"))),
                            ("fsync failure", ("fsync", OSError(errno.EIO, "Input/output error")))):
            path = d / f"{patch[0]}.jsonl"
            wf = writer(path)
            before, size = wf.events, path.stat().st_size
            with mock.patch.object(wr.os, patch[0], side_effect=patch[1]):
                first = _raises(lambda wf=wf: wf.append(T.RUN_END, {}), JournalError)
            faults[name] = {"refused": first is not None and first.endswith("the journal did not grow"),
                            "log_unchanged": (wf.events, path.stat().st_size) == (before, size),
                            "writer_poisoned": (_raises(lambda wf=wf: wf.append(T.RUN_END, {}), JournalError) or "")
                            .endswith("accepts nothing more"),
                            "reopens_to_the_same_events": wr.JournalWriter(path).events == before}
            wf.close()
        wt = writer(d / "torn.jsonl")
        with mock.patch.object(wr.os, "fsync", side_effect=OSError(errno.EIO, "gone")), \
                mock.patch.object(wr.os, "ftruncate", side_effect=OSError(errno.EIO, "gone")):
            _raises(lambda: wt.append(T.RUN_END, {}), JournalError)
        wt.close()
        text = (d / "torn.jsonl").read_text(encoding="utf-8")
        (d / "torn.jsonl").write_text(text[:len(text) - 7], encoding="utf-8")
        torn = reconstruct((d / "torn.jsonl").read_text(encoding="utf-8"))
        faults["torn tail (truncation also failed)"] = {
            "reported": torn.torn_tail, "complete_prefix_only": len(torn.events) == 1,
            "not_extended": (_raises(lambda: wr.JournalWriter(d / "torn.jsonl"), JournalError) or "")
            .endswith("before extending it")}
    from aisef2.control.owner import TAXONOMY
    TAXONOMY_VIEW = {c.value: [TAXONOMY[c].owner.value, TAXONOMY[c].budget is not None] for c in TAXONOMY}
    carried = {c: [ev.carried("failure/observed", {"story_id": "S", "code": c, "detail": ""})[k]
                   for k in ("owner", "retryable")] for c in TAXONOMY_VIEW}
    public = sorted(n for n in dir(wr.JournalWriter) if not n.startswith("_"))
    sample = Event(3, "story/begin", {"story_id": "S1", "parent": "a" * 40}, 1.5)
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from aisef2.journal.event import Event, event_id; "
            "print(event_id(Event(3, 'story/begin', {'parent': 'a' * 40, 'story_id': 'S1'}, 1.5)))")
    other = subprocess.run([sys.executable, "-P", "-c", code, str(ROOT)], capture_output=True, encoding="utf-8").stdout.strip()
    f1 = _conformance("F1.event_envelope")
    return {
        "record": "AISEF V2 — P3 JOURNAL WRITER", "work_package": "WP-3.1", "rfc_sections": ["20", "20.1"],
        "frozen_items": ["F1"],
        "format": {"version": ev.FORMAT, "writable_types": sorted(ev.SCHEMAS),
                   "vocabulary_types_without_a_format_1_schema": sorted(ev.VOCABULARY - set(ev.SCHEMAS)),
                   "storage": "one canonical JSON line per event: {chain, event}; chain_n = sha256(chain_n-1 ‖ "
                              "event_id_n) from GENESIS; UTF-8, LF",
                   "sample_event_id": ev.event_id(sample)},
        "writer_surface": public,
        "seq_layers": {"assignment": "append takes no seq; _assign is its only source",
                       "seed_admission": layer_seed, "append": layer_append, "decode": layer_decode},
        "JOURNAL_1_seq_gap": journal_1,
        "JOURNAL_2_duplicate_or_conflicting_identity": journal_2,
        "append_site_refusals": refused,
        "fault_injection": faults,
        "failure_observed_carried_from_the_taxonomy": carried,
        "f1_conformance": f1,
        "residuals": ["a tail rewritten together with its chain links is detected only against an anchor held outside "
                      "the journal (a cache row's head, an evidence record)",
                      "payload schemas exist for the 18 types P3's projections and P2's StoryAdmission write; the other "
                      "vocabulary types are unwritable until a format bump gives them one"],
        "properties": {
            "seq_layer_assignment": "seq" not in inspect.signature(wr.JournalWriter.append).parameters,
            "seq_layer_seed_admission": (layer_seed or "").endswith("the journal is refused, never partially read"),
            "seq_layer_append": (layer_append or "").endswith("seq == index"),
            "seq_layer_decode": (layer_decode or "").startswith("line 6 holds seq 5: seq == index is broken"),
            "seq_equals_index_over_a_long_sequence": long_ok,
            "no_update_or_delete_verb": public == ["append", "close", "emit", "events", "head", "path"],
            "every_append_fsyncd": len(fsyncs) == 299,
            "JOURNAL_1_a_seq_gap_is_refused_never_partial": all(m and "seq == index is broken" in m
                                                                for m in journal_1.values()),
            "JOURNAL_2_duplicate_or_conflicting_identity_fails_closed": all(journal_2.values()),
            "append_site_validation_refuses_before_the_log_grows": all(refused.values()) and validation_log_unchanged,
            "fault_injection_leaves_the_log_unchanged": all(all(v.values()) for v in faults.values()),
            "event_identity_deterministic_across_processes": other == ev.event_id(sample),
            "failure_owner_and_retryable_carried_from_the_taxonomy": carried == TAXONOMY_VIEW,
            "f1_event_envelope_equals_rfc": f1["state"] == "PASS",
        },
    }


# --------------------------------------------------------------------------------------- WP-3.2

def format_compat() -> dict:
    from aisef2.journal.compat import UnknownRequiredEvent, reconstruct
    from aisef2.journal.event import FORMAT, SCHEMAS, JournalError
    fx = _module("aisef_v2_p3_journal_fixtures", "tests/v2/p3/journal_fixtures.py")
    outcomes, silent_wrong = {}, []
    for name, (text, (expected, _)) in fx.FIXTURES.items():
        committed = (fx.DIR / f"{name}.jsonl").read_bytes().decode("utf-8")
        try:
            j = reconstruct(committed)
            outcomes[name] = {"expected": expected, "read": "OK", "known_seqs": [e.seq for e in j.events],
                              "skipped": list(j.skipped), "torn_tail": j.torn_tail, "equals_build": committed == text}
            if not all(e.type in SCHEMAS and not e.ignorable for e in j.events) or \
                    sorted([e.seq for e in j.events] + list(j.skipped)) != list(range(j.length)):
                silent_wrong.append(name)
        except JournalError as err:
            outcomes[name] = {"expected": expected, "read": "REFUSED", "refusal": type(err).__name__, "reason": str(err),
                              "equals_build": committed == text}
    o = outcomes
    return {
        "record": "AISEF V2 — P3 FORMAT COMPATIBILITY", "work_package": "WP-3.2", "rfc_sections": ["20", "35"],
        "frozen_items": ["F1"],
        "format": FORMAT,
        "rule": "unknown type without ignorable -> refuse to reconstruct (never partial); unknown ignorable -> skip, "
                "seq kept, never folded; a known type is always validated and never ignorable; the format is declared "
                "once, in run/begin at seq 0; a torn tail is reported and never decoded; a reader never negotiates",
        "fixtures": outcomes,
        "properties": {
            "committed_fixtures_equal_the_build": all(v["equals_build"] for v in o.values())
                and sorted(p.stem for p in fx.DIR.glob("*.jsonl")) == sorted(fx.FIXTURES),
            "every_fixture_reads_as_expected": all(
                (v["read"] == "REFUSED") is (v["expected"] == "REFUSE") for v in o.values()),
            "FORMAT_1_unknown_required_refuses_reconstruction": all(
                o[n].get("refusal") == UnknownRequiredEvent.__name__
                for n in ("unknown_required", "mixed_stream_new_required")),
            "FORMAT_2_unknown_ignorable_skipped_and_reconstruction_continues":
                (o["unknown_ignorable"].get("skipped"), o["unknown_ignorable"].get("known_seqs")) == ([2], [0, 1, 3, 4])
                and o["mixed_stream_new_ignorable"].get("skipped") == [1, 3],
            "malformed_known_type_refused": o["malformed_known"]["read"] == "REFUSED",
            "version_or_schema_mismatch_refused": all(o[n]["read"] == "REFUSED"
                                                      for n in ("version_mismatch", "newer_schema_field")),
            "mixed_old_new_stream": [o[n]["read"] for n in ("mixed_stream_second_declaration",
                                                            "mixed_stream_new_required", "mixed_stream_new_ignorable")]
                == ["REFUSED", "REFUSED", "OK"],
            "a_known_type_marked_ignorable_is_refused_not_skipped": o["known_type_marked_ignorable"]["read"] == "REFUSED",
            "torn_tail_reported_never_decoded": o["torn_tail"].get("torn_tail") is True
                and o["torn_tail"].get("known_seqs") == [0, 1],
            "no_newer_log_produces_a_silent_wrong_state": silent_wrong == [],
        },
    }


BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-3.1": ("closure-evidence/v2/P3-JOURNAL-WRITER.json", journal_writer, "aisef2/journal/writer.py"),
    "WP-3.2": ("closure-evidence/v2/P3-FORMAT-COMPAT.json", format_compat, "aisef2/journal/compat.py"),
}


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


def problems_of(record: dict) -> list[str]:
    props = record.get("properties") or {}
    out = [] if props else [f"{record.get('work_package')}: record carries no properties"]
    return out + [f"{record.get('work_package')}: property {k} is false" for k, v in props.items() if v is not True]


def check(root: pathlib.Path = ROOT) -> list[str]:
    out = []
    for rel, build, needs in BUILDERS.values():
        if not (root / needs).exists():
            continue
        fresh = build()
        out += problems_of(fresh)
        committed = root / rel
        if not committed.exists():
            out.append(f"{rel} is missing")
        elif committed.read_text(encoding="utf-8") != render(fresh):
            out.append(f"{rel} is stale: regenerate it")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        problems = check()
    else:
        problems = []
        for rel, build, needs in BUILDERS.values():
            if (ROOT / needs).exists():
                record = build()
                problems += problems_of(record)
                if not problems_of(record):
                    (ROOT / rel).write_text(render(record), encoding="utf-8")
                    print(f"wrote {rel}")
    for p in problems:
        print(f"FAIL  {p}")
    print("p3 evidence: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
