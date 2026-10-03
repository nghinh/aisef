"""RFC §9 — probe kind `process_effect`, the scenario probe (Cycle 2, WP-2.3.1; CYCLE2-PROBE-TAXONOMY-PROPOSAL §4).

**Subject.** `kind = process_effect`, locator `"<module>:<Class>"` or `"<module>:<callable>"`. The module is located
with the import system's path finder inside the revision (its root and, if present, `src/`) without executing
anything — python_callable's inside() rule, as cli_invocation applies it; a module that does not resolve, resolves
only outside the checkout, or does not define the name is absent *at this revision*: SUBJECT_ABSENT before any step
runs. A module that resolves and raises on import is a present subject that does not work: OBSERVED, REFUTED.

**Stimulus.** `{"scenario": [step, ...]}`, every step a mapping whose `"step"` names its kind in the closed vocabulary
`STEPS` (kind -> required fields, optional fields); each kind's fields have one typed shape (`_SHAPES`, keyed by the
same vocabulary). Anything else — an unknown kind, a missing or extra field, a wrongly typed one — gives the spec no
class: UNSUPPORTED -> INVALID_SPEC at admission (`ProbeMetadata.observation_class`), never a default meaning.

| step | fields | meaning |
|---|---|---|
| `workspace` | `files: {name: {text, newline?} or {bytes_hex}}` | flat names, written byte-exactly into the fresh workspace before anything runs; at most one, first |
| `construct` | `args, kwargs` | `instance = Subject(*args, **kwargs)`; at most one |
| `call` | `args, kwargs, method?, as?` | on the instance when there is one, else on the subject; the result bound to `as` |
| `expect_raises` | `args, kwargs, exception, method?, attrs?` | the call raises exactly that type name, every declared attribute equal after JSON serialisation |
| `write` | `path, (text, newline?) or bytes_hex, append?` | the harness itself writes (or appends to) `<ws>/name`, never through the subject |
| `edit_jsonl` | `path, line, field, value` | the harness rewrites one JSON line's field (the line re-serialised compactly, its key order kept) |
| `subprocess` | `argv: ["-m", module, ...], expect_exit?` | one child of the harness: the revision's module run as `__main__` under the same isolation |
| `fault` | `fault: <id of FAULTS>` | DECISION-2: the next call / expect_raises / subprocess step sees one controlled fault |

A step that raises where it should not, a missing method, an expect_raises that does not match, a subprocess that does
not exit as declared, an edit_jsonl on a line that is not a JSON object with that field: the scenario stops there and
the observation is REFUTED with that step's index and kind in `detail` (`refuted`), whatever the class.

**Fault step (DECISION-2).** `FAULTS` is a closed table in this module (so in the digest and the capability identity):
id -> (module, attribute, exception type name). No callable, shell string, path or developer file can select or
shape a fault, and nothing the subject returns or prints can: the harness reads the table entry the parent put in
the request. Right before the next step's call the harness replaces that one attribute with a stand-in whose first
invocation raises the declared type (later invocations pass through to the original); right after the call, in a
`finally`, it restores the original and asserts mechanically that the attribute IS the original object again. A
failed restoration ends the scenario as a harness failure (`{"harness_failure": ...}` -> HARNESS_FAILED, never a
verdict). A fault not followed by a call, expect_raises or subprocess step is refused at admission. The step's trace
records the fault and whether it fired.

**Placeholder.** `<ws>` is the only token: a string of a step's args, kwargs or argv that is `<ws>` or starts with
`<ws>/` gets the workspace's absolute path (`<ws>/x` becomes the workspace path, a `/`, then `x`, on every platform);
nothing else is substituted. On the way out every occurrence of the workspace path (as given and resolved) in a
reported value — returned results, exception attributes, JSON fields — is replaced by `<ws>` before comparison.

**Observable classes.** One bounded window `within_s` per scenario: every step, from DISPATCHED to RESULT, completes
inside it; an expired window is REFUTED for every class (`ON_DEADLINE`).

| class | observable | SATISFIED when (the scenario completed) |
|---|---|---|
| `scenario_returns` | `{"returns": json}` / `{"returns_bytes_hex": hex}` / `{"returns_name": a, "equals_name": b}` | the last call returned that value / those bytes; or the two bound results are equal (neither unserializable) |
| `scenario_raises` | `{"raises": true}` (the last step is expect_raises) | the last step raised as declared |
| `scenario_files` | `{"files": {"<ws>/name": shape}}` | every named file matches its shape |

File shapes (one per file, closed): `{"sha256": hex}`, `{"equals_before": true}` (the file's digest, or its absence,
is what it was right after the workspace step — before the first other step), `{"absent": true}`, `{"line_count":
n}` (newline-terminated lines, plus an unterminated last one), `{"final_byte": "\\n"}` and `{"jsonl": {"line": i,
"field": f, "equals": json}}`. Results are serialised as python_callable does (a JSON round trip); bytes are reported
as hex (`last_returned_bytes_hex`, `{"bytes_hex": ...}` when bound), anything else by its type name
(`last_unserializable`), which never equals a JSON expectation.

**Class table (DECISION-1).** `CLASS_TABLE`: each class measures the one declared scenario exhaustively (the domain
is that step sequence alone). A scenario whose fault step witnesses a universally quantified property (a crash at any
point) measures one declared fault at one declared call: a bounded witness, never a proof of the universal property;
a contract that derives such a property from it declares `bounded_witness_measurement` (enforcement stays PARTIAL).

**Harness.** As cli_invocation (whose watch primitives and subject process are imported, never copied): the evaluation
directory (`_evaluation_dir`, refused inside the checkout) holds the request, the marker file, the harness log, fresh
empty bytecode caches, `tmp/` (the subject's temporary directory — B6) and `ws/` (the subject's workspace, working
directory and HOME). B1 (V2.0 release charter §7): the probe's process is a controller that never imports, constructs
or calls the subject; the subject's process (`cli_invocation.AGENT`, started before DISPATCHED) runs each construct
and call the controller asks for and answers with what it did; the workspace, write, edit_jsonl and subprocess steps,
every file fact, the trace and the facts are the controller's own, and the controller alone writes the protocol to the
marker file, each line authenticated with the evaluation's key (READY, DISPATCHED before the subject's module is
touched, `STEP i` before each step, RESULT, END). The subject's descriptors 0/1/2 are redirected onto the null device
and binary capture files in its own process, so nothing the subject writes reaches the protocol. The standard text streams' newline handling is pinned (C2-P2-FINDING-001); every file the harness
writes is written in binary mode. A subprocess step runs `[interpreter, -I, -B, -X pycache_prefix=<fresh>, -X utf8=1,
-c SUBPROCESS, <checkout>, -m module, ...]` with the working directory in the workspace and the scrubbed environment:
the interpreter is the ExecutionEnv's (never the harness process's own `sys.executable`), and SUBPROCESS only puts
the revision on the path and runs the module; the child is a member of the probe's process range, so what it leaves
running is the range's residual (§17.1), stopped by the range's release — never by the probe.

Parent decision table after DISPATCHED (as cli_invocation): RESULT read -> SUBJECT_ABSENT, HARNESS_FAILED (a harness
failure the controller reported), NON_CONTROLLER_SIGNAL (the subject's process ended by a signal the controller did not
send), REFUTED (an answer on the subject's channel the agent did not write), or OBSERVED with `verdict_of` — the
subject's process ending during a step is in RESULT as an observation, REFUTED with that step and the steps completed
before it; no RESULT and an exit status -> the controller failed: HARNESS_FAILED; a signal -> NON_CONTROLLER_SIGNAL
unless the controller's ledger holds it (an interruption); the window's end with the process present ->
SUBJECT_DEADLINE, REFUTED; nothing left and no status reported -> HARNESS_FAILED unless the ledger holds a stop. Every conclusion after
DISPATCHED goes through python_callable._after_dispatch (C2-P2-FINDING-002).

**Enforcement: PARTIAL.** `WEAKEST_PATH`: the subject and every subprocess step run as the harness user, with that
user's filesystem and network; the subject cannot read the key nor build a fact; isolation, not a sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import secrets
import time

from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.probe import cli_invocation as ci
from aisef2.probe.protocol import (
    ExecutionEnv, HarnessProbe, Observation, ObservationKind, ProbeMetadata, RevisionRef,
)
from aisef2.probe.python_callable import (
    _COLLECT_S, _GRACE_S, _MARK, _WAIT_S, _after_dispatch, _evaluation_dir, _inside, window_of,
)
from aisef2.runtime.process_range import ProcessRange, RangeError
from aisef2.product.contract import plain
from aisef2.product.spec import ProductProofSpec

PROBE_ID = "probe.process_effect"
#: every module this probe takes behaviour from is a source of its digest (§35): the Cycle-1 helpers, cli_invocation's
#: watch primitives, and this module (the step vocabulary, the fault table and the harness scripts are in it)
PROBE_SOURCES = ("probe/protocol.py", "probe/python_callable.py", "probe/cli_invocation.py", "probe/process_effect.py")
LOCATOR = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*")
CLASSES = ("scenario_returns", "scenario_raises", "scenario_files")
#: Each class's meaning of an expired window (§9.2): the scenario did not complete, so nothing it declares was seen.
ON_DEADLINE = {"scenario_returns": BehaviorVerdict.REFUTED, "scenario_raises": BehaviorVerdict.REFUTED,
               "scenario_files": BehaviorVerdict.REFUTED}
#: The closed step vocabulary: kind -> (required fields, optional fields); the key "step" names the kind.
STEPS = {
    "workspace": (("files",), ()),
    "construct": (("args", "kwargs"), ()),
    "call": (("args", "kwargs"), ("method", "as")),
    "expect_raises": (("args", "kwargs", "exception"), ("method", "attrs")),
    "write": (("path",), ("text", "newline", "bytes_hex", "append")),
    "edit_jsonl": (("path", "line", "field", "value"), ()),
    "subprocess": (("argv",), ("expect_exit",)),
    "fault": (("fault",), ()),
}
#: DECISION-2: the closed fault table, id -> (module, attribute, exception type name). Part of this module's source,
#: hence of the probe digest; a step names an id, never a callable, a shell string or a file.
FAULTS = {
    "os.replace": ("os", "replace", "OSError"),
    "os.rename": ("os", "rename", "OSError"),
    "os.fsync": ("os", "fsync", "OSError"),
    "os.write": ("os", "write", "OSError"),
}
#: the steps a fault applies to: exactly the one that follows it
FAULTED = ("call", "expect_raises", "subprocess")
FILE_SHAPES = ("sha256", "equals_before", "absent", "line_count", "final_byte", "jsonl")
_ONE = "the one declared scenario (its steps, in order, in one harness process): the domain is that scenario alone"
#: DECISION-1: what each class measures, under which quantifier, and every (observation facts -> verdict) row
#: `verdict_of` / `ON_DEADLINE` answer (tests/v2/test_probe_process_effect_units.py exercises every row).
CLASS_TABLE = {
    "scenario_returns": {"quantifier": "exhaustive_finite_domain", "domain": _ONE, "enforcement": "PARTIAL", "rows": (
        ("window expired", "REFUTED"), ("a step refuted", "REFUTED"), ("the process ended during a step", "REFUTED"),
        ("completed, the last call returned the declared value", "SATISFIED"),
        ("completed, the last call returned another value, bytes or an unserializable value", "REFUTED"),
        ("completed, the last call returned the declared bytes", "SATISFIED"),
        ("completed, the two bound results are equal", "SATISFIED"),
        ("completed, the two bound results differ or one is unserializable", "REFUTED"))},
    "scenario_raises": {"quantifier": "exhaustive_finite_domain", "domain": _ONE, "enforcement": "PARTIAL", "rows": (
        ("window expired", "REFUTED"), ("a step refuted", "REFUTED"), ("the process ended during a step", "REFUTED"),
        ("completed, the last step raised the declared type with every declared attribute", "SATISFIED"))},
    "scenario_files": {"quantifier": "exhaustive_finite_domain", "domain": _ONE, "enforcement": "PARTIAL", "rows": (
        ("window expired", "REFUTED"), ("a step refuted", "REFUTED"), ("the process ended during a step", "REFUTED"),
        ("completed, every named file matches its shape", "SATISFIED"),
        ("completed, a named file does not match its shape", "REFUTED"))},
}
FAULT_WITNESS = ("a fault step measures one declared fault at one declared call: a bounded witness of a property "
                 "quantified over every crash point, never a proof of it (DECISION-1)")
WEAKEST_PATH = ("the subject, in a process of its own, and every subprocess step run as the harness user with that "
                "user's filesystem and network access; the subject can read the evaluation directory but not the key "
                "that authenticates the protocol, and the controller alone builds the facts and writes the protocol; "
                "-I interpreter isolation, a scrubbed environment, fresh working and temporary directories and "
                "harness-owned bytecode caches (-X pycache_prefix, -B) are isolation, not a sandbox")
PLACEHOLDER = ci.PLACEHOLDER
_CONTENT = ("text", "newline", "bytes_hex")
_FLAT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")
_IDENT = re.compile(r"[A-Za-z_]\w*")
_MODULE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")


def _probe_digest() -> str:
    root = pathlib.Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for rel in PROBE_SOURCES:
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


DIGEST = _probe_digest()


# --------------------------------------------------------------------------------------- shapes

def _flat_ok(name) -> bool:
    """A workspace name: one component, never starting with a dot (so never `..`)."""
    return isinstance(name, str) and _FLAT.fullmatch(name) is not None


def _ws_path_ok(key) -> bool:
    return isinstance(key, str) and key.startswith(PLACEHOLDER + "/") and _flat_ok(key[len(PLACEHOLDER) + 1:])


def _ident_ok(value) -> bool:
    return isinstance(value, str) and _IDENT.fullmatch(value) is not None


def _content_of(step: dict) -> dict:
    return {k: step[k] for k in _CONTENT if k in step}


def _invocation_ok(step: dict) -> bool:
    """construct / call: positional args, keyword args by identifier, an optional method and binding name."""
    return isinstance(step["args"], list) and isinstance(step["kwargs"], dict) \
        and all(_ident_ok(k) for k in step["kwargs"]) and all(_ident_ok(step[k]) for k in ("method", "as") if k in step)


def _workspace_ok(step: dict) -> bool:
    files = step["files"]
    return isinstance(files, dict) and bool(files) and all(_flat_ok(n) and ci._content_ok(c) for n, c in files.items())


def _expect_ok(step: dict) -> bool:
    attrs = step.get("attrs", {})
    return _invocation_ok(step) and _ident_ok(step["exception"]) and isinstance(attrs, dict) \
        and all(_ident_ok(k) for k in attrs)


def _write_ok(step: dict) -> bool:
    return _ws_path_ok(step["path"]) and ci._content_ok(_content_of(step)) \
        and ("append" not in step or isinstance(step["append"], bool))


def _edit_ok(step: dict) -> bool:
    return _ws_path_ok(step["path"]) and ci._is_int(step["line"]) and step["line"] >= 0 \
        and isinstance(step["field"], str) and bool(step["field"])


def _subprocess_ok(step: dict) -> bool:
    argv = step["argv"]
    return isinstance(argv, list) and len(argv) >= 2 and all(isinstance(a, str) for a in argv) and argv[0] == "-m" \
        and _MODULE.fullmatch(argv[1]) is not None and ci._is_int(step.get("expect_exit", 0))


def _fault_ok(step: dict) -> bool:
    return isinstance(step["fault"], str) and step["fault"] in FAULTS


#: the typed shape of each step kind, keyed by the vocabulary itself (an unknown kind is refused before this is read)
_SHAPES = {"workspace": _workspace_ok, "construct": _invocation_ok, "call": _invocation_ok, "expect_raises": _expect_ok,
           "write": _write_ok, "edit_jsonl": _edit_ok, "subprocess": _subprocess_ok, "fault": _fault_ok}


def _step_ok(step) -> bool:
    """One step of the closed vocabulary with exactly its typed fields."""
    if not isinstance(step, dict) or not isinstance(step.get("step"), str) or step["step"] not in STEPS:
        return False
    required, optional = STEPS[step["step"]]
    fields = set(step) - {"step"}
    return set(required) <= fields <= {*required, *optional} and _SHAPES[step["step"]](step)


def _scenario_ok(scenario) -> bool:
    """Every step well formed; at most one workspace step, first; at most one construct; binding names distinct;
    every fault followed by the step it applies to."""
    if not isinstance(scenario, list) or not scenario or not all(_step_ok(s) for s in scenario):
        return False
    kinds = [s["step"] for s in scenario]
    names = [s["as"] for s in scenario if "as" in s]
    if kinds.count("construct") > 1 or "workspace" in kinds[1:] or len(set(names)) != len(names):
        return False
    return all(i + 1 < len(kinds) and kinds[i + 1] in FAULTED for i, k in enumerate(kinds) if k == "fault")


_FILE_SHAPE_OK = {
    "sha256": lambda v: isinstance(v, str) and ci._SHA.fullmatch(v) is not None,
    "equals_before": lambda v: v is True,
    "absent": lambda v: v is True,
    "line_count": lambda v: ci._is_int(v) and v >= 0,
    "final_byte": lambda v: isinstance(v, str) and len(v.encode("utf-8")) == 1,
    "jsonl": lambda v: isinstance(v, dict) and set(v) == {"line", "field", "equals"} and ci._is_int(v["line"])
    and v["line"] >= 0 and isinstance(v["field"], str) and bool(v["field"]),
}


def _file_shape_ok(shape) -> bool:
    if not isinstance(shape, dict) or len(shape) != 1:
        return False
    kind, value = next(iter(shape.items()))
    return kind in _FILE_SHAPE_OK and _FILE_SHAPE_OK[kind](value)


def observation_class(observable, stimulus) -> str | None:
    """The class a spec's observable asks for over its scenario, or None when this probe cannot give it a meaning."""
    if window_of(observable) is None:
        return None
    obs = {k: v for k, v in plain(dict(observable)).items() if k != "within_s"}
    stim = plain(dict(stimulus))
    if set(stim) != {"scenario"} or not _scenario_ok(stim["scenario"]):
        return None
    kinds = [s["step"] for s in stim["scenario"]]
    names = {s["as"] for s in stim["scenario"] if "as" in s}
    if set(obs) == {"raises"}:
        return "scenario_raises" if obs["raises"] is True and kinds[-1] == "expect_raises" else None
    if set(obs) == {"files"}:
        files = obs["files"]
        ok = isinstance(files, dict) and bool(files) and all(_ws_path_ok(k) and _file_shape_ok(v)
                                                             for k, v in files.items())
        return "scenario_files" if ok else None
    if set(obs) == {"returns_name", "equals_name"}:
        a, b = obs["returns_name"], obs["equals_name"]
        return "scenario_returns" if _ident_ok(a) and _ident_ok(b) and a != b and {a, b} <= names else None
    if "call" not in kinds:
        return None
    if set(obs) == {"returns"}:
        return "scenario_returns"
    if set(obs) == {"returns_bytes_hex"} and isinstance(obs["returns_bytes_hex"], str) \
            and ci._HEX.fullmatch(obs["returns_bytes_hex"]) is not None:
        return "scenario_returns"
    return None


