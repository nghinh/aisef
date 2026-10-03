"""`aisef run`: the V2 product command.

    aisef run --project BUNDLE --settings SETTINGS --repo REPO --out DIR    run the project's plan on REPO (a new DIR)
    aisef run --check --project BUNDLE --settings SETTINGS --repo REPO      everything before the provider: no request
    aisef run --verify --project BUNDLE --out DIR                          re-derive a finished run from its journal

Exit status: 0 the delivery verdict is PASS (check: ready; verify: VERIFIED); 1 FAIL or NOT_REACHED (verify: REFUTED);
2 refused before the run began (an input that does not hold, an identity stop) — no session was started."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from aisef2.app import bundle, preflight, settings
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
    p.add_argument("--out", type=pathlib.Path, help="the run directory (must not exist)")
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
    try:
        project = bundle.read(a.project)
        if a.verify:
            v = verify(project, a.out)
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
        rec = R.execute(project, s, a.repo, a.out)
    except (bundle.BundleError, settings.SettingsError, R.RunRefused, preflight.IdentityStop, SessionRefused) as e:
        print(f"aisef run: refused: {e}", file=sys.stderr)
        return 2
    _print({k: rec.get(k) for k in ("project", "delivery_verdict", "delivery_blocked_by", "story_outcomes", "final_main",
                                     "journal", "plan_quality_verdict")} | {"record": str(a.out / "RUN.json")})
    return 0 if rec["delivery_verdict"] == "PASS" else 1


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
