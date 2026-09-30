"""Shared by every rung: the frozen qualification subject, the harness digest, the platform identity, the in-process
test-case runner and the typed rung status (GREEN / FAILED / UNRUNNABLE — inability to run is never FAILED)."""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time
import traceback
import unittest
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "validation" / "v2")):
    if p not in sys.path:
        sys.path.insert(0, p)

#: Cycle 1 (QP-7, accepted and closed): the P6 seal commit, the semantic candidate the P7-FINDING-001 correction put in
#: its place and their kernel tree. Kept as the Cycle-1 lineage the Cycle-2 rungs still assert (q0 seals).
CYCLE1_SEAL_COMMIT = "b720de7c4f03061cfa07e7b9f74a74e614e52de4"
CYCLE1_SEMANTIC_CANDIDATE = "7114177834da5a7e4a0fc2c7f8fa9d067e0abaa2"
CYCLE1_KERNEL_TREE = "4d6081940f5b9dae47439f73f0157161e028d804"
CYCLE1_OUT_REL = "closure-evidence/v2/Q0-Q3"
#: The Cycle-2 qualification subject (QP-2.6; owner ruling 2026-09-30: "Run Q0-Q3 on ONE exact Cycle-2 candidate"):
#: the candidate commit, which carries the accepted C2-P5 boundary (a76177e) and the witness-independence cases.
#: Cycle 2 has no seal of its own, so the candidate is its own seal commit. The subject is the candidate's kernel
#: tree AND its validation/v2 and tests/v2 trees: every rung refuses to run unless HEAD carries all three (any change
#: to one of them is a new candidate, restarted from Q0).
SEMANTIC_CANDIDATE = "63112544f1146097b69c538d98e09e5a52c547c1"
SEAL_COMMIT = SEMANTIC_CANDIDATE
KERNEL_TREE = "f4bfc7f1291cc72fa8ade79e798f5222f3429759"
SUBJECT_TREES = {"validation/v2": "60920999bdc44dc9530e7a6fe14d1341f5615a07", "tests/v2": "f17acb6f6c2d1f64d6f32c809c4f57100ef13330"}
C2_P5_ACCEPTANCE_REL = "closure-evidence/v2/cycle2/C2-P5-ACCEPTANCE.json"
V1_PRODUCT_TREE = "4359f347378e84fcac2d213128c7c26f282c13c0"
OUT_REL = "closure-evidence/v2/cycle2/Q0-Q3"
#: the platforms the qualification claims (§20); any other platform's record is kept as a non-gate observation
QUALIFICATION_PLATFORMS = ("linux", "windows")
GREEN, FAILED, UNRUNNABLE = "GREEN", "FAILED", "UNRUNNABLE"
PASS, FAIL, ERROR, SKIP, NOT_APPLICABLE = "PASS", "FAIL", "ERROR", "SKIP", "NOT_APPLICABLE"
#: a skip for one of these reasons is a platform inapplicability, recorded and not counted; any other skip is a case
#: that could not execute here, which makes the rung UNRUNNABLE (never FAILED)
_PLATFORM_SKIP_MARKS = ("POSIX", "posix", "Windows", "windows", "Linux", "linux", "darwin", "macOS", "signal exit",
                        "BREAKAWAY_OK", "job object")   # the Windows Job Object's own semantics, named without the word Windows
#: a skip for one of these reasons is a declared optional capability absent on the platform (the qualification
#: platforms run the stdlib test runner and install no third-party runner): recorded as NOT_APPLICABLE with the
#: capability named, so the record says exactly what was not exercised there; never a rung that cannot run
OPTIONAL_CAPABILITY_SKIP_MARKS = {"pytest is not installed": "pytest adapter (optional third-party runner)",
                                  # Cycle 2 (file_artifact FA-ADV fixtures): an OS that withholds the privilege to create
                                  # a symbolic link (Windows without SeCreateSymbolicLinkPrivilege)
                                  "symlink creation not permitted here": "symbolic-link creation privilege (platform)"}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def lf_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def harness_digest() -> dict:
    """The digest of this package's sources (§25: hashed before execution, bound into every record)."""
    here = pathlib.Path(__file__).resolve().parent
    files = sorted(p for p in here.glob("*.py"))
    lines = [f"{p.relative_to(ROOT).as_posix()}\t{lf_sha(p)}" for p in files]
    return {"files": {ln.split("\t")[0]: ln.split("\t")[1] for ln in lines},
            "sha256": sha_text("\n".join(lines)), "rule": "sha256 over '<posix path>\\t<lf-sha256>' lines, sorted"}


