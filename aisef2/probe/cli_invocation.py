"""RFC §9 — probe kind `cli_invocation` (Cycle 2, WP-2.2.1; CYCLE2-PROBE-TAXONOMY-PROPOSAL §2).

**Subject.** `kind = cli_invocation`, locator `"<module>:__main__"` (the module of the revision run as `__main__` through
`runpy.run_module`; for a package that is its `__main__` submodule) or `"<module>:<callable>"` (an entry function
called with the argv list; its return value is its exit status, as `sys.exit(main(argv))` would take it). The module
is located with the import system's path finder against the revision checkout (its root and, if present, `src/`)
without executing anything; a module that does not resolve, or resolves only outside the checkout, is absent *at this
revision*. A console-script name is never accepted: it resolves through the environment, not the revision.

**Stimulus.** `{"argv": [...], "stdin": null | {"text", "newline"} | {"bytes_hex"}, "workspace": {name: content},
"pre": [{"argv": [...]}, ...]}`. Workspace files are written byte-exactly into the subject's workspace before any
invocation; `<ws>` is the only placeholder — an argv entry `<ws>/name` becomes that file's absolute path, nothing else
is ever substituted. The pre-steps invoke the same subject, in the same child process, in order, each captured on its
own; one that does not exit 0 makes the observation REFUTED with its index in `detail`.

**Observable classes.** Every observable declares its bounded window `within_s` (§9.2).

| class | observable | SATISFIED when | the window expires |
|---|---|---|---|
| `exits` | `{"exit_code": N, "within_s": W}` | the invocation returned with that exit code | REFUTED |
| `exits_streams` | adds `"stdout"` / `"stderr"`, each a shape | `exits`, and each named stream matches its shape | REFUTED |
| `exits_files` | adds `"files": {"<ws>/name": shape}` | `exits`, and each named file matches its shape | REFUTED |
| `blocks` | `{"blocks": true, "within_s": W}` | the invocation has not returned when W closes | SATISFIED |

Stream shapes (a closed set, compared over the captured bytes; prose matching is not offered): an exact string or
`{"text": s, "newline": nl}` (the text's newlines written as `nl`, default `"\\n"`, compared as bytes), `{"contains":
[s, ...]}` (every string present as bytes), `{"regex": r}` (`re.search` over the utf-8 decoding), `{"lines": n}` (the
number of lines) and `{"first_word": w}`. File shapes: `{"sha256": hex}`, `{"text": s, "newline": nl}` (its digest),
`{"absent": true}` and `{"equals_before": true}` (the file's digest, or its absence, is what it was before the main
invocation — the harness records every named file before and after). Exit codes are recorded as CPython reports them:
`SystemExit(None)` is 0, an int is itself, any other status is 1 and is printed to stderr; an uncaught exception is
recorded by its type name, with a traceback on stderr and exit code 1. The raw status is kept beside the code.

**Captured streams.** The subject's stdout and stderr are redirected at the descriptor level (`os.dup2` onto files of
the evaluation directory, one pair per invocation), so nothing the subject writes can reach the protocol channel: a
forged protocol line on stdout is captured bytes like any other. Each capture keeps at most `STREAM_CAP` bytes (the
subject may write more; the fact says `truncated`, and an exact shape is then REFUTED), and a stream's facts are the
bytes captured when the invocation returned — bytes a lingering thread writes later are not the invocation's.

**Protocol channel (DESIGN-CHECK-1).** The taxonomy proposal suggested a dedicated descriptor (fd 3) on POSIX and a
marker file on Windows. The owned process range (`aisef2/runtime/process_range.py`) launches the target through an
anchor process that forwards no extra descriptor, and the runtime is out of this package's scope, so the channel is a
harness-owned marker file inside the evaluation directory on every platform — a design choice inside F5, not an
exception. The child writes `<mark> READY <nonce>`, `<mark> DISPATCHED <nonce>` (right before the first invocation),
`<mark> PRE <nonce> <i>` / `<mark> MAIN <nonce> {"before": ...}` (which invocation is running), `<mark> RESULT <nonce>
<facts>` and `<mark> END <nonce>` to that file only, flushing and fsyncing each line. The parent polls the file: it
reads the whole file, keeps the complete lines (ending in a newline) that carry the mark and this evaluation's nonce
— an unterminated last line is never a protocol line — and the poll decides only when to look, never what was said.
Under the harness watchdog (`ExecutionEnv.timeout_s`) it waits for DISPATCHED; under the spec's window for RESULT.
The exit is lifecycle evidence, asked of the range with a non-blocking wait at each poll: when the process has
exited, the file is read once more, to its end, before anything is concluded (RFC §9.4 applied to the file: no
timing window orders the exit and the last write). Decision table, after DISPATCHED:

* RESULT read -> OBSERVED with `verdict_of` (SUBJECT_ABSENT when the child found no subject);
* no RESULT, the process exited by a status: the subject ended the process itself (`os._exit`, a hard exit) — OBSERVED
  with the process's exit code and the capture files as the streams (`hard_exit` in the facts); a hard exit during a
  pre-step is REFUTED with that step's index;
* no RESULT, the process exited by a signal: NON_CONTROLLER_SIGNAL (§9.3) unless the controller's own ledger holds the
  signal, which is an interruption (`ProbeInterrupted`, as python_callable._after_dispatch);
* no RESULT at the window's end with the process still there (measured on the range, never assumed): SUBJECT_DEADLINE
  with the class's `ON_DEADLINE` verdict; the caller's `release` stops it — the probe never signals anything.

Before DISPATCHED the watchdog runs: an exit with no READY/DISPATCHED, or none within the watchdog, is HARNESS_FAILED
(UNRUNNABLE): the harness did not start or broke its protocol.

**Evaluation directory.** `python_callable._evaluation_dir` (fresh; refused inside the checkout): it holds the request,
the protocol file, the harness's own log, a fresh empty bytecode cache (`-X pycache_prefix`, with `-B` and `-I` on the
command line — P7-FINDING-001) and `ws/`, the subject's workspace, working directory and HOME. The child runs with
`python_callable._scrubbed_env` plus `LC_ALL=C.UTF-8`, `LANG=C.UTF-8`, `PYTHONUTF8=1`, `TZ=UTC`, `HOME=<ws>`; because
`-I` discards every `PYTHON*` variable, UTF-8 mode is pinned on the command line too (`-X utf8=1`), the way the
bytecode prefix is. The child flushes the interpreter's original stdout/stderr objects between invocations so each
capture holds what its invocation wrote; it never writes to them.

**Enforcement: PARTIAL.** Weakest path (`WEAKEST_PATH`): the subject runs inside the harness's child process as the
harness user, with that user's filesystem and network; it can read the request and the protocol file. `-I`, the
scrubbed environment, the fresh working directory and the harness-owned bytecode cache are isolation, not a sandbox.
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
#: python_callable's frozen helpers are imported, so this probe's behaviour depends on that source too (§35).
PROBE_SOURCES = ("probe/protocol.py", "probe/python_callable.py", "probe/cli_invocation.py")
LOCATOR = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*")
CLASSES = ("exits", "exits_streams", "exits_files", "blocks")
#: Each class's meaning of an expired observation window (§9.2): what "not returned by W" says about the observable.
ON_DEADLINE = {"exits": BehaviorVerdict.REFUTED, "exits_streams": BehaviorVerdict.REFUTED,
               "exits_files": BehaviorVerdict.REFUTED, "blocks": BehaviorVerdict.SATISFIED}
WEAKEST_PATH = ("the subject runs inside the harness's child process as the harness user, with that user's filesystem "
                "and network access, and can read the request and the protocol file; -I interpreter isolation, a "
                "scrubbed environment, a fresh working directory and a harness-owned bytecode cache "
                "(-X pycache_prefix, -B) are isolation, not a sandbox")
STREAM_CAP = 8 * 1024 * 1024   # bytes kept per captured stream; a subject may write more, the fact says truncated
STREAM_SHAPES = ("text", "contains", "regex", "lines", "first_word")
FILE_SHAPES = ("sha256", "text", "absent", "equals_before")
PLACEHOLDER = "<ws>"
POLL_S = 0.02   # how often the parent looks at the protocol file; it never decides content
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*(?:/[A-Za-z0-9_][A-Za-z0-9._-]*)*")
_HEX = re.compile(r"(?:[0-9a-fA-F]{2})*")
_SHA = re.compile(r"[0-9a-f]{64}")


def _probe_digest() -> str:
    root = pathlib.Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for rel in PROBE_SOURCES:
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


DIGEST = _probe_digest()


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
        return isinstance(v, str)
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


def observation_class(observable, stimulus) -> str | None:
    """The class a spec's observable asks for, or None when this probe cannot give it a meaning."""
    if window_of(observable) is None:
        return None
    obs = {k: v for k, v in plain(dict(observable)).items() if k != "within_s"}
    if not _stimulus_ok(plain(dict(stimulus))):
        return None
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