def spec_class(spec: ProductProofSpec) -> str | None:
    """Harness metadata (`ProbeMetadata.observation_class`): the class `spec` asks of this probe, or None."""
    subject = dict(spec.probe_input["subject"])
    if subject.get("kind") != "process_effect" or not isinstance(subject.get("locator"), str) \
            or not LOCATOR.fullmatch(subject["locator"]):
        return None
    return observation_class(spec.probe_input["observable"], spec.probe_input["stimulus"])


# --------------------------------------------------------------------------------------- verdicts

def _same(a, b) -> bool:
    """JSON equality: the canonical texts are equal (true is not 1, 1 is not 1.0; key order is not significant)."""
    x, y = (json.dumps(v, sort_keys=True) for v in (a, b))
    return x == y


def _returns_hold(obs: dict, facts: dict) -> bool:
    if "returns" in obs:
        return "last_returned" in facts and _same(facts["last_returned"], obs["returns"])
    if "returns_bytes_hex" in obs:
        return facts.get("last_returned_bytes_hex") == obs["returns_bytes_hex"].lower()
    bound = facts.get("bound", {})
    a, b = bound.get(obs["returns_name"]), bound.get(obs["equals_name"])
    return a is not None and "unserializable" not in a and _same(a, b)


def _raises_hold(obs: dict, facts: dict) -> bool:
    trace = facts.get("trace", [])
    return bool(trace) and trace[-1].get("kind") == "expect_raises" \
        and str(trace[-1].get("outcome", "")).startswith("raised:")


