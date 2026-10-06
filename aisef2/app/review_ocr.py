"""Open Code Review as a reviewer that only finds (V2.1, proposal C). Pinned: alibaba/open-code-review v1.12.12 =
182898cf522da3d04157b422752d028417974e19, Apache-2.0, run as an external process — never vendored, never imported.

What this module decides, and what it leaves to OCR:

* **Scope is AISEF's.** The files a review must cover (`required`) are computed by the caller from git (the candidate's
  changes under the product roots), never taken from OCR. OCR's coverage manifest is then checked against them:
  COMPLETE only if the manifest is OCR's run-manifest v1, its terminal state is `complete` with exit status 0, it reviewed
  exactly the frozen range (resolved head = candidate, resolved base = the merge base), it was this pinned version, every
  required path is `completed` or `reused` under the item_id OCR derives for it (recomputed here), no required path is
  excluded or missing in the preview, and no `code_comment` call failed (a finding may have been dropped). Anything else is
  INDETERMINATE, with every reason — exit 0 is not a full review, and `files_reviewed` is never read as coverage.
* **Findings are claims.** Each OCR comment becomes a finding with a stable id (OCR's own SARIF fingerprint: path, category,
  trimmed existing code or the start line, with an occurrence index after a deterministic sort). OCR states no
  observable behaviour, so a finding is UNVERIFIABLE by app/review_verify and goes to triage: it never blocks.
* **The process is AISEF's.** The argv and environment are built here: an isolated HOME holding only a config this module
  writes, every OCR_/ANTHROPIC_/OTEL_ variable scrubbed, OCR_NO_UPDATE=1, a fresh --output file read instead of stdout,
  the binary by absolute path with its sha256 checked against the operator's pin before it runs.

Code facts cite the upstream source at 182898c (research record: docs/v2.1/UPSTREAM-RESEARCH.md). Not yet exercised
against the real binary (none installed, no approved provider budget): the fixtures are built from OCR's own structs.
The rule file's shape (`include`) is INFERENCE from system_rules.go until a real run confirms it."""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Iterable, Mapping

OCR = {"repository": "https://github.com/alibaba/open-code-review", "version": "v1.12.12",
       "commit": "182898cf522da3d04157b422752d028417974e19", "license": "Apache-2.0"}
MANIFEST_SCHEMA = "ocr.run-manifest/v1"
TERMINAL = ("complete", "partial", "failed", "skipped")
#: warnings after which a complete manifest is still not a full review (llmloop/pool.go, output.go)
NOT_FULL = ("review_round_failed", "token_threshold_exceeded", "token_budget_reached")
SCRUB_PREFIXES = ("OCR_", "ANTHROPIC_", "OTEL_")
COMPLETE, INDETERMINATE = "COMPLETE", "INDETERMINATE"


def item_id(mode: str, old_path: str, new_path: str) -> str:
    """OCR's manifest item_id (internal/session/manifest.go ItemID): sha256 of review, mode, old, new joined by NUL."""
    norm = [str(pathlib.PurePosixPath(p.replace("\\", "/"))) if p else "" for p in (old_path, new_path)]
    return hashlib.sha256("\x00".join(["review", mode, *norm]).encode("utf-8")).hexdigest()


def finding_id(comment: Mapping) -> str:
    """OCR's SARIF fingerprint (cmd/opencodereview/sarif.go): path|category|trimmed existing code, else the start line."""
    category = comment.get("category") or "other"
    code = str(comment.get("existing_code") or "").strip()
    source = f"{comment.get('path', '')}|{category}|{code if code else int(comment.get('start_line') or 0)}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Coverage:
    status: str
    reasons: tuple[str, ...]
    terminal_state: str | None
    failed: tuple[dict, ...] = field(default_factory=tuple)


