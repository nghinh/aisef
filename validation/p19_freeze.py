"""Phase 19 — freeze the exact hardened candidate (owner item 8: after W0, before W1). Records the candidate SHA, the
`aisef/` tree digest (must equal PHASE12_KERNEL_DIGEST), the wheel built from that SHA and its sha256, the run venv
created from that wheel (never the checkout), the oracle venv, the sandbox image id, the OpenCode version, the CI run
and the W0 record. No tag, no publish: the wheel stays outside git in a persistent local directory; its digest is the
record.

    python3 validation/p19_freeze.py --ci-run <id> --w0 closure-evidence/hardening/AISEF-W0-QUALIFICATION.json \
        --build-python <build venv python> --dest ~/Downloads/projects/aisef-freeze
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "closure-evidence/hardening/P19-FREEZE.json"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def git(*a: str) -> str:
    return run(["git", "-C", str(ROOT), *a]).stdout.strip()


def _aisef_tree_of(w0: dict | None) -> str:
    """The W0 record qualifies a product tree, not a commit message: a later evidence commit keeps the tree."""
    return git("rev-parse", f"{((w0 or {}).get('sha') or (w0 or {}).get('candidate_sha') or '')}:aisef") if w0 else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci-run", required=True)
    ap.add_argument("--w0", default=str(ROOT / "closure-evidence/hardening/AISEF-W0-QUALIFICATION.json"))
    ap.add_argument("--build-python", required=True)
    ap.add_argument("--dest", default=str(Path.home() / "Downloads/projects/aisef-freeze"))
    ap.add_argument("--oracle-pins", default="coverage==7.16.1 pytest==9.1.1")
    ap.add_argument("--out", default=str(OUT), help="rehearsals write elsewhere; the real record is closure-evidence/hardening/P19-FREEZE.json")
    a = ap.parse_args()
    if git("status", "--porcelain", "--", "aisef", "tests", "pyproject.toml", "bin"):      # the wheel's inputs must be committed; evidence may be pending
        print("REFUSED: product inputs are dirty:", git("status", "--porcelain", "--", "aisef", "tests", "pyproject.toml", "bin")[:300])
        return 1
    sha = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD:aisef")
    ident = json.loads((ROOT / "closure-evidence/hardening/phase12/PHASE12-KERNEL-IDENTITY.json").read_text(encoding="utf-8"))
    w0 = json.loads(Path(a.w0).read_text(encoding="utf-8")) if Path(a.w0).is_file() else None
    dest = Path(a.dest).expanduser() / sha[:12]
    dest.mkdir(parents=True, exist_ok=True)
    dist = dest / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    b = run([a.build_python, "-m", "build", "--wheel", "--outdir", str(dist), str(ROOT)])
    wheels = sorted(dist.glob("*.whl"))
    if b.returncode or not wheels:
        print("BUILD FAILED", b.stdout[-500:], b.stderr[-800:])
        return 1
    if git("status", "--porcelain", "--", "aisef", "tests", "pyproject.toml", "bin"):
        print("REFUSED: the build dirtied the product inputs:", git("status", "--porcelain")[:300])
        return 1
    wheel = wheels[0]
    wsha = hashlib.sha256(wheel.read_bytes()).hexdigest()
    venv = dest / "w1-venv"
    shutil.rmtree(venv, ignore_errors=True)
    for cmd in ([sys.executable, "-m", "venv", str(venv)], [str(venv / "bin/pip"), "install", "-q", str(wheel)]):
        r = run(cmd)
        if r.returncode:
            print("VENV FAILED", cmd, r.stderr[-500:])
            return 1
    where = run([str(venv / "bin/python"), "-c", "import aisef; print(aisef.__file__)"], cwd=str(dest)).stdout.strip()
    ver = run([str(venv / "bin/aisef"), "--version"]).stdout.strip()
    ovenv = dest.parent / "oracle-venv"
    if not (ovenv / "bin/python").exists():
        run([sys.executable, "-m", "venv", str(ovenv)])
        run([str(ovenv / "bin/pip"), "install", "-q", *a.oracle_pins.split()])
    opins = run([str(ovenv / "bin/pip"), "list", "--format", "json"]).stdout
    # SS-65: never a second copy of an image name — the registry that the product resolves from is the only source.
    img = run([str(venv / "bin/python"), "-c", "from aisef.harness.capabilities import profile_by_stack; print(profile_by_stack('python').image)"]).stdout.strip()
    img_id = run(["docker", "image", "inspect", img, "--format", "{{.Id}}"]).stdout.strip()
    ci = run(["gh", "run", "view", a.ci_run, "--json", "conclusion,headSha,jobs"]).stdout
    ci = json.loads(ci) if ci.strip().startswith("{") else {"raw": ci[:200]}
    rec = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "candidate_sha": sha, "aisef_tree_digest": tree, "PHASE12_KERNEL_DIGEST": ident["PHASE12_KERNEL_DIGEST"],
           "tree_equals_phase12_kernel": tree == ident["PHASE12_KERNEL_DIGEST"], "version_string": ver,
           "wheel": {"file": str(wheel), "sha256": wsha, "bytes": wheel.stat().st_size, "built_with": run([a.build_python, "-m", "build", "--version"]).stdout.strip()},
           "run_venv": {"path": str(venv), "aisef_file": where, "installed_from_the_wheel": "site-packages" in where and str(ROOT) not in where},
           "oracle_venv": {"path": str(ovenv), "packages": [p for p in json.loads(opins) if p["name"] in ("coverage", "pytest")] if opins.strip().startswith("[") else opins[:200]},
           "docker_image": {"name": img, "id": img_id}, "docker_image_id": img_id, "opencode_version": run(["opencode", "--version"]).stdout.strip(),
           "ci": {"run": a.ci_run, "sha": ci.get("headSha"), "conclusion": ci.get("conclusion"), "jobs": {j.get("name"): j.get("conclusion") for j in ci.get("jobs", [])}},
           "ci_matches_candidate": ci.get("headSha") == sha, "w0": {"path": a.w0, "qualified": (w0 or {}).get("qualified"), "sha": (w0 or {}).get("sha") or (w0 or {}).get("candidate_sha"),
                  "aisef_tree": _aisef_tree_of(w0), "tree_matches_frozen": _aisef_tree_of(w0) == tree},
           "no_tag_no_publish": True, "rule": "W1 runs use run_venv's aisef only; any aisef/ change after this record voids it and the W1 runs that rest on it"}
    rec["pass"] = rec["tree_equals_phase12_kernel"] and rec["w0"]["qualified"] is True and rec["w0"]["tree_matches_frozen"] and rec["run_venv"]["installed_from_the_wheel"] and rec["ci_matches_candidate"] and rec["ci"]["conclusion"] == "success" and bool(img_id)
    Path(a.out).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: rec[k] for k in ("candidate_sha", "tree_equals_phase12_kernel", "version_string", "ci_matches_candidate", "pass")}, indent=1))
    print("wheel sha256:", wsha, "| run venv:", venv)
    return 0 if rec["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