def _identity(fact: dict) -> dict:
    return {"absent": True} if fact.get("absent") is True else {"sha256": fact.get("sha256")}


def _jsonl_holds(v: dict, after: dict) -> bool:
    row = after.get("jsonl", {}).get(str(v["line"]))
    return isinstance(row, dict) and v["field"] in row and _same(row[v["field"]], v["equals"])


#: one check per file shape, keyed by the shape vocabulary (a shape outside it is refused at admission)
_FILE_HOLDS = {
    "sha256": lambda v, after, before: after.get("sha256") == v,
    "equals_before": lambda v, after, before: before is not None and _identity(after) == before,
    "absent": lambda v, after, before: after.get("absent") is True,
    "line_count": lambda v, after, before: after.get("line_count") == v,
    "final_byte": lambda v, after, before: after.get("final_byte_hex") == v.encode("utf-8").hex(),
    "jsonl": lambda v, after, before: _jsonl_holds(v, after),
}


def _files_hold(obs: dict, facts: dict) -> bool:
    after, before = facts.get("files", {}), facts.get("before", {})
    out = True
    for key, shape in obs["files"].items():
        kind, value = next(iter(dict(shape).items()))
        name = ci._ws_name(key)
        out = out and after.get(name) is not None and _FILE_HOLDS[kind](value, after[name], before.get(name))
    return out


