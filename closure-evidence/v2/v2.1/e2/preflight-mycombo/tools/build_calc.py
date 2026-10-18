"""Build the canary's stock calc project in scratch, exactly as docs/v2.1/USAGE-2.1.md §1 documents it:
init -> git init/add/commit (the baseline) -> seal -> approve BC-ADD (a technical approval of a stock example, by the
lane, NOT an owner acceptance) -> lint.  Usage: python3 -P -B build_calc.py OUTDIR"""
import pathlib
import subprocess
import sys

from aisef2.app import bundle_cli

out = pathlib.Path(sys.argv[1]).resolve()
calc = out / "calc"
rc = bundle_cli.main(["init", "--example", "calc-1-story", "--out", str(calc)])
assert rc == 0, rc
repo = calc / "repo"
for args in (["init", "-q", "-b", "main"], ["add", "-A"],
             ["-c", "user.name=lane-pf", "-c", "user.email=lane-pf@aisef", "commit", "-q", "-m", "baseline"]):
    subprocess.run(["git", "-C", str(repo), *args], check=True)
assert bundle_cli.main(["seal", str(calc / "authoring.json"), "--repo", str(repo), "--out", str(calc / "bundle.json")]) == 0
assert bundle_cli.main(["approve", str(calc / "bundle.json"), "--contract", "BC-ADD", "--approver", "human:lane-pf-operator",
                        "--out", str(calc / "approved.json")]) == 0
print("lint exit:", bundle_cli.main(["lint", str(calc / "approved.json")]))
