"""V2 production-publish gate (docs/v2/V2-STABLE-RELEASE-CHARTER.md G8, §10, §19, §22; docs/v2/RELEASE-PROCESS.md).

.github/workflows/release.yml runs it before its publish job; exit 0 only when production PyPI may receive VERSION:

    python -P validation/v2_release_gate.py <version>

For the V2 release path it REPLACES the V1 client-conformance freshness gate (tests/test_release_gate.py
TestCongPhatHanh: docs/CONFORMANCE.md no older than aisef/control/conformance.py MAX_AGE_DAYS), as charter G8 allows
("current or explicitly replaced by this V2 release charter") and §10 requires. That V1 code stays, for the legacy
surface, and no longer blocks or authorizes a V2 release.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUS_REL = "closure-evidence/v2/release/V2-STABLE-STATUS.json"      # charter §22
DECISIONS_REL = "closure-evidence/v2/cycle2/RELEASE-DECISIONS.json"   # append-only owner rulings (charter G9)
STABLE = re.compile(r"\d+\.\d+\.\d+")


def problems(version: str, pyproject_version: str, status: dict, decisions: dict, rc: dict | None,
             rc_problems: list[str]) -> list[str]:
    """Why production PyPI must not receive `version`; empty means it may.

    The latest RELEASE-DECISIONS entry that rules on PRODUCTION_PUBLISH decides: it must be the owner's
    (approver "human:owner") with decision.PRODUCTION_PUBLISH == "AUTHORIZED" and decision.VERSION == `version`.
    A later entry that holds or revokes publication therefore wins over an earlier authorization.

    `rc` is the frozen release candidate (V2.0-RC1-FREEZE.json, charter G2) and `rc_problems` its check on this
    commit: the published bytes are the RC's only when this commit's shipped files are the RC's (the build then uses
    the RC's epoch, and the publish job compares the files with the frozen digests).
    """
    out = []
    if rc is None:
        out.append("no frozen release candidate (closure-evidence/v2/release/V2.0-RC1-FREEZE.json, charter G2)")
    elif rc.get("rc", {}).get("version") != version:
        out.append(f"the frozen candidate is {rc.get('rc', {}).get('version')!r}, the tag says {version!r}")
    out += [f"release candidate: {p}" for p in rc_problems]
    if not STABLE.fullmatch(version):
        out.append(f"{version!r} is not a stable X.Y.Z version (RC and dev versions never reach production PyPI)")
    if pyproject_version != version:
        out.append(f"pyproject version is {pyproject_version!r}, the tag says {version!r}")
    if status.get("FINAL_RELEASE_READY") != "PASS":
        out.append(f"{STATUS_REL}: FINAL_RELEASE_READY is {status.get('FINAL_RELEASE_READY')!r}, not 'PASS'")
    if status.get("OPEN_V2_0_BLOCKERS") != []:
        out.append(f"{STATUS_REL}: OPEN_V2_0_BLOCKERS is {status.get('OPEN_V2_0_BLOCKERS')!r}, not []")
    rulings = [e for e in decisions.get("entries", []) if "PRODUCTION_PUBLISH" in (e.get("decision") or {})]
    last = max(rulings, key=lambda e: e.get("seq", 0), default=None)
    if last is None:
        out.append(f"{DECISIONS_REL}: no entry rules on PRODUCTION_PUBLISH")
    elif (last.get("approver"), last["decision"].get("PRODUCTION_PUBLISH"), last["decision"].get("VERSION")) != \
            ("human:owner", "AUTHORIZED", version):
        out.append(f"{DECISIONS_REL} seq {last.get('seq')} does not authorize publishing {version}: approver "
                   f"{last.get('approver')!r}, PRODUCTION_PUBLISH {last['decision'].get('PRODUCTION_PUBLISH')!r}, "
                   f"VERSION {last['decision'].get('VERSION')!r}")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2

    def load(rel: str) -> dict:
        p = ROOT / rel
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    sys.path.insert(0, str(ROOT))
    from validation.qualification import release_rc
    rc = load(release_rc.OUT_REL) or None
    found = problems(argv[0], pyproject, load(STATUS_REL), load(DECISIONS_REL), rc, release_rc.check(rc) if rc else [])
    for p in found:
        print(f"FAIL  {p}")
    print(f"V2 release gate for {argv[0]}: " + ("FAIL — production publication is not authorized" if found else "PASS"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
