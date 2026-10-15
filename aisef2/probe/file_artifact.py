"""RFC §9 — the second probe kind: `file_artifact` (Cycle 2, WP-2.1.1; CYCLE2-PROBE-TAXONOMY-PROPOSAL §3).

**Subject.** `path:<relative posix path>` — a file or a directory of the revision. A locator that is absolute (or
carries a drive letter), holds `..`, an empty or `.` component or a backslash, or reaches its entry through a
symlink or gitlink component is refused (HARNESS_FAILED, the offending part named): the tree is never escaped and a
link is never followed. A blob on the way (`file/x`) is not an escape: the path is simply not in the tree. A symlink
entry itself (mode 120000) is refused for `content` and `grep_count`; for `exists` it is an entry of the tree like
any other. A gitlink (mode 160000) is not a file of this repository and is refused.

**Observable classes.** Every observable declares its bounded observation window `within_s` (§9.2); a spec without
one gives an expired window no meaning and is INVALID_SPEC. Negation is the contract's polarity (§7).

| class | observable | stimulus | SATISFIED when |
|---|---|---|---|
| `exists` | `{"condition": "exists", "within_s": W}` | `{}` | the path is an entry of the tree |
| `content` | `{"sha256": H, ["newline": N,] "within_s": W}` or `{"equals_text": T, "newline": N, "within_s": W}` | `{}` | the blob hashes to H / equals T |
| `grep_count` | `{"matches": M, "within_s": W}` | `{"grep": R, ["suffixes": [".py", ...]]}` | exactly M lines match R, over at least one selected file |
| `python_imports` | `{"matches": M, "within_s": W}` | `{"imports_outside": {"stdlib": B, "allowed": [N, ...]}, ["suffixes": [".py", ...]]}` | exactly M import statements name a module outside the set, over at least one selected file |

`newline` (`"\\n"` or `"\\r\\n"`) declares the line convention: when it is declared the blob's line endings are
normalised to it (CRLF to LF, then LF to the declared one) before hashing or comparing, and `equals_text` is a text
whose lines end in `\\n`; without it `sha256` is over the exact blob bytes. `grep_count` compiles R (a pattern that
does not compile is UNSUPPORTED; one longer than `PATTERN_CAP` is a harness refusal), decodes each selected file as
UTF-8 (a leading byte-order mark is dropped, see below) and counts the lines with at least one match — one per
matching line, never overlapping matches. A directory is walked recursively; `suffixes` selects by file-name suffix,
the default selecting every file. A file holding a NUL byte is binary: skipped and named in the detail. A file that is
not UTF-8 leaves the count unestablished: REFUTED, the file named. A file over `FILE_CAP` bytes is a harness refusal,
never a verdict. `content` over a directory is observed and REFUTED (a tree has no blob). Every class means REFUTED by
an expired window (`ON_DEADLINE`): a read that did not complete in W is not an observation of presence.

**A selection of no file** (V2.1, PM-9, `CAPABILITY_VERSION` 3). `grep_count` and `python_imports` count over the files
a path selects. A path that is in the tree but selects none — a directory holding no file the suffixes take (a
documentation directory, a package whose modules moved), or one file the suffixes do not take — has nothing to count
over, and a count of zero over nothing is not an observation that the files satisfy a prohibition: it is the absence of
the subject, decided by the spec's declaration exactly as a path that is not in the tree (`Absence`, below). A selection
that holds a file is a subject whatever the file holds: an empty file, a file of the byte-order mark alone, a binary file
(`grep_count` skips it and names it; `python_imports` cannot parse it: REFUTED) all keep the verdict they always had.
Only the selection by path and suffix is meant: the files `facts_of` takes, before any is read — never a judgement of
what is in them.

`python_imports` (V2.1, V21-37 — a line regex counted a docstring line beginning `from` as an import and rolled back a
correct story) reads the same files as `grep_count` (default suffix `.py`) and parses each with this interpreter's
`ast`: it counts the `import` / `from ... import` statements (relative imports excluded: they are the project's own)
whose top-level module is neither in `allowed` nor, when `stdlib` is true, in this interpreter's
`sys.stdlib_module_names`. Comments, strings and docstrings are never statements. A file that does not parse leaves the
count unestablished: REFUTED, the file and line named (`file:?` when the parser names none: a NUL byte). A file the
parser cannot take at all — it stops on its own stack or memory limit (`RecursionError`, `MemoryError`) before it can
say what the file is — is a harness refusal, never a verdict (as `FILE_CAP`): UNRUNNABLE, the file named, and the way
out said in the detail. A refusal outranks any file's own answer, whichever comes first: the kind of the result is
the tree's, not the order a reader lists it in (a git tree lists `a.py` before `a/b.py`, a plain directory the
reverse). It sees the syntax only: `importlib.import_module(...)` and `__import__` are calls, not import statements,
and are not counted.

**A byte-order mark.** A UTF-8 byte-order mark at the start of a file is the encoding's signature, not text:
`grep_count` and `python_imports` drop it before they read the file, as CPython's tokenizer drops it (a file Python
imports is a file that parses, and `^` anchors the first line's text). One anywhere else, or a second one after it, is
a character: a syntax error in source, as it is for CPython. A UTF-16 or UTF-32 mark is no UTF-8: the file is not
UTF-8. `content` is over the exact bytes of the blob, the mark included. Two consequences, both stated so that nobody
finds them out from a verdict. The leading mark is not text, so **no `grep_count` pattern sees it** (not U+FEFF, not a
non-ASCII class): a requirement that no file may carry the mark is stated over the bytes, with `content`. And the mark
declares UTF-8: a coding cookie beside it that names anything else (or no codec at all) contradicts it, which is a
syntax error for CPython and is here (`file:?`, the tokenizer names no line). A cookie with no mark is not read: the
probe takes UTF-8 only and says `undecodable` for anything else, as it did before.

**Reading rule — the object store, never the working file.** When the checkout root is itself the top level of a
git repository (a worktree the harness made of the revision), existence, mode and content are read from that
repository's object store at `RevisionRef.sha`: `git ls-tree -z -l -t` for the entry, its size and every tree
component on the way (git stops silently at a component it cannot descend, and that component is then looked up on
its own, so a link on the way is seen before anything is read), `git cat-file blob <oid>` for bytes. The working
file is never opened, so autocrlf, editors, a dirty index, executable bits and the file system's case folding
cannot become authorities, and the implementer's and the verifier's checkouts of one commit read the same bytes by
construction. A repository that does not hold the revision is HARNESS_FAILED ("revision not in the repository"),
never SUBJECT_ABSENT. When the root is not a repository top level (a committed calibration fixture, which the
frozen `calibrate()` names by its placeholder revision), the directory tree at the root is read with the same
refusal rules, names matched exactly against the directory listing (never the file system's case folding) and
links never followed. The decision is by repository presence at the root, made by git's own discovery with
`GIT_CEILING_DIRECTORIES` set to the root's parent — never by the SHA's value. The detail records which was read.

**Absence.** A path that is not in the tree — or, for `grep_count` and `python_imports`, one that selects no file (see
above) — is SUBJECT_ABSENT with the verdict the observable gives the absent subject: REFUTED for `exists` and `content`;
for `grep_count` and `python_imports` the verdict the count gives zero matches (SATISFIED when M is 0), so a
prohibition declared ABSENCE_IS_DECIDABLE decides (§10.2); whether it counts is the spec's declaration, applied by
`protocol.classify_failure`, never here: REQUIRES_SUBJECT drops it for INDETERMINATE(PRECONDITION_ABSENT). The facts of
a selection of none say so (`present` false, `files` 0, the `suffixes` that selected), so the detail of a direct
observation tells a path that is not there from one that selects nothing.

**Bounded matching** (V2.1, PM-13). The regex loop of `grep_count` — the one operation of this probe whose time depends
on the text and the pattern, not on the size of what it reads — runs in a worker process of its own, under the harness
watchdog `ExecutionEnv.timeout_s` (the operator's `timeouts_s.probe`), never in this process. The worker is a harness
script (`GREP_WORKER`, in this module, so in EXECUTION_DIGEST) started as `sys.executable -I -S -B` inside a process
range (`aisef2.runtime.process_range`, §17.1) with a scrubbed environment; it is given the pattern and the bytes of
the selected files by a file of the evaluation directory and gives back the facts the in-process loop always gave, as
numbers by file index, in a second file. Nothing of the subject runs: it holds bytes, it executes none. One deadline
covers the whole operation — the request written, the worker started, the files decoded, the lines matched, the result
read — and a worker that does not give a valid result inside it is a harness failure, UNRUNNABLE (owner ENVIRONMENT),
never a verdict: it hung (DEADLINE: the file, the line being matched and the head of the pattern are named, and the
way out), it could not start (LAUNCH), it ended by an exit status or a signal (CRASHED), it wrote nothing (NO_RESULT),
or what it wrote is not facts of this request (BAD_RESULT: not JSON, a field missing or of another type, more than a
request this size can produce). A failure is never retried here — the same pattern over the same bytes within the same
deadline stops the same way — and the process range is emptied before the observation returns: what the worker
started, a grandchild included, is the range's, and nothing outside the range is signalled. The window `within_s` is
still decided after the read, as before (PM-12): a read that finished is judged by its own window.

**Why git runs outside the owned process range** (design note). The Cycle-1 probe runs the subject inside a P4
process range because the subject is untrusted code that may fork, hang or leave processes behind, and what ended
it must be read from the controller's own signal ledger (§9.3). Here no subject code runs: git is a harness tool,
invoked with an argv this module builds (`shell=False`, the binary resolved once at construction by absolute path),
reading only objects the revision SHA identifies, its output captured as bytes, bounded by `ExecutionEnv.timeout_s`
(the harness watchdog: a git that does not answer in time is HARNESS_FAILED, never a verdict) and by the per-file
size cap; it starts nothing of the subject's. `on_range` and `scratch` are accepted for the harness-owned
constructor convention (PROBE-META-1), recorded and unused. The environment is scrubbed to an allowlist of the
host's (the temporary-directory and system-root variables, and PATH so that git's own helpers load on Windows —
the binary itself is never looked up through it again): no user or system git configuration
(`GIT_CONFIG_NOSYSTEM`, a global config path that does not exist, `HOME` inside a fresh temporary directory of
this evaluation), no prompt, no background maintenance, `LC_ALL=C`.

**Enforcement: FULL.** No subject code runs: the worker of `grep_count` is the harness's own script on bytes. Weakest
path: git's own object store at the revision SHA (the binary's identity is a RunSpec capability), or the bytes of a
directory that is not a repository.
"""

