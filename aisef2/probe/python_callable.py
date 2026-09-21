"""RFC §9 — the reference probe kind: `python_callable` (one kind ships in Cycle 1; WP-2.1).

**Subject.** `module.path:attr[.attr]` resolved against the revision checkout (the checkout root and, if present, its
`src/`). A module that resolves only from outside the checkout — stdlib, site-packages — is absent *at this revision*.

**Observable classes** — every one is a positive observation; negation is the contract's polarity (§7):

| class | observable | stimulus | SATISFIED when |
|---|---|---|---|
| `exists`  | `{"condition": "exists"}` | `{}` | the locator resolves (the module imports, the attribute is there) |
| `returns` | `{"returns": <json>}` | `{"args": [...], "kwargs": {...}}` | calling it returns that value |
| `raises`  | `{"raises": "<ExceptionName>"}` | same | calling it raises exactly that exception type |

Over an absent subject no positive observable is observed, so this probe reports REFUTED as the observable's verdict;
whether that verdict counts is the spec's `SubjectAbsence`, applied by `protocol.classify_failure`, never here. A
subject that is present but does not resolve (its own import fails, the attribute is not callable) or that ends the
harness process mid-observation (exit status >= 0, no RESULT) is observed: REFUTED. A process killed by a signal
cannot be told apart from the environment killing it, so it is a harness failure.

**Observation harness** (`harness_preconditions`): the interpreter the harness names, a readable checkout, and a
subprocess that completes the harness protocol. The harness script is part of this module, hence of the probe digest;
it reads its request from stdin before touching the subject, prints a nonce-tagged READY, then a nonce-tagged RESULT.
No READY -> the harness did not work -> UNRUNNABLE. Timeout -> UNRUNNABLE (§9 lists probe timeout as a harness failure).

**Enforcement: PARTIAL.** Weakest path: the subject runs inside the probe's subprocess with the harness user's
filesystem and network access; isolation is `-I` interpreter isolation and a scrubbed environment, not a sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import secrets
import subprocess

from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.probe.protocol import ExecutionEnv, HarnessProbe, Observation, ObservationKind, RevisionRef
from aisef2.product.spec import ProductProofSpec

PROBE_ID = "probe.python_callable"
PROBE_SOURCES = ("probe/protocol.py", "probe/python_callable.py")
LOCATOR = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
CLASSES = ("exists", "returns", "raises")
WEAKEST_PATH = ("the subject runs inside the probe's subprocess with the harness user's filesystem and network "
                "access; isolation is -I interpreter isolation and a scrubbed environment, not a sandbox")
_MARK = "AISEF2-PROBE"


def _probe_digest() -> str:
    root = pathlib.Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for rel in PROBE_SOURCES:
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def observation_class(observable, stimulus) -> str | None:
    """The class a spec's observable asks for, or None when this probe does not support it."""
    obs, stim = dict(observable), dict(stimulus)
    if obs == {"condition": "exists"}:
        return "exists" if not stim else None
    if not set(stim) <= {"args", "kwargs"}:
        return None
    if set(obs) == {"returns"}:
        return "returns"
    if set(obs) == {"raises"} and isinstance(obs["raises"], str) and obs["raises"].isidentifier():
        return "raises"
    return None


def verdict_of(cls: str, observable, facts: dict) -> BehaviorVerdict:
    """What a present subject's facts say about the observable. Positive observations only."""
    if cls == "exists":
        seen = facts.get("resolved") is True
    elif cls == "returns":
        seen = "returned" in facts and facts["returned"] == _plain(observable["returns"])
    else:
        seen = facts.get("raised") == observable["raises"]
    return BehaviorVerdict.SATISFIED if seen else BehaviorVerdict.REFUTED


def _plain(value):
    return json.loads(json.dumps(value))


#: The harness script. Probe-owned; runs in `-I` mode with the checkout on sys.path; never names a developer file.
HARNESS = r'''
import importlib, json, os, sys
req = json.loads(sys.stdin.read())
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
emit("RESULT", json.dumps(facts()))
'''


