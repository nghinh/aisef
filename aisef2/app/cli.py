"""`aisef run`: the V2 product command.

    aisef run --project BUNDLE --settings SETTINGS --repo REPO --out DIR [--anchor-out FILE] [--parent RUN]
                                                                          run the project's plan on REPO (a new DIR)
    aisef run --check --project BUNDLE --settings SETTINGS --repo REPO      everything before the provider: no request
    aisef run --verify --project BUNDLE --out DIR [--expect-anchor A]     re-derive a finished run from its journal
                                                                          and evidence (A: the anchor the run printed)

Exit status: 0 the delivery verdict is PASS (check: ready; verify: VERIFIED); 1 FAIL or NOT_REACHED (verify: REFUTED);
2 refused before the run began (an input that does not hold, an identity stop) — no session was started."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

from aisef2.app import bundle, lineage, preflight, settings
from aisef2.app import run as R
from aisef2.app.client import SessionRefused
from aisef2.app.verify import verify


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aisef run", description="Run a project's admitted plan under the AISEF V2 kernel.")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="check the inputs and the plan's admission; no provider request")
    mode.add_argument("--verify", action="store_true", help="verify a finished run directory against its journal")
    p.add_argument("--project", required=True, type=pathlib.Path, help="the project bundle (aisef-v2-project/1)")
    p.add_argument("--settings", type=pathlib.Path, help="the run settings (aisef-v2-run/1)")
    p.add_argument("--repo", type=pathlib.Path, help="the project's git repository (cloned; never written)")
    p.add_argument("--out", type=pathlib.Path, help="the run directory (a new one to run; an existing one to verify)")
    p.add_argument("--expect-anchor", metavar="SHA256",
                   help="verify only: the evidence anchor the run printed, kept outside the run directory")
    p.add_argument("--parent", type=pathlib.Path,
                   help="run only: the run this one continues (`aisef bundle continue`), recorded with its anchor")
    p.add_argument("--anchor-out", type=pathlib.Path,
                   help="run only: a new file (never overwritten) the evidence anchor is written to — keep it where the "
                        "developer cannot write (docs/v2.1/ANCHOR-THREAT-MODEL.md)")
    p.add_argument("--accept-unaccounted", action="store_true",
                   help="run --parent only: start although the lineage has spend no evidence accounts for (recorded)")
    p.add_argument("--supersede-claim", metavar="SHA256",
                   help="run --parent only: supersede the predecessor's claim with this sha256 whose child never began "
                        "and whose claimant cannot be shown gone (the operator's assertion, recorded)")
    return p


def _print(doc: dict) -> None:
    print(json.dumps(doc, indent=1, sort_keys=True, default=str))


def run(argv: list[str]) -> int:
    p = _parser()
    a = p.parse_args(argv)
    need = ["out"] if a.verify else ["settings", "repo"] + ([] if a.check else ["out"])
    missing = [f"--{k}" for k in need if getattr(a, k) is None]
    if missing:
        p.error(f"this mode needs {' '.join(missing)}")
    if a.expect_anchor is not None and not a.verify:
        p.error("--expect-anchor is given to --verify")
    if a.anchor_out is not None and (a.verify or a.check or os.path.lexists(a.anchor_out)):
        p.error("--anchor-out names a new file (not a link, not an existing path), for a run")
    if (a.accept_unaccounted or a.supersede_claim) and a.parent is None:
        p.error("--accept-unaccounted and --supersede-claim are given with --parent")
    if a.expect_anchor is not None and not re.fullmatch(r"[0-9a-f]{64}", a.expect_anchor):
        p.error("--expect-anchor is the 64-hex evidence anchor the run printed")
    try:
        project = bundle.read(a.project)
        if a.verify:
            v = verify(project, a.out, **({"expect_anchor": a.expect_anchor} if a.expect_anchor is not None else {}))
            _print(v)
            return 0 if v["verdict"] == "VERIFIED" else 1
        s = settings.read(a.settings)
        if a.check:
            R.check_git()
            R.check_repository(project, a.repo)
            adm = R.admit(project, R.calibrations())
            _print({"project": project.name, "plan_hash": project.plan.plan_hash, "route": s.route, "admission": adm,
                    "ready": adm["admitted"]})
            return 0 if adm["admitted"] else 2
        rec = R.execute(project, s, a.repo, a.out, **({"predecessor": a.parent, "accept_unaccounted": a.accept_unaccounted,
                                                         "supersede_claim": a.supersede_claim} if a.parent is not None else {}))
    except (bundle.BundleError, settings.SettingsError, R.RunRefused, preflight.IdentityStop, SessionRefused) as e:
        print(f"aisef run: refused: {e}", file=sys.stderr)
        return 2
    anchor = R.anchor_in(a.out)     # V2.1: keep it outside the run directory; `--verify --expect-anchor` checks it
    wrote = None
    if anchor and a.anchor_out is not None:
        try:
            lineage.write_anchor(a.anchor_out, anchor)
            wrote = str(a.anchor_out)
        except (OSError, ValueError) as e:      # the run is done and its evidence intact: only the copy failed
            print(f"aisef run: the anchor was NOT written to {a.anchor_out} ({type(e).__name__}: {e}); keep the printed "
                  "one", file=sys.stderr)
    _print({k: rec.get(k) for k in ("project", "delivery_verdict", "delivery_blocked_by", "story_outcomes", "final_main",
                                     "journal", "plan_quality_verdict")} | {"record": str(a.out / "RUN.json")}
           | ({"evidence_anchor": anchor} if anchor else {}) | ({"anchor_written_to": wrote} if wrote else {}))
    if a.anchor_out is not None and wrote is None:
        return 2
    return 0 if rec["delivery_verdict"] == "PASS" else 1


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
