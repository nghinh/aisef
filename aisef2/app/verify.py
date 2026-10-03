"""Verify a finished run directory from its own evidence: the raw journal reconstructs (format 3: every line's hash
chains to the one before), it is the journal RUN.json names (digest and length), and the record's delivery verdict and
ProductProof account are what the journal and the project bundle re-derive. Nothing is taken from the record that the
journal can say."""

from __future__ import annotations

import hashlib
import json
import pathlib

from aisef2.app import run as R
from aisef2.app.bundle import Project
from aisef2.journal import format3
from aisef2.orchestrate.workspace import git
from aisef2.product.contract import plain


def verify(project: Project, out: pathlib.Path) -> dict:
    problems: list[str] = []
    rec = json.loads((out / "RUN.json").read_text(encoding="utf-8"))
    if rec.get("format") != R.FORMAT:
        return {"verdict": "REFUTED", "problems": [f"RUN.json is not a run record of format {R.FORMAT}"]}
    if rec.get("bundle_digest") != project.digest:
        problems.append("the run is not of this project bundle")
    j = rec.get("journal")
    events: list[dict] = []
    if not j:
        problems.append("the run has no journal (it ended before the run began)")
    else:
        data = (out / j["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != j["sha256"] or data.count(b"\n") != j["lines"]:
            problems.append("the journal is not the one RUN.json names (digest or length)")
        try:
            journal = format3.reconstruct(data.decode("utf-8"))
            events = [{"seq": e.seq, "type": e.type, "data": plain(e.data)} for e in journal.events]
            if journal.torn_tail:
                problems.append("the journal ends in a torn line")
        except Exception as e:  # noqa: BLE001 — any refusal of the reader is the finding
            problems.append(f"the journal does not reconstruct: {type(e).__name__}: {e}"[:500])
    budget = rec.get("budget") or {}
    verdict, _, committed = R.delivery(project, events, rec.get("story_outcomes") or {}, budget.get("reached"),
                                       rec.get("story_errors") or [])
    if rec.get("failure") and verdict == "PASS":
        verdict = "FAIL"
    if rec.get("delivery_verdict") != verdict:
        problems.append(f"the record says {rec.get('delivery_verdict')}; the journal re-derives {verdict}")
    if events and rec.get("productproof") != R.productproof(project, events, committed):
        problems.append("the record's ProductProof account is not the one the journal re-derives")
    if rec.get("final_main") and (out / "repo").exists():
        if git(out / "repo", "rev-parse", "main").stdout.strip() != rec["final_main"]:
            problems.append("the run's repository main is not the record's final main")
    return {"verdict": "REFUTED" if problems else "VERIFIED", "problems": problems, "delivery_verdict": verdict,
            "journal_events": len(events)}
