"""RFC §9 — probe kind `cli_invocation` (Cycle 2, WP-2.2.1; CYCLE2-PROBE-TAXONOMY-PROPOSAL §2).

**Subject.** `kind = cli_invocation`, locator `"<module>:__main__"` (the module of the revision run as `__main__` through
`runpy.run_module`; for a package that is its `__main__` submodule) or `"<module>:<callable>"` (an entry function
called with the argv list; its return value is its exit status, as `sys.exit(main(argv))` would take it). The module
is located with the import system's path finder against the revision checkout (its root and, if present, `src/`)
without executing anything; a module that does not resolve, or resolves only outside the checkout, is absent *at this
revision*. A console-script name is never accepted: it resolves through the environment, not the revision.
A directory without `__init__.py` is a namespace package like any other, at every depth: each component of the
dotted name is looked up by its own name within its parent's locations, so a module below one is located as the
import system locates it, never an environment failure.

**Stimulus.** `{"argv": [...], "stdin": null | {"text", "newline"} | {"bytes_hex"}, "workspace": {name: content},
"pre": [{"argv": [...]}, ...]}`. Workspace files are written byte-exactly into the subject's workspace before any
invocation; `<ws>` is the only placeholder — an argv entry `<ws>/name` becomes that file's absolute path, nothing else
is ever substituted. The pre-steps invoke the same subject, in the same child process, in order, each captured on its
own; one that does not exit 0 makes the observation REFUTED with its index in `detail`.

**Observable classes.** Every observable declares its bounded window `within_s` (§9.2). The controller arms the window's
timer right after DISPATCHED, and the subject's answer and the timer take one lock between them: a subject that answers
at exactly W is whichever of the two takes it first, and no `<` or `<=` is published for it. A finite W the timer cannot
hold (`threading.TIMEOUT_MAX`, about 292 years) ends the timer's thread and leaves the window to the watchdog's wait of
`W + timeouts_s.probe`; nothing here caps W.

| class | observable | SATISFIED when | the window expires |
|---|---|---|---|
| `exits` | `{"exit_code": N, "within_s": W}` | the invocation returned with that exit code | REFUTED |
| `exits_streams` | adds `"stdout"` / `"stderr"`, each a shape | `exits`, and each named stream matches its shape | REFUTED |
| `exits_files` | adds `"files": {"<ws>/name": shape}` | `exits`, and each named file matches its shape | REFUTED |
| `blocks` | `{"blocks": true, "within_s": W}` | the invocation has not returned when W closes | SATISFIED |
| `equality` | `{"equality": {...}, "streams": [...], "within_s": W}` | two invocations agree (below) | REFUTED |

**Equality (WP-2.2.2, DECISION-4).** `{"equality": {"stimulus_a": {...}, "stimulus_b": {...}, "normalization":
{"newline": "\n", "strip_trailing_newline": false}, "comparator": "bytes_equal" | "json_equal"}, "streams":
["stdout", ...], "within_s": W}` with an empty spec stimulus: two independent invocations of the same subject, each in
a fresh evaluation directory of its own (workspace, bytecode cache, protocol file, captures), each under W. SATISFIED
iff both returned, their exit codes are equal and, for every named stream, the captured bytes — the declared newline
turned into `\n`, one trailing newline stripped when the policy says so — are equal under the comparator. Both
stimuli, the policy and the comparator are probe input, so they enter `semantic_hash`; all four are required (an
empty policy `{}` compares the bytes as captured) — one left out is refused at admission (UNSUPPORTED -> INVALID_SPEC),
never defaulted. The comparator reads the two normalised results and nothing else; under `json_equal`, bytes that are
not UTF-8 JSON are unequal (REFUTED), never an error. A half that is not a returned invocation is the observation (an
absent subject, an expired window — REFUTED —, a signal, a harness failure, a failed pre-step).

**Class table (WP-2.2.2, DECISION-1).** `CLASS_TABLE` declares, per class, its quantifier semantics — the `exits`
classes measure the one declared invocation exhaustively; `blocks` and `equality` are bounded witness measurements
(the window, the two invocations), never a proof of the universal property — and the rows (observation facts ->
verdict) `verdict_of` and `ON_DEADLINE` answer, tested exhaustively.

Stream shapes (a closed set, compared over the captured bytes; prose matching is not offered): an exact string or
`{"text": s, "newline": nl}` (the text's newlines written as `nl`, default `"\\n"`, compared as bytes), `{"contains":
[s, ...]}` (every string present as bytes), `{"regex": r}` (`re.search` over the utf-8 decoding; `r` is a pattern
`re.compile` takes, else the observable has no meaning; that compile is made by the classifier, in the kernel's process,
and has no deadline: its cost grows with the pattern's size, 3.7 s for 19 KB of case-insensitive full-range classes,
measured — nothing here bounds it), `{"lines": n}` (the number of lines) and `{"first_word": w}`.
The pattern is a model's or a spec author's and the stream is the candidate's, and the time a search takes depends on
both (`(a+)+$` over a line of `a`s does not return): so the search of a `regex` shape never runs in the probe's own
process. It runs in a worker of its own (`REGEX_WORKER`, `sys.executable -I -S -B`, in a process range of its own), given
the pattern and the captured bytes by a file and answering by a file, under the harness watchdog
`ExecutionEnv.timeout_s` (the operator's `timeouts_s.probe`) for the whole operation. A worker that does not answer
inside it — it hung (DEADLINE), could not start (LAUNCH), ended by a status or a signal (CRASHED), wrote nothing
(NO_RESULT) or something that is not an answer (BAD_RESULT) — is a stop of the harness: HARNESS_FAILED, UNRUNNABLE
(owner ENVIRONMENT), never a verdict about the product, never retried (the same pattern over the same bytes within the
same deadline stops the same way), its range emptied before the observation returns. A search that returned gives the
verdict the in-process search always gave. It is not part of the subject's window: it begins after RESULT, and the time
it takes is the harness's, never charged to `within_s` (a search that is slow and finishes inside the watchdog changes
no verdict; one that does not finish is not a verdict at all). The conjuncts are read in the order exit code, stdout,
stderr: one that already fails is REFUTED without a search, and a search that cannot be made for a conjunct that is
reached is HARNESS_FAILED even where a later conjunct would have failed — the harness does not decide by what it did
not compute. The search is made only once the subject's range is empty, never while any of it is alive (the verdict is
decided after `release`, with everything that could change what is read already gone): the worker's request, result and
log are files of a directory made for that search at that moment, with a name nobody can have chosen before (`mkdtemp`
inside the evaluation directory), so a name the subject could guess is not where the harness writes or reads, a link it
planted there is not followed, and no process of the subject can rewrite the pattern, the bytes or the answer. If the
controller stops the search (its signal ledger holds a signal on the worker's range) the observation is interrupted
(§9.3), as it is for the subject's range; it is not a harness failure.
File shapes: `{"sha256": hex}`, `{"text": s, "newline": nl}` (its digest), `{"absent": true}` and `{"equals_before":
true}` (the file's digest, or its absence, is what it was before the main
invocation — the harness records every named file before and after). Exit codes are recorded as CPython reports them:
`SystemExit(None)` is 0, an int is itself, any other status is 1 and is printed to stderr; an uncaught exception is
recorded by its type name, with a traceback on stderr and exit code 1. The raw status is kept beside the code.

**Captured streams.** The subject's stdout and stderr are redirected at the descriptor level (`os.dup2` onto files of
the evaluation directory, one pair per invocation), so nothing the subject writes can reach the protocol channel: a
forged protocol line on stdout is captured bytes like any other. Each capture keeps at most `STREAM_CAP` bytes (the
subject may write more; the fact says `truncated`, and an exact shape is then REFUTED; every other shape is judged over
the bytes that were kept, whatever was cut, and no rule is published for that), and a stream's facts are the bytes
captured when the invocation returned — bytes a lingering thread APPENDS later are not the invocation's (the parent
reads the first `size` bytes). It does not compare them with the fact's `sha256`: a process that lingers and rewrites
bytes already captured, before its range is released, changes what is read (measured; an older limit of this probe's
PARTIAL enforcement, not closed here).
The captured bytes are the same on every platform (C2-P2-FINDING-001): the capture files are opened in binary mode
(`O_BINARY` where the platform has it, so no C runtime translates a descriptor's newlines), and the harness pins
the newline handling of the interpreter's standard text streams to `"\n"` before the first invocation — the
platform default on POSIX, and on Windows what keeps a `"\n"` written through `sys.stdout` from becoming `"\r\n"` and
a `"\r\n"` read through `sys.stdin` from becoming `"\n"` — the way UTF-8 mode is pinned: a verdict is a function of
the revision, the spec and the probe identity, never of the platform the harness runs on. Files the subject opens
itself keep whatever newline convention its own code asks of the platform: that is the product's behaviour.

**Controller and subject process (B1, V2.0 release charter §7).** The probe's process is a controller that never
imports, constructs, calls or invokes the subject and never puts the revision on its own path: it starts the
subject's process (`AGENT`, a child of the controller in the same owned range) before DISPATCHED and asks it for one
operation at a time over a pair of pipes — each answer echoing its request's number, a final request closing the
exchange, so an answer the agent did not write is detected — and builds every fact itself, from those answers and
from the files it reads (captures, workspace files). The controller alone writes the protocol, each line authenticated
with HMAC-SHA256 under a key the parent puts in the request; the key and the nonce leave the request file before the
subject's process exists. Code of the revision therefore cannot write, forge or overwrite a protocol line, nor build
the facts the verdict is decided from: what it controls is its own behaviour, which is what is observed. A hard exit
or a signal of the subject's process is reported by the controller, which outlives it.

What this does not give (PM-5, V21-26; measured, closure-evidence/v2/v2.1/round-3/probes/repro-5*): the answers of the
subject's process -- an exit code, a returned value, a raised exception -- are given by a process the subject's own code
shares, so the channel is protected and the truth of an answer is not. Code written to answer for itself, or to recognise
that it is being probed (`sys.flags.isolated`, the scrubbed environment), can make a product that fails when a person
runs it come out SATISFIED here. The probe says what the process answered; it cannot say the answer is honest.

**Protocol channel (DESIGN-CHECK-1).** The taxonomy proposal suggested a dedicated descriptor (fd 3) on POSIX and a
marker file on Windows. The owned process range (`aisef2/runtime/process_range.py`) launches the target through an
anchor process that forwards no extra descriptor, and the runtime is out of this package's scope, so the channel is a
harness-owned marker file inside the evaluation directory on every platform — a design choice inside F5, not an
exception. The controller writes `<mark> READY <nonce> <mac>`, `<mark> DISPATCHED <nonce> <mac>` (right before the first
invocation), `<mark> PRE <nonce> <mac> <i>` / `<mark> MAIN <nonce> <mac> {"before": ...}` (which invocation is running),
`<mark> RESULT <nonce> <mac> <facts>` and `<mark> END <nonce> <mac>` to that file only, flushing and fsyncing each line.
The parent polls the file: it reads the whole file, keeps the complete lines (ending in a newline) that carry the mark,
this evaluation's nonce and a valid authentication of their tag and body — an unterminated last line, and a line
anything else wrote, are never protocol lines — and the poll decides only when to look, never what was said.
Under the harness watchdog (`ExecutionEnv.timeout_s`) it waits for DISPATCHED; under the spec's window for RESULT.
The exit is lifecycle evidence, asked of the range with a non-blocking wait at each poll: when the process has
exited, the file is read once more, to its end, before anything is concluded (RFC §9.4 applied to the file: no
timing window orders the exit and the last write). Decision table, after DISPATCHED:

* RESULT read -> OBSERVED with `verdict_of`, decided once the subject's range is empty (SUBJECT_ABSENT when the
  controller found no subject); a `regex` shape whose search gave no answer (above) is HARNESS_FAILED instead, there
  being no verdict to give. The subject's process
  ending itself is in RESULT: by an exit status (`os._exit`, a hard exit) — the facts carry its exit code and the capture
  files as the streams (`hard_exit`); a hard exit during a pre-step is REFUTED with that step's index; by a signal —
  NON_CONTROLLER_SIGNAL (§9.3) unless the controller's own ledger holds a signal (an interruption, `ProbeInterrupted`,
  as python_callable._after_dispatch); an answer on the subject's channel that the agent did not write — REFUTED;
* no RESULT, the controller's process exited by a status: the observation mechanism failed — HARNESS_FAILED;
* no RESULT, the controller's process exited by a signal: NON_CONTROLLER_SIGNAL (§9.3) unless the controller's own
  ledger holds the signal, which is an interruption;
* no RESULT at the window's end with the process still there (measured on the range, never assumed): SUBJECT_DEADLINE
  with the class's `ON_DEADLINE` verdict; the caller's `release` stops it — the probe never signals anything.
* no RESULT at the window's end, nothing left of the process and its exit status never reported: HARNESS_FAILED,
  unless the controller's ledger holds a stop — an interruption (C2-P2-FINDING-002: on Windows the controller's
  TerminateJobObject takes the range's anchor down with the job, so its own stop reports no exit status).

Before DISPATCHED the watchdog runs: an exit with no READY/DISPATCHED, or none within the watchdog, is HARNESS_FAILED
(UNRUNNABLE): the harness did not start or broke its protocol.

**Evaluation directory.** `python_callable._evaluation_dir` (fresh; refused inside the checkout): it holds the request,
the protocol file, the harness's own log, fresh empty bytecode caches for the controller and the subject's process
(`-X pycache_prefix`, with `-B` and `-I` on each command line — P7-FINDING-001), `tmp/`, the subject's temporary
directory (`TMPDIR`, `TEMP`, `TMP` — B6: never the host's), and `ws/`, the subject's workspace, working directory and
HOME. Both processes run with `python_callable._scrubbed_env` plus `LC_ALL=C.UTF-8`, `LANG=C.UTF-8`, `PYTHONUTF8=1`,
`TZ=UTC`, `HOME=<ws>`; because `-I` discards every `PYTHON*` variable, UTF-8 mode is pinned on the command line too
(`-X utf8=1`), the way the bytecode prefix is. The subject's process flushes the interpreter's original stdout/stderr
objects between invocations so each capture holds what its invocation wrote; it never writes to them.

**Enforcement: PARTIAL.** Weakest path (`WEAKEST_PATH`): the subject runs in a process of its own as the harness user,
with that user's filesystem and network; it can read the evaluation directory, never the key. The controller builds
every fact, from answers the subject's own process gives about itself, which that code can misreport (the section
above). `-I`, the scrubbed environment, the fresh working and temporary directories and the harness-owned bytecode caches are
isolation, not a sandbox.
"""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import sys
import tempfile
import time