def _stream_matches(shape, fact: dict) -> bool:
    data = _stream_bytes(fact)
    if isinstance(shape, str):
        shape = {"text": shape}
    if "text" in shape:
        return not fact.get("truncated") and data == _bytes_of(shape)
    if "contains" in shape:
        return all(s.encode("utf-8") in data for s in shape["contains"])
    if "regex" in shape:
        return re.search(shape["regex"], data.decode("utf-8", "replace")) is not None
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


def verdict_of(cls: str, observable, facts: dict) -> BehaviorVerdict:
    """What a present subject's facts say about the observable, when the invocation returned (or ended the process)
    before the window closed. Pure over the facts and the capture files they name; no clock."""
    if facts.get("pre_failed") is not None or cls == "blocks":
        return BehaviorVerdict.REFUTED   # the state was never built; or blocks: the invocation returned
    obs = dict(observable)
    ok = facts.get("exit_code") == obs["exit_code"]
    if cls == "exits_streams":
        ok = ok and all(_stream_matches(obs[k], facts.get(k, {})) for k in ("stdout", "stderr") if k in obs)
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


#: The harness script. Probe-owned; runs in `-I` mode with the checkout on sys.path; its protocol goes to the marker
#: file named in the request and nowhere else; the subject's streams are redirected at the descriptor level.
HARNESS = r'''
import hashlib, importlib, json, os, runpy, sys, traceback
from importlib.machinery import PathFinder
req = json.loads(open(sys.argv[1], encoding="utf-8").read())
nonce, root, work, ws, cap = req["nonce"], os.path.realpath(req["root"]), req["work"], req["ws"], req["cap"]
name, _, attr = req["locator"].partition(":")
sys.path[:0] = [p for p in (root, os.path.join(root, "src")) if os.path.isdir(p)]
proto = open(req["protocol"], "wb")
def emit(tag, body=""):
    line = req["mark"] + " " + tag + " " + nonce + (" " + body if body else "") + "\n"
    proto.write(line.encode("utf-8")); proto.flush(); os.fsync(proto.fileno())
emit("READY")
def inside(spec):
    places = [spec.origin] if spec.origin and spec.has_location else list(spec.submodule_search_locations or [])
    return any(os.path.realpath(p).startswith(root + os.sep) for p in places)
def resolve(dotted):
    parts, spec, path = dotted.split("."), None, None
    for i in range(len(parts)):
        spec = PathFinder.find_spec(".".join(parts[:i + 1]), path)
        if spec is None:
            return None
        path = spec.submodule_search_locations
        if path is None and i + 1 < len(parts):
            return None
    return spec
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
def file_fact(rel):
    path = os.path.join(ws, *rel.split("/"))
    return {"sha256": sha(path)} if os.path.isfile(path) else {"absent": True}
def stream_fact(path):
    size = os.path.getsize(path)
    if size > cap:
        os.truncate(path, cap)
    return {"path": path, "size": min(size, cap), "truncated": size > cap, "sha256": sha(path)}
def flush():
    for s in (sys.__stdout__, sys.__stderr__):
        try:
            s.flush()
        except (OSError, ValueError):
            pass
def plain(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)
def invoke(argv, stdin_path, out_path, err_path):
    flush()
    for fd, path, flags in ((0, stdin_path, os.O_RDONLY), (1, out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC),
                            (2, err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)):
        h = os.open(path, flags)
        os.dup2(h, fd)
        os.close(h)
    sys.argv = [name, *argv]
    raw, raised = None, None
    try:
        if attr == "__main__":
            runpy.run_module(name, run_name="__main__", alter_sys=True)
        else:
            mod = importlib.import_module(name)
            try:
                fn = getattr(mod, attr)
            except AttributeError:
                return {"subject": "absent"}
            raw = fn(list(argv))
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
    return {"exit_status_raw": plain(raw), "exit_code": code, "raised": raised,
            "stdout": stream_fact(out_path), "stderr": stream_fact(err_path)}
def main():
    emit("DISPATCHED")
    spec = resolve(name)
    if attr == "__main__" and spec is not None and spec.submodule_search_locations is not None:
        spec = PathFinder.find_spec(name + ".__main__", spec.submodule_search_locations)
    if spec is None or not inside(spec):
        return {"subject": "absent", "note": "" if spec is None else "resolves only outside the revision"}
    pre = []
    for i, step in enumerate(req["pre"]):
        emit("PRE", str(i))
        r = invoke(step["argv"], os.devnull, os.path.join(work, "pre" + str(i) + ".stdout.bin"),
                   os.path.join(work, "pre" + str(i) + ".stderr.bin"))
        if r.get("subject") == "absent":
            return r
        pre.append(r)
        if r["exit_code"] != 0:
            return {"subject": "present", "pre_failed": i, "pre": pre}
    before = {n: file_fact(n) for n in req["files"]}
    emit("MAIN", json.dumps({"before": before}))
    r = invoke(req["argv"], req["stdin"] or os.devnull, os.path.join(work, "stdout.bin"),
               os.path.join(work, "stderr.bin"))
    if r.get("subject") == "absent":
        return r
    r.update({"subject": "present", "pre": pre, "before": before, "files": {n: file_fact(n) for n in req["files"]}})
    return r
emit("RESULT", json.dumps(main()))
emit("END")
'''


