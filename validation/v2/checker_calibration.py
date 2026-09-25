"""WP-0.5 — Q0 checker calibration: every Q0 checker must be observed saying NO.

For every registered checker, the checker's REAL decision function is run three ways:

1. on the clean repository — it must PASS;
2. on its committed known-bad fixture (`tests/v2/fixtures/known_bad/<name>.json`) — it must FAIL, and with the
   specific failure the fixture names, so a checker that fails for the wrong reason (a missing file) does not count;
3. replaced by an **always-PASS mutant** — calibration must then FAIL. That proves calibration itself can say no:
   a checker that cannot reject anything is caught, not certified.

A checker whose fixture no longer fails it is itself a Q0 failure (`--check` exits non-zero).

    python -P validation/v2/checker_calibration.py            # write closure-evidence/v2/Q0-CHECKER-CALIBRATION.json
    python -P validation/v2/checker_calibration.py --check    # fail if any checker is uncalibrated or the record is stale
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import time
import tempfile
from dataclasses import dataclass, replace
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parents[2]
V2 = ROOT / "validation" / "v2"
FIXTURES = ROOT / "tests" / "v2" / "fixtures" / "known_bad"
OUT_REL = "closure-evidence/v2/Q0-CHECKER-CALIBRATION.json"


def _load(name: str, path: pathlib.Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _edit(text: str, fx: dict) -> str:
    if text.count(fx["find"]) != 1:
        raise AssertionError(f"fixture anchor for {fx['checker']} must occur exactly once")
    return text.replace(fx["find"], fx["replace"])


def _git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.t", *args], cwd=root,
                          capture_output=True, encoding="utf-8", check=True).stdout.strip()


@dataclass(frozen=True)
class Checker:
    name: str
    package: str
    clean: Callable[[], list[str]]
    known_bad: Callable[[dict], list[str]]
    sources: tuple[str, ...] = ()


# --------------------------------------------------------------------------------------- the registry

def _freeze_manifest() -> Checker:
    fm = _load("aisef_v2_freeze_manifest", V2 / "freeze_manifest.py")

    def bad(fx):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            for rel in fm.BASELINE_FILES:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, root / rel)
            rfc = root / fm.RFC_REL
            rfc.write_text(_edit(rfc.read_text(encoding="utf-8"), fx), encoding="utf-8")
            return fm.check(root)
    return Checker("freeze_manifest", "WP-0.1", lambda: fm.check(ROOT), bad, ("validation/v2/freeze_manifest.py",))


def _v1_evidence_guard() -> Checker:
    g = _load("aisef_v2_v1_evidence_guard", V2 / "v1_evidence_guard.py")

    def bad(fx):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            _git(root, "init", "-q")
            (root / "closure-evidence" / "hardening").mkdir(parents=True)
            (root / "closure-evidence" / "v2").mkdir()
            (root / "closure-evidence" / "hardening" / "a.json").write_text('{"a": 1}\n', encoding="utf-8")
            _git(root, "add", ".")
            _git(root, "commit", "-q", "-m", "close")
            close = _git(root, "rev-parse", "HEAD")
            (root / g.BASELINE_REL).write_text(json.dumps(g.build_baseline(root, close)), encoding="utf-8")
            _git(root, "add", ".")
            _git(root, "commit", "-q", "-m", "baseline")
            (root / "closure-evidence" / "hardening" / "a.json").write_text('{"a": 9}\n', encoding="utf-8")
            _git(root, "commit", "-q", "-am", "mutate")
            return g.check(root, source=close)
    return Checker("v1_evidence_guard", "WP-0.4", lambda: g.check(), bad, ("validation/v2/v1_evidence_guard.py",))


def _arch_catalog() -> Checker:
    gc = _load("aisef_v2_gen_arch_catalog", V2 / "gen_arch_catalog.py")
    text = lambda: (ROOT / gc.CATALOG_REL).read_text(encoding="utf-8")  # noqa: E731
    return Checker("arch_catalog", "WP-0.2", lambda: gc.check(),
                   lambda fx: gc.compare(gc.code_vocabularies(), _edit(text(), fx)),
                   ("validation/v2/gen_arch_catalog.py",))


def _f_conformance() -> Checker:
    fc = _load("aisef_v2_freeze_conformance", V2 / "freeze_conformance.py")

    def bad(fx):
        rfc, code, manifest = fc.load_inputs()
        return fc.problems_of(fc.evaluate(_edit(rfc, fx), code, manifest))
    return Checker("f_conformance", "WP-0.3", lambda: fc.problems_of(fc.evaluate(*fc.load_inputs())), bad,
                   ("validation/v2/freeze_conformance.py",))


def _plan_validate() -> Checker:
    pv = _load("aisef_v2_plan_validate", V2 / "plan_validate.py")
    return Checker("plan_validate", "plan correction", lambda: pv.validate(pv.load()),
                   lambda fx: pv.validate(pv.apply_fixture(pv.load(), fx["fixture"])),
                   ("validation/v2/plan_validate.py",))


def _plan_docs_check() -> Checker:
    pv = _load("aisef_v2_plan_validate", V2 / "plan_validate.py")

    def bad(fx):
        with tempfile.TemporaryDirectory() as t:
            docs = pathlib.Path(t)
            for f in pv.DOCS.iterdir():
                if f.is_file():
                    shutil.copy(f, docs / f.name)
            target = docs / fx["file"]
            target.write_text(_edit(target.read_text(encoding="utf-8"), fx), encoding="utf-8")
            saved, pv.DOCS = pv.DOCS, docs
            try:
                return pv.generate(pv.load(saved / "cycle1-manifest.json"), write=False)
            finally:
                pv.DOCS = saved
    return Checker("plan_docs_check", "plan correction", lambda: pv.generate(pv.load(), write=False), bad,
                   ("validation/v2/plan_validate.py",))


def _state_model_prover() -> Checker:
    pr = _load("aisef_v2_prove_state_model_fix", V2 / "prove_state_model_fix.py")

    def verdict(result: dict) -> list[str]:
        return [] if pr.holds(result) else \
            [k for k in ("normalised_trees_identical", "assertions_identical", "test_methods_identical")
             if not result[k]] + (["writes_into_closure_evidence"] if result["writes_into_closure_evidence"] else [])

    def bad(fx):
        old = subprocess.run(["git", "show", f"{fx['base']}:{pr.TARGET}"], cwd=ROOT, capture_output=True,
                             encoding="utf-8", check=True).stdout
        new = _edit((ROOT / pr.TARGET).read_text(encoding="utf-8"), fx)
        return verdict(pr.prove_sources(old, new))
    return Checker("state_model_prover", "WP-0.4", lambda: verdict(pr.prove("6ac6f74")), bad,
                   ("validation/v2/prove_state_model_fix.py",))


def _v2_encoding_scanner() -> Checker:
    tm = _load("_v1_test_meta_scanner", ROOT / "tests" / "test_meta.py")
    scan = tm.TestKhongDocDauRaBangBangMaCuaMay("test_phep_quet_that_su_thay_duoc_loi")._thieu

    def clean():
        return [f"{p.relative_to(ROOT)} line {n}" for p in sorted(V2.rglob("*.py")) for n in scan(p)]

    def bad(fx):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "x.py"
            p.write_text(fx["source"], encoding="utf-8")
            return [f"line {n}" for n in scan(p)]
    return Checker("v2_encoding_scanner", "WP-0.4", clean, bad, ("tests/test_meta.py",))


def _packaging_check() -> Checker:
    pc = _load("aisef_v2_packaging_check", V2 / "packaging_check.py")
    text = lambda: (ROOT / "pyproject.toml").read_text(encoding="utf-8")  # noqa: E731
    return Checker("packaging_check", "WP-0.2", lambda: pc.check(text()), lambda fx: pc.check(_edit(text(), fx)),
                   ("validation/v2/packaging_check.py",))


def _run_history() -> Checker:
    rh = _load("aisef_v2_run_history", V2 / "run_history.py")
    policy = json.loads((ROOT / rh.POLICY_REL).read_text(encoding="utf-8"))
    return Checker("run_history", "P1 retry policy", lambda: rh.check(ROOT),
                   lambda fx: rh.append_only_problems(fx["versions"]) + rh.entry_problems(fx["versions"][-1], policy),
                   ("validation/v2/run_history.py",))


def _kernel_rule(name: str, rule: str, package: str) -> Callable[[], Checker]:
    def make() -> Checker:
        ks = _load("aisef_v2_kernel_static_checks", V2 / "kernel_static_checks.py")
        return Checker(name, package, lambda: ks.check(ROOT, (rule,)),
                       lambda fx: ks.violations(fx["path"], fx["source"], (fx["rule"],)),
                       ("validation/v2/kernel_static_checks.py",))
    return make


def _except_boundaries() -> Checker:
    eb = _load("aisef_v2_except_boundaries", V2 / "except_boundaries.py")
    return Checker("except_boundaries", "WP-5.5 (RFC §4 uncontainable)", lambda: eb.check(ROOT),
                   lambda fx: eb.violations(fx["path"], fx["source"]), ("validation/v2/except_boundaries.py",))


def _invariants_doc() -> Checker:
    idoc = _load("aisef_v2_invariants_doc", V2 / "invariants_doc.py")

    def bad(fx):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            (root / fx["path"]).parent.mkdir(parents=True, exist_ok=True)
            (root / fx["path"]).write_text(_edit((ROOT / fx["path"]).read_text(encoding="utf-8"), fx), encoding="utf-8")
            return idoc.check(root)
    return Checker("invariants_doc", "WP-5.5 (F10 registry/docs sync)", lambda: idoc.check(ROOT), bad,
                   ("validation/v2/invariants_doc.py",))


def _destructive_authority() -> Checker:
    """INV-MUTATION-AUTHORITY, static half: every destructive call site is ledgered with an authority source whose
    derivation the checker validates. Known bad (MUT-AUTH-NEG-1): a kill of a pid read from subject output, with a
    ledger row claiming a test-created handle — the claimed derivation is rejected."""
    da = _load("aisef_v2_destructive_authority", V2 / "destructive_authority.py")

    def bad(fx):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            for rel, text in fx["files"].items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            for scope in da.SCOPES:
                (root / scope).mkdir(parents=True, exist_ok=True)
            (root / da.LEDGER_REL).write_text(json.dumps({"sites": fx["ledger"]}), encoding="utf-8")
            return da.check(root)
    return Checker("destructive_authority", "P4 post-seal hygiene (INV-MUTATION-AUTHORITY)", lambda: da.check(ROOT), bad,
                   ("validation/v2/destructive_authority.py",))


def _cleanup_authority() -> Checker:
    """P4-FINDING-011: the mutation runner's only way to signal a process. Clean: on this host, a child the runner
    starts after its boundary is selectable (dry run). Known bad: a report naming processes that are not the runner's
    — launchd, a shell, a child born before the boundary, a launchd-owned agent — is refused for the named reason."""
    ca = _load("aisef_v2_cleanup_authority", V2 / "cleanup_authority.py")

    def clean():
        if not ca.POSIX:
            return []
        boundary = ca.establish(ROOT)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.2)
            report = ca.signal_owned(boundary, pids=[child.pid], dry_run=True)
        finally:
            child.kill()
            child.wait()
        return [f"unproven: {u}" for u in report.unproven] + (
            [] if [x["id"] for x in report.signalled] == [child.pid] else ["the runner's own child was not selected"])

    def bad(fx):
        table = {row[0]: ca.Host(*row) for row in fx["table"]}
        boundary = ca.Boundary(**fx["boundary"])
        report = ca.signal_owned(boundary, pids=fx["reported"]["pids"], groups=fx["reported"]["groups"], dry_run=True,
                                 table=table)
        return [f"{u['kind']} {u['id']}: {u['why']}" for u in report.unproven] + [
            f"selected a process that is not the runner's: {x['id']}" for x in report.signalled]
    return Checker("cleanup_authority", "P4 correction (P4-FINDING-011)", clean, bad,
                   ("validation/v2/cleanup_authority.py",))


def _mutation() -> Checker:
    mu = _load("aisef_v2_mutation", V2 / "mutation.py")

    def clean():
        return mu.check(ROOT)

    def bad(fx):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            rel = fx["target"].split("::")[0]
            for path, text in ((rel, fx["module"]), ("aisef2/__init__.py", ""), ("aisef2/cal/__init__.py", ""),
                               ("tests/v2/__init__.py", ""), ("tests/v2/p1/__init__.py", ""),
                               ("tests/v2/p1/test_m.py", fx["test"])):
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(text, encoding="utf-8")
            return mu.target_problems(mu.run_target(root, fx["target"], ["tests/v2/p1/test_m.py"]), root)
    return Checker("mutation", "WP-1.1", clean, bad, ("validation/v2/mutation.py",))


def _p1_evidence() -> Checker:
    ev = _load("aisef_v2_p1_evidence", V2 / "p1_evidence.py")
    return Checker("p1_evidence", "WP-1.1", lambda: ev.check(ROOT), lambda fx: ev.problems_of(fx["record"]),
                   ("validation/v2/p1_evidence.py",))


def _p2_evidence() -> Checker:
    ev = _load("aisef_v2_p2_evidence", V2 / "p2_evidence.py")
    return Checker("p2_evidence", "WP-2.1", lambda: ev.check(ROOT), lambda fx: ev.problems_of(fx["record"]),
                   ("validation/v2/p2_evidence.py",))


def _p3_evidence() -> Checker:
    ev = _load("aisef_v2_p3_evidence", V2 / "p3_evidence.py")
    return Checker("p3_evidence", "WP-3.1", lambda: ev.check(ROOT), lambda fx: ev.problems_of(fx["record"]),
                   ("validation/v2/p3_evidence.py",))


def _p4_evidence() -> Checker:
    ev = _load("aisef_v2_p4_evidence", V2 / "p4_evidence.py")
    return Checker("p4_evidence", "WP-4.1", lambda: ev.check(ROOT), lambda fx: ev.problems_of(fx["record"]),
                   ("validation/v2/p4_evidence.py",))


def _p5_evidence() -> Checker:
    ev = _load("aisef_v2_p5_evidence", V2 / "p5_evidence.py")
    return Checker("p5_evidence", "WP-5.1", lambda: ev.check(ROOT), lambda fx: ev.problems_of(fx["record"]),
                   ("validation/v2/p5_evidence.py",))


def _p6_evidence() -> Checker:
    ev = _load("aisef_v2_p6_evidence", V2 / "p6_evidence.py")
    return Checker("p6_evidence", "WP-6.2", lambda: ev.check(ROOT), lambda fx: ev.problems_of(fx["record"]),
                   ("validation/v2/p6_evidence.py",))


def _owned_run() -> Checker:
    ow = _load("aisef_v2_owned_run", V2 / "owned_run.py")
    return Checker("owned_run", "WP-4.2", lambda: ow.check(ROOT), lambda fx: ow.problems_of(fx["measurement"]),
                   ("validation/v2/owned_run.py",))


def _refmodel_independence() -> Checker:
    ri = _load("aisef_v2_refmodel_independence", V2 / "refmodel_independence.py")
    return Checker("refmodel_independence", "WP-3.5", lambda: ri.check(ROOT),
                   lambda fx: ri.violations(fx["path"], fx["source"]), ("validation/v2/refmodel_independence.py",))


def _migration_table() -> Checker:
    gm = _load("aisef_v2_gen_migration_table", V2 / "gen_migration_table.py")

    def bad(fx):
        table = gm.generate(ROOT)
        texts = {rel: (ROOT / rel).read_text(encoding="utf-8") for rel in (gm.TABLE_REL, gm.DOC_REL)}
        texts[fx["path"]] = _edit(texts[fx["path"]], fx)
        return gm.compare(table, texts[gm.TABLE_REL], texts[gm.DOC_REL])
    return Checker("migration_table", "WP-6.1 (RFC §31 generated, --checked)", lambda: gm.check(ROOT), bad,
                   ("validation/v2/gen_migration_table.py",))


def _gen_specs() -> Checker:
    gs = _load("aisef_v2_gen_specs", V2 / "gen_specs.py")

    def bad(fx):
        with tempfile.TemporaryDirectory() as t:
            corpus = pathlib.Path(t) / "corpus"
            shutil.copytree(ROOT / gs.CORPUS_REL, corpus)
            spec = corpus / "specs" / fx["spec"]
            spec.write_text(_edit(spec.read_text(encoding="utf-8"), fx), encoding="utf-8")
            return gs.check(corpus)
    return Checker("gen_specs", "WP-1.2", lambda: gs.check(), bad, ("validation/v2/gen_specs.py",))


def _plan_semantics() -> Checker:
    pv = _load("aisef_v2_plan_validate", V2 / "plan_validate.py")
    return Checker("plan_semantics", "P2 plan correction", lambda: pv.check_f_probe_absence_semantics(pv.load()),
                   lambda fx: pv.check_f_probe_absence_semantics(pv.apply_fixture(pv.load(), fx["fixture"])),
                   ("validation/v2/plan_validate.py",))


def _plan_baseline() -> Checker:
    pv = _load("aisef_v2_plan_validate", V2 / "plan_validate.py")

    def bad(fx):
        m = pv.load()
        m["architecture_baseline"].update(fx["set"])
        return pv.check_g_baseline(m)
    return Checker("plan_baseline", "P2 plan correction", lambda: pv.check_g_baseline(pv.load()), bad,
                   ("validation/v2/plan_validate.py",))


REGISTRY: list[Callable[[], Checker]] = [
    _freeze_manifest, _v1_evidence_guard, _arch_catalog, _f_conformance, _plan_validate, _plan_docs_check,
    _state_model_prover, _v2_encoding_scanner, _packaging_check, _run_history,
    _kernel_rule("no_prose_control", "NO_PROSE_CONTROL", "WP-1.1"),
    _kernel_rule("no_raw_verdict_routing", "NO_RAW_VERDICT_ROUTING", "WP-1.3"),
    _kernel_rule("retryable_only_in_taxonomy", "RETRYABLE_ONLY_IN_TAXONOMY", "WP-1.4"),
    _kernel_rule("no_verdict_from_absence_declaration", "NO_VERDICT_FROM_ABSENCE_DECLARATION", "P1 hygiene (RFC §10.2)"),
    _kernel_rule("result_only_through_binding", "RESULT_ONLY_THROUGH_BINDING", "P2 correction (PROBE-BIND-1)"),
    _kernel_rule("no_time_in_projections", "NO_TIME_IN_PROJECTIONS", "WP-3.3"),
    _kernel_rule("no_side_retry_counter", "NO_SIDE_RETRY_COUNTER", "WP-4.5"),
    _kernel_rule("sentinel_is_not_evidence", "SENTINEL_IS_NOT_EVIDENCE", "WP-4.3"),
    _kernel_rule("one_signal_authority", "ONE_SIGNAL_AUTHORITY", "P4 correction (V2-003, RFC §9.3)"),
    _kernel_rule("candidate_only_execution", "CANDIDATE_ONLY_EXECUTION", "WP-5.3 (invariant IX)"),
    _kernel_rule("no_developer_artefact_at_parent", "NO_DEVELOPER_ARTEFACT_AT_PARENT", "WP-5.5 (invariant IX)"),
    _except_boundaries, _invariants_doc,
    _mutation, _cleanup_authority, _destructive_authority, _p1_evidence, _p2_evidence, _p3_evidence, _p4_evidence, _p5_evidence, _owned_run, _refmodel_independence, _gen_specs, _plan_semantics, _plan_baseline,
    _migration_table, _p6_evidence,
]


# --------------------------------------------------------------------------------------- calibration

#: Modules in validation/v2 that are not Q0 checkers themselves. Everything else there must be calibrated.
NOT_CHECKERS = {"validation/v2/checker_calibration.py"}


def uncovered_checker_modules(checkers: list[Checker]) -> list[str]:
    covered = {s for c in checkers for s in c.sources}
    present = {str(p.relative_to(ROOT)).replace("\\", "/") for p in V2.glob("*.py")} - NOT_CHECKERS
    return sorted(present - covered)


def fixture_for(name: str) -> dict | None:
    path = FIXTURES / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def calibrate(c: Checker) -> dict:
    fx = fixture_for(c.name)
    if fx is None:
        return {"checker": c.name, "package": c.package, "calibrated": False, "reason": "no committed known-bad fixture"}
    clean = c.clean()
    bad = c.known_bad(fx)
    names_expected = any(fx["expect"] in p for p in bad)
    return {
        "checker": c.name, "package": c.package, "fixture": f"tests/v2/fixtures/known_bad/{c.name}.json",
        "clean_passes": not clean, "clean_problems": clean[:5],
        "rejects_known_bad": bool(bad), "rejects_for_the_expected_reason": names_expected,
        "expected": fx["expect"], "observed": bad[:5],
        "calibrated": not clean and bool(bad) and names_expected,
    }


def always_pass_mutant(c: Checker) -> Checker:
    return replace(c, clean=lambda: [], known_bad=lambda fx: [])


def run() -> dict:
    checkers = [make() for make in REGISTRY]
    results = []
    for c in checkers:
        r = calibrate(c)
        r["always_pass_mutant_rejected_by_calibration"] = not calibrate(always_pass_mutant(c))["calibrated"]
        results.append(r)
    return {
        "record": "AISEF V2 — Q0 CHECKER CALIBRATION",
        "work_package": "WP-0.5",
        "rule": "each checker must pass the clean repository, fail its committed known-bad fixture for the named "
                "reason, and calibration must reject an always-PASS mutant of it",
        "checker_count": len(results),
        "uncovered_checker_modules": uncovered_checker_modules(checkers),
        "calibrated_count": sum(r["calibrated"] for r in results),
        "always_pass_mutants_rejected": sum(r["always_pass_mutant_rejected_by_calibration"] for r in results),
        "checkers": results,
    }


def problems_of(result: dict) -> list[str]:
    out = [f"checker module with no calibration: {m}" for m in result["uncovered_checker_modules"]]
    for r in result["checkers"]:
        if not r["calibrated"]:
            out.append(f"{r['checker']} is NOT calibrated: {r.get('reason') or r}")
        if not r["always_pass_mutant_rejected_by_calibration"]:
            out.append(f"calibration failed to reject an always-PASS mutant of {r['checker']}")
    return out


def render(result: dict) -> str:
    return json.dumps(result, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    result = run()
    problems = problems_of(result)
    if "--check" in argv:
        committed = ROOT / OUT_REL
        if not committed.exists() or committed.read_text(encoding="utf-8") != render(result):
            problems.append(f"{OUT_REL} is missing or stale")
    for r in result["checkers"]:
        print(f"{'OK  ' if r['calibrated'] else 'FAIL'} {r['checker']:22s} clean={r.get('clean_passes')} "
              f"rejects={r.get('rejects_for_the_expected_reason')} "
              f"always-pass-mutant-caught={r['always_pass_mutant_rejected_by_calibration']}")
    for p in problems:
        print(f"FAIL  {p}")
    print(f"calibrated {result['calibrated_count']}/{result['checker_count']}; "
          f"always-PASS mutants rejected {result['always_pass_mutants_rejected']}/{result['checker_count']}")
    if "--check" not in argv and not problems:
        (ROOT / OUT_REL).write_text(render(result), encoding="utf-8")
        print(f"wrote {OUT_REL}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
