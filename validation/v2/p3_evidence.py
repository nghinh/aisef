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


# --------------------------------------------------------------------------------------- WP-3.3

def fold_oracle() -> dict:
    import dataclasses
    import random
    from aisef2.arch.enums import ControlProjection as P, EventType as T
    from aisef2.journal import fold as fo
    from aisef2.journal.compat import reconstruct
    from aisef2.journal.event import JournalError
    from aisef2.journal.projections import PROJECTIONS, project
    from aisef2.journal.writer import JournalWriter
    from aisef2.product.contract import canonical, digest
    gen = _module("aisef_v2_p3_journal_gen", "tests/v2/p3/journal_gen.py")
    ks = _module("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
    six = list(PROJECTIONS.values())
    runs = [reconstruct(gen.journal(seed, stories=2 + seed % 4)) for seed in range(40)]
    prefixes = sum(len(j.events) for j in runs)
    every_prefix = {p.id: sum(len(fo.oracle_problems(p, j.events)) for j in runs) for p in six}
    large = [reconstruct(gen.journal(seed, stories=40)) for seed in (101, 202)]
    sampled = {p.id: sum(len(fo.oracle_problems(p, j.events, every=37)) for j in large) for p in six}
    fold_2 = []
    for seed in range(15):
        rng = random.Random(seed)
        a = reconstruct(gen.journal(seed))
        b = reconstruct(gen.journal(seed, times=lambda n, rng=rng: 1.7e9 + rng.uniform(0, 1e6)))
        fold_2.append(a.head() != b.head() and all(fo.fold(p, a.events) == fo.fold(p, b.events) for p in six))
    text = gen.journal(5)
    torn = reconstruct(text[:len(text) - 30])
    complete = reconstruct(text[:len(text) - 30][:text[:len(text) - 30].rindex("\n") + 1])
    here = {p.id: digest(fo.fold(p, reconstruct(gen.journal(11)).events)) for p in six}
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from aisef2.journal.compat import reconstruct; "
            "from aisef2.journal.fold import fold; from aisef2.journal.projections import PROJECTIONS; "
            "from aisef2.product.contract import digest; from tests.v2.p3 import journal_gen as g; "
            "j = reconstruct(g.journal(11)); print({p.id: digest(fold(p, j.events)) for p in PROJECTIONS.values()})")
    other = subprocess.run([sys.executable, "-c", code, str(ROOT)], capture_output=True, encoding="utf-8",
                           cwd=str(ROOT)).stdout.strip()

    class Mutating:
        id, version = "mutating", 1

        def initial(self):
            return {"n": 0}

        def step(self, state, event):
            state["n"] += 1
            return state
    # caches
    p = PROJECTIONS[P.BUDGETS]
    full_text = gen.journal(21)
    lines = full_text.splitlines(keepends=True)
    full, half = reconstruct(full_text), reconstruct("".join(lines[:len(lines) // 2]))
    truth, row = fo.fold(p, full.events), fo.cache_row(p, half)
    wrong = dataclasses.replace(row, state={**row.state, "retries": {"S1": {"DEVELOPER": 99}}})

    def sealed(r, **over):
        r = dataclasses.replace(r, **over)
        return dataclasses.replace(r, digest=fo._seal(r.projection, r.version, r.length, r.head, r.state))
    cache_cases = {name: fo.resume(p, full, r)[1] for name, r in (
        ("stale row (shorter prefix)", row), ("edited state", wrong),
        ("another projection", fo.cache_row(PROJECTIONS[P.STORY_STATE], half)),
        ("version mismatch", sealed(row, version=2)), ("head differs", sealed(row, head="f" * 64)),
        ("ahead of the journal", sealed(row, length=full.length + 1)))}
    cache_answers = {name: fo.resume(p, full, r)[0] == truth for name, r in (
        ("stale row (shorter prefix)", row), ("edited state", wrong), ("version mismatch", sealed(row, version=2)),
        ("head differs", sealed(row, head="f" * 64)), ("ahead of the journal", sealed(row, length=full.length + 1)))}
    forged = sealed(row, state=wrong.state)
    with _journal_dir() as d:
        w = JournalWriter(d / "authority.jsonl", clock=lambda: 0.0)
        authority = fo.Authority(w, six)
        specs = gen.specs(31)[:60]
        for type_, data, cites in specs:
            authority.append(T(type_), data, source_seqs=cites)
        j = reconstruct((d / "authority.jsonl").read_text(encoding="utf-8"))
        incremental_is_fold = all(authority.state(q.id) == fo.fold(q, j.events) for q in six)
        size = (d / "authority.jsonl").stat().st_size
        refused = _raises(lambda: authority.append(T.STORY_COMMIT, {"story_id": "S-never", "revision": "a" * 40}),
                          fo.ProjectionError)
        log_unchanged = (d / "authority.jsonl").stat().st_size == size and len(w.events) == len(specs)
        w.close()
    ft = _module("aisef_v2_p3_fold_oracle_tests", "tests/v2/test_fold_oracle.py")
    proj_2 = {how: [_raises(lambda s=seed, h=how: reconstruct(ft.tampered(gen.journal(s), h)), JournalError)
                    for seed in range(10)] for how in ("edit", "delete")}
    time_clean = ks.check(ROOT, ("NO_TIME_IN_PROJECTIONS",)) == []
    time_fires = ks.violations("aisef2/journal/projections/bad.py", "def f(e):\n    return e.time\n",
                               ("NO_TIME_IN_PROJECTIONS",)) != []
    return {
        "record": "AISEF V2 — P3 FOLD ORACLE", "work_package": "WP-3.3", "rfc_sections": ["21"],
        "frozen_items": ["F11"],
        "rule": "every read model is a pure fold of a journal prefix; incremental state == fold(prefix); a cache row "
                "is a sealed, checked shortcut, discarded (never migrated) when it no longer describes the journal; a "
                "gate never reads a cache; no projection reads time",
        "oracle": {"generated_runs": len(runs), "prefixes_checked_per_projection": prefixes,
                   "problems_every_prefix": every_prefix, "large_runs": [len(j.events) for j in large],
                   "problems_sampled_every_37": sampled},
        "FOLD_2_wall_clock_rewritten": {"runs": len(fold_2), "control_state_unchanged": sum(fold_2)},
        "PROJ_2_tampered_old_event": {how: v[0] for how, v in proj_2.items()},
        "caches": {"how_each_row_was_treated": cache_cases, "answer_is_the_journal_fold": cache_answers,
                   "ceiling": "a row re-sealed over a wrong state with the right head passes resume's checks "
                              "(resumed: " + str(fo.resume(p, full, forged)[1].startswith("resumed")) + "); no gate "
                              "reads a cache — project() folds the journal"},
        "properties": {
            "FOLD_1_incremental_equals_full_fold_for_every_prefix": all(v == 0 for v in every_prefix.values()),
            "large_generated_journals_sampled": all(v == 0 for v in sampled.values()) and min(len(j.events)
                                                                                              for j in large) > 300,
            "FOLD_2_wall_clock_time_is_not_control_state": all(fold_2),
            "empty_and_one_event_journals": all(canonical(fo.fold(q, [])) == canonical(q.initial()) for q in six)
                and all(fo.fold(q, runs[0].events[:1]) == fo.Folder(q).advance(runs[0].events[0]) for q in six),
            "replay_twice_identical": all(canonical(fo.fold(q, runs[9].events)) == canonical(fo.fold(q, runs[9].events))
                                          for q in six),
            "interrupted_tail_folds_as_its_complete_prefix": torn.torn_tail and torn.events == complete.events,
            "deterministic_serialisation_across_processes": other == str(here),
            "a_step_cannot_change_its_input_state": _raises(lambda: fo.fold(Mutating(), runs[1].events), TypeError)
                is not None,
            "stale_cache_used_only_as_a_checked_shortcut": cache_cases["stale row (shorter prefix)"].startswith(
                "resumed") and all(cache_answers.values()),
            "PROJ_1_a_row_that_differs_from_the_journal_is_discarded": all(
                v.endswith("discarded") or "discarded" in v for k, v in cache_cases.items()
                if k != "stale row (shorter prefix)"),
            "version_mismatch_discarded_not_migrated": cache_cases["version mismatch"].endswith("not migrated"),
            "no_gate_reads_a_cache": "cache" not in inspect.signature(project).parameters
                and project(full, P.BUDGETS) == truth,
            "no_projection_reads_time": time_clean and time_fires,
            "PROJ_2_an_edited_or_deleted_old_event_fails_reconstruction":
                all(m and "the chain does not link" in m for m in proj_2["edit"])
                and all(m and "seq == index is broken" in m for m in proj_2["delete"]),
            "authority_incremental_state_is_the_fold": incremental_is_fold,
            "a_refused_event_never_reaches_the_log": refused is not None and log_unchanged,
        },
    }


# --------------------------------------------------------------------------------------- WP-3.4

def control_projections() -> dict:
    from aisef2.arch.enums import ControlProjection as P
    from aisef2.journal.fold import ProjectionError, fold
    from aisef2.journal.projections import PROJECTIONS, project
    from aisef2.product.contract import digest, plain
    t = _module("aisef_v2_p3_control_projections", "tests/v2/p3/test_control_projections.py")
    gen = _module("aisef_v2_p3_journal_gen", "tests/v2/p3/journal_gen.py")
    mut = json.loads((ROOT / "closure-evidence/v2/P3-MUTATION.json").read_text(encoding="utf-8")) \
        if (ROOT / "closure-evidence/v2/P3-MUTATION.json").exists() else {"targets": []}
    reference = t.run(t.plan(A="INTRODUCE", B="INTRODUCE", C="PRESERVE"), t.begin("S1"),
                      t.admit("S1", {"A": "PRE_SATISFIED", "B": "READY"}), t.drift("S1", "A", []),
                      t.request("S1", "B"), t.fail("S1", "CONTRACT_UNSATISFIED"), t.fail("S1", "PROVIDER_UNAVAILABLE"),
                      t.story("retry", "S1", 7), t.story("dispose", "S1"), t.story("end", "S1"), t.begin("S1"),
                      t.admit("S1", {"A": "READY", "B": "READY"}), t.request("S1", "A", "B"), t.story("commit", "S1"),
                      t.story("dispose", "S1"), t.story("end", "S1"), t.begin("S2"),
                      t.admit("S2", {"C": "PLAN_CONTRADICTION"}), t.fail("S2", "PLAN_CONTRADICTION"),
                      t.story("rollback", "S2", 19), ("run/dispose-begin", {}), ("run/end", {}))
    states = {k.value: plain(fold(p, reference)) for k, p in PROJECTIONS.items()}
    samples = {}
    for name, case, specs in (
            ("story_state: commit before admission", P.STORY_STATE, (t.begin("S1"), t.story("commit", "S1"))),
            ("failure_owner: a rollback citing another attempt's failure", P.FAILURE_OWNER,
             (t.begin("S1"), t.fail("S1"), t.story("retry", "S1", 2), t.story("dispose", "S1"), t.story("end", "S1"),
              t.begin("S1"), t.story("rollback", "S1", 2))),
            ("budgets: developer charge on a PRE_SATISFIED criterion", P.BUDGETS,
             (t.begin("S1"), t.admit("S1", {"A": "PRE_SATISFIED", "B": "READY"}), t.request("S1", "A"))),
            ("budgets: retry of a non-retryable failure", P.BUDGETS,
             (t.begin("S1"), t.fail("S1", "INVALID_CREDENTIAL"), t.story("retry", "S1", 2))),
            ("retry_target: failure of a story never begun", P.RETRY_TARGET, (t.fail("S1"),)),
            ("terminal_state: an event after run/end", P.TERMINAL_STATE, (("run/end", {}), t.begin("S1"))),
            ("qualification_counters: a second plan freeze", P.QUALIFICATION_COUNTERS,
             (t.plan(A="INTRODUCE"), t.plan(A="INTRODUCE")))):
        samples[name] = _raises(lambda c=case, s=specs: fold(PROJECTIONS[c], t.run(*s)), ProjectionError)
    independence = t.Independence("test_every_story_folds_alone_to_its_entry_in_the_run")
    independent = unittest_ok(independence)
    by_target = {x["target"]: f"{x['killed']}/{x['mutants']}" for x in mut["targets"]
                 if "/projections/" in x["target"]}
    f11 = _conformance("F11.projections_implemented")
    generated = [gen.journal(seed) for seed in range(20)]
    return {
        "record": "AISEF V2 — P3 CONTROL PROJECTIONS", "work_package": "WP-3.4", "rfc_sections": ["17", "21", "22", "29"],
        "frozen_items": ["F11"],
        "semantics": "docs/implementation/v2/P3-PROJECTION-SEMANTICS.md",
        "projections": {k.value: {"version": p.version, "module": type(p).__module__} for k, p in PROJECTIONS.items()},
        "reference_journal_states": states,
        "reference_journal_state_digests": {k: digest(v) for k, v in states.items()},
        "refusal_samples": samples,
        "mutation_by_target": by_target,
        "f11_conformance": f11,
        "properties": {
            "six_of_six_implemented": [k.value for k in PROJECTIONS] == [x.value for x in P],
            "closed_list_a_seventh_cannot_be_cited": _raises(lambda: project(None, "progress_report"), ProjectionError)
                is not None and _raises(lambda: _assign(PROJECTIONS, "seventh"), TypeError) is not None,
            "no_side_counter_every_value_is_a_fold": all(vars(p) == {} for p in PROJECTIONS.values()),
            "every_rule_sample_refuses": all(v is not None and v.startswith(k.split(":")[0])
                                             for k, v in samples.items()),
            "a_story_depends_on_its_own_events_only": independent,
            "generated_runs_fold_through_all_six": all(fold(p, _reconstruct(text).events) is not None
                                                        for text in generated for p in PROJECTIONS.values()),
            "mutation_fully_killed": bool(by_target) and all(a == b for a, b in
                                                             (v.split("/") for v in by_target.values())),
            "f11_projections_equal_rfc": f11["state"] == "PASS",
        },
    }


# --------------------------------------------------------------------------------------- WP-3.5

def reference_models() -> dict:
    from aisef2.arch.enums import ControlProjection as P
    from aisef2.journal.compat import reconstruct
    from aisef2.journal.event import JournalError
    from aisef2.journal.projections import PROJECTIONS
    h = _module("aisef_v2_p3_reference_models", "tests/v2/p3/test_reference_models.py")
    x = _module("aisef_v2_p3_reference_defects", "tests/v2/p3/test_reference_defects.py")
    gen = _module("aisef_v2_p3_journal_gen", "tests/v2/p3/journal_gen.py")
    ind = _module("aisef_v2_refmodel_independence", "validation/v2/refmodel_independence.py")
    mut = json.loads((ROOT / "closure-evidence/v2/P3-MUTATION.json").read_text(encoding="utf-8"))
    calibration = {pid: h.calibration_problems(model, h.CALIBRATIONS[pid]) for pid, model in h.MODELS.items()}
    implementation_on_calibration = {
        pid: [c["name"] for c in h.CALIBRATIONS[pid]
              if h.projection_answer(PROJECTIONS[P(pid)], reconstruct(h.stored(c["events"])).events)
              != h.expected_of(c)]
        for pid in h.MODELS}
    agreeing = {}
    for pid, cases in h.CALIBRATIONS.items():
        answers = {json.dumps(c["events"], sort_keys=True): c["wrong"] for c in cases}

        def mirror(events, answers=answers):
            got = answers[json.dumps(events, sort_keys=True)]
            if got == h.REFUSED:
                raise h.Refused("mirrored")
            return got
        agreeing[pid] = len(h.calibration_problems(mirror, cases)) > 0
    diff = {pid: 0 for pid in h.MODELS}
    traces = 0
    for seed in range(120):
        events = reconstruct(gen.journal(seed, stories=3 + seed % 5)).events
        traces += 1
        for pid, model in h.MODELS.items():
            diff[pid] += h.projection_answer(PROJECTIONS[P(pid)], events) != h.model_answer(model, events)
    edited = {"compared": 0, "refused_by_both": 0, "divergent": 0}
    for seed in range(150):
        try:
            events = reconstruct(h.text_of(h.mutated(seed))).events
        except JournalError:
            continue
        for pid, model in h.MODELS.items():
            want, got = h.projection_answer(PROJECTIONS[P(pid)], events), h.model_answer(model, events)
            edited["compared"] += 1
            edited["refused_by_both"] += want == got == h.REFUSED
            edited["divergent"] += want != got
    injected = {pid: x.divergences(pid, x.defective(pid, step)) for pid, step in x.DEFECTS.items()}
    clean = {pid: x.divergences(pid, PROJECTIONS[P(pid)], range(0, 200, 7)) for pid in h.MODELS}
    mt = _module("aisef_v2_mutation", "validation/v2/mutation.py")
    refmodel = [x for x in mut["targets"] if "refmodel" in x["target"]]
    by_target = {x["target"]: {"killed": f"{x['killed']}/{x['mutants']}",
                               "audited_equivalent": {s: mt.AUDITED[(x["target"], s)] for s in x["survivors"]
                                                      if (x["target"], s) in mt.AUDITED}} for x in refmodel}
    return {
        "record": "AISEF V2 — P3 REFERENCE MODELS", "work_package": "WP-3.5", "rfc_sections": ["21", "27 (Q1)"],
        "frozen_items": ["F11"],
        "authorship": "authored in a separate work session from the RFC and docs/implementation/v2/"
                      "P3-PROJECTION-SEMANTICS.md, in a clone holding neither aisef2/journal/fold.py nor "
                      "aisef2/journal/projections/ (the manifest's WP-3.5 authorship constraint)",
        "independence_rule": "validation/v2/refmodel_independence.py: stdlib and the package only; no aisef2, no other "
                             "tests module, no importlib / __import__ / exec / eval / compile",
        "models": {pid: {"calibration_cases": [c["name"] for c in h.CALIBRATIONS[pid]]} for pid in h.MODELS},
        "calibration_problems": calibration,
        "implementation_disagrees_with_calibration": implementation_on_calibration,
        "differential": {"generated_traces": traces, "divergent_by_model": diff, "edited_traces": edited},
        "REF_1_injected_defects": {pid: {"defect": x.DEFECTS[pid].__name__, "divergent_traces": n}
                                   for pid, n in injected.items()},
        "mutation_by_target": by_target,
        "properties": {
            "six_of_six_reference_models": sorted(h.MODELS) == sorted(p.value for p in P),
            "no_import_constraint_mechanically_enforced": ind.check(ROOT) == []
                and bool(ind.violations("tests/v2/refmodel/x.py", "import aisef2.journal.projections\n")),
            "six_of_six_calibrated": all(v == [] for v in calibration.values())
                and all(len(h.CALIBRATIONS[p]) >= 3 for p in h.MODELS),
            "the_implementation_reproduces_every_calibration_answer": all(v == [] for v in
                                                                          implementation_on_calibration.values()),
            "REF_2_an_always_agree_model_fails_calibration": all(agreeing.values()),
            "implementation_equals_reference_model_over_generated_traces": all(v == 0 for v in diff.values()),
            "on_edited_traces_both_refuse_or_agree": edited["divergent"] == 0 and edited["refused_by_both"] > 20,
            "REF_1_every_injected_projection_defect_is_caught": all(n > 0 for n in injected.values())
                and all(n == 0 for n in clean.values()),
            # every mutant killed but those audited equivalent in mutation.AUDITED; a stale result fails
            "reference_model_mutation_killed_or_audited_equivalent": len(refmodel) == sum(
                "refmodel" in t for t in mt.P3_TARGETS) and all(mt.target_problems(x, ROOT) == [] for x in refmodel),
        },
    }


def _assign(mapping, key) -> None:
    mapping[key] = None


def _reconstruct(text):
    from aisef2.journal.compat import reconstruct
    return reconstruct(text)


def unittest_ok(case) -> bool:
    import unittest
    result = unittest.TestResult()
    case.run(result)
    return result.wasSuccessful() and result.testsRun == 1


BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-3.1": ("closure-evidence/v2/P3-JOURNAL-WRITER.json", journal_writer, "aisef2/journal/writer.py"),
    "WP-3.2": ("closure-evidence/v2/P3-FORMAT-COMPAT.json", format_compat, "aisef2/journal/compat.py"),
    "WP-3.3": ("closure-evidence/v2/P3-FOLD-ORACLE.json", fold_oracle, "aisef2/journal/fold.py"),
    "WP-3.4": ("closure-evidence/v2/P3-CONTROL-PROJECTIONS.json", control_projections,
               "aisef2/journal/projections/__init__.py"),
    "WP-3.5": ("closure-evidence/v2/P3-REFERENCE-MODELS.json", reference_models, "tests/v2/refmodel/__init__.py"),
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
