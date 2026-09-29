"""RFC §9 — `python_callable`, second identity (Cycle 2, WP-2.4.1; owner DECISION-6).

The Cycle-1 probe (`aisef2/probe/python_callable.py`, digest 1961e84d…) is immutable: every Cycle-1
`ProductProofSpec` / `semantic_hash` stays bound to it. The observation classes LedgerLock needs beyond it
(CYCLE2-PROBE-TAXONOMY-PROPOSAL §5, CYCLE2-F5-COMPATIBILITY-REPORT §2.4) ship here, under their own `PROBE_ID`, digest,
calibration fixtures and evidence. Nothing of the frozen protocol changes: the subject split, the READY / DISPATCHED /
RESULT lines with a per-evaluation nonce on captured stdout, the harness watchdog vs the subject's window (§9.2), the
signal provenance rule (§9.3), the pump-completion barrier (§9.4) and bytecode isolation (P7-FINDING-001) are the
Cycle-1 mechanisms, reused by import where they do not depend on this module's own tables — hence
`probe/python_callable.py` is one of this probe's sources and part of its digest.

**Subject.** `module.path:attr[.attr]` resolved against the revision checkout, as in Cycle 1.

**Observable classes.** Every observable declares its bounded window `within_s` (§9.2).

| class | observable | stimulus | SATISFIED when | the window expires |
|---|---|---|---|---|
| `exists`  | `{"condition": "exists"}` | `{}` | the locator resolves | REFUTED |
| `returns` | `{"returns": <json>}` | call | calling it returns that value | REFUTED |
| `raises`  | `{"raises": "<Name>"}` | call | calling it raises exactly that type | REFUTED |
| `blocks`  | `{"blocks": true}` | call | the call is still running when W closes | SATISFIED |
| `returns_bytes` | `{"returns_bytes_hex": "<hex>"}` | call | the call returns bytes/bytearray/memoryview with that hex; any other result is REFUTED | REFUTED |
| `equals`  | `{"equals": <json>}` | `{}` | the locator resolves to a NON-callable value whose JSON form equals it; a callable subject is UNSUPPORTED | REFUTED |
| `raises_attrs` | `{"raises": "<Name>", "attrs": {name: <json>, …}}` | call | the type name matches AND every declared attribute of the exception, JSON-serialised, equals; a missing or unserialisable attribute is REFUTED | REFUTED |

A call stimulus is `{"args": [...], "kwargs": {...}, "workspace": {...}}`, each key optional. `workspace` names files the
harness writes byte-exactly into a fresh directory of this evaluation's own before the call — `{"name": {"text": "...",
"newline": "\\n" | "\\r\\n"}}` (the text's `\\n` written as the declared newline) or `{"name": {"bytes_hex": "..."}}`,
flat names only. The one placeholder `<ws>` in any string of `args`/`kwargs` is replaced by that directory's absolute
(real) path before dispatch; any occurrence of the path in what the subject returned or raised is replaced back by
`<ws>` before comparison, so a verdict and its detail never depend on where the evaluation ran. There is no other
token and no formatting of stimulus text. The directory exists — empty — for every evaluation, so `<ws>` always
resolves.

Absent subject, a subject that does not resolve or that ends the harness process, and the harness/subject split are
exactly Cycle 1's (see that module's docstring). **Enforcement: PARTIAL**, the same weakest path.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import queue
import re
import secrets
import subprocess
import threading
import time
from collections.abc import Mapping

from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.probe.protocol import (
    ExecutionEnv, HarnessProbe, Observation, ObservationKind, ProbeMetadata, RevisionRef,
)
from aisef2.probe import python_callable as _cycle1
from aisef2.probe.python_callable import (
    _GRACE_S, _MARK, _WAIT_S, LOCATOR, _after_dispatch, _ended_without_result, _evaluation_dir, _harness_failure,
    _inside, _next, _plain, _pump, _scrubbed_env, window_of,
)
from aisef2.runtime.process_range import ProcessRange, RangeError
from aisef2.product.contract import plain
from aisef2.product.spec import ProductProofSpec

PROBE_ID = "probe.python_callable_v2"
WEAKEST_PATH = _cycle1.WEAKEST_PATH  # PARTIAL, the same weakest path: the subject runs in the harness's subprocess
PROBE_SOURCES = ("probe/protocol.py", "probe/python_callable.py", "probe/python_callable_v2.py")
CLASSES = ("exists", "returns", "raises", "blocks", "returns_bytes", "equals", "raises_attrs")
#: Each class's meaning of an expired observation window (§9.2).
ON_DEADLINE = {"exists": BehaviorVerdict.REFUTED, "returns": BehaviorVerdict.REFUTED,
               "raises": BehaviorVerdict.REFUTED, "blocks": BehaviorVerdict.SATISFIED,
               "returns_bytes": BehaviorVerdict.REFUTED, "equals": BehaviorVerdict.REFUTED,
               "raises_attrs": BehaviorVerdict.REFUTED}
PLACEHOLDER = "<ws>"
_HEX = re.compile(r"(?:[0-9a-f]{2})*")
_WS_NAME = re.compile(r"[A-Za-z0-9_][\w.-]*")
_NEWLINES = ("\n", "\r\n")


def _probe_digest() -> str:
    root = pathlib.Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for rel in PROBE_SOURCES:
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


DIGEST = _probe_digest()


def _is_hex(value) -> bool:
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _workspace_ok(workspace) -> bool:
    """A well-formed workspace: flat names, each a text file with its newline or a hex byte string."""
    if not isinstance(workspace, Mapping):
        return False
    for name, file in workspace.items():
        if not isinstance(name, str) or not _WS_NAME.fullmatch(name) or not isinstance(file, Mapping):
            return False
        if set(file) == {"text", "newline"}:
            if not isinstance(file["text"], str) or file["newline"] not in _NEWLINES:
                return False
        elif set(file) != {"bytes_hex"} or not _is_hex(file["bytes_hex"]):
            return False
    return True


def observation_class(observable, stimulus) -> str | None:
    """The class a spec's observable asks for, or None when this probe cannot give it a meaning."""
    if window_of(observable) is None:
        return None
    obs = {k: v for k, v in dict(observable).items() if k != "within_s"}
    stim = dict(stimulus)
    if obs == {"condition": "exists"}:
        return "exists" if not stim else None
    if set(obs) == {"equals"}:
        return "equals" if not stim else None
    if not set(stim) <= {"args", "kwargs", "workspace"}:
        return None
    if "workspace" in stim and not _workspace_ok(stim["workspace"]):
        return None
    raises = isinstance(obs.get("raises"), str) and obs["raises"].isidentifier()
    if set(obs) == {"returns"}:
        return "returns"
    if set(obs) == {"returns_bytes_hex"} and _is_hex(obs["returns_bytes_hex"]):
        return "returns_bytes"
    if set(obs) == {"raises"} and raises:
        return "raises"
    if set(obs) == {"raises", "attrs"} and raises and isinstance(obs["attrs"], Mapping) and obs["attrs"] \
            and all(isinstance(k, str) and k.isidentifier() for k in obs["attrs"]):
        return "raises_attrs"
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
    """What a present subject's facts say about the observable, when the harness reported before the window closed.
    An expectation is compared in its JSON form (`plain`: the spec's frozen mappings and tuples as dicts and lists),
    the form the harness reports facts in."""
    if cls == "exists":
        seen = facts.get("resolved") is True
    elif cls in ("returns", "equals"):
        seen = "returned" in facts and facts["returned"] == plain(observable[cls])
    elif cls == "returns_bytes":
        seen = facts.get("returned_bytes_hex") == observable["returns_bytes_hex"]
    elif cls in ("raises", "raises_attrs"):
        got = facts.get("raised_attrs", {})
        seen = facts.get("raised") == observable["raises"] and all(
            k in got and got[k] == plain(v) for k, v in dict(observable).get("attrs", {}).items())
    else:
        seen = False  # blocks: it returned, raised or failed to resolve before the window closed
    return BehaviorVerdict.SATISFIED if seen else BehaviorVerdict.REFUTED


