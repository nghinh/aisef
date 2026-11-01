"""V2.1.0 scoped release qualification (owner RELEASE-DECISIONS seq 7, Option 1, 2026-11-01).

Runs the real unit suite — in process, exactly as `python -m unittest discover -s tests` does (the release path
wraps THIS in validation/v2/owned_run.py, so the process-leak discipline still holds) — keeps every test's authentic
PASS/FAIL, and decides a SEPARATE release-qualification result against a version-scoped, exact allowlist:

    python -P validation/qualification/release_qualify.py [--version X.Y.Z]   # default: pyproject's version

Qualification PASSES only when, for the current platform:
  * every failing/errored test is named in the allowlist (no new, unclassified, or materially different failure), and
  * every allowlisted test that protects security, isolation, destructive authority, or process safety carries
    clean-environment evidence (otherwise that exception is itself a blocker), and
  * all non-excepted tests pass.
It applies the allowlist ONLY to the version the manifest is written for (2.1.0). For any other version the allowlist
is empty, so the gate is the ordinary "the whole suite is green". Raw verdicts are printed and never rewritten.

The allowlist is closure-evidence/v2/release/V<version>-QUALIFICATION-ALLOWLIST.json; its schema is RELEASE_ALLOWLIST
below. The mandatory build / install / integrity / release checks (lint, wheel, staging, v2_release_gate) stay their
own jobs and must pass on their own — this gate covers the unit suite only.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

SAFETY_CATEGORIES = {"security", "isolation", "destructive-authority", "process-safety"}


def base_id(test_id: str) -> str:
    """The test method identity, dropping any subTest parametrisation suffix. unittest reports a failing subTest's
    id() as '<module>.<Class>.<method> (param=...)' or '... [param]'; the allowlist names the method, and a subTest
    is a parametrisation of it, so comparison and the safety-evidence check are made on the method identity. A new
    method failing is still caught (its base id is not in the allowlist); only further subTests of an already-accepted
    method are covered."""
    return re.split(r" [\(\[]", test_id, maxsplit=1)[0]


def platform_token() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith(("win", "cygwin", "msys")):
        return "windows"
    return sys.platform


def allowlist_rel(version: str) -> str:
    return f"closure-evidence/v2/release/V{version}-QUALIFICATION-ALLOWLIST.json"


def load_allowlist(version: str, root: pathlib.Path = ROOT) -> dict:
    p = root / allowlist_rel(version)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def decide(version: str, measured_fail: set[str], manifest: dict, token: str) -> dict:
    """The release-qualification decision for one platform. Pure, so it is unit-testable without running the suite."""
    scoped = manifest.get("version") == version          # the allowlist is honoured only for its own version
    exceptions = manifest.get("exceptions", []) if scoped else []
    applicable = [e for e in exceptions if token in e.get("platforms", [])]
    allowed = {e["test"] for e in applicable}

    measured_base = {base_id(t) for t in measured_fail}  # a failing subTest is matched by its method identity
    unexpected = sorted(measured_base - allowed)
    stale = sorted(allowed - measured_base)              # excepted but passed now — fine, just unused
    missing_evidence = sorted(
        e["test"] for e in applicable
        if e.get("category") in SAFETY_CATEGORIES and not e.get("clean_env_evidence")
    )

    problems = [f"unexpected/unclassified failure, not in the {version} allowlist: {t}" for t in unexpected]
    problems += [f"safety-sensitive exception without clean-environment evidence (blocker): {t}" for t in missing_evidence]
    return {
        "version": version, "platform": token, "scoped_to_version": scoped,
        "raw_failing": sorted(measured_fail), "raw_fail_count": len(measured_fail),
        "failing_methods": sorted(measured_base), "failing_method_count": len(measured_base),
        "allowlisted_applicable": sorted(allowed),
        "excepted_and_observed": sorted(measured_base & allowed),
        "excepted_but_passed": stale,
        "unexpected": unexpected, "missing_clean_env_evidence": missing_evidence,
        "qualification": "PASS" if not problems else "FAIL", "problems": problems,
    }


def run_suite() -> set[str]:
    """Run the suite in process, exactly as the CI unit step does, and return the authentic failing-test id set."""
    sys.path.insert(0, str(ROOT))
    suite = unittest.TestLoader().discover(str(ROOT / "tests"))
    res = unittest.TextTestRunner(verbosity=1, resultclass=unittest.TextTestResult).run(suite)
    return ({tc.id() for tc, _ in res.failures}
            | {tc.id() for tc, _ in res.errors}
            | {tc.id() for tc in getattr(res, "unexpectedSuccesses", [])})


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    version = argv[argv.index("--version") + 1] if "--version" in argv else \
        tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

    token = platform_token()
    manifest = load_allowlist(version)
    measured_fail = run_suite()
    d = decide(version, measured_fail, manifest, token)

    print("\n=== RAW SUITE VERDICT (authentic, never rewritten) ===")
    print(f"failing/errored tests: {d['raw_fail_count']}")
    for t in d["raw_failing"]:
        print(f"  FAIL  {t}")
    print(f"\n=== RELEASE QUALIFICATION ({version}, platform {token}, scoped={d['scoped_to_version']}) ===")
    print(f"failing methods: {d['failing_method_count']} (from {d['raw_fail_count']} failing tests/subTests)  "
          f"excepted & observed: {len(d['excepted_and_observed'])}  "
          f"excepted but now passing: {len(d['excepted_but_passed'])}  unexpected: {len(d['unexpected'])}")
    for p in d["problems"]:
        print(f"  BLOCKER  {p}")
    print(f"RELEASE QUALIFICATION for {version}: {d['qualification']}"
          + ("" if d["qualification"] == "PASS" else " — a new/unclassified failure or missing safety evidence blocks publication"))
    return 0 if d["qualification"] == "PASS" else 1


def _selftest() -> None:
    m = {"version": "2.1.0", "exceptions": [
        {"test": "t.a", "category": "record-currency", "platforms": ["linux", "darwin", "windows"]},
        {"test": "t.sec", "category": "isolation", "platforms": ["windows"], "clean_env_evidence": {"run": "x"}},
        {"test": "t.sec2", "category": "process-safety", "platforms": ["linux"]},  # no evidence -> blocker on linux
    ]}
    # all failures excepted, safety evidence present -> PASS
    assert decide("2.1.0", {"t.a"}, m, "darwin")["qualification"] == "PASS"
    assert decide("2.1.0", {"t.a", "t.sec"}, m, "windows")["qualification"] == "PASS"
    # a new failure -> FAIL
    assert decide("2.1.0", {"t.a", "t.new"}, m, "darwin")["qualification"] == "FAIL"
    # safety-sensitive exception without evidence, applicable on this platform -> FAIL even if it's the only failure
    assert decide("2.1.0", {"t.sec2"}, m, "linux")["qualification"] == "FAIL"
    # wrong version -> allowlist not honoured -> any failure fails (scope is exclusively 2.1.0)
    assert decide("2.1.1", {"t.a"}, m, "darwin")["qualification"] == "FAIL"
    assert decide("2.1.1", set(), m, "darwin")["qualification"] == "PASS"
    # excepted but passing is not a failure
    r = decide("2.1.0", set(), m, "darwin")
    assert r["qualification"] == "PASS" and r["excepted_but_passed"] == ["t.a"]
    # a failing subTest is matched by its method identity (base id), not reported as unexpected
    assert decide("2.1.0", {"t.a (checker='mutation')", "t.a [registry]"}, m, "darwin")["qualification"] == "PASS"
    # but a new METHOD failing (even as a subTest) is still rejected
    assert decide("2.1.0", {"t.brand_new (x=1)"}, m, "darwin")["qualification"] == "FAIL"
    print("release_qualify selftest: OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        _selftest()
    else:
        sys.exit(main())
