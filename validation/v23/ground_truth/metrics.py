"""B2 metrics: §4.2 classification and aggregates, §4.3 NO-GO (B2 protocol, 2026-11-25 draft).

§4.2 — per item, `predicted` = the `delivery()` verdict, `expected` = the verdict derived from the labelset
(§3.1). "false-accept (false PASS): predicted PASS, expected FAIL — reported per severity class of the most
severe violated in-scope criterion"; "false-reject (false FAIL): predicted FAIL (or blocked/refused), expected
PASS"; TA/TR the agreeing cells; "INDETERMINATE: NOT_REACHED or a run refusal: counted as neither PASS nor FAIL,
reported in its own class; if > 20 % of a workload's items are INDETERMINATE the workload's measurement is
invalid" (Q5). Recall per severity class = "detected in-scope defective items / all in-scope defective items of
that class"; precision = "true FAILs / all FAILs"; the "out-of-scope escape rate" is "reported separately as
by-design scope behaviour, never summed into false-accepts" (§2.2). All aggregates are reported "per tier, per
repo, and pooled over Tier-1 only".

§4.3 — "Any P0 or P1 false-PASS on any tier ⇒ NO-GO. One owner decision, no loop." P2/P3 false-accepts,
false-rejects and escape rates carry no pre-committed threshold (Q11): reported, never gating silently.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23.ground_truth import corpus, labels  # noqa: E402

#: §4.4 B2-MEASURE per-item `class` values
CLASSES = ("TA", "TR", "FP", "FN", "INDETERMINATE")
#: the delivery() verdict domain (aisef2/app/run.py delivery(): PASS / FAIL / NOT_REACHED)
PREDICTED = ("PASS", "FAIL", "NOT_REACHED")


def classify(predicted: str, expected: str, *, refusal: bool = False) -> str:
    """§4.2 per-item class. INDETERMINATE = "NOT_REACHED or a run refusal" (Q5: its own class, neither PASS nor
    FAIL); a `blocked` delivery is already a FAIL verdict (B-M1), so "predicted FAIL (or blocked/refused)" with
    expected PASS is the false-reject cell; `refusal` is a run-level refusal (no verdict at all)."""
    if expected not in ("PASS", "FAIL"):
        raise ValueError(f"expected must be a derived verdict PASS or FAIL (§3.1): {expected!r}")
    if predicted not in PREDICTED:
        raise ValueError(f"predicted is not a delivery() verdict {PREDICTED}: {predicted!r}")
    if refusal or predicted == "NOT_REACHED":
        return "INDETERMINATE"
    if predicted == expected:
        return "TA" if expected == "PASS" else "TR"
    return "FP" if predicted == "PASS" else "FN"


def item_record(item_id: str, *, tier: str, repo: str, item_class: str, predicted: str, refusal: bool = False,
                blocked: tuple | list = (), severity: str | None = None, cost: dict | None = None) -> dict:
    """One §4.4 B2-MEASURE per-item row: `item_id`, `predicted`, `blocked[]`, `expected`, `class`, `severity`,
    `cost` (wallclock/tokens/USD, real or clearly estimated — recorded by the caller, never read from a clock
    here). `expected` is fixed by the §2.2 corpus class, never passed in; `severity` is
    labels.most_severe_violated_in_scope(...) and is required exactly for expected-FAIL items (§4.2
    false-accepts are reported per severity class)."""
    if item_class not in corpus.CLASSES:
        raise ValueError(f"item_class not in {corpus.CLASSES}: {item_class!r}")
    if tier not in corpus.TIERS:
        raise ValueError(f"tier not in {corpus.TIERS}: {tier!r}")
    if not isinstance(repo, str) or not repo:
        raise ValueError(f"repo must be a non-empty string: {repo!r}")
    expected = corpus.EXPECTED_DELIVERY[item_class]
    if expected == "FAIL" and severity not in labels.SEVERITIES:
        raise ValueError(f"an expected-FAIL item carries the most severe violated in-scope class (§4.2): {severity!r}")
    if expected == "PASS" and severity is not None:
        raise ValueError(f"an expected-PASS item has no violated in-scope criterion to grade: {severity!r}")
    return {"item_id": item_id, "tier": tier, "repo": repo, "item_class": item_class,
            "predicted": predicted, "blocked": list(blocked), "expected": expected,
            "class": classify(predicted, expected, refusal=refusal), "severity": severity, "cost": cost}


def _agg(records: list[dict], *, workload: bool = False) -> dict:
    counts = {c: sum(1 for r in records if r["class"] == c) for c in CLASSES}
    recall = {}
    for s in labels.SEVERITIES:
        defective = [r for r in records if r["expected"] == "FAIL" and r["severity"] == s]
        # §4.2 taken literally: the denominator is ALL in-scope defective items of the class, so an
        # INDETERMINATE defective item counts as undetected (conservative); Q5 still reports it in its own class
        recall[s] = sum(1 for r in defective if r["class"] == "TR") / len(defective) if defective else None
    fails = counts["TR"] + counts["FN"]
    oos = [r for r in records if r["item_class"] == "OUT_OF_SCOPE_DEFECT"]
    escapes = sum(1 for r in oos if r["predicted"] == "PASS")
    n = len(records)
    out = {"items": n, "counts": counts,
           "false_accepts_by_severity": {s: sum(1 for r in records if r["class"] == "FP" and r["severity"] == s)
                                         for s in labels.SEVERITIES},
           "recall_by_severity": recall,
           "precision": counts["TR"] / fails if fails else None,
           "out_of_scope_escapes": escapes,
           "out_of_scope_escape_rate": escapes / len(oos) if oos else None,
           "indeterminate_rate": counts["INDETERMINATE"] / n if n else 0.0}
    if workload:
        # Q5: "> 20 %" invalidates — exactly 20 % is still valid; integer arithmetic, no float boundary
        out["measurement_valid"] = counts["INDETERMINATE"] * 5 <= n
    return out


def aggregate(records: list[dict]) -> dict:
    """§4.2 aggregates "per tier, per repo, and pooled over Tier-1 only" plus the §4.3 NO-GO flag ("any P0 or P1
    false-PASS on ANY tier"). Per-repo aggregates carry the Q5 workload validity — the workload of §4.1 is
    (repo, bundle), and Tier-0 runs one bundle per repo, so the repo keys the workload here."""
    # ponytail: workload keyed by repo; key by (repo, bundle) when a repo ever carries two bundles
    for r in records:
        if not isinstance(r, dict) or r.get("class") not in CLASSES or r.get("tier") not in corpus.TIERS \
                or r.get("item_class") not in corpus.CLASSES:
            raise ValueError(f"not a measured item record (build it with item_record): {r!r}")
    no_go_basis = sorted(r["item_id"] for r in records if r["class"] == "FP" and r["severity"] in ("P0", "P1"))
    return {"per_tier": {t: _agg([r for r in records if r["tier"] == t])
                         for t in sorted({r["tier"] for r in records})},
            "per_repo": {p: _agg([r for r in records if r["repo"] == p], workload=True)
                         for p in sorted({r["repo"] for r in records})},
            "pooled_tier1": _agg([r for r in records if r["tier"] == "external"]),
            "no_go": bool(no_go_basis), "no_go_basis": no_go_basis}
