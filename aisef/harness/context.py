"""Code map around write scope — static context for a new session (ADR-005 V7).

A developer entering a fresh session has no map: on e9 the first turn costs
42-91 rounds, mostly probing "what does this file define, who calls it, which
tests touch it"; a reviewer spends 22-68 rounds on the same questions. Aider
answers with a repo map ranked by PageRank over the identifier graph;
Agentless measured that **skeleton** (signatures, body -> `...`) beats full
files in both accuracy and cost (58% @ $0.02 vs 54% @ $0.15). Here we take
both ideas using stdlib, **one hop** around write scope:

  (a) skeleton of in-scope files — Python via `ast`, TS/JS via
      `_EXPORTS` + inline signatures;
  (b) out-of-scope files referencing names in scope (callers) and files
      imported by scope — each file <= 3 lines;
  (c) test files referencing names in scope.

This is a **static hint**, not ground truth — same limitations as
`control/impact.py`: dynamic calls, reflection, dependency injection are
invisible. The character budget is by design, not a compromise; Aider does
not publish measurements for repo map, so `context.max_repo_map_chars`
defaults to 0 (off) until A/B T8 provides numbers. The full map is always
available via `aisef ctx --story S`.

External provider (`context.map_provider`, tree-sitter/serena pluggable
later) receives stdin JSON ``{project, seeds, budget}`` and returns text;
on failure falls back to the built-in and reports it on the first line —
same pattern as `review.impact_provider`.

# ponytail: 1-hop neighbours; stdlib PageRank ~20 lines when repo > 500 files
# would blow the neighbour budget.
"""

from __future__ import annotations

import ast
import json
import math
import os
import re
import shlex
import subprocess
from collections import defaultdict
from pathlib import Path

from ..clients.base import split_command
from ..control.impact import _EXPORTS, SOURCE_EXT, _rel_files, is_test_path, refs, symbols, weights

#: Aider `to_tree` truncates at 100 chars/line — enough to read signatures, not enough to copy bodies.
MAX_LINE = 100
#: Max lines per neighbour file.
PER_NEIGHBOUR = 3
#: Identifiers in the story shorter than this are common words, not code names.
MIN_IDENT = 5
_IDENT = re.compile(r"[A-Za-z][\w-]{%d,}" % (MIN_IDENT - 1), re.ASCII)
_IMPORT_JS = re.compile(r"""(?:from|require\()\s*['"](\.{1,2}/[^'"]+)['"]""")
_IMPORT_PY = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([\w.]+))", re.M)

HEADING = "## Code map around write scope — static hints, not ground truth"


def seeds_for(story, project: Path | str, *, artifact_root: Path | str, config=None) -> list[str]:
    """Seeds for a story: effective write scope ∪ verification paths
    ∪ identifiers >= 5 chars from the story file (Aider `get_ident_mentions`)."""
    from ..control.normalize import effective_write_scope, verification_paths

    project = Path(project)
    seeds = list(effective_write_scope(story, project))
    seeds += [p for p in verification_paths(story, project, config) if p not in seeds]
    f = Path(artifact_root) / "stories" / story.epic_id / f"{story.id}.md"
    text = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else (
        story.title + "\n" + "\n".join(story.acceptance_criteria)
    )
    seen = set(seeds)
    for tok in _IDENT.findall(text):
        if tok not in seen:
            seen.add(tok)
            seeds.append(tok)
    return seeds


def repo_map(project: Path | str, seeds: list[str], budget_chars: int = 0, *,
             command: str = "", story_id: str = "", timeout: int = 120) -> str:
    """Map around ``seeds`` (real paths = scope; rest = identifiers), truncated
    at ``budget_chars`` (0 = no truncation). Uses external command if given;
    falls back to built-in on failure and notes it on the first line."""
    project = Path(project)
    note = ""
    if command.strip():
        got = _run_provider(project, seeds, budget_chars, command, timeout)
        if got is not None:
            return _cut(f"_Source: {command.split()[0]}._\n\n{got}", budget_chars, story_id)
        note = f" · **raw** — `context.map_provider` failed ({command.split()[0]}), fell back to built-in"
    text = f"_Source: built-in (stdlib, 1-hop neighbours){note}._\n\n" + _builtin(project, seeds)
    return _cut(text, budget_chars, story_id)