from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.probe.protocol import (
    ExecutionEnv, HarnessProbe, Observation, ObservationKind, ProbeMetadata, RevisionRef,
)
from aisef2.probe.python_callable import (
    _COLLECT_S, _GRACE_S, _MARK, _WAIT_S, _after_dispatch, _evaluation_dir, _inside, _plain, _scrubbed_env,
    window_of,
)
from aisef2.runtime.process_range import ProcessRange, RangeError
from aisef2.product.contract import plain
from aisef2.product.spec import ProductProofSpec

PROBE_ID = "probe.cli_invocation"
#: Every file whose code decides what this probe observes is a source of its digest (§35) — measured, not assumed
#: (tests/v2/test_v21_probe_sources.py): the protocol and python_callable's frozen helpers it imports, this module
#: (the observation logic, and the AGENT and HARNESS scripts of its child processes), the product plane's `plain`,
#: `names_test_artefact` and `on_subject_absent` that `observe` and `run_probe` call, and the owned process range
#: with the anchor script it launches. A source is only hashed here: this tuple grants no access to anything.
PROBE_SOURCES = ("probe/protocol.py", "probe/python_callable.py", "probe/cli_invocation.py", "product/contract.py",
                 "product/outcome.py", "runtime/process_range.py", "runtime/range_anchor.py")
LOCATOR = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*")
CLASSES = ("exits", "exits_streams", "exits_files", "blocks", "equality")
#: Each class's meaning of an expired observation window (§9.2): what "not returned by W" says about the observable.
ON_DEADLINE = {"exits": BehaviorVerdict.REFUTED, "exits_streams": BehaviorVerdict.REFUTED,
               "exits_files": BehaviorVerdict.REFUTED, "blocks": BehaviorVerdict.SATISFIED,
               "equality": BehaviorVerdict.REFUTED}
#: DECISION-1: the quantifier semantics a class may declare (never "N examples passed => universal property proven").
QUANTIFIERS = ("exhaustive_finite_domain", "bounded_witness_measurement", "unsupported_for_full_enforcement")
COMPARATORS = ("bytes_equal", "json_equal")
_ONE = "the one declared invocation (argv, stdin, workspace, pre-steps): the domain is that invocation alone"
#: The class table: what each class measures, under which quantifier, and every (observation facts -> verdict) row
#: `verdict_of` / `ON_DEADLINE` answer (tests/v2/test_c2_cli_calibration.py exercises every row on fixture facts).
CLASS_TABLE = {
    "exits": {"quantifier": "exhaustive_finite_domain", "domain": _ONE, "enforcement": "PARTIAL", "rows": (
        ("window expired", "REFUTED"), ("pre-step failed", "REFUTED"),
        ("returned, exit code equal", "SATISFIED"), ("returned, exit code differs", "REFUTED"),
        ("hard exit, exit code equal", "SATISFIED"), ("hard exit, exit code differs", "REFUTED"))},
    "exits_streams": {"quantifier": "exhaustive_finite_domain", "domain": _ONE, "enforcement": "PARTIAL", "rows": (
        ("window expired", "REFUTED"), ("pre-step failed", "REFUTED"), ("returned, exit code differs", "REFUTED"),
        ("returned, exit code equal, every stream matches", "SATISFIED"),
        ("returned, exit code equal, a stream differs", "REFUTED"),
        ("returned, exit code equal, a truncated stream under an exact shape", "REFUTED"),
        ("hard exit, exit code equal, the captured streams match", "SATISFIED"))},
    "exits_files": {"quantifier": "exhaustive_finite_domain", "domain": _ONE, "enforcement": "PARTIAL", "rows": (
        ("window expired", "REFUTED"), ("pre-step failed", "REFUTED"), ("returned, exit code differs", "REFUTED"),
        ("returned, exit code equal, every file matches", "SATISFIED"),
        ("returned, exit code equal, a file differs", "REFUTED"),
        ("hard exit before the files were recorded, equals_before", "REFUTED"))},
    "blocks": {"quantifier": "bounded_witness_measurement", "enforcement": "PARTIAL", "rows": (
        ("window expired", "SATISFIED"), ("pre-step failed", "REFUTED"), ("returned", "REFUTED"),
        ("hard exit", "REFUTED")),
        "domain": "the declared window W witnesses that the invocation had not returned by W; it never proves that "
                  "it blocks forever"},
    "equality": {"quantifier": "bounded_witness_measurement", "enforcement": "PARTIAL", "rows": (
        ("window expired", "REFUTED"), ("pre-step failed in a half", "REFUTED"),
        ("both returned, exit codes equal, every stream equal", "SATISFIED"),
        ("both returned, exit codes differ", "REFUTED"), ("both returned, a stream differs", "REFUTED"),
        ("both returned, json_equal over equal documents in another order", "SATISFIED"),
        ("both returned, the declared newline and a trailing newline normalised away", "SATISFIED"),
        ("both returned, evaluation directories not distinct", "REFUTED")),
        "domain": "the two declared invocations witness equality; they never prove it for every run"},
}
WEAKEST_PATH = ("the subject runs in a process of its own, a child of the probe's controller, as the harness user with "
                "that user's filesystem and network access; it can read the evaluation directory but not the key that "
                "authenticates the protocol, and the controller alone builds the facts and writes the protocol -- from "
                "answers the subject's own process gives about itself (an exit code, a returned value), which code "
                "written to answer for itself, or to recognise that it is being probed, can misreport: the channel "
                "is protected, the truth of an answer is not; -I interpreter isolation, a scrubbed environment, "
                "fresh working and temporary directories and harness-owned bytecode caches (-X pycache_prefix, -B) "
                "are isolation, not a sandbox")
