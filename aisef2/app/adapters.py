"""The developer, the reviewer and the scanner the kernel's story runner calls (aisef2.orchestrate.adapters protocols).

The developer works in the kernel's checkout of the story and the harness commits what it changed (every git the
kernel runs is under the isolated configuration of aisef2.orchestrate.workspace, B4). A finding blocks only when the
kernel's own probe reproduces it and the bundle's approved contracts anchor its expectation (V2.1, app/review_verify);
a review alone never does (RFC §25). The scanner is informational: ruff when the operator has it, else a
scanner that reports nothing — the record says which."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import time

from aisef2.app import client, feedback, review_ocr, review_verify
from aisef2.app.bundle import Project
from aisef2.arch.enums import ControlProjection
from aisef2.journal.format2 import OperationOutcome as O
from aisef2.orchestrate.adapters import CapabilityUnrunnable, Finding, Implemented, ProviderOutage, Reviewed, Scanned
from aisef2.orchestrate.workspace import _ISOLATED_GIT as ISOLATED_GIT
from aisef2.orchestrate.workspace import commit_all, git
from aisef2.runtime.process_range import ProcessRange, RangeError

REVIEW_PROMPT = ("Review the implementation of story {story} of {name} in this read-only checkout against {requirements} "
                 "and these clauses:\n{clauses}\nDo not modify any file. Answer with ONLY one JSON object: "
                 '{{"findings": [{{"id": "short-id", "blocking": true or false, "severity": "low|medium|high|critical", '
                 '"summary": "one line", "reproducer": null or {{"clause": "<requirement id>/<clause> as listed above, e.g. R-9/3", "subject": '
                 '{{"kind": "cli_invocation|python_callable|file_artifact|process_effect", "locator": "..."}}, '
                 '"stimulus": {{...}}, "observable": {{..., "within_s": 10}}}}}}]}}\n'
                 "A finding is acted on only when its reproducer — the behaviour the cited clause demands, in the probe's "
                 "grammar — is observed NOT to hold when the kernel runs it, and the clause's approved criteria expect "
                 "exactly that behaviour; any other finding is recorded for a person to triage.")
#: what Open Code Review is told besides the diff (`--background-file`): the clauses, and how a comment states a
#: behaviour the kernel can check (app/review_ocr.REPRODUCER_FENCE)
OCR_BACKGROUND = ("You review a change to {name}. {requirements} in the repository is the authoritative specification; the "
                  "change must satisfy these requirement clauses:\n{clauses}\n\nWhen a comment says the change violates "
                  "one of these clauses, end the comment with a fenced block whose info string is aisef-reproducer, "
                  "holding one JSON object: {{\"clause\": \"<requirement id>/<clause> as listed, e.g. R-9/3\", \"subject\": {{\"kind\": "
                  "\"cli_invocation|python_callable|file_artifact|process_effect\", \"locator\": \"...\"}}, \"stimulus\": "
                  "{{...}}, \"observable\": {{..., \"within_s\": 10}}}} — the behaviour the clause demands, which the change "
                  "does not have. A comment without one is recorded for a person; it never blocks the change.")


#: the review is refused, not the finding downgraded: a confirmed, anchored finding whose evidence cannot be kept would
#: otherwise pass the story (a cut statement is never grounds to block, and none is dropped silently)
NOT_PRESERVED = ("finding {id} is confirmed and anchored, but its full reproducer could not be preserved ({why}): the "
                 "review did not complete with its evidence (every finding discarded)")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def attempt_of(run, story_id: str) -> tuple[int, bool]:
    """The story's attempt number (the kernel's projection) and whether the journal holds an earlier failure of it."""
    st = run.state(ControlProjection.STORY_STATE).get(story_id) or {}
    prior = any(e.type == "failure/observed" and e.data.get("story_id") == story_id for e in run.events)
    return st.get("attempt", 0), prior


class Developer:
    def __init__(self, run, project: Project, logs: pathlib.Path, session_kw: dict, timeout_s: float) -> None:
        self.run, self.project, self.logs, self.kw, self.timeout_s = run, project, logs, session_kw, timeout_s
        self.sessions: list[dict] = []

    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str) -> Implemented:
        attempt, prior = attempt_of(self.run, story_id)
        prompt = feedback.task(self.project, story_id)
        if prior:
            events = [(e.seq, e.type, e.data) for e in self.run.events]
            told = feedback.retry_feedback(events, story_id, self.project)
            pack = feedback.context_pack(events, story_id, self.project, self.kw.get("secrets", ()))   # V2.1 D4
            prompt += (f"\n\nA previous attempt of this story was not accepted; the kernel observed:\n{told}\n"
                       + (f"{pack}\n" if pack else "") + "Fix the implementation.")
        parent = git(checkout, "rev-parse", "HEAD").stdout.strip()
        s = client.session(f"developer {story_id}", prompt, checkout, self.logs / f"{story_id}.developer.{attempt}.jsonl",
                           self.timeout_s, **self.kw)
        s.update(story_id=story_id, attempt=attempt, role="developer", prompt_sha256=_sha(prompt.encode("utf-8")))
        self.sessions.append(s)
        head = git(checkout, "rev-parse", "HEAD").stdout.strip()
        changed = bool(git(checkout, "status", "--porcelain").stdout.strip()) or head != parent
        s["developer_committed_itself"] = head != parent
        if s["error"] and not changed:
            raise ProviderOutage(s["error"])
        if not changed:
            return Implemented(O.FAILED, None, f"the developer changed nothing (exit {s['exit']}, timed out {s['timed_out']})")
        sha = commit_all(checkout, f"{story_id}: developer attempt {attempt}")
        s["candidate"] = sha
        return Implemented(O.COMPLETED, sha, f"opencode exit {s['exit']}, {s['turns']} turns" + (f", {s['stopped']}" if s["stopped"] else ""))


def _braces(text: str) -> str | None:
    r"""From the first `{` of `text` to the last `}` after it — what `re.search(r"\{.*\}", text, re.S)` matches — or
    None. Found by two scans: the regex tries every `{` and reads to the end of the text for each, so a reviewer's reply
    (a model's text, of any length) of `{` with no `}` after them costs the square of its length."""
    first, last = text.find("{"), text.rfind("}")
    return text[first:last + 1] if 0 <= first < last else None


class Reviewer:
    """The review stage's finder and the verification of what it finds (V2.1). The finder is the model reviewer (an
    OpenCode session, 2.0.0's) or Open Code Review (settings review.finder = "ocr": app/review_ocr). Whichever finds,
    the kernel's probe verifies each reproducer and the bundle's approved contracts anchor its expectation
    (app/review_verify); and the reviewed checkout must not change while the review runs: the candidate is captured
    before the finder starts and every file of the checkout is compared after the finder and after the verification —
    a change discards every finding (CapabilityUnrunnable: the review did not run on the candidate).

    Each finding is kept whole, secret-redacted, in an artifact of the run directory (`review_verify.preserve`) that
    its journaled statement names; the statement is bounded and says so when it cut. A finding that would block and
    whose artifact cannot be kept refuses the review the same way (`NOT_PRESERVED`): a cut statement is never what
    blocks a story, and a confirmed finding is never passed silently. The run's secrets are the session streams'.

    `diagnostics` (PM-8, app/diagnostics): the run's sink, which keeps for the operator what the probe saw of each
    reproducer it did not satisfy. It is handed the probes' entries and nothing else: what it keeps reaches no verdict."""

    def __init__(self, run, project: Project, logs: pathlib.Path, session_kw: dict, timeout_s: float,
                 review: dict | None = None, probe_timeout_s: float = 60.0, interpreter: str | None = None,
                 route: dict | None = None, diagnostics=None) -> None:
        self.run, self.project, self.logs, self.kw, self.timeout_s = run, project, logs, session_kw, timeout_s
        self.sessions: list[dict] = []
        self.diagnostics = diagnostics
        self._at: dict = {}      # the finding being verified, for the sink: its place in the finder's list
        from aisef2.app.settings import REVIEW_ABSENT
        self.review_policy = review or REVIEW_ABSENT     # V2.1 (app/review_verify): what a confirmed finding does
        self.probe_timeout_s = probe_timeout_s
        self.interpreter = interpreter or sys.executable     # the probes' (app/run: the run's probe interpreter)
        self.route = route or {}                             # OCR's endpoint {url, token, model} and base environment

    def review(self, scope, criteria: tuple[str, ...]) -> Reviewed:
        attempt, _ = attempt_of(self.run, scope.story_id)
        head = git(scope.root, "rev-parse", "HEAD")
        if head.returncode != 0:
            raise CapabilityUnrunnable("the checkout to review has no revision")
        head = head.stdout.strip()
        before = tree_of(scope.root)
        ocr = self.review_policy.get("finder") == "ocr"
        found, s, coverage = (self._ocr(scope, attempt, head) if ocr else self._model(scope, attempt))
        # a finding's prose is read with `str()`: nothing of it nests deeper than the artifact keeps
        found = [review_verify.bounded(f) for f in found]
        _unchanged(scope.root, head, before, "the finder")
        secrets = (*self.kw.get("secrets", ()), self.route.get("token"))     # what the session streams are redacted with
        typed = []
        for index, f in enumerate(found):     # evidence only when the kernel's probe reproduces it and its clause anchors it
            fid = review_verify.redacted(str(f.get("id")), secrets)[0]      # it names the gate row: no secret there either
            self._at = {"origin": "review", "story_id": scope.story_id, "attempt": attempt, "index": index, "finding": fid}
            v = self._verify(f, scope.root, head)
            a = review_verify.anchor(f, self.project) if isinstance(f.get("reproducer"), dict) else None
            f["verification"] = {"status": v.status, "why": v.reason, "probe": v.probe, "observed": v.observed}
            if a is not None:
                f["anchor"] = {"status": a.status, "why": a.reason, "contracts": list(a.contracts)}
            confirmed = review_verify.blocks(v, f, self.review_policy["policy"], self.review_policy["min_severity"], a)
            # the statement is bounded; the finding is kept whole, redacted, in an artifact the row names and the
            # manifest binds — and a block rests on that artifact, never on the statement's cut text
            kept = review_verify.preserve(self.logs.parent, f, story=scope.story_id, attempt=attempt, index=index,
                                          revision=head, session=s.get("log"), secrets=secrets)
            if confirmed and not isinstance(kept, review_verify.Artifact):
                raise CapabilityUnrunnable(NOT_PRESERVED.format(id=fid, why=kept))
            typed.append(Finding(fid, confirmed or bool(f.get("blocking")),
                                 (v.evidence(),) if confirmed else (), review_verify.detail(f, v, a, kept, secrets)))
        _unchanged(scope.root, head, before, "the verification")
        s["findings"] = review_verify.redacted(found, secrets)[0]     # RUN.json: never a secret of the run
        confirmed = sum(1 for t in typed if t.blocks)
        return Reviewed(O.COMPLETED, tuple(typed), f"{len(found)} findings" + (f", {coverage}" if coverage else "")
                        + (f", parsed={s.get('parsed')}" if not ocr else "")
                        + (f", confirmed={confirmed}" if confirmed else ""))

    def _model(self, scope, attempt: int) -> tuple[list, dict, str | None]:
        prompt = REVIEW_PROMPT.format(story=scope.story_id, name=self.project.name, requirements=self.project.requirements_path,
                                      clauses=feedback.clauses(self.project, scope.story_id))
        s = client.session(f"reviewer {scope.story_id}", prompt, scope.root,
                           self.logs / f"{scope.story_id}.reviewer.{attempt}.jsonl", self.timeout_s, **self.kw)
        s.update(story_id=scope.story_id, attempt=attempt, role="reviewer", prompt_sha256=_sha(prompt.encode("utf-8")))
        self.sessions.append(s)
        if s["error"] and not s["text"]:
            raise ProviderOutage(s["error"])
        found = []
        braced = _braces(s["text"])
        try:
            found = json.loads(braced)["findings"] if braced is not None else []
        except (ValueError, KeyError, RecursionError):
            # a {...} match loads as an object or not at all: no TypeError is possible; nested past the parser's depth
            # (a RecursionError) is text that does not parse, like any other
            found = []
        s["parsed"] = braced is not None
        return ([f for f in found if isinstance(f, dict)] if isinstance(found, list) else []), s, None

    def _ocr(self, scope, attempt: int, head: str) -> tuple[list, dict, str]:
        """Open Code Review on exactly the story's change (app/review_ocr): the controller's scope, its pinned binary
        (the bytes, then what it declares, both before any review command), its environment and HOME, a preview then
        the review, one session stream the budget and the evidence read."""
        pin = self.review_policy["ocr"]
        why = review_ocr.pinned(pin["exe"], pin["sha256"])
        if why:
            raise CapabilityUnrunnable(why)
        declared, why = _declared(pin["exe"], review_ocr.VERSION_TIMEOUT_S)     # before any review command, its own bound
        if why:
            raise CapabilityUnrunnable(why)
        story = scope.story_id
        base = next((e.data["parent"] for e in reversed(self.run.events)
                     if e.type == "story/begin" and e.data.get("story_id") == story), None)
        if base is None:
            raise CapabilityUnrunnable(f"the journal names no parent of {story}")
        # -z: NUL ends every field and no path is quoted, so a path is read whole whatever its characters and the
        # repository's core.quotepath (git's default prints a non-ASCII path C-quoted); --no-renames: a row is a
        # status letter and one path
        changed = git(scope.root, "diff", "-z", "--name-status", "--no-renames", f"{base}..{head}")
        if changed.returncode != 0:
            raise CapabilityUnrunnable(f"git diff {base[:12]}..{head[:12]} exited {changed.returncode}")
        fields = changed.stdout.split("\0")[:-1]       # the last field is closed by its NUL too
        rows = list(zip(fields[0::2], fields[1::2], strict=False))
        if 2 * len(rows) != len(fields) or any(len(k) != 1 for k, _ in rows):   # a row of two paths, a dangling status
            raise CapabilityUnrunnable(f"git diff {base[:12]}..{head[:12]} printed a row of another shape: {fields[:3]!r}")
        mine = [(k, p) for k, p in rows if p.split("/")[0] in self.project.product_roots]
        required = sorted(p for k, p in mine if k != "D")
        log = self.logs / f"{story}.reviewer.{attempt}.jsonl"
        budget = self.kw["budget"]
        stopped = f"{log.name} exists: a session's evidence is never overwritten" if log.exists() \
            else budget.reached(in_progress=True)
        if stopped:
            raise ProviderOutage(stopped)
        work = self.logs.parent / "review" / f"{story}.{attempt}"
        (work / "home").mkdir(parents=True)
        rule, background = work / "rule.json", work / "background.md"
        rule.write_text(json.dumps({"include": [f"{r}/**" for r in self.project.product_roots]}), encoding="utf-8")
        background.write_text(OCR_BACKGROUND.format(name=self.project.name, requirements=self.project.requirements_path,
                                                    clauses=feedback.clauses(self.project, story)), encoding="utf-8")
        env = review_ocr.environment({**self.route.get("env", {}), **ISOLATED_GIT}, work / "home",
                                     {k: self.route[k] for k in ("url", "token", "model")})
        spent = budget.spend()
        room = max(1, sum(budget.limits[k] - spent[k] for k in ("input_tokens", "output_tokens")))
        common = {"repo": scope.root, "base": base, "head": head, "rule": str(rule), "model": self.route["model"],
                  "max_tokens": pin["max_tokens"], "budget_tokens": room, "timeout_min": pin["timeout_min"],
                  "background_file": str(background)}
        started = time.monotonic()
        code_p = _bounded(review_ocr.argv(pin["exe"], output=str(work / "preview.json"), preview=True, **common),
                          scope.root, env, work / "preview.log", self.timeout_s, f"ocr preview {story}")
        preview = review_ocr.read_output(work / "preview.json")
        keys = (*self.kw.get("secrets", ()), self.route["token"])     # what the session stream is redacted with
        for raw in ("preview.json", "preview.log"):     # the finder's own copies: read above, they keep no secret
            client.redact(work / raw, keys)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("x", encoding="utf-8") as fh:     # before the review starts: a stream that exists may have spent
            fh.write(json.dumps({"type": "ocr_started", "finder": f"ocr {review_ocr.OCR['version']}"}) + "\n")
        code = _bounded(review_ocr.argv(pin["exe"], output=str(work / "output.json"), **common), scope.root, env,
                        work / "ocr.log", self.timeout_s, f"ocr review {story}")
        output = review_ocr.read_output(work / "output.json")
        for raw in ("output.json", "ocr.log"):     # likewise: the comments' reproducers are in `output`, in memory
            client.redact(work / raw, keys)
        summary = (output or {}).get("summary") or {}
        counts = [summary.get(k) for k in ("input_tokens", "output_tokens")]
        tokens = ({"input": counts[0], "output": counts[1], "reasoning": 0,
                   "cache": {"read": int(summary.get("cache_read_tokens") or 0),
                             "write": int(summary.get("cache_write_tokens") or 0)}}
                  if all(isinstance(c, int) and not isinstance(c, bool) for c in counts) else None)
        lines = [{"type": "ocr_preview", "exit": code_p, "document": preview},
                 {"type": "ocr_output", "exit": code, "document": output},
                 {"type": "text", "part": {"text": str((output or {}).get("message") or "")}},
                 {"type": "step_finish", "part": {"tokens": tokens} if tokens else {}}]  # no tokens: unaccounted
        with log.open("a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(x, sort_keys=True) + "\n" for x in lines))
        redacted = client.redact(log, keys)
        seen = client.read_session(log)
        s = {"exit": code, "timed_out": code is None, "stopped": None, "started": True, "error": seen["error"],
             "text": seen["text"], "turns": seen["turns"], "tokens": seen["tokens"],
             "seconds": round(time.monotonic() - started, 1), "log": log.name, "redacted": redacted,
             "story_id": story, "attempt": attempt, "role": "reviewer", "finder": f"ocr {review_ocr.OCR['version']}",
             "required": required, "deleted": sorted(p for k, p in mine if k == "D"),
             "identity": {"sha256_checked": pin["sha256"], "declared": declared,
                          "declared_by": "the binary's own `version` output: a self-declaration, not build evidence"}}
        self.sessions.append(s)
        cov = review_ocr.coverage(output, -1 if code is None else code, required=required, base=base, head=head,
                                  preview=preview)
        s["coverage"] = {"status": cov.status, "reasons": list(cov.reasons), "not_reviewable": list(cov.not_reviewable)}
        if cov.status != review_ocr.COMPLETE:
            what = ("timed out: " if code is None else "") + "; ".join(cov.reasons)
            if cov.failure == "provider" or (cov.failed and all(i.get("classification") == "provider" for i in cov.failed)):
                raise ProviderOutage(f"OCR could not reach the provider: {what}"[:600])
            if self.review_policy["policy"] == "fix-loop":
                raise CapabilityUnrunnable(f"review coverage INDETERMINATE (the candidate was not fully reviewed): {what}"[:600])
        return review_ocr.findings(output, required), s, f"coverage {cov.status}" + (
            f" ({'; '.join(cov.reasons)[:300]})" if cov.reasons else "")

    def _verify(self, finding: dict, root: str, head: str) -> review_verify.Verification:
        if not isinstance(finding.get("reproducer"), dict):
            return review_verify.Verification(review_verify.UNVERIFIABLE, "no reproducer: the finding states no observable behaviour")
        tapped = {} if self.diagnostics is None else {"entries": self.diagnostics.entries(self._at)}
        return review_verify.verify(finding, requirements=self.project.requirements,
                                    product_roots=self.project.product_roots, root=root, revision=head,
                                    timeout_s=self.probe_timeout_s, interpreter=self.interpreter, **tapped)


def tree_of(root: str) -> dict[str, str]:
    """Every entry of a checkout but its .git, by relative path: a file's sha256, a link's target, a directory."""
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]     # the walk order reaches no reader: compared as a mapping
        for name in [*dirs, *files]:
            p = pathlib.Path(d, name)
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                out[rel] = "link:" + os.readlink(p)
            elif p.is_dir():
                out[rel] = "dir"
            else:
                try:
                    out[rel] = _sha(p.read_bytes())
                except OSError as e:
                    out[rel] = f"unreadable:{type(e).__name__}"
    return out


def _unchanged(root: str, head: str, before: dict, during: str) -> None:
    now = git(root, "rev-parse", "HEAD")
    if now.returncode != 0 or now.stdout.strip() != head:
        raise CapabilityUnrunnable(f"the reviewed checkout changed during {during}: HEAD is no longer {head[:12]} "
                                   "(every finding discarded)")
    after = tree_of(root)
    if after != before:
        diff = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        raise CapabilityUnrunnable(f"the reviewed checkout changed during {during}: {diff[:10]} (every finding discarded)")


def _declared(exe: str, timeout_s: float) -> tuple[dict | None, str | None]:
    """What `exe` says it is (app/review_ocr.declared), asked once before any review command, in a clean environment:
    nothing inherited, an empty HOME that is its working directory, no repository and no model route."""
    with tempfile.TemporaryDirectory(prefix="aisef-ocr-version-") as d:
        home = pathlib.Path(d, "home")
        home.mkdir()
        out = pathlib.Path(d, "version.out")
        try:
            code = _bounded(review_ocr.version_argv(exe), str(home), review_ocr.version_environment(home, os.environ),
                            out, timeout_s, "ocr version")
        except (OSError, RangeError) as e:      # not executable, or the range could not start it
            return None, f"{exe}: `version` could not be started ({type(e).__name__}: {str(e)[:300]})"
        text = out.read_bytes()[:4096].decode("utf-8", "replace")
    return review_ocr.declared(exe, code, text)


def _bounded(argv: list[str], cwd: str, env: dict, out: pathlib.Path, timeout_s: float, name: str) -> int | None:
    """One process in a range of its own, its output to `out`; its exit status, or None when `timeout_s` ran out (the
    range is released either way)."""
    with out.open("x", encoding="utf-8") as fh:
        r = ProcessRange(name, argv, cwd=cwd, env=env, output=fh)
        r.start()
        try:
            deadline, code = time.monotonic() + timeout_s, None
            while code is None and time.monotonic() < deadline:
                code = r.wait(min(client.POLL_S, max(0.0, deadline - time.monotonic())))
            return code
        finally:
            r.release()


class RuffScanner:
    """ruff as an informational scanner, run by the kernel in its owned range; its findings never block."""
    name = "ruff"

    def __init__(self, exe: str) -> None:
        self.exe = exe

    def argv(self, scope, report: str) -> tuple[str, ...]:
        return (self.exe, "check", "--exit-zero", "--no-cache", "--output-format", "json", "--output-file", report, scope.root)

    def read(self, report: str, exit_code) -> Scanned:
        p = pathlib.Path(report)
        if not p.exists():
            return Scanned(False, ())
        rows = json.loads(p.read_text(encoding="utf-8") or "[]")
        return Scanned(True, tuple(Finding(f"{r.get('code')}:{pathlib.Path(r.get('filename', '')).name}:"
                                           f"{(r.get('location') or {}).get('row')}", False, ("scanner:ruff",)) for r in rows))


class NoScanner:
    """No scanner on this machine: the stage runs and reports no finding (the record names it)."""
    name = "none"

    def argv(self, scope, report: str) -> tuple[str, ...]:
        return (sys.executable, "-I", "-c", "import sys; open(sys.argv[1], 'w').write('[]')", report)

    def read(self, report: str, exit_code) -> Scanned:
        return Scanned(pathlib.Path(report).exists(), ())


def scanner():
    exe = shutil.which("ruff")
    return RuffScanner(exe) if exe else NoScanner()
