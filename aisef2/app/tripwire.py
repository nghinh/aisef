"""ROADMAP-2.2 G1 — the stimulus serve-surface tripwire (DEVELOPER-CONFINEMENT-GAP-001).

A proof is independent of the developer only while the sealed stimulus and expected observable stay out of
everything the developer (and the review finder) is served. This module makes that mechanical: the needles are the
contracts' own stimulus/observable content (canonical JSON of each mapping, of each composite element, and every
string leaf, at least MIN_NEEDLE canonical characters), matched raw and in their JSON-escaped spelling; a needle
that also occurs in the bundle's public text (facts, name, description — served to the developer by design) cannot
distinguish a leak and is DROPPED, by name; a contract that yields no needle is UNSCANNED, by name — short stimuli
are tripwire-blind and the record says so rather than silently passing or refusing every small project.

What a hit means: the scanned surfaces are kernel-built (the prompt) or kernel-staged (the repository tree at the
baseline), so a match is a real leak or the project's own bundle committed into the tree the developer reads —
find the read path that produced it; it is not a false positive to widen around. What this is NOT: confinement.
The run directory (journal, probe scratch, the clone) stays host-reachable from an unconfined session (V21-02);
the record's statement says exactly that."""

from __future__ import annotations

import json
import pathlib
from typing import Any, Mapping

MIN_NEEDLE = 16
MAX_FILE_BYTES = 2 * 1024 * 1024    # a serve-surface scan reads text the size of source files, not media
BUNDLE_MARKERS = ("aisef-v2-project/1", "aisef-v2-authoring/1")
STATEMENT = ("a mechanical serve-surface tripwire, not confinement: the repository tree at the baseline and every "
             "prompt were scanned for the sealed stimulus/observable content before serving; the run directory "
             "(journal, probe scratch, the clone) remains host-reachable from an unconfined session (V21-02 open). "
             "Contracts under 'unscanned' yield no needle of at least %d canonical characters and are not covered."
             % MIN_NEEDLE)
FOUND = ("this is a leak, not a false positive to widen around: find the read path that put the sealed content "
         "there. Remove the project bundle (and any copy of a contract's stimulus/observable) from the repository "
         "history served to the developer, or change the contract, and run again.")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _fragments(value: Any) -> set[str]:
    """The canonical form of the value, of every composite element under it, and every string leaf."""
    out = {_canonical(value)}
    if isinstance(value, Mapping):
        for v in value.values():
            out |= _fragments(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            out |= _fragments(v)
    elif isinstance(value, str):
        out.add(value)
    return out


def _public_text(project) -> str:
    """Every string the bundle serves the developer by design: the facts, the name, the description, the paths."""
    parts = [project.name, project.description, project.requirements_path, *project.product_roots]
    for fact in project.facts.values():
        parts += [str(v) for v in fact.values()]
    return "\n".join(parts)


def needles_of(project) -> dict:
    """The needle set of a project: {"needles": {needle: contract_id}, "dropped": [...], "unscanned": [...]}."""
    public = _public_text(project)
    needles: dict[str, str] = {}
    dropped: list[str] = []
    unscanned: list[str] = []
    for spec in project.specs.values():
        mine = set()
        for key in ("stimulus", "observable"):
            for fragment in _fragments(spec.probe_input[key]):
                if len(fragment) >= MIN_NEEDLE:
                    mine.add(fragment)
        kept = 0
        for n in sorted(mine):
            if n in public:
                dropped.append(f"{spec.contract_id}: a {len(n)}-char needle occurs in the bundle's public text")
                continue
            needles.setdefault(n, spec.contract_id)
            kept += 1
        if not kept:
            unscanned.append(spec.contract_id)
    return {"needles": needles, "dropped": sorted(set(dropped)), "unscanned": sorted(set(unscanned))}


def scan_text(text: str, needles: Mapping[str, str]) -> list[dict]:
    """Every needle `text` carries, raw or JSON-escaped — reported as contract id and length, NEVER the value."""
    hits = []
    for needle, contract in needles.items():
        if needle in text or json.dumps(needle, ensure_ascii=False)[1:-1] in text:
            hits.append({"contract": contract, "needle_chars": len(needle)})
    return hits


def _bundle_hit(text: str, project) -> bool:
    """Whether `text` is a bundle/authoring document OF THIS PROJECT (its plan, digest or any contract id)."""
    if not any(marker in text for marker in BUNDLE_MARKERS):
        return False
    try:
        doc = json.loads(text)
    except ValueError:
        return True     # carries the format marker but does not parse: refuse rather than guess (fail closed)
    if not isinstance(doc, dict) or doc.get("format") not in BUNDLE_MARKERS:
        return True
    ids = {c.get("id") for c in doc.get("contracts", []) if isinstance(c, dict)}
    plan = doc.get("plan") if isinstance(doc.get("plan"), dict) else {}
    return bool(ids & set(project.contracts)) or plan.get("plan_hash") == project.plan.plan_hash


def scan_repo(repo: pathlib.Path, project, wire: Mapping) -> dict:
    """Scan the checked-out repository tree (the baseline the kernel just staged; .git excluded) for the project's
    bundle and for stimulus/observable content. The report, with `hits` for the caller to refuse on."""
    files = 0
    hits: list[dict] = []
    for p in sorted(pathlib.Path(repo).rglob("*")):
        if not p.is_file() or ".git" in p.parts:
            continue
        files += 1
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
            text = p.read_bytes().decode("utf-8", "replace")
        except OSError:
            continue
        rel = p.relative_to(repo).as_posix()
        if _bundle_hit(text, project):
            hits.append({"file": rel, "contract": "(the project bundle itself)", "needle_chars": 0})
        hits += [{"file": rel, **h} for h in scan_text(text, wire["needles"])]
    return {"files_scanned": files, "needles": len(wire["needles"]), "dropped": list(wire["dropped"]),
            "unscanned": list(wire["unscanned"]), "hits": hits,
            "verdict": "LEAK" if hits else "CLEAN", "statement": STATEMENT}


def refusal(hits: list[dict], where: str) -> str:
    named = "; ".join(f"{h.get('file', where)}: contract {h['contract']}"
                      + (f" ({h['needle_chars']} chars)" if h.get("needle_chars") else "")
                      for h in hits[:5])
    return (f"sealed stimulus/observable content would reach the developer via {where}: {named}"
            + (f" (+{len(hits) - 5} more)" if len(hits) > 5 else "") + ". " + FOUND)
