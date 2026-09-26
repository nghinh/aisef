"""RFC §9 — the reference probe kind: `python_callable` (one kind ships in Cycle 1; WP-2.1).

**Subject.** `module.path:attr[.attr]` resolved against the revision checkout (the checkout root and, if present, its
`src/`). A module that resolves only from outside the checkout — stdlib, site-packages — is absent *at this revision*.

**Observable classes.** Every observable declares its bounded observation window, `within_s` (§9.2); a spec without
one gives an expired window no meaning and is INVALID_SPEC. Negation is the contract's polarity (§7).

| class | observable | stimulus | SATISFIED when | the window expires |
|---|---|---|---|---|
| `exists`  | `{"condition": "exists", "within_s": W}` | `{}` | the locator resolves | REFUTED: it did not resolve in W |
| `returns` | `{"returns": <json>, "within_s": W}` | `{"args", "kwargs"}` | calling it returns that value | REFUTED: no value in W |
| `raises`  | `{"raises": "<Name>", "within_s": W}` | same | calling it raises exactly that type | REFUTED: nothing raised in W |
| `blocks`  | `{"blocks": true, "within_s": W}` | same | the call is still running when W closes | SATISFIED: it blocked |

The last column is each class's own meaning of an expired window (`ON_DEADLINE`), not a rule about timeouts: the same
hanging subject is REFUTED for `returns` and SATISFIED for `blocks` (TIME-4).

Over an absent subject no positive observable is observed, so this probe reports REFUTED as the observable's verdict;
whether that verdict counts is the spec's `SubjectAbsence`, applied by `protocol.classify_failure`, never here. A
subject that is present but does not resolve (its own import fails, the attribute is not callable), or that ends the
harness process mid-observation (exit status >= 0, no RESULT), is observed: REFUTED. A process killed by a signal
cannot be told apart from the environment killing it, so it is a harness failure.

**Observation harness vs subject window** (`harness_preconditions`, §9.2). The harness script is part of this module,
hence of the probe digest. It reads its request from stdin, prints a nonce-tagged READY, then DISPATCHED just before
it touches the subject (import, resolution, call), then RESULT. The parent reads the lines as they arrive:

* until DISPATCHED the harness watchdog (`ExecutionEnv.timeout_s`) runs: cannot launch, exit before READY, or no
  READY/DISPATCHED in time -> HARNESS_FAILED -> UNRUNNABLE / ENVIRONMENT (TIME-1);
* after DISPATCHED the spec's window runs: no RESULT within `within_s` -> the process is stopped and the observation is
  SUBJECT_DEADLINE with the class's `ON_DEADLINE` verdict -> EXECUTED (TIME-2..5). Never UNRUNNABLE.

**Protocol stream vs process lifecycle** (RFC §9.4, ARCHITECTURE-EXCEPTION-V2-006). Two independent facts, never
collapsed: the protocol stream reached its own end of file, and the process's exit was reported. The protocol is read
from the output stream alone — one pump reads every line in order and publishes STREAM_CLOSED only after the stream's
end of file, so no line that preceded it can be overtaken; the range's anchor holds no copy of the stream's writer, so
that end of file is the target's own. The exit is lifecycle evidence, asked of the range only once the stream has
closed; it never ends the protocol by itself. "Exit before READY" is concluded only when the stream has closed, the
exit is reported and no READY was read. No timing window decides the order; the watchdog and the subject's window stay
what they were — deadlines for a harness that does not answer and a subject that does not report.

**Enforcement: PARTIAL.** Weakest path: the subject runs inside the probe's subprocess with the harness user's
filesystem and network access; isolation is `-I` interpreter isolation and a scrubbed environment, not a sandbox.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import queue
import re
import secrets
import subprocess
import tempfile
import threading
import time

from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.probe.protocol import (
    ExecutionEnv, HarnessProbe, Observation, ObservationKind, ProbeInterrupted, ProbeMetadata, RevisionRef,
)
from aisef2.runtime.process_range import ProcessRange, RangeError
from aisef2.product.spec import ProductProofSpec

_GRACE_S = (1.0, 1.0)   # the range's graceful-first ladder when the observation is over
_WAIT_S = 30.0          # bounded: a range that will not empty is a residual, never an endless wait
_COLLECT_S = 5.0        # how long the anchor is given to report the target's exit status

PROBE_ID = "probe.python_callable"
PROBE_SOURCES = ("probe/protocol.py", "probe/python_callable.py")
LOCATOR = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
CLASSES = ("exists", "returns", "raises", "blocks")
#: Each class's meaning of an expired observation window (§9.2) — what the observable says about "not yet, at W".
ON_DEADLINE = {"exists": BehaviorVerdict.REFUTED, "returns": BehaviorVerdict.REFUTED,
               "raises": BehaviorVerdict.REFUTED, "blocks": BehaviorVerdict.SATISFIED}
WEAKEST_PATH = ("the subject runs inside the probe's subprocess with the harness user's filesystem and network "
                "access; isolation is -I interpreter isolation and a scrubbed environment, not a sandbox")
_MARK = "AISEF2-PROBE"


def _probe_digest() -> str:
    root = pathlib.Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for rel in PROBE_SOURCES:
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


DIGEST = _probe_digest()


def window_of(observable) -> float | None:
    """The spec's bounded observation window in seconds, or None when it declares none."""
    w = dict(observable).get("within_s")
    ok = isinstance(w, (int, float)) and not isinstance(w, bool) and math.isfinite(w) and w > 0
    return float(w) if ok else None


