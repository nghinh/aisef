"""B2 labels: schema, derived verdict, commit-then-reveal, agreement (B2 protocol §3, 2026-11-25 draft).

§3.1 — per (story, criterion) of the frozen bundle a label MUST assert `scope` ("is this criterion part of the
approved contract?"), `verdict` ("is the candidate's behaviour as asserted?"), `severity` ("required iff
VIOLATED") and `basis` ("the command/check the labeler ran and what it showed"). The item's "expected delivery
verdict is derived mechanically, never hand-assigned: FAIL iff ≥1 IN_SCOPE criterion is VIOLATED, else PASS.
(OUT_OF_SCOPE violations do not change it — §2.2.)"

§3.3 — "Each evaluator commits the sha256 of their finished labelset before any labelset is exchanged
(hash-commit, then reveal); both hashes go into the oracle manifest." Here the commitment is the sha256 of the
canonical labelset bytes + the evaluator's salt, so the reveal reproduces it or fails by name.

§3.4 — "Two labels agree when `scope` and `verdict` match; a severity differing by one class is recorded and the
more severe stands (default, Q10). Any other difference is a disagreement" that "goes to a recorded adjudication
session". "The raw inter-evaluator agreement rate (per field, before adjudication) MUST be reported."
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23.ground_truth import canonical, hex_problems  # noqa: E402

SCOPES = ("IN_SCOPE", "OUT_OF_SCOPE")
VERDICTS = ("SATISFIED", "VIOLATED")
#: §2.4 severity rubric, most severe first: P0 data loss/security/crash on a contracted path, P1 functionally
#: wrong, P2 degraded but partially holding, P3 cosmetic within scope
SEVERITIES = ("P0", "P1", "P2", "P3")


def label_problems(label: Any) -> list[str]:
    """Fail-closed §3.1 schema check for one label; a malformed label returns named problems, never crashes."""
    if not isinstance(label, dict):
        return [f"label is not an object: {type(label).__name__}"]
    out = []
    for key in ("story", "criterion"):
        if not isinstance(label.get(key), str) or not label.get(key):
            out.append(f"{key} must be a non-empty string: {label.get(key)!r}")
    if label.get("scope") not in SCOPES:
        out.append(f"scope {label.get('scope')!r} not in {SCOPES}")
    if label.get("verdict") not in VERDICTS:
        out.append(f"verdict {label.get('verdict')!r} not in {VERDICTS}")
    severity = label.get("severity")
    if label.get("verdict") == "VIOLATED" and severity not in SEVERITIES:
        out.append(f"severity is required iff VIOLATED and must be one of {SEVERITIES} (§3.1): {severity!r}")
    if label.get("verdict") == "SATISFIED" and severity is not None:
        out.append(f"severity is required iff VIOLATED — a SATISFIED label carries null (§3.1): {severity!r}")
    if not isinstance(label.get("basis"), str) or not label.get("basis").strip():
        out.append(f"basis must be a non-empty string — the command/check the labeler ran (§3.1): {label.get('basis')!r}")
    return out


def labelset_problems(labelset: Any) -> list[str]:
    """One labelset per corpus item (§3.1): a non-empty list of valid labels, one per (story, criterion)."""
    if not isinstance(labelset, list):
        return [f"labelset is not a list: {type(labelset).__name__}"]
    if not labelset:
        return ["labelset is empty: a labelset covers every (story, criterion) of the frozen bundle (§3.1)"]
    out, seen = [], set()
    for n, label in enumerate(labelset):
        out += [f"label #{n}: {p}" for p in label_problems(label)]
        if isinstance(label, dict):
            key = (label.get("story"), label.get("criterion"))
            if key in seen:
                out.append(f"label #{n}: duplicate (story, criterion) {key!r}")
            seen.add(key)
    return out


def _valid(labelset: Any) -> list[dict]:
    bad = labelset_problems(labelset)
    if bad:
        raise ValueError("not a valid labelset: " + "; ".join(bad))
    return labelset


def derived_verdict(labelset: list[dict]) -> str:
    """§3.1: '`FAIL` iff ≥1 `IN_SCOPE` criterion is `VIOLATED`, else `PASS`' — OUT_OF_SCOPE violations never
    change it (§2.2). Derived mechanically, never hand-assigned; refuses an invalid labelset (fail closed)."""
    violated = any(x["scope"] == "IN_SCOPE" and x["verdict"] == "VIOLATED" for x in _valid(labelset))
    return "FAIL" if violated else "PASS"


def most_severe_violated_in_scope(labelset: list[dict]) -> str | None:
    """§4.2: the false-accept severity class is 'the most severe violated in-scope criterion' (P0 most severe)."""
    ranks = [SEVERITIES.index(x["severity"]) for x in _valid(labelset)
             if x["scope"] == "IN_SCOPE" and x["verdict"] == "VIOLATED"]
    return SEVERITIES[min(ranks)] if ranks else None


# --------------------------------------------------------------------------------------- §3.3 commit-then-reveal

def canonical_labelset(labelset: list[dict]) -> str:
    """The labelset's canonical bytes: labels in (story, criterion) order, canonical JSON — the commitment is
    therefore independent of the order the evaluator wrote the labels in."""
    return canonical(sorted(_valid(labelset), key=lambda x: (x["story"], x["criterion"])))


def commitment(labelset: list[dict], salt: bytes) -> str:
    """§3.3 hash-commit: sha256 over the canonical labelset bytes + the evaluator's salt, hex. Committed before
    any labelset is exchanged; both evaluators' hashes go into the oracle manifest."""
    if not isinstance(salt, bytes):
        raise ValueError(f"salt must be bytes: {type(salt).__name__}")
    return hashlib.sha256(canonical_labelset(labelset).encode("utf-8") + salt).hexdigest()