class PythonCallableProbe(HarnessProbe):
    id = PROBE_ID
    digest = _probe_digest()

    def enforcement(self) -> Enforcement:
        return Enforcement.PARTIAL

    def harness_preconditions(self) -> tuple[str, ...]:
        return ("interpreter: the ExecutionEnv's Python interpreter exists and executes",
                "checkout: the revision's checkout is a readable directory",
                "protocol: the harness subprocess prints READY before touching the subject, then RESULT")

    def observation_class(self, spec: ProductProofSpec) -> str | None:
        subject = dict(spec.probe_input["subject"])
        if subject.get("kind") != "python_callable":
            return None
        return observation_class(spec.probe_input["observable"], spec.probe_input["stimulus"])

    def observe(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> Observation:
        pi = spec.probe_input
        subject = dict(pi["subject"])
        if subject.get("kind") != "python_callable":
            return Observation(ObservationKind.UNSUPPORTED, detail=f"subject kind {subject.get('kind')!r} is not "
                                                                   "python_callable")
        if not isinstance(subject.get("locator"), str) or not LOCATOR.fullmatch(subject["locator"]):
            return Observation(ObservationKind.UNSUPPORTED, detail=f"locator {subject.get('locator')!r} is not "
                                                                   "module.path:attr — a path is never accepted")
        cls = self.observation_class(spec)
        if cls is None:
            return Observation(ObservationKind.UNSUPPORTED, detail="observable/stimulus is not a supported class "
                                                                   f"{CLASSES}; refused, not degraded")
        if not os.path.isfile(env.interpreter):
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"interpreter absent: {env.interpreter}")
        if not os.path.isdir(at.root):
            return Observation(ObservationKind.HARNESS_FAILED, detail="cannot inspect: the revision checkout is missing")
        nonce = secrets.token_hex(16)
        stim = dict(pi["stimulus"])
        request = {"mark": _MARK, "nonce": nonce, "root": at.root, "locator": subject["locator"], "cls": cls,
                   "args": list(stim.get("args", [])), "kwargs": dict(stim.get("kwargs", {}))}
        try:
            done = subprocess.run([env.interpreter, "-I", "-c", HARNESS], input=json.dumps(_plain(request)),
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=env.timeout_s, cwd=at.root, env=_scrubbed_env())
        except subprocess.TimeoutExpired:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"probe timeout after {env.timeout_s}s")
        except OSError as e:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"sandbox cannot execute: {type(e).__name__}")
        lines = {tag: body for tag, body in _protocol_lines(done.stdout, nonce)}
        if "READY" not in lines:
            return Observation(ObservationKind.HARNESS_FAILED,
                               detail=f"the harness did not start (exit {done.returncode}): tool absent or broken")
        if "RESULT" not in lines and done.returncode < 0:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"the harness process was killed by signal "
                                                                     f"{-done.returncode} mid-observation")
        if "RESULT" not in lines:
            return Observation(ObservationKind.OBSERVED, BehaviorVerdict.REFUTED,
                               detail=f"the subject ended the process before the observable (exit {done.returncode})")
        facts = json.loads(lines["RESULT"])
        if facts.get("subject") == "absent":
            # every observable here is positive, so over an absent subject it is not observed
            return Observation(ObservationKind.SUBJECT_ABSENT, BehaviorVerdict.REFUTED, detail=facts.get("note", ""))
        return Observation(ObservationKind.OBSERVED, verdict_of(cls, pi["observable"], facts), detail=json.dumps(facts))


def _protocol_lines(stdout: str, nonce: str):
    for line in stdout.splitlines():
        parts = line.split(" ", 3)
        if len(parts) >= 3 and parts[0] == _MARK and parts[2] == nonce:
            yield parts[1], parts[3] if len(parts) == 4 else ""


def _scrubbed_env() -> dict:
    keep = ("SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR")  # Windows needs SYSTEMROOT to start Python
    return {**{k: os.environ[k] for k in keep if k in os.environ},
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"}