def observation_class(observable, stimulus) -> str | None:
    """The class a spec's observable asks for, or None when this probe cannot give it a meaning."""
    if window_of(observable) is None:
        return None
    obs = {k: v for k, v in dict(observable).items() if k != "within_s"}
    stim = dict(stimulus)
    if obs == {"condition": "exists"}:
        return "exists" if not stim else None
    if not set(stim) <= {"args", "kwargs"}:
        return None
    if set(obs) == {"returns"}:
        return "returns"
    if set(obs) == {"raises"} and isinstance(obs["raises"], str) and obs["raises"].isidentifier():
        return "raises"
    if set(obs) == {"blocks"} and obs["blocks"] is True:
        return "blocks"
    return None


def spec_class(spec: ProductProofSpec) -> str | None:
    """Harness metadata (`ProbeMetadata.observation_class`): the class `spec` asks of this probe, or None."""
    subject = dict(spec.probe_input["subject"])
    if subject.get("kind") != "python_callable" or not isinstance(subject.get("locator"), str) \
            or not LOCATOR.fullmatch(subject["locator"]):
        return None
    return observation_class(spec.probe_input["observable"], spec.probe_input["stimulus"])


def verdict_of(cls: str, observable, facts: dict) -> BehaviorVerdict:
    """What a present subject's facts say about the observable, when the harness reported before the window closed."""
    if cls == "exists":
        seen = facts.get("resolved") is True
    elif cls == "returns":
        seen = "returned" in facts and facts["returned"] == _plain(observable["returns"])
    elif cls == "raises":
        seen = facts.get("raised") == observable["raises"]
    else:
        seen = False  # blocks: it returned, raised or failed to resolve before the window closed
    return BehaviorVerdict.SATISFIED if seen else BehaviorVerdict.REFUTED


def _plain(value):
    return json.loads(json.dumps(value))