_HOLDS = {"scenario_returns": _returns_hold, "scenario_raises": _raises_hold, "scenario_files": _files_hold}


def verdict_of(cls: str, observable, facts: dict) -> BehaviorVerdict:
    """What a present subject's facts say about the observable when the scenario ended before the window closed: a
    refuted step (or a process that ended during one) refutes every class. Pure over the facts; no clock."""
    ok = facts.get("refuted") is None and _HOLDS[cls](dict(observable), facts)
    return BehaviorVerdict.SATISFIED if ok else BehaviorVerdict.REFUTED


def _substitute(value, ws: str):
    """`<ws>` as a whole string, or followed by `/`, becomes the workspace path (then `/` and the rest); lists and
    mapping values are walked; nothing else is ever substituted."""
    if isinstance(value, str):
        if value == PLACEHOLDER:
            return ws
        return ws + value[len(PLACEHOLDER):] if value.startswith(PLACEHOLDER + "/") else value
    if isinstance(value, list):
        return [_substitute(v, ws) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, ws) for k, v in value.items()}
    return value


def _resolved(step: dict, ws: str) -> dict:
    """A step as the harness script runs it: `<ws>` substituted in args, kwargs and argv; a path named by its file;
    content as hex bytes; a fault as its FAULTS entry."""
    out = {k: _substitute(v, ws) if k in ("args", "kwargs", "argv") else v for k, v in step.items() if k not in _CONTENT}
    if "path" in step:
        out["path"] = ci._ws_name(step["path"])
    if _content_of(step):
        out["data_hex"] = ci._bytes_of(_content_of(step)).hex()
    if "files" in step:
        out["files"] = {n: ci._bytes_of(c).hex() for n, c in step["files"].items()}
    if "fault" in step:
        out["patch"] = list(FAULTS[step["fault"]])
    return out