from __future__ import annotations

import ast
import codecs
import hashlib
import io
import json
import math
import os
import pathlib
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import tokenize
from typing import Mapping

from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.probe.protocol import ExecutionEnv, HarnessProbe, Observation, ObservationKind, ProbeMetadata, RevisionRef
from aisef2.product.spec import ProductProofSpec
from aisef2.runtime.process_range import ProcessRange, RangeError

PROBE_ID = "probe.file_artifact"
#: The bytes this probe takes behaviour from, in dependency order, and no more (PM-7): the module, the protocol that turns
#: an observation into a result (`classify_failure`, `run_probe`), the result types with the verdict over an absent
#: subject (`product/outcome.py`) and the invariant-IX name gate `run_probe` answers InvalidSpec by
#: (`product/contract.py`: a change to it changes a record). They are hashed into EXECUTION_DIGEST and nothing else
#: reads this tuple: it grants no access and loads nothing (`_probe_digest` is its one reader).
PROBE_SOURCES = ("product/contract.py", "product/outcome.py", "probe/protocol.py", "probe/file_artifact.py")
CLASSES = ("exists", "content", "grep_count", "python_imports")
#: Each class's meaning of an expired observation window (§9.2): a read that did not complete is no observation.
ON_DEADLINE = {"exists": BehaviorVerdict.REFUTED, "content": BehaviorVerdict.REFUTED,
               "grep_count": BehaviorVerdict.REFUTED, "python_imports": BehaviorVerdict.REFUTED}