#: The harness script. Probe-owned; runs in `-I` mode with the checkout on sys.path; never names a developer file.
HARNESS = r'''
import importlib, json, os, sys
req = json.loads(open(sys.argv[1], encoding="utf-8").read())
nonce, root = req["nonce"], os.path.realpath(req["root"])
sys.path[:0] = [p for p in (root, os.path.join(root, "src")) if os.path.isdir(p)]
out = sys.stdout
def emit(tag, body=""):
    out.write("\n%s %s %s %s\n" % (req["mark"], tag, nonce, body)); out.flush()
emit("READY")
def inside(mod):
    f = getattr(mod, "__file__", None)
    places = [f] if f else list(getattr(mod, "__path__", []))
    return any(os.path.realpath(p).startswith(root + os.sep) for p in places)
def facts():
    name, _, attrs = req["locator"].partition(":")
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name and (name == e.name or name.startswith(e.name + ".")):
            return {"subject": "absent"}
        return {"subject": "present", "resolved": False, "error": type(e).__name__}
    except BaseException as e:
        return {"subject": "present", "resolved": False, "error": type(e).__name__}
    if not inside(mod):
        return {"subject": "absent", "note": "resolves only outside the revision"}
    obj = mod
    for a in attrs.split("."):
        try:
            obj = getattr(obj, a)
        except AttributeError:
            return {"subject": "absent"}
        except BaseException as e:
            return {"subject": "present", "resolved": False, "error": type(e).__name__}
    if req["cls"] == "exists":
        return {"subject": "present", "resolved": True}
    if not callable(obj):
        return {"subject": "present", "resolved": False, "error": "not callable"}
    try:
        value = obj(*req["args"], **req["kwargs"])
    except BaseException as e:
        return {"subject": "present", "resolved": True, "raised": type(e).__name__}
    try:
        return {"subject": "present", "resolved": True, "returned": json.loads(json.dumps(value))}
    except (TypeError, ValueError):
        return {"subject": "present", "resolved": True, "returned_unserializable": type(value).__name__}
emit("DISPATCHED")
emit("RESULT", json.dumps(facts()))
'''