def _harness_argv(interpreter: str, ask: str, pycache: str) -> list[str]:
    """The harness command line: isolated mode, no bytecode written, the bytecode cache under a fresh prefix and UTF-8
    mode — each on the command line, because `-I` discards every PYTHON* variable (P7-FINDING-001)."""
    return [interpreter, "-I", "-B", "-X", f"pycache_prefix={pycache}", "-X", "utf8=1", "-c", HARNESS, ask]


def _child_env(ws: str) -> dict:
    return {**_scrubbed_env(), "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "PYTHONUTF8": "1", "TZ": "UTC",
            "HOME": ws, "USERPROFILE": ws}


def _protocol(path: str, nonce: str) -> dict[str, list[str]]:
    """The protocol lines the marker file holds now, tag -> bodies in order: complete lines only (an unterminated
    last line is not one), carrying the mark and this evaluation's nonce."""
    try:
        data = pathlib.Path(path).read_bytes()
    except OSError:
        return {}
    out: dict[str, list[str]] = {}
    for raw in data.split(b"\n")[:-1]:
        parts = raw.decode("utf-8", "replace").rstrip("\r").split(" ", 3)
        if len(parts) >= 3 and parts[0] == _MARK and parts[2] == nonce:
            out.setdefault(parts[1], []).append(parts[3] if len(parts) == 4 else "")
    return out