def identity() -> dict:
    """The subject as HEAD carries it now, checked against the frozen values; the effective RFC lineage; the probe."""
    import freeze_manifest as fm
    from aisef2.probe import catalog
    from aisef2.probe import python_callable as pc
    head = git("rev-parse", "HEAD")
    kernel = git("rev-parse", "HEAD:aisef2")
    eff, links, broken = fm.lineage(ROOT)
    dirty = git("status", "--porcelain")
    return {
        "seal_commit": SEAL_COMMIT, "semantic_candidate": SEMANTIC_CANDIDATE, "kernel_tree": KERNEL_TREE,
        "head": head, "head_is_after_the_seal": head == SEAL_COMMIT or SEAL_COMMIT in git("rev-list", "HEAD").split(),
        "head_kernel_tree": kernel, "kernel_tree_is_the_candidates": kernel == KERNEL_TREE,
        "candidate_kernel_tree": git("rev-parse", f"{SEMANTIC_CANDIDATE}:aisef2"),
        "v1_product_tree": git("rev-parse", "HEAD:aisef"), "v1_product_tree_unchanged": git("rev-parse", "HEAD:aisef") == V1_PRODUCT_TREE,
        "validation_v2_tree": git("rev-parse", "HEAD:validation/v2"), "tests_v2_tree": git("rev-parse", "HEAD:tests/v2"),
        "subject_trees": {rel: {"head": git("rev-parse", f"HEAD:{rel}"), "candidate": git("rev-parse", f"{SEMANTIC_CANDIDATE}:{rel}"),
                                "frozen": tree} for rel, tree in SUBJECT_TREES.items()},
        "cycle1": {"seal_commit": CYCLE1_SEAL_COMMIT, "semantic_candidate": CYCLE1_SEMANTIC_CANDIDATE, "kernel_tree": CYCLE1_KERNEL_TREE,
                   "records": CYCLE1_OUT_REL},
        "working_tree_clean_outside_qualification_output": all(
            ln[3:].startswith(OUT_REL) or ln[3:].startswith("validation/qualification") for ln in dirty.splitlines()),
        "rfc": {"effective_normative_digest": eff.get("rfc_normative_digest"), "effective_freeze_table_digest": eff.get("freeze_table_digest"),
                "lineage": [pathlib.Path(x["record"]).name for x in links], "lineage_end": pathlib.Path(links[-1]["record"]).name if links else None,
                "broken_links": broken},
        "probe": {"id": pc.PROBE_ID, "digest": pc.DIGEST},   # the frozen Cycle-1 identity (resolvable, inactive for its kind)
        "probes": {e.probe_id: {"digest": e.probe_digest, "kind": e.subject_kind.value, "active": e.active, "cycle": e.cycle}
                   for e in catalog.CATALOG},
        "harness": harness_digest(),
    }


def subject_problems(ident: dict) -> list[str]:
    out = []
    if not ident["kernel_tree_is_the_candidates"]:
        out.append(f"HEAD's aisef2 tree {ident['head_kernel_tree']} is not the candidate's {KERNEL_TREE}: a new candidate, restart from Q0")
    if ident["candidate_kernel_tree"] != KERNEL_TREE:
        out.append("the semantic candidate does not carry the frozen kernel tree")
    if not ident["head_is_after_the_seal"]:
        out.append("HEAD does not descend from the seal commit")
    for rel, t in ident["subject_trees"].items():
        if not (t["head"] == t["candidate"] == t["frozen"]):
            out.append(f"HEAD's {rel} tree {t['head']} is not the candidate's {t['frozen']}: a new candidate, restart from Q0")
    if not ident["v1_product_tree_unchanged"]:
        out.append("the V1 product tree changed")
    if ident["rfc"]["broken_links"] or ident["rfc"]["lineage_end"] != "AISEF-V2-RFC-AMENDMENT-V2-006.json":
        out.append("the effective RFC lineage does not end at V2-006 unbroken")
    return out


def platform_id() -> dict:
    system = platform.system().lower()
    free_gb = round(shutil.disk_usage(ROOT).free / 1e9, 1)
    return {"os": system, "os_release": platform.release(), "python": platform.python_version(), "free_disk_gb": free_gb,
            "implementation": platform.python_implementation(), "machine": platform.machine(),
            "runner_os": os.environ.get("RUNNER_OS"), "ci_run": os.environ.get("GITHUB_RUN_ID"),
            "ci_job": os.environ.get("GITHUB_JOB"), "ci_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "qualification_platform": system in QUALIFICATION_PLATFORMS,
            "range_mechanism": "windows-job" if os.name == "nt" else "posix-session-and-group",
            "label": f"{system}-py{platform.python_version_tuple()[0]}.{platform.python_version_tuple()[1]}"}


# ------------------------------------------------------------------------------------------------- cases

def _outcome(case_id: str, result: unittest.TestResult, seconds: float) -> dict:
    out = {"id": case_id, "outcome": PASS, "seconds": round(seconds, 3)}
    if result.skipped:
        reason = result.skipped[0][1]
        capability = next((cap for mark, cap in OPTIONAL_CAPABILITY_SKIP_MARKS.items() if mark in reason), None)
        out["outcome"] = NOT_APPLICABLE if capability or any(m in reason for m in _PLATFORM_SKIP_MARKS) else SKIP
        out["detail"] = reason
        if capability:
            out["optional_capability_absent"] = capability
    elif result.errors:
        out["outcome"], out["detail"] = ERROR, result.errors[0][1][-2000:]
    elif result.failures:
        out["outcome"], out["detail"] = FAIL, result.failures[0][1][-2000:]
    elif result.testsRun != 1:
        out["outcome"], out["detail"] = ERROR, f"{result.testsRun} tests ran for one case"
    return out