class PythonCallableProbe(HarnessProbe):
    id = PROBE_ID
    digest = DIGEST

    def __init__(self, on_range=None) -> None:
        """`on_range` is called with the process range as soon as it starts — harness-owned, not part of the frozen
        `Probe` protocol (PROBE-META-1). A run uses it to acquire the range into the story's StoryScope, so an
        interruption disposes it through P4's ownership and its ledger records what the controller sent (§9.3)."""
        self._on_range = on_range

    def enforcement(self) -> Enforcement:
        return Enforcement.PARTIAL

    def harness_preconditions(self) -> tuple[str, ...]:
        return ("interpreter: the ExecutionEnv's Python interpreter exists and launches",
                "checkout: the revision's checkout is a readable directory",
                "protocol: the harness prints READY, then DISPATCHED before touching the subject, within the "
                "harness watchdog (ExecutionEnv.timeout_s)")

    def observe(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> Observation:
        pi = spec.probe_input
        subject = dict(pi["subject"])
        if subject.get("kind") != "python_callable":
            return Observation(ObservationKind.UNSUPPORTED, detail=f"subject kind {subject.get('kind')!r} is not "
                                                                   "python_callable")
        if not isinstance(subject.get("locator"), str) or not LOCATOR.fullmatch(subject["locator"]):
            return Observation(ObservationKind.UNSUPPORTED, detail=f"locator {subject.get('locator')!r} is not "
                                                                   "module.path:attr — a path is never accepted")
        cls = spec_class(spec)
        if cls is None:
            return Observation(ObservationKind.UNSUPPORTED, detail="observable/stimulus is not a supported class "
                                                                   f"{CLASSES} with a bounded window (within_s); "
                                                                   "refused, not degraded")
        if not os.path.isfile(env.interpreter):
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"interpreter absent: {env.interpreter}")
        if not os.path.isdir(at.root):
            return Observation(ObservationKind.HARNESS_FAILED, detail="cannot inspect: the revision checkout is missing")
        nonce = secrets.token_hex(16)
        stim = dict(pi["stimulus"])
        request = {"mark": _MARK, "nonce": nonce, "root": at.root, "locator": subject["locator"], "cls": cls,
                   "args": list(stim.get("args", [])), "kwargs": dict(stim.get("kwargs", {}))}
        with tempfile.TemporaryDirectory(prefix="aisef2-probe-") as work:
            ask = os.path.join(work, "request.json")
            pathlib.Path(ask).write_text(json.dumps(_plain(request)), encoding="utf-8")
            # the harness runs inside a P4 process range: its ledger is the one authority on what this controller
            # signalled, and disposal takes the whole tree down, not only the direct child (§9.3, V2-003)
            run = ProcessRange(f"probe {spec.id}", [env.interpreter, "-I", "-c", HARNESS, ask], cwd=at.root,
                               env=_scrubbed_env(), output=subprocess.PIPE, grace_s=_GRACE_S, wait_s=_WAIT_S)
            try:
                run.start()
                if self._on_range is not None:
                    self._on_range(run)
            except (RangeError, OSError) as e:
                return Observation(ObservationKind.HARNESS_FAILED, detail=f"the harness cannot launch: "
                                                                         f"{type(e).__name__}")
            try:
                return self._watch(run, nonce, cls, pi, env)
            finally:
                run.release()  # RangeNotEmpty / RangeEscaped propagate: a leak is never silent (§17.1)

    def _watch(self, run, nonce: str, cls: str, pi, env) -> Observation:
        """Read the harness protocol: READY and DISPATCHED under the harness watchdog, then the subject's own window.
        The protocol comes from the output stream alone, through one pump (§9.4); the process's exit is asked of the
        range only after that stream has closed."""
        lines: queue.Queue = queue.Queue()
        threading.Thread(target=_pump, args=(run.output, lines), daemon=True).start()
        watchdog = time.monotonic() + env.timeout_s
        for expected in ("READY", "DISPATCHED"):
            tag, _ = _next(lines, nonce, watchdog)
            if tag != expected:
                return _harness_failure(run, tag, expected, env.timeout_s, watchdog)
        window = window_of(pi["observable"])
        until = time.monotonic() + window
        tag, body = _next(lines, nonce, until)
        # the stream closed with no RESULT in it: now, and only now, how did the process end? (still running at W: the
        # window expired, below)
        if tag == "STREAM_CLOSED" and (run.wait(max(0.0, until - time.monotonic())) is not None
                                       or time.monotonic() < until):
            return _after_dispatch(run, _ended_without_result(run))
        if tag != "RESULT":  # the window closed with the process still running
            return _after_dispatch(run, Observation(ObservationKind.SUBJECT_DEADLINE, ON_DEADLINE[cls],
                                                    detail=f"the subject's {window:g}s observation window expired "
                                                           f"({cls})"))
        facts = json.loads(body)
        if facts.get("subject") == "absent":
            # every observable here is positive, so over an absent subject it is not observed
            return _after_dispatch(run, Observation(ObservationKind.SUBJECT_ABSENT, BehaviorVerdict.REFUTED,
                                                    detail=facts.get("note", "")))
        return _after_dispatch(run, Observation(ObservationKind.OBSERVED, verdict_of(cls, pi["observable"], facts),
                                                detail=json.dumps(facts)))


METADATA = ProbeMetadata(PROBE_ID, DIGEST, spec_class)


def _pump(stream, lines: queue.Queue) -> None:
    """The protocol stream's one reader (§9.4): every line, in order, then STREAM_CLOSED — published by this same
    thread only after the stream's own end of file, so no line that preceded it can be overtaken by it."""
    try:
        for line in stream:
            lines.put(("LINE", line))
    finally:
        lines.put(("STREAM_CLOSED", ""))
        if hasattr(stream, "close"):
            stream.close()


def _next(lines: queue.Queue, nonce: str, until: float) -> tuple[str, str]:
    """The next protocol line (tag, body) before `until`; ("STREAM_CLOSED", "") once the pump has read the stream to
    its end, every line before it already returned; ("TIMEOUT", "") when late. A protocol line is complete — it ends in
    a newline — and carries the mark and this run's nonce; an unterminated fragment is never one."""
    while True:
        left = until - time.monotonic()
        if left <= 0:
            return "TIMEOUT", ""
        try:
            kind, line = lines.get(timeout=left)
        except queue.Empty:
            return "TIMEOUT", ""
        if kind == "STREAM_CLOSED":
            lines.put((kind, line))  # a closed stream stays closed for any later read
            return kind, ""
        if not line.endswith("\n"):
            continue
        parts = line[:-1].rstrip("\r").split(" ", 3)
        if len(parts) >= 3 and parts[0] == _MARK and parts[2] == nonce:
            return parts[1], parts[3] if len(parts) == 4 else ""