def _substituted(value, ws: str):
    """A spec's frozen stimulus data (read-only mappings, tuples) as plain JSON data with every `<ws>` in a string
    replaced by the workspace path."""
    if isinstance(value, str):
        return value.replace(PLACEHOLDER, ws)
    if isinstance(value, Mapping):
        return {k: _substituted(v, ws) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_substituted(v, ws) for v in value]
    return value


def _unsubstituted(value, ws: str):
    """The harness's facts (parsed JSON: dicts, lists) with every occurrence of the workspace path in a string
    replaced back by `<ws>`."""
    if isinstance(value, str):
        return value.replace(ws, PLACEHOLDER)
    if isinstance(value, dict):
        return {k: _unsubstituted(v, ws) for k, v in value.items()}
    if isinstance(value, list):
        return [_unsubstituted(v, ws) for v in value]
    return value


def _write_workspace(ws: str, workspace) -> None:
    """Every declared file, byte-exactly, into the fresh workspace directory."""
    for name, file in dict(workspace).items():
        if "bytes_hex" in file:
            data = bytes.fromhex(file["bytes_hex"])
        else:
            data = file["text"].replace("\n", file["newline"]).encode("utf-8")
        pathlib.Path(ws, name).write_bytes(data)


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
def plain(value):
    return json.loads(json.dumps(value))