def _await(run, path: str, nonce: str, tag: str, until: float) -> tuple[str, dict]:
    """Poll the marker file until a `tag` line is in it ("LINE"), the range reports the process's exit ("EXITED" —
    the file read once more, to its end, first: §9.4) or `until` passes ("TIMEOUT"). The poll never decides content."""
    while True:
        seen = _protocol(path, nonce)
        if tag in seen:
            return "LINE", seen
        if run.wait(0.0) is not None:
            seen = _protocol(path, nonce)
            return ("LINE" if tag in seen else "EXITED"), seen
        left = until - time.monotonic()
        if left <= 0:
            return "TIMEOUT", seen
        time.sleep(min(POLL_S, left))


class CliInvocationProbe(HarnessProbe):
    id = PROBE_ID
    digest = DIGEST

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
        return self._observe(spec.id, cls, subject["locator"], plain(dict(pi["stimulus"])), plain(dict(pi["observable"])),
                             at, env)[0]

    def _observe(self, spec_id: str, cls: str, locator: str, stim: dict, observable, at: RevisionRef,
                 env: ExecutionEnv) -> tuple[Observation, dict | None]:
        """One invocation of the subject in a fresh evaluation directory: the observation and, when the harness
        reported, the facts it reported (capture paths included; they are gone when this returns)."""
        if not os.path.isfile(env.interpreter):
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"interpreter absent: {env.interpreter}"), None
        if not os.path.isdir(at.root):
            return Observation(ObservationKind.HARNESS_FAILED,
                               detail="cannot inspect: the revision checkout is missing"), None
        try:
            holder = _evaluation_dir(self._scratch)
        except OSError as e:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"the evaluation directory cannot be created: "
                                                                     f"{type(e).__name__}"), None
        with holder as work:
            if _inside(work, at.root):
                return Observation(ObservationKind.HARNESS_FAILED, detail="the evaluation directory lies inside the "
                                                                         "revision checkout: refused"), None
            nonce = secrets.token_hex(16)
            files = [_ws_name(k) for k in dict(observable).get("files", {})]   # a frozen observable's keys are sorted
            try:
                ask, ws, pycache = _prepare(work, at.root, locator, stim, files, nonce)
            except OSError as e:
                return Observation(ObservationKind.HARNESS_FAILED, detail="the evaluation directory cannot be "
                                                                         f"prepared: {type(e).__name__}"), None
            log = open(os.path.join(work, "harness.log"), "wb")  # closed once the range has started
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
                return _watch(run, os.path.join(work, "protocol.log"), nonce, cls, stim, observable, env, work, ws)
            finally:
                run.release()  # RangeNotEmpty / RangeEscaped propagate: a leak is never silent (§17.1)