def prompt_section(map_text: str) -> str:
    """Prompt section for all three roles; empty when there is no map (knob 0)
    so the prompt doesn't carry a blank heading."""
    if not map_text.strip():
        return ""
    return (
        f"{HEADING}\n\n"
        "This is a **hint**, not ground truth: static analysis cannot see dynamic calls, "
        "reflection, or dependency injection. Do not stop here, and do not skip what it "
        "does not mention. Full map: `aisef ctx --story <id>`.\n\n" + map_text
    )


# ------------------------------------------------------------------ built-in


def _builtin(project: Path, seeds: list[str]) -> str:
    scope, idents = _split_seeds(project, seeds)
    if not scope:
        return "_(write scope has no source files on disk — story starts from scratch)_"
    files = list(_rel_files(project))
    syms = symbols(project, scope)
    names = sorted({n for s in syms.values() for n, _, _ in s})
    w = weights(project, names, files)
    # Aider: files whose stem matches a story identifier get a 10x boost.
    boost = lambda rel: 10.0 if any(i in Path(rel).stem.lower() for i in idents) else 1.0  # noqa: E731

    score: dict[str, float] = defaultdict(float)
    hit: dict[str, set[str]] = defaultdict(set)
    for name, per_file in refs(project, names, files).items():
        for rel, n in per_file.items():
            if rel in scope or w[name] <= 0:
                continue
            score[rel] += w[name] * math.sqrt(n)
            if w[name] >= 1:
                hit[rel].add(name)
    imported = {rel for f in scope for rel in _imports(project, f) if rel not in scope}
    for rel in imported:
        score[rel] += 1.0

    out = ["**In scope (skeleton):**"]
    for rel in sorted(scope, key=lambda r: (-boost(r), r)):
        out.append(f"`{rel}`")
        out += [f"  {ln} {sig}" for ln, sig in _skeleton(project / rel, syms.get(rel, []))] or ["  (no exported definitions)"]

    rank = lambda r: (-score[r] * boost(r), r)  # noqa: E731
    near = sorted((r for r in score if not is_test_path(r) and (score[r] >= 1 or r in imported)), key=rank)
    if near:
        out.append("\n**1-hop neighbours (reference names in scope / imported by scope):**")
        for rel in near:
            tag = ", ".join(sorted(hit[rel])[:4]) or "imported"
            out.append(f"`{rel}` · {tag}")
            out += [f"  {ln} {line}" for ln, line in _lines(project / rel, hit[rel], syms_of=rel in imported and not hit[rel])]
    tests = sorted((r for r in score if is_test_path(r) and score[r] >= 1), key=rank)
    if tests:
        out.append("\n**Tests referencing names in scope:**")
        out += [f"- `{rel}` · {', '.join(sorted(hit[rel])[:4])}" for rel in tests]
    return "\n".join(out)


def _split_seeds(project: Path, seeds: list[str]) -> tuple[list[str], set[str]]:
    """Seeds that are real paths (file, directory, glob) become scope; the rest
    become identifiers (lowercased, matched against file stems for 10x boost)."""
    scope: list[str] = []
    idents: set[str] = set()
    for s in seeds:
        p = project / s
        if p.is_file():
            hits = [p]
        elif p.is_dir():
            hits = [f for f in sorted(p.rglob("*")) if f.is_file()]
        elif any(c in s for c in "*?["):
            # `src/**` matches **directories only** on Python <= 3.12 (3.13+
            # matches files too) — a write scope written that way would produce
            # an empty map on the very versions this package claims to support
            # (CI Linux 3.12, 2026-09-06). Normalize to `**/*`: same result
            # on 3.11 through 3.14.
            pat = s + "/*" if s.endswith("**") else s
            hits = [f for f in sorted(project.glob(pat)) if f.is_file()]
        else:
            if len(s) >= MIN_IDENT:
                idents.add(s.lower())
            continue
        for f in hits:
            rel = f.relative_to(project).as_posix()
            if f.suffix in SOURCE_EXT and rel not in scope and not ({"node_modules", ".git"} & set(f.parts)):
                scope.append(rel)
    return scope, idents