WEAKEST_PATH = ("no subject code runs: the weakest path is git's own object store at the revision SHA (the binary "
                "resolved once at construction, its identity a RunSpec capability), or the bytes of a directory that "
                "is not a repository")
NEWLINES = ("\n", "\r\n")
PATTERN_CAP = 512             # characters of a grep pattern
FILE_CAP = 4 * 1024 * 1024    # bytes of one file read for content or grep
#: tree entry modes this probe reads: regular file, executable file, symlink, directory
MODES = ("100644", "100755", "120000", "040000")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_MODULE_NAME = re.compile(r"[A-Za-z_]\w*")      # a top-level module name, as python_imports compares them
_PREFIX = "path:"
_LOCATIONS = 50               # match locations kept in the detail
#: PM-13. The failures of grep_count's worker, each its own reason in the detail (`grep_count worker <REASON>: ...`).
WORKER_REASONS = ("DEADLINE", "LAUNCH", "CRASHED", "NO_RESULT", "BAD_RESULT", "INPUT")
_WORKER_GRACE_S = (0.5, 0.5)  # the worker's range ladder once the observation is over: it holds nothing to flush
_WORKER_WAIT_S = 30.0         # bounded: a range that will not empty is a residual, never an endless wait
_PATTERN_HEAD = 40            # characters of the pattern a DEADLINE names
_RESULT_FLOOR = 65536         # bytes a worker's result may hold before the size of its request is counted
#: The deadline clock of the worker. Bound here, once, to the function: the observation window of `observe` reads the
#: module's `time` (a test clock replaces it there), and the watchdog of a subprocess is not that window.
_monotonic = time.monotonic


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
CAPABILITY_VERSION = 3     # 2: the class python_imports (V21-37); 3: a selection of no file is an absent subject (PM-9)
EXECUTION_DIGEST = _probe_digest()
DIGEST = hashlib.sha256(json.dumps([PROBE_ID, CAPABILITY_VERSION, list(CLASSES)]).encode("utf-8")).hexdigest()


def window_of(observable) -> float | None:
    """The spec's bounded observation window in seconds, or None when it declares none."""
    w = dict(observable).get("within_s")
    ok = isinstance(w, (int, float)) and not isinstance(w, bool) and math.isfinite(w) and w > 0
    return float(w) if ok else None


def _compiles(pattern) -> bool:
    if not isinstance(pattern, str) or not pattern:
        return False
    try:
        re.compile(pattern)
    except re.error:
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
    newline_ok = "newline" not in obs or obs["newline"] in NEWLINES
    if set(obs) <= {"sha256", "newline"} and isinstance(obs.get("sha256"), str) and _HEX64.fullmatch(obs["sha256"]) \
            and newline_ok:
        return "content" if not stim else None
    if set(obs) == {"equals_text", "newline"} and isinstance(obs["equals_text"], str) and newline_ok:
        return "content" if not stim else None
    m = obs.get("matches")
    suffixes = stim.get("suffixes", [])
    if set(obs) == {"matches"} and isinstance(m, int) and not isinstance(m, bool) and m >= 0 \
            and set(stim) in ({"grep"}, {"grep", "suffixes"}) and _compiles(stim["grep"]) \
            and isinstance(suffixes, (list, tuple)) and all(isinstance(s, str) and len(s) > 1 and s[0] == "." for s in suffixes):
        return "grep_count"
    outside = stim.get("imports_outside")
    if set(obs) == {"matches"} and isinstance(m, int) and not isinstance(m, bool) and m >= 0 \
            and set(stim) in ({"imports_outside"}, {"imports_outside", "suffixes"}) and isinstance(outside, Mapping) \
            and set(outside) == {"stdlib", "allowed"} and isinstance(outside["stdlib"], bool) \
            and isinstance(outside["allowed"], (list, tuple)) and all(isinstance(n, str) and _MODULE_NAME.fullmatch(n)
                                                                       for n in outside["allowed"]) \
            and isinstance(suffixes, (list, tuple)) and all(isinstance(s, str) and len(s) > 1 and s[0] == "." for s in suffixes):
        return "python_imports"
    return None


def spec_class(spec: ProductProofSpec) -> str | None:
    """Harness metadata (`ProbeMetadata.observation_class`): the class `spec` asks of this probe, or None."""
    subject = dict(spec.probe_input["subject"])
    locator = subject.get("locator")
    if subject.get("kind") != "file_artifact" or not isinstance(locator, str) or not locator.startswith(_PREFIX):
        return None
    return observation_class(spec.probe_input["observable"], spec.probe_input["stimulus"])


