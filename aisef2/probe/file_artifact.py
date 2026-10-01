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
| `grep_count` | `{"matches": M, "within_s": W}` | `{"grep": R, ["suffixes": [".py", ...]]}` | exactly M lines match R |

`newline` (`"\\n"` or `"\\r\\n"`) declares the line convention: when it is declared the blob's line endings are
normalised to it (CRLF to LF, then LF to the declared one) before hashing or comparing, and `equals_text` is a text
whose lines end in `\\n`; without it `sha256` is over the exact blob bytes. `grep_count` compiles R (a pattern that
does not compile is UNSUPPORTED; one longer than `PATTERN_CAP` is a harness refusal), decodes each selected file as
UTF-8 and counts the lines with at least one match — one per matching line, never overlapping matches. A directory
is walked recursively; `suffixes` selects by file-name suffix, the default selecting every file. A file holding a
NUL byte is binary: skipped and named in the detail. A file that is not UTF-8 leaves the count unestablished:
REFUTED, the file named. A file over `FILE_CAP` bytes is a harness refusal, never a verdict. `content` over a
directory is observed and REFUTED (a tree has no blob). Every class means REFUTED by an expired window
(`ON_DEADLINE`): a read that did not complete in W is not an observation of presence.

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

**Absence.** A path that is not in the tree is SUBJECT_ABSENT with the verdict the observable gives the absent
subject: REFUTED for `exists` and `content`; for `grep_count` the verdict the count gives zero matches (SATISFIED
when M is 0), so a prohibition declared ABSENCE_IS_DECIDABLE decides (§10.2); whether it counts is the spec's
declaration, applied by `protocol.classify_failure`, never here.

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

**Enforcement: FULL.** No subject code runs. Weakest path: git's own object store at the revision SHA (the binary's
identity is a RunSpec capability), or the bytes of a directory that is not a repository.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile
import time

from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.probe.protocol import ExecutionEnv, HarnessProbe, Observation, ObservationKind, ProbeMetadata, RevisionRef
from aisef2.product.spec import ProductProofSpec

PROBE_ID = "probe.file_artifact"
PROBE_SOURCES = ("probe/protocol.py", "probe/file_artifact.py")
CLASSES = ("exists", "content", "grep_count")
#: Each class's meaning of an expired observation window (§9.2): a read that did not complete is no observation.
ON_DEADLINE = {"exists": BehaviorVerdict.REFUTED, "content": BehaviorVerdict.REFUTED,
               "grep_count": BehaviorVerdict.REFUTED}
WEAKEST_PATH = ("no subject code runs: the weakest path is git's own object store at the revision SHA (the binary "
                "resolved once at construction, its identity a RunSpec capability), or the bytes of a directory that "
                "is not a repository")
NEWLINES = ("\n", "\r\n")
PATTERN_CAP = 512             # characters of a grep pattern
FILE_CAP = 4 * 1024 * 1024    # bytes of one file read for content or grep
#: tree entry modes this probe reads: regular file, executable file, symlink, directory
MODES = ("100644", "100755", "120000", "040000")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_PREFIX = "path:"
_LOCATIONS = 50               # match locations kept in the detail


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


def grep_facts(pattern: re.Pattern, files: list[tuple[str, bytes]]) -> dict:
    """Lines matching `pattern` over the decoded files, one match per matching line. A file holding a NUL byte is
    binary: skipped and named. A file that is not UTF-8 leaves the count unestablished (no `matches`)."""
    matches, skipped, where = 0, [], []
    for rel, data in files:
        if b"\0" in data:
            skipped.append(rel)
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return {"present": True, "undecodable": rel, "skipped_binary": skipped}
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                matches += 1
                if len(where) < _LOCATIONS:
                    where.append([rel, n])
    return {"present": True, "files": len(files), "matches": matches, "skipped_binary": skipped, "locations": where}


def selected(path: str, suffixes) -> bool:
    return not suffixes or any(path.endswith(s) for s in suffixes)


class Refused(Exception):
    """The harness could not read the tree honestly: an escape, a link, a cap, a missing revision, a git failure."""


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


def facts_of(reader, cls: str, rel: str, observable, stim: dict) -> dict:
    """The facts `verdict_of` decides on, read through `reader`; `present` False when the path is not in the tree."""
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
    chosen = [f for f in files if selected(f[0], stim.get("suffixes"))]
    odd = [f"{f[0]} ({f[1]})" for f in chosen if f[1] not in ("100644", "100755")]
    if odd:
        raise Refused(f"entries under {rel!r} selected for grep that are not files: {odd[:5]}; a link is never read")
    contents = [(f[0], read(reader, f[0], f[2], f[3])) for f in chosen]
    return {"path": rel, "mode": mode, **grep_facts(re.compile(stim["grep"]), contents)}


class FileArtifactProbe(HarnessProbe):
    id = PROBE_ID
    digest = DIGEST

    def __init__(self, on_range=None, scratch: str | None = None) -> None:
        """`on_range` and `scratch` are the harness-owned constructor convention every catalog probe accepts
        (PROBE-META-1); this probe starts no subject process and keeps no state, so both are recorded and unused.
        The git binary is resolved once, here: a probe constructed without one refuses every observation."""
        self._on_range, self._scratch = on_range, scratch
        self._git = shutil.which("git")

    def enforcement(self) -> Enforcement:
        return Enforcement.FULL

    def harness_preconditions(self) -> tuple[str, ...]:
        return ("git: a git binary was resolvable when the probe was constructed and answers within the harness "
                "watchdog (ExecutionEnv.timeout_s)",
                "checkout: the revision's checkout root exists — the top level of a repository, or a directory",
                "object store: when the root is a repository, it holds the revision (RevisionRef.sha)")

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
                facts = facts_of(reader, cls, rel, pi["observable"], stim)
            except Refused as e:
                return Observation(ObservationKind.HARNESS_FAILED, detail=str(e))
        expired = time.monotonic() - started > window
        detail = json.dumps({"read": reader.name, "revision": at.sha, **facts})
        if expired:
            return Observation(ObservationKind.SUBJECT_DEADLINE, ON_DEADLINE[cls],
                               detail=f"the {window:g}s observation window expired ({cls}); " + detail)
        if facts.get("present") is not True:
            over_absent = verdict_of(cls, pi["observable"], {"matches": 0}) if cls == "grep_count" \
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
