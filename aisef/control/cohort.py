"""Cohort identity and classification integrity for benchmark evidence (G5.2).

Why this module exists, stated as the failure it prevents rather than as a
feature: C-1b graded three cut sessions as ordinary failures and produced a
+0,06 that was an artifact. The lesson is not "every row ever written must
carry `exit_status`" — that demand is unsatisfiable for rows produced before
the field existed, and satisfying it would mean guessing. The lesson is that
**the evidence supporting a current claim must be able to show that no cut or
infra session was silently graded**.

So the unit of evaluation is a *cohort*, declared before it is scored and
immutable afterwards:

* ``CURRENT`` — backs a claim being made now. Every integrity check below
  applies, and failing any of them fails G5.2. No waiver.
* ``HISTORICAL_UNCLASSIFIABLE`` — predates the classification schema. Its raw
  evidence is preserved byte for byte and never rewritten, its limitation is
  recorded, and it backs no current claim. Its old schema is **not** a defect
  in the present gate.

This is a semantic correction, not a relaxation: a ``CURRENT`` cohort must now
reconcile attempts, sessions, retries and report totals exactly, which is
strictly more than "every row has a non-empty field".

Read-only. Pure stdlib. No git, no subprocess, no network.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

#: Where cohort declarations live. One file per cohort, named by its id.
COHORT_DIR = "closure-evidence/cohorts"

CURRENT = "CURRENT"
HISTORICAL = "HISTORICAL_UNCLASSIFIABLE"

#: A session that ended in one of these did not produce a gradeable attempt.
#: Kept as a literal rather than imported from `clients.stream` so a cohort
#: frozen today still reads the same way if that tuple later grows: the cohort
#: records which vocabulary it was scored under.
DEFAULT_INFRA_STATUSES = ("timeout", "infra", "rate_limit")

#: Identity a CURRENT cohort must carry. Absent or empty -> the cohort cannot
#: be said to be the thing that was pre-registered, so nothing downstream of it
#: can be trusted either.
IDENTITY = (
    "cohort_id",
    "protocol_digest",
    "protocol_path",
    "benchmark_execution_sha",
    "manifest_sha256",
    "scoring_version",
    "report",
)


@dataclass
class Reconciliation:
    """Everything G5.2 asks about one cohort, and what it measured."""

    cohort_id: str
    status: str
    problems: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def totals_digest(totals: dict) -> str:
    """Digest of the declared totals, stable under key order.

    The report carries this value. Changing any total — dropping a failing
    row, rounding a rate — changes the digest, so a report and the rows it
    claims to summarise cannot drift apart silently.
    """
    return sha256_text(json.dumps(totals, sort_keys=True, separators=(",", ":")))


def declarations(root: Path) -> list[dict]:
    """Every cohort declaration in the tree, ordered by id."""
    out = []
    for p in sorted((root / COHORT_DIR).glob("*.json")):
        if p.name.endswith("-sessions.json") or p.name.endswith("-attempts.jsonl"):
            continue
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as e:
            out.append({"cohort_id": p.stem, "_unreadable": str(e)})
    return out


def _rows(root: Path, rel: str) -> list[dict] | None:
    try:
        text = (root / rel).read_text(encoding="utf-8")
    except OSError:
        return None
    rows = []
    for line in text.splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                return None
    return rows


def _pinned(root: Path, spec: dict, what: str, problems: list[str]) -> str | None:
    """Read a file the cohort pinned by digest. A digest mismatch is the
    anti-cherry-pick check: the rows scored are the rows declared."""
    rel = str(spec.get("path") or "")
    if not rel:
        problems.append(f"{what}: no path declared")
        return None
    try:
        text = (root / rel).read_text(encoding="utf-8")
    except OSError:
        problems.append(f"{what}: {rel} unreadable")
        return None
    want = str(spec.get("sha256") or "")
    got = sha256_text(text)
    if not want:
        problems.append(f"{what}: {rel} carries no declared sha256 — the cohort "
                        f"could be re-selected after scoring")
    elif want != got:
        problems.append(f"{what}: {rel} is {got[:12]} but the cohort declares "
                        f"{want[:12]} — the evidence changed after it was frozen")
    return text


def verify_historical(decl: dict) -> Reconciliation:
    """A historical cohort owes three things, and none of them is a schema."""
    r = Reconciliation(str(decl.get("cohort_id") or "?"), HISTORICAL)
    if not str(decl.get("limitation") or "").strip():
        r.problems.append("no `limitation` recorded — an unclassifiable cohort "
                          "must say what cannot be concluded from it")
    if decl.get("report"):
        r.problems.append(f"declares report {decl['report']!r}: a cohort kept as "
                          f"{HISTORICAL} may not back a current claim")
    if not str(decl.get("raw_sha256") or "").strip():
        r.problems.append("no `raw_sha256` — historical evidence must be pinned "
                          "so 'unchanged' is checkable rather than asserted")
    return r


def verify_current(root: Path, decl: dict) -> Reconciliation:
    """Every question G5.2 asks of the cohort backing a current claim."""
    r = Reconciliation(str(decl.get("cohort_id") or "?"), CURRENT)
    p = r.problems

    for k in IDENTITY:
        if not str(decl.get(k) or "").strip():
            p.append(f"identity field {k!r} is missing or empty")

    attempts_text = _pinned(root, decl.get("attempts") or {}, "attempts", p)
    sessions_text = _pinned(root, decl.get("sessions") or {}, "sessions", p)
    if attempts_text is None or sessions_text is None:
        return r

    rows = _rows(root, str((decl.get("attempts") or {}).get("path")))
    if rows is None:
        p.append("attempts file is not valid JSONL")
        return r
    try:
        ledger = json.loads(sessions_text)
        sessions = list(ledger.get("sessions") or [])
    except (json.JSONDecodeError, AttributeError):
        p.append("session ledger is not valid JSON")
        return r

    infra = tuple(decl.get("infra_statuses") or DEFAULT_INFRA_STATUSES)
    declared = decl.get("attempts") or {}
    if declared.get("count") is not None and int(declared["count"]) != len(rows):
        p.append(f"declares {declared['count']} attempts, file holds {len(rows)} — "
                 f"rows were added or removed after the cohort was declared")

    # -- every graded attempt is traceable, and carries a classification ------
    key = lambda d: (d.get("client"), d.get("task_id"), d.get("attempt"))   # noqa: E731
    blank = [key(x) for x in rows if not str(x.get("exit_status") or "")]
    if blank:
        p.append(f"{len(blank)} attempt(s) carry no exit_status, e.g. {blank[0]} — "
                 f"a cut session cannot be told apart from a graded one")

    by_attempt: dict[tuple, list[dict]] = {}
    for s in sessions:
        by_attempt.setdefault((s.get("client"), s.get("task_id"), s.get("attempt")), []).append(s)

    attempts = {key(x) for x in rows}
    orphan = sorted(k for k in by_attempt if k not in attempts)
    if orphan:
        p.append(f"{len(orphan)} session group(s) belong to no declared attempt, "
                 f"e.g. {orphan[0]} — the ledger reaches outside the cohort")
    unsessioned = sorted(k for k in attempts if k not in by_attempt)
    if unsessioned:
        p.append(f"{len(unsessioned)} attempt(s) have no session recorded, e.g. "
                 f"{unsessioned[0]} — a graded outcome with no traceable session")

    no_status = [s for s in sessions if not str(s.get("status") or "")]
    if no_status:
        p.append(f"{len(no_status)} session(s) carry no status")

    # -- cut/infra sessions were treated the way the frozen protocol says -----
    mis = []
    for k, group in by_attempt.items():
        row = next((x for x in rows if key(x) == k), None)
        if row is None:
            continue
        if group and str(group[-1].get("status") or "") == "cut" \
                and str(row.get("exit_status") or "") not in infra:
            mis.append(k)
    if mis:
        p.append(f"{len(mis)} attempt(s) whose final session was cut are graded "
                 f"with a non-infra exit_status, e.g. {mis[0]} — this is exactly "
                 f"the C-1b artifact: a cut session scored as a result")

    # -- retries are traceable: one session per run, plus one per retry ------
    drift = [k for k, g in by_attempt.items()
             if (row := next((x for x in rows if key(x) == k), None)) is not None
             and len(g) != int(row.get("infra_retries") or 0) + 1]
    if drift:
        p.append(f"{len(drift)} attempt(s) where sessions != infra_retries + 1, "
                 f"e.g. {drift[0]} — a run happened that no retry counter explains")

    # -- nothing was dropped without saying so --------------------------------
    for ex in decl.get("excluded") or []:
        if not str(ex.get("reason") or "").strip():
            p.append(f"excluded row {ex.get('row')!r} carries no reason")

    # -- the report summarises these rows, and says so ------------------------
    totals = decl.get("totals") or {}
    recomputed = compute_totals(rows, sessions, infra)
    for k, v in sorted(recomputed.items()):
        if k in totals and totals[k] != v:
            p.append(f"totals.{k} declared {totals[k]!r} but the rows give {v!r}")
    missing_totals = sorted(set(recomputed) - set(totals))
    if missing_totals:
        p.append(f"totals omit {', '.join(missing_totals)} — a total that is not "
                 f"declared cannot be reconciled")

    want = totals_digest(totals)
    report_rel = str(decl.get("report") or "")
    report = None
    if report_rel:
        try:
            report = (root / report_rel).read_text(encoding="utf-8")
        except OSError:
            p.append(f"report {report_rel} unreadable")
    if report is not None:
        if r.cohort_id not in report:
            p.append(f"report {report_rel} never names cohort {r.cohort_id}")
        if want not in report:
            p.append(f"report {report_rel} does not carry totals digest "
                     f"{want[:12]} — its numbers are not bound to these rows")

    # -- data collected after a frozen stop rule fired is labelled as such ---
    conf = decl.get("confirmatory") or {}
    if conf:
        a, b = int(conf.get("confirmatory_attempts") or 0), int(conf.get("post_stop_attempts") or 0)
        if a + b != len(rows):
            p.append(f"confirmatory {a} + post-stop {b} != {len(rows)} attempts — "
                     f"the two layers do not account for the cohort")
        label = str(conf.get("post_stop_label") or "")
        if b and not label:
            p.append("post-stop data exists but declares no label")
        elif label and report is not None and label not in report:
            p.append(f"report {report_rel} does not carry the post-stop label "
                     f"{label[:40]!r} — data gathered after the stop rule fired "
                     f"reads as though the protocol required it")

    r.facts = {"attempts": len(rows), "sessions": len(sessions),
               "totals_sha256": want, **recomputed}
    return r


def compute_totals(rows: list[dict], sessions: list[dict],
                   infra: tuple[str, ...] = DEFAULT_INFRA_STATUSES) -> dict:
    """The numbers a report may state, recomputed from raw rows.

    Recomputed rather than read, so a report cannot quietly drop a failing row:
    `pass@1` is over **declared** attempts, and the declared attempt count is
    itself pinned by digest.
    """
    out: dict = {}
    arms = sorted({str(x.get("client") or "") for x in rows})
    for arm in arms:
        rs = [x for x in rows if x.get("client") == arm]
        ss = [s for s in sessions if s.get("client") == arm]
        n = len(rs)
        tasks = sorted({str(x.get("task_id")) for x in rs})
        solved = sum(1 for t in tasks
                     if any(x.get("outcome") == "PASS" for x in rs if x.get("task_id") == t))
        out[f"{arm}.attempts"] = n
        out[f"{arm}.pass"] = sum(1 for x in rs if x.get("outcome") == "PASS")
        out[f"{arm}.infra_attempts"] = sum(
            1 for x in rs if str(x.get("exit_status") or "") in infra)
        out[f"{arm}.retries"] = sum(int(x.get("infra_retries") or 0) for x in rs)
        out[f"{arm}.sessions"] = len(ss)
        out[f"{arm}.sessions_cut"] = sum(1 for s in ss if s.get("status") == "cut")
        out[f"{arm}.tasks"] = len(tasks)
        out[f"{arm}.tasks_solved"] = solved
    return out


def verify(root: Path, decl: dict) -> Reconciliation:
    status = str(decl.get("status") or "")
    if decl.get("_unreadable"):
        r = Reconciliation(str(decl.get("cohort_id") or "?"), status or "?")
        r.problems.append(f"declaration unreadable: {decl['_unreadable']}")
        return r
    if status == CURRENT:
        return verify_current(root, decl)
    if status == HISTORICAL:
        return verify_historical(decl)
    r = Reconciliation(str(decl.get("cohort_id") or "?"), status or "(none)")
    r.problems.append(f"status {status!r} is neither {CURRENT} nor {HISTORICAL}")
    return r
