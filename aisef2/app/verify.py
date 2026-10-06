"""Verify a finished run directory from its own evidence: the raw journal reconstructs (format 3: every line's hash
chains to the one before), it is the journal RUN.json names (digest and length), and the record's delivery verdict and
ProductProof account are what the journal and the project bundle re-derive.

V2.1 (V2-02, backlog V21-30): nothing that could RAISE a verdict is taken from the record. The story outcomes are the
journal's decisions; the settings the record names are bound to the journal by re-deriving the RunSpec hash the
journal chained (capability/resolved + run/spec-resolved); the spend is re-derived from the session streams and the
preflight ledger with those settings' ceilings; a story the journal shows begun and never ended is a refused story.
What the record alone says can only LOWER the verdict (a run failure, a refused story, a budget stop) — and the
record and every evidence file are bound by EVIDENCE.json, whose digest is the anchor the run printed: given that
anchor (`expect_anchor`), a consistent rewrite of the whole directory is refuted too. Without it, verification proves
consistency, not authenticity: the run directory is writable by its operator's user."""

from __future__ import annotations

import hashlib
import json
import pathlib

from aisef2.app import client, preflight, settings, usage
from aisef2.app import run as R
from aisef2.app.bundle import Project
from aisef2.arch.enums import Enforcement, IdentityGrade
from aisef2.journal import format3
from aisef2.orchestrate.workspace import git
from aisef2.product.contract import plain
from aisef2.runtime.capability import CapabilityIdentity
from aisef2.runtime.runspec import resolve


def _runspec_problems(project: Project, rec: dict, events: list[dict]) -> tuple[list[str], settings.Settings | None]:
    """The record's settings, bound to the journal: the RunSpec hash re-derived from the journal's capabilities and the
    record's settings is the hash the journal chained. The settings when they are bound, else why not."""
    spec = next((e["data"] for e in events if e["type"] == "run/spec-resolved"), None)
    if spec is None:
        return [], None     # the run ended before its RunSpec: nothing ran under settings
    try:
        s = settings.load(rec.get("settings") or {})
    except settings.SettingsError as e:
        return [f"the record's settings do not load: {e}"], None
    try:
        caps = [CapabilityIdentity(d["name"], IdentityGrade(d["grade"]), d["binding"], Enforcement(d["enforcement"]))
                for d in (e["data"] for e in events if e["type"] == "capability/resolved")]
        derived = resolve(caps, R.layers_of(project, s), spec["revision"]).runspec_hash
    except (KeyError, TypeError, ValueError) as e:
        return [f"the RunSpec does not re-derive from the journal's capabilities: {type(e).__name__}: {e}"[:300]], None
    if derived != spec["runspec_hash"]:
        return ["the record's settings are not the ones the journal's runspec hash binds (re-derived "
                f"{derived[:12]}, journaled {spec['runspec_hash'][:12]})"], None
    return [], s


def _spend(out: pathlib.Path, s: settings.Settings, events: list[dict], rec: dict) -> tuple[dict, str | None]:
    """What the evidence says was spent (the session streams, the preflight ledger, the journal's provider requests,
    and — V2.1, a continuation — the lineage's, re-derived from the predecessor's evidence as it is now) and whether it
    broke a ceiling or cannot be accounted for — the run's own Budget, re-derived."""
    from aisef2.app import lineage
    base = preflight.accounting(out / "preflight" / "LEDGER.jsonl")
    requests = sum(1 for e in events if e["type"] == "provider/request")
    c = rec.get("continues") or {}
    inherited = lineage.lineage_account(pathlib.Path(c["path"]), out) if c.get("account") else None
    b = client.Budget(s.budget, base, out / "sessions", lambda: requests, inherited)
    return b.spend(), b.exceeded()