STREAM_CAP = 8 * 1024 * 1024   # bytes kept per captured stream; a subject may write more, the fact says truncated
STREAM_SHAPES = ("text", "contains", "regex", "lines", "first_word")
FILE_SHAPES = ("sha256", "text", "absent", "equals_before")
PLACEHOLDER = "<ws>"
POLL_S = 0.02   # how often the parent looks at the protocol file; it never decides content
DISPOSE_S = 10.0   # how long the disposal of a probe-owned evaluation directory waits out a sharing violation
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*(?:/[A-Za-z0-9_][A-Za-z0-9._-]*)*")
_HEX = re.compile(r"(?:[0-9a-fA-F]{2})*")
_SHA = re.compile(r"[0-9a-f]{64}")


def _probe_digest() -> str:
    root = pathlib.Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for rel in PROBE_SOURCES:
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


#: V2.1 (ARCHITECTURE-EXCEPTION-V2-007): three identities, no longer one. A spec binds the probe's CAPABILITY — its id,
#: this version and its observation classes — so a change to the bytes that does not change what any class observes
#: leaves every spec, approval and plan valid; such a change is bumped here by hand when it does change an observation
#: (a stimulus grammar, a verdict rule, a class's meaning). The bytes that run are EXECUTION_DIGEST: a calibration row
#: and the run's RunSpec bind them, so a byte change needs its calibrations demonstrated again before anything admits.
#: A matching digest is not evidence that two executions behave alike; the calibration contrast is the evidence.
CAPABILITY_VERSION = 1
EXECUTION_DIGEST = _probe_digest()
DIGEST = hashlib.sha256(json.dumps([PROBE_ID, CAPABILITY_VERSION, list(CLASSES)]).encode("utf-8")).hexdigest()


#: The worker of a `regex` stream shape (owner decision of 2026-10-15, item 4): a harness script that is given bytes and
#: a pattern and executes nothing of the subject. Started as `sys.executable -I -S -B -c REGEX_WORKER <request>
#: <result>`; stdlib only, no clock, nothing on stdout. `request` is one JSON line {pattern} then the stream's bytes;
#: `result` is `1` when the pattern is found in the utf-8 decoding (undecodable bytes replaced) and `0` when it is not.
REGEX_WORKER = r"""
import json, re, sys
with open(sys.argv[1], "rb") as f:
    head, _, data = f.read().partition(b"\n")
found = re.search(json.loads(head)["pattern"], data.decode("utf-8", "replace")) is not None
with open(sys.argv[2], "wb") as f:
    f.write(b"1" if found else b"0")
"""
#: The failures of that worker, each its own reason in the message (`regex search <REASON>: ...`): the vocabulary of
#: file_artifact's grep worker (PM-13), for the same kind of stop.
SEARCH_REASONS = ("DEADLINE", "LAUNCH", "CRASHED", "NO_RESULT", "BAD_RESULT", "INPUT")
_PATTERN_HEAD = 40       # characters of the pattern a DEADLINE names
_SEARCH_GRACE_S = (0.5, 0.5)   # the worker's range ladder once the search is over: it holds nothing to flush
#: The deadline clock of the worker, bound once to the function (as file_artifact's): not the observation window.
_monotonic = time.monotonic


#: What `_after_dispatch` is handed when it is asked only whether the controller stopped the worker's range (it returns
#: this, unused, when the ledger is empty, and raises `ProbeInterrupted` when it is not).
_SEARCH_STOPPED = Observation(ObservationKind.HARNESS_FAILED, detail="the regex search was interrupted")


class StreamSearchFailed(Exception):
    """The search a `regex` shape asks for gave no answer (module docstring): the harness could not tell whether the
    pattern is in the stream, so there is no verdict. `reason` is one of `SEARCH_REASONS` and opens the message."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"regex search {reason}: {message}")
        self.reason = reason


def search_in_worker(pattern: str, data: bytes, *, stream: str, work: str, name: str, timeout_s: float,
                     on_range=None) -> bool:
    """Whether `pattern` is found in `data` (utf-8, undecodable bytes replaced): the answer of `REGEX_WORKER`, under
    `timeout_s` for the whole operation — the request written, the worker started, run and answered, the result read.
    `work` is the evaluation directory and `name` the range's own; `stream` names the stream in a message. The caller
    holds nothing of the subject alive (`CliInvocationProbe._observe_in` decides after `release`): the request, the
    result and the worker's output are files of a directory made here, with a name nobody chose before, never of a
    name the subject could have planted. `on_range` is the harness's hook for the worker's process range (the story's
    scope releases it). Raises `StreamSearchFailed` for every way the worker gave no answer; the range is emptied before
    it returns either way (a range that will not empty raises RangeNotEmpty: a leak is never silent). A signal the
    controller sent to the worker's range is an interruption (§9.3, `ProbeInterrupted`), not a failure of the worker."""
    begun = _monotonic()
    try:
        home = tempfile.mkdtemp(prefix="regex-", dir=work)
        request, result, log = (os.path.join(home, n) for n in ("request", "result", "worker.log"))
        with open(request, "wb") as f:
            f.write(json.dumps({"pattern": pattern}).encode("ascii") + b"\n" + data)
        out = open(log, "wb")
    except OSError as e:
        raise StreamSearchFailed("INPUT", f"the request cannot be written ({type(e).__name__})") from None
    try:
        run = ProcessRange(name, [sys.executable, "-I", "-S", "-B", "-c", REGEX_WORKER, request, result], cwd=home,
                           env=_scrubbed_env(), output=out, grace_s=_SEARCH_GRACE_S, wait_s=_WAIT_S)
        run.start()
    except (RangeError, OSError) as e:
        raise StreamSearchFailed("LAUNCH", f"the worker did not start ({type(e).__name__})") from None
    finally:
        out.close()
    try:
        if on_range is not None:
            on_range(run)
        status = run.wait(max(0.0, timeout_s - (_monotonic() - begun)))
        elapsed = _monotonic() - begun
        _after_dispatch(run, _SEARCH_STOPPED)     # a signal in the ledger before this function's own release: §9.3
    finally:
        run.release()   # RangeNotEmpty / RangeEscaped propagate: a leak is never silent (§17.1)
    if status is None and elapsed < timeout_s:   # the range's report ended before the watchdog did: no exit status
        raise StreamSearchFailed("CRASHED", "the process range ended without reporting how the worker ended"
                                 + _said(log))
    if status is None or elapsed > timeout_s:    # the deadline is the whole operation: a late answer is no answer
        head = pattern[:_PATTERN_HEAD] + ("..." if len(pattern) > _PATTERN_HEAD else "")
        raise StreamSearchFailed(
            "DEADLINE", f"the search did not finish within the harness watchdog ({timeout_s:g}s: timeouts_s.probe) "
                        f"over {len(data)} bytes of the {stream} stream, against the pattern {head!r} "
                        f"({len(pattern)} characters); its process range was emptied and nothing was decided from "
                        "it, so this is a stop of the harness and never a verdict about the product. The same "
                        "pattern over the same bytes within the same deadline stops the same way: running it again "
                        "changes nothing. Simplify the pattern (no nested or overlapping quantifiers over the same "
                        "text) or raise timeouts_s.probe on purpose")
    if status != 0:
        how = f"ended by signal {-status}" if status < 0 else f"exited with status {status}"
        raise StreamSearchFailed("CRASHED", f"the worker {how} before it gave its result" + _said(log))
    try:
        with open(result, "rb") as f:
            said = f.read(2)     # an answer is one byte: a longer file is read for what it is, not whole
    except OSError:
        raise StreamSearchFailed("NO_RESULT", "the worker exited 0 and wrote no result" + _said(log)) from None
    if said not in (b"0", b"1"):
        raise StreamSearchFailed("NO_RESULT" if not said else "BAD_RESULT",
                                 "the worker exited 0 and its result is " + ("empty" if not said else
                                                                          "not an answer (0 or 1)"))
    return said == b"1"