def value_of(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"subject": "present", "resolved": True, "returned_bytes_hex": bytes(value).hex()}
    try:
        return {"subject": "present", "resolved": True, "returned": plain(value)}
    except (TypeError, ValueError):
        return {"subject": "present", "resolved": True, "returned_unserializable": type(value).__name__}
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
    if req["cls"] == "equals":
        if callable(obj):
            return {"subject": "present", "resolved": True,
                    "unsupported": "equality over a callable subject is not offered"}
        return value_of(obj)
    if not callable(obj):
        return {"subject": "present", "resolved": False, "error": "not callable"}
    try:
        value = obj(*req["args"], **req["kwargs"])
    except BaseException as e:
        got = {"subject": "present", "resolved": True, "raised": type(e).__name__}
        if req["attrs"]:
            got["raised_attrs"], got["raised_attrs_unserializable"] = {}, []
            for a in req["attrs"]:
                try:
                    got["raised_attrs"][a] = plain(getattr(e, a))
                except AttributeError:
                    pass
                except (TypeError, ValueError):
                    got["raised_attrs_unserializable"].append(a)
        return got
    return value_of(value)
emit("DISPATCHED")
emit("RESULT", json.dumps(facts()))
'''


def _harness_argv(interpreter: str, ask: str, pycache: str) -> list[str]:
    """The harness command line: isolated mode, no bytecode written, the bytecode cache under a fresh prefix — every
    control on the command line, because `-I` discards every PYTHON* variable (P7-FINDING-001)."""
    return [interpreter, "-I", "-B", "-X", f"pycache_prefix={pycache}", "-c", HARNESS, ask]


class PythonCallableV2Probe(HarnessProbe):
    id = PROBE_ID
    digest = DIGEST

    def __init__(self, on_range=None, scratch: str | None = None) -> None:
        """`on_range` and `scratch` exactly as the Cycle-1 probe's: harness-owned hooks, not part of the frozen
        `Probe` protocol — the range is acquired into the story's StoryScope, the evaluation directory lies under the
        controller-owned scratch when one is given."""
        self._on_range, self._scratch = on_range, scratch

    def enforcement(self) -> Enforcement:
        return Enforcement.PARTIAL

    def harness_preconditions(self) -> tuple[str, ...]:
        return ("interpreter: the ExecutionEnv's Python interpreter exists and launches",
                "checkout: the revision's checkout is a readable directory",
                "workspace: the evaluation directory and the stimulus's workspace files can be written",
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
        try:
            holder = _evaluation_dir(self._scratch)
        except OSError as e:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"the evaluation directory cannot be created: "
                                                                     f"{type(e).__name__}")
        with holder as work:
            if _inside(work, at.root):
                return Observation(ObservationKind.HARNESS_FAILED, detail="the evaluation directory lies inside the "
                                                                         "revision checkout: refused")
            ask = os.path.join(work, "request.json")
            pycache = os.path.join(work, "pycache")
            ws = os.path.realpath(os.path.join(work, "ws"))
            try:
                os.mkdir(pycache)   # fresh and empty: no other evaluation's bytecode, and none from the checkout
                os.mkdir(ws)        # fresh and empty too: the workspace of this evaluation alone
                _write_workspace(ws, stim.get("workspace", {}))
            except OSError as e:
                return Observation(ObservationKind.HARNESS_FAILED, detail=f"the workspace cannot be written: "
                                                                         f"{type(e).__name__}")
            request = {"mark": _MARK, "nonce": nonce, "root": at.root, "locator": subject["locator"], "cls": cls,
                       "args": _substituted(stim.get("args", []), ws), "kwargs": _substituted(stim.get("kwargs", {}), ws),
                       "attrs": list(dict(pi["observable"]).get("attrs", {}))}
            pathlib.Path(ask).write_text(json.dumps(_plain(request)), encoding="utf-8")
            run = ProcessRange(f"probe {spec.id}", _harness_argv(env.interpreter, ask, pycache), cwd=at.root,
                               env=_scrubbed_env(), output=subprocess.PIPE, grace_s=_GRACE_S, wait_s=_WAIT_S)
            try:
                run.start()
                if self._on_range is not None:
                    self._on_range(run)
            except (RangeError, OSError) as e:
                return Observation(ObservationKind.HARNESS_FAILED, detail=f"the harness cannot launch: "
                                                                         f"{type(e).__name__}")
            try:
                return self._watch(run, nonce, cls, pi, env, ws)
            finally:
                run.release()  # RangeNotEmpty / RangeEscaped propagate: a leak is never silent (§17.1)

    def _watch(self, run, nonce: str, cls: str, pi, env, ws: str) -> Observation:
        """Cycle 1's protocol reader (§9.2, §9.4): READY and DISPATCHED under the harness watchdog, then the subject's
        window; the facts are read with the workspace path replaced back by `<ws>` before any comparison."""
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
        if tag == "STREAM_CLOSED" and (run.wait(max(0.0, until - time.monotonic())) is not None
                                       or time.monotonic() < until):
            return _after_dispatch(run, _ended_without_result(run))
        if tag != "RESULT":  # the window closed with the process still running
            return _after_dispatch(run, Observation(ObservationKind.SUBJECT_DEADLINE, ON_DEADLINE[cls],
                                                    detail=f"the subject's {window:g}s observation window expired "
                                                           f"({cls})"))
        facts = _unsubstituted(json.loads(body), ws)
        if facts.get("subject") == "absent":
            # every observable here is positive, so over an absent subject it is not observed
            return _after_dispatch(run, Observation(ObservationKind.SUBJECT_ABSENT, BehaviorVerdict.REFUTED,
                                                    detail=facts.get("note", "")))
        if "unsupported" in facts:  # equals over a callable: the spec asks what this probe does not offer
            return _after_dispatch(run, Observation(ObservationKind.UNSUPPORTED, detail=facts["unsupported"]))
        return _after_dispatch(run, Observation(ObservationKind.OBSERVED, verdict_of(cls, pi["observable"], facts),
                                                detail=json.dumps(facts)))


METADATA = ProbeMetadata(PROBE_ID, DIGEST, spec_class)