def _observed_files(observable) -> dict:
    """The files the observable names, each with the (line, field) its jsonl shape reads, if any."""
    out = {}
    for key, shape in dict(observable).get("files", {}).items():
        jsonl = dict(shape).get("jsonl")
        out[ci._ws_name(key)] = [[jsonl["line"], jsonl["field"]]] if jsonl is not None else []
    return out


#: The harness script — the controller (B1, V2.0 release charter §7). Probe-owned; runs in `-I` mode and never imports,
#: constructs or calls the subject, nor puts the revision on its own path: the subject's process (cli_invocation.AGENT)
#: is started before DISPATCHED and asked for one construct or call at a time; the workspace, write, edit_jsonl and
#: subprocess steps, every file fact, the trace and the facts are the controller's own. Its protocol goes to the marker
#: file named in the request and nowhere else, each line authenticated with the evaluation's key, which leaves the
#: request file before the subject's process exists.
HARNESS = r'''
import builtins, hashlib, hmac, importlib, json, os, queue, subprocess, sys, threading
from importlib.machinery import PathFinder
ask_path = sys.argv[1]
req = json.loads(open(ask_path, encoding="utf-8").read())
with open(ask_path, "w", encoding="utf-8") as f:
    f.write("{}")
KEY, nonce = bytes.fromhex(req["key"]), req["nonce"]
root, work, ws = os.path.realpath(req["root"]), req["work"], req["ws"]
name, _, attr = req["locator"].partition(":")
SEARCH = [p for p in (root, os.path.join(root, "src")) if os.path.isdir(p)]
proto = open(req["protocol"], "wb")
FSYNC = os.fsync
FORMS = sorted({ws, os.path.realpath(ws)}, key=len, reverse=True)
MISSING = object()
def emit(tag, body=""):
    mac = hmac.new(KEY, (tag + "\n" + body).encode("utf-8"), hashlib.sha256).hexdigest()
    proto.write((req["mark"] + " " + tag + " " + nonce + " " + mac + (" " + body if body else "") + "\n").encode("utf-8"))
    proto.flush()
    FSYNC(proto.fileno())
emit("READY")
agent = subprocess.Popen([req["interpreter"], "-I", "-B", "-X", "pycache_prefix=" + req["agent_pycache"], "-X", "utf8=1",
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
class Leak(Exception):
    pass
class Ended(Exception):
    pass
def answered(op):
    got = ask(op)
    if got is None or "tampered" in got:
        raise Ended(got)
    return got
def inside(spec):
    places = [spec.origin] if spec.origin and spec.has_location else list(spec.submodule_search_locations or [])
    return any(os.path.realpath(p).startswith(root + os.sep) for p in places)
def resolve(dotted, search):
    parts, spec, path = dotted.split("."), None, search
    for i in range(len(parts)):
        spec = PathFinder.find_spec(".".join(parts[:i + 1]), path)
        if spec is None:
            return None
        path = spec.submodule_search_locations
        if path is None and i + 1 < len(parts):
            return None
    return spec
def unws(value):
    if isinstance(value, str):
        for form in FORMS:
            value = value.replace(form, "<ws>")
        return value
    if isinstance(value, list):
        return [unws(v) for v in value]
    if isinstance(value, dict):
        return {unws(k): unws(v) for k, v in value.items()}
    return value
def reported(t):
    if "bytes_hex" in t:
        data = bytes.fromhex(t["bytes_hex"])
        for form in FORMS:
            data = data.replace(form.encode("utf-8"), b"<ws>")
        return {"bytes_hex": data.hex()}
    if "json" in t:
        return {"json": unws(t["json"])}
    if "memoryview_hex" in t:
        return {"unserializable": "memoryview"}
    return {"unserializable": t["unserializable"]}
def same(a, b):
    x, y = (json.dumps(v, sort_keys=True) for v in (a, b))
    return x == y
def row_of(raw, field):
    if raw is None:
        return None
    try:
        rec = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(rec, dict):
        return None
    return {field: unws(rec[field])} if field in rec else {}
def count_lines(data):
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
def file_fact(n, probes):
    path = os.path.join(ws, n)
    if not os.path.isfile(path):
        return {"absent": True}
    with open(path, "rb") as f:
        data = f.read()
    count, lines = count_lines(data), data.split(b"\n")
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "line_count": count,
            "final_byte_hex": data[-1:].hex() if data else None,
            "jsonl": {str(line): row_of(lines[line] if line < count else None, field) for line, field in probes}}
def files_now():
    return {n: file_fact(n, probes) for n, probes in req["files"].items()}
def identity(fact):
    return {"absent": True} if fact.get("absent") else {"sha256": fact["sha256"]}
def guarded(state, call):
    step = state["fault"]
    if step is None:
        return call()
    module, target, error = step["patch"]
    owner = importlib.import_module(module)
    original, kind, fired = getattr(owner, target), getattr(builtins, error), state["fired"]
    def fault(*args, **kwargs):
        if fired:
            return original(*args, **kwargs)
        fired.append(step["fault"])
        raise kind("controlled fault " + step["fault"])
    setattr(owner, target, fault)
    try:
        return call()
    finally:
        setattr(owner, target, original)
        if getattr(owner, target) is not original:
            raise Leak("the fault " + step["fault"] + " was not restored after step " + str(state["i"]))
def subject_call(step, state, attrs):
    op = {"op": "call", "args": step["args"], "kwargs": step["kwargs"], "attrs": attrs}
    if "method" in step:
        op["method"] = step["method"]
    if state["fault"] is not None:
        op["patch"] = list(state["fault"]["patch"]) + [state["fault"]["fault"]]
    got = answered(op)
    if "leak" in got:
        raise Leak("the fault " + state["fault"]["fault"] + " was not restored after step " + str(state["i"]))
    if got.get("fired"):
        state["fired"].append(state["fault"]["fault"])
    return got
def do_workspace(step, state):
    for n, data in step["files"].items():
        with open(os.path.join(ws, n), "wb") as f:
            f.write(bytes.fromhex(data))
    return {"outcome": "ok"}
def do_construct(step, state):
    got = answered({"op": "construct", "args": step["args"], "kwargs": step["kwargs"]})
    if "raised" in got:
        return {"outcome": "refuted:construct raised " + got["raised"]}
    return {"outcome": "ok"}
def unresolved(step, got):
    if got.get("no_method"):
        return {"outcome": "refuted:method " + step["method"] + " missing"}
    if "resolve_raised" in got:
        return {"outcome": "refuted:resolving the method raised " + got["resolve_raised"]}
    return None
def do_call(step, state):
    got = subject_call(step, state, [])
    refused = unresolved(step, got)
    if refused is not None:
        return refused
    if "raised" in got:
        return {"outcome": "refuted:raised " + got["raised"]}
    state["last"] = reported(got["returned"])
    if "as" in step:
        state["bound"][step["as"]] = state["last"]
    return {"outcome": "ok"}
def do_expect(step, state):
    wanted = step.get("attrs", {})
    got = subject_call(step, state, list(wanted))
    refused = unresolved(step, got)
    if refused is not None:
        return refused
    if "returned" in got:
        return {"outcome": "refuted:returned; " + step["exception"] + " was not raised"}
    kind = got["raised"]
    if kind != step["exception"]:
        return {"outcome": "refuted:raised " + kind + ", not " + step["exception"]}
    seen = {}
    for a, want in wanted.items():
        t = got["attrs"][a]
        if t.get("missing"):
            return {"outcome": "refuted:" + kind + " has no attribute " + a}
        if "error" in t:
            return {"outcome": "refuted:reading " + kind + "." + a + " raised " + t["error"]}
        seen[a] = reported(t)
        if not same(seen[a], {"json": want}):
            return {"outcome": "refuted:" + kind + "." + a + " is not the declared value"}
    state["raised"] = {"type": kind, "attrs": seen}
    return {"outcome": "raised:" + kind}
def do_write(step, state):
    try:
        with open(os.path.join(ws, step["path"]), "ab" if step.get("append") else "wb") as f:
            f.write(bytes.fromhex(step["data_hex"]))
    except OSError as e:
        return {"outcome": "refuted:write " + step["path"] + " raised " + type(e).__name__}
    return {"outcome": "ok"}
def do_edit(step, state):
    path, n = os.path.join(ws, step["path"]), step["line"]
    if not os.path.isfile(path):
        return {"outcome": "refuted:edit_jsonl: no file " + step["path"]}
    with open(path, "rb") as f:
        data = f.read()
    lines = data.split(b"\n")
    if n >= count_lines(data):
        return {"outcome": "refuted:edit_jsonl: " + step["path"] + " has no line " + str(n)}
    try:
        rec = json.loads(lines[n].decode("utf-8"))
    except ValueError:
        return {"outcome": "refuted:edit_jsonl: line " + str(n) + " is not JSON"}
    if not isinstance(rec, dict) or step["field"] not in rec:
        return {"outcome": "refuted:edit_jsonl: line " + str(n) + " has no field " + step["field"]}
    rec[step["field"]] = step["value"]
    lines[n] = json.dumps(rec, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as f:
        f.write(b"\n".join(lines))
    return {"outcome": "ok"}
def do_subprocess(step, state):
    prefix = os.path.join(work, "pycache-step" + str(state["i"]))
    os.mkdir(prefix)
    cmd = [req["interpreter"], "-I", "-B", "-X", "pycache_prefix=" + prefix, "-X", "utf8=1", "-c", req["boot"],
           root] + step["argv"]
    done = guarded(state, lambda: subprocess.run(cmd, cwd=ws, env=req["env"], stdin=subprocess.DEVNULL,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    want = step.get("expect_exit", 0)
    if done.returncode != want:
        return {"outcome": "refuted:the subprocess exited " + str(done.returncode) + ", not " + str(want),
                "exit": done.returncode}
    return {"outcome": "ok", "exit": done.returncode}
def do_fault(step, state):
    return {"outcome": "ok"}
HANDLERS = {"workspace": do_workspace, "construct": do_construct, "call": do_call, "expect_raises": do_expect,
            "write": do_write, "edit_jsonl": do_edit, "subprocess": do_subprocess, "fault": do_fault}
def run(steps, state):
    trace = state["trace"]
    for i, step in enumerate(steps):
        if state["before"] is None and step["step"] != "workspace":
            state["before"] = {n: identity(f) for n, f in files_now().items()}
        emit("STEP", str(i))
        state["i"], state["fired"] = i, []
        entry = {"i": i, "kind": step["step"]}
        entry.update(HANDLERS[step["step"]](step, state))
        if state["fault"] is not None:
            entry.update({"fault": state["fault"]["fault"], "fired": bool(state["fired"])})
        trace.append(entry)
        state["fault"] = step if step["step"] == "fault" else None
        if entry["outcome"].startswith("refuted:"):
            return trace, {"step": i, "kind": step["step"], "why": entry["outcome"][len("refuted:"):]}
    return trace, None
def ended(got, state):
    if got is not None:
        return {"subject": "present", "tampered": got["tampered"]}
    code = agent.wait()
    if code < 0:
        return {"subject_signal": -code}
    return {"subject": "present", "hard_exit": True, "exit_code": code, "trace": state["trace"] if state else [],
            "refuted": {"step": state["i"] if state else None,
                        "why": "the process ended with exit status " + str(code) + " before the scenario completed"}}
def main():
    if answer_to(0) is None:
        return None
    emit("DISPATCHED")
    spec = resolve(name, SEARCH)
    if spec is None and PathFinder.find_spec(name.split(".")[0], SEARCH) is None:
        spec = resolve(name, None)
    if spec is None or not inside(spec):
        return {"subject": "absent", "note": "" if spec is None else "resolves only outside the revision"}
    got = ask({"op": "import", "name": name})
    if got is None or "tampered" in got:
        return ended(got, None)
    if "raised" in got:
        return {"subject": "present", "trace": [],
                "refuted": {"step": None, "kind": "import", "why": "importing the subject raised " + got["raised"]}}
    got = ask({"op": "resolve", "chain": [attr]})
    if got is None or "tampered" in got:
        return ended(got, None)
    if got.get("absent"):
        return {"subject": "absent", "note": "the module does not define " + attr}
    if "raised" in got:
        return {"subject": "present", "trace": [],
                "refuted": {"step": None, "kind": "import", "why": "resolving the subject raised " + got["raised"]}}
    state = {"instance": MISSING, "bound": {}, "fault": None, "raised": None, "last": None, "before": None, "trace": [],
             "i": None, "fired": []}
    try:
        trace, refuted = run(req["steps"], state)
    except Leak as e:
        return {"harness_failure": str(e)}
    except Ended as e:
        return ended(e.args[0], state)
    if state["before"] is None:
        state["before"] = {n: identity(f) for n, f in files_now().items()}
    facts = {"subject": "present", "trace": trace, "bound": state["bound"], "raised": state["raised"],
             "before": state["before"], "files": files_now()}
    if refuted is not None:
        facts["refuted"] = refuted
    last = state["last"] or {}
    if "json" in last:
        facts["last_returned"] = last["json"]
    if "bytes_hex" in last:
        facts["last_returned_bytes_hex"] = last["bytes_hex"]
    if "unserializable" in last:
        facts["last_unserializable"] = last["unserializable"]
    return facts
try:
    facts = main()
except BaseException as e:
    facts = {"harness_failure": "the harness raised " + type(e).__name__}
if facts is not None:
    if not ("subject_signal" in facts or "tampered" in facts or facts.get("hard_exit") or "harness_failure" in facts):
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

#: The boot of a subprocess step: the revision on the path, then its module run as __main__ (probe-owned, like HARNESS).
SUBPROCESS = r'''
import os, runpy, sys
for s in (sys.__stdout__, sys.__stderr__):
    if s is not None:
        s.reconfigure(newline="\n")