def verify(project: Project, out: pathlib.Path, expect_anchor: str | None = None) -> dict:
    problems: list[str] = []
    notes: list[str] = []
    try:
        rec = json.loads((out / "RUN.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:     # no record, or not one: nothing to verify against
        return {"verdict": "REFUTED", "problems": [f"{out / 'RUN.json'}: no readable run record ({type(e).__name__})"]}
    if not isinstance(rec, dict) or rec.get("format") != R.FORMAT:
        return {"verdict": "REFUTED", "problems": [f"RUN.json is not a run record of format {R.FORMAT}"]}
    anchor = None
    try:
        stored = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    except OSError:
        stored = None
        notes.append(f"no {R.MANIFEST}: a run of a release before 2.1 — its record is bound by nothing but itself")
    except ValueError:
        stored = None
        problems.append(f"{R.MANIFEST} is not JSON")
    if stored is not None:
        anchor = R.anchor_of(stored)
        fresh = R.evidence_manifest(out)
        if stored != fresh:
            changed = sorted(k for k in set(stored.get("files", {})) | set(fresh["files"])
                             if stored.get("files", {}).get(k) != fresh["files"].get(k))
            problems.append(f"the evidence manifest does not match the run directory: {changed[:5]}")
    if expect_anchor is not None and anchor != expect_anchor:
        problems.append(f"the evidence anchor is {anchor and anchor[:12]}, not the {expect_anchor[:12]} the run printed")
    elif expect_anchor is not None:     # the match proves integrity against the value given, nothing about its source
        notes.append("the anchor matches the expected value: authentic only as far as that value came from a store the "
                     "developer cannot write (docs/v2.1/ANCHOR-THREAT-MODEL.md); it does not prove the run happened as "
                     "its journal says")
    if rec.get("bundle_digest") != project.digest:
        problems.append("the run is not of this project bundle")
    j = rec.get("journal")
    events: list[dict] = []
    if not j:
        problems.append("the run has no journal (it ended before the run began)")
    else:
        try:
            data = (out / j["path"]).read_bytes()
        except (OSError, KeyError, TypeError) as e:
            data = b""
            problems.append(f"the journal RUN.json names cannot be read ({type(e).__name__})")
        if hashlib.sha256(data).hexdigest() != j.get("sha256") or data.count(b"\n") != j.get("lines"):
            problems.append("the journal is not the one RUN.json names (digest or length)")
        try:
            journal = format3.reconstruct(data.decode("utf-8"))
            events = [{"seq": e.seq, "type": e.type, "data": plain(e.data)} for e in journal.events]
            if journal.torn_tail:
                problems.append("the journal ends in a torn line")
        except Exception as e:  # noqa: BLE001 — any refusal of the reader is the finding
            problems.append(f"the journal does not reconstruct: {type(e).__name__}: {e}"[:500])
    outcomes = R.outcomes_from(events)
    recorded = rec.get("story_outcomes") or {}
    differ = sorted(s for s in outcomes if recorded.get(s) != outcomes[s])
    if differ:
        problems.append(f"the record's story outcomes are not the journal's for {differ}")
    refused = R.unfinished(events)
    bound, s = _runspec_problems(project, rec, events)
    problems += bound
    stop = None
    if s is not None:
        spent, stop = _spend(out, s, events, rec)
        claimed = (rec.get("budget") or {}).get("spent") or {}
        off = [k for k in client.Budget.KEYS if claimed.get(k) != spent[k]]
        if off:
            problems.append(f"the record's spend is not what the evidence re-derives for {off}")
    # what can only lower the verdict is taken from the record too; nothing in it can raise one
    errors = [{"story": x, "error": "begun and never ended in the journal"} for x in refused] + list(rec.get("story_errors") or [])
    verdict, _, committed = R.delivery(project, events, outcomes, stop or rec.get("budget_stop"), errors)
    if rec.get("failure") and verdict == "PASS":
        verdict = "FAIL"
    if rec.get("delivery_verdict") != verdict:
        problems.append(f"the record says {rec.get('delivery_verdict')}; the journal re-derives {verdict}")
    if events and rec.get("productproof") != R.productproof(project, events, committed):
        problems.append("the record's ProductProof account is not the one the journal re-derives")
    if isinstance(rec.get("usage"), dict) and "error" not in rec["usage"]:     # V2.1: the account is the evidence's
        try:
            prices = settings.load(rec.get("settings") or {}).prices
        except settings.SettingsError:
            prices = None
        if rec["usage"] != json.loads(json.dumps(usage.usage(out, events, prices, rec), default=str)) \
                or rec.get("no_progress") != usage.no_progress(events):
            problems.append("the record's usage is not what the evidence re-derives")
    if rec.get("final_main") and (out / "repo").exists():
        if git(out / "repo", "rev-parse", "main").stdout.strip() != rec["final_main"]:
            problems.append("the run's repository main is not the record's final main")
    return {"verdict": "REFUTED" if problems else "VERIFIED", "problems": problems, "delivery_verdict": verdict,
            "journal_events": len(events), "evidence_anchor": anchor, "notes": notes}