def _said(log: str) -> str:
    """What the worker printed (its traceback, when it crashed), cut: the tail of its output file."""
    try:
        tail = pathlib.Path(log).read_bytes()[-300:].decode("utf-8", "replace").strip()
    except OSError:
        return ""
    return f": {tail!r}" if tail else ""


# --------------------------------------------------------------------------------------- shapes

def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _content_ok(c) -> bool:
    """A byte-exact content declaration: text with an explicit newline, or hex bytes."""
    if not isinstance(c, dict):
        return False
    if set(c) == {"bytes_hex"}:
        return isinstance(c["bytes_hex"], str) and _HEX.fullmatch(c["bytes_hex"]) is not None
    if set(c) in ({"text"}, {"text", "newline"}):
        return isinstance(c["text"], str) and ("newline" not in c or isinstance(c["newline"], str))
    return False


def _bytes_of(c) -> bytes:
    if "bytes_hex" in c:
        return bytes.fromhex(c["bytes_hex"])
    return c["text"].replace("\n", c.get("newline", "\n")).encode("utf-8")


def _name_ok(name) -> bool:
    """A workspace name: relative, forward slashes, no component starting with a dot (so never `..`)."""
    return isinstance(name, str) and _NAME.fullmatch(name) is not None


def _ws_key_ok(key) -> bool:
    return isinstance(key, str) and key.startswith(PLACEHOLDER + "/") and _name_ok(key[len(PLACEHOLDER) + 1:])


def _argv_ok(argv) -> bool:
    return isinstance(argv, list) and all(isinstance(a, str) for a in argv)


def _stimulus_ok(stim: dict) -> bool:
    if not set(stim) <= {"argv", "stdin", "workspace", "pre"} or not _argv_ok(stim.get("argv", [])):
        return False
    if stim.get("stdin") is not None and not _content_ok(stim["stdin"]):
        return False
    ws = stim.get("workspace", {})
    if not isinstance(ws, dict) or not all(_name_ok(n) and _content_ok(c) for n, c in ws.items()):
        return False
    pre = stim.get("pre", [])
    return isinstance(pre, list) and all(isinstance(p, dict) and set(p) == {"argv"} and _argv_ok(p["argv"])
                                         for p in pre)


def _compiles(pattern: str) -> bool:
    """Whether `re` takes the pattern. `re.compile` says no in three ways: `re.error` (a malformed pattern),
    `OverflowError` (a repetition count past the engine's) and `RecursionError` (groups nested past the compiler's).
    The pattern is a model's; an observable that names one `re` cannot take has no meaning, and is never an exception
    at the verdict (`_stream_matches`), which only ever searches with a pattern this accepted."""
    try:
        re.compile(pattern)
    except (re.error, OverflowError, RecursionError):
        return False
    return True


def _stream_shape_ok(shape) -> bool:
    if isinstance(shape, str):
        return True
    if not isinstance(shape, dict) or not shape:
        return False
    if "text" in shape:
        return _content_ok(shape)
    if len(shape) != 1:
        return False
    kind, v = next(iter(shape.items()))
    if kind not in STREAM_SHAPES:
        return False
    if kind == "contains":
        return isinstance(v, list) and bool(v) and all(isinstance(s, str) for s in v)
    if kind == "regex":
        return isinstance(v, str) and _compiles(v)
    if kind == "lines":
        return _is_int(v) and v >= 0
    return isinstance(v, str) and bool(v) and v.split() == [v]   # first_word: one word, no whitespace


def _file_shape_ok(shape) -> bool:
    if not isinstance(shape, dict) or not shape:
        return False
    if "text" in shape:
        return _content_ok(shape)
    if len(shape) != 1:
        return False
    kind, v = next(iter(shape.items()))
    if kind not in FILE_SHAPES:
        return False
    if kind == "sha256":
        return isinstance(v, str) and _SHA.fullmatch(v) is not None
    return kind in ("absent", "equals_before") and v is True


def _normalization_ok(n) -> bool:
    """The policy: an optional non-empty newline (what the subject writes, turned into LF) and an optional flag."""
    return isinstance(n, dict) and set(n) <= {"newline", "strip_trailing_newline"} \
        and ("newline" not in n or isinstance(n["newline"], str) and bool(n["newline"])) \
        and ("strip_trailing_newline" not in n or isinstance(n["strip_trailing_newline"], bool))


def _equality_ok(eq) -> bool:
    """DECISION-4 binds both stimuli, the normalization policy and the comparator: all four are declared."""
    if not isinstance(eq, dict) or set(eq) != {"stimulus_a", "stimulus_b", "normalization", "comparator"}:
        return False
    if not all(isinstance(eq[k], dict) and _stimulus_ok(eq[k]) for k in ("stimulus_a", "stimulus_b")):
        return False
    return _normalization_ok(eq["normalization"]) and eq["comparator"] in COMPARATORS


def _streams_ok(streams) -> bool:
    # names first: a set is built of the entries, and a list or a dict in it is unhashable — a TypeError out of a
    # classifier whose answer is a class or None, for a reproducer a model wrote
    return isinstance(streams, list) and bool(streams) and all(isinstance(s, str) for s in streams) \
        and len(set(streams)) == len(streams) and set(streams) <= {"stdout", "stderr"}


def observation_class(observable, stimulus) -> str | None:
    """The class a spec's observable asks for, or None when this probe cannot give it a meaning."""
    if window_of(observable) is None:
        return None
    obs = {k: v for k, v in plain(dict(observable)).items() if k != "within_s"}
    stim = plain(dict(stimulus))
    if not _stimulus_ok(stim):
        return None
    if set(obs) == {"equality", "streams"}:
        return "equality" if stim == {} and _streams_ok(obs["streams"]) and _equality_ok(obs["equality"]) else None
    if set(obs) == {"blocks"}:
        return "blocks" if obs["blocks"] is True else None
    if not _is_int(obs.get("exit_code")):
        return None
    extra = set(obs) - {"exit_code"}
    if not extra:
        return "exits"
    if extra and extra <= {"stdout", "stderr"} and all(_stream_shape_ok(obs[k]) for k in extra):
        return "exits_streams"
    if extra == {"files"} and isinstance(obs["files"], dict) and obs["files"] \
            and all(_ws_key_ok(k) and _file_shape_ok(v) for k, v in obs["files"].items()):
        return "exits_files"
    return None


def spec_class(spec: ProductProofSpec) -> str | None:
    """Harness metadata (`ProbeMetadata.observation_class`): the class `spec` asks of this probe, or None."""
    subject = dict(spec.probe_input["subject"])
    if subject.get("kind") != "cli_invocation" or not isinstance(subject.get("locator"), str) \
            or not LOCATOR.fullmatch(subject["locator"]):
        return None
    return observation_class(spec.probe_input["observable"], spec.probe_input["stimulus"])


# --------------------------------------------------------------------------------------- verdicts

def _sha_file(path: str, limit: int | None = None) -> str:
    h = hashlib.sha256()
    if os.path.isfile(path):
        with open(path, "rb") as f:
            left = limit
            while left is None or left > 0:
                chunk = f.read(1 << 20 if left is None else min(1 << 20, left))
                if not chunk:
                    break
                h.update(chunk)
                if left is not None:
                    left -= len(chunk)
    return h.hexdigest()


def _stream_fact(path: str) -> dict:
    """What a capture file holds, for the hard-exit rule: the same shape the child reports, capped."""
    size = os.path.getsize(path) if os.path.isfile(path) else 0
    return {"path": path, "size": min(size, STREAM_CAP), "truncated": size > STREAM_CAP,
            "sha256": _sha_file(path, STREAM_CAP)}


def _file_fact(path: str) -> dict:
    return {"sha256": _sha_file(path)} if os.path.isfile(path) else {"absent": True}


def _stream_bytes(fact: dict) -> bytes:
    """The bytes a stream's facts name: the first `size` bytes of its capture file (at most STREAM_CAP)."""
    path = fact.get("path", "")
    if not os.path.isfile(path):
        return b""
    with open(path, "rb") as f:
        return f.read(min(int(fact.get("size", 0)), STREAM_CAP))


def _stream_matches(shape, fact: dict, search=None, stream: str = "") -> bool:
    """Whether the bytes `fact` names match `shape`. A `regex` shape is searched by `search(pattern, data, stream)` — the
    probe's own is `search_in_worker`, which may raise `StreamSearchFailed` — and by nothing else: there is no search of
    a data-supplied pattern in this process to fall back to (a caller that forgets to give one is a `TypeError`, not an
    unbounded `re.search`). A caller that holds no harness (the class table's fixture facts) gives its own."""
    data = _stream_bytes(fact)
    if isinstance(shape, str):
        shape = {"text": shape}
    if "text" in shape:
        return not fact.get("truncated") and data == _bytes_of(shape)
    if "contains" in shape:
        return all(s.encode("utf-8") in data for s in shape["contains"])
    if "regex" in shape:
        if search is None:
            raise TypeError("a regex shape is searched by the harness's bounded search: none was given")
        return search(shape["regex"], data, stream)
    if "lines" in shape:
        return len(data.splitlines()) == shape["lines"]
    words = data.split(None, 1)
    return bool(words) and words[0].decode("utf-8", "replace") == shape["first_word"]


def _file_matches(shape: dict, after: dict | None, before: dict | None) -> bool:
    if "text" in shape:
        return after is not None and after.get("sha256") == hashlib.sha256(_bytes_of(shape)).hexdigest()
    if "sha256" in shape:
        return after is not None and after.get("sha256") == shape["sha256"]
    if "absent" in shape:
        return after is not None and after.get("absent") is True
    return after is not None and before is not None and after == before