def _prepare(work: str, root: str, locator: str, stim: dict, files: list[str], nonce: str) -> tuple[str, str, str]:
    """Lay out the evaluation directory: the workspace with its byte-exact files, the stdin file, the fresh bytecode
    cache and the request. Returns (request path, workspace, bytecode prefix)."""
    ws, pycache = os.path.join(work, "ws"), os.path.join(work, "pycache")
    os.mkdir(ws)
    os.mkdir(pycache)   # fresh and empty: no other evaluation's bytecode, and none from the checkout
    for name, content in stim.get("workspace", {}).items():
        target = pathlib.Path(ws, *name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_bytes_of(content))
    stdin = None
    if stim.get("stdin") is not None:
        stdin = os.path.join(work, "stdin.bin")
        pathlib.Path(stdin).write_bytes(_bytes_of(stim["stdin"]))
    request = {"mark": _MARK, "nonce": nonce, "root": root, "locator": locator, "work": work, "ws": ws,
               "protocol": os.path.join(work, "protocol.log"), "cap": STREAM_CAP,
               "argv": _substitute(list(stim.get("argv", [])), ws), "stdin": stdin,
               "pre": [{"argv": _substitute(list(p["argv"]), ws)} for p in stim.get("pre", [])], "files": files}
    ask = os.path.join(work, "request.json")
    pathlib.Path(ask).write_text(json.dumps(_plain(request)), encoding="utf-8")
    return ask, ws, pycache