def coverage(output: Mapping | None, exit_code: int, *, required: Iterable[str], base: str, head: str,
             preview: Mapping | None = None) -> Coverage:
    """Whether OCR's run reviewed every required path of exactly the frozen range (module docstring)."""
    required = sorted(set(required))
    reasons: list[str] = []
    m = (output or {}).get("manifest") if isinstance(output, Mapping) else None
    if not isinstance(m, Mapping):
        return Coverage(INDETERMINATE, ("no run manifest: nothing says what was reviewed",), None)
    if m.get("schema_version") != MANIFEST_SCHEMA:
        return Coverage(INDETERMINATE, (f"manifest schema {m.get('schema_version')!r}, not {MANIFEST_SCHEMA}",), None)
    state = m.get("terminal_state")
    if state != "complete":
        reasons.append(f"terminal state {state!r}")
    if exit_code != 0:
        reasons.append(f"exit status {exit_code}")
    inp = m.get("input") or {}
    if inp.get("resolved_head") != head:
        reasons.append(f"reviewed head {str(inp.get('resolved_head'))[:12]}, not the candidate {head[:12]}")
    if inp.get("resolved_base") != base:
        reasons.append(f"reviewed base {str(inp.get('resolved_base'))[:12]}, not {base[:12]}")
    version = (m.get("execution") or {}).get("ocr_version")
    if version != OCR["version"]:
        reasons.append(f"OCR {version!r}, not the pinned {OCR['version']}")
    cov = m.get("coverage") or {}
    mode = inp.get("mode", "")
    done: dict[str, str] = {}
    for item in [*(cov.get("completed") or []), *(cov.get("reused") or [])]:
        path = item.get("path", "")
        if item.get("item_id") != item_id(mode, item.get("old_path") or path, path):
            reasons.append(f"{path}: its item_id is not the one OCR derives for it")
            continue
        done[path] = item["item_id"]
    missing = [p for p in required if p not in done]
    if missing:
        reasons.append(f"required paths not completed: {missing[:10]}")
    if preview is not None:
        files = {f.get("path"): f for f in preview.get("files") or []}
        excluded = [f"{p} ({files[p].get('exclude_reason')})" for p in required if p in files and not files[p].get("will_review")]
        absent = [p for p in required if p not in files]
        if excluded:
            reasons.append(f"required paths the preview excludes: {excluded[:10]}")
        if absent:
            reasons.append(f"required paths absent from the preview (gitignored or a provider directory): {absent[:10]}")
    dropped = [d for d in ((output.get("tool_calls") or {}).get("failure_details") or []) if d.get("tool_name") == "code_comment"]
    if dropped:
        reasons.append(f"{len(dropped)} code_comment call(s) failed: findings may have been dropped")
    for w in output.get("warnings") or []:
        if w.get("type") == "manifest_error" or w.get("type") in NOT_FULL:
            reasons.append(f"warning {w.get('type')}: {str(w.get('message'))[:120]}")
    return Coverage(COMPLETE if not reasons else INDETERMINATE, tuple(reasons), state, tuple(cov.get("failed") or ()))


def findings(output: Mapping | None, required: Iterable[str]) -> list[dict]:
    """OCR's comments as triage findings: a stable id, OCR's severity, in or out of the required scope; no reproducer,
    so never blocking (app/review_verify: UNVERIFIABLE)."""
    comments = [c for c in ((output or {}).get("comments") or []) if isinstance(c, Mapping)]
    comments.sort(key=lambda c: (str(c.get("path")), int(c.get("start_line") or 0), str(c.get("category")),
                                 str(c.get("content"))))
    required, seen, out = set(required), {}, []
    for c in comments:
        fid = finding_id(c)
        n = seen[fid] = seen.get(fid, -1) + 1
        out.append({"id": f"ocr-{fid[:12]}-{n}", "blocking": False, "severity": c.get("severity") or "low",
                    "category": c.get("category") or "other", "summary": str(c.get("content", ""))[:400],
                    "path": c.get("path"), "start_line": c.get("start_line") or 0,
                    "in_scope": c.get("path") in required, "source": f"ocr {OCR['version']}"})
    return out


def environment(base: Mapping[str, str], home: pathlib.Path) -> dict[str, str]:
    """The process environment: the operator's minus every OCR, Anthropic and OpenTelemetry variable, an isolated home,
    no self-update (bin/ocr.js) and no telemetry (telemetry/config.go)."""
    env = {k: v for k, v in base.items() if not k.startswith(SCRUB_PREFIXES)}
    return env | {"HOME": str(home), "USERPROFILE": str(home), "OCR_NO_UPDATE": "1"}


def argv(exe: str, *, repo: str, base: str, head: str, rule: str, output: str, provider: str, model: str,
         max_tokens: int, budget_tokens: int, timeout_min: int, background_file: str, preview: bool = False) -> list[str]:
    """`ocr review` on exactly base..head (full SHAs), the controller's rule and background, one fresh output file."""
    out = [exe, "review", "--repo", repo, "--from", base, "--to", head, "--rule", rule, "--format", "json",
           "--output", output]
    if preview:
        return out + ["--preview"]
    return out + ["--audience", "agent", "--provider", provider, "--model", model, "--effort", "high",
                  "--max-tokens", str(max_tokens), "--max-tokens-budget", str(budget_tokens), "--concurrency", "1",
                  "--timeout", str(timeout_min), "--no-filter", "--background-file", background_file]


def pinned(exe: str, sha256: str) -> str | None:
    """Why the binary at `exe` may not run: not an absolute path, unreadable, or not the operator's pinned bytes."""
    p = pathlib.Path(exe)
    if not p.is_absolute():
        return f"{exe}: the OCR binary is named by an absolute path, never looked up"
    try:
        have = hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError as e:
        return f"{exe}: cannot be read ({type(e).__name__})"
    return None if have == sha256 else f"{exe}: sha256 {have[:12]}, not the pinned {sha256[:12]}"


def read_output(path: pathlib.Path) -> dict | None:
    """The one JSON document OCR wrote to --output, or None (a failed run may write nothing; stdout is never parsed)."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def scrubbed_names(base: Mapping[str, str]) -> list[str]:
    """The variable names `environment` removes (names only, for the record; never values)."""
    return sorted(k for k in base if k.startswith(SCRUB_PREFIXES))

