#!/usr/bin/env python3
"""O3 — calibrate `story.verified_touched_weight` on recorded corpora.

ADR-009 "Open" asks for the neighbour weight to be calibrated with **both**
error rates reported: innocent stories blocked, and broken behaviours missed.
This script computes that table from recorded dogfood runs.  No model calls, no
network: every number comes from `_bmad-output/` on disk.

Three inputs per corpus, all recorded:

1. **base score** — `complexity.json`, the row the harness wrote for each story.
   The neighbour weight was 0 during those runs, so the recorded `total` *is*
   the score without the neighbour dimension.
2. **neighbour count** — recomputed with `complexity.verified_touched` against
   the ledger **as of that story's first evidence event**, so the counterfactual
   only uses what the gate could have known.  The ledger is projected from
   evidence with `ledger.build` (the same projection the gate reads), not from
   `ledger.json`: that file is refreshed only at the end of a sprint, which is
   why the recorded rows understate the dimension (see `--counts`).  Evidence is
   append-only across re-runs of the same story; scoring as of the **last**
   `plan->developer` attempt 1 instead of the first gives the same count on all
   32 rows, so the choice of instant does not move the table.
3. **ground truth** — did the story really break a VERIFIED behaviour of
   another story.  Two independent sources, both SHA-bound:
   * the gate's own `preservation` check recorded FAILED in `gate:verdict`;
   * a ledger REOPENED entry **corroborated** by red evidence at the same
     instant — the named criterion red for an `ac`, a criterion of the owning
     story red for `fr`/`nfr`, a red `qa:*` run or a failed `mockup_map`.
   An uncorroborated REOPENED is reported as ARTIFACT and does **not** count as
   a regression: measured on todo-cli STORY-06-01, five requirements flipped to
   REOPENED while the run was 65/65 green, because that story `covers` the same
   requirements as three earlier ones and had one criterion without a test.
   That was a defect in the requirement rollup, fixed 2026-09-14 (bug 155): this
   script is unchanged and now reports **4** uncorroborated entries instead of 29,
   all four one `todo` instant where the runner never started.

Usage:
    python3 validation/o3_preservation_radius.py [--counts] [corpus_dir ...]

A corpus_dir is a project directory containing `_bmad-output/`.  Missing
corpora are reported and skipped — a table of made-up rows is worse than a
small honest one.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aisef.control import complexity                     # noqa: E402
from aisef.control.ledger import build as build_ledger    # noqa: E402

#: Recorded dogfood corpora on the development machine.  Two exclusions, both
#: deliberate: `e9`, the corpus the ADR's pinning note cites (stories 02-03 /
#: 03-03 / 05-01 at 15.0–16.0), is **not** on this machine any more, so those
#: numbers are not reproducible here and are not carried into the table; and
#: `marks-cli` was mid-run while this was measured (92 files written in the
#: preceding two hours), so its rows would not be stable between two runs of
#: this script.  Pass it as an argument once its sprint is finished.
DEFAULT_CORPORA = (
    "~/Downloads/projects/todo-oc",
    "~/Downloads/projects/todo-cli",
    "~/Downloads/projects/todo",
    "~/Downloads/projects/todo-e2e",
)

#: Weights to score.  0 is the current default; 0.5 is the value the ADR says
#: was tried and pinned back to 0; the rest bracket the range where the recorded
#: corpora actually change verdict.
WEIGHTS = (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)


class _Story:
    """Just enough of `normalize.Story` for `verified_touched`."""

    def __init__(self, sid: str, scope: list[str]) -> None:
        self.id, self.write_scope = sid, list(scope)
        self.acceptance_criteria, self.screens, self.depends_on = [], [], []


def _events(root: Path) -> dict[float, list[dict]]:
    """Every evidence event keyed by timestamp — the corroboration lookup."""
    out: dict[float, list[dict]] = collections.defaultdict(list)
    for path in sorted((root / "evidence").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            out[e.get("at")].append(e)
    return out


def _started(root: Path, sid: str) -> float | None:
    """First recorded moment of this story — when its score was computed."""
    path = root / "evidence" / f"{sid}.jsonl"
    if not path.is_file():
        return None
    ats = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            at = json.loads(line).get("at")
        except json.JSONDecodeError:
            continue
        if at:
            ats.append(float(at))
    return min(ats) if ats else None


def _asof(behaviors: dict, when: float) -> dict:
    """Ledger state as of `when`, replayed from each behaviour's history."""
    out: dict[str, dict] = {}
    for bid, rec in behaviors.items():
        status = ""
        for h in rec.get("history") or []:
            if h.get("at") is not None and float(h["at"]) <= when:
                status = str(h.get("status") or "")
        if status:
            out[bid] = {"status": status, "story": str(rec.get("story") or ""),
                        "kind": rec.get("kind"), "regressed_by": rec.get("regressed_by")}
    return {"behaviors": out}