def _normalize(data: bytes, policy: dict) -> bytes:
    """The declared normalization: the policy's newline becomes LF; one trailing LF is dropped when asked."""
    data = data.replace(policy.get("newline", "\n").encode("utf-8"), b"\n")
    if policy.get("strip_trailing_newline") and data.endswith(b"\n"):
        data = data[:-1]
    return data


def _equal(a: bytes, b: bytes, comparator: str) -> bool:
    if comparator == "json_equal":
        try:
            return json.loads(a.decode("utf-8")) == json.loads(b.decode("utf-8"))
        except (ValueError, RecursionError):
            # a JSON error or a decoding error (UnicodeDecodeError is one) — or a document nested past what the parser
            # (~1,000 levels on 3.11, ~10,000 on 3.12) or the comparison ("Stack overflow in comparison") can take:
            # the streams are the candidate's, and what is no document this comparator can read is not equal. It is
            # never UNVERIFIABLE: a candidate would then make its own output undecidable by nesting it.
            return False
    return a == b


def _half_ok(half: dict) -> bool:
    return half.get("pre_failed") is None and "exit_code" in half


def _equality_verdict(obs: dict, facts: dict) -> BehaviorVerdict:
    eq = obs["equality"]
    a, b = facts.get("a", {}), facts.get("b", {})
    ok = facts.get("distinct_evaluation_directories") is True and _half_ok(a) and _half_ok(b) \
        and a["exit_code"] == b["exit_code"]
    policy, comparator = eq["normalization"], eq["comparator"]
    ok = ok and all(_equal(_normalize(_stream_bytes(a.get(s, {})), policy),
                           _normalize(_stream_bytes(b.get(s, {})), policy), comparator) for s in obs["streams"])
    return BehaviorVerdict.SATISFIED if ok else BehaviorVerdict.REFUTED


def verdict_of(cls: str, observable, facts: dict, search=None) -> BehaviorVerdict:
    """What a present subject's facts say about the observable, when the invocation returned (or ended the process)
    before the window closed. Pure over the facts and the capture files they name; no clock. `search` is how a `regex`
    shape is searched (`_stream_matches`), required by any observable that holds one: `observe` always gives the
    bounded one, and what it raises (`StreamSearchFailed`) is no verdict — `_Later.settle` makes it HARNESS_FAILED."""
    if cls == "equality":
        return _equality_verdict(dict(observable), facts)
    if facts.get("pre_failed") is not None or cls == "blocks":
        return BehaviorVerdict.REFUTED   # the state was never built; or blocks: the invocation returned
    obs = dict(observable)
    ok = facts.get("exit_code") == obs["exit_code"]
    if cls == "exits_streams":
        ok = ok and all(_stream_matches(obs[k], facts.get(k, {}), search, k) for k in ("stdout", "stderr") if k in obs)
    elif cls == "exits_files":
        after, before = facts.get("files", {}), facts.get("before", {})
        ok = ok and all(_file_matches(shape, after.get(_ws_name(k)), before.get(_ws_name(k)))
                        for k, shape in obs["files"].items())
    return BehaviorVerdict.SATISFIED if ok else BehaviorVerdict.REFUTED


def _ws_name(key: str) -> str:
    return key[len(PLACEHOLDER) + 1:]


def _substitute(argv: list, ws: str) -> list[str]:
    """`<ws>` at the head of an argv entry becomes the workspace's absolute path; nothing else is substituted."""
    out = []
    for a in argv:
        if a == PLACEHOLDER or a.startswith(PLACEHOLDER + "/"):
            out.append(os.path.join(ws, *a[len(PLACEHOLDER) + 1:].split("/")) if a != PLACEHOLDER else ws)
        else:
            out.append(a)
    return out