def refusal(rel: str) -> str | None:
    """Why `rel` (the locator after `path:`) may not name an entry of the tree; None when it may."""
    if not rel or rel[0] == "/" or (len(rel) > 1 and rel[1] == ":"):
        return "absolute path or drive letter"
    if "\\" in rel:
        return "backslash"
    parts = rel.split("/")
    if ".." in parts:
        return "'..' component"
    if "" in parts or "." in parts:
        return "empty or '.' component"
    return None


def expected_sha256(observable) -> str:
    """The digest the `content` observable expects: `sha256` as declared, or the digest of `equals_text` written
    with the declared newline."""
    if "sha256" in observable:
        return observable["sha256"]
    text = observable["equals_text"].replace("\n", observable["newline"])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verdict_of(cls: str, observable, facts: dict) -> BehaviorVerdict:
    """What the facts read from the tree say about the observable."""
    if cls == "exists":
        seen = facts.get("present") is True
    elif cls == "content":
        seen = facts.get("sha256") == expected_sha256(observable)
    else:
        seen = facts.get("matches") == observable["matches"]
    return BehaviorVerdict.SATISFIED if seen else BehaviorVerdict.REFUTED


def normalised(data: bytes, newline: str | None) -> bytes:
    """The blob's bytes with their line endings normalised to `newline`; the bytes themselves when none is declared."""
    if newline is None:
        return data
    return data.replace(b"\r\n", b"\n").replace(b"\n", newline.encode("utf-8"))


def content_facts(data: bytes, observable) -> dict:
    return {"present": True, "kind": "blob", "size": len(data),
            "sha256": hashlib.sha256(normalised(data, dict(observable).get("newline"))).hexdigest()}


#: The worker of `grep_count` (PM-13): a harness script, never given anything of the subject but bytes. It is started as
#: `sys.executable -I -S -B -c GREP_WORKER <request> <result> <progress>`; stdlib only, no clock, nothing on stdout.
#: `request` is one JSON line {pattern, sizes, locations} then the selected files' bytes end to end; `progress` is eight
#: bytes the worker keeps up to date through a mapping (the 1-based index of the file it is on, the 1-based number of the
#: line it is matching: 0 for none yet) so that a stop can say where; `result` is the facts, by file index.
GREP_WORKER = r"""
import json, mmap, os, re, struct, sys


def grep(pattern, sizes, blob, cap, mark):
    matches, skipped, where, offset = 0, [], [], 0
    for index, size in enumerate(sizes):
        data = blob[offset:offset + size]
        offset += size
        mark[0:8] = struct.pack("<II", index + 1, 0)
        if b"\0" in data:
            skipped.append(index)
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return {"undecodable": index, "skipped_binary": skipped}
        for number, line in enumerate(text.splitlines(), 1):
            mark[4:8] = struct.pack("<I", number)
            if pattern.search(line):
                matches += 1
                if len(where) < cap:
                    where.append([index, number])
    return {"files": len(sizes), "matches": matches, "skipped_binary": skipped, "locations": where}


def main(request, result, progress):
    with open(request, "rb") as f:
        head, _, blob = f.read().partition(b"\n")
    ask = json.loads(head)
    with open(progress, "r+b") as f:
        mark = mmap.mmap(f.fileno(), 8)
        facts = grep(re.compile(ask["pattern"]), ask["sizes"], blob, ask["locations"], mark)
    with open(result, "w", encoding="utf-8") as f:
        json.dump(facts, f)


main(sys.argv[1], sys.argv[2], sys.argv[3])
"""


def _worker_env() -> dict:
    """What the worker's process is given: the variables Python needs to start on Windows, and nothing else (under -I
    it would ignore PYTHON* anyway)."""
    keep = ("SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR")
    return {k: os.environ[k] for k in keep if k in os.environ}


def _worker_facts(obj, rels: list[str]) -> dict:
    """The facts a worker's result stands for, with the files named: a result that is not the shape the worker writes
    for a request of these files is BAD_RESULT (a result is data from another process, never trusted for its shape)."""
    def bad(why: str):
        raise WorkerFailed("BAD_RESULT", f"the result is not the facts of this request ({why})")

    def index(v) -> bool:
        return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(rels)
    if not isinstance(obj, dict):
        bad(f"a {type(obj).__name__}, not an object")
    if set(obj) not in ({"undecodable", "skipped_binary"}, {"files", "matches", "skipped_binary", "locations"}):
        bad(f"fields {sorted(obj)}")
    skipped = obj["skipped_binary"]
    if not isinstance(skipped, list) or not all(index(i) for i in skipped) or skipped != sorted(set(skipped)):
        bad("skipped_binary is not an ascending list of file indexes")
    named = [rels[i] for i in skipped]
    if "undecodable" in obj:
        if not index(obj["undecodable"]):
            bad("undecodable is not a file index")
        return {"present": True, "undecodable": rels[obj["undecodable"]], "skipped_binary": named}
    matches, where = obj["matches"], obj["locations"]
    if obj["files"] != len(rels) or isinstance(obj["files"], bool):
        bad("files is not the number of files sent")
    if not isinstance(matches, int) or isinstance(matches, bool) or matches < 0:
        bad("matches is not a count")
    if not isinstance(where, list) or len(where) != min(matches, _LOCATIONS) \
            or not all(isinstance(w, list) and len(w) == 2 and index(w[0]) and isinstance(w[1], int)
                       and not isinstance(w[1], bool) and w[1] >= 1 and w[0] not in skipped for w in where) \
            or where != sorted(where):
        bad("locations are not the first matching lines, in order")
    return {"present": True, "files": len(rels), "matches": matches, "skipped_binary": named,
            "locations": [[rels[i], n] for i, n in where]}