root = os.path.realpath(sys.argv[1])
sys.path[:0] = [p for p in (root, os.path.join(root, "src")) if os.path.isdir(p)]
module = sys.argv[3]
sys.argv = [module] + sys.argv[4:]
runpy.run_module(module, run_name="__main__", alter_sys=True)
'''


def _harness_argv(interpreter: str, ask: str, pycache: str) -> list[str]:
    """The harness command line: isolated mode, no bytecode written, the bytecode cache under a fresh prefix and UTF-8
    mode — each on the command line, because `-I` discards every PYTHON* variable (P7-FINDING-001)."""
    return [interpreter, "-I", "-B", "-X", f"pycache_prefix={pycache}", "-X", "utf8=1", "-c", HARNESS, ask]


def _prepare(work: str, root: str, locator: str, steps: list, files: dict, nonce: str, key: str,
             interpreter: str) -> tuple[str, str, str]:
    """Lay out the evaluation directory: an empty workspace (the workspace step writes it), fresh bytecode caches (the
    controller's and the subject process's), the evaluation's own temporary directory and the request. Returns
    (request path, workspace, bytecode prefix)."""
    ws, pycache, agent_pycache, tmp = (os.path.join(work, n) for n in ("ws", "pycache", "pycache-agent", "tmp"))
    for d in (ws, pycache, agent_pycache, tmp):
        os.mkdir(d)     # fresh and empty: no other evaluation's bytecode, and none from the checkout
    request = {"mark": _MARK, "nonce": nonce, "key": key, "root": root, "locator": locator, "work": work, "ws": ws,
               "protocol": os.path.join(work, "protocol.log"), "interpreter": interpreter, "env": ci._child_env(ws, tmp),
               "boot": SUBPROCESS, "steps": [_resolved(s, ws) for s in steps], "files": files, "agent": ci.AGENT,
               "agent_pycache": agent_pycache, "cwd": ws}
    ask = os.path.join(work, "request.json")
    pathlib.Path(ask).write_text(json.dumps(request), encoding="utf-8")
    return ask, ws, pycache


class ProcessEffectProbe(HarnessProbe):
    id = PROBE_ID
    digest = DIGEST

    def __init__(self, on_range=None, scratch: str | None = None) -> None:
        """`on_range` and `scratch` as python_callable and cli_invocation: harness-owned hooks — the range is acquired
        into the story's StoryScope (its ledger is the one signal authority, §9.3), and each evaluation gets a fresh
        directory under the controller-owned scratch, or a temporary directory of its own."""
        self._on_range, self._scratch = on_range, scratch

    def enforcement(self) -> Enforcement:
        return Enforcement.PARTIAL

    def harness_preconditions(self) -> tuple[str, ...]:
        return ("interpreter: the ExecutionEnv's Python interpreter exists and launches under -I",
                "checkout: the revision's checkout is a readable directory",
                "evaluation directory: creatable, outside the checkout, with the workspace and the bytecode cache",
                "protocol: the harness writes READY, then DISPATCHED before it touches the subject, to the marker "
                "file within the harness watchdog (ExecutionEnv.timeout_s)",
                "fault table: every fault the scenario names is restored after its step, asserted by identity")

    def observe(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> Observation:
        pi = spec.probe_input
        subject = dict(pi["subject"])
        if subject.get("kind") != "process_effect":
            return Observation(ObservationKind.UNSUPPORTED, detail=f"subject kind {subject.get('kind')!r} is not "
                                                                   "process_effect")
        if not isinstance(subject.get("locator"), str) or not LOCATOR.fullmatch(subject["locator"]):
            return Observation(ObservationKind.UNSUPPORTED, detail=f"locator {subject.get('locator')!r} is not "
                                                                   "module.path:Name — a path is never accepted")
        cls = spec_class(spec)
        if cls is None:
            return Observation(ObservationKind.UNSUPPORTED, detail="observable/stimulus is not a supported class "
                                                                   f"{CLASSES} over a scenario of the closed step "
                                                                   "vocabulary with a bounded window (within_s); "
                                                                   "refused, not degraded")
        failed = ci._preflight(at, env)
        if failed is not None:
            return failed
        try:
            holder = _evaluation_dir(self._scratch)
        except OSError as e:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"the evaluation directory cannot be created: "
                                                                     f"{type(e).__name__}")
        with ci._disposed(holder) as work:
            return self._observe_in(work, spec.id, cls, subject["locator"], plain(dict(pi["stimulus"]))["scenario"],
                                    plain(dict(pi["observable"])), at, env)

    def _observe_in(self, work: str, spec_id: str, cls: str, locator: str, steps: list, observable: dict,
                    at: RevisionRef, env: ExecutionEnv) -> Observation:
        if _inside(work, at.root):
            return Observation(ObservationKind.HARNESS_FAILED, detail="the evaluation directory lies inside the "
                                                                     "revision checkout: refused")
        nonce, key = secrets.token_hex(16), secrets.token_hex(32)
        try:
            ask, ws, pycache = _prepare(work, at.root, locator, steps, _observed_files(observable), nonce, key,
                                        env.interpreter)
        except OSError as e:
            return Observation(ObservationKind.HARNESS_FAILED, detail="the evaluation directory cannot be "
                                                                     f"prepared: {type(e).__name__}")
        log = open(os.path.join(work, "harness.log"), "wb")  # closed once the range has started
        try:
            run = ProcessRange(f"probe {spec_id}", _harness_argv(env.interpreter, ask, pycache), cwd=ws,
                               env=ci._child_env(ws), output=log, grace_s=_GRACE_S, wait_s=_WAIT_S)
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
            return _watch(run, os.path.join(work, "protocol.log"), nonce, key, cls, observable, env)
        finally:
            run.release()  # RangeNotEmpty / RangeEscaped propagate: a leak is never silent (§17.1)


def _watch(run, proto: str, nonce: str, key: str, cls: str, observable: dict, env: ExecutionEnv) -> Observation:
    """cli_invocation's watch over this probe's lines: READY and DISPATCHED under the harness watchdog, then RESULT
    under the scenario's one window; the exit is lifecycle evidence, the marker file read to its end after it (§9.4)."""
    state, seen = ci._await(run, proto, nonce, key, "DISPATCHED", time.monotonic() + env.timeout_s)
    if state != "LINE":
        return ci._harness_failure(run, state, seen, env.timeout_s)
    window = window_of(observable)
    state, seen = ci._await(run, proto, nonce, key, "RESULT", time.monotonic() + window)
    if state == "TIMEOUT":
        if run.members():   # measured on the range: the scenario's process is still there at W
            at = seen["STEP"][-1] if seen.get("STEP") else "none"
            return _after_dispatch(run, Observation(ObservationKind.SUBJECT_DEADLINE, ON_DEADLINE[cls],
                                                    detail=f"the scenario's {window:g}s observation window expired "
                                                           f"at step {at} ({cls})"))
        if run.wait(_COLLECT_S) is None:   # nothing of it is left, and the range never said how it ended
            return _after_dispatch(run, Observation(ObservationKind.HARNESS_FAILED,
                                                    detail="the harness process ended and its exit status was "
                                                           "never reported"))
        seen = ci._protocol(proto, nonce, key)
    if "RESULT" in seen:
        return _after_dispatch(run, _concluded(cls, observable, json.loads(seen["RESULT"][0])))
    return _after_dispatch(run, ci._no_result(run))


def _concluded(cls: str, observable: dict, facts: dict) -> Observation:
    """What the controller's RESULT says — only the controller writes it (B1): the subject's process ended by a signal
    the controller did not send (NON_CONTROLLER_SIGNAL, §9.3); an absent subject; a harness failure it reported; an
    answer on the subject's channel the agent did not write (REFUTED); or an observation — a hard exit of the subject's
    process during a step is one, REFUTED with the step named."""
    if "subject_signal" in facts:
        return Observation(ObservationKind.NON_CONTROLLER_SIGNAL,
                           detail=f"the subject's process ended by signal {facts['subject_signal']} after DISPATCHED, "
                                  "and this controller's signal ledger is empty: it did not send it")
    if facts.get("subject") == "absent":   # every observable here is positive: not observed over an absent subject
        return Observation(ObservationKind.SUBJECT_ABSENT, BehaviorVerdict.REFUTED, detail=facts.get("note", ""))
    if "harness_failure" in facts:
        return Observation(ObservationKind.HARNESS_FAILED, detail="the harness failed its own scenario: "
                                                                 + str(facts["harness_failure"]))
    if "tampered" in facts:
        return Observation(ObservationKind.OBSERVED, BehaviorVerdict.REFUTED, detail=json.dumps(facts))
    return Observation(ObservationKind.OBSERVED, verdict_of(cls, observable, facts), detail=json.dumps(facts))


METADATA = ProbeMetadata(PROBE_ID, DIGEST, spec_class)