def _after_dispatch(run, observation: Observation) -> Observation:
    """§9.3 (ARCHITECTURE-EXCEPTION-V2-003), CASE A. Nothing observed after DISPATCHED survives this controller's own
    stop: if its signal ledger holds a signal, the observation was interrupted, whatever the harness managed to report
    before it died — a cooperative SIGINT, for instance, surfaces inside the subject as KeyboardInterrupt, and reading
    that as the subject's own behaviour would charge a controller's decision to the product. An interruption is not a
    measurement: no `ProbeResult`, no verdict, no owner. The ledger is the authority, never the signal number."""
    stages = [s["stage"] for s in run.ledger]
    if not stages:
        return observation
    raise ProbeInterrupted(f"the controller stopped this observation ({', '.join(stages)}): what the subject did is "
                           "not known", signal=_signal_of(run.returncode), stage=stages[-1])


def _ended_without_result(run) -> Observation:
    """§9.3, CASES B and C after DISPATCHED: how the harness's process ended, when this controller did not stop it.

    * it ended by a signal: the controller did not send it, and nothing here knows who did — EXECUTED +
      INDETERMINATE(NON_CONTROLLER_SIGNAL), never UNRUNNABLE and never a verdict (CASE B);
    * it ended by an exit status: the subject ended the process before the observable — an observation, REFUTED;
    * its status was never reported: the observation mechanism cannot say what happened — UNRUNNABLE.
    """
    code = run.wait(_COLLECT_S)
    if code is None:
        return Observation(ObservationKind.HARNESS_FAILED,
                           detail="the harness process ended and its exit status was never reported")
    if code < 0:
        return Observation(ObservationKind.NON_CONTROLLER_SIGNAL,
                           detail=f"the process ended by signal {-code} after DISPATCHED, and this controller's "
                                  "signal ledger is empty: it did not send it")
    return Observation(ObservationKind.OBSERVED, BehaviorVerdict.REFUTED,
                       detail=f"the subject ended the process before the observable (exit {code})")


def _signal_of(code: int | None) -> int | None:
    return -code if code is not None and code < 0 else None


def _harness_failure(run, tag: str, expected: str, timeout_s: float, until: float) -> Observation:
    """Before DISPATCHED the observation mechanism itself failed: UNRUNNABLE, unchanged by V2-003 (V2-002, CASE C).
    It ended before `expected` only when both facts are in (§9.4): the stream closed with no `expected` in it, and the
    exit was reported — asked of the range now, under the same watchdog. A stream closed while its process still runs
    at the watchdog is a harness timeout; a protocol tag out of order is the harness breaking its protocol."""
    code = None
    if tag == "STREAM_CLOSED":
        code = run.wait(max(0.0, until - time.monotonic()))
        if code is None and time.monotonic() >= until:
            tag = "TIMEOUT"
    if tag == "TIMEOUT":
        detail = f"harness timeout: no {expected} within {timeout_s:g}s — the observation mechanism did not operate"
    elif tag != "STREAM_CLOSED":
        detail = f"the harness broke its protocol: {tag} before {expected}"
    elif code is not None and code < 0:
        detail = f"the harness process was killed by signal {-code} before {expected}"
    else:
        detail = f"the harness did not start (exit {code}, no {expected}): tool absent or broken"
    return Observation(ObservationKind.HARNESS_FAILED, detail=detail)


def _scrubbed_env() -> dict:
    keep = ("SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR")  # Windows needs SYSTEMROOT to start Python
    return {**{k: os.environ[k] for k in keep if k in os.environ},
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"}