def grep_facts(pattern: str, files: list[tuple[str, bytes]], *, timeout_s: float, work: str, on_range=None) -> dict:
    """Lines matching `pattern` over the decoded files, one match per matching line: what a worker process computes,
    under `timeout_s` for the whole operation (module docstring, "Bounded matching"). A file holding a NUL byte is
    binary: skipped and named. A file that is not UTF-8 leaves the count unestablished (no `matches`). `work` is the
    evaluation's directory: the request, the progress mark, the result and the worker's output live in it.
    `on_range` is the harness's hook for the worker's process range (the story's scope releases it). Raises
    `WorkerFailed` when the worker gives no valid facts; the range is emptied before it returns either way."""
    begun = _monotonic()
    request, result, progress, log = (os.path.join(work, n) for n in ("request", "result", "progress", "worker.log"))
    try:
        os.makedirs(work, exist_ok=True)
        with open(request, "wb") as f:
            f.write(json.dumps({"pattern": pattern, "sizes": [len(d) for _, d in files],
                                "locations": _LOCATIONS}).encode("ascii") + b"\n")
            for _, data in files:
                f.write(data)
        with open(progress, "wb") as f:
            f.write(bytes(8))
        out = open(log, "wb")
    except OSError as e:
        raise WorkerFailed("INPUT", f"the request cannot be written ({type(e).__name__})") from None
    try:
        run = ProcessRange("grep_count worker", [sys.executable, "-I", "-S", "-B", "-c", GREP_WORKER, request, result,
                                                 progress],
                           cwd=work, env=_worker_env(), output=out, grace_s=_WORKER_GRACE_S, wait_s=_WORKER_WAIT_S)
        run.start()
    except (RangeError, OSError) as e:
        raise WorkerFailed("LAUNCH", f"the worker did not start ({type(e).__name__})") from None
    finally:
        out.close()
    try:
        if on_range is not None:
            on_range(run)
        status = run.wait(max(0.0, timeout_s - (_monotonic() - begun)))
        elapsed = _monotonic() - begun
    finally:
        run.release()   # RangeNotEmpty / RangeEscaped propagate: a leak is never silent (§17.1)
    if status is None and elapsed < timeout_s:   # the range's report ended before the watchdog did: no exit status
        raise WorkerFailed("CRASHED", "the process range ended without reporting how the worker ended" + _said(log))
    if status is None or elapsed > timeout_s:    # the deadline is the whole operation: a late answer is no answer
        raise WorkerFailed("DEADLINE", _stopped(pattern, files, progress, timeout_s, None if status is None else elapsed))
    if status != 0:
        how = f"ended by signal {-status}" if status < 0 else f"exited with status {status}"
        raise WorkerFailed("CRASHED", f"the worker {how} before it gave its result" + _said(log) + "; it is not "
                           "retried here: a harness that ends the same way again is the environment's to fix")
    rels = [rel for rel, _ in files]
    cap = _RESULT_FLOOR + 8 * sum(len(rel) + 8 for rel in rels)
    try:
        size = os.path.getsize(result)
    except OSError:
        raise WorkerFailed("NO_RESULT", "the worker exited 0 and wrote no result" + _said(log)) from None
    if size == 0:
        raise WorkerFailed("NO_RESULT", "the worker exited 0 and its result is empty" + _said(log))
    if size > cap:
        raise WorkerFailed("BAD_RESULT", f"the result is {size} bytes: more than a request of {len(rels)} file(s) can "
                                         f"produce ({cap})")
    try:
        obj = json.loads(pathlib.Path(result).read_bytes())
    except (OSError, ValueError, RecursionError) as e:
        raise WorkerFailed("BAD_RESULT", f"the result is not JSON ({type(e).__name__})") from None
    return _worker_facts(obj, rels)


def _said(log: str) -> str:
    """What the worker printed (its traceback, when it crashed), cut: the tail of its output file."""
    try:
        tail = pathlib.Path(log).read_bytes()[-300:].decode("utf-8", "replace").strip()
    except OSError:
        return ""
    return f": {tail!r}" if tail else ""


def _stopped(pattern: str, files: list[tuple[str, bytes]], progress: str, timeout_s: float,
             finished_after: float | None) -> str:
    """The DEADLINE message: where the worker was when its range was stopped (the progress mark, read after the stop),
    the head of the pattern, and what to do — not to run it again. `finished_after` is the time a worker took that
    did finish, but only after the watchdog had passed (the start of the range counts): its answer is not taken."""
    try:
        at, line = struct.unpack("<II", pathlib.Path(progress).read_bytes()[:8])
    except (OSError, struct.error):
        at = line = 0
    name = files[at - 1][0] if 0 < at <= len(files) else None
    where = ("before it began on the first file" if name is None else
             f"reading {name!r}" if line == 0 else f"matching line {line} of {name!r}")
    head = pattern[:_PATTERN_HEAD] + ("..." if len(pattern) > _PATTERN_HEAD else "")
    what = ("the regex loop did not finish within" if finished_after is None else
            f"the worker answered only after the watchdog had passed ({finished_after:.1f}s, start included; nothing is "
            "taken from a late answer):")
    return (f"{what} the harness watchdog ({timeout_s:g}s: timeouts_s.probe), {where}, "
            f"against the pattern {head!r} ({len(pattern)} characters); its process range was emptied and nothing was "
            "observed, so this is a stop of the harness and never a verdict. The same pattern over the same bytes "
            "within the same deadline stops the same way: running it again changes nothing. Simplify the pattern "
            "(no nested or overlapping quantifiers over the same text) or raise timeouts_s.probe on purpose")


