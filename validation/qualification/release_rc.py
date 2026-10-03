"""V2.0 release charter G2 / S4: freeze ONE exact release candidate — its full source SHA, version, kernel tree and
kernel digest, the build epoch, and the wheel and sdist digests of its reproducible build.

    python -P validation/qualification/release_rc.py --freeze RC_SHA --sums SHA256SUMS --ci-run RUN_ID
        # -> closure-evidence/v2/release/V2.0-RC1-FREEZE.json (written once, in the harness-only commit after the RC)
    python -P validation/qualification/release_rc.py --check
        # the record is what the RC's own git objects say (works on any later commit)

SHA256SUMS is the file the staging build of the RC commit wrote (.github/workflows/staging.yml: SOURCE_DATE_EPOCH =
the commit's time, the sdist re-packed by repro_dist.py); S7's rebuild must give the same digests. No source change
after the freeze keeps the RC's qualification (G2): `--check` also says whether HEAD's shipped files still equal it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tomllib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_REL = "closure-evidence/v2/release/V2.0-RC1-FREEZE.json"
VERSION = "2.0.0"
SHIPPED = ("aisef", "aisef2", "pyproject.toml", "MANIFEST.in", "README.md")
_SUM = re.compile(r"([0-9a-f]{64})\s+\*?(\S+)")


def _git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


def kernel_digest_at(sha: str) -> str:
    """aisef2.app.run.kernel_digest, computed from the commit's objects: every .py of aisef2, LF, by relative path."""
    names = sorted(n for n in _git("ls-tree", "-r", "--name-only", sha, "aisef2").decode().splitlines() if n.endswith(".py"))
    h = hashlib.sha256()
    for n in names:
        h.update(n.removeprefix("aisef2/").encode() + b"\0" + _git("show", f"{sha}:{n}").replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def sums(text: str) -> dict[str, str]:
    return {name: digest for digest, name in _SUM.findall(text)}


def freeze(sha: str, sums_text: str, ci_run: str) -> dict:
    full = _git("rev-parse", "--verify", f"{sha}^{{commit}}").decode().strip()
    version = tomllib.loads(_git("show", f"{full}:pyproject.toml").decode())["project"]["version"]
    artifacts = sums(sums_text)
    want = {f"aisef-{version}-py3-none-any.whl", f"aisef-{version}.tar.gz"}
    problems = [] if version == VERSION else [f"the candidate's version is {version}, not {VERSION}"]
    if set(artifacts) != want:
        problems.append(f"SHA256SUMS names {sorted(artifacts)}, not exactly {sorted(want)}")
    return {"record": "AISEF V2.0 — RELEASE CANDIDATE 1, FROZEN (charter G2, S4)",
            "rc": {"sha": full, "version": version, "source_date_epoch": int(_git("log", "-1", "--format=%ct", full).decode()),
                   "shipped_trees": {rel: _git("rev-parse", f"{full}:{rel}").decode().strip() for rel in SHIPPED}},
            "kernel": {"tree": _git("rev-parse", f"{full}:aisef2").decode().strip(), "digest": kernel_digest_at(full)},
            "artifacts": {"source": f"staging build of {full} (CI run {ci_run})", "sha256": artifacts},
            "runspec": "resolved at the release smoke's preregistration (S6) from this kernel digest",
            "rule": "no source change after the freeze keeps this qualification (G2)", "problems": problems,
            "verdict": "FROZEN" if not problems else "PROBLEMS"}


def check(rec: dict) -> list[str]:
    sha = rec["rc"]["sha"]
    out = []
    if kernel_digest_at(sha) != rec["kernel"]["digest"] or _git("rev-parse", f"{sha}:aisef2").decode().strip() != rec["kernel"]["tree"]:
        out.append("the kernel identity is not the RC commit's")
    head = {rel: _git("rev-parse", f"HEAD:{rel}").decode().strip() for rel in SHIPPED}
    moved = sorted(rel for rel, tree in rec["rc"]["shipped_trees"].items() if head.get(rel) != tree)
    if moved:
        out.append(f"HEAD's shipped files are not the RC's: {moved} (a new candidate is needed)")
    return out + rec.get("problems", [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze")
    ap.add_argument("--sums", type=pathlib.Path)
    ap.add_argument("--ci-run")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.freeze:
        if (ROOT / OUT_REL).exists():
            print(f"{OUT_REL} exists: a frozen candidate is never rewritten", file=sys.stderr)
            return 1
        if not (a.sums and a.ci_run):
            ap.error("--freeze needs --sums and --ci-run")
        rec = freeze(a.freeze, a.sums.read_text(encoding="utf-8"), a.ci_run)
        (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{OUT_REL}: {rec['verdict']} {rec['problems']}")
        return 0 if not rec["problems"] else 1
    problems = check(json.loads((ROOT / OUT_REL).read_text(encoding="utf-8")))
    print("release candidate: " + ("PASS" if not problems else "FAIL " + "; ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