def _skeleton(path: Path, syms: list[tuple[str, int, str]]) -> list[tuple[int, str]]:
    """Definition lines + signatures, body -> `...` (Agentless `get_skeleton`)."""
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if path.suffix == ".py":
        got = _py_skeleton(body)
        if got:
            return got
    lines = body.splitlines()
    out = []
    for _, ln, _ in syms:
        # TS/JS signatures often span multiple lines (`export function X(\n  props: P\n) {`):
        # join up to the line containing `{` or `;`, max 6 lines, then cut at `{`.
        chunk = []
        for i, l in enumerate(lines[ln - 1: ln + 5]):
            chunk.append(l.strip())
            nxt = lines[ln + i] if ln + i < len(lines) else ""
            if "{" in l or ";" in l or not nxt.strip() or any(p.match(nxt) for p in _EXPORTS):
                break
        sig = " ".join(chunk)
        # Cut at the **last** `{` — destructured params (`({ onReload }: Props) {`)
        # also contain `{`; then strip trailing `=` / `=>` (`export type X =`, `() =>`).
        sig = sig.rsplit("{", 1)[0] if "{" in sig else sig
        sig = re.sub(r"\s*(?:=>|=)\s*$", "", sig.rstrip())
        out.append((ln, sig[:MAX_LINE] + " …"))
    return out


def _py_skeleton(body: str) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return []

    def sig(n) -> str:
        if isinstance(n, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in n.bases)
            return f"class {n.name}({bases}):" if bases else f"class {n.name}:"
        ret = f" -> {ast.unparse(n.returns)}" if n.returns else ""
        kw = "async def" if isinstance(n, ast.AsyncFunctionDef) else "def"
        return f"{kw} {n.name}({ast.unparse(n.args)}){ret}: …"

    out = []
    for n in tree.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or n.name.startswith("_"):
            continue
        out.append((n.lineno, sig(n)[:MAX_LINE]))
        if isinstance(n, ast.ClassDef):
            out += [(m.lineno, "    " + sig(m)[:MAX_LINE]) for m in n.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and (not m.name.startswith("_") or m.name == "__init__")]
    return out


def _lines(path: Path, names: set[str], *, syms_of: bool) -> list[tuple[int, str]]:
    """Up to 3 lines from a neighbour file: lines referencing names in scope;
    for import-only files, take its first exported definition lines instead."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    if syms_of:
        picks = [i + 1 for i, l in enumerate(lines) if any(pat.match(l) for pat in _EXPORTS)]
    else:
        pat = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\b") if names else None
        picks = [i + 1 for i, l in enumerate(lines) if pat and pat.search(l)]
    return [(ln, lines[ln - 1].strip()[:MAX_LINE]) for ln in picks[:PER_NEIGHBOUR]]


def _imports(project: Path, rel: str) -> list[str]:
    """Files that ``rel`` imports, limited to files that exist in the repo
    (relative JS/TS imports; relative and package-absolute Python imports)."""
    f = project / rel
    root = project.resolve()
    try:
        body = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[str] = []
    cands: list[Path] = []
    if f.suffix == ".py":
        for m in _IMPORT_PY.finditer(body):
            mod = m.group(1) or m.group(2)
            dots = len(mod) - len(mod.lstrip("."))
            base = f.parents[dots - 1] if dots else project
            cands.append(base / Path(*mod.lstrip(".").split(".")) if mod.lstrip(".") else base)
    else:
        cands += [f.parent / m.group(1) for m in _IMPORT_JS.finditer(body)]
    for c in cands:
        for cand in (c, *(c.with_suffix(e) for e in SOURCE_EXT), *(c / f"index{e}" for e in SOURCE_EXT)):
            if cand.is_file() and cand.suffix in SOURCE_EXT and root in cand.resolve().parents:
                r = Path(os.path.normpath(cand)).relative_to(os.path.normpath(project)).as_posix()
                if r != rel and r not in out:
                    out.append(r)
                break
    return out


def _run_provider(project: Path, seeds: list[str], budget: int, command: str, timeout: int) -> str | None:
    try:
        proc = subprocess.run(
            split_command(command), cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            input=json.dumps({"project": str(project), "seeds": seeds, "budget": budget}),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip()


def _cut(text: str, budget: int, story_id: str) -> str:
    """Truncate at a line boundary, with a tail pointing to the full map (R6).
    Result is always <= ``budget`` chars."""
    if budget <= 0 or len(text) <= budget:
        return text
    tail = f"\n_(truncated — `aisef ctx --story {story_id or '<id>'}`)_"
    keep = text[: max(budget - len(tail), 0)]
    keep = keep[: keep.rfind("\n")] if "\n" in keep else keep
    return (keep.rstrip() + tail)[:budget]


__all__ = ["HEADING", "prompt_section", "repo_map", "seeds_for"]