def import_facts(outside, files: list[tuple[str, bytes]]) -> dict:
    """Import statements (by syntax, this interpreter's `ast`) naming a top-level module outside `outside`, one per
    statement. A file that is not UTF-8 or does not parse leaves the count unestablished (no `matches`): that is the
    file's own answer. A file the parser stops on (`RecursionError`, `MemoryError`) is `Refused`: the harness could not
    say what the file is, so there is no answer and no verdict — here, once, for every caller. Every file is looked at
    before any answer is given, and a refusal outranks a file's own answer: the kind of the result is the tree's, never
    the order a reader lists it in (a git tree and a plain directory list `a.py` and `a/b.py` in opposite orders)."""
    allowed = set(outside["allowed"]) | (set(sys.stdlib_module_names) if outside["stdlib"] else set())
    matches, where, own, stopped = 0, [], None, None
    for rel, data in files:
        try:
            text = data.decode("utf-8-sig")        # CPython drops a leading BOM from source bytes
            if data.startswith(codecs.BOM_UTF8):   # the mark declares UTF-8: a cookie that says otherwise is its error
                tokenize.detect_encoding(io.BytesIO(data).readline)
            tree = ast.parse(text, filename=rel)
        except UnicodeDecodeError:
            own = own or {"present": True, "undecodable": rel}
            continue
        except (SyntaxError, ValueError) as e:     # ValueError: a NUL byte in the source, up to Python 3.11
            line = getattr(e, "lineno", None)       # a NUL byte or a cookie names none: never write the word None
            own = own or {"present": True, "unparsable": f"{rel}:{'?' if line is None else line}"}
            continue
        except (RecursionError, MemoryError) as e:  # the parser's own limit, not a statement about the file
            stopped = stopped or (rel, type(e).__name__)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            outside_names = sorted({n.split(".")[0] for n in names} - allowed)
            if outside_names:
                matches += 1
                if len(where) < _LOCATIONS:
                    where.append([rel, node.lineno, outside_names])
    if stopped is not None:
        raise Refused(f"{stopped[0]!r}: this interpreter's parser stopped ({stopped[1]}: a nesting, stack or memory "
                      "limit of its own) before it could say what the file is, so there is no count and no verdict "
                      "(refused, not refuted). The same file under the same interpreter stops the same way, so "
                      "running it again changes nothing: it is read once the file is made shallower (split long "
                      "operator chains, `elif` ladders and nested lambdas) or the proof runs on an interpreter "
                      f"whose limit admits it (this one: python {sys.version_info.major}.{sys.version_info.minor})")
    if own is not None:
        return own
    return {"present": True, "files": len(files), "matches": matches, "locations": where,
            "stdlib_of": f"python {sys.version_info.major}.{sys.version_info.minor}"}


def selected(path: str, suffixes) -> bool:
    return not suffixes or any(path.endswith(s) for s in suffixes)


class Refused(Exception):
    """The harness could not read the tree honestly: an escape, a link, a cap, a missing revision, a git failure."""