def _watch(run, proto: str, nonce: str, cls: str, stim: dict, observable, env: ExecutionEnv, work: str,
           ws: str) -> tuple[Observation, dict | None]:
    """READY and DISPATCHED under the harness watchdog, then RESULT under the subject's window; the process's exit is
    lifecycle evidence read from the range, and the marker file is read to its end after it (§9.4)."""
    state, seen = _await(run, proto, nonce, "DISPATCHED", time.monotonic() + env.timeout_s)
    if state != "LINE":
        return _harness_failure(run, state, seen, env.timeout_s), None
    window = window_of(observable)
    state, seen = _await(run, proto, nonce, "RESULT", time.monotonic() + window)
    if state == "TIMEOUT":
        if run.members():   # measured on the range: the subject's process is still there at W
            return _after_dispatch(run, Observation(ObservationKind.SUBJECT_DEADLINE, ON_DEADLINE[cls],
                                                    detail=f"the subject's {window:g}s observation window expired "
                                                           f"({cls})")), None
        if run.wait(_COLLECT_S) is None:   # nothing of it is left, and the range never said how it ended
            return Observation(ObservationKind.HARNESS_FAILED,
                               detail="the harness process ended and its exit status was never reported"), None
        seen = _protocol(proto, nonce)
    if "RESULT" in seen:
        facts = json.loads(seen["RESULT"][0])
        if facts.get("subject") == "absent":   # every observable here is positive: not observed over an absent subject
            return _after_dispatch(run, Observation(ObservationKind.SUBJECT_ABSENT, BehaviorVerdict.REFUTED,
                                                    detail=facts.get("note", ""))), None
        return _after_dispatch(run, Observation(ObservationKind.OBSERVED, verdict_of(cls, observable, facts),
                                                detail=json.dumps(_public(facts)))), facts
    return _hard_exit(run, seen, cls, stim, observable, work, ws)


def _hard_exit(run, seen: dict, cls: str, stim: dict, observable, work: str, ws: str) -> tuple[Observation, dict | None]:
    """After DISPATCHED the process ended with no RESULT in the marker file (§9.3 CASES B and C): by a signal the
    controller did not send — NON_CONTROLLER_SIGNAL; by an exit status — the subject ended the process itself, an
    observation of the invocation that was running (its exit code, the capture files as its streams)."""
    code = run.returncode
    if code < 0:
        return _after_dispatch(run, Observation(ObservationKind.NON_CONTROLLER_SIGNAL,
                                                detail=f"the process ended by signal {-code} after DISPATCHED, and "
                                                       "this controller's signal ledger is empty: it did not "
                                                       "send it")), None
    if "MAIN" not in seen and (seen.get("PRE") or stim.get("pre")):
        step = int(seen["PRE"][-1]) if seen.get("PRE") else 0
        facts = {"subject": "present", "pre_failed": step, "exit_code": code, "hard_exit": True}
        return _after_dispatch(run, Observation(ObservationKind.OBSERVED, BehaviorVerdict.REFUTED,
                                                detail=json.dumps(facts))), facts
    before = json.loads(seen["MAIN"][0])["before"] if seen.get("MAIN") else {}
    names = [_ws_name(k) for k in dict(observable).get("files", {})]
    facts = {"subject": "present", "exit_code": code, "hard_exit": True,
             "stdout": _stream_fact(os.path.join(work, "stdout.bin")),
             "stderr": _stream_fact(os.path.join(work, "stderr.bin")), "before": before,
             "files": {n: _file_fact(os.path.join(ws, *n.split("/"))) for n in names}}
    return _after_dispatch(run, Observation(ObservationKind.OBSERVED, verdict_of(cls, observable, facts),
                                            detail=json.dumps(_public(facts)))), facts


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