def run_case(module: str, cls: str, name: str) -> dict:
    """One named test method, run in-process through a suite (class setup honoured), quiet on stdout."""
    case_id = f"{module}:{cls}.{name}"
    try:
        klass = getattr(importlib.import_module(module), cls)
        suite = unittest.TestSuite([klass(name)])
    except Exception as e:  # noqa: BLE001 — the case cannot be built: UNRUNNABLE, typed by the exception, never FAILED
        return {"id": case_id, "outcome": ERROR, "detail": f"cannot load: {type(e).__name__}: {e}", "unrunnable": True, "seconds": 0.0}
    result = unittest.TestResult()
    t = time.monotonic()
    with _quiet():
        suite.run(result)
    return _outcome(case_id, result, time.monotonic() - t)


def run_module(module: str, *, classes: tuple[str, ...] | None = None) -> list[dict]:
    """Every test of a module (or of the named classes), one outcome each."""
    try:
        mod = importlib.import_module(module)
        loader = unittest.defaultTestLoader
        suites = [loader.loadTestsFromTestCase(getattr(mod, c)) for c in classes] if classes else [loader.loadTestsFromModule(mod)]
    except Exception as e:  # noqa: BLE001
        return [{"id": module, "outcome": ERROR, "detail": f"cannot load: {type(e).__name__}: {e}", "unrunnable": True, "seconds": 0.0}]
    out = []
    for suite in suites:
        for case in _flatten(suite):
            if isinstance(case, unittest.TestCase) and case.__class__.__name__ != "_FailedTest":
                name = case.id().rsplit(".", 1)[-1]
                out.append(run_case(module, case.__class__.__name__, name))
            elif isinstance(case, unittest.TestCase):
                out.append({"id": f"{module}:{case.id()}", "outcome": ERROR, "detail": "failed to load", "unrunnable": True, "seconds": 0.0})
    return out


def _flatten(suite):
    for x in suite:
        if isinstance(x, unittest.TestSuite):
            yield from _flatten(x)
        else:
            yield x


class _quiet:
    def __enter__(self):
        self._out, self._err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        return self

    def __exit__(self, *exc):
        sys.stdout, sys.stderr = self._out, self._err
        return False


def counts(cases: list[dict]) -> dict:
    return {k: sum(1 for c in cases if c["outcome"] == k) for k in (PASS, FAIL, ERROR, SKIP, NOT_APPLICABLE)}


def status_of(cases: list[dict], problems: list[str] = (), harness_problems: list[str] = ()) -> str:
    """GREEN: every applicable case passed and no typed assertion failed. FAILED: a case executed and failed, or a
    typed assertion of the rung does not hold. UNRUNNABLE: the harness could not measure, or a case could not be built
    or executed here (never presented as FAILED — owner §21)."""
    failed = bool(problems) or any(c["outcome"] in (FAIL, ERROR) and not c.get("unrunnable") for c in cases)
    if failed:
        return FAILED
    if harness_problems or any(c.get("unrunnable") or c["outcome"] == SKIP for c in cases):
        return UNRUNNABLE
    return GREEN


def problems_of(cases: list[dict]) -> list[str]:
    return [f"{c['id']}: {c['outcome']} — {c.get('detail', '').strip().splitlines()[-1] if c.get('detail') else ''}"
            for c in cases if c["outcome"] not in (PASS, NOT_APPLICABLE)]


def capture(fn) -> tuple[object, str | None]:
    """Run a harness measurement; an exception is the harness's own problem (UNRUNNABLE material), returned typed."""
    try:
        return fn(), None
    except BaseException as e:  # noqa: BLE001 — an InvariantError here is a finding, reported, never swallowed silently
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        return None, f"{type(e).__module__}.{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"


# ------------------------------------------------------------------------------------------------- records

def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False, sort_keys=False) + "\n"


def write(rel: str, record: dict) -> pathlib.Path:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(record), encoding="utf-8")
    return p


def emit(rel: str, record: dict) -> None:
    """Print a record for a CI log: zlib+base64, in 4000-character lines between markers, so a job on another
    platform can hand its record back byte-for-byte (nothing is downloaded; the log is read)."""
    payload = base64.b64encode(zlib.compress(render(record).encode("utf-8"), 9)).decode("ascii")
    print(f"===AISEF-QUALIFICATION-RECORD {rel} {sha_text(render(record))}===")
    for i in range(0, len(payload), 4000):
        print(payload[i:i + 4000])
    print("===AISEF-QUALIFICATION-END===")
    sys.stdout.flush()


def decode(lines: list[str]) -> dict:
    return json.loads(zlib.decompress(base64.b64decode("".join(lines))).decode("utf-8"))


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