def reveal_problems(labelset: Any, salt: Any, committed: Any) -> list[str]:
    """§3.3/§3.5 reveal: [] iff the revealed labelset + salt reproduce the committed hash. A mismatch is a named
    problem for the record, never an exception — and a signed label is only ever corrected by an appended,
    dated erratum (§3.5), never by editing."""
    out = hex_problems("commitment", committed, 64)
    if not isinstance(salt, bytes):
        out.append(f"salt is not bytes: {type(salt).__name__}")
    out += labelset_problems(labelset)
    if out:
        return out
    got = commitment(labelset, salt)
    return [] if got == committed else \
        [f"commitment mismatch: the revealed labelset hashes to {got}, the commitment was {committed}"]


# --------------------------------------------------------------------------------------- §3.4 agreement

def agreement(a: list[dict], b: list[dict]) -> dict:
    """§3.4 between two labelsets, per (story, criterion): agree when scope and verdict match; where both are
    VIOLATED, a severity differing by one class is recorded in `severity_resolutions` and 'the more severe
    stands' (Q10) — still an agreement; any other difference (a larger severity gap, a scope or verdict
    mismatch, a criterion one labelset lacks) joins `disagreements` for the recorded adjudication session.
    `rate` is the raw inter-evaluator agreement rate before adjudication. Deterministically ordered."""
    am = {(x["story"], x["criterion"]): x for x in _valid(a)}
    bm = {(x["story"], x["criterion"]): x for x in _valid(b)}
    agreed, resolutions, disagreements = 0, [], []
    for story, criterion in sorted(set(am) | set(bm)):
        la, lb = am.get((story, criterion)), bm.get((story, criterion))
        if la is None or lb is None:
            disagreements.append({"story": story, "criterion": criterion, "field": "missing",
                                  "a": la, "b": lb})
            continue
        fields = [f for f in ("scope", "verdict") if la[f] != lb[f]]
        if fields:
            disagreements.append({"story": story, "criterion": criterion, "field": "+".join(fields),
                                  "a": {f: la[f] for f in fields}, "b": {f: lb[f] for f in fields}})
            continue
        if la["verdict"] == "VIOLATED" and la["severity"] != lb["severity"]:
            ra, rb = SEVERITIES.index(la["severity"]), SEVERITIES.index(lb["severity"])
            if abs(ra - rb) == 1:
                resolutions.append({"story": story, "criterion": criterion, "a": la["severity"],
                                    "b": lb["severity"], "stands": SEVERITIES[min(ra, rb)]})
                agreed += 1
            else:
                disagreements.append({"story": story, "criterion": criterion, "field": "severity",
                                      "a": la["severity"], "b": lb["severity"]})
            continue
        agreed += 1
    total = len(set(am) | set(bm))
    return {"compared": total, "agreed": agreed, "rate": agreed / total if total else None,
            "severity_resolutions": resolutions, "disagreements": disagreements}