class WorkerFailed(Refused):
    """The harness could not count: the worker of `grep_count` gave no valid facts (PM-13). `reason` is one of
    `WORKER_REASONS` and opens the message, so a reader and a machine tell a hang from a crash from a bad answer."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"grep_count worker {reason}: {message}")
        self.reason = reason


def git_env(home: str) -> dict:
    """The scrubbed environment git runs in: an allowlist of the host's, `HOME` inside this evaluation's directory,
    no user or system configuration, no prompt, no background maintenance, the C locale."""
    keep = ("SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "PATH")
    return {**{k: os.environ[k] for k in keep if k in os.environ},
            "HOME": home, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.path.join(home, "no-global-gitconfig"),
            "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
            "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0"}


def run_git(git: str, root: str, args: list[str], env: dict, timeout_s: float) -> subprocess.CompletedProcess:
    """One bounded git invocation: argv, no shell, bytes captured, the harness watchdog as its timeout."""
    try:
        return subprocess.run([git, "-C", root, *args], capture_output=True, env=env, timeout=timeout_s, shell=False)
    except subprocess.TimeoutExpired:
        raise Refused(f"git {args[0]} did not answer within the harness watchdog ({timeout_s:g}s)") from None
    except OSError as e:
        raise Refused(f"git {args[0]} cannot launch: {type(e).__name__}") from None


class ObjectStore:
    """The revision's tree, read from the object store of the repository whose top level is the checkout root.
    Entries are (path, mode, oid, size)."""
    name = "object_store"

    def __init__(self, git: str, root: str, sha: str, env: dict, timeout_s: float) -> None:
        self.git, self.root, self.sha, self.env, self.timeout_s = git, root, sha, env, timeout_s

    def run(self, *args: str) -> bytes:
        p = run_git(self.git, self.root, list(args), self.env, self.timeout_s)
        if p.returncode != 0:
            raise Refused(f"git {args[0]} exited {p.returncode}: {p.stderr.decode('utf-8', 'replace').strip()[:200]}")
        return p.stdout

    def holds_revision(self) -> bool:
        p = run_git(self.git, self.root, ["cat-file", "-e", f"{self.sha}^{{commit}}"], self.env, self.timeout_s)
        return p.returncode == 0

    def lookup(self, rel: str) -> list[tuple[str, str, str, int]]:
        """`rel` and every tree component on the way to it (`-t`); git stops silently at a component that is not a
        tree, so a missing leaf is told from a blocked path by `entries` on the first component not listed."""
        return self._parse(self.run("ls-tree", "-z", "-l", "-t", self.sha, "--", rel))

    def entries(self, path: str) -> list[tuple[str, str, str, int]]:
        return self._parse(self.run("ls-tree", "-z", "-l", self.sha, "--", path))

    def walk(self, path: str) -> list[tuple[str, str, str, int]]:
        return self._parse(self.run("ls-tree", "-z", "-l", "-r", self.sha, "--", path))

    @staticmethod
    def _parse(out: bytes) -> list[tuple[str, str, str, int]]:
        rows = []
        for item in out.split(b"\0"):
            if not item:
                continue
            head, _, p = item.partition(b"\t")
            mode, _kind, oid, size = head.split()
            rows.append((p.decode("utf-8", "surrogateescape"), mode.decode(), oid.decode(),
                         int(size) if size != b"-" else 0))
        return rows

    def blob(self, path: str, oid: str) -> bytes:
        return self.run("cat-file", "blob", oid)


class PlainTree:
    """A checkout root that is not a repository (a fixture directory): its entries, names matched exactly against the
    directory listing (never the file system's case folding), links never followed. Entries as `ObjectStore`'s."""
    name = "directory"

    def __init__(self, root: str) -> None:
        self.root = root

    def _full(self, rel: str) -> str:
        return os.path.join(self.root, *rel.split("/"))

    def _row(self, rel: str) -> tuple[str, str, str, int] | None:
        """The entry `rel` names, as the object store would list it, or None when there is no such entry: the name
        matched exactly against its directory's listing, the mode from lstat (a link is a link, never followed)."""
        full = self._full(rel)
        parent, name = os.path.split(full)
        try:
            if name not in os.listdir(parent):   # ponytail: one listdir per entry; a fixture tree is small
                return None
            st = os.lstat(full)
        except OSError:
            return None
        if stat.S_ISLNK(st.st_mode):
            mode = "120000"
        elif stat.S_ISDIR(st.st_mode):
            mode = "040000"
        elif stat.S_ISREG(st.st_mode):
            mode = "100644"
        else:
            return None
        return (rel, mode, "", st.st_size)

    def lookup(self, rel: str) -> list[tuple[str, str, str, int]]:
        """As `ObjectStore.lookup`: the tree components on the way and the leaf, stopping at a component that is not
        a directory (so nothing below a link is ever stat-ed through it)."""
        parts = rel.split("/")
        out = []
        for i in range(1, len(parts) + 1):
            row = self._row("/".join(parts[:i]))
            if row is None or (row[1] != "040000" and row[0] != rel):
                break
            out.append(row)
        return out

    def entries(self, path: str) -> list[tuple[str, str, str, int]]:
        row = self._row(path)
        return [row] if row is not None else []

    def walk(self, path: str) -> list[tuple[str, str, str, int]]:
        out = []

        def visit(directory: str, prefix: str) -> None:
            for e in sorted(os.scandir(directory), key=lambda e: e.name):
                rel = f"{prefix}/{e.name}"
                if e.is_dir(follow_symlinks=False):
                    visit(e.path, rel)
                else:
                    row = self._row(rel)
                    if row is not None:
                        out.append(row)
        visit(self._full(path), path)
        return out

    def blob(self, path: str, oid: str) -> bytes:
        return pathlib.Path(self._full(path)).read_bytes()


def entry(reader, rel: str) -> tuple[str, str, int] | None:
    """The tree entry `rel` names, as (mode, oid, size), or None when the path is not in the tree. Every component on
    the way must be a directory of the tree: the reader lists the components it could descend, and the first one it
    could not is looked up on its own — a link or a gitlink there is refused before anything is read (a link is never
    followed); a blob there, or nothing, means the path is not in the tree."""
    parts = rel.split("/")
    prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    found = {p: (mode, oid, size) for p, mode, oid, size in reader.lookup(rel)}
    if rel in found:
        return found[rel]
    blocked = next((p for p in prefixes[:-1] if p not in found), None)
    if blocked is None:
        return None
    for p, mode, _oid, _size in reader.entries(blocked):
        if p == blocked and mode not in ("100644", "100755"):
            raise Refused(f"component {p!r} of the locator is not a directory of the tree (mode {mode}"
                          f"{', a symlink: a link is never followed' if mode == '120000' else ''}); refused")
    return None


def read(reader, path: str, oid: str, size: int) -> bytes:
    if size > FILE_CAP:
        raise Refused(f"{path!r} is {size} bytes, over the per-file cap of {FILE_CAP}; refused, not a verdict")
    return reader.blob(path, oid)


def facts_of(reader, cls: str, rel: str, observable, stim: dict, grep) -> dict:
    """The facts `verdict_of` decides on, read through `reader`; `present` False when the path is not in the tree or,
    for a count, when it selects no file (PM-9). `grep(pattern, files)` gives the facts of a `grep_count` (the bounded
    worker, PM-13); a count of a selection of none needs none."""
    found = entry(reader, rel)
    if found is None:
        return {"present": False, "path": rel}
    mode, oid, size = found
    if mode not in MODES:
        raise Refused(f"{rel!r} has mode {mode}: not a file, link or directory of this repository; refused")
    if cls == "exists":
        return {"present": True, "path": rel, "mode": mode}
    if mode == "120000":
        raise Refused(f"{rel!r} is a symlink entry (mode 120000); a link is never read")
    if cls == "content":
        if mode == "040000":
            return {"present": True, "path": rel, "kind": "tree"}
        return {"path": rel, "mode": mode, **content_facts(read(reader, rel, oid, size), observable)}
    files = reader.walk(rel) if mode == "040000" else [(rel, mode, oid, size)]
    suffixes = stim.get("suffixes") or ((".py",) if cls == "python_imports" else ())
    chosen = [f for f in files if selected(f[0], suffixes)]
    odd = [f"{f[0]} ({f[1]})" for f in chosen if f[1] not in ("100644", "100755")]
    if odd:
        raise Refused(f"entries under {rel!r} selected for grep that are not files: {odd[:5]}; a link is never read")
    if not chosen:    # PM-9: nothing is selected, so nothing is counted: the subject of the count is absent
        return {"present": False, "path": rel, "mode": mode, "files": 0, "suffixes": list(suffixes)}
    contents = [(f[0], read(reader, f[0], f[2], f[3])) for f in chosen]
    if cls == "python_imports":
        return {"path": rel, "mode": mode, **import_facts(stim["imports_outside"], contents)}
    return {"path": rel, "mode": mode, **grep(stim["grep"], contents)}


class FileArtifactProbe(HarnessProbe):
    id = PROBE_ID
    digest = DIGEST
    execution_digest = EXECUTION_DIGEST

    def __init__(self, on_range=None, scratch: str | None = None) -> None:
        """`on_range` and `scratch` are the harness-owned constructor convention every catalog probe accepts
        (PROBE-META-1). This probe starts no subject process and keeps no state: `on_range` receives the process range
        of a `grep_count` worker (the story's scope releases it; the probe releases it itself first), `scratch` is
        recorded and unused. The git binary is resolved once, here: a probe constructed without one refuses every
        observation."""
        self._on_range, self._scratch = on_range, scratch
        self._git = shutil.which("git")

    def enforcement(self) -> Enforcement:
        return Enforcement.FULL

    def harness_preconditions(self) -> tuple[str, ...]:
        return ("git: a git binary was resolvable when the probe was constructed and answers within the harness "
                "watchdog (ExecutionEnv.timeout_s)",
                "checkout: the revision's checkout root exists — the top level of a repository, or a directory",
                "object store: when the root is a repository, it holds the revision (RevisionRef.sha)",
                "worker: this interpreter launches under -I -S in a process range of the harness and answers a "
                "grep_count within the harness watchdog (ExecutionEnv.timeout_s)")

    def observe(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> Observation:
        pi = spec.probe_input
        subject = dict(pi["subject"])
        if subject.get("kind") != "file_artifact":
            return Observation(ObservationKind.UNSUPPORTED, detail=f"subject kind {subject.get('kind')!r} is not "
                                                                   "file_artifact")
        locator = subject.get("locator")
        if not isinstance(locator, str) or not locator.startswith(_PREFIX):
            return Observation(ObservationKind.UNSUPPORTED, detail=f"locator {locator!r} is not "
                                                                   "path:<relative posix path>")
        cls = spec_class(spec)
        if cls is None:
            return Observation(ObservationKind.UNSUPPORTED, detail="observable/stimulus is not a supported class "
                                                                   f"{CLASSES} with a bounded window (within_s); "
                                                                   "refused, not degraded")
        if self._git is None:
            return Observation(ObservationKind.HARNESS_FAILED, detail="git absent: no git binary was resolvable when "
                                                                     "the probe was constructed")
        rel = locator[len(_PREFIX):]
        why = refusal(rel)
        if why is not None:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"locator {locator!r} refused ({why}): the tree "
                                                                     "is never escaped")
        stim = dict(pi["stimulus"])
        if cls == "grep_count" and len(stim["grep"]) > PATTERN_CAP:
            return Observation(ObservationKind.HARNESS_FAILED, detail=f"grep pattern of {len(stim['grep'])} characters "
                                                                     f"exceeds the cap of {PATTERN_CAP}; refused")
        if not os.path.isdir(at.root):
            return Observation(ObservationKind.HARNESS_FAILED, detail="cannot inspect: the revision checkout is missing")
        window = window_of(pi["observable"])
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="aisef2-file-artifact-") as home:
            try:
                reader = self._reader(at, env, home)
                facts = facts_of(reader, cls, rel, pi["observable"], stim,
                                 grep=lambda pattern, files: grep_facts(pattern, files, timeout_s=env.timeout_s,
                                                                        work=os.path.join(home, "grep"),
                                                                        on_range=self._on_range))
            except Refused as e:
                return Observation(ObservationKind.HARNESS_FAILED, detail=str(e))
        expired = time.monotonic() - started > window
        detail = json.dumps({"read": reader.name, "revision": at.sha, **facts})
        if expired:
            return Observation(ObservationKind.SUBJECT_DEADLINE, ON_DEADLINE[cls],
                               detail=f"the {window:g}s observation window expired ({cls}); " + detail)
        if facts.get("present") is not True:
            over_absent = verdict_of(cls, pi["observable"], {"matches": 0}) if cls in ("grep_count", "python_imports") \
                else BehaviorVerdict.REFUTED
            return Observation(ObservationKind.SUBJECT_ABSENT, over_absent, detail=detail)
        return Observation(ObservationKind.OBSERVED, verdict_of(cls, pi["observable"], facts), detail=detail)

    def _reader(self, at: RevisionRef, env: ExecutionEnv, home: str):
        """The object store of the repository whose top level is the checkout root, else the directory itself. Git's
        own discovery decides, ceilinged at the root's parent, so a directory nested inside some other repository is
        a directory; the SHA's value never enters the decision."""
        root = os.path.realpath(at.root)
        genv = git_env(home)
        p = run_git(self._git, root, ["rev-parse", "--show-toplevel"],
                    {**genv, "GIT_CEILING_DIRECTORIES": os.path.dirname(root)}, env.timeout_s)
        if p.returncode != 0:
            if b"not a git repository" not in p.stderr:
                raise Refused(f"git rev-parse exited {p.returncode}: {p.stderr.decode('utf-8', 'replace').strip()[:200]}")
            return PlainTree(root)
        store = ObjectStore(self._git, root, at.sha, genv, env.timeout_s)
        if not store.holds_revision():
            raise Refused(f"revision {at.sha[:12]} not in the repository at the checkout root")
        return store


METADATA = ProbeMetadata(PROBE_ID, DIGEST, spec_class)