def _gate_failed(root: Path) -> set[str]:
    """Stories whose `preservation` check the gate recorded as FAILED."""
    out: set[str] = set()
    for path in sorted((root / "evidence").glob("STORY-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if '"gate:verdict"' not in line:
                continue
            for ch in (json.loads(line).get("detail") or {}).get("checks") or []:
                if ch.get("name") == "preservation" and ch.get("outcome") == "failed":
                    out.add(path.stem)
    return out


def _corroborated(behaviors: dict, events: dict) -> tuple[set[str], list[str]]:
    """Stories with a REOPENED entry backed by red evidence, plus the artifacts.

    A REOPENED row is only a regression when the same instant carries the red
    that justifies it.  Everything else is bookkeeping.
    """
    real: set[str] = set()
    artifacts: list[str] = []
    for bid, rec in sorted(behaviors.items()):
        kind, owner = str(rec.get("kind") or ""), str(rec.get("story") or "")
        for h in rec.get("history") or []:
            if str(h.get("status")) != "reopened":
                continue
            culprit, at = str(h.get("story") or ""), h.get("at")
            ok = False
            for e in events.get(at, []):
                det = e.get("detail") or {}
                failed = {str(t) for t in det.get("failed_ids") or []}
                if kind == "ac":
                    ok = ok or any(t.startswith(bid) for t in failed)
                elif kind in ("fr", "nfr"):
                    ok = ok or any(f"AC-{owner}-" in t.replace("_", "-") for t in failed)
                elif e.get("kind") in ("tool_run", "mockup_map") and not e.get("ok"):
                    ok = True
            (real.add(culprit) if ok
             else artifacts.append(f"{bid} (owner {owner}) by {culprit}"))
    return real, artifacts


def rows(corpora) -> tuple[list[dict], list[str]]:
    out, notes = [], []
    for raw in corpora:
        project = Path(raw).expanduser()
        root = project / "_bmad-output"
        cal = root / complexity.CALIBRATION_FILE
        if not cal.is_file():
            notes.append(f"{project.name}: no {complexity.CALIBRATION_FILE} — skipped")
            continue
        recorded = json.loads(cal.read_text(encoding="utf-8")).get("stories") or {}
        behaviors = build_ledger(root).as_dict().get("behaviors") or {}
        scopes = complexity.read_scopes(project)
        events = _events(root)
        broke, artifacts = _corroborated(behaviors, events)
        broke |= _gate_failed(root)
        notes.append(f"{project.name}: {len(recorded)} scored stories, "
                     f"{len(behaviors)} behaviours, {len(broke)} confirmed regressors, "
                     f"{len(artifacts)} uncorroborated REOPENED")
        for bid in artifacts:
            notes.append(f"    ARTIFACT {bid}")
        for sid, rec in sorted(recorded.items()):
            began = _started(root, sid)
            led = _asof(behaviors, began) if began else {"behaviors": {}}
            touched = complexity.verified_touched(_Story(sid, scopes.get(sid, [])), led, scopes)
            owners = {str((led["behaviors"].get(b) or {}).get("story") or b) for b in touched}
            out.append({
                "corpus": project.name, "story": sid,
                "base": float(rec.get("total") or 0.0),
                "limit": float(rec.get("threshold") or 16.0),
                "count": len(owners),
                "recorded": int(rec["components"]["verified_touched"]["count"]),
                "broke": sid in broke,
            })
    return out, notes


def _blocking_weight(r: dict) -> float:
    """Smallest weight at which this story's score crosses the threshold."""
    if r["count"] <= 0 or r["base"] > r["limit"]:
        return float("inf")
    return (r["limit"] - r["base"]) / r["count"]


def report(data: list[dict], notes: list[str], *, show_counts: bool) -> str:
    lines = ["# O3 — neighbour weight calibration", ""]
    lines += [f"- {n}" for n in notes] + [""]
    if not data:
        return "\n".join(lines + ["No corpus available — nothing measured."])

    positives = [r for r in data if r["broke"]]
    lines += [
        f"{len(data)} scored stories, {len(positives)} of them confirmed to have "
        f"broken a VERIFIED behaviour of another story.", "",
        "| corpus | story | base | neighbours | recorded | broke a neighbour | blocks above w |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for r in sorted(data, key=_blocking_weight):
        w = _blocking_weight(r)
        lines.append(
            f"| {r['corpus']} | {r['story']} | {r['base']:g} | {r['count']} | "
            f"{r['recorded']} | {'yes' if r['broke'] else 'no'} | "
            f"{'never' if w == float('inf') else format(w, '.2f')} |")

    lines += ["", "| weight | blocked | innocent blocked | regressors caught | "
              "regressions missed |", "|---:|---:|---:|---:|---:|"]
    for w in WEIGHTS:
        blocked = [r for r in data if r["base"] + w * r["count"] > r["limit"]]
        caught = [r for r in blocked if r["broke"]]
        lines.append(f"| {w:g} | {len(blocked)} | {len(blocked) - len(caught)} | "
                     f"{len(caught)} | {len(positives) - len(caught)} |")

    xs = [r["count"] for r in data]
    ys = [1.0 if r["broke"] else 0.0 for r in data]
    rho = complexity.spearman(xs, ys)
    reg = [r["count"] for r in positives]
    clean = [r["count"] for r in data if not r["broke"]]
    lines += [
        "",
        f"Spearman(neighbour count, broke a neighbour) = {rho:.3f} over {len(data)} stories.",
        f"Mean neighbour count: {sum(reg) / len(reg):.2f} for the "
        f"{len(reg)} regressors, {sum(clean) / len(clean):.2f} for the "
        f"{len(clean)} clean stories.",
        f"Regressors whose neighbour count was 0 — unreachable by any weight: "
        f"{sum(1 for r in positives if r['count'] == 0)}/{len(positives)}.",
        # How discriminating the predicate is at all, before any weight: a signal
        # true for most stories cannot rank the subset that regresses.
        f"Touch at least one neighbour: {sum(1 for r in data if r['count'])}/"
        f"{len(data)} stories — {sum(1 for r in positives if r['count'])}/"
        f"{len(positives)} regressors and "
        f"{sum(1 for r in data if r['count'] and not r['broke'])}/{len(clean)} clean.",
    ]
    if show_counts:
        stale = [r for r in data if r["recorded"] != r["count"]]
        lines += ["", f"Stale `ledger.json` at scoring time: {len(stale)}/{len(data)} "
                  "stories were scored against fewer neighbours than the evidence "
                  "projection held; "
                  f"{sum(1 for r in positives if r['recorded'] == 0)}/{len(positives)} "
                  "of the confirmed regressors were scored at 0, where no weight "
                  "can reach them."]
        for r in stale:
            lines.append(f"    {r['corpus']}/{r['story']}: recorded "
                         f"{r['recorded']}, projection {r['count']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    data, notes = rows(args or DEFAULT_CORPORA)
    print(report(data, notes, show_counts="--counts" in argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