def _public(facts: dict) -> dict:
    """The facts as recorded in `detail`: without the capture paths (the evaluation directory is disposed)."""
    out = {}
    for k, v in facts.items():
        if isinstance(v, dict):
            out[k] = _public(v) if k not in ("stdout", "stderr") else {x: y for x, y in v.items() if x != "path"}
        elif isinstance(v, list):
            out[k] = [_public(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


#: B1 (V2.0 release charter §7) — the subject's process. Every line of developer code a probe executes runs here and
#: nowhere else: on the controller's request this script imports the subject, resolves, constructs, calls or invokes
#: it, and answers with what that one operation did — never a fact about the observable, never a protocol line. It
#: holds no reference to the protocol file, the nonce or the key: its channel to the controller is a pair of pipes
#: (each answer echoes its request's number), and the subject's own standard streams are files of the evaluation
#: directory. Shared by every probe that executes a subject (cli_invocation, process_effect, python_callable_v2).
AGENT = r'''
import builtins, importlib, json, os, runpy, sys, traceback
root = os.path.realpath(sys.argv[1])
work = sys.argv[2]
sys.path[:0] = [p for p in (root, os.path.join(root, "src")) if os.path.isdir(p)]
BINARY = getattr(os, "O_BINARY", 0)
RIN = os.fdopen(os.dup(0), "rb")
WOUT = os.dup(1)
for s in (sys.__stdin__, sys.__stdout__, sys.__stderr__):
    if s is not None:
        s.reconfigure(newline="\n")
def flush():
    for s in (sys.__stdout__, sys.__stderr__):
        try:
            s.flush()
        except (OSError, ValueError):
            pass
def redirect(stdin_path, out_path, err_path):
    flush()
    for fd, path, flags in ((0, stdin_path, os.O_RDONLY), (1, out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC),
                            (2, err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)):
        h = os.open(path, flags | BINARY)
        os.dup2(h, fd)
        os.close(h)
redirect(os.devnull, os.path.join(work, "stdout.bin"), os.path.join(work, "stderr.bin"))
def send(answer):
    data = (json.dumps(answer) + "\n").encode("utf-8")
    while data:
        data = data[os.write(WOUT, data):]
class Leak(Exception):
    pass
def tagged(value):
    if isinstance(value, (bytes, bytearray)):
        return {"bytes_hex": bytes(value).hex()}
    if isinstance(value, memoryview):
        return {"memoryview_hex": bytes(value).hex()}
    try:
        return {"json": json.loads(json.dumps(value))}
    except Exception:
        return {"unserializable": type(value).__name__}
def plain(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)
STATE = {"module": None, "subject": None, "instance": None, "constructed": False}
def op_import(r):
    try:
        mod = importlib.import_module(r["name"])
    except ModuleNotFoundError as e:
        return {"raised": "ModuleNotFoundError", "missing": e.name}
    except BaseException as e:
        return {"raised": type(e).__name__}
    STATE["module"] = mod
    own = vars(mod)   # the module's own namespace: a module-level __getattr__ of the subject is never asked
    return {"ok": True, "file": own.get("__file__"), "path": [str(p) for p in own.get("__path__") or []]}
def op_resolve(r):
    obj = STATE["module"]
    for a in r["chain"]:
        try:
            obj = getattr(obj, a)
        except AttributeError:
            return {"absent": True}
        except BaseException as e:
            return {"raised": type(e).__name__}
    STATE["subject"] = obj
    return {"ok": True, "callable": callable(obj)}
def op_value(r):
    return tagged(STATE["subject"])
def op_construct(r):
    try:
        STATE["instance"] = STATE["subject"](*r["args"], **r["kwargs"])
    except BaseException as e:
        return {"raised": type(e).__name__}
    STATE["constructed"] = True
    return {"ok": True}
def guarded(patch, fired, call):
    if patch is None:
        return call()
    module, target, error, fault_id = patch
    owner = importlib.import_module(module)
    original, kind = getattr(owner, target), getattr(builtins, error)
    def fault(*args, **kwargs):
        if fired:
            return original(*args, **kwargs)
        fired.append(fault_id)
        raise kind("controlled fault " + fault_id)
    setattr(owner, target, fault)
    try:
        return call()
    finally:
        setattr(owner, target, original)
        if getattr(owner, target) is not original:
            raise Leak("the fault " + fault_id + " was not restored")
def op_call(r):
    base = STATE["instance"] if STATE["constructed"] else STATE["subject"]
    fn = base
    if "method" in r:
        try:
            fn = getattr(base, r["method"])
        except AttributeError:
            return {"no_method": True}
        except BaseException as e:
            return {"resolve_raised": type(e).__name__}
    fired = []
    try:
        out = {"returned": tagged(guarded(r.get("patch"), fired, lambda: fn(*r["args"], **r["kwargs"])))}
    except Leak as e:
        return {"leak": str(e)}
    except BaseException as e:
        out = {"raised": type(e).__name__, "attrs": {}}
        for a in r.get("attrs", []):
            try:
                out["attrs"][a] = tagged(getattr(e, a))
            except AttributeError:
                out["attrs"][a] = {"missing": True}
            except BaseException as x:
                out["attrs"][a] = {"error": type(x).__name__}
    out["fired"] = bool(fired)
    return out
def op_invoke(r):
    redirect(r["stdin"], r["out"], r["err"])
    name, attr = r["name"], r["attr"]
    sys.argv = [name] + list(r["argv"])
    raw, raised = None, None
    try:
        if attr == "__main__":
            runpy.run_module(name, run_name="__main__", alter_sys=True)
        else:
            mod = importlib.import_module(name)
            try:
                fn = getattr(mod, attr)
            except AttributeError:
                return {"absent": True}
            raw = fn(list(r["argv"]))
    except SystemExit as e:
        raw = e.code
    except BaseException as e:
        raised = type(e).__name__
        traceback.print_exc(file=sys.stderr)
    if raised is not None:
        code = 1
    elif raw is None:
        code = 0
    elif isinstance(raw, int):
        code = int(raw)
    else:
        code = 1
        print(raw, file=sys.stderr)
    flush()
    return {"raw": plain(raw), "code": code, "raised": raised}
def op_bye(r):
    return {}
OPS = {"import": op_import, "resolve": op_resolve, "value": op_value, "construct": op_construct, "call": op_call,
       "invoke": op_invoke, "bye": op_bye}
send({"ready": True, "n": 0})
for line in RIN:
    request = json.loads(line)
    try:
        answer = OPS[request["op"]](request)
    except BaseException as e:
        answer = {"agent_failure": type(e).__name__}
    answer["n"] = request["n"]
    send(answer)
'''

#: The harness script — the controller (B1). Probe-owned; runs in `-I` mode and never imports, constructs, calls or
#: invokes the subject, nor puts the revision on its own path: it starts the subject's process (AGENT) before
#: DISPATCHED, asks it for one operation at a time, builds every fact itself from those answers and from the files it
#: reads, and alone writes the protocol — to the marker file named in the request, each line authenticated with the
#: evaluation's key (HMAC-SHA256). The key and the nonce leave the request file before the subject's process exists.
HARNESS = r'''
import hashlib, hmac, json, os, queue, subprocess, sys, threading
from importlib.machinery import PathFinder
ask_path = sys.argv[1]
req = json.loads(open(ask_path, encoding="utf-8").read())
with open(ask_path, "w", encoding="utf-8") as f:
    f.write("{}")
KEY, nonce = bytes.fromhex(req["key"]), req["nonce"]
root, work, ws, cap = os.path.realpath(req["root"]), req["work"], req["ws"], req["cap"]
name, _, attr = req["locator"].partition(":")
SEARCH = [p for p in (root, os.path.join(root, "src")) if os.path.isdir(p)]
proto = open(req["protocol"], "wb")
def emit(tag, body=""):
    mac = hmac.new(KEY, (tag + "\n" + body).encode("utf-8"), hashlib.sha256).hexdigest()
    proto.write((req["mark"] + " " + tag + " " + nonce + " " + mac + (" " + body if body else "") + "\n").encode("utf-8"))
    proto.flush()
    os.fsync(proto.fileno())
said = threading.Lock()
held = [False]
def settle():
    # one RESULT: the facts, or — when the subject's window ends first — the controller's own deadline (B1: the
    # verdict never rests on the range merely being alive; a controller that is stopped reports nothing). The race is
    # settled when the observed operation ANSWERS, never after the closing exchange: a subject that stalls once it
    # has answered cannot turn its answer into a deadline (B1-BLOCKS-STOP-001, IR-01)
    if not held[0]:
        held[0] = said.acquire(blocking=False)
    return held[0]
def conclude(facts):
    if said.acquire(blocking=False):
        emit("RESULT", json.dumps(facts))
        emit("END")
def deadline():
    timer = threading.Timer(req["window"], conclude, ({"deadline": True},))
    timer.daemon = True
    timer.start()
emit("READY")
agent = subprocess.Popen([req["interpreter"], "-I", "-S", "-B", "-X", "pycache_prefix=" + req["agent_pycache"], "-X", "utf8=1",
                          "-c", req["agent"], root, work], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=open(os.path.join(work, "agent.log"), "wb"), cwd=req["cwd"], env=req["env"])
replies = queue.Queue()
def pump():
    for line in agent.stdout:
        replies.put(line)
    replies.put(None)
threading.Thread(target=pump, daemon=True).start()
sent = [0]
def answer_to(n):
    line = replies.get()
    if line is None:
        return None
    try:
        got = json.loads(line)
    except ValueError:
        got = None
    if not isinstance(got, dict) or got.get("n") != n:
        return {"tampered": "an answer on the subject's channel is not the agent's"}
    return got
def ask(op):
    sent[0] += 1
    op["n"] = sent[0]
    try:
        agent.stdin.write((json.dumps(op) + "\n").encode("utf-8"))
        agent.stdin.flush()
    except OSError:
        pass
    return answer_to(sent[0])
def finish():
    got = ask({"op": "bye"})
    if got is not None and (set(got) != {"n"} or not replies.empty()):
        return "an answer on the subject's channel is not the agent's"
    return None
def inside(spec):
    places = [spec.origin] if spec.origin and spec.has_location else list(spec.submodule_search_locations or [])
    return any(os.path.realpath(p).startswith(root + os.sep) for p in places)
def resolve(dotted, search):
    parts, spec, path = dotted.split("."), None, search
    for i in range(len(parts)):
        # a finder looks a component up by its own name within the parent's locations: the dotted name would make an
        # implicit namespace portion read sys.modules[parent].__path__, which this process (it never imports the
        # subject) does not hold
        spec = PathFinder.find_spec(parts[i], path)
        if spec is None:
            return None
        path = spec.submodule_search_locations
        if path is None and i + 1 < len(parts):
            return None
    return spec
def sha(path):
    h = hashlib.sha256()
    if os.path.isfile(path):
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()
def file_fact(rel):
    path = os.path.join(ws, *rel.split("/"))
    return {"sha256": sha(path)} if os.path.isfile(path) else {"absent": True}
def stream_fact(path):
    size = os.path.getsize(path) if os.path.isfile(path) else 0
    if size > cap:
        os.truncate(path, cap)
    return {"path": path, "size": min(size, cap), "truncated": size > cap, "sha256": sha(path)}
def invoke(argv, stdin_path, out_path, err_path):
    got = ask({"op": "invoke", "name": name, "attr": attr, "argv": argv, "stdin": stdin_path, "out": out_path,
               "err": err_path})
    if got is None or "tampered" in got:
        return got
    if got.get("absent"):
        return {"subject": "absent"}
    return {"exit_status_raw": got["raw"], "exit_code": got["code"], "raised": got["raised"],
            "stdout": stream_fact(out_path), "stderr": stream_fact(err_path)}
def ended():
    code = agent.wait()
    return {"subject_signal": -code} if code < 0 else {"subject": "present", "exit_code": code, "hard_exit": True}
def main():
    if answer_to(0) is None:
        return None
    emit("DISPATCHED")
    deadline()
    spec = resolve(name, SEARCH)
    if spec is None and PathFinder.find_spec(name.split(".")[0], SEARCH) is None:
        spec = resolve(name, None)   # the revision is not on this process's path: where else the name resolves
    if attr == "__main__" and spec is not None and spec.submodule_search_locations is not None:
        spec = PathFinder.find_spec("__main__", spec.submodule_search_locations)
    if spec is None or not inside(spec):
        return {"subject": "absent", "note": "" if spec is None else "resolves only outside the revision"}
    pre = []
    for i, step in enumerate(req["pre"]):
        emit("PRE", str(i))
        r = invoke(step["argv"], os.devnull, os.path.join(work, "pre" + str(i) + ".stdout.bin"),
                   os.path.join(work, "pre" + str(i) + ".stderr.bin"))
        if r is None:
            r = ended()
            if "subject_signal" in r:
                return r
            r["pre_failed"] = i
            return r
        if "tampered" in r:
            return {"subject": "present", "tampered": r["tampered"]}
        if r.get("subject") == "absent":
            return r
        pre.append(r)
        if r["exit_code"] != 0:
            return {"subject": "present", "pre_failed": i, "pre": pre}
    before = {n: file_fact(n) for n in req["files"]}
    emit("MAIN", json.dumps({"before": before}))
    out, err = os.path.join(work, "stdout.bin"), os.path.join(work, "stderr.bin")
    r = invoke(req["argv"], req["stdin"] or os.devnull, out, err)
    if not settle():
        return None     # the deadline was written first: it stands
    if r is None:
        r = ended()
        if "subject_signal" not in r:
            r.update({"stdout": stream_fact(out), "stderr": stream_fact(err), "before": before,
                      "files": {n: file_fact(n) for n in req["files"]}})
        return r
    if "tampered" in r:
        return {"subject": "present", "tampered": r["tampered"]}
    if r.get("subject") == "absent":
        return r
    r.update({"subject": "present", "pre": pre, "before": before, "files": {n: file_fact(n) for n in req["files"]}})
    return r
facts = main()
if facts is not None and settle():
    if not ("subject_signal" in facts or "tampered" in facts or facts.get("hard_exit")):
        wrong = finish()
        if wrong is not None:
            facts = {"subject": "present", "tampered": wrong}
    emit("RESULT", json.dumps(facts))
    emit("END")
try:
    agent.stdin.close()
except OSError:
    pass
'''

def _harness_argv(interpreter: str, ask: str, pycache: str) -> list[str]:
    """The harness command line: isolated mode, no bytecode written, the bytecode cache under a fresh prefix and UTF-8
    mode — each on the command line, because `-I` discards every PYTHON* variable (P7-FINDING-001)."""
    return [interpreter, "-I", "-S", "-B", "-X", f"pycache_prefix={pycache}", "-X", "utf8=1", "-c", HARNESS, ask]


def _child_env(ws: str, tmp: str | None = None) -> dict:
    env = {**_scrubbed_env(), "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "PYTHONUTF8": "1", "TZ": "UTC",
           "HOME": ws, "USERPROFILE": ws}
    if tmp is not None:     # B6 (V2.0 release charter §7): the subject's temporary files are the evaluation's own
        env.update({"TMPDIR": tmp, "TEMP": tmp, "TMP": tmp})
    return env


def _mac(key: bytes, tag: str, body: str) -> str:
    """B1: the authentication of one protocol line — HMAC-SHA256 of its tag and body under the evaluation's key, which
    only the parent and the controller hold."""
    return hmac.new(key, (tag + "\n" + body).encode("utf-8"), hashlib.sha256).hexdigest()


def _protocol(path: str, nonce: str, key: str) -> dict[str, list[str]]:
    """The authentic protocol lines the marker file holds now, tag -> bodies in order: complete lines only (an
    unterminated last line is not one), carrying the mark, this evaluation's nonce and the line's authentication under
    this evaluation's key (B1). A line anything else wrote — the subject reading the nonce from this file included —
    is not one."""
    try:
        data = pathlib.Path(path).read_bytes()
    except OSError:
        return {}
    k = bytes.fromhex(key)
    out: dict[str, list[str]] = {}
    for raw in data.split(b"\n")[:-1]:
        parts = raw.decode("utf-8", "replace").rstrip("\r").split(" ", 4)
        if len(parts) >= 4 and parts[0] == _MARK and parts[2] == nonce:
            body = parts[4] if len(parts) == 5 else ""
            if hmac.compare_digest(parts[3], _mac(k, parts[1], body)):
                out.setdefault(parts[1], []).append(body)
    return out


def _await(run, path: str, nonce: str, key: str, tag: str, until: float) -> tuple[str, dict]:
    """Poll the marker file until a `tag` line is in it ("LINE"), the range reports the process's exit ("EXITED" —
    the file read once more, to its end, first: §9.4) or `until` passes ("TIMEOUT"). The poll never decides content."""
    while True:
        seen = _protocol(path, nonce, key)
        if tag in seen:
            return "LINE", seen
        if run.wait(0.0) is not None:
            seen = _protocol(path, nonce, key)
            return ("LINE" if tag in seen else "EXITED"), seen
        left = until - time.monotonic()
        if left <= 0:
            return "TIMEOUT", seen
        time.sleep(min(POLL_S, left))


class CliInvocationProbe(HarnessProbe):
    id = PROBE_ID
    digest = DIGEST
    execution_digest = EXECUTION_DIGEST

    def __init__(self, on_range=None, scratch: str | None = None) -> None:
        """`on_range` and `scratch` as python_callable: harness-owned hooks — the range is acquired into the story's
        StoryScope (its ledger is the one signal authority, §9.3), and each evaluation gets a fresh directory under
        the controller-owned scratch, or a temporary directory of its own."""
        self._on_range, self._scratch = on_range, scratch

    def enforcement(self) -> Enforcement:
        return Enforcement.PARTIAL

    def harness_preconditions(self) -> tuple[str, ...]:
        return ("interpreter: the ExecutionEnv's Python interpreter exists and launches under -I",
                "checkout: the revision's checkout is a readable directory",
                "evaluation directory: creatable, outside the checkout, with the workspace and the bytecode cache",
                "protocol: the harness writes READY, then DISPATCHED before the first invocation, to the marker "
                "file within the harness watchdog (ExecutionEnv.timeout_s)")

    def observe(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> Observation:
        pi = spec.probe_input
        subject = dict(pi["subject"])
        if subject.get("kind") != "cli_invocation":
            return Observation(ObservationKind.UNSUPPORTED, detail=f"subject kind {subject.get('kind')!r} is not "
                                                                   "cli_invocation")
        if not isinstance(subject.get("locator"), str) or not LOCATOR.fullmatch(subject["locator"]):
            return Observation(ObservationKind.UNSUPPORTED, detail=f"locator {subject.get('locator')!r} is not "
                                                                   "module.path:__main__ or module.path:callable — "
                                                                   "a path or a console script is never accepted")
        cls = spec_class(spec)
        if cls is None:
            return Observation(ObservationKind.UNSUPPORTED, detail="observable/stimulus is not a supported class "
                                                                   f"{CLASSES} with a bounded window (within_s); "
                                                                   "refused, not degraded")
        observable = plain(dict(pi["observable"]))
        if cls == "equality":
            return self._observe_equality(spec.id, subject["locator"], observable, at, env)
        return self._observe(spec.id, cls, subject["locator"], plain(dict(pi["stimulus"])), observable, at, env)[0]

    def _observe(self, spec_id: str, cls: str, locator: str, stim: dict, observable, at: RevisionRef,
                 env: ExecutionEnv) -> tuple[Observation, dict | None]:
        """One invocation of the subject in a fresh evaluation directory: the observation and, when the harness
        reported, the facts it reported (capture paths included; they are gone when this returns)."""
        failed = _preflight(at, env)
        if failed is not None:
            return failed, None
        try:
            holder = _evaluation_dir(self._scratch)
        except OSError as e:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"the evaluation directory cannot be created: "
                                                                     f"{type(e).__name__}"), None
        with _disposed(holder) as work:
            def search(pattern: str, data: bytes, stream: str) -> bool:
                return search_in_worker(pattern, data, stream=stream, work=work, timeout_s=env.timeout_s,
                                        name=f"probe {spec_id} regex {stream}", on_range=self._on_range)
            return self._observe_in(work, spec_id, cls, locator, stim, observable, at, env,
                                    lambda facts: functools.partial(verdict_of, cls, observable, facts, search))

    def _observe_equality(self, spec_id: str, locator: str, observable: dict, at: RevisionRef,
                          env: ExecutionEnv) -> Observation:
        """DECISION-4: two independent invocations, two fresh evaluation directories, one comparison of the
        normalised captures. A half that is not a returned invocation is the observation."""
        failed = _preflight(at, env)
        if failed is not None:
            return failed
        eq, window = observable["equality"], {"within_s": observable["within_s"]}
        try:
            holder_a, holder_b = _evaluation_dir(self._scratch), _evaluation_dir(self._scratch)
        except OSError as e:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"the evaluation directory cannot be created: "
                                                                     f"{type(e).__name__}")
        with _disposed(holder_a) as work_a, _disposed(holder_b) as work_b:
            halves = {}
            for side, work in (("a", work_a), ("b", work_b)):
                o, facts = self._observe_in(work, f"{spec_id}/{side}", "equality", locator, eq[f"stimulus_{side}"],
                                            window, at, env,
                                            lambda f: BehaviorVerdict.SATISFIED if _half_ok(f) else BehaviorVerdict.REFUTED)
                if o.kind is not ObservationKind.OBSERVED or o.verdict is BehaviorVerdict.REFUTED:
                    return o   # absent, expired (REFUTED), a signal, a harness failure, a failed pre-step: the observation
                halves[side] = facts
            facts = {"subject": "present", "a": halves["a"], "b": halves["b"],
                     "distinct_evaluation_directories": os.path.realpath(work_a) != os.path.realpath(work_b)}
            return Observation(ObservationKind.OBSERVED, verdict_of("equality", observable, facts),
                               detail=json.dumps(_public(facts)))

    def _observe_in(self, work: str, spec_id: str, cls: str, locator: str, stim: dict, observable, at: RevisionRef,
                    env: ExecutionEnv, decide) -> tuple[Observation, dict | None]:
        """One invocation inside the evaluation directory `work`; `decide` maps the reported facts to the verdict, or to a
        function that gives it (`_Later`): that one runs after the subject's range is released, so nothing of the subject
        is alive while the harness reads what it left and starts the worker of a pattern's search."""
        if _inside(work, at.root):
            return Observation(ObservationKind.HARNESS_FAILED, detail="the evaluation directory lies inside the "
                                                                     "revision checkout: refused"), None
        nonce, key = secrets.token_hex(16), secrets.token_hex(32)
        files = [_ws_name(k) for k in dict(observable).get("files", {})]   # a frozen observable's keys are sorted
        try:
            ask, ws, pycache = _prepare(work, at.root, locator, stim, files, nonce, key, env.interpreter,
                                        window_of(observable))
            log = open(os.path.join(work, "harness.log"), "wb")  # closed once the range has started
        except OSError as e:
            return Observation(ObservationKind.HARNESS_FAILED, detail="the evaluation directory cannot be "
                                                                     f"prepared: {type(e).__name__}"), None
        try:
            run = ProcessRange(f"probe {spec_id}", _harness_argv(env.interpreter, ask, pycache), cwd=ws,
                               env=_child_env(ws), output=log, grace_s=_GRACE_S, wait_s=_WAIT_S)
            try:
                run.start()
                if self._on_range is not None:
                    self._on_range(run)
            except (RangeError, OSError) as e:
                return Observation(ObservationKind.HARNESS_FAILED, detail=f"the harness cannot launch: "
                                                                         f"{type(e).__name__}"), None
        finally:
            log.close()
        try:
            observed, facts = _watch(run, os.path.join(work, "protocol.log"), nonce, key, cls, window_of(observable), env,
                                     decide)
        finally:
            run.release()  # RangeNotEmpty / RangeEscaped propagate: a leak is never silent (§17.1)
        if isinstance(observed, _Later):
            observed = observed.settle()
            facts = facts if observed.kind is ObservationKind.OBSERVED else None
        return observed, facts


@contextlib.contextmanager
def _disposed(holder):
    """The evaluation directory, disposed when the evaluation ends (C2-P2-FINDING-003). The range is released
    before this runs, so no member is alive; on Windows a member the controller's TerminateJobObject just ended
    can still hold its working directory and inherited handles inside the directory for a moment, and the
    disposal meets a sharing violation. It is retried until `DISPOSE_S` has passed, then raised: a directory that
    stays in use is a leak, never silent. A controller-owned scratch is not disposed here (StoryScope does it)."""
    work = holder.__enter__()
    try:
        yield work
    finally:
        until = time.monotonic() + DISPOSE_S
        while True:
            try:
                holder.__exit__(None, None, None)
                break
            except PermissionError:
                if time.monotonic() >= until:
                    raise
                time.sleep(POLL_S)


def _preflight(at: RevisionRef, env: ExecutionEnv) -> Observation | None:
    """What must function for the probe to look at all (harness preconditions 1 and 2)."""
    if not os.path.isfile(env.interpreter):
        return Observation(ObservationKind.HARNESS_FAILED, detail=f"interpreter absent: {env.interpreter}")
    if not os.path.isdir(at.root):
        return Observation(ObservationKind.HARNESS_FAILED, detail="cannot inspect: the revision checkout is missing")
    return None


def _prepare(work: str, root: str, locator: str, stim: dict, files: list[str], nonce: str, key: str,
             interpreter: str, window: float) -> tuple[str, str, str]:
    """Lay out the evaluation directory: the workspace with its byte-exact files, the stdin file, the fresh bytecode
    caches (the controller's and the subject process's), the evaluation's own temporary directory and the request.
    Returns (request path, workspace, bytecode prefix)."""
    ws, pycache, agent_pycache, tmp = (os.path.join(work, n) for n in ("ws", "pycache", "pycache-agent", "tmp"))
    for d in (ws, pycache, agent_pycache, tmp):
        os.mkdir(d)     # fresh and empty: no other evaluation's bytecode, and none from the checkout
    for name, content in stim.get("workspace", {}).items():
        target = pathlib.Path(ws, *name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_bytes_of(content))
    stdin = None
    if stim.get("stdin") is not None:
        stdin = os.path.join(work, "stdin.bin")
        pathlib.Path(stdin).write_bytes(_bytes_of(stim["stdin"]))
    request = {"mark": _MARK, "nonce": nonce, "key": key, "root": root, "locator": locator, "work": work, "ws": ws,
               "protocol": os.path.join(work, "protocol.log"), "cap": STREAM_CAP,
               "argv": _substitute(list(stim.get("argv", [])), ws), "stdin": stdin,
               "pre": [{"argv": _substitute(list(p["argv"]), ws)} for p in stim.get("pre", [])], "files": files,
               "interpreter": interpreter, "agent": AGENT, "agent_pycache": agent_pycache, "cwd": ws,
               "env": _child_env(ws, tmp), "window": window}
    ask = os.path.join(work, "request.json")
    pathlib.Path(ask).write_text(json.dumps(_plain(request)), encoding="utf-8")
    return ask, ws, pycache


def _watch(run, proto: str, nonce: str, key: str, cls: str, window: float, env: ExecutionEnv,
           decide) -> tuple[Observation | _Later, dict | None]:
    """READY and DISPATCHED under the harness watchdog, then RESULT under the subject's window; the process's exit is
    lifecycle evidence read from the range, and the marker file is read to its end after it (§9.4). Only authentic
    lines count (B1). A `_Later` stands for a verdict `decide` left to the caller (`_observe_in`)."""
    state, seen = _await(run, proto, nonce, key, "DISPATCHED", time.monotonic() + env.timeout_s)
    if state != "LINE":
        return _harness_failure(run, state, seen, env.timeout_s), None
    state, seen = _await(run, proto, nonce, key, "RESULT", time.monotonic() + window + env.timeout_s)
    if state == "TIMEOUT":
        if run.members():   # B1: the controller's own timer would have spoken at W; a range alive and silent is no verdict
            return _after_dispatch(run, _silent(window, env)), None
        if run.wait(_COLLECT_S) is None:   # nothing of it is left, and the range never said how it ended
            # after DISPATCHED the controller's ledger is asked first (§9.3): on Windows its TerminateJobObject
            # takes the range's anchor down with the job, so a controller stop reports no exit status at all
            return _after_dispatch(run, Observation(ObservationKind.HARNESS_FAILED,
                                                    detail="the harness process ended and its exit status was "
                                                           "never reported")), None
        seen = _protocol(proto, nonce, key)
    if "RESULT" in seen:
        facts = json.loads(seen["RESULT"][0])
        if facts.get("deadline"):
            return _after_dispatch(run, _deadline(cls, window)), None
        return _concluded(run, facts, decide)
    return _after_dispatch(run, _no_result(run)), None


def _deadline(cls: str, window: float, table: dict = ON_DEADLINE) -> Observation:
    """The controller's own deadline (B1): its timer ran out with the subject still inside its observation."""
    return Observation(ObservationKind.SUBJECT_DEADLINE, table[cls],
                       detail=f"the subject's {window:g}s observation window expired ({cls})")


def _silent(window: float, env: ExecutionEnv) -> Observation:
    """B1-BLOCKS-STOP-001: by the end of the subject's window and the harness watchdog the controller said nothing,
    while the range still holds a process — a stopped or starved controller is never read as the subject's deadline."""
    return Observation(ObservationKind.HARNESS_FAILED,
                       detail=f"the probe's controller reported nothing by the end of the subject's {window:g}s window "
                              f"and the {env.timeout_s:g}s harness watchdog")


@dataclasses.dataclass(frozen=True, slots=True)
class _Later:
    """An observation whose verdict is still to be decided: what `_concluded` returns when `decide` gave a function
    instead of a verdict. The facts are the controller's and were checked against its signal ledger (§9.3) before the
    subject's range was released; the verdict is computed by `verdict` once nothing of the subject is alive, because
    deciding it reads the capture files and starts a worker on files the subject could still reach."""
    verdict: object      # () -> BehaviorVerdict; may raise StreamSearchFailed
    detail: str

    def settle(self) -> Observation:
        try:
            verdict = self.verdict()
        except StreamSearchFailed as e:     # the harness could not search: nothing was observed of the product's output
            return Observation(ObservationKind.HARNESS_FAILED, detail=str(e))
        return Observation(ObservationKind.OBSERVED, verdict, detail=self.detail)


def _concluded(run, facts: dict, decide) -> tuple[Observation | _Later, dict | None]:
    """What the controller reported — only the controller writes RESULT (B1): the subject's process ended by a signal
    the controller did not send (NON_CONTROLLER_SIGNAL, §9.3); the controller's own failure; an absent subject; an
    answer on the subject's channel that was not the agent's (REFUTED: the subject tampered with its observation);
    or the facts, decided."""
    if "subject_signal" in facts:
        return _after_dispatch(run, Observation(ObservationKind.NON_CONTROLLER_SIGNAL,
                                                detail=f"the subject's process ended by signal {facts['subject_signal']} "
                                                       "after DISPATCHED, and this controller's signal ledger is empty: "
                                                       "it did not send it")), None
    if "harness_failure" in facts:
        return _after_dispatch(run, Observation(ObservationKind.HARNESS_FAILED, detail=facts["harness_failure"])), None
    if facts.get("subject") == "absent":   # every observable here is positive: not observed over an absent subject
        return _after_dispatch(run, Observation(ObservationKind.SUBJECT_ABSENT, BehaviorVerdict.REFUTED,
                                                detail=facts.get("note", ""))), None
    if "tampered" in facts:
        return _after_dispatch(run, Observation(ObservationKind.OBSERVED, BehaviorVerdict.REFUTED,
                                                detail=json.dumps(facts))), None
    decided, detail = decide(facts), json.dumps(_public(facts))
    if callable(decided):      # the verdict waits for the subject's range to be empty (`_observe_in` settles it)
        return _after_dispatch(run, _Later(decided, detail)), facts
    return _after_dispatch(run, Observation(ObservationKind.OBSERVED, decided, detail=detail)), facts


def _no_result(run) -> Observation:
    """After DISPATCHED the controller's process ended with no RESULT: by a signal this controller did not send —
    NON_CONTROLLER_SIGNAL (§9.3); otherwise the observation mechanism failed (the subject's own ending, a hard exit
    or a signal, is reported by the controller, which outlives it — B1)."""
    code = run.returncode
    if code is not None and code < 0:
        return Observation(ObservationKind.NON_CONTROLLER_SIGNAL,
                           detail=f"the process ended by signal {-code} after DISPATCHED, and this controller's signal "
                                  "ledger is empty: it did not send it")
    return Observation(ObservationKind.HARNESS_FAILED, detail=f"the probe's controller ended without a result "
                                                              f"(exit {code})")


def _harness_failure(run, state: str, seen: dict, timeout_s: float) -> Observation:
    """Before DISPATCHED the observation mechanism itself failed: UNRUNNABLE (V2-002, CASE C). Concluded only from
    the marker file read to its end and the exit reported (§9.4), or from the watchdog."""
    expected = "DISPATCHED" if "READY" in seen else "READY"
    if state == "TIMEOUT":
        detail = f"harness timeout: no {expected} within {timeout_s:g}s — the observation mechanism did not operate"
    elif run.returncode is not None and run.returncode < 0:
        detail = f"the harness process was killed by signal {-run.returncode} before {expected}"
    else:
        detail = f"the harness did not start (exit {run.returncode}, no {expected}): tool absent or broken"
    return Observation(ObservationKind.HARNESS_FAILED, detail=detail)


METADATA = ProbeMetadata(PROBE_ID, DIGEST, spec_class)
