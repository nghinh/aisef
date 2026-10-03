"""RFC §9 — `python_callable`, second identity (Cycle 2, WP-2.4.1; owner DECISION-6).

The Cycle-1 probe (`aisef2/probe/python_callable.py`, digest 1961e84d…) is immutable: every Cycle-1
`ProductProofSpec` / `semantic_hash` stays bound to it. The observation classes LedgerLock needs beyond it
(CYCLE2-PROBE-TAXONOMY-PROPOSAL §5, CYCLE2-F5-COMPATIBILITY-REPORT §2.4) ship here, under their own `PROBE_ID`, digest,
calibration fixtures and evidence. The harness watchdog vs the subject's window (§9.2), the signal provenance rule
(§9.3) and bytecode isolation (P7-FINDING-001) are the Cycle-1 mechanisms, reused by import; the subject's process,
the protocol channel and its reader are cli_invocation's (B1, below) — hence `probe/python_callable.py` and
`probe/cli_invocation.py` are sources of this probe and part of its digest.

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

**Controller and subject process (B1, V2.0 release charter §7).** As cli_invocation and process_effect: the probe's
process is a controller (`HARNESS`) that never imports, resolves or calls the subject nor puts the revision on its own
path. It starts the subject's process (`cli_invocation.AGENT`, a child of the controller in the same owned range)
before DISPATCHED — with the Cycle-1 harness's settings: the checkout as its working directory, the scrubbed
environment, `-I -B` and the evaluation's fresh bytecode prefix, no UTF-8 mode — and with the evaluation's own
temporary directory (`TMPDIR`, `TEMP`, `TMP` — B6). It asks it for one operation at a time (import, resolve, value,
call), each answer echoing its request's number and a closing request ending the exchange, and builds every fact
itself from the answers: absence from the import's missing module name, the inside-the-revision rule from the
module's own `__file__` / `__path__`, the attribute chain, callability, the returned or raised value. It alone writes
the protocol — READY, DISPATCHED, RESULT, END — to a marker file of the evaluation directory, each line authenticated
with HMAC-SHA256 under a key that leaves the request file before the subject's process exists; the parent keeps only
authentic lines (`cli_invocation._protocol`, `_await`). What the subject writes to its stdout or stderr goes to files
of the evaluation directory, never to the protocol. Decision table after DISPATCHED:

* RESULT read -> SUBJECT_ABSENT (REFUTED: every observable here is positive); UNSUPPORTED (equals over a callable);
  HARNESS_FAILED (a failure the controller reported); NON_CONTROLLER_SIGNAL (the subject's process ended by a signal
  the controller did not send, §9.3); OBSERVED, REFUTED, `"the subject ended the process before the observable (exit
  N)"` (its process ended by an exit status before the observable); OBSERVED, REFUTED (an answer on the subject's
  channel the agent did not write); otherwise OBSERVED with `verdict_of`, `detail` the facts' JSON;
* no RESULT, the controller exited by a status: HARNESS_FAILED; by a signal: NON_CONTROLLER_SIGNAL unless the
  controller's ledger holds it (an interruption);
* no RESULT at the window's end with the process still there: SUBJECT_DEADLINE with the class's `ON_DEADLINE`;
  nothing left and no exit status reported: HARNESS_FAILED. Every conclusion after DISPATCHED goes through
  python_callable._after_dispatch.

Differences from the Cycle-1 harness's facts, none of which turns a verdict into SATISFIED: an attribute of the
raised exception whose read raises is reported in `raised_attrs_unserializable` (the Cycle-1 harness died on it: an
exit after DISPATCHED, REFUTED) — REFUTED either way; a value whose serialisation raises anything is unserializable;
an operation the subject's process fails to answer (a subject that replaced its own `sys.modules` entry with an object
without a namespace, for instance) is a harness failure the controller reports — HARNESS_FAILED, where the Cycle-1
harness's exit was REFUTED.

**Enforcement: PARTIAL.** `WEAKEST_PATH`, cli_invocation's: the subject runs in a process of its own as the harness
user, with that user's filesystem and network; it can read the evaluation directory, never the key, and builds no
fact. Isolation, not a sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import secrets
import time
from collections.abc import Mapping

from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.probe import cli_invocation as ci
from aisef2.probe.protocol import (
    ExecutionEnv, HarnessProbe, Observation, ObservationKind, ProbeMetadata, RevisionRef,
)
from aisef2.probe.python_callable import (
    _COLLECT_S, _GRACE_S, _MARK, _WAIT_S, LOCATOR, _after_dispatch, _evaluation_dir, _inside, _plain, _scrubbed_env,
    window_of,
)
from aisef2.runtime.process_range import ProcessRange, RangeError
from aisef2.product.contract import plain
from aisef2.product.spec import ProductProofSpec

PROBE_ID = "probe.python_callable_v2"
WEAKEST_PATH = ci.WEAKEST_PATH  # PARTIAL: the subject runs in a process of its own, a child of the controller
#: every module this probe takes behaviour from is a source of its digest (§35): the Cycle-1 helpers, cli_invocation's
#: subject process and protocol reader, and this module (its classes and controller script)
PROBE_SOURCES = ("probe/protocol.py", "probe/python_callable.py", "probe/cli_invocation.py",
                 "probe/python_callable_v2.py")
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


def _file_ok(name, file) -> bool:
    """One workspace file: a flat name, and either a text with its newline or a hex byte string."""
    shaped = isinstance(name, str) and _WS_NAME.fullmatch(name) is not None and isinstance(file, Mapping)
    text = shaped and set(file) == {"text", "newline"} and isinstance(file["text"], str) and file["newline"] in _NEWLINES
    raw = shaped and set(file) == {"bytes_hex"} and _is_hex(file["bytes_hex"])
    return text or raw


def _workspace_ok(workspace) -> bool:
    """A well-formed workspace: a mapping of well-formed files (an empty one is well-formed)."""
    return isinstance(workspace, Mapping) and all(_file_ok(name, file) for name, file in workspace.items())


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


#: The harness script — the controller (B1, V2.0 release charter §7). Probe-owned; runs in `-I` mode and never imports,
#: resolves or calls the subject, nor puts the revision on its own path: the subject's process (cli_invocation.AGENT) is
#: started before DISPATCHED and asked for one operation at a time; every fact is built here from its answers. The
#: protocol goes to the marker file named in the request and nowhere else, each line authenticated with the
#: evaluation's key, which leaves the request file before the subject's process exists.
HARNESS = r'''
import hashlib, hmac, json, os, queue, subprocess, sys, threading
ask_path = sys.argv[1]
req = json.loads(open(ask_path, encoding="utf-8").read())
with open(ask_path, "w", encoding="utf-8") as f:
    f.write("{}")
KEY, nonce = bytes.fromhex(req["key"]), req["nonce"]
root, work = os.path.realpath(req["root"]), req["work"]
name, _, chain = req["locator"].partition(":")
proto = open(req["protocol"], "wb")
def emit(tag, body=""):
    mac = hmac.new(KEY, (tag + "\n" + body).encode("utf-8"), hashlib.sha256).hexdigest()
    proto.write((req["mark"] + " " + tag + " " + nonce + " " + mac + (" " + body if body else "") + "\n").encode("utf-8"))
    proto.flush()
    os.fsync(proto.fileno())
said = threading.Lock()
def conclude(facts):
    # one RESULT: the facts, or — when the subject's window ends first — the controller's own deadline (B1: the
    # verdict never rests on the range merely being alive; a controller that is stopped reports nothing)
    if said.acquire(blocking=False):
        emit("RESULT", json.dumps(facts))
        emit("END")
def deadline():
    timer = threading.Timer(req["window"], conclude, ({"deadline": True},))
    timer.daemon = True
    timer.start()
emit("READY")
agent = subprocess.Popen([req["interpreter"], "-I", "-B", "-X", "pycache_prefix=" + req["agent_pycache"], "-c",
                          req["agent"], root, work], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=open(os.path.join(work, "agent.log"), "wb"), cwd=root, env=req["env"])
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
class Ended(Exception):
    pass
def answered(op):
    got = ask(op)
    if got is None or "tampered" in got or "agent_failure" in got:
        raise Ended(got)
    return got
def ended(got):
    if got is None:
        code = agent.wait()
        if code < 0:
            return {"subject_signal": -code}
        return {"subject": "present", "hard_exit": True, "exit_code": code}
    if "tampered" in got:
        return {"subject": "present", "tampered": got["tampered"]}
    return {"harness_failure": "the subject's process failed an operation: " + got["agent_failure"]}
def inside(got):
    places = [got["file"]] if got["file"] else got["path"]
    return any(os.path.realpath(p).startswith(root + os.sep) for p in places)
def value_of(t):
    got = {"subject": "present", "resolved": True}
    hexed = t.get("bytes_hex", t.get("memoryview_hex"))
    if hexed is not None:
        got["returned_bytes_hex"] = hexed
    elif "json" in t:
        got["returned"] = t["json"]
    else:
        got["returned_unserializable"] = t["unserializable"]
    return got
def main():
    if answer_to(0) is None:
        return None
    emit("DISPATCHED")
    deadline()
    got = answered({"op": "import", "name": name})
    if "raised" in got:
        missing = got.get("missing")
        if missing and (name == missing or name.startswith(missing + ".")):
            return {"subject": "absent"}
        return {"subject": "present", "resolved": False, "error": got["raised"]}
    if not inside(got):
        return {"subject": "absent", "note": "resolves only outside the revision"}
    got = answered({"op": "resolve", "chain": chain.split(".")})
    if got.get("absent"):
        return {"subject": "absent"}
    if "raised" in got:
        return {"subject": "present", "resolved": False, "error": got["raised"]}
    if req["cls"] == "exists":
        return {"subject": "present", "resolved": True}
    if req["cls"] == "equals":
        if got["callable"]:
            return {"subject": "present", "resolved": True,
                    "unsupported": "equality over a callable subject is not offered"}
        return value_of(answered({"op": "value"}))
    if not got["callable"]:
        return {"subject": "present", "resolved": False, "error": "not callable"}
    got = answered({"op": "call", "args": req["args"], "kwargs": req["kwargs"], "attrs": req["attrs"]})
    if "returned" in got:
        return value_of(got["returned"])
    facts = {"subject": "present", "resolved": True, "raised": got["raised"]}
    if req["attrs"]:
        facts["raised_attrs"], facts["raised_attrs_unserializable"] = {}, []
        for a in req["attrs"]:
            t = got["attrs"][a]
            if "json" in t:
                facts["raised_attrs"][a] = t["json"]
            elif not t.get("missing"):
                facts["raised_attrs_unserializable"].append(a)
    return facts
try:
    facts = main()
except Ended as e:
    facts = ended(e.args[0])
except BaseException as e:
    facts = {"harness_failure": "the harness raised " + type(e).__name__}
if facts is not None:
    if not ("subject_signal" in facts or "tampered" in facts or facts.get("hard_exit") or "harness_failure" in facts):
        wrong = finish()
        if wrong is not None:
            facts = {"subject": "present", "tampered": wrong}
    conclude(facts)
try:
    agent.stdin.close()
except OSError:
    pass
'''


def _harness_argv(interpreter: str, ask: str, pycache: str) -> list[str]:
    """The harness command line: isolated mode, no bytecode written, the bytecode cache under a fresh prefix — every
    control on the command line, because `-I` discards every PYTHON* variable (P7-FINDING-001). The subject's process
    gets the same controls on its own command line (HARNESS), under the same fresh prefix."""
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
        return ("interpreter: the ExecutionEnv's Python interpreter exists and launches under -I",
                "checkout: the revision's checkout is a readable directory",
                "workspace: the evaluation directory and the stimulus's workspace files can be written",
                "protocol: the harness writes READY, then DISPATCHED before it touches the subject, to the marker "
                "file within the harness watchdog (ExecutionEnv.timeout_s)")

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
        failed = ci._preflight(at, env)
        if failed is not None:
            return failed
        stim = dict(pi["stimulus"])
        try:
            holder = _evaluation_dir(self._scratch)
        except OSError as e:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"the evaluation directory cannot be created: "
                                                                     f"{type(e).__name__}")
        with ci._disposed(holder) as work:
            if _inside(work, at.root):
                return Observation(ObservationKind.HARNESS_FAILED, detail="the evaluation directory lies inside the "
                                                                         "revision checkout: refused")
            nonce, key = secrets.token_hex(16), secrets.token_hex(32)
            ask, proto = os.path.join(work, "request.json"), os.path.join(work, "protocol.log")
            pycache, tmp = os.path.join(work, "pycache"), os.path.join(work, "tmp")
            ws = os.path.realpath(os.path.join(work, "ws"))
            try:
                for d in (pycache, ws, tmp):
                    os.mkdir(d)   # fresh and empty: no other evaluation's bytecode, workspace or temporary files
                _write_workspace(ws, stim.get("workspace", {}))
            except OSError as e:
                return Observation(ObservationKind.HARNESS_FAILED, detail=f"the workspace cannot be written: "
                                                                         f"{type(e).__name__}")
            # the subject's process shares the controller's fresh bytecode prefix: -B on both command lines, nothing
            # is written there; B6: its temporary directory is the evaluation's own
            request = {"mark": _MARK, "nonce": nonce, "key": key, "root": at.root, "locator": subject["locator"],
                       "cls": cls, "args": _substituted(stim.get("args", []), ws),
                       "kwargs": _substituted(stim.get("kwargs", {}), ws),
                       "attrs": list(dict(pi["observable"]).get("attrs", {})), "protocol": proto, "work": work,
                       "interpreter": env.interpreter, "agent": ci.AGENT, "agent_pycache": pycache,
                       "env": {**_scrubbed_env(), "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp},
                       "window": window_of(pi["observable"])}
            pathlib.Path(ask).write_text(json.dumps(_plain(request)), encoding="utf-8")
            log = open(os.path.join(work, "harness.log"), "wb")  # closed once the range has started
            try:
                run = ProcessRange(f"probe {spec.id}", _harness_argv(env.interpreter, ask, pycache), cwd=at.root,
                                   env=_scrubbed_env(), output=log, grace_s=_GRACE_S, wait_s=_WAIT_S)
                try:
                    run.start()
                    if self._on_range is not None:
                        self._on_range(run)
                except (RangeError, OSError) as e:
                    return Observation(ObservationKind.HARNESS_FAILED, detail=f"the harness cannot launch: "
                                                                             f"{type(e).__name__}")
            finally:
                log.close()
            try:
                return _watch(run, proto, nonce, key, cls, pi["observable"], env, ws)
            finally:
                run.release()  # RangeNotEmpty / RangeEscaped propagate: a leak is never silent (§17.1)


def _watch(run, proto: str, nonce: str, key: str, cls: str, observable, env: ExecutionEnv, ws: str) -> Observation:
    """cli_invocation's watch over this probe's lines: READY and DISPATCHED under the harness watchdog, then RESULT under
    the subject's window; the exit is lifecycle evidence, the marker file read to its end after it (§9.4). The facts
    are read with the workspace path replaced back by `<ws>` before any comparison."""
    state, seen = ci._await(run, proto, nonce, key, "DISPATCHED", time.monotonic() + env.timeout_s)
    if state != "LINE":
        return ci._harness_failure(run, state, seen, env.timeout_s)
    window = window_of(observable)
    state, seen = ci._await(run, proto, nonce, key, "RESULT", time.monotonic() + window + env.timeout_s)
    if state == "TIMEOUT":
        if run.members():   # B1: the controller's own timer would have spoken at W; a range alive and silent is no verdict
            return _after_dispatch(run, ci._silent(window, env))
        if run.wait(_COLLECT_S) is None:   # nothing of it is left, and the range never said how it ended
            return _after_dispatch(run, Observation(ObservationKind.HARNESS_FAILED,
                                                    detail="the harness process ended and its exit status was "
                                                           "never reported"))
        seen = ci._protocol(proto, nonce, key)
    if "RESULT" in seen:
        facts = json.loads(seen["RESULT"][0])
        if facts.get("deadline"):
            return _after_dispatch(run, ci._deadline(cls, window, ON_DEADLINE))
        return _after_dispatch(run, _concluded(cls, observable, _unsubstituted(facts, ws)))
    return _after_dispatch(run, ci._no_result(run))


def _concluded(cls: str, observable, facts: dict) -> Observation:
    """What the controller's RESULT says — only the controller writes it (B1): the subject's process ended by a signal
    the controller did not send (NON_CONTROLLER_SIGNAL, §9.3), or by an exit status before the observable (REFUTED);
    a harness failure it reported; an absent subject; an answer on the subject's channel the agent did not write
    (REFUTED); equality asked of a callable (UNSUPPORTED); or the facts, decided."""
    if "subject_signal" in facts:
        return Observation(ObservationKind.NON_CONTROLLER_SIGNAL,
                           detail=f"the subject's process ended by signal {facts['subject_signal']} after DISPATCHED, "
                                  "and this controller's signal ledger is empty: it did not send it")
    if "harness_failure" in facts:
        return Observation(ObservationKind.HARNESS_FAILED, detail=facts["harness_failure"])
    if facts.get("hard_exit"):
        return Observation(ObservationKind.OBSERVED, BehaviorVerdict.REFUTED,
                           detail=f"the subject ended the process before the observable (exit {facts['exit_code']})")
    if facts.get("subject") == "absent":   # every observable here is positive: not observed over an absent subject
        return Observation(ObservationKind.SUBJECT_ABSENT, BehaviorVerdict.REFUTED, detail=facts.get("note", ""))
    if "tampered" in facts:
        return Observation(ObservationKind.OBSERVED, BehaviorVerdict.REFUTED, detail=json.dumps(facts))
    if "unsupported" in facts:
        return Observation(ObservationKind.UNSUPPORTED, detail=facts["unsupported"])
    return Observation(ObservationKind.OBSERVED, verdict_of(cls, observable, facts), detail=json.dumps(facts))


METADATA = ProbeMetadata(PROBE_ID, DIGEST, spec_class)
